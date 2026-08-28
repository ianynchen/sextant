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
| ✅ | Shipped and verified against a real project |
| ◐ | Partly shipped — known gaps in the same cell |
| **A** / **B** / **C** | Not built; tier is the cost of the mainstream library |
| — | Not applicable — the protocol does not exist in that ecosystem |
| ⛔ | Blocked by the language toolchain, not by our effort |
| † | The cell hides a significantly worse case; see §5 |

`—` and `⛔` are deliberately distinct from a gap. JMS in Go is not missing work.

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
identical and the **return type** decides. This generalises a gap already recorded for
`@HttpExchange`, where the *direction* depends on use rather than on the catalog: **both
`protocol` and `direction` are currently properties of the catalog, and both need to be
derivable per match.** See §8.

### Verification

Researched against primary sources, August 2026. Anything marked ⚠️ was **not** confirmed
and must be checked before entering a catalog — a wrong annotation name does not fail
loudly, it silently matches nothing.

---
## 2. The matrices

Rows are languages. **Scanner** is the prerequisite: without it, nothing else in the row is
reachable regardless of tier. Split in two because the address shapes differ (§1) and one
eleven-column table is unreadable.

### 2a. Application protocols over HTTP

| Language | Scanner | REST in | REST out | SOAP | GraphQL | WebSocket | SSE |
|---|---|---|---|---|---|---|---|
| **Java / Kotlin** | ✅ | ◐ † | A † | A | A | A † | **B** |
| **Go** | — | A | A | — | A | B | **C** |
| **TypeScript** | — | A † | A | — | A | A | B |
| **JavaScript** | — | A † | A | — | A | A | B |
| **Python** | — | A † | A | B | A | A | B |
| **Rust** | — | A † | B | — | A | A | B |
| **Swift** | — | — † | A † | — | A † | B | — |

### 2b. Messaging and RPC

| Language | gRPC | Kafka | JMS / AMQP | SQS | Pub/Sub | Async |
|---|---|---|---|---|---|---|
| **Java / Kotlin** | B | A † | A | A | B | A |
| **Go** | A | A | — † | A | B | A |
| **TypeScript** | B † | A | — | A | B | A |
| **JavaScript** | B † | A | — | A | B | A |
| **Python** | A | A | — † | **C** † | B | A |
| **Rust** | A | A | — † | B | ⚠️ | B |
| **Swift** | A | — | — | — | — | B |

Payload formats are a **separate axis** — see §4. They are orthogonal to both tables
(Avro-over-Kafka, Protobuf-over-gRPC, Protobuf-over-Kafka, JSON-over-REST are all real) and
almost entirely language-independent.

### Reading the matrices

**SSE is the worst column in either table, and it is the only one that is worse in every
language than the protocol it rides on.** Nothing declares it. It is detected from a return
type (`SseEmitter`, `Flux<ServerSentEvent>`, axum `Sse<S>`, `EventSourceResponse`) or, in Go
and Express, from a bare `Content-Type: text/event-stream` header string. There is no
annotation anywhere.

**GraphQL is far better than expected — A almost everywhere.** Every ecosystem either
declares operations with annotations (Spring `@QueryMapping`, NestJS `@Query`, Strawberry
`@strawberry.field`, async-graphql `#[Object]`) or ships an SDL schema file that *is* the
contract. Both are readable. GraphQL is the cheapest new protocol on this page.

**The JVM is the outlier on gRPC.** Everywhere else the generated code *names the service in
a call* — Go's `pb.RegisterFooServer(s, impl)`, Python's `add_FooServicer_to_server`, Rust's
`FooServer::new`. Only the JVM uses inheritance (`extends FooGrpc.FooImplBase`). That is why
gRPC is B for us and A for everyone else.

**`registration_call` is to the non-JVM languages what `fluent_chain` is to the JVM** — one
capability that unlocks most cells at once. It is the baseline for four of the seven rows.

