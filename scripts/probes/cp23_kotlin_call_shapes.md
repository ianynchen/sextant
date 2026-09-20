# CP-23 — kotlinc 2.2.0 call-site shapes: `$default` masks, `@JvmStatic` bridges, and lambdas as classes

**Question.** Spec 2026-09-19 §3a rewrites a call to a `$default` bridge into a call to
the function it stands for, reading the mask literal(s) the caller pushes to learn which
parameters were defaulted; §3b marks a Kotlin lambda compiled as a class with
`lambda_body` on its type fact; §3c projects `@kotlin.Metadata`'s `declaresDefaultValue`
as `declares_default`. Each rests on a shape of kotlinc's output that no probe had
recorded: Q1–Q3 the mask literal(s) and the `aconst_null` marker before `invokestatic
greet$default` for a fully-defaulted call, a partially-defaulted call and a 33-parameter
function that needs two masks; Q4 a `@JvmStatic` default call, whose bridge has no
receiver slot; Q5 the bridge's own body — bit set means the default is substituted; Q6
under `-Xlambdas=class`, a plain lambda's superclass and its two `invoke`s (one typed,
one synthetic bridge), a suspend lambda's superclass and `invokeSuspend`, and a capturing
lambda's field and constructor; Q7 which lambdas are `invokedynamic` under the default
mode and whether a suspend lambda is a class in BOTH modes; Q8 whether the extractor jar
reads `declares_default` off a defaulted parameter.

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file, or (Q8) the extractor's own fact read off the same class files. It measures
one compiler and one source file: kotlinc's OUTPUT for these shapes, not what the Kotlin
language guarantees (the `$default` calling convention, the `Lambda`/`SuspendLambda`
base classes and `-Xlambdas` are compiler mechanisms, not language). It does not measure
the resolve-layer rewrite §3a specifies, which does not exist yet; it does not measure
kotlinc's SAM conversion to a Java functional interface (`-Xsam-conversions`, a separate
flag `KotlinCaptureSample` in the extractor tests depends on); and Q6/Q7 measure a lambda
that is RETURNED — a lambda passed as an argument compiles the same way but reaches a
call site's argument slot, which this probe does not exercise (`KotlinLambdaBodyTest`
pins the type fact, not the argument).

**Version scope (§5.4).** kotlinc as the `kotlin-maven-plugin` at Maven coordinate
`2.2.0` resolves it — and, as the identity the harness files every cell under, the
metadata version the class files THEMSELVES report: `@kotlin.Metadata`'s `mv` on
`Shapes.class` is `[2,2,0]` and the `META-INF/*.kotlin_module` written beside it opens
with the same three ints, both read as **2.2.0**. kotlinc writes no compiler-version
string into any class file, so the metadata version is the only identity the archive
reports; the harness aborts when the two readings disagree with each other or with the
version the run expected. Every verdict below is bounded by that one compiler, `kotlin-
stdlib` 2.2.0, `-jvm-target 21`, and the two lambda modes `indy` (the default) and
`class` (`-Xlambdas=class`). Q8 is additionally bounded by this repository's extractor
jar as built from the working tree at the time of the run, with
`kotlin-metadata-jvm:2.2.0` (the cell names both).

**How to run.** `JAVA_HOME=<jdk> bash scripts/probes/cp23_kotlin_call_shapes/run.sh`. It
compiles `scripts/probes/cp23_kotlin_call_shapes/src/main/kotlin/cp23/Shapes.kt` twice
with Maven — profile `indy` into `target/indy`, profile `class` into `target/class`, each
after a `clean` of its own directory, so a stale build cannot be read (CP-5's failure) —
builds the extractor jar with Gradle, then runs `probe.py`, which reads the identity off
each build's class bytes and prints the table below. Needs a JDK (for `javap` and to run
the extractor), Maven, Gradle's wrapper, and network on the first run only (kotlinc 2.2.0
is cached in `~/.m2` afterwards). Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the metadata version the class files REPORTED — `@kotlin.Metadata`'s
`mv` on `Shapes.class` as `javap -v` decodes it, cross-checked against the version header
of the `.kotlin_module` the same compilation wrote — and not the version the POM's
`kotlin.version` parameter asked for.** `probe.py` reads both values off the bytes of each
profile's build before it measures anything and ABORTS the whole run when they disagree
with each other or with the version the run expected, rather than filling a mislabelled
column. The `profile` column says which build a cell was read from; the two profiles
differ only in `-Xlambdas=class`. Rows 8a/8b are not `javap` reads — each is the
extractor jar run on that profile's classes, and the cell names the scanner and the
metadata library it reported.

