package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
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

    private static MethodNode methodNode(String methodName) throws Exception {
        ClassNode classNode = new ClassNode();
        try (InputStream in =
                MethodFlowTest.class.getResourceAsStream("/dev/sextant/extractor/CallSample.class")) {
            new ClassReader(in.readAllBytes()).accept(classNode, ClassReader.SKIP_FRAMES);
        }
        return classNode.methods.stream()
            .filter(candidate -> candidate.name.equals(methodName))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no method named " + methodName + " on CallSample"));
    }

    private static String symbolOf(MethodNode method) {
        return new ClassScanner("com.acme/orders", "1.0.0")
            .symbolOf(OWNER + "#" + method.name + "(" + ClassScanner.disambiguatorOf(method.desc) + ").");
    }

    private static List<String> callSites(String methodName) throws Exception {
        MethodNode method = methodNode(methodName);
        return MethodFlow.callSites("doc-call-sample", symbolOf(method), method);
    }

    private static List<String> methodReturns(String methodName) throws Exception {
        MethodNode method = methodNode(methodName);
        return MethodFlow.methodReturns("doc-call-sample", symbolOf(method), method);
    }

    private static String last(List<String> lines) {
        return lines.get(lines.size() - 1);
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
        // `this` has no producing instruction: it was already in local 0 before
        // the first bytecode ran. The ALOAD that pushes a copy of it is not its
        // origin, so the receiver is null rather than that load's index.
        assertTrue(line.contains("\"receiver\":null"), line);
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

    /** The ordering pin: {@code BigDecimal.ZERO} takes the exact enum-constant
     *  shape (a GETSTATIC of a field typed as its own owner) on a class that
     *  declares no {@code ACC_ENUM} at all, so it must still read {@code enum}
     *  rather than fall through to the {@code field} branch that follows it —
     *  the enum check has to run first, and this is what would break first if
     *  it did not. */
    @Test
    void keeps_reading_big_decimal_zero_as_enum_even_though_it_is_not_a_language_enum()
            throws Exception {
        String line = callSites("bigDecimalZeroArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"enum\","
            + "\"symbol\":\"java/math/BigDecimal#ZERO.\"}]"), line);
    }

    /** A GETFIELD that is not the enum-constant shape — D00 §5's {@code field}
     *  kind, the cross-language "this argument reads a declared field"
     *  contract. Strictly additive: before this, the slot read as {@code
     *  unresolved}. */
    @Test
    void captures_a_field_read_as_a_symbol_reference() throws Exception {
        String line = callSites("fieldArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"field\","
            + "\"symbol\":\"" + OWNER + "#url.\"}]"), line);
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

    /** The caller was handed this value: D00 §5's `parameter` kind, carrying
     *  the parameter's own index.
     *
     *  <p>It read `unresolved` until 2G, which made it indistinguishable from a
     *  slot the pass genuinely could not read — javac's synthesized varargs
     *  array is the neighbour it sat beside, spelled identically — and a
     *  payload the caller supplies is exactly the case a parse-call binding has
     *  to follow. No `source`: a parameter is produced by no call in this
     *  method, and that stays true. */
    @Test
    void names_the_parameter_an_argument_was_handed_straight_from() throws Exception {
        String line = callSites("variableArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"parameter\",\"value\":0}]"), line);
    }

    /** Capability 9.19 (spec 2026-10-21-merged-values-design.md): a parameter REASSIGNED
     *  on one branch reaches the consuming call with two producers — the parameter marker
     *  and the {@code substring} call's result — and the fact now writes BOTH as
     *  candidates rather than collapsing to a bare {@code unresolved} with no source. The
     *  order is instruction order with the marker (which indexes nothing) first; nothing
     *  is chosen; the second candidate keeps its {@code source} so the walk can see which
     *  call produced it, which is the whole of the root check. */
    @Test
    void writes_every_producer_of_a_merged_value_as_a_candidate() throws Exception {
        String line = last(callSites("reassignedOnABranch"));
        assertTrue(line.contains("\"kind\":\"merge\""), line);
        assertTrue(line.contains("\"candidates\":[{\"kind\":\"parameter\",\"value\":0},"
                                 + "{\"kind\":\"unresolved\",\"source\":"), line);
        assertFalse(line.contains("\"candidates\":[{\"kind\":\"unresolved\"}"), line);
    }

    /** A static method's parameter 0 is local slot 0 — where an instance
     *  method keeps `this`. Reading the slot as the index (or assuming the
     *  instance offset) misnames every argument of every static call. */
    @Test
    void counts_a_static_methods_parameters_from_slot_zero() throws Exception {
        String line = callSites("staticVariableArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"parameter\",\"value\":0}]"), line);
    }

    /** `long id` occupies slots 1 and 2, so `label` starts at slot 3 while
     *  being parameter 1. The fact names the index — the same slot/index
     *  distinction `field_write` pins, and the one a consumer joins on. */
    @Test
    void maps_a_two_slot_leading_parameter_to_the_right_parameter_index() throws Exception {
        String line = callSites("wideLeadingParameter").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"parameter\",\"value\":1}]"), line);
    }

    /** A parameter parked in a local and read back is still the parameter: the
     *  store and the reload relocate a value without producing one, so the
     *  answer must not depend on whether a method wrote the argument inline. */
    @Test
    void keeps_naming_the_parameter_across_a_store_and_a_reload() throws Exception {
        String line = callSites("parameterThroughLocal").get(0);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"parameter\",\"value\":0}]"), line);
    }

    /** Two different parameters merged on a branch are two producers, and naming
     *  either would be a fact about a path that may never run, exactly as it
     *  would for two literals. Since capability 9.19 the fact names BOTH as
     *  candidates and chooses neither — the ruling that such a merge resolves
     *  to nothing lives at the walk (spec 2026-10-21-merged-values-design.md
     *  §3b: no common root, `unresolved`), where it can also see the one case
     *  it should not refuse. */
    @Test
    void reports_two_merged_parameters_as_candidates_choosing_neither() throws Exception {
        String line = callSites("mergedParameters").get(0);
        assertTrue(line.contains("\"arguments\":[{\"candidates\":[{\"kind\":\"parameter\",\"value\":2},"
            + "{\"kind\":\"parameter\",\"value\":1}],\"kind\":\"merge\"}]"), line);
    }

    /** A parameter merged with a literal is two producers. 9.8 reported
     *  `/default` here, because a parameter contributed no producer at all and
     *  the literal was left standing alone: a fact about the else-branch,
     *  asserted for an argument that is the parameter whenever the condition
     *  holds. Since 9.19 both stand as candidates and the literal never stands
     *  ALONE as the argument — which is the leak this test exists to catch. */
    @Test
    void reports_a_parameter_merged_with_a_literal_as_two_candidates() throws Exception {
        String line = callSites("mergedParameterAndLiteral").get(0);
        assertTrue(line.contains("\"candidates\":[{\"kind\":\"parameter\",\"value\":1},"
            + "{\"kind\":\"string\",\"value\":\"/default\"}],\"kind\":\"merge\""), line);
        assertFalse(line.contains("\"arguments\":[{\"kind\":\"string\",\"value\":\"/default\"}]"), line);
    }

    /** `this` sits in slot 0 of an instance method and is a parameter of no
     *  descriptor, so it names no index and stays the honest `unresolved` —
     *  never parameter 0, which belongs to the first declared parameter.
     *
     *  <p>Both calls are asserted together because one without the other
     *  proves nothing: the parameter's own call fixes slot 1 as index 0, so a
     *  pass reading slots as indices would have to call `this` parameter 0 to
     *  satisfy the second assertion and fail the first. */
    @Test
    void reports_this_as_unresolved_beside_the_parameter_that_occupies_slot_one()
            throws Exception {
        List<String> lines = callSites("selfArgument");
        assertTrue(lines.get(0).contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), lines.get(0));
        assertTrue(lines.get(1).contains("\"arguments\":[{\"kind\":\"parameter\",\"value\":0}]"),
                   lines.get(1));
    }

    /** The rule the whole choice of {@code SourceInterpreter} rests on: after a
     *  branch merges, the slot has two producing instructions and no single
     *  answer. Both are string literals, so a pass that took "the first one" or
     *  "any one" would emit a confident, wrong URL — and would look right in
     *  every test that only ever sees straight-line code. Since 9.19 both are
     *  written, as CANDIDATES of a merge, and neither stands alone as the
     *  argument: the fact says "one of these" and the choice is nobody's. */
    @Test
    void reports_a_branch_merged_argument_as_two_candidates_and_picks_neither() throws Exception {
        String line = callSites("conditionalArgument").get(0);
        assertTrue(line.contains("\"arguments\":[{\"candidates\":[{\"kind\":\"string\",\"value\":\"/a\"},"
            + "{\"kind\":\"string\",\"value\":\"/b\"}],\"kind\":\"merge\"}]"), line);
        assertFalse(line.contains("\"arguments\":[{\"kind\":\"string\""), line);
    }

    /** Transparency must not turn a branch merge into a confident answer. A
     *  local assigned on two paths still reaches the invoke with two producing
     *  instructions — the store and the reload no longer collapse them into
     *  one — so the slot carries both as candidates and neither literal stands
     *  alone. This is the case that would break first if the interpreter had
     *  made copies transparent by *picking* a source rather than by passing the
     *  whole set through. */
    @Test
    void reports_a_branch_merged_local_as_two_candidates_after_a_store_and_a_reload()
            throws Exception {
        String line = callSites("conditionalThroughLocal").get(0);
        assertTrue(line.contains("\"candidates\":[{\"kind\":\"string\",\"value\":\"/a\"},"
            + "{\"kind\":\"string\",\"value\":\"/b\"}],\"kind\":\"merge\""), line);
        assertFalse(line.contains("\"arguments\":[{\"kind\":\"string\""), line);
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

    /** A lambda's code is not at the call site: javac lifts the body into a
     *  synthetic method and the call site only names it, through the second
     *  bootstrap argument of a {@code LambdaMetafactory} invokedynamic. */
    @Test
    void captures_a_lambda_argument_as_the_symbol_of_the_body_javac_lifted_out() throws Exception {
        String line = last(callSites("lambdaArgument"));
        assertTrue(line.contains("\"name\":\"forEach\""), line);
        assertTrue(line.contains("\"kind\":\"lambda\",\"source\":"), line);
        assertNamesLambdaOf(line, "symbol", "lambdaArgument");
    }

    /** `value -> sink(value)` reads `this` (sink is an instance method), so javac makes
     *  an INSTANCE synthetic method and passes `this` as the indy's one argument: one
     *  captured value, and it became the receiver, not a parameter — `captures` is 0. */
    @Test
    void counts_a_captured_this_as_no_leading_parameter() throws Exception {
        String line = last(callSites("lambdaArgument"));
        assertTrue(line.contains("\"captures\":0,\"kind\":\"lambda\""), line);
    }

    @Test
    void counts_a_captured_local_as_one_leading_parameter() throws Exception {
        String line = last(callSites("lambdaCapturingLocal"));
        assertTrue(line.contains("\"captures\":1,\"kind\":\"lambda\""), line);
    }

    @Test
    void counts_nothing_for_a_lambda_that_captures_nothing() throws Exception {
        String line = last(callSites("lambdaCapturingNothing"));
        assertTrue(line.contains("\"captures\":0,\"kind\":\"lambda\""), line);
    }

    /** `this::sink`: the bound receiver is the indy's one argument and the handle is
     *  `H_INVOKEVIRTUAL`, so it becomes the body's `this` — `captures` 0, and `sink`'s
     *  own parameter is the interface's parameter 0. */
    @Test
    void counts_a_bound_method_references_receiver_as_no_leading_parameter() throws Exception {
        String line = last(callSites("methodReferenceArgument"));
        assertTrue(line.contains("\"captures\":0,\"kind\":\"lambda\""), line);
    }

    /** `String::trim` is UNBOUND: the indy carries no argument and the handle is an
     *  instance kind, so the interface's first parameter becomes the body's receiver.
     *  `captures` is -1 — the interface's parameter k is the body's parameter k-1, and
     *  parameter 0 is no parameter of the body at all. */
    @Test
    void reports_minus_one_for_an_unbound_instance_method_reference() throws Exception {
        String line = last(callSites("jdkMethodReferenceArgument"));
        assertTrue(line.contains("\"captures\":-1,\"kind\":\"lambda\""), line);
    }

    /** Capability 9.17, on the site itself rather than on a slot that happens
     *  to hold it: a `dynamic` call site names the body its dispatch will run.
     *  Before it, a traversal following call targets stopped at
     *  `LambdaMetafactory` and every statement inside the lambda — a
     *  `mapper.insert` among them — was extracted into a synthetic method that
     *  nothing referenced. */
    @Test
    void names_the_lambda_body_a_dynamic_site_will_dispatch_into() throws Exception {
        String line = callSites("lambdaArgument").get(0);
        assertTrue(line.contains("\"invoke_kind\":\"dynamic\""), line);
        assertNamesLambdaOf(line, "implementation", "lambdaArgument");
        // The bootstrap is still recorded, and must be: it is what says this
        // site is a lambda at all, where the body alone does not.
        assertTrue(line.contains("\"owner\":\"java/lang/invoke/LambdaMetafactory#\""), line);
    }

    /** The gap the `lambda` argument kind cannot close, which is why 9.17 is a
     *  field on the site rather than a wider read of arguments: a returned
     *  lambda fills no argument slot, so nothing in this method's facts carried
     *  its body before — the assertion below is that the `lambda` kind is
     *  genuinely absent here, not merely elsewhere. */
    @Test
    void names_the_body_of_a_lambda_that_fills_no_argument_slot() throws Exception {
        List<String> lines = callSites("returnedLambda");
        assertEquals(1, lines.size());
        String line = lines.get(0);
        assertNamesLambdaOf(line, "implementation", "returnedLambda");
        assertFalse(line.contains("\"kind\":\"lambda\""), line);
    }

    /** The near-miss, and the reason `implementationOf` asks the bootstrap
     *  rather than the opcode: **not every invokedynamic is a lambda**. A
     *  string concatenation's bootstrap arguments are a format recipe and its
     *  constants — there is no implementation method, so naming one would
     *  assert a call to code that does not exist.
     *
     *  <p>Paired with a positive in the same body, because a rule that matched
     *  nothing would pass the negative half forever: the site IS a real
     *  `dynamic` call site with a `StringConcatFactory` bootstrap, and the
     *  lambda case above still fires. */
    @Test
    void names_no_body_for_an_invokedynamic_that_bootstraps_no_method() throws Exception {
        String line = callSites("concatenated").get(0);
        assertTrue(line.contains("\"invoke_kind\":\"dynamic\""), line);
        assertTrue(line.contains("\"owner\":\"java/lang/invoke/StringConcatFactory#\""), line);
        assertFalse(line.contains("\"implementation\""), line);
    }

    /** The other near-miss: an ordinary invoke's `target` already names its
     *  callee, so a second field saying the same thing would be a claim
     *  duplicated in two places that can disagree. The key is absent — not
     *  null — on every call site but a lambda's. */
    @Test
    void names_no_body_for_an_ordinary_call_whose_target_already_is_one() throws Exception {
        assertFalse(callSites("stringLiteral").get(0).contains("\"implementation\""),
                    callSites("stringLiteral").get(0));
    }

    /** D00 §1's stability rule again, at the new field: `implementation` is the
     *  same **bare** descriptor path the `lambda` argument kind emits, so
     *  `String::trim` is one symbol in every module that writes it. The cost is
     *  stated in D00 §5 rather than discovered later — an in-module body joins
     *  to its own method fact by stripping that fact's module prefix, which is
     *  what every consumer of these symbols already does. */
    @Test
    void names_a_jdk_body_without_stamping_the_callers_coordinates_on_it() throws Exception {
        String line = callSites("jdkMethodReferenceArgument").get(0);
        assertTrue(line.contains("\"implementation\":\"java/lang/String#trim(sig_"), line);
        assertFalse(line.contains("com.acme/orders 1.0.0 java/lang/String"), line);
    }

    /** A method reference bootstraps identically and names the referenced
     *  method itself — there is no synthetic body to lift. */
    @Test
    void captures_a_method_reference_argument_as_the_referenced_method() throws Exception {
        String line = last(callSites("methodReferenceArgument"));
        assertTrue(line.contains("\"kind\":\"lambda\",\"source\":"), line);
        assertTrue(line.contains("\"symbol\":\"" + OWNER + "#sink(sig_"), line);
    }

    /** D00 §1's stability rule, at the one kind most likely to break it: a
     *  method reference is very often into a library, and "two modules seeing
     *  the same library type produce the same string" fails the moment the
     *  *caller's* module coordinates are stamped onto `java/lang/String`. Every
     *  module that writes {@code String::trim} would then mint a different
     *  symbol for it, and none would join to another's. The bare descriptor
     *  path is what the `class`, `enum` and `instance` kinds beside it emit,
     *  and it is what this emits too. */
    @Test
    void names_a_jdk_method_reference_without_stamping_the_callers_coordinates_on_it()
            throws Exception {
        String line = last(callSites("jdkMethodReferenceArgument"));
        assertTrue(line.contains("\"kind\":\"lambda\",\"source\":"), line);
        assertTrue(line.contains("\"symbol\":\"java/lang/String#trim(sig_"), line);
        // The prefix is the whole point: not merely "starts with the right
        // path", but that the module's own coordinates appear nowhere in it.
        assertTrue(!line.contains("com.acme/orders 1.0.0 java/lang/String"), line);
    }

    /** The value an argument slot holds after {@code NEW; DUP; <init>} is the
     *  one the {@code NEW} pushed — the constructor returns void and produces
     *  no value at all — so the {@code NEW} is the instruction that names the
     *  concrete type. That type is what D00 §5a's PTR carrier and D02's
     *  one-hop body follow both read. */
    @Test
    void captures_a_constructed_argument_as_the_type_the_new_named() throws Exception {
        // The constructor is a call site of its own and comes first; the call
        // that *takes* the constructed value is the one under test.
        List<String> lines = callSites("instanceArgument");
        assertEquals(2, lines.size());
        assertTrue(lines.get(0).contains("\"name\":\"<init>\""), lines.get(0));
        String line = lines.get(1);
        assertTrue(line.contains("\"name\":\"hold\""), line);
        assertTrue(line.contains("\"kind\":\"instance\""), line);
        assertTrue(line.contains("\"symbol\":\"" + OWNER + "$Holder#\""), line);
    }

    /** D02 §2h's one-hop body follow, made a join rather than a search: the
     *  constructed value's id, the id its `<init>` site reports as receiver,
     *  and the `source` on the argument that carries it are one number. All
     *  three name the {@code NEW}.
     *
     *  <p>They agree only because the interpreter is copy-transparent. ASM's
     *  own {@code SourceInterpreter} attributes the duplicated value to the
     *  {@code DUP}, so the constructor's receiver named the stack shuffle while
     *  the enclosing call named the NEW — two ids for one object, and a
     *  consumer left matching by proximity, which is exactly what D00 §5
     *  refuses everywhere else. */
    @Test
    void gives_a_constructed_value_one_id_across_its_constructor_and_its_consumer()
            throws Exception {
        List<String> lines = callSites("instanceArgument");
        String constructor = lines.get(0);
        String consumer = lines.get(1);
        assertTrue(constructor.contains("\"name\":\"<init>\""), constructor);
        assertTrue(consumer.contains("\"arguments\":[{\"kind\":\"instance\",\"source\":"
            + field(constructor, "receiver") + ","), consumer);
    }

    /** An invokedynamic is a call site (D00 §5's {@code dynamic} dispatch
     *  form). It has no receiver to own it, so `target.owner` names the
     *  **bootstrap method's** owner — the thing that says what the site means,
     *  {@code StringConcatFactory} here. */
    @Test
    void states_the_whole_fact_for_an_invokedynamic() throws Exception {
        String line = callSites("concatenated").get(0);
        assertTrue(line.contains("\"invoke_kind\":\"dynamic\""), line);
        assertTrue(line.contains("\"target\":{\"descriptor\":"), line);
        assertTrue(line.contains("\"name\":\"makeConcatWithConstants\","
            + "\"owner\":\"java/lang/invoke/StringConcatFactory#\"}"), line);
        assertTrue(line.contains("\"ordinal\":0"), line);
        assertTrue(line.contains("\"receiver\":null"), line);
        assertTrue(Integer.parseInt(field(line, "result")) >= 0, line);
    }

    /** The chain join across an indy, and W4's change to what the value itself
     *  says.
     *
     *  <p>This asserted `unresolved` until W4: the concatenation's literal parts
     *  were in the class file, in the bootstrap's recipe, and were thrown away —
     *  so an address assembled from pieces reached a catalog naming nothing.
     *  The value is now the TEMPLATE, `order-{}`, with a hole where the runtime
     *  value goes.
     *
     *  <p>The join is unchanged and still asserted here, because the template
     *  says only WHERE the hole is: what fills it is the concat site's own
     *  call-site fact, reached by `source` -> `result`. */
    @Test
    void names_the_producing_invokedynamic_when_an_argument_is_its_result() throws Exception {
        List<String> lines = callSites("concatenated");
        assertEquals(2, lines.size());
        assertTrue(lines.get(1).contains("\"name\":\"sink\""), lines.get(1));
        assertTrue(lines.get(1).contains("\"arguments\":[{\"kind\":\"concat\",\"source\":"
            + field(lines.get(0), "result") + ",\"value\":\"order-{}\"}]"), lines.get(1));
    }

    /** The join Task 12's terminal needs on honest code. Nobody writes
     *  {@code client.newCall(new Request.Builder()….build())} in one expression;
     *  they store the request in a local first, and a store followed by a
     *  reload is not where that value came from. With the copy instructions
     *  transparent the argument names {@code second()}'s result — the call that
     *  actually built it — and the split chain reconstructs. */
    @Test
    void links_a_stored_and_reloaded_value_to_the_call_that_built_it() throws Exception {
        List<String> lines = callSites("storedThenConsumed");
        assertEquals(3, lines.size());
        String builder = lines.get(1);
        String consumer = lines.get(2);
        assertTrue(builder.contains("\"name\":\"second\""), builder);
        assertTrue(consumer.contains("\"name\":\"consume\""), consumer);
        assertTrue(consumer.contains("\"arguments\":[{\"kind\":\"unresolved\",\"source\":"
            + field(builder, "result") + "}]"), consumer);
    }

    /** A receiver that arrives as a parameter still has no producing instruction, so
     *  `receiver` stays null — and the fact now also says WHICH parameter it is, the
     *  same index the argument grammar has carried since capability 9.8. */
    @Test
    void names_the_parameter_a_receiver_was_handed_straight_from() throws Exception {
        List<String> lines = callSites("parameterReceiver");
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"receiver\":null"), lines.get(0));
        assertTrue(lines.get(0).contains("\"receiver_parameter\":0"), lines.get(0));
    }

    @Test
    void counts_a_static_methods_parameter_receiver_from_slot_zero() throws Exception {
        String line = callSites("staticParameterReceiver").get(0);
        assertTrue(line.contains("\"receiver_parameter\":0"), line);
    }

    @Test
    void maps_a_receiver_after_a_two_slot_parameter_to_the_right_index() throws Exception {
        String line = callSites("wideParameterReceiver").get(0);
        assertTrue(line.contains("\"receiver_parameter\":1"), line);
    }

    /** A receiver produced by a call carries `receiver` and NO `receiver_parameter`:
     *  the key is written only where there is a parameter to name. */
    @Test
    void writes_no_receiver_parameter_where_the_receiver_is_a_calls_result() throws Exception {
        String line = last(callSites("chain"));
        assertFalse(line.contains("receiver_parameter"), line);
    }

    @Test
    void leaves_the_receiver_null_on_a_static_call() throws Exception {
        String line = callSites("staticCall").get(0);
        assertTrue(line.contains("\"invoke_kind\":\"static\""), line);
        assertTrue(line.contains("\"receiver\":null"), line);
    }

    /** `this` is slot 0 of an instance method and a parameter of neither the descriptor
     *  nor D00 §5's numbering, and a static call has no receiver at all: neither writes
     *  the key. A walk reading `receiver_parameter` as "the lambda's own parameter" must
     *  never see one on a `this`-receiver call. */
    @Test
    void writes_no_receiver_parameter_for_this_or_for_a_static_call() throws Exception {
        String onThis = callSites("stringLiteral").get(0);
        assertTrue(onThis.contains("\"name\":\"sink\""), onThis);
        assertFalse(onThis.contains("receiver_parameter"), onThis);
        String stat = callSites("staticCall").get(0);
        assertFalse(stat.contains("receiver_parameter"), stat);
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

    /** WebClient's and RestClient's own real bytecode: a mid-chain hop
     *  inherited from a generic self-type interface returns the erased bound,
     *  not the caller's own narrower static type, so javac bridges the gap
     *  with a {@code CHECKCAST} — {@code CallSample.checkcastBridgedChain}
     *  reproduces the exact shape (confirmed by {@code javap} against
     *  {@code RestClient.RequestBodyUriSpec.uri} / {@code .body}: the same
     *  cast, the same one-hop gap). A cast does not build a new object, only
     *  a new static type for the same reference, so the join must survive it
     *  exactly as {@link #links_each_hop_of_a_chain_to_the_previous_hops_result}
     *  proves it survives a load/store/dup — without this, every fluent
     *  chain whose middle sets a request body (WebClient's {@code bodyValue},
     *  RestClient's {@code body}) would silently stop deriving one hop early. */
    @Test
    void links_a_checkcast_bridged_hop_to_the_previous_hops_result() throws Exception {
        List<String> lines = callSites("checkcastBridgedChain");
        assertEquals(2, lines.size());
        assertTrue(lines.get(0).contains("\"name\":\"uri\""), lines.get(0));
        assertTrue(lines.get(1).contains("\"name\":\"body\""), lines.get(1));
        assertEquals(field(lines.get(0), "result"), field(lines.get(1), "receiver"));
    }

    /** Coordinator fix round 1: pins that {@code CHECKCAST}'s new
     *  transparency is narrow, not a fully-transparent {@code
     *  unaryOperation} (which the reviewer confirmed still passes every
     *  other test in this suite). {@code box} is a method parameter — no
     *  producing instruction, so its own id is absent (`"receiver":null`,
     *  the same rule {@link #names_the_parameter_a_receiver_was_handed_straight_from}
     *  pins) — and a {@code GETFIELD} genuinely computes a new value from
     *  the object it reads, so {@code third()}'s own receiver must be that
     *  {@code GETFIELD}'s own real id, never {@code box}'s absent one. */
    @Test
    void leaves_a_getfield_sourced_receiver_with_its_own_id_not_the_objects() throws Exception {
        String line = callSites("getfieldSourcedReceiver").get(0);
        assertTrue(line.contains("\"name\":\"third\""), line);
        assertTrue(!line.contains("\"receiver\":null"), line);
        assertTrue(Integer.parseInt(field(line, "receiver")) >= 0, line);
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

    /** Capability 9.15's happy path. The value reaching a `String...` slot is
     *  the array the {@code ANEWARRAY} produced, so before this capability both
     *  literals were absent from the fact stream entirely and the arity was
     *  unreadable — one `unresolved` says nothing about whether a flow consumes
     *  one queue or twenty (measured:
     *  `scripts/probes/spring-integration-destinations.md`). */
    @Test
    void reads_the_elements_of_a_varargs_array_argument() throws Exception {
        String line = last(callSites("varargsLiterals"));
        assertTrue(line.contains("\"arguments\":[{\"elements\":["
            + "{\"kind\":\"string\",\"value\":\"orders.queue\"},"
            + "{\"kind\":\"string\",\"value\":\"orders.retry.queue\"}],\"kind\":\"array\"}]"), line);
    }

    /** The element list is the point: one argument that happens to be an array,
     *  with its contents beside it, never N arguments. A consumer reading
     *  arity off `arguments` must still see the ONE slot the descriptor
     *  declares — unpacking would renumber every slot after it. */
    @Test
    void keeps_a_varargs_array_as_one_argument_slot() throws Exception {
        String line = last(callSites("varargsLiterals"));
        assertTrue(line.contains("\"descriptor\":\"([Ljava/lang/String;)V\""), line);
        assertEquals(1, line.split("\"kind\":\"array\"", -1).length - 1, line);
    }

    /** Each element carries the SAME kind a single-`String` parameter in the
     *  same position would — a field reads `field`, a parameter reads
     *  `parameter`, an unreadable call result reads `unresolved` WITH its
     *  `source`. That is the whole defect this capability closes: the probe's
     *  control arm discriminated all eight destination spellings through a
     *  single-`String` sink while the varargs sink collapsed them to one
     *  byte-identical `unresolved`, and the elements now discriminate the same
     *  way. */
    @Test
    void gives_each_varargs_element_the_kind_a_single_argument_would_have() throws Exception {
        List<String> lines = callSites("varargsMixedProducers");
        String line = last(lines);
        assertTrue(line.contains("{\"kind\":\"field\",\"symbol\":\""
            + OWNER + "#url.\"}"), line);
        assertTrue(line.contains("{\"kind\":\"parameter\",\"value\":0}"), line);
        // The unreadable one keeps its instruction id, so the call that
        // produced it is a join away — exactly what the varargs `unresolved`
        // never had.
        assertTrue(line.contains("{\"kind\":\"unresolved\",\"source\":"), line);
    }

    /** Zero-length varargs — `foo()` against `foo(String...)` — compiles to an
     *  empty {@code ANEWARRAY}, and the empty list is written rather than
     *  omitted: "called with no destinations" is a different statement from
     *  "the array could not be read", and `unresolved` is what says the
     *  latter. */
    @Test
    void reports_a_zero_length_varargs_array_as_an_empty_element_list() throws Exception {
        String line = last(callSites("varargsEmpty"));
        assertTrue(line.contains("\"arguments\":[{\"elements\":[],\"kind\":\"array\"}]"), line);
    }

    /** A primitive varargs array is {@code NEWARRAY}/{@code IASTORE}, the other
     *  creation opcode and the other end of the eight store opcodes. */
    @Test
    void reads_the_elements_of_a_primitive_varargs_array() throws Exception {
        String line = last(callSites("varargsPrimitives"));
        assertTrue(line.contains("\"arguments\":[{\"elements\":["
            + "{\"kind\":\"int\",\"value\":1},{\"kind\":\"int\",\"value\":2}],"
            + "\"kind\":\"array\"}]"), line);
    }

    /** The declared element type is load-bearing one level down exactly as it
     *  is at the top level: {@code ICONST_1} is both the int 1 and the flag
     *  `true`, and only `boolean...`'s element type tells them apart. */
    @Test
    void tells_a_boolean_varargs_element_from_an_int_one() throws Exception {
        String line = last(callSites("varargsBooleans"));
        assertTrue(line.contains("\"arguments\":[{\"elements\":["
            + "{\"kind\":\"boolean\",\"value\":true},{\"kind\":\"boolean\",\"value\":false}],"
            + "\"kind\":\"array\"}]"), line);
    }

    /** An explicitly written `new String[]{…}` against a varargs parameter is
     *  byte-identical to the sugar — the ACC_VARARGS flag lives on the callee,
     *  a class this pass has not read — so the two MUST agree. They are the
     *  same call, and `elements` states what the callee receives. */
    @Test
    void reads_an_explicit_array_argument_exactly_as_it_reads_varargs_sugar() throws Exception {
        assertEquals(last(callSites("varargsLiterals")).replace("varargsLiterals", "X"),
                     last(callSites("explicitArray")).replace("explicitArray", "X"));
    }

    /** NEAR MISS — an array filled by a loop. Creation and stores are the same
     *  opcodes as the happy path; the index is a loop counter rather than a
     *  constant, so there is no element list. The assertion is that NOTHING was
     *  produced (GUIDELINES §10) — no `elements` key at all, not a different
     *  one. */
    @Test
    void produces_no_element_list_for_an_array_filled_in_a_loop() throws Exception {
        String line = last(callSites("varargsFilledInALoop"));
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
        assertFalse(line.contains("\"elements\""), line);
    }

    /** NEAR MISS — a conditionally populated array. Constant length, constant
     *  index, every slot written: only the branch separates it from the happy
     *  path, and each element then has two producing stores. Naming either
     *  would assert a path that may never run — the merge rule a plain
     *  conditional argument already obeys, one level down. */
    @Test
    void produces_no_element_list_for_a_conditionally_populated_array() throws Exception {
        String line = last(callSites("varargsPopulatedConditionally"));
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
        assertFalse(line.contains("\"elements\""), line);
    }

    /** NEAR MISS — a partially populated array: constant length 2, one constant
     *  store, the second element left null. Reporting the written half as the
     *  whole would claim an arity the call does not have. */
    @Test
    void produces_no_element_list_for_a_partially_populated_array() throws Exception {
        String line = last(callSites("varargsPartiallyPopulated"));
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
        assertFalse(line.contains("\"elements\""), line);
    }

    /** NEAR MISS — an array handed in from elsewhere. Its producer is no array
     *  creation, so it never reaches the array branch and keeps the
     *  `parameter` kind it already had: 9.15 does not turn every array-typed
     *  slot into an element list. */
    @Test
    void leaves_an_array_that_arrived_as_a_parameter_alone() throws Exception {
        String line = last(callSites("varargsFromAnArrayParameter"));
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"parameter\",\"value\":0}]"), line);
        assertFalse(line.contains("\"elements\""), line);
    }

    /** NEAR MISS — the array reaches another method between construction and
     *  the call that consumes it. Every element is a constant store at a
     *  constant index, so it reads perfectly at the moment it is built; what
     *  this pass cannot see is whether the callee rewrote it, and an element
     *  list would be a claim about the wrong instant. */
    @Test
    void produces_no_element_list_for_an_array_that_escapes_to_another_call() throws Exception {
        String line = last(callSites("varargsMutatedElsewhere"));
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
        assertFalse(line.contains("\"elements\""), line);
    }

    /** NEAR MISS — a store into the array after the call that consumes it. The
     *  callee holds the reference, so the elements this slot would claim are
     *  not the ones it ultimately sees. */
    @Test
    void produces_no_element_list_for_an_array_mutated_after_the_call() throws Exception {
        List<String> lines = callSites("varargsMutatedAfterTheCall");
        String line = lines.get(0);
        assertTrue(line.contains("\"name\":\"destinations\""), line);
        assertTrue(line.contains("\"arguments\":[{\"kind\":\"unresolved\"}]"), line);
        assertFalse(line.contains("\"elements\""), line);
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
        assertEquals(List.of(), MethodFlow.methodReturns("doc",
            "sextant-jvm maven c v o/P#missing().", abstractMethod));
    }

    /** `G-52`: a throw is an exit, published as a call-site-shaped fact whose target
     *  is the thrown TYPE and no method — `name` and `descriptor` ABSENT, not empty,
     *  because an empty name would match nothing while looking like one. It shares
     *  the ordinal sequence with the invokes before it, and it is not a
     *  `method_return`. Three producers of the thrown value: a `NEW` names the exact
     *  type, an invoke names its declared return type as a bound, and a rethrow's
     *  catch-handler entry names none — and the exit is published in all three. */
    @Test
    void publishes_a_throw_as_an_exit_naming_the_thrown_type_and_no_method() throws Exception {
        List<String> lines = callSites("throwsNew");
        String site = last(lines);
        assertTrue(site.contains("\"invoke_kind\":\"throw\""), site);
        assertTrue(site.contains("\"target\":{\"owner\":\"java/lang/IllegalStateException#\"}"), site);
        assertFalse(site.contains("\"name\""), site);
        assertFalse(site.contains("\"descriptor\""), site);
        assertTrue(site.contains("\"receiver\":null"), site);
        assertTrue(site.contains("\"result\":null"), site);
        // `<init>` is ordinal 0, the throw that follows it is ordinal 1: one sequence.
        assertTrue(lines.get(0).contains("\"name\":\"<init>\""), lines.get(0));
        assertTrue(site.contains("\"ordinal\":1"), site);
        assertEquals(List.of(), methodReturns("throwsNew"));

        String rethrow = last(callSites("rethrows"));
        assertTrue(rethrow.contains("\"invoke_kind\":\"throw\""), rethrow);
        assertTrue(rethrow.contains("\"target\":{\"owner\":null}"), rethrow);

        String built = last(callSites("throwsBuilt"));
        assertTrue(built.contains("\"invoke_kind\":\"throw\""), built);
        assertTrue(built.contains("\"target\":{\"owner\":\"java/lang/RuntimeException#\"}"), built);
    }

    /** Capability 9.18, and the whole point of it: the value a method hands
     *  back is another call's result, so the return NAMES that site. The chain
     *  a round trip needs was already extracted one hop short of this — an
     *  argument carries the `source` of the call that produced it — and this is
     *  the link that says which of those the method returns.
     *
     *  <p>The producing call's own `result` is read back rather than
     *  hardcoded: a value id is an instruction index, and pinning one would
     *  make the assertion about javac's label placement instead of about the
     *  join. */
    @Test
    void states_the_whole_fact_for_a_returned_call_result() throws Exception {
        String producer = callSites("returnsCallResult").get(0);
        List<String> returns = methodReturns("returnsCallResult");
        assertEquals(1, returns.size());
        String line = returns.get(0);
        assertTrue(line.contains("\"kind\":\"method_return\""), line);
        assertTrue(line.contains("\"document_id\":\"doc-call-sample\""), line);
        assertTrue(line.contains("\"method\":\"sextant-jvm maven com.acme/orders 1.0.0 "
            + OWNER + "#returnsCallResult("), line);
        assertTrue(line.contains("\"ordinal\":0"), line);
        assertTrue(line.contains("\"value\":{\"kind\":\"unresolved\",\"source\":"
            + field(producer, "result") + "}"), line);
    }

    /** A void return pops nothing, and that is an ANSWER rather than a failure
     *  to read one — which is why `value` is an argument entry and not a bare
     *  id. `null` here is a shape no value-returning form can produce, so
     *  "returns nothing" stays distinguishable from "returns something this
     *  pass could not name", which is `{"kind":"unresolved"}`.
     *
     *  <p>Paired deliberately: the same assertion pins BOTH spellings against
     *  each other, because a reading that collapsed them would still satisfy
     *  either one alone. */
    @Test
    void distinguishes_a_void_return_from_a_value_it_could_not_read() throws Exception {
        String empty = methodReturns("stringLiteral").get(0);
        assertTrue(empty.contains("\"value\":null"), empty);
        assertFalse(empty.contains("\"unresolved\""), empty);

        // A merged return is "one of these" since 9.19 — still not `null`, and still
        // not a value this pass named: the candidates are named, the choice is not.
        String unread = methodReturns("returnsAMergedValue").get(0);
        assertTrue(unread.contains("\"value\":{\"candidates\":["), unread);
        assertTrue(unread.contains("\"kind\":\"merge\"}"), unread);
        assertFalse(unread.contains("\"value\":null"), unread);
    }

    /** The declared RETURN type is load-bearing for the same reason an
     *  argument's declared type is: {@code true} and {@code 1} are one
     *  {@code ICONST_1}, and reporting a flag as an int loses the distinction
     *  the flag exists for. */
    @Test
    void reads_a_primitive_return_against_the_methods_own_declared_type() throws Exception {
        String line = methodReturns("returnsPrimitive").get(0);
        assertTrue(line.contains("\"value\":{\"kind\":\"boolean\",\"value\":true}"), line);
    }

    /** Two `return` statements are two facts, told apart by `ordinal`. Modelled
     *  rather than collapsed: a branch gives two possible answers and no single
     *  one, and asserting either as "the" returned value would be a fact about
     *  code that may never run — the same refusal a merged value gets. */
    @Test
    void records_each_return_of_a_branching_method_rather_than_one_of_them() throws Exception {
        List<String> returns = methodReturns("returnsOnTwoBranches");
        assertEquals(2, returns.size());
        assertTrue(returns.get(0).contains("\"ordinal\":0"), returns.get(0));
        assertTrue(returns.get(0).contains("\"value\":{\"kind\":\"string\",\"value\":\"first\"}"),
                   returns.get(0));
        assertTrue(returns.get(1).contains("\"ordinal\":1"), returns.get(1));
        assertTrue(returns.get(1).contains("\"value\":{\"kind\":\"string\",\"value\":\"second\"}"),
                   returns.get(1));
    }

    /** A returned parameter reads through the same grammar an argument slot
     *  does — the value is knowable only where THIS method was called, which is
     *  exactly what the cross-method propagation this fact feeds resolves. */
    @Test
    void reads_a_returned_parameter_as_the_parameter_it_is() throws Exception {
        String line = methodReturns("returnsParameter").get(0);
        assertTrue(line.contains("\"value\":{\"kind\":\"parameter\",\"value\":0}"), line);
    }

    /** A returned lambda, which is where 9.17 and 9.18 meet: the returned value
     *  reads as the `lambda` kind naming the body, and the site that created it
     *  carries the same symbol in `implementation`. One object, one answer from
     *  two directions. */
    @Test
    void reads_a_returned_lambda_as_the_body_it_names() throws Exception {
        String line = methodReturns("returnedLambda").get(0);
        // `() -> url` reads `this`, so the body is an instance method and the one
        // captured value became its receiver: `captures` 0, sorted ahead of `kind`.
        assertTrue(line.contains("\"value\":{\"captures\":0,\"kind\":\"lambda\",\"source\":"), line);
        assertNamesLambdaOf(line, "symbol", "returnedLambda");
    }

    /** A synthetic lambda method named by its ENCLOSING METHOD, with javac's own
     *  counter left unpinned.
     *
     *  The counter is the compiler's business and it moves: these assertions read
     *  `lambda$returnedLambda$0` under one JDK and `$1` under another, which is how
     *  two of them passed locally and failed in CI. The FACT under test is that the
     *  site names the lambda's own synthetic method — never which ordinal javac
     *  handed it. §13.8: the RUNBOOK already records "one compiler's conventions
     *  written down as the format's rules" as a repeated class; this is that class
     *  in a test rather than in a reader. */
    private static void assertNamesLambdaOf(String line, String key, String method) {
        String prefix = OWNER + "#lambda$" + method + "$";
        assertTrue(
            Pattern.compile(Pattern.quote("\"" + key + "\":\"" + prefix) + "\\d+" + Pattern.quote("(sig_"))
                   .matcher(line)
                   .find(),
            line);
    }

}
