# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/) (GUIDELINES §5).

Nothing has been released yet: `0.1.0` is the working version and the
version-bump gate has not opened, so everything below sits under Unreleased.
This file starts at Phase 2O — earlier phases are recorded in
`docs/superpowers/plans/` and `docs/superpowers/specs/`, and backfilling them
here would restate those documents rather than add anything.

## [Unreleased]

### Fixed

- **A compiler-generated bridge is read from the fact, and its mapping now lands on the
  method someone actually wrote** (OI-47, closed).

  Spring's annotations are inherited from an interface or superclass, and Sextant walks that
  hierarchy to work out a handler's effective mapping. The ancestor lookup joins by method
  name AND descriptor — so for a covariant or generic override, whose descriptor is by
  definition not its ancestor's, the only thing that can match is the forwarder javac
  generates beside it. The bridge is therefore the only method that resolves, and it is the
  wrong answer to publish.

  Which method is the bridge was inferred from shape — same class, same name, same
  parameters, different return — and that was wrong in **both** directions, measured:

  | Bridge differs from the real method in | Rule saw it? | What shipped |
  |---|---|---|
  | return type (covariant override) | yes | both excluded — the mapping was **lost** |
  | parameter types (generic interface) | **no** | the row named **the synthetic bridge** |

  The second is a fabrication: a class implementing `Api<String>` published its handler as
  `handle(Object)`, a method no source file contains.

  A method fact has stated the answer since the `modifiers` slot shipped — `modifiers.synthetic`,
  with `ACC_BRIDGE` folded in because javac sets the two together — and the rule's own comment
  claimed the opposite (*"Bytecode carries no other marker — no `modifiers`"*). It is read now,
  and a bridge is treated as **evidence rather than a target**: the mapping it resolves is
  carried across to the same-class, same-name, non-synthetic method it forwards to. Exactly one
  such method, or nothing at all — several same-named methods a human wrote leave nothing
  saying which the bridge stands for (§8). The structural rule stays as the fallback for a fact
  carrying no `modifiers` key at all.

  **The wiring is the part that had to be proved.** The first attempt added the column to the
  query and stopped: `annotation_driven._method_declaration_rows` is the only producer of these
  rows and rebuilt them without it, so every real run kept the old behaviour while every test
  about the new one passed — they hand-build their own rows. Measured on the fixture now:
  `GET /api/orders/{id}` derives where it did not before, its handler naming the covariant
  override rather than javac's bridge, and the module's endpoint count moves 122 to 123 with
  nothing else moving.

  **Finding I1's outcome is unchanged for DIFFERING mappings, and its reason is now honest.** A class overriding one
  method against two mapped ancestors grows two bridges that redirect to one method; it still
  derives nothing, but because two ancestors give one method two different answers and this
  pass does not read the framework's own annotation search order — not because every bridge was
  discarded. Closing that means mirroring the framework exactly (DR-6), which is its own work.

