# Phase 2I — SOAP: JAX-WS, Spring-WS, WSDL, and opt-in library extraction

**Status:** approved in brainstorm 2026-09-01; this document records the design.
**Depends on:** 2H (schema_operations + role, path_fallback/qualifier vocabulary,
reader→interpreter chain, format_fixed), 2F (field ladder, config resolution),
2B (annotation-driven outbound), DR-6 (predicted behaviour mirrors the framework).
**Roadmap row:** JAX-WS + Spring-WS catalogs; WSDL as a declared-shape source —
"catalog work only, by then" (an honesty edit lands with this phase: the WSDL/XSD
reader and interpreter branch are real code; roughly two-thirds of the phase is data).

## The thesis

SOAP is the last committed protocol for Spring module-level coverage — closing it hits
**milestone 1**. Its boundary is not an HTTP route (one POST path, N operations — the
2H problem), its identity is the **input element's QName**, and it is the most
contract-first protocol in the estate: the WSDL is the actual contract, so schema-first
derivation matters more here than anywhere. Everything rides 2H's machinery; the one
genuinely new subsystem is the user-ruled **opt-in library extraction** (§5), which
exists because SOAP's most common outbound form — generated client stubs — often lives
in a dependency jar Sextant cannot see today.

User rulings that shaped scope: everything in — the two inbound catalogs plus
`@SoapAction`, WSDL/XSD declared shapes + schema-first operations, `WebServiceTemplate`
outbound, JAX-WS generated-stub outbound, the opt-in `.sextant.yml` library-extraction
mechanism, and a live pin that a config-fed `defaultUri` resolves through 2F's field
ladder. Agreed boundaries: document/literal (wrapped included) only — `rpc/encoded` is
a stated boundary (WS-I-banned since 2004), never implemented; the wrapper element is
the wire-true request shape (DR-6: we present the wire, not the programming model);
`@SoapAction` rows may be link-orphans (different identity axis, honest); WS-Security/
WS-Addressing, MTOM, `Dispatch` dynamic clients, SOAP 1.1-vs-1.2 distinction, and
auto-scanning the dependency tree are all out.

## 1. Wire identity

`protocol: soap`, verbless (`method` NULL — the 2D precedent). The path column carries:

- **QName rows** (JAX-WS, `@PayloadRoot`, WSDL operations): W3C QName notation —
  `{http://ns/}operationName`. The notation is an XML standard
  (`javax.xml.namespace.QName.toString`), framework-neutral, and is exactly what
  Spring-WS dispatches on, so annotation-derived and WSDL-derived rows meet on it.
- **Action rows** (`@SoapAction`): the action URI verbatim. A different identity axis
  on the same protocol — D01 permits both ("the operation name"); these rows link only
  when a client states the same action, which code rarely does. Stated boundary.

`format_fixed: xml` on every soap catalog — rung 1's second live surface.

## 2. Inbound catalogs

**`spring-ws.yml`** (`annotation_driven`): `@Endpoint` class gate;
`@PayloadRoot(namespace, localPart)` → `(soap, NULL, {namespace}localPart)`, request
shape from the payload parameter; `@SoapAction(value)` → the action URI. Evidence per
the existing annotation ladder.

