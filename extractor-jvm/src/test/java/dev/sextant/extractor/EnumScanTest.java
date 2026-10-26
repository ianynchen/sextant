package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** What an enumeration looks like in the fact stream. {@code Verb} is the enum
 *  {@code EnumAnnotated.java} already declares, compiled by Gradle's own test
 *  compilation like every other fixture here. */
class EnumScanTest {

    private List<String> scanVerb() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/dev/sextant/extractor/Verb.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0").scan(in.readAllBytes(), "doc-verb");
        }
    }

    /** D00 §4 has `enum` in the construct-kind set and D00 §5b has it in the
     *  wire vocabulary, and only the type's own fact can say which one this is:
     *  a type reference to it looks exactly like a reference to a record.
     *  Reported as `class`, a closed set of constants expands structurally and
     *  every constant becomes a field of a payload nobody sends. */
    @Test
    void names_an_enumeration_by_its_own_construct_kind() throws Exception {
        assertTrue(scanVerb().stream().anyMatch(line ->
            line.contains("\"symbol\":\"sextant-jvm maven com.acme/orders 1.0.0 "
                    + "dev/sextant/extractor/Verb#\"")
                && line.contains("\"construct_kind\":\"enum\"")));
    }

    /** {@code $VALUES} is compiler machinery, not a declaration: nobody wrote
     *  it, so there is no fact to emit about it. A modifier would be the wrong
     *  answer — that says "a field somebody declared, kept off the wire" — and
     *  the symbol graph would carry a member no source file contains.
     *
     *  <p>**The one fact that does name it is the WRITE**, and that is a fact about an
     *  instruction rather than a declaration: {@code <clinit>} stores {@code $values()}'s
     *  result into the field, which D00 §5's {@code field_write} reports since 2026-10-26
     *  (CP-33 row 6). A write into a compiler-made field was a fact before that too — a
     *  Kotlin lambda class's captured {@code $seen} is {@code ACC_SYNTHETIC}, and the walk
     *  reads its write — so that one write is the only line allowed to name it, and it is
     *  asserted exactly: one {@code field_write}, by {@code <clinit>}. */
    @Test
    void emits_no_fact_at_all_for_a_compiler_synthesized_field() throws Exception {
        List<String> naming = scanVerb().stream().filter(line -> line.contains("VALUES")).toList();
        assertEquals(1, naming.size(), String.join("\n", naming));
        assertTrue(naming.get(0).contains("\"kind\":\"field_write\"")
            && naming.get(0).contains("\"field\":\"dev/sextant/extractor/Verb#$VALUES.\"")
            && naming.get(0).contains("#<clinit>("), naming.get(0));
    }

    /** The constants themselves are declarations, and they are bound to the
     *  type — so they are emitted, carrying the modifier that keeps them off
     *  the wire. */
    @Test
    void marks_each_declared_constant_as_bound_to_the_type() throws Exception {
        assertTrue(scanVerb().stream().anyMatch(line ->
            line.contains("Verb#GET.") && line.contains("\"static\":true")));
    }
}
