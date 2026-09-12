# Java/Kotlin — what is not delivered, and how to close it

**Target:** an accurate architecture document for a **Java/Kotlin module** — every
framework, not one. Micronaut, Quarkus, Ktor, Javalin, Vert.x, Alpakka and Temporal are
**in scope and sequenced after Spring Boot**, which is the first framework rather than the
definition of done. *(Corrected 2026-09-11: an earlier version of this document called them
out of scope, which under-counted the work by about eleven libraries.)*

**Spring Boot end-to-end is the first MILESTONE.** It gates the version bump. It does not
close a feature.

**Delivered means:** every Java/Kotlin library catalogued, **no open Critical or Major**,
and no unsettled boundary in the feature's own `docs/COVERAGE.md` section. A feature with an
open Major is not delivered.

**Two axes, and they are different questions.** *Spring Boot ready* — the milestone — and
*delivered* — every Java/Kotlin framework. A feature can be the first without being the
second, and the blocker lists below mark which is which.

Every row was verified against the code and the framework jars on 2026-09-11. Where a row
says a count, the command that produces it is in the `verify` line.

---

## 0. The machine-readable register

**This block is the source of truth and `tests/architecture/test_feature_delivery.py`
enforces it.** One line per feature: the COVERAGE column it maps to, then every open issue
blocking it. A feature with no blockers must read `✅` in `docs/COVERAGE.md`'s matrices, and
a feature with blockers must not. Both directions fail the suite.

Adding a Critical or Major anywhere without naming the feature it blocks fails the suite
too — that is the check aimed at half-delivery: the half you did not do has to appear here,
against the feature it belongs to, or the build goes red.

```delivery
REST inbound       | REST in    | G-37 G-30 W44-verb-overloads GAP-1b conditional-controllers kotlin-null-handler quarkus-jaxrs ktor-routing javalin-routing javalin-apibuilder
REST outbound      | REST out   | G-30-outbound jdk-httpclient
SOAP               | SOAP       | jaxws-public-final jaxws-inherited-unannotated
GraphQL            | GraphQL    |
WebSocket          | WebSocket  |
SSE                | SSE        | jaxrs-sse
gRPC               | gRPC       |
Kafka              | Kafka      | G-31 kafka-batch-generics alpakka-pekko
JMS and AMQP       | JMS / AMQP | G-44
AWS SQS            | SQS        | micronaut-sqs sqs-template-receive micronaut-jms-over-sqs
Google Pub/Sub     | Pub/Sub    | pubsub-channel-adapter
Meridian           | —          | FR-21 FR-22 FR-23 FR-24
Async              | Async      | temporal-cadence vertx-eventbus
```

**Delivered in Java/Kotlin, matrix cell stays `◐`** — because §2 scores every language and
the only remaining gaps are in languages this target does not cover. gRPC's are Go, Python,
Rust and Swift; there is no Java gap left in it.

**SSE is NOT here any more.** Its gap is JAX-RS `@Produces(SERVER_SENT_EVENTS)`, which is
Java — so it is real work, sequenced after Spring Boot, not something scoped away.

```scoped-out
gRPC
```

**Not blocking any feature** — tracked so "no open Critical or Major" can be claimed
honestly at the end, and excluded from the per-feature check by being named here:

```unassigned
OI-85
```

**Out of scope for this target** — neither blocking nor tracked for delivery:

```out-of-scope
GAP-2 G-10 G-71
```

**Intention test not yet written** — every feature needs one (`GUIDELINES.md` §4.1), and
these do not have one. Named here so the suite can be GREEN while the gap stays visible:
the check expects each of these to fail, and **fails if one unexpectedly passes**, which is
what forces this list to shrink rather than rot. A feature missing from both this block and
`tests/e2e/` is a hard failure.

```intention-test-missing
SSE | gRPC
Google Pub/Sub | Meridian
```

**Severity, carried here** so this register stands on its own. Folded from
`docs/java-gap-analysis-2026-09-06.md` on 2026-09-11 when that file was removed; it was
the input audit of 2026-09-06, and every one of its rows is now either placed above or
recorded as closed below.

