# D02 — Framework catalog

How Sextant learns what a library's API means. Written by people. Read by
[M04](M04-resolver.md).

A call instruction tells you that `RestTemplate.postForObject` was invoked. Nothing in the
bytecode says that this is an outbound HTTP POST whose URL is the first argument. **That
knowledge is per library, and it lives here as data.**

The rule this document exists to enforce: **there is no `if spring … else if micronaut`
anywhere in Sextant.** Engines are generic interpreters; frameworks are catalog files.

---

## 1. A catalog file

```yaml
id: spring-resttemplate
displayName: Spring RestTemplate
style: single_call
protocol: http
direction: outbound

detect:
  coordinates: ["org.springframework:spring-web"]

requires: [annotation_args, string_constants]

matches:
  owner: org.springframework.web.client.RestTemplate
  methods:
    - { name: postForObject, http_method: POST, url_arg: 0, body_arg: 1, response_arg: 2 }
    - { name: getForObject,  http_method: GET,  url_arg: 0, response_arg: 1 }
```

| Field | Meaning |
|---|---|
| `id` | Stable. Appears in `evidence` and in skip reports. |
| `style` | Which engine interprets `matches` |
| `protocol`, `direction`, `format` | From [D00](D00-fact-schema.md)'s closed sets. **Defaults** — a match may resolve them differently, see §2c |
| `detect` | Coordinates that make this catalog active for a module |
| `requires` | Scanner capabilities. **If unmet, the catalog does not run and the skip is reported.** |
| `matches` | Style-specific |

**`requires` is the mechanism that keeps degradation visible.** A catalog needing chain
reconstruction simply does not run against a scanner that lacks it, and
[M04](M04-resolver.md) reports which catalogs were skipped and why. Silently finding fewer
endpoints is the failure this prevents.

---

## 2. The six styles

A style is a shape of evidence, not a framework. New frameworks reuse a style; only a
genuinely new shape needs a new engine.

### `annotation_driven`

The declaration is an annotation and its arguments.

```yaml
style: annotation_driven
matches:
  type_annotation: org.springframework.web.bind.annotation.RestController
  request_body_annotation: "…annotation.RequestBody"
  mapping:
    path_from: [value, path]
    method_from: method
    all_methods: [GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS, TRACE]
    prefix_annotation: "…annotation.RequestMapping"
    annotations:
      - { fqn: "…annotation.RequestMapping" }
      - { fqn: "…annotation.GetMapping",    method: [GET] }
      - { fqn: "…annotation.PostMapping",   method: [POST] }
```

**One shape, and each annotation carries only what differs about it.** This mirrors the
framework rather than working around it: `@GetMapping` *is* `@RequestMapping` with the method
pre-set, and its own class file says so — it is meta-annotated
`@RequestMapping(method = [GET])` and declares no `method` attribute of its own.

Four rules follow, and none of them names a framework:

- **`prefix_annotation` names the type-level annotation carrying the path prefix**, and it
  reads `path_from` like everything else. It stays a separate field rather than being inferred
  from position: Spring puts the prefix and the method on one annotation, but JAX-RS does not —
  `@Path` on the type is the prefix and `@GET` on the method is the verb. An engine that
  inferred the role from position alone would serve Spring and no one else.
- **`path_from` lists attributes that alias one another**, first present wins, in the order
  written. Spring's `value` and `path` are `@AliasFor` each other, so only one of them is in
  the bytecode: whichever the author typed. Reading one name and defaulting to empty would
  emit an endpoint with **no path** — wrong output rather than a missing one.
- **The method comes from the attribute if present, else the annotation's declared default,
  else every method in `all_methods`.**
- **An annotation naming no method produces one endpoint per method**, not one endpoint with
  an unresolved method. It is not that the analysis failed; the handler genuinely accepts them
  all. Endpoint identity is minted from the wire contract including the method
  ([D01](D01-graph-schema.md)), so a caller sending `POST` must match an inbound endpoint that
  accepts `POST`. One endpoint with an unresolved method would match every caller and blunt
  the comparison the tool exists to make.

**This table hand-copies what the bytecode already states**, and that is a deliberate,
temporary duplication. A `meta_annotations` capability would derive it instead, by reading the
annotation's own class file and following the composition — which would also cover a project's
own composed annotations, such as an `@ApiGet` built from `@GetMapping`. Recorded in §7.

Covers Spring Web, JAX-RS, Spring Kafka, JMS listeners, and JAX-WS.

### `single_call`