**Pub/Sub is B in every language.** Only Micronaut ships a first-party annotation; everywhere
else it is a builder chain over a client library.

**The `†` clusters worth knowing before reading §5.** Java REST-in hides
`@RequestMapping(method=…)`, which yields zero endpoints today. TypeScript REST-in hides
Next.js filesystem routing, which no engine we have designed can express. Python SQS is C
because `boto3` has no static form at all. Java WebSocket is A for `@ServerEndpoint` and
`@MessageMapping` but B for programmatic `addHandler` registration.

## 3. Language readiness — the gate on every row

| Language | Compiler-grade fact source | Types | Build needed | Call graph | Baseline engines |
|---|---|---|---|---|---|
| **Java / Kotlin** | JVM bytecode via **ASM** ✅ | Full | Yes | We write it | `annotation` ✅ |
| **Go** | **`go/packages`** + `go/ssa` | Full | No (deps only) | ✅ **`callgraph/{cha,rta,vta}` ships with the toolchain** | `registration_call` |
| **TypeScript** | **`ts.TypeChecker`** compiler API | Full where annotated | No | `Jelly` ✅ | `registration_call` + `annotation` + `filesystem` |
| **Swift** | **IndexStoreDB** (index-while-building) ✅ | Full | Yes (macOS) | Index carries call relations | `registration_call` |
| **Python** | None — pyright has **no programmatic API**, only LSP ⚠️ | Sparse (§7) | No | `PyCG` | `annotation` + `registration_call` |
| **Rust** | None stable — `syn` has no types; rustdoc JSON unstable ⚠️ | Syntax only | — | None | `annotation` (syntax-only) |
| **JavaScript** | None | None | No | `Jelly`, degraded | as TypeScript, payloads ⛔ |

**Three findings worth stating outright.**

**Go ships the analysis we deferred.** `golang.org/x/tools/go/callgraph` provides `static`,
`cha`, `rta` and `vta` as maintained library code ✅, and `cha` is documented sound on
partial programs — libraries with no `main`, which is our situation exactly. For the JVM we
planned to write class hierarchy analysis and defer variable type analysis. **Go's dispatch
resolution starts ahead of the JVM's.**

**Swift is not the hard case people assume.** `swiftc` emits index data as a side effect of
compilation; `IndexStoreDB` reads it into a queryable store of symbols, occurrences and
relations ✅ — the same data `sourcekit-lsp` uses for call hierarchy. It needs a build,
which fits DR-4 precisely. Periphery already works this way.

**For TypeScript the JVM rule inverts.** We scan compiled output on the JVM because bytecode
is richer than source. In TypeScript it is strictly poorer — types erased, decorators
lowered to `__decorate` calls, bundlers renaming and inlining. **Scan TypeScript source**,
with `tsconfig.json` as the build input carrying authority under DR-4.

Per-language essays — toolchain detail, payload handling, structural oddities:
[Go](coverage/go.md) · [Rust](coverage/rust.md) · [Python](coverage/python.md) ·
[TypeScript and JavaScript](coverage/typescript.md) · [Android and iOS](coverage/mobile.md).

---

## 4. Payload formats — the orthogonal axis

Avro and Protobuf are **not protocols**; they are serialization formats that ride on the
protocols in §2. Treating them as columns would create meaningless cells ("Avro in Go" — over
what transport?) and hide the ones that matter ("Avro-over-Kafka subject naming").

They are also **almost entirely language-independent**, which is a genuine simplification:
generated code carries the schema in every language, always as `generated_descriptor`.

