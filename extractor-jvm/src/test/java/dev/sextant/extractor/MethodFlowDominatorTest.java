package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;

/** {@code call_site}'s {@code dominator} and {@code on_every_exit} (D00 §5, spec
 *  2026-11-02-per-path-truth rule 9), one control-flow shape per test, read off the
 *  bytecode javac emits for {@code BranchSample.java}.
 *
 *  <p>Sites are found by the method they call, and a dominator is compared with the
 *  ORDINAL of the site it should name, never with a hardcoded number: the ordinal is
 *  javac's instruction order, and pinning it would test javac's layout. */
class MethodFlowDominatorTest {

    private static final String OWNER = "dev/sextant/extractor/BranchSample";

    private static List<String> callSites(String methodName) throws Exception {
        ClassNode classNode = new ClassNode();
        try (InputStream in = MethodFlowDominatorTest.class.getResourceAsStream(
                "/dev/sextant/extractor/BranchSample.class")) {
            new ClassReader(in.readAllBytes()).accept(classNode, ClassReader.SKIP_FRAMES);
        }
        MethodNode method = classNode.methods.stream()
            .filter(candidate -> candidate.name.equals(methodName))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no method named " + methodName));
        String symbol = new ClassScanner("com.acme/orders", "1.0.0")
            .symbolOf(OWNER + "#" + method.name + "(" + ClassScanner.disambiguatorOf(method.desc) + ").");
        return MethodFlow.callSites("doc-branch-sample", symbol, method);
    }

    /** The one site in `lines` calling `name`. */
    static String site(List<String> lines, String name) {
        List<String> found = lines.stream()
            .filter(line -> line.contains("\"name\":\"" + name + "\""))
            .toList();
        assertEquals(1, found.size(), "one call of " + name + " in " + lines);
        return found.get(0);
    }

    static int ordinal(String line) {
        Matcher matcher = Pattern.compile("\"ordinal\":(\\d+)").matcher(line);
        assertTrue(matcher.find(), "no ordinal on " + line);
        return Integer.parseInt(matcher.group(1));
    }

    /** The site's `dominator`, or null where the key is absent. */
    static Integer dominator(String line) {
        Matcher matcher = Pattern.compile("\"dominator\":(\\d+)").matcher(line);
        return matcher.find() ? Integer.valueOf(matcher.group(1)) : null;
    }

    /** The site's `on_every_exit`, which every reached site carries. */
    static boolean onEveryExit(String line) {
        Matcher matcher = Pattern.compile("\"on_every_exit\":(true|false)").matcher(line);
        assertTrue(matcher.find(), "no on_every_exit on " + line);
        return Boolean.parseBoolean(matcher.group(1));
    }

    /** The site's `post_dominator`, or null where the key is absent. */
    static Integer postDominator(String line) {
        Matcher matcher = Pattern.compile("\"post_dominator\":(\\d+)").matcher(line);
        return matcher.find() ? Integer.valueOf(matcher.group(1)) : null;
    }

    /** The site's `loop_group`, or null where the key is absent. */
    static Integer loopGroup(String line) {
        Matcher matcher = Pattern.compile("\"loop_group\":(\\d+)").matcher(line);
        return matcher.find() ? Integer.valueOf(matcher.group(1)) : null;
    }

    /** The site's `reaches_return`, which every reached site carries. */
    static boolean reachesReturn(String line) {
        Matcher matcher = Pattern.compile("\"reaches_return\":(true|false)").matcher(line);
        assertTrue(matcher.find(), "no reaches_return on " + line);
        return Boolean.parseBoolean(matcher.group(1));
    }

    private static void followedBy(List<String> lines, String call, String by) {
        assertEquals(ordinal(site(lines, by)), postDominator(site(lines, call)),
            call + " is post-dominated by " + by + " in " + lines);
    }

    private static void followedByNothing(List<String> lines, String call) {
        assertNull(postDominator(site(lines, call)), call + " in " + lines);
    }

    private static void dominatedBy(List<String> lines, String call, String by) {
        assertEquals(ordinal(site(lines, by)), dominator(site(lines, call)),
            call + " is dominated by " + by + " in " + lines);
    }

