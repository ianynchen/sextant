# Phase 2D — Messaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kafka, JMS, SQS and Pub/Sub endpoints, inbound and outbound, derived by the engines 2C shipped — the broker family becomes the protocol, the destination expression becomes the wire identity, and no extractor work happens at all.

**Architecture:** The D00 protocol set widens to broker families; `endpoints` gets no DDL change (a messaging row is `method` NULL + `path` = destination expression). Listener annotations ride `annotation_driven` (its SQL gains multi-valued path attributes and NULL-verb rows); templates ride `single_call` (which gains `arity`, `channel_arg`, per-row `direction`, verbless rows and `record_wrappers`); `@SendTo` replies are a small Python second phase in `annotation_driven`. `ConsumerRecord`/`Message` unwrap through the *existing* `wrappers` grammar (`payload_arg: 1`) — the spec's `payload_type_arg` extension is dropped as unnecessary per its own §7 permission.

**Tech Stack:** Python 3.12 + DuckDB (no Java changes); fixture deps spring-kafka, spring-jms, jakarta.jms-api, awspring SQS, spring-cloud-gcp-pubsub, kafka-clients (compile scope only).

**Spec:** `docs/superpowers/specs/2026-08-30-phase-2d-messaging-design.md`

## Global Constraints

- Protocol closed set after this phase: `http, soap, grpc, kafka, jms, sqs, pubsub` (`message` retired unused; spec §1).
- No `endpoints` DDL change; wire identity = (protocol, direction, method-nullable, path) with `IS NOT DISTINCT FROM` semantics on `method`.
- Destination expressions verbatim, never evaluated: literals resolve; `${...}` placeholders resolve as templates; patterns verbatim; variable-borne destinations → `path` NULL, `resolution: unresolved`. Unresolved is an answer, never an omission; NULL keeps exactly one meaning; nothing is guessed.
- Framework names live ONLY in catalogs (protocol names are D00 closed-set values, not framework names, and may appear in engine/egress code).
- All new messaging catalogs copy the 2C outbound catalogs' `wrappers`/`serialization`/`known_types` blocks verbatim (first-in-sort-order harvest compatibility; spec §7) and extend the cross-catalog pinning test.
- Exact-list discipline: frozen route sets extend once from a live run, asserted exactly. Determinism: the double-run byte-identity e2e must stay green.
- No version bumps (`pyproject.toml` stays `0.1.0`). Full `scripts/check.sh` before every commit (pre-commit runs the lint gates). Never commit `uv.lock` or touch `.gitignore`.
- Suite baseline at plan time: 211 passed, 1 skipped.
- Gap rotation is exactly: retire `messaging_endpoints_not_read` from both `KNOWN_GAPS` (`src/sextant/egress/render/metadata.py`) and `_GAPS` (`src/sextant/egress/render/document.py`) in lockstep, 12 → 11, no replacement key.

---

### Task 1: Docs — D00 protocol set, D02 vocabulary, COVERAGE consistency grep

**Files:**
- Modify: `docs/components/D00-fact-schema.md` (the `protocol` closed set, currently `http, soap, grpc, message` at ~line 164), `docs/components/D02-catalog-schema.md` (§2 grammar), `docs/COVERAGE.md` (only if a sentence contradicts the amendments — verify by grep, do not restyle)

**Interfaces:** Produces the amended spec text every later task implements. No code.

- [ ] **Step 1: D00** — the `protocol` set becomes `http`, `soap`, `grpc`, `kafka`, `jms`, `sqs`, `pubsub`. One sentence records the retirement: `message` was reserved and never declared by any shipped catalog; the broker family is the protocol because linking gates on protocol equality (DR-5) and a Kafka topic can never be answered by an SQS queue.
- [ ] **Step 2: D02 §2 (`single_call`)** — extend the `methods` row grammar to `{name, arity?, http_method | method_arg | neither, url_arg | channel_arg, body_arg?, response_arg?, record_arg?, direction?}` with these exact rules, each stated in one or two sentences: `arity` restricts the row to call sites with exactly that many arguments (a row without it matches every overload — the shipped 2C catalogs parse unchanged); `channel_arg` is an alias of `url_arg` for protocols whose identity is a destination, and declaring both on one row is a `CatalogError`; a row declaring **neither** `http_method` nor `method_arg` is *verbless by declaration* — the row derives `method` NULL without penalising `resolution`, and resolved verbless rows dedup on (protocol, direction, path); `direction` on a row overrides the catalog's declared direction (Pub/Sub's `subscribe` is inbound in an outbound file), and on an inbound row the deriving method lands in `handler`, not `caller`; `record_arg` names an argument whose linked constructor carries both identity and payload, resolved through the new catalog-level block `record_wrappers: [{type, channel_ctor_arg, payload_ctor_arg}]` where `payload_ctor_arg` is an integer or the string `last`.
- [ ] **Step 3: D02 §2 (`annotation_driven`)** — three amendments: a multi-valued path attribute (`topics = {"a","b"}`) derives one endpoint per listed value (the `all_methods` precedent extended to identity); `all_methods: []` declares a verbless protocol — one row per mapping, `method` NULL, resolution untouched; the new `reply` block `{annotation, destination_from, payload: return}` derives one additional outbound row per listed reply destination with the handler as `caller` and the handler's return type as the request payload, and a value-returning handler without the reply annotation derives one outbound row with `path` NULL, `resolution: unresolved` (a `void` handler derives no reply row). Extend `request_body` with `excludes: [<fqn types>]` — parameters of these types are ignored by the `sole_unannotated` count (the `(payload, Acknowledgment)` case; spec §2, adopted here as a `request_body` sub-key rather than a separate top-level `payload_excludes`).
- [ ] **Step 4: D02 §2a (`wrappers`)** — one sentence: `payload_arg` already positions the payload type argument, and `ConsumerRecord<K, V>`'s payload is `payload_arg: 1`; the spec's `payload_type_arg` carrier extension is explicitly dropped as redundant (spec §7 permission), recorded here so nobody reintroduces it.
- [ ] **Step 5: Grep for contradictions** — `grep -rn "message\b" docs/components/D00-fact-schema.md docs/components/D02-catalog-schema.md docs/components/D01-graph-schema.md` and `grep -rn "protocol" docs/COVERAGE.md | head -30`; no surviving sentence may name `message` as a live protocol value. D01 needs no change (its wire-identity text already names "the topic expression") — verify, do not edit.
- [ ] **Step 6: Commit**

