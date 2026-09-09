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

requires: [call_site, string_constants]

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
| `protocol`, `direction`, `format` | From [D00](D00-fact-schema.md)'s closed sets. **Defaults** — a match may resolve them differently, see §2c. Omitted only by a NON-WIRE style, below |
| `detect` | Coordinates that make this catalog's framework rule applicable to a module, plus `required` and `satisfied_by`. **Read since Phase 2O Task 6 — by two styles, and by any catalog setting `detect.required`** — see below |
| `measured` | The artifact(s) and version(s) this catalog's rule was verified against, and the probe that verified it — §1a |
| `slice` | The part of its framework's surface this catalog does NOT read, named method by method with the reason — §1c. Optional; a catalog with none claims its framework entire |
| `requires` | Capabilities — scanner-declared or pipeline-declared (below). **If unmet, the catalog does not run and the skip is reported.** |
| `matches` | Style-specific |

**`protocol` and `direction` are omitted by a NON-WIRE style, and their absence is a claim**
(Phase 2O design §4, Task 8). Every style before that phase derives into `endpoints`, whose
identity IS `(protocol, direction, method, path)`, so a catalog omitting either is a broken
file. The two non-wire styles — `scheduled_work` and `error_advice` — derive into tables
with no such columns: work started on a clock speaks no protocol, and an exception handler
is not a boundary anyone can address. Writing one of [D00](D00-fact-schema.md)'s protocols
on those catalogs to satisfy a required field would put a wire claim in a shipped file that
nothing reads and every reader believes, which is §5.3's failure introduced deliberately.

So the loader accepts the two keys as absent, **and refuses a value outside the closed set
either way** — a typo is not an absence, and `protocol: htp` must never be read as "no wire
identity". Which styles need one is checked in `application/resolve/endpoints.py`, the one
module that knows: it refuses a wire style declaring neither and a non-wire style declaring
either, naming the file in both messages. That is the same split this document already makes
for `style` itself, and for the same reason — the loader may not import the layer that knows
what an engine does.

**Every type name a catalog writes — `owner`, `fqn`, `type` — is dotted**
(`reactor.core.publisher.Mono`), never the SCIP symbol form the fact stream uses
(`reactor/core/publisher/Mono#`). The dotted notation is sugar for the JVM symbol scheme
specifically: the conversion (`domain/symbols.type_descriptor`) becomes scheme-aware when
the first non-JVM catalog arrives, so this notation is documented as JVM sugar now rather
than ossifying as a universal one.

**Twenty-one type-name keys may name a LIST of dotted types instead of one** (§3.1). A list
means ONE library or annotation reachable under more than one name — held by its interface
(`JmsOperations` beside `JmsTemplate`, `RestOperations` beside `RestTemplate`), or under an
older package. A call site's owner is the DECLARED type, so a codebase writing the interface
produced a call site the catalog did not name and derived nothing at all, silently.

It does **not** mean two libraries: a `javax`/`jakarta` pair is two jars at two versions
needing two measurements and stays two catalogs (§3.3). Every name in a list must be measured
against the library's own bytecode before it is written — `scripts/probes/cp10_catalog_descriptors`
checks each alternate separately, because an interface declaring a SUBSET of the class's
methods would match some call sites and miss the rest.

The keys, by the engine that reads them:

| engine | keys |
|---|---|
| `single_call` | `matches.owner`, `matches.methods[].path_from_argument_type.annotation` |
| `fluent` | `matches.roots[].owner`, `matches.steps[].owner` |
| `annotation_driven` | `matches.type_annotation`, `mapping.prefix_annotation`, `reply.annotation` |
| `interface_implementation` | `matches.interface`, `registration.owner` |
| `injected_client` | `field_annotation` |
| `scheduled_work` | `annotation`, `container` |
| `error_advice` | `handler_annotation`, `status_annotation` |
| `supertype_dispatch` | `matches.supertype` |
| `derived_resource` | `no_repository_bean`, `resource_annotation`, `member_annotation` |
| `config_join` | `when.implements`, `rule.annotation` |
| `combinator` | `media_values.owner` |

**`identity_marker` and `supertype_marker` are NOT in this list**, though F2 §3.1 named them.
Neither holds a type name: each is a mapping of CALL specs
(`service_name_call: {owner, method}`), and the type name sits one level down under that
`owner`. Widening the key itself would be widening a mapping. The nested `owner` is a
candidate, and no shipped catalog needs one — the two that declare these keys name gRPC's own
descriptor classes, which have no second spelling.

Nineteen of these are F2 §3.1's own list. Two are not, and the design missed both:
`matches.steps[].owner`, widened because it sits in the same file and the same shape as
`matches.roots[].owner` and leaving one of a pair scalar would have been the inconsistency;
and `matches.methods[].path_from_argument_type.annotation`, which is what let
`spring-ws-template.yml` name both JAXB spellings rather than needing a twin catalog (W12).

The scalar form stays valid and is what almost every shipped catalog writes; this is a
widening, not a migration. `application/resolve/shapes/rooting.catalog_symbols` is the one
place that reads either form, and it refuses anything else — a mapping, a number, an empty
list — naming the file and the key. Where a widened value reaches a consumer, the variable is
PLURAL (`owners`, `handler_fqns`): the rename is what makes a consumer still comparing with
`==` fail loudly instead of comparing a string against a tuple and matching nothing.

### 1b-i. `registration.started_by` — construction is not subscription (`OI-64`)

An `interface_implementation` catalog may declare an ordered chain of calls that must
FOLLOW its registration before the registration is a boundary at all. Each step is
`{owner, method}`, linked to the previous by receiver-to-result within one method.

`google-pubsub-subscriber.yml` is why it exists. It derived a live inbound endpoint from
`Subscriber.newBuilder(subscription, receiver).build()` — construction, which subscribes
to nothing: `Subscriber` is an ordinary start/stop service and delivers no message until
`startAsync()` runs (measured, `scripts/probes/oi64_subscriber_activation.md`). Our own
acceptance fixture built two subscribers, started neither, and had both published as
endpoints the test suite asserted were correct.

**Absent, the style is unchanged**: the registration alone is the evidence, which is
right for a framework whose registration call IS the subscription. The key is opt-in
per catalog because that is a property of the framework, not of the style.

**Three outcomes, not two**, because chain reconstruction is within-method only (D00 §5):

- the chain completes in the same method → a row;
- it does not, and the built object is the method's RETURN type → a
  `registration_activation` open question. A factory that builds and hands back is
  ordinary code whose caller may start it, and answering "no boundary" would trade a
  fabricated row for a silent false negative;
- it does not, and nothing leaves the method → silence. Nobody can start it, so it is
  provably not a boundary (GUIDELINES §8: here the absence genuinely is unambiguous).

### 1c. `slice` — what a catalog does not read (F2 §3.8)

**Catalog presence used to mean completeness, and it never was.** `spring-jms-template`
reads ONE of the 37 methods `JmsTemplate` declares; `aws-sqs-sdk` reads one of
`SqsClient`'s 29 and none of `SqsAsyncClient`'s 28, so an SDK-level SQS consumer is
invisible; `spring-webflux-router` reads **none** of `RouterFunctions$Builder`'s 20, so
the builder DSL — the reference documentation's recommended Java shape since Spring 5.2
— derives nothing at all. None of those files said so, and a consumer reading the
catalog list saw "JMS: supported", "SQS: supported", "WebFlux routing: supported".

`slice.outside` is a list of `{owner, methods, why}`. All three are required, and `why`
is load-bearing rather than decorative: *"this is not a boundary"* and *"this is a
boundary we do not model"* are different claims, and a reader deciding whether a
catalog covers their code needs to know which one they are being told.

**It is checked, not merely written.** `scripts/probes/w19_catalog_surface/run.sh`
enumerates each owner's declared methods out of the jar's own bytecode, cross-references
the catalog as LOADED, and emits every unread method that can address a wire — by taking
a name at argument 0, or by taking a request object the way the AWS SDK does.
`tests/architecture/test_catalog_slice_coverage.py` requires every one of those to
appear in `slice.outside`, and requires the reverse too: an entry naming a method the
enumeration does not list is stale. So a framework release that adds an addressable
method fails the audit **once the probe is re-run and its table pasted back** — the same
arrangement `cp10_catalog_descriptors.md` uses, and the same limit: `scripts/check.sh`
does not resolve jars, so nothing re-reads bytecode on its own. The audit holds the
catalog to the last measurement, not to the current release.

**What the audit cannot check is whether the reason is RIGHT.** Only a reader can tell
whether "not a boundary" was the honest answer. What it holds is that a choice was made,
in the file, for every method — and that the distance between what a catalog claims and
what it reads cannot grow silently.

**`detect.coordinates` is read, and it gates SOME catalogs rather than the whole catalog
set** (Phase 2O Task 6, ruling R9; before it, every shipped catalog declared the key and the
loader ignored it). The value is on the `Catalog` model, and
`application/resolve/dependencies.py` applies it to the styles whose framework rule is
CONDITIONAL on the library being present — today `derived_resource` and `config_join`. Most
catalogs need no such gate: their evidence NAMES the framework (an annotation only it
defines, a call to a type only it ships), so the dependency is implied by the match itself.
`derived_resource` is the opposite case — a repository interface mentions no HTTP anywhere
— so without the antecedent there is no consequent to derive. *This paragraph said "ONE
style … today `derived_resource` alone" after `config_join` had joined the set and again
after `detect.required` shipped; it is corrected here rather than left as a document a
reader would have to disbelieve (§5.3).*

**`detect.required` (F2 §3.6) makes the coordinates a conjunct for ONE CATALOG whose style
is not gated.** Style was a proxy for "is this catalog's evidence enough to name its
framework", and `spring-stomp` / `spring-rsocket` are the pair where the proxy fails: both
claim `@MessageMapping`, and Spring's own two handlers scan for it with the identical
`@Controller` bean predicate, so no fact about the class separates them and the build is the
only discriminator there is. Setting it refuses to load without `detect.coordinates` — a
catalog requiring a dependency it does not name gates on nothing and derives nothing, which
is the silent-disable shape rather than a strict one.

**`detect.satisfied_by` names the annotations that answer the dependency question by
themselves**, and is refused without `detect.required` (it would describe a bypass of a gate
that is not there). The gate answers BEFORE any matching runs, so without this key an
annotation only one framework defines could never be the positive evidence §3.6 says it is:
a module whose build recorded no RSocket coordinate — the ordinary Maven case, where a
starter's own transitives are not recorded — derived nothing from a `@ConnectMapping` class
and asked nothing either. Declared per catalog rather than computed as "an annotation only
one catalog claims", because a rule that changes when an unrelated catalog is added is a
rule nobody can read off the file that states it.

**A gated catalog that does not derive files a question rather than going quiet**, on
either failing branch of the gate: no module fact recorded, and coordinates recorded that
name none of the catalog's. The two are one finding, because on Maven a dependency reaching
a module only as another artifact's own transitive is absent from the recorded set and
cannot be told from real absence. The question is `handler_protocol`
([D01](D01-graph-schema.md) §7), it is filed only for classes the catalog's whole match —
`type_annotation` conjunct included — would have claimed and that nothing else derived a row
for, and where two catalogs ask it about one class the rows are folded into one question
carrying both wires as candidates.

The coordinates a module's build declares reach the workspace as [D00](D00-fact-schema.md)
§5's `module` fact (`dependency_coordinates`). **Their REACH differs by build system and
is not smoothed over**: Gradle reports the resolved compile classpath, transitives
included; Maven reports the POM's own direct declarations, because the detector parses
`pom.xml` rather than asking Maven to resolve it. A gated catalog whose question cannot be
answered — no module fact recorded, or a starter arriving transitively on Maven — is
SKIPPED and reported, exactly as an unmet capability is. Making this a MODULE-WIDE
activation gate (the "active set" §12 describes) still waits on a resolved classpath under
both build systems: applied today it would deactivate a catalog like `spring-mvc.yml` on
any Maven module that declares only `spring-boot-starter-web`.

**`requires` is the mechanism that keeps degradation visible.** A catalog needing chain
reconstruction simply does not run against a scanner that lacks it, and
[M04](M04-resolver.md) reports which catalogs were skipped and why. Silently finding fewer
endpoints is the failure this prevents.

**Capabilities are scanner-declared or pipeline-declared.** Every capability above is
scanner-declared — earned once, up front, by the scanner that produced a module's facts.
`resolved_config` ([D01](D01-graph-schema.md)) is the first pipeline-declared capability:
the pipeline adds it once [M04](M04-resolver.md)'s pass 2 has run, so a catalog naming it
in `requires` does not run — and is reported skipped, the same as any unmet scanner
capability — until that pass has produced it in this run. A config-less run therefore
skips such a catalog visibly, never silently, the guarantee `requires` already gives every
scanner capability above.

---

## 1a. `measured` — the version(s) a rule was verified against

A framework rule is version-scoped, and [GUIDELINES](../../GUIDELINES.md) §5.4 says a
verdict is bounded by what it measured. A catalog is a standing verdict, so it states its
bound:

```yaml
measured:
  - { artifact: org.springframework:spring-webmvc, versions: ["6.1.6", "6.2.15", "7.0.2", "7.0.9"],
      identity: reported, by: scripts/probes/cp11_sweep_round1.md }
```

| Key | Meaning |
|---|---|
| `artifact` | `groupId:artifactId` of the archive the rule was READ OUT OF |
| `versions` | Every version of that artifact the rule was verified against, as strings |
| `identity` | `reported` \| `assumed` — where the version STRING itself came from |
| `by` | The committed probe document that measured it, repository-relative |

**`artifact` is what was opened, not what the module declares.** It is often not the
coordinate `detect` names: `spring-web.yml`'s handler gate is `spring-webmvc`'s own
`isHandler` predicate, and filing the evidence against `spring-web` would name a jar
nobody read.

**`identity` exists because of CP-5.** That probe published eight observation cells under a
version header no process had reported. `reported` means the artifact or the running
process stated the version itself — a manifest's `Implementation-Version`, a
`pom.properties`, a Boot banner — and every probe harness aborts when that self-report
disagrees with the coordinate that resolved it. `assumed` means nothing in the archive
states one at all and the value is the coordinate: Retrofit's two rows are the only
`assumed` ones that ship, because the retrofit jar states a version nowhere. The
vocabulary is closed; a third value is a schema change (NFR-5).

**A version nobody measured is never written here.** A catalog whose rule no probe has
opened declares no block at all and is listed by name in
`tests/architecture/test_catalog_measurement_coverage.py`'s audit list (§8.3), with what it
is waiting on. Writing a plausible number instead is `A-Mi8`'s own defect — a catalog
naming a version because a sibling named two — and it is the failure this block exists to
end, not a shortcut it permits.

