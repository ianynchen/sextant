# COVERAGE

What Sextant can detect, and what it cannot. Delivery status is in [PROJECT.md](PROJECT.md);
this document is about *reach* — which real-world ways of declaring a boundary we can
actually see. It is the completeness checklist for future implementation.

Written after running Phase 1 against a real project ([spring-petclinic](https://github.com/spring-projects/spring-petclinic)),
which found **zero endpoints on the first attempt** because the catalog matched
`@RestController` and petclinic uses `@Controller`. That failure is why this document
exists: coverage gaps are invisible until something real is pointed at the tool.

| | |
|---|---|
| §1–§8 | The JVM — the MVP languages, in detail |
| §9 | [Go](coverage/go.md) · [Rust](coverage/rust.md) · [Python](coverage/python.md) · [TypeScript and JavaScript](coverage/typescript.md) · [Android and iOS](coverage/mobile.md) |
| §10 | Why Python and JavaScript are the hard cases, and what to do about it |
| §11–§12 | What all of it implies |

---

## 1. How to read this

### Detection shapes

Every boundary in every language and framework surveyed here falls into one of eight
shapes. **The shape predicts the cost far better than the language or the protocol does**,
so this is the vocabulary the rest of the document uses. Ordered cheapest first.

| Shape | The facts live in | Example |
|---|---|---|
| `annotation` | A declaration | `@GetMapping("/x")`, NestJS `@Get()`, Retrofit `@GET`, FastAPI `@app.get` |
| `registration_call` | One call's literal arguments | `app.get("/x", h)`, `mux.HandleFunc("GET /x", h)`, `pb.RegisterFooServer(s, impl)` |
| `generated_descriptor` | Schema embedded in generated code | protobuf descriptors, Avro `SCHEMA$` |
| `interface_implementation` | A type's supertype | gRPC `FooImplBase`, `MessageReceiver` |
| `fluent_chain` | Spread across a builder chain | `WebClient`, `RestClient`, AWS SDK, Vert.x |
| `filesystem` | The file's path on disk | Next.js `app/api/users/[id]/route.ts` |
| `config_join` | Code names a key; the value is in configuration | Spring Cloud Stream, SmallRye, MicroProfile REST Client |
| `runtime_dynamic` | Constructed at runtime; **no static form exists** | `boto3` clients, DRF routers, `@grpc/proto-loader` |

`runtime_dynamic` is the only one where the honest answer is that we cannot see it. The
other seven are engineering.

### Tiers

Within the JVM, where a scanner already exists, gaps are tiered by cost:

| Tier | Means | Cost |
|---|---|---|
| **A** | A catalog entry away. Fits an engine that already exists. | One YAML file and a fixture. **No code.** |
| **B** | Needs a scanner capability we have not built. | Real work in the extractor, then a catalog. |
| **C** | The boundary is not in the code at all. | New modelling. |

Tier A is large and cheap. Tier B is gated almost entirely on one capability
(`fluent_chain` reconstruction). Tier C is where the interesting design problems are.

### Verification

Facts were researched against primary sources in August 2026. Anything marked ⚠️ was not
confirmed and **must be verified before being written into a catalog** — a wrong
annotation name does not fail loudly, it silently matches nothing.

---

## 2. Supported today

Java and Kotlin, from compiled bytecode, via ASM. Two catalogs, both `annotation`-shaped,
both inbound HTTP only.

| Catalog | Type annotation | Method annotations | Path prefix |
|---|---|---|---|
| `spring-web` | `@RestController` | `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping` | class-level `@RequestMapping`, `value` only |
| `spring-mvc` | `@Controller` | same | same |

Paths come from the `value` attribute, first array element, with a scalar fallback.
Endpoints carry request and response **type references**, not expanded field lists.

**Two scanner capabilities are implemented** of eight designed: `annotation_args` and
`typed_signatures`. Anything needing one of the other six is Tier B by definition.

**Nothing outbound exists.** No call sites are recorded at all, so the system tier has
nothing to match on.

---

## 3. Gaps inside Spring MVC — the framework we claim to support

The highest-value gaps in the project, because they affect codebases we would otherwise
report on confidently.

| Gap | Tier | Note |
|---|---|---|
| **`@RequestMapping(method = RequestMethod.GET)`** | **A** | The original Spring form, ubiquitous in code written before 4.3. We treat `@RequestMapping` **only** as a prefix, so such a controller yields **zero endpoints** — the petclinic failure in a different disguise. **The single biggest gap.** |
| `@RequestMapping` with no `method` | A | Matches every verb. Invisible today. |
| `path =` as an alias for `value =` | A | Spring treats them identically. We read `value` only, so `@GetMapping(path="/x")` produces an **empty path** — wrong output, not missing output. |
| `produces` / `consumes` | A | Part of the wire contract; ignored entirely. |
| `@RequestMapping` on an interface or superclass | B | Spring inherits mappings; we read only a class's own annotations. Common with `interface FooApi` + `class FooController implements FooApi`. |
| **Meta-annotations** — custom `@ApiGet` composed from `@GetMapping` | B | Spring resolves these transitively; we match FQNs exactly. |
| `@ControllerAdvice` + `@ExceptionHandler` | C | Not endpoints, but they define the error contract of *every* endpoint. |
| **Spring Data REST** (`@RepositoryRestResource`) | **C** | A repository *interface* silently becomes a full CRUD HTTP API. No controller, no mapping annotation. |
| Actuator — `@Endpoint`/`@ReadOperation`, plus built-ins | A / C | The annotations are Tier A; the built-ins exist from a dependency and a property, with no code at all. |
| Servlets, filters, interceptors | C | `@WebServlet`, `FilterRegistrationBean`, `HandlerInterceptor`, `WebFilter` |
| `@ConditionalOnProperty` / `@Profile` controllers | C | An endpoint that exists in one environment and not another |
| WebFlux **functional routing** — `RouterFunctions.route().GET(…)`, Kotlin `coRouter { }` | **B** | `fluent_chain` / `combinator` — no annotations exist |
| WebFlux annotated controllers returning `Mono`/`Flux` | B | The **endpoint is found**; the response type is the wrapper, because unwrapping ([D02](components/D02-catalog-schema.md) §2a) is designed and not implemented |
| Nested and inner classes | B | Skipped and *reported* — honest, but a nested `@Controller` is a real missed endpoint |

---

## 4. Spring Framework 7 / Spring Boot 4

| Feature | Exact form | Tier | Verified |
|---|---|---|---|
| **API versioning** | `version` attribute on `@RequestMapping` and composed annotations: `@GetMapping(path="/x", version="1.1")`. Fixed (`"1.2"`) or baseline (`"1.2+"`). | **A** | ✅ javadoc + release notes |
| **HTTP service client registration** | `org.springframework.web.service.registry.ImportHttpServices` on a `@Configuration` class | A (once outbound exists) | ✅ javadoc |
| **JSpecify null-safety** | `org.jspecify.annotations.{Nullable,NonNull,NullMarked,NullUnmarked}`, `TYPE_USE` + `RUNTIME` | **B** | ✅ javadoc |
| `org.springframework.lang.Nullable` deprecated | Replaced by JSpecify; **both FQNs must be matched** | B | ✅ reference docs |
| `RestTemplate` deprecation | Intent announced in 7.0; formal `@Deprecated` reportedly 7.1 | — | ⚠️ secondary source |
| Version-aware functional route predicates | A `RouterFunctions` predicate matching by API version | B | ⚠️ name unconfirmed |

**Easy to miss:** JSpecify is `TYPE_USE` with `RUNTIME` retention, so it lands in
`RuntimeVisibleTypeAnnotations`. [M03](components/M03-scanner.md) names the **Invisible**
attribute, and the scanner does not override `visitTypeAnnotation` at all today, so neither
is read. Nullability is what sets `required` on a contract field, so this gates honest
shape comparison.

---

## 5. Other JVM frameworks

The headline finding: **in both Micronaut and Quarkus the original annotations survive
compilation with `RUNTIME` retention.** Neither framework's build-time processor strips
them — both emit *additional* generated classes alongside. Our bytecode approach works on
them unchanged, and the annotation-driven parts are Tier A.

### Micronaut

| Concern | Exact form | Tier |
|---|---|---|
| Inbound | `io.micronaut.http.annotation.Controller` (class, `value` is a **String**) + `Get`/`Post`/`Put`/`Delete`/`Patch`/`Head`/`Options`/`Trace`, each with `value`/`uri` as String **and** `uris` as String[] | **A** |
| Declarative client | `io.micronaut.http.client.annotation.Client` — URL, service id, or `${property}` | A |
| Programmatic client | `HttpRequest.GET(uri)` static factory + `client.retrieve`/`exchange` | `registration_call` |
| Kafka | `@KafkaListener` + `@Topic`; `@KafkaClient` + `@Topic` | A |
| JMS | `@JMSListener` + `@Queue`/`@Topic` | A |
| SQS | **No first-party annotations** — raw AWS SDK, or `micronaut-jms-sqs` | B |
| Pub/Sub | `@PubSubClient`, `@PubSubListener` + `@Subscription` — **the only first-party Pub/Sub annotation surveyed** | A |
| gRPC | `@Singleton` extending the generated `ImplBase`; `@GrpcChannel` factory | B |

⚠️ Kafka annotations documented under `io.micronaut.configuration.kafka.annotation`;
Micronaut has relocated `configuration.*` packages before — verify per version.

### Quarkus

| Concern | Exact form | Tier |
|---|---|---|
| Inbound | **`jakarta.ws.rs`**: `@Path` (a scalar String) + `@GET`/`@POST`/`@PUT`/`@DELETE`/`@PATCH`/`@HEAD`/`@OPTIONS` | **A** |
| Custom verbs | `jakarta.ws.rs.HttpMethod` as a meta-annotation | B |
| Reactive Routes | `io.quarkus.vertx.web.Route` on bean methods | A |
| Declarative client | `org.eclipse.microprofile.rest.client.inject.RegisterRestClient`; URL via `baseUri` **or** a `<fqcn>/mp-rest/url` property | A + `config_join` |
| Programmatic client | Vert.x Mutiny `WebClient` | `fluent_chain` |
| Messaging (all brokers) | SmallRye `@Incoming`/`@Outgoing` naming a **channel**, topic bound in `application.properties` | **`config_join`** — see §11 |
| gRPC | `io.quarkus.grpc.GrpcService`, `io.quarkus.grpc.GrpcClient("name")` | A |

---

## 6. JVM libraries and integration frameworks

### Protocol Buffers on the JVM

Generated classes extend `com.google.protobuf.GeneratedMessageV3` (protobuf-java 3.x) or
**`GeneratedMessage`** (4.26+ — `GeneratedMessageV3` is deprecated and slated for removal
in 5.x ✅ verified). **Both must be matched.** Each message exposes a static
`getDescriptor()`, and the generated outer file class embeds the serialized
`FileDescriptorProto`.

**This means the entire `.proto` is recoverable from a compiled jar** — the same trick as
Avro's `SCHEMA$`. Tier B, high value: field numbers are the strongest join key of any
protocol, because both sides derive from the same schema.

### Akka and Apache Pekko

✅ Verified, and easy to get wrong. Lightbend moved Akka to the Business Source License
from 2.7; **Apache Pekko** is the Apache-2.0 fork of Akka 2.6.x. Packages were renamed
`akka.*` → `org.apache.pekko.*`, and `alpakka` → `connectors` (so
`akka.stream.alpakka.jms` became `org.apache.pekko.stream.connectors.jms`).

**Every Akka matcher needs a Pekko twin.** A catalog written against one silently matches
nothing in a codebase using the other, and the split runs right through the middle of the
Scala/JVM ecosystem.

| Concern | Shape | Tier |
|---|---|---|
| Akka HTTP routing DSL — `path("users" / IntNumber) { get { complete(…) } }` | `combinator` | **C-ish.** Nested closures where the route is a *value*, frequently composed across methods. **The hardest inbound form surveyed**, harder than WebFlux functional routing or Rust's `warp`. |
| Akka HTTP client — `Http().singleRequest(HttpRequest(uri = …))` | `fluent_chain` | B |
| Alpakka / Pekko Connectors Kafka — `Consumer.plainSource(settings, Subscriptions.topics("t"))` | `registration_call` | B |
| Akka gRPC | generated services | B |
| **Actor messaging** — `ref ! msg`, `ref.tell(msg)` | — | **C, and possibly permanent** |

**Actor messaging deserves a plain statement.** `ref ! msg` is a real call edge — control
and data cross it — but the receiving actor is determined by an `ActorRef` created
somewhere else entirely, often from configuration or a router. Class hierarchy analysis
cannot see through it, and neither can RTA or VTA. **In a heavily actor-based system, most
of the call graph is invisible to any static tool**, ours included. If we support Akka, we
must say so in the coverage report rather than presenting a confident but hollow graph.

### Vert.x

`io.vertx.ext.web.Router` ✅ — `router.get("/api/whiskies").handler(this::getAll)`, also
`router.route(HttpMethod.GET, path)` and `router.post(…)`.

This is a `fluent_chain`, but a **short and regular one**: receiver type identifies the
framework, method name gives the verb, first argument gives the path, and `.handler(ref)`
gives the target. It is one of the easier Tier B wins and a good first exercise for chain
reconstruction.

| Concern | Shape | Note |
|---|---|---|
| `Router` verb methods | `fluent_chain` | As above |
| **Event bus** — `vertx.eventBus().send("address", msg)` / `.consumer("address", h)` | `registration_call` | An in-process pub/sub with **string addresses** — matchable exactly like topics, and a genuine boundary between modules |
| `RouterBuilder.create(vertx, "openapi.yml")` + `.operation("opId").handler(…)` | artifact + `fluent_chain` | **Routes come from the OpenAPI document**, bound by `operationId`. Joins directly to our OpenAPI reader. |
| Service proxies (`@ProxyGen`) | `annotation` | Generates event-bus clients |

### Others worth a catalog

| Framework | Shape | Note |
|---|---|---|
| **Apache Camel** — `from("kafka:orders?brokers=…").to("http://svc/api")` | `fluent_chain` over **URI strings** | Exceptionally information-dense: protocol, direction, destination and options all in one literal. If we read Camel routes we get inbound *and* outbound *and* the protocol in one pass. High value. |
| **Ktor** (server) — `routing { get("/path") { … } }` | `combinator` | Kotlin DSL; relevant to Android teams running Kotlin on both sides |
| Javalin — `app.get("/path", ctx -> …)` | `registration_call` | Easy |
| Dropwizard, RESTEasy, Jersey, Helidon MP | `annotation` (JAX-RS) | Covered by the same `jakarta.ws.rs` catalog as Quarkus |
| Spring GraphQL — `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` | `annotation` | Tier A |
| WebSocket / STOMP — `@MessageMapping`, `@ServerEndpoint` | `annotation` | Tier A |
| RabbitMQ — `@RabbitListener` | `annotation` | Tier A |
| Apache Pulsar — `@PulsarListener` | `annotation` | Tier A |
| Scheduling — `@Scheduled`, Quartz | `annotation` | Not a protocol, but a real entry point |
| Spring Integration | `@ServiceActivator`, `@InboundChannelAdapter` | `config_join` — channels, not destinations |
| Temporal / Cadence | `@WorkflowInterface`, `@ActivityInterface` | `annotation` — a durable async boundary |

---

## 7. Outbound HTTP on the JVM

**Nothing here is supported.** Phase 1 records no call sites at all.

| Client | Shape | Tier |
|---|---|---|
| `RestTemplate` | `registration_call` | **A** |
| Feign `@FeignClient`, Retrofit `@GET`, Spring `@HttpExchange`, Micronaut `@Client`, MicroProfile `@RegisterRestClient` | `annotation` | **A** |
| `RestClient` (Spring 6.1+), `WebClient`, OkHttp, JDK `HttpClient`, Apache HttpClient | `fluent_chain` | **B** |
| Legacy `URL.openConnection()` | `fluent_chain` | B |

**Chain reconstruction is not one feature among many — it is the gate on modern HTTP
clients generally.** Every client written in the last five years is a builder chain.

**A schema problem worth flagging now:** `@HttpExchange` is used for declarative *clients*,
and Spring 6.1+ also supports implementing such an interface *server-side*. The same
annotation means inbound or outbound depending on context, which our catalog format — where
`direction` is a property of the catalog, not of the match — cannot express.

---

## 8. By protocol (JVM)

### Kafka
| Form | Exact | Tier |
|---|---|---|
| Spring `@KafkaListener` | `org.springframework.kafka.annotation.KafkaListener` — `topics`, `topicPattern`, `topicPartitions`, `groupId` | **A** |
| Spring `KafkaTemplate` | `send(topic, …)`; also `send(ProducerRecord)` and `send(Message)` with the topic in a header | A / B |
| Plain client — consume | `KafkaConsumer.subscribe(Collection<String>)` or `subscribe(Pattern)` | A |
| Plain client — produce | `KafkaProducer.send(ProducerRecord)` — **the topic is a constructor argument of `ProducerRecord`** | **B** |
| Spring Cloud Stream functional beans | `Consumer<T>`/`Supplier<T>`; topic in `spring.cloud.stream.bindings.<name>.destination` | **`config_join`** |

⚠️ `KafkaTemplate.send` returns `ListenableFuture` in older Spring Kafka, `CompletableFuture` in current.

### AWS SQS
| Form | Exact | Tier |
|---|---|---|
| Spring Cloud AWS 3.x | `io.awspring.cloud.sqs.annotation.SqsListener`; `io.awspring.cloud.sqs.SqsTemplate` | **A** |
| Spring Cloud AWS 2.x | `io.awspring.cloud.messaging.listener.annotation.SqsListener` ⚠️ different package | A |
| AWS SDK v2 | `SqsClient.sendMessage(SendMessageRequest)`, queue URL via `…builder().queueUrl(…)` | **B** |

### Google Cloud Pub/Sub
**The hardest of the six.** No first-party Spring annotation exists.

| Form | Exact | Tier |
|---|---|---|
| Micronaut | `@PubSubListener` + `@Subscription`, `@PubSubClient` | **A** |
| Client library — publish | `Publisher.newBuilder(TopicName.of(project, topic)).build()`, `.publish(…)` | **B** |
| Client library — subscribe | `Subscriber` + `MessageReceiver`, `.startAsync()` | **B/C** |
| Spring Cloud GCP | `PubSubTemplate.subscribe(…)`, or `PubSubInboundChannelAdapter` + `@ServiceActivator` | **C** |

⚠️ Spring Cloud GCP packages moved from `org.springframework.cloud.gcp.*` to `com.google.cloud.spring.*`; version of the rename unconfirmed.

### JMS
| Form | Exact | Tier |
|---|---|---|
| Spring | `org.springframework.jms.annotation.JmsListener` (`destination`, `selector`, `subscription`); `JmsTemplate.send`/`convertAndSend` | **A** |
| Direct API | `jakarta.jms.{ConnectionFactory,Session,MessageProducer,MessageConsumer}` | B |

**Package change:** `javax.jms` (Spring ≤5 / Boot ≤2) → `jakarta.jms` (Spring 6 / Boot 3+). Both must be matched.

### gRPC
| Form | Exact | Tier |
|---|---|---|
| Generated server base | `FooGrpc.FooImplBase` implementing `io.grpc.BindableService` | **B** — `interface_implementation`, designed but not implemented |
| Generated client stubs | `FooStub`/`FooBlockingStub`/`FooFutureStub` extending `io.grpc.stub.Abstract{Async,Blocking,Future}Stub` | B |
| `net.devh` starter | `net.devh.boot.grpc.server.service.GrpcService`, `net.devh.boot.grpc.client.inject.GrpcClient` | A |
| Quarkus | `io.quarkus.grpc.GrpcService`, `io.quarkus.grpc.GrpcClient` | A |
| Official `org.springframework.grpc` starter | ⚠️ names unconfirmed | A |

### SOAP
Deferred by decision. `@WebService`/`@WebMethod` would be Tier A; WSDL reading is a separate tier-2 artifact, and without it SOAP link matching falls back to structural comparison.

### Avro
| Form | Exact | Tier |
|---|---|---|
| Generated classes | Extend `org.apache.avro.specific.SpecificRecordBase`, carry a **`public static final Schema SCHEMA$`** | **B** |
| Confluent serializers | `io.confluent.kafka.serializers.KafkaAvroSerializer`/`Deserializer` ⚠️ | B |
| Subject naming | Default `TopicNameStrategy`: `<topic>-key` / `<topic>-value` | B |

---

## 9. Beyond the JVM

**The fact-source question decides everything, and it ranks the languages very differently
from how difficulty is usually assumed.** Before asking which frameworks a language has,
ask what its toolchain will tell us.

| Language | Compiler-grade fact source | Types | Build needed | Call graph available | Rank |
|---|---|---|---|---|---|
| **Java / Kotlin** | JVM bytecode via **ASM** | Full | Yes | We write it | 1 |
| **Go** | **`go/packages`** + `go/ssa` | Full | No (deps only) | ✅ **`callgraph/{cha,rta,vta}` ships with the toolchain** | 2 |
| **TypeScript** | **`ts.TypeChecker`** compiler API | Full where annotated | No | `Jelly` ✅ | 3 |
| **Swift** | **IndexStoreDB** (index-while-building) ✅ | Full | Yes (macOS) | Index has call relations | 4 |
| **Rust** | None stable — `syn` has no types; rustdoc JSON is unstable ⚠️ | Syntax only | — | None | 6 |
| **Python** | None — pyright has **no programmatic API**, only LSP ⚠️ | Sparse (§10) | No | `PyCG` | 7 |
| **JavaScript** (no TS) | None | None | No | `Jelly`, degraded | 8 |

Three findings from this table are worth stating outright.

**Go ships the analysis we deferred.** `golang.org/x/tools/go/callgraph` provides `static`,
`cha`, `rta` and `vta` as maintained library code ✅, and `cha` is documented as sound on
partial programs — libraries with no `main`, which is our situation exactly. For the JVM we
planned to write class hierarchy analysis and defer variable type analysis to a later
version. For Go, all of it exists. **Go's dispatch resolution starts ahead of the JVM's.**

**Swift is not the hard case people assume.** `swiftc` emits index data as a side effect of
compilation, and `IndexStoreDB` reads it into a queryable store of symbols, occurrences and
relations ✅ — the same data `sourcekit-lsp` uses for call hierarchy. It needs a build,
which fits DR-4 precisely. Periphery already works this way.

**For TypeScript the JVM rule inverts.** We scan what is compiled on the JVM because
bytecode is richer than source. In TypeScript compiled output is *strictly poorer* — types
erased, decorators lowered to `__decorate` calls, bundlers renaming and inlining. **We must
scan TypeScript source**, with `tsconfig.json` as the build input carrying authority under
DR-4.

Per-language detail: [Go](coverage/go.md) · [Rust](coverage/rust.md) ·
[Python](coverage/python.md) · [TypeScript and JavaScript](coverage/typescript.md) ·
[Android and iOS](coverage/mobile.md).

---

## 10. The typing problem in Python and JavaScript

The concern is real, but it is narrower and more tractable than "these languages have no
types". Three findings change the shape of the problem.

### The types exist exactly where the framework needed them

The frameworks hardest to type-erase are the ones that **cannot function without
declarations**. FastAPI builds validation and its OpenAPI document from parameter
annotations. NestJS DTOs carry `class-validator` decorators. tRPC procedures are defined by
a `zod` schema. Fastify routes take a JSON Schema in the options object.

So payload coverage correlates with **framework modernity, not with language**:

| Typed and recoverable | Untyped, needs inference |
|---|---|
| FastAPI + Pydantic, Litestar | Flask `request.json["x"]` |
| NestJS + `class-validator`, tRPC + `zod`, Fastify + JSON Schema | Express `req.body.x` |
| Go struct tags, Rust `serde`, Swift `Codable` | Plain JavaScript with no `tsconfig.json` |

The right response is not one verdict per language but **`resolution` per endpoint** —
machinery [D00](components/D00-fact-schema.md) already has.

### "Python is typed now" is false at the granularity we need

⚠️ From a 2026 study of Python libraries and frameworks: **91% contain at least one type
hint, but half cover only 13.6% of their members.** Among libraries that use hints
systematically, median coverage is 45.8% of parameters and 35.9% of returns.

So a repository-level check for "does this project use type hints" tells us almost nothing.
The question has to be asked per function, and the answer will usually be no.

### Benchmark evidence says to use an LLM for shapes and never for edges

⚠️ From an empirical study of 24 LLMs on Python and JavaScript static analysis (arXiv
2410.00603, Venkatesh and Bodden), evaluated against TypeEvalPy and the SWARM-CG/SWARM-JS
benchmarks:

- **Call graphs: traditional static analysis wins, consistently.** `PyCG` for Python and
  `Jelly` for JavaScript outperformed every model tested. Even the strongest models
  "struggle with completeness and soundness."
- **Type inference for Python: LLMs win clearly**, surpassing `HeaderGen` and the hybrid
  `HiTyper`.

That is a precise split, and it maps directly onto machinery we already have:

| Task | Method | `evidence` | `precedence` |
|---|---|---|---|
| Call edges, dispatch, reachability | Static analysis (`PyCG`, `Jelly`, `go/callgraph`) | `syntax` / `compiler` | 50 |
| Payload field names, types, optionality | LLM, where declarations are absent | `llm` | 10 |

**The operating rule: an LLM may propose a shape; it may never propose an edge.** An
invented field is a visible, checkable error that a human overlay can correct at precedence
90. An invented call edge silently corrupts blast-radius answers — the thing the tool exists
to compute — and nothing downstream would catch it.

`PyCG`, `Jelly`, `TypeEvalPy` and `SWARM-CG` also give us something rarer than a technique:
**published benchmarks to measure our own output against**, rather than asserting quality.

### The residual honest gap

Where a Flask handler reads `request.json["customer"]["id"]`, the wire shape exists only as
a set of subscript expressions scattered through the function body. Recovering it means
collecting field accesses along a path — cheap and reliable for *names*, unreliable for
*types* and worse for *optionality*. `boto3` is the extreme case: its clients are
synthesised at runtime from JSON service models, so `client.send_message` is defined in no
Python file at all and no analysis will resolve it. Detection there is a `name_match` on the
service string `boto3.client("sqs")`, and `resolution: narrowed` is the honest ceiling.

---

## 11. The strategic risk: boundaries are leaving the code

The clearest pattern across all this research, and the thing most likely to limit Sextant's
value over time.

**Modern frameworks move destinations out of annotations and into configuration**, leaving
only an opaque channel name in the code:

| Framework | In the code | Where the destination actually lives |
|---|---|---|
| Spring Cloud Stream | a `Consumer<T>` bean named `handleOrder` | `spring.cloud.stream.bindings.handleOrder-in-0.destination` |
| Quarkus / SmallRye | `@Incoming("orders")` | `mp.messaging.incoming.orders.topic` |
| MicroProfile REST Client | `@RegisterRestClient(configKey="orders")` | `orders/mp-rest/url` |
| Django | a view function | `urls.py`, in a different module |

An annotation-only reader sees `handleOrder-in-0` and learns nothing. **For these
frameworks the code-to-configuration join is not an optimisation — it is the only path to
the answer.**

Sextant is better placed for this than most tools, because configuration resolution is
already a first-class pass and endpoints already carry *expressions* rather than values. But
no catalog style expresses "the destination is a property key derived from this bean's
name", and that is a gap in [D02](components/D02-catalog-schema.md), not a missing catalog
file.

The same drift shows in HTTP: WebFlux functional routing, Akka HTTP's DSL, Rust's `warp`,
and every modern client are chains or combinators rather than annotations — and Next.js and
SvelteKit have moved the path out of the code entirely, into the filename. **The
annotation-driven engine covers the past well and the future progressively less well.**

---

## 12. What this implies

**Tier A is large, cheap, and immediately valuable.** `@RequestMapping(method=…)`, `path`
as an alias, Micronaut, Quarkus/JAX-RS, `@KafkaListener`, `@JmsListener`, `@SqsListener`,
Retrofit, GraphQL, RabbitMQ — YAML files against an engine that exists and is proven.

**`fluent_chain` reconstruction is the single highest-leverage capability.** It gates every
modern HTTP client, WebFlux functional routing, Vert.x, the AWS SDK, the Pub/Sub client
library, plain Kafka producers, and Apache Camel. Almost every Tier B entry traces to it.
Vert.x's `Router` is the cleanest first exercise; Camel offers the largest single payoff.

**Implementation order across languages should follow the fact sources, not the popularity
of the language:** Go, then TypeScript, then Swift, then Python, then Rust. Go because the
toolchain hands us more than the JVM does; Rust last because no stable compiler API exists,
not because the ecosystem is unmatchable.

**Three engines do not exist yet and each unlocks a whole ecosystem:** `filesystem` routing
(Next.js, SvelteKit, Remix, Nuxt), `config_join` destinations (§11), and `combinator` DSL
routing (Akka HTTP, Ktor, `warp`, WebFlux functional).

**Four things should be settled in the schema before more catalogs are written**, because
none is expressible today: a match whose direction depends on context (`@HttpExchange`); a
destination derived from a configuration key (§11); a path derived from a file's location;
and per-endpoint `resolution` driven by whether the framework forced a declaration (§10).

**Two limits should be stated in the product, not discovered by users.** Actor messaging is
largely invisible to static analysis, so an Akka-heavy system will produce a confident but
hollow graph unless we report it. And `runtime_dynamic` boundaries — `boto3`, DRF routers,
`@grpc/proto-loader` — are not gaps we will close later; they are boundaries that do not
exist statically, and the coverage report has to say so.

---

## Verification status

Researched August 2026 against primary sources — Spring, Micronaut, Quarkus, Apache Kafka,
AWS, Google Cloud, gRPC, Avro, Protocol Buffers, Apache Pekko, Vert.x, the Go and Swift
toolchains, and the academic literature on LLM-assisted static analysis. Items marked ⚠️
rest on secondary sources or could not be confirmed, and **must be checked against the
library's own documentation or source before entering a catalog**. A wrong annotation name
does not fail loudly; it silently matches nothing, which is exactly how petclinic returned
zero endpoints.
