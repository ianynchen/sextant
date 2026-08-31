# 2E-prep Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pay down the row-ownership debt (a `catalog_id` column deleting two of four ownership mechanisms), make the suite fast, then ship the raw messaging driver clients — including the sixth engine style, `interface_implementation`, and its extractor capability.

**Architecture:** Hardening first so every new catalog is born on the clean ownership model: `catalog_id` stamps every derived row and collapses `_owns` plus the reply pass's annotation intersection to an id comparison; a session-scoped fixture cuts the suite ~3.5×; one dotted notation with conversion at the single `_catalog_symbol` seam. Then two vocabulary extensions (`channel_via` linked-call follow, `when` value-guarded steps), the `implemented_interfaces` extractor capability, the `interface_implementation` engine, and seven driver catalogs.

**Tech Stack:** Python 3.12 + DuckDB; one Java change (ClassScanner already receives `String[] ifaces` in `visit` — plumbing only); fixture deps `software.amazon.awssdk:sqs`, `com.google.cloud:google-cloud-pubsub` (compile scope).

**Spec:** `docs/superpowers/specs/2026-08-31-2e-prep-hardening-design.md`

## Global Constraints

- Branch `feat/2e-prep-hardening` (stacked on `feat/phase-2d-messaging`); no PR until the phase completes; no version bumps (`pyproject.toml` stays `0.1.0`); never commit `uv.lock`, never touch `.gitignore`.
- "Unresolved is an answer, never an omission; destinations verbatim, never evaluated; NULL keeps exactly one meaning; nothing is guessed." Framework names live ONLY in catalogs.
- Spec §4 ruling binds: duplicate rows (fluent-resolved + single_call-degraded for one call) are accepted and documented; ZERO shipped 2D behavior changes.
- Spec §1a ruling binds: the contracts-SQL `handler_signature IS NOT NULL` guard stays unchanged; the `(owner, direction)` re-key is rejected.
- Exact-list discipline (frozen sets extend once from live runs); determinism (the two-run test — which Task 4 extends to `endpoints` — and the double-run e2e stay green); full `scripts/check.sh` before every commit.
- Suite baseline at plan time: 276 passed, 1 skipped. Fixture baseline: 55 endpoints, 31 documents, 407 fact lines.
- All new catalogs copy the verbatim compatibility blocks (`wrappers`/`serialization` from spring-resttemplate.yml, `nullability` from spring-mvc.yml, the scalar `known_types` set); the loader-iterating pinning tests sweep them automatically.

---

### Task 1: `catalog_id` — schema and stamping

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql` (endpoints DDL), `derive_endpoints.sql`, `derive_call_endpoints.sql`, `merge_endpoints.sql`, `src/sextant/application/resolve/engines/annotation_driven.py` (run + reply rows), `single_call.py` (row dict), `fluent.py` (row dict)
- Test: `tests/storage/test_workspace.py`, `tests/application/test_call_engines.py`

**Interfaces:**
- Produces: every `endpoints` row carries `catalog_id` TEXT (nullable); `derive_endpoints.sql` takes `$catalog_id`; `derive_call_endpoints.sql`'s `$rows` STRUCT gains `catalog_id VARCHAR`; a merged `both` row keeps the INBOUND side's id; Task 2 relies on `endpoint["catalog_id"]` being present on every row.

- [ ] **Step 1: Failing tests.** (a) In `test_workspace.py`, following its synthetic-derivation patterns: derive one row via `derive("endpoints", ...)` with `catalog_id="cat-a"` and one via `derive("call_endpoints", rows=[{... "catalog_id": "cat-b" ...}])`; assert `workspace.query("endpoints")` rows carry the ids. (b) A merge test: same identity inbound (id `cat-in`) + outbound (id `cat-out`) → after `endpoints_merge`, the `both` row's `catalog_id == "cat-in"`. (c) In `test_call_engines.py`: a single_call derivation stamps `catalog.id` on its rows (extend one existing test's assertions).
- [ ] **Step 2: Run — all fail** (unknown column / missing key).
- [ ] **Step 3: Implement.** `schema.sql`: add `catalog_id TEXT,` to the endpoints DDL beside `evidence`. `derive_endpoints.sql`: add `$catalog_id AS catalog_id` to `derived` and the column to the INSERT list. `derive_call_endpoints.sql`: add `catalog_id VARCHAR` to the STRUCT and column lists. `merge_endpoints.sql`: no change needed if the merge only UPDATEs the inbound row and DELETEs the outbound (verify by reading; if any SELECT recombines columns, keep the inbound side's value explicitly). `annotation_driven.run`: pass `catalog_id=catalog.id`; `_reply_row` adds `"catalog_id": catalog.id`. `single_call`/`fluent` row dicts add `"catalog_id": catalog.id`.
- [ ] **Step 4: Full suite** — `pytest tests/ -q`; every frozen set untouched (the exact-set assertions don't select catalog_id; verify none does `SELECT *`-style dict equality that now breaks — fix mechanically where they do, itemizing in the report).
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: every endpoint row names the catalog that derived it"`

