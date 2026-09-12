# Plan-Only Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every open item in `docs/java-kotlin-delivery-list.md` that needs no spec — sixteen items, each either delivered red-to-green on real bytecode or measured off the list with the evidence recorded.

**Architecture:** Every item is one of three shapes the codebase already has: (1) `single_call` catalog rows over a measured `javap` surface, pinned by an intention test on a fixture module; (2) an extractor change in `extractor-jvm` pinned by a `.kt`/`.java` sample and an `ExtractorTest`; (3) a measurement whose outcome is recorded in the register and COVERAGE. No engine word is added anywhere in this plan — an item that turns out to need one is moved to the spec column, with the measurement, and the plan stops on it.

**Tech Stack:** Python 3.12, DuckDB SQL (`src/sextant/storage/duckdb/*.sql`), YAML catalogs (`src/sextant/catalogs/`), Java 21 + ASM + `kotlin-metadata-jvm` 2.2.0 (`extractor-jvm/`), Maven fixture modules under `fixtures/`, pytest with `-n 4 --dist loadfile`.

**Spec:** No single spec. Each task cites the register row it closes (`docs/java-kotlin-delivery-list.md`) and the measurement it argues from (a `scripts/probes/*.md` file this plan has the task write, or a `javap` output pasted into the task). Read `GUIDELINES.md` §1–§4, §8, §10 and §13.5 before any task.

## Global Constraints

