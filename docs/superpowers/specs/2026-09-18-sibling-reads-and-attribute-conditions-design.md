# Sibling-annotation reads and rules conditional on an annotation attribute (register Groups B and C)

**Status:** design. Approved in conversation 2026-09-18, section by section; Approach 2 of
three ruled by the user. **Self-review against the frameworks' own jars and sources, the
JVM extractor's facts and the engine found five Major findings and three refuted claims;
each was ruled by the user on 2026-09-18 and is folded in below** (§0 lists them). Not yet
planned.
**Closes — Groups B and C of the register, four items plus one addition:** `quarkus-jaxrs`
(every JAX-RS resource derives nothing — no catalog exists), `jaxrs-sse`
(`@Produces(SERVER_SENT_EVENTS)` on a JAX-RS method is unread), `kafka-batch-generics`
(`@KafkaListener(batch = "true")` publishes the `List`, the wire carries the element),
`micronaut-jms-over-sqs` (a Micronaut JMS listener bound to the SQS connection factory
publishes `jms`, so it links with no SQS sender), and — added 2026-09-18, user rulings —
the same switch on `@JMSProducer`, which the register never named, and `mp-rest-client`
(MicroProfile REST Client: a `@RegisterRestClient` interface carrying JAX-RS annotations —
the outbound twin of the JAX-RS catalogs, on the same words).
**Rows it empties:** SSE, Kafka, SQS. REST inbound 9 → 8; REST outbound 2 → 1 (`apache-camel` stays).

Every factual claim below carries the command that produces it, or names the probe (§7)
that must record it before the key it forces is written. Claims marked **measured
2026-09-18** were verified during the self-review against the artifacts named; the plan's
probe files reproduce those measurements with the commands quoted. **A probe that
contradicts a section here changes the section, not the probe** (GUIDELINES §1.1).

**Standing requirement: nothing that works today may move.** Every key here is optional
and inert unless declared, so every shipped catalog derives byte-identically; §8 states the
proof, and the plan runs it before any engine work.

---

## 0. What the self-review found, and what was ruled

| # | Finding | Ruling |
|---|---|---|
| M2 | `sole_unannotated` disqualifies a parameter for **any** annotation (`contracts.py:268`); kotlinc's `@NotNull` reaches the facts (`retention: class`, `fixtures/orders-service/.sextant/facts/.../KotlinMvcRoutes.jsonl`), so every Kotlin JAX-RS body and every `@Valid` Java body publishes no contract | **A** — a new fallback word whose "unbound" is measured against the framework's own binding annotations (§4) |
| M4 | Quarkus REST binds an unannotated parameter **by name** to a path variable, and treats a parameter whose **class** carries bound fields as a container, not a body (`EndpointIndexer.java:1380-1413`, `ResteasyReactiveParameterContainerScanner.java:19-31`) | **A′** — two implicit-binding words on the same fallback, declared by `quarkus-rest.yml` only (§4) |
| M1 | `@RestStreamElementType` with no `@Produces` **makes the response SSE** (`EndpointIndexer.java:719-723`); the draft read its value as `produces` and would have classified a JSON stream as REST | **A** — a third `protocol_hint` evidence kind, `hint_annotations` (presence), §3c; the element type as per-event *format* is a named follow-up, not in this group |
| M3 | All three implementations make a class implementing a `@Path` interface a root resource, and JAX-RS §3.6 inherits **all** of an interface method's annotations; the engine inherits the mapping and the type-level prefix but not the **sibling** `@Path`/`@Produces`, so an inherited `@GET @Path("/{id}")` derives the prefix alone — a wrong address | **A** — the inheritance walk synthesizes the catalog's declared siblings with the mapping, all-or-nothing (§3b, word 3) |
| M5 | Spring tests `batch` with `Boolean.parseBoolean` after `hasText`, case-insensitively, with no placeholder resolution (`KafkaListenerAnnotationBeanPostProcessor`, 3.1.4 and 4.1.1); exact `equals: "true"` misses `"TRUE"` | **B** — a second closed comparator, `parses_true`, defined as exactly that predicate (§2) |
| R1 | Quarkus REST does **not** relax the class-level `@Path` for servers — `scanResources` collects root resources from `@Path` on classes and `@Path` interfaces only; the "no `@Path` whatsoever" rule (`ResteasyReactiveScanner.java:344`) is for **client** interfaces | corrected: `quarkus-rest.yml` keeps the gate |
| R2 | `@JMSListener`/`@JMSProducer` carry **only `value()`** at 4.2.0 — no `connectionFactory` attribute; `value` is the `ConnectionFactory` bean name (`getRequiredValue(String.class)` → `Qualifiers.byName`) | corrected: `name: value`; COVERAGE line 3222's `connectionFactory = …` wording is corrected with it |
| R3 | `request_body.annotation` cannot be absent today (`contracts.py:260`) | corrected: the new fallback word makes `annotation` optional |
| + | `mp-rest-client` (REST outbound, register row) is the same declaration shape as `jakarta-jaxrs.yml` on an **interface**, outbound — measured 2026-09-18 on `microprofile-rest-client-api` 4.0: `@RegisterRestClient` is `@Target(TYPE)`, `RUNTIME`, `baseUri()`/`configKey()` both default `""` | **joins the group** (user ruling): §3f, one catalog task |

---

## 1. What is wrong today, in six places

1. **No JAX-RS catalog exists.** `ls src/sextant/catalogs | grep -i 'rs\|jaxrs'` returns
   nothing. `fixtures/orders-spring7/src/main/java/com/acme/jaxrs/OrderResource.java` has
   carried five resource methods and one SSE method since the completeness design, and
   `tests/e2e/test_rest_inbound_delivered.py::test_a_jaxrs_resource_derives_every_operation`
   and `::test_a_jaxrs_sse_endpoint_is_classified_as_sse` are strict-xfail. Every Quarkus,
   Helidon, Jersey and RESTEasy module derives nothing.

   The register said "engine work" on 2026-09-11. Most of it has since landed for another
   framework: `path_from_siblings` (`OI-35`, commit `b87d625`, 2026-09-06 — `git log
   --format='%h %ad' --date=short -S'path_from_siblings' --
   src/sextant/catalogs/microprofile-graphql.yml`) reads a method's path off a sibling
   annotation, and D02 names JAX-RS as the case `prefix_annotation` exists for. What is
   missing: the **media** siblings (`@Produces`/`@Consumes`) and the class-level media
   default on a type-level sibling.

2. **SSE from JAX-RS is one YAML block away** once `produces` is filled — COVERAGE §5.6:
   *"a JAX-RS catalog would carry its own `protocol_hint` block … One YAML entry, no code."*

