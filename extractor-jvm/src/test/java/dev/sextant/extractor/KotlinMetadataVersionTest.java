package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.AnnotationVisitor;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;

/**
 * The Kotlin metadata range this build reads, pinned against real bytes (OI-219).
 *
 * <p>The same defect {@link ClassFileVersionTest} closes for ASM, one layer up: the
 * pinned {@code kotlin-metadata-jvm} refuses {@code @Metadata} from a compiler newer
 * than it knows, and the class then comes out {@code partial} with its nullability,
 * suspend return types, parameter defaults and extension-receiver mark unread. With
 * 2.2.0 pinned, every class kotlinc 2.4 wrote came out that way, and nothing failed.
 *
 * <p>Measured the way the ceiling is reached: by rewriting the {@code mv} element of a
 * REAL class's {@code @Metadata} and scanning it. Nothing here consults the library's
 * own version constants.
 */
class KotlinMetadataVersionTest {

    /** The newest Kotlin minor this build's metadata library reads — one past the
     *  library's own release, which is how kotlin-metadata-jvm is versioned. Raising it
     *  means bumping the library and the Kotlin plugin together (build.gradle.kts), and
     *  COVERAGE §3a's Kotlin row with them. */
    static final int READS_THROUGH_MINOR = 5;

    private static byte[] sampleClassBytes() throws IOException {
        try (InputStream in = KotlinMetadataVersionTest.class
                .getResourceAsStream("/dev/sextant/extractor/KotlinSample.class")) {
            return in.readAllBytes();
        }
    }

    /** The class with its {@code @Metadata mv} replaced by {@code {2, minor, 0}}. */
    private static byte[] withMetadataVersion(byte[] original, int minor) {
        ClassReader reader = new ClassReader(original);
        ClassWriter writer = new ClassWriter(0);
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
                AnnotationVisitor next = super.visitAnnotation(descriptor, visible);
                if (!descriptor.equals(KotlinNullability.DESCRIPTOR)) {
                    return next;
                }
                return new AnnotationVisitor(Opcodes.ASM9, next) {
                    @Override
                    public void visit(String name, Object value) {
                        super.visit(name, name.equals("mv") ? new int[] {2, minor, 0} : value);
                    }
                };
            }
        }, 0);
        return writer.toByteArray();
    }

    /** The reasons the scanner gave for not reading this class's metadata. */
    private static List<String> unreadable(byte[] bytes) {
        List<String> reasons = new ArrayList<>();
        new ClassScanner("com.acme/orders", "1.0.0").scan(bytes, "doc-version", reasons::add);
        return reasons;
    }

    @Test
    void the_sample_this_build_compiled_is_read() throws IOException {
        // The test sources are compiled by the same Kotlin plugin version the library
        // is pinned to, so this is the newest compiler output the build claims to read.
        assertEquals(List.of(), unreadable(sampleClassBytes()));
    }

    @Test
    void the_read_range_is_what_the_pinned_library_actually_reads() throws IOException {
        byte[] sample = sampleClassBytes();
        List<Integer> read = new ArrayList<>();
        List<Integer> refused = new ArrayList<>();
        // Past the declared ceiling deliberately: a bump that raises it must fail
        // here rather than pass by being untested above the old value.
        for (int minor = 0; minor <= READS_THROUGH_MINOR + 3; minor++) {
            (unreadable(withMetadataVersion(sample, minor)).isEmpty() ? read : refused).add(minor);
        }
        assertEquals(0, read.get(0), "Kotlin 2.0 metadata is no longer read");
        assertEquals(READS_THROUGH_MINOR, read.get(read.size() - 1),
            "the ceiling this build actually reads is 2." + read.get(read.size() - 1)
                + ", not the declared 2." + READS_THROUGH_MINOR);
        assertTrue(refused.contains(READS_THROUGH_MINOR + 1),
            "nothing above the ceiling was refused, so the ceiling is not where it is declared");
    }

    @Test
    void metadata_past_the_ceiling_is_named_not_dropped_silently() throws IOException {
        // The class is still scanned; the refusal is what makes it `partial`, and its
        // reason names the version, so a document says why its Kotlin facts are missing.
        List<String> reasons =
            unreadable(withMetadataVersion(sampleClassBytes(), READS_THROUGH_MINOR + 1));
        assertEquals(1, reasons.size());
        assertTrue(reasons.get(0).contains("2." + (READS_THROUGH_MINOR + 1)), reasons.get(0));
    }
}
