# Phase 2I — SOAP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SOAP operations become endpoints with QName wire identities — two inbound catalogs, WSDL/XSD declared shapes with schema-first operations, two outbound forms, and the opt-in `.sextant.yml` library-extraction mechanism — closing milestone 1 (Spring Boot module-level coverage complete).

**Architecture:** Everything rides 2H machinery: `path_fallback` + two new closed vocabulary words (`qualifier_format: qname`, `namespace_default: reversed_package`), the reader→interpreter chain (stdlib `ElementTree`, zero new deps), `schema_operations` widened with per-SHAPE `role: operation` derivation (the one engine touch), `field_sources` for `defaultUri`. The new subsystem is §5's opt-in extraction: `.sextant.yml` → library roots → origin-carrying facts under `facts/lib/<coordinate>/`.

**Tech Stack:** Python (stdlib XML — no new pip deps), YAML catalogs, DuckDB SQL, Maven fixture (new compile deps: `spring-ws-core`, `jakarta.jws-api`, `javax.jws` API jar; a reactor sibling stub-jar module).

**Spec:** docs/superpowers/specs/2026-09-01-phase-2i-soap-design.md

## Global Constraints

- **No version bumps** (SEXTANT_VERSION/FACT_SCHEMA_VERSION/GRAPH_SCHEMA_VERSION frozen); the extractor may change ONLY if checkpoint item 1 falsifies jar-input capability (then zip-walking + its own version bump per convention — the one sanctioned touch).
- **DR-6**: predicted behaviour mirrors the framework exactly — JAX-WS's bare-public-method exposure and reversed-package default are derived because the framework defines them; unknown behaviour yields `unresolved`, never a guess.
- **Wire identities** (spec §1): `(soap, NULL, {http://ns/}operationName)` W3C QName notation; `@SoapAction` rows carry the action URI; verbless (method NULL).
- **Determinism (NFR-1)**: double-run byte-identity over every touched table/export.
- **Unresolved is an answer, never an omission**; assumed never looks observed; framework names in catalogs only (`qname`/`reversed_package`/`operation` are neutral closed words).
- **Opt-in assertion rule** (spec §5): opting a library in asserts it is part of the module's runtime surface; every derivation carries the origin coordinate; rendered rows are marked; the dependency tree is never auto-scanned.
- **Wrapper element is the wire-true request shape** (document/literal; `rpc/encoded` is a stated boundary, never implemented).
- **Exact-list pins from live fixture runs only**; suite baseline 826 passed/1 skipped; hooks pass; uv.lock untracked; comments state constraints; no adjacent refactors.
- **Permitted refactor**: if `descriptors.py` nears ~1300 lines, split into per-format modules behind the same confinement test (allowlist adjusted).

## File Structure

| File | Responsibility |
|---|---|
| `fixtures/orders-service/` (pom + soap/ classes + wsdl/xsd resources) | T1 surfaces |
| `fixtures/orders-soap-client/` (reactor sibling) + `fixtures/orders-service/.sextant.yml` | T6 stub jar + opt-in |
| `src/sextant/application/resolve/engines/annotation_driven.py` + `derive_endpoints.sql` | `qualifier_format: qname`, `namespace_default: reversed_package` (T2) |
| `src/sextant/catalogs/{spring-ws,jakarta-jws}.yml` | inbound catalogs + `format_fixed: xml` (T2); outbound blocks (T5) |
| `src/sextant/ingress/read/wsdl_xsd.py`; `descriptors.py` wsdl branch | T3 |
| `src/sextant/domain/facts.py` (`role` gains `"operation"`, `Document.origin`), `closed_sets` if formats listed | T3/T4/T6 |
| `src/sextant/application/resolve/engines/schema_operations.py` + `src/sextant/catalogs/wsdl-schema.yml` | per-shape operation derivation (T4) |
| `src/sextant/ingress/detect/maven.py` + `application/ports/detector.py` + `stages/analyze.py` + `domain/factfile.py` | opt-in library roots, origin, `facts/lib/` (T6) |
| `src/sextant/egress/render/document.py` | library-row marking (T6) |
| docs (D00/D01/D02/D06/COVERAGE/README/roadmap) | T7 |

### Task order and why

