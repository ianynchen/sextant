package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** `kotlin-defaultimpls`: the nested `DefaultImpls` class kotlinc emits for an interface
 *  with a default method body is attributed to that interface, and each of its static
 *  bodies to the interface method it stands for.
 *
 * <p>Measured on kotlinc 2.2.0's output for `interface Pricer { fun price(): Int = 0 }`
 * (no `-jvm-default` flag, so the compiler's own `enable` mode): `Pricer$DefaultImpls`
 * is `public final` — NOT `synthetic` — with `@kotlin.Metadata k=3`, no fields, no
 * constructor, and every method `public static` with the interface at descriptor slot
 * 0: `price(Ldev/sextant/extractor/KotlinDefaultImplsSample$Pricer;)I`. Its
 * `InnerClasses` entry names the interface as the outer class. In this mode the
 * interface ALSO carries `price()` as a JVM default method and the `DefaultImpls`
 * body is a `@Deprecated` stub that delegates back to it; under `-jvm-default=disable`
 * (kotlinc 2.4.10, measured) the class file shape is identical, the interface method
 * is abstract and the body is in `DefaultImpls`. The recogniser reads the shape,
 * which both modes share.
 */
class KotlinDefaultImplsTest {

    private static final String HOLDER = "KotlinDefaultImplsSample$Pricer$DefaultImpls";
    private static final String PRICER =
        "sextant-jvm maven com.acme/orders 1.0.0 dev/sextant/extractor/KotlinDefaultImplsSample$Pricer#";

    @Test
    void defaultImplsIsAttributedToItsInterface() throws Exception {
        var holder = classFact(HOLDER);
        assertEquals(PRICER, holder.get("implements_default_of"));
        assertEquals("price", methodFact(HOLDER, "price").get("bridge_of"));
    }

    @Test
    void aBodyWithParametersStandsForTheInterfaceMethodAndKeepsTheInterfaceSlot() throws Exception {
        // `discount(Pricer, int, int)`: slot 0 is the interface instance, kept — a call
        // site names the body by its full descriptor — and the two after it are the
        // method's own.
        var discount = methodFact(HOLDER, "discount");
        assertEquals("discount", discount.get("bridge_of"));
        assertEquals(3, parameters(discount).size());
        assertEquals(
            "dev/sextant/extractor/KotlinDefaultImplsSample$Pricer#",
            parameters(discount).get(0).get("symbol"));
    }

    @Test
    void theDefaultBridgeInsideDefaultImplsStandsForTheFunctionNotForItself() throws Exception {
        // `discount$default(Pricer, int, int, int, Object)` is `OI-81`'s bridge with the
        // interface at slot 0; it stands for `discount`, not for `discount$default`.
        var bridge = methodFact(HOLDER, "discount$default");
        assertEquals("discount", bridge.get("bridge_of"));
        assertEquals(true, modifiers(bridge).get("synthetic"));
    }

    @Test
    void theInterfaceAndItsImplementationCarryNeitherKey() throws Exception {
        // The interface is what the holder stands for, not a holder; the implementing
        // class is nested in the same file and is an ordinary class.
        assertEquals(null, classFact("KotlinDefaultImplsSample$Pricer").get("implements_default_of"));
        assertEquals(null, classFact("KotlinDefaultImplsSample$FlatPricer").get("implements_default_of"));
        assertEquals(null, methodFact("KotlinDefaultImplsSample$FlatPricer", "price").get("bridge_of"));
    }

    // ---- reading the emitted facts -------------------------------------------------

    private Map<String, Object> classFact(String className) throws Exception {
        return fact(className, "#\"");
    }

    private Map<String, Object> methodFact(String className, String member) throws Exception {
        return fact(className, "#" + member + "(");
    }

    private Map<String, Object> fact(String className, String memberSuffix) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-defaultimpls");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"")
                    && l.contains("\"symbol\":\"sextant-jvm maven com.acme/orders 1.0.0 dev/sextant/extractor/"
                        + className + memberSuffix))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + className + memberSuffix));
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

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> list(Object value) {
        return (List<Object>) value;
    }
}
