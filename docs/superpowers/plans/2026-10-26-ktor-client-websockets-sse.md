# Ktor HTTP client, WebSockets and SSE — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ktor's HTTP client calls, WebSocket and SSE servers, and WebSocket and SSE clients derive boundary rows. The client's `defaultRequest` base is joined by Ktor's own URL rule. Verbs written as Ktor 3.x static fields are read, which fixes the shipped routing catalog.

**Architecture:**
- **Servers:** new verbs in the existing Ktor routing vocabulary (`combinator`).
- **HTTP client:** a new `fluent` catalog over the inlined request builder, with one general Kotlin rule: an extension function's receiver is its first argument.
- **WebSocket and SSE clients:** `single_call` catalogs.
- **Base address:** one reader, shared by the client catalogs, walks a catalog-declared configuration ladder to the client's `defaultRequest { url(…) }`.

**Tech Stack:** Python 3.13, DuckDB, pytest; Kotlin fixtures built with Maven, JDK 21.

**Spec:** `docs/superpowers/specs/2026-10-26-ktor-client-websockets-sse-design.md`

## Global Constraints

- **Gate:** `PATH=/Users/yining/programming/ai/sextant/.venv/bin:$PATH JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`. Fixtures are built with JDK 21, never 27.
- **Framework knowledge is catalog data** with a `measured:` probe (CP-54). No engine names an `io.ktor.*` type, and no rule matches a class by name suffix. JVM method names that carry compiler-made suffixes (`webSocket$default`, `sse-Mswn-_c$default`) are listed as measured data, per version.
- **Ktor 3.6.0, Kotlin 2.4.20** is the measured version, the one the real corpora use. Ktor 3.0.3's getter vocabulary stays, so older code still reads.
- **Joining a relative URL to the base** follows Ktor's own `DefaultRequest` rule, measured by CP-54, never plain concatenation (DR-6). Spring's `base` join is unchanged.
- **Row shapes follow each protocol's existing catalogs:**
  - HTTP: split into peer and path;
  - WebSocket: the whole URL in `path`, `peer` NULL, verbless;
  - SSE: as the existing SSE rows, verb GET.
- **Versions:** no new table, so `GRAPH_SCHEMA_VERSION` does not move. If a task adds one, it moves the version with the docs.
- **Guards:** every new rule gets a guard in `scripts/guard_check.py`, measured killed. A pinned test whose expectation changes is re-pinned, never deleted.
- **Issues** go to Plane. The next OI is OI-213; add its row to the id map in `docs/open-issues.md`.
- **Commit trailer:** `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- **A base not ending in `/`, joined to a relative path without a leading `/`.** The base's last segment is replaced, as Ktor does: `https://h/v1` plus `items` gives `https://h/items` (Task 5).
- **Two clients with different bases in one class.** Each call joins its own client's base, never the first one found (Task 5).
- **A client whose construction the walk cannot reach,** for example injected from another module. The relative row stays relative and `unresolved`, with the reason stated, never another client's base (Task 5).
- **A WebSocket route inside `method(HttpMethod.Post) { … }` or under a verb scope.** It stays one verbless row: never seven rows, never dropped (Task 3).
- **Ktor 3.0.3 code** (`orders-ktor-classlambdas` stays on 3.0.3) still reads its verbs through the getters, after the field form is added (Task 2).

---

### Task 1: CP-54 — Ktor 3.6.0's client, WebSocket and SSE shapes, measured

**Files:**
- Create: `scripts/probes/cp54_ktor_client_ws_sse/{probe.py,run.sh}` and `scripts/probes/cp54_ktor_client_ws_sse.md`, in the layout and generated-table convention of `scripts/probes/cp53_quarkus_mutiny_wiring/`.
- Create: the probe's own Kotlin module under `scripts/probes/cp54_ktor_client_ws_sse/module/`, compiled by Maven, never run as an application. Its `pom.xml` and `Probe.kt` start from the controller's scratch probe at `/private/tmp/claude-501/-Users-yining-programming-ai-sextant/fdac1556-cd5f-46d3-9a18-6bbe73324f48/scratchpad/ktor-probe/`.

