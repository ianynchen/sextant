package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * W4: three JVMS 4.7 attributes that each stood in for an invented rule.
 *
 * <p>`ConstantValue` (4.7.2) gives D00 §5's `constant` its first producer.
 * `InnerClasses` (4.7.6) and `EnclosingMethod` (4.7.7) give a nested class the
 * enclosing symbol it reported as null. Both were sitting in the class file,
 * and one of them — `ConstantValue` — was already being handed to us by ASM as
 * a parameter we ignored.
 */
class ClassFileAttributesTest {

    private List<String> scan(String simpleName) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + simpleName + ".class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-" + simpleName);
        }
    }

    @Test
    void a_static_final_field_yields_a_constant_fact_carrying_its_value() throws Exception {
        // The shape the fact exists for: `static final String TOPIC = "orders"`
        // is how a great many real listeners name their destination, and
        // without this the address resolves to an unresolved reference.
        assertTrue(
            scan("ConstantHolder").stream().anyMatch(line ->
                line.contains("\"kind\":\"constant\"")
                    && line.contains("TOPIC")
                    && line.contains("\"value\":\"orders\"")),
            "no constant fact carried the String's value");
    }

    @Test
    void a_numeric_constant_keeps_its_own_json_type() throws Exception {
        // Not stringified: a consumer reading a port needs the number, and
        // re-parsing text would put a guess between it and the class file.
        assertTrue(
            scan("ConstantHolder").stream().anyMatch(line ->
                line.contains("CONCURRENCY") && line.contains("\"value\":3")),
            "the int constant was not recorded as a JSON number");
    }

    @Test
    void a_field_with_no_constant_value_attribute_produces_no_constant_fact() throws Exception {
        // A field initialised in `<clinit>` carries no `ConstantValue`. What a
        // static initialiser computes is a different question, and answering it
        // from this attribute would be a guess.
        assertTrue(
            scan("ConstantHolder").stream().noneMatch(line ->
                line.contains("\"kind\":\"constant\"") && line.contains("COMPUTED")),
            "a computed field must not be reported as a compile-time constant");
    }

    @Test
    void a_member_class_reports_its_outer_type_as_enclosing() throws Exception {
        assertTrue(
            scan("ConstantHolder$Nested").stream().anyMatch(line ->
                line.contains("\"construct_kind\":\"class\"")
                    && line.contains("\"enclosing\":\"sextant-jvm maven com.acme/orders 1.0.0 "
                                     + "dev/sextant/extractor/ConstantHolder#\"")),
            "a nested class still reports no enclosing symbol");
    }

    @Test
    void an_anonymous_class_reports_the_METHOD_that_encloses_it() throws Exception {
        // The half `$`-splitting can never recover: the binary name yields the
        // outer TYPE at best, and `EnclosingMethod` names the method.
        assertTrue(
            scan("ConstantHolder$1").stream().anyMatch(line ->
                line.contains("\"construct_kind\":\"class\"")
                    && line.contains("ConstantHolder#make(")),
            "an anonymous class did not name its enclosing method");
    }

    @Test
    void a_classs_own_symbol_still_precedes_its_members() throws Exception {
        // W4 MOVED this emit. `InnerClasses` and `EnclosingMethod` arrive after
        // ASM's `visit`, so the class symbol is now built at `visitEnd` and put
        // back at the front — and nothing pinned that order before, though
        // `symbols.seq` IS this order and every content hash moves with it
        // (NFR-1). Found by review: the ordering was depended on and untested.
        List<String> lines = scan("ConstantHolder");
        assertTrue(lines.get(0).contains("\"construct_kind\":\"class\""),
            "a class's own symbol must be the first fact in its file, not the last: " + lines.get(0));
    }

    @Test
    void an_annotation_element_carries_the_default_the_class_file_states() throws Exception {
        // Catalogs hardcode these today — a claim about what a framework does at
        // a version nobody measured, which is the prediction GUIDELINES §8.1
        // forbids. The jar states it.
        List<String> lines = scan("Defaulted");
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("value(") && line.contains("\"annotation_default\":\"orders\"")));
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("concurrency(") && line.contains("\"annotation_default\":3")));
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("topics(") && line.contains("\"annotation_default\":[\"a\",\"b\"]")));
    }
}
