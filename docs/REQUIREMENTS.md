# REQUIREMENTS

What Sextant must do, and the properties its output must have. This document states
*what*, never *how*; technology choices live in [ARCHITECTURE.md](ARCHITECTURE.md), and the
component that realises each requirement is named in
[Traceability](#traceability) at the end. Terms used here are defined in
[CONTEXT.md](../CONTEXT.md) and are not redefined.

---

## Scope of version 1

**In scope.** Java and Kotlin modules whose bytecode is available. Analysis of a single
module, of several modules in one repository, and of a system assembled from modules
across repositories. HTTP, SOAP, gRPC, and message-broker boundaries.

**Recorded for later versions, not built now.** Python, Go, Rust, and
TypeScript/JavaScript extraction. Source-level extraction of any language. Front-end
participation in a system.

**Explicitly excluded.** Performance measurement of any kind. A general code-search or
summarisation index. Any call to a language model from inside Sextant. Enforcement of
architecture rules in continuous integration.

---

## Functional requirements

### FR-1 — Module discovery

Sextant discovers the buildable units at a given path by reading the build files, and
classifies each as a service or a library from evidence rather than by convention.

A repository containing several modules is analysed in one invocation, producing **one
workspace per module**. A sibling module enters a dependent's analysis as a first-party
dependency through its build output, so calls between them resolve inside each workspace
while each module remains a separate participant at the system tier. The discovered module
inventory is recorded at the repository root for later discovery.

*Where the evidence does not determine the classification, Sextant reports it as
undetermined rather than choosing.*

### FR-2 — Fact extraction

Sextant produces facts from a module's compiled artifacts, without requiring its source
and without requiring the module to have been analysed before.

Extraction reads, at minimum: type hierarchies, method signatures, call sites with
fully-qualified targets, annotations with their argument values, constant values, and
source file and line attribution.

Facts are the only output of extraction. Everything else Sextant produces is derived
from facts.

### FR-3 — Endpoint catalog

Sextant produces a catalog of every endpoint a module exposes and every endpoint it
calls, across HTTP, SOAP, gRPC, and message brokers.

Each entry carries its protocol, its wire identity, its handler or calling symbol, its
request and response shapes, and its trust fields.

*Framework knowledge that maps a library's API onto an endpoint is expressed as catalog
data, never as code, so that supporting a new framework requires no change to Sextant
itself.*

**Status, as of Phase 2O Task 6: all four protocol families named above derive.** HTTP
(both directions, plus GraphQL, WebSocket and SSE on top of it), SOAP, the message brokers
Kafka, JMS, SQS and Pub/Sub, and now gRPC. gRPC's Java surface shipped in two halves
([COVERAGE.md](COVERAGE.md) §5.7): the `.proto` descriptor (Phase 2O Task 4, both origins —
embedded and a `.proto` file on disk) and the JVM bytecode half (Task 5) — a
framework-neutral `supertype_derived` engine for generated `<Service>ImplBase`
implementations (capability 9.13's `superclass` plus a call-site-argument read, R11) and an
`injected_client` engine for net.devh's `@GrpcClient`-injected stubs, fenced against a
locally-implemented service by symbol name. The `@GrpcService`/net.devh annotation
CORROBORATION ships alongside them (`grpc-spring.yml`, on `annotation_driven`'s new
`corroborates` block): it derives no endpoint row — the annotation carries no service
name and cannot mint an identity — and instead surfaces an annotated-but-unmatched class
as a `service_identity` question rather than silence. Three boundaries remain stated
rather than closed — published-stubs jars, an UNANNOTATED Spring gRPC service implemented
against published stubs, and bare `newBlockingStub(channel)` wiring with no field
injection ([COVERAGE.md](COVERAGE.md) §5.7).
None of the three narrows what derives; each narrows what a silent miss is visible as.

**Phase 2O Task 6 adds the first endpoints nobody DECLARED.** Spring Data REST exposes a
CRUD HTTP API from a repository interface — no controller, no mapping annotation — and the
new `derived_resource` style derives that route table from the framework's own rule
([COVERAGE.md](COVERAGE.md) §5.1, verified live in `scripts/probes/cp2_data_rest.md`).
Because such a rule is CONDITIONAL, this is the first style with a DEPENDENCY gate:
[D02](components/D02-catalog-schema.md) §1's `detect.coordinates` is now read, matched
against the coordinates the module's build declares (which travel as
[D00](components/D00-fact-schema.md) §5's `module` fact, constructed for the first time),
and a module that does not declare the framework — or one whose build system cannot answer
the question, as Maven cannot for a transitively-inherited starter — is reported SKIPPED
with its reason rather than derived or silently omitted.

**Phase 2O Task 7b adds the oldest HTTP surface on the platform.** A Jakarta Servlet
carries its address on a TYPE-level `@WebServlet` and its verb on the `doXxx` method it
overrides, which no shipped style could join — an annotation-driven derivation joins method
symbols, and `supertype_derived`'s match requires a supertype whose own facts are in the
module. The new `supertype_dispatch` style reads all three pieces jointly: the type
annotation for the address, a catalog-named supertype for the dispatch contract, and the
members the class overrides — selected by name AND parameter types, which is how the
language identifies one — for the operations
([COVERAGE.md](COVERAGE.md) §5.1, measured live in `scripts/probes/cp9_servlet_shapes.md`
against three container versions). It ships twice, once per package spelling
(`jakarta-servlet.yml` and `javax-servlet.yml`), because the legacy estate the surface
exists for is the population using the older one — and as two catalogs only because the
third container column measured the two behaving identically, never on the assumption that
they would. Its boundaries are stated rather than closed: the annotation is one of three
registration routes (`web.xml` and `ServletContext.addServlet` derive nothing); a module
whose `web.xml` declares `metadata-complete="true"` serves none of its annotated servlets
and we derive all of them, because nothing here reads a deployment descriptor; and the
verbs the container serves IMPLICITLY are deliberately not derived — the code serving them
is not in the module, and the same ruling was already made for Data REST above. An
explicitly overridden handler is a different case and derives even where a deployment
would refuse to route to it: `doTrace` is in the verb map with the connector's `allowTrace`
recorded as a stated dependency, because configuration outside the module is not evidence
about the module.

### FR-4 — Shape catalog

Sextant produces the shape of every payload crossing a boundary: its fields, their
types, whether each is required, and its wire identity.

Shapes are identified by wire contract — serialised field names, or field numbers where
the format defines them — never by the name of the type carrying them.

Where a shape comes from a schema format with published compatibility rules, those rules
are applied rather than reimplemented.

### FR-5 — Call graph

Sextant produces the calls between symbols within a module, and resolves the possible
targets of each call site.

Where a call site has more than one possible target, every candidate is recorded. No
call site is reduced to a single guessed winner.

### FR-6 — Traces

For every inbound endpoint, Sextant produces the call structure reachable from it, from
its root to each terminal.

A trace carries the control-flow position of each call, so that alternatives, loops and
optional branches are distinguishable from a straight sequence.

Traces are not bounded by depth. A trace stops only at a terminal.

> **Not met as shipped, and recorded rather than quietly reinterpreted** (2Q,
> `docs/open-issues.md` OI-27). The walk stops at a terminal and at three other places: a
> depth bound of 64 (a safety limit, never silent — 0 of `mall-admin`'s 160 traces reach
> it), a `cycle`, and a method already expanded elsewhere in the same trace. Whether the
> close is an amended requirement or changed code is a decision this document's owner
> takes; until then the divergence is stated here, in `COVERAGE.md`, and in the rendered
> document's own `Known gaps`.

### FR-7 — Diagrams

Sextant renders sequence diagrams at module and system level, and class diagrams, from
the graph.

Rendering introduces no information that is not in the graph. Where a diagram omits
anything, it states that it has done so and how much.

*Terminals of kind `unresolved` and `cycle` are always drawn, and cannot be suppressed
by any filter or overlay.*

> **Module-scope sequence diagrams ship in 2Q, one per root, and they are FLAT** — no
> `alt`/`opt`/`loop`, because `call_site.ordinal` is instruction order and nothing more
> ([D00](components/D00-fact-schema.md) §5, which prices the richer field as a later
> re-extraction). "Where a diagram omits anything, it states that it has done so and how
> much" is met literally: every diagram carries a machine-written `Elides:` line counting
> each kind of stop, and no step is filtered out of one.

### FR-8 — System linking

Given a set of modules, Sextant matches each outbound endpoint to the inbound endpoints
it may reach, and records the result as a link with its trust fields.

Matching considers protocol, wire identity, and payload compatibility. Payload
compatibility is directional: a client's request must satisfy every field the server
requires, and a server's response must satisfy every field the client declares.

Where more than one inbound endpoint survives matching, every candidate is recorded and
the ambiguity is written out for a person to settle.

Outbound endpoints matching nothing, and inbound endpoints nobody calls, are both
reported as findings.

### FR-9 — Blast radius

Given a symbol, Sextant reports what a change to it would affect, in three parts: what
is definitely affected, what may be affected together with the candidates involved, and
which unknown regions were reached.

Blast radius is never reported as a single count.

### FR-10 — Query surface

Sextant answers structural questions about a workspace without re-analysing it and
without rendering anything: which symbols match a name, where a symbol is defined, what
calls it, what it calls, what implements it, what references a type, what a change to it
would affect, the routes between two symbols, which endpoint a concrete address belongs
to, and what happens when an endpoint is called.

Answers are available in a machine-readable form suitable for direct consumption by an
agent.

*The query surface answers structural questions only. Sextant never produces prose about
what code is for.*

### FR-11 — Drift detection

Where a module contains both a declared contract and an implementation of the same
contract, Sextant records both and reports any disagreement between them.

Authority is determined by the build: an artifact the build consumes produces facts; an
artifact it does not consume is documentation and produces none, but is still compared.

Where a generated artifact embeds the schema it was generated from, that embedded schema
is the one compared.

### FR-12 — Refactor findings

Sextant reports structural problems: dependency cycles between modules or packages,
symbols with disproportionate coupling, and violations of a declared layering.

*A symbol is reported as unreachable only where no unresolved call site exists within the
scope searched. Where one does, the finding is withheld and the unresolved site reported
instead.*

### FR-13 — Design findings

Sextant reports information supporting the division of a system into services: coupling
between candidate boundaries, shapes crossing more than one boundary, and the contracts
each boundary would carry.

### FR-14 — Structural performance risk

Sextant reports shapes in the code that are usually costly: the number of remote hops an
endpoint makes, the number of distinct services it involves, an endpoint reached more
than once within a single trace, a persistence or remote call inside a loop, and a
blocking call on an asynchronous path.

*Sextant reports structure, never cost. It does not measure, estimate, or rank by
latency, throughput, or resource use.*

### FR-15 — Overlays

Sextant accepts overlays: statements about the graph that did not come from reading
code.

An overlay may name only symbols, endpoints, and modules that exist in the graph.
Sextant validates this before any overlay is used, and rejects the overlay otherwise.

Overlays that assert facts are applied during analysis. Overlays that affect presentation
are applied during rendering. No overlay silently overrides evidence: where an overlay
and the graph disagree, the disagreement is recorded as an open question.

### FR-16 — Curation and proposals

A person may assert, correct, or delete a statement in the graph. A curated statement
outranks every other source and is presented to consumers as proven.

Where Sextant finds a candidate it will not act on alone, it writes a proposal in the
form a curation takes, so that accepting it requires review rather than transcription.

### FR-17 — Coverage reporting

Sextant reports, for any workspace: the commit it was built from, which source files the
compiled artifacts did not account for, the distribution of call sites across the
resolution values, and every capability an extractor lacks that a framework catalog
required.

*An analysis that proceeded despite uncovered sources is recorded as partial in the
workspace, and every document derived from it says so.*

### FR-18 — Export

Sextant writes a module's analysis as a portable, self-describing artifact that another
machine can consume without access to the original repository or build.

The artifact records the versions of everything that produced it, so that assembling a
system from artifacts of differing vintages is refused rather than silently joined.

### FR-19 — Exclusion and redaction

Sextant honours a repository-level exclusion list, following the same conventions and
cascading behaviour as version-control ignore files, so that files may be kept out of
analysis entirely.

Independently, Sextant redacts values matching configured patterns at the moment facts
are produced, so that a secret appearing inside a file that is otherwise analysed never
reaches storage.

> **Amendment (2026-09-02, Phase 2K design §2 — approved, Task 2 delivered).** The
> exclusion list is a single **root-level** `.sextantignore` — not the cascading,
> nearest-file-wins behaviour version-control ignore files have when nested; a
> per-directory file is a stated fast-follow, not read today. Every pattern in it is
> matched against a path relative to the repository root, whatever resource or schema
> root a given walk started from. Underneath it, a fixed, **non-negatable** built-in
> pattern set (`domain/ignorefile.py`'s `BUILTIN_PATTERNS`) always applies — a repository
> `.sextantignore` cannot re-admit a file the built-ins exclude, only widen exclusion
> further among its own patterns. See [D04](components/D04-config-and-exclusion.md) §3
> for the full amendment, including the built-in set itself.

> **Amendment (2026-09-02, Phase 2K design §1 — approved).** Redaction runs at the
> **exits** — the rendered document, the exported bundle, and the enrichment tools' read
> path — not at fact production. Masking values on the way in would empty the very table
> the endpoint catalog resolves addresses against; the workspace is the analyst's own disk
> and is not the trust boundary. See [D04](components/D04-config-and-exclusion.md) §4 for
> the full amendment, including what is not yet covered.

### FR-20 — Command surface

Every command takes the form *noun, verb, subject, options*. Subjects may be named
approximately; where a name is ambiguous Sextant lists the matches and stops rather than
choosing. Every result carries an exact identifier that can be given back to Sextant.

---

## Non-functional requirements

### NFR-1 — Determinism

The same inputs produce byte-identical outputs. This holds for the entire product: no
part of Sextant's output depends on a non-deterministic source.

*Verified by byte-comparing fact files, bundles, rendered documents and `metadata.json`
across repeated runs on fixed example repositories. The workspace database file itself is
not byte-compared — no embedded database guarantees file-level stability — so its
determinism is verified by comparing its exported tables instead.*

> **Amendment (2026-09-02, Phase 2K design §8 — approved, delivered).** `sextant module
> enrich` calls a language model, and that one call is the sole exclusion from this
> requirement in the entire product. Everything else `enrich` does stays byte-deterministic:
> the brief composed from a workspace, the validation an agent's (or `--ingest`'s) answer is
> checked against, and the assembly that interleaves a written `.sextant-enrichment.json`
> into `architecture.md`/`architecture.html`. Same workspace plus the same overlay produces
> the same rendered documents on every run — `render`, invoked standalone over a workspace
> with an overlay already on disk, takes the identical assembly code path `enrich`'s own
> auto-render does, so the two outputs can never disagree. See
> [ARCHITECTURE.md](ARCHITECTURE.md#dr-2--no-language-model-inside-sextant) DR-2's own
> amendment for the port and adapter this call runs behind.

### NFR-2 — Honest failure

Sextant states what it could not do. Silent degradation is a defect.

Specifically: a partial analysis fails unless explicitly permitted, and when permitted is
recorded as partial; an unresolved target is a first-class recorded value carrying its
reason and location, never an omission and never a guess; a filtered or simplified output
states that it was filtered.

### NFR-3 — Stable identity

A symbol's identifier is derived from its content and is stable across runs, across
machines, and across modules. The same entity observed from two modules carries the same
identifier.

*This is what makes blast radius work across a system, and what makes comparison between
two analyses possible later.*

### NFR-4 — Incrementality

Re-analysis after a change costs work proportional to what changed. Facts are maintained
per source file; everything derived from them is rebuilt whole, never patched in place.

Any cached result is keyed by every input that could change it, including the versions of
the code that produced it and the redaction patterns in force. A stale cache is treated
as a correctness defect, not an efficiency one.

### NFR-5 — Closed construct sets

The vocabulary of the fact model is closed. Root kinds, terminal kinds, construct kinds,
resolution values, evidence values, and unresolved reasons are each a fixed, enumerated
set defined once.

Extending a closed set is a schema change that invalidates existing analyses and requires
re-extraction. Language-specific detail is carried in a per-language extension namespace,
never by widening a closed set.

### NFR-6 — Fact set justified by consumers

Every fact kind and every edge kind exists because a stated requirement consumes it.
Anything with no consumer is not produced.

*Where a fact kind is retained speculatively, it is disabled by default and enabled
explicitly.*

### NFR-7 — Language-neutral output

The set of files Sextant produces, and the vocabulary within them, is the same regardless
of the language analysed. A section with nothing to report is present and empty, never
absent, so that "nothing found" is distinguishable from "not examined".

Language is recorded as a property of the source of a fact, never by varying the shape of
the output.

### NFR-8 — Confidentiality

No credential, key, token, or value matching a configured redaction pattern is written to
any fact, workspace, export, or rendered document.

*Redaction occurs before anything reaches storage, because a value already written cannot
be withdrawn from artifacts already distributed.*

> **Amendment (2026-09-02, Phase 2K design §1 — approved).** The guarantee is scoped to
> what **leaves**: the export and the rendered document, plus the enrichment tools' read
> path. Facts and the workspace hold values verbatim, because resolution needs them and
> the local disk is not the boundary — and because a value masked on the way in cannot be
> resolved on the way out either. What a bundle was masked with is recorded on it
> (`producer.redaction_set_hash`), so the claim is checkable rather than assumed.

### NFR-9 — Extension without modification

Adding support for a framework requires only data and a test fixture. Adding a language
requires only a new extractor and its data. Neither requires a change to any stage between
extraction and rendering, and neither requires modifying an existing test.

Behaviour is selected by what an extractor declares it can do, never by which language it
handles.

### NFR-10 — Schema as code

The fact schema is expressed as validated definitions and enforced when facts are
written. Documentation of the schema is generated from those definitions.

*Drift between the schema as documented and the schema as written must be impossible,
rather than detected during review.*

### NFR-11 — Bulk data handling

Data movement between stages is performed in bulk. Per-row operations across a fact set
are a defect, not an optimisation opportunity.

---

## Traceability

Every requirement names the component that realises it. A requirement with no component, or
a component realising no requirement, is a defect in one of the two documents — NFR-6
depends on this table being complete in both directions.

Component designs live in [components/](components/README.md).

### Functional

| | Requirement | Realised by |
|---|---|---|
| FR-1 | Module discovery | [M02](components/M02-detector.md) |
| FR-2 | Fact extraction | [M03](components/M03-scanner.md), [D00](components/D00-fact-schema.md) |
| FR-3 | Endpoint catalog | [M04](components/M04-resolver.md), [D02](components/D02-catalog-schema.md) |
| FR-4 | Shape catalog | [M04](components/M04-resolver.md), [D01](components/D01-graph-schema.md) |
| FR-5 | Call graph | [M04](components/M04-resolver.md) |
| FR-6 | Traces | [M04](components/M04-resolver.md), [M03](components/M03-scanner.md) |
| FR-7 | Diagrams | [M07](components/M07-renderer.md) |
| FR-8 | System linking | [M06](components/M06-stitcher.md), [M05](components/M05-sync.md) |
| FR-9 | Blast radius | [M09](components/M09-query.md) |
| FR-10 | Query surface | [M09](components/M09-query.md), [D01](components/D01-graph-schema.md) |
| FR-11 | Drift detection | [M03](components/M03-scanner.md), [M04](components/M04-resolver.md) |
| FR-12 | Refactor findings | [M04](components/M04-resolver.md) |
| FR-13 | Design findings | [M04](components/M04-resolver.md) |
| FR-14 | Structural performance risk | [M04](components/M04-resolver.md) |
| FR-15 | Overlays | [M01](components/M01-overlay.md), [D03](components/D03-overlay-schema.md) |
| FR-16 | Curation and proposals | [M01](components/M01-overlay.md), [M06](components/M06-stitcher.md) |
| FR-17 | Coverage reporting | [M02](components/M02-detector.md), [M03](components/M03-scanner.md), [M04](components/M04-resolver.md) |
| FR-18 | Export | [M08](components/M08-exporter.md), [D06](components/D06-bundle-format.md) |
| FR-19 | Exclusion and redaction | [D04](components/D04-config-and-exclusion.md), [M03](components/M03-scanner.md) |
| FR-20 | Command surface | [M00](components/M00-cli.md) |

### Non-functional

| | Property | Held by |
|---|---|---|
| NFR-1 | Determinism | [M01](components/M01-overlay.md) per-slot resolution, [M08](components/M08-exporter.md) deterministic output |
| NFR-2 | Honest failure | Every module's *Honesty obligations* section |
| NFR-3 | Stable identity | [D00](components/D00-fact-schema.md) |
| NFR-4 | Incrementality | [D01](components/D01-graph-schema.md), [M04](components/M04-resolver.md) |
| NFR-5 | Closed construct sets | [D00](components/D00-fact-schema.md) |
| NFR-6 | Fact set justified by consumers | [D00](components/D00-fact-schema.md), [D01](components/D01-graph-schema.md), and this table |
| NFR-7 | Language-neutral output | [D00](components/D00-fact-schema.md), [M07](components/M07-renderer.md) |
| NFR-8 | Confidentiality | [D04](components/D04-config-and-exclusion.md), [M03](components/M03-scanner.md) |
| NFR-9 | Extension without modification | [D02](components/D02-catalog-schema.md), [M03](components/M03-scanner.md) capability selection |
| NFR-10 | Schema as code | [D00](components/D00-fact-schema.md) |
| NFR-11 | Bulk data handling | [M04](components/M04-resolver.md) |

**Two components realise no requirement directly**, by design.
[M00](components/M00-cli.md) is the composition root, and
[D05](components/D05-manifest-and-state.md) is the state that makes FR-8 and FR-17
reproducible across runs.

---

## Known gaps in version 1

Recorded so they are not mistaken for oversights.

| Gap | Consequence |
|---|---|
| ~~SOAP contracts are not read~~ — **closed in Phase 2I** | `.wsdl`/`.xsd` files in the repository are read into declared shapes, and an operation's input element gives the same QName identity an annotation states, so a SOAP link has a contract key rather than a structural fallback. What remains is narrower and named in [COVERAGE.md](COVERAGE.md) §5.3: the output message is not read, so a schema-first row carries no response shape, and `rpc/encoded` is out of scope. A module whose contract lives only at a runtime URL still falls back to structure, and FR-17 still requires that be reported. |
| Branch conditions are not named | Sequence diagrams show `alt`, `opt` and `loop` blocks with unlabelled branches — the structure is honest, the condition text is not recovered from bytecode in this version. |
| Message payload schema files are not read | Payload shapes for brokers come from code only. |
| Source-retention annotations are not visible | Measured as reaching no requirement on this list. |
| Comments and documentation are not extracted | Sextant produces no prose; see FR-10. |
| A module that does not build cannot be analysed | FR-17 requires this be reported rather than worked around. |
