package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

class ClassScannerTest {

    private List<String> scanSelf() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/dev/sextant/extractor/Sample.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0").scan(in.readAllBytes(), "doc-sample");
        }
    }

    @Test
    void emits_a_class_symbol_when_a_class_is_scanned() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"class\"") && line.contains("Sample#")));
    }

    @Test
    void emits_a_method_symbol_with_its_return_type_when_a_method_is_scanned() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("Sample#greet(sig_") && line.contains("java/lang/String#")));
    }
}
