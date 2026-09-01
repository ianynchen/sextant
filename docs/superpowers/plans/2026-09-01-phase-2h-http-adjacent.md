# Phase 2H — HTTP-Adjacent Protocols Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GraphQL operations, WebSocket/STOMP destinations, and SSE streams become endpoints with true wire identities — via three annotation catalogs, an SDL reader feeding the one interpreter, the `schema_operations` style, and the `protocol_hint` reclassification pass — with `format_fixed` going live.

**Architecture:** Everything rides existing machinery except the two sanctioned mechanisms: `schema_operations` (a derive-time style reading the graphql declared-shape universe, first-writer via the existing insert-if-absent guard + one coalesce stamp) and `protocol_hint` (a post-merge resolve pass ordered before `resolve_format`, changing protocol only, scoped to http rows). `graphql-core` joins the one-interpreter confinement.

**Tech Stack:** Python (duckdb, pydantic, protobuf, grpcio-tools, **new: graphql-core**), YAML catalogs, DuckDB SQL, Maven fixture (**new compile-scope jars: spring-boot-starter-graphql, DGS annotations, microprofile-graphql-api, jakarta.websocket-api**). **No extractor changes** (spec §8 — a checkpoint-found gap routes through a plan amendment, never silent extractor work).

**Spec:** docs/superpowers/specs/2026-09-01-phase-2h-http-adjacent-design.md

## Global Constraints

- **No version bumps** (SEXTANT_VERSION/FACT_SCHEMA_VERSION/GRAPH_SCHEMA_VERSION frozen; no extractor version change this phase).
- **Determinism (NFR-1)**: double-run byte-identity over every touched table/export.
- **Unresolved is an answer, never an omission**; assumed never looks observed; nothing guessed — specifically **no Java-class↔SDL-type name join, ever** (spec §4).
- **Framework names in catalogs only**; `graphql-core` imports only in `ingress/interpret/descriptors.py` (confinement test extended with a positive control).
- **protocol_hint changes `protocol`, never `direction`, never creates an endpoint; http rows only** (D02 contract, spec §6).
- **Wire identities** (spec §§1,3,5): root GraphQL `(graphql, query|mutation|subscription, <field>)`; nested `(graphql, NULL, Type.field)`; WebSocket/STOMP `(websocket, NULL, <path-or-destination>)`; SSE = reclassified http rows keeping their path.
- **Exact-list pins from live fixture runs only**; suite baseline 683 passed/1 skipped.
- Ingress write-only; layering contracts KEPT; hooks pass; uv.lock untracked; comments state constraints; no adjacent refactors; match existing patterns (§13.5).

## File Structure

| File | Responsibility |
|---|---|
| `fixtures/orders-service/pom.xml` + new fixture classes + `src/main/resources/graphql/*.graphqls` | 2H surfaces |
| `src/sextant/domain/closed_sets.py` | protocol members `graphql`, `websocket`, `sse` |
| `src/sextant/catalogs/{spring-graphql,netflix-dgs,microprofile-graphql}.yml` | GraphQL annotation catalogs + `format_fixed: json` + `schema_operations` block (spring-graphql) |
| `src/sextant/catalogs/{jakarta-websocket,spring-stomp}.yml` | WebSocket/STOMP catalogs (+ registerWebSocketHandlers single_call entry in spring-stomp) |
| `src/sextant/ingress/read/graphql_sdl.py` | SDL reader (verbatim, never parses) |
| `src/sextant/ingress/interpret/descriptors.py` | graphql branch (graphql-core; module-wide multi-file merge) |
| `src/sextant/ingress/detect/maven.py` | schema root `src/main/resources/graphql` |
| `src/sextant/application/resolve/engines/schema_operations.py` + registry wiring | mechanism 1: SDL roots → endpoint rows |
| `src/sextant/application/resolve/protocol_hint.py` + `resolve/pipeline.py` | mechanism 2: reclassification pass (engines → parse_binding → protocol_hint → resolve_format) |
| `src/sextant/storage/duckdb/` (stamp/insert SQL as needed) | schema_operations insert + declared-response coalesce stamp |
| docs (D00/D01/D02/D06/COVERAGE/README/roadmap) | Task 7 |

