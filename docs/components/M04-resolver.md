# M04 — Resolver

## Purpose

Turn facts into a graph.

The largest module, because everything between "what was observed" and "what can be
rendered" happens here — and none of it knows a language exists.

## Interface

```
Resolver
  resolve(workspace, model, catalogs, overlays) -> ResolveReport
```

One implementation. Its internals are staged, but the stages are private — they are not
plug-in points and not commands.

**Where the code lives.** The resolver is `application/resolve` — core computation, not an
adapter. It talks to the workspace only through the `Workspace` port; the SQL bodies of the
named derivations it orchestrates live in `storage/duckdb` as the implementation of
[D01](D01-graph-schema.md). The semantics and the ordering are owned here; the dialect is
owned there.

The module is **language-blind by construction**: it reads facts and catalogs, and branches
on capabilities, never on names. An architecture test asserts that no language name appears
in it.

## Inputs

Facts from [M03](M03-scanner.md). The `RepositoryModel` from [M02](M02-detector.md).
Catalogs ([D02](D02-catalog-schema.md)). Claims from [M01](M01-overlay.md).

## Output

Every derived table in [D01](D01-graph-schema.md), and a report of what could not be
resolved. As its final act, `analyze` writes `metadata.json`
([D05](D05-manifest-and-state.md)) — the workspace's self-description, stamped by the
pipeline that computed it so an agent never finds it absent or describing a previous graph.

## Behaviour

Six passes, in order. Each reads what the previous produced.

### 1. Load

Facts into the workspace, **in bulk**. Per-row insertion across a fact set is a defect
(NFR-11): the difference is orders of magnitude — minutes against seconds on a real fact
set.

Only changed documents are reloaded, by delete and reinsert on `document_id`. Everything
after this pass is **rebuilt whole** — a derived row is a join across files, and adding one
implementation of an interface invalidates dispatch edges in files that did not change.

### 2. Configuration resolution

**Every profile found, not one.** A module analysis is not tied to an environment — the
expensive work before and after this pass is identical across all of them, so resolving each
profile once is the only sensible arrangement. `resolved_config` carries an environment
column; consumers select.

Layer configuration by profile, then resolve placeholders, including placeholders whose
values contain further placeholders.

**Endpoints keep the expression, not the value.** A listener on `${orders.topic}` stores that
expression; what it resolves to in each environment lives here. Only hosts and topic names
vary by environment — protocol, path template, gRPC method and payload shapes come from code
and do not — so making the whole endpoint environment-scoped would over-react to a variation
touching two fields.

A key that cannot be resolved is recorded as unresolved **with a reason and an environment**.
*Unresolved for `prod`, resolved for `dev`* says the profile is incomplete; a bare
"unresolved" suggests the code is unreadable. And a value that was redacted is a different
reason from a value that is missing, or somebody goes looking for a setting that is there.

### 3. Symbol graph

Intern identifiers, build containment and its closure, build the type hierarchy, and
materialise the edge kinds [D01](D01-graph-schema.md) keeps.

The four type-reference edge kinds are built here — a substantial fraction of the graph,
kept deliberately. They exist for blast radius, which is on the requirement list; they are
exactly the kinds a diagrams-only tool would drop as unused.

### 4. Dispatch resolution

For each call site, the set of method bodies that could run.

| Opcode | Result |
|---|---|
| Static, constructor, private, super | Exactly one target |
| Virtual or interface | Every non-abstract subtype of the owner declaring a matching method |

Then narrowed by **rapid type analysis**: a candidate survives only if the program creates
an instance of that type somewhere. This removes a large part of the noise for about a
hundred lines. **In version 1, by sign-off 2026-08-27** — added from the start rather than
after the graph becomes unreadable.

**VTA — variable type analysis — is the recorded next tier**, deferred from version 1 but
expected to be needed: it narrows per call site by what can actually flow to the receiver,
removing RTA's one-`new`-anywhere-keeps-it-everywhere imprecision. Two things make the
upgrade cheap when it comes: the candidate-set shape in [D01](D01-graph-schema.md) is
already per-call-site, so VTA changes the contents of `dispatch` rows and nothing
downstream; and Go's toolchain ships VTA natively, so language two will exercise the shape
before the JVM implementation exists.

**The tier follows from the indexed boundary, not from judgement.** If nothing outside the
indexed set can extend or implement the type, the set is complete — `narrowed`. If the type
is visible outside it, `partial`. The boundary is [M02](M02-detector.md)'s classpath
tiering, which is why that tiering is load-bearing rather than an optimisation.

The tier lives on the **call site**. It says how much is known about the call; it does not
rank candidates.

Java's own resolution rules have to be respected: the superclass chain before interface
default methods, bridge methods so a generic override is not missed, package-private
methods overridden only within a package.

### 5. Endpoints, in two halves

