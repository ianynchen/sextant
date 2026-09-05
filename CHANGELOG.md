# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/) (GUIDELINES §5).

Nothing has been released yet: `0.1.0` is the working version and the
version-bump gate has not opened, so everything below sits under Unreleased.
This file starts at Phase 2O — earlier phases are recorded in
`docs/superpowers/plans/` and `docs/superpowers/specs/`, and backfilling them
here would restate those documents rather than add anything.

## [Unreleased]

### Added

- **CP-11: the four framework rules the principles-sweep fix pass mirrors are measured**
  (`scripts/probes/cp11_sweep_round1.md`). Each of `A-C2`, `A-C7`, `A-C1` and `A-C6` encoded a
  framework rule taken from documentation, a checkpoint note or memory, and each was plausible
  and wrong. The committed harness resolves each artifact through Maven, reads every jar's
  self-reported version out of the archive it opened — aborting rather than filling a
  mislabelled column — and asks `javap` four questions: OkHttp's complete `Request.Builder`
  verb-setter set, `RequestMappingHandlerMapping.isHandler`'s body across four Spring minors,
  which jakarta.websocket artifact declares which annotation and what each targets, and what
  `Retrofit.create` does with a non-interface. `tests/architecture/
  test_sweep_round1_framework_rules.py` is the offline half and pins the shipped catalogs
  against the generated table.

- **CP-10: every catalog `descriptor:` is now pinned to bytecode somebody read**
  (`scripts/probes/cp10_catalog_descriptors.md`, descriptor sweep R7). Load-time validation
  refuses a `descriptor` that is not a string opening with `(`, and that is all it can do: a
  wrong return type, a misspelled package or a stale erasure is well-formed and WRONG — it
  claims its candidate set in `_matching_method` and every overload of that name then derives
  nothing, with no error, no COVERAGE row, and every absence-asserting test still passing.
  The committed harness resolves each artifact through Maven, reads every `descriptor:` out
  of the shipped catalogs, indexes class → jar off the archives it opened, and asks
  `javap -p -s` whether the owner — or a superclass on the same classpath, which is what
  `SqsTemplate`'s inherited `send` needs — declares that exact erased descriptor. Each
  column is the version the JAR reported about itself, and a jar disagreeing with the
  coordinate that resolved it ABORTS the run (§5.4). `tests/architecture/test_catalog_descriptors.py`
  is the offline half: it pins the shipped catalogs against the generated table in both
  directions and fails on any verdict other than `declared`, so a descriptor added without
  re-running the harness fails the suite rather than going quiet.
- **Servlets: the oldest HTTP surface on the platform derives, under both package
  spellings** (2O design §3b, Task 7b). A new `supertype_dispatch` engine style
  (`jakarta-servlet.yml` and `javax-servlet.yml`) reads three pieces of evidence jointly —
  a TYPE-level `@WebServlet` for the address, `HttpServlet` for the dispatch contract, and
  the `doXxx` methods the class overrides for the verbs — none of which any shipped style
  could join: an annotation-driven derivation joins METHOD symbols and mints no row for a
  type-level annotation, and `supertype_derived`'s match requires a supertype whose own
  facts are in the module, which a container's abstract base never is. Every `urlPatterns`
  entry is its own endpoint; `value` is its alias, and a declaration writing BOTH derives
  nothing, because that is a deployment the container refuses and either value would then
  be a fabricated address. The member selector matches a name AND its parameter types in
  order, because that is how the language identifies a method (GUIDELINES §8.1):
  `doGet(String, HttpServletResponse)` overrides nothing and derives nothing, where a
  name-keyed selector would have published an address the container answers 405 to.
