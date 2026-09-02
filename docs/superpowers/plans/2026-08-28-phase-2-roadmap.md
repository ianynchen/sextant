# The coverage program — from Spring Boot to the full estate

What began as "Phase 2 — Spring Boot completeness" is now the roadmap for the whole
committed surface: Java + Kotlin across Spring Boot, Spring Cloud, Micronaut and Quarkus;
Kafka, JMS, SQS and Pub/Sub; protobuf and Avro; GraphQL, WebSocket, SSE and SOAP — plus
the linking tier that turns per-service analyses into a system. Each phase is its own
plan, ships one *capability* and the frameworks that ride it, and ends with the same
review discipline.

**Where we actually are.** Forty-two of the seventy-nine Java rows in
[COVERAGE.md](../../COVERAGE.md) §5 are shipped — about 53%. An endpoint carries request and
response contracts field by field, in both directions, with `required` and `nullable`
resolved; Feign, Retrofit and `@HttpExchange` outbound clients are read (a path a module
both exposes and calls merges into one endpoint), and a module's analysis exports as a D06
bundle. **2G moved none of those rows, and the count is re-derived rather than carried**:
its flips land in COVERAGE §4 — the format-detection regimes, the protobuf and Avro
spec-binding rows, the Kafka serializer table now live as `format_from`, and a new parser
table carrying Jackson 3 — because §5's checklist is one library per row and wire format is
not a library. Every §5 row it touches was already ✅. **2H then moved nine of them**, and
the headline count is re-derived from those flips rather than carried: four in §5.4 (all
three GraphQL annotation frameworks plus the `graphql-java` SDL row), three in §5.5
(jakarta `@ServerEndpoint`, Spring STOMP, the programmatic `addHandler`) and two in §5.6
(Spring MVC's `SseEmitter` and WebFlux's `Flux<ServerSentEvent<T>>`) — 28 + 9 = 37. **2I
then took §5.3 from `2A` to shipped outright, and moved the denominator with it**: its two
existing Java rows flipped (JAX-WS, Spring-WS) and three more were added for surfaces the
phase also ships and the checklist had never enumerated — `@SoapAction` as a second
identity axis, `WebServiceTemplate` outbound, and JAX-WS generated client stubs — so 37 + 5
= 42 of 79. The WSDL/XSD artifact row flipped too (`C` → shipped) and is counted in no
language's cell. The version bump is gated on the full
program below (user decision, twice reaffirmed): no version moves until Java + Spring Boot
and the listed protocols and frameworks are done.

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
| **2E-prep** | Hardening + raw messaging drivers | delivered | `catalog_id` provenance on every `endpoints` row; `channel_via`/`when` catalog vocabulary; six surfaces (seven catalog files) of raw drivers — direct jakarta.jms, AWS SDK v2 `SqsClient`, `KafkaConsumer.subscribe`, Google `Publisher`, `Subscriber`+`MessageReceiver`, `KafkaTemplate.send(Message)`; the session-scoped pipeline fixture (suite ~140s → ~50s) | the sixth engine style, `interface_implementation`, gated by a new `implemented_interfaces` capability |
| **2E** | Spring HTTP inbound completeness | delivered | WebFlux functional routing (`RouterFunctions`, `coRouter`, Java and Kotlin), module-local meta-annotations, inherited `@RequestMapping`, `produces`/`consumes` — GraphQL, WebSocket and SSE deferred to 2H; SOAP to 2I | the `combinator` engine, on 2C's indy groundwork |
| **2F** | Configuration resolution | delivered | `application.yml`/properties into `resolved_config`, every profile, environment expressions; declared outbound HTTP bases (a field, a constructor-injected value, `@ConfigurationProperties`) become real peers through the field ladder; Spring Cloud Stream's functional bindings resolve their destination through `config_join` — spring-cloud-aws's own channel-adapter bindings and Spring Integration ride the same engine once catalogued, not yet shipped | the `config_join` engine; D02 §2d made real |
| **2G** | Wire formats | delivered — [spec](../specs/2026-08-31-phase-2g-wire-formats-design.md) | `format`/`format_resolution` on every endpoint row from a six-rung catalog-driven ladder; protobuf and Avro schemas — embedded descriptors and `.proto`/`.avsc` sources, compiled winning per DR-4 — landing in 2A's own `shapes`/`shape_fields` with `field_number` and `json_name` wire names; parse-call payload binding at the handler and one hop; the `open_questions` ledger (table, bundle artifact, document section) for what no pass could answer | format as an inferred channel property, stamped by one late pass rather than per match (D02 §2c) |
| **2H** | HTTP-adjacent protocols | delivered — [spec](../specs/2026-09-01-phase-2h-http-adjacent-design.md) | GraphQL inbound across Spring GraphQL, Netflix DGS and MicroProfile plus the `.graphqls` SDL reader (the field is the endpoint); WebSocket/STOMP `@ServerEndpoint`/`@MessageMapping`/`@SubscribeMapping`/`@SendTo` and the programmatic `addHandler`; SSE by reclassification from a `produces` string or a return-type marker — nine §5 rows flipped | both reserved mechanisms, and neither landed as sketched: operation-as-endpoint identity became the `schema_operations` engine style (the ninth), and `protocol_hint` became a post-merge **resolve pass** rather than an engine |
| **2I** | SOAP | delivered — [spec](../specs/2026-09-01-phase-2i-soap-design.md) | JAX-WS (`@WebService`/`@WebMethod`, both spellings, bare public methods included) and Spring-WS (`@PayloadRoot`, `@SoapAction`) inbound; `WebServiceTemplate` and generated client stubs outbound; a stdlib-XML `.wsdl`/`.xsd` reader and interpreter branch whose input elements derive schema-first operations — five §5.3 rows shipped, on the QName wire identity | **`.sextant.yml`** — opt-in, per-library extraction of a dependency's own bytecode, the first analysis-configuration file living in the analysed repository |
| **2K** | Enrich | planned | `sextant module enrich` — LLM-written sections as overlay claims at `evidence: llm` ([2B spec](../specs/2026-08-29-phase-2b-outbound-and-export-design.md) §6); the LLM verification seat D02 §2d reserves for doubtful config joins (2F records the evidence, 2K judges it) | redaction-before-wire; first network dependency |
| **2J** | Second frameworks | planned | Micronaut, Quarkus/JAX-RS, MicroProfile REST Client — **zero engine changes is the acceptance test**; then the typed-Catalog refactor | none — that is the point |
| **L** | Linking and system scope | planned | `participants`, `links`, DR-5 over bundles; the system document; shape provenance fixed structurally | M05/M06 over federated Parquet |