- **The `Signature` attribute is read for the half of it that was being dropped** (W5).
  It was already read for field types, method RETURN types, the generic superclass and the
  generic superinterfaces. It was not read for method or constructor **parameter** types, nor
  for the formal type parameters a class or method declares. A fact could therefore say a
  method returns `Map<K, T>` while being unable to say what `K` or `T` were, and every
  parameter arrived erased.

  **Two documented gaps close outright**, both in the messaging fixture and both previously
  frozen as honest limitations with a test asserting the wrong answer:
  `onBatch(List<OrderEvent>)` now reports `wire_type: array` **carrying its element**, and
  `onDeadLetter(ConsumerRecord<String, OrderEvent>)` now reaches its payload through the
  catalog's declared `payload_arg: 1` and reports `OrderEvent` instead of nothing. The
  checkpoint's own expectation for that row had been recorded as not holding against the
  scanner's real output; it holds now.

  **`type_parameters` is new on a class or method symbol fact** — an ordered `{name, bounds}`
  per formal type parameter, emitted only where a declaration has any. Bounds are recorded as
  the signature states them, an explicit root-type bound included, because `<T>` and
  `<T extends Object>` compile to identical bytes and an empty list would otherwise mean
  either "unbounded" or "not read". It is declared as a capability so a catalog can require
  it, and it has **no consumer yet** — W25 is where generic substitution reads it, recorded
  as OI-46 rather than left to be discovered.

  **Aligning the descriptor's parameters against the signature's is done with the class
  file's own flags, not by counting**, and the first attempt here did count. JVMS 4.7.9.1
  lets a signature omit implicitly declared parameters, and a compiler may also omit ones it
  synthesised — but the difference in LENGTH does not say which. Measured: an inner class's
  constructor carries the enclosing instance first and an enum's constructor its name and
  ordinal first, while a local class that captures carries its captures **last**. Counting
  from the end is right for the first two and puts a collection's element type onto an `int`
  in the third — a perfectly well-formed fact that is false. `MethodParameters` (JVMS 4.7.24)
  distinguishes them: `ACC_MANDATED` and `ACC_SYNTHETIC` mark exactly the parameters a
  signature may omit, wherever they sit. Where the attribute is absent, or its flags do not
  account for the difference, every parameter keeps its erased type — less specific, never
  wrong. A local class inside a **static** method is the real case that needs that fallback:
  captures at the end and no `MethodParameters` at all.

  **A parameter keeps the descriptor's symbol too, as `erased_symbol`.** Reading the
  signature was first written as REPLACING the parameter's type, and that deleted something
  four consumers were using. A parameterized type is unaffected — `List<String>` was and
  still is `java/util/List#`, it merely keeps `String` now — but a bare **type variable**
  changes from its erasure to its name, and **a type variable's name is scoped to the
  declaration that introduced it**: an interface calls it `E` where its implementation calls
  it `T`, for one method. Four consumers compare or look up by a parameter's symbol ACROSS
  declarations, and each broke differently:

  | Consumer | What it does | What replacing the symbol did |
  |---|---|---|
  | `derive_endpoints.sql` overload dedup | partitions on the parameter symbols | `m(E)` and `m(T)` land in two partitions: one method, two published rows |
  | `effective_annotations._is_bridge` | matches an override's parameters against its bridge's | the bridge carries no signature, so the pair stops matching and the **synthetic bridge stops being excluded** |
  | `supertype_dispatch` selector | matched against a catalog-declared parameter type | a variable's name matches no declared type |
  | `single_call` payload lookup | reads annotations OFF the named type | `<T extends OrderEvent> handle(T)` resolved through `OrderEvent`; `T` resolves through nothing |

  A second review found the sweep was short: there are **six** such consumers, not four.
  `interface_implementation` compares an interface's parameter tuple against an
  implementation's — a `Handler<E>` read `E`, matched neither the override nor its bridge, and
  the subscription's handler attribution was lost outright. `error_advice` tests a parameter
  against the set of throwable types the workspace declares — a generic advice base
  (`handle(E ex)` where `E extends BusinessException`) matched nothing and its exception list
  emptied. Two more compare against catalog-declared type names
  (`shapes/contracts.py`'s `sole_unannotated` exclusions, `shapes/parse_binding.py`'s
  `bytes_payloads`).

  So the fact carries both: `type` is the signature's answer, which is what a substitution
  binds and what closed the two gaps above, and `erased_symbol` is the descriptor's, which is
  what can be compared between declarations. All six read `erased_symbol` and are back to
  exactly their previous answers — restored, not improved: `_is_bridge` keeps its structural
  rule rather than switching to the `modifiers.synthetic` the fact already carries, because
  that would also erase a documented over-exclusion, which is its own change (OI-47).

  **One place deliberately does NOT switch**, and gains a guard instead. `_body_type` roots a
  request shape at the parameter's declared type — reading the signature there is what closed
  the two gaps above — but a shape is identified BY its symbol, and `@RequestBody T body` on a
  generic base controller would mint a shape whose id is `T`, which every unrelated `T` in the
  module then collides onto. It now roots no shape at a type variable: no answer rather than
  one shape claiming to describe several unrelated payloads.

  `erased_symbol` is written on **every** parameter, not only where the two differ: a JSON
  path wildcard drops elements whose key is absent (measured in DuckDB — three parameters,
  two entries returned), so a sparse key yields a shorter list that misaligns against the
  parameters it describes. That is the same class of defect as the descriptor/signature skew
  above, reached a different way.

  **`ACC_MANDATED` does not mean "omitted from the tables", and reading it that way deleted
  a fact.** The first version of this fix stated that premise and acted on it, and a record's
  COMPACT canonical constructor disproves it: javac flags EVERY slot mandated there — what is
  implicit is the constructor, not its parameters — while the tables omit nothing (measured:
  two parameters, both mandated, a full-length parameter-annotation table, a type annotation
  at `param_index=1`). `Signature` and the parameter-annotation table each carry a count to
  corroborate the flags against and were unaffected; `METHOD_FORMAL_PARAMETER` (4.7.20.1)
  carries none, read the flags blind, concluded the method declares no parameters, and
  **dropped every type annotation on a record component** — a type-use `@Nullable`, gone. An
  empty flag result now means "the flags say nothing", never "there are no parameters".

  **The parameter-ANNOTATION table was wrong the same way, and is fixed with it.** Three
  attributes are indexed by declared parameters rather than by descriptor slots —
  `Signature` (4.7.9.1), `Runtime[In]VisibleParameterAnnotations` (4.7.18) and
  `METHOD_FORMAL_PARAMETER` type annotations (4.7.20.1) — and each was aligned by its own
  arithmetic on counts. Measured: `@Labelled` written on a capturing local class's
  `List<String>` parameter was landing on the captured `int`, in both the instance form and
  the static form. All three now read one helper over the `MethodParameters` flags, so they
  cannot disagree with each other. Where no flags exist the index is taken as the slot,
  stated as measured rather than as a property of the format: every shape that omits from
  the FRONT carries flags saying so, and the one measured shape that carries none — a local
  class in a static method — appends its synthetics.

  Kotlin needs no alignment and is pinned saying so: kotlinc writes a full-length signature
  (a `suspend fun`'s trailing `Continuation` appears in both lists) and its `$default` bridge
  carries no signature at all, so neither path reaches the flag-based alignment.

- **The field check stops refusing a pin it does not need to build** (`scripts/field_check.py`).
  Its JDK guard ran before `_ensure_compiled` decided whether a build was needed at all, so
  `mall-admin` — already compiled at the pinned commit by a JDK 21 — was refused on a machine
  whose Maven reports 26. Nothing was going to invoke Maven, so there was no wrong toolchain
  to prevent, and the message reported "this pin cannot be validated" for what was really
  "this machine cannot BUILD this pin". The guard now runs on the build path, where it
  belongs, and both arms are tested. The field baseline is 3/3 from the script again.

- **Four JVMS 4.7 attributes that each stood in for an invented rule are now read** (W4).
  Every one was already in the class file, and one was being handed to us by ASM as a
  parameter we ignored.

  **`ConstantValue` (4.7.2)** gives D00 §5's `constant` fact its first producer — a declared
  fact kind with nothing emitting it. `static final String TOPIC = "orders"` is how a great
  many real listeners name their destination. 19 such facts from the fixture; a field
  initialised in `<clinit>` correctly yields none, because what a static initialiser computes
  is a different question.

  **`InnerClasses` (4.7.6) and `EnclosingMethod` (4.7.7)** give a nested class the enclosing
  symbol it reported as `null`. `OrderResult$Detail` → `OrderResult#`, and — the half that
  splitting a binary name on `$` can never recover — `BillingRestTemplate$1` → its enclosing
  METHOD. The class symbol is now emitted at `visitEnd` and re-inserted at index 0, because
  ASM fires `visit` before those attributes arrive; the fact stream's order is unchanged.

  **`AnnotationDefault` (4.7.22)** reads what an annotation element falls back to, which
  catalogs currently hardcode — a claim about a framework at a version nobody measured.
  All four value shapes verified: string, int, array, boolean.

  **`StringConcatFactory`'s recipe** turns an assembled address into a template. Before this,
  `"/api/" + version + "/orders"` reached a catalog as `{"kind": "unresolved"}` — an outbound
  call naming nothing at all. It now reads `/api/{}/orders`.

  **The hole stays unnamed deliberately.** A path variable's name was never part of the
  address — a server routes `/api/owners/42` to `/api/owners/{ownerId}` by POSITION and could
  rename the variable without changing the wire — so `{}` is exactly what both sides share.
  Normalising the name away lines a client template up with a server route
  (`/api/owners/{ownerId}` ↔ `/api/owners/{}`), which is what makes the recorded address
  matchable at all. Naming it would also invent a name: the class file carries a parameter's
  name only when the build asked for it, and the filler is often not a parameter.

  **The matching itself is phase L, not this.** Whether a template is ambiguous depends on
  the set of routes it is compared against, and those live in another service's bundle. What
  W4 delivers is an address recorded in a shape that will match, instead of one lost entirely.


- **Multi-release selection is applied, so G-62 is fixed rather than renamed** (W3c, Fork 4
  rule 3). W3 tagged every copy and dropped none, which by itself left LABELLED duplicates —
  two documents minting the SAME type symbol, and no table downstream has a uniqueness
  constraint. That was the caution Fork 4 attached to its own ruling, and this is what
  discharges it. Measured on a jar holding one class at base and at release 21: **12 symbols
  with 6 duplicated, becoming 6 with none.**

  The JVM's own rule (JEP 238): among copies of one class name, the highest release not
  exceeding the module's target wins, else base. The target is W3b's declared release —
  which until now had no consumer at all.

  **Applied where the tables are built**, not merely computed: `symbols`, `annotations`,
  `call_sites`, `method_returns` and `field_writes` each exclude documents that lost. A
  selection nothing acts on would have renamed the bug.

  **Nothing is deleted.** Every copy stays in `documents` with its release, so a reader can
  see what was selected between rather than only the winner, and `selected_documents` travels
  in the bundle so a consumer can tell which copy the derived rows came from.

  Three branches, each pinned by a test and each mutation-checked. A class overlaid ONLY
  above the target — 626 such names in the measured corpus — keeps its lowest copy rather
  than vanishing: dropping it would assert the class does not exist, which is false. A module
  declaring no target reaches the highest overlay rather than base, which is the JVM's
  behaviour on a modern runtime and beats preferring a base copy the build may have overlaid
  precisely because it does not work — `spring-core`'s own base `VirtualThreadDelegate`
  throws from every method.

### Added

- **The build's declared Java release is read** (W3b) — `maven.compiler.release` and its
  siblings on Maven, Gradle's own evaluated model on Gradle. **Nothing read any of them
  before**: `grep -rn "maven.compiler\|targetCompatibility\|sourceCompatibility" src/`
  returned nothing. §8.2 admits the value — it is written in the pom or build script, so it
  is code rather than a deployment possibility.

  **Maven** reads it from the `<properties>` already merged across parent inheritance, so no
  second walk of the ancestor chain is needed. maven-compiler-plugin's
  `<configuration><release>` is read FIRST, because `maven.compiler.release` is only the
  default expression for that parameter and an explicit configuration overrides it — then
  `release`, `target`, `source`, and `java.version`, which is the one Spring Boot's parent
  sets. `1.8` and `8` both reduce to 8; the legacy spelling is still what older builds carry
  and reading one form only would miss half the estate. A `${property}` nothing defines
  yields absence, not a guess.

  **Gradle is ASKED rather than parsed**: the value can come from a convention plugin, a
  toolchain or a property, and only the evaluated model knows which won. The init script
  reports `options.release`, falling back to `targetCompatibility`. Verified by a live run
  against `fixtures/gradle-orders` — both Java projects report 21, the root project (no Java
  plugin) reports absence — and the committed capture was brought in step with those
  measured values.

  A module whose build declares none reports `None`, which sends multi-release selection to
  its next source rather than to a wrong answer. **Its consumer is W3c**, still to come.

### Fixed

- **Multi-release jars stopped being scanned whole** (Fork 4, G-62), `fact_schema_version`
  4 → 5. `JarSource.names()` filtered on `.class` and nothing else, so every overlaid copy
  was scanned: the copies got different `document_id`s while minting the SAME type symbol,
  and no table downstream has a uniqueness constraint, so they became duplicate rows.

  **The manifest attribute gates everything, and it is read once per archive.** Without
  `Multi-Release: true` the JVM never searches `META-INF/versions/`, so those entries sit at
  a path no loader will look in — unreachable code whose symbols collide with the reachable
  base copies. They are now not scanned at all, which is different from treating them as
  ordinary classes. Measured on the real case: `testcontainers-2.0.5.jar` carries **1,218**
  versioned `.class` entries under a manifest holding only `Manifest-Version` and
  `Implementation-Version`; all 1,218 were scanned before and none are now. It is a parsed
  attribute lookup, never a grep — the jar spec makes attribute names case-insensitive and
  manifest values fold at 72 bytes with a leading-space continuation.

  **Where the attribute IS present, every copy is kept and TAGGED** with `class_release`.
  Nothing is selected here: which copy loads depends on the release the depending module
  targets, so one scan serves modules targeting different ones, and deciding in the
  extractor would force a re-scan per consumer and put a config-derived judgement inside the
  fact layer. Verified on `spring-core-7.0.9.jar`: 1,223 documents, tagged `base` 1,213 ·
  `21` 1 · `24` 9.

  **And an overlay stops naming a source file that cannot exist.** `sourcePathOf` yielded
  `META-INF/versions/21/org/…/VirtualThreadDelegate.java`, which names no file in any
  repository; the prefix is stripped first, so it now reads
  `org/springframework/core/task/VirtualThreadDelegate.java`. An overlay is a different
  COMPILATION of one source, not a different source.

  **Not yet done, and the tag alone changes nothing without it:** the duplicates are now
  LABELLED duplicates. The filter that acts on the label — highest `N ≤ target`, else base —
  is W3c, and the target it needs is W3b's declared-release read.

- **A parameter annotation on an enum or inner-class constructor landed on the wrong
  parameter** (Critical 6, JVMS 4.7.18). The parameter-annotation attribute may be SHORTER
  than the descriptor's parameter list, because javac omits parameters it synthesised, and
  the omitted ones are always LEADING — so entries align from the END. We never overrode
  `visitAnnotableParameterCount` and indexed from zero.

  Measured on a new fixture, and the shift is not a constant: **0** for a top-level class,
  **1** for an inner class (the outer instance), **2** for an enum (`$enum$name` and
  `$enum$ordinal`). All three are now pinned, including the shift-0 case — a fix that
  aligned from the end unconditionally would have broken every ordinary constructor, and
  one that hardcoded any single shift would pass one of the three tests.

  **The enum case is the one that mattered and the reason the spec required it.** There the
  hidden first parameter is also a `String`, so `@Labelled("display")` landed on
  `$enum$name` and no downstream type check could tell. Before: `param 0` carried the
  annotation and the real `display` at `param 2` carried none. After: it is on `param 2`.

  Scope stated rather than oversold: this needs a constructor that is BOTH annotated AND on
  an inner class or enum, so the real-world hit rate is low. It was a genuine fabrication
  with a small blast radius, not a widespread one.

### Added

- **`docs/COVERAGE.md` §3a — what we support, and at which versions**, so a user can see
  what they are accepting rather than inferring it from a tick in a matrix. Three things a
  coverage tick never said: the **language versions** the scanner can read at all (Java
  class-file majors 45–71, i.e. through JDK 27; Kotlin ≤ 2.2 for nullability, both bounded
  by the pinned libraries and both degrading to a named gap rather than a failed run); the
  **exact framework and library versions each catalog's rules were measured against**; and
  which catalogs measured **nothing**.

  **Measured points, not ranges** (ruled): every version listed is one whose bytecode was
  read. A version in between is *unverified, not unsupported* — stating a range would be a
  prediction about bytecode nobody opened, which §8.1 forbids and which produced several of
  the defects this plan exists to fix.

  Two findings the table makes unavoidable rather than merely available. **19 of 55 catalogs
  record no version** — including all four gRPC catalogs, both Pub/Sub halves, DGS, Spring
  GraphQL, Spring Integration, Cloud Stream and OpenFeign. That is a statement about our
  RECORD, not about the knowledge: several are bounded by a library Sextant itself ships and
  declares (`grpc-schema` by `grpcio-tools`/`protobuf`, `graphql-schema` by `graphql-core`),
  so the bound is already determinable and merely unwritten. Separating those from the ones
  that genuinely rest on documentation is deferred work, not unknowable work. And **Spring
  Boot 2 / Framework 5 is ruled in scope but measured almost nowhere**: the only pre-Jakarta
  evidence in the estate is Tomcat 9 for `javax-servlet`.

  Generated by `scripts/coverage_versions.py` from the catalogs' own `measured:` blocks and
  gated by `tests/architecture/test_coverage_versions.py`, so it cannot drift. The gate ships
  in the same commit as the generator deliberately: `scripts/coverage_matrix.py` regenerates
  §2 and **nothing runs it**, which is the "opt-in check nobody runs is not a net" lesson
  RUNBOOK already records, one document over.

### Changed

- **One unreadable class no longer takes the whole scan with it** (Critical 1's half that
  lasts). `Main`'s scan loop was wrapped whole in `catch (Exception)` and exited 1, so a
  single class file from a JDK ahead of our ASM destroyed every other class in the module —
  measured on `byte-buddy-1.18.11.jar`: exit 1, zero fact files. It is now a finding about
  ONE class, on the channel findings already ride (FR-17), carrying ASM's own words rather
  than a message of ours predicting them. **The document is still written**: its id, path,
  content hash and class-file major are all knowable without parsing it, and a class that
  vanishes silently is what FR-17 exists to prevent.

  The bump alone would have hidden this. A newer ASM raises the ceiling; it does not make a
  refusal visible.

- **A library no longer loses every readable class because one entry is bad, and the
  "discard the whole subtree" rule is GONE.** It existed because "a fraction of a library is
  indistinguishable, once loaded, from all of a smaller one" — true when a mid-archive
  failure meant the extractor died, leaving an arbitrary prefix. Measured on a three-entry
  jar with one corrupt entry: **exit 1, one document on disk**, nothing recording that two
  more were never attempted.

  The rule was never implemented; it was a side effect of that death. Removing the death
  without closing the hole beside it would have left the prefix silent, so **the archive read
  moved inside the per-entry guard**: a bad CRC or truncated deflate stream now yields a
  labelled `partial` document like any other failure. Same jar, re-measured: **exit 0, three
  of three documents**, the corrupt entry named in `uncovered`.

  With the scan complete, nothing is indistinguishable and the discard has nothing to
  protect — while discarding would MAXIMISE the gap it claimed to prevent, throwing away
  every readable class to hide one labelled one. A consumer resolving a type gets "not
  found" either way; the discard made that true for the whole jar instead of one class.

- **`partial` and `partial_reason` have a producer.** They were the literal strings `false`
  and `null` in every class document, with no code path able to set either — so
  `partial_documents` reached the rendered gaps list and a bundle's `coverage.partial` as a
  number that could only ever be zero. Two producers now, both matching D00's definition
  ("analysed incompletely, with a reason"): a class this build cannot parse, and a Kotlin
  class whose metadata a newer compiler wrote in a form it cannot decode.

- **A document records the class-file version it was read from** — `class_major`, a new
  `class_file_version` capability, `fact_schema_version` 3 → 4. Read from JVMS 4.1's fixed
  offset rather than from ASM's constant set, which runs ahead of the reader beside it: that
  is what makes the value available for a class the reader REFUSED, which is the case it
  exists to describe.

- **The accepted class-file range is a test, against real bytes.** `build.gradle.kts` has
  claimed since the ASM bump that the range "is pinned by a test in this same source tree"
  and **no such test existed** — the same class of unchecked claim about our own code this
  plan keeps finding. `ClassFileVersionTest` now rewrites the two `major_version` bytes of a
  real class file and asks the pinned ASM to read it, asserting both ends and deliberately
  probing past the ceiling so a library bump that moves it fails here instead of passing
  untested. Measured independently: **ASM 9.10.1 accepts majors 45–71 and refuses 72+.**

- **A version is recorded only where the thing can move independently of Sextant** (Step 1
  of Wave 1, ruled by the user). `scanner_version` is REMOVED from a document, and
  `fact_schema_version` goes to `3`. It named a version for facilities that ship inside the
  wheel and therefore have none of their own — `sextant-config-reader` and
  `sextant-detector` each stamped `"0.1.0"`, a hand-maintained copy of `sextant_version`
  that had never once differed from it. On the one facility that does run third-party code
  it read `"9.18"`, which is **capability** 9.18 wearing a library version's name while the
  pinned ASM was **9.10.1** — a value naming no ASM release at all, in the field a consumer
  reads to decide whether to trust a bundle. Tests held nine different fabricated values for
  it (9.7, 9.8, 9.12, 9.14, 9.16, 9.18, 1.0, 0.1.0, "0"), none of them the real one.

- **`metadata.json` records every facility that produced a document, not one.** The field has
  always been a LIST and was always handed a single entry, so on a fixture module two of the
  three producers were absent from provenance — `sextant-config-reader` (10 documents across
  avro, graphql, proto, wsdl, xsd and yaml) and `sextant-detector` (1). Only a facility
  running third-party code carries `libraries`, and those are the coordinates **Gradle
  resolved**, written into the jar manifest at build time so nothing in Java maintains a
  copy. `scanner_id` now names the facility rather than the library (`"asm"` →
  `"sextant-jvm-extractor"`), which is D00 §2's own rule and what made a library version
  look like the right thing to put beside it.

- **The extractor declares its own capabilities, over the subprocess contract it already
  answers scans on** (`--capabilities`, measured at 0.02s, cached per scanner). This
  implements a day-one contract that had never been built: D02 §3 says *"capabilities are
  scanner-declared — earned once, up front, by the scanner that produced a module's facts"*,
  and M03 puts `capabilities()` on the scanner's interface — but the fourteen-name set lived
  in Python, making an unverified claim about a subprocess built by a separate manual step.
  Capabilities gate which catalogs run, so a stale jar did not fail: it ran catalogs against
  fact kinds that jar never emitted, and the module reported an absence nothing could
  distinguish from a real one. A jar that is behind now reports fewer capabilities and the
  catalogs needing them are reported in `skipped_catalogs` — the visible degradation D02 §2
  already defines, so no new refusal was needed.

  **Consequence, recorded rather than discovered later** (M03): a command-line protocol
  assumes we control the scanner's entry point, so adopting a third-party analyzer we did
  not write means writing a WRAPPER that declares what it can read. Accepted deliberately —
  a third-party analyzer does not emit D00 facts either, so something has to stand between
  it and the workspace regardless, and inferring capabilities from a version string instead
  is precisely the mechanism that produced `"9.18"`: a version cannot be interrogated, only
  looked up in a hand-maintained table that is a second copy of the declaration with none
  of its authority.

- **`fact_schema_version` and `graph_schema_version` are single monotonically increasing
  integers, both set to `2`** (Step 0 of the Java/Kotlin v1 completeness plan, ruled by the
  user). Neither is ever parsed, ordered or compared for compatibility — `api._stale_stamps`
  compares each for equality and always has — so a dotted triple carried two numbers that
  meant nothing, in a text type that let copies of one stamp disagree unnoticed. **Every
  workspace written before this change is refused by the stamp gate, naming the stamp, and
  must be re-analysed.** That is the designed behaviour, not a migration: nothing is
  rewritten in place. Measured, so the shape of the refusal is not a surprise: `render`,
  `enrich` and `export` refuse at `api._stale_stamps` naming the stamp and both values, and a
  re-`analyze` over a workspace still holding pre-Step-0 fact files fails in
  `read_fact_file` with `fact_schema_version — Input should be a valid integer ... input_value='1.0.0'`.
  Both are loud and both name the field; neither migrates anything.

  The divergence this settles was live and undetected: `fact_schema_version` was maintained
  by hand in **four** places holding **two** values, and the one producer whose shape had
  actually changed — `ingress/read/*`, which gained `DeclaredShapeFact.operation` — was the
  copy that was never bumped. So every `.proto`, WSDL, Avro and GraphQL document on disk
  carried `operation` while stamping the version that predates it, with the whole suite
  green: nothing compared the copies, and the staleness gate reads `metadata.json` and never
  the documents.

- **The four copies of that stamp are gone, not merely tested.** `extractor-jvm`'s literal is
  deleted — the extractor is HANDED the value as a required `--fact-schema-version` option
  and refuses without it, so Python owns the number and nothing in a repository that cannot
  see a Python constant is asked to track one. The two Python restatements
  (`ingress/read/__init__.py`, `application/stages/analyze.py`) now import from
  `sextant.domain.version`; the layering always permitted it, and only `application`
  importing `ingress` was ever forbidden. `SEXTANT_VERSION` gets the same treatment in both
  directions: `--sextant-version` becomes required rather than defaulted in Java, and the
  Python constant is read from the installed distribution so `pyproject.toml` owns it.

- **Nothing is dropped on export (C10).** `_EXPORTED_TABLES` was eleven hand-written names;
  it is now **every table and view in the schema**, derived from the export queries
  themselves so the two cannot fall out of step. The seven that were silently omitted now
  travel: `raw_facts`, `call_edges` (1,393 rows on `mall-admin`), `return_flows` (444),
  `roots` (79), and the three views `config_entries`, `field_writes` and `method_returns`.
  A consumer can now recompute and check what a rendered trace asserts.

  **The ratchet inverts**: a table in the schema and absent from the export is a test
  failure, so the list cannot fall behind a new `CREATE TABLE`. It lands before anything that
  adds a table — two later items add three — because a safety net installed after the things
  it protects is not one.

  Redaction extends with it, answering the same question per column: `roots.path` joins the
  address map its value was carried from; `return_flows.value` and `method_returns.value`
  join the JSON map, since all four columns of that grammar are built from the same string
  constants; `config_entries.value` is masked by the same `redact_value` keyed on the same
  `key_path` that masks it in the fact stream; and `graph/raw_facts.parquet` joins the very
  map `facts/*.parquet` joins, so the two shapes of one table cannot disagree.

### Added

- **The vocabulary pass's own audit table is closed: none of the four annotations it left
  unmeasured is `@Repeatable`.** `spring-kafka.yml` and `spring-rabbit.yml` each gain a
  **CP-17** `measured:` row beside their CP-16 one — same artifact, same two versions,
  different question — and their handler entries stop saying "not measured at all".
  `@KafkaHandler` and `@RabbitHandler` are `@Target({METHOD, ANNOTATION_TYPE})` with no
  `@Repeatable` at spring-kafka 3.1.4/4.1.1 and spring-rabbit 3.1.4/4.1.1, and no
  `KafkaHandlers`/`RabbitHandlers` exists in any of the four jars. So the two catalogs'
  silence about a container is a **claim about the framework**, and `docs/COVERAGE.md`'s row
  asking for exactly this `javap` question is retired rather than restated.

  Of the four the audit named, three answers say the catalog was already right; the fourth
  (`@PulsarListener`) turned out to have a container the framework reads and the language
  never writes, which is why refusing to encode the predicted answer was worth the round.

- **Both legacy `@SqsListener` spellings are measured, and were already right** —
  `spring-sqs-legacy.yml` gains a `measured:` row per artifact (**CP-17**,
  `org.springframework.cloud:spring-cloud-aws-messaging` 2.2.6.RELEASE and
  `io.awspring.cloud:spring-cloud-aws-messaging` 2.4.4, each version read out of that jar's
  own manifest). Nothing about the catalog changed: both annotations declare exactly
  `value(): String[]` and a `deletionPolicy()` and nothing else, both are `@Target(METHOD)`
  so a class-level use is illegal rather than merely unmodelled, neither is `@Repeatable`,
  neither jar holds a container-shaped sibling, and `QueueMessageHandler` reads those two
  attributes and no third in either generation.

  Recorded as a result rather than passed over, because a pass that only retired entries it
  had to FIX would leave the correct catalogs permanently unmeasured. `_NOT_MEASURED_YET`
  drops to **19**.

- **SQS listeners have a class-level, polymorphic form, and this catalog said they had
  none** (`OI-40`) — Stage 4's per-catalog pass, measured by **CP-17** at
  spring-cloud-aws-sqs 3.1.1 and 4.1.1. `io.awspring.cloud.sqs.annotation.SqsHandler` was
  added at 4.1.1, `@SqsListener`'s `@Target` widened from `{METHOD}` to `{METHOD, TYPE}`, and
  the post-processor grew a branch that builds a `MultiMethodSqsEndpoint` from the
  **class-level** annotation's own `value()` and dispatches to every `@SqsHandler` method —
  read verbatim out of the sources jar, against the *same method* at 3.1.1, which has no such
  branch. `spring-sqs.yml`'s comment was true when it was written and had stopped being true,
  which is the version-scope failure §5.4 exists for; every `@SqsHandler` method in a 4.x
  module was absent from the export. Closed with the `spring-kafka.yml` prefix shape, and
  **no version constraint** — code built against 3.1.1 cannot carry an annotation that
  artifact does not declare.

  Also measured and found CORRECT: the `value`/`queueNames` `@AliasFor` pair at a second
  version, confirmed *by omission* — the post-processor reads `value()` alone at both, because
  the merge happens inside `findMergedAnnotation`. And `@SqsListener` names no container in
  any of its three spellings, which CP-17 measured rather than assumed. One new guard,
  mutation-proved: `spring-sqs.class-level-listener-is-the-prefix`.

- **Spring for Apache Pulsar's second inbound annotation, and its container** — Stage 4's
  per-catalog pass, measured by **CP-17**
  (`scripts/probes/cp17_containers_and_class_level.md`, spring-pulsar 1.2.11 and 2.0.7,
  both versions read out of each jar's own manifest).

  - **`@PulsarReader` is derived at all** (`OI-39`). It ships in the artifact
    `spring-pulsar.yml` already depends on, declares `topics(): java.lang.String[]`, and has
    its own post-processor, endpoint type and registrar — and the catalog named it **nowhere**,
    so every reader in a scanned module was absent from the export. A whole shape missing, not
    an attribute of one.
  - **A second `@PulsarListener` written into `@PulsarListeners` is derived** (`OI-38`) —
    `OI-36`'s silent drop one framework over, and by a **different mechanism**:
    `@PulsarListener` is *not* `@Repeatable`, so the container is one an author writes by hand
    and the framework registers the **union** of it and any direct use (read verbatim out of
    the sources jar at the same coordinate). The `container:` key the vocabulary pass shipped
    says that exactly — a class file does not record whose container it is — and only the
    documentation was narrower than the key. D02 §2 and two engine docstrings now say so; the
    key, the engine and every other catalog are unchanged. Needs extractor capability 9.16,
    which the catalog now `requires`.

  Also measured and found CORRECT, which is what makes the audit re-runnable rather than
  repeated: `@PulsarListener`'s `topics`/`topicPattern` split at a second version, and the
  claim that the framework ships **no** class-level handler annotation —
  `org.springframework.pulsar.annotation.PulsarHandler` is absent from both jars, so
  `prefix_from: []` is the framework's own rule rather than a simplification.

  Two new guards, both mutation-proved: `spring-pulsar.container-is-the-frameworks-own` and
  `spring-pulsar.reader-is-a-second-inbound-surface`. `spring-pulsar` leaves
  `_NOT_MEASURED_YET`, which drops to **20** (`OI-10`).

- **`annotation_driven` gains three words, designed as one pass** (D02 §2). The style
  **21 catalogs** share grew a key at a time against whichever framework was in front of its
  author, and Stage 4 found three catalogs at once whose framework rule was known exactly and
  whose grammar had no word for it — which is GUIDELINES §13.8's third occurrence. Each word
  names the measurement that forces it, each is optional, and each is inert while absent, so
  every catalog that declares none derives byte-identically.

  - **`mapping.annotations[].container`** — the repeatable container javac folds two uses of
    that annotation into. **CP-16**, six versions across three frameworks: the three listener
    annotations are each `@Repeatable` and each post-processor reads the container, while
    javac writes the container and *not* the member (JLS 9.7.5) — so a method carrying two
    listeners derived **nothing at all** (`OI-36`). The engine unfolds each container use into
    ordinary annotation rows before composition and inheritance, so there is no container in
    the query at all. Needs extractor capability 9.16.
  - **`mapping.path_from_siblings`** — ordered `{annotation, arg}` name sources that live on
    *other* annotations of the same declaration, consulted only where every `path_from` alias
    is absent. **CP-15 rows 1-2**: `getOperationName` consults five sources in order and takes
    the first with a value; the catalog read the first alone (`OI-35`).
  - **`mapping.annotations[].path_fallback`, and two new fallback words** —
    `read_accessor_property` (strips `get`, `is`) and `write_accessor_property` (strips
    `set`). **CP-15 rows 3-5**, row 5 *compiled and run*: the un-named-operation fallback is
    direction-dependent and the direction is chosen by which annotation matched, so one
    catalog-level word made one of two annotations newly wrong (`OI-5`).

  Five new guards, all measured to kill: `annotation_driven.folded-uses-are-read`,
  `annotation_driven.folded-entry-is-the-declared-annotation`,
  `derive_endpoints.sibling-name-source-order`,
  `derive_endpoints.path-fallback-is-per-annotation` and
  `derive_endpoints.accessor-strip-is-the-measured-one`.

- **`## Traces` draws every trace, and `render` has no display flag at all** (GUIDELINES
  §8.4, ruled 2026-09-06). `mall-admin` — one module, 157 classes — walks **160 traces**,
  and the document draws all of them: a **711 KB** `architecture.md` and a **4.6 MB**
  `architecture.html` with **161 diagrams**. That was briefly bounded to 37 traces by
  default, on the grounds that 711 KB is a document nobody opens, and the ruling reversed
  it: *"we should be focused on telling the truth, not the amount of information ... which
  is why we have indices planned for sextant, such that agents can leverage the truth +
  indices to quickly find things"*. **Completeness is the deliverable; a document too large
  to read linearly is a navigation problem**, solved by indices and by the agents that read
  it, never by leaving 123 walked traces undrawn.

  The bound survived one day longer as `sextant module render --brief` and was then
  **deleted outright** — *"deleting that --brief if it only cuts the first N. that's same
  as lying"*. What it drew was whole traces while a 500-step budget lasted, taken in the
  summary table's own order: an arbitrary **prefix**, presented as a reduced document.
  Saying in-band that it was reduced made the omission honest and never made the prefix a
  summary, and which traces a reader can spare is a judgement no renderer can compute — so
  a trimmed document is enrichment work (an LLM overlay), not a render flag: *"that's a
  different story and a different ask"*. Nothing in `## Traces` takes a bound now; every
  trace keeps its summary row, is drawn whole, and the section states the two counts —
  drawn and walked — that would differ if that ever stopped being true.

  Closes `OI-30`. Records `OI-31` (the 3.5 MB of inlined mermaid and the 161 eagerly
  rendered diagrams — a payload question, whose close is lazy per-diagram rendering and is
  **never** drawing fewer diagrams) and `OI-32` (`spring-petclinic-rest`'s pinned routes
  have been stale since 2O's identity migration, so that field pin has been failing
  unnoticed for a phase).

- **`macrozheng/mall` is a pinned, reproducible example** (`scripts/field-expectations/mall-admin.json`).
  It is the corpus every claim about document size in this repository is measured on, and
  it existed only in one session's scratch directory — so nobody else could re-measure any
  of them, which GUIDELINES §8.4 rule 4 forbids. It is carried exactly as every other
  example is (`examples/` is gitignored; the pin holds the `remote`, the `commit`, and the
  counts and routes recorded against it), with three new optional keys `field_check.py`
  needed to reach it: **`module`** (`mall-admin`, whose own `target/classes` decides
  whether a build is needed — the reactor root has none), **`maven`** (`mall` ships no
  `mvnw`), and **`jdk`** (`21` — a newer JDK breaks Lombok's annotation processor, and the
  pin is refused against Maven's own `-v` banner before anything is built rather than
  failing several screens into a stack trace). `README.md` carries the four commands.


- **A trace can be found by the URL a reader knows** (2Q close, defect 1). `## Traces`
  named every trace by its handler descriptor and its kind, so `GET /order/list` appeared
  nowhere in `mall-admin`'s section: finding the trace for an endpoint required already
  knowing the descriptor. **`roots` now carries the wire address** — `protocol`, `method`
  and `path`, one ROW per address and still one ROOT per (handler, kind), collapsed by
  `roots_of` so a handler serving three paths is one walk listing three ways in. The
  summary table gains a `Reached by` column and every block header names its addresses;
  both are composed by the same `_wire_address` the inbound endpoint table uses, so one
  address is never spelled two ways, and a `path` still passes the render exit's redactor.
  **A root nothing addresses says `no wire address`** rather than the em dash that means
  "nothing recorded" everywhere else: a scheduled job is started by a clock, and inventing
  a label for it would be fabrication. `OI-23` — an exposed address whose handler no chain
  reader named, and which therefore has no root at all — is unchanged and stays open.
  The join is made in `resolve/`, never in `egress`: a renderer that joins is deriving.
  `GRAPH_SCHEMA_VERSION` moves to **1.2.0**, because a 1.1.0 workspace's `roots` has no
  address columns at all and the read gate must refuse it rather than fail reading it.

- **A trace, in front of a reader** (2Q, closing `OI-25`). Everything before this produced
  tables; `sextant module render` now writes a **`## Traces`** section into
  `architecture.md` and `architecture.html` alike — one rendered trace and one Mermaid
  `sequenceDiagram` **per ROOT**, so a scheduled job gets both for the same reason an
  endpoint handler does.
  **Every step is a row and an arrow. Nothing is filtered.** The step table carries `Depth`,
  `Caller`, `Call`, `Dispatch`, `Resolution`, `Value`, `Returns` and `Stop`, and the walk's
  2,147 steps on `mall-admin` are 2,147 rows: a hidden call and an absent call are the same
  bytes to a reader, and this is the first document anyone reads a trace in.
  **The four places a reader could be misled are stated where they render.** A trace is
  reachability and never execution — said in the section preamble and again under every
  diagram; `revisited` keeps its row and says the subtree is at the callee's first
  appearance; nothing classifies a terminal, because `terminal_kind` has no producer and
  inventing one in `egress` would be derivation hiding in presentation; and a sibling
  build module reads `boundary` exactly as the JDK does, which the preamble says in
  capitals because `/order/list`'s own response composition is where it bites.
  **`MachineDiagram` gains `elides`**, mirroring `DiagramClaim.elides` field for field —
  markdown writes an `Elides:` line, HTML passes it to the diagram caption — and every
  trace diagram carries one, counted from that trace's own stops. `## Structure`'s class
  diagram passes `None` and is byte-identical to before.
  **An arrow ends at the body the walk expanded**, not at the interface the compiler named,
  with `(declared X)` on the message: drawing the interface leaves the implementation
  sending messages nobody sent it, which is a diagram a reader cannot follow. Two types
  whose simple names collide fall back to full descriptors, `_disambiguated_shape_names`'
  rule per diagram, because two lifelines labelled `Order` assert a call between things
  that never touched.
  **Verified against the vendored mermaid 11.17.2 build in a live browser**: all 161
  diagrams in `mall-admin`'s document render, 0 syntax errors, 160 captions. Two renders
  of one workspace are byte-identical (NFR-1).
  Two gaps retire BY NAME — `sequence_diagrams_pending_call_graph` and
  `call_graph_not_implemented` — and **five narrower ones** take their place, because what
  is still true of a trace is five separate things a reader can act on. Records `OI-27`
  (FR-6 says a trace is unbounded and stops only at a terminal; three things stop it
  earlier).

- **A stale workspace is refused instead of rendered short** (2Q, closing `OI-24`).
  [D01](docs/components/D01-graph-schema.md) §7 has said since Phase 1 that *"any Sextant
  version change re-derives, because derivation logic may have changed and there is no cheap
  way to know"* — and nothing compared a stamp. `api._stale_stamps` now does, inside the read
  gate `render`, `enrich` and `export` already share: `schema_version`,
  `provenance.sextant_version` and `provenance.fact_schema_version` are checked against the
  running build, an absent stamp counts as a mismatch, and a disagreement is a refusal naming
  the stamp that moved rather than a silent re-analysis.
  **It closes here because this is the change that made it live.** A workspace derived before
  `roots` and `call_edges` existed answers both queries with no rows, and an empty table is
  byte-identical to a module that has none — so `## Traces` would have rendered `None found.`
  for a service with 160 endpoints. `GRAPH_SCHEMA_VERSION` moves to **1.1.0** for the same
  reason: the two new derived tables are purely additive, and additive is exactly the shape a
  stamp has to catch, because nothing in the output looks wrong.

- **A trace, from a root to every terminal** (2Q, `G4` + `I3`). The thing this project has
  been asked for since day one, and the missing half of what `CONTEXT.md` promises. New
  derived table **`call_edges`** ([D01](docs/components/D01-graph-schema.md) §3) — one row
  per (call site, candidate callee), carrying `caller`, `ordinal`, `invoke_kind`, the bare
  `target` the compiler wrote, the module-prefixed `callee` whose body it reaches, `result`,
  `resolution` and `evidence` — and **`application/query/trace.py`**, a bounded,
  cycle-refusing walk over it.
  **It takes a ROOT, not an endpoint** (`I3`, the user's ruling: *a scheduled job still
  contains business logic, so there should still be sequence diagrams*). The walk reads
  `Root.kind` for exactly one purpose — carrying it back on the answer — and branches on it
  nowhere, so the third root kind costs nothing on the day it gains a producer.
  **`callee IS NULL` is the third-party boundary and the row is still written**: "this call
  leaves the module here" and "this method makes no calls" are different answers, and a
  table recording neither would report them identically.
  **A lambda body is reached, not stopped at.** An `invokedynamic` edge names the body the
  site CREATES (capability 9.17's `implementation`), never the bootstrap factory — closing
  `OI-14`, whose condition was a terminal reachable only through a lambda. Seven of
  `mall-admin`'s 160 traces have one.
  **Each step says why it was not expanded**, from a new closed set `TraceStop` —
  `boundary`, `cycle`, `revisited`, `depth_limit`. It is deliberately NOT D00 §4's
  `terminal_kind`, which classifies what a call REACHES and still has no producer, because
  three of its members need framework knowledge nothing has applied at a call site.
  **The depth bound is never silent**: `Trace.truncated` answers whether a walk is whole.
  **Measured on `macrozheng/mall`'s `mall-admin`**: 2,608 edges over 2,664 call sites (the
  56 without one are `invokedynamic` string concatenation, whose bootstrap is a compiler
  artifact); 1,966 boundary rows; 160 roots, all producing a trace, deepest 5 against a
  bound of 64. `GET /order/list` derives exactly the source: `OmsOrderService#list` →
  `OmsOrderServiceImpl#list` (sole implementation) → `PageHelper.startPage` and
  `OmsOrderDao#getList`, with `CommonPage#restPage` and `CommonResult#success` as the
  sibling-module terminals that compose the response. 155 roots reach a mapper or DAO
  terminal and three more an object-store client, which is the roadmap's 158 reproduced
  when the classification it used is applied by hand; the two that reach neither are
  `/admin/refreshToken` and `/aliyun/oss/callback`, as recorded.
  Closes `OI-14` and `OI-20`. Records `OI-24` (D01 §7's re-derivation rule is documentation,
  not code — G3's concern 3, verified), `OI-25` (nothing outside tests reads the walk) and
  `OI-26` (`SEXTANT_VERSION` is declared three times).

- **A scheduled job is a root, not a table nobody walks** (2Q, `I1`).
  [D00](docs/components/D00-fact-schema.md) §4 has documented a `root_kind` set for as long
  as the fact schema has existed and **nothing produced one** — entry #7 of
  [documented-not-implemented.md](docs/documented-not-implemented.md), and the reason
  `resolve/engines/scheduled_work.py` carried a docstring saying its own rows fed no root
  set. New derived table **`roots`** ([D01](docs/components/D01-graph-schema.md) §3): one
  row per (`handler`, `root_kind`), written from every `endpoints` row the module exposes
  and names a handler for, and from every `scheduled_work` handler.
  **A root is a place a walk starts, not an address.** A method serving three paths is ONE
  root — the walk is the same whichever path invoked it — so the fixture's 77
  handler-bearing endpoint rows collapse to 66 roots. A method that is both exposed and
  scheduled is two rows, because those are two different answers to "what starts this".
  **The member list is corrected as part of shipping it.** `http_inbound`, `soap_inbound`,
  `grpc_inbound` and `message_inbound` collapse to one `inbound_endpoint`: protocol is a
  property of an endpoint (`CONTEXT.md`), an inbound row already carries it, and
  `message_inbound` named a `message` protocol family this schema had already retired.
  `cli_entry` becomes `entry_point`, which is what `CONTEXT.md` calls it and claims no
  command-line surface nobody measured.
  **`entry_point` has no producer, deliberately.** Which signature starts a program is a
  LANGUAGE rule and ARCHITECTURE §10 keeps those out of the resolver, so it needs a
  catalog and none declares one. Recorded as `OI-22` and in
  [COVERAGE](docs/COVERAGE.md) §7 rather than left for a reader to discover. Closes
  register entry #7.

- **A value chain now crosses a method boundary** (2Q, `G3`). Within a method the chain was
  already complete — a `call_site` carries the value id its call produced, and every
  argument carries the `source` id of the call that produced it — so
  `OmsOrderService#list` → `CommonPage#restPage` → `CommonResult#success` was three facts.
  What nothing said is where the FIRST of those values came from. New derived table
  **`return_flows`** ([D01](docs/components/D01-graph-schema.md) §3): one row per (call
  site, candidate callee, callee return), carrying the caller's `result` id, the callee, its
  `return_ordinal`, what it hands back in D00 §5's argument grammar, and the site's
  `resolution`/`evidence`. It is the only thing licensed to cross a method boundary, and it
  does so by naming both sides — a `source` inside `value` is a value id in the CALLEE.
  **Caller to callee is arithmetic, not a lookup.** `domain/symbols.method_descriptor`
  composes the callee's descriptor from the call target's triple with the same first-four-
  bytes-of-SHA-256 disambiguator the extractor writes, so a callee outside the workspace
  matches nothing instead of raising.
  **The JVM's dispatch rule is mirrored, not approximated** (DR-6). `invokestatic` and
  `invokespecial` name the method that runs; `invokevirtual` and `invokeinterface` take the
  declared body plus every in-module override — one candidate is `resolved`, several are
  `narrowed` with all of them listed and none picked. `invokedynamic` contributes nothing:
  its `result` is the lambda INSTANCE, never anything the body returns.
  **Measured on `macrozheng/mall`'s `mall-admin`** (160 endpoints, Boot 3.x, JDK 21): 566
  rows over 552 call sites, of which 386 are direct and 166 resolve through a sole
  implementation. `OmsOrderController#list`'s value 7 is now stated to be what
  `OmsOrderServiceImpl#list` hands back, which is the result of `OmsOrderDao#getList` — the
  MyBatis terminal, checked against source. 1,411 of 2,065 value-producing call sites
  contribute no row, which is the ruled third-party boundary and the common case.
  Closes `OI-15`; `OI-14` is amended and stays open. `OI-16`, `OI-17` and `OI-18` recorded.
  **No consumer yet** — the reader is 2Q's `G4`.

- **What a method hands back is a fact — extractor capability 9.18** (2Q, `G2`). `ARETURN`
  appeared in the extractor only inside a comment, so the last link of a round trip was
  missing: an argument already carries the `source` id of the call that produced it, and
  nothing said which of a method's call results the METHOD returns. New fact kind
  **`method_return`** ([D00](docs/components/D00-fact-schema.md) §5), one per return
  instruction, carrying `method`, `ordinal` and `value`.
  **`value` is an entry of the argument grammar, not a bare id**, and that is what keeps two
  real answers apart: `null` means a `void` return pops nothing, `{"kind": "unresolved"}`
  means it pops something the pass could not name, and `{"kind": "unresolved", "source": N}`
  is the join. A returned literal, field, parameter or lambda reads exactly as it would in
  an argument slot in the same position, against the method's own declared return type.
  **Every return form, and nothing collapsed.** All six return opcodes; a method with two
  `return` statements yields two facts, told apart by `ordinal`, because a branch gives two
  possible answers and no single one. `ATHROW` is deliberately not one of them.
  807 facts on the orders-service fixture, 176 of them void returns and 62 methods carrying
  more than one. `scanner_version` moves `9.17` → `9.18`.
  **No consumer yet** — the reader is 2Q's `G3`, recorded as `OI-15`.

- **A lambda's body is named by the site that creates it — extractor capability 9.17**
  (2Q, `G1`). An `invokedynamic` call site recorded the BOOTSTRAP method and discarded the
  implementation, so the synthetic method javac lifts a lambda body into was extracted with
  its own symbol and its own call sites and referenced by nothing. `call_site` gains an
  optional **`implementation`** ([D00](docs/components/D00-fact-schema.md) §5): the symbol
  of the method the dispatch will run, read from the bootstrap's second argument. Seventeen
  bodies on the orders-service fixture, four of them Spring Cloud Stream `@Bean` methods
  that RETURN their lambda — the shape the existing `lambda` argument kind cannot see at
  all, because the lambda fills no argument slot.
  **Written only where the bootstrap names a method.** A `StringConcatFactory` site's
  bootstrap arguments are a format recipe, so the key is absent there and on every ordinary
  invoke, whose `target` already is the answer. Strictly additive: an engine that does not
  read it sees exactly what it saw before, and `scanner_version` moves `9.16` → `9.17` so a
  stale jar's silence is distinguishable from a module with no lambdas.
  **No consumer yet** — the reader is 2Q's `G3`/`G4`, and the honest state is recorded as
  `OI-14` rather than claimed here.

- **`@HttpExchange` faces both ways: `resolves.direction`, the direction flip** (2O design §6,
  Task 10). An `@HttpExchange` interface a local CONTROLLER implements now derives the INBOUND
  routes Spring actually serves, at the composed address, handled by the implementing class's
  own method — where before the module was published as CALLING a service it serves, and, after
  `A-C1`'s SEI fence turned that fabrication into silence, as neither. [D02](docs/components/D02-catalog-schema.md)
  §2c's `resolves.direction` is the mechanism, shipped on `spring-http-interface.yml` and read
  by no other catalog; the register entry that recorded it as documented-and-unbuilt closes with
  it.
  **The CONDITION is not the one D02 sketched, and that is the point.**
  `owner_implemented_in_module: true` is weaker than Spring's own rule and fabricates: measured
  on spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9 (`scripts/probes/cp7_http_exchange.md`),
  `isHandler` is one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call with
  no `@RequestMapping` disjunct, so a `@Service` implementing an exchange interface is
  dispatched to by nothing and an inbound row for one would invent an endpoint. The shipped
  condition names the controller annotations as catalog data — the same fqns `spring-mvc.yml`
  and `spring-web.yml` already declare — and resolves them through the composition pre-pass, so
  a module-local stereotype composed from `@Controller` counts. The type-HIERARCHY half of that
  predicate is deliberately not mirrored and aligns with COVERAGE's existing
  inherited-stereotype boundary.
  **Behaviour change for real modules:** on a module that both declares an `@HttpExchange`
  interface and implements it with a controller, rows that were absent become inbound endpoints;
  nothing moves in the other direction, and an interface with no local controller implementation
  keeps deriving exactly the outbound row it always did. Where the controller ALSO writes its
  own mapping for the same route, the two rows share a wire identity and the existing dedup
  folds them into one, with the implementing class's method surviving as handler — no collision
  detector is involved, because there is none.

- **Spring Integration's channels, enumerated and handed off** (2O design §5, Task 9).
  `config_join` gains a second binding-name source, **`binding.from: annotation_value`** — the
  name is the value of a declared argument on a declared annotation instead of a bean's own
  method name — and the destination side is unchanged, still `resolved_config` alone. The
  measured basis is `scripts/probes/spring-integration-destinations.md`: the channel join is
  real in both shapes, with the SAME literal on the annotation side and the call-site side.
  The new built-in `spring-integration.yml` declares **no `key`**, because Spring Integration
  defines no standard configuration key for a channel's destination and any template would be a
  project convention. It therefore derives **no endpoint row and no ghost row** and files one
  **`channel_destination` open question** per channel, carrying the channel name and the handler
  symbol — the enrichment seat's inbox, which is how "we cannot see it" becomes a route to an
  answer rather than a dead end. Never a fabricated wire, never `peer: in-process`. Three rules
  separate this source from the bean one and each is stated in [D02](docs/components/D02-catalog-schema.md):
  the annotation's target must be a METHOD, the value must be a non-empty string taken verbatim,
  and an unanswered name derives nothing at all. The questions ride the existing `gaps` seam
  (`resolve/service_identity.py`), which is the only place a pass may write to a ledger the
  pipeline resets after the engine loop.

- **The two NON-WIRE families: `scheduled_work` and `error_handlers`** (2O design §4). Work a
  framework starts on a clock, and the exceptions a module answers, each in a table of its own
  with the full derive → render → export chain: two engine styles (`scheduled_work`,
  `error_advice`), two catalogs (`spring-scheduling.yml`, `spring-advice.yml`), two D01 tables,
  two bundle artifacts and two document sections. **Neither reaches `endpoints`, and that is the
  design** — the endpoint table is wire-true, a scheduled method speaks no protocol and has no
  address, and an error handler is not a boundary anyone can address but what happens inside one
  that already exists. Giving either a wire identity would invent a route nothing serves.
  Schedule expressions are carried verbatim, with a property placeholder reported `unresolved`
  rather than substituted; an error handler's exception comes from the annotation's value, else
  from a parameter this workspace can PROVE is a throwable. Both tables are reset once per
  resolve from the pipeline, never by the engine, so a second catalog describing the same family
  cannot erase the first's rows.

- **`protocol` and `direction` may be ABSENT from a catalog, and only from a non-wire one**
  ([D02](docs/components/D02-catalog-schema.md) §1). Absence is a claim — "this catalog derives
  nothing addressable" — checked in `resolve/endpoints.py`, which refuses a wire style declaring
  neither and a non-wire style declaring either. A value outside D00's closed sets is still
  refused at the loader: a typo is not an absence. Writing one of the twelve protocols on a
  scheduling catalog to satisfy a required field would have put a wire claim in a shipped file
  that nothing reads and every reader believes.

- **CP-12: the framework surfaces the round-1b fix pass mirrors are measured**
  (`scripts/probes/cp12_sweep_round1b.md`). Eight Class A Majors share one shape — the catalog
  encodes a SUBSET of the framework's surface and no COVERAGE row names the rest — and CP-10's
  green table could not have caught any of them, because it asks whether every descriptor a
  catalog declares names a real method and never whether the framework declares one the catalog
  does not (`A-Mi5`). CP-12 asks that second question twelve times, and every answer is the
  framework's WHOLE set: `WebClient`/`RestClient`'s request starters and response-obtaining
  methods, Retrofit's method-targeted annotations with what each declares, every
  `KafkaProducer.send`, `KafkaConsumer.subscribe`/`assign` and `KafkaTemplate.send` overload,
  every `jakarta.jms.Session` receiver factory, `@SqsListener`'s attributes and its `@AliasFor`
  pair, and both WebFlux router DSLs' per-verb factories. Two Spring minors rather than one,
  because `A-M4` is a version finding in both directions at once. `tests/architecture/
  test_sweep_round1b_framework_surfaces.py` is the offline half.

- **CP-11: the four framework rules the principles-sweep fix pass mirrors are measured**
  (`scripts/probes/cp11_sweep_round1.md`). Each of `A-C2`, `A-C7`, `A-C1` and `A-C6` encoded a
  framework rule taken from documentation, a checkpoint note or memory, and each was plausible
  and wrong. The committed harness resolves each artifact through Maven, reads every jar's
  self-reported version out of the archive it opened — aborting rather than filling a
  mislabelled column — and asks `javap` four questions: OkHttp's complete `Request.Builder`
  verb-setter set, `RequestMappingHandlerMapping.isHandler`'s body across four Spring minors,
  which jakarta.websocket artifact declares which annotation and what each targets, and what
  `Retrofit.create` does with a non-interface. `tests/architecture/
  test_sweep_round1_framework_rules.py` is the offline half and pins the shipped catalogs
  against the generated table.

- **CP-10: every catalog `descriptor:` is now pinned to bytecode somebody read**
  (`scripts/probes/cp10_catalog_descriptors.md`, descriptor sweep R7). Load-time validation
  refuses a `descriptor` that is not a string opening with `(`, and that is all it can do: a
  wrong return type, a misspelled package or a stale erasure is well-formed and WRONG — it
  claims its candidate set in `_matching_method` and every overload of that name then derives
  nothing, with no error, no COVERAGE row, and every absence-asserting test still passing.
  The committed harness resolves each artifact through Maven, reads every `descriptor:` out
  of the shipped catalogs, indexes class → jar off the archives it opened, and asks
  `javap -p -s` whether the owner — or a superclass on the same classpath, which is what
  `SqsTemplate`'s inherited `send` needs — declares that exact erased descriptor. Each
  column is the version the JAR reported about itself, and a jar disagreeing with the
  coordinate that resolved it ABORTS the run (§5.4). `tests/architecture/test_catalog_descriptors.py`
  is the offline half: it pins the shipped catalogs against the generated table in both
  directions and fails on any verdict other than `declared`, so a descriptor added without
  re-running the harness fails the suite rather than going quiet.
- **Servlets: the oldest HTTP surface on the platform derives, under both package
  spellings** (2O design §3b, Task 7b). A new `supertype_dispatch` engine style
  (`jakarta-servlet.yml` and `javax-servlet.yml`) reads three pieces of evidence jointly —
  a TYPE-level `@WebServlet` for the address, `HttpServlet` for the dispatch contract, and
  the `doXxx` methods the class overrides for the verbs — none of which any shipped style
  could join: an annotation-driven derivation joins METHOD symbols and mints no row for a
  type-level annotation, and `supertype_derived`'s match requires a supertype whose own
  facts are in the module, which a container's abstract base never is. Every `urlPatterns`
  entry is its own endpoint; `value` is its alias, and a declaration writing BOTH derives
  nothing, because that is a deployment the container refuses and either value would then
  be a fabricated address. The member selector matches a name AND its parameter types in
  order, because that is how the language identifies a method (GUIDELINES §8.1):
  `doGet(String, HttpServletResponse)` overrides nothing and derives nothing, where a
  name-keyed selector would have published an address the container answers 405 to.
- **CP-9, measured live on three container majors** (`scripts/probes/cp9_servlet_shapes.md`,
  Apache Tomcat 10.1.50, 11.0.24 and 9.0.121, each column identified by the container the
  process itself reported). Its harness is committed beside it, deploys a real webapp so the
  CONTAINER's own annotation scan is what registers each servlet, and runs the committed
  extractor over the same build to record what actually reaches the fact stream. The
  questions the design left open are answered by measurement: **HEAD, OPTIONS and TRACE ARE
  served implicitly from `doGet`** and are deliberately NOT derived (the code serving them
  is in a container jar nothing scans, so the row would carry either no handler or a
  handler that does not serve that verb — the same ruling Task 6 made for Data REST); **an
  explicitly overridden `doTrace` IS dispatched to**, 200 over a connector that permits the
  method, so it is in the verb map with `allowTrace` recorded as a stated dependency rather
  than treated as proof the address is unserved; **the `javax.servlet` spelling behaves
  identically**, all 33 rows, which is why a second catalog ships instead of a stated
  boundary; and **a `protected` handler's recorded visibility is `other`, not
  `protected`**, so the style reads no visibility at all — an override may never narrow
  visibility, which makes the check both impossible and unnecessary.
- A class overriding `service()` derives **nothing**, and so does a `GenericServlet`
  subclass: the first replaces the verb dispatch itself and serves every verb alike
  (measured), so the verb map would publish a wrong verb set rather than a partial one;
  the second declares no HTTP verb semantics at all.
- **The one shape these catalogs over-report is stated and measured**: a module whose
  `WEB-INF/web.xml` declares `metadata-complete="true"` serves none of its annotated
  servlets — 404 on all three containers, same classes, one descriptor — and nothing in the
  pipeline reads a deployment descriptor, so every row is derived anyway. A COVERAGE
  boundary row in the over-report direction, closed by a descriptor reader.

- **The API nobody wrote a controller for: Spring Data REST routes derive** (2O design §2,
  Task 6). A new `derived_resource` engine style (`spring-data-rest.yml`) derives the CRUD
  route table from a repository INTERFACE — six routes per exposed repository plus one
  `/search/{query}` per query method — in a module that contains no controller, no mapping
  annotation and no string that is a URL. Every rule was verified against a live Boot 4.0.1
  / spring-data-rest 5.0.1 application (`scripts/probes/cp2_data_rest.md`): which item
  routes exist follows which CRUD contract is extended (a `PagingAndSortingRepository`-only
  repository serves a collection GET and nothing else), `path=` overrides the derived path,
  `exported = false` removes the repository, `@RestResource` renames or removes a search
  route, and which repositories are exposed at all follows
  `spring.data.rest.detection-strategy` — whose default exposes PUBLIC repositories only.
- **The dependency gate is real** (ruling R9). `detect.coordinates` was declared by every
  shipped catalog and read by nothing; it is now on the `Catalog` model and gates the one
  style whose framework rule is conditional on the library being present. The coordinates a
  module's build declares reach the workspace as D00 §5's `module` fact —
  constructed for the first time, from both detectors (Gradle's resolved compile classpath,
  Maven's direct POM declarations). A gated catalog whose question cannot be answered is
  reported SKIPPED with its reason, never derived and never silently omitted.
- **`domain/pluralize.py`** — a port of Evo Inflector's rule set, pinned by a differential
  run against the real library over every word in `/usr/share/dict/words`.
  `spring-data-rest-core` depends on that library non-optionally, so a working Data REST
  application always pluralizes its collection paths. A ported rule set is a derivative
  work, so Apache-2.0 §4's attribution travels with it:
  `src/sextant/domain/LICENSE-evo-inflector` carries the origin and the licence in full,
  named by the module docstring and by README's Dependencies section.
- **D02's `default_produces` is implemented** after being specified-not-used since 2E: read
  as a top-level catalog key, filling `produces` for rows no mapping declares a media type
  for. `application/hal+json → json` joins the shared `media_formats` table.
- A `static` helper declared on a Spring Data repository derives **no** `/search/` route:
  it is bound to the type, never to the repository's instance contract, so the framework
  serves nothing for it. The `method_visibility` query now projects the `static` modifier
  the extractor already emitted. A `default` method is still over-reported — `ACC_ABSTRACT`
  is not recorded, so nothing in the facts tells one from an abstract method — and that is
  now a stated boundary in COVERAGE rather than an undeclared one.
- The `environment_divergence` pass re-applies the CAPABILITY gate as well as the
  dependency gate, so a catalog `derive_endpoints` skipped for a missing capability can no
  longer file a question about a route it derived nothing for.
- A gated catalog's SKIPPED reason now carries Maven's direct-declarations-only caveat in
  the message itself, so "this module's build declares none of them" cannot be read as a
  confident negative for a starter inherited through a parent or a BOM. A module fact
  carrying no `dependency_coordinates` key at all degrades to that same SKIPPED path
  instead of aborting the resolve.
- **A new open-question kind is written**: `environment_divergence`, filed when
  `spring.data.rest.base-path` differs between environments — the derived rows then carry
  the configuration expression as their prefix at `unresolved`, rather than one
  environment's URL.
- **gRPC's JVM bytecode surface derives** (2O design §1b/§1c, Task 5), closing FR-3's
  last open protocol on the JVM alongside Task 4's schema half. Two new, framework-neutral
  engine styles: `supertype_derived` matches any class extending a generated
  `<Service>ImplBase` (`grpc-java.yml`) and derives one inbound row per overridden RPC
  method, reading the service identity and each wire method name off the generated
  class's own identity-building call-site arguments (`ServiceDescriptor.newBuilder`,
  `MethodDescriptor.generateFullMethodName`) rather than a field value — D00 §5's
  `constant` fact kind has no producer in this codebase (ruling R11). `injected_client`
  matches a net.devh `@GrpcClient`-injected stub field (`grpc-net-devh.yml`) and derives
  one outbound, service-level row (`method` NULL), fenced by symbol name against a service
  this module implements locally. Both merge with Task 4's descriptor-derived rows on the
  identical wire identity where both exist — and the merged row keeps BOTH halves: the
  bytecode's handler symbol plus the descriptor's request contract, response contract and
  streaming word, carried across by `stamp_declared_response.sql` and its new sibling
  `stamp_declared_request.sql` rather than by an insert the identity guard rejects. An
  unreadable identity derives an honest `unresolved` row plus a `service_identity` open
  question, never a fabricated package — and `supertype_derived` matches ONLY where the
  supertype's own generated class makes one of the marker calls, so ordinary class
  inheritance derives no row and files no question at all. Where two wire method names
  collapse onto one candidate override neither is attributed, and an override no wire
  name reaches is filed as a question rather than dropped silently.
- **`@GrpcService` corroboration** (`grpc-spring.yml`, Spring gRPC and net.devh
  spellings): a new `corroborates` block on `annotation_driven`, plus a `gaps` entry
  point beside `supertype_derived`'s and `injected_client`'s. It derives NO endpoint rows
  — the annotation names no service — and files a `service_identity` question for any
  class it flags that no gRPC endpoint names as a handler, which is the published-stubs
  case that previously produced nothing at all.
- **Five messaging and annotation catalogs** (2O Task 7): `spring-rabbit.yml`
  (`@RabbitListener`, plus the class-level `@RabbitListener` + `@RabbitHandler` shape),
  `spring-pulsar.yml` (`@PulsarListener`), `spring-rabbit-template.yml`
  (`RabbitTemplate.convertAndSend`), `spring-sqs-legacy.yml` (both older `@SqsListener`
  packages, so all three generations of the annotation now ship) and `spring-actuator.yml`
  (`@Endpoint` + `@ReadOperation`/`@WriteOperation`/`@DeleteOperation`). Every annotation's
  attribute shape was read off the real class files with `javap`, and the Actuator address
  and verb rules were confirmed live against Boot 3.5.10 AND 4.1.1
  (`scripts/probes/cp5_actuator_paths.md`, harness committed beside it).
- **`address_arg_2` — a composite outbound destination** (`single_call`). AMQP's wire
  identity is the exchange AND the routing key, which the one-address contract could not
  express: a row now names a second capture and a catalog-declared `address_separator`
  renders the pair as `exchange/routingKey`. An overload with no exchange is the routing key
  alone, and an explicitly empty exchange renders as the routing key alone too, so the two
  spellings of one destination stay one identity. If either half cannot be read the row
  publishes NO address — half a composite identity is a different destination, not a partial
  answer.
- **`path_prefix` — a framework's constant base path** (`annotation_driven`). A catalog may
  declare a fixed prefix that no annotation carries; it joins the front of the type-level
  prefix under the same deduping seam. Refused at load without a `path_separator`, since the
  two halves would otherwise concatenate bare.

- **A varargs argument's own elements are read, by all three consumers that wanted them**
  (2O Task 13). Extractor capability 9.15 models the array a varargs call site builds
  (`{"kind":"array","elements":[…]}`); nothing read it, so three declarations sitting in the
  facts derived nothing. All three now read it, through one conjunct
  (`resolve/shapes/arguments.py`'s `_array_elements`, guarded by the `array` kind and only
  that kind — an array the extractor could not read END TO END never reaches it and still
  degrades to `unresolved`):
  - `combinator`'s **media predicates** — `accept(MediaType...)`/`contentType(...)` fill
    `produces`/`consumes` where they always declared them.
  - `channel_via`'s **`all_strings`** — `Arrays.asList("t1","t2")` is genuine varargs and now
    resolves per topic, as `List.of` already did. The two spellings of one subscription answer
    alike.
  - `single_call`'s **`channel_arg`** — a destination slot holding an array derives ONE ROW PER
    ELEMENT, via the new `channels_of`. `WebSocketHandlerRegistry.addHandler(handler,
    String... paths)` registers one handler at every path named, so every path is a row.
  **Behaviour change for real modules**, all in the direction of columns that were NULL
  carrying values, none of it a new or changed endpoint identity: a WebFlux functional route
  declaring `accept`/`contentType` gains `produces`/`consumes` (and, with them, a rung-2
  answer from the format ladder where it previously fell to `unresolved`); a Kafka consumer
  subscribing through `Arrays.asList` gains one row per topic where it had one unresolved row;
  a Spring WebSocket registration gains its dispatch path, and a multi-path registration gains
  one row per path. `url_arg` is deliberately untouched — no shipped address capture is
  varargs, and CP-2's peer/path split has no measured meaning applied element-wise.

### Changed

- **One dispatch rule, in one place** (2Q, `G4`). Which method a call site can run moved out
  of `resolve/return_flow.py` into **`resolve/dispatch.py`**, unchanged, so `call_edges` and
  `return_flows` read the same answer rather than deriving it twice — `OI-16` already
  records that M04 §4's designed pass will one day be a second answer, and this keeps it
  from being a third. The move exposed one defect and fixed it: the "is this a method this
  workspace scanned" set was built from `method_symbols`, which excludes constructors by
  construct kind, so every `new` on a type the module declares read as the third-party
  boundary — 13 of `mall-admin`'s 1,979 boundary edges, and a constructor doing real work
  invisible to a trace. `return_flows` is unaffected and byte-identical (566 rows over 552
  sites, measured before and after). The two guards moved with the rule and are renamed
  `dispatch.callee-descriptor-is-stripped-to-bare` and
  `dispatch.exact-dispatch-admits-no-override`.

### Fixed

- **The extractor could not read a class file built by the current LTS JDK at all** (`OI-42`,
  the gap analysis's `G-3`). `org.ow2.asm:asm`, `asm-tree` and `asm-analysis` move **9.7 ->
  9.10.1** — the one dependency change in this group, approved by the user for exactly this
  reason (GUIDELINES §7 otherwise forbids it), with no other version touched.

  ASM's version *is* the class-file ceiling: 9.7 refuses `major_version` above **67** (JDK
  23), so a module compiled by JDK 24, 25 or 26 was refused outright — and the refusal took
  the whole scan with it, exit 1 with zero fact files. Measured before, on
  `byte-buddy-1.18.11.jar` from the local repository: `Unsupported class file major version
  68`, 0 documents. Measured after, same jar: **3,074 documents, 114,805 facts**. Eight of
  1,792 locally cached jars already carry a major above 67.

  **Measured, not assumed:** 9.10.1 parses majors **45 through 71** (`major = JDK + 44`, so
  Java 1.1 through JDK 27) and throws at 72 — measured by rewriting the two `major_version`
  bytes JVMS 4.1 fixes at offset 6 on a real class file and scanning it, at every major from
  45 to 72. The range is pinned as a test by the change below, so a later bump that moves the
  ceiling is caught rather than silently skipping class files ASM could have read.

  **The visitor API level is deliberately unchanged.** `Opcodes.ASM9` says which visitor
  callbacks this code is written against; it is a different concept from the class-file
  ceiling and raising it is not a side effect of reading newer bytecode. 9.10.1 offers no
  higher *stable* level: the only constant above `ASM9` is the deprecated
  `ASM10_EXPERIMENTAL`, and constructing a visitor with it throws — measured, this jar —
  `IllegalStateException: ASM10_EXPERIMENTAL can only be used by classes compiled with
  --enable-preview`. Taking it would therefore cost a `--enable-preview` compile and runtime
  for the whole extractor, on an API ASM itself marks unstable and deprecated, in exchange for
  callbacks describing JDK *preview* constructs this codebase reads nothing of. Not taken.

  **This moves the wall; it does not remove it.** The next JDK arrives on a schedule. The
  durable half — a class file above the ceiling is skipped rather than fatal — is `OI-42`'s
  remaining half and ships separately, so that this dependency change can be reverted on its
  own.

- **Four catalogs adopt the three new words, and three register rows close.**
  `spring-kafka.yml`, `spring-jms.yml` and `spring-rabbit.yml` each name their
  repeatable container, so a method carrying two listeners now exports both
  destinations instead of none (`OI-36`); all three gain a `nested_annotation_args`
  requirement, so a scanner that cannot read a folded use skips the catalog visibly
  rather than reporting half a module's listener surface.
  `microprofile-graphql.yml` reads all five of the operation-name sources SmallRye
  consults, in the measured order (`OI-35`), and falls back per annotation —
  `@Query` stripping `get`/`is`, `@Mutation` stripping `set` (`OI-5`). The
  characterisation test that asserted the wrong address now asserts the served one.

  **CP-15 gains a sixth question**, added because `OI-35`'s close needed an
  attribute name and rows 1-2 give annotation types: `getOneOfTheseMethodAnnotationsValue`
  reads each source's member named `value`, and an empty value stops the search
  rather than falling through. Taking that from the method's own name would have
  been §5.3's own failure, and Jackson's `@JsonProperty` declares six members.

  Five more guards, all measured to kill — one per catalog on the container fqn,
  plus `microprofile-graphql.fallback-direction-is-per-annotation` and
  `microprofile-graphql.name-sources-are-the-measured-annotations`.

  **`OI-37` is NOT closed**, and its row says why: two of the three annotation
  searches carry no strategy constant, so what they search is unmeasured. What the
  pass did settle is that `annotation_driven._synthetic_annotations`' claim that "a
  messaging listener annotation is never interface-inherited by its own framework"
  is false (CP-16 row 4e), and the comment no longer says it.

- **`config_join` asked the canonical-path seam nothing, on rows whose protocol and direction
  are both per-row** (2O Task 9 step 4; the Task 2 carry). `single_call` had the identical
  shape and the identical bug — its rows carried a per-row `direction` override while its seam
  read `catalog.direction`, so the gate answered about a different row from the one being
  minted — and `config_join` writes `path` from a destination whose protocol comes from the
  binder configuration and whose direction comes from a suffix or channel rule, with no seam at
  all. `_addressed` now asks `serves_urls` of the ROW's own two values. **No shipped catalog
  reaches the canonicalizing branch and no real module's output moves**: the branch is inbound
  HTTP alone and both shipped `config_join` catalogs speak broker protocols. It is pinned by
  two synthetic catalogs, one per binding source, each failing under either half of the wrong
  gate.

- **Two schema-describing documents said `open_questions.question` was a two-value set** while
  `resolve/open_questions.py` had enforced five since the start of Phase 2O
  (`docs/principles-sweep-2026-09-05.md`, `B-M1`). Corrected in
  [D01](docs/components/D01-graph-schema.md) and `storage/duckdb/schema.sql`, in the commit that
  shipped the writer the last of the three 2O kinds was waiting for — D01 now also names each
  kind's own `candidates` keys, which is what a reader of that table needs and what the
  renderer switches on.

- **`docs/COVERAGE.md` gave a stale reason for the WebFlux predicate-media boundary.** It said
  the `MediaType` vararg constants "compile through an `ANEWARRAY` the extractor cannot read",
  which stopped being true at extractor capability 9.15: the slot now carries
  `{"kind":"array","elements":[…]}`, and `combinator._media_value` answers for `string` and
  `enum` kinds with no case for `array`. What the row reports is unchanged; what would close it
  is engine work rather than an extractor candidate.

- **Five stale or unstated rationales corrected** (round-1 review, the minors it named).
  `spring-kafka-template.yml` said `sendDefault`'s arities 2/3/4 "remain undeclared" thirty
  lines above the rows declaring them, and its counts said "held six" and "the four that were
  missing" while enumerating five — it held five and five were added. `retrofit.yml` said
  "MEASURED, at retrofit 2.11.0" where the artifact states no version anywhere in its own
  bytes and CP-12's identity row prints `assumed` for that column alone: the label is the
  coordinate that was requested, which §5.4 separates from the observation. CP-12's
  `_declared` reads a type's DECLARED members and walks no supertype, which bounds every "the
  framework's whole set" answer in that probe and was disclosed nowhere — the probe and its
  document now say so, with the condition that falsifies it. `jakarta-jms.yml` justified one
  `channel_via` pair for all eleven consumer rows with "`Topic` and `Queue` both extend
  `Destination`", which is false for the eight `Topic`-typed rows: `createQueue` returns a
  `Queue`, so that half can never link there. And `A-M10`'s old-workspace incomparability was
  in COVERAGE only, where the person who can act on it — by re-running `analyze` — does not
  look; `README.md` now carries it, which is what §8.1 rule 3 asks of an escape that is a
  user action.

- **The call-site insert had no addresses-nothing gate, and `combinator` reached it**
  (round-1 review, MAJOR 6). `derive_endpoints.sql` has carried mechanism 3's gate since
  `A-C1` — a row whose address is empty and whose `peer` is NULL names no endpoint, and
  publishing one at `resolved`/`compiler` presents a boundary the running system does not
  serve as an observation. `derive_call_endpoints.sql`, which every call-site engine inserts
  through, had none: its only `WHERE NOT` was the dedup.

  `combinator` stamps `resolution: resolved` whenever nothing poisoned the read and returns a
  NULL path when a folded route accumulated no path part, so
  `RouterFunctions.route(RequestPredicates.accept("application/json"), handler)` inserted an
  inbound-HTTP row with a NULL method AND a NULL path, at the top evidence tier — and NULL
  paths skip the dedup key, so N such routes inserted N of them. Round 1b called this
  pre-existing and out of scope; it is the exact shape mechanism 3 exists for, and mechanism 3
  made the asymmetry sharper rather than softer.

  The gate is **scoped to `resolved`**, and the scope is the whole difference between a gate
  and a silent under-report: an `unresolved` row with no path is a real, distinct fact — "this
  method calls something whose destination nobody could read" — which the same file's dedup
  paragraph already turns on. A `resolved` row with no path claims the address was read and
  that there is none. It is also scoped to a **NULL** path rather than to an empty one: on
  this side a `path` is either an address an engine read or NULL, and whether an empty address
  is real is a protocol question `domain/paths.py` owns — `supertype_dispatch` publishes its
  patterns verbatim, so `@WebServlet(urlPatterns = "")` reaches this insert as `''` and no
  probe has measured what we should publish for it. The under-report the gate does trade for
  is stated in `docs/COVERAGE.md`: a constraint-only WebFlux route IS served and we cannot
  express its address.

  The test that asserted the old row now asserts emptiness, and `scripts/guard_check.py` kills
  it with the gate disabled. `spring-webflux-router` leaves the near-miss backlog.

- **`A-M9` closed one of FOUR WebFlux routing surfaces and COVERAGE claimed all four**
  (round-1 review, MAJOR 3). `docs/COVERAGE.md` listed
  `RouterFunctions.route().GET(…)` — the BUILDER DSL — as "✅ shipped", and the `A-M9` pass
  added "Both routing DSLs now read all seven verbs" beside it. `RouterFunctions$Builder`
  (seven verbs x four overloads) and `RouterFunctionDslKt.router` with `RouterFunctionDsl`
  (seven x five) are undeclared in `spring-webflux-router.yml`, unmentioned in any probe, and
  derive **nothing** — verified with `javap`/`unzip` against spring-webflux 6.1.6 and by
  driving the builder shape through the shipped catalog.

  **Both claims are corrected rather than the surfaces closed**, which is the honest half of
  the choice: the builder's verb call sits on a receiver returned by an argument-less
  `route()`, and the `combinator` grammar's entries are argument-rooted or body-linked with no
  word for that, so closing it is engine work plus a probe of which overload position carries
  the path. Two boundary rows name each surface with what falsifies it, and a test pins the
  builder DSL's silence so that closing it shows up as a failure rather than as nothing.

  This is an under-report and not a fabrication: the argument-less `route()` is not a root
  candidate, so no poisoned row is minted either.

- **Two near-misses declared coverage the guard harness measured as absent** (round-1 review,
  findings 7 and 8 — the harness's own first audit found both).

  The `spring-rabbit` `@RabbitHandler` near-miss named `derive_endpoints.qualifier-scope`, and
  `spring-rabbit.yml` declares no `requires_qualifier` at all — so that conjunct is a no-op
  for the catalog and the guard name was simply false. It names
  `derive_endpoints.addresses-nothing` now, the gate that really holds it up; that guard is
  registered for the first time, which closes one of sweep 1's four unnamed
  fabrication-prevention guards, and the qualifier gate is named by the invented-catalog
  near-miss that does reach it.

  The `spring-actuator` empty-`@Endpoint` near-miss is guarded twice over and pins neither
  half: making `@Endpoint` a mapping annotation mints a CLASS-target declaration, and the
  `construct_kind IN ('method', 'function')` join drops every one of those on its own account.
  Since `@Endpoint` is `@Target(TYPE)`, that weakening can never produce a row —
  `spring-actuator.operations-are-the-mapping-annotations` was a **no-op mutation**, which the
  harness's own design forbids counting, so the registry entry is removed and the test carries
  no marker and says why.

  `_DOES_NOT_DISCRIMINATE_YET` is now **empty**: `scripts/check.sh --guards` reports **31
  killed, 0 survived, 0 unmeasurable**. The harness's own self-test no longer depends on a live
  defect existing — it constructs a guard whose edit rewrites a comment, so that "the edit
  changes no behaviour" is a property the test guarantees rather than a fact about another
  test that any commit may change.

- **`A-M2`: a servlet whose `service()` override does NOT delegate published verbs the
  container does not dispatch, and `bypassed_by` was inert** (round-1 review, MAJOR 5 and
  MAJOR 4 — one change, because they are one defect seen from two ends).

  CP-9 rows 35-40 measured a DELEGATING `service()` wrapper — `super.service(req, resp)` with
  `doGet`/`doPost` declared — serving GET 200, POST 200 and refusing PUT with 405, and round
  1b correctly stopped discarding such a class. It then applied that verdict to every
  `service()` override declaring `doXxx`, which is §5.4's failure with the arrow reversed, and
  recorded the residual in COVERAGE as an accepted over-report. **CP-9 rows 41-43 now measure
  it**: the same class with the delegation removed serves GET 200, POST 200 and **PUT 200** on
  all three containers. The dispatch never runs, the `doXxx` methods are unreachable, and
  publishing the declared verbs while withholding one the container serves is a wrong answer
  rather than a partial one.

  **The distinguishing fact was always in the stream, and CP-9 rows 44-46 measure that too**:
  a delegating override's `super` call arrives as `invoke_kind: special` on an
  `HttpServlet#service` target — both entry-point signatures, both package spellings — where
  the non-delegating one's reads `ABSENT`. So the bypass now asks it, and `call_site` joins
  both servlet catalogs' `requires`; a scan producing no call sites SKIPS the catalog and says
  so rather than reading every wrapper as a replacement. No new catalog key: `bypassed_by`
  names the members, and what delegation means is `supertype_dispatch`'s own semantics.

  **This is also the `bypassed_by` decision (§5.3).** Under round 1b's `and not handlers`
  qualifier the key reached only classes another branch reached anyway — provably inert, dead
  catalog vocabulary that looked live, with three near-misses claiming to pin it and the guard
  harness measuring that none of them did. It is **kept and made load-bearing** rather than
  retired: the retirement case rested on the narrowing, and the narrowing was itself the
  defect. All three near-misses are rewritten to declare a `doXxx` — so there is something to
  lose — and `scripts/check.sh --guards` now kills all three.

- **`A-M13`'s own regression: a Spring Data custom-fragment method was published as a
  `/search/` route** (round-1 review, CRITICAL 2). The `A-M13` fix widened the query-method
  walk to cross every module-local superinterface, so
  `interface OrderRepository extends CrudRepository<Order, Long>, OrderRepositoryCustom`
  derived `GET /orders/search/searchByFullText` — a route Spring Data REST does not serve, on
  a method whose body lives in a hand-written `OrderRepositoryCustomImpl`. **Before the
  `A-M13` fix that input derived no search route at all.**

  CP-13 Q1 recorded `calculateQueryMethods`' filter and named `isCustomMethod` inside it; the
  fix read the ENUMERATION beside it and reasoned about the rest. Q6 and Q7 now open the
  filter, identical bytecode at spring-data-commons 3.2.5 and 4.1.1: `isCustomMethod` is
  `RepositoryComposition.getMethod(m) != null`, so a method the custom-fragment composition
  resolves is not a query method; and `FragmentMetadata.getFragmentInterfaces` is the
  repository interface's own `getInterfaceNames()` filtered to those NOT carrying
  `@NoRepositoryBean`. So the annotation — already catalog data, as `no_repository_bean` — is
  the whole of what tells a shared base from a fragment, and the walk now crosses only the
  annotated ones. Pinned by
  `derived_resource.inherited-interfaces-are-no-repository-beans` in `scripts/guard_check.py`.

  An under-report rides with it and is stated in `docs/COVERAGE.md`: a module-local base that
  extends a contract WITHOUT the annotation is a fragment by the same measured rule, so its
  query methods reach no `/search/` route on the repository deriving from it.

- **`A-M15`'s own regression: an OVERRIDDEN SOAP operation was published twice, and an
  `@WebMethod(exclude = true)` override republished the operation it withdraws** (round-1
  review, CRITICAL 1). The `A-M15` fix below widened the member rule to walk a gated class's
  superclass closure — correctly — and then enumerated **one row per declaration** where the
  enumeration it mirrors yields **one per signature**.

  MEASURED rather than reasoned (CP-13 Q5, on the JDK the probe process itself reported):
  `Class.getMethods()` over `class BillingWebService extends AbstractBilling`, both declaring
  `public String refund(String)`, returns `BillingWebService#refund` and NOT the base's. So a
  `@WebService` class overriding a base operation shipped **two** rows for one operation, the
  second handled by a class the RI never exposes; and where the override carried
  `@WebMethod(exclude = true)`, the annotated rule withdrew the override's row while the base's
  identical declaration walked past the member rule's anti-join and published the withdrawn
  operation at `resolved`/`compiler`, attributed to the base. **Before the `A-M15` fix that
  input derived nothing at all**, which makes this the one place the sweep's fix pass left the
  project worse than it found it.

  A new `exposed_members` CTE keeps the nearest declaration of each `(name, parameter types)` —
  the language's own key (GUIDELINES §8.1), never the descriptor hash, which covers the return
  type and would leave a covariant-return override undeduplicated — and the exclusions and the
  annotation anti-join are asked of that one member. `gate_ancestry` gained a `depth` and, with
  it, an explicit `walked` cycle guard, since the plain `UNION`'s deduplication stopped being
  one the moment two visits to an ancestor differed in a column. Pinned by
  `derive_endpoints.one-exposed-member-per-signature` in `scripts/guard_check.py`.

- **`A-M15`: a `@WebService` class's INHERITED operations were absent from its SOAP surface**
  (principles sweep §3.3). `derive_endpoints.sql`'s member rule joined the class gate on
  `s.enclosing`, which reads "the public methods of C" as "the public methods DECLARED in C" —
  JLS 8.2 says the members of a class include those inherited from its superclass, and
  `jakarta-jws.yml`'s own comment argues at length that an unannotated public method IS an
  operation ("a catalog that derived only the annotated methods would report a service missing
  one of its own operations") while the join made exactly that mistake one axis over.

  Measured rather than read off the specification's wording (CP-13 Q3/Q4, jaxws-rt 4.0.2):
  `RuntimeModeler.processClass` walks the implementor class's `Class.getMethods()`, drops only
  those declared by `java.lang.Object`, then applies `isWebMethodBySpec`. A new `gate_ancestry`
  CTE is that walk — the transitive superclass closure over capability 9.13's erased edge,
  `UNION` rather than `UNION ALL` so a fact stream disagreeing with its own language about
  cycles terminates instead of looping. Rows now carry the type that ANNOTATED them beside the
  method symbol, because an inherited member's declaring class carries no scope, prefix or
  construct gate; every catalog written before this carries it NULL and nothing about them
  changes.

  Two divergences from the RI are stated rather than closed: a `public final` method is exposed
  by us and not by JAX-WS, because `ClassScanner.methodModifiersJson` records neither
  `ACC_FINAL` nor `ACC_ABSTRACT`; and Apache CXF is not measured, so `jakarta-jws.yml` stops
  claiming it was "verified against BOTH reference implementations" without naming either
  (`A-Mi7`) and is scoped to the one CP-13 opened.

- **`A-M2`: a servlet that wraps `service()` and delegates lost its whole surface** (principles
  sweep §3.3). CP-9's verdict 8 — "a class overriding `service()` derives NOTHING" — was measured
  against `ServiceOnlyServlet`, which overrides `service()` and declares no `doXxx` **at all**,
  and was then applied to every `service()` override. The commonest real form is a cross-cutting
  wrapper that calls `super.service(req, resp)` and declares `doGet`/`doPost`, and it derived
  nothing: address, verbs and handlers, all silently absent. §5.4 in one line — a verdict is
  bounded by the configuration it measured.

  Re-measured rather than reasoned. CP-9 gains a delegating servlet on **both** `service`
  signatures (rows 35-40), because `HttpServlet` has two and a verdict read against one must not
  be applied to the other — which is this finding's own mistake. All three containers agree:
  GET 200, POST 200, **PUT 405**. The 405 is the discriminator: `HttpServlet`'s dispatch still
  runs, so the verb table describes such a class exactly. The bypass now discards a class only
  where it declares no member of the dispatch table.

  Three shipped tests asserted the defect — each declared a `doGet` beside the `service`
  override and expected nothing — and are corrected to the configuration CP-9 actually measured.
  The residual is stated in COVERAGE and is deliberate: a `service()` override that does NOT
  delegate and declares `doXxx` anyway now over-reports, because nothing in the fact stream
  separates it from the delegating form without `call_site` in the catalog's `requires`.

- **`A-M10`: an array had exactly one dimension** (principles sweep §3.3). ASM's
  `Type#getElementType` returns an array's **innermost** element type rather than its component
  type, and both `TypeRefs.descriptorName` and `TypeRefs.elementArguments` built their fact from
  it — so `descriptorName(getElementType()) + "[]"` appended exactly one `[]` however many the
  descriptor carried. `String[][]` and `String[]` produced **byte-identical** facts, symbol and
  argument alike, and JVMS 4.3.2 and JLS 10.1 make the number of `[` part of the type's
  identity: a DR-5 contract comparison of a caller sending `String[][]` against a callee
  expecting `String[]` read equal, and `shapes/expansion.py` hashed the wrong shape. The two
  seams also disagreed with each other — `NodeCollector.visitArrayType` recurses one dimension
  at a time on the signature path and was right, while the descriptor path, which is the one
  every plain array takes because javac writes no `Signature` attribute for one, was wrong.
  Both now drop one leading `[` and recurse.

- **`A-M16`: `.sextantignore` was loaded at the module root, so a reactor's never reached a
  submodule** (principles sweep §3.3). D04 §3 is emphatic and is itself an amendment — "One
  file, at the **repository root**, and every pattern in it is matched against a path made
  relative to THAT root" — and `analyze` loaded it at `module.root` while `api.py` analyzes each
  submodule with its own root. Both halves failed: the file was never read, and a pattern
  written relative to the reactor root would not have matched if it had been. The rules are now
  loaded at the root the run was invoked against, and the walk relativizes against
  `ignore.repo_root` rather than `module.root` so the two cannot drift apart by construction.
  A single-module repository is unchanged — the two roots coincide, which is why the old spelling
  looked right. **A module OUTSIDE the analysed root keeps its own**:
  `<module>../orders-service</module>` is legal Maven and `fixtures/orders-reactor` is exactly
  that shape, and a path outside a root has no root-relative form for a pattern to address. The
  built-in layer applies at every depth and always did, so this was a coverage gap in the
  repository-authored layer and never a credential leak. The enrichment jail's own
  load is unchanged and stated in D04: `enrich` is invoked against one module and has no reactor
  model to ask.

- **`stamp_media.sql`'s reach is settled** (principles sweep §7.4, where two sweeps touched the
  file and neither read it). Sweep 2's claim — "a stamp lands only where every resolved
  environment agrees, and never over a non-NULL column" — is TRUE, and two shipped tests already
  proved each half. Sweep 1's is half true: the UPDATE really does match on
  `(protocol, direction)` alone, so it stamps rows other catalogs derived — which is the
  mechanism, since `spring-kafka-media.yml` derives none of its own — but the CROSS-MODULE half
  is impossible, because `endpoints` has no module column, every module gets its own workspace,
  and `resolve()` runs once per module. What remains is an over-report onto a raw
  `KafkaProducer` row within one module, on a carried column rather than an identity one,
  bounded by the dependency gate and now stated in COVERAGE and pinned in both directions.

- **CP-13: what three frameworks do with an INHERITED member is now measured**
  (`scripts/probes/cp13_inherited_members.md`). `A-M13`, `A-M14` and `A-M15` encode the same
  invented rule — a type's members are the ones it DECLARES — and the sweep graded all three
  `read`, with the framework half explicitly unverified. The language half was never in doubt
  (JLS 8.2, 9.2, 9.4.1, 8.4.2); what needed measuring turns out to be answerable from bytecode
  without deploying anything, because in every case the question reduces to which reflective
  enumeration the framework calls and what it filters out of the result. Spring Data's
  `calculateQueryMethods` is `getRepositoryInterface().getMethods()`; its base-method lookup
  compares name, parameter count AND parameter types; the JAX-WS RI's `RuntimeModeler` walks the
  implementor's `getMethods()`, drops only `java.lang.Object`'s, and then excludes `static` and
  `final`. What it does NOT settle is stated in the probe: nothing was deployed, so a live run
  stays on the backlog and `A-M14` is left open on the strength of this rather than closed by it.

- **`A-M13`: a repository's query methods were the ones it DECLARED** (principles sweep §3.3).
  `derived_resource._methods` keys on `enclosing`, so
  `interface OrderRepository extends BaseRepo<Order, Long> {}` — the ordinary shared-base
  repository layer — exposed no search routes at all while the framework served every one of the
  base's. Silent, with no COVERAGE row. The walk now crosses module-local superinterfaces,
  own-first so an override shadows what it overrides, and stops short of a `contracts` entry.
  Measured, not assumed (CP-13 Q1): the framework enumerates `getMethods()`, which returns
  inherited interface methods, at both measured spring-data-commons minors.

- **`A-M12`: the payload-binding ancestry walk had `A-C4`'s invented rule too** (principles
  sweep §3.3). `shapes/parse_binding.py` built its ancestry from `supertypes` +
  `implementations` and never from `superclasses`, so a payload type whose only route to a
  protobuf marker is a non-generic `extends GeneratedMessage` reached nothing and bound nothing
  — an under-report, silent, with the endpoint keeping the bytes shape its signature declared.
  Two stale sentences went with it, both asserting that "a plain `extends` is NOT in the fact
  stream at all": the walk's own docstring and `spring-web.yml`'s protobuf comment. That was
  true when written and capability 9.13 falsified it — `supertype` is D00 §5a's
  parameterised-type carrier, `superclass` is the inheritance edge, and reading the first as
  the second is the rule `A-C4` names. `spring-web.yml` also stops asserting that the protobuf
  LITE runtime "reaches none of these and binds nothing", which nothing measured (`A-Mi2`).

- **`A-M1`: an overloaded receiver's handler was picked by descriptor hash order** (principles
  sweep §3.3). `interface_implementation` resolved a registration's receiver to a handler with a
  prefix scan over `method_symbols` ordered by symbol — a SHA-256 of the descriptor — taking the
  first match, and the comment defending it reasoned about the INTERFACE while the lookup ran
  against the implementing CLASS. Nothing stops a class declaring a private helper, a
  convenience form or a javac bridge beside its real override, so the "tiebreak" was a coin flip
  between two methods, one of which is wrong, published at `resolved`/`compiler` and carried
  into this engine's dedup key. The selector is now name AND parameter types (JLS 8.4.2), the
  rule `supertype_dispatch._members` already applies and which sweep 6 clears as this tree's
  reference implementation. One candidate resolves as before; several resolve only when the
  interface is itself scanned and its declared parameter types name one; otherwise the handler
  is NULL and the row still derives — which is what the engine's own docstring already promised
  and did not do.

- **`A-M9`: the WebFlux router catalog's verb vocabulary was the fixture's verb vocabulary**
  (principles sweep §3.3). `RequestPredicates` and `CoRouterFunctionDsl` each declare seven
  per-verb factories at spring-webflux 6.1.6 and 7.0.2 (CP-12 Q11/Q12), and
  `spring-webflux-router.yml` encoded GET/POST/HEAD in Java and GET/POST in Kotlin — exactly
  what `fixtures/orders-service`'s own two route files declare. An ordinary
  `RouterFunctions.route(RequestPredicates.PUT(…), …)` derived a row with neither verb nor
  address, and COVERAGE stated two WebFlux boundaries and named no verb gap. The catalog's own
  comment states the standard it was built to — "exactly what 2E's checkpoint froze against a
  real scan… nothing here is invented past that" — which, applied to a fixture rather than to
  the framework, is §8.1 rule 1's failure in the catalog's own words. Pure catalog data: nine
  new vocabulary rows, no engine change. `method(HttpMethod)`/`methods(HttpMethod...)` stay a
  stated boundary, because their verb is an enum constant argument and this grammar reads a verb
  only as a literal declared beside its owner.

- **`A-M6` / `A-M7`: four broker catalogs declared the arity their fixture happened to call**
  (principles sweep §3.3). `_matching_method` filters candidates on
  `row.get("arity") in (None, len(arguments))` **before** it consults a descriptor, so a call at
  an undeclared arity reaches no row at all and derives nothing. That silenced
  `producer.send(record, callback)` and `consumer.subscribe(topics, rebalanceListener)` — the
  idiomatic asynchronous producer call and the idiomatic consumer-group call — the four
  partition- and timestamp-carrying `KafkaTemplate.send`/`sendDefault` forms, and ten of
  `jakarta.jms.Session`'s eleven consumer factories, which is every selector-carrying consumer
  and every durable or shared subscription. COVERAGE listed all four catalogs "✅ shipped" with
  no arity qualification. Measured at kafka-clients 3.6.2, spring-kafka 3.1.4 and
  jakarta.jms-api 3.1.0 (CP-12 Q6-Q9), with every new descriptor pinned to bytecode by a
  re-run of CP-10. Each addition is a TRAILING argument, so every new row reads its
  destination at the position its sibling already does.

  Two exclusions are stated and pinned rather than left silent.
  `KafkaConsumer.assign(Collection<TopicPartition>)` carries its topic inside a constructor two
  hops from the call site, where every `channel_via` form is one hop; `Session.createBrowser`
  returns a `QueueBrowser`, which enumerates a queue without consuming from it, so an inbound
  row would claim a delivery the broker does not make.

- **`A-M5` / `A-M8`: two annotation catalogs read a subset of their annotation set** (principles
  sweep §3.3). `retrofit.yml` declared six of Retrofit's eight request-method annotations, so an
  `@OPTIONS("/x")` method derived nothing at all with no boundary stated; `@OPTIONS` now derives,
  and `@HTTP` is a boundary the suite pins rather than a silence — its verb is a plain `String`
  and `$method_from`'s read extracts an enum constant's name, so declaring it would ship
  `method: ''`, and a test goes red the moment somebody adds the row without changing the engine.
  `spring-sqs.yml` read `@SqsListener.value` alone while `queueNames()` carries
  `@AliasFor(value = "value")` — one attribute under two spellings, measured at
  spring-cloud-aws-sqs 3.1.1 (CP-12 Q10) — so a listener using the spelling AWS's own
  documentation uses composed an empty destination and the addresses-nothing gate withheld it:
  absent from the export, not present with a blank address. Both spellings are now read, `value`
  first, which mirrors `@AliasFor`'s own rule that the two can never carry different values.
  `retrofit` and `spring-sqs` leave the near-miss backlog.

- **`A-M3` / `A-M4`: the two Spring HTTP clients knew five of eight verbs, and a terminal set
  that was wrong at both measured Spring minors** (principles sweep §3.3). `spring-webclient.yml`
  and `spring-restclient.yml` each declared five request-starting roots —
  GET/POST/PUT/DELETE/PATCH, exactly the verb vocabulary the fixture happens to use — while both
  clients declare eight at 6.1.6 and 7.0.2 (CP-12 Q1/Q3). A chain rooted on an undeclared starter
  is never rooted at all, so `webClient.head().uri("/health").retrieve()` derived NO row and
  nothing said so. `head()` and `options()` now derive their own verb; `method(HttpMethod)`
  derives its address at `unresolved` with `method: NULL`, because its verb is an enum constant
  a string-literal scanner cannot read and withholding the call entirely would trade nothing for
  a silent drop. WebClient's `terminal: [retrieve, exchange]` was wrong in both directions at
  once: `exchangeToMono`/`exchangeToFlux` were in the list at neither version and are the only
  exchange-style terminals at 7.0.2, while `exchange` was **removed** in Spring 7. And
  `spring-restclient.yml` stated "no `exchange` on this synchronous surface" about a type
  declaring two `exchange` overloads at both minors. Every list is now measured, version-scoped
  in the catalog, and pinned against the **7.0.2** column so a dead entry is never made
  compulsory.

- **`A-C8`: ARCHITECTURE said redaction happens during extraction; it does not** (principles
  sweep §3.2). Masking runs at the two EXITS — `render` and `export` — and the workspace holds
  verbatim values, which D04 §4 has recorded as an approved amendment since 2026-09-02 and
  ARCHITECTURE was never updated (a §5.1 miss). The second sentence described a cache key, and
  there is no cache. A confidentiality claim (NFR-8) that was false in the first document a
  reader opens, and the one that decides whether somebody believes `<module>/.sextant/facts/**`
  is safe to copy, share or commit. Corrected in place, with the old text quoted so the
  correction is visible rather than silent.

- **`A-C9`: following the documented configuration aborted every command** (principles sweep
  §3.2). D04 §2 specifies `~/.sextant/config.yml` and a repository-root `sextant.yml`; neither
  is ever opened by anything. The file that IS read is the per-module `.sextant.yml` — one
  character from the documented repository name, with a closed key set — so in a single-module
  repository, where the two roots coincide, writing any documented key raised
  `SextantConfigError` and stopped the run, with a message saying only that the key is "read
  nowhere". That is equally true of a typo and points at nothing. The refusal now names the
  mistake: which file the key belongs to, and that Sextant does not read that file either.
  Amendment boxes in D04 §2 and D02 §6 say the same to a reader, and the register gains its
  missing row — including the standing ruling that project catalogs are deliberately
  unscheduled, so NFR-9's stated extension path is knowingly unmet.

- **`A-C3`: an endpoint returning no body was published as returning an object** (principles
  sweep §3.2). `WireTypes` mapped the primitive `void` to the empty string and let
  `java/lang/Void` fall through to `default -> "object"`, so `ResponseEntity<Void>` /
  `Mono<Void>` / `Call<Void>` — the idiomatic "no body" in nine catalogs' frameworks — published
  an object response shape AND filed `java/lang/Void#` as an unexpanded type, a gap report
  pointing at a type with nothing to expand. Thirty-three catalogs carried a `known_types`
  repair for it and nine did not; `derive_shapes` is global and insert-if-absent, so the first
  catalog to reach the type described it for every other one. Fixed in the projection, where it
  belongs: `java.lang.Void` is an uninstantiable placeholder whose only value is null, which is
  language knowledge and not catalog knowledge. A new architecture test refuses any catalog
  `known_types` entry that contradicts the extractor's own switch — the invariant twenty-eight
  catalog comments already claimed and nothing enforced.

- **`A-C1` / `A-C6`: four catalogs derived from evidence the framework does not act on**
  (principles sweep §3.2). `jakarta-websocket` and `spring-stomp` declared no type-level gate at
  all, so a lone method annotation minted a declaration — and with no class-level annotation to
  prefix it, at the EMPTY address. Worst of them: a `@ClientEndpoint` class, one that dials OUT,
  carrying the `@OnMessage` callback was published as an INBOUND WebSocket endpoint, direction
  inverted and address invented in one row. `retrofit` and `spring-http-interface` declared no
  `declared_on`, so an exchange annotation on a concrete CLASS derived an outbound row for a
  client the framework would never create. All four gates are now measured rather than chosen
  (CP-11): `@OnMessage` is `@Target(METHOD)`, addressless, and ships in the CLIENT api jar, so
  `@ServerEndpoint` is what makes a class served; Spring STOMP's `isHandler` is byte for byte
  the `@Controller` predicate Spring MVC runs; `Retrofit.create` throws on a non-interface; and
  `HttpServiceProxyFactory` proxies through Spring AOP's `ProxyFactory`, which asserts
  `isInterface`. **Output changes for real modules**: a WebSocket client, a STOMP handler on a
  non-`@Controller` class, and an exchange annotation on a concrete class all stop deriving. The
  stated cost is on the two outbound catalogs — `declared_on: interface` also engages the SEI
  fence, so a module that ships a local implementation of its own Retrofit or `@HttpExchange`
  client loses that client's rows; recorded in COVERAGE §5.2. Two under-reports `A-C1` names are
  stated rather than closed: a `@ServerEndpoint` class whose only lifecycle method is
  `@OnOpen`/`@OnClose`, and Spring RSocket controllers, whose routing annotation
  `spring-stomp.yml` claims and whose derived output is unverified.

- **`A-C7`: a custom stereotype deleted its controller's entire HTTP surface** (principles sweep
  §3.2). `spring-web`, `spring-mvc` and `spring-graphql` gated on string equality against one
  annotation FQN over a type's own direct annotations. Spring's rule is
  `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` — a four-instruction body,
  measured identical across spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9 (CP-11 Q2) — and that
  predicate is meta-annotation aware, so a controller wearing a module-local `@MyApi` composed
  from `@RestController` matched nothing and every one of its endpoints was silently absent from
  the export. The type gate now seeds the same composition closure the method-level mapping
  annotations already used, so the composition it was always able to see reaches it. **Output
  changes for real modules**: a module with its own composed stereotype gains its whole
  controller surface. Two of the three divergences the sweep names stay OPEN on purpose and are
  stated in COVERAGE §5.1: a stereotype inherited from a superclass or an interface makes
  `isHandler` true, but `@Component` is not `@Inherited` and whether component scanning admits
  such a class is unmeasured — deriving on half a rule is what §8.1 rule 4 forbids.

- **`A-C4`: a class inherited from its superclass only when the superclass was generic**
  (principles sweep §3.2). The annotation-inheritance walk read the `supertype` fact, which the
  extractor emits only where the superclass carries type ARGUMENTS, so `class OrderController
  extends PrefixBase` had no superclass edge at all — and since an absent prefix composes as the
  empty string, the child published `/{id}` where the framework serves `/api/orders/{id}`. A
  confidently wrong address at `resolved`/`compiler`, reached by a route neither `path_fallback`
  nor `canonical_path` guards. The walk now reads capability 9.13's erased `superclass` field,
  written for every non-`Object` superclass. **Output changes for real modules**: controllers
  extending a non-generic base gain the prefix and the inherited mappings the framework serves.
  The same edge retires the bare-to-prefixed lookback the old one needed, so an abstract base
  that declares no method at all — one whose only purpose is to carry a type-level
  `@RequestMapping` — is reachable too (`A-M11`).

- **Mechanism 3: the empty-address guard was keyed on a formatting property** (principles sweep
  §4, §7.7). `derive_endpoints.sql` dropped a row with an empty address only when the catalog
  declared no `path_separator` — a property about how two halves of an address are JOINED, which
  says nothing about whether the empty address means anything. The result was that a broker
  catalog whose destinations have no slashes was protected and its structural twin on a
  slash-separated protocol was not, because declaring a separator to compose destinations
  switched the twin's own validity gate off in the same line. Seven shipped catalogs declared one
  and were all unguarded. The gate now asks whether anything in the row names an endpoint at all:
  an empty address ships only where a resolved `peer` names the service, and the one protocol for
  which the empty address is real — an inbound HTTP root route — has already been spelled `/` by
  the canonical-address gate before this runs. **Output changes for real modules**: a
  `websocket`- or outbound-HTTP-shaped annotation catalog that composed an empty address stops
  publishing that row (`A-C1`'s fabrication half); inbound HTTP root routes, named destinations
  and Feign clients calling their base address are all unaffected. `docs/COVERAGE.md`'s claim
  that an unlisted destination attribute "derives a resolved row with an empty path today" was
  already false before this change and is corrected with it.

- **`A-C5`: a module with no Spring Cloud Stream asserted four Kafka boundaries** (principles
  sweep §3.2). `config_join`'s candidate scan reads every declared method and keeps the ones
  returning `Function`/`Consumer`/`Supplier` — platform interfaces, not framework ones — and with
  no `spring.cloud.function.definition` present the framework's own default binds every
  candidate, so three ordinary utility methods on a plain class published four boundaries the
  module does not have. `config_join` joins `derived_resource` in `DEPENDENCY_GATED`: the two
  styles whose evidence names no framework are the two gated on the build declaring it, and
  `resolve/dependencies.py` now records that test applied to all eleven styles. **Output changes
  for real modules**: a module whose recorded coordinates do not name
  `org.springframework.cloud:spring-cloud-stream` derives no Stream bindings and is reported
  SKIPPED with its reason; the same applies to `spring-kafka-media`'s media stamps and
  `org.springframework.kafka:spring-kafka`. Under Maven only DIRECT declarations are recorded,
  so a module inheriting either through a parent or a starter is skipped — the skip message says
  so, and the rows it loses are a Stream binding set or a carried media decoration, never a row
  another engine derived. `fixtures/orders-service` gained the `spring-cloud-stream` dependency
  it had always been modelling and never declared.

- **`A-C2`: OkHttp's `.method("DELETE", body)` no longer publishes `GET`** (principles sweep
  §3.2). `okhttp3.Request$Builder`'s generic verb setter was not a declared step, so it passed
  through uncaptured (D02 §4) and the chain root's `http_method: GET` — OkHttp's real default
  for a bare builder — stood uncorrected: a module issuing DELETE was published as issuing GET
  at `resolved`/`compiler`, where nothing downstream can tell an asserted verb from an observed
  one. The `fluent` grammar now accepts `http_method: argN` beside the literal spelling, and
  `okhttp.yml` declares the step. A verb the scanner cannot read as a string literal derives
  `method: NULL` at `unresolved` — the honest gap the catalog's own comment claimed to be
  taking while publishing a guess. Rows change for any module using
  `Request.Builder.method(...)`: previously one `GET` row per such call, now the real verb, or
  an unresolved row where the verb is computed.

- **A client held by its INTERFACE derives nothing, and that is now written down** (descriptor
  sweep R8). A call site records the compile-time qualifying type javac emitted, and every
  `single_call` client catalog declares a single concrete `matches.owner` — so
  `SqsOperations`, `AmqpTemplate`, `JmsOperations`, `KafkaOperations`, `RestOperations`,
  `WebServiceOperations`, `PubSubOperations`, `org.apache.kafka.clients.consumer.Consumer` and
  `jakarta.jms.QueueSession`/`TopicSession` calls match nothing at all. The highest-risk case
  is `SqsTemplate.newSyncTemplate(...)`, which **returns `SqsOperations`** — the idiomatic
  construction misses entirely, and both `send` arities are inherited so nothing anchors them
  to the class. This is an owner problem a descriptor cannot fix, and making `matches.owner`
  multi-valued is engine work that was out of scope for the sweep; recorded as a
  `docs/COVERAGE.md` boundary with its falsifier rather than left silent (§8.1 rule 3). The
  descriptors themselves are identical through either type, so they carry over unchanged when
  it closes.
- **`spring-resttemplate.yml` converts wholesale: seven rows become twenty-six** (descriptor
  sweep R4). Its rows carried neither `arity` nor `descriptor`, which makes each of them a
  candidate at EVERY argument count — so adding one descriptor to one row would have claimed
  every argument count for that name and silenced every other overload of it, with no error
  path. A half-conversion of this file is strictly worse than none, which is why it is all at
  once. The file was benign as it stood and that is said plainly rather than dressed up: what
  closes here is the shape that produced the AMQP, JMS and SOAP fabrications, not a live
  defect. Every `getForObject`, `getForEntity`, `postForObject`, `postForEntity`, `put`,
  `delete` and `exchange` overload `RestTemplate` declares now has its own row with both
  `arity` and `descriptor`; the two `exchange(RequestEntity, …)` forms, whose position 0 is
  not a url, declare no captures at all and keep deriving exactly the honest empty row they
  derived before. No golden-fixture output moved.
- **`spring-websocket.yml` said varargs make a three-argument call; they do not** (descriptor
  sweep R6). The catalog, a COVERAGE bullet and three tests all asserted that a multi-path
  `.addHandler(h, "/a", "/b")` "is a THREE-argument call this row's own `arity: 2` does not
  match at all", and that the two-argument shape was unverified. Measured by compiling both
  calls against spring-websocket 6.1.6 and running the shipped extractor: varargs collapse
  into ONE argument, so one path and two paths alike record exactly two arguments with an
  `array` at position 1. The row has always matched the multi-path call. The real boundary is
  narrower and worse — `channel_of` resolves only a `kind: "string"` argument, so
  `channel_arg: 1` can never resolve a path for ANY call, and every registration derives one
  honest row with `path` NULL. Stated in the catalog and in `docs/COVERAGE.md` with its
  falsifier, and named as Task 13's to close by wiring capability 9.15's `elements` read. The
  row also gains the erased descriptor of the interface's one declared method. **Not fixed
  here**: the capture is engine work, and this is a catalog sweep.
- **`JmsTemplate` publishes through two more overloads than the catalog admitted** (descriptor
  sweep R5). `convertAndSend(Destination, Object)` is an ordinary destination-carrying call
  whose argument 0 is a `Queue`/`Topic` instance and therefore can never fabricate anything;
  it derived an honest path-NULL row until the arity-2 descriptor claimed the arity, and that
  was a regression rather than a boundary. It has its own row again.
  `convertAndSend(String, Object, MessagePostProcessor)` was never declared at ANY arity, so
  every such call derived nothing at all — a recall gap nothing recorded — and the destination
  it carries is genuinely at position 0 and genuinely readable. Both are recall with no
  fabrication risk. The file now documents its own remaining boundaries, which it did not,
  though it makes the same claim `spring-rabbit-template.yml` documents in full.
- **A row that meant several overloads is now several rows** (descriptor sweep R3). Five
  catalogs carried one `methods` row standing for two real overloads, which is the language's
  own rule missing rather than a simplification: `KafkaConsumer.subscribe(Collection)` and
  `(Pattern)`; `PubSubTemplate.publish(String, T)` and `(String, PubsubMessage)`;
  `SqsTemplate.send` at both arity 1 and arity 2; and the `Message` siblings of
  `KafkaTemplate.send(ProducerRecord)` and `ReplyingKafkaTemplate.sendAndReceive(ProducerRecord)`.
  Each is now one row per overload, each with its own descriptor. **A single descriptor would
  have been the wrong fix in every one of these**: it claims the arity, so the undeclared
  sibling goes silent. `kafka-consumer`'s `channel_via` resolver list splits with the row —
  `List.of`/`Arrays.asList`/`Collections.singletonList` to the `Collection` overload,
  `Pattern.compile` to the `Pattern` one — and the two `Message` rows declare no capture keys
  at all (`spring-sqs-template.yml`'s precedent), which preserves today's honest empty row
  rather than spending recall to close an ambiguity. Three catalog comments asserting a second
  row at the same arity "would never be reached" were true of arity matching and are false
  under descriptor matching; all three are corrected.
- **Every unique-overload `methods` row now names the overload it means** (descriptor sweep
  R2). A row matched on name and argument COUNT is matching on a rule Java does not have —
  the language identifies a method by name and parameter types in order (GUIDELINES §8.1's
  language rule) — and the rows below happened to be unambiguous only because their jars
  declare one overload at that arity today. `google-pubsub-client`, `jakarta-jms` (both
  rows), `kafka-clients`, `spring-rabbit-template`'s arity-1 row and `spring-ws-template`'s
  arity-1 and arity-3 rows each declare their own erased descriptor. Nothing derived changes:
  a unique overload's descriptor can only equal what a matching call carries. What changes is
  the release that adds a sibling — it derives NOTHING instead of having its own argument 0
  read as a destination or a payload. The comments that said a unique overload needs no
  descriptor are corrected, each with the condition that falsifies it.
- **A SOAP request PAYLOAD could be published as the SOAP service's address** (descriptor
  sweep R1, §8). The same overload collision Task 7 closed for AMQP and JMS was still live
  in `spring-ws-template.yml`: `WebServiceTemplate.marshalSendAndReceive` declares
  `(String uri, Object payload)` AND `(Object payload, WebServiceMessageCallback after)` at
  arity 2 (javap -p -s, spring-ws-core 4.1.4), and the shipped row read position 0 as the
  address for both. `marshalSendAndReceive("PAYLOAD", message -> {...})` binds the callback
  form — a lambda is not compatible with the other overload's `Object` parameter, so javac
  picks it unambiguously — and the message body was published whole as `peer`, the remote
  service the module calls, at `evidence: compiler`. Reproduced end-to-end before it was
  fixed. The arity-2 row now declares its own erased descriptor. The file's own comment
  asserted this collision "never publishes a wrong row" and also counted arity 3 into it;
  both claims were false and are corrected — arity 3 is the only three-argument overload in
  that jar. The claimed arity's cost, a callback-form call now deriving nothing, is a stated
  boundary in `docs/COVERAGE.md`.
- **A message PAYLOAD could be published as a wire destination** (2O Task 7 review,
  §8). `single_call` selected a `methods` row by name and ARITY only, and both
  `RabbitTemplate.convertAndSend` and `JmsTemplate.convertAndSend` overload on argument type
  at the arities the shipped catalogs declare — arity 2 as well as arity 3, which neither
  file admitted. A call passing a `MessagePostProcessor` therefore reached a row expecting a
  destination at that position, and a string-literal payload was published as an AMQP or JMS
  destination at `resolved`/`compiler`, indistinguishable from an observation. A `methods`
  row may now declare the overload's own erased JVM `descriptor`, compared verbatim against
  the call site's `target.descriptor`; both shipped catalogs declare one per
  address-carrying row. Once any row for a name and arity declares a descriptor that arity
  is CLAIMED — an unmatched call derives NOTHING rather than falling through to a
  descriptor-less sibling, which is the fabrication the key exists to stop. The cost is a
  stated under-report in `docs/COVERAGE.md`: the undeclared overloads, which used to derive
  an `unresolved` row, now derive none.
- **The Actuator catalog's rows are now stated as conditional on WEB EXPOSURE** (§8, 2O
  Task 7 review). `management.endpoints.web.exposure.include` is Boot's gate on whether a
  custom `@Endpoint` is served over HTTP at all, and its default is `health` alone: measured
  on Boot 3.5.10 and 4.1.1, `/actuator/probe` is a **404** under the default while
  `/actuator/health` is a 200. Nothing in Sextant reads the key, so under a module's own
  defaults every `/actuator/<id>` published at `resolved`/`compiler` is a URL nothing
  serves. No derivation changed; the over-report is now a stated boundary in
  `docs/COVERAGE.md`, in the catalog and in the probe verdict, together with
  `@Endpoint(defaultAccess = Access.NONE)`, the same conjunct in miniature.
