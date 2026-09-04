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
| `protocol`, `direction`, `format` | From [D00](D00-fact-schema.md)'s closed sets. **Defaults** — a match may resolve them differently, see §2c |
| `detect` | Coordinates that make this catalog active for a module |
| `requires` | Capabilities — scanner-declared or pipeline-declared (below). **If unmet, the catalog does not run and the skip is reported.** |
| `matches` | Style-specific |

**Every type name a catalog writes — `owner`, `fqn`, `type` — is dotted**
(`reactor.core.publisher.Mono`), never the SCIP symbol form the fact stream uses
(`reactor/core/publisher/Mono#`). The dotted notation is sugar for the JVM symbol scheme
specifically: the conversion (`domain/symbols.type_descriptor`) becomes scheme-aware when
the first non-JVM catalog arrives, so this notation is documented as JVM sugar now rather
than ossifying as a universal one.

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

## 2. The eleven styles

A style is a shape of evidence, not a framework. New frameworks reuse a style; only a
genuinely new shape needs a new engine. (Nine as of Phase 2H; `supertype_derived` and
`injected_client`, Phase 2O Task 5, are the tenth and eleventh.)

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
  here and an unrecognised one is refused. It exists because **an annotation's declared
  default is not written into the class file**: Spring GraphQL, DGS and MicroProfile all
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
  never the withdrawing value**: a declared default is not written into the class file, so
  the attribute reads NULL wherever it was left alone, and only a value actually written
  out withdraws anything. The comparison happens on the text `json ->>` reads every scalar
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

**Three catalogs, one engine change.** The forms are stated in framework-neutral words for
a reason that was tested rather than asserted: `spring-graphql.yml` introduced them, and
`netflix-dgs.yml` and `microprofile-graphql.yml` then rode them with **zero further engine
change** — DGS spells the scope `parentType` where Spring spells it `typeName`, and
MicroProfile has no scope at all, and all three differences are one line of YAML each.
That is §4's acceptance test run early, on one protocol, which is why the vocabulary grew
here instead of three framework special cases growing in the engine.

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

Each `methods` row is `{name, arity?, http_method | method_arg | neither, url_arg |
channel_arg, body_arg?, response_arg?, record_arg?, direction?, path_from_argument_type?}`,
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
  terminal: [retrieve, exchange]
