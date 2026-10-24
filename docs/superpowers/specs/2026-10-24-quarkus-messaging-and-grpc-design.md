# Quarkus messaging and gRPC — design

**Status: DESIGNED 2026-10-24 — three decisions ruled (§1).** Closes the two Quarkus cells of
COVERAGE §2c that are not ✅:
- **Kafka**, `◐ (1 open, 1 not shipped)`: the register item `smallrye-reactive-messaging`;
- **gRPC**, `◐ (1 not shipped)`: Quarkus `io.quarkus.grpc.{GrpcService, GrpcClient}`.

Closing both makes Quarkus the second framework family at ✅. The general rule also moves
Quarkus's AMQP, JMS, Pulsar and SQS rows (§3a).

## 1. The rulings (2026-10-24)

| # | Question | Ruling |
|---|---|---|
| 1 | Which SmallRye connectors are read | **B — every connector with a Protocol member**, as one catalog table (connector name → protocol, destination key, its default). A connector not in the table gives an `unresolved` row naming it (*as built: a `binder_protocol` question, no row — §3c*). Rejected: A (Kafka only, a special case of one framework feature) and C (a new `mqtt` Protocol member, a separate design). |
| 2 | Which channels are boundaries, through which connector | **A — mirror Quarkus's wiring rule.** A channel is a boundary when its connector is configured (`mp.messaging.<dir>.<channel>.connector`), or when it is an ORPHAN and exactly one connector of that direction is on the module's resolved classpath. An in-memory channel (produced and consumed in the module) gives no row. Rejected: B (configured connectors only, which finds 2 of 15 measured modules) and C (every channel, which fabricates brokers). |
| 3 | Quarkus gRPC | **A** — `io.quarkus.grpc.GrpcService` joins `grpc-spring.yml`'s corroboration list (one rule, a third spelling); `io.quarkus.grpc.GrpcClient` gets its own `injected_client` catalog because its naming rule differs (an empty value names the client by the field). **C — a client's configured address as its peer, for net.devh and Quarkus together — is logged as its own item**, not built here. |

## 2. Measured first

`quarkusio/quarkus-quickstarts` @ `81a5844` (Quarkus 3.40.1.1), cloned into `examples/` with the
user's permission on 2026-10-24.

| | count |
|---|---|
| modules using `@Incoming` / `@Outgoing` / `@Channel` | 15 |
| … that configure no `connector=` key (Quarkus attaches it) | 13 |
| … whose connector has a Protocol member (Kafka, AMQP, RabbitMQ, Pulsar, SQS) | 14 (MQTT is the 15th) |

*As built (Task 4): the 14 counted connectors, not modules that derive rows. Measured after the
build (below): **13 modules derive rows**. `mqtt-quickstart` gives two `binder_protocol`
questions naming `smallrye-mqtt`. `context-propagation-quickstart` gives none, and that is
correct: its one channel, `prices`, is an in-memory pair (a `MutinyEmitter` and a `Multi` in
the same module), and Quarkus attaches no connector to one (CP-50 rows 1, 11).*
| destination keys (`topic`, `address`, `queue`, `exchange…`) per module | 0–3; most channels use the channel name |
| `@GrpcService` / `@GrpcClient` uses | 2 / 4 (client `hello`, `quarkus.grpc.clients.hello.{host,port}`) |

Framework rule, read informally from `quarkus-messaging-deployment` 3.17.5's
`WiringProcessor` (to be recorded as probe rows, §3b):
- `detectOrphanChannels` collects incoming and outgoing channel names; an orphan is a name of one
  direction that no channel of the other direction carries, and that no connector manages.
- `autoConfigureConnectorForOrphansAndProduceManagedChannels` attaches the connector to every
  orphan of a direction when exactly ONE connector of that direction is on the classpath, gated
  by a build-time boolean. It does so as a RUNTIME CONFIGURATION DEFAULT.

## 3. What changes

### 3a. The connector table — catalog data

A new `config_join`-shaped catalog, `smallrye-reactive-messaging.yml`, declares:
- **The channel annotations.**
  - `@Incoming(value)` on a method: inbound.
  - `@Outgoing(value)` on a method: outbound.
  - `@Channel(value)` on an injected `Emitter`/`MutinyEmitter`: outbound.
  - `@Channel(value)` on an injected `Multi`/`Publisher`: inbound.
  - The repeatable containers `@Incomings`/`@Outgoings`.

  Each fact comes from the jar, by probe (`microprofile-reactive-messaging-api` 3.0.1 as shaded
  into `smallrye-reactive-messaging-api` 4.25.0).