---

### Task 2: `catalog_id` — the consumers collapse

**Files:**
- Modify: `src/sextant/application/resolve/shapes/contracts.py:207-266` (`_owns`/`_owned_directions`), `annotation_driven.py` (reply handler collection), `src/sextant/egress/render/metadata.py` + `document.py` (gap-key narrowing), `docs/components/D01-graph-schema.md`
- Test: `tests/application/test_shapes.py`, `tests/application/test_reply.py`

**Interfaces:**
- Consumes: Task 1's stamped rows.
- Produces: `_owns(catalog, endpoint)` = `endpoint.get("catalog_id") == catalog.id` (a row with NULL catalog_id is owned by nobody — impossible after Task 1, honest if it happens); `_owned_directions` deleted; the reply pass reads handlers from rows `WHERE catalog_id == catalog.id AND handler IS NOT NULL` with no annotations scan.

- [ ] **Step 1: Update the pinning tests FIRST** (they define the contract): `test_owns_never_crosses_a_protocol_it_was_not_declared_for` and the row-level-direction ownership test in `test_shapes.py` restate their scenarios in catalog_id terms (same behaviors — a catalog owns exactly its own rows — simpler setup: stamp the ids). `test_reply.py`'s cross-catalog phantom test keeps its scenario verbatim: catalog B's row (id B) must yield no reply from catalog A — now via id.
- [ ] **Step 2: Run — fail** (old code ignores catalog_id).
- [ ] **Step 3: Implement.** Replace `_owns`'s body; delete `_owned_directions` and its docstring; in `_derive_replies`, replace the endpoints filter + `matched_handlers` intersection with the id filter, delete the annotations query and the 22-line scoping docstring (replace with two lines: the id is the scope). Grep for `_owned_directions` — zero references must survive.
- [ ] **Step 4: Gap narrowing (lockstep).** Reword `shape_rules_unscoped_to_the_producing_catalog` in BOTH `KNOWN_GAPS` and `_GAPS` (same position): body/contract rules are now id-scoped; what remains unscoped is global shape expansion — a payload type shared across catalogs expands under whoever reaches it first, kept safe by the verbatim-block pins. Update any test pinning the old sentence.
- [ ] **Step 5: D01** — one paragraph beside the endpoints table description: `catalog_id` is provenance for rule scoping, never part of wire identity, never compared across services.
- [ ] **Step 6: Full suite + commit** — `git commit -m "feat: rule scoping reads the producing catalog off the row"`

---

### Task 3: Session-scoped pipeline fixture

**Files:**
- Create: `tests/application/conftest.py`
- Modify: `tests/application/test_pipeline.py` (fixture consumption)

**Interfaces:**
- Produces: `resolved_fixture` (session-scoped): the compiled+scanned+resolved report + workspace paths the read-only tests share. Later tasks' pipeline tests use it.

