package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

/** D00 §5's {@code field_write}: a method assigns a parameter, a constant or a call's result
 *  directly to field F, and the fact names which method did it. {@code ConstructorSample.java} is compiled by
 *  Gradle's own test compilation, like {@code CallSample.java} beside it, so every assertion
 *  here is about the bytecode javac actually emits.
 *
 *  <p>Constructors only until 2026-10-18. The guard was never a soundness rule — a setter's
 *  assignment is the same triple, which CP-33 row 1 measured — and lifting it was measured
 *  to roughly triple the writes found on real code (spec
 *  {@code 2026-10-18-the-sixth-edge-design.md} §0). What stays refused is a STATIC method's
 *  {@code PUTFIELD}, where slot 0 is the first parameter rather than {@code this}; a
 *  {@code PUTSTATIC}, and a write from a call's result, are facts since 2026-10-26 (CP-33
 *  rows 6 and 7). */
class FieldWriteScanTest {

    private static final String OWNER = "dev/sextant/extractor/ConstructorSample";
    /** Stands in for the symbol `ClassScanner` mints per method; the fact carries it
     *  verbatim, so the test asserts the string it was handed rather than a shape. */
    private static final String SYMBOL = "doc com/acme/Sample#<init>(sig_abc).";

    private static List<String> fieldWrites(String descriptor) throws Exception {
        return MethodFlow.fieldWrites("doc-constructor-sample", SYMBOL, method("<init>", descriptor));
    }

    /** One method of the compiled {@code ConstructorSample}, as javac emitted it. */
    private static MethodNode method(String name, String descriptor) throws Exception {
        return method("ConstructorSample", name, descriptor);
    }

    /** One method of a compiled test fixture class, as its compiler emitted it. */
    private static MethodNode method(String className, String name, String descriptor)
            throws Exception {
        ClassNode classNode = new ClassNode();
        try (InputStream in = FieldWriteScanTest.class
                .getResourceAsStream("/dev/sextant/extractor/" + className + ".class")) {
            new ClassReader(in.readAllBytes()).accept(classNode, ClassReader.SKIP_FRAMES);
        }
        return classNode.methods.stream()
            .filter(candidate -> name.equals(candidate.name) && candidate.desc.equals(descriptor))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no " + name + descriptor + " on " + className));
    }

    /** The writes {@code fieldWrites} reports into one named field of a fixture method. */
    private static List<String> writesInto(
            String className, String name, String descriptor, String field) throws Exception {
        return MethodFlow.fieldWrites("doc", SYMBOL, method(className, name, descriptor)).stream()
            .filter(line -> line.contains("#" + field + ".\""))
            .toList();
    }

    /** The {@code "source":N} a write's value carries, or -1 where it carries none. */
    private static int sourceOf(String line) {
        java.util.regex.Matcher found =
            java.util.regex.Pattern.compile("\"source\":(\\d+)").matcher(line);
        return found.find() ? Integer.parseInt(found.group(1)) : -1;
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

    /** **A write from a CONSTANT carries the constant** (`OI-138` cause 2). `private String
     *  url = "http://visits-service/"` compiles into the constructor as {@code ALOAD 0;
     *  LDC; PUTFIELD} — no parameter anywhere — so the fact says `value` instead of
     *  `from_parameter`, and before it said nothing at all. */
    @Test
    void captures_a_write_from_a_constant_and_names_no_parameter() {
        MethodNode constructor = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, 0, "<init>", "()V", null, null);
        constructor.visitCode();
        constructor.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        constructor.visitLdcInsn("http://visits-service/");
        constructor.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        constructor.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        constructor.visitMaxs(2, 1);
        constructor.visitEnd();

        String written = "doc com/acme/Sample#<init>(sig_abc).";
        List<String> lines = MethodFlow.fieldWrites("doc", written, constructor);
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#url.\""), lines.get(0));
        assertTrue(
            lines.get(0).contains("\"value\":{\"kind\":\"string\",\"value\":\"http://visits-service/\"}"),
            lines.get(0));
        // The two keys are exclusive: a constant write has no parameter to name, and a
        // reader that found both would not know which one the value came from.
        assertTrue(!lines.get(0).contains("from_parameter"), lines.get(0));
    }

