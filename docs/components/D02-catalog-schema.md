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
| `protocol`, `direction` | From [D00](D00-fact-schema.md)'s closed sets |
| `detect` | Coordinates that make this catalog active for a module |
| `requires` | Scanner capabilities. **If unmet, the catalog does not run and the skip is reported.** |
| `matches` | Style-specific |

**`requires` is the mechanism that keeps degradation visible.** A catalog needing chain
reconstruction simply does not run against a scanner that lacks it, and
[M04](M04-resolver.md) reports which catalogs were skipped and why. Silently finding fewer
endpoints is the failure this prevents.

---

## 2. The five styles

A style is a shape of evidence, not a framework. New frameworks reuse a style; only a
genuinely new shape needs a new engine.

### `annotation_driven`

The declaration is an annotation and its arguments.

```yaml
style: annotation_driven
matches:
  type_annotation:   org.springframework.web.bind.annotation.RestController
  method_annotations:
    - { fqn: "…annotation.GetMapping",  http_method: GET,  path_arg: value }
    - { fqn: "…annotation.PostMapping", http_method: POST, path_arg: value }
  path_prefix_from: { annotation: "…annotation.RequestMapping", arg: value }
  request_body_annotation: "…annotation.RequestBody"
```

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