```severity
G-1 | Critical
G-2 | Critical
G-3 | Critical
G-4 | Critical
G-5 | Critical
G-6 | Critical
G-7 | Critical
G-8 | Critical
G-9 | Critical
G-10 | Critical
G-11 | Critical
G-12 | Critical
G-13 | Critical
G-14 | Critical
G-15 | Major
G-16 | Major
G-17 | Major
G-18 | Major
G-19 | Major
G-20 | Major
G-21 | Major
G-22 | Major
G-23 | Major
G-24 | Major
G-25 | Major
G-26 | Major
G-27 | Major
G-28 | Major
G-29 | Major
G-30 | Major
G-31 | Major
G-32 | Major
G-33 | Major
G-34 | Major
G-35 | Major
G-36 | Major
G-37 | Major
G-38 | Major
G-39 | Major
G-40 | Major
G-41 | Major
G-42 | Major
G-43 | Major
G-44 | Major
G-45 | Major
G-46 | Major
G-47 | Major
G-48 | Major
G-49 | Major
G-50 | Major
G-51 | Major
G-52 | Major
G-53 | Major
G-54 | Major
G-55 | Major
G-56 | Major
G-57 | Major
G-58 | Major
G-59 | Major
G-60 | Major
G-61 | Major
G-62 | Major
G-63 | Major
G-64 | Major
G-65 | Major
G-66 | Major
G-67 | Major
G-68 | Major
G-69 | Major
G-70 | Major
G-71 | Major
G-73 | Moderate
G-74 | Moderate
```

**Closed by the waves, verified by reading the code on 2026-09-11 — a WEAKER
guarantee than the `closed` block above.** These have no test that fails if they
regress; they were checked once, against the shipped catalogs and engines, in the audit
of all 53 Criticals and Majors that the completeness plan never named by number. Any of
them reopening would be silent. Listed rather than deleted so that is visible.

```closed-by-audit
G-1 G-2 G-3 G-4 G-5 G-6 G-7 G-8 G-9 G-11 G-12 G-13 G-14 G-15 G-16 G-17 G-18
G-19 G-20 G-21 G-22 G-23 G-24 G-25 G-26 G-27 G-28 G-29 G-32 G-33 G-35 G-38
G-41 G-42 G-46 G-48 G-49 G-50 G-51 G-53 G-54 G-55 G-56 G-57 G-58 G-59 G-60
G-61 G-62 G-63 G-64 G-65 G-66 G-67 G-68 G-69 G-70
```

**Retired as not-gaps, 2026-09-11 — measured, not fixed.** Two items on the direct list
turned out to be nothing to build, found by reading what was already written down:

- `pubsub-receive-half` — the probe's own conclusion, already in
  `scripts/probes/w19_catalog_surface.md:177`: *"no unread method addresses a wire by
  either style."* W18 read all ten inbound methods; the nine unread are `ack`, `nack`,
  `modifyAckDeadline` and accessors. The "11 of 20" ratio put it on this list; the line
  beneath the ratio should have kept it off.
- `spring7-import-http-services` — measured: an `@HttpExchange` interface registered
  through `@ImportHttpServices` derived its outbound row before any catalog read the
  registration, because `spring-http-interface.yml` reads the interface itself
  (`declared_on: interface`). "Registration unread" implied missing rows; there were none.
  Pinned by `tests/e2e/test_rest_outbound_delivered.py`.
- `async-limited` — `@Scheduled(cron = "${…}")` publishes the placeholder as `unresolved`
  verbatim, and COVERAGE §5.12 says why: the value comes from configuration a deployment
  overwrites, so substituting it would be a guess (`GUIDELINES` §8.2). That is the correct
  output. The matrix counts it as `limited` because the generator counts any `◐ shipped`
  row; a boundary that is correct by design is not a blocker.

**Retired as not-gaps, 2026-09-12 — measured, not fixed.**

- `apache-cxf` — measured (w63, `scripts/probes/w63_cxf_web_method_rule.md`): CXF's
  `JaxWsServiceConfiguration.isWebMethod` excludes `static`/`final` the same pair
  `RuntimeModeler.isWebMethodBySpec` invokes, honours `@WebMethod(exclude = true)`
  identically, and reads `@WebService` off a method's own declaring class the same way
  the RI's `isWebMethodBySpec` does (both bytecode-read AND live-run confirmed, over the
  identical `BillingWebService`/`AbstractBilling` fixture). "Version-scoped, not settled"
  implied a live divergence; there is none. `jakarta-jws.yml`'s `measured:` block now
  carries both implementations.

**Moved to engine work, 2026-09-11 — measured off the direct list:** `quarkus-jaxrs`,
`jaxrs-sse` (attributes on sibling annotations of one method) and `kafka-batch-generics`
(a wrapper conditional on an annotation attribute; `wrappers` are unconditional and
global by type). Each keeps its fixture and a strict-xfail test where one was written.