One call carries the whole declaration. Arguments are addressed by position or name.

### `fluent`

The request is assembled across several calls, so one value must be followed through a
method body.

```yaml
style: fluent
matches:
  root: { owner: okhttp3.Request$Builder, method: "<init>" }
  steps:
    - { method: url,  captures: { url: arg0 } }
    - { method: post, captures: { http_method: POST, body: arg0 } }
  terminal: build
  execute: { owner: okhttp3.OkHttpClient, method: newCall }
```

**This style requires `chain_reconstruction`** and therefore gates every builder-based
client library. It is the reason that capability matters.

### `interface_implementation`

The boundary is declared by implementing a framework interface — a JMS `MessageListener`,
a generated gRPC base class. Matching is on the hierarchy, and for gRPC it joins to the
protobuf descriptor so that one endpoint is produced per remote method.

### `protocol_hint`

Runs last, and **reclassifies endpoints other engines already produced** — a streaming
response, a long-poll. It changes protocol, never direction, and it never creates an
endpoint.

**It must not touch direction, and the reason is §3's ordering.** Inbound runs before
outbound so that a path a module both exposes and calls merges into one endpoint with
direction `both`. A later pass that changed direction would arrive after that merge has
already happened, silently corrupting it. Direction is therefore resolved **at match
time** — §2c — never afterwards.

### `filesystem`

The declaration is the file's own location. Next.js, SvelteKit, Remix and Nuxt derive the
path from the directory structure and the HTTP verb from an exported symbol's name —
`app/api/users/[id]/route.ts` exporting `GET` is `GET /api/users/:id`. No annotation, no
call, and no string anywhere in the source contains the path.

**Two sources, in order of authority.**

