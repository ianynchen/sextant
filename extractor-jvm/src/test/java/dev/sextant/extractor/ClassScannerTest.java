package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

class ClassScannerTest {

    /** The type reference `TypeCarrier<List<String>>` takes, spelled out once:
     *  every level of the chain is a full reference, the same recursive shape a
     *  field or a parameter carries (D00 §5a). */
    private static final String CARRIER_OF_STRINGS =
        "\"supertype\":{\"arguments\":[{\"arguments\":[{\"arguments\":[],\"nullable\":true,"
        + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\","
        + "\"wire_format\":\"\",\"wire_type\":\"string\"}],\"nullable\":true,"
        + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/util/List#\","
        + "\"wire_format\":\"\",\"wire_type\":\"array\"}],\"nullable\":true,"
        + "\"nullable_resolution\":\"resolved\",\"symbol\":\"dev/sextant/extractor/TypeCarrier#\","
        + "\"wire_format\":\"\",\"wire_type\":\"object\"}";

    private List<String> scanSelf() throws Exception {
        return scan("Sample");
    }

    private List<String> scan(String simpleName) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + simpleName + ".class")) {
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

    /** D00 §5a's PTR carrier. The class file's own descriptor says only
     *  "extends TypeCarrier"; the `Signature` attribute is the only place
     *  `List<String>` is written down, and the subclass declares nothing of its
     *  own that names it. */
    @Test
    void keeps_a_generic_superclass_argument_on_the_class_symbol() throws Exception {
        assertTrue(scan("SupertypeSample").stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"class\"") && line.contains(CARRIER_OF_STRINGS)),
            String.join("\n", scan("SupertypeSample")));
    }

    /** The shape a real `new ParameterizedTypeReference<…>() {}` takes: the
     *  subclass has no name and no members, so the supertype reference is the
     *  only carrier of the payload type. */
    @Test
    void keeps_the_same_argument_when_the_subclass_is_anonymous() throws Exception {
        assertTrue(scan("SupertypeSample$1").stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"class\"") && line.contains(CARRIER_OF_STRINGS)),
            String.join("\n", scan("SupertypeSample$1")));
    }

    /** A class signature exists whenever the class *itself* declares a type
     *  parameter, so a generic class over a plain base has one and its
     *  superclass part names a bare type. D00 §5a: "an ordinary, non-generic
     *  superclass carries no such field" — writing `java/lang/Object#` there
     *  would put a supertype reference on nearly every class in a module and
     *  say nothing with it. */
    @Test
    void writes_no_supertype_when_the_superclass_carries_no_type_argument() throws Exception {
        assertFalse(scan("SupertypeSample$PlainBase").stream().anyMatch(line ->
            line.contains("\"supertype\"")),
            String.join("\n", scan("SupertypeSample$PlainBase")));
    }

    /** Two interfaces, named in the order the source declares them — the class
     *  symbol's own record of what it implements (`implemented_interfaces`,
     *  D00 §5a): a caller with only the supertype chain cannot ask "does this
     *  fulfil that contract" without walking every interface's own hierarchy. */
    @Test
    void lists_implemented_interfaces_in_declaration_order() throws Exception {
        assertTrue(scan("InterfaceSample").stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"class\"")
                && line.contains("\"interfaces\":[\"sextant-jvm maven com.acme/orders 1.0.0 "
                    + "java/lang/AutoCloseable#\",\"sextant-jvm maven com.acme/orders 1.0.0 "
                    + "java/lang/Runnable#\"]")),
            String.join("\n", scan("InterfaceSample")));
    }

    /** A class implementing nothing omits the key entirely — an absent key means
     *  "none", not an empty array every consumer has to special-case identically. */
    @Test
    void omits_interfaces_when_a_class_implements_none() throws Exception {
        assertFalse(scanSelf().stream().anyMatch(line ->
            line.contains("\"construct_kind\":\"class\"") && line.contains("\"interfaces\"")),
            String.join("\n", scanSelf()));
    }
}
