# Phase 2E — Spring HTTP Inbound Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WebFlux functional routing in both DSLs (the `combinator` engine), module-local composed annotations, inherited mappings, and `produces`/`consumes` as two protocol-neutral endpoint columns — opened by the §0 language-neutrality hardening so nothing new is built on a JVM-ism.

**Architecture:** One new engine module (`combinator`, registered like the other four), one new pre-pass module (`resolve/effective_annotations.py` — deliberately NOT in `annotation_driven.py`), two new nullable TEXT columns on `endpoints` carried as data (never identity), and a symbol-grammar seam in the existing `domain/symbols.py`. `derive_endpoints.sql` changes twice, both small: an `annotations_effective` CTE (view UNION ALL a bound synthetic-rows parameter) and the media-attribute read. Zero extractor changes is the phase bet; Task 4's checkpoint proves or falsifies it before any catalog task dispatches.

**Tech Stack:** Python 3.12 + DuckDB; fixture adds `kotlinx-coroutines-core` and `kotlinx-coroutines-reactor` (compile scope; version provisional 1.10.2, checkpoint-confirmed).

**Spec:** `docs/superpowers/specs/2026-08-31-phase-2e-http-inbound-design.md`

## Global Constraints

- Wire identity stays (protocol, direction, method-nullable, path) with `IS NOT DISTINCT FROM` on `method`; `consumes`/`produces` are carried data, NEVER identity, NEVER compared in any dedup/merge join.
- Media semantics verbatim from spec §4: NULL = no declaration derivable from any evidence source, never a guessed default; lists are JSON arrays of MIME strings, order-normalized (sorted, distinct); within-batch union is engine-side only; across batches the existing first-writer dedup stands — no new SQL merge machinery.
- Unresolved is an answer, never an omission; destinations/paths verbatim, never evaluated; NULL keeps exactly one meaning; nothing is guessed. Any unresolvable part poisons exactly its own column.
- Every emitted handler symbol is resolved against the symbols facts, module-prefixed (the 2E-prep interface-engine rule) — a fabricated concatenation is a review-rejectable defect.
- Framework names live ONLY in catalogs. A Kotlin `if` in engine code is a review-rejectable smell (spec §1d) — the two entry shapes are catalog declarations interpreted by one core.
- Symbol-grammar string parsing lives only in `src/sextant/domain/symbols.py` after Task 1; the new architecture test enforces it.
- Exact-list discipline: frozen sets extend from live runs (never hand-predicted), asserted exactly. The two-run and double-run determinism e2e tests stay green through every task.
- No version bumps (`pyproject.toml` stays `0.1.0`). Never commit `uv.lock` or touch `.gitignore`. Full `scripts/check.sh` gates every commit.
- Suite baseline at plan time: 348 passed, 1 skipped; endpoint frozen baseline: 68 rows.
- Checkpoint discipline: Task 4 freezes items (1a) (1b) (2) (3) (4) (5) from real facts; Tasks 5–9 consume those rulings and MUST NOT guess past an unfrozen one.

---

### Task 1: §0 language-neutrality hardening

**Files:**
- Modify: `src/sextant/domain/closed_sets.py` (ConstructKind), `src/sextant/domain/symbols.py` (the seam — this module EXISTS, holding the `Symbol` SCIP renderer; extend it, do not create), `src/sextant/storage/duckdb/derive_endpoints.sql:147`, `src/sextant/application/resolve/shapes/rooting.py`, `src/sextant/application/resolve/shapes/expansion.py:139-169`, `src/sextant/application/resolve/engines/single_call.py:511`, `src/sextant/application/resolve/engines/interface_implementation.py:200-232`, `src/sextant/application/resolve/shapes/arguments.py:250`, `src/sextant/egress/render/viewmodel.py`, `src/sextant/egress/render/document.py` (the two `.rsplit(" ", 1)[-1]` handler/caller strips), `docs/components/D00-fact-schema.md`, `docs/components/D02-catalog-schema.md`
- Test: `tests/domain/test_symbols.py` (extend), `tests/architecture/test_symbol_grammar_confinement.py` (create)

**Interfaces:**
- Produces (all in `sextant.domain.symbols`, exact signatures later tasks import):
  - `bare_descriptor(symbol: str) -> str` — the descriptor after the space-separated module coordinates; the whole string when no coordinates are present.
  - `owner_of(descriptor: str) -> str | None` — the owning type's descriptor INCLUDING its trailing `#`, or `None` for an ownerless symbol (an answer, never an exception).
  - `member_name(descriptor: str) -> str` — the segment after the last `#`, trailing `.` stripped (`org/springframework/http/HttpMethod#POST.` → `POST`; a descriptor with no `#` returns itself minus any trailing `.`).
  - `type_descriptor(dotted: str) -> str` — `reactor.core.publisher.Mono` → `reactor/core/publisher/Mono#` (moved verbatim from `rooting._catalog_symbol`).
  - `simple_name(symbol: str) -> str` — moved verbatim from `viewmodel.simple_name`.
- Produces: `ConstructKind` gains `STRUCT = "struct"`, `TRAIT = "trait"`, `PROTOCOL = "protocol"`, `ALIAS = "alias"`, `FUNCTION = "function"`, `ACCESSOR = "accessor"` — exactly D00 §4's 14, no more.

