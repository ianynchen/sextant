# COVERAGE

The completeness checklist: what Sextant can detect, what it cannot, and what each gap
costs. Delivery status is in [PROJECT.md](PROJECT.md); this is about *reach*.

Organised on two axes — **language × application protocol**. §2 is the index, §5 is the work list.

Written after running Phase 1 against [spring-petclinic](https://github.com/spring-projects/spring-petclinic),
which found **zero endpoints on the first attempt** because the catalog matched
`@RestController` and petclinic uses `@Controller`. Coverage gaps are invisible until
something real is pointed at the tool.

---

## 1. How to read this

### Tiers

A tier is the **marginal cost of one cell, given that language's baseline scanner exists**.
This is the important qualification. Measuring every language against the *JVM's* engine
would collapse the whole table to "JVM: interesting, everything else: B", which tells us
nothing.

| Tier | Means | Cost |
|---|---|---|
| **A** | A catalog against the language's baseline engine | One YAML file and a fixture. **No code.** |
| **B** | Needs a capability beyond the baseline | Work in the extractor, then a catalog |
| **C** | The boundary is not in the code at all | New modelling |

Each language declares its **baseline** in §3 — the engine set its mainstream frameworks
require, which any scanner for that language would have to ship with on day one. Java's
baseline is `annotation`, which is why `WebClient` is B there. Go's baseline is
`registration_call`, which is why `gin` is A there.

### Status

| | |
|---|---|
| ✅ | **Shipped today** — implemented, tested, verified against a real project |
| ◐ | **Partly shipped** — working, with known gaps in the same cell |
| **A** / **B** / **C** | **Not built.** Tier is the *marginal* cost of the mainstream library, measured against that language's baseline — not against what ships today |
| — | Not applicable — the protocol does not exist in that ecosystem |
| ⛔ | **Blocked by the language toolchain**, not by our effort. Used once, on Rust: no stable compiler API exists to ask, at any price |
| · | **Not yet enumerated** — §5 has no rows for this cell, so we do not know. Distinct from `—`, which means we looked and it does not exist |
| ⚠️ | **Not confirmed against a primary source.** Attached to a claim, that claim needs checking before it enters a catalog. As a whole cell, no tier could be assigned because the underlying fact is unverified |

`—` and `⛔` are deliberately distinct from a gap. JMS in Go is not missing work, and Rust's
missing compiler API is not something more effort would fix.

`⚠️` is the one marker that is about **us**, not about the ecosystem: it records where this
document's own research stopped short.

### Detection shapes

Every boundary surveyed falls into one of eight shapes. **The shape is a property of the
library and never goes stale; the tier is a property of this moment and burns down.** Encode
the shape once and the tier follows from which capabilities exist.

| Shape | The facts live in | Example |
|---|---|---|
| `annotation` | A declaration | `@GetMapping("/x")`, NestJS `@Get()`, Retrofit `@GET`, FastAPI `@app.get` |
| `registration_call` | One call's literal arguments | `app.get("/x", h)`, `mux.HandleFunc("GET /x", h)`, `pb.RegisterFooServer(s, impl)` |
| `generated_descriptor` | Schema embedded in generated code | protobuf descriptors, Avro `SCHEMA$` |
| `interface_implementation` | Direct interfaces plus a registration join | gRPC `FooImplBase`, `MessageReceiver` |
| `fluent_chain` | Spread across a builder chain | `WebClient`, `RestClient`, AWS SDK, Vert.x |
| `filesystem` | The file's path on disk | Next.js `app/api/users/[id]/route.ts` |
| `config_join` | Code names a key; the value is in configuration | Spring Cloud Stream, SmallRye, MicroProfile REST Client |
| `runtime_dynamic` | Built at runtime; **no static form exists** | `boto3` clients, DRF routers, `@grpc/proto-loader` |

`runtime_dynamic` is the only shape where the honest answer is that we cannot see it. The
other seven are engineering.


### Transport versus application protocol

HTTP is a **transport**. What we care about is the application protocol running on top of
it, because that is what determines the *address shape* of a boundary — and therefore what
can be matched against what.

| Application protocol | Transport | Address shape | Consequence |
|---|---|---|---|
| **REST** | HTTP/1.1, HTTP/2 | verb + path template | One route, one operation |
| **SOAP** | HTTP POST | namespace + localPart | **One HTTP path, N operations** |
| **GraphQL** | HTTP POST, usually one path | operation type + field name | **One HTTP path, N operations** |
| **WebSocket** | HTTP upgrade, then frames | connection path + **event name** | **One HTTP path, N events** |
| **SSE** | HTTP GET, streaming response | path + event name | One route, a stream |
| **gRPC** | HTTP/2 | `package.Service/Method` | Invisible to any HTTP-level matcher |
| Webhook | HTTP — an inbound REST endpoint | verb + path | Detection-identical to REST; a semantic property, not a protocol |

**Two consequences that change the model.**

**Four of these put one HTTP path in front of many logical operations.** A service exposing
200 GraphQL fields has exactly one HTTP route, and a SOAP service exposing 40 operations has
one. **The unit of a boundary has to be the operation, not the HTTP route** — otherwise we
would report "1 endpoint" for both and the system tier would have nothing to match.

**The protocol is not always determined by the annotation.** A Spring `@GetMapping` returning
`List<Order>` is REST; the same annotation returning `SseEmitter` or
`Flux<ServerSentEvent<T>>` is SSE. `@ServerEndpoint` is WebSocket. The declaration is
identical and the **return type** decides. This generalises a gap recorded for
`@HttpExchange`, where the *direction* depends on use rather than on the catalog. Both are
resolved per match against a catalog-level default —
[D02](components/D02-catalog-schema.md) §2c. **`format` is not**: it turned out not to be
answerable at match time at all, and is stamped instead by one late pass over the finished
endpoint table (§4.1, and the same §2c).

### Verification

Researched against primary sources, August 2026, and **re-verified in full**: every fully
qualified name, package relocation and library-maturity claim in this document has been traced
to a primary source. `⚠️` currently appears nowhere outside this legend — if it returns, it
marks a claim that has not been. A wrong annotation name does not fail loudly; it silently
matches nothing, which is exactly how petclinic returned zero endpoints.

---
## 2. The matrices

Rows are languages. **Scanner** is the prerequisite: without it, nothing else in the row is
reachable regardless of tier. Split in two because the address shapes differ (§1) and one
eleven-column table is unreadable.

### What ships today

**Two cells, now with contracts and an outbound direction.** Java and Kotlin, REST inbound,
read from compiled bytecode, via two catalogs — `spring-web` (`@RestController`) and
`spring-mvc` (`@Controller`) — each matching `@RequestMapping` plus the five verb shortcuts
and reading the `value`/`path` aliases. Since Phase 2A an endpoint also carries its request
and response contract field by field — wire name, wire type and format, `required`,
`nullable`, each with its trust fields — rooted through declared wrappers, with known types
mapped to their wire form and expansion stopping visibly at unknown ones. Since Phase 2B the
same `annotation_driven` engine also reads REST outbound — Feign `@FeignClient`, Spring
`@HttpExchange` and Retrofit `@GET` — carrying the same payload contract. Since Phase 2C two
more engines read REST outbound from method calls rather than annotations, both fed by the
same linked `call_site` facts: `single_call` reads `RestTemplate`, and `fluent` reconstructs
builder chains for `RestClient`, `WebClient` and OkHttp, calls made inside lambdas included.
A module's full analysis exports as a self-describing D06 bundle. Eight of the eleven designed
scanner capabilities are implemented: `annotation_args`, `typed_signatures`,
`type_annotations`, `kotlin_metadata`, `call_site`, `string_constants`, `chain_reconstruction`
and `implemented_interfaces`. Verified end-to-end on spring-petclinic: 17 endpoints, byte-identical
across runs.

**Phase 2D gave §2b the same texture.** `@KafkaListener` (class-level `@KafkaListener` +
`@KafkaHandler` included), `@JmsListener` and `@SqsListener` are read as inbound catalogs;
`KafkaTemplate`, `ReplyingKafkaTemplate`, the raw `KafkaProducer`, `JmsTemplate`, `SqsTemplate`
and `PubSubTemplate` (publish, and typed `subscribeAndConvert` inbound) are read outbound by the
same `single_call` engine 2C shipped, pointed at `send`-shaped methods; a `@KafkaListener` method
returning a value under `@SendTo` derives its reply as a second, outbound row. None of these carry
a method in their wire identity — D01's verbless case, rendered as `protocol path` alone.

**2E-prep then shipped the raw driver clients Phase 2D deferred, plus the codebase's sixth
engine style.** Direct `jakarta.jms.Session` producers/consumers, `KafkaConsumer.subscribe`,
AWS SDK v2 `SqsClient` and the co-located Google `Publisher` builder chain read through
`single_call`/`fluent` unchanged; `Subscriber` + `MessageReceiver` reads through
`interface_implementation`, a new style joining a registration call site to a receiver's own
directly declared interfaces — never a supertype's — the first framework this codebase reads by
matching a type's shape against a catalog rather than an annotation or a call alone. Every
`endpoints` row also now carries `catalog_id`, naming the catalog that derived it.

**Phase 2F then made configuration a first-class fact.** Every `application.yml`/properties
file resolves into `resolved_config`, one row per key per environment, through a
catalog-declared `config_model` (D02 §2i) — no framework name in the engine, the same
generic-interpreter discipline every style keeps; a key that cannot be resolved is recorded
with a reason and the environment, never a bare "unresolved". Two consumers ride it: the
`config_join` engine (D02 §2d's eighth style) joins a bean's own name to the configuration
key that names its destination — shipped for Spring Cloud Stream's functional
`Consumer`/`Supplier`/`Function` bindings and Kafka's serializer-to-format table — and the
field resolution ladder (D02 §2j) climbs a DECLARED outbound base address (a field, a
constructor parameter, an `@ConfigurationProperties` class) to the same table, so
`WebClient.builder().baseUrl(...)` fed from configuration composes a real address per
environment instead of standing `unresolved`. Both land as expressions, not values —
`resolved_peers` (a join, never a write) answers each per environment, so a bundle serves
every environment and the system tier selects (D06 §3).

**Phase 2G then made the wire format an answered question.** Every `endpoints` row now
carries `format` and `format_resolution`, stamped by a six-rung ladder over the finished
table (§4.1, [D02](components/D02-catalog-schema.md) §2c) whose whole vocabulary — the MIME
table, the serializer-to-format table, the default-converter package families, the parse
calls — is catalog data. Protobuf and Avro schemas reach the same `shapes`/`shape_fields`
tables 2A built, from **both** origins: the descriptor a generated class embeds (harvested
by the extractor as string constants and handed on unparsed) and the repository's own
`.proto`/`.avsc` files, compiled and read by the one component in the core that understands
a schema format — compiled wins where both declare the same schema (DR-4). Fields carry
their `field_number` and protobuf's own `json_name` as the wire name. Bytes-only channels
bind their payload from the parse call in the code, at the handler or one delegation hop
out; a parse further out, or two parses of one payload, binds nothing and becomes a row in
the new `open_questions` ledger — a workspace table, a bundle artifact and a section of the
rendered document, handing the undecidable to the enrichment tier instead of guessing.

**Phase 2H closed the three HTTP-adjacent columns of §2a.** GraphQL, WebSocket and SSE
join [D00](components/D00-fact-schema.md)'s protocol set, and each gets the wire identity
it actually has: a GraphQL FIELD is the endpoint (`graphql query orders`, `graphql
Order.lines`), a WebSocket destination is verbless like a topic (`websocket
/orders/place`), and an SSE route keeps its HTTP verb under a new protocol (`sse GET
/events/stream`). Six catalogs and one SDL reader ship it. The phase delivered the two
mechanisms the roadmap had reserved: **`schema_operations`**, the ninth engine style and
the first to read a schema file as a statement of operations — a schema-first service with
no annotation anywhere now derives its roots, at `declared` with a NULL handler — and
**`protocol_hint`**, which is not an engine at all but a post-merge resolve pass that
RECLASSIFIES rows other engines minted, changing `protocol` and never `direction`, never
the row count, and never anything outside the source protocol its own catalog declares.
Two framework-neutral naming forms on `annotation_driven` (a name that falls back to the
annotated construct's own, and a scope composed onto it) carried all three GraphQL
frameworks, with **DGS and MicroProfile riding them with zero further engine change** — a
deliberate early run of 2J's acceptance test. `graphql-core` joined the core dependencies,
confined to the one descriptor interpreter like `protobuf` before it, and the format
ladder's rung 1 got its first live surface.

**Everything else in both matrices remains a gap** — including, inside the cells Phase 2D and
2E-prep touched, Spring Integration's channel adapters and spring-cloud-aws's own
channel-adapter bindings (`config_join`'s shape, not yet catalogued — Spring Cloud Stream's
own functional bindings are the one row this phase ships), and every messaging peer address
except SQS's queue URL. In particular, per Q1 a tier in a row whose
**Scanner** reads `none` is a *marginal* cost — what the cell would take once a scanner for
that language exists. It is not a cost you can pay today. Only ✅ and ◐ mean working code.

### What a run produces — and what it does not

The matrices above count libraries; this section answers the operator's question. Running
`sextant module analyze` → `render` → `export` against a compiled Java/Kotlin Spring Boot
module today produces:

- **Facts** — one JSONL file per compiled source file: symbols with typed signatures,
  every annotation from both retention tables with `type_path`, field type references with
  wire types and nullability, Kotlin nullability projected from `@Metadata` and the
  interop annotations.
- **A graph workspace** — `endpoints` in both directions (inbound `@RestController`/
  `@Controller`; outbound Feign, `@HttpExchange`, Retrofit, `RestTemplate`, `RestClient`,
  `WebClient`, OkHttp — plus, since Phase 2D, `@KafkaListener`, `@JmsListener` and
  `@SqsListener` inbound, and `KafkaTemplate`, `ReplyingKafkaTemplate`, `KafkaProducer`,
  `JmsTemplate`, `SqsTemplate` and `PubSubTemplate` outbound — and since 2E-prep, direct
  `jakarta.jms.Session` producers/consumers, `KafkaConsumer.subscribe` and AWS SDK v2
  `SqsClient`/co-located Google `Publisher` outbound, plus `Subscriber` + `MessageReceiver`
  inbound through the new `interface_implementation` style — and since Phase 2E, WebFlux
  functional routing (`RouterFunctions.route()`/`.andRoute()`/`.nest()`, Kotlin's `coRouter {}`)
  through the new `combinator` engine, inherited and meta-annotation-composed `@RequestMapping`
  rows, and every inbound row's declared `consumes`/`produces` media types — and since Phase 2F,
  Spring Cloud Stream's functional `Consumer`/`Supplier`/`Function` bindings through the new
  `config_join` engine), each with its wire identity, handler and/or caller, `peer` where the
  code declares one or a DECLARED base address climbs the field ladder to a configuration key
  (NULL on every messaging row except SQS's queue URL — broker addresses are otherwise
  configuration), and its request and response payload descriptors; `shapes`/`shape_fields`
  holding every reachable payload field by field — wire name, wire type and format, `required`,
  `nullable`, trust fields — with known types mapped and expansion stopping visibly at unknown
  ones. A path the module both exposes and calls is one endpoint, direction `both`.
- **`resolved_config` and `resolved_peers`** (Phase 2F) — every configuration key resolved per
  environment, with a reason where it could not be; and, per environment, every outbound
  expression's own substituted address — a join over the two, never a write, so a bundle
  serves every environment and a consumer selects (D06 §3).
- **A format on every endpoint row, and an `open_questions` ledger** (Phase 2G) — `format`
  and `format_resolution` on every row, `resolved` where a protocol, a declared MIME type or
  a configured serializer named the wire and `narrowed` where only the payload's own type or
  a framework default suggested it, NULL and `unresolved` where nothing did; declared shapes
  from embedded descriptors and repository schema files in the same `shapes`/`shape_fields`
  tables, with `field_number` and `json_name` wire names; and one row per question no pass
  could answer, carried into the bundle and rendered in the document.
- **`architecture.md`** — coverage (environments resolved, every unresolved configuration key
  named with its reason and environment, every unresolved endpoint derivation named by catalog
  and site), a Mermaid contract class diagram, per-endpoint contract tables for inbound, an
  outbound table with peers, a **Format column beside Media on both endpoint tables** —
  hedged as `(assumed)` for anything below `resolved`, `unresolved` where nothing answered —
  an **Open questions** section where the ledger holds rows, and a Known-gaps section naming
  every omission below.
- **`metadata.json` and a D06 bundle** — the machine-readable summary, and a portable
  directory of Parquet tables plus a manifest carrying versions, catalog hash, coverage,
  the profiles resolved (`environments`, Phase 2F) and the same gaps, byte-identical on
  every re-run of the same inputs. Since Phase 2G the summary also names, in full rather
  than counted, any schema source `protoc` refused to compile (`schema_sources_not_compiled`)
  and any embedded payload the interpreter could not read (`descriptors_not_interpreted`);
  and `open_questions` is one of the bundle's tables.

What a run does **not** give you, each entry named in the output's own gap list rather
than silently absent:

| You do not get | Because | Arrives with |
|---|---|---|
| Spring Integration's channel adapters, spring-cloud-aws's own channel-adapter bindings | each names a destination through a channel indirection, not a bean's own functional shape — `config_join`'s shape fits, but neither has a catalog yet (D02 §2d) | undecided |
| A base address built by computation — concatenation, setter injection, a method's return value | only a directly-read field, a constructor-injected value, or an `@ConfigurationProperties` class climbs the field ladder to configuration; a computed base derives `path` NULL, `unresolved` (`computed_base_addresses_not_traced`) | undecided |
| Configuration constructed in code — a settings module, a config factory | only configuration FILES reach resolution; a `resolved_config` row exists only where a reader parsed a file from disk (`config_as_code_not_read`) | undecided |
| Every messaging peer except SQS's queue URL | a broker address is connection configuration, never the destination expression `config_join`/the field ladder resolve — `peer` stays NULL there even where the destination itself now resolves | undecided |
| Sequencing between reactive/lambda calls (`flatMap`, `map`) | calls inside them derive endpoints, but the sequence between those calls awaits the call graph (`reactive_flow_not_traced`) | call-graph phases |
| Sequence diagrams, traces, a call graph | no `call_site`/control-flow facts (`sequence_diagrams_pending_call_graph`, `call_graph_not_implemented`) | call-graph phases |
| A full class diagram (inheritance) | only contract types are drawn (`structure_diagram_limited_to_contracts`) | with the `edges` table |
| A link between a Java class and the SDL type of the same name | two shape universes now describe one GraphQL service, and matching them by simple name is a guess; both are recorded and the cross-link is comparison work with its own evidence (§5.4) | the phase that earns it |
| The HTTP address a GraphQL or STOMP service listens on | the `path` column carries the OPERATION, because that is what the identity is; no engine derives `/graphql` or the STOMP endpoint registration ([D01](components/D01-graph-schema.md) §3) | undecided |
| Cross-service links or a system document | linking is a system-scope pass over bundles; no `participants`/`links` exist yet | linking phase |
| `consumes`/`produces` on a predicate-derived WebFlux functional route | `accept(...)`/`contentType(...)`'s `MediaType` vararg constants compile through an `ANEWARRAY` the extractor cannot read | a later extractor candidate |
| `@RequestMapping` inherited from a non-generic superclass | the `supertype` edge exists only for a generic superclass — the extractor reads it from the Signature attribute alone | undecided |
| A handler symbol for a Kotlin WebFlux functional route | Kotlin compiles every DSL handler to an `instance`-kind argument naming a generated class, never a method | undecided |
| Trustworthy analysis of a POM using parents/profiles/interpolation | the detector reads `pom.xml` raw (`maven_parent_and_profile_resolution_not_implemented`) | undecided |
| A payload bound from a parse more than one delegation hop from its handler | a flow followed further than it was observed is an assumption; the parse is found at hop two and ledgered as an open question instead, and past hop two it is not found at all (`payload_parsed_beyond_horizon`, §4.2) | the enrichment tier |
| A payload bound where one channel's bytes reach two different parses | two answers about one wire is a question for a reader, not a coin toss to publish (`payload_parse_ambiguous`) | the enrichment tier |

Two honesty caveats also ride every output: a merged `both` endpoint keeps only the
handler's declared contract (`merged_endpoints_keep_only_the_handlers_contract`), and —
even though endpoint request/response contracts are scoped to the catalog that produced
them — a payload type reachable from several catalogs is still expanded once, under
whichever catalog's rules reach it first, not necessarily the ones that produced the
endpoint referencing it (`shape_rules_unscoped_to_the_producing_catalog`). The shipped
catalogs do not declare identical rules, so a wrapper type one of them unwraps and
another does not can be reported as an unexpanded type even where the shape behind it
was expanded correctly.

**Configuration resolution (Phase 2F) carries its own honesty caveats**, narrower than a
missing capability — each is a nuance in how far a shipped mechanism reaches, not a gap in
the gap list:

- **A candidate is never gated on the bean annotation.** `config_join`'s Spring Cloud
  Stream catalog matches every method whose RETURN type is a `Consumer`/`Supplier`/
  `Function` — a private helper that merely returns one, never itself a `@Bean`, is picked
  up exactly like a real bean, and where `spring.cloud.function.definition` is absent
  (every candidate binds, the framework's own default) it derives its own row, unresolved
  when nothing in configuration names a destination for it.
- **A binding key absent from every configuration file is visible as its unresolved
  endpoint row, not as a named key.** Only a key some file actually declares reaches
  `resolved_config` at all — a key nobody wrote has no row to be missing FROM, so there is
  nothing for the coverage report to name it by. The report instead names the row itself:
  by its `catalog_id` and by its `handler` (the bean method exists even where its binding
  key does not) — the honest boundary discovered when Task 7's review found no
  engine-to-report channel carrying a config_join row's own key.
- **`@ConfigurationProperties` binds through the `prefix` argument only; the `value`
  alias is not read.** A class annotated `@ConfigurationProperties(value = "billing")`
  never climbs the field ladder — only `prefix =` does.
- **Relaxed binding is honest at the ladder and exact at the join.** The field ladder's
  rung 3 emits the DECLARED field's own spelling (`getBaseUrl` → `${billing.baseUrl}`),
  but `resolved_config`'s join compares keys exactly — a properties class whose field is
  `baseUrl` and whose config key is written `base-url` produces an expression no
  environment resolves (`missing_key`, correctly, though the value exists).
- **A constructor-assigned field names no overload.** Where two constructors assign the
  same field from different parameter positions, the field ladder's rung 2 takes the
  first (by symbol order) carrying the argument annotation at that index —
  deterministic, never a guess, but a first match rather than a proof.
- **The `${}` placeholder delimiters are engine constants**, shared between the field
  ladder's own synthesis (rung 3) and `resolved_peers`' substitution query — a framework
  whose placeholder syntax differs would need the pair threaded onto `field_sources`
  rather than reading it from the catalog, the way every other config_model detail is.
- **Media stamping requires agreement across every environment.** Kafka's
  serializer-to-format table (§4.1) stamps `consumes`/`produces` only where every
  environment's own serializer key resolves to the SAME class; a per-environment split —
  JSON in `default`, Avro in `prod` — leaves both columns NULL rather than picking one
  environment's answer over another's.
- **A `resolved_config` row imported from a remote source is never fetched.** A
  `spring.config.import`-shaped value resolves `unresolved_reason: remote_source`,
  naming where the value lives, never what it is.

### 2a. Application protocols over HTTP

| Language | Scanner | [REST in](#51-rest-inbound) | [REST out](#52-rest-outbound) | [SOAP](#53-soap) | [GraphQL](#54-graphql) | [WebSocket](#55-websocket) | [SSE](#56-server-sent-events) |
|---|---|---|---|---|---|---|---|
| **Java / Kotlin** | ✅ ASM | ◐ 5A 3B 5C | ◐ 2A 2B | 2A | ✅ | ✅ | ◐ 1A |
| **Go** | none | 2A 1B 1C | 1A | — | 1A | 1B | 1C |
| **TypeScript** | none | 3A 2B | 1A | — | 2A | 2A 1B | 1B 1C |
| **JavaScript** | none | 3A 2B | 1A | — | 2A | 2A 1B | 1B 1C |
| **Python** | none | 4A 1B 1C | 1A | 1B | 2A | 2A 1B | 2B |
| **Rust** | none | 1A 2B 1C | 1B | — | 1A | 1A 1B | 1B |
| **Swift** | none | 1A | 1A 1B | — | 1A | 1B | — |

### 2b. Messaging and RPC

SNS and Redis are **out of scope by decision**, not oversight — each would be a new column.

| Language | [gRPC](#57-grpc) | [Kafka](#58-kafka) | [JMS / AMQP](#59-jms-and-amqp) | [SQS](#510-aws-sqs) | [Pub/Sub](#511-google-cloud-pubsub) | [Async](#512-async-and-internal-boundaries) |
|---|---|---|---|---|---|---|
| **Java / Kotlin** | 3A 1B | ◐ 1A 2B | ◐ 2A | ◐ 2A 1B | ◐ 1A 1B | 2A 2B 1C |
| **Go** | 1A | 2A | 1A | 1A | 1B | 2A |
| **TypeScript** | 2B | 1A | 1A | 1A | 1B | 1A |
| **JavaScript** | 2B | 1A | 1A | 1A | 1B | 1A |
| **Python** | 1A | 2A | 1A | 1C | 1B | 2A |
| **Rust** | 1A | 1A | 1A | 1B | 1B | 2A 1B |
| **Swift** | 1A | 1A | — | 1B | — | 1B |

**Wire format is not in these tables at all** — see §4. Format is a property of a channel to
be *inferred*, not a protocol to be supported: Avro-over-Kafka, Protobuf-over-gRPC,
Protobuf-over-REST and JSON-over-anything are all real, and the detection job is nearly
identical in every language.
### Reading the matrices

**Every cell is generated from §5** by `scripts/coverage_matrix.py`, so the summary cannot
drift from the checklist it summarises. A cell counts libraries at each tier — `4A 3B 2C`
means four need only a catalog, three need a scanner capability, and two are not in the code
at all. **The spread is the point**: a single headline tier hides the gap, which is the thing
worth seeing.

**Java + Kafka shows why.** Several ways of using Kafka from Java cost a YAML file each;
several more need real work, including `KafkaProducer.send(new ProducerRecord("t", …))`, where
the topic is a constructor argument of a *different object*; and Spring Cloud Stream and
SmallRye put the topic in a properties file under a key derived from a bean name. A cell
reading "A" would have been true and useless.

**Java REST inbound is the largest cell in the document at `8A 8B 5C`** — twenty-one distinct
ways of declaring an HTTP endpoint in one language, of which we currently read two. That
number, more than anything here, is the argument for catalogs being data.

**SSE is the worst column in either matrix**, and the only one worse in every language than
the protocol it rides on. Nothing declares it: it is inferred from a return type
(`SseEmitter`, `Flux<ServerSentEvent>`, axum `Sse<S>`, `EventSourceResponse`) or, in Go and
Express, from a bare `Content-Type: text/event-stream` string in the handler body.

**GraphQL is the cheapest new protocol on the page — tier A everywhere it exists.** Every
ecosystem either annotates its operations or ships an SDL file that *is* the contract.

**The JVM is the outlier on gRPC.** Everywhere else the generated code names the service in a
call — Go's `pb.RegisterFooServer(s, impl)`, Python's `add_FooServicer_to_server`, Rust's
`FooServer::new`. Only the JVM uses inheritance, which is why gRPC carries a B for us and A
for everyone else.

**`registration_call` is to the non-JVM languages what `fluent_chain` is to the JVM** — one
capability unlocking most cells at once. It is the baseline for four of the seven rows.

**Pub/Sub is B in every language.** Only Micronaut ships a first-party annotation; everywhere
else it is a builder chain over a client library.


### Why the tiers are consistent

Tiers here are not assigned row by row. A tier is derived from the row's **detection shape**
against the capabilities that language's scanner has:

```
shape ∈ that language's baseline                       → A
shape ∈ {runtime_dynamic, combinator}                  → C   (not in the code)
otherwise (fluent_chain, generated_descriptor,
           interface_implementation, config_join,
           filesystem)                                  → B
```

**`config_join` and `filesystem` were C until the design questions in §8 were settled.** They
are B now because a mechanism exists on paper — [D02](components/D02-catalog-schema.md) §2d
and the `filesystem` style. Nothing about the frameworks changed; what changed is that we know
how to read them. That is the burndown property working, and it is the reason a tier is
derived rather than asserted.

Checked against all 183 rows, this reproduces the hand-assigned tier **86%** of the time, and
every disagreement was worth having. The largest cluster was **our own inconsistency**: in
Java, `RestTemplate`, `KafkaTemplate.send`, `KafkaConsumer.subscribe` and `JmsTemplate.send`
are all `registration_call` and had been marked A, while Javalin, Alpakka and the Vert.x event
bus — *the same shape* — were marked B. The first four were wrong: Phase 1 records no call
sites at all, so none of them is a catalog away. They now read B, and become A the day
call-site extraction ships. That is the burndown property working.

Three residual cases need more than a shape, and are recorded rather than smoothed over:

- **`combinator` spans B to C** by nesting depth. Ktor and WebFlux functional routing are
  tractable; Akka HTTP's `path(…) { get { … } }` composes routes as values across methods and
  is not.
- **`runtime_dynamic` is B, not C, when a readable artifact escapes it.** `@grpc/proto-loader`
  and `zeep` build clients at runtime, but from a `.proto` or WSDL path that is a **literal in
  the source** — so read the artifact instead. `boto3` has no such escape, which is why it
  stays C.
- **`artifact` depends on whether that reader exists.** GraphQL SDL is A because reading it is
  planned; WSDL is C because SOAP is deferred.

Run `python scripts/coverage_matrix.py --check` to confirm §2 still matches §5.

---

## 3. Language readiness — the gate on every row

| Language | Compiler-grade fact source | Types | Build needed | Call graph | Baseline engines |
|---|---|---|---|---|---|
| **Java / Kotlin** | JVM bytecode via **ASM** | Full | Yes | We write it | `annotation` ✅ built |
| **Go** | **`go/packages`** + `go/ssa` | Full | No (deps only) | **`callgraph/{cha,rta,vta}` ships with the Go toolchain** | `registration_call` |
| **TypeScript** | **`ts.TypeChecker`** compiler API | Full where annotated | No | `Jelly` | `registration_call` + `annotation` + `filesystem` |
| **Swift** | **IndexStoreDB** (index-while-building) | Full | Yes (macOS) | Index carries call relations | `registration_call` |
| **Python** | None — pyright has **no programmatic API**, only LSP | Sparse (§7) | No | `PyCG` | `annotation` + `registration_call` |
| **Rust** | ⛔ **None stable.** `syn` has no types; rustdoc JSON needs `cargo +nightly … -Z unstable-options` and its `FORMAT_VERSION` breaks between releases | Syntax only | — | None | `annotation` (syntax-only) |
| **JavaScript** | `ts.TypeChecker` via `allowJs` + `checkJs` | Inferred, plus JSDoc | No | `Jelly` | as TypeScript |

**Three findings worth stating outright.**

**Go ships the analysis we deferred.** `golang.org/x/tools/go/callgraph` provides `static`,
`cha`, `rta` and `vta` as maintained library code, and `cha` is documented sound on
partial programs — libraries with no `main`, which is our situation exactly. For the JVM we
planned to write class hierarchy analysis and defer variable type analysis. **Go's dispatch
resolution starts ahead of the JVM's.**

**Swift is not the hard case people assume.** `swiftc` emits index data as a side effect of
compilation; `IndexStoreDB` reads it into a queryable store of symbols, occurrences and
relations — the same data `sourcekit-lsp` uses for call hierarchy. It needs a build,
which fits DR-4 precisely. Periphery already works this way.

**For TypeScript the JVM rule inverts.** We scan compiled output on the JVM because bytecode
is richer than source. In TypeScript it is strictly poorer — types erased, decorators
lowered to `__decorate` calls, bundlers renaming and inlining. **Scan TypeScript source**,
with `tsconfig.json` as the build input carrying authority under DR-4.

Per-language essays — toolchain detail, payload handling, structural oddities:
[Go](coverage/go.md) · [Rust](coverage/rust.md) · [Python](coverage/python.md) ·
[TypeScript and JavaScript](coverage/typescript.md) · [Android and iOS](coverage/mobile.md).

---

## 4. Wire format — a separate concern from protocol

Format is not a protocol and not a coverage cell. It is a **property of a channel that has to
be inferred**, and it decomposes into two questions asked in order:

1. **What is on the wire?** Does this Kafka topic carry Avro, Protobuf, JSON or opaque bytes?
   Does this REST endpoint serve JSON or `application/x-protobuf`?
2. **Where is the spec for it, and how does it bind?** Which `.proto` message, which `.avsc`
   record, which XSD element describes what question 1 found?

In that framing Protobuf and Avro are **no different from JSON or XML**. The only reason they
felt different is that we have been silently assuming JSON for REST — which is not
necessarily true, and worse, is not currently recorded as an assumption.

### 4.1 Detecting the format

Evidence quality varies enormously by protocol. Three regimes — and since **Phase 2G**,
`endpoints.format` and `endpoints.format_resolution` carry the answer for every row, from
the six-rung ladder ([D02](components/D02-catalog-schema.md) §2c). The last column says how
far that reaches today:

| Protocol | How the format is declared | Evidence | If nothing is declared | Shipped today |
|---|---|---|---|---|
| **gRPC** | **Fixed by the protocol** | `compiler` | Protobuf, always. The only certain cell in this table. | Rung 1 is built; **no shipped catalog owns gRPC**, so nothing declares `format_fixed` — **A**, one catalog entry once a gRPC catalog exists |
| SOAP | Fixed | `compiler` | XML | as gRPC — **A**, with the catalog (§5.3, 2I) |
| GraphQL | Fixed | `compiler` | JSON | ✅ **rung 1, and its first live surface** (2H). `format_fixed: {graphql: json}` ships on all four catalogs owning the protocol, so every GraphQL row answers `json`/`resolved` before any other rung is consulted |
| **REST in** | `produces` / `consumes`, JAX-RS `@Produces` / `@Consumes`, or a return type that is itself a generated message | `declared` | **Assumed** from the framework's default converter (Jackson → JSON) | ◐ **rung 2** off Spring's own `produces`/`consumes` (2E), `resolved`; an undeclared route falls to **rung 5** — `json` at `narrowed` — where it carries a declared payload type at all, and to rung 6 where it carries none. JAX-RS `@Produces` is **A**, with that catalog |
| **REST out** | `Content-Type` / `Accept` set somewhere in the client chain | `syntax` | **Assumed** JSON | **not read** — no client chain's `Content-Type` reaches `consumes`/`produces`, so outbound rows answer at rung 5 (`json`, `narrowed`) or rung 6 |
| **Kafka** | **Serializer configuration** — `key.serializer` / `value.serializer`, or the generic parameters of `KafkaTemplate<K,V>` and the `@KafkaListener` payload type | `config_join` | Unknown. Kafka carries anything. | ✅ **rung 3**, from the serializer table below as catalog data (`format_from`), `resolved` — off the **value** serializer/deserializer keys the shipped rules name. The record **key**'s own serializer and the **generic parameters** of `KafkaTemplate<K,V>` are not read: configuration, and the value side of it, is the whole of it |
| SSE | `text/event-stream` framing; the payload inside each event is separate | `declared` | Assumed JSON per event | ✅ **shipped, and the framing answers nothing** (2H). `text/event-stream` is deliberately absent from `media_formats` — it is the envelope, so it names the PROTOCOL (`protocol_hint`) and never the format. The per-event payload lands at **rung 5**, `json` at `narrowed`: the "assumed" in the column to the left, finally carrying its marker |
| WebSocket | A negotiated subprotocol, or nothing — usually only the parse call | `syntax` | Unknown | ◐ **the protocol shipped, the format did not** (2H). A raw frame is untyped by declaration, so a `@ServerEndpoint` row reads `unresolved` rather than guessing; a STOMP row carries a real payload parameter and answers **rung 5** (`json`, `narrowed`). No subprotocol is read, and no parse-call rung reaches a frame |
| **Pub/Sub** | Nothing. The message is `bytes`. Only the **parse call** reveals it — `Order.parseFrom(data)` versus `objectMapper.readValue(data, Order.class)` | `syntax` | Unknown | the parse-call binding is built and protocol-neutral, but **not reached here**: the shipped bytes-payload vocabulary is `String` and `byte[]` only, and a `MessageReceiver`'s payload parameter is a `PubsubMessage` envelope |
| **SQS** | Nothing. The body is a string; same as Pub/Sub | `syntax` | Unknown | ✅ **the parse call**, binding the payload type — which, where that type is schema-described, then answers **rung 4** at `narrowed`, and otherwise makes the row an ordinary rung-5 one |
| JMS | `TextMessage` / `BytesMessage` / `ObjectMessage`, then the parse call | `syntax` | Unknown | ✅ as SQS, for a `String`/`byte[]` payload parameter. The **message-type distinction** (`TextMessage` versus `BytesMessage`) is not read |

Kafka is the interesting one, because the answer sits in configuration rather than code —
`config_join` again (§7), the same shape as Spring Cloud Stream destinations. **Since Phase
2G this table is live, as data**: it is the `format_from` block of `spring-kafka-media.yml`
([D02](components/D02-catalog-schema.md) §2c), read by the ladder's rung 3, and each
serializer's matching deserializer is catalogued beside it.

| Serializer | Format | Schema registry | In `format_from` |
|---|---|---|---|
| `org.apache.kafka.common.serialization.StringSerializer` | string | no | ✅ `string` |
| `…serialization.ByteArraySerializer` | opaque bytes | no | ✅ `bytes` |
| `io.confluent.kafka.serializers.KafkaAvroSerializer` | Avro | **yes** — subject `<topic>-value` | ✅ `avro` |
| `io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer` | Protobuf | yes | ✅ `protobuf` |
| `io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer` | JSON Schema | yes | ✅ `json` — **plain JSON is what it puts on the wire**; the schema travels out of band, and `json_schema` (the schema *language*) is a reserved value nothing writes |
| `io.confluent.kafka.serializers.KafkaJsonSerializer` | JSON | no — **note the package: no `.json` segment, and no registry** | ✅ `json` |
| `org.springframework.kafka.support.serializer.JsonSerializer` | JSON | no | ✅ `json` |

**The registry column is knowledge, not behaviour**: no subject name is derived from any of
these rows today (§4.3, §11 of the 2G design — re-derivable later from the topic and the
serializer, both of which are already kept).

**The rung fires on the wire pair, not the listener.** `format_from`'s
`on: {protocol: kafka, direction: inbound}` selector is 2F's own coverage-rule shape,
reused rather than narrowed for rung 3: it stamps every inbound Kafka row the config's
environment agreement reaches, whichever engine minted that row — a raw
`KafkaConsumer.subscribe` listener that never reads `spring.kafka.consumer.value-deserializer`
at all is stamped the same as a Spring-managed `@KafkaListener`. A fixture's count of rows
landing `protobuf`/`resolved` this way is evidence of the stamp's *reach*, never evidence
that each row's own listener was individually checked against the configured deserializer.

### 4.2 Binding the spec

| Format | Spec artifact | Where it lives | Binds by | Shipped today |
|---|---|---|---|---|
| **Protobuf** | `.proto`, or the `FileDescriptorProto` embedded in generated code | repository **and** compiled output | message type name | ✅ **both origins.** The embedded descriptor is harvested from the generated holder class and the `.proto` compiled with a bundled `protoc`; both feed one interpreter, and where both declare the same schema the **compiled one wins** (DR-4) |
| **Avro** | `.avsc`, or `SCHEMA$` on a `SpecificRecordBase` subclass | repository **and** compiled output | record full name; on Kafka, the **subject** `<topic>-value` | ◐ **both origins**, with two limits: only the Avro-1.12 `SCHEMA$` shape is harvested (below), and **no subject is derived** |
| **JSON** | Usually none — **the DTO type declaration is the spec** | code | type reference | ✅ since Phase 2A — the shape tables *are* this row |
| JSON Schema | Fastify route options, OpenAPI `components`, `zod` | code or artifact | `$ref` / type reference | **out of scope.** `json_schema` is a reserved format value: a catalog that writes it is refused by name rather than read as something adjacent |
| XML | XSD, WSDL | repository | namespace + element name | with SOAP (§5.3, 2I) |
| **GraphQL SDL** | `.graphqls` / `.graphql` under `src/main/resources/graphql` | repository **only** — SDL compiles into no class, so there is no second origin | the type's own name, which is both its `symbol` and its `schema_name` | ✅ since Phase 2H, at `declared`. The reader emits each file verbatim and the interpreter merges every file in the module into one type universe before projecting (the protobuf-pool precedent, because the runtime merges them too). Object, interface, input and enum types become shapes; **`field_number` is NULL — the format numbers nothing** |

Protobuf and Avro share a property nothing else here has: **the schema survives into the
compiled artifact**, so it is recoverable from a jar with no source present. That is the same
mechanism in every language — `generated_descriptor` — which is why it needs saying once
rather than seven times. Phase 2G is that mechanism: an extractor harvests the embedded
payload **without parsing it**, and one component in the Python core turns it into the same
`shapes`/`shape_fields` rows a Java DTO produces — so a second language's scanner gains
schema support by emitting one more fact and linking no schema runtime.

**Where a declared shape's two namings go.** A protobuf field carries both its schema name
with its `field_number` and its JSON-encoded `wire_name` (protobuf's own `json_name`, read
from the descriptor, never computed). `wire_name` is what `shape_fields` stores as the
identity and `field_number` rides beside it, so the `total_amount` → `totalAmount` rename
below is recorded rather than reconstructed.

#### Parser libraries, as catalogue rows

What turns a bytes-only channel's payload into a typed one is library knowledge, so it is
catalog vocabulary (`parse_calls`), never engine knowledge. Shipped:

| Library | Call | The payload type is | Shipped today |
|---|---|---|---|
| **protobuf** | `parseFrom` on a generated message | the call's **receiver** | ✅ matched by the receiver's **hierarchy**, never by a name pattern — a rule keyed on a generated class's spelling would have to know how the code generator names its output |
| **Jackson 2** — `com.fasterxml.jackson` | `ObjectMapper#readValue` | the `Class<T>` literal argument | ✅ |
| **Jackson 3** — `tools.jackson` | `ObjectMapper#readValue`, `JsonMapper#readValue` | the `Class<T>` literal argument | ✅ — the whole relocation between the two generations is a package rename, so it cost **three catalog rows and no code**, and both package families are also listed as `json_default_markers` for the framework-default rung. Pinned against real compiled `tools.jackson` bytecode in the fixture, not only against an invented owner in a unit test |
| Avro | `SpecificDatumReader` construction | the `Class<T>` literal argument | catalogued and **inert** — see below |

#### What 2G deliberately does not do

Each of these is a boundary of a shipped mechanism, stated so it cannot be mistaken for
coverage:

- **Parse tracing stops at one hop.** A bytes-only channel binds its payload from a parse
  in the handler's own body, or in one module-local method the handler hands the bytes to.
  A parse further out is refused, not followed: a flow followed further than it was
  observed is an assumption.
- **And the beyond-horizon ledger itself sees only hop two.** The refusal is *recorded* —
  as an `open_questions` row of kind `payload_binding`, naming the parse it would not bind
  — but only for a parse found at exactly two hops, because that is as far as the walk
  looks. A three-hop chain is indistinguishable from nobody parsing at all: no binding, no
  ledger row, `unresolved`. `payload_parsed_beyond_horizon` and `payload_parse_ambiguous`
  are named in every run's gap list, and the rows themselves are in `open_questions`.
- **Avro's `SpecificDatumReader` entry binds nothing.** It is catalogued, and it names the
  payload type — but the bytes reach a separately built decoder, never that constructor, so
  no rung can prove the channel's bytes get there. The entry declares no bytes argument and
  is inert by construction: it is where the type will already be the day a decoder-tracing
  rung exists.
- **An Avro `SCHEMA$` built the pre-1.12 way is not read.** Avro 1.12's generated code
  assembles the schema from a `String[]`, which is what the harvest recognises; older
  generators wrote `new Schema.Parser().parse("…")` with a single constant and no array. A
  module on that generator records **no schema** rather than a wrong one — silent, and
  never wrong.
- **`GeneratedMessageLite` is untested.** A lite-runtime message carries no
  `FileDescriptor` in its generated code at all, so a lite-only artifact harvests nothing —
  a gap, never a guess — and the lite marker in the parse-call vocabulary is a name nothing
  in any fixture reaches.
- **Embedded-versus-source drift is not compared.** Both origins are recorded, with the
  compiled one winning where they declare the same schema; whether they *disagree* is a
  future DR-4 check that needs no new data, because both were kept.
- **Registry subjects are not derived** (§4.1 above): re-derivable from the topic and the
  serializer, both already kept.
- **gRPC service extraction from descriptors is deferred.** A descriptor names services and
  methods; reading them is a protocol phase, not a format phase.
- **JSON Schema and XSD are out** — `json_schema` reserved and refused (§4.2 above).
- **Rung 5's presence test is annotation-only.** The framework-default rung fires when an
  annotation from a declared converter package family appears anywhere in the module. A
  module that uses a JSON converter through code alone — no annotation from its package
  family anywhere — reads `unresolved` where the converter is in fact on the classpath.
  Presence evidence, honestly narrow.
- **A merged `both` row carries ONE format column, and it can hide a per-direction split.**
  Wire identity is one row; format is one column on it. Where a module both consumes and
  produces one destination with different serializers configured per direction, the ladder's
  rung order decides what that single column says — and a higher rung answering first (a
  media type carried through the merge, say) settles it before the serializer rung is ever
  consulted, so the other direction's configured format never appears. That is the rung
  order working as specified, not a defect, but a reader must not read a merged row's
  `format` as a statement about both directions.
- **A source-origin declared shape is a fact, and stays one until something references
  it.** A `.avsc` the build never compiles produces its shape keyed by the schema's own full
  name; an endpoint payload is keyed by the generated class it travels as. Nothing joins the
  two today, so such a shape is recorded and unreferenced — the `schema_name` → symbol join
  is reserved, not built.
- **Protobuf well-known types expand as ordinary object shapes.** A `google.protobuf.Timestamp`
  field is a message field, so it becomes an `object` referring to a shape; no catalog maps
  the well-known types to the wire scalars their JSON encoding actually uses, and
  `known_types` ([D02](components/D02-catalog-schema.md) §2g) is consulted only on the
  bytecode-derived path, never on a declared shape's own fields.
- **Schema roots are the two conventional directories only** — `src/main/proto` and
  `src/main/avro`, each read when it exists. A `.proto` or `.avsc` elsewhere in the source
  tree is not swept up.

### 4.3 What this changes in the model

**An assumed format must not look like an observed one.** If a REST endpoint declares no
`produces` and we record JSON because Jackson is the default, that is an *inference from
framework configuration*, not an observation. It belongs at `resolution: narrowed` at
best — never at the same trust level as a `produces` attribute or a Kafka serializer
setting. **Shipped in Phase 2G, and as its own column rather than as an evidence tier**:
`endpoints.format_resolution` says `narrowed` for exactly these rows, and the rendered
document prints such a value as `json (assumed)` — only `resolved` ever prints unhedged.

**Protobuf-over-REST silently renames every field.** The proto3 JSON mapping converts field
names to lowerCamelCase by default, so a proto field `total_amount` appears on a JSON wire as
`totalAmount` unless `json_name` overrides it. Any service defined by a `.proto` but exposed
over REST — gRPC transcoding, gRPC-Gateway, Connect — therefore has **different field names
on the wire than its schema states**. Structural comparison (DR-5) that reads the `.proto`
and compares it to a JSON contract will report a total mismatch unless the mapping is applied
first. This is a concrete correctness bug waiting in the matching rule.

**But the descriptor answers it for us.** Reading a generated message through protobuf's own
reflection exposes each field's `JSONName()` — verified against protobuf-go — so the mapping
is **data we read, not an algorithm we implement**, and any `json_name` override comes with
it. That turns a subtle rule we could get wrong into a field lookup. **Shipped in Phase
2G**: the descriptor's `json_name` lands in `shape_fields.wire_name` for every declared
protobuf field, computed default and explicit override alike, beside the schema's own
`field_number`.

**Comparison is only valid within a format, or across a known mapping.** DR-5's directional
structural compatibility assumes both sides describe the same wire. A Protobuf request
contract and a JSON response contract are not comparable until one is projected into the
other.

**Avro already solved our matching problem, and we should borrow its vocabulary.** Schema
registries enforce `BACKWARD` (a new reader can read old data), `FORWARD` (an old reader can
read new data) and `FULL` compatibility. That is exactly DR-5's directional rule — request a
superset of required fields, response a subset — expressed in terms the industry already
uses. Aligning our vocabulary with it costs nothing and buys credibility over inventing our
own.

**The registry is a runtime service, not a repository artifact.** For Kafka with Confluent
serializers the authoritative schema lives in a schema registry we cannot read at scan time.
What we *can* derive statically is the **subject name** from the topic and the naming
strategy — which is enough to state what would have to be fetched, and is a natural place for
a `sync` command to fill in later.

## 5. The checklist, by protocol

The work list. Each row is one library in one language: what it looks like, what shape it
is, what it costs.

### 5.1 REST inbound

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@RestController` / `@Controller` + `@GetMapping` etc. | annotation on class + method | `annotation` | ✅ shipped |
| Java | **`@RequestMapping(method = RequestMethod.GET)`** | the pre-4.3 form | `annotation` | ✅ shipped |
| Java | `@RequestMapping` naming no method | Spring accepts every method, so it is one endpoint per method, not one with an unresolved method | `annotation` | ✅ shipped |
| Java | `path =` alias for `value =` | `@AliasFor`, so only the one typed reaches the bytecode | `annotation` | ✅ shipped |
| Java | `produces` / `consumes` | — | `annotation` | ✅ shipped |
| Java | Spring 7 `version = "1.1"` / `"1.2+"` on `@RequestMapping` | API versioning | `annotation` | A |
| Java | Micronaut `@Controller` + `@Get`/`@Post`… (`value`/`uri` String, **`uris` String[]**) | — | `annotation` | A |
| Java | Quarkus / JAX-RS **`jakarta.ws.rs`** `@Path` + `@GET`… | `@Path` value is a scalar String | `annotation` | A |
| Java | Quarkus `io.quarkus.vertx.web.Route` | second Quarkus style | `annotation` | A |
| Java | Actuator `@Endpoint` / `@ReadOperation` | — | `annotation` | A |
| Java | `@RequestMapping` on an **interface or superclass** | Spring inherits mappings | `annotation` + hierarchy | ✅ shipped |
| Java | **Meta-annotations** — custom `@ApiGet` composed from `@RequestMapping(method = GET)` | Spring resolves transitively | `annotation` (recursive) | ✅ shipped |
| Java | Nested / inner classes | the phase-1 skip lifted in Phase 2C — read as ordinary class files, so `@RestController`/`@Controller` resolve the same nested or not | `annotation` | ✅ shipped |
| Java | WebFlux `Mono`/`Flux` return types | response shape roots through the declared wrapper ([D02](components/D02-catalog-schema.md) §2a) | — | ✅ shipped |
| Java | **Vert.x** `router.get("/x").handler(this::h)` | receiver + verb + first arg | `fluent_chain` | **B — the cleanest first exercise for chain reconstruction** |
| Java | WebFlux functional `RouterFunctions.route().GET(…)`, `coRouter { }` | — | `combinator` | ✅ shipped |
| Java | **Akka HTTP** `path("users" / IntNumber) { get { complete(…) } }` | nested closures, route is a *value* | `combinator` | **C-ish — the hardest inbound form surveyed** |
| Java | Ktor `routing { get("/path") { … } }` | Kotlin DSL | `combinator` | B |
| Java | Javalin `app.get("/path", ctx -> …)` | — | `registration_call` | B |
| Java | **Spring Data REST** `@RepositoryRestResource` | a repository interface becomes a CRUD API | — | **C — no controller, no mapping annotation** |
| Java | `@ControllerAdvice` + `@ExceptionHandler` | defines the error contract of every endpoint | — | C |
| Java | Servlets, filters, interceptors, built-in Actuator endpoints | `@WebServlet`, `FilterRegistrationBean`, dependency + property | — | C |
| Java | `@ConditionalOnProperty` / `@Profile` controllers | exists in one environment only | — | C |
| Go | `net/http` 1.22+ `mux.HandleFunc("GET /items/{id}", h)` | **verb and path in one literal** | `registration_call` | A |
| Go | `gin`, `echo`, `chi`, `fiber` | `r.GET("/p", h)`, groups nest a prefix | `registration_call` | A |
| Go | `gorilla/mux` `r.HandleFunc(p, h).Methods("GET")` | verb is a sibling call | `fluent_chain` | B |
| Go | `net/http` pre-1.22 | verb is an `if r.Method` inside the handler | `runtime_dynamic` | C |
| TS | **NestJS** `@Controller("users")` + `@Get(":id")` + `@Body() dto` | **structurally identical to Spring MVC** | `annotation` | **A — highest-value non-JVM target** |
| TS | Express, Koa, Hapi, Hono | `app.get("/p", h)`, mounted via `app.use("/api", r)` | `registration_call` | A |
| TS | Fastify `fastify.get(p, { schema }, h)` | **options object carries a JSON Schema** | `registration_call` | A |
| TS | **Next.js / SvelteKit / Remix / Nuxt** | **path is the file path, verb is the exported symbol name** | `filesystem` | **B** — read the build's route manifest, walk as fallback ([D02](components/D02-catalog-schema.md) `filesystem` style) |
| TS | tRPC `publicProcedure.input(z.object(…)).query(fn)` | contract is a `zod` schema | `fluent_chain` | B |
| Python | **FastAPI** `@app.get("/items/{id}")`, `response_model=` | **types mandatory — the framework cannot run without them** | `annotation` | A |
| Python | Litestar `@get("/items/{id:int}")` | same | `annotation` | A |
| Python | Flask `@app.route(p, methods=["GET"])`, blueprints | prefix joined at `register_blueprint` | `annotation` + `registration_call` | A |
| Python | aiohttp `app.router.add_get(p, h)`, Starlette `Route(p, ep, methods=[…])` | — | `registration_call` | A |
| Python | **Django** `urlpatterns = [path("items/<int:id>/", views.item)]` | **path and view in different files**, nested via `include()` | `registration_call` | B |
| Python | **Django REST Framework** `router.register(r"users", UserViewSet)` | **one line produces six+ endpoints**, generated at runtime | `runtime_dynamic` | **C — read `drf-spectacular` OpenAPI instead** |
| Rust | `actix-web` / Rocket `#[get("/users/{id}")]` | attribute readable by `syn`, no types needed | `annotation` | A |
| Rust | Rocket `.mount("/api", routes![…])` | **prefix joined at the mount, elsewhere** | `registration_call` | B |
| Rust | `axum` `Router::new().route("/u", get(h))` | most popular; verb nested in arg 2 | `fluent_chain` | B |
| Rust | **`warp`** `warp::path("u").and(warp::get()).and_then(h)` | route is a composed value, type-encoded | `combinator` | **C** |
| Swift | Vapor `app.get("users", ":id") { … }` | **path segments are variadic args** | `registration_call` | A |
| Swift | iOS apps | apps are not servers | — | — |

**Phase 2E Task 7** ships the interface/superclass row above (`@RequestMapping` inherited
mapping resolution, `annotation` + `hierarchy`), gated to catalogs that declare their own
`type_annotation` — spec §3's own scope is the handler-side OpenAPI-generator pattern
(mappings on an interface, `@RestController` on the class that implements it); a gateless
catalog (Retrofit, `spring-http-interface`, `spring-jms`, `spring-kafka`, `spring-sqs`) never
runs the inheritance walk at all, since its annotated interface method already IS the
client/listener identity and an unrelated implementing class is never a plausible mapping
target (Task 7 review, Critical finding C1). Five boundaries are drawn deliberately rather
than left implicit: a **jar-defined interface is never scanned**, so its own mappings never
derive onto an implementer — the standing compiled-library boundary that gates every form
until dependency scanning exists (D02 §7); a class **directly implementing two interfaces
that map the same method** resolves to declaration order, **depth-first** — the first
interface's own ancestor chain is walked to exhaustion before the second interface is ever
consulted, matching Spring's own hierarchy-scan order — recorded as the implementer's own
read of the ambiguity, never rendered as one; inheritance folds attributes through the same
same-name-attribute subset of `@AliasFor` the meta-annotation pass already commits to, never
its full cross-name aliasing or `@AliasFor(annotation=...)` re-targeting generality; and a
class that inherits the SAME-named method from both a mapped interface AND a generic
superclass together **loses that mapping entirely** — the compiler's bridge-exclusion rule
(checkpoint item (4)) is purely structural, per class, and cannot tell which ancestor a given
bridge belongs to, so every bridge AND the real override are excluded together rather than
only the genuine bridge (Task 7 review, Important finding I1); and the **supertype edge
itself only exists for a generic superclass** — the extractor derives `supertype` solely
from the class's generic `Signature` attribute, so a plain non-generic `class B extends A`
carries no such edge and its mappings do not derive at all, even though the superclass
branch is implemented and unit-tested synthetically (checkpoint ruling F3).

**Phase 2E Task 6** ships the meta-annotations row above — the **module-local** half only: a
project's own composed mapping annotation (its `@Retention`/`@Target` and mapping attributes
declared on a type the scan reaches) resolves through a fixpoint pass over the scanned
annotation facts, folding attributes base-outward through the same same-name-attribute
`@AliasFor` subset Task 7's inheritance pass reuses. An **unscanned framework jar's own
internal composition** — `@GetMapping` itself is meta-annotated with
`@RequestMapping(method = RequestMethod.GET)` inside `spring-web`'s own compiled classes —
stays a hand-copied mapping table in the catalog, not a read; a `meta_annotations` capability
that scans dependency jars to replace it remains open (D02 §7).

**Phase 2E Tasks 8–9** ship the WebFlux functional-routing row above (`RouterFunctions.route()
.GET(…)`/`.andRoute(…)`/`.nest(…)`, Kotlin's `coRouter { "/p".nest { GET(…) } }`) through the
new `combinator` engine, walking the routing tree from its declared entry call rather than by
owner alone. Two more boundaries ride with it, beside the superclass one above: **predicate-
declared media is invisible** — `accept(...)`/`contentType(...)`'s `MediaType` vararg constants
compile through an `ANEWARRAY` the extractor's argument reader has no case for, so every
predicate-derived row's `consumes`/`produces` reads NULL even though a declaration
demonstrably exists on the call site (checkpoint F1) — a later extractor candidate, not a gap
in the engine; and **Kotlin functional handlers resolve to NULL** — Kotlin 2.2 compiles every
DSL handler, bound method reference and lambda alike, to an `instance`-kind argument naming a
compiler-generated class rather than a method symbol, so the honest answer is no handler
rather than a fabricated guess through that class's own `invokeSuspend` (checkpoint (1b)).

### 5.2 REST outbound

**Phase 2B shipped the first three; Phase 2C shipped the next four.** Feign, Retrofit and
Spring `@HttpExchange` are read as outbound annotation clients; `RestTemplate` is read by the
`single_call` engine and `RestClient`, `WebClient` and OkHttp by the `fluent` engine
reconstructing their builder chains — all from the same linked `call_site` facts, calls made
inside lambdas included. OkHttp's generic `Request.Builder.method(String, RequestBody)` verb
call is not readable — only the named verb methods (`get`/`post`/`put`/`patch`/`delete`/
`head`) derive. Everything else in this table remains unimplemented; the system tier still
has nothing to match against them.

| Language | Library | Shape | Tier |
|---|---|---|---|
| Java | Feign `@FeignClient`, Retrofit `@GET`, Spring `@HttpExchange` | `annotation` | ✅ shipped |
| Java | Micronaut `@Client`, MicroProfile `@RegisterRestClient` | `annotation` | A |
| Java | Spring 7 `ImportHttpServices` registration | `annotation` | A |
| Java | `RestTemplate` | `registration_call` | ✅ shipped |
| Java | `RestClient`, `WebClient`, OkHttp | `fluent_chain` | ✅ shipped |
| Java | JDK `HttpClient`, Apache HttpClient, `URL.openConnection()` | `fluent_chain` | B |
| Java | **Apache Camel** `from("kafka:orders").to("http://svc/api")` | `fluent_chain` over **URI strings** | **B — largest single payoff: protocol, direction and destination in one literal** |
| Go | `http.Get(url)`, `http.NewRequest(m, url, b)` + `client.Do` | `registration_call` / `fluent_chain` | A |
| TS | `fetch(url, {method})`, `axios.get(url)` (+ instance `baseURL`) | `registration_call` | A |
| Python | `requests.get(url)`, `httpx`, `aiohttp`, `urllib3.request("GET", url)` | `registration_call` | **A — the easiest outbound form in any language** |
| Rust | `reqwest` `client.get(u).send()`, `hyper` builder | `fluent_chain` | B |
| Swift | Alamofire `AF.request(url, method: .get)` | `registration_call` | A |
| Swift | `URLSession` + `URLRequest.httpMethod = "POST"` | **verb is a property assignment** — a shape seen nowhere else | `fluent_chain` | B |
| Any | Generated clients — `oapi-codegen`, `openapi-typescript`, `swift-openapi-generator` | read the OpenAPI document instead | artifact | A |

### 5.3 SOAP

Deferred by decision — *"can defer, not really that widely used"*. Listed for completeness.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | JAX-WS `@WebService`, `@WebMethod`, `@WebParam` | — | `annotation` | A |
| Java | Spring-WS `@Endpoint` + `@PayloadRoot(namespace, localPart)` | — | `annotation` | A |
| Python | `zeep`, `spyne` | client built from a WSDL URL at runtime | `runtime_dynamic` | B |
| Go | — | **no meaningful SOAP ecosystem** — hand-rolled XML if at all | — | — |
| TS | — | **no meaningful SOAP ecosystem** | — | — |
| Rust | — | **no meaningful SOAP ecosystem** | — | — |
| Swift | — | **no meaningful SOAP ecosystem** | — | — |
| — | WSDL / XSD documents | the actual contract | artifact | C (tier-2 artifact) |

Without WSDL reading, SOAP link matching falls back to structural comparison.

### 5.4 GraphQL

Better than expected: **A in almost every language.** Every ecosystem either declares
operations with annotations or ships an SDL file that *is* the contract. Remember that the
endpoint is the **field**, not `/graphql` — a schema with 200 fields is 200 boundaries behind
one HTTP route.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring GraphQL `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping`, `@BatchMapping` | code-first | `annotation` | ✅ shipped — all five, plus a class-level `@SchemaMapping(typeName)` scope the methods inherit (the method's own value winning) |
| Java | Netflix DGS `com.netflix.graphql.dgs.{DgsComponent, DgsData, DgsQuery, DgsMutation, DgsSubscription}` | code-first; the shorthands are equivalent to `@DgsData` | `annotation` | ✅ shipped, including `@DgsData(parentType, field)` |
| Java | MicroProfile GraphQL `org.eclipse.microprofile.graphql.{GraphQLApi, Query, Mutation}` (Quarkus) | code-first | `annotation` | ✅ shipped — `@Query`/`@Mutation` under the `@GraphQLApi` gate |
| Java | `graphql-java` schema-first — `.graphqls` + `RuntimeWiring` | **the SDL file is the contract** | artifact + `registration_call` | ✅ shipped — the SDL half. A root field no annotation implements derives at `declared` with a NULL handler; `RuntimeWiring` itself is not read |
| Go | `gqlgen` — schema-first, resolvers generated from `.graphql` | SDL is authoritative | artifact | A |
| TS | NestJS `@Resolver()` + `@Query()` / `@Mutation()` | code-first | `annotation` | A |
| TS | Apollo Server `typeDefs` (SDL) + a `resolvers` object; TypeGraphQL, Pothos | schema- or code-first | artifact / `annotation` | A |
| Python | Strawberry `@strawberry.type`, `@strawberry.field` | **code-first and fully typed** | `annotation` | A |
| Python | Graphene, Ariadne | class- or SDL-based | `annotation` / artifact | A |
| Rust | `async-graphql` `#[Object]`, `#[graphql(...)]` | code-first macros, readable by `syn` | `annotation` | A |
| Swift | Apollo iOS — client operations generated from `.graphql` documents | **outbound only** | artifact | A |

**The SDL file is the single best artifact in this document.** Where a project is
schema-first, the entire contract — every operation, every field, every type, nullability
included — sits in one readable file that is a build input. Prefer it over code inspection.

**Phase 2H ships all four Java rows: three annotation catalogs and the SDL reader.** A
root operation is `(graphql, query|mutation|subscription, <field>)` and a non-root
resolver is `(graphql, NULL, Type.field)` ([D01](components/D01-graph-schema.md) §3) — the
endpoint is the field, so the fixture's GraphQL surface yields twelve endpoint rows from
four controllers, two SDL files and four catalogs — eleven derived from annotations, one
from a root field the SDL declares that no annotation implements. Two
framework-neutral vocabulary forms carried it: a declared name that falls back to the
annotated construct's own name (all three frameworks declare their field attribute
`default ""`, which never reaches the class file), and a dotted composition of a scope and
that name. **DGS and MicroProfile rode both forms with zero further engine change**, which
is the phase's own acceptance test. `format_fixed: {graphql: json}` on all four catalogs
made the format ladder's rung 1 live for the first time.

The boundaries, each verified against the shipped code rather than assumed:

- **Every GraphQL row is inbound.** All four catalogs declare `direction: inbound`; no
  GraphQL client side is read in any language, DGS's and MicroProfile's included.
- **No Java-class↔SDL-type join is ever made.** Two shape universes now describe one
  service — Java classes from bytecode, SDL types from the schema — and matching them by
  simple name is a guess. An annotation-derived operation keeps its Java types (in a
  code-first service that IS the wire), an SDL-derived one carries SDL-type references,
  and where a schema names an identity an annotation also derived, the declared response
  is stamped and then re-answered by the handler's own signature. Cross-linking the two
  universes is comparison work with its own evidence — 2G's reserved `schema_name`→symbol
  seam, now with a second customer — and is left for the phase that earns it.
- **`RuntimeWiring`'s programmatic field registration is not read.** The SDL is taken as
  the contract; a field wired only in code and declared in no schema derives nothing.
- **A schema root is `src/main/resources/graphql` and nothing else** — Spring GraphQL's
  own convention, contributed beside `proto`/`avro`. Conventional directories only; a
  configured or non-standard location is invisible.
- **A resolver whose scope no annotation states derives NO row.** Spring infers a parent
  type from the resolver's parameter, which is a fact no annotation carries, so
  `@SchemaMapping(field = "orphan")` on a class with no `typeName` is refused rather than
  derived as the bare `orphan` — which would claim a root-operation-shaped identity.
- **`@DgsData(parentType = "Query")` renders verbless**, as `Query.field` rather than the
  root `(query, field)` its shorthand `@DgsQuery` derives. Saying "this parent type IS a
  root" needs a fourth vocabulary form nobody has asked for; a correctly-addressed
  verbless row is visible and honest, where a guessed root would not be.
- **MicroProfile `@Source` resolvers derive nothing.** MicroProfile names a non-root
  resolver's parent through a PARAMETER's own type, not through an attribute on the
  operation annotation — a genuinely different declaration shape that no shipped form
  reads.
- **A `@BatchMapping`'s shape columns carry the batching envelope, not the schema field's
  contract.** Its declared `Map<Parent, Value>` return and `List<Parent>` parameter are
  what root, because neither is a declared wrapper; the schema field it implements returns
  the value type, and the map is how one call answers many parents. Modelling a resolver's
  real contract (parent object in, field value out) is not attempted.
- **A custom SDL scalar stays open**: `scalar Long` states a name and nothing about the
  wire — its encoding lives in a coercer in the service's own code — so a field of that
  type is `object` with no shape reference, reported open rather than guessed as `string`.
- **A union type is a gap, not a shape.** A union is one of several types and this wire
  vocabulary has no word for that, so the file declaring one publishes nothing and is
  reported (`descriptors_not_interpreted`) rather than half-published. `extend union`,
  `extend enum` and `extend scalar` take the same answer.
- **An operations document is ignored outright** — neither shape nor gap. `.graphql` also
  spells the queries a client sends, and those are not a schema; a gap would report a file
  that is not missing anything, permanently, for as long as it sits beside the schema.
- **Federation directives are parsed as data and never interpreted.** No directive of any
  kind reaches a shape, a field or an endpoint; federation's meaning is deferred to the
  linking era.
- **Subscription transport is not resolved.** A `subscription` row's protocol is `graphql`;
  whether the service serves it over WebSocket or SSE is not read, and the operation is
  the identity either way.

### 5.5 WebSocket

The boundary is the **event name**, not the connection path. `socket.on("orderCreated")` is
matchable exactly like a Kafka topic; `/ws` on its own tells us nothing.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Jakarta WebSocket `jakarta.websocket.server.ServerEndpoint("/ws")` (was `javax.websocket.*` — **match both**) | annotation on the class; the value is a URI template | `annotation` | ✅ shipped for the **jakarta** spelling; javax is detection-only (below) |
| Java | Spring STOMP `@MessageMapping("/topic/x")`, `@SubscribeMapping` | annotation | `annotation` | ✅ shipped — class-level prefix composition, `@SubscribeMapping`, and `@SendTo` reply rows |
| Java | Spring `registerWebSocketHandlers(registry).addHandler(h, "/ws")` | programmatic — the path is a literal argument, not a chain | `registration_call` | ✅ shipped as a catalog, with **no live fixture surface** (below) |
| Go | `gorilla/websocket` `upgrader.Upgrade(w, r, nil)` | **the protocol is decided by a call *inside* the HTTP handler**, not by the route registration | `registration_call` in a body | B |
| TS | NestJS `@WebSocketGateway()` + `@SubscribeMessage("event")` | annotation | `annotation` | A |
| TS | `socket.io` `io.on("connection", s => s.on("event", cb))`, `socket.emit("event", d)` | string event names | `registration_call` | A |
| TS | `ws` `wss.on("connection", …)` | no event names — raw frames | `registration_call` | B |
| Python | FastAPI `@app.websocket("/ws")` | annotation | `annotation` | A |
| Python | Flask-SocketIO `@socketio.on("event")` | **event name in the annotation** | `annotation` | A |
| Python | Django Channels — `ws_urlpatterns`, `AsyncWebsocketConsumer` | routing module + class | `registration_call` + `interface_implementation` | B |
| Rust | `axum` — a `WebSocketUpgrade` extractor in the handler signature | **type name visible in the syntax** | `annotation`-like | A |
| Rust | `tokio-tungstenite` | manual | `registration_call` | B |
| Swift | `URLSessionWebSocketTask` | client only | `fluent_chain` | B |

**Phase 2H ships all three Java rows**, verbless like every messaging row —
`(websocket, NULL, <path-or-destination>)`, `method` NULL, the destination in `path`
([D01](components/D01-graph-schema.md) §3). `@ServerEndpoint` on the class is both the
marker and the path prefix, with `@OnMessage` supplying the handler symbol; a STOMP
class-level `@MessageMapping("/orders")` composes with a method's `@MessageMapping("/place")`
or `@SubscribeMapping("/board")` exactly as `@RequestMapping` paths do; and a `@SendTo`
handler derives its reply as a second, outbound row. STOMP payloads answer the format
ladder at rung 5 (`json`, `narrowed` — Spring's default converter with Jackson present).

Boundaries, each verified against the shipped code:

- **A raw WebSocket frame is untyped, and the row says so.** `jakarta-websocket.yml`
  deliberately declares no `request_body` block: `@OnMessage(String frame)`'s parameter is
  an opaque frame, not a declared contract, and the protocol offers no `@Payload`-shaped
  marker to tell one from the other. Shapes stay NULL and the format reads `unresolved`.
- **A negotiated subprotocol is not read** in any form, so nothing narrows that
  `unresolved`.
- **`javax.websocket` is detection-only.** The pre-Jakarta-EE-9 spelling is a package
  rename and nothing else, but `mapping.prefix_annotation` is SINGLE-valued and widening it
  is an engine change. `detect.coordinates` still names the javax artifact, so such a module
  is recognised as WebSocket-shaped; a `javax.websocket.server.ServerEndpoint` class in it
  derives no endpoint. Naming the javax `@OnMessage` without a matching javax prefix would
  not fail honestly — it would derive a *wrong* address, an empty prefix on a resolved row.
- **`@SendToUser` is not read as a reply destination.** The `reply` block's `annotation` is
  single-valued for the same reason. A `@SendToUser`-only handler falls into the branch an
  unannotated value-returning handler already takes — the honest `path` NULL, `unresolved`
  reply row — never a wrong destination. Proved over synthetic facts; no fixture surface.
- **A class-level array-valued prefix contributes element 0 only.** `@MessageMapping({"/a",
  "/b"})` on a class composes every method under `/a`; the second value is silently
  unavailable as a prefix. The same limitation `@KafkaListener` already carries, not a new
  one, and not exercised by the fixture.
- **`@MessageMapping` and `@SubscribeMapping` on ONE method is unexercised.** Nothing
  refuses it and nothing pins it; the fixture declares each separately.
- **The programmatic `addHandler` catalog has no live fixture surface.** It is proved over
  synthetic call facts only. Its `arity: 2` assumes the single-path call form compiles to
  exactly two call-site arguments, unverified against real bytecode, and a multi-path
  `.addHandler(h, "/a", "/b")` is a three-argument call the row does not match at all — no
  row rather than a wrong one.

### 5.6 Server-Sent Events

**The worst column in either matrix.** Nothing declares SSE. It is inferred from a return
type or from a media-type string, so the *same* route declaration is REST or SSE depending on
what the handler returns. This is the clearest case for making `protocol` a per-match
property — see §8.

| Language | Library | How it is actually detected | Shape | Tier |
|---|---|---|---|---|
| Java | Spring MVC — returns `org.springframework.web.servlet.mvc.method.annotation.SseEmitter` | **return type**; present since 4.2 and still in 7.x | return-type read | ✅ shipped — `hint_returns`, matched as the flat outer symbol |
| Java | WebFlux — returns `Flux<ServerSentEvent<T>>`, or `produces = MediaType.TEXT_EVENT_STREAM_VALUE` | return type **or** a `produces` string | return-type read | ✅ shipped — **both** evidence kinds; the marker is matched mid-chain |
| Java | JAX-RS — `@Produces(MediaType.SERVER_SENT_EVENTS)` + `SseEventSink` | **an annotation argument** — the one good case | `annotation` | A |
| Go | manual — `w.Header().Set("Content-Type", "text/event-stream")` then flush in a loop | **a bare string in the handler body.** No library, pure convention | `runtime_dynamic`-adjacent | **C** |
| TS | Express — `res.setHeader("Content-Type", "text/event-stream")` | string in the body | — | C |
| TS | Next.js / Hono streaming responses, `ReadableStream` | return type | — | B |
| Python | `sse-starlette` — returns `EventSourceResponse` | **return type** | return-type read | B |
| Python | FastAPI — `StreamingResponse(media_type="text/event-stream")` | constructor argument | `registration_call` | B |
| Rust | `axum` — returns `Sse<S>` | **return type**, visible in the syntax | return-type read | B |
| Swift | rare | — | — | — |

**The one cheap win:** `produces = "text/event-stream"` and `@Produces(SERVER_SENT_EVENTS)`
are annotation arguments we can already read. That catches a real share of JVM SSE endpoints
for the cost of a catalog entry, and is worth doing even though the return-type route is the
complete answer.

**Phase 2H took that win and the return-type route together.** Nothing declares SSE, so no
engine derives an `sse` row: an HTTP row is derived as HTTP and RECLASSIFIED, by the
`protocol_hint` pass ([D02](components/D02-catalog-schema.md) §2) running after the
engines' merge and before the format ladder. Two evidence kinds, media first — the row's
own `produces` naming `text/event-stream`, else a marker type appearing anywhere in the
handler's return-type generic chain. The pass changes `protocol` only: never `direction`,
never the row count, and only rows of the source protocol the declaring catalog owns.
The rendered identity keeps the HTTP verb and gains the protocol name —
`sse GET /events/stream` ([D06](components/D06-bundle-format.md) §5b).

Boundaries, each verified against the shipped code:

- **`text/event-stream` names the protocol and never the format.** It is the envelope, not
  the payload, so it is deliberately absent from `media_formats` and rung 2 passes it by.
  The per-event payload falls to rung 5 — `json`, `narrowed`, rendered `json (assumed)` —
  which is COVERAGE §4.1's "Assumed JSON per event" finally carrying its trust marker.
- **`ServerSentEvent<T>` unwraps to `T`.** It is the per-event envelope, declared as a
  wrapper, so `Flux<ServerSentEvent<OrderView>>` publishes `OrderView` as the contract and
  the envelope type appears nowhere in the document.
- **`SseEmitter`'s payload is unreachable, honestly.** It is a callback handle with no type
  argument to unwrap — the events are pushed through it at runtime — so the row is
  disclosed as an unexpanded open type rather than published as an empty contract.
- **Body-string SSE stays unshipped**, as §10 of the design states: the Go and Express form
  writes `Content-Type: text/event-stream` as a bare string inside the handler body, which
  needs `runtime_dynamic`-adjacent reading no engine has. C-tier, deliberately.
- **JAX-RS's `@Produces(SERVER_SENT_EVENTS)` is still A**, with that catalog. The
  mechanism is done; a JAX-RS catalog would carry its own `protocol_hint` block, since the
  block is scoped by the declaring catalog's protocol and a Quarkus module loads no Spring
  catalog to inherit one from. One YAML entry, no code.

### 5.7 gRPC

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | generated `FooGrpc.FooImplBase` implementing `io.grpc.BindableService`; stubs extend `Abstract{Async,Blocking,Future}Stub` | inheritance, not a call | `interface_implementation` | **B — the JVM is the outlier here** |
| Java | `net.devh.boot.grpc.{server.service.GrpcService, client.inject.GrpcClient}` | — | `annotation` | A |
| Java | Quarkus `io.quarkus.grpc.{GrpcService, GrpcClient}` | — | `annotation` | A |
| Java | Spring gRPC `org.springframework.grpc.server.service.GrpcService` | **the annotation is optional** — Spring gRPC exposes *any* `BindableService` bean, so `interface_implementation` is the reliable match and the annotation only adds interceptors | `annotation` + `interface_implementation` | A |
| Go | `pb.RegisterFooServer(s, impl)`, `pb.NewFooClient(conn)` | **the generated function names the service** | `registration_call` | A |
| Python | `_pb2_grpc.py`: `FooServicer`, `add_FooServicer_to_server`, `FooStub(channel)` | — | `registration_call` | A |
| Rust | `tonic` `FooServer::new(impl)`, `FooClient::connect(url)` | — | `registration_call` | A |
| TS | `@grpc/grpc-js` + `@grpc/proto-loader` `loadSync("foo.proto")` | **service built at runtime from a `.proto` path** | `runtime_dynamic` | **B — the path is a literal, so read the `.proto` as an artifact** |
| TS | `ts-proto`, `protobufjs` static mode | generated typed services | `generated_descriptor` | B |
| Swift | gRPC-Swift generated clients and providers; Connect-Swift | — | `registration_call` | A |

### 5.8 Kafka

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@KafkaListener` (`topics`, `topicPattern`), class-level `@KafkaListener` + `@KafkaHandler` included | — | `annotation` | ✅ shipped |
| Java | Micronaut `@KafkaListener`/`@KafkaClient` + `@Topic` | — | `annotation` | A |
| Java | `ReplyingKafkaTemplate.sendAndReceive(ProducerRecord)`, and a `@KafkaListener` method returning a value annotated `@SendTo` | the reply derives as its own outbound row | `registration_call` + `annotation` | ✅ shipped |
| Java | `KafkaTemplate.send(topic, …)`, `.sendDefault(…)` | — | `registration_call` | ✅ shipped |
| Java | `KafkaConsumer.subscribe(Collection<String>` \| `Pattern)` | `List.of` (≤10 elements) resolves per topic; `Collections.singletonList`/`Pattern.compile` resolve their one argument; `Arrays.asList` is genuine varargs and degrades to one unresolved row | `registration_call` | ✅ shipped |
| Java | **`KafkaProducer.send(ProducerRecord)`** | **topic is a constructor argument of `ProducerRecord`**, not of `send` | `fluent_chain` | ✅ shipped |
| Java | `KafkaTemplate.send(Message)` with topic in a header | topic read from a `setHeader(KafkaHeaders.TOPIC, …)` value-guarded step | `fluent_chain` | ✅ shipped |
| Java | **Spring Cloud Stream** functional `Consumer<T>`/`Supplier<T>` beans | topic in `spring.cloud.stream.bindings.<bean>-in-0.destination` | `config_join` | ✅ shipped |
| Java | **SmallRye** `@Incoming("orders")` / `@Outgoing` | channel in code, topic in `application.properties` | `config_join` | **B** — rides 2F's `config_join` once catalogued |
| Java | Alpakka / Pekko Connectors `Consumer.plainSource(s, Subscriptions.topics("t"))` | — | `registration_call` | B |
| Go | `segmentio/kafka-go` `kafka.NewReader(kafka.ReaderConfig{Topic: "t"})` | **topic is a struct-literal field** — easier than positional | `registration_call` | A |
| Go | `IBM/sarama` (was `Shopify/sarama`), `confluent-kafka-go` | **both import paths are live in the wild** — the module declared the Shopify path for a period after the move, so neither can be dropped | `registration_call` | A |
| TS | `kafkajs` `consumer.subscribe({topic})`, `producer.send({topic, messages})` | topic in an object literal | `registration_call` | A |
| Python | `confluent-kafka`, `kafka-python` `KafkaConsumer("topic", …)` | **topic is a constructor argument** | `registration_call` | A |
| Python | `faust-streaming` `app.topic("orders")` + `@app.agent(topic)` | — | `annotation` + `registration_call` | A |
| Rust | `rdkafka` `consumer.subscribe(&["topic"])`, `FutureRecord::to("topic")` | — | `registration_call` | A |
| Swift | `swift-server/swift-kafka-client` — a `librdkafka` wrapper with an async/await producer and an `AsyncSequence` consumer | **three years of development and no tagged release**; the tier is the detection cost, not an endorsement | `registration_call` | A |

`KafkaTemplate.send` returns `ListenableFuture` before Spring Kafka 3.0 and `CompletableFuture` from 3.0 on; 2.9 added a `usingCompletableFuture()` bridge that 3.0 removed.

A class-level `@KafkaListener`'s `topics` array contributes only its first element to any topic
identity. A method-level `@KafkaListener` nested inside a class already carrying one is not
unread territory — the engine's generic prefix-join rule (`coalesce(p.prefix,'') ||
m.path_suffix`) concatenates the class-level topic onto the method's own topic and derives a
confidently `resolved` row under a topic name nobody wrote: a known fabrication boundary, not
exercised by the fixture, slated for tightening alongside the empty-path wart below. Where a
class-level `@KafkaListener` does derive, every `@KafkaHandler` method on it derives its own row
against the shared topic identity — several payload contracts riding one topic is the deliberate
outcome, not a deduplication the engine owes anyone.

`KafkaTemplate.sendDefault`, `JmsTemplate.convertAndSend(Object)` with no destination and
`SqsTemplate`'s builder-lambda `send(Consumer<SqsSendOptions<T>>)` all put the destination
somewhere the engine cannot read a literal from, so each derives a real row with `path: NULL,
resolution: unresolved` — the same honesty rule OkHttp's un-named verb call established in §5.2,
never a fabricated name.

A listener annotation that puts its destination in an attribute the catalog does not list —
`@KafkaListener(topicPartitions = …)` here, `@SqsListener(queueNames = …)` in §5.10 beside the
shipped `value` alias — derives a resolved row with an **empty** path today rather than an
unresolved one; a known wart, slated for tightening rather than shipped as designed.

The scanner does not capture a parameter's own generic type arguments — only a return type's —
so a `ConsumerRecord<K, V>` payload parameter reads as honestly absent rather than resolving to
`V`, the same reason a `List<T>` parameter's element type never reaches `request_shape.item`.

A `KafkaConsumer.subscribe(Pattern)` call derives a resolved row whose `path` is the pattern's
own regex text, recorded verbatim — not an expanded list of the topics it might match. That is
an honest capture, never a guess, but it also means the row can never participate in a link
match against a concrete topic name on the wire: a `Pattern` subscription resolves and links
nothing.

`KafkaTemplate.send(Message)` derives two rows for the same call, deliberately.
`spring-kafka-message.yml`'s fluent chain resolves the topic from the `setHeader` guard above,
while `spring-kafka-template.yml`'s pre-existing `record_arg` row degrades the same call to a
path-NULL unresolved row, because a `Message` argument names no `record_wrappers` entry it can
read. Both rows stand — unresolved is an answer, never an omission — the same duplicate-row
ruling the co-located Pub/Sub `Publisher` case in §5.11 repeats. The resolved
`spring-kafka-message.yml` row still carries `resolution: unresolved` overall when the
message's own payload arrives as a bare method parameter rather than a `MessageBuilder`-visible
literal: a resolved topic identity next to an unresolved row is not a contradiction, it is two
separate facts about the same call — the destination is known, the payload capture is not. AWS
SQS's builder row (§5.10) carries the identical shape.

### 5.9 JMS and AMQP

JMS is a **Java specification**. The other languages have no equivalent — the `—` in §2 is
structural, not a gap. AMQP is the cross-language analogue and is listed here.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@JmsListener` (`destination`, `selector`, `subscription`, `concurrency`) | — | `annotation` | ✅ shipped |
| Java | Micronaut `@JMSListener` + `@Queue`/`@Topic` | — | `annotation` | A |
| Java | `JmsTemplate.send` / `convertAndSend` | — | `registration_call` | ✅ shipped |
| Java | Direct `jakarta.jms.{Session, MessageProducer, MessageConsumer}` | `createProducer`/`createConsumer` linked to `createQueue`/`createTopic` via `channel_via`; `send()` deliberately unread | `registration_call` | ✅ shipped |
| Java | `@RabbitListener`, `@PulsarListener` | — | `annotation` | A |
| Go | `rabbitmq/amqp091-go` (was `streadway/amqp`) `ch.Publish(exchange, key, …)` | — | `registration_call` | A |
| TS | `amqplib` `ch.publish(exchange, key, …)`, `ch.consume(queue, cb)` | — | `registration_call` | A |
| Python | `pika`, `kombu` `channel.basic_publish(exchange, routing_key, …)` | — | `registration_call` | A |
| Swift | — | **no JMS or AMQP client in common iOS use** | — | — |
| Rust | `lapin` `channel.basic_publish(…)` | — | `registration_call` | A |

**Package change:** `javax.jms` (Spring ≤5 / Boot ≤2) → `jakarta.jms` (Spring 6 / Boot 3+).
Both must be matched.

**Queue versus topic is invisible here by construction.** Kind is configured on the container
factory, not written beside the destination expression the code actually carries, so identity is
the destination expression alone — a `@JmsListener(destination = …)` row derives with no way to
say whether it names a queue or a topic, which is a fact about where JMS puts that decision, not
a gap in the catalog. Direct `jakarta.jms.{Session, MessageProducer, MessageConsumer}` ships as
a `single_call` catalog: `createProducer`/`createConsumer` each link to their own
`createQueue`/`createTopic` call through `channel_via`, and `send()` is deliberately never read
— a raw `jakarta.jms.Message` is an opaque envelope no rule can pull a payload out of, so the
registration call itself is the evidence that a route exists, not the call that later uses it.

### 5.10 AWS SQS

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring Cloud AWS 3.x `io.awspring.cloud.sqs.annotation.SqsListener`, `SqsTemplate` | — | `annotation` | ✅ shipped |
| Java | Spring Cloud AWS 2.x `io.awspring.cloud.messaging.listener.annotation.SqsListener` | **different package** | `annotation` | A |
| Java | Spring Cloud AWS 1.x/2.2 `org.springframework.cloud.aws.messaging.listener.annotation.SqsListener` | **a third generation**, under the old `org.springframework.cloud` group | `annotation` | A |
| Java | AWS SDK v2 `SqsClient.sendMessage(SendMessageRequest)`, `…builder().queueUrl(u)` | `SendMessageRequest.builder()` root, `queueUrl`/`messageBody` steps, `build` reaches `sendMessage` | `fluent_chain` | ✅ shipped |
| Go | `aws-sdk-go-v2` `client.SendMessage(ctx, &sqs.SendMessageInput{QueueUrl: …})` | struct literal | `registration_call` | A |
| TS | `@aws-sdk/client-sqs` v3 `client.send(new SendMessageCommand({QueueUrl}))` | **command classes are real, statically visible types** | `registration_call` | A |
| **Python** | **`boto3`** `boto3.client("sqs").send_message(QueueUrl=…)` | **clients synthesised at runtime from JSON service models — `send_message` is defined in no Python file** | `runtime_dynamic` | **C — ceiling is a `name_match` on the service string; `resolution: narrowed` at best** |
| Rust | `aws-sdk-rust` `client.send_message().queue_url(u).send()` | — | `fluent_chain` | B |
| Swift | `Soto`, the community AWS SDK for Swift — actively maintained, Linux/macOS/iOS | `sqs.sendMessage(.init(queueUrl: …))` | `registration_call` | B |
| Java | Micronaut | **no first-party annotations** — raw SDK or `micronaut-jms-sqs` | — | B |

Raw AWS SDK v2 `SqsClient` ships as a `fluent` catalog reaching `SqsClient.sendMessage` through
the OkHttp `terminal_via_argument` pattern verbatim. Its `queueUrl` capture is the one messaging
surface in this document that resolves through `url`, not `channel`: SQS's queue URL is a
genuine `https://sqs.<region>.amazonaws.com/<account>/<queue>` address by AWS's own API design,
so CP-2 splits it into `peer` and `path` exactly as an HTTP client's absolute URL would — every
other messaging destination in §5.8-§5.11 stays a `channel`, recorded verbatim, with `peer`
always NULL. The resolved row still carries `resolution: unresolved` when `messageBody`'s own
argument is a bare method parameter rather than a captured literal: a resolved queue identity
next to an unresolved row, not a contradiction — two separate facts about the same call, the
same shape `KafkaTemplate.send(Message)` carries in §5.8.

### 5.11 Google Cloud Pub/Sub

The hardest protocol in the table: **B in every language**, because only Micronaut ships a
first-party annotation — Java's own `PubSubTemplate.publish`/`subscribeAndConvert` calls are now
the exception, read directly with no annotation at all.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | **Micronaut `@PubSubClient` / `@PubSubListener` + `@Subscription`** | the only first-party annotation surveyed | `annotation` | A |
| Java | Spring Cloud GCP `PubSubTemplate.publish(…)`, `.subscribeAndConvert(…, Class<T>)` | typed direct calls, not the channel-adapter indirection below | `registration_call` | ✅ shipped |
| Java | `Publisher.newBuilder(TopicName.of(p, t)).build()`, `.publish(…)` | co-located build+publish chains resolve; a config-built/field-held `Publisher` derives an honest unresolved row instead of vanishing | `fluent_chain` | ✅ shipped |
| Java | `Subscriber` + `MessageReceiver`, `.startAsync()` | named implementers and lambda receivers both resolve; direct implementers only, and the registration is the evidence | `interface_implementation` | ✅ shipped |
| Java | Spring Cloud GCP `PubSubTemplate.subscribe(…)`, or `PubSubInboundChannelAdapter` + `@ServiceActivator` | channel indirection | `config_join` | B — rides 2F's `config_join` once catalogued |
| Go | `client.Topic("n").Publish(ctx, m)`, `client.Subscription("s").Receive(ctx, fn)` | — | `fluent_chain` | B |
| TS | `pubsub.topic("n").publishMessage(…)`, `subscription.on("message", cb)` | — | `fluent_chain` | B |
| Python | `publisher.publish(topic_path, data)`, path built by `publisher.topic_path(proj, t)` | topic assembled from a helper call | `fluent_chain` | B |
| Rust | `google-cloud-pubsub` (official `googleapis/google-cloud-rust`) | **publish only — receiving messages is not implemented**, and the crate is pre-GA with breaking changes expected. So Rust Pub/Sub has no inbound side to detect at all | `fluent_chain` | B |
| Swift | — | **no first-party or mature community Swift client** | — | — |

Spring Cloud GCP moved to Google's own repository **at version 2.0**, renaming packages `org.springframework.cloud.gcp.*` → `com.google.cloud.spring.*` and the Maven group `org.springframework.cloud` → `com.google.cloud`. Both generations are in the wild.

The raw `Publisher`/`Subscriber` clients ship as three catalogs. `google-pubsub-publisher.yml`
resolves the co-located `Publisher.newBuilder(TopicName.of(...)).build().publish(...)` chain via
`channel_via`; a `Publisher` built elsewhere and merely held in a field — config, a `@Bean` —
has no chain for that catalog to walk, so `google-pubsub-client.yml`'s `single_call` sibling
derives the same call as an honest path-NULL unresolved row rather than letting it vanish, and
where both catalogs match the same co-located call, both rows stand — the same deliberate
duplicate-row pairing §5.8 states for `KafkaTemplate.send(Message)`. `google-pubsub-subscriber.yml`
is the `interface_implementation` style's own shipped example: a named class implementing
`MessageReceiver` and a lambda receiver both resolve through the same registration join, but
only a class's own direct interfaces match — a subclass of an implementing class is a stated
one-hop limitation, not a gap to close later — and a `MessageReceiver` implementation never
handed to `Subscriber.newBuilder` derives nothing at all, because the registration is the
evidence, never the class's shape alone.

**Every messaging peer is NULL except one.** A broker address, a queue URL or a GCP
project/topic pair is usually configuration, not code — `peer` stays NULL on every Kafka,
JMS and Pub/Sub row, a different question from the DESTINATION Spring Cloud Stream's own
`config_join` catalog now resolves (§5.8): a broker's connection address is never what a
binding key names. Phase 2F gave a DECLARED outbound HTTP base the analogous treatment
(§5.2) — a directly-read field, a constructor parameter or an `@ConfigurationProperties`
class climbs the field ladder to a real `peer` — but no messaging catalog reaches a
broker's own connection address the same way; that stays a gap (§2's "does not give
you" table). AWS SQS's raw `SqsClient` catalog (§5.10) is the one exception either phase
ships: its queue URL is a genuine HTTP-style address by AWS's own design, so it resolves
a real `peer` today, the same way OkHttp's absolute `Request.Builder#url` does.

### 5.12 Async and internal boundaries

Not protocols, but genuine entry points that would otherwise fall out of the checklist.

| Language | Mechanism | Shape | Tier |
|---|---|---|---|
| Java | `@Scheduled`, Quartz | `annotation` | A |
| Java | Temporal / Cadence `@WorkflowInterface`, `@ActivityInterface` | `annotation` | A |
| Java | **Vert.x event bus** `vertx.eventBus().send("addr", m)` / `.consumer("addr", h)` | in-process pub/sub with **string addresses**, matchable like topics | `registration_call` | B |
| Java | Spring Integration `@ServiceActivator`, `@InboundChannelAdapter` | channels, not destinations | `config_join` | B — rides 2F's `config_join` once catalogued |
| Java | **Akka / Pekko actor messaging** `ref ! msg`, `ref.tell(msg)` | receiver comes from an `ActorRef` created elsewhere | — | **C, possibly permanent — see §7** |
| Python | **Celery** `@app.task`, `task.delay(…)`, `.apply_async(queue=…)` | a real async boundary, easy to miss | `annotation` | A |
| TS | `bullmq` `new Queue("n")`, `new Worker("n", fn)` | string names, matchable like topics | `registration_call` | A |
| Go | `robfig/cron` `c.AddFunc("@hourly", fn)`; Temporal Go SDK `w.RegisterWorkflow(fn)` | `registration_call` | A |
| Go | `asynq`, `machinery` task queues — `mux.HandleFunc("task:name", h)` | `registration_call` | A |
| Rust | `tokio-cron-scheduler` `Job::new("0 * * * * *", fn)` | `registration_call` | A |
| Rust | Temporal Rust SDK — `register_workflow::<T>()`, `register_activities()`; **public preview, API still evolving** | `registration_call` | A |
| Rust | `apalis` — worker pulls from a Postgres/Redis/SQLite backend | `registration_call` | B |
| Python | APScheduler `@scheduler.scheduled_job("cron", …)` | `annotation` | A |
| Swift | `BGTaskScheduler.register(forTaskWithIdentifier:)` — identifiers also declared in `Info.plist` (§6) | `registration_call` | B |
| Any | Database access — Room `@Query`, JPA repositories, ORM models | a data boundary, not a protocol | `annotation` | B |

---

## 6. Not on the protocol axis — platform boundaries

Mobile inverts the assumption the rest of the project rests on. A service has inbound
endpoints; **an app is nearly all outbound**, and its inbound boundaries are not HTTP at
all. These need new `protocol` values, not new columns in §2.

| Platform | Boundary | Declared in | Shape | Tier |
|---|---|---|---|---|
| Android | **Deep links / App Links** | `AndroidManifest.xml` `<intent-filter>` + `<data scheme host pathPrefix>` | artifact (XML) | B |
| Android | Exported activities, services, receivers | manifest `android:exported="true"` | artifact | B — **also the primary attack surface** |
| Android | Content providers | manifest `<provider android:authorities>` + subclass | artifact + `interface_implementation` | B |
| Android | Push | `FirebaseMessagingService.onMessageReceived` | `interface_implementation` | B |
| Android | Background work | `WorkManager` `Worker` subclasses | `interface_implementation` | B |
| Android | **Retrofit** `@GET("users/{id}")` (outbound) | interface annotations | `annotation` | **A — highest-value Android catalog** |
| iOS | Custom URL schemes | `Info.plist` `CFBundleURLTypes` | artifact | B |
| iOS | **Universal Links** | `apple-app-site-association` — **lives on the server, outside the app repository** | artifact | C — cross-repository join |
| iOS | App Intents / Siri — `AppIntents` framework, iOS 16+ | structs conforming to `AppIntent` with a `perform()` method; **they live in the main binary**, not an extension | `interface_implementation` | B |
| iOS | Push, share extensions, background tasks | delegate methods, `NSExtension` keys, `BGTaskScheduler` ids | mixed | B |

**Android needs no new scanner.** The build emits ordinary JVM `.class` intermediates
before D8 dexes them, and the Android Gradle Plugin's own instrumentation API takes an **ASM
`ClassVisitor`** over exactly those files. Point the scanner at the intermediates and our
extractor works unchanged. Android-specific features are **post-MVP by decision**; the work
is catalogs and an `AndroidManifest.xml` reader, not a scanner.

---

## 7. Cross-cutting findings

### Boundaries are leaving the code

The clearest pattern in the research, and the thing most likely to limit Sextant's value
over time. **Modern frameworks move destinations out of annotations and into
configuration**, leaving only an opaque name in the code:

| Framework | In the code | Where the destination actually lives |
|---|---|---|
| Spring Cloud Stream | a `Consumer<T>` bean named `handleOrder` | `spring.cloud.stream.bindings.handleOrder-in-0.destination` |
| Quarkus / SmallRye | `@Incoming("orders")` | `mp.messaging.incoming.orders.topic` |
| MicroProfile REST Client | `@RegisterRestClient(configKey="orders")` | `orders/mp-rest/url` |
| Django | a view function | `urls.py`, in a different module |

An annotation-only reader sees `handleOrder-in-0` and learns nothing. **For these frameworks
the code-to-configuration join is not an optimisation — it is the only path to the answer.**
Sextant is well placed for it (configuration resolution is already a first-class pass, and
endpoints carry *expressions* rather than values), but no catalog style expresses "the
destination is a property key derived from this bean's name". That is a gap in
[D02](components/D02-catalog-schema.md), not a missing catalog file.

### Akka and Pekko are a silent doubling

Lightbend moved Akka to the Business Source License from 2.7; **Apache Pekko** is the
Apache-2.0 fork of Akka 2.6.x, renaming `akka.*` → `org.apache.pekko.*` and `alpakka` →
`connectors` (`akka.stream.alpakka.jms` → `org.apache.pekko.stream.connectors.jms`). **Every
Akka matcher needs a Pekko twin**, and the split runs through the middle of the Scala/JVM
ecosystem.

### Actor messaging may be permanently invisible

`ref ! msg` is a real call edge — control and data cross it — but the receiving actor is
determined by an `ActorRef` created elsewhere, often from configuration or a router. CHA
cannot see through it, and neither can RTA or VTA. **In a heavily actor-based system most of
the call graph is invisible to any static tool**, ours included. If we support Akka we must
say so in the coverage report rather than presenting a confident but hollow graph.

### The typing problem in Python and JavaScript

**The types exist exactly where the framework needed them.** The frameworks hardest to
type-erase are those that cannot function without declarations — FastAPI builds validation
and OpenAPI from annotations, NestJS DTOs carry `class-validator` decorators, tRPC
procedures *are* a `zod` schema, Fastify routes take a JSON Schema. Payload coverage
correlates with **framework modernity, not language**. The right response is `resolution`
per endpoint, which [D00](components/D00-fact-schema.md) already supports — not one verdict
per language.

**"Python is typed now" is false at our granularity.** A 2026 ICPC study of **1,000 popular
GitHub repositories** found that **91% use type hints at least once, but half cover only 13.6%
of their members**; among libraries using them systematically, median coverage is 45.8% of
parameters and 35.9% of returns.

**Benchmark evidence sets the LLM boundary.** An empirical study of 24 LLMs (arXiv
2410.00603) against TypeEvalPy and SWARM-CG/SWARM-JS found that **traditional static
analysis consistently beat every model on call graphs** (`PyCG` for Python, `Jelly` for
JavaScript — models "struggle with completeness and soundness"), while **LLMs clearly beat
static tools on Python type inference** (surpassing `HeaderGen` and `HiTyper`). This maps
onto machinery we already have:

| Task | Method | `evidence` | `precedence` |
|---|---|---|---|
| Call edges, dispatch, reachability | Static analysis | `syntax` / `compiler` | 50 |
| Payload fields, types, optionality | LLM, where declarations are absent | `llm` | 10 |
| A destination behind a configuration key | Catalog rule, **verified** by an LLM, corrected by a human | `declared` / `llm` / `human` | 50 / 10 / 90 |

**The operating rule: an LLM may propose a shape, and may verify a derivation; it may never
be the sole source of anything that creates a link.** An invented field is a visible,
checkable error a human overlay corrects at precedence 90. An invented call edge silently
corrupts blast radius — the thing the tool exists to compute — and nothing downstream would
catch it.

**The third row needs its boundary drawn carefully**, because it is the case where the rule
above is easiest to violate by accident. The benchmark finding concerns *call graph
construction inside a program*, where `PyCG` and `Jelly` are demonstrably better than a model.
Joining a bean name to a configuration key is not that: there is no static competitor beyond
reading the configuration, which we already do. So an LLM there is filling a gap rather than
losing to a better method — but a destination is part of a wire identity, so a wrong one does
not produce an odd-looking field. It produces **a confident link between two services that do
not talk to each other.** Hence verification rather than derivation
([D02](components/D02-catalog-schema.md) §2d): where an LLM is nonetheless the only source,
the endpoint carries `evidence: llm` and every link built on it inherits that precedence.

`PyCG`, `Jelly`, `TypeEvalPy` and `SWARM-CG` also give us **published benchmarks to measure
our own output against**, rather than asserting quality.

### JSpecify lands in an attribute we now read

Spring 7 adopts JSpecify (`org.jspecify.annotations.*`), which is `TYPE_USE` with
`RUNTIME` retention — so it lands in `RuntimeVisibleTypeAnnotations`. **Shipped in Phase
2A**: the scanner reads both retention tables, and `visitTypeAnnotation` carries `type_path`
so `@Nullable List<String>` and `List<@Nullable String>` stay apart. Nullability feeds
`nullable` per reference — never `required`, which comes from presence machinery
([D00](components/D00-fact-schema.md) §5b) — and gates honest shape comparison.
`org.springframework.lang.Nullable` is deprecated but still present in compiled code — the
catalogs match both FQNs, alongside the `javax`/`jakarta`/JetBrains spellings.

---

## 8. Open questions

Recommendations included. Items marked **needs a decision** change how the table is built.

**Q1 — Is a tier relative to the JVM's engine or to each language's baseline? needs a decision.**
Recommend **per-language baseline** (§1). Measured against the JVM, every non-JVM cell is B
and the column carries no information. Measured against each language's baseline, `gin` is A
and Go's Pub/Sub is B — which is the distinction we actually want when planning work.

**Q2 — Do Avro and Protobuf belong on the protocol axis? resolved — separated entirely.**
No, and not as a parallel coverage axis either. Format is a **property of a channel that has
to be inferred**, in two steps: detect what is on the wire, then bind the spec that describes
it (§4). In that framing Protobuf and Avro are no different from JSON or XML — the only
reason they seemed different is that we were **silently assuming JSON for REST**, which is
not necessarily true and was not recorded as an assumption. §4 now covers detection evidence
per protocol, spec binding per format, and the consequences: assumed formats must not carry
observed-format trust, and proto3's lowerCamelCase JSON mapping renames every field on a
transcoded wire.

**Q3 — HTTP versus REST as separate columns? resolved.**
Neither. **HTTP is a transport; the axis is the application protocol running on it** — REST,
SOAP, GraphQL, WebSocket, SSE, gRPC (§1). That distinction is load-bearing rather than
cosmetic: four of those protocols put **one HTTP path in front of many logical operations**,
so a model that stopped at the HTTP route would report "1 endpoint" for a service exposing
200 GraphQL fields. Direction still earns two columns for REST, where the tiers genuinely
diverge.

**Q4 — Does "pubsub" mean the GCP product or the publish-subscribe pattern? resolved.**
The **GCP product** — messaging middleware to support alongside Kafka, JMS and SQS, not the
publish-subscribe pattern in general. **SNS and Redis are explicitly out of scope** for now;
they are absent by decision, not by oversight, and would each be a new column when wanted.

**Q5 — Is direction a third dimension? resolved — no.**
Except for REST, where the tiers genuinely diverge: inbound is `annotation`-shaped and mostly
cheap, outbound is `fluent_chain`-shaped and mostly not, so it earns two columns. For Kafka,
JMS, SQS and Pub/Sub, producer and consumer sit in the same library at the same tier, so
direction belongs in the library row.

**Q6 — What does a cell mean when it holds several libraries at different tiers? resolved — carry all of them.**
A cell shows the **count at each tier** (`4A 3B 2C`), not a headline. A single tier hides
exactly what the checklist exists to reveal: Java + Kafka is genuinely cheap for
`@KafkaListener` and much harder for Spring Cloud Stream, and both facts matter when
planning. Each column header links to the §5 subsection holding the named libraries, where
rows are grouped by language — §2 answers "how much work, and is something hiding here", §5
answers "what exactly do I build". The matrices are **generated from §5** by
`scripts/coverage_matrix.py`, so the two cannot disagree, and `--check` fails if they drift.
A `·` marks a cell §5 has no rows for — *not yet enumerated*, distinct from `—`, which means
we looked and it does not exist.

**Q7 — How do we stop this document drifting from reality? partly resolved; the rest needs a decision.**
Done for §2, which is now **generated from §5** by `scripts/coverage_matrix.py`; `--check`
fails if they have drifted. The open part is whether to go further and derive the *tiers*
too. Evidence says yes: the rule in §2's "Why the tiers are consistent" reproduces the
hand-assigned tier for 86% of 183 rows, and the disagreements were mostly **our own
inconsistency** rather than rule failure — four Java `registration_call` rows had been marked
A while three identical-shaped rows were marked B. Deriving tiers found them; hand-reading
would not have.

The remaining choice is where the source data lives. §5's markdown tables already parse
cleanly, so the incremental value of moving to YAML is narrow: a tier that recomputes when a
capability ships, and queryability from the CLI. Against it, the *notes* carry much of this
document's value ("the topic is a constructor argument of a different object") and they read
badly in YAML. **Recommend keeping §5 as markdown and adding shape→tier derivation as a
`--check` rule**, so an inconsistent tier fails the check the way a stale matrix does. Revisit
a YAML registry only if a second language's checklist makes the tables unwieldy.

**Q8 — Do the per-language files now duplicate §5?**
Partly, and deliberately: §5 owns the **judgment** (tier, status) and the language files own
the **essay** (toolchain verdict, payload handling, structural oddities such as Django's
`urls.py`, Next.js filesystem routing, `boto3`). No fact carries a tier in two places. If Q7
lands, §5 becomes generated and the essays stay hand-written.

**Q9 — Can `protocol`, `direction` and `format` stay properties of the catalog? resolved — no, they become per-match with a catalog default.**
Recorded in [D02](components/D02-catalog-schema.md) §2c. Reading D02 to make the change
corrected part of the question: **`protocol` was already handled.** The reserved
`protocol_hint` reclassifies endpoints other engines produced, so a `@GetMapping` returning
`Flux<ServerSentEvent<T>>` was always going to be reclassified as SSE. **Phase 2H built it
and corrected the trigger this answer named**: `wrappers`' `semantics: streaming` is not it,
because `Flux` carries that on every reactive route in a WebFlux service and reclassifying
all of them would rename ordinary REST as SSE. The real triggers are a declared
`text/event-stream` in `produces` and a named marker type anywhere in the return type's
generic chain (`hint_media`/`hint_returns`, [D02](components/D02-catalog-schema.md) §2). It
also shipped as a resolve pass rather than an engine — after the merge, before the format
ladder — not "last with `config_join`".

Two things genuinely needed the change, and one part of the original proposal was wrong.
**`direction` cannot be a later pass.** D02 §3 runs inbound before outbound so a path a module
both exposes and calls merges into `direction: both`; a pass that changed direction afterwards
would arrive after that merge and corrupt it. Direction resolves **at match time**.
**`format` had no home in the schema at all** — §4's whole analysis, including the assumed-JSON
problem and Kafka serializers, had nowhere to live. It is now a catalog default with per-match
resolution, and a default that survives unchallenged is recorded at `evidence: declared`
rather than at an observed level.

### Design questions raised by this research

Each of these blocked a whole family of frameworks rather than one library, and all three are
now settled. Recorded here because the reasoning matters more than the outcome.

1. ~~The unit of a boundary where one address carries many operations~~ — **resolved**:
   the operation is the endpoint, the address stays on it as `path`,
   [D01](components/D01-graph-schema.md). Aggregation is possible and disaggregation is not,
   so recording operations still allows one arrow per service; recording only the address
   could never answer *who calls `getOrder`*. The cost lands on rendering, not the schema.
2. ~~Config-derived destinations~~ — **resolved**: catalog vocabulary is primary
   ([D02](components/D02-catalog-schema.md) §2d), an LLM verifies the join, a human curation
   settles what neither can. Framework knowledge belongs in data — five rules written once
   beat every user writing them per project — and pushing it onto users is what the
   architecture says it will not do. The open risk is expressiveness: Spring Cloud Stream's
   binding name depends on the functional interface and can be overridden wholesale, and a
   catalog format that needs conditionals to express that has stopped being data. Logged in
   D02 §7.
3. ~~Filesystem-derived paths~~ — **resolved**: read the build's own route manifest where
   it exists, fall back to a directory walk recorded as `partial`, with LLM verification and
   human curation on top ([D02](components/D02-catalog-schema.md) §2, `filesystem` style).
   A manifest is not an artifact the build *consumes* — it is one the build *produces*, which
   puts it in the same category as bytecode, so this is an instance of our approach rather
   than an exception to it. The fallback is cheaper than it looks: a manifest yields paths
   only, so the source must be read for handlers and types either way.

**All three are now resolved**, along with context-dependent `direction`, `protocol` and
`format` ([D02](components/D02-catalog-schema.md) §2c). What remains open is not a shape the
schema cannot express but a question of how much expressiveness the catalog format can absorb
before it stops being data — logged in D02 §7.

**Answered elsewhere by §4:** [M06](components/M06-stitcher.md) asks how shapes are compared
when the two sides use different serialisation formats. §4.3 answers it — comparison is valid
only within a format or across a known projection, and proto3's lowerCamelCase JSON mapping is
the concrete case that makes the projection non-identity.

**Two limits belong in the product, not in a discovery by users.** Actor messaging is largely
invisible to static analysis, and `runtime_dynamic` boundaries — `boto3`, DRF routers,
`@grpc/proto-loader` — are not gaps we will close later. They are boundaries that do not exist
statically, and the coverage report has to say so.

---

## 9. Verification status

Researched against primary sources in August 2026 and **re-verified end to end**: every fully
qualified name, package relocation and maturity claim below has been traced to the library's
own documentation, javadoc, or repository. Three checks changed an answer rather than
confirming one.

**A third generation of `@SqsListener`.** Spring Cloud AWS has had the annotation in
`org.springframework.cloud.aws.messaging.listener.annotation` (1.x/2.2, old Maven group),
`io.awspring.cloud.messaging.listener.annotation` (2.x) and
`io.awspring.cloud.sqs.annotation` (3.x). A catalog matching two of the three silently misses
the rest.

**Rust Pub/Sub has no inbound side.** The official `google-cloud-pubsub` crate is pre-GA and
**does not implement receiving messages**, so there is nothing to detect on the consumer side
at all — a stronger statement than the unverified "maturity unknown" it replaces.

**Swift does have a Kafka client.** `swift-server/swift-kafka-client` wraps `librdkafka` with
an async/await producer and an `AsyncSequence` consumer, contradicting the earlier claim that
none existed — though it has three years of commits and no tagged release.

Two further details were sharpened. Spring gRPC's `@GrpcService` is **optional** — Spring
gRPC exposes any `BindableService` bean, so the supertype is the reliable match and the
annotation only adds interceptors. And the `sarama` move left **both import paths live**,
because the module declared the Shopify path for a period after moving to IBM.

The research citations were traced to their sources: the Python typing figures come from an
ICPC 2026 study of **1,000 popular GitHub repositories**, and the LLM benchmark findings from
the arXiv abstract for 2410.00603.

`⚠️` now appears nowhere in this document outside the legend. If it returns, it marks a claim
that has not been checked — and a wrong annotation name does not fail loudly, it silently
matches nothing.
