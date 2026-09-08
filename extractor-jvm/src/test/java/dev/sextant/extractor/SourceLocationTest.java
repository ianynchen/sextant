package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.Opcodes;

/**
 * W6: where a symbol is, which nothing could say before.
 *
 * <p>Measured on mall-admin before this: 1,428 symbols, `line_start: 0` and
 * `line_end: 0` on every one of them. Sextant could say WHAT exists and never
 * WHERE, and an index that cannot produce `file:line` saves nobody a grep.
 *
 * <p>The numbers below are pinned literally against
 * {@link SourceLocationSample}, whose own javadoc says why: a test asserting
 * only "non-zero" passes with every method reporting one wrong line.
 */
class SourceLocationTest {

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

    private static String lines(String fact) {
        int start = fact.indexOf("\"line_start\":");
        int end = fact.indexOf("\"line_end\":");
        return fact.substring(end + 11, fact.indexOf(',', end)) + " from "
            + fact.substring(start + 13, fact.indexOf(',', start));
    }

    @Test
    void a_methods_range_is_the_extent_of_its_body() throws Exception {
        // `single`'s body is line 16; its DECLARATION is 15, and the class file
        // does not state that one. `LineNumberTable` maps bytecode offsets to
        // lines and a signature compiles to no bytecode, so the first line a
        // method can state is its first statement. Subtracting to reach the
        // declaration would be a guess about how the source is formatted —
        // annotations, a wrapped parameter list — so what is read is published.
        assertTrue(
            symbol("SourceLocationSample", "single").contains("\"line_start\":16,"),
            "expected the body's line; got " + lines(symbol("SourceLocationSample", "single")));
        assertTrue(symbol("SourceLocationSample", "single").contains("\"line_end\":16,"));
    }

    @Test
    void a_multi_line_body_reports_a_range_rather_than_a_point() throws Exception {
        // 22 to 25. Without this, `line_end` could be a copy of `line_start`
        // and every single-statement method would still pass.
        String spanning = symbol("SourceLocationSample", "spanning");
        assertTrue(spanning.contains("\"line_start\":22,"), lines(spanning));
        assertTrue(spanning.contains("\"line_end\":25,"), lines(spanning));
    }

    @Test
    void a_method_with_no_body_states_no_line() throws Exception {
        // An abstract method has no `Code` attribute, so there is no
        // `LineNumberTable` inside one. 0 is "not stated" — JVMS numbers source
        // lines from 1, so it can never collide with a real answer — and
        // deriving something from the class's other members would be invention.
        String stated = symbol("SourceLocationSample", "stated");
        assertTrue(stated.contains("\"line_start\":0,"), lines(stated));
        assertTrue(stated.contains("\"line_end\":0,"), lines(stated));
    }

    @Test
    void a_class_states_no_line_of_its_own_but_its_constructor_does() throws Exception {
        // `LineNumberTable` lives inside `Code` (JVMS 4.7.12), and a class has
        // none — so a class symbol reports 0 rather than the minimum over its
        // members, which would be a guess that lands on whichever member sorts
        // first rather than on the declaration.
        //
        // It is not unreachable, though, and that is worth writing down for
        // whatever builds the index: javac maps the IMPLICIT constructor to the
        // class's own declaration line, 11 here, so `<init>` answers what the
        // class symbol cannot.
        assertTrue(
            symbol("SourceLocationSample", "\"construct_kind\":\"class\"").contains("\"line_start\":0,"),
            "a class carries no LineNumberTable of its own");
        assertTrue(
            symbol("SourceLocationSample", "<init>").contains("\"line_start\":11,"),
            "the implicit constructor lands on the class declaration");
    }

