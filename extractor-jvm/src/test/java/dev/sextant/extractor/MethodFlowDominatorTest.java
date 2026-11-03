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
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

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