3. **The body fallback is stricter than any framework.** `contracts.py:264-274` marks a
   parameter as the body only when it carries **no annotation at all**. JAX-RS's rule
   (§3.3.2.1) is "the one parameter carrying none of *JAX-RS's* parameter annotations";
   Quarkus's (`EndpointIndexer.java:1380-1413`) adds three implicit bindings. Measured
   2026-09-18: the extractor records kotlinc's `@org.jetbrains.annotations.NotNull` on every
   non-null parameter (`grep -o '"retention":"[a-z]*"' fixtures/orders-service/.sextant/facts/
   com/acme/orders/mvcroutes/KotlinMvcRoutes.jsonl | sort | uniq -c` → `class` rows present).
   So under the shipped rule every Kotlin JAX-RS body and every `@Valid Order order` publishes
   **no request contract** — an empty contract at `resolved`, which nothing flags. JAX-RS has
   no body-marker annotation, so this fallback is its only body rule. Latent today for the
   Feign and Micronaut catalogs that declare `fallback: sole_unannotated` (logged, §6).

4. **A batch listener's request shape is the container, not the wire.**
   `fixtures/orders-service/.../OrderEventsListener.java:32-34` declares
   `@KafkaListener(topics = "order-batches") onBatch(List<OrderEvent>)` — a **record**
   listener taking a list, for which `tests/application/test_pipeline.py::
   test_a_batch_listeners_request_shape_is_an_array` correctly asserts `wire_type: array`:
   Spring's converter deserialises one record's JSON array into that parameter. A listener
   declaring `batch = "true"` takes the same `List<OrderEvent>` and receives one element per
   **record** — the wire payload is `OrderEvent`, and `List` is the container's envelope.
   `wrappers` (D02 §2a) are global by type and unconditional, so they cannot say it.

5. **JMS over SQS reads as `jms`.** COVERAGE §5 SQS line 3222. The producer side
   (`micronaut-jms-producer.yml`, `@JMSProducer`) has the identical attribute and gap and was
   never registered.

6. **Inherited resources lose their siblings.** `effective_annotations.py::inherited_rows_over`
   synthesizes onto an implementor the mapping annotation of each inherited method and the
   type-level prefix; it does not synthesize the other annotations of the inherited method.
   For Spring that is complete (the path lives inside `@GetMapping`); for JAX-RS the path and
   media are siblings, so an interface's `@GET @Path("/{id}")` would derive the class prefix
   alone on the implementor. Measured 2026-09-18 that all three implementations accept the
   interface form: Jersey `ModelHelper.getAnnotatedResourceClass` and RESTEasy
   `AnnotationResolver.getClassWithAnnotation` both walk class → interfaces → superclass
   (`javap -c -p` on jersey-server 4.0.0, resteasy-core 6.2.12.Final); Quarkus
   `ResteasyReactiveScanner.java:309-316` registers every non-abstract implementor of a
   `@Path` interface.

---

## 2. The one condition shape, declared once (Approach 2)

Items 4 and 5 are both *a rule that holds only when an annotation attribute has a value*.
One closed condition serves both — the word D02 §2c's own `resolves` sketch already names:

```yaml
when:
  annotation_arg:
    annotation: <fqn>        # required — which annotation, never "the matched one"
    name: <attribute>        # one attribute name, or a list of aliases, first present wins
    equals: <string>         # exact comparison of the attribute's string form …
    # — or —
    parses_true: true        # … or Java's Boolean.parseBoolean after StringUtils.hasText (M5)
```

- **Read on the declaration, else on its enclosing type.** The engine looks for
  `annotation` among the annotation rows targeting the owner symbol; absent there, among
  those targeting the owner's enclosing type (the `#`-delimited prefix of the identifier,
  D00 §5). One shape serves `@KafkaListener(batch)` on a method and `@JMSListener(value)` on
  a class — the same two-level read `prefix_annotation` already makes.
- **`annotation` is required.** Naming the fqn makes the condition self-contained, so a
  `wrappers` entry — attached to no mapping annotation — can carry one.
- **`name` is a scalar or an alias list**, read like `path_from`: first present wins. The
  list form exists for an aliased attribute (only the alias the author typed is in the
  bytecode); neither consumer in this group needs it (§5b, R2), so it ships as the
  `path_from` precedent, not as a new rule.
- **Exactly one comparator, `equals` or `parses_true`.** `equals` compares the attribute's
  string form; an array attribute matches if any element equals. `parses_true` is exactly
  Spring's predicate, measured on two versions (§7 P3): true when the attribute has text
  and `Boolean.parseBoolean` of it is true — so `"true"`, `"TRUE"`, `"True"` match and `""`,
  `"false"`, `"${listener.batch}"` do not. It is a separate word rather than a
  case-insensitive `equals` because §5b compares a **bean name**, and Micronaut's
  `Qualifiers.byName` is case-sensitive: `SqsJmsConnectionFactory` is a different bean.
  A third comparator is a further measurement and re-triggers §13.8.
- **The vocabulary is CLOSED** (NFR-5): `when` naming anything but `annotation_arg`, an
  `annotation_arg` with a key outside these four, both comparators, or neither, is
  **refused by name** at catalog load — in the engine, where `unless` and `resolves.when` are
  checked (`annotation_driven.py::_validate_unless`, `::_direction_rule`), never read as
  "never fires".

Two consumers, §5a and §5b. `resolves:` is untouched: it keeps refusing any key but
`direction` and any second rule. Approach 3 — building `resolves.protocol`/`resolves.format`
out as D02 sketched — was refused: no open register item consumes it, and D02 §2c itself
defers the list semantics "until the semantics is built".

---

## 3. Group B — JAX-RS in three catalogs and three engine words

### 3a. Three catalogs, one style

| Catalog | `detect.coordinates` | Why separate |
|---|---|---|
| `jakarta-jaxrs.yml` | `jakarta.ws.rs:jakarta.ws.rs-api` (3.x, 4.x) | The spec as written, `jakarta.*` |
| `javax-jaxrs.yml` | `javax.ws.rs:javax.ws.rs-api` (2.1.x); P1 settles whether `jakarta.ws.rs:jakarta.ws.rs-api:2.1.6` (Jakarta EE 8, still `javax`-packaged) is listed too | Same rules, `javax.*` fqns — the `javax-jms.yml`/`jakarta-jms.yml` split |
| `quarkus-rest.yml` | `io.quarkus:quarkus-rest`, and `io.quarkus:quarkus-resteasy-reactive` (its name through 3.15.x; both artifacts exist on Central, measured 2026-09-18 via `maven-metadata.xml`; P2 records the relocation version) | Quarkus REST adds rules the spec does not have (§3c): SSE by element annotation, two implicit body bindings, Vert.x context types. Same source under Jersey and under Quarkus derives differently, and each catalog says only what its framework does (DR-6) |

Two catalogs owning the same HTTP rows in one module is the `spring-web.yml`/`spring-mvc.yml`
precedent: identical identities meet the insert-if-absent guard and one row survives — **where
the two catalogs' rules agree wherever they overlap.** `jakarta-jaxrs.yml` and
`quarkus-rest.yml` do not (their `request_body` rules genuinely differ), so `jakarta-jaxrs.yml`
and `javax-jaxrs.yml` instead declare `detect.superseded_by` naming `quarkus-rest.yml`'s own
coordinates and are SKIPPED outright on a module that declares one — the framework's own fact
that Quarkus REST IS the JAX-RS implementation there — rather than run and risk winning a
filename tie-break they should not be in (amended in execution, Task 10 fix round 1; D02's
`detect.superseded_by` entry has the mechanism). `type_annotation` and `prefix_annotation`
naming the same fqn is the `jakarta-websocket.yml` and `micronaut-http.yml` precedent.