**`jakarta-jws.yml`** (`annotation_driven`): `@WebService` class gate — BOTH
`jakarta.jws` and `javax.jws` spellings wired (this catalog needs no single-valued
prefix machinery, so both CAN be, unlike 2H's websocket case). `@WebMethod` methods;
`@WebMethod(exclude = true)` derives nothing. **DR-6 application:** a public method
without `@WebMethod` in a `@WebService` class IS exposed by JAX-WS's own rules, so the
class gate derives every public method, `operationName` falling back to the method
name via 2H's `path_fallback: construct_name`.

Two vocabulary additions, both closed words, both refused-when-meaningless per the 2H
validation pattern, no SOAP word in engine code:

1. **`qualifier_format: qname`** — joins two attributes as `{a}b`. 2H's
   `qualifier_separator` is deliberately single-character; QName needs bracketing, and
   widening the separator would re-admit arbitrary glue. One closed format word
   instead, alongside (mutually exclusive with) the separator form.
2. **`namespace_default: reversed_package`** — JAX-WS's spec-defined default
   `targetNamespace` (package `com.acme.orders` → `http://orders.acme.com/`). DR-6
   commands predicting the framework, and this default is deterministic; the
   checkpoint verifies the exact algorithm (trailing slash, segment order) against
   real JAX-WS behaviour before the catalog ships it — if the probe shows ambiguity,
   the honest answer is `unresolved`, never a guessed namespace.

## 3. WSDL/XSD — the 2H pattern on stdlib XML

- **Reader** (`ingress/read/wsdl_xsd.py`): claims `wsdl`/`xsd` extensions, emits
  verbatim, never parses. Schema roots: `src/main/resources/wsdl`,
  `src/main/resources/xsd`, `META-INF/wsdl` (the JAX-WS packaging convention) —
  conventional dirs only, boundary stated.
- **Interpreter branch** (`descriptors.py`, `schema_format: "wsdl"` covering both
  extensions — a WSDL embeds XSD in `<types>`; a standalone XSD joins the same type
  universe): **stdlib `ElementTree`, zero new dependencies.** One universe per module;
  `xsd:import`/`xsd:include` and WSDL→XSD references resolve within the module's
  files under 2H's merge rules verbatim — missing import fails that file, duplicate
  type names fail those files, partial reads discarded, failures are gaps never
  crashes. Projection: `xsd:element`/`complexType` → declared shapes; element names
  as `wire_name` verbatim; `minOccurs="0"` → not required; `nillable="true"` →
  nullable; `maxOccurs="unbounded"` → array with item; enumeration facets → enum
  symbols; `schema_name` = the QName. Substitution groups, `xsd:any`, and `choice`
  groups are that file's gap — never a guess.
- **Permitted refactor:** this is `descriptors.py`'s fourth format branch. If the
  module nears ~1300 lines, splitting into per-format modules behind the same
  confinement test (allowlist adjusted to the new file set) is sanctioned here.
- **Schema-first operations:** in document/literal-wrapped, an operation's identity IS
  its input element's QName — the thing `@PayloadRoot` matches. The interpreter marks
  each WSDL operation's input element via 2H's role machinery, widened by one neutral
  word: `role` gains `"operation"`, and `schema_operations` maps it to
  `(soap, NULL, {ns}element)` at `declared`, NULL handler (rendered "none recorded").
  **The derivation shape differs from 2H's and the engine must say so** (self-review
  correction): graphql roles derive one endpoint per *field of* the role-carrying
  type; `operation` derives one endpoint from **the shape itself** — the input
  element IS the operation, its `schema_name` QName IS the path, and its fields are
  the request shape, not further endpoints. This per-shape mapping plus the
  role→method addition is this phase's one sanctioned engine-code touch.
  The style block ships on a new **`wsdl-schema.yml`** (one file = one style — the
  registry constraint `graphql-schema.yml` already proved). Agreement with annotation
  rows rides the existing first-writer guard + response-shape coalesce unchanged.

## 4. Outbound

**`WebServiceTemplate`** (`single_call` rows on `spring-ws.yml`): URI-carrying
overloads (`marshalSendAndReceive(uri, payload)`) derive the address from the
literal or config-fed argument; no-URI overloads fall back to `defaultUri` —
constructor/setter-fed, resolved through the existing **`field_sources` vocabulary**
declared on `spring-ws.yml` (the mechanism `spring-resttemplate.yml` already uses:
the call's receiver is the template field, and 2F's ladder walks its constructor/
`@Value`/config feed — named here so the mechanism is concrete, not implied;
self-review correction), **pinned live** (a fixture template fed
`${soap.billing.uri}` through configuration). The operation identity
lives in the payload argument's JAXB annotations (`@XmlRootElement(name, namespace)`),
not in the call: the **checkpoint probes whether the argument's type is recoverable
from existing `call_site` facts**. If yes, one targeted vocabulary form — identity
from the argument type's catalog-named annotation — lights real `{ns}op` identities;
if not, those rows ship with address and peer resolved and the operation honestly
`unresolved`, boundary stated. No guessing either way.