```bash
git add docs && git commit -m "docs: broker families become protocols, and the catalogs learn messaging vocabulary"
```

---

### Task 2: The Protocol closed set in code

**Files:**
- Modify: `src/sextant/domain/closed_sets.py` (the `Protocol` StrEnum)
- Test: `tests/ingress/test_catalog_source.py` (or the existing catalog-loader test module — find it with `grep -rln "YamlCatalogSource" tests/`)

**Interfaces:**
- Produces: `Protocol` members `HTTP, SOAP, GRPC, KAFKA, JMS, SQS, PUBSUB` (exact lowercase values `kafka`, `jms`, `sqs`, `pubsub`; `MESSAGE` removed). Every later catalog task relies on these loading.

- [ ] **Step 1: Write the failing test** (in the loader test module, following its existing tmp-directory pattern for writing a catalog file and loading it):

```python
def test_broker_family_protocols_load_and_message_is_retired(tmp_path):
    for protocol in ("kafka", "jms", "sqs", "pubsub"):
        _write_catalog(tmp_path, f"x-{protocol}.yml", protocol=protocol)
    loaded = YamlCatalogSource(tmp_path).load()
    assert [c.protocol for c in loaded] == ["jms", "kafka", "pubsub", "sqs"]

def test_message_is_no_longer_a_protocol(tmp_path):
    _write_catalog(tmp_path, "x.yml", protocol="message")
    with pytest.raises(CatalogError, match="closed"):
        YamlCatalogSource(tmp_path).load()
```

(`_write_catalog` is whatever helper the module already uses to author a minimal valid catalog; reuse it, adding a `protocol` parameter if it lacks one. Note the sorted-by-filename load order in the first assertion.)

- [ ] **Step 2: Run to verify both fail** — `pytest tests/ingress -k protocol -v` — the first fails with `CatalogError` (kafka not in the closed set), the second fails because `message` still loads.
- [ ] **Step 3: Amend `Protocol`** in `closed_sets.py`: remove `MESSAGE = "message"`, add `KAFKA = "kafka"`, `JMS = "jms"`, `SQS = "sqs"`, `PUBSUB = "pubsub"`. Then `grep -rn '"message"' src/ tests/ | grep -v __pycache__` — any live reference to the retired value (there should be none outside historical docs) is fixed or the finding is escalated in the report.
- [ ] **Step 4: Run** `pytest tests/ -x -q` — full suite green (211 + 2 new).
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: the protocol closed set names broker families"`

---

### Task 3: SQL — NULL-verb identity, multi-valued paths

**Files:**
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql`, `src/sextant/storage/duckdb/derive_call_endpoints.sql`, `src/sextant/storage/duckdb/merge_endpoints.sql`
- Test: `tests/storage/test_workspace.py` (or wherever derivation SQL is unit-tested — `grep -rln "derive(" tests/storage/`)

**Interfaces:**
- Consumes: Task 2's protocols (tests may use `kafka`).
- Produces: (a) `derive_endpoints.sql` derives one row per element of a multi-valued path attribute, and derives `method` NULL when the effective method list is empty; (b) all three files compare `method` with `IS NOT DISTINCT FROM` so NULL-method rows dedup and merge; (c) no behavior change for any existing HTTP row (frozen sets prove it).

- [ ] **Step 1: Failing tests.** Three, driven through the workspace derive API with synthetic facts (follow the module's existing pattern for inserting `annotations`/`symbols` rows and calling `workspace.derive("endpoints", ...)`):

```python
def test_a_multi_valued_path_attribute_derives_one_row_per_value(workspace):
    # annotation args: {"topics": ["order-events", "order-audit"]}
    ... derive with path_from=["topics"], all_methods=[] ...
    rows = workspace.query("endpoints")
    assert [(r["method"], r["path"]) for r in rows] == [
        (None, "order-audit"), (None, "order-events"),
    ]