| Format | Where the schema lives | Shape | Tier | Note |
|---|---|---|---|---|
| **Protobuf** | Generated code embeds the serialized `FileDescriptorProto` — JVM `getDescriptor()`, Go `.pb.go` raw descriptor ⚠️, Python `_pb2.py` `DESCRIPTOR`, Rust `prost` field attributes, Swift generated structs | `generated_descriptor` | **B** | **The whole `.proto` is recoverable from compiled output.** Field numbers are the strongest join key of any protocol — both sides derive from one schema, so numbers must agree (DR-5). |
| **Avro** | Generated JVM classes extend `org.apache.avro.specific.SpecificRecordBase` with `public static final Schema SCHEMA$` | `generated_descriptor` | **B** | Same trick as protobuf. Confluent subject naming: `<topic>-key` / `<topic>-value` under the default `TopicNameStrategy`. |
| **JSON** | Jackson/`serde`/Pydantic/`Codable`/struct tags — the type declaration *is* the schema | `annotation` / type read | ◐ | Shipped as type references, not expanded fields. Optionality is what needs nullability annotations (§7). |
| **JSON Schema** | Fastify route options, `zod`, OpenAPI components | literal / `fluent_chain` | B | Already in the shape we want |
| **XML / XSD** | WSDL and XSD documents | artifact | C | Deferred with SOAP |

**Two version traps.** JVM protobuf generated classes extend `GeneratedMessageV3`
(protobuf-java 3.x) **or `GeneratedMessage`** (4.26+, with `V3` deprecated and slated for
removal in 5.x ✅). Both must be matched. And Confluent's serializer FQNs ⚠️ are unconfirmed.

---

## 5. The checklist, by protocol

The work list. Each row is one library in one language: what it looks like, what shape it
is, what it costs.