```
| what the run read | 2.2.0 |
|---|---|
| builds whose class files report this metadata version | `target/indy/classes`, `target/class/classes` |
| identity read from the class bytes themselves (`@kotlin.Metadata` `mv`, `.kotlin_module` header) | yes |

| # | question | profile | kotlinc metadata | observed |
|---|---|---|---|---|
| 1 | callsGreetWithDefaults: mask literal and marker before greet$default | `indy` | 2.2.0 | `aload_0 ; aconst_null ; iconst_0 ; iconst_3 ; aconst_null ; invokestatic Method greet$default:(Lcp23/Shapes;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String; ; areturn` |
| 2 | callsGreetPartially: mask 2 | `indy` | 2.2.0 | `aload_0 ; ldc String y ; iconst_0 ; iconst_2 ; aconst_null ; invokestatic Method greet$default:(Lcp23/Shapes;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String; ; areturn` |
| 3 | callsWide: two mask literals for 33 parameters | `indy` | 2.2.0 | `aload_0 ; iconst_0 ×32 ; iconst_1 ; iconst_m1 ; iconst_0 ; aconst_null ; invokestatic Method wide$default:(Lcp23/Shapes;IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIILjava/lang/Object;)I ; ireturn` |
| 4 | Statics.callsJs: @JvmStatic js$default with no receiver | `indy` | 2.2.0 | `ldc String a ; iconst_0 ; iconst_2 ; aconst_null ; invokestatic Method js$default:(Ljava/lang/String;IILjava/lang/Object;)Ljava/lang/String; ; areturn` |
| 5 | greet$default body: bit set -> default substituted | `indy` | 2.2.0 | `iload_3 ; iconst_1 ; iand ; ifeq ; ldc String x ; astore_1 ; iload_3 ; iconst_2 ; iand ; ifeq ; iconst_0 ; istore_2 ; aload_0 ; aload_1 ; iload_2 ; invokevirtual Method greet:(Ljava/lang/String;Z)Ljava/lang/String; ; areturn` |
| 6a | -Xlambdas=class: Shapes$plain$1 | `class` | 2.2.0 | `extends kotlin/jvm/internal/Lambda ; field INSTANCE:Lcp23/Shapes$plain$1; [ACC_PUBLIC, ACC_STATIC, ACC_FINAL] ; method <init>()V [] ; method invoke(Ljava/lang/String;)Ljava/lang/Integer; [ACC_PUBLIC, ACC_FINAL] ; method invoke(Ljava/lang/Object;)Ljava/lang/Object; [ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC] ; method <clinit>()V [ACC_STATIC]` |
| 6b | -Xlambdas=class: Shapes$suspended$1 | `class` | 2.2.0 | `extends kotlin/coroutines/jvm/internal/SuspendLambda ; field label:I [] ; field L$0:Ljava/lang/Object; [ACC_SYNTHETIC] ; method <init>(Lkotlin/coroutines/Continuation;)V [] ; method invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object; [ACC_PUBLIC, ACC_FINAL] ; method create(Ljava/lang/Object;Lkotlin/coroutines/Continuation;)Lkotlin/coroutines/Continuation; [ACC_PUBLIC, ACC_FINAL] ; method invoke(Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object; [ACC_PUBLIC, ACC_FINAL] ; method invoke(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object; [ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC]` |
| 6c | -Xlambdas=class: Shapes$capturing$1 | `class` | 2.2.0 | `extends kotlin/jvm/internal/Lambda ; field $prefix:Ljava/lang/String; [ACC_FINAL, ACC_SYNTHETIC] ; method <init>(Ljava/lang/String;)V [] ; method invoke(Ljava/lang/String;)Ljava/lang/String; [ACC_PUBLIC, ACC_FINAL] ; method invoke(Ljava/lang/Object;)Ljava/lang/Object; [ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC]` |
| 7a | default profile: which lambdas are invokedynamic, which are classes | `indy` | 2.2.0 | `plain: invokedynamic InvokeDynamic #0:invoke:()Lkotlin/jvm/functions/Function1; ; suspended: new class cp23/Shapes$suspended$1 ; capturing: invokedynamic InvokeDynamic #1:invoke:(Ljava/lang/String;)Lkotlin/jvm/functions/Function1; ; class files: Shapes$suspended$1.class` |
| 7b | -Xlambdas=class: the same three | `class` | 2.2.0 | `plain: getstatic Field cp23/Shapes$plain$1.INSTANCE:Lcp23/Shapes$plain$1; ; suspended: new class cp23/Shapes$suspended$1 ; capturing: new class cp23/Shapes$capturing$1 ; class files: Shapes$capturing$1.class, Shapes$plain$1.class, Shapes$suspended$1.class` |
| 8a | extractor jar reads declares_default off greet's parameters | `indy` | 2.2.0 | `sextant-jvm-extractor with org.jetbrains.kotlin:kotlin-metadata-jvm:2.2.0 read name: declares_default=True ; loud: declares_default=True` |
| 8b | extractor jar reads declares_default off greet's parameters | `class` | 2.2.0 | `sextant-jvm-extractor with org.jetbrains.kotlin:kotlin-metadata-jvm:2.2.0 read name: declares_default=True ; loud: declares_default=True` |
```

## Verdicts

**Q1 — fully-defaulted call (§3a).** `callsGreetWithDefaults` pushes the receiver, one
placeholder per declared slot (`aconst_null` for the `String`, `iconst_0` for the
`boolean`), then the mask literal `iconst_3` (`0b11`: both parameters defaulted) and the
`aconst_null` marker, and calls `greet$default(Lcp23/Shapes;Ljava/lang/String;ZILjava/lang/Object;)`.
The mask is the LAST `int` before the marker, and the marker is the last argument —
exactly the two trailing slots `KotlinDefaultBridge` trims. The placeholder values are
not the defaults: `aconst_null` stands where `"x"` will be substituted, so a rule reading
the placeholder would read the wrong value — §3a's `{kind: unresolved, reason: defaulted}`
for a bit that is set is the honest projection.

**Q2 — partially-defaulted call (§3a).** `callsGreetPartially` pushes `ldc "y"` in the
first slot, `iconst_0` in the second, mask `iconst_2` (`0b10`: only `loud` defaulted).
Bit *i* of the mask is parameter *i*, counting declared parameters from 0 — the reading
§3a states.

**Q3 — two masks (§3a).** `wide` has 33 parameters; `callsWide` pushes 32 × `iconst_0`, then
`iconst_1` for `p32`, then TWO mask literals — `iconst_m1` (`0xFFFFFFFF`: parameters 0–31 all
defaulted) and `iconst_0` (`0b0`: parameter 32 supplied) — then the marker. The bridge's
descriptor carries 33 `I` slots for the parameters plus two `I` mask slots plus the
`Object` marker: ⌈33/32⌉ = 2 masks, mask *k* covering parameters 32k…32k+31, matching
§3a's `⌊i/32⌋`. A one-mask reader would take `iconst_1` (`p32`'s VALUE) for a mask, so
the mask count must be derived from the declared parameter count, never assumed to be
one.

**Q4 — `@JvmStatic` sibling (§3a).** `Statics.callsJs` calls
`js$default(Ljava/lang/String;IILjava/lang/Object;)` with `ldc "a" ; iconst_0 ; iconst_2 ;
aconst_null` and NO receiver slot: the bridge of a static sibling starts at the function's
own first parameter. §3a's "for a static sibling nothing moves" is the right rule, and
the receiver question is settled by which sibling exists, not by the bridge's shape
alone (`KotlinDefaultBridgeTest.twoCandidateSiblingsIsNoSibling`).

**Q5 — the bridge's body (§3a).** `greet$default` is, per parameter, `iload_3 (mask) ;
iconst_<bit> ; iand ; ifeq <skip> ; <push default> ; <store slot>`, then the call to
`greet` with the (possibly substituted) slots. Bit SET means the default IS substituted,
so a set bit is a defaulted parameter — the polarity §3a assumes, now measured.

**Q6 — a lambda as a class (§3b).** Under `-Xlambdas=class`:
`Shapes$plain$1 extends kotlin/jvm/internal/Lambda` with `invoke(Ljava/lang/String;)Ljava/lang/Integer;`
(`ACC_PUBLIC, ACC_FINAL` — not synthetic) and `invoke(Ljava/lang/Object;)Ljava/lang/Object;`
(`ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC`), a static `INSTANCE` singleton and a no-arg
constructor; `Shapes$suspended$1 extends kotlin/coroutines/jvm/internal/SuspendLambda` with
`invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;`, `create`, a typed
`invoke(Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;` and its
synthetic bridge; `Shapes$capturing$1` carries the captured value as field `$prefix`
(`ACC_FINAL, ACC_SYNTHETIC`), a constructor `(Ljava/lang/String;)V` taking it, and an
`invoke(Ljava/lang/String;)Ljava/lang/String;` with ONE parameter — the capture is never a
leading parameter of the body. The extractor's rule (`ClassScanner`, `lambda_body`) —
`invokeSuspend(Object)Object` where declared, else the one non-synthetic `invoke` — names
exactly the author's statements in all three, and `captures: 0` for the §3b projection is
exact. The typed `invoke` returns the BOXED `Ljava/lang/Integer;`, not `I`, so the body's
descriptor is `(Ljava/lang/String;)Ljava/lang/Integer;` — the spelling `KotlinLambdaBodyTest`
asserts.

**Q7 — which lambdas are classes (§3b).** Under the default mode `plain` and `capturing`
compile to `invokedynamic` (`LambdaMetafactory`, no class file) while `suspended` is `new
cp23/Shapes$suspended$1` and its class file is written; under `-Xlambdas=class` all three
are classes, and the non-capturing `plain` is reached through `getstatic
Shapes$plain$1.INSTANCE` rather than `new`. **A suspend lambda is a class in both modes**,
so `lambda_body` fires on every kotlinc 2.2.0 module that hands a suspend lambda to a
call — Ktor's `get("/x") { … }` handler exactly — with no compiler flag anyone set; the
`-Xlambdas=class` build is what makes a PLAIN lambda's class shape testable, not what
makes the field matter.

**Q8 — `declaresDefaultValue` (§3c).** The extractor jar, run on either profile's
`Shapes.class`, emits `declares_default: true` on both of `greet`'s parameters (`name`,
`loud`) — the flag is in `@kotlin.Metadata`'s protobuf and `kotlin-metadata-jvm:2.2.0`
decodes it; the fact IS the observation. Identical across the two lambda modes, as it
should be: the flag is on the function's declaration, which `-Xlambdas` does not touch.

`measured: 2026-09-20`, all eight questions, on the one compiler the scope names.