### Task order and why

Fixtures first (bytecode must exist to probe); Task 2 doubles as the **checkpoint** (annotation-default reality frozen before catalogs are written against guesses); SDL machinery before `schema_operations` (its input); WebSocket/STOMP independent; `protocol_hint` after everything it reclassifies exists; docs last.

---

### Task 1: Fixture surfaces and dependencies

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/example/orders/graphql/OrderGraphqlController.java`, `graphql/DgsOrderFetcher.java`, `graphql/MpOrderApi.java`, `ws/LiveEndpoint.java`, `ws/OrderStompController.java`, `sse/OrderEventsController.java`, `src/main/resources/graphql/schema.graphqls`, `src/main/resources/graphql/audit.graphqls`

**Interfaces:**
- Produces: every 2H surface later tasks pin. Exact classes below — copy verbatim.

- [ ] **Step 1: pom.xml** — add compile-scope, version-pinned: `org.springframework.boot:spring-boot-starter-graphql`, `com.netflix.graphql.dgs:graphql-dgs` (annotations only needed — if the full artifact drags a dependency tree that breaks the offline build, use the smallest DGS artifact carrying `com.netflix.graphql.dgs.@DgsComponent/@DgsQuery/@DgsData`), `org.eclipse.microprofile.graphql:microprofile-graphql-api`, `jakarta.websocket:jakarta.websocket-api`. Verify each resolves before pinning.
- [ ] **Step 2: GraphQL controller** (`OrderGraphqlController.java`):

```java
package com.example.orders.graphql;

import com.example.orders.model.OrderView;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

@Controller
public class OrderGraphqlController {

    @QueryMapping("orderById")            // explicit field name
    public OrderView byId(String id) { return null; }

    @QueryMapping                          // method-name fallback → field "orders"
    public List<OrderView> orders() { return List.of(); }

    @MutationMapping
    public OrderView placeOrder(String sku) { return null; }

    @SubscriptionMapping
    public Flux<OrderView> orderUpdates() { return Flux.empty(); }

    @SchemaMapping(typeName = "Order", field = "lines")
    public List<String> orderLines(OrderView order) { return List.of(); }

    @BatchMapping(typeName = "Order")      // field falls back to method name "totals"
    public Map<OrderView, Long> totals(List<OrderView> orders) { return Map.of(); }
}
```

- [ ] **Step 3: DGS + MicroProfile classes** (one query each — the zero-engine-change pins):

```java
// DgsOrderFetcher.java
package com.example.orders.graphql;
import com.example.orders.model.OrderView;
import com.netflix.graphql.dgs.DgsComponent;
import com.netflix.graphql.dgs.DgsQuery;

@DgsComponent
public class DgsOrderFetcher {
    @DgsQuery(field = "dgsOrders")
    public java.util.List<OrderView> dgsOrders() { return java.util.List.of(); }
}
```

```java
// MpOrderApi.java
package com.example.orders.graphql;
import com.example.orders.model.OrderView;
import org.eclipse.microprofile.graphql.GraphQLApi;
import org.eclipse.microprofile.graphql.Query;

@GraphQLApi
public class MpOrderApi {
    @Query("mpOrders")
    public java.util.List<OrderView> mpOrders() { return java.util.List.of(); }
}
```

- [ ] **Step 4: SDL files.** `schema.graphqls` — root types listing every annotated operation above (`orderById`, `orders`, `placeOrder`, `orderUpdates`, `dgsOrders`, `mpOrders`) **plus one schema-first-only operation no annotation implements** (`auditTrail(id: ID!): [AuditEntry!]` — the RuntimeWiring pin), the `Order` type with `lines: [String!]` and `totals: Long`, an enum, an input type, an interface, and `!`/list variety. `audit.graphqls` — the `AuditEntry` type (multi-file merge pin: `auditTrail` in file 1 returns a type declared in file 2):

```graphql
# schema.graphqls
type Query {
  orderById(id: ID!): Order
  orders: [Order!]!
  dgsOrders: [Order!]!
  mpOrders: [Order!]!
  auditTrail(id: ID!): [AuditEntry!]
}
type Mutation { placeOrder(sku: String!): Order }
type Subscription { orderUpdates: Order }

