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

    /** An instance field: not a constant of its own type, so it must miss the
     *  enum-constant shape and land in {@code field} instead. */
    String url;

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

    /** {@code BigDecimal.ZERO} is a GETSTATIC of a field typed as its own
     *  owner — exactly the enum-constant shape, on a class that carries no
     *  {@code ACC_ENUM} at all. The ordering pin: the enum check runs first,
     *  so this must still read {@code enum}, never fall through to the
     *  {@code field} branch beside it. */
    public void bigDecimalZeroArgument() {
        amount(java.math.BigDecimal.ZERO);
    }

    /** {@code this.url}: a GETFIELD that is not the enum-constant shape —
     *  D00 §5's {@code field} kind. */
    public void fieldArgument() {
        sink(this.url);
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

    /** A static method has no {@code this}, so its first parameter is local
     *  slot 0 — the one place where the instance rule (slot 0 is the receiver)
     *  would report the wrong index, or none at all. */
    public static void staticVariableArgument(String supplied) {
        helper(supplied);
    }

    /** {@code long} occupies two slots, so {@code label} — parameter 1 —
     *  starts at slot 3. The fact must name the parameter's own index, never
     *  its slot, the same distinction {@code field_write} already pins. */
    public void wideLeadingParameter(long id, String label) {
        sink(label);
    }

    /** A parameter parked in a local and read back: the store and the reload
     *  relocate the value without producing it, so it is still the parameter
     *  that reached the call — the ordinary way a method spells this. */
    public void parameterThroughLocal(String supplied) {
        String local = supplied;
        sink(local);
    }

    /** Two *different* parameters merged on a branch: two producers, so the
     *  answer is the same honest silence a merge of two literals gets. Naming
     *  either one would be a fact about a path that may never run — the
     *  parameter kind must not weaken the merge rule it rides on. */
    public void mergedParameters(boolean fast, String left, String right) {
        sink(fast ? left : right);
    }

    /** A parameter and a literal merged on a branch. This is the arity change
     *  the parameter kind makes, stated as a test rather than discovered
     *  downstream: while a parameter contributed <em>no</em> producer, this
     *  merge had exactly one and the pass reported {@code /default} as though
     *  the argument were always that — one branch's value asserted for both.
     *  The parameter is a producer of its own now, so the slot is honestly
     *  {@code unresolved}: less recall, and the only answer that is true on
     *  every path. */
    public void mergedParameterAndLiteral(boolean fast, String supplied) {
        sink(fast ? supplied : "/default");
    }

    /** {@code this} is in slot 0 of an instance method and is a parameter of
     *  no descriptor: it names no index, so it stays {@code unresolved}.
     *
     *  <p>The parameter beside it is what gives the case teeth: with no
     *  parameters declared there are no slots to be off by one against, and an
     *  implementation reading the slot number as the index would pass. Here
     *  {@code supplied} occupies slot 1 as parameter 0, so that implementation
     *  would call {@code this} parameter 0 too. */
    public void selfArgument(String supplied) {
        consumeSelf(this);
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

    /** The fluent-builder shape WebClient/RestClient actually compile to: a
     *  mid-chain hop inherited from a generic self-type interface ({@code
     *  UriStep<S>}) returns {@code S}'s erased bound, not the narrower type
     *  the next call in the chain needs, so javac bridges the gap with a
     *  {@code CHECKCAST}. The cast does not build a new object — only a new
     *  static type for the same reference — so a chain join must survive it
     *  exactly as it survives a load/store/dup. */
    public void checkcastBridgedChain(BodyUriStep spec, Object payload) {
        spec.uri("/x").body(payload);
    }

    /** The other side of the {@code CHECKCAST}-only carve-out: a {@code
     *  GETFIELD} genuinely computes a new value from the object it reads, so
     *  it must NOT get the same transparent treatment. {@code box} itself is
     *  a method parameter — no producing instruction, so its own id reads as
     *  absent (D00 §5) — and a fully-transparent {@code unaryOperation}
     *  would fold {@code box.link}'s read straight through to that same
     *  absent id, leaking a null receiver onto {@code third()} instead of
     *  the {@code GETFIELD}'s own real one. */
    public void getfieldSourcedReceiver(Box box) {
        box.link.third();
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

    void amount(java.math.BigDecimal value) {
        record(value.toString());
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

    void consumeSelf(CallSample value) {
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

    /** A field whose read must count as producing a value, not relocating
     *  one — see {@link #getfieldSourcedReceiver}. */
    static final class Box {
        Link link;
    }

    /** The erased bound {@code UriStep.uri} actually returns — the exact shape
     *  {@code WebClient.RequestHeadersUriSpec}/{@code RestClient}'s own
     *  {@code UriSpec<S extends RequestHeadersSpec<S>>} takes. */
    interface Wide {}

    /** A generic self-type hop: {@code S}'s bound is {@link Wide}, so the
     *  erased bytecode return type is {@code Wide} even where the caller's own
     *  static type substitutes something narrower. */
    interface UriStep<S extends Wide> {
        S uri(String value);
    }

    /** The narrower type the next hop in a real request-body chain needs
     *  (WebClient/RestClient's own {@code RequestBodySpec}) — a subtype of
     *  {@link Wide}, never returned directly by {@link UriStep#uri}. */
    interface Narrow extends Wide {
        Narrow body(Object value);
    }

    /** {@code WebClient.RequestBodyUriSpec}'s own shape: narrows {@code S} to
     *  {@link Narrow}, so {@code uri(...)}'s compile-time type is {@link
     *  Narrow} while its erased bytecode return type stays {@link Wide} —
     *  the gap javac bridges with a {@code CHECKCAST}. */
    interface BodyUriStep extends Narrow, UriStep<Narrow> {}
}