**Moved to spec work, 2026-09-12 — measured off the direct list:** `temporal-cadence`.
`javap` on temporal-sdk 1.27.0: `@WorkflowMethod(name)` defaults to the *interface's*
simple name and `@ActivityInterface(namePrefix)` + `@ActivityMethod(name)` defaults to
prefix + the method name with its first letter capitalised — two naming rules the
`path_fallback` vocabulary (`construct_name`, the accessor properties) cannot say. The
task queue, which is the half of the wire identity a client actually addresses, is on
`WorkerFactory.newWorker(String)` and `WorkflowOptions.Builder.setTaskQueue`, not on any
annotation. And no member of the closed `Protocol` set fits a workflow engine; adding one
is a schema decision with its own precedent (`RSOCKET`, stated in `closed_sets.py`). Three
engine words and a schema member is a spec, not a catalog.

**Also moved to spec work, 2026-09-12 — measured off the direct list:**
`sqs-template-receive`, the SQS quarter of `G-44`, carried on the SQS row above under its
own name so `G-44` can close on its three delivered quarters without losing the fourth.
`SqsTemplate.receive` / `receiveMany` / `receiveAsync` / `receiveManyAsync`
(spring-cloud-aws-sqs 3.1.1, `scripts/probes/w59_template_receive_halves.md`) all take
`Consumer<SqsReceiveOptions>` at argument 0, and the queue is named inside that lambda —
`opts.queue("orders")` — not at any argument `single_call` can read. That is the
receiver-chain form, Category B of the register (§4), the same overload-discrimination
work `G-37`/`G-30`/`GAP-1b` wait on — not a fixture-and-test item like the other three
quarters. `RabbitTemplate`, `JmsTemplate` and `KafkaTemplate`'s receive halves already
derive (Tasks 1-3, commits `371cfaf`, `760c884`, `7771be7`).

**Also named 2026-09-12, alongside `javalin-routing` shipping:**
`javalin-apibuilder`. `config.router.apiBuilder(() -> path("/orders", () ->
get("/{id}", h)))` calls the static `ApiBuilder.get` inside a lambda inside
`path(…)`'s own lambda — measured (w61, `scripts/probes/
w61_javalin_surface.md`): `ApiBuilder.get`'s descriptor carries a route
`String` at argument 0, the identical shape and position `javalin.yml`'s flat
`Javalin.get` reads, so a `single_call` row on `ApiBuilder.get` alone would
publish `/{id}` with no `/orders` prefix — a wrong row, not a missing one
(`javalin.yml`'s own `test_javalin_flat_registrations_derive_every_route`
pins the negative). Composing the prefix needs the same receiver-chain walk
`G-37`/`GAP-1b`/`G-30` wait on — Category B, not a catalog fix.

**Named 2026-09-12 when the Pub/Sub cell's last blocker closed:** `pubsub-channel-adapter` —
`PubSubInboundChannelAdapter` + `@ServiceActivator`, the one Java row COVERAGE §5.11 still
tiers `B`. It is the Pub/Sub instance of §5.12's "the DESTINATION behind a channel" boundary:
the subscription name is a constructor argument of the adapter, and `config_join` reads
configuration files, never call-site arguments. Same engine form as the AMQP and Kafka
adapters — one spec for the three, not a catalog.

**Closed** — a blocker leaves this register only when its intention test has passed **in
the CI pipeline**, and the entry records the run that proves it. Ruled by the user
2026-09-11: *"definition of done is when all tests pass in ci pipeline"*.

Implemented-and-locally-green is NOT closed. `G-36` was moved here on a local pass and moved
back the same hour, which is exactly the drift this format exists to stop: the entry cannot
be written without a run id, so there is nothing to write until CI has actually said so.

Format: `id | test node id | CI run URL`

```closed
G-36 | tests/e2e/test_soap_delivered.py::test_one_handler_serving_two_message_types_derives_both | https://github.com/ianynchen/sextant/actions/runs/34646355110
G-39 | tests/e2e/test_graphql_delivered.py::test_one_resolver_serving_two_fields_derives_both | https://github.com/ianynchen/sextant/actions/runs/34669970510
G-40 | tests/e2e/test_graphql_delivered.py::test_a_federation_entity_fetcher_is_visible | https://github.com/ianynchen/sextant/actions/runs/34669970510
G-34 | tests/e2e/test_websocket_delivered.py::test_a_programmatically_registered_endpoint_is_visible | https://github.com/ianynchen/sextant/actions/runs/34669970510
G-43 | tests/e2e/test_aws_sqs_delivered.py::test_a_send_through_the_async_client_is_visible | https://github.com/ianynchen/sextant/actions/runs/34669970510
G-47 | tests/e2e/test_async_delivered.py::test_every_channel_bearing_annotation_derives_its_channel | https://github.com/ianynchen/sextant/actions/runs/34669970510
G-45 | tests/e2e/test_rest_inbound_delivered.py::test_a_data_rest_resource_over_mongodb_derives_its_route_table | https://github.com/ianynchen/sextant/actions/runs/34669970510
spring7-version | tests/e2e/test_rest_inbound_delivered.py::test_two_versions_of_one_route_are_not_reported_as_a_conflict | https://github.com/ianynchen/sextant/actions/runs/34669970510
micronaut-controller | tests/e2e/test_rest_inbound_delivered.py::test_a_micronaut_controller_derives_every_operation | https://github.com/ianynchen/sextant/actions/runs/34669970510
micronaut-client | tests/e2e/test_rest_inbound_delivered.py::test_a_micronaut_declarative_client_derives_outbound | https://github.com/ianynchen/sextant/actions/runs/34669970510
quarkus-vertx-route | tests/e2e/test_rest_inbound_delivered.py::test_quarkus_reactive_routes_derive_every_route | https://github.com/ianynchen/sextant/actions/runs/34669970510
micronaut-kafka | tests/e2e/test_messaging_micronaut_delivered.py::test_micronaut_kafka_both_directions | https://github.com/ianynchen/sextant/actions/runs/34669970510
micronaut-jms | tests/e2e/test_messaging_micronaut_delivered.py::test_micronaut_jms_both_directions | https://github.com/ianynchen/sextant/actions/runs/34669970510
micronaut-pubsub | tests/e2e/test_messaging_micronaut_delivered.py::test_micronaut_pubsub_both_directions | https://github.com/ianynchen/sextant/actions/runs/34669970510
```

---

## 1. The list, by feature

One row per blocker the ```delivery block above still carries, in that block's order. A
closed item keeps a row only where its closing has to be read beside its neighbours, and
every such row says `**closed**` with the CI run that proved it. Seven blockers below
(`javalin-routing`, `jaxws-public-final`, `jaxws-inherited-unannotated`, `G-31`,
`alpakka-pekko`, `micronaut-sqs`, `G-44`) are implemented and pinned by a test that is green
locally; they stay on the register until that test has passed in CI, because that is the
definition of done (§0, "Closed").