### 5.1 REST inbound

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@RestController` / `@Controller` + `@GetMapping` etc. | annotation on class + method | `annotation` | ✅ shipped |
| Java | **`@RequestMapping(method = RequestMethod.GET)`** | the pre-4.3 form | `annotation` | **A — biggest single gap; yields zero endpoints today** |
| Java | `path =` alias for `value =` | — | `annotation` | **A — currently produces an *empty path*, wrong output not missing output** |
| Java | `produces` / `consumes` | — | `annotation` | A |
| Java | Spring 7 `version = "1.1"` / `"1.2+"` on `@RequestMapping` ✅ | API versioning | `annotation` | A |
| Java | Micronaut `@Controller` + `@Get`/`@Post`… (`value`/`uri` String, **`uris` String[]**) | — | `annotation` | A |
| Java | Quarkus / JAX-RS **`jakarta.ws.rs`** `@Path` + `@GET`… | `@Path` value is a scalar String | `annotation` | A |
| Java | Quarkus `io.quarkus.vertx.web.Route` | second Quarkus style | `annotation` | A |
| Java | Actuator `@Endpoint` / `@ReadOperation` | — | `annotation` | A |
| Java | `@RequestMapping` on an **interface or superclass** | Spring inherits mappings | `annotation` + hierarchy | B |
| Java | **Meta-annotations** — custom `@ApiGet` composed from `@GetMapping` | Spring resolves transitively | `annotation` (recursive) | B |
| Java | Nested / inner classes | currently skipped **and reported** | — | B |
| Java | WebFlux `Mono`/`Flux` return types | endpoint found, response type is the wrapper | — | B (unwrapping, [D02](components/D02-catalog-schema.md) §2a) |
| Java | **Vert.x** `router.get("/x").handler(this::h)` ✅ | receiver + verb + first arg | `fluent_chain` | **B — the cleanest first exercise for chain reconstruction** |
| Java | WebFlux functional `RouterFunctions.route().GET(…)`, `coRouter { }` | — | `combinator` | B |
| Java | **Akka HTTP** `path("users" / IntNumber) { get { complete(…) } }` | nested closures, route is a *value* | `combinator` | **C-ish — the hardest inbound form surveyed** |
| Java | Ktor `routing { get("/path") { … } }` | Kotlin DSL | `combinator` | B |
| Java | Javalin `app.get("/path", ctx -> …)` | — | `registration_call` | B |
| Java | **Spring Data REST** `@RepositoryRestResource` | a repository interface becomes a CRUD API | — | **C — no controller, no mapping annotation** |
| Java | `@ControllerAdvice` + `@ExceptionHandler` | defines the error contract of every endpoint | — | C |
| Java | Servlets, filters, interceptors, built-in Actuator endpoints | `@WebServlet`, `FilterRegistrationBean`, dependency + property | — | C |
| Java | `@ConditionalOnProperty` / `@Profile` controllers | exists in one environment only | — | C |
| Go | `net/http` 1.22+ `mux.HandleFunc("GET /items/{id}", h)` ✅ | **verb and path in one literal** | `registration_call` | A |
| Go | `gin`, `echo`, `chi`, `fiber` | `r.GET("/p", h)`, groups nest a prefix | `registration_call` | A |
| Go | `gorilla/mux` `r.HandleFunc(p, h).Methods("GET")` | verb is a sibling call | `fluent_chain` | B |
| Go | `net/http` pre-1.22 | verb is an `if r.Method` inside the handler | `runtime_dynamic` | C |
| TS | **NestJS** `@Controller("users")` + `@Get(":id")` + `@Body() dto` | **structurally identical to Spring MVC** | `annotation` | **A — highest-value non-JVM target** |
| TS | Express, Koa, Hapi, Hono | `app.get("/p", h)`, mounted via `app.use("/api", r)` | `registration_call` | A |
| TS | Fastify `fastify.get(p, { schema }, h)` | **options object carries a JSON Schema** | `registration_call` | A |
| TS | **Next.js / SvelteKit / Remix / Nuxt** | **path is the file path, verb is the exported symbol name** | `filesystem` | **C — no engine we have designed can express this** |
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

**Nothing is supported anywhere.** Phase 1 records no call sites at all, so the system tier
has nothing to match on.

| Language | Library | Shape | Tier |
|---|---|---|---|
| Java | Feign `@FeignClient`, Retrofit `@GET`, Spring `@HttpExchange`, Micronaut `@Client`, MicroProfile `@RegisterRestClient` | `annotation` | A |
| Java | Spring 7 `ImportHttpServices` registration ✅ | `annotation` | A |
| Java | `RestTemplate` | `registration_call` | A |
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
| Java | Netflix DGS `@DgsComponent` + `@DgsQuery` / `@DgsData` ⚠️ | code-first | `annotation` | A |
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
| Java | JSR-356 `jakarta.websocket.server.ServerEndpoint("/ws")` ⚠️ | annotation on the class | `annotation` | A |
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
| Java | Spring MVC — returns `org.springframework.web.servlet.mvc.method.annotation.SseEmitter` ⚠️ | **return type** | return-type read | B |
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
| Java | official `org.springframework.grpc` starter ⚠️ | names unconfirmed | `annotation` | A |
| Go | `pb.RegisterFooServer(s, impl)`, `pb.NewFooClient(conn)` | **the generated function names the service** | `registration_call` | A |
| Python | `_pb2_grpc.py`: `FooServicer`, `add_FooServicer_to_server`, `FooStub(channel)` | — | `registration_call` | A |
| Rust | `tonic` `FooServer::new(impl)`, `FooClient::connect(url)` | — | `registration_call` | A |
| TS | `@grpc/grpc-js` + `@grpc/proto-loader` `loadSync("foo.proto")` | **service built at runtime from a `.proto` path** | `runtime_dynamic` | **B — the path is a literal, so read the `.proto` as an artifact** |
| TS | `ts-proto`, `protobufjs` static mode | generated typed services | `generated_descriptor` | A |
| Swift | gRPC-Swift generated clients and providers; Connect-Swift | — | `registration_call` | A |

### 5.8 Kafka

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@KafkaListener` (`topics`, `topicPattern`, `topicPartitions`, `groupId`) | — | `annotation` | A |
| Java | Micronaut `@KafkaListener`/`@KafkaClient` + `@Topic` | — | `annotation` | A |
| Java | `KafkaTemplate.send(topic, …)` | — | `registration_call` | A |
| Java | `KafkaConsumer.subscribe(Collection<String>` \| `Pattern)` | — | `registration_call` | A |
| Java | **`KafkaProducer.send(ProducerRecord)`** | **topic is a constructor argument of `ProducerRecord`**, not of `send` | `fluent_chain` | B |
| Java | `KafkaTemplate.send(Message)` with topic in a header | — | `fluent_chain` | B |
| Java | **Spring Cloud Stream** functional `Consumer<T>`/`Supplier<T>` beans | topic in `spring.cloud.stream.bindings.<bean>-in-0.destination` | `config_join` | **C — see §7** |
| Java | **SmallRye** `@Incoming("orders")` / `@Outgoing` | channel in code, topic in `application.properties` | `config_join` | **C** |
| Java | Alpakka / Pekko Connectors `Consumer.plainSource(s, Subscriptions.topics("t"))` | — | `registration_call` | B |
| Go | `segmentio/kafka-go` `kafka.NewReader(kafka.ReaderConfig{Topic: "t"})` | **topic is a struct-literal field** — easier than positional | `registration_call` | A |
| Go | `IBM/sarama` ⚠️ (was `Shopify/sarama`), `confluent-kafka-go` | — | `registration_call` | A |
| TS | `kafkajs` `consumer.subscribe({topic})`, `producer.send({topic, messages})` | topic in an object literal | `registration_call` | A |
| Python | `confluent-kafka`, `kafka-python` `KafkaConsumer("topic", …)` | **topic is a constructor argument** | `registration_call` | A |
| Python | `faust-streaming` `app.topic("orders")` + `@app.agent(topic)` | — | `annotation` + `registration_call` | A |
| Rust | `rdkafka` `consumer.subscribe(&["topic"])`, `FutureRecord::to("topic")` | — | `registration_call` | A |