- [ ] **Step 1: Read every `test_pipeline.py` test**; classify read-only vs mutating (invented catalogs, tmp workspaces). List the classification in the task report.
- [ ] **Step 2: Write `conftest.py`** — port `_resolved_fixture`'s body into `@pytest.fixture(scope="session")`; read-only tests take the fixture parameter; mutating tests keep private runs. Keep the helper for the mutating tests if they share it.
- [ ] **Step 3: Run `pytest tests/application/test_pipeline.py -q` and time it** (expect one compile+scan; wall-clock drop from ~104s to roughly 10-15s), then the FULL suite twice to prove no order-dependence (session fixture + test isolation).
- [ ] **Step 4: Commit** — `git commit -m "test: the pipeline compiles the fixture once per session"`

---

### Task 4: Enforcement one-liners + helper dedup

**Files:**
- Modify: `tests/application/test_pipeline.py` (`test_two_runs_agree_on_every_shape_and_every_field`), `src/sextant/application/resolve/shapes/contracts.py` (shared home), `single_call.py`, `fluent.py`
- Test: existing suites pin behavior

**Interfaces:**
- Produces: the two-run test also compares `workspace.query("endpoints")` row lists; ONE `_arg_at(arguments, index)` and one capture-resolution helper in the shared shapes home, imported by both engines.