Fixtures first (bytecode to probe); T2 is the CHECKPOINT (five reality gates) + inbound catalogs; reader/interpreter before schema-first ops (its input); outbound after the checkpoint's item-3 answer; opt-in last of the code tasks (its fixture needs the reactor layout); docs close milestone 1.

---

### Task 1: Fixture surfaces and dependencies

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/example/orders/soap/OrderSoapEndpoint.java`, `soap/BillingWebService.java`, `soap/BillingSoapClient.java`, `soap/payload/PlaceOrderRequest.java`, `src/main/resources/wsdl/orders.wsdl`, `src/main/resources/wsdl/orders-types.xsd`, config row in `src/main/resources/application.yml`

**Interfaces:**
- Produces: every 2I surface later tasks pin. Copy the classes verbatim; the real fixture DTO is `com.acme.orders.contracts.OrderView`.

- [ ] **Step 1: pom.xml** — compile-scope, version-pinned, verified resolving: `org.springframework.ws:spring-ws-core`, `jakarta.jws:jakarta.jws-api`, `javax.jws:javax.jws-api` (or the historical `jsr181-api` coordinate if that one resolves cleaner — pick whichever carries `javax.jws.WebService`, state the choice). NOT in extractor-jvm.
- [ ] **Step 2: Spring-WS endpoint**:

```java
package com.example.orders.soap;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;
import com.example.orders.soap.payload.PlaceOrderRequest;
import com.acme.orders.contracts.OrderView;

@Endpoint
public class OrderSoapEndpoint {

    @PayloadRoot(namespace = "http://orders.example.com/ws", localPart = "placeOrderRequest")
    @ResponsePayload
    public OrderView placeOrder(@RequestPayload PlaceOrderRequest request) { return null; }

    @SoapAction("http://orders.example.com/action/cancelOrder")
    @ResponsePayload
    public OrderView cancelOrder(@RequestPayload PlaceOrderRequest request) { return null; }
}
```

- [ ] **Step 3: JAX-WS service** (jakarta spelling; the javax spelling gets a second tiny class so BOTH wired rows pin live):

```java
package com.example.orders.soap;

import jakarta.jws.WebMethod;
import jakarta.jws.WebService;
import com.acme.orders.contracts.OrderView;

@WebService(targetNamespace = "http://billing.example.com/ws")
public class BillingWebService {

    @WebMethod(operationName = "chargeOrder")
    public OrderView charge(String orderId) { return null; }

    public OrderView refund(String orderId) { return null; }        // bare public: JAX-WS exposes it (DR-6); name + namespace default

    @WebMethod(exclude = true)
    public void internalAudit() { }                                  // derives nothing
}
```

Plus `soap/LegacyBillingWebService.java` — identical shape, `javax.jws.WebService`/`javax.jws.WebMethod` imports, one `@WebMethod(operationName = "legacyCharge")` method, NO explicit targetNamespace (pins the reversed-package default on the javax row too).

- [ ] **Step 4: JAXB payload + WebServiceTemplate client**:

```java
// payload/PlaceOrderRequest.java
package com.example.orders.soap.payload;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "placeOrderRequest", namespace = "http://orders.example.com/ws")
public class PlaceOrderRequest {
    public String sku;
    public int count;
}
```

```java
// BillingSoapClient.java
package com.example.orders.soap;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;
import com.example.orders.soap.payload.PlaceOrderRequest;

@Component
public class BillingSoapClient {

    private final WebServiceTemplate template;
    private final String billingUri;

    public BillingSoapClient(WebServiceTemplate template, @Value("${soap.billing.uri}") String billingUri) {
        this.template = template;
        this.template.setDefaultUri(billingUri);
        this.billingUri = billingUri;
    }

    public Object place(PlaceOrderRequest request) {
        return template.marshalSendAndReceive(request);                                   // defaultUri path
    }

    public Object placeAt(PlaceOrderRequest request) {
        return template.marshalSendAndReceive("http://billing.example.com/ws/direct", request);  // URI-literal path
    }
}
```

`application.yml` gains `soap.billing.uri: http://billing.internal.example.com/ws` (and the prod profile file a variant — follow the existing `${...}` fixture rows' style).

- [ ] **Step 5: WSDL + XSD** (document/literal; ONE operation no annotation implements — the schema-first pin; the XSD referenced from the WSDL — the cross-file pin):

