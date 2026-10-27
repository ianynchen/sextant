package dev.sextant.extractor;

/** Committed fixture for {@code field_write}'s same-block rule: every write here stores a
 *  value two branches MERGE at the write, so the instruction right below it is only the last
 *  branch's value — plus the near-miss, where the branch sits below a producer that is itself
 *  in the write's block. Compiled by Gradle's own test compilation, like {@code
 *  ConstructorSample}, so the assertions are about the bytecode javac actually emits. */
final class MergedWriteSample {
    static String host;
    String url;

    /** A ternary of two constants: {@code getstatic; ifeq; ldc; goto; ldc; putstatic}. */
    static void ternaryStatic(boolean prod) {
        host = prod ? "https://prod.example.com/" : "https://staging.example.com/";
    }

    /** A null-default: the lookup's result on one branch, a constant on the other. */
    static void nullDefaultStatic() {
        host = System.getenv("SEXTANT_UNSET") != null
            ? System.getenv("SEXTANT_UNSET") : "https://default.example.com/";
    }

    /** A ternary of two calls into {@code this}'s field. */
    void ternaryField(boolean c) {
        this.url = c ? make("https://x.example.com/") : make("https://y.example.com/");
    }

    /** A null-default whose both branches are calls. */
    void nullDefaultField() {
        this.url = lookup() != null ? lookup() : make("https://default.example.com/");
    }

    /** Two calls joined BEFORE a cast: {@code invokestatic; goto; invokestatic; L: checkcast;
     *  putfield}. The cast is in the write's block and the call it looks through is not. */
    void castAfterTheJoin(boolean c) {
        this.url = (String) (c ? makeObject("https://x.example.com/") : makeObject("https://y.example.com/"));
    }

    /** The RECEIVER merged rather than the value: {@code (c ? other : this).url = value}. The
     *  {@code aload_0} right below the value is the else branch's, and the then branch writes
     *  another object's field. */
    void mergedReceiver(boolean c, MergedWriteSample other, String value) {
        (c ? other : this).url = value;
    }

    /** The near-miss: the branch is in the call's ARGUMENT, below a call that is itself in
     *  the write's block, so the field holds that one call's result. */
    void branchBelowTheCall(boolean c) {
        this.url = make(c ? "https://x.example.com/" : "https://y.example.com/");
    }

    static String make(String s) {
        return s;
    }

    static Object makeObject(String s) {
        return s;
    }

    static String lookup() {
        return System.getenv("SEXTANT_UNSET");
    }
}