    @Test
    void in_a_straight_line_each_call_is_dominated_by_the_one_before_it() throws Exception {
        List<String> lines = callSites("straightLine");
        assertNull(dominator(site(lines, "a")), "the first call has no call before it");
        dominatedBy(lines, "b", "a");
        dominatedBy(lines, "c", "b");
        for (String call : List.of("a", "b", "c")) {
            assertTrue(onEveryExit(site(lines, call)), call);
        }
    }

    /** `a(); if (x) b(); c();` — `b` is on one branch: it runs before `c` on one path
     *  only, so `c`'s nearest dominating call is `a`, and `b` is not on every exit. */
    @Test
    void a_call_under_an_if_dominates_nothing_after_the_if() throws Exception {
        List<String> lines = callSites("ifThen");
        dominatedBy(lines, "b", "a");
        dominatedBy(lines, "c", "a");
        assertTrue(onEveryExit(site(lines, "a")));
        assertFalse(onEveryExit(site(lines, "b")));
        assertTrue(onEveryExit(site(lines, "c")));
    }

    @Test
    void neither_branch_of_an_if_else_dominates_the_other_or_the_join() throws Exception {
        List<String> lines = callSites("ifElse");
        dominatedBy(lines, "b", "a");
        dominatedBy(lines, "c", "a");
        dominatedBy(lines, "d", "a");
        assertFalse(onEveryExit(site(lines, "b")));
        assertFalse(onEveryExit(site(lines, "c")));
        assertTrue(onEveryExit(site(lines, "d")));
    }

    /** `a(); if (x) { b(); return; } c();` — `c` does not run on the path that returns
     *  early, so it is not on every exit, though nothing branches after it. */
    @Test
    void a_call_after_an_early_return_is_not_on_every_exit() throws Exception {
        List<String> lines = callSites("earlyReturn");
        dominatedBy(lines, "c", "a");
        assertTrue(onEveryExit(site(lines, "a")));
        assertFalse(onEveryExit(site(lines, "b")));
        assertFalse(onEveryExit(site(lines, "c")));
    }

    /** The loop's condition runs on every path; its body on one only. */
    @Test
    void a_while_body_dominates_nothing_after_the_loop() throws Exception {
        List<String> lines = callSites("whileLoop");
        dominatedBy(lines, "more", "a");
        dominatedBy(lines, "b", "more");
        dominatedBy(lines, "c", "more");
        assertTrue(onEveryExit(site(lines, "more")));
        assertFalse(onEveryExit(site(lines, "b")));
        assertTrue(onEveryExit(site(lines, "c")));
    }

    /** A `do/while` body runs at least once, so it is on every path. */
    @Test
    void a_do_while_body_runs_on_every_path() throws Exception {
        List<String> lines = callSites("doWhileLoop");
        dominatedBy(lines, "b", "a");
        dominatedBy(lines, "more", "b");
        dominatedBy(lines, "c", "more");
        assertTrue(onEveryExit(site(lines, "b")));
    }

    /** `e(); try { a(); b(); } catch (…) { c(); } d();` — the handler can be entered
     *  before `a` completes (exception edges count from the state BEFORE an instruction),
     *  so nothing in the try dominates the handler or the join; `e` does. */
    @Test
    void a_call_in_a_try_dominates_nothing_in_its_catch() throws Exception {
        List<String> lines = callSites("tryCatch");
        dominatedBy(lines, "a", "e");
        dominatedBy(lines, "b", "a");
        dominatedBy(lines, "c", "e");
        dominatedBy(lines, "d", "e");
        assertTrue(onEveryExit(site(lines, "e")));
        assertFalse(onEveryExit(site(lines, "a")));
        assertFalse(onEveryExit(site(lines, "b")));
        assertFalse(onEveryExit(site(lines, "c")));
        assertTrue(onEveryExit(site(lines, "d")));
    }