**Its consumer is that test**, which is why there is no `Catalog.measured` field: a value
carried into the domain and read by nothing is the `detect.coordinates` defect (§5.3), and
the runtime comparison this block eventually enables — a module's RESOLVED dependency
versions (`metadata.json`'s `module.dependencies`) against the versions its catalogs
measured — is not built. The test reads the shipped YAML, refuses a malformed row, and
refuses a version absent from the version-scope paragraph of the probe the row cites.

---

## 1b. `shape_model` — the payload-type blocks, declared once

Three of the blocks below describe a **payload type** rather than a framework boundary:
§2e's `nullability`, §2f's `serialization` and §2g's `known_types`. They are not framework
knowledge in the way `matches` is — which annotation renames a field is the serialiser's
answer, and the same answer for every framework using that serialiser — and they were
duplicated across **forty-two catalogs**.

The duplication was not cosmetic. Shape expansion (`derive_shapes`) is a GLOBAL,
insert-if-absent pass keyed on the type symbol alone, outside any catalog scoping: a
payload type an HTTP endpoint and a Kafka listener both reach is described once, by
whichever catalog reached it first, and catalogs are read in filename order. **Two copies
that disagree do not produce two answers; they produce one answer chosen by a filename.**
`A-C3` is that live — `{type: java.lang.Void, wire: ""}` in thirty-three catalogs and
absent from nine, so `ResponseEntity<Void>` published an `object` response shape.

So a catalog names a model instead of carrying a copy:

```yaml
shape_model: json
```

and the model is a file in `catalogs/shape-models/`, holding exactly those three blocks
plus an `id`:

```yaml
id: json
serialization: { … }
nullability: { … }
known_types: [ … ]
```

**A shape model is not a catalog.** It declares no `style`, no `matches`, no `protocol`
and no boundary; no engine runs it, and it derives no rows. It lives in a subdirectory for
that reason — thirteen places glob `catalogs/*.yml` expecting every hit to be a catalog,
and none of them has to learn an exception. The two places that DO read the subdirectory
say so where they read it: `api._catalog_hash`, so an edit to the model changes the
analysis identity exactly as an edit to a catalog does, and
`tests/architecture/test_known_types_mirror_the_projection.py`, so the wire-type table is
still checked against the extractor's own projection.

**A catalog takes the model or declares its own, never both.** The loader refuses a file
that names a model and declares one of the three beside it, and
`tests/architecture/test_shape_model_is_declared_once.py` refuses a shipped catalog that
declares one with no model named — its allowlist is EMPTY. Between them the two close both
routes back to a private copy. A catalog whose payload-type knowledge genuinely differs
adds a SECOND model and names that; a private copy is `A-C3` waiting for a different
symbol.

**This is what makes a Jackson 2 / Jackson 3 split tractable** (Stage 6). `@JsonProperty`
kept its exact FQN across the split, so the two cannot be told apart by annotation
spelling — but `tools.jackson.core:jackson-databind` and
`com.fasterxml.jackson.core:jackson-databind` are different coordinates. On the catalog
estate that is one new file in `shape-models/` rather than eighty-four edited blocks.
**It is not by itself a two-file change**: choosing between two models per module is a
selection rule that does not exist, and nothing here pretends otherwise.

---

## 2. The styles

A style is a shape of evidence, not a framework. New frameworks reuse a style; only a
genuinely new shape needs a new engine. (Nine as of Phase 2H; `supertype_derived` and
`injected_client`, Phase 2O Task 5, are the tenth and eleventh; `derived_resource`, Task 6,
is the twelfth; `supertype_dispatch`, Task 7b, is the thirteenth; `scheduled_work` and
`error_advice`, Task 8, are the fourteenth and fifteenth.)

**Fifteen sections follow, and they are NOT fifteen engines** — §5.3 requires this document
to say which is which rather than let a reader count headings. **Thirteen have an engine**,
each registered in `application/resolve/endpoints.py`'s `_ENGINES`, which is the list a
catalog's `style:` is resolved against and the only place the answer lives. The other two
are:

- **`protocol_hint` is a resolve PASS, not an engine** — no catalog declares it, and one
  that did would be refused by name. Its own section states this and gives its position in
  the pipeline.
- **`filesystem` is SPECIFIED HERE AND NOT IMPLEMENTED.** No engine exists, no shipped
  catalog declares it, and a catalog that did would abort the resolve by name
  (`_engine_for`, called for every catalog before `endpoints_reset` runs, so nothing is
  half-emptied behind it). It is the design
  for the first non-JVM route shape and is written down so a later phase inherits the
  reasoning; nothing in it describes behaviour that runs today. Its section says so again
  at the top, in the `default_produces` model §5.3 names.

The count above therefore reads: thirteen shipped engine styles, one resolve pass, one
design. *This heading read "The thirteen styles" and the two non-wire engines had no section
at all until the 2O documentation sweep; the number counted headings, which is exactly the
substitution §5.3 forbids.*

### `annotation_driven`

The declaration is an annotation and its arguments.

```yaml
style: annotation_driven
matches:
  type_annotation: org.springframework.web.bind.annotation.RestController
  request_body: { annotation: "…annotation.RequestBody", fallback: none }
  mapping:
    path_from: [value, path]
    method_from: method
    all_methods: [GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS, TRACE]
    prefix_annotation: "…annotation.RequestMapping"
    class_level: prefix          # or `sibling`; `prefix` is the default
    annotations:
      - { fqn: "…annotation.RequestMapping" }
      - { fqn: "…annotation.GetMapping",    method: [GET] }
      - { fqn: "…annotation.PostMapping",   method: [POST] }
```

**One shape, and each annotation carries only what differs about it.** This mirrors the
framework rather than working around it: `@GetMapping` *is* `@RequestMapping` with the method
pre-set, and its own class file says so — it is meta-annotated
`@RequestMapping(method = [GET])` and declares no `method` attribute of its own.

Five rules follow, and none of them names a framework:

- **`class_level` says whether a class-level address COMPOSES with each method's**, and it is
  the one rule here about the RELATIONSHIP between the two levels rather than about where a
  value is read. Two values, and a value outside them is refused by name:

  - **`prefix`** (the default) composes them. `@RequestMapping("/api")` on the class and
    `@GetMapping("/orders")` on the method address `/api/orders`, and a WebSocket
    `@ServerEndpoint("/live")` whose `@OnMessage` methods carry no address of their own take
    the class's unchanged.
  - **`sibling`** does not. A method that names its own destination is its OWN registration
    and takes its own address whole; a method that names none still takes the class's, which
    is what keeps the handler shape working under either value.

  **Declared, not inferred from the protocol.** Measured per framework in
  `scripts/probes/w14_listener_registration.md`: `@KafkaListener` and `@RabbitListener` are
  `@Target(TYPE, METHOD)`, declare a destination at both levels, and their registrars each
  declare two paths — one taking a `Class`, one a `Method` — with neither excluding the
  other, so a class carrying both registers **two** containers on two topics. Composed, they
  published `orderspayments`, a destination no broker carries, at `resolved`. `@SqsListener`
  is `@Target(METHOD)` only, so the question cannot arise for it at all.

  The distinction the value encodes is **whether the member names a destination of its own**,
  not "messaging versus HTTP". That is why `@KafkaHandler` needs no special case: it declares
  exactly one attribute, `isDefault()`, and no destination, so both values agree about it.

  The default is `prefix` because every catalog written before this key assumed composition;
  making it required would refuse ten shipped files to state a rule nine already follow. A
  messaging catalog must therefore declare `sibling` explicitly rather than rely on anything.
  The value is refused in `derive_endpoints`'s pre-flight, before any table is emptied — an
  engine-level check would not fire at all for a catalog skipped on capabilities.

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
temporary duplication for *framework-internal* composition (`@GetMapping` = `@RequestMapping`
with the method pre-set) — those class files live in unscanned jars, out of reach until
dependency scanning exists. Recorded in §7.

**A project's own composed annotations resolve for free, as of Phase 2E.** An `@ApiGet` built
from `@RequestMapping` lives in this module's own scanned bytecode, so the effective-annotations
pre-pass (`resolve/effective_annotations.py`, spec §2, §3) widens the mapping-annotation set to
every module-local annotation type transitively meta-annotated with one of the catalog's own
declared fqns, before this table is ever consulted — no catalog author hand-copies a project's
own composition. The jar half above is what remains open — narrowed rather than closed by
Phase 2I: `.sextant.yml` (§4a) scans a NAMED library's own bytecode, so a framework
jar's class files are no longer unreachable in principle, but nothing has been tested
against a framework jar and no shipped catalog stops hand-copying its table.

**Outbound annotation clients generalise the same vocabulary rather than needing a new
style.** Three parts of the shape above, previously assumed constant, become catalog data:

```yaml
matches:
  # Optional: a catalog may declare no type-level gate. Any type containing a
  # matching mapping annotation then participates (a Retrofit interface has no
  # type-level marker at all).
  type_annotation: org.springframework.cloud.openfeign.FeignClient
  # The body rule is catalog data: which annotation marks the payload
  # parameter, and whether the sole unannotated parameter is the fallback.
  request_body: { annotation: org.springframework.web.bind.annotation.RequestBody,
                  fallback: sole_unannotated }   # or: none
  mapping:
    prefix_annotation: org.springframework.cloud.openfeign.FeignClient
    # Type-level and method-level annotations are different roles. On
    # @RequestMapping, value/path are aliases meaning *path*; on @FeignClient,
    # value aliases *name* — the service id — and only path means prefix. One
    # shared alias list conflated the two roles by the luck of @RequestMapping's
    # aliasing; prefix_from and peer_from name them separately.
    prefix_from: [path]
    peer_from: [name, value]
    path_from: [value, path]
    ...
```

- **`type_annotation` is optional.** A Retrofit interface carries no type-level marker at
  all; it is recognised by its `retrofit2.http` method annotations alone. Where the catalog
  declares none, any type containing a matching mapping annotation participates, and the
  controller join — `type_annotation: …RestController` in the opening example — simply
  disappears for that catalog.
- **`request_body` is catalog data**, not an engine assumption: which annotation marks the
  payload parameter, and whether the sole unannotated parameter is the fallback when none is
  marked. Spring inbound and `@HttpExchange` require `@RequestBody` with no fallback;
  Retrofit requires `@Body` with no fallback; Feign's Spring-flavoured contract accepts
  `@RequestBody` but falls back to the sole unannotated parameter when it is absent.
- **`prefix_from` and `peer_from` replace the single `path_from` alias list at the type
  level**, because the type-level and method-level annotations play different roles.
  `path_from` still serves method mappings, where it is correct: `@RequestMapping`'s
  `value`/`path` are `@AliasFor` each other, both meaning *path*. But `@FeignClient`'s
  `value` aliases `name` — the service id, sourced through `peer_from` — and only `path`
  means prefix; reading it through the shared list would turn the service name into a URL
  prefix on every Feign endpoint. `prefix_from` and `peer_from` name the two roles
  separately, so `@RequestMapping` declares `prefix_from: [value, path]`, `@FeignClient`
  declares `prefix_from: [path]` and `peer_from: [name, value]`, and `@HttpExchange`
  declares `prefix_from: [value, url]`.
- **`path_separator` says what joins the prefix to the address it prefixes**, and it is
  the character deduped at that seam. Optional; a catalog declaring none concatenates the
  two halves bare, which is what every catalog did before the key existed.

  ```yaml
  mapping:
    prefix_from: [value, path]
    path_separator: "/"   # the seam joins with exactly one, whichever half spelled it
  ```

  It is **catalog data for the same reason `qualifier_separator` is**: whether two address
  fragments join with a separator, and which, is the framework's convention. A path-addressed
  framework composes a class prefix and a method path into a sequence of segments, and the two
  halves are written by two different authors who each decide independently whether to spell
  the separator — Spring joins them with **exactly one `/` however they were written**. A
  broker-destination catalog has no such composition: `spring-kafka.yml`'s prefix is a
  class-level `@KafkaListener`'s *topic name*, which has no segments, and a `/` inserted into
  one would invent a destination no broker carries. So the key is **opt-in, never an engine
  default**, and `spring-kafka.yml` says in place why it declares none.

  **Declaring no separator was not the same as declaring no composition, and that gap was a
  live fabrication.** With `path_separator` absent the seam stayed a bare concatenation, so a
  class-level `@KafkaListener("orders")` and a method-level one on `payments` composed to
  `orderspayments` — a topic no broker carries, at `resolved`. The separator key answers "with
  what do the halves join"; it cannot answer "do they join at all". `class_level: sibling`
  answers the second, and the two keys are independent: a `sibling` catalog needs no separator
  because it never joins, and a `prefix` catalog without one joins bare, which is right where
  the halves are meant to abut.

  Two forms were derived wrong while the seam was a bare concatenation, both ordinary Spring
  and both found live against `spring-petclinic-microservices`:
  `@RequestMapping("/api/gateway")` + `@GetMapping("owners/{ownerId}")` published
  `/api/gatewayowners/{ownerId}` where Spring serves `/api/gateway/owners/{ownerId}`, and
  `@RequestMapping("/")` + `@PostMapping("/chatclient")` published `//chatclient` where Spring
  serves `/chatclient`. An address nobody serves, emitted at `resolved`/`compiler` where
  nothing downstream can tell it from something observed, is the **same
  confidently-wrong-address class `path_fallback` closes from the other direction**.

  **An empty half takes no separator with it.** An absent prefix leaves the address exactly as
  written — a slashless name does not gain a leading `/` the engine would be inventing — and
  an empty suffix (`@KafkaHandler`, `@OnMessage`: annotations carrying no path attribute at
  all) leaves the prefix alone. **The separator is a single character**, refused at load
  otherwise: the dedupe is `rtrim`/`ltrim`, which trim a *set* of characters, so a longer
  separator would strip each of its characters individually.

  > **OVERTURNED for an INBOUND `protocol: http` catalog (2O design §8, Phase 2O Task 2, as
  > narrowed by ruling R8).** The rule above is about the JOIN, and the join still inserts
  > nothing into an empty half. What changed is what happens *after* it for a catalog whose
  > addresses are URLs the module SERVES: the composed address is canonicalized into **the
  > URL the framework serves** — leading separator guaranteed, one separator per boundary,
  > trailing separator preserved as distinct — because `@RequestMapping("users")` and
  > `@RequestMapping("/users")` are the same URL to Spring (checkpoint CP-1, confirmed live
  > against Boot 4.0.1) and recording them as two identities splits dedup and every
  > path-keyed anchor downstream. So a slashless inbound HTTP mapping DOES end up with a
  > leading `/` — from the canonical gate, which knows it is looking at a served URL, and
  > never from the seam, which does not.
  >
  > **Scoped to INBOUND `http`, and to path-shaped values.** STOMP, websocket and every
  > messaging composition keep the rule above unchanged: a topic is not a URL, and a `/`
  > invented into one names a destination no broker carries. GraphQL is out for the same
  > reason from the other end — its address is a FIELD NAME. **Client-side HTTP is out too**
  > (R8): a `@GET("legacy/invoices")` on a client interface is resolved against the
  > configured base address's own path, while `@GET("/legacy/invoices")` is root-relative —
  > against `https://host/v1/` those are different URLs on different services, so
  > canonicalizing one would rewrite an address rather than normalize a spelling. CP-1 is
  > evidence about a server, and applying it to client composition is the approximation DR-6
  > forbids. Inside inbound `http`, a `path` holding a whole address or a
  > placeholder-bearing composition (`https://${billing.host}/orders`) is untouched; D02
  > keeps those whole until the peer join splits them, and prefixing one would publish a URL
  > nobody serves. The gate is `sextant.domain.paths::serves_urls` and the rule is
  > `canonical_http_path` beside it, with a mirror in `derive_endpoints.sql` (whose address
  > is composed from columns that layer never sees) pinned against both by a test that runs
  > every protocol/direction combination.

  **It is not the qualifier seam, and does not touch it.** `qualifier_separator` joins a scope
  to the member it qualifies and dedupes nothing, because both halves are written by one author
  on one annotation and neither ever spells the separator. The two remain separate rules; a
  catalog may declare both, and the GraphQL catalogs — which declare only the qualifier one —
  are unchanged by this key existing.

  Declared today by every catalog whose addresses are URI-style paths and whose type-level
  annotation can carry a prefix: `spring-web.yml`, `spring-mvc.yml`,
  `spring-cloud-openfeign.yml`, `spring-http-interface.yml`, `spring-stomp.yml` (a STOMP
  destination composes through the same `AntPathMatcher` separator, `/` by default) and
  `jakarta-websocket.yml`. `retrofit.yml` declares none because it declares no
  `prefix_annotation` either — it has no seam to rule on.

Covers Spring Web, JAX-RS, Spring Kafka, JMS listeners, and JAX-WS — inbound; Spring Cloud
OpenFeign, Spring 6 `@HttpExchange`, and Retrofit — outbound.

**Messaging listener catalogs generalise the annotation vocabulary a third time**, this
time for a destination that carries no verb.

- **A multi-valued destination attribute** (`@KafkaListener(topics = {"a", "b"})`) derives
  one endpoint per listed value — the `all_methods` precedent above, extended from verb to
  identity: an annotation naming several destinations means several endpoints, not one
  endpoint with an unresolved destination.
- **`all_methods: []` declares a verbless protocol.** A topic has no verb to enumerate, so
  the catalog states an empty set rather than a method list: one row per mapping, `method`
  NULL, and `resolution` untouched by the absence — the destination was read either way.
- **The `reply` block** `{annotation, destination_from, payload: return}` derives one
  additional outbound row per listed reply destination named on the annotation — one row
  per destination, mirroring the multi-valued rule above. The reply row's `caller` is the
  handler method, and its request payload is the handler's own return type. A
  value-returning handler with no reply annotation still derives one outbound row, with
  `path` NULL and `resolution: unresolved`: the handler is known to answer something, only
  where it answers is not. A `void` handler derives no reply row — there is nothing to
  send.

`request_body` gains an `excludes: [<fqn types>]` sub-key: parameters of these types are
ignored by the `sole_unannotated` fallback count. A listener taking `(OrderEvent event,
Acknowledgment ack)` has two unannotated parameters, and without `excludes` the fallback
would honestly find none; naming `Acknowledgment` there lets the fallback see the one real
payload. This lives under `request_body` rather than as a separate top-level
`payload_excludes`, because it is the same fallback rule this key already governs.

**`mapping` gains `consumes_from`/`produces_from`, two more alias lists reading declared
media types (`endpoints.consumes`/`endpoints.produces`, [D01](D01-graph-schema.md) §4's
evidence kind (a)).**

```yaml
mapping:
  consumes_from: [consumes]
  produces_from: [produces]
```

- **Same scalar-or-array read as `path_from`, first present alias wins.** A mapping
  annotation whose `produces()` is a plain `String` and one whose `produces()` is a
  `String[]` both read correctly; the values that survive are sorted and de-duplicated
  before landing in the column ([D01](D01-graph-schema.md) §4's order-normalisation, NFR-1)
  — a catalog author never orders these by hand.
- **A catalog declaring neither key reads nothing.** `consumes_from`/`produces_from` both
  default to an empty alias list, and an empty list matches no attribute, so the column is
  `NULL` — absence is not a licence to invent a default. This is why every catalog that
  predates this key keeps deriving `NULL` with zero YAML change.
- **`default_produces` is read since Phase 2O Task 6; `default_consumes` is still
  specified-not-used.** `default_produces` is read as a **top-level catalog key**, not
  under `mapping` where this bullet first sketched it: the catalog that finally needed it
  (`spring-data-rest.yml`) declares no `mapping` at all — its rows come from a framework
  rule rather than from annotation attributes — and the contract belongs to the framework,
  not to any one annotation. `derived_resource` refuses a catalog of its own style that
  declares none, since nothing else could fill `produces` for a row no mapping wrote.
  What follows is the original statement of the pair, which still holds for
  `default_consumes`:
- **`default_consumes`/`default_produces` are specified here, not yet used**: a
  catalog-declared framework-contract default ([D01](D01-graph-schema.md) §4's evidence kind
  (b)) — a media type the framework enforces whenever a mapping declares none itself, rather
  than one read off any single annotation attribute. `spring-web.yml` and `spring-mvc.yml`
  deliberately declare neither key: Spring negotiates an undeclared mapping at runtime rather
  than enforcing a contract default, so filling one in here would misrepresent an undeclared
  mapping as a declared one. Left for the catalogs that do carry a real framework-contract
  default to declare when they are added.
- **Type-level media attributes are not read in 2E.** A class-level
  `@RequestMapping(produces = ...)` — Spring's own equivalent of `prefix_from` for media —
  is out of scope for this phase; only the method-level mapping annotation's own attributes
  fill `consumes`/`produces`.

**Phase 2H generalises the vocabulary a fourth time, for a declaration whose name is
DEFAULTED and whose scope sits on the annotation itself.** Four keys, every one of them
optional and inert unless declared, so every catalog written before them derives
byte-identically:

```yaml
mapping:
  path_fallback: construct_name        # the declared name when every path_from alias is absent
  qualifier_from: [typeName]           # the SCOPE, read off the SAME annotation
  qualifier_separator: "."             # what joins a scope to the name it qualifies
  annotations:
    - { fqn: "…annotation.SchemaMapping", requires_qualifier: true }
```

- **`path_fallback` says what the declared name is when every `path_from` alias is
  absent.** Today's one word is `construct_name` — the annotated construct's own name —
  and it is a closed vocabulary rather than a boolean, so a second source is a new word
  here and an unrecognised one is refused. It exists because **an omitted attribute is not written into the annotation USE**
  — the declared default lives on the annotation TYPE (JVMS 4.7.22 `AnnotationDefault`,
  readable since W4) and never on the use that left it out, so a use reads NULL there:
  Spring GraphQL, DGS and MicroProfile all
  declare their field attribute `default ""` and all three mean "the method's name", so
  an absent attribute read as an empty string published a `resolved` endpoint addressing
  nothing — `path_from`'s own "wrong output rather than a missing one" failure reached by
  a second route. The fallback fires only on an empty suffix, which is the same fact as
  "every alias was absent".
- **`qualifier_from` reads a SCOPE off the same annotation that carries the name**, first
  present alias wins, scalar-or-array like every other read here, and
  `qualifier_separator` states what joins the two. It is deliberately not `prefix_from`:
  that reads a TYPE-level annotation through an entirely different join and composes under
  a separator rule of its own (`path_separator`, above), which dedupes the seam where this
  one does not. `@SchemaMapping(typeName = "Order", field = "lines")` composes
  `Order.lines`; a `@QueryMapping` carrying no `typeName` composes nothing. **The
  separator is catalog data and never a literal in the engine** — which punctuation
  separates a scope from a member is a framework's convention — so `qualifier_from`
  declared without a usable separator is refused, an explicitly EMPTY separator with it
  (`Parentmember` is not a composition anyone declared), and `qualifier_from` without
  `path_fallback` too, since a scoped declaration naming no member would compose a
  dangling `Parent.`.
- **`requires_qualifier: true` on one annotation entry says the annotation names a member
  OF a scope**, so a declaration under it has no address at all until the scope is found.
  Where neither the annotation nor its enclosing type states one, **the row is not
  derived**: the bare member name would read as a top-level identity, which is a
  different endpoint from the one the code declares, and `resolved`/`compiler` beside it
  would present that as observed. Silence is the honest answer — Spring can infer a
  resolver's parent type from a parameter, and that is a fact no annotation carries.
  Absent (false) on every annotation shipped before it.
- **A class-level annotation may state the qualifier once for every method the type
  declares**, read one level out through the same attribute list and the same join
  `prefix_from` uses. **The method's own value wins where both are present** — the nearer
  declaration is the more specific, which is the precedence every framework carrying both
  levels keeps. A type-level annotation still mints no row of its own, which is what lets
  one annotation play both roles without colliding with itself (the `prefix_annotation`
  precedent, unchanged).

**Phase 2I generalises it a fifth time, for a scope that composes into ONE token and a
scope whose ABSENCE the framework's own spec defines.** Two more keys, both optional and
both inert unless declared:

```yaml
mapping:
  qualifier_from: [namespace]          # the SCOPE, as before
  qualifier_format: qname              # …composed `{scope}name`, not `scope<sep>name`
  namespace_default: reversed_package  # …and what the scope IS when the attribute is absent
```

- **`qualifier_format` states a WHOLE composition where no single character can.** Today's
  one word is `qname` — the XML-namespace notation `{scope}name`, one bracketed token
  whose closing brace has no separator equivalent at all, which is precisely why it could
  not be spelled as a `qualifier_separator` (that key is refused unless it is exactly one
  character, because the seam dedupe trims a SET of characters). A closed vocabulary for
  `path_fallback`'s reason. **It is mutually exclusive with `qualifier_separator`**: two
  composition rules for one seam is one too many, and a file declaring both states no
  preference, so it is refused rather than resolved by a precedence nobody wrote down.
  `@PayloadRoot(namespace = "…/ws", localPart = "placeOrderRequest")` composes
  `{…/ws}placeOrderRequest`; an annotation on the same catalog carrying no `namespace`
  attribute composes no braces at all, which is what lets one mapping block carry two
  identity forms (a QName and an opaque action URI) with no engine branch.
- **`namespace_default` says what the scope is when the attribute carrying it is absent.**
  Today's one word is `reversed_package`: `"http://"` + the DECLARING TYPE's package
  tokens reversed and dot-joined + a trailing `"/"`, so `com.example.orders.soap` yields
  `http://soap.orders.example.com/`. It is a fact rather than a guess because the JAX-WS
  spec DEFINES that default — pinned against both reference implementations, which agree
  character for character (Phase 2I Task 2 checkpoint item 2). Two rules keep it honest.
  **It fires only where the scope-carrying annotation was actually found on the type**, so
  "attribute absent" and "annotation absent" stay different things — otherwise any class
  holding a matching method would be minted an endpoint. And **a class in the DEFAULT
  package derives NO scope**, because both implementations return null there: that
  refusal is part of the pinned algorithm, not a gap in it. A catalog declaring no
  `namespace_default` gets no scope, never a plausible-looking one (DR-6). Like
  `qualifier_format`, either word declared without `qualifier_from` is refused — both
  describe a scope, and neither means anything on a catalog that reads none.
- **The scheme lives in the engine, not the query.** `storage/` may not name a protocol
  (ARCHITECTURE §10), and a URI scheme is one, so `annotation_driven.py` maps the declared
  word to a `printf` template and the SQL composes only the package half into it.

**Phase 2I generalises it a sixth time, for a framework that exposes what a class DECLARES
rather than what an author marked, and for one that WITHDRAWS a declaration it marked.**
Two more keys, both optional and both inert unless declared:

```yaml
mapping:
  members: public_methods              # the class gate exposes the construct's public members
  annotations:
    - { fqn: "…jws.WebService" }                      # the gate, and the scope
    - { fqn: "…jws.WebMethod", requires_qualifier: true,
        unless: { attribute: exclude, equals: true } }  # …withdrawn where the flag says so
```

- **`members` says what a gated class exposes on its own, with no member-level annotation
  anywhere.** Today's one word is `public_methods`. It is the only word in the mapping
  block that derives rows for declarations carrying **no annotation at all**, which is why
  it is the most tightly fenced. **A member-level rule overrides it for the member it
  names** — one row per member, never two — and the override is keyed on the member
  *carrying* one of the catalog's annotations, not on that rule having produced a row:
  otherwise a declaration removed by `unless` below would be silently re-derived under its
  own construct name, making every withdrawal a no-op on a gated class.
- **Four things are not exposed members**, each excluded for a reason rather than a taste:
  a **constructor** (`construct_kind` says so, and the derivation admits only methods and
  functions), a **static** method (bound to the type, not to an exposed instance), a
  **synthetic** method (compiler machinery nobody wrote — and unlike fields, synthetic
  methods deliberately DO reach the fact stream, because the inheritance walk's bridge rule
  needs them), and a **non-public** one. The last two modifiers are read from `symbols.
  modifiers`, defaulted false where a scanner reports none (D00 §5a).
- **The gate is what makes the rule safe rather than catastrophic**, so it is checked:
  `members` is refused with no class gate at all, and refused without `path_fallback`,
  since a member carries no annotation and therefore no name attribute — every member row
  would compose the empty address. The gate may be the single `type_annotation`, or one of
  the catalog's own `mapping.annotations` found on a TYPE (the same type-level join a
  class-level qualifier reaches methods through) — which is the only form that can carry
  **two spellings of one gate**, since `type_annotation` is one fqn. That is how a
  `javax`/`jakarta` pair is gated without an engine change, and it closes for a scope the
  javax boundary a single-valued `prefix_annotation` still leaves open for a prefix.
- **`unless: {attribute, equals}` on one annotation entry withdraws the declarations the
  framework itself withdraws.** A closed SHAPE — exactly those two keys, anything else
  refused — rather than a closed vocabulary, because *which* attribute withdraws a
  declaration and at *which* value is the framework's convention. **An absent attribute is
  never the withdrawing value**: an omitted attribute is not written into the annotation
  USE — the declared default lives on the annotation TYPE (JVMS 4.7.22, readable since
  W4) — so the attribute reads NULL wherever it was left alone, and only a value actually
  written out withdraws anything. The comparison happens on the text `json ->>` reads every scalar
  back as, so a YAML `equals: true` matches a real JSON boolean in the bytecode without
  either side guessing at the other's type.

**Phase 2I generalises it once more, at `matches` level rather than inside `mapping`,
because the question is about the DECLARATION SITE rather than about naming:**

```yaml
matches:
  declared_on: interface     # …or `class`; absent applies the rules to either
```

- **`declared_on` confines a catalog's rules to declarations enclosed by one kind of
  construct.** It exists because one annotation family can mark two opposite things: a
  JAX-WS `@WebService` marks both the class that SERVES an operation and the generated stub
  INTERFACE through which a module CALLS one, and those are opposite directions of the same
  wire identity. Without it each of the two catalogs derives both rows, the pair then
  merges (§3), and a module is published as calling the very operations it serves. With it
  the annotation is partitioned between the two files and neither reaches the other's
  declarations.
- **A closed set of two words, `class` and `interface`**, and deliberately not the whole of
  D00's construct set: only a type encloses the methods this style derives from, so a
  member kind here would gate every row out and let a file say "this catalog derives
  nothing" by accident. An unrecognised word is refused rather than read as "no gate",
  because that reading is the dangerous one — it republishes a served operation as a called
  one.
- **Absent means either**, which is what every catalog written before this word declares,
  and what keeps their derivations byte-identical.
- **An OUTBOUND catalog declaring `declared_on: interface` subtracts every interface the
  module's own classes implement** ([D00](D00-fact-schema.md) §5a's
  `implemented_interfaces`). This is not extra vocabulary — it is what the gate already
  *means*, made true. Such a catalog describes client stubs, declarations whose whole
  content is "somebody else answers this"; an interface the module implements is the
  opposite claim, and one annotation family marks both (a `wsimport` stub and a
  hand-written service endpoint interface are annotated identically). Without the
  subtraction the pair derives an outbound row from the interface and an inbound one from
  its implementing class, the two merge (§3), and the module is published as CALLING an
  operation it only serves. With it the operation derives exactly once, from the
  implementing class, since a class-gated inbound catalog is untouched. **Scoped to the
  interface gate rather than to every outbound catalog**, deliberately: a Spring Cloud
  `@FeignClient(fallback = …)` names a local class implementing the client interface, and
  that interface is still a client — widening the rule would delete every Feign client
  declaring a fallback.
- **It YIELDS to a `resolves.direction` rule** (§2c, 2O Task 10). Where the catalog resolves
  a row's direction, the fence's coarser test — SOMETHING implements this interface — has
  already been answered more precisely, and subtracting the row would delete exactly the one
  the resolution flips. The subtraction stands wherever the resolution declines, and stands
  unchanged on every catalog that declares no resolution at all.

