# Quarkus messaging and gRPC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Quarkus module's SmallRye Reactive Messaging channels become endpoint rows through every connector with a Protocol member, wired as Quarkus wires them; Quarkus's gRPC annotations are read. Quarkus reaches ✅ in COVERAGE §2c.

**Architecture:** Framework facts are measured by four probes (CP-49..52) and stated as catalog data. `smallrye-reactive-messaging.yml` extends `config_join`'s existing channel mode (the one `spring-integration.yml` uses) with a connector table and the orphan/single-connector wiring rule. `grpc-spring.yml` gains a third `@GrpcService` spelling, and a new `grpc-quarkus-client.yml` reads `io.quarkus.grpc.GrpcClient` with its field-name default.

**Tech Stack:** Python 3.13, DuckDB, YAML catalogs, pytest; probes over jars in `~/.m2` with `javap`; Java fixtures built with JDK 21.

**Spec:** `docs/superpowers/specs/2026-10-24-quarkus-messaging-and-grpc-design.md`

## Global Constraints

- Gate: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh` (pre-commit needs `PATH=/Users/yining/programming/ai/sextant/.venv/bin:$PATH`).
- Fixtures are built with JDK 21, never 27.
- Framework knowledge is catalog data with a probe: resolve code names no framework, connector, annotation or config key. Every catalog value cites the probe row that read it (`measured:` / `by:`).
- Probes read the jars' own manifest version first and generate their observation tables. Jars used are: `smallrye-reactive-messaging-{api,provider,kafka}` 4.25.0, `microprofile-reactive-messaging-api` 3.0.1, `quarkus-messaging{,-deployment,-kafka,-kafka-deployment}` 3.17.5 and `quarkus-grpc` 3.17.5, all in `~/.m2` (downloaded with the user's permission). A further jar a probe needs (another connector) may be fetched with `mvn -q dependency:get -Dartifact=… -Dtransitive=false`, under the same permission.
- Mirror the framework (DR-6). A channel is a boundary only as ruling 2 says. An in-memory channel gives no row. An unknown connector, or two unconfigured connectors, gives `unresolved` with a reason, never silence.
- Values the repository configures go through the one placeholder rule (`config.substitute`) and are reported as such.
- No schema or version stamp moves. If a task finds it must add a table, view or vocabulary attribute, it stops and reports.
- Every new rule gets a guard in `scripts/guard_check.py`, measured killed; a re-pinned test is never deleted.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- **The kafka-quickstart processor exactly.** `@Incoming("requests") @Outgoing("quotes")` with only `quarkus-messaging-kafka` on the classpath and no `mp.messaging.*` keys gives `kafka inbound requests` and `kafka outbound quotes`, both resolved.
- **An in-memory pair** (`@Outgoing("x")` and `@Incoming("x")` in one module) gives no row, even with a connector on the classpath.
- **A configured connector overrides attachment.** With `mp.messaging.incoming.requests.connector=smallrye-amqp`, the row is `amqp` even when only Kafka is on the classpath. Report what the probe says the framework does.
- **A `${…}` topic** (`mp.messaging.incoming.requests.topic=${REQ_TOPIC:requests}`) resolves per environment through `substitute`, its default where unset.
- **`@GrpcClient` with an empty value** names the client by the field. Two such fields of the same stub type give two rows only if the framework would make two clients.

---

### Task 1: Probes CP-49..CP-52

**Files:**
- Create: `scripts/probes/cp49_reactive_messaging_annotations/{probe.py,run.sh}` and `.md`; the same trio for `cp50_quarkus_channel_wiring`, `cp51_smallrye_connectors` and `cp52_quarkus_grpc_annotations`. Copy `scripts/probes/cp45_active_profiles/` for layout and conventions.
- Test: none (probes are records). `run.sh` must exit 0, and each `.md`'s observation table must be the verbatim `run.sh` output.

**Interfaces:**
- Produces, as each `.md`'s generated table, the facts Tasks 2–3 cite:
  - **CP-49:** the FQNs of `Incoming`, `Outgoing`, `Channel`, `Emitter`, `MutinyEmitter`, `Incomings`, `Outgoings`; their `@Target`; `@Repeatable` containers; each `value()` member.
  - **CP-50:** orphan detection (incoming names minus outgoing names and vice versa, minus connector-managed); the single-connector condition per direction; the build-time flag's config key and default; that attachment is a runtime configuration default.
  - **CP-51:** for each SmallRye connector jar available, the connector name (`@Connector` value), the protocol it speaks, and every `@ConnectorAttribute` with direction, name and `defaultValue`. Required: Kafka (`smallrye-reactive-messaging-kafka` 4.25.0). Also AMQP, RabbitMQ, Pulsar, JMS and SQS if their jars can be fetched under the permission. Record any you could not fetch as "not measured".
  - **CP-52:** `io.quarkus.grpc.GrpcService` / `GrpcClient` FQNs and targets; `GrpcClient.value()`'s default; where the extension maps an empty value to the field or parameter name (find it in `quarkus-grpc` or its deployment jar, fetching `io.quarkus:quarkus-grpc-deployment:3.17.5` if needed).

- [ ] **Step 1: Write each probe**, reading versions from manifests, observations via `javap -c -constants -v` (annotation data comes from `RuntimeVisibleAnnotations`/`AnnotationDefault`).
- [ ] **Step 2: Run each `run.sh`.** Expected: exit 0 and every row observed, or a row reading `NOT MEASURED` with its reason.
- [ ] **Step 3: Write each `.md`** around the generated table: version scope, why it was measured, and what it does NOT measure.
- [ ] **Step 4: Commit** `probe: CP-49..52 — SmallRye channels, Quarkus wiring, connectors, Quarkus gRPC`.

### Task 2: SmallRye Reactive Messaging — the catalog and the channel wiring

**Files:**
- Create: `src/sextant/catalogs/smallrye-reactive-messaging.yml`
- Modify: `src/sextant/application/resolve/engines/config_join.py` (the channel mode: `_derive_channels`, `_channels`, `_channel_name`) and the catalog loader's validation (`src/sextant/ingress/catalogs/yaml_source.py`) for any new keys
- Modify: `docs/components/D02-catalog-schema.md` (the new catalog words)
- Test: `tests/application/test_config_join.py` (fact-built workspaces, as its existing channel tests build them), `tests/ingress/` (loader refusals)

**Interfaces:**
- Consumes: CP-49/50/51 facts (Task 1); `config.substitute`/`placeholder_rule` for configured destinations; the resolved classpath the Maven detector publishes (find where `detect.coordinates` checks it — `grep -rn "coordinates" src/sextant/application`).
- Produces: inbound/outbound `endpoints` rows with `protocol` from the connector table, `path` = the destination, `resolution` resolved or unresolved with a reason, `evidence` naming the connector and how it was chosen (`configured` / `attached: sole connector on the classpath`).

- [ ] **Step 1: Write failing tests** (one per Review Focus line plus):
  - The processor pair, from the brief's first Review Focus line.
  - An `Emitter` on `@Channel("quote-requests")` → outbound `quote-requests`.
  - A `Multi` on `@Channel("prices")` → inbound.
  - The in-memory pair → no row.
  - A configured `topic` → that topic.
  - A `${…}` topic → resolved per environment.
  - Two connectors on the classpath, none configured → `unresolved`, naming both.
  - A configured unknown connector (`smallrye-mqtt`) → `unresolved`, naming it.
  - A configured `connector=smallrye-amqp` with only Kafka on the classpath → whatever CP-50 says the framework does.
  - The RabbitMQ destination attribute per direction, as CP-51 measured.
  - `@Incomings` container → one row per nested `@Incoming`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write the catalog** with every value cited to its probe row, and extend the channel mode with the catalog words the tests need (a connector table, the orphan rule, the classpath-attachment rule). Each word is stated in D02 and validated by the loader with a refusal test.
- [ ] **Step 4: Run** the new tests, the existing `test_config_join.py` (spring-integration's channel mode must not move) and the full gate. Expected: all pass.
- [ ] **Step 5: Guards:**
  - `messaging.an-ORPHAN-channel-takes-the-sole-connector` (edit: attachment disabled);
  - `messaging.an-IN-MEMORY-channel-is-no-boundary` (edit: orphan check skipped);
  - `messaging.the-CONNECTOR-table-names-the-protocol` (edit: protocol from a fixed value).

  Pin and measure: killed.
- [ ] **Step 6: Commit** `feat(messaging): SmallRye channels become boundaries through every known connector, wired as Quarkus wires them`.

### Task 3: Quarkus gRPC

**Files:**
- Modify: `src/sextant/catalogs/grpc-spring.yml` (corroboration list + `measured:` row citing CP-52; drop "Spring" from `displayName` only if the file's own comments say the catalog is framework-neutral)
- Create: `src/sextant/catalogs/grpc-quarkus-client.yml` (style `injected_client`, `detect.coordinates: ["io.quarkus:quarkus-grpc"]`, `field_annotation: io.quarkus.grpc.GrpcClient`, `identity_marker` as `grpc-net-devh.yml`)
- Modify: the `injected_client` engine and loader only if a name-default word is needed; D02 for that word
- Modify: `docs/open-issues.md` (a new OI for ruling 3C: a gRPC client's configured address as its peer, for net.devh `grpc.client.<name>.address` and Quarkus `quarkus.grpc.clients.<name>.{host,port}` together)
- Test: `tests/application/test_*grpc*.py` (find the net.devh client tests and mirror them)

**Interfaces:**
- Consumes: CP-52 (Task 1).

- [ ] **Step 1: Write failing tests:** a `@GrpcService` class extending a generated `ImplBase` is corroborated as the Spring and net.devh spellings are. A `@GrpcClient("hello")` stub field gives one outbound service-level row, the same shape `grpc-net-devh` produces. A `@GrpcClient` with an empty value derives the same row.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the list entry, the catalog and any engine word.
- [ ] **Step 4: Run** the new tests, the existing gRPC tests and the full gate.
- [ ] **Step 5: Guard** `grpc.a-QUARKUS-client-field-is-an-outbound-service`. Pin and measure: killed.
- [ ] **Step 6: Commit** `feat(grpc): Quarkus's @GrpcService and @GrpcClient are read`.

