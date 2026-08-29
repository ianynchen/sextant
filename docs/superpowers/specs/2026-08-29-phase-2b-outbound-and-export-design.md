# Phase 2B — Outbound annotation clients and bundle export: design

**Approved through brainstorming, 2026-08-29.** This spec is the authority for the Phase 2B
implementation plan. It follows Phase 2A (shapes and nullability, merged as PR #2) and
precedes the call-site clients phase.

**Goal.** A module's analysis covers both directions of its HTTP surface — the endpoints it
exposes and the annotation-declared calls it makes, each carrying its payload contract —
and the whole analysis exports as a portable bundle. After 2B, `analyze → render → export`
is a functional end-to-end pipeline for a Spring Boot service, which is the milestone the
version bump waits on.

**Scope decisions taken with the user:**

- 2B = outbound annotation clients **plus** the M08/D06 exporter. DR-5 linking and the
  system workspace are the next-plus-one phase (linking is a system-scope activity over
  bundles; it structurally cannot live in a single-module analyze).
- Client libraries: Spring Cloud OpenFeign, Spring 6 `@HttpExchange`, Retrofit. The
  call-site clients (RestTemplate, WebClient, OkHttp) are the immediately following phase —
  they need `call_site`/`string_constants`/`chain_reconstruction`, capabilities that do not
  exist; pulling them into 2B was considered and rejected for size.
- Transforms run **once, at derivation** (adversarially reviewed with the user): the wire
  form of a payload is stored, not recomputed by consumers. The raw generic types remain in
  the facts verbatim; the derived layer records their wire projection. Comparison at link
  time is a read over stored field lists, never a re-derivation — the bundle seam (M08)
  depends on this.

---

## 1. Outbound derivation: one engine, three catalogs

The `annotation_driven` engine gains three generalisations, all driven by catalog data — no
framework name enters the engine:

1. **`type_annotation` becomes optional.** A catalog may declare none (Retrofit interfaces
   have no type-level marker; they are recognised by `retrofit2.http` method annotations
   alone). When absent, any type containing a matching mapping annotation participates and
   the controller join disappears for that catalog.
2. **`direction` flows from the catalog into endpoint rows.** Already a bound parameter;
   every existing catalog is inbound so nothing varied until now. `@HttpExchange`'s
   server-side dual use (D02 §2c `resolves`) is **not implemented**: it ships as the named
   gap `http_exchange_inbound_use_not_detected`. The §3 merge below still guards the
   semantics for the day it matters.
3. **The body-parameter rule becomes catalog data:**
   `request_body: {annotation: <fqn>, fallback: sole_unannotated | none}`.
   Spring inbound and `@HttpExchange`: `@RequestBody`, no fallback. Retrofit: `@Body`, no
   fallback. Feign (Spring contract): `@RequestBody` with `sole_unannotated` fallback.
4. **The type-level annotation declares its own attribute lists** — `prefix_from` (which
   attributes mean URL prefix, in alias order) and `peer_from` (which mean the peer).
   The engine today reads type-level prefixes through the same `path_from` alias list that
   serves method mappings; that works for `@RequestMapping` (where `value`/`path` are
   aliases meaning *path*) and is silently wrong for `@FeignClient` (where `value` aliases
   **`name`** — the service id — and only `path` means prefix): the service name would
   become a path prefix on every Feign endpoint. Catalogs declare:
   `@RequestMapping` → `prefix_from: [value, path]`; `@FeignClient` →
   `prefix_from: [path]`, `peer_from: [name, value]`; `@HttpExchange` →
   `prefix_from: [value, url]`. Type-level and method-level annotations are different
   roles; the shared alias list conflated them by the luck of `@RequestMapping`'s aliasing.

**Three new catalogs:** `spring-cloud-openfeign.yml`, `spring-http-interface.yml`,
`retrofit.yml` — each `direction: outbound`, `style: annotation_driven`, with its own
mapping table and the wrappers/nullability/serialization/known_types blocks (Feign and
`@HttpExchange` reuse Jackson semantics; Retrofit ships Jackson-converter-shaped in 2B).
Detect coordinates: `org.springframework.cloud:spring-cloud-openfeign-core`,
`org.springframework:spring-web` (interface package present since 6.0),
`com.squareup.retrofit2:retrofit`.

**Endpoint model additions (D01 amendments):**

- **`peer`** (nullable TEXT): the link-target hint — `@FeignClient(name=…)`'s service name,
  or the authority when `url=` is a literal. Retrofit and `@HttpExchange` leave it NULL
  (base URLs live in builder code — the call-site phase); the named gap
  `client_base_addresses_not_resolved` covers those NULLs.
- **Endpoint identity is minted WITHOUT direction** (D01 amendment, decided after
  adversarial review): D01 §3 currently hashes *(module, protocol, direction, wire
  identity)*, but D02 §3's merge makes direction **mutable** — an exposed path gains a
  client and becomes `both` — and mutable state does not belong in identity, by D01's own
  argument for excluding the handler ("a refactor that moves the handler must not orphan
  the curations… the wire contract did not change"). Identity becomes
  *(module, protocol, wire identity)*. The rule is spec'd-but-unimplemented and nothing
  references endpoint identities yet, so this is the cheapest moment it will ever be.
- **`caller`** (nullable TEXT): the client-side method symbol. A merged `both` row keeps
  `handler` (server side) **and** `caller` (client side) — D01's "handler or caller"
  becomes "handler and/or caller". An outbound-only row carries `caller` with `handler`
  NULL. The shape columns of a `both` row serve both directions at once: what the client
  sends is what the server receives.
- **D02 §3 inbound/outbound merge**: a wire identity a module both exposes and calls
  becomes one endpoint with `direction: both`, handler and caller both retained. The
  fixture exercises it end-to-end.

## 2. Endpoint payload descriptors and shape reuse

`endpoints.request_shape` / `response_shape` change from a bare shape id to a JSON
descriptor in the exact grammar `shape_fields.item` uses —
`{wire_type, wire_format, nullable, shape_id?, item?}`:

| Payload | Descriptor |
|---|---|
| `OrderRequest` body | `{"wire_type":"object","shape_id":"…OrderRequest#"}` |
| `List<OrderView>` | `{"wire_type":"array","item":{"wire_type":"object","shape_id":"…OrderView#"}}` |
| `Map<String,OrderView>` | `{"wire_type":"map","item":{…}}` (value descriptor; JSON keys are strings) |
| `String` | `{"wire_type":"string"}` |
| `void` / no body parameter | `NULL` — the one meaning NULL keeps: *no payload* |

This supersedes 2A's "only object roots get a column" rule. Scalar payloads are recorded;
NULL stops being ambiguous. The `collection_payloads_carry_no_shape` gap **closes** (both
gap lists, in lockstep — retired because fixed, not renamed).

Rooting order is unchanged: wrappers unwrap first (`ResponseEntity<List<OrderView>>` →
array descriptor); the declared-envelope refusal stays; a scanned-enum payload is
`{"wire_type":"enum"}`.

Outbound roots feed the existing `derive_shapes` pass with the client catalog's blocks.
Shared types across an inbound and an outbound catalog ride the existing insert-if-absent
discipline.

**Spec amendments riding this section:**

- D01 §5: descriptor grammar on the endpoint columns; the clarifying sentence that
  **`shape_id` is the payload type's symbol — a local join key, never compared across
  services** (DR-5 matches field structure, not ids); and the object case added to the
  `item` enumeration (parked drift from 2A's final review).
- D02: the outbound catalog vocabulary (`request_body`, optional `type_annotation`,
  `peer` sourcing), and the false "chain recorded on the endpoint" sentence (§ near 214)
  corrected — the other parked 2A drift.
- D02 §7 gains an open-decision row: `known_types.nullable` versus a
  `not_null_by_default` scope — precedence unspecified; scope wins as implemented
  (parked 2A ruling, now recorded in the spec where it belongs).

## 3. The exporter (M08 / D06)

**CLI:** `sextant module export <path> [--workspace DIR] [--out DIR]`. Reads what `analyze`
left; never re-analyzes. Output: a bundle directory `<module-id>@<commit>` (sanitised),
laid out exactly per D06 §2:

```
<module-id>@<commit>/
  manifest.json
  facts/**/*.parquet     one partition per source file, mirroring the JSONL tree
  graph/*.parquet        endpoints, shapes, shape_fields, symbols, documents, annotations
```

**All Parquet is written by DuckDB's native `COPY … TO` behind the Workspace port** — zero
new dependencies. Layering: storage does all Parquet I/O (a port method per table, reusing
each table's deterministic `ORDER BY`); `application/stages/export.py` orchestrates
(application does no file I/O); `egress/export/manifest.py` writes `manifest.json` from
plain data (the `metadata.py` pattern — egress never touches the Workspace port).

**Manifest** (D06 §3), populated honestly for what exists:

- `module`, `source.repo` (git remote), `commit`, `module_commit` (last commit touching the
  module's own path, computed locally).
- `producer`: the three version fields **as they are** (0.1.0 / 1.0.0 / 1.0.0 until the
  user's functional-gate bump), scanner id/version, `catalog_hash` — pinned as sha256 over
  the sorted *(relative filename, bytes)* pairs of the loaded catalog files, computed for
  the first time — and `redaction_set_hash` from documents.
- `environments: []` (nothing resolves profiles yet); `coverage` incl. `partial`; `gaps`
  carried verbatim from metadata.
- `contents.tables` lists only what travelled. The sequence-diagram tables of D06 §5
  (`edges`, `dispatch`, `trace_summary`, `deployments`) do not exist yet; their absence is
  named by the existing gap entries. A 2B bundle supports a contract map, not sequences,
  and says so.

**Facts-as-Parquet schema (pinned):** the raw-fact rows *(kind, document_id, payload as a
JSON string column)*, partitioned per source file per D06 §2 — honest, barely columnar,
sufficient until M05 states a columnar need per fact kind.

**Determinism (NFR-1 at the boundary):** fixed row order, pinned compression, no
timestamps; a test exports twice and byte-compares bundles. Risk note: byte-identity
additionally depends on DuckDB's Parquet writer being stable within one installed version
(it embeds a `created_by` string) — a failure of this test on one machine reads as
environment drift, and its assertion message says so.

**Detect-coordinate note:** `spring-http-interface.yml`'s coordinate (`spring-web`)
matches every Spring module — a weak discriminator, moot today because catalog-module
matching is not enforced (`catalog_module_matching_not_implemented`); the annotation match
is what actually gates. Recorded so nobody later treats the coordinate as the filter.

**D06 open decisions resolved for 2B:** bundle is a **directory** (publishing is the
caller's business; the archive question waits); `--what` deferred (always export facts and
graph — facts are what make a bundle re-derivable); the index question is moot.

## 4. Fixtures, testing, and the rendered document

**Fixture:** extend `orders-service` (a second module waits for the linking phase, where
`participants` gives it a purpose):

- `BillingClient` — `@FeignClient(name = "billing")`, Spring mapping annotations, a
  body-taking method and a `List<…>`-returning method (peer + array descriptor).
- `InventoryExchange` — type-level `@HttpExchange("/v1/inventory")` +
  `@GetExchange`/`@PostExchange` (optional prefix form, NULL peer).
- `LegacyBillingApi` — Retrofit `@GET`/`@POST` with `@Body`/`@Path` (no type marker,
  explicit body annotation).
- One Feign method calling `POST /v1/orders` — a path the module itself exposes — so the
  `direction: both` merge is exercised end-to-end.

Dependency note: `spring-cloud-openfeign-core` and `retrofit` are **not** in the local
Maven repository — a one-time online resolve is a setup step; all tests stay `mvn -o`
afterward. Conformance fixtures use the real frameworks (D02 §4); stubs are off the table.

**Testing:** unit tests over hand-built facts for every engine generalisation, descriptor
form, and the merge; the e2e vertical slice extends to
analyze → outbound endpoints with descriptors and peer → export → bundle exists, manifest
fields correct, a table read back from Parquet equals the workspace query, two exports
byte-identical.

**Gap ledger rotation (exhaustive — a broad label must never narrow silently):**
`outbound_endpoints_not_implemented` retires (it would now be false, and a false gap
misleads as badly as a missing one). Its coverage is replaced label-for-label so every
remaining not-yet stays named, each with a scheduled death:

- `call_site_clients_not_read` — RestTemplate/WebClient/OkHttp; dies in the call-site phase.
- `messaging_endpoints_not_read` — listeners **and** producers (Kafka/JMS/SQS, both
  directions); dies in 2C. This also fixes a pre-existing hole: messaging *inbound* was
  never named in any phase.
- `http_exchange_inbound_use_not_detected` and `client_base_addresses_not_resolved` —
  2B-specific.

Boundary: gaps name the roadmap's known not-yets a Spring Boot reader would expect —
recorded scope *decisions* (e.g. SOAP, per COVERAGE) are not gaps. Each entry paired in
`document.py`'s `_GAPS` lockstep. `metadata.json`'s `endpoints.outbound` counts populate.

## 5. The module document blueprint (M07 amendment)

The target structure of `architecture.md`, agreed with the user. Every target section is
named in M07; each is either derived now or carries its gap by name — a section whose
machinery does not exist must never appear empty (NFR-7: empty claims "looked, found
nothing").

| Section | Source | Status in 2B |
|---|---|---|
| Overview | module identity, kind, languages, coverage, commit | shipped (polish) |
| Structure — contract class diagram | `shapes`/`shape_fields`; nodes are payload types with wire fields, edges are `shape_id` references | **built in 2B** (Mermaid `classDiagram`) |
| Structure — full class diagram (inheritance) | `inherits`/`implements` edges — table does not exist | named gap; call-graph phase |
| Inbound endpoints — contract field tables per endpoint | endpoints + descriptors + shapes | **built in 2B** |
| Inbound endpoints — sequence diagram per endpoint | `edges` with control-flow, `dispatch`, `trace_of` | named gap `sequence_diagrams_pending_call_graph`; call-site/call-graph phases |
| Outbound endpoints | 2B's rows | **built in 2B** |
| Components, descriptions, algorithm design, extension guides | LLM-authored via overlay (M01), `evidence: llm` | later phase (see §6) |

Implementation note: the class-diagram emitter is the first real use of M07's
projection → view model → emitter split — the emitter is tested against hand-written view
models, no workspace needed. Build on that shape rather than extending `document.py`'s
string assembly.

## 6. Later phases recorded here so 2B reserves their slots

**Call-site clients phase (immediately next):** RestTemplate first (`registration_call` —
the cheapest form), then WebClient/RestClient/OkHttp (`fluent_chain`). Needs `call_site`
facts, `string_constants`, then `chain_reconstruction`. Pulled ahead of messaging/WebFlux
by user priority (functional Spring Boot support).

**Linking phase:** M05/system workspace, `participants`, `links`, DR-5 over bundles. The
version-bump gate opens when analyze → render → export is functional end to end; linking
follows.

**Enrich phase (new verb, user-requested):** `sextant module enrich` (later
`system enrich`) invokes an LLM to write the sections machines cannot derive. Four
constraints recorded at decision time:

1. LLM prose lands as **overlay claims (M01) at `evidence: llm`** (rank 10, below `human`
   at 90) — assembled by `render` with provenance labels, never unattributed edits to
   `architecture.md`. A human can promote or correct a claim.
2. **Determinism quarantine:** `render` stays deterministic over workspace + overlay;
   `enrich` is the one creative step, and its output is versionable input (a file in git),
   not pipeline state.
3. **Redaction before the wire:** enrich is the first time analysis data leaves the machine
   mid-pipeline; the bundle's no-unredacted-values rule applies to the API request body.
4. First network + credential dependency: API keys, model choice, an approved dependency
   (ARCHITECTURE §9) — each needs its own decision when the phase is planned.

## Self-review and adversarial round

An initial self-review passed too kindly; a second, adversarial pass against the engine
code and upstream specs found three real issues, resolved with the user one by one:

- **I1** — D01's direction-in-identity contradicted D02 §3's merge, and a merged row had
  nowhere to keep both handler and caller. Resolved (option A): identity without
  direction; nullable `caller` column. §1 carries the full reasoning.
- **I2** — the shared `path_from` alias list would have read `@FeignClient`'s service
  name as a URL prefix. Resolved (option A): `prefix_from`/`peer_from` split, §1 item 4.
- **I3** — retiring the broad outbound gap label would have left messaging unnamed.
  Resolved (option A): exhaustive rotation, §4.

Also pinned: the facts-Parquet schema (I4) and the `catalog_hash` definition (I5); risk
notes recorded for Parquet writer stability (I6) and the weak `spring-web` detect
coordinate (I7). Remaining deliberate openness: exact Mermaid layout of the contract class
diagram is the implementer's, bounded by the emitter-testing rule in §5.