**Three catalogs, one engine change.** The forms are stated in framework-neutral words for
a reason that was tested rather than asserted: `spring-graphql.yml` introduced them, and
`netflix-dgs.yml` and `microprofile-graphql.yml` then rode them with **zero further engine
change** — DGS spells the scope `parentType` where Spring spells it `typeName`, and
MicroProfile has no scope at all, and all three differences are one line of YAML each.
That is §4's acceptance test run early, on one protocol, which is why the vocabulary grew
here instead of three framework special cases growing in the engine.

**Phase 2O generalises it one last way, and the generalisation is that a catalog may derive
NO ROWS AT ALL.** `corroborates` sits at `matches` level beside `mapping`, and a catalog
carrying it *without* a `mapping` derives nothing whatever — its entire contribution is
`service_identity` open questions:

```yaml
matches:
  corroborates:
    class_annotations:
      - org.springframework.grpc.server.service.GrpcService
      - net.devh.boot.grpc.server.service.GrpcService
```

- **Why an annotation can be real evidence and still mint nothing.** `@GrpcService` marks a
  class as serving something and names NOTHING else — no address, no verb, no member rule.
  The wire identity comes only from the generated class's own constants, which
  `supertype_derived` (below) reads. A row derived here would carry an invented address, so
  none is.
- **What it buys is the one case that style cannot reach**: a service implemented against a
  PUBLISHED stubs jar. The extends edge is the module's own fact, but the generated
  supertype's facts never arrive, so `supertype_derived` derives nothing at all — and
  without this block the outcome is SILENCE, which 2O design §1b rules out in as many words.
  A flagged class that no endpoint of this catalog's protocol names as a handler surfaces as
  a `service_identity` question instead, filed by the engine's `gaps` entry point through
  `resolve/service_identity.py` (the same hand-off `supertype_derived` and `injected_client`
  use, and the reason it is a separate pass: the ledger is reset AFTER endpoint derivation).
- **A flagged class the match DID derive files nothing.** The corroboration asks one
  question of the finished table — "does any endpoint of this protocol name a method of this
  class as its handler?" — and is silent when the answer is yes. A version that filed
  regardless would put every correctly derived service in the ledger.
- **Inert for every catalog that declares none**, which is every catalog written before it:
  `gaps` returns an empty list and `run` is untouched. Malformed is REFUSED, not ignored —
  an unread key is indistinguishable from a typo, and a typo here silently restores the
  silence the block exists to remove.

**The 2026-09-06 vocabulary pass adds three words at once, and the "at once" is the point.**
Every generalisation above arrived alone, against whichever framework was in front of its
author — which is how a style **21 catalogs** share reached a state where three of them knew
their framework's rule exactly and could not say it. GUIDELINES §13.8's third-occurrence rule
fired on that (`docs/open-issues.md`, "The §13.8 stop rule fired in Stage 4"), and these three
words are its answer. **No word here is speculative: each names the measurement that forces
it**, and a fourth need found later re-triggers §13.8 rather than being pre-solved.

```yaml
mapping:
  path_from: [value]                        # …as before: the MATCHED annotation's aliases
  path_from_siblings:                       # …then these, in order, if none of those is present
    - { annotation: org.eclipse.microprofile.graphql.Name,        arg: value }
    - { annotation: jakarta.json.bind.annotation.JsonbProperty,   arg: value }
  path_fallback: construct_name             # …then this, as before — now a DEFAULT
  annotations:
    - { fqn: "…graphql.Query",    method: [query],    path_fallback: read_accessor_property }
    - { fqn: "…graphql.Mutation", method: [mutation], path_fallback: write_accessor_property }
    - { fqn: "…annotation.RabbitListener", container: "…annotation.RabbitListeners" }
```

- **`container` names the container annotation whose `value` array holds uses of that
  annotation** — the `scheduled_work` style's own key, one style over, and the same rule.
  **Forced by CP-16** (`scripts/probes/cp16_listener_destinations.md`, rows 2a–2f and 4a–4f;
  six versions across three frameworks): `@KafkaListener`, `@JmsListener` and
  `@RabbitListener` are each `@Repeatable`, and each framework's post-processor reads the
  container. javac writes the container and **not** the member (JLS 9.7.5), so a method
  carrying two listeners carries no listener annotation at all, the mapping join matches
  nothing, and **both** destinations vanish — silently, beside a single-listener neighbour
  that derives normally (`OI-36`). The engine reads each container use's `value` array and
  synthesizes one ordinary `{target, annotation, args}` row per folded use, before
  composition and before inheritance, so a folded use is an ordinary annotation everywhere
  downstream and **there is no container in the query at all**.
  - **The container need not be javac's, and this key does not ask whose it is.** CP-17
    (`scripts/probes/cp17_containers_and_class_level.md`, rows 2a/2b, 3a/3b and 6a/6b, at
    spring-pulsar 1.2.11 and 2.0.7) measured a framework that ships the container SHAPE
    without the language mechanism: `@PulsarListener` is **not** `@Repeatable`, and
    `@PulsarListeners` is an ordinary annotation declaring `value(): PulsarListener[]` for
    an author to write by hand. Its post-processor then registers the **union** of a direct
    `@PulsarListener` and every member of the container. A class file cannot tell the two
    mechanisms apart — the bytes are identical — so the engine reads them identically, and
    the union is what a real row plus the synthesized ones already are. This wording was
    narrower than the key until CP-17 measured the case; the key itself did not change.
  - **`value` is not catalog data.** JLS 9.6.3 requires a containing annotation type to
    declare exactly `value()` returning an array of the repeatable type, so it is the
    *language's* word; a key for it would let a file state something Java forbids. A
    hand-written container is under no such obligation, and one declaring its array under
    another name is unreadable here — a stated boundary in `docs/COVERAGE.md`, not a key.
    Each entry of the array is checked against the declared member fqn rather than taken on
    position — a container is an ordinary annotation whose `value` happens to be an array.
  - **Declared per ANNOTATION ENTRY, not per catalog**, and that is where the difference
    lives: `scheduled_work` names one annotation, this style names a list, and an entry
    claims a container only where one was measured. CP-16 measured `@Repeatable` on the
    listener annotations only; **CP-17 then measured the four the audit left open** (rows
    2e–2l, 3e–3l) and found `@SqsListener` in all three spellings, `@KafkaHandler` and
    `@RabbitHandler` neither repeatable nor accompanied by a container-shaped sibling — so
    those entries' silence is now a measured claim rather than an absence of evidence.
  - **It needs extractor capability 9.16** (`nested_annotation_args`), because a folded use
    is a nested annotation. A catalog declaring a container therefore `requires` it, for
    `spring-scheduling.yml`'s stated reason: a scanner that cannot read one must skip the
    catalog **visibly** rather than report part of a module's listener surface and stay
    silent about the rest.

- **`path_from_siblings` names name sources that live on OTHER annotations of the same
  declaration**, consulted **in the order written** and only where every `path_from` alias
  is absent. **Forced by CP-15** (`scripts/probes/cp15_mp_graphql_names.md`, rows 1a–1b and
  2a–2b): `OperationCreator.getOperationName` consults five sources in order and takes the
  first with a value — the operation annotation's own `value`, then `@Name`, then the
  `jakarta` and `javax` spellings of `@JsonbProperty`, then Jackson's `@JsonProperty`.
  `microprofile-graphql.yml` read the first alone, so `@Query @Name("allOrders")
  List<Order> orders()` was served as `allOrders` while we published `orders` — a wrong
  address, not a missing one (`OI-35`).
  - **The order is the rule, not a presentation detail.** The `iconst_N` indices of the
    source array ARE the order, and a set would not say which name a declaration carrying
    two of them is served under. So the key is a list, and the engine carries an ordinal.
  - **`path_from` first, then these, then `path_fallback`** — which is exactly the measured
    order, since row 1 puts the matched annotation's own value at index 0. **A framework
    that consulted a sibling BEFORE the matched annotation's own attribute cannot be stated
    in this grammar**; the boundary is in `docs/COVERAGE.md` rather than left silent, and a
    framework needing it is a fourth measurement, not a key to add now.
  - Read scalar-or-array, first present wins, like every other attribute read in this style.
    A closed SHAPE (`annotation` and `arg`, nothing else) rather than a closed vocabulary,
    for `unless`'s reason: which annotation renames an operation is the framework's own
    convention.

- **`path_fallback` on an ANNOTATION ENTRY overrides `mapping.path_fallback` for the
  declarations that annotation matches**, and **two new words join the closed vocabulary**:
  `read_accessor_property` and `write_accessor_property`. **Forced by CP-15 rows 3a–5b**,
  row 5 *compiled and run* against both jars: the un-named-operation fallback is
  `MethodHelper.getPropertyName`, and **which transformation it applies is chosen by which
  operation annotation matched** — `@Query`/`@Subscription` take `Direction.OUT`, which
  strips `get` and `is`; `@Mutation` takes `Direction.IN`, which strips `set` and nothing
  else. One catalog-level word therefore makes one of the two annotations newly wrong,
  which §8.1 rule 1 forbids in as many words — that is why `OI-5` shipped a
  measured-and-wrong address for a month rather than a plausible fix.

  | word | strips | measured (CP-15 row 5) |
  |---|---|---|
  | `construct_name` | nothing | the construct's own name — unchanged, the word every catalog already declares |
  | `read_accessor_property` | `get`, `is` | `getOrders→orders`, `isActive→active`, `getX→x`, `get→get`, `gettotal→gettotal`, `getURL→uRL`, `setStatus→setStatus` |
  | `write_accessor_property` | `set` | `setStatus→status`, `getOrders→getOrders` |

  - **The strip's three conditions are the framework's own**, not a paraphrase that fits the
    examples: the name starts with the prefix, is **longer** than it, and carries an
    **upper-case character at the seam** — then the remainder is taken with its **first
    character** lowercased, never the whole of it. `getURL → uRL` is the case that tells
    this rule apart from every plausible paraphrase, and any encoding that does not
    reproduce it is not this rule.
  - **Which prefixes belong to which word is engine data**, the `namespace_default`
    precedent: a closed-vocabulary word owes the derivation a rule as well as a name, and
    the accessor prefixes are the *language's* bean convention rather than any framework's
    naming choice. What a catalog states is which direction an annotation faces, which is
    the framework's own fact.
  - **The catalog-level key stays**, as the default every entry declaring no override
    carries — so a catalog written before this word binds one value on every entry and
    derives byte-identically — and as the **only** word an unannotated `members` row can
    read, since such a row has no annotation to read an override off.

### `single_call`

One call carries the whole declaration. Arguments are addressed by position or name.

```yaml
style: single_call
matches:
  owner: org.springframework.web.client.RestTemplate
  methods:
    - { name: postForObject, http_method: POST, url_arg: 0, body_arg: 1, response_arg: 2 }
    - { name: getForObject,  http_method: GET,  url_arg: 0, response_arg: 1 }
    - { name: exchange,      method_arg: 1,     url_arg: 0, body_arg: 2, response_arg: 3 }
```

Each `methods` row is `{name, arity?, descriptor?, http_method | method_arg | neither,
url_arg | channel_arg, body_arg?, response_arg?, record_arg?, direction?,
path_from_argument_type?}`,
beside the catalog-level `default_address?` both described below.
**`http_method` is a literal when the catalog already knows the verb** — `postForObject` is
always a POST, so the catalog states it once. **`method_arg` is a position when the call
site carries it instead** — `exchange`'s verb is its own `HttpMethod` argument, an
`enum`-kind entry ([D00](D00-fact-schema.md) §5), so the catalog names the slot and the
engine reads the resolved value per call rather than assuming one. When a `method_arg`
slot cannot be resolved — the verb arrives in a parameter — the row still derives, with
`method` NULL and `resolution` `unresolved`: the call was made, only its verb is unread.
`body_arg` and
`response_arg` are optional: `getForObject` has no request body, and a `void`-returning
call has no response to root.

**`arity` restricts a row to call sites with exactly that many arguments.** A row without
it matches every overload, so the shipped 2C catalogs parse unchanged; a catalog that
needs to tell `send(topic, payload)` from `send(topic, key, payload)` apart writes one row
per arity instead.

**`descriptor` restricts a row to ONE overload, by argument type.** Arity cannot separate
`convertAndSend(String routingKey, Object message)` from `convertAndSend(Object message,
MessagePostProcessor after)` — same name, same owner, same count — and where a row reads an
ADDRESS out of a position, matching the wrong one publishes a message payload as a wire
destination. The value is the overload's erased JVM method descriptor, and its
**PARAMETER portion** is compared against the call site's own `target.descriptor`
([D00](D00-fact-schema.md) §5); `javap -s` prints it.

*The whole string was compared until F2 §4.1.* JLS 8.4.2 identifies a method by its name
and parameter types — the return type is in the descriptor and is not part of the
signature — so comparing it tied every row to a library version by accident: a library
that changes a return type changes nothing in its callers' source and the descriptor
entirely, and every Spring Kafka 2.x producer derived nothing against rows declaring the
3.x `CompletableFuture`. **What this means for an author:** a row whose declared RETURN
type is wrong now still matches, so it is no longer a silent-failure shape; a row whose
declared PARAMETERS are wrong still is, and that is what the paragraph below is about.

It is validated at load to open with `(` and to contain `)`, because a descriptor no call
can equal fails INVISIBLY.

**Declaring one on any row CLAIMS that (name, arity) for every row.** A call at a claimed
arity whose descriptor matches no row derives **nothing** — it does not fall through to a
descriptor-less sibling, because falling through is exactly the fabrication the key exists
to stop. So a catalog adding `descriptor` to one overload accepts an under-report on the
others until it declares them too, and that under-report belongs in `docs/COVERAGE.md`
(§8). Arities no row claims are unaffected: `spring-rabbit-template.yml` declares
descriptors at arities 2 and 3 and none at arity 1, whose `convertAndSend(Object)` has no
sibling to collide with.

**`channel_arg` is an alias of `url_arg` for protocols whose identity is a destination
rather than a URL** — a topic or queue name in place of a path. Declaring both `url_arg`
and `channel_arg` on one row is a `CatalogError`: the two name the same capture, and a row
naming it twice is a broken catalog, not two different pieces of evidence. The two are an
alias in the *grammar* only, never in how the capture is read: a `channel_arg` value is a
destination expression, recorded verbatim as `path` with `peer` always NULL, while
`url_arg` still splits an absolute URL into peer and path (CP-2). SQS's canonical
destination is a whole queue URL
(`https://sqs.us-east-1.amazonaws.com/123456789012/my-queue`), and splitting it would
record a destination nothing could send to plus a peer no messaging fact ever carried.

**`channel_via` reads a destination the consuming call's own argument position never names
directly** — `session.createProducer(session.createQueue("raw-audit"))`'s topic lives on
`createQueue`'s own argument, not `createProducer`'s. A row declaring it is `[{owner,
method, arg: int | "all_strings"}]`, each form tried in the order written until one's
`owner`+`method` reach the argument's own linked call site (the same value-id join
`call_wrappers` uses, §2h, generalised to any named method rather than only `<init>`); `arg`
an integer reads that one position off the linked call, verbatim, and `arg: "all_strings"`
reads every one of its string-kind positional arguments as its own resolved tuple — one row
per element, plus one trailing unresolved tuple if any element failed to resolve, never a
per-element guess. **The ladder tries the literal argument FIRST, `channel_via` only as a
fallback**: some APIs genuinely overload a destination-taking method with both a
literal-string form and a linked-instance form, so a `channel_via`-declared row still reads
the captured position directly before ever following the link, and only falls back once
that direct read is not a resolved string literal. `channel_via` without `channel_arg`/
`url_arg` on the same row is a `CatalogError`: it says *how* to read a position the row has
to name first. **`channel_via` together with `url_arg` is a `CatalogError` too** — it pairs
with `channel_arg`'s verbatim reader, since a linked call's own argument is read as a
destination (`peer` always NULL), and a row asking for CP-2's peer/path split as well would
have one destination read two incompatible ways depending on which rung of the ladder
answered. This same ladder — literal first, linked call as fallback — is what `fluent`
and `interface_implementation` (both below) read a `channel`/`channel_arg` position through
too.

**`mapping.duplicate: conflict` says the framework REFUSES two handlers on one address**
(F5 §6.1, W28), and its absence — which is every catalog but `spring-web` and `spring-mvc` —
says several handlers there is ordinary. `@KafkaListener` on a class with `@KafkaHandler` on
its methods dispatches by PAYLOAD TYPE, so a topic served by two methods is correct and
reporting it would be a rule mirrored onto a set it does not describe. Spring MVC is the
other case: `AbstractHandlerMethodMapping$MappingRegistry.validateMethodMapping` throws
`IllegalStateException` at startup, so the application does not run.

Two more keys ride with it, and both exist to keep the finding honest rather than to produce
one. **`discriminators` names the conditions `RequestMappingInfo.equals` compares that are
not already columns on the endpoint row** — `params` and `headers`. Class-level and
method-level values UNION, because `ParamsRequestCondition.combine` adds one expression set
to the other, so two methods inside one `@RequestMapping(params = "v=1")` class still
conflict with each other while neither conflicts with a method outside it. **`custom_condition`
names the framework's handler-mapping type**, whose subclasses may register a condition that
is code rather than an attribute: a module declaring one is left alone entirely, because a
conflict named against a service that starts perfectly well is a claim and a missing finding
is not (NFR-2).

**A row declaring neither `http_method` nor `method_arg` is verbless by declaration** — a
topic has no verb. The row derives `method` NULL without penalising `resolution`, exactly
as `method_arg`'s own unresolved case does; resolved verbless rows dedup on `(protocol,
direction, path)` rather than on a method-inclusive key, since there is no method to
distinguish them by.

**`direction` on a row overrides the catalog's declared direction** — Pub/Sub's
`subscribe` is inbound even inside an otherwise outbound file. On an inbound row, the
deriving method lands in `handler`, not `caller`: it is the consumer, not the caller.

**`record_arg` names an argument whose linked constructor carries both identity and
payload** — `send(ProducerRecord)`'s one argument names the record, not the topic or the
value directly. It resolves through the catalog-level block `record_wrappers: [{type,
channel_ctor_arg, payload_ctor_arg}]`, where `payload_ctor_arg` is an integer position or
the string `last`.

**`path_from_argument_type` names the operation off the PAYLOAD rather than the address**
(2I design §4). Some protocols address every operation at one URL and distinguish them by
what is sent: a SOAP call's identity is its payload's root element, stated on the payload
*type*, and the call site itself names no type at all — its argument is a bare `parameter`
([D00](D00-fact-schema.md) §5) and its target descriptor is the erased `Object` such APIs
declare. The rule is `{arg, annotation, name_from, qualifier_from?, format?}`: the argument
at `arg` must be a bare parameter reference, its declared type comes from the caller's own
signature (one hop, the join `parse_binding` already makes for the same argument kind), and
`annotation`'s attributes on that type give the name and, where declared, the scope it sits
in. `qualifier_from` and `format` are declared together or not at all — a scope with no
stated composition is half a rule — and `format`'s one word today is `qname`, the same
`{scope}name` bracketing `annotation_driven`'s own `qualifier_format` composes.

Three consequences follow, and each is a refusal rather than a convenience. **The address
stops being the identity**: a row declaring this reads its url argument for `peer` only,
WHOLE and unsplit (an address fed from configuration is a `${...}` expression with no
authority half to take, and two deployments on one host are two peers), leaving `path` to
the operation. **An absent attribute derives no operation** — a framework's own default
for one is never written into the class file, and a scope defaulted from a schema is not in
the class file at all, so the row is `unresolved` rather than carrying a plausible-looking
address. **The resolved type is the payload**, so the row describes its request without a
`body_arg` that would have failed on a bare parameter — but only once `annotation` has been
found on it: a type carrying none is not evidence of a payload, whatever sits at that
position. `path_from_argument_type` beside `record_arg` is a `CatalogError` (the record IS
the payload source), as is any malformed or unrecognised rule.

**`default_address: {method, arg}` is the address a client was CONFIGURED with**, for the
overloads that carry none — a `WebServiceTemplate` whose `setDefaultUri` was called in its
holder's constructor. Catalog-level, because it describes the `owner` rather than one of
its methods, and applied only to rows naming no `url_arg`/`channel_arg`/`record_arg` of
their own: a declared position is the call's own answer and always wins. The lookup is
CONFINED TO THE TYPE THAT MAKES THE CALL, and that boundary is the soundness argument —
nothing links a call's receiver back to the field holding it (a receiver is a value id,
meaningless outside its own method), so what can honestly be said is that the type making
the call also configures the client in its own body. A client configured in another class
resolves to nothing; so does a type whose setup calls hand over two different addresses,
because two candidates are not an address. The argument found is read through the field
ladder (§2j) exactly as an address written at a call site is.

Per matching call site: `path` is the url argument's string literal — the template
verbatim, placeholders and all, because the template is the wire identity — and
**`resolution` is `resolved` when it did and `unresolved` when it did not; the row still
derives either way**, because "this method calls something over HTTP" is true and useful
on its own. `direction` is `outbound` by default, or the row's own `direction` where
declared; an outbound row's deriving method lands in `caller`, an inbound row's in
`handler`, per the rule above. `peer` is NULL (§2d); `evidence` is `compiler`. Rows enter
the same `endpoints` table as every other style, merging and counting the same way.

### `fluent`

The request is assembled across several calls, so one value must be followed through a
method body — a join in the derivation over each `result → receiver` link a `call_site`
fact carries ([D00](D00-fact-schema.md) §5), read within one method.

```yaml
style: fluent
matches:
  roots:
    - { owner: org.springframework.web.reactive.function.client.WebClient, method: get,  captures: { http_method: GET } }
    - { owner: org.springframework.web.reactive.function.client.WebClient, method: post, captures: { http_method: POST } }
  steps:
    - { method: uri,        captures: { url: arg0 } }
    - { method: bodyValue,  captures: { body: arg0 } }
    - { method: body,       captures: { body: arg0 } }
    - { method: bodyToMono, captures: { response: arg0 } }
    - { method: bodyToFlux, captures: { response: arg0, response_is: array } }
    - { method: header,     collects: { kind: header, name: arg0, value: arg1 } }
  terminal: [retrieve, exchange]
