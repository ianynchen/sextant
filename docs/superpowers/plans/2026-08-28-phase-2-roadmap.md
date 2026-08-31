# The coverage program — from Spring Boot to the full estate

What began as "Phase 2 — Spring Boot completeness" is now the roadmap for the whole
committed surface: Java + Kotlin across Spring Boot, Spring Cloud, Micronaut and Quarkus;
Kafka, JMS, SQS and Pub/Sub; protobuf and Avro; GraphQL, WebSocket, SSE and SOAP — plus
the linking tier that turns per-service analyses into a system. Each phase is its own
plan, ships one *capability* and the frameworks that ride it, and ends with the same
review discipline.

**Where we actually are.** Twenty-three of the seventy-six Java rows in
[COVERAGE.md](../../COVERAGE.md) §5 are shipped — about 30%. An endpoint carries request and
response contracts field by field, in both directions, with `required` and `nullable`
resolved; Feign, Retrofit and `@HttpExchange` outbound clients are read (a path a module
both exposes and calls merges into one endpoint), and a module's analysis exports as a D06
bundle. The version bump is gated on the full program below (user decision, twice
reaffirmed): no version moves until Java + Spring Boot and the listed protocols and
frameworks are done.

## Why this order

[DR-5](../../ARCHITECTURE.md) links an outbound endpoint to an inbound one only when
**protocol, wire identity and payload compatibility** all agree — *"the failure mode is
fabrication, not imprecision."* That rule ordered the early phases (shapes before
outbound), and it orders the rest: capabilities first, then the frameworks that ride
them; linking only once peers are real and the edge kinds that carry most estates (HTTP +
messaging) both exist.

| | Phase | Status | Delivers | The one new mechanism |
|---|---|---|---|---|
| **2A** | Shapes and nullability | delivered | field-by-field contracts with `required`/`nullable` | field symbols, type annotations, Kotlin nullability |
| **2B** | Outbound annotation clients + export | delivered (PR #3) | Feign, `@HttpExchange`, Retrofit; the D06 bundle exporter | generalized `annotation_driven`; payload descriptors |
| **2C** | Call-site HTTP clients | delivered — [spec](../specs/2026-08-29-phase-2c-call-site-clients-design.md) | RestTemplate, WebClient, RestClient, OkHttp; PTR payloads; lambda-body calls | linked `call_site` facts (the dataflow pass); `single_call` + `fluent` engines |
| **2D** | Messaging | delivered | `@KafkaListener` (class-level + `@KafkaHandler` included), `@JmsListener`, `@SqsListener`, Pub/Sub `subscribeAndConvert`; `KafkaTemplate`/`ReplyingKafkaTemplate`/raw `KafkaProducer`/`JmsTemplate`/`SqsTemplate`/`PubSubTemplate` producers riding 2C's `single_call` engine unchanged; `@SendTo` replies | non-HTTP **wire identity**: NULL method + the path column carrying the destination, no new `endpoints` column |
| **2E-prep** | Hardening + raw messaging drivers | delivered | `catalog_id` provenance on every `endpoints` row; `channel_via`/`when` catalog vocabulary; six raw driver catalogs — direct jakarta.jms, AWS SDK v2 `SqsClient`, `KafkaConsumer.subscribe`, Google `Publisher`, `Subscriber`+`MessageReceiver`, `KafkaTemplate.send(Message)`; the session-scoped pipeline fixture (suite ~140s → ~50s) | the sixth engine style, `interface_implementation`, gated by a new `implemented_interfaces` capability |
| **2E** | Spring inbound completeness | planned | WebFlux functional routing (`RouterFunctions`, `coRouter`), meta-annotations, inherited `@RequestMapping`, `produces`/`consumes` | the `combinator` engine, on 2C's indy groundwork |
| **2F** | Configuration resolution | planned | `application.yml`/properties into `resolved_config`; environment expressions; **base URLs become real peers**; Spring Cloud Stream and spring-cloud-aws bindings | the `config_join` engine; D02 §2d made real |
| **L** | Linking and system scope | planned | `participants`, `links`, DR-5 over bundles; the system document; shape provenance fixed structurally | M05/M06 over federated Parquet |
| **2G** | Wire formats | planned | protobuf + Avro: format inference, `generated_descriptor` readers, declared shapes into the same tables, proto3 JSON-name projection | format as an inferred channel property (D02 §2c) |
| **2H** | HTTP-adjacent protocols | planned | GraphQL (`@QueryMapping` et al.), WebSocket/STOMP (`@MessageMapping`), SSE | operation-as-endpoint identity; `protocol_hint` engine |
| **2I** | SOAP | planned | JAX-WS + Spring-WS catalogs; WSDL as a declared-shape source | catalog work only, by then |
| **2J** | Second frameworks | planned | Micronaut, Quarkus/JAX-RS, MicroProfile REST Client — **zero engine changes is the acceptance test**; then the typed-Catalog refactor | none — that is the point |
| **2K** | Enrich | planned | `sextant module enrich` — LLM-written sections as overlay claims at `evidence: llm` ([2B spec](../specs/2026-08-29-phase-2b-outbound-and-export-design.md) §6) | redaction-before-wire; first network dependency |

L and 2K are not coverage and may be reordered against the later coverage phases by
priority; the version-bump gate opens after **2J**.

## What each phase is really blocked on

**2C** was the largest single piece of in-house work in
[M03](../../components/M03-scanner.md): `call_site` is
[D00](../../components/D00-fact-schema.md)'s *"load-bearing one"*, and
`chain_reconstruction` *"gates every builder-based client library"*
([D02](../../components/D02-catalog-schema.md)). It shipped as a per-method dataflow pass
emitting linked call sites, with the engines staying catalog-driven joins.

**2D** was blocked on something structural rather than large: the `endpoints` table has a
`method` column because it was built for HTTP; a Kafka topic has no method, and
[D01](../../components/D01-graph-schema.md) already defined wire identity as *"the path
template, the topic expression, the fully-qualified remote method, or the operation
name"*. The catalogs were trivial; the identity was not — and the bet held without a schema
change: `method` reads NULL on a messaging row and the rendered identity drops the verb
(`kafka order-events`, not `kafka NULL order-events`), so `path` alone carries the
destination. 2D's producers rode 2C's `single_call` engine pointed at `send`-shaped methods,
unmodified.

**2F** is the phase that unlocks three stuck things at once: outbound peers
(`client_base_addresses_not_resolved` retires), Spring Cloud Stream and the
spring-cloud-aws bindings (`config_join` — code names a key, the value lives in
configuration), and the environment expressions D06 already reserves a manifest field
for. It is deliberately placed before **L**, because links drawn without real peers are
sparse and links drawn with them are dense.

**2G** exists because two contracts in different formats are not comparable until one is
projected into the other — proto3's JSON mapping renames `total_amount` to `totalAmount`,
so a service defined by a `.proto` but exposed over REST carries different field names
than its own schema states (D02 §2c). Declared shapes land in the same `shapes` tables 2A
built; no second schema.

**2J** is the payoff proof of the catalog thesis: if Micronaut and Quarkus need engine
changes, the architecture failed its own test. It also marks the point where the catalog
vocabulary is stable enough to justify typing the `Catalog` model.

## History — decisions this roadmap already survived

Shapes came before outbound (2A before 2B) because DR-5 without payload compatibility
fabricates links. Nullability rode shapes because a field set without `required` cannot be
compared directionally. Call-site clients were pulled ahead of messaging by user priority
(functional Spring Boot support first). The 2A scoping round also found the D02
serialisation-naming gap (`wire_name` had no catalog vocabulary), amended before code —
the pattern every later phase kept.
