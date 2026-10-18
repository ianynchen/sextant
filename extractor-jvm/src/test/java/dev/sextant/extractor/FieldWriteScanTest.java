package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

/** D00 §5's {@code field_write}: an INSTANCE METHOD assigns parameter N directly to field
 *  F, and the fact names which method did it. {@code ConstructorSample.java} is compiled by
 *  Gradle's own test compilation, like {@code CallSample.java} beside it, so every assertion
 *  here is about the bytecode javac actually emits.
 *
 *  <p>Constructors only until 2026-10-18. The guard was never a soundness rule — a setter's
 *  assignment is the same triple, which CP-33 row 1 measured — and lifting it was measured
 *  to roughly triple the writes found on real code (spec
 *  {@code 2026-10-18-the-sixth-edge-design.md} §0). What stays refused is a STATIC method,
 *  where slot 0 is the first parameter rather than {@code this}. */
class FieldWriteScanTest {

    private static final String OWNER = "dev/sextant/extractor/ConstructorSample";
    /** Stands in for the symbol `ClassScanner` mints per method; the fact carries it
     *  verbatim, so the test asserts the string it was handed rather than a shape. */
    private static final String SYMBOL = "doc com/acme/Sample#<init>(sig_abc).";

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
        return MethodFlow.fieldWrites("doc-constructor-sample", SYMBOL, constructor);
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
        // WHICH method wrote it, carried verbatim — the fact is useless to the walk
        // without it once several methods can write one field.
        assertTrue(lines.get(0).contains("\"written_by\":\"" + SYMBOL + "\""), lines.get(0));
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

    /** **A SETTER IS A WRITE.** The same triple in a method named anything else emits the
     *  same fact, naming that method — which is the whole of the guard lift: the shape is
     *  identical and the old filter refused it on the method's NAME. */
    @Test
    void captures_a_setter_assignment() {
        MethodNode setter = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, 0, "setUrl", "(Ljava/lang/String;)V", null, null);
        setter.visitCode();
        setter.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        setter.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 1);
        setter.visitFieldInsn(org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        setter.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        setter.visitMaxs(2, 2);
        setter.visitEnd();

        String written = "doc com/acme/Sample#setUrl(sig_def).";
        List<String> lines = MethodFlow.fieldWrites("doc", written, setter);
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#url.\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"from_parameter\":0"), lines.get(0));
        // The setter's own symbol, not the constructor's: with the guard gone, a field can
        // have several writers and the fact has to say which one this is.
        assertTrue(lines.get(0).contains("\"written_by\":\"" + written + "\""), lines.get(0));
    }

    /** **A STATIC method still emits nothing, and that IS a soundness rule.** Slot 0 holds
     *  the first parameter rather than {@code this}, so {@code ALOAD 0; ALOAD 1; PUTFIELD}
     *  means something else entirely there — and a static field is written by
     *  {@code PUTSTATIC}, a different opcode this pass never matches (CP-33 row 6). */
    @Test
    void emits_nothing_for_a_static_method() {
        MethodNode staticWriter = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9,
            org.objectweb.asm.Opcodes.ACC_STATIC,
            "wire",
            "(Ldev/sextant/extractor/ConstructorSample;Ljava/lang/String;)V",
            null,
            null);
        staticWriter.visitCode();
        staticWriter.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        staticWriter.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 1);
        staticWriter.visitFieldInsn(org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        staticWriter.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        staticWriter.visitMaxs(2, 2);
        staticWriter.visitEnd();

        assertEquals(List.of(), MethodFlow.fieldWrites("doc", "doc com/acme/Sample#wire(sig_ghi).", staticWriter));
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
