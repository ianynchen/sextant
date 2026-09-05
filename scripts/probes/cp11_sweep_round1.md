# CP-11 — the four framework rules the round-1 sweep fix pass mirrors

**Question.** `docs/principles-sweep-2026-09-05.md` records four Class A
Criticals whose encoded rule was taken from documentation, from a checkpoint
note, or from memory. DR-6 says mirror what the framework actually does, and
GUIDELINES §8.1 says measure it before building on it. So, for each: **what does
the framework's own bytecode say?**

| finding | the rule that was encoded | what this probe asks |
|---|---|---|
| `A-C2` | `okhttp.yml` seeds `http_method: GET` at the chain root and declares six verb steps | which methods of `okhttp3.Request$Builder` set the verb — ALL of them, because an uncovered one leaves the seeded GET standing |
| `A-C7` | `spring-web`/`spring-mvc`/`spring-graphql` gate on string equality against `org.springframework.stereotype.Controller` | what `RequestMappingHandlerMapping.isHandler` actually executes, per Spring minor |
| `A-C1` | `jakarta-websocket.yml` mints an inbound endpoint from a lone `@OnMessage` | which artifact declares `@OnMessage`, `@ClientEndpoint` and `@ServerEndpoint`, and what each targets |
| `A-C1` | `spring-stomp.yml` declares no type-level gate at all | what Spring STOMP's own handler test is |
| `A-C1` | `spring-http-interface.yml` declares neither a type gate nor `declared_on` | whether an `@HttpExchange` client has to be an interface |
| `A-C6` | `retrofit.yml` declares no `declared_on`, so a `@GET` method on a CLASS derives an outbound row | what `Retrofit.create` does when handed a non-interface |

The questions are worth a probe because of the failure mode rather than the
likelihood. Each of the four is *plausible and wrong*: an incomplete verb-setter
list publishes a confidently wrong verb, a literal annotation compare deletes a
whole controller's surface, a method-target annotation with no type gate invents
an address on a class that dials OUT, and a missing `declared_on` publishes an
outbound dependency nobody has.

**Version scope (§5.4).** Read against **okhttp 4.12.0, retrofit 2.11.0,
jakarta.websocket-api 2.2.0, jakarta.websocket-client-api 2.2.0,
spring-aop 6.1.6, spring-messaging 6.1.6, spring-web 6.1.6 and
spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9**. Four Spring minors rather than
one because `A-C7`'s whole claim is that the handler predicate is stable and the
catalogs' literal compare is not — a verdict from a single minor could not say
that. Every other row is evidence about the one artifact named beside it and no
other. Widening the scope means adding a coordinate to `ARTIFACTS` in
`scripts/probes/cp11_sweep_round1/run.sh` and re-running, never assuming.

**Retrofit is the one stated assumption.** The retrofit jar writes no version
into its manifest, ships no `pom.properties`, and declares no version constant,
so there is nothing in the archive to read; its column is labelled `assumed` by
the run itself and is the resolved coordinate. Every other column is the
artifact's own answer.

**How to run.** `bash scripts/probes/cp11_sweep_round1/run.sh`. It resolves each
artifact above through Maven (network on the first run only, cached in `~/.m2`
afterwards), reads each jar's self-reported version out of the archive it
opened, and asks `javap` the four questions. It ends by printing the two tables
below. Needs a JDK and Maven. Not a test: nothing in the suite runs it, and
NFR-1's no-network rule governs the suite rather than evidence gathering.

`tests/architecture/test_sweep_round1_framework_rules.py` is the offline half.
It pins the shipped catalogs and engines against the table below, so a rule
edited without re-running this harness fails the suite rather than going quiet.

## Expectation table

