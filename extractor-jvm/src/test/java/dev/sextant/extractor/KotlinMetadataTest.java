package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** {@code KotlinSample.kt} is compiled by Gradle's own Kotlin test compilation, exactly
 *  like {@code FieldSample.java} is compiled by javac — a committed source fixture
 *  satisfies that just as well as reaching into a sibling Maven module's gitignored
 *  build output, without a dependency this module's build doesn't express. */
class KotlinMetadataTest {

    private List<String> scan(String className) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-kotlin-sample");
        }
    }

    @Test
    void projects_kotlin_type_system_nullability_onto_the_shared_field() throws Exception {
        List<String> lines = scan("KotlinSample");
        // Resolved, not partial: unlike Java, the Kotlin type itself declares it.
        assertTrue(lines.stream().anyMatch(l -> l.contains("KotlinSample#note.")
            && l.contains("\"nullable\":true")
            && l.contains("\"nullable_resolution\":\"resolved\"")));
        assertTrue(lines.stream().anyMatch(l -> l.contains("KotlinSample#id.")
            && l.contains("\"nullable\":false")
            && l.contains("\"nullable_resolution\":\"resolved\"")));
    }

    /** D00 §6: the raw @Metadata read must stay recoverable behind the extension
     *  namespace, not only survive as the projection onto the shared field above. */
    @Test
    void keeps_the_raw_metadata_read_recoverable_in_ext_kotlin() throws Exception {
        assertTrue(scan("KotlinSample").stream().anyMatch(l -> l.contains("KotlinSample#note.")
            && l.contains("\"ext\":{\"kotlin\":{\"nullable\":true}}")));
    }
}
