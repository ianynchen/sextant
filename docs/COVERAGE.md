# COVERAGE

What Sextant detects today, and what it does not. Delivery status is in
[PROJECT.md](PROJECT.md); this document is about *reach* — which real-world ways of
declaring a boundary we can actually see.

Written after running Phase 1 against a real project ([spring-petclinic](https://github.com/spring-projects/spring-petclinic)),
which found **zero endpoints on the first attempt** because the catalog matched
`@RestController` and petclinic uses `@Controller`. That failure is the reason this
document exists: coverage gaps are invisible until something real is pointed at the tool.

---

## How to read this

Every gap is one of three kinds, and the distinction is the whole point — they cost
wildly different amounts to close.

| Tier | Means | Cost |
|---|---|---|
| **A** | A catalog entry away. Fits an engine that already exists. | One YAML file and a fixture. **No code.** |
| **B** | Needs a scanner capability we have not built. | Real work in the extractor, then a catalog. |
| **C** | The boundary does not exist in the code at all. | New modelling — a rule that infers a boundary from something other than an annotation. |

Tier A is large and cheap. Tier B is gated almost entirely on one capability. Tier C is
where the interesting design problems are.

**Verification.** Facts below were researched against primary sources in August 2026.
Anything marked ⚠️ was not confirmed from a primary source and **must be verified before
being written into a catalog** — a wrong annotation name produces silently wrong output,
which is the failure mode this project cares most about.

---

## 1. Supported today

Java and Kotlin, from compiled bytecode, via ASM. Two catalogs, both `annotation_driven`,
both inbound HTTP only.

| Catalog | Type annotation | Method annotations | Path prefix |
|---|---|---|---|
| `spring-web` | `@RestController` | `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping` | class-level `@RequestMapping`, `value` only |
| `spring-mvc` | `@Controller` | same | same |

Paths are read from the `value` attribute, first array element, with a scalar fallback.
Endpoints carry request and response **type references**, not expanded field lists.

**Two scanner capabilities are implemented** of eight designed: `annotation_args` and
`typed_signatures`. Everything below that needs one of the other six is Tier B by
definition.

**Nothing outbound exists.** No call sites are recorded at all, so the system tier has
nothing to match on.

---

## 2. Gaps inside Spring MVC — the framework we claim to support

These are the highest-value gaps in the project, because they affect codebases we would
otherwise report on confidently.

| Gap | Tier | Note |
|---|---|---|
| **`@RequestMapping(method = RequestMethod.GET)`** | **A** | The original Spring form, ubiquitous in code written before 4.3. We treat `@RequestMapping` **only** as a prefix, so such a controller yields **zero endpoints** — the petclinic failure again, in a different disguise. **The single biggest gap.** |
| `@RequestMapping` with no `method` | A | Matches every verb. Invisible today. |
| `path =` as an alias for `value =` | A | Spring treats them identically. We read `value` only, so `@GetMapping(path="/x")` produces an **empty path** — wrong output, not missing output. |
| `produces` / `consumes` | A | Part of the wire contract; ignored entirely. |
| `@RequestMapping` on an **interface or superclass** | B | Spring inherits mappings. We read only a class's own annotations. Common with `interface FooApi` + `class FooController implements FooApi`. |
| **Meta-annotations** — custom `@ApiGet` composed from `@GetMapping` | B | Spring resolves these transitively. We match FQNs exactly, so a composed annotation is invisible. Needs scanning annotation *classes* for their own annotations. |
| `@ControllerAdvice` + `@ExceptionHandler` | C | Not endpoints, but they define the error contract of *every* endpoint. |
| **Spring Data REST** (`@RepositoryRestResource`) | **C** | A repository *interface* silently becomes a full CRUD HTTP API. No controller, no mapping annotation, nothing to match. |
| Actuator — `@Endpoint`/`@ReadOperation`, plus built-ins | A / C | The annotations are Tier A; the built-in endpoints exist from a dependency and a property, with no code at all. |
| Servlets, filters, interceptors | C | `@WebServlet`, `FilterRegistrationBean`, `HandlerInterceptor`, `WebFilter`. |
| `@ConditionalOnProperty` / `@Profile` controllers | C | An endpoint that exists in one environment and not another — interacts with the environment model we designed but have not exercised. |
| WebFlux **functional routing** — `RouterFunctions.route().GET(…)`, Kotlin `coRouter { }` | **B** | No annotations exist. Needs chain reconstruction and the `fluent` engine style, neither implemented. |
| WebFlux annotated controllers returning `Mono`/`Flux` | B | The **endpoint is found**; the response type is the wrapper, because wrapper unwrapping ([D02](components/D02-catalog-schema.md) §2a) is designed and not implemented. |
| Nested and inner classes | B | Currently skipped and *reported* as uncovered — honest, but a nested `@Controller` is a real missed endpoint. |

---

## 3. Spring Framework 7 / Spring Boot 4

Researched specifically because the version is current and our catalogs were written
against Boot 3 idioms.

| Feature | Exact form | Tier | Verified |
|---|---|---|---|
| **API versioning** | `version` attribute on `@RequestMapping` and its composed annotations: `@GetMapping(path="/x", version="1.1")`. Values fixed (`"1.2"`) or baseline (`"1.2+"`). | **A** | ✅ javadoc + release notes |
| **HTTP service client registration** | `org.springframework.web.service.registry.ImportHttpServices` on a `@Configuration` class, registering `@HttpExchange` interfaces as proxies without manual `HttpServiceProxyFactory` wiring | A (once outbound exists) | ✅ javadoc |
| **JSpecify null-safety** | `org.jspecify.annotations.{Nullable,NonNull,NullMarked,NullUnmarked}`, `TYPE_USE` + `RUNTIME` | **B** | ✅ javadoc |
| `org.springframework.lang.Nullable` deprecated | Replaced by JSpecify; **both FQNs must be matched**, since code compiled against ≤6 still carries the old one | B | ✅ reference docs |
| `RestTemplate` deprecation | Intent announced in 7.0; formal `@Deprecated` reportedly 7.1 | — | ⚠️ secondary source only |
| Version-aware functional route predicates | A predicate for matching by API version in `RouterFunctions` | B | ⚠️ method name unconfirmed |

**Consequence for us that is easy to miss.** JSpecify is `TYPE_USE` with `RUNTIME`
retention, so it lands in `RuntimeVisibleTypeAnnotations`. [M03](components/M03-scanner.md)
names the **Invisible** attribute. When type annotations are implemented, **both** must be
read — and today the scanner overrides `visitTypeAnnotation` at all, so neither is.
Nullability is what sets `required` on a contract field, so this gates honest shape
comparison.

---

## 4. Other JVM frameworks

The headline finding: **in both Micronaut and Quarkus the original annotations survive
compilation with `RUNTIME` retention.** Neither framework's build-time processor strips
them — both emit *additional* generated classes alongside. So Sextant's bytecode approach
works for them unchanged, and the annotation-driven parts are Tier A.

### Micronaut

| Concern | Exact form | Tier |
|---|---|---|
| Inbound | `io.micronaut.http.annotation.Controller` (class, `value` is a **String**, not an array) + `Get`/`Post`/`Put`/`Delete`/`Patch`/`Head`/`Options`/`Trace`, each with `value`/`uri` as String **and** `uris` as String[] | **A** |
| Declarative client | `io.micronaut.http.client.annotation.Client` — target is a URL, a service id, or a `${property}` placeholder | A |
| Programmatic client | `HttpRequest.GET(uri)` static factory + `client.retrieve(…)`/`exchange(…)` — **not** a fluent builder over a live request | A-ish |
| Kafka | `@KafkaListener` (class) + `@Topic` (method); `@KafkaClient` + `@Topic` for producers | A |
| JMS | `@JMSListener` (class) + `@Queue`/`@Topic` (method) | A |
| SQS | **No first-party annotations** — raw AWS SDK v2, or `micronaut-jms-sqs` bridging the JMS annotations | B |
| Pub/Sub | `@PubSubClient` (interface) and `@PubSubListener` (class) + `@Subscription` — **Micronaut is the only framework surveyed with a first-party Pub/Sub annotation** | A |
| gRPC | Bean extending the generated `XxxGrpc.XxxImplBase`; client stubs built manually from a `@GrpcChannel`-qualified channel | B |

⚠️ The Kafka annotations are documented under `io.micronaut.configuration.kafka.annotation`; Micronaut has relocated `configuration.*` packages before, so verify per version.

### Quarkus

| Concern | Exact form | Tier |
|---|---|---|
| Inbound | **`jakarta.ws.rs`** (Jakarta REST): `@Path` (class, `value` is a String) + `@GET`/`@POST`/`@PUT`/`@DELETE`/`@PATCH`/`@HEAD`/`@OPTIONS` | **A** |
| Custom verbs | `jakarta.ws.rs.HttpMethod` as a meta-annotation | B (meta-annotations) |
| Reactive Routes | `io.quarkus.vertx.web.Route` on bean methods — a genuinely distinct second style | A |
| Declarative client | `org.eclipse.microprofile.rest.client.inject.RegisterRestClient`; URL via `baseUri` **or** a `<fqcn>/mp-rest/url` property | A + config join |
| Programmatic client | Vert.x `WebClient` (Mutiny flavour) — genuinely fluent: `webClient.get(path).send()` | B |
| Messaging (all brokers) | SmallRye: `org.eclipse.microprofile.reactive.messaging.{Incoming,Outgoing}` naming a **channel**, with the actual topic bound in `application.properties` | **C** — see §7 |
| gRPC | `io.quarkus.grpc.GrpcService` on a CDI bean; `io.quarkus.grpc.GrpcClient("name")` injection | A |

Note that Jakarta REST's `@Path` `value` is a **scalar String**, not an array — precisely
the case our scalar fallback was added for.

---

## 5. Outbound HTTP

**Nothing here is supported.** Phase 1 records no call sites at all. Listed by what it
would take once outbound exists.

| Client | Shape | Tier |
|---|---|---|
| `RestTemplate` | Single call, URL as an argument | **A** |
| Feign `@FeignClient` | Annotation on an interface | **A** |
| Retrofit `@GET` | Annotation on an interface | **A** |
| Spring `@HttpExchange`/`@GetExchange` | Annotation on an interface | **A** |
| Micronaut `@Client`, MicroProfile `@RegisterRestClient` | Annotation on an interface | **A** |
| `RestClient` (Spring 6.1+) | `restClient.get().uri(…).retrieve().body(…)` | **B** — chain reconstruction |
| `WebClient` | `webClient.get().uri(…).retrieve().bodyToMono(…)` | **B** |
| OkHttp | `new Request.Builder().url(…).get().build()` then `client.newCall(req).execute()` | **B** |
| JDK `java.net.http.HttpClient` | `HttpRequest.newBuilder().uri(…).GET().build()` | **B** |
| Apache HttpClient | `new HttpGet(url)` + `client.execute(…)` | B |
| Legacy `URL.openConnection()` | — | B |

**Chain reconstruction is not one feature among many — it is the gate on modern HTTP
clients generally.** Every client written in the last five years is a builder chain.

**One schema problem worth flagging now:** `@HttpExchange` is used for declarative
*clients*, and Spring 6.1+ also supports implementing such an interface *server-side*. The
same annotation means inbound or outbound depending on context, which our catalog format —
where `direction` is a property of the catalog, not of the match — cannot express.

---

## 6. By protocol

Against the protocol list this project set out to support.

### REST / HTTP
Partially covered inbound (§1–4), nothing outbound (§5).

### Kafka
| Form | Exact | Tier |
|---|---|---|
| Spring `@KafkaListener` | `org.springframework.kafka.annotation.KafkaListener` — `topics`, `topicPattern`, `topicPartitions`, `groupId` | **A** |
| Spring `KafkaTemplate` | `send(topic, …)` overloads; also `send(ProducerRecord)` and `send(Message)` with the topic in a header | A / B |
| Plain client — consume | `KafkaConsumer.subscribe(Collection<String>)` or `subscribe(Pattern)` | A |
| Plain client — produce | `KafkaProducer.send(ProducerRecord)` — **the topic is a constructor argument of `ProducerRecord`**, not an argument of `send` | **B** — needs value tracking across statements |
| Spring Cloud Stream functional beans | `Consumer<T>`/`Supplier<T>` beans; topic in `spring.cloud.stream.bindings.<name>.destination` | **C** — see §7 |

⚠️ `KafkaTemplate.send` returns `ListenableFuture` in older Spring Kafka and
`CompletableFuture` in current — version-dependent.

### AWS SQS
| Form | Exact | Tier |
|---|---|---|
| Spring Cloud AWS 3.x | `io.awspring.cloud.sqs.annotation.SqsListener`; `io.awspring.cloud.sqs.SqsTemplate` | **A** |
| Spring Cloud AWS 2.x | `io.awspring.cloud.messaging.listener.annotation.SqsListener` — different package ⚠️ | A |
| AWS SDK v2 | `SqsClient.sendMessage(SendMessageRequest)`, `receiveMessage(…)`; queue URL via `…builder().queueUrl(…)` | **B** — builder chain |

### Google Cloud Pub/Sub
**The hardest of the six.** No first-party Spring annotation exists.

| Form | Exact | Tier |
|---|---|---|
| Micronaut | `@PubSubListener` + `@Subscription`, `@PubSubClient` | **A** |
| Client library — publish | `Publisher.newBuilder(TopicName.of(project, topic)).build()`, `.publish(PubsubMessage)` | **B** |
| Client library — subscribe | `Subscriber` + a `MessageReceiver` implementation, `.startAsync()` | **B/C** |
| Spring Cloud GCP | `PubSubTemplate.subscribe(…)`, or a Spring Integration `PubSubInboundChannelAdapter` + `@ServiceActivator` | **C** |

⚠️ Spring Cloud GCP packages moved from `org.springframework.cloud.gcp.*` to
`com.google.cloud.spring.*`; the version of that rename was not confirmed.

### JMS
| Form | Exact | Tier |
|---|---|---|
| Spring | `org.springframework.jms.annotation.JmsListener` (`destination`, `selector`, `subscription`); `JmsTemplate.send`/`convertAndSend` | **A** |
| Direct API | `jakarta.jms.{ConnectionFactory,Session,MessageProducer,MessageConsumer}` | B |

**Package change:** `javax.jms` (Spring ≤5 / Boot ≤2) → `jakarta.jms` (Spring 6 / Boot 3+).
Both must be matched.

### gRPC
| Form | Exact | Tier |
|---|---|---|
| Generated server base | `FooGrpc.FooImplBase` implementing `io.grpc.BindableService` | **B** — `interface_implementation` style, designed but not implemented |
| Generated client stubs | `FooGrpc.FooStub`/`FooBlockingStub`/`FooFutureStub`, extending `io.grpc.stub.Abstract{Async,Blocking,Future}Stub` | B |
| `net.devh` starter | `net.devh.boot.grpc.server.service.GrpcService`, `net.devh.boot.grpc.client.inject.GrpcClient` | A |
| Quarkus | `io.quarkus.grpc.GrpcService`, `io.quarkus.grpc.GrpcClient` | A |
| Official `org.springframework.grpc` starter | Annotation names ⚠️ unconfirmed | A |

**Good news for matching:** both sides derive from the same `.proto`, so field numbers must
agree — the strongest join key of any protocol, per [ARCHITECTURE](ARCHITECTURE.md) DR-5.

### SOAP
Deferred by decision. `@WebService`/`@WebMethod` would be Tier A for the endpoints; WSDL
reading is a separate tier-2 artifact, and without it SOAP link matching falls back to
structural comparison.

### Avro
| Form | Exact | Tier |
|---|---|---|
| Generated classes | Extend `org.apache.avro.specific.SpecificRecordBase`, carry a **`public static final Schema SCHEMA$`** | **B** |
| Confluent serializers | `io.confluent.kafka.serializers.KafkaAvroSerializer`/`Deserializer` ⚠️ | B |
| Subject naming | Default `TopicNameStrategy`: subject = `<topic>-key` / `<topic>-value` | B |

**`SCHEMA$` is the important find.** The schema is retrievable from the compiled class,
exactly as protobuf's descriptor is — so the "read the schema out of generated code"
approach behind [ARCHITECTURE](ARCHITECTURE.md) DR-4 generalises to a second format.

---

## 7. The strategic risk: boundaries are leaving the code

The clearest pattern across all this research, and the thing most likely to limit Sextant's
value over time.

**Modern frameworks are moving topic and destination names out of annotations and into
configuration**, leaving only an opaque channel name in the code:

| Framework | In the code | Where the destination actually lives |
|---|---|---|
| Spring Cloud Stream | a `Consumer<T>` bean named `handleOrder` | `spring.cloud.stream.bindings.handleOrder-in-0.destination` |
| Quarkus / SmallRye | `@Incoming("orders")` | `mp.messaging.incoming.orders.topic` |
| MicroProfile REST Client | `@RegisterRestClient(configKey="orders")` | `orders/mp-rest/url` |

An annotation-only reader sees `handleOrder-in-0` and learns nothing. **The join between
code and configuration is not an optimisation for these frameworks — it is the only path
to the answer.**

Sextant is better placed for this than most tools, because configuration resolution is
already a first-class pass and endpoints already carry *expressions* rather than values.
But no catalog style expresses "the destination is a property key derived from this bean's
name", and that is a genuine gap in [D02](components/D02-catalog-schema.md), not a missing
catalog file.

The same drift shows in HTTP: WebFlux functional routing and every modern client are
builder chains rather than annotations. **The annotation-driven engine covers the past
well and the future progressively less well.**

---

## 8. What this implies

Three conclusions, in the order they matter.

**Tier A is large, cheap, and immediately valuable.** `@RequestMapping` with a `method`
attribute, `path` as an alias, Micronaut, Quarkus/JAX-RS, `@KafkaListener`, `@JmsListener`,
`@SqsListener` — all of these are YAML files against an engine that exists and is proven.
That is a great deal of real-world reach for no new machinery.

**Chain reconstruction is the single highest-leverage capability.** It gates: all modern
HTTP clients, WebFlux functional routing, the AWS SDK, the Pub/Sub client library, and
plain Kafka producers. Almost every Tier B entry above traces back to it.

**Two schema questions should be settled before more catalogs are written**, because both
are shapes the format cannot currently express: a match whose direction depends on context
rather than on the catalog (`@HttpExchange`), and a destination that lives in configuration
under a key derived from code (§7).

---

## Verification status

Researched August 2026 against primary sources — Spring, Micronaut, Quarkus, Apache Kafka,
AWS, Google Cloud, gRPC and Avro documentation. Items marked ⚠️ rest on secondary sources
or could not be confirmed, and **must be checked against the library's own javadoc or
source before entering a catalog**. A wrong annotation name does not fail loudly; it
silently matches nothing, which is exactly how petclinic returned zero endpoints.