The plain catalog. Every key exists today except the three marked new (§3b) and the body
rule (§4):

```yaml
id: jakarta-jaxrs
style: annotation_driven
protocol: http
direction: inbound
detect: { coordinates: ["jakarta.ws.rs:jakarta.ws.rs-api"] }
requires: [annotation_args, typed_signatures]
matches:
  type_annotation: jakarta.ws.rs.Path        # JAX-RS §3.1: a root resource class is one annotated @Path —
                                             # on itself, or on an interface/superclass (§3b word 3)
  declared_on: class                         # a @Path INTERFACE mints no inbound row of its own — it is a
                                             # client (§3f) or a contract an implementor inherits (word 3);
                                             # the jakarta-jws.yml / jakarta-jws-client.yml partition
  request_body:                              # §4 — the new fallback word; no body-marker annotation exists
    fallback: sole_unbound
    bound_by: [jakarta.ws.rs.PathParam, jakarta.ws.rs.QueryParam, jakarta.ws.rs.HeaderParam,
               jakarta.ws.rs.CookieParam, jakarta.ws.rs.FormParam, jakarta.ws.rs.MatrixParam,
               jakarta.ws.rs.BeanParam, jakarta.ws.rs.DefaultValue, jakarta.ws.rs.core.Context,
               jakarta.ws.rs.container.Suspended]
    excludes: [jakarta.ws.rs.sse.SseEventSink, jakarta.ws.rs.sse.Sse, jakarta.ws.rs.core.UriInfo,
               jakarta.ws.rs.core.HttpHeaders, jakarta.ws.rs.core.Request,
               jakarta.ws.rs.core.SecurityContext, jakarta.ws.rs.ext.Providers,
               jakarta.ws.rs.container.ResourceContext, jakarta.ws.rs.core.Configuration,
               jakarta.ws.rs.core.Application]          # P1 (d): the spec's @Context-injectable types
  mapping:
    prefix_annotation: jakarta.ws.rs.Path
    prefix_from: [value]
    path_separator: "/"
    path_from: []                            # a verb annotation declares no attributes (measured, §7 P1 a)
    path_from_siblings: [{ annotation: jakarta.ws.rs.Path, arg: value }]
    produces_from_siblings: [{ annotation: jakarta.ws.rs.Produces, arg: value }]   # §3b word 1, new
    consumes_from_siblings: [{ annotation: jakarta.ws.rs.Consumes, arg: value }]   # §3b word 1, new
    type_media_from_siblings:                                                       # §3b word 2, new
      produces: [{ annotation: jakarta.ws.rs.Produces, arg: value }]
      consumes: [{ annotation: jakarta.ws.rs.Consumes, arg: value }]
    method_from: method                      # never present; each entry pre-sets its verb
    all_methods: []                          # an entry naming no verb derives nothing — there is none
    annotations:
      - { fqn: jakarta.ws.rs.GET,     method: [GET] }
      - { fqn: jakarta.ws.rs.POST,    method: [POST] }
      - { fqn: jakarta.ws.rs.PUT,     method: [PUT] }
      - { fqn: jakarta.ws.rs.DELETE,  method: [DELETE] }
      - { fqn: jakarta.ws.rs.PATCH,   method: [PATCH] }
      - { fqn: jakarta.ws.rs.HEAD,    method: [HEAD] }
      - { fqn: jakarta.ws.rs.OPTIONS, method: [OPTIONS] }
protocol_hint:
  protocol: sse
  hint_media: [text/event-stream]           # MediaType.SERVER_SENT_EVENTS, inlined by javac (measured)
media_formats: { application/json: json, application/xml: xml, … the spring-web.yml table }
shape_model: json
```

- **`method_from: method` with `all_methods: []`** is the JMS/Kafka verbless declaration used
  for the opposite reason: every verb comes from the entry, none from an attribute, and an
  annotation naming no verb must derive nothing. Measured 2026-09-18 on
  `jakarta.ws.rs-api-4.0.0.jar`: `javap -cp … jakarta.ws.rs.GET` prints an empty interface
  body; each verb is `@Target(METHOD)` and meta-annotated `@HttpMethod("GET")` etc.; `@Path`,
  `@Produces`, `@Consumes` are `@Target({TYPE, METHOD})` with `value(): String` / `String[]`.
  In the SQL, an empty `path_from` falls to the sibling read and then to `''`
  (`derive_endpoints.sql:458-463`), and an entry's verbs win over an empty `all_methods`
  (lines 464-479) — verified by reading, pinned by the tests in §3e.
- **The SSE block is COVERAGE §5.6's "one YAML entry."** `text/event-stream` stays out of
  `media_formats` for the reason `spring-web.yml` states: it names the envelope, never the
  per-event format.

### 3b. Three engine words

**Word 1 — `produces_from_siblings` / `consumes_from_siblings`.** `{annotation, arg}` lists,
the closed shape `path_from_siblings` already has (`annotation_driven.py::_SIBLING_KEYS`),
consulted **where every `produces_from` / `consumes_from` alias is absent**, in the order
written, scalar-or-array, first present wins, values sorted and de-duplicated (D01 §4). One
new CTE pair in `derive_endpoints.sql` beside `sibling_path_sources`/`sibling_names` (lines
401-412), joined into `produces`/`consumes` as the path CTEs join into `path`. Forced by the
measurement above: the verb annotations declare no attribute a media alias could read.

**Word 2 — `type_media_from_siblings`.** The class-level media default: `{produces: […],
consumes: […]}`, sibling lists read off annotations targeting the **enclosing type**.
Combine rule — the method's declaration wins when non-empty, else the type's, never a union
— is Spring's (`ProducesRequestCondition.combine`, shipped 2026-09-12) and JAX-RS's: measured
2026-09-18, Jersey `IntrospectionModeller.resolveProducedTypes(method, classDefault)` takes
the method's `@Produces` when present, else the class list (`javap -c -p` on jersey-server
4.0.0), and Quarkus `EndpointIndexer.java:724-726` does the same ("use the @Produces
annotation at class level if exists"). A separate word from the prefix read because `@Path`
carries no media and `@Produces` no prefix — the `prefix_from`/`peer_from` reason.

**Word 3 — siblings inherit with the mapping, all or nothing (M3).**
`effective_annotations.py::inherited_rows_over` gains one rule for catalogs that declare
`inherit_siblings: all_or_nothing` *(amended after the final review: opt-in through that
one-word key rather than implied by any sibling list — `microprofile-graphql.yml` names
siblings under a framework with no §3.6)*: when it synthesizes an inherited mapping onto a target method, it also
synthesizes that ancestor method's annotations whose fqn appears in the catalog's
`path_from_siblings`, `produces_from_siblings`, `consumes_from_siblings` or
`protocol_hint.hint_annotations` — and it does so **only when the target method carries none
of the catalog's annotations of its own** (mapping or sibling). That is JAX-RS §3.6 exactly:
*"if a subclass or implementation method has any JAX-RS annotations then all of the
annotations on the superclass or interface method are ignored."* Spring's own rule (merge
per annotation, mapping-only own-check) stays as today for catalogs declaring no siblings.

