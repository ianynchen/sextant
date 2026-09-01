# Phase 2H — HTTP-adjacent protocols: GraphQL, WebSocket/STOMP, SSE

**Status:** approved in brainstorm 2026-09-01; this document records the design.
**Depends on:** 2G (readers/interpreter/declared shapes, format ladder, resolve-pass
ordering), 2E (composed annotations, produces/consumes), 2D (@SendTo, verbless
identity), 2C (single_call).
**Roadmap row:** GraphQL (`@QueryMapping` et al.), WebSocket/STOMP (`@MessageMapping`),
SSE — operation-as-endpoint identity; `protocol_hint` engine.

## The thesis

These three protocols share one property: their boundary is not an HTTP route. A
GraphQL schema with 200 fields is 200 boundaries behind one POST path; a WebSocket
connection path fans into N destinations; an SSE endpoint is an HTTP route that a
*return type* quietly turned into a stream. 2H gives each its true wire identity and
ships the two mechanisms the roadmap reserved: **operation-as-endpoint identity**
(realized as the `schema_operations` style, §3) and the **`protocol_hint` engine**
(reclassification, §5). Everything else rides machinery that already exists.

User rulings that shaped scope: GraphQL takes **everything** — Spring GraphQL, Netflix
DGS, and MicroProfile GraphQL as catalogs now (a deliberate early run of 2J's
zero-engine-change acceptance test on one protocol; 2J keeps Micronaut/Quarkus REST as
its own proof) plus the `.graphqls` SDL reader; operation identity is
`(graphql, query|mutation|subscription, <field>)` for root operations and
`(graphql, NULL, Type.field)` for non-root resolvers; `graphql-core` (the Python
reference implementation) joins the core dependencies for SDL parsing — the 2G
"data we read, never an algorithm we implement" argument, approved per GUIDELINES §7.

Self-review corrections baked in: the SDL-to-endpoint derivation is named as its own
engine style rather than hidden in a reader section (§3), and the "response shapes
prefer the SDL type" idea is **withdrawn** as a guess — the honest rule is §4's.

## 1. GraphQL inbound — three catalogs, two vocabulary forms

Three new annotation catalogs on the `annotation_driven` engine. **Execution
amendment (checkpoint falsification, 2026-09-01):** the brainstorm assumed an existing
default-to-method-name vocabulary and an existing `{a}.{b}` path composition; the
checkpoint proved live that neither exists (all three frameworks declare their field
attribute `default ""`, which never materializes into bytecode, so an absent value
derived `path: ''` at `resolved`/`compiler` — four actively wrong rows; and a
method-level `typeName` can never reach the class-prefix CTE). The ruling: two
**framework-neutral vocabulary additions** to `annotation_driven` — (1) a declared
name that falls back to the annotated construct's own name when the attribute is
absent, and (2) a dotted composition of two attribute values where the second falls
back per (1) — the `channel_via`/`field_sources` precedent: vocabulary grows for a
genuinely new declaration pattern; framework names stay in catalogs. **The
zero-engine-change acceptance test moves to where it is meaningful: Netflix DGS and
MicroProfile GraphQL must ride the two new forms with zero further engine change.**

- **`spring-graphql.yml`**: `@QueryMapping` → `method: query`, `@MutationMapping` →
  `mutation`, `@SubscriptionMapping` → `subscription`; field name from the annotation
  value (`name`/`value`), falling back to the method name — Spring's own rule, and the
  fallback is statically resolvable (an absent annotation value reads as absent in
  bytecode; **execution amendment**: the vocabulary is the NEW `path_fallback:
  construct_name` the paragraph above rules in, not an existing one — the checkpoint
  proved none existed).
  `@SchemaMapping(typeName = "Order", field = "lines")` → `method` NULL, path
  `Order.lines` (field falls back to method name here too). Class-level
  `@SchemaMapping(typeName = ...)` composes with method-level annotations through the
  2E composed/effective-annotation machinery. `@BatchMapping` projects the same as
  `@SchemaMapping` (its Map/Flux return shape is a batching detail, noted for the
  shapes pass, not identity).
- **`netflix-dgs.yml`**: `@DgsComponent` class gate; `@DgsQuery`/`@DgsMutation`/
  `@DgsSubscription` shorthands and `@DgsData(parentType, field)` project identically
  (root parentTypes map to the method column, others go verbless).
- **`microprofile-graphql.yml`**: `@GraphQLApi` class gate; `@Query`/`@Mutation`
  methods (`org.eclipse.microprofile.graphql`).