### Task 4: Fixture, field measurement, record

**Files:**
- Modify: `fixtures/orders-quarkus` (pom: `quarkus-messaging-kafka` and `quarkus-grpc` at the BOM's 3.17.5, with the exclusions the existing dependencies use; the classes and `application.properties` keys of spec §3e). Rebuild with `JAVA_HOME=/opt/homebrew/opt/openjdk@21`.
- Modify: the e2e test that analyses `orders-quarkus` (`grep -rln "orders-quarkus" tests/e2e`); re-pin any count that moves, with a reason line.
- Modify: `docs/COVERAGE.md` (§5.8 SmallRye row → ✅ shipped; §5.7 Quarkus gRPC row → ✅ shipped; regenerate §2c with `scripts/coverage_matrix.py`), `docs/java-kotlin-delivery-list.md` (close `smallrye-reactive-messaging`; re-check the Kafka delivery row for any uncatalogued library its COVERAGE section still carries, and name it as a new register item if so), `CHANGELOG.md` (Unreleased `### Added`), the spec's Status → BUILT.
- Measure: build the 15 measured quickstart modules (spec §2) with `JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q -DskipTests package` under `examples/quarkus-quickstarts/<module>`, analyse each, and count the messaging rows per module against spec §2's table. Record the table in the spec under "As built — measured on quarkus-quickstarts". This downloads those modules' dependencies, under the user's 2026-10-24 permission for the field corpus.

- [ ] **Step 1: Fixture + e2e pins:**
  - `kafka inbound requests` and `kafka outbound quotes` from the processor, and `kafka outbound quote-requests` from the emitter;
  - the configured-topic channel at its topic;
  - no row for the in-memory pair;
  - the Quarkus gRPC client row.
- [ ] **Step 2: Run** the e2e tests. Expected: PASS after the fixture change.
- [ ] **Step 3: Field measurement** on the quickstarts. Expected per spec §2: rows for 14 modules, and an `unresolved` naming `smallrye-mqtt` for the 15th. Report any difference verbatim. Do not change the code to match a guess.
- [ ] **Step 4: Record** COVERAGE, the regenerated §2c Quarkus line (quote it in the report), the delivery list, the CHANGELOG and the spec status.
- [ ] **Step 5: Run** the full gate, `scripts/field_check.py` (six `ok`) and the full guard sweep (`0 survived`).
- [ ] **Step 6: Commit** `feat(quarkus): orders-quarkus carries messaging and gRPC; Quarkus Kafka and gRPC ✅`.