def test_an_empty_all_methods_derives_one_null_method_row(workspace):
    # single-valued destination, all_methods=[] -> exactly one row, method NULL
    ...
    assert [(r["method"], r["path"]) for r in rows] == [(None, "order-events")]

def test_null_method_rows_dedup_and_merge_on_the_same_identity(workspace):
    # derive the same (kafka, inbound, NULL, "order-events") twice via
    # derive("endpoints", ...); then a call_endpoints row with the same
    # identity outbound plus a second identical one; then endpoints_merge.
    # Expect: one inbound row survives the double derivation, one outbound
    # row survives the call batch, and the merge folds them into one `both`.
    ...
```

- [ ] **Step 2: Run to verify failures** — the first derives only `order-events` (element 0), the second derives zero rows (UNNEST of empty list), the third duplicates (`NULL = NULL` is unknown in the NOT EXISTS joins and in merge's equality join).
- [ ] **Step 3: Amend `derive_endpoints.sql`.** In `declared`, path becomes a list — replace the `path` expression with the `method_from` pattern applied to `$path_from` aliases:

```sql
coalesce(list_extract(list_filter(list_transform(
    $path_from::VARCHAR[],
    n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
              THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                            [a.args ->> n]) END
), v -> v IS NOT NULL), 1), ['']) AS paths
```

In `mappings`, UNNEST both dimensions (cross product — a two-topic, two-method mapping is four identities) and make the empty method list mean one NULL:

```sql
mappings AS (
    SELECT d.target AS method_symbol,
           UNNEST(CASE WHEN len(d.methods) = 0
                       THEN [CAST(NULL AS VARCHAR)] ELSE d.methods END) AS wire_method,
           UNNEST(d.paths) AS path_suffix
    FROM declared d
)
```

(DuckDB UNNESTs multiple lists in one SELECT positionally, zipping them — verify with a two-topic fact that the result is the cross product; if zipping occurs instead, nest the UNNESTs as two chained CTEs, methods first, then paths.) In the final `WHERE NOT EXISTS`, change `existing.method = d.method` to `existing.method IS NOT DISTINCT FROM d.method`.

- [ ] **Step 4: Amend `derive_call_endpoints.sql`** — the NOT EXISTS gains `IS NOT DISTINCT FROM` on `method` (path stays as-is: NULL paths must NOT dedup, per 2C's I2 reasoning, and `IS NOT DISTINCT FROM` on path would wrongly merge them — leave `existing.path = r.path`). Amend `merge_endpoints.sql`: every `method` equality (`GROUP BY` is already NULL-safe; the joins at ~:24 and ~:33 are not) becomes `IS NOT DISTINCT FROM`.
- [ ] **Step 5: Run** the three new tests (pass) and `pytest tests/ -q` — the frozen 36-route set and every existing derivation test must be untouched.
- [ ] **Step 6: Commit** — `git add -A src tests && git commit -m "feat: wire identity survives a NULL verb and multi-valued destinations"`

---

### Task 4: Fixture — the messaging layer

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/messaging/OrderEventsListener.java`, `AuditJmsListener.java`, `ShipmentsSqsListener.java`, `NotificationsSubscriber.java`, `EventProducers.java`, and `com/acme/orders/contracts/OrderEvent.java` (a small DTO: `orderId` String, `total` BigDecimal, `placedAt` Instant)

**Interfaces:**
- Produces: compiled fixture classes whose facts Tasks 6–11 derive from; the exact class/method inventory below is what the checkpoint freezes shapes from.

- [ ] **Step 1: Dependencies** (compile scope, versions aligned with the existing spring 6.1.6 tree — adjust patch versions only if `mvn -o` cannot resolve, and record what resolved):

```xml
<dependency><groupId>org.springframework.kafka</groupId><artifactId>spring-kafka</artifactId><version>3.1.4</version></dependency>
<dependency><groupId>org.apache.kafka</groupId><artifactId>kafka-clients</artifactId><version>3.6.2</version></dependency>
<dependency><groupId>org.springframework</groupId><artifactId>spring-jms</artifactId><version>6.1.6</version></dependency>
<dependency><groupId>jakarta.jms</groupId><artifactId>jakarta.jms-api</artifactId><version>3.1.0</version></dependency>
<dependency><groupId>io.awspring.cloud</groupId><artifactId>spring-cloud-aws-sqs</artifactId><version>3.1.1</version></dependency>
<dependency><groupId>com.google.cloud</groupId><artifactId>spring-cloud-gcp-pubsub</artifactId><version>5.1.2</version></dependency>
```