- **CP-9, measured live on three container majors** (`scripts/probes/cp9_servlet_shapes.md`,
  Apache Tomcat 10.1.50, 11.0.24 and 9.0.121, each column identified by the container the
  process itself reported). Its harness is committed beside it, deploys a real webapp so the
  CONTAINER's own annotation scan is what registers each servlet, and runs the committed
  extractor over the same build to record what actually reaches the fact stream. The
  questions the design left open are answered by measurement: **HEAD, OPTIONS and TRACE ARE
  served implicitly from `doGet`** and are deliberately NOT derived (the code serving them
  is in a container jar nothing scans, so the row would carry either no handler or a
  handler that does not serve that verb — the same ruling Task 6 made for Data REST); **an
  explicitly overridden `doTrace` IS dispatched to**, 200 over a connector that permits the
  method, so it is in the verb map with `allowTrace` recorded as a stated dependency rather
  than treated as proof the address is unserved; **the `javax.servlet` spelling behaves
  identically**, all 33 rows, which is why a second catalog ships instead of a stated
  boundary; and **a `protected` handler's recorded visibility is `other`, not
  `protected`**, so the style reads no visibility at all — an override may never narrow
  visibility, which makes the check both impossible and unnecessary.
- A class overriding `service()` derives **nothing**, and so does a `GenericServlet`
  subclass: the first replaces the verb dispatch itself and serves every verb alike
  (measured), so the verb map would publish a wrong verb set rather than a partial one;
  the second declares no HTTP verb semantics at all.
- **The one shape these catalogs over-report is stated and measured**: a module whose
  `WEB-INF/web.xml` declares `metadata-complete="true"` serves none of its annotated
  servlets — 404 on all three containers, same classes, one descriptor — and nothing in the
  pipeline reads a deployment descriptor, so every row is derived anyway. A COVERAGE
  boundary row in the over-report direction, closed by a descriptor reader.

- **The API nobody wrote a controller for: Spring Data REST routes derive** (2O design §2,
  Task 6). A new `derived_resource` engine style (`spring-data-rest.yml`) derives the CRUD
  route table from a repository INTERFACE — six routes per exposed repository plus one
  `/search/{query}` per query method — in a module that contains no controller, no mapping
  annotation and no string that is a URL. Every rule was verified against a live Boot 4.0.1
  / spring-data-rest 5.0.1 application (`scripts/probes/cp2_data_rest.md`): which item
  routes exist follows which CRUD contract is extended (a `PagingAndSortingRepository`-only
  repository serves a collection GET and nothing else), `path=` overrides the derived path,
  `exported = false` removes the repository, `@RestResource` renames or removes a search
  route, and which repositories are exposed at all follows
  `spring.data.rest.detection-strategy` — whose default exposes PUBLIC repositories only.
