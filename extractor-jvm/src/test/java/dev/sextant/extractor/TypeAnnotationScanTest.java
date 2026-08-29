package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** {@code FieldSample.java} carries JSpecify annotations so these assertions
 *  are about what javac actually emits — same rationale as
 *  {@link FieldScanTest}. */
class TypeAnnotationScanTest {

    private List<String> scan() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/FieldSample.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-field-sample");
        }
    }

    @Test
    void records_a_type_use_annotation_on_a_field() throws Exception {
        assertTrue(scan().stream().anyMatch(l ->
            l.contains("FieldSample#note.") && l.contains("org/jspecify/annotations/Nullable#")));
    }

    @Test
    void distinguishes_an_annotation_on_the_outer_type_from_one_on_a_type_argument() throws Exception {
        // `@Nullable List<String>` and `List<@Nullable String>` are different
        // contracts, and ASM tells them apart only through the TypePath. Without
        // it both collapse to "this field has a Nullable somewhere on it", which
        // is the ambiguity D00 §5a says the per-reference value exists to remove.
        List<String> lines = scan();
        assertTrue(lines.stream().anyMatch(l ->
            l.contains("FieldSample#maybeList.") && l.contains("\"type_path\":\"\"")));
        assertTrue(lines.stream().anyMatch(l ->
            l.contains("FieldSample#listOfMaybe.") && l.contains("\"type_path\":\"0;\"")));
    }

    /** Every other annotation in this file is JSpecify, which is `RUNTIME` and
     *  lands only in the visible table. `ClassRetainedNullable` is declared
     *  `CLASS`-retention in the extractor's own test sources specifically so one
     *  case here proves the invisible table is read too — the real-world case,
     *  since `javax.annotation.Nullable` and the JetBrains spellings are mostly
     *  `CLASS`, and a module compiled over a decade lands annotations in both. */
    @Test
    void records_a_class_retention_type_use_annotation_from_the_invisible_table() throws Exception {
        assertTrue(scan().stream().anyMatch(l ->
            l.contains("FieldSample#classRetained.")
                && l.contains("ClassRetainedNullable#")
                && l.contains("\"retention\":\"class\"")));
    }

    /** A method has two kinds of type reference — the return type, and each
     *  parameter — so unlike a field's single reference, the annotation itself
     *  does not say which one it belongs to; only ASM's `TypeReference` sort
     *  does. Both are annotated here so a scanner that discarded the sort (and
     *  attached every method type annotation to the same place, as a prior
     *  round of this task did) would produce byte-identical JSON for "the
     *  return type is nullable" and "the parameter is nullable" — this proves
     *  they land in different, addressable places in the signature instead. */
    @Test
    void distinguishes_a_return_type_annotation_from_a_parameter_type_annotation() throws Exception {
        List<String> lines = scan();
        assertTrue(lines.stream().anyMatch(l ->
            l.contains("FieldSample#getName(")
                && l.contains("\"return_type_annotations\":[{")
                && l.contains("org/jspecify/annotations/Nullable#")));
        assertTrue(lines.stream().anyMatch(l ->
            l.contains("FieldSample#getName(")
                && l.contains("\"type_annotations\":[{")
                && l.contains("org/jspecify/annotations/Nullable#")));
    }
}
