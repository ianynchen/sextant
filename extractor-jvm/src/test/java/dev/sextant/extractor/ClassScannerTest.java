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

    /** A signature-level type reference carries D1's wire projection and D3's
     *  nullability at every level, exactly as a field's does. Two grammars for
     *  the same idea would make every consumer ask which of the two it is
     *  holding before it could read `wire_type` — and a shape rooted from a
     *  return type could not say whether what it rooted at is a payload. */
    @Test
    void projects_a_methods_return_type_and_parameters_like_a_fields() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("Sample#greet(sig_")
                && line.contains("\"returns\":{\"arguments\":[],\"nullable\":true,"
                    + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\","
                    + "\"wire_format\":\"\",\"wire_type\":\"string\"}")
                && line.contains("\"type\":{\"arguments\":[],\"nullable\":false,"
                    + "\"nullable_resolution\":\"resolved\",\"symbol\":\"int#\","
                    + "\"wire_format\":\"int32\",\"wire_type\":\"integer\"}")));
    }

    /** The Signature-attribute path for a method: `List<String>` keeps
     *  `String`, the same claim D00 §5a already makes for a field. */
    @Test
    void keeps_a_generic_return_types_argument_as_a_full_type_reference() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("Sample#greetAll(sig_")
                && line.contains("\"returns\":{\"arguments\":[{\"arguments\":[],"
                    + "\"nullable\":true,\"nullable_resolution\":\"resolved\","
                    + "\"symbol\":\"java/lang/String#\",\"wire_format\":\"\","
                    + "\"wire_type\":\"string\"}],\"nullable\":true,"
                    + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/util/List#\","
                    + "\"wire_format\":\"\",\"wire_type\":\"array\"}")));
    }

    /** A method that returns nothing must not be described as returning an
     *  object: that is a shape claim, and it is the difference between "this
     *  endpoint answers with a payload we could not expand" and "this endpoint
     *  answers with no payload at all". */
    @Test
    void gives_a_void_return_no_wire_type() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("Sample#reset(sig_")
                && line.contains("\"symbol\":\"void#\"")
                && line.contains("\"wire_type\":\"\"")));
    }
}
