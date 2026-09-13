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

    /** The receiver is a STATIC method's parameter 0 — local slot 0, where the instance
     *  rule would read `this`. The fact must say parameter 0. */
    public static void staticParameterReceiver(Link supplied) {
        supplied.third();
    }

    /** {@code long id} takes slots 0-1 after {@code this}, so {@code supplied} is slot 3
     *  and parameter 1. The fact names the parameter's index, never its slot. */
    public void wideParameterReceiver(long id, Link supplied) {
        supplied.third();
    }

    /** A lambda that captures a LOCAL. javac compiles it to a static synthetic method
     *  whose first parameter is the captured value and whose second is the interface's:
     *  {@code lambda$lambdaCapturingLocal$N(String, String)}. The indy carries one
     *  argument (the capture), the handle is static, so {@code captures} is 1. */
    public static void lambdaCapturingLocal(java.util.List<String> values, String prefix) {
        values.forEach(value -> helper(prefix + value));
    }

    /** A lambda that captures nothing at all: a static synthetic with the interface's
     *  parameter alone. Zero indy arguments, static handle, {@code captures} 0. */
    public static void lambdaCapturingNothing(java.util.List<String> values) {
        values.forEach(value -> helper(value));
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

    /** The shape capability 9.17 exists for: a lambda that fills **no argument
     *  slot at all**, so the {@code lambda} argument kind never fires and the
     *  body javac lifted out was named nowhere. The synthetic method's own
     *  symbol and call sites are facts already; nothing pointed at them.
     *
     *  <p>Returning it is the cheapest spelling of that shape, and it is not a
     *  contrived one — {@code OrderStreamBindings#handleOrder} in the
     *  orders-service fixture is a {@code @Bean} that does exactly this, and
     *  Spring Cloud Stream's whole functional model is written this way. A
     *  lambda parked in a field or invoked through its own interface is the
     *  same gap. */
    public java.util.function.Supplier<String> returnedLambda() {
        return () -> url;
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

    /** Capability 9.15's happy path: javac erases the varargs sugar into
     *  {@code ICONST_2; ANEWARRAY String; DUP; ICONST_0; LDC; AASTORE; …}, so
     *  the value reaching the slot is the array and every literal is invisible
     *  without the array branch. Two elements rather than one, because a
     *  one-element array cannot tell an element list from an accidental
     *  single-value read. */
    public void varargsLiterals() {
        destinations("orders.queue", "orders.retry.queue");
    }

    /** The element list must carry the SAME kind a single-`String` parameter in
     *  the same position would — that is the whole point of the capability, and
     *  the probe's control arm is exactly this comparison. A field, a
     *  parameter and an unreadable call result, in one array. */
    public void varargsMixedProducers(String supplied) {
        destinations(this.url, supplied, source());
    }

    /** Zero-length varargs: `foo()` compiles to `ICONST_0; ANEWARRAY`, and the
     *  empty element list is the fact — "called with no destinations", which is
     *  a different statement from "the array could not be read". */
    public void varargsEmpty() {
        destinations();
    }

    /** A primitive varargs array — {@code NEWARRAY} rather than {@code
     *  ANEWARRAY}, and {@code IASTORE} rather than {@code AASTORE}, which is
     *  the other half of the two creation opcodes and the other end of the
     *  eight store opcodes. */
    public void varargsPrimitives() {
        counts(1, 2);
    }

    /** The element type comes from the descriptor, and it is load-bearing one
     *  level down exactly as it is at the top level: {@code ICONST_1} is both
     *  the int 1 and the flag {@code true}, and only {@code boolean...}'s own
     *  element type tells them apart. Without it every flag in a varargs array
     *  would read as an int. */
    public void varargsBooleans() {
        flags(true, false);
    }

    /** An explicitly written array against the same varargs parameter. javac
     *  emits byte-identical bytecode for this and for {@link
     *  #varargsLiterals}'s sugar — the ACC_VARARGS flag is on the callee, not
     *  the call site — so the two MUST read the same, and this test exists to
     *  state that rather than to leave it discovered later. */
    public void explicitArray() {
        destinations(new String[] {"orders.queue", "orders.retry.queue"});
    }

    /** NEAR MISS — an array filled by a loop. The creation is an
     *  {@code ANEWARRAY} and the stores are {@code AASTORE}s, so the shape
     *  passes every syntactic test; the index is the loop counter, which is
     *  not a constant, and there is no element list to report. */
    public void varargsFilledInALoop(java.util.List<String> supplied) {
        String[] queues = new String[supplied.size()];
        for (int i = 0; i < queues.length; i++) {
            queues[i] = supplied.get(i);
        }
        destinations(queues);
    }

    /** NEAR MISS — a conditionally populated array. Constant length, constant
     *  indices, every slot written: only the *branch* separates it from
     *  {@link #varargsLiterals}, and each element has two producing stores, so
     *  reporting either would assert a path that may never run — the same
     *  merge rule a plain conditional argument already obeys. */
    public void varargsPopulatedConditionally(boolean fast) {
        String[] queues = new String[1];
        if (fast) {
            queues[0] = "fast.queue";
        } else {
            queues[0] = "slow.queue";
        }
        destinations(queues);
    }

    /** NEAR MISS — a partially populated array: constant length 2, one
     *  constant store, the other element left null. Reporting the written half
     *  as the whole would claim an arity the call does not have. */
    public void varargsPartiallyPopulated() {
        String[] queues = new String[2];
        queues[0] = "orders.queue";
        destinations(queues);
    }

    /** NEAR MISS — an array reference handed in from elsewhere. Its producer is
     *  not an array creation at all, so it never reaches the array branch and
     *  keeps the `parameter` kind it already had. The point is that 9.15 does
     *  not turn every array-typed slot into an element list. */
    public void varargsFromAnArrayParameter(String[] supplied) {
        destinations(supplied);
    }

    /** NEAR MISS — the array escapes to another method between construction and
     *  the call that consumes it. Every element is a constant store at a
     *  constant index, so the array reads perfectly at the moment it is built;
     *  what a within-method pass cannot see is whether {@code shuffle} rewrote
     *  it, and an element list here would be a claim about the wrong instant. */
    public void varargsMutatedElsewhere() {
        String[] queues = new String[] {"orders.queue"};
        shuffle(queues);
        destinations(queues);
    }

    /** NEAR MISS — an array stored into after the call that consumes it. The
     *  callee holds the reference for the rest of its life, so the elements
     *  this slot would claim are not the ones the callee ultimately sees. */
    public void varargsMutatedAfterTheCall() {
        String[] queues = new String[] {"orders.queue"};
        destinations(queues);
        queues[0] = "rewritten.queue";
    }

    void sink(String value) {
        record(value);
    }

    /** The varargs sink capability 9.15's cases call. `String...`, the shape
     *  every AMQP/Kafka inbound destination in Spring Integration takes. */
    void destinations(String... queues) {
        for (String queue : queues) {
            record(queue);
        }
    }

    /** A primitive varargs sink: `NEWARRAY`/`IASTORE` rather than
     *  `ANEWARRAY`/`AASTORE`. */
    void counts(int... values) {
        record(String.valueOf(values.length));
    }

    /** A `boolean...` sink: {@code BASTORE} into a {@code NEWARRAY boolean}, so
     *  the elements arrive as the same {@code ICONST_*} an int would. */
    void flags(boolean... values) {
        record(String.valueOf(values.length));
    }

    /** A method that receives the array and could rewrite it — what makes
     *  {@link #varargsMutatedElsewhere} an escape rather than a read. */
    static void shuffle(String[] queues) {
        if (queues.length > 1) {
            queues[0] = queues[1];
        }
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

    /** The link capability 9.18 exists for, in its smallest honest form: the
     *  value handed back is another call's result, so the return names the site
     *  that produced it and a caller can be joined to it one hop later. */
    String returnsCallResult() {
        return source();
    }

    /** A primitive return, and the reason the declared RETURN type is read
     *  alongside the value: {@code true} and {@code 1} are the same
     *  {@code ICONST_1}, and only the method descriptor tells them apart —
     *  exactly as an argument slot's own declared type does. */
    boolean returnsPrimitive() {
        return true;
    }

    /** Two {@code return} statements are two facts, not one. A method with a
     *  branch has two possible answers and no single one; collapsing them
     *  would assert whichever the pass happened to read last as the value the
     *  method returns. */
    String returnsOnTwoBranches(boolean flag) {
        if (flag) {
            return "first";
        }
        return "second";
    }

    /** The other half of the void/unreadable pair: a value that reaches the
     *  return from two branches has two producers and therefore no single
     *  answer, so it reads {@code unresolved} — a real value this pass cannot
     *  name, which a void return's "no value at all" must stay distinct from. */
    String returnsAMergedValue(boolean flag) {
        return flag ? "first" : source();
    }

    /** The value handed back is the caller's own parameter — knowable only
     *  where THIS method was called, which is precisely what the cross-method
     *  propagation this fact feeds will resolve. */
    String returnsParameter(String supplied) {
        return supplied;
    }

    /** `G-52`. The only exit is a throw: before the throw site existed this
     *  method published a call to the exception's CONSTRUCTOR and nothing
     *  saying the method then left through it — the same facts as a method
     *  that builds an exception to hand somewhere else. */
    void throwsNew(String reason) {
        throw new IllegalStateException(reason);
    }

    /** A rethrow: the thrown value's producer is the catch handler's stack
     *  entry, whose type lives in the try-catch table this pass does not read,
     *  so the site names NO type rather than a guess — but still names the exit. */
    void rethrows() {
        try {
            helper("attempt");
        } catch (RuntimeException caught) {
            throw caught;
        }
    }

    /** A helper-built exception, which is how most factory methods throw: the
     *  producer is an invoke, and the DECLARED return type is a bound the class
     *  file states rather than a guess. */
    void throwsBuilt() {
        throw build("reason");
    }

    static RuntimeException build(String reason) {
        return new RuntimeException(reason);
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
