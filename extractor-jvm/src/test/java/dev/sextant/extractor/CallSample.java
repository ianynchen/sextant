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
     *  <p>The merge at its narrowest: nothing at all sits between the branch
     *  and the invoke. {@link #conditionalThroughLocal} is the same merge with
     *  a store and a reload in the way, and the two must agree — see the note
     *  there for why that pair is worth keeping. */
    public void conditionalArgument(boolean fast) {
        sink(fast ? "/a" : "/b");
    }

    /** The same two-literal merge, reached through a local.
     *
     *  <p>This spelling used to be the <em>weaker</em> of the pair and is now
     *  the sharper one. While a store and a load each counted as a producer,
     *  javac's merge was hidden behind them: the reload handed the invoke a
     *  fresh single-sourced value, the slot landed in the ordinary
     *  variable-argument case, and the assertion passed whether or not the
     *  merge rule worked at all. With the copy instructions transparent the two
     *  producers survive the round trip through the local, so the slot is
     *  honestly {@code unresolved} — and this now genuinely tests the merge
     *  across the store, which is where a real method puts it. */
    public void conditionalThroughLocal(boolean fast) {
        String path = fast ? "/a" : "/b";
        sink(path);
    }

    public void staticCall() {
        helper("static");
    }

    public void chain() {
        first().second().third();
    }

    /** The OkHttp shape, and the ordinary way people write a builder: the built
     *  value goes into a local and a *separate* call consumes it. The store and
     *  the reload are the only things between the two halves, and if they count
     *  as producers the second call's argument names nothing — which is exactly
     *  the join a split builder chain has to be reconstructed from. */
    public void storedThenConsumed() {
        Link built = first().second();
        consume(built);
    }

    /** A receiver that arrives as a method parameter has no producing
     *  instruction anywhere in this method — the value existed before the first
     *  bytecode ran. The honest answer is a null receiver, not the index of the
     *  load that pushed a copy of it onto the stack. */
    public void parameterReceiver(Link supplied) {
        supplied.third();
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

    /** A method reference into the JDK, which is the common case: the symbol
     *  names a class no module declares, and every module that writes
     *  {@code String::trim} must produce the same one (D00 §1). */
    public void jdkMethodReferenceArgument(java.util.List<String> values) {
        values.replaceAll(String::trim);
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

    void consume(Link value) {
        record(String.valueOf(value));
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
