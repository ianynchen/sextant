package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

/** D00 §5's {@code field_write}: a constructor assigns parameter N directly
 *  to field F. {@code ConstructorSample.java} is compiled by Gradle's own
 *  test compilation, like {@code CallSample.java} beside it, so every
 *  assertion here is about the bytecode javac actually emits. */
class FieldWriteScanTest {

    private static final String OWNER = "dev/sextant/extractor/ConstructorSample";

    private static List<String> fieldWrites(String descriptor) throws Exception {
        ClassNode classNode = new ClassNode();
        try (InputStream in = FieldWriteScanTest.class
                .getResourceAsStream("/dev/sextant/extractor/ConstructorSample.class")) {
            new ClassReader(in.readAllBytes()).accept(classNode, ClassReader.SKIP_FRAMES);
        }
        MethodNode constructor = classNode.methods.stream()
            .filter(candidate -> "<init>".equals(candidate.name) && candidate.desc.equals(descriptor))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no <init>" + descriptor + " on ConstructorSample"));
        return MethodFlow.fieldWrites("doc-constructor-sample", constructor);
    }

    /** {@code this.url = url;} — the exact {@code ALOAD 0; ALOAD 1; PUTFIELD}
     *  triple, and the only shape that produces a fact. */
    @Test
    void captures_a_direct_parameter_assignment() throws Exception {
        List<String> lines = fieldWrites("(Ljava/lang/String;)V");
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"kind\":\"field_write\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"document_id\":\"doc-constructor-sample\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#url.\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"from_parameter\":0"), lines.get(0));
    }

    /** {@code this.url = url + suffix;} — the value PUTFIELD stores is the
     *  concatenation's result, not a bare parameter load, so no fact. */
    @Test
    void emits_nothing_for_a_computed_assignment() throws Exception {
        assertEquals(List.of(), fieldWrites("(Ljava/lang/String;Ljava/lang/String;)V"));
    }

    /** {@code long id} occupies slots 1 and 2, so {@code label} — the second
     *  parameter — starts at slot 3, not 1. {@code from_parameter} must read
     *  the parameter's own index (1), never its slot number (3). */
    @Test
    void maps_a_two_slot_leading_parameter_to_the_right_parameter_index() throws Exception {
        List<String> lines = fieldWrites("(JLjava/lang/String;)V");
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#label.\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"from_parameter\":1"), lines.get(0));
    }

    /** The pass runs where its own gate is: only {@code <init>}. A method
     *  with the exact same bytecode shape but a different name emits
     *  nothing. */
    @Test
    void emits_nothing_outside_a_constructor() {
        MethodNode notAConstructor = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, 0, "setUrl", "(Ljava/lang/String;)V", null, null);
        notAConstructor.visitCode();
        notAConstructor.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        notAConstructor.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 1);
        notAConstructor.visitFieldInsn(org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        notAConstructor.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        notAConstructor.visitMaxs(2, 2);
        notAConstructor.visitEnd();

        assertEquals(List.of(), MethodFlow.fieldWrites("doc", notAConstructor));
    }

    /** The pass runs where the method symbol is minted, so a {@code
     *  field_write} is a line of the same fact file as the constructor it
     *  belongs to, carrying the same document. */
    @Test
    void class_scanner_emits_field_write_beside_the_constructor_symbol_it_belongs_to()
            throws Exception {
        try (InputStream in = FieldWriteScanTest.class
                .getResourceAsStream("/dev/sextant/extractor/ConstructorSample.class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-constructor-sample");
            assertTrue(lines.stream().anyMatch(line -> line.contains("\"kind\":\"field_write\"")
                && line.contains("\"document_id\":\"doc-constructor-sample\"")
                && line.contains("\"field\":\"" + OWNER + "#url.\"")
                && line.contains("\"from_parameter\":0")), String.join("\n", lines));
        }
    }
}
