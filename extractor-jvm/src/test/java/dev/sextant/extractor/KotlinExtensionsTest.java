package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** `kotlin-extension-functions`: an extension function's receiver is marked as one.
 *
 * <p>Measured on kotlinc 2.2.0's output for `fun String.shout(): String`: the top-level
 * extension lives in the file facade `KotlinExtensionsSampleKt` (`@kotlin.Metadata`
 * `k=2`) as `public static final String shout(String)` — the receiver is descriptor slot
 * 0, named only in the `LocalVariableTable` (`$this$shout`), with no `MethodParameters`
 * attribute. A member extension `fun List<Int>.total()` is an instance method
 * `total(List)` with the receiver at slot 0 the same way. Metadata lists both with NO
 * value parameters and a receiver parameter type, which is the only thing in the class
 * file that says slot 0 was written as a receiver.
 */
class KotlinExtensionsTest {

    @Test
    void anExtensionReceiverIsMarkedNotPublishedAsAParameter() throws Exception {
        var shout = methodFact("KotlinExtensionsSampleKt", "shout");
        assertEquals(true, parameterEntries(shout).get(0).get("receiver"));
        assertEquals("java/lang/String#", parameters(shout).get(0).get("symbol"));
        assertEquals(1, parameters(shout).size());
    }

    @Test
    void aMemberExtensionsReceiverIsSlotZeroToo() throws Exception {
        var total = methodFact("KotlinExtensionsHolder", "total");
        assertEquals(true, parameterEntries(total).get(0).get("receiver"));
        assertEquals("java/util/List#", parameters(total).get(0).get("symbol"));
        assertEquals(1, parameters(total).size());
    }

    @Test
    void theParameterBesideTheReceiverIsNotOneAndReadsItsDeclaredType() throws Exception {
        // `fun String.repeatShout(suffix: String)`: slot 0 the receiver, slot 1 `suffix`.
        // Metadata's value parameters do not list the receiver, so `suffix` is laid
        // against slot 1 — under Java's rule it would read `nullable: true`.
        var repeat = methodFact("KotlinExtensionsSampleKt", "repeatShout");
        assertEquals(true, parameterEntries(repeat).get(0).get("receiver"));
        assertEquals(null, parameterEntries(repeat).get(1).get("receiver"));
        assertEquals("java/lang/String#", parameters(repeat).get(1).get("symbol"));
        assertEquals(false, parameters(repeat).get(1).get("nullable"));
    }

    @Test
    void aDefaultBridgeOfAnExtensionMarksTheReceiverToo() throws Exception {
        // `fun String.decorate(prefix: String = "*")` — the bridge is read under the
        // function's key (`OI-81`), and the function's first own slot is the receiver.
        var bridge = methodFact("KotlinExtensionsSampleKt", "decorate$default");
        assertEquals("decorate", bridge.get("bridge_of"));
        assertEquals(true, parameterEntries(bridge).get(0).get("receiver"));
        assertEquals(false, parameters(bridge).get(1).get("nullable"));   // prefix: String
        assertEquals(4, parameters(bridge).size());   // receiver, prefix, mask, marker
    }

    @Test
    void aSuspendingExtensionKeepsTheReceiverFirstAndDropsTheContinuation() throws Exception {
        // `suspend fun String.fetchShout(): String` is
        // `(Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;`: the
        // receiver first, the `Continuation` last and dropped as `G-63` already drops it.
        var fetch = methodFact("KotlinExtensionsSampleKt", "fetchShout");
        assertEquals(true, parameterEntries(fetch).get(0).get("receiver"));
        assertEquals(1, parameters(fetch).size());
    }

    @Test
    void aFunctionWithNoReceiverCarriesNoKey() throws Exception {
        // Absent means false, as `bridge_of` is absent rather than null: a facade
        // function beside the extensions, and a member beside the member extension.
        var plain = methodFact("KotlinExtensionsSampleKt", "plain");
        assertEquals(null, parameterEntries(plain).get(0).get("receiver"));
        var count = methodFact("KotlinExtensionsHolder", "count");
        assertEquals(null, parameterEntries(count).get(0).get("receiver"));
    }

    // ---- reading the emitted facts -------------------------------------------------

    private Map<String, Object> methodFact(String className, String member) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-extensions");
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

    /** The parameter entries themselves — `name`, `receiver`, `type` — where
     *  {@link #parameters} reads only each entry's type. */
    private static List<Map<String, Object>> parameterEntries(Map<String, Object> methodFact) {
        List<Map<String, Object>> parameters = new ArrayList<>();
        for (Object parameter : list(object(methodFact.get("signature")).get("parameters"))) {
            parameters.add(object(parameter));
        }
        return parameters;
    }

    private static Map<String, Object> returns(Map<String, Object> methodFact) {
        return object(object(methodFact.get("signature")).get("returns"));
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