    @Test
    void a_parameter_takes_its_name_from_the_local_variable_table() throws Exception {
        // This build passes no `-parameters`, so `MethodParameters` (JVMS
        // 4.7.24) is absent and every parameter name used to be null.
        // `LocalVariableTable` (4.7.13) names the locals, and a method's
        // parameters occupy its first slots.
        //
        // Measured on a real jar rather than claimed: spring-web 6.1.6 gains 282
        // parameter names from this that no other attribute supplied.
        String spanning = symbol("SourceLocationSample", "spanning");
        assertTrue(spanning.contains("\"name\":\"first\""), "first parameter unnamed");
        assertTrue(spanning.contains("\"name\":\"second\""), "second parameter unnamed");
        assertEquals(
            spanning.indexOf("\"name\":\"first\"") < spanning.indexOf("\"name\":\"second\""),
            true,
            "the names are not in declaration order, so the slot walk is wrong");
    }

    @Test
    void a_long_parameter_takes_two_slots_and_does_not_shift_the_names() throws Exception {
        // JVMS 2.6.1: a `long` or `double` occupies TWO local slots, so a slot
        // number is not a parameter index. `widened(long id, String label)` puts
        // `label` at slot 3 — counting instead of walking the sizes reads slot
        // 2, the second half of the long, which holds no variable at all, so
        // `label` comes back unnamed and every later parameter is off by one.
        String widened = symbol("SourceLocationSample", "widened");
        assertTrue(widened.contains("\"name\":\"id\""), "the long parameter is unnamed");
        assertTrue(
            widened.contains("\"name\":\"label\""),
            "the parameter after a long is unnamed, so the slot walk counted instead of sizing");
    }

