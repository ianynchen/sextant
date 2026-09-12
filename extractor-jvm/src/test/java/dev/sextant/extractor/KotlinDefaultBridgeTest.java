package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** `OI-81`: a `$default` bridge names the function it stands for and takes its declared
 *  types.
 *
 * <p>Measured on kotlinc 2.2.0's output for `fun greet(name: String = "x", loud: Boolean =
 * false): String`: the bridge is `greet$default`, flags `ACC_PUBLIC, ACC_STATIC,
 * ACC_SYNTHETIC`, descriptor
 * `(Ldev/sextant/extractor/KotlinDefaultsSample;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String;`
 * — the receiver, the function's own slots, one `int` mask (one per 32 parameters) and an
 * `Object` marker. It has no `Signature` attribute and no entry in `@kotlin.Metadata`'s
 * function list, so `copy` read `nullable: false` beside a `copy$default` reading `true`:
 * one declared type, two answers.
 */
class KotlinDefaultBridgeTest {

    @Test
    void aDefaultBridgeNamesTheFunctionItStandsFor() throws Exception {
        var bridge = methodFact("KotlinDefaultsSample", "greet$default");
        assertEquals("greet", bridge.get("bridge_of"));
        assertEquals(true, modifiers(bridge).get("synthetic"));
        // OI-81: the bridge's declared types are the FUNCTION's, not Java's rule.
        assertEquals(false, parameters(bridge).get(1).get("nullable"));   // name: String
        assertEquals(false, parameters(bridge).get(2).get("nullable"));   // loud: Boolean
        assertEquals(false, returns(bridge).get("nullable"));
        // The receiver, the mask and the marker are the bridge's own and no function
        // declares them: the receiver keeps Java's rule, the mask is a primitive.
        assertEquals(5, parameters(bridge).size());
        assertEquals(true, parameters(bridge).get(0).get("nullable"));
        assertEquals("int#", parameters(bridge).get(3).get("symbol"));
        assertEquals("java/lang/Object#", parameters(bridge).get(4).get("symbol"));
    }

    @Test
    void theNullableSideIsBorrowedToo() throws Exception {
        // `fun maybe(note: String? = null, tags: List<String?> = emptyList()): String?`.
        // The bridge carries no `Signature`, so `tags` stays the erased `List` — its
        // element is not invented — but the declared nullability at the top level is the
        // function's.
        var bridge = methodFact("KotlinDefaultsSample", "maybe$default");
        assertEquals("maybe", bridge.get("bridge_of"));
        assertEquals(true, parameters(bridge).get(1).get("nullable"));    // note: String?
        assertEquals(false, parameters(bridge).get(2).get("nullable"));   // tags: List<String?>
        assertEquals(List.of(), parameters(bridge).get(2).get("arguments"));
        assertEquals(true, returns(bridge).get("nullable"));
    }

    @Test
    void aSuspendFunctionsBridgeAlignsPastTheContinuation() throws Exception {
        // `suspend fun fetch(id: String = "0"): String` — the bridge's descriptor is
        // `(Owner;Ljava/lang/String;Lkotlin/coroutines/Continuation;ILjava/lang/Object;)Ljava/lang/Object;`,
        // the `Continuation` BEFORE the mask and marker, and the sibling is keyed with it.
        // `id` reads the declared type; the `Continuation` is nobody's declaration.
        var bridge = methodFact("KotlinDefaultsSample", "fetch$default");
        assertEquals("fetch", bridge.get("bridge_of"));
        assertEquals(false, parameters(bridge).get(1).get("nullable"));   // id: String
        assertEquals(true, parameters(bridge).get(2).get("nullable"));    // Continuation
        assertEquals(5, parameters(bridge).size());   // receiver, id, Continuation, mask, marker
    }

    @Test
    void twoCandidateSiblingsIsNoSibling() throws Exception {
        // `object KotlinDefaultsObject { @JvmStatic fun js(a: String, b: Int = 0): String;
        // fun js(b: Int): String }`. The bridge is `js$default(Ljava/lang/String;IILjava/lang/Object;)`
        // with no receiver; read WITH one it derives `js(I)Ljava/lang/String;`, which the
        // arity overload keys, and the bridge would publish that overload's declared
        // return (`nullable: false`) as its own. Both candidates key, so neither is taken:
        // `bridge_of` is certain from the shape, and every slot and the return keep Java's
        // rule — the projection a bridge with no sibling in metadata already has.
        var bridge = methodFact("KotlinDefaultsObject", "js$default");
        assertEquals("js", bridge.get("bridge_of"));
        assertEquals(4, parameters(bridge).size());
        assertEquals(true, parameters(bridge).get(0).get("nullable"));    // a: String
        assertEquals(false, parameters(bridge).get(1).get("nullable"));   // b: Int (primitive)
        assertEquals(true, returns(bridge).get("nullable"));              // Java's rule, not the overload's
        assertEquals(null, bridge.get("ext"));
    }

    @Test
    void theFunctionItselfIsUntouched() throws Exception {
        var greet = methodFact("KotlinDefaultsSample", "greet");
        assertEquals(null, greet.get("bridge_of"));
        assertEquals(false, modifiers(greet).get("synthetic"));
        assertEquals(2, parameters(greet).size());
        assertEquals(false, parameters(greet).get(0).get("nullable"));
    }

    // ---- reading the emitted facts -------------------------------------------------

    private Map<String, Object> methodFact(String className, String member) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-defaults");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"")
                    && l.contains(className + "#" + member + "("))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + member));
            return object(JsonFacts.parse(line));
        }
    }

    private static Map<String, Object> modifiers(Map<String, Object> methodFact) {
        return object(methodFact.get("modifiers"));
    }

    private static List<Map<String, Object>> parameters(Map<String, Object> methodFact) {
        List<Map<String, Object>> parameters = new ArrayList<>();
        for (Object parameter : list(object(methodFact.get("signature")).get("parameters"))) {
            parameters.add(object(object(parameter).get("type")));
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
}
