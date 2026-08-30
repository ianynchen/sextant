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
| `interface_implementation` | A type's supertype | gRPC `FooImplBase`, `MessageReceiver` |
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
now resolved per match against a catalog-level default, along with `format` —
[D02](components/D02-catalog-schema.md) §2c.

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
`@HttpExchange` and Retrofit `@GET` — carrying the same payload contract, and a module's full
analysis exports as a self-describing D06 bundle. Four of the designed scanner capabilities
are implemented: `annotation_args`, `typed_signatures`, `type_annotations` and
`kotlin_metadata`. Verified end-to-end on spring-petclinic: 17 endpoints, byte-identical
across runs.

**Everything else in both matrices is a gap.** In particular, per Q1 a tier in a row whose
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
  `@Controller`; outbound Feign, `@HttpExchange`, Retrofit), each with its wire identity,
  handler and/or caller, `peer` where the code declares one, and its request and response
  payload descriptors; `shapes`/`shape_fields` holding every reachable payload field by
  field — wire name, wire type and format, `required`, `nullable`, trust fields — with
  known types mapped and expansion stopping visibly at unknown ones. A path the module
  both exposes and calls is one endpoint, direction `both`.
- **`architecture.md`** — coverage, a Mermaid contract class diagram, per-endpoint
  contract tables for inbound, an outbound table with peers, and a Known-gaps section
  naming every omission below.
- **`metadata.json` and a D06 bundle** — the machine-readable summary, and a portable
  directory of Parquet tables plus a manifest carrying versions, catalog hash, coverage
  and the same gaps, byte-identical on every re-run of the same inputs.

What a run does **not** give you, each entry named in the output's own gap list rather
than silently absent:

| You do not get | Because | Arrives with |
|---|---|---|
| Kafka/JMS/SQS listeners **or** producers | no messaging catalog and no non-HTTP wire identity yet (`messaging_endpoints_not_read`) | Phase 2D |
| Sequencing between reactive/lambda calls (`flatMap`, `map`) | calls inside them derive endpoints, but the sequence between those calls awaits the call graph (`reactive_flow_not_traced`) | call-graph phases |
| Sequence diagrams, traces, a call graph | no `call_site`/control-flow facts (`sequence_diagrams_pending_call_graph`, `call_graph_not_implemented`) | call-graph phases |
| A full class diagram (inheritance) | only contract types are drawn (`structure_diagram_limited_to_contracts`) | with the `edges` table |
| Outbound base addresses for `@HttpExchange`/Retrofit | they live in builder code (`client_base_addresses_not_resolved`); `peer` is NULL there | Phase 2C |
| Cross-service links or a system document | linking is a system-scope pass over bundles; no `participants`/`links` exist yet | linking phase |
| WebFlux functional routes, meta-annotations, inherited mappings, nested classes | unimplemented forms, each listed in §5 | per their tiers |
| Trustworthy analysis of a POM using parents/profiles/interpolation | the detector reads `pom.xml` raw (`maven_parent_and_profile_resolution_not_implemented`) | undecided |

Two honesty caveats also ride every output: a merged `both` endpoint keeps only the
handler's declared contract (`merged_endpoints_keep_only_the_handlers_contract`), and a
payload type reachable from several catalogs is expanded under the first catalog's rules
(`shape_rules_unscoped_to_the_producing_catalog`) — the shipped catalogs declare
compatible rules, so no answer differs today.

### 2a. Application protocols over HTTP

