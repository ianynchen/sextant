# 2E-prep — Hardening and the raw messaging drivers

Two halves, one branch, strictly ordered. The hardening half pays down the ownership
debt the 2D architecture review quantified — a `catalog_id` column that deletes two of
the four row-ownership mechanisms, a session-scoped test fixture that returns three
quarters of the suite's wall-clock, one catalog name notation, and two one-line
enforcement pins. The coverage half then ships the raw messaging driver clients on top
of the cleaned model: jakarta.jms direct, AWS SDK v2 `SqsClient`,
`KafkaConsumer.subscribe`, Google `Publisher`/`Subscriber`, and
`KafkaTemplate.send(Message)` — including the codebase's sixth engine style,
`interface_implementation`, and its extractor capability. Hardening comes first so
every new catalog is born on the clean ownership model and every later task runs
against a fast suite.

User rulings binding this spec: everything is in scope including
`Subscriber`+`MessageReceiver` (the new engine style); the work lands before any new
PR, on `feat/2e-prep-hardening` stacked on `feat/phase-2d-messaging`.

## 1. Hardening

### 1a. `catalog_id` on `endpoints`

One nullable TEXT column in `schema.sql`. Every derivation stamps it:
`derive_endpoints.sql` and `derive_call_endpoints.sql` gain a `$catalog_id` bound
parameter; the reply pass stamps `catalog.id` on its rows in Python.
`merge_endpoints.sql` keeps the inbound row's value, exactly as it already keeps the
inbound `handler_signature`, so a `both` row carries the inbound catalog's id.

Consumers change by deletion only:

- `_owns`/`_owned_directions` (`shapes/contracts.py:207-266`) become
  `endpoint["catalog_id"] == catalog.id` — the direction/protocol/row-override
  scoping and its 45 lines of justifying prose are deleted.
- The reply pass's annotation-scoped intersection and its full-table `annotations`
  scan (`annotation_driven.py:96-134`) are deleted; the handler set is read straight
  off this catalog's own rows.
- The contracts-SQL guard (`handler_signature IS NOT NULL`) **stays unchanged**. It
  answers a question `catalog_id` cannot (both rows come from one catalog): whether a
  row's signature is its evidence. The earlier idea of re-keying it on
  `(owner, direction)` is explicitly rejected — direction cannot separate
  signature-carrying outbound rows (Feign, whose caller signature must yield
  contracts) from signature-less reply rows; the existing predicate is already the
  precise one.
- Global shape expansion **stays** first-in-sort-order with verbatim-block
  compatibility, enforced by the loader-iterating pinning tests. The
  `shape_rules_unscoped_to_the_producing_catalog` gap key is **narrowed, not
  retired**: its sentence now describes only the surviving shape-expansion half
  (payload types shared across catalogs expand under whoever reaches them first),
  in lockstep in both `KNOWN_GAPS` and `_GAPS`.

Known accepted edge: if two catalogs ever mapped the same handler to the same wire
identity, the second's reply pass would no longer see the row (its `catalog_id` names
the first). No shipped or planned catalog pair does this — one listener grammar per
protocol — and the old annotation-intersection had the mirror-image edge. Recorded
here so it is a decision, not a surprise.

D01 gains a one-paragraph description of the column: provenance for rule scoping,
never part of wire identity, never compared across services.

### 1b. Session-scoped pipeline fixture

`tests/application/conftest.py` gains a session-scoped fixture performing the one
`mvn compile` + scan + resolve; the read-only `test_pipeline.py` tests (34 of 35 at
last count) consume it. Tests that author invented catalogs or mutate workspace state
keep their own runs — the plan enumerates which by reading each test, not by
assumption. Expected effect: ~140s suite → ~40s.

### 1c. One catalog name notation

