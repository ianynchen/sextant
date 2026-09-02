package dev.sextant.extractor;

import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Stream;

/** The subprocess contract: arguments in, fact files out, a JSON report on
 *  stdout. Errors exit non-zero with a message on stderr. */
public final class Main {

    public static void main(String[] args) {
        try {
            Map<String, String> options = parse(args);
            Path classes = Path.of(options.get("classes"));
            Path out = Path.of(options.get("out"));
            ClassScanner scanner =
                new ClassScanner(options.get("coordinates"), options.get("version"));

            int documents = 0;
            int facts = 0;
            List<String> uncovered = new ArrayList<>();
            try (Stream<Path> walk = Files.walk(classes)) {
                List<Path> classFiles = walk
                    .filter(p -> p.toString().endsWith(".class"))
                    .sorted()
                    .toList();
                for (Path classFile : classFiles) {
                    String classRelative = posix(classes.relativize(classFile));
                    byte[] bytes = Files.readAllBytes(classFile);
                    // D00 §2: one class file is one document, a nested or
                    // anonymous class's own file included. The id is the sha256
                    // of the **class**-relative path, so `OrderResult` and its
                    // nested `Detail` never collide on one id; `relative_path`
                    // instead names the outer **source** file, because that is
                    // the file a human edited. The two fields answer different
                    // questions on purpose.
                    String relative = sourcePathOf(classRelative);
                    String documentId = sha256(classRelative);
                    // A Kotlin class compiled by a newer compiler than
                    // kotlin-metadata-jvm supports is not a corrupt class file —
                    // its nullability just cannot be read. The class is still
                    // scanned and its fact file still written (with Java's own
                    // rule standing in for the field), but the gap itself is an
                    // honesty obligation the same as a nested class's (FR-17).
                    List<String> lines = scanner.scan(bytes, documentId, reason ->
                        uncovered.add(classRelative + ": kotlin metadata unreadable (" + reason + ")"));
                    // Named after the class file, not after `relative`: a
                    // nested class and its outer share a source path, and two
                    // documents writing to one file would leave only the
                    // last one on disk.
                    writeFactFile(out.resolve(replaceSuffix(classRelative, ".class", ".jsonl")),
                                  relative, documentId, options, sha256Bytes(bytes), lines);
                    documents++;
                    facts += lines.size();
                }
            }
            System.out.println(report(documents, facts, uncovered));
        } catch (Exception failure) {
            System.err.println("extractor failed: " + failure);
            System.exit(1);
        }
    }

    private static void writeFactFile(Path target, String relative, String documentId,
                                      Map<String, String> options, String contentHash,
                                      List<String> factLines) throws IOException {
        Files.createDirectories(target.getParent());
        TreeMap<String, String> document = new TreeMap<>();
        document.put("kind", JsonOut.string("document"));
        document.put("document_id", JsonOut.string(documentId));
        document.put("relative_path", JsonOut.string(relative));
        document.put("module_id", JsonOut.string(options.get("module-id")));
        document.put("language", JsonOut.string("java"));
        document.put("sextant_version", JsonOut.string(options.getOrDefault("sextant-version", "0.1.0")));
        document.put("fact_schema_version", JsonOut.string("1.0.0"));
        document.put("scanner_id", JsonOut.string("asm"));
        document.put("scanner_version", JsonOut.string("9.10"));
        document.put("content_hash", JsonOut.string("sha256:" + contentHash));
        document.put("origin_entry", JsonOut.string(options.get("classes")));
        document.put("origin_tier", JsonOut.string("module_output"));
        document.put("redaction_set_hash", JsonOut.string(options.getOrDefault("redaction-hash", "sha256:none")));
        document.put("partial", "false");
        document.put("partial_reason", "null");

        List<String> all = new ArrayList<>();
        all.add(JsonOut.object(document));
        all.addAll(factLines);
        Files.write(target, String.join("\n", all).concat("\n").getBytes("UTF-8"));
    }

    /** Forward slashes whatever the platform. `relative_path` is hashed into
     *  the document id and reappears in artifact names, so a backslash here
     *  would make one module produce different documents on Windows. */
    private static String posix(Path relative) {
        StringBuilder joined = new StringBuilder();
        for (Path part : relative) {
            if (joined.length() > 0) joined.append('/');
            joined.append(part);
        }
        return joined.toString();
    }

    /** Suffix-aware, because `String.replace` is a *global* substring replace:
     *  it rewrites every occurrence, so a workspace path holding ".java"
     *  anywhere would be corrupted mid-string rather than re-extensioned. */
    private static String replaceSuffix(String value, String from, String to) {
        if (!value.endsWith(from)) {
            throw new IllegalArgumentException("expected " + value + " to end with " + from);
        }
        return value.substring(0, value.length() - from.length()) + to;
    }

    /** The source file a class file was compiled from (D00 §2): everything from
     *  the class name's first {@code $} onwards is the compiler's nesting
     *  notation, not part of any file name — {@code OrderResult$Detail.class}
     *  and the anonymous {@code OrderController$1.class} were both edited as
     *  their outer class's {@code .java}.
     *
     *  <p>Searched from the last separator rather than across the whole path,
     *  because a directory is free to hold a {@code $} of its own and cutting
     *  there would name a source file in a package that does not exist. */
    private static String sourcePathOf(String classRelative) {
        String withoutSuffix = replaceSuffix(classRelative, ".class", "");
        int nested = withoutSuffix.indexOf('$', withoutSuffix.lastIndexOf('/') + 1);
        return (nested < 0 ? withoutSuffix : withoutSuffix.substring(0, nested)) + ".java";
    }

    private static String report(int documents, int facts, List<String> uncovered) {
        List<String> quoted = new ArrayList<>();
        for (String source : uncovered) quoted.add(JsonOut.string(source));
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("documents", String.valueOf(documents));
        fields.put("facts", String.valueOf(facts));
        fields.put("scanner_id", JsonOut.string("asm"));
        fields.put("scanner_version", JsonOut.string("9.10"));
        fields.put("uncovered", JsonOut.array(quoted));
        return JsonOut.object(fields);
    }

    private static Map<String, String> parse(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int i = 0; i < args.length - 1; i += 2) {
            options.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        }
        return options;
    }

    private static String sha256(String value) throws Exception {
        return sha256Bytes(value.getBytes("UTF-8"));
    }

    private static String sha256Bytes(byte[] value) throws Exception {
        StringBuilder hex = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(value)) {
            hex.append(String.format("%02x", b));
        }
        return hex.toString();
    }
}
