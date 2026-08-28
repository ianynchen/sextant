package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

class EnumAnnotationScanTest {

    private List<String> scanEnumAnnotated() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/EnumAnnotated.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-enum-annotated");
        }
    }

    /** D00 §5a lists an enum reference in the literal model, and a dropped one is
     *  indistinguishable from an absent argument: {@code @RequestMapping} with no
     *  method and {@code @RequestMapping(method = GET)} would look identical. */
    @Test
    void records_each_enum_constant_in_an_array_valued_annotation_argument() throws Exception {
        assertTrue(scanEnumAnnotated().stream().anyMatch(line ->
            line.contains("Verb#GET.") && line.contains("Verb#POST.")));
    }

    @Test
    void records_a_scalar_enum_valued_annotation_argument() throws Exception {
        assertTrue(scanEnumAnnotated().stream().anyMatch(line ->
            line.contains("\"single\":\"dev/sextant/extractor/Verb#POST.\"")));
    }
}