Every annotation fqn in every catalog becomes dotted
(`org.springframework.web.bind.annotation.RequestBody`, never
`org/springframework/...#`). Conversion to the SCIP symbol form happens at exactly one
seam — `_catalog_symbol` — applied by `annotation_driven.run` before binding SQL
parameters and by the engines where they already call it. A new source rule (the
`tests/architecture` suite) forbids `#` in `src/sextant/catalogs/*.yml`. D02's
examples are made consistent in the same commit.

### 1d. Enforcement one-liners

- `test_two_runs_agree_on_every_shape_and_every_field` extends to compare
  `endpoints` across two runs — the ORDER BY discipline (including 2D's `caller`
  tiebreak) becomes enforced rather than conventional.
- `_arg_at` and `_capture_resolved`, which exist twice with drifted signatures in
  `single_call.py` and `fluent.py`, deduplicate into the shared shapes home; both
  engines' behavior is pinned by existing tests before the move.

### 1e. `shapes/arguments.py`

The call-payload rooting block (`contracts.py:331-617`, ~290 lines with no dependence
on Catalog orchestration) moves to a new `shapes/arguments.py`. This lands in the
hardening half because §2's `channel_via` extends exactly this block — the new code
should be born in the new home. `contracts.py` keeps contract orchestration and the
(much smaller, post-`catalog_id`) ownership logic.

## 2. Two vocabulary extensions

### 2a. `channel_via` — the linked-call follow

An `instance`-kind captured argument may declare which ordinary call produced it and
where in that call the channel lives:

```yaml
methods:
  - { name: createProducer, arity: 1, direction: outbound,
      channel_via: { owner: jakarta.jms.Session, method: createQueue, arg: 0 } }
```

Mechanics: the argument's `source` value id links to a call site in the same method —
the `_linked_constructor` walk generalized to non-`<init>` targets — and the channel
reads that call's argument at `arg`. `channel_via` may list several
`{owner, method, arg}` forms (createQueue and createTopic; List.of and
Arrays.asList); the linked call matches at most one.

Honesty rules, verbatim from the record wrapper: an unlinked argument, a linked call
matching no declared form, or a non-string slot derives `path` NULL,
`resolution: unresolved` — never a guess.

`arg: all_strings` is the multi-element form for collection factories
(`List.of("t1", "t2")`): every resolved string element derives its own row (the
multi-topic listener precedent), and a partially resolved list (one literal, one
variable) derives the resolved rows **plus one** unresolved row, so nothing vanishes.

Loader/engine validation: malformed blocks are `CatalogError`s naming the file, the
row and the value, per the 2D precedent.

### 2b. `when` — the value-guarded step

A `fluent` step may capture only when another argument holds a specific string
literal:

```yaml
steps:
  - { method: setHeader, when: { arg: 0, equals: "kafka_topic" },
      captures: { url: arg1 } }
```

javac inlines `KafkaHeaders.TOPIC` to the literal `"kafka_topic"`, so the guard
compares the call site's argument string (checkpoint-verified against real compiled
`MessageBuilder` chains before any catalog freezes it). A `setHeader` with a
*different* literal key does not capture — the step still matches the chain and
passes through, like today's unmatched steps. A `setHeader` whose key is
**unresolved** poisons the guarded capture to unresolved: it might be the topic
header, and the guard never lets an unreadable key preserve an earlier confident
answer.

## 3. `interface_implementation` — the sixth engine style

### 3a. The extractor capability

The JVM scanner's class-level symbol fact gains `interfaces` — the directly
implemented interface symbols, from the ClassReader's own interface table (erased
names; no generic signatures). This is the declared capability
`implemented_interfaces`, recorded in M03's table and D00 §5a. Version coupling per
the established rule: the extractor jar rebuilds, fixture facts regenerate, and
`SymbolFact` gains `interfaces: list[str]` defaulting empty so pre-existing fact
files still validate through the all-facts contract test.

### 3b. The engine

