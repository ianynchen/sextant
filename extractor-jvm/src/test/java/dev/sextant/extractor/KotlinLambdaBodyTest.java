package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** R2 (spec §3b): a Kotlin lambda compiled as a class carries `lambda_body` on its TYPE
 *  fact — the typed `invoke` for a plain lambda, `invokeSuspend` for a suspend one — and
 *  an ordinary class carries no such key.
 *
 * <p>Measured on kotlinc 2.2.0 under `-Xlambdas=class` (`scripts/probes/cp23_kotlin_call_shapes.md`
 * Q6): `KotlinLambdaSample$plain$1 extends kotlin/jvm/internal/Lambda` with
 * `invoke(Ljava/lang/String;)Ljava/lang/Integer;` (`ACC_PUBLIC, ACC_FINAL`) beside the erased
 * `invoke(Ljava/lang/Object;)Ljava/lang/Object;` (`ACC_BRIDGE, ACC_SYNTHETIC`);
 * `KotlinLambdaSample$suspended$1 extends kotlin/coroutines/jvm/internal/SuspendLambda` with
 * `invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;`, `create`, a typed `invoke(String,
 * Continuation)` and its erased bridge. The value is the body's BARE symbol — the spelling a
 * `lambda` argument's `symbol` carries (`MethodFlow.lambdaSymbol`), no module coordinates —
 * so it joins to the body's own symbol fact by descriptor suffix.
 */
class KotlinLambdaBodyTest {

    private static final String PLAIN = "KotlinLambdaSample$plain$1";
    private static final String SUSPENDED = "KotlinLambdaSample$suspended$1";

    @Test
    void a_plain_lambda_class_names_its_typed_invoke() throws Exception {
        String body = "dev/sextant/extractor/" + PLAIN + "#invoke("
            + ClassScanner.disambiguatorOf("(Ljava/lang/String;)Ljava/lang/Integer;") + ").";
        assertEquals(body, typeFact(PLAIN).get("lambda_body"));
        // The key joins: the body's own symbol fact is this string after the coordinates.
        assertTrue(bodyFact(PLAIN, body).toString().endsWith(" " + body), body);
    }

    @Test
    void a_suspend_lambda_class_names_invokeSuspend() throws Exception {
        String body = "dev/sextant/extractor/" + SUSPENDED + "#invokeSuspend("
            + ClassScanner.disambiguatorOf("(Ljava/lang/Object;)Ljava/lang/Object;") + ").";
        assertEquals(body, typeFact(SUSPENDED).get("lambda_body"));
        assertTrue(bodyFact(SUSPENDED, body).toString().endsWith(" " + body), body);
    }

    @Test
    void an_ordinary_class_carries_no_lambda_body() throws Exception {
        assertFalse(typeFact("KotlinLambdaSample").containsKey("lambda_body"));
    }

    // ---- reading the emitted facts -------------------------------------------------

    /** The TYPE's own symbol fact: the one whose symbol ends at the class name. */
    private Map<String, Object> typeFact(String className) throws Exception {
        return fact(className, l -> l.contains(className + "#\""));
    }

    /** The `symbol` of the method fact `lambdaBody` names, or an assertion failure. Keyed
     *  on the space the coordinates prefix ends with, so the type fact — which now quotes
     *  the same string as its `lambda_body` — is not the line found. */
    private Object bodyFact(String className, String lambdaBody) throws Exception {
        return fact(className, l -> l.contains(" " + lambdaBody + "\"")).get("symbol");
    }

    private Map<String, Object> fact(String className, java.util.function.Predicate<String> match)
            throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-lambda-body");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"") && match.test(l))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no matching symbol fact in " + lines));
            return object(JsonFacts.parse(line));
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }
}
