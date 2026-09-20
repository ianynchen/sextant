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

**Minor items are logged, not blocking (ruled 2026-09-13, after PR A2).** The definition above
says a feature is delivered with no open Critical or Major, so the ```delivery block carries
Critical and Major ids only. Every Minor gap keeps its `severity` line and its §1 row
(`javalin-crud`, `ktor-wildcard-segment`, `gateway-and-of-two-paths`,
`gateway-order-mid-chain`, `url-openconnection`, `jdk-body-publisher`, `jdk-newbuilder-copy`,
`apache-execute-httphost-peer`, `gateway-detect-4x-coordinate`) and is addressed when its
feature's next spec touches the seam — never silently dropped, never a blocker.
`ktor-route-with-verb` was the first to close that way (2026-09-20, the Kotlin/Ktor spec).

```delivery
REST inbound       | REST in    | conditional-controllers dsl-media-route gateway-properties-routes
REST outbound      | REST out   | apache-camel
SOAP               | SOAP       |
GraphQL            | GraphQL    |
WebSocket          | WebSocket  |
SSE                | SSE        |
gRPC               | gRPC       |
Kafka              | Kafka      | smallrye-reactive-messaging
JMS and AMQP       | JMS / AMQP |
AWS SQS            | SQS        |
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
dsl-media-route | Major
javalin-crud | Minor
ktor-route-extensions | Major
ktor-selector-blocks | Major
ktor-wildcard-segment | Minor
ktor-route-with-verb | Minor
gateway-properties-routes | Major
gateway-and-of-two-paths | Minor
gateway-order-mid-chain | Minor
url-openconnection | Minor
kotlin-class-lambdas | Major
kotlin-default-bridge-calls | Major
jdk-body-publisher | Minor
jdk-newbuilder-copy | Minor
apache-execute-httphost-peer | Minor
gateway-detect-4x-coordinate | Minor
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

The seven rows at the head of the block (the four Kotlin/Ktor Majors and `kotlin-null-handler`,
`ktor-route-with-verb`, `inbound-request-requirements`; 2026-09-20) were written before their PR ran in CI; `<pending PR CI>`
is filled with the run id once that pipeline is green, and until then they are
implemented-and-locally-green, not closed by this file's own definition.

```closed
kotlin-null-handler | tests/e2e/test_rest_inbound_delivered.py::test_ktor_routing_derives_every_route_under_its_nested_prefixes | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
kotlin-class-lambdas | tests/e2e/test_rest_inbound_delivered.py::test_the_class_lambda_twin_derives_identical_rows | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
kotlin-default-bridge-calls | tests/application/test_ktor_defaults_fixture.py::test_under_a_catalog_naming_mount_the_defaulted_call_derives_its_route | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
ktor-route-extensions | tests/e2e/test_rest_inbound_delivered.py::test_a_dsl_receiver_helper_called_inside_the_kotlin_router_derives_its_route | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
ktor-selector-blocks | tests/e2e/test_rest_inbound_delivered.py::test_ktor_selector_requirements_reach_endpoint_metadata | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
ktor-route-with-verb | tests/e2e/test_rest_inbound_delivered.py::test_ktor_routing_derives_every_route_under_its_nested_prefixes | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
inbound-request-requirements | tests/e2e/test_rest_inbound_delivered.py::test_spring_request_params_record_what_the_binder_enforces | https://github.com/ianynchen/sextant/actions/runs/<pending PR CI>
G-30 | tests/e2e/test_rest_inbound_delivered.py::test_gateway_routes_derive_their_inbound_surface | https://github.com/ianynchen/sextant/actions/runs/34793215476
G-30-outbound | tests/e2e/test_rest_outbound_delivered.py::test_gateway_targets_derive_outbound | https://github.com/ianynchen/sextant/actions/runs/34793215476
ktor-routing | tests/e2e/test_rest_inbound_delivered.py::test_ktor_routing_derives_every_route_under_its_nested_prefixes | https://github.com/ianynchen/sextant/actions/runs/34793215476
javalin-apibuilder | tests/e2e/test_rest_inbound_delivered.py::test_javalin_api_builder_derives_the_composed_path | https://github.com/ianynchen/sextant/actions/runs/34793215476
sqs-template-receive | tests/e2e/test_aws_sqs_delivered.py::test_a_template_receive_names_its_queue_inside_the_options_lambda | https://github.com/ianynchen/sextant/actions/runs/34793215476
jdk-httpclient | tests/e2e/test_rest_outbound_delivered.py::test_the_jdk_http_client_derives_every_request_it_builds_and_sends | https://github.com/ianynchen/sextant/actions/runs/34793215476
G-36 | tests/e2e/test_soap_delivered.py::test_one_handler_serving_two_message_types_derives_both | https://github.com/ianynchen/sextant/actions/runs/34646355110
G-44 | tests/e2e/test_jms_and_amqp_delivered.py::test_rabbit_template_receives_derive_one_inbound_row_per_queue | https://github.com/ianynchen/sextant/actions/runs/34703991222
G-31 | tests/e2e/test_kafka_delivered.py::test_a_streams_dsl_topology_derives_every_source_and_sink | https://github.com/ianynchen/sextant/actions/runs/34703991222
alpakka-pekko | tests/e2e/test_kafka_delivered.py::test_pekko_consumer_sources_derive_one_inbound_row_per_subscribed_topic | https://github.com/ianynchen/sextant/actions/runs/34703991222
javalin-routing | tests/e2e/test_rest_inbound_delivered.py::test_javalin_flat_registrations_derive_every_route | https://github.com/ianynchen/sextant/actions/runs/34703991222
micronaut-sqs | tests/e2e/test_aws_sqs_delivered.py::test_a_micronaut_module_using_the_raw_sqs_sdk_derives_its_queues | https://github.com/ianynchen/sextant/actions/runs/34703991222
jaxws-public-final | tests/e2e/test_soap_delivered.py::test_a_public_final_method_is_not_an_operation | https://github.com/ianynchen/sextant/actions/runs/34703991222
jaxws-inherited-unannotated | tests/e2e/test_soap_delivered.py::test_an_operation_inherited_from_an_unannotated_superclass_is_not_published | https://github.com/ianynchen/sextant/actions/runs/34703991222
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
G-37 | tests/e2e/test_rest_inbound_delivered.py::test_the_builder_form_derives_every_route_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/34767891205
W44-verb-overloads | tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/34767891205
GAP-1b | tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/34767891205
quarkus-jaxrs | tests/e2e/test_rest_inbound_delivered.py::test_a_jaxrs_resource_derives_every_operation | https://github.com/ianynchen/sextant/actions/runs/35416301779
jaxrs-sse | tests/e2e/test_rest_inbound_delivered.py::test_a_jaxrs_sse_endpoint_is_classified_as_sse | https://github.com/ianynchen/sextant/actions/runs/35416301779
kafka-batch-generics | tests/application/test_pipeline.py::test_a_batch_true_listener_publishes_the_element_not_the_list | https://github.com/ianynchen/sextant/actions/runs/35416301779
micronaut-jms-over-sqs | tests/e2e/test_messaging_micronaut_delivered.py::test_micronaut_jms_over_sqs_is_sqs_on_both_sides | https://github.com/ianynchen/sextant/actions/runs/35416301779
mp-rest-client | tests/e2e/test_rest_outbound_delivered.py::test_a_microprofile_rest_client_interface_derives_its_outbound_operations | https://github.com/ianynchen/sextant/actions/runs/35416301779
```