All rows `protocol: graphql`; evidence per the existing annotation ladder;
`catalog_id` per catalog. Request shapes from handler parameters and response shapes
from return types via the existing shapes pass (subject to §4's rule).

**Closed set:** D00's protocol set gains `graphql`, `websocket`, `sse` — declared once,
all three used this phase.

## 2. The SDL reader and the interpreter's third format

The `.graphqls` file is 2H's descriptor. Same layering as 2G, nothing new invented:

- **Reader** (`ingress/read/graphql_sdl.py`): claims `graphqls`/`graphql` extensions
  through the existing ArtifactReader registry. Schema root: `src/main/resources/graphql`
  (the Spring GraphQL convention; the detector contributes it beside `proto`/`avro` —
  conventional-dirs-only, boundary stated). The reader emits the SDL **verbatim** as an
  `embedded_descriptor`-shaped fact (`schema_format: "graphql"`, `origin: "source"`);
  it never parses. **Multi-file schemas**: Spring merges every `.graphqls` under the
  root into one schema, so the reader emits one fact per file and the interpreter
  merges all of a module's graphql payloads into one type universe before projecting —
  the protobuf pool precedent (checkpoint item: verify against a two-file fixture
  schema, including a type extension split across files).
- **Interpreter**: `descriptors.py` grows a `graphql` branch — `graphql-core` joins
  `google.protobuf` in that one module's confinement allowlist (structural test
  extended with a positive control). Per object type, one `declared_shape`
  (`schema_name` = the type name, symbol = the type name — source-origin convention);
  per field: `wire_name` = the field name verbatim (GraphQL renames nothing),
  `!` → `required: true` / `nullable: false` (absent `!` → nullable), `[T]` → array
  with `item` (inner `!` on the item), object references → `shape_ref`, enums with
  their symbols, `field_number` NULL (the format has none — 2G's column contract
  allows it). Interfaces land as shapes carrying their own fields;
  input types project the same as object types. **Execution amendment (Task 3
  review): a UNION does not land as a shape.** A union is one of several types and
  this wire vocabulary has no word for that — it declares no field of its own, so a
  shape for it would be an empty payload nobody sends — so a file declaring one (or an
  `extend union`) becomes that file's gap, which is the sentence below applied rather
  than an exception to it. A construct the branch cannot project
  (a directive-bearing edge case, a malformed document) records
  `descriptors_not_interpreted` for that file and moves on — never a crash, and the
  failure boundary follows 2G's Avro fix (partial reads discarded, not half-published).
- Evidence: `declared` (source-origin — there is no compiled origin for SDL).

## 3. `schema_operations` — the operation-as-endpoint style (mechanism 1 of 2)

The interpreter emits facts, never endpoints; deriving operations from the SDL is its
own small catalog-declared style, stated here as a mechanism rather than hidden in §2
(self-review correction):

- **What it reads:** the module's graphql `declared_shape` universe. **What it derives:**
  one endpoint row per field on a root type — `Query` → `(graphql, query, <field>)`,
  `Mutation` → `mutation`, `Subscription` → `subscription` — honoring a `schema { query:
  MyQuery }` block's renames. Direction `inbound`, evidence `declared`,
  `handler` NULL (the SDL names no code), response shape = the field's declared type
  (an SDL shape reference, which resolves within the declared universe — no class join).
- **Why it exists:** schema-first services (`graphql-java` + `RuntimeWiring`) have no
  annotations at all; without this style they derive nothing. The wiring code itself
  (programmatic field registration) is explicitly not read — the SDL is the contract,
  and the boundary is stated in COVERAGE.
- **Agreement:** when an annotation row and an SDL row share a wire identity, the
  existing dedup folds them and the annotation row's answers survive where present
  (first-writer; the handler symbol only the annotation knows, the declared response
  shape only the SDL row carries — coalesce, the merge-carry precedent).