### REST inbound — NOT DELIVERED (largest)

| # | issue | what it costs |
|---|---|---|
| `G-37` | `RouterFunctions$Builder` unread, **0 of 20 methods, both stacks** | a module routing this way exports **no HTTP at all** |
| `G-30` | **Spring Cloud Gateway — no catalog exists at all**; Category B, because `RouteLocatorBuilder$Builder.route` has two overloads with the lambda at different positions | the commonest edge component in a Spring estate, inbound and outbound |
| `W44-verb-overloads` | W44's seven `RouterFunctionDsl` verb rules are correct for **1 of 5** overloads | publishes a lambda or a predicate **as a URL** — a wrong row, not a missing one |
| `GAP-1b` | WebFlux non-coroutine `router { }` derives nothing | whole Kotlin router silent |
| `conditional-controllers` | `@ConditionalOnProperty` / `@Profile` controllers | tier C — no mechanism in the code |
| `kotlin-null-handler` | Kotlin routes carry a **NULL handler**, all 3 of them; no Kotlin symbol reaches `roots` or `reachability` | Java functional routes name theirs |
| `quarkus-jaxrs` | JAX-RS `@Path` + `@GET` + `@Produces` are sibling annotations on ONE method, and `annotation_driven` reads one annotation's attributes; engine work (§4's opening note) | every Quarkus, Helidon, Jersey and RESTEasy resource derives nothing — deliberately, since a catalog of the existing forms would put every GET onto the class `@Path` |
| `ktor-routing` | `RoutingBuilderKt.get(Route, String, Function2)` — the prefix a surrounding `route("/api") { … }` adds is visible only by walking from the inner call's receiver to the outer call's lambda; Category B | a `single_call` row would publish `/x` alone, a wrong row |
| `javalin-routing` | **shipped** (`javalin.yml`, w61, `5e3e887` and `abba4db`): both flat forms derive, pinned by `tests/e2e/test_rest_inbound_delivered.py::test_javalin_flat_registrations_derive_every_route`. Still on the register because that test has not yet passed in CI | — |
| `javalin-apibuilder` | the nested `ApiBuilder` form — `get("/{id}", h)` inside `path("/orders", …)`'s lambda; Category B (§4) | a flat read would publish `/{id}` without its prefix, a wrong row |
| `G-45` | **closed** — a Data REST resource over MongoDB derives its route table since `6f088be`, proven in CI run 34669970510. The R2DBC, Cassandra, Elasticsearch, Neo4j and reactive contracts still outside are `GAP-6` | — |
| `spring7-version` | **closed** — two versions of one route are not reported as a conflict, proven in CI run 34669970510 | — |