```yaml
style: interface_implementation
protocol: pubsub
direction: inbound
requires: [call_site, string_constants, implemented_interfaces]
matches:
  interface: com.google.cloud.pubsub.v1.MessageReceiver
  handler_method: receiveMessage
  registration:
    owner: com.google.cloud.pubsub.v1.Subscriber
    method: newBuilder
    channel_arg: 0
    receiver_arg: 1
    channel_via:
      - { owner: com.google.pubsub.v1.ProjectSubscriptionName, method: of, arg: 1 }
```

The derivation joins two facts per registration call site:

- **Identity** — `channel_arg` through the full capture ladder: string literal →
  resolved; `channel_via` linked call → resolved; anything else → NULL, unresolved.
- **Handler** — the `receiver_arg`: a `lambda`-kind argument resolves to its
  synthetic method symbol (2C's bare-descriptor lambda facts); an `instance`-kind
  argument resolves to its type's `handler_method` when that type's `interfaces`
  include the declared interface. Only direct implementers match — a subclass of an
  implementing class is a stated one-hop limitation. An unresolvable receiver
  derives the row with `handler` NULL: the subscription is consumed; who handles it
  is unread.

**The registration is the evidence.** An implementing class never registered in
scanned code derives nothing — implementing an interface is not an endpoint. This is
stated in D02 to prevent the phantom-endpoint failure mode, and it is why the style
needs no execute-terminal: binding a receiver to a subscription is intent in a way a
built-but-unlogged HTTP request is not (the OkHttp `terminal_via_argument` reasoning,
resolved the other way for this evidence shape, deliberately).

Payload: `PubsubMessage` is a declared no-shape envelope (the `jakarta.jms.Message`
precedent) — `request_shape` honestly absent. Rows are verbless, stamped with
`catalog_id`, and enter the same tables as every style.

Forward value: this style is the landing zone for 2H's WebSocket handlers and 2E's
functional-routing handlers; Pub/Sub's simple case builds it against real facts.

## 4. The driver catalogs and fixture

All new catalogs carry the verbatim compatibility blocks (the loader-iterating pins
sweep them automatically) and are stamped by `catalog_id` from birth.

- **`aws-sqs-sdk.yml`** (`fluent`, sqs, outbound):
  `SendMessageRequest.builder()` root → `queueUrl` (url) / `messageBody` (body)
  steps → `build` terminal with
  `terminal_via_argument: {owner: software.amazon.awssdk.services.sqs.SqsClient,
  method: sendMessage}` — the OkHttp pattern verbatim. Detect
  `software.amazon.awssdk:sqs`.
- **`jakarta-jms.yml`** (`single_call`, jms): `createProducer` (outbound) and
  `createConsumer` (inbound) rows, each `channel_via`
  `createQueue`/`createTopic` arg 0. `send()` is deliberately not read: its payload
  is an opaque `jakarta.jms.Message` (honestly absent anyway), and the
  registration call is the evidence — one mechanism, stated in the catalog comment.
  Detect `jakarta.jms:jakarta.jms-api`.
- **`kafka-consumer.yml`** (`single_call`, kafka, inbound): `subscribe` arity 1 with
  `channel_via` `List.of`/`Arrays.asList`/`Collections.singletonList`
  `arg: all_strings` — one row per resolved topic; the `Pattern` overload resolves
  through `channel_via` `Pattern.compile` arg 0 (pattern verbatim as path, the
  `topicPattern` precedent), else unresolved. Its own file because `matches.owner`
  is single-valued (`KafkaConsumer` ≠ `KafkaProducer`). Detect
  `org.apache.kafka:kafka-clients`.
- **`google-pubsub-publisher.yml`** (`fluent`, pubsub, outbound):
  `Publisher.newBuilder` root with `channel_via` `TopicName.of` arg 1 → `build`
  terminal via `publish` — resolves the co-located build+publish case.
- **`google-pubsub-client.yml`** (`single_call`, pubsub, outbound): a `publish`
  arity-1 `{body_arg: 0}` row with no channel — the field-held-Publisher case
  derives an honest path-NULL unresolved row instead of vanishing (a fluent chain
  that never reaches its terminal derives nothing, so without this row a
  config-built Publisher would be silent).
- **`google-pubsub-subscriber.yml`** (`interface_implementation`, §3b's example).
- **`spring-kafka-message.yml`** (`fluent`, kafka, outbound):
  `MessageBuilder.withPayload` root (body capture, result-keyed static root) →
  `setHeader` with §2b's `when` guard → `build` terminal via
  `{owner: org.springframework.kafka.core.KafkaTemplate, method: send}`.

**Ruling — duplicate rows are accepted, documented, and deliberate.** A
`KafkaTemplate.send(Message)` call is matched both by `spring-kafka-message.yml`
(deriving the resolved topic row) and by `spring-kafka-template.yml`'s arity-1
`record_arg` row (degrading to a path-NULL unresolved row, exactly as 2D shipped and
unit-tested). The co-located `Publisher` case mirrors it. Both rows stand:
"unresolved is an answer, never an omission" outranks tidiness, suppressing the
degraded row would make grammar-mismatch a silence, and cross-catalog suppression is
a linking-phase concern. One COVERAGE sentence documents the pairing; **zero shipped
2D behavior changes**.

**Fixture** — a `messaging/raw` layer (new classes; asm_scanner document lists extend
mechanically): a jakarta.jms producer+consumer pair with `createQueue` literals; a
`KafkaConsumer.subscribe(List.of("raw-t1", "raw-t2"))` and a `Pattern.compile`
subscribe; the `SqsClient` builder send; a co-located `Publisher` build+publish AND a
field-held publish (the honest-unresolved case); a `MessageBuilder` send; a named
`MessageReceiver` implementing class AND a lambda receiver, each bound via
`Subscriber.newBuilder`. Dependencies compile-scope:
`software.amazon.awssdk:sqs`, `com.google.cloud:google-cloud-pubsub` (exact versions
checkpoint-resolved offline).

## 5. Testing, docs, close-out

Four layers as always. Unit tests for every new vocabulary form and validator
(`channel_via` incl. `all_strings` and partial resolution, `when` incl. the
unresolved-key poisoning, the registration/receiver join incl. lambda and
handler-NULL cases); a Java test for the `interfaces` capture; frozen sets extend
once from live runs; the (newly `endpoints`-covering) two-run determinism test;
double-run e2e byte-identity. Docs: D00 (§5a interfaces), D01 (`catalog_id`
paragraph; gap-key narrowing), D02 (§2 `channel_via`/`when`; the new §2-style
section for `interface_implementation`; notation cleanup), M03 (capability table),
COVERAGE (six B rows → shipped with limitation sentences: Publisher's config-built
reality, `Pattern` subscriptions match-nothing-links-nothing, JMS
registration-as-evidence, the duplicate-row pairing), roadmap (a 2E-prep line
recording what landed). Gap lockstep for the narrowed key. No version bump.

## 6. Checkpoint — frozen from reality after the fixture task

(1) The real overload descriptors for every new call (`javap`); (2) the
`KafkaHeaders.TOPIC` inlining claim against compiled MessageBuilder chains; (3) the
emitted `interfaces` fact shape for the named receiver class and the lambda
argument's kind/symbol on `newBuilder`; (4) the `List.of` linked-call fact shape
(varargs array vs positional args — the `all_strings` reader is written against what
is actually emitted); (5) the exact route additions frozen for the catalog tasks.

## 7. Sequencing and review discipline

Task order: 1a → 1b → (1c, 1d, 1e in any order) → fixture → checkpoint → 2a → 2b →
3a → 3b → catalogs (batched sensibly) → e2e sweep → close-out. The final
whole-branch review receives the explicit seam list (ownership column vs reply pass
vs contracts guard; `channel_via` vs the fluent walker; the new engine vs the
registry and capability gate) — the 2D lesson that seam-between-tasks defects are
what scoped reviews structurally miss.
