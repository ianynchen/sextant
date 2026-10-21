package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** The `type_header` read (D00 §5), against classes this test's own compilation produced and
 *  a jar it builds from them — no fixture, no network. */
class TypeHeadersTest {

    /** The shape the whole item is about: an exception that reaches a handler ONLY as a
     *  parameter type. Its name appears in no `CONSTANT_Class` entry of the caller — only in
     *  a method descriptor — which is exactly what a constant-pool walk would miss. */
    static class ParameterOnly extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }
    static class Handler {
        String handle(ParameterOnly e) { return "x"; }
    }

    private static byte[] bytesOf(Class<?> type) throws IOException {
        String resource = type.getName().replace('.', '/') + ".class";
        try (InputStream in = TypeHeadersTest.class.getClassLoader().getResourceAsStream(resource)) {
            return in.readAllBytes();
        }
    }

    private static String internal(Class<?> type) {
        return type.getName().replace('.', '/');
    }

    @Test
    void a_type_named_only_in_a_method_descriptor_is_a_reference() throws IOException {
        Set<String> referenced = new HashSet<>();
        TypeHeaders.collectReferences(bytesOf(Handler.class), referenced);
        assertTrue(referenced.contains(internal(ParameterOnly.class)),
            "the parameter type is referenced through its descriptor alone: " + referenced);
    }

    @Test
    void the_header_of_a_referenced_type_is_read_from_a_jar_and_its_chain_followed(
            @TempDir Path dir) throws IOException {
        // A jar holding the exception; `RuntimeException` is the JDK's and in no jar, so the
        // chain must stop there WITHOUT inventing a fact for it.
        Path jar = dir.resolve("lib-1.0.jar");
        try (JarOutputStream out = new JarOutputStream(Files.newOutputStream(jar))) {
            out.putNextEntry(new JarEntry(internal(ParameterOnly.class) + ".class"));
            out.write(bytesOf(ParameterOnly.class));
            out.closeEntry();
        }
        List<TypeHeaders.Entry> classpath =
            List.of(new TypeHeaders.Entry("com.acme:lib", "1.0", jar));

        TypeHeaders.Result result = TypeHeaders.resolve(
            Set.of(internal(ParameterOnly.class)), Set.of(), classpath, "doc");

        assertEquals(1, result.headers(), "one header: the exception; RuntimeException is JDK");
        assertEquals(1, result.unlocated(), "RuntimeException was looked for and not found");
        String fact = result.factLines().get(0);
        assertTrue(fact.contains("\"kind\":\"type_header\""), fact);
        assertTrue(fact.contains("sextant-jvm maven com.acme/lib 1.0 " + internal(ParameterOnly.class) + "#"),
            "the symbol carries the LIBRARY's coordinate, not the module's: " + fact);
        assertTrue(fact.contains("java/lang/RuntimeException#"), "superclass recorded: " + fact);
        assertFalse(fact.contains("\"call_site\""), "no member of the type is read");
    }

    @Test
    void a_type_the_module_itself_compiled_is_never_looked_up(@TempDir Path dir) throws IOException {
        Path jar = dir.resolve("lib-1.0.jar");
        try (JarOutputStream out = new JarOutputStream(Files.newOutputStream(jar))) {
            out.putNextEntry(new JarEntry(internal(ParameterOnly.class) + ".class"));
            out.write(bytesOf(ParameterOnly.class));
            out.closeEntry();
        }
        TypeHeaders.Result result = TypeHeaders.resolve(
            Set.of(internal(ParameterOnly.class)),
            Set.of(internal(ParameterOnly.class)),   // the module's OWN type
            List.of(new TypeHeaders.Entry("com.acme:lib", "1.0", jar)), "doc");
        assertEquals(0, result.headers(), "a module's own class has real facts; no header for it");
    }
}