```

**`collects` accumulates where `captures` overwrites** (F5 §6.2, W29), and the difference
is the whole reason it is a second key rather than a spelling of the first. A capture is
LAST-WINS — a repeated step overwrites its own earlier value — which is right for a url and
wrong for a header: a chain calling `.header(...)` three times would keep the third and say
nothing about the other two, and that is not a smaller answer but a false one. A collecting
step contributes one `endpoint_metadata` entry per visit instead.

Its `kind` is the catalog's own word for what the entry IS — `header`, `query`, `key` — so a
reader is never left inferring it from the name; `name` is optional, because a partition key
and a routing key have a value and no name at all, and writing one in would invent a label
the wire does not carry. **A varargs position contributes one entry per value**:
`header(String name, String... values)` is what the API declares, the scanner models the
call's second argument as an array, and `header("Accept", "a", "b")` sends two values under
one name. Reading the array itself resolves to no literal — which is what a first
implementation did, recording every header as `unresolved` including the ones written as
literals in plain sight.

The value is **redacted where it is read**, not at export ([D01](D01-graph-schema.md) §3),
and an entry whose value is not a literal is recorded present-and-`unresolved` rather than
dropped.

**`roots` replaces the single `root`** — a builder library commonly has several
verb-carrying entry points, each seeding its own `captures`, so this is a list rather than
one fixed starting point. **`steps` are owner-free by default**: a step matches by method
name alone, because the same builder-shaped call sequence appears on more than one concrete
type across a library's surface and an owner gate would just make the catalog repeat itself.
A step may still declare an `owner` where the library itself reuses one method name for two
different roles on two different types — RestClient's `body(Object)` (a request-setter on
its `RequestBodySpec`) and `body(Class)` (a response-extractor on its `ResponseSpec`) are
otherwise indistinguishable by name alone. Two step entries sharing a method name with no
`owner` telling them apart — or the same `owner` — is a broken catalog, refused by name at
load: silent last-wins would hide exactly that bug. **`terminal` is a list**, for the same
reason `roots` is — WebClient reaches its response two ways (`retrieve` and `exchange`), and
both end the chain.

Per chain reaching a terminal: fold captures in order, last wins, and derive one endpoint —
verb from the root, path from the url capture (or `unresolved`, exactly as `single_call`'s
rule above), response from a class literal, a `type_carrier` instance, or `response_is:
array` (§2h), request via §2h's rooting. Unmatched steps pass through uncaptured, and
**a builder that never reaches a terminal derives nothing** — the true answer, not a gap:
a `Request.Builder` built and thrown away made no call. Two chains sharing a prefix each
derive on their own; value ids ([D00](D00-fact-schema.md) §5) keep interleaved builders
apart where adjacency heuristics would fabricate a link between two unrelated calls that
happen to run close together.

**This style requires `chain_reconstruction`** and therefore gates every builder-based
client library. It is the reason that capability matters. Catalogs on this engine:
`spring-webclient.yml`, `spring-restclient.yml` (the synchronous twin), `okhttp.yml`
(`Request$Builder` root, `url`/`post` steps, a `build` terminal joined to `newCall` through
the argument `source` id — [D00](D00-fact-schema.md) §5's `arguments[].source`). A terminal
entry's `terminal_via_argument` is ordinarily the bare flag `true`: any row carrying that
argument link completes the chain. Where a builder's own value could reach more than one
consumer — `Request r = builder.build(); log.debug("…", r);` alongside the real
`client.newCall(r)` — a catalog instead writes `terminal_via_argument: {owner, method}`, and
the join narrows to that one declared call; every other consumer of the same value no longer
counts.

**A step's own `captures` may also name `base`** — the other half of ONE address, not a
second address (2F). A builder states its base address once
(`WebClient.builder().baseUrl(…).build().get().uri("/invoices")`) and every request off
that builder appends its own path, so `base` and `url` compose at derive time: base plus
path where a chain captures both, the base alone where it captures no `url`, and the
composed string then read exactly as a written url is — CP-2 splits an absolute literal
into peer and path. **A composed address carrying a placeholder ANYWHERE keeps the whole
expression as `path` with `peer` NULL**, checked before that split rather than after:
`https://${billing.host}/orders` matches CP-2's absolute shape perfectly, and splitting it
would write `${billing.host}` into `peer` as though it were an authority — a peer no
environment ever named. It stays whole until the per-environment peer join resolves it.
**A `base` that was captured and could not be read makes the row unresolved with `path`
NULL**, never the path alone — and a `url` capture that was REACHED and could not be read
does the same, for the same reason: half an address presented as the whole one names a URL
the module never calls. A `url` capture never reached at all is no claim, and the base then
stands alone as the address.

`baseUrl` sits BEFORE the row that roots the chain, so a chain's captures are folded from
its PRE-ROOT prefix too — the same `result → receiver` link followed backward from the
root, outermost producer first, so last-wins reads the same in both directions. A row's
`receiver` is one value id and the row that produced it is the one whose own chain key IS
that id; nothing here is a search by proximity.

**Backward folding consults steps that declare an `owner`, and only those** — the same
gate `combinator` puts on rooting an owner-free continuation, for the same reason. Forward
of a root, an owner-free step is already bounded: the walk is chain-rooted, so the step can
only fold into a chain this catalog matched. The pre-root prefix is precisely the part of a
chain no root has vouched for, and an owner-free step reached there would fold ANY
same-named call the value happens to come from — an unrelated registry's own
`uri("registry-key")` read as this row's address, or one chain's capture leaking into
another's row through a shared prefix. So a `base`-shaped step declares its builder type,
and a catalog whose step is owner-free is forward-only, exactly as before.

**A root's or a step's own `captures` may also name `channel`** — `url`'s
destination-shaped counterpart, exactly the distinction `single_call`'s own `url_arg`/
`channel_arg` pair keeps (§2, above): a `url` capture is an address CP-2 may split into
peer and path, a `channel` capture is a destination expression recorded verbatim as `path`
with `peer` always NULL. `google-pubsub-publisher.yml`'s root captures
`Publisher.newBuilder`'s own `channel: arg0`. **A chain's `roots` and `steps`, TAKEN TOGETHER, may
declare `url` or `channel`, never both** — checked over every entry's own captures at once,
not one entry at a time: a chain folds every step's captures into one running set as it
walks (above), so `channel` declared on one step and `url` declared on a *different* step
in the same catalog collide in that one running set exactly as one entry naming both would,
and a per-entry-only check would let the collision load silently.

**A `channel`-declaring entry may also declare `channel_via`**, read through the SAME
literal-first, linked-call-fallback ladder `single_call`'s own `channel_arg`/`channel_via`
pair defines (§2, above) — a `[{owner, method, arg}]` list, tried in order, followed only
once the captured position itself is not a resolved string literal. `channel_via` is
declared alongside `captures` on the SAME root or step entry that captures `channel`, and —
since a root's own captures already fold forward through every later step it reaches — a
root's own `channel_via` ladder rides forward the same way, available to resolve the
chain's `channel` wherever the walk finally derives, with no need to repeat it on a later
step.

**A step may declare `when`** — `{arg: int, equals: str}`, exactly those two keys — a value
guard on one of the *matched call's own* arguments, for the builder shape where the
capturing method is generic and only the argument says what it set:
`MessageBuilder.setHeader(KafkaHeaders.TOPIC, "raw-messages")` sets a topic, while
`setHeader(anythingElse, …)` on the same chain does not. **`when` guards steps only.** A
root starts the chain, with no prior capture a guard could ever condition, so a `when` on a
root is a broken catalog, refused by name at load rather than silently stripped.

The guard has **three** answers, not two, because "the guard did not hold" and "the guard
could not be read" are different facts:

- the guard argument is a string literal **equal to** `equals` — the step's own captures
  apply, exactly as an unguarded step's would;
- the guard argument is a string literal, but a **different** one — the step still *matched*
  the chain, only its captures do not apply, so nothing it declares overwrites whatever an
  earlier step already folded in (pass-through);
- **anything else** — no argument at that position, the wrong kind, or the compiler's own
  `unresolved` — poisons every *argument* capture (`url`/`body`/`response`/`channel`) the
  step declares to `unresolved`. It might have been the guarded key, and an unreadable key
  must never let a chain keep an earlier confident answer. A later step that writes the same
  key unambiguously supersedes the poison: "can't tell" is an answer this pass records, not
  a state it locks. The step's *literal* declarations (`http_method`, `response_is`, a
  `channel_via` ladder) are not argument reads and carry no `unresolved` form at all, so
  they are left out of the fold rather than poisoned into a value their readers cannot
  interpret.

### `combinator`

Neither one call (`single_call`) nor one chain (`fluent`) carries the declaration here:
the router is a **tree**, assembled by handing predicate objects, subtrees and whole
routers to further calls as arguments, rather than fluently through one receiver.
Spring WebFlux's functional routing is the fixture case — `RouterFunctions.route(...)`/
`.nest(...)` in Java, `coRouter { }` in Kotlin — but nothing below names either language:
every edge the walk follows is already in the facts
([D00](D00-fact-schema.md) §5) — a predicate argument links to its producing call
through `source`, a chain link through `result` → `receiver`, and a subtree or a nested
body arrives as one more linked argument, `lambda`-kind where the compiler moved the
block into a method of its own.

```yaml
style: combinator
requires: [call_site, string_constants, chain_reconstruction]
matches:
  entries:
    - { owner: org.springframework.web.reactive.function.server.RouterFunctions,
        methods: [route, nest], handler_arg: 1 }
    - { owner: org.springframework.web.reactive.function.server.CoRouterFunctionDslKt,
        method: coRouter, body_arg: 0 }
  vocabulary:
    verbs:
      - { owner: "…RequestPredicates", method: GET, verb: GET, path_arg: 0 }
      - { owner: "…CoRouterFunctionDsl", method: GET, verb: GET, path_arg: 0, handler_arg: 1 }
    prefixes:
      - { owner: "…RequestPredicates", method: path, path_arg: 0 }
      - { owner: "…RouterFunctions", method: nest, path_arg: 0, subtree_arg: 1 }
      - { owner: "…CoRouterFunctionDsl", method: nest, path_arg: 0, body_arg: 1 }
    media:
      - { owner: "…RequestPredicates", method: accept, fills: produces }
    media_values:
      owner: org.springframework.http.MediaType
      values: { APPLICATION_JSON: application/json }
    composers:
      and: [{ owner: "…RequestPredicate", method: and }]
      or:  [{ owner: "…RequestPredicate", method: or }]
  continuations:
    - { name: andRoute, owner: "…RouterFunction" }
    - { name: andNest,  owner: "…RouterFunction", path_arg: 0, subtree_arg: 1 }
    - { name: and,      owner: "…RouterFunction" }
```

**Three grammar blocks, and each is catalog data alone — nothing below names a
framework:**

- **`entries`** declares where trees start, in two shapes. An **argument-rooted**
  entry (`{owner, methods, handler_arg}`) is a call that takes a predicate and a
  handler as its own arguments — Java's static `route`/`nest`. A **body-linked**
  entry (`{owner, method, body_arg}`) is a call whose `body_arg` names, as a
  `lambda`-kind argument, the method holding the routes — Kotlin's `coRouter`, whose
  builder body the compiler puts in a synthetic method of its own. The walk roots
  ONLY at the entry call and jumps to the named method; a prefix rule's own
  `body_arg` (below) makes the same jump one level deeper. Body methods are never
  rooted on their own — a method that merely *contains* a vocabulary call is not a
  root, because rooting it too would double-derive every nested route, once
  prefixed and once bare (2E checkpoint F4, the frozen defect this rule exists to
  close). The entry owner and the vocabulary owner are routinely two different
  types — `CoRouterFunctionDslKt` (the file facade with the static entry point) is
  not `CoRouterFunctionDsl` (the DSL type every builder call carries) — so a
  catalog declares both.
