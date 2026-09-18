# Groups B and C Implementation Plan — sibling-annotation reads, the body rule, and rules conditional on an annotation attribute

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `quarkus-jaxrs`, `jaxrs-sse`, `kafka-batch-generics` and `micronaut-jms-over-sqs` (plus the `@JMSProducer` half the register never named) so the **SSE, Kafka and SQS delivery rows empty** and REST inbound drops by one.

**Architecture:** JAX-RS is three `annotation_driven` catalogs (`jakarta`, `javax`, Quarkus REST) over three new engine words — media read off sibling annotations, a class-level media default off a type-level sibling, and sibling inheritance all-or-nothing per JAX-RS §3.6 — and one new body-fallback word, `sole_unbound`, whose "unbound" is measured against the framework's own binding annotations with two Quarkus-only implicit bindings. Kafka batch and Micronaut SQS share one closed condition, `annotation_arg` with `equals` | `parses_true`, consumed by `wrappers[].when` (at rooting, never at expansion) and by `protocol_hint.hint_when`; Quarkus's element-type SSE is a third hint kind, `hint_annotations`. `resolves:` is untouched.

**Tech Stack:** Python 3.14 + pydantic + DuckDB, YAML catalogs, Maven fixtures (Java 21, Kotlin 2.2.0), pytest `-n 4 --dist loadfile`, `javap` on jars in `~/.m2` and downloaded to the scratchpad.

