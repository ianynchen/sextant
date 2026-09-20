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
        var list = methodFact("KotlinDefaultParams", "list");
        var parameters = parameterEntries(list);
        assertEquals(3, parameters.size());
        assertEquals(true, parameters.get(0).get("declares_default"));   // page: Int = 0
        assertEquals(null, parameters.get(1).get("declares_default"));  // size: Int
        assertEquals(null, parameters.get(2).get("declares_default"));  // tag: String?
    }

    // ---- reading the emitted facts -------------------------------------------------

    private Map<String, Object> methodFact(String className, String member) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-declares-default");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"")
                    && l.contains(className + "#" + member + "("))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + member));
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