**The remaining sequence, and its three milestones** (2K deliberately moved ahead of 2J,
ruled 2026-08-31: a complete end-to-end flow for module-level Java/Spring — coverage,
enrichment, docs and export together — comes before any second Java framework; L moved
after 2J, ruled 2026-08-31 post-2F: everything module-level for Java lands first, then
linking services into a system-level architecture begins):

1. After **2I**: Spring Boot module-level *coverage* is complete — every declaration
   form a Spring service uses derives, modulo the named A-tier catalog rows (RabbitMQ,
   Pulsar, Micronaut variants — one YAML file each) and the ledgered extractor
   candidates (vararg constants, batch-listener generics).
   **DECLARED, 2026-09-02.** 2I shipped, and with it the last protocol on **this
   roadmap's** committed list: REST in both directions, GraphQL, WebSocket, SSE, SOAP,
   Kafka, JMS, SQS and Pub/Sub all derive from a Spring service's own declarations,
   carrying configuration-resolved peers, wire formats and field-by-field payload
   contracts. Forty-two of seventy-nine Java rows, and SOAP's §2a column joins
   GraphQL's and WebSocket's as one with no unshipped row left in it.

   **That list is narrower than [REQUIREMENTS.md](../../REQUIREMENTS.md)'s version-1
   scope, which also names gRPC** (§ Scope, and FR-3). gRPC has no shipped Java row at
   all, so it is named in the modulo below rather than folded into this declaration.
   Whether v1 scope should still carry it is the user's decision and is not taken here.

   **What the "modulo" actually covers, stated rather than waved at**, because the
   sentence above is a claim about *committed* coverage and not about every line a
   Spring codebase can contain. Still open and still Spring: the A-tier catalog rows
   this milestone always excepted (`@Scheduled`, `@RabbitListener`/`@PulsarListener`,
   the two older `@SqsListener` package spellings, Actuator `@Endpoint`, Spring 7's
   `version =` and `ImportHttpServices`, and both Spring-side gRPC rows —
   `org.springframework.grpc.server.service.GrpcService` and the Spring Boot starter's
   `net.devh.boot.grpc.{server.service.GrpcService, client.inject.GrpcClient}` — one
   YAML file and a fixture each); two B-tier Spring rows that need a catalog on an
   existing engine rather than an engine (Spring Integration's channel adapters, Spring
   Cloud GCP's `PubSubTemplate.subscribe`); the JVM's own inheritance-shaped gRPC
   server, which is the B-tier row under those two and leaves gRPC — a protocol
   REQUIREMENTS' v1 scope names — with no shipped Java row at all; and the four C-tier
   REST forms where the boundary is not a declaration at all (`@RepositoryRestResource`,
   `@ControllerAdvice` error contracts, servlets and filters, environment-conditional
   controllers). The ledgered engine-side candidates are unchanged — vararg media
   constants and batch-listener generics in the extractor — and 2I adds two on the
   interpreter side: `xsd:attribute` and `complexContent`, which gap a schema file
   today and are cheap to project.

   What this milestone is NOT: it is coverage, not the end-to-end flow, which is
   milestone 2's.
2. After **2K**: the module-level flow is complete *end to end* — analyze → resolve →
   enrich → render → export, nothing stubbed.
3. After **2J**: the catalog thesis is proven on second frameworks and the
   **version-bump gate opens** (unchanged anchor — the gate is about Java coverage,
   which linking is not part of).

L now comes last, after the gate: linking services into a system-level architecture
starts only once everything module-level for Java is built. Its precondition never
weakens by waiting — 2F's real peers are already in the bundles, and every phase
between here and L only makes the links denser (wire formats make payloads
comparable, 2H/2I add edge kinds, 2J adds frameworks emitting the same tables).

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

**2F** is the phase that unlocks three stuck things at once: outbound peers for a
DECLARED base address (`client_base_addresses_not_resolved` retires into two narrower
gaps — a base built by computation, `computed_base_addresses_not_traced`, and
configuration constructed in code, `config_as_code_not_read`), Spring Cloud Stream's
functional bindings (`config_join` — code names a key, the value lives in
configuration; spring-cloud-aws's own bindings and Spring Integration ride the same
engine once catalogued), and the environment expressions D06 already reserves a
manifest field for, now populated live from `resolved_config`'s own distinct
environments. It is also what makes **L** viable whenever L runs: links drawn without
real peers are sparse, and links drawn with them are dense.

**2G** exists because two contracts in different formats are not comparable until one is
projected into the other — proto3's JSON mapping renames `total_amount` to `totalAmount`,
so a service defined by a `.proto` but exposed over REST carries different field names
than its own schema states (D02 §2c). Declared shapes land in the same `shapes` tables 2A
built; no second schema. It shipped that way, and the projection is **read, not
reimplemented**: `json_name` comes off the descriptor. Two design points moved during the
build, both recorded in the spec: format is stamped by one late pass over the finished
table rather than resolved per match, and a payload the code parses further out than one
delegation hop is **refused and ledgered** rather than followed — `open_questions` is the
hand-off that makes 2K's seat an inbox rather than a re-analysis.

**2I was billed as "catalog work only, by then", and that was wrong** — an honesty edit
made when the phase shipped rather than an excuse written after it. Roughly two-thirds of
the phase is data, which is the half the prediction got right: five catalog files, seven
framework-neutral vocabulary words on three existing engines, and no framework name
anywhere in engine code. The other third is real code in two places the roadmap had not
counted. The **WSDL/XSD branch** is a reader plus an ~800-line interpreter branch over
stdlib XML — the fourth format the one descriptor interpreter understands, and the reason
the module had to split one file per format — because a contract this protocol is defined
by cannot be read by a catalog. And **opt-in library extraction** is a subsystem, not a
setting: a configuration file in the analysed repository, coordinate resolution in the
detector, jar reading and an origin stamp in the extractor, a scan loop and a discardable
fact subtree, and the attribution that carries the reader's assertion into the document and
the bundle. The prediction was made before anyone asked where a generated stub actually
lives.

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