⚠️ `KafkaTemplate.send` returns `ListenableFuture` in older Spring Kafka, `CompletableFuture` in current.

### 5.9 JMS and AMQP

JMS is a **Java specification**. The other languages have no equivalent — the `—` in §2 is
structural, not a gap. AMQP is the cross-language analogue and is listed here.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring `@JmsListener` (`destination`, `selector`, `subscription`, `concurrency`) | — | `annotation` | A |
| Java | Micronaut `@JMSListener` + `@Queue`/`@Topic` | — | `annotation` | A |
| Java | `JmsTemplate.send` / `convertAndSend` | — | `registration_call` | A |
| Java | Direct `jakarta.jms.{Session, MessageProducer, MessageConsumer}` | — | `fluent_chain` | B |
| Java | `@RabbitListener`, `@PulsarListener` | — | `annotation` | A |
| Go | `rabbitmq/amqp091-go` ⚠️ (was `streadway/amqp`) `ch.Publish(exchange, key, …)` | — | `registration_call` | A |
| Python | `pika`, `kombu` `channel.basic_publish(exchange, routing_key, …)` | — | `registration_call` | A |
| Rust | `lapin` `channel.basic_publish(…)` | — | `registration_call` | A |

**Package change:** `javax.jms` (Spring ≤5 / Boot ≤2) → `jakarta.jms` (Spring 6 / Boot 3+).
Both must be matched.

