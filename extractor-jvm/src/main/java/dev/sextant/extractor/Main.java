package dev.sextant.extractor;

import java.io.Closeable;
import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

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
            try (ClassSource source = ClassSource.of(classes)) {
                List<String> classFiles = source.names();
                // The silent-success hole, closed (2I Task 6). A `--classes`
                // that yields no class file at all used to report
                // `documents: 0, facts: 0` at exit 0 with an empty `uncovered`
                // — indistinguishable from a scan that genuinely found
                // nothing to say. The two honest shapes are split by what is
                // wrong: an input this extractor cannot READ is a failed
                // request and exits non-zero (`ClassSource.of` throws); an
                // input it read fine that simply holds no class file is a
                // finding ABOUT the input, so it rides the channel findings
                // already ride (FR-17's `uncovered`) and reaches
                // metadata.json and the rendered gaps list by itself. A jar of
                // zero classes is legitimate-but-suspicious, and this is what
                // makes it visible instead of silent.
                //
                // Named by the COORDINATE where one was given, and only by the
                // path otherwise. An `uncovered` entry is read by a person, in
                // metadata.json and in a published bundle: an absolute archive
                // path under someone's home directory identifies nothing once
                // it leaves the machine that produced it, while the coordinate
                // is the same name the configuration used to ask for it.
                if (classFiles.isEmpty()) {
                    String named = options.getOrDefault("origin", options.get("classes"));
                    uncovered.add(named + ": no class files found");
                }
                for (String classRelative : classFiles) {
                    byte[] bytes = source.read(classRelative);
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

    /** Where the class files being scanned come from. Two forms, because a
     *  library ships as a jar and a module's own output does not: a directory
     *  tree of loose `.class` files, and a jar read as a zip.
     *
     *  <p>Both answer with class-relative POSIX names in one fixed sorted
     *  order, which is what keeps a scan byte-identical between runs and
     *  between platforms (NFR-1) — a zip's own entry order is whatever the
     *  archiver wrote and is never relied on. */
    private interface ClassSource extends Closeable {

        /** Every `.class` file this source holds, class-relative and sorted. */
        List<String> names() throws IOException;

        byte[] read(String name) throws IOException;

        /** Refuses anything it cannot read, rather than reporting an empty
         *  scan: a `--classes` naming a regular file that is not a jar (or a
         *  path that does not exist at all) is a failed REQUEST, and a failed
         *  request exits non-zero. */
        static ClassSource of(Path classes) throws IOException {
            if (Files.isDirectory(classes)) {
                return new DirectorySource(classes);
            }
            if (Files.isRegularFile(classes) && classes.getFileName().toString().endsWith(".jar")) {
                return new JarSource(classes);
            }
            throw new IllegalArgumentException(
                "--classes must name a directory of class files or a .jar file: " + classes);
        }
    }

    private record DirectorySource(Path root) implements ClassSource {

        @Override public List<String> names() throws IOException {
            try (Stream<Path> walk = Files.walk(root)) {
                return walk.filter(p -> p.toString().endsWith(".class"))
                           .map(p -> posix(root.relativize(p)))
                           .sorted()
                           .toList();
            }
        }

        @Override public byte[] read(String name) throws IOException {
            return Files.readAllBytes(root.resolve(name));
        }

        @Override public void close() {}
    }

    private static final class JarSource implements ClassSource {
        private final ZipFile zip;

        JarSource(Path jar) throws IOException {
            // Throws on a file that is not a readable zip, which `of` above
            // lets propagate: a corrupt jar is an error, never an empty scan.
            this.zip = new ZipFile(jar.toFile());
        }

        @Override public List<String> names() {
            // Directory entries are skipped by the `.class` filter itself; a
            // zip may also omit them entirely, so nothing here may depend on
            // their presence.
            return zip.stream()
                      .map(ZipEntry::getName)
                      .filter(name -> name.endsWith(".class"))
                      .sorted()
                      .toList();
        }

        @Override public byte[] read(String name) throws IOException {
            ZipEntry entry = zip.getEntry(name);
            try (var stream = zip.getInputStream(entry)) {
                return stream.readAllBytes();
            }
        }

        @Override public void close() throws IOException {
            zip.close();
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
        document.put("scanner_version", JsonOut.string("9.15"));
        document.put("content_hash", JsonOut.string("sha256:" + contentHash));
        document.put("origin_entry", JsonOut.string(options.get("classes")));
        // The library this document was extracted FROM, as its coordinate —
        // written only when `--origin` names one (D00 §2). Omitted entirely
        // for a module's own output, rather than written as null, so a scan
        // of a module is byte-for-byte the scan it was before opt-in library
        // extraction existed.
        //
        // The TIER moves with it, and must: `module_output` on a class this
        // module did not build is a claim known to be false. `dependency` is
        // the factual answer and deliberately not `first_party`/`third_party`
        // — those need the group patterns D04 §2 declares and nothing
        // implements, so either would be a guess about ownership dressed as
        // an observation (D00 §4).
        if (options.get("origin") != null) {
            document.put("origin", JsonOut.string(options.get("origin")));
            document.put("origin_tier", JsonOut.string("dependency"));
        } else {
            document.put("origin_tier", JsonOut.string("module_output"));
        }
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
        fields.put("scanner_version", JsonOut.string("9.15"));
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