**Interfaces:**
- Produces: the CP-54 record that every task cites in its catalog's `measured:`, as `{ artifact: io.ktor:<artifact>, versions: ["3.6.0"], identity: reported, by: scripts/probes/cp54_ktor_client_ws_sse.md }`.

- [ ] **Step 1: Write `probe.py`.** It reads the Ktor 3.6.0 jars (versions from each jar's manifest) and the compiled probe module with `javap -c -p`, and prints one table row per observation:
  - (a) `io.ktor.http.HttpMethod`'s static verb fields, all of them (Get … Options, Trace, Query);
  - (b) the inlined client sequence, for each of the five forms;
  - (c) every overload of the server `RoutingKt.webSocket`/`webSocket$default`/`webSocketRaw` and `sse`, with the role of each argument (path, protocol, handler), told apart by descriptor;
  - (d) every client `BuildersKt` WebSocket and SSE function (`webSocket`, `ws`, `wss`, `webSocketSession`, `sse`, `sseSession`, with any mangled suffix), with its argument roles;
  - (e) the `DefaultRequest` builder's URL setters and the `defaultRequest(config, block)` call shape;
  - (f) the default verb of a fresh `HttpRequestBuilder`;
  - (g) how `DefaultRequest` merges a relative URL into the base, for six cases:
    - base ending in `/` or not;
    - relative path with and without a leading `/`;
    - an absolute URL;
    - a path with query.

    Measure this by running Ktor's own merge code from the probe (a tiny `main` in the probe module, run with `java -cp`). The probe may execute Ktor's code; it never runs a downloaded project.
- [ ] **Step 2:** Run `bash scripts/probes/cp54_ktor_client_ws_sse/run.sh` and paste the generated table into the `.md`, with a verdict per row (a)–(g) and the spec section it supports.
- [ ] **Step 3:** Run `pytest tests/architecture/test_probe_provenance.py -q`. Expected: PASS.
- [ ] **Step 4:** Commit `probe(cp54): Ktor 3.6.0's client, WebSocket and SSE shapes, measured`.

### Task 2: A verb read from a static field (fixes shipped routing on Ktor 3.x)

**Files:**
- Modify: `src/sextant/application/resolve/engines/combinator.py` (verb argument resolution), `src/sextant/application/resolve/engines/fluent.py` (the `http_method` capture), `src/sextant/catalogs/ktor-routing.yml`, `docs/components/D02-catalog-schema.md`
- Test: `tests/application/test_combinator*.py` (find with `grep -rln "verb_values" tests`), `tests/application/test_fluent*.py`

**Interfaces:**
- Produces: a `verb_values.fields` map, with keys of the form `"<owner fqn>#<field name>"` and values that are verbs. For example, `"io.ktor.http.HttpMethod#Get": GET`.
  - It sits beside the existing `verb_values.getters` and is read wherever a verb argument is a `CallArgument` of kind `field` whose `symbol` names the field.
  - `fluent` gains the same vocabulary for its `http_method: argN` capture, so a field-kind verb argument resolves instead of reading `unresolved`.
  - One reader serves both engines; place it in `application/resolve/shapes/`.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_ktor3_method_block_reads_its_verb_from_the_static_field`: facts for `method(HttpMethod.Get) { get("/x") }`, where the verb argument is `{kind: field, symbol: io/ktor/http/HttpMethod#Get.}` (check the symbol's spelling against a real fact) → one GET row.
  - `test_the_ktor303_getter_form_still_reads`: the same with the Companion getter → GET. This is unchanged behaviour.
  - `test_a_fluent_verb_capture_reads_a_static_field`: under a test `fluent` catalog with `verb_values.fields` → the verb resolves.
  - `test_an_undeclared_field_is_no_verb`: any other static field passed as the verb → today's `unresolved` behaviour.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Add every CP-54 row (a) field to `ktor-routing.yml` (`fields:` beside `getters:`, including `Trace` and `Query` if `all_methods` admits them; otherwise log them), with CP-54 in `measured:`. Write the D02 rows.
- [ ] **Step 4:** Run the tests and the gate. Expected: PASS, with no expectation edited.
- [ ] **Step 5: Guard** `ktor.a-VERB-read-from-a-static-field`, edit: ignore `fields`. Measure: killed.
- [ ] **Step 6:** Commit `fix(ktor): a verb written as a Ktor 3.x static field is read (routing and fluent)`.

### Task 3: WebSocket and SSE servers in Ktor routing

**Files:**
- Modify: `src/sextant/application/resolve/engines/combinator.py` (only if a per-verb protocol needs engine support), `src/sextant/catalogs/ktor-routing.yml` (or a sibling catalog sharing its vocabulary; see spec §3b), `docs/components/D02-catalog-schema.md`
- Test: `tests/application/test_combinator*.py`

**Interfaces:**
- Produces: inbound `websocket` rows (verbless) and inbound `sse` rows (verb GET), at nested paths. All three protocols share one prefixes and entries list.
- The JVM names and overloads come from CP-54 row (c): `webSocket`, `webSocket$default`, `webSocketRaw`, and both `sse` arity-3 overloads, told apart by descriptor or `arg_types`.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_ktor_websocket_route_nests_under_its_prefix`: `routing { route("/api") { webSocket("/chat") {} } }` → one inbound `websocket` row at `/api/chat`, method NULL.
  - `test_a_ktor_sse_route_is_a_get_sse_row`: `routing { route("/api") { sse("/events") {} } }` → one inbound `sse` row, GET `/api/events`.
  - `test_a_websocket_route_under_a_verb_scope_stays_one_verbless_row`: inside `method(HttpMethod.Post) { webSocket("/ws") {} }` → one verbless row. No seven-way expansion, nothing dropped.
  - `test_the_websocket_protocol_overload_is_not_read_as_a_path`: the overload whose argument 1 is the protocol → the path comes from the right argument.
  - `test_http_routes_are_unchanged`: the existing routing tests keep their expectations.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement with the mechanism the engine supports. The requirement: one shared prefix list, never a copy per protocol.
- [ ] **Step 4:** Run the tests and the gate. Expected: PASS.
- [ ] **Step 5: Guards:**
  - `ktor.a-WEBSOCKET-route-is-a-verbless-inbound-row`;
  - `ktor.an-SSE-route-is-a-get-sse-row`;
  - `ktor.a-websocket-under-a-verb-scope-is-NOT-expanded`.

  Measure each: killed.
- [ ] **Step 6:** Commit `feat(ktor): WebSocket and SSE routes are inbound rows at their nested paths`.

### Task 4: The HTTP client, without a base (`ktor-client.yml`, `fluent`)

**Files:**
- Modify: `src/sextant/application/resolve/engines/fluent.py` (the step receiver rule), `docs/components/D02-catalog-schema.md`
- Create: `src/sextant/catalogs/ktor-client.yml`
- Test: `tests/application/test_fluent*.py` and `tests/application/test_ktor_client.py` (new)

**Interfaces:**
- Produces: an optional step key `receiver_arg: N`, meaning "this step's receiver is its argument N", for a Kotlin extension function compiled to a static method. The general rule: a step with `receiver_arg` joins the chain through that argument's value id instead of the call's receiver.
- `ktor-client.yml`:
  - `root`: `io.ktor.client.request.HttpRequestBuilder#<init>`, with the CP-54 row (f) default verb as its capture;
  - `steps`:
    - `{ owner: io.ktor.client.request.HttpRequestKt, method: url, receiver_arg: 0, captures: { url: arg1 } }`;
    - `setMethod`, with verb `arg0` resolved by Task 2's `fields`;
    - `setBody`, with body `arg0`;
  - `terminal`: the builder passed as argument 0 to `io.ktor.client.statement.HttpStatement#<init>`, in the `terminal_via_argument` shape OkHttp uses;
  - `detect.coordinates`: the Ktor client artifacts;
  - `measured:` CP-54.

- [ ] **Step 1: Write the failing tests,** with call-site facts shaped like CP-54 row (b), one per form:
  - `get("https://orders.example.com/orders")` → outbound GET, peer `orders.example.com`, path `/orders`;
  - `post(url){ setBody(x) }` → POST, with a body;
  - `get { url(u) }` → GET;
  - `request(u) { method = HttpMethod.Put }` → PUT;
  - `prepareGet(u)` → GET.

  Also `test_a_relative_url_with_no_base_stays_relative_and_unresolved`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement `receiver_arg` and write the catalog.
- [ ] **Step 4:** Run the tests and the gate. Expected: PASS. The other `fluent` catalogs are unchanged.
- [ ] **Step 5: Guards:**
  - `fluent.an-EXTENSION-step-joins-through-its-receiver-argument`;
  - `ktor.an-INLINED-client-call-is-an-outbound-row`.

  Measure each: killed.
- [ ] **Step 6:** Commit `feat(ktor): an inlined Ktor client call is an outbound HTTP row`.

### Task 5: The client's base — a declared configuration ladder and Ktor's URL join

**Files:**
- Create: `src/sextant/application/resolve/shapes/client_base.py`
- Modify: `src/sextant/application/resolve/engines/fluent.py` (the base capture source), `src/sextant/catalogs/ktor-client.yml`, `docs/components/D02-catalog-schema.md`
- Test: `tests/application/test_client_base.py`

**Interfaces:**
- **The catalog key `client_base`,** declared in `ktor-client.yml` and read by the WebSocket and SSE catalogs of Task 6:
  - `client_arg`: where the client value sits at the terminal (here, `HttpStatement#<init>`'s argument 1);
  - `ladder`: a list of `{ owner, method, block_arg }` (`HttpClient`'s constructor or factory, `defaultRequest`, and `config`, as CP-54 row (e) measures them);
  - `setter`: `{ owner: <DefaultRequestBuilder fqn>, method: url, value_arg: … }`;
  - `join`: `ktor_default_request`.
- **The readers:**
  - `client_base(workspace: Workspace, values: ValueIndex | None, client_value: dict[str, Any], declared: Mapping[str, Any]) -> tuple[str | None, str | None]`, returning `(base, unresolved_reason)`. It walks the client value with the existing value walk to its construction, then reads into each declared block's body for the next ladder entry, ending at the setter's string. Field, top-level `val`, derived `config { }`, and parameter-passed clients are followed as far as the walk already reaches.
  - `join_url(base: str, relative: str, rule: str) -> str` implements Ktor's merge exactly as CP-54 row (g) measured it.
- **Where the chain leaves the code:** `(None, "computed_base_addresses_not_traced")`, or the walk's own reason.

- [ ] **Step 1: Write the failing tests:**
  - `test_join_url_follows_ktors_rule`: one assertion per CP-54 row (g) case, including `join_url("https://api.openai.com/v1/", "/chat", …) == "https://api.openai.com/chat"`, and the base without a trailing `/` with `items` → the last segment replaced.
  - `test_a_top_level_client_base_joins_a_relative_call`: facts with a top-level `val client = HttpClient(CIO) { defaultRequest { url("https://pricing.example.com/") } }` and `client.get("quotes")` → peer `pricing.example.com`, path `/quotes`.
  - `test_a_derived_config_client_reads_its_own_base`.
  - `test_two_clients_join_their_own_bases`.
  - `test_an_unreachable_client_leaves_the_call_relative_with_a_reason`.
  - `test_an_absolute_call_ignores_the_base`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement, and wire `fluent` to take `base` from `client_base` when the catalog declares it.
- [ ] **Step 4:** Run the tests, the gate, and `scripts/field_check.py` (six `ok`). Expected: PASS.
- [ ] **Step 5: Guards:**
  - `ktor.a-RELATIVE-call-joins-its-clients-default-request-base`;
  - `ktor.the-join-follows-KTORS-rule-not-concatenation`;
  - `ktor.each-client-joins-its-OWN-base`.

  Measure each: killed.
- [ ] **Step 6:** Commit `feat(ktor): a relative client call joins its client's defaultRequest base, by Ktor's rule`.

### Task 6: WebSocket and SSE clients (`single_call`)

**Files:**
- Create: `src/sextant/catalogs/ktor-websocket-client.yml` (protocol `websocket`) and `src/sextant/catalogs/ktor-sse-client.yml` (protocol `sse`), both outbound.
- Modify: `src/sextant/application/resolve/engines/single_call.py` (read `client_base` when declared), `docs/components/D02-catalog-schema.md`
- Test: `tests/application/test_ktor_ws_sse_clients.py`

**Interfaces:**
- Consumes: `client_base` and `join_url` (Task 5). The client is argument 0 of each `BuildersKt` call.
- Produces:
  - WebSocket: outbound rows from the URL argument (CP-54 row (d) names and roles), joined to the base; the whole URL in `path`, `peer` NULL, verbless.
  - SSE: outbound rows, GET, in the existing SSE row shape.
  - The `host`/`port`/`path` overload gives its `path` joined to the base where readable, else `unresolved` with the reason (spec §3g item 4). No part assembly.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_ktor_websocket_client_url_is_an_outbound_row`: `webSocket$default(client, "ws://chat.example.com/chat", …)`.
  - `test_a_relative_ws_call_joins_the_base`: `client.ws("/opentelemetry/websocket")` under a base.
  - `test_a_ktor_sse_client_is_an_outbound_sse_row`: `"sse-Mswn-_c$default"(client, "https://events.example.com/stream", …)`.
  - `test_the_host_port_path_form_is_not_assembled`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the `single_call` wiring and write the two catalogs, with CP-54 in `measured:`.
- [ ] **Step 4:** Run the tests and the gate. Expected: PASS.
- [ ] **Step 5: Guards:**
  - `ktor.a-WEBSOCKET-client-call-is-an-outbound-row`;
  - `ktor.an-SSE-client-call-is-an-outbound-row`;
  - `ktor.a-relative-WS-call-joins-the-base`.

  Measure each: killed.
- [ ] **Step 6:** Commit `feat(ktor): WebSocket and SSE client calls are outbound rows`.

### Task 7: Fixture, real-corpus measurement, and the record

**Files:**
- Modify: `fixtures/orders-ktor/pom.xml` (Ktor 3.6.0, Kotlin 2.4.20, plus `ktor-server-websockets-jvm`, `ktor-server-sse-jvm`, `ktor-client-core-jvm`, `ktor-client-cio-jvm`) and its sources (spec §3f):
  - a WebSocket route and an SSE route under `route("/api")`;
  - `method(HttpMethod.Get) { get("/legacy") {} }`;
  - a top-level `HttpClient` with `defaultRequest { url("https://pricing.example.com/") }` and one call in each of the five client forms, one relative (`client.get("quotes")`);
  - `client.webSocket("ws://chat.example.com/chat")`;
  - `client.sse("https://events.example.com/stream")`.
- Modify: `tests/e2e/` (the Ktor delivered pins; find with `grep -rln orders-ktor tests/e2e`), `docs/COVERAGE.md` (the Ktor rows in §5.2, §5.5 and §5.6 → ✅ shipped, citing the spec, CP-54 and the pins; regenerate with `scripts/coverage_matrix.py`), `CHANGELOG.md`, the spec's Status → BUILT and its "As built".

- [ ] **Step 1: Write the failing e2e pins:**
  - inbound `websocket` `/api/chat` (verbless);
  - inbound `sse` GET `/api/events`;
  - GET `/legacy`;
  - five outbound HTTP rows, the relative one at peer `pricing.example.com`, path `/quotes`;
  - outbound `websocket` `ws://chat.example.com/chat`;
  - outbound `sse` `https://events.example.com/stream`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Write the fixture and rebuild it with `JAVA_HOME=/opt/homebrew/opt/openjdk@21`. Re-pin every count the version bump moves; `orders-ktor-classlambdas` stays on 3.0.3. Expected: PASS.
- [ ] **Step 4: Re-measure the built corpora** under `examples/`. They were built with their own Gradle wrappers, as the user allowed; do not rebuild unless a class directory is missing. Record each in the spec's "As built":
  - `ktor-samples/client-tools`: its client rows;
  - `kotlin-ktor-exposed-starter`: its WebSocket server at its nested path;
  - `ktor-samples/youkube`, built if its wrapper builds it, for `method(HttpMethod.Get)`.

  Any difference from the spec is a finding: fix a Critical or Major, log a Minor in Plane.
- [ ] **Step 5:** Run the full gate, `scripts/field_check.py` (six `ok`), and the full guard sweep (`0 survived`).
- [ ] **Step 6: Record:**
  - COVERAGE, and regenerate §2c. Quote the regenerated Ktor line in the report: ✅ on REST in, REST out, WebSocket and SSE.
  - CHANGELOG.
  - A Plane item for manual SSE (spec §4): OI-213, its row added to the id map.
- [ ] **Step 7:** Commit `feat(ktor): HTTP client, WebSockets and SSE delivered (orders-ktor at Ktor 3.6.0)`.

---

## Amendment 2026-10-26: reaching the client (user ruling "build both now")

Task 5 found that the value walk cannot reach a Ktor client (`.superpowers` report, summarised here):

- **Gap 1, no fact:** nothing records a field or a static field written from a call's RESULT. Examples:
  - `val client = HttpClient { … }` at top level is `invokestatic …; putstatic` in `<clinit>`.
  - `private val c = HttpClient { … }` is `aload_0; invoke…; putfield`.

  These are CP-33 rows 6 and 7, open in D00 §5. `MethodFlow.fieldWrites` skips static methods and records only `aload_0; xLOAD|LDC; putfield`.
- **Gap 2, no producer:** the walk answers values, never the call that built a value. So no construction can be found to read `defaultRequest` from.

**Order of work:** Tasks 1–4, then the unblocked slice of Task 5 (`join_url`, the `client_base` key, the derived-client probe rows), then **Task 8**, **Task 9**, **Task 10**, then Tasks 6 and 7. Task 10 is the rest of Task 5. Task 6 consumes Task 10's reader.

### Task 8: A field or static field written from a call's result is a fact

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java` (and its tests), `docs/components/D00-fact-schema.md` §5 (the `field_write` entry and the CP-33 rows 6–7 text), `docs/superpowers/specs/2026-10-18-the-sixth-edge-design.md` §5 (mark rows 6–7 built), and the walk's binding crossing in `src/sextant/application/resolve/values.py` (`_binding`, around line 1860), so that a write whose value is a call result is followed in the writing method's frame.
- Test: the extractor's Java tests beside MethodFlow, plus `tests/application/test_values*.py` (find with `grep -rln no_writer tests`).

**Interfaces:**
- Produces two new kinds of `field_write` fact:
  - a write whose value is a call's result: `invoke…` followed by `putfield` on `this`, or by `putstatic` in any method, `<clinit>` included;
  - a `putstatic` of a constant or parameter.
- The value is an §5 argument-grammar entry carrying a `source` site in the WRITER's frame, in the same shape a call argument that is a call result already has. Both keys stay OPTIONAL, so old facts read as before. Only if the fact's shape changes in a way old readers can't skip does the schema version move with D00.
- The walk's `_binding` crosses into the writer and resolves that value there. For a `field`-kind read of `Owner#name.`, a static field matches its `putstatic` writer, and no receiver check applies.
- The three things D00 says the fact deliberately does not report keep their reasons, except that `PUTSTATIC` is now reported. A write overwritten later in the same basic block, and `other.f = …`, stay excluded.

- [ ] **Step 1: Write the failing tests.**
  - Extractor: a class whose constructor does `this.c = Factory.make()`, and a Kotlin-style `<clinit>` doing `putstatic FileKt.client` from an `invokestatic`. Both emit `field_write` with a value whose `source` is the factory call.
  - A `putstatic` of a literal emits a constant value.
  - A write followed in the same block by another write to the same field emits only the later one.
  - Walk: `test_a_static_field_written_from_a_call_is_followed_to_that_call`. A read of `probe/ProbeKt#client.` resolves past `no_writer`, and with the factory unscanned answers `external`. That is the honest answer for a value; Task 9 reads the producer.
  - Walk: `test_a_property_written_from_a_call_in_the_constructor_is_followed`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement in the extractor and the walk. Rebuild the extractor the way `scripts/check.sh` and CI do.
- [ ] **Step 4: Measure before and after,** in the D00 history paragraph's style:
  - the number of `field_write` facts on the field pins (`scripts/field_check.py`'s corpora) and on the CP-54 probe module;
  - the reads and rows per resolve (GUIDELINES §8.7).

  `field_check.py` must stay six `ok`. A pin that moves is investigated. If more is read and the reads are correct, re-pin it with the reason; if it is a regression, fix it.
- [ ] **Step 5:** Run the gate. Expected: PASS.
- [ ] **Step 6: Guards:**
  - `values.a-field-written-from-a-CALL-is-followed`;
  - `extractor.a-PUTSTATIC-is-a-field-write`, if the guard harness reaches Java; otherwise pin it with a Java test and say so.

  Measure each: killed.
- [ ] **Step 7:** Commit `feat(values): a field or static field written from a call's result is followed (CP-33 rows 6–7)`.

### Task 9: The walk answers the call that produced a value

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (a new public reader beside `resolve_site`), and `docs/superpowers/specs/2026-09-22-value-resolution-design.md` (an "As built" note for the reader).
- Test: `tests/application/test_values*.py`.

**Interfaces:**
- Produces `producers_of(index: ValueIndex, site: <the same site type resolve_site takes>, slot: <same>, declared: <a set of (owner, method) identities>) -> tuple[Producer, ...]`.
  - `Producer` is a small frozen record: the producing call site's id and caller, and the identity it matched. The record is `None` when a path ends elsewhere, and then carries the walk's own reason (`external`, `no_writer`, …).
  - It walks backwards with the SAME crossings `resolve_site` uses: locals, parameters (`bound_to_parameter`), returns, and bindings (Task 8). It stops at a call whose identity is in `declared`.
  - There is no second distance rule and no per-catalog follow (spec 2026-09-22 §0a).
- A lambda stays "not a value" (ruled 2026-09-22). This reader returns the CALL, and the caller reads that call's block argument itself.

- [ ] **Step 1: Write the failing tests:**
  - a value built by a declared factory in the same method returns that call;
  - one passed as a parameter from such a method returns the caller's call;
  - one read from a static field written in `<clinit>` (Task 8) returns the `<clinit>` call;
  - a value from an undeclared call gives no producer, with reason `external`;
  - a value with two writers gives two producers, one per path.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement by sharing the walk's crossing code. Do not copy it.
- [ ] **Step 4:** Run the tests and the gate. Also run the shadow and measurement gate that walk changes go through (`tests/application/test_shadow_mode.py` and its inventory). Expected: PASS.
- [ ] **Step 5: Guard** `values.the-PRODUCER-reader-stops-at-a-declared-call`. Measure: killed.
- [ ] **Step 6:** Commit `feat(values): the walk answers the call that produced a value`.

### Task 10: The client's base read through the declared ladder (the rest of Task 5)

**Files:** those in Task 5, using Task 9's `producers_of` to find each client's construction.

**Interfaces:**
- Consumes `client_base`, `join_url` and the ladder declared in the Task 5 slice, and `producers_of` from Task 9.
- `client_base(...)` is Task 5's signature. It asks `producers_of` for the client value's producers, with the ladder's first rung as `declared`. It then reads into the declared block argument for the next rung, as `fluent`'s lambda joins already do, and ends at the setter's string.

Then follow:
- the derived `config { }` rung, as CP-54's derived-client rows measure;
- the no-base case: http://localhost per the ledger ruling;
- the unreached case: relative, `unresolved`, with the reason.

- [ ] **Steps:** Task 5's Steps 1–6, unchanged. Add the real-bytecode check: on the CP-54 probe, `client.get("relative/path")` gives peer `api.example.com`, path `/relative/path`, and `derivedClient` follows the measured inheritance.