- **The dependency gate is real** (ruling R9). `detect.coordinates` was declared by every
  shipped catalog and read by nothing; it is now on the `Catalog` model and gates the one
  style whose framework rule is conditional on the library being present. The coordinates a
  module's build declares reach the workspace as D00 §5's `module` fact —
  constructed for the first time, from both detectors (Gradle's resolved compile classpath,
  Maven's direct POM declarations). A gated catalog whose question cannot be answered is
  reported SKIPPED with its reason, never derived and never silently omitted.
- **`domain/pluralize.py`** — a port of Evo Inflector's rule set, pinned by a differential
  run against the real library over every word in `/usr/share/dict/words`.
  `spring-data-rest-core` depends on that library non-optionally, so a working Data REST
  application always pluralizes its collection paths. A ported rule set is a derivative
  work, so Apache-2.0 §4's attribution travels with it:
  `src/sextant/domain/LICENSE-evo-inflector` carries the origin and the licence in full,
  named by the module docstring and by README's Dependencies section.
- **D02's `default_produces` is implemented** after being specified-not-used since 2E: read
  as a top-level catalog key, filling `produces` for rows no mapping declares a media type
  for. `application/hal+json → json` joins the shared `media_formats` table.
- A `static` helper declared on a Spring Data repository derives **no** `/search/` route:
  it is bound to the type, never to the repository's instance contract, so the framework
  serves nothing for it. The `method_visibility` query now projects the `static` modifier
  the extractor already emitted. A `default` method is still over-reported — `ACC_ABSTRACT`
  is not recorded, so nothing in the facts tells one from an abstract method — and that is
  now a stated boundary in COVERAGE rather than an undeclared one.
- The `environment_divergence` pass re-applies the CAPABILITY gate as well as the
  dependency gate, so a catalog `derive_endpoints` skipped for a missing capability can no
  longer file a question about a route it derived nothing for.
- A gated catalog's SKIPPED reason now carries Maven's direct-declarations-only caveat in
  the message itself, so "this module's build declares none of them" cannot be read as a
  confident negative for a starter inherited through a parent or a BOM. A module fact
  carrying no `dependency_coordinates` key at all degrades to that same SKIPPED path
  instead of aborting the resolve.
- **A new open-question kind is written**: `environment_divergence`, filed when
  `spring.data.rest.base-path` differs between environments — the derived rows then carry
  the configuration expression as their prefix at `unresolved`, rather than one
  environment's URL.
- **gRPC's JVM bytecode surface derives** (2O design §1b/§1c, Task 5), closing FR-3's
  last open protocol on the JVM alongside Task 4's schema half. Two new, framework-neutral
  engine styles: `supertype_derived` matches any class extending a generated
  `<Service>ImplBase` (`grpc-java.yml`) and derives one inbound row per overridden RPC
  method, reading the service identity and each wire method name off the generated
  class's own identity-building call-site arguments (`ServiceDescriptor.newBuilder`,
  `MethodDescriptor.generateFullMethodName`) rather than a field value — D00 §5's
  `constant` fact kind has no producer in this codebase (ruling R11). `injected_client`
  matches a net.devh `@GrpcClient`-injected stub field (`grpc-net-devh.yml`) and derives
  one outbound, service-level row (`method` NULL), fenced by symbol name against a service
  this module implements locally. Both merge with Task 4's descriptor-derived rows on the
  identical wire identity where both exist — and the merged row keeps BOTH halves: the
  bytecode's handler symbol plus the descriptor's request contract, response contract and
  streaming word, carried across by `stamp_declared_response.sql` and its new sibling
  `stamp_declared_request.sql` rather than by an insert the identity guard rejects. An
  unreadable identity derives an honest `unresolved` row plus a `service_identity` open
  question, never a fabricated package — and `supertype_derived` matches ONLY where the
  supertype's own generated class makes one of the marker calls, so ordinary class
  inheritance derives no row and files no question at all. Where two wire method names
  collapse onto one candidate override neither is attributed, and an override no wire
  name reaches is filed as a question rather than dropped silently.
- **`@GrpcService` corroboration** (`grpc-spring.yml`, Spring gRPC and net.devh
  spellings): a new `corroborates` block on `annotation_driven`, plus a `gaps` entry
  point beside `supertype_derived`'s and `injected_client`'s. It derives NO endpoint rows
  — the annotation names no service — and files a `service_identity` question for any
  class it flags that no gRPC endpoint names as a handler, which is the published-stubs
  case that previously produced nothing at all.
- **Five messaging and annotation catalogs** (2O Task 7): `spring-rabbit.yml`
  (`@RabbitListener`, plus the class-level `@RabbitListener` + `@RabbitHandler` shape),
  `spring-pulsar.yml` (`@PulsarListener`), `spring-rabbit-template.yml`
  (`RabbitTemplate.convertAndSend`), `spring-sqs-legacy.yml` (both older `@SqsListener`
  packages, so all three generations of the annotation now ship) and `spring-actuator.yml`
  (`@Endpoint` + `@ReadOperation`/`@WriteOperation`/`@DeleteOperation`). Every annotation's
  attribute shape was read off the real class files with `javap`, and the Actuator address
  and verb rules were confirmed live against Boot 3.5.10 AND 4.1.1
  (`scripts/probes/cp5_actuator_paths.md`, harness committed beside it).
- **`address_arg_2` — a composite outbound destination** (`single_call`). AMQP's wire
  identity is the exchange AND the routing key, which the one-address contract could not
  express: a row now names a second capture and a catalog-declared `address_separator`
  renders the pair as `exchange/routingKey`. An overload with no exchange is the routing key
  alone, and an explicitly empty exchange renders as the routing key alone too, so the two
  spellings of one destination stay one identity. If either half cannot be read the row
  publishes NO address — half a composite identity is a different destination, not a partial
  answer.
