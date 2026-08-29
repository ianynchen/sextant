# Phase 2 — Spring Boot completeness: roadmap

Six sub-phases, each its own plan. Phase 1 proved a vertical slice; Phase 2 makes one
framework genuinely covered before a second is attempted.

**Where we actually are.** Six of the seventy-two Java rows in
[COVERAGE.md](../../COVERAGE.md) §5 are shipped — about 8%. An endpoint carries request and
response contracts field by field, in both directions, with `required` and `nullable`
resolved; Feign, Retrofit and `@HttpExchange` outbound clients are read, linked to their
inbound peers, and exported as a D06 bundle.

## Why this order

[DR-5](../../ARCHITECTURE.md) links an outbound endpoint to an inbound one only when
**protocol, wire identity and payload compatibility** all agree, and says plainly what happens
without the third: *"In an estate where many services expose the same path shape, it invents
dependencies that do not exist... The failure mode is fabrication, not imprecision."*

We have protocol and wire identity. We have no payload compatibility. **So shapes come before
outbound**, or the first links Sextant draws are the ones the architecture was written to
prevent.

Nullability is not a refinement of shapes — it is what makes them comparable. DR-5's rule is
directional: *the client's request must satisfy every field the server requires*. A field set
without `required` cannot be compared in either direction, so it is in 2A, not after it.

| | Sub-phase | Status | Delivers | Depends on |
|---|---|---|---|---|
| **2A** | Shapes and nullability | delivered | Endpoints carry request and response contracts, field by field, with `required` and `nullable` | — |
| **2B** | Outbound annotation clients | delivered | Feign, `@HttpExchange`, Retrofit, and the D06 bundle exporter. **First linkable endpoints** | 2A |
| **2C** | Call-site clients | planned | `RestTemplate` first, then `WebClient`/`RestClient`, then **OkHttp** — pulled ahead of the messaging annotations below by user priority | `call_site` facts, `string_constants`, `chain_reconstruction` |
| **2D** | The rest of Spring Boot's annotations | planned | `@KafkaListener`, `@JmsListener`, `@SqsListener`, `@Scheduled`, `@MessageMapping`, `@QueryMapping` | Endpoint identity that is not HTTP-shaped |
| **2E** | WebFlux functional routing | planned | `RouterFunctions.route().GET(…)`, Kotlin `coRouter` | New `combinator` engine, `invokedynamic` |
| **2F** | Enrich | planned | `sextant module enrich` invokes an LLM to write the sections machines cannot derive, landing as overlay claims at `evidence: llm` — see the [design spec](../specs/2026-08-29-phase-2b-outbound-and-export-design.md) §6 | Redaction before the wire; a network + credential dependency |

## What each sub-phase is really blocked on

**2A** needed three extractor capabilities that did not exist. The scanner **never visited
fields** — `visitField` was not overridden, so there were no field symbols to build a shape
from. `visitTypeAnnotation` was not overridden either, so JSpecify's `TYPE_USE` nullability
was invisible. And Kotlin's nullability lives in `@Metadata`, not in annotations at all.

**2D** is blocked on something structural rather than large. The `endpoints` table has a
`method` column because it was built for HTTP; a Kafka topic has no method, and
[D01](../../components/D01-graph-schema.md) already says wire identity is *"the path template,
the topic expression, the fully-qualified remote method, or the operation name"*. The catalogs
are trivial; the identity is not.

**2C** is the largest single piece of in-house work in
[M03](../../components/M03-scanner.md). `call_site` is described in
[D00](../../components/D00-fact-schema.md) as *"the load-bearing one"*, and `chain_reconstruction`
is what [D02](../../components/D02-catalog-schema.md) says *"gates every builder-based client
library"* — which is exactly `WebClient`, `RestClient` and OkHttp.

## One spec gap found while scoping

[D01](../../components/D01-graph-schema.md) §5 states that **`shape_fields.wire_name` is the
identity, never the source field name** — *"after a naming strategy or an explicit
serialisation annotation, `customerId` and `customer_id` may be the same field."* But
[D02](../../components/D02-catalog-schema.md) has no vocabulary for declaring which annotation
supplies a wire name, or which naming strategy a module uses. Serialisation naming is
framework knowledge, so it belongs in a catalog, and 2A cannot produce a correct `wire_name`
without it. **2A amends D02 before it writes any code.**