- The synthesized siblings are ordinary annotation rows to the SQL, so the sibling CTEs and
  words 1–2 need no inheritance awareness — one module knows about inheritance, as today.
  *(Amended after the final review: this sentence also named the hint pass, and the hint pass
  reads the raw `annotations` table, not the walk's `$synthetic` rows — an interface-declared
  `@GET @RestStreamElementType(...)` with an annotation-free implementor derives `http`;
  `OI-92`.)*
- The type-level gate already inherits: the walk synthesizes `{target: type_symbol,
  annotation: <prefix fqn>}` for a class whose interface or superclass carries the prefix
  (`effective_annotations.py`, the `found_prefix` block), and `@Path` is both prefix and
  gate, so `controllers` (`derive_endpoints.sql:435-439`) admits the implementor. Pinned by
  the interface fixture in §3e rather than assumed.
- **Boundary, measured in P1/P2 before it is stated:** the §3.6 "any own annotation" switch
  means an implementor method carrying only its own `@Produces` is, to JAX-RS, **not** a
  resource method (interface annotations ignored, no verb of its own). Word 3 reproduces
  that — the target has an own sibling, so nothing is inherited, and with no own verb no row
  derives — which is the framework's answer. Whether Quarkus REST's `AnnotationStore`
  follows §3.6 or Spring-style merging is a P2 item; if it diverges, `quarkus-rest.yml`
  states it.

All three words are optional and inert unless declared.

### 3c. Quarkus REST — what the third catalog adds

Each is measured 2026-09-18 on quarkus-rest 3.39.4 sources unless marked P2:

- **The class-level `@Path` gate stays** (R1). `ResteasyReactiveScanner.scanResources`
  builds root resources from `@Path` on a class or on an interface it implements (lines
  247-254, 309-316); a class with HTTP-method annotations and no `@Path` anywhere is a
  *possible sub-resource* (lines 361-390), never a root. The "no PATH whatsoever" rule at
  line 344 is for client interfaces. The draft's bullet claiming otherwise is withdrawn.
- **`@RestStreamElementType` implies SSE (M1).** `EndpointIndexer.java:713-723`: the
  element type is read from the method, else the class; if the method has no `@Produces`
  and an element type is present, `produces` **becomes `text/event-stream`**. The
  deprecated `@RestSseElementType` is read as an alias (`getStreamAnnotationValue`, lines
  862-866). So the annotation's **presence with no method-level `@Produces`** is the SSE
  evidence *(amended after the final review: the draft said presence alone, and CP-19 row
  2a's own condition is `produces == null || produces.length == 0` on the METHOD's
  `@Produces` — a handler declaring `@Produces(APPLICATION_STREAM_JSON)` beside the marker
  serves what it declares; the pass yields to the catalog's `produces_from_siblings`
  annotation on the owner)*, and its **value** is the
  per-event type. The catalog declares a third `protocol_hint` evidence kind:

  ```yaml
  protocol_hint:
    protocol: sse
    hint_media: [text/event-stream]
    hint_annotations: [org.jboss.resteasy.reactive.RestStreamElementType,
                       org.jboss.resteasy.reactive.RestSseElementType]
  ```
  `hint_annotations` is a list of fqns in `hint_returns`' shape, unioned across catalogs;
  the pass fires when one targets the row's handler **or its enclosing type** (the class-level
  form) **and the handler itself carries none of the catalog's `produces_from_siblings`
  annotations** (amended, above). Same contract as the other two kinds: protocol only,
  existing rows only, source protocol scoped.

  **The value as per-event format is a named follow-up, not in this group.** Today an SSE
  row's per-event payload falls to rung 5 (`json`, `narrowed`, rendered *json (assumed)*);
  the element annotation is rung-2 evidence for it. Carrying it means a new rung-2 source
  on the format ladder — a trust-marker upgrade with no wrong output either way — logged in
  the register pointing at rung 2, shipped when the ladder is next touched. It is
  deliberately **not** read into `produces`: on an SSE row `produces` names the envelope.
- **Two implicit body bindings (M4, A′)** — `request_body.implicit_bindings: [path_variable,
  container]`, §4.
- **Vert.x context types.** `DEFAULT_CONTEXT_TYPES` (`EndpointIndexer.java:153-158`) plus
  what `quarkus-rest-deployment` adds through `addContextTypes` — `io.vertx.ext.web.RoutingContext`,
  `io.vertx.core.http.HttpServerRequest`/`HttpServerResponse` and the rest P2 (c) lists —
  go in `excludes`. Measured at one version and pinned in `measured:`; an unlisted future
  type is a phantom body and is the honest boundary of a type list.
- **`@RestPath`/`@RestQuery`/`@RestHeader`/`@RestForm`/`@RestCookie`/`@RestMatrix`,
  `@MultipartForm`** join `bound_by` — they are Quarkus's binding annotations
  (`JAX_RS_ANNOTATIONS_FOR_FIELDS`, `ResteasyReactiveDotNames.java:265-268`).
- **`@ResponseStatus`, `@ResponseHeader`, `@Blocking`/`@NonBlocking`, `@Separator`**: no
  effect on wire identity or contract; stated in COVERAGE.
- **Default `produces` by return type** (`applyDefaultProduces`, line 853): Quarkus fills an
  undeclared `produces` from the return type (`String` → `text/plain`, otherwise JSON where a
  JSON provider is present). A framework-contract default of the kind `default_produces`
  exists for, but keyed on return type, which no key states. Boundary: an undeclared Quarkus
  route falls to rung 5 exactly as a Spring one does.

### 3d. Stated boundaries (COVERAGE, not built)

- **Sub-resource locators** — a `@Path` method with no verb returning a resource class.
  Derives nothing, and says so; the target is a return type the engine would have to recurse
  into.
- **Custom verbs** via `@HttpMethod("LINK")` on a framework-jar annotation. A **module-local**
  one resolves through the effective-annotations pre-pass; the jar half is D02 §7's standing
  boundary. Measured: `@HttpMethod` is `@Target(ANNOTATION_TYPE)` with `value(): String`.
- **Regex path templates** `{id: \d+}` are kept verbatim in `path`; the §4 name match reads
  the variable name before the `:`.
- **Implicit `HEAD` and `OPTIONS`** are not minted, as for Spring and Micronaut.
- **`@ApplicationPath`** — a deployment-wide prefix on the `Application` subclass, read from
  neither the class nor configuration. Recorded beside Actuator's base-path boundary.
- **Nested parameter containers** — Quarkus itself does not handle them
  (`ResteasyReactiveParameterContainerScanner.java:16`, `FIXME`), so not a divergence.
- **Parameter names absent** (compiled without `-parameters` or `-g`): the `path_variable`
  binding cannot fire and the parameter falls through to the body rule — which is Quarkus's
  own behaviour short of its build-time failure. Quarkus's Maven and Gradle plugins pass
  `-parameters` by default, so rare.
