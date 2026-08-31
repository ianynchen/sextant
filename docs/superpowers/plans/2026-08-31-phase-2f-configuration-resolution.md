# Phase 2F — Configuration Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Config files become facts, every profile resolves into `resolved_config`, the eighth engine (`config_join`) derives Stream bindings and stamps serializer media, and both halves of base addresses join — the annotation-declared half through placeholders, the imperatively-fed half through two additive extractor amendments.

**Architecture:** Format-keyed `ArtifactReader`s (M03's dormant port) emit neutral `config_entry` facts that the analyze stage writes into the same JSONL tree; M04 gains pass 2 as a generic interpreter over a catalog-declared `config_model` (Spring's ships on `spring-web.yml`); `config_join` registers like the other seven styles and runs last (the `protocol_hint` ordering precedent); the field ladder lives beside the existing literal-first ladders in `shapes/arguments.py`. Endpoint rows keep expressions; `resolved_config` carries values; nothing rewrites a row per environment.

**Tech Stack:** Python 3.12 + DuckDB; extractor-jvm (ASM) gains the `field` argument kind and the `field_write` fact — its own version bumps (D05 invalidation), `pyproject.toml` stays 0.1.0.

**Spec:** `docs/superpowers/specs/2026-08-31-phase-2f-configuration-resolution-design.md`

## Global Constraints