```

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

**This style needs no execute-terminal.** `fluent`'s `terminal`/`terminal_via_argument`
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
**`binding.from` is `bean_name`** — the only source implemented, and anything else is
refused rather than read as this one.

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
  or declared but resolvable in no environment — takes the framework default and binds
  every candidate; a key that RESOLVED, to an empty value or to separators alone, is a
  select-nothing statement and derives no row. Collapsing the two would bind every bean in
  the module against a configuration that said the opposite: the one place this style
  could fabricate a boundary rather than degrade.

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
override name among what bytecode itself declared — a candidate that matches nothing
derives nothing.

**Where the constants cannot be read at all — CP-8(b)/(d) falsifying, not the supertype
being absent — the row still derives** ([D02](D02-catalog-schema.md) §2's unresolved-is-an-
answer): `path` the supertype's own bare descriptor verbatim, `resolution: unresolved`,
`handler` NULL, plus one `service_identity` open question naming the implementer class and
the reason. A supertype whose own facts never reached this workspace at all (a published
`*-grpc-stubs` jar, consumed without the library opt-in) derives NOTHING — not even the
unresolved fallback, which is reserved for a LOCALLY SEEN supertype.

`direction`/`protocol` are the catalog's own; `method` is always NULL (gRPC is verbless,
like every non-HTTP protocol); `caller`/`peer` are always NULL (the deriving method is a
`handler`); `request_shape`/`response_shape` stay NULL — this style contributes the handler
symbol only, and where a `.proto` descriptor also covers the same identity
(`schema_operations`, above), the two rows merge on the identical `(protocol, direction,
method, path)` D02 §5 already dedups on, the descriptor contributing the method inventory
and payload shapes it alone can read.

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

### `protocol_hint`

**Reclassifies endpoints other engines already produced** — a streaming response, a
long-poll. It changes protocol, never direction, and it never creates an endpoint.

**Execution amendment (Phase 2H): it is not an engine in the §3 runs-last group, and it
does not "run last with `config_join`".** That sentence predates resolve passes. It ships
as a post-merge resolve pass (`resolve/protocol_hint.py`, the 2G `format.py` precedent),
and the pipeline order is: engines including their merge → `parse_binding` →
**`protocol_hint`** → the format ladder. Both sides of that position are the pass's own
contract. AFTER the merge, because every row must exist and a merged `both` row must
already BE one row, so it reclassifies wholesale — one identity in, one identity out.
BEFORE the ladder, because rung 1 reads `protocol` directly, so a row answered before it
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
`direction` — direction is resolved at match time (§2c) and the inbound/outbound merge has
already run, so a pass that moved direction afterwards would silently corrupt a `both` row
the merge had already built. (2) It never creates or deletes an endpoint; the row count is
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
  evidence it. On an inbound row it is what the route streams back; carried onto a merged
  `both` row from the outbound twin the merge deleted, it is what a caller expects to
  receive — evidence either way. `consumes`, on ANY row, means "this accepts event-stream
  REQUEST BODIES", and a channel is not named after what it eats. Reading `consumes` on a
  client-side row was tempting and is refused anyway: after the merge the column's
  PROVENANCE is gone (the merge coalesces, keeping the surviving inbound row's own value
  first), so a `both` row's `consumes` may be either half's and nothing on the row says
  which. One column, one meaning.
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
holds. A merged `both` row is covered by rules for **either** direction — it is one
identity the module both exposes and calls — and where the two halves' configured classes
mean different formats, that is a real disagreement about one wire, recorded as a
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
`schema_operations`. Inbound precedes outbound so that a path a module both
exposes and calls merges into one endpoint with direction `both` rather than appearing
twice. The enriching styles come after both, whatever direction their own catalog file
declares, because a stamp cannot reach a row that does not exist yet.

`schema_operations` is in that group for the same reason twice over: it stamps a declared
response shape onto rows other engines minted, and its OWN rows meet §5's insert-if-absent
guard last on purpose — a schema states an operation, an annotation states the operation
AND the code serving it, so running afterwards is the whole of what makes the annotation
row the one that survives. First-writer agreement by ordering, with no second rule to keep
in step. **Within the runs-last group the same reason applies one level down**: a style
whose catalogs may either DERIVE rows or only stamp them runs every deriving catalog
first, or a stamp arrives before the rows it was meant to enrich. Direction and filename
remain the tiebreaks after both ranks.

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
annotation or configuration catalog, where the fixture is cheap.

**It is still the only instance, and Phase 2I is the reason that is worth recording.**
`jakarta-jws-client.yml` — generated client stubs, whose declarations live in a dependency
by definition — was pinned over synthetic facts for exactly one task, and then got a real
fixture of a shape this document had not had before: a **sibling module built and consumed
as a jar**, opted into by the analysed fixture's own `.sextant.yml` (§4a), deriving its one
endpoint through the real commands in CI. A catalog whose subject matter is compiled
libraries is fixturable after all; it just needs a library.

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
| A `meta_annotations` capability reading an UNSCANNED jar's own class files, so framework-internal composition (`@GetMapping` = `@RequestMapping`) stops being hand-copied catalog data too — the module-local half (a project's own composed annotations) shipped in Phase 2E and is no longer open | §2 `annotation_driven`'s hand-copied mapping table |
| Whether a scope rule (`@NullMarked`) may be declared on a package as well as a class, and how it interacts with `@NullUnmarked` | §2e |
| Whether the manifest reader pins framework versions, given the files are undocumented internals that may shift | §2's `filesystem` style |
| Whether a globally configured naming strategy is read from configuration, or only declared per catalog | §2f, and any module that sets one in `application.yml` |
| **How much expressiveness `address_from_config` needs before it stops being data.** Partly settled: the suffix table, its parallel `direction`/`payload_arg` lists, the two separators and the binder→protocol map all ship as data (§2's `config_join`). Still open — a binding INDEX beyond `-in-0`/`-out-0` for a multi-input function, and whether a composed `a\|b` entry should ever be decomposed rather than degraded | §2d, and the Spring Cloud Stream catalog |
| Precedence between a `known_types` entry's own `nullable` and an enclosing `not_null_by_default` scope — unspecified; as implemented the scope wins. Unreachable with shipped catalogs. | §2e, §2g |
