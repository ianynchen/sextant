package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;

/** Two overloads that share one symbol are two rows the resolver cannot tell
 *  apart: every join on that symbol multiplies, so N annotated overloads
 *  become N² endpoints. D00 §1 requires a descriptor hash here — on every
 *  method, so that identity never moves when a neighbour appears. */
class OverloadScanTest {

    /** The value of the `symbol` field alone — two overloads differ in their
     *  signature whatever happens, so only the identifier answers the
     *  questions these tests ask. */
    private static List<String> symbolsNamed(List<String> lines, String name) {
        Pattern symbolField = Pattern.compile("\"symbol\":\"([^\"]*)\"");
        List<String> found = new ArrayList<>();
        for (String line : lines) {
            if (!line.contains("\"kind\":\"symbol\"")) continue;
            Matcher hit = symbolField.matcher(line);
            while (hit.find()) {
                if (hit.group(1).contains(name)) found.add(hit.group(1));
            }
        }
        return found;
    }

    private List<String> scanOverloaded() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/Overloaded.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-overloaded");
        }
    }

    @Test
    void gives_two_overloads_two_different_symbols_when_they_share_a_name() throws Exception {
        List<String> renders = symbolsNamed(scanOverloaded(), "Overloaded#render");
        assertEquals(2, renders.size(), renders.toString());
        assertNotEquals(renders.get(0), renders.get(1));
    }

    @Test
    void disambiguates_an_overload_by_descriptor_hash_and_never_by_an_ordinal() throws Exception {
        for (String render : symbolsNamed(scanOverloaded(), "Overloaded#render")) {
            assertTrue(render.contains("Overloaded#render(sig_"), render);
            assertTrue(render.endsWith(")."), render);
        }
    }

    @Test
    void names_a_method_with_no_sibling_by_descriptor_hash_too() throws Exception {
        List<String> plain = symbolsNamed(scanOverloaded(), "Overloaded#plain");
        assertEquals(1, plain.size(), plain.toString());
        assertTrue(plain.get(0).contains("Overloaded#plain(sig_"), plain.get(0));
    }

    /** One class, one name, the given descriptors. Built rather than compiled
     *  so that "before" and "after" are genuinely the same type — the symbols
     *  can then be compared for equality outright, owner included. */
    private static byte[] classDeclaring(String... descriptors) {
        ClassWriter writer = new ClassWriter(0);
        writer.visit(Opcodes.V21, Opcodes.ACC_PUBLIC | Opcodes.ACC_ABSTRACT,
                     "com/acme/Grown", null, "java/lang/Object", null);
        for (String descriptor : descriptors) {
            writer.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_ABSTRACT,
                               "save", descriptor, null, null).visitEnd();
        }
        writer.visitEnd();
        return writer.toByteArray();
    }

    @Test
    void leaves_an_untouched_methods_symbol_unchanged_when_an_overload_is_added() {
        ClassScanner scanner = new ClassScanner("com.acme/orders", "1.0.0");
        String before = symbolsNamed(
            scanner.scan(classDeclaring("(I)V"), "doc-grown"), "Grown#save").get(0);

        List<String> after = symbolsNamed(
            scanner.scan(classDeclaring("(I)V", "(Ljava/lang/String;)V"), "doc-grown"),
            "Grown#save");

        // The invariant D00 §1's ordinal prohibition exists to protect: the
        // identity of a method nobody touched does not move because a sibling
        // appeared beside it (NFR-3). A disambiguator spent only on names that
        // are *currently* shared breaks this exactly as an ordinal would —
        // `save().` would become `save(sig_…).` on the next commit, and every
        // curation, link and blast radius pinned to the old string is orphaned.
        assertEquals(2, after.size(), after.toString());
        assertTrue(after.contains(before), before + " missing from " + after);
    }
}