    /** `try { first(); } catch (…) { c(); }`, where the static call is the try's first
     *  instruction: the handler is entered exactly when `first` did not complete, so even
     *  the call an exception edge leaves from does not dominate the handler. */
    @Test
    void a_call_that_may_throw_does_not_dominate_its_own_handler() throws Exception {
        List<String> lines = callSites("tryOpensWithTheCall");
        assertNull(dominator(site(lines, "c")), lines.toString());
    }

    @Test
    void no_case_of_a_switch_dominates_another_or_the_join() throws Exception {
        List<String> lines = callSites("switched");
        for (String call : List.of("b", "c", "d", "e")) {
            dominatedBy(lines, call, "a");
        }
        for (String call : List.of("b", "c", "d")) {
            assertFalse(onEveryExit(site(lines, call)), call);
        }
        assertTrue(onEveryExit(site(lines, "e")));
    }

    /** A method with no normal return: no call is on every exit, because there is none. */
    @Test
    void a_method_that_always_throws_has_no_call_on_every_exit() throws Exception {
        List<String> lines = callSites("alwaysThrows");
        assertFalse(onEveryExit(site(lines, "a")));
        assertFalse(onEveryExit(site(lines, "<init>")));
        dominatedBy(lines, "<init>", "a");
    }

    /** Kotlin's `other?.go()` jumps around the call when `other` is null. */
    // `post_dominator` (rule 9, ruled by the user 2026-11-03, "A: add post_dominator"): the
    // nearest call that completes on every path from this one to a normal return.

    @Test
    void in_a_straight_line_each_call_is_followed_by_the_next() throws Exception {
        List<String> lines = callSites("straightLine");
        followedBy(lines, "a", "b");
        followedBy(lines, "b", "c");
        followedByNothing(lines, "c");
    }

    @Test
    void a_call_under_an_if_and_the_call_before_it_are_followed_by_the_join() throws Exception {
        List<String> lines = callSites("ifThen");
        followedBy(lines, "a", "c");
        followedBy(lines, "b", "c");
    }

    @Test
    void both_branches_of_an_if_else_are_followed_by_the_join() throws Exception {
        List<String> lines = callSites("ifElse");
        followedBy(lines, "a", "d");
        followedBy(lines, "b", "d");
        followedBy(lines, "c", "d");
    }

    /** `a(); if (x) { b(); return; } c();` — the early return leaves without `c`, so
     *  nothing follows `a` or `b` on every path, and the use after the `if` is NOT reached
     *  from `b`. */
    @Test
    void a_call_before_an_early_return_is_followed_by_nothing() throws Exception {
        List<String> lines = callSites("earlyReturn");
        followedByNothing(lines, "a");
        followedByNothing(lines, "b");
        followedByNothing(lines, "c");
    }

    @Test
    void a_loop_body_is_followed_by_its_condition_and_the_condition_by_the_exit_call()
            throws Exception {
        List<String> whileLines = callSites("whileLoop");
        followedBy(whileLines, "a", "more");
        followedBy(whileLines, "b", "more");
        followedBy(whileLines, "more", "c");
        List<String> doLines = callSites("doWhileLoop");
        followedBy(doLines, "a", "b");
        followedBy(doLines, "b", "more");
        followedBy(doLines, "more", "c");
    }

    /** `e(); try { a(); b(); } catch (…) { c(); } d();` — `b` may be skipped by the handler
     *  edge, so `a` is followed by `d`, not `b`. */
    @Test
    void a_handler_edge_skips_the_rest_of_a_try() throws Exception {
        List<String> lines = callSites("tryCatch");
        followedBy(lines, "e", "d");
        followedBy(lines, "a", "d");
        followedBy(lines, "b", "d");
        followedBy(lines, "c", "d");
    }

    @Test
    void every_case_of_a_switch_is_followed_by_the_join() throws Exception {
        List<String> lines = callSites("switched");
        for (String call : List.of("a", "b", "c", "d")) {
            followedBy(lines, call, "e");
        }
        followedByNothing(lines, "e");
    }

    /** No normal return is reachable: nothing follows, and the throw follows nothing. */
    @Test
    void a_call_from_which_every_path_throws_is_followed_by_nothing() throws Exception {
        List<String> lines = callSites("alwaysThrows");
        followedByNothing(lines, "a");
        followedByNothing(lines, "<init>");
    }

