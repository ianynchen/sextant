package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** `OI-82`, the PARAMETER half of `G-63`.
 *
 * <p>A Kotlin parameter's nullability is in its type, and kotlinc erases it: `sku: String`
 * and `note: String?` reach the descriptor as one `Ljava/lang/String;`, and
 * `List&lt;String?&gt;` and `List&lt;String&gt;?` reach the `Signature` attribute as one
 * `Ljava/util/List&lt;Ljava/lang/String;&gt;;`. Java's rule — every reference permits null —
 * then read every one of them as `nullable: true`. Only `@kotlin.Metadata` states what
 * was declared, and it states it at every level of the type, so the assertions here reach
 * into the type arguments too.
 */
class KotlinParameterNullabilityTest {

    @Test
    void parametersCarryTheDeclaredNullability() throws Exception {
        var method = methodFact("KotlinParameterSample", "place");
        List<Map<String, Object>> params = parameters(method);
        assertEquals(false, params.get(0).get("nullable"));                 // sku: String
        assertEquals(true,  params.get(1).get("nullable"));                 // qty: Int?
        assertEquals(false, params.get(2).get("nullable"));                 // tags: List<String?>
        assertEquals(true,  argument(params.get(2), 0).get("nullable"));    // …String?
        assertEquals(true,  params.get(3).get("nullable"));                 // meta: Map<…>?
        assertEquals(false, argument(params.get(3), 0).get("nullable"));    // String
        assertEquals(true,  argument(params.get(3), 1).get("nullable"));    // List<Int>?
        assertEquals(false, argument(argument(params.get(3), 1), 0).get("nullable")); // Int
    }

    @Test
    void constructorParametersToo() throws Exception {
        var ctor = methodFact("KotlinParameterSample", "<init>");
        assertEquals(false, parameters(ctor).get(0).get("nullable"));
        assertEquals(true,  parameters(ctor).get(1).get("nullable"));
    }

    @Test
    void aDefaultedParameterIsTheOrdinaryCase() throws Exception {
        // `copy(id: String = this.id, note: String? = this.note)`: the defaults live in a
        // separate `copy$default` bridge; the function itself is declared like any other.
        var copy = methodFact("KotlinParameterSample", "copy");
        assertEquals(false, parameters(copy).get(0).get("nullable"));
        assertEquals(true,  parameters(copy).get(1).get("nullable"));
    }

    // ---- reading the emitted facts -------------------------------------------------

    private Map<String, Object> methodFact(String className, String member) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-parameters");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"")
                    && l.contains(className + "#" + member + "("))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + member));
            return object(new Json(line).value());
        }
    }

    private static List<Map<String, Object>> parameters(Map<String, Object> methodFact) {
        List<Map<String, Object>> parameters = new ArrayList<>();
        for (Object parameter : list(object(methodFact.get("signature")).get("parameters"))) {
            parameters.add(object(object(parameter).get("type")));
        }
        return parameters;
    }

    private static Map<String, Object> argument(Map<String, Object> typeRef, int index) {
        return object(list(typeRef.get("arguments")).get(index));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> list(Object value) {
        return (List<Object>) value;
    }

    /** Enough JSON to read one fact line back: the extractor's own {@code JsonOut} writes
     *  objects, arrays, strings, numbers, booleans and null, and nothing else. */
    private static final class Json {
        private final String text;
        private int at;

        Json(String text) {
            this.text = text;
        }

        Object value() {
            char c = text.charAt(at);
            if (c == '{') return objectValue();
            if (c == '[') return arrayValue();
            if (c == '"') return string();
            if (text.startsWith("true", at)) { at += 4; return true; }
            if (text.startsWith("false", at)) { at += 5; return false; }
            if (text.startsWith("null", at)) { at += 4; return null; }
            int start = at;
            while (at < text.length() && "-+.eE0123456789".indexOf(text.charAt(at)) >= 0) at++;
            return Double.parseDouble(text.substring(start, at));
        }

        private Map<String, Object> objectValue() {
            Map<String, Object> fields = new LinkedHashMap<>();
            at++; // {
            while (text.charAt(at) != '}') {
                String key = string();
                at++; // :
                fields.put(key, value());
                if (text.charAt(at) == ',') at++;
            }
            at++; // }
            return fields;
        }

        private List<Object> arrayValue() {
            List<Object> items = new ArrayList<>();
            at++; // [
            while (text.charAt(at) != ']') {
                items.add(value());
                if (text.charAt(at) == ',') at++;
            }
            at++; // ]
            return items;
        }

        private String string() {
            StringBuilder out = new StringBuilder();
            at++; // opening quote
            while (text.charAt(at) != '"') {
                char c = text.charAt(at++);
                if (c != '\\') {
                    out.append(c);
                    continue;
                }
                char escaped = text.charAt(at++);
                switch (escaped) {
                    case 'n' -> out.append('\n');
                    case 't' -> out.append('\t');
                    case 'r' -> out.append('\r');
                    case 'b' -> out.append('\b');
                    case 'f' -> out.append('\f');
                    case 'u' -> {
                        out.append((char) Integer.parseInt(text.substring(at, at + 4), 16));
                        at += 4;
                    }
                    default -> out.append(escaped); // \" \\ \/
                }
            }
            at++; // closing quote
            return out.toString();
        }
    }
}