### 5.10 AWS SQS

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | Spring Cloud AWS 3.x `io.awspring.cloud.sqs.annotation.SqsListener`, `SqsTemplate` | — | `annotation` | A |
| Java | Spring Cloud AWS 2.x `io.awspring.cloud.messaging.listener.annotation.SqsListener` ⚠️ | **different package** | `annotation` | A |
| Java | AWS SDK v2 `SqsClient.sendMessage(SendMessageRequest)`, `…builder().queueUrl(u)` | — | `fluent_chain` | B |
| Go | `aws-sdk-go-v2` `client.SendMessage(ctx, &sqs.SendMessageInput{QueueUrl: …})` | struct literal | `registration_call` | A |
| TS | `@aws-sdk/client-sqs` v3 `client.send(new SendMessageCommand({QueueUrl}))` | **command classes are real, statically visible types** | `registration_call` | A |
| **Python** | **`boto3`** `boto3.client("sqs").send_message(QueueUrl=…)` | **clients synthesised at runtime from JSON service models — `send_message` is defined in no Python file** | `runtime_dynamic` | **C — ceiling is a `name_match` on the service string; `resolution: narrowed` at best** |
| Rust | `aws-sdk-rust` `client.send_message().queue_url(u).send()` | — | `fluent_chain` | B |
| Java | Micronaut | **no first-party annotations** — raw SDK or `micronaut-jms-sqs` | — | B |

### 5.11 Google Cloud Pub/Sub

The hardest protocol in the table: **B in every language**, because only Micronaut ships a
first-party annotation.

| Language | Library | Form | Shape | Tier |
|---|---|---|---|---|
| Java | **Micronaut `@PubSubClient` / `@PubSubListener` + `@Subscription`** | the only first-party annotation surveyed | `annotation` | A |
| Java | `Publisher.newBuilder(TopicName.of(p, t)).build()`, `.publish(…)` | — | `fluent_chain` | B |
| Java | `Subscriber` + `MessageReceiver`, `.startAsync()` | — | `interface_implementation` | B |
| Java | Spring Cloud GCP `PubSubTemplate.subscribe(…)`, or `PubSubInboundChannelAdapter` + `@ServiceActivator` | channel indirection | `config_join` | C |
| Go | `client.Topic("n").Publish(ctx, m)`, `client.Subscription("s").Receive(ctx, fn)` | — | `fluent_chain` | B |
| TS | `pubsub.topic("n").publishMessage(…)`, `subscription.on("message", cb)` | — | `fluent_chain` | B |
| Python | `publisher.publish(topic_path, data)`, path built by `publisher.topic_path(proj, t)` | topic assembled from a helper call | `fluent_chain` | B |
| Rust | `google-cloud-rust` ⚠️ | maturity unconfirmed | — | ⚠️ |

⚠️ Spring Cloud GCP packages moved `org.springframework.cloud.gcp.*` → `com.google.cloud.spring.*`; version of the rename unconfirmed.

### 5.12 Async and internal boundaries

Not protocols, but genuine entry points that would otherwise fall out of the checklist.

| Language | Mechanism | Shape | Tier |
|---|---|---|---|
| Java | `@Scheduled`, Quartz | `annotation` | A |
| Java | Temporal / Cadence `@WorkflowInterface`, `@ActivityInterface` | `annotation` | A |
| Java | **Vert.x event bus** `vertx.eventBus().send("addr", m)` / `.consumer("addr", h)` | in-process pub/sub with **string addresses**, matchable like topics | `registration_call` | B |
| Java | Spring Integration `@ServiceActivator`, `@InboundChannelAdapter` | channels, not destinations | `config_join` | C |
| Java | **Akka / Pekko actor messaging** `ref ! msg`, `ref.tell(msg)` | receiver comes from an `ActorRef` created elsewhere | — | **C, possibly permanent — see §7** |
| Python | **Celery** `@app.task`, `task.delay(…)`, `.apply_async(queue=…)` | a real async boundary, easy to miss | `annotation` | A |
| TS | `bullmq` `new Queue("n")`, `new Worker("n", fn)` | string names, matchable like topics | `registration_call` | A |
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
| iOS | App Intents / Siri ⚠️ | `AppIntent` conformances | `interface_implementation` | B |
| iOS | Push, share extensions, background tasks | delegate methods, `NSExtension` keys, `BGTaskScheduler` ids | mixed | B |

✅ **Android needs no new scanner.** The build emits ordinary JVM `.class` intermediates
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