    // `reaches_return` (rule 9, ruled by the user 2026-11-03, option A): every path from the
    // call's completion ends at a normal return — none in a throw, none looping forever.

    @Test
    void every_call_of_a_straight_line_reaches_a_return() throws Exception {
        List<String> lines = callSites("straightLine");
        for (String call : List.of("a", "b", "c")) {
            assertTrue(reachesReturn(site(lines, call)), call);
        }
    }

    /** Both of `earlyReturn`'s exits are normal returns, so every call reaches one. */
    @Test
    void a_call_before_an_early_return_reaches_a_return() throws Exception {
        List<String> lines = callSites("earlyReturn");
        for (String call : List.of("a", "b", "c")) {
            assertTrue(reachesReturn(site(lines, call)), call);
        }
    }

    @Test
    void a_call_from_which_every_path_throws_reaches_no_return() throws Exception {
        List<String> lines = callSites("alwaysThrows");
        assertFalse(reachesReturn(site(lines, "a")));
        assertFalse(reachesReturn(site(lines, "<init>")));
    }

    /** `a(); if (x) throw …; b();` — one path from `a` throws, so `a` does not reach a return
     *  on every path; `b`, after the throw's branch, does. */
    @Test
    void a_throw_on_one_branch_means_not_every_path_reaches_a_return() throws Exception {
        List<String> lines = callSites("throwOnBranch");
        assertFalse(reachesReturn(site(lines, "a")));
        assertTrue(reachesReturn(site(lines, "b")));
    }

    /** A throw a handler covers is still read as one that may leave the method: which
     *  exceptions a handler catches is a matter of types this pass does not compare. So a
     *  call before it does not reach a return on every path — `partial`, never a wrong
     *  `resolved`. */
    @Test
    void a_caught_throw_is_still_read_as_one_that_may_leave() throws Exception {
        List<String> lines = callSites("throwCaught");
        assertFalse(reachesReturn(site(lines, "a")));
        assertTrue(reachesReturn(site(lines, "b")));
    }

    /** `try { a(); } catch (…) { throw failed; } b();` — the handler is entered only where `a`
     *  did NOT complete, so every path from `a`'s completion reaches `b` and the return; the
     *  plain try/catch's calls reach it too. */
    @Test
    void a_handler_that_rethrows_is_not_a_path_from_a_completed_call() throws Exception {
        List<String> lines = callSites("tryRethrows");
        assertTrue(reachesReturn(site(lines, "a")));
        assertTrue(reachesReturn(site(lines, "b")));
        List<String> caught = callSites("tryCatch");
        for (String call : List.of("e", "a", "b", "c", "d")) {
            assertTrue(reachesReturn(site(caught, call)), call);
        }
    }

    @Test
    void a_loop_that_exits_reaches_a_return_and_one_that_never_does_does_not() throws Exception {
        List<String> lines = callSites("whileLoop");
        for (String call : List.of("a", "more", "b", "c")) {
            assertTrue(reachesReturn(site(lines, call)), call);
        }
        List<String> forever = callSites("forever");
        assertFalse(reachesReturn(site(forever, "a")));
        assertFalse(reachesReturn(site(forever, "b")));
    }

    // `loop_group` (rule 9, ruled by the user 2026-11-03, option A for M1): the lowest call
    // ordinal in the non-trivial strongly connected component of the control-flow graph that
    // holds the call; absent where the call is in no cycle.

    @Test
    void a_method_with_no_loop_has_no_loop_group() throws Exception {
        List<String> lines = callSites("straightLine");
        for (String call : List.of("a", "b", "c")) {
            assertNull(loopGroup(site(lines, call)), call);
        }
    }