- Endpoints keep expressions, never per-environment values; `resolved_config` carries values; consumers select (M04's rule, verbatim).
- Unresolved is an answer with a REASON and an ENVIRONMENT: `missing_key`, `environment`, `remote_source`, `placeholder_cycle` — a closed set; nothing is guessed, no default is invented, NULL keeps one meaning.
- Framework names live ONLY in catalogs. Readers are format-keyed and model-blind: no layering, no profiles, no placeholder logic in ingress. The resolution pass interprets ONE declared `config_model`; a Spring name in the pass is a review-rejectable smell.
- The D00 amendments are written as neutral cross-language contracts first (the `lambda`/`<init>` precedent), JVM instructions as one extractor's mapping.
- Media stamps: only where every resolved environment agrees; never overwrite a non-NULL column; unknown serializer stamps nothing.
- The `field` kind is consulted ONLY by the argument ladders — no shape/nullability behavior change (frozen pins prove it).
- Exact-list discipline: frozen sets extend from live runs, never hand-predicted. Determinism: two-run/double-run byte-identity stays green; every new accumulation is deterministically ordered (NFR-1).
- `pyproject.toml` stays 0.1.0; never commit `uv.lock`; never touch `.gitignore`. `scripts/check.sh` gates every commit.
- Suite baseline at plan time: 410 passed, 1 skipped; endpoint baseline 82 rows (branch stacked on feat/phase-2e-http-inbound).
- Checkpoint discipline: Task 6 freezes spec §6's items (1)–(5); Tasks 7–8 consume those rulings and never guess past an unfrozen one.

---

### Task 1: Docs — D00 amendments, D01 resolved_config, D02 config vocabulary

**Files:**
- Modify: `docs/components/D00-fact-schema.md`, `docs/components/D01-graph-schema.md`, `docs/components/D02-catalog-schema.md`

**Interfaces:** Produces the amended contract text every later task implements. No code.

- [ ] **Step 1: D00 — `config_entry`.** In §5's fact-kind material add the new kind: one per configuration key — `key_raw` (exactly as written), `key_path` (normalized dot-joined segments; arrays as indexed segments `foo[0]`), `value` (verbatim string, never coerced), `doc_index` (multi-document files). The document's `language` column carries the FORMAT (`yaml`, `properties`). State the neutrality rule: a reader never layers, never resolves, never interprets a profile.
- [ ] **Step 2: D00 — `field` argument kind + `field_write` fact**, each with its cross-language contract sentence FIRST (spec §4's rule, the `lambda`/`<init>` pattern): `field` = "an argument that reads a declared field, carrying that field's symbol" (JVM mapping: a GETFIELD/GETSTATIC that is not the enum-constant shape; a Python attribute read or Go struct-field read normalizes the same way); `field_write` = "a constructor assigns parameter N directly to field F" (JVM mapping: the `ALOAD 0; xLOAD k; PUTFIELD` shape in `<init>`; computed assignments emit nothing). Both additive: a consumer that does not know `field` treats it as `unresolved`.
- [ ] **Step 3: D01 — `resolved_config` real.** The §3 row already names it; expand: one row per key per environment, `source` = the winning file, the four unresolved reasons, and the peer-resolution join (a query over outbound expressions × resolved values per environment — endpoints untouched; single-placeholder substitution, a multi-placeholder expression answers unresolved with reason `multi_placeholder` — a fifth reason, added to the closed set here).
- [ ] **Step 4: D02 — `config_model`** as a top-level optional catalog block, the spec §2 YAML verbatim, with the closed profile vocabulary (`from_filename` with the `{profile}`-anywhere marker rule, `from_document_key`, `from_key_prefix` reserved for Quarkus, documented-unimplemented), placeholder grammar (delimiters + default separator only), `key_matching: relaxed | exact`. **§1 capability paragraph** gains the provenance sentence: capabilities are scanner-declared or PIPELINE-declared (`resolved_config` is the first of the second kind). **§2d** updates from sketch to as-specified (`address_from_config` with `selected_by`, the `Function`-derives-two-rows rule, candidate = method whose return type is/implements the declared interface, bean name = method name); add `media_from_config` (rules + values, agreement-across-environments, never-overwrite); note the eighth style's full section arrives with Task 7's engine.
- [ ] **Step 5: Grep for contradictions** — `grep -rn "resolved_config\|config_join" docs/components/ docs/COVERAGE.md | head -30`; no surviving sentence may describe the pre-2F "planned" state as current. Commit: `git commit -m "docs: config facts, resolved_config, and the config vocabulary (2F design §§1-4)"`

---

### Task 2: The readers — `config_entry` facts through the ArtifactReader port

**Files:**
- Create: `src/sextant/application/ports/artifacts.py`, `src/sextant/ingress/read/__init__.py`, `src/sextant/ingress/read/properties.py`, `src/sextant/ingress/read/yaml_config.py`
- Modify: `src/sextant/domain/facts.py` (ConfigEntryFact + the Fact union), `src/sextant/application/ports/detector.py` (`ModuleModel.resource_roots`), `src/sextant/ingress/detect/maven.py` (populate it: `src/main/resources` when present), `src/sextant/application/stages/analyze.py` (read + write between scan and resolve), `src/sextant/cli/app.py` (register the two readers), `src/sextant/storage/duckdb/schema.sql` (a `config_entries` view over raw_facts)
- Test: `tests/domain/test_facts.py` (extend), `tests/ingress/test_config_readers.py` (create), `tests/ingress/test_maven_detector.py` (extend)

**Interfaces:**
- Produces: `ConfigEntryFact(kind="config_entry", document_id, key_raw: str, key_path: str, value: str, doc_index: int = 0)` in the Fact union.
- Produces: `ArtifactReader` protocol — `accepts(file_kind: str) -> bool` (the extension: `properties`, `yml`, `yaml`), `read(request: ReadRequest) -> list[tuple[Document, list[Fact]]]` where `ReadRequest(module_id, version, files: tuple[Path, ...], root: Path)`. Readers RETURN pairs; the analyze stage writes each via `domain.factfile.write_fact_file` into `fact_root / "config" / <slug>.jsonl` — ingress never touches the Workspace port.
- Produces: `config_entries` view: `document_id, key_raw, key_path, value, doc_index, rowid AS seq` from raw_facts `WHERE kind = 'config_entry'`.

- [ ] **Step 1: Failing model + reader tests.** ConfigEntryFact round-trips through the factfile writer/reader. Properties reader: `a.b.c=v` → key_path `a.b.c`, value verbatim (trailing spaces, `${x}` untouched); a malformed line does not kill the file. YAML reader: nested maps flatten to dotted paths; a list value becomes `foo[0]`, `foo[1]`; a multi-doc file emits `doc_index` 0,1,…; scalars stringify verbatim (`true` stays `"true"` — never coerced); an unparseable file yields a Document with `partial=True, partial_reason` set and zero entries. Detector: `resource_roots` contains `src/main/resources` for the fixture, empty for a POM without one.
- [ ] **Step 2: Implement.** Document fields mirror what the scanner emits (read one scanner-written document line from a fixture fact file for the exact field set; `language` = the format; `scanner_id: "sextant-config-reader"`, its own version constant; `content_hash` over the file bytes; `document_id` derived the way existing hand-built test documents derive theirs). Deterministic entry order: file order within a document is declaration order (NFR-1); files sorted by relative path.
- [ ] **Step 3: Wire.** analyze: after scan, glob each resource root for files whose extension some reader accepts, group by reader, write returned pairs. CLI registers `[PropertiesReader(), YamlConfigReader()]`. A module with no resource roots reads nothing and changes nothing.
- [ ] **Step 4: Suite.** No fixture config files exist yet, so the live pipeline is byte-identical — the full suite must pass UNCHANGED (410 + the new unit tests). Commit: `feat: config files become facts through the ArtifactReader port`

---

### Task 3: Fixture — config files and the code that reads them

**Files:**
- Create: `fixtures/orders-service/src/main/resources/application.yml`, `application-prod.yml`, `bootstrap.yml`; `fixtures/orders-service/src/main/java/com/acme/orders/streams/OrderStreamBindings.java`, `.../config/BillingClients.java` (the three half-2 clients + one computed-base miss)
- Modify: one existing messaging listener gains a `${orders.audit.topic}` destination (pick `AuditJmsListener` — its literal destination becomes the placeholder, and `application.yml` supplies the value, keeping the rendered identity an expression per M04)
- Test: pins in `tests/application/test_pipeline.py`, `tests/ingress/test_asm_scanner.py` (document counts), `tests/e2e`, `tests/cli` as the live run dictates

**Interfaces:** Produces the bytecode + config surface Tasks 4–8 pin against. Config content (exact keys, so later tasks' briefs can cite them): `orders.audit.topic: audit-events`; `billing.url: http://billing.internal` (overridden in prod: `http://billing.prod.internal`); `only.in.default: yes` (ABSENT from prod — the per-env unresolved pin); `boot.layer.probe` in bootstrap.yml overridden by application.yml (layering pin); a multi-doc section activating on `prod` setting `extra.prod.key`; `spring.cloud.function.definition: "handleOrder;auditTap;pipeA|pipeB"`; `spring.cloud.stream.bindings.handleOrder-in-0.destination: order-events`; `...auditTap-out-0.destination: audit-tap` ; NO binding key for one selected bean (the missing-key pin needs a selected bean whose destination key is absent — add `spring.cloud.function.definition` entry `orphanConsumer` with no binding key); `spring.kafka.producer.value-serializer: org.springframework.kafka.support.serializer.JsonSerializer`, `spring.kafka.consumer.value-deserializer: ...JsonSerializer` (same in prod — agreement holds).

- [ ] **Step 1: Streams.** `OrderStreamBindings`: `@Bean Consumer<OrderEvent> handleOrder()`, `@Bean Supplier<OrderEvent> auditTap()`, `@Bean Consumer<OrderEvent> orphanConsumer()`, `@Bean Consumer<OrderEvent> unselectedBean()` (NOT in `definition` — the selection pin), bodies returning trivial lambdas. Nothing here may call any template/client API.
- [ ] **Step 2: Half-2 clients.** `BillingClients`: (a) `@Value("${billing.url}") private String fieldUrl;` feeding `WebClient.builder().baseUrl(fieldUrl)...retrieve()`-shaped chain; (b) a constructor-injected final field (`BillingClients(@Value("${billing.url}") String url)`) feeding a second chain; (c) a `@ConfigurationProperties(prefix = "billing")` class with a `url` field, injected and read; (d) the computed miss: `baseUrl(this.fieldUrl + "/v2")`. Reuse the chain shapes `InventoryWebClient` already compiles.
- [ ] **Step 3: Config files** per the Interfaces block, comments in each explaining which pin it carries.
- [ ] **Step 4: Pins from the live run.** `mvn -q -o compile` green, then the pipeline: config documents now count (scanner pins, coverage documents); the new WebClient chains derive unresolved outbound rows through the SHIPPED fluent catalog (field-kind doesn't exist yet — their url captures are `unresolved`); the placeholder listener's row keeps its identity with the expression as destination. Extend every touched frozen set from the run; endpoint count lands where the run says (record it in the ledger as the Task 3 baseline). Commit: `fixture: configuration surface — profiles, bindings, and imperatively-fed clients`

---

### Task 4: `resolved_config` — the model interpreter as M04 pass 2

**Files:**
- Create: `src/sextant/application/resolve/config.py`
- Modify: `src/sextant/storage/duckdb/schema.sql` (`resolved_config` table), `workspace.py` (derivations `resolved_config_reset`/`resolved_config_insert` + named query `resolved_config`; add `resolved_config` to `_EXPORTED_TABLES`/`_EXPORT_QUERIES` ordered by `environment, key`), new `src/sextant/storage/duckdb/insert_resolved_config.sql` + `reset_resolved_config.sql`, `src/sextant/application/ports/catalogs.py` (`config_model: dict[str, Any] = field(default_factory=dict)`), `src/sextant/ingress/catalogs/yaml_source.py` (load it), `src/sextant/catalogs/spring-web.yml` (Spring's `config_model` block — the family's base catalog carries the family's model), `src/sextant/application/resolve/pipeline.py` (pass 2 between load and derive_endpoints; then `capabilities = capabilities | {"resolved_config"}`)
- Test: `tests/application/test_config_resolution.py` (create), pins

**Interfaces:**
- Produces: `resolve_config(workspace: Workspace, catalogs: list[Catalog]) -> None` — collects every declared `config_model`, and per model: selects `config_entries` documents by source pattern, enumerates profiles (filename marker + document key), layers per profile in declared order (profile variant over base, later source over earlier), resolves placeholders recursively (`:default`, cycle guard), inserts rows `{key, value, source, environment, unresolved_reason}` (value NULL exactly when a reason is set). Table DDL: `resolved_config(key TEXT, value TEXT, source TEXT, environment TEXT, unresolved_reason TEXT)`.
- Produces: the `resolved_config` capability, pipeline-declared after the pass.

- [ ] **Step 1: Failing unit tests** over hand-built entry rows + a hand-built model (never Spring's names in the test module beyond the model dict): layering (bootstrap < application < profile variant; later source wins); profile enumeration from both mechanisms; `${a}` → `${b}` → literal recursion; `${missing:fallback}` takes the default; `${missing}` → unresolved `missing_key`; a two-key cycle → both `placeholder_cycle`; a value referencing `${ENV_VAR}` that no entry defines and the model marks env-shaped — RULING: any unresolvable placeholder whose key is absent resolves `missing_key`; the `environment` reason is reserved for keys the model's sources explicitly import from the environment (Spring: a `${}` default chain ending in an env-var name is still `missing_key` — one comment says the finer split waits for a model that declares env imports); `remote_source` when the winning value is a `spring.config.import`-shaped URL per a model-declared prefix list; resolved-in-default-missing-in-prod expressible.
- [ ] **Step 2: Implement + DDL.** Deterministic: profiles sorted, keys sorted, insert order fixed. `default_profile` always present.
- [ ] **Step 3: Wire + pins.** Pass 2 runs unconditionally (empty in, empty out). Live pins: the layered `boot.layer.probe`, `billing.url` in both environments with prod's override, `only.in.default` unresolved-for-prod with `missing_key`, the multi-doc `extra.prod.key` in prod only. Endpoint rows UNCHANGED (nothing consumes resolved_config yet). Determinism e2e green (the new table exports; byte-identity covers it). Commit: `feat: every profile resolves into resolved_config`

---

### Task 5: Extractor — the `field` kind and the `field_write` fact

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java` (the `field` branch in `argumentJson`, AFTER the enum-shape check), `ClassScanner.java` (the `<init>` pattern scan emitting `field_write`), `Main.java` (bump the extractor version constant), `src/sextant/domain/facts.py` (`"field"` joins CallArgument kinds; `FieldWriteFact(kind="field_write", document_id, field: str, from_parameter: int)` joins the union), `src/sextant/storage/duckdb/schema.sql` (a `field_writes` view), `workspace.py` (named query `field_writes`: `field, from_parameter` ordered by both)
- Test: `extractor-jvm/src/test/java/...` (extend the scan tests with a field-argument and a ctor-assignment sample), `tests/ingress/test_asm_scanner.py`, `tests/domain/test_facts.py`

**Interfaces:**
- Produces: argument `{kind: "field", symbol: "<owner>#<name>."}` for any GETFIELD/GETSTATIC producer that is not the enum-constant shape (the enum check stays FIRST — own-type constants keep reading `enum`); `field_write` facts from `<init>` bodies matching `ALOAD 0; xLOAD k; PUTFIELD` exactly (slot k maps to parameter index accounting for long/double two-slot widths; any other producer pattern emits nothing).

- [ ] **Step 1: Failing extractor tests** (the repo's existing Java test idiom): a method passing `this.url` to a call → `field` kind with the field's bare symbol; `BigDecimal.ZERO` still reads `enum` (the ordering pin); a constructor `this.url = url;` → one `field_write {from_parameter: 0}`; a constructor `this.url = url + "/x";` → none; a two-slot case (`long` first param, field assigned from param 1) maps the slot correctly.
- [ ] **Step 2: Implement + version bump.** Build the jar the way the repo's build note prescribes; re-scan the fixture.
- [ ] **Step 3: The additive-degrade proof.** Run the FULL Python suite against the rebuilt jar with NO Python changes except the facts model/view: every engine must treat the new kind as it treated `unresolved` — the frozen endpoint sets from Task 3 must be byte-identical (the `field`-kind arguments were `unresolved` before and no ladder consults them yet). Any diff is a defect. Commit: `feat: field reads and constructor assignments become facts`

---

### Task 6: Checkpoint — freeze the config-era reality

**Files:** `.superpowers/sdd/<this-plan>/checkpoint.md` (git-ignored workspace)

**Interfaces:** Written answers to spec §6 items (1)–(5), each quoting fact rows. Tasks 7–8 consume them.

- [ ] **Step 1:** (1) Does `Consumer<OrderEvent>`'s type argument survive into `handleOrder`'s signature facts (`returns.arguments`)? Binding-row shapes hinge on it.
- [ ] **Step 2:** (2) The emitted `field`/`field_write` shapes on the three real `BillingClients` — and confirm the Task 5 Step 3 proof held (cite the run).
- [ ] **Step 3:** (3) `@Value` fact shapes on the field and on the constructor parameter (`Parameter.annotations`), `@ConfigurationProperties` on the class — exact attribute spellings.
- [ ] **Step 4:** (4) The config documents through the readers: multi-doc indices, profile filenames, entry counts.
- [ ] **Step 5:** (5) The expected endpoint/row delta for Tasks 7–8, frozen. Report DONE with one line per item.

---

### Task 7: The `config_join` engine — bindings, media, peers

**Files:**
- Create: `src/sextant/application/resolve/engines/config_join.py`, `src/sextant/catalogs/spring-cloud-stream.yml`, `src/sextant/catalogs/spring-kafka-media.yml`, `src/sextant/storage/duckdb/stamp_media.sql`
- Modify: `src/sextant/application/resolve/endpoints.py` (registry + the style-aware ordering: `config_join` sorts LAST, comment citing D02 §3's `protocol_hint` precedent), `workspace.py` (derivation `stamp_media`; named query `resolved_peers`), `docs/components/D02-catalog-schema.md` (the eighth style's full section)
- Test: `tests/application/test_config_join.py` (create; invented catalogs + hand-built facts), pins

**Interfaces:**
- Consumes: checkpoint (1)/(5); `resolved_config` (Task 4); `requires: [resolved_config]` gating.
- Produces: `run(workspace, catalog)` reading `matches.address_from_config` (key template with `{binding}`, `binding.from: bean_name`, `selected_by`, `suffix` rules with `when.implements` + per-rule `direction`; a `Function` match derives BOTH rows) and `matches.media_from_config` (rules + values). Candidate = `construct_kind` method whose `signature.returns` symbol IS the declared interface or a scanned type implementing it; bean name = `member_name` of the method symbol. Selection: `definition` value absent → all candidates; present → exactly its `;`-split entries; an entry containing `|` (composition) derives ONE row with `path` NULL, `resolution: unresolved`, `handler` NULL — there is no single bean to name a handler from — and the report names the expression verbatim. Missing binding key → row with `path` NULL, unresolved, handler = the bean method (it exists). Resolved key whose VALUE contains `${...}` → destination keeps the expression form. Protocol: from `...bindings.{binding}.binder` / `spring.cloud.stream.default-binder` where resolvable AND the catalog maps binder names to protocols (`binder_protocols: {kafka: kafka, rabbit: jms, ...}` — catalog data); else the catalog's declared protocol. Rows: verbless (`method` NULL), `evidence: compiler`, `catalog_id`, `handler_signature` from the bean method's own signature fact, `request_shape` from the functional type argument per checkpoint (1) (NULL if the facts don't carry it), inserted via the standard `call_endpoints` derive.
- Produces: `stamp_media.sql` — parameterized UPDATE setting `consumes`/`produces` where the target column IS NULL and protocol/direction match; the ENGINE computes the stamp value (env-agreement, class→MIME) and calls it once per rule.
- Produces: `resolved_peers` named query — outbound rows whose `peer` or `path` contains a single `${key}`: join `resolved_config` per environment, substituted via `replace()`; multi-placeholder expressions surface with `unresolved_reason: 'multi_placeholder'`; rows without placeholders pass through with their literal.

- [ ] **Step 1: Failing unit tests**: Consumer/Supplier/Function derivation (Function = two rows); selection (unselected bean derives nothing; absent `definition` selects all); the pipe entry's unresolved row; the missing-key row; expression-preserving destination; binder→protocol mapping incl. the unmapped-binder fallback; media stamping (agreement stamps, per-env split leaves NULL, non-NULL never overwritten, unknown class stamps nothing); `resolved_peers` (single placeholder substituted per env, multi-placeholder unresolved, prod-missing key unresolved for prod only).
- [ ] **Step 2: Implement + catalogs.** `spring-cloud-stream.yml`: `style: config_join`, `protocol: kafka`, `direction: inbound` (per-rule direction overrides), `requires: [resolved_config]`, the `address_from_config` block with the three suffix rules + `binder_protocols`. `spring-kafka-media.yml`: `style: config_join`, the two rules + the values table (JsonSerializer, StringSerializer, ByteArraySerializer as spec'd).
- [ ] **Step 3: D02 §2's eighth-style section** — the vocabulary, the ordering (runs last), the honesty rules (missing key, pipe entry, expression-keeping, agreement-only stamps), the recorded-for-2K sentence (every join's trail is in `resolved_config` + `catalog_id`; the verification seat is 2K's).
- [ ] **Step 4: Pins from the live run** — the checkpoint (5) delta: `handleOrder-in-0` → `(kafka, inbound, NULL, order-events, handler = the bean method)`, `auditTap-out-0` → outbound `audit-tap`, the orphan's missing-key row, the pipe entry's unresolved row, the unselected bean's ABSENCE (assert explicitly), kafka rows' media stamps (`consumes`/`produces` `["application/json"]` where direction matches), and every pre-2F kafka row's stamp state. Commit: `feat: the config_join engine — bindings derive, media stamps, peers resolve`

---

### Task 8: The field ladder — both halves joined

**Files:**
- Modify: `src/sextant/application/resolve/shapes/arguments.py` (the ladder: `field_expression(argument, field_facts) -> str | None` + a `FieldFacts` container built once per engine run: field annotations, `field_writes`, `<init>` parameter annotations, `@ConfigurationProperties` prefixes by enclosing class), `single_call.py` + `fluent.py` (where a url/channel capture reads its argument: a `field`-kind argument first consults the ladder; a returned expression proceeds exactly as a string literal — CP-2 split and all; None → today's unresolved path), `src/sextant/egress/render/metadata.py` + `document.py` (gap rotation: retire `client_base_addresses_not_resolved`; add `computed_base_addresses_not_traced` and `config_as_code_not_read` with their sentences)
- Test: `tests/application/test_call_engines.py` (ladder scenarios), pins, `tests/egress/test_manifest.py` (key list)

**Interfaces:**
- Consumes: checkpoint (2)/(3); Task 5's facts; the catalog's `key_matching` strategy for rung 3 (relaxed binding shared with Task 4's implementation — export the helper from `resolve/config.py`, do not duplicate it).
- Produces: the four-rung ladder exactly as spec §4 orders it; the annotation fqns consulted (`@Value`, `@ConfigurationProperties`) arrive as CATALOG data — a new optional `matches`-level block on the client catalogs (`field_sources: {value_annotation: org.springframework.beans.factory.annotation.Value, properties_annotation: ..., prefix_from: prefix}`) added to `spring-webclient.yml`/`spring-restclient.yml`/`spring-resttemplate.yml`/`okhttp.yml` — no Spring name enters engine code.

- [ ] **Step 1: Failing ladder tests** (hand-built facts): rung 1 (field `@Value` expression returned verbatim); rung 2 (ctor param via `field_write` + parameter annotation); rung 3 (`@ConfigurationProperties` prefix + relaxed-bound field name → the ladder returns `${billing.url}`-equivalent expression? NO — RULING: rung 3 returns the KEY's placeholder expression `${<prefix>.<relaxed-name>}` so every rung yields an expression and downstream is uniform); rung 4 (no match → None, row unresolved as today); a catalog without `field_sources` never consults the ladder (gating pin).
- [ ] **Step 2: Implement + wire.** The ladder is pure; the engines build `FieldFacts` once per run (the `_rules_of`/`_enum_symbols` precedent).
- [ ] **Step 3: Pins from the live run.** The three `BillingClients` chains upgrade from Task 3's unresolved rows to rows whose path/peer carry the `${billing.url}`-derived expression through CP-2 (pin exactly what the run emits, all three rungs distinguishable by caller); the computed case STAYS unresolved (assert explicitly); `resolved_peers` now answers the three with per-environment authorities. Gap keys rotated in lockstep (manifest tests updated; count recorded). Commit: `feat: imperatively-fed base addresses join through the field ladder`

---

### Task 9: Renderer, docs, close-out

**Files:**
- Modify: `src/sextant/egress/render/document.py` (coverage section: environments resolved + every unresolved config key with reason and environment; the one-sentence note that per-environment peers are L's system-document material), `docs/COVERAGE.md` (Stream/aws rows flip + boundaries: config-as-code, setter injection, computed bases, per-env serializer splits, remote sources), `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md` (2F → delivered), `docs/components/M02/M03/M04.md` (readers real, pass 2 real, resource roots), `docs/components/D06-bundle-format.md` (`environments` live — populated from resolved_config's distinct environments into metadata.json via `egress/render/metadata.py`)
- Test: `tests/egress/test_render.py` (an environments + unresolved-key rendering pin), e2e metadata pins

**Interfaces:** Consumes everything shipped; produces the phase's documentation close-out.

- [ ] **Step 1: Renderer + metadata** per the file list; the unresolved-key line renders reason and environment (`only.in.default — missing_key in prod`).
- [ ] **Step 2: COVERAGE flips + boundaries; roadmap; module docs.** Verify no doc still calls pass 2 planned. Also correct §5.12's Spring Integration row (user-caught): its "`config_join` — D02 §2d, Phase 2F" tag overpromises — 2F ships the ENGINE, not that catalog; reword to "rides 2F's `config_join` once catalogued" with its tier unchanged.
- [ ] **Step 3: Matrix + volume + full close.** `python scripts/coverage_matrix.py` + `--check`; fact volume vs the pre-2F baseline in the commit body; full suite + both e2e determinism runs green. Commit: `docs: 2F close-out — coverage, roadmap, environments live`

---

## Final review seam list (hand to the whole-branch reviewer verbatim)

- readers × the resolution pass (facts neutral; the model is catalog data; no Spring name outside catalogs)
- the pass × `config_join` (`resolved_config` is the whole interface; no merge logic in SQL)
- `config_join` × the seven existing engines (stamps never overwrite; ordering last; rows keep expressions; the `call_endpoints` contract untouched)
- the field ladder × CP-2 and the literal-first ladders (an expression behaves exactly as a literal from the split onward)
- the extractor amendments × every existing engine (the additive-degrade proof of Task 5 Step 3; enum-before-field ordering)
- the new facts/tables × the D06 bundle and determinism (resolved_config exports ordered; two-run byte-identity)
- pipeline-declared capability × the gating discipline (skipped visibly, never silently)