- [ ] **Step 2: The listeners.** `OrderEventsListener`: `@KafkaListener(topics = {"order-events", "order-audit"}) void onEvent(OrderEvent event, Acknowledgment ack)`; `@KafkaListener(topics = "order-returns") @SendTo("order-return-receipts") ReceiptView onReturn(OrderEvent event)` (add `ReceiptView` to contracts if absent — reuse an existing DTO if one fits); `@KafkaListener(topicPattern = "order-.*-dlq") void onDeadLetter(ConsumerRecord<String, OrderEvent> record)`; `@KafkaListener(topics = "order-batches") void onBatch(List<OrderEvent> events)`; `@KafkaListener(topics = "order-escalations") ReceiptView escalate(OrderEvent event)` (value-returning, NO `@SendTo` — the dynamic-reply row). `AuditJmsListener`: `@JmsListener(destination = "audit.queue") void onAudit(OrderEvent event)`; `@JmsListener(destination = "audit.raw") void onRaw(jakarta.jms.Message message)`. `ShipmentsSqsListener`: `@SqsListener("shipments-inbound") void onShipment(OrderEvent event)`. `NotificationsSubscriber`: a constructor-injected `PubSubTemplate` field and one method calling a typed subscribe variant on it with subscription literal `"order-notifications"` and `OrderEvent.class` (use the real API — `subscribeAndConvert(String, Consumer<ConvertedBasicAcknowledgeablePubsubMessage<OrderEvent>>, Class<OrderEvent>)`; whatever overload actually compiles is what the checkpoint freezes).
- [ ] **Step 3: The producers.** `EventProducers` with injected `KafkaTemplate<String, OrderEvent>`, `ReplyingKafkaTemplate<String, OrderEvent, ReceiptView>`, raw `KafkaProducer<String, OrderEvent>`, `JmsTemplate`, `SqsTemplate`, `PubSubTemplate` fields and one method each: `kafkaTemplate.send("order-events", event)`; `kafkaTemplate.send("order-events", key, event)`; `kafkaTemplate.sendDefault(event)`; `kafkaTemplate.send(new ProducerRecord<>("order-audit", event))`; `rawProducer.send(new ProducerRecord<>("order-raw", key, event))`; `replyingTemplate.sendAndReceive(new ProducerRecord<>("order-returns", event))`; `jmsTemplate.convertAndSend("audit.queue", event)`; `jmsTemplate.convertAndSend(event)` (destination-less); `sqsTemplate.send("shipments-outbound", event)`; `pubSubTemplate.publish("order-notifications", event)`.
- [ ] **Step 4: Compile** — `mvn -q -o -f fixtures/orders-service/pom.xml compile` (drop `-o` once if new artifacts must download, then confirm a second offline run works). Fix compile errors by adjusting to the real APIs — every adjustment goes in the report verbatim, because the checkpoint freezes from what actually compiled.
- [ ] **Step 5: Regenerate fixture facts** exactly the way `tests/e2e` consumes them (find the recipe: `grep -rn "fixtures/orders-service" tests/e2e/ scripts/ | head`) and note the new fact/document counts.
- [ ] **Step 6: Commit** — `git add -A fixtures && git commit -m "feat: the fixture speaks kafka, jms, sqs and pubsub"`

---

### CHECKPOINT (controller, after Task 4, before Tasks 5–11 dispatch)

Freeze from the real compiled facts, amending the affected task briefs before dispatch: (1) the annotation attribute names/shapes as emitted (`topics` scalar-vs-array, `topicPattern`, `destination`, `@SqsListener`'s attribute, `@SendTo`'s `value` array); (2) the real overload descriptors for every producer call and the typed `subscribe` variant that compiled; (3) whether class-level `@KafkaListener` + `@KafkaHandler` is expressible as-is (if yes, add a fixture method + catalog lines to Task 10; if no, one COVERAGE sentence in Task 13); (4) the `SqsTemplate` builder-consumer form (confirm parameter-rooted chains read unresolved — add the fixture method only if it compiles cleanly); (5) the exact expected route additions for Tasks 10–11's frozen sets.

---

### Task 5: `request_body.excludes`

**Files:**
- Modify: `src/sextant/application/resolve/shapes/contracts.py:225-243` (`_body_type`)
- Test: `tests/application/test_shapes.py` (follow its existing `_body_type`/catalog-stub patterns)

**Interfaces:**
- Consumes: `_body_type(signature, catalog)` as shipped.
- Produces: `request_body: {annotation, fallback: sole_unannotated, excludes: [fqn, ...]}` — excluded types never count as the sole unannotated parameter and are never chosen as the body.

- [ ] **Step 1: Failing test:**

```python
def test_excluded_infrastructure_types_do_not_defeat_the_sole_unannotated_fallback():
    catalog = _catalog(request_body={
        "annotation": "x/Payload#",
        "fallback": "sole_unannotated",
        "excludes": ["org.springframework.kafka.support.Acknowledgment"],
    })
    signature = {"parameters": [
        {"type": {"symbol": "com/acme/orders/contracts/OrderEvent#"}, "annotations": []},
        {"type": {"symbol": "org/springframework/kafka/support/Acknowledgment#"}, "annotations": []},
    ]}
    assert _body_type(signature, catalog)["symbol"] == "com/acme/orders/contracts/OrderEvent#"
```

Plus its negative twin: two non-excluded bare parameters still yield `None` (the fallback stays honest). Convert the dotted `excludes` entries with the same `_catalog_symbol` helper the engines use, so catalogs keep writing dotted names.

