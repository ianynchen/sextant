# Phase 2E — Spring HTTP inbound completeness

Four features close the gap between "annotation-declared HTTP endpoints" and "the ways
Spring services actually declare them": functional routing in both DSLs (the
`combinator` engine, the codebase's seventh style), module-local composed annotations,
mappings inherited from scanned interfaces and superclasses, and the declared media
types (`produces`/`consumes`) as two protocol-neutral endpoint columns. Plus the
ledgered docs carries. Zero extractor changes is the phase bet, checkpoint-verified.

User rulings binding this spec: Java `RouterFunctions` AND Kotlin `coRouter` both ship
this phase; media types land as two endpoint columns with the four-evidence-kind
semantics of §4 (settled through the cross-language verification — Go/Rust/Python/
JS/TS surveyed, including Flask/Django/DRF and Express/Koa/Hapi); the engine is
language-agnostic by construction, with the Java/Kotlin pair as the in-phase proof.

## 1. The `combinator` engine — the seventh style

`style: combinator`, `requires: [call_site, string_constants, chain_reconstruction]`.
A router is a tree of calls; every edge of that tree is already in the facts —
predicate arguments link via `source` to their producing calls, chains link via
result→receiver, handlers are `lambda`-kind arguments (method refs and lambdas both,
via 2C's indy facts), and `nest` subtrees are linked arguments one level deeper.

### 1a. Catalog grammar

The catalog declares three things:

- **Entry points** — where trees start. Two shapes, both catalog data:
  argument-rooted static calls (`RouterFunctions.route`, `RouterFunctions.nest`) and
  receiver-rooted builder calls (Kotlin's `coRouter`/`router`): the engine matches
  builder-node call sites **by owner** (the DSL type), grouped by their containing
  method, wherever the compiler put them. Kotlin suspend lambdas do NOT compile to
  indy synthetics — the DSL body may land in a generated inner class's `invoke`
  (its class file is scanned; 2C's nested-class work) or, for non-suspend bodies,
  in a synthetic method. The exact container per compiler version is checkpoint
  item (1b), not assumed here; owner-based matching works for either.
- **A vocabulary table** mapping owner+method to roles:
  - verb-sources: `RequestPredicates.GET("/x")` → verb `GET`, path at arg 0 (and the
    Kotlin builder's `GET("/x", handler)` two-argument form — one vocabulary, two
    arities);
  - prefix-sources: `path("/api")`, Kotlin's `"/api".nest { }`;
  - media predicates: `contentType(...)` fills `consumes`, `accept(...)` fills
    `produces` — request-matching semantics (a route guarded by `accept(JSON)` serves
    clients that accept JSON), frozen at the checkpoint against real facts, not
    assumed;
  - composers: `and` merges constraints; `or` duplicates the route per branch —
    over any predicate kind (verbs, paths, media), the `all_methods` precedent; an
    unresolvable branch derives its row unresolved rather than vanishing;
  - handler positions, three cases: a Java **method reference** (`handler::hello`)
    is an indy whose fact names the real referenced method — the handler symbol is
    the actual handler; a **lambda** resolves to its synthetic body's symbol; a
    Kotlin **suspend reference or adapted function object** may arrive as an
    `instance` of a generated class — the engine resolves what the facts support
    and emits handler NULL otherwise (never a fabricated encoding; every emitted
    symbol is resolved against the symbols facts, module-prefixed, per the 2E-prep
    interface-engine rule). What Kotlin's compiler makes recoverable is checkpoint
    item (1b).
- **Chain continuations** — `.andRoute`, `.andNest`, `.and`, `build` — merging route
  sets along result→receiver links.

### 1b. The walk

From each entry point, resolve every argument through its `source` link recursively:
predicate subtrees fold into (verb, path, consumes, produces); `nest` pushes its
prefix onto every route its subtree yields; chains merge route sets. Each leaf route
derives one row: `http`, `inbound`, the verb, prefix+path, the handler symbol,
`catalog_id`, media columns from predicates, `evidence: compiler`. Rows enter the
same `endpoints` table as every style, dedup and merge unchanged.

### 1c. Honesty rules

Any unresolvable part poisons exactly its own column: a variable path → `path` NULL,
`resolution: unresolved`; an unresolvable predicate subtree → that route unresolved;
a router composed from another method's `RouterFunction` (the walk is per-method by
design) → one unresolved row for the reference, never a silent absence. **Stated
limitation:** functional handlers' payload contracts are invisible in 2E — a handler's
signature is `ServerRequest → Mono<ServerResponse>`, so `request_shape`/
`response_shape` stay honestly NULL (the payloads live in `bodyToMono` calls inside
handler bodies — call-evidence work for a later phase; one COVERAGE sentence, and
`reactive_flow_not_traced`'s sentence is reworded in lockstep to cover it).

### 1d. Language-agnosticism, enforced in-phase

The engine sees only D00 facts and catalog data — no JVM grammar, no framework name,
no Kotlin-specific branch (a Kotlin `if` in engine code is a review-rejectable smell;
the two entry shapes are catalog declarations interpreted by one core). This is the
same discipline that makes axum's `Router::new().route(...)`, gin's registrations and
Express's `app.get(...)` future catalog files against this engine once their
languages' extractors emit the same fact grammar — the 2J zero-engine-changes test,
extended to languages.

## 2. Composed (meta-) annotations

The effective mapping-annotation set for `annotation_driven` widens from the
catalog's declared fqns to those **plus every module-local annotation type
transitively meta-annotated with one of them**. The chain is already facts: a
module's `@ApiGet` class is scanned, and its class-level `@GetMapping(...)` is an
ordinary annotation fact on its type symbol. A Python pre-pass (beside the reply
pass) computes the transitive closure — module-local, cycle-guarded — and hands the
derivation an expanded annotation list where each composed entry carries its
inherited defaults (the attribute values declared on the composition).

**Merge semantics — the honest subset, stated as such:** use-site attributes win over
the composition's declared values, which win over catalog defaulting (`all_methods`
etc.). This implements the common case of Spring's `@AliasFor` machinery, not its
full generality (explicit cross-name aliasing, `@AliasFor(annotation=...)`
re-targeting) — the boundary is one COVERAGE sentence, and the checkpoint freezes
what javac actually emits for a fixture composition.

Framework-internal composition (`@GetMapping` = `@RequestMapping(method=GET)`) stays
hand-copied catalog data — those class files live in unscanned jars. D02's existing
meta-annotation note updates: the module-local half now exists; the jar half awaits
dependency scanning. The mechanism applies to every `annotation_driven` catalog for
free — the fixture proves it with one HTTP composition and one messaging composition
(`@OrderTopicListener` composing `@KafkaListener`).

## 3. Inherited mappings

A handler method with no mapping of its own inherits from the same-**name+descriptor**
method on a scanned supertype or implemented interface — the OpenAPI-generator
pattern. The type edges are `implemented_interfaces` (2E-prep) and `supertype` (2A);
descriptor matching uses the bare-descriptor forms both symbol kinds carry.

**Resolution order, exact:** own annotations win outright; then directly implemented
interfaces in declaration order; then the superclass; applied transitively up scanned
chains. Two different interfaces both supplying mappings for one method is a genuine
conflict: the derivation takes the first in declaration order — deterministic, and
recorded as one COVERAGE sentence rather than a rendered note in 2E. Type-level prefixes join the same way (a
class-level `@RequestMapping` on the interface prefixes its inherited method
mappings), composing with §2 (an inherited composed annotation resolves through both
mechanisms — one fixture case proves the composition).

**Boundaries:** jar-defined interfaces are not scanned, so their mappings do not
derive — one COVERAGE sentence (the standing compiled-library boundary).
`handler_signature` comes from the implementing method, so shapes and nullability
derive from real implementation types.

**Home:** §2 and §3 share a pre-pass computing "effective annotations for a method",
living in its own module (`resolve/effective_annotations.py`) — deliberately NOT in
`annotation_driven.py`, which the 2D architecture review rated deteriorating for
absorbing exactly this kind of growth. The plan decides how much lands in the
pre-pass versus `derive_endpoints.sql`, optimizing for SQL readability.

## 4. The media-type columns

Two nullable TEXT columns on `endpoints` — `consumes`, `produces` — holding JSON
arrays of MIME strings verbatim, stamped by whichever engine derives the row.

**The rules, cross-language-verified and written into D01 verbatim:**

1. **NULL = no declaration derivable from any evidence source.** Never a guessed
   default: an undeclared Spring mapping is *negotiated at runtime* (converters +
   `Accept`), which is a different fact from a declared `["application/json"]` — a
   declared restriction 406s, an undeclared one does not.
2. **Four catalog-driven evidence kinds fill the lists:** (a) mapping attributes and
   route options (Spring `produces=`/`consumes=`, Hapi `payload.allow`, DRF
   per-view classes) — 2E implements this kind for Spring; (b) catalog-declared
   framework-contract defaults (`default_produces: [application/json]` for FastAPI,
   NestJS, tRPC — framework knowledge in catalogs, including type-conditional
   contracts like Flask's dict→JSON/str→HTML, which live in the call/type-evidence
   grammar); (c) call/type evidence (gin's `c.JSON`, axum's `Json<T>` extractors,
   Express's app-scoped `express.json()` middleware); (d) **config-declared
   defaults, arriving with 2F's `config_join`** (DRF `settings.py`, Spring's own
   content-negotiation properties, and — the messaging payoff — configured Kafka/JMS
   serializers, so kafka/jms rows' media types fill from configuration in 2F and
   feed 2G's format inference; a JSON producer versus an Avro consumer on one topic
   is exactly the payload-incompatibility DR-5 must see). Messaging rows are
   honestly NULL in 2E.
3. **MIME strings are the vocabulary** — byte-comparable across languages. DR-5's
   rule is conservative: NULL is compatible with everything; otherwise lists must
   intersect. Evidence-kind strictness (an enforced `produces=` versus an observed
   `c.JSON`) is deferred to L, where `catalog_id` already names each row's evidence
   provenance.

D02 gains `consumes_from`/`produces_from` alias lists on `annotation_driven` mappings
(read through §§2-3's composed and inherited paths too) and §1's media predicates;
the `default_produces`/`default_consumes` catalog vocabulary is specified now for the
frameworks that will use it (Spring's catalogs do not). Dedup and merge treat the
columns as carried data, never identity: wire identity stays (protocol, direction,
method, path). Rows differing only in media types are one endpoint: the union happens
**engine-side, within one derivation batch** (order-normalized — NFR-1), which is
where Spring's content-negotiated sibling mappings actually arise; across batches the
existing first-writer dedup stands, stated rather than silently assumed — no new SQL
merge machinery is promised. Rendering shows the lists compactly when present; the
D06 bundle carries them by construction.

## 5. Fixtures, testing, gaps, carries, close-out

**Fixture.** A Java `RouterFunctions` router (nested prefixes, an `or`'d verb,
`accept`/`contentType` predicates, a method-ref handler, a lambda handler, one
cross-method composition for the honest-unresolved case); a Kotlin `coRouter`
mirroring the core shapes (the fixture's first Kotlin code beyond contracts; the
build already compiles Kotlin); an `@ApiGet` HTTP composition and an
`@OrderTopicListener` messaging composition; an OpenAPI-style interface with mappings
plus its implementing controller, including one composed-and-inherited case AND one
covariant-return override (the name+descriptor join must miss it honestly, and must
not double-join on the compiler's bridge method); `produces`/`consumes` attributes on
existing MVC mappings. Kotlin needs `kotlinx-coroutines-core` and
`kotlinx-coroutines-reactor` in compile scope for suspend handlers (exact versions
checkpoint-resolved).

**Testing.** The four layers: engine unit tests for the walk (poisoning, `or`
duplication, nest prefixing, cross-method honesty, both entry shapes through one
core); pre-pass unit tests (closure, merge precedence, name+descriptor join,
conflict order); frozen exact sets extended once from live runs; the two-run and
double-run determinism tests (covering the new columns by construction);
loader-iterating compatibility pins sweeping the new catalog automatically; media
columns pinned per evidence path (declared, composed, inherited, predicate-derived,
and a NULL row staying NULL).

**Gaps.** No new keys expected; `reactive_flow_not_traced`'s sentence rewords in
lockstep to also cover invisible functional-handler payloads; the plan verifies
against the live list.

**Docs carries (ledgered, fold into the docs tasks):** the roadmap 2E row renames to
"Spring HTTP inbound completeness" with the GraphQL/WebSocket/SSE→2H, SOAP→2I note;
the three fluent-HTTP catalogs' stale `_owns` rationale and the eleven "harvest
compatibility" pointer labels correct to the shape-expansion reason; D02's
meta-annotation note updates per §2.

**Close-out** as always: COVERAGE flips (WebFlux functional routing incl. `coRouter`,
meta-annotations, inherited mappings, `produces`/`consumes`), matrix regen +
`--check`, roadmap 2E → delivered, fact volume measured against the pre-phase
baseline.

## 6. Checkpoint — frozen from reality after the fixture task

(1) Both DSLs' real bytecode shapes proving the zero-extractor-changes bet, or
falsifying it before catalog tasks dispatch — (1a) the Java static-call tree and
method-ref indy facts; (1b) Kotlin: WHERE the DSL body's calls land (inner-class
`invoke` vs synthetic method), what kind the handler argument carries (adapted
function object vs reference), and what is honestly recoverable as the handler
symbol; (2) the composed annotation's emitted attribute placement (use-site value vs
composition defaults) AND its retention/visibility in bytecode (Spring requires
RUNTIME retention so real compositions carry it — verified, not assumed); (3) `accept`/`contentType`
call-site fact shapes and the exact `MediaType` constant forms (inlined literals vs
enum-like fields — the media predicates' reader is written against what is emitted);
(4) the interface/controller method-symbol descriptor forms the §3 join keys on,
including the bridge-method fact shape for the covariant fixture case;
(5) the exact route additions frozen for the catalog tasks.

## 7. Review discipline

The final whole-branch review receives the explicit seam list: the combinator engine
× the §2/§3 pre-pass; the pre-pass × `derive_endpoints.sql`; the media columns ×
dedup/merge/rendering; the Java × Kotlin entry shapes sharing one core; the new
columns × the D06 bundle and determinism tests.