type Order implements Node {
  id: ID!
  lines: [String!]
  totals: Long
  status: OrderStatus!
}
interface Node { id: ID! }
enum OrderStatus { OPEN CLOSED }
input OrderFilter { sku: String, open: Boolean! }
scalar Long
```

```graphql
# audit.graphqls
type AuditEntry { at: String!, actor: String }
```

- [ ] **Step 5: WebSocket/STOMP/SSE classes**:

```java
// LiveEndpoint.java
package com.example.orders.ws;
import jakarta.websocket.OnMessage;
import jakarta.websocket.server.ServerEndpoint;

@ServerEndpoint("/live")
public class LiveEndpoint {
    @OnMessage
    public void onFrame(String frame) { }
}
```

```java
// OrderStompController.java
package com.example.orders.ws;
import com.example.orders.model.OrderView;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SubscribeMapping;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/orders")
public class OrderStompController {

    @MessageMapping("/place")             // composes to /orders/place
    @SendTo("/topic/order-placed")
    public OrderView place(OrderView order) { return order; }

    @SubscribeMapping("/board")           // composes to /orders/board
    public OrderView board() { return null; }
}
```

```java
// OrderEventsController.java
package com.example.orders.sse;
import com.example.orders.model.OrderView;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.publisher.Flux;

@RestController
public class OrderEventsController {

    @GetMapping("/events/emitter")        // NO produces — return-type rung pin
    public SseEmitter emitterEvents() { return new SseEmitter(); }