| # | Under test | Expected |
|---|---|---|
| 1 | `okhttp3.Request$Builder`'s verb setters | every one has a declared step in `okhttp.yml` |
| 2 | `RequestMappingHandlerMapping.isHandler`, per Spring minor | one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call, identical across minors |
| 3 | `jakarta.websocket.OnMessage` | `@Target(METHOD)`, declared by the CLIENT api jar — so it cannot mint a served endpoint alone |
| 4 | `retrofit2.Retrofit.validateServiceInterface` | an `isInterface` test guarding a thrown `IllegalArgumentException` |
| 5 | `SimpAnnotationMethodMessageHandler.isHandler` | the SAME predicate as row 2 — which is what makes a `@Controller` gate on `spring-stomp.yml` a mirror rather than an invention |
| 6 | `HttpServiceProxyFactory.createClient`, and `AdvisedSupport.addInterface` two hops below it | the client type reaches Spring AOP's `ProxyFactory`, which asserts `isInterface` |

## Observations

Verbatim from `run.sh`'s generated tables (`probe.py` prints them; nothing here
is typed by hand). **Every column header of the first table is a version the
JAR itself reported** — out of the manifest's `Implementation-Version`, or, for
OkHttp, the `ConstantValue` of `okhttp3.OkHttp.VERSION` — and **not the version
the coordinate list asked for**. `probe.py` reads the value out of the archive
it opened and ABORTS the whole run when it disagrees with the coordinate that
resolved the jar, rather than filling a mislabelled column; that is CP-5's
failure, which printed a version it believed beside output from a version it had
not run. The one column the run could not read that way is retrofit's, and the
row beneath the headers says `assumed` for it rather than `yes`.

| what the run read | 2.11.0 | 2.2.0 | 4.12.0 | 6.1.6 | 6.2.15 | 7.0.2 | 7.0.9 |
|---|---|---|---|---|---|---|---|
| artifacts reporting this version | retrofit | jakarta.websocket-api, jakarta.websocket-client-api | okhttp | spring-aop, spring-messaging, spring-web, spring-webmvc | spring-webmvc | spring-webmvc | spring-webmvc |
| identity read from the archive itself | assumed | yes | yes | yes | yes | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | okhttp `Request$Builder` verb setters | `okhttp` | 4.12.0 | `delete(), delete(Lokhttp3/RequestBody;), get(), head(), method(Ljava/lang/String;Lokhttp3/RequestBody;), patch(Lokhttp3/RequestBody;), post(Lokhttp3/RequestBody;), put(Lokhttp3/RequestBody;)` |
| 2a | Spring MVC `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 6.1.6 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 2b | Spring MVC `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 6.2.15 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 2c | Spring MVC `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 7.0.2 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 2d | Spring MVC `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 7.0.9 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 3 | jakarta.websocket annotation homes and targets | `jakarta.websocket-api+jakarta.websocket-client-api` | 2.2.0 | `OnMessage in jakarta.websocket-client-api @Target(METHOD); ClientEndpoint in jakarta.websocket-client-api @Target(TYPE); ServerEndpoint in jakarta.websocket-api @Target(TYPE)` |
| 4 | `Retrofit.create`'s interface guard | `retrofit` | 2.11.0 | `aload_1 ; invokevirtual Method java/lang/Class.isInterface:()Z ; ifne ; new class java/lang/IllegalArgumentException ; dup ; ldc String API declarations must be interfaces.` |
| 5 | Spring STOMP `SimpAnnotationMethodMessageHandler.isHandler` | `spring-messaging` | 6.1.6 | `aload_1 ; ldc_w class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 6a | `@HttpExchange` client proxying, and its interface assertion | `spring-web` | 6.1.6 | `invokestatic Method org/springframework/aop/framework/ProxyFactory.getProxy:(Ljava/lang/Class;Lorg/aopalliance/intercept/Interceptor;)Ljava/lang/Object;` |
| 6b | `@HttpExchange` client proxying, and its interface assertion | `spring-aop` | 6.1.6 | `aload_1 ; ldc String Interface must not be null ; invokestatic Method org/springframework/util/Assert.notNull:(Ljava/lang/Object;Ljava/lang/String;)V ; aload_1 ; invokevirtual Method java/lang/Class.isInterface:()Z ; ifne ; new class java/lang/IllegalArgumentException` |