- **`path_prefix` — a framework's constant base path** (`annotation_driven`). A catalog may
  declare a fixed prefix that no annotation carries; it joins the front of the type-level
  prefix under the same deduping seam. Refused at load without a `path_separator`, since the
  two halves would otherwise concatenate bare.

### Fixed

- **`A-C1` / `A-C6`: four catalogs derived from evidence the framework does not act on**
  (principles sweep §3.2). `jakarta-websocket` and `spring-stomp` declared no type-level gate at
  all, so a lone method annotation minted a declaration — and with no class-level annotation to
  prefix it, at the EMPTY address. Worst of them: a `@ClientEndpoint` class, one that dials OUT,
  carrying the `@OnMessage` callback was published as an INBOUND WebSocket endpoint, direction
  inverted and address invented in one row. `retrofit` and `spring-http-interface` declared no
  `declared_on`, so an exchange annotation on a concrete CLASS derived an outbound row for a
  client the framework would never create. All four gates are now measured rather than chosen
  (CP-11): `@OnMessage` is `@Target(METHOD)`, addressless, and ships in the CLIENT api jar, so
  `@ServerEndpoint` is what makes a class served; Spring STOMP's `isHandler` is byte for byte
  the `@Controller` predicate Spring MVC runs; `Retrofit.create` throws on a non-interface; and
  `HttpServiceProxyFactory` proxies through Spring AOP's `ProxyFactory`, which asserts
  `isInterface`. **Output changes for real modules**: a WebSocket client, a STOMP handler on a
  non-`@Controller` class, and an exchange annotation on a concrete class all stop deriving. The
  stated cost is on the two outbound catalogs — `declared_on: interface` also engages the SEI
  fence, so a module that ships a local implementation of its own Retrofit or `@HttpExchange`
  client loses that client's rows; recorded in COVERAGE §5.2. Two under-reports `A-C1` names are
  stated rather than closed: a `@ServerEndpoint` class whose only lifecycle method is
  `@OnOpen`/`@OnClose`, and Spring RSocket controllers, whose routing annotation
  `spring-stomp.yml` claims and whose derived output is unverified.

- **`A-C7`: a custom stereotype deleted its controller's entire HTTP surface** (principles sweep
  §3.2). `spring-web`, `spring-mvc` and `spring-graphql` gated on string equality against one
  annotation FQN over a type's own direct annotations. Spring's rule is
  `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` — a four-instruction body,
  measured identical across spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9 (CP-11 Q2) — and that
  predicate is meta-annotation aware, so a controller wearing a module-local `@MyApi` composed
  from `@RestController` matched nothing and every one of its endpoints was silently absent from
  the export. The type gate now seeds the same composition closure the method-level mapping
  annotations already used, so the composition it was always able to see reaches it. **Output
  changes for real modules**: a module with its own composed stereotype gains its whole
  controller surface. Two of the three divergences the sweep names stay OPEN on purpose and are
  stated in COVERAGE §5.1: a stereotype inherited from a superclass or an interface makes
  `isHandler` true, but `@Component` is not `@Inherited` and whether component scanning admits
  such a class is unmeasured — deriving on half a rule is what §8.1 rule 4 forbids.

- **`A-C4`: a class inherited from its superclass only when the superclass was generic**
  (principles sweep §3.2). The annotation-inheritance walk read the `supertype` fact, which the
  extractor emits only where the superclass carries type ARGUMENTS, so `class OrderController
  extends PrefixBase` had no superclass edge at all — and since an absent prefix composes as the
  empty string, the child published `/{id}` where the framework serves `/api/orders/{id}`. A
  confidently wrong address at `resolved`/`compiler`, reached by a route neither `path_fallback`
  nor `canonical_path` guards. The walk now reads capability 9.13's erased `superclass` field,
  written for every non-`Object` superclass. **Output changes for real modules**: controllers
  extending a non-generic base gain the prefix and the inherited mappings the framework serves.
  The same edge retires the bare-to-prefixed lookback the old one needed, so an abstract base
  that declares no method at all — one whose only purpose is to carry a type-level
  `@RequestMapping` — is reachable too (`A-M11`).

