package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

class AnnotationScanTest {

    @Test
    void emits_annotation_facts_with_their_argument_values_when_a_class_is_annotated()
            throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/Annotated.class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-annotated");
            assertTrue(lines.stream().anyMatch(line ->
                line.contains("\"kind\":\"annotation\"")
                    && line.contains("Deprecated")));
        }
    }
}