> `verify: grep -rl "RouteLocator" src/sextant/catalogs/` → empty
> `verify: awk '/repositories:/,/routes:/' src/sextant/catalogs/spring-data-rest.yml | grep -c Mongo` → 4

### REST outbound — NOT DELIVERED

| # | issue |
|---|---|
| `G-30-outbound` | Spring Cloud Gateway outbound half — no catalog; the same Category B read as its inbound half |
| `jdk-httpclient` | JDK `HttpClient`, Apache HttpClient, `URL.openConnection()` — tier B, a builder chain; Category C until the combinator spec says whether it falls out of Category B's mechanism |

### SOAP — NOT DELIVERED (`◐ (2 open)`)

| # | issue |
|---|---|
| `G-36` | **closed** — `spring-ws.yml` declares `container:` for `@PayloadRoot` and `@SoapAction`, both `@Repeatable`, proven in CI run 34646355110 |
| `jaxws-public-final` | **shipped** (Task 9, `c6539f0`): a `public final` method on a `@WebService` is not an operation — `isWebMethodBySpec` excludes `final` beside `static`, and `derive_endpoints.sql`'s member rule now does too. Pinned by `tests/e2e/test_soap_delivered.py::test_a_public_final_method_is_not_an_operation`. Still on the register because that test has not yet passed in CI |
| `jaxws-inherited-unannotated` | both runtimes measured, w63; Sextant over-reported: `gate_ancestry` derived an operation inherited from a plain, unannotated superclass that NEITHER jaxws-rt nor Apache CXF would ever serve. **Fixed in Task 10b, awaiting CI** — `derive_endpoints.sql`'s member rule now requires the DECLARING class to carry `@WebService`; pinned by `tests/e2e/test_soap_delivered.py::test_an_operation_inherited_from_an_unannotated_superclass_is_not_published` |

> `verify: javap -v -cp $(find ~/.m2 -name 'spring-ws-core-*.jar'|grep -v sources|head -1) org.springframework.ws.server.endpoint.annotation.PayloadRoot | grep Repeatable`
> `verify: grep -c container src/sextant/catalogs/spring-ws.yml` → 5

### GraphQL — DELIVERED

`G-39` (the `@DgsData` container) and `G-40` (`@DgsEntityFetcher`) both closed on CI run
34669970510; the cell reads `✅`. The superclass-method fetcher DGS registers and we do not
see is `OI-67`, a stated boundary rather than a blocker.

### WebSocket — DELIVERED

`G-34` (programmatic `ServerEndpointConfig.Builder.create(Class, "/path")`) closed on CI
run 34669970510; the cell reads `✅`.

### SSE — NOT DELIVERED

| # | issue |
|---|---|
| `jaxrs-sse` | JAX-RS `@Produces(SERVER_SENT_EVENTS)` — an attribute on a sibling annotation of the verb's method, the same engine form as `quarkus-jaxrs` (§0, "Moved to engine work") |

### Kafka — NOT DELIVERED

| # | issue |
|---|---|
| `G-31` | **Kafka Streams — three catalogs ship** (`kafka-streams.yml`, `kafka-streams-sink.yml`, `kafka-streams-topology.yml`, w60, split by owner per D02 §3.1): DSL sources/sinks, Processor API sink, and the `addSource` varargs topics all derive; `to(TopicNameExtractor)` and `through` are stated outside. Stays open here only because closing needs a CI run URL (register discipline), not because work remains |
| `kafka-batch-generics` | batch listener generics: `@KafkaListener(batch = true)` takes `List<Foo>`; the payload publishes as the list, not the element. Engine work (§0, "Moved to engine work") — a wrapper conditional on an annotation attribute |
| `alpakka-pekko` | **shipped** (`15deca9`, w62): Pekko Connectors consumer sources derive one inbound row per subscribed topic, pinned by `tests/e2e/test_kafka_delivered.py::test_pekko_consumer_sources_derive_one_inbound_row_per_subscribed_topic`. Still on the register because that test has not yet passed in CI |

### JMS / AMQP — NOT DELIVERED

| # | issue |
|---|---|
| `G-44` | three of four quarters derive (Tasks 1–3, commits `371cfaf`, `760c884`, `7771be7`): `RabbitTemplate`'s nine queue-naming overloads, `JmsTemplate`'s four, `KafkaTemplate`'s one. The SQS quarter is `sqs-template-receive` on the SQS row — `SqsTemplate.receive*` buries the queue inside `Consumer<SqsReceiveOptions>`, Category B (§4). `G-44` closes when the three delivered quarters' tests have passed in CI |

