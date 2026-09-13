# Combinator PR A2 Implementation Plan — the six calls nested in a lambda, and the A1 register close

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `sqs-template-receive`, `javalin-apibuilder`, `ktor-routing`, `G-30`, `G-30-outbound` and `jdk-httpclient` — every one a call written inside a lambda handed to an outer call — so **REST outbound's register row empties** and REST inbound drops by three; and record `G-37`, `W44-verb-overloads`, `GAP-1b` as closed on PR #25's run.

**Architecture:** Two of the six are catalog data on words that exist (`single_call`'s `lambda_steps`). One needs no engine change (Javalin's static `ApiBuilder` inside an `EndpointGroup` body). Two need `combinator` to know where a body's chain starts — `origin_param`, resolved through the two fact fields PR A1 landed (`receiver_parameter`, `captures`) — and, for the gateway, to fold a receiver chain of predicates as one route's constraints (`chain_composers`, `negators`, `terminal`, `verb_arg`). The JDK and Apache clients are `fluent` catalogs in `okhttp.yml`'s exact shape, plus one `fluent` word (`url_via`, the `channel_via` ladder for a URL).

**Tech Stack:** Python 3.14 + pydantic + DuckDB, YAML catalogs, Maven fixtures (Java 21, Kotlin 2.2.0), pytest `-n 4 --dist loadfile`.