- [ ] **Step 1:** Extend the two-run test to `endpoints` (full row-dict list equality). Run — green (2D's caller tiebreak holds); then temporarily drop `caller` from the ORDER BY and confirm the test CAN fail (mutation check), restore.
- [ ] **Step 2:** Dedup `_arg_at` (identical) into the shared home. The two `_capture_resolved`s have different signatures (`declared_index: int|None` vs `declared: bool`) — unify on one signature (`declared: bool`, the more general; single_call passes `method.get("body_arg") is not None` etc.), keeping both engines' tests green unmodified.
- [ ] **Step 3:** Full suite + commit — `git commit -m "refactor: one argument reader and one capture rule, enforced ordering"`

---

### Task 5: One notation + `shapes/arguments.py` split

**Files:**
- Create: `src/sextant/application/resolve/shapes/arguments.py`
- Modify: every `src/sextant/catalogs/*.yml` with slashed fqns, `annotation_driven.py` (convert before binding), `contracts.py` (the moved block + re-exports), `docs/components/D02-catalog-schema.md` (examples), `tests/architecture/` (new source rule)
- Test: `tests/architecture/test_source_rules.py` (or the module holding them)

**Interfaces:**
- Produces: catalogs are 100% dotted; `_catalog_symbol` is the only conversion seam; `arguments.py` holds the call-payload rooting block (`argument_descriptor`, `url_of`, `channel_of`, `split_url`, `supertypes_of`, `_linked_constructor`, `CallFacts`, `CarrierRules`, and Task 4's shared helpers) — Tasks 7+ import from it; `contracts.py` re-exports nothing (imports updated at every consumer, mechanical).

- [ ] **Step 1: New source rule (failing):** no `#` in any `src/sextant/catalogs/*.yml` (follow the existing source-rule test style — regex over file contents). Run: FAILS on the slashed fqns.
- [ ] **Step 2: Rewrite the catalogs** — every `type_annotation`, `prefix_annotation`, `mapping.annotations[].fqn`, `request_body.annotation`, `reply.annotation` to dotted. In `annotation_driven.run`, convert with `_catalog_symbol` before binding (`type_annotation`, `prefix_annotation`, each mapping fqn; `reply.annotation` already converts). Full suite must stay green — the SQL sees identical values.
- [ ] **Step 3: The split** — move `contracts.py:331-617` (the "Call-payload rooting (D02 §2h)" block) plus Task 4's shared helpers to `arguments.py`; update all imports (engines, tests); `lint-imports` must keep 4/4.
- [ ] **Step 4: D02 examples** made dotted-consistent. Full `scripts/check.sh`; commit — `git commit -m "refactor: one catalog notation, and the argument grammar gets its own home"`

---

### Task 6: Fixture — the raw messaging layer

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/messaging/raw/` — `RawJmsBridge.java`, `RawKafkaConsumers.java`, `RawSqsClientSender.java`, `RawPubSubPublishers.java`, `RawPubSubReceiver.java` (a named class implementing `MessageReceiver`), `RawPubSubSubscribers.java` (registrations: the named receiver AND a lambda), `RawKafkaMessageSender.java` (MessageBuilder chain)
- Test: `tests/ingress/test_asm_scanner.py` (document lists extend mechanically)

**Interfaces:**
- Produces: compiled bytecode the checkpoint freezes shapes from. Inventory (destinations exact): jms `createQueue("raw-audit")` → `createProducer`; `createQueue("raw-intake")` → `createConsumer`; kafka `consumer.subscribe(List.of("raw-t1", "raw-t2"))` and `consumer.subscribe(Pattern.compile("raw-.*"))`; sqs `SendMessageRequest.builder().queueUrl("https://sqs.us-east-1.amazonaws.com/123456789012/raw-queue").messageBody(body).build()` → `client.sendMessage(request)`; pubsub co-located `Publisher.newBuilder(TopicName.of(project, "raw-events")).build()` + `.publish(msg)` in one method AND a field-held `publisher.publish(msg)` in another; `Subscriber.newBuilder(ProjectSubscriptionName.of(project, "raw-notify"), new RawPubSubReceiver())` and `Subscriber.newBuilder(ProjectSubscriptionName.of(project, "raw-notify-lambda"), (m, c) -> c.ack())`; `kafkaTemplate.send(MessageBuilder.withPayload(event).setHeader(KafkaHeaders.TOPIC, "raw-messages").build())`.

- [ ] **Step 1:** Dependencies (adjust patch versions only if offline resolution fails; record):

```xml
<dependency><groupId>software.amazon.awssdk</groupId><artifactId>sqs</artifactId><version>2.25.31</version></dependency>
<dependency><groupId>com.google.cloud</groupId><artifactId>google-cloud-pubsub</artifactId><version>1.129.3</version></dependency>
```

- [ ] **Step 2:** Write the classes per the inventory; existing fixture style (constructor injection / plain final fields; static-method locals where a template isn't natural — match `EventProducers`).
- [ ] **Step 3:** `mvn -q -o -f fixtures/orders-service/pom.xml compile` (online once if needed, then offline). `javap -c -p -v` every new call — the descriptor table goes in the report (checkpoint input), including: the `List.of` linked-call fact shape as EMITTED (varargs array vs positional), the inlined `setHeader` first argument (verify `"kafka_topic"` literal), the `interfaces` entries visible in the class file for `RawPubSubReceiver`, and the lambda argument's shape on `newBuilder`.
- [ ] **Step 4:** Extend `test_asm_scanner.py`'s document lists mechanically; full suite green (no catalogs exist yet — endpoint counts unchanged at 55); commit — `git commit -m "feat: the fixture speaks the raw driver clients"`

---

### CHECKPOINT (controller, after Task 6, before Tasks 7-13 dispatch)

Freeze from the report: (1) every overload descriptor; (2) the `KafkaHeaders.TOPIC` inlining truth; (3) the emitted `List.of`/`Pattern.compile`/`TopicName.of`/`ProjectSubscriptionName.of` call-site fact shapes (the `channel_via` and `all_strings` readers are written against these); (4) the `newBuilder` receiver argument kinds (instance + lambda) and the named class's interface table; (5) expected route additions for Tasks 11-12.

---

### Task 7: `channel_via` — the linked-call follow

**Files:**
- Modify: `src/sextant/application/resolve/shapes/arguments.py` (the follow + reader), `single_call.py` (row wiring + validation)
- Test: `tests/application/test_call_engines.py`

**Interfaces:**
- Consumes: `arguments.py`'s `_linked_constructor`-style walk (generalize to non-`<init>` targets), `channel_of`.
- Produces: a methods row may declare `channel_via: {owner, method, arg} | [{...}, ...]` where `arg` is an int or `"all_strings"`; `linked_channels(argument, facts, forms) -> list[tuple[peer, path, resolution]]` in `arguments.py`: resolves the argument's source call site, matches at most one form, reads the channel(s) verbatim (peer always None). Returns `[(None, None, "unresolved")]` for unlinked/unmatched/non-string. `all_strings`: one tuple per resolved string element, PLUS one `(None, None, "unresolved")` when any element is unresolved. The engine derives ONE ROW PER TUPLE (multi-topic precedent). `channel_via` on a row alongside `channel_arg` is fine (channel_arg names the position; channel_via says how to read an instance there); `channel_via` without `channel_arg`/`url_arg` is a `CatalogError`.

- [ ] **Step 1: Failing tests** (synthetic call_site fixtures mirroring the checkpoint shapes): (a) `createProducer(instance→createQueue("raw-audit"))` derives `(jms, outbound, None, "raw-audit")` resolved; (b) `subscribe(instance→List.of("t1","t2"))` with `all_strings` derives two rows; (c) a partially-resolved list derives the resolved rows + one unresolved row; (d) an unlinked instance derives one NULL-path unresolved row; (e) a linked call matching NO declared form derives one NULL-path unresolved row; (f) malformed `channel_via` blocks → `CatalogError` naming file/row/value.
- [ ] **Step 2: Run — fail.** **Step 3: Implement** (the follow generalizes the constructor walk: match linked site by owner symbol + name instead of `<init>`; validation in `_validate_methods`). **Step 4: Full suite.** **Step 5: Commit** — `git commit -m "feat: a channel may arrive through the call that produced the argument"`

---

### Task 8: `when` — the value-guarded step

**Files:**
- Modify: `src/sextant/application/resolve/engines/fluent.py` (`_matching_step`/`_resolve_captures`/`_validate_captures`)
- Test: `tests/application/test_call_engines.py`

**Interfaces:**
- Produces: a step may declare `when: {arg: N, equals: "<literal>"}`: the step matches the chain either way (pass-through when the guard doesn't hold); captures apply only when arg N is a string literal equal to `equals`; an UNRESOLVED arg N poisons every capture the step declares to unresolved (overwriting a prior good capture — the guard never lets an unreadable key preserve a confident answer). Malformed `when` → `CatalogError`.

- [ ] **Step 1: Failing tests:** (a) `setHeader("kafka_topic", "t")` guarded step captures url "t"; (b) `setHeader("other", "x")` captures nothing, chain continues, url stays whatever an earlier step set; (c) `setHeader(<unresolved>, "x")` after a resolved url → row unresolved, path NULL (poisoned); (d) malformed `when` refused at load.
- [ ] **Step 2-5:** red → implement (guard evaluated in `_resolve_captures`' caller where the site's arguments are at hand; poisoning writes an explicit unresolved sentinel into captures, riding Task 4's unified `_capture_resolved`) → full suite → `git commit -m "feat: a step may capture only under a declared literal guard"`

---

### Task 9: `implemented_interfaces` — the extractor capability

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/ClassScanner.java` (`visit` already receives `String[] ifaces` at :94 — carry into the class symbol fact as `interfaces`, converted to symbol form like `supertype` at :474-487), `src/sextant/domain/facts.py` (`SymbolFact.interfaces: list[str] = []`), `src/sextant/storage/duckdb/workspace.py` (named query `implementations`, copying the `supertypes` pattern at :73-76: symbol + interfaces where non-empty), M03's capability table, D00 §5a
- Test: extractor-jvm `ClassScannerTest` (or the module testing symbol facts), `tests/domain/test_facts.py`, the e2e all-facts contract test (sweeps automatically)

**Interfaces:**
- Produces: class symbol facts carry `interfaces` (erased interface symbols, emitted only when non-empty); capability id `implemented_interfaces` declared by the JVM scanner; `workspace.query("implementations")` → rows of `{symbol, interfaces}` (JSON list). Task 10 consumes the query.

- [ ] **Step 1:** Java failing test: a compiled sample class implementing two interfaces → its symbol fact lists both, in declaration order; a class implementing none omits the key. **Step 2:** implement + gradle green. **Step 3:** Python: `SymbolFact.interfaces` default empty (old fact files validate — run the contract test); the named query + a workspace unit test. **Step 4:** M03 marks the capability shipped; D00 §5a one sentence. Regenerate fixture facts; full suite. **Step 5:** commit — `git commit -m "feat: class facts name their interfaces, as a declared capability"`

---

### Task 10: The `interface_implementation` engine

**Files:**
- Create: `src/sextant/application/resolve/engines/interface_implementation.py`
- Modify: `src/sextant/application/resolve/endpoints.py:56` (`_engine_for` registry), `docs/components/D02-catalog-schema.md` (the style's section, per spec §3b verbatim)
- Test: `tests/application/test_call_engines.py` or a new `test_interface_engine.py` (match suite granularity)

**Interfaces:**
- Consumes: `workspace.query("call_sites")`, `query("implementations")`, `arguments.py`'s `linked_channels`/`channel_of`, `_catalog_symbol`.
- Produces: `interface_implementation.run(workspace, catalog)` reading `matches: {interface, handler_method, registration: {owner, method, channel_arg, receiver_arg, channel_via?}}`; per registration call site, one row per resolved channel tuple: `{protocol, direction, method: None, path, handler, caller: None, peer: None, handler_signature: None, resolution, evidence: "compiler", catalog_id, request_shape: None, response_shape: None}` — handler = lambda synthetic method (lambda-kind receiver) or `<type>#<handler_method>` (instance-kind receiver whose type's interfaces include the declared one, direct implementers only), else NULL (the row still derives). Registration is the evidence: implementing classes without a registration derive nothing. Insert via `derive("call_endpoints", rows=...)`; rows sorted by caller-site order (NFR-1).

- [ ] **Step 1: Failing tests:** (a) named-receiver registration derives `(pubsub, inbound, None, "raw-notify")` resolved with handler `...RawPubSubReceiver#receiveMessage...` (synthetic facts per checkpoint shapes); (b) lambda receiver → handler = the synthetic method symbol; (c) unresolvable receiver → handler NULL, row derives; (d) unresolvable channel → path NULL unresolved; (e) an implementing class with NO registration derives nothing; (f) a registered instance whose type does NOT implement the interface → handler NULL (not a fabricated handler); (g) malformed matches → `CatalogError`.
- [ ] **Step 2-5:** red → implement → registry entry (one line; `_engine_for` already errors on unknown styles) → D02 section → full suite → `git commit -m "feat: an implemented interface plus its registration derives the endpoint"`

---

### Task 11: Driver catalogs A — sqs-sdk, jakarta-jms, kafka-consumer

**Files:**
- Create: `src/sextant/catalogs/aws-sqs-sdk.yml`, `jakarta-jms.yml`, `kafka-consumer.yml` (contents per spec §4, checkpoint-amended)
- Modify: `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py` (frozen sets)

**Interfaces:** consumes Tasks 1-8; checkpoint descriptors. Expected additions (verify live FIRST, freeze truth): sqs outbound `/123456789012/raw-queue` with peer `sqs.us-east-1.amazonaws.com`... **no** — the sqs builder catalog uses `url` steps (fluent), so CP-2 splits the absolute queue URL exactly as OkHttp's did; assert what the run shows and note the contrast with `channel_arg`'s verbatim rule in the catalog comment (both are honest; the fluent `url` capture is an http-style URL by AWS's own design). jms outbound `raw-audit` + inbound `raw-intake` (payloads honestly absent); kafka inbound `raw-t1`, `raw-t2` (two rows from one subscribe), `raw-.*` (pattern verbatim).

- [ ] **Step 1:** author catalogs → live run → inspect every row → freeze exact sets → full `scripts/check.sh` + double-run e2e → commit — `git commit -m "feat: the sqs sdk, direct jms and the raw kafka consumer derive their endpoints"`

---

### Task 12: Driver catalogs B — pubsub trio + kafka message

**Files:**
- Create: `src/sextant/catalogs/google-pubsub-publisher.yml`, `google-pubsub-client.yml`, `google-pubsub-subscriber.yml`, `spring-kafka-message.yml` (contents per spec §3b/§4)
- Modify: frozen sets as Task 11

**Interfaces:** consumes Tasks 7-10. Expected (verify live, freeze truth): pubsub outbound `raw-events` resolved (co-located fluent) + one path-NULL unresolved (field-held publish via google-pubsub-client) + possibly a second unresolved from the co-located `publish` ALSO matching the client catalog (the spec §4 duplicate ruling — assert what is true and cross-reference the ruling in a comment); pubsub inbound `raw-notify` (named receiver handler) + `raw-notify-lambda` (lambda handler); kafka outbound `raw-messages` resolved (MessageBuilder chain) + the send(Message) degraded duplicate from spring-kafka-template (the ruling again — assert both rows).

- [ ] **Step 1:** author → live run → inspect (the duplicate rows are EXPECTED; a missing or extra one is not) → freeze → check.sh + double-run → commit — `git commit -m "feat: raw pubsub and message-built kafka sends derive their endpoints"`

---

### Task 13: E2E sweep

**Files:**
- Modify: `tests/e2e/test_vertical_slice.py`

- [ ] **Step 1:** From a live render: assert one raw-driver identity renders (`kafka raw-t1`), the interface-implementation row renders with its handler, and metadata buckets count the new rows; the all-facts contract test passes over the grown tree; double-run byte-identity twice. Commit — `git commit -m "test: the document and manifest carry the raw drivers end to end"`

---

### Task 14: Close-out

**Files:**
- Modify: `docs/COVERAGE.md`, `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md`

- [ ] **Step 1:** Measure fact volume before/after (baseline 407/31); the 3× rule gates any note. COVERAGE: the six B rows → shipped (jakarta.jms direct, SqsClient, KafkaConsumer.subscribe, Publisher builder, Subscriber+MessageReceiver, KafkaTemplate.send(Message)) with the limitation sentences spec §5 lists (Publisher's config-built reality, Pattern match-nothing-links-nothing, JMS registration-as-evidence, the duplicate-row pairing, direct-implementers-only); tidy the `groupId` overclaim in §5.8 (parked 2D ruling). Matrix regen + `--check`. Roadmap: a 2E-prep line recording the catalog_id column, the sixth style, and the capability. Full check.sh; commit — `git commit -m "docs: record what the 2E-prep hardening shipped"`

---

## Self-review against the spec

**Coverage.** §1a → Tasks 1, 2. §1b → Task 3. §1c → Task 5. §1d → Task 4. §1e → Task 5. §2a → Task 7. §2b → Task 8. §3a → Task 9. §3b → Task 10. §4 catalogs+fixture+ruling → Tasks 6, 11, 12. §5 → Tasks 13, 14 (+ doc steps inside 2, 9, 10). §6 → the checkpoint block. §7 sequencing → the task order as written; the seam list rides the final-review dispatch (controller instruction, not a task).

**Corrections made during this self-review:** (1) Task 11's sqs expectation initially contradicted spec §2a's verbatim rule — resolved: the sqs-sdk catalog captures via fluent `url` steps, so CP-2's split applies (AWS queue URLs are genuinely http-style); `channel_arg`'s verbatim rule governs `single_call` channels only; both stated in the task and to-be-stated in the catalog comment. (2) Task 12 names the expected duplicate rows explicitly so the freeze asserts the ruling rather than stumbling on it.

**Type consistency:** `linked_channels(argument, facts, forms)` (Task 7) is what Task 10's engine imports; `catalog_id` stamping (Task 1) matches Task 2's reads and Task 10's row dict; the unified `_capture_resolved(declared: bool, argument)` (Task 4) is what Task 8's poisoning sentinel rides; `workspace.query("implementations")` (Task 9) is Task 10's consumer; every catalog filename in Tasks 11-12 matches spec §4.
