package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** D00 §5a: a method symbol carries {@code modifiers.static} and
 *  {@code modifiers.synthetic}, and NOT the field pair.
 *
 *  <p>These flags are what a rule enumerating a class's exposed members
 *  (D02's {@code mapping.members}) filters on, so a wrong answer here is
 *  published as an endpoint nobody serves. {@code MethodModifierSample.java}
 *  is compiled by Gradle's own test compilation, exactly like
 *  {@code FieldSample.java}, so every assertion below is about what javac
 *  actually emits. */
class MethodModifierScanTest {

    private List<String> scanSample() throws Exception {
        try (InputStream in = getClass()
                .getResourceAsStream("/dev/sextant/extractor/MethodModifierSample.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-method-modifier-sample");
        }
    }

    /** Lines that are the symbol fact for a method of this sample whose
     *  descriptor-disambiguated name starts with {@code name}. */
    private List<String> methodFacts(List<String> lines, String name) {
        return lines.stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"")
                && line.contains("MethodModifierSample#" + name + "("))
            .toList();
    }

    /** Both keys on every method fact, never only the true one: a consumer
     *  reading an absent key cannot tell "not static" from "this scanner does
     *  not report staticness" — the rule {@code FieldScanTest} already states
     *  for fields, restated for the construct that now also carries them. */
    @Test
    void states_both_modifiers_on_an_ordinary_public_method() throws Exception {
        List<String> plain = methodFacts(scanSample(), "plain");

        assertEquals(1, plain.size());
        assertTrue(plain.get(0).contains("\"static\":false"));
        assertTrue(plain.get(0).contains("\"synthetic\":false"));
        assertTrue(plain.get(0).contains("\"visibility\":\"public\""));
    }

    /** THE TRAP, pinned. {@code ACC_VARARGS} is {@code 0x0080} — the same bit
     *  that means {@code ACC_TRANSIENT} on a field — so emitting the FIELD
     *  modifier pair for methods would report every varargs method as
     *  "declared not serialized", a modifier nobody wrote. This method's real
     *  flags are both false, and {@code transient} must not appear at all. */
    @Test
    void never_reports_a_varargs_method_as_transient() throws Exception {
        List<String> varargs = methodFacts(scanSample(), "varargs");

        assertEquals(1, varargs.size());
        assertFalse(varargs.get(0).contains("transient"),
            "ACC_VARARGS shares a bit with ACC_TRANSIENT: a method fact must not "
                + "carry a `transient` key at all");
        assertTrue(varargs.get(0).contains("\"static\":false"));
        assertTrue(varargs.get(0).contains("\"synthetic\":false"));
    }

    /** Bound to the type rather than to an instance, so not a member of the
     *  exposed object. */
    @Test
    void marks_a_method_bound_to_the_type_rather_than_to_an_instance() throws Exception {
        List<String> helper = methodFacts(scanSample(), "helper");

        assertEquals(1, helper.size());
        assertTrue(helper.get(0).contains("\"static\":true"));
        assertTrue(helper.get(0).contains("\"synthetic\":false"));
    }

    /** Not callable from outside the type. The scanner still emits the fact —
     *  somebody wrote the method — and {@code visibility} is what lets a
     *  member rule leave it alone. */
    @Test
    void reports_a_private_method_as_private() throws Exception {
        List<String> hidden = methodFacts(scanSample(), "hidden");

        assertEquals(1, hidden.size());
        // G-73: this pinned `"other"` — the two-valued reading — until `visibility`
        // gained the other three JVMS 4.1 access levels; a private method reports
        // its own word now rather than the same catch-all a package-private one gets.
        assertTrue(hidden.get(0).contains("\"visibility\":\"private\""));
    }

    /** The bridge {@code MethodModifierBase}'s erasure forces javac to emit:
     *  {@code echo(Object)} beside the real {@code echo(String)}, flagged
     *  {@code ACC_BRIDGE} (and {@code ACC_SYNTHETIC}). Both reach the fact
     *  stream — deliberately, since the inheritance walk's bridge rule has to
     *  see them — so the flag is the ONLY thing telling the compiler's copy
     *  from the declaration a human wrote.
     *
     *  <p>Asserted as a partition of the two {@code echo} facts rather than by
     *  naming a descriptor: which disambiguator each gets is not this test's
     *  business, but that exactly one of them is synthetic is. */
    @Test
    void marks_a_compiler_generated_bridge_as_synthetic() throws Exception {
        List<String> echoes = methodFacts(scanSample(), "echo");

        assertEquals(2, echoes.size(),
            "the generic supertype must force javac to emit a bridge beside the override");
        assertEquals(1, echoes.stream().filter(l -> l.contains("\"synthetic\":true")).count());
        assertEquals(1, echoes.stream().filter(l -> l.contains("\"synthetic\":false")).count());
        // The synthetic one is the erased bridge: its parameter is Object,
        // where the declaration a human wrote takes a String.
        assertTrue(echoes.stream().anyMatch(l -> l.contains("\"synthetic\":true")
            && l.contains("\"symbol\":\"java/lang/Object#\"")));
    }

    /** A constructor carries the pair too — it is emitted through the same
     *  method visitor — which is why a member rule excludes it by
     *  {@code construct_kind} rather than by hoping the modifiers say so. */
    @Test
    void states_the_pair_on_a_constructor_which_construct_kind_is_what_excludes()
            throws Exception {
        List<String> constructors = scanSample().stream()
            .filter(l -> l.contains("\"construct_kind\":\"constructor\"")
                && l.contains("MethodModifierSample#"))
            .toList();

        assertEquals(1, constructors.size());
        assertTrue(constructors.get(0).contains("\"static\":false"));
        assertTrue(constructors.get(0).contains("\"synthetic\":false"));
    }
}