`orders-types.xsd`: targetNamespace `http://orders.example.com/ws`; elements `placeOrderRequest` (sku `string` required, count `int`, note `minOccurs="0"`, tags `maxOccurs="unbounded"`), `quoteOrderRequest` (the annotation-less operation's input), a `status` enumeration facet type, one `nillable="true"` element.
`orders.wsdl`: imports the XSD; portType `OrdersPort` with operations `placeOrder` (input element `placeOrderRequest` — will AGREE with the annotation row) and `quoteOrder` (input `quoteOrderRequest` — schema-first only); document/literal binding.

- [ ] **Step 6: build + suite.** Fixture builds with the suite's invocation; full suite runs; expect ONLY mechanical scanner/document-count pin churn (update from live output — the standing ruling) plus: the two `marshalSendAndReceive` calls may derive as unresolved rows under existing generic vocabulary — if ANY endpoint row appears, STOP and report which catalog derived it (nothing catalogs SOAP yet; a phantom row means an existing catalog matched — controller decides).
- [ ] **Step 7: Commit** `feat(fixtures): SOAP surfaces — Spring-WS, JAX-WS, WSDL, template client`.

### Task 2: CHECKPOINT + vocabulary + the two inbound catalogs

**Files:**
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py` (+ `derive_endpoints.sql`) — the two vocabulary words
- Create: `src/sextant/catalogs/spring-ws.yml`, `src/sextant/catalogs/jakarta-jws.yml`
- Test: vocabulary unit tests beside the 2H naming-form tests; live pins in the pipeline tests

**Interfaces:**
- Consumes: T1 bytecode; 2H's `path_fallback`/qualifier machinery and validation patterns.
- Produces: soap inbound rows; `qualifier_format: qname` and `namespace_default: reversed_package` for T4/T5; `checkpoint-task-2.md` answers gating T5 (item 3) and T6 (item 1).

**CHECKPOINT first — write `checkpoint-task-2.md` in the SDD workspace with evidence:** (1) does the extractor accept a JAR input (feed it the fixture's own built jar; gates T6's approach); (2) the reversed-package algorithm against real JAX-WS (probe `wsimport`/JAX-WS RI behaviour or its spec text: `com.example.orders.soap` → `http://soap.orders.example.com/`? trailing slash? — pin the exact string JAX-WS produces); (3) is a call argument's TYPE recoverable from existing call_site facts (the `marshalSendAndReceive(request)` argument — what kind/symbol does it carry? gates T5's identity vocabulary); (4) defaulted `@WebService`/`@WebMethod` attributes in bytecode (absent vs empty — the 2H probe replayed); (5) how `@XmlRootElement(name, namespace)` reads on `PlaceOrderRequest`'s class facts.

- [ ] **Step 1: vocabulary, test-first.** `qualifier_format: qname` — mutually exclusive with `qualifier_separator` (declaring both refused; `qname` with no `qualifier_from` refused); produces `{namespaceAttr}localAttr`. `namespace_default: reversed_package` — when the namespace-carrying attribute is absent, derive per checkpoint item 2's pinned algorithm; any other word refused. Unit tests over an invented framework (the 2H pattern): explicit both-attrs → `{ns}op`; absent namespace + `reversed_package` → the pinned reversed form; absent namespace + NO `namespace_default` → row derives with path unresolved (never a guessed namespace); refusals (both forms declared; unknown word; qname without qualifier_from).
- [ ] **Step 2: spring-ws.yml** — `annotation_driven`, `protocol: soap`, `format_fixed: {soap: xml}`; `@Endpoint` class gate; `@PayloadRoot` rule with `qualifier_from: [namespace, localPart]` + `qualifier_format: qname`, method NULL; `@SoapAction` rule with the action value as path; request shape from the `@RequestPayload` parameter (existing vocabulary).
- [ ] **Step 3: jakarta-jws.yml** — BOTH `jakarta.jws.WebService` and `javax.jws.WebService` class gates (no prefix machinery needed — verify and state); `@WebMethod` rule: path from `operationName` with `path_fallback: construct_name`, qualified by the class annotation's `targetNamespace` via `qname` + `namespace_default: reversed_package`; the DR-6 bare-public-method rule (class gate derives public methods without `@WebMethod` — check how existing class-gates enumerate methods; if the engine only derives annotated methods, this needs the class-gate-derives-members vocabulary the `@ServerEndpoint`/`@OnMessage` catalog used — cite that mechanism, don't invent); `@WebMethod(exclude = true)` derives nothing (a `when`-style attribute filter — existing vocabulary).
- [ ] **Step 4: live pins.** Expected rows (verify live, pin exact): `(soap, NULL, {http://orders.example.com/ws}placeOrderRequest)` handler placeOrder; `(soap, NULL, http://orders.example.com/action/cancelOrder)`; `(soap, NULL, {http://billing.example.com/ws}chargeOrder)`; `(soap, NULL, {http://billing.example.com/ws}refund)` (bare-method + explicit ns); `(soap, NULL, {<reversed default>}legacyCharge)` (javax + defaulted ns); NO row for `internalAudit`. All `(xml, resolved)` via rung 1 (format_fixed's second live surface — pin it). Suite green, hooks; commit `feat: SOAP inbound — Spring-WS and JAX-WS on QName vocabulary`.

### Task 3: WSDL/XSD reader and the interpreter's fourth branch

**Files:**
- Create: `src/sextant/ingress/read/wsdl_xsd.py`
- Modify: `src/sextant/domain/facts.py` (`schema_format` Literal gains `"wsdl"`), `src/sextant/ingress/interpret/descriptors.py` (wsdl branch — or the per-format split if the module crosses ~1300 lines: sanctioned, state what you did), `src/sextant/ingress/detect/maven.py` (+port if needed: schema roots `src/main/resources/wsdl`, `src/main/resources/xsd`, `META-INF/wsdl`)
- Test: `tests/ingress/read/test_wsdl_xsd.py`, `tests/ingress/interpret/test_wsdl_descriptors.py`

**Interfaces:**
- Consumes: ArtifactReader protocol (`reads_schema_sources = True`), the 2H merge/failure discipline in `descriptors.py`.
- Produces: wsdl `declared_shape` facts (schema_name = QName `{ns}element`, origin source, evidence declared, `role="operation"` on operation input elements — T4's input).

- [ ] **Step 1: failing reader tests** — claims `wsdl`/`xsd` only; verbatim emission; coexistence with the other readers.
- [ ] **Step 2: failing interpreter tests** (in-test XML mirroring T1's fixture files): element/complexType → shapes with `wire_name` verbatim; `minOccurs="0"` → not required; `nillable` → nullable; `maxOccurs="unbounded"` → array+item; enumeration → enum symbols; WSDL `<types>`-embedded XSD and standalone XSD join ONE universe; `xsd:import` cross-file resolves; missing import → that file fails, others interpret, partial discarded (the 2H boundary verbatim); duplicate type names across files → those files fail; substitution groups/`xsd:any`/`choice` → that file's gap; **operation marking**: each portType operation's input element's shape carries `role="operation"`; an element no operation references carries role None; deterministic double-run.
- [ ] **Step 3: implement** — stdlib `ElementTree` only (extend the confinement test's allowlist? NOT needed — stdlib is not a runtime; but ADD a positive-control-style test asserting no third-party XML lib is imported, matching the file's pattern). `role` Literal gains `"operation"` in `domain/facts.py` (neutral docstring sentence in D00 lands in the same commit — the 2H precedent).
- [ ] **Step 4: full suite (fixture pin churn: wsdl declared shapes appear — from live output); hooks; commit** `feat: WSDL/XSD reader and the interpreter's wsdl branch`.

### Task 4: Schema-first operations — per-shape derivation

**Files:**
- Modify: `src/sextant/application/resolve/engines/schema_operations.py` (the one engine touch: `role == "operation"` derives one row from THE SHAPE ITSELF — path = its schema_name, method NULL — never from its fields)
- Create: `src/sextant/catalogs/wsdl-schema.yml` (`style: schema_operations`, `protocol: soap`, `schema_format: wsdl` gate, `format_fixed: {soap: xml}`)
- Test: `tests/application/test_schema_operations.py` additions + live pins

**Interfaces:**
- Consumes: T3's role-carrying shapes; the existing insert-if-absent guard + response-shape coalesce.
- Produces: schema-first soap rows; the graphql behavior byte-identical (regression pins).

- [ ] **Step 1: failing unit tests**: an `operation`-role shape derives `(soap, NULL, {ns}element)` at declared, NULL handler, request shape = the shape itself (wrapper is wire-true — assert request_shape references it); its FIELDS derive nothing (the per-shape-not-per-field pin); a query-role shape still derives per-field (graphql regression); agreement: a pre-existing annotation row with the same QName blocks the twin (first-writer), and `{http://orders.example.com/ws}placeOrderRequest` is exactly that case live.
- [ ] **Step 2: implement + live pins**: `(soap, NULL, {http://orders.example.com/ws}quoteOrderRequest)` appears at declared/none-recorded (the auditTrail analog); `placeOrderRequest` NOT duplicated (count pinned); `(xml, resolved)` on both. Double-run identity. Commit `feat: schema-first SOAP operations — role operation derives per shape`.

### Task 5: Outbound — WebServiceTemplate and generated stubs

**Files:**
- Modify: `src/sextant/catalogs/spring-ws.yml` (outbound `single_call` block: `marshalSendAndReceive`/`sendAndReceive` — URI-literal overload via `url_arg`; `field_sources` for the receiver template's `defaultUri` feed, the `spring-resttemplate.yml` pattern cited in-catalog), `src/sextant/catalogs/jakarta-jws.yml` (outbound `annotation_driven` block: `@WebService` INTERFACES derive outbound rows — the Feign pattern; identity per T2's vocabulary)
- Test: live pins + unit tests for the identity vocabulary IF checkpoint item 3 said yes
- (Conditional, checkpoint-gated): the argument-type-annotation identity vocabulary in `annotation_driven.py`/SQL if item 3 showed argument types recoverable

**Interfaces:**
- Consumes: checkpoint items 3 & 5; T2 vocabulary; 2B's Feign outbound catalog as the pattern (read `spring-cloud-openfeign.yml`).
- Produces: outbound soap rows; T6's stub-jar pins reuse the jakarta-jws outbound block unchanged.

- [ ] **Step 1: rule per checkpoint item 3.** If argument types ARE recoverable: implement the one targeted vocabulary form (path from the argument type's catalog-named annotation attributes — `@XmlRootElement(name, namespace)` via `qname`), unit-tested over an invented framework, and the `place(request)` call pins `(soap, outbound, NULL, {http://orders.example.com/ws}placeOrderRequest)`. If NOT: the call derives with address/peer resolved and path unresolved — pin THAT, state the boundary in-catalog, and record the gap key the row falls under.
- [ ] **Step 2: address resolution pins**: `placeAt`'s URI-literal → resolved address; `place`'s defaultUri → resolved via field_sources from `${soap.billing.uri}` (peer from config — the 2F pin this phase owes). Verify the `both`-direction merge doesn't collide the outbound QName row with the INBOUND `placeOrderRequest` row (same QName, different direction — they SHOULD merge to `both` if identity matches fully: adjudicate against D02 §3 and pin whichever the SQL actually does, honestly).
- [ ] **Step 3: stub outbound**: jakarta-jws.yml outbound block over `@WebService` interfaces (interface construct gate — Feign's); no fixture surface until T6's jar (state: unit-pinned now, live-pinned in T6). Suite, hooks, commit `feat: SOAP outbound — template calls and generated stubs`.

### Task 6: Opt-in library extraction

**Files:**
- Create: `fixtures/orders-soap-client/` (reactor sibling: pom w/ parent, one `wsimport`-shaped interface: `@WebService(targetNamespace="http://billing.example.com/ws")` interface `BillingPort` with `@WebMethod(operationName="stubCharge")`), `fixtures/orders-service/.sextant.yml` (`extract_libraries: ["com.example:orders-soap-client"]`), reactor aggregator pom if the fixture build needs one
- Modify: `fixtures/orders-service/pom.xml` (dependency on the sibling), `src/sextant/ingress/detect/maven.py` (read `.sextant.yml`; resolve coordinates via recorded classpath → library roots), `src/sextant/application/ports/detector.py` (ModuleModel gains `library_roots: tuple[LibraryRoot, ...]` — coordinate + jar path), `src/sextant/application/stages/analyze.py` (scan loop over library roots), `src/sextant/domain/facts.py` (`Document.origin: str | None = None`), `src/sextant/domain/factfile.py` (`facts/lib/<coordinate>/` targets), `src/sextant/egress/render/document.py` (library-contributed rows marked — a `via <coordinate>` note in the endpoint detail, style-matched), metadata gap `libraries_not_resolved`
- (Conditional): extractor zip-walking if checkpoint item 1 falsified jar input — its own commit + extractor version bump
- Test: `tests/ingress/test_sextant_config.py`, wiring tests, live pins

**Interfaces:**
- Consumes: checkpoint item 1; `ClasspathEntry` facts; T5's jakarta-jws outbound block.
- Produces: origin-carrying facts; the live stub row `(soap, outbound, NULL, {http://billing.example.com/ws}stubCharge)` attributed with origin `com.example:orders-soap-client`.

- [ ] **Step 1: failing config tests**: `.sextant.yml` absent → no library roots (byte-identical behavior — regression); present with a resolvable coordinate → one library root (jar path from classpath); unresolvable coordinate → `libraries_not_resolved` gap with the coordinate, no crash; malformed YAML → refused loudly (Sextant's own input — the DR-6 exemption).
- [ ] **Step 2: wiring**: scan loop runs the extractor over each library root; Documents carry `origin`; fact files land under `facts/lib/<coordinate>/…` (coordinate path-sanitized — state the sanitization rule); double-run byte-identity incl. the lib subtree; the module's own facts carry `origin: None` and identical bytes to a run without the config (isolation pin).
- [ ] **Step 3: live pins**: the stub row derives with origin; the rendered document marks it (`via com.example:orders-soap-client` — pin the line); removing `.sextant.yml` removes the row (assertion-rule pin). Suite, hooks, commit(s) `feat: opt-in library extraction — .sextant.yml` (+ extractor commit if conditional fired).

### Task 7: Docs, COVERAGE, README, roadmap — milestone 1

**Files:**
- Modify: `docs/components/D00-fact-schema.md` (verify T3's role sentence; `Document.origin`; `schema_format` wsdl), `D01` (QName + action-URI identity forms), `D02` (`qualifier_format`/`namespace_default` words + refusals; the soap catalogs; `wsdl-schema.yml`; per-shape operation derivation; the §5 mechanism + assertion rule), `D06` (soap rendering; the `via <coordinate>` marking), `docs/COVERAGE.md` (§5.3 flips + boundaries: rpc/encoded, @SoapAction link-orphans, WS-*/MTOM/Dispatch, un-opted jars invisible, runtime WSDL URLs, auto-scan never), `README.md` (`.sextant.yml` section), roadmap (2I delivered; the "catalog work only" honesty edit; **milestone 1 declared** — modulo the named A-tier rows and ledgered extractor candidates; headline re-derived by counting actual flips)
- Test: suite stays green (docs only)

- [ ] **Step 1**: every claim checked against shipped code (a false doc sentence is a Critical — the standing discipline); checkpoint-gated outcomes (T5 item 3, T6 item 1) documented as they SHIPPED, not as planned.
- [ ] **Step 2**: commit `docs: 2I — SOAP delivered, milestone 1`.

---

## Plan Self-Review (run before execution)

1. **Spec coverage**: §1→T2 pins; §2→T2; §3→T3 (+permitted split); §3 schema-first→T4; §4→T5; §5→T6 (incl. assertion-rule render marking); §6 fixtures→T1+T6, checkpoint→T2; §7→T7; §8 boundaries→T7. The three self-review corrections all have homes: library-inbound assertion (T6 step 3 + T7), per-shape derivation (T4 step 1's pin), field_sources naming (T5 step 2).
2. **Placeholder scan**: clean — conditional steps carry decision rules, not TBDs.
3. **Type consistency**: `role="operation"` (T3→T4); `Document.origin: str | None` (T6); `library_roots`/`LibraryRoot` named once (T6 owns both sides); checkpoint file name `checkpoint-task-2.md` used by T5/T6.
4. **Known risks, stated**: T1's phantom-row stop condition (an existing generic catalog might match `marshalSendAndReceive`); T5's both-direction QName merge adjudication (pin reality against D02 §3); the javax API jar coordinate choice left to verification with a decision rule.