| Language | Scanner | [REST in](#51-rest-inbound) | [REST out](#52-rest-outbound) | [SOAP](#53-soap) | [GraphQL](#54-graphql) | [WebSocket](#55-websocket) | [SSE](#56-server-sent-events) |
|---|---|---|---|---|---|---|---|
| **Java / Kotlin** | ✅ ASM | ◐ 6A 7B 5C | ◐ 2A 3B | 2A | 4A | 2A 1B | 1A 2B |
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
| **Java / Kotlin** | 3A 1B | 2A 7B | 3A 2B | 3A 2B | 1A 3B | 2A 2B 1C |
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

Evidence quality varies enormously by protocol. Three regimes:

| Protocol | How the format is declared | Evidence | If nothing is declared |
|---|---|---|---|
| **gRPC** | **Fixed by the protocol** | `compiler` | Protobuf, always. The only certain cell in this table. |
| SOAP | Fixed | `compiler` | XML |
| GraphQL | Fixed | `compiler` | JSON |
| **REST in** | `produces` / `consumes`, JAX-RS `@Produces` / `@Consumes`, or a return type that is itself a generated message | `declared` | **Assumed** from the framework's default converter (Jackson → JSON) |
| **REST out** | `Content-Type` / `Accept` set somewhere in the client chain | `syntax` | **Assumed** JSON |
| **Kafka** | **Serializer configuration** — `key.serializer` / `value.serializer`, or the generic parameters of `KafkaTemplate<K,V>` and the `@KafkaListener` payload type | `config_join` | Unknown. Kafka carries anything. |
| SSE | `text/event-stream` framing; the payload inside each event is separate | `declared` | Assumed JSON per event |
| WebSocket | A negotiated subprotocol, or nothing — usually only the parse call | `syntax` | Unknown |
| **Pub/Sub** | Nothing. The message is `bytes`. Only the **parse call** reveals it — `Order.parseFrom(data)` versus `objectMapper.readValue(data, Order.class)` | `syntax` | Unknown |
| **SQS** | Nothing. The body is a string; same as Pub/Sub | `syntax` | Unknown |
| JMS | `TextMessage` / `BytesMessage` / `ObjectMessage`, then the parse call | `syntax` | Unknown |

Kafka is the interesting one, because the answer sits in configuration rather than code —
`config_join` again (§7), the same shape as Spring Cloud Stream destinations:

| Serializer | Format | Schema registry |
|---|---|---|
| `org.apache.kafka.common.serialization.StringSerializer` | string | no |
| `…serialization.ByteArraySerializer` | opaque bytes | no |
| `io.confluent.kafka.serializers.KafkaAvroSerializer` | Avro | **yes** — subject `<topic>-value` |
| `io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer` | Protobuf | yes |
| `io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer` | JSON Schema | yes |
| `io.confluent.kafka.serializers.KafkaJsonSerializer` | JSON | no — **note the package: no `.json` segment, and no registry** |
| `org.springframework.kafka.support.serializer.JsonSerializer` | JSON | no |

### 4.2 Binding the spec

| Format | Spec artifact | Where it lives | Binds by |
|---|---|---|---|
| **Protobuf** | `.proto`, or the `FileDescriptorProto` embedded in generated code | repository **and** compiled output | message type name |
| **Avro** | `.avsc`, or `SCHEMA$` on a `SpecificRecordBase` subclass | repository **and** compiled output | record full name; on Kafka, the **subject** `<topic>-value` |
| **JSON** | Usually none — **the DTO type declaration is the spec** | code | type reference |
| JSON Schema | Fastify route options, OpenAPI `components`, `zod` | code or artifact | `$ref` / type reference |
| XML | XSD, WSDL | repository | namespace + element name |

Protobuf and Avro share a property nothing else here has: **the schema survives into the
compiled artifact**, so it is recoverable from a jar with no source present. That is the same
mechanism in every language — `generated_descriptor` — which is why it needs saying once
rather than seven times.

### 4.3 What this changes in the model

**An assumed format must not look like an observed one.** If a REST endpoint declares no
`produces` and we record JSON because Jackson is the default, that is an *inference from
framework configuration*, not an observation. It belongs at `evidence: declared` with
`resolution: narrowed` at best — never at the same trust level as a `produces` attribute or a
Kafka serializer setting. Today we would record nothing at all, which is arguably more honest
and definitely less useful.

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
it. That turns a subtle rule we could get wrong into a field lookup.

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
| Java | `produces` / `consumes` | — | `annotation` | A |
| Java | Spring 7 `version = "1.1"` / `"1.2+"` on `@RequestMapping` | API versioning | `annotation` | A |
| Java | Micronaut `@Controller` + `@Get`/`@Post`… (`value`/`uri` String, **`uris` String[]**) | — | `annotation` | A |
| Java | Quarkus / JAX-RS **`jakarta.ws.rs`** `@Path` + `@GET`… | `@Path` value is a scalar String | `annotation` | A |
| Java | Quarkus `io.quarkus.vertx.web.Route` | second Quarkus style | `annotation` | A |
| Java | Actuator `@Endpoint` / `@ReadOperation` | — | `annotation` | A |
| Java | `@RequestMapping` on an **interface or superclass** | Spring inherits mappings | `annotation` + hierarchy | B |
| Java | **Meta-annotations** — custom `@ApiGet` composed from `@GetMapping` | Spring resolves transitively | `annotation` (recursive) | B |
| Java | Nested / inner classes | currently skipped **and reported** | — | B |
| Java | WebFlux `Mono`/`Flux` return types | response shape roots through the declared wrapper ([D02](components/D02-catalog-schema.md) §2a) | — | ✅ shipped |
| Java | **Vert.x** `router.get("/x").handler(this::h)` | receiver + verb + first arg | `fluent_chain` | **B — the cleanest first exercise for chain reconstruction** |
| Java | WebFlux functional `RouterFunctions.route().GET(…)`, `coRouter { }` | — | `combinator` | B |
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

### 5.2 REST outbound

**Phase 2B shipped the first three.** Feign, Retrofit and Spring `@HttpExchange` are read as
outbound annotation clients — the first linkable endpoints. Everything else in this table
remains unimplemented; the system tier still has nothing to match against them.

| Language | Library | Shape | Tier |
|---|---|---|---|
| Java | Feign `@FeignClient`, Retrofit `@GET`, Spring `@HttpExchange` | `annotation` | ✅ shipped |
| Java | Micronaut `@Client`, MicroProfile `@RegisterRestClient` | `annotation` | A |
| Java | Spring 7 `ImportHttpServices` registration | `annotation` | A |
| Java | `RestTemplate` | `registration_call` | B |
| Java | `RestClient`, `WebClient`, OkHttp, JDK `HttpClient`, Apache HttpClient, `URL.openConnection()` | `fluent_chain` | **B — gates every client written in the last five years** |
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
| Java | Spring GraphQL `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping`, `@BatchMapping` | code-first | `annotation` | A |
| Java | Netflix DGS `com.netflix.graphql.dgs.{DgsComponent, DgsData, DgsQuery, DgsMutation, DgsSubscription}` | code-first; the shorthands are equivalent to `@DgsData` | `annotation` | A |
| Java | MicroProfile GraphQL `org.eclipse.microprofile.graphql.{GraphQLApi, Query, Mutation}` (Quarkus) | code-first | `annotation` | A |
| Java | `graphql-java` schema-first — `.graphqls` + `RuntimeWiring` | **the SDL file is the contract** | artifact + `registration_call` | A |
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

### 5.5 WebSocket

The boundary is the **event name**, not the connection path. `socket.on("orderCreated")` is
matchable exactly like a Kafka topic; `/ws` on its own tells us nothing.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Jakarta WebSocket `jakarta.websocket.server.ServerEndpoint("/ws")` (was `javax.websocket.*` — **match both**) | annotation on the class; the value is a URI template | `annotation` | A |
| Java | Spring STOMP `@MessageMapping("/topic/x")`, `@SubscribeMapping` | annotation | `annotation` | A |
| Java | Spring `registerWebSocketHandlers(registry).addHandler(h, "/ws")` | programmatic | `fluent_chain` | B |
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

### 5.6 Server-Sent Events

**The worst column in either matrix.** Nothing declares SSE. It is inferred from a return
type or from a media-type string, so the *same* route declaration is REST or SSE depending on
what the handler returns. This is the clearest case for making `protocol` a per-match
property — see §8.

| Language | Library | How it is actually detected | Shape | Tier |
|---|---|---|---|---|
| Java | Spring MVC — returns `org.springframework.web.servlet.mvc.method.annotation.SseEmitter` | **return type**; present since 4.2 and still in 7.x | return-type read | B |
| Java | WebFlux — returns `Flux<ServerSentEvent<T>>`, or `produces = MediaType.TEXT_EVENT_STREAM_VALUE` | return type **or** a `produces` string | return-type read | B |
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
| Java | Spring `@KafkaListener` (`topics`, `topicPattern`, `topicPartitions`, `groupId`) | — | `annotation` | A |
| Java | Micronaut `@KafkaListener`/`@KafkaClient` + `@Topic` | — | `annotation` | A |
| Java | `KafkaTemplate.send(topic, …)` | — | `registration_call` | B |
| Java | `KafkaConsumer.subscribe(Collection<String>` \| `Pattern)` | — | `registration_call` | B |
| Java | **`KafkaProducer.send(ProducerRecord)`** | **topic is a constructor argument of `ProducerRecord`**, not of `send` | `fluent_chain` | B |
| Java | `KafkaTemplate.send(Message)` with topic in a header | — | `fluent_chain` | B |
| Java | **Spring Cloud Stream** functional `Consumer<T>`/`Supplier<T>` beans | topic in `spring.cloud.stream.bindings.<bean>-in-0.destination` | `config_join` | **B** — [D02](components/D02-catalog-schema.md) §2d |
| Java | **SmallRye** `@Incoming("orders")` / `@Outgoing` | channel in code, topic in `application.properties` | `config_join` | **B** — [D02](components/D02-catalog-schema.md) §2d |
| Java | Alpakka / Pekko Connectors `Consumer.plainSource(s, Subscriptions.topics("t"))` | — | `registration_call` | B |
| Go | `segmentio/kafka-go` `kafka.NewReader(kafka.ReaderConfig{Topic: "t"})` | **topic is a struct-literal field** — easier than positional | `registration_call` | A |
| Go | `IBM/sarama` (was `Shopify/sarama`), `confluent-kafka-go` | **both import paths are live in the wild** — the module declared the Shopify path for a period after the move, so neither can be dropped | `registration_call` | A |
| TS | `kafkajs` `consumer.subscribe({topic})`, `producer.send({topic, messages})` | topic in an object literal | `registration_call` | A |
| Python | `confluent-kafka`, `kafka-python` `KafkaConsumer("topic", …)` | **topic is a constructor argument** | `registration_call` | A |
| Python | `faust-streaming` `app.topic("orders")` + `@app.agent(topic)` | — | `annotation` + `registration_call` | A |
| Rust | `rdkafka` `consumer.subscribe(&["topic"])`, `FutureRecord::to("topic")` | — | `registration_call` | A |
| Swift | `swift-server/swift-kafka-client` — a `librdkafka` wrapper with an async/await producer and an `AsyncSequence` consumer | **three years of development and no tagged release**; the tier is the detection cost, not an endorsement | `registration_call` | A |

`KafkaTemplate.send` returns `ListenableFuture` before Spring Kafka 3.0 and `CompletableFuture` from 3.0 on; 2.9 added a `usingCompletableFuture()` bridge that 3.0 removed.

### 5.9 JMS and AMQP

JMS is a **Java specification**. The other languages have no equivalent — the `—` in §2 is
structural, not a gap. AMQP is the cross-language analogue and is listed here.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@JmsListener` (`destination`, `selector`, `subscription`, `concurrency`) | — | `annotation` | A |
| Java | Micronaut `@JMSListener` + `@Queue`/`@Topic` | — | `annotation` | A |
| Java | `JmsTemplate.send` / `convertAndSend` | — | `registration_call` | B |
| Java | Direct `jakarta.jms.{Session, MessageProducer, MessageConsumer}` | — | `fluent_chain` | B |
| Java | `@RabbitListener`, `@PulsarListener` | — | `annotation` | A |
| Go | `rabbitmq/amqp091-go` (was `streadway/amqp`) `ch.Publish(exchange, key, …)` | — | `registration_call` | A |
| TS | `amqplib` `ch.publish(exchange, key, …)`, `ch.consume(queue, cb)` | — | `registration_call` | A |
| Python | `pika`, `kombu` `channel.basic_publish(exchange, routing_key, …)` | — | `registration_call` | A |
| Swift | — | **no JMS or AMQP client in common iOS use** | — | — |
| Rust | `lapin` `channel.basic_publish(…)` | — | `registration_call` | A |

**Package change:** `javax.jms` (Spring ≤5 / Boot ≤2) → `jakarta.jms` (Spring 6 / Boot 3+).
Both must be matched.

### 5.10 AWS SQS

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring Cloud AWS 3.x `io.awspring.cloud.sqs.annotation.SqsListener`, `SqsTemplate` | — | `annotation` | A |
| Java | Spring Cloud AWS 2.x `io.awspring.cloud.messaging.listener.annotation.SqsListener` | **different package** | `annotation` | A |
| Java | Spring Cloud AWS 1.x/2.2 `org.springframework.cloud.aws.messaging.listener.annotation.SqsListener` | **a third generation**, under the old `org.springframework.cloud` group | `annotation` | A |
| Java | AWS SDK v2 `SqsClient.sendMessage(SendMessageRequest)`, `…builder().queueUrl(u)` | — | `fluent_chain` | B |
| Go | `aws-sdk-go-v2` `client.SendMessage(ctx, &sqs.SendMessageInput{QueueUrl: …})` | struct literal | `registration_call` | A |
| TS | `@aws-sdk/client-sqs` v3 `client.send(new SendMessageCommand({QueueUrl}))` | **command classes are real, statically visible types** | `registration_call` | A |
| **Python** | **`boto3`** `boto3.client("sqs").send_message(QueueUrl=…)` | **clients synthesised at runtime from JSON service models — `send_message` is defined in no Python file** | `runtime_dynamic` | **C — ceiling is a `name_match` on the service string; `resolution: narrowed` at best** |
| Rust | `aws-sdk-rust` `client.send_message().queue_url(u).send()` | — | `fluent_chain` | B |
| Swift | `Soto`, the community AWS SDK for Swift — actively maintained, Linux/macOS/iOS | `sqs.sendMessage(.init(queueUrl: …))` | `registration_call` | B |
| Java | Micronaut | **no first-party annotations** — raw SDK or `micronaut-jms-sqs` | — | B |

### 5.11 Google Cloud Pub/Sub

The hardest protocol in the table: **B in every language**, because only Micronaut ships a
first-party annotation.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | **Micronaut `@PubSubClient` / `@PubSubListener` + `@Subscription`** | the only first-party annotation surveyed | `annotation` | A |
| Java | `Publisher.newBuilder(TopicName.of(p, t)).build()`, `.publish(…)` | — | `fluent_chain` | B |
| Java | `Subscriber` + `MessageReceiver`, `.startAsync()` | — | `interface_implementation` | B |
| Java | Spring Cloud GCP `PubSubTemplate.subscribe(…)`, or `PubSubInboundChannelAdapter` + `@ServiceActivator` | channel indirection | `config_join` | B — [D02](components/D02-catalog-schema.md) §2d |
| Go | `client.Topic("n").Publish(ctx, m)`, `client.Subscription("s").Receive(ctx, fn)` | — | `fluent_chain` | B |
| TS | `pubsub.topic("n").publishMessage(…)`, `subscription.on("message", cb)` | — | `fluent_chain` | B |
| Python | `publisher.publish(topic_path, data)`, path built by `publisher.topic_path(proj, t)` | topic assembled from a helper call | `fluent_chain` | B |
| Rust | `google-cloud-pubsub` (official `googleapis/google-cloud-rust`) | **publish only — receiving messages is not implemented**, and the crate is pre-GA with breaking changes expected. So Rust Pub/Sub has no inbound side to detect at all | `fluent_chain` | B |
| Swift | — | **no first-party or mature community Swift client** | — | — |

Spring Cloud GCP moved to Google's own repository **at version 2.0**, renaming packages `org.springframework.cloud.gcp.*` → `com.google.cloud.spring.*` and the Maven group `org.springframework.cloud` → `com.google.cloud`. Both generations are in the wild.

### 5.12 Async and internal boundaries

Not protocols, but genuine entry points that would otherwise fall out of the checklist.

| Language | Mechanism | Shape | Tier |
|---|---|---|---|
| Java | `@Scheduled`, Quartz | `annotation` | A |
| Java | Temporal / Cadence `@WorkflowInterface`, `@ActivityInterface` | `annotation` | A |
| Java | **Vert.x event bus** `vertx.eventBus().send("addr", m)` / `.consumer("addr", h)` | in-process pub/sub with **string addresses**, matchable like topics | `registration_call` | B |
| Java | Spring Integration `@ServiceActivator`, `@InboundChannelAdapter` | channels, not destinations | `config_join` | B — [D02](components/D02-catalog-schema.md) §2d |
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
corrected part of the question: **`protocol` was already handled.** The `protocol_hint` style
reclassifies endpoints other engines produced, and `wrappers` with `semantics: streaming` is
named as its trigger — so a `@GetMapping` returning `Flux<ServerSentEvent<T>>` was always
going to be reclassified as SSE.

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
