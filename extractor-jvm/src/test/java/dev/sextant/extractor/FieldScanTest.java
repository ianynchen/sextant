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

    /** An array keeps its element as a real type argument, exactly as
     *  {@code List<E>} does. The element is in the erased descriptor and nowhere else —
     *  javac writes no Signature attribute for a field typed with no type variable and no
     *  parameterization — and it survives there only as the {@code []} suffix on the
     *  symbol. Leaving it there makes {@code FieldSampleItem[]} and {@code String[]} the
     *  same {@code array} holding nothing, which no consumer can tell apart and no report
     *  can name. */
    @Test
    void keeps_an_erased_arrays_element_as_a_full_type_reference() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#alternates.")
            && l.contains("\"symbol\":\"dev/sextant/extractor/FieldSampleItem#[]\"")
            && l.contains("\"wire_type\":\"array\"")
            && l.contains("\"arguments\":[{\"arguments\":[],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\","
                + "\"symbol\":\"dev/sextant/extractor/FieldSampleItem#\","
                + "\"wire_format\":\"\",\"wire_type\":\"object\"}]")));
    }

    /** `A-M10`: the number of `[` is part of an array type's identity (JVMS 4.3.2, JLS
     *  10.1), and every dimension past the first was being dropped. ASM's
     *  {@code Type#getElementType} returns an array's INNERMOST element type rather than
     *  its component type, so `descriptorName(getElementType()) + "[]"` appended exactly
     *  one `[]` however many the descriptor carried — making {@code FieldSampleItem[][]}
     *  and {@code FieldSampleItem[]} byte-identical facts, which a DR-5 contract
     *  comparison of a caller sending one against a callee expecting the other reads as
     *  equal.
     *
     *  <p>Both halves are asserted, because the defect had both: the SYMBOL carries two
     *  dimensions, and the single ARGUMENT is the one-dimensional array the outer one
     *  holds — not the innermost element, which is what {@code expansion.py::_described}
     *  reads and hashes. */
    @Test
    void keeps_every_dimension_of_a_multidimensional_array() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#alternateGroups.")
            && l.contains("\"symbol\":\"dev/sextant/extractor/FieldSampleItem#[][]\"")
            && l.contains("\"wire_type\":\"array\"")
            && l.contains("\"arguments\":[{\"arguments\":[{\"arguments\":[],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\","
                + "\"symbol\":\"dev/sextant/extractor/FieldSampleItem#\","
                + "\"wire_format\":\"\",\"wire_type\":\"object\"}],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\","
                + "\"symbol\":\"dev/sextant/extractor/FieldSampleItem#[]\","
                + "\"wire_format\":\"\",\"wire_type\":\"array\"}]")));
    }

    /** The near-miss for the same fix, and the half that keeps it from being "append a
     *  `[]` per recursion and hope": a ONE-dimensional array must still be exactly what it
     *  was. A change that counted dimensions wrongly in the other direction would pass the
     *  test above and fail this one. */
    @Test
    void a_one_dimensional_array_is_unchanged_by_the_dimension_fix() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#alternates.")
            && l.contains("\"symbol\":\"dev/sextant/extractor/FieldSampleItem#[]\"")));
        assertTrue(scanFieldSample().stream().noneMatch(l -> l.contains("FieldSample#alternates.")
            && l.contains("[][]")));
    }

    /** The same claim through the other path: an array reached inside a generic argument
     *  is built from the Signature attribute rather than the descriptor, and the two must
     *  not disagree about whether an array says what it holds. */
    @Test
    void keeps_a_signature_arrays_element_as_a_full_type_reference() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#nameGroups.")
            && l.contains("\"arguments\":[{\"arguments\":[{\"arguments\":[],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\","
                + "\"wire_format\":\"\",\"wire_type\":\"string\"}],\"nullable\":true,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#[]\","
                + "\"wire_format\":\"\",\"wire_type\":\"array\"}]")));
    }

    /** A field bound to the type rather than to an instance is a real
     *  declaration — somebody wrote it, and a symbol graph that lost it would
     *  answer "no such field" about code that has one. What it is not is a
     *  payload field, and only the modifier says so: without it the shape pass
     *  has nothing to filter on and every constant becomes a contract nobody
     *  wrote. */
    @Test
    void marks_a_field_bound_to_the_type_rather_than_to_an_instance() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#SOURCE.")
            && l.contains("\"static\":true")));
    }

    /** The same claim, declared rather than implied: a field the language marks
     *  as not serialized reaches no payload. */
    @Test
    void marks_a_field_the_language_declares_as_not_serialized() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#cachedSummary.")
            && l.contains("\"transient\":true")));
    }

    /** Both flags are always present on a field fact, never only the true one:
     *  a consumer reading an absent key cannot tell "not static" from "this
     *  scanner does not report staticness". */
    @Test
    void states_both_modifiers_on_an_ordinary_payload_field() throws Exception {
        assertTrue(scanFieldSample().stream().anyMatch(l -> l.contains("FieldSample#reference.")
            && l.contains("\"static\":false") && l.contains("\"transient\":false")));
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