**Spec:** `docs/superpowers/specs/2026-09-11-combinator-overload-discrimination-design.md` Part II — §9–§16, as amended 2026-09-13 (read §12's table and its numbered words, §13, §14, §16 items 5–10). Every rule below argues from it; where the plan and the spec disagree the spec wins and the executor records the conflict.

## Global Constraints

- **Nothing that works today may move** — every live row of every existing fixture stays; new rows only. The four fixture-total tests (`tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`, `tests/cli/test_app.py`, `tests/application/test_asm_scanner.py`) move additively.
- **Never a wrong row, never silence** (spec §3, §13): a chain whose head is not the body's origin parameter, a predicate the walk cannot read, a lambda the extractor did not link — each is ONE unresolved row, never a resolved row read off the wrong value, never nothing.
- **A catch-all serves every path: `/**`** (spec §7 case 3); a gateway route with only `method(GET)` or only `host(…)` is `GET /**` / `NULL /**`, resolved.
- **A Kotlin `suspend` handler is NULL** on its row (spec §13 case 8) — asserted, not hidden.
- **One catalog, one style, one direction**: the gateway is two catalogs, SQS receive is a sibling of the send catalog.
- **Every rule traces to `javap -p -s`** on the jar in `~/.m2` at the measured version, recorded in the catalog comment; `measured` blocks cite a probe with a version scope (`tests/architecture/test_catalog_measurement_coverage.py`).
- **GUIDELINES §5.1:** an engine word moves `docs/components/D02-catalog-schema.md` in the same commit; the CHANGELOG entry for the PR lands in Task 9.
- **No stamp bump; no version bump.** Language confinement in `src/**` prose (`tests/architecture/test_language_confinement.py`; catalog YAML and fixture sources are exempt). Plain language.
- **Per-item loop:** every task ends with the full gate in the foreground — `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh` — then one commit. `git add`/`git commit` only: never `stash`, `checkout --`, `reset`, `push`, worktrees, branches.
- **Fixture facts are not committed** (`.sextant/` gitignored); `target/` never added. A new fixture MODULE joins `tests/fixture_build.py`'s `PRIMED_FIXTURES` so CI primes it; its first compile may need the network once (`mvn -q compile` without `-o`), after which `-o` works.
- **Guards:** every new near-miss test carries `@pytest.mark.declines(<catalog>)` and exactly one `@pytest.mark.pins(<guard>)`; `bash scripts/check.sh --guards` runs end to end.

---

## File map

| file | responsibility |
|---|---|
| `docs/java-kotlin-delivery-list.md` | Task 1: A1's three ids → `closed`; Task 9: A2's six |
| `src/sextant/catalogs/spring-sqs-template-receive.yml` (new), `spring-sqs-template.yml` (slice) | Task 2 |
| `fixtures/orders-service/src/main/java/com/acme/orders/messaging/OrderPoller.java` | Task 2 |
| `src/sextant/catalogs/javalin-apibuilder.yml` (new), `javalin.yml` (slice note) | Task 3 |
| `src/sextant/application/resolve/engines/combinator.py` | Task 4 (`origin_param`, `receiver_arg`), Task 6 (`chain_composers`, `negators`, `terminal`, `verb_arg`, array paths) |
| `src/sextant/catalogs/spring-webflux-router.yml`, `spring-mvc-router.yml` | Task 4: `origin_param: 0` on every body whose parameter is the builder |
| `fixtures/orders-ktor/**` (new module), `src/sextant/catalogs/ktor-routing.yml` (new) | Task 5 |
| `fixtures/orders-gateway/**` (new module), `src/sextant/catalogs/spring-cloud-gateway.yml`, `spring-cloud-gateway-outbound.yml` (new) | Task 7 |
| `src/sextant/application/resolve/engines/fluent.py` (`url_via`), `src/sextant/catalogs/jdk-httpclient.yml`, `apache-httpclient.yml` (new) | Task 8 |
| `fixtures/orders-service/src/main/java/com/acme/orders/httpclient/JdkOrdersClient.java`, `ApacheOrdersClient.java`, `fixtures/orders-service/pom.xml` (httpclient5) | Task 8 |
| `tests/e2e/test_rest_inbound_delivered.py`, `test_rest_outbound_delivered.py`, `test_aws_sqs_delivered.py` | live tests, Tasks 2–8 |
| `tests/application/test_combinator_engine.py`, `test_fluent_engine.py` (or the fluent test file that exists — `grep -ln "style=\"fluent\"" tests/application/*.py`), `tests/application/test_endpoints.py` | engine tests, near-misses |
| `tests/fixture_build.py` | `PRIMED_FIXTURES` gains `orders-ktor`, `orders-gateway` |
| `scripts/guard_check.py` | guards: `combinator.origin-parameter-is-the-chains-head`, `combinator.receiver-arg-is-the-origin`, `combinator.negator-poisons`, `fluent.url-via-follows-only-a-declared-call` |
| `docs/components/D02-catalog-schema.md` | Tasks 4, 6, 8 |
| `scripts/probes/w19_catalog_surface.md` | regenerated in Tasks 3, 5, 7 (`ApiBuilder`, `RoutingBuilderKt`, `RouteLocatorBuilder$Builder`/`PredicateSpec`) |
| `docs/COVERAGE.md`, `CHANGELOG.md` | Task 9 |

---

### Task 1: the A1 register close

**Files:**
- Modify: `docs/java-kotlin-delivery-list.md` (```delivery, ```closed blocks; §1 REST inbound rows for the three ids; §4 Category B sentence; the "eight specs" table's group-A row)
- Regenerate: `docs/COVERAGE.md` (`scripts/coverage_matrix.py`, `scripts/coverage_versions.py`)

**Interfaces:** none. Docs only; the tests `tests/architecture/test_feature_delivery.py` and `test_feature_intention.py` parse the blocks.

- [ ] **Step 1: move the ids.** In the ```delivery block's `REST inbound` row remove `G-37`, `W44-verb-overloads`, `GAP-1b`. In the ```closed block add three lines (the format is `id | test node | CI URL`; copy an existing line's spacing):

```
G-37 | tests/e2e/test_rest_inbound_delivered.py::test_the_builder_form_derives_every_route_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/34767891205
W44-verb-overloads | tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/34767891205
GAP-1b | tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/34767891205
```

(Check the two test names exist at head with `grep -n "def test_the_builder_form\|def test_every_kotlin_dsl" tests/e2e/test_rest_inbound_delivered.py`; use the exact names found.)

- [ ] **Step 2: the prose.** §1's REST inbound table: each of the three rows gets a leading `**closed** (PR #25, run 34767891205)` note in the style of the `G-44` row. §4 Category B: replace the "spec is written … awaiting your review" sentence with "PR A1 (#25) shipped items 1–4 of §16 — `G-37`, `W44-verb-overloads`, `GAP-1b`; PR A2 is the six of Part II." The "eight specs" table's group-A row gains "A1 shipped (#25); A2 in progress".

- [ ] **Step 3: regenerate and gate.** `.venv/bin/python scripts/coverage_matrix.py && .venv/bin/python scripts/coverage_versions.py`; the REST inbound cell reads `◐ (7 open)` (nine minus three plus `dsl-media-route`). `.venv/bin/pytest tests/architecture -q -p no:cacheprovider` → green. `bash scripts/check.sh --lint`.

- [ ] **Step 4: commit.**

```bash
git add docs/java-kotlin-delivery-list.md docs/COVERAGE.md
git commit -m "docs(register): G-37, W44-verb-overloads and GAP-1b close on PR #25's run 34767891205 — REST inbound 9 → 7 open"
```

---

### Task 2: `SqsTemplate.receive*` through `lambda_steps` — a sibling inbound catalog

**Files:**
- Create: `src/sextant/catalogs/spring-sqs-template-receive.yml`
- Modify: `src/sextant/catalogs/spring-sqs-template.yml` (the `slice.outside` entry for `receive*` → its `why` now points at the sibling catalog, or the entry is removed if the slice audit requires that a read name not be listed as outside — `tests/architecture/test_catalog_slice_coverage.py` decides; read it)
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/messaging/OrderPoller.java`
- Test: `tests/e2e/test_aws_sqs_delivered.py`, `tests/application/test_endpoints.py` (near-miss)

**Interfaces:**
- Consumes: `single_call`'s `lambda_arg`/`lambda_steps` (`src/sextant/application/resolve/engines/single_call.py:84-92, 160-208`): a step `{owner, method, channel_arg}` reads a call inside the lambda body whose owner matches; a null receiver (the lambda's own parameter) is accepted; `channel_arg` keeps the destination whole (no peer split).
- Produces: `sqs-template-receive` closed.

**What the spec says (§12, first table row for `sqs-template-receive`):** the receive twin of the existing `send` rule; `receive`/`receiveMany`/`receiveAsync`/`receiveManyAsync` `(Consumer<SqsReceiveOptions>[, Class])`, `lambda_steps: [{owner: SqsReceiveOptions, method: queue, channel_arg: 0}]`; the direct `receive(String, …)` overloads by `arity`; caller = the method holding the outer call.

- [ ] **Step 1: measure.** `javap -p -s -cp $(find ~/.m2 -name 'spring-cloud-aws-sqs-3.1.1.jar') io.awspring.cloud.sqs.operations.SqsTemplate | grep -A1 -E " receive(Many|Async|ManyAsync)?\("` and the same on 4.1.1, and `SqsReceiveOptions` for `queue(String)`. Record every overload (name, descriptor) in the catalog comment; the rules below assume the 3.1.1 shapes the existing slice comment states ("every overload takes `Consumer<SqsReceiveOptions>` at argument 0") — if a version adds a direct `receive(String queue, Class<T>)` overload, it gets a row with `arity` + `descriptor` + `channel_arg: 0`.

- [ ] **Step 2: the fixture, first.**

```java
// `SqsTemplate.receive*` with the queue named inside the options lambda (`sqs-template-receive`,
// spec §12): the receive twin of the `send(to -> to.queue(…))` shape `spring-sqs-template.yml`
// reads. Four forms, one queue, so the catalog's four rules are each exercised; the direct
// overload — if the measured version declares one — on a second queue.
package com.acme.orders.messaging;

import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

@Service
public class OrderPoller {
    private final SqsTemplate template;

    public OrderPoller(SqsTemplate template) {
        this.template = template;
    }

    public Optional<Message<OrderPlaced>> pollOne() {
        return template.receive(opts -> opts.queue("orders-poll"), OrderPlaced.class);
    }

    public Collection<Message<OrderPlaced>> pollMany() {
        return template.receiveMany(opts -> opts.queue("orders-poll"), OrderPlaced.class);
    }

    public CompletableFuture<Optional<Message<OrderPlaced>>> pollOneAsync() {
        return template.receiveAsync(opts -> opts.queue("orders-poll"), OrderPlaced.class);
    }

    public CompletableFuture<Collection<Message<OrderPlaced>>> pollManyAsync() {
        return template.receiveManyAsync(opts -> opts.queue("orders-poll"), OrderPlaced.class);
    }
}
```

`OrderPlaced` — use whichever payload type the existing SQS send fixture in the same package uses (`grep -rn "SqsTemplate" fixtures/orders-service/src/main/java`); the class exists. Compile: `cd fixtures/orders-service && mvn -q -o compile`.

- [ ] **Step 3: the live test, first and failing.** In `tests/e2e/test_aws_sqs_delivered.py` (read its fixtures — it reads the session's `analyzed_orders_service`):

```python
def test_a_template_receive_names_its_queue_inside_the_options_lambda(sqs_rows):
    """`sqs-template-receive`: the four receive forms, the queue named in `opts.queue(…)`,
    inbound, caller = the polling method — the send rule's receive twin (spec §12)."""
    rows = {
        (row["catalog_id"], row["direction"], row["path"], _short_caller(row), row["resolution"])
        for row in sqs_rows
        if row["path"] == "orders-poll"
    }
    assert rows == {
        ("spring-sqs-template-receive", "inbound", "orders-poll", "OrderPoller#pollOne", "resolved"),
        ("spring-sqs-template-receive", "inbound", "orders-poll", "OrderPoller#pollMany", "resolved"),
        ("spring-sqs-template-receive", "inbound", "orders-poll", "OrderPoller#pollOneAsync", "resolved"),
        ("spring-sqs-template-receive", "inbound", "orders-poll", "OrderPoller#pollManyAsync", "resolved"),
    }, sorted(rows)
```

(`sqs_rows` = every `protocol == "sqs"` row as dicts, a module fixture built like `http_rows` in `test_rest_inbound_delivered.py`; `_short_caller` = the `Class#method` tail of the caller symbol — copy the helper from the same file.) Run it → FAIL: no such catalog.

- [ ] **Step 4: the catalog.**

```yaml
id: spring-sqs-template-receive
displayName: Spring Cloud AWS SQS (SqsTemplate receive)
style: single_call
protocol: sqs
direction: inbound

detect:
  coordinates: ["io.awspring.cloud:spring-cloud-aws-sqs"]

measured:
  - { artifact: io.awspring.cloud:spring-cloud-aws-sqs, versions: ["3.1.1", "4.1.1"],
      identity: reported, by: scripts/probes/w59_template_receive_halves.md }

requires: [call_site, string_constants]

# The receive half of `spring-sqs-template.yml`, in its own file because a catalog has one
# direction. MEASURED (`javap -p -s`, 3.1.1 and 4.1.1 — <paste the overload list>): every
# form takes `Consumer<SqsReceiveOptions>` at argument 0 and names the queue INSIDE it —
# `opts -> opts.queue("orders")` — which is exactly what `lambda_arg`/`lambda_steps` read
# for `send(to -> to.queue(…))` (W57). The step names its OWNER: a body touching any other
# type with a `queue` method must not answer for this one (W57's review).
matches:
  methods:
    - { name: receive, arity: 2,
        descriptor: "(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/Optional;",
        lambda_arg: 0,
        lambda_steps: [{ owner: io.awspring.cloud.sqs.operations.SqsReceiveOptions, method: queue, channel_arg: 0 }] }
    - { name: receiveMany, arity: 2,
        descriptor: "(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/Collection;",
        lambda_arg: 0,
        lambda_steps: [{ owner: io.awspring.cloud.sqs.operations.SqsReceiveOptions, method: queue, channel_arg: 0 }] }
    - { name: receiveAsync, arity: 2,
        descriptor: "(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;",
        lambda_arg: 0,
        lambda_steps: [{ owner: io.awspring.cloud.sqs.operations.SqsReceiveOptions, method: queue, channel_arg: 0 }] }
    - { name: receiveManyAsync, arity: 2,
        descriptor: "(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;",
        lambda_arg: 0,
        lambda_steps: [{ owner: io.awspring.cloud.sqs.operations.SqsReceiveOptions, method: queue, channel_arg: 0 }] }
```

Descriptors: take them from `javap -s`, not from this block. The arity-1 forms (`receive(Consumer)`) and the argument-less ones (`receive()`, reading the template's default queue — a `default_address`? no: the default queue is configuration, not a literal; those forms derive an unresolved row, stated in a comment and a slice line) get rows only where the jar declares them; copy the send catalog's `slice`, `wrappers` and `shape_model` blocks as that file does for its own harvest compatibility. In `spring-sqs-template.yml`, the `receive*` `slice.outside` entry's `why` becomes one sentence: read by `spring-sqs-template-receive.yml`; keep or drop the entry per the slice audit.

Run the live test → PASS; run `tests/architecture` (catalog audits: descriptor coverage, slice coverage, measurement coverage, `test_catalog_near_miss_coverage` — which requires a `declines` test per catalog).

- [ ] **Step 5: the near-miss.** In `tests/application/test_endpoints.py`, beside the existing `spring-sqs-template` declining test (find it: `grep -n 'declines("spring-sqs-template")'`), a test that hands the lambda a body whose `queue("x")` is on a DIFFERENT owner (`com.example.Metrics#queue`) and asserts no row — pinned to the existing guard `single_call.lambda-step-owner-is-the-declared-type`:

```python
@pytest.mark.declines("spring-sqs-template-receive")
@pytest.mark.pins("single_call.lambda-step-owner-is-the-declared-type")
def test_a_receive_lambda_naming_a_queue_on_another_type_derives_nothing(tmp_path: Path):
    ...
```

Model the facts on the existing send near-miss verbatim (same helper), swapping `send` for `receive` with the measured descriptor.

- [ ] **Step 6: gate, commit.** Full gate; the fixture-total tests move by four rows (recount, additive, with a comment naming `OrderPoller`).

```bash
git add src/sextant/catalogs/spring-sqs-template-receive.yml src/sextant/catalogs/spring-sqs-template.yml fixtures/orders-service/src/main/java/com/acme/orders/messaging/OrderPoller.java tests/e2e/test_aws_sqs_delivered.py tests/application/test_endpoints.py tests/application/test_pipeline.py tests/e2e/test_vertical_slice.py tests/cli/test_app.py tests/application/test_asm_scanner.py
git commit -m "feat(catalogs): SqsTemplate's four receive forms derive the queue named inside the options lambda — the send rule's receive twin, in its own inbound catalog (sqs-template-receive; A2 Task 2, spec §12)"
```

---

### Task 3: Javalin `ApiBuilder` — a `combinator` catalog on the words A1 shipped

**Files:**
- Create: `src/sextant/catalogs/javalin-apibuilder.yml`
- Modify: `src/sextant/catalogs/javalin.yml` (the comment/slice line that says the nested form derives nothing)
- Modify: `fixtures/orders-javalin/src/main/java/com/acme/jv/OrderApp.java` (`nested()` gains the shapes spec §14 lists)
- Test: `tests/e2e/test_rest_inbound_delivered.py` (the strict `xfail` at `test_javalin_api_builder_derives_the_composed_path` becomes a positive), `tests/application/test_endpoints.py` (near-miss)
- Regenerate: `scripts/probes/w19_catalog_surface.md` (`ApiBuilder` 0 of 18 → N of 18)

**Interfaces:**
- Consumes: `combinator`'s body-linked entry (`{owner, method, body_arg}`), prefixes with `body_arg`, verbs with `arity`/`arg_types`/`handler_arg` (A1). `ApiBuilder` is all static: a verb inside the body has `receiver` null, so `_chained_routes` contributes nothing and the body folds under its `path` prefix — no `origin_param` needed (spec §12: "no receiver to verify").
- Produces: `javalin-apibuilder` closed.

- [ ] **Step 1: measure.** `javap -p -s -cp $(find ~/.m2 -name 'javalin-6.4.0.jar' | head -1) io.javalin.apibuilder.ApiBuilder` — 45 static members: `path(String, EndpointGroup)`; for each of `get post put patch delete head options` four overloads: `(String, Handler)`, `(String, Handler, RouteRole...)`, `(Handler)`, `(Handler, RouteRole...)`; `before/after`, `ws`, `sse`, `crud`, `prefixPath`, `staticInstance`, `setStaticJavalin`, `clearStaticJavalin`. And `javap -p -s -cp … io.javalin.config.RouterConfig | grep apiBuilder` → `apiBuilder(EndpointGroup)`. Record in the catalog comment.

- [ ] **Step 2: the fixture.** Replace `nested()` in `OrderApp.java`:

```java
    /** The nested form (`javalin-apibuilder`, spec §14): two nesting levels, a verb with no
     *  path (inherits the prefix alone → `/jv/nested/{id}/items/**`? no — a path-less verb
     *  under a prefix serves the prefix itself, see the catalog), a role-carrying overload. */
    public Javalin nested() {
        return Javalin.create(config -> config.router.apiBuilder(() -> {
            ApiBuilder.path("/jv/nested", () -> {
                ApiBuilder.get("/{id}", ctx -> ctx.result("{}"));
                ApiBuilder.post(ctx -> ctx.status(201));                       // get(Handler): no path of its own
                ApiBuilder.path("/{id}/items", () -> {
                    ApiBuilder.get(ctx -> ctx.result("[]"));                  // inherits both prefixes
                    ApiBuilder.delete("/{itemId}", ctx -> ctx.status(204), new io.javalin.security.RouteRole() {});
                });
            });
        }));
    }
```

Write the comment as a statement, not a question (the plan's draft above is not the final text): Javalin's own rule — `get(handler)` inside `path("/x", …)` registers `/x`; measure it from Javalin's `ApiBuilder.prefixPath`: `prefixPath("")` under `/jv/nested` yields `/jv/nested` (read the decompiled `prefixPath` with `javap -c` or Javalin's source in the sources jar if present). The row is therefore `POST /jv/nested`, not `/jv/nested/**` — a path-less verb is NOT a catch-all here; the catalog spells that with a rule whose path is the empty literal contribution. Since `_verb_constraints` treats "no `path_arg`" as a catch-all (`_served` → `/**`), the rule for `get(Handler)` must contribute an EMPTY path part explicitly. Add to the engine, in Task 3 (the one engine touch here): a verb rule may declare `path: ""` — a literal path contribution, the empty string — which `_verb_constraints` merges as `path_parts=("",)` so `_served` does not fire and `_merged` yields the prefix alone. Two lines plus a test on hand-built facts: `path("/x", () -> get(h))` → `GET /x`. D02: one sentence on `path:` (a literal) beside `path_arg`.

Compile: `cd fixtures/orders-javalin && mvn -q -o compile`.

- [ ] **Step 3: the live test.** Remove the `xfail` marker and rewrite:

```python
def test_javalin_api_builder_derives_the_composed_path(javalin_routes):
    """`javalin-apibuilder`, spec §14 test 12: two nesting levels; a path-less verb serves its
    prefix; the role-carrying overload reads the same positions; every row's caller is the
    method holding `apiBuilder`."""
    expected = {
        ("inbound", "GET", "/jv/nested/{id}"),
        ("inbound", "POST", "/jv/nested"),
        ("inbound", "GET", "/jv/nested/{id}/items"),
        ("inbound", "DELETE", "/jv/nested/{id}/items/{itemId}"),
    }
    assert expected <= javalin_routes, sorted(javalin_routes)
    assert ("inbound", "GET", "/{id}") not in javalin_routes
```

Run → FAIL (no catalog).

- [ ] **Step 4: the catalog.**

```yaml
id: javalin-apibuilder
displayName: Javalin (ApiBuilder nested routing)
style: combinator
protocol: http
direction: inbound

detect:
  coordinates: ["io.javalin:javalin"]

measured:
  - { artifact: io.javalin:javalin, versions: ["6.4.0"],
      identity: reported, by: scripts/probes/w61_javalin_surface.md }

requires: [call_site, string_constants, chain_reconstruction]

# `config.router.apiBuilder(() -> { path("/orders", () -> { get("/{id}", h); }); })`. The
# `EndpointGroup` is a functional interface, so each block is a lambda the extractor links;
# `ApiBuilder` keeps its own prefix stack and every member is STATIC — a verb inside a body
# has no receiver, contributes no chain, and folds under the `path` that linked the body.
# MEASURED, `javap -p -s` at 6.4.0: <the 45 members>.
matches:
  entries:
    - owner: io.javalin.config.RouterConfig
      method: apiBuilder
      body_arg: 0
  vocabulary:
    verbs:
      # Four overloads per verb: (String, Handler), (String, Handler, RouteRole...),
      # (Handler), (Handler, RouteRole...). A path-less form serves the prefix it sits under
      # (Javalin's `prefixPath("")`), spelled here as the empty literal path.
      - { owner: io.javalin.apibuilder.ApiBuilder, method: get, verb: GET, arity: 2, arg_types: { 0: java.lang.String }, path_arg: 0, handler_arg: 1 }
      - { owner: io.javalin.apibuilder.ApiBuilder, method: get, verb: GET, arity: 3, arg_types: { 0: java.lang.String }, path_arg: 0, handler_arg: 1 }
      - { owner: io.javalin.apibuilder.ApiBuilder, method: get, verb: GET, arity: 1, path: "", handler_arg: 0 }
      - { owner: io.javalin.apibuilder.ApiBuilder, method: get, verb: GET, arity: 2, arg_types: { 0: io.javalin.http.Handler }, path: "", handler_arg: 0 }
      # … the same four for post, put, patch, delete, head, options …
    prefixes:
      - { owner: io.javalin.apibuilder.ApiBuilder, method: path, arity: 2, path_arg: 0, body_arg: 1 }

slice:
  outside:
    - owner: io.javalin.apibuilder.ApiBuilder
      method_names: [before, after, ws, sse, crud, prefixPath, staticInstance, setStaticJavalin, clearStaticJavalin]
      why: >
        `before`/`after` are filters, not routes; `ws`/`sse` are the WebSocket and SSE
        registrations, which their own catalogs read (or will); `crud` registers five routes
        from one handler object — a shape with no readable path per verb here, named as a
        gap; the rest are the builder's own plumbing.
```

Write all seven verbs out (28 rules). `crud` is a real gap: log it on the register in Task 9 as `javalin-crud` (Minor: five routes under one prefix, `crud("/users/{id}", handler)` — derivable as five rows from one rule with a fixed verb/path table; not built here).

- [ ] **Step 5: near-miss, probe, gate.** A `declines("javalin-apibuilder")` test in `tests/application/test_endpoints.py` (or the combinator test file, where the other combinator near-misses live): `apiBuilder` on a different owner than `RouterConfig` (`com.example.NotRouter#apiBuilder`) → nothing derives; pinned to `combinator.entry-owner-is-the-declared-type`. Regenerate the w19 probe (`bash scripts/probes/w19_catalog_surface/run.sh`): `ApiBuilder` reads N of 18 (the seven verbs × … — the sweep counts names; expect 8 of 18: seven verbs + `path`); the sweep may need the new catalog id added to its owner list — read `sweep.py`. Full gate.

```bash
git add src/sextant/catalogs/javalin-apibuilder.yml src/sextant/catalogs/javalin.yml src/sextant/application/resolve/engines/combinator.py docs/components/D02-catalog-schema.md fixtures/orders-javalin/src/main/java/com/acme/jv/OrderApp.java tests/e2e/test_rest_inbound_delivered.py tests/application/test_combinator_engine.py tests/application/test_endpoints.py scripts/probes/w19_catalog_surface.md
git commit -m "feat(catalogs): Javalin's nested ApiBuilder derives every route under its path prefixes, a path-less verb serving the prefix itself (javalin-apibuilder; A2 Task 3, spec §12)"
```

---

### Task 4: `origin_param` and `receiver_arg` — where a body's chain starts, made exact

**Files:**
- Modify: `src/sextant/application/resolve/engines/combinator.py` (`_Scope` gains `origin_parameter: int | None`; `_body_routes` computes it; `_chained_routes` and `_is_statement_verb_or_prefix` read it; a new `_receiver_argument_is_the_origin`; `_validate_matches` accepts the two keys)
- Modify: `src/sextant/catalogs/spring-webflux-router.yml`, `spring-mvc-router.yml` (`origin_param: 0` on `coRouter`, `router`, the DSL `nest`, the builder's `Consumer` `path`/`nest`)
- Modify: `docs/components/D02-catalog-schema.md`, `scripts/guard_check.py`
- Test: `tests/application/test_combinator_engine.py`

**Interfaces:**
- Consumes: `call_sites.receiver_parameter` (A1 Task 2), `argument["captures"]` on the linking site's `lambda` argument.
- Produces: rule keys `origin_param: int` (on a body-linked entry or a prefix with `body_arg`) and `receiver_arg: int` (on a verb or prefix); `_Scope.origin_parameter`. Tasks 5 and 7 write rules with them.

**What the spec says (§10, §12 words 1 and 2):** the interface's parameter `k` is the body method's parameter `captures + k`. In a body linked with `origin_param: k`, a chain whose head has `receiver_parameter == captures + k` is clean; a head that is null, another parameter, or an unknown call poisons. `receiver_arg: n`: argument `n` must be `{kind: parameter, value: captures + k}` of the enclosing body, else the row poisons. A body linked without `origin_param` keeps today's rule (a null receiver is clean) — stated in D02 as the less exact form.

- [ ] **Step 1: tests, first and failing.** Append to `tests/application/test_combinator_engine.py` (reuse `_body_linked_facts`' constants; `INLINE_BODY` is the body symbol):

```python
# --- origin_param / receiver_arg (spec §12 words 1–2) ---------------------------

def _origin_matches(origin_param: int | None) -> dict[str, object]:
    matches = _overload_matches()
    entry = {"owner": "com.example.web.RouterDslFacade", "method": "router", "body_arg": 0}
    if origin_param is not None:
        entry["origin_param"] = origin_param
    matches["entries"] = [e for e in matches["entries"] if e.get("method") != "router"] + [entry]  # type: ignore[index]
    return matches


def _dsl_body(*, receiver_parameter: int | None, captures: int) -> list:
    """`router { GET("/x") { h } }` where the DSL call sits on the body's parameter —
    `receiver_parameter` — and the linking lambda captured `captures` values."""
    entry = _site(
        DECLARER + "routes(sig_r).", 0, DSL_FACADE, "router", result=1,
        arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0, captures=captures)],
    )
    verb = CallSiteFact(
        document_id="doc_1", caller=INLINE_BODY,
        target=CallTarget(owner=DSL, name="GET", descriptor="(Ljava/lang/String;Lkotlin/jvm/functions/Function1;)V"),
        invoke_kind="virtual", ordinal=0, receiver=None, receiver_parameter=receiver_parameter,
        arguments=[CallArgument(kind="string", value="/x"), CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0)],
    )
    return [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, verb]


def test_a_body_chain_on_the_declared_origin_parameter_derives_clean(tmp_path: Path):
    """`captures + k`: the lambda captured one value, so the DSL parameter is the body's
    parameter 1; a rule declaring `origin_param: 0` accepts a head on parameter 1."""
    workspace = _resolve(tmp_path, _dsl_body(receiver_parameter=1, captures=1), _catalog(_origin_matches(0)))
    assert _identities(_rows(workspace)) == [("GET", "/x", _MODULE + LIST_ORDERS, "resolved")]


def test_a_body_chain_on_a_field_or_another_parameter_poisons(tmp_path: Path):
    """A null receiver is a field or an unreadable value; another index is not the origin.
    Both are one unresolved row — the fixed-index design's wrong row, refused."""
    for head in (None, 0):
        workspace = _resolve(tmp_path / str(head), _dsl_body(receiver_parameter=head, captures=1), _catalog(_origin_matches(0)))
        assert [row["resolution"] for row in _rows(workspace)] == ["unresolved"], head


def test_a_body_linked_without_an_origin_parameter_keeps_the_permissive_rule(tmp_path: Path):
    """Stated in D02: without `origin_param` a null receiver in a body is read as the body's
    own parameter, as every shipped rule did before this word existed."""
    workspace = _resolve(tmp_path, _dsl_body(receiver_parameter=None, captures=0), _catalog(_origin_matches(None)))
    assert _identities(_rows(workspace)) == [("GET", "/x", _MODULE + LIST_ORDERS, "resolved")]


def test_a_receiver_argument_must_be_the_origin_parameter(tmp_path: Path):
    """The extension-receiver form: `get(route, "/x", h)` is a STATIC call whose argument 0
    is the route; inside `route("/api") { … }` that argument must be the body's own
    parameter, else the row is not under `/api` and poisons (spec §12 word 2)."""
    matches = _origin_matches(0)
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {"owner": "com.example.web.RoutingKt", "method": "get", "verb": "GET", "arity": 3,
         "receiver_arg": 0, "path_arg": 1, "handler_arg": 2}
    )
    def body(argument: CallArgument) -> list:
        entry = _site(DECLARER + "routes(sig_r).", 0, DSL_FACADE, "router", result=1,
                      arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0, captures=0)])
        verb = _site(INLINE_BODY, 0, "com/example/web/RoutingKt#", "get",
                     descriptor="(Lcom/example/web/Route;Ljava/lang/String;Lkotlin/jvm/functions/Function2;)Lcom/example/web/Route;",
                     arguments=[argument, CallArgument(kind="string", value="/x"), CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0)])
        return [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, verb]
    good = _resolve(tmp_path / "good", body(CallArgument(kind="parameter", value=0)), _catalog(matches))
    assert _identities(_rows(good)) == [("GET", "/x", _MODULE + LIST_ORDERS, "resolved")]
    bad = _resolve(tmp_path / "bad", body(CallArgument(kind="parameter", value=1)), _catalog(matches))
    assert [row["resolution"] for row in _rows(bad)] == ["unresolved"]
    unread = _resolve(tmp_path / "unread", body(CallArgument(kind="unresolved")), _catalog(matches))
    assert [row["resolution"] for row in _rows(unread)] == ["unresolved"]
```

(`CallArgument(kind="parameter", value=0)` — check `LiteralValue` accepts an int; the extractor writes `"value":0`, so the model does.) Run → the first, second and fourth FAIL (no `origin_param`/`receiver_arg`), the third passes (today's rule).

- [ ] **Step 2: the engine.**

`_Scope` gains `origin_parameter: int | None = None`. `_body_routes(argument, scope, *, origin_param: int | None = None)`: after `body = _scope_of(sites, scope.context)`, if `origin_param is not None` and `argument.get("captures") is not None`: `body = replace(body, origin_parameter=int(argument["captures"]) + origin_param)`; if `origin_param` is declared but `captures` is absent (a fact from before A1's extractor), leave `origin_parameter` None and the permissive rule applies — say so in the comment. Every caller of `_body_routes` passes the rule's `origin_param` (`_routes_of`'s body-entry branch, `_nested_routes`' `body_arg` branch, `_subtree_routes`).

`_chained_routes`, first lines:

```python
    if site["receiver"] is None:
        origin = scope.origin_parameter
        if origin is None:
            return []
        # Spec §12 word 1: the body's chain starts on the lambda's own parameter, and the
        # rule said which one. Any other head — a field, another parameter, a value the
        # extractor could not follow — is not the origin, and the row says so.
        return [] if site.get("receiver_parameter") == origin else [_Route(poisons=_IDENTITY_POISON)]
```

`_is_statement_verb_or_prefix`: unchanged (a body chain's head carries `receiver_parameter` and is never a root).

`receiver_arg`, in `_verb_constraints` and `_prefix_constraints` (before reading positions):

```python
def _receiver_argument_is_the_origin(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> bool:
    """`receiver_arg` (spec §12 word 2): the argument at that position must be the enclosing
    body's origin parameter — the extension receiver the framework handed the block — or
    the route is not under this body's prefix at all."""
    if "receiver_arg" not in rule:
        return True
    argument = _arg_at(site["arguments"], rule["receiver_arg"])
    return (
        argument is not None
        and argument.get("kind") == "parameter"
        and scope.origin_parameter is not None
        and argument.get("value") == scope.origin_parameter
    )
```

returning `[_Route(poisons=_IDENTITY_POISON)]` when false. `_validate_matches`: `origin_param` only on an entry or prefix carrying `body_arg`; `receiver_arg` an int within `arity` where declared.

- [ ] **Step 3: the shipped bodies declare their origin.** In both router catalogs add `origin_param: 0` to: the `CoRouterFunctionDslKt.coRouter` entry, the `RouterFunctionDslKt.router` entry, the DSL `nest` prefixes (`body_arg: 1`), the builder's `path`/`nest` rules typed `java.util.function.Consumer` (`body_arg: 1`). NOT the `Supplier` ones. Run `tests/e2e/test_rest_inbound_delivered.py` and the four count tests: every row identical (the fixtures' bodies sit on `captures + 0` — Task 1 of A1 measured it). If any row moves, the formula is wrong for that body: stop and report which.

- [ ] **Step 4: D02, guards, gate.** D02's combinator section: `origin_param` (with the `captures + k` sentence and the permissive fallback), `receiver_arg`. Guards: `combinator.origin-parameter-is-the-chains-head` (anchor: the `receiver_parameter == origin` comparison → replace with `True`) pinned by `test_a_body_chain_on_a_field_or_another_parameter_poisons`; `combinator.receiver-arg-is-the-origin` (anchor: `argument.get("value") == scope.origin_parameter` → `True`) pinned by the fourth test. `bash scripts/check.sh --guards` → both killed. Full gate.

```bash
git add src/sextant/application/resolve/engines/combinator.py src/sextant/catalogs/spring-webflux-router.yml src/sextant/catalogs/spring-mvc-router.yml docs/components/D02-catalog-schema.md scripts/guard_check.py tests/application/test_combinator_engine.py
git commit -m "feat(resolve): a body's chain starts on the parameter the rule names — origin_param through captures + k, receiver_arg for the extension-receiver form; the shipped bodies declare theirs (A2 Task 4, spec §12)"
```

---

### Task 5: Ktor — a new fixture module and the `ktor-routing` catalog

**Files:**
- Create: `fixtures/orders-ktor/pom.xml`, `fixtures/orders-ktor/src/main/kotlin/com/acme/kt/KtorRoutes.kt`
- Modify: `tests/fixture_build.py` (`PRIMED_FIXTURES` += `"orders-ktor"`)
- Create: `src/sextant/catalogs/ktor-routing.yml`
- Test: `tests/e2e/test_rest_inbound_delivered.py` (module fixture `ktor_rows` built like `javalin_routes`, analysing `fixtures/orders-ktor`), near-miss in `tests/application/test_combinator_engine.py`
- Regenerate: `scripts/probes/w19_catalog_surface.md` (sweep gains `io.ktor:ktor-server-core-jvm:3.0.3`)

**Interfaces:**
- Consumes: Task 4's `origin_param`, `receiver_arg`.
- Produces: `ktor-routing` closed with a NULL handler stated.

- [ ] **Step 1: measure.** `javap -p -s -cp $(find ~/.m2 -name 'ktor-server-core-jvm-3.0.3.jar') io.ktor.server.routing.RoutingRootKt | grep -A1 " routing("` → `routing(Application, Function1<Routing, Unit>)`; `…RoutingBuilderKt` → `route(Route, String, Function1)`, `route(Route, String, HttpMethod, Function1)`, per verb `get/post/put/patch/delete/head/options(Route, String, Function2)` and `(Route, Function2)`. Record all.

- [ ] **Step 2: the module.** `fixtures/orders-ktor/pom.xml` (model: `orders-javalin/pom.xml` for the exclusions, `orders-service/pom.xml` for the Kotlin plugin):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>orders-ktor</artifactId>
  <version>1.0.0</version>
  <!-- Ktor (`ktor-routing`), in its own module: a Kotlin server stack with no Spring, so
       `orders-service`'s pinned row counts do not move. Compiled, never run. -->
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <kotlin.version>2.2.0</kotlin.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency><groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-stdlib</artifactId><version>${kotlin.version}</version></dependency>
    <dependency><groupId>org.jetbrains.kotlinx</groupId><artifactId>kotlinx-coroutines-core-jvm</artifactId><version>1.10.2</version></dependency>
    <dependency><groupId>io.ktor</groupId><artifactId>ktor-server-core-jvm</artifactId><version>3.0.3</version></dependency>
  </dependencies>
  <build>
    <sourceDirectory>src/main/kotlin</sourceDirectory>
    <plugins>
      <plugin>
        <groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-maven-plugin</artifactId><version>${kotlin.version}</version>
        <executions><execution><id>compile</id><phase>compile</phase><goals><goal>compile</goal></goals></execution></executions>
      </plugin>
    </plugins>
  </build>
</project>
```

The Kotlin compiler needs the supertypes of every referenced type, so `ktor-server-core-jvm`'s transitive jars (`ktor-http`, `ktor-utils`, `ktor-io`, `ktor-events`, …) must be resolvable: the first `mvn -q compile` runs ONLINE (no `-o`) and fetches them; record which artifacts arrived. Then `mvn -q -o compile` must succeed.

`KtorRoutes.kt`:

```kotlin
// Ktor's routing DSL (`ktor-routing`, spec §14): every verb is a STATIC extension function
// whose receiver is the Route the enclosing block was handed — argument 0 in the bytecode —
// and every block is a `Function1<Route, Unit>` lambda the extractor links. Handlers are
// `suspend` lambdas, which compile to classes rather than `invokedynamic` bodies, so their
// rows carry a NULL handler (spec §13 case 8) until `kotlin-null-handler` lands.
package com.acme.kt

import io.ktor.server.application.Application
import io.ktor.server.response.respondText
import io.ktor.server.routing.Route
import io.ktor.server.routing.delete
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.route
import io.ktor.server.routing.routing

fun Application.orders() {
    routing {
        route("/api") {
            get("/orders") { call.respondText("[]") }
            post("/orders") { call.respondText("created") }
            route("/v2") {
                get("/orders") { call.respondText("[]") }
                delete("/orders/{id}") { call.respondText("gone") }
            }
            get { call.respondText("root") }                                  // get(Route, Function2): the prefix itself
        }
        get("/health") { call.respondText("ok") }
    }
}

// The wrong-receiver case (spec §14 test 13): a verb registered on ANOTHER route from inside
// a block is not under that block's prefix, and the engine must not say it is.
fun Application.elsewhere(other: Route) {
    routing {
        route("/api") {
            get(other, "/stray") { call.respondText("stray") }
        }
    }
}
```

`get(other, "/stray") { }` — Ktor's `get` is an extension `Route.get(path, body)`; calling it on `other` explicitly is `other.get("/stray") { }`. Write it that way. Confirm with `javap -p target/classes/com/acme/kt/KtorRoutesKt.class` that the blocks are `invokedynamic` bodies (`orders$lambda$…` static methods) — if Kotlin emitted classes for the `Function1` blocks, the fixture cannot be read and this task stops with `NEEDS_CONTEXT`.

Add `"orders-ktor"` to `PRIMED_FIXTURES`.

- [ ] **Step 3: the live test, first and failing.** Module fixture `ktor_rows` (analyse `fixtures/orders-ktor` exactly as `javalin_routes` does, returning whole rows), then:

```python
def test_ktor_routing_derives_every_route_under_its_nested_prefixes(ktor_rows):
    """`ktor-routing`, spec §14 test 13. Handler NULL on every row — a suspend lambda is a
    class, not a linked body — asserted here so `kotlin-null-handler` moves a pinned value."""
    rows = {(r["method"], r["path"], r["resolution"], r["handler"]) for r in ktor_rows if r["catalog_id"] == "ktor-routing"}
    assert {
        ("GET", "/api/orders", "resolved", None),
        ("POST", "/api/orders", "resolved", None),
        ("GET", "/api/v2/orders", "resolved", None),
        ("DELETE", "/api/v2/orders/{id}", "resolved", None),
        ("GET", "/api", "resolved", None),           # get { } on the prefix: Ktor serves the prefix itself
        ("GET", "/health", "resolved", None),
    } <= rows, sorted(rows)
    stray = [r for r in ktor_rows if r["caller"].endswith("#elsewhere(…)")]  # match on the method name
    assert stray and all(r["resolution"] == "unresolved" for r in stray) and not any(str(r["path"]).startswith("/api") for r in stray)
```

(Fix the `caller` match to the real symbol shape — `KtorRoutesKt#elsewhere(sig_…)`; use `"#elsewhere(" in r["caller"]`.) Ktor's own rule for `get { }` under `route("/api")`: the route is `/api` — measured from Ktor's `RoutingBuilderKt.get(Route, Function2)` = `method(Get) { handle(body) }` on the receiver, which is the prefix node itself; so the rule is the empty literal path (`path: ""`, Task 3's word), not a catch-all.

- [ ] **Step 4: the catalog.**

```yaml
id: ktor-routing
displayName: Ktor (routing DSL)
style: combinator
protocol: http
direction: inbound

detect:
  coordinates: ["io.ktor:ktor-server-core-jvm", "io.ktor:ktor-server-core"]

measured:
  - { artifact: io.ktor:ktor-server-core-jvm, versions: ["3.0.3"],
      identity: reported, by: scripts/probes/w19_catalog_surface.md }

requires: [call_site, string_constants, chain_reconstruction]

matches:
  entries:
    # `routing(Application, Function1<Routing, Unit>)` — the block's parameter is the root
    # `Routing`, and every verb inside is called on it: `origin_param: 0`.
    - owner: io.ktor.server.routing.RoutingRootKt
      method: routing
      body_arg: 1
      origin_param: 0
  vocabulary:
    prefixes:
      # `route(Route, String, Function1<Route, Unit>)`: the receiver is argument 0 (must be the
      # enclosing block's Route), the path argument 1, the block argument 2 — whose own
      # parameter is the new Route.
      - { owner: io.ktor.server.routing.RoutingBuilderKt, method: route, arity: 3,
          receiver_arg: 0, path_arg: 1, body_arg: 2, origin_param: 0 }
    verbs:
      # Per verb: (Route, String, Function2) and (Route, Function2) — the second serves the
      # receiver route itself (the empty literal path).
      - { owner: io.ktor.server.routing.RoutingBuilderKt, method: get, verb: GET, arity: 3, receiver_arg: 0, path_arg: 1, handler_arg: 2 }
      - { owner: io.ktor.server.routing.RoutingBuilderKt, method: get, verb: GET, arity: 2, receiver_arg: 0, path: "", handler_arg: 1 }
      # … post put patch delete head options …

slice:
  outside:
    - owner: io.ktor.server.routing.RoutingBuilderKt
      method_names: [route]      # the FOUR-argument `route(Route, String, HttpMethod, Function1)` — a prefix carrying a verb; one unresolved row today (unrecognised arity), named as a gap
      why: >
        …
```

(The slice audit may refuse a name that is also read; if so, state the four-argument overload in the prefix comment instead and let the unrecognised-overload row speak.) Run the live test → PASS.

- [ ] **Step 5: near-miss, probe, gate.** `declines("ktor-routing")` in the combinator test file: `routing` on another owner → nothing; pinned to `combinator.entry-owner-is-the-declared-type`. Add the Ktor artifact to `scripts/probes/w19_catalog_surface/run.sh`'s list and the owners to `sweep.py` if it enumerates by catalog; regenerate. Full gate (the suite compiles the new module through `fixture_build`).

```bash
git add fixtures/orders-ktor tests/fixture_build.py src/sextant/catalogs/ktor-routing.yml tests/e2e/test_rest_inbound_delivered.py tests/application/test_combinator_engine.py scripts/probes/w19_catalog_surface/run.sh scripts/probes/w19_catalog_surface/sweep.py scripts/probes/w19_catalog_surface.md
git commit -m "feat(catalogs): Ktor's routing DSL derives every route under its nested prefixes, the receiver argument checked against the block's own Route (ktor-routing; A2 Task 5, spec §12)"
```

---

### Task 6: chain-form composers, negators, the terminal, `verb_arg`, array paths

**Files:**
- Modify: `src/sextant/application/resolve/engines/combinator.py` (`_TreeContext` gains `chain_composers: dict[tuple[str,str], str]`, `negators: frozenset[tuple[str,str]]`; `_routes_of` gains the `terminal` branch; new `_chained_constraints`; `_verb_constraints` reads `verb_arg`; `_argument_constraints` reads a string array; `_validate_matches` accepts the keys)
- Modify: `docs/components/D02-catalog-schema.md`, `scripts/guard_check.py`
- Test: `tests/application/test_combinator_engine.py`

**Interfaces:**
- Consumes: A1's rules; Task 4's `origin_parameter`.
- Produces: `matches.vocabulary.chain_composers: {and: [{owner, method}], or: [...]}`, `matches.vocabulary.negators: [{owner, method}]`, rule key `terminal: true` (with `handler_arg` or `handler: none`), rule key `verb_arg: int` (instead of `verb`), and: a `path_arg` argument that is an array of string literals is one branch per element. Task 7 writes rules with all of them.

**What the spec says (§12 words 4–5, as amended):** a gateway route is a receiver chain of predicate calls composed by the zero-argument `and()`/`or()`, emitted by the chain's last call; the terminal folds the chain as constraints — origin (or the body's origin parameter) starts one empty branch, pass-throughs stepped over, each other rule's constraints merged into every branch, `or()` opens a new branch (left-associative), a negator poisons every branch, an unread head poisons; merged with the terminal's own constraints; a route reading no path is `/**`.

- [ ] **Step 1: tests, first and failing.** Hand-built, on an invented gateway-shaped vocabulary:

```python
# --- chain-form composers and a terminal (spec §12 word 4) -------------------------

SPEC = "com/example/gw/PredicateSpec#"
BOOL = "com/example/gw/BooleanSpec#"
GW = "com/example/gw/Routes#"


def _gateway_matches() -> dict[str, object]:
    return {
        "entries": [{"owner": "com.example.gw.Routes", "method": "route", "body_arg": 1, "origin_param": 0}],
        "origins": [{"owner": "com.example.gw.Routes", "method": "routes", "arity": 0}],
        "vocabulary": {
            "prefixes": [{"owner": "com.example.gw.PredicateSpec", "method": "path", "arity": 1, "path_arg": 0}],
            "verbs": [
                {"owner": "com.example.gw.PredicateSpec", "method": "method", "arity": 1, "verb_arg": 0},
                {"owner": "com.example.gw.BooleanSpec", "method": "uri", "arity": 1, "terminal": True, "handler": "none"},
            ],
            "chain_composers": {
                "and": [{"owner": "com.example.gw.BooleanSpec", "method": "and"}],
                "or": [{"owner": "com.example.gw.BooleanSpec", "method": "or"}],
            },
            "negators": [{"owner": "com.example.gw.PredicateSpec", "method": "not"}, {"owner": "com.example.gw.BooleanSpec", "method": "negate"}],
        },
        "continuations": [
            {"name": "build", "owner": "com.example.gw.Routes"},
            {"name": "filters", "owner": "com.example.gw.BooleanSpec", "pass_through": True},
        ],
    }


def _gateway_body(chain: list[tuple[str, str, list[CallArgument]]]) -> list:
    """`route("id", r -> r.<chain>.uri("http://x"))`: `chain` is (owner, name, args) from the
    head; each call's receiver is the previous call's result, the head's is the body's
    parameter 0 (the lambda captures nothing)."""
    caller = DECLARER + "routes(sig_r)."
    entry_sites = [
        _site(caller, 0, GW, "routes", result=0, descriptor="()Lcom/example/gw/Builder;"),
        _site(caller, 1, GW, "route", invoke_kind="virtual", receiver=0, result=1,
              descriptor="(Ljava/lang/String;Ljava/util/function/Function;)Lcom/example/gw/Builder;",
              arguments=[CallArgument(kind="string", value="id"),
                         CallArgument(kind="lambda", symbol=INLINE_BODY, source=1, captures=0)]),
        _site(caller, 2, GW, "build", invoke_kind="virtual", receiver=1, result=2, descriptor="()Lcom/example/gw/Locator;"),
    ]
    body: list[CallSiteFact] = []
    previous: int | None = None
    for ordinal, (owner, name, args) in enumerate(chain):
        body.append(CallSiteFact(
            document_id="doc_1", caller=INLINE_BODY, invoke_kind="virtual", ordinal=ordinal,
            target=CallTarget(owner=owner, name=name, descriptor="(...)V"),
            receiver=previous, receiver_parameter=0 if previous is None else None, result=ordinal,
            arguments=args,
        ))
        previous = ordinal
    return [_method_symbol(INLINE_BODY), *entry_sites, *body]


def _enum(name: str) -> CallArgument:
    return CallArgument(kind="enum", symbol="org/springframework/http/HttpMethod#" + name + ".")


def test_a_predicate_chain_ending_at_a_terminal_is_one_route(tmp_path: Path):
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/orders/**")]),
        (BOOL, "and", []),
        (SPEC, "method", [_enum("GET")]),
        (BOOL, "uri", [CallArgument(kind="string", value="http://orders")]),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    assert _identities(_rows(workspace)) == [("GET", "/orders/**", None, "resolved")]


def test_or_opens_a_branch_and_and_binds_to_the_left(tmp_path: Path):
    """`(a or b) and GET`, left-associative as the framework composes it."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "or", []),
        (SPEC, "path", [CallArgument(kind="string", value="/b")]),
        (BOOL, "and", []),
        (SPEC, "method", [_enum("GET")]),
        (BOOL, "uri", [CallArgument(kind="string", value="http://x")]),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    assert _identities(_rows(workspace)) == [("GET", "/a", None, "resolved"), ("GET", "/b", None, "resolved")]


def test_a_verb_only_route_serves_every_path_and_a_vararg_of_verbs_is_one_branch_each(tmp_path: Path):
    chain = [
        (SPEC, "method", [CallArgument(kind="array", elements=[_enum("GET"), _enum("POST")])]),
        (BOOL, "uri", [CallArgument(kind="string", value="http://x")]),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    assert _identities(_rows(workspace)) == [("GET", "/**", None, "resolved"), ("POST", "/**", None, "resolved")]


def test_a_negator_anywhere_in_the_chain_poisons_the_route(tmp_path: Path):
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "negate", []),
        (BOOL, "uri", [CallArgument(kind="string", value="http://x")]),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    assert [(row["path"], row["resolution"]) for row in _rows(workspace)] == [(None, "unresolved")]


def test_a_pass_through_in_the_chain_contributes_nothing(tmp_path: Path):
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "filters", [CallArgument(kind="lambda", symbol=HEALTH, source=0, captures=0)]),
        (BOOL, "uri", [CallArgument(kind="string", value="http://x")]),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    assert _identities(_rows(workspace)) == [(None, "/a", None, "resolved")]


def test_a_path_vararg_is_one_branch_per_literal(tmp_path: Path):
    chain = [
        (SPEC, "path", [CallArgument(kind="array", elements=[CallArgument(kind="string", value="/a"), CallArgument(kind="string", value="/b")])]),
        (BOOL, "uri", [CallArgument(kind="string", value="http://x")]),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    assert _identities(_rows(workspace)) == [(None, "/a", None, "resolved"), (None, "/b", None, "resolved")]


def test_a_chain_whose_head_is_not_the_origin_parameter_poisons(tmp_path: Path):
    facts = _gateway_body([(SPEC, "path", [CallArgument(kind="string", value="/a")]),
                           (BOOL, "uri", [CallArgument(kind="string", value="http://x")])])
    head = next(f for f in facts if isinstance(f, CallSiteFact) and f.target.name == "path")
    facts[facts.index(head)] = head.model_copy(update={"receiver_parameter": None})   # a field receiver
    workspace = _resolve(tmp_path, facts, _catalog(_gateway_matches()))
    assert [row["resolution"] for row in _rows(workspace)] == ["unresolved"]
```

Run → all FAIL (unknown keys refused at load, or `[]`).

- [ ] **Step 2: the engine.**

`_context_of`: `chain_composers` → `dict[(owner, method)] -> "and" | "or"`; `negators` → `frozenset`. `_claimed` also true for both. `_routes_of`, before the verb branch:

```python
    if key in context.verb_names:
        verb = _matching_rule(site, context.verbs)
        if verb is None:
            return [_Route(poisons=_IDENTITY_POISON)]
        if verb.get("terminal"):
            # Spec §12 word 4: the route is the receiver chain folded as CONSTRAINTS,
            # merged with this call's own — the chain's last call emits it, and there is
            # exactly one route per branch the chain's `or()`s opened.
            handler = None if verb.get("handler") == "none" else _handler_of(site["arguments"], frozenset({verb["handler_arg"]}), context.method_symbols)
            own = _verb_constraints(site, verb, scope)  # [] own constraints for a bare terminal is [_Route()]
            return [replace(_served(_merged(branch, mine)), handler=handler) for branch in _chained_constraints(site, scope) for mine in own]
```

(`_verb_constraints` for a rule with neither `verb`/`verb_arg` nor positions must return `[_Route()]`, not `[_Route(verb=None)]` through `_served` — check what it returns for a verb-less path-less rule after A1 and adjust so a bare terminal contributes an empty route; `_served` is applied once, after the merge.)

`_chained_constraints`:

```python
def _chained_constraints(site: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The receiver chain `site` ends, folded as one route's constraints (spec §12 word 4):
    walked from its head, every branch starts empty; a rule's constraints merge into each
    branch; a chain-form `or()` makes the next contribution a branch of its own — the
    framework composes left to right, `(a or b) and c`; a negator, or a head that is
    neither a declared origin nor the body's own parameter, poisons every branch; a
    pass-through contributes nothing."""
    chain: list[dict[str, Any]] = []
    current = _producing_site(site["receiver"], scope, exclude=site)
    head = site if current is None else None
    while current is not None:
        chain.append(current)
        nxt = _producing_site(current["receiver"], scope, exclude=current)
        if nxt is None:
            head = current
        current = nxt
    chain.reverse()
    context = scope.context
    # The head: an origin call, or a call on the body's origin parameter.
    if chain and _matching_rule(chain[0], context.origins) is not None:
        chain = chain[1:]
        branches = [_Route()]
    elif head is not None and head["receiver"] is None and scope.origin_parameter is not None \
            and head.get("receiver_parameter") == scope.origin_parameter:
        branches = [_Route()]
    elif head is not None and head["receiver"] is None and scope.origin_parameter is None:
        branches = [_Route()]   # the permissive body rule (Task 4)
    else:
        return [_Route(poisons=_IDENTITY_POISON)]
    opening = False
    for call in chain:
        key = (str(call["owner"]), str(call["name"]))
        if key in context.negators:
            return [_Route(poisons=_IDENTITY_POISON)]
        if _is_pass_through(call, context):
            continue
        composer = context.chain_composers.get(key)
        if composer == "or":
            opening = True
            continue
        if composer == "and":
            continue
        contributed = _constraints_of(call, scope)
        if not contributed:
            return [_Route(poisons=_IDENTITY_POISON)]
        if opening:
            branches = [*branches, *contributed]
            opening = False
        else:
            branches = [_merged(branch, c) for branch in branches for c in contributed]
    return branches
```

Note the `or` semantics: `path("/a").or().path("/b")` → branches `[/a]`, then `or` → the next contribution `[/b]` is appended as its own branch → `[/a, /b]`; a following `.and().method(GET)` merges into both ✓. (A chain where the head itself is the `site`'s receiver — the terminal directly on the origin parameter — has an empty `chain` and returns `[_Route()]` → `/**` after `_served`.)

`verb_arg` in `_verb_constraints`: the argument at `verb_arg` — a `string` literal → that verb (upper-cased as written); an `enum` → its member name (the symbol's last segment, `_enum_symbols`' convention — read `shapes/expansion.py`); an `array` of those → one branch per element; anything else → `_Route(poisons=(_METHOD,))`. In `_argument_constraints`: an `array` kind whose elements are all `string` literals → one `_Route(path_parts=(value,))` per element; an array with any other element → poison.

- [ ] **Step 3: D02, guards, gate.** D02: `chain_composers`, `negators`, `terminal`, `verb_arg`, the array rule — in the combinator section, with the gateway chain as the example. Guard `combinator.negator-poisons` (anchor: the `if key in context.negators:` line → `if False:`) pinned by the negator test. `--guards` end to end. Full gate — no shipped catalog uses the words, no live row moves.

```bash
git add src/sextant/application/resolve/engines/combinator.py docs/components/D02-catalog-schema.md scripts/guard_check.py tests/application/test_combinator_engine.py
git commit -m "feat(resolve): a receiver chain of predicates folds as one route's constraints — chain-form and/or, negators, a terminal, a verb read from an argument, a path vararg one branch per literal (A2 Task 6, spec §12)"
```

---

### Task 7: Spring Cloud Gateway — a new fixture module, two catalogs, `G-30` and `G-30-outbound`

**Files:**
- Create: `fixtures/orders-gateway/pom.xml`, `fixtures/orders-gateway/src/main/java/com/acme/gw/GatewayRoutes.java`
- Modify: `tests/fixture_build.py` (`PRIMED_FIXTURES` += `"orders-gateway"`)
- Create: `src/sextant/catalogs/spring-cloud-gateway.yml` (combinator, http inbound), `src/sextant/catalogs/spring-cloud-gateway-outbound.yml` (single_call, http outbound)
- Test: `tests/e2e/test_rest_inbound_delivered.py` (`gateway_rows` module fixture), `tests/e2e/test_rest_outbound_delivered.py`, near-misses
- Regenerate: `scripts/probes/w19_catalog_surface.md` (sweep gains `org.springframework.cloud:spring-cloud-gateway-server-webflux:5.0.0`)

**Interfaces:**
- Consumes: Tasks 4 and 6's words; `single_call`'s `lambda_steps`.
- Produces: `G-30`, `G-30-outbound` closed.

- [ ] **Step 1: measure.** The gateway 5.0.0 API (`javap -p -s -cp $(find ~/.m2 -name 'spring-cloud-gateway-server-webflux-5.0.0.jar')` on `RouteLocatorBuilder`, `RouteLocatorBuilder$Builder`, `PredicateSpec`, `BooleanSpec`, `BooleanSpec$BooleanOpSpec`, `UriSpec`, `GatewayFilterSpec`, `Buildable`):
  - `RouteLocatorBuilder.routes()` → `Builder` (origin, arity 0); `Builder.route(String, Function<PredicateSpec, Buildable<Route>>)`, `route(Function)`, `build()`.
  - `PredicateSpec`: `path(String...)`, `path(boolean, String...)`, `method(HttpMethod...)`, `method(String...)`, `host(String...)`, `header(String)`, `header(String, String)`, `query(String)`, `query(String, String)`, `cookie(String, String)`, `remoteAddr(String...)`, `after/before/between(ZonedDateTime…)`, `readBody`, `weight`, `cloudFoundryRouteService`, `not(Function)`, `alwaysTrue()`, `order(int)`, `predicate(...)`, `asyncPredicate(...)`.
  - `BooleanSpec`: `and()`, `or()`, `negate()`, `filters(Function<GatewayFilterSpec, UriSpec>)`; `BooleanOpSpec` (extends `PredicateSpec`): the same predicates plus `not(Function)`.
  - `UriSpec`: `uri(String)`, `uri(URI)`, `metadata(…)` ×2.
  Record the full lists.

- [ ] **Step 2: the module and fixture.** `fixtures/orders-gateway/pom.xml` — `spring-cloud-gateway-server-webflux:5.0.0`, `spring-webflux:7.0.2`, `spring-web:7.0.2`, `spring-context:7.0.2`, `spring-core:7.0.2`, `spring-beans:7.0.2`, `reactor-core` (the version `spring-webflux 7.0.2` declares — read its pom in `~/.m2`), each with the `<exclusions>*` pattern from `orders-javalin/pom.xml`, `maven.compiler.release` 21. Compile online once if a jar is missing. `GatewayRoutes.java`:

```java
// Spring Cloud Gateway's Java DSL (`G-30` inbound, `G-30-outbound`; spec §14): every route is a
// lambda handed to `route(…)`, its predicates a chain on the lambda's own parameter, its target
// the `uri(…)` at the chain's end. Both `route` overloads; path only; path and method; `or`;
// `not`; a lambda capturing a local and one capturing `this` — the two capture shapes a fixed
// parameter index gets wrong; every route ends in `uri`, one `http://`, one `lb://`.
package com.acme.gw;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;

@Configuration
public class GatewayRoutes {
    private final String billing = "http://billing-service";

    @Bean
    public RouteLocator routes(RouteLocatorBuilder builder) {
        String prefix = "/legacy";
        return builder.routes()
            .route("orders", r -> r.path("/orders/**").uri("http://orders-service"))
            .route("orders-write", r -> r.path("/orders/**").and().method(HttpMethod.POST, HttpMethod.PUT)
                                         .filters(f -> f.stripPrefix(1)).uri("lb://orders-service"))
            .route("either", r -> r.path("/a/**").or().path("/b/**").uri("http://ab-service"))
            .route("not-admin", r -> r.not(p -> p.path("/admin/**")).uri("http://public-service"))
            .route("legacy", r -> r.path(prefix + "/**").uri("http://legacy-service"))          // captures a local
            .route("billing", r -> r.path("/billing/**").uri(billing))                          // captures this
            .route(r -> r.host("**.example.org").uri("http://host-service"))                    // route(Function): host only → /**
            .build();
    }
}
```

Compile: `cd fixtures/orders-gateway && mvn -q compile` (online once), then `-o`. `javap -p target/classes/com/acme/gw/GatewayRoutes.class` must show `lambda$routes$N` methods with the `PredicateSpec` at index 0 or 1 as the capture shape dictates — record the list in the report.

- [ ] **Step 3: the live tests, first and failing.**

```python
def test_gateway_routes_derive_their_inbound_surface(gateway_rows):
    """`G-30`, spec §14 test 10: the captured-local and captured-`this` routes read the right
    path (the two rows a fixed-index design gets wrong); `or` two branches; `not` unresolved;
    a host-only route serves every path; no handler on any row; caller = `routes`."""
    rows = {(r["method"], r["path"], r["resolution"]) for r in gateway_rows if r["catalog_id"] == "spring-cloud-gateway"}
    assert {
        (None, "/orders/**", "resolved"),
        ("POST", "/orders/**", "resolved"), ("PUT", "/orders/**", "resolved"),
        (None, "/a/**", "resolved"), (None, "/b/**", "resolved"),
        (None, None, "unresolved"),                      # not-admin
        (None, "/legacy/**", "resolved"),                # captured local — `prefix + "/**"` is a concat: see below
        (None, "/billing/**", "resolved"),               # captured this
        (None, "/**", "resolved"),                       # host only
    } <= rows, sorted(rows)
    assert all(r["handler"] is None and r["caller"].endswith("#routes(sig_" + r["caller"].split("(sig_")[1]) for r in gateway_rows if r["catalog_id"] == "spring-cloud-gateway")


def test_gateway_targets_derive_outbound(gateway_rows):
    """`G-30-outbound`: every `uri(…)` through `lambda_steps`, kept whole (a routing
    destination, not a request URL — `lb://` is not a URL), caller = `routes`."""
    targets = {r["path"] for r in gateway_rows if r["catalog_id"] == "spring-cloud-gateway-outbound" and r["direction"] == "outbound"}
    assert targets >= {"http://orders-service", "lb://orders-service", "http://ab-service", "http://public-service", "http://legacy-service", "http://host-service"}
```

`prefix + "/**"` compiles to a `concat` argument (`/legacy/**`? no — `prefix` is a captured VALUE, and the extractor records the template `{}/**` with a hole). So the captured-local route's path is a `concat` kind, which `_argument_constraints` poisons → `(None, None, "unresolved")` — that is the honest answer for a path built from a captured local, and the row still proves the parameter index (it is attributed, not dropped). Change the expectation to `(None, None, "unresolved")` for `legacy` and assert the row's caller — but then it is indistinguishable from `not-admin`. Instead make the captured local a full literal path: `String legacyPath = "/legacy/**"; … r.path(legacyPath)` — a `parameter`-kind? No: a captured local reaching the body is the body's parameter 0 and the path argument is `{kind: parameter, value: 0}` → unresolved too. The capture shape's proof lives in the extractor tests (A1 Task 1) and in `billing` (captured `this`, the field read `this.billing` → a `field`-kind argument that `_address_read`… `combinator` has no field ladder → unresolved). So: keep both rows as UNRESOLVED and assert they exist with the RIGHT ORIGIN (the row is under `routes`, not silence): the poison is on the path value, not on the chain head — assert the two unresolved rows carry `method` NULL and are exactly two beyond `not-admin` (three unresolved rows total). Write the expectation that way, and say in the docstring what each unresolved row proves. The `uri(billing)` in the outbound catalog is a field read → `lambda_steps` `channel_arg` on a `field` argument → `single_call`'s field ladder may read `this.billing` = `"http://billing-service"` (a `final` field with an initialiser is a `field_write` fact) — measure; expect `http://billing-service` to appear, else `unresolved`, and pin whichever the measurement shows with the reason.

- [ ] **Step 4: the two catalogs.**

`spring-cloud-gateway.yml`:

```yaml
id: spring-cloud-gateway
displayName: Spring Cloud Gateway (route DSL, inbound)
style: combinator
protocol: http
direction: inbound
detect:
  coordinates: ["org.springframework.cloud:spring-cloud-gateway-server-webflux", "org.springframework.cloud:spring-cloud-starter-gateway", "org.springframework.cloud:spring-cloud-gateway-server"]
measured:
  - { artifact: org.springframework.cloud:spring-cloud-gateway-server-webflux, versions: ["5.0.0"], identity: reported, by: scripts/probes/w19_catalog_surface.md }
requires: [call_site, string_constants, chain_reconstruction]
matches:
  entries:
    - { owner: org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder$Builder, method: route, arity: 2, arg_types: { 0: java.lang.String }, body_arg: 1, origin_param: 0 }
    - { owner: org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder$Builder, method: route, arity: 1, body_arg: 0, origin_param: 0 }
  origins:
    - { owner: org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder, method: routes, arity: 0 }
  vocabulary:
    prefixes:
      # `path(String...)` on PredicateSpec and on BooleanOpSpec (after an and()/or()) — a vararg
      # is one branch per literal.
      - { owner: org.springframework.cloud.gateway.route.builder.PredicateSpec, method: path, arity: 1, path_arg: 0 }
      - { owner: org.springframework.cloud.gateway.route.builder.BooleanSpec$BooleanOpSpec, method: path, arity: 1, path_arg: 0 }
    verbs:
      - { owner: org.springframework.cloud.gateway.route.builder.PredicateSpec, method: method, arity: 1, verb_arg: 0 }
      - { owner: org.springframework.cloud.gateway.route.builder.BooleanSpec$BooleanOpSpec, method: method, arity: 1, verb_arg: 0 }
      - { owner: org.springframework.cloud.gateway.route.builder.UriSpec, method: uri, arity: 1, terminal: true, handler: none }
      - { owner: org.springframework.cloud.gateway.route.builder.BooleanSpec, method: uri, arity: 1, terminal: true, handler: none }
    chain_composers:
      and: [{ owner: org.springframework.cloud.gateway.route.builder.BooleanSpec, method: and }]
      or:  [{ owner: org.springframework.cloud.gateway.route.builder.BooleanSpec, method: or }]
    negators:
      - { owner: org.springframework.cloud.gateway.route.builder.PredicateSpec, method: not }
      - { owner: org.springframework.cloud.gateway.route.builder.BooleanSpec$BooleanOpSpec, method: not }
      - { owner: org.springframework.cloud.gateway.route.builder.BooleanSpec, method: negate }
      - { owner: org.springframework.cloud.gateway.route.builder.PredicateSpec, method: predicate }
      - { owner: org.springframework.cloud.gateway.route.builder.PredicateSpec, method: asyncPredicate }
  continuations:
    - { name: build, owner: org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder$Builder }
    # Predicates that narrow WHO is served, not WHAT path: the route still serves its path.
    - { name: host,       owner: org.springframework.cloud.gateway.route.builder.PredicateSpec, pass_through: true }
    - { name: header,     owner: …PredicateSpec, pass_through: true }
    - { name: query,      … }  # cookie, remoteAddr, after, before, between, readBody, weight, order, alwaysTrue, cloudFoundryRouteService
    - { name: filters,    owner: org.springframework.cloud.gateway.route.builder.BooleanSpec, pass_through: true }
    - { name: metadata,   owner: org.springframework.cloud.gateway.route.builder.UriSpec, pass_through: true }
```

Which owner a call's `owner` carries in the facts is the DECLARING class as the compiler wrote it (`BooleanSpec$BooleanOpSpec` for a `path` after `and()`); declare both owners wherever the jar declares the member on both. The `build()` continuation is what roots (the chain `routes().route(…).route(…).build()` is a plain receiver chain of body-linked entries — `_routes_of` for `build` → `_declared_routes(extends_receiver)` → `_chained_routes` → the `route` calls' body routes; confirm on the hand-built model in Task 6's `_gateway_body`, which already has this shape).

`spring-cloud-gateway-outbound.yml`:

```yaml
id: spring-cloud-gateway-outbound
displayName: Spring Cloud Gateway (route targets, outbound)
style: single_call
protocol: http
direction: outbound
detect: { coordinates: [same three] }
measured: [same]
requires: [call_site, string_constants]
matches:
  methods:
    - { name: route, arity: 2, descriptor: "(Ljava/lang/String;Ljava/util/function/Function;)Lorg/springframework/cloud/gateway/route/builder/RouteLocatorBuilder$Builder;",
        lambda_arg: 1,
        lambda_steps: [{ owner: org.springframework.cloud.gateway.route.builder.UriSpec, method: uri, channel_arg: 0 },
                       { owner: org.springframework.cloud.gateway.route.builder.BooleanSpec, method: uri, channel_arg: 0 }] }
    - { name: route, arity: 1, descriptor: "(Ljava/util/function/Function;)Lorg/…/RouteLocatorBuilder$Builder;",
        lambda_arg: 0, lambda_steps: [same two] }
```

`single_call` rows match on `name` + `arity` + `descriptor` — and on the OWNER? Read `_matching_method`'s owner handling and the `types`/`owner` block other single_call catalogs declare (`spring-sqs-template.yml`'s head) and declare `RouteLocatorBuilder$Builder` the same way. `channel_arg` keeps `lb://…` whole (D02: a channel is never split). Run both live tests → PASS.

- [ ] **Step 5: near-misses, probe, gate.** `declines("spring-cloud-gateway")`: a `route(String, Function)` on a different owner → nothing (pinned to `combinator.entry-owner-is-the-declared-type`); `declines("spring-cloud-gateway-outbound")`: `uri` inside the lambda on another owner → nothing (pinned to `single_call.lambda-step-owner-is-the-declared-type`). w19: add the artifact and regenerate (`RouteLocatorBuilder$Builder`, `PredicateSpec` N of M). Full gate.

```bash
git add fixtures/orders-gateway tests/fixture_build.py src/sextant/catalogs/spring-cloud-gateway.yml src/sextant/catalogs/spring-cloud-gateway-outbound.yml tests/e2e/test_rest_inbound_delivered.py tests/e2e/test_rest_outbound_delivered.py tests/application/test_combinator_engine.py tests/application/test_endpoints.py scripts/probes/w19_catalog_surface/run.sh scripts/probes/w19_catalog_surface/sweep.py scripts/probes/w19_catalog_surface.md
git commit -m "feat(catalogs): Spring Cloud Gateway's route DSL derives its inbound surface from the predicate chain on each lambda's own parameter, and its targets outbound (G-30, G-30-outbound; A2 Task 7, spec §12)"
```

---

### Task 8: the JDK and Apache clients as `fluent` catalogs, and `url_via`

**Files:**
- Modify: `src/sextant/application/resolve/engines/fluent.py` (`url_via` — the `channel_via` ladder applied to the `url` capture when its literal did not resolve; `_validate_channel_via_entries` covers `url_via` too)
- Create: `src/sextant/catalogs/jdk-httpclient.yml`, `src/sextant/catalogs/apache-httpclient.yml`
- Modify: `fixtures/orders-service/pom.xml` (`org.apache.httpcomponents.client5:httpclient5:5.2.3`, API only), create `fixtures/orders-service/src/main/java/com/acme/orders/httpclient/JdkOrdersClient.java`, `ApacheOrdersClient.java`
- Modify: `docs/components/D02-catalog-schema.md` (fluent section: `url_via`), `scripts/guard_check.py`
- Test: the fluent engine test file, `tests/e2e/test_rest_outbound_delivered.py`, near-misses

**Interfaces:**
- Consumes: `fluent`'s roots/steps/terminal/`terminal_via_argument`/`channel_via` (`fluent.py:1-30, 405-470, 500-520, 1000-1050`; `okhttp.yml` as the model).
- Produces: `url_via: [{owner, method, arg}]` on a root or step; `jdk-httpclient` closed; REST outbound's row empties.

**What the spec says (§12, `jdk-httpclient` row as amended):** `okhttp.yml`'s exact shape. One root `newBuilder` with `captures: {http_method: GET, url: arg0}` — the argument-less overload's `arg0` reads nothing and the `uri` step overwrites it; `uri(URI.create("…"))` / `uri(new URI("…"))` reach the step as `unresolved`+`source`, followed through `url_via`; terminal `build` via `HttpClient.send`/`sendAsync`. Apache: static roots `ClassicRequestBuilder.get/post/…(String)` with `build` via `CloseableHttpClient.execute`; constructor roots `HttpGet(String)`… that are themselves the terminal via `execute`.

- [ ] **Step 1: measure.** `javap -p -s` on `java.net.http.HttpRequest` (`newBuilder()`, `newBuilder(URI)`), `HttpRequest$Builder` (`uri(URI)`, `GET()`, `POST(BodyPublisher)`, `PUT(BodyPublisher)`, `DELETE()`, `HEAD()` (21+), `method(String, BodyPublisher)`, `header`, `headers`, `setHeader`, `timeout`, `version`, `expectContinue`, `copy`, `build()`), `java.net.http.HttpClient` (`send`, `sendAsync` ×2) — from `$JAVA_HOME/jmods` via `javap -cp $JAVA_HOME/jmods/java.net.http.jmod` or `--module java.net.http`; `java.net.URI` (`create(String)`, `<init>(String)`). Apache 5.2.3: `org.apache.hc.core5.http.io.support.ClassicRequestBuilder` (`get()`, `get(String)`, `get(URI)`, same for post/put/delete/patch/head/options/trace, `setUri`, `build()`), `org.apache.hc.client5.http.classic.methods.HttpGet` (`<init>(String)`, `<init>(URI)`) etc., `CloseableHttpClient.execute(…)` overloads. Record.

- [ ] **Step 2: the fixtures.**

```java
// JDK `HttpClient` (`jdk-httpclient`, spec §14): the builder chain `okhttp.yml` already reads on
// OkHttp — a static root, verb-setting steps, `build()` handed to `send`. Both `newBuilder`
// overloads; `uri(URI.create(…))` and `uri(new URI(…))`; `method("PATCH", …)`; a request
// built in a helper and sent elsewhere — one unresolved row, the split-builder rule.
package com.acme.orders.httpclient;

import java.net.URI;
import java.net.URISyntaxException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class JdkOrdersClient {
    private final HttpClient client = HttpClient.newHttpClient();

    public String create(String body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://orders.example.com/v1/orders"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String fetch(String id) throws Exception {
        return client.send(HttpRequest.newBuilder(new URI("https://orders.example.com/v1/orders/" + id)).GET().build(),
                           HttpResponse.BodyHandlers.ofString()).body();
    }

    public void patch(String id, String body) {
        client.sendAsync(HttpRequest.newBuilder(URI.create("https://orders.example.com/v1/orders/42"))
                             .method("PATCH", HttpRequest.BodyPublishers.ofString(body)).build(),
                         HttpResponse.BodyHandlers.discarding());
    }

    public String viaHelper() throws Exception {
        return client.send(deleteRequest(), HttpResponse.BodyHandlers.ofString()).body();
    }

    private HttpRequest deleteRequest() {
        return HttpRequest.newBuilder(URI.create("https://orders.example.com/v1/orders/42")).DELETE().build();
    }
}
```

`"…/orders/" + id` is a `concat` → `fluent`'s `url_of` reads the template with its hole (`/v1/orders/{}`) — check what `url_of` does with a concat (it has a documented answer; pin it). `ApacheOrdersClient.java`: `ClassicRequestBuilder.get("https://…/v1/orders").build()` handed to `client.execute(request, handler)`; `new HttpPost("https://…/v1/orders")` handed to `client.execute(post, handler)`; `new HttpGet(URI.create(…))`. Add `httpclient5` (+ `httpcore5`, same exclusions) to `orders-service/pom.xml`; compile `-o` (both jars are in `~/.m2`).

- [ ] **Step 3: live tests, first and failing** (`tests/e2e/test_rest_outbound_delivered.py`, using `analyzed_orders_service` rows with `direction == "outbound"`):

```python
def test_the_jdk_http_client_derives_every_request_it_builds(outbound_rows):
    rows = {(r["method"], r["peer"], r["path"], r["resolution"]) for r in outbound_rows if r["catalog_id"] == "jdk-httpclient"}
    assert {
        ("POST", "orders.example.com", "/v1/orders", "resolved"),
        ("GET", "orders.example.com", "/v1/orders/{}", "resolved"),    # the concat's hole, as url_of spells it — adjust to url_of's actual spelling
        ("PATCH", "orders.example.com", "/v1/orders/42", "resolved"),
        ("DELETE", "orders.example.com", "/v1/orders/42", "resolved"),  # built in the helper: the row is the helper's (its chain reaches build; send is elsewhere) — see below
    } <= rows, sorted(rows)
```

The helper case: `deleteRequest()`'s chain ends at `build()`, which is `terminal_via_argument` on `send` — and `send` is in ANOTHER method, so the join fails and the chain "never reaches a terminal derives nothing" (fluent's rule, `okhttp.yml` precedent: a built request not issued is not a call). So the helper's request derives NOTHING, and `viaHelper()`'s `send(deleteRequest())` argument is an `unresolved`+`source` to a call in this method with no chain → nothing. Spec §7 case 4 promised one unresolved row for the split form in `combinator`; `fluent`'s rule is different and already stated ("a built request is not an issued one", guard `fluent.a-built-request-is-not-an-issued-one`). Rule: follow `fluent`'s existing doctrine — drop the DELETE row from the expectation, assert it is ABSENT, and record in the spec's §13 case 9 that the JDK client follows `fluent`'s stated rule (a request built in one method and sent in another derives nothing, as OkHttp's does). Apache:

```python
def test_the_apache_client_derives_the_builder_and_the_constructor_forms(outbound_rows):
    rows = {(r["method"], r["path"], r["resolution"]) for r in outbound_rows if r["catalog_id"] == "apache-httpclient"}
    assert {("GET", "/v1/orders", "resolved"), ("POST", "/v1/orders", "resolved"), ("GET", "/v1/orders/7", "resolved")} <= rows, sorted(rows)
```

- [ ] **Step 4: `url_via` and the catalogs.** In `fluent.py`, where the `url` capture is read (`_composed_address` / the `channel_via` block near line 512): if the url literal did not resolve and `captures.get("url_via")` names forms, `linked_channels(url_argument, context.facts, forms)` — the SAME call `channel_via` makes (it handles `<init>` and any named method through `_linked_constructor`) — and the result feeds `url_of` as the literal; validation reuses `_validate_channel_via_entries` for `url_via`; a step's `url_via` rides in `captures` like `channel_via` does (`fluent.py:952`). Test, hand-built in the fluent engine test file: a `uri` step whose argument is `unresolved`+`source` to a `URI.create("https://h/p")` site → `peer h, path /p`; to a `new URI("…")` (`instance` + `<init>` site) → the same; to an undeclared call → unresolved. Guard `fluent.url-via-follows-only-a-declared-call` (anchor: the owner/method comparison inside `linked_channels`' caller for url — or, if `linked_channels` already has a guard for `channel_via`, pin the url test to that existing guard instead; read `guard_check.py`).

`jdk-httpclient.yml` (fluent, http, outbound). Detection: `detect.coordinates` is read only by the two styles that gate on it (`src/sextant/application/ports/catalogs.py:45-75` — `fluent` is not one; every other catalog applies module-wide today), and a JDK API has no coordinate, so declare `detect: { coordinates: [] }` with a comment saying so; the YAML loader accepts an empty list (`detect_coordinates: tuple[str, ...] = ()` is the default) — confirm at load with `tests/architecture`:

```yaml
matches:
  roots:
    - { owner: java.net.http.HttpRequest, method: newBuilder, captures: { http_method: GET, url: arg0 },
        url_via: [{ owner: java.net.URI, method: create, arg: 0 }, { owner: java.net.URI, method: <init>, arg: 0 }] }
  steps:
    - { method: uri,    captures: { url: arg0 }, url_via: [same two] }
    - { method: GET,    captures: { http_method: GET } }
    - { method: HEAD,   captures: { http_method: HEAD } }
    - { method: DELETE, captures: { http_method: DELETE } }
    - { method: POST,   captures: { http_method: POST, body: arg0 } }
    - { method: PUT,    captures: { http_method: PUT, body: arg0 } }
    - { method: method, captures: { http_method: arg0, body: arg1 } }
  terminal:
    - { method: build, terminal_via_argument: { owner: java.net.http.HttpClient, method: send } }
    - { method: build, terminal_via_argument: { owner: java.net.http.HttpClient, method: sendAsync } }
```

(Whether `terminal_via_argument.method` accepts a list, or two `build` entries are allowed, is decided by `_terminal_index` — read it; the okhttp precedent has one.) `apache-httpclient.yml`: roots `ClassicRequestBuilder.get/post/put/delete/patch/head/options(String)` each `captures: {http_method: X, url: arg0}` with `url_via` for the `URI` overloads; `<init>` roots on `HttpGet`/`HttpPost`/`HttpPut`/`HttpDelete`/`HttpPatch`/`HttpHead`/`HttpOptions` with `captures: {http_method: X, url: arg0}` and `url_via`; steps `setUri` (`url: arg0`); terminal `build` via `CloseableHttpClient.execute`, and `<init>` via `execute` for the constructor form. `detect.coordinates: ["org.apache.httpcomponents.client5:httpclient5"]`.

Run the live tests → PASS. Measure the `<init>`-root-as-terminal join on the fixture; if `_has_execute_join` does not see a constructed instance handed to `execute`, report it as the plan's stated risk with the facts, and log the constructor form (`apache-httpclient-constructors`) rather than approximate.

- [ ] **Step 5: near-misses, D02, gate.** `declines("jdk-httpclient")`: a `newBuilder` on another owner → nothing (an existing fluent guard, `fluent.root-is-a-declared-request-starter`); `declines("apache-httpclient")`: a built request never handed to `execute` → nothing (`fluent.a-built-request-is-not-an-issued-one`). D02's fluent section: `url_via`. `--guards`. Full gate; four count tests move additively (three JDK + three Apache rows, or as measured).

```bash
git add src/sextant/application/resolve/engines/fluent.py src/sextant/catalogs/jdk-httpclient.yml src/sextant/catalogs/apache-httpclient.yml fixtures/orders-service/pom.xml fixtures/orders-service/src/main/java/com/acme/orders/httpclient docs/components/D02-catalog-schema.md scripts/guard_check.py tests/application/test_fluent_engine.py tests/e2e/test_rest_outbound_delivered.py tests/application/test_endpoints.py tests/application/test_pipeline.py tests/e2e/test_vertical_slice.py tests/cli/test_app.py tests/application/test_asm_scanner.py
git commit -m "feat(catalogs): the JDK and Apache HTTP clients derive every request they build and send, a URI built by URI.create or new URI followed through url_via (jdk-httpclient; A2 Task 8, spec §12)"
```

---

### Task 9: CHANGELOG, COVERAGE, the register — part 1 now, part 2 after CI

**Files:** `CHANGELOG.md`, `docs/COVERAGE.md`, `docs/java-kotlin-delivery-list.md`, `docs/superpowers/specs/…design.md` (§13 case 9 note from Task 8)

- [ ] **Part 1 (before the PR opens):** CHANGELOG `[Unreleased]` → `### Added`: one entry for A2 (the six frameworks, the engine words, `url_via`, the two new fixture modules) in the file's register; `docs/COVERAGE.md`: the rows for Ktor, Javalin ApiBuilder, gateway, JDK/Apache client, SQS receive move from their boundary/gap wording to shipped (hand-edit prose rows; run `coverage_matrix.py`/`coverage_versions.py` for generated parts); the register's §1 tables gain the closing notes for the six; new logged items: `javalin-crud` (Minor), `ktor-route-with-verb` (the four-argument `route`, Minor), `gateway-properties-routes` (from spec §15, Major — the YAML/properties form is the commoner one), `url-openconnection` (spec §15), `kotlin-class-lambdas` (spec §15, Major — W44's DSL catalogs derive nothing on Kotlin < 2.0), `apache-httpclient-constructors` only if Task 8 measured the constructor join failing. `.venv/bin/pytest tests/architecture -q`. Commit: `docs: CHANGELOG, COVERAGE and the register catch up with PR A2's six catalogs; five gaps logged`.

- [ ] **Part 2 (after CI is green — or folded into the next PR, as the user rules):** the six ids move to ```closed with the run URL; REST outbound's `delivery` row reads empty; `coverage_matrix.py` moves REST outbound to `✅`; `test_feature_delivery.py` proves it.

---

## Self-review against the spec

| spec | task |
|---|---|
| §12 `sqs-template-receive` via `lambda_steps` | 2 |
| §12 `javalin-apibuilder` (static, no receiver check; `get(handler)` serves the prefix) | 3 (+ the `path: ""` literal, the one engine touch) |
| §12 words 1–2 `origin_param`, `receiver_arg`; shipped bodies declare `origin_param: 0` | 4 |
| §12 `ktor-routing`, handler NULL stated (§13 case 8) | 5 |
| §12 word 4 chain composers/negators/terminal, word 5 `verb_arg`, array paths | 6 |
| §12 `G-30`, `G-30-outbound`; §14 test 10/11; §13 cases 6, 7 | 7 |
| §12 `jdk-httpclient` as `fluent`, `url_via`; §14 test 14 | 8 (with the split-builder rule following `fluent`'s doctrine, recorded) |
| §14 test 16 unlinked lambda | covered by A1's `_body_routes` poison on a non-`lambda` argument — verify one existing test asserts it; if none, add it in Task 4 |
| §14 tests 17–18, §15 exclusions logged | 2–8 near-misses; 9 |
| §16 items 5–10 order | 4/6 (engine first), 3, 5, 7, 2 (SQS is data — placed early because it is cheap and independent), 8, 9 |

**Type consistency:** `origin_parameter` on `_Scope` (Task 4) is read by `_chained_routes`, `_receiver_argument_is_the_origin` (Task 4) and `_chained_constraints` (Task 6); `path: ""` (Task 3) is read by `_verb_constraints` and used by Ktor's arity-2 verbs (Task 5); `terminal`/`verb_arg`/`chain_composers`/`negators` (Task 6) are written by Task 7's catalog; `url_via` (Task 8) by both Task 8 catalogs.

**Judgement calls the executor will meet:** (1) `single_call` owner matching for the gateway-outbound rows — read the engine, follow the send catalog; (2) the JDK catalog's detection with no coordinate — measure the loader; (3) the constructor-root terminal join for Apache — measure, log if it fails; (4) Ktor's transitive jars need one online Maven run; (5) `path: ""` vs `/**` — Javalin and Ktor serve the PREFIX for a path-less verb, the Spring builder serves EVERY path: two frameworks, two truths, both measured from the framework's own code and stated in each catalog.
