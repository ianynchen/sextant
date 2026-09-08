package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** W7's declaration attributes: `Record`, `Exceptions`, `PermittedSubclasses`,
 *  `Deprecated`. */
class DeclarationAttributeTest {

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
    void a_record_stops_reporting_itself_as_a_class() throws Exception {
        // There is no ACC_RECORD; JVMS 4.7.30's `Record` attribute is the signal, and its
        // presence is all of it. `record` has been in D00 §4's closed set since it was
        // written and had NO producer — every record in the estate read `class`, which is
        // the "declared, never read" shape reached from the other side.
        assertTrue(
            symbol("RecordComponents", "RecordComponents#").contains("\"construct_kind\":\"record\""),
            "a record still reads as a class");
        assertTrue(
            symbol("AccessFlagSample", "AccessFlagSample#").contains("\"construct_kind\":\"class\""),
            "a plain class must be unaffected");
    }

    @Test
    void a_records_components_are_already_its_fields() throws Exception {
        // Why the components are NOT emitted as a second fact shape: they are already
        // here as the record's private final fields, in declaration order, with their
        // types. Emitting them again would be two vocabularies for one declaration.
        List<String> facts = scan("RecordComponents");
        assertTrue(
            facts.stream().anyMatch(f -> f.contains("RecordComponents#id.") && f.contains("\"field\"")),
            "the first component is not present as a field");
        assertTrue(
            facts.stream().anyMatch(f -> f.contains("RecordComponents#tags.") && f.contains("\"field\"")),
            "the second component is not present as a field");
    }

    @Test
    void a_sealed_type_names_every_type_permitted_to_extend_it() throws Exception {
        String sealed = symbol("SealedSample", "SealedSample#");
        assertTrue(sealed.contains("\"permits\":"), "the sealed type states no permits");
        assertTrue(sealed.contains("SealedSample$Approved#") || sealed.contains("Approved#"),
            "the first permitted subtype is missing");
        assertTrue(sealed.contains("Rejected#"), "the second permitted subtype is missing");
    }

    @Test
    void an_unsealed_type_carries_no_permits_key_at_all() throws Exception {
        // The same "nothing to say, nothing written" rule `supertype` and
        // `generic_interfaces` follow: nearly every type permits nothing.
        assertTrue(
            !symbol("AccessFlagSample", "AccessFlagSample#").contains("permits"),
            "an ordinary class carried a permits key");
    }

    @Test
    void a_declared_throws_is_carried_in_declaration_order() throws Exception {
        // ASM has always handed `Exceptions` to `visitMethod`; the parameter was accepted
        // and discarded. Order matters because it is the declaration's own.
        String settle = symbol("SealedSample", "settle");
        int io = settle.indexOf("java/io/IOException#");
        int interrupted = settle.indexOf("java/lang/InterruptedException#");
        assertTrue(io > 0 && interrupted > 0, "a declared throws is missing: " + settle);
        assertTrue(io < interrupted, "the declared order was not kept");
        assertTrue(settle.contains("\"throws\":"), "throws is not inside the signature");
    }

    @Test
    void a_method_declaring_no_throws_carries_no_key() throws Exception {
        assertTrue(
            !symbol("AccessFlagSample", "#array(").contains("throws"),
            "a method declaring nothing carried a throws key");
    }

    @Test
    void a_deprecated_declaration_says_so() throws Exception {
        // JVMS 4.7.15, which ASM folds into the access flags. Distinct from the
        // `@Deprecated` ANNOTATION, which a catalog reads separately — a class file can
        // carry either, both, or neither.
        assertTrue(symbol("SealedSample", "legacy").contains("\"deprecated\":true"));
        assertTrue(symbol("SealedSample", "settle").contains("\"deprecated\":false"));
    }
}
