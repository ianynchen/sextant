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

    /** D3 (corrected): Java's type system settles nullability outright — every
     *  reference permits null and every primitive forbids it — so both cases are
     *  `resolved`, never `partial`. `resolution` is candidate-set semantics
     *  (CONTEXT.md) that a boolean has no analogue for; whether anyone
     *  *declared* intent is a separate question, answered elsewhere by counting
     *  annotated fields, not by weakening this flag. */
    @Test
    void states_javas_own_nullability_rule_without_reading_any_annotation() throws Exception {
        List<String> lines = scanFieldSample();
        assertTrue(lines.stream().anyMatch(l -> l.contains("FieldSample#reference.")
            && l.contains("\"nullable\":true") && l.contains("\"nullable_resolution\":\"resolved\"")));
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

    /** D00 §5a: "`List<OrderLine>` keeps `OrderLine`" — a generic argument is a
     *  full type reference of its own, not a bare string. The erased descriptor
     *  alone cannot say this (`List<String>` and a raw `List` erase identically);
     *  it can only come from reading the field's generic {@code Signature}. */
    @Test
    void keeps_a_simple_generics_argument_as_a_full_type_reference() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#tags.")
            && l.contains("\"arguments\":[{\"arguments\":[],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\","
                + "\"wire_format\":\"\",\"wire_type\":\"string\"}]")));
    }

    /** The generic argument is one of our own types, not a JDK box or
     *  collection — it must keep its own real symbol and wire type
     *  ({@code object}, since nothing here expands it structurally; that is a
     *  later task's job), never collapse to a bare {@code List#}. */
    @Test
    void keeps_a_first_party_generics_argument_as_a_full_type_reference() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#items.")
            && l.contains("\"wire_type\":\"array\"")
            && l.contains("\"arguments\":[{\"arguments\":[],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\","
                + "\"symbol\":\"dev/sextant/extractor/FieldSampleItem#\","
                + "\"wire_format\":\"\",\"wire_type\":\"object\"}]")));
    }

    /** {@code Map<String, List<String>>}: the second argument is itself
     *  parameterized, proving the recursion actually recurses rather than
     *  stopping one level down. */
    @Test
    void recurses_into_a_nested_generics_argument() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#nestedTags.")
            && l.contains("\"wire_type\":\"map\"")
            && l.contains("\"arguments\":[{\"arguments\":[],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\","
                + "\"wire_format\":\"\",\"wire_type\":\"string\"},{\"arguments\":[{\"arguments\":[],"
                + "\"nullable\":true,\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\","
                + "\"wire_format\":\"\",\"wire_type\":\"string\"}],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/util/List#\","
                + "\"wire_format\":\"\",\"wire_type\":\"array\"}]")));
    }
}