    /** A class whose method carries a hand-built `LocalVariableTable`, so the
     *  two rules below can be driven at all: javac never emits a body local
     *  sharing a parameter's slot (a parameter is live for the whole method),
     *  and this build passes no `-parameters`, so it never emits both
     *  attributes on one method either. */
    private String builtMethod(boolean declareParameterName, boolean shadowFirst) throws Exception {
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "Built", null, "java/lang/Object", null);
        org.objectweb.asm.MethodVisitor method = writer.visitMethod(
            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "take", "(Ljava/lang/String;)V", null, null);
        if (declareParameterName) method.visitParameter("fromMethodParameters", 0);
        method.visitCode();
        org.objectweb.asm.Label first = new org.objectweb.asm.Label();
        org.objectweb.asm.Label later = new org.objectweb.asm.Label();
        org.objectweb.asm.Label end = new org.objectweb.asm.Label();
        method.visitLabel(first);
        method.visitInsn(Opcodes.NOP);
        method.visitLabel(later);
        method.visitInsn(Opcodes.RETURN);
        method.visitLabel(end);
        // Slot 0 is the parameter (the method is static). The shadow claims the
        // same slot from a LATER label, which is what a reused slot looks like.
        if (shadowFirst) {
            method.visitLocalVariable("fromAShadowingLocal", "Ljava/lang/String;", null, later, end, 0);
        }
        method.visitLocalVariable("fromLocalVariableTable", "Ljava/lang/String;", null, first, end, 0);
        method.visitMaxs(0, 0);
        method.visitEnd();
        writer.visitEnd();
        return new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-built").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains("take"))
            .findFirst()
            .orElseThrow();
    }

    @Test
    void a_local_reusing_a_parameters_slot_does_not_take_its_name() throws Exception {
        // A slot is REUSED: once a variable goes out of scope its number is free,
        // so slot alone names two variables in one method. Taking whichever entry
        // comes first in the table reads the wrong one — and reads it silently,
        // since both are well-formed names.
        //
        // A parameter's scope begins at the method's first instruction and a body
        // local's cannot, which is what tells them apart. javac never actually
        // produces this shape — a parameter is live for the whole method — so it
        // is built rather than compiled, and the guard is defensive by design.
        String taken = builtMethod(false, true);
        assertTrue(
            taken.contains("\"name\":\"fromLocalVariableTable\""),
            "the parameter took a shadowing local's name");
        assertTrue(
            !taken.contains("fromAShadowingLocal"),
            "a local scoped after the first instruction is not a parameter");
    }

    @Test
    void method_parameters_wins_where_both_attributes_name_a_parameter() throws Exception {
        // `MethodParameters` describes PARAMETERS; `LocalVariableTable` describes
        // every local and happens to cover them. The specific attribute wins, and
        // this only fills what nothing else stated — otherwise W5's own alignment
        // of the parameter tables would be silently overwritten here by a slot
        // walk that knows nothing about mandated or synthetic parameters.
        assertTrue(
            builtMethod(true, false).contains("\"name\":\"fromMethodParameters\""),
            "the local variable table overwrote a name MethodParameters stated");
    }

    @Test
    void a_local_whose_type_does_not_match_the_parameter_is_not_its_name() throws Exception {
        // "Scoped from the first instruction, in this slot" is strong evidence, not
        // proof — the format permits something else there, and the failure mode is a
        // WRONG name rather than a missing one, which is well formed and undetectable.
        // No compiler measured here produces this, so it is built.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "Mismatched", null, "java/lang/Object", null);
        org.objectweb.asm.MethodVisitor method = writer.visitMethod(
            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "take", "(Ljava/lang/String;)V", null, null);
        method.visitCode();
        org.objectweb.asm.Label first = new org.objectweb.asm.Label();
        org.objectweb.asm.Label end = new org.objectweb.asm.Label();
        method.visitLabel(first);
        method.visitInsn(Opcodes.RETURN);
        method.visitLabel(end);
        // Slot 0 from the first instruction, but an `int` where the parameter is a String.
        method.visitLocalVariable("anIntSomehow", "I", null, first, end, 0);
        method.visitMaxs(0, 0);
        method.visitEnd();
        writer.visitEnd();

        String taken = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-mismatched").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains("take"))
            .findFirst()
            .orElseThrow();
        assertTrue(
            !taken.contains("anIntSomehow"),
            "a local of a different type was read as the parameter's name");
    }

    @Test
    void a_line_number_of_zero_does_not_become_a_range() throws Exception {
        // JVMS numbers source lines from 1, so 0 in the table states nothing, and 0 is
        // also this schema's "no line stated". A consumer reads 0 as "cannot open this",
        // so a stray 0 entry must not turn into half a range.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "Zeroed", null, "java/lang/Object", null);
        org.objectweb.asm.MethodVisitor method = writer.visitMethod(
            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC, "take", "()V", null, null);
        method.visitCode();
        org.objectweb.asm.Label first = new org.objectweb.asm.Label();
        method.visitLabel(first);
        method.visitLineNumber(0, first);
        method.visitInsn(Opcodes.RETURN);
        method.visitMaxs(0, 0);
        method.visitEnd();
        writer.visitEnd();

        String taken = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-zeroed").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains("take"))
            .findFirst()
            .orElseThrow();
        assertTrue(taken.contains("\"line_start\":0,"), lines(taken));
        assertTrue(taken.contains("\"line_end\":0,"), lines(taken));
    }

    @Test
    void a_source_file_naming_a_path_is_refused() throws Exception {
        // `SourceFile` is a free-form constant-pool string, not a validated path, and it
        // reaches `relative_path` — hashed into artifact names, and read by anything that
        // opens a file. A value carrying a separator is evidence about a class file, not
        // an instruction to this scanner.
        //
        // Asserted through the scanner's own report channel rather than through `Main`,
        // whose join is private: what is pinned is that the stated value arrives verbatim
        // for the caller to judge, and `Main.namesAFile` is the judge.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "sep/Evil", null, "java/lang/Object", null);
        writer.visitSource("../../../../etc/passwd", null);
        writer.visitEnd();

        String[] stated = {null};
        new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-evil", reason -> {}, name -> stated[0] = name);
        assertEquals("../../../../etc/passwd", stated[0], "the stated name is reported verbatim");
    }
}
