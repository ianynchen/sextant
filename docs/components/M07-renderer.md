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

> **Amendment (2026-09-02, Phase 2K design §6b — approved, delivered).** Module scope now
> writes the document TWICE — `architecture.md` (Mermaid fences, unchanged) and
> `architecture.html`, the same assembled sections through one templated HTML emitter
> (`egress/render/html.py`), self-contained and offline (a pinned, vendored `mermaid.min.js`,
> a small pan-zoom script of Sextant's own). Same workspace and overlay produce byte-identical
> bytes in both. `enrich` writes both itself as its own final step (2K design §8: "no second
> render command"); a standalone `render` over a workspace an overlay is already sitting
> beside reproduces the identical pair.

System scope: the system architecture document, the service map, cross-service sequence
diagrams, contract diagrams.

**The same set of files regardless of language, and a section with nothing to report is
present and empty** (NFR-7). An empty section says *Sextant looked and found nothing*; an
absent one says *unknown*, and an agent cannot tell those apart.

## Behaviour

### The module document blueprint

`architecture.md`'s target structure, agreed with the user. Every target section is named
here; each is either derived now or carries its gap by name:

| Section | Source | Status in 2B |
|---|---|---|
| Overview | module id, coverage, commit | shipped (polish) |
| Structure — contract class diagram | `shapes`/`shape_fields`; nodes are payload types with wire fields, edges are `shape_id` references | **built in 2B** (Mermaid `classDiagram`) |
| Structure — full class diagram (inheritance) | `inherits`/`implements` edges — table does not exist | named gap; call-graph phase |
| Inbound endpoints — contract field tables per endpoint | endpoints + descriptors + shapes | **built in 2B** |
| Traces — one rendered trace and one sequence diagram per ROOT | `roots`, `call_edges`, `return_flows` through `application/query/trace.py`, handed to `assemble_module_document(traces=…)` | **built in 2Q** (`## Traces`; Mermaid `sequenceDiagram`). The gap `sequence_diagrams_pending_call_graph` retired by name, and so did `call_graph_not_implemented` |
| Outbound endpoints | 2B's rows | **built in 2B** |
| Components, descriptions, algorithm design, extension guides | LLM-authored via overlay, `evidence: llm` | **delivered, 2K** — not via M01: `.sextant-enrichment.json` ([D04](D04-config-and-exclusion.md) §4b, [ARCHITECTURE.md](../ARCHITECTURE.md) DR-2's amendment), a closed, pydantic-validated claim schema `enrich` writes and this renderer's own assembly (`egress/render/document.py`) interleaves at fixed anchors, never through M01's `Overlay` port |

**A section whose machinery does not exist is never rendered empty.** It is named as a gap
instead — the same NFR-7 corollary the rest of this document argues from: an empty section
reads as *Sextant looked and found nothing*, which is a false claim when the underlying
capability was never built. A gap says *not yet*; only an empty section is permitted to say
*looked, found nothing*.

### What the shipped trace section does, and the two designs below it that are NOT applied

Recorded here rather than left for a reader to infer from the absence of code (§5.3): the
2Q rendering is deliberately the plainest thing the walk supports, and the two sections
that follow describe machinery it does not use.

- **Per ROOT, not per endpoint — and NAMED by the addresses that reach it.** A root is a
  method: an inbound endpoint handler or a scheduled one, so a scheduled job gets a trace
  and a diagram on the user's own ruling, and a handler serving three paths is one trace
  rather than three copies of it. Every address that reaches it is on the summary row and
  in the block header, because the address is the only name a reader has for the trace they
  came to find — a section searchable only by handler descriptor is one a reader cannot
  navigate. **The address arrives as data**: `roots` carries it ([D01](D01-graph-schema.md)
  §3, as of 2Q's close), and re-making that join here would be the renderer deriving. A
  root nothing addresses says `no wire address`, never the em dash this document uses for
  "nothing recorded".
- **No noise filtering at all** (the table below). Every step of the walk is a row and an
  arrow — accessors, `toString`, third-party calls included. The filters are designed and
  cheap, and the reason they are not applied is that a hidden call is indistinguishable
  from a call that does not exist, and this is the first document in which anyone reads a
  trace. A `view` overlay choosing what to hide is a decision a person makes about their
  own module; the machine half does not make it for them.
- **Every trace, every diagram, by default** ([GUIDELINES](../../GUIDELINES.md) §8.4, ruled
  2026-09-06). All 160 of `mall-admin`'s traces are drawn: a 711 KB `architecture.md` and a
  4.6 MB `architecture.html` with 161 diagrams, for one module. That was briefly bounded to
  37 traces by default and the ruling reversed it — *"we should be focused on telling the
  truth, not the amount of information"* — because a document too large to read linearly is
  a **navigation** problem, answered by indices and by the agents that read it, never by
  leaving 123 walked traces undrawn for a reader who cannot see they are missing.
  **The bound survived one day as `render --brief`'s and is now gone entirely** — *"deleting
  that --brief if it only cuts the first N. that's same as lying"*. It drew whole traces
  while a 500-step budget lasted, taken in the summary table's own order, and order was
  chosen precisely because it claims nothing: drawing the cheap traces first would answer
  "which traces matter" with a judgement this renderer has no basis for. But a rule that
  claims nothing selects nothing either — what it produced was an arbitrary **prefix** of
  the section, and the three properties that made it careful (every trace keeps its summary
  row; a trace is drawn whole or not at all; the section said it was the brief one, how
  many of how many, and the command that drew them all) made the omission honest without
  making the prefix a summary. A trimmed document is enrichment work, an LLM overlay, and
  not a render flag. **`## Traces` now takes no bound**, and the sentence under the summary
  table states the count drawn and the count walked, which are the same count.
- **No `alt`/`opt`/`loop` blocks** (the section after it). The structure is not in the
  facts: [D00](D00-fact-schema.md) §5 states that `call_site.ordinal` is *the v1 of the
  control-flow position* and *"not the richer context a sequence diagram needs to show a
  `loop` or an `alt` without lying about it"*, with the enrichment priced as a later
  re-extraction. So the diagram is flat — and it says so, in every diagram's own
  `Elides:` line and in the section's preamble, because a flat diagram that does not admit
  it is the lying diagram §8 forbids. **The statement is the mitigation, not an excuse:
  the honest close is the richer field.**
- **The elision is stated per diagram, counted from that trace.** `MachineDiagram.elides`
  carries it, exactly as `DiagramClaim.elides` carries a model's — same field, same
  `Elides:` prefix, same caption in HTML. A trace diagram is simplified by construction (it
  draws no lifeline for a body the walk never entered and no subtree for a method expanded
  elsewhere), so the statement is not optional on any of them.

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

**None of them run as of 2Q.** The section above says why: the first document anyone reads
a trace in is the wrong place to start hiding calls, because a hidden call and an absent
call are the same bytes to a reader. Every rule here still holds; each needs a way for the
diagram to SAY it fired, which is what `MachineDiagram.elides` now provides.

### Control flow is rendered, not flattened

`alt`, `opt` and `loop` blocks come from the control-flow position on each trace step. Four
calls listed in order, two of which are branches of one `if`, is the lying diagram
`GUIDELINES.md` §8 forbids.

Where [M03](M03-scanner.md) could not structure a region, the steps render sequentially and
**the diagram says the structure was not recovered**.

**As of 2Q that is every region.** `call_site.ordinal` is instruction order and nothing
more ([D00](D00-fact-schema.md) §5), so the shipped diagram renders every step
sequentially and says the structure was not recovered — the second half of this rule
carrying the whole of it until the field is enriched.

### Two things no filter and no overlay may hide

Terminals of kind `unresolved` and `cycle` are always drawn. They are the places a person
must look, and hiding them makes a diagram look complete when it is not.

### Environment is a display choice at module scope, fixed at system scope

Endpoints carry expressions; values are per-environment. At module scope, `render --env
prod` selects which resolutions the document shows; **without the flag, the document shows
the expression and every resolution side by side**. Either way, the document states which it
is showing — a catalog silently showing development values is a lying document. At system
scope there is no choice: the system's declared environment is used, and named.

### A conditional bean's rows are rendered in words, from its tables

`bean_conditions`, `bean_presence` and `candidate_presence` (D01, "Conditional beans") are the
structured result; the documents are their one verbose rendering (spec
`2026-10-22-conditional-beans-design.md` §3, generalizing PR #61's ruling for inbound
endpoints). One index is built from them once, and **every row derived from a conditional
bean** — inbound and outbound endpoints, scheduled jobs, error handlers — finds its bean
through `symbol_beans` and states what is there; no kind has its own copy of the logic. An
unconditional row gains nothing, and the tables' columns are unchanged: a condition is a fact
about where the row exists, not a column every unconditional row would carry empty.

**A row's detail block gains two lines (the first is a small table for a bean with several routes):**

* *Exists only when: …* where the bean has ONE registration route — its conditions joined by
  "and" (a bean whose single route is `@Profile("prod")` and `@ConditionalOnProperty(…)` is
  one sentence, not PR #61's pair of lines: presence belongs to the bean).
  *Exists when any of these registers it* where it has SEVERAL, with a two-column table
  (*Registered by*, *Registers it when*), one row per route. An unconditional route reads
  *always*; a plain `new` outside any factory reads *constructed outside any bean factory —
  not decided*; an inherited body no bean runs reads *no bean of this module runs this
  inherited body — not decided*.
* *Of this module's environments: holds in 1 of 2 environments — not in `default`*, read from
  `bean_presence` alone. An environment left open says why, in words: *not evaluated in
  `default`, `github` — the active profiles here come from `${apollo_profile}`, which this
  module does not fill*. A bean open in every environment reads *not evaluated by this
  analysis in any of the N environments*, then its reason. A condition this analysis does not
  evaluate is named (`@Conditional`), never quoted as JSON.
* A `@ConditionalOnMissingBean` / `@ConditionalOnBean` condition reads *no other bean of type
  `UserService` is registered — decided from this module's beans only (`partial`); the other
  beans of that type: `LdapUserService` (not in any environment; profile `ldap` is named but
  this module has no `ldap` environment)*. The competitors are the module's other beans the
  condition matches, each with where it exists. The competitor JSON the evidence carries is
  never printed.

**A call site's candidates, per environment.** Under a narrowed call in a trace block, and
under a call a framework-generated implementation answers, the block states the site and every
candidate (*`NotifyController#notify` calls `NotificationSender#send`, answered by one of:
`KafkaNotificationSender`, `LogNotificationSender`*), then one line per group of environments
naming the candidates that exist there (*in `default`: `LogNotificationSender`*; *in `prod`:
`KafkaNotificationSender`*), then *not evaluated in `h2`: …* for candidates open there, with
the reason. Environments with the same list share a line; where no candidate exists the line
says *none of them*. A line that names a `partial` candidate, or leaves one out because a
`partial` verdict ruled it out, says *(decided from this module's beans only)*. A reason that
every candidate on a line shares is said once after them; a framework-generated
implementation reads *a framework-generated implementation of `SpringDataOwnerRepository`*.
**Where every candidate of a site holds in every environment, decided**, the block carries the
*answered by* line alone: an unconditional repository would otherwise repeat one line per
environment. Nothing is dropped: the step table and the diagram show every candidate, as
before, and a narrowed site none of whose candidates is conditional renders byte for byte as it
did.

**The system document** states where each end of a link exists, read through the federated
views (M06): *exists in `prod`; not in `default`* beside the inbound endpoint and *called only
in `prod`; not in `default`* beside the calling side.

### Every reduced output states that it was reduced

A simplified diagram says how many steps were hidden. A truncated list says how many were
omitted. A diagram derived from a partial analysis says so.

**The trace section is the live instance, and it now states a reduction of zero.** Under
the summary table it says how many traces it drew of how many were walked — the same
number, because nothing bounds it — so a reader meets the boundary question and gets an
answer rather than a silence. The rule that makes the sentence necessary is the same one
that makes an `Elides:` caption necessary: a reduced output that does not say it was
reduced is indistinguishable from a complete one, and so is a complete one that says
nothing.

**The reduced form of this section is deleted, not tuned.** `render --brief` drew the first
traces in table order, and *"deleting that --brief if it only cuts the first N. that's same
as lying"* is the ruling that removed it — a prefix is not a summary, whatever it says
about itself.

**And stating it is not a licence to reduce by default** ([GUIDELINES](../../GUIDELINES.md)
§8.4). This section's own defect was exactly that inference: the omission WAS stated, three
ways, and the default was still wrong, because the reader who has to be told is the one who
never chose. A statement makes a reduction honest; it does not make it a default.

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
| How deep a system chain renders before it becomes unreadable, and what says so | — |
| The exact grouping rule for many operations on one address — [D01](D01-graph-schema.md) requires grouping by `path` by default; the shape of the opt-out is undecided | System scope |
