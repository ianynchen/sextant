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
| 1 | Which SmallRye connectors are read | **B — every connector with a Protocol member**, as one catalog table (connector name → protocol, destination key, its default). A connector not in the table gives an `unresolved` row naming it. Rejected: A (Kafka only, a special case of one framework feature) and C (a new `mqtt` Protocol member, a separate design). |
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
  connector. A Protocol member for MQTT is its own design.
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