- [ ] **Step 2: Run, verify FAIL** (two bare params → None today).
- [ ] **Step 3: Implement** — in `_body_type`, before the `bare` comprehension: `excluded = {_catalog_symbol(t) for t in declared.get("excludes", [])}`, then `bare = [p for p in parameters if not p.get("annotations") and p["type"].get("symbol") not in excluded]`.
- [ ] **Step 4: Run** targeted tests, then `pytest tests/ -q` (frozen sets untouched).
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: infrastructure parameters stop hiding the message payload"`

---

### Task 6: `single_call` — arity, channel_arg, per-row direction, verbless rows

**Files:**
- Modify: `src/sextant/application/resolve/engines/single_call.py`
- Test: `tests/application/test_call_engines.py` (its existing synthetic-workspace pattern)

**Interfaces:**
- Consumes: the module as shipped (`run(workspace, catalog)`, `_verb_of`, `_capture_resolved`, the `seen` dedup).
- Produces: `methods` rows honouring `arity` (row skipped unless `len(arguments) == arity` when declared), `channel_arg` (alias of `url_arg`; both on one row → `CatalogError` naming the file), `direction` (row-level override; inbound rows put the symbol in `handler`, `caller` NULL), and verbless rows (a row declaring neither `http_method` nor `method_arg` derives `method` NULL with `resolution` NOT penalised for the missing verb, and dedups on `(protocol, direction, path)` when the path resolved). Multiple rows may now share a `name` (arity disambiguates) — the `methods` dict-by-name at `:40` becomes a list scan.

