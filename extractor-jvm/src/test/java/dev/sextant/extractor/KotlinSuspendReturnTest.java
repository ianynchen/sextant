package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Q2's `suspend fun` obligation and `G-63`'s RETURN half, which are one read.
 *
 * <p>kotlinc erases a suspending function's declared return to {@code Object} and appends
 * a {@code Continuation} parameter the author never wrote. Both were published as facts:
 * a parameter absent from the source, and a return type absent from the language.
 *
 * <p>The fixture is built so that no weaker source could pass these tests.
 * {@code fetch(String): KotlinSample} and {@code maybe(String): KotlinSample?} compile to
 * ONE descriptor and therefore one signature hash, and kotlinc stamps {@code @Nullable} on
 * both — so neither the descriptor, nor the signature hash, nor an annotation separates
 * them. Only {@code @kotlin.Metadata} does.
 */
class KotlinSuspendReturnTest {

    private String symbol(String className, String member) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-suspend");
            return lines.stream()
                .filter(line -> line.contains("\"kind\":\"symbol\"")
                    && line.contains(className + "#" + member))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + member));
        }
    }

    @Test
    void a_suspend_function_publishes_the_return_type_its_author_declared() throws Exception {
        assertTrue(
            symbol("KotlinSuspendSample", "fetch").contains(
                "\"returns\":{\"arguments\":[],\"nullable\":false,"
                    + "\"nullable_resolution\":\"resolved\","
                    + "\"symbol\":\"dev/sextant/extractor/KotlinSample#\""),
            "a suspend fun's declared return was not recovered, or its nullability was not");
    }

    @Test
    void the_two_suspend_functions_one_descriptor_cannot_separate_are_separated() throws Exception {
        String fetch = symbol("KotlinSuspendSample", "fetch");
        String maybe = symbol("KotlinSuspendSample", "maybe");
        // The premise, asserted rather than assumed: if these ever stop sharing a
        // signature hash the test below proves something weaker than it claims.
        assertTrue(fetch.contains("sig_3a5b604f") && maybe.contains("sig_3a5b604f"),
            "the two no longer share one descriptor, so this test's premise is gone");
        assertTrue(fetch.contains("\"nullable\":false"), "a non-null declared return reads nullable");
        assertTrue(maybe.contains("\"nullable\":true,\"nullable_resolution\":\"resolved\","
                + "\"symbol\":\"dev/sextant/extractor/KotlinSample#\""),
            "a nullable declared return reads non-null");
    }

    @Test
    void the_compilers_trailing_continuation_is_not_published_as_a_parameter() throws Exception {
        String fetch = symbol("KotlinSuspendSample", "fetch");
        assertFalse(fetch.contains("$completion"),
            "the parameter kotlinc appends is still published as one the author wrote");
        assertFalse(fetch.contains("kotlin/coroutines/Continuation#"),
            "the Continuation survives somewhere in the signature");
        // Exactly one parameter, and it is the declared one. Counting the occurrences of
        // the key rather than parsing: a second parameter object writes a second `name`.
        assertEquals(1, fetch.split("\"erased_symbol\"", -1).length - 1,
            "a suspend fun published other than exactly its declared parameters");
        assertTrue(fetch.contains("\"name\":\"id\""), "the declared parameter was dropped too");
    }

    @Test
    void an_ordinary_kotlin_function_gets_the_same_treatment() throws Exception {
        // `G-63`: this is the case that has nothing to do with coroutines. Before the
        // metadata read, `plain(String): KotlinSample` published `nullable: true,
        // nullable_resolution: "resolved"` — a certainty marker on a value the same fact
        // contradicts, since kotlinc writes `@NotNull` on the method beside it.
        assertTrue(
            symbol("KotlinSuspendSample", "plain").contains(
                "\"returns\":{\"arguments\":[],\"nullable\":false"),
            "an ordinary Kotlin function's declared non-null return still reads nullable");
    }

    @Test
    void a_java_method_that_merely_takes_a_continuation_is_left_alone() throws Exception {
        // `G-63` review, CRITICAL. Deciding "is this suspending" from the SHAPE of the
        // last parameter fires on every one of these. Measured across
        // `kotlinx-coroutines-core-jvm` 1.8.0 + `kotlin-stdlib` 2.2.0: 683 of 14,895
        // methods match structurally and 228 are not suspend functions at all.
        String await = symbol("ContinuationImposters", "await");
        assertEquals(2, await.split("\"erased_symbol\"", -1).length - 1,
            "a Java method lost a declared parameter to the suspend rule");
        assertTrue(await.contains("\"returns\":{\"arguments\":[],\"nullable\":false,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"int#\""),
            "a Java method's own return type was replaced by the suspend rule");

        String collect = symbol("ContinuationImposters", "collect");
        assertEquals(1, collect.split("\"erased_symbol\"", -1).length - 1,
            "a Java method's only parameter was dropped");
        assertTrue(collect.contains("\"symbol\":\"java/util/List#\""),
            "a Java method's List return was replaced");
    }

    @Test
    void an_inner_classes_constructor_keeps_the_parameter_its_author_wrote() throws Exception {
        // `G-63` review, MAJOR. The recovery reads a SIGNATURE position while the drop
        // removes a DESCRIPTOR slot, and an inner class is where they differ: the
        // enclosing instance is in the descriptor and absent from the signature. Trusting
        // the signature alone deleted the DECLARED parameter and kept the synthetic —
        // the inversion W5's alignment exists to prevent — and turned a constructor's
        // `void#` into a class.
        String constructor = symbol("ContinuationImposters$Inner", "<init>");
        assertEquals(2, constructor.split("\"erased_symbol\"", -1).length - 1,
            "an inner class constructor lost a parameter");
        assertTrue(constructor.contains("\"symbol\":\"kotlin/coroutines/Continuation#\""),
            "the DECLARED Continuation parameter was dropped and the synthetic kept");
        assertTrue(constructor.contains("\"returns\":{\"arguments\":[],\"nullable\":false,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"void#\""),
            "a constructor stopped returning void");
    }

    @Test
    void a_kotlin_function_that_is_not_suspend_is_left_alone() throws Exception {
        // Metadata says these are not suspend; nothing structural can. `arrayParam` is
        // the second half: ASM's `visitArrayType` returns `this` by default, so for
        // `Array<Continuation<String>>` the ELEMENT's class name reaches the owner check.
        String resume = symbol("KotlinContinuationImposters", "resumeIt");
        assertEquals(1, resume.split("\"erased_symbol\"", -1).length - 1,
            "a non-suspend Kotlin fun lost its parameter");
        assertTrue(resume.contains("\"symbol\":\"int#\""), "its Int return was replaced");

        String array = symbol("KotlinContinuationImposters", "arrayParam");
        assertEquals(1, array.split("\"erased_symbol\"", -1).length - 1,
            "an Array<Continuation<T>> parameter was read as a trailing Continuation");
        assertTrue(array.contains("\"symbol\":\"int#\""), "its Int return was replaced");
    }

    @Test
    void a_property_getter_stops_contradicting_the_field_beside_it() throws Exception {
        // The field `KotlinSample#note.` has read `nullable: true` since M03 and the
        // field `#id.` `false`; their GETTERS both read `true`, because a getter is a
        // method and took Java's rule. One declared type, two facts, one of them wrong.
        assertTrue(symbol("KotlinSample", "getId").contains("\"returns\":{\"arguments\":[],\"nullable\":false"),
            "a non-null property's getter still returns nullable");
        assertTrue(symbol("KotlinSample", "getNote").contains("\"returns\":{\"arguments\":[],\"nullable\":true"),
            "a nullable property's getter stopped reporting nullable");
    }
}
