package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** {@code FieldSample.java} is compiled by Gradle's own test compilation,
 *  exactly like {@code Sample.java} and this directory's other fixtures, so
 *  these assertions are about what javac actually emits — a committed
 *  source fixture satisfies that just as well as reaching into a sibling
 *  module's build output, without a dependency this module's build doesn't
 *  express. */
class FieldScanTest {

    private List<String> scanFieldSample() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/FieldSample.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-field-sample");
        }
    }

    @Test
    void emits_a_field_symbol_with_its_wire_type_when_a_class_has_fields() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"field\"")
                && line.contains("FieldSample#total.")
                && line.contains("\"wire_type\":\"integer\"")
                && line.contains("\"wire_format\":\"int64\"")));
    }

    @Test
    void states_javas_own_nullability_rule_without_reading_any_annotation() throws Exception {
        List<String> lines = scanFieldSample();
        assertTrue(lines.stream().anyMatch(l -> l.contains("FieldSample#reference.")
            && l.contains("\"nullable\":true") && l.contains("\"nullable_resolution\":\"partial\"")));
        assertTrue(lines.stream().anyMatch(l -> l.contains("FieldSample#total.")
            && l.contains("\"nullable\":false") && l.contains("\"nullable_resolution\":\"resolved\"")));
    }

    @Test
    void projects_a_string_field_to_the_string_wire_type() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#reference.")
            && l.contains("\"wire_type\":\"string\"")));
    }

    @Test
    void projects_a_boxed_long_field_to_integer_int64_like_its_primitive() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#boxedTotal.")
            && l.contains("\"wire_type\":\"integer\"") && l.contains("\"wire_format\":\"int64\"")));
    }

    /** D1 assigns collections to the extractor's own projection, but a known
     *  wire form like BigDecimal's is catalog knowledge (D2) — expanding it
     *  structurally would surface intVal/scale/intCompact/precision, none of
     *  which is on the wire. Mapping it to "object" here, rather than
     *  guessing "number", is what leaves a catalog known_types entry
     *  something to override. */
    @Test
    void projects_a_collection_field_to_array_and_leaves_a_known_type_field_open() throws Exception {
        List<String> lines = scanFieldSample();
        assertTrue(lines.stream().anyMatch(l -> l.contains("FieldSample#tags.")
            && l.contains("\"wire_type\":\"array\"")));
        assertTrue(lines.stream().anyMatch(l -> l.contains("FieldSample#amount.")
            && l.contains("\"wire_type\":\"object\"")));
    }

    /** A map's keys are arbitrary, which "object" cannot say (D1): an object
     *  shape has named fields, and collapsing the two would make a
     *  {@code Map<String, X>} look type-compatible with a record. */
    @Test
    void projects_a_map_field_to_the_map_wire_type() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#attributes.")
            && l.contains("\"wire_type\":\"map\"")));
    }
}
