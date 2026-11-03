package dev.sextant.extractor;

/** A committed fixture whose method bodies exercise one control-flow shape each, for
 *  {@code call_site}'s {@code dominator} and {@code on_every_exit} (D00 §5, spec
 *  2026-11-02-per-path-truth rule 9). Compiled by Gradle's own test compilation, so the
 *  assertions are about the graph javac actually emits.
 *
 *  <p>Its own class rather than more methods on {@code CallSample}: javac 21 numbers a
 *  class's lambdas with one class-wide counter, and a new method there could renumber what
 *  that class's tests read. The callees are package-private for the reason
 *  {@code CallSample} states. */
public final class BranchSample {

    void a() {}

    void b() {}

    void c() {}

    void d() {}

    void e() {}

    boolean more() {
        return false;
    }

    static void first() {}

    public void straightLine() {
        a();
        b();
        c();
    }

    public void ifThen(boolean x) {
        a();
        if (x) {
            b();
        }
        c();
    }

    public void ifElse(boolean x) {
        a();
        if (x) {
            b();
        } else {
            c();
        }
        d();
    }

    public void earlyReturn(boolean x) {
        a();
        if (x) {
            b();
            return;
        }
        c();
    }

    public void whileLoop() {
        a();
        while (more()) {
            b();
        }
        c();
    }

    public void doWhileLoop() {
        a();
        do {
            b();
        } while (more());
        c();
    }

    public void tryCatch() {
        e();
        try {
            a();
            b();
        } catch (RuntimeException failed) {
            c();
        }
        d();
    }

    /** The try's first instruction is the call itself: no load before it. */
    public void tryOpensWithTheCall() {
        try {
            first();
        } catch (RuntimeException failed) {
            c();
        }
    }

    public void switched(int n) {
        a();
        switch (n) {
            case 1:
                b();
                break;
            case 2:
                c();
                break;
            default:
                d();
        }
        e();
    }

    public void alwaysThrows() {
        a();
        throw new IllegalStateException("never returns");
    }
}
