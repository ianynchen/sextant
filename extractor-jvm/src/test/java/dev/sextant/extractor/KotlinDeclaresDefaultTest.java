package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** R1 (spec §3c): `@kotlin.Metadata`'s `declaresDefaultValue` flag reaches the parameter
 *  fact as `declares_default: true`, absent otherwise — the same alignment nullability
 *  (`OI-82`) reads, so a parameter this projection would get wrong is one nullability
 *  already declines to touch.
 */
class KotlinDeclaresDefaultTest {

    @Test
    void aDefaultedParameterCarriesTheFlagAndItsNeighboursDoNot() throws Exception {
        // `fun list(page: Int = 0, size: Int, tag: String?): String`.
        var list = methodFact(
            "KotlinDefaultParams", "list", "(IILjava/lang/String;)Ljava/lang/String;");
        var parameters = parameterEntries(list);
        assertEquals(3, parameters.size());
        assertEquals(true, parameters.get(0).get("declares_default"));   // page: Int = 0
        assertEquals(null, parameters.get(1).get("declares_default"));  // size: Int
        assertEquals(null, parameters.get(2).get("declares_default"));  // tag: String?
    }

    @Test
    void aMisalignedDeclarationCarriesNoFlagOnAnySlot() throws Exception {
        // `inner class Page(val size: Int = 20)`: kotlinc's constructor descriptor is
        // `(LKotlinDefaultParams;I)V` — the enclosing instance first, then `size` — and
        // metadata's value parameters list `size` alone, so `parametersAligned` is false
        // and the flag rides NO slot: a partial alignment would put `size`'s default on
        // the enclosing-instance slot, which is worse than not reading it. The same
        // condition nullability declines under (`OI-82`); both slots keep the JVM's rule.
        // The descriptor selects the constructor the author wrote; kotlinc also emits a
        // synthetic `<init>(KotlinDefaultParams, int, int, DefaultConstructorMarker)` for
        // the defaulted call, and a name-prefix match could pick either.
        var ctor = methodFact("KotlinDefaultParams$Page", "<init>",
            "(Ldev/sextant/extractor/KotlinDefaultParams;I)V");
        var parameters = parameterEntries(ctor);
        assertEquals(2, parameters.size());
        assertEquals(null, parameters.get(0).get("declares_default"));  // this$0
        assertEquals(null, parameters.get(1).get("declares_default"));  // size: Int = 20
    }

    // ---- reading the emitted facts -------------------------------------------------

    /** The symbol fact of ONE method: name and full descriptor, the descriptor hashed the
     *  way `ClassScanner` names the symbol (`sig_…`), so an overload or a compiler-added
     *  sibling sharing the name cannot be picked by emission order. */
    private Map<String, Object> methodFact(String className, String member, String descriptor)
            throws Exception {
        String symbol =
            className + "#" + member + "(" + ClassScanner.disambiguatorOf(descriptor) + ")";
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-declares-default");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"") && l.contains(symbol))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + symbol));
            return object(JsonFacts.parse(line));
        }
    }

    private static List<Map<String, Object>> parameterEntries(Map<String, Object> methodFact) {
        List<Map<String, Object>> parameters = new ArrayList<>();
        for (Object parameter : list(object(methodFact.get("signature")).get("parameters"))) {
            parameters.add(object(parameter));
        }
        return parameters;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> list(Object value) {
        return (List<Object>) value;
    }
}