### AWS SQS — NOT DELIVERED

| # | issue |
|---|---|
| `G-43` | **closed** — `SqsAsyncClient.sendMessage` derives since `6f088be`, proven in CI run 34669970510. The 27 other methods on the async client, `receiveMessage` among them, are `GAP-3` |
| `micronaut-sqs` | **shipped** (`b4bbfa4`): a Micronaut module's raw `SqsClient` derives through `aws-sqs-sdk.yml`, pinned by `tests/e2e/test_aws_sqs_delivered.py::test_a_micronaut_module_using_the_raw_sqs_sdk_derives_its_queues`. Still on the register because that test has not yet passed in CI |
| `sqs-template-receive` | the SQS quarter of `G-44`: `SqsTemplate.receive` / `receiveMany` / `receiveAsync` / `receiveManyAsync` name the queue inside a `Consumer<SqsReceiveOptions>` lambda, not at any argument `single_call` reads; Category B (§4) |
| `micronaut-jms-over-sqs` | `@JMSListener(connectionFactory = "sqsJmsConnectionFactory")` derives through `micronaut-jms.yml` with protocol `jms` though the wire is SQS, so a Spring SQS sender and this listener will not link; Category C (§4) |

### Google Pub/Sub — NOT DELIVERED

| # | issue |
|---|---|
| `pubsub-channel-adapter` | `PubSubInboundChannelAdapter` + `@ServiceActivator` — the subscription name is a constructor argument of the adapter, and `config_join` reads configuration files, never call-site arguments. The one Java row COVERAGE §5.11 still tiers `B`; one spec with the AMQP and Kafka adapters (§0, "Named 2026-09-12") |

### Async and internal boundaries — NOT DELIVERED

| # | issue |
|---|---|
| `G-47` | Spring Integration read **2 of 11** channel-declaring annotations; **closed** — five more (`@Aggregator`, `@Filter`, `@Router`, `@Splitter`, `@Transformer`) derive since `6f088be`, 7 of 11 now, proven in CI run 34669970510; `@BridgeFrom`/`@BridgeTo` carry their channel in a bare `value()` and stay a stated boundary (COVERAGE §5.12) |
| `temporal-cadence` | spec work (§0, "Moved to spec work"): two naming rules the `path_fallback` vocabulary cannot say, a task queue named on `WorkerFactory.newWorker` rather than any annotation, and no `Protocol` member for a workflow engine |
| `vertx-eventbus` | `EventBus.consumer(String, Handler)` / `send`, `publish`, `request(String, Object[, DeliveryOptions])` are `single_call` shapes exactly, but an event-bus address is none of the closed `Protocol` set's members; the same schema decision as `temporal-cadence`, Category C |

### Meridian integration — NOT DELIVERED, and asked for four times

**Not a protocol, so it has no COVERAGE column** — the register's `—` says so. It is here
because it is four committed requirements with no implementation, and because leaving it off
this list is how it went unbuilt for a week.

| # | requirement | state |
|---|---|---|
| `FR-21` | Boundary vocabulary — a closed, versioned set of kinds over the derived tables, so two analyses compare kind by kind rather than row by row | **unimplemented.** Its stated blocker is gone: the `dependency` kind derives from edges and dispatch, which did not exist when it was written and do now (F8) |
| `FR-22` | Derivation diff — two analyses of one module, typed `added｜removed｜changed` per kind with evidence pointers | **unimplemented.** This is what the drift scenario waits on |
| `FR-23` | Observability map — per boundary kind, `observable｜partial｜not-observable` | **unimplemented.** Every input already ships: `manifest.json` carries gaps and skipped catalogs, `coverage` carries uncovered files. An assembly, not a measurement |
| `FR-24` | Library embedding — analyze, query, export, diff callable in-process | **partial.** `analyze` and `export` ship; `query` and `diff` are absent, and there is no configuration object |

**Why it is on this list now.** The user asked for it at least four times — *"wrap this in
2P"*, *"check ... if not, add it to a roadmap item and have it covered"*, *"i want you to
implement @docs/meridian-integration.md"*, *"this is a real FR ... Add this to your FR"*. Each
time it was documented further and never built: FR-21–24 were written into `REQUIREMENTS.md`
with traceability rows, scoped to a phase 2P that never ran. *"It is on the roadmap"* was the
answer that made it disappear four times. It is on a list that a test enforces now.