- **Mechanism 3: the empty-address guard was keyed on a formatting property** (principles sweep
  §4, §7.7). `derive_endpoints.sql` dropped a row with an empty address only when the catalog
  declared no `path_separator` — a property about how two halves of an address are JOINED, which
  says nothing about whether the empty address means anything. The result was that a broker
  catalog whose destinations have no slashes was protected and its structural twin on a
  slash-separated protocol was not, because declaring a separator to compose destinations
  switched the twin's own validity gate off in the same line. Seven shipped catalogs declared one
  and were all unguarded. The gate now asks whether anything in the row names an endpoint at all:
  an empty address ships only where a resolved `peer` names the service, and the one protocol for
  which the empty address is real — an inbound HTTP root route — has already been spelled `/` by
  the canonical-address gate before this runs. **Output changes for real modules**: a
  `websocket`- or outbound-HTTP-shaped annotation catalog that composed an empty address stops
  publishing that row (`A-C1`'s fabrication half); inbound HTTP root routes, named destinations
  and Feign clients calling their base address are all unaffected. `docs/COVERAGE.md`'s claim
  that an unlisted destination attribute "derives a resolved row with an empty path today" was
  already false before this change and is corrected with it.

- **`A-C5`: a module with no Spring Cloud Stream asserted four Kafka boundaries** (principles
  sweep §3.2). `config_join`'s candidate scan reads every declared method and keeps the ones
  returning `Function`/`Consumer`/`Supplier` — platform interfaces, not framework ones — and with
  no `spring.cloud.function.definition` present the framework's own default binds every
  candidate, so three ordinary utility methods on a plain class published four boundaries the
  module does not have. `config_join` joins `derived_resource` in `DEPENDENCY_GATED`: the two
  styles whose evidence names no framework are the two gated on the build declaring it, and
  `resolve/dependencies.py` now records that test applied to all eleven styles. **Output changes
  for real modules**: a module whose recorded coordinates do not name
  `org.springframework.cloud:spring-cloud-stream` derives no Stream bindings and is reported
  SKIPPED with its reason; the same applies to `spring-kafka-media`'s media stamps and
  `org.springframework.kafka:spring-kafka`. Under Maven only DIRECT declarations are recorded,
  so a module inheriting either through a parent or a starter is skipped — the skip message says
  so, and the rows it loses are a Stream binding set or a carried media decoration, never a row
  another engine derived. `fixtures/orders-service` gained the `spring-cloud-stream` dependency
  it had always been modelling and never declared.

- **`A-C2`: OkHttp's `.method("DELETE", body)` no longer publishes `GET`** (principles sweep
  §3.2). `okhttp3.Request$Builder`'s generic verb setter was not a declared step, so it passed
  through uncaptured (D02 §4) and the chain root's `http_method: GET` — OkHttp's real default
  for a bare builder — stood uncorrected: a module issuing DELETE was published as issuing GET
  at `resolved`/`compiler`, where nothing downstream can tell an asserted verb from an observed
  one. The `fluent` grammar now accepts `http_method: argN` beside the literal spelling, and
  `okhttp.yml` declares the step. A verb the scanner cannot read as a string literal derives
  `method: NULL` at `unresolved` — the honest gap the catalog's own comment claimed to be
  taking while publishing a guess. Rows change for any module using
  `Request.Builder.method(...)`: previously one `GET` row per such call, now the real verb, or
  an unresolved row where the verb is computed.

- **A client held by its INTERFACE derives nothing, and that is now written down** (descriptor
  sweep R8). A call site records the compile-time qualifying type javac emitted, and every
  `single_call` client catalog declares a single concrete `matches.owner` — so
  `SqsOperations`, `AmqpTemplate`, `JmsOperations`, `KafkaOperations`, `RestOperations`,
  `WebServiceOperations`, `PubSubOperations`, `org.apache.kafka.clients.consumer.Consumer` and
  `jakarta.jms.QueueSession`/`TopicSession` calls match nothing at all. The highest-risk case
  is `SqsTemplate.newSyncTemplate(...)`, which **returns `SqsOperations`** — the idiomatic
  construction misses entirely, and both `send` arities are inherited so nothing anchors them
  to the class. This is an owner problem a descriptor cannot fix, and making `matches.owner`
  multi-valued is engine work that was out of scope for the sweep; recorded as a
  `docs/COVERAGE.md` boundary with its falsifier rather than left silent (§8.1 rule 3). The
  descriptors themselves are identical through either type, so they carry over unchanged when
  it closes.