- **Jersey package scanning** discovers root resources by the class file's *own* `@Path`;
  a class implementing a `@Path` interface is a root resource once registered (explicitly
  or via `Application.getClasses()`), not by package scan. A registration-mode nuance, not a
  model divergence; stated.

### 3f. `mp-rest-client` — the outbound twin, on the same words

MicroProfile REST Client declares an HTTP client as an **interface** carrying the JAX-RS
annotations — `@Path` on the type, `@GET`/`@Path`/`@Produces`/`@Consumes` on the methods —
gated by `@RegisterRestClient`. Measured 2026-09-18 on
`org.eclipse.microprofile.rest.client:microprofile-rest-client-api:4.0` (`javap -v`):
`@RegisterRestClient` is `@Target(TYPE)`, `@Retention(RUNTIME)`, and declares `baseUri()`
and `configKey()`, both `String`, both defaulting `""`. It is `jakarta-jaxrs.yml` with the
direction flipped and the construct kind fixed — the `jakarta-jws.yml`/`jakarta-jws-client.yml`
partition, and the `spring-http-interface.yml` shape (`declared_on: interface`, outbound):

```yaml
id: microprofile-rest-client
style: annotation_driven
protocol: http
direction: outbound
declared_on: interface
detect: { coordinates: ["org.eclipse.microprofile.rest.client:microprofile-rest-client-api",
                        "io.quarkus:quarkus-rest-client", "io.quarkus:quarkus-rest-client-jackson"] }
matches:
  type_annotation: org.eclipse.microprofile.rest.client.inject.RegisterRestClient
  request_body: { fallback: sole_unbound, bound_by: [ …the jakarta-jaxrs list… ], excludes: [] }
  mapping:
    prefix_annotation: jakarta.ws.rs.Path        # the interface's @Path, as the resource's is
    prefix_from: [value]
    peer_from: [baseUri, configKey]              # read off @RegisterRestClient — the type gate, not @Path
    path_separator: "/"
    path_from: []
    path_from_siblings: [{ annotation: jakarta.ws.rs.Path, arg: value }]
    produces_from_siblings: [{ annotation: jakarta.ws.rs.Produces, arg: value }]
    consumes_from_siblings: [{ annotation: jakarta.ws.rs.Consumes, arg: value }]
    type_media_from_siblings: { produces: […], consumes: […] }
    method_from: method
    all_methods: []
    annotations: [ …the seven verb entries… ]
```

- **`peer_from` reads the gate annotation, not the prefix annotation.** Feign's `peer_from:
  [name, value]` reads `@FeignClient`, which is both gate and prefix carrier; here the
  prefix is on `@Path` and the peer on `@RegisterRestClient`. The plan verifies which
  annotation `peer_from` is read off today (`derive_endpoints.sql`'s `prefixes` CTE joins
  `prefix_gates`); if it is the prefix annotation only, `peer_from` gains a
  `peer_annotation` twin of `prefix_annotation`, declared here and inert elsewhere. P5
  records the answer.
- **Boundary, stated:** the base URI resolved from configuration —
  `<fqn>/mp-rest/url`, `<configKey>/mp-rest/url`, Quarkus's
  `quarkus.rest-client.<configKey>.url` — is not read; a client declaring `configKey` and
  no `baseUri` carries the key as its `peer`, exactly as a Feign client carries its
  service id. Reading the property is D02 §2d's `config_join` territory and a later item.
- The client's own inbound-side fence: `jakarta-jaxrs.yml`, `javax-jaxrs.yml` and
  `quarkus-rest.yml` declare `declared_on: class` (§3a), so a `@RegisterRestClient @Path`
  interface mints no inbound row.
- **Fixture and test.** `fixtures/orders-quarkus/.../OrdersClient.java` —
  `@RegisterRestClient(configKey = "orders") @Path("/remote/orders")` with `@GET List<Order> list()`
  and `@GET @Path("/{id}") Order byId(@PathParam("id") String id)`, plus one method with
  `baseUri`; the module gains `microprofile-rest-client-api` (4.0) as a dependency. Strict-xfail
  test in `tests/e2e/test_rest_outbound_delivered.py`: two `http` outbound rows on
  `/remote/orders` and `/remote/orders/{id}` with `peer` = `orders`, and no inbound row for
  the interface.

### 3e. Fixtures and tests

- `fixtures/orders-spring7/src/main/java/com/acme/jaxrs/OrderResource.java` — **unchanged**;
  its two strict-xfail tests turn green.
- New in `orders-spring7`: a `javax.ws.rs` twin (`LegacyResource.java`; the module gains
  `javax.ws.rs:javax.ws.rs-api` as `provided`); a `@Valid Order order` body method (M2's Java
  case); and the generated-interface pair `OrdersApi` (all annotations, including a
  `@GET @Path("/{id}") @Produces` method and an SSE method) with `OrdersResource implements
  OrdersApi` carrying no annotations (M3). Strict-xfail tests first: the implementor's rows
  carry the interface's composed paths and media, and the SSE row reclassifies.
- New Kotlin resource in a fixture module that already compiles Kotlin (`orders-service`
  does; the plan picks it or adds the Kotlin plugin to `orders-spring7`): a body parameter
  under kotlinc's `@NotNull` derives its contract (M2's Kotlin case).
- New: `fixtures/orders-quarkus/src/main/java/com/acme/quarkus/OrderResource.java` — a
  `@Path` class with: `byId(String id)` under `@Path("/{id}")` (path-variable binding); an
  `Upload` container parameter whose class has `@RestForm` fields; a `RoutingContext`
  parameter; an SSE method declaring `@RestStreamElementType(APPLICATION_JSON)` and **no**
  `@Produces`; and a `@Produces(SERVER_SENT_EVENTS)` method with no element type. Strict-xfail
  tests: no body on `byId`, no body on the upload method, no body beside `RoutingContext`,
  the element-type method is `sse`, and the same class under `jakarta-jaxrs.yml` alone
  publishes `String` as `byId`'s body — which is what Jersey does. Two catalogs, two answers,
  each its framework's; that assertion is what proves the third catalog earns its file.
- Media tests assert `produces` as read from the sibling: `application/json` off the class
  on `list()`, `text/event-stream` off the method on `events()`.

---

## 4. The body rule — `sole_unbound` (M2, M4)

**The framework's rule.** JAX-RS §3.3.2.1: the entity parameter is the one parameter that
carries none of the specification's parameter annotations. Quarkus REST
(`EndpointIndexer.java:1380-1413`), in order: an explicit binding annotation → a context type
→ a *parameter container* class → a name matching a path-template variable → **else the body**.
Today's `sole_unannotated` approximates the first step as "no annotation of any kind", which
is why kotlinc's `@NotNull` and Bean Validation's `@Valid` remove the body (§1 item 3).

**One new fallback word, three predicates, one shared list:**

```yaml
request_body:
  fallback: sole_unbound
  bound_by: [ <fqns> ]                        # the framework's binding annotations — required with this word
  excludes: [ <fqns> ]                        # types injected without an annotation — as today
  implicit_bindings: [path_variable, container]   # optional; closed vocabulary; absent = none