**Generated stubs** (outbound `annotation_driven` — the 2B Feign pattern verbatim): a
`wsimport` interface carries `@WebService(targetNamespace)` + `@WebMethod`; outbound
rows derive from the interface annotations exactly as Feign's did, identity
`{ns}operationName` (defaults per §2's two vocabulary words) — whether the stubs sit
in the module or in an opted-in jar (§5).

## 5. Opt-in library extraction (`.sextant.yml`)

The first analysis-configuration surface living in the analyzed repository:

```yaml
# .sextant.yml at the analyzed repo's root
extract_libraries:
  - com.acme:orders-soap-client
```

- The detector reads it at detect time (repo content — ingress reads repos), maps each
  coordinate to its resolved jar through the recorded classpath (the `ClasspathEntry`
  facts that already exist), and contributes the jars as **library roots**. An
  unresolvable coordinate records the `libraries_not_resolved` gap with the
  coordinate — never a crash. Coordinates are `group:artifact` today; other build
  ecosystems add their own coordinate forms to the same key later.
- The scan loop runs the extractor over each library root beside the module's own
  classes. **Checkpoint item: verify the extractor accepts a jar input** (it scans
  class directories today); if falsified, a small extractor addition (zip-walking) is
  sanctioned — the one place this phase may touch the extractor, version bumped per
  its own convention.
- Every fact from a library carries its **origin**: `Document` gains an optional
  `origin` field (the library coordinate; D00 addition, neutral wording — any
  ecosystem's coordinate fits a string). Library fact files land under their own
  subtree, `facts/lib/<coordinate>/…` — the 2F/2G collision rule extended, so a
  library class path can never collide with a module class.
- Honesty structure, stated precisely (self-review correction): call-driven styles
  derive only where the module's own call sites reach the library's types, so opting
  in cannot fabricate call-evidenced endpoints; annotation-driven outbound (Feign-
  style, §4's stubs) derives from the interface alone — identical to in-module stubs,
  which is the mechanism's purpose. But annotation-driven **inbound** from a library
  class (a jar carrying `@RestController`/`@Endpoint` classes) derives from
  annotations alone, and whether those surfaces are active depends on component
  scanning Sextant cannot see. The rule: **opting a library in asserts it is part of
  the module's runtime surface** — the user's own claim, made once, per library.
  Every derivation carries the origin coordinate, and the rendered document marks
  library-contributed rows, so the assertion is always visible, never laundered into
  module-observed evidence. The dependency tree is never auto-scanned: opt-in,
  per-library, stated.

## 6. Fixtures and checkpoint

Fixture surfaces in `orders-service` (deps: `jakarta.jws-api` + `javax.jws` API jar,
`spring-ws-core` — compile-scope, pinned): a `@Endpoint` class with `@PayloadRoot`
(explicit QName) and `@SoapAction` methods; a `@WebService` class with an explicit
`@WebMethod(operationName=...)`, a bare public method (JAX-WS-exposed, method-name +
reversed-package defaults), and a `@WebMethod(exclude=true)` method; a WSDL + separate
XSD pair under `src/main/resources/wsdl` declaring types with `minOccurs`/`nillable`/
`unbounded`/enumeration variety and **one operation no annotation implements** (the
schema-first pin, the `auditTrail` analog); a `WebServiceTemplate` bean with
config-fed `defaultUri` (`${soap.billing.uri}` in application.yml) and one
URI-literal call; a **stub-jar fixture**: a small reactor sibling module
(`orders-soap-client`) whose jar carries `wsimport`-shaped stub interfaces, opted in
via `fixtures/orders-service/.sextant.yml` — exercising §5 end-to-end (the reactor
layout also exercises the parent-pom inheritance fix live).

Checkpoint items (freeze before dependent tasks): (1) extractor jar-input capability;
(2) the reversed-package algorithm against real JAX-WS output; (3) whether a call
argument's type is recoverable from `call_site` facts (gates §4's identity
vocabulary); (4) `@WebService`/`@WebMethod` defaulted-attribute reality in bytecode
(the 2H probe replayed); (5) how `@XmlRootElement` reads on fixture JAXB classes.
Exact-list pins from live runs only; double-run byte-identity over every touched
table; suite baseline 826 passed/1 skipped.

## 7. Docs

D00 (`Document.origin`, `role` gains `operation`, `schema_format` gains `wsdl`); D01
(QName + action-URI identity forms); D02 (`qualifier_format`, `namespace_default`,
the soap catalogs, `wsdl-schema.yml`'s style block, the §5 mechanism); D06 (rendered
`soap {ns}op` identities — verbless, the messaging precedent; origin-carrying facts'
rendering note); COVERAGE §5.3 flips + boundaries; README (`.sextant.yml` section);
roadmap (2I → delivered, the "catalog work only" honesty edit, milestone 1 declared —
modulo the named A-tier rows and ledgered extractor candidates).

## 8. Boundaries, stated

`rpc/encoded` unimplemented (WS-I-banned; wrapper-element shapes are wire-true for
document/literal only); `@SoapAction` rows link-orphan-prone; WS-Security/
WS-Addressing/MTOM semantics unread; `Dispatch` dynamic clients out
(`runtime_dynamic` class); SOAP 1.1 vs 1.2 not distinguished (both `soap` + `xml`);
dependency tree never auto-scanned; stubs in un-opted jars invisible; WSDL served
from a runtime URL (not a repo file) unread — the registry-at-runtime class 2G
recorded for Confluent subjects.