    @GetMapping(value = "/events/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<OrderView>> streamEvents() { return Flux.empty(); }
}
```

- [ ] **Step 6: build + suite.** Fixture builds with the suite's own invocation; full Python suite runs. Expect ONLY mechanical pin churn (scanner fact-file lists, document counts — new classes/resources appear). Update exhaustive pins from live output (the Task-1-of-2G precedent, ruled there). Any endpoint/shape pin movement beyond counts = STOP and report (nothing here is catalogued yet, so no endpoint may appear).
- [ ] **Step 7: Commit** `feat(fixtures): GraphQL, WebSocket, STOMP and SSE surfaces`.

### Task 2: CHECKPOINT + the three GraphQL annotation catalogs

**Files:**
- Modify: `src/sextant/domain/closed_sets.py` (protocol members), whatever validates protocols in `src/sextant/application/ports/catalogs.py`
- Create: `src/sextant/catalogs/spring-graphql.yml`, `src/sextant/catalogs/netflix-dgs.yml`, `src/sextant/catalogs/microprofile-graphql.yml`
- Test: live pins in the pipeline/endpoint test files (follow where 2G's live pins live)

**Interfaces:**
- Consumes: fixture bytecode (Task 1); existing `annotation_driven` engine — **UNCHANGED: any needed engine edit is a BLOCKED-report, not a change** (spec §1's acceptance test).
- Produces: `graphql` rows the later tasks read; protocol closed set carries `graphql`, `websocket`, `sse`.

**CHECKPOINT (before writing any catalog): probe the fixture bytecode and write answers to the SDD workspace** (`checkpoint-task-2.md`): (1) how a DEFAULTED annotation value reads (absent `value` on `@QueryMapping orders()` — confirm the existing default-to-method-name vocabulary path fires); (2) DGS attribute names as compiled (`field`? `value`? both `@DgsQuery` and `@DgsData(parentType=...)`); (3) MicroProfile `@Query("mpOrders")` attribute; (4) `@BatchMapping(typeName=...)` attributes and its `Map<K,V>` signature shape; (5) class-level `@ServerEndpoint`/`@OnMessage` and class-level `@MessageMapping` prefix reality (Task 5 dispatches off 5's answers); (6) what `Signature.returns` carries for `Flux<ServerSentEvent<OrderView>>` and `SseEmitter` (Task 6 dispatches off this). Adjust catalog vocabulary to the probed reality, never to guesses.

- [ ] **Step 1: closed set** — `graphql`, `websocket`, `sse` join the protocol members; catalog validation accepts them; a failing-then-passing unit test on the validator.
- [ ] **Step 2: spring-graphql.yml** — `annotation_driven`, `protocol: graphql`, rules per spec §1: `@QueryMapping`→`method: query`, `@MutationMapping`→`mutation`, `@SubscriptionMapping`→`subscription`, field from annotation value with method-name fallback (existing vocabulary); `@SchemaMapping`/`@BatchMapping` → method NULL, path `{typeName}.{field-or-method-name}` (check how existing catalogs compose path fragments; if no `{a}.{b}` composition vocabulary exists, this is the task's one hard part — model it on the 2E prefix-composition vocabulary and document the addition as catalog vocabulary, not engine code; if it cannot be expressed without engine changes, STOP and report BLOCKED per the acceptance test). Include `format_fixed: json` (rung 1 — Task 6 wires the ladder to read it; declaring it now is harmless data).
- [ ] **Step 3: netflix-dgs.yml + microprofile-graphql.yml** — same projections per spec §1, `format_fixed: json` on both.
- [ ] **Step 4: live pins.** Run the pipeline; pin the new graphql rows exactly: `(graphql, query, orderById)`, `(graphql, query, orders)`, `(graphql, mutation, placeOrder)`, `(graphql, subscription, orderUpdates)`, `(graphql, NULL, Order.lines)`, `(graphql, NULL, Order.totals)`, `(graphql, query, dgsOrders)`, `(graphql, query, mpOrders)` — handlers, evidence, catalog_id from live output. Assert the DGS and MicroProfile rows derive **with zero engine diffs** (the acceptance-test pin: `git diff --stat` of engine files is empty for this task).
- [ ] **Step 5: full suite + hooks; commit** `feat: GraphQL inbound — three catalogs, zero engine changes`.

### Task 3: SDL reader and the interpreter's graphql branch

**Files:**
- Modify: `pyproject.toml` (graphql-core, pinned), `src/sextant/ingress/interpret/descriptors.py`, `src/sextant/ingress/detect/maven.py` (+ its port if schema-root plumbing needs the entry), `tests/architecture/test_protobuf_confinement.py` (allowlist + positive control)
- Create: `src/sextant/ingress/read/graphql_sdl.py`
- Test: `tests/ingress/read/test_graphql_sdl.py`, `tests/ingress/interpret/test_graphql_descriptors.py`

**Interfaces:**
- Consumes: `ArtifactReader` protocol; `EmbeddedDescriptorFact` (`schema_format` gains `"graphql"` — widen the Literal in `domain/facts.py`); `interpret_descriptors(descriptors, naming)`.
- Produces: graphql `declared_shape` facts (`schema_name` = SDL type name, symbol = type name, origin `source`, evidence `declared`, `field_number` NULL) that Task 4 reads; reader registered in analyze beside avsc/proto; detector contributes `src/main/resources/graphql`.

- [ ] **Step 1: failing reader tests** — one `EmbeddedDescriptorFact(schema_format="graphql", origin="source")` per `.graphqls`/`.graphql` file, payload verbatim; claims those extensions only (coexistence with config/proto readers asserted); no parsing (assert `graphql` never imported by the reader — extend the confinement test's allowlist map instead of a new test file, plus the positive control).
- [ ] **Step 2: failing interpreter tests** (in-test SDL strings mirroring Task 1's fixture files):

```python
def test_object_type_projects_fields():        # Order: id required+non-null, lines array w/ non-null items, status enum ref
def test_bang_and_list_semantics():            # T! → required/not nullable; T → nullable; [T!] vs [T]! distinguished on item vs field
def test_multi_file_merge():                   # auditTrail's [AuditEntry!] in file 1 resolves shape_ref to file 2's type
def test_interface_and_input_and_enum():       # Node, OrderFilter, OrderStatus each a shape; enum carries symbols
def test_malformed_document_is_gap():          # syntax error → that file's symbol in failed list, others interpret; partial discard per the 2G Avro rule
def test_unknown_reference_is_gap():           # field typed as an undeclared name → that file fails, not a crash
def test_output_deterministic():               # forwards/reversed input identical
```

- [ ] **Step 3: implement** — `uv add graphql-core` (pin; do not commit uv.lock); `descriptors.py` gains `_graphql_shapes`: collect ALL graphql payloads module-wide, concatenate into one document set, `graphql.parse` each then build one type map (merge across files; a duplicate type name across files fails those files into the gap list — Spring itself would reject it), project per spec §2's table. Failure boundary identical to the Avro fix (wrap the walk; `GraphQLSyntaxError` + KeyError/TypeError → failed list). The naming hook is NOT called for graphql (source-origin only — symbol is the schema name; state that in one comment).
- [ ] **Step 4: detector + analyze wiring** — `src/main/resources/graphql` joins schema roots when present (beside proto/avro; languages untouched); reader registered in cli's registry. Wiring test: a fake module with the two SDL files yields the declared shapes through the analyze stage.
- [ ] **Step 5: full suite (fixture pins churn: new declared shapes appear — update from live); hooks; commit** `feat: SDL reader and the interpreter's graphql branch`.

### Task 4: `schema_operations` — SDL roots become endpoints

**Files:**
- Create: `src/sextant/application/resolve/engines/schema_operations.py`, `src/sextant/storage/duckdb/insert_schema_operations.sql` (or the stamp/insert pair — follow the config_join derives-rows file conventions)
- Modify: `src/sextant/application/resolve/engines/endpoints.py` (registry: the style runs AFTER annotation catalogs, with the `_DERIVES_ROWS`-before-merge ordering — read how config_join's derives-rows engines slot in), `src/sextant/catalogs/spring-graphql.yml` (the `schema_operations` block: root-type defaults `{query: Query, mutation: Mutation, subscription: Subscription}` + `schema`-block rename handling)
- Test: `tests/application/test_schema_operations.py` + live pins

**Interfaces:**
- Consumes: graphql `declared_shape` facts (Task 3), the `declared_shapes` workspace query (extend its columns if needed — Task 5-of-2G trimmed to symbol/evidence/fields; this task may re-add `schema_name`/`schema_format` WITH a consumer, which is the rule the trim enforced).
- Produces: `(graphql, <kind>, <field>)` rows at evidence `declared`, handler NULL, direction inbound; declared response shape carried; the two-part agreement mechanics later phases rely on.

- [ ] **Step 1: failing unit tests** (synthetic declared-shape universe):

```python
def test_root_fields_become_operations():      # Query.orders → (graphql, query, orders), declared, handler NULL
def test_schema_block_rename_honored():        # schema { query: MyQ } → MyQ's fields are the query ops
def test_non_root_types_derive_nothing():      # Order's fields never become operations from this style
def test_agreement_annotation_wins_identity(): # pre-existing (graphql, query, orders) row w/ handler → SDL row NOT inserted (insert-if-absent guard)
def test_agreement_coalesces_response_shape(): # matching row w/ NULL response_shape gains the declared field type; non-NULL never overwritten
def test_sdl_only_operation_inserts():         # auditTrail-style op absent from endpoints → inserted
def test_deterministic():                      # double-run identity
```

- [ ] **Step 2: implement** — the engine reads the catalog block + the graphql declared shapes, derives candidate rows, inserts through the existing insert-if-absent guard (first-writer: annotation rows already present block the SDL twin), then one coalesce stamp (`response_shape = coalesce(existing, declared)` on matching wire identities — the merge-carry comment discipline: state exactly what the SQL delivers). Response shape references the SDL type's shape identity (within the declared universe — **no class join**, spec §4).
- [ ] **Step 3: live pins** — `(graphql, query, auditTrail)` appears at `declared` with NULL handler (the RuntimeWiring pin); the six annotation ops are NOT duplicated (count pinned); `orders`' response shape stays its Java type (annotation won); double-run byte-identity.
- [ ] **Step 4: full suite; hooks; commit** `feat: schema_operations — SDL roots become endpoints`.

### Task 5: WebSocket and STOMP catalogs

**Files:**
- Create: `src/sextant/catalogs/jakarta-websocket.yml`, `src/sextant/catalogs/spring-stomp.yml`
- Test: live pins

**Interfaces:**
- Consumes: checkpoint answers 5 (class-level annotation shapes); existing engines only — the acceptance-test rule from Task 2 applies (a needed engine change = BLOCKED report).
- Produces: `(websocket, NULL, ...)` rows Task 6's scoping test reads.

- [ ] **Step 1: jakarta-websocket.yml** — class-level `@ServerEndpoint` (BOTH `jakarta.websocket.server` and `javax.websocket.server` rows), path from the annotation value, handler = the `@OnMessage` method (the 2E class-annotation + method-role machinery — checkpoint 5 confirms the vocabulary); shapes/format stay NULL/unresolved (frames untyped — assert it).
- [ ] **Step 2: spring-stomp.yml** — `@MessageMapping`/`@SubscribeMapping` methods with class-level `@MessageMapping` prefix composition (the `@RequestMapping` path vocabulary); `@SendTo`/`@SendToUser` → outbound rows (2D's reply vocabulary, new protocol); plus the `single_call` entry for `WebSocketHandlerRegistry.addHandler(handler, path)` (literal path; non-literal → unresolved).
- [ ] **Step 3: live pins** — `(websocket, NULL, /live)` handler `onFrame`; `(websocket, NULL, /orders/place)` + its outbound `(websocket, NULL, /topic/order-placed)`; `(websocket, NULL, /orders/board)`; STOMP payload shapes present (OrderView), `/live` shapes NULL; STOMP rows read `json (assumed)` after Task 6 (pin here as whatever the ladder currently answers, re-pin in Task 6 if it moves).
- [ ] **Step 4: full suite; hooks; commit** `feat: WebSocket and STOMP inbound — two catalogs`.

### Task 6: `protocol_hint` pass and `format_fixed` live

**Files:**
- Create: `src/sextant/application/resolve/protocol_hint.py`, `src/sextant/storage/duckdb/reclassify_protocol.sql`
- Modify: `src/sextant/application/resolve/pipeline.py` (order: engines → parse_binding → **protocol_hint** → resolve_format), `src/sextant/application/resolve/format.py` (rung 1 reads `format_fixed` — the mechanism shipped in 2G unexercised; verify it fires rather than reimplementing), `src/sextant/catalogs/spring-mvc.yml` + `spring-web.yml` (the `protocol_hint` vocabulary: `hint_media: [text/event-stream]`, `hint_returns` — exact type names per checkpoint answer 6, e.g. `org.springframework.web.servlet.mvc.method.annotation.SseEmitter`, and the ServerSentEvent-inside-generic reading)
- Test: `tests/application/test_protocol_hint.py` + live pins

**Interfaces:**
- Consumes: endpoints rows (post-merge), `Signature.returns` TypeRef in `handler_signature`, checkpoint answer 6's generic reality.
- Produces: `sse` rows; the final pipeline ordering; rung 1 live.

- [ ] **Step 1: failing unit tests**:

```python
def test_produces_event_stream_reclassifies():   # http row w/ produces text/event-stream → sse, same path/direction
def test_return_type_reclassifies():             # SseEmitter return, no produces → sse
def test_scoped_to_http():                       # graphql/websocket/kafka rows never touched even w/ matching signature
def test_direction_never_changes():              # a both row reclassifies wholesale, direction intact
def test_no_row_created():                       # row count identical before/after
def test_format_fixed_rung_fires():              # graphql row → (json, resolved) via rung 1 (first live surface)
def test_sse_format_honest():                    # sse row w/ Jackson marker → (json, narrowed); event-stream MIME maps to NO format
def test_deterministic():
```

- [ ] **Step 2: implement** — the pass reads catalog `protocol_hint` blocks (media first, then `hint_returns` against `Signature.returns` incl. the generic-wrapper chain as catalog data), one UPDATE scoped `protocol = 'http'`; pipeline ordering per spec §6; confirm `media_formats` does NOT map `text/event-stream` (add the explicit no-mapping comment); verify rung 1 fires from the 2G mechanism (if 2G's `format_fixed` reading has a latent bug — it shipped unexercised — fix it HERE with a pinned regression test and say so in the report).
- [ ] **Step 3: live pins** — `/events/emitter` and `/events/stream` read `protocol: sse` (one via each evidence kind — pin which); `/events/stream`'s payload shape is OrderView (PTR unwrap); every graphql row reads `(json, resolved)`; STOMP rows re-pinned if moved; the full-ladder live pin (the 2G `test_the_format_ladder_answers_every_live_row` style) re-pinned from live output; double-run byte-identity incl. open_questions.
- [ ] **Step 4: full suite; hooks; commit** `feat: protocol_hint — SSE reclassification, format_fixed live`.

### Task 7: Docs, COVERAGE, README, roadmap

**Files:**
- Modify: `docs/components/D00-fact-schema.md` (three protocol members), `D01-graph-schema.md` (operation identity forms; verbless rendering already documented for messaging — extend the identity list), `D02-catalog-schema.md` (protocol_hint reserved→real + execution amendment superseding "runs last with config_join"; `schema_operations` style section; `hint_returns`/`hint_media` + `format_fixed`-live vocabulary; the three-GraphQL-catalog zero-engine-change note), `D06-*.md` (rendered identities `graphql query orders` / `websocket /orders/place` / `sse /events/stream`), `docs/COVERAGE.md`, `README.md` (graphql-core), `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md` (2H row → delivered; headline count re-derived from actual flips)
- Test: suite stays green (docs only)

- [ ] **Step 1: COVERAGE flips** — §5.4 Spring GraphQL/DGS/MicroProfile/graphql-java-SDL rows, §5.5 @ServerEndpoint/STOMP/programmatic rows, §5.6 SseEmitter + Flux rows, §4.1 GraphQL + SSE regime rows. Boundaries, one sentence each, verified against code before writing: raw WebSocket frames untyped; negotiated subprotocols unread; body-string SSE unshipped (C-tier); DGS/MicroProfile client sides out; RuntimeWiring code unread (SDL is the source); **no Java-class↔SDL-type join** (both universes recorded; the reserved schema_name→symbol seam now has two customers); subscription transport not resolved; federation directives data-only; schema root is the one conventional dir.
- [ ] **Step 2: D02/D01/D06/D00/README per the file list**; every claim checked against shipped code (the 2G Task-9 discipline — a false doc sentence is a Critical).
- [ ] **Step 3: roadmap** — 2H delivered row; count re-derived by counting the actual §5 flips.
- [ ] **Step 4: full suite; hooks; commit** `docs: 2H — HTTP-adjacent protocols delivered`.

---

## Plan Self-Review (run before execution)

1. **Spec coverage**: §1→T2, §2→T3, §3→T4, §4→T4 (no-join rule enforced in engine + COVERAGE in T7), §5→T5, §6→T6, §7→T1 + per-task pins + checkpoint in T2, §8→T3 (graphql-core)/T1 (fixture jars), §9→T7, §10→T7 boundaries. Both mechanisms have their own tasks; format_fixed declared in T2, wired/verified in T6 (stated in both).
2. **Placeholder scan**: none found; every code step carries real code; the one deliberately open value (DGS artifact coordinates if the platform jar is too heavy) is an instruction with a decision rule, not a TBD.
3. **Type consistency**: `schema_format="graphql"` Literal widening named in T3 and consumed in T3/T4; `(graphql, query, orderById)`-style identities identical across T2/T4/T6/T7; `hint_returns`/`hint_media` named identically in T6's catalog and test steps; checkpoint file `checkpoint-task-2.md` referenced by T5 (answer 5) and T6 (answer 6).
4. **Known risk, stated**: T2's `{typeName}.{field}` path composition may lack existing catalog vocabulary — the task carries an explicit BLOCKED escape rather than a silent engine edit, preserving the acceptance test.