- [ ] **Step 1: Failing seam tests** in `tests/domain/test_symbols.py`: `owner_of("com/acme/OrderService#save().") == "com/acme/OrderService#"`; `owner_of("pkg/handleOrders().") is None` (the free-function case that today crashes `expansion.py:148`); `member_name` on the enum-constant, method, and hashless forms; `bare_descriptor` on a five-part symbol and on a bare descriptor; `type_descriptor` round-trips the docstring example; `simple_name` unchanged behavior. Run — fail with ImportError.
- [ ] **Step 2: Implement the five functions** in `domain/symbols.py`, each a 1-3 line body, docstrings citing D00 §5a. Run — pass.
- [ ] **Step 3: Rewire the eight parse sites**, byte-identical for every JVM symbol: `rooting.py` — delete `_catalog_symbol`'s body, replace with `from sextant.domain.symbols import type_descriptor as _catalog_symbol` (all five importers stay untouched; keep the docstring rationale as a module comment beside the import); `expansion.py:148` — `owner = owner_of(descriptor)` and `if owner is None: continue` (a field with no owning type belongs to no shape — a decision, commented as such); `expansion.py:147,169` and `arguments.py:250` and `interface_implementation.py:208,228-229` — `bare_descriptor(...)`; `single_call.py:511` — `return member_name(str(arg["symbol"]))`; `viewmodel.simple_name` — re-export from the seam (`from sextant.domain.symbols import simple_name` — its one caller keeps its import path); `document.py`'s two `.rsplit(" ", 1)[-1]` — `bare_descriptor(...)`.
- [ ] **Step 4: ConstructKind + SQL.** Add the six members (Interfaces block above). In `derive_endpoints.sql:147`: `AND s.construct_kind IN ('method', 'function')` with a one-line comment: a handler is a method OR a free function (D00 §4) — the JVM extractor emits only `method`, which is what keeps this a no-op today.
- [ ] **Step 5: Full suite** — `pytest tests/ -x -q`. The frozen 68-row set and every shape pin must be untouched (the proof of byte-identity). Any diff is a defect in Step 3, not a set to re-freeze.
- [ ] **Step 6: The structural test** `tests/architecture/test_symbol_grammar_confinement.py`, modeled on `test_language_confinement.py` (same `SOURCE_ROOT` walk, same offences-list assertion, same positive-control second test proving the pattern matches inside the seam): scan `src/sextant/**/*.py` EXCLUDING `domain/symbols.py`; forbid `re.compile(r"""['\"]#['\"]|r?partition\(\s*['\"] ['\"]\s*\)|rsplit\(\s*['\"] ['\"]""")`. Docstring names the one deliberate out-of-scope site: `derive_endpoints.sql:82`'s `regexp_extract(v, '#([A-Za-z0-9_]+)\.$', 1)` reads the enum-constant grammar in SQL, where the seam cannot reach — SQL files are excluded and this test says so rather than silently skipping them. Run: the test must pass against the Step 3 result and FAIL when you temporarily revert one rewiring (verify once, then restore).
- [ ] **Step 7: Contract sentences.** D00 §5 (beside the `instance` row's existing `<init>` mention): `<init>` is the canonical constructor call-site NAME every extractor normalizes to (Python's `__init__` maps in; a language without constructors simply never emits it — readers already tolerate absence). D00 §5a (beside `implemented_interfaces`): interface satisfaction is extractor-computed — a structural-interface language derives the same `interfaces` facts from method-set satisfaction; the engine's join is unchanged. D02 §1 (beside the dotted-notation rule): the dotted notation is sugar for the JVM symbol scheme; the conversion (`domain/symbols.type_descriptor`) becomes scheme-aware when the first non-JVM catalog arrives.
- [ ] **Step 8: Commit** — `git add -A src tests docs && git commit -m "feat: language-neutrality hardening — construct vocabulary aligned, one symbol-grammar seam"`

---