- **An annotation-derived path carrying an expression is no longer published as an
  observation** (§8). Every such row was stamped `resolved`/`compiler` unconditionally, so a
  destination written as SpEL `#{…}` or a property `${…}` was published as though the
  characters of the expression were the address. It now publishes `unresolved` with the
  expression VERBATIM — uncanonicalized, and never resolved: the config ladder is a
  call-site mechanism this derivation does not invoke. `domain/paths.py` learned the `#{`
  notation beside the `${` it already refused to rewrite.
- **A declaration that composes an EMPTY name derives no row.** For a catalog whose address
  is an opaque name rather than a sequence of segments (no `path_separator`), an empty
  composition is not a destination — nothing subscribes to it and nothing publishes to it —
  so the row is dropped instead of published as an endpoint addressing nothing. Two real
  shapes reached it: a member-level handler annotation outside the class-level annotation
  that would have named its destination, and a listener declaring its destination only
  through nested annotations no catalog reads yet. Segmented addresses are untouched: an
  empty segmented address is the base address itself.

### Changed

- **Endpoint identity for INBOUND `http` is now the URL the framework serves**
  (2O design §8, checkpoint CP-1 confirmed live against Boot 4.0.1).
  `@RequestMapping("users")` and `@RequestMapping("/users")` were two endpoint
  identities and are one; every combine boundary carries exactly one `/`; a
  trailing slash stays DISTINCT, because Framework 6 removed trailing-slash
  matching. A `path` holding a whole address or a placeholder-bearing
  composition (`https://${billing.host}/orders`) is untouched, and GraphQL
  (field names) and websocket/STOMP (a shared protocol with handshake-path
  rows) are out of scope. **Client-side HTTP rows are out of scope too**: a
  client's slashless path resolves against its configured base address's own
  path while a leading separator is root-relative, so canonicalizing one would
  rewrite an address rather than normalize a spelling. The rule and its gate
  live in `sextant.domain.paths`.