**Spec:** `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md`, as reviewed and ruled 2026-09-18 (read §0's table first, then §2, §3a–§3e, §4, §5a–§5b, §7–§9). Every rule below argues from it; where the plan and the spec disagree the spec wins and the executor records the conflict.

## Global Constraints

- **Nothing that works today may move** (spec §8): every key is optional and inert unless declared. Task 3 onward each end with the golden check — `endpoints`, `shapes`, `shape_fields`, `open_questions` rows and both rendered documents of `fixtures/orders-service`, `orders-spring7`, `orders-micronaut`, `orders-quarkus` byte-identical to `main`'s until a catalog declares the word (Tasks 10–12). The four fixture-total tests (`tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`, `tests/cli/test_app.py`, `tests/application/test_asm_scanner.py`) move additively when Task 1's fixtures land, with a comment naming the class.
- **Every new word is forced by a probe row** (spec §7): a `scripts/probes/cp<N>_*.md` file quotes the command and its output before the word is written; every catalog's `measured:` cites it (`tests/architecture/test_catalog_measurement_coverage.py`).
- **Closed vocabularies are refused by name, never read as "never fires"** (spec §2, §4): an unknown key under `when`, `annotation_arg`, `implicit_bindings`, `request_body` or `protocol_hint` raises `CatalogError` at load, in the engine that reads it.
- **Never a wrong row, never silence:** a body the rule cannot single out is *no contract*, never a guess; a hint whose condition does not hold leaves the row as derived.
- **GUIDELINES §5.1:** an engine word moves `docs/components/D02-catalog-schema.md` in the same commit; COVERAGE, the delivery list and the CHANGELOG land in Task 13.
- **No version bump** (standing gate). Plain language in `src/**` prose; language confinement (`tests/architecture/test_language_confinement.py`; catalog YAML and fixture sources are exempt).
- **Per-item loop:** every task ends with the full gate in the foreground — `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh` — then one commit. `git add`/`git commit` only: never `stash`, `checkout --`, `reset`, `push`, worktrees, branches.
- **Fixture facts are not committed** (`.sextant/` gitignored); `target/` never added. A fixture module's first compile after a new dependency may need the network once (`mvn -q compile` without `-o`), after which `-o` works. No new fixture MODULE: every fixture lands in `orders-spring7`, `orders-quarkus`, `orders-micronaut`, `orders-service`, all already in `tests/fixture_build.py::PRIMED_FIXTURES`.
- **Guards:** every new near-miss test carries `@pytest.mark.declines(<catalog>)` and exactly one `@pytest.mark.pins(<guard>)`; each new guard is a `Guard` entry in `scripts/guard_check.py` whose `Edit.find` is the exact line the task wrote; `bash scripts/check.sh --guards` runs end to end.
- **Symbol forms:** catalog YAML spells fqns dotted (`jakarta.ws.rs.Path`); facts and the `annotations` view spell them as descriptors (`jakarta/ws/rs/Path#`). Convert once at the binding seam with `_catalog_symbol` / `catalog_symbols` (`src/sextant/application/resolve/shapes/rooting.py`), never compare across notations.

---

## File map

| file | responsibility |
|---|---|
| `fixtures/orders-spring7/pom.xml`, `src/main/java/com/acme/jaxrs/{LegacyResource,ValidatedResource,OrdersApi,OrdersResource}.java` | Task 1 |
| `fixtures/orders-quarkus/pom.xml`, `src/main/java/com/acme/quarkus/{OrderResource,Upload}.java` | Task 1 |
| `fixtures/orders-service/pom.xml`, `src/main/kotlin/com/acme/orders/jaxrs/KotlinOrderResource.kt`, `src/main/java/com/acme/orders/messaging/OrderEventsListener.java` | Task 1 |
| `fixtures/orders-micronaut/pom.xml`, `src/main/java/com/acme/mn/OrderMessaging.java` | Task 1 |
| `tests/e2e/test_rest_inbound_delivered.py`, `tests/e2e/test_messaging_micronaut_delivered.py`, `tests/application/test_pipeline.py` | Task 1: strict-xfail live tests; Tasks 10–12 flip them |
| `scripts/probes/cp18_jaxrs_api_and_implementations.md`, `cp19_quarkus_rest.md`, `cp20_spring_kafka_batch.md`, `cp21_micronaut_jms_sqs.md` | Task 2 |
| `src/sextant/application/resolve/engines/annotation_driven.py` | Task 3 (`_sibling_sources` generalised, two params), Task 4 (`type_media_from_siblings`), Task 5 (sibling fqns into the walk) |
| `src/sextant/storage/duckdb/derive_endpoints.sql` | Task 3 (`sibling_media` CTEs), Task 4 (`type_media` CTE) |
| `src/sextant/application/resolve/effective_annotations.py` | Task 5 (`inherited_rows_over` gains `sibling_fqns`; `_resolve_method` returns its source) |
| `src/sextant/application/resolve/conditions.py` (new) | Task 7: `AnnotationArg`, `parse_condition`, `holds`, `annotation_index`, `enclosing_type_of` — shared by Tasks 6, 8, 9 |
| `src/sextant/application/resolve/shapes/contracts.py` | Task 6 (`sole_unbound`, `_body_parameter` with owner/path), Task 8 (`wrappers[].when` at rooting) |
| `src/sextant/application/resolve/shapes/expansion.py` | Task 8 (`_Rules.conditional_wrappers`) |
| `src/sextant/application/resolve/protocol_hint.py` | Task 9 (`hint_when`, `hint_annotations`) |
| `src/sextant/catalogs/jakarta-jaxrs.yml`, `javax-jaxrs.yml`, `quarkus-rest.yml` (new) | Task 10 |
| `src/sextant/catalogs/spring-kafka.yml` | Task 11 |
| `src/sextant/catalogs/micronaut-jms.yml`, `micronaut-jms-producer.yml` | Task 12 |
| `tests/application/test_endpoints.py`, `tests/application/test_effective_annotations.py` (or the file that tests `inherited_rows_over` — `grep -ln inherited_rows_over tests/application/*.py`), `tests/application/test_contracts.py` (or the file testing `_body_parameter` — `grep -ln "_body_parameter\|sole_unannotated" tests/application/*.py`), `tests/application/test_protocol_hint.py` (`grep -ln apply_protocol_hints tests/application/*.py`), `tests/application/test_conditions.py` (new) | engine tests and near-misses, Tasks 3–9 |
| `scripts/guard_check.py` | guards: `annotation_driven.sibling-media-only-when-own-absent`, `effective_annotations.siblings-inherit-all-or-nothing`, `contracts.sole-unbound-measures-bound-by`, `contracts.implicit-path-variable-reads-the-composed-path`, `contracts.conditional-wrapper-needs-its-condition`, `protocol_hint.hint-when-reads-the-owner` |
| `docs/components/D02-catalog-schema.md` | Tasks 3–9 |
| `docs/COVERAGE.md`, `docs/java-kotlin-delivery-list.md`, `CHANGELOG.md`, `docs/open-issues.md` | Task 13 (COVERAGE line 3222's wording also in Task 12) |

---

### Task 1: fixtures and strict-xfail tests — every case the group closes, failing first

**Files:**
- Modify: `fixtures/orders-spring7/pom.xml`, `fixtures/orders-quarkus/pom.xml`, `fixtures/orders-service/pom.xml`, `fixtures/orders-micronaut/pom.xml`
- Create: the fixture classes named in the file map
- Modify: `fixtures/orders-service/src/main/java/com/acme/orders/messaging/OrderEventsListener.java`, `fixtures/orders-micronaut/src/main/java/com/acme/mn/OrderMessaging.java`
- Test: `tests/e2e/test_rest_inbound_delivered.py`, `tests/e2e/test_messaging_micronaut_delivered.py`, `tests/application/test_pipeline.py`

**Interfaces:**
- Produces: the fixture classes and the eleven strict-xfail tests Tasks 10–12 flip. Fixture-total tests move additively here.

**What the spec says (§3e, §5a, §5b):** the existing `OrderResource.java` is unchanged; new cases are one class each; every test is `@pytest.mark.xfail(strict=True, reason=…)` until its catalog lands.

- [ ] **Step 1: dependencies.**

`fixtures/orders-spring7/pom.xml` — beside the existing `jakarta.ws.rs-api` dependency add, same scope:
```xml
<dependency><groupId>javax.ws.rs</groupId><artifactId>javax.ws.rs-api</artifactId><version>2.1.1</version></dependency>
<dependency><groupId>jakarta.validation</groupId><artifactId>jakarta.validation-api</artifactId><version>3.0.2</version></dependency>
```
`fixtures/orders-quarkus/pom.xml` — add a `dependencyManagement` import of `io.quarkus:quarkus-bom:3.17.5` (`<type>pom</type><scope>import</scope>`; it is in `~/.m2` already), then dependencies `io.quarkus:quarkus-rest` (with the same all-exclusions pattern the existing `quarkus-reactive-routes` entry uses), `jakarta.ws.rs:jakarta.ws.rs-api`, `org.jboss.resteasy.reactive:resteasy-reactive-common` (for `@RestStreamElementType`, `@RestForm`, `@RestPath`), `io.smallrye.reactive:mutiny` (for `Multi`), `io.vertx:vertx-web` (for `RoutingContext`) — versions from the BOM, no `<version>` element. Compile once online: `cd fixtures/orders-quarkus && mvn -q compile`.
`fixtures/orders-service/pom.xml` — add `jakarta.ws.rs:jakarta.ws.rs-api:4.0.0` (`provided`).
`fixtures/orders-micronaut/pom.xml` — beside `micronaut-jms-core` add `io.micronaut.jms:micronaut-jms-sqs:4.2.0` and `io.micronaut.jms:micronaut-jms-activemq-classic:4.2.0`, same scope and exclusion pattern as the existing entry.

- [ ] **Step 2: the JAX-RS fixtures in `orders-spring7`, package `com.acme.jaxrs`.**

```java
// LegacyResource.java — the `javax.ws.rs` spelling (JAX-RS 2.1, Jakarta EE 8 and every
// 2.x-era Jersey/RESTEasy project). Same shape as OrderResource, other package.
package com.acme.jaxrs;

import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;

@Path("/legacy/orders")
@Produces(MediaType.APPLICATION_JSON)
public class LegacyResource {
    @GET
    public String list() { return "[]"; }

    @POST
    public String create(String body) { return body; }

    @GET
    @Path("/{id}")
    public String byId(@PathParam("id") String id) { return id; }
}
```
```java
// ValidatedResource.java — M2's Java case: the entity parameter carries a Bean Validation
// annotation. To JAX-RS `@Valid` is not a parameter-binding annotation, so `order` is the
// body; under the shipped `sole_unannotated` rule any annotation disqualified it.
package com.acme.jaxrs;

import jakarta.validation.Valid;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;

@Path("/validated/orders")
public class ValidatedResource {
    public static class Order { public String sku; public int quantity; }

    @POST
    public Order create(@Valid Order order) { return order; }
}
```
```java
// OrdersApi.java + OrdersResource.java — M3's generated-interface pattern: every annotation
// on the interface, none on the class. JAX-RS §3.6 and all three implementations make the
// class a root resource and inherit the interface method's WHOLE annotation set.
package com.acme.jaxrs;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.sse.SseEventSink;
import java.util.List;

@Path("/api/orders")
public interface OrdersApi {
    @GET
    List<String> list();

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    String byId(@PathParam("id") String id);

    @GET
    @Path("/events")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    void events(@Context SseEventSink sink);
}
```
```java
package com.acme.jaxrs;

import jakarta.ws.rs.sse.SseEventSink;
import java.util.List;

public class OrdersResource implements OrdersApi {
    @Override public List<String> list() { return List.of(); }
    @Override public String byId(String id) { return id; }
    @Override public void events(SseEventSink sink) {}
}
```

- [ ] **Step 3: the Kotlin fixture in `orders-service`, `src/main/kotlin/com/acme/orders/jaxrs/KotlinOrderResource.kt`.**

```kotlin
// M2's Kotlin case: kotlinc writes `@org.jetbrains.annotations.NotNull` on `order`, and the
// extractor records it (retention: class). Under `sole_unannotated` that erased the body.
package com.acme.orders.jaxrs

import jakarta.ws.rs.POST
import jakarta.ws.rs.Path

@Path("/kt/orders")
class KotlinOrderResource {
    class KtOrder(val sku: String, val quantity: Int)

    @POST
    fun create(order: KtOrder): KtOrder = order
}
```

- [ ] **Step 4: the Quarkus fixture, `fixtures/orders-quarkus/src/main/java/com/acme/quarkus/`.**

```java
// Upload.java — a parameter CONTAINER: no annotation on the class, bound fields inside.
// Quarkus's ResteasyReactiveParameterContainerScanner makes any parameter of this type a
// set of form values, never the body.
package com.acme.quarkus;

import org.jboss.resteasy.reactive.RestForm;

public class Upload {
    @RestForm public String description;
    @RestForm public String fileName;
}
```
```java
// OrderResource.java — the five Quarkus REST cases the spec §3e names. The class keeps
// @Path (R1: Quarkus does not relax it for servers).
package com.acme.quarkus;

import io.smallrye.mutiny.Multi;
import io.vertx.ext.web.RoutingContext;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.jboss.resteasy.reactive.RestStreamElementType;

@Path("/q/orders")
public class OrderResource {
    public static class Order { public String sku; }
    public static class OrderEvent { public String sku; }

    // implicit path binding: `id` matches `{id}`, so it is a path param and there is no body
    @GET
    @Path("/{id}")
    public Order byId(String id) { return new Order(); }

    // implicit path binding beside a real body
    @PUT
    @Path("/{id}")
    public Order replace(String id, Order order) { return order; }

    // container: no body
    @POST
    @Path("/upload")
    public String upload(Upload form) { return form.fileName; }

    // Vert.x context type, injected without @Context: no body
    @GET
    @Path("/whoami")
    public String whoami(RoutingContext rc) { return rc.normalizedPath(); }

    // M1: no @Produces — the element type alone makes this SSE
    @GET
    @Path("/events")
    @RestStreamElementType(MediaType.APPLICATION_JSON)
    public Multi<OrderEvent> events() { return Multi.createFrom().empty(); }

    // the explicit SSE form, for the media hint
    @GET
    @Path("/ticks")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    public Multi<String> ticks() { return Multi.createFrom().empty(); }
}
```

- [ ] **Step 5: the Kafka and Micronaut fixtures.**

In `OrderEventsListener.java`, after `onBatch`:
```java
    // `kafka-batch-generics`: `batch = "true"` makes this a BATCH listener — one element per
    // record, so the topic's wire payload is OrderEvent and `List` is the container's
    // envelope. `onBatch` above, with no attribute, is a RECORD listener taking a list: its
    // wire payload IS the list. Same parameter type, two contracts (spec §5a).
    @KafkaListener(topics = "order-batch-records", batch = "true")
    public void onRecords(List<OrderEvent> events) {
    }

    // Spring parses the attribute with Boolean.parseBoolean — case-insensitive (M5).
    @KafkaListener(topics = "order-batch-records-upper", batch = "TRUE")
    public void onRecordsUpper(List<OrderEvent> events) {
    }
```
In `OrderMessaging.java`, add imports `io.micronaut.jms.sqs.configuration.SqsConfiguration`, `io.micronaut.jms.activemq.classic.configuration.ActiveMqClassicConfiguration` and three nested types:
```java
    // JMS over SQS: the listener is bound to the SQS module's connection factory by its bean
    // NAME, the framework's own constant. The wire is SQS; `@Queue` names the SQS queue.
    @JMSListener(SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME)
    public static class SqsConsumer {
        @Queue("mn.orders.sqs")
        public void onQueued(String body) {}
    }

    @JMSProducer(SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME)
    public interface SqsSender {
        @Queue("mn.orders.sqs-out")
        void send(String body);
    }

    // The negative: another broker's constant stays `jms`.
    @JMSListener(ActiveMqClassicConfiguration.CONNECTION_FACTORY_BEAN_NAME)
    public static class ClassicConsumer {
        @Queue("mn.orders.classic")
        public void onQueued(String body) {}
    }
```
Compile all four modules (`mvn -q compile`, online once where a dependency is new).

- [ ] **Step 6: the strict-xfail tests.** All `@pytest.mark.xfail(strict=True, reason="<item>: <one sentence naming the missing word>; Groups B/C spec §<n>")`. Leave the two existing JAX-RS xfails exactly as they are.

In `tests/e2e/test_rest_inbound_delivered.py`, using the existing `spring7` fixture (full rows) and `spring7_routes`:
```python
def _spring7_row(endpoints: list[dict], method: str, path: str) -> dict:
    rows = [r for r in endpoints if r["method"] == method and r["path"] == path and r["direction"] == "inbound"]
    assert len(rows) == 1, f"{method} {path}: {len(rows)} rows; paths: {sorted(r['path'] for r in endpoints)}"
    return rows[0]


@pytest.mark.xfail(strict=True, reason="javax-jaxrs: no catalog reads the javax.ws.rs spelling; spec §3a")
def test_the_javax_spelling_derives_the_same_operations(spring7_routes):
    expected = {("http", "GET", "/legacy/orders"), ("http", "POST", "/legacy/orders"),
                ("http", "GET", "/legacy/orders/{id}")}
    assert expected <= spring7_routes, sorted(expected - spring7_routes)


@pytest.mark.xfail(strict=True, reason="quarkus-jaxrs (M2): sole_unannotated disqualifies a @Valid body; spec §4")
def test_a_validated_entity_parameter_is_still_the_body(spring7):
    endpoints, _ = spring7
    row = _spring7_row(endpoints, "POST", "/validated/orders")
    assert row["request_shape"] is not None
    assert json.loads(row["request_shape"])["shape_id"].endswith("ValidatedResource$Order#")


@pytest.mark.xfail(strict=True, reason="quarkus-jaxrs (M3): an implementor inherits the mapping but not the sibling @Path/@Produces; spec §3b word 3")
def test_a_class_implementing_a_path_interface_derives_the_interfaces_operations(spring7):
    endpoints, _ = spring7
    assert {(r["method"], r["path"]) for r in endpoints if r["path"].startswith("/api/orders")} == {
        ("GET", "/api/orders"), ("GET", "/api/orders/{id}"), ("GET", "/api/orders/events")}
    by_id = _spring7_row(endpoints, "GET", "/api/orders/{id}")
    assert by_id["produces"] == '["application/json"]'
    assert by_id["handler"].endswith("OrdersResource#byId(sig_" + by_id["handler"].split("sig_")[1])  # the IMPLEMENTOR handles it
    assert _spring7_row(endpoints, "GET", "/api/orders/events")["protocol"] == "sse"


@pytest.mark.xfail(strict=True, reason="jaxrs-sse (word 1): produces is read off no sibling; spec §3b")
def test_jaxrs_media_comes_from_the_sibling_and_the_class_default(spring7):
    endpoints, _ = spring7
    assert _spring7_row(endpoints, "GET", "/jaxrs/orders")["produces"] == '["application/json"]'   # class-level @Produces
    assert _spring7_row(endpoints, "POST", "/jaxrs/orders")["consumes"] == '["application/json"]'  # method-level @Consumes
```
Using the existing Quarkus fixture (`QUARKUS`, line 415; add a module fixture `quarkus_endpoints` returning full rows exactly as `spring7` does, if the existing one returns only routes):
```python
@pytest.mark.xfail(strict=True, reason="quarkus-jaxrs (M4): implicit path/container/context bindings; spec §4")
def test_quarkus_rest_binds_the_body_the_way_quarkus_does(quarkus_endpoints):
    def row(method, path):
        return next(r for r in quarkus_endpoints if r["method"] == method and r["path"] == path)
    assert row("GET", "/q/orders/{id}")["request_shape"] is None          # `id` is the path variable
    assert json.loads(row("PUT", "/q/orders/{id}")["request_shape"])["shape_id"].endswith("OrderResource$Order#")
    assert row("POST", "/q/orders/upload")["request_shape"] is None       # container
    assert row("GET", "/q/orders/whoami")["request_shape"] is None        # RoutingContext


@pytest.mark.xfail(strict=True, reason="quarkus-jaxrs (M1): @RestStreamElementType implies SSE; spec §3c")
def test_quarkus_element_type_alone_makes_a_stream_sse(quarkus_endpoints):
    protocols = {r["path"]: r["protocol"] for r in quarkus_endpoints if r["direction"] == "inbound"}
    assert protocols["/q/orders/events"] == "sse"
    assert protocols["/q/orders/ticks"] == "sse"
```
In `tests/application/test_pipeline.py`, beside `test_a_batch_listeners_request_shape_is_an_array` (which stays):
```python
@pytest.mark.xfail(strict=True, reason="kafka-batch-generics: wrappers are unconditional; spec §5a")
@pytest.mark.parametrize("topic", ["order-batch-records", "order-batch-records-upper"])
def test_a_batch_true_listener_publishes_the_element_not_the_list(resolved_fixture, topic):
    """`batch = "true"` (and `"TRUE"`: Spring parses it with Boolean.parseBoolean): one
    element per record, so the wire payload is OrderEvent and `List` is the envelope."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", topic)
    descriptor = json.loads(row["request_shape"])
    assert descriptor["wire_type"] == "object"
    assert descriptor["shape_id"] == "com/acme/orders/contracts/OrderEvent#"


@pytest.mark.xfail(strict=True, reason="quarkus-jaxrs (M2): kotlinc's @NotNull erases the body under sole_unannotated; spec §4")
def test_a_kotlin_jaxrs_body_under_kotlincs_notnull_keeps_its_contract(resolved_fixture):
    _, report = resolved_fixture
    [row] = [r for r in report.endpoints if r["path"] == "/kt/orders" and r["method"] == "POST"]
    assert json.loads(row["request_shape"])["shape_id"].endswith("KotlinOrderResource$KtOrder#")
```
(`report.endpoints` — use whatever accessor the neighbouring HTTP tests in that file read rows from; `grep -n '"/v1/orders"' tests/application/test_pipeline.py` shows it.)

In `tests/e2e/test_messaging_micronaut_delivered.py`, using `messaging_rows` (`(protocol, direction, path)` triples):
```python
@pytest.mark.xfail(strict=True, reason="micronaut-jms-over-sqs: protocol_hint has no attribute condition; spec §5b")
def test_micronaut_jms_over_sqs_is_sqs_on_both_sides(messaging_rows):
    assert {("sqs", "inbound", "mn.orders.sqs"), ("sqs", "outbound", "mn.orders.sqs-out")} <= messaging_rows
    assert ("jms", "inbound", "mn.orders.sqs") not in messaging_rows


def test_micronaut_jms_on_another_broker_stays_jms(messaging_rows):
    """Not xfail: ActiveMQ Classic's constant is not SQS's, and the existing pair is untouched."""
    assert {("jms", "inbound", "mn.orders.classic"), ("jms", "inbound", "mn.orders.queue"),
            ("jms", "outbound", "mn.orders.audit")} <= messaging_rows
```

- [ ] **Step 7: run, gate, commit.** `uv run pytest tests/e2e/test_rest_inbound_delivered.py tests/e2e/test_messaging_micronaut_delivered.py tests/application/test_pipeline.py -q` — every new xfail reports XFAIL (a new test that PASSES here is a wrong test: strict xfail fails the run). Recount the four fixture-total tests. Full gate. Commit:

```bash
git add fixtures/orders-spring7 fixtures/orders-quarkus/pom.xml fixtures/orders-quarkus/src fixtures/orders-service/pom.xml fixtures/orders-service/src fixtures/orders-micronaut/pom.xml fixtures/orders-micronaut/src tests/e2e/test_rest_inbound_delivered.py tests/e2e/test_messaging_micronaut_delivered.py tests/application/test_pipeline.py tests/e2e/test_vertical_slice.py tests/cli/test_app.py tests/application/test_asm_scanner.py
git commit -m "test(fixtures): every case Groups B and C close, failing first — javax and interface JAX-RS, @Valid and Kotlin bodies, five Quarkus REST shapes, batch=true/TRUE listeners, JMS over SQS on both sides (B/C Task 1)"
```

---

### Task 2: probes P1–P4 as `scripts/probes/` files

**Files:**
- Create: `scripts/probes/cp18_jaxrs_api_and_implementations.md`, `cp19_quarkus_rest.md`, `cp20_spring_kafka_batch.md`, `cp21_micronaut_jms_sqs.md`

**Interfaces:**
- Produces: the `by:` paths every catalog's `measured:` block cites in Tasks 10–12; the quoted rules Tasks 3–9 cite in their D02 paragraphs.

**What the spec says (§7):** every row a command, its output quoted, the claim it settles named. The self-review ran these informally; this task makes them the record.

- [ ] **Step 1: fetch what `~/.m2` lacks** into the scratchpad (never the repo), from `https://repo1.maven.org/maven2/`: `javax/ws/rs/javax.ws.rs-api/2.1.1/*.jar`, `jakarta/ws/rs/jakarta.ws.rs-api/3.1.0/*.jar`, `org/jboss/resteasy/resteasy-core/6.2.12.Final/*.jar`, `io/quarkus/quarkus-rest/3.39.4/*.jar`, `io/quarkus/quarkus-rest-deployment/3.39.4/*.jar`, `io/quarkus/resteasy/reactive/resteasy-reactive-common/3.39.4/*.jar`; and the sources `ResteasyReactiveScanner.java`, `EndpointIndexer.java`, `ResteasyReactiveDotNames.java`, `ResteasyReactiveParameterContainerScanner.java` from `raw.githubusercontent.com/quarkusio/quarkus/3.39.4/independent-projects/resteasy-reactive/common/processor/src/main/java/org/jboss/resteasy/reactive/common/processor/…`. Already in `~/.m2`: `jakarta.ws.rs-api` 4.0.0, `jersey-server` 4.0.0, `spring-kafka` 3.1.4 and 4.1.1, `micronaut-jms-core` 4.2.0, `micronaut-jms-sqs` 4.2.0, `quarkus-bom` 3.17.5.

- [ ] **Step 2: `cp18_jaxrs_api_and_implementations.md`.** Rows, each `command → quoted output → claim`:
  - 1a–1g: `javap -cp <api jar> jakarta.ws.rs.{GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS}` → empty interface body → *verb annotations declare no attributes* (spec §3a `path_from: []`). Repeat on 3.1.0 and the `javax` 2.1.1 jar.
  - 2a–2c: `javap -v -cp <api jar> jakarta.ws.rs.{Path,Produces,Consumes} | grep -A1 'annotation.Target('` and the `public abstract` line → `@Target({TYPE, METHOD})`, `value(): String` / `String[]`.
  - 3: `javap -v … jakarta.ws.rs.GET | grep -A2 'HttpMethod('` → `@HttpMethod("GET")`; `javap -v … jakarta.ws.rs.HttpMethod` → `@Target(ANNOTATION_TYPE)`, `value(): String` (the custom-verb boundary, §3d).
  - 4: `javap -constants -cp <api jar> jakarta.ws.rs.core.MediaType | grep -E 'SERVER_SENT_EVENTS =|APPLICATION_JSON ='`.
  - 5: `javap -c -p -cp <jersey-server jar> org.glassfish.jersey.server.model.IntrospectionModeller | grep -B2 -A12 resolveProducedTypes` → the method's `@Produces` when `isAnnotationPresent`, else the class default list → *method-over-class* (§3b word 2).
  - 6a/6b: `javap -c -p -cp <jersey-server jar> org.glassfish.jersey.server.model.internal.ModelHelper | sed -n '/getAnnotatedResourceClass/,/^$/p'` and `javap -c -p -cp <resteasy-core jar> org.jboss.resteasy.util.AnnotationResolver | sed -n '/getClassWithAnnotation/,/^$/p'` → both `isAnnotationPresent` on the class, then `getInterfaces()`, then `getSuperclass()` → *a `@Path` interface/superclass makes the implementor a root resource* (§3b word 3).
  - 7: the binding-annotation list — `unzip -l <api jar> | grep -E 'rs/(Path|Query|Header|Cookie|Form|Matrix|Bean)Param|DefaultValue|core/Context|container/Suspended'` — and the `@Context`-injectable type list from JAX-RS 3.1 §9.2 with each class confirmed present in the jar (`unzip -l … | grep -E 'core/(UriInfo|HttpHeaders|Request|SecurityContext|Configuration|Application)|ext/Providers|container/ResourceContext|sse/(Sse|SseEventSink)'`) → `bound_by` and `excludes` for `jakarta-jaxrs.yml`.
  - 8: JAX-RS §3.6 quoted from the specification text ("if a subclass or implementation method has any JAX-RS annotations then all of the annotations on the superclass or interface method are ignored") → the all-or-nothing rule.

- [ ] **Step 3: `cp19_quarkus_rest.md`.**
  - 1: `sed -n 232,260p ResteasyReactiveScanner.java` and `sed -n 296,330p` and `sed -n 340,395p` → root resources from class `@Path` (247-254) and `@Path` interfaces' implementors (309-316); HTTP-method-only classes are `possibleSubResources` (361-390); line 344's "no PATH whatsoever" is `clientInterfaces` → *the gate stays; R1*.
  - 2: `sed -n 710,740p EndpointIndexer.java` → element type from method else class (713-717); `produces = [SERVER_SENT_EVENTS]` when no `@Produces` and element type present (720-723); class-level `@Produces` fallback (725); `sed -n 860,870p` → `getStreamAnnotationValue` reads `REST_STREAM_ELEMENT_TYPE` then `REST_SSE_ELEMENT_TYPE` → *`hint_annotations`, both fqns* (§3c).
  - 3: `sed -n 153,158p EndpointIndexer.java` → `DEFAULT_CONTEXT_TYPES`; `grep -rn addContextTypes` over the deployment jar's classes (`javap -c -p` on `io.quarkus.resteasy.reactive.server.deployment.ResteasyReactiveProcessor` or wherever `grep -l addContextTypes` lands after `unzip`) → the Vert.x additions → `excludes` for `quarkus-rest.yml`.
  - 4: `sed -n 1380,1416p EndpointIndexer.java` → the order: annotation → context type → container type → path-variable name (1393-1399, message quoted) → body; `sed -n 14,31p ResteasyReactiveParameterContainerScanner.java` and `sed -n 265,268p ResteasyReactiveDotNames.java` → the container rule and its annotation set → `implicit_bindings` and the Quarkus additions to `bound_by` (§4).
  - 5: `curl -s https://repo1.maven.org/maven2/io/quarkus/quarkus-rest/maven-metadata.xml | grep -o '<version>3\.[0-9]*\.0</version>' | head -3` and the same for `quarkus-resteasy-reactive` → the relocation version → both `detect.coordinates`.
  - 6: `grep -n "AnnotationStore\|getAnnotation(" EndpointIndexer.java | head` and the `AnnotationStore` class → whether an implementor method with an own `@Produces` still inherits the interface's `@GET` (§3b word 3's boundary). Record the answer either way; if Quarkus merges per annotation, `quarkus-rest.yml` states it in a comment and COVERAGE names it.

- [ ] **Step 4: `cp20_spring_kafka_batch.md`.** For each of 3.1.4 and 4.1.1 (`K=~/.m2/repository/org/springframework/kafka/spring-kafka/$v/spring-kafka-$v.jar`):
  - 1: `javap -v -cp $K org.springframework.kafka.annotation.KafkaListener | grep -A4 'String batch()'` → `String`, `AnnotationDefault` empty string.
  - 2: `javap -c -p -cp $K org.springframework.kafka.annotation.KafkaListenerAnnotationBeanPostProcessor | grep -B6 -A3 'KafkaListener.batch:()'` → `StringUtils.hasText` → `ifeq` → `Boolean.parseBoolean` → `setBatchListener(Z)` — quote the bytecode → *`parses_true`: no resolution, case-insensitive, empty is "factory decides"* (§2, §5a).
  - 3: `javap -p -cp $K org.springframework.kafka.listener.adapter.BatchMessagingMessageListenerAdapter | grep onMessage` → the accepted shapes.
  - 4: `javap -c -p -cp $K org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory | grep -i batch` → `setBatchListener` on the FACTORY, no annotation read → *config-driven batching leaves the attribute empty; boundary*.
  - 5: `grep -rn "messaging.Message\b" src/sextant/catalogs/spring-kafka*.yml` → whether `Message<T>` is declared as a wrapper anywhere (it is not; record that `List<Message<T>>` stays a disclosed open type unless Task 11 adds the row).

- [ ] **Step 5: `cp21_micronaut_jms_sqs.md`.** `C=~/.m2/repository/io/micronaut/jms/micronaut-jms-core/4.2.0/micronaut-jms-core-4.2.0.jar`, `S=…/micronaut-jms-sqs/4.2.0/micronaut-jms-sqs-4.2.0.jar`, the two broker jars from the scratchpad:
  - 1a/1b: `javap -v -cp $C io.micronaut.jms.annotations.{JMSListener,JMSProducer} | grep -E 'public abstract|Retention|Target'` → `value(): String` (listener also `successHandlers`, `errorHandlers`), **no `connectionFactory`**, `RUNTIME`, `TYPE` → R2.
  - 2: `javap -c -p -cp $C io.micronaut.jms.configuration.AbstractJMSListenerMethodProcessor | grep -E 'JMSListener|getRequiredValue|byName'` → `getAnnotation(JMSListener).getRequiredValue(String)` … `Qualifiers.byName` → *`value` is the factory bean name*.
  - 3a–3c: `javap -constants -cp $S io.micronaut.jms.sqs.configuration.SqsConfiguration | grep 'static final'` → `"sqsJmsConnectionFactory"`; same on `ActiveMqClassicConfiguration` → `"activeMqConnectionFactory"`, `ActiveMqArtemisConfiguration` → `"activeMqArtemisConnectionFactory"`; `javap -v -cp $S 'io.micronaut.jms.sqs.configuration.$SqsConfiguration$SqsJmsConnectionFactory0$Definition' | grep -E 'sqsJmsConnectionFactory|Named'` → the bean is `@Named` with that literal.
  - 4: after Task 1's compile: `javap -v -cp fixtures/orders-micronaut/target/classes 'com.acme.mn.OrderMessaging$SqsConsumer' | grep -B2 -A3 JMSListener` → the class file carries `value="sqsJmsConnectionFactory"` → *the constant inlines; `name: value`*.

- [ ] **Step 6: commit.**

```bash
git add scripts/probes/cp18_jaxrs_api_and_implementations.md scripts/probes/cp19_quarkus_rest.md scripts/probes/cp20_spring_kafka_batch.md scripts/probes/cp21_micronaut_jms_sqs.md
git commit -m "docs(probes): CP-18..21 — JAX-RS API and two implementations, Quarkus REST's scanner and indexer, Spring Kafka's batch parse, Micronaut JMS's factory-name attribute (B/C Task 2)"
```

---

### Task 3: `produces_from_siblings` / `consumes_from_siblings` — media read off a sibling annotation

**Files:**
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py` (`_sibling_sources` at 628, `params_for` at 97)
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql` (`catalog_params` STRUCT at ~281; new CTEs beside `sibling_names` at 401–412; `declared` at ~440–500)
- Modify: `docs/components/D02-catalog-schema.md` (the `path_from_siblings` bullet block, ~995–1020)
- Test: `tests/application/test_endpoints.py`; `scripts/guard_check.py`

**Interfaces:**
- Consumes: `_sibling_sources(catalog, mapping)` (returns `[{ordinal, annotation, arg}]` for `path_from_siblings`); the `sibling_path_sources`/`sibling_names` CTE pattern; `declared`'s `produces_list`/`consumes_list` columns.
- Produces: `_sibling_sources(catalog, mapping, key: str = "path_from_siblings")`; params `produces_from_siblings`, `consumes_from_siblings` (same row shape); `declared.produces_list = coalesce(<own alias read>, sm_p.found)`, likewise consumes.

**What the spec says (§3b word 1):** consulted where every `produces_from`/`consumes_from` alias is absent; ordered; scalar-or-array; first present wins; sorted and de-duplicated downstream as today.

- [ ] **Step 1: the failing engine test.** In `tests/application/test_endpoints.py`, extend `_gate_facts` with one optional parameter `sibling_annotations: dict[str, dict] | None = None` — extra `AnnotationFact`s on the handler symbol, written exactly as the mapping annotation's fact is written in that helper (same `document_id`, `target=handler`, `use={"annotation": fqn, "args": args}`, `retention` as the existing one). Add a helper returning media:

```python
def _gate_media(tmp_path: Path, catalog_id: str, **facts) -> list[tuple]:
    _gate_facts(tmp_path / "facts", **facts)
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id)
    if catalog.detect_required:
        write_fixture_module_fact_with(tmp_path / "facts", catalog.detect_coordinates[:1])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args", "typed_signatures", "type_annotations"})
    rows = [(r["method"], r["path"], r["produces"], r["consumes"]) for r in workspace.query("endpoints")]
    workspace.close()
    return rows
```
The test needs a catalog declaring the word; until Task 10 there is none, so write a **synthetic catalog** the way the engine tests that exercise a not-yet-shipped word do (`grep -n "Catalog(" tests/application/test_endpoints.py | head` — a `Catalog(...)` built in the test with `id="test-siblings"`, `style="annotation_driven"`, `protocol="http"`, `direction="inbound"`, `matches={...}`), and a variant of `_gate_media` taking a `Catalog` object instead of an id (`_gate_media_for(tmp_path, catalog, **facts)`). The mapping:
```python
_SIBLING_MEDIA_MATCHES = {
    "type_annotation": "com.acme.rs.Path",
    "request_body": {"annotation": "com.acme.rs.Body", "fallback": "none"},
    "mapping": {
        "prefix_annotation": "com.acme.rs.Path", "prefix_from": ["value"], "path_separator": "/",
        "path_from": [], "path_from_siblings": [{"annotation": "com.acme.rs.Path", "arg": "value"}],
        "produces_from_siblings": [{"annotation": "com.acme.rs.Produces", "arg": "value"}],
        "consumes_from_siblings": [{"annotation": "com.acme.rs.Consumes", "arg": "value"}],
        "method_from": "method", "all_methods": [],
        "annotations": [{"fqn": "com.acme.rs.GET", "method": ["GET"]}],
    },
}


def test_media_is_read_off_a_sibling_when_the_matched_annotation_carries_none(tmp_path: Path):
    """Spec §3b word 1: `@GET` declares no attribute at all (CP-18 row 1), so produces/consumes
    come from the sibling `@Produces`/`@Consumes` on the same method, scalar-or-array."""
    rows = _gate_media_for(
        tmp_path, _catalog("test-siblings", _SIBLING_MEDIA_MATCHES),
        owner_kind=ConstructKind.CLASS,
        type_annotations={"com/acme/rs/Path#": {"value": "/orders"}},
        method_annotation="com/acme/rs/GET#", method_args={},
        sibling_annotations={"com/acme/rs/Path#": {"value": "/{id}"},
                             "com/acme/rs/Produces#": {"value": ["text/plain", "application/json"]},
                             "com/acme/rs/Consumes#": {"value": "application/xml"}},
    )
    assert rows == [("GET", "/orders/{id}", '["application/json","text/plain"]', '["application/xml"]')]
```
Run → FAIL (`produces` NULL; the key is unknown or ignored).

- [ ] **Step 2: Python.** In `annotation_driven.py`, give `_sibling_sources` a `key: str = "path_from_siblings"` parameter, use `key` in `mapping.get(key)` and in the error message (`f"`mapping.{key}`"`), and in `params_for` add beside `path_from_siblings`:
```python
        # Spec 2026-09-18 §3b word 1: the media siblings — `@Produces`/`@Consumes` on a
        # JAX-RS method sit beside a verb annotation that declares no attribute at
        # all (CP-18 row 1). Same closed shape and order rule as the path siblings;
        # read only where every `produces_from`/`consumes_from` alias is absent.
        "produces_from_siblings": _sibling_sources(catalog, mapping, "produces_from_siblings"),
        "consumes_from_siblings": _sibling_sources(catalog, mapping, "consumes_from_siblings"),
```

- [ ] **Step 3: SQL.** In `derive_endpoints.sql`: add to the `catalog_params` STRUCT (line ~281, after `path_from_siblings`) `produces_from_siblings STRUCT(ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[], consumes_from_siblings STRUCT(ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[]`. After `sibling_names` add:
```sql
-- Spec 2026-09-18 §3b word 1: the media twins of the two CTEs above — same shape, same
-- "first present wins" over the catalog's ordinal, grouped by TARGET because the
-- annotation carrying the media is not the mapping annotation. Empty for every catalog
-- declaring no media sibling, so the LEFT JOINs in `declared` reduce to what they were.
sibling_produces_sources AS (
    SELECT u.catalog_id AS catalog_id, s.ordinal AS ordinal, s.annotation AS annotation, s.arg AS arg
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.produces_from_siblings) AS s FROM catalog_params cp) u
),
sibling_produces AS (
    SELECT sp.catalog_id AS catalog_id, a.target AS target,
           min_by(coalesce(TRY_CAST(a.args -> sp.arg AS VARCHAR[]), [a.args ->> sp.arg]), sp.ordinal) AS found
    FROM annotations_effective a
    JOIN sibling_produces_sources sp ON sp.annotation = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = sp.catalog_id)
    WHERE coalesce(a.args -> sp.arg ->> 0, a.args ->> sp.arg) IS NOT NULL
    GROUP BY sp.catalog_id, a.target
),
sibling_consumes_sources AS ( … identical, over cp.consumes_from_siblings … ),
sibling_consumes AS ( … identical, joining sibling_consumes_sources … ),
```
In `declared`, find where `sibling_names sn` is LEFT JOINed (`grep -n "LEFT JOIN sibling_names" derive_endpoints.sql`) and add beside it `LEFT JOIN sibling_produces smp ON smp.catalog_id = mc.catalog_id AND smp.target = a.target` and `LEFT JOIN sibling_consumes smc …`; wrap the two existing media reads (lines ~486–498) as `coalesce(<existing produces_list expression>, smp.found) AS produces_list` and `coalesce(<existing consumes_list expression>, smc.found) AS consumes_list`. The `member_declarations` UNION branch (line ~797, `CAST(NULL AS VARCHAR[]) AS produces_list`) is unchanged — a member carries no annotation to read a sibling off.

- [ ] **Step 4: run** the new test → PASS; run `tests/application/test_endpoints.py` whole → green; golden check (no catalog declares the word yet).

- [ ] **Step 5: the near-miss + guard.** A test identical to Step 1's but with `"com/acme/rs/GET#"` carrying its OWN `produces` attribute (`method_args={"produces": ["text/csv"]}` and the synthetic catalog also declaring `produces_from: ["produces"]`) → the own value wins, the sibling is not consulted: expect `'["text/csv"]'`. Mark `@pytest.mark.declines("test-siblings")` is not a shipped catalog — so mark it `@pytest.mark.pins("annotation_driven.sibling-media-only-when-own-absent")` and register the guard in `scripts/guard_check.py` with `Edit(path=_DERIVE_ENDPOINTS_SQL, find="coalesce(<the exact produces expression's first line>, smp.found) AS produces_list", replace="coalesce(smp.found, <…>) AS produces_list  -- guard disabled")` — the exact text is the line Step 3 wrote; a test that still passes with the sibling preferred is not measuring the order. (`_DERIVE_ENDPOINTS_SQL` — add the path constant beside the existing `_ARGUMENTS`/`_SINGLE_CALL` ones if none exists.)