- **`spring-resttemplate.yml` converts wholesale: seven rows become twenty-six** (descriptor
  sweep R4). Its rows carried neither `arity` nor `descriptor`, which makes each of them a
  candidate at EVERY argument count — so adding one descriptor to one row would have claimed
  every argument count for that name and silenced every other overload of it, with no error
  path. A half-conversion of this file is strictly worse than none, which is why it is all at
  once. The file was benign as it stood and that is said plainly rather than dressed up: what
  closes here is the shape that produced the AMQP, JMS and SOAP fabrications, not a live
  defect. Every `getForObject`, `getForEntity`, `postForObject`, `postForEntity`, `put`,
  `delete` and `exchange` overload `RestTemplate` declares now has its own row with both
  `arity` and `descriptor`; the two `exchange(RequestEntity, …)` forms, whose position 0 is
  not a url, declare no captures at all and keep deriving exactly the honest empty row they
  derived before. No golden-fixture output moved.
- **`spring-websocket.yml` said varargs make a three-argument call; they do not** (descriptor
  sweep R6). The catalog, a COVERAGE bullet and three tests all asserted that a multi-path
  `.addHandler(h, "/a", "/b")` "is a THREE-argument call this row's own `arity: 2` does not
  match at all", and that the two-argument shape was unverified. Measured by compiling both
  calls against spring-websocket 6.1.6 and running the shipped extractor: varargs collapse
  into ONE argument, so one path and two paths alike record exactly two arguments with an
  `array` at position 1. The row has always matched the multi-path call. The real boundary is
  narrower and worse — `channel_of` resolves only a `kind: "string"` argument, so
  `channel_arg: 1` can never resolve a path for ANY call, and every registration derives one
  honest row with `path` NULL. Stated in the catalog and in `docs/COVERAGE.md` with its
  falsifier, and named as Task 13's to close by wiring capability 9.15's `elements` read. The
  row also gains the erased descriptor of the interface's one declared method. **Not fixed
  here**: the capture is engine work, and this is a catalog sweep.
- **`JmsTemplate` publishes through two more overloads than the catalog admitted** (descriptor
  sweep R5). `convertAndSend(Destination, Object)` is an ordinary destination-carrying call
  whose argument 0 is a `Queue`/`Topic` instance and therefore can never fabricate anything;
  it derived an honest path-NULL row until the arity-2 descriptor claimed the arity, and that
  was a regression rather than a boundary. It has its own row again.
  `convertAndSend(String, Object, MessagePostProcessor)` was never declared at ANY arity, so
  every such call derived nothing at all — a recall gap nothing recorded — and the destination
  it carries is genuinely at position 0 and genuinely readable. Both are recall with no
  fabrication risk. The file now documents its own remaining boundaries, which it did not,
  though it makes the same claim `spring-rabbit-template.yml` documents in full.