- **Spring Cloud Stream's `rabbit` binder now derives `amqp`, not `jms`**
  (2O design §3a). The `jms` stopgap was chosen when D00 had no AMQP member;
  keeping it would leave a Stream producer and a `@RabbitListener` consumer on
  different protocols permanently, and DR-5 gates linking on protocol equality.
- **The format ladder's rung 5 reads the evidence its documentation always
  described** (2O design §7, checkpoint CP-6). A `json_default_markers` entry
  may now be a dependency coordinate (`{coordinate: "group:artifact"}`) as well
  as a package family, and a package family is matched against every fqn the
  module names rather than annotations alone. Boot auto-configures Jackson's
  converter from the jar's mere presence, so a module carrying it answers
  `json` at `narrowed` even with no annotation anywhere.

- **Every rendered `architecture.md` now states the catalog-matching gap
  truthfully** (2O Task 12). `egress/render/document.py`'s `_GAPS` said *"every
  catalog's `detect.coordinates` is declared and read by nobody, so every
  catalog runs against every module"*. That has been false since 2O Task 6:
  the key IS read, by `application/resolve/dependencies.py`, and it skips —
  visibly, with a reason — the catalogs whose framework rule is conditional on
  the library being declared (`derived_resource` and `config_join` styles, four
  of the 55 shipped catalogs). **This changes the "what this cannot see" list of
  every document Sextant renders**, which is why it is here and not only in the
  sweep report; the `gaps` KEY in `metadata.json` is unchanged, because
  module-wide catalog activation is still unimplemented and that is what the key
  names. No endpoint row, count or identity moves.
