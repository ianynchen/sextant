package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertFalse;
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
     *  the symbol graph would carry a member no source file contains. */
    @Test
    void emits_no_fact_at_all_for_a_compiler_synthesized_field() throws Exception {
        assertFalse(scanVerb().stream().anyMatch(line -> line.contains("VALUES")));
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