- **A row that meant several overloads is now several rows** (descriptor sweep R3). Five
  catalogs carried one `methods` row standing for two real overloads, which is the language's
  own rule missing rather than a simplification: `KafkaConsumer.subscribe(Collection)` and
  `(Pattern)`; `PubSubTemplate.publish(String, T)` and `(String, PubsubMessage)`;
  `SqsTemplate.send` at both arity 1 and arity 2; and the `Message` siblings of
  `KafkaTemplate.send(ProducerRecord)` and `ReplyingKafkaTemplate.sendAndReceive(ProducerRecord)`.
  Each is now one row per overload, each with its own descriptor. **A single descriptor would
  have been the wrong fix in every one of these**: it claims the arity, so the undeclared
  sibling goes silent. `kafka-consumer`'s `channel_via` resolver list splits with the row —
  `List.of`/`Arrays.asList`/`Collections.singletonList` to the `Collection` overload,
  `Pattern.compile` to the `Pattern` one — and the two `Message` rows declare no capture keys
  at all (`spring-sqs-template.yml`'s precedent), which preserves today's honest empty row
  rather than spending recall to close an ambiguity. Three catalog comments asserting a second
  row at the same arity "would never be reached" were true of arity matching and are false
  under descriptor matching; all three are corrected.
- **Every unique-overload `methods` row now names the overload it means** (descriptor sweep
  R2). A row matched on name and argument COUNT is matching on a rule Java does not have —
  the language identifies a method by name and parameter types in order (GUIDELINES §8.1's
  language rule) — and the rows below happened to be unambiguous only because their jars
  declare one overload at that arity today. `google-pubsub-client`, `jakarta-jms` (both
  rows), `kafka-clients`, `spring-rabbit-template`'s arity-1 row and `spring-ws-template`'s
  arity-1 and arity-3 rows each declare their own erased descriptor. Nothing derived changes:
  a unique overload's descriptor can only equal what a matching call carries. What changes is
  the release that adds a sibling — it derives NOTHING instead of having its own argument 0
  read as a destination or a payload. The comments that said a unique overload needs no
  descriptor are corrected, each with the condition that falsifies it.
- **A SOAP request PAYLOAD could be published as the SOAP service's address** (descriptor
  sweep R1, §8). The same overload collision Task 7 closed for AMQP and JMS was still live
  in `spring-ws-template.yml`: `WebServiceTemplate.marshalSendAndReceive` declares
  `(String uri, Object payload)` AND `(Object payload, WebServiceMessageCallback after)` at
  arity 2 (javap -p -s, spring-ws-core 4.1.4), and the shipped row read position 0 as the
  address for both. `marshalSendAndReceive("PAYLOAD", message -> {...})` binds the callback
  form — a lambda is not compatible with the other overload's `Object` parameter, so javac
  picks it unambiguously — and the message body was published whole as `peer`, the remote
  service the module calls, at `evidence: compiler`. Reproduced end-to-end before it was
  fixed. The arity-2 row now declares its own erased descriptor. The file's own comment
  asserted this collision "never publishes a wrong row" and also counted arity 3 into it;
  both claims were false and are corrected — arity 3 is the only three-argument overload in
  that jar. The claimed arity's cost, a callback-form call now deriving nothing, is a stated
  boundary in `docs/COVERAGE.md`.
- **A message PAYLOAD could be published as a wire destination** (2O Task 7 review,
  §8). `single_call` selected a `methods` row by name and ARITY only, and both
  `RabbitTemplate.convertAndSend` and `JmsTemplate.convertAndSend` overload on argument type
  at the arities the shipped catalogs declare — arity 2 as well as arity 3, which neither
  file admitted. A call passing a `MessagePostProcessor` therefore reached a row expecting a
  destination at that position, and a string-literal payload was published as an AMQP or JMS
  destination at `resolved`/`compiler`, indistinguishable from an observation. A `methods`
  row may now declare the overload's own erased JVM `descriptor`, compared verbatim against
  the call site's `target.descriptor`; both shipped catalogs declare one per
  address-carrying row. Once any row for a name and arity declares a descriptor that arity
  is CLAIMED — an unmatched call derives NOTHING rather than falling through to a
  descriptor-less sibling, which is the fabrication the key exists to stop. The cost is a
  stated under-report in `docs/COVERAGE.md`: the undeclared overloads, which used to derive
  an `unresolved` row, now derive none.
- **The Actuator catalog's rows are now stated as conditional on WEB EXPOSURE** (§8, 2O
  Task 7 review). `management.endpoints.web.exposure.include` is Boot's gate on whether a
  custom `@Endpoint` is served over HTTP at all, and its default is `health` alone: measured
  on Boot 3.5.10 and 4.1.1, `/actuator/probe` is a **404** under the default while
  `/actuator/health` is a 200. Nothing in Sextant reads the key, so under a module's own
  defaults every `/actuator/<id>` published at `resolved`/`compiler` is a URL nothing
  serves. No derivation changed; the over-report is now a stated boundary in
  `docs/COVERAGE.md`, in the catalog and in the probe verdict, together with
  `@Endpoint(defaultAccess = Access.NONE)`, the same conjunct in miniature.