- **`docs/components/D00-fact-schema.md`'s `protocol` list now names `amqp` and
  `pulsar`** (2O Task 12). Both have been in `domain/closed_sets.py` since Task 1
  and both are live; the schema document omitted them, which is a §5.1 violation
  rather than a schema change. `D06`'s verbless-render row gains them too. No
  code changes: the closed set is unchanged.
- **`docs/components/D02-catalog-schema.md` §2 no longer counts engines by
  counting headings** (2O Task 12). The two non-wire styles Task 8 shipped —
  `scheduled_work` and `error_advice` — have sections; the heading says "The
  styles" rather than "The thirteen styles"; and the preamble names the two
  sections that are NOT engines, `protocol_hint` (a resolve pass) and
  `filesystem` (specified, never implemented, and now carrying the
  "specified here, not yet used" box §5.3 asks for).

### Consequences of the identity migration — please read before upgrading

These four are the whole blast radius 2O design §8 names, and each is a
consequence of the same one change:

1. **Goldens moved.** Every recorded INBOUND HTTP path that omitted its
   leading separator now carries one. On this repository's own fixture that is
   no rows at all: every inbound route it declares already spelled its leading
   separator, and the two slashless declarations it has are client-side, which
   this change deliberately does not touch. A codebase with a slashless
   `@RequestMapping` will see those rows move.
2. **Curation and view overlays naming an old endpoint id are REJECTED WHOLE**
   by M01's existing rule — an overlay is validated as a unit, so one stale
   anchor rejects the file rather than silently dropping a claim. Re-anchor the
   overlay on the new id and re-apply.
3. **2N enrichment overlays anchored on old paths go STALE** and are dropped
   honestly at render (`stale_claims`) rather than rendered against a row they
   no longer name. Re-enriching is the documented remedy.
4. **`open_questions` snapshots re-derive** on the next analysis: the ledger is
   keyed on the wire identity, so a snapshot taken before this change names
   rows that no longer exist under those ids.
