package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** `OI-80`: a suspending function's primitive return read as the primitive.
 *
 * <p>A suspend function's declared return is recovered from the trailing
 * {@code Continuation}'s type argument (`G-63`), and a type argument cannot be a primitive
 * — the class file genuinely says {@code Ljava/lang/Integer;} there. So
 * {@code suspend fun suspCount(): Int} published {@code java/lang/Integer#} where
 * {@code fun plainCount(): Int} publishes {@code int#}: two spellings of one declared type,
 * seen by every consumer that compares symbols across declarations. Only
 * {@code @kotlin.Metadata}'s classifier says {@code kotlin/Int} was written, and only its
 * nullability says whether that boxes — {@code Int?} genuinely does.
 */
class KotlinSuspendPrimitiveTest {

    @Test
    void aSuspendingPrimitiveReturnReadsAsThePrimitive() throws Exception {
        assertEquals("int#",     returnSymbol("KotlinSuspendSample", "suspCount"));
        assertEquals("boolean#", returnSymbol("KotlinSuspendSample", "suspFlag"));
        assertEquals("long#",    returnSymbol("KotlinSuspendSample", "suspTotal"));
        assertEquals("int#",     returnSymbol("KotlinSuspendSample", "plainCount")); // unchanged
    }

    @Test
    void aNullablePrimitiveGenuinelyBoxesAndStaysBoxed() throws Exception {
        String returns = returns("KotlinSuspendSample", "suspMaybeCount");
        assertEquals("java/lang/Integer#", symbolOf(returns));
        assertEquals(true, returns.contains("\"nullable\":true"),
            "a declared `Int?` return stopped reading nullable: " + returns);
    }

    @Test
    void theRecoveredPrimitiveCarriesAPrimitivesWholeReference() throws Exception {
        // The whole reference, not only the symbol: a primitive forbids null and its wire
        // projection is the descriptor's, exactly as `plainCount` has always read.
        assertEquals(returns("KotlinSuspendSample", "plainCount"),
                     returns("KotlinSuspendSample", "suspCount"));
    }

    // ---- reading the emitted facts -------------------------------------------------

    private String returnSymbol(String className, String member) throws Exception {
        return symbolOf(returns(className, member));
    }

    private static String symbolOf(String returns) {
        String key = "\"symbol\":\"";
        int at = returns.indexOf(key) + key.length();
        return returns.substring(at, returns.indexOf('"', at));
    }

    /** The method fact's {@code signature.returns} object, as emitted. */
    private String returns(String className, String member) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-suspend-primitive");
            String line = lines.stream()
                .filter(l -> l.contains("\"kind\":\"symbol\"")
                    && l.contains(className + "#" + member + "("))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no symbol fact for " + member));
            String key = "\"returns\":";
            int start = line.indexOf(key) + key.length();
            int depth = 0;
            for (int i = start; i < line.length(); i++) {
                char c = line.charAt(i);
                if (c == '{') depth++;
                if (c == '}' && --depth == 0) return line.substring(start, i + 1);
            }
            throw new AssertionError("unterminated returns object in " + line);
        }
    }
}