**Closes by** M09's query surface (FR-21, FR-22), an assembly over the manifest (FR-23), and
two functions plus a config object on `sextant.api` (FR-24).

### DELIVERED in this scope

**gRPC**, **GraphQL** and **WebSocket.** GraphQL and WebSocket closed their last blockers on
CI run 34669970510 and read `✅`. gRPC's every remaining gap is another language (Go, Python,
Rust, Swift), so its cell reads `◐` correctly and forever — the ```scoped-out block says so.

---

## 2. Open Criticals and Majors that block no single feature

These are real and they are not on the path to any cell above. They are listed so that
"no open Critical or Major" can be claimed honestly at the end, not so they are done first.

`GAP-7` left this register on 2026-09-12: it is a performance cost (a reactor module
analyses in 111s, 8s alone — `OI-68` has the profile), not a missing feature, and the user
ruled that a slow correct answer is not a gap. It stays open as a performance issue there.
`G-52` throw exits left this list on 2026-09-12: it blocked no feature, so it is not in
the `closed` block above; it is recorded closed in `open-issues.md`, by the tests named there.
`G-74` `signature.throws` gains its consumer left this list on 2026-09-12: it blocked no
feature, so it is not in the `closed` block above; it is recorded closed in
`open-issues.md`, by the tests named there.
`G-73` `visibility` two-valued for a four-valued concept left this list on 2026-09-12: it
blocked no feature, so it is not in the `closed` block above; it is recorded closed in
`open-issues.md`, by the tests named there.

## 3. Out of scope for this target

`GAP-2` the linking tier (FR-8, M05, M06 — phase L, never started) · `G-10` FR-11 to
FR-14 unbuilt · `G-71` blast radius has no surface at all.

---

## 4. Categories, and what each needs

**Measured off the direct list, 2026-09-11.** Three items COVERAGE tiered as `A` (a
catalog file) turned out to need an engine form that does not exist, found by writing
the fixture and watching what the existing vocabulary derives:

- `G-30` Spring Cloud Gateway — two `route` overloads with the lambda at different
  positions on a receiver chain. Needs the combinator overload discriminator (spec written).
- **JAX-RS (Quarkus, Helidon, Jersey, RESTEasy) and JAX-RS SSE** — the verb is a marker
  annotation, the path a separate `@Path`, the media separate `@Consumes`/`@Produces`,
  all on ONE method. `annotation_driven` reads one annotation's attributes; it has no way
  to read a sibling's. A catalog of the existing forms derives every GET onto the class
  `@Path`, which is a wrong row, not a missing one. Fixture and tests exist and are
  strict-xfail in `tests/e2e/test_rest_inbound_delivered.py`.

### Category A — catalog data, no engine change · **NOTHING OPEN**

Every item this category held on 2026-09-11 has shipped: `G-36`, `G-39`, `G-40`, `G-34`,
`G-43`, `G-45` and `G-47` are in the ```closed block with their runs; Spring 7 `version=`
closed as `spring7-version`; Spring 7 `ImportHttpServices` and the Pub/Sub receive half
were measured to be nothing to build (§0, "Retired as not-gaps"); batch-listener generics
moved to engine work. `G-44` was four items wearing one number, and three of the four —
`RabbitTemplate`, `JmsTemplate`, `KafkaTemplate` — are delivered (Tasks 1–3), each with its
own fixture, because a `receive()` with no payload capture is a boundary with no readable
contract; the fourth is `sqs-template-receive` in Category B.

What remains on the register is either implemented and waiting on a CI run
(`javalin-routing`, `jaxws-public-final`, `jaxws-inherited-unannotated`, `G-31`,
`alpakka-pekko`, `micronaut-sqs`) or needs engine or spec work, below.

### Category B — needs the overload discriminator first · **SPEC EXISTS, THEN PLAN**

`G-37` builder routing (both stacks) · `GAP-1b` WebFlux `router { }` · W44's wrong verb
rules · `G-30` Spring Cloud Gateway (and `G-30-outbound`) · `javalin-apibuilder` nested
`ApiBuilder` · `ktor-routing` · `sqs-template-receive` (`SqsTemplate.receive*`)

All of these need the same two things: telling same-name overloads apart, and walking a
receiver chain. The spec is written and committed
(`docs/superpowers/specs/2026-09-11-combinator-overload-discrimination-design.md`) and is
**awaiting your review**. `G-30` was measured into this group at the same time as
`javalin-apibuilder` and `sqs-template-receive` — `RouteLocatorBuilder$Builder.route`
has two overloads with the lambda at different positions, so writing it as catalog
data first would publish a lambda as a path.

