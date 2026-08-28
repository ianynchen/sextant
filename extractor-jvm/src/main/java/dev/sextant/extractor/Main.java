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
            try (Stream<Path> walk = Files.walk(classes)) {
                List<Path> classFiles = walk
                    .filter(p -> p.toString().endsWith(".class"))
                    .filter(p -> !p.getFileName().toString().contains("$"))
                    .sorted()
                    .toList();
                for (Path classFile : classFiles) {
                    byte[] bytes = Files.readAllBytes(classFile);
                    String relative = classes.relativize(classFile).toString()
                        .replace(".class", ".java");
                    String documentId = sha256(relative);
                    List<String> lines = scanner.scan(bytes, documentId);
                    writeFactFile(out.resolve(relative), relative, documentId,
                                  options, sha256Bytes(bytes), lines);
                    documents++;
                    facts += lines.size();
                }
            }
            System.out.println(report(documents, facts));
        } catch (Exception failure) {
            System.err.println("extractor failed: " + failure);
            System.exit(1);
        }
    }

    private static void writeFactFile(Path target, String relative, String documentId,
                                      Map<String, String> options, String contentHash,
                                      List<String> factLines) throws IOException {
        Path path = Path.of(target.toString().replace(".java", ".jsonl"));
        Files.createDirectories(path.getParent());
        TreeMap<String, String> document = new TreeMap<>();
        document.put("kind", JsonOut.string("document"));
        document.put("document_id", JsonOut.string(documentId));
        document.put("relative_path", JsonOut.string(relative));
        document.put("module_id", JsonOut.string(options.get("module-id")));
        document.put("language", JsonOut.string("java"));
        document.put("sextant_version", JsonOut.string(options.getOrDefault("sextant-version", "0.1.0")));
        document.put("fact_schema_version", JsonOut.string("1.0.0"));
        document.put("scanner_id", JsonOut.string("asm"));
        document.put("scanner_version", JsonOut.string("9.7"));
        document.put("content_hash", JsonOut.string("sha256:" + contentHash));
        document.put("origin_entry", JsonOut.string(options.get("classes")));
        document.put("origin_tier", JsonOut.string("module_output"));
        document.put("redaction_set_hash", JsonOut.string(options.getOrDefault("redaction-hash", "sha256:none")));
        document.put("partial", "false");
        document.put("partial_reason", "null");

        List<String> all = new ArrayList<>();
        all.add(JsonOut.object(document));
        all.addAll(factLines);
        Files.write(path, String.join("\n", all).concat("\n").getBytes("UTF-8"));
    }

    private static String report(int documents, int facts) {
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("documents", String.valueOf(documents));
        fields.put("facts", String.valueOf(facts));
        fields.put("scanner_id", JsonOut.string("asm"));
        fields.put("scanner_version", JsonOut.string("9.7"));
        fields.put("uncovered", "[]");
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