*The build's own manifest, where it exists.* Next.js writes out the resolved route table;
SvelteKit's equivalent varies by adapter. **This is the same category as bytecode** — not an
artifact the build consumes (§DR-4's case) but one it produces, which is the build's own
answer to the question. Every convention is handled for free and stays correct when the
framework adds more, and the framework's conventions are a moving target maintained by
someone else.

*A directory walk, as fallback.* Reading the manifest requires a successful build, which
requires an install and can fail, so a bare checkout must still yield something. A walk
handles the common patterns — nested folders, `[id]` parameters — and records anything it does
not recognise as `partial` rather than guessing. Route groups in parentheses contribute
nothing to the URL; parallel and intercepting routes are rare for API routes specifically.

```yaml
style: filesystem
matches:
  manifest: [".next/routes-manifest.json", ".next/app-paths-manifest.json"]   # ⚠️ internal, unversioned
  walk:
    root: "app"
    endpoint_file: "route.{ts,js}"
    verb_from: exported_symbol_name
    segment:
      - { pattern: "[{name}]",    then: parameter }
      - { pattern: "[[...{name}]]", then: optional_catch_all }
      - { pattern: "[...{name}]", then: catch_all }
      - { pattern: "({name})",    then: omitted_from_path }
```

**A manifest gives paths and nothing else** — not the handler symbol, not the request or
response types. The source still has to be read to connect a path to its code, so the
fallback shares most of its machinery with the primary path rather than duplicating it.

An LLM may verify a walked path against the manifest or the source; a human curation settles
what neither can. As in §2d, an LLM is never the sole source of an address that creates a
link.

## 2a. Wrapper declarations

A return or parameter type is often an envelope around the wire payload:
`ResponseEntity<OrderResult>`, `Mono<OrderResult>`, `Flux<OrderEvent>`,
`CompletableFuture<T>`, `Optional<T>`. The scanner records the full generic type verbatim
([D00](D00-fact-schema.md) §5a); knowing which types are envelopes and where the payload
sits is framework knowledge, so catalogs declare it:

```yaml
wrappers:
  - { type: org.springframework.http.ResponseEntity, payload_arg: 0, semantics: http_envelope }
  - { type: reactor.core.publisher.Mono,             payload_arg: 0, semantics: async }
  - { type: reactor.core.publisher.Flux,             payload_arg: 0, semantics: streaming }
  - { type: java.util.concurrent.CompletableFuture,  payload_arg: 0, semantics: async }
  - { type: java.util.Optional,                      payload_arg: 0, semantics: optional }
```

[M04](M04-resolver.md) unwraps recursively at shape-rooting time —
`Mono<ResponseEntity<OrderResult>>` roots the shape at `OrderResult` — and records the
unwrapping chain on the endpoint. `semantics` is a closed set, and it earns its keep twice
over: `streaming` is evidence for `protocol_hint` reclassification, and `async` marks the
endpoint's path for the blocking-call-on-async-path finding (FR-14). An unfamiliar generic
wrapper with no declaration is **not unwrapped** — the shape roots at the wrapper and the
endpoint records that no wrapper rule matched, so an incomplete catalog degrades visibly
rather than guessing.

---

## 2b. Classification declarations

Endpoints are not the only boundary a trace can stop at. "This call touches a database",
"this call hands work to another thread" — that is framework knowledge too, so catalogs
declare it with the same matching machinery, producing a **call-site classification**
instead of an endpoint:

```yaml
classifications:
  - { match: { owner_hierarchy: org.springframework.data.repository.Repository },
      terminal: persistence, target: database }
  - { match: { owner: java.sql.Connection },
      terminal: persistence, target: database }
  - { match: { owner: java.util.concurrent.ExecutorService, method: submit },
      terminal: async_handoff }
  - { match: { annotation: org.springframework.scheduling.annotation.Async },
      terminal: async_handoff }
```

`terminal` and `target` come from [D00](D00-fact-schema.md)'s closed sets — a catalog can
use them, never extend them. This is what gives `trace_of` its `persistence` and
`async_handoff` terminals, and FR-14 its call-in-loop and blocking-on-async findings.

**A classification never creates an edge or an endpoint.** It decorates a call site the
graph already holds — the same property that keeps overlays incapable of inventing
structure. (`throws` needs no catalog: throw sites are recorded by the scanner directly,
and declared exceptions ride the typed signature.)

## 2c. Resolving `direction`, `protocol` and `format` per match

`protocol`, `direction` and `format` are declared on the catalog as **defaults**, because for
most catalogs they are constant. Three cases break that, and all three are real:

- **`@HttpExchange` is inbound or outbound depending on use.** It normally declares an
  outbound client; Spring 6.1+ also allows *implementing* the interface server-side, which
  makes the same annotation inbound.
- **A `@GetMapping` returning `SseEmitter` is not REST.** Handled already by `wrappers` with
  `semantics: streaming` feeding `protocol_hint` — recorded here for completeness.
- **Format is rarely constant.** `produces = "application/x-protobuf"` changes the wire; a
  payload type extending a generated message says the same thing; a Kafka `value.serializer`
  says it in configuration rather than code.

So a catalog may declare resolution rules alongside its defaults:

```yaml
protocol: rest
direction: outbound        # the default
format: json               # the default

resolves:
  direction:
    - { when: { owner_implemented_in_module: true }, then: inbound }
  format:
    - { when: { annotation_arg: { name: produces, contains: "application/x-protobuf" } },
        then: protobuf }
    - { when: { payload_hierarchy: com.google.protobuf.GeneratedMessage }, then: protobuf }
```

**Rules are evaluated at match time**, in order, first match wins. `direction` resolution must
complete before §3's inbound/outbound merge, which is why it cannot be a later pass.

**A default that survives unchallenged is not an observation.** If no rule fires and the
endpoint takes the catalog's declared `format: json` — because Jackson is simply the framework
default — that value is recorded at `evidence: declared`, never at the `compiler` or `syntax`
level a `produces` attribute would earn. The distinction matters: an assumed format compared
against an observed one is how a matcher reports agreement it has not established.

**Format also gates comparison.** [D00](D00-fact-schema.md)'s directional structural
compatibility assumes both sides describe the same wire. Two contracts in different formats
are not comparable until one is projected into the other — and the projection is not always
identity. Proto3's JSON mapping renames fields to lowerCamelCase by default, so a `.proto`
field `total_amount` reaches a JSON wire as `totalAmount`. A service defined by a `.proto` but
exposed over REST therefore carries different field names than its own schema states.

---

## 2d. Addresses that live in configuration

Some frameworks put no destination in the code at all. A Spring Cloud Stream `Consumer<Order>`
bean named `handleOrder` reads a Kafka topic named nowhere in the source; the topic is under
`spring.cloud.stream.bindings.handleOrder-in-0.destination`. SmallRye's `@Incoming("orders")`
names a channel, not a topic — that is `mp.messaging.incoming.orders.topic`. MicroProfile's
`@RegisterRestClient(configKey="orders")` finds its URL under `orders/mp-rest/url`.

The pattern is constant: **the code carries a name, and configuration says what the name
means.** Configuration resolution is already a first-class pass, so what is missing is only
the vocabulary for the derivation. A catalog declares it:

```yaml
address_from_config:
  key: "spring.cloud.stream.bindings.{binding}.destination"
  binding:
    from: bean_name
    suffix:
      - { when: { implements: java.util.function.Consumer }, then: "-in-0" }
      - { when: { implements: java.util.function.Supplier }, then: "-out-0" }
```

**Three layers, in order of authority.** The catalog rule is primary, because this is
framework knowledge and framework knowledge belongs in data — five rules written once beat
every user writing them per project. Where a rule exists but the resolved value is doubtful,
an LLM **verifies** the join and flags disagreement. Where no rule exists or the verification
disputes it, a human curation settles it at precedence 90.

**An LLM may verify this join; it must not be the sole source of it.** A destination is part
of a wire identity, so a wrong one does not produce a visibly odd field — it produces a
*confident link between two services that do not talk to each other*. Where an LLM is
nonetheless the only source, the endpoint carries `evidence: llm` and every link built on it
inherits that precedence and renders as unconfirmed.

**An unresolved address is not an absent endpoint.** If the key is missing from every
configuration source, the endpoint is still recorded with its address as the unresolved
expression, and the coverage report names the key that was not found. Dropping it would make
a partially-configured module look like a module with fewer boundaries.

---

## 2e. Nullability declarations

Which annotation means "may be null" is framework knowledge, so catalogs declare it and
[D00](D00-fact-schema.md) §5a's `nullable` flag is populated from it. Note the question: this
is about the **value**, not about whether the field must appear — those are separate flags in
D00 and separate keywords in every schema format:

```yaml
nullability:
  nullable:
    - org.jspecify.annotations.Nullable
    - org.springframework.lang.Nullable      # deprecated in Spring 7, still in compiled code
    - javax.annotation.Nullable
    - jakarta.annotation.Nullable
    - org.jetbrains.annotations.Nullable
    - androidx.annotation.Nullable
  not_null:
    - org.jspecify.annotations.NonNull
    - org.springframework.lang.NonNull
    - org.jetbrains.annotations.NotNull
  scope:
    - { annotation: org.jspecify.annotations.NullMarked, means: not_null_by_default }
```

**Several of these coexist in one codebase.** A module compiled over a decade may carry the
JetBrains annotations in old code, Spring's in middle-aged code, and JSpecify in new code, all
reaching the same shape. A catalog listing one of them falls back to the language default for
the rest — for Java that is `nullable` at `resolution: partial`, which is a weaker claim than
an annotated field and is recorded as one.

**Bean Validation's `@NotNull` does not belong in this list.** It constrains a value at
validation time and says nothing about whether the field may be omitted from the payload, so
it is a presence-adjacent rule, not a type one. Putting it here would make every validated
field look non-nullable in its type.

**`NullMarked` is a scope, not a field marker.** JSpecify's default-non-null applies to a
package or class, so a field with *no* annotation inside a `@NullMarked` scope is `not_null` —
the absence carries meaning, and only a declared scope rule recovers it.

**Two facts about reading these that [M03](M03-scanner.md) has to face.** JSpecify is
`TYPE_USE` with `RUNTIME` retention, so it lands in `RuntimeVisibleTypeAnnotations`. And the
older annotations are mostly `CLASS`-retention, landing in the *Invisible* attribute
instead. Neither table can be skipped — the scanner reads both.

---

## 2f. Serialisation naming

`shape_fields.wire_name` is the identity ([D01](D01-graph-schema.md) §5), and a source field
name is not it: `customerId` reaches the wire as `customer_id` under a snake-case strategy, or
as whatever `@JsonProperty` says. Which annotation carries the name, and what happens when
none does, is framework knowledge:

```yaml
serialization:
  name_from:
    - { annotation: com.fasterxml.jackson.annotation.JsonProperty, arg: value }
  ignore:
    - com.fasterxml.jackson.annotation.JsonIgnore
  default_strategy: as_declared      # as_declared | snake_case | kebab_case | upper_camel
```

**`default_strategy` is a declaration, not an observation.** A module may configure a strategy
globally, in which case the value the catalog states is a default that configuration overrides
— so a `wire_name` derived from the default carries `evidence: declared`, while one from an
explicit annotation carries the evidence of the code that declared it. Comparing a declared
name against an observed one is how a matcher reports agreement it has not established
(§2c).

**A field the catalog says to ignore produces no `shape_field` at all.** It is absent from the
wire, and a shape carrying it would fail DR-5's directional comparison against a peer that
correctly omits it.

---

## 2g. Types with a known wire form

Some types are objects in code and something else entirely on the wire. `java.time.Instant`
is an ISO-8601 string; `java.math.BigDecimal` is a number; `google.protobuf.Timestamp` has
`seconds` and `nanos` fields and serialises to an RFC-3339 string. **Expanding them
structurally produces a shape no payload can match** — `BigDecimal` would contribute
`intVal`, `scale`, `intCompact` and `precision`, none of which exists on the wire.

Which types these are is **serialiser knowledge, not language knowledge**: `Instant` is an ISO
string under Jackson's `JavaTimeModule`, epoch millis without it, and whatever a custom
serialiser says. So a catalog declares them:

```yaml
known_types:
  - { type: java.time.Instant,           wire: string, format: date-time }
  - { type: java.time.LocalDate,         wire: string, format: date }
  - { type: java.math.BigDecimal,        wire: number }
  - { type: java.util.UUID,              wire: string, format: uuid }
  - { type: google.protobuf.Timestamp,   wire: string, format: date-time }
  - { type: google.protobuf.StringValue, wire: string, nullable: true }
```

This is the boundary against the extractor's own projection (§D1 of the Phase 2A plan): the
extractor converts what the **language** leaves no choice about — primitives, their boxes,
`String`, arrays, collections. A catalog converts what the **serialiser** decides.

**A third-party type with no entry here is not guessed at.** Expansion stops, the shape is
marked open, the type reference is kept, and [M04](M04-resolver.md) reports the type that
stopped it — so the catalog grows from observation rather than from a structural guess about
what looks "simple".

---

## 3. Ordering

Engines run in a fixed order because later passes depend on earlier ones: inbound first,
then outbound, then `protocol_hint`. Inbound precedes outbound so that a path a module both
exposes and calls merges into one endpoint with direction `both` rather than appearing
twice.

**The order is a property of the engine style, not of the catalog file.** A catalog cannot
request a position.

---

## 4. Every catalog ships a conformance fixture

A catalog is not accepted without a tiny repository that uses the framework, and the exact
endpoint list expected from it. The fixture runs in CI.

Without this, a catalog is an assertion. With it, a catalog is tested — and adding a
framework stays *one YAML file and one fixture, with no engine change and no existing test
modified*.

---

## 5. What a catalog must not contain

- **No code.** If a framework cannot be expressed in a style, that is an argument for a new
  engine, not for an escape hatch.
- **No language names.** Catalogs match on symbols. This is why one Spring catalog serves
  both Java and Kotlin.
- **No ordering requests.**
- **No conditional logic across catalogs.** Two catalogs may both match; both produce
  endpoints, and duplicates merge on wire identity.

---

## 6. Where catalogs live

Built-in catalogs ship with Sextant. A repository adds its own — for an in-house client
library — through `sextant.yml` ([D04](D04-config-and-exclusion.md)). Both sets are loaded
together and neither is privileged.

The active set for a module is decided by `detect.coordinates` against the dependencies
[M02](M02-detector.md) resolved. `module status` lists which catalogs were active, which
were skipped, and why.

---

## 7. Open decisions

| Decision | Blocks |
|---|---|
| Argument addressing — position only, or names where `-parameters` is present | Catalog authoring for overloaded APIs |
| Whether `fluent` needs conditional steps, for builders where one call sets several fields | The OkHttp and WebClient catalogs |
| How a catalog expresses a topic name assembled from a constant and a literal | Kafka catalogs |
| The closed set for `format`, and whether a schema-registry subject is part of it | §2c, and Avro or Protobuf on Kafka |
| Whether `resolves` needs config-sourced conditions, for a Kafka `value.serializer` in properties | §2c format resolution for Kafka |
| A `meta_annotations` capability: follow an annotation's own meta-annotations so composed annotations resolve, instead of listing each one | §2 `annotation_driven`, and every custom composed mapping annotation |
| Whether a scope rule (`@NullMarked`) may be declared on a package as well as a class, and how it interacts with `@NullUnmarked` | §2e |
| Whether the manifest reader pins framework versions, given the files are undocumented internals that may shift | §2's `filesystem` style |
| Whether a globally configured naming strategy is read from configuration, or only declared per catalog | §2f, and any module that sets one in `application.yml` |
| **How much expressiveness `address_from_config` needs before it stops being data.** Spring Cloud Stream's binding suffix depends on the functional interface, gains an index for multiple inputs, and can be overridden wholesale by `spring.cloud.function.definition` | §2d, and the Spring Cloud Stream catalog |
