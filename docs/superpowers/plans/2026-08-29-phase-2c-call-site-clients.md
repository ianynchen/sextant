# Phase 2C — Call-site HTTP clients Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HTTP calls whose URL and verb live in method calls — RestTemplate, WebClient, RestClient, OkHttp, including calls inside lambdas — derive outbound endpoints with payload contracts, from linked `call_site` facts rich enough that later phases never re-extract.

**Architecture:** A per-method ASM dataflow pass (`MethodFlow`) emits `call_site` facts with per-method value ids (receiver/result/argument sources) and eight literal kinds; two new catalog-driven engines (`single_call`, `fluent`) interpret them in the derivation. Four architecture remediations (spec §6) land first so every later task hits a focused file. `ParameterizedTypeReference` resolves via nested-class scanning plus generic-supertype capture.

**Tech Stack:** ASM 9.7 + `asm-tree`/`asm-analysis` (same org/version, shaded — treated as within ARCHITECTURE §9's ASM approval, with a §9 note); Python 3.12 + DuckDB; fixture gains `spring-webflux`, `reactor-core`, `okhttp` (fixture-scope, one-time online fetch); pytest, ruff, mypy, import-linter.

**Spec:** [docs/superpowers/specs/2026-08-29-phase-2c-call-site-clients-design.md](../specs/2026-08-29-phase-2c-call-site-clients-design.md) — binding; §1's fact grammar, §2's PTR rules, §4's engine semantics and §6's remediations are requirements, not suggestions.

## Global Constraints

- **Dependencies:** `asm-tree` + `asm-analysis` at the existing ASM version, shaded into the extractor jar, recorded in ARCHITECTURE §9's note beside ASM. Fixture-only: `spring-webflux`, `reactor-core` (transitively), `com.squareup.okhttp3:okhttp`. Nothing new in Python.
- **No version bumps** (user's standing gate: full program per the roadmap).
- **No framework name outside catalogs; no language name outside `ingress/extract/jvm`** — architecture tests scan every line of `src/`.
- **`application/` performs no file I/O; outer groups never import one another** — 4 import-linter contracts, enforced by pre-commit.
- **Determinism (NFR-1):** value ids, ordinals, chain walks and every derived row are deterministic; the double-run e2e is the net, extended to the new facts.
- **`unresolved` is an answer, never an omission.** A call site with an unresolvable URL still derives its endpoint row at `resolution: unresolved`.
- **Spec before code:** Task 1 amends D00/D02/M03/ARCHITECTURE §9; no later task deviates without an amendment.
- **Exact-list discipline:** scanner file lists, route sets and counts extend with full membership, never loosen.
- **MANDATORY MID-PLAN RE-CHECK** (spec §7): after Task 7 completes, the controller re-reads Tasks 8–14's briefs against the *actually emitted* facts from the fixture and amends before dispatching Task 8. This is a plan step, not advice.

## File structure

| File | Responsibility |
|---|---|
| `docs/components/{D00,D02,M03}.md`, `docs/ARCHITECTURE.md` §9 | **Amend** (Task 1) |
| `src/sextant/application/resolve/shapes/` — `__init__.py`, `rooting.py`, `expansion.py`, `contracts.py`, `nullability.py` | **Create** (Task 2, pure moves from `shapes.py`) |
| `src/sextant/application/resolve/engines/` — `__init__.py`, `annotation_driven.py`, later `single_call.py`, `fluent.py` | **Create** (Tasks 3, 9, 11) |
| `src/sextant/domain/facts.py` | **Modify** (Task 4): catch-up + `CallSiteFact` |
| `extractor-jvm/.../MethodFlow.java` | **Create** (Tasks 5–6): the dataflow pass |
| `extractor-jvm/.../ClassScanner.java`, `Main.java`, `build.gradle.kts` | **Modify** (Tasks 5–7) |
| `src/sextant/storage/duckdb/schema.sql`, `workspace.py` | **Modify** (Task 8): `call_sites` view + queries |
| `src/sextant/catalogs/spring-resttemplate.yml`, `spring-webclient.yml`, `spring-restclient.yml`, `okhttp.yml` | **Create** (Tasks 9, 12) |
| `fixtures/orders-service/.../clients/{BillingRestTemplate,InventoryWebClient,OrdersRestClient,LegacyOkHttp}.java` | **Create** (Task 7) |
| `src/sextant/egress/render/{document,metadata}.py`, `docs/COVERAGE.md`, roadmap | **Modify** (Tasks 13–14) |

---

### Task 1: Spec amendments — D00, D02, M03, ARCHITECTURE §9

**Files:**
- Modify: `docs/components/D00-fact-schema.md` (§5, §5a), `docs/components/D02-catalog-schema.md` (§2 styles), `docs/components/M03-scanner.md` (capability table), `docs/ARCHITECTURE.md` (§9)

**Interfaces:** Produces the amended spec text every later task implements. No code.

- [ ] **Step 1: D00 §5 — the `call_site` fact grammar.** State the full shape from spec §1 verbatim: the JSON example, the eight argument kinds table (`string`, `int`/`long`/`boolean`, `enum`, `class`, `lambda`, `instance`, `null`, `unresolved`), the optional `source` value id on every argument entry, `receiver`/`result` semantics (per-method, deliberately meaningless across methods), `ordinal` as the v1 control-flow position (later phases enrich it; D01 §7 prices the re-extraction), and `invoke_kind` ∈ {virtual, static, interface, special, dynamic}. Add to §5a: a class symbol fact carries its **generic supertype reference** when the superclass signature is generic (the PTR carrier).
- [ ] **Step 2: D00 §2 — multi-class documents.** One class file = one document stays true; a nested class's document keeps `relative_path` pointing at its **outer source file** (`OrderResult$Detail.class` → `com/acme/orders/OrderResult.java`) while `document_id` stays the sha256 of the class-relative path, so ids never collide and source mapping stays honest.
- [ ] **Step 3: D02 — the two engine styles' full grammar.** Extend `single_call` with the methods-row grammar (`{name, http_method | method_arg, url_arg, body_arg?, response_arg?}`); extend `fluent` from the single `root` to `roots` (each with `captures`) + owner-free `steps` + `terminal` list, exactly as spec §4's YAML shows; add the two new catalog declarations `type_carriers: [<dotted type>]` (a response/body argument whose `instance` type subtypes one resolves through its supertype argument) and `call_wrappers: [{type, payload_ctor_arg}]` (the one-hop body follow). State the no-terminal rule ("a builder that never reaches a terminal derives nothing") and the unresolved-URL rule.
- [ ] **Step 4: M03 — capabilities.** Mark `call_site`, `string_constants`, `chain_reconstruction` as shipped by the JVM scanner (7 of 10), with `chain_reconstruction` defined as "receiver/result value ids present on call_site facts". Note `invokedynamic` stays undeclared and what that means (indy call sites recorded, arguments unresolved, lambda bootstrap handles captured).
- [ ] **Step 5: ARCHITECTURE §9** — one sentence beside the ASM row: the `asm-tree`/`asm-analysis` sibling artifacts ride at the same version, shaded identically.
- [ ] **Step 6: Grep for contradictions** (`grep -rn "call_site\|chain_reconstruction\|nested and anonymous" docs/components/`) — no remaining sentence may contradict an amendment. Commit.

```bash
git add docs && git commit -m "docs: specify linked call sites, the two call-site engine styles, and their capabilities"
```

---

### Task 2: Remediation D1 — split `shapes.py` into a package (pure moves)

**Files:**
- Create: `src/sextant/application/resolve/shapes/{__init__.py,rooting.py,expansion.py,contracts.py,nullability.py}`
- Delete: `src/sextant/application/resolve/shapes.py`
- Test: the existing suite, unchanged — that is the point.

**Interfaces:**
- Produces: same public names, now importable from `sextant.application.resolve.shapes` (the package re-exports). The split map is binding:

| Module | Moves (from current `shapes.py`) |
|---|---|
| `rooting.py` | `RootedType`, `root_type`, `_matching_wrapper`, `_catalog_symbol` |
| `expansion.py` | `ExpandedShapes`, `derive_shapes`, `_Rules`, `_rules_of`, `_declared_fields`, `_enum_symbols`, `_rows_of`, `_wire_name`, `_separated`, `_STRATEGIES`, `_COLLECTIONS`, `_described`, `_item_of`, `_content_hash` |
| `contracts.py` | `derive_endpoint_shapes`, `_contracts_of`, `_owns`, `_body_type`, `_payload_descriptor`, `_REQUEST`, `_RESPONSE` |
| `nullability.py` | `_PACKAGE_FILE_CLASS`, `_scope_prefixes`, `_scope_prefix`, `_scope_nullable`, `_explicit_nullable`, `_nullability_of` |

- [ ] **Step 1:** Create the package; move each symbol verbatim (docstrings and comments travel with their functions; the module docstring's three paragraphs split to the module each describes). Cross-module needs become explicit imports (`from sextant.application.resolve.shapes.rooting import root_type, _catalog_symbol` etc. — the underscore names are package-internal, which the architecture tests permit within one package).
- [ ] **Step 2:** `__init__.py` re-exports the public surface: `RootedType`, `root_type`, `ExpandedShapes`, `derive_shapes`, `derive_endpoint_shapes`. Grep callers (`pipeline.py`, tests) and update imports that reached private names (`tests/application/test_shapes.py` imports several `_`-names — update paths, change nothing else).
- [ ] **Step 3:** Run: `.venv/bin/pytest -q` — expected: **identical pass count as before the move** (no behaviour change tolerated). `scripts/check.sh --lint` (import contracts must stay 4/4).
- [ ] **Step 4:** Commit: `git commit -m "refactor: shapes.py becomes a package, one job per module"`

---

### Task 3: Remediation D2 — the engines package

**Files:**
- Create: `src/sextant/application/resolve/engines/{__init__.py,annotation_driven.py}`
- Modify: `src/sextant/application/resolve/endpoints.py`

**Interfaces:**
- Produces: `engines.annotation_driven.run(workspace, catalog) -> None` (the moved `_run_annotation_driven`); `endpoints.py` keeps `derive_endpoints`, `missing_capabilities`, `SkippedCatalog`, `_engine_for`, and the `_ENGINES` registry now mapping `"annotation_driven": annotation_driven.run`. Tasks 9/11 add `single_call.run` and `fluent.run` beside it.

- [ ] **Step 1:** Move `_run_annotation_driven` verbatim to `engines/annotation_driven.py` as `run`; registry updates; module docstrings state the split (the engine module carries the "framework knowledge is data" paragraph).
- [ ] **Step 2:** Run the full suite + lint — identical counts. Commit: `git commit -m "refactor: engines get a package before their number triples"`

---

### Task 4: Remediation D4 — `domain/facts.py` catches up, gains `CallSiteFact`

**Files:**
- Modify: `src/sextant/domain/facts.py`
- Test: `tests/domain/test_facts.py` (create if absent — check `tests/` first)

**Interfaces:**
- Produces (models later tasks and tests may build): `TypeRef` gains `wire_type: str | None = None`, `wire_format: str | None = None`, `nullable: bool | None = None`, `nullable_resolution: str | None = None` (optional — method-signature refs carry them since 2B, older hand-built facts may not); `AnnotationFact` gains `type_path: str | None = None`; `SymbolFact` gains `modifiers: dict[str, bool] = {}` and `supertype: TypeRef | None = None`; new:

```python
class CallArgument(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["string", "int", "long", "boolean", "enum", "class",
                   "lambda", "instance", "null", "unresolved"]
    value: LiteralValue | None = None
    symbol: str | None = None
    source: int | None = None


class CallTarget(BaseModel):
    model_config = {"frozen": True}
    owner: str
    name: str
    descriptor: str


class CallSiteFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["call_site"] = "call_site"
    document_id: str
    caller: str
    target: CallTarget
    invoke_kind: str
    ordinal: int
    receiver: int | None = None
    result: int | None = None
    arguments: list[CallArgument] = Field(default_factory=list)
```

  `Fact` union gains `CallSiteFact`. The module docstring's NFR-10 claim becomes true again.

- [ ] **Step 1: Failing test** — round-trip a `CallSiteFact` through `model_dump`/validate; validate a 2B-real field fact dict (with wire projection and modifiers) against `SymbolFact` without loss (`model_dump` preserves the new fields).
- [ ] **Step 2:** Implement; run the full suite (hand-built test facts using `write_fact_file` must still validate — additive optional fields, nothing breaks).
- [ ] **Step 3:** Commit: `git commit -m "feat: the fact models catch up to the facts, and call_site joins them"`

---

### Task 5: `MethodFlow` part 1 — value ids, argument capture, call_site emission

**Files:**
- Create: `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java`
- Modify: `extractor-jvm/build.gradle.kts` (add `org.ow2.asm:asm-tree` and `org.ow2.asm:asm-analysis` at the ASM version already declared), `ClassScanner.java` (wire the pass into `visitMethod` via a `MethodNode` capture)
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/MethodFlowTest.java` + a committed fixture class `CallSample.java` under the extractor's existing test-fixture pattern

**Interfaces:**
- Produces: `MethodFlow.callSites(String callerSymbol, MethodNode method) -> List<String>` — one JSON line per invoke instruction, exactly spec §1's grammar. Kinds shipped in this task: `string`, `int`, `long`, `boolean`, `class`, `enum`, `null`, `unresolved` (+`source`); `receiver`/`result` ids; `ordinal`; `invoke_kind`. (`lambda` and `instance` are Task 6.) Value ids: the producing instruction's index in the method's instruction list — deterministic by construction.

- [ ] **Step 1: The committed fixture** — `CallSample.java` with methods exercising each capture: a call with a string-literal arg; folded constants (`private static final String BASE = "/api"; use(BASE + "/x")`); an int and boolean; an enum constant arg; a class literal arg; a null; a variable arg (→ unresolved, no source); an arg that is another call's result (→ unresolved **with** `source`); a static call (receiver null); chained calls `a().b().c()` (receiver of `b` = result of `a`).
- [ ] **Step 2: Failing tests** — one per capture, asserting the exact JSON fields (the existing `FieldScanTest` assertion style: parse the emitted line, compare fields). Plus: two invokes in one method get distinct `ordinal`s in instruction order; running the pass twice yields identical lines (determinism).
- [ ] **Step 3: Implement.** The reference implementation shape (the tests are the contract; keep the structure):

```java
/** Per-method dataflow: which instruction produced each value an invoke
 *  consumes. Uses ASM's Analyzer with SourceInterpreter — SourceValue's
 *  instruction set has exactly one element for a straight-line producer and
 *  several after a branch merge, which is precisely the resolved/unresolved
 *  line D00 §5 draws. Value ids are instruction indices: deterministic, and
 *  meaningless across methods on purpose. */
public final class MethodFlow {
    public static List<String> callSites(String callerSymbol, MethodNode method) {
        Analyzer<SourceValue> analyzer = new Analyzer<>(new SourceInterpreter());
        Frame<SourceValue>[] frames;
        try {
            frames = analyzer.analyze(ownerOf(callerSymbol), method);
        } catch (AnalyzerException impossible) {
            return List.of();   // an unanalyzable body yields no call facts — the
        }                        // method symbol itself was already emitted
        List<String> lines = new ArrayList<>();
        int ordinal = 0;
        AbstractInsnNode[] insns = method.instructions.toArray();
        for (int i = 0; i < insns.length; i++) {
            if (!(insns[i] instanceof MethodInsnNode invoke)) continue;
            Frame<SourceValue> frame = frames[i];
            if (frame == null) { ordinal++; continue; }   // unreachable code
            Type[] argTypes = Type.getArgumentTypes(invoke.desc);
            int stackTop = frame.getStackSize();
            // Stack layout at an invoke: ... receiver? arg0 .. argN-1
            List<String> arguments = new ArrayList<>();
            for (int a = 0; a < argTypes.length; a++) {
                SourceValue value = frame.getStack(stackTop - argTypes.length + a);
                arguments.add(argumentJson(value, insns));
            }
            Integer receiver = invoke.getOpcode() == Opcodes.INVOKESTATIC ? null
                : sourceId(frame.getStack(stackTop - argTypes.length - 1), insns);
            Integer result = Type.getReturnType(invoke.desc) == Type.VOID_TYPE ? null : i;
            lines.add(callSiteJson(callerSymbol, invoke, ordinal++, receiver, result, arguments));
        }
        return lines;
    }
    // argumentJson: single-source LDC String/Integer/Long/Type -> string/int/long/class;
    // ICONST_0/1 with boolean descriptor slot -> boolean; GETSTATIC whose owner is the
    // field's own type and desc matches owner -> enum; ACONST_NULL -> null;
    // otherwise unresolved, with "source": <index> when the single source is a
    // MethodInsnNode. Multi-source (branch merge) -> unresolved, no source.
}
```

  `ClassScanner.visitMethod` switches that one visitor to collect a `MethodNode` (asm-tree) and appends `MethodFlow.callSites(methodSymbol, node)` to the emitted lines at `visitEnd` — the existing annotation/signature collection is untouched.
- [ ] **Step 4:** `./gradlew test` green, jar rebuilt (`./gradlew build`), then `.venv/bin/pytest -q` — the Python suite must stay green with call_site lines now present in fixture facts (the loader takes any kind; **check the exact-count scanner tests** — fact counts per document change; extend those counts, never loosen the file lists).
- [ ] **Step 5:** Commit: `git commit -m "feat: linked call_site facts from a per-method dataflow pass"`

---

### Task 6: `MethodFlow` part 2 — lambda + instance kinds, nested classes, supertypes, capabilities

**Files:**
- Modify: `MethodFlow.java` (two kinds), `ClassScanner.java` (supertype capture in `visit`), `Main.java:31-38` (lift the `$` skip), `src/sextant/ingress/extract/jvm/scanner.py` (`_CAPABILITIES` + docstring)
- Test: `MethodFlowTest.java`, `ClassScannerTest`-family, `tests/ingress/test_asm_scanner.py`

**Interfaces:**
- Produces: `{"kind":"lambda","symbol":"<impl method symbol>"}` for `InvokeDynamicInsnNode` whose bootstrap is `LambdaMetafactory` (read `bsmArgs[1]` as a `Handle`, build the method symbol with the existing symbol grammar + `disambiguatorOf`); `{"kind":"instance","symbol":"<owner>#"}` for a single-source `NEW`/constructor result; class symbol facts gain `"supertype": {…TypeRef JSON…}` when the class signature declares a generic superclass (reuse `TypeRefs`' signature machinery — the `Collector` already parses class type signatures); nested/anonymous class files are scanned (document rule from Task 1 Step 2: fact file per class file, `relative_path` = outer source, `document_id` = sha256 of the class-relative path); `_CAPABILITIES` becomes `{"annotation_args", "typed_signatures", "type_annotations", "kotlin_metadata", "call_site", "string_constants", "chain_reconstruction"}` and the class docstring says seven.

- [ ] **Step 1: Failing Java tests** — a lambda arg (`list.forEach(x -> use(x))`) captures kind `lambda` with the synthetic method's symbol; a method reference (`this::use`) captures the referenced method; `new CallSample.Holder()` passed as an arg captures kind `instance`; a class whose source declares `extends TypeToken<List<String>>`-shaped generic supertype emits `supertype` with the full nested reference; a nested class file emits its own facts under the outer `relative_path`.
- [ ] **Step 2: Implement**; lift `Main.java`'s skip — the `uncovered` add for `$` files goes away entirely (the gap retires; anonymous classes scan like any class).
- [ ] **Step 3: Update the Python exact lists** — `tests/ingress/test_asm_scanner.py` gains `OrderResult$Detail.jsonl` (and every other `$` file the fixture compiles — run once and freeze the exact list); document counts rise accordingly; the e2e `uncovered` assertions that named the nested class change to expect an empty (or reduced-exactly) list.
- [ ] **Step 4:** Full gates: `./gradlew build test`, `.venv/bin/pytest -q`, `scripts/check.sh --lint`. Commit: `git commit -m "feat: lambdas, instances, supertypes, and nested classes reach the facts"`

> **CONTROLLER CHECKPOINT — the mid-plan re-check (spec §7).** Regenerate the fixture facts, inspect real call_site lines for each fixture client pattern, and re-verify Tasks 8–14's briefs against them (argument shapes, symbol forms, counts). Amend briefs before dispatching Task 8. This checkpoint is why Task 7 (fixture) comes next: the re-check needs the real clients compiled.

---

### Task 7: The fixture clients and dependencies

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/clients/{BillingRestTemplate,InventoryWebClient,OrdersRestClient,LegacyOkHttp}.java`
- Test: `tests/ingress/test_asm_scanner.py` (exact lists), `tests/e2e/test_fixture_builds.py` if counts appear there

**Interfaces:**
- Produces: the wire paths later tasks assert: RestTemplate — `GET /billing/balances/{id}` (getForObject + class literal), `POST /billing/settlements` (postForObject), `PUT /billing/settlements/{id}`, exchange `POST /billing/batch` (enum verb + `HttpEntity<>(new OrderRequest(...))` + `ParameterizedTypeReference<List<OrderView>>`); WebClient — `GET /v2/inventory/levels` (bodyToMono class literal), `POST /v2/inventory/reserve` (bodyValue + bodyToMono), `GET /v2/inventory/history` (bodyToFlux → array), one `uri(b -> b.path("/v2/inventory/search")…)` chain (derives `resolution: unresolved`), and a `flatMap(x -> …)` whose lambda body performs the reserve call; RestClient — `GET /v2/orders/mirror`, `POST /v2/orders/mirror`; OkHttp — `GET /legacy/exports` and `POST /legacy/exports` via `Request.Builder` + separate `client.newCall(request).execute()`.

- [ ] **Step 1: pom additions** (one-time online `mvn -q compile`, then `-o` forever):

```xml
    <dependency><groupId>org.springframework</groupId><artifactId>spring-webflux</artifactId><version>6.1.6</version></dependency>
    <dependency><groupId>io.projectreactor</groupId><artifactId>reactor-core</artifactId><version>3.6.5</version></dependency>
    <dependency><groupId>com.squareup.okhttp3</groupId><artifactId>okhttp</artifactId><version>4.12.0</version></dependency>
```

  (If 6.1.6/3.6.5 disagree at resolution time, prefer the nearest versions that resolve against spring-web 6.1.6 and record them.)
- [ ] **Step 2: The four classes.** Each method's calls exactly as the Interfaces block lists; every client held in a field initialised in the constructor (the realistic form — chains root on field reads); comments in the fixture's established voice explaining which capture each method exercises. The PTR use is `new ParameterizedTypeReference<List<OrderView>>() {}` — its anonymous class is part of the point.
- [ ] **Step 3:** `mvn -q -o compile`; extend the scanner exact lists (four new files **plus their anonymous/nested class files** — run once, freeze exactly); full suite green (no engine reads these yet).
- [ ] **Step 4:** Commit: `git commit -m "feat: fixture clients for every call-site capture path"`

---

### Task 8: The `call_sites` view and named queries

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql`, `src/sextant/storage/duckdb/workspace.py`
- Test: `tests/storage/test_workspace.py`

**Interfaces:**
- Produces: view `call_sites(document_id, caller, owner, name, descriptor, invoke_kind, ordinal, receiver, result, arguments)` where `arguments` stays JSON; named query `"call_sites"` ordered `caller, ordinal` (total: `ordinal` is unique per caller); the view joins the export set (`_EXPORTED_TABLES` + `_EXPORT_QUERIES` gain it — manifest `contents.tables` grows to seven).

- [ ] **Step 1: Failing test** — load a hand-written call_site JSONL line, query the view, assert every column including `arguments` round-tripping as JSON; assert the export includes `graph/call_sites.parquet`.
- [ ] **Step 2:** Implement:

```sql
CREATE OR REPLACE VIEW call_sites AS
SELECT document_id,
       payload ->> 'caller'                    AS caller,
       payload -> 'target' ->> 'owner'         AS owner,
       payload -> 'target' ->> 'name'          AS name,
       payload -> 'target' ->> 'descriptor'    AS descriptor,
       payload ->> 'invoke_kind'               AS invoke_kind,
       (payload ->> 'ordinal')::INTEGER        AS ordinal,
       (payload ->> 'receiver')::INTEGER       AS receiver,
       (payload ->> 'result')::INTEGER         AS result,
       payload ->  'arguments'                 AS arguments
FROM raw_facts WHERE kind = 'call_site';
```

- [ ] **Step 3:** Full suite; the bundle-manifest tests extend their `contents.tables` expectation (exact list). Commit: `git commit -m "feat: call sites become a queryable, exported table"`

---

### Task 9: The `single_call` engine and the RestTemplate catalog

**Files:**
- Create: `src/sextant/application/resolve/engines/single_call.py`, `src/sextant/catalogs/spring-resttemplate.yml`
- Modify: `src/sextant/application/resolve/endpoints.py` (registry), `src/sextant/application/resolve/shapes/contracts.py` (call-payload rooting helpers, shared with Task 11)
- Test: `tests/application/test_call_engines.py` (new), `tests/application/test_pipeline.py`

**Interfaces:**
- Consumes: the `call_sites` named query; `rooting._catalog_symbol`; the descriptor machinery via `contracts`.
- Produces: `engines.single_call.run(workspace, catalog) -> None` inserting endpoint rows (same columns/dedup as ever; `caller` = calling method symbol, `handler` NULL, `peer` NULL); registry `"single_call": single_call.run`. Shared payload helpers in `contracts.py` (Task 11 reuses them verbatim):
  - `argument_descriptor(argument, workspace_types, catalog_rules) -> str | None` — `class` kind → object/known descriptor for that symbol; `instance` kind whose type subtypes a declared `type_carrier` → descriptor of the supertype argument (via the type's `supertype` fact); `instance` of a declared `call_wrapper` → one hop through the linked constructor call site's `payload_ctor_arg`; plain `instance` → object descriptor of that type; else `None`.
  - Verb resolution: a methods row carries `http_method` or `method_arg` (an `enum` argument's symbol tail).
  - URL: a `string` argument → `resolution: "resolved"`; anything else → path `NULL`-safe placeholder is **not** used — the row derives with the literal absent and `resolution: "unresolved"`, path stored as the empty string is FORBIDDEN: store `path` as `"(unresolved)"`? No — decided: `path` column keeps the template when known, else SQL NULL, and `resolution: unresolved` marks the row; the renderer prints "unresolved". (This is the one place NULL means "unknown", not "no payload" — the column is `path`, and D01 §3's wire-identity minting simply cannot mint one, which is what `unresolved` says.)

- [ ] **Step 1: The catalog** — spec §3's content:

```yaml
id: spring-resttemplate
displayName: Spring RestTemplate
style: single_call
protocol: http
direction: outbound
detect:
  coordinates: ["org.springframework:spring-web"]
requires: [call_site, string_constants]
matches:
  owner: org.springframework.web.client.RestTemplate
  type_carriers: [org.springframework.core.ParameterizedTypeReference]
  call_wrappers:
    - { type: org.springframework.http.HttpEntity, payload_ctor_arg: 0 }
  methods:
    - { name: getForObject,  http_method: GET,  url_arg: 0, response_arg: 1 }
    - { name: postForObject, http_method: POST, url_arg: 0, body_arg: 1, response_arg: 2 }
    - { name: put,           http_method: PUT,  url_arg: 0, body_arg: 1 }
    - { name: delete,        http_method: DELETE, url_arg: 0 }
    - { name: getForEntity,  http_method: GET,  url_arg: 0, response_arg: 1 }
    - { name: postForEntity, http_method: POST, url_arg: 0, body_arg: 1, response_arg: 2 }
    - { name: exchange, method_arg: 1, url_arg: 0, body_arg: 2, response_arg: 3 }
wrappers:
  - { type: org.springframework.http.ResponseEntity, payload_arg: 0, semantics: http_envelope }
  - { type: java.util.Optional, payload_arg: 0, semantics: optional }
serialization:
  name_from:
    - { annotation: com.fasterxml.jackson.annotation.JsonProperty, arg: value }
  ignore: [com.fasterxml.jackson.annotation.JsonIgnore]
  default_strategy: as_declared
known_types:
  - { type: java.time.Instant,    wire: string, format: date-time }
  - { type: java.math.BigDecimal, wire: number }
```

- [ ] **Step 2: Failing unit tests** over hand-built call_site facts (mirror the Task 5 emission shapes exactly): getForObject with string url + class literal → resolved endpoint with response descriptor; exchange with enum verb; a variable url → row exists, `resolution == "unresolved"`, `path is None`; the `HttpEntity` hop → request descriptor roots at `OrderRequest#`; the PTR instance → response descriptor `{"wire_type":"array","item":{…OrderView…}}`; two identical calls in one method dedup to one row.
- [ ] **Step 3: Implement**; the engine reads `call_sites` where `owner == _catalog_symbol(matches.owner)`, matches `methods` rows by name, builds rows, inserts via the existing endpoint insert path (a parameterised derivation mirroring `derive_endpoints.sql`'s dedup discipline — create `derive_call_endpoints.sql` with the same NOT EXISTS guard, columns identical).
- [ ] **Step 4: e2e** — `test_pipeline.py`'s exact route set gains the four RestTemplate routes (`GET /billing/balances/{id}`, `POST /billing/settlements`, `PUT /billing/settlements/{id}`, `POST /billing/batch`), count updated; the exchange row's request/response descriptors asserted.
- [ ] **Step 5:** Full gates; commit: `git commit -m "feat: single_call derives RestTemplate endpoints from linked call sites"`

---

### Task 10: PTR and supertype resolution hardening

**Files:**
- Modify: `src/sextant/application/resolve/shapes/contracts.py`, `src/sextant/storage/duckdb/workspace.py` (a `supertypes` named query: `SELECT symbol, payload -> 'supertype' AS supertype FROM raw_facts WHERE kind='symbol' AND payload -> 'supertype' IS NOT NULL ORDER BY symbol` — adjust to the real projection shape observed at the checkpoint)
- Test: `tests/application/test_call_engines.py`

This task exists separately so the reviewer can gate the subtle piece alone: `argument_descriptor`'s `type_carrier` path walks: instance type → its symbol fact's `supertype` reference → assert the supertype's symbol matches a declared carrier → take `arguments[0]` of the supertype reference → build the descriptor via `_described` (nested `List<OrderView>` → array-of-shape, exactly the field grammar).

- [ ] **Step 1: Failing tests** — carrier with `List<OrderView>` → array descriptor whose element shape expands; carrier with a bare `OrderView` → object descriptor; an `instance` whose type has no supertype fact → `None` (honest); a carrier subtype declared in a DIFFERENT document still resolves (the query is workspace-wide).
- [ ] **Step 2:** Implement + full suite. Commit: `git commit -m "feat: ParameterizedTypeReference payloads resolve through captured supertypes"`

---

### Task 11: Chain reconstruction and the `fluent` engine

**Files:**
- Create: `src/sextant/application/resolve/engines/fluent.py`
- Modify: `endpoints.py` (registry)
- Test: `tests/application/test_call_engines.py`

**Interfaces:**
- Consumes: `call_sites` rows; `contracts.argument_descriptor`; `_catalog_symbol`.
- Produces: `engines.fluent.run(workspace, catalog) -> None`. Semantics exactly spec §4: group rows by `caller`; index by `result`; a chain starts at any row matching a `roots` entry (owner+method) and follows rows whose `receiver` equals the previous row's chain key — a root's chain key is its `result`, except a constructor root (`<init>`, whose `result` is void/None) whose key is its `receiver`, the constructed value's id (checkpoint ruling CP-3) (**and**, for the execute-join, a row one of whose arguments' `source` equals a prior chain row's `result` — the OkHttp shape: the catalog marks it `terminal_via_argument: true` on the terminal entry); fold `captures` in chain order, last wins; derive one endpoint per chain reaching a terminal; no terminal → nothing.

- [ ] **Step 1: Failing unit tests** — a WebClient-shaped chain (hand-built rows) derives GET with url + bodyToMono response; last-wins on a repeated step; two interleaved chains in one caller derive two correct endpoints (ids keep them apart); a rootless fragment derives nothing; a root-without-terminal derives nothing; `bodyToFlux` sets `response_is: array` (descriptor wraps in `{"wire_type":"array","item":…}`); a `uri` step whose argument is a `lambda` kind → row derives with `resolution: "unresolved"`; the OkHttp split (builder chain ends at `build`, separate `newCall` row carries `source` = build's result) derives via `terminal_via_argument`.
- [ ] **Step 2:** Implement the walker (pure functions over the row list — no SQL recursion), insert through the same `derive_call_endpoints.sql`.
- [ ] **Step 3:** Full suite; commit: `git commit -m "feat: fluent chains reassemble from value links and derive endpoints"`

---

### Task 12: The WebClient, RestClient and OkHttp catalogs, end to end

**Files:**
- Create: `src/sextant/catalogs/spring-webclient.yml`, `spring-restclient.yml`, `okhttp.yml`
- Test: `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`

- [ ] **Step 1: The catalogs.** `spring-webclient.yml` exactly as spec §4's YAML (all five verbs as roots: get/post/put/delete/patch; steps `uri`, `bodyValue`, `body`, `retrieve` in terminal list with `exchange`; `bodyToMono`/`bodyToFlux` as steps captured *after* terminal — note: `bodyToMono` follows `retrieve` in real chains, so `terminal` means "the chain is executable", and steps continue to be captured past it; state this in the engine (Task 11 behaviour) and the catalog comment). `spring-restclient.yml` the synchronous twin (`org.springframework.web.client.RestClient`, same roots/steps, terminal `retrieve`, `body(...)` step capturing response class). `okhttp.yml`: root `{owner: okhttp3.Request$Builder, method: <init>, captures: {http_method: GET}}` (GET is OkHttp's default), steps `url {url: arg0}`, `get {http_method: GET}`, `post {http_method: POST, body: arg0}`, terminal `build` with `terminal_via_argument` pointing at `{owner: okhttp3.OkHttpClient, method: newCall}`. **Absolute-URL rule (checkpoint ruling CP-2, generic to every engine):** a url capture that is an absolute URL splits — `peer` = the authority, `path` = the path component; OkHttp's `url()` API forces absolute URLs, so its fixture rows derive `GET`/`POST /legacy/exports` with `peer: legacy.acme.internal`. All three carry `requires: [call_site, string_constants, chain_reconstruction]`, the standard serialization/known_types blocks, and `type_carriers` where the client supports PTR (`spring-webclient`, `spring-restclient`).
- [ ] **Step 2: e2e** — the exact route set gains the eight WebClient/RestClient/OkHttp routes from Task 7's Interfaces block; the unresolved uriBuilder row asserted with `resolution == "unresolved"` and `path is None`; the flatMap-lambda's reserve call asserted present (it derives from the lambda body's chain); per-direction counts refeozen — **run once, freeze exactly**.
- [ ] **Step 3:** Full gates; commit: `git commit -m "feat: WebClient, RestClient and OkHttp derive from reconstructed chains"`

---

### Task 13: Rendering, gaps, metadata, export

**Files:**
- Modify: `src/sextant/egress/render/document.py`, `metadata.py`, `tests/egress/test_render.py`, `tests/e2e/test_vertical_slice.py`

- [ ] **Step 1: Gap rotation** (lockstep discipline, exact pairing): retire `call_site_clients_not_read` and `nested_and_anonymous_classes_not_read`; add `reactive_flow_not_traced` ("Reactive and lambda flow is recorded but not traced: calls inside flatMap and map derive endpoints, but the sequence between them awaits the call graph."). Net 13 → 12 keys.
- [ ] **Step 2: Unresolved rows render honestly** — the outbound table prints `unresolved` in the Endpoint column when `path` is NULL (e.g. `| GET (unresolved) | … |`), and the summary counts them; a test pins one such row's rendering.
- [ ] **Step 3:** e2e document assertions extend (`/billing/settlements` appears; the unresolved row appears as unresolved); the double-run byte-identical test now covers call_site facts and the new parquet table by construction — verify it passes untouched.
- [ ] **Step 4:** Commit: `git commit -m "feat: the document carries call-site endpoints and rotates its gaps"`

---

### Task 14: Close-out — volume measurement, COVERAGE, roadmap

**Files:**
- Modify: `docs/COVERAGE.md` (§5.1/§5.2 rows → shipped; regenerate §2; "What ships today" + "What a run produces" prose), `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md` (2C → delivered)

- [ ] **Step 1: Measure and record** — fact counts on the fixture before/after (from Task 5's baseline vs now), written into the task report AND a one-line note in COVERAGE's run-produces section if the growth is material (>3× total facts would trigger the origin-tier filter conversation — record the number either way).
- [ ] **Step 2: COVERAGE** — `RestTemplate` row (§5.2) → `✅ shipped`; the `RestClient, WebClient, OkHttp…` fluent row → split: those three `✅ shipped`, JDK `HttpClient`/Apache/`URL.openConnection` stay B; §5.1's Vert.x row note stays (chain reconstruction now exists — its tier drops to A? No: leave tiers to the matrix script's rules; update only what shipped). Run `python3 scripts/coverage_matrix.py && --check`.
- [ ] **Step 3: Roadmap** — 2C row → delivered; blocked-on paragraph updated to past tense.
- [ ] **Step 4:** Full `scripts/check.sh`; commit: `git commit -m "docs: record what Phase 2C shipped"`

---

## Self-review against the spec

**Coverage.** Spec §1 (fact grammar, pass, capabilities, volume) → Tasks 1, 5, 6, 8, 14. §2 (nested classes, supertypes, PTR, call wrappers) → Tasks 1, 6, 9, 10. §3 (single_call + RestTemplate) → Task 9. §4 (chains, fluent, three catalogs) → Tasks 11, 12. §5 (fixtures, four-layer testing, rendering, export) → Tasks 7, 8, 9–13. §6 (remediations D1–D4) → Tasks 2, 3, 4, 5 (MethodFlow born separate). §7 (sequencing + mid-plan re-check) → the checkpoint block after Task 6, deliberately after the fixture task was moved adjacent (Task 7) so the re-check sees real client facts. §8 → Task 14.

**Known open points, stated not hidden:** the exact `supertypes` query projection and the emitted symbol forms for anonymous classes are frozen at the controller checkpoint, not guessed here (two named "adjust to observed" points, both checkpoint-gated). `bodyToMono`-after-terminal semantics are specified in Task 12 Step 1 and implemented by Task 11's walker (steps keep capturing past the terminal; the terminal only marks executability).

**Type consistency checked:** `argument_descriptor` is defined once (Task 9) and consumed by Tasks 10–12; the registry names (`single_call.run`, `fluent.run`) match Task 3's pattern; `CallSiteFact` field names match Task 5's emitted JSON and Task 8's view columns; the route lists in Tasks 9/12 match Task 7's Interfaces block exactly.
