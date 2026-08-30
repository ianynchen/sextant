# Phase 2D — Messaging

Kafka, JMS, SQS and Pub/Sub, inbound and outbound, on the engines 2C shipped. The one
structural change is wire identity: a topic has no verb, so the `endpoints` table's
`method` column — nullable since 2C — stays NULL and the destination expression carries
the identity. Everything else is catalog vocabulary. This phase adds **no extractor
work**: every capability it consumes (`annotations`, `call_site`, `string_constants`,
`chain_reconstruction`) shipped in 2A–2C, which makes 2D the first live test of the
roadmap's bet that "the catalogs are trivial; the identity is not."

Scope ruling (user): Spring-level surfaces plus the raw `KafkaProducer`; other raw
driver clients stay out. Reply ruling (user): `@SendTo` derives a second, outbound
endpoint.

## 1. Wire identity

**D00 §protocol amendment.** The closed set `http, soap, grpc, message` becomes
`http, soap, grpc, kafka, jms, sqs, pubsub`. `message` is retired unused — no shipped
catalog ever declared it, so nothing migrates. The broker family is the protocol in
DR-5's sense: a Kafka producer can only be answered by a Kafka consumer, and making the
family the protocol means linking needs zero new rules — protocol equality already
gates it, and a Kafka topic named `orders` can never link to an SQS queue named
`orders`, which is exactly the fabrication DR-5 exists to prevent.

**No `endpoints` DDL change.** A messaging row is
`{protocol: kafka, direction: inbound|outbound, method: NULL, path: <destination
expression>}`. The endpoint id stays `hash(module, protocol, wire identity template)`
per D01 §id; only the vocabulary of identity widens, not its shape.

**The destination expression is recorded verbatim, never evaluated.**

- A literal `"order-events"` derives `resolution: resolved`.
- A property placeholder `${orders.topic}` derives as the template itself, resolved —
  D01 already declares the template *is* the identity (same string in every
  environment); its value arrives in 2F's `config_join`.
- A `topicPattern` regex derives with the pattern verbatim as `path`. At linking time a
  pattern that matches nothing links nothing — imprecision, not fabrication.
- A destination readable only from a variable derives `path` NULL,
  `resolution: unresolved`. The row still derives: "this method consumes/produces a
  message" is true and useful on its own.

**Multi-destination listeners** (`@KafkaListener(topics = {"a", "b"})`) derive one
endpoint per listed destination, riding the one-row-per-identity rule `all_methods` set
for method-less HTTP mappings.

**JMS destination kind is not encoded.** Whether a JMS destination is a queue or a
topic lives in container-factory configuration, not code. Identity is the destination
expression alone — a stated limitation (one sentence of COVERAGE prose, not a gap key),
never a guess.

**Rendering.** A protocol that defines no verbs renders no verb: messaging rows print
the protocol and the destination (`kafka order-events`), never `(unresolved)` in the
verb position — `(unresolved)` remains the marker for identity the analysis could not
read, and a Kafka row's absent verb is not that. A NULL `path` on a messaging row
renders `(unresolved)` in the destination position exactly as HTTP rows do.

## 2. Inbound — the listener catalogs

Three annotation catalogs ride `annotation_driven` unchanged in engine mechanics:

| catalog | annotation | destination attribute | protocol |
|---|---|---|---|
| `spring-kafka.yml` | `@KafkaListener` | `topics` / `topicPattern` | `kafka` |
| `spring-jms.yml` | `@JmsListener` | `destination` | `jms` |
| `spring-sqs.yml` | `@SqsListener` (io.awspring.cloud) | its queue-names attribute | `sqs` |

Exact attribute names and their scalar/array shapes are **checkpoint-gated** (§6): they
are frozen from the real jars' observed annotation facts at plan time, not guessed here.

