package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

/** {@code CallSample.java} is compiled by Gradle's own test compilation, like
 *  {@code FieldSample.java} beside it, so every assertion here is about the
 *  bytecode javac actually emits rather than about bytecode this test wrote
 *  for itself. */
class MethodFlowTest {

    private static final String OWNER = "dev/sextant/extractor/CallSample";

    private static List<String> callSites(String methodName) throws Exception {
        ClassNode classNode = new ClassNode();
        try (InputStream in =
                MethodFlowTest.class.getResourceAsStream("/dev/sextant/extractor/CallSample.class")) {
            new ClassReader(in.readAllBytes()).accept(classNode, ClassReader.SKIP_FRAMES);
        }
        MethodNode method = classNode.methods.stream()
            .filter(candidate -> candidate.name.equals(methodName))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no method named " + methodName + " on CallSample"));
        String caller = new ClassScanner("com.acme/orders", "1.0.0")
            .symbolOf(OWNER + "#" + methodName + "(" + ClassScanner.disambiguatorOf(method.desc) + ").");
        return MethodFlow.callSites("doc-call-sample", caller, method);
    }

    /** The one field this test reads back rather than hardcoding: a value id is
     *  an instruction index, and pinning it would make the assertion about
     *  javac's label placement instead of about the join it is testing. */
    private static String field(String line, String name) {
        Matcher matcher = Pattern.compile("\"" + name + "\":(-?\\d+)").matcher(line);
        assertTrue(matcher.find(), "no " + name + " on " + line);
        return matcher.group(1);
    }