    /** A constant D00 §5's table has no kind for emits NOTHING — not a write with an
     *  unreadable value. A reader seeing the fact would cross to it and find no value; its
     *  absence says "no write was reported", which is true. */
    @Test
    void emits_nothing_for_a_constant_the_grammar_has_no_kind_for() {
        MethodNode constructor = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, 0, "<init>", "()V", null, null);
        constructor.visitCode();
        constructor.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        constructor.visitLdcInsn(2.5d);
        constructor.visitFieldInsn(org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "rate", "D");
        constructor.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        constructor.visitMaxs(3, 1);
        constructor.visitEnd();

        assertEquals(
            List.of(),
            MethodFlow.fieldWrites("doc", "doc com/acme/Sample#<init>(sig_abc).", constructor));
    }

    /** **A static method's PUTFIELD still emits nothing, and that IS a soundness rule.** Slot
     *  0 holds the first parameter rather than {@code this}, so {@code ALOAD 0; ALOAD 1;
     *  PUTFIELD} writes ANOTHER object's field there — {@code other.f = …}, which this fact
     *  never reports. A static field's own {@code PUTSTATIC} is a different opcode, read by
     *  the tests below. */
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

    /** **A write from a CALL'S RESULT names that call** (CP-33 row 7). {@code this.url =
     *  make()} is {@code ALOAD 0; INVOKESTATIC; PUTFIELD}: no parameter and no constant, so
     *  the value is the §5 argument-grammar entry a call argument fed by a call already
     *  has — {@code unresolved} with the call's {@code source}, which is that call site's
     *  own {@code result} in the WRITER's frame. The join is asserted against the call
     *  site the same method emits, not against a number. */
    @Test
    void captures_a_write_from_a_calls_result_and_names_that_call() throws Exception {
        MethodNode constructor = method("<init>", "(Z)V");
        List<String> lines = MethodFlow.fieldWrites("doc", SYMBOL, constructor);
        assertEquals(1, lines.size(), String.join("\n", lines));
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#url.\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"value\":{\"kind\":\"unresolved\",\"source\":"),
            lines.get(0));
        assertTrue(!lines.get(0).contains("from_parameter"), lines.get(0));
        int source = sourceOf(lines.get(0));
        assertTrue(MethodFlow.callSites("doc", SYMBOL, constructor).stream()
            .anyMatch(site -> site.contains("\"name\":\"make\"")
                && site.contains("\"result\":" + source + ",")),
            "no call site whose result is " + source);
    }

    /** CP-33 row 7's exact sequence — a CAST between the call and the write. A cast is the
     *  same reference re-labelled, so the value is still the call's result. */
    @Test
    void captures_a_calls_result_through_a_cast() throws Exception {
        MethodNode constructor = method("<init>", "(Ljava/util/List;)V");
        List<String> lines = MethodFlow.fieldWrites("doc", SYMBOL, constructor);
        assertEquals(1, lines.size(), String.join("\n", lines));
        int source = sourceOf(lines.get(0));
        assertTrue(MethodFlow.callSites("doc", SYMBOL, constructor).stream()
            .anyMatch(site -> site.contains("\"name\":\"get\"")
                && site.contains("\"result\":" + source + ",")),
            "no call site whose result is " + source);
    }

    /** **A PUTSTATIC is a field write** (CP-33 row 6), and javac's static initialiser is the
     *  real bytecode for it: {@code ldc; invokestatic List.of; putstatic NAMES}. No receiver
     *  is loaded and none is checked — a static field has no {@code this}. */
    @Test
    void captures_a_static_field_written_from_a_call_in_the_static_initialiser()
            throws Exception {
        MethodNode initialiser = method("<clinit>", "()V");
        String written = "doc com/acme/Sample#<clinit>(sig_cl).";
        List<String> lines = MethodFlow.fieldWrites("doc", written, initialiser);
        assertEquals(1, lines.size(), String.join("\n", lines));
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#NAMES.\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"written_by\":\"" + written + "\""), lines.get(0));
        int source = sourceOf(lines.get(0));
        assertTrue(MethodFlow.callSites("doc", written, initialiser).stream()
            .anyMatch(site -> site.contains("\"name\":\"of\"")
                && site.contains("\"result\":" + source + ",")),
            "no call site whose result is " + source);
    }

    /** Kotlin's top-level {@code val client = HttpClient(CIO) { … }}, as kotlinc 2.2 emits it
     *  into {@code ProbeKt.<clinit>} (CP-54's probe module): a factory call whose result is
     *  stored straight into the file class's static field. */
    @Test
    void captures_a_kotlin_top_level_val_written_from_a_factory() {
        MethodNode initialiser = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_STATIC, "<clinit>", "()V",
            null, null);
        initialiser.visitCode();
        initialiser.visitFieldInsn(org.objectweb.asm.Opcodes.GETSTATIC,
            "io/ktor/client/engine/cio/CIO", "INSTANCE", "Lio/ktor/client/engine/cio/CIO;");
        initialiser.visitTypeInsn(org.objectweb.asm.Opcodes.CHECKCAST,
            "io/ktor/client/engine/HttpClientEngineFactory");
        initialiser.visitMethodInsn(org.objectweb.asm.Opcodes.INVOKESTATIC,
            "io/ktor/client/HttpClientKt", "HttpClient",
            "(Lio/ktor/client/engine/HttpClientEngineFactory;)Lio/ktor/client/HttpClient;", false);
        initialiser.visitFieldInsn(org.objectweb.asm.Opcodes.PUTSTATIC,
            "probe/ProbeKt", "client", "Lio/ktor/client/HttpClient;");
        initialiser.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        initialiser.visitMaxs(1, 0);
        initialiser.visitEnd();

        List<String> lines = MethodFlow.fieldWrites("doc", "doc probe/ProbeKt#<clinit>(sig_cl).",
            initialiser);
        assertEquals(1, lines.size(), String.join("\n", lines));
        assertTrue(lines.get(0).contains("\"field\":\"probe/ProbeKt#client.\""), lines.get(0));
        // The invokestatic is instruction 2 — the same index its call site reports as `result`.
        assertTrue(lines.get(0).contains("\"value\":{\"kind\":\"unresolved\",\"source\":2}"),
            lines.get(0));
    }

    /** A {@code PUTSTATIC} of a CONSTANT carries the constant, exactly as {@code PUTFIELD}'s
     *  {@code ALOAD 0; LDC} does (CP-33 row 6's own {@code ldc; putstatic}). */
    @Test
    void captures_a_static_field_written_from_a_constant() {
        MethodNode initialiser = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_STATIC, "<clinit>", "()V",
            null, null);
        initialiser.visitCode();
        initialiser.visitLdcInsn("http://static-host/");
        initialiser.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTSTATIC, OWNER, "host", "Ljava/lang/String;");
        initialiser.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        initialiser.visitMaxs(1, 0);
        initialiser.visitEnd();

        List<String> lines = MethodFlow.fieldWrites("doc", "doc com/acme/Sample#<clinit>(sig_cl).",
            initialiser);
        assertEquals(1, lines.size(), String.join("\n", lines));
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#host.\""), lines.get(0));
        assertTrue(
            lines.get(0).contains("\"value\":{\"kind\":\"string\",\"value\":\"http://static-host/\"}"),
            lines.get(0));
    }

    /** A {@code PUTSTATIC} of a PARAMETER names it — and in a STATIC method parameter 0 is
     *  slot 0, which is the per-method {@code firstSlot} CP-33 row 5 called out. */
    @Test
    void captures_a_static_field_written_from_a_static_methods_parameter() {
        MethodNode setter = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_STATIC, "configure",
            "(JLjava/lang/String;)V", null, null);
        setter.visitCode();
        setter.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 2);
        setter.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTSTATIC, OWNER, "host", "Ljava/lang/String;");
        setter.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        setter.visitMaxs(1, 3);
        setter.visitEnd();

        List<String> lines = MethodFlow.fieldWrites("doc", "doc com/acme/Sample#configure(sig_c).",
            setter);
        assertEquals(1, lines.size(), String.join("\n", lines));
        assertTrue(lines.get(0).contains("\"field\":\"" + OWNER + "#host.\""), lines.get(0));
        assertTrue(lines.get(0).contains("\"from_parameter\":1"), lines.get(0));
    }

    /** **A write the same block overwrites is still dead, whatever its value.** The constant
     *  default is followed in one straight line by the factory's result, so only the second
     *  is reported — for {@code PUTSTATIC} and for a call-result {@code PUTFIELD} alike. */
    @Test
    void a_write_overwritten_in_the_same_block_emits_only_the_later_one() {
        MethodNode initialiser = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_STATIC, "<clinit>", "()V",
            null, null);
        initialiser.visitCode();
        initialiser.visitLdcInsn("default");
        initialiser.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTSTATIC, OWNER, "host", "Ljava/lang/String;");
        initialiser.visitMethodInsn(org.objectweb.asm.Opcodes.INVOKESTATIC,
            OWNER, "make", "()Ljava/lang/String;", false);
        initialiser.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTSTATIC, OWNER, "host", "Ljava/lang/String;");
        initialiser.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        initialiser.visitMaxs(1, 0);
        initialiser.visitEnd();
        List<String> statics = MethodFlow.fieldWrites("doc", "doc com/acme/Sample#<clinit>(sig_cl).",
            initialiser);
        assertEquals(1, statics.size(), String.join("\n", statics));
        assertTrue(statics.get(0).contains("\"source\":2"), statics.get(0));

        MethodNode constructor = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, 0, "<init>", "()V", null, null);
        constructor.visitCode();
        constructor.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        constructor.visitLdcInsn("default");
        constructor.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        constructor.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 0);
        constructor.visitMethodInsn(org.objectweb.asm.Opcodes.INVOKESTATIC,
            OWNER, "make", "()Ljava/lang/String;", false);
        constructor.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        constructor.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        constructor.visitMaxs(2, 1);
        constructor.visitEnd();
        List<String> fields = MethodFlow.fieldWrites("doc", SYMBOL, constructor);
        assertEquals(1, fields.size(), String.join("\n", fields));
        assertTrue(fields.get(0).contains("\"source\":4"), fields.get(0));
    }

    /** {@code other.f = make()} — a call's result written into ANOTHER object's field. The
     *  receiver is parameter 0, not {@code this}, so no fact: a read of the field elsewhere
     *  is about whichever object it is read on, and this write says nothing about it. */
    @Test
    void emits_nothing_for_another_objects_field_written_from_a_call() {
        MethodNode wire = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, 0, "wire",
            "(Ldev/sextant/extractor/ConstructorSample;)V", null, null);
        wire.visitCode();
        wire.visitVarInsn(org.objectweb.asm.Opcodes.ALOAD, 1);
        wire.visitMethodInsn(org.objectweb.asm.Opcodes.INVOKESTATIC,
            OWNER, "make", "()Ljava/lang/String;", false);
        wire.visitFieldInsn(org.objectweb.asm.Opcodes.PUTFIELD, OWNER, "url", "Ljava/lang/String;");
        wire.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        wire.visitMaxs(2, 2);
        wire.visitEnd();

        assertEquals(List.of(), MethodFlow.fieldWrites("doc", "doc com/acme/Sample#wire(sig_w).", wire));
    }

    /** {@code this.url = new String(built)} — the call right below the write is the
     *  CONSTRUCTOR, which returns nothing, so it is not what the field holds; the value is
     *  the {@code NEW}'s, and a {@code source} naming the {@code <init>} would join no call
     *  site's {@code result} at all. No fact: a constructed value is not this write's shape. */
    @Test
    void emits_nothing_for_a_value_built_with_new() throws Exception {
        assertEquals(List.of(), fieldWrites("(Ljava/lang/StringBuilder;)V"));
    }

    /** **A lambda is not a value** (ruled 2026-09-22). {@code static Runnable r = () -> …}
     *  stores an {@code invokedynamic}'s result, and the fact says nothing about it: what a
     *  reader would cross to is a body, never a value. */
    @Test
    void emits_nothing_for_a_static_field_holding_a_lambda() {
        org.objectweb.asm.Handle metafactory = new org.objectweb.asm.Handle(
            org.objectweb.asm.Opcodes.H_INVOKESTATIC, "java/lang/invoke/LambdaMetafactory",
            "metafactory",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;"
                + "Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;"
                + "Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;",
            false);
        org.objectweb.asm.Handle body = new org.objectweb.asm.Handle(
            org.objectweb.asm.Opcodes.H_INVOKESTATIC, OWNER, "lambda$static$0", "()V", false);
        MethodNode initialiser = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_STATIC, "<clinit>", "()V",
            null, null);
        initialiser.visitCode();
        initialiser.visitInvokeDynamicInsn("run", "()Ljava/lang/Runnable;", metafactory,
            org.objectweb.asm.Type.getType("()V"), body, org.objectweb.asm.Type.getType("()V"));
        initialiser.visitFieldInsn(
            org.objectweb.asm.Opcodes.PUTSTATIC, OWNER, "task", "Ljava/lang/Runnable;");
        initialiser.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        initialiser.visitMaxs(1, 0);
        initialiser.visitEnd();

        assertEquals(List.of(),
            MethodFlow.fieldWrites("doc", "doc com/acme/Sample#<clinit>(sig_cl).", initialiser));
    }

    /** **A value two branches merge AT the write emits nothing** (CP-33 row 9). javac's
     *  {@code host = prod ? "https://prod…" : "https://staging…"} ends each branch with its own
     *  {@code ldc} and joins them at the {@code putstatic}, so the instruction right below the
     *  write is the else branch's constant alone. Reported, it published a {@code resolved}
     *  staging address through a {@code RestTemplate} for a field that also holds the
     *  production one. Neither constant is the field's one value, so no fact. */
    @Test
    void a_java_ternary_of_two_constants_into_a_static_field_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("MergedWriteSample", "ternaryStatic", "(Z)V", "host"));
    }

    /** {@code host = getenv(k) != null ? getenv(k) : "https://default…"} — the lookup's result
     *  on one branch and a constant on the other. The constant is the one right below the
     *  write, and it is the value only when the lookup found nothing. */
    @Test
    void a_java_null_default_into_a_static_field_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("MergedWriteSample", "nullDefaultStatic", "()V", "host"));
    }

    /** {@code this.url = c ? make("x") : make("y")}: each branch ends with its own call, so the
     *  call right below the write is {@code make("y")}'s alone. The receiver is {@code this}
     *  on both branches, which the frame confirms; the VALUE is what is merged. */
    @Test
    void a_java_ternary_of_two_calls_into_this_field_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("MergedWriteSample", "ternaryField", "(Z)V", "url"));
    }

    /** {@code this.url = lookup() != null ? lookup() : make("default")} — the null-default
     *  with a call on both branches. */
    @Test
    void a_java_null_default_of_two_calls_into_this_field_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("MergedWriteSample", "nullDefaultField", "()V", "url"));
    }

    /** {@code this.url = (String) (c ? makeObject("x") : makeObject("y"))}: the branches join
     *  BEFORE the cast, so the cast is in the write's block and neither call is. The block
     *  compared is the CALL's, which the cast is looked through to reach. */
    @Test
    void a_cast_after_two_calls_join_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("MergedWriteSample", "castAfterTheJoin", "(Z)V", "url"));
    }

    /** {@code (c ? other : this).url = value} — the RECEIVER merged, the value not. The {@code
     *  aload_0} two below the write is the else branch's, and the then branch writes
     *  another object's field, which this fact never reports. */
    @Test
    void a_write_whose_receiver_two_branches_merge_emits_nothing() throws Exception {
        assertEquals(List.of(), writesInto("MergedWriteSample", "mergedReceiver",
            "(ZLdev/sextant/extractor/MergedWriteSample;Ljava/lang/String;)V", "url"));
    }

    /** **The near-miss: a branch BELOW the producer leaves the write reported.** {@code
     *  this.url = make(c ? "x" : "y")} merges the call's ARGUMENT, and the call itself is in the
     *  write's block, so the field holds that one call's result — which the call site's own
     *  argument grammar then reports as merged. */
    @Test
    void a_branch_in_the_calls_argument_leaves_the_write_reported() throws Exception {
        MethodNode writer = method("MergedWriteSample", "branchBelowTheCall", "(Z)V");
        List<String> lines = MethodFlow.fieldWrites("doc", SYMBOL, writer);
        assertEquals(1, lines.size(), String.join("\n", lines));
        int source = sourceOf(lines.get(0));
        assertTrue(MethodFlow.callSites("doc", SYMBOL, writer).stream()
            .anyMatch(site -> site.contains("\"name\":\"make\"")
                && site.contains("\"result\":" + source + ",")),
            "no call site whose result is " + source);
    }

    /** kotlinc's elvis into a top-level {@code val}: {@code getenv; dup; ifnonnull L; pop;
     *  ldc; L: putstatic}. The {@code ldc} is the value only when the lookup returned null.
     *  This is the {@code val envBase = getenv("PRICING_URL") ?: "https://default…"} read by
     *  {@code defaultRequest { url(envBase) }} that published the default as resolved. */
    @Test
    void a_kotlin_elvis_into_a_top_level_val_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("KotlinMergedWritesKt", "<clinit>", "()V", "elvisTop"));
    }

    /** kotlinc's {@code if} expression into a top-level {@code val}, a factory call on each
     *  branch — {@code val client = if (f) HttpClient {…} else HttpClient {…}}'s shape. The
     *  {@code val} beside it, written from one call, is still reported. */
    @Test
    void a_kotlin_if_expression_into_a_top_level_val_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("KotlinMergedWritesKt", "<clinit>", "()V", "chosenTop"));
        assertEquals(1,
            writesInto("KotlinMergedWritesKt", "<clinit>", "()V", "singleTop").size());
    }

    /** The elvis into a class property, a call on both sides: {@code putfield} from a call
     *  that is not the value on every path. */
    @Test
    void a_kotlin_elvis_of_two_calls_into_a_property_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("KotlinMergedHolder", "<init>", "(Z)V", "elvis"));
    }

    /** The {@code if} expression into a class property; its single-call neighbour stays
     *  reported, so the rule refuses the merge and nothing else in the constructor. */
    @Test
    void a_kotlin_if_expression_into_a_property_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("KotlinMergedHolder", "<init>", "(Z)V", "chosen"));
        assertEquals(1, writesInto("KotlinMergedHolder", "<init>", "(Z)V", "single").size());
    }

    /** **A parameter's SLOT is the parameter only where the method never stores to it.**
     *  {@code init(String given) { if (…) given = "https://fallback…"; host = given; }}: the
     *  load right below the {@code putstatic} reads slot 0, which holds the caller's argument
     *  on one path and the fallback on the other. Reported as {@code from_parameter: 0}, the
     *  caller's {@code "http://given…"} was published as the field's value. */
    @Test
    void a_parameter_reassigned_on_a_branch_into_a_static_field_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("ReassignedParameterSample", "init", "(Ljava/lang/String;)V", "host"));
    }

    /** {@code if (!given.endsWith("/")) given = given + "/"; this.base = given;} — the
     *  caller's {@code "…/api"} was joined as {@code /apiorders} where the field holds
     *  {@code /api/} on that path. */
    @Test
    void a_parameter_reassigned_on_a_branch_into_this_field_emits_nothing() throws Exception {
        assertEquals(List.of(), writesInto("ReassignedParameterSample", "normalise",
            "(Ljava/lang/String;)V", "base"));
    }

    /** {@code given = given.trim(); this.url = given;} — one straight line, so no block rule
     *  catches it: the slot holds the call's result, not the argument. D00 §5's "a value
     *  parked in a local first" emits nothing, and a parameter's own slot is such a local. */
    @Test
    void a_parameter_reassigned_in_one_straight_line_emits_nothing() throws Exception {
        assertEquals(List.of(), writesInto("ReassignedParameterSample", "trimmed",
            "(Ljava/lang/String;)V", "url"));
        assertEquals(List.of(), writesInto("ReassignedParameterSample", "trimmedStatic",
            "(Ljava/lang/String;)V", "host"));
    }

    /** {@code n++; count = n;} — {@code IINC} writes the slot as a store does. */
    @Test
    void a_parameter_incremented_in_place_emits_nothing() throws Exception {
        assertEquals(List.of(),
            writesInto("ReassignedParameterSample", "bumped", "(I)V", "count"));
    }

    /** **The near-misses.** An untouched parameter written into {@code this}'s field is
     *  still {@code from_parameter: 0}; and where ANOTHER parameter is reassigned, the one
     *  written is still reported — the rule is per slot, not per method. */
    @Test
    void an_untouched_parameter_is_still_reported() throws Exception {
        List<String> field = writesInto("ReassignedParameterSample", "untouched",
            "(Ljava/lang/String;)V", "kept");
        assertEquals(1, field.size(), String.join("\n", field));
        assertTrue(field.get(0).contains("\"from_parameter\":0"), field.get(0));
        List<String> statics = writesInto("ReassignedParameterSample", "otherReassigned",
            "(Ljava/lang/String;Ljava/lang/String;)V", "host");
        assertEquals(1, statics.size(), String.join("\n", statics));
        assertTrue(statics.get(0).contains("\"from_parameter\":0"), statics.get(0));
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
