package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/**
 * Invariants that must hold for EVERY fixture in this package, across EVERY compiler
 * that produced one — as against a pin on an example somebody thought of.
 *
 * <p>GUIDELINES §13.8, at the third occurrence. Three times now a rule has been read off
 * whichever class files were compiled to hand and then written down as a property of the
 * class-file FORMAT:
 *
 * <ul>
 *   <li>a signature's parameters aligned by the difference in two counts, right for an
 *       inner class and an enum and wrong for a local class that captures;
 *   <li>`ACC_MANDATED` called "exactly the set the short tables omit", right for four
 *       shapes and wrong for a record's compact constructor;
 *   <li>every `LineNumberTable` entry treated as a line in this class's own file, right
 *       for javac and wrong for every Kotlin method that calls an `inline` function.
 * </ul>
 *
 * <p>Each was caught by review, and each fix was a better per-case pin — which is what
 * §13.8 says not to do: prose and examples have been tried on this cause and lost. The
 * format permits more than any one compiler emits, so an example test only ever covers
 * the compiler whose output somebody remembered to compile.
 *
 * <p>These assert properties of the FACTS instead. They need nobody to think of the right
 * compiler: a new one that breaks an assumption fails here the day its fixture lands.
 */
class FactInvariantTest {

    /** Every compiled fixture in this package, whichever compiler produced it. */
    private static List<Path> compiledFixtures() throws Exception {
        List<Path> classes = new ArrayList<>();
        for (String tree : new String[] {"build/classes/java/test", "build/classes/kotlin/test"}) {
            Path root = Path.of(tree, "dev/sextant/extractor");
            if (!Files.isDirectory(root)) continue;
            try (Stream<Path> found = Files.walk(root)) {
                found.filter(path -> path.toString().endsWith(".class")).forEach(classes::add);
            }
        }
        assertTrue(classes.size() > 20, "expected the fixtures to be compiled; found " + classes.size());
        return classes;
    }

    /** The source file a class states, resolved against this module's own source roots. */
    private static Path sourceOf(String fileName) {
        for (String tree : new String[] {"src/test/java", "src/test/kotlin"}) {
            Path candidate = Path.of(tree, "dev/sextant/extractor", fileName);
            if (Files.isRegularFile(candidate)) return candidate;
        }
        return null;
    }

    @Test
    void no_symbol_claims_a_line_its_own_source_file_does_not_have() throws Exception {
        // The invariant W6's defect broke, stated so that no one has to think of Kotlin
        // inlining to catch it: a line number is a position in a FILE, and the file is
        // the one the class names. Measured before the fix, a 13-line Kotlin source
        // reported a method ending at line 17 — a line belonging to the standard
        // library's `_Collections.kt`.
        //
        // This catches any compiler that splices foreign lines in, including ones nobody
        // here has compiled: ECJ, Groovy, Scala, and whatever comes next.
        List<String> offences = new ArrayList<>();
        for (Path compiled : compiledFixtures()) {
            String[] stated = {null};
            List<String> facts = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(Files.readAllBytes(compiled), "doc", reason -> {}, name -> stated[0] = name);
            Path source = stated[0] == null ? null : sourceOf(stated[0]);
            if (source == null) continue;
            long available = Files.readAllLines(source).size();
            for (String fact : facts) {
                if (!fact.contains("\"kind\":\"symbol\"")) continue;
                int end = intField(fact, "\"line_end\":");
                if (end > available) {
                    offences.add(stated[0] + " has " + available + " lines; a symbol claims "
                        + end + " — " + compiled.getFileName());
                }
            }
        }
        assertTrue(offences.isEmpty(), "line numbers outside their own file:\n" + String.join("\n", offences));
    }

    @Test
    void no_symbol_reports_a_range_that_runs_backwards() throws Exception {
        // Cheap, and it holds whatever the compiler: `line_end` is a maximum over the
        // same table `line_start` is a minimum over, so an inversion means the two came
        // from different places — which is what a filter applied to one and not the
        // other would produce.
        List<String> offences = new ArrayList<>();
        for (Path compiled : compiledFixtures()) {
            for (String fact : new ClassScanner("com.acme/orders", "1.0.0")
                    .scan(Files.readAllBytes(compiled), "doc")) {
                if (!fact.contains("\"kind\":\"symbol\"")) continue;
                int start = intField(fact, "\"line_start\":");
                int end = intField(fact, "\"line_end\":");
                if (end < start) offences.add(compiled.getFileName() + ": " + start + " > " + end);
                // 0 is the "not stated" sentinel and must be BOTH or neither: one of the
                // two set alone means a construct with no `Code` attribute picked up half
                // a range from somewhere.
                if ((start == 0) != (end == 0)) {
                    offences.add(compiled.getFileName() + ": half a range, " + start + "-" + end);
                }
            }
        }
        assertTrue(offences.isEmpty(), String.join("\n", offences));
    }

    private static int intField(String fact, String key) {
        int at = fact.indexOf(key);
        if (at < 0) return 0;
        int from = at + key.length();
        int to = from;
        while (to < fact.length() && Character.isDigit(fact.charAt(to))) to++;
        return to == from ? 0 : Integer.parseInt(fact.substring(from, to));
    }
}
