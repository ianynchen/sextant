package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Reads the real compiled output of the {@code orders-service} fixture's
 *  {@code OrderRequest} — CI's "prime the fixture" step and
 *  {@code fixtures/orders-service && mvn -q -o compile} both put it at this
 *  path before this suite runs — so these assertions are about what javac
 *  actually emits, not a hand-built stand-in. */
class FieldScanTest {

    private List<String> scan(String simpleName) throws Exception {
        Path classFile = Path.of("..", "fixtures", "orders-service", "target", "classes",
            "com", "acme", "orders", "contracts", simpleName + ".class");
        byte[] classBytes = Files.readAllBytes(classFile);
        return new ClassScanner("com.acme/orders", "1.0.0").scan(classBytes, "doc-" + simpleName);
    }

    @Test
    void emits_a_field_symbol_with_its_wire_type_when_a_class_has_fields() throws Exception {
        assertTrue(scan("OrderRequest").stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"field\"")
                && line.contains("OrderRequest#total.")
                && line.contains("\"wire_type\":\"integer\"")
                && line.contains("\"wire_format\":\"int64\"")));
    }

    @Test
    void states_javas_own_nullability_rule_without_reading_any_annotation() throws Exception {
        List<String> lines = scan("OrderRequest");
        assertTrue(lines.stream().anyMatch(l -> l.contains("OrderRequest#reference.")
            && l.contains("\"nullable\":true") && l.contains("\"nullable_resolution\":\"partial\"")));
        assertTrue(lines.stream().anyMatch(l -> l.contains("OrderRequest#total.")
            && l.contains("\"nullable\":false") && l.contains("\"nullable_resolution\":\"resolved\"")));
    }

    /** D1 assigns collections to the extractor's own projection, but a known
     *  wire form like BigDecimal's is catalog knowledge (D2) — expanding it
     *  structurally would surface intVal/scale/intCompact/precision, none of
     *  which is on the wire. Mapping it to "object" here, rather than
     *  guessing "number", is what leaves Task 8's known_types entry
     *  something to override. */
    @Test
    void projects_a_collection_field_to_array_and_leaves_a_known_type_field_open() throws Exception {
        List<String> lines = scan("OrderRequest");
        assertTrue(lines.stream().anyMatch(l -> l.contains("OrderRequest#alternates.")
            && l.contains("\"wire_type\":\"array\"")));
        assertTrue(lines.stream().anyMatch(l -> l.contains("OrderRequest#totalAmount.")
            && l.contains("\"wire_type\":\"object\"")));
    }
}
