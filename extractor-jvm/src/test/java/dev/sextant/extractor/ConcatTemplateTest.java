package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * W4: an address the code ASSEMBLES rather than states.
 *
 * <p>`"/api/" + version + "/orders"` is not built in the bytecode. javac emits
 * one `invokedynamic` plus a RECIPE — the literal text with a marker where each
 * runtime value goes — and those literals were being thrown away, so the call
 * reached a catalog as `unresolved`: an outbound call naming nothing at all.
 *
 * <p>The hole stays UNNAMED on purpose. A path variable's name was never part
 * of the address — a server routes `/api/owners/42` to `/api/owners/{ownerId}`
 * by position, and could rename the variable without changing the wire — so
 * `{}` is what both sides share, and naming it would invent a name the class
 * file often does not carry.
 */
class ConcatTemplateTest {

    private List<String> scan() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/ConcatAddresses.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0").scan(in.readAllBytes(), "doc");
        }
    }

    @Test
    void a_joined_address_is_recorded_as_a_template_with_a_hole() throws Exception {
        assertTrue(
            scan().stream().anyMatch(line ->
                line.contains("\"kind\":\"concat\"")
                    && line.contains("\"value\":\"/api/{}/orders\"")),
            "the literal parts of a joined address were not recorded");
    }

    @Test
    void a_constant_folded_by_javac_is_a_plain_string_not_a_concat() throws Exception {
        // `"/api/" + "v2"` never reaches StringConcatFactory: javac folds it,
        // so it must arrive as an ordinary string literal. A `concat` here
        // would mean this reads a hole into an address that has none.
        assertTrue(
            scan().stream().anyMatch(line -> line.contains("\"value\":\"/api/v2/folded\"")),
            "a compile-time constant should stay a plain string");
    }

    @Test
    void the_holes_filler_is_reachable_by_the_source_join() throws Exception {
        // The template says WHERE the hole is; the concat site's own call-site
        // fact says what fills it, joined by `source` -> `result`. Whether the
        // filler resolves is a later tier's question — this only has to leave
        // the join reachable rather than dropping it.
        assertTrue(
            scan().stream().anyMatch(line ->
                line.contains("\"kind\":\"concat\"") && line.contains("\"source\":")),
            "a concat argument must carry the join to its own site");
    }
}