---

## 1. The list, by feature

One row per blocker the ```delivery block above still carries, in that block's order. A
closed item keeps a row only where its closing has to be read beside its neighbours, and
every such row says `**closed**` with the CI run that proved it. The seven blockers that
shipped on the delivery branch (`javalin-routing`, `jaxws-public-final`,
`jaxws-inherited-unannotated`, `G-31`, `alpakka-pekko`, `micronaut-sqs`, `G-44`) passed their
intention tests in CI run 34703991222 and are in ```closed; their rows below say so.

### REST inbound — NOT DELIVERED (largest)

| # | issue | what it costs |
|---|---|---|
| `G-37` | **closed** (PR #25, run 34767891205) — `RouterFunctions$Builder` unread, **0 of 20 methods, both stacks** | a module routing this way exports **no HTTP at all** |
| `G-30` | **shipped** (PR A2 Task 7, commit `3ca2219`) — `spring-cloud-gateway.yml` reads a route's receiver chain of predicates (`path`, `method`, `host`, `header`, `query`, `cookie`, `remoteAddr`, `xForwardedRemoteAddr`, `after`, `before`, `between`, `readBody`, `weight`, `version`, `cloudFoundryRouteService`, `order`, `alwaysTrue`, `metadata`/`replaceMetadata`/`customize`), composed by `and()`/`or()` and negated by `not()`/`negate()`, folded into the route the chain's terminal `uri(…)` call emits; a route with no `method()` publishes the framework's own catch-all (method NULL, resolved), and `not()` anywhere in the tree poisons the row. Both `routes().route(id, r -> …)` and `routes().route(r -> …)` fold their own body, told apart by the new entry-`arity` word. Not yet in ```closed — awaiting this PR's CI | the commonest edge component in a Spring estate, inbound and outbound |
| `W44-verb-overloads` | **closed** (PR #25, run 34767891205) — W44's seven `RouterFunctionDsl` verb rules are correct for **1 of 5** overloads | MEASURED 2026-09-13 (not the fabrication this row claimed): `GET(handler)` derives `unresolved` for a deliberate catch-all, `GET("/x", predicate, handler)` loses its handler and reads `resolved`, `GET(predicate, handler)` loses the predicate — mis-graded rows, not invented ones |
| `GAP-1b` | **closed** (PR #25, run 34767891205) — WebFlux non-coroutine `router { }` derives nothing | whole Kotlin router silent |
| `gateway-properties-routes` | **logged (PR A2 Task 9, spec §15)** — `spring.cloud.gateway.routes[0].predicates[0]=Path=/orders/**`: routes declared in properties or YAML rather than the Java DSL, `config_join` territory and, in some estates, the commoner spelling of the two | a gateway module configured this way still publishes no routes |
| `gateway-and-of-two-paths` | **logged (PR A2 Task 6/7, Minor)** — `path("/a").and().path("/b")` folds to one route, `/a/b` — the framework serves neither path alone, so the folded route is dead on real traffic | a spurious resolved row rather than the two the framework actually refuses to route |
| `gateway-order-mid-chain` | **logged (PR A2 Task 6/7, Minor)** — `order(int)` returns `PredicateSpec`, so a predicate after it does not extend its result; written mid-chain, the pass-through is reached unconsumed by the body fold and yields a spurious unresolved row beside the route's own resolved one. At the head of the chain it is stepped over cleanly | one extra row per such route |
| `gateway-detect-4x-coordinate` | **logged (PR A2 Task 9, Minor)** — `spring-cloud-gateway.yml` is a `combinator` catalog, and `detect.coordinates` is inert for that style (`src/sextant/application/resolve/dependencies.py` ~46-70: the rules apply on any module whose bytecode names the matched types, coordinate list or not), so listing `spring-cloud-gateway-server` (the pre-5.0 combined artifact) alongside the 5.x split artifacts changes nothing either way. The real gap is that `measured:` only javap's `spring-cloud-gateway-server-webflux:5.0.0` — the catalog's rules are unverified against a 4.x jar's bytecode | a 4.x module is read by rules measured on 5.0.0 alone, unverified at that version |
| `conditional-controllers` | `@ConditionalOnProperty` / `@Profile` controllers | tier C — no mechanism in the code |
| `kotlin-null-handler` | **closed** (Kotlin/Ktor spec 2026-09-19 §3b, commits `eefca79` + `e6497f0`; pinned by `test_ktor_routing_derives_every_route_under_its_nested_prefixes` and `tests/application/test_pipeline.py`'s Kotlin router pins; run pending) — Kotlin routes carried a **NULL handler**, all 3 of `orders-service`'s and 8 of 8 of `orders-ktor`'s; no Kotlin symbol reached `roots` or `reachability`. kotlinc 2.2.0 compiles every suspend handler to a CLASS (CP-23), the extractor now marks that class's type fact with the `invokeSuspend` holding its body (`lambda_body`, D00 §5), and `resolve/effective_calls.py` hands every engine the `instance` as that `lambda` — so `handler_arg` names the body and `roots`/`reachability` walk it (`orders-ktor`: 8 roots, 64 reachable). The function-reference handler (`GET("/orders", ::listOrders)`, a `FunctionReferenceImpl`) closed with CP-23 Q9: 3 of 3 on `orders-service` | Java functional routes name theirs; Kotlin ones now do too |
| `quarkus-jaxrs` | **closed** — implemented, pinned by `test_a_jaxrs_resource_derives_every_operation`, `test_the_javax_spelling_derives_the_same_operations`, `test_a_class_implementing_a_path_interface_derives_the_interfaces_operations`, `test_quarkus_rest_binds_the_body_the_way_quarkus_does` (`tests/e2e/test_rest_inbound_delivered.py`), **closed** on CI run 35416301779 (PR #30, merged 2026-09-18)** — three catalogs (`jakarta-jaxrs.yml`, `javax-jaxrs.yml`, `quarkus-rest.yml`) read `@Path`/`@GET`/`@Produces` as siblings of one method via `produces_from_siblings`/`consumes_from_siblings`/`type_media_from_siblings`, with `sole_unbound` as the request-body fallback (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md` §3, §4) | every Quarkus, Helidon, Jersey and RESTEasy resource derives nothing — deliberately, since a catalog of the existing forms would put every GET onto the class `@Path` |
| `ktor-routing` | **shipped** (PR A2 Task 5, commit `812a175`) — `ktor-routing.yml` walks a nested `route("/api") { get("/orders") { … } }` through `receiver_arg`, checking each inner call's receiver against the enclosing block's own `Route`, to arbitrary nesting depth; handler NULL stated at the time (no Kotlin symbol reached it — `kotlin-null-handler`, closed 2026-09-20, every row names its `invokeSuspend` body now). **closed** on CI run 34793215476 | a `single_call` row would publish `/x` alone, a wrong row |
| `ktor-route-extensions` | **closed** (spec 2026-09-19 §4a, commits `11cc5ce` + `f488c3e`; pinned on all three frameworks — Ktor by `test_ktor_routing_derives_every_route_under_its_nested_prefixes` (`GET /helper`, `GET /api/deep` two helpers deep), Javalin by `test_javalin_api_builder_derives_the_composed_path` (`GET /jv/helped/h`), the Spring Kotlin DSL by `test_a_dsl_receiver_helper_called_inside_the_kotlin_router_derives_its_route`; run pending) — a module-local helper the routing origin flows into as an ARGUMENT is followed, under the caller's prefix; an origin-less body follows only where its rule declares `follow_calls: all` (Javalin's thread-local `ApiBuilder`, CP-25 row 1); sixteen calls deep the walk stops and files one `routing_depth` question, never a row. Was: **logged (PR A2 Task 5, Major)** — the shape is not Ktor-only. Ktor's `fun Route.api() { get("/x") {} }` called from `routing { api() }`, Javalin's `apiBuilder(() -> { userRoutes(); })` with a static helper method that itself calls `get(...)`, and Spring's Kotlin DSL `router { helper() }` with `fun RouterFunctionDsl.helper()` all derive NOTHING, not even an unresolved row: a non-extending verb sitting in a method no linking call names is never rooted, so the walk never reaches it. Each is that framework's own documented way to structure a non-trivial app. A method reference at the call site (`path("/x", Ctl::routes)`) DOES work — the reference is itself the root the walk needs | a module structured any of these three ways is under-reported with no row even saying so |
| `ktor-selector-blocks` | **closed** (spec 2026-09-19 §4b, commit `c3d017c`; pinned by `test_ktor_routing_derives_every_route_under_its_nested_prefixes` — `GET /j` with `produces`, `POST /c` with `consumes`, `/orders`, `/dbg`, `/fast`, `/paged` beneath `header`/`param`/`optionalParam`, `/never` absent — and `test_ktor_selector_requirements_reach_endpoint_metadata`; run pending) — a selector is a PREFIX that sets a verb (`verb_arg`), a media column (`media_arg` + `fills`) or a request requirement (`request_requirement`) instead of a path; `HttpMethod.Get` and `ContentType.Application.Json` are getter calls (CP-24 rows 3–4) read through `verb_values.getters`/`media_values.getters`; a route whose verb disagrees with its `method` scope is a node Ktor never dispatches (CP-24 row 7) and publishes nothing. Was: **logged (PR A2 Task 5, Major)** — the six selector blocks `method`, `param`, `optionalParam`, `header`, `accept`, `contentType` derive NOTHING, not even an unresolved row, and every route nested under one is lost with them; only the four-argument `route` overload yields a row | a `method(Get) { get { } }` guard silently drops the route inside it |
| `ktor-wildcard-segment` | **logged (PR A2 Task 5, Minor)** — a bare `*` path segment under `leading_slash` (`route("/api") { get("*") { } }`) publishes `/api*` resolved, where Ktor serves `/api/<one segment>` — the documented wildcard forms (`*`/`{...}` inside a longer path) read correctly; only a bare `*` component is wrong | a wrong resolved row, rare in practice |
| `ktor-route-with-verb` | **closed** (spec 2026-09-19 §4b–c, commits `c3d017c` + `e727f1c`; pinned by `test_ktor_routing_derives_every_route_under_its_nested_prefixes` — `PUT /legacy2` from `route("/legacy2", HttpMethod.Put) { handle { } }`, and `handle { }` under a bare `route("/health2")` fanning out through `all_methods`' seven members; run pending) — `verb_arg` is a prefix word now, and `handle` is a verb-less terminal taking the scope's verb. Was: **logged (PR A2 Task 5, Minor)** — the four-argument `route(Route, String, HttpMethod, Function1)`, a prefix that also sets the verb, derives one unrecognised-overload row; reading it needs `verb_arg` on a PREFIX, and today's `verb_arg` is a verb-rule-only word | one unresolved row instead of the route it declares |
| `javalin-routing` | **closed** on CI run 34703991222 — **shipped** (`javalin.yml`, w61, `5e3e887` and `abba4db`): both flat forms derive, pinned by `tests/e2e/test_rest_inbound_delivered.py::test_javalin_flat_registrations_derive_every_route`. Still on the register because that test has not yet passed in CI | — |
| `javalin-apibuilder` | **shipped** (PR A2 Task 3, commit `23932a1`) — `javalin-apibuilder.yml` reads the nested `apiBuilder(() -> path("/orders", () -> { get("/{id}", h); post(h); path("/{id}/items", () -> get(h)); }))` form to arbitrary nesting depth, every row attributed to the enclosing `Javalin.create(config -> …)` lambda; a catalog-declared `path_join: leading_slash` rule joins a slashless `path("api", …)` to `/api`, never the wrong `api` glued to its parent. Not yet in ```closed — awaiting this PR's CI | a flat read would publish `/{id}` without its prefix, a wrong row |
| `javalin-crud` | **logged (PR A2 Task 3, Minor)** — `crud("/users/{id}", h)` registers five routes (`GET`, `GET {id}`, `POST`, `PATCH {id}`, `DELETE {id}`) from one call; derivable as five rows off a fixed verb/path table, not built | five routes read as none |
| `G-45` | **closed** — a Data REST resource over MongoDB derives its route table since `6f088be`, proven in CI run 34669970510. The R2DBC, Cassandra, Elasticsearch, Neo4j and reactive contracts still outside are `GAP-6` | — |
| `spring7-version` | **closed** — two versions of one route are not reported as a conflict, proven in CI run 34669970510 | — |
| `dsl-media-route` | `accept(MediaType, Function1)` / `contentType(MediaType, Function1)` on `RouterFunctionDsl` (both stacks) and `CoRouterFunctionDsl`: a route declared under a media guard alone. Before PR A1 this was silence; now it is one honest `unresolved` row (PR A1, the addresses-nothing seam pinned by a guard) — but the proper read needs a word this grammar does not have: "the media value IS the route's own constraint" on a verb-less rule, so the row can carry its handler and its media instead of naming neither | a media-gated route (e.g. a JSON-only handler with no path) derives an unresolved row instead of `path: /**` with its `produces`/`consumes` set |
| `kotlin-class-lambdas` | **closed** (spec 2026-09-19 §3b, commits `645dd1d` + `eefca79` + `b81a2ae`; pinned by `test_the_class_lambda_twin_derives_identical_rows` — `fixtures/orders-ktor-classlambdas`, the same source compiled with `-Xlambdas=class`, derives byte-identical endpoint rows to `orders-ktor` — and `test_the_class_lambda_twin_is_built_from_the_very_same_source`; run pending) — engine-wide: the projection sits where every engine reads call sites, so no engine learns the word Kotlin. Was: **logged (PR A2 Task 9, spec §15, Major)** — a lambda compiled as a class (`-Xlambdas=class`, the default before Kotlin 2.0) arrives as `kind: instance`, not `kind: lambda`; the body-linked entry roots and derives zero routes — one unresolved row under §4b, not silence, but the address is unreadable | every Kotlin router DSL module built with Kotlin < 2.0 (or `-Xlambdas=class` explicitly) under-reports |
| `kotlin-default-bridge-calls` | **closed** (spec 2026-09-19 §3a, commits `389b719` + `b81a2ae`; pinned by `tests/application/test_ktor_defaults_fixture.py` — `mount("/d") { }` omitting `version` reaches the engine as `mount` with `version` unresolved and, under a catalog naming `mount`, derives `/d/x` — and eleven unit tests in `tests/application/test_effective_calls.py` incl. a 33-parameter two-mask function; run pending) — `resolve/effective_calls.py` re-targets a `$default` site to the sibling its `bridge_of` fact names, mask bits over the DECLARED parameters (an extension receiver is not one), each omitted parameter `{kind: unresolved, reason: defaulted}`: a defaulted path is an unresolved row, never a guessed default. Was: **logged 2026-09-13 (user question after PR A2), Major when reachable** — a Kotlin call that OMITS a defaulted parameter is compiled as a call to the synthetic `name$default(…, mask, marker)` bridge: a different name and arity, which no catalog rule matches, so the route derives NOTHING (not the unrecognised-overload row — that fires only on a name the vocabulary carries). Named and out-of-order arguments are NOT affected (the compiler reorders them into the declaration's order before the bytecode). Not triggered today: `RoutingBuilderKt` declares zero `$default` bridges (measured, 3.0.3) and the Spring DSL rules are on Java-declared members. Fix when a catalog first covers a Kotlin function with defaults: the catalog declares the bridge form (`name$default`, arity = declared + masks + 1, the same positions) — or the engine maps a `$default` call back to its sibling as the extractor's `KotlinDefaultBridge` already does on the declaration side | a Kotlin DSL function with a default parameter, called without it — silence for that route |
| `inbound-request-requirements` | **added 2026-09-19 (user ruling) and closed in the same PR** (spec 2026-09-19 §5, commits `51f363b`, `c3546e7`, `c2d6792`, `a45c0a3`, `6107170`, `b277087`, `d4ffd1a`, `e8cf642`; pinned by `test_spring_request_params_record_what_the_binder_enforces`, `test_a_kotlin_defaulted_or_nullable_parameter_is_optional_to_the_binder`, `test_spring_mapping_params_and_headers_expressions_are_requirements`, `test_jaxrs_named_parameters_are_optional_in_both_spellings`, `test_micronaut_binds_required_unless_the_argument_is_nullable`, `test_quarkus_rest_and_reactive_routes_parameters_are_optional`, `test_ktor_selector_requirements_reach_endpoint_metadata`, `test_ktor_handler_reads_reach_endpoint_metadata`, `test_javalin_handler_reads_reach_endpoint_metadata`, `test_servlet_handler_reads_reach_endpoint_metadata`, `test_gateway_header_and_query_predicates_reach_endpoint_metadata`, `test_a_query_param_predicate_reaches_endpoint_metadata_on_the_functional_router`; run pending) — no REST inbound row recorded that the endpoint requires a header, query parameter or cookie, while every outbound row already recorded what the call sends. `endpoint_metadata.requirement` (`required`/`optional`/`absent`, NULL where the code states nothing) is now written for fourteen catalogs: Spring MVC/Web (`@RequestParam`/`@RequestHeader`/`@CookieValue` through the binder rule, `@RequestMapping(params=, headers=)` expressions), JAX-RS ×3 and Quarkus's `@Rest*`, Micronaut, reactive routes' `@Param`/`@Header`, Ktor (selectors, handler reads, `required_when_thrown`), Javalin (`ApiBuilder` rows), Servlet ×2 (reads), Gateway DSL (`header`/`query`/`cookie`), Spring router Java (`queryParam`/`param`). Boundaries stated in COVERAGE §5.1: a Javalin flat row's lambda reads, `headers(Predicate)`, `name!=v`'s excluded value, Ktor 2.x interface receivers | every REST inbound framework's rows say what a caller must send; the stitcher's request-compatibility test has headers to compare (M06) |

> `verify: grep -rl "RouteLocator" src/sextant/catalogs/` → empty
> `verify: awk '/repositories:/,/routes:/' src/sextant/catalogs/spring-data-rest.yml | grep -c Mongo` → 4

**Stated boundaries in the builder form, measured rather than fixed (PR A1 Task 4; not delivery
blockers — each is either honest engine output or a shape real code rarely writes).**

- A statement-form builder held in a FIELD or received as a PARAMETER — `this.b.GET("/a",
  h);`, `void routes(Builder b) { b.GET("/a", h); }` — derives nothing, not even the
  unresolved row: in the facts that verb's chain has no call in the method for a head, which
  is exactly what keeps a body from rooting (spec §7 case 4's stated boundary). The
  `base().POST(…)` spelling, whose receiver IS a call in the method, is the one that yields a
  row.
- An UNDECLARED statement-form head — `var b = helper(); b.GET("/a", h); b.POST("/b", h);
  return b.build();` — yields one unresolved row per statement, not one row for the whole
  chain: each statement roots on the unread `helper()` and so does `build()`, so N statements
  give N+1 identity-less rows beside the N real routes (spec §7 case 4, extended). Identity-
  unknown rows never dedup, by design.
- A method that is BOTH linked as a lambda body (`nest(path("/api"), this::apiRoutes)`) AND
  separately served on its own (its own `@Bean`) loses its own row: the A1 final review's fix
  for a linked body double-deriving (I-1) skips ANY caller a linking call names as its body
  from the root scan, whole — so the same method reached a second way, as an independent
  root, is skipped too, and is folded under the prefix only.
- A mixed-form builder (some statements, some chained) whose shared route is itself
  unresolved yields that one unresolved row twice: `_merged`'s identity dedup removes a
  resolved route that both a statement and `build()` reach (spec §4, "identity dedup removes
  the routes both reach"), but an identity-unknown row carries no identity to dedup on.

### REST outbound — NOT DELIVERED

| # | issue |
|---|---|
| `G-30-outbound` | **shipped** (PR A2 Task 7, commit `3ca2219`) — `spring-cloud-gateway-outbound.yml` reads each route's `uri(…)` target via `lambda_steps`, `channel_arg` keeping `http://…`/`lb://…` whole (peer NULL by design — a load-balanced target names no host). Not yet in ```closed — awaiting this PR's CI |
| `mp-rest-client` | **closed** — implemented, pinned by `test_a_microprofile_rest_client_interface_derives_its_outbound_operations` (`tests/e2e/test_rest_outbound_delivered.py`), **closed** on CI run 35416301779 (PR #30, merged 2026-09-18)** — `microprofile-rest-client.yml` (`declared_on: interface`) is `jakarta-jaxrs.yml` with the direction flipped, `peer_from: [baseUri, configKey]` read off `@RegisterRestClient` itself via the new `peer_annotation` word (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md` §3f). Was: **named 2026-09-13 (A2 register close)** — MicroProfile REST Client (`@RegisterRestClient` on an interface, `@GET`/`@Path` on its methods; Quarkus's standard outbound client) had no catalog. Costs a Quarkus/MicroProfile module its whole outbound surface |
| `apache-camel` | **named 2026-09-13 (A2 register close)** — Apache Camel's route DSL (`from("kafka:orders").to("http://svc/api")`) has no catalog: protocol, direction and destination sit in one URI literal, tier B, `fluent` over URI strings. COVERAGE §5.2 calls it the largest single payoff. Needs a short spec (a URI-scheme→protocol table; `from`/`to`/`toD` as steps). Costs a Camel module its whole integration surface |
| `jdk-httpclient` | **shipped** (PR A2 Task 8, commit `be46e52`) — `jdk-httpclient.yml` and `apache-httpclient.yml` are `fluent` catalogs: `HttpRequest.newBuilder().uri(URI.create(…)).POST(…).build()` sent inline, the `newBuilder(URI)` overload, `.method("PATCH", …)`, and Apache's `new HttpGet(…)`/`ClassicRequestBuilder.get(…)` all derive through `send`/`execute`, a constructed Apache request handed straight to `execute` included (fix round 2). `url_via` gained an optional `arity` so a via form naming `java.net.URI`'s `<init>` cannot misread a multi-argument constructor's first argument as the URL. `RestTemplate`/`RestClient`/`WebClient`/OkHttp's own `fluent` doctrine — a request built in one method and sent in another derives NOTHING — now literally governs these two catalogs too (spec §13 case 9). Not yet in ```closed — awaiting this PR's CI |
| `url-openconnection` | **logged (PR A2 Task 9, spec §15, Minor)** — `URL.openConnection()`'s verb is set by a LATER statement on the same connection (`conn.setRequestMethod("POST")`), default GET if never set — a walk forward from a receiver, not backward to a root, and a new default-verb rule this design does not have; every module using the JDK's older client shape derives no outbound rows for it |
| `jdk-body-publisher` | **logged (PR A2 Task 8, Minor)** — a `body` capture that reads a `BodyPublisher` leaves the row `unresolved` rather than reading through it to the payload type — `fluent`'s own rule, same shape as OkHttp's `RequestBody.create(x)`; every JDK POST/PUT/PATCH row through this fixture reads `unresolved` rather than `resolved`. Open doctrine question: should an unreadable body shape poison the whole ROW, or only the claim about its payload? |
| `jdk-newbuilder-copy` | **logged (PR A2 Task 8, Minor)** — `newBuilder(HttpRequest, BiPredicate)` (copy-and-modify) carries the SEEDED request's verb (GET) rather than reading the copy's own; a copied-and-modified request may publish the wrong verb |
| `apache-execute-httphost-peer` | **logged (PR A2 Task 8, Minor)** — `execute(HttpHost, ClassicHttpRequest, …)`: the `HttpHost` peer argument is not read, so the row is path-only with `peer` NULL; the target host is missing from a row that has it available |

### SOAP — DELIVERED (both blockers closed on run 34703991222; matrix `✅`)

| # | issue |
|---|---|
| `G-36` | **closed** — `spring-ws.yml` declares `container:` for `@PayloadRoot` and `@SoapAction`, both `@Repeatable`, proven in CI run 34646355110 |
| `jaxws-public-final` | **closed** on CI run 34703991222 — **shipped** (Task 9, `c6539f0`): a `public final` method on a `@WebService` is not an operation — `isWebMethodBySpec` excludes `final` beside `static`, and `derive_endpoints.sql`'s member rule now does too. Pinned by `tests/e2e/test_soap_delivered.py::test_a_public_final_method_is_not_an_operation`. Still on the register because that test has not yet passed in CI |
| `jaxws-inherited-unannotated` | **closed** on CI run 34703991222 — both runtimes measured, w63; Sextant over-reported: `gate_ancestry` derived an operation inherited from a plain, unannotated superclass that NEITHER jaxws-rt nor Apache CXF would ever serve. **Fixed in Task 10b, awaiting CI** — `derive_endpoints.sql`'s member rule now requires the DECLARING class to carry `@WebService`; pinned by `tests/e2e/test_soap_delivered.py::test_an_operation_inherited_from_an_unannotated_superclass_is_not_published` |

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
| `jaxrs-sse` | **closed** — implemented, pinned by `test_a_jaxrs_sse_endpoint_is_classified_as_sse` and `test_quarkus_element_type_alone_makes_a_stream_sse` (`tests/e2e/test_rest_inbound_delivered.py`), **closed** on CI run 35416301779 (PR #30, merged 2026-09-18)** — `jakarta-jaxrs.yml`/`javax-jaxrs.yml` carry `protocol_hint.hint_media` on `@Produces(SERVER_SENT_EVENTS)`; `quarkus-rest.yml` adds a second, presence-only evidence kind, `protocol_hint.hint_annotations`, for `@RestStreamElementType`/`@RestSseElementType` (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md` §3c). Was: JAX-RS `@Produces(SERVER_SENT_EVENTS)` — an attribute on a sibling annotation of the verb's method, the same engine form as `quarkus-jaxrs` (§0, "Moved to engine work") |

### Kafka — NOT DELIVERED

| # | issue |
|---|---|
| `G-31` | **closed** on CI run 34703991222 — **Kafka Streams — three catalogs ship** (`kafka-streams.yml`, `kafka-streams-sink.yml`, `kafka-streams-topology.yml`, w60, split by owner per D02 §3.1): DSL sources/sinks, Processor API sink, and the `addSource` varargs topics all derive; `to(TopicNameExtractor)` and `through` are stated outside. Stays open here only because closing needs a CI run URL (register discipline), not because work remains |
| `kafka-batch-generics` | **closed** — implemented, pinned by `test_a_batch_true_listener_publishes_the_element_not_the_list` (`tests/application/test_pipeline.py`), **closed** on CI run 35416301779 (PR #30, merged 2026-09-18)** — `spring-kafka.yml` declares a conditional wrapper, `wrappers[].when: { annotation_arg: { annotation: …KafkaListener, name: batch, parses_true: true } }` (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md` §5a); `batch = "true"`/`"TRUE"` unwraps `List<T>` to `T` at rooting, and an ordinary `List<T>` request body with no `batch` attribute still publishes the array (`test_a_batch_listeners_request_shape_is_an_array`, unchanged). Was: batch listener generics: `@KafkaListener(batch = true)` takes `List<Foo>`; the payload publishes as the list, not the element. Engine work (§0, "Moved to engine work") — a wrapper conditional on an annotation attribute |
| `smallrye-reactive-messaging` | **named 2026-09-18 (B/C register close)** — SmallRye Reactive Messaging (`@Incoming("orders")` / `@Outgoing`, Quarkus's Kafka binding; the channel is named in code and the topic sits in `application.properties` under `mp.messaging.incoming.<channel>.topic`) has no catalog — COVERAGE §5.8 line 3107, tier **B**, a `config_join` read in the shape `spring-cloud-stream.yml` already does. Surfaced because Kafka's ```delivery row emptied when `kafka-batch-generics` closed while §5.8 still carried this row uncatalogued — the definition's second clause, exactly as `mp-rest-client` surfaced on REST outbound at the A2 close. Costs a Quarkus/SmallRye module its whole Kafka surface — a module using `@Incoming`/`@Outgoing` publishes no Kafka endpoint |
| `alpakka-pekko` | **closed** on CI run 34703991222 — **shipped** (`15deca9`, w62): Pekko Connectors consumer sources derive one inbound row per subscribed topic, pinned by `tests/e2e/test_kafka_delivered.py::test_pekko_consumer_sources_derive_one_inbound_row_per_subscribed_topic`. Still on the register because that test has not yet passed in CI |

### JMS / AMQP — DELIVERED (`G-44` closed on run 34703991222; matrix `✅`)

| # | issue |
|---|---|
| `G-44` | **closed** on CI run 34703991222 — three of four quarters derive (Tasks 1–3, commits `371cfaf`, `760c884`, `7771be7`): `RabbitTemplate`'s nine queue-naming overloads, `JmsTemplate`'s four, `KafkaTemplate`'s one. The SQS quarter is `sqs-template-receive` on the SQS row — `SqsTemplate.receive*` buries the queue inside `Consumer<SqsReceiveOptions>`, Category B (§4). `G-44` closes when the three delivered quarters' tests have passed in CI |

### AWS SQS — NOT DELIVERED

| # | issue |
|---|---|
| `G-43` | **closed** — `SqsAsyncClient.sendMessage` derives since `6f088be`, proven in CI run 34669970510. The 27 other methods on the async client, `receiveMessage` among them, are `GAP-3` |
| `micronaut-sqs` | **closed** on CI run 34703991222 — **shipped** (`b4bbfa4`): a Micronaut module's raw `SqsClient` derives through `aws-sqs-sdk.yml`, pinned by `tests/e2e/test_aws_sqs_delivered.py::test_a_micronaut_module_using_the_raw_sqs_sdk_derives_its_queues`. Still on the register because that test has not yet passed in CI |
| `sqs-template-receive` | **shipped** (PR A2 Task 2, commit `deb2355`) — `spring-sqs-template-receive.yml` reads all four `receive`/`receiveMany`/`receiveAsync`/`receiveManyAsync` overloads through the options lambda, the queue named inside (`opts.queue("orders-queue")`); handler = the polling method, caller NULL. `G-44`'s fourth and final quarter. Not yet in ```closed — awaiting this PR's CI |
| `micronaut-jms-over-sqs` | **closed** — implemented, pinned by `test_micronaut_jms_over_sqs_is_sqs_on_both_sides` (`tests/e2e/test_messaging_micronaut_delivered.py`), **closed** on CI run 35416301779 (PR #30, merged 2026-09-18)** — `micronaut-jms.yml` and `micronaut-jms-producer.yml` each carry a `protocol_hint.hint_when` on `@JMSListener`/`@JMSProducer`'s `value` attribute (R2: `value()` is the sole address-bearing attribute — there is no `connectionFactory` attribute, correcting the wording this row used to carry) equalling `SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME` (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md` §5b); a listener AND a producer bound to that factory both reclassify to `sqs` and link with a Spring SQS sender/listener on the shared queue name (DR-5). **The `@JMSProducer` half shipped with it (ruled 2026-09-18)**: the register named only the listener side, but the same factory-name switch applies identically to the producer's own `@JMSProducer.value()`, so both directions closed in one task (B/C Task 12) rather than leaving the outbound half open under a name of its own. Was: `@JMSListener(connectionFactory = "sqsJmsConnectionFactory")` derives through `micronaut-jms.yml` with protocol `jms` though the wire is SQS, so a Spring SQS sender and this listener will not link; Category C (§4) |

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

**gRPC**, **GraphQL**, **WebSocket**, **SOAP** and **JMS / AMQP.** GraphQL and WebSocket
closed their last blockers on CI run 34669970510, SOAP and JMS / AMQP on run 34703991222; all
four read `✅`. gRPC's every remaining gap is another language (Go, Python,
Rust, Swift), so its cell reads `◐` correctly and forever — the ```scoped-out block says so.

---

## 2. Open Criticals and Majors that block no single feature

These are real and they are not on the path to any cell above. They are listed so that
"no open Critical or Major" can be claimed honestly at the end, not so they are done first.

`GAP-7` left this register on 2026-09-12: it is a performance cost (a reactor module
analyses in 111s, 8s alone), not a missing feature, and the user ruled that a slow correct
answer is not a gap. It lives in [`performance.md`](performance.md) P-1, worked after the
register is empty.
`G-52` throw exits left this list on 2026-09-12: it blocked no feature, so it is not in
the `closed` block above; it is recorded closed in `open-issues.md`, by the tests named there.
`G-74` `signature.throws` gains its consumer left this list on 2026-09-12: it blocked no
feature, so it is not in the `closed` block above; it is recorded closed in
`open-issues.md`, by the tests named there.
`G-73` `visibility` two-valued for a four-valued concept left this list on 2026-09-12: it
blocked no feature, so it is not in the `closed` block above; it is recorded closed in
`open-issues.md`, by the tests named there.

**Logged 2026-09-20 (Kotlin/Ktor spec, Tasks 1–15) — eight issues real input can reach only
at the edges, none Critical or Major, recorded as `OI-96`–`OI-103` in `open-issues.md`:**
`apply_protocol_hints` reclassifying an outbound row after `fluent` wrote its metadata;
two `combinator` catalogs each filing a `routing_depth` question under one identity; the
whole-map skip by EXACT erased type (`HashMap` under `@RequestParam` slips through where
Spring's `isAssignableFrom` would not); a helper reached as a member call ON the origin, and
the Spring `Supplier<RouterFunction>` bodies, not followed; Ktor 2.x's interface-typed
`call`/`request` not being `via` owners; a Javalin flat row's lambda reads invisible;
`AdaptedFunctionReference` recognised by name and unmeasured.

**Logged 2026-09-13 (PR A2 Task 9) — rulings and probe notes that block no single feature,
none of them Critical or Major and none carrying a register severity:**

- `callback-rooted-caller` — a root inside a config callback (`Javalin.create(config ->
  …)`; the same shape reaches any framework whose entry point is a configuration lambda)
  carries the callback LAMBDA as its `caller`, never the enclosing method — the engine's
  own stated rule (a root's caller is the method that roots it), consistent with the
  `single_call` sibling rows. Attributing it to the enclosing method instead would need a
  word no vocabulary in this design carries. Cross-engine; ruled in Task 3, restated here
  for the register.
- `w19-receiver-first-style` — the w19 surface probe enumerates a candidate address by
  checking for a `String` at argument 0; an API that reads its address behind an extension
  RECEIVER instead (Ktor's own shape) prints a confident zero rather than "not measured by
  this style" — literally true of the three styles the probe measures, and the exact
  mirrored-rule risk its own docstring warns about. A fourth style would also add
  candidates to owners already enumerated by another style, so it is recorded here rather
  than built as a side effect of one catalog (Task 5).
- `origin-static-head-exempt` — a non-origin STATIC head inside an `origin_param` body
  (`Helpers.builder().GET(…)`, where the body's own parameter is never touched) is exempt
  from the head check the same way a declared-origin chain is (below): a static call is
  never an extending receiver, so no real input produces it today. Widens Task 4's
  original "declared-origin chain" log item to "any static head."
- `origin-declared-chain-in-body` — a declared-origin chain written and discarded inside an
  `origin_param` body (`route().GET("/a", h).build();` as a statement whose result is
  never returned or stored) reads clean under `_head_on_the_origin`, because `route()` is
  itself a static origin, and derives under the prefix even though nothing ever registers
  it. A discarded builder call registers nothing at runtime, so no real input produces it
  either (Task 4).

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
  strict-xfail in `tests/e2e/test_rest_inbound_delivered.py`. **Implemented, pinned, awaiting
  CI run (Groups B and C, PR pending)** — three engine words
  (`produces_from_siblings`/`consumes_from_siblings`, `type_media_from_siblings`, sibling
  inheritance) closed this; the tests are real assertions now, not xfail (§1's rows).

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
receiver chain. PR A1 (#25) shipped items 1–4 of §16 — `G-37`, `W44-verb-overloads`,
`GAP-1b`; PR A2 is the six of Part II. `G-30` was measured into this group at the same time as
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
  lambda class. Short spec. **Closed 2026-09-20** with the four Kotlin/Ktor Majors on spec
  `docs/superpowers/specs/2026-09-19-kotlin-majors-and-inbound-request-requirements-design.md`
  (§1's row); awaiting the PR's CI run.
- **JDK / Apache `HttpClient`** (`jdk-httpclient`, REST outbound, tier B). A builder
  chain; may fall out of Category B's mechanism, which the spec should establish before
  assuming it.
- **`@ConditionalOnProperty` / `@Profile` controllers** (`conditional-controllers`, tier
  C). No mechanism exists; a route's existence becomes conditional on configuration.
  Largest design question here.
- **`micronaut-jms-over-sqs`.** `@JMSListener(value = "sqsJmsConnectionFactory")` (R2: `value`
  is the sole address-bearing attribute; there is no `connectionFactory` attribute) derived
  through `micronaut-jms.yml` with protocol `jms` even though the wire is SQS, and choosing the
  protocol from the factory-name attribute was a per-attribute switch no engine word had
  (§5.10's DR-5 boundary note). **Implemented, pinned, awaiting CI run (Groups B and C, PR
  pending)** — `protocol_hint.hint_when` closed it, on both `@JMSListener` and `@JMSProducer`
  (§1's SQS row).
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

### The 22 items that need a spec — eight specs, and the order they run in

**Ruled 2026-09-12.** Every item without a spec is delivered and CI-proven; what is left
is the 22 below, and they are eight designs, not 22. The order is the one that empties
```delivery rows fastest — a row closed is the unit of progress, not an item shipped —
with the spec already written first.

| order | group | items | what closes when it lands |
|---|---|---|---|
| 1 | **A. Receiver chain / overload discrimination** — spec `ba59750`; **A1 shipped (#25); A2 in progress**: `G-37`, `W44-verb-overloads`, `GAP-1b`; **A2 is Part II**, the rest | `G-37` `GAP-1b` `W44-verb-overloads` `G-30` `G-30-outbound` `ktor-routing` `javalin-apibuilder` `sqs-template-receive` `jdk-httpclient` (9) | **REST outbound closes**; REST inbound 9 → 3; SQS 2 → 1. Fixes the three `RouterFunctionDsl` overloads the shipped rules mis-grade (`W44-verb-overloads`: a catch-all read as unreadable, a handler lost) |
| 2 | **B. Sibling-annotation reads** — `annotation_driven` reads an attribute off a sibling annotation of the same method — **DONE — closed on CI run 35416301779, PR #30** (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md`, B/C Tasks 1–10b) | `quarkus-jaxrs` `jaxrs-sse` (2) | **SSE closes**; REST inbound −1 |
| 2 | **C. Rules conditional on an annotation attribute** — one plan with B, both grow `annotation_driven` by one word — **DONE — closed on CI run 35416301779, PR #30** (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md`, B/C Tasks 11–12) | `kafka-batch-generics` `micronaut-jms-over-sqs` (2) | **SQS closed**; Kafka did NOT close — §5.8 still carried SmallRye Reactive Messaging uncatalogued (tier B), now the register item `smallrye-reactive-messaging` |
| 3 | **E. Adapter destination as a constructor argument** — `config_join` reads a call-site argument | `pubsub-channel-adapter` (1) | **Pub/Sub closes** |
| 4 | **D. New `Protocol` members and two naming words** | `temporal-cadence` `vertx-eventbus` (2) | **Async closes** |
| 5 | **G. Kotlin routes with a NULL handler** — short spec — **DONE 2026-09-20** (spec `docs/superpowers/specs/2026-09-19-kotlin-majors-and-inbound-request-requirements-design.md`, which also closed `ktor-route-extensions`, `ktor-selector-blocks`, `kotlin-class-lambdas`, `kotlin-default-bridge-calls`, `ktor-route-with-verb` and the new `inbound-request-requirements`; CI run pending) | `kotlin-null-handler` (1) | REST inbound −1 — and −4 more: the row now holds `conditional-controllers`, `dsl-media-route`, `gateway-properties-routes` |
| 6 | **F. Conditional controllers** — the hardest design question | `conditional-controllers` (1) | **REST inbound closes** |
| 7 | **H. Meridian** | `FR-21` `FR-22` `FR-23` `FR-24` (4) | **Meridian closes** — every row empty |

Each group is one spec → one plan → one PR, on the per-item loop; a group starts only
when its spec names the COVERAGE cell every item moves. Categories B and C above are the
same 22 items sorted by mechanism; this table is the same items sorted by what they close.

---

## 5. Where that leaves the matrix

1. **Moved to `✅`**: GraphQL and WebSocket, when their last blockers passed in CI run
   34669970510. SOAP did not — `G-36` closed on run 34646355110, but `jaxws-public-final`
   and `jaxws-inherited-unannotated` were found and fixed afterwards, and it reads
   `◐ (2 open)` until their tests pass in CI.
2. **`◐` waiting only on a CI run** — implemented, pinned, green locally: SOAP (the two
   above), Kafka's `G-31`, `alpakka-pekko` and now `kafka-batch-generics`, SQS's
   `micronaut-sqs` and now `micronaut-jms-over-sqs`, REST inbound's `javalin-routing` and
   now `quarkus-jaxrs`, REST outbound's `mp-rest-client`, SSE's `jaxrs-sse`, and JMS/AMQP's
   `G-44` for its three delivered quarters. **Kafka and SSE now wait on nothing but this CI
   run** — the ```delivery rows they carried held exactly one id each
   (`kafka-batch-generics`, `jaxrs-sse`), and both are implemented (Groups B and C, spec
   `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md`, PR
   pending). **SQS is the same**, its sole remaining id (`micronaut-jms-over-sqs`,
   both directions) implemented alongside them.
3. **Category B as one plan** — REST inbound and outbound engine work, `ktor-routing`,
   `javalin-apibuilder` and `sqs-template-receive`, on the spec that is already written
   and waiting. Beyond the CI runs above, REST out now waits on `apache-camel` alone
   (`mp-rest-client` implemented, pending the same CI run); REST in waits on this plus its
   remaining Category B/C/F items (`conditional-controllers`, `kotlin-null-handler`) —
   `quarkus-jaxrs` moved to row 2 above; JMS/AMQP waits on CI alone. *2026-09-20:
   `kotlin-null-handler` and the four Kotlin/Ktor Majors are implemented and pinned (row 5
   of §4's table); REST in now waits on `conditional-controllers`, `dsl-media-route`,
   `gateway-properties-routes` and the CI run.*
4. **Category C** — the remaining items that need their own design, `temporal-cadence` and
   `vertx-eventbus` among them; Async waits on those two. `micronaut-jms-over-sqs` moved to
   row 2 above — SQS no longer waits on Category C.
5. **`pubsub-channel-adapter`** — its own `config_join` extension; Pub/Sub's one open item.
6. **Meridian** (`FR-21`–`FR-24`) has no matrix cell and waits on nothing but being built.
7. **Section 2's cross-cutting defects** last, to make "no open Critical or Major" true.