- **`vocabulary`** maps owner+method to a role: `verbs` (a verb plus the argument
  its path sits at, and — the two-argument form — its handler position, ONE
  vocabulary read at two arities: a one-argument predicate becomes a route only
  once some entry attaches a handler to it, a two-argument call declares the whole
  route itself), `prefixes` (a path contribution, plus optionally the
  `subtree_arg`/`body_arg` holding the routes it prefixes — declaring both on one
  row is nonsensical and never arises, since a subtree is a same-method expression
  and a body is a compiler-moved one), `media` (which of `consumes`/`produces` a
  predicate fills — `accept` is request-matching semantics: a route guarded by
  `accept(JSON)` *serves* clients that accept JSON, not the reverse), `media_values`
  (an enum type's member names to their declared wire values), and `composers`
  (`and` merges constraint sets into one; `or` duplicates the route per branch, over
  ANY predicate kind — verbs, paths, media alike — the `all_methods` precedent
  generalised).
- **`continuations`** are the calls that merge route SETS along `result` →
  `receiver`, `fluent`'s own steps discipline extended: a plain name matches any
  owner, useful for reaching a step inside a chain already known to be this
  catalog's; a mapping narrows the same name to one `owner`, and — for the
  nest-shaped form — adds `path_arg`/`subtree_arg`, which fold the *whole router* at
  that argument under this call's own prefix rather than reading a handler it does
  not have. **Every continuation that can END a chain needs an `owner`.** A bare
  `and` matches a method name half the libraries on a classpath declare; rooting at
  every one of them would invent a router out of any two-argument call that happens
  to share the name. The cost is stated rather than hidden: an owner-free
  continuation extends a walk some real root already reaches, but never roots one
  by itself.

**The walk, one core for both shapes.** From an argument-rooted entry, or from a
body-linked entry's own named method, every argument is resolved through its
`source` link recursively: predicate subtrees fold into (verb, path, consumes,
produces); a prefix pushes its own contribution onto every route its subtree or
body yields; a continuation merges the route sets on either side of it. Each leaf
route derives one row: the catalog's declared `protocol`/`direction`, the verb, the
concatenated prefix+path, the handler symbol (a bound method reference resolves to
the real target, an inline block to its synthetic body — both joined against the
scanned symbol facts and written module-prefixed, never fabricated; an adapted
function object read as an `instance` of a generated class is not a method symbol
at all, and reads NULL rather than being invented), `evidence: compiler`. Rows
enter the same `endpoints` table as every other style, dedup and merge unchanged.

**Honesty rules, verbatim from the design spec.** An unreadable part poisons
EXACTLY its own column: a variable path leaves `path` NULL and the row
`unresolved`; an unreadable media constant leaves only that media column NULL,
since the verb and path — the wire identity — are intact and the row stays
`resolved` (2E checkpoint F1's ruling: Spring's own vararg `accept(MediaType...)`
constants are, in real bytecode, exactly this case — the `ANEWARRAY` producing the
array has no case in the extractor's argument reader, so the argument is a bare
`{"kind":"unresolved"}` with no `source` and no `symbol`, and the media vocabulary
above is declared *specified-but-unread* against that fixture, proven by a
synthetic-facts unit test rather than the live scan, for the day the extractor
grows the missing case). A router composed from another method's own return value
— the walk is per-method BY DESIGN — derives ONE unresolved row for the reference
rather than a silent absence: the facts would support following it, and spec §1c's
boundary is a stated one, not a gap the evidence left open. `request_shape`/
`response_shape` stay honestly NULL always: a functional handler's signature is
`Request → Response`, and its payload contracts live inside its body — `bodyToMono`
calls and their like — which is call-evidence work for a later phase, not a
signature this style can read.

**Two PATH predicates inside one `and`-chain CONCATENATE rather than poison, and
the resulting row still emits `resolved`** — the identical fold that composes a
`nest` prefix onto whatever its subtree contributes, run twice in the same chain.
This is a deliberate asymmetry from the doubled-verb case above, and it is stated
openly rather than smoothed over: `and`ing two full path patterns together
(`path("/a").and(path("/b"))`) is a degenerate input to begin with — no real
request path satisfies both at once — and the fold has no way to tell a `nest`
prefix apart from a full path predicate at this point in the merge, so it
concatenates the one the same way it concatenates the other. Concatenation is the
2E behavior; poisoning the path here, the way a doubled verb already is, is the
stated future fix, not the current one.

**Media unions within one batch, exactly `fluent`'s own rule reapplied**: two `or`
branches differing ONLY in the media they declare are one endpoint, not two, folded
before the insert ever sees them (spec §4). **A row whose path could not be read
takes part in NEITHER the union nor the dedup key that follows it** — two such rows
compare equal on every identity column and would collapse into one under a naive
key, but each is its own distinct "this method declares something unreadable" fact,
so each stays its own row (`derive_call_endpoints.sql`'s own contract: SQL's
`NULL = NULL` is unknown, not true, and two unresolved rows are two facts about two
call sites, never one).

**This style is deliberately language-agnostic, and the engine enforces it: no JVM
grammar, no framework name, no Kotlin-specific branch anywhere in its code** — the
two entry shapes above are catalog declarations interpreted by one core. The ENGINE
stays unchanged; the catalog VOCABULARY it reads is additively extensible, not
frozen at these two shapes. That said, some shapes are known to need vocabulary
additions before their catalogs can be written: a verb row with no path argument
(axum's `get(handler)`, the path supplied by whatever `.route("/x", get(handler))`
it is nested under), a literal route path carried at the entry call rather than
folded through a chain, and a receiver-accumulated router topology (gin's `Group`,
which mutates a receiver across calls rather than composing a return value). Simple
per-call registrations — gin's `r.GET("/x", h)`, Express's `app.get(...)` — need none
of that: they already fit the existing `single_call` style once their languages'
extractors emit the same fact grammar (D00 §5's `source`/`result`/`receiver` links).

### `interface_implementation`

The boundary is declared by implementing a framework interface — Pub/Sub's
`MessageReceiver`, JMS's `MessageListener`. Unlike every style above, one call's own
declaration is not the evidence: two facts are joined instead, a *registration* call
site and, where its receiver is a named instance rather than a lambda, that instance's
own declared `interfaces` ([D00](D00-fact-schema.md) §5a's `implemented_interfaces`
capability).

```yaml
style: interface_implementation
protocol: pubsub
direction: inbound
requires: [call_site, string_constants, implemented_interfaces]
matches:
  interface: com.google.cloud.pubsub.v1.MessageReceiver
  handler_method: receiveMessage
  registration:
    owner: com.google.cloud.pubsub.v1.Subscriber
    method: newBuilder
    channel_arg: 0
    receiver_arg: 1
    channel_via:
      - { owner: com.google.pubsub.v1.ProjectSubscriptionName, method: of, arg: 1 }
```

`registration` is `{owner, method, channel_arg, receiver_arg, channel_via?}` — the one
call site that binds a receiver to a channel. **`channel_arg` reads through the same
capture ladder `single_call`'s own `channel_via` already defines (§2, above), tried in
that order**: a string literal at that position resolves directly first — `Subscriber.newBuilder(String,
MessageReceiver)` is a real overload alongside the `ProjectSubscriptionName` one, and a
`channel_via`-declared row must still catch it — and only when the argument is not a
resolved string literal does a declared `channel_via` form follow the linked call's own
argument instead (`ProjectSubscriptionName.of`'s own `name` argument, not `newBuilder`'s);
anything else is `path` NULL, `unresolved` — the registration was made, only its channel
is unread.

**`receiver_arg` is the argument that names the handler**, read one of two ways depending
on what the compiler resolved it to: a `lambda`-kind argument names its own synthetic body
method ([D00](D00-fact-schema.md) §5a) — the lambda IS the handler, whatever the declared
interface's method is named. An `instance`-kind argument (a `NEW`-produced named class)
names `<type>#<handler_method>` only when that type's own declared `interfaces` include the
declared `interface` — **direct implementers only**: the fact carries a class's own
interface table, never a superclass's, so a subclass of an implementing class is a stated
one-hop limitation, not a gap to close later.

**Either way the receiver only names the method; the `handler` written is the method
*symbol*, joined out of the scanned symbol facts and copied verbatim.** A call argument's
own `symbol` is always the *bare* descriptor — no module coordinates, and for an `instance`
receiver no signature either ([D00](D00-fact-schema.md) §5a) — so a `handler` assembled by
gluing that descriptor to the catalog's `handler_method` would name nothing any fact ever
emitted, and would join to no `symbols` row: a decorative string in a column the graph is
supposed to be able to follow. The engine matches the bare form against the declared method
symbols instead, and writes the one it found.

Anything else — the receiver uncaptured, an `unresolved` kind, a registered instance whose
type does not implement the declared interface, or a receiver whose handler method no
scanned document declares (the implementer lives outside this module) — resolves `handler`
to NULL: the subscription is still consumed, only who handles it is unread, never
fabricated.

**The registration is the evidence.** A class implementing the declared interface but
never handed to a matching registration call site derives nothing at all — implementing an
interface is not, on its own, an endpoint. This is the failure mode this style exists to
prevent: a phantom endpoint conjured from a class's shape alone, with no call anywhere in
the scanned code that ever wires it to a channel.

**This style needed no execute-terminal — and that was wrong; see §1b-i.**
A registration whose framework requires a later ACTIVATION call is not a boundary
until that call is reached, which `registration.started_by` now declares (`OI-64`).
What follows is why the ARGUMENT-passing shape still needs no terminal of its own.
`fluent`'s `terminal`/`terminal_via_argument`
(§2, above) exists because a *built* HTTP request is not yet a *sent* one — a
`Request.Builder` built and logged, never executed, made no call. Binding a receiver to a
subscription has no such gap: the registration call itself IS the intent, in a way a built
request is not, so `interface_implementation` derives directly off the registration site
with no further join to prove the subscription actually ran.

Per registration call site: one row per resolved channel tuple, `direction`/`protocol` the
catalog's own declared fields, `method` always NULL (the style is verbless — a subscription
has no verb), `caller`/`peer` always NULL (the deriving method is a `handler`, never a
`caller`, and a channel is never split into a peer, §2d). **A resolved row's wire identity
includes `handler`**: two registrations of the *same* channel by the *same* handler
collapse to one row (the usual duplicate-registration merge every style keeps), but two
*different* handlers registered on the same channel — two `@KafkaHandler`-shaped consumers
sharing one subscription, say — each keep their own row; dropping `handler` from the key
would silently discard the second registration's own evidence. **`request_shape`/`response_shape`
are always NULL** — `PubsubMessage` is a declared no-shape envelope: the registration names
an identity and, where readable, a handler, never a payload. This is the same
honest-absence precedent a future messaging catalog whose payload is likewise opaque
(`jakarta.jms.Message`) is expected to keep: NULL means "no shape to root", not "unread".
`evidence` is `compiler`; rows enter the same `endpoints` table as every other style,
merging and counting the same way.

### `config_join`

The declaration is not in the code at all. **The code carries a name — a bean's own
method name — and configuration says what the name means** (§2d). A `config_join`
catalog reads exactly one input, the `resolved_config` table [M04](M04-resolver.md)'s
pass 2 produced, and does two jobs with it: `address_from_config` DERIVES endpoint rows
from a key template, and `media_from_config` STAMPS declared media onto rows other
engines already minted. Both blocks are optional and independent; a `config_join`
catalog declaring neither is a broken file.

```yaml
style: config_join
protocol: kafka           # the default; a resolved binder may say otherwise (§2c)
direction: inbound        # the default; each suffix rule carries its own
requires: [resolved_config, typed_signatures, implemented_interfaces]
matches:
  address_from_config:
    key: "spring.cloud.stream.bindings.{binding}.destination"
    binding:
      from: bean_name
      unselected_binds: sole      # or `all`; `all` is the default
      selected_by: spring.cloud.function.definition
      selection_separator: ";"
      composition_separator: "|"
      suffix:
        - { when: { implements: java.util.function.Consumer }, then: "-in-0",
            direction: inbound, payload_arg: 0 }
        - { when: { implements: java.util.function.Supplier }, then: "-out-0",
            direction: outbound, payload_arg: 0 }
        - { when: { implements: java.util.function.Function }, then: ["-in-0", "-out-0"],
            direction: [inbound, outbound], payload_arg: [0, 1] }
    binder_key: "spring.cloud.stream.bindings.{binding}.binder"
    default_binder_key: spring.cloud.stream.default-binder
    binder_protocols: { kafka: kafka, rabbit: amqp }
```

**`key` is a template carrying exactly one placeholder, `{binding}`**, and a key naming
no binding is refused: it would resolve the same address for every bean. `binder_key`
takes the same check, being as per-binding as `key` is; `default_binder_key` does not,
since naming no binding is exactly what makes it the module-wide fallback.

**`binding.from` is `bean_name` or `annotation_value`** — the two sources implemented, and
anything else is refused rather than read as one of them. The DESTINATION half is identical
for both and is `resolved_config` alone; what differs is where the name being asked about
comes from, and what happens to a name configuration never answers.

#### `binding.from: annotation_value`

The name is the value of a named ARGUMENT on a named annotation — a channel name written on
the method the framework wires to that channel — rather than a declared method's own name.

```yaml
matches:
  address_from_config:
    binding:
      from: annotation_value
      channels:
        - { annotation: org.springframework.integration.annotation.ServiceActivator,
            arg: inputChannel, direction: inbound }
        - { annotation: org.springframework.integration.annotation.ServiceActivator,
            arg: outputChannel, direction: outbound }
```

**`channels` is a non-empty list of `{annotation, arg, direction}`**, one entry per
`(annotation, attribute)` pair the framework spells a name with; `direction` defaults to the
catalog's own and is checked against [D00](D00-fact-schema.md)'s closed set. It is an
attribute SET and not an annotation's attribute list — most attributes of a channel-bearing
annotation are not channels, and one of them is usually a plain `String` too, so reading
whatever is written files a question about a name nobody wrote.

Three rules this source has and `bean_name` does not, each because a channel name is not a
bean:

- **The annotation's target must be a METHOD.** The same annotation is `@Target`-legal on an
  ANNOTATION TYPE, which is how a module composes its own stereotype; nothing subscribes
  there. (`scheduled_work`'s own conjunct, and `derive_endpoints.sql`'s
  `handler-is-a-method` join on the wire side.)
- **The value must be a non-empty STRING**, taken verbatim. An array, a nested annotation or
  a number is not a channel name; an expression still carrying a `${…}` placeholder is asked
  about exactly as written, resolved by nothing on the way in.
- **A name whose destination configuration never answered derives NOTHING** — no row, and no
  ghost row. A bean is a declaration whose address is merely unread; a channel names an
  in-process pipe, and whether it reaches a broker at all is the thing nobody answered, so a
  `path` NULL row would assert a boundary no declaration in the module makes. It is not
  silence either: `gaps` files it (below).

**`key` is therefore OPTIONAL for this source and required for the other.** A framework whose
channels have no standard configuration key declares none: the catalog then asks
configuration nothing, derives nothing, and files every channel it finds as a question.
Requiring a key there would force a template to be invented, which is a convention no
framework states — and D02 places a project's own convention in that repository's catalog,
never in a built-in.

**`gaps`: the `channel_destination` hand-off.** One question per `(channel, handler)` whose
destination configuration did not give, carrying `candidates: [{channel, handler}]` and a
trail naming the reason — no key template was declared, or a key was built and
`resolved_config` holds no value every environment agrees on. It is a `gaps` function rather
than a write inside `run` because the ledger is emptied once per resolve, from the pipeline,
AFTER the engine loop ([M04](M04-resolver.md)); it rides the same seam
`supertype_derived`/`injected_client`/`annotation_driven` use. Inert for a `bean_name`
catalog — whose unresolved bindings already answer for themselves with a row — and for a
`media_from_config`-only one.

#### `binding.from: bean_name`

**A candidate is a declared method whose RETURN type matches a suffix rule**, tried two
ways in that order: equality against the declared interface's own descriptor, then the
`implemented_interfaces` join for a scanned type that declares it. The equality half is
what a library's functional interface reaches — an interface the module does not itself
compile has no symbol fact and can never appear in any class's interface table — and the
join half is for a module's own named implementation. Suffix rules are tried in declared
order; two methods sharing a bean name keep the first in symbol order (NFR-1).

**`then`, `direction` and `payload_arg` are read in parallel.** A scalar `then` is one
row; a LIST is the both-halves-at-once case (§2d), where one bean derives two rows
through the same key template. `direction` and `payload_arg` may each be a scalar
(applying to every suffix) or a list of the same length (one per suffix) — which is what
makes that case expressible as data, since each half of a two-argument functional type
carries a different payload position and a different direction, and neither is derivable
from the suffix string without the engine learning a framework's naming convention. A
rule stating no `direction` takes the catalog's own; `payload_arg` defaults to 0.

**Row shape.** Verbless (`method` always NULL), `evidence: compiler`, `peer` always NULL
(a destination is never split into a peer, §2d). **`handler` versus `caller` follows
[D01](D01-graph-schema.md) §3's direction rule, not the style**: an inbound binding's
bean method is the row's `handler`; an outbound one's is its `caller`, `handler` NULL.
`request_shape` roots from the functional type's own type ARGUMENT at the declared
position — the interface itself is machinery and never reaches a shape column — and is
`request_shape` on both directions, the reply-row precedent ([D01](D01-graph-schema.md)
§3): an outbound row's payload is what it sends, and `response_shape` is reserved for a
response the row actually receives, which a binding has none of.
**`handler_signature` is always NULL**, exactly as it is on every other pass-computed
row (`single_call`, `fluent`, a `reply` row): the payload is decided here, and the
owner-keyed contract update is guarded on that column precisely so a row that answered
for itself is not answered again from a signature whose return type is the functional
interface.

**Protocol is resolved per match (§2c)**, most specific first: the binding's own
`binder_key`, then `default_binder_key`, each looked up in `binder_protocols`. A
configured name absent from that map leaves the row on the catalog's own declared
protocol — an unmapped name is a gap to grow the catalog from, never a guessed protocol.
`binder_protocols`' values are checked against [D00](D00-fact-schema.md)'s closed set,
like every other protocol a catalog writes.

**Six honesty rules, none of them silence:**

- **A missing key still derives a row.** The bean exists and the binding was declared;
  only the address is unread. `path` NULL, `resolution: unresolved`, handler named
  (§2d: "an unresolved address is not an absent endpoint").
- **An entry naming no single readable bean derives ONE row naming nobody.** `path`
  NULL, `handler` AND `caller` NULL, the catalog's own declared direction — no functional
  shape was read to say otherwise. Two entries land here: a **composed** one, which is not
  decomposed because picking one of the halves would be an invention, and a **ghost** one,
  a name the selection states that no candidate answers to (a bean renamed, deleted, or of
  a shape this catalog's interfaces do not describe). The ghost case must derive a row and
  not silence: its most common real cause is configuration still selecting a bean the code
  has since renamed, and silence makes that indistinguishable from a module that never
  selected it. These are the only endpoint rows in the schema that name no symbol at all.
  They share `(protocol, direction, NULL, NULL)` with each other and with a missing-key
  row, and each stays its own row: a NULL path never dedups, in the pass or in SQL.
- **A destination is written verbatim.** This engine never interprets what it reads: a
  resolved value still carrying a placeholder expression keeps that expression as its
  `path`, and the row still resolves, because the address WAS found. Rows keep
  expressions; `resolved_config` keeps values; the per-environment answer is the
  `resolved_peers` join's (§2d, job 3), never a rewritten row.
- **Agreement across environments is required for every single-valued answer — an
  ADDRESS as much as a stamp.** A destination key resolving to two different values in two
  environments derives the row with `path` NULL and `resolution: unresolved`, exactly as a
  missing key does: `path` is one column, an endpoint row is environment-neutral by design,
  and folding two real answers into one would invent a third that neither environment gave.
  Both values stay in `resolved_config`, which is where a per-environment question is
  answered.
- **A stamp lands only on agreement.** Every environment must resolve the same class, and
  the class must be in `values`; an environment that resolves a different one, one that
  never resolved the key, and a class the catalog does not know all stamp nothing. A stamp
  never overwrites a non-NULL column. The unstamped column is not a claim that nothing was
  declared — the class name is in `resolved_config` either way.
- **An explicitly EMPTY selection selects nothing.** "Nobody said anything" and "somebody
  said: nothing" are opposite statements. A `selected_by` key absent from configuration —
  or declared but resolvable in no environment — falls to `unselected_binds` below; a key
  that RESOLVED, to an empty value or to separators alone, is a select-nothing statement
  and derives no row. Collapsing the two would bind every bean in the module against a
  configuration that said the opposite: the one place this style could fabricate a
  boundary rather than degrade.
- **`unselected_binds` says what binds when the selection key names nobody**, and it is a
  CARDINALITY rule (F2 §3.4). Two values: `all` (the default — every candidate binds) and
  `sole` (one candidate binds where there is exactly one; two or more bind **nothing**).

  This exists because a framework may refuse to choose. Measured
  (`scripts/probes/w13_stream_binding.md`): Spring Cloud Function's
  `normalizeFunctionDefinition` opens its guard with `eligibleFunction.size() == 1`, so
  with two eligible functions and no definition configured the definition stays empty and
  nothing binds. `spring-cloud-stream.yml` said the opposite in prose — "absent, every
  candidate binds, **the framework's own default**" — and derived one endpoint per bean
  for an application that serves neither. A sentence naming the framework as its
  authority, saying what the framework does not do; nothing had compared it to the code.

  **Two or more under `sole` files one `unselected_binding` question per candidate.** It
  filed none at first, on the reasoning that the framework binds nothing so "no row" is
  the complete answer — which needed the count taken by the engine to EQUAL the count the
  framework takes. It does not: the framework counts registered BEANS, and
  `config_join._candidates` counts every declared method returning one of the declared
  interfaces, with no `@Bean` conjunct. A suppression here is therefore not evidence that
  the framework suppressed, and suppressing silently lost a real single-bean binding
  (OI-60).
- **A configured binder name absent from `binder_protocols` derives NO ROW and files a
  `binder_protocol` question** (F2 §3.4). It used to take the catalog's own declared
  `protocol:`, described in place as "a gap to grow this map from, never a guessed
  protocol" — the parenthetical was false, and a test pinned the fallback under a name
  that stated it (`..._falls_back_to_its_protocol`).

  **This is the one defect in the analysis that leaves the bundle.** `protocol` is
  identity and DR-5 gates linking on protocol equality, so a row published on a protocol
  nobody read links into another consumer's graph against endpoints this module never
  speaks to, and fails to link to the ones it does. Measured before the fix: a module
  bound to `rocketmq` derived a row on `kafka`, complete, confident, with no question
  anywhere. NO configured name at all is a different answer and still takes the catalog's
  declared protocol — nothing was configured, so the catalog's own declaration is the only
  statement there is (§2c), which is a declaration rather than a fallback.

The SELECTION key is the one place environments are unioned rather than required to
agree, because it decides which rows EXIST rather than what a single-valued column holds:
entries are taken in environment order, so a bean selected in production binds in
production. An endpoint row says a boundary exists, never which profile it exists under.

**Ordering: `config_join` runs LAST**, after every call-site and annotation style,
whatever its own declared direction (§3) — it was the first style to need that, and
`schema_operations` later joined it. A style
that enriches rows other engines minted cannot run before those rows exist. The
consequence is real and not an accident: its rows are also the last to face §5's
insert-if-absent guard, so a wire identity another catalog already recorded stays that
catalog's row. **Within the style, every catalog declaring `address_from_config` runs
before every catalog that only stamps**, for the same reason one level down — filename
order must not decide whether a stamp arrives before the rows it was meant to enrich.
Direction and filename remain the tiebreaks after that rank.

**Every join this style makes is RECORDED with its full trail, and verified later.** The
trail is `resolved_config` (the key, its value, the file that won it, per environment)
plus the row's own `catalog_id` — enough for a reader, or a later pass, to reconstruct
exactly which key produced which address. §2d's second authority layer — an LLM
**verifying** a doubtful join, a human curation settling what it disputes — is deferred
to a later phase: the seat is deferred, never the evidence, and nothing here is ever the
sole source of an address an LLM invented.

### `schema_operations`

The ninth style, and the first whose evidence is neither a call site, an annotation nor a
configuration key: **a schema file states the operations outright**. A schema-first
service — a hand-built runtime wiring, no mapping annotation anywhere — derives nothing
at all without it, and the schema is the contract that service publishes.

```yaml
style: schema_operations
protocol: graphql
direction: inbound
detect: { coordinates: [] }     # the evidence is a file in the repository, not a dependency
requires: []                    # nothing scanner-produced is read
matches:
  schema_operations:
    schema_format: graphql      # which declared shapes this catalog speaks for
    operations: { query: query, mutation: mutation, subscription: subscription }
```

**What it reads is the module's `declared_shape` universe** — the facts the one
descriptor interpreter emits — and one field of one of those facts answers the whole root
question: `DeclaredShapeFact.role` ([D00](D00-fact-schema.md) §5) names the operation root
a type serves. **So this style parses no schema and re-derives no root name.** Which type
is the query root is a fact because a schema can *rename* its roots (`schema { query:
MyQuery }`), and no pass outside that one interpreter may learn a schema format. That is
also why there is no `root_types` table here: it would be a catalog guessing at something
already read. `schema_format` is the gate that makes the catalog's declared `protocol`
true of the rows — `role` is neutral across formats, and a root declared by some other
schema language is some other protocol's operation. A role the `operations` map does not
name derives nothing, the same "an unmapped value is a gap, never a column value to
invent" answer `config_join` gives an unknown binder.

**What it derives** is one row per field of a root type, at [D01](D01-graph-schema.md)
§3's root-operation identity — `method` from the `operations` map, `path` the field's own
`wire_name`. `resolution` is `resolved` (the schema states the operation outright, and
nothing about the address was left unread); `evidence` is the DECLARING SHAPE's own tier,
carried rather than restated, so a repository schema is `declared` and one the build
embedded would be `compiler`; `handler` and `caller` are both NULL, because a schema names
no code and the wiring that would is explicitly not read (a COVERAGE boundary).
`request_shape` is NULL for the same kind of reason — a root field's ARGUMENTS are what
the operation takes, and the interpreter deliberately does not project them.

**A `role` of `operation` derives PER SHAPE instead, and the engine says so** (Phase 2I).
Where `query`/`mutation`/`subscription` name a root type whose FIELDS are the operations,
`operation` names a shape that IS one — a WSDL input element is the whole request payload,
not a type some field returns — so iterating its fields would mint an endpoint per element
of a request body. One row comes from the shape itself: `path` is the shape's own schema
name (the QName), `method` is NULL because SOAP is verbless, and `request_shape` is **not**
NULL here but a self-reference to that same shape, because the wrapper element is what
goes on the wire. `response_shape` stays NULL and takes no stamp at all: the interpreter
marks input elements only, so no fact links an operation to what its output message names,
and an output join would be invented rather than read. `handler`, `caller`, `evidence` and
`resolution` read exactly as above. This is the one place the engine matches a role name
rather than reading it off catalog data; the catalog must still NAME the role to be read at
all, but the value it maps the role to is never consulted, since a WSDL input element names
no operation KIND for a `method` column to spell.

```yaml
# wsdl-schema.yml — framework-neutral, one file for one style, and its own
# because a contract belongs to no framework.
style: schema_operations
protocol: soap
matches:
  schema_operations:
    schema_format: wsdl
    operations: { operation: operation }   # a GATE; the value is never read
```

**Agreement with the annotation catalogs rides two existing mechanics, not a new rule.**
The style runs in the §3 runs-last group, so its rows meet the same insert-if-absent guard
every call-site style meets, LAST — an operation an annotation already derived keeps
THAT row, with the handler symbol only the annotation knows. A second statement then
stamps `response_shape` onto every matching identity that still has none, which reaches
the style's own rows and any annotation twin alike. **That stamp is deliberately transient
on an annotated row**: the shape pass runs after every engine and re-answers both payload
columns for any row still carrying a `handler_signature`, so an annotated operation ends
up publishing the types its own handler really serializes and the schema's declared type
is what a row with nothing else to say keeps. That is the no-class↔type-join rule arriving
by ordering rather than by a second guard. The declared response is a SCHEMA-NAME reference
within the declared universe; no join to a bytecode-derived class is attempted anywhere on
this path.

### `supertype_derived`

The tenth style, and the first that derives from a SUPERCLASS rather than a call site, an
annotation, a configuration key or a declared interface (Phase 2O Task 5). gRPC's own
generated server base (`<Service>Grpc.<Service>ImplBase`) is reached by `extends`, and a
Spring/net.devh gRPC service registers by bean scanning — there is no registration call
site for `interface_implementation` (above) to gate on, and no `implements` edge either.
The evidence is structural and pattern-free instead: protoc compiles the generated classes
INTO the module's own output, so both the extends edge
([D00](D00-fact-schema.md) §4's `relationship_kind: extends`, capability 9.13's
`superclass`) and the identity-building call sites the generated class makes are already in
the workspace's own facts.

```yaml
style: supertype_derived
protocol: grpc
direction: inbound
requires: [call_site, string_constants, superclass]
matches:
  supertype_marker:
    service_name_call: { owner: io.grpc.ServiceDescriptor, method: newBuilder }
    method_name_call: { owner: io.grpc.MethodDescriptor, method: generateFullMethodName }
  members: overridden_public_methods
```

**Where the identity comes from is a call-site argument, never a field value** (ruling R11,
superseding an earlier draft's `identity_marker: {constant: SERVICE_NAME}`):
[D00](D00-fact-schema.md) §5's `constant` fact kind has no producer in this codebase, so a
compile-time constant's VALUE cannot be read off the field that declares it. It is still
recoverable from bytecode alone, because the compiler inlines such a constant at every use
site (JLS 13.1/13.4.9): the service identity is `service_name_call`'s own FIRST argument,
read on the class whose facts make that call; the wire method name is `method_name_call`'s
own SECOND argument, one per RPC method the generated class builds a descriptor for. Both
markers are `{owner, method}`, never a combined `Owner.Fqn#method` string — every catalog
value is refused if it carries a `#`, reserved for the SCIP symbol grammar the fact stream
itself uses.

**The match has TWO conjuncts, and the marker call's PRESENCE is the first of them.** A
class matches only where its extends target is itself in the module's facts **and** that
target's own outer class MAKES one of the marker calls. Presence, not readability: whether
the call's arguments can be read is a separate question, answered after the match, and it
decides only resolved-versus-unresolved. Without the first conjunct the match reduces to
"extends a module-local class and publicly overrides one of its methods", which every
abstract-base/template-method pair in an ordinary repository satisfies — and each would then
mint an inbound boundary plus a ledger question on no protocol evidence at all. That is not
unresolved-is-an-answer; it is its converse failing: **no evidence means NO ROW, never an
unresolved one** (fix round 2, C-1).

**`members: overridden_public_methods`** is this style's one vocabulary word: a method the
implementing class declares under the SAME NAME as one the supertype itself declares,
PUBLIC on the implementer's own copy (an override may only widen visibility, never narrow
it, so the supertype's own copy need not be checked). "The registration is the evidence"
restated one level over: a class merely extending the generated base, overriding none of
its methods, derives nothing at all.

**One row per `(wire method, overridden method)` pair the marker calls and the overrides
agree on.** The wire method name in the row's own `path` always carries the literal
call-site string verbatim — **never derived by casing the compiled override's own method
name**, which is not invertible (a `mixedLower`-shaped transform can collapse more than one
proto spelling onto one compiled identifier). The one casing operation this style performs
runs the OTHER way: decapitalizing the wire name it already read, to find the matching
override name among what bytecode itself declared.

**That lookup is not injective either, and both of its failures REFUSE rather than guess**
(fix round 2, I-1). Where two wire names decapitalize onto ONE override — `GetOrder` and
`getOrder` are two distinct RPCs and both compile to one `getOrder` — **both** are refused:
deriving a row for each would carry the same handler symbol twice, and at least one of those
attributions is false. The class derives its unresolved fallback row and a `service_identity`
question naming the collision. Where an override no wire name reaches at all is found beside
siblings that DID correlate (`mixedLower` can move a proto name further than decapitalization
inverts), the correlating siblings still derive and the uncorrelated override is filed as a
`service_identity` question — a visible gap, never a silent drop.

**Where the constants cannot be read at all — CP-8(b)/(d) falsifying, not the supertype
being absent — the row still derives** ([D02](D02-catalog-schema.md) §2's unresolved-is-an-
answer): `path` the supertype's own bare descriptor verbatim, `resolution: unresolved`,
`handler` NULL, plus one `service_identity` open question naming the implementer class and
the reason. A supertype whose own facts never reached this workspace at all (a published
`*-grpc-stubs` jar, consumed without the library opt-in) derives NOTHING — not even the
unresolved fallback, which is reserved for a LOCALLY SEEN supertype.

`direction`/`protocol` are the catalog's own; `method` is always NULL (gRPC is verbless,
like every non-HTTP protocol); `caller`/`peer` are always NULL (the deriving method is a
`handler`); `request_shape`/`response_shape` are written NULL — this style contributes the
handler symbol only.

**They do not STAY NULL where a descriptor also covers the identity, and that took a fix**
(round 2, C-2). This style is not in §3's runs-last group, so its row is inserted first, and
`schema_operations`'s own insert at the identical `(protocol, direction, method, path)` is
then a no-op under the insert-if-absent guard. Its STAMPS are not: running last is exactly
what lets it fill `request_shape` and `response_shape` — and, riding the latter's `shape_id`,
the `unary | server-streaming | client-streaming | bidi` streaming word — onto the row that
survived, each stamp guarding its own column on `IS NULL` so a first writer is never
overwritten. The merged row therefore carries BOTH halves: this style's handler symbol and
the descriptor's own contracts. Before the fix it carried strictly less than the descriptor
row alone would have, which inverted the whole redundancy the two halves exist for.

### `injected_client`

A second, separate style from `supertype_derived` — injection is a different SHAPE of
evidence (a field the module declares and a framework populates, never a class the module
itself extends), and the rule that a style is a shape of evidence, not a framework, forbids
fusing the two into one engine, even though both read the same kind of identity-building
call site.

```yaml
style: injected_client
protocol: grpc
direction: outbound
requires: [call_site, string_constants, annotation_args, typed_signatures]
matches:
  field_annotation: net.devh.boot.grpc.client.inject.GrpcClient
  identity_marker:
    service_name_call: { owner: io.grpc.ServiceDescriptor, method: newBuilder }
```

**One row per injected stub, at the SERVICE level.** `method` stays NULL and `path` is
`<protoPackage>.<Service>` — the stub type's own outer class marker call, read exactly as
`supertype_derived` reads it (R11: a call-site argument, never a field value), or the stub
type's own bare descriptor verbatim where that call cannot be read. The injection declares
that the module TALKS TO the service; it does not declare which methods, and deriving one
row per service method would fabricate a boundary nothing here observes — per-method
outbound rows wait on a later phase's call graph, which can read the stub's own calls. An
unreadable identity derives the same unresolved-fallback-plus-gap pair
`supertype_derived` derives.

**The fence: an outbound row derives only for a service this module does NOT itself
implement.** Stated by SYMBOL NAME rather than by identity, because the fence must still
fire when the injected stub's own identity is unreadable (a module implementing a service
against PUBLISHED stubs has no local `SERVICE_NAME` to read either): does any of this
module's own classes carry an `extends` edge whose OUTER class matches the injected stub
type's own outer class? The extends RELATIONSHIP is a fact of the module's own class even
when its target lives in an unscanned jar — what the jar withholds is the identity, not the
edge — so this test survives the published-stubs-jar case an identity-based fence could not.

`direction` is always the catalog's own `outbound`; `handler`/`caller`/`peer` are all
NULL — the injection names no calling method of its own (a field declaration, not a call
site) and no handler. This is gRPC's SECOND identity form on [D01](D01-graph-schema.md)
§3's own table (`<protoPackage>.<Service>`, no method) — it links to nothing until a later
phase makes it per-method, the same honest-coarseness precedent SOAP's own two forms set.

### `derived_resource`

The twelfth style, and the first whose rows nobody DECLARED (Phase 2O Task 6). Spring Data
REST exposes a CRUD HTTP API from a repository INTERFACE — no controller, no mapping
annotation, no string in the module that is a URL. Not `annotation_driven` with `members:`:
that style reads a path and a verb OFF each member, while here the route table is fixed BY
FRAMEWORK RULE per repository — six verb/route combinations whose existence depends on
which CRUD contract is extended — plus one search route per query method.

```yaml
style: derived_resource
protocol: http
direction: inbound
detect:
  coordinates: ["org.springframework.boot:spring-boot-starter-data-rest", …]
requires: [annotation_args, implemented_interfaces, generic_interfaces]
default_produces: ["application/hal+json"]
matches:
  repositories:                     # contract fqn -> the CRUD operations extending it licenses
    org.springframework.data.repository.CrudRepository: [item_read, save, delete]
    org.springframework.data.repository.PagingAndSortingRepository: []
  routes:                           # the rule table; `needs` names the operation a route requires
    - { method: GET,  item: false }
    - { method: POST, item: false, needs: save }
    - { method: GET,  item: true,  needs: item_read }
  item_segment: "{id}"
  search_segment: search
  resource_annotation: org.springframework.data.rest.core.annotation.RepositoryRestResource
  member_annotation: org.springframework.data.rest.core.annotation.RestResource
  path_attribute: path
  exported_attribute: exported
  no_repository_bean: org.springframework.data.repository.NoRepositoryBean
  crud_methods: [save, findAll, findById, …]   # a declared method is a QUERY method only if not one of these
  base_path: { key: spring.data.rest.base-path }
  detection_strategy:
    key: spring.data.rest.detection-strategy
    strategies:                     # flags: public_only | annotated_only | honors_exported
      default: [public_only, honors_exported]
      all: []
      annotated: [annotated_only, honors_exported]
      visibility: [public_only]
```

**`detect.coordinates` is mandatory for this style and refused when empty** (§1): the rule
is conditional, and applying its consequent to a module that does not declare the library
would mint an entire REST API for every plain Spring Data JPA module in every analysed
repository.

**WHICH repositories are exposed is configuration, not a constant** (CP-2(0),
`scripts/probes/cp2_data_rest.md`, verified live). The default exposes every PUBLIC
repository honouring `exported = false`; `annotated` exposes only annotated ones — which
empties the un-annotated case this style exists for — `all` ignores both visibility and
`exported`, and `visibility` ignores `exported` alone. The engine reads the key
READ-IF-PRESENT and derives NOTHING when configuration names a strategy the catalog does
not enumerate, or names different ones per environment: which repositories are exposed is
the precondition of every row, and an unanswered precondition produces no rows.

**The collection path** is `path=` when the annotation gives one, else the entity's own
simple name — first character uncapitalized, then pluralized by `domain/pluralize.py`
(a port of Evo Inflector's rule set, which `spring-data-rest-core` depends on
non-optionally, so a working Data REST application always pluralizes). The ENTITY type
comes from capability 9.14's `generic_interfaces`: `interfaces` erases
`CrudRepository<Order, Long>` to a bare symbol, and the walk crosses interfaces DECLARED
IN THIS MODULE only (the `@NoRepositoryBean` base pattern; a base repository shipped in
another jar is a stated boundary).

**Rows publish at `resolved` / `declared`** — the mirrored rule IS the framework's rule
(DR-6, the 2I `reversed_package` precedent) — except where `spring.data.rest.base-path`
differs between environments, in which case one row carries the configuration EXPRESSION
as its prefix at `unresolved` and an `environment_divergence` question is filed. `handler`
is NULL on a CRUD row (framework code serves it, and no fact in the module names a symbol
for it) and the query METHOD's own symbol on a search row.

**Ordering (§3): this style is in the runs-last group.** A predicted route must never
displace an observed controller's row, and `derive_call_endpoints.sql`'s insert-if-absent
guard only means that if every observing style has already written.

### `supertype_dispatch`

The thirteenth style (Phase 2O Task 7b), and the second to read a SUPERCLASS — a sibling of
`supertype_derived`, deliberately not a widening of it. There the supertype is a generated
base the module COMPILES IN, whose own identity-building call sites carry the address, and
the match is gated on those calls appearing in the module's facts. Here the supertype is an
abstract base shipped in a DEPENDENCY, which the workspace never scans and which makes no
call anything could read, so the address comes from somewhere else entirely: **a type-level
annotation carries the address, the supertype fixes a dispatch contract, and the members the
class overrides name the operations.** Three pieces of evidence, jointly.

It is not `annotation_driven` either, and for the reason that engine states about itself: its
derivation joins METHOD symbols, and *"a type-level annotation mints no row of its own"*
(`derive_endpoints.sql:398-400`). Routing this shape through `members:` plus the
`path_fallback` that key requires would compose the type's address with each member's own
NAME — one fabricated address per member, none of them served (2O design §3b).

```yaml
style: supertype_dispatch
protocol: http
direction: inbound
requires: [annotation_args, type_annotations, typed_signatures, superclass]
matches:
  supertype: jakarta.servlet.http.HttpServlet
  address:
    annotation: jakarta.servlet.annotation.WebServlet
    args: [urlPatterns, value]
  members: overridden_dispatch_methods
  dispatch:
    - name: doGet
      parameters: [jakarta.servlet.http.HttpServletRequest, jakarta.servlet.http.HttpServletResponse]
      method: GET
  bypassed_by:
    - name: service
      parameters: [jakarta.servlet.http.HttpServletRequest, jakarta.servlet.http.HttpServletResponse]
```

**`supertype` matches the DIRECT superclass, by bare descriptor.** `superclasses` carries one
hop, and its target is module-prefixed even when it lives in a dependency jar
(CP-9 rows 27-28), so — unlike `supertype_derived` — the target being a module-local symbol
is neither required nor possible. A class reaching the supertype through an intermediate base
of its own is a STATED BOUNDARY, never a guess at what the intermediate declares.

**`address` is `{annotation, args}`, and `args` is an ALIAS SET of the argument
spellings that carry the address — exactly one of which a declaration writes.** Aliased
attributes reach the fact stream as their own distinct keys, so both must be named; more than
one present derives NOTHING rather than a winner, because a declaration writing both is one
the framework itself refuses to deploy, so the module serves nothing and either value would be
a fabricated address. Order-independent by construction. **Each value is its own
endpoint** — one declaration is N addresses, never one — and each is published VERBATIM: an
address argument may be a pattern grammar with its own precedence rules, and normalising one
would publish an address no probe covered. The RAW annotation table is read, never the
composed one: the frameworks reached by this style read the literal annotation written on the
class, resolving neither meta-annotations nor inheritance, and reading the composed view would
derive rows for a shape nothing serves (§8.1 rule 4).

**`members: overridden_dispatch_methods`** is this style's one vocabulary word, and its
selector is `{name, parameters}` — **a member is identified by its name AND its parameter
types in order** (GUIDELINES §8.1's language rule; arity is a consequence of that list, never
the rule). A same-named member whose parameter types differ overrides nothing, the supertype's
own implementation still applies, and a name-only selector publishes an address the framework
answers 405 to — measured, CP-9 rows 18 and 26.

**No visibility is read, and that is mirroring rather than relaxing.** [D00](D00-fact-schema.md)
§5a's `visibility` is two-valued, so a `protected` handler is recorded as `other` and the
column cannot say which (CP-9 row 24). It need not: an override may only widen the visibility
of the member it overrides, never narrow it, so a member declared under the supertype's own
name and parameter types IS the override at every visibility the language permits.

**`bypassed_by` discards the CLASS, never merely the member.** A class overriding the
supertype's own dispatch ENTRY POINT has replaced the lookup the table describes, and serves
every operation alike (CP-9 rows 14-15). Deriving the table's entries anyway would publish the
ones it names and withhold the ones it does not — a wrong answer, not a partial one. The key is
REQUIRED and may be empty: a supertype with no bypass says so, because an omitted bypass is
indistinguishable from a forgotten one and the forgotten one publishes wrong verbs.

**One row per handler the MODULE DECLARES.** A dispatch supertype may also serve operations
IMPLICITLY, off a member the module never overrode — measured, it does (CP-9 rows 7-9 and 32).
Those derive nothing: the code serving them is in a dependency this workspace never scanned, so
the row would carry either no handler at all or the symbol of a DIFFERENT member the implicit
path merely calls, and the second is false. A stated under-report in `docs/COVERAGE.md`, on the
same terms as the identical ruling Task 6 made for `derived_resource`'s own HEAD/OPTIONS.

**The complement of that rule decides the DEPLOYMENT question too**, and it is the sharpest
thing this style has to get right. An operation the class explicitly overrode is a handler the
module DECLARED, and a declaration is a code fact — so it derives, even where the deployment
the probe happened to run refuses to route to it. `doTrace` is the worked case: a Tomcat
connector rejects TRACE before dispatch unless `allowTrace` is set (CP-9 row 13), but
`allowTrace` is configuration outside the module that any deployment overrides and no
repository can see, so its default proves nothing (§8's "exclude only on proof, never on
inference"). Measured with the connector out of the way, `service()` dispatches TRACE to
`doTrace` exactly as it dispatches GET to `doGet` (row 31). The row derives and
`docs/COVERAGE.md` carries the connector as a **stated dependency**, in the shape Task 7 used
for Actuator's `exposure.include`. The test to apply is whether the thing withholding the
response is the framework's dispatch or somebody's deployment.

`resolution` is always `resolved` (an address argument is a compile-time constant of the
declaration itself; the one that cannot be read derives no row rather than an unresolved one);
`caller`/`peer` are NULL; and `handler_signature`/`request_shape`/`response_shape` are NULL
together, because a dispatch member's declared parameters are the framework's own request and
response objects rather than the wire payload — a non-NULL `handler_signature` is what tells
`derive_endpoint_contracts.sql` a row wants owner-keyed shape expansion, so writing one would
publish the dependency's API as the module's contract.

**Ordering (§3): NOT in the runs-last group.** Every one of its three evidence pieces is a fact
of the class itself, so it observes rather than predicts.

### `scheduled_work`

The fourteenth style, and the **first NON-WIRE one** (Phase 2O Task 8). It derives into
`scheduled_work` — a table of its own with no protocol, no address and no direction — and
never into `endpoints`: `endpoints` is wire-true, and a method the framework calls on a
clock serves no protocol anyone can address. A row claiming one would be a boundary nothing
serves.

```yaml
# spring-scheduling.yml
style: scheduled_work
# NO `protocol` AND NO `direction`. Their absence is a CLAIM, not an omission —
# see §1: `resolve/endpoints.py` refuses a non-wire style that declares either.
detect:
  coordinates: ["org.springframework:spring-context"]
requires: [annotation_args, nested_annotation_args]
matches:
  annotation: org.springframework.scheduling.annotation.Scheduled
  container: org.springframework.scheduling.annotation.Schedules
  triggers:                       # attribute -> the framework's own word for the schedule kind
    cron: cron
    fixedDelay: fixedDelay
    fixedDelayString: fixedDelay
    fixedRate: fixedRate
    fixedRateString: fixedRate
  disabled:                       # attribute -> the value the FRAMEWORK reads as "never"
    cron: "-"                     # `@Scheduled.CRON_DISABLED`, measured by CP-14
```

**`disabled` is optional, and its absence claims that the framework has no such value.**
Not that nobody looked: `OI-2` was exactly the second state, and what retires it is a probe,
so a catalog claiming a sentinel cites one in `measured:` and a catalog claiming none says
so in prose. A key naming an attribute `triggers` does not is REFUSED rather than ignored —
a sentinel written against the wrong spelling withdraws nothing, silently, which is the
mistake it exists to prevent. The value is compared against the expression the declaration
WROTE, after the "is this a literal we can spell" test and never before it, so an
unreadable value is never attributed to a disable nobody wrote.

**`container` is where extractor capability 9.16 is load-bearing, and the catalog REQUIRES
it rather than degrading.** Two or more `@Scheduled` on one method are folded by javac into
a single `@Schedules` whose `value` is an ARRAY OF ANNOTATIONS (JLS 9.7.5), so on a scanner
that cannot read a nested annotation such a method carries no readable trigger at all while
its single-schedule neighbour carries its own. Requiring the capability makes that scanner
skip the catalog VISIBLY (M04, FR-17) instead of reporting part of a module's scheduled
surface and staying silent about the rest.

**`triggers` is an ALIAS SET, not the annotation's attribute list.** `@Scheduled` also
carries `initialDelay`, `initialDelayString`, `zone`, `timeUnit` and `scheduler`, and not
one of them is a schedule. `initialDelay` is the sharpest: it is a duration, it sits beside
a rate, and reading it would publish the delay before the FIRST run as the interval between
every run. A declaration naming no trigger attribute therefore derives NOTHING — an
absence, not a refusal.

**Every expression is carried VERBATIM and nothing is evaluated.** A `${...}` placeholder
is preserved exactly as written with `resolution: unresolved` beside it, because a
placeholder's value comes from configuration a deployment can overwrite (GUIDELINES §8.2)
and substituting one here would publish a schedule this repository cannot know. `evidence`
is always `compiler`.

**Ordering (§3): NOT in the runs-last group.** A scheduled declaration is a fact of the
declaring class, not an enrichment of a row another engine minted — and its table is
untouched by `endpoints_reset`, so it could not participate in it.

**These rows are deliberately not roots, and the omission is SCOPED rather than permanent.**
[D00](D00-fact-schema.md) §4 documents a `root_kind` set whose members include `scheduled`,
and [D01](D01-graph-schema.md) §5 documents a `trace_of` walk. Neither exists anywhere in
`src/` (entries #7 and #11 of `docs/documented-not-implemented.md`), so nothing here is one
half of a live mechanism. **The omission becomes wrong the moment a `root_kind` producer
ships**: a scheduled method IS a root at that point, and these rows have to be re-examined
as roots rather than left as a table nobody traverses.

### `error_advice`

The fifteenth style and the **second non-wire one** (Phase 2O Task 8). It derives into
`error_handlers` for the reason `scheduled_work` has its own table: an exception handler is
not a boundary anyone can address, it is what happens INSIDE one that already exists.

```yaml
# spring-advice.yml
style: error_advice
# NO `protocol` AND NO `direction`, on the same terms as `scheduled_work` above.
detect:
  coordinates: ["org.springframework:spring-web"]
requires: [annotation_args, typed_signatures]
matches:
  handler_annotation: org.springframework.web.bind.annotation.ExceptionHandler
  advice_annotations:             # applies to controllers OTHER than itself
    - org.springframework.web.bind.annotation.ControllerAdvice
    - org.springframework.web.bind.annotation.RestControllerAdvice
  controller_annotations:         # its own handlers answer for that controller alone
    - org.springframework.stereotype.Controller
    - org.springframework.web.bind.annotation.RestController
  scope_from: [annotations, basePackages, basePackageClasses, assignableTypes]
  status_annotation: org.springframework.web.bind.annotation.ResponseStatus
  status_from: [code, value]      # an ALIAS ORDER, not a set
  exception_roots: [java.lang.Throwable, java.lang.Exception,
                    java.lang.RuntimeException, java.lang.Error]
```

**TWO container kinds, and they are different claims** — which is why `error_handlers`
carries `declared_by`. An advice class applies to controllers other than itself, to every
controller in the application when it narrows nothing; a controller's own handler methods
answer for that controller alone. A single NULL `scope` cannot tell those apart, and
reporting the second as the first would widen a handler's reach across the whole
application.

**Meta-annotations are followed the way the framework follows them**, for module-local
types: the composition pre-pass (`resolve/effective_annotations.py`) widens both the advice
set and the controller set to every annotation type THIS MODULE declares that is
transitively meta-annotated with one of them — the same mechanism `annotation_driven`'s
type-level gate uses, and for the same reason (§8.1 rule 1: a check for a literal
annotation name rejects a valid custom stereotype). A composed annotation whose type lives
in an unscanned jar is a stated boundary of the pre-pass.

**Exception types: the annotation's value, else the parameter type — and the second half is
deliberately narrower than the framework's own test.** The framework asks whether a
parameter is assignable to the language's throwable root; this workspace can answer that
only where the chain is READABLE, so `exception_roots` names the roots and the engine walks
each scanned class's own `superclass` edges up to one of them. All four are listed rather
than `Throwable` alone because the JDK's own hierarchy is never scanned: a module exception
extending `RuntimeException` reaches its root in one hop and would reach nothing if only the
top were named. A handler whose exception parameter comes from an unscanned jar derives no
row from that parameter, and COVERAGE says so. **The under-report is the only honest
direction**: nothing but a throwable reaches a throwable root, so this can never publish an
ordinary argument as a handled exception.

**One exception type per ROW.** A handler naming three types is three rows: each is a
distinct, separately answerable fact, and an array in one cell joins against nothing.

**`scope_from` deliberately omits `value`**, which is `@ControllerAdvice`'s own alias for
`basePackages`. Reading it verbatim under its own name would record the same scope twice
under two keys and make two identical declarations compare unequal. The consequence is
stated rather than hidden: an advice narrowed only by the bare `value` form records no
scope, which reads as "every controller" — the WIDER claim, so it can never under-report a
handler's reach.

**`status` is NULL where the declaration writes none, and NULL is an answer.** A status
computed inside a `ResponseEntity` body is `fluent` territory — body analysis that derives
no endpoint — and a `@ResponseStatus` on the EXCEPTION CLASS is readable only where that
class is in this module's own facts. Both are stated boundaries of this phase, not gaps
this column fills in.

**Ordering (§3): NOT in the runs-last group**, on the same terms as `scheduled_work`.

### `protocol_hint`

**Reclassifies endpoints other engines already produced** — a streaming response, a
long-poll. It changes protocol, never direction, and it never creates an endpoint.

**Execution amendment (Phase 2H): it is not an engine in the §3 runs-last group, and it
does not "run last with `config_join`".** That sentence predates resolve passes. It ships
as a resolve pass (`resolve/protocol_hint.py`, the 2G `format.py` precedent), and the
pipeline order is: engines → `parse_binding` → **`protocol_hint`** → `self_exchange` → the
format ladder. Both sides of that position are the pass's own contract. AFTER the engines,
because every row must exist before one can be reclassified. BEFORE the ladder, because rung 1 reads `protocol` directly, so a row answered before it
was reclassified would carry the format of a protocol it no longer has. It stays
catalog-declared: the vocabulary below is the whole of what it knows.

```yaml
protocol: http                 # the catalog's own protocol — the SOURCE, never named in the block
protocol_hint:
  protocol: sse                # the TARGET
  hint_media: [text/event-stream]
  hint_returns: ["…annotation.SseEmitter"]
```

**Three promises, and they are the whole contract.** (1) It changes `protocol`, never
`direction` — direction is resolved at match time (§2c), and a pass that moved it here
would move a row out from under the question `self_exchange` is about to ask, which reads
both directions on one identity (F5 §6.1). (2) It never creates or deletes an endpoint; the row count is
identical before and after. (3) It only ever moves a row of the SOURCE protocol its own
catalog declares — the block is scoped by the catalog's own `protocol` field, so an HTTP
catalog can only reclassify HTTP rows and the graphql, websocket and messaging rows no
catalog names as a source are untouchable rather than merely untouched.

**Two evidence kinds, media first**, because a row whose own declared media names the
protocol's envelope is the cheaper and stronger read — it is the channel's own
declaration, made in the source. The return-type read exists because a handler may declare
no media at all and still be a stream.

- **`hint_media` reads `produces` ONLY, on every row, whatever its direction** — and this
  is deliberately narrower than the format ladder's rung 2, which folds both media columns
  into one answer. `format` describes one wire and both columns describe it; a PROTOCOL
  hint is the narrower claim *this channel IS an event stream*, and only `produces` can
  evidence it. On an inbound row it is what the route streams back; on an outbound
  one it is what a caller expects to receive — evidence either way. `consumes`, on ANY
  row, means "this accepts event-stream REQUEST BODIES", and a channel is not named after
  what it eats. Reading `consumes` on a client-side row (where it is what the client
  RECEIVES) is refused for that reason alone since W27 deleted the merge: the ambiguity
  that used to make it unreadable — a merged row's `consumes` being either half's, with
  nothing saying which — is gone, and the rule stays because one column with one meaning
  is worth more than the outbound case it gives up, which no shipped catalog produces.
- **`hint_returns` matches a marker type appearing ANYWHERE in the handler's return
  type** — the outer symbol, or any symbol reachable through nested type arguments, to any
  depth. Both halves of that rule are load-bearing because the two real shapes sit at
  opposite ends of it: `SseEmitter` is a flat return whose own symbol IS the marker, while
  `Flux<ServerSentEvent<T>>` carries the marker in the MIDDLE of a two-level chain under
  an ordinary reactive outer type. Matching only the outer symbol catches the first and
  misses the second entirely; matching only nested arguments does the reverse. A row with
  no handler declares no return type and is answered by its media or not at all.

**How the two lists merge across catalogs differs, and on purpose.** The target protocol
is single-valued per source, so two catalogs of a family disagreeing about it is REFUSED
rather than resolved (picking either side would make the answer depend on filename order).
The evidence lists are UNIONED, because they are additive — a family's two catalogs each
name the markers their own artifact declares, and a module pulling in one of them must
still get that one's. `hint_media` is an HTTP media declaration and is therefore
duplicated across the family exactly as `media_formats` is; `hint_returns` names LIBRARY
types and each is declared once, by the catalog whose artifact declares it.

**A malformed block is refused at run start**, four ways, each a case where reading on
would make a broken catalog look like an absent one: an unknown key; a target outside
[D00](D00-fact-schema.md)'s protocol set or equal to the catalog's own; an evidence list
that is not a list of strings; and a block naming no evidence at all, which is exactly what
declaring no block already means.

**One thing outside `endpoints` moves with a row: its `open_questions`.** The ledger
snapshots a wire identity rather than joining to it ([D01](D01-graph-schema.md) §3), and
the payload-binding pass took that snapshot before this one ran — so without the follow-up
a reclassified row's question would publish one protocol while the endpoint published
another. (A `format_conflict` question cannot go stale: the ladder runs afterwards.)
**The ledger match is WIDER than the endpoint match, and that is a stated limitation**: a
question carries three of the six identity columns — no `direction`, `handler` or
`caller` — because a question is about a wire identity, not a symbol. Where two endpoint
rows share `(protocol, method, path)` and only one reclassifies, a question belonging to
the other moves too. Moving is still the right side to err on; a future ledger carrying the
handler could tighten it.

### `filesystem`

> **SPECIFIED HERE, NOT YET USED.** There is no `filesystem` engine in
> `application/resolve/endpoints.py`'s `_ENGINES`, no shipped catalog declares this style,
> and a catalog that declared it would raise `CatalogError` from `_engine_for` at the top of
> `derive_endpoints` — before any table is touched, so the run aborts rather than degrading.
> Everything
> below is design for a phase that has not run — the shape of the evidence, the source
> precedence, and the vocabulary a catalog would use — and none of it describes behaviour
> that exists. Stated in the document rather than left to a grep, per §5.3's second
> corollary.

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
`Mono<ResponseEntity<OrderResult>>` roots the shape at `OrderResult` — and the chain is
consumed where it is produced, never stored on the endpoint: `optional` semantics feed
`required`, `async` and `streaming` feed the flags below, and nothing records the chain
itself on the endpoint row — a second copy could only ever disagree with the columns that
already hold what it decided. `semantics` is a closed set. **`streaming` is NOT what feeds
`protocol_hint`** — an earlier draft of this paragraph said it was, and Phase 2H's
implementation shows why it cannot be: `Flux` is `streaming` on every reactive route in a
WebFlux service, and reclassifying all of them would rename ordinary REST as SSE. The pass
matches a named MARKER TYPE (`hint_returns`, §2's `protocol_hint`) instead. Of the set,
**`optional` is the only value any shipped pass branches on** — it is what makes a rooted
payload's `required` false. `async` stays specified as the marker for the
blocking-call-on-async-path finding (FR-14), which no pass computes yet; `streaming` and
`http_envelope` are labels for a reader. An unfamiliar generic
wrapper with no declaration is **not unwrapped** — the shape roots at the wrapper and the
endpoint records that no wrapper rule matched, so an incomplete catalog degrades visibly
rather than guessing.

**`payload_arg` already positions the payload type argument, so messaging's
`ConsumerRecord<K, V>` needs no new carrier extension** — its payload is simply
`payload_arg: 1`, declared the same way as every other wrapper above. The spec's
`payload_type_arg` carrier extension (§7 permission) is dropped as redundant; recorded
here so it is not reintroduced.

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
- **A `@GetMapping` returning `SseEmitter` is not REST.** Shipped in Phase 2H, and **not
  the way this bullet originally sketched it**: not through `wrappers`' `semantics:
  streaming`, which every reactive route carries, but through `protocol_hint`'s own
  `hint_returns` marker list plus a `produces: text/event-stream` read — and as a
  post-merge pass rather than at match time, because a protocol may be rewritten
  afterwards where a direction may not (§2's `protocol_hint`).
- **Format is rarely constant.** `produces = "application/x-protobuf"` changes the wire; a
  payload type extending a generated message says the same thing; a Kafka `value.serializer`
  says it in configuration rather than code.

So a catalog may declare resolution rules alongside its defaults. **This is the sketch, not
what shipped** — the shipped form is the block below it:

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

### `resolves.direction`, as built (2O Task 10)

Shipped on `spring-http-interface.yml`, the only catalog that declares `resolves` at all, and
read by `annotation_driven` alone. It differs from the sketch in three ways, each of which is a
correction rather than a simplification:

```yaml
resolves:
  direction:
    - when:
        owner_implemented_by_type_annotated:
          - org.springframework.stereotype.Controller
          - org.springframework.web.bind.annotation.RestController
      then: inbound
```

1. **The condition is not `owner_implemented_in_module`.** That one is weaker than the
   framework's own rule and fabricates: Spring dispatches to a handler BEAN, and its handler
   test is one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call carrying
   no `@RequestMapping` disjunct — measured on spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9
   (`scripts/probes/cp7_http_exchange.md`). A plain `@Service` implementing an exchange
   interface is served by nothing, so an inbound row for one invents an endpoint. The shipped
   condition `owner_implemented_by_type_annotated` reads: *the type enclosing this declaration
   is implemented, in this module, by a class carrying one of these annotations*. The fqns are
   catalog data — the same values `spring-mvc.yml` and `spring-web.yml` declare as their own
   `type_annotation` — because which annotation marks a handler bean is the framework's
   convention, never an engine's to know.
2. **The condition vocabulary is CLOSED** (NFR-5), one word today, and a `when` naming anything
   else is REFUSED rather than read as "never flips" — by the engine, where `declared_on` and
   the `mapping` vocabulary are also checked, not by the loader. So is a `resolves` block
   naming any key but `direction` (`format` is named in this section and did not ship, so a
   rule written under it would be one nothing runs), and so is a `then` outside D00's
   direction set or equal to the catalog's own declared direction — a rule that resolves
   nothing is a file claiming a flip it does not perform.
3. **Exactly ONE rule, not a list evaluated in order.** First-match-wins over several
   conditions is this section's stated semantics and nothing shipped needs it; an engine
   honouring one rule while accepting a list would silently drop every rule after the first, so
   a second rule is refused until the semantics is built.

**What a flipped row carries.** The resolved direction, and the handler that goes with it: the
symbol handling a flipped declaration is the IMPLEMENTING type's own member where it declares
one, and the declaring member itself where it does not — a `default` method the implementer
never overrides is still selected and served, because the framework's handler-method walk
covers the type's interfaces (CP-7 Q3). Its address is canonicalized under the rule for the
direction the row TOOK, not the one the catalog declared, which is what lets it merge with the
identical route a controller's own mapping derives (§3's dedup, ruling R12 — there is no
collision detector and this needs none).

**Where the interface gate and the flip meet.** An OUTBOUND catalog declaring
`declared_on: interface` also engages §2's implemented-interface fence, which subtracts every
interface the module implements. The fence and the flip answer the same question with opposite
answers, and the fence's is the coarser: it YIELDS where the flip's condition holds. Shipping
both unconditioned cancels — the fence subtracts exactly the rows the flip must flip, and no
inbound row survives.

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

### Format, as built: the six-rung ladder

The `resolves.format` sketch above is **not what shipped, and neither is a catalog-level
`format:` default.** Format turned out not to be resolvable per match at all: the evidence
that settles it — a declared MIME string, a configured serializer class, the payload type a
shape pass bound — is spread across columns that do not all exist yet when a match is being
made, and some of it is not on the row at all. So `format` is answered by **one late pass
over the finished `endpoints` table**, after media stamping and after payload binding, and
it stamps [D01](D01-graph-schema.md) §3's two columns on **every** row. `direction`
resolution is unaffected: it still has to complete before §3's merge, for the reason stated
above.

The pass climbs six rungs. **The first rung that answers, wins**, and the answer carries
that rung's resolution tier:

| | Rung | Answers from | `format_resolution` |
|---|---|---|---|
| 1 | Fixed by protocol | the protocol's own constant format, `format_fixed` | `resolved` |
| 2 | Declared media | the row's own `consumes`/`produces`, through `media_formats` | `resolved` |
| 3 | Serializer config | the class the module's configuration names, through `format_from` | `resolved` |
| 4 | Payload hierarchy | the bound payload was described by a **schema**, and the schema names its own format | `narrowed` |
| 5 | Framework default | an ordinary declared payload, plus a default converter present in the module — a marker package family named by any fqn the module names, or a marker dependency coordinate the analysis recorded (`json_default_markers`) | `narrowed` |
| 6 | Nothing | — | `unresolved`, `format` NULL |

**Two rules bind the whole ladder.**

**An assumed format must never look observed.** A framework default is recorded, but at
`narrowed` — never at the tier a `produces` attribute or a configured serializer earns.
That is the §2c rule above ("a default that survives unchallenged is not an observation"),
carried into a column instead of an evidence tier.

**A payload's TYPE does not determine the wire, which is why rung 2 sits above rung 4.**
Proto3 defines a JSON encoding, so a protobuf-typed payload under `produces =
"application/json"` is `format: json` — and the shape's `wire_name` (the `json_name`) is
what a JSON wire carries, while its `name` and `field_number` are what a protobuf wire
does. Reading the wire off the payload's type would be a confident wrong answer exactly
where the proto3 rename above makes the mistake most expensive. Rung 4 is therefore
`narrowed` at best: negotiation the pass cannot see may still put the JSON encoding on the
wire.

**Rung 4 is silent for a schema language that is not also a wire format** (added in Phase
2H, when the first such language arrived). A `declared_shape`'s `schema_format` names the
schema LANGUAGE that described the payload ([D00](D00-fact-schema.md) §5): protobuf and
Avro define an encoding, so "described by this schema" really does suggest bytes; GraphQL
states a type system and leaves the transport to say how it is written, so it suggests
nothing this column can hold. Since `endpoints.format` is closed at
[D00](D00-fact-schema.md) §4's six values (NFR-5) and the stamp applies rather than
decides, a rung 4 that published its input verbatim would put a non-member straight into a
closed column, where a reader cannot tell it from an observation. Such a shape therefore
contributes no candidate and the row falls to a weaker rung or to `unresolved`, which is
the honest answer. Rung 1's `format_fixed` masks this on today's live GraphQL rows — and a
mask is not a rule, which is why the guard is stated and tested rather than left to it.

**A rung that answers with more than one format answers with none.** Two MIME types
meaning different formats, a merged row whose two halves' configured serializers disagree,
a request described by one schema format and a response by another: the row records
`unresolved` and the impasse becomes an `open_questions` row of kind `format_conflict`
([D01](D01-graph-schema.md) §3) carrying the candidates and the trail. **The ladder stops
at a conflict rather than falling through** — a weaker rung breaking a tie that stronger
evidence could not is precisely the guess the ledger exists to avoid.

### The five format vocabularies

Every framework, protocol, MIME, class and package name the ladder compares against is
catalog data; no engine learns one. Three are top-level blocks, one rides inside
`media_from_config` (§2d), and one is read by the payload-binding pass rather than by the
ladder itself.

```yaml
# Rung 1 — a protocol whose wire is constant by definition. Shipped by the
# catalog that owns the protocol, never hardcoded. LIVE SINCE PHASE 2H:
# `format_fixed: {graphql: json}` ships on all four catalogs that own the
# graphql protocol (the three annotation catalogs and `graphql-schema.yml`),
# which closed this branch's documented dead end. PHASE 2I added the second
# such protocol: `format_fixed: {soap: xml}` ships on all five catalogs owning
# `soap` — a SOAP envelope IS an XML document, so no handler-level declaration
# can make it anything else. gRPC still has no catalog, so `grpc: protobuf`
# remains an illustration.
format_fixed:
  graphql: json

# Rung 2 — what a declared MIME string means on the wire. `text/event-stream`
# is deliberately ABSENT, and its absence is a rule rather than an omission:
# it is the ENVELOPE, not the payload, so mapping it to anything would state a
# format nobody declared. It IS read — by `protocol_hint` (§2), which names a
# PROTOCOL from it, a different column and a different claim.
media_formats:
  application/json: json
  application/x-protobuf: protobuf
  application/protobuf: protobuf
  avro/binary: avro
  application/xml: xml
  text/xml: xml

# Rung 5 — markers whose PRESENCE anywhere in the module is evidence that a
# JSON default converter is available. Both Jackson generations: the
# relocation between them is a package rename and nothing else.
json_default_markers:
  - com.fasterxml.jackson
  - tools.jackson
  # The second FORM (2O design §7): a dependency coordinate rather than a
  # package family, because Boot auto-configures the converter from the jar's
  # mere presence — a module can carry it and name none of its packages
  # (checkpoint CP-6, confirmed live).
  - coordinate: com.fasterxml.jackson.core:jackson-databind
```

**A marker has two forms and no third** (2O design §7). A bare string is a **package
family**, matched against every fqn the module names — the annotations it carries and the
call-site owners it invokes; a `{coordinate: "group:artifact"}` mapping is a **dependency
coordinate**, matched against the coordinates this analysis recorded ([D00](D00-fact-schema.md)
§2's `origin`). Anything else is refused at load, the discipline every value in this
vocabulary keeps: a marker nothing recognizes answers nothing, and a rung that answers
nothing reads exactly like a converter that is genuinely absent. The coordinate form
answers only for a dependency this run actually read — a jar nobody opted into is not
recorded, and silence about it is the honest answer rather than a guess.

**The two map tables are unioned across every catalog that declares them**, rather than
scoped to one: a MIME string means the same format whoever wrote it down, and a row that
several engines have contributed to carries no catalog of its own. **Two catalogs
disagreeing about one key is refused, not resolved** — the same table deliberately ships on
more than one catalog of a family (each owns its own protocol), so the collision is a real
editing mistake, and picking either side would make the answer depend on filename order.
`json_default_markers` is a list rather than a map, so it merges without a collision to
have; every marker in it means the same format anyway.

**Every declared format value — in `format_fixed`, `media_formats` and the `format_from`
below — is validated against [D00](D00-fact-schema.md) §4's closed format set before
anything is stamped**: a whole catalog is refused rather than a table half-read, the same
discipline the configuration model keeps. And **`json_schema` is
refused by name**: the design names it, nothing implements it, and a catalog writing it
must fail loudly rather than be read as something adjacent (the reserved-value pattern §2i
already uses for `from_key_prefix`). Note the distinction the Kafka table below turns on — Confluent's
JSON-Schema serializer puts plain **JSON** on the wire and carries the schema out of band,
so it maps to `json`; `json_schema` is about the schema *language*, which is out of scope.

**`format_from` — rung 3 — rides beside `media_from_config`'s `values`** (§2d), because the
rules that say *which* configuration key holds a serializer and *which rows it covers* are
already stated there; a second copy of that machinery keyed on the same configuration would
be two things to keep in step. The two tables answer different questions about the same
declared class — what MIME type it implies, and what is actually on the wire — and **their
key sets deliberately differ**. A schema-registry serializer has no MIME string anyone
registered, so it appears in `format_from` and not in `values`: it stamps no media and
answers rung 3 instead, which is the more honest of the two answers. The reverse also
holds. Where a module both exposes and calls one identity the two rows stand apart (F5
§6.1, W27), each covered by the rules for its own direction — and where their configured
classes mean different formats, that is a real disagreement about one wire, recorded as a
`format_conflict` rather than resolved.

**`parse_calls` — read by the payload-binding pass, not by the ladder.** It says which
payload parameter types mean *this channel carries the wire's bytes* and which calls turn
those bytes into a typed payload:

```yaml
parse_calls:
  bytes_payloads: [java.lang.String, "byte[]"]
  calls:
    - owner_hierarchy:
        - com.google.protobuf.MessageOrBuilder
        - com.google.protobuf.GeneratedMessage
        - com.google.protobuf.GeneratedMessageV3
        - com.google.protobuf.GeneratedMessageLite
      method: parseFrom
      bytes_arg: 0
      payload_from: receiver_owner
    - { owner: com.fasterxml.jackson.databind.ObjectMapper, method: readValue,
        bytes_arg: 0, payload_from: class_arg, class_arg: 1 }
    - { owner: tools.jackson.databind.ObjectMapper, method: readValue,
        bytes_arg: 0, payload_from: class_arg, class_arg: 1 }
    - { owner: tools.jackson.databind.json.JsonMapper, method: readValue,
        bytes_arg: 0, payload_from: class_arg, class_arg: 1 }
    - { owner: org.apache.avro.specific.SpecificDatumReader, method: "<init>",
        payload_from: class_arg, class_arg: 0 }
```

An entry names **exactly one** of `owner` (identity) or `owner_hierarchy` (ancestry),
a `method`, and a `payload_from` of `receiver_owner` (the parse whose receiver *is* the
payload type) or `class_arg` (the parse handed a class literal, with `class_arg` naming its
position). A malformed entry is refused at run start rather than silently matching nothing.

**Why protobuf matches through `MessageOrBuilder` and not through the `extends
GeneratedMessage` the hierarchy evidence elsewhere names.** A plain `extends` is **not in
the fact stream at all**: [D00](D00-fact-schema.md) §5a emits a `supertype` reference only
for a *generic* superclass, and a generated message's superclass is not generic. What the
facts do carry is the message's own `implements …OrBuilder`, and that interface's own
`extends MessageOrBuilder` — an interface chain, which §5a does record. So the marker that
actually joins is `MessageOrBuilder`, and it is listed first for that reason. The three
`GeneratedMessage*` spellings ride along for the case where a generic supertype does name
one (a generated *builder*'s does). The lite runtime reaches none of these and binds
nothing — silence, never a wrong payload type.

**The Avro entry ships inert, deliberately.** `SpecificDatumReader`'s constructor names the
payload type and nothing else: the bytes reach a separately built decoder, never that call.
It therefore declares **no `bytes_arg`**, and no rung can prove the channel's bytes reach
it, so it binds nothing today. It is declared because the entry is where the type will
already be the day a decoder-tracing rung exists — and because an entry that named a
`bytes_arg` it could not justify would bind a payload on the strength of being in the right
method.

---

## 2d. Addresses that live in configuration

Some frameworks put no destination in the code at all. A Spring Cloud Stream `Consumer<Order>`
bean named `handleOrder` reads a Kafka topic named nowhere in the source; the topic is under
`spring.cloud.stream.bindings.handleOrder-in-0.destination`. SmallRye's `@Incoming("orders")`
names a channel, not a topic — that is `mp.messaging.incoming.orders.topic`. MicroProfile's
`@RegisterRestClient(configKey="orders")` finds its URL under `orders/mp-rest/url`.

The pattern is constant: **the code carries a name, and configuration says what the name
means.** Configuration resolution is already a first-class pass, so what is missing is only
the vocabulary for the derivation. Two vocabularies read `resolved_config` this way:
`address_from_config`, below, and `media_from_config` (end of this section), which stamps a
module's declared media types from the same source rather than an address. A catalog
declares the first:

```yaml
address_from_config:
  key: "spring.cloud.stream.bindings.{binding}.destination"
  binding:
    from: bean_name
    selected_by: spring.cloud.function.definition
    suffix:
      - { when: { implements: java.util.function.Consumer }, then: "-in-0", direction: inbound }
      - { when: { implements: java.util.function.Supplier }, then: "-out-0", direction: outbound }
      # A Function is both halves at once: its one entry derives TWO rows,
      # `-in-0` inbound and `-out-0` outbound, each through the same key template.
      # `direction` and `payload_arg` are read in PARALLEL with `then` — see the
      # `config_join` style (§2) for the as-implemented grammar.
      - { when: { implements: java.util.function.Function }, then: ["-in-0", "-out-0"],
          direction: [inbound, outbound], payload_arg: [0, 1] }
```

**A candidate bean is a method whose return type is, or implements, one of the declared
interfaces** — checked on the returned type through the `interfaces` facts the
`interface_implementation` style already reads ([D00](D00-fact-schema.md) §5a's
`implemented_interfaces` capability) — **and its bean name is the method's own name**,
Spring's own default, stated here so no later pass re-derives it.

**`selected_by` names a configuration key that narrows the candidate set**, read through
`resolved_config`: absent, every candidate binds — Spring's own default when
`spring.cloud.function.definition` is not set. A `definition` value containing `|`
composes two or more functions into one binding and is not decomposed here — the
vocabulary records the whole expression rather than guessing which function contributed
which half.

**Each `suffix` entry carries its own `direction`.** A `Consumer` is inbound, a `Supplier`
outbound; **a `Function` is both halves at once, and its one entry derives TWO rows** —
`-in-0` inbound and `-out-0` outbound, each built through the same key template — rather
than a single row whose direction cannot say which.

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
expression. The coverage report names the DERIVATION — by its `catalog_id` and its
`handler`/`caller`, since the bean method exists even where its binding key does not — and
names a missing KEY only where some configuration file actually declared it: a key nobody
wrote leaves no `resolved_config` row to be missing FROM, so there is nothing for the
report to name it by (the no-channel boundary Task 7's review discovered, recorded in
[COVERAGE.md](../COVERAGE.md)). Dropping the row would make a partially-configured module
look like a module with fewer boundaries.

**`media_from_config` stamps declared media onto messaging endpoints from the same resolved
keys, rather than deriving an address:**

```yaml
media_from_config:
  rules:
    - { key: spring.kafka.producer.value-serializer,   fills: produces, on: { protocol: kafka, direction: outbound } }
    - { key: spring.kafka.consumer.value-deserializer, fills: consumes, on: { protocol: kafka, direction: inbound } }
  values:
    org.springframework.kafka.support.serializer.JsonSerializer: application/json
    org.apache.kafka.common.serialization.StringSerializer: text/plain
    org.apache.kafka.common.serialization.ByteArraySerializer: application/octet-stream
```

Each `rules` entry names a resolved config key, which of `consumes`/`produces`
([D01](D01-graph-schema.md) §3) it fills, and the `(protocol, direction)` pair of rows it
applies to; `values` maps the resolved class name to the MIME string it means — the
config-declared evidence kind [D01](D01-graph-schema.md) §3 already reserves a place for.

**A stamp lands only where every resolved environment agrees.** A serializer that differs
across environments leaves the column NULL with the disagreement recorded as a degrade —
[D01](D01-graph-schema.md)'s `consumes`/`produces` are single-valued, so a per-environment
split cannot be forced into one column without inventing an answer neither environment gave
alone. **A stamp never overwrites a non-NULL column** — the same first-writer discipline
every other media-declaring evidence kind already follows. **An unresolved or unknown
serializer class stamps nothing**: the class name still lands in `resolved_config`
regardless, which is what a later format-inference pass reads; a class absent from `values`
is a gap to grow the catalog from, not a guess.

**A second table sits beside `values` in this same block: `format_from`** — the same
configured classes answering the other question, *what is actually on the wire* rather
than *what MIME type this implies*. It is read by the format ladder's rung 3 and specified
in §2c above, here rather than in a block of its own because the `rules` above already say
which key holds a serializer and which rows it covers.

The engine that runs both `address_from_config` and `media_from_config` — `config_join`,
the eighth style — has its own full section in §2 above; this section specifies the
vocabulary the two jobs read, and §2 specifies what the engine does with it, including
the two separators (`selection_separator`, `composition_separator`) that give the list
and composition semantics described in prose here a spelling a second framework family
can override.

**Job 3, peer resolution, is a JOIN and never a write** — the `resolved_peers` named
query ([D01](D01-graph-schema.md)): every client-side row's `${...}`-bearing `peer` and
`path` expressions, substituted against `resolved_config` once per environment. A literal
passes through as itself; a single placeholder is substituted; an expression carrying more
than one surfaces with `unresolved_reason: multi_placeholder` — the one reason M04's pass
2 never emits, because it is a property of an endpoint expression rather than of a
configuration value. Endpoint rows are untouched, in every environment.

---

## 2e. Nullability declarations

**Declared in the shape model, not in a catalog (§1b).** The block below is the
grammar; the one shipped copy of it lives in `catalogs/shape-models/json.yml`, and a
catalog reaches it with `shape_model:`. A catalog declaring one of its own is refused.

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

**Declared in the shape model, not in a catalog (§1b).** The block below is the
grammar; the one shipped copy of it lives in `catalogs/shape-models/json.yml`, and a
catalog reaches it with `shape_model:`. A catalog declaring one of its own is refused.

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
  accessors:                         # optional; which methods name a property
    - { prefix: get }
    - { prefix: is, wire_type: boolean }
```

**`accessors` is read only where a type's fields describe nothing.** Fields come first
and keep every shape that already had one; the accessors answer the types whose wire
contract is not in their fields at all. An **interface** is the whole case: it declares
no fields, so `Page<T>` and `Slice<T>` — the most common paginated Spring response —
expanded to a zero-field shape however well the type was reached.

**A prefix may constrain the return's `wire_type`.** `is` names a property only on a
boolean, which is jackson-databind's own `findNameForIsGetter`; without the constraint
`isoCode(): String` becomes a field called `oCode`. The name is then Jackson's
`legacyManglePropertyName`: a bare `get()` names nothing, and the leading run of capitals
is lowercased whole before the remainder is appended (`getURL` → `url`, `getURLValue` →
`urlvalue`).

**Only public, non-static, non-synthetic, zero-argument methods with a return.** Each
clause drops something a looser rule would publish as a wire field — `hasNext()`,
`nextPageable()`, a private accessor, a bridge method javac generated.

**Accessors are collected across the scanned ancestry**, in JVMS 5.4.3.3's order, with
the first declaration of a property name winning. `Page` declares only `getTotalPages`
and `getTotalElements`; `getContent()` — the accessor the payload travels in — is on
`Slice`. Reading only the named type would publish a paged response whose metadata is
present and whose content is missing.

**Substitution is by variable name across that ancestry**, so `Page<T> extends Slice<T>`
binds `getContent(): List<T>` to the argument `Page` was given. A hierarchy that renames
the variable leaves the field holding an unbound one, which names no type: the field is
undescribed and the shape stays open, which is the answer it had before this existed.

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

**Declared in the shape model, not in a catalog (§1b).** The block below is the
grammar; the one shipped copy of it lives in `catalogs/shape-models/json.yml`, and a
catalog reaches it with `shape_model:`. A catalog declaring one of its own is refused.

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

## 2j. What a call reaches — `terminals`

**A top-level, optional block** (F7 §8.2, W30). It answers [D00](D00-fact-schema.md) §4's
`terminal_kind` for a call whose callee's body this workspace did not read, and it exists
because that set had no producer for two phases for a reason D00 states plainly: *a
data-access call is `persistence` only to something that knows the callee is one.* This is
where that knowledge is written down.

```yaml
terminals:
  - { owner: jakarta.persistence.EntityManager, kind: persistence, target: database }
  - { supertype: [org.springframework.data.jpa.repository.JpaRepository],
      kind: persistence, target: database }
  - { scanned_by: org.mybatis.spring.annotation.MapperScan, packages_from: value,
      kind: persistence, target: database }
```

`kind` is a member of D00's `terminal_kind` set; `target` is `persistence`'s own sub-field
(`database`, `cache`, `file`) and is omitted for every other kind. Each rule names exactly
one of three ways to recognise the callee, and **each exists because a real framework needs
it** — measured on three repositories before any of them was written:

- **`owner`** — the call lands on the library type itself. `EntityManager` is 82 of
  `spring-petclinic-rest`'s terminals; `RedisTemplate` is 41 of `mall-admin`'s and is the
  rule whose `target` is `cache` rather than `database`.
- **`supertype`** — the owner implements a declared type, read from `type_hierarchy`
  ([D01](D01-graph-schema.md) §3, W21). `jhipster-sample-app`'s repositories are its own
  interfaces carrying no annotation at all; the class file says they implement
  `JpaRepository`. **The match is transitive but stops at the first unscanned type**, so a
  catalog must name the level a USER extends: naming only Spring Data's base `Repository`
  classified 2 of that corpus's 75, because `JpaRepository` comes back `scanned: false` and
  has no rows of its own.
- **`scanned_by`** — an annotation names PACKAGES and every type inside them qualifies.
  `mall-admin`'s MyBatis mappers carry no annotation; `@MapperScan({"com.macro.mall.
  mapper"})` on a config class is how MyBatis registers them, and that is 199 terminals.
  `packages_from` names the attribute holding the list and defaults to `value`. A package
  matches its own subpackages and never a sibling whose name merely shares a prefix.

**None of the three is a name match, deliberately.** `*Mapper` and `*Repository` are naming
conventions and §8.1 forbids a rule weaker than the one the framework applies: matching by
name would claim every unrelated type ending that way, and miss every one named otherwise.

**Routes are tried owner, then supertype, then scanned package** — most specific first, so
a catalog can name one type out of a scanned package and have that win.

**Where it lives.** On the family's base catalog, the rule `config_model` already follows:
a terminals-only file cannot be a catalog (`style` and `matches` are required and it
declares no boundary), and every catalog is loaded regardless of gating, so the rules reach
every module.

---

## 2h. Type carriers and call wrappers

Two more argument-resolution declarations, both read through the `instance` argument kind
([D00](D00-fact-schema.md) §5) — the concrete type a `NEW` or constructor call produced at
the call site, never the declared parameter type:

```yaml
type_carriers: [org.springframework.core.ParameterizedTypeReference]

call_wrappers:
  - { type: org.springframework.http.HttpEntity, payload_ctor_arg: 0 }
```

**`type_carriers` names a supertype whose own generic argument is the payload** — a
different shape from §2a's `wrappers`, which name an envelope a payload sits *inside*.
`new ParameterizedTypeReference<List<OrderView>>() {}` is an anonymous subclass, and the
generic supertype reference [D00](D00-fact-schema.md) §5a's class symbol fact carries is
exactly what names `List<OrderView>` back out. When a response or request `instance`
argument's type subtypes a declared `type_carrier`, the engine resolves the payload through
that supertype reference instead of through the declared parameter type — the same
array-of-shape descriptor already built for a directly-typed response, reached one hop
later. "PTR" is named here, in the catalog, and never in the engine.

**`call_wrappers` names a constructor argument that holds the real payload.**
`new HttpEntity<>(orderRequest)` is itself a `call_site` fact — a constructor invoke — and
the outer call's `instance` argument that names `HttpEntity` carries a `source` id pointing
at that constructor's `receiver` ([D00](D00-fact-schema.md) §5) — the constructed value's
own id, shared by both facts. Not its `result`: `<init>` returns void, so a constructor
call site's `result` is `null` by construction and could never carry the join.
`payload_ctor_arg: 0` tells the engine which of the constructor's own `arguments` is the
payload; the engine follows exactly that one hop and stops. Beyond one hop, or where no
`call_wrappers` entry matches
the `instance` type, the body stays `unresolved` — an envelope Sextant does not know is not
one worth guessing through.

---

## 2i. The configuration model

Which files matter, in what order, and what a placeholder means is framework knowledge
too — Spring's own layering of `application.yml` over `bootstrap.yml`, its own profile
spellings, its own `${key:default}` grammar — so it is catalog data, read by
[M04](M04-resolver.md)'s pass 2 ([D01](D01-graph-schema.md)) rather than assumed by the
engine. **The model is a new top-level, optional catalog block, one per framework family.**
Spring's ships in 2F:

```yaml
config_model:
  sources:                      # precedence order, lowest first
    - { pattern: "bootstrap{-profile}.properties" }
    - { pattern: "bootstrap{-profile}.yml" }
    - { pattern: "application{-profile}.properties" }
    - { pattern: "application{-profile}.yml" }
  profiles:
    from_filename: "{-profile}"
    from_document_key: spring.config.activate.on-profile
    default_profile: default
  placeholders: { open: "${", close: "}", default_separator: ":" }
  key_matching: relaxed          # relaxed | exact
```

**`sources` is precedence order, lowest first** — a later source in the list, and a
profile variant of any source, both win over what came before. Each entry's `pattern` is
matched against files under the module's resource roots; a module missing a listed source
simply contributes nothing from it. WITHIN one source, precedence is three tiers, lowest
first — an unlocked base document, a document of that same base file activated by
`from_document_key`, then a separate profile-variant FILE named by the filename marker —
so an inline activated document never outranks a same-profile variant file, Spring's own
real resource order.

**Profile spelling is a closed three-mechanism vocabulary** — `from_filename`,
`from_document_key`, and `from_key_prefix` (reserved for Quarkus's `%dev.` prefix style,
documented now, unimplemented until a Quarkus catalog exists). **The filename marker
generalizes: a `{profile}` (or `{-profile}`) placeholder may sit ANYWHERE in a source
pattern** — `application{-profile}.yml` for Spring, `{profile}.json` for a node-config
layout whose whole filename is the profile — with the empty match naming the base file.
No regex-in-YAML anywhere; the placeholder grammar is delimiters plus a default separator,
which covers every surveyed ecosystem.

**`placeholders` declares the open/close delimiters and the default-value separator** a
`${key:default}` expression resolves through — nothing more. No ecosystem-specific
escaping rules live here; a delimiter pair and one separator character are what every
surveyed placeholder grammar reduces to.

**`key_matching` is a closed two-value set governing how a `config_entry`'s normalized
`key_path` ([D00](D00-fact-schema.md) §5c) is compared against a catalog-declared key
template.** `relaxed` tolerates Spring's own RELAXED binding — kebab-case, camelCase and
`ENV_VAR` style all matching one canonical key; `exact` requires a literal match. A
catalog declares which its framework uses; the pass never guesses. It governs LOOKUPS
only — a `${...}` reference, and later a catalog's own key-template join — never the
layering merge itself, which always keys on a `config_entry`'s own exact `key_path`:
relaxed binding is Spring's own binding-time concept, not a file-reading one, so two
different spellings in config files stay two different keys at merge time regardless.

**`remote_prefixes` is an optional list of literal string prefixes** naming a
config-server or `spring.config.import`-shaped value — Spring's own model declares
`["configserver:", "optional:configserver:"]`. The pass checks a key's WINNING raw
value (before any placeholder substitution — an import URL is a literal, never itself a
`${...}` reference) against this list; a match resolves [D01](D01-graph-schema.md)'s
`remote_source` reason rather than a value the pass could never truthfully read from
files alone. A model declaring no `remote_prefixes` simply never emits the reason.

---

## 2j. Field sources — the imperative address ladder

An address is as often fed to a client imperatively — a field, a constructor parameter, a
bound properties object — as written at the call site. Which annotations carry
configuration onto those is framework knowledge, so it is catalog data too: an OPTIONAL
`matches`-level block on any client catalog, read by the shared argument ladder that
`single_call` and `fluent` both use (2F design §4).

```yaml
matches:
  field_sources:
    value_annotation: org.springframework.beans.factory.annotation.Value
    properties_annotation: org.springframework.boot.context.properties.ConfigurationProperties
    prefix_from: prefix
    getter_prefixes: [get, is]
```

**A catalog declaring no `field_sources` never consults the ladder at all** — its rows are
exactly what they were without it. Where one does, an address argument the scanner read as
a `field` ([D00](D00-fact-schema.md) §5) climbs four rungs, in order:

1. the field's own `value_annotation` expression, returned verbatim;
2. the constructor parameter the field was assigned from
   ([D00](D00-fact-schema.md) §5's `field_write`) and ITS own `value_annotation`
   expression — a parameter's annotations live only inside the constructor's signature,
   never as an annotation fact of their own;
   - **2a. the enclosing declaration's OWN parameter**, where the address argument IS that
     parameter passed straight through ([D00](D00-fact-schema.md) §5's `parameter` kind):
     rung 2's terminal read, reached without the field. An injected value assigned to a
     field and an injected value handed straight to a configuring call are the same
     declaration, and only the second carries no `field_write` to follow. Bare parameter
     references only — a value merged from a parameter and anything else reads
     `unresolved`, which is the honest answer and not a case to widen;
3. a `properties_annotation` prefix (read from the annotation argument `prefix_from`
   names) plus the relaxed-bound property name — §2i's own `key_matching` rule, reused
   rather than re-implemented. The property is read either from a properties FIELD the
   argument reads directly, or — the realistic idiom — from a zero-argument accessor
   whose result the address argument is, followed exactly one hop through
   [D00](D00-fact-schema.md) §5's `arguments[].source` within the same caller. An
   accessor name is de-prefixed by `getter_prefixes` (declared, so no language's own
   accessor spelling enters the engine) and then relaxed-bound against the type's own
   declared field names, so the expression carries the spelling the configuration key is
   written in;
4. nothing matches — the argument stays exactly what it was, and the row is the same
   honest `unresolved` it was before.

**Every rung yields an EXPRESSION, never a value** — rungs 1 and 2 return the one the
facts already carry, rung 3 synthesises `${prefix.name}` — so the engine reads the
argument as that expression exactly as if it had been a literal at the call site, and
everything downstream (CP-2's split, composition with a `base`, dedup) behaves identically
for both. Values stay in `resolved_config`, and the per-environment answer stays a join
([D01](D01-graph-schema.md)). A base built by computation — a concatenation, a setter, a
method's return value — reaches no rung and is a named gap, not a guess.

---

## 3. Ordering

Engines run in a fixed order because later passes depend on earlier ones: inbound first,
then outbound, then the styles that ENRICH what those produced — `config_join` and
`schema_operations`. **Inbound no longer precedes outbound to make them merge** (F5 §6.1,
W27): a path a module both exposes and calls now keeps two rows, and
`resolve/self_exchange.py` files a `self_exchange` question naming each side and its
address. Merging asserted that the thing called IS the thing served, which is a claim about
the far end of a call; it keyed on `(protocol, method, path)` and `peer` is not part of
endpoint identity (RC-5), so the fixture's call to `${soap.billing.uri}` was published as
the module's own served operation. The order between the two directions is now merely the
order they were written. The enriching styles still come after both, whatever direction
their own catalog file declares, because a stamp cannot reach a row that does not exist
yet.

`schema_operations` is in that group for the same reason twice over: it stamps a declared
response shape onto rows other engines minted, and its OWN rows meet §5's insert-if-absent
guard last on purpose — a schema states an operation, an annotation states the operation
AND the code serving it, so running afterwards is the whole of what makes the annotation
row the one that survives. First-writer agreement by ordering, with no second rule to keep
in step. **Within the runs-last group the same reason applies one level down**: a style
whose catalogs may either DERIVE rows or only stamp them runs every deriving catalog
first, or a stamp arrives before the rows it was meant to enrich. Direction and filename
remain the tiebreaks after both ranks.

`derived_resource` joins that group for a reason of its own (Phase 2O Task 6): its rows
are PREDICTIONS from a framework rule rather than readings of a declaration, so where a
real controller serves the same URL the observed row is the one that must survive — and
insert-if-absent only means that once every observing style has written. (2O design §2b
also said "and before `config_join`". That half is not implementable and is not
load-bearing: within this group the ranks above decide, there is no per-style rank, and
the two mint disjoint identities — HTTP routes versus messaging destinations.)

**`protocol_hint` is no longer in this list** (Phase 2H). It ships as a resolve pass
rather than an engine, and its position is stated where it runs: after the engines' merge
and before the format ladder (§2's `protocol_hint`).

**The order is a property of the engine style, not of the catalog file.** A catalog cannot
request a position.

---

## 4. Every catalog ships a conformance fixture

A catalog is not accepted without a tiny repository that uses the framework, and the exact
endpoint list expected from it. The fixture runs in CI.

Without this, a catalog is an assertion. With it, a catalog is tested — and adding a
framework stays *one YAML file and one fixture, with no engine change and no existing test
modified*.

**One narrow exception, and it is stated rather than taken quietly (Phase 2H).** A catalog
whose only surface is a **programmatic registration call** may ship fixture-less, on three
conditions together: the rows are pinned over synthetic `call_site` facts against the
**real loaded catalog** (never an invented one, so the shipped file's own arities and
argument positions are what the test exercises), every assumption the fixture would have
settled is written down as a limitation, and the boundary is recorded in
[COVERAGE](../COVERAGE.md) rather than left to the catalog file. The reason is that such a
fixture is not small: registering a handler programmatically means a configuration class,
a framework's own registry interface on the compile classpath and a callback body, all to
pin one literal argument.

`spring-websocket.yml` (`WebSocketHandlerRegistry.addHandler`) is the first instance, and
it carries the cost the exception implies: its `arity: 2` assumes a single-path call
compiles to exactly two call-site arguments, which no bytecode has confirmed, and a
multi-path call matches no row at all. A catalog under this exception is weaker evidence
than one with a fixture, and the sentence above — "without this, a catalog is an
assertion" — is exactly what it trades
against, so the exception is for this one shape and does not generalise to an
annotation or configuration catalog **on the strength of the shape alone**, where the fixture
is usually cheap.

**Phase 2I is worth recording before the second instance, because it narrowed the exception
rather than widening it.** `jakarta-jws-client.yml` — generated client stubs, whose
declarations live in a dependency by definition — was pinned over synthetic facts for exactly
one task, and then got a real fixture of a shape this document had not had before: a **sibling
module built and consumed as a jar**, opted into by the analysed fixture's own `.sextant.yml`
(§4a), deriving its one endpoint through the real commands in CI. A catalog whose subject
matter is compiled libraries is fixturable after all; it just needs a library.

**The second instance: `jakarta-servlet.yml` and `javax-servlet.yml` (Phase 2O Task 7b).**
They are ANNOTATION catalogs, which the paragraph above says the exception does not cover on
the strength of the shape — so they take it on a different ground, stated here rather than
assumed. **The reason is a dependency, not a shape.** A servlet fixture compiles against a
servlet API, which puts `jakarta.servlet:jakarta.servlet-api` (and, for the second catalog,
`javax.servlet:javax.servlet-api`) into CI's offline priming — a dependency change §7 puts out
of an implementation task's scope without instruction. The fixture is cheap to WRITE and not
cheap to LAND, which is a different sentence from the one 2H was written against.

**What ships instead**, satisfying the exception's three conditions with unusually strong
compensating evidence: the rows are pinned over synthetic facts against the **real loaded
catalogs** (`tests/application/test_supertype_dispatch.py` loads the shipped files, never a
copy); every assumption is written down; the boundary is recorded in
[COVERAGE](../COVERAGE.md). And the fact shapes those synthetic facts mirror were not
imagined — CP-9 ran the committed extractor over real compiled servlet class files on three
containers and recorded what reached the fact stream (`scripts/probes/cp9_servlet_shapes.md`,
rows 20-30). What is still missing is narrow and real: nothing runs the DERIVATION end to end
over that bytecode in CI, so a change in the fact stream's shape is caught by re-running the
probe rather than by the suite.

**The condition that closes it** (§9: an omission states what would make it wrong): a servlet
API present in CI's offline priming. The day one is primed — for this or any other reason —
the ground above evaporates, and these two catalogs get the fixture D02 §4 requires of every
other annotation catalog. **Two instances is the count, and it is not a trend**: each was
admitted for a reason of its own, written down where the catalog is, and a third needs its own
ruling rather than a citation of these.

---

## 4a. Catalog rules over an extracted library

Every style above reads facts, and since Phase 2I some of those facts can come from a
**dependency's own bytecode** rather than from the module's output — the libraries a module
names in `.sextant.yml` ([D04](D04-config-and-exclusion.md) §2a). No style changed to allow
it and none is opted out of it, so what each one then claims has to be stated:

- **A call-driven style derives only where the module's own call sites reach the library's
  types.** `single_call`, `fluent`, `combinator` and `interface_implementation` all root in
  a call this module makes, so opting a library in cannot fabricate call-evidenced rows; at
  most it adds the declarations those calls resolve against.
- **An annotation-driven OUTBOUND catalog derives from the interface alone**, which is the
  mechanism's purpose: a generated client stub is annotated exactly as it would be inside
  the module, and a row derived from it says the module calls that operation because the
  module compiled against the stub.
- **An annotation-driven INBOUND catalog derives from annotations alone too, and that is
  the claim the opt-in has to carry.** A jar holding `@RestController` or `@Endpoint`
  classes derives inbound rows whether or not component scanning ever reaches them, and
  Sextant cannot see component scanning. So **naming a library asserts it is part of this
  module's runtime surface** — the reader's own claim, made once, per library, never
  inferred from the dependency tree. Every such derivation carries its origin coordinate
  into the facts ([D00](D00-fact-schema.md) §2), the rendered document
  ([D06](D06-bundle-format.md) §5b) and the exported `documents` table, so the assertion
  stays visible instead of being laundered into module-observed evidence.

**The assertion is retractable, which is what makes it a decision rather than a
commitment.** Removing a coordinate from `.sextant.yml` removes its rows on the next run:
the library fact subtree is discarded whole before anything is written, because a fact file
is written whole and a library that is no longer scanned would otherwise overwrite nothing
and be read straight back out of the same workspace.

---

## 5. What a catalog must not contain

- **No code.** If a framework cannot be expressed in a style, that is an argument for a new
  engine, not for an escape hatch.
- **No language names.** Catalogs match on symbols. This is why one Spring catalog serves
  both Java and Kotlin.
- **No ordering requests.**
- **No conditional logic across catalogs.** Two catalogs may both match; both produce
  endpoints, and duplicates on one identity IN ONE DIRECTION dedup. The two directions are
  never folded together (F5 §6.1).

---

## 6. Where catalogs live

Built-in catalogs ship with Sextant. ~~A repository adds its own — for an in-house client
library — through `sextant.yml` ([D04](D04-config-and-exclusion.md)). Both sets are loaded
together and neither is privileged.~~

> **Amendment (2026-09-05, principles sweep `A-C9`).** **There is no mechanism by which a
> repository catalog could load.** `YamlCatalogSource` globs the installed package's own
> directory and nothing else, and the `sextant.yml` D04 §2 specifies is never opened — see
> that section's own amendment. The sentence above is struck rather than deleted because
> NFR-9 names this as the supported extension path and a reader needs to know it is not one;
> project catalogs are deliberately unscheduled (2O roadmap `:201-205`), because they would
> make this schema a public API after which every change here is breaking. Recorded in
> [documented-not-implemented.md](../documented-not-implemented.md).

**Shape models (§1b) live in a `shape-models/` subdirectory of the same set.** They are
resolved within the set that declares them, so a catalog naming a model its own directory
does not hold fails at load naming both the file and the model. That the built-in set is
the only set today is the amendment above, not a property of the reference.

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
| A `meta_annotations` capability reading an UNSCANNED jar's own class files, so framework-internal composition (`@GetMapping` = `@RequestMapping`) stops being hand-copied catalog data too — the module-local half (a project's own composed annotations) shipped in Phase 2E and is no longer open | §2 `annotation_driven`'s hand-copied mapping table |
| Whether a scope rule (`@NullMarked`) may be declared on a package as well as a class, and how it interacts with `@NullUnmarked` | §2e |
| Whether the manifest reader pins framework versions, given the files are undocumented internals that may shift | §2's `filesystem` style |
| Whether a globally configured naming strategy is read from configuration, or only declared per catalog | §2f, and any module that sets one in `application.yml` |
| **How much expressiveness `address_from_config` needs before it stops being data.** Partly settled: the suffix table, its parallel `direction`/`payload_arg` lists, the two separators and the binder→protocol map all ship as data (§2's `config_join`). Still open — a binding INDEX beyond `-in-0`/`-out-0` for a multi-input function, and whether a composed `a\|b` entry should ever be decomposed rather than degraded | §2d, and the Spring Cloud Stream catalog |
| Precedence between a `known_types` entry's own `nullable` and an enclosing `not_null_by_default` scope — unspecified; as implemented the scope wins. Unreachable with shipped catalogs. | §2e, §2g |
