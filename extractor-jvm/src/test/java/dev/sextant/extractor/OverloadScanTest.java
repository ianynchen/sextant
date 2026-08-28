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

/** Two overloads that share one symbol are two rows the resolver cannot tell
 *  apart: every join on that symbol multiplies, so N annotated overloads
 *  become N² endpoints. D00 §1 requires a descriptor hash here. */
class OverloadScanTest {

    private List<String> scanOverloaded() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/Overloaded.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-overloaded");
        }
    }

    /** The value of the `symbol` field alone — two overloads differ in their
     *  signature whatever happens, so only the identifier answers the
     *  question this test asks. */
    private List<String> symbolsNamed(String name) throws Exception {
        Pattern symbolField = Pattern.compile("\"symbol\":\"([^\"]*)\"");
        List<String> found = new ArrayList<>();
        for (String line : scanOverloaded()) {
            if (!line.contains("\"kind\":\"symbol\"")) continue;
            Matcher hit = symbolField.matcher(line);
            while (hit.find()) {
                if (hit.group(1).contains("Overloaded#" + name)) found.add(hit.group(1));
            }
        }
        return found;
    }

    @Test
    void gives_two_overloads_two_different_symbols_when_they_share_a_name() throws Exception {
        List<String> renders = symbolsNamed("render");
        assertEquals(2, renders.size(), renders.toString());
        assertNotEquals(renders.get(0), renders.get(1));
    }

    @Test
    void disambiguates_an_overload_by_descriptor_hash_and_never_by_an_ordinal() throws Exception {
        for (String render : symbolsNamed("render")) {
            assertTrue(render.contains("Overloaded#render(sig_"), render);
            assertTrue(render.endsWith(")."), render);
        }
    }

    @Test
    void leaves_a_method_with_no_sibling_the_bare_form_when_it_is_not_overloaded()
            throws Exception {
        List<String> plain = symbolsNamed("plain");
        assertEquals(1, plain.size(), plain.toString());
        assertTrue(plain.get(0).contains("Overloaded#plain()."), plain.get(0));
    }
}
