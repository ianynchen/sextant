package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** W7: eleven access flags the scanner was dropping, and the one that changes a
 *  derived value rather than adding one. */
class AccessFlagTest {

    private List<String> scan(String simpleName) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + simpleName + ".class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-" + simpleName);
        }
    }

    private String symbol(String simpleName, String named) throws Exception {
        return scan(simpleName).stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains(named))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no symbol fact matching " + named));
    }

    @Test
    void an_annotation_type_is_not_reported_as_an_interface() throws Exception {
        // `@interface` compiles to an interface extending java.lang.annotation.Annotation,
        // so it carries ACC_INTERFACE as well — and testing that flag first made every
        // annotation type in the estate report `construct_kind: "interface"`. The class
        // file distinguishes them with ACC_ANNOTATION, and §8.1 rule 5 says to follow a
        // distinction the provider makes rather than flatten it.
        //
        // This is the one W7 flag that changes a value rather than adding one, which is
        // why `construct_kind` gained a fourteenth member (D00 §4, ruled in the design).
        assertTrue(
            symbol("Marked", "Marked#").contains("\"construct_kind\":\"annotation\""),
            "an annotation type still reads as an interface");
        assertTrue(
            symbol("Behaviour", "Behaviour#").contains("\"construct_kind\":\"interface\""),
            "a plain interface must be unaffected");
    }

    @Test
    void varargs_is_the_only_thing_telling_two_identical_descriptors_apart() throws Exception {
        // Capability 9.15's blocker, stated as the fixture states it: `spread(String...)`
        // and `array(String[])` compile to the SAME descriptor — both
        // `([Ljava/lang/String;)V`, both hashing to `sig_05a88677` — so a call passing
        // three strings and one passing `new String[]{…}` were the same declaration.
        String spread = symbol("AccessFlagSample", "#spread(");
        String array = symbol("AccessFlagSample", "#array(");
        assertTrue(spread.contains("sig_05a88677") && array.contains("sig_05a88677"),
            "the fixture no longer has two methods of one descriptor; the point is lost");
        assertTrue(spread.contains("\"varargs\":true"), "the varargs method is not flagged");
        assertTrue(array.contains("\"varargs\":false"), "the array method is flagged varargs");
    }

    @Test
    void an_interfaces_abstract_and_default_methods_stop_reading_identically() throws Exception {
        // Both are public, neither is static or synthetic: before `abstract`, a consumer
        // asking "does this interface declare behaviour" had nothing to read at all.
        assertTrue(symbol("Behaviour", "abstractOne").contains("\"abstract\":true"));
        assertTrue(symbol("Behaviour", "defaultOne").contains("\"abstract\":false"));
    }

    @Test
    void a_methods_remaining_flags_are_reported() throws Exception {
        assertTrue(symbol("AccessFlagSample", "guarded").contains("\"final\":true"));
        assertTrue(symbol("AccessFlagSample", "guarded").contains("\"synchronized\":true"));
        assertTrue(symbol("AccessFlagSample", "foreign").contains("\"native\":true"));
        // `native` and `abstract` both mean "no body here", and they are not the same
        // claim: one says the code is elsewhere in this language, the other outside it.
        assertTrue(symbol("AccessFlagSample", "foreign").contains("\"abstract\":false"));
    }

    @Test
    void a_fields_final_and_volatile_are_reported() throws Exception {
        assertTrue(symbol("AccessFlagSample", "fixed").contains("\"final\":true"));
        assertTrue(symbol("AccessFlagSample", "changing").contains("\"volatile\":true"));
        // `transient` keeps its own meaning and is not confused with either: its bit is
        // ACC_VARARGS on a method, which is why the two constructs have separate readers.
        assertTrue(symbol("AccessFlagSample", "fixed").contains("\"transient\":false"));
    }

    @Test
    void a_type_reports_abstract_and_final() throws Exception {
        assertTrue(symbol("AccessFlagSample", "AccessFlagSample#").contains("\"abstract\":true"));
        assertTrue(symbol("AccessFlagSample", "AccessFlagSample#").contains("\"final\":false"));
    }

    @Test
    void every_modifier_key_is_written_whether_or_not_it_is_set() throws Exception {
        // D00 §5a's rule, extended to W7's keys: an ABSENT modifier cannot be told apart
        // from a scanner that does not report it, so each is always written.
        String method = symbol("AccessFlagSample", "#array(");
        for (String key : List.of("static", "synthetic", "abstract", "varargs", "final",
                                  "native", "synchronized")) {
            assertTrue(method.contains("\"" + key + "\":"), "method modifier missing: " + key);
        }
        String field = symbol("AccessFlagSample", "changing");
        for (String key : List.of("static", "transient", "final", "volatile")) {
            assertTrue(field.contains("\"" + key + "\":"), "field modifier missing: " + key);
        }
        assertEquals(
            1,
            symbol("AccessFlagSample", "AccessFlagSample#").split("\"abstract\":", -1).length - 1,
            "a type states abstract once, in its modifiers, and nowhere else");
    }
}