✅ Lightbend moved Akka to the Business Source License from 2.7; **Apache Pekko** is the
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

**"Python is typed now" is false at our granularity.** ⚠️ A 2026 study found **91% of
libraries contain at least one type hint, but half cover only 13.6% of their members**;
among systematic users, median coverage is 45.8% of parameters and 35.9% of returns.

**Benchmark evidence sets the LLM boundary.** ⚠️ An empirical study of 24 LLMs (arXiv
2410.00603) against TypeEvalPy and SWARM-CG/SWARM-JS found that **traditional static
analysis consistently beat every model on call graphs** (`PyCG` for Python, `Jelly` for
JavaScript — models "struggle with completeness and soundness"), while **LLMs clearly beat
static tools on Python type inference** (surpassing `HeaderGen` and `HiTyper`). This maps
onto machinery we already have:

| Task | Method | `evidence` | `precedence` |
|---|---|---|---|
| Call edges, dispatch, reachability | Static analysis | `syntax` / `compiler` | 50 |
| Payload fields, types, optionality | LLM, where declarations are absent | `llm` | 10 |

**The operating rule: an LLM may propose a shape; it may never propose an edge.** An
invented field is a visible, checkable error a human overlay corrects at precedence 90. An
invented call edge silently corrupts blast radius — the thing the tool exists to compute —
and nothing downstream would catch it.

`PyCG`, `Jelly`, `TypeEvalPy` and `SWARM-CG` also give us **published benchmarks to measure
our own output against**, rather than asserting quality.

### JSpecify lands in an attribute we do not read

✅ Spring 7 adopts JSpecify (`org.jspecify.annotations.*`), which is `TYPE_USE` with
`RUNTIME` retention — so it lands in `RuntimeVisibleTypeAnnotations`.
[M03](components/M03-scanner.md) names the **Invisible** attribute, and the scanner does not
override `visitTypeAnnotation` at all, so neither is read. Nullability sets `required` on
contract fields, so this gates honest shape comparison. `org.springframework.lang.Nullable`
is deprecated but still present in compiled code — **match both FQNs**.

---

## 8. Open questions

Recommendations included. Items marked **needs a decision** change how the table is built.

**Q1 — Is a tier relative to the JVM's engine or to each language's baseline? needs a decision.**
Recommend **per-language baseline** (§1). Measured against the JVM, every non-JVM cell is B
and the column carries no information. Measured against each language's baseline, `gin` is A
and Go's Pub/Sub is B — which is the distinction we actually want when planning work.

**Q2 — Do Avro and Protobuf belong on the protocol axis? needs a decision.**
Recommend **no** — a separate format axis (§4). They ride *on* the protocols, so cells like
"Avro in Go" have no meaning without naming a transport, while the fact that matters —
Avro-over-Kafka subject naming — has nowhere to live. They are also nearly
language-independent, which is a simplification worth capturing rather than spreading across
seven rows.

**Q3 — HTTP versus REST as separate columns? resolved.**
Neither. **HTTP is a transport; the axis is the application protocol running on it** — REST,
SOAP, GraphQL, WebSocket, SSE, gRPC (§1). That distinction is load-bearing rather than
cosmetic: four of those protocols put **one HTTP path in front of many logical operations**,
so a model that stopped at the HTTP route would report "1 endpoint" for a service exposing
200 GraphQL fields. Direction still earns two columns for REST, where the tiers genuinely
diverge.

**Q4 — Does "pubsub" mean the GCP product or the publish-subscribe pattern?**
Read as **the GCP product**, since Kafka and JMS already have columns. Publish-subscribe as a
pattern is a property of an endpoint, not a column — otherwise Kafka, JMS topics, SNS and
Redis all belong in it too.

**Q5 — Is direction a third dimension?**
Recommend **no**, except for HTTP. For Kafka, JMS, SQS and Pub/Sub, producer and consumer sit
in the same library and usually the same tier, so direction belongs in the library row. For
HTTP the tiers genuinely diverge, so it earns two columns.