- [ ] **Step 6: D02.** Under the `path_from_siblings` bullet block (~995), a sibling bullet: **`produces_from_siblings` / `consumes_from_siblings`** — same closed shape, same order rule, consulted where every `produces_from`/`consumes_from` alias is absent; forced by CP-18 row 1 (verb annotations declare no attribute); the media lands sorted/de-duplicated exactly as evidence kind (a) does; the class-level default is word 2 (Task 4), not this key.

- [ ] **Step 7: gate, commit.**
```bash
git add src/sextant/application/resolve/engines/annotation_driven.py src/sextant/storage/duckdb/derive_endpoints.sql docs/components/D02-catalog-schema.md tests/application/test_endpoints.py scripts/guard_check.py
git commit -m "feat(engine): produces_from_siblings / consumes_from_siblings — media read off a sibling annotation where the matched one carries none (B/C Task 3, spec §3b word 1)"
```

---

### Task 4: `type_media_from_siblings` — the class-level media default on a type-level sibling

**Files:**
- Modify: `annotation_driven.py` (`params_for`), `derive_endpoints.sql` (STRUCT, new `type_media` CTE, the `coalesce` at ~1314 and the LEFT JOIN block at ~1339), D02
- Test: `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: Task 3's helper and synthetic catalog; the `prefixes p` join keyed on `coalesce(m.gate_type, s.enclosing)`.
- Produces: param `type_media_from_siblings: {"produces": [rows], "consumes": [rows]}` → SQL STRUCT `type_media_from_siblings STRUCT(column VARCHAR, ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[]` (flattened, `column` ∈ `produces`/`consumes`); CTE `type_media(catalog_id, type_symbol, produces_list, consumes_list)`; final `coalesce(m.produces_list, p.produces_list, tm.produces_list)`.

**What the spec says (§3b word 2):** method's declaration wins when non-empty, else the type's, never a union — Jersey `resolveProducedTypes`, Quarkus line 725 (CP-18 row 5, CP-19 row 2).

- [ ] **Step 1: failing test.** Same synthetic catalog plus `"type_media_from_siblings": {"produces": [{"annotation": "com.acme.rs.Produces", "arg": "value"}], "consumes": [{"annotation": "com.acme.rs.Consumes", "arg": "value"}]}`; facts: type annotations `{"com/acme/rs/Path#": {"value": "/orders"}, "com/acme/rs/Produces#": {"value": "application/json"}}`, method `@GET` with sibling `@Path("/{id}")` only → expect `("GET", "/orders/{id}", '["application/json"]', None)`. A second case where the method also carries `@Produces("text/plain")` → `'["text/plain"]'` (method wins, no union). Run → FAIL.

- [ ] **Step 2: Python.** In `params_for`:
```python
        "type_media_from_siblings": _type_media_sources(catalog, mapping),
```
with
```python
def _type_media_sources(catalog: Catalog, mapping: dict[str, Any]) -> list[dict[str, object]]:
    """`mapping.type_media_from_siblings` flattened to `{column, ordinal, annotation, arg}`
    rows — the class-level media default read off a TYPE-level sibling (spec 2026-09-18
    §3b word 2). Refused unless a mapping of `produces`/`consumes` to sibling lists."""
    declared = mapping.get("type_media_from_siblings")
    if declared is None:
        return []
    if not isinstance(declared, dict) or not declared or not set(declared) <= {"produces", "consumes"}:
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.type_media_from_siblings` must be a mapping "
            f"of `produces`/`consumes` to sibling-source lists — got {declared!r}"
        )
    rows: list[dict[str, object]] = []
    for column in ("produces", "consumes"):
        if column in declared:
            for source in _sibling_sources(catalog, {"_": declared[column]}, "_"):
                rows.append({"column": column, **source})
    return rows
```
(Reusing `_sibling_sources` for the shape check by handing it a one-key mapping; fix the error text so it names `type_media_from_siblings.<column>` — pass the display key through, e.g. add a `shown: str | None = None` argument used only in the message.)

- [ ] **Step 3: SQL.** STRUCT field; CTE after `prefixes`:
```sql
-- Spec 2026-09-18 §3b word 2: the class-level media default read off a TYPE-level sibling
-- (`@Produces` on a JAX-RS resource class). Keyed on the type so it joins exactly as
-- `prefixes` does; the combine below is coalesce — the method's declaration, else the
-- class's, never a union (Jersey `resolveProducedTypes`, Quarkus EndpointIndexer 725,
-- CP-18 row 5 / CP-19 row 2).
type_media_sources AS (
    SELECT u.catalog_id AS catalog_id, s.column AS column, s.ordinal AS ordinal, s.annotation AS annotation, s.arg AS arg
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.type_media_from_siblings) AS s FROM catalog_params cp) u
),
type_media AS (
    SELECT ts.catalog_id AS catalog_id, a.target AS type_symbol,
           min_by(CASE WHEN ts.column = 'produces' THEN coalesce(TRY_CAST(a.args -> ts.arg AS VARCHAR[]), [a.args ->> ts.arg]) END, ts.ordinal)
               FILTER (WHERE ts.column = 'produces') AS produces_list,
           min_by(CASE WHEN ts.column = 'consumes' THEN coalesce(TRY_CAST(a.args -> ts.arg AS VARCHAR[]), [a.args ->> ts.arg]) END, ts.ordinal)
               FILTER (WHERE ts.column = 'consumes') AS consumes_list
    FROM annotations_effective a
    JOIN type_media_sources ts ON ts.annotation = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = ts.catalog_id)
    WHERE coalesce(a.args -> ts.arg ->> 0, a.args ->> ts.arg) IS NOT NULL
    GROUP BY ts.catalog_id, a.target
),
```
In the final select: `LEFT JOIN type_media tm ON tm.catalog_id = m.catalog_id AND tm.type_symbol = coalesce(m.gate_type, s.enclosing)` beside `prefixes p`, and `coalesce(m.consumes_list, p.consumes_list, tm.consumes_list)`, `coalesce(m.produces_list, p.produces_list, tm.produces_list)`. (`type_media` only ever matches a TYPE symbol because the join key is the enclosing type; a method-level `@Produces` row in `annotations_effective` has a method target and never joins here.)

- [ ] **Step 4: run** → PASS both cases; golden check.

- [ ] **Step 5: D02** — beside Task 3's bullet: **`type_media_from_siblings`** `{produces: […], consumes: […]}`; combine rule; why a separate word from `prefix_annotation` media (the `prefix_from`/`peer_from` reason: `@Path` carries no media, `@Produces` no prefix).

- [ ] **Step 6: gate, commit.**
```bash
git add src/sextant/application/resolve/engines/annotation_driven.py src/sextant/storage/duckdb/derive_endpoints.sql docs/components/D02-catalog-schema.md tests/application/test_endpoints.py
git commit -m "feat(engine): type_media_from_siblings — the class-level media default read off a type-level sibling, method wins, never a union (B/C Task 4, spec §3b word 2)"
```

---

### Task 5: siblings inherit with the mapping, all or nothing (M3)

**Files:**
- Modify: `src/sextant/application/resolve/effective_annotations.py` (`inherited_rows_over` at 379, `_own_mapping` at 487, `_resolve_method` at 503)
- Modify: `annotation_driven.py::_synthetic_annotations` (1352) — pass the sibling fqns
- Modify: D02 (word 3 bullet beside Tasks 3–4's)
- Test: the file that tests `inherited_rows_over` (`grep -ln inherited_rows_over tests/application/*.py`); `scripts/guard_check.py`

**Interfaces:**
- Consumes: `inherited_rows_over(hierarchy, annotation_rows, mapping_fqns, prefix_fqns)`; `_resolve_method(...) -> tuple[str, dict] | None`.
- Produces: `inherited_rows_over(hierarchy, annotation_rows, mapping_fqns, prefix_fqns, sibling_fqns: frozenset[str] = frozenset())`; `_resolve_method(...) -> tuple[str, str, dict] | None` — `(source_method_symbol, annotation, args)`; the one caller adapts.

**What the spec says (§3b word 3):** for a catalog declaring any sibling list, an inherited mapping brings the ancestor method's sibling annotations (those in `path_from_siblings`/`produces_from_siblings`/`consumes_from_siblings`/`protocol_hint.hint_annotations`) with it — and only when the target carries **none** of the catalog's annotations of its own (mapping or sibling). Catalogs declaring no siblings keep today's mapping-only own-check byte-identically.

- [ ] **Step 1: failing test.** In the `inherited_rows_over` test file, following its existing fixture-building style (a `TypeHierarchy` from `type_hierarchy(implementation_rows, superclass_rows, method_declaration_rows)`), an interface `com/acme/OrdersApi#` with method `byId(sig_1).` carrying `{com/acme/rs/GET#: {}}`, `{com/acme/rs/Path#: {"value": "/{id}"}}`, `{com/acme/rs/Produces#: {"value": ["application/json"]}}`; class `com/acme/OrdersResource#` implementing it with an unannotated `byId(sig_1).`:
```python
def test_siblings_inherit_with_the_mapping_when_the_target_carries_nothing_of_its_own():
    rows = inherited_rows_over(hierarchy, annotation_rows, {"com/acme/rs/GET#"}, ["com/acme/rs/Path#"],
                               sibling_fqns=frozenset({"com/acme/rs/Path#", "com/acme/rs/Produces#"}))
    method = "com/acme/OrdersResource#byId(sig_1)."
    assert {(r["target"], r["annotation"], json.dumps(r["args"], sort_keys=True)) for r in rows if r["target"] == method} == {
        (method, "com/acme/rs/GET#", "{}"),
        (method, "com/acme/rs/Path#", '{"value": "/{id}"}'),
        (method, "com/acme/rs/Produces#", '{"value": ["application/json"]}'),
    }


def test_an_own_sibling_blocks_all_inheritance_for_that_method():
    """JAX-RS §3.6 (CP-18 row 8): ANY own JAX-RS annotation makes the interface's set
    ignored — so an implementor method carrying only its own @Produces inherits no
    mapping and derives nothing, which is the framework's answer."""
    # same hierarchy; the class method carries {com/acme/rs/Produces#: {"value": ["text/plain"]}}
    rows = inherited_rows_over(hierarchy2, annotation_rows2, {"com/acme/rs/GET#"}, ["com/acme/rs/Path#"],
                               sibling_fqns=frozenset({"com/acme/rs/Path#", "com/acme/rs/Produces#"}))
    assert [r for r in rows if r["target"] == "com/acme/OrdersResource#byId(sig_1)."] == []


def test_without_sibling_fqns_the_walk_is_unchanged():
    rows = inherited_rows_over(hierarchy, annotation_rows, {"com/acme/rs/GET#"}, ["com/acme/rs/Path#"])
    assert {r["annotation"] for r in rows if r["target"].endswith("#byId(sig_1).")} == {"com/acme/rs/GET#"}
```
Run → the first two FAIL (`TypeError: unexpected keyword` / only the mapping row).

- [ ] **Step 2: implement.** `_resolve_method` returns `(method, *found)` at every `return found` site where `method` is the ancestor method symbol that carried it (the recursive returns pass through unchanged). In `inherited_rows_over`:
```python
    own_fqns = mapping_fqns | set(sibling_fqns)   # §3.6: any own annotation of the catalog's blocks inheritance
    ...
        for key, candidate in methods.items():
            if _own_mapping(candidate, own_fqns, annotations_by_target) is not None:
                continue
            found = _resolve_method(...)            # now (source, annotation, args)
            if found is None:
                continue
            source, annotation, args = found
            target = _synthesis_target(...)
            ...
            resolved.setdefault(target, []).append((annotation, args))
            if sibling_fqns:
                for sib_annotation, sib_args in annotations_by_target.get(source, []):
                    if sib_annotation in sibling_fqns:
                        siblings.setdefault(target, []).append((sib_annotation, sib_args))
```
and after the `resolved` loop emits mapping rows, emit one row per `(target, sibling)` in `siblings` — **only for targets that received a mapping row** (a target whose two ancestors disagreed gets no mapping and therefore no siblings either). Keep the NFR-1 sort. `_own_mapping`'s signature is unchanged; it is simply handed the wider set.

- [ ] **Step 3: the caller.** In `_synthetic_annotations`, compute
```python
    mapping = catalog.matches["mapping"]
    sibling_fqns = frozenset(
        _catalog_symbol(str(source["annotation"]))
        for key in ("path_from_siblings", "produces_from_siblings", "consumes_from_siblings")
        for source in (mapping.get(key) or [])
    ) | frozenset(_catalog_symbol(name) for name in (catalog.protocol_hint.get("hint_annotations") or []))
```
and pass `sibling_fqns=sibling_fqns` to `inherited_rows_over`. (`hint_annotations` is Task 9's key; reading an absent key here is an empty set today, so this line is inert until Task 9 and Task 10.)

- [ ] **Step 4: run** the three tests → PASS; the whole `effective_annotations` test file green; golden check (no catalog declares siblings yet).

- [ ] **Step 5: guard.** `effective_annotations.siblings-inherit-all-or-nothing`: `Edit(path=_EFFECTIVE_ANNOTATIONS, find="    own_fqns = mapping_fqns | set(sibling_fqns)", replace="    own_fqns = set(mapping_fqns)  # guard disabled")`; the second test above pins it (`@pytest.mark.pins(...)`; no `declines` marker — this is not a catalog near-miss).

- [ ] **Step 6: D02.** Word 3 bullet: the rule, the §3.6 quote, "one module knows about inheritance", the type gate already inherits via the prefix synthesis, and the measured boundary (CP-19 row 6's answer on Quarkus).

- [ ] **Step 7: gate, commit.**
```bash
git add src/sextant/application/resolve/effective_annotations.py src/sextant/application/resolve/engines/annotation_driven.py docs/components/D02-catalog-schema.md tests/application/<the effective_annotations test file> scripts/guard_check.py
git commit -m "feat(engine): an inherited mapping brings the ancestor method's declared siblings with it, all or nothing, and any own annotation of the catalog's blocks inheritance — JAX-RS §3.6 (B/C Task 5, spec §3b word 3)"
```

---

### Task 6: `sole_unbound` — the body rule measured against the framework's binding annotations (M2, M4)

**Files:**
- Create: `src/sextant/application/resolve/conditions.py` (only `annotation_index`, `enclosing_type_of` and `member_annotations_by_type` in this task; Task 7 adds the condition itself)
- Modify: `src/sextant/application/resolve/shapes/contracts.py` (`_contracts_of` 102, `_body_type` 212, `_body_parameter` 242)
- Modify: `docs/components/D02-catalog-schema.md` (the `request_body` paragraphs in `annotation_driven`, ~523–540 and ~715–725)
- Test: the file testing `_body_parameter`/`sole_unannotated` (`grep -ln "sole_unannotated" tests/application/*.py`); `scripts/guard_check.py`

**Interfaces:**
- Consumes: `_body_parameter(signature, catalog) -> tuple[int, dict] | None`; `_contracts_of(endpoints, catalog, settled, rules, enums, referenced)`; `workspace.once(fn)`; `workspace.query("annotations")` rows `{target, annotation, args, retention}`; `workspace.query("symbols")` rows with `symbol`, `enclosing`, `construct_kind`.
- Produces:
  - `conditions.annotation_index(workspace) -> dict[str, list[tuple[str, dict]]]` — target → `[(annotation_descriptor, args)]`, built once via `workspace.once`.
  - `conditions.enclosing_type_of(symbol: str) -> str | None` — `symbol[: symbol.find("#") + 1]` or None when no `#`.
  - `conditions.member_annotations_by_type(workspace) -> dict[str, set[str]]` — enclosing type → the set of annotation descriptors carried by any field or method symbol declared in it (join `symbols.enclosing` to `annotations.target` for `construct_kind IN ('field','method')`), via `workspace.once`.
  - `_body_parameter(signature, catalog, *, owner: str, paths: frozenset[str], index: dict, members: dict) -> tuple[int, dict] | None`.

**What the spec says (§4):** bound = carries a `bound_by` annotation, or its type is in `excludes`, or (`path_variable`) its name matches a `{name}`/`{name: regex}` in the row's composed path, or (`container`) its class declares a field/method carrying a `bound_by` annotation. Body = the sole unbound parameter. `bound_by` required with `sole_unbound`, refused with `sole_unannotated`; `implicit_bindings` closed; `annotation` optional.

- [ ] **Step 1: failing unit tests** in the `_body_parameter` test file, calling the new signature directly with hand-built signatures (the shape `SymbolFact.signature` serialises to — copy from an existing test there):
```python
_JAXRS_BODY = {"fallback": "sole_unbound",
               "bound_by": ["jakarta.ws.rs.PathParam", "jakarta.ws.rs.QueryParam", "jakarta.ws.rs.core.Context"],
               "excludes": ["jakarta.ws.rs.sse.SseEventSink"]}
_QUARKUS_BODY = {**_JAXRS_BODY, "implicit_bindings": ["path_variable", "container"]}


def _catalog_with(body: dict) -> Catalog: ...   # a minimal annotation_driven Catalog whose matches["request_body"] = body


def test_a_validation_annotation_does_not_unbind_the_body():
    sig = _signature([_param("order", "com/acme/Order#", annotations=["jakarta/validation/Valid#"])])
    assert _body_parameter(sig, _catalog_with(_JAXRS_BODY), owner="com/acme/R#create(sig_1).", paths=frozenset({"/orders"}),
                           index={}, members={})[0] == 0


def test_a_kotlin_notnull_does_not_unbind_the_body():
    sig = _signature([_param("order", "com/acme/Order#", annotations=["org/jetbrains/annotations/NotNull#"])])
    assert _body_parameter(sig, _catalog_with(_JAXRS_BODY), owner="com/acme/R#create(sig_1).", paths=frozenset({"/orders"}),
                           index={}, members={}) is not None


def test_a_bound_by_annotation_unbinds():
    sig = _signature([_param("id", "java/lang/String#", annotations=["jakarta/ws/rs/PathParam#"]),
                      _param("order", "com/acme/Order#")])
    assert _body_parameter(sig, _catalog_with(_JAXRS_BODY), owner="o", paths=frozenset(), index={}, members={})[0] == 1


def test_path_variable_binding_is_quarkus_only():
    sig = _signature([_param("id", "java/lang/String#")])
    plain = _body_parameter(sig, _catalog_with(_JAXRS_BODY), owner="o", paths=frozenset({"/orders/{id}"}), index={}, members={})
    quarkus = _body_parameter(sig, _catalog_with(_QUARKUS_BODY), owner="o", paths=frozenset({"/orders/{id}"}), index={}, members={})
    assert plain is not None and quarkus is None


def test_path_variable_binding_reads_the_name_before_a_regex():
    sig = _signature([_param("id", "java/lang/String#"), _param("order", "com/acme/Order#")])
    assert _body_parameter(sig, _catalog_with(_QUARKUS_BODY), owner="o", paths=frozenset({"/orders/{id: \\d+}"}), index={}, members={})[0] == 1


def test_container_binding_reads_the_parameters_class_members():
    sig = _signature([_param("form", "com/acme/Upload#")])
    members = {"com/acme/Upload#": {"org/jboss/resteasy/reactive/RestForm#"}}
    body = {**_QUARKUS_BODY, "bound_by": [*_QUARKUS_BODY["bound_by"], "org.jboss.resteasy.reactive.RestForm"]}
    assert _body_parameter(sig, _catalog_with(body), owner="o", paths=frozenset(), index={}, members=members) is None


def test_sole_unbound_without_bound_by_is_refused():
    with pytest.raises(CatalogError, match="bound_by"):
        _body_parameter(_signature([]), _catalog_with({"fallback": "sole_unbound"}), owner="o", paths=frozenset(), index={}, members={})


def test_an_unknown_implicit_binding_is_refused():
    with pytest.raises(CatalogError, match="implicit_bindings"):
        _body_parameter(_signature([]), _catalog_with({**_JAXRS_BODY, "implicit_bindings": ["by_type"]}), owner="o", paths=frozenset(), index={}, members={})
```
Run → FAIL (unexpected keyword arguments).

- [ ] **Step 2: `conditions.py`, the index half.**
```python
"""Shared reads for rules conditional on annotations (spec 2026-09-18 §2, §4):
where an owner's and its type's annotations are, once per load.

Built through `Workspace.once` so the `annotations` decode runs once per load
rather than once per catalog (`annotation_driven._annotation_rows`' reason).
Read by the body rule (`shapes/contracts.py`), the conditional wrapper filter
and the `protocol_hint` pass; written by none of them.
"""
from __future__ import annotations
import json
from typing import Any
from sextant.application.ports.workspace import Workspace


def enclosing_type_of(symbol: str) -> str | None:
    """The type a member symbol belongs to, `#` included — the coordinates
    prefix carries no `#`, so this holds for a full symbol and a bare
    descriptor alike (D00 §5a). None for a type or a free function."""
    index = symbol.find("#")
    if index == -1 or symbol.endswith("#"):
        return None
    return symbol[: index + 1]


def annotation_index(workspace: Workspace) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """target → [(annotation descriptor, args)], every annotation row once."""
    def build(ws: Workspace) -> dict[str, list[tuple[str, dict[str, Any]]]]:
        found: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for row in ws.query("annotations"):
            args = json.loads(str(row["args"])) if row["args"] is not None else {}
            found.setdefault(str(row["target"]), []).append((str(row["annotation"]), args))
        for entries in found.values():
            entries.sort(key=lambda entry: entry[0])
        return found
    return workspace.once(build)


def member_annotations_by_type(workspace: Workspace) -> dict[str, set[str]]:
    """enclosing type → the annotation descriptors any field or method declared
    in it carries — Quarkus's parameter-container rule reads exactly this
    (CP-19 row 4)."""
    def build(ws: Workspace) -> dict[str, set[str]]:
        enclosing = {str(r["symbol"]): str(r["enclosing"]) for r in ws.query("symbols")
                     if r.get("enclosing") and str(r["construct_kind"]) in ("field", "method")}
        found: dict[str, set[str]] = {}
        for target, entries in annotation_index(ws).items():
            owner = enclosing.get(target)
            if owner is not None:
                found.setdefault(owner, set()).update(annotation for annotation, _ in entries)
        return found
    return workspace.once(build)
```
(Check `Workspace.once`'s exact signature — `grep -n "def once" src/sextant/application/ports/workspace.py` — and whether `symbols` rows expose `enclosing`; they do per `schema.sql`'s view, line ~756.)

- [ ] **Step 3: `_body_parameter`.** New signature per Interfaces. Body:
```python
    declared = catalog.matches.get("request_body")
    if declared is None:
        return None
    marker = declared.get("annotation")
    parameters = signature.get("parameters", [])
    if marker is not None:
        body_annotation = _catalog_symbol(marker)
        for i, parameter in enumerate(parameters):
            if any(use["annotation"] == body_annotation for use in parameter.get("annotations", [])):
                return i, parameter
    fallback = declared.get("fallback")
    excluded = {_catalog_symbol(t) for t in declared.get("excludes", [])}
    if fallback == "sole_unannotated":
        if "bound_by" in declared or "implicit_bindings" in declared:
            raise CatalogError(f"loading catalog {catalog.source}: `request_body.bound_by`/`implicit_bindings` belong to `fallback: sole_unbound`, not `sole_unannotated`")
        bare = [(i, p) for i, p in enumerate(parameters)
                if not p.get("annotations") and (p.get("erased_symbol") or p["type"].get("symbol")) not in excluded]
        return bare[0] if len(bare) == 1 else None
    if fallback == "sole_unbound":
        bound_by = declared.get("bound_by")
        if not isinstance(bound_by, list) or not bound_by:
            raise CatalogError(f"loading catalog {catalog.source}: `fallback: sole_unbound` requires a non-empty `request_body.bound_by` list — the word means 'unbound by THESE'")
        implicit = declared.get("implicit_bindings") or []
        if not isinstance(implicit, list) or not set(implicit) <= _IMPLICIT_BINDINGS:
            raise CatalogError(f"loading catalog {catalog.source}: `request_body.implicit_bindings` must be a subset of {sorted(_IMPLICIT_BINDINGS)}, got {implicit!r}")
        binders = {_catalog_symbol(a) for a in bound_by}
        variables = _path_variables(paths) if "path_variable" in implicit else frozenset()
        unbound = [(i, p) for i, p in enumerate(parameters) if not _is_bound(p, binders, excluded, variables, "container" in implicit, members)]
        return unbound[0] if len(unbound) == 1 else None
    return None
```
with
```python
_IMPLICIT_BINDINGS = frozenset({"path_variable", "container"})
_PATH_VARIABLE = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^}]*)?\}")


def _path_variables(paths: frozenset[str]) -> frozenset[str]:
    return frozenset(name for path in paths for name in _PATH_VARIABLE.findall(path))


def _is_bound(parameter, binders, excluded, variables, container: bool, members) -> bool:
    symbol = parameter.get("erased_symbol") or parameter["type"].get("symbol")
    if symbol in excluded:
        return True
    if any(use["annotation"] in binders for use in parameter.get("annotations", [])):
        return True
    if parameter.get("name") in variables:
        return True
    return container and bool(members.get(symbol, set()) & binders)
```
`_body_type(signature, catalog, **context)` forwards the keyword arguments. In `_contracts_of`, before the loop: `index = annotation_index(workspace)` and `members = member_annotations_by_type(workspace)` — `_contracts_of` does not receive the workspace today; thread it from `derive_endpoint_shapes` (it has `workspace`). Per owner, `paths = frozenset(str(e["path"]) for e in endpoints if _owns(catalog, e) and (e["handler"] or e["caller"]) == owner and e["path"] is not None)` — build a `dict[owner, set[path]]` once before the loop, not per row (§8.7).

- [ ] **Step 4: run** the unit tests → PASS; the whole test file and `tests/application/test_pipeline.py` green (`sole_unannotated` path unchanged); golden check.

- [ ] **Step 5: guards.** `contracts.sole-unbound-measures-bound-by`: `find="    if any(use[\"annotation\"] in binders for use in parameter.get(\"annotations\", [])):", replace="    if parameter.get(\"annotations\"):  # guard disabled"` — pinned by `test_a_validation_annotation_does_not_unbind_the_body`. `contracts.implicit-path-variable-reads-the-composed-path`: `find="        variables = _path_variables(paths) if \"path_variable\" in implicit else frozenset()", replace="        variables = frozenset()  # guard disabled"` — pinned by `test_path_variable_binding_is_quarkus_only`.

- [ ] **Step 6: D02.** In the `request_body` paragraph: `annotation` optional; the new word with its three predicates, the two closed implicit words and who declares them; why `sole_unannotated` stays (byte-identity) and its recorded Kotlin defect (register, Task 13).

- [ ] **Step 7: gate, commit.**
```bash
git add src/sextant/application/resolve/conditions.py src/sextant/application/resolve/shapes/contracts.py docs/components/D02-catalog-schema.md tests/application/<body-rule test file> scripts/guard_check.py
git commit -m "feat(engine): sole_unbound — the body is the one parameter none of the framework's own binding annotations claim, with Quarkus's path-variable and container bindings as closed implicit words (B/C Task 6, spec §4; M2, M4)"
```

---

### Task 7: the `annotation_arg` condition — `equals` | `parses_true`, read on the owner else its type

**Files:**
- Modify: `src/sextant/application/resolve/conditions.py` (add the condition)
- Create: `tests/application/test_conditions.py`
- Modify: D02 — a new subsection "Conditions on an annotation attribute" directly before §2a "Wrapper declarations"

**Interfaces:**
- Produces:
```python
@dataclass(frozen=True)
class AnnotationArg:
    annotation: str                 # descriptor form, e.g. "org/springframework/kafka/annotation/KafkaListener#"
    names: tuple[str, ...]          # aliases, first present wins
    equals: str | None              # exactly one of equals / parses_true is set
    parses_true: bool

def parse_condition(declared: object, where: str) -> AnnotationArg      # raises CatalogError
def holds(condition: AnnotationArg, owner: str, index: dict[str, list[tuple[str, dict]]]) -> bool
```

**What the spec says (§2):** `when: {annotation_arg: {annotation, name, equals | parses_true}}`; `annotation` required; `name` scalar or list; exactly one comparator; `equals` on the string form, any-element for arrays; `parses_true` = `hasText` then `Boolean.parseBoolean` (CP-20 row 2); read on the declaration else its enclosing type; anything else refused by name.

- [ ] **Step 1: failing tests**, `tests/application/test_conditions.py`:
```python
KL = "org/springframework/kafka/annotation/KafkaListener#"
JL = "io/micronaut/jms/annotations/JMSListener#"


def test_equals_reads_the_owner_first():
    c = parse_condition({"annotation_arg": {"annotation": "io.micronaut.jms.annotations.JMSListener", "name": "value", "equals": "sqsJmsConnectionFactory"}}, "t")
    index = {"m com/acme/A#on(sig_1).": [(JL, {"value": "sqsJmsConnectionFactory"})]}
    assert holds(c, "m com/acme/A#on(sig_1).", index)


def test_equals_falls_back_to_the_enclosing_type():
    c = parse_condition({"annotation_arg": {"annotation": "io.micronaut.jms.annotations.JMSListener", "name": "value", "equals": "sqsJmsConnectionFactory"}}, "t")
    index = {"m com/acme/A#": [(JL, {"value": "sqsJmsConnectionFactory"})]}
    assert holds(c, "m com/acme/A#on(sig_1).", index)
    assert not holds(c, "m com/acme/A#on(sig_1).", {"m com/acme/A#": [(JL, {"value": "activeMqConnectionFactory"})]})


def test_equals_is_case_sensitive_and_matches_any_array_element():
    c = parse_condition({"annotation_arg": {"annotation": "x.Y", "name": "v", "equals": "a"}}, "t")
    assert holds(c, "o", {"o": [("x/Y#", {"v": ["b", "a"]})]})
    assert not holds(c, "o", {"o": [("x/Y#", {"v": "A"})]})


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("TRUE", True), ("True", True), ("false", False), ("", False), ("${x}", False), (None, False)])
def test_parses_true_is_boolean_parseboolean_after_hastext(value, expected):
    c = parse_condition({"annotation_arg": {"annotation": "org.springframework.kafka.annotation.KafkaListener", "name": "batch", "parses_true": True}}, "t")
    args = {} if value is None else {"batch": value}
    assert holds(c, "o", {"o": [(KL, args)]}) is expected


def test_name_aliases_first_present_wins():
    c = parse_condition({"annotation_arg": {"annotation": "x.Y", "name": ["a", "b"], "equals": "1"}}, "t")
    assert holds(c, "o", {"o": [("x/Y#", {"b": "1"})]})
    assert not holds(c, "o", {"o": [("x/Y#", {"a": "2", "b": "1"})]})


@pytest.mark.parametrize("bad", [
    {"annotation_arg": {"annotation": "x.Y", "name": "v"}},                                  # no comparator
    {"annotation_arg": {"annotation": "x.Y", "name": "v", "equals": "1", "parses_true": True}},  # both
    {"annotation_arg": {"name": "v", "equals": "1"}},                                        # no annotation
    {"annotation_arg": {"annotation": "x.Y", "name": "v", "contains": "1"}},                 # unknown key
    {"annotation_present": "x.Y"},                                                           # unknown condition
    "annotation_arg",
])
def test_anything_else_is_refused_by_name(bad):
    with pytest.raises(CatalogError):
        parse_condition(bad, "t")
```
Run → FAIL (import error).

- [ ] **Step 2: implement** in `conditions.py`:
```python
_CONDITION_KEYS = frozenset({"annotation_arg"})
_ARG_KEYS = frozenset({"annotation", "name", "equals", "parses_true"})


@dataclass(frozen=True)
class AnnotationArg: ...  # as in Interfaces


def parse_condition(declared: object, where: str) -> AnnotationArg:
    if not isinstance(declared, dict) or set(declared) != _CONDITION_KEYS:
        raise CatalogError(f"{where}: `when` must be exactly `{{annotation_arg: {{...}}}}` — got {declared!r} (spec 2026-09-18 §2, closed)")
    arg = declared["annotation_arg"]
    if not isinstance(arg, dict) or not set(arg) <= _ARG_KEYS or "annotation" not in arg or "name" not in arg:
        raise CatalogError(f"{where}: `annotation_arg` takes `annotation`, `name` and exactly one of `equals`/`parses_true` — got {arg!r}")
    has_equals, has_parses = "equals" in arg, "parses_true" in arg
    if has_equals == has_parses:
        raise CatalogError(f"{where}: `annotation_arg` needs exactly one comparator, `equals` or `parses_true` — got {arg!r}")
    if has_parses and arg["parses_true"] is not True:
        raise CatalogError(f"{where}: `parses_true` is written `parses_true: true`; it is Spring's `Boolean.parseBoolean` after `hasText`, not a value to compare")
    names = arg["name"] if isinstance(arg["name"], list) else [arg["name"]]
    if not names or not all(isinstance(n, str) and n for n in names) or not isinstance(arg["annotation"], str) or not arg["annotation"]:
        raise CatalogError(f"{where}: `annotation_arg.annotation` is one fqn and `name` one attribute or a non-empty list of aliases — got {arg!r}")
    return AnnotationArg(annotation=_catalog_symbol(arg["annotation"]), names=tuple(names),
                         equals=None if not has_equals else str(arg["equals"]), parses_true=has_parses)


def holds(condition: AnnotationArg, owner: str, index) -> bool:
    for target in (owner, enclosing_type_of(owner)):
        if target is None:
            continue
        for annotation, args in index.get(target, []):
            if annotation != condition.annotation:
                continue
            value = next((args[n] for n in condition.names if n in args), None)
            return _compare(condition, value)
    return False


def _compare(condition: AnnotationArg, value: object) -> bool:
    values = value if isinstance(value, list) else [value]
    if condition.parses_true:
        # CP-20 row 2: StringUtils.hasText, then Boolean.parseBoolean — no placeholder resolution.
        return any(isinstance(v, str) and v.strip() != "" and v.lower() == "true" for v in values)
    return any(v is not None and str(v) == condition.equals for v in values)
```
(`Boolean.parseBoolean(s)` is `s != null && s.equalsIgnoreCase("true")` — hence `.lower() == "true"`; `_catalog_symbol` imported from `shapes/rooting.py`.) Note `holds` returns on the **first matching annotation found on the nearer target**: if the owner carries the annotation, the type is never consulted — the nearer declaration wins, D02's precedence.

- [ ] **Step 3: run** → PASS.

- [ ] **Step 4: D02** subsection: the YAML, the six bullets of spec §2 (two-level read, `annotation` required, `name` aliases, exactly one comparator with the bean-name reason for two words, closed), and "two consumers: §2a `wrappers[].when`, §2 `protocol_hint.hint_when`" pointing forward to Tasks 8–9.

- [ ] **Step 5: gate, commit.**
```bash
git add src/sextant/application/resolve/conditions.py tests/application/test_conditions.py docs/components/D02-catalog-schema.md
git commit -m "feat(engine): the annotation_arg condition — equals or parses_true, read on the owner else its enclosing type, everything else refused by name (B/C Task 7, spec §2)"
```

---

### Task 8: `wrappers[].when` — a conditional envelope, applied at rooting

**Files:**
- Modify: `src/sextant/application/resolve/shapes/expansion.py` (`_Rules` at 185, `_rules_of` at 307)
- Modify: `src/sextant/application/resolve/shapes/contracts.py` (`_contracts_of`, `_payload_descriptor`)
- Modify: D02 §2a
- Test: the contracts/body-rule test file; `scripts/guard_check.py`

**Interfaces:**
- Consumes: `conditions.parse_condition`, `conditions.holds`, `conditions.annotation_index`; `root_type(reference, wrappers)`, `_matching_wrapper(symbol, wrappers)`.
- Produces: `_Rules.wrappers` holds only **unconditional** entries; `_Rules.conditional_wrappers: tuple[tuple[AnnotationArg, dict], ...]`; `_wrappers_for(rules, owner, index) -> list[dict]`; `_payload_descriptor(reference, rules, enums, referenced, wrappers)` takes the per-owner list.

**What the spec says (§5a):** the wrapper list handed to `root_type` for an owner is the unconditional wrappers plus every conditional one whose `when` holds for that owner; evaluated once per owner against the shared index; rooting only — expansion never sees a conditional wrapper; `when` refused on an entry whose `type` another catalog's unconditional list also names.

- [ ] **Step 1: failing test** (unit, in the contracts test file, with a synthetic `Catalog` whose `wrappers` carry the conditional `List` row and a signature `onRecords(List<OrderEvent>)`; `index` hand-built with `KL` `{"batch": "true"}` on the owner, then `"false"`):
```python
def test_a_conditional_wrapper_unwraps_only_where_its_condition_holds():
    catalog = _catalog_with_wrappers([
        {"type": "java.util.List", "payload_arg": 0, "semantics": "envelope",
         "when": {"annotation_arg": {"annotation": "org.springframework.kafka.annotation.KafkaListener", "name": "batch", "parses_true": True}}}])
    rules = _rules_of(catalog)
    owner = "m com/acme/L#onRecords(sig_1)."
    batch = _wrappers_for(rules, owner, {owner: [(KL, {"batch": "true"})]})
    record = _wrappers_for(rules, owner, {owner: [(KL, {"batch": "false"})]})
    assert [w["type"] for w in batch] == ["java.util.List"] and record == []
    assert rules.wrappers == []            # nothing conditional reaches the unconditional list


def test_a_conditional_wrapper_never_reaches_expansion():
    """Expansion is keyed on the type symbol and insert-if-absent (spring-kafka.yml's stated
    hazard); a conditional envelope must not make `java.util.List` an envelope module-wide."""
    catalog = _catalog_with_wrappers([...same...])
    assert "java/util/List#" not in {_catalog_symbol(w["type"]) for w in _rules_of(catalog).wrappers}


def test_when_on_a_type_another_catalog_names_unconditionally_is_refused():
    with pytest.raises(CatalogError, match="when"):
        _check_conditional_wrappers([catalog_with_conditional_list, catalog_with_unconditional_list])
```

- [ ] **Step 2: implement.** In `expansion.py::_Rules` add `conditional_wrappers: tuple[tuple[AnnotationArg, dict[str, Any]], ...]`; in `_rules_of`, split `catalog.wrappers` into entries with and without `"when"`, parsing each `when` with `parse_condition(entry["when"], f"loading catalog {catalog.source}: wrappers[type={entry['type']}]")` and keeping the entry minus the `when` key beside its condition. In `contracts.py`:
```python
def _wrappers_for(rules: "_Rules", owner: str, index) -> list[dict[str, Any]]:
    """The envelopes that apply to THIS owner: every unconditional wrapper, plus each
    conditional one whose `when` holds on the owner or its type (spec 2026-09-18 §5a)."""
    return [*rules.wrappers, *(wrapper for condition, wrapper in rules.conditional_wrappers if holds(condition, owner, index))]
```
`_payload_descriptor` takes `wrappers` explicitly and uses it in both `root_type` and `_matching_wrapper`; `_contracts_of` computes `wrappers = _wrappers_for(rules, owner, index)` once per owner and passes it for both columns. Add `_check_conditional_wrappers(catalogs)` called from `derive_endpoint_shapes` before the loop: for every conditional entry, if any *other* catalog's unconditional `wrappers` names the same `type` → `CatalogError` naming both files (the sort-order hazard).

- [ ] **Step 3: run** → PASS; `test_pipeline.py` green (unchanged catalogs have no `when`); golden check.

- [ ] **Step 4: guard.** `contracts.conditional-wrapper-needs-its-condition`: `find="    return [*rules.wrappers, *(wrapper for condition, wrapper in rules.conditional_wrappers if holds(condition, owner, index))]", replace="    return [*rules.wrappers, *(wrapper for condition, wrapper in rules.conditional_wrappers)]  # guard disabled"` — pinned by the first test.

- [ ] **Step 5: D02 §2a**: `when` on a wrapper entry; rooting-only; the refusal; the `spring-kafka.yml` example forward-referenced to Task 11.

- [ ] **Step 6: gate, commit.**
```bash
git add src/sextant/application/resolve/shapes/expansion.py src/sextant/application/resolve/shapes/contracts.py docs/components/D02-catalog-schema.md tests/application/<contracts test file> scripts/guard_check.py
git commit -m "feat(engine): wrappers[].when — an envelope that applies only where an annotation attribute says so, at rooting and never at expansion (B/C Task 8, spec §5a)"
```

---

### Task 9: `protocol_hint.hint_when` and `hint_annotations` — two evidence kinds read off the owner

**Files:**
- Modify: `src/sextant/application/resolve/protocol_hint.py` (`_KEYS`, `_Hint`, `_checked`, `_vocabulary`, `apply_protocol_hints`, module docstring)
- Modify: D02 §2 `protocol_hint`
- Test: the protocol_hint test file; `scripts/guard_check.py`

**Interfaces:**
- Consumes: `conditions.parse_condition`, `holds`, `annotation_index`, `enclosing_type_of`; `_MATCH_COLUMNS` includes `handler`, `caller`.
- Produces: `_Hint(target, media, returns, annotations: frozenset[str], conditions: tuple[AnnotationArg, ...])`; keys `hint_annotations` (list of fqns) and `hint_when` (one condition per catalog; unioned across catalogs into the tuple); `_owner(endpoint) = endpoint["handler"] or endpoint["caller"]`.

**What the spec says (§3c, §5b):** `hint_annotations` fires when a listed annotation targets the row's owner **or its enclosing type**; `hint_when` fires when the §2 condition holds on the owner (else its type). Same three promises; the docstring records the widened read. A block must still name at least one evidence kind; the four kinds union across catalogs of one source protocol; a conflicting target is refused as today.

- [ ] **Step 1: failing tests** (in the protocol_hint test file, following its existing pattern of building a workspace with endpoint rows and a catalog list):
```python
def test_hint_when_reclassifies_the_owners_type_binding_on_both_directions(tmp_path):
    # two jms rows: inbound handler `…/SqsConsumer#onQueued(sig_1).`, outbound caller `…/SqsSender#send(sig_1).`;
    # annotation facts: @JMSListener(value=sqsJmsConnectionFactory) on SqsConsumer#, @JMSProducer(value=…) on SqsSender#,
    # and a third jms row whose type carries value=activeMqConnectionFactory.
    catalogs = [_hint_catalog("micronaut-jms", "jms", {"protocol": "sqs", "hint_when": {"annotation_arg": {"annotation": "io.micronaut.jms.annotations.JMSListener", "name": "value", "equals": "sqsJmsConnectionFactory"}}}),
                _hint_catalog("micronaut-jms-producer", "jms", {"protocol": "sqs", "hint_when": {"annotation_arg": {"annotation": "io.micronaut.jms.annotations.JMSProducer", "name": "value", "equals": "sqsJmsConnectionFactory"}}})]
    apply_protocol_hints(workspace, catalogs)
    assert {(r["path"], r["protocol"]) for r in workspace.query("endpoints")} == {("mn.orders.sqs", "sqs"), ("mn.orders.sqs-out", "sqs"), ("mn.orders.classic", "jms")}


def test_hint_annotations_fires_on_the_handler_or_its_type(tmp_path):
    # http rows for /events (handler carries @RestStreamElementType), /ticks (its TYPE carries it), /plain (neither)
    catalogs = [_hint_catalog("quarkus-rest", "http", {"protocol": "sse", "hint_annotations": ["org.jboss.resteasy.reactive.RestStreamElementType"]})]
    apply_protocol_hints(workspace, catalogs)
    assert {(r["path"], r["protocol"]) for r in workspace.query("endpoints")} == {("/events", "sse"), ("/ticks", "sse"), ("/plain", "http")}


def test_a_block_with_only_the_new_kinds_is_a_valid_block():
    _checked({"protocol": "sse", "hint_annotations": ["a.B"]}, catalog)
    _checked({"protocol": "sqs", "hint_when": {"annotation_arg": {"annotation": "a.B", "name": "value", "equals": "x"}}}, catalog)
    with pytest.raises(CatalogError):
        _checked({"protocol": "sse", "hint_annotations": "a.B"}, catalog)    # not a list
```

- [ ] **Step 2: implement.** `_ANNOTATIONS = "hint_annotations"`, `_WHEN = "hint_when"`, `_KEYS = (_TARGET, _MEDIA, _RETURNS, _ANNOTATIONS, _WHEN)`. `_checked` returns a 5-tuple: `annotations = frozenset(type_descriptor(n) for n in block.get(_ANNOTATIONS) or [])` (must be a string list), `condition = parse_condition(block[_WHEN], f"loading catalog {catalog.source}: `protocol_hint.hint_when`") if _WHEN in block else None`; the "no evidence" refusal becomes `not (media or returns or annotations or condition)`. `_Hint` gains `annotations: frozenset[str]` and `conditions: tuple[AnnotationArg, ...]`; `_vocabulary` unions `annotations` and appends conditions. In `apply_protocol_hints`, build `index = annotation_index(workspace)` once (only if any hint has annotations or conditions), and the row test becomes:
```python
        if (_declares_media(endpoint, hint) or _returns_marker(endpoint, hint)
                or _owner_annotated(endpoint, hint, index) or _condition_holds(endpoint, hint, index)):
```
with
```python
def _owner(endpoint) -> str | None:
    return str(endpoint["handler"] or endpoint["caller"] or "") or None


def _owner_annotated(endpoint, hint, index) -> bool:
    owner = _owner(endpoint)
    if owner is None or not hint.annotations:
        return False
    for target in (owner, enclosing_type_of(owner)):
        if target and any(annotation in hint.annotations for annotation, _ in index.get(target, [])):
            return True
    return False


def _condition_holds(endpoint, hint, index) -> bool:
    owner = _owner(endpoint)
    return owner is not None and any(holds(c, owner, index) for c in hint.conditions)
```
Docstring: add a fourth paragraph — "**Two evidence kinds read off the OWNER rather than the row** (spec 2026-09-18 §3c, §5b): `hint_annotations`, presence of a listed annotation on the handler/caller or its enclosing type; `hint_when`, the §2 condition on the same two targets. This is the one widening of what the pass reads — annotation facts for the owner — and it still writes exactly one column on rows that already exist."

- [ ] **Step 3: run** → PASS; existing hint tests green; golden check.

- [ ] **Step 4: guard.** `protocol_hint.hint-when-reads-the-owner`: `find="    return owner is not None and any(holds(c, owner, index) for c in hint.conditions)", replace="    return owner is not None and bool(hint.conditions)  # guard disabled"` — pinned by the first test (the ActiveMQ row must stay `jms`).

- [ ] **Step 5: D02 §2 `protocol_hint`**: the two new keys, the owner/type read, the widened-read sentence, the union rule unchanged.

- [ ] **Step 6: gate, commit.**
```bash
git add src/sextant/application/resolve/protocol_hint.py docs/components/D02-catalog-schema.md tests/application/<protocol_hint test file> scripts/guard_check.py
git commit -m "feat(engine): protocol_hint reads the row's owner — hint_annotations (presence on the handler or its type) and hint_when (the annotation_arg condition) beside media and return-type markers (B/C Task 9, spec §3c, §5b)"
```

---

### Task 10: the three JAX-RS catalogs

**Files:**
- Create: `src/sextant/catalogs/jakarta-jaxrs.yml`, `javax-jaxrs.yml`, `quarkus-rest.yml`
- Test: the eight strict-xfail tests in `test_rest_inbound_delivered.py` and the two in `test_pipeline.py` flip; near-misses in `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: Tasks 3–9's words. `detect.coordinates` reads dependency facts by `groupId:artifactId`.
- Produces: `quarkus-jaxrs`, `jaxrs-sse` closed.

**What the spec says (§3a, §3c, §3d):** the YAML in §3a for `jakarta-jaxrs.yml`; `javax-jaxrs.yml` the same under `javax.ws.rs` fqns and `detect.coordinates: ["javax.ws.rs:javax.ws.rs-api"]` (+ `jakarta.ws.rs:jakarta.ws.rs-api` only if CP-18 shows 2.1.6 is `javax`-packaged AND the 4.0.0 catalog would otherwise claim it — it would not, since fqns differ, so list it); `quarkus-rest.yml` = the `jakarta` file plus: `detect.coordinates: ["io.quarkus:quarkus-rest", "io.quarkus:quarkus-resteasy-reactive"]`, `request_body.bound_by` += `org.jboss.resteasy.reactive.{RestPath,RestQuery,RestHeader,RestForm,RestCookie,RestMatrix,MultipartForm}`, `request_body.implicit_bindings: [path_variable, container]`, `excludes` += CP-19 row 3's Vert.x types, `protocol_hint.hint_annotations: [org.jboss.resteasy.reactive.RestStreamElementType, org.jboss.resteasy.reactive.RestSseElementType]`.

- [ ] **Step 1: write the three files.** Each carries: the header keys; `measured:` — `jakarta-jaxrs`: `{artifact: jakarta.ws.rs:jakarta.ws.rs-api, versions: ["3.1.0", "4.0.0"], identity: reported, by: scripts/probes/cp18_jaxrs_api_and_implementations.md}`; `javax-jaxrs`: `{artifact: javax.ws.rs:javax.ws.rs-api, versions: ["2.1.1"], …cp18}`; `quarkus-rest`: `{artifact: io.quarkus:quarkus-rest, versions: ["3.17.5", "3.39.4"], identity: reported, by: scripts/probes/cp19_quarkus_rest.md}`; the `requires` list; the `matches` block verbatim from spec §3a with the Task 6 `request_body`; `protocol_hint`; `media_formats` copied from `spring-web.yml`'s table (with its comment on why `text/event-stream` is absent); `shape_model: json`. Comments state, in place: verb annotations carry nothing (CP-18 row 1); why `all_methods: []`; the body rule's `bound_by` provenance (CP-18 row 7 / CP-19 row 4); the boundaries of spec §3d; and for `quarkus-rest.yml` why it is a separate file (spec §3a's last table row) and CP-19 row 6's answer on §3.6.

- [ ] **Step 2: run the live tests.** `uv run pytest tests/e2e/test_rest_inbound_delivered.py tests/application/test_pipeline.py -q` — the two original JAX-RS xfails and the eight new ones now **fail as strict-xfail-that-passed**; remove their `@pytest.mark.xfail` decorators; rerun → green. If a case does not pass, the catalog or an earlier task is wrong — fix there, never weaken the assertion.

- [ ] **Step 3: near-misses**, one per catalog, in `tests/application/test_endpoints.py`. For `jakarta-jaxrs` and `javax-jaxrs`: add each to the `_W58_ANNOTATION_CATALOGS`-style parametrised package near-miss (the method annotation from `com.acme.own` derives nothing), `@pytest.mark.declines("jakarta-jaxrs")` etc., pinned to the existing `derive_endpoints.mapping-annotation-fqn`. For `quarkus-rest`: the same, **and** a body near-miss using Task 6's unit style — `byId(String id)` under `/{id}` derives no body under `quarkus-rest.yml` and a `String` body under `jakarta-jaxrs.yml` — `@pytest.mark.declines("quarkus-rest")`, pinned to `contracts.implicit-path-variable-reads-the-composed-path`. Run `tests/architecture` (near-miss coverage, measurement coverage, catalog audits).

- [ ] **Step 4: gate, commit.**
```bash
git add src/sextant/catalogs/jakarta-jaxrs.yml src/sextant/catalogs/javax-jaxrs.yml src/sextant/catalogs/quarkus-rest.yml tests/e2e/test_rest_inbound_delivered.py tests/application/test_pipeline.py tests/application/test_endpoints.py
git commit -m "feat(catalogs): JAX-RS in three catalogs — jakarta and javax spellings, and Quarkus REST with its element-type SSE and implicit body bindings; the SSE row's last Java gap closes (quarkus-jaxrs, jaxrs-sse; B/C Task 10)"
```

---

### Task 11: `spring-kafka.yml` — the conditional `List` envelope

**Files:**
- Modify: `src/sextant/catalogs/spring-kafka.yml` (`wrappers`, `measured`)
- Test: `tests/application/test_pipeline.py` (the two xfails flip); a near-miss in the contracts test file

- [ ] **Step 1: the catalog.** Append to `wrappers` the row from spec §5a (with `parses_true: true`), preceded by a comment: CP-20 rows 2–3 (`hasText` → `parseBoolean` → `setBatchListener`; the batch adapter hands `List<V>`), why `when` and not an unconditional row (the record-listener `onBatch` case is a list on the wire), the `spring.kafka.listener.type` boundary, and the placeholder *agreement*. Add `{artifact: org.springframework.kafka:spring-kafka, versions: ["3.1.4", "4.1.1"], identity: reported, by: scripts/probes/cp20_spring_kafka_batch.md}` to `measured`. If CP-20 row 5 decided `Message<T>` joins, add `{type: org.springframework.messaging.Message, payload_arg: 0, semantics: envelope}` — unconditional, since a `Message<T>` parameter is an envelope on either listener kind.

- [ ] **Step 2: run** `tests/application/test_pipeline.py` — the two batch xfails pass → remove the decorators → green; `test_a_batch_listeners_request_shape_is_an_array` still green.

- [ ] **Step 3: near-miss.** `@pytest.mark.declines("spring-kafka")` `@pytest.mark.pins("contracts.conditional-wrapper-needs-its-condition")`: the real loaded `spring-kafka` catalog, an owner whose `@KafkaListener` carries `batch = "false"` and a `List<Foo>` parameter → `_wrappers_for` contains no `java.util.List`.

- [ ] **Step 4: gate, commit.**
```bash
git add src/sextant/catalogs/spring-kafka.yml tests/application/test_pipeline.py tests/application/<contracts test file>
git commit -m "feat(catalogs): a batch=true @KafkaListener publishes the record's element — List is the container's envelope only where Spring's own parseBoolean says so (kafka-batch-generics; B/C Task 11)"
```

---

### Task 12: `micronaut-jms.yml`, `micronaut-jms-producer.yml` — JMS over SQS on both sides

**Files:**
- Modify: both catalogs (`protocol_hint`, `measured`); `docs/COVERAGE.md` line 3222 (the `connectionFactory = …` wording → `@JMSListener(SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME)`, and the boundary sentence becomes the shipped statement — the rest of the row is Task 13's)
- Test: `tests/e2e/test_messaging_micronaut_delivered.py` (the xfail flips); near-miss in the protocol_hint test file

- [ ] **Step 1: the catalogs.** Add the `protocol_hint` blocks from spec §5b (`name: value`), each preceded by a comment quoting CP-21 rows 1–4 (only `value()`; `getRequiredValue` → `Qualifiers.byName`; the three constants; the compiled fixture carries the literal) and the stated boundaries (a user-named factory bean stays `jms`; a placeholder stays `jms`). Add `{artifact: io.micronaut.jms:micronaut-jms-sqs, versions: ["4.2.0"], identity: reported, by: scripts/probes/cp21_micronaut_jms_sqs.md}` to both `measured` lists.

- [ ] **Step 2: run** the Micronaut e2e file — the SQS xfail passes → remove the decorator → green, including the ActiveMQ negative.

- [ ] **Step 3: near-miss.** `@pytest.mark.declines("micronaut-jms")` `@pytest.mark.pins("protocol_hint.hint-when-reads-the-owner")`: the real loaded catalog, a `jms` row whose type carries `@JMSListener("activeMqConnectionFactory")` stays `jms`.

- [ ] **Step 4: gate, commit.**
```bash
git add src/sextant/catalogs/micronaut-jms.yml src/sextant/catalogs/micronaut-jms-producer.yml docs/COVERAGE.md tests/e2e/test_messaging_micronaut_delivered.py tests/application/<protocol_hint test file>
git commit -m "feat(catalogs): a Micronaut JMS listener or producer bound to the SQS connection factory publishes sqs and links with Spring's SQS rows (micronaut-jms-over-sqs, both directions; B/C Task 12)"
```

---

### Task 13: COVERAGE, the delivery list, CHANGELOG, the register — part 1 now, part 2 after CI

**Files:**
- Modify: `docs/COVERAGE.md` (§5 REST in line 2040 → ✅ with the three catalogs and CP-18/19; §5.6 SSE line 2778 → ✅ and the "one YAML entry" paragraph amended with `hint_annotations`; §4.1 a new Kafka row for `batch = "true"` beside the `List<T>` sentence at ~3061; §5 SQS line 3222 ✅; the boundaries of spec §3d, §5a, §5b each on the row it belongs to), regenerate with `scripts/coverage_matrix.py`, `scripts/coverage_versions.py`
- Modify: `docs/java-kotlin-delivery-list.md` — ```delivery: `quarkus-jaxrs` leaves REST inbound; `jaxrs-sse`, `kafka-batch-generics`, `micronaut-jms-over-sqs` leave their rows (SSE, Kafka, SQS now empty); §1 rows for the four ids → **closed** "on CI run <id>" (part 2); the Micronaut `@JMSProducer` addition recorded under SQS as delivered with the same run; the "eight specs" table's B and C rows → done, spec path named
- Modify: `CHANGELOG.md` `Unreleased`: four items + the producer addition, plain language, no bump
- Modify: `docs/open-issues.md`: three entries from spec §6 — the Feign/Micronaut `sole_unannotated` Kotlin defect (real input: a Kotlin Feign client or Micronaut listener with a non-null body), the SSE per-event format from `@RestStreamElementType` (rung-2 source), Quarkus's return-type default `produces`; plus anything a review of Tasks 3–12 recorded

- [ ] **Step 1 (part 1, now):** every document above except the CI run id; `tests/architecture/test_feature_delivery.py` and `test_feature_intention.py` green (a closed id must appear in ```closed with a run id — until part 2, keep the four ids in ```delivery and write the §1 rows as "implemented, pinned, awaiting CI run"; the register's own rule).

- [ ] **Step 2: gate, commit, PR.** Full gate; commit; open the PR from `feat/group-bc` to `main` with the spec and plan linked, the four items and the addition listed, "no version bump — standing gate" stated.

```bash
git add docs/COVERAGE.md docs/java-kotlin-delivery-list.md CHANGELOG.md docs/open-issues.md docs/coverage
git commit -m "docs: COVERAGE, CHANGELOG and the register catch up with Groups B and C — three JAX-RS catalogs, batch listeners, JMS over SQS; SSE, Kafka and SQS rows await their CI run (B/C Task 13, part 1)"
```

- [ ] **Step 3 (part 2, after CI is green):** move the four ids to ```closed with the run id, empty the three rows, and commit `docs(register): Groups B and C close on run <id>`.

---

## Self-review against the spec

**Coverage.** §0's eight rulings: M2/M4 → Task 6; M1 → Task 9 + Task 10's `quarkus-rest.yml`; M3 → Task 5; M5 → Task 7 (`parses_true`) + Task 11; R1 → Task 10 (gate kept) and the Task 1 Quarkus fixture keeps `@Path`; R2 → Task 12 (`name: value`) and COVERAGE 3222; R3 → Task 6 (`annotation` optional). §2 → Task 7. §3a → Task 10. §3b words 1–3 → Tasks 3, 4, 5. §3c → Tasks 9, 10, 6. §3d boundaries → Task 10 comments + Task 13 COVERAGE. §3e fixtures → Task 1 (every named class; the Kotlin resource in `orders-service`, the module that compiles Kotlin). §4 → Task 6. §5a → Tasks 7, 8, 11, and Task 1's two batch methods. §5b → Tasks 9, 12, and Task 1's three Micronaut types. §6 logged items → Task 13. §7 probes → Task 2, cited by Tasks 10–12's `measured:`. §8 proof → the golden check on every engine task. §9's table → the thirteen tasks here in the same order.

**Placeholders.** None: every step names the file, the code or the exact command. Two places delegate a filename to a `grep` because the repository's test files for `inherited_rows_over`, `_body_parameter` and `apply_protocol_hints` are found, not remembered — the grep is given.

**Type consistency.** `AnnotationArg`, `parse_condition(declared, where)`, `holds(condition, owner, index)`, `annotation_index(workspace)`, `enclosing_type_of(symbol)`, `member_annotations_by_type(workspace)` are defined in Tasks 6–7 and used with those names in Tasks 8, 9. `_wrappers_for(rules, owner, index)` (Task 8) is what Task 11's near-miss calls. `_body_parameter(signature, catalog, *, owner, paths, index, members)` (Task 6) is what Task 10's Quarkus near-miss calls. `_sibling_sources(catalog, mapping, key)` (Task 3) is what Task 4's `_type_media_sources` reuses. The SQL column names `produces_list`/`consumes_list` and the STRUCT field names match between Tasks 3 and 4. Guard ids in the file map match those registered in Tasks 3, 5, 6, 8, 9.