**The halves exist because shapes and endpoints depend on each other**, and the naive
ordering deadlocks: a shape is a type that crosses a boundary, so you cannot know which
types are shapes until endpoints are found — but an endpoint is not complete until its
shapes are attached.

**5a. Find the boundaries.** Catalog engines run in a fixed order: inbound, then outbound,
then reclassification. Inbound precedes outbound so that a path a module both exposes and
calls merges into one endpoint with direction `both` rather than appearing twice. Each
endpoint records its protocol, wire identity, handler or caller, and the **type references**
of its request and response — not yet their contents.

**Every catalog whose required capabilities are unmet is skipped and reported.** This is the
mechanism that keeps a weaker scanner visible instead of silently producing a shorter
catalog.

**5b. Expand the shapes**, rooted at exactly those type references — after **unwrapping
envelopes by catalog rule** ([D02](D02-catalog-schema.md) §2a): `Mono<ResponseEntity<T>>`
roots at `T`, and the `semantics` peeled on the way there (`async`, `optional`,
`http_envelope`) are what settle presence, protocol reclassification and the FR-14 findings.
That chain is consumed where it is produced rather than stored on the endpoint: it describes
the route to the payload, not the contract, and everything it decides already has a column of
its own — a second copy could only ever disagree with them. An undeclared wrapper is left
unwrapped and reported, never guessed at. Fields resolved to **wire identity** — the
serialised name after any naming strategy or explicit annotation, or the field number where
the format makes a number the identity. **Required-ness comes from presence machinery and
from nothing else** ([D00](D00-fact-schema.md) §5b): a wrapper the catalog declares
`optional` is what makes a field omittable. A nullability annotation answers the other
question — Bean Validation's `@NotNull` constrains the value at validation time and says
nothing about whether the field may be absent — so reading one as a presence rule publishes a
`required` nobody declared. Expansion follows nested types transitively, and stops at
platform types.

Where a format publishes compatibility rules, those rules are applied rather than
reimplemented. A hand-rolled approximation would disagree with what the runtime actually
does, which is worse than not answering.

**5c. Attach** each shape to the endpoint that rooted it.

Rooting expansion at boundary types rather than expanding everything also bounds the cost: a
service has tens of contracts and thousands of types.

### 6. Trace summaries and findings

Traces are **not materialised** — the named query `trace_of` computes each walk on demand
([D01](D01-graph-schema.md)), because storing traces would copy every shared subtree once
per endpoint that reaches it. What this pass builds is `trace_summary`: one row per inbound
endpoint with hop counts, services involved, terminal counts by kind, and endpoints reached
more than once — the numbers findings need without walking everything. It also denormalises
each call site's control-flow position onto its `calls` edge, which is what lets the walk
run from the graph alone.

**Every terminal kind has a named producer.** `outbound_call` from the endpoint engines;
`returns` and `ends_silently` from the method descriptor; `unresolved` from dispatch;
`cycle` from the walk; `persistence` and `async_handoff` from **catalog classifications**
([D02](D02-catalog-schema.md) §2b), applied here to call sites; `throws` from the scanner's
throw-site facts. A terminal with no producer would be a decorative enum value — the audit
that added this sentence found three.

**No depth bound.** A trace is a subgraph, so its size grows with the code reached, not with
branching. It stops at a terminal — and `cycle` is a terminal detected during the walk, a
correctness requirement rather than a limit.

Findings are computed here rather than in the renderer, so [M09](M09-query.md) can serve
them too. Refactor findings, design findings, and structural performance risk — hop counts,
services involved, an endpoint reached twice in one trace, a persistence call inside a loop.

**A symbol is reported unreachable only where no `unresolved` call site exists in the scope
searched.** Otherwise the finding is withheld and the unresolved site reported instead. A
dead-code claim is the most dangerous output on the list, because acting on it deletes
something.

## What it must not do

- **No code.** Facts are the only input describing a codebase.
- **No language names.** Enforced by test.
- **No framework logic.** Engines interpret catalogs; a framework name never appears in
  code here.
- **No prose.** Names and purposes are overlays applied at render.
- **No materialised blast radius.** It is a query.
- **No patching of derived tables.** Rebuild whole.

## Honesty obligations

- Counts by resolution tier, which are how much of this graph to trust.
- Every catalog skipped, and the capability that was missing.
- Configuration keys unresolved, distinguishing redacted from missing.
- Call sites `unresolved`, grouped by reason — and `unindexed_dependency` reported
  separately, because it is the only reason fixable with a setting.
- Findings withheld because of unresolved sites in scope.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether findings is one table with a kind column or one per family | [D01](D01-graph-schema.md) |
| How a trace crossing an `async_handoff` is recorded — stop, or continue on the other side | FR-6 |
| Whether shape extraction follows types into third-party signatures without limit | Graph size |
