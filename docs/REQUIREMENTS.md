# REQUIREMENTS

What Sextant must do, and the properties its output must have. This document states
*what*, never *how*; technology choices live in [ARCHITECTURE.md](ARCHITECTURE.md), and the
component that realises each requirement is named in
[Traceability](#traceability) at the end. Terms used here are defined in
[CONTEXT.md](../CONTEXT.md) and are not redefined.

---

## Scope of version 1

**In scope.** Java and Kotlin modules whose bytecode is available — **every JVM framework,
not one.** Spring Boot is the first framework and the version-bump milestone, never the
definition of done; Micronaut, Quarkus, Ktor, Javalin, Vert.x, Alpakka and Temporal are in
scope and sequenced after it. *(Stated 2026-09-11 after the opposite was assumed for a week
and under-counted the remaining work by about eleven libraries.)*
What is not delivered, per feature, is
[`java-kotlin-delivery-list.md`](java-kotlin-delivery-list.md), which
`tests/architecture/test_feature_delivery.py` enforces against this document's own
traceability. Analysis of a single
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

**Status.** All four protocol families named above derive — but *derives* is not
*delivered*, and this paragraph read as though it were for a week. Three protocol cells in
[COVERAGE.md](COVERAGE.md) §2 said `✅` while carrying open Majors, because `✅` there means
*every library catalogued* and never *no open defects*. Per-feature delivery is
[`java-kotlin-delivery-list.md`](java-kotlin-delivery-list.md); what follows is the 2O-era
record of what began deriving and is kept as history.

**As of Phase 2O Task 6:** HTTP
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

> **Met as of W31** (`docs/open-issues.md` OI-27, closed). This said "not met as shipped"
> for the whole of 2Q: the walk stopped at a terminal and at three other places, one of
> which was a depth bound of 64. The bound is gone — the walk is an explicit stack, so the
> interpreter's own recursion limit is out of the failure modes and nothing needs a counter
> to stay finite.
>
> **Two stops remain and they are not depth bounds**: a `cycle` (the callee is already on
> the path from the root) and a `revisit` (the callee was expanded elsewhere in this same
> trace, and its subtree is shown there). Both are correctness rather than limits — without
> them the walk would not terminate, and expanding a shared subtree once per route is
> exponential on an ordinary diamond. Each is stated on the step, so neither is silent.

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
recorded and reported.

> **Amendment (2026-09-10, W52 review).** This clause read *"reported as findings"*. There is
> no `findings` table and there never was — the same discovery the usage-scenarios section
> records below for `M04-resolver.md` and `D01`. Nothing about the requirement changes: an
> unmatched outbound endpoint and an uncalled inbound one are both output. Only the word
> naming a mechanism that does not exist is gone. **Nothing is output today**: the linking tier
> that would produce these ([M05](components/M05-sync.md), [M06](components/M06-stitcher.md))
> is `planned`, so the whole requirement is unbuilt and this clause states what it WILL do.

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

*State: **partial — six questions at module scope**, built 2026-10-22 and callable in process
only (`sextant.api.query`): where a symbol is defined, what calls it, what it calls, what
implements it, what references a type, and what a change to it would affect, the last in
three parts. Still waiting, under the language gate of 2026-09-18 that was reopened for the
function alone: which symbols match a name, the routes between two symbols, which endpoint an
address belongs to, what happens when an endpoint is called, and every command-line and plugin
form. See [M09](components/M09-query.md).*

### FR-15 — Overlays

Sextant accepts overlays: statements about the graph that did not come from reading
code.

An overlay may name only symbols, endpoints, and modules that exist in the graph.
Sextant validates this before any overlay is used, and rejects the overlay otherwise.

Overlays that assert facts are applied during analysis. Overlays that affect presentation
are applied during rendering. No overlay silently overrides evidence: where an overlay
and the graph disagree, the disagreement is recorded as an open question.

### FR-16 — Curation and proposals

A person may add a curation **file** that supplies links and context the analysis cannot
derive — a claim about the world, never an edit to a fact. A curated statement is presented
to consumers as a distinct, higher-trust source beside the derived one, and the derived fact
it accompanies is never overwritten, corrected or deleted.

Where Sextant finds a candidate it will not act on alone, it writes a proposal in the form a
curation takes, so that accepting it requires review rather than transcription.

> **Amendment (W51).** The shipped text read *"A person may assert, correct, or delete a
> statement in the graph. A curated statement outranks every other source and is presented to
> consumers as proven."* That describes something this project has now ruled it will never
> build: F11's curation tier moved to phase L with M06, and the design says a format whose
> only consumer does not exist would ship a schema, an evidence tier and a no-mutation test
> with nothing that reads any of them. Correcting a false requirement is the work; the
> **wording** is what stays in v1, and this is it. What ships today is neither half — see
> `docs/COVERAGE.md` §5.18, where both this and FR-15 clause 3 are recorded `unsupported`.

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

Every command takes the form *noun, verb, subject, options*. Every result carries an exact
identifier that can be given back to Sextant.

> **Amendment (2026-09-10, W52 review).** This sentence ended *"and every command takes one"*.
> **No shipped command takes an identifier.** All four verbs take a filesystem PATH that must
> already exist — `@click.argument("path", type=click.Path(exists=True, …))` on `analyze`,
> `render`, `enrich` and `export` in `src/sextant/cli/app.py` — and `sextant.api.analyze` has
> the same signature. The first half stands and is met: results carry exact identifiers. The
> second half described the identifier-taking surface FR-20's noun-verb-subject form implies,
> which is one of the reasons [PROJECT.md](PROJECT.md) records M00 as `in-progress`. It is
> stated as the gap it is rather than left reading as shipped.

**Approximate lookup happens against the INDEX, not in the command surface.** A person who
knows a route or part of a name greps `<bundle>/index/` — `symbols.ndjson`, `addresses.ndjson`
and the six beside them — and gets back the exact identifier a command then takes. That is
where the matching belongs: the index is the artifact built for it, and a command that
resolved names itself would need a second matching rule nobody could see.

> **Amendment (W51).** The shipped clause read *"Subjects may be named approximately; where a
> name is ambiguous Sextant lists the matches and stops rather than choosing."* No command
> resolves a subject approximately, so the ambiguity rule governed nothing — it is recorded
> `unsupported` in `docs/COVERAGE.md` §5.20. The restatement is not a retreat: the capability
> a reader wanted is real and shipped in W35/W36, one layer out.

### FR-21 — Boundary vocabulary

Sextant defines a **closed, versioned boundary vocabulary** over its derived tables — the
granularity at which architecture is compared and exported. Each kind names what it is
derived from and what identifies it, so two analyses can be compared kind by kind rather than
row by row.

*State: **implemented** (2026-10-22, `boundary_vocabulary_version` 1). Seven kinds — `module`,
`endpoint`, `dependency`, `data-contract`, `boundary-property`, `schedule`, `error-handler` —
each with the columns that identify an entry, the ones that are its attributes and the ones
that are evidence; the wire is the identity and the handler is evidence. See
[D01](components/D01-graph-schema.md) §3, "The boundary vocabulary". It was tracked on
[`java-kotlin-delivery-list.md`](java-kotlin-delivery-list.md) from 2026-09-11 until built.*

### FR-22 — Derivation diff

Given two analyses of the **same module** — workspace or bundle, any mix — Sextant reports
the typed change-set in the boundary vocabulary: per kind, entries `added | removed |
changed`, with `from`/`to` attribute values on `changed`, each entry carrying evidence
pointers to the symbols and documents that ground it.

*State: **implemented at module scope** (2026-10-22): `sextant module diff` and
`sextant.api.diff`, each side a module, workspace or bundle, refusing by name where the two
analyses are not comparable and labelling a producer change it was told to allow. A
**system-scope** diff, over `links` and `participants`, is deferred. See
[M00](components/M00-cli.md). This is what the drift scenario waits on, and no longer waits.*

### FR-23 — Observability map

For any analysis, Sextant answers **per boundary kind, and per attribute where they differ:
`observable | partial | not-observable`** — derived from the manifest's gaps, the skipped
catalogs, the uncovered files, and the shipped coverage cells for the module's languages and
frameworks.

*State: **implemented** (2026-10-22). `analyze` writes `observability` into `metadata.json`,
a pure function of the measurements beside it — uncovered files, partial documents, skipped
catalogs and the kinds each would have fed, `dependency_source` — with the reasons; the
exporter copies it into the manifest, and `sextant.api.observability` answers it in process.
`KNOWN_GAPS` is listed as stated boundaries and never folded into a verdict. A skipped
catalog counts by its recorded `cause`: one skipped because its framework is absent from a
classpath the build tool resolved is not a gap (nothing to observe) and moves no verdict, while
a missing extractor capability, an absence on a `declared` classpath, and every other cause
still degrade (ruled 2026-10-22). The per-attribute
clause is met where a measurement names one (`endpoint.format`, `dependency.peer`); the
shipped coverage cells of `docs/COVERAGE.md` are not an input, because a cell describes
Sextant and the map describes this analysis. See
[D05](components/D05-manifest-and-state.md) §3.*

### FR-24 — Library embedding

Analyze, query, export and diff are callable **in-process from Python**: the CLI is a thin
wrapper over the same operations. No subprocess *required* of the caller, no global state, no
environment reads — the caller supplies configuration as an object. The enrichment step's language-model port stays a
port, so an embedding caller supplies its own.

*State: **partial** — five clauses met (one with a carve-out the requirement itself names)
and one never measured. Clause by clause, first on 2026-09-10 and amended on 2026-10-22 when
`query`, `diff` and the configuration objects landed, rather than summarised into a single
word:*

| Clause | State |
|---|---|
| the four operations are callable in-process | **met, four of the four this clause names.** It names `analyze`, `query`, `export` and `diff`, and `sextant.api` ships all four: `query` answers six module-scope questions (FR-10's partial state) and `diff` is FR-22. It also ships `render`, `enrich`, `system_analyze` and `observability` (FR-23), which this clause does not name |
| the CLI is a thin wrapper over the same operations | **met.** Each verb in `src/sextant/cli/app.py` calls into `sextant.api`. `query` has no command-line form, by the language gate on the agent query surface |
| no subprocess *required of the caller* | **met as written** — an embedding caller calls `sextant.api` in-process and shells out to nothing. **The stronger reading is false**: Sextant itself cannot run `analyze` without a subprocess — the JVM extractor is launched with `subprocess.run` (`src/sextant/ingress/extract/jvm/scanner.py:41`, `:60`), Gradle detection shells out (`ingress/detect/gradle.py:319`), `protoc` likewise (`ingress/read/proto_source.py:124`), and `api.py:389`, `:399`, `:409` run `git` for provenance. Which reading is meant matters, so both are stated |
| no global state | **not assessed here** — no measurement was taken, and saying so beats guessing |
| no environment reads | **one, and it is the carved-out one.** `src/sextant/agents/tradewind.py:343` reads an API key for the language-model adapter, which this requirement's own last sentence says an embedding caller replaces |
| the caller supplies configuration as an object | **met.** `AnalyzeOptions(allow_resolve, shadow, workspace_dir)` for `analyze` and `DiffOptions(allow_producer_change)` for `diff` carry the knobs the command line has and no others; the flag form of `analyze` stays for compatibility, and giving both is refused |

> **The wording was also strengthened in W51 and is restored.** `docs/meridian-integration.md:105`
> says *"No subprocess **required**"* — a claim about the caller not having to shell out to
> Sextant. W51 transcribed it as "No subprocess", which is a claim about Sextant not shelling
> out to anything, and that is false today. Read as written in the source it is a much weaker
> commitment, and the row above measures the stronger reading it acquired here.

> **Where these came from (W51).** `docs/meridian-integration.md` states them and is tracked
> verbatim; they were cited as requirements without being in this file, which is the same
> defect in the other direction from FR-11 … FR-14 — a commitment nobody could look up.
> They are requirements: each is a thing Sextant must DO, not a thing a consumer derives.

---

## Implementation state — FR-21 … FR-24

These four are in the [Traceability](#traceability) table at the end with every other
requirement, which is what NFR-6 depends on. This table adds only what that one does not
carry for any requirement: how much of each is built today.

| Requirement | Component | State |
|---|---|---|
| FR-21 boundary vocabulary | [D01](components/D01-graph-schema.md), [M09](components/M09-query.md) | implemented (2026-10-22) |
| FR-22 derivation diff | [M00](components/M00-cli.md), [D06](components/D06-bundle-format.md) | implemented at module scope (2026-10-22); system diff deferred |
| FR-23 observability map | [D05](components/D05-manifest-and-state.md), [M04](components/M04-resolver.md) | implemented (2026-10-22) |
| FR-24 library embedding | [M00](components/M00-cli.md), `sextant.api` | partial — FR-24's own six-row table measures each clause; five are met and "no global state" was never measured |

---

## Usage scenarios

**These are not requirements of Sextant. They are things Sextant ENABLES** — ruled by the
user, and consistent with the whole design: Sextant observes, and judgement belongs to
enrichment, curation or a downstream tool. *"Sextant can only provide the ammo, but won't be
pulling the trigger."*

They were written as FR-11 … FR-14 and read as things Sextant **reports**; they are things a
consumer **derives** from what Sextant reports. Each names the capability it waits on, so a
reader can tell "not built" from "not ours".

| | Scenario | Depends on |
|---|---|---|
| Drift | A design is generated, something implements it, Sextant derives the architecture from the **built** code, and the two are compared | FR-22's derivation diff |
| Refactor | The user reads the architecture plus `call_edges` — dependency cycles, disproportionate coupling, layering violations | `call_edges` exported (shipped, F8) |
| Design | Coupling between candidate boundaries, shapes crossing more than one — needs stitching between services | phase L |
| Performance risk | Remote hops per endpoint, an endpoint reached twice in one trace, a call inside a loop — needs cross-module call hops | phase L, plus traces |

**Three rules travelled with these four, and all three are about what Sextant may SAY rather
than what a consumer does with it — so all three survive the move.** W51 kept the first and
dropped the other two without saying so; W52 restores them.

1. **Unreachability.** A symbol is reported unreachable only where NO unresolved call site
   exists in the scope searched. Two thirds of a typical graph ends at a boundary, so this
   withholds most such findings on most modules — which is why the scenario is a consumer's
   judgement and not a row we publish.
2. **Structure, never cost.** Sextant *"does not measure, estimate, or rank by latency,
   throughput, or resource use."* It reports that an endpoint makes four remote hops; it never
   says that is slow. This rule is the reason the performance-risk scenario is a consumer's:
   the word "risk" is the consumer's to apply, and Sextant supplies only the count.
3. **The embedded schema is the one compared.** Where a generated artifact embeds the schema
   it was generated from, that embedded schema is what a comparison uses — which is what makes
   drift exact rather than approximate. This one is a live design rule, not just a scenario's:
   it is [ARCHITECTURE.md](ARCHITECTURE.md)'s DR-4 consequence, and FR-22's derivation diff
   inherits it.

*`M04-resolver.md` and `D01` asserted that the resolver computes these and that a `findings`
table is produced. Neither is true and neither ever was; both now say so.*

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
| ~~FR-11 … FR-14~~ | **Usage scenarios, not requirements** (W51) — see the section above; these four rows named [M04](components/M04-resolver.md) as satisfying them, and it computes none of them | — |
| FR-15 | Overlays | [M01](components/M01-overlay.md), [D03](components/D03-overlay-schema.md) |
| FR-16 | Curation and proposals | [M01](components/M01-overlay.md), [M06](components/M06-stitcher.md) |
| FR-17 | Coverage reporting | [M02](components/M02-detector.md), [M03](components/M03-scanner.md), [M04](components/M04-resolver.md) |
| FR-18 | Export | [M08](components/M08-exporter.md), [D06](components/D06-bundle-format.md) |
| FR-19 | Exclusion and redaction | [D04](components/D04-config-and-exclusion.md), [M03](components/M03-scanner.md) |
| FR-20 | Command surface | [M00](components/M00-cli.md) |
| FR-21 | Boundary vocabulary | [D01](components/D01-graph-schema.md), [M09](components/M09-query.md) |
| FR-22 | Derivation diff | [M00](components/M00-cli.md), [D06](components/D06-bundle-format.md) |
| FR-23 | Observability map | [D05](components/D05-manifest-and-state.md), [M04](components/M04-resolver.md) |
| FR-24 | Library embedding | [M00](components/M00-cli.md), `sextant.api` |

W51 added FR-21 … FR-24 and this table did not gain them until W52 — which is exactly the
defect NFR-6 names, a requirement with no component named. How much of each is built is in
[Implementation state](#implementation-state--fr-21--fr-24) above; this table answers only
*which component realises it*, as it does for the other sixteen.

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