- [ ] **Step 1: Failing tests** (five, following the module's synthetic call_site fixtures): (a) two `send` rows with arities 2/3 route the body capture to arg 1 vs arg 2 respectively; (b) a `channel_arg` row fills `path` exactly as `url_arg` would, and a row declaring both raises `CatalogError` matching the catalog filename; (c) a `direction: inbound` row derives `handler` set, `caller` NULL, direction `inbound`; (d) a verbless row with a string-literal channel derives `method is None and resolution == "resolved"`; two identical verbless resolved identities derive once; (e) a verbless row whose channel is a parameter derives `path` NULL, `resolution: unresolved`, and two such rows do NOT dedup.
- [ ] **Step 2: Run, verify all fail** (b's error case and (a) fail on the dict-by-name overwrite; (d) fails because `resolution` requires `verb is not None`).
- [ ] **Step 3: Implement.** Replace the `methods` dict with a matcher:

```python
def _matching_method(rows, name, arguments):
    for row in rows:
        if row["name"] != name:
            continue
        arity = row.get("arity")
        if arity is not None and arity != len(arguments):
            continue
        return row
    return None
```

Validate at run start (the `fluent._validate_steps` precedent): every row's `url_arg`/`channel_arg` exclusivity, raising `CatalogError(f"catalog {catalog.source}: ...")`. Effective channel index: `row.get("url_arg", row.get("channel_arg"))`. Verbless flag: `verbless = "http_method" not in row and "method_arg" not in row`; resolution's `verb is not None` term becomes `(verb is not None or verbless)`; the dedup guard `if path is not None and verb is not None` becomes `if path is not None and (verb is not None or verbless)` with key `(protocol, row_direction, verb or "", path)`. Row direction: `row_direction = row.get("direction", catalog.direction)`; the row dict then sets `direction: row_direction`, `handler`/`caller` by `row_direction == "inbound"`.

- [ ] **Step 4: Run** targeted, then full `pytest tests/ -q`.
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: single_call learns arities, channels, verbless rows and inbound rows"`

---

### Task 7: `record_wrappers`

**Files:**
- Modify: `src/sextant/application/resolve/engines/single_call.py`, `src/sextant/application/resolve/shapes/contracts.py` (only if `_linked_constructor` needs a public seam — prefer reusing what `argument_descriptor` already exposes)
- Test: `tests/application/test_call_engines.py`

**Interfaces:**
- Consumes: Task 6's row matcher; `contracts.py`'s existing linked-constructor machinery (read `_linked_constructor` and `CallFacts.caller_call_sites` first — the record's constructor is a `<init>` call site in the same caller, found by the record argument's `source` value id, exactly the `call_wrappers` one-hop).
- Produces: a `methods` row `{name, arity?, record_arg: N}` plus catalog block `record_wrappers: [{type, channel_ctor_arg, payload_ctor_arg}]` (`payload_ctor_arg`: int or `"last"`): the engine resolves the record argument's linked constructor, reads the channel argument at `channel_ctor_arg` through the same `url_of` split, and the payload at `payload_ctor_arg` (`"last"` = the constructor's final argument) through `argument_descriptor`. A record argument whose constructor cannot be linked, or whose channel/payload slots are unresolved, follows I1: row derives, `resolution: unresolved`.

- [ ] **Step 1: Failing tests:** (a) a synthetic caller with `new ProducerRecord("order-audit", <instance OrderEvent>)` linked into `send(record)` derives `(kafka, outbound, None, "order-audit")` resolved with `request_shape` naming OrderEvent; (b) the three-arg constructor (`topic, key, value`) with `payload_ctor_arg: "last"` still lands the payload on the value; (c) an unlinked record argument (kind `unresolved`) derives the row with `path` NULL, unresolved.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** in `single_call.run`: when a matched row declares `record_arg`, resolve `record = _arg_at(arguments, row["record_arg"])`; find its constructor call site (same mechanism `contracts._linked_constructor` uses — if that helper is private-but-importable, import it as the engines already import `_rules_of`/`_enum_symbols`; do not duplicate it); look up the record's type in `record_wrappers` by `_catalog_symbol`; then channel argument = ctor args at `channel_ctor_arg`, payload argument = ctor args at `payload_ctor_arg` (`"last"` → `ctor_args[-1]` when non-empty). Feed them through the exact same `url_of`/`argument_descriptor`/`_capture_resolved` path a direct row uses — the record path must not invent a second resolution rule.
- [ ] **Step 4: Run** targeted + full suite.
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: a producer record's constructor yields the destination and the payload"`

---

### Task 8: `reply` — @SendTo second rows

**Files:**
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py`
- Test: `tests/application/test_call_engines.py` or a new `tests/application/test_reply.py` (match the suite's file-granularity convention)

**Interfaces:**
- Consumes: `workspace.query("annotations")` (columns `target, annotation, args, ...`), `workspace.query("symbols")` (incl. `signature`), `workspace.query("endpoints")`, `workspace.derive("call_endpoints", rows=...)` (the 12-column insert), `_payload_descriptor`/`_rules_of`/`_enum_symbols` from the shapes package, `_catalog_symbol`.
- Produces: `annotation_driven.run` gains a second phase when `catalog.matches` has `reply`: for each *inbound endpoint row this catalog just derived* whose handler carries the reply annotation, one outbound row per listed destination — `{protocol: catalog.protocol, direction: "outbound", method: None, path: <destination>, handler: None, caller: <handler symbol>, peer: None, handler_signature: None, resolution: "resolved", evidence: "compiler", request_shape: <descriptor of the handler's return type>, response_shape: None}`; and for each value-returning handler (return type's wire_type not in `(None, "")` after `_payload_descriptor`) without the annotation, one such row with `path` None, `resolution: "unresolved"`. Ordering: handlers in sorted order, destinations in listed order (NFR-1).

- [ ] **Step 1: Failing tests:** (a) a handler with `@SendTo(["order-return-receipts"])` and return type ReceiptView derives exactly one outbound `(kafka, None, "order-return-receipts")` resolved row, `caller` = the handler, `request_shape` naming ReceiptView; (b) a two-destination `@SendTo` derives two rows; (c) a value-returning handler without `@SendTo` derives one `path` NULL unresolved row; (d) a void handler derives nothing; (e) a handler that never matched this catalog's inbound mapping derives nothing even when annotated. Author annotations/symbols/endpoints synthetically per the suite's workspace fixtures.
- [ ] **Step 2: Run, verify fail** (`run` derives no reply rows today).
- [ ] **Step 3: Implement** `_derive_replies(workspace, catalog)` called at the end of `run` when `"reply" in catalog.matches`: collect this catalog's inbound handler symbols from `workspace.query("endpoints")` (filter `protocol == catalog.protocol and direction in ("inbound", "both") and handler`); index annotations by target for the reply annotation's fqn (`_catalog_symbol` on `matches["reply"]["annotation"]`); destinations = the `destination_from` attribute read as scalar-or-array (mirror the Python-side of the SQL alias pattern: `args.get(name)` list or single); return types from the symbols query's `signature` JSON (`returns` node — verify the exact key against a real signature row first and pin it in the test fixtures); descriptor via `_payload_descriptor(returns_ref, _rules_of(catalog), _enum_symbols(workspace), referenced)` — a `None` descriptor (void/no-wire) means no reply row. Insert via `workspace.derive("call_endpoints", rows=rows)`.
- [ ] **Step 4: Run** targeted + full suite (HTTP catalogs declare no `reply`; nothing else may move).
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: a listener's declared reply derives its outbound endpoint"`

---

### Task 9: Rendering — verbless identities; gap rotation

**Files:**
- Modify: `src/sextant/egress/render/document.py` (identity rendering at ~:107, ~:116, ~:138-141; `_GAPS`), `src/sextant/egress/render/metadata.py` (`KNOWN_GAPS`)
- Test: `tests/egress/test_render.py`

**Interfaces:**
- Consumes: endpoint dicts as rendered today.
- Produces: `_wire_identity(endpoint) -> str` used at all three render sites: for `endpoint["protocol"]` in the verbless set `{"kafka", "jms", "sqs", "pubsub"}` it renders `f"{protocol} {path}"` (path NULL → `f"{protocol} (unresolved)"`); otherwise today's `method (unresolved-when-NULL) + path` logic verbatim. Gap keys: `messaging_endpoints_not_read` removed from both lists in lockstep (12 → 11), equal-length assertion untouched.

- [ ] **Step 1: Failing tests:** (a) a kafka inbound row renders `` `kafka order-events` `` with no `(unresolved)` anywhere; (b) a kafka row with `path` NULL renders `` `kafka (unresolved)` ``; (c) an HTTP row with NULL method still renders `(unresolved) /path` (regression pin); (d) the gap lists no longer contain `messaging_endpoints_not_read` and have length 11.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** `_wire_identity` + the three call sites + the rotation (both files, same position removed). Update any test pinning the 12-count.
- [ ] **Step 4: Run** targeted + full suite.
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: the document renders verbless identities and retires the messaging gap"`

---

### Task 10: The listener catalogs, end to end

**Files:**
- Create: `src/sextant/catalogs/spring-kafka.yml`, `src/sextant/catalogs/spring-jms.yml`, `src/sextant/catalogs/spring-sqs.yml`
- Modify: `tests/application/test_pipeline.py` (frozen set), the cross-catalog compatibility pinning test

**Interfaces:**
- Consumes: everything from Tasks 2–9; checkpoint-frozen attribute shapes.
- Produces: three `annotation_driven` catalogs (protocols `kafka`/`jms`/`sqs`, direction `inbound`, `all_methods: []`, `path_from` per the checkpoint, `request_body` with `fallback: sole_unannotated` and the broker's `excludes` list, `reply` on spring-kafka only, `wrappers` including `{type: org.apache.kafka.clients.consumer.ConsumerRecord, payload_arg: 1, semantics: envelope}` and `{type: java.util.List, ...}` only if the checkpoint shows List isn't already collection-expanded — verify, don't guess) with the 2C-compatible `serialization`/`known_types`/`wrappers` blocks copied verbatim plus the broker-specific wrapper entries. Detect coordinates: `org.springframework.kafka:spring-kafka`, `org.springframework:spring-jms`, `io.awspring.cloud:spring-cloud-aws-sqs`.

- [ ] **Step 1: Author the three catalogs** per the checkpoint-amended shapes. spring-kafka's `reply` block: `{annotation: org.springframework.messaging.handler.annotation.SendTo, destination_from: value, payload: return}`.
- [ ] **Step 2: Run the pipeline live** against the fixture; inspect every derived messaging inbound + reply row. Expected (checkpoint-amended, from the Task 4 inventory): kafka inbound `order-events`, `order-audit`, `order-returns`, `order-.*-dlq` (pattern verbatim), `order-batches`, `order-escalations`; kafka outbound replies `order-return-receipts` (resolved, ReceiptView) and one path-NULL unresolved (escalate); jms inbound `audit.queue` (OrderEvent) and `audit.raw` (payload absent); sqs inbound `shipments-inbound`. The `onEvent` row's payload must be OrderEvent (the `excludes` proof); the batch row's request_shape `wire_type: array`.
- [ ] **Step 3: Freeze** — extend `test_pipeline.py`'s exact route set + counts with the true derived rows; extend the cross-catalog compatibility test to the new files.
- [ ] **Step 4: Full suite + `scripts/check.sh`.**
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: kafka, jms and sqs listeners derive their endpoints"`

---

### Task 11: The producer catalogs, end to end

**Files:**
- Create: `src/sextant/catalogs/spring-kafka-template.yml`, `spring-jms-template.yml`, `spring-sqs-template.yml`, `spring-pubsub.yml`, `kafka-clients.yml`
- Modify: `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`, the cross-catalog compatibility test

**Interfaces:**
- Consumes: Tasks 6–7's grammar; checkpoint-frozen overload descriptors.
- Produces: five `single_call` catalogs, all verbless rows, `requires: [call_site, string_constants]`, 2C-compatible blocks: spring-kafka-template (owner KafkaTemplate: `send` arity 2 `{channel_arg: 0, body_arg: 1}`, arity 3 `{channel_arg: 0, body_arg: 2}`, `send` arity 1 `{record_arg: 0}`, `sendDefault` `{body_arg: 0}` — no channel declared → path NULL unresolved per I1 verified live; plus owner ReplyingKafkaTemplate `sendAndReceive` `{record_arg: 0}` — one catalog may need two owner sections; if `matches.owner` is single-valued, put ReplyingKafkaTemplate rows in the same file only if the loader allows a list, else give it its own `spring-kafka-replying.yml` and say so in the report); spring-jms-template (JmsTemplate `convertAndSend` arity 2 + arity 1 destination-less); spring-sqs-template (SqsTemplate `send` arity 2); spring-pubsub (PubSubTemplate `publish` `{channel_arg: 0, body_arg: 1}` outbound + the checkpoint-frozen typed `subscribe` row with `direction: inbound`, subscription at arg 0, response capture at the class-literal position); kafka-clients (owner KafkaProducer, `send` arities 1/2 both `{record_arg: 0}`, `record_wrappers` ProducerRecord `{channel_ctor_arg: 0, payload_ctor_arg: last}`, detect `org.apache.kafka:kafka-clients`).

- [ ] **Step 1: Author** the five catalogs per checkpoint shapes.
- [ ] **Step 2: Run live**; inspect every derived row. Expected additions (checkpoint-amended): kafka outbound `order-events` (resolved, deduped across the two send arities), `order-audit` (record), `order-raw` (raw producer), `order-returns` (sendAndReceive, response NULL), one path-NULL unresolved (sendDefault); jms outbound `audit.queue` + one path-NULL unresolved; sqs outbound `shipments-outbound`; pubsub outbound `order-notifications` + pubsub inbound `order-notifications` (typed subscribe, OrderEvent payload). Verify the kafka `order-events`/`order-audit`/`order-returns` and jms `audit.queue` and pubsub `order-notifications` identities MERGE with Task 10's inbound rows into `both` where the module holds both sides — read `merge_endpoints`' output and assert what is true.
- [ ] **Step 3: Freeze** the full new exact set (pipeline counts, e2e outbound/inbound counts, document assertions for one kafka row rendered `kafka order-events`); double-run byte-identity must pass.
- [ ] **Step 4: Full suite + `scripts/check.sh`.**
- [ ] **Step 5: Commit** — `git add -A src tests && git commit -m "feat: templates and the raw producer derive their messaging endpoints"`

---

### Task 12: E2E document + determinism sweep

**Files:**
- Modify: `tests/e2e/test_vertical_slice.py`

**Interfaces:** Consumes Tasks 9–11. Produces: e2e assertions that the rendered document carries the messaging sections (at least one inbound kafka identity, the reply row, one `(unresolved)` messaging destination), that `metadata.json` counts messaging rows in its direction/protocol buckets, and that the byte-identity double-run still passes over the grown output — plus the M5-style contract test still validating every fixture fact (it sweeps the new facts automatically; just confirm).

- [ ] **Step 1:** Extend the document/manifest assertions with the true rendered lines (from a live run, exact strings).
- [ ] **Step 2:** Run the full e2e module twice; byte-identity green.
- [ ] **Step 3: Commit** — `git add -A tests && git commit -m "test: the document and manifest carry messaging end to end"`

---

### Task 13: Close-out — COVERAGE, matrix, roadmap, volume

**Files:**
- Modify: `docs/COVERAGE.md`, `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md`

**Interfaces:** Consumes everything. Produces the recorded truth of what shipped.

- [ ] **Step 1:** Measure fixture fact volume before/after (Task 4's report holds the before; re-measure now) and record in the task report; add a COVERAGE note only if growth crosses the 3× rule.
- [ ] **Step 2:** COVERAGE §5 messaging rows → `✅ shipped` for exactly what Tasks 10–11 derive (listeners, templates, raw KafkaProducer); raw JMS/SQS/Pub-Sub drivers, Spring Integration and Cloud Stream stay unshipped with one sentence each naming where they land (2F for the config-driven ones). One sentence each for: JMS queue-vs-topic blindness, `sendDefault`/dynamic destinations as unresolved rows, the `@KafkaHandler` outcome the checkpoint decided. `python3 scripts/coverage_matrix.py` then `python3 scripts/coverage_matrix.py --check`.
- [ ] **Step 3:** Roadmap: 2D row → delivered; its blocked-on paragraph → past tense; 2D's "one new mechanism" sentence updated to what actually shipped (NULL-verb identity + verbless rows; no schema change was needed).
- [ ] **Step 4:** Full `scripts/check.sh`; commit — `git add -A docs && git commit -m "docs: record what Phase 2D shipped"`

---

## Self-review against the spec

**Coverage.** Spec §1 (protocol set, verbatim identities, multi-destination, JMS-kind limitation, rendering) → Tasks 1, 2, 3, 9, 13. §2 (three listener catalogs, payload rule + excludes, carriers via wrappers, batch, raw Message, @KafkaHandler checkpoint, Pub/Sub inbound via single_call) → Tasks 4, 5, 10, 11, checkpoint items 1/3. §3 (arity, channel_arg, record wrapper, per-client coverage, reply, ReplyingKafkaTemplate, peers NULL) → Tasks 6, 7, 8, 11. §4 (fixture, four-layer testing) → Tasks 4, 10, 11, 12. §5 (gap rotation 12→11, rendering, export-by-construction, close-out) → Tasks 9, 12, 13. §6 checkpoint → the block after Task 4. §7 (compatible blocks, vocabulary dropped when unnecessary) → Global Constraints + Task 1 Step 4 (payload_type_arg dropped, recorded in D02).

**Deviations from the spec, argued:** (1) `payload_type_arg` dropped — `wrappers.payload_arg` already does it (spec §7 grants this). (2) `payload_excludes` landed as `request_body.excludes` — same semantics, one home for one rule. (3) Multi-topic and NULL-verb derivation are SQL changes the spec never located — the spec said "riding the existing rules", which was optimistic; Task 3 is the honest cost. (4) `ReplyingKafkaTemplate` may need its own file if `matches.owner` is single-valued — named in Task 11 rather than silently assumed.

**Type consistency checked:** `_matching_method(rows, name, arguments)` (Task 6) is what Task 7's `record_arg` path extends; `_wire_identity` (Task 9) is egress-only; `reply` reads `destination_from` (Tasks 1, 8, 10 agree); `record_wrappers` keys (`type`, `channel_ctor_arg`, `payload_ctor_arg`) match across Tasks 1, 7, 11; the verbless set in Task 9 equals Task 2's new protocol values.