- **The configuration keys:** `mp.messaging.incoming.<channel>.<attr>` and
  `mp.messaging.outgoing.<channel>.<attr>`.
- **The connector table.** One entry per connector:
  - its name (`smallrye-kafka`, `smallrye-amqp`, `smallrye-rabbitmq`, `smallrye-pulsar`,
    `smallrye-jms`, plus the SQS connector's name as its jar states it);
  - its Protocol (`kafka`, `amqp`, `amqp`, `pulsar`, `jms`, `sqs`);
  - its destination attribute(s) per direction, and the destination's default (the channel
    name, or what the connector's own `@ConnectorAttribute` declares);
  - the classpath coordinate that puts it there (e.g. `io.quarkus:quarkus-messaging-kafka`).

  Every value is backed by a probe row read from that connector's jar
  (`@ConnectorAttribute(name="topic", …)` is itself annotation data on the connector class).
- **The wiring rule** of ruling 2, as data: orphan detection and single-connector attachment,
  with the probe that read it.

Values the repository configures are reported as such, through the one placeholder rule: a
destination written `${…}` resolves per environment like any configured value.

### 3b. Probes

- **CP-49:** the channel annotations, their targets and direction, and the repeatable containers
  (`microprofile-reactive-messaging-api` 3.0.1).
- **CP-50:** Quarkus's orphan and single-connector rule (`quarkus-messaging-deployment`, read on
  3.17.5 and on the quickstarts' 3.40.1.1 if it resolves locally), including the build-time flag's
  config key and default.
- **CP-51:** each connector's name, destination attributes and defaults, from its
  `@ConnectorAttribute` declarations (`smallrye-reactive-messaging-kafka` and the others at
  4.25.0).
- **CP-52:** `io.quarkus.grpc.GrpcService` and `GrpcClient` identities, and `GrpcClient.value()`'s
  default with the field-name rule (`quarkus-grpc` 3.17.5).

Probes read jars from `~/.m2`. The user approved downloading them on 2026-10-24.

### 3c. What a row looks like

```text
protocol  direction  method  path             handler / caller                 resolution
kafka     inbound    —       requests         QuoteProcessor#process(String)   resolved
kafka     outbound   —       quotes           QuoteProcessor#process(String)   resolved
amqp      outbound   —       quote-requests   QuoteResource.emitter (Emitter)  resolved
```

- Two connectors on the classpath and none configured: `unresolved`, the reason naming both.
- A configured connector the table does not know (`smallrye-mqtt`): `unresolved`, naming it.

*As built (Task 2, corrected in its fix round):* "`unresolved`" in the two lines above and in
§1 ruling 1 and §4 is a `binder_protocol` OPEN QUESTION, not an `endpoints` row. The protocol
is the thing nobody read, and a row must carry one, so the channel gets no row and the
question names the connector(s) in its candidates, each with the reason. That is the
`spring-cloud-stream` precedent for an unmapped binder (F2 §3.4). It covers: two or more
connectors in the dependency set; a connector the table does not know; and a connector the
table COUNTS but reads no wire for. MQTT, Camel, in-memory and Google Pub/Sub are counted
entries (CP-51 rows 32-51). The framework's sole-connector test counts them too (CP-50 rows
6, 16), so Kafka beside MQTT is two connectors. A wired channel whose ADDRESS is unread
(spellings that disagree, Kafka `topics`) does keep its row, with `path` NULL, plus a
`channel_destination` question.
- An in-memory channel gives no row.

A message channel's identity is its destination, as for Spring Cloud Stream. The connector is
stated as evidence.

### 3d. gRPC

- `grpc-spring.yml`'s corroboration list gains `io.quarkus.grpc.GrpcService`, with CP-52 cited in
  its `measured:` block. The display name drops "Spring" if the file's own comments say it is
  framework-neutral.