### Task 2: The media columns — plumbing only

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql` (endpoints DDL), `src/sextant/storage/duckdb/derive_endpoints.sql` (INSERT column list + two NULL literals), `src/sextant/storage/duckdb/derive_call_endpoints.sql` (INSERT list + STRUCT gains two VARCHAR fields), `src/sextant/application/resolve/engines/single_call.py`, `fluent.py`, `interface_implementation.py`, `annotation_driven.py` (`_reply_row`) — every row dict gains `"consumes": None, "produces": None`, `docs/components/D01-graph-schema.md` §3
- Test: `tests/storage/test_workspace.py`, plus mechanical pin updates wherever an existing test asserts a full row shape

**Interfaces:**
- Produces: `endpoints` carries `consumes TEXT` and `produces TEXT` as its last two columns (nullable; JSON arrays of MIME strings when present). `derive_call_endpoints.sql`'s `$rows` STRUCT ends `..., request_shape VARCHAR, response_shape VARCHAR, consumes VARCHAR, produces VARCHAR`. Tasks 5 and 8 fill them; everything else passes `None`.

- [ ] **Step 1: Failing test** in `tests/storage/test_workspace.py`: derive one row through `derive("call_endpoints", rows=[...])` carrying `"consumes": '["application/json"]'`, `"produces": None`; assert the queried row's two columns round-trip and that a second row with the same wire identity but different media does NOT insert (media never in the NOT EXISTS join).
- [ ] **Step 2: DDL + SQL.** Append the two columns to the `endpoints` CREATE TABLE with the D01 comment (carried data, never identity). `derive_endpoints.sql`: add them to the INSERT list and `NULL AS consumes, NULL AS produces` in `derived` (Task 5 replaces the literals). `derive_call_endpoints.sql`: extend INSERT list, SELECT, and STRUCT.
- [ ] **Step 3: Engines.** Add the two `None` entries to every row dict the four engines build (fluent `_derive`, single_call's row builder, interface_implementation's row, `annotation_driven._reply_row`). Grep-verify: `grep -n '"response_shape"' src/sextant/application/resolve/` — every hit's dict now also carries the two new keys.
- [ ] **Step 4: Suite + mechanical pins.** Run `pytest tests/ -q`. Any test asserting a full endpoint row dict/column list gains the two NULL fields — mechanical, no judgment; any test asserting `(method, path)` tuples is untouched. The frozen 68 rows stay 68.
- [ ] **Step 5: D01 §3** — add `consumes`/`produces` to the endpoints row ("Direction, protocol, wire identity, handler and/or caller, peer, request and response payload descriptors, **declared media types**, trust fields") plus a paragraph stating spec §4's three rules verbatim: NULL means no declaration derivable (never a guessed default — a declared restriction 406s, an undeclared one negotiates); the four evidence kinds with 2E implementing kind (a) for Spring and kinds (b)/(d) specified for 2F+; MIME strings, DR-5's conservative rule (NULL compatible with everything; otherwise lists must intersect), evidence-kind strictness deferred to L where `catalog_id` names provenance. State the batch rule: rows differing only in media union engine-side within one derivation batch, order-normalized; across batches first-writer dedup stands.
- [ ] **Step 6: Commit** — `git commit -m "feat: consumes/produces endpoint columns, carried as data and never identity"`

---

### Task 3: Fixture — routers, compositions, interface, media attributes

**Files:**
- Modify: `fixtures/orders-service/pom.xml` (two deps: `org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2`, `org.jetbrains.kotlinx:kotlinx-coroutines-reactor:1.10.2`), `fixtures/orders-service/src/main/java/com/acme/orders/OrderController.java` (media attributes on two existing mappings)
- Create: `.../java/com/acme/orders/routes/RouteHandlers.java`, `.../routes/OrderRoutes.java`, `.../kotlin/com/acme/orders/routes/KotlinOrderRoutes.kt`, `.../java/com/acme/orders/composed/ApiGet.java`, `.../composed/OrderTopicListener.java`, `.../composed/ComposedController.java`, `.../composed/ComposedListener.java`, `.../java/com/acme/orders/openapi/OrdersApi.java`, `.../openapi/OrdersApiController.java`

**Interfaces:**
- Produces: compiled bytecode covering every spec §5 fixture case, AND the invariant that this task derives ZERO new endpoint rows (nothing here is matched by any shipped catalog until Tasks 5–9) — asserted before commit.

- [ ] **Step 1: Handlers.** `RouteHandlers`: a component with `Mono<ServerResponse> listOrders(ServerRequest r)`, `Mono<ServerResponse> createOrder(ServerRequest r)`, `Mono<ServerResponse> health(ServerRequest r)` — bodies `return ServerResponse.ok().build();` only. NOTHING in any new file may call WebClient/RestTemplate/OkHttp/Kafka/JMS APIs (they would derive rows through shipped catalogs and break the zero-new-rows invariant).
- [ ] **Step 2: Java router.** `OrderRoutes` with two beans:

```java
public RouterFunction<ServerResponse> routes(RouteHandlers h) {
    return RouterFunctions.nest(RequestPredicates.path("/fn"),
        RouterFunctions.route(RequestPredicates.GET("/orders")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON)), h::listOrders)
            .andRoute(RequestPredicates.POST("/orders")
                .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)), h::createOrder)
            .andRoute(RequestPredicates.GET("/health").or(RequestPredicates.HEAD("/health")),
                request -> ServerResponse.ok().build()));
}
public RouterFunction<ServerResponse> composite(RouteHandlers h) {
    return RouterFunctions.route(RequestPredicates.GET("/extra"), h::health).and(other());
}
private RouterFunction<ServerResponse> other() { ... one GET route ... }
```

  — nested prefix, an `or`'d verb, one `accept`, one `contentType`, a method-ref handler, a lambda handler, and the cross-method composition (`other()`'s RouterFunction crossing into `composite` — the honest-unresolved case).
- [ ] **Step 3: Kotlin router.** `KotlinOrderRoutes.kt`: a `coRouter { }` bean mirroring the core shapes — `"/kt".nest { GET("/orders", ...suspend handler reference or lambda...) ; POST("/orders") { ... } ; accept(MediaType.APPLICATION_JSON).nest { GET("/rich") { ... } } }`. Exact DSL calls may be adjusted at the checkpoint; what is fixed: one nest prefix, two verbs, one media predicate, at least one handler as a reference and one as a lambda.
- [ ] **Step 4: Compositions.** `@ApiGet`: `@Target(METHOD) @Retention(RUNTIME) @GetMapping(path = "/composed")` annotation type. `ComposedController`: `@RestController` class whose ONLY mapping is one `@ApiGet`-annotated method (any plain mapping here would derive a row now and break the invariant). `@OrderTopicListener`: `@Target(METHOD) @Retention(RUNTIME) @KafkaListener(topics = "composed-orders")`; `ComposedListener` uses it on one void method.
- [ ] **Step 5: Interface.** `OrdersApi`: `@RequestMapping("/api")` type-level prefix; methods `@GetMapping("/orders") List<OrderResult> list();`, one method annotated `@ApiGet` (the composed-AND-inherited case), and `OrderResult find(long id)` mapped `@GetMapping("/orders/{id}")`. `OrdersApiController implements OrdersApi`: overrides carry NO annotations; the `find` override returns a SUBTYPE (declare `class DetailedOrderResult extends OrderResult` beside it) — the covariant case whose name+descriptor join must miss honestly and whose compiler bridge must not double-join. No `@RestController` gate problem: give the controller `@RestController` (the class-level gate lives on the implementation, mappings on the interface — the OpenAPI-generator pattern).
- [ ] **Step 6: Media attributes** on the EXISTING `OrderController`, attributes only — paths and methods must not change: `createDetailed` becomes `@PostMapping(value = "/detailed", consumes = "application/json", produces = "application/json")`, and the one-argument `get` becomes `@GetMapping(value = "/{id}", produces = "application/json")`. Every other mapping stays untouched (they are the NULL-stays-NULL pins).
- [ ] **Step 7: The invariant.** `mvn -q -o compile` green (network-restricted? drop `-o` once to fetch the two new artifacts, then verify `-o` works). Then run the pipeline (borrow `tests/application/test_pipeline.py::_resolved_fixture`'s body in a scratch script or run `pytest tests/application/test_pipeline.py -q`): endpoint count still 68, every frozen assertion green. If any new row appears, a new file leaked into a shipped catalog's match — fix the file, never the pin.
- [ ] **Step 8: Commit** — `git commit -m "fixture: functional routers, composed annotations, mapped interface, media attributes"`

---

### Task 4: Checkpoint — freeze the bytecode reality

**Files:**
- Create: `.superpowers/sdd/2026-08-31-phase-2e-http-inbound/checkpoint.md` (the frozen findings; git-ignored workspace — the controller copies load-bearing rulings into the ledger and, where they contradict this plan, amends the plan file itself)

**Interfaces:**
- Produces: written answers to spec §6 items (1a) (1b) (2) (3) (4) (5), each quoting the actual fact rows (JSON) it was frozen from. Tasks 5–9 consume these; none may proceed on a guess where the checkpoint answered.

- [ ] **Step 1: Scan and open the workspace.** Compile the fixture, scan with `AsmScanner`, load into a scratch `DuckDbWorkspace` (the `_resolved_fixture` path without `resolve()`), then answer with SQL over `call_sites`/`annotations`/`symbols`.
- [ ] **Step 2: (1a) Java tree.** For caller `com/acme/orders/routes/OrderRoutes#routes(...)`: dump every call site (owner, name, arguments with kinds and sources, receiver/result). Freeze: do predicate arguments link to their producing calls via `source`; is the method-ref argument `lambda`-kind naming `RouteHandlers#listOrders` directly; is the lambda argument `lambda`-kind naming a synthetic `lambda$routes$N`; do `.and(...)`/`.andRoute(...)` chains link result→receiver.
- [ ] **Step 3: (1b) Kotlin.** Which document/method contains the DSL body's `GET`/`POST`/`nest`/`accept` calls (inner-class `invoke` vs synthetic method); what owner do they carry (`CoRouterFunctionDsl`?); what kind the handler argument arrives as (lambda-kind reference vs `instance` of a generated class) and what is honestly recoverable as the handler symbol; how the `nest` call links to its body's containing method (lambda-kind symbol, `instance`, or nothing — this decides Task 8's cross-method jump for receiver-rooted entries). Also confirm the two kotlinx artifacts compiled at 1.10.2 (else record the working version and update pom + this plan's Tech Stack line).
- [ ] **Step 4: (2) Compositions.** Dump every annotation fact targeting `ApiGet`'s and `OrderTopicListener`'s type symbols and every use of them. Freeze: the composition's `@GetMapping(path="/composed")` args as emitted; the use-site's args; retention values (Spring requires RUNTIME so real compositions carry it — verify the `retention` column says so); the `construct_kind` an annotation TYPE symbol carries (Task 6's module-local test is "the target type symbol exists in `symbols`" — confirm it does).
- [ ] **Step 5: (3) Media predicates.** Dump the `accept`/`contentType` call sites: are the `MediaType` constants `enum`-kind arguments (symbol `org/springframework/http/MediaType#APPLICATION_JSON.`) or inlined strings? Freeze the exact member names the fixture produces — Task 9's `media_values` table is written against exactly these.
- [ ] **Step 6: (4) Inheritance join keys.** Dump `OrdersApi`'s and `OrdersApiController`'s method symbols and the controller's `interfaces` fact. Freeze: the descriptor forms (does the parenthetical hash make same-erased-signature methods equal across the two types — the join key Task 7 needs); whether the compiler's bridge method for the covariant `find` appears as its own symbol fact, and if so what distinguishes it (a `modifiers` key? a duplicate name+descriptor?) — Task 7's must-not-double-join rule is written against this.
- [ ] **Step 7: (5) Freeze the route additions** — from items (1a)/(1b), list every (method, path, handler-or-NULL, consumes, produces, resolution) row Tasks 5–9 are expected to add, as the once-extended target for the frozen sets. Mark any the facts cannot support (falsifying part of the zero-extractor-changes bet) — the controller rules on scope, never the implementer.
- [ ] **Step 8:** Write `checkpoint.md`, report DONE with the six answers summarized in one line each.

---

### Task 5: Annotation media evidence — SQL read + within-batch union

**Files:**
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql`, `src/sextant/application/resolve/engines/annotation_driven.py` (two new bound params), `src/sextant/catalogs/spring-web.yml`, `spring-mvc.yml` (vocabulary), `docs/components/D02-catalog-schema.md` §2
- Test: `tests/application/test_endpoints.py` (unit, synthetic facts), `tests/application/test_pipeline.py` (pins)

**Interfaces:**
- Consumes: Task 2's columns; Task 3's fixture attributes; checkpoint item (2) (attribute emission shapes).
- Produces: catalog vocabulary `consumes_from: [<attr>...]` / `produces_from: [<attr>...]` on the `mapping` block (alias lists, first present wins — the `path_from` pattern); `annotation_driven.run` passes `consumes_from=list(mapping.get("consumes_from", []))` (same for produces) so a catalog declaring neither behaves exactly as today.

- [ ] **Step 1: Failing unit tests** (synthetic-facts pattern already in `test_endpoints.py`): (i) a mapping with `consumes = "application/json"` scalar and one with `produces = ["b/y", "a/x"]` array derive `consumes = '["application/json"]'` and `produces = '["a/x","b/y"]'` (scalar-or-array read; order-normalized); (ii) a mapping with neither attribute derives both NULL; (iii) two mapping annotations on ONE method (same path/method — rows differing only in media) derive ONE row whose `produces` is the sorted distinct union; (iv) two mappings on different methods sharing a wire identity (content-negotiation siblings) still derive their rows exactly as today — the union groups on every non-media column, so differing handlers never collapse.
- [ ] **Step 2: SQL.** In `declared`, add per-row lists via the `path_from` alias-reading pattern applied to `$consumes_from` / `$produces_from` (empty alias list → NULL). In `derived`, replace Task 2's NULL literals with the normalized text, then wrap the final SELECT's source in the within-batch union:

```sql
SELECT protocol, direction, method, path, handler, caller, peer,
       handler_signature, resolution, evidence, catalog_id,
       CASE WHEN count(consumes_list) = 0 THEN NULL
            ELSE to_json(list_sort(list_distinct(flatten(list(consumes_list)
                 FILTER (WHERE consumes_list IS NOT NULL))))) END AS consumes,
       ... same for produces ...
FROM derived
GROUP BY ALL
```

  (`GROUP BY ALL` over the non-media columns — verify the exact DuckDB spelling; if `GROUP BY ALL` grabs the aggregates, list the eleven columns explicitly). Comment: rows differing ONLY in media are one endpoint (D01 §3, spec §4); everything else — including content-negotiation siblings with different handlers — is untouched.
- [ ] **Step 3: Vocabulary.** `spring-web.yml` and `spring-mvc.yml` `mapping:` blocks gain `consumes_from: [consumes]` / `produces_from: [produces]`. D02 §2 `annotation_driven`: document both alias lists, the scalar-or-array read, order normalization, the NULL rule (a catalog declaring neither reads nothing — absence is not a licence to invent a default), and — specified now for the frameworks that will use it, Spring's catalogs deliberately NOT — `default_produces` / `default_consumes` as catalog-declared framework-contract defaults (evidence kind (b), spec §4). One boundary sentence: type-level media attributes (a class-level `@RequestMapping(produces=...)`) are not read in 2E.
- [ ] **Step 4: Pins.** Run the pipeline; the two Task 3 attribute sites now fill their rows' columns. Extend the frozen assertions from the live run (`get /v1/orders/{id}` gains `produces '["application/json"]'`; `post /v1/orders/detailed` gains both; every other row's media NULL — assert at least one existing row's columns are both NULL, the NULL-stays-NULL pin). Count stays 68.
- [ ] **Step 5: Commit** — `git commit -m "feat: annotation-declared media types fill consumes/produces"`

---

### Task 6: The effective-annotations pre-pass — composed annotations

**Files:**
- Create: `src/sextant/application/resolve/effective_annotations.py`
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql` (the `annotations_effective` CTE), `src/sextant/application/resolve/engines/annotation_driven.py` (compute + bind synthetic rows), `docs/components/D02-catalog-schema.md` (§7 open-decision row → §2 note: the module-local half now exists, the jar half awaits dependency scanning)
- Test: `tests/application/test_effective_annotations.py` (create), `tests/application/test_pipeline.py` (pins)

**Interfaces:**
- Consumes: checkpoint item (2) (attribute placement, retention, annotation-type construct_kind).
- Produces: `composed_mapping_rows(annotation_rows: list[dict], scanned_targets: set[str], mapping_fqns: set[str]) -> list[dict]` — pure function over already-queried rows (each `{target, annotation, args}`; `annotation` values in the same `type_descriptor` form the view carries; `args` a parsed dict). Returns synthetic rows `{target, annotation, args}` where `annotation` is always one of `mapping_fqns`. `annotation_driven.run` queries `annotations`, calls it, JSON-dumps each `args`, and binds the list as `$synthetic_annotations`; `derive_endpoints.sql` gains:

```sql
annotations_effective AS (
    SELECT target, annotation, args FROM annotations
    UNION ALL
    SELECT s.target, s.annotation, s.args::JSON FROM (SELECT UNNEST(
        $synthetic_annotations::STRUCT(target VARCHAR, annotation VARCHAR, args VARCHAR)[]
    ) AS s)
)
```

  and the `controllers`, `declared`, `prefixes` CTEs read `annotations_effective` instead of `annotations`.

- [ ] **Step 1: Failing unit tests** (hand-built row lists, no workspace): (i) one-hop composition — `@ApiGet`'s type carries `@GetMapping(path="/composed")`, a method uses `@ApiGet` → one synthetic row (target = the method, annotation = GetMapping-descriptor, args = `{"path": "/composed"}`); (ii) use-site wins — the use carries `{"path": "/override"}` → merged args `{"path": "/override"}` (`{**composition_args, **use_args}`); (iii) transitive two-hop closure, nearest declaration's args winning over the base's; (iv) cycle-guarded — two annotation types meta-annotating each other terminates and yields nothing false; (v) module-local only — a composed type whose symbol is NOT in `scanned_targets` yields nothing (the jar half); (vi) a plain direct use of a mapping fqn yields NO synthetic row (never duplicate what the view already has).
- [ ] **Step 2: Implement.** Fixpoint loop: seed the effective set with `mapping_fqns`; each round, find annotation rows whose `annotation` is in the set and whose `target` is a scanned TYPE symbol (checkpoint (2)'s construct_kind rule; the target's own bare descriptor is then a usable annotation identifier); record `composed[T_descriptor] = (base_fqn, folded_args)`; repeat with the composed identifiers added, folding args base-outward; visited-set cycle guard. Then one pass over uses: every row whose `annotation` is a composed identifier synthesizes `{target, base_fqn, {**folded_args, **use_args}}`. Deterministic output order: sorted by (target, annotation) — NFR-1. Module docstring: this is the honest subset of `@AliasFor` (same-name attributes only; explicit cross-name aliasing and re-targeting excluded — one COVERAGE sentence, Task 10).
- [ ] **Step 3: Wire + SQL** per the Interfaces block. `_derive_replies`' `annotations_of` lookup ALSO needs the composed view for a composed reply annotation — out of 2E scope (no fixture case): leave it, note in the module docstring.
- [ ] **Step 4: Pins.** Live run: `/composed` (GET, handler = the ComposedController method) and the `composed-orders` kafka row (method NULL, inbound) appear; the `@ApiGet`-on-interface case does NOT yet (inheritance is Task 7). Extend frozen sets once from the run; 68 → 70. The kafka row proves the mechanism is catalog-generic (spec §2's "for free").
- [ ] **Step 5: Commit** — `git commit -m "feat: module-local composed annotations resolve through the effective-annotations pre-pass"`

---

### Task 7: Inherited mappings

**Files:**
- Modify: `src/sextant/application/resolve/effective_annotations.py` (adds `inherited_rows`), `src/sextant/application/resolve/engines/annotation_driven.py` (folds them into the same `$synthetic_annotations` bind), `docs/COVERAGE.md` (three boundary sentences)
- Test: `tests/application/test_effective_annotations.py`, `tests/application/test_pipeline.py` (pins)

**Interfaces:**
- Consumes: checkpoint item (4) (descriptor join key; bridge-method fact shape), Task 6's synthesis path, the `implementations`/`supertypes`/`method_symbols` named queries (2E-prep/2A).
- Produces: `inherited_rows(workspace_rows..., mapping_fqns, prefix_fqn, composed_universe) -> list[dict]` — exact signature settled by the implementer from what Task 6 shaped, with these fixed semantics: input annotation universe = real rows + Task 6's synthetics (compose FIRST, then inherit — the composed-and-inherited fixture case resolves through both); a method with any own mapping in the universe inherits nothing; otherwise the first match wins in this exact order — directly implemented interfaces in declaration order, then the superclass, transitively up scanned chains; the join key is (method name, member descriptor) per checkpoint (4); synthesized mapping rows target the implementing method; a prefix row (`prefix_fqn` args from the supertype's TYPE) is synthesized targeting the implementing CLASS only when that class carries no own `prefix_fqn`.

- [ ] **Step 1: Failing unit tests**: (i) interface method's `@GetMapping` lands on the un-annotated implementing method; (ii) own annotation wins outright (no synthesis); (iii) two interfaces both mapping one method → first in declaration order, deterministically; (iv) superclass loses to interfaces; transitive chain reached; (v) type-level prefix inherited only when the class has none of its own; (vi) covariant override: descriptors differ → NO synthesis for the real method, and the bridge (per checkpoint (4)'s frozen shape) is excluded so no row targets it — the join misses honestly, exactly once; (vii) composed-and-inherited: a synthetic (composed) interface-side row inherits onto the implementation.
- [ ] **Step 2: Implement** in `effective_annotations.py` — same pure-function style, `bare_descriptor`/`member_name` from the Task 1 seam for every symbol operation, deterministic output order. Bridge exclusion per checkpoint (4); if the checkpoint found bridges carry no distinguishing modifier, the rule becomes: when one type declares two same-name methods and one's member descriptor equals the supertype's exactly while another differs only in return type, synthesize onto NEITHER (the honest miss) — write whichever rule the checkpoint supports, cite it in the docstring.
- [ ] **Step 3: Wire** — `annotation_driven.run` concatenates composed + inherited synthetic rows into the one existing bind. No SQL change.
- [ ] **Step 4: Pins.** Live run: `/api/orders` (GET, handler = the controller's `list` — `handler_signature` from the implementing method, so shapes derive from real types), the composed-and-inherited row, and NO row for the covariant `find` (assert its absence explicitly — the honesty pin). Extend frozen sets once; the count lands where the live run says (~72).
- [ ] **Step 5: COVERAGE sentences** — jar-defined interfaces do not derive (the standing compiled-library boundary); two-interface conflicts take declaration order (recorded, not rendered); `@AliasFor` full generality excluded.
- [ ] **Step 6: Commit** — `git commit -m "feat: mappings inherit from scanned interfaces and superclasses"`

---

### Task 8: The combinator engine — core, unit-tested against hand-built facts

**Files:**
- Create: `src/sextant/application/resolve/engines/combinator.py`
- Modify: `src/sextant/application/resolve/endpoints.py` (registry gains `"combinator": combinator.run`)
- Test: `tests/application/test_combinator_engine.py` (create; hand-built call-site facts through the `_Catalogs` seam, the `test_call_engines.py` pattern)

**Interfaces:**
- Consumes: checkpoint items (1a), (1b), (3); Task 2's row shape; `_arg_at` from `shapes.arguments`; `type_descriptor` (as `rooting._catalog_symbol` does).
- Produces: `run(workspace, catalog)` reading this `matches` grammar (Task 9 documents it in D02; the engine is written against it now):

```yaml
matches:
  entries:                       # where trees start
    - { owner: <fqn>, methods: [route, nest], handler_arg: 1 }   # argument-rooted static call
    - { owner: <fqn>, receiver_rooted: true }                    # every call on this owner, grouped by caller
  vocabulary:
    verbs:      [{ owner: <fqn>, method: GET, verb: GET, path_arg: 0, handler_arg: 1? }, ...]
    prefixes:   [{ owner: <fqn>, method: path, path_arg: 0 }, { owner: <fqn>, method: nest, path_arg: 0, subtree_arg: 1 }, ...]
    media:      [{ owner: <fqn>, method: accept, fills: produces }, { owner: <fqn>, method: contentType, fills: consumes }]
    media_values: { owner: <fqn>, values: { APPLICATION_JSON: application/json, ... } }
    composers:  { and: [{owner, method}...], or: [{owner, method}...] }
  continuations: [andRoute, andNest, and]
```

- [ ] **Step 1: Failing unit tests**, each a small hand-built fact set (caller symbols, call_sites rows with kinds/sources/receiver/result per checkpoint (1a)'s real grammar) resolved through an invented catalog: (1) one `route(GET("/x"), h::m)` static tree → `(http, inbound, GET, /x, <resolved handler>, resolution resolved)`; (2) nest prefix folds onto every subtree route; (3) `or` duplicates per branch over verb predicates AND over media predicates (two rows differing only in produces → engine-side union to ONE row, sorted list — the within-batch rule); (4) `and` merges constraints (verb + path + media on one row); (5) poisoning per column — a variable path argument → path NULL, resolution unresolved, verb intact; an unresolvable media constant → that column NULL, row otherwise resolved; (6) handler three cases — method ref (lambda-kind naming a real method, resolved module-prefixed via the `method_symbols` join), lambda (synthetic body symbol, same join), neither resolvable → handler NULL, row derives; (7) a cross-method `RouterFunction` reference (an argument whose source is another METHOD's return — per checkpoint (1a)) → ONE unresolved row, never silence; (8) chain continuation `.andRoute` merges route sets result→receiver; (9) receiver-rooted entry — DSL-owner calls grouped by caller derive the same shapes through the same core, and a `nest`-linked child method's routes fold under the parent's prefix (the checkpoint (1b) jump); (10) dedup: only identity-known rows enter the `seen` key (fluent's discipline), and the key includes handler (two handlers on one wire identity both survive — the interface-engine parity rule).
- [ ] **Step 2: Implement.** Structure mirrors `fluent.py`'s idiom: parse call sites once, group `by_caller`; a `_TreeContext` frozen dataclass; entry scan (argument-rooted: owner+method match on static roots; receiver-rooted: all sites of that owner in a caller, treed by receiver/result and source links); a recursive `_fold(site) -> list[_Route]` where `_Route` is a small dataclass `(verb, path_parts, consumes, produces, handler, resolution_poisons)`; predicate resolution reads `_arg_at` + kinds (string literal path; `enum`-kind media constant → `media_values[member_name(symbol)]`, else poison that column); composers: `and` merges field-wise (later verb/path wins-never — a second verb in one `and` chain is a poison, comment why), `or` concatenates the two branches' route lists; nest maps its subtree's routes with the prefix pushed; continuations merge lists along result→receiver; handler resolution = the `method_symbols` bare→prefixed join (build the dict inline from `workspace.query("method_symbols")`, the interface-engine precedent, comment the no-fabrication rule); rows built like fluent's `_derive` (evidence compiler, catalog protocol/direction, catalog_id) with `caller` = the containing method, `handler` as resolved; before insert: within-batch media union — group rows by every field except consumes/produces, union+sort each list, then the `seen` dedup and one `derive("call_endpoints", rows=rows)`. NO Kotlin branch, NO framework name — the receiver-rooted path and the argument-rooted path converge on `_fold`.
- [ ] **Step 3: Registry** — add the import and `"combinator": combinator.run`. The error message's style list updates itself (sorted keys).
- [ ] **Step 4: Suite** — unit tests green; pipeline untouched (no shipped catalog names the style yet). Commit — `git commit -m "feat: the combinator engine — routing trees fold into endpoint rows"`

---

### Task 9: The WebFlux router catalog — both DSLs through one core

**Files:**
- Create: `src/sextant/catalogs/spring-webflux-router.yml`
- Modify: `docs/components/D02-catalog-schema.md` (§2 gains the `combinator` style section — "The six styles" heading becomes seven), `tests/application/conftest.py` + `test_pipeline.py` (capability-comment lines mentioning which catalogs each capability gates), `tests/application/test_pipeline.py` (pins)
- Test: pins + the loader-iterating compatibility sweeps (they pick the new catalog up automatically — verify, don't rewrite)

**Interfaces:**
- Consumes: Task 8's grammar; checkpoint items (1a) (1b) (3) (5).
- Produces: the shipped catalog — `style: combinator`, `protocol: http`, `direction: inbound`, `requires: [call_site, string_constants, chain_reconstruction]`, entries for `org.springframework.web.reactive.function.server.RouterFunctions` (argument-rooted, `route`/`nest`) and the Kotlin DSL owner checkpoint (1b) froze (receiver-rooted), vocabulary rows for `RequestPredicates` + the Kotlin builder's two-arity verbs (one vocabulary, two arities), `path`/`nest` prefixes, `accept`→produces / `contentType`→consumes, `media_values` for exactly the constants checkpoint (3) froze, composers `and`/`or` on `RequestPredicate`, continuations `andRoute`/`andNest`/`and`. Copy the `wrappers`/`nullability`/`serialization`/`known_types` blocks verbatim from `spring-web.yml` (harvest compatibility).

- [ ] **Step 1: Write the catalog** per the Interfaces block, checkpoint values only — no constant, owner, or method the checkpoint did not freeze.
- [ ] **Step 2: D02 §2 `combinator`** — the style's contract in the section style of its five siblings: the three grammar blocks, the walk (argument-rooted and receiver-rooted entries, one core), the honesty rules verbatim from spec §1c (poison-per-column; cross-method reference → one unresolved row; functional handler payloads invisible — `request_shape`/`response_shape` honestly NULL), the within-batch media union, and the language-agnosticism sentence (axum/gin/Express as future catalog files against this engine).
- [ ] **Step 3: Pins.** Live run: the checkpoint item (5) route list appears — nested `/fn` prefixes, the `or`'d GET+HEAD `/health` pair, media columns from the two predicates, the method-ref handler resolved, the lambda handler's synthetic symbol, ONE unresolved row for the cross-method composition, and the Kotlin `/kt` routes per checkpoint (1b)'s recoverability ruling (handler NULL where that is the honest answer). Extend the frozen sets once from the run; assert the resulting exact count. `mvn` handler pins use the symbols the run emits — never hand-derived.
- [ ] **Step 4: Determinism** — run the pipeline twice (the existing two-run/double-run e2e covers it; run `pytest tests/e2e -q` explicitly here); byte-identical including the new columns and the Kotlin rows.
- [ ] **Step 5: Commit** — `git commit -m "feat: WebFlux functional routing derives through the combinator engine, both DSLs"`

---

### Task 10: Rendering, gaps, docs carries, close-out

**Files:**
- Modify: `src/sextant/egress/render/document.py` (media display + the `reactive_flow_not_traced` sentence), `src/sextant/egress/render/metadata.py` (nothing unless the key list changed — verify only), `docs/COVERAGE.md`, `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md`, `src/sextant/catalogs/okhttp.yml` + `spring-restclient.yml` + `spring-webclient.yml` (stale `_owns` comment), the eleven catalogs carrying the drifted "harvest compatibility" pointer label, `docs/components/D02-catalog-schema.md` §7 (meta-annotation open-decision row resolves per Task 6)
- Test: `tests/egress/test_render.py`

**Interfaces:** Consumes everything shipped; produces the documentation state the phase closes on.

- [ ] **Step 1: Rendering.** Inbound endpoints table gains a `Media` column, compact: `consumes → produces` with each side the JSON list's comma-joined members or `-` when NULL (e.g. `application/json → application/json`, `- → application/json`); omit nothing silently — a row with both NULL shows `-`. One render test pins a media row and a NULL row.
- [ ] **Step 2: Gap sentence.** `document.py`'s `reactive_flow_not_traced` sentence rewords in lockstep (the KEY does not change — verify `metadata.py` untouched): "Reactive and lambda flow is recorded but not traced: calls inside flatMap and map derive endpoints, and a functional route's handler resolves, but the sequence between reactive calls — and the payloads read inside a functional handler's body — await the call graph." Update the two manifest tests asserting the key list only if a key changed (it must not).
- [ ] **Step 3: COVERAGE flips** — WebFlux functional routes (incl. `coRouter`), meta-annotations, inherited mappings, `produces`/`consumes` move from "unimplemented forms" to delivered, each with its boundary sentence (Tasks 6–9's honesty rules); the §"What a run produces" list updates.
- [ ] **Step 4: Roadmap** — the 2E row renames to "Spring HTTP inbound completeness" with the GraphQL/WebSocket/SSE→2H, SOAP→2I note, status → delivered, delivered-column text from what actually shipped.
- [ ] **Step 5: Catalog comment carries** — the three fluent-HTTP catalogs' `_owns` cross-catalog rationale (obsoleted by `catalog_id`) corrects to the shape-expansion reason; the eleven "harvest compatibility" pointer labels correct to the same. Comments only — `git diff` on those files must show no value change.
- [ ] **Step 6: Matrix + volume** — `python scripts/coverage_matrix.py` regenerate, then `--check` green. Measure fact volume against the pre-phase baseline (scan the fixture at Task 3's parent commit and at HEAD; record both counts in the commit message body).
- [ ] **Step 7: Full suite + commit** — `pytest tests/ -q` all green; `git commit -m "docs: 2E close-out — coverage flips, roadmap, catalog comment carries"`

---

## Final review seam list (hand to the whole-branch reviewer verbatim)

- the combinator engine × the effective-annotations pre-pass (both feed `endpoints`; neither may know the other exists)
- the pre-pass × `derive_endpoints.sql` (the `annotations_effective` CTE is the whole interface; merge logic must not leak into SQL)
- the media columns × dedup/merge/rendering (carried data, never identity — check every join)
- the Java × Kotlin entry shapes sharing one core (no language branch; catalog data only)
- the new columns × the D06 bundle and the determinism tests (SELECT * exports carry them; two-run byte-identity)
- Task 1's seam × every symbol operation added in Tasks 6–9 (nothing new parses `#` or the space grammar outside `domain/symbols.py` — the structural test is the gate, but the reviewer reads for intent)