    /** `a(); while (more()) { b(); } c();` — the condition and the body are one cycle, named by
     *  its lowest call ordinal; `a` and `c` are in none. */
    @Test
    void a_while_loops_condition_and_body_share_one_group() throws Exception {
        List<String> lines = callSites("whileLoop");
        assertNull(loopGroup(site(lines, "a")));
        assertNull(loopGroup(site(lines, "c")));
        int lowest = Math.min(ordinal(site(lines, "more")), ordinal(site(lines, "b")));
        assertEquals(lowest, loopGroup(site(lines, "more")));
        assertEquals(lowest, loopGroup(site(lines, "b")));
    }

    @Test
    void a_do_while_body_and_condition_share_one_group() throws Exception {
        List<String> lines = callSites("doWhileLoop");
        assertNull(loopGroup(site(lines, "a")));
        assertNull(loopGroup(site(lines, "c")));
        assertEquals(ordinal(site(lines, "b")), loopGroup(site(lines, "b")));
        assertEquals(ordinal(site(lines, "b")), loopGroup(site(lines, "more")));
    }

    /** An inner loop's calls lie in the outer loop's component: every call of the outer body,
     *  the inner loop's included, is one group, so any of them can run before any other. */
    @Test
    void nested_loops_are_one_group() throws Exception {
        List<String> lines = callSites("nestedLoops");
        assertNull(loopGroup(site(lines, "a")));
        assertNull(loopGroup(site(lines, "e")));
        int group = ordinal(site(lines, "b"));
        for (String call : List.of("b", "c", "d")) {
            assertEquals(group, loopGroup(site(lines, call)), call);
        }
    }

    @Test
    void two_separate_loops_are_two_groups() throws Exception {
        List<String> lines = callSites("twoLoops");
        assertEquals(ordinal(site(lines, "a")), loopGroup(site(lines, "a")));
        assertEquals(ordinal(site(lines, "b")), loopGroup(site(lines, "b")));
    }

    /** The handler's edge back into the loop keeps the catch in the loop's group. */
    @Test
    void a_loop_with_a_try_catch_is_one_group() throws Exception {
        List<String> lines = callSites("loopWithTryCatch");
        int group = ordinal(site(lines, "more"));
        for (String call : List.of("more", "a", "b")) {
            assertEquals(group, loopGroup(site(lines, call)), call);
        }
        assertNull(loopGroup(site(lines, "c")));
    }

    /** An invoke no path reaches emits no site, so no group; the reached one has none either. */
    @Test
    void an_unreachable_call_is_no_site_and_in_no_group() throws Exception {
        MethodNode method = new MethodNode(Opcodes.ACC_PUBLIC, "dead", "()V", null, null);
        method.instructions.add(new VarInsnNode(Opcodes.ALOAD, 0));
        method.instructions.add(new MethodInsnNode(Opcodes.INVOKEVIRTUAL, OWNER, "a", "()V", false));
        method.instructions.add(new InsnNode(Opcodes.RETURN));
        method.instructions.add(new VarInsnNode(Opcodes.ALOAD, 0));
        method.instructions.add(new MethodInsnNode(Opcodes.INVOKEVIRTUAL, OWNER, "b", "()V", false));
        method.instructions.add(new InsnNode(Opcodes.RETURN));
        method.maxLocals = 1;
        method.maxStack = 1;
        String symbol = new ClassScanner("com.acme/orders", "1.0.0")
            .symbolOf(OWNER + "#dead(" + ClassScanner.disambiguatorOf("()V") + ").");
        List<String> lines = MethodFlow.callSites("doc-branch-sample", symbol, method);
        assertEquals(1, lines.size(), lines.toString());
        assertNull(loopGroup(site(lines, "a")));
    }

    @Test
    void a_kotlin_safe_call_is_on_one_branch() throws Exception {
        List<String> lines = KotlinMetadataTest.scan("KotlinBranchSample").stream()
            .filter(line -> line.contains("\"kind\":\"call_site\"")
                && line.contains("KotlinBranchSample#safeCall("))
            .toList();
        String go = site(lines, "go");
        String after = site(lines, "after");
        assertFalse(onEveryExit(go));
        assertTrue(onEveryExit(after));
        assertTrue(dominator(after) == null || dominator(after) != ordinal(go), after);
        assertEquals(ordinal(after), postDominator(go), go);
    }
}