**These are one plan, not seven.** The first four plus `javalin-apibuilder` and
`ktor-routing` are REST inbound's receiver-chain work (its other open items,
`quarkus-jaxrs` and the two Category C ones, are different mechanisms);
`sqs-template-receive` is the same read one column over — a
static or instance verb call named inside a lambda passed to an outer call
(`ApiBuilder.get` inside `path(…)`; `RoutingBuilderKt.get` inside `route(…)`;
`opts.queue(...)` inside `SqsTemplate.receive(Consumer<SqsReceiveOptions>)`) — so one
spec closes all of them, not only the REST-inbound four. `pubsub-channel-adapter` (§0,
"Named 2026-09-12") is a DIFFERENT engine form — a `config_join` extension to read a
constructor argument, not a receiver-chain walk — and stays out of this list for that
reason.

### Category C — needs a spec of its own · **SPEC THEN PLAN**

- **Kotlin routes with a NULL handler** (`kotlin-null-handler`). A resolve-layer question
  about what counts as a handler and a root when the handler is a compiler-generated
  lambda class. Short spec.
- **JDK / Apache `HttpClient`** (`jdk-httpclient`, REST outbound, tier B). A builder
  chain; may fall out of Category B's mechanism, which the spec should establish before
  assuming it.
- **`@ConditionalOnProperty` / `@Profile` controllers** (`conditional-controllers`, tier
  C). No mechanism exists; a route's existence becomes conditional on configuration.
  Largest design question here.
- **`micronaut-jms-over-sqs`.** `@JMSListener(connectionFactory = "sqsJmsConnectionFactory")`
  derives through `micronaut-jms.yml` with protocol `jms` even though the wire is SQS, and
  choosing the protocol from the connection-factory attribute is a per-attribute switch no
  engine word has (§5.10's DR-5 boundary note).
- **`temporal-cadence` and `vertx-eventbus`.** Both need a `Protocol` member that does
  not exist — a schema decision with its own precedent (`RSOCKET`, stated in
  `closed_sets.py`) — and Temporal needs two naming rules besides (§0, "Moved to spec
  work").

### Category D — measure first, then decide · **NOTHING OPEN**

Both items this category held were measured. SOAP `public final` over-reporting was real
and shipped as `jaxws-public-final` (Task 9, `c6539f0`); Apache CXF's operation rule was
measured identical to the RI's and retired as a not-gap (`apache-cxf`, §0).

### Category E — the honesty fix · **DONE**

`✅` in `COVERAGE.md`'s matrices used to mean *"every library catalogued"* and nothing
about open defects, which is how SOAP, GraphQL and WebSocket read `✅` on 2026-09-11 while
each carried an open Major. `scripts/coverage_matrix.py` now reads the ```delivery block
and writes `◐ (N open)` for a cell whose feature has blockers, and
`tests/architecture/test_feature_delivery.py` fails in both directions — a blocked feature
reading `✅`, or an unblocked one not reading it. A cell reads `✅` only when the feature is
delivered by the definition at the top of this document.

---

## 5. Where that leaves the matrix

1. **Moved to `✅`**: GraphQL and WebSocket, when their last blockers passed in CI run
   34669970510. SOAP did not — `G-36` closed on run 34646355110, but `jaxws-public-final`
   and `jaxws-inherited-unannotated` were found and fixed afterwards, and it reads
   `◐ (2 open)` until their tests pass in CI.
2. **`◐` waiting only on a CI run** — implemented, pinned, green locally: SOAP (the two
   above), Kafka's `G-31` and `alpakka-pekko`, SQS's `micronaut-sqs`, REST inbound's
   `javalin-routing`, and JMS/AMQP's `G-44` for its three delivered quarters.
3. **Category B as one plan** — REST inbound and outbound engine work, `ktor-routing`,
   `javalin-apibuilder` and `sqs-template-receive`, on the spec that is already written
   and waiting. Beyond the CI runs above, REST out waits on this alone; REST in and SQS
   wait on this plus their Category B/C items (`quarkus-jaxrs`, `conditional-controllers`,
   `kotlin-null-handler`; `micronaut-jms-over-sqs`); JMS/AMQP waits on CI alone.
4. **Category C** — the six that need their own design, `temporal-cadence` and
   `vertx-eventbus` among them; Async waits on those two, SQS on `micronaut-jms-over-sqs`.
5. **`pubsub-channel-adapter`** — its own `config_join` extension; Pub/Sub's one open item.
6. **Meridian** (`FR-21`–`FR-24`) has no matrix cell and waits on nothing but being built.
7. **Section 2's cross-cutting defects** last, to make "no open Critical or Major" true.
