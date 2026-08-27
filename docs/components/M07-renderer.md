# M07 — Renderer

## Purpose

Turn a graph scope into diagrams and documents.

One module serves both scopes. The reason is that a sequence diagram generator needs
participants, ordered messages and nesting — and **it does not care whether a participant is
a class or a service.**

## Shape

```
   module trace   ──► projection ──┐
                                   ├──► view model ──► emitter ──► Mermaid
   system chain   ──► projection ──┘
```

| Part | Job | Scope-specific |
|---|---|---|
| **Projection** | Turn a graph scope into a view model | **Yes** |
| **View model** | Participants, messages, nesting; nodes, fields, relations | No |
| **Emitter** | View model to Mermaid | No |
| **Document template** | Assemble sections around the diagrams | **Yes** |

**The testing payoff is the real argument for this split.** The emitter is tested against a
hand-written view model — no workspace, no facts, no database. Diagram correctness stops
depending on having a repository to analyse.

The view model is internal. Nothing outside this module reads it, so it is not a `D`
document.

## Interface

```
Renderer
  render(scope, workspace, claims) -> [Document]

Projection
  accepts(scope_kind) -> bool
  project(scope, workspace) -> ViewModel
```

## Inputs

The graph ([D01](D01-graph-schema.md)) at module or system scope. Presentation claims from
[M01](M01-overlay.md). Coverage from [M02](M02-detector.md), [M03](M03-scanner.md) and
[M04](M04-resolver.md).

## Output

Module scope: the module architecture document, class diagrams, sequence diagrams.
(`metadata.json` is **not** written here — `analyze` stamps it, per
[D05](D05-manifest-and-state.md), so it can never be absent or stale when only analysis
ran.)

System scope: the system architecture document, the service map, cross-service sequence
diagrams, contract diagrams.

**The same set of files regardless of language, and a section with nothing to report is
present and empty** (NFR-7). An empty section says *Sextant looked and found nothing*; an
absent one says *unknown*, and an agent cannot tell those apart.

## Behaviour

### Cross-service sequence diagrams need no new machinery

[M04](M04-resolver.md) ends each trace at a classified terminal; one kind is
`outbound_call`. [M06](M06-stitcher.md) matches an outbound endpoint to an inbound endpoint
— and an inbound endpoint is what a trace starts from.

**The terminal of one trace and the root of the next are the same join.** The system
projection chains traces at their terminals and hides the interior.

Two consequences to handle rather than discover:

- A chain may revisit a participant, so **cycle detection applies at system scope** exactly
  as it does within a trace.
- A terminal whose link is `narrowed` continues into **several branches**, rendered as
  alternatives rather than as one path.

### Noise filtering is deterministic, and comes before any model

Most of what makes a raw sequence diagram unreadable is removable by rule:

| Rule | Basis |
|---|---|
| Hide members marked as generated | An annotation already in the bytecode |
| Hide accessors and record accessors | Name and shape |
| Hide `toString`, `equals`, `hashCode` | A fixed list |
| Hide calls to symbols of third-party **origin** | The tier recorded on the symbol's document at extraction — never a package-name pattern, which shading makes silently wrong |
| Collapse repeated consecutive calls to one participant, with a count | Trace shape |

These are testable, stable and free. **What genuinely needs judgement is the leftover** —
which first-party participants carry the story — and that is what a `view` overlay supplies.

### Control flow is rendered, not flattened

`alt`, `opt` and `loop` blocks come from the control-flow position on each trace step. Four
calls listed in order, two of which are branches of one `if`, is the lying diagram
`GUIDELINES.md` §8 forbids.

Where [M03](M03-scanner.md) could not structure a region, the steps render sequentially and
**the diagram says the structure was not recovered**.

### Two things no filter and no overlay may hide

Terminals of kind `unresolved` and `cycle` are always drawn. They are the places a person
must look, and hiding them makes a diagram look complete when it is not.

### Environment is a display choice at module scope, fixed at system scope

Endpoints carry expressions; values are per-environment. At module scope, `render --env
prod` selects which resolutions the document shows; **without the flag, the document shows
the expression and every resolution side by side**. Either way, the document states which it
is showing — a catalog silently showing development values is a lying document. At system
scope there is no choice: the system's declared environment is used, and named.

### Every reduced output states that it was reduced

A simplified diagram says how many steps were hidden. A truncated list says how many were
omitted. A diagram derived from a partial analysis says so.

### The renderer adds nothing

Every participant and every message comes from a graph row. An overlay says what to *show*,
never what happened — which is why a model cannot put a call on a diagram that does not
exist.

## What it must not do

- **No derivation.** If a number is computed here, [M09](M09-query.md) cannot serve it and
  the two will disagree.
- **No workspace writes** beyond its own output.
- **No prose of its own.** Purposes arrive as overlays or are absent.
- **No silent omission.** Section 5 of the behaviour, restated as a prohibition.
- **No scope-specific emitter.** If the emitter needs to know which scope it is in, the
  projection did too little.

## Honesty obligations

- Coverage, partial status and resolution counts on every document.
- Known gaps, named — a catalog that cannot be complete must not read as complete.
- Steps hidden, and by which rule.
- Regions rendered flat because control flow could not be recovered.
- Where a diagram was cut by a system-scope cycle.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether `metadata.json` lists endpoints in full below some count, or always as counts | [D05](D05-manifest-and-state.md) |
| Whether a `view` overlay may apply to a class diagram as well as a trace | [D03](D03-overlay-schema.md) |
| Whether the document is Markdown, HTML, or both | — |
| How deep a system chain renders before it becomes unreadable, and what says so | System scope |