- **Definition of done** (user, 2026-09-11): a blocker leaves the register only with a passing intention test AND the CI run URL where it passed. A locally green task is *implemented*, not *done*; the `closed` block entry is written after CI.
- **One feature fully implemented beats ten half done.** A task that cannot be finished whole is stopped and its state recorded in the register — never split into a done half and a new issue.
- **Measure before claiming.** Every catalog row cites a probe that opened the jar (`measured.by:`); every version in `measured.versions` must appear in that probe's `**Version scope**` paragraph (`tests/architecture/test_catalog_measurement_coverage.py` enforces this).
- **Never a wrong row.** Where the existing vocabulary would publish a wrong address (a nested prefix it cannot see, a lambda as a path), the form derives NOTHING and the catalog's `slice.outside` says why. A wrong row is worse than none.
- **No version bumps.** `pyproject.toml` and the extractor's version stay as they are.
- **Catalog discipline, every new or changed catalog:** a `measured:` row citing a committed probe; a `@pytest.mark.declines("<id>")` near-miss test (`tests/architecture/test_catalog_near_miss_coverage.py`); `scripts/coverage_versions.py` re-run (COVERAGE §3a); `scripts/coverage_matrix.py` re-run (§2 matrices); the w19 surface probes re-run when a catalog's method reads change (`bash scripts/probes/w19_catalog_surface/run.sh`, `bash scripts/probes/w19b_type_and_annotation_surface/run.sh`).
- **Fixtures are NEW modules, not additions to `fixtures/orders-service`.** That module's row counts are pinned in a dozen places; a new module (`fixtures/orders-receivers`, `fixtures/orders-streams`, …) compiles against annotation/API jars only (`<exclusions>*</exclusions>`) and is primed in `.github/workflows/pr.yml`'s "Prime the fixture's dependencies" step.
- **The gate is `bash scripts/check.sh`** with `JAVA_HOME=~/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home` (CI's JDK). Nothing is committed on a red gate. ~4 minutes.
- **Per-item loop:** implement → gate → review (a reviewer subagent, told: no state-changing git commands, no worktrees) → fix every Critical and Major → record → commit. No step is optional.
- **Plain language in every comment and commit.** Say what was measured and what it derives; never "blast radius", "mutations caught".
- **Reviewers and executors never run** `git stash`, `git checkout -- <file>`, `git reset --hard`, or create worktrees.

## Items this plan covers, and four it does not

| # | register id | task |
|---|---|---|
| 1 | `G-44` — `RabbitTemplate` receive half | Task 1 |
| 2 | `G-44` — `JmsTemplate` receive half | Task 2 |
| 3 | `G-44` — `KafkaTemplate.receive` | Task 3 |
| 4 | `G-44` — `SqsTemplate` receive half | Task 4 (measured boundary) |
| 5 | `G-31` Kafka Streams | Task 5 |
| 6 | `javalin-routing` | Task 6 |
| 7 | `alpakka-pekko` | Task 7 |
| 8 | `micronaut-sqs` | Task 8 |
| 9 | `jaxws-public-final` | Task 9 |
| 10 | `apache-cxf` | Task 10 |
| 11 | `OI-82` Kotlin parameter nullability | Task 11 |
| 12 | `OI-80` boxed primitive on a suspend return | Task 12 |
| 13 | `OI-81` + `kotlin-default-bridge` | Task 13 |
| 14 | `kotlin-extension-functions` | Task 14 |
| 15 | `kotlin-defaultimpls` | Task 15 |
| 16 | `G-52` throw exits | Task 16 |
| 17 | `G-74` `signature.throws` has no consumer | Task 17 |
| 18 | `G-73` `visibility` two-valued | Task 18 |
| 19 | `GAP-7` reactor-module cost | Task 19 |

**Measured off this plan while writing it (2026-09-12), and moved to the spec column:**

- **`ktor-routing`** — `javap` on ktor-server-core-jvm 3.0.3: every verb is a static `RoutingBuilderKt.get(Route, String, Function2)` whose receiver (argument 0) is the `Route` a surrounding `route("/api") { … }` created. The address is `/api` + `/x`, and the prefix is only visible by walking from the inner call's receiver to the outer call's lambda — the receiver chain the combinator spec (`docs/superpowers/specs/2026-09-11-combinator-overload-discrimination-design.md`) exists for. A `single_call` row on `get` would publish `/x` alone: a wrong row. Category B.
- **`vertx-eventbus`** — `EventBus.consumer(String, Handler)` / `send|publish|request(String, Object[, DeliveryOptions])` are `single_call` shapes exactly, BUT an event-bus address is none of the closed `Protocol` set's members (`src/sextant/domain/closed_sets.py`), and adding one is the schema decision the `RSOCKET` member's comment describes. Goes with `temporal-cadence`.
- **`javalin-apibuilder`** (the nested half of Javalin, split out of item 6) — `ApiBuilder.path("/api", () -> { get("/x", h); })`: the inner `get` is a static call inside a lambda passed to `path`; same receiver-chain shape as Ktor. Task 6 delivers the flat `app.get("/x", h)` form and files this half against Category B by name.
- **`kotlin-null-handler`, `jdk-httpclient`** — already Category C in the register; not re-examined here.

---

## Part A — the messaging receive halves (`G-44`)

All four tasks share one fixture module. Task 1 creates it; Tasks 2–4 add to it.

### Task 1: `RabbitTemplate` receive rows

**Files:**
- Create: `fixtures/orders-receivers/pom.xml`
- Create: `fixtures/orders-receivers/src/main/java/com/acme/recv/RabbitReceivers.java`
- Modify: `src/sextant/catalogs/spring-rabbit-template.yml` (the `methods:` list and the `slice.outside` block)
- Create: `tests/e2e/test_jms_and_amqp_delivered.py`
- Modify: `tests/application/test_call_engines.py` (declining test, appended)
- Modify: `.github/workflows/pr.yml:57-61` (priming)
- Modify: `docs/java-kotlin-delivery-list.md` (`intention-test-missing` block: remove `JMS and AMQP`)

**Interfaces:**
- Produces: `fixtures/orders-receivers` (Maven module `com.acme:orders-receivers`, `<maven.compiler.release>21`), and the module-scoped fixture `receiver_rows` in the test file, returning `set[tuple[str, str, str]]` of `(protocol, direction, path)` for every non-HTTP row — Tasks 2–4 add assertions against it.

**Measured, spring-rabbit 3.1.4 (`javap -s`), the overloads whose argument 0 is the queue name:**

```
receive(String)                                   (Ljava/lang/String;)Lorg/springframework/amqp/core/Message;
receive(String, long)                             (Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;
receiveAndConvert(String)                         (Ljava/lang/String;)Ljava/lang/Object;
receiveAndConvert(String, long)                   (Ljava/lang/String;J)Ljava/lang/Object;
receiveAndConvert(String, ParameterizedTypeReference)        (Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;
receiveAndConvert(String, long, ParameterizedTypeReference)  (Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;
receiveAndReply(String, ReceiveAndReplyCallback)              (Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z
receiveAndReply(String, ReceiveAndReplyCallback, String, String)          (Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z
receiveAndReply(String, ReceiveAndReplyCallback, ReplyToAddressCallback)  (Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z
```

The destination-less overloads (`receive()`, `receive(long)`, `receiveAndConvert()`, …) read the template's configured default queue and stay outside — the same line `convertAndSend(Object)` is already on. `receiveAndReply` is a receive whose reply goes to the message's own `replyTo`: ONE inbound row on the queue, no outbound row (the reply address is per-message and unreadable).

- [ ] **Step 1: Create the fixture module**

`fixtures/orders-receivers/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>orders-receivers</artifactId>
  <version>1.0.0</version>
  <!-- The RECEIVE half of the messaging templates (`G-44`), in its own module so that
       `orders-service`'s pinned row counts do not move. API jars only; never runs. -->
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.amqp</groupId><artifactId>spring-rabbit</artifactId><version>3.1.4</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>org.springframework.amqp</groupId><artifactId>spring-amqp</artifactId><version>3.1.4</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId><artifactId>spring-core</artifactId><version>6.1.6</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId><artifactId>spring-jms</artifactId><version>6.1.6</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>jakarta.jms</groupId><artifactId>jakarta.jms-api</artifactId><version>3.1.0</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>org.springframework.kafka</groupId><artifactId>spring-kafka</artifactId><version>3.1.4</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>org.apache.kafka</groupId><artifactId>kafka-clients</artifactId><version>3.6.2</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>io.awspring.cloud</groupId><artifactId>spring-cloud-aws-sqs</artifactId><version>3.1.1</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId><artifactId>spring-messaging</artifactId><version>6.1.6</version>
      <exclusions><exclusion><groupId>*</groupId><artifactId>*</artifactId></exclusion></exclusions>
    </dependency>
  </dependencies>
</project>
```

`fixtures/orders-receivers/src/main/java/com/acme/recv/RabbitReceivers.java`:

```java
package com.acme.recv;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.core.ParameterizedTypeReference;

/** Synchronous receives the way a batch job or a poller writes them. */
public class RabbitReceivers {
    private final RabbitTemplate template;

    public RabbitReceivers(RabbitTemplate template) {
        this.template = template;
    }

    public Message pollRaw() {
        return template.receive("recv.orders.raw");
    }

    public Object pollConverted() {
        return template.receiveAndConvert("recv.orders.converted", 500L);
    }

    public OrderEvent pollTyped() {
        return template.receiveAndConvert("recv.orders.typed",
                new ParameterizedTypeReference<OrderEvent>() {});
    }

    public boolean serveOne() {
        return template.receiveAndReply("recv.orders.rpc", (OrderEvent e) -> new OrderEvent(e.id(), "served"));
    }

    public record OrderEvent(String id, String status) {}
}
```

Run: `mvn -q -B -f fixtures/orders-receivers/pom.xml compile`
Expected: compiles; `ls fixtures/orders-receivers/target/classes/com/acme/recv/` shows `RabbitReceivers.class`.

- [ ] **Step 2: Write the failing intention test**

`tests/e2e/test_jms_and_amqp_delivered.py`:

```python
"""JMS and AMQP are delivered when the RECEIVE half of each template is visible — the
half `G-44` names. `RabbitTemplate` read 1 of 88 methods and `JmsTemplate` 1 of 49; the
sends. A module that polls a queue derived nothing.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner
from fixture_build import FIXTURES, compile_fixture

from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

RECEIVERS = FIXTURES / "orders-receivers"


@pytest.fixture(scope="module")
def receiver_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every non-HTTP row the receivers fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("receivers")
    compile_fixture(RECEIVERS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(RECEIVERS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["protocol"]), str(row["direction"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) != "http"
        }
    finally:
        workspace.close()


def test_rabbit_template_receives_derive_one_inbound_row_per_queue(receiver_rows):
    """`G-44`, AMQP half. Four receive shapes on four queues: raw `receive(String)`, a
    timed `receiveAndConvert(String, long)`, a typed `receiveAndConvert(String, PTR)`, and
    `receiveAndReply(String, callback)` — which is ONE inbound row, because the reply goes
    to the message's own `replyTo` and no argument names it."""
    expected = {
        ("amqp", "inbound", "recv.orders.raw"),
        ("amqp", "inbound", "recv.orders.converted"),
        ("amqp", "inbound", "recv.orders.typed"),
        ("amqp", "inbound", "recv.orders.rpc"),
    }
    missing = expected - receiver_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(receiver_rows)}"
    assert ("amqp", "outbound", "recv.orders.rpc") not in receiver_rows, (
        "receiveAndReply derived an OUTBOUND row on the receive queue; the reply address is per-message"
    )
```

- [ ] **Step 3: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/e2e/test_jms_and_amqp_delivered.py -q`
Expected: FAIL — `missing [('amqp', 'inbound', 'recv.orders.converted'), …]. Derived: []`.

- [ ] **Step 4: Add the rows to `spring-rabbit-template.yml`**

In the `methods:` list of `src/sextant/catalogs/spring-rabbit-template.yml`, after the existing `convertAndSend` rows, add (per-row `direction: inbound` is the `spring-pubsub.yml:82` precedent; `body_arg` on a `ParameterizedTypeReference` reads through `type_carriers` exactly as `spring-resttemplate.yml:25` does — add `type_carriers: [org.springframework.core.ParameterizedTypeReference]` under `matches:` if the file has none):

```yaml
    # `G-44`, the RECEIVE half. MEASURED spring-rabbit 3.1.4 (`javap -s`, pasted in
    # scripts/probes/w59_template_receive_halves.md): nine overloads take the queue name at
    # argument 0. The destination-less ones read the configured default queue and stay
    # outside, on the line `convertAndSend(Object)` already sits on.
    - { name: receive, arity: 1, descriptor: "(Ljava/lang/String;)Lorg/springframework/amqp/core/Message;",
        channel_arg: 0, direction: inbound }
    - { name: receive, arity: 2, descriptor: "(Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;",
        channel_arg: 0, direction: inbound }
    - { name: receiveAndConvert, arity: 1, descriptor: "(Ljava/lang/String;)Ljava/lang/Object;",
        channel_arg: 0, direction: inbound }
    - { name: receiveAndConvert, arity: 2, descriptor: "(Ljava/lang/String;J)Ljava/lang/Object;",
        channel_arg: 0, direction: inbound }
    - { name: receiveAndConvert, arity: 2,
        descriptor: "(Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;",
        channel_arg: 0, body_arg: 1, direction: inbound }
    - { name: receiveAndConvert, arity: 3,
        descriptor: "(Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;",
        channel_arg: 0, body_arg: 2, direction: inbound }
    # `receiveAndReply` is a receive whose reply goes to the message's OWN `replyTo`: one
    # inbound row on the queue and no outbound row, because no argument names the reply
    # address and publishing the receive queue as it would be a wrong row.
    - { name: receiveAndReply, arity: 2,
        descriptor: "(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z",
        channel_arg: 0, direction: inbound }
    - { name: receiveAndReply, arity: 4,
        descriptor: "(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z",
        channel_arg: 0, direction: inbound }
    - { name: receiveAndReply, arity: 3,
        descriptor: "(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z",
        channel_arg: 0, direction: inbound }
```

Then in `slice.outside`, remove `receive, receiveAndConvert, receiveAndReply` from the `RabbitTemplate` entry at line ~133 and replace that entry with one naming ONLY the destination-less overloads:

```yaml
    - owner: org.springframework.amqp.rabbit.core.RabbitTemplate
      method_names: [receive, receiveAndConvert, receiveAndReply]
      why: >
        The overloads WITHOUT a queue name at argument 0 — `receive()`, `receive(long)`,
        `receiveAndConvert()`, `receiveAndConvert(long)`, `receiveAndConvert(PTR)`,
        `receiveAndConvert(long, PTR)`, `receiveAndReply(callback…)` — read the template's
        configured default queue, which is configuration this catalog does not join. The
        nine overloads that DO name the queue are read above (`G-44`).
```

(`tests/architecture/test_catalog_slice_coverage.py` keys on method NAMES, so a name that is both read and outside is legal only when the `why` states which overloads are which — that is what the paragraph above does. If the test rejects the split, list the outside overloads by descriptor in the `why` and keep the name out of `method_names`; run the test to find out which reading it takes.)

Update the `measured:` block to cite the probe Task 1 Step 6 writes: `by: scripts/probes/w59_template_receive_halves.md`, versions `["3.1.4"]`, artifact `org.springframework.amqp:spring-rabbit`.

- [ ] **Step 5: Run the intention test, then the near-miss gates**

Run: `.venv/bin/python -m pytest tests/e2e/test_jms_and_amqp_delivered.py -q`
Expected: PASS (1 test).

Run: `.venv/bin/python -m pytest tests/architecture -q -n 4`
Expected: `test_every_cited_version_appears_in_the_probe_that_is_cited` FAILS naming `scripts/probes/w59_template_receive_halves.md` as missing — Step 6 writes it.

- [ ] **Step 6: Write the probe**

Create `scripts/probes/w59_template_receive_halves/run.sh` and `sweep.py` by copying `scripts/probes/w58_micronaut_quarkus_annotations/{run.sh,sweep.py}` and changing: the `for artifact in` list to `org.springframework.amqp:spring-rabbit:3.1.4`, `org.springframework:spring-jms:6.1.6`, `org.springframework.kafka:spring-kafka:3.1.4`, `io.awspring.cloud:spring-cloud-aws-sqs:3.1.1`; the `CLAIMS` tuple replaced by a `METHODS` tuple of `(coordinate, internal class, method-name regex)` — `("org.springframework.amqp:spring-rabbit:3.1.4", "org/springframework/amqp/rabbit/core/RabbitTemplate", r"receive\w*")` and the same for `org/springframework/jms/core/JmsTemplate`, `org/springframework/kafka/core/KafkaTemplate`, `io/awspring/cloud/sqs/operations/SqsTemplate`; and `main()` printing, per class, a table `| # | method | descriptor | argument 0 type | addressable |` where `addressable` is `**yes**` when the descriptor starts with `(Ljava/lang/String;` and `no` otherwise (the `_javap(jar, internal, "-s")` output has each descriptor on the line after its signature — parse with `re.findall(r"public .*? (\w+)\(.*?\n\s+descriptor: (\S+)", text)`). Keep the provenance table (`| what the run read | 3.1.4 | 6.1.6 | 3.6.2 | 3.1.1 |`) and the sentence "**Every version in the headers below is the one the JAR itself reported** … and **not the version the coordinate list asked for**" — `tests/architecture/test_probe_provenance.py` requires both.

Write `scripts/probes/w59_template_receive_halves.md` with a header (question, `**Version scope (§5.4).** Read against **spring-rabbit 3.1.4, spring-jms 6.1.6, spring-kafka 3.1.4 and spring-cloud-aws-sqs 3.1.1** …`, how to run, expectation table with rows "argument 0 is a `String` → addressable, one row per call" / "argument 0 is a `Consumer<…Options>` → the queue is inside a lambda; not addressable by `single_call`"), a `---` rule, then the script's output pasted verbatim.

Run: `bash scripts/probes/w59_template_receive_halves/run.sh > /tmp/w59.out && cat /tmp/w59.out >> scripts/probes/w59_template_receive_halves.md`
Then: `.venv/bin/python -m pytest tests/architecture -q -n 4`
Expected: all pass except `test_every_shipped_catalog_has_a_declining_test` if it now names `spring-rabbit-template` — it will not, because that catalog already has one; confirm with `grep -n 'declines("spring-rabbit-template")' -r tests/`.

- [ ] **Step 7: The declining test for the new rows**

Append to `tests/application/test_call_engines.py`, following the file's own `_single_call_rows` helper (read the nearest `@pytest.mark.declines("spring-rabbit-template")` test in that file and copy its fact-building calls exactly — the helper names differ per section of the file, so the executor reads them rather than this plan guessing them):

```python
@pytest.mark.declines("spring-rabbit-template")
@pytest.mark.pins("single_call.descriptor-pins-the-overload")
def test_a_rabbit_receive_from_the_default_queue_derives_nothing(tmp_path: Path):
    """§10 near-miss for `G-44`'s receive rows: `receive(long)` — a timeout, no queue —
    reads the template's configured default queue. It shares its NAME with the addressable
    overload and differs only in descriptor, which is what the descriptor pin is for. A
    row here would publish a queue nobody named."""
    rows = <the file's single_call helper>(
        tmp_path,
        catalog_id="spring-rabbit-template",
        owner="org/springframework/amqp/rabbit/core/RabbitTemplate#",
        name="receive",
        descriptor="(J)Lorg/springframework/amqp/core/Message;",
        arguments=[{"kind": "long", "value": 500}],
    )
    assert rows == []
```

Run: `.venv/bin/python -m pytest tests/application/test_call_engines.py -q -k default_queue`
Expected: PASS. Then `python scripts/guard_check.py single_call.descriptor-pins-the-overload` — Expected: the guard is noticed (exit 0, output names the test).

- [ ] **Step 8: Prime the fixture in CI and register the test**

In `.github/workflows/pr.yml`, after `mvn -q -B -f fixtures/orders-quarkus/pom.xml compile`, add:

```yaml
          mvn -q -B -f fixtures/orders-receivers/pom.xml compile
```

In `docs/java-kotlin-delivery-list.md`, remove `JMS and AMQP` from the ```intention-test-missing block (the file now exists; `test_every_feature_has_an_intention_test` would fail as an unexpected pass otherwise).

Run: `.venv/bin/python scripts/coverage_versions.py && .venv/bin/python scripts/coverage_matrix.py && bash scripts/probes/w19_catalog_surface/run.sh > /dev/null && bash scripts/probes/w19b_type_and_annotation_surface/run.sh > /dev/null`
Then the gate: `JAVA_HOME=… bash scripts/check.sh`
Expected: all gates passed.

- [ ] **Step 9: Update COVERAGE §5.9 and commit**

In `docs/COVERAGE.md`, the JMS/AMQP table (§5.9): change the `RabbitTemplate` row's tier text to say the receive half is read — "`receive`, `receiveAndConvert`, `receiveAndReply` — every overload naming the queue at argument 0 (nine, spring-rabbit 3.1.4, `scripts/probes/w59_template_receive_halves.md`); the destination-less overloads read the configured default queue and derive nothing. `receiveAndReply` is one INBOUND row: the reply goes to the message's own `replyTo`." Re-run `scripts/coverage_matrix.py` after editing.

```bash
git add fixtures/orders-receivers src/sextant/catalogs/spring-rabbit-template.yml tests/e2e/test_jms_and_amqp_delivered.py tests/application/test_call_engines.py scripts/probes/w59_template_receive_halves* .github/workflows/pr.yml docs/COVERAGE.md docs/java-kotlin-delivery-list.md
git commit -m "feat(amqp): RabbitTemplate's receive half derives — nine overloads naming the queue, one inbound row each (G-44)"
```

### Task 2: `JmsTemplate` receive rows

**Files:**
- Create: `fixtures/orders-receivers/src/main/java/com/acme/recv/JmsReceivers.java`
- Modify: `src/sextant/catalogs/spring-jms-template.yml` (`methods:` and `slice.outside`, lines 78–131)
- Modify: `tests/e2e/test_jms_and_amqp_delivered.py` (one test appended)
- Modify: `tests/application/test_call_engines.py` (one declining test)

**Interfaces:**
- Consumes: `receiver_rows` from Task 1.

**Measured, spring-jms 6.1.6, overloads with the destination NAME at argument 0** (the `jakarta.jms.Destination` overloads take an object built elsewhere and stay outside — the `createQueue` link `jakarta-jms.yml` follows is a different owner):

```
receive(String)                                (Ljava/lang/String;)Ljakarta/jms/Message;
receiveSelected(String, String)                (Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;   -- (destinationName, selector)
receiveAndConvert(String)                      (Ljava/lang/String;)Ljava/lang/Object;
receiveSelectedAndConvert(String, String)      (Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;
```

**Trap:** `receiveSelected(String)` and `receiveSelectedAndConvert(String)` — arity 1 — take the SELECTOR, not a destination (spring-jms's own javadoc; the descriptor is identical to `receive(String)`'s parameter list). They read the default destination. They are pinned OUT by the declining test below, because a name-and-arity match would publish a selector expression as a queue name.

- [ ] **Step 1: Fixture**

```java
package com.acme.recv;

import jakarta.jms.Message;
import org.springframework.jms.core.JmsTemplate;

public class JmsReceivers {
    private final JmsTemplate template;

    public JmsReceivers(JmsTemplate template) {
        this.template = template;
    }

    public Message pollRaw() {
        return template.receive("recv.jms.raw");
    }

    public Message pollSelected() {
        return template.receiveSelected("recv.jms.selected", "priority > 5");
    }

    public Object pollConverted() {
        return template.receiveAndConvert("recv.jms.converted");
    }

    public Object pollSelectedConverted() {
        return template.receiveSelectedAndConvert("recv.jms.selected.converted", "kind = 'order'");
    }

    /** The trap: arity 1 `receiveSelected` takes a SELECTOR and reads the default destination. */
    public Message pollDefaultSelected() {
        return template.receiveSelected("priority > 5");
    }
}
```

- [ ] **Step 2: Failing test** — append to `tests/e2e/test_jms_and_amqp_delivered.py`:

```python
def test_jms_template_receives_derive_one_inbound_row_per_destination_name(receiver_rows):
    """`G-44`, JMS half. Four shapes naming the destination at argument 0. And the trap:
    `receiveSelected("priority > 5")` — arity 1 — takes a SELECTOR and reads the default
    destination; a name-and-arity read would publish the selector as a queue."""
    expected = {
        ("jms", "inbound", "recv.jms.raw"),
        ("jms", "inbound", "recv.jms.selected"),
        ("jms", "inbound", "recv.jms.converted"),
        ("jms", "inbound", "recv.jms.selected.converted"),
    }
    missing = expected - receiver_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(receiver_rows)}"
    assert ("jms", "inbound", "priority > 5") not in receiver_rows, "a selector was published as a queue"
```

Run: `.venv/bin/python -m pytest tests/e2e/test_jms_and_amqp_delivered.py -q -k jms`
Expected: FAIL, `Derived:` carries only the amqp rows.

- [ ] **Step 3: Rows** — in `spring-jms-template.yml`'s `methods:`:

```yaml
    # `G-44`, the RECEIVE half. MEASURED spring-jms 6.1.6 (w59): the four overloads whose
    # argument 0 is the destination NAME. The `jakarta.jms.Destination` overloads take an
    # object built elsewhere and stay outside; `receiveSelected(String)` at arity 1 takes a
    # SELECTOR — same parameter list as `receive(String)` — and is pinned out by descriptor
    # AND name below, because `(Ljava/lang/String;)Ljakarta/jms/Message;` is both of them.
    - { name: receive, arity: 1, descriptor: "(Ljava/lang/String;)Ljakarta/jms/Message;",
        channel_arg: 0, direction: inbound }
    - { name: receiveSelected, arity: 2, descriptor: "(Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;",
        channel_arg: 0, direction: inbound }
    - { name: receiveAndConvert, arity: 1, descriptor: "(Ljava/lang/String;)Ljava/lang/Object;",
        channel_arg: 0, direction: inbound }
    - { name: receiveSelectedAndConvert, arity: 2, descriptor: "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;",
        channel_arg: 0, direction: inbound }
```

Note `single_call` matches on `name` + `arity` + `descriptor`: `receiveSelected` arity 1 shares NO row above (arity 2 only), so it derives nothing — which is the required outcome. Update `slice.outside` (lines 111–118): replace the `receive, receiveSelected, receiveAndConvert, receiveSelectedAndConvert` entry's `why` with one stating that the `Destination`-typed overloads and the arity-1 selector overloads are what remain outside, and why. Update `measured:` to cite w59 with versions `["6.1.6"]`.

- [ ] **Step 4: Run, declining test, gate, commit**

Run: `.venv/bin/python -m pytest tests/e2e/test_jms_and_amqp_delivered.py -q` — Expected: 2 passed.

Declining test (append to `tests/application/test_call_engines.py`, same helper as Task 1 Step 7):

```python
@pytest.mark.declines("spring-jms-template")
@pytest.mark.pins("single_call.descriptor-pins-the-overload")
def test_a_jms_receive_selected_at_arity_one_derives_nothing(tmp_path: Path):
    """`receiveSelected(String)` takes a SELECTOR and reads the default destination.
    Same name, same parameter list as `receive(String)`; only the arity-2 overload names
    a destination. A row here would publish `priority > 5` as a queue."""
    rows = <helper>(tmp_path, catalog_id="spring-jms-template",
        owner="org/springframework/jms/core/JmsTemplate#", name="receiveSelected",
        descriptor="(Ljava/lang/String;)Ljakarta/jms/Message;",
        arguments=[{"kind": "string", "value": "priority > 5"}])
    assert rows == []
```

Gate, then COVERAGE §5.9 `JmsTemplate` row updated as in Task 1 Step 9, then:

```bash
git commit -am "feat(jms): JmsTemplate's receive half derives — the four overloads naming the destination; the arity-1 selector form stays silent (G-44)"
```

### Task 3: `KafkaTemplate.receive`

**Files:**
- Create: `fixtures/orders-receivers/src/main/java/com/acme/recv/KafkaReceivers.java`
- Modify: `src/sextant/catalogs/spring-kafka-template.yml`
- Create: `tests/e2e/test_kafka_delivered.py`
- Modify: `docs/java-kotlin-delivery-list.md` (`intention-test-missing`: remove `Kafka`)

**Measured, spring-kafka 3.1.4:**

```
receive(String, int, long, Duration)                        (Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;
receive(Collection<TopicPartitionOffset>, Duration)         (Ljava/util/Collection;Ljava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecords;
```

Only the first names a topic in an argument. The second takes `TopicPartitionOffset` objects built elsewhere — a `channel_via` on `TopicPartitionOffset.<init>(String, int, long)` would read it, but constructor `channel_via` is not a form `single_call` has (`kafka-consumer.yml`'s `channel_via` rows are all static factories). It stays outside, stated.

- [ ] **Step 1: Fixture**

```java
package com.acme.recv;

import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.core.KafkaTemplate;

public class KafkaReceivers {
    private final KafkaTemplate<String, String> template;

    public KafkaReceivers(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public ConsumerRecord<String, String> peekOne() {
        return template.receive("recv.orders.replay", 0, 42L, Duration.ofSeconds(5));
    }
}
```

- [ ] **Step 2: Failing test** — `tests/e2e/test_kafka_delivered.py`, same module fixture shape as Task 1's file but named `kafka_rows` and filtered to `protocol == "kafka"`; one test:

```python
def test_kafka_template_receive_derives_an_inbound_row_on_the_topic(kafka_rows):
    """`G-44`, Kafka. `KafkaTemplate.receive(String topic, int partition, long offset,
    Duration)` — spring-kafka 3.1.4 — is a synchronous read of one record: an inbound
    boundary on the topic at argument 0."""
    assert ("kafka", "inbound", "recv.orders.replay") in kafka_rows, sorted(kafka_rows)
```

Run: expected FAIL.

- [ ] **Step 3: Row**

```yaml
    - { name: receive, arity: 4,
        descriptor: "(Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;",
        channel_arg: 0, direction: inbound }
```

plus a `slice.outside` entry for `receive` naming the `Collection<TopicPartitionOffset>` overload and why (constructor-built addresses; no `channel_via` form for a constructor). `measured:` → w59, `["3.1.4"]`.

- [ ] **Step 4: Run, decline, gate, commit**

Declining test: `receive(Collection, Duration)` with `arguments=[{"kind":"object"}, {"kind":"object"}]` derives `[]`, marker `@pytest.mark.declines("spring-kafka-template")`. Remove `Kafka` from `intention-test-missing`. Gate. COVERAGE §5.8 `KafkaTemplate` row: add the receive sentence.

```bash
git commit -am "feat(kafka): KafkaTemplate.receive(topic, partition, offset, timeout) derives an inbound row (G-44)"
```

### Task 4: `SqsTemplate` receive — measured, not derivable; recorded

**Files:**
- Modify: `src/sextant/catalogs/spring-sqs-template.yml` (`slice.outside`)
- Modify: `docs/COVERAGE.md` §5.10, `docs/java-kotlin-delivery-list.md`

**Measured, spring-cloud-aws-sqs 3.1.1:** every receive overload — `receive`, `receiveMany`, `receiveAsync`, `receiveManyAsync` — takes `Consumer<SqsReceiveOptions>` at argument 0 and the queue is named INSIDE that lambda (`opts -> opts.queue("orders")`). No argument carries a string. `single_call` reads arguments; reading a call inside the lambda body that the argument names is the receiver-chain form (Category B).

- [ ] **Step 1: Record it in the catalog**

In `spring-sqs-template.yml`'s `slice.outside`, make the `receive*` entry's `why` state exactly the measurement above and name the spec it waits on. Do not add rows.

- [ ] **Step 2: Record it in the register and COVERAGE**

In `docs/java-kotlin-delivery-list.md`, under "Moved to spec work", add: `G-44`'s SQS quarter — `SqsTemplate.receive*(Consumer<SqsReceiveOptions>)`: the queue is `opts.queue("…")` inside the options lambda; Category B. Change the `G-44` row in §1's JMS/AMQP table to say: "three of four halves derive (Tasks 1–3); SQS's needs the lambda-body read".

In COVERAGE §5.10, the `SqsTemplate` row: "**Boundary — receive is unread, and the reason is measured:** …".

Run: `.venv/bin/python -m pytest tests/architecture -q -n 4` — Expected: pass.

```bash
git commit -am "docs(sqs): SqsTemplate's receive half is a lambda-body read — measured, recorded against Category B (G-44)"
```

---

## Part B — new catalogs

### Task 5: Kafka Streams (`G-31`)

**Files:**
- Create: `fixtures/orders-streams/pom.xml` (kafka-streams 3.6.2 + kafka-clients 3.6.2, exclusions `*`)
- Create: `fixtures/orders-streams/src/main/java/com/acme/streams/OrderTopology.java`
- Create: `src/sextant/catalogs/kafka-streams.yml`
- Create: `scripts/probes/w60_kafka_streams_surface/{run.sh,sweep.py}`, `scripts/probes/w60_kafka_streams_surface.md`
- Modify: `tests/e2e/test_kafka_delivered.py` (a second module fixture + two tests)
- Modify: `tests/application/test_call_engines.py` (declining test), `.github/workflows/pr.yml`, `docs/COVERAGE.md` §5.8

**Measured, kafka-streams 3.6.2 (`javap -s`), the topic-addressing methods:**

```
StreamsBuilder.stream(String)                             (Ljava/lang/String;)L…/KStream;                       inbound
StreamsBuilder.stream(String, Consumed)                   (Ljava/lang/String;L…/Consumed;)L…/KStream;           inbound
StreamsBuilder.stream(Collection<String>[, Consumed])     (Ljava/util/Collection;…)                             inbound, channel_via List.of / Arrays.asList
StreamsBuilder.stream(Pattern[, Consumed])                (Ljava/util/regex/Pattern;…)                          inbound, channel_via Pattern.compile
StreamsBuilder.table(String[, Consumed][, Materialized])  four overloads, String at 0                           inbound
StreamsBuilder.globalTable(String[, Consumed][, Materialized])  four overloads, String at 0                     inbound
KStream.to(String)                                        (Ljava/lang/String;)V                                 outbound
KStream.to(String, Produced)                              (Ljava/lang/String;L…/Produced;)V                     outbound
KStream.to(TopicNameExtractor[, Produced])                dynamic topic — derives nothing, stated
KStream.through(String[, Produced])                       deprecated; outbound AND inbound on one topic — outside, stated
Topology.addSource(String name, String... topics)         topics are a VARARGS ARRAY at argument 1 — see Step 4
Topology.addSink(String name, String topic, String... parents)  topic at argument 1
```

`KStream` is an INTERFACE and the call site's owner is the declared type: a `KStream<K,V>` local carries owner `org/apache/kafka/streams/kstream/KStream#` — the `owner:` list names the interface, exactly as `spring-jms-template.yml` names `JmsOperations`.

- [ ] **Step 1: Fixture**

```java
package com.acme.streams;

import java.util.List;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;

/** A topology the way the Kafka Streams quickstart writes one. */
public class OrderTopology {

    public Topology build() {
        StreamsBuilder builder = new StreamsBuilder();
        KStream<String, String> orders = builder.stream("streams.orders.placed");
        KStream<String, String> audit = builder.stream(List.of("streams.audit.a", "streams.audit.b"));
        KTable<String, String> customers = builder.table("streams.customers");
        builder.globalTable("streams.rates");
        orders.mapValues(String::toUpperCase).to("streams.orders.shouted");
        audit.to("streams.audit.merged");
        customers.toStream().to("streams.customers.changelog");
        return builder.build();
    }

    public Topology processorApi() {
        Topology topology = new Topology();
        topology.addSource("src", "streams.pa.in.a", "streams.pa.in.b");
        topology.addSink("snk", "streams.pa.out", "src");
        return topology;
    }
}
```

- [ ] **Step 2: Failing tests** — in `tests/e2e/test_kafka_delivered.py`, add `STREAMS = FIXTURES / "orders-streams"`, a module fixture `streams_rows` (same shape as `kafka_rows`, over `STREAMS`), and:

```python
def test_a_streams_dsl_topology_derives_every_source_and_sink(streams_rows):
    """`G-31`. `StreamsBuilder.stream/table/globalTable` consume the topic at argument 0
    (a `Collection` through `List.of`); `KStream.to` produces to it. kafka-streams 3.6.2."""
    expected = {
        ("kafka", "inbound", "streams.orders.placed"),
        ("kafka", "inbound", "streams.audit.a"),
        ("kafka", "inbound", "streams.audit.b"),
        ("kafka", "inbound", "streams.customers"),
        ("kafka", "inbound", "streams.rates"),
        ("kafka", "outbound", "streams.orders.shouted"),
        ("kafka", "outbound", "streams.audit.merged"),
        ("kafka", "outbound", "streams.customers.changelog"),
    }
    missing = expected - streams_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(streams_rows)}"


def test_a_processor_api_topology_derives_its_sink(streams_rows):
    """`Topology.addSink(name, topic, parents…)` names the topic at argument 1. `addSource`
    takes its topics as a VARARGS array at argument 1 — see the catalog for what that
    derives; this test pins the sink and Step 4 decides the source."""
    assert ("kafka", "outbound", "streams.pa.out") in streams_rows, sorted(streams_rows)
```

Run: expected FAIL, `Derived: []`.

- [ ] **Step 3: Catalog** — `src/sextant/catalogs/kafka-streams.yml`:

```yaml
id: kafka-streams
displayName: Apache Kafka Streams
style: single_call
protocol: kafka
direction: inbound
detect:
  coordinates: ["org.apache.kafka:kafka-streams"]
measured:
  - { artifact: org.apache.kafka:kafka-streams, versions: ["3.6.2"],
      identity: reported, by: scripts/probes/w60_kafka_streams_surface.md }
requires: [call_site, string_constants]
matches:
  owner:
    - org.apache.kafka.streams.StreamsBuilder
    - org.apache.kafka.streams.kstream.KStream
    - org.apache.kafka.streams.kstream.KTable
    - org.apache.kafka.streams.Topology
  methods:
    # SOURCES — the topic at argument 0. MEASURED kafka-streams 3.6.2 (w60).
    - { name: stream, arity: 1, descriptor: "(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KStream;", channel_arg: 0 }
    - { name: stream, arity: 2, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;", channel_arg: 0 }
    - { name: stream, arity: 1, descriptor: "(Ljava/util/Collection;)Lorg/apache/kafka/streams/kstream/KStream;", channel_arg: 0,
        channel_via:
          - { owner: java.util.List, method: of, arg: all_strings }
          - { owner: java.util.Arrays, method: asList, arg: all_strings }
          - { owner: java.util.Collections, method: singletonList, arg: 0 } }
    - { name: stream, arity: 2, descriptor: "(Ljava/util/Collection;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;", channel_arg: 0,
        channel_via:
          - { owner: java.util.List, method: of, arg: all_strings }
          - { owner: java.util.Arrays, method: asList, arg: all_strings }
          - { owner: java.util.Collections, method: singletonList, arg: 0 } }
    - { name: stream, arity: 1, descriptor: "(Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/kstream/KStream;", channel_arg: 0,
        channel_via: [{ owner: java.util.regex.Pattern, method: compile, arg: 0 }] }
    - { name: stream, arity: 2, descriptor: "(Ljava/util/regex/Pattern;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;", channel_arg: 0,
        channel_via: [{ owner: java.util.regex.Pattern, method: compile, arg: 0 }] }
    - { name: table, arity: 1, descriptor: "(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KTable;", channel_arg: 0 }
    - { name: table, arity: 2, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KTable;", channel_arg: 0 }
    - { name: table, arity: 2, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/KTable;", channel_arg: 0 }
    - { name: table, arity: 3, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/KTable;", channel_arg: 0 }
    - { name: globalTable, arity: 1, descriptor: "(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/GlobalKTable;", channel_arg: 0 }
    - { name: globalTable, arity: 2, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/GlobalKTable;", channel_arg: 0 }
    - { name: globalTable, arity: 2, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/GlobalKTable;", channel_arg: 0 }
    - { name: globalTable, arity: 3, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/GlobalKTable;", channel_arg: 0 }
    # SINKS — `KStream.to(String[, Produced])`. `to(TopicNameExtractor…)` chooses the topic
    # per record at runtime and derives nothing; `through` is deprecated and is a sink AND
    # a source on one topic, so it is outside rather than half-read.
    - { name: to, arity: 1, descriptor: "(Ljava/lang/String;)V", channel_arg: 0, direction: outbound }
    - { name: to, arity: 2, descriptor: "(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Produced;)V", channel_arg: 0, direction: outbound }
    # PROCESSOR API. `addSink(name, topic, parents…)` — the topic at argument 1.
    - { name: addSink, arity: 3, descriptor: "(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;", channel_arg: 1, direction: outbound }
shape_model: json
slice:
  outside:
    - owner: org.apache.kafka.streams.kstream.KStream
      method_names: [through, repartition]
      why: >
        `through(String)` is deprecated and is a sink and a source on ONE topic in one call;
        a row of either direction alone would be half of it. `repartition` names no topic
        (Streams generates one).
    - owner: org.apache.kafka.streams.Topology
      method_names: [addSource]
      why: >
        Topics arrive as a VARARGS array at argument 1 (`String...`). Step 4 of the task
        that wrote this catalog measured what `single_call` reads from an array argument
        and this paragraph records the answer.
```

Add to `matches:` before `owner:` if the loader requires it for `KTable.toStream().to(...)`: nothing — `to` is called on the `KStream` that `toStream()` returns, and the call site's owner is `KStream`. Verify with the fixture rather than assuming (Step 5).

- [ ] **Step 4: Measure the varargs form**

Run the analysis on the fixture and print what `addSource` produced:

```bash
W=$(mktemp -d) && .venv/bin/sextant module analyze fixtures/orders-streams --workspace $W > /dev/null 2>&1
.venv/bin/python - $W <<'PY'
import sys; from pathlib import Path
from sextant.storage.duckdb.workspace import DuckDbWorkspace
w = DuckDbWorkspace(Path(sys.argv[1]) / "workspace.duckdb")
print([ (r["direction"], r["path"]) for r in w.query("endpoints") if "pa.in" in str(r["path"]) ])
print([ (s["target"]["name"], s.get("arguments")) for s in w.query("call_sites") if s["target"]["name"] == "addSource" ])
PY
```

Expected: the second line shows argument 1 as `{"kind": "array", "elements": [{"kind":"string","value":"streams.pa.in.a"}, …]}` (extractor capability 9.15). If `single_call` derives one row per element when `channel_arg: 1` names an array argument — the first line prints both topics — add the `addSource` rows (descriptors: `(Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` arity 2 `channel_arg: 1`, and the `AutoOffsetReset`/`TimestampExtractor`-prefixed overloads with the array one position later each) and move the pin into `test_a_processor_api_topology_derives_its_sink`. If it derives nothing, leave `addSource` outside with the `why` above completed by the sentence "an array argument is not read by `single_call` (measured 2026-…)", and add that as a Category B line in the register. Either answer is a finished task; a guess is not.

- [ ] **Step 5: Run the tests, then the probe**

Run: `.venv/bin/python -m pytest tests/e2e/test_kafka_delivered.py -q` — Expected: PASS (all).

Probe `w60_kafka_streams_surface`: copy the `w59` harness, artifacts `org.apache.kafka:kafka-streams:3.6.2`, classes `StreamsBuilder`, `kstream/KStream`, `kstream/KTable`, `Topology`, method regex `stream|table|globalTable|to|through|addSource|addSink`, column "topic argument" = position of the first `Ljava/lang/String;` / `Ljava/util/Collection;` / `Ljava/util/regex/Pattern;` / `[Ljava/lang/String;` in the descriptor. Document with version scope `**kafka-streams 3.6.2**`.

- [ ] **Step 6: Declining test**

```python
@pytest.mark.declines("kafka-streams")
@pytest.mark.pins("single_call.descriptor-pins-the-overload")
def test_a_streams_sink_with_a_topic_name_extractor_derives_nothing(tmp_path: Path):
    """`KStream.to(TopicNameExtractor)` picks the topic per record at runtime. Same name
    and arity as `to(String)`; only the descriptor tells them apart, and a row here would
    publish the extractor's class name as a topic."""
    rows = <helper>(tmp_path, catalog_id="kafka-streams",
        owner="org/apache/kafka/streams/kstream/KStream#", name="to",
        descriptor="(Lorg/apache/kafka/streams/processor/TopicNameExtractor;)V",
        arguments=[{"kind": "object"}])
    assert rows == []
```

- [ ] **Step 7: Discipline, COVERAGE, gate, commit**

Prime `fixtures/orders-streams` in `pr.yml`. `coverage_versions.py`, `coverage_matrix.py`, both w19 probes. COVERAGE §5.8: replace the Kafka Streams row (currently tier `A`/"no catalog") with "✅ shipped (`kafka-streams.yml`, 3.6.2, w60): DSL sources and sinks, Processor API sink; `addSource` per Step 4's answer; `to(TopicNameExtractor)` and `through` stated". Register: `G-31` moves to the `closed` block ONLY after CI; until then stays in the Kafka row.

```bash
git commit -am "feat(kafka): Kafka Streams derives — DSL sources, sinks and the Processor API sink, one row per topic (G-31)"
```

### Task 6: Javalin — the flat registration form

**Files:**
- Create: `fixtures/orders-javalin/pom.xml` (io.javalin:javalin:6.4.0, exclusions `*`)
- Create: `fixtures/orders-javalin/src/main/java/com/acme/jv/OrderApp.java`
- Create: `src/sextant/catalogs/javalin.yml`
- Create: probe `scripts/probes/w61_javalin_surface/…` + `.md`
- Modify: `tests/e2e/test_rest_inbound_delivered.py` (fixture + one test + one strict-xfail test), `tests/application/test_call_engines.py`, `pr.yml`, COVERAGE §5.1, register

**Measured, javalin 6.4.0:** `Javalin implements JavalinDefaultRoutingApi<Javalin>`; the verbs are `default` methods on that interface — `get(String, Handler)` `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;`, with a `RouteRole...` overload `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;`; same for `post`, `put`, `delete`, `patch`, `head`, `options`; and `addHttpHandler(HandlerType, String, Handler[, RouteRole...])` with the verb as an ENUM at argument 0 (`single_call` has `http_method:` per row and no "method from argument" word — `addHttpHandler` stays outside, stated). A call `app.get(...)` on a `Javalin`-typed local has owner `io/javalin/Javalin#`; on a `JavalinDefaultRoutingApi`-typed one, the interface — both go in `owner:`.

**Not this task, filed against Category B by name `javalin-apibuilder`:** `config.router.apiBuilder(() -> { path("/orders", () -> { get("/{id}", h); }); })` — static `ApiBuilder.get` inside a lambda inside `path`. A `single_call` row on `ApiBuilder.get` would publish `/{id}` without `/orders`. The strict-xfail test pins that this form derives the full path once Category B lands.

- [ ] **Step 1: Fixture**

```java
package com.acme.jv;

import io.javalin.Javalin;
import io.javalin.apibuilder.ApiBuilder;

public class OrderApp {
    public Javalin flat() {
        Javalin app = Javalin.create();
        app.get("/jv/orders", ctx -> ctx.result("[]"));
        app.get("/jv/orders/{id}", ctx -> ctx.result("{}"));
        app.post("/jv/orders", ctx -> ctx.status(201));
        app.delete("/jv/orders/{id}", ctx -> ctx.status(204));
        return app;
    }

    /** The nested form — Category B (`javalin-apibuilder`); derives nothing until then. */
    public Javalin nested() {
        return Javalin.create(config -> config.router.apiBuilder(() -> {
            ApiBuilder.path("/jv/nested", () -> {
                ApiBuilder.get("/{id}", ctx -> ctx.result("{}"));
            });
        }));
    }
}
```

- [ ] **Step 2: Failing tests** — in `tests/e2e/test_rest_inbound_delivered.py`, `JAVALIN = FIXTURES / "orders-javalin"`, a module fixture `javalin_routes` returning `{(direction, method, path)}` for HTTP rows, and:

```python
def test_javalin_flat_registrations_derive_every_route(javalin_routes):
    """`app.get("/path", handler)` on a `Javalin` — the form the Javalin front page
    shows. javalin 6.4.0: the verbs are default methods on `JavalinDefaultRoutingApi`,
    path at argument 0, handler a lambda at 1 (the handler recorded is the calling
    method, as for every `single_call` inbound row)."""
    expected = {
        ("inbound", "GET", "/jv/orders"), ("inbound", "GET", "/jv/orders/{id}"),
        ("inbound", "POST", "/jv/orders"), ("inbound", "DELETE", "/jv/orders/{id}"),
    }
    missing = expected - javalin_routes
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(javalin_routes)}"
    assert ("inbound", "GET", "/{id}") not in javalin_routes, (
        "the ApiBuilder inner path was published WITHOUT its `path(…)` prefix — a wrong row"
    )


@pytest.mark.xfail(strict=True, reason="javalin-apibuilder: nested ApiBuilder needs the receiver-chain walk (Category B)")
def test_javalin_api_builder_derives_the_composed_path(javalin_routes):
    assert ("inbound", "GET", "/jv/nested/{id}") in javalin_routes
```

- [ ] **Step 3: Catalog** — `src/sextant/catalogs/javalin.yml`, `style: single_call`, `protocol: http`, `direction: inbound`, `detect.coordinates: ["io.javalin:javalin"]`, `measured` → w61 `["6.4.0"]`, `owner: [io.javalin.Javalin, io.javalin.router.JavalinDefaultRoutingApi]`, and for each verb `v` in get/post/put/delete/patch/head/options two rows:

```yaml
    - { name: get, arity: 2, http_method: GET, url_arg: 0,
        descriptor: "(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;" }
    - { name: get, arity: 3, http_method: GET, url_arg: 0,
        descriptor: "(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;" }
```

(`url_arg` and `http_method` are the words `jakarta-websocket-programmatic.yml` and `spring-resttemplate.yml` use for an HTTP-addressed `single_call`; copy their spelling.) `slice.outside`: `addHttpHandler` (verb is an enum argument; no word reads it), `sse`, `ws`, `wsBefore/After`, `before/after` (filters, not routes), and `io.javalin.apibuilder.ApiBuilder` in full — "nested inside `path`; Category B `javalin-apibuilder`; a flat read would publish the inner segment alone".

- [ ] **Step 4: Run, probe, decline, discipline, commit**

Run the tests: expected 1 passed, 1 xfailed. Probe w61 over `io.javalin:javalin:6.4.0`, classes `io/javalin/router/JavalinDefaultRoutingApi` and `io/javalin/apibuilder/ApiBuilder`, method regex `get|post|put|delete|patch|head|options|addHttpHandler|path`. Declining test: `addHttpHandler(HandlerType, String, Handler)` with a string at argument 1 derives `[]` (`@pytest.mark.declines("javalin")`). Prime the fixture. COVERAGE §5.1: add a Javalin row "✅ flat form shipped (`javalin.yml`, 6.4.0, w61); **Boundary — `ApiBuilder` nesting derives nothing** (Category B `javalin-apibuilder`)". Register: `javalin-routing` stays in REST inbound until CI; add `javalin-apibuilder` beside it, tagged Category B in §4.

```bash
git commit -am "feat(http): Javalin's flat registrations derive; the ApiBuilder nesting is a stated Category B boundary (javalin-routing)"
```

### Task 7: Pekko Connectors Kafka (`alpakka-pekko`)

**Files:**
- Create: `fixtures/orders-pekko/pom.xml` (`org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0`, `org.apache.pekko:pekko-stream_2.13:1.1.2`, `org.apache.pekko:pekko-actor_2.13:1.1.2`, `org.apache.kafka:kafka-clients:3.6.2`, `org.scala-lang:scala-library:2.13.14` — all exclusions `*`; `mvn dependency:get` each first)
- Create: `fixtures/orders-pekko/src/main/java/com/acme/pk/OrderFlows.java`
- Create: `src/sextant/catalogs/pekko-connectors-kafka.yml`, probe `w62_pekko_kafka_surface`
- Modify: `tests/e2e/test_kafka_delivered.py`, `tests/application/test_call_engines.py`, `pr.yml`, COVERAGE §5.8, register

**Measured, pekko-connectors-kafka 1.1.0:** `Consumer.plainSource(ConsumerSettings, Subscription)` static on `org.apache.pekko.kafka.javadsl.Consumer`; `Subscriptions.topics(String...)` static, `([Ljava/lang/String;)Lorg/apache/pekko/kafka/AutoSubscription;`; `Subscriptions.topicPattern(String)`; `Subscriptions.assignment(TopicPartition...)`. The subscription is argument 1 of `plainSource`/`committableSource`/`atMostOnceSource`/`plainPartitionedSource`/`committablePartitionedSource`, built by the `Subscriptions` factory — the `channel_via` shape `kafka-consumer.yml` already uses for `List.of`. **Outbound:** `Producer.plainSink(ProducerSettings)` names no topic; the topic is on each `new ProducerRecord<>(topic, …)` flowing into the sink. No call names both the sink and the topic → outbound is a stated boundary.

**Also inside this task, measured first:** whether `channel_via … arg: all_strings` reads a VARARGS array argument (`Subscriptions.topics("a", "b")` arrives as one array). Same measurement as Task 5 Step 4; if arrays are unread, the row still derives for `Subscriptions.topics(String)` with one element only if the extractor passes single-element varargs as an array too — measure, and record the answer in the catalog. If nothing derives, `alpakka-pekko` moves to Category B with the measurement and the task ends there.

- [ ] **Step 1: Fixture**

```java
package com.acme.pk;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.pekko.kafka.ConsumerSettings;
import org.apache.pekko.kafka.Subscriptions;
import org.apache.pekko.kafka.javadsl.Consumer;
import org.apache.pekko.stream.javadsl.Source;

public class OrderFlows {
    public Source<ConsumerRecord<String, String>, Consumer.Control> placed(ConsumerSettings<String, String> settings) {
        return Consumer.plainSource(settings, Subscriptions.topics("pk.orders.placed"));
    }

    public Source<ConsumerRecord<String, String>, Consumer.Control> audit(ConsumerSettings<String, String> settings) {
        return Consumer.plainSource(settings, Subscriptions.topics("pk.audit.a", "pk.audit.b"));
    }
}
```

- [ ] **Step 2: Failing test** (in `test_kafka_delivered.py`, fixture `pekko_rows`):

```python
def test_pekko_consumer_sources_derive_one_inbound_row_per_subscribed_topic(pekko_rows):
    """`Consumer.plainSource(settings, Subscriptions.topics(…))` — pekko-connectors-kafka
    1.1.0. The topics are the varargs of a factory call at argument 1: the `channel_via`
    form `kafka-consumer.yml` uses for `List.of`."""
    expected = {("kafka", "inbound", "pk.orders.placed"), ("kafka", "inbound", "pk.audit.a"), ("kafka", "inbound", "pk.audit.b")}
    missing = expected - pekko_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(pekko_rows)}"
```

- [ ] **Step 3: Catalog**

```yaml
id: pekko-connectors-kafka
displayName: Apache Pekko Connectors Kafka (Alpakka)
style: single_call
protocol: kafka
direction: inbound
detect:
  coordinates: ["org.apache.pekko:pekko-connectors-kafka_2.13", "org.apache.pekko:pekko-connectors-kafka_3"]
measured:
  - { artifact: org.apache.pekko:pekko-connectors-kafka_2.13, versions: ["1.1.0"],
      identity: reported, by: scripts/probes/w62_pekko_kafka_surface.md }
requires: [call_site, string_constants]
matches:
  owner: [org.apache.pekko.kafka.javadsl.Consumer]
  methods:
    - { name: plainSource, arity: 2,
        descriptor: "(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;",
        channel_arg: 1,
        channel_via:
          - { owner: org.apache.pekko.kafka.Subscriptions, method: topics, arg: all_strings }
          - { owner: org.apache.pekko.kafka.Subscriptions, method: topicPattern, arg: 0 } }
    # committableSource, atMostOnceSource, plainPartitionedSource, committablePartitionedSource:
    # same two arguments, same channel_via — one row each, descriptors from w62.
shape_model: json
slice:
  outside:
    - owner: org.apache.pekko.kafka.javadsl.Producer
      method_names: [plainSink, committableSink, flexiFlow]
      why: >
        Names no topic. The topic is on each `ProducerRecord` the stream carries into the
        sink, and no single call names both; the outbound half derives nothing, stated.
```

- [ ] **Step 4: Measure, run, decline, discipline, commit**

Run the analysis and print `call_sites` whose target name is `topics` (as Task 5 Step 4) to see the argument shape; then the test. If green: probe w62 (artifact above; classes `org/apache/pekko/kafka/javadsl/Consumer`, `org/apache/pekko/kafka/Subscriptions`, `org/apache/pekko/kafka/javadsl/Producer`), declining test (`plainSource` with argument 1 a plain `{"kind":"object"}` derives `[]`), prime, COVERAGE §5.8 Pekko row, commit `feat(kafka): Pekko Connectors consumer sources derive one inbound row per subscribed topic (alpakka-pekko)`. If red because the array is unread: record in the register under "Moved to spec work" with the printed argument shape, keep the fixture and the test as strict-xfail, commit `docs(kafka): alpakka-pekko measured — varargs subscriptions are an array argument single_call does not read`.

### Task 8: Micronaut SQS (`micronaut-sqs`)

**Files:**
- Modify: `fixtures/orders-micronaut/pom.xml` (add `software.amazon.awssdk:sqs:2.25.x` — the version `aws-sqs-sdk.yml`'s `measured:` names; exclusions `*`)
- Create: `fixtures/orders-micronaut/src/main/java/com/acme/mn/SqsPoller.java`
- Modify: `tests/e2e/test_aws_sqs_delivered.py` (a second fixture over `orders-micronaut` + one test), COVERAGE §5.10, register

**Measured:** `micronaut-jms-sqs` 4.2.0 carries NO annotations — it is a JMS `ConnectionFactory` over SQS (`SqsConfiguration`, `SqsConfigurationProperties`, two `SqsJmsConnectionFactory` bean definitions). A Micronaut module reaches SQS one of two ways: (a) the raw AWS SDK `SqsClient`/`SqsAsyncClient`, which `aws-sqs-sdk.yml` already reads framework-independently; (b) `@JMSListener(connectionFactory = "sqsJmsConnectionFactory") + @Queue("orders")`, which `micronaut-jms.yml` (shipped 2026-09-12) derives as protocol **`jms`** — the wire is SQS, the row says JMS, and DR-5 linking on protocol equality would not join it to a Spring SQS sender. Reading `connectionFactory` to choose the protocol is a per-attribute protocol switch no engine word has.

- [ ] **Step 1: Fixture** — `SqsPoller.java` in `orders-micronaut`: a `@Singleton` class holding an `SqsClient` and calling `client.receiveMessage(ReceiveMessageRequest.builder().queueUrl("https://sqs.eu-west-1.amazonaws.com/123456789012/mn-orders").build())` and `client.sendMessage(SendMessageRequest.builder().queueUrl("https://sqs.eu-west-1.amazonaws.com/123456789012/mn-audit").messageBody("{}").build())` — the two shapes `aws-sqs-sdk.yml` reads (check its `methods:` for the exact receive form it reads; if `receiveMessage` is outside, use only `sendMessage` and say so in the test).

- [ ] **Step 2: Test** (in `test_aws_sqs_delivered.py`, fixture `micronaut_sqs_rows` over `FIXTURES / "orders-micronaut"`):

```python
def test_a_micronaut_module_using_the_raw_sqs_sdk_derives_its_queues(micronaut_sqs_rows):
    """`micronaut-sqs`. Micronaut ships no SQS annotation (micronaut-jms-sqs 4.2.0 is a
    JMS ConnectionFactory over SQS and carries none). The raw SDK is how a Micronaut
    module addresses SQS directly, and `aws-sqs-sdk.yml` reads it framework-independently
    — this pins that it does so inside a Micronaut module."""
    assert ("sqs", "outbound", "https://sqs.eu-west-1.amazonaws.com/123456789012/mn-audit") in micronaut_sqs_rows, sorted(micronaut_sqs_rows)
```

Run: expected PASS on the first run if `aws-sqs-sdk.yml` is truly framework-independent — a passing-first test is fine HERE because the assertion is the measurement (that no Micronaut gate blocks the SDK catalog). If it fails, the failure is the finding: record it.

- [ ] **Step 3: Record the JMS-over-SQS boundary**

COVERAGE §5.10 Micronaut row: "✅ raw SDK (`aws-sqs-sdk.yml`, pinned in a Micronaut module by `test_aws_sqs_delivered.py`). **Boundary — JMS over SQS reads as `jms`:** `@JMSListener(connectionFactory = "sqsJmsConnectionFactory")` derives through `micronaut-jms.yml` with protocol `jms`; choosing the protocol from the factory attribute is a per-attribute switch no word has. A Spring SQS sender and a Micronaut JMS-over-SQS listener will not link (DR-5)." Register: `micronaut-sqs` → SQS row keeps it until CI; add the boundary line to §4 Category C as `micronaut-jms-over-sqs`.

```bash
git commit -am "feat(sqs): a Micronaut module's raw SqsClient derives; JMS-over-SQS is a stated protocol boundary (micronaut-sqs)"
```

---

## Part C — SOAP

### Task 9: `public final` JAX-WS operation over-report (`jaxws-public-final`)

**Files:**
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql:729` (the `$members` rule)
- Modify: `src/sextant/catalogs/jakarta-jws.yml:150-156`, `jakarta-jws-client.yml` (comment), COVERAGE §5.3 row 2359
- Create: `fixtures/orders-service/…` — NO. Create `fixtures/orders-soap-final/` (jakarta.jws-api 3.0.0, exclusions `*`) with one `@WebService` class declaring `public String quote()` and `public final String internalAudit()`
- Modify: `tests/e2e/test_soap_delivered.py` (fixture + test), `tests/application/test_endpoints.py` (declining test on `jakarta-jws`)

**Measured now:** `ClassScanner.java:1407` writes `modifiers.final` for every method since W7 — the catalog comment saying it is not recorded is stale. `derive_endpoints.sql:729` excludes `static` (and `synthetic` at 627) from `$members` and nothing else. CP-13 Q4: `isWebMethodBySpec` excludes `static` AND `final`. Both catalogs using `members: public_methods` are JAX-WS, so the exclusion is the framework's own rule for every user of the word.

- [ ] **Step 1: Fixture + failing test**

`fixtures/orders-soap-final/src/main/java/com/acme/soapf/QuoteService.java`:

```java
package com.acme.soapf;

import jakarta.jws.WebService;

@WebService(serviceName = "QuoteService", targetNamespace = "http://soapf.acme.com/")
public class QuoteService {
    public String quote(String sku) { return "0.00"; }
    /** `isWebMethodBySpec` excludes a final method (CP-13 Q4): NOT an operation. */
    public final String internalAudit() { return "n/a"; }
}
```

Test in `test_soap_delivered.py` (fixture `soap_final_paths` over the new module, `protocol == "soap"`):

```python
def test_a_public_final_method_is_not_an_operation(soap_final_paths):
    """JAX-WS RI 4.0.2 `isWebMethodBySpec` excludes `static` and `final` (CP-13 Q4). Ours
    excluded `static` only, so a `public final` helper on a `@WebService` derived a SOAP
    operation nobody serves. `modifiers.final` has been in the facts since W7."""
    assert any(p.endswith("quote") for p in soap_final_paths), sorted(soap_final_paths)
    assert not any(p.endswith("internalAudit") for p in soap_final_paths), sorted(soap_final_paths)
```

Run: expected FAIL on the second assertion.

- [ ] **Step 2: The SQL**

At `derive_endpoints.sql:729`, change

```sql
      AND coalesce(s.modifiers ->> 'static', 'false') <> 'true'
```

to

```sql
      AND coalesce(s.modifiers ->> 'static', 'false') <> 'true'
      -- A `final` member is not exposed either: JAX-WS's `isWebMethodBySpec` (CP-13 Q4)
      -- excludes it beside `static`, and both catalogs that declare `$members` are JAX-WS.
      -- `modifiers.final` is written for every method (`ClassScanner.methodModifiersJson`).
      AND coalesce(s.modifiers ->> 'final', 'false') <> 'true'
```

Run the test: PASS. Run `tests/application/test_endpoints.py -q -n 4`: expected all pass (no existing fixture declares a final member on a JWS class — if one does, the failing pin is the over-report being corrected; update it and say so in the commit).

- [ ] **Step 3: Declining test, docs, commit**

Append to `tests/application/test_endpoints.py`, using `_gate_rows` with `modifiers={"final": True}` if `_gate_facts` accepts modifiers; otherwise extend `_gate_facts` with a `method_modifiers: dict[str, bool] | None = None` parameter that is passed into the method `SymbolFact(modifiers=…)` (read `_gate_facts` first; the parameter list is at line ~5859):

```python
@pytest.mark.declines("jakarta-jws")
@pytest.mark.pins("derive_endpoints.members-exclude-final")
def test_a_final_public_method_on_a_web_service_derives_nothing(tmp_path: Path):
    assert _gate_rows(tmp_path, "jakarta-jws", owner_kind=ConstructKind.CLASS,
        type_annotations={"jakarta/jws/WebService#": {}}, method_annotation=None, method_args={},
        method_modifiers={"final": True}) == []
```

Add the guard `derive_endpoints.members-exclude-final` to `scripts/guard_check.py`'s table (read its `GUARDS` mapping; the entry names the SQL line to blank). Update `jakarta-jws.yml:150-156` (remove the stale "records neither `ACC_FINAL`" paragraph; state the exclusion is applied), COVERAGE row 2359 → "✅ shipped 2026-…: excluded beside `static`", register: `jaxws-public-final` stays in the SOAP row until CI. Prime the fixture. Gate.

```bash
git commit -am "fix(soap): a public final method on a @WebService is not an operation — isWebMethodBySpec's rule, applied (jaxws-public-final)"
```

### Task 10: Apache CXF — measure the implementor rule

**Files:**
- Create: `scripts/probes/w63_cxf_web_method_rule/{run.sh,sweep.py}`, `scripts/probes/w63_cxf_web_method_rule.md`
- Modify: `jakarta-jws.yml` `measured:` (add the CXF row if the rule agrees), COVERAGE §5.3 row 2360, register

**What to measure:** CXF's JAX-WS frontend decides which methods are operations in `org.apache.cxf.jaxws.support.JaxWsServiceConfiguration.isOperation(Method)` and `JaxWsImplementorInfo`. Fetch `org.apache.cxf:cxf-rt-frontend-jaxws:4.0.5` and `org.apache.cxf:cxf-core:4.0.5` (`mvn dependency:get -Dtransitive=false`), `javap -p -c` `isOperation` and count the `ACC_STATIC`/`ACC_FINAL` tests (look for `getModifiers` followed by `Modifier.isStatic` / `isFinal` invokestatics), the `@WebMethod(exclude=true)` read, and whether inherited public methods are walked (`getMethods` vs `getDeclaredMethods`).

- [ ] **Step 1: Write and run the probe** — harness as w58/w59; the sweep prints, per method inspected, the invokestatic/invokevirtual sequence names (`Modifier.isStatic`, `Modifier.isFinal`, `Class.getMethods`, …) as a table `| class | method | calls, in order |`. Version scope `**cxf-rt-frontend-jaxws 4.0.5**`. Expectation table: rows "isFinal is tested → same rule as the RI; add the CXF `measured:` row" / "isFinal is NOT tested → CXF exposes final methods; the catalog's exclusion is RI-only and needs a per-catalog switch — record as a spec item".

- [ ] **Step 2: Record the answer.** If the rule agrees: add `- { artifact: org.apache.cxf:cxf-rt-frontend-jaxws, versions: ["4.0.5"], identity: reported, by: scripts/probes/w63_cxf_web_method_rule.md }` to `jakarta-jws.yml`, COVERAGE row 2360 → "✅ measured: CXF 4.0.5 applies the same static/final/`exclude` rule (w63)", register: `apache-cxf` leaves the SOAP row (this one closes by measurement — record it under "Retired as not-gaps" with the probe, not under `closed`, since no intention test changes). If it disagrees: register under "Moved to spec work" with the exact divergence.

```bash
git commit -am "docs(soap): Apache CXF's operation rule measured against the RI's (apache-cxf)"
```

---

## Part D — the Kotlin extractor

All five tasks are in `extractor-jvm/`. Build and test with `cd extractor-jvm && ./gradlew --quiet build`; the shaded jar is what the Python suite loads, so after every extractor change run `bash scripts/check.sh` in full. Kotlin samples live in `extractor-jvm/src/test/kotlin/dev/sextant/extractor/`; the test that reads a sample's facts is `KotlinMetadataTest.java` / `KotlinSuspendReturnTest.java` — copy their `scan(…)` helper usage.

### Task 11: Kotlin parameter nullability (`OI-82`)

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/KotlinNullability.java` (`Decoded` gains `parameterNullable: Map<String, List<Boolean>>`), `ClassScanner.java` (apply per parameter), `TypeRefs.java` (apply on the `Node` tree, not on JSON text)
- Create: `extractor-jvm/src/test/kotlin/dev/sextant/extractor/KotlinParameterSample.kt`, `extractor-jvm/src/test/java/dev/sextant/extractor/KotlinParameterNullabilityTest.java`
- Modify: `docs/COVERAGE.md` §5.13 (the `OI-82` row), `docs/open-issues.md` (OI-82 → closed), register (`unassigned` block: remove `OI-82`)

**Start from `git stash list`'s `stash@{0}` ("WIP kotlin nullability: parameters+constructors WORK; nested type args INVERTED")** — read it with `git diff stash@{0}^1 stash@{0}`; do NOT `git stash apply` (the executor never runs state-changing git commands; copy the hunks by hand). Its `Decoded` extension and `ClassScanner` alignment are right. Its `TypeRefs.withDeclaredNullability(String json, List<Boolean>)` — walking the SERIALIZED JSON by brace depth to overwrite `"nullable":` values — is the cause of the inversion: `toJson` writes `arguments` before `nullable`, so the text order is child-first while metadata's `KmType` walk is pre-order. Do not fix the string walk; remove it. Apply nullability on the `Node` tree before serialization, walking `KmType` and `Node` together.

- [ ] **Step 1: Sample + failing test**

`KotlinParameterSample.kt`:

```kotlin
package dev.sextant.extractor

class KotlinParameterSample(val id: String, val note: String?) {
    fun place(sku: String, qty: Int?, tags: List<String?>, meta: Map<String, List<Int>?>?) = sku
    fun copy(id: String = this.id, note: String? = this.note) = KotlinParameterSample(id, note)
}
```

`KotlinParameterNullabilityTest.java` (mirror `KotlinSuspendReturnTest`'s setup — it compiles the sample through the Gradle Kotlin plugin and scans `build/classes/kotlin/test`):

```java
@Test
void parametersCarryTheDeclaredNullability() {
    var method = methodFact("KotlinParameterSample", "place");
    List<Map<String, Object>> params = parameters(method);
    assertEquals(false, params.get(0).get("nullable"));                 // sku: String
    assertEquals(true,  params.get(1).get("nullable"));                 // qty: Int?
    assertEquals(false, params.get(2).get("nullable"));                 // tags: List<String?>
    assertEquals(true,  argument(params.get(2), 0).get("nullable"));    // …String?
    assertEquals(true,  params.get(3).get("nullable"));                 // meta: Map<…>?
    assertEquals(false, argument(params.get(3), 0).get("nullable"));    // String
    assertEquals(true,  argument(params.get(3), 1).get("nullable"));    // List<Int>?
    assertEquals(false, argument(argument(params.get(3), 1), 0).get("nullable")); // Int
}

@Test
void constructorParametersToo() {
    var ctor = methodFact("KotlinParameterSample", "<init>");
    assertEquals(false, parameters(ctor).get(0).get("nullable"));
    assertEquals(true,  parameters(ctor).get(1).get("nullable"));
}
```

(`methodFact`, `parameters`, `argument` are small helpers reading the emitted JSON — write them in the test class; `argument(p, i)` returns `((List<Map>) p.get("arguments")).get(i)`.) Run: `cd extractor-jvm && ./gradlew --quiet test --tests '*KotlinParameterNullabilityTest*'` — expected FAIL (every parameter reads `true` today).

- [ ] **Step 2: Decode parameters per function**

In `KotlinNullability.decode`, beside `returns`, build `Map<String, List<KmType>> parameterTypes` keyed by the same `name + descriptor` key: `function.getValueParameters().stream().map(KmValueParameter::getType).toList()`; and for constructors, `classMetadata.getKmClass().getConstructors()` with `JvmExtensionsKt.getSignature(constructor)` giving `"<init>" + descriptor`. Add the map to `Decoded` (record component `parameterTypes`, default `Map.of()` in `NONE`). Keep the raw `KmType` (not a flattened boolean list) — the tree walk in Step 3 needs it.

- [ ] **Step 3: Apply on the Node tree**

In `TypeRefs.java`, add:

```java
/** The declared nullability of `declared` and of every type argument, applied to `node`
 *  by walking both trees together. Applied ONLY where the two agree on the shape at every
 *  level: metadata spells a raw type, a type variable or a projection differently from
 *  the `Signature` attribute, and where the argument counts differ NOTHING below that
 *  point is applied — Java's rule stands, which is less specific and never wrong. */
static Node withDeclaredNullability(Node node, KmType declared) {
    Node out = node.withNullable(Attributes.isNullable(declared));
    List<KmTypeProjection> args = declared.getArguments();
    if (args.size() != node.arguments().size()) return out;
    List<Node> applied = new ArrayList<>();
    for (int i = 0; i < args.size(); i++) {
        KmType argType = args.get(i).getType();            // null for a star projection
        applied.add(argType == null ? node.arguments().get(i)
                                    : withDeclaredNullability(node.arguments().get(i), argType));
    }
    return out.withArguments(applied);
}
```

(`Node` is `TypeRefs`' own tree record; if it is immutable without `withNullable`/`withArguments`, add those two `with` methods to it.) In `ClassScanner`, at the point the WIP applied per-parameter nullability (its hunk around the `parameters` emission), call this on each parameter's `Node` BEFORE `toJson`, aligning metadata index → descriptor slot exactly as the WIP does (skipping a leading synthetic `this$0`/outer-instance slot and trailing `$default` mask slots — the WIP's alignment, kept).

Run the test: PASS, all eight assertions. Run the whole extractor suite: `./gradlew --quiet build` — expected green (`GenericSignatureTest`, which caught the string-walk bug, included).

- [ ] **Step 4: Python side, docs, commit**

`bash scripts/check.sh` (the vertical slice reads `KotlinOrder`'s parameter facts; a pin that reads `nullable: true` for a non-null Kotlin parameter is the defect being fixed — update the pin and say so). COVERAGE §5.13 `OI-82` row → shipped; `open-issues.md` OI-82 → `**CLOSED** by …`; register: remove `OI-82` from `unassigned`.

```bash
git commit -am "feat(extractor): a Kotlin parameter carries the nullability its source declared, type arguments included (OI-82)"
```

### Task 12: Boxed primitive on a suspend return (`OI-80`)

**Files:**
- Modify: `KotlinNullability.java` (`Decoded` gains `returnClassifier: Map<String, String>` — the Kotlin classifier name for the primitive cases), `ClassScanner.java` (where a suspend return is recovered from the `Continuation` type argument)
- Create: `extractor-jvm/src/test/java/dev/sextant/extractor/KotlinSuspendPrimitiveTest.java` (sample: `KotlinSuspendSample.kt` already has `suspCount(): Int` per OI-80 — confirm with `grep -n "suspCount\|plainCount" extractor-jvm/src/test/kotlin/…/KotlinSuspendSample.kt`; add `suspFlag(): Boolean` and `suspTotal(): Long` if absent)

- [ ] **Step 1: Failing test**

```java
@Test
void aSuspendingPrimitiveReturnReadsAsThePrimitive() {
    assertEquals("int#",     returnSymbol("KotlinSuspendSample", "suspCount"));
    assertEquals("boolean#", returnSymbol("KotlinSuspendSample", "suspFlag"));
    assertEquals("long#",    returnSymbol("KotlinSuspendSample", "suspTotal"));
    assertEquals("int#",     returnSymbol("KotlinSuspendSample", "plainCount")); // unchanged
}
```

Expected: FAIL — `java/lang/Integer#`.

- [ ] **Step 2: Read the classifier**

In `decode`, for each function also store `returnClassifier.put(key, classifierName(function.getReturnType()))` where `classifierName` returns the `KmClassifier.Class` name (`kotlin/Int`, `kotlin/Boolean`, …) or `null`. In `ClassScanner`, where the suspend return's `Node` is built from the `Continuation` argument, map `kotlin/Int→int`, `kotlin/Long→long`, `kotlin/Boolean→boolean`, `kotlin/Double→double`, `kotlin/Float→float`, `kotlin/Short→short`, `kotlin/Byte→byte`, `kotlin/Char→char` ONLY when the declared return is NOT nullable (`Int?` genuinely boxes; `Attributes.isNullable` says which). A `Map<String,String>` constant `KOTLIN_PRIMITIVES` in `KotlinNullability` holds the eight pairs.

Run: PASS. `./gradlew --quiet build`, then `bash scripts/check.sh`. Docs: `open-issues.md` OI-80 closed; register `unassigned` minus `OI-80`; COVERAGE §5.13 suspend row.

```bash
git commit -am "feat(extractor): a suspend fun returning Int reads as int, not Integer, where the source declared it non-null (OI-80)"
```

### Task 13: `$default` bridges (`OI-81`, `kotlin-default-bridge`)

**Files:**
- Modify: `ClassScanner.java` (method emission), `docs/components/D00-fact-schema.md` §5 (one sentence: a `$default` bridge is emitted with `modifiers.synthetic: true` AND `bridge_of: "<name>"`), `src/sextant/domain/facts.py` (`Signature` or `SymbolFact` gains `bridge_of: str | None = None`)
- Create: sample `KotlinDefaultsSample.kt` (`fun greet(name: String = "x", loud: Boolean = false)`), test `KotlinDefaultBridgeTest.java`

**Rule (measured by reading kotlinc's output on `KotlinSample.copy$default`):** a `$default` bridge is `static synthetic`, named `<fn>$default`, with parameters `(receiver, <fn's params…>, int mask[, int mask2…], Object marker)`. It is not in `@kotlin.Metadata`'s function list, which is why it fell to Java's rule (OI-81).

- [ ] **Step 1: Failing test**

```java
@Test
void aDefaultBridgeNamesTheFunctionItStandsFor() {
    var bridge = methodFact("KotlinDefaultsSample", "greet$default");
    assertEquals("greet", bridge.get("bridge_of"));
    assertEquals(true, modifiers(bridge).get("synthetic"));
    // OI-81: the bridge's declared types are the FUNCTION's, not Java's rule.
    assertEquals(false, parameters(bridge).get(1).get("nullable"));   // name: String
    assertEquals(false, returnOf(bridge).get("nullable"));
}
```

- [ ] **Step 2: Recognise the bridge**

In `ClassScanner`'s method visitor, when `(access & ACC_SYNTHETIC) != 0 && (access & ACC_STATIC) != 0 && name.endsWith("$default")`: set `bridge_of = name.substring(0, name.length() - 8)`; look up the sibling's metadata key by name + the sibling's descriptor (the bridge's descriptor minus the leading receiver slot for an instance function, minus the trailing `I…Ljava/lang/Object;` mask slots) and apply the sibling's `returnNullable` and `parameterTypes` (Task 11's map) shifted by one for the receiver. Emit `bridge_of` in the fact. Python: add the field to the fact model with a docstring sentence; `schema.sql` needs no change (`->>` on an absent key is NULL).

Run: PASS. Full gate. `open-issues.md` OI-81 closed; COVERAGE §5.13 `$default` row → shipped; register `unassigned` minus `OI-81 kotlin-default-bridge`.

```bash
git commit -am "feat(extractor): a Kotlin \$default bridge names the function it stands for and takes its declared types (OI-81)"
```

### Task 14: Extension functions (`kotlin-extension-functions`)

**Files:**
- Modify: `KotlinNullability.java` (`Decoded` gains `extensionReceivers: Set<String>` — keys of functions whose `KmFunction.getReceiverParameterType()` is non-null; file facades: `KotlinClassMetadata.FileFacade` must be decoded too — `decode` currently returns `NONE` for anything but `Class`; extend it to `FileFacade.getKmPackage().getFunctions()`), `ClassScanner.java` (emit `receiver: true` on parameter 0 of such a method), `facts.py` (`Parameter` gains `receiver: bool = False`), D00 §5

- [ ] **Step 1: Failing test** — sample `KotlinExtensionsSample.kt`: `fun String.shout(): String = uppercase()` (file facade → `KotlinExtensionsSampleKt`) and inside a class `fun List<Int>.total() = sum()`:

```java
@Test
void anExtensionReceiverIsMarkedNotPublishedAsAParameter() {
    var shout = methodFact("KotlinExtensionsSampleKt", "shout");
    assertEquals(true, parameters(shout).get(0).get("receiver"));
    assertEquals("java/lang/String#", parameters(shout).get(0).get("symbol"));
}
```

- [ ] **Step 2: Implement** as described; the Python `Parameter` model gains `receiver: bool = False` with the sentence "Kotlin: this slot is the extension receiver, published so a consumer can drop it from the declared signature; the JVM sees a parameter, the author wrote a receiver." COVERAGE §5.13 row 3326 → shipped. Register `unassigned` minus `kotlin-extension-functions`.

```bash
git commit -am "feat(extractor): a Kotlin extension function's receiver is marked as one (kotlin-extension-functions)"
```

### Task 15: `DefaultImpls` (`kotlin-defaultimpls`)

**Files:**
- Modify: `ClassScanner.java` (a nested class named `<Iface>$DefaultImpls`, `ACC_SYNTHETIC` absent but recognisable by name + every method `static` with the interface as parameter 0: emit `implements_default_of: "<Iface>#"` on the class symbol fact and `bridge_of: "<name>"` on each method, reusing Task 13's field), `facts.py`, D00 §5
- Create: sample `KotlinDefaultImplsSample.kt` (`interface Pricer { fun price(): Int = 0 }`, compiled WITHOUT `-Xjvm-default=all` so `Pricer$DefaultImpls` exists — check `extractor-jvm/build.gradle.kts`' `freeCompilerArgs`; if `all` is set, the sample needs `@JvmDefaultWithoutCompatibility` absent and the flag overridden for the test source set, which is a build change: state it in the commit)

- [ ] **Step 1: Failing test**

```java
@Test
void defaultImplsIsAttributedToItsInterface() {
    var holder = classFact("KotlinDefaultImplsSample$Pricer$DefaultImpls");
    assertEquals("dev/sextant/extractor/KotlinDefaultImplsSample$Pricer#", holder.get("implements_default_of"));
    assertEquals("price", methodFact("KotlinDefaultImplsSample$Pricer$DefaultImpls", "price").get("bridge_of"));
}
```

- [ ] **Step 2: Implement; then the resolve side.** `supertype_dispatch` should treat a `DefaultImpls` method as the interface method's body: in `src/sextant/application/resolve/engines/supertype_dispatch.py`, where candidates are collected for an interface method, include the symbol whose `bridge_of` equals the method name on the type whose `implements_default_of` is the interface. Pin it with a `tests/application/test_supertype_dispatch.py` case built from facts (copy the file's nearest fact-builder). COVERAGE §5.13 row 3328 → shipped. Register `unassigned` minus `kotlin-defaultimpls`.

```bash
git commit -am "feat(extractor): a Kotlin DefaultImpls body is the interface method's body, and dispatch reaches it (kotlin-defaultimpls)"
```

---

## Part E — the four that block no feature

### Task 16: Throw exits (`G-52`)

**Files:** everything `stash@{1}` touches — `extractor-jvm/…/MethodFlow.java` (+120), `docs/components/D00-fact-schema.md`, `src/sextant/domain/facts.py`, `src/sextant/application/resolve/call_edges.py`, `resolve/terminals.py`, `egress/render/document.py`, `tests/domain/test_facts.py`, `tests/e2e/test_vertical_slice.py`.

Read the stash with `git diff stash@{1}^1 stash@{1}`. Its review already fixed 2 Criticals and 3 Majors; what it lacks is the GATE and the register entry. Do not `git stash pop`; re-apply the hunks by hand on a fresh branch `feat/g52-throw-exits` from `main`.

- [ ] **Step 1: Re-apply the hunks**, file by file, in this order: `facts.py` (the `CallTarget` optional fields + `_only_a_throw_names_no_method` validator), `test_facts.py` (its four new cases — run them: `.venv/bin/python -m pytest tests/domain/test_facts.py -q`, expected PASS), `MethodFlow.java` (the `ATHROW` visitor emitting a call-site fact with `invoke_kind: "throw"`, `target.owner` = the thrown type or NULL for a rethrow), `call_edges.py` and `terminals.py` (`THROW` skips dispatch; `classify` takes `invoke_kind`), `document.py`, D00.

- [ ] **Step 2: Gate.** `cd extractor-jvm && ./gradlew --quiet build`, then `bash scripts/check.sh`. The vertical-slice pins in the stash (`Dispatch, by outcome … resolved 1511`, `owner_not_scanned 348`) were measured against a fixture that has since gained classes — re-measure them (`grep -n "Dispatch, by outcome" tests/e2e/test_vertical_slice.py`, run the slice, copy the actual numbers, and state in the commit that they moved because of the fixture, not because of this change: run the slice once WITHOUT the extractor change to prove it).

- [ ] **Step 3: Review** (subagent, diff `main..HEAD`), fix Critical + Major, register: `G-52` from `unassigned` to `closed` after CI; `open-issues.md` entry updated. Commit:

```bash
git commit -am "feat(extractor): a throw is an exit — every ATHROW is a call-site fact whose target is the thrown type, and traces stop on it (G-52)"
```

### Task 17: `signature.throws` gains its consumer (`G-74`)

**Files:**
- Modify: `src/sextant/egress/render/document.py` (the per-endpoint detail block), `tests/egress/test_render.py`
- Depends on: Task 16 (a rendered "Fails with" line pairs the DECLARED `throws` with the OBSERVED throw exits on the handler's trace).

- [ ] **Step 1: Failing test** — in `tests/egress/test_render.py`, build a workspace with one endpoint whose handler `Signature.throws == ["java/io/IOException#"]` (copy the file's nearest workspace-builder) and assert the rendered `architecture.md` carries, under that endpoint's detail block:

```
  - Fails with: `IOException` (declared)
```

and, when a throw-exit call site for `IllegalStateException` sits on the same handler, `… \`IllegalStateException\` (thrown)`.

- [ ] **Step 2: Implement** in `document.py`: read `signature.throws` off the handler's symbol row and the `invoke_kind = 'throw'` call sites reachable from the handler (the `reachability` table joined to `call_sites`), render one line, sorted, declared first. Where both lists are empty, render nothing. `open-issues.md` G-74 closed; register `unassigned` minus `G-74`; COVERAGE §5.13 or §6 (wherever `throws` is described) → "consumed by the document".

```bash
git commit -am "feat(render): an endpoint's detail names what its handler declares it throws and what it is observed to throw (G-74)"
```

### Task 18: Four-valued `visibility` (`G-73`)

**Files:**
- Modify: `ClassScanner.java:1598` (`visibility` for methods/fields/types), `src/sextant/domain/facts.py:234`, `src/sextant/domain/closed_sets.py` (a `Visibility` StrEnum: `public | protected | package | private`), D00 §5, `extractor-jvm/src/test/java/dev/sextant/extractor/AccessFlagTest.java`
- Every consumer that compares `visibility == "other"`: `grep -rn '"other"' src/sextant/ | grep -i visib` — each becomes `!= "public"` or the enum member it meant.

- [ ] **Step 1: Failing test** — extend `AccessFlagSample.java` with `protected void p()`, `void pkg()`, `private void priv()`, and in `AccessFlagTest`:

```java
assertEquals("protected", visibilityOf("p"));
assertEquals("package",   visibilityOf("pkg"));
assertEquals("private",   visibilityOf("priv"));
assertEquals("public",    visibilityOf("pub"));
```

- [ ] **Step 2: Implement** at `ClassScanner.java:1598`: `ACC_PUBLIC → "public"`, `ACC_PROTECTED → "protected"`, `ACC_PRIVATE → "private"`, else `"package"`. For a NESTED type the class-file flag is the coarse one and the `InnerClasses` entry carries the source modifier (the comment at line 262–275 says so and names OI-51) — leave nested types on the class-file flag and say in D00 that nested-type visibility is the outer word until OI-51. Python: `visibility: Visibility = Visibility.PUBLIC`. Every `"other"` comparison updated; `grep -rn '"other"' src tests` must return only unrelated hits afterwards.

Run `./gradlew build`, `bash scripts/check.sh`. `open-issues.md`/register: `G-73` out of `unassigned`.

```bash
git commit -am "feat(extractor): visibility is the four words the language has, not public-or-other (G-73)"
```

### Task 19: Reactor-module cost (`GAP-7` / `OI-68`)

**Files:**
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql` and `derive_endpoint_shapes.sql` (per the profile), `tests/application/test_pipeline.py` (a timing pin), `docs/open-issues.md` OI-68

**What W56 established:** lever 1 (types-only sibling scan) is REFUTED — sibling bodies are traced. Lever 2 (root-filter `derive_endpoints` to the module's own documents) was NOT refuted; it is the 13–15s of `derive_endpoints` searching 487 sibling documents for endpoints that are then dropped by `drop_borrowed_endpoints.sql`. `derive_endpoint_shapes` (~16.5s) is legitimate work. So this task is lever 2 plus a measured profile of what remains.

- [ ] **Step 1: Measure before touching anything.** Run `.venv/bin/sextant module analyze examples/mall-admin --workspace $(mktemp -d)` (the corpus OI-68 measured on; if `examples/` is absent locally, the reactor fixture `fixtures/orders-reactor` with `billing-lib` is the stand-in) with `SEXTANT_PROFILE=1` if the pipeline has a phase timer (grep `time.perf_counter` in `src/sextant/application/resolve/pipeline.py`; if none, add one that logs each `derive_*` call's seconds at `INFO`). Record the per-phase table in the task's commit message.

- [ ] **Step 2: Root-filter the minting passes.** In `derive_endpoints.sql`, the `annotations_effective` / `declared` / call-site sources that mint rows: add `WHERE d.origin_tier = 'module_output'` (the `documents` column that distinguishes the module's own classes from a sibling's — confirm the column name with `grep -n origin_tier src/sextant/storage/duckdb/schema.sql`) at the FIRST join to `documents`, so a sibling's classes are never candidates. `drop_borrowed_endpoints.sql` stays as the belt-and-braces check the OI-68 entry describes.

- [ ] **Step 3: Pin that output is unchanged and time dropped.** In `tests/application/test_pipeline.py`, the reactor test that analyses with siblings: assert the endpoint set is byte-identical to the pre-change run (capture it once in the test as a sorted list of `(protocol, direction, method, path)`), and assert `derive_endpoints` wall time on `fixtures/orders-reactor` is under a bound measured as 2× the post-change local figure (state the figure and the machine in the test's docstring; a bound is a regression alarm, not a benchmark).

Re-measure (Step 1 again). `open-issues.md` OI-68: record the new per-phase table and what remains, and whether `GAP-7` closes (it closes when the figure is under the 10s the register calls acceptable, else it stays with the new number).

```bash
git commit -am "perf(resolve): endpoint minting reads the module's own documents only; sibling classes are types, not candidates (GAP-7 lever 2, measured)"
```

---

## Self-review

- **Coverage:** every plan-only register item has a task (table at the top); the four moved to spec are named with their measurement.
- **Placeholders:** the two places an executor must read a file to learn a helper's name (`tests/application/test_call_engines.py`'s single_call fact builder in Tasks 1–3, 5–7; `_gate_facts`' modifier parameter in Task 9) say so explicitly and say what to look for; they are not "TBD"s but a rule the plan cannot pre-empt without guessing a name.
- **Type consistency:** `receiver_rows`, `kafka_rows`, `streams_rows`, `pekko_rows`, `javalin_routes`, `soap_final_paths`, `micronaut_sqs_rows` all return `set[tuple[str, str, str]]` of `(protocol|direction, direction|method, path)` as each file's docstring states; `Decoded.parameterTypes: Map<String, List<KmType>>` (Task 11) is what Task 13 reads; `bridge_of` (Task 13) is what Task 15 reuses; `Visibility` (Task 18) replaces the string on `SymbolFact.visibility`.
- **Order:** Tasks 1→4 share a fixture and go in order; 5–8 are independent; 9 before 10; 11 before 13 before 15 (each consumes the previous one's `Decoded` field); 16 before 17; 18 and 19 are independent of everything.