```

A parameter is **bound** — and therefore not the body — when any of these holds:

1. it carries an annotation whose fqn is in `bound_by`, **or** its declared type is in
   `excludes`;
2. `path_variable` is declared and its `name` equals a `{name}` (or `{name: regex}` — the
   token before the `:`) in the row's **composed** path
   (`EndpointIndexer.java:1393-1399`: *"this parameter name matches the @Path parameter name,
   so it has been implicitly assumed to be an @PathParam and not the request body"*);
3. `container` is declared and the parameter's class declares a **field or method** carrying
   an annotation in `bound_by`
   (`ResteasyReactiveParameterContainerScanner.java:19-31`, over the set at
   `ResteasyReactiveDotNames.java:265-268` — which is why `@BeanParam`, `@MultipartForm`,
   `@DefaultValue` and `@Suspended` are in the catalog's `bound_by` too).

The body is the **sole** unbound parameter; zero or several → no contract, as today. Any
other annotation on a parameter — `@Valid`, `@NotNull`, kotlinc's `@NotNull`, Jackson's,
Lombok's — is invisible to the rule, because it is invisible to the framework.

- **`bound_by` is required with `sole_unbound`** and refused with `sole_unannotated`: the word
  means "measured against this list", and a list-less use would be the old word under a new
  name. `request_body.annotation` becomes optional (R3): JAX-RS has no marker.
- **`implicit_bindings` is a closed vocabulary**, two words, refused otherwise. Declared by
  `quarkus-rest.yml` only. `jakarta-jaxrs.yml` deliberately declares none: under Jersey,
  `byId(String id)` beneath `@Path("/{id}")` **is** an entity body, and the catalog says so.
- **Engine.** `_body_parameter` (`contracts.py:242`) gains the word. Predicate 2 needs the
  row's composed path, which `_contracts_of` iterates but does not pass down — one plumbing
  change. Predicate 3 needs annotation rows on fields and methods grouped by enclosing type
  — one query per catalog declaring `container`, fetched once (GUIDELINES §8.7), the same
  shape as the §2 owner lookup.
- **What stays with `sole_unannotated`.** Every shipped catalog declaring it derives
  byte-identically; none is rewritten in this group. The Feign and Micronaut fallbacks have
  the same latent Kotlin defect and are logged in the register with `sole_unbound` as their
  fix (§6).

---

## 5. Group C — two consumers of the §2 condition

### 5a. `kafka-batch-generics` — `wrappers[].when`

**The framework's rule, measured 2026-09-18 on spring-kafka 3.1.4 and 4.1.1** (`javap -c -p`
on `KafkaListenerAnnotationBeanPostProcessor`, both jars; the versions `spring-kafka.yml`'s
`measured:` block already carries):

- `@KafkaListener.batch()` is a `String`; the post-processor runs
  `if (StringUtils.hasText(batch)) endpoint.setBatchListener(Boolean.parseBoolean(batch))`.
  **No placeholder resolution**: `"${x}"` is parsed literally and reads `false`. **Case-
  insensitive**: `"TRUE"` is batch. Hence `parses_true` (§2) rather than `equals`.
- A batch endpoint's adapter (`BatchMessagingMessageListenerAdapter.onMessage(List<ConsumerRecord<K,V>>, …)`)
  hands the handler a `List` whose elements are the **individual records' values** — the
  topic's wire payload is `T`, and `List` is the container's envelope, as `ConsumerRecord<K,V>`
  is for a record listener (already `semantics: envelope, payload_arg: 1`).
- A record listener with a `List<T>` parameter gets one record's payload converted into that
  list — the wire payload is the list. The shipped `onBatch` test asserts this and stays.
- `spring.kafka.listener.type=batch` (a container-factory property) makes every listener
  under that factory a batch listener with **no annotation trace** — a `config_join`
  question and a **stated boundary**: a module using it publishes the array; COVERAGE names
  the property.
- **Agreement, not a boundary:** `batch = "${listener.batch}"` publishes the array here and
  is a record listener in Spring — both read the literal. The draft called this a boundary;
  it is the framework's own answer.
- P3 (c) lists the parameter shapes the batch adapter accepts — `List<T>`,
  `List<ConsumerRecord<K,V>>`, `List<Message<T>>`, `ConsumerRecords<K,V>` — so the
  boundary list below is measured.

**The catalog change**, `spring-kafka.yml`:

```yaml
wrappers:
  - { type: org.springframework.http.ResponseEntity, payload_arg: 0, semantics: http_envelope }
  - { type: java.util.Optional, payload_arg: 0, semantics: optional }
  - { type: org.apache.kafka.clients.consumer.ConsumerRecord, payload_arg: 1, semantics: envelope }
  - { type: java.util.List, payload_arg: 0, semantics: envelope,
      when: { annotation_arg: { annotation: org.springframework.kafka.annotation.KafkaListener,
                                name: batch, parses_true: true } } }
```

**The engine change.** `shapes/contracts.py::_contracts_of` roots each owner's signature
through `rules.wrappers` (`_payload_descriptor` → `rooting.root_type`) with no row context.
It gains one step: the wrapper list handed to `root_type` for an owner is the unconditional
wrappers plus every conditional wrapper whose `when` holds for that owner — evaluated against
the annotation rows targeting the owner and its enclosing type, fetched **once per catalog**
keyed on target (§8.7). `_matching_wrapper`'s "rooting stopped on a declared envelope → no
payload" rule reads the *filtered* list too.

**Where the condition deliberately does not reach.** Shape *expansion* (`expansion.py`) is
global, keyed on type symbol, insert-if-absent; `spring-kafka.yml`'s own comment records the
sort-order hazard of wrapper copies. A conditional wrapper applies at **rooting**, before a
shape is named, so `java.util.List` never enters `shapes` as an envelope and a `List<OrderView>`
response elsewhere is untouched. `when` is refused on an entry whose type any *other*
catalog's unconditional list also names.

**Chained envelopes.** `root_type` unwraps recursively, so `List<ConsumerRecord<K,V>>` under
batch reaches `V` through both wrappers; `List<Message<T>>` reaches `T` once `Message` is
declared (P3 (e) decides whether it joins this catalog). `ConsumerRecords<K,V>` has no element
position and stays an open type, disclosed.

**Fixture and test.** `OrderEventsListener.java` gains
`@KafkaListener(topics = "order-batch-records", batch = "true") onRecords(List<OrderEvent>)`
and a second `batch = "TRUE"` listener; strict-xfail tests in `tests/application/test_pipeline.py`
assert both `request_shape`s are `OrderEvent` — beside the existing array test, unchanged, as
the negative case.

### 5b. `micronaut-jms-over-sqs` — `protocol_hint.hint_when`, on both directions

**The framework's rule, measured 2026-09-18 on micronaut-jms-core 4.2.0, micronaut-jms-sqs
4.2.0, micronaut-jms-activemq-classic 4.2.0, micronaut-jms-activemq-artemis 4.2.0** (`javap -v`
/ `javap -constants`; commands recorded by P4):

- `@JMSListener` declares `value(): String`, `successHandlers()`, `errorHandlers()` — **no
  `connectionFactory` attribute** (R2). `@JMSProducer` declares `value()` alone. Both are
  `@Retention(RUNTIME)`, `@Target(TYPE)`, so the extractor sees them. `AbstractJMSListenerMethodProcessor`
  reads `getAnnotation(JMSListener.class).getRequiredValue(String.class)` and looks the
  `ConnectionFactory` up with `Qualifiers.byName(…)` — `value` **is** the factory bean name.
  The fixture's `@JMSListener("orders-connection")` is that spelling.
- `micronaut-jms-sqs` registers its factory as `@Named("sqsJmsConnectionFactory")`
  (`$SqsConfiguration$SqsJmsConnectionFactory0$Definition`), with
  `SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME = "sqsJmsConnectionFactory"`. A source writing
  the constant compiles to the literal (JLS 15.29). ActiveMQ Classic's is
  `"activeMqConnectionFactory"`, Artemis's `"activeMqArtemisConnectionFactory"` — both stay
  `jms`; the negative fixture.
- What "Micronaut SQS" is: Micronaut ships no first-party SQS annotation (COVERAGE §5 SQS).
  A Micronaut module reaches SQS either through the raw AWS SDK (`aws-sqs-sdk.yml`, shipped)
  or through **JMS over SQS** — `micronaut-jms-sqs` wrapping `amazon-sqs-java-messaging-lib`,
  where `@Queue("name")` is the SQS queue name. That name is the identity a Spring
  `@SqsListener("name")` row carries, so the reclassified row links under DR-5.

**Third `protocol_hint` evidence kind (`hint_when`), beside `hint_media`, `hint_returns` and
§3c's `hint_annotations`:**

```yaml
# micronaut-jms.yml
protocol_hint:
  protocol: sqs
  hint_when: { annotation_arg: { annotation: io.micronaut.jms.annotations.JMSListener,
                                 name: value, equals: sqsJmsConnectionFactory } }
