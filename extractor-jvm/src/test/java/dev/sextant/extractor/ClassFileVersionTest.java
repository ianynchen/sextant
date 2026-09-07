package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;

/**
 * The accepted class-file range, pinned against real bytes.
 *
 * <p>`build.gradle.kts` has claimed since the ASM bump that this range "is
 * pinned by a test in this same source tree". It was not — no such test
 * existed, which is the exact shape of the defect the bump was meant to close:
 * a ceiling that moves silently, where a class file from a newer JDK is refused
 * and the refusal is the only thing that says so.
 *
 * <p>Measured the way the ceiling is actually reached: by rewriting the two
 * `major_version` bytes JVMS 4.1 fixes at offset 6 of a REAL class file and
 * asking ASM to read it. Nothing here consults ASM's own constant set, which
 * runs ahead of the reader shipped beside it.
 */
class ClassFileVersionTest {

    private static byte[] sampleClassBytes() throws IOException {
        String resource = "/" + Sample.class.getName().replace('.', '/') + ".class";
        try (InputStream in = ClassFileVersionTest.class.getResourceAsStream(resource)) {
            return in.readAllBytes();
        }
    }

    private static byte[] withMajor(byte[] original, int major) {
        byte[] copy = original.clone();
        copy[6] = (byte) ((major >> 8) & 0xFF);
        copy[7] = (byte) (major & 0xFF);
        return copy;
    }

    private static boolean asmReads(byte[] bytes) {
        try {
            new ClassReader(bytes).getClassName();
            return true;
        } catch (RuntimeException refused) {
            return false;
        }
    }

    @Test
    void the_accepted_range_is_what_the_pinned_asm_actually_reads() throws IOException {
        byte[] sample = sampleClassBytes();
        List<Integer> accepted = new ArrayList<>();
        List<Integer> refused = new ArrayList<>();
        // Past the declared ceiling deliberately: a bump that raises it must
        // fail here rather than pass by being untested above the old value.
        for (int major = Main.ACCEPTED_MAJOR_MIN; major <= Main.ACCEPTED_MAJOR_MAX + 4; major++) {
            (asmReads(withMajor(sample, major)) ? accepted : refused).add(major);
        }
        assertEquals(Main.ACCEPTED_MAJOR_MIN, accepted.get(0),
            "the floor moved: JVMS 4.1 starts the format at 45");
        assertEquals(Main.ACCEPTED_MAJOR_MAX, accepted.get(accepted.size() - 1),
            "the ceiling this build actually reads is " + accepted.get(accepted.size() - 1)
                + ", not the declared " + Main.ACCEPTED_MAJOR_MAX
                + " — bump ACCEPTED_MAJOR_MAX with the library, or the refusal is silent");
        assertTrue(refused.contains(Main.ACCEPTED_MAJOR_MAX + 1),
            "nothing above the ceiling was refused, so the ceiling is not where it is declared");
    }

    @Test
    void the_major_read_off_the_bytes_is_the_one_that_was_written() throws IOException {
        byte[] sample = sampleClassBytes();
        // The value a document records comes from the file, so a rewritten
        // header must read back exactly — including a major this build cannot
        // parse, which is the case the field exists to describe.
        for (int major : List.of(45, 52, 61, 65, Main.ACCEPTED_MAJOR_MAX, Main.ACCEPTED_MAJOR_MAX + 1)) {
            assertEquals(major, Main.majorVersionOf(withMajor(sample, major)));
        }
    }

    @Test
    void a_file_too_short_to_hold_a_header_answers_zero_rather_than_guessing() {
        assertEquals(0, Main.majorVersionOf(new byte[] {(byte) 0xCA, (byte) 0xFE}));
    }
}