- A new `grpc-quarkus-client.yml`, style `injected_client`, detected by
  `io.quarkus:quarkus-grpc`, with `field_annotation: io.quarkus.grpc.GrpcClient` and the
  field-name default for an empty value. If `injected_client` has no word for that default, it
  gains one, stated as data. Service-level rows only, as `grpc-net-devh.yml`.

### 3e. Fixture

`fixtures/orders-quarkus` (Quarkus 3.17.5) gains, built with JDK 21:
- a processor `@Incoming("requests") @Outgoing("quotes")`;
- an `Emitter` on `@Channel("quote-requests")`;
- an in-memory pair;
- `quarkus-messaging-kafka` on the classpath;
- one channel configured with an explicit `topic`;
- a `@GrpcService` and a `@GrpcClient` (one with an empty value).

## 4. What it does NOT do

- **MQTT, Camel and other connectors without a Protocol member:** an `unresolved` row naming the
  connector — *as built, a `binder_protocol` question naming it and no row (§3c's note)*. A
  Protocol member for MQTT is its own design.
- **The gRPC client's address as its peer** (ruling 3C): logged as its own item, for net.devh and
  Quarkus together.
- **Message payload shapes and serializer formats:** a later rung of the format ladder, as for
  Spring Cloud Stream's first cut.
- **Kafka Streams in Quarkus:** covered by the Kafka Streams family already.

## 5. Cost (§8.7)

- One read of the annotation facts and one of `resolved_config` per resolve.
- The orphan rule is a set difference over the module's own channel names.
- The connector-on-classpath test reads the resolved classpath the Maven detector already
  publishes (OI-167).

## 6. Verify what it closes

- COVERAGE §5.8 SmallRye row → ✅. §5.7 Quarkus gRPC row → ✅. Regenerate §2c and confirm
  Quarkus reads ✅ in Kafka and gRPC. Quote the line.
- The register: `smallrye-reactive-messaging` closes, and the Kafka delivery row is re-checked
  for any library its COVERAGE section still carries uncatalogued.
- Field: the 15 measured quickstart modules are re-measured after building, and their derived
  messaging rows are counted against §2's table.

## As built — measured on quarkus-quickstarts

`quarkusio/quarkus-quickstarts` @ `81a5844` (Quarkus 3.40.1.1). Each module was built with
`JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q -DskipTests package`; all 15 built, and none
needed a newer JDK or a container. Each was then analysed with `sextant module analyze`.
Every row is `resolved`.

| module | rows | questions |
|---|---|---|
| amazon-sqs-connector-quickstart | 4 sqs: in/out `quote-requests`, in/out `quotes` | 2 `self_exchange` |
| amqp-quickstart-processor | 2 amqp: in `quote-requests`, out `quotes` | — |
| amqp-quickstart-producer | 2 amqp: out `quote-requests`, in `quotes` | — |
| context-propagation-quickstart | 0 (in-memory pair `prices`) | — |
| kafka-avro-schema-quickstart | 2 kafka: in/out `movies` | 1 `self_exchange` |
| kafka-panache-quickstart | 2 kafka: in/out `prices` | 1 `self_exchange` |
| kafka-panache-reactive-quickstart | 2 kafka: in/out `prices` | 1 `self_exchange` |
| kafka-quickstart/processor | 2 kafka: in `quote-requests`, out `quotes` | — |
| kafka-quickstart/producer | 2 kafka: out `quote-requests`, in `quotes` | — |
| kafka-streams-quickstart/producer | 2 kafka: out `temperature-values`, `weather-stations` | — |
| mqtt-quickstart | 0 | 2 `binder_protocol` naming `smallrye-mqtt` (`prices`, `topic-price`) |
| pulsar-quickstart-processor | 2 pulsar: in `persistent://public/default/quote-requests`, out `…/quotes` | — |
| pulsar-quickstart-producer | 2 pulsar: out `…/quote-requests`, in `…/quotes` | — |
| rabbitmq-quickstart-processor | 2 amqp: in `quote-requests`, out `quotes` | — |
| rabbitmq-quickstart-producer | 2 amqp: out `quote-requests`, in `quotes` | — |

That is 28 rows in 13 modules. The `self_exchange` questions are the existing serve-and-call
rule (COVERAGE 3a-v), filed for a module that produces and consumes one destination.
`mqtt-quickstart`'s in-memory `my-data-stream` pair gives nothing, as it should.