- **An annotation-derived path carrying an expression is no longer published as an
  observation** (§8). Every such row was stamped `resolved`/`compiler` unconditionally, so a
  destination written as SpEL `#{…}` or a property `${…}` was published as though the
  characters of the expression were the address. It now publishes `unresolved` with the
  expression VERBATIM — uncanonicalized, and never resolved: the config ladder is a
  call-site mechanism this derivation does not invoke. `domain/paths.py` learned the `#{`
  notation beside the `${` it already refused to rewrite.
- **A declaration that composes an EMPTY name derives no row.** For a catalog whose address
  is an opaque name rather than a sequence of segments (no `path_separator`), an empty
  composition is not a destination — nothing subscribes to it and nothing publishes to it —
  so the row is dropped instead of published as an endpoint addressing nothing. Two real
  shapes reached it: a member-level handler annotation outside the class-level annotation
  that would have named its destination, and a listener declaring its destination only
  through nested annotations no catalog reads yet. Segmented addresses are untouched: an
  empty segmented address is the base address itself.

### Changed

- **Endpoint identity for INBOUND `http` is now the URL the framework serves**
  (2O design §8, checkpoint CP-1 confirmed live against Boot 4.0.1).
  `@RequestMapping("users")` and `@RequestMapping("/users")` were two endpoint
  identities and are one; every combine boundary carries exactly one `/`; a
  trailing slash stays DISTINCT, because Framework 6 removed trailing-slash
  matching. A `path` holding a whole address or a placeholder-bearing
  composition (`https://${billing.host}/orders`) is untouched, and GraphQL
  (field names) and websocket/STOMP (a shared protocol with handshake-path
  rows) are out of scope. **Client-side HTTP rows are out of scope too**: a
  client's slashless path resolves against its configured base address's own
  path while a leading separator is root-relative, so canonicalizing one would
  rewrite an address rather than normalize a spelling. The rule and its gate
  live in `sextant.domain.paths`.
- **Spring Cloud Stream's `rabbit` binder now derives `amqp`, not `jms`**
  (2O design §3a). The `jms` stopgap was chosen when D00 had no AMQP member;
  keeping it would leave a Stream producer and a `@RabbitListener` consumer on
  different protocols permanently, and DR-5 gates linking on protocol equality.
- **The format ladder's rung 5 reads the evidence its documentation always
  described** (2O design §7, checkpoint CP-6). A `json_default_markers` entry
  may now be a dependency coordinate (`{coordinate: "group:artifact"}`) as well
  as a package family, and a package family is matched against every fqn the
  module names rather than annotations alone. Boot auto-configures Jackson's
  converter from the jar's mere presence, so a module carrying it answers
  `json` at `narrowed` even with no annotation anywhere.

### Consequences of the identity migration — please read before upgrading

These four are the whole blast radius 2O design §8 names, and each is a
consequence of the same one change:

1. **Goldens moved.** Every recorded INBOUND HTTP path that omitted its
   leading separator now carries one. On this repository's own fixture that is
   no rows at all: every inbound route it declares already spelled its leading
   separator, and the two slashless declarations it has are client-side, which
   this change deliberately does not touch. A codebase with a slashless
   `@RequestMapping` will see those rows move.
2. **Curation and view overlays naming an old endpoint id are REJECTED WHOLE**
   by M01's existing rule — an overlay is validated as a unit, so one stale
   anchor rejects the file rather than silently dropping a claim. Re-anchor the
   overlay on the new id and re-apply.
3. **2N enrichment overlays anchored on old paths go STALE** and are dropped
   honestly at render (`stale_claims`) rather than rendered against a row they
   no longer name. Re-enriching is the documented remedy.
4. **`open_questions` snapshots re-derive** on the next analysis: the ledger is
   keyed on the wire identity, so a snapshot taken before this change names
   rows that no longer exist under those ids.
