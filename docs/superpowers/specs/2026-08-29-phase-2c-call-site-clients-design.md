# Phase 2C — Call-site HTTP clients: design

**Approved through brainstorming, 2026-08-29.** This spec is the authority for the Phase 2C
implementation plan. It follows Phase 2B (outbound annotation clients and export, PR #3)
and implements the call-site half of Spring Boot's outbound surface: RestTemplate,
WebClient, RestClient and OkHttp, in one phase — the user's explicit scope choice over a
recommended two-phase split, taken with the safeguards in §7.

**Goal.** An HTTP call whose URL and verb live in *method calls* rather than annotations
derives an outbound endpoint with its payload contract — including calls made inside
lambdas — on facts rich enough that the later call-graph, linking and enrich phases never
re-extract what this phase already saw.

**Scope decisions taken with the user:**

- All four call-site clients in one phase (the two-phase split was offered and declined).
- Approach A: the extractor emits **linked** `call_site` facts (per-method value ids for
  receiver and result); the `single_call` and `fluent` engines stay generic, catalog-driven
  interpreters in the derivation. Bytecode dataflow is language knowledge and lives in the
  extractor (D1's line); which chain steps matter is framework knowledge and lives in
  catalogs (D02's first rule).
- `constant_propagation` stays out: javac folds compile-time constant expressions
  (`BASE + "/orders"` with a `static final` is one literal in bytecode), so
  `string_constants` covers the common assembled-URL case; runtime-assembled values are
  honestly `unresolved`.
- `ParameterizedTypeReference` support is **in** (user ruling — request/response typing
  cannot silently drop it), which pulls nested-and-anonymous-class scanning into this
  phase and retires that phase-1 gap entirely.
- Base URLs configured in builder/config code remain deferred to Phase 2F (configuration
  resolution) — the named gap `client_base_addresses_not_resolved` continues to cover
  them, and D02 §2d plus D01's `resolved_config` table are the reserved landing places.

---

## 1. The `call_site` fact and the dataflow pass (extractor)

D00 §5 reserves the fact kind; this phase amends §5 to state the full shape:

```json
{"kind": "call_site", "document_id": "…", "caller": "<method symbol>",
 "target": {"owner": "org/springframework/web/client/RestTemplate#",
            "name": "postForObject", "descriptor": "(…)…"},
 "invoke_kind": "virtual",
 "ordinal": 14,
 "receiver": 3, "result": 7,
 "arguments": [
   {"kind": "string", "value": "/billing/invoices"},
   {"kind": "unresolved", "source": 7},
   {"kind": "class", "symbol": "com/acme/orders/contracts/OrderView#"}]}
```

- **`ordinal`** — the invoke's index within its method. Deterministic, and it is the v1 of
  the control-flow position D00's table names, so the call-graph phase starts from these
  facts. Richer control-flow context (loop/branch nesting) will be an *enrichment* of this
  field in that phase; D01 §7's schema versioning prices the re-extraction openly.
- **`receiver` / `result`** — per-method value ids from the dataflow pass; `receiver`
  null for statics, `result` null for void. Deliberately meaningless across methods:
  chain reconstruction is within-method, and a chain that crosses a method boundary stops
  honestly.
- **`arguments`** — one entry per slot, resolved by walking the frame to each slot's
  source instruction. Kinds:

| Kind | Source instruction | Notes |
|---|---|---|
| `string` | LDC (incl. javac-folded constants) | the URL/topic carrier |
| `int` / `long` / `boolean` | constant instructions | |
| `enum` | GETSTATIC on an enum type | symbol reference — `HttpMethod.POST` |
| `class` | LDC of a class constant | symbol reference — the shape root |
| `lambda` | invokedynamic via `LambdaMetafactory` | symbol reference to the lambda's
  synthetic body method — method references resolve the same way |
| `instance` | NEW/constructor result | the concrete type's symbol — feeds PTR and the
  one-hop body follow |
| `null` | ACONST_NULL | |
| `unresolved` | anything else | a first-class honest answer, never an omission |

  Every entry additionally carries an optional **`source`** value id when the argument is
  another call's result — the join that makes OkHttp's `build()` → `newCall(request)`
  split reconstructable, and the `HttpEntity` one-hop follow possible. One grammar, three
  consumers.

**The pass.** A per-method ASM dataflow analysis (`Analyzer` with a source-tracking
interpreter) computes, for every invoke, the source of each argument slot and of the
receiver, assigning value ids in instruction order (deterministic — NFR-1). It lands in
its own class (`MethodFlow.java`), with `ClassScanner` only wiring the visitor (§6, D3).
Lambda bodies are ordinary synthetic methods and are scanned like any other, so calls made
inside `flatMap(x -> …)` derive endpoints normally; the `lambda` argument kind records the
linkage from the `flatMap` call to that body for the call-graph phase to interpret.

**Capabilities declared:** `call_site`, `string_constants`, `chain_reconstruction`
(the last meaning "receiver/result links are present"). `invokedynamic` stays undeclared;
indy *call sites themselves* are recorded with `unresolved` arguments (runtime string
concat is indy on modern javac — refusing to guess it is the point).

**Volume.** All call sites are emitted — they are the call-graph phase's substrate, and an
owner filter would smuggle framework knowledge into the scanner. The plan measures the
fact-count delta on the fixture; the escape hatch, decided only with numbers, is an
origin-tier emission filter.

### Completeness sweep (user-requested; what every future consumer needs)

Captured and interpreted now: direct chains including inside lambda bodies; folded string
constants; enum verbs; class-literal responses; method references; field-held clients
(steps match by target owner); Kotlin inline/reified helpers (inlining exposes the real
calls). Captured as facts, interpreted later: the `flatMap` flow linkage (call-graph);
`uri(uriBuilder -> …)` — lambda linkage recorded, URL honestly `unresolved` until a
fluent-engine extension follows one hop; loop/branch context (control-flow phase enriches
`ordinal`). Not captured, each named: runtime-assembled strings (`unresolved` +
constant-propagation deferral); varargs contents (URI variables do not change the wire
identity); config-time base URLs (2F).

## 2. Nested classes and `ParameterizedTypeReference`

Four bounded pieces:

1. The phase-1 skip on nested and anonymous classes is lifted — they are ordinary class
   files. The `nested_and_anonymous_classes_not_read` gap **retires**; inner-class
   endpoints and annotations start being read.
2. Class symbol facts gain their **generic supertype reference** (the 2A signature
   machinery run in one more place) — `OrderFlow$1`'s fact carries
   `ParameterizedTypeReference<List<OrderView>>`. This also pre-feeds `inherits` edges.
3. The `instance` argument kind (§1) records the anonymous type at the call site.
4. The engines resolve a response/request argument whose `instance` type is a subtype of a
   catalog-declared **`type_carrier`** through that type's supertype argument —
   `List<OrderView>` becomes the same array-of-shape descriptor 2B built. "PTR" is named
   in the catalog, never in the engine.

Request bodies resolve by the same machinery: a body argument's `instance` type roots the
request shape directly; when that type is a catalog-declared **call wrapper**
(`{type: org.springframework.http.HttpEntity, payload_ctor_arg: 0}`), the engine follows
exactly one hop through the linked constructor call site to the real payload. One hop,
catalog-declared, `unresolved` beyond.

## 3. The `single_call` engine and the RestTemplate catalog

The engine mirrors `annotation_driven`'s shape — a generic interpreter over a new
`call_sites` view, fed by catalog data. `spring-resttemplate.yml` is D02 §1's opening
example extended with 2B's standard blocks: `matches.owner` plus `methods` rows
`{name, http_method | method_arg, url_arg, body_arg?, response_arg?}` covering
`getForObject`, `postForObject`, `put`, `delete`, `exchange` (verb from the enum argument),
and the `*ForEntity` variants (rooted through the existing `ResponseEntity` wrapper).

Per matching call site: `path` from the url argument's string literal — the template
verbatim, placeholders and all, because the template is the wire identity; `caller` = the
calling method symbol; `peer` NULL (2F); `direction: outbound`; `evidence: compiler`;
`resolution: resolved` when the URL resolved and **`unresolved` when it did not — the row
still derives**, because "this method calls something over HTTP" is true and useful.
Rows enter the same `endpoints` table, merge and count exactly as 2B's do.

## 4. Chain reconstruction and the `fluent` engine

Reconstruction is a join in the derivation: within one method, follow `result → receiver`
links; the engine interprets D02's `fluent` declarations (amended to allow multiple
verb-carrying `roots` and owner-free step matching) over each chain:

```yaml
style: fluent
matches:
  roots:
    - { owner: org.springframework.web.reactive.function.client.WebClient, method: get,  captures: { http_method: GET } }
    - { owner: org.springframework.web.reactive.function.client.WebClient, method: post, captures: { http_method: POST } }
  steps:
    - { method: uri,        captures: { url: arg0 } }
    - { method: bodyValue,  captures: { body: arg0 } }
    - { method: body,       captures: { body: arg0 } }
    - { method: bodyToMono, captures: { response: arg0 } }
    - { method: bodyToFlux, captures: { response: arg0, response_is: array } }
  terminal: [retrieve, exchange]
```

Per chain reaching a terminal: fold captures in order (last wins) and derive one endpoint —
verb from the root, path from the url capture (or `unresolved`), response from class
literal / `type_carrier` instance / `response_is: array`, request via §2's rooting.
Unmatched steps pass through uncaptured; a builder that never reaches a terminal derives
nothing (the true answer); two chains sharing a prefix each derive — value ids keep
interleaved builders apart where adjacency heuristics would fabricate.

Catalogs on this engine: `spring-webclient.yml`, `spring-restclient.yml` (synchronous
twin), `okhttp.yml` (`Request$Builder` root, `url`/`post` steps, `build` terminal joined
to `newCall` through the argument `source` id).

## 5. Fixtures, testing, rendering

**Fixture:** `BillingRestTemplate` (class literal, enum verb, `HttpEntity` one-hop, PTR of
`List<OrderView>`); `InventoryWebClient` (field-held client, `bodyToMono`/`bodyToFlux`, a
`flatMap` whose lambda makes a second call, one `uri(uriBuilder -> …)` deriving
`resolution: unresolved`); `OrdersRestClient`; `LegacyOkHttp` (split build/execute). New
fixture-scope deps: `spring-webflux`, `reactor-core`, `okhttp` (one-time online fetch;
real frameworks per D02 §4). Nested-class scanning changes the exact-list tests
(`OrderResult$Detail` and the anonymous PTR class appear).

**Testing, four layers:** Java unit tests on the dataflow pass (every argument kind, the
links, interleaved builders, varargs staying unresolved); Python unit tests over
hand-built call_site facts (both engines' rules, PTR, the hop, the OkHttp join, branch
chains, no-terminal); e2e on the fixture (exact outbound route extension, the unresolved
row asserted as unresolved, double-run byte-identical over the new facts); and a measured
fact-volume delta recorded in the plan's close-out.

**Rendering and export:** unresolved-path rows render honestly; gap rotation —
`call_site_clients_not_read` and `nested_and_anonymous_classes_not_read` retire,
`reactive_flow_not_traced` arrives; the `call_sites` view joins the exported graph tables;
scanner capabilities go 4 → 7 of 10 (the tenth row is `typed_signatures` — shipped since
Phase 2A/2B, but never given its own row in M03's capability table until Task 1 corrected
that).

## 6. Architecture remediations (approved to ride this phase)

Boundary health is good (contracts never broken, no framework leakage); within-module
cohesion is deteriorating at four accretion points, each made worse by this phase if left:

- **D1** — `shapes.py` (723 lines, five jobs) splits into `resolve/shapes/` —
  `rooting.py`, `expansion.py`, `contracts.py`, `nullability.py`. Pure moves, first code
  task, so later tasks land in the right files.
- **D2** — engines split into `resolve/engines/` (one module per style) before the count
  triples; `endpoints.py` returns to orchestration.
- **D3** — the dataflow pass is born in its own `MethodFlow.java`; `ClassScanner` wires.
- **D4** — `domain/facts.py` catches up to the shipped fact shape (wire projection on
  `TypeRef`, `type_path` on annotations, modifiers) and gains `CallSiteFact`, restoring
  the NFR-10 schema-as-code claim and closing D00's open field-list decision.

Deferred with reasons: typed `Catalog` models (until the vocabulary stabilises, ~2J);
shape provenance (named gap, structurally the linking phase's); `cli/app.py` git-helper
extraction (at the fourth helper).

## 7. Process safeguards and sequencing

The plan sequences extractor-first (spec amendments → D1–D4 splits → `MethodFlow` in two
tasks → capabilities/views), then `single_call` + RestTemplate, then PTR/nested classes,
then `fluent` + the three catalogs, then rendering and close-out — with a **mandatory
mid-plan re-check of all remaining briefs against the real emitted facts once the
dataflow tasks land** (the checkpoint that saved 2A). Implementation stacks on
`feat/phase-2b-outbound-export` until PR #3 merges. No version bumps (user's standing
gate: full Java + Spring Boot support).

## 8. Later phases this spec reserves slots for

The full program roadmap (2D messaging → 2E Spring inbound completeness → 2F configuration
resolution → L linking → 2G wire formats → 2H GraphQL/WebSocket/SSE → 2I SOAP → 2J
Micronaut/Quarkus → 2K enrich) lives in the roadmap document; this phase's facts are
designed so 2D's producers reuse `single_call` unchanged, the call-graph work reads
`ordinal`/`lambda` linkages without re-extraction, and 2F's config resolution has the
`peer` column and gap waiting.

## Self-review

Checked for placeholders (none), internal consistency (the argument grammar in §1 matches
every consumer named in §2–§4; gap rotations consistent between §5 and the sweeps), scope
(one plan, internally sequenced, with the declared mid-plan re-check), and ambiguity (the
one-hop rule, the no-terminal rule, and unresolved-row semantics are stated exactly).
Known risk accepted by user choice: single-phase breadth — mitigated by §7's sequencing
and checkpoint.
