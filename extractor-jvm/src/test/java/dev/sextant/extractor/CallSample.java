package dev.sextant.extractor;

/** A committed fixture whose method bodies exercise one call-site capture each
 *  (D00 §5's {@code call_site}). Compiled by Gradle's own test compilation, like
 *  every other fixture here, so the assertions are about the bytecode javac
 *  actually emits — a hand-written expectation of what a compiler "should" do
 *  is the one thing a dataflow pass must never be tested against.
 *
 *  <p>The callees are package-private rather than private on purpose: javac
 *  reaches a private member through {@code invokespecial}, which would make
 *  every case here read as the same dispatch form and hide the one distinction
 *  {@code invoke_kind} exists to draw. */
public final class CallSample {

    /** A compile-time constant: javac folds {@code BASE + "/x"} into a single
     *  {@code LDC} before the pass ever sees it, which is exactly why a
     *  constant-folded URL is recoverable at all. */
    private static final String BASE = "/api";

    enum Mode { FAST, SLOW }

    public void stringLiteral() {
        sink("/billing/invoices");
    }

    public void foldedConstant() {
        sink(BASE + "/x");
    }

    public void primitives() {
        numbers(7, 9000000000L, true);
    }

    public void enumConstant() {
        mode(Mode.FAST);
    }

    public void classLiteral() {
        type(CallSample.class);
    }

    public void nullArgument() {
        sink(null);
    }

    public void variableArgument(String supplied) {
        sink(supplied);
    }

    public void callResult() {
        sink(source());
    }

    /** Two literals, one slot: after the branch merges there are two producing
     *  instructions and no single answer, which is the case the whole choice of
     *  {@code SourceInterpreter} rests on. Naming either literal here would be a
     *  fact about a path that may never run.
     *
     *  <p>Passed straight into the call on purpose. Assigning it to a local
     *  first — {@code String path = fast ? "/a" : "/b"; sink(path);} — does
     *  <em>not</em> test this: javac merges at the store, and the reload is a
     *  fresh single-sourced value, so the slot reaches the invoke with one
     *  producing instruction (the ALOAD) and lands in the ordinary
     *  variable-argument case instead. That version passes whether or not the
     *  merge rule works. */
    public void conditionalArgument(boolean fast) {
        sink(fast ? "/a" : "/b");
    }

    public void staticCall() {
        helper("static");
    }

    public void chain() {
        first().second().third();
    }

    /** A lambda reaches the callee as the result of an {@code invokedynamic}
     *  bootstrapped by {@code LambdaMetafactory}; the body javac lifted out is
     *  the second bootstrap argument, and it is the only place the lambda's
     *  code survives. */
    public void lambdaArgument(java.util.List<String> values) {
        values.forEach(value -> sink(value));
    }

    /** A method reference compiles to the same bootstrap with the referenced
     *  method — no synthetic body — in the same bootstrap-argument slot. */
    public void methodReferenceArgument(java.util.List<String> values) {
        values.forEach(this::sink);
    }

    /** {@code NEW Holder; DUP; INVOKESPECIAL <init>}: the constructor returns
     *  void, so the value that reaches the argument slot is the one the
     *  {@code NEW} pushed. */
    public void instanceArgument() {
        hold(new Holder());
    }

    /** String concatenation is an {@code invokedynamic} too — bootstrapped by
     *  {@code StringConcatFactory}, and the producer of the value {@code sink}
     *  then consumes. Without a fact for the indy, that argument names a call
     *  site nothing emitted and the chain join dead-ends. */
    public void concatenated(String name) {
        sink("order-" + name);
    }

    void sink(String value) {
        record(value);
    }

    void numbers(int count, long total, boolean enabled) {
        record(count + ":" + total + ":" + enabled);
    }

    void mode(Mode value) {
        record(value.name());
    }

    void type(Class<?> value) {
        record(value.getName());
    }

    String source() {
        return BASE;
    }

    void hold(Holder held) {
        record(held.note());
    }

    Link first() {
        return new Link();
    }

    static void helper(String value) {
        record(value);
    }

    static void record(String value) {
        if (value == null) {
            return;
        }
    }

    /** A constructed argument: the concrete type is what a payload root and
     *  D02's one-hop body follow both read, and only the {@code NEW} names it. */
    static final class Holder {
        String note() {
            return "held";
        }
    }

    /** A chain's middle links: {@code a().b().c()} is the shape a fluent client
     *  builder takes, and the receiver of each hop is the previous hop's result. */
    static final class Link {
        Link second() {
            return this;
        }

        Link third() {
            return this;
        }
    }
}