```
```yaml
# micronaut-jms-producer.yml — identical rule, the producer's gate
protocol_hint:
  protocol: sqs
  hint_when: { annotation_arg: { annotation: io.micronaut.jms.annotations.JMSProducer,
                                 name: value, equals: sqsJmsConnectionFactory } }
```

- The pass resolves each candidate row's owner (`handler` on the listener's rows, `caller` on
  the producer's — the `handler or caller` or-chain `_contracts_of` uses), evaluates the §2
  condition against the owner's and its enclosing type's annotation rows, and writes `sqs`;
  `reclassify_protocol` and `reclassify_open_questions` carry the row and its ledger as they
  do for SSE. The rewritten row takes the format ladder as SQS.
- **One widening of the pass's contract, recorded in its module docstring:** today it reads
  catalog vocabulary and the row's own columns; with `hint_when` and `hint_annotations` it
  also reads annotation facts for the row's owner and the owner's type. It still writes
  exactly one column, on rows that already exist.
- **Scoping, verified by reading `protocol_hint.py::_vocabulary`:** hint blocks are keyed by
  the declaring catalog's source protocol; evidence lists are **unioned** across catalogs
  and a conflicting **target** is refused. So two Micronaut catalogs hinting `jms → sqs`
  merge; the union means the rule is evaluated on every `jms` row, including Spring's, and
  cannot match one because `annotation` names a Micronaut fqn. `hint_when` conditions union
  as a list, like `hint_returns`.
- **Why not `resolves.protocol`.** Match-time protocol would thread a per-row protocol
  through `derive_endpoints.sql` and change identity minting; the post-merge pass is the
  documented home for "same declaration, different protocol" (D02 §2c, second bullet).

**Stated boundaries.** A user-named factory bean (`@JMSListener("myFactory")` wired to an SQS
`ConnectionFactory` in a `@Factory`) is unknowable from bytecode and stays `jms`; only the
framework's constant is matched. A `value` written as a property placeholder compares unequal
and stays `jms`.

**Fixture and tests.** `fixtures/orders-micronaut/.../OrderMessaging.java` gains
`@JMSListener(SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME) SqsConsumer` with
`@Queue("mn.orders.sqs")`, `@JMSProducer(SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME)
SqsSender` with `@Queue("mn.orders.sqs-out")`, and an
`@JMSListener(ActiveMqClassicConfiguration.CONNECTION_FACTORY_BEAN_NAME)` negative; the module
gains the `micronaut-jms-sqs` and `micronaut-jms-activemq-classic` dependencies. Strict-xfail
tests in `tests/e2e/test_messaging_micronaut_delivered.py` assert one `sqs` inbound and one
`sqs` outbound row on those names, and that the `orders-connection` and ActiveMQ rows stay
`jms`. COVERAGE line 3222's example is corrected to the `value` spelling in the same task.

---

## 6. What this design does not do, and what it logs

Not done:
- No `resolves.protocol`, `resolves.format`, or ordered rule lists (Approach 3, refused).
- No third comparator on `annotation_arg`; no condition on configuration values
  (`spring.kafka.listener.type`, `@ApplicationPath`).
- No sub-resource locator recursion, no implicit HEAD/OPTIONS, no path-template
  normalisation, no nested parameter containers.
- No change to shape expansion; conditional wrappers act at rooting only.
- `@RestStreamElementType`'s value is not carried as the per-event format (§3c).
- No version bump: the standing gate (Spring Boot end-to-end before any bump) holds;
  CHANGELOG `Unreleased` records the four items and the producer addition.

Logged in the register by the closing task, each with real input that triggers it:
- **Feign and Micronaut `sole_unannotated` catalogs** (`spring-cloud-openfeign.yml`,
  `micronaut-jms*.yml`, `micronaut-kafka.yml`, `micronaut-pubsub.yml`) lose a Kotlin
  caller's or listener's body to kotlinc's `@NotNull` — fix is `sole_unbound` with each
  framework's own `bound_by`, measured per framework.
- **SSE per-event format from `@RestStreamElementType`** — a rung-2 source for the format
  ladder; today rung 5 "assumed".
- **Quarkus default `produces` by return type** — a return-type-keyed framework default.

---

## 7. The four probes — recorded before any key is written

`scripts/probes/cp<N>_<topic>.md`, the CP-n convention: every row a command, its output
quoted, the claim it settles named. The self-review of 2026-09-18 ran the commands below
informally; the probe files make them the record, and each catalog's `measured:` block
cites its probe by path.

| Probe | Artifacts, versions | Must record |
|---|---|---|
| **P1** JAX-RS API and two implementations | `jakarta.ws.rs:jakarta.ws.rs-api` 4.0.0 (measured) and 3.1.0; `javax.ws.rs:javax.ws.rs-api` 2.1.1; `jakarta.ws.rs:jakarta.ws.rs-api` 2.1.6; `org.glassfish.jersey.core:jersey-server` 4.0.0 (measured); `org.jboss.resteasy:resteasy-core` 6.2.12.Final (measured) | (a) the seven verb annotations declare **no** attributes and are `@HttpMethod("…")`-meta-annotated, `@Target(METHOD)`; (b) `@Path`/`@Produces`/`@Consumes` `@Target({TYPE, METHOD})`, `value(): String` / `String[]`; (c) method-over-class media in Jersey `resolveProducedTypes` and Quarkus line 725; (d) the `@Context`-injectable type list for `excludes` and the binding-annotation list for `bound_by`; (e) `SERVER_SENT_EVENTS = "text/event-stream"`; (f) `@HttpMethod` `@Target(ANNOTATION_TYPE)`; (g) both implementations' root-resource walk over interfaces and superclasses; (h) JAX-RS §3.6's any-own-annotation rule as Jersey and RESTEasy apply it |
| **P2** Quarkus REST | `io.quarkus:quarkus-rest` 3.39.4 sources (measured) and 3.17.5; `quarkus-rest-deployment` 3.39.4; `quarkus-resteasy-reactive` 3.15.7 | (a) `scanResources`: class `@Path` required for servers, interface implementors registered, client-only relaxation; (b) `EndpointIndexer` 713-737: element type from method else class, SSE implied when no `@Produces`, `@RestSseElementType` alias; (c) `DEFAULT_CONTEXT_TYPES` plus `addContextTypes` callers in the deployment module; (d) the body-parameter order at 1380-1413 and the container scan set at `ResteasyReactiveDotNames.java:265`; (e) relocation version and both coordinates; (f) whether `AnnotationStore` applies §3.6 or merges per annotation |
| **P3** Spring Kafka | `org.springframework.kafka:spring-kafka` 3.1.4, 4.1.1 (both measured) | (a) `batch(): String`; (b) `hasText` → `Boolean.parseBoolean` → `setBatchListener`, no resolution, quoted; (c) `BatchMessagingMessageListenerAdapter`'s accepted parameter shapes; (d) `spring.kafka.listener.type` leaves the attribute empty; (e) whether `Message<T>` needs a wrapper row |
| **P5** MicroProfile REST Client | `org.eclipse.microprofile.rest.client:microprofile-rest-client-api` 4.0 (measured), 3.0.1; `io.quarkus:quarkus-rest-client` 3.39.4 | (a) `@RegisterRestClient` target, retention, attributes and defaults; (b) which annotation `peer_from` is read off in `derive_endpoints.sql` today; (c) how Quarkus resolves the base URI (`RestClientBase`/`RestClientBuilder` — `baseUri`, then config) for the boundary statement |
| **P4** Micronaut JMS | `io.micronaut.jms:micronaut-jms-core` 4.2.0, `micronaut-jms-sqs` 4.2.0, `micronaut-jms-activemq-classic` 4.2.0, `micronaut-jms-activemq-artemis` 4.2.0 (all measured) | (a) `@JMSListener`/`@JMSProducer` attributes — `value()` only — retention and target; (b) `AbstractJMSListenerMethodProcessor` reading `value` as the factory bean name via `Qualifiers.byName`; (c) the three `CONNECTION_FACTORY_BEAN_NAME` literals and the SQS factory's `@Named`; (d) `javap -v` of a compiled fixture class showing `value` in the class file |

---

## 8. The proof that nothing existing moves — run before any engine work

1. Every key here is optional and defaults to shipped behaviour: no sibling media source →
   media read as today; no `when` → wrapper unconditional; no `hint_when`/`hint_annotations`
   → the hint block reads media and return types as today; `sole_unannotated` unchanged; no
   `inherit_siblings` → the inheritance walk synthesizes exactly what it synthesizes today
   *(amended after the final review: opt-in through `inherit_siblings`, since a sibling list
   alone — `microprofile-graphql.yml` has one — must not switch the walk)*.
2. **Golden run:** `uv run sextant module analyze` + `render` + `export` on
   `fixtures/orders-service`, `orders-spring7`, `orders-micronaut`, `orders-quarkus` at `main`
   and after the engine words land with **no catalog yet declaring them**; every
   `endpoints`, `shapes`, `shape_fields`, `open_questions` row and both rendered documents
   byte-identical. `mall-admin` (`scripts/field_check.py mall-admin`) byte-identical before
   and after the whole group.
3. The shipped `onBatch` array test and every `jms` row assertion in
   `test_messaging_micronaut_delivered.py` stay green through every task.

---

## 9. Sizing and the plan's order

Fixtures and strict-xfail tests first (GUIDELINES §4.1), then the four probes, then engine
words in the order they unblock items, then catalogs — each item on the per-item loop
(implement, `scripts/check.sh`, review, fix Critical/Major, record the rest, commit):

| # | Task | Unblocks |
|---|---|---|
| 1 | Fixtures + strict-xfail tests: JAX-RS `javax` twin, `@Valid` body, `OrdersApi`/`OrdersResource`, Kotlin resource, Quarkus resource (five cases), Kafka `batch = "true"`/`"TRUE"`, Micronaut SQS listener + producer + ActiveMQ negative | everything |
| 2 | Probes P1–P4 as `scripts/probes/` files | every key below |
| 3 | `produces_from_siblings` / `consumes_from_siblings` (Python params + SQL CTE pair + D02) | B |
| 4 | `type_media_from_siblings` (Python + SQL + D02) | B |
| 5 | Sibling inheritance, all-or-nothing, in `effective_annotations.py` (+ D02) | B (M3) |
| 6 | `sole_unbound`: `bound_by`, `implicit_bindings` (`path_variable`, `container`), optional `annotation`; composed path into `_body_parameter`; field/method annotation lookup (+ D02) | B (M2, M4) |
| 7 | §2 `when` condition: validator, evaluator with `equals` and `parses_true`, owner→type lookup (+ D02 subsection) | 8, 9 |
| 8 | `wrappers[].when` at rooting (`contracts.py` + D02 §2a) | C-1 |
| 9 | `protocol_hint`: `hint_when` and `hint_annotations`, owner/type annotation read, docstring contract (+ D02 §2) | C-2, B (M1) |
| 10 | `jakarta-jaxrs.yml`, `javax-jaxrs.yml`, `quarkus-rest.yml` + conformance fixtures (D02 §4) | `quarkus-jaxrs`, `jaxrs-sse` |
| 10b | `microprofile-rest-client.yml` + fixture + (if P5 (b) says so) `peer_annotation` | `mp-rest-client` (§3f) |
| 11 | `spring-kafka.yml` conditional wrapper | `kafka-batch-generics` |
| 12 | `micronaut-jms.yml`, `micronaut-jms-producer.yml` hint blocks; COVERAGE 3222 wording | `micronaut-jms-over-sqs` + producer |
| 13 | COVERAGE, delivery list (four closes on the CI run id, producer addition), CHANGELOG, register entries from §6 | close |

Engine tasks: **seven** (3–9), up from five in the draft — tasks 5 and 6 are the review's
M3 and M2/M4. Catalog tasks: four, `mp-rest-client` joining by ruling (§3f). Approach 3 would have been ten to twelve engine tasks
for the same four items *before* the review's additions.

**Cost check (§8.7), per resolve:** one `annotations` query per catalog declaring a `when`
or `hint_annotations` (three today); one field/method annotation query per catalog declaring
`container` (one today); one CTE pair in `derive_endpoints.sql`, empty for every catalog
declaring no sibling media source; the inheritance walk's sibling filter runs over a map it
already holds. No per-row queries, no new tables.