**Payload rule — existing grammar plus one exclusion list.** The message payload
parameter is the `@Payload`-annotated one, falling back to `sole_unannotated`; this is
the `request_body` vocabulary verbatim. But real listeners routinely take framework
infrastructure alongside the payload — `(OrderEvent event, Acknowledgment ack)` has two
unannotated parameters and the sole-unannotated fallback would honestly find none. So
the vocabulary gains `payload_excludes:` — a catalog-local list of fully-qualified
types (`Acknowledgment`, `Consumer`, `ConsumerRecordMetadata`, JMS `Session`, …) the
fallback ignores when counting; framework names stay in catalogs, where they belong.
The payload lands in `request_shape`; `response_shape` stays NULL except for §3's reply
rows.

**Carrier extension — `payload_type_arg`.** `ConsumerRecord<K, V>` and
`Message<T>` are carriers, but the payload is not always type argument 0
(`ConsumerRecord`'s payload is `V`, position 1), while `type_carriers` today always
resolves argument 0. The declaration gains an optional position:

```yaml
type_carriers:
  - org.springframework.core.ParameterizedTypeReference          # bare form: arg 0
  - { type: org.apache.kafka.clients.consumer.ConsumerRecord, payload_type_arg: 1 }
  - { type: org.springframework.messaging.Message, payload_type_arg: 0 }
```

The bare-string form keeps meaning position 0, so the four shipped 2C catalogs parse
unchanged.

**Batch listeners** (`List<Foo>`) come out as `wire_type: array` of the item through
the existing collection expansion. **A raw `jakarta.jms.Message` / `TextMessage`
parameter has no derivable shape**: the row derives with the payload descriptor
honestly absent — never a fabricated `object`.

**Class-level `@KafkaListener` with `@KafkaHandler` methods.** The type-level /
method-level role split in D02 §2 appears sufficient (topics at type level, handler
marking at method level), but this is asserted only after the plan proves it on real
bytecode (§6). If the grammar cannot carry it, it becomes a named limitation, not a
stretch.

**Pub/Sub inbound rides `single_call`, not annotations.** Spring Cloud GCP has no
standard listener annotation — subscribers are programmatic
(`pubSubTemplate.subscribe(...)`) or Spring-Integration adapters (config-driven, 2F
territory). The `single_call` grammar gains a per-row `direction: inbound` (every
existing row is implicitly `outbound`): `subscribe`-shaped calls derive inbound rows
with the subscription name at arg 0 and, in the typed variants, the payload class
literal as the payload capture. On a `direction: inbound` row the deriving method
lands in the `handler` column, not `caller` — it is the consumer. Untyped `subscribe`
overloads derive with no payload descriptor. The handler lambda's internals are not
traced (that is `reactive_flow_not_traced`'s territory).

## 3. Outbound — the producer catalogs

A catalog declares exactly one `style`, so listener annotations and template call sites
cannot share a file. The outbound catalogs are `spring-kafka-template.yml`,
`spring-jms-template.yml`, `spring-sqs-template.yml` and `spring-pubsub.yml` (Pub/Sub's
inbound `subscribe` and outbound `publish` are both `single_call`, so they do share
one file), plus `kafka-clients.yml` for the raw `KafkaProducer` — its detect
coordinate is `org.apache.kafka:kafka-clients`, not the Spring starter, so it must
stand alone to detect correctly.

**Overload discriminator — `arity`.** `KafkaTemplate.send(topic, payload)` puts the
payload at arg 1; `send(topic, key, payload)` puts it at arg 2. The `methods` row
grammar matches by name, so rows gain an optional parameter-count discriminator:

```yaml
methods:
  - { name: send, arity: 2, channel_arg: 0, body_arg: 1 }
  - { name: send, arity: 3, channel_arg: 0, body_arg: 2 }
```

A row without `arity` matches every overload, so the shipped 2C catalogs parse
unchanged. `channel_arg` is an alias the loader maps to the same capture as `url_arg`:
messaging catalogs write `channel_arg`, HTTP catalogs keep `url_arg`, both feed `path`.
Declaring both on one row is a `CatalogError`.

**Record wrapper — the constructor form.** `send(ProducerRecord)` and raw
`KafkaProducer.send(ProducerRecord[, callback])` carry both identity and payload in the
record's constructor, whose overloads put the topic at arg 0 and the value **last**:

```yaml
record_wrappers:
  - { type: org.apache.kafka.clients.producer.ProducerRecord,
      channel_ctor_arg: 0, payload_ctor_arg: last }
```

This is a sibling of `call_wrappers`, not a change to it: `call_wrappers` follows a
payload one hop; `record_wrappers` additionally sources the wire identity from the same
constructor. `payload_ctor_arg: last` holds across every `ProducerRecord` overload.

**Per-client coverage.**

- `KafkaTemplate`: both `send` arities; `send(ProducerRecord)` via the record wrapper;
  `sendDefault(...)` targets the config-borne default topic → `path` NULL,
  `resolution: unresolved` (the value is 2F's).
- Raw `KafkaProducer.send` via the record wrapper (user scope ruling).
- `JmsTemplate`: `convertAndSend(destination, payload)`; the destination-less overload
  → NULL-path unresolved; `send(destination, MessageCreator)` builds the message in a
  lambda → the row derives, the payload is honestly unresolved.
- `SqsTemplate`: `send(queue, payload)` covered; the consumer-builder form
  (`send(to -> to.queue(...).payload(...))`) roots a fluent chain on a parameter,
  which 2C's chain walk deliberately reads as unresolved — row derives, captures
  unresolved, named limitation in COVERAGE prose.
- `PubSubTemplate.publish(topic, payload)`.
- `ReplyingKafkaTemplate.sendAndReceive(record)`: outbound row via the record wrapper.
  No overload exposes the reply type at the call site (it lives in the template
  field's generics), so `response_shape` is NULL in 2D — stated, not hedged.

**Reply declaration — `@SendTo` (user ruling).** The inbound catalogs gain a `reply`
block, the phase's second vocabulary extension: one annotation deriving two rows.

```yaml
reply:
  annotation: org.springframework.messaging.handler.annotation.SendTo
  destination_from: value
  payload: return
```

A `@SendTo("dest")` listener derives, besides its inbound row, an outbound row on the
same protocol: `path` = the literal destination, `request_shape` = the handler's return
type, `caller` = the handler method. `@SendTo.value` is `String[]` — one reply row per
listed destination, like multi-topic listeners. A value-returning listener without a
literal destination (reply-to-header routing) derives that outbound row with `path`
NULL, `resolution: unresolved`. A `void` listener derives no reply row.

**Peers stay NULL everywhere.** Broker addresses are configuration — the
`client_base_addresses_not_resolved` story, arriving in 2F.

## 4. Fixtures and testing

**Fixture.** `fixtures/orders-service` gains a messaging layer:

- `messaging/OrderEventsListener.java` — `@KafkaListener` with a topics array; one
  `@SendTo` method returning a DTO; one `ConsumerRecord<String, OrderEvent>`
  parameter; one batch `List<OrderEvent>` method; one value-returning method with no
  `@SendTo`.
- `messaging/AuditJmsListener.java` — `@JmsListener(destination = ...)`; one raw
  `jakarta.jms.Message` parameter.
- `messaging/ShipmentsSqsListener.java` — `@SqsListener`.
- `messaging/NotificationsSubscriber.java` — a typed `pubSubTemplate.subscribe` call.
- `messaging/EventProducers.java` — both `KafkaTemplate.send` arities, `sendDefault`,
  a `ProducerRecord` send, raw `KafkaProducer.send`, `JmsTemplate.convertAndSend`,
  `SqsTemplate.send(queue, payload)`, `PubSubTemplate.publish`.

Dependencies (spring-kafka, the jakarta JMS API, awspring SQS, spring-cloud-gcp
Pub/Sub) enter compile scope only, as okhttp and webflux did. Exact versions are fixed
in the plan against what resolves offline-cleanly.

**Testing — the four layers as always.** Unit tests for each new vocabulary form
(`payload_type_arg`, `arity`, `record_wrappers`, `reply`, `direction: inbound`) plus
loader validation for each (a `CatalogError` naming the file for a malformed form — the
2C `_validate_captures` precedent). The frozen exact route set extends once from a live
run of the real pipeline; e2e asserts the rendered document carries the messaging
sections and the double-run byte-identity test passes unchanged. Determinism, exact-list
discipline and "unresolved is an answer, never an omission" bind every task.

## 5. Gaps, rendering, export, COVERAGE

**Gap rotation.** `messaging_endpoints_not_read` retires from both `KNOWN_GAPS` and
`_GAPS` in lockstep — 12 → 11, no replacement key. Dynamic destinations, `sendDefault`,
and builder-lambda captures land as ordinary `unresolved` rows; Spring-Integration and
Cloud-Stream bindings are config-driven and already slated for 2F, recorded in COVERAGE
prose, not a key.

**Rendering** follows §1's rule; the document's endpoint tables group messaging rows
under their protocol with destination-as-identity.

**Export needs nothing.** Messaging rows enter the same `endpoints` table and flow into
the D06 bundle by construction; e2e asserts they arrive.

**Close-out** mirrors 2C's: COVERAGE §5 messaging rows flip to shipped (raw drivers
other than `KafkaProducer` stay unshipped tiers), matrix regenerated with `--check`,
roadmap 2D → delivered, fact-volume before/after measured and recorded.

## 6. Checkpoint — verified against reality, not guessed

Frozen at a controller checkpoint after the fixture task compiles, before the catalog
tasks dispatch (the 2C pattern):

1. The exact annotation attribute names and shapes: `@KafkaListener.topics` /
   `topicPattern`, `@JmsListener.destination`, `@SqsListener`'s queue-names attribute
   (its `value` vs `queueNames` aliasing), each as observed in real annotation facts.
2. Whether class-level `@KafkaListener` + `@KafkaHandler` is expressible in the
   type-level/method-level grammar as-is.
3. The real `send` / `convertAndSend` / `subscribe` / `publish` overload descriptors
   the fixture bytecode exhibits, fixing each catalog row's `arity` and argument
   positions.
4. The `SqsTemplate` consumer-builder shape as actually compiled (confirming the
   parameter-rooted chain reads unresolved rather than wrong).
5. The exact route set the fixture derives — run once, frozen exactly.

## 7. Architecture notes

The pre-2D carry list is deliberately **not** bundled into this phase: the `_owns`
producing-catalog column (D01 change), the per-catalog `call_sites` scan cost (M10),
and `AnalyzerException` diagnostics (M7) are real, but each is orthogonal to messaging
and none blocks it — messaging catalogs declare the same compatible
serialization/known_types/wrappers blocks as the 2C four, so the first-in-sort-order
expansion stays answer-identical, enforced by the existing cross-catalog pinning test
extended to the new files. If 2D's plan review finds that bet false for any messaging
payload, the producing-catalog column gets pulled into 2D at that point rather than
papered over.

**Amendment (Task 10 fix round 1):** the bet was found false, in real bytecode, in two
directions — a same-direction, different-protocol catalog claiming an HTTP body rule
never meant for it, and (separately) `nullability`, omitted from the harvest, silently
degrading a shared payload's `@NonNull` field once a first-in-sort messaging catalog
reached it. Settled within 2D by scoping `_owns` by protocol as well as direction and
harvesting `nullability` verbatim too, not deferred. The producing-catalog column
remains the principled fix for the class of bug this bet accepted; it is not resolved,
only patched around, and stays slated pre-2E.

New D02 vocabulary summarized for the amendment task: `type_carriers` positional form,
`arity` on `methods` rows, `channel_arg` (alias of `url_arg`), `record_wrappers`,
`reply`, `direction: inbound` on `single_call` catalogs, `payload_excludes`. Seven
forms; each ships with loader validation and a unit test, and any found unnecessary at
implementation time is dropped rather than shipped speculatively. D00 changes: the
protocol set. D01 changes: none (wire identity text already names the topic
expression).
