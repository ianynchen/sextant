# COVERAGE

The completeness checklist: what Sextant can detect, what it cannot, and what each gap
costs. Delivery status is in [PROJECT.md](PROJECT.md); this is about *reach*.

Organised on two axes — **language × application protocol**. §2 is the index, §5 is the work list.

Written after running Phase 1 against [spring-petclinic](https://github.com/spring-projects/spring-petclinic),
which found **zero endpoints on the first attempt** because the catalog matched
`@RestController` and petclinic uses `@Controller`. Coverage gaps are invisible until
something real is pointed at the tool.

## The matrices

**Rows are languages; cells count libraries.** `Scanner` is the prerequisite — without one,
nothing else in that row is reachable at any tier. Two tables because the address shapes
differ and one eleven-column table is unreadable.

| cell | means |
|---|---|
| `✅` | shipped, **and nothing outstanding** — no uncatalogued library AND no open Critical or Major. Enforced by `tests/architecture/test_feature_delivery.py` against `java-kotlin-delivery-list.md` |
| `◐ (2 open Major)` | every library catalogued, and that many defects open against it — the cell a reader used to see as `✅` |
| `◐ (2 limited)` | every library catalogued, 2 of them narrower than the framework's rule |
| `◐ (4A 3B 4C)` | 4 + 3 + 4 libraries not catalogued at all |
| `◐ (2 limited, 4A 3B 4C)` | both |
| `4A 3B` | nothing shipped here; these are what it would take |
| `—` | not applicable to that language |
| `·` | not enumerated in §5 yet |

A tier is what a gap COSTS: **A** needs only a catalog file, **B** needs a scanner
capability, **C** is not in the code at all (§1). `◐` never appears alone — the bracket
always names what is missing.

### 2a. Application protocols over HTTP

| Language | Scanner | [REST in](#51-rest-inbound) | [REST out](#52-rest-outbound) | [SOAP](#53-soap) | [GraphQL](#54-graphql) | [WebSocket](#55-websocket) | [SSE](#56-server-sent-events) |
|---|---|---|---|---|---|---|---|
| **Java / Kotlin** | ✅ ASM | ◐ (2 limited, 2A 2B 4C, 7 open) | ◐ (2A 2B, 2 open) | ✅ | ✅ | ✅ | ◐ (1A, 1 open) |
| **Go** | none | 2A 1B 1C | 1A | — | 1A | 1B | 1C |
| **TypeScript** | none | 3A 2B | 1A | — | 2A | 2A 1B | 1B 1C |
| **JavaScript** | none | 3A 2B | 1A | — | 2A | 2A 1B | 1B 1C |
| **Python** | none | 4A 1B 1C | 1A | 1B | 2A | 2A 1B | 2B |
| **Rust** | none | 1A 2B 1C | 1B | — | 1A | 1A 1B | 1B |
| **Swift** | none | 1A | 1A 1B | — | 1A | 1B | — |

### 2b. Messaging and RPC

| Language | [gRPC](#57-grpc) | [Kafka](#58-kafka) | [JMS / AMQP](#59-jms-and-amqp) | [SQS](#510-aws-sqs) | [Pub/Sub](#511-google-cloud-pubsub) | [Async](#512-async-and-internal-boundaries) |
|---|---|---|---|---|---|---|
| **Java / Kotlin** | ◐ (1A) | ◐ (1B, 1 open) | ✅ | ◐ (2 open) | ◐ (1B, 1 open) | ◐ (1 limited, 2A 1B 1C, 2 open) |
| **Go** | 1A | 2A | 1A | 1A | 1B | 2A |
| **TypeScript** | 2B | 1A | 1A | 1A | 1B | 1A |
| **JavaScript** | 2B | 1A | 1A | 1A | 1B | 1A |
| **Python** | 1A | 2A | 1A | 1C | 1B | 2A |
| **Rust** | 1A | 1A | 1A | 1B | 1B | 2A 1B |
| **Swift** | 1A | 1A | — | 1B | — | 1B |

Everything below is the detail behind these two tables: how to read them (§1), what a run produces today (§2), the language and version gate (§3), wire formats (§4), and the per-protocol work list they are generated from (§5).

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
## 2. Behind the matrices

The two tables are at the top of this file, where a reader meets them before anything else.
This section is what stands behind them: what a run actually produces today, what the
`✅ ASM` in the Scanner column claims, what the messaging table leaves out, and how the
cells are generated.

**What the `Java / Kotlin` row does and does not claim** (W42). Both matrices carry ONE row
for the two languages, and `coverage_matrix.py` aliases `Kotlin` to it — so a checklist row
spelled `Java` counts into a cell labelled for both. Measured: §5.1 to §5.12 hold **186 rows
whose first cell is `Java` and 0 whose first cell is `Kotlin`**, so every cell in that row is
carried by rows spelled `Java` — several of which are about Kotlin, which is the first sign
that the spelling is not the measurement.

That is not a false claim, and the qualification is the point. These catalogs match on
FULLY QUALIFIED annotation and type names in compiled bytecode, and Kotlin compiles to the
same class files — a Kotlin `@RestController` carries the same `@RequestMapping` descriptor a
Java one does, which is Q2's "same bytecode level" ruling. The fixture proves that much:
`KotlinOrderRoutes.kt` derives three routes through the reactive functional catalog, at the
right verbs and the right composed addresses.

**They are NOT indistinguishable from the Java ones, and the difference is measurable in the
export.** All three Kotlin routes carry a NULL `handler`; every Java functional route names
one, *including the two whose handler is itself a lambda* (`GET /fn/health`, `GET /other`).
Downstream the gap widens: `roots` and `reachability` contain **no Kotlin symbol at all**,
while the Java functional handlers contribute 21 reachability rows. So a Kotlin route is
published as an address nobody serves — the address is right and the thing behind it is
absent. *An earlier version of this paragraph said the two were indistinguishable, which was
its only evidence for the parity it claims, and it was never checked against the `handler`
column.* `docs/open-issues.md` `OI-23` carries the NULL handler as a functional-routing
issue; measured, the live instances are Kotlin's three and no Java one.

**What the shared row cannot show is where Kotlin DIVERGES.** §5.13 carries the language
constructs — `suspend fun`, extension functions, `$default` synthetics, `DefaultImpls` — and
§5.1 already carries protocol rows that are about Kotlin and spelled `Java`: the
non-coroutine `router { GET("/x") { … } }` DSL derives NOTHING, and Ktor's
`routing { get(…) }` sits at tier B. So "0 rows spelled `Kotlin`" measures the SPELLING, not
the content, and a reader who takes the merged row as "Kotlin is at parity" is right about
what a catalog matches on and wrong about what reaches the export — which is exactly why the
checklist gained a language axis in W41.

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
A module's full analysis exports as a self-describing D06 bundle. Twenty-three of the twenty-six designed
scanner capabilities are implemented: `annotation_args`, `typed_signatures`,
`type_annotations`, `kotlin_metadata`, `call_site`, `string_constants`, `chain_reconstruction`,
`implemented_interfaces`, from Phase 2O `superclass` (9.13), `generic_interfaces`
(9.14), `array_arguments` (9.15) and `nested_annotation_args` (9.16), from 2Q
`lambda_body` (9.17) and `method_returns` (9.18), from W4 `annotation_default`,
`class_file_version`, `concat_template`, `constant_value` and `enclosing_class`, from
W5 `type_parameters`, and from W6 `source_file`, `line_numbers` and
`local_variable_names`. The three unshipped are
`invokedynamic`, `constant_propagation` and `control_flow` ([M03](components/M03-scanner.md)).
The count is of `Capabilities.ALL` in the extractor jar, which is the authority — this
sentence is a copy of it and was stale by five for the whole of W4.
Verified end-to-end on spring-petclinic: 17 endpoints, byte-identical
across runs.

**Phase 2D gave §2b the same texture.** `@KafkaListener` (class-level `@KafkaListener` +
`@KafkaHandler` included), `@JmsListener` and `@SqsListener` are read as inbound catalogs
— joined in 2O Task 7 by `@RabbitListener` (with `@RabbitHandler`), `@PulsarListener`, the
two legacy `@SqsListener` spellings and `RabbitTemplate.convertAndSend`;
`KafkaTemplate`, `ReplyingKafkaTemplate`, the raw `KafkaProducer`, `JmsTemplate`, `SqsTemplate`
and `PubSubTemplate` (publish, plus all ten of its consuming methods inbound since F2 §3.9) are read outbound by the
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
/events/stream`). **Seven catalogs and one SDL reader ship it**: four owning `graphql`
(`spring-graphql`, `netflix-dgs`, `microprofile-graphql` and the framework-neutral
`graphql-schema`, which reads the SDL), and three owning `websocket`
(`jakarta-websocket`, `spring-stomp`, `spring-websocket`). No catalog owns `sse` — a
`protocol_hint` block on the two existing HTTP catalogs moves rows there instead. The
phase delivered the two
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

**Phase 2I closed SOAP — the last protocol on the coverage program's own committed list.**
That list is the roadmap's, not [REQUIREMENTS.md](REQUIREMENTS.md)'s: version-1 scope names
**gRPC** as well; at the time this section was written gRPC had no shipped Java row, and it
was enumerated in the milestone's own modulo rather than quietly folded into "done" — Phase
2O (Tasks 4-5) has since shipped both the descriptor and the JVM bytecode halves (§5.7). A SOAP
operation is `(soap, NULL, {namespace}localPart)` — verbless, the identity being the input
element's QName rather than the one POST path every operation shares — with a second form
on the same protocol for `@SoapAction`, whose address is the transport header's URI
verbatim. **Five catalogs and one reader ship it**: `spring-ws` (`@Endpoint` +
`@PayloadRoot` + `@SoapAction`) and `jakarta-jws` (`@WebService`/`@WebMethod`, **both** the
`jakarta` and `javax` spellings, a bare public method included because JAX-WS exposes it)
inbound; `spring-ws-template` (`WebServiceTemplate`, reading the operation off the payload
argument's own type and the address off the template's configured default) and
`jakarta-jws-client` (generated stubs, the 2B Feign shape) outbound; and the
framework-neutral `wsdl-schema`, over a new **stdlib-XML** reader and interpreter branch
for `.wsdl`/`.xsd` — zero new dependencies — that projects declared shapes and marks each
operation's input element, so a schema-first service with no annotation anywhere derives
its operations at `declared`. Seven new vocabulary words carried the catalogs, and every
one of them is named for a shape rather than for a framework — a QName composition, a
reversed-package namespace default, a class gate over public members, a per-annotation
withdrawal filter, an identity read off an argument's type, a client's configured default
address, and a gate on whether a declaration sits on a class or an interface — so the
framework names stay in the catalog files. The phase also shipped the **first
analysis-configuration file that lives in the analysed repository**: `.sextant.yml` names
dependencies whose own bytecode is extracted beside the module's, because SOAP's commonest
outbound form is a stub in a jar — an opt-in, per library, never a walk of the dependency
tree, and every row it contributes carries its origin coordinate into the facts, the
rendered document and the exported bundle.

**Phase 2M closed gap area A — build systems and project shape — and fixed four
rendered-output defects a live analysis surfaced.** `GradleDetector` joins `MavenDetector`
behind the same `Detector` port ([M02](components/M02-detector.md)): it learns a Gradle
build by running the project's own wrapper against a read-only init script, never by
parsing `build.gradle(.kts)` — a Kotlin program, version catalogs and `subprojects` blocks
put real parsing out of reach. A multi-module root — Maven's `<modules>` walk, now
recursive, and Gradle's own settings evaluation — is discovered, and every module not
KNOWN to be a library or a leaf `pom` packaging is analyzed into its own workspace,
root-relative and pinned in `modules.json`. **Tested surface, stated honestly:** every
fixture behind this document's matrices still pins Spring Boot 3.x semantics — the
goldens' value is stability, not currency. Boot 4.1 is field-validated, not
fixture-pinned, for the HTTP inbound surface — verified live against
`examples/jhipster-sample-app` and `examples/spring-petclinic-rest`, both Boot 4.1 —
through `scripts/field_check.py`: opt-in, network-using by nature, and never part of the
test suite or `scripts/check.sh`. Anything Boot-4-specific the field run finds missing
becomes a catalog row in Phase 2O, never a special case bolted onto this phase.

**Everything else in both matrices remains a gap** — including, inside the cells Phase 2D and
2E-prep touched, spring-cloud-aws's own channel-adapter bindings (`config_join`'s shape,
not yet catalogued — Spring Cloud Stream's own functional bindings are the one row this
phase ships; Spring Integration's channels are enumerated as open questions since 2O
Task 9, §5.12), and every messaging peer address
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
  `JmsTemplate`, `SqsTemplate` and `PubSubTemplate` outbound — and since 2O Task 7,
  `@RabbitListener`, `@PulsarListener`, the two legacy `@SqsListener` spellings and Actuator
  `@Endpoint` inbound, plus `RabbitTemplate.convertAndSend` outbound — and since 2E-prep, direct
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
  ones. A path the module both exposes and calls is TWO endpoints with a `self_exchange`
  question naming both sides (F5 §6.1, W27); `both` is reserved for the linking tier. Since
  Phase 2I the same table also holds SOAP operations — `@PayloadRoot`/`@SoapAction`,
  `@WebService`/`@WebMethod` in both spellings, `WebServiceTemplate` calls and generated
  client stubs, plus every operation a `.wsdl` declares — verblessly, at their QName.
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
- **The module's resolved dependency set, with a version each** (F1) — on the `module` fact
  and in `metadata.json`'s `module.dependencies`. **Reach differs by build system and the
  difference is not smoothed over.** Gradle reports its own RESOLVED compile classpath,
  transitives included, with the version its conflict resolution actually chose. Maven is
  read from pom FILES — the module's own, every ancestor reachable through
  `<relativePath>` or already unpacked in the local Maven repository, and every BOM those
  import — because `mvn` may not be installed and running a build as a side effect of
  ANALYSING one is not a thing an analyser may do. That reaches inheritance,
  `<dependencyManagement>`, imported BOMs and `${…}` interpolation, and it reaches no
  transitive at all. Four consequences are stated rather than left to be discovered:
  a coordinate arriving only as another artifact's own dependency is absent on Maven and
  present on Gradle; **`<scope>` is not read on the Maven side**, so a `test`-scoped
  dependency is in the set where Gradle's compile classpath excludes it; a version range
  is carried verbatim, since choosing within it is mediation; and the local Maven
  repository is one of this analysis's INPUTS, so a machine that never built the module
  resolves fewer versions — every shortfall named, with its reason, in
  `metadata.json`'s `dependencies_not_resolved` rather than silently shortening the map.

What a run does **not** give you, each entry named in the output's own gap list rather
than silently absent:

| You do not get | Because | Arrives with |
|---|---|---|
| A WIRE row for a Spring Integration channel, and spring-cloud-aws's own channel-adapter bindings | each names a destination through a channel indirection, not a bean's own functional shape. Since 2O Task 9 Spring Integration's channels are ENUMERATED — one `channel_destination` open question each, carrying the channel and the handler — because the framework defines no standard configuration key a built-in could read; spring-cloud-aws has no catalog at all (D02 §2d) | the enrichment seat, for the first; undecided for the second |
| A base address built by computation — concatenation, setter injection, a method's return value | only a directly-read field, a constructor-injected value, or an `@ConfigurationProperties` class climbs the field ladder to configuration; a computed base derives `path` NULL, `unresolved` (`computed_base_addresses_not_traced`) | undecided |
| Configuration constructed in code — a settings module, a config factory | only configuration FILES reach resolution; a `resolved_config` row exists only where a reader parsed a file from disk (`config_as_code_not_read`) | undecided |
| Every messaging peer except SQS's queue URL | a broker address is connection configuration, never the destination expression `config_join`/the field ladder resolve — `peer` stays NULL there even where the destination itself now resolves | undecided |
| Sequencing between reactive/lambda calls (`flatMap`, `map`) | calls inside them derive endpoints, but the sequence between those calls awaits the call graph (`reactive_flow_not_traced`) | call-graph phases |
| Sequence diagrams, traces, a call graph | no `call_site`/control-flow facts (`sequence_diagrams_pending_call_graph`, `call_graph_not_implemented`) | call-graph phases |
| A full class diagram (inheritance) | only contract types are drawn (`structure_diagram_limited_to_contracts`) | with the `edges` table |
| A link between a Java class and the SDL type of the same name | two shape universes now describe one GraphQL service, and matching them by simple name is a guess; both are recorded and the cross-link is comparison work with its own evidence (§5.4) | the phase that earns it |
| The HTTP address a GraphQL or STOMP service listens on | the `path` column carries the OPERATION, because that is what the identity is; no engine derives `/graphql` or the STOMP endpoint registration ([D01](components/D01-graph-schema.md) §3) | undecided |
| Cross-service links or a system document | linking is a system-scope pass over bundles; no `participants`/`links` exist yet | linking phase |
| A handler symbol for a Kotlin WebFlux functional route | Kotlin compiles every DSL handler to an `instance`-kind argument naming a generated class, never a method | undecided |
| A Maven dependency that is neither declared nor inherited — a TRANSITIVE, or one declared inside a `<profile>` | F1 resolves the pom chain: a parent's own `<dependencies>`, `<dependencyManagement>`, imported BOMs and `${…}` properties all reach the recorded set with a version each. Another artifact's OWN dependencies do not, because following them means implementing Maven's mediation — nearest-wins, scopes, exclusions, ranges — which is a resolver rather than a parse, and a wrong one silently ADDS coordinates the build does not have. Profiles are unread for the same reason one level up: which profile is active is a property of an invocation this analysis never makes (`maven_profile_and_transitive_resolution_not_implemented`) | undecided |
| A payload bound from a parse more than one delegation hop from its handler | a flow followed further than it was observed is an assumption; the parse is found at hop two and ledgered as an open question instead, and past hop two it is not found at all (`payload_parsed_beyond_horizon`, §4.2) | the enrichment tier |
| A payload bound where one channel's bytes reach two different parses | two answers about one wire is a question for a reader, not a coin toss to publish (`payload_parse_ambiguous`) | the enrichment tier |
| Anything declared inside a dependency jar nobody named | a jar's own bytecode is scanned only where `.sextant.yml` opts it in, per library; the dependency tree is never walked, because scanning everything reachable publishes every framework's annotated types as this module's endpoints ([D04](components/D04-config-and-exclusion.md) §2a) | opt-in, per library |
| The response payload of a SOAP operation read from a WSDL | operations are marked from their INPUT elements only, so a schema-first row's response is honestly NULL rather than joined to a guessed output message (§5.3) | the phase that reads the output side |

One honesty caveat also rides every output — there were two until W27 retired
`merged_endpoints_keep_only_the_handlers_contract`, which closed when the merge that
discarded the client's contract was deleted. Even though endpoint request/response
contracts are scoped to the catalog that produced them, a payload type reachable from several catalogs is still expanded once, under
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

### 2c. What `✅ ASM` in the Scanner column claims

**What `✅ ASM` claims, and what backs it (W8).** Every attribute JVMS 4.7 defines is in
`AttributeLedger` in exactly one of two states — read, naming the callback that reads it, or
deliberately not read with a stated reason. **There is no third state**, and its absence is
the point: an attribute nobody had read and an attribute nobody had thought about used to
look identical from outside, because both simply produced no facts. **Five** are deliberately
not read — `StackMapTable` (verification metadata, describes no declaration),
`LocalVariableTypeTable` (duplicates `Signature`), and the three `Module` attributes (module
identity comes from the build's coordinates, and `module-info.class` is suppressed whole, so
`ModuleMainClass` has no visitor to be read from; measured over 1,672 cached jars, 383 carry
a module descriptor and 6 of those declare a main class). The two `TypeAnnotations`
attributes are read on a field and on a method and **not** on the class's own supertypes, and
their entries say so — that qualification used to live only in this paragraph while the
ledger said `read`, which was the third state itself. Every access flag is in the same list
on the same terms.

`AttributeLedgerTest` is what makes it a claim rather than a sentence: it compares the ledger
against JVMS's own list, refuses a reason that is a deferral in disguise, and resolves every
"read" claim against the source so a renamed callback cannot leave a stale claim behind. It
has already earned that — it caught `ACC_RECORD`, which ASM synthesises from the `Record`
attribute and which replaced two approximations of the same question with the one signal.
### 2d. What the messaging table leaves out

SNS and Redis are **out of scope by decision**, not oversight — each would be a new column.
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

**The notation was changed after a reader took `◐ —` to mean half-done.** It had meant
"shipped, and nothing outstanding" — the strongest a protocol cell could be — because the
generator emitted `◐` for shipped OR partial and wrote `—` when the gap list was empty. Two
different states rendered identically, and this paragraph used to instruct readers to take
the pair as "the stronger of the two markings, not the weaker".

That instruction was a defect report written as a legend. `◐` is a half-filled circle and
reads as half-done to anyone; `—` reads as not-applicable to anyone; the pair read as
neither of the things it meant. SOAP, GraphQL and WebSocket are 7/7, 5/5 and 3/3 shipped
with no gaps at any tier, and all three displayed `◐ —`. They read `✅` now, which is what
they were.

`◐` also **can no longer appear alone**, which was incoherent — a partial cell is one with
something missing, so the bracket names what. A library that is shipped but narrower than
the framework's rule counts as `limited`, and those were invisible before: REST inbound hid
two and Async hid one.

**Java + Kafka shows why.** Several ways of using Kafka from Java cost a YAML file each;
several more need real work, including `KafkaProducer.send(new ProducerRecord("t", …))`, where
the topic is a constructor argument of a *different object*; and Spring Cloud Stream and
SmallRye put the topic in a properties file under a key derived from a bean name. A cell
reading "A" would have been true and useless.

**Java REST inbound is still the largest gap spread in the document, at `4A 3B 4C`** — a
dozen distinct ways of declaring an HTTP endpoint in one language that we do not yet read,
beside the many we do. (The prose here read `8A 8B 5C` until Phase 2O Task 7b, a
hand-written headline left behind by the phases that burned it down; the number above is
the generator's, like every cell in the matrices, and it lost a `C` in Task 8 when
`@ControllerAdvice` stopped being one.) That spread, more than anything here, is
the argument for catalogs being data.

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
- **`artifact` depends on whether that reader exists.** Both readers now do: GraphQL SDL
  shipped in 2H and WSDL/XSD in 2I, so a row resting on either is no longer waiting on the
  reader — which is the same burndown property, seen from the artifact side.

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

## 3a. What we support, and at which versions

**Read this before accepting anything below.** A row elsewhere in this document says a
surface is covered. This section says *what we actually opened to find that out* — the
language versions the scanner can read at all, and the exact framework and library versions
each catalog's rules were measured against.

### The language gate

| | Range | Bounded by | How it fails outside the range |
|---|---|---|---|
| **Java** | class-file majors **45–71** — Java 1.1 through **JDK 27** | the pinned ASM (`org.ow2.asm:asm:9.10.1`) | **JDK 28** (major 72) and later: the class is skipped, its document marked `partial` with ASM's own refusal, and the scan continues |
| **Kotlin** | the same bytecode range for structure; **Kotlin ≤ 2.2** for nullability | `kotlin-metadata-jvm:2.2.0` — its `LATEST_STABLE_SUPPORTED` | a newer compiler's metadata cannot be decoded: the class is still scanned and still yields facts, nullability falls back to Java's rule, and the document is marked `partial` |

`verify: java -jar src/sextant/extractor-jvm/sextant-extractor.jar --capabilities` ·
the range itself is asserted against real bytes by
`extractor-jvm/src/test/java/dev/sextant/extractor/ClassFileVersionTest.java`.

**The mapping is `major = JDK release + 44`**, measured at six release targets (8→52, 11→55,
17→61, 21→65, 25→69, 26→70). Nothing here is taken from ASM's own constant set, which runs
ahead of the reader shipped beside it.

**Neither ceiling is a cliff.** Both degrade to a named gap on one document rather than a
failed run — which has only been true since Wave 1; before it, one class from a too-new JDK
ended the whole scan with exit 1 and zero facts.

### The frameworks and libraries

**Measured points, not ranges.** Every version below is one we READ the framework's bytecode
at. A version in between — spring-kafka 3.5, say, sitting between the measured 3.1.4 and
4.1.1 — is **unverified, not unsupported**: it very likely works, and we have not looked.
Stating a range would be a prediction about bytecode nobody opened, which is the move
[GUIDELINES](../GUIDELINES.md) §8.1 forbids.

*Generated from the catalogs by `scripts/coverage_versions.py`, and asserted current by
`tests/architecture/test_coverage_versions.py`. Do not edit the block below by hand.*

<!-- BEGIN GENERATED: coverage_versions -->

**71 of 86 catalogs name the artifact and versions their rules were read from. 15 record none.** The second number is a statement about our RECORD, not about the knowledge: a bound usually exists and is findable, it has simply never been written down here.

| Catalog | Artifact | Versions read |
|---|---|---|
| `apache-httpclient` | `org.apache.httpcomponents.client5:httpclient5` | 5.2.3 |
|  | `org.apache.httpcomponents.core5:httpcore5` | 5.2.4 |
| `google-pubsub-client` | `com.google.cloud:google-cloud-pubsub` | 1.129.3 |
| `google-pubsub-subscriber` | `com.google.cloud:google-cloud-pubsub` | 1.127.3 |
| `grpc-net-devh` | `net.devh:grpc-client-spring-boot-starter` | 3.1.0.RELEASE |
| `grpc-spring` | `net.devh:grpc-server-spring-boot-starter` | 3.1.0.RELEASE |
|  | `org.springframework.grpc:spring-grpc-core` | 0.10.0 |
| `jakarta-jms` | `jakarta.jms:jakarta.jms-api` | 3.1.0 |
| `jakarta-jws` | `com.sun.xml.ws:jaxws-rt` | 4.0.2 |
|  | `org.apache.cxf:cxf-rt-frontend-jaxws` | 4.0.5 |
| `jakarta-servlet` | `org.apache.tomcat.embed:tomcat-embed-core` | 10.1.50, 11.0.24 |
| `jakarta-websocket-client` | `jakarta.websocket:jakarta.websocket-client-api` | 2.2.0 |
| `jakarta-websocket-programmatic` | `jakarta.websocket:jakarta.websocket-api` | 2.1.1 |
| `jakarta-websocket` | `jakarta.websocket:jakarta.websocket-api` | 2.2.0 |
|  | `jakarta.websocket:jakarta.websocket-client-api` | 2.2.0 |
| `javalin-apibuilder` | `io.javalin:javalin` | 6.4.0 |
| `javalin` | `io.javalin:javalin` | 6.4.0 |
| `javax-jms` | `javax.jms:javax.jms-api` | 2.0.1 |
| `javax-servlet` | `org.apache.tomcat.embed:tomcat-embed-core` | 9.0.121 |
| `jdk-httpclient` | `jmod:java.net.http` | 21.0.12.1 |
| `kafka-clients` | `org.apache.kafka:kafka-clients` | 3.6.2 |
| `kafka-consumer` | `org.apache.kafka:kafka-clients` | 3.6.2 |
| `kafka-streams-sink` | `org.apache.kafka:kafka-streams` | 3.6.2 |
| `kafka-streams-topology` | `org.apache.kafka:kafka-streams` | 3.6.2 |
| `kafka-streams` | `org.apache.kafka:kafka-streams` | 3.6.2 |
| `ktor-routing` | `io.ktor:ktor-server-core-jvm` | 3.0.3 |
| `micronaut-http-client` | `io.micronaut:micronaut-http-client-core` | 4.7.6 |
| `micronaut-http` | `io.micronaut:micronaut-http` | 4.7.6 |
| `micronaut-jms-producer` | `io.micronaut.jms:micronaut-jms-core` | 4.2.0 |
| `micronaut-jms` | `io.micronaut.jms:micronaut-jms-core` | 4.2.0 |
| `micronaut-kafka-client` | `io.micronaut.kafka:micronaut-kafka` | 5.6.0 |
| `micronaut-kafka` | `io.micronaut.kafka:micronaut-kafka` | 5.6.0 |
| `micronaut-pubsub-client` | `io.micronaut.gcp:micronaut-gcp-pubsub` | 5.8.0 |
| `micronaut-pubsub` | `io.micronaut.gcp:micronaut-gcp-pubsub` | 5.8.0 |
| `microprofile-graphql` | `io.smallrye:smallrye-graphql-schema-builder` | 2.0.0, 2.18.5 |
| `okhttp` | `com.squareup.okhttp3:okhttp` | 3.14.9, 4.12.0 |
| `pekko-connectors-kafka` | `org.apache.pekko:pekko-connectors-kafka_2.13` | 1.1.0 |
| `quarkus-reactive-routes` | `io.quarkus:quarkus-reactive-routes` | 3.17.5 |
| `retrofit` | `com.squareup.retrofit2:retrofit` | 2.11.0 |
| `spring-actuator` | `org.springframework.boot:spring-boot-actuator` | 3.5.10, 4.1.1 |
| `spring-cloud-gateway-outbound` | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 |
| `spring-cloud-gateway` | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 |
| `spring-data-rest` | `org.springframework.data:spring-data-commons` | 3.2.5, 4.0.1, 4.1.1 |
|  | `org.springframework.data:spring-data-jpa` | 4.1.1 |
|  | `org.springframework.data:spring-data-rest-core` | 5.0.1 |
| `spring-http-interface` | `org.springframework:spring-aop` | 6.1.6 |
|  | `org.springframework:spring-core` | 6.2.15 |
|  | `org.springframework:spring-web` | 6.1.6, 6.2.15 |
|  | `org.springframework:spring-webmvc` | 6.1.6, 6.2.15, 7.0.2, 7.0.9 |
| `spring-jms-template` | `org.springframework:spring-jms` | 6.1.6 |
| `spring-jms` | `org.springframework:spring-jms` | 6.1.6, 7.0.9 |
| `spring-kafka-media` | `io.confluent:kafka-avro-serializer` | 7.6.0 |
|  | `io.confluent:kafka-json-schema-serializer` | 7.6.0 |
|  | `io.confluent:kafka-json-serializer` | 7.6.0 |
|  | `io.confluent:kafka-protobuf-serializer` | 7.6.0 |
|  | `org.apache.kafka:kafka-clients` | 3.6.2 |
|  | `org.springframework.kafka:spring-kafka` | 3.1.4 |
| `spring-kafka-replying` | `org.springframework.kafka:spring-kafka` | 3.1.4 |
| `spring-kafka-template` | `org.springframework.kafka:spring-kafka` | 3.1.4 |
| `spring-kafka` | `org.springframework.kafka:spring-kafka` | 3.1.4, 4.1.1 |
| `spring-mvc-router` | `org.springframework:spring-webmvc` | 6.1.6, 7.0.2 |
| `spring-mvc` | `org.springframework:spring-webflux` | 6.1.6, 7.0.2 |
|  | `org.springframework:spring-webmvc` | 6.1.6, 6.2.15, 7.0.2, 7.0.9 |
| `spring-pubsub` | `com.google.cloud:spring-cloud-gcp-pubsub` | 5.1.2 |
| `spring-pulsar` | `org.springframework.pulsar:spring-pulsar` | 1.2.11, 2.0.7 |
| `spring-rabbit-template` | `org.springframework.amqp:spring-amqp` | 3.1.4 |
|  | `org.springframework.amqp:spring-rabbit` | 3.1.4 |
| `spring-rabbit` | `org.springframework.amqp:spring-rabbit` | 3.1.4, 4.1.1 |
| `spring-restclient` | `org.springframework:spring-web` | 6.1.6, 7.0.2 |
| `spring-resttemplate` | `org.springframework:spring-web` | 6.1.6 |
| `spring-rsocket` | `io.rsocket:rsocket-core` | 1.1.4 |
|  | `org.springframework.boot:spring-boot-autoconfigure` | 3.2.5 |
|  | `org.springframework:spring-messaging` | 6.1.6 |
| `spring-scheduling` | `org.springframework:spring-context` | 6.1.6, 6.2.19, 7.0.9 |
| `spring-sqs-legacy` | `io.awspring.cloud:spring-cloud-aws-messaging` | 2.4.4 |
|  | `org.springframework.cloud:spring-cloud-aws-messaging` | 2.2.6.RELEASE |
| `spring-sqs-template-receive` | `io.awspring.cloud:spring-cloud-aws-sqs` | 3.1.1 |
| `spring-sqs-template` | `io.awspring.cloud:spring-cloud-aws-sqs` | 3.1.1, 4.1.1 |
| `spring-sqs` | `io.awspring.cloud:spring-cloud-aws-sqs` | 3.1.1, 4.1.1 |
| `spring-stomp-advice` | `org.springframework:spring-messaging` | 6.1.6 |
|  | `org.springframework:spring-websocket` | 6.1.6 |
| `spring-stomp-client` | `org.springframework:spring-websocket` | 6.1.6 |
| `spring-stomp-endpoint` | `org.springframework:spring-websocket` | 6.1.6 |
| `spring-stomp-template` | `org.springframework:spring-messaging` | 6.1.6 |
| `spring-stomp` | `org.springframework:spring-messaging` | 6.1.6 |
|  | `org.springframework:spring-websocket` | 6.1.6 |
| `spring-web` | `org.springframework:spring-webmvc` | 6.1.6, 6.2.15, 7.0.2, 7.0.9 |
| `spring-webclient` | `org.springframework:spring-webflux` | 6.1.6, 7.0.2 |
| `spring-webflux-router` | `org.springframework:spring-webflux` | 6.1.6, 7.0.2 |
| `spring-websocket-client` | `org.springframework:spring-websocket` | 6.1.6 |
| `spring-websocket` | `org.springframework:spring-websocket` | 6.1.6 |
| `spring-ws-template` | `org.springframework.ws:spring-ws-core` | 4.1.4 |

**No `measured:` block.** Not the same as unbounded, and not a claim that these do not work. Some are bounded by a library SEXTANT ITSELF ships — `grpc-schema` and `grpc-java` by `grpcio-tools>=1.83.1` and `protobuf>=7.36.1`, `graphql-schema` by `graphql-core>=3.2.6`, all declared in `pyproject.toml` — so their version bound is already determinable and merely unrecorded. Others rest on framework knowledge taken from documentation or source. **Telling those two apart per catalog is deferred, not impossible**: there is always a way to find the real version if we want it.

| Catalog |
|---|
| `aws-sqs-sdk` |
| `google-pubsub-publisher` |
| `graphql-schema` |
| `grpc-java` |
| `grpc-schema` |
| `jakarta-jws-client` |
| `netflix-dgs` |
| `spring-advice` |
| `spring-cloud-openfeign` |
| `spring-cloud-stream` |
| `spring-graphql` |
| `spring-integration` |
| `spring-kafka-message` |
| `spring-ws` |
| `wsdl-schema` |

<!-- END GENERATED: coverage_versions -->

### 3a-xiv. Coverage reports how much was UNDERSTOOD (FR-17 clause 3, F8 §9.5)

`coverage` carried `{documents, partial_documents}` — how many files were OPENED — and
nothing about how much of the call graph was read. Every resolution figure ever quoted about
this project came from a throwaway script written once and discarded; these are standing.

**The design asked for one `GROUP BY` on `call_edges.resolution`, and warned in the same
breath that it looks perfect. It does. Measured:**

| Corpus | edges | `resolution` | body READ |
|---|---|---|---|
| `mall-admin` | 24,591 | **100% resolved** | 19,239 (78%) |
| `jhipster-sample-app` | 1,686 | **100% resolved** | 545 (32%) |
| `spring-petclinic-rest` | 3,045 | 2,977 resolved, 68 narrowed | 971 (32%) |
| `orders-service` (fixture) | 1,474 | 1,472 resolved, 2 narrowed | 468 (32%) |

Each `body READ` percentage is the instrument's own — `round`, as `document.py` prints it.
*Petclinic's read 31% here for one release: 971/3,045 is 31.9, and truncating instead of
rounding put the document a point below the tool it describes.*

`resolution` says whether DISPATCH settled a call — whether the compiler's target narrowed
to one body — and naming that target is easy. Reading the body is the work, and on the two
corpora whose column reads 100% the picture is not the same: `jhipster-sample-app` leaves
**68% of its graph at a boundary** while `mall-admin` leaves **22%**, so a perfect dispatch
score sits beside both. *That sentence read "two thirds of the graph ends at a boundary" of
both, which is true of jhipster, petclinic and the fixture and false of `mall-admin` — one
of the two corpora it was about.* **Shipping
that distribution alone would satisfy the design's letter and leave the standing instrument
reading 100% forever**, which is precisely the corpus blindness §9.5 says it exists to catch.

So three buckets ship, and the reach rate LEADS:

**The three are counted at two different GRAINS, and they must not be added together.**
Reach and dispatch are per EDGE; method lookup is per `(class, name, descriptor)` — one
answer per method, however many call sites reach it. The document labels each one's unit
where it prints it, and `metadata.json` and the bundle manifest carry the bare maps under
their own key names.

- **reach** — `callee IS NULL` or not. How often a called body was actually here. Per edge.
- **dispatch** — the `resolution` distribution the design names. Per edge, and it can only
  ever hold `resolved` or `narrowed`: `call_edges` writes `NARROWED if len(callees) > 1 else
  RESOLVED`, so a third bucket is impossible by construction.
- **method lookup** — `method_resolution`'s reasons, which say WHY a body was missed:
  `owner_not_scanned` is a scanning decision (339 of the fixture's 565 METHODS, 425 of
  jhipster's 675), while `no_declaration_found` would be a defect. None of the four corpora
  has one.

**FR-17 clause 3 asks for the distribution of call SITES, and what ships is per edge.** The
two differ where dispatch narrowed: `spring-petclinic-rest`'s 68 narrowed edges are 34
sites, because a narrowed site writes one row per candidate body. The published figures are
labelled `call edges`, so nothing here is mislabelled — but the clause is met at a
neighbouring grain rather than exactly, and that is worth a reader knowing before they
quote it.

All three reach `metadata.json`, the bundle manifest, and — since a person reading the
document is who the instrument is for — the `## Coverage` section itself. `render` reads the
workspace back rather than re-resolving, so the summary is composed on both paths by one
function; composed only in the resolve pipeline, it reached the manifest and never the
document.

A module with no call graph prints no line at all rather than `0 of 0`: nothing was looked
for, so nothing was missed.

### 3a-xiii. Reachability is kept, and the tables carry a second ordering (F8 §9.4)

**The trace walk already computed this and threw it away.** `query/trace.py` walks every
root on every render and hands the renderer a tree; nothing kept the reachability, so "what
does changing this method affect" was a walk over the whole graph, once per question. The
`reachability` table is that walk's own answer written down — by the SAME function, which is
the point rather than a convenience: a second traversal with its own rules about cycles and
revisits would be a second opinion, and the day the two disagreed the document and the table
would both be defensible and one of them wrong.

| | fixture | `mall-admin` |
|---|---|---|
| rows | 190 | 3,892 |
| roots | 77 | 160 |
| terminals | 63 | 1,308 |
| deepest | 5 | 8 |

One row per `(root, symbol)`, carrying the SHALLOWEST depth any route to it reached. The
walk expands a method once per trace but still emits a step for every route to it — only
the subtree is elided — so every distance is seen and the least of them is the distance
from the root. **The first version recorded the depth the depth-first walk happened to see
first, which is not the shortest**: 51 rows on `mall-admin` came out deeper than the truth,
26 of them symbols the root calls DIRECTLY and filed at depth 2 or more, so a consumer
filtering `depth = 1` for "what does this handler call directly" missed every one. The
fixture had no instance of it, which is why the tests passed. Recording every ROUTE instead
is the shape D01 rejects when it declines to store traces at all — per-endpoint duplication
(D01 §3), not branching, which D01 is explicit a single trace does not suffer. A root
records ITSELF at depth 0, so "everything this root touches" is one lookup rather than a
lookup plus a union with the key.

A terminal is recorded by the TARGET the compiler wrote, since no body was read to name a
callee — omitting it would make a root that only calls a library look like a root that calls
nothing, which is the difference between "this handler does no work" and "the work leaves
the module".

**The two alternate orderings are the only index DuckDB over Parquet has.** There are no
B-trees; the levers are sort order and the zone maps that come with it — a row group carries
each column's min and max, so a query filtering on a column the file is SORTED by skips whole
groups and one filtering on any other reads everything. `call_edges` ships caller-major,
which makes "what does this method call" cheap and "who calls this method" a full scan, and
traversal needs both. `roots` ships handler-major while a person names a route.

`call_edges_by_callee` and `roots_by_address` are VIEWS, so the rows are the base tables'
own and cannot fall out of step; what ships is a second parquet of the same rows in a
different order, which is the artifact the zone maps live in. The bundle pays one extra file
each — 29 KB beside 29 KB for `call_edges` on the fixture, 4 KB beside 4 KB for `roots` —
and `roots_by_address` masks its `path` exactly as `roots` does, because a second file of
the same rows that skipped the mask would be the leak the index bundle had.

**The zone-map skipping buys nothing at today's sizes**, and saying otherwise would be
claiming a benefit that does not exist. DuckDB writes one row group per 122,880 rows and
`mall-admin`'s `call_edges` is 24,591, so every exported parquet is a SINGLE group: measured,
the two files' min/max statistics are identical and a point lookup on `callee` costs the
same against either. What the second file gives today is a second ORDER; the skipping begins
at roughly five times the largest corpus here.

**This is not `callers.ndjson`.** That answers "who calls X" for an agent grepping a file;
these serve a query engine reading the dataset. Two audiences, two artifacts, one set of rows.

### 3a-xii. The bundle says WHERE, not only what (F8 §9.3)

Sextant scanned a repository and could name every symbol in it without ever saying which
file to open. An agent holding the bundle still had to grep source it had already been told
about. `index/` is the third projection beside `graph/` and `render/`: eight NDJSON files an
agent loads once and greps, each record self-describing so a grep HIT is a complete answer.

| File | Answers |
|---|---|
| `symbols.ndjson` | symbol → file, line range, kind, enclosing |
| `callers.ndjson` | who CALLS this — resolved, not text |
| `implementors.ndjson` | who implements this interface |
| `annotated.ndjson` | which declarations carry this annotation |
| `shape_carriers.ndjson` | which endpoints carry this shape, request side and response side apart |
| `addresses.ndjson` | `GET /order/list` → root → handler → `file:line` |
| `files.ndjson` (W36) | per file: what it declares, by kind, and which annotations appear in it |
| `impact.ndjson` (W36) | "change `Order`" → the shape, its fields, the endpoints carrying it, and the handlers and callers of those, each placed |

**Six answer one question from one table; two assemble the others**, and those two exist
because the JOIN is the work. `files` is the cheapest win in the bundle — most of what an
assistant spends goes on files opened and discarded, so the record that lets it decide NOT
to open one pays for itself first; it carries counts and annotation NAMES rather than the
symbols, since `symbols.ndjson` already holds every symbol with its own location. `impact`
is the one a person's words map onto: nobody says "change `com/acme/OrderView#totalAmount`",
they say "change `Order`", and what comes back is every place that decision reaches, each
entry already placed so the agent does not make six more requests to find out where.

A shape id is a bare descriptor and a symbol carries module coordinates (D00 §5a), so the
location map is keyed on BOTH spellings — looked up on the whole symbol alone, every
contract in `impact` reported itself undeclared. The LISTING keeps one record per symbol;
aliasing a single map emitted each of them twice.

`addresses` is the one that makes the rest reachable: **a person names a route, not a
symbol**, and every other index needs a symbol to begin. Measured live on the fixture,
`GET /v1/orders/{id}` returns `src/main/java/com/acme/orders/OrderController.java:40`,
which opens on `return service.find(id);` with the `@GetMapping` two lines above — the
extent of the CODE, which is what `LineNumberTable` records.

**What §9.2 said and what is true now.** The design's keystone finding was "every line
number in the estate is 0". Half of that is fixed and half was never a gap:

| | measured |
|---|---|
| methods with a line | 20,961 of 22,059 on `mall-admin` |
| constructors | 818 of 818 |
| types and fields | **0, and correctly so** — a class file carries no `LineNumberTable` for either, and subtracting to guess a declaration line would be a claim about formatting |

So a type's record says `line: null` rather than borrowing its first method's line, which is
where that METHOD is.

**Placement, and the one thing that moved it.** A `relative_path` is a package path,
openable against nothing; `metadata.json` now carries the module's `source_roots` so the
index can join them. That alone placed **157 of `mall-admin`'s 648 documents** — every one
of its own and not a single symbol of the four reactor siblings it scans, 1,428 of 25,521.
A sibling's sources are under the SIBLING's root, and `origin_entry` is the only thing that
names it; the module root above the classes directory is SEARCHED for rather than computed,
because how deep it sits is the build tool's business (`target/classes` against
`build/classes/java/main`).

| Corpus | symbols placed |
|---|---|
| `mall-admin` | **25,521 / 25,521 (100%)**, 24,093 of them through a sibling |
| `jhipster-sample-app` | 775 / 857 (90%) |
| `spring-petclinic-rest` | 635 / 1,209 (52%) |
| `orders-service` (fixture) | 456 / 1,087 (41%) |

**Unplaced symbols have two causes, and generated code is 1,285 of the 1,287.**
`AuditEvent.java` (Avro), `OwnerMapperImpl.java` (MapStruct),
`AbstractAuditingEntity_.java` (JPA metamodel) — all written into `target/generated-sources/`
at build time, which is not a declared source root. The files exist and could be reached by
teaching the exporter each build tool's generated-source layout; that is deliberately NOT
done, because a generated file is regenerated and an agent sent there to make a change
would edit what the next build overwrites.

**The other two are a LIBRARY's**, and their reason is different and permanent:
`com/example/billing/BillingPort#` and its `charge` method come from the fixture's own
`extract_libraries` opt-in, read out of a jar. A library's sources are not in this
repository at all — there is nothing to teach the exporter about, and nothing to reach. The
record says `file: null` for both causes, and the distinction is here rather than in the
record because a consumer's action is the same either way: do not go looking.

**The index is an EXIT, so it masks.** It reads the same rows `graph/` does, and an
address published unmasked here would be the same bytes the parquet beside it takes trouble
to strip — measured before it was wired, a root at
`https://user:hunter2@internal.example.com/orders` reached `addresses.ndjson` whole while
`graph/roots.parquet` held the host alone. Only the address-bearing fields take the rule,
because that is the only kind of value these records hold: a symbol, a file path, a line
number and an annotation's NAME are none of them things a rule masks, and annotation
ARGUMENTS are deliberately not in the index at all.

**Never an absolute path.** A bundle travels; an absolute path names a directory on one
computer. A sibling comes back as `../mall-common/src/main/java/…`, and anything that will
not reduce to a relative path is dropped rather than published.

**The accepted cost, from the design:** the index cannot be joined against the tables in
DuckDB. Its job is to reach a `file:line` fast; after that the consumer opens the file or
queries the tables by the exact symbol the index handed back, which is why every record
carries the symbol verbatim.

### 3a-xi. The contract diagram draws inheritance (F7 §8.4)

FR-7 commits to class diagrams, and the emitter drew exactly one arrow — `-->`, the
association a field makes. Two more say what a type IS: `<|--` extends, `<|..` implements.

**Not every ancestor earns one.** `type_hierarchy` holds all of them, and drawing all of
them buries the diagram in relationships that say nothing about the wire — measured, 30 of
`mall-admin`'s 34 shape ancestors are a single marker interface, and four of this repo's
fixture's are a protobuf runtime base with four generated builder interfaces beside them.
Drawn naively, the fixture's diagram gained four `<<open>>` boxes above four shapes the
`.proto` describes completely. So the rule is what an ancestor CONTRIBUTES:

| Ancestor | Drawn? | Why |
|---|---|---|
| scanned, and itself a contract here | **yes** | both are payloads a reader can see |
| unscanned SUPERCLASS of an `open` shape | **yes**, plus an `<<open>>` node | that is where the unread contract lives |
| unscanned superclass of a CLOSED shape | no | nothing is missing — a schema-described type takes nothing from its class file |
| unscanned interface | no | an interface's own fields are constants; it explains no part of the payload |
| scanned, not a contract here | no | its fields are already IN the subtype's list, so the arrow points at an empty box |

What that draws, measured: **one arrow each** on the three corpora that have any —
`OrderResult <|-- DetailedOrderResult` (fixture), `PmsProductParam <|-- PmsProductResult`
(`mall-admin`), `AdminUserDTO <|-- ManagedUserVM` (`jhipster-sample-app`) — and none on
`spring-petclinic-rest`, whose payloads inherit nothing.

**Two of the five rows have no live instance, and both are shipped anyway.** The
`<<open>>` ancestor node is the second: measured across all four corpora, zero are drawn —
which follows from the shape rule beside it, since after the inherited-fields fix only a
schema-described type can be closed AND have an unscanned superclass, and those are exactly
what the third row excludes. It is a rule against a shape no corpus has, a payload
extending a vendor jar's base class, and its absence is recorded here rather than left for
a reader to infer from a diagram that never draws one.

**`<|..` is the first.** No corpus has a payload implementing an interface that is itself a
payload. `Page<T>`/`Slice<T>` is exactly that shape and W26
made such an interface expandable, so the rule is declared and pinned rather than deferred
until something ships it — and its absence is recorded here rather than left for a reader
to infer from a diagram that never draws one.

**The arrow and the stereotype are read from ONE flag.** Whether an unscanned superclass is
drawn comes from the shape's own `open`, not from re-deriving why it is open, so the arrow
and the `<<open>>` box beside it cannot disagree. Verified against the vendored mermaid
build in a live browser: both notations parse, and `<<open>>` renders as `«open»` above the
class name.

### 3a-x. A payload publishes the fields it INHERITS (F4 §5.2)

A payload class extending another published only its OWN fields, and said the description
was complete. Found while starting W33, which asks what a contract type extends.

| Shape | published | its scanned parent declares | said |
|---|---|---|---|
| `mall-admin` `dto/OmsOrderDetail` | 2 | 45 | `open: false` |
| `mall-admin` `dto/PmsProductParam` | 7 | 43 | `open: false` |
| `mall-admin` `dto/SmsCouponParam` | 2 | 19 | `open: false` |
| `jhipster` `ManagedUserVM` | 1 | 14 | `open: false` |

`OmsOrderDetail` is the response of a real endpoint. It published `orderItemList` and
`historyList` and claimed a complete description, while the JSON on the wire also carries
`id`, `orderSn`, `totalAmount` and 41 more — **46 fields, not 2**. (The "declares" column
is the parent's DECLARED count; one field of each parent is a static `serialVersionUID`,
which reaches no wire, so the merged contracts are 46, 49, 20 and 14.) That is the over-claim NFR-2 rates worst, and
DR-5 links services on exactly this comparison — two services agreeing on a 2-field
contract that is really 46 fields is a match made on almost nothing.

**The accessor half is why it lived this long.** `_rows_of` falls back to accessors only
where the field pass produced NOTHING, and W26 gave that fallback an ancestry walk — so a
payload declaring no field of its own came out right, through its getters. Only a payload
with SOME field of its own never reached the fallback. The fixture had the first shape and
not the second, so the always-on gate could not see it; `DetailedOrderResult` now carries a
field of its own, which makes it the second.

The field pass walks the scanned ancestry the same way the accessor pass does — JVMS
5.4.3.3 order, first declaration of a name winning, so a subtype shadows what it
redeclares. Recovered **153 wire fields on `mall-admin`** and 17 on `jhipster-sample-app`.

**An unscanned SUPERCLASS now opens its subtype**, which is F7 §8.4's `<<open>>` applied to
the shape rather than only to the diagram: fields we cannot see are fields we cannot claim
to have described. **It opens ZERO shapes on every corpus measured** — four shapes reach an
unscanned superclass and all four are the fixture's protobuf messages, which the second
exclusion below then removes — so it is a rule shipped against a shape no corpus has, a
payload extending a vendor jar's base class. Declared and pinned rather than deferred, and
its absence recorded here, which is the standing `<|..` has in the class diagram. Two
exclusions keep it from becoming a flood:

- **An unscanned INTERFACE does not.** An interface's own fields are constants, dropped as
  `static`, so implementing a marker interface says nothing about the payload. Counting it
  opened 30 of mall-admin's 107 shapes for one interface with no members.
- **A type owning a `declared_shape` does not.** Its contract comes from the schema and
  never from its class file (the never-a-blend rule, D01 §3), so what its generated class
  extends is irrelevant — every protobuf message extends an unscanned `GeneratedMessage`,
  and counting it opened all four of the fixture's proto shapes while the `.proto`
  describes them completely.

Net on `mall-admin`: 31 open shapes became 35, and all four newly-open ones are honest —
their recovered parent fields hold `java.util.Date`, a type this workspace never scanned.

### 3a-ix. A call with several possible bodies stops reading as several calls (F7 §8.3)

A `narrowed` call site is several candidate bodies with none picked — dispatch could not
commit, so the walk records one step per candidate. Drawn flat they read as a SEQUENCE, and
that was live in rendered output: `spring-petclinic-rest`'s `ClinicServiceImpl#saveOwner`
drew `save` to the JDBC repository and, eight arrows later, `save` to the JPA one, with the
first candidate's whole subtree in between. A reader could not see they were alternatives,
and the diagram said the service saves twice when exactly one repository is active.

**W32's own plan row said this shape "has never fired on real code (four corpora, zero
occurrences)".** It was wrong, and the correction is the reason the item was worth doing:

| Corpus | narrowed edges | call sites with several candidates |
|---|---|---|
| `spring-petclinic-rest` | 68 | 34 (31 reached by a trace) |
| `orders-service` (fixture) | 2 | 1 |
| `mall-admin` | 0 | 0 |
| `jhipster-sample-app` | 0 | 0 |

Every one of petclinic-rest's 34 is a repository interface narrowing to a JDBC
implementation and a JPA one — the shape a profile-switched application has by design.
**31 of the 34 are reached by a trace** and therefore reach the document, drawn as 62 `alt`
blocks across the traces that reach them, 4 of those nested inside another branch. The
other three are in the graph and in no walk. Both numbers are pinned in the corpus
expectations (`narrowed_sites`), because the last unpinned claim about this shape — the
plan row's — was wrong.

They now draw as mermaid's `alt`/`else`, which is the only notation it has for "one of
these, not all of these" — meaning at most one branch PER INVOCATION, not one ever: two
in-module implementations can both be live and both run at different times, and this repo's
own `TraceProbe#describe` narrows to two splitters with nothing making them exclusive. Each branch carries the candidate's own arrow AND everything
below it, which the walk being depth-first makes possible: a candidate is immediately
followed by everything it leads to, so a branch is a contiguous range. **Nothing is
reordered and nothing is dropped** — the same arrows, in the same order, inside a block
that says what they are. Verified against the vendored mermaid build in a live browser.

The caption changed with it. It read "nothing is filtered", which is true and useless to a
reader who has taken the arrows for a sequence; it names the number of CHOICES instead —
per site, not per candidate, because two candidates on one site is one choice.

**What guards it, and what does not.** Six unit tests, each verified against the mutation
it names — flat rendering, a branch losing its subtree, a lone candidate grouping,
`_grouped`'s recursion, `_named`'s recursion, and the `(caller, ordinal)` site key — plus
the corpus pin above. **The always-on fixture has no rendered `alt` block**: its one
narrowed site is `TraceProbe#describe`, which nothing calls and which is therefore no
root, so no trace reaches it. Making it reachable would move every trace, step and root
count in the fixture pins for one end-to-end instance of behaviour six unit tests already
discriminate, so it is stated here instead of bought.

**A single `narrowed` candidate is NOT drawn as a choice**, and the guard is defensive
rather than live. `resolve/call_edges.py` writes `NARROWED if len(callees) > 1 else
RESOLVED`, so `narrowed` IS "two or more candidates" by definition and zero lone rows exist
on any measured workspace — an earlier version of this paragraph said "dispatch can narrow
to one body and still decline to commit", which is not what the word means. The projection
keeps the guard because that invariant is another module's, not its own.

**The second half of §8.3's acceptance is NOT delivered**: *"and as one arrow labelled with
them when they are not [known]"*. There is no such state to render. A site whose candidate
bodies could not be named is not `narrowed` at all — it is `resolved` with `callee IS
NULL`, which the diagram already draws as one arrow marked `[boundary]`. The clause
describes a row the graph does not produce, and no code was written for it.

### 3a-viii. A terminal says what it reaches, not just that it is one (F7 §8.2)

[D00](components/D00-fact-schema.md) §4 declared `terminal_kind` for as long as the fact
schema has existed and **nothing produced one for two phases**. The note it carried gave
the right reason — *a data-access call is `persistence` only to something that knows the
callee is one* — and the renderer said what that cost a reader, in as many words: "a JDK
call and a MyBatis mapper call both read `boundary`… the distinction is the reader's to
make."

That knowledge is catalog data now (D02 §2j), and the classification is read.

| Corpus | terminals | classified | breakdown |
|---|---|---|---|
| `mall-admin` | 5,352 | **240** (4%) | 199 `database` (scanned package), 41 `cache` (owner) |
| `spring-petclinic-rest` | 2,074 | **102** (5%) | 102 `database` — 82 `EntityManager`, 17 `ResultSet`, 3 `JdbcTemplate` |
| `jhipster-sample-app` | 1,141 | **70** (6%) | 70 `database` — 68 supertype, 2 `EntityManager` |

These are the numbers `call_edges` holds, re-measured whole for W30's review, which found
five published figures disagreeing with each other across this file, the catalog, D00, D02
and the module. Where any other document still disagrees, this table and
`resolve/terminals.py` were corrected together from one run and the other is stale.

**The remaining 94-96% is the point, not a shortfall.** It is `StringBuilder`, `Object`,
`List`, `Iterator` — ordinary library calls, and they read `unresolved`, which says *this is
a terminal we examined and could not classify*. NULL means something else entirely: the
edge is not a terminal at all, because its callee's body was read.

**Three routes, one per framework, and none of them a name match.** `*Mapper` and
`*Repository` would have been the easy rules and both are naming conventions:

- `mall-admin`'s MyBatis mappers carry **no annotation at all**. `@MapperScan({"com.macro.
  mall.mapper", "com.macro.mall.dao"})` on a config class is how MyBatis registers them,
  and that annotation is in the fact stream with its package list.
- `jhipster-sample-app`'s repositories are its own interfaces, also unannotated; the class
  file says they implement `JpaRepository`.
- `spring-petclinic-rest` reaches its store through `EntityManager` and `ResultSet`
  directly.

**Two things this cost to get right, both found by measuring rather than reasoning.**
Naming Spring Data's base `Repository` classified **zero** of jhipster's: the supertype
walk ends at the first UNSCANNED type, and a framework's own interface has no facts here,
so the walk never sees what it extends — a catalog must name the level a user actually
extends. And the first version read the `type_hierarchy` TABLE, which the same pass writes
after the edges, so it returned nothing at all; it reads the `superclasses`/
`implementations` facts that table is built from instead, in JVMS 5.4.3.3 order. Three
documents and the catalog itself still credited `type_hierarchy` after that fix and have
been corrected.

**Eight of the nine declared supertypes are unmeasured.** `JpaRepository` is the only one
any corpus reaches; the other eight are the levels Spring Data's own documentation tells a
user to extend. That is a considered guess at the shape, recorded as one.

**What checks the shipped rules, and what cannot.** Every unit test here invents its own
annotation and its own base type, deliberately — a rule read from catalog data is only
proved to be read from catalog data if the data is not the real spellings — so nothing in
the suite touches `spring-web.yml`'s twelve rows. A typo in
`org.mybatis.spring.annotation.MapperScan` is not INVALID, so no loader refuses it; it is
inert, with no error and no failing test. The corpus pins carry that check instead
(`scripts/field-expectations/*.json`, `terminal_kinds`), one corpus per route, and each was
verified by introducing the typo: `MapperScan` moves mall-admin's 199 to zero,
`JpaRepository` moves jhipster's 68 to zero, `RedisTemplate` moves mall-admin's 41. They are
opt-in and network-using by nature (2M design §3), so the guard is real but not always-on —
which is the same standing `resolvable_superclass_calls` has, and for the same reason.

**`java.sql.Date` is deliberately unclassified**, beside `java.sql.ResultSet` which is not.
Both are in the same package and both are terminals in `spring-petclinic-rest`. One is an
API that reaches a store and one is a date. The package is not the evidence.

**Five of the eight members have no producer, and for two different reasons** (`OI-75`).
`outbound_call` and `async_handoff` are one catalog rule away — an `owner` rule
naming `ExecutorService` would mint `async_handoff` today, and none is declared, so all
twelve shipped rules say `persistence`. `cycle`, `returns` and `ends_silently` are
unreachable BY CONSTRUCTION and no rule can change that: a cyclic edge has a non-NULL
`callee`, so `classify` returns NULL for it, and the other two describe how a BODY exits
while every catalog route is a predicate on the callee's TYPE. `throws` was the sixth until
`G-52` (2026-09-12), and it closed by the second route, not the first: `classify` returns it
for a `throw` site directly, from the instruction, because how a method exits is not
something any library knows (§5.13's throw-exits row).

`TargetKind.file` has no producer either, and it has live candidates:
`io.minio.MinioClient` and `com.aliyun.oss.OSSClient` are both called on `mall-admin` and
both read `unresolved`.

### 3a-iii. A module reads its dependencies' types, and publishes none of their rows (F4 §5.2)

`CommonResult<T>` is compiled in `mall-common`; every one of `mall-admin`'s controllers
returns it. Until W24 that module's class files were never read, so **160 of 160
endpoints carried one distinct response shape with zero fields** — the envelope, empty.
A reactor sibling this module DECLARES as a dependency is now scanned as a library root,
transitively (`mall-common` is reached through `mall-security`), and its three fields —
`code`, `message`, `data` — are in the workspace. Substituting `data`'s type parameter is
W25; W24 is what makes it possible.

**The set is the declared dependencies, not the reactor.** An earlier attempt walked the
parent POM's whole `<modules>` list, which put `mall-portal` and `mall-demo` — modules
`mall-admin` does not depend on — into its workspace: **246 endpoints against its own
160**, and `mall-portal`'s `@Scheduled` cron task rendered inside `mall-admin`'s own
document. A type can only reach this module's signatures if the module compiles against
it, so the dependency list is the right set, and reading it removed the fabrication at
source: the same corpus now derives exactly 160 with the guardrail disabled.

**The guardrail stays, because a shared `-web` or `-api` module does carry controllers.**
A dependency's rows are dropped before the endpoint merge — after it, a dependency
serving an address this module CALLS would take the module's own outbound row with it,
silently. `schema_operations` filters its own roots instead, because it mints rows with
neither a handler nor a caller and there is nothing downstream to key on. Error advice is
gated on the HANDLER's tier, so a dependency's `@ControllerAdvice` on this module's
handlers survives while its advice on its own does not.

**`extract_libraries` is deliberately NOT covered, and it took a failing test to see
why.** An earlier version of the guardrail keyed on the origin tier, which both kinds of
library share, and it deleted the SOAP operation `test_vertical_slice.py` asserts an
opted-in library contributes. That is not a hole being closed: [D04](components/D04-config-and-exclusion.md)
§2a defines that file as "scan this dependency's own bytecode as well as mine", so the
surface is what the person asked for. A sibling is scanned because it is on the classpath
and nobody was asked. **Consent is the difference**, it is not readable from the tier, and
that is why the module fact carries `sibling_coordinates` and the guardrail keys on those.

**What it costs, measured (2026-09-12):** `mall-admin` analyses in 111s against 8s, 648
documents against 161. `derive_endpoints` is 47s of it and `derive_endpoint_shapes` 39s,
and the cost is NOT work the guardrail then discards — the SQL the guardrail cleans up
after is 2.8s of the 31.7s replay (the fresh run's 47s was not profiled to the query); the
rest is every catalog re-reading the fact tables from
Python (`docs/performance.md` P-1 has the profile to the query and the fix shape; it is
a performance item, not a gap, and is worked after the delivery register is empty). **Gradle is not implemented** — `GradleDetector` sets no sibling
roots, so every Gradle multi-project build keeps the empty-envelope defect (`OI-69`).

### 3a-vii. What an outbound call carries besides its address (F5 §6.2)

`endpoint_metadata` is a side table, one row per entry, each carrying **its own resolution
and evidence**. Measured on the fixture's `GET /v2/inventory/tagged`:

| kind | name | value | resolution |
|---|---|---|---|
| header | `Authorization` | `«redacted»` | resolved |
| header | `X-Tenant` | `acme` | resolved |
| header | `X-Trace-Id` | — | unresolved |

The third row is the point. *This call sends an `X-Trace-Id` header whose value we could
not read* is a materially different statement from *this call sends no such header*, and a
table recording only readable values could not tell them apart.

**Redacted at the origin.** The first row's value is a literal `Bearer` token in bytecode.
Nothing in this system reads a metadata value — no pass substitutes one into an address
the way `resolved_config.value` is substituted into a peer — so the masked string is the
only one ever written down, there is no export query to add and nothing to forget. (The
masking uses the BUILT-IN patterns only; a module's own `redact:` additions do not reach a
resolve engine — `OI-71`.)

**`collects` is a new kind of catalog capture, and the difference is load-bearing.** Every
existing capture is LAST-WINS: a repeated step overwrites its own earlier value. Applied
to headers that keeps the third of three and says nothing about the other two — not a
smaller answer but a wrong one. A collecting step accumulates instead. A varargs position
contributes one entry per value, because `header(String, String…)` is what the API
declares and `header("Accept", "a", "b")` sends two values.

#### What is NOT recorded, and why — measured, not assumed

The design's table names six protocols. Four of the seven metadata kinds in it are not
readable here, and one was already delivered:

| Protocol | Entry | Status |
|---|---|---|
| HTTP | headers | ✅ read |
| HTTP | query parameters | ✅ read, and **so is the URL they are built with** (`OI-73`, closed here). `uri(Function)` hands a `UriBuilder` to a lambda, and the whole address used to go unread — the row derived with `path` NULL, which costs the row its identity, since DR-5 matches on the wire contract. The lambda's own synthetic method is now walked as a chain of its own and its declared captures folded back: `InventoryWebClient#search` went from `path` NULL to `/v2/inventory/search` |
| AMQP | routing key | ✅ **already delivered before this**, as part of the address: `spring-rabbit-template.yml` reads it at `address_arg_2`, and AMQP's wire identity IS the exchange and routing key together |
| Kafka | partition key | ❌ blocked by `OI-72` — `ProducerRecord`'s value sits at a different index per overload, and two different 5-arity constructors disagree, so only the descriptor can say which |
| Kafka | record headers | ❌ an `Iterable<Header>` built outside the call |
| SQS | message attributes | ❌ a whole `Map<String, MessageAttributeValue>`, built outside the call |
| Pub/Sub | attributes | ❌ `PubsubMessage.Builder.putAttributes(k, v)` is per-entry and in a chain, but that is the MESSAGE's chain, joined to the publish by argument rather than by receiver — a join the walk does not follow |
| JMS | properties | ❌ `setStringProperty(k, v)` mutates a message object; there is no chain from the send call to it |

The four remaining ❌ share one cause: **the entries are built as a map, a collection, or
by mutation, outside the call the row was derived from**. Reading them is flow analysis
this system deliberately does not do, so the answer is a stated boundary rather than a
guess.

**The query-parameter row was one of them until it was measured properly.** It was first
recorded as unreadable for the same reason — the builder chain is not the client chain —
and that was true of the mechanism and wrong as a conclusion: the lambda is one argument
of one call, the fact stream names the synthetic method it compiled to, and reading that
method's own call sites is reading rather than guessing. What it cost was not the
parameters but the ADDRESS, on every WebClient call that builds a URL the idiomatic way.

### 3a-vi. Two handlers a framework would refuse to register (F5 §6.1)

D01 has said since it was written that two handlers declaring one wire contract "is a
routing-ambiguity finding". Nothing detected one — `docs/open-issues.md` OI-83
row 9 recorded exactly that — and W28 builds it.

**The reason it is catalog data and not a rule.** Two rows on one address is ORDINARY in
most frameworks, and this repo's own fixture has such a pair: `@KafkaListener` on a class
with `@KafkaHandler` on its methods dispatches by PAYLOAD TYPE, so `order-polymorphic` is
served by `ClassLevelListener#onDefault` and `#onEvent` together and Spring Kafka is
perfectly happy. A global "duplicates are conflicts" rule would open with a false finding
against correct code — the defect class W13, W14 and six of W19's probe findings all
share. So only `spring-web` and `spring-mvc` declare `mapping.duplicate: conflict`, and
they do because only their annotations reach `RequestMappingHandlerMapping`, whose
`validateMethodMapping` throws `IllegalStateException` at startup rather than choosing.

**What is compared, read from Spring's own bytecode.** `RequestMappingInfo.equals`
(spring-webmvc 6.1.6) compares **seven** conditions: patterns, methods, params, headers,
consumes, produces, and a custom condition. **Five and a half are readable here.** Three
are already columns on the endpoint row; `params`/`headers` are attributes of the mapping
annotation, named by the catalog as `discriminators`, read from the EFFECTIVE annotation
set so a composed, folded or interface-inherited one is not missed, and UNIONED across the
class and method levels because `ParamsRequestCondition.combine` adds one expression set
to the other.

**The half is the methods condition**, and it cost a false positive to find.
`RequestMethodsRequestCondition.equals` compares the DECLARED set, and an empty set is not
equal to `{GET}` — so `@RequestMapping("/x")` and `@GetMapping("/x")` are two mappings,
both register, and a GET resolves to the more specific one. What reaches this pass is
`derive_endpoints.sql`'s eight-verb EXPANSION of that set, and comparing a single expanded
verb collided them and named an `IllegalStateException` against a module that starts.
`_verbs_of` groups the rows back into the set, which recovers the comparison for every
case but one: a mapping listing all eight verbs explicitly expands to the same eight rows
as one listing none, and Spring holds those to be different.

**The seventh is a stated boundary that silences the analysis rather than guessing.** A
custom `RequestCondition` arrives through a `RequestMappingHandlerMapping` subclass and is
code, not an attribute, so two mappings separated only by one are indistinguishable from a
genuine conflict. Any such subclass anywhere in the analysis — including in a scanned
DEPENDENCY — silences the detector entirely: a finding named against a service that starts
perfectly well is a claim, and a missing finding is not. It reaches only what was scanned,
so a module extending a framework subclass that lives in an unscanned jar is NOT silenced,
which is the one over-report this boundary leaves and needs dependency scanning to close.

**Measured base rate, taken before a line was written:** across the orders-service fixture
and `mall-admin`, `spring-petclinic-rest` and `jhipster-sample-app` — **zero genuine
conflicts**, and **zero uses of `params=` or `headers=` anywhere**. The discriminators
exist to keep a future finding honest, not to explain one already there. The fixture's own
`RoutingConditionsController` now carries the case nothing else in six repositories did:
three handlers on one path and verb, separated by `params` and by `headers`, which Spring
registers and this reports nothing about.

### 3a-v. Serving and calling one identity is a question, not one row (F5 §6.1)

A wire identity a module both exposed and called used to collapse into a single row with
`direction: both`, keeping the handler and carrying the caller and its address onto it.
That asserts the thing called IS the thing served — a claim about the far end of a call,
which is the one thing a module's own bytecode cannot show. And the merge keyed on
`(protocol, method, path)` alone, because **`peer` is not part of endpoint identity**
(RC-5), so a path this module serves collided with the same path anywhere in the world.

**Measured on the orders-service fixture: six merged rows, two of them wrong.**

| Merged row | What the single row said | What is actually there |
|---|---|---|
| `{http://orders.example.com/ws}placeOrderRequest` | one endpoint, `peer: ${soap.billing.uri}` | the module SERVES this operation, and separately CALLS the billing service; they share a QName because they share a payload type, which is not identity |
| `POST /v1/orders` | one endpoint, `peer: orders-loop` | served here; called at `orders-loop`, which is somewhere else |
| `order-events`, `order-audit`, `order-returns`, `order-notifications` | one endpoint, no peer | genuinely self-publish/self-consume — the case that made the merge look right |

The six rows became twelve (141 endpoints to 147), and `resolve/self_exchange.py` files a
`self_exchange` open question naming each side and the address it reaches.

**It is asked rather than answered because both readings are real and the evidence does not
separate them.** A service that publishes to a topic and reads it back genuinely is one
identity in both directions; a client calling another service's copy of a path this module
also serves genuinely is two. Curation or the linking tier — where a schema match or a
person can justify the claim — decides. `Direction.BOTH` stays in D00 §4 for that tier and
**no pass here produces it**.

**One gap retired by name** (spec ruling I3):
`merged_endpoints_keep_only_the_handlers_contract` said a path the module both exposes and
calls keeps only the handler's declared contract, discarding the client's where the two
differ. There is no merge to discard it any more — each row keeps its own — so the gap is
gone rather than narrowed, and nothing takes its place.

**The other half of F5 §6.1 was NOT already true, and W27 published that it was.** The
claim rested on `derive_endpoints.sql`'s `unioned`, whose `GROUP BY ALL` does include
`caller` and `peer` — but that is the ANNOTATION-DRIVEN path, and every outbound HTTP call
in the estate comes from the call-site engines, which keyed on
`(protocol, direction, verb, path)` with a `seen` set spanning the whole module.

Measured: two callers, two hosts (`alpha.internal`, `bravo.internal`), one path — **one
row**, with the second caller dropped outright. No row, no peer, no gap row, no question.
That is RC-5 again — identity compared without `peer` — in a second location, and with a
worse failure mode than the merge it replaced: the merge at least carried the caller onto
the surviving row.

`caller` and `peer` are in the key now, in `single_call`, in `fluent` and in
`derive_call_endpoints.sql`'s cross-batch guard. "Collapse only within one caller, where
both sides are observable" holds: one method calling one target twice is still one row.
**Four rows the fixture had been losing came back** — a second caller on
`/v2/inventory/levels` and on `/v2/inventory/reserve`, `EventProducers#sendKeyed`'s own
`order-events` publish, and a SOAP call to a DIFFERENT billing address that had been
collapsing into the first. `fixtures/orders-service`'s `SharedPathClients` now carries the
shape nothing in six repositories had.

### 3a-iv. A payload whose contract is in its accessors, not its fields (F4 §5.2)

`Page<T>` and `Slice<T>` are **interfaces**. An interface declares no fields, and shape
expansion read fields only — so the most common paginated Spring response expanded to a
shape with **zero fields however well the type was reached**. Naming spring-data-commons
in `extract_libraries` changed nothing: the class file was read, `origin_tier` came out
`dependency`, and the shape was still empty. G-66 recorded this and **stated the wrong
cause** — "declared as wrappers nowhere" — which is the correction worth keeping, because
the remedy it implies is a fabrication. A `wrappers` entry means *this type vanishes on
the wire*. That is true of `ResponseEntity` and false of `Page`: Spring sends
`{content: [...], totalElements: ...}`, and spring-data-commons 3.5 added `PagedModel<T>`
— `{content: List<T>, metadata}` — precisely so that envelope would serialise stably.
Rooting through `Page` would publish `OrderView` as the response body, a contract no
handler produces, trading a visible under-report for an invisible over-report.

What these types actually share is that their wire contract lives in **bean accessors**.
The shape model now declares which methods name a property (D02 §2f), and expansion reads
them **where a type's fields describe nothing** — fields keep every shape that already had
one, so nothing that worked before changed.

**Measured, on the fixture with the jar in reach:** `Page<OrderView>` went from an open
shape with 0 fields to a closed one with **11**, `content` an **array of `OrderView`** —
the payload type reaching the reader at last — beside `totalElements`, `totalPages`,
`number`, `size`, `numberOfElements`, `pageable`, `sort`, `first`, `last`, `empty`. That
is the JSON Spring sends, field for field. `Pageable` and `Sort` expanded in turn, by the
same rule.

**The rule is Jackson's, read from Jackson's bytecode** rather than from its
documentation: `is` names a property only on a boolean (`findNameForIsGetter`), a bare
`get()` names nothing, and the leading run of capitals is lowercased whole before the
remainder is appended (`legacyManglePropertyName`, so `getURLValue` → `urlvalue`).
Accessors are collected across the **scanned ancestry** in JVMS 5.4.3.3's order —
`getContent()` is on `Slice`, not on `Page`, so a rule reading only the named type would
publish page metadata with the content missing.

**Boundaries, both stated rather than hidden.** A type this workspace never read gains no
accessors, exactly as it gains no fields: the fixture names spring-data-commons in no
`extract_libraries`, so its own `Page<OrderView>` response stays open with zero fields and
`Page` is still reported as a type nothing could expand. And substitution is by variable
NAME across the ancestry, so a hierarchy that renames its type variable leaves the
inherited field holding an unbound one — undescribed, shape open, which is the answer it
had before this existed.

**What it costs, measured:** nothing on a corpus that does not need it. The accessor map
is read on the first ask rather than on construction, and `derive_shapes` runs once per
catalog — so building it eagerly scanned every method symbol and walked the whole type
graph forty-odd times to answer nothing. On `mall-admin`, whose payload types all carry
fields, that was **15s of a 90s resolve**; lazily it is 74.7s against a 75.8s baseline
measured with the rule removed outright, which is inside the run-to-run noise.

**HATEOAS is covered by the same rule and measured by nothing.** `EntityModel`,
`CollectionModel` and `PagedModel` appear in **zero files across all six corpora**, so no
claim is made about them here.

### 3a-ii. "The body is not here" now says WHICH kind of not-here (F3 §4.2)

One word did three jobs, and that is what made it a fabrication rather than a gap. A call
whose body the workspace had not read, a call whose owner it had never scanned, and a call
whose method is declared on a superclass it DID scan all produced the same answer: no
callee, `resolved`, "the call IS the terminal". The third is false — the body is in the
workspace, one hop up.

`method_resolution` states the reason for every method a call site names, from a closed
set of four: `declared_here`, `inherited` (with the declaring class), `ancestor_not_scanned`
and `owner_not_scanned`. `type_hierarchy` carries the ancestry it resolves over, including
**whether each ancestor was scanned** — which is the column that separates the last two.

Measured, JVMS 5.4.3.3 over the scanned closure. **Two denominators, and an earlier
version of this table mixed them**: `method_resolution` holds one row per distinct
(class, name, descriptor), while a reader cares how many CALL SITES change. Both are
below, and both are read off the shipped tables rather than a script beside them.

| corpus | | `declared_here` | `inherited` | `ancestor_not_scanned` | `owner_not_scanned` | `dynamic` |
|---|---|---|---|---|---|---|
| `spring-petclinic-rest` | methods | 341 | **38** | 0 | 234 | — |
| | call sites | 751 | **131** | 0 | 2071 | 84 |
| `fixtures/orders-service` | methods | 191 | 2 | **33** | 317 | — |
| | call sites | 444 | 2 | **158** | 790 | 23 |

An `invokedynamic` site gets no `method_resolution` row at all — its target names the
bootstrap factory rather than a callee — so those sites are counted in their own column
rather than folded into a reason. The first draft of this table folded them into
`owner_not_scanned`, which attributed a reason to the very sites the writer declines to
give one, and separately dropped `<init>` from `declared_here` without saying so.

- **Petclinic's 131** are hand-written inherited accessors — `Owner#setId`, where `setId`
  lives on `BaseEntity`. Every one of them used to read as a third-party boundary; every
  one now reaches a body a reader can open.
- **orders-service's 158** are generated code — 101 protobuf, 57 Avro — extending
  supertypes that live in jars. They are still terminals, and that is correct; what
  changed is that they no longer look identical to a call into a library we never heard
  of. A reader can see the body is inherited from something unopened, and which type.

**What this does not do** is resolve into a jar. An unscanned ancestor stays unscanned;
the answer is a better-stated boundary, not a new source of bodies.

### 3a-i. A catalog row is not tied to a library version by accident (F2 §4.1)

A `descriptor:` in a catalog is compared on its **parameter types only**. JLS 8.4.2
identifies a method by its name and parameter types; the return type is in the JVM
descriptor and is not part of the signature.

**This was a real, whole-major-version hole.** Comparing whole descriptors made every
row version-dependent by accident: a library that changes a return type changes nothing
in its callers' source and the descriptor entirely. `spring-kafka-template`'s ten
`send`/`sendDefault` rows declare `CompletableFuture`, which is Spring Kafka **3.x** —
the identical call in a 2.x module returns `ListenableFuture`, matched no row, and
because any row declaring a descriptor CLAIMS that arity, it fell through to nothing at
all rather than to a looser sibling. Every Spring Kafka 2.x producer derived silence.
Sixteen rows across two catalogs carried a `CompletableFuture` return and were exposed
the same way.

Measured before the change and held by
`tests/architecture/test_catalog_descriptor_identity.py` after it: across all 96
declared descriptors, no two rows share a catalog, owner, name and parameter list while
differing only in what they return, so dropping the return type introduces **zero**
ambiguity. A covariant-return bridge does put two such methods in one class file, but
call sites are disambiguated by owner — already part of the match — and the bridge
delegates, so both are semantically one method.

**What this does NOT do** is make a rule version-independent. A method that exists in
3.x and not in 2.x is still absent; that is what each catalog's `measured:` block and
the resolved dependency versions state, and it must not be asked to carry weight that
belongs to getting identity right.

### 3b. What each catalog does NOT read — the declared slices

`3a` says which versions a catalog's rules were measured against. It does not say how
much of the framework those rules cover, and **presence in that table never meant
completeness**. Measured (`scripts/probes/w19_catalog_surface.md`, which enumerates each
owner's declared methods out of the jar and cross-references the catalog as loaded):

| catalog | owner | reads | of those unread, can address a wire |
|---|---|---|---|
| `spring-jms-template` | `JmsTemplate` (spring-jms 6.1.6) | **5 of 49** | 7 |
| `spring-jms-template` | `JmsOperations` | **5 of 10** | 5 |
| `spring-rabbit-template` | `RabbitTemplate` (spring-rabbit 3.1.4) | **4 of 88** | 17 |
| `spring-rabbit-template` | `AmqpTemplate` (spring-amqp 3.1.4) | **4 of 8** | 4 |
| `spring-sqs-template` | `SqsTemplate` (spring-cloud-aws-sqs 3.1.1) | **1 of 12** | 7 |
| `spring-sqs-template` | `SqsOperations` | **1 of 4** | 3 |
| `spring-pubsub` | `PubSubTemplate` (spring-cloud-gcp-pubsub 5.1.2) | **11 of 20** | 0 |
| `spring-webflux-router` | `RouterFunctions$Builder` (spring-webflux 6.1.6) | **0 of 20** | 14 |
| `spring-webflux-router` | `RouterFunctions` (spring-webflux 6.1.6) | **1 of 8** | 7 |
| `spring-mvc-router` | `RouterFunctions$Builder` (spring-webmvc 6.1.6) | **0 of 20** | 14 |
| `spring-mvc-router` | `RouterFunctions` (spring-webmvc 6.1.6) | **1 of 6** | 5 |
| `aws-sqs-sdk` | `SqsClient` (sqs 2.25.31) | **1 of 29** | 24 |
| `aws-sqs-sdk` | `SqsAsyncClient` | **1 of 28** | 24 |

**A raw ratio overstates every one of these** — most of what a template declares is
configuration and lifecycle, and a method taking no destination cannot address a wire.
The counts include INHERITED methods: `SqsTemplate` declares ten of its own and gets its
whole messaging surface from `AbstractMessagingTemplate`, and an earlier run of this
enumeration missed that and published a `0` in the last column for a catalog whose entire
inbound direction is unread.
The last column is the number that matters, and each of those methods is now named
individually in its catalog's `slice.outside` with the reason it is outside
([D02](components/D02-catalog-schema.md) §1c). The four headline absences:

- **`RouterFunctions.route()`'s builder DSL derives nothing** — 0 of 20, and it has been
  the reference documentation's recommended Java shape since Spring 5.2.
- **An SDK-level SQS consumer is invisible** — `SqsClient.receiveMessage` is unread, so a
  module that only consumes looks like one that does not touch SQS.
- **`SqsAsyncClient` is read for one call only.** Since `G-43`, `sendMessage` is read on
  BOTH clients — `matches.terminal` names `SqsClient` and `SqsAsyncClient` together as the
  builder chain's terminal owner — but the other 27 methods on the async client, including
  the entire inbound direction, are unread exactly as they are on the sync client.
- **The JMS, AMQP and SQS templates model the send half only.** Every `receive`, every
  request/reply form, and — for SQS — every asynchronous and batch send, derives nothing.

**Three more slices are declared, and they are not about methods** — so they are
enumerated separately (`scripts/probes/w19b_type_and_annotation_surface.md`):

| catalog | surface | reads |
|---|---|---|
| `spring-integration` | channel-declaring annotations (spring-integration-core 6.2.4) | **7 of 11** |
| `spring-data-rest` | repository contracts across 12 Spring Data artifacts | **7 of 28** |

- **`spring-integration`'s cost is bounded**: it mints no endpoint rows, it files
  `channel_destination` questions, so four unread annotations under-report a QUESTION
  list rather than producing four wrong rows. Two further gaps are recorded rather than
  closed: `@InboundChannelAdapter("orders")` — the shorthand, whose `value()` is an
  `@AliasFor` of `channel` — filed no question at all until this change added the second
  row, and both annotations this catalog reads are `@Repeatable` while `config_join` has
  no container vocabulary, so a repeated one still drops (`OI-66`). `@BridgeFrom` and `@BridgeTo` carry their
  channel in a bare `value()`, which the enumeration's attribute-name test cannot see —
  declared in the slice anyway, and emitted into the table so the audit holds them.
- **`spring-data-rest`'s roster IS the whole rule.** A `derived_resource` match has no
  other evidence, so a contract missing from the roster removes the row entirely rather
  than degrading it. `MongoRepository` is now read (7 of 28); every R2DBC, Cassandra,
  Elasticsearch and Neo4j repository still derives nothing, and so does every reactive,
  coroutine and RxJava3 one — including `ReactiveMongoRepository` and those declared in
  `spring-data-commons` beside the contracts the roster does name.
  *Scoped to a module-local fact stream: a repo declaring `extract_libraries` for one
  of these artifacts may cross the jar hop for the contracts whose parents the roster
  does name. Not measured — named so the claim is not read as absolute.*
- **`netflix-dgs` is a stated boundary, not a slice** (`OI-67`). A fetcher declared on
  a superclass METHOD registers on every subclass bean and we do not see it — measured
  from DGS's own registration code, which calls
  `ReflectionUtils.getUniqueDeclaredMethods`, whose `doWithMethods` walks
  `getSuperclass()` and `getInterfaces()`. *All five DGS annotations are also
  `@Inherited`, three more than the gap analysis recorded — and that bit is INERT on
  four of them, because `@Inherited` has no effect on anything but a class and these
  declare `@Target(METHOD)`. The mechanism first written here was that one, and it does
  not exist; the fix is a superclass method walk, not `@Inherited` resolution.* The
  catalog reads every NAME, so there is nothing to put in `slice.outside`.

This table is not maintained by hand: `tests/architecture/test_catalog_slice_coverage.py`
fails if the enumeration lists an addressable method no slice accounts for, and fails the
other way if a slice names a method the enumeration no longer lists. It holds the catalogs
to the last measurement — re-reading a new release's bytecode means re-running BOTH
enumerations, `scripts/probes/w19_catalog_surface/run.sh` for the method surfaces and
`scripts/probes/w19b_type_and_annotation_surface/run.sh` for the annotation and
repository ones, neither of which `scripts/check.sh` does.

### What this does not tell you

- **A measured version means the RULES were read at it, not that a project on it was
  analysed end to end.** The field corpus (`scripts/field_check.py`) is where that is
  proved, and it currently holds three projects, all inbound HTTP.
- **Spring Boot 2 / Spring Framework 5 is ruled in scope and is measured almost nowhere.**
  The only pre-Jakarta evidence in the table is Tomcat 9 for `javax-servlet`. Everything
  else Spring is 6.1.6 and later.
- **A catalog with no `measured:` block is not a catalog without a version bound.** Some of
  them are bounded by a library Sextant itself ships and declares in `pyproject.toml` —
  protobuf through `grpcio-tools`, GraphQL SDL through `graphql-core` — so the bound exists
  and is findable; it has just never been written into the catalog. Others genuinely rest on
  framework knowledge read from documentation. **Separating the two per catalog is deferred
  work, not unknowable work**, and until it is done this table reports what we have
  RECORDED rather than what could be determined.

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
| **gRPC** | **Fixed by the protocol** | `compiler` | Protobuf, always. The only certain cell in this table. | ✅ **rung 1, the third live surface** (2O). `format_fixed: {grpc: protobuf}` ships on `grpc-schema.yml`, so every gRPC row answers `protobuf`/`resolved` before any other rung is consulted — both the Task 4 schema-derived operation rows and the Task 5 bytecode-detected `<Service>Grpc`/`@GrpcClient` rows (§5.7) reach it |
| SOAP | Fixed | `compiler` | XML | ✅ **rung 1, the second live surface** (2I). `format_fixed: {soap: xml}` ships on all five catalogs owning the protocol, so every SOAP row answers `xml`/`resolved` before any other rung — including the schema-first rows, which carry no bytecode type for a later rung to read |
| GraphQL | Fixed | `compiler` | JSON | ✅ **rung 1, and its first live surface** (2H). `format_fixed: {graphql: json}` ships on all four catalogs owning the protocol, so every GraphQL row answers `json`/`resolved` before any other rung is consulted |
| **REST in** | `produces` / `consumes`, JAX-RS `@Produces` / `@Consumes`, or a return type that is itself a generated message | `declared` | **Assumed** from the framework's default converter (Jackson → JSON) | ◐ **rung 2** off Spring's own `produces`/`consumes` (2E), `resolved`; an undeclared route falls to **rung 5** — `json` at `narrowed` — where it carries a declared payload type at all, and to rung 6 where it carries none. Rung 5 reads its markers three ways since **2O**: a package family named by ANY fqn the module names (annotations, and now the call-site owners it invokes), plus a **dependency coordinate** the analysis recorded — Boot auto-configures the converter from the jar's mere presence (CP-6), so a module with no Jackson annotation and no Jackson call still answers `json`/`narrowed` where the coordinate was read. JAX-RS `@Produces` is **A**, with that catalog |
| **REST out** | `Content-Type` / `Accept` set somewhere in the client chain | `syntax` | **Assumed** JSON | **not read** — no client chain's `Content-Type` reaches `consumes`/`produces`, so outbound rows answer at rung 5 (`json`, `narrowed`) or rung 6. Rung 5's widened marker read (2O, above) reaches these rows too: it is a fact about the module, not about the row's direction |
| **Kafka** | **Serializer configuration** — `key.serializer` / `value.serializer`, or the generic parameters of `KafkaTemplate<K,V>` and the `@KafkaListener` payload type | `config_join` | Unknown. Kafka carries anything. | ✅ **rung 3**, from the serializer table below as catalog data (`format_from`), `resolved` — off the **value** serializer/deserializer keys the shipped rules name. The record **key**'s own serializer and the **generic parameters** of `KafkaTemplate<K,V>` are not read: configuration, and the value side of it, is the whole of it |
| SSE | `text/event-stream` framing; the payload inside each event is separate | `declared` | Assumed JSON per event | ✅ **shipped, and the framing answers nothing** (2H). `text/event-stream` is deliberately absent from `media_formats` — it is the envelope, so it names the PROTOCOL (`protocol_hint`) and never the format. The per-event payload lands at **rung 5**, `json` at `narrowed`: the "assumed" in the column to the left, finally carrying its marker |
| WebSocket | A negotiated subprotocol, or nothing — usually only the parse call | `syntax` | Unknown | ◐ **the protocol shipped, the format did not** (2H). A raw frame is untyped by declaration, so a `@ServerEndpoint` row reads `unresolved` rather than guessing; a STOMP row carries a real payload parameter and answers **rung 5** (`json`, `narrowed`). No subprotocol is read, and no parse-call rung reaches a frame |
| **Pub/Sub** | Nothing. The message is `bytes`. Only the **parse call** reveals it — `Order.parseFrom(data)` versus `objectMapper.readValue(data, Order.class)` | `syntax` | Unknown | the parse-call binding is built and protocol-neutral, but **not reached here**: the shipped bytes-payload vocabulary is `String` and `byte[]` only, and a `MessageReceiver`'s payload parameter is a `PubsubMessage` envelope |
| **SQS** | Nothing. The body is a string; same as Pub/Sub | `syntax` | Unknown | ✅ **the parse call**, binding the payload type — which, where that type is schema-described, then answers **rung 4** at `narrowed`, and otherwise makes the row an ordinary rung-5 one |
| JMS | `TextMessage` / `BytesMessage` / `ObjectMessage`, then the parse call | `syntax` | Unknown | ✅ as SQS, for a `String`/`byte[]` payload parameter. The **message-type distinction** (`TextMessage` versus `BytesMessage`) is not read |
| **AMQP** | Nothing on the wire declaration. A message body is `byte[]` plus a `content_type` property set at publish time, which no annotation carries | `syntax` | Unknown | ◐ **the protocol shipped, the format did not** (2O Task 7). `spring-rabbit.yml` and `spring-rabbit-template.yml` derive the rows; nothing reads a format for them, so they answer at rung 5 or 6 like every other broker row whose payload parameter is an ordinary type |
| **Pulsar** | The consumer's `schemaType` attribute, and the Pulsar `Schema<T>` a template is built with | `annotation` + `config_join` | Unknown | ◐ **the protocol shipped, the format did not** (2O Task 7). `spring-pulsar.yml` derives the rows. `@PulsarListener.schemaType` is **not read**: it is an enum-valued attribute naming a schema family (`JSON`, `AVRO`, `PROTOBUF`, `NONE`), and no `format_from` rule is declared for it — a boundary, not an absence of evidence |

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
| XML | XSD, WSDL | repository **only** — a contract file compiles into no class, so there is no second origin | namespace + element name, as one QName that is both the shape's `symbol` and its `schema_name` | ✅ since Phase 2I, at `declared`. One reader claims both extensions and one interpreter branch merges every contract file in the module into a single type universe before projecting — **stdlib `ElementTree`, no new dependency**. Global elements and named complex types become shapes; `minOccurs="0"`, `nillable`, unbounded repeats and enumeration facets become presence, nullability, arrays and enum symbols; **`field_number` is NULL — the format numbers nothing** |
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
| **protobuf** | `parseFrom` on a generated message | the call's **receiver** | ✅ matched by the receiver's **hierarchy**, never by a name pattern — a rule keyed on a generated class's spelling would have to know how the code generator names its output. Since `A-M12` the hierarchy walk reads capability 9.13's erased `superclass` edge beside `supertypes` and `implementations`, so a payload whose only route to a marker is a plain `extends GeneratedMessage` binds instead of silently keeping its bytes shape |
| **Jackson 2** — `com.fasterxml.jackson` | `ObjectMapper#readValue` | the `Class<T>` literal argument | ✅ |
| **Jackson 3** — `tools.jackson` | `ObjectMapper#readValue`, `JsonMapper#readValue` | the `Class<T>` literal argument | ✅ — the whole relocation between the two generations is a package rename, so it cost **three catalog rows and no code**, and both package families are also listed as `json_default_markers` for the framework-default rung, joined since **2O** by a third marker in the coordinate FORM (`com.fasterxml.jackson.core:jackson-databind`) for the module that carries the jar and names none of its packages. Pinned against real compiled `tools.jackson` bytecode in the fixture, not only against an invented owner in a unit test |
| Avro | `SpecificDatumReader` construction | the `Class<T>` literal argument | catalogued and **inert** — see below |

**The escape is a USER ACTION, so it is in the usage docs too** (§8.1 rule 3): `README.md`'s
"Re-analyse after an upgrade" tells the person who can actually change the outcome that a
workspace an older version wrote is not comparable with one this version writes, and why. A
COVERAGE row records what we can see; the README is where the reader who can re-run `analyze`
will look.

**Every dimension of an array reaches the facts** (`A-M10`, principles sweep §3.3). The
extractor built an array's symbol and its single type argument from ASM's `Type#getElementType`,
which returns the **innermost** element type rather than the component type — so exactly one
`[]` was appended however many the descriptor carried, and `String[][]` and `String[]` produced
byte-identical facts. JVMS 4.3.2 and JLS 10.1 make the number of `[` part of the type's
identity, so a DR-5 contract comparison of a caller sending one against a callee expecting the
other read **equal**, and the shape hashed for the payload was the wrong one. The descriptor
path is the one every plain array takes — javac writes no `Signature` attribute for one — and
the signature path, which recurses a dimension at a time, was right all along; the two seams
disagreed with each other. Both now drop one leading `[` and recurse. `domain/symbols.py`'s
`type_descriptor("byte[][]")` already produced `byte#[][]`, a string the extractor never
emitted; the two agree now.

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
- **JSON Schema is out** — `json_schema` reserved and refused (§4.2 above). XSD was out of
  2G for the same reason and is no longer: Phase 2I reads it as half of a SOAP contract
  (§5.3), which changes nothing about the reserved value.
- **Rung 5's presence test is annotation-only.** The framework-default rung fires when an
  annotation from a declared converter package family appears anywhere in the module. A
  module that uses a JSON converter through code alone — no annotation from its package
  family anywhere — reads `unresolved` where the converter is in fact on the classpath.
  Presence evidence, honestly narrow.
- **~~A merged `both` row carries ONE format column, and it can hide a per-direction
  split.~~ Retired by W27** (F5 §6.1). This caveat said that where a module both consumes
  and produces one destination with different serializers configured per direction, the
  ladder's rung order decides what the single column says — a media type carried through
  the merge settling it before the serializer rung is consulted — and that a reader must
  not read a merged row's `format` as a statement about both directions. It was not a
  hypothetical: this repo's own fixture publishes JSON to `order-events`/`order-audit`/
  `order-returns` and consumes **protobuf** from them, and the merged rows all read
  `json`, because the producer's `application/json` was carried onto the inbound half and
  answered at rung 2 before the consumer's configured deserializer was reached. There is
  no merged row now — each direction is its own row and answers off its own evidence, so
  the outbound halves read `json`, the inbound halves read `protobuf`, and the
  disagreement is on the page instead of behind one confident answer.
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

## 5. The checklist

The work list. **§5.1 to §5.12 are the PROTOCOL axis** — each row one library in one
language: what it looks like, what shape it is, what it costs. §5.13 onwards are the other
axes.

### The axes, and why there is more than one (F6 §7.2, W41)

For four phases this section had **one axis, and the axis was protocol**. That is a
structural limit rather than an editorial one: a cross-cutting item had nowhere to be a row
at all. A Kotlin language construct is not a protocol; neither is a payload wrapper, a
configuration key, a trace, the bundle, the open-question ledger, the rendered document, or
a finding about the code's shape. So each of those was committed somewhere — a requirement,
a design document, a roadmap line — and enumerated NOWHERE, which is how twelve committed
items came to have no support level anybody could look up. The gap analysis lists all twelve
(`docs/java-kotlin-delivery-list.md`, RC-4); every one of them is a row below.

| Axis | Section | First column |
|---|---|---|
| Protocol | §5.1 – §5.12 | Language |
| Language construct | §5.13 | Construct |
| Shape and contract | §5.14 | Surface |
| Configuration source | §5.15 | Source |
| Trace and diagram | §5.16 | Surface |
| Bundle and export | §5.17 | Artifact |
| Question ledger | §5.18 | Entry |
| Rendered document | §5.19 | Section |
| Query and findings | §5.20 | Report |

**The first column is never `Language` outside the protocol axis, and that is load-bearing
rather than a style choice.** `scripts/coverage_matrix.py` builds §2's matrices by reading
every `### 5.x` heading and counting rows whose first cell names a language; a non-protocol
row starting with `Java` would be counted into a cell §2 has no column for and then dropped
on the floor. The generator now REFUSES a §5 section it has no column for unless the section
is declared non-protocol, so this cannot become silent.

**Support levels.** Every row outside the protocol axis carries one of three, and the
protocol axis keeps its own tier vocabulary (§2's legend) because a tier there says *when we
will catalogue this library*, which is a different question:

* **supported** — shipped, with a row or a passing test naming it.
* **partially supported** — shipped, narrower than the thing it names; the row says what
  falls outside.
* **unsupported** — no producer. The row says what is committed and what it would take.

**W42 completes the enumeration.** W41 builds the axes and homes the twelve items that had
nowhere to live; the remaining sets the design names — Q2's Kotlin boundaries in full, Q3's
four out-of-scope surfaces, Q4's six slices, and F1's `deliberately-not-read` residue —
arrive there.

### 5.1 REST inbound

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@RestController` / `@Controller` + `@GetMapping` etc. | annotation on class + method | `annotation` | ✅ shipped |
| Java | **`@RequestMapping(method = RequestMethod.GET)`** | the pre-4.3 form | `annotation` | ✅ shipped |
| Java | `@RequestMapping` naming no method | Spring accepts every method, so it is one endpoint per method, not one with an unresolved method | `annotation` | ✅ shipped |
| Java | `path =` alias for `value =` | `@AliasFor`, so only the one typed reaches the bytecode | `annotation` | ✅ shipped |
| Java | `produces` / `consumes` | — | `annotation` | ✅ shipped |
| Java | `produces` / `consumes` declared on the CLASS-level `@RequestMapping` | `ProducesRequestCondition.combine` keeps the method's declaration when non-empty and the class's otherwise, never a union | `annotation` | ✅ shipped (2026-09-12) — **read off the prefix annotation and applied where the method declares none.** Until then the class-level value was dropped: `produces = "application/xml"` on the class derived `produces` NULL, and a Boot module with Jackson present would have called that route `json`. Pinned by `tests/e2e/test_rest_inbound_delivered.py::test_class_level_produces_reaches_every_handler_that_declares_none` |
| Java | Spring 7 `version = "1.1"` / `"1.2+"` on `@RequestMapping` | API versioning | `annotation` | A |
| Java | Micronaut `@Controller` + `@Get`/`@Post`… (`value`/`uri` String, **`uris` String[]**) | `@Controller` carries the prefix and class-level media; the eight verb annotations carry the path (`value`/`uri`/`uris`) and, on five of them, media — `@Options` has `consumes` only, `@Head` and `@Trace` neither (W58 rows 33-44) | `annotation` | ✅ shipped (`micronaut-http.yml`, micronaut-http 4.7.6, `scripts/probes/w58_micronaut_quarkus_annotations.md`). Pinned on `fixtures/orders-micronaut` by `tests/e2e/test_rest_inbound_delivered.py`. **Boundary:** Micronaut's normalisation of `@Post(uri = "/")` under a prefix is unmeasured, so the fixture does not exercise it |
| Java | Quarkus / JAX-RS **`jakarta.ws.rs`** `@Path` + `@GET`… | `@Path` value is a scalar String | `annotation` | A |
| Java | Quarkus `io.quarkus.vertx.web.Route` | second Quarkus style: no type gate at all — any class with a `@Route` method is a bean; `@RouteBase(path)` is the prefix, `methods` is an `HttpMethod[]` of six (no `PATCH`), `@Route` is `@Repeatable` through `Route$Routes` | `annotation` | ✅ shipped (`quarkus-reactive-routes.yml`, 3.17.5, W58). Pinned on `fixtures/orders-quarkus`. **Two stated boundaries, both measured in `ReactiveRoutesProcessor`:** a `@Route` with no `path` serves `/` + the method name dashed (`helloWorld` → `/hello-world`), which no `path_fallback` word says, so it derives nothing rather than `/helloWorld`; and `@Route(regex = …)` is a pattern, not a path, and derives nothing |
| Java | Actuator `@Endpoint` / `@ReadOperation` / `@WriteOperation` / `@DeleteOperation` | address is the type's `id` under a constant `/actuator` prefix; verb is the operation annotation's own | `annotation` | ✅ **shipped** (2O Task 7) — every row of CP-5 confirmed live on Boot 3.5.10 and 4.1.1 (`scripts/probes/cp5_actuator_paths.md`), each column identified by the run's own Boot banner. **Read with the exposure row below: the addresses are correct, and served only where the module opted in** |
| Java | Actuator — `management.endpoints.web.base-path` moving the whole surface | CP-5 rows 7-8: `/manage/probe` is a 200 and `/actuator/probe` a 404 on both versions probed | `config_join` | **Boundary — OVER-reports the address.** `annotation_driven` never touches `resolved_config` — measured, it names the table nowhere — so a module that overrides the base path is published under `/actuator`. *The parenthesis here read "only `config_join.py:528` and `derived_resource.py:578` read it", which was false twice over: **five** modules read the table — `api.py`, the `config_join` and `derived_resource` engines, and `enrich/brief.py` and `enrich/validate.py`, every one of them by `workspace.query("resolved_config")` — and both line numbers had drifted. *(Corrected again on 2026-09-10: the first correction said SIX and named `resolve/config.py`, which WRITES the table and never reads it, and `resolve/pipeline.py`, which only carries the string as a capability name — while omitting `api.py`, which reads it twice. A replacement count reached by reading a grep for the table's name rather than for a read of it.)* The half that matters — that the ANNOTATION-driven engine does not — is what the boundary rests on, and it is checkable by name rather than by line.* Closes the day an annotation-derived row can read a configuration key |
| Java | Actuator — `management.endpoints.web.exposure.include`, which decides whether a custom `@Endpoint` is served over HTTP AT ALL | CP-5 rows 9-10, measured on both versions: with Boot's DEFAULT exposure (`health` alone) `/actuator/probe` is a **404** and absent from the discovery document, while `/actuator/health` is a 200 | `config_join` | **Stated dependency, NOT an over-report.** The endpoint is a code fact — declared, registered, and correctly addressed — and we report code, never deployment. Whether it is PUBLISHED over HTTP depends on `exposure.include`, whose default is `health` alone but which any deployment routinely overrides; that is a runtime property we cannot read from a repository and must not predict. Contrast Spring Data REST, which we DO gate: absent that dependency no code path exists to serve those routes, so the rule's precondition is unmet and the rule does not apply. Here the rule applies and a runtime switch controls visibility. §8 also forbids the inverse error — excluding on inference — and a default is not proof of absence. **Partially knowable later:** the key can live in the module's own `application.yml`, so a row able to read `resolved_config` could sharpen this; `annotation_driven` cannot today. **Falsified by** a Boot release changing the default, or by this catalog gaining the ability to read configuration |
| Java | Actuator — `@Endpoint(defaultAccess = Access.NONE)` | CP-5 row 11: exposed by `*` and still a **404**, still absent from the discovery document, on both versions | `annotation` | **Boundary — OVER-reports the row.** `prefix_from: [id]` reads the annotation's `id` and nothing reads its `defaultAccess`, so a deliberately closed endpoint is published exactly like an open one. **Falsified by** a `defaultAccess = NONE` endpoint appearing in an export; closes when an annotation attribute can GATE a row rather than only name one |
| Java | Actuator — `@Selector` path segments (`/actuator/env/{toMatch}`) | a path segment contributed by a PARAMETER annotation | `annotation` | **Boundary — the segment is dropped**, so such an endpoint is published at its bare id. `mapping` has no vocabulary for a name a parameter contributes; adding one closes it |
| Java | Actuator — `@WebEndpoint`, `@ControllerEndpoint`, `@RestControllerEndpoint`, `@ServletEndpoint`, `@EndpointExtension` | four more registration annotations and one extension mechanism, none probed | — | **Boundary — derives nothing.** Absent evidence, produce nothing (§8); each needs its own probe before it can be catalogued |
| Java | Actuator — the BUILT-IN endpoints (`/actuator/health`, `/actuator/info`, …) | their `@Endpoint` classes live in the actuator jar, not in the module | — | **Boundary — invisible until the user opts in.** They are ordinary `@Endpoint` classes, so the catalog reads them the moment their bytecode is scanned — which needs `extract_libraries`, a USER ACTION, documented in the usage docs rather than only here (§8.1 rule 3) |
| Java | `@RequestMapping` on an **interface or superclass** | Spring inherits mappings | `annotation` + hierarchy | ✅ shipped |
| Java | **Meta-annotations** — custom `@ApiGet` composed from `@RequestMapping(method = GET)`, and a custom `@MyApi` composed from `@Controller`/`@RestController` | Spring resolves transitively, on the METHOD mapping and on the type-level handler gate alike: `RequestMappingHandlerMapping.isHandler` is one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call, identical across spring-webmvc 6.1.6 / 6.2.15 / 7.0.2 / 7.0.9 (CP-11 Q2) | `annotation` (recursive) | ✅ shipped — the TYPE half only since `A-C7`; before it, string equality against one FQN deleted a custom-stereotyped controller's entire HTTP surface |
| Java | A controller whose stereotype is inherited from a `@Controller` SUPERCLASS or a `@Controller` INTERFACE, and which carries none of its own | `AnnotatedElementUtils.hasAnnotation` searches the type hierarchy, so `isHandler` answers **true** for both (measured) | `annotation` + hierarchy | **Boundary — derives nothing, deliberately.** `isHandler` is only half the question: a class is a handler when it is a handler-shaped BEAN, and `@Component` is not `@Inherited`, so whether component scanning admits such a subclass at all is **unmeasured** — the sweep records it as not settled. Deriving on the strength of `isHandler` alone would add rows on the framework's behalf under conditions nobody checked (§8.1 rule 4), and the honest answer until a probe runs is silence with this row beside it. **Falsified by** a live app in which a plain subclass of an `@Controller` base serves its inherited mappings. Closes by measuring the component scan, then walking `superclasses`/`implementations` for the gate the way the composition pre-pass now composes it |
| Java | **Server-side `@HttpExchange`** — an exchange interface a local CONTROLLER implements | `RequestMappingHandlerMapping` builds a mapping from `@HttpExchange` exactly as from `@RequestMapping`, through a `MergedAnnotations` search with `SearchStrategy.TYPE_HIERARCHY` — measured on spring-webmvc 6.1.6 / 6.2.15 / 7.0.2 / 7.0.9 (CP-7 Q2, `scripts/probes/cp7_http_exchange.md`) | `annotation` + [D02](components/D02-catalog-schema.md) §2c `resolves.direction` | ✅ **shipped** (2O Task 10). The interface's rows flip from outbound to INBOUND, at the composed address, handled by the implementing class's own method. Before it, the module was published as CALLING a service it serves, and after the SEI fence landed it was published as neither — a whole HTTP surface missing from the export |
| Java | The flip's condition — the implementer must be a CONTROLLER | `isHandler` is one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call, identical on all four minors and carrying **no** `@RequestMapping` disjunct (CP-7 Q1) | `resolves.direction` | ✅ shipped as the framework's own predicate. Spec §6 ordered `owner_implemented_in_module: true` instead, which is weaker: a `@Service` implementing an exchange interface is dispatched to by nothing, and an inbound row for one invents an endpoint (§8.1 rule 4). Meta-annotation aware through the composition pre-pass, so a module-local stereotype composed from `@Controller` flips; the HIERARCHY half of `hasAnnotation` is NOT mirrored, and aligns with the inherited-stereotype row above rather than widening it |
| Java | Server-side `@HttpExchange` — an interface a controller reaches through an ABSTRACT BASE, or through another interface | Spring resolves the whole hierarchy; `implemented_interfaces` records only what a class declares DIRECTLY (D00 §5a) | `resolves.direction` | **Boundary — derives nothing, and the fence still subtracts.** Both shapes need a within-module closure over `implementations`/`superclasses` that this rule does not walk. **UNDER-reports**, never fabricates: the routes are absent from the export rather than present with a wrong direction. **Falsified by** a module whose controller inherits its exchange interface; closes with a bounded closure over the two direct-only facts |
| Java | Server-side `@HttpExchange` — the interface lives in a DEPENDENCY jar | the contract is compiled elsewhere, so it carries no symbol or annotation fact in this workspace | `resolves.direction` | **Boundary — invisible until the user opts in.** The interface reads exactly like a local one the moment its bytecode is scanned, which needs `extract_libraries`, a USER ACTION documented in the usage docs rather than only here (§8.1 rule 3). The implementing controller's own `@GetMapping`s still derive; the inherited exchange routes do not |
| Java | Server-side `@HttpExchange` — TWO local controllers implementing one exchange interface | Spring refuses to start: two beans register one mapping | `resolves.direction` | **Boundary — one row, handled by the lexicographically first implementer.** A deterministic tie-break (NFR-1) for an application the framework itself will not run, stated rather than left to read order. **Tested since W54** (`G-110`): `test_endpoints.py::test_two_controllers_implementing_one_exchange_interface_derive_one_row` names the winner rather than only counting the rows, and fails when the sort is reversed — an untested determinism claim is the kind that decays without the output ever looking wrong. **Falsified by** an app that starts with two such beans |
| Java | Nested / inner classes | the phase-1 skip lifted in Phase 2C — read as ordinary class files, so `@RestController`/`@Controller` resolve the same nested or not | `annotation` | ✅ shipped |
| Java | WebFlux `Mono`/`Flux` return types | response shape roots through the declared wrapper ([D02](components/D02-catalog-schema.md) §2a) | — | ✅ shipped |
| Java | **Vert.x** `router.get("/x").handler(this::h)` | receiver + verb + first arg | `fluent_chain` | **B — the cleanest first exercise for chain reconstruction** |
| Java | WebFlux functional `RouterFunctions.route(RequestPredicates.GET("/x"), h)`, `coRouter { GET("/x") { … } }` | the static predicate factory attached by `RouterFunctions.route`, and the coroutine DSL's own two-argument form | `combinator` | ✅ shipped — all seven verbs on each, since `A-M9` |
| Java | **Spring MVC** functional `RouterFunctions.route(RequestPredicates.GET("/x"), h)`, Kotlin's `router { GET("/x") { … } }` | the same two DSLs one package along, in `org.springframework.web.servlet.function` | `combinator` | ✅ **shipped** (W44, `G-29`). A servlet application using functional routing derived NOTHING before this — its whole routing surface absent, with nothing saying so, while the reactive twin had shipped since 2E. **Measured against spring-webmvc 6.1.6 rather than mirrored**: the two packages really are structurally identical here, and W43 is the cautionary case where a twin's own descriptor was wrong for its sibling. The one thing a copy would have got wrong is the Kotlin entry point, which is `router`, not `coRouter`. Live on the fixture: `GET /mvcfn/invoices` with `produces`, `POST /mvcfn/invoices` with `consumes`, and `PUT /mvcfn/invoices/{id}` |
| Java | Either package's `RouterFunctions.route()` **builder** DSL | the verb sits on a RECEIVER returned by an argument-less `route()` | `combinator` | ✅ **shipped** (PR A1, `G-37`). Every verb `RouterFunctions$Builder` declares reads on both packages, all four shapes a chain can take (one long chain, one statement per verb, a mix of the two, or a chain split across an owning method and its caller), plus `nest`/`path`/a mid-chain `filter`/`add`, and the handler-less `resources`/`resource` forms — 20 of the 20 methods declared, on each package (`scripts/probes/w19_catalog_surface.md`). Pinned by `tests/e2e/test_rest_inbound_delivered.py::test_the_builder_form_derives_every_route_on_both_stacks`. **Stated boundaries, not blockers** (register: REST inbound, spec §7 case 4): a statement-form builder held in a FIELD or received as a PARAMETER derives nothing, indistinguishable from a body; an undeclared statement-form head yields one unresolved row per statement (N+1, never deduped); a method both linked as a lambda body and served on its own loses its own row, folded under the prefix only; a mixed-form builder's unresolved shared route is counted twice, since identity-unknown rows never dedup |
| Java | WebFlux functional — the BUILDER DSL, `RouterFunctions.route().GET("/orders", h)` | `RouterFunctions$Builder` declares seven verbs x four overloads (`javap`, spring-webflux 6.1.6) | `combinator` | ✅ **shipped** (PR A1, `G-37`) — the reactive package's half of the row above. **This row used to say the call was undeclared in `spring-webflux-router.yml` and unprobed; both are now false**: the catalog declares all four overloads per verb (`arity`/`arg_types`), and the w19 probe reads 20 of 20. See the row above for the stated boundaries that remain |
| Java | WebFlux functional — a route whose only predicate is a media or header constraint, e.g. `route(accept(APPLICATION_JSON), h)` | such a route IS served, at every path matching that constraint; this grammar reads a verb and an address and neither is present | `combinator` | ✅ **shipped** (PR A1, spec §7 case 3, ruled 2026-09-13). Such a route now reads `path: /**` — the framework's any-path pattern — with its media (`produces`/`consumes`) carried alongside, since `combinator` never emits a resolved row with a NULL path any more; the addresses-nothing gate in `derive_call_endpoints.sql` never has one to drop. Pinned by `tests/e2e/test_rest_inbound_delivered.py::test_the_builder_catch_all_serves_every_path_and_is_resolved`. The gate itself is unchanged and still holds for a genuinely unreadable path (`path` NULL, `resolution: unresolved`) |
| Java | WebFlux functional — the non-coroutine Kotlin DSL, `router { GET("/x") { … } }` | `RouterFunctionDslKt.router` and `RouterFunctionDsl`'s seven verbs x five overloads (`javap`, spring-webflux 6.1.6) | `combinator` | ✅ **shipped** (PR A1, `W44-verb-overloads`, `GAP-1b`). `spring-webflux-router.yml` now declares `RouterFunctionDslKt.router` and `RouterFunctionDsl`'s seven verbs, each split into its five overloads by `arity`/`arg_types`, beside the coroutine DSL's own rules. Pinned by `tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks`. **Stated boundary:** the DSL's media-guarded verb-less form (`accept(MediaType) { … }` / `contentType(MediaType) { … }`) has no rule yet and derives one `unresolved` row rather than the route it declares — logged as `dsl-media-route` on the register, pinned by `test_a_kotlin_dsl_route_declared_under_a_media_guard_alone_is_one_unresolved_row` |
| Java | **Akka HTTP** `path("users" / IntNumber) { get { complete(…) } }` | nested closures, route is a *value* | `combinator` | **C-ish — the hardest inbound form surveyed** |
| Java | Ktor `routing { get("/path") { … } }` | Kotlin DSL | `combinator` | B |
| Java | Javalin — TWO flat forms, `app.get("/path", ctx -> …)` and `config.router.mount(router -> router.get("/path", ctx -> …))` | `JavalinDefaultRoutingApi<API>` declares the verbs as `default` methods, and exactly two types implement it — `Javalin` and `JavalinDefaultRouting` (`RouterConfig.mount`'s parameter) — same fourteen descriptors, no nesting, found on review | `single_call` | ✅ **shipped** (`javalin.yml`, javalin 6.4.0, w61, `javalin-routing`), both forms. **Boundary — the nested `ApiBuilder` form derives nothing, deliberately.** `config.router.apiBuilder(() -> path("/x", () -> get("/{id}", h)))` calls the static `ApiBuilder.get` inside a lambda inside `path(…)`'s lambda — reading it as a flat row would publish `/{id}` with no `path(…)` prefix, a wrong row rather than a missing one (pinned: `test_javalin_flat_registrations_derive_every_route` asserts `("inbound","GET","/{id}")` is never derived). Filed as `javalin-apibuilder`, Category B (the register §4) — needs the same receiver-chain walk `G-37`/`GAP-1b`/`G-30` wait on |
| Java | **Spring Data REST** — a repository interface becomes a CRUD API | six routes per exposed repository plus one per query method, derived from a framework rule; `@RepositoryRestResource` is OPTIONAL and the un-annotated case is the common one | `derived_resource` | ✅ **shipped** (2O Task 6) — gated on the module's build declaring Spring Data REST |
| Java | Data REST — WHICH repositories are exposed (`spring.data.rest.detection-strategy`) | `default` = public only, honouring `exported = false`; `all`, `annotated`, `visibility` each change the set | `derived_resource` | ✅ shipped — all four verified live (CP-2(0)); a value the catalog does not enumerate, or one that differs per environment, derives **nothing** |
| Java | Data REST — `path=`, `exported=false`, `/search/{query}`, `@RestResource` renames/removals | — | `derived_resource` | ✅ shipped |
| Java | Data REST — a `default` method on a repository interface | Spring Data treats it as a CUSTOM IMPLEMENTATION and excludes it from `RepositoryInformation.getQueryMethods()`, so no `/search/` route is served for it | `derived_resource` | **Boundary — OVER-reports one row per such method.** `ACC_ABSTRACT` is not among the modifiers the extractor records, so nothing in the facts tells a `default` method from an abstract one. Bounded to modules already past the dependency gate; recording the abstract bit closes it (fix round 3, I-3) |
| Java | Data REST — a query method INHERITED from a module-local `@NoRepositoryBean` base repository | Spring Data enumerates `getRepositoryInterface().getMethods()`, so an inherited query method is one of the repository's own (`javap -p -c`, spring-data-commons 3.2.5 and 4.1.1, CP-13 Q1) | `derived_resource` | ✅ **shipped** (`A-M13`) — the walk crosses a module-local superinterface that carries `@NoRepositoryBean`, and stops short of a `contracts` entry, whose methods are CRUD. A base in a JAR still has no facts here, which is 2O design §2a's own stated boundary |
| Java | Data REST — a method declared on a CUSTOM FRAGMENT interface (`interface OrderRepository extends CrudRepository<Order, Long>, OrderRepositoryCustom`) | `calculateQueryMethods` filters `getMethods()` through `isCustomMethod`, which is `RepositoryComposition.getMethod(m) != null` (CP-13 Q6), and the fragments are the repository's own direct superinterfaces minus those carrying `@NoRepositoryBean` (Q7) — identical bytecode at 3.2.5 and 4.1.1 | `derived_resource` | ✅ **shipped — derives NOTHING**, which is what the framework serves. **This corrects a fabrication the `A-M13` fix itself shipped**: crossing every module-local superinterface published `GET /orders/search/searchByFullText` for a method whose body lives in a hand-written `…Impl`, where before `A-M13` that input derived no search route at all. CP-13 Q1 recorded `isCustomMethod` by name and the fix read only the enumeration beside it (§5.4). **Falsified by** a live Data REST app serving a `/search/` route for a fragment method |
| Java | Data REST — a module-local base repository that extends a contract and carries NO `@NoRepositoryBean` | by Q7's rule it is a FRAGMENT interface, so its methods are custom methods and reach no `/search/` route; it is also a repository bean in its own right | `derived_resource` | **Boundary — UNDER-reports its inherited query routes on the DERIVED repository**, deliberately, because that is what the measured filter says. The base itself is still derived as its own repository wherever its entity type is readable. **Falsified by** a live app serving `/search/` routes on a repository whose base declares them without the annotation |
| Java | Data REST — a derived query method whose NAME collides with a CRUD method, e.g. `findAll(String tenantId)` | Spring Data's base-method lookup compares a method's name, its parameter COUNT and its parameter TYPES — a signature (JLS 8.4.2) — through `MethodLookups$RepositoryAwareMethodLookup` (CP-13 Q2), so such a method IS a query method and `/orders/search/findAll` is served | `derived_resource` | **Boundary — UNDER-reports, silently** (`A-M14`, still open). Our exclusion is `if name in crud_methods`, 25 bare identifiers, and the catalog's comment cites CP-2's observed 404 for an override of `findAll(Pageable)` — the SAME signature, generalised to the name alone. Closing it needs `crud_methods` to carry parameter types per contract per store AND the type-variable resolution the framework does through `getMostSpecificMethod`; the fact stream supports neither, so it is stated rather than half-built (§8.1 rule 4). **Falsified by** any repository declaring a derived query method with a CRUD name |
| Java | Data REST — a `static` helper on a repository interface | not a query method at all: it is bound to the type, never to the repository's instance contract | `derived_resource` | ✅ shipped — the `static` modifier is projected by the `method_visibility` query and such methods derive **nothing** (fix round 3, I-3) |
| Java | Data REST — a repository reached through a module-local `@NoRepositoryBean` base | within-module closure walk over `generic_interfaces` | `derived_resource` | ✅ shipped. **Boundary:** a chain through ANOTHER JAR is invisible (no facts here to walk), and a base that PERMUTES its type parameters would be read wrongly — no hop's type-parameter list is in the facts to check against |
| Java | Data REST — a module whose build declares the framework only TRANSITIVELY, on Maven | the POM parse records direct declarations only | `derived_resource` | **Boundary — reported SKIPPED with its reason**, never derived and never silent. Gradle's resolved classpath has no such gap |
| Java | Data REST — a NESTED entity type (`Order.Item`) | what the framework serves for one was not probed | `derived_resource` | **Boundary — derives nothing** rather than composing a path segment no probe covered |
| Java | Data REST — REACTIVE repository contracts (`ReactiveCrudRepository`…) | Data REST is built on Spring MVC; no reactive store was probed | — | **Boundary — not enumerated**, so nothing derives. Absent evidence, produce nothing |
| Java | Data REST — projections, excerpts, HAL affordances, `@CrossOrigin`, event handlers, QueryDSL web support | each changes the representation or adds routes | — | **C — stated boundaries** (2O design §2c) |
| Java | Data REST — the `HEAD`/`OPTIONS` verbs and the `/{basePath}/search` index route it also serves | observed live, deliberately not derived | — | **Boundary — §2b's table is what ships** |
| Java | `@ControllerAdvice` / `@RestControllerAdvice` + `@ExceptionHandler` | defines the error contract of every endpoint | `error_advice` | ✅ **shipped** (2O Task 8) — into `error_handlers`, its own table, never `endpoints`: an error handler is not a boundary anyone can address. Advice class, `declared_by`, scope attributes verbatim, exception type, status and response shape |
| Java | `@ExceptionHandler` declared inside a CONTROLLER | Spring scopes such a handler to that controller alone, where an advice class declaring no attributes applies to every controller | `error_advice` | ✅ shipped — the two are told apart by `declared_by`, because both carry a NULL `scope` and reading `scope` alone would widen one controller's contract across the application |
| Java | Error handling — a module-local stereotype composed from `@ControllerAdvice` (or from `@Controller`/`@RestController`) | the framework's own container test is meta-annotation aware, the same `AnnotatedElementUtils` rule the handler gate above uses | `error_advice` | ✅ shipped — through the composition pre-pass. A composed annotation whose TYPE lives in an unscanned jar is the pre-pass's own stated boundary, unchanged here |
| Java | Error handling — the exception type taken from the handler's PARAMETER, where `@ExceptionHandler` names none | the framework asks whether the parameter is assignable to `Throwable` | `error_advice` | ◐ **shipped, narrower than the framework's rule.** A parameter is read as an exception only where the chain is READABLE — it IS one of the catalog's declared roots, or its own scanned `superclass` chain reaches one. A handler whose exception comes from an unscanned jar derives **nothing** from that parameter. **UNDER-reports**, which is the only safe direction: nothing but a throwable reaches a throwable root, so this can never publish an ordinary argument as a handled exception. Closes when a dependency's hierarchy is scannable (`extract_libraries`, a USER ACTION documented in the usage docs) |
| Java | Error handling — a status set inside a `ResponseEntity` body (`ResponseEntity.status(NOT_FOUND).body(…)`) | body analysis, not a declaration | — | **Boundary — `status` is NULL, deliberately** (2O design §4b). Reading it is `fluent`-style body analysis that derives no endpoint. NULL is an answer here rather than a gap: inventing a status would present a value nothing declared as one the framework returns |
| Java | Error handling — `@ResponseStatus` on the EXCEPTION CLASS | the framework's default for every handler that declares none | `error_advice` | ◐ shipped **only where that class is in this module's own facts.** A third-party exception carries its annotation in a jar this workspace never scanned, so such a handler's `status` is NULL. Same escape as the row above it: `extract_libraries` |
| Java | Error handling — `ResponseEntityExceptionHandler` subclasses, `@ExceptionHandler` on an interface or superclass, `ErrorController`, `ProblemDetail` bodies | four more ways the error contract is declared, none probed | — | **Boundary — derives nothing.** Absent evidence, produce nothing (§8); each needs its own probe before it can be catalogued |
| Java | The `error_advice` engine's own fixture coverage | — | — | **Boundary — `spring-advice` derives ZERO rows on the fixture**, and has since 2O: the fixture declares no `@ExceptionHandler` or `@ControllerAdvice` anywhere, so these rows are proved by unit-level tests over synthetic facts and never end to end. W47 gave the shared ENGINE a live instance through `spring-stomp-advice` (§5.5); this catalog still has none |
| Java | Jakarta Servlet — `@WebServlet` on an `HttpServlet` subclass | address on the TYPE annotation, verb from the overridden `doXxx`; every `urlPatterns` entry is its own endpoint | `supertype_dispatch` | ✅ **shipped** (2O Task 7b) — every row of CP-9 confirmed live on Apache Tomcat 10.1.50, 11.0.24 AND 9.0.121 (`scripts/probes/cp9_servlet_shapes.md`), each column identified by the container the process itself reported. `value` and `urlPatterns` are read as the aliases they are. **Read with the boundary rows below: the annotation is one of THREE registration routes, a deployment descriptor can switch it off wholesale, and the verbs the container serves implicitly are deliberately not derived** |
| Java | Servlets — `web.xml` `<servlet-mapping>` and programmatic `ServletContext.addServlet` | the other two registration routes the Servlet specification defines, both registering the same servlets with no annotation anywhere | — | **Boundary — derives nothing, for either.** A WAR that maps everything in `web.xml` reports zero servlet endpoints, and neither route was probed. §8.1 rule 3: the shape is named here rather than left silent. Closes for `web.xml` when a deployment-descriptor reader exists, and for `addServlet` when a call-site catalog is written and probed |
| Java | Servlets — a module whose `WEB-INF/web.xml` declares `metadata-complete="true"` (or a `web-app` version below 3.0) | CP-9 rows 33-34: the same classes, the same container, one descriptor — `GET /metadata-complete/getonly` is a **404** on all three, beside a **200** for the servlet that same descriptor registers by hand, which is the positive control separating a suppressed scan from a context that never started. The specification switches the annotation deployment scan off wholesale, so every `@WebServlet` in the module is inert | `supertype_dispatch` | **Boundary — OVER-reports EVERY servlet row in such a module**, which is the anti-fabrication rule's own direction and the reason this row sits beside the under-report above rather than among them. Nothing in the pipeline reads `WEB-INF/web.xml`, so no fact can suppress a row and the catalogs apply unconditionally; the whole servlet surface of a metadata-complete WAR is published and served by nothing. Unlike Actuator's `exposure.include` this is not deployment configuration we cannot see — it is a file in the module's own tree we chose not to read. **Falsified by** a metadata-complete module appearing in an export; closed by a deployment-descriptor reader, which closes the `web.xml` registration route above at the same time |
| Java | Servlets — implicit `HEAD`, `OPTIONS` and `TRACE` | CP-9 rows 7-9 and 32, all three containers: where a class declares only `doGet`, `HEAD` and `OPTIONS` are **200** with `Allow: GET, HEAD, OPTIONS`, and `TRACE` is **200** too wherever the connector permits the method | `supertype_dispatch` | **Boundary — UNDER-reports up to three verbs per servlet.** The code serving them is `HttpServlet`'s own, in a container jar nothing here scans, so such a row could carry either no handler at all or `doGet`'s symbol — and the second is false, since `doGet` is *called by* the HEAD path rather than serving HEAD. The same ruling this phase made for Data REST's HEAD/OPTIONS above, deliberately: two catalogs answering one question two ways would be worse than either answer. An **explicit** `doHead`/`doOptions`/`doTrace` override IS derived. **Falsified by** an endpoint row becoming able to name a handler outside the module |
| Java | Servlets — an explicitly overridden `doTrace` | CP-9 row 31, all three containers: over a connector configured `allowTrace="true"`, `service()` dispatches TRACE to `doTrace` and the answer is **200**. Row 13 is the same request over the DEFAULT connector: **405**, refused before dispatch | `supertype_dispatch` | ✅ **shipped** — `doTrace` is in the verb map, with the connector as a **stated dependency**, on the same terms as Actuator's `exposure.include` above. `allowTrace` is connector configuration: any deployment sets it, it lives outside the module, and a repository cannot see it — so its default is not proof the address is unserved, and §8 forbids excluding on inference. A class that overrides `doTrace` has declared a handler, and a declared handler is a code fact we report. Fix round 1 reversed the original ruling, which had read a deployment default as a code fact. **Falsified by** a container in which `service()` stops dispatching TRACE to `doTrace` at all — not by one shipping a different connector default |
| Java | Servlets — the `javax.servlet` spelling | pre-Jakarta modules declare `javax.servlet.annotation.WebServlet` on a `javax.servlet.http.HttpServlet` subclass | `supertype_dispatch` | ✅ **shipped** (fix round 1) as `javax-servlet.yml`, a second catalog rather than an assumption: CP-9 gained a third column on Apache Tomcat 9.0.121 (Servlet 4.0) and measured all 33 rows identical to the two `jakarta` columns modulo the package name (rows 25-28 and 30). The two files are one document under a package rename, pinned as such by `test_the_two_spellings_declare_one_rule`. Every boundary in these rows applies to both. Legacy servlets are the population that uses this spelling, so a jakarta-only catalog would have under-served the estate the style exists for |
| Java | Servlets — a class reaching `HttpServlet` through an intermediate base | `class Orders extends AbstractBaseServlet`, itself extending `HttpServlet` | `supertype_dispatch` | ✅ **CLOSED** (F3 §4.2, W22). Was a boundary because `superclasses` carries the DIRECT edge only, and the style matched one hop rather than guessing what the intermediate declares — a boundary only while the hierarchy was unavailable. `type_hierarchy` is that hierarchy, and the match is now the closure. It is still not a guess: the walk crosses only ancestors this workspace SCANNED, so a chain running through a class in a jar stops there and derives nothing (the near-miss beside the positive). The TARGET is exempt from that test and must be — `HttpServlet` ships in the servlet API and is never scanned. **And the chain's members are read, not only the leaf's**: an intermediate that overrides `service` without delegating has replaced the verb table, so the class is discarded exactly as a leaf's own override would be (CP-9 rows 41-43 — the container serves PUT too, making a `GET`-only row a wrong answer rather than a partial one). That is also what lets a handler declared on the intermediate, with the address on the leaf, derive |
| Java | Servlets — an **abstract** `@WebServlet` class | the container's `InstanceManager` cannot instantiate it, so the URL answers 500 and the declared handler never runs | `supertype_dispatch` | **Boundary — OVER-reports one row per dispatch override on such a class.** `ACC_ABSTRACT` is not among the modifiers the extractor records, so nothing in the facts tells an abstract class from a concrete one — the same fact gap as Data REST's `default` repository methods above, and closed the same way, by recording the abstract bit. Not probed: nobody deliberately annotates an abstract servlet, which is why it is stated rather than gated |
| Java | Servlets — a class overriding `service()` and declaring **no** `doXxx` | CP-9 rows 14-15: GET **and** PUT both 200 from one `service` override, because it replaces the verb dispatch itself | `supertype_dispatch` | ✅ shipped — such a class derives **nothing**, rather than the verb set the map would have claimed. Publishing `GET` while withholding `PUT` would be a wrong answer, not a partial one |
| Java | Servlets — a class overriding `service()` that **delegates** through `super.service(req, resp)` and declares `doGet`/`doPost` | CP-9 rows 35-40, added 2026-09-05: GET 200, POST 200, **PUT 405**, on all three containers and BOTH `service` signatures. `HttpServlet`'s own dispatch still runs, and the 405 is what says so | `supertype_dispatch` | ✅ **shipped** (`A-M2`) — it derives the verbs it declares. Before this it derived **nothing**: the CP-9 verdict was measured against the no-`doXxx` configuration above and applied to every `service()` override, so the commonest real form — a cross-cutting wrapper — lost its whole surface, address, verbs and handlers, silently |
| Java | Servlets — a class overriding `service()` that does **not** delegate and declares `doXxx` anyway | CP-9 rows 41-43, added 2026-09-05: GET 200, POST 200 and **PUT 200**, on all three containers — where the delegating twin refuses PUT with 405 (row 37). The dispatch never runs and the `doXxx` methods are unreachable | `supertype_dispatch` | ✅ **shipped — derives NOTHING**, on the same terms as the no-`doXxx` class above. **This row used to say "Boundary — OVER-reports", and the over-report was real**: rows 35-40 measured the DELEGATING wrapper and the verdict was applied to every `service()` override declaring `doXxx`, publishing GET and POST while withholding a PUT the container serves. The distinguishing fact IS in the stream and is now read — CP-9 rows 44-46 measure a delegating override's `super` call arriving as `invoke_kind: special` on an `HttpServlet#service` target, both signatures and both spellings, against `ABSENT` for the non-delegating one — so both servlet catalogs now declare `call_site` in `requires`. **Falsified by** a container in which a non-delegating `service()` override refuses a verb it declares no `doXxx` for |
| Java | Servlets — a module scanned WITHOUT call sites | — | `supertype_dispatch` | **Boundary — the catalog is SKIPPED and the manifest says so**, rather than degrading silently. `call_site` is required for the delegation read above, and without it every delegating wrapper would read as a replacement. The JVM scanner produces `call_site` for every module it scans, so this reaches no shipped configuration today; it stops being true the day a scanner that does not is registered |
| Java | Servlets — a `GenericServlet` subclass | CP-9 rows 16-17: GET and PUT both 200, through one protocol-agnostic `service` | `supertype_dispatch` | ✅ shipped — derives **nothing**. It declares no HTTP verb semantics at all, and it is excluded structurally (its own `superclass` is not the one the catalog names) rather than by a special case |
| Java | Servlets — a same-named member with other parameter types | CP-9 rows 18 and 26: `doGet(String, HttpServletResponse)` overrides nothing and the container answers **405** | `supertype_dispatch` | ✅ shipped — the member selector is `{name, parameters}`, because a method is identified by name AND parameter types in order (§8.1's language rule). A name-only selector would have published that address |
| Java | Servlets — the pattern grammar (`/legacy/*`, `*.do`, `/`) and container matching precedence | patterns are published **verbatim**, never expanded, canonicalised or ranked against each other | `supertype_dispatch` | **Boundary — stated.** CP-9 measured only that a declared pattern is served at its own literal spelling; interpreting the grammar, or ranking two servlets that both match a URL, is modelling nobody probed |
| Java | Servlets — a servlet's request and response PAYLOADS | read off a stream at runtime; the handler's declared parameters are the container's own request/response objects | `supertype_dispatch` | **Boundary — `request_shape`/`response_shape` are NULL.** Expanding the declared parameters would publish the container's API as the module's contract |
| Java | Servlets — no conformance fixture ([D02](components/D02-catalog-schema.md) §4) | rows are pinned over synthetic facts against the **real loaded catalogs**, and the fact shapes those synthetic facts mirror were read off real compiled class files by CP-9's own extractor run (rows 20-30) | `supertype_dispatch` | **Limitation — stated.** No fixture repository exercises the derivation end to end in CI, so a change in the fact stream's shape is caught by re-running CP-9 rather than by the suite. D02 §4 records these two catalogs as its **second** fixture-less instance, with the reason (a servlet fixture puts a servlet API into CI's offline priming, a dependency change §7 puts out of scope) and the condition that closes it. Closes with an offline-primed servlet API and a fixture module |
| Java | Servlets — `@WebServlet`'s other attributes, and `@WebFilter`/`@WebListener`/`FilterRegistrationBean`/`ServletRegistrationBean` | `name`, `loadOnStartup`, `asyncSupported`, `initParams`; and the filter/listener registrations beside them | — | C — **stated boundaries.** None of the attributes changes the address or the verb set. Filters and listeners are cross-cutting plumbing rather than a service surface; `@WebFilter` has its own pinned no-derivation row below |
| Java | `@WebFilter` / `@WebListener` | `@WebFilter` carries `urlPatterns` and looks exactly like an address-bearing inbound mapping | `annotation` | **Boundary — deliberately derives nothing, and pinned.** A filter intercepts URLs other components serve; publishing its patterns would invent a service surface out of cross-cutting plumbing. `test_a_web_filter_derives_nothing_from_any_shipped_catalog` asserts it against EVERY shipped catalog at once |
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

**`A-C4` (principles sweep §3.2) closed the superclass half of that**, which shipped broken
from 2E Task 7 to the sweep. The inheritance walk read the `supertype` fact, and the extractor
emits that ONLY where the superclass carries type arguments — so `class OrderController extends
PrefixBase` had no superclass edge at all, and because `derive_endpoints.sql` composes an absent
prefix as the empty string, the child published `/{id}` where the framework serves
`/api/orders/{id}`: a confidently wrong address, not a missing row. The walk now reads
capability 9.13's erased `superclass` field, written for every non-`Object` superclass. **Output
changes for real modules**: a controller extending a non-generic base that carries a type-level
prefix, or that maps a method the child overrides, now derives what the framework serves. The
same edge retires the "a scanned ancestor always declares a method" assumption, so an abstract
base whose only content is a type-level mapping is reachable too.

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
superclass together still **derives no mapping for it** — but now because the two ancestors
give one method two different answers and nothing here reads the framework's own annotation
search order to choose (§8's ambiguous evidence), not because every bridge was discarded.
*Until OI-47 closed, the bridge rule was structural — same class, same name, same
parameters, different return — which excluded the real override alongside the bridge in the
covariant case and did not recognise a generic-parameter bridge at all, publishing the
compiler's forwarder as the handler. A method fact states `modifiers.synthetic`, so a bridge
is now read rather than inferred, and its resolved mapping is carried across to the method it
forwards to. Measured on the fixture, not asserted: `GET /api/orders/{id}` derives where it
did not before, its handler naming `OrdersApiController#find(sig_95a78dff)` — the override
returning the covariant `DetailedOrderResult` — and the module's endpoint count moves 122 to
123 with nothing else changing.* **Two boundaries remain**: two ancestors mapping one method
still derive nothing where their mappings DIFFER (identical ones now derive one row); and a
bridge forwarding to a method its class INHERITS rather than declares resolves nothing, since
the redirect reaches only the bridge's own class and a wrong-arity same-named sibling there is
not the target (measured: `class Sub extends Base implements IGet<String>` with an unrelated
`get(int)`). And the **supertype edge
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
declared media is READ, and was invisible for two phases** — `accept(...)`/`contentType(...)`'s
`MediaType` vararg constants compile through an `ANEWARRAY`, and every predicate-derived row's
`consumes`/`produces` read NULL even though a declaration demonstrably existed on the call site
(checkpoint F1). *This sentence read "an `ANEWARRAY` the extractor's argument reader has no case
for ... a later extractor candidate, not a gap in the engine". It was corrected once at extractor
capability 9.15, which teaches `MethodFlow.argumentJson` that construction and puts the constants
in the slot's own `elements`, and it is closed by 2O Task 13, which teaches
`combinator._media_constraints` to read them.* Live: `GET /fn/orders` and `GET /kt/rich` carry
`produces`, `POST /fn/orders` carries `consumes`, all `application/json`. **What remains is
narrower and stated where it lives** — `media_values` translates only the members a catalog
declares, and `spring-webflux-router.yml` declares `APPLICATION_JSON` alone, so a route declaring
any other constant still reads NULL rather than leaking that constant's own member name. And **Kotlin functional handlers resolve to NULL** — Kotlin 2.2 compiles every
DSL handler, bound method reference and lambda alike, to an `instance`-kind argument naming a
compiler-generated class rather than a method symbol, so the honest answer is no handler
rather than a fabricated guess through that class's own `invokeSuspend` (checkpoint (1b)).

**Both DECLARED routing surfaces now read all seven verbs** (`A-M9`, principles sweep §3.3).
*They are two of four.* `RouterFunctions$Builder` (seven verbs x four overloads) and
`RouterFunctionDslKt.router` with `RouterFunctionDsl` (seven x five) are undeclared, unprobed
and derive nothing — the table above carries a boundary row for each, and this sentence used to
read "both routing DSLs" as though the catalog's two were the framework's two. `A-M9` closed a
vocabulary gap inside one surface; it did not close the surface count, and the row above claiming
`RouterFunctions.route().GET(…)` shipped was wrong before `A-M9` and wrong after it.
`RequestPredicates` and `CoRouterFunctionDsl` each declare seven per-verb factories at
spring-webflux 6.1.6 **and** 7.0.2 (CP-12 Q11/Q12, read off the jars as "declared on the type
and spelled in upper case", which is the framework's own way of marking a verb factory apart
from `all`, `path`, `accept`, `headers`, `contentType`, `method` and `methods`).
`spring-webflux-router.yml` encoded GET/POST/HEAD in Java and GET/POST in Kotlin — **exactly**
the verbs `OrderRoutes.java` and `KotlinOrderRoutes.kt` declare. So
`RouterFunctions.route(RequestPredicates.PUT("/orders/{id}"), h::update)` derived a row with
neither verb nor address, and no boundary here named the gap. The catalog states the standard
it was built to, "exactly what 2E's checkpoint froze against a real scan… nothing here is
invented past that" — applied to a fixture rather than to the framework, which is §8.1 rule 1's
failure said in the catalog's own words.

**`method(HttpMethod)` / `methods(HttpMethod...)` stay a boundary** and derive no verb: this
grammar reads a verb as a literal declared beside the owner, and theirs is an enum constant
argument. **Falsified by** a module routing through the generic predicate forms; closes when
the `combinator` vocabulary can read a verb off an argument the way `fluent` now can.

### 5.2 REST outbound

**Phase 2B shipped the first three; Phase 2C shipped the next four.** Feign, Retrofit and
Spring `@HttpExchange` are read as outbound annotation clients; `RestTemplate` is read by the
`single_call` engine and `RestClient`, `WebClient` and OkHttp by the `fluent` engine
reconstructing their builder chains — all from the same linked `call_site` facts, calls made
inside lambdas included. OkHttp's generic `Request.Builder.method(String, RequestBody)` verb
call reads its verb off argument 0 like any other captured argument, so it derives beside the
named verb methods (`get`/`post`/`put`/`patch`/`delete`/`head`); a verb the scanner cannot read
as a string literal derives `method: NULL` at `unresolved` rather than the builder's own GET
default (`A-C2`). All eight verb-setting methods `Request.Builder` declares are covered, which
is the property that keeps that default honest — an uncovered one would fall through as an
unmatched step and leave GET standing (CP-11). What stays unread is
`delete(RequestBody)`'s **body**: a `fluent` step matches on name alone, so the one `delete`
step serves both overloads and the arity-1 form's payload is absent. Everything else in this
table remains unimplemented; the system tier still has nothing to match against them.

**`java.lang.Void` reaches no wire type, in every catalog** (`A-C3`, principles sweep §3.2).
`WireTypes` mapped only the PRIMITIVE `void` to the empty string; `java/lang/Void` is an object
sort and fell through to `default -> "object"`, so `ResponseEntity<Void>`, `Mono<Void>` and
`Call<Void>` — the idiomatic "no body" in nine catalogs' frameworks — published an endpoint
returning nothing as returning an OBJECT, and filed `java/lang/Void#` as an unexpanded type: a
gap report pointing at a type with nothing to expand. Thirty-three catalogs carried a
`known_types` REPAIR for it and nine did not, and because `derive_shapes` is global and
insert-if-absent, whichever catalog reached the type first described it for all of them. Fixed
at the source, where it is language knowledge — `java.lang.Void` is an uninstantiable
placeholder whose only value is null — and `tests/architecture/
test_known_types_mirror_the_projection.py` now refuses any catalog entry that contradicts the
projection, which is the invariant twenty-eight catalog comments already claimed.

**Both annotation clients are now gated on the construct the framework actually proxies**
(`A-C6` and `A-C1`, principles sweep §3.2). Retrofit and Spring's HTTP interface declared
neither a type gate nor `declared_on`, so an exchange annotation on a **concrete class**
derived an outbound row at `resolved`/`compiler` — a plausible-looking dependency the module
does not have, and the worst kind, because nothing downstream can tell a plausible fabricated
address from an observed one. Measured (CP-11): `Retrofit.create` throws
`IllegalArgumentException("API declarations must be interfaces.")` on anything else, and
`HttpServiceProxyFactory.createClient` hands its type to Spring AOP's `ProxyFactory`, whose
`AdvisedSupport.addInterface` asserts `Class.isInterface()`. Both catalogs declare
`declared_on: interface`.

**The stated cost of that key, on both files:** `declared_on: interface` on an OUTBOUND catalog
also engages the SEI fence, which subtracts every interface the module's own classes implement
— the fence exists because a generated server stub and a hand-written client interface are
annotated identically, and an interface the module IMPLEMENTS is one it answers. Neither
framework has that rule: `Retrofit.create` and `createClient` proxy the interface whether or not
a local class also implements it. So a module that both declares one of these clients and ships
a local implementation of it in MAIN sources loses that client's rows. Accepted as the smaller
error — the shape it costs is rarer than the concrete-class fabrication it fixes — and
**falsified by** any module shipping local fallbacks for its Retrofit or `@HttpExchange`
services. Closes when the fence can be declared separately from the construct gate.

**Narrowed for `@HttpExchange` by the direction flip (2O Task 10).** Where the implementing
class is a CONTROLLER, the fence no longer subtracts: the row becomes the inbound route
Spring really serves, handled by the implementing class's own method (§5.1's flip rows). The
fence still stands for an implementer the framework dispatches nothing to, and that case is
not an under-report at all — such a module neither calls the interface nor serves it. What
remains of the cost above, for this catalog, is the local-FALLBACK shape: a client interface
with a non-controller local implementation still loses its outbound rows. `retrofit.yml` is
unchanged in every respect.

**`RestClient` and `WebClient` now read all eight of their request-starting methods**
(`A-M3`, principles sweep §3.3). Both catalogs declared five — GET/POST/PUT/DELETE/PATCH,
which is exactly the verb vocabulary `fixtures/orders-service` happens to use — while both
clients declare eight at spring-web/spring-webflux 6.1.6 **and** 7.0.2 (CP-12 Q1/Q3,
`scripts/probes/cp12_sweep_round1b.md`). The cost of a missing root is total rather than
partial: a chain whose first call matches no root is never rooted, so nothing reaches a
terminal and `webClient.head().uri("/health").retrieve()` produced no row at all, with no
boundary stated anywhere. `head()` and `options()` now derive their own verb.
**`method(HttpMethod)` derives the call without the verb**: its argument is an enum constant
and `string_constants` reads string literals, so the capture is reached and unreadable and the
row ships with its address at `resolution: unresolved`, `method: NULL` — the same answer an
unreadable OkHttp verb argument gets. Withholding it instead would trade nothing for a silent
drop. **Falsified by** a module whose only outbound call is `.method(...)` and which expects a
verb; that closes when the fact stream carries an enum constant's own name, with no catalog
change.

**`WebClient`'s terminal set was wrong in both directions at once, and the file stated no
version** (`A-M4`). It declared `terminal: [retrieve, exchange]`. Measured (CP-12 Q2):
`exchangeToMono`/`exchangeToFlux` are the exchange-style terminals at 6.1.6 and the ONLY ones
at 7.0.2 — recommended since 5.3 — and were in the list at neither version, so a module using
them had its whole WebClient surface absent; while `exchange()` is declared and was **removed**
in Spring 7. Both are now declared, and the reasoning for keeping `exchange` is asymmetry: at
7.0.2 no call site can name a method the jar does not declare, so a dead entry costs no row
where a missing one costs every 6.1.6 chain. `spring-restclient.yml` said "no `exchange` on
this synchronous surface" about a type declaring two `exchange` overloads at both minors, plus
`exchangeForRequiredValue` at 7.0.2; all three are now terminals, and the reactive pair is
deliberately NOT copied across — that is the difference between the two twins.

The versions each list was read against are recorded in the catalogs themselves and pinned by
`tests/architecture/test_sweep_round1b_framework_surfaces.py`, which asserts against the
**7.0.2** column rather than the union so that a dead entry is never made compulsory.

**Retrofit reads seven of its eight request-method annotations, and the eighth is a stated
boundary** (`A-M5`). `retrofit2.http` declares eight annotations that name a request method —
identified from the jar rather than a list: `@Target(METHOD)`, tested for by
`RequestFactory$Builder`, and declaring a scalar `String value()` holding the path (CP-12 Q5,
retrofit 2.11.0). The catalog declared six, so `@OPTIONS("/x")` derived nothing, silently.
`@OPTIONS` now derives. **`@HTTP(method = "REPORT", path = "/x")` still derives nothing**, and
the reason is the engine rather than the framework: its path is in `path` while `path_from` is
one list for the whole catalog, and its verb is a plain `String` where `$method_from`'s read
extracts an enum constant's name — `regexp_extract(v, '#([A-Za-z0-9_]+)\.$')` — which on
`"REPORT"` returns the **empty string**. Declaring the row would ship a verb no evidence
supports, which is deriving on half a measured rule (§8.1 rule 4). A test asserts `@HTTP`
derives nothing, so adding it without the engine change goes red rather than quiet.
**Falsified by** any module using `@HTTP` for a non-standard verb; closes when `method_from`
can name a plain-string attribute and `path_from` can be declared per annotation.

| Language | Library | Shape | Tier |
|---|---|---|---|
| Java | Feign `@FeignClient`, Retrofit `@GET`, Spring `@HttpExchange` | `annotation` | ✅ shipped |
| Java | Micronaut `@Client` + `@Get`/`@Post`… on an interface | `annotation` | ✅ shipped (`micronaut-http-client.yml`, `declared_on: interface`, W58). `@Client` declares `value` and `path` and no media (W58 rows 45-46) |
| Java | MicroProfile `@RegisterRestClient` | `annotation` | A |
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
| Swift | `URLSession` + `URLRequest.httpMethod = "POST"` — **verb is a property assignment** — a shape seen nowhere else | `fluent_chain` | B |
| Any | Generated clients — `oapi-codegen`, `openapi-typescript`, `swift-openapi-generator` — read the OpenAPI document instead | artifact | A |

### 5.3 SOAP

**Shipped in Phase 2I** — the last protocol on the coverage roadmap's committed list, which
is a narrower list than [REQUIREMENTS.md](REQUIREMENTS.md)'s version-1 scope: that also
names gRPC, shipped for Java in Phase 2O Tasks 4-5 (§5.7). The boundary is not the HTTP route — one POST path fronts every
operation — so the identity is the **input element's QName** in W3C notation
(`{http://orders.example.com/ws}placeOrderRequest`), verbless, on
[D01](components/D01-graph-schema.md) §3's operation-is-the-endpoint rule. The row that
was `C (tier-2 artifact)` here — the WSDL itself — is the reason the rest works: the same
QName is stated by a handler's annotation, by a client's payload type and by the contract
file, so three independent statements meet on one string.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | JAX-WS `@WebService` + `@WebMethod` — **both `jakarta.jws` and `javax.jws`** | annotation on class + method; the class-level namespace scopes every operation | `annotation` | ✅ shipped — both spellings, including a **bare public method** (JAX-WS exposes it, so it derives) and `@WebMethod(exclude = true)` deriving nothing. `@WebParam` is not read |
| Java | JAX-WS — a public operation **inherited** from a superclass | `RuntimeModeler.processClass` walks the implementor class's `Class.getMethods()`, which returns inherited public methods (CP-13 Q3); `isWebMethodBySpec` (RI, offsets 124-147) and `hasWebServiceAnnotation` (CXF, offsets 0-17) then read `@WebService` off each method's OWN declaring class (w63) | `annotation` | ✅ shipped 2026-09-12 — an inherited public member is an operation only when its DECLARING class carries `@WebService` (w63, both runtimes, live: `charge` alone over `BillingWebService extends AbstractBilling`). The walk (`A-M15`) still continues past a plain ancestor — an annotated grandparent's methods derive — and the check is asked of the nearest declaration, after the one-per-signature dedup, so a plain class shadowing an annotated ancestor's method exposes nothing (JLS 8.4.8.1, confirmed with `getMethods()`), while the ancestor's unshadowed methods still derive through the plain class (pinned by `tests/application/test_endpoints.py::test_an_unannotated_base_shadowing_an_annotated_ancestors_method_exposes_nothing`). Before this `gate_ancestry` published the base's `refund` — a row NEITHER runtime serves. Pinned by `tests/e2e/test_soap_delivered.py::test_an_operation_inherited_from_an_unannotated_superclass_is_not_published` |
| Java | JAX-WS — an operation the `@WebService` class OVERRIDES from its base | `Class.getMethods()` returns ONE entry per signature, declared by the overriding class (CP-13 Q5, measured on the JDK the probe reported), and `processClass` walks exactly that enumeration (Q3) | `annotation` | ✅ **shipped** — the ancestry walk keeps the nearest declaration of each `(name, parameter types)`, so an overridden operation derives once and is attributed to the override. **This corrects a fabrication the `A-M15` fix itself shipped**: the widened walk published one row per DECLARATION, so an overridden operation went out twice, the second handled by a base class the RI never exposes, and an override carrying `@WebMethod(exclude = true)` withdrew only its own row while the base's identical declaration published the withdrawn operation at `resolved`/`compiler`. **Falsified by** two rows for one QName on a class that overrides a base method |
| Java | JAX-WS — a `public final` operation | `isWebMethodBySpec` excludes `static` **and `final`** (CP-13 Q4); our member rule excludes `static` and `final` | `annotation` | ✅ shipped 2026-09-12: excluded beside `static`, `derive_endpoints.sql`; pinned by `tests/e2e/test_soap_delivered.py::test_a_public_final_method_is_not_an_operation` |
| Java | JAX-WS — Apache CXF rather than the reference implementation | ✅ measured: CXF 4.0.5 applies the same static/final/`exclude`/declaring-class rule as jaxws-rt 4.0.2 (w63) | `annotation` | ✅ shipped — `javap -p -c` on `cxf-rt-frontend-jaxws`/`cxf-rt-wsdl` 4.0.5, cross-checked by booting BOTH `JaxWsServiceFactoryBean` (CXF) and the RI's own `RuntimeModeler` (via `DatabindingFactory`) over the identical fixture (`scripts/probes/w63_cxf_web_method_rule.md`). CXF's `JaxWsServiceConfiguration.isWebMethod` excludes `static`/`final` the same pair `RuntimeModeler.isWebMethodBySpec` invokes, honours `@WebMethod(exclude = true)` identically (both throw on an illegal `static`/`final` + explicit `@WebMethod` combination rather than silently withdrawing), and reads `@WebService` off a method's own declaring class the same way the RI's `isWebMethodBySpec` does (`hasWebServiceAnnotation` vs. `isWebMethodBySpec` offsets 117-147, both `ldc class jakarta/jws/WebService` then `getAnnotation`). The first pass of this probe read a CP-13 SUMMARY sentence instead of the RI's own bytecode and concluded CXF diverges; re-reading `isWebMethodBySpec` directly, and a live run of both runtimes over `BillingWebService extends AbstractBilling`, showed both exclude `refund` identically — see the row above (`A-M15`) for what that shared behaviour means for `gate_ancestry` |
| Java | Spring-WS `@Endpoint` + `@PayloadRoot(namespace, localPart)` | annotation | `annotation` | ✅ shipped — `{namespace}localPart`, and `@RequestPayload` binds the request shape strictly |
| Java | Spring-WS `@SoapAction("…")` | a second identity axis on the same handler class — the transport header, not the payload | `annotation` | ✅ shipped — the action URI verbatim, in the same catalog and with no engine branch |
| Java | Spring-WS `WebServiceTemplate.marshalSendAndReceive` | the operation is on the payload TYPE (`@XmlRootElement`), the address on the template (`setDefaultUri`) | `registration_call` | ✅ shipped — outbound, with the address resolved through configuration |
| Java | JAX-WS generated client stubs — a `wsimport` service endpoint interface | the annotated interface IS the client (the Feign shape) | `annotation` | ✅ shipped — outbound, from the module's own code or from an opted-in dependency jar |
| Python | `zeep`, `spyne` | client built from a WSDL URL at runtime | `runtime_dynamic` | B |
| Go | — | **no meaningful SOAP ecosystem** — hand-rolled XML if at all | — | — |
| TS | — | **no meaningful SOAP ecosystem** | — | — |
| Rust | — | **no meaningful SOAP ecosystem** | — | — |
| Swift | — | **no meaningful SOAP ecosystem** | — | — |
| — | WSDL / XSD documents | the actual contract | artifact | ✅ shipped — a reader and a stdlib-XML interpreter branch; an operation no annotation implements derives at `declared` with no handler |

**Five catalogs and one reader ship it.** `spring-ws` and `jakarta-jws` inbound,
`spring-ws-template` and `jakarta-jws-client` outbound, and the framework-neutral
`wsdl-schema` reading the contract; `format_fixed: {soap: xml}` on all five makes SOAP the
format ladder's second rung-1 protocol. Four framework-neutral vocabulary words carried the
annotation side — a QName composition, the JAX-WS spec's own reversed-package namespace
default, a class gate that exposes its public members, and a per-annotation withdrawal
filter — plus two on the call side (an identity read off an argument's TYPE, and a
client's configured default address) and one gate on where a declaration sits
([D02](components/D02-catalog-schema.md) §2). The phase also shipped the first
analysis-configuration file living in the analysed repository, `.sextant.yml`, because
SOAP's commonest outbound form — a generated stub — usually sits in a dependency jar
(§2a of [D04](components/D04-config-and-exclusion.md)).

**`declared_on` is what keeps a service from being published as its own client.**
`@WebService` marks both a service implementation and a generated stub, so the two catalogs
partition the annotation by what it sits on — class inbound, interface outbound — and the
outbound one further subtracts every interface the module's own classes implement. That
subtraction is the style's semantic rather than extra vocabulary: a stub is a declaration
nothing local answers.

The boundaries, each verified against the shipped code rather than assumed:

- **`rpc/encoded` is not implemented, and never will be here.** Only document/literal
  (wrapped included) has an element QName to be identified by; an `rpc`-style message part
  is typed rather than element-declared, and makes its file a gap.
- **An input message with more than one part — or none — is that WSDL's gap.**
  Document/literal *wrapped* is exactly one part and the wrapper IS the operation; a
  two-part message is a different wire shape, and a zero-part one names no request element
  at all, so both refuse rather than mark an arbitrary part.
- **`xsd:attribute` and `complexContent` make their file a gap.** The projection reads
  elements; attributes and derivation-by-extension are constructs it has no word for. Both
  are common in real schemas and both are cheap additions — recorded as a fast-follow
  candidate rather than a permanent boundary.
- **`substitutionGroup`, `xsd:any`/`anyAttribute`, `choice`, `redefine` and `override` are
  each their file's gap.** The first three describe a payload this vocabulary cannot state
  without guessing; the last two REPLACE a declaration in the file they name, so publishing
  that file would publish the definition the contract explicitly replaced — a wrong answer
  rather than a partial one.
- **A chameleon include gaps the INCLUDING file**, because the included file is read on its
  own terms and its components carry the bare names it wrote rather than the includer's
  namespace. The mirror case is not detected: the check fires only where the including
  schema has a target namespace, so a no-namespace schema including a namespaced one passes
  unremarked.
- **An element and a `complexType` sharing a QName is a representation limit, not an
  invalid schema.** XSD has two symbol spaces where a declared shape's symbol has one, so
  the file is reported rather than publishing two facts under one name — and this is a
  different rule from the duplicate-declaration gap, where the schema really is invalid.
- **Only conventional schema directories are read** — `src/main/resources/wsdl`, `.../xsd`
  and `.../META-INF/wsdl`. A configured or non-standard location is invisible, and a WSDL
  served from a **runtime URL** is not fetched at all (the registry-at-runtime class 2G
  already recorded for Confluent subjects).
- **The WSDL's output side is unread.** Operations are marked from input elements only, so
  every schema-first row's `response_shape` is NULL — permanently, until something reads
  the output message and links it.
- **`@SoapAction` rows are link-orphan-prone.** They are a different identity axis on the
  same protocol, so such a row links only where a client states the same action URI, which
  code rarely does. Honest and stated, not a defect in the derivation.
- **A JAX-WS operation has no request shape.** Its payload is the generated wrapper
  element, whose type exists in no source file the scanner reads, and the method's own
  parameters are that wrapper's children — so both JAX-WS catalogs deliberately declare no
  request-body rule rather than publishing a parameter type as the contract.
- **`sendAndReceive` is not claimed.** Its four callback overloads take no payload argument
  at all — the request message is written inside the callback — so no declared type carries
  the identity annotation, and a row for one would read its address through the url rule and
  publish a transport address in the column that holds the operation.
- **`marshalSendAndReceive`'s arity-2 collision is CLOSED, and what stood here was false.**
  The bullet used to say the callback forms collide at arities 2 and 3 and that "both reads
  then fail, so the cost is recall … and never a wrong row". It was a live fabrication:
  `marshalSendAndReceive("PAYLOAD", message -> {...})` binds
  `(Object, WebServiceMessageCallback)` — the lambda is what makes javac pick it
  unambiguously — and the row read position 0 as the address, publishing the SOAP request
  BODY whole as `peer`, the remote service the module calls, at `evidence: compiler`.
  Reproduced end-to-end. The arity-2 row now declares the erased descriptor of
  `(String, Object)` (javap -p -s, spring-ws-core 4.1.4), and arity 3 is the ONLY
  three-argument overload in that jar, so it never collided at all.
- **A `marshalSendAndReceive(payload, callback)` call now derives NOTHING**, where it used
  to derive a row carrying a fabricated peer. Once any row for a name+arity declares a
  `descriptor` that arity is claimed and an unmatched sibling falls through to no row — the
  same stated under-report `RabbitTemplate`/`JmsTemplate` already carry. **Falsified by** a
  module whose only SOAP calls take a `WebServiceMessageCallback`: its SOAP client surface
  is absent from the export entirely. Closes by declaring a row per overload — which cannot
  be done honestly here, because the callback form names its operation nowhere a declared
  type carries it.
- **JAXB's own defaults are not synthesised.** An `@XmlRootElement` omitting `name` or
  `namespace` derives an `unresolved` operation: neither default is written into the class
  file, and the namespace default is the schema's, which is not in the class file at all.
- **A hand-written `@WebService` interface whose methods carry no `@WebMethod` derives
  nothing** on the client side, and the belief that `wsimport` annotates every operation is
  recorded as **secondhand**: no JAX-WS RI, CXF, Axis or Metro artifact was available to
  probe, and this JDK has removed `wsimport`.
- **A stub interface with no local implementation always derives outbound**, which is the
  honest limit of the fence above: a hand-written service endpoint interface that this
  module does not implement is indistinguishable, in the facts, from a generated stub.
- **Two calls to one operation at two addresses keep one address.** `peer` is not part of
  wire identity, so the surviving address is whichever call was read first — call-order
  dependent, and the other address is not recorded.
- **SOAP 1.1 and 1.2 are not distinguished**, and WS-Security, WS-Addressing, MTOM and
  `Dispatch` dynamic clients are unread — the last of these is `runtime_dynamic` by
  construction.

**Opt-in library extraction has boundaries of its own**, all of them about reach rather
than about correctness:

- **The dependency tree is never auto-scanned.** A stub in a jar nobody named in
  `.sextant.yml` is invisible, and that is the design: scanning everything reachable would
  publish every framework's own annotated types as this module's endpoints.
- **A version managed by a parent POM or a BOM does not resolve from the two-part
  coordinate**, even though F1 resolves exactly that for the module's own recorded
  dependency set: `_library_roots` still reads `_dependency_versions`, the one-pom
  reader, because it answers a different question — which ARCHIVE to open, where a
  `<classifier>` or a non-jar `<type>` makes the file name wrong however well the
  version resolves. Routing it through the fuller resolution would widen library
  extraction on the change that widened the dependency gate, with neither measured;
  it is registered in `docs/open-issues.md` instead. The remedy is in the file:
  `groupId:artifactId:version` states the release outright.
- **A relocated local repository is invisible.** `settings.xml`'s `<localRepository>`,
  `-Dmaven.repo.local` and `M2_REPO` are all unread, so such a coordinate lands in the
  run's `libraries_not_resolved` list with its reason rather than resolving to a guess.
- **A jar inside a jar is not opened.** Only `.class` entries are read, so a Spring Boot
  fat jar's `BOOT-INF/lib/*.jar` contributes nothing.
- **A multi-release jar documents its versioned copies separately.** Every `.class` entry
  is scanned, `META-INF/versions/…` included, so one class compiled twice becomes two
  documents.

### 5.4 GraphQL

Better than expected: **A in almost every language.** Every ecosystem either declares
operations with annotations or ships an SDL file that *is* the contract. Remember that the
endpoint is the **field**, not `/graphql` — a schema with 200 fields is 200 boundaries behind
one HTTP route.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring GraphQL `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping`, `@BatchMapping` | code-first | `annotation` | ✅ shipped — all five, plus a class-level `@SchemaMapping(typeName)` scope the methods inherit (the method's own value winning) |
| Java | Netflix DGS `com.netflix.graphql.dgs.{DgsComponent, DgsData, DgsQuery, DgsMutation, DgsSubscription}` | code-first; the shorthands are equivalent to `@DgsData` | `annotation` | ✅ shipped, including `@DgsData(parentType, field)` |
| Java | MicroProfile GraphQL `org.eclipse.microprofile.graphql.{GraphQLApi, Query, Mutation}` (Quarkus) | code-first | `annotation` | ✅ **shipped, with the fallback name MEASURED and now correct** (`OI-5`, closed 2026-09-06 by the `annotation_driven` vocabulary pass). `@Query`/`@Mutation` under the `@GraphQLApi` gate; where the annotation and every sibling source name nothing, the operation is published under the name SmallRye derives from the method's own. CP-15 compiled `MethodHelper.getPropertyName` against smallrye-graphql-schema-builder 2.0.0 and 2.18.5 and RAN it, and the rule is direction-dependent per ANNOTATION — `@Query` strips `get`/`is`, `@Mutation` strips `set` — so the catalog declares `path_fallback: read_accessor_property` on one and `write_accessor_property` on the other. Every measured edge is asserted, `getURL -> uRL` included. **Bounded to SmallRye and to those two versions**: it is one implementation of a specification several vendors implement, and a second is a second `measured:` row rather than an assumption. Nothing was deployed — row 5 is the schema builder's own answer |
| Java | `@Name`, `@JsonbProperty` (jakarta and javax) or `@JsonProperty` on a MicroProfile GraphQL operation | code-first | `annotation` | ✅ **shipped** (`OI-35`, closed 2026-09-06 by the same pass). CP-15 rows 1-2: `getOperationName` consults five sources in order and takes the first with a value — the operation annotation, then `@Name`, then the two `JsonbProperty` spellings, then Jackson's `@JsonProperty` — and CP-15 **row 6** disassembles the loop that reads them, so the member is measured rather than inferred from the method's name: each is read from its own `value`, including Jackson's, which declares six members. `microprofile-graphql.yml` declares all four as `mapping.path_from_siblings`, IN THAT ORDER, and the engine consults them only where every `path_from` alias is absent — which is where CP-15 row 1 puts them. A source written EMPTY stops the search and yields no name, which `path_fallback` then answers, exactly as the framework does |
| Java | A framework that consults a SIBLING annotation's attribute BEFORE the matched annotation's own | the vocabulary orders `path_from` first, then `path_from_siblings`, then `path_fallback` | `annotation` | **Boundary — the grammar cannot state it, and the omission is deliberate.** CP-15 row 1 puts the matched annotation's own `value` at index 0 of the source array, so the shipped order IS the measured order for the one framework that needs it; a fully interleaved single list would rewrite the expression all 21 `annotation_driven` catalogs compose their address with, to buy a generality no measurement asks for. Nothing is under-reported today — no shipped catalog names such a framework. **Closes when** one does, at which point `path_from` takes `{annotation, arg}` entries beside its plain aliases and the two lists become one |
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
| Java | Jakarta WebSocket `jakarta.websocket.server.ServerEndpoint("/ws")` (was `javax.websocket.*` — **match both**) | annotation on the class; the value is a URI template | `annotation` | ✅ shipped for **both** spellings (W12) |
| Java | Spring STOMP `@MessageMapping("/topic/x")`, `@SubscribeMapping` | annotation | `annotation` | ✅ shipped — class-level prefix composition, `@SubscribeMapping`, and `@SendTo` reply rows |
| Java | **`StompEndpointRegistry.addEndpoint("/ws")`** — the URL a client opens | a `single_call` on the registry `WebSocketMessageBrokerConfigurer#registerStompEndpoints` is handed | `call_site` | ✅ **shipped** (W45, `G-42`). The destinations derived and **the transport endpoint they arrive on existed nowhere in the export**, so a reader could see `/orders/place` and had no way to learn a client reaches it by opening `/ws`. `spring-websocket.yml` names the RAW handler registry — a different interface, and mistaking the two for it is the gap itself. VARARGS: `addEndpoint("/a", "/b")` records ONE array argument and derives TWO rows, one per URL registered, compiled against spring-websocket 6.1.6 and read back rather than assumed. Live on the fixture: `/ws`, `/ws-alt`, `/ws-legacy` |
| Java | **`@MessageExceptionHandler`** — STOMP's error contract | the same `error_advice` engine the HTTP twin uses, one framework along | `annotation` | ✅ **shipped** (W47, `G-35`). §5.1 has shipped `error_handlers` for `@ControllerAdvice` since 2O and this direction was absent from §5 entirely, so a service whose messaging errors ARE handled looked like one whose are not. **The advice container is measured, not assumed from the twin**: `AbstractMethodMessageHandler` looks for a `MessagingAdviceBean` interface, which names no annotation — what supplies them is `spring-websocket`'s `WebSocketAnnotationMethodMessageHandler.initControllerAdviceCache()`, whose bytecode calls the SAME `ControllerAdviceBean.findAnnotatedBeans` the MVC side uses. So `@ControllerAdvice` really is the container here, for the framework's own reason. Live on the fixture, and it is the fixture's FIRST `error_handlers` row |
| Java | A STOMP error handler's **status** | — | — | **Boundary — `status` is NULL, and that is the answer rather than a missing read.** `@ResponseStatus` sets an HTTP response code; a STOMP handler answers over a broker where there is no such thing, so this catalog declares no status annotation at all and an `@ResponseStatus` written beside a `@MessageExceptionHandler` is ignored exactly as Spring ignores it. The engine's `status_annotation`/`status_from` pair became OPTIONAL for this case — before, a catalog had to invent a rule the framework does not apply or leave the surface uncatalogued |
| Java | `@ControllerAdvice` / `@ExceptionHandler`, the HTTP twin | — | `annotation` | ✅ shipped (2O) — see §5.1, where the rows are. **`spring-advice` still derives ZERO rows on the fixture**: what W47 gave an end-to-end instance is the shared `error_advice` ENGINE, through a different catalog. The HTTP catalog itself remains proved by unit-level tests over synthetic facts alone |
| Java | **The WebSocket CLIENT direction** — `WebSocketContainer.connectToServer(endpoint, URI)` | a `single_call`; the URL is one hop away behind `URI.create(...)` or `new URI(...)` | `call_site` | ✅ **shipped** (W46, `G-32`). §5.5 held THREE inbound Java rows and ZERO outbound, with no boundary saying the direction derived nothing — unlike REST, SOAP and Kafka, each of which states its client side. **`@ClientEndpoint` is not where the address is**: measured at jakarta.websocket-client-api 2.2.0 it declares `subprotocols`, `decoders`, `encoders` and `configurator` and no address at all, so a rule minting a row from it would publish an endpoint addressed at nothing. All four `connectToServer` overloads take their `URI` LAST; `channel_via` joins by owner and method NAME, so one entry covers the static factory and one the constructor. Live on the fixture: `ws://feeds.example.com/orders` and `/audit` |
| Java | **Spring's clients** — `WebSocketClient.execute`, `WebSocketStompClient.connectAsync`/`connect` | `single_call`, url a plain String except `execute`'s `URI` overload | `call_site` | ✅ **shipped** (W46). Two files, one owner each: they were ONE catalog with a two-entry `owner` list for a draft, and CP-10 refused it — the probe checks every declared descriptor against every listed owner, so the file was claiming `execute` on the STOMP client and `connectAsync` on the raw one, neither of which declares the other's method. The deprecated `ListenableFuture` `connect` pair is declared beside `connectAsync`, because a Boot 2 codebase calls it and a deprecated method is still a live boundary. Live on the fixture: `ws://feeds.example.com/stomp` |
| Java | A client URL's **peer** | — | `call_site` | **Boundary — `peer` is NULL and the whole URL is the `path`, on every client row.** A `ws://host/path` could be split, and the two-rung address ladder makes that a trap: a literal read would split while the `channel_via` rung returns a peerless tuple by construction, so one catalog would publish two address SHAPES for one boundary depending on which overload a caller reached. One shape everywhere, the rule `spring-websocket.yml` already states for a dispatch path and D02 §3 states for messaging peers. What it costs is the service identity on an outbound row |
| Java | `jakarta-websocket.yml`'s **coordinate list** | — | — | ✅ **corrected** (W46, `G-32`'s second half). It named `jakarta.websocket-api`, and that jar at 2.2.0 contains **only `jakarta/websocket/server/**`** — measured by opening it — so `@OnMessage`, `@OnOpen`, `@OnClose` and `@OnError` were not in any coordinate it named. **Nothing derived wrongly**: `annotation_driven` is not dependency-gated and this file declares no `detect.required`, so the coordinates are provenance and never a fence. Corrected because a provenance record omitting the jar that carries four of the six annotations is wrong as a record |
| Java | Joining a connect URL to the destinations served over it | — | — | **Boundary — the two are separate rows and nothing links them.** `/ws` and `/orders/place` both read `websocket inbound`, and a reader has to know that one is a handshake URL and the other a broker destination. Linking them needs a row shape this schema does not have; the honest state is two true rows rather than one invented relation |
| Java | Spring STOMP `SimpMessagingTemplate.convertAndSend` — the OUTBOUND half | a `single_call`, `KafkaTemplate.send`'s own shape one framework along | `call_site` | ✅ **shipped** (W43, `G-33`). Before it a service that both received and sent STOMP was published with half its messaging surface and nothing saying which half. **The descriptor could not be mirrored from its twin**: `convertAndSend` is declared on `MessageSendingOperations<D>`, `D` erases to `java.lang.Object`, and `SimpMessagingTemplate` declares no bridge — so a real call site written `convertAndSend("/topic/orders", payload)` compiles to `(Ljava/lang/Object;Ljava/lang/Object;)V`, and the `(Ljava/lang/String;Ljava/lang/Object;)V` a copy of `KafkaTemplate.send(String, V)` would have declared matches NOTHING. Compiled and read at spring-messaging 6.1.6 rather than reasoned about, and that String descriptor is the near-miss the suite pins. Six `convertAndSend` overloads, two `send`, four `convertAndSendToUser`; reads 3 of the 14 methods `SimpMessagingTemplate` declares and 3 of `SimpMessageSendingOperations`' 3, with the one unread addressable method named in the slice |
| Java | The same, to a DEFAULT destination — `convertAndSend(payload)` | no destination argument at all; the template's configuration carries it | `call_site` | ✅ shipped — `path` NULL at `unresolved`, `KafkaTemplate.sendDefault`'s own answer. The boundary is published and its address says outright it was not resolved, rather than the call vanishing |
| Java | `convertAndSendToUser(user, destination, payload)` | Spring's `UserDestinationMessageHandler` rewrites the destination before the broker sees it | `call_site` | **Boundary — the row ships, the address does not.** The literal at argument 1 is NOT what is published: publishing `/queue/orders` would name an address no subscriber holds, which is an OVER-report and worse than silence because it looks resolved. So these four overloads capture the payload and leave `path` NULL at `unresolved`. **Falsified by** a measurement of the handler's own composition, which is what would let them carry a destination |
| Any | An outbound `single_call` row whose payload is a method PARAMETER | the type is stated in the CALLER's own signature and nowhere else | `call_site` | ✅ **shipped** (`OI-77`, closed in W43's own commit). Found while checking W43's new rows against their siblings: `_reference_of` read a payload type from a class literal, a scalar or an `instance`, and a `parameter` named none of them — so a payload handed straight through (`send(OrderEvent event)` calling `template.send(topic, event)`) shipped with no contract at all. Measured before and after on the fixture: **3 of the fixture's 25 outbound `single_call` rows carried a payload, and 19 do.** *Re-measured after W46 and W47 added rows: the fixture now has 28 such rows, 19 with a payload, and 47 across `single_call` and `fluent` with 24. The 25/19 figures are the measurement AT THE TIME the rung landed, and are labelled as that rather than silently re-scaled — three earlier attempts at this sentence each named a set that had already moved or never existed.* * The 25/19 figures are the measurement AT THE TIME the rung landed, and are labelled as that rather than silently re-scaled — three earlier attempts at this sentence each named a set that had already moved or never existed.* *Published first as "3 of 27 … `single_call`" and then as "27 across the `single_call` AND `fluent` engines" — both wrong. 27 is 25 plus the two `fluent` catalogs that happened to be in the list, and across BOTH engines the fixture had 44 outbound rows with 24 payloads at that time.*|
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

**`A-C1` (principles sweep §3.2) put a type gate on both catalogs.** Neither declared one, so
`derive_endpoints.sql`'s controller join was a no-op and a lone method annotation minted a
declaration: on Jakarta WebSocket a `@ClientEndpoint` class — one that DIALS OUT — carrying the
`@OnMessage` callback was published as an INBOUND endpoint at the empty address, direction
inverted and address invented in one row; on STOMP a bare `@MessageMapping` on any class did the
same. Both gates are measured rather than chosen (CP-11): `@OnMessage` is `@Target(METHOD)`,
carries no address and ships in the CLIENT api jar, so it is the callback for both kinds of
endpoint and `@ServerEndpoint` is what makes a class served; and Spring STOMP's
`SimpAnnotationMethodMessageHandler.isHandler` is byte for byte the
`AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call Spring MVC runs. **Output
changes for real modules**: a WebSocket client and a STOMP handler on a non-`@Controller` class
stop deriving; everything the container actually serves is unaffected.

Boundaries, each verified against the shipped code:

- **A `@ServerEndpoint` class whose only lifecycle method is `@OnOpen`/`@OnClose` derives
  nothing.** It is a real served endpoint, and `mapping.annotations` lists `@OnMessage` alone —
  so a connection-oriented endpoint that never declares a message handler is absent from the
  export entirely. Silent before `A-C1`, stated here now. **Falsified by** any
  `@ServerEndpoint` class with no `@OnMessage`; closes by listing the lifecycle annotations
  beside it, which needs a probe of what the container serves for each.
- **RSocket and STOMP are told apart by the build** ✅ **CLOSED** (W16). This entry read
  "raised, not closed: separating them needs a fact that tells an RSocket registration from a
  STOMP one, and neither catalog reads one" — `@MessageMapping` is the routing annotation for
  BOTH, so every RSocket controller in a scanned module was published as `websocket`, a
  wrong-PROTOCOL fabrication rather than an empty-address one.

  Measured (`scripts/probes/w16_rsocket_versus_stomp.md`): **Spring does not distinguish them
  on the class at all.** STOMP's `SimpAnnotationMethodMessageHandler.isHandler` tests
  `@Controller`, and the reactive handler RSocket builds on defaults its bean predicate to a
  lambda testing `@Controller` — the same stereotype through the same
  `AnnotatedElementUtils.hasAnnotation` call. So the `@Controller` gate `A-C1` added could
  never have separated them, and no other fact about the class can either.

  The fact that does is which handler auto-configuration would REGISTER:
  `@ConditionalOnClass(io.rsocket.RSocket, …)` against
  `@ConditionalOnClass(WebSocketMessageBrokerConfigurer)`. Both catalogs gate on the
  coordinates that ship those types, and on the STARTERS beside them — F1 does not resolve
  transitives, so a module declaring `spring-boot-starter-rsocket` records the starter alone.
  `rsocket` joined D00's protocol set in the same change.

  **Three residuals, each stated rather than closed:**
  - **A module whose build records NO coordinates earns a `handler_protocol` question**, not a
    row. Parent-POM inheritance is the real case; F1 cannot settle it. A build that records
    coordinates and names neither library has said something and is declined outright — the
    two absences are different findings.
  - **Both libraries present derives TWO rows**, which §3.6 calls a correct answer rather than
    an ambiguity: both handlers scan the same beans with the same predicate. A module carrying
    RSocket over its WebSocket transport for ONE framework gets a deliberate over-report, and
    how common that is was not measured.
  - **`detect.required` is what makes the gate real for these two**, and only these two.
    `detect.coordinates` had been read by no `annotation_driven` catalog — only
    `derived_resource` and `config_join` are `DEPENDENCY_GATED` — so both gates were inert when
    first written and the RSocket catalog derived a SECOND row for the same controller. Gating
    the whole style would have been wrong: 20 of the 22 need no gate because their evidence
    names their framework (D02 ruling R9).
- **A raw WebSocket frame is untyped, and the row says so.** `jakarta-websocket.yml`
  deliberately declares no `request_body` block: `@OnMessage(String frame)`'s parameter is
  an opaque frame, not a declared contract, and the protocol offers no `@Payload`-shaped
  marker to tell one from the other. Shapes stay NULL and the format reads `unresolved`.
- **A negotiated subprotocol is not read** in any form, so nothing narrows that
  `unresolved`.
- **`javax.websocket` is matched** (W12, second pass). It was detection-only, on the stated
  grounds that `mapping.prefix_annotation` is single-valued and widening it is an engine
  change — W9 widened it, along with `matches.type_annotation`, and the boundary outlived
  its reason by a wave. Measured before adding the names: at javax.websocket-api 1.1 against
  jakarta.websocket-api 2.2.0, both `ServerEndpoint`s declare the same five attributes and
  target `TYPE`, and both `OnMessage`s declare `maxMessageSize` and target `METHOD`.
  It was also invisible to W11's own sweep, which read catalog TEXT — so the `javax` names
  written in the comment recording this very boundary counted as "named", and the sweep
  reported websocket as carrying both spellings while this bullet said the opposite. The
  sweep reads rule-bearing values now.
- **`@SendToUser` is not read as a reply destination.** The `reply` block's `annotation` used
  to be single-valued and no longer is (W9 widened it), so the stated reason is gone and the
  work is a catalog edit plus a measurement — OI-57. Until then the behaviour is unchanged: A `@SendToUser`-only handler falls into the branch an
  unannotated value-returning handler already takes — the honest `path` NULL, `unresolved`
  reply row — never a wrong destination. Proved over synthetic facts; no fixture surface.
- **A class-level array-valued prefix contributes element 0 only.** `@MessageMapping({"/a",
  "/b"})` on a class composes every method under `/a`; the second value is silently
  unavailable as a prefix. The same limitation `@KafkaListener` already carries, not a new
  one, and not exercised by the fixture.
- **`@MessageMapping` and `@SubscribeMapping` on ONE method is unexercised.** Nothing
  refuses it and nothing pins it; the fixture declares each separately.
- **The programmatic `addHandler` catalog has no live fixture surface.** It is proved over
  synthetic call facts against the real shipped file — the first catalog to ship under
  [D02](components/D02-catalog-schema.md) §4's stated fixture exception for a
  registration-call-only surface. No pom in this repository depends on `spring-websocket`
  at all, so the row's descriptor is measured against a jar pinned to the Spring Framework
  version the fixtures use, which is an assumption rather than a measurement.
- **`addHandler` resolves every registered path, and it took two corrections to get there.**
  This bullet used to say `arity: 2` was "unverified against real bytecode" and that a
  multi-path `.addHandler(h, "/a", "/b")` is "a three-argument call the row does not match at
  all". Both are false, measured (descriptor sweep R6) by compiling those exact calls against
  spring-websocket 6.1.6 and running the shipped extractor: `addHandler(WebSocketHandler,
  String...)` is varargs, so ONE path and TWO paths alike record exactly two arguments, with
  argument 1 an `array` carrying its own `elements`. The row therefore matches every call. It
  then derived `path` NULL for all of them, because `channel_of` resolved only a
  `kind: "string"` argument — an honest empty row, never a wrong address, and the boundary
  this bullet stated. **Closed by 2O Task 13**: `single_call` reads a `channel_arg` slot
  through `channels_of`, which reads the array's `elements`, so each registered path is its
  own row the same way each `urlPatterns` entry is. A path element javac could not fold to a
  constant contributes the one trailing unresolved row `all_strings` gives — the registration
  count stays right and the unread element says so. **Falsified by** a WebSocket registration
  whose exported path is not one the source names, or by a multi-path registration exporting
  fewer rows than it names paths. Still proved over synthetic call facts only: no pom in this
  repository depends on `spring-websocket`, so nothing here is measured against a live scan.
- **`addHandler`'s `handler` is the REGISTERING method, not the registered class.**
  `single_call` has no vocabulary for reading a symbol off an argument, so an inbound row's
  handler is the method whose body made the call (`registerWebSocketHandlers`); the
  `WebSocketHandler` implementation at argument 0 is not named anywhere on the row.

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

**The schema half shipped in Phase 2O Task 4; the JVM bytecode half shipped in Task 5.**
A `.proto` `service` block names its own methods with no help from any generated class,
exactly as a WSDL names its operations (§5.3) — so the descriptor interpreter reads it
directly: one `declared_shape` per RPC method, `role: operation`, carrying the request and
response type refs and the two streaming flags
(`ingress/interpret/protobuf._service_shapes`). `schema_operations`
derives gRPC's verbless identity, `(grpc, NULL, "<protoPackage>.<Service>/<Method>")`, from
that record (`schema_operations._grpc_operation_row`), and the `grpc-schema.yml` catalog's `format_fixed: {grpc: protobuf}`
makes gRPC the format ladder's third live rung-1 protocol (§4.1). This reads the descriptor
alone — embedded in generated code, or a `.proto` file on disk — whether or not any
generated-class bytecode ever reaches the workspace.

**Task 5 adds the JVM bytecode half — two new engine styles, both `supertype_derived`
`src/sextant/application/resolve/engines/supertype_derived.py` and `injected_client`
`src/sextant/application/resolve/engines/injected_client.py`**, both reading a call-site
argument the generated class's own identity-building calls carry (R11 — the checkpoint that
falsified the brief's original `constant: SERVICE_NAME` field-value read;
`scripts/probes/cp3_cp8_grpc_facts.md`), never a field value: `ServiceDescriptor.newBuilder`'s
own first argument for the service identity, `MethodDescriptor.generateFullMethodName`'s own
second argument for the wire method name (`shapes/identity_calls.py`). The engines are
framework-NEUTRAL — `supertype_derived` matches any class extending a generated
`<Service>ImplBase` regardless of which annotation, if any, marks it, and `injected_client`
matches net.devh's own `@GrpcClient`-annotated field. Neither reads or names a framework
inside the engine; catalog data does (`src/sextant/catalogs/grpc-java.yml`,
`src/sextant/catalogs/grpc-net-devh.yml`).

**Where both halves cover one identity the merged row keeps BOTH, and that is a fix rather
than an accident** (fix round 2). The bytecode row is inserted first, so `schema_operations`'s
insert at the same `(grpc, inbound, NULL, path)` is a no-op — its two STAMPS are what carry
the descriptor's half across: `src/sextant/storage/duckdb/stamp_declared_response.sql` and its
new sibling `src/sextant/storage/duckdb/stamp_declared_request.sql`, each touching only a row
whose own column is still NULL. So the merged row publishes the handler symbol (bytecode) AND
the request contract, the response contract and the streaming word (descriptor). Before the
fix the bytecode half made the row strictly THINNER than the descriptor alone would have
made it — both contracts and the `unary | server-streaming | client-streaming | bidi` Detail
disappeared exactly where the tool knew MORE about the endpoint.

**The `@GrpcService` corroboration ships too** (`src/sextant/catalogs/grpc-spring.yml`,
carrying both the Spring gRPC and the net.devh spellings). It rides `annotation_driven` on a
new `corroborates` block and a new `gaps` entry point
(`src/sextant/application/resolve/engines/annotation_driven.py`, wired through
`src/sextant/application/resolve/service_identity.py` beside the other two): it derives **no
endpoint rows at all** — the annotation carries no service name and cannot mint an identity —
and instead files a `service_identity` open question for any class it flags that no gRPC
endpoint names as a handler. That is the published-stubs case in §1b: the extends edge is the
module's own fact, the generated supertype's facts never arrive, `supertype_derived` derives
nothing, and without this catalog the outcome was silence. A flagged class the supertype
match DID derive files nothing.

**Two derivation corrections landed with it** (fix round 2). `supertype_derived`'s match now
requires the supertype's own outer class to MAKE one of the marker calls, not merely to be a
module-local class with an overridden public method — without that conjunct every
abstract-base/template-method pair in an ordinary repository minted a fabricated inbound gRPC
boundary plus a ledger question on no gRPC evidence at all. And the wire-name-to-override
lookup now refuses its two non-injective cases instead of guessing: two wire names collapsing
onto one override refuse BOTH (unresolved row plus a question), and an override no wire name
reaches is filed as a question rather than dropped.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | generated `FooGrpc.FooImplBase` implementing `io.grpc.BindableService`; stubs extend `Abstract{Async,Blocking,Future}Stub` | inheritance, not a call | `supertype_derived` | ✅ shipped (2O Task 5) — **B, as scoped**: the extends edge (capability 9.13) plus a call-site-argument read, framework-neutral, no annotation needed |
| Java | `net.devh.boot.grpc.client.inject.GrpcClient` (client stub injection) | field injection | `injected_client` | ✅ shipped (2O Task 5) — service-level only (`method` NULL); per-method outbound waits on 2Q's call graph |
| Java | `net.devh.boot.grpc.server.service.GrpcService` (server annotation) | class annotation, **no service name** | `annotation_driven` `corroborates` | ✅ shipped (2O Task 5, fix round 2) — derives NO row by design (`supertype_derived` above already derives it, and the annotation names no identity); it files a `service_identity` open question for a flagged class no gRPC endpoint names as a handler |
| Java | Quarkus `io.quarkus.grpc.{GrpcService, GrpcClient}` | — | `annotation` | A — server side rides `supertype_derived` already (framework-neutral); the `@GrpcService` corroboration catalog carries the Spring gRPC and net.devh spellings only, and `@GrpcClient` injection is net.devh's annotation only |
| Java | Spring gRPC `org.springframework.grpc.server.service.GrpcService` | **the annotation is optional** — Spring gRPC exposes *any* `BindableService` bean, so `supertype_derived` is the reliable match and the annotation only adds interceptors | `supertype_derived` + `corroborates` | ✅ shipped (2O Task 5) inbound via the framework-neutral supertype match, with the annotation's own corroboration shipped beside it (fix round 2) — a question where the supertype match saw nothing, never a row |
| Go | `pb.RegisterFooServer(s, impl)`, `pb.NewFooClient(conn)` | **the generated function names the service** | `registration_call` | A |
| Python | `_pb2_grpc.py`: `FooServicer`, `add_FooServicer_to_server`, `FooStub(channel)` | — | `registration_call` | A |
| Rust | `tonic` `FooServer::new(impl)`, `FooClient::connect(url)` | — | `registration_call` | A |
| TS | `@grpc/grpc-js` + `@grpc/proto-loader` `loadSync("foo.proto")` | **service built at runtime from a `.proto` path** | `runtime_dynamic` | **B — the path is a literal, so read the `.proto` as an artifact** |
| TS | `ts-proto`, `protobufjs` static mode | generated typed services | `generated_descriptor` | B |
| Swift | gRPC-Swift generated clients and providers; Connect-Swift | — | `registration_call` | A |
| — | `.proto` service descriptions, or the `FileDescriptorSet` embedded in generated code | **the actual contract, read directly** | artifact | ✅ shipped — both origins (2O), the same dual-origin read the message shapes already had (§4.1's Protobuf row); an RPC method's `symbol`/`schema_name` are the schema identity itself, since no generated class names it |

**Three stated boundaries, all Java, all explicit rather than silent (2O design §1b/§1c,
Task 5):**

- **Published-stubs jars.** A module implementing or injecting against `*-grpc-stubs`
  consumed as a dependency has no generated classes in its OWN output — the extends/field-type
  EDGE is still this module's own fact, but the target's `SERVICE_NAME`-building call sites
  never reach this workspace, so the identity cannot be read. `supertype_derived` derives
  nothing at all for such a class (not even the unresolved fallback, which is reserved for a
  LOCALLY SEEN supertype); `injected_client` derives the unresolved fallback row (`path` the
  stub type's own descriptor) plus a `service_identity` gap. The shipped `.sextant.yml` library
  opt-in (D02 §4a) is the escape, unexercised by this task.
- **UNANNOTATED Spring gRPC on published stubs.** Spring gRPC's own `@GrpcService` is
  optional — it exposes any `BindableService` bean — and this interacts with the boundary
  above. An ANNOTATED service on published stubs is now visible as a `service_identity`
  question (the corroboration catalog above); an UNANNOTATED one on published stubs still
  goes entirely unseen, because neither the identity nor any marker reaches this workspace.
  That is the one remaining silent cell, and the escape is the same `.sextant.yml` library
  opt-in.
- **Bare `newBlockingStub(channel)` without `@GrpcClient`.** No engine derives from a type
  reference alone; the call's own argument is a `Channel` object, not an address. Client
  wiring built by hand, with no field injection anywhere, is invisible to `injected_client`.

### 5.8 Kafka

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@KafkaListener` (`topics`, `topicPattern`), class-level `@KafkaListener` + `@KafkaHandler` included | — | `annotation` | ✅ shipped |
| Java | Micronaut `@KafkaListener`/`@KafkaClient` + `@Topic` (`value[]`, `patterns[]`) | the class marker decides the direction, so two catalogs gate on it — `micronaut-kafka.yml` inbound, `micronaut-kafka-client.yml` outbound on the interface | `annotation` | ✅ shipped (micronaut-kafka 5.6.0, W58). Pinned by `tests/e2e/test_messaging_micronaut_delivered.py` |
| Java | `ReplyingKafkaTemplate.sendAndReceive(ProducerRecord)`, and a `@KafkaListener` method returning a value annotated `@SendTo` | the reply derives as its own outbound row | `registration_call` + `annotation` | ✅ shipped |
| Java | `KafkaTemplate.send(topic, …)`, `.sendDefault(…)` | **all ten overloads** since `A-M6` — the partition- and timestamp-carrying `send` forms take the topic at argument 0 and the payload last, and every `sendDefault` form derives `path: NULL` at `unresolved` because its destination is config-borne. **`G-44`'s Kafka receive half**: `receive(String topic, int partition, long offset, Duration)` is a synchronous read of one record and derives one INBOUND row on the topic at argument 0 (spring-kafka 3.1.4, `scripts/probes/w59_template_receive_halves.md`). Its sibling `receive(Collection<TopicPartitionOffset>, Duration)` takes addresses built elsewhere — each `TopicPartitionOffset` assembled from a topic, partition and offset the caller already has — and stays outside; there is no `channel_via` form for a constructor, so a row here would need one that does not exist | `registration_call` | ✅ shipped |
| Java | `KafkaConsumer.subscribe(Collection<String>` \| `Pattern)`, **with or without a `ConsumerRebalanceListener`** | `List.of` (≤10 elements) resolves per topic; `Collections.singletonList`/`Pattern.compile` resolve their one argument; `Arrays.asList` is genuine varargs and resolves per topic too since **2O Task 13**, which taught `all_strings` to read the array slot's own `elements` (capability 9.15's `{kind: array, elements: […]}`) — it degraded to one unresolved row before that. An array the extractor cannot read end to end never reaches the `array` kind and still degrades that way | `registration_call` | ✅ shipped |
| Java | **`KafkaProducer.send(ProducerRecord[, Callback])`** | **topic is a constructor argument of `ProducerRecord`**, not of `send`; the callback overload is a trailing argument and reads the same position (`A-M6`) | `fluent_chain` | ✅ shipped |
| Java | `KafkaTemplate.send(Message)` with topic in a header | topic read from a `setHeader(KafkaHeaders.TOPIC, …)` value-guarded step | `fluent_chain` | ✅ shipped |
| Java | **Kafka Streams** — `StreamsBuilder.stream/table/globalTable`, `KStream.to`, `Topology.addSource`/`addSink` (`G-31`) | split into three catalogs by owner — `kafka-streams.yml` (`StreamsBuilder`), `kafka-streams-sink.yml` (`KStream`), `kafka-streams-topology.yml` (`Topology`); the three are unrelated types with disjoint method sets, not one library reachable under more than one name (§3.1), the same reason `spring-websocket-client.yml`/`spring-stomp-client.yml` split | `call_site` | **supported** (3.6.2, w60): DSL sources (`stream`/`table`/`globalTable`, `Collection`/`Pattern` overloads included) and sinks (`KStream.to`), Processor API sink (`Topology.addSink`); `Topology.addSource`'s `String...` topics MEASURED to derive one inbound row per topic (w60 Step 4 — `single_call`'s `channel_arg` already reads an array argument element-wise, the `spring-websocket.yml` `addHandler` precedent) and read across its four `AutoOffsetReset`/`TimestampExtractor` prefixed forms; `to(TopicNameExtractor)` and the deprecated `through` are stated outside rather than read. Pinned by `tests/e2e/test_kafka_delivered.py` |
| Java | **Spring Cloud Stream** functional `Consumer<T>`/`Supplier<T>` beans | topic in `spring.cloud.stream.bindings.<bean>-in-0.destination`; gated on the build declaring `org.springframework.cloud:spring-cloud-stream`, and **any** method returning one of the three function interfaces is a candidate — see the boundary note below | `config_join` | ✅ shipped |
| Java | **SmallRye** `@Incoming("orders")` / `@Outgoing` | channel in code, topic in `application.properties` | `config_join` | **B** — rides 2F's `config_join` once catalogued |
| Java | **Apache Pekko Connectors Kafka (Alpakka)** `Consumer.plainSource`/`committableSource`/`atMostOnceSource`/`plainPartitionedSource`/`committablePartitionedSource(settings, Subscriptions.topics("t"))` (`alpakka-pekko`) | subscription is `channel_arg: 1`, built by a `Subscriptions` factory read through `channel_via` — `topics(String...)` MEASURED (w62, this task's Step 4) to arrive as one `array`-kind argument the existing `all_strings` reader already unpacks (the same mechanism `kafka-consumer.yml`'s `Arrays.asList` row carries); `topicPattern(String)` reads its one argument directly. `Producer.plainSink`/`committableSink`/`flexiFlow` name no topic — outbound is a stated boundary | `call_site` | ✅ shipped (pekko-connectors-kafka 1.1.0, w62). Pinned by `tests/e2e/test_kafka_delivered.py` |
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
exercised by the fixture, slated for tightening alongside the addresses-nothing gate described below. Where a
class-level `@KafkaListener` does derive, every `@KafkaHandler` method on it derives its own row
against the shared topic identity — several payload contracts riding one topic is the deliberate
outcome, not a deduplication the engine owes anyone.

**Spring Cloud Stream's candidate scan is the return type and nothing else, and the dependency
is what fences it** (`A-C5`, principles sweep §3.2). `config_join`'s `_candidates` reads EVERY
declared method in the module and keeps the ones whose return type is `Function`, `Consumer` or
`Supplier` — there is **no `@Bean` or `@Configuration` conjunct**. On a module with no Spring
Cloud Stream at all that published four Kafka boundaries from three ordinary utility methods;
the catalog is now dependency-gated (`resolve/dependencies.py`), so such a module is SKIPPED
with its reason instead.

*This paragraph used to end "and where `spring.cloud.function.definition` is absent the
framework's own default is to bind every candidate". That is false, measured against the
framework's own selection code (W13, `scripts/probes/w13_stream_binding.md`): the definition is
defaulted to a bean only when exactly one is eligible, and `FunctionBindingRegistrar` binds only
a definition with text.*

**The residual, stated rather than closed, and it now cuts BOTH ways.** The over-count is
unchanged: `_candidates` sees every function-shaped method, bean or not. What changed is what
that over-count costs. Where the selection key names nobody, `unselected_binds: sole` declines
to choose — so a module with one real bean beside one function-shaped helper derives **no row**
and files one `unselected_binding` question per candidate, where before W13 it derived the real
row plus a fabrication.

Neither is right, and the question is the honest middle: a count taken over declared methods is
not the count the framework takes over registered beans, so a suppression here is not evidence
the framework suppressed. Closing it still needs to know which registration forms the framework
binds — `@Bean`, `@Component`, a programmatic `FunctionRegistry` entry — and that is unmeasured
(rank 3 in the sweep's probe backlog). §8.1 forbids inventing the conjunct.

**Falsified by** a Spring Cloud Stream module with exactly one real function bean, no
`spring.cloud.function.definition`, and any function-shaped utility method beside it: its real
binding is absent from the export, with two open questions in its place.

`KafkaTemplate.sendDefault` and `JmsTemplate.convertAndSend(Object)` with no destination put
the destination somewhere the engine cannot read a literal from, so each derives a real row
with `path: NULL, resolution: unresolved` — the same honesty rule an unreadable OkHttp verb
argument follows in §5.2, never a fabricated name.

**`SqsTemplate`'s builder-lambda `send(Consumer<SqsSendOptions<T>>)` was in that list from
2026-08-30 until W57 and is not any more** (`OI-74`). The queue name was never unreadable: it is a
string literal inside the lambda's own synthetic method, which the fact stream records under
the symbol this call's own argument names. The catalog declares `lambda_arg` and `lambda_steps`
now — *which builder method inside the body carries the destination, and at which position* —
and the fixture's `sqsTemplate.send(to -> to.queue("shipments-lambda").payload(event))` derives
`shipments-lambda` at `resolved`, with the payload's contract too. **Reading the named step is
what keeps it reading rather than guessing**: `SqsSendOptions` declares seven methods and four
take a string, so a reader taking the first literal in the body would publish a trace header as
a queue. That conjunct is measured by `single_call.lambda-step-is-the-declared-method`. This
row read "the engine cannot read a literal from" it, which was a statement about the engine
dressed as one about the framework.

A listener annotation that puts its destination in an attribute the catalog does not list —
`@KafkaListener(topicPartitions = …)` is the one still live here — derives **nothing at all**:
the composed destination is empty, and the addresses-nothing gate (`derive_endpoints.sql`)
withholds a row that names no endpoint. This paragraph previously said such a listener "derives
a resolved row with an **empty** path today rather than an unresolved one; a known wart", which
was measurably false — sweep 1 measured zero rows on the shipped `spring-sqs` catalog and the
sweep's §7.7 settled it. **The correction matters in the direction that costs a reader**: it
told them the row was present-but-empty when the listener is absent from the export entirely,
which is the harder of the two to notice. Closes for the `topicPartitions` case by a `path_from`
that can fan out a nested annotation.

**A method carrying TWO listener annotations now derives both destinations, in all three
frameworks** (`OI-36`, measured 2026-09-06 by CP-16, closed the same day by the
`annotation_driven` vocabulary pass). `@KafkaListener`, `@JmsListener` and `@RabbitListener`
are each `@Repeatable`, into `KafkaListeners`, `JmsListeners` and `RabbitListeners`
respectively, and each framework's post-processor reads that container — Kafka calls
`KafkaListeners.value()`, JMS calls
`AnnotatedElementUtils.getMergedRepeatableAnnotations(element, JmsListener, JmsListeners)`,
spring-rabbit 3.1.4 streams `RabbitListener` out of a `MergedAnnotations` view. javac writes
the CONTAINER and not the annotation on such a method (JLS 9.7.5), so the class file carried
no `@KafkaListener` at all, the mapping join matched nothing, and **both** destinations
vanished from the export while the single-listener neighbour derived normally. All three
catalogs now declare `mapping.annotations[].container` — the key `spring-scheduling.yml`
already had one style over — and `requires` extractor capability 9.16, so a scanner that
cannot read a nested annotation skips the catalog visibly rather than reporting half a
module's listener surface.

**What used to be a boundary here is now a MEASURED absence, and the difference matters.**
`@KafkaHandler` and `@RabbitHandler` declare no container, and CP-16 could not say whether
that was right: row 2 asked `@Repeatable` of the listener annotations only, and row 3 read the
handler annotations' declaration without asking. **CP-17 asked** — rows 2i–2l read
`@Target({METHOD, ANNOTATION_TYPE})` with no `@Repeatable` on either, at spring-kafka 3.1.4 and
4.1.1 and spring-rabbit 3.1.4 and 4.1.1, and rows 3i–3l found no `KafkaHandlers` or
`RabbitHandlers` in any of the four jars. `@SqsHandler` is the same answer at
spring-cloud-aws-sqs 4.1.1 (rows 2n, 3n). So all three handler entries' silence about a
container is a claim about the framework rather than an absence of evidence, and **there is no
repeated-handler shape left to miss** — the row that stood here asked for one `javap`
question, and this is it.

**A `@RabbitListener` declared on a superclass or interface method registers a listener on the
implementing bean, and we see it only where it is written** (`OI-37`). CP-16 row 4e:
spring-rabbit 3.1.4 searches `MergedAnnotations.from(element, SearchStrategy.TYPE_HIERARCHY)`,
and the strategy arrives as a constant the probe could read rather than a contract it had to
assume. Bounded to spring-rabbit 3.1.4: Kafka's `findMergedAnnotation` and JMS's
`getMergedRepeatableAnnotations` carry no such constant, so what they search is unmeasured, and
spring-rabbit 4.1.1 moved its search into `spring-amqp`, an artifact CP-16 does not open.
**Falsified by** an inherited listener declaration appearing in an export.

**`@SqsListener(queueNames = …)` was the other half of this and is now shipped** (`A-M8`,
principles sweep §3.3). `value()` and `queueNames()` are one attribute under two spellings —
`queueNames` carries `@AliasFor(value = "value")`, measured at spring-cloud-aws-sqs 3.1.1
(CP-12 Q10) — and `spring-sqs.yml` read `value` alone, so the spelling AWS's own documentation
uses composed an empty destination and the listener vanished from the export. Both are now in
`path_from`, `value` first, which mirrors `@AliasFor`: Spring refuses an annotation that sets
both to different values, so first-alias-wins can never pick between two live answers.

The scanner does not capture a parameter's own generic type arguments — only a return type's —
so a `ConsumerRecord<K, V>` payload parameter reads as honestly absent rather than resolving to
`V`, the same reason a `List<T>` parameter's element type never reaches `request_shape.item`.

**The three Kafka catalogs now declare every overload that names a destination** (`A-M6`,
principles sweep §3.3). Each previously declared the arity its fixture happened to call:
`KafkaProducer.send(record, callback)`, `KafkaConsumer.subscribe(topics, rebalanceListener)`
and the four partition- or timestamp-carrying `KafkaTemplate` forms derived **nothing at all**,
because `_matching_method` filters candidates on `row.get("arity") in (None, len(arguments))`
**before** it consults a descriptor — so a call at an undeclared arity never reaches any row.
The first two are the idiomatic asynchronous producer call and the idiomatic consumer-group
call, and this section listed all three catalogs "✅ shipped" with no arity qualification.
Measured at kafka-clients 3.6.2 and spring-kafka 3.1.4 (CP-12 Q6/Q7/Q8) and pinned to bytecode
by CP-10; every new row's argument positions are its sibling's, because in each case the
addition is a trailing argument.

**A serializer stamp reaches every `kafka/outbound` row in the module, whatever derived it**
(principles sweep §7.4, settled). `stamp_media.sql` matches on `(protocol, direction)` and
nothing else. That is the mechanism rather than a defect for the templates —
`spring-kafka-media.yml` derives no rows of its own and exists only to fill a column on rows
other engines minted — and it is an **over-report** for a raw `KafkaProducer` row, which builds
its own `Properties` and reads no `spring.kafka.*` key. `produces`/`consumes` are carried data,
never identity: no address, verb or protocol moves, and dedup and merge never compare them.
Bounded by the dependency gate, so a module using the raw producer ALONE is never stamped.
Narrowing it means declaring which catalogs a rule applies to, which is a D02 §2d schema
change. **Falsified by** a module that declares spring-kafka and also publishes through a raw
`KafkaProducer` configured differently. **Not** an over-report across modules: `endpoints`
carries no module column, every module gets its own workspace, and one module's configuration
has no path to another's rows.

**`KafkaConsumer.assign(Collection<TopicPartition>)` is a stated boundary and still derives
nothing.** Its argument is a collection of `TopicPartition` **objects**, and the topic name is
a constructor argument inside each one — two hops from the call site, where every `channel_via`
form is one hop to a call returning the destination itself. `channel_arg: 0` would read a
partition list as a destination, and a row with no channel at all would assert a subscription
with no address. Neither is taken as a side effect of `A-M6`. **Falsified by** a module whose
consumers use manual partition assignment; closes when `record_wrappers`' constructor-argument
read can be declared over a collection of records rather than one.

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
| Java | Micronaut `@JMSListener` + `@Queue`/`@Topic`, `@JMSProducer` + the same on an interface | one catalog per direction, as for Kafka above | `annotation` | ✅ shipped (micronaut-jms-core 4.2.0, W58). Pinned by `tests/e2e/test_messaging_micronaut_delivered.py` |
| Java | `JmsTemplate.send` / `convertAndSend` | the declared row is `convertAndSend(String destinationName, Object message)`, pinned to that overload by its `descriptor` | `registration_call` | ✅ shipped — **read with the two collision rows below**, which it shares with `RabbitTemplate` |
| Java | `RabbitTemplate.receive` / `receiveAndConvert` / `receiveAndReply` | every overload naming the queue at argument 0 (nine, spring-rabbit 3.1.4, `scripts/probes/w59_template_receive_halves.md`); the destination-less overloads read the configured default queue and derive nothing. `receiveAndReply` is one INBOUND row: the reply goes to the message's own `replyTo` | `registration_call` | ✅ **shipped** (`G-44`, AMQP half) |
| Java | `JmsTemplate.receive` / `receiveSelected` / `receiveAndConvert` / `receiveSelectedAndConvert` | the four overloads naming the destination at argument 0 (spring-jms 6.1.6, `scripts/probes/w59_template_receive_halves.md`) | `registration_call` | ✅ **shipped** (`G-44`, JMS half). The `jakarta.jms.Destination`-typed overloads take an object built elsewhere and stay outside; the arity-1 `receiveSelected(String)`/`receiveSelectedAndConvert(String)` forms take a SELECTOR, not a destination — their descriptor is identical to `receive(String)`/`receiveAndConvert(String)`'s, but the catalog separates overloads by NAME first, so it simply declares no arity-1 row for those two names and each call derives nothing |
| Java | Direct `jakarta.jms.{Session, MessageProducer, MessageConsumer}` | `createProducer` and **all eleven consumer factories** — plain, selector-carrying, shared, durable and shared-durable — linked to `createQueue`/`createTopic` via `channel_via`; `send()` deliberately unread, `createBrowser` deliberately undeclared | `registration_call` | ✅ shipped |
| Java | Spring AMQP `@RabbitListener(queues = …)`, plus class-level `@RabbitListener` + `@RabbitHandler` | `queues` is a `String[]` (javap, spring-rabbit 3.1.4); the class-level form doubles as the destination prefix, `spring-kafka.yml`'s shape | `annotation` | ✅ **shipped** (2O Task 7) |
| Java | `@RabbitListener(bindings = @QueueBinding(…))` / `queuesToDeclare = @Queue(…)` | the destination lives inside a NESTED annotation | `annotation` | **Boundary — derives nothing.** Nested-annotation arguments are readable since extractor capability 9.16, and **`spring-rabbit.yml` does not read them** — precisely: no catalog reads a nested annotation's own ATTRIBUTE as an address, because no `path_from` alias can name one, and declaring `path_from: [bindings]` would hand `annotation_driven` the whole `@QueueBinding` value and publish its JSON text as a queue name. (9.16 is not unread in general: `spring-scheduling.yml` reads a repeatable container's array of annotations through `engines/scheduled_work.py::_folded`. This row is about the ATTRIBUTE half.) The addresses-nothing gate drops the would-be row rather than publishing an empty destination. **Closes when** a `path_from` alias can name an attribute inside a nested annotation — an engine change, not a catalog one |
| Java | A listener destination written as SpEL `#{…}` or a property `${…}` | the value is a bean property or a config key, resolved at container start | `annotation` | ✅ **shipped as `unresolved`** (2O Task 7) — the expression is published VERBATIM beside `resolution: unresolved`, never canonicalized and never resolved. Nothing here resolves it: the config ladder is a call-site mechanism `annotation_driven` never invokes |
| Java | `@RabbitHandler` outside a class-level `@RabbitListener`, and a class-level `@RabbitListener` naming more than one queue | the first names no destination at all; the second is read element-0-only | `annotation` | **Boundary.** The first derives NOTHING (the addresses-nothing gate, pinned by a §10 near-miss); the second takes the first queue, `spring-kafka.yml`'s own class-level limitation. **Falsified by** a listener whose `queues` array has more than one element — every queue after the first is missing from the export, and the row that does derive claims one destination for a consumer that serves N. Closes when `path_from` can fan one annotation out to a row per array element |
| Java | A class carrying BOTH a class-level and a method-level `@RabbitListener` | Spring registers the two independently; this catalog composes the class queue in front of the method one | `annotation` | **Boundary — OVER-reports one composed destination.** Inherited from `spring-kafka.yml`'s prefix shape, which has the same seam. Closes when a prefix annotation can be scoped to the member annotations it actually prefixes |
| Java | `@RabbitListener` + `@SendTo` (the declared reply destination) | `spring-kafka.yml` reads its own via D02 §2's `reply` block | `annotation` | **Boundary — no `reply` block is declared**, so a Rabbit listener's declared reply derives no outbound row. One `reply` block closes it |
| Java | `@RabbitListeners` — the `@Repeatable` container | a repeated annotation reaches the bytecode as its container, never as N annotations | `annotation` | ✅ **shipped** (the 2026-09-06 vocabulary pass, `OI-36`). `spring-rabbit.yml` names the container, and the engine unfolds each folded use into an ordinary annotation row before anything else reads one. Measured: CP-16 rows 2e/2f read `@Repeatable(RabbitListeners.class)` off the annotation's own class file at 3.1.4 and 4.1.1, and row 4e shows the post-processor streaming `RabbitListener` out of a `MergedAnnotations` view. Needs extractor capability 9.16, which the catalog now `requires` |
| Java | `@PulsarListeners` — the container a SECOND `@PulsarListener` is written into | **not javac's**: `@PulsarListener` is not `@Repeatable`, and `@PulsarListeners` is an ordinary annotation of container shape an author writes by hand | `annotation` | ✅ **shipped** (Stage 4 batch 2, `OI-38`). `spring-pulsar.yml` names the container and the engine unfolds each member into an ordinary annotation row before anything else reads one. Measured: CP-17 rows 2a/2b read NO `@Repeatable` at spring-pulsar 1.2.11 or 2.0.7, rows 3a/3b read `PulsarListeners.value(): PulsarListener[]` out of the same jars, and rows 6a/6b show `findListenerAnnotations` registering the **union** of a direct use and every member — which is what a real row plus the synthesized ones already are. Needs extractor capability 9.16, which the catalog now `requires` |
| Java | A container annotation whose array is declared under a name other than `value` | JLS 9.6.3 binds `value` for a `@Repeatable` container; a HAND-WRITTEN one is under no such obligation | `annotation` | **Boundary — derives nothing**, and it is a boundary rather than a defect because nothing has been measured that needs it: `value` is spelled in the engine as the language's word (D02 §2), and both containers read so far declare it. **Falsified by** a framework shipping a hand-written container under another attribute name — every member of it would be missing from the export. Closes by making the array attribute a catalog word, which is a key nobody has evidence for yet |
| Java | Spring for Apache Pulsar `@PulsarListener(topics = …/topicPattern = …)` | `topics` is a `String[]` and `topicPattern` a scalar (CP-17 rows 1a/1b, spring-pulsar 1.2.11 and 2.0.7) — the `@KafkaListener` shape | `annotation` | ✅ **shipped** (2O Task 7; the version scope is CP-17's since Stage 4 batch 2). A TYPE-level use derives nothing: the framework ships no class-level handler annotation to dispatch to — `org.springframework.pulsar.annotation.PulsarHandler` is ABSENT FROM THE JAR at both versions (rows 4a/4b), which is now measured rather than asserted |
| Java | Spring for Apache Pulsar `@PulsarReader(topics = …)` | a SECOND inbound annotation of the same framework, with its own post-processor (`PulsarReaderAnnotationBeanPostProcessor`), endpoint type (`MethodPulsarReaderEndpoint`) and registrar | `annotation` | ✅ **shipped** (Stage 4 batch 2, `OI-39`). Was a **silent drop of the whole shape**: this catalog named the annotation nowhere, so every reader in a scanned module was absent from the export. Measured: CP-17 rows 1c/1d read `topics(): java.lang.String[]`, rows 5c/5d show the post-processor feeding it to `setTopics([Ljava/lang/String;)`, and rows 6c/6d show a method-level discovery reading the annotation alone — no container (rows 3c/3d found none) and no class-level form |
| Java | `@PulsarReader`'s `startMessageId` and `schemaType` | the position a reader starts from, and the schema family it decodes with | `annotation` | **Boundary — neither is read.** `startMessageId` is a start POSITION rather than an address and names no destination; `schemaType` is the same enum-valued attribute already stated for `@PulsarListener` two rows above, and no `format_from` rule is declared for it. Both are stated rather than silent because CP-17 rows 1c/1d enumerate them |
| Java | `RabbitTemplate.convertAndSend(exchange, routingKey, message)` | the wire identity is the exchange+routing-key PAIR, rendered `exchange/routingKey`; the two-argument overload targets the default exchange and is the routing key alone | `registration_call` | ✅ **shipped** (2O Task 7), via `single_call`'s new `address_arg_2` |
| Java | `RabbitTemplate` / `JmsTemplate` — every form no row declares: `send(…)` (four arities), `convertSendAndReceive(…)`, every `convertAndSend` carrying a `CorrelationData`, Rabbit's `MessagePostProcessor` forms, and JMS's `(Object, MessagePostProcessor)` and `(Destination, Object, MessagePostProcessor)` | pre-converted `Message`, request/reply, and the correlation / post-processor forms | `registration_call` | **Boundary — derives NOTHING, and this is silence rather than an `unresolved` row.** Once any row for a name+arity declares a `descriptor` that arity is claimed, so an undeclared sibling falls through to no row at all — deliberately, because falling through to a descriptor-less row is the fabrication the key exists to stop. **Narrowed by the descriptor sweep (R5)**: `JmsTemplate.convertAndSend(Destination, Object)` was in this row by accident — it can never fabricate a destination, since its argument 0 is an instance rather than a string constant — and has its own row again; `convertAndSend(String, Object, MessagePostProcessor)` was never declared at any arity and now is, which is recall this row never admitted losing. **Falsified by** a module that publishes only through the forms still listed: its AMQP/JMS surface is absent from the export entirely. Closes by declaring a row per overload, one descriptor each |
| Java | `RabbitTemplate` / `JmsTemplate` — overloads that COLLIDE on arity | **arity 2 is exposed as well as arity 3**, on both classes (javap -s, spring-rabbit 3.1.4 / spring-jms 6.1.6): Rabbit arity 2 is `(String, Object)` and `(Object, MessagePostProcessor)`, arity 3 is four overloads; JMS arity 2 is `(String, Object)`, `(Destination, Object)` and `(Object, MessagePostProcessor)` | `registration_call` | ✅ **CLOSED** (2O Task 7 fix round). Was a live fabrication in both shipped catalogs — a `MessagePostProcessor` overload published its message PAYLOAD as the wire destination at `resolved`/`compiler`. Each address-carrying row now declares its own erased JVM `descriptor`, whose PARAMETER portion is matched against the call's `target.descriptor` (`storage/duckdb/schema.sql:243`) — verbatim until F2 §4.1, which dropped the return type because it is not part of method identity (§3a-i). **The residual boundary is the under-report in the row above** |
| Java | EVERY `single_call` client catalog — a call made through an INTERFACE or supertype rather than the concrete class | a call site records the **compile-time qualifying type** javac emitted, so `SqsOperations.send(...)`, `AmqpTemplate.convertAndSend(...)`, `JmsOperations`, `KafkaOperations`, `RestOperations`, `WebServiceOperations`, `PubSubOperations`, `org.apache.kafka.clients.consumer.Consumer` and `jakarta.jms.QueueSession`/`TopicSession` each record THEIR own owner | `registration_call` | ✅ **CLOSED for seven of them** (W9/W10). `matches.owner` accepts a LIST of names, and `JmsOperations`, `AmqpTemplate`, `SqsOperations`, `RestOperations`, `KafkaOperations` and Kafka's own `Consumer` and `Producer` are declared beside their concrete classes — each checked against the library's own bytecode by `scripts/probes/cp10_catalog_descriptors.md`, which asks its question of every alternate separately because an interface declaring a SUBSET of the class's methods would match some call sites and miss the rest. All 53 alternate rows come back `declared`. The highest-risk case was `spring-sqs-template.yml`, whose `SqsTemplate.newSyncTemplate(...)` **returns `SqsOperations`** (javap -p -s, spring-cloud-aws-sqs 3.1.1), so the idiomatic construction missed entirely. **The residual boundary is `WebServiceOperations`, `PubSubOperations` and `jakarta.jms.QueueSession`/`TopicSession`**, which are named here and are not declared as alternates: nothing measured them, and an unmeasured alternate is the one thing the list form must not carry. **Falsified by** a module holding one of those three by its interface: that part of its surface is still absent from the export. Closes by measuring each and adding it, which is now a catalog edit rather than engine work |
| Go | `rabbitmq/amqp091-go` (was `streadway/amqp`) `ch.Publish(exchange, key, …)` | — | `registration_call` | A |
| TS | `amqplib` `ch.publish(exchange, key, …)`, `ch.consume(queue, cb)` | — | `registration_call` | A |
| Python | `pika`, `kombu` `channel.basic_publish(exchange, routing_key, …)` | — | `registration_call` | A |
| Swift | — | **no JMS or AMQP client in common iOS use** | — | — |
| Rust | `lapin` `channel.basic_publish(…)` | — | `registration_call` | A |

**Package change:** `javax.jms` (Spring ≤5 / Boot ≤2) → `jakarta.jms` (Spring 6 / Boot 3+).
**Both are matched, and the sentence that stood here — "Both must be matched" in the
indicative — was false for as long as it stood** (W11/W12,
`scripts/probes/w11_javax_jakarta.md`). It read as a description of the catalogs and was a
requirement nobody had checked, which is why nobody looked: a mechanical sweep of every
`jakarta.*` type any catalog names found three families in one spelling only — `jms`,
JAXB's `XmlRootElement`, and `websocket`. The third was found only after the sweep was
corrected to read rule-bearing values rather than file text: it had been reading the `javax`
names written in a COMMENT recording the boundary, and reporting the boundary as closed.

The sweep also found that the gap fails in **three** different ways, not the two that were
expected, and that the third is the worst:

| what named one spelling | what a Boot 2 codebase got | closed by |
|---|---|---|
| `jakarta-jms.yml`'s `matches.owner` (a POSITIVE match) | nothing at all — the whole route invisible | `javax-jms.yml`, its own descriptors measured against `javax.jms-api 2.0.1` |
| `spring-ws-template.yml`'s `@XmlRootElement` read (an IDENTITY rule) | a SOAP endpoint at the right peer with `path` NULL at `unresolved` — reads as "the operation was unreadable" when it was never looked for | both spellings on all three rules (§3.1) |
| `spring-jms.yml`'s `request_body.excludes` (a NEGATIVE list) | the opaque `javax.jms.Message` envelope published AS the payload contract — a wrong contract, not silence and not a hole | both spellings in the list |

The third is the one no one would have predicted: every rule that names a type in order to
REFUSE it inverts the failure, because a missing spelling stops the refusal rather than
stopping the match. A sweep that only reads `matches` will keep missing that class.

**Queue versus topic is invisible here by construction.** Kind is configured on the container
factory, not written beside the destination expression the code actually carries, so identity is
the destination expression alone — a `@JmsListener(destination = …)` row derives with no way to
say whether it names a queue or a topic, which is a fact about where JMS puts that decision, not
a gap in the catalog. Direct `jakarta.jms.{Session, MessageProducer, MessageConsumer}` ships as
a `single_call` catalog: `createProducer`/`createConsumer` each link to their own
`createQueue`/`createTopic` call through `channel_via`, and `send()` is deliberately never read
— a raw `jakarta.jms.Message` is an opaque envelope no rule can pull a payload out of, so the
registration call itself is the evidence that a route exists, not the call that later uses it.

**`Session` opens eleven kinds of consumer and the catalog modelled one** (`A-M7`, principles
sweep §3.3). Measured at jakarta.jms-api 3.1.0 (CP-12 Q9), reading the set off the jar as
"declared on `Session` and returning a `MessageConsumer`, a `TopicSubscriber` or a
`QueueBrowser`" — the framework's own statement that the call opens a receiver. Thirteen
factories, of which eleven are consumers. Every selector-carrying consumer and every durable or
shared subscription derived **nothing**: a real inbound JMS endpoint, on a destination
`channel_via` could already resolve, silently absent with no row here saying so. The catalog's
own comment mentioned the two extra `createConsumer` overloads and declined them; the durable
and shared families were not mentioned at all. All eleven take their destination at argument 0
— the selector, the subscription name and the `noLocal` flag are trailing — so the ten new rows
read it exactly as the original does.

**`createBrowser(Queue[, String])` is a stated boundary and derives nothing.** A `QueueBrowser`
enumerates a queue without consuming from it, so publishing it as an inbound endpoint would say
the module receives messages the broker never delivers to it. That reading is the
specification's rather than a measurement of a running broker, and a test pins the exclusion so
it cannot be added by momentum. **Falsified by** a model that wants every READ of a destination
on the graph regardless of delivery semantics — which is a modelling decision, not a catalog
one.

### 5.10 AWS SQS

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring Cloud AWS 3.x/4.x `io.awspring.cloud.sqs.annotation.SqsListener`, `SqsTemplate` | `value()` and `queueNames()` are ONE attribute — `queueNames` carries `@AliasFor(value = "value")` (`javap -v`, 3.1.1, CP-12 Q10), and CP-17 rows 5e/5f confirm at BOTH 3.1.1 and 4.1.1 that the post-processor reads `value()` alone because the merge happens inside `findMergedAnnotation` | `annotation` | ✅ shipped — **both spellings** since `A-M8` |
| Java | Class-level `io.awspring.cloud.sqs.annotation.SqsListener` + `@SqsHandler` | a shape that did **not exist** at 3.1.1 and does at 4.1.1: `@Target` widened from `{METHOD}` to `{METHOD, TYPE}`, `@SqsHandler` was added, and the post-processor grew a branch building a `MultiMethodSqsEndpoint` from the class-level `value()` | `annotation` | ✅ **shipped** (Stage 4 batch 2, `OI-40`). Was a **silent drop of the whole shape** — `spring-sqs.yml` said in as many words that SQS has no class-level listener, which was true when it was written. Measured: CP-17 rows 2e/2f, 4e/4f, 5f and the branch itself at row 6f, against row 6e's same method at 3.1.1. The class-level listener doubles as the destination prefix, `spring-kafka.yml`'s shape. **No version constraint**, and the plan's rule is why: code built against 3.1.1 cannot carry an annotation that artifact does not declare |
| Java | `@SqsHandler` outside a class-level `@SqsListener`, and a class-level `@SqsListener` naming more than one queue | the first names no destination at all; the second is read element-0-only | `annotation` | **Boundary.** The first derives NOTHING (the addresses-nothing gate, pinned by a §10 near-miss); the second takes the first queue, `spring-kafka.yml`'s own class-level limitation, and the framework resolves ALL of them (`queueNames(resolveEndpointNames(sqsListenerAnnotation.value()))`, CP-17 row 6f). **Falsified by** a class-level listener whose `value` array has more than one element — every queue after the first is missing from the export. Closes when `path_from` can fan one annotation out to a row per array element |
| Java | A class carrying BOTH a class-level and a method-level `@SqsListener` | Spring Cloud AWS registers the two independently — CP-17 row 6f runs the method-level branch and the class-level branch in sequence, neither gated on the other — while this catalog composes the class queue in front of the method one | `annotation` | **Boundary — OVER-reports one composed destination.** Inherited from `spring-kafka.yml`'s prefix shape, which has the same seam and the same row. Closes when a prefix annotation can be scoped to the member annotations it actually prefixes |
| Java | Spring Cloud AWS 2.x `io.awspring.cloud.messaging.listener.annotation.SqsListener` | **different package**; declares exactly `value()` as `String[]` and `deletionPolicy()` and nothing else, `@Target(METHOD)`, no `@Repeatable` and no container-shaped sibling in the jar (CP-17 rows 1h, 2h, 3h, 5h, at 2.4.4) | `annotation` | ✅ **shipped** (2O Task 7, `spring-sqs-legacy.yml`); **measured and found correct** by Stage 4 batch 2, which is what makes this row re-runnable rather than repeated |
| Java | Spring Cloud AWS 1.x/2.2 `org.springframework.cloud.aws.messaging.listener.annotation.SqsListener` | **a third generation**, under the old `org.springframework.cloud` group; identical shape, and `QueueMessageHandler` reads `value()` and `deletionPolicy()` and no third attribute in either generation (CP-17 rows 1g, 2g, 3g, 5g, at 2.2.6.RELEASE) | `annotation` | ✅ **shipped** (2O Task 7, same file); **measured and found correct** by Stage 4 batch 2 |
| Java | Either legacy `@SqsListener` on a container-managed argument other than `Acknowledgment` | `@Header`/`@Headers` parameters, the visibility handle, the raw `Message` | `annotation` | **Boundary — the payload reads as absent** rather than wrong: `sole_unannotated` needs exactly one bare parameter, and two leave the request shape NULL. The two `Acknowledgment` types are excluded by name; anything else the framework injects is not |
| Java | `SqsTemplate.receive` / `receiveMany` / `receiveAsync` / `receiveManyAsync` | every overload takes `Consumer<SqsReceiveOptions>` at argument 0 (spring-cloud-aws-sqs 3.1.1, `scripts/probes/w59_template_receive_halves.md`); the queue is named INSIDE that lambda, `opts -> opts.queue("orders")`, and no argument carries a string | `registration_call` | **Boundary — receive is unread, and the reason is measured:** unlike `RabbitTemplate`'s and `JmsTemplate`'s receive halves (§5.9, `G-44`), which name the destination at argument 0 and already derive, every SQS overload buries the queue inside the options lambda instead. Reading a call inside a lambda body that the argument names is the receiver-chain form, Category B of the register (`docs/java-kotlin-delivery-list.md` §4) — the same overload-discrimination work `G-37`/`G-30` wait on, not a `single_call` row. Three of `G-44`'s four halves derive (Rabbit, JMS, Kafka); SQS's needs that lambda-body read first |
| Java | AWS SDK v2 `SqsClient.sendMessage(SendMessageRequest)`, `…builder().queueUrl(u)` | `SendMessageRequest.builder()` root, `queueUrl`/`messageBody` steps, `build` reaches `sendMessage` | `fluent_chain` | ✅ shipped |
| Go | `aws-sdk-go-v2` `client.SendMessage(ctx, &sqs.SendMessageInput{QueueUrl: …})` | struct literal | `registration_call` | A |
| TS | `@aws-sdk/client-sqs` v3 `client.send(new SendMessageCommand({QueueUrl}))` | **command classes are real, statically visible types** | `registration_call` | A |
| **Python** | **`boto3`** `boto3.client("sqs").send_message(QueueUrl=…)` | **clients synthesised at runtime from JSON service models — `send_message` is defined in no Python file** | `runtime_dynamic` | **C — ceiling is a `name_match` on the service string; `resolution: narrowed` at best** |
| Rust | `aws-sdk-rust` `client.send_message().queue_url(u).send()` | — | `fluent_chain` | B |
| Swift | `Soto`, the community AWS SDK for Swift — actively maintained, Linux/macOS/iOS | `sqs.sendMessage(.init(queueUrl: …))` | `registration_call` | B |
| Java | Micronaut | raw AWS SDK `SqsClient.sendMessage`, the same `aws-sqs-sdk.yml` chain as row above — Micronaut ships no first-party SQS annotation | `fluent_chain` | ✅ raw SDK (`aws-sqs-sdk.yml`, pinned in a Micronaut module by `test_aws_sqs_delivered.py`). **Boundary — JMS over SQS reads as `jms`:** `@JMSListener(connectionFactory = "sqsJmsConnectionFactory")` derives through `micronaut-jms.yml` with protocol `jms`; choosing the protocol from the factory attribute is a per-attribute switch no word has. A Spring SQS sender and a Micronaut JMS-over-SQS listener will not link (DR-5) |

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
first-party annotation — Java's own `PubSubTemplate` calls are now the exception, publish and all
ten consuming methods alike, read directly with no annotation at all.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | **Micronaut `@PubSubListener` + `@Subscription`, `@PubSubClient` + `@Topic`** | the only first-party annotation surveyed; one catalog per direction | `annotation` | ✅ shipped (micronaut-gcp-pubsub 5.8.0, W58). Pinned by `tests/e2e/test_messaging_micronaut_delivered.py` |
| Java | Spring Cloud GCP `PubSubTemplate.publish(…)` | typed direct calls, not the channel-adapter indirection below | `registration_call` | ✅ shipped |
| Java | Spring Cloud GCP `PubSubTemplate` INBOUND — `subscribe`, `subscribeAndConvert`, `pull`, `pullAsync`, `pullAndConvert`, `pullAndConvertAsync`, `pullAndAck`, `pullAndAckAsync`, `pullNext`, `pullNextAsync` | all ten consuming methods the class declares, enumerated from the 5.1.2 jar's own declared methods, then split into consuming and publishing by a name-prefix test the probe states (`scripts/probes/w18_pubsub_inbound.md` §1); each takes the subscription name at argument 0. **Two different §8.6 chains**: for the eight `pull*` methods the call IS the consumption, so a trace reaching it is the whole chain; for `subscribe`/`subscribeAndConvert`, which return a `Subscriber`, the chain is the call PLUS the measured rule that `PubSubSubscriberTemplate.subscribe` calls `Subscriber.startAsync()` itself before returning (`javap -c`, 5.1.2, offset 26) | `registration_call` | ✅ shipped since F2 §3.9. **This row read ONE of the ten until W18**, so every PULL-based consumer derived nothing at all — not a partial row, not a question, but the same silence a module consuming no Pub/Sub produces. Payload shape is stated by the THREE overloads that take a `Class<T>` — `subscribeAndConvert` at argument 2, `pullAndConvert` and `pullAndConvertAsync` at argument 3; the other seven derive an address with `request_shape` NULL, because their return type is an untyped envelope and deriving a shape from it would be invention. **The `handler` recorded is the calling method, not the lambda that receives** — true of `subscribeAndConvert` before W18 and now of `subscribe` too |
| Java | `Publisher.newBuilder(TopicName.of(p, t)).build()`, `.publish(…)` | co-located build+publish chains resolve; a config-built/field-held `Publisher` derives an honest unresolved row instead of vanishing | `fluent_chain` | ✅ shipped |
| Java | `Subscriber` + `MessageReceiver`, `.startAsync()` | named implementers and lambda receivers both resolve; direct implementers only, and the registration plus its ACTIVATION is the evidence | `interface_implementation` | ✅ shipped — **this row used to say "over-reports, and knowingly"**, and it did: `Subscriber.newBuilder(subscription, receiver)` is CONSTRUCTION, construction subscribes to nothing, and a subscriber built and never started derived a live inbound endpoint. Our own fixture built two, started neither, and had both published as rows the suite asserted were correct. `registration.started_by` (D02 §1b-i) now requires the framework's activation chain — `build` then `startAsync` — following the registration through any number of intervening builder calls, on any path. **Two answers, not three:** the chain completes here → a row; anything else → a `registration_activation` question. There is deliberately no "provably dead" answer, because a subscriber assigned to a FIELD leaves the method through `putfield`, which is not a call site and so not a fact this walk can see — "no later call mentions this value" is inference, and §8 permits exclusion only on proof. **Falsified by** a module whose subscriber is started in a way the walk cannot reach and which files no question |
| Java | `PubSubInboundChannelAdapter` + `@ServiceActivator` | channel indirection | `config_join` | B — rides 2F's `config_join` once catalogued. *This row named `PubSubTemplate.subscribe(…)` as well, and stopped being true at W18, which derives it directly three rows above — leaving the page answering "is `subscribe` supported" both ways.* |
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

**An ambiguous handler is now unread rather than picked by hash order** (`A-M1`, principles
sweep §3.3). The receiver-to-handler lookup was a prefix scan over `method_symbols` ordered by
symbol — a SHA-256 of the descriptor — taking the first match, and the comment defending it
reasoned about the INTERFACE ("the interface declares exactly one, which makes that ordering a
tiebreak rather than a choice") while the lookup ran against the implementing CLASS. Nothing
stops a class declaring a private helper, a convenience form or a javac bridge beside its real
override, and the scanner deliberately keeps all three, so the tiebreak was a coin flip between
two methods one of which is wrong — published at `resolved`/`compiler`, and part of this
engine's dedup key, so a wrong pick can split or merge rows as well as mis-attribute one.

The selector is now name **and** parameter types (JLS 8.4.2), the same rule
`supertype_dispatch._members` already applies. One candidate resolves as before; several
resolve only when the interface is itself in the scan and its own declared parameter types name
one of them; otherwise the handler is **NULL**, which is what this engine's docstring already
promised. **The row still derives** — the destination is a separate fact, and withholding it
would trade a fabrication for a silent drop. **Falsified by** a module whose receiver overloads
its handler method while the interface lives in a jar: its subscription is now attributed to
nothing rather than to the wrong method, and closing that needs the interface's own bytecode,
which is D02 §7's unscanned-jar question.

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
| Java | `@Scheduled` — `cron`, `fixedRate(String)`, `fixedDelay(String)` | `annotation` | ✅ **shipped** (2O Task 8) — into `scheduled_work`, its own table, never `endpoints`: a method the framework calls on a clock speaks no protocol and has no address. Handler, trigger kind, expression **verbatim** |
| Java | `@Schedules` — two or more `@Scheduled` on one method, folded by javac | `annotation` (nested) | ✅ shipped — through capability 9.16. The catalog REQUIRES that capability rather than degrading: on a scanner without it a two-schedule method would carry no readable trigger while its single-schedule neighbour carried its own, so the whole catalog is skipped **visibly** instead |
| Java | `@Scheduled(cron = "${orders.sweep.cron}")` — a property placeholder | `annotation` | ◐ shipped as **`unresolved`, expression carried verbatim.** The value comes from configuration a deployment overwrites, so it is never substituted here. Closes when a non-wire row can read `resolved_config`, which needs an environment column this table does not have |
| Java | `@Scheduled(cron = "-")` — `@Scheduled.CRON_DISABLED` | `annotation` | ✅ shipped — **derives NOTHING** (`OI-2`, closed). CP-14 reads the constant off the annotation at spring-context 6.1.6, 6.2.19 and 7.0.9 and finds the post-processor comparing `cron()` against it immediately before `scheduleCronTask` and before nothing else, so the framework registers no task. `cron` is the only attribute with a sentinel: CP-14 row 3 enumerates every string comparison in that class and finds one |
| Java | `@Scheduled(cron = "-", fixedDelay = 1000)` — a disabled cron BESIDE a live rate | `annotation` | **Boundary — OVER-reports one row (`OI-34`).** CP-14 rows 4-5: the "a schedule was declared" flag is written before the sentinel comparison and read into a failing `Assert.isTrue` after it, so the container refuses to start — while we drop the cron row and publish the `fixedDelay` one. Not encoded: every conjunct this style has is per ATTRIBUTE, and refusing the declaration as a whole is a rule the grammar does not have (§8.1 rule 4). **Falsified by** such a declaration exporting a `scheduled_work` row |
| Java | `@Scheduled` naming two trigger attributes at once, or none — what the container does at startup with such a declaration | `annotation` | **Boundary — one row per attribute written, and none where none is.** Whether the container refuses to start is a startup question a repository cannot answer, so each declared trigger is reported as the code fact it is. A declaration naming no trigger derives nothing: there is no expression to carry |
| Java | `initialDelay`, `initialDelayString`, `zone`, `timeUnit`, `scheduler` — real `@Scheduled` attributes that are not a schedule | `annotation` | ✅ shipped — **none of them is read**, and `spring-scheduling.triggers-are-the-schedule-attributes` measures that a near-miss notices if one ever is. Reading `initialDelay` would publish the wait before the FIRST run as the interval between EVERY run |
| Java | Quartz `@DisallowConcurrentExecution` / `Job` implementations / `JobDetail` builders — a second scheduler, writing to the same `scheduled_work` table | `annotation` + `fluent_chain` | A for the annotation half, B for the builder half — neither catalogued |
| Java | Temporal / Cadence `@WorkflowInterface`, `@ActivityInterface` | `annotation` | A |
| Java | **Vert.x event bus** `vertx.eventBus().send("addr", m)` / `.consumer("addr", h)` — in-process pub/sub with **string addresses**, matchable like topics | `registration_call` | B |
| Java | Spring Integration `@ServiceActivator` (`inputChannel`, `outputChannel`) and `@InboundChannelAdapter` (`channel`) — the annotation names a CHANNEL, and configuration — where a project has any — says what the channel means | `config_join` | ✅ **shipped as a hand-off** (2O Task 9), through `config_join`'s new `binding.from: annotation_value`. Spring Integration defines no standard configuration key for a channel's destination — real apps wire them in bean definitions, and any key template would be a PROJECT convention — so the built-in declares no `key`, derives **no endpoint row and no ghost row**, and files one `channel_destination` open question per channel carrying the channel name and the handler symbol. Never a fabricated wire, never `peer: in-process` |
| Java | The DESTINATION behind a channel — `Amqp.inboundAdapter(cf, String…)`, `setQueueNames(String…)`, `Kafka.messageDrivenChannelAdapter(cf, String…)` — the queue or topic the adapter feeding that channel actually reads | `registration_call` | **Boundary — readable and unread, which is a different gap from an unreadable one.** Since extractor capability 9.15 these arrive as `{"kind":"array","elements":[…]}` with the same producer discrimination a single-`String` parameter gives and the arity beside them (`scripts/probes/spring-integration-destinations.md`, the 9.15 re-run — its original 9.14 headline says the opposite and is corrected in place). They are CALL-SITE arguments; `config_join`'s address input is `resolved_config` alone, which is built from configuration FILES (`application/resolve/config.py:107`), so no element can reach that join. **Falsified by** a module whose Spring Integration destinations are hard-coded at the adapter: every one is an open question rather than an endpoint row, and the string is sitting in the facts. Closes with a style that reads the elements and joins an adapter to its channel |
| Java | `@Transformer`, `@Router`, `@Filter`, `@Splitter`, `@Aggregator`, `@BridgeFrom`/`@BridgeTo` — the rest of the endpoint-annotation family — each also carries `inputChannel`/`outputChannel` | `config_join` | **Boundary — asks nothing.** Only the two annotations the probe measured are declared; §8.1 requires a framework's rule to be measured before it is built on, and the probe's harness carries neither. Each is one `channels` row once measured, with no engine change |
| Java | `@InboundChannelAdapter("orders")` — the `value` spelling of `channel` — the attribute written positionally | `config_join` | **Boundary — asks nothing.** The probe measured the `channel` spelling only, and that the two are `@AliasFor` each other is a fact of a jar this analysis does not scan. Closes with one measured `channels` row |
| Java | Spring Integration Java DSL flows (`IntegrationFlow`, `IntegrationFlows.from(…)`) and XML-configured flows — the flow's topology, and the anonymous channels inside it | `fluent_chain` / `filesystem` | **Boundary — derives nothing.** The DSL chain is FULLY reconstructable from within-method `result` ↔ `receiver` joins, with handler bodies named through `{"kind":"lambda","symbol":…}` (probe Q4), and no engine walks it. An XML-configured flow contributes **zero** facts — the extractor reads `target/classes/**/*.class` and the XML is a resource sitting beside them — so it needs a resource reader of its own, the same category as the `.avsc` reader |
| Java | The `protocol` column on a `channel_destination` question — which broker, if any, a channel actually reaches | `config_join` | **Boundary — the column is EMPTY, and that is the answer.** It read `amqp` from Task 9 until OI-1's fix: a wire STYLE had to declare a protocol (`resolve/endpoints.py`) and D00's closed set has no "unknown" member (NFR-5), so `spring-integration.yml` declared the one value the probe measured a channel join against end to end (Q3) — and **every** question it filed was filed under it, a Kafka- or JMS-fed channel's included. The rule is now keyed on whether the CATALOG derives endpoint rows rather than on what its style is nominally called, so a catalog that mints none declares no wire identity and its questions carry none. What remains is an ABSENCE, stated as one: nothing here reads which broker feeds a channel, the ledger row says so, and the renderer prints the channel name alone. **Closes when** the protocol comes from the ADAPTER that feeds the channel — Stage 4 adapter work, which needs the destination row above first. **Falsified by** a question carrying a protocol nothing measured |
| Java | **Akka / Pekko actor messaging** `ref ! msg`, `ref.tell(msg)` — receiver comes from an `ActorRef` created elsewhere | — | **C, possibly permanent — see §7** |
| Python | **Celery** `@app.task`, `task.delay(…)`, `.apply_async(queue=…)` — a real async boundary, easy to miss | `annotation` | A |
| TS | `bullmq` `new Queue("n")`, `new Worker("n", fn)` — string names, matchable like topics | `registration_call` | A |
| Go | `robfig/cron` `c.AddFunc("@hourly", fn)`; Temporal Go SDK `w.RegisterWorkflow(fn)` | `registration_call` | A |
| Go | `asynq`, `machinery` task queues — `mux.HandleFunc("task:name", h)` | `registration_call` | A |
| Rust | `tokio-cron-scheduler` `Job::new("0 * * * * *", fn)` | `registration_call` | A |
| Rust | Temporal Rust SDK — `register_workflow::<T>()`, `register_activities()`; **public preview, API still evolving** | `registration_call` | A |
| Rust | `apalis` — worker pulls from a Postgres/Redis/SQLite backend | `registration_call` | B |
| Python | APScheduler `@scheduler.scheduled_job("cron", …)` | `annotation` | A |
| Swift | `BGTaskScheduler.register(forTaskWithIdentifier:)` — identifiers also declared in `Info.plist` (§6) | `registration_call` | B |
| Any | Database access — Room `@Query`, JPA repositories, ORM models — a data boundary, not a protocol | `annotation` | B |

### 5.13 Language construct

Not a protocol, and not a library: a thing the COMPILER emits that a reader of the class
file has to recognise. **Almost nothing in this section is measured against real Kotlin**: the six corpora under
`examples/` contain **zero `.kt` files** between them, and the fixture contains exactly TWO —
`KotlinOrder.kt`, a data class, and `KotlinOrderRoutes.kt`, a reactive `coRouter`.

**Each row below says for itself whether the fixture exercises it**, and that is deliberate:
this paragraph carried a summary sentence for four revisions and was wrong every time — "no
`.kt` files at all", then "only nullability", then "nullability and `suspend fun`", then
"exactly one". A count that has to be re-derived whenever the fixture gains a class does not
belong in a preamble; the fact belongs beside the claim it qualifies. That is the honest state and it is why the levels are what they are. Kotlin is where this axis earns its keep — §5.1 to §5.12 hold **0
Kotlin rows out of 186** while `coverage_matrix.py` aliases Kotlin to Java, so the matrix
has been asserting a parity nobody measured.

| Construct | What the class file holds | Committed at | Support |
|---|---|---|---|
| Kotlin property nullability | The compiler states it once, in the protobuf blob inside every Kotlin class's `@kotlin.Metadata` — not in any annotation a scanner could read the way JSpecify's `@Nullable` is read | Scanner capability `kotlin_metadata` (M03) | **supported** — `extractor-jvm/.../KotlinNullability.java` decodes the blob and maps each property to the nullability its declared type carries — except a property declared as a bare type variable (`class Box<T>(val x: T)`), which is left to Java's rule on all three projections, field, getter and parameter, and whose field carries no `ext.kotlin` block at all (2026-09-12, `KotlinParameterNullabilityTest`) **Live at the FACT level and nowhere else**: the fixture's `KotlinOrder#id` carries `{"kotlin": {"nullable": false}}` and `#note` carries `true`, so the decoder fires here rather than only in `extractor-jvm`'s tests — but `KotlinOrder` is used by nothing, reaches no wire boundary, and contributes none of the fixture's 54 `shape_fields`. **The GETTER half closed 2026-09-11** (`G-63`): `getId()` reported `nullable: true, nullable_resolution: "resolved"` beside the `@NotNull` kotlinc writes on the same method — a certainty marker on a value the same fact contradicted — and now reports `false`, while `getNote()` correctly keeps `true`. **The PARAMETER half closed 2026-09-12** (`OI-82`, `extractor-jvm/.../KotlinParameterNullabilityTest.java`): a function's and a constructor's value parameters carry the nullability their declared type states, at every level of the type — `place(sku: String, qty: Int?, tags: List<String?>, meta: Map<String, List<Int>?>?)` reads `false, true, false[true], true[false, true[false]]`, and `KotlinOrder#<init>`'s `(id: String, note: String?)` reads `false, true` where both read `true` before. Metadata's type tree is walked beside the reference built from `Signature`, and applied only where the two agree on the shape at every level; where they do not — an inner class's enclosing instance, an enum's name/ordinal, both of which metadata's parameter list omits, and a `var` property's setter, whose descriptor metadata never keys at all — every parameter of that method keeps Java's rule (an extension function's receiver is omitted the same way, and since `kotlin-extension-functions` the declared types are laid from the slot after it — the extension-functions row below), which is less specific and never wrong (a `$default` bridge's descriptor is one metadata never keys either, and since `OI-81` it is read under its sibling's key instead — the row below). **A bare type variable keeps Java's rule too** (2026-09-12, with `OI-80`): metadata's "not nullable" on `x: T` in `fun <T> ranked(x: T): T` describes the variable, whose implicit bound is `Any?`, not what a caller binds it to, so `x: T` and the return `T` keep Java's `nullable: true` rather than metadata's `false`, while `y: T?` reads `true` because it is; the FIELD of a `val x: T` is left the same way and carries no `ext.kotlin` block, so the field, the getter and the constructor parameter of one declared type agree; a bound that would settle it (`T : Any`) is not read. |
| Kotlin `suspend fun` | An extra trailing `Continuation` parameter and an erased `Object` return | Q2's Kotlin boundaries; `REQUIREMENTS` scope line | **supported** (`G-63`, 2026-09-11). A suspending function is read as the ordinary function it describes: the trailing synthetic is dropped and the return is recovered from that synthetic's own type argument in `Signature`, with `kotlin/Unit` becoming `void` as a non-suspending `fun` returning `Unit` already reads. Nothing downstream knows coroutines exist, and no identity moved — a symbol hashes the RAW descriptor. **The type comes from `Signature`, the nullability from `@kotlin.Metadata`, and neither could supply the other**: measured, `fetch(String): KotlinSample` and `maybe(String): KotlinSample?` compile to one descriptor and one signature hash with kotlinc stamping `@Nullable` on both, so only metadata separates them; metadata in turn spells Kotlin classifiers whose boxed-versus-primitive mapping depends on the nullability itself. **Whether a method is suspending is metadata's statement, never its shape** — the structural test fires on 683 of 14,895 methods across `kotlinx-coroutines-core-jvm` 1.8.0 and `kotlin-stdlib` 2.2.0, and 228 of those are not suspend functions, mostly the `<init>` of generated state-machine classes. **Live on the fixture**: `KotlinOrderRoutes#listOrders` published `[request, $completion]` returning `java/lang/Object#` and now publishes `[request]` returning `ServerResponse#`, non-null. The endpoint row still carries no handler (§2), which is a separate gap. **At parity on primitives since 2026-09-12** (`OI-80`, `extractor-jvm/.../KotlinSuspendPrimitiveTest.java`): a type argument cannot be a primitive, so the `Continuation` spelled `suspend fun suspCount(): Int` as `Integer` where `fun plainCount(): Int`'s descriptor says `I`. Metadata's declared classifier, read beside the nullability it already supplied, now maps the eight `kotlin/Int`-style classifiers to the primitive when declared non-null — `suspCount` reads `int#`, the same whole reference as `plainCount` — and leaves `suspMaybeCount(): Int?` as `java/lang/Integer#`, nullable, because a nullable `Int` genuinely boxes. |
| Kotlin extension functions | A static method whose FIRST parameter is the receiver | Q2's Kotlin boundaries | **supported** — shipped 2026-09-12 as `kotlin-extension-functions`, proved by `extractor-jvm/.../KotlinExtensionsTest.java`. Measured on kotlinc 2.2.0: a top-level `fun String.shout()` compiles into the file facade `KotlinExtensionsSampleKt` (`@kotlin.Metadata` `k=2`) as `static shout(Ljava/lang/String;)`, a member `fun List<Int>.total()` as the instance method `total(Ljava/util/List;)`, and a suspending extension keeps the receiver first with the `Continuation` last — descriptor slot 0 in every case, named only in the `LocalVariableTable` (`$this$shout`), with no `MethodParameters` attribute. `KotlinNullability` now decodes the file facade (it returned `NONE` for anything but a class, so a top-level function's return and parameters took Java's rule and a top-level `suspend fun` kept its `Continuation`; both now read as a member's do) and keeps the key of every function whose metadata carries a receiver parameter type; the scanner emits `receiver: true` on that slot (absent means false) and lays the declared value parameters from the slot after it, so `fun String.repeatShout(suffix: String)`'s `suffix` reads `nullable: false` where it took Java's rule before. The slot is kept, not dropped — a call site names the method by its full descriptor — and its own type keeps Java's rule; the `$default` bridge of an extension with defaults (`decorate$default(Ljava/lang/String;Ljava/lang/String;ILjava/lang/Object;)`, receiver first, no owner) marks the same slot through `OI-81`'s sibling read. **Not read**: extension PROPERTIES' getters (`val String.first: Char`), top-level properties, and `@JvmMultifileClass` parts (`KotlinClassMetadata.MultiFileClassPart` still decodes to `NONE`) — their receivers are unmarked and their types keep Java's rule. No corpus here has one on a wire boundary, so there is still no live instance |
| Kotlin `$default` synthetic methods | The compiler emits a second method carrying the default-argument mask beside every function with default parameters | Q2's Kotlin boundaries | **shipped** (`OI-81`, 2026-09-12, `extractor-jvm/.../KotlinDefaultBridgeTest.java`). The bridge is recognised from its shape — measured on kotlinc 2.2.0, `greet$default` is `static synthetic (Owner;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String;`: the receiver (absent for a `@JvmStatic` function), the function's own slots, one `int` mask per 32 parameters, an `Object` marker — and its fact carries `bridge_of: "greet"` beside `synthetic: true`, with its return and the function's own slots reading the types the FUNCTION declared: `name: String` reads `nullable: false` where it read Java's `true` beside a `greet` reading `false`. The receiver, the masks, the marker and a suspend sibling's `Continuation` keep Java's rule. **A suspend sibling's bridge returns the erased `java/lang/Object#`** with the declared nullability laid over it — accurate for the erased protocol (the value or the `COROUTINE_SUSPENDED` marker), not the declared type, which only the sibling's `Signature` holds and the bridge does not. **Where the receiver question cannot be settled** — metadata keys neither candidate sibling, or keys both (an `object`'s `@JvmStatic fun js(a: String, b: Int = 0)` beside an arity overload `fun js(b: Int)`) — the bridge carries `bridge_of` and nothing else: ambiguity is not a guess, so every slot and the return keep Java's rule. **Still two symbols**, on purpose: a call site names the bridge by its own descriptor, and every consumer that filters `synthetic: true` already excludes it from a wire boundary, so `bridge_of` is what a later dispatch follows back rather than a row today. The bridge carries **no signature at all** (`GenericSignatureTest`), so its parameterized slots stay erased at the type level — only the declared nullability is borrowed, at the levels the erased reference and metadata agree on, which for a `List<String?>` is the top. **Live**: a data class emits one, and the fixture's `KotlinOrder#copy$default` now reads `bridge_of: "copy"`. |
| Kotlin `DefaultImpls` | An interface with a default method body compiles to a nested `DefaultImpls` class holding the body | Q2's Kotlin boundaries | **supported** — shipped 2026-09-12 as `kotlin-defaultimpls`, proved by `extractor-jvm/.../KotlinDefaultImplsTest.java` (the facts) and `tests/application/test_call_edges.py`'s `default_impls` cases (the dispatch). Measured on kotlinc 2.2.0 with no `-jvm-default` flag: `Pricer$DefaultImpls` is `public final` — NOT `synthetic` — with `@kotlin.Metadata k=3`, no fields, no constructor, and every method `public static` with the interface at descriptor slot 0 (`price(LPricer;)I`, `discount(LPricer;II)I`, and the `static synthetic discount$default(LPricer;IIILjava/lang/Object;)I` bridge), plus an `InnerClasses` entry naming the interface as its outer class; under `-jvm-default=disable` (kotlinc 2.4.10) the holder's flags, methods and descriptors are identical. The scanner recognises the holder from all three of its name, that `InnerClasses` entry and every method having that shape (a hand-written nested class of the name fails at its own constructor), writes `implements_default_of: "<Iface>#"` on the holder's type fact — module-prefixed as `enclosing` is — and `bridge_of: "<interface method>"` on each body, the `$default` bridge inside it naming the function as it does anywhere. The holder's own metadata declares no function, so a body's slots and return keep Java's rule; the declared types are in the interface's class file, and the scanner reads one class at a time. **Dispatch** (`resolve/dispatch.py`, read by `call_edges` and `return_flows`): a call to an interface method that declares no body of its own resolves to the holder body the scanner attributed to it, matched by name and erased parameter types with slot 0 dropped — and ONLY where the interface declares none, because kotlinc 2.2.0's default mode emits BOTH a JVM default method on the interface and a `@Deprecated` holder stub calling back into it, and joining the stub too would turn every such call from `resolved` to `narrowed`. **What this closes is narrower than this row used to read**: in both modes kotlinc also gives every implementing class its own forwarding `price()` (`invokespecial Pricer.price()` under `enable`, `invokestatic Pricer$DefaultImpls.price(this)` under `disable`), so a scanned implementor already reached the body in two hops through ordinary call edges; the join closes the case where the implementors are outside the scanned module and the holder body was the boundary. **The consequence for a SCANNED implementor under `disable`**: its forwarding method is already a candidate, so the holder body joining beside it moves such a call from `resolved` (1 candidate) to `narrowed` (2) — parity with what `enable` mode already reads (the interface's default plus the forwarder), and the JVM never dispatches to the holder directly. **Not live**: no interface in the estate declares a default method body. |
| Nested and inner classes | Ordinary class files with `InnerClasses` naming their enclosure | Phase 2C | **supported** — the phase-1 skip is lifted; annotations resolve the same nested or not **Live**: 594 nested-class symbols across the estate. |
| Lambda bodies | `invokedynamic` plus a synthetic method holding the body | Scanner capability `lambda_body` (2Q, M03 9.17) | **supported** — a call made inside a lambda is an edge from the enclosing method **Live**: 15 lambda-body symbols, and FOUR endpoints are handled by one — `GET /other`, `GET`/`HEAD /fn/health`, and a Pub/Sub subscription. |
| Formal type parameters | `Signature` (JVMS 4.7.9), which the erased descriptor discards | Scanner capability `type_parameters` (W5) | **supported** — see §5.14's substitution row for what is done with them |
| Throw exits | An `ATHROW` instruction: the method leaves through it, and no method is called | `G-52` (F1 §2.3) | **supported** — shipped 2026-09-12. Every `ATHROW` is a `call_site` fact with `invoke_kind: "throw"` whose target is the thrown TYPE and no method (`name` and `descriptor` absent, D00 §5), so a trace that ends in a throw stops there and says so instead of looking like one that fell off the end. The type is read from the thrown value's producer — a `NEW` names it exactly, an invoke's declared return type is a bound the class file states — and is NULL for a rethrow, whose type lives in the try-catch table this pass does not read; the exit is published either way, because the exit is the fact and the type is the detail. `resolve/call_edges` gives the site a row with no candidates and `terminal_kind: throws`, decided from the instruction rather than by a catalog rule (the one member of `TerminalKind` produced that way — `OI-75`). Proved by `extractor-jvm/.../MethodFlowTest.java`'s `publishes_a_throw_as_an_exit_naming_the_thrown_type_and_no_method` (the three producers), `tests/domain/test_facts.py` (the shape and the invariant that only a throw names no method, neither half of one), `tests/application/test_terminals.py`'s `test_a_throw_edge_is_throws_from_its_invoke_kind_and_not_from_a_rule` and `tests/application/test_call_edges.py`'s `test_a_throw_site_is_one_resolved_edge_to_the_thrown_type_and_reads_throws` (the row: no callee, `resolved`, `throws`, NULL target for a rethrow), `tests/application/test_trace.py`'s `test_a_throw_with_no_target_stays_null_on_its_step` and `tests/application/test_reachability.py`'s `test_a_throw_whose_type_was_unread_reaches_no_symbol` (the NULL stays NULL and names no symbol), `tests/egress/test_render_traces.py`'s `test_a_throw_step_is_an_arrow_labelled_throw_into_the_thrown_type` and `test_a_throw_whose_type_was_unread_is_a_self_arrow_said_in_words` (the diagram arrow reads `throw` into the type's lifeline; a type-unread throw is a self-arrow on the method that exits, labelled in words, and the step table's call cell reads `throws (type unread)`) and `tests/e2e/test_vertical_slice.py` (the counts). **Live**: 39 throw sites on the fixture — 8 named types, 5 rethrows unread — and all 39 read `throws`. **`signature.throws` — the DECLARED clause beside this row's OBSERVED exits — is consumed by the document, `Fails with`, shipped 2026-09-12 (`G-74`).** The endpoint detail block's `- Fails with:` line pairs the handler's own declared exceptions (`handler_signature`, read the same way the Request/Response lines already do) with a reachable throw-exit call site (`reachable_throws`, joining `reachability` to `call_sites` at the composition root) — declared first, both sorted, an unread rethrow's target said in words once rather than repeated. Proved by `tests/egress/test_render.py`'s `test_a_handlers_declared_exception_renders_as_fails_with`, `test_a_reachable_throw_exit_joins_the_same_line_after_the_declared_half`, `test_a_throw_site_whose_target_was_unread_says_so_in_words` and `test_no_fails_with_line_where_neither_half_has_anything`. |

### 5.14 Shape and contract

The payload axis. A row here is a SHAPE question — what a field is called on the wire, what
a wrapper does to the body — and none of it is per-protocol: the same wrapper behaves the
same way over REST and over a message broker.

| Surface | What it is | Committed at | Support |
|---|---|---|---|
| Generic type-parameter substitution | A declaration says `CommonResult<T>` and a use says `CommonResult<OrderView>`; the fields of the use are the declaration's with `T` replaced | Implied by FR-4; one adjacent sentence at `COVERAGE.md` about Data REST only | **supported** (W25), for a TYPE's own parameters. The map is built POSITIONALLY — a reference's arguments are positional, so the first declared name binds the first argument — and a reference carrying fewer arguments than the declaration has parameters binds nothing rather than binding what it can, because a partial binding reads as a real type downstream. A generic METHOD's own parameters are deliberately excluded from the map's keys: a class and a method that both declare `T` are two unrelated scopes, and substituting across them is the hazard, not the feature |
| `Page<T>` / `Slice<T>` | **Interfaces**, so they declare no fields — and Spring does NOT send the element type on the wire, it sends the envelope with `content` inside | Implied by FR-4 | **supported** (W26), and measured: with the jar in reach a `Page<OrderView>` response went from an open shape with zero fields to the envelope's own. Rooting THROUGH `Page` would have published `OrderView` as the body, a contract no client receives |
| The same, without the jar | `Page` and `Slice` live in `spring-data-commons`, not in the module | — | **partially supported.** A module that has not run `extract_libraries` leaves its own `Page<OrderView>` open with zero fields, and `Page` is reported as a type nothing could expand — stated, not silently empty |
| HATEOAS `EntityModel` / `CollectionModel` / `PagedModel` | The same envelope shape one library along | Implied by FR-4 | **unsupported, and unmeasurable here.** These appear in **zero files across all six corpora**, so the rule that covers `Page` has never been exercised on them and claiming they work would be claiming a measurement nobody took. **Falsified by** a corpus that uses one |
| Batch-listener generics | `@KafkaListener(batch = true)` takes `List<Foo>`, so the message shape is the ELEMENT type and not the list | `docs/roadmap.md` | **unsupported.** No catalog rule names `batch`, so a batch listener's payload is read from the declared parameter and published as a list. **Falsified by** a batch listener whose export row carries the ELEMENT type — which is what this row says does not happen |

### 5.15 Configuration source

Where a value comes from, and whether a derived row may read it. The distinction that
matters is not the file format: it is which engine is allowed to ask.

| Source | What it is | Committed at | Support |
|---|---|---|---|
| `application.yml` / `.properties`, with profiles | Read into `config_entries` and resolved into `resolved_config`, per environment | FR-19 and D04 | **supported** — both tables ship in the bundle, and an unresolved value carries the reason it stayed unresolved rather than being dropped |
| A derived row reading a resolved key | Two passes do it — `config_join.py` and `derived_resource.py` | D02 | **partially supported.** `annotation_driven` does NOT read `resolved_config`, which is why an Actuator module overriding `management.endpoints.web.base-path` is still published under `/actuator` (§5.1). The boundary is per-ENGINE, not per-key |
| Redaction of a configured value | `redact_value(key, value)`, applied at the exits | FR-19's 2026-09-02 amendment | **supported** — the workspace stays verbatim and the mask happens at the rendered document, the exported bundle, and the enrichment read path |

### 5.16 Trace and diagram

A trace is a named query rather than a table (D01), so this axis is about what the WALK
does and what a diagram drawn from it may assert.

| Surface | What it is | Committed at | Support |
|---|---|---|---|
| The walk itself | Root to terminal over `call_edges`, an explicit stack | FR-6, FR-7 | **supported** — see "Where a TRACE stops" below for every reason it halts, each measured |
| Depth bounding | — | FR-6's "not bounded by depth" | **supported** by removal (W31): the bound never fired and is gone, so nothing needs a counter to stay finite |
| Materialised reachability | One row per (root, symbol) with the shallowest depth | F8 §9.4 | **supported** (W37) — §3a-xiii |
| Branch distinction | Two `return` statements are two possible answers; an `if` contributes both sides | — | **unsupported, and ruled rather than missing.** A trace is reachability, never execution. Distinguishing branches would require control flow, which the scanner does not read |
| The contract class diagram | Association, `extends` and `implements` arrows | F7 §8.4 | **partially supported** (W33): `<\|..` implements has **no live instance in any corpus** and ships pinned rather than deferred, with the absence recorded |

### 5.17 Bundle and export

| Artifact | What it is | Committed at | Support |
|---|---|---|---|
| Every schema object travels | 26 of 26 tables and views, with no exclusion class | FR-18; D06 §5, ruled by the user (C10) | **supported.** For four phases the export was a hand-written list of eleven names and the seven it omitted — `raw_facts`, `call_edges`, `return_flows`, `roots`, and the views `config_entries`, `field_writes`, `method_returns` — were dropped from every bundle with nothing saying so, which made D06's own sequence-diagram row false as written. A ratchet now asserts the export's query list EQUALS the schema's object list, so the omission cannot recur |
| The versions that produced it | `sextant_version`, `fact_schema_version`, `graph_schema_version` in `manifest.json` | FR-18 | **supported** — D06 §3 |
| Refusing to join bundles of differing vintages | FR-18's second sentence: assembling a system from artifacts of differing vintages is *refused rather than silently joined* | FR-18 | **unsupported, and the recording half is what ships.** The manifest states every version a refusal would need; nothing reads two manifests and compares them, because v1 has no consumer that assembles a system from bundles. The row exists so the half that is missing is visible beside the half that is not |
| The index bundle | Eight NDJSON files an agent greps | F8 §9.3 | **supported** (W35, W36) — §3a-xii |

### 5.18 Question ledger

| Entry | What it is | Committed at | Support |
|---|---|---|---|
| `open_questions` | What no programmatic pass could answer, written for the enrichment tier | D06 §5 | **supported** — the table ships in the bundle |
| An overlay that disagrees with the graph | *"No overlay silently overrides evidence: where an overlay and the graph disagree, the disagreement is recorded as an open question"* | FR-15 clause 3 | **unsupported.** `open_questions.py`'s `QUESTIONS` is a CLOSED set of twelve kinds — `record_open_questions` raises on anything outside it — and none of them is an overlay/graph disagreement; its four writers are the format, environment-divergence, service-identity and routing-conflict passes. The overlay FR-15 means is D03's, which has no producer at all (`PROJECT.md` lists D03 and M01's overlay as planned; the 2026-09-05 principles sweep records the whole tier as absent under `B-C2`). The only overlay in `src/` is the ENRICHMENT overlay, a different envelope — and when one of its claims disagrees with the graph, `enrich/validate.py` REFUSES the claim and render excludes it with a count, which is not a ledger entry |
| A curation FILE supplying links and context | *"a claim about the world, never an edit to a fact"* | FR-16 clause 1 | **unsupported.** No curation file exists. The only overlay in `src/` is the ENRICHMENT overlay, which supplies prose rather than links, and D03's overlay tier — the one FR-16 means — has no producer at all (`PROJECT.md` carries D03 and M01 as `planned`; the 2026-09-05 principles sweep records the whole tier absent under `B-C2`) |
| A proposal written in the form a curation takes | *"accepting it requires review rather than transcription"* | FR-16 clause 2 | **unsupported.** There is no curation form to write a proposal in, and no acceptance step: `domain/enrichment.py` carries no proposal or accepted state, and `api.py` loads `.sextant-enrichment.json` and applies it at render unconditionally. `validate.py`'s check is GROUNDING — a claim naming a symbol nothing declares is never written — which is a different guarantee from review |

> **Re-assessed 2026-09-10 (W52 review).** The FR-16 row here read *"no verb asserts, corrects
> or deletes a statement"* as its evidence of a gap. That was evidence against the wording
> **W51 deleted**. The requirement now says curation is *"never an edit to a fact"* — so the
> absence of such a verb is the requirement being honoured, not missed. What is actually
> missing is the curation file and the proposal form, and the two rows above say that instead.

### 5.19 Rendered document

The `## Coverage` section of a rendered module document, and the reporting FR-17 commits to.

| Section | What it is | Committed at | Support |
|---|---|---|---|
| The commit a workspace was built from | — | FR-17 clause 1 | **supported** |
| Which source files the compiled artifacts did not account for | `{documents, partial_documents}` | FR-17 clause 2 | **supported**, and an analysis that proceeded despite uncovered sources is recorded as PARTIAL rather than silently complete |
| The distribution of call sites across the resolution values | — | FR-17 clause 3 | **supported** (W38). Every resolution figure this project has ever quoted came from a throwaway script; these are standing. Three distributions ship and the REACH rate leads, because `resolution` alone reads 100% on two of four corpora — it says whether dispatch settled a call, and naming a target the compiler wrote is easy |
| Every capability an extractor lacks that a catalog required | — | FR-17 clause 4 | **supported** — a catalog declares what it `requires` and the workspace says which requirement went unmet |
| Composed on ONE path | `resolve()` and `render` must produce the same summary | — | **supported** (W38): `coverage_of(workspace)` is called by both. Composed only in the resolve pipeline, a figure reached the manifest and never the rendered document |

### 5.20 Query and findings

Four REPORTS about the code's shape, and two command-surface rules — six rows. **The first four are no
longer requirements of Sextant** — W51 moved them out of `REQUIREMENTS.md` to
[Usage scenarios](REQUIREMENTS.md#usage-scenarios), because the user ruled they are things a
CONSUMER derives from what Sextant reports: *"Sextant can only provide the ammo, but won't be
pulling the trigger."* They stay measured here, and the measurement is unchanged — none has a
producer — but `unsupported` now means *we do not build this*, not *we promised this and have
not built it*. The FR numbers are kept as the addresses a reader already has; each is struck
through to say it is retired. Of the two FR-20 rows, the FIFTH is retired too — W51 removed
the clause it measures — and the SIXTH is the live requirement.

| Report | What is committed | Committed at | Support |
|---|---|---|---|
| Drift detection | Where a module holds both a declared contract and an implementation of it, record both and report any disagreement; authority is decided by the BUILD, and an artifact the build does not consume is documentation | ~~FR-11~~ (scenario) | **unsupported.** No pass compares a declared contract to an implementation. The facts a comparison needs — `shapes`, `shape_fields`, and the resources a build consumes — all ship; nothing joins them |
| Refactor findings | Dependency cycles between modules or packages, symbols with disproportionate coupling, violations of a declared layering | ~~FR-12~~ (scenario) | **unsupported.** Note the requirement's own guard, which any producer must honour: a symbol is reported unreachable only where NO unresolved call site exists in the scope searched — and between 22% and 68% of a corpus's graph ends at a boundary, so that guard would withhold most findings on most modules |
| Design findings | Coupling between candidate boundaries, shapes crossing more than one boundary, the contracts each boundary would carry | ~~FR-13~~ (scenario) | **unsupported.** `shapes` and `endpoints` carry what "a shape crossing more than one boundary" needs; no pass asks the question |
| Structural performance risk | Remote hops per endpoint, distinct services involved, an endpoint reached twice in one trace, a persistence or remote call inside a loop, a blocking call on an async path | ~~FR-14~~ (scenario) | **unsupported**, and two of the five are further out than the other three: "inside a loop" and "on an async path" both need control flow, which the scanner does not read (`control_flow` is one of the three unshipped capabilities). The other three are queries over `reachability` and `call_edges` as they stand |
| Approximate subject names | *"where a name is ambiguous Sextant lists the matches and stops rather than choosing"* | ~~FR-20~~ (retired W51) | **unsupported, and the clause is gone.** No command resolves a subject approximately, so the ambiguity rule governed nothing. FR-20's W51 amendment removed it and points here; what a reader wanted is real and ships one layer out, as `<bundle>/index/` |
| Every command takes an exact identifier | *"every command takes one"* — the clause W52 removed from FR-20, kept here as the record of what was promised | FR-20 | **unsupported** (W52), which is why the clause is gone from the requirement rather than left standing. All four verbs take a filesystem PATH that must already exist — `@click.argument("path", type=click.Path(exists=True, …))` in `src/sextant/cli/app.py`, and `sextant.api.analyze(path, *, allow_resolve=False)` has the same shape. Results DO carry exact identifiers; nothing takes one back. FR-20 now states this as its own gap |

---

### 5.21 Out of scope for v1 (Q3)

Q3 ruled that v1 builds **the five asymmetries only** — the missing half of a surface we
already claim — and that everything else is a stated boundary. These are the three still
open of the four the gap analysis named — Kafka Streams shipped and moved to §5.8 — each
`unsupported` with what it would take, so a reader meets them here rather than inferring
them from silence.

| Surface | What it is | Committed at | Support |
|---|---|---|---|
| **Spring Cloud Gateway** | Routes declared in a `RouteLocator` builder chain or in `spring.cloud.gateway.routes` configuration | `G-30`, and the design calls it *"the largest single hole"* | **unsupported.** Both halves are shapes this analysis has vocabulary for — a builder chain is `fluent`'s, a configuration list is `config_join`'s — and neither is catalogued. A gateway module publishes no routes at all, which for a gateway is its whole reason to exist |
| **Programmatic Jakarta WebSocket registration** | `ServerEndpointConfig.Builder.create(Class, "/path")` rather than `@ServerEndpoint` | `G-34` | **unsupported.** `jakarta-websocket.yml` reads the annotation only. The programmatic path is a `single_call` on a builder, and W46 read the CLIENT direction of this same library without touching it |
| **`@DgsEntityFetcher`** | Netflix DGS federation entity resolution | `G-40` | **unsupported.** `netflix-dgs.yml` reads `@DgsQuery`, `@DgsMutation`, `@DgsData` and `@DgsSubscription`; the federation annotation names an entity type rather than a schema field, which is a different identity this catalog has no rule for |

### 5.22 Class-file attributes deliberately not read (F1)

Every attribute JVMS 4.7 defines is in `AttributeLedger` in exactly one of two states — read,
naming the callback that reads it, or deliberately not read with a stated reason. **There is
no third state**, and `AttributeLedgerTest` compares the ledger against JVMS's own list and
refuses a reason that is a deferral in disguise. §2c has the whole argument; this is the
residue, enumerated so it carries a support level like everything else.

| Attribute | Why it is not read | Support |
|---|---|---|
| `StackMapTable` | Verification metadata. It describes no declaration — it tells the verifier what the operand stack looks like at each branch target | **unsupported, and ruled rather than deferred.** Nothing a boundary could be derived from |
| `LocalVariableTypeTable` | Duplicates `Signature` | **unsupported, measured.** It adds a local's generic signature where the plain `LocalVariableTable` has the erased one — and the NAMES W6 wants are in the plain table, while generic parameter types already come from `Signature` (W5). Reading it would duplicate what is read |
| `Module` | Module identity comes from the build's coordinates | **unsupported.** `module-info.class` is suppressed whole |
| `ModulePackages` | The same | **unsupported** |
| `ModuleMainClass` | The same, and it has no visitor to be read from once `module-info.class` is suppressed | **unsupported.** Measured over 1,672 cached jars: 383 carry a module descriptor and 6 of those declare a main class |

### 5.23 Declared slices (Q4)

Q4 ruled that a catalog may cover part of its framework **where the slice is declared** — in
the catalog and here — with what falls outside it. Presence stops meaning completeness. The
cost is a per-catalog enumeration pass, and `scripts/probes/w19_catalog_surface/run.sh` is
what pays it: it reads each owner's declared methods out of the jar and cross-references the
catalog AS LOADED, so a release adding an addressable method fails a test rather than quietly
widening the distance between what a catalog claims and what it reads.

| Slice | Catalog | What is outside | Support |
|---|---|---|---|
| `G-44` | `spring-jms-template`, `spring-rabbit-template`, `spring-sqs-template` | `spring-sqs-template` reads its SEND half only and declares the rest outside. `spring-rabbit-template` and `spring-jms-template` now BOTH read both halves (`scripts/probes/w59_template_receive_halves.md`): Rabbit reads `convertAndSend` plus the nine queue-naming `receive`/`receiveAndConvert`/`receiveAndReply` overloads, and JMS reads `convertAndSend` plus the four destination-naming `receive`/`receiveSelected`/`receiveAndConvert`/`receiveSelectedAndConvert` overloads. Each still declares outside: Rabbit's destination-less receive overloads, request/reply forms and setters; JMS's `send`/`sendAndReceive`, `browse`/`browseSelected`, `execute`, the setters, and the `jakarta.jms.Destination`-typed and arity-1-selector overloads of its four read receive names | **partially supported**, declared |
| — | `spring-pubsub` | **NOTHING.** *This file was listed under `G-44` as reading "the send half only" and marked declared; both halves were false.* It declares TEN `direction: inbound` methods — `subscribe`, `subscribeAndConvert`, and the eight `pull*` forms — and derives a live inbound row on the fixture beside its outbound one. It has no `slice:` block because it needs none: the surface probe measures 11 of `PubSubTemplate`'s 20 read and records that **no unread method addresses a wire**, which is the one case the enumeration says needs no slice | ✅ **supported**, both directions |
| `G-37` | `spring-webflux-router`, `spring-mvc-router` | `RouterFunctions$Builder` entirely — 0 of 20 on each side. `route()`'s builder DSL has been the reference documentation's recommended Java shape since Spring 5.2 | **partially supported**, declared |
| `G-43` | `aws-sqs-sdk` | `SqsAsyncClient`'s other 27 methods (`sendMessage` is read on it too, since `G-43`), the batch forms, and the entire inbound direction including `receiveMessage` | **partially supported**, declared |
| `G-45` | `spring-data-rest` | The base contracts plus `JpaRepository` and `MongoRepository` (7 of 28); every other store-specific contract (R2DBC, Cassandra, Elasticsearch, Neo4j, Couchbase, and every reactive/coroutine/RxJava variant) is outside | **partially supported**, declared |
| `G-47` | `spring-integration` | 7 of 11 channel annotations | **partially supported**, declared |
| `G-41` | `netflix-dgs` | **NOT a declared slice, and the row that said so was wrong three ways.** The file is `netflix-dgs.yml`, not `dgs-graphql.yml`; it carries no `slice:` block; and its own comment is headed *"Why this is not `slice.outside`"* — filing it as one *"would let a reader conclude the annotations themselves are unhandled, which is the opposite of true"*. The mechanism this cell used to name is one the catalog records as FALSE: `@Inherited` inherits from SUPERCLASSES and never through methods, and four of the five annotations are `@Target(METHOD)`, so the bit is inert. The real gap is a superclass METHOD walk — `docs/open-issues.md` `OI-67` | ✅ **supported** for the annotations it reads; the inherited-method case is `OI-67`, not a slice |
| — | `spring-stomp-template` | 11 of `SimpMessagingTemplate`'s 14 methods, one of them addressing-shaped | **partially supported** (W43), declared |

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

### What a trace can start from

2Q's `I1` produces [D00](components/D00-fact-schema.md) §4's `root_kind` into
[D01](components/D01-graph-schema.md) §3's `roots`, so "a scheduled job is a first-class
root" stopped being a sentence in a document. Two of the set's three members have a
producer; the third does not, and this is where a reader meets that.

| Root kind | Produced from | State |
|---|---|---|
| `inbound_endpoint` | every `endpoints` row the module exposes and names a handler for — `direction <> outbound`, so a `both` row from the linking tier would keep its trace; no pass here writes one since W27 | ✅ shipped. 77 handler-bearing rows are 77 root rows and 66 roots on the orders-service fixture: a root is a place a walk starts, not an address, and the row carries the address so a reader can find the walk by the URL they know |
| `scheduled` | every `scheduled_work` handler | ✅ shipped. The user's own ruling — a scheduled job still contains business logic — and the reason `I1` was promoted out of paperwork |
| `entry_point` | nothing | **Boundary — the member exists and no producer writes it.** Which signature starts a program is a rule of a LANGUAGE, and ARCHITECTURE §10 keeps language knowledge out of the language-blind half: the descriptor a runtime looks for belongs in a catalog exactly as a framework's annotation does, and no catalog declares one. Matching on a method's NAME alone would derive a root for any method that happens to be called that. **Falsified by** a module whose only starting point is a `main` producing no trace at all. **Closes with** a catalog declaring the entry-point signature — `docs/open-issues.md` OI-22 |

**An error handler is deliberately not a root.** It runs INSIDE work something else already
started, so a trace beginning at one would report an exception path as though a request or
a clock had begun it. `error_handlers` therefore feeds nothing here, while `scheduled_work`
does.

**A root carries the wire address that reaches it** (2Q close). `roots` holds one row per
(handler, kind, address) and `roots_of` collapses them into one root per (handler, kind), so
a handler serving three paths is still one walk and one trace — and `## Traces` names that
trace by `GET /order/list` as well as by the handler descriptor. A root nothing addresses —
a scheduled job — carries three NULLs and renders `no wire address`: an absence, not an
unread value.

**An exposed row that names no handler produces no root, and that is an under-report worth
naming.** A functional-route row — `RouterFunctions.route(GET("/kt/orders"), handler)` — is
a real served address whose handler is a LAMBDA the chain reader did not name, so the row
carries `caller` (the method that built the router) and a NULL `handler`. **Measured: 5 of
the orders-service fixture's 82 exposed rows**, four functional routes and one binding whose
destination configuration named nothing. Making the `caller` a root instead would state that
a request trace begins at the router REGISTRATION, which runs once at startup and is not the
work the request does. **Falsified by** a functional route whose real work is invisible in
every trace. **Closes with** the chain reader naming the lambda as the row's handler — at
which point these become roots with no change here — `docs/open-issues.md` OI-23.

### Where a TRACE stops, now that there is one

2Q's `G4`/`I3` walk from a root to every terminal (`application/query/trace.py`, over
`call_edges`). Measured on `macrozheng/mall`'s `mall-admin` — 160 endpoints, Boot 3.x, JDK
21, built and analysed with the shipped pipeline — rather than reasoned about.

| Where it stops | Measured on `mall-admin` | Why, and what closes it |
|---|---|---|
| **The third party.** A mapper, a repository, a driver, the JDK: the call IS the terminal | **1,966 of 2,608** call edges | Ruled, not a gap. We do not trace into a dependency and we do not read its configuration, so a terminal is a method name and never a table name |
| **A sibling build module.** A call into another module of the same reactor leaves for a workspace this one does not hold | included in the 1,966 above, and **indistinguishable from it** — `CommonPage#restPage` and `CommonResult#success`, the two calls that compose `/order/list`'s response, are both this | Correct in that no body was read here, incomplete in that a body exists somewhere. Joining the two is `Bundle`/`Link` work, not this walk's. **Falsified by** a service that delegates real logic to a sibling module and shows a one-hop trace |
| **A cycle.** The callee is already on the path from the root | 1 trace, reachable only through a lambda body (`UmsMenuServiceImpl#covertMenuNode`, a recursive menu tree) | Not a gap: recursion is real code, so the walk states it and stops. Following it is the only alternative and it does not terminate |
| **A method already expanded elsewhere in the same trace** | 40 steps | Its subtree is shown at its first occurrence. Expanding per route copies every shared subtree once per path that reaches it, which is the cost D01 gives as its reason for a trace being a walk rather than a stored table |
| ~~**The depth bound**~~ | **GONE, W31** | It never fired: the deepest trace is **9 edges** across `mall-admin` (160 traces), `spring-petclinic-rest` (37) and `jhipster-sample-app` (38), against a bound of 64. This row said 5, measured on mall-admin alone and stale. The walk is an explicit stack now, so nothing needs a counter to stay finite and FR-6's "not bounded by depth" is met (`OI-27` closed) |
| **A `dynamic` site that creates no body** | 56 of `mall-admin`'s 74 `invokedynamic` sites | String concatenation compiles to one whose bootstrap is a compiler artifact rather than a call the program makes. An edge to it would put a platform factory into a trace at every string a method builds |

**A trace is reachability, never execution**, and three consequences of that belong to a
reader rather than to a footnote: branches are not distinguished (two `return` statements
are two possible answers; an `if` contributes both sides); a `narrowed` step walks every
candidate and picks none; and a `dynamic` step names a body **created** at that line, which
runs later, elsewhere, if at all.

**What "reaches a terminal" counts, and why our number differs from the roadmap's.** Every
one of `mall-admin`'s 160 roots reaches a boundary, because a call into the JDK is a
boundary exactly as a call into a mapper is — the WALK does not classify a terminal, and
`Stop` is the only thing it decides. The roadmap's "158 of 160 reach a real terminal (DB /
cache / object store)" is a classified count. It was reproduced by hand before W30 and the
classification is read now (§3a-viii): **155 roots reach a mapper or DAO terminal**, three
more reach an object-store client (`io/minio/MinioClient`, `com/aliyun/oss/OSSClient` —
still `unresolved`, since no rule names them and `TargetKind.file` has no producer,
`OI-75`), and the two that reach neither are `GET /admin/refreshToken` and `POST
/aliyun/oss/callback` — the same two the roadmap names, verified in source.

**Values through library code** are unchanged by any of this: `stream().map(f).collect()`
leaves for the JDK and comes back, the `collect` result is visible, per-element provenance
is not.

**Every one of the stops above is now something a reader SEES**, which is what changed when
`## Traces` landed ([M07](components/M07-renderer.md)). Each is a `Stop` value on the step's
own row, each is bracketed on the arrow in the sequence diagram, and each is counted in that
diagram's `Elides:` line. The one that is still incomplete rather than merely stated is the
sibling-module boundary: nothing in the rendered document distinguishes it from a
third-party one. `Reaches` (W30) does not close it either — both read `unresolved` unless a
catalog names the type, and no catalog names a sibling module — so the section says so in
prose and leaves the full descriptor in the `Call` column for a reader to judge.

**What the rendered section does NOT do, measured the same way.** No step is filtered — all
2,147 of `mall-admin`'s steps are rows, and all of them are arrows — so a reader never has
to wonder whether a call was hidden. No `alt`/`opt`/`loop` structure is drawn, because
`call_site.ordinal` is instruction order and nothing more ([D00](components/D00-fact-schema.md)
§5's "v1 of the control-flow position"); the diagram is flat and says so. And no trace is
named by a wire identity: a root is a handler, `roots` collapsed 160 endpoints to 160
handlers here and 77 to 66 on the fixture, and the endpoint tables above are where a path
meets its handler.

### Where a value chain stops, now that it crosses method boundaries

2Q's `G3` links a callee's returned value to the caller's own `result` id
(`return_flows`, [D01](components/D01-graph-schema.md) §3), so a chain no longer ends at the
first call. It still ends, and these are the places — each measured on `macrozheng/mall`'s
`mall-admin` (160 endpoints, Boot 3.x, JDK 21) rather than reasoned about.

| Where it stops | Measured on `mall-admin` | Why, and what closes it |
|---|---|---|
| **The third party.** A mapper, a repository, a driver, the JDK: the call IS the terminal | **1,411 of 2,065** value-producing call sites | Ruled, not a gap. We do not trace into a dependency and we do not read MyBatis XML, so a terminal is `OmsOrderMapper#selectByExample` and never a table name |
| **A declaration this workspace never scanned**, even where the module overrides it — `AdminUserDetails#getPassword` against Spring Security's `UserDetails` | **3 of 2,065**, every one a genuine in-module override | Deliberate, and the conservative side of a rule with one corpus behind it. Widening it would let a call on `java/lang/Object#toString()` list every `toString` the module declares — reachable, honest, and useless. **Closes by** a second corpus measuring that blast radius. **OI-17** |
| **Values through library code.** `stream().map(f).collect()` leaves for the JDK and comes back | not counted | The `collect` result is visible; per-element provenance is not |
| **Values parked in a field** between calls | not counted | `field_write` is constructors-only by design |
| **Several returns, several implementations** — a set, never a pick | 62 fixture methods with more than one return; **0** calls on `mall-admin` with more than one implementation | Not a stop at all: the set is carried and the site says `narrowed`. But the several-implementations rule has still **never run on real code** — the roadmap recorded zero and `G3` measured zero again — so it ships exercised by a fixture only |

**Responses built by mutation are attributable and get no row of their own.** Where a method
writes `result.setFilename(x); return result;`, the returned value entry carries the id of
the value that was mutated, and every setter that wrote into it is a `call_site` in the SAME
method whose `receiver` is that id. That is a within-method join over facts that already
exist — 17 of `mall-admin`'s 1,014 returns are built this way, all reachable by it — and
`return_flows` exists for the step BETWEEN methods. Adding a second, redundant spelling of a
within-method fact would put one claim in two places. **This was the one boundary the
roadmap left open; the decision is recorded here rather than in a commit message.**

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

### A catalog's measured version is recorded and never compared to the module's

**BOUNDARY, stated 2026-09-06 with F5** ([D02](components/D02-catalog-schema.md) §1a;
`docs/open-issues.md` OI-10, OI-11). A catalog now declares the artifact(s) and version(s)
its rule was verified against. **How many do is not restated here**: [§3a](#3a-what-we-support-and-at-which-versions)'s
generated block carries the count and names every catalog on each side of it, and a test
regenerates it from the catalogs themselves — so it cannot go stale, where this paragraph
did. It read "twenty-nine of the fifty-five" and "twenty-six declare no measured version"
long after both numbers had moved (`G-27`, corrected in W53 by deleting the numbers rather
than by refreshing them).

**Nothing compares a catalog's measured version against the version the analysed module
resolves**, and a catalog with no `measured:` block at all has had no committed probe open
its framework's jar.

So a run says nothing about whether the rules that produced it were ever measured on the
framework generation the module actually builds against. The shape this hides is a rule
that MOVED: `WebClient$RequestHeadersSpec.exchange` is declared by `spring-webclient.yml`,
exists at spring-webflux 6.1.6 and is **removed** at 7.0.2 (CP-12), so on a Framework 7
module its rows are simply absent — indistinguishable from a call site nobody wrote. A
version-aware verdict is Stage 6 work and needs a version ordering §7's dependency rule
forbids importing; `docs/open-issues.md` OI-11 lists what it would take.

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
the rest. **All three now ship** — 3.x on `spring-sqs.yml`, the two older spellings on
`spring-sqs-legacy.yml`, kept a separate file because each generation carries its own
dependency coordinate and `detect.coordinates` names the module a catalog's rule applies to.

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