    @Test
    void captures_a_string_literal_argument() throws Exception {
        List<String> lines = callSites("stringLiteral");
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"arguments\":[{\"kind\":\"string\","
            + "\"value\":\"/billing/invoices\"}]"), lines.get(0));
    }

    /** The whole call-site fact for one real call, field by field: the target
     *  triple that makes it unambiguous, the dispatch form, the ordinal, the
     *  receiver and result value ids, and the caller symbol it links back to. */
    @Test
    void states_the_whole_fact_for_an_instance_call() throws Exception {
        String line = callSites("stringLiteral").get(0);
        assertTrue(line.contains("\"kind\":\"call_site\""), line);
        assertTrue(line.contains("\"document_id\":\"doc-call-sample\""), line);
        assertTrue(line.contains("\"caller\":\"sextant-jvm maven com.acme/orders 1.0.0 "
            + OWNER + "#stringLiteral("), line);
        assertTrue(line.contains("\"target\":{\"descriptor\":\"(Ljava/lang/String;)V\","
            + "\"name\":\"sink\",\"owner\":\"" + OWNER + "#\"}"), line);
        assertTrue(line.contains("\"invoke_kind\":\"virtual\""), line);
        assertTrue(line.contains("\"ordinal\":0"), line);
        assertTrue(line.contains("\"result\":null"), line);
        // `this`, loaded by the ALOAD that precedes the argument. Its id is an
        // instruction index — read back rather than pinned, because pinning it
        // would assert javac's label placement, not the receiver capture.
        assertTrue(Integer.parseInt(field(line, "receiver")) >= 0, line);
    }

    /** javac folds a compile-time constant before the pass ever sees it, so a
     *  URL assembled from a constant prefix is a plain LDC — which is the only
     *  reason a path built that way is recoverable at all. */
    @Test
    void captures_a_javac_folded_constant_as_the_string_it_folded_to() throws Exception {
        String line = callSites("foldedConstant").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"string\",\"value\":\"/api/x\"}]"), line);
    }

    /** A boolean and an int reach the stack through the same {@code ICONST_*}
     *  family; only the descriptor's argument type tells them apart, and
     *  reporting {@code true} as {@code 1} loses the distinction a flag carries. */
    @Test
    void captures_an_int_a_long_and_a_boolean_by_their_declared_argument_types() throws Exception {
        String line = callSites("primitives").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"int\",\"value\":7},"
            + "{\"kind\":\"long\",\"value\":9000000000},"
            + "{\"kind\":\"boolean\",\"value\":true}]"), line);
    }

    /** An enum constant is a symbol reference, not a bare name: `FAST` alone
     *  says nothing about which closed set it belongs to. */
    @Test
    void captures_an_enum_constant_as_a_symbol_reference() throws Exception {
        String line = callSites("enumConstant").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"enum\","
            + "\"symbol\":\"" + OWNER + "$Mode#FAST.\"}]"), line);
    }

    @Test
    void captures_a_class_literal_as_a_symbol_reference() throws Exception {
        String line = callSites("classLiteral").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"class\","
            + "\"symbol\":\"" + OWNER + "#\"}]"), line);
    }

    @Test
    void captures_an_explicit_null_argument() throws Exception {
        String line = callSites("nullArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"null\"}]"), line);
    }

    /** An argument the pass cannot resolve is `unresolved` with nothing else —
     *  never an omitted slot, which would silently renumber every argument
     *  after it. A method parameter has no producing call, so no `source`. */
    @Test
    void reports_a_variable_argument_as_unresolved_with_no_source() throws Exception {
        String line = callSites("variableArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
    }

    /** The rule the whole choice of {@code SourceInterpreter} rests on: after a
     *  branch merges, the slot has two producing instructions and no single
     *  answer. Both are string literals, so a pass that took "the first one" or
     *  "any one" would emit a confident, wrong URL — and would look right in
     *  every test that only ever sees straight-line code. */
    @Test
    void reports_a_branch_merged_argument_as_unresolved_with_no_source() throws Exception {
        String line = callSites("conditionalArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
        // Neither branch's literal leaked into the fact.
        assertTrue(!line.contains("/a") && !line.contains("/b"), line);
    }

    /** The join that makes a split builder chain reconstructable: the argument
     *  is unresolved as a value, and still names the call that produced it. */
    @Test
    void names_the_producing_call_when_an_argument_is_another_calls_result() throws Exception {
        List<String> lines = callSites("callResult");
        assertEquals(2, lines.size());
        String producer = lines.get(0);
        String consumer = lines.get(1);
        assertTrue(producer.contains("\"name\":\"source\""), producer);
        assertTrue(consumer.contains("\"arguments\":[{\"kind\":\"unresolved\",\"source\":"
            + field(producer, "result") + "}]"), consumer);
    }

    @Test
    void leaves_the_receiver_null_on_a_static_call() throws Exception {
        String line = callSites("staticCall").get(0);
        assertTrue(line.contains("\"invoke_kind\":\"static\""), line);
        assertTrue(line.contains("\"receiver\":null"), line);
    }

    /** Chain reconstruction is a within-method join on these ids: the receiver
     *  of each hop is the previous hop's result, and nothing about it depends
     *  on the two calls sitting next to each other in the source. */
    @Test
    void links_each_hop_of_a_chain_to_the_previous_hops_result() throws Exception {
        List<String> lines = callSites("chain");
        assertEquals(3, lines.size());
        assertEquals(field(lines.get(0), "result"), field(lines.get(1), "receiver"));
        assertEquals(field(lines.get(1), "result"), field(lines.get(2), "receiver"));
    }

    /** The v1 control-flow position: assigned in instruction order, so two
     *  calls in one method are never the same call site. */
    @Test
    void numbers_the_invokes_of_one_method_in_instruction_order() throws Exception {
        List<String> lines = callSites("chain");
        assertTrue(lines.get(0).contains("\"ordinal\":0"), lines.get(0));
        assertTrue(lines.get(1).contains("\"ordinal\":1"), lines.get(1));
        assertTrue(lines.get(2).contains("\"ordinal\":2"), lines.get(2));
    }

    /** NFR-1: two runs over the same bytes emit the same lines. Value ids are
     *  instruction indices and every key is written from a sorted map, so
     *  there is no set iteration order left to leak into the output. */
    @Test
    void emits_identical_lines_when_the_same_method_is_analysed_twice() throws Exception {
        assertEquals(callSites("chain"), callSites("chain"));
        assertEquals(callSites("primitives"), callSites("primitives"));
    }

    /** The pass runs where the method symbol is minted, so a call site is a
     *  line of the same fact file as its caller, carrying the same document. */
    @Test
    void class_scanner_emits_call_sites_beside_the_method_symbols_they_belong_to() throws Exception {
        try (InputStream in =
                MethodFlowTest.class.getResourceAsStream("/dev/sextant/extractor/CallSample.class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-call-sample");
            assertTrue(lines.stream().anyMatch(line -> line.contains("\"kind\":\"call_site\"")
                && line.contains("\"document_id\":\"doc-call-sample\"")
                && line.contains("#stringLiteral(")
                && line.contains("\"value\":\"/billing/invoices\"")), String.join("\n", lines));
        }
    }

    /** An LDC of a {@code MethodType} constant — legal in any class file since
     *  Java 7 — is a {@code Type} whose sort is neither OBJECT nor ARRAY, and
     *  reading it as a class constant reaches ASM's {@code getClassName()},
     *  which throws an {@code AssertionError}. An Error escapes {@code Main}'s
     *  {@code catch (Exception)}, so one such constant anywhere on the classpath
     *  would end the whole extraction with no fact files and no failure message.
     *  Every other class's facts, lost to one constant pool entry.
     *
     *  <p>Built by hand rather than compiled: no Java source javac accepts puts
     *  a bare MethodType in an argument slot, which is exactly why the crash
     *  survived a fixture-driven suite. */
    @Test
    void reports_a_method_type_constant_as_unresolved_rather_than_dying_on_it() {
        MethodNode method = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_STATIC,
            "loads", "()V", null, null);
        method.visitCode();
        method.visitLdcInsn(org.objectweb.asm.Type.getMethodType("()V"));
        method.visitMethodInsn(org.objectweb.asm.Opcodes.INVOKESTATIC, "o/P", "consume",
            "(Ljava/lang/Object;)V", false);
        method.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        method.visitMaxs(1, 0);
        method.visitEnd();

        List<String> lines =
            MethodFlow.callSites("doc", "sextant-jvm maven c v o/P#loads().", method);
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), lines.get(0));
    }

    /** A method with no body — an interface method, an abstract one — has no
     *  frames to walk and must not stop the scan. */
    @Test
    void emits_nothing_for_a_method_with_no_body() {
        MethodNode abstractMethod = new MethodNode(
            org.objectweb.asm.Opcodes.ASM9, org.objectweb.asm.Opcodes.ACC_ABSTRACT,
            "missing", "()V", null, null);
        assertEquals(List.of(), MethodFlow.callSites("doc", "sextant-jvm maven c v o/P#missing().",
            abstractMethod));
    }
}