- **Vocabulary (execution amendment, Task 4):** the style ships as its own file,
  `graphql-schema.yml`, not as a block on `spring-graphql.yml` — one file is one
  catalog is one style (`spring-kafka-media.yml`'s precedent), and what this reads is a
  schema, which belongs to no framework: the same SDL serves the Spring, DGS and
  MicroProfile modules and a schema-first service with no annotation library at all.
  It declares `matches.schema_operations: {schema_format, operations}` and **no
  root-type table**: which type is the query root is a FACT
  (`DeclaredShapeFact.role`), because a `schema { query: MyQuery }` block renames it
  and nothing outside the interpreter may read a schema format. Catalog-declared,
  engine reads vocabulary only.

## 4. Shapes: the honest rule (no class↔type guessing)

Two shape universes now describe one service: Java classes (bytecode/annotation
expansion) and SDL types (declared). The rule, replacing the withdrawn
"SDL-preferred" idea:

- An **annotation-derived** operation keeps its Java-type shapes — in a code-first
  service that IS the wire (Jackson serializes the Java object).
- An **SDL-derived** operation carries its SDL-type shapes — schema-name references
  within the declared universe.
- Where both rows folded (§3), the surviving row keeps the handler's Java shapes and
  the declared response shape rides the coalesce where the Java side had none.
- **No simple-name join between a Java class and an SDL type is ever made** — that is
  a guess. Both universes are recorded; cross-linking them is comparison work with its
  own evidence (the reserved `schema_name`→symbol seam from 2G, now with a second
  customer), recorded as a COVERAGE boundary and left for the phase that earns it.

## 5. WebSocket and STOMP

`protocol: websocket`, verbless (`method` NULL — the 2D precedent):

- **Raw WebSocket**: `@ServerEndpoint("/ws")` on the class — `jakarta.websocket.server`
  AND `javax.websocket.server`, two catalog rows (the Jackson-2/3 precedent). One row
  per URI template, `(websocket, NULL, /ws)`; the `@OnMessage` method is the handler
  symbol (class-level annotation + method role — the 2E class-annotation machinery).
  Frames are untyped: shapes NULL, format `unresolved`, honestly.
- **STOMP**: `@MessageMapping("/order.place")` and `@SubscribeMapping` →
  `(websocket, NULL, <destination>)` — the destination is what a peer addresses.
  Class-level `@MessageMapping` prefixes compose exactly as `@RequestMapping` paths
  do. `@SendTo` on a STOMP handler derives outbound rows to the reply
  destination — 2D's vocabulary pointed at a new protocol, no new mechanism.
  **Execution amendment (Task 5, fix round 1): `@SendToUser` does not.** 2D's `reply`
  block is SINGLE-valued (`reply.annotation` is one fqn, and widening it is an engine
  change this phase's own acceptance rule forbids), so a `@SendToUser`-only handler
  falls into the branch an unannotated value-returning handler already takes — the
  honest `path` NULL, `resolution: unresolved` reply row, never a wrong destination. Payload
  shape from the handler's payload parameter; format via the ladder (rung 5 assumed
  JSON when Jackson is present — Spring STOMP's default converter, so
  `json (assumed)` is the true reading).
- **Programmatic registration**: `registerWebSocketHandlers` /
  `.addHandler(handler, "/ws")` as a `single_call`-style catalog entry — literal path
  argument, handler class from the handler argument; a non-literal path derives
  unresolved. Existing engine.

## 6. SSE and `protocol_hint` (mechanism 2 of 2)

Nothing declares SSE — the same `@GetMapping` is REST or SSE depending on its return
type. The reserved `protocol_hint` style becomes real, honoring its long-standing
contract: **it reclassifies rows other engines already produced; it changes
`protocol`, never `direction`, and never creates an endpoint.**

- **Execution** (D02 amendment): still catalog-declared, but executed as a post-merge
  resolve pass (`resolve/protocol_hint.py`) — the 2G `format.py` precedent; D02's
  "runs last with config_join" sentence predates resolve passes and is amended.
  Pipeline order: engines (incl. merge) → parse_binding → **protocol_hint** →
  resolve_format — so SSE rows take the format ladder under their true protocol.
  Post-merge protocol rewriting cannot collide: nothing else writes `sse`, and a
  merged `both` row reclassifies wholesale, staying one endpoint.
- **Evidence, in order**: (1) declared media — the row's `produces` contains
  `text/event-stream` (readable since 2E; COVERAGE's "one cheap win"); (2) return-type
  read — the handler signature's return type appears in the catalog's `hint_returns`
  list (`SseEmitter`; `Flux<ServerSentEvent<T>>` via the PTR carrier — the generic
  wrapper chain is catalog data). Scoped to `http` rows only; graphql/websocket/
  messaging rows are never touched.
- **Format honesty**: `text/event-stream` is the envelope, not the payload —
  `media_formats` maps it to nothing. The per-event payload falls to rung 5
  (`json (assumed)` with Jackson present) or stays `unresolved` — COVERAGE §4.1's
  "Assumed JSON per event" finally carries its trust marker. Payload shape:
  `ServerSentEvent<T>`/`Flux<T>` unwrap through existing PTR/generic machinery.
- **Rung 1 goes live**: `format_fixed: json` on the GraphQL catalogs — four of them
  once `graphql-schema.yml` (§3's amendment) is counted, since every catalog owning the
  protocol carries the identical entry and the ladder refuses a contradiction — the
  first live surface for 2G's rung 1, closing that documented dead branch. WebSocket
  declares no fixed format (frames are anything); SSE's fixedness is the envelope
  only, so neither gets a `format_fixed`.

## 7. Fixtures and proof obligations

Fixture-only compile deps in `orders-service`: `spring-boot-starter-graphql`, the DGS
platform annotation jar, `org.eclipse.microprofile.graphql` API jar,
`jakarta.websocket-api`. Surfaces:

- A `@Controller` with `@QueryMapping` (annotation value), `@QueryMapping` (method-name
  fallback), `@MutationMapping`, `@SubscriptionMapping` returning `Flux<T>`, a
  `@SchemaMapping(typeName = "Order")` nested resolver, and a `@BatchMapping`.
- `src/main/resources/graphql/schema.graphqls` + a second file (multi-file merge pin):
  root types including **one schema-first-only operation no annotation implements**
  (the RuntimeWiring pin — derives at `declared` with NULL handler), object types with
  `!`, lists, an enum, an input type, an interface.
- One DGS `@DgsComponent` query and one MicroProfile `@GraphQLApi` query — the
  zero-engine-change pins.
- `@ServerEndpoint("/live")` + `@OnMessage`; a STOMP controller with a class-level
  prefix, `@MessageMapping`, `@SubscribeMapping`, and `@SendTo`.
- An `SseEmitter` handler with NO `produces` (return-type rung); a
  `Flux<ServerSentEvent<OrderEvent>>` handler WITH `produces = text/event-stream`
  (media rung + PTR payload pin).

Checkpoint items (freeze before dependent tasks): defaulted annotation values in real
bytecode (Spring method-name fallback, DGS attribute names, MicroProfile defaults);
multi-file SDL merge including a cross-file type reference; `@BatchMapping`'s actual
signature shapes; what `@OnMessage`/class-level `@ServerEndpoint` look like to the
scanner. Exact-list pins from live runs only; double-run byte-identity over every
touched table.

## 8. Dependencies (GUIDELINES §7 — approved in brainstorm)

- Python: `graphql-core`, pinned (SDL parsing in the one interpreter module only).
- Fixture: the four compile-scope jars above. No extractor changes, no extractor deps —
  2H needs no new facts (checkpoint may falsify; any gap found routes through a plan
  amendment, not silent extractor work).

## 9. Docs, rendering, gaps

- D00: three protocol members. D01: the operation identity forms (`graphql query
  orders`, verbless `Type.field`, STOMP destinations as path). D02: `protocol_hint`
  rewritten reserved→real with the execution amendment; `schema_operations` style;
  `hint_returns` vocabulary; `format_fixed` now live. D06: rendered identities drop
  the verb exactly as messaging rows do where method is NULL. **Execution amendment
  (Task 6/7):** two protocols are also PREFIXED with their own name, because their verb
  does not imply one — `graphql query orders` (a bare `query orders` names nothing in
  particular) and `sse GET /events/stream`, which is VERBED with an ordinary HTTP verb
  because an SSE stream is a route a client GETs, and unqualified would read as an
  ordinary REST route. A GraphQL resolver's NULL verb renders `graphql Order.lines`
  rather than `(unresolved)`; an SSE row's would not, because there it really is unread.
- COVERAGE: §5.4/5.5/5.6 Java flips; §4.1 GraphQL + SSE regime rows live; boundaries —
  raw WebSocket frames untyped; negotiated subprotocols unread; body-string SSE
  (Go/Express style) stays unshipped; DGS/MicroProfile client sides out;
  programmatic RuntimeWiring beyond SDL roots unread; **no Java-class↔SDL-type join**
  (§4); subscription transport (WS vs SSE) not resolved — the operation is the
  identity; GraphQL federation directives parsed as data, meaning deferred to L-era.
- README dependency section gains `graphql-core`.

## 10. Out of scope, stated

SOAP (2I). GraphQL federation semantics. Subscription transport negotiation. STOMP
broker relay topology. SDL directive semantics. Client-side GraphQL (Apollo iOS et
al. — other languages' phases). Body-string SSE detection (C-tier, needs
`runtime_dynamic`-adjacent reading no engine has).