**Q6 — What does a cell mean when it holds several libraries at different tiers?**
The cell shows the tier of the **mainstream** library and carries `†` when it hides a
significantly worse case. §5 is the real checklist; §2 is navigation. Collapsing Kafka-in-Java
to a single tier would hide that Spring Cloud Stream is C.

**Q7 — How do we stop this document drifting from reality? my strongest suggestion.**
Catalogs are already YAML, and the design already has capability gating — scanners declare
capabilities, catalogs declare requirements, unmet requirements are skipped *and reported*.
So the matrix could be **generated**: add a small registry of `(language, protocol, library,
shape, status)` records, derive the tier mechanically from `shape` against the capabilities a
scanner declares, and have `sextant` render §2 and §5. Coverage then cannot drift, "what
needs adding" becomes a query rather than a document, and it follows the project's own rule
that frameworks are data. Recommend doing this once a second language exists — before that
the registry costs more than it saves.

**Q8 — Do the per-language files now duplicate §5?**
Partly, and deliberately: §5 owns the **judgment** (tier, status) and the language files own
the **essay** (toolchain verdict, payload handling, structural oddities such as Django's
`urls.py`, Next.js filesystem routing, `boto3`). No fact carries a tier in two places. If Q7
lands, §5 becomes generated and the essays stay hand-written.

**Q9 — Can `protocol` stay a property of the catalog? needs a decision. New — surfaced by adding SSE.**
**No.** A Spring `@GetMapping` returning `List<Order>` is REST; the identical annotation
returning `SseEmitter` or `Flux<ServerSentEvent<T>>` is SSE. The declaration does not
distinguish them — the **return type** does. This is the same shape as the `@HttpExchange`
problem, where *direction* depends on use rather than on the catalog. Recommend treating both
`protocol` and `direction` as **per-match, with a catalog-level default**: a catalog declares
what it usually produces, and a rule may override it from the match. That is a smaller change
than it sounds and it closes two gaps at once.

### Still-open design questions, unchanged by this reorganisation

Four shapes the schema cannot express today. All four surfaced from the research, none is an
organisational problem:

1. **Context-dependent `direction` and `protocol`.** `@HttpExchange` is inbound or outbound
   depending on use; `@GetMapping` is REST or SSE depending on its return type. Both are
   catalog properties today and both need to be per-match (Q9).
2. **Config-derived destinations** (§7) — no catalog style says "the destination is a
   property key derived from this bean's name".
3. **Filesystem-derived paths** — Next.js, SvelteKit, Remix and Nuxt put the route in the
   file's location and the verb in an export name. No engine we have designed reads a
   directory walk as a fact source.
5. **One route, many operations** — GraphQL, SOAP, WebSocket and SSE need the *operation* to
   be the boundary, not the HTTP route ([D01](components/D01-graph-schema.md)).
4. **Per-endpoint `resolution` driven by framework typing** (§7) rather than by language.

Two limits should be stated **in the product**, not discovered by users: actor messaging is
largely invisible to static analysis, and `runtime_dynamic` boundaries — `boto3`, DRF
routers, `@grpc/proto-loader` — are not gaps we will close later. They are boundaries that do
not exist statically, and the coverage report has to say so.

---

## 9. Verification status

Researched August 2026 against primary sources — Spring, Micronaut, Quarkus, Apache Kafka,
AWS, Google Cloud, gRPC, Avro, Protocol Buffers, Apache Pekko, Vert.x, the Go and Swift
toolchains, and the academic literature on LLM-assisted static analysis. Items marked ⚠️ rest
on secondary sources or could not be confirmed, and **must be checked against the library's
own documentation or source before entering a catalog**. A wrong annotation name does not
fail loudly; it silently matches nothing, which is exactly how petclinic returned zero
endpoints.
