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
}
