# codetospec compared with Sextant

Research date: 2026-09-18. Sextant snapshot: `36c1d26` (`main`, after PR #27).
codetospec snapshot: `main` as of its last push, 2026-07-15.

The question this answers: can Sextant leverage codetospec's ideas to generate business
rules, logic and algorithms from code?

## Disambiguation

This comparison uses [edouard-claude/codetospec](https://github.com/edouard-claude/codetospec)
— Go, MIT, ~9,500 lines, one author, created 2026-07-08, last pushed 2026-07-15, three
stars, self-described v0.1. It is the only project under that name whose subject is
business rules. GitHub search also surfaces
[LucivHuang/CodeSpec](https://github.com/LucivHuang/CodeSpec) (a spec-driven-development
workflow plugin, unrelated), and several `code-to-spec` repositories that generate OpenAPI
documents or reverse-engineer implementation specs; none extract rules.

## Honest verdict

codetospec and Sextant share a trust philosophy and own different halves of the problem:

- **codetospec produces a rule artifact.** It chunks source with tree-sitter, asks a model
  for candidate business rules in EARS form (`WHEN <trigger>, the system shall
  <response>`), constrains every rule to cite `path:lines` inside the chunk it came from,
  deduplicates per domain, has a second fresh-context model try to refute each rule, and
  re-checks every citation deterministically before anything is written. It has run on
  real legacy code and written down what broke.
- **Sextant produces the facts codetospec lacks.** It reads bytecode, so it has resolved
  call sites with `invoke_kind` (including `throw`) and `control_flow_kind`
  ([D00 §4](../components/D00-fact-schema.md)), dispatch resolution, payload shapes, catalog-derived
  endpoints, and traces from every inbound root to every terminal
  ([CONTEXT.md:74](../../CONTEXT.md), [CONTEXT.md:101](../../CONTEXT.md)). codetospec's "anchors" are
  symbols, routes and tables; it has no call graph and no data flow.

Sextant's overlay contract already states codetospec's trust model more rigorously than
codetospec does — overlays may name only things that exist and are otherwise **rejected
whole** ([M01:39](../components/M01-overlay.md)), model claims attach at rank 10 and never override
a fact ([M01:74-76](../components/M01-overlay.md)), and the word "confidence" is banned
([CONTEXT.md:120](../../CONTEXT.md)). What codetospec adds is a **rule** artifact with a
validated grammar and the verification machinery around it: citation constraints at every
stage, an adversarial reviewer, citation repair, and a stale-check. Those are borrowable as
designs, not as code — codetospec is Go with CGo, a one-week v0.1, and not a dependency
anyone should take.

The strongest opportunity is not to copy codetospec's per-chunk map. It is to use what
Sextant already has and codetospec does not — traces and their terminals — as the
deterministic candidate sites for rules, and to give the rules the overlay treatment
every other model output already gets.

## What codetospec does

```
extract ──▶ chunk ──▶ map ──▶ reduce ──▶ crosscheck (+repair) ──▶ build ──▶ digest ──▶ verify ──▶ render
[deterministic]        [LLM, gated]       [LLM, gated]              [all deterministic]
```

1. **extract** — two deterministic fact sources. tree-sitter with one declarative `.scm`
   query per language (PHP, Go, JavaScript, TypeScript/TSX, Rust ship) yields
   definitions, modules and imports. External extractor executables speaking a small JSON
   protocol (`kind: symbol|route|table|module|import`, `source: {path, lines}`,
   `certainty: static|proved`) add ecosystem facts — three ship: Laravel routes and
   schema, Go gin/echo/chi routes plus SQL tables, and a SCIP converter for precise symbol
   spans. Facts merge by id with priority `proved > extractor > tree-sitter`
   ([README](https://github.com/edouard-claude/codetospec#extractor-protocol-facts-v1)).
2. **chunk** — one top-level definition per chunk when it fits in 300 lines; larger
   containers split per method with the class header prepended as non-citable CONTEXT;
   files without a grammar fall back to 250-line windows with 20 lines of overlap
   (`internal/sitter/chunk.go`). Domain is a namespace segment, depth configurable.
3. **map** — one model call per chunk, in a worker pool. The prompt prefixes **every code
   line with its absolute line number**, lists the allowed entity and endpoint ids for
   that file, and — with a SCIP index — the exact spans of the symbols in the chunk.
   Output is JSON: `ears_kind`, `requirement`, `citations`, `entities ⊆ ALLOWED`,
   `endpoints ⊆ ALLOWED`, `nature: business|presentation|technical`,
   `origin: explicit|implicit`, `confidence`. A validator rejects a reply whose citation
   falls outside the chunk, names an unknown entity, or breaks an enum; the exact error is
   fed back, twice at most, then the chunk is marked failed and the run continues
   (`internal/mapper/mapper.go`).
4. **reduce** — one model call per domain deduplicates candidates and writes two to five
   acceptance criteria per rule. Citations **must appear verbatim among the candidates**;
   the model cannot invent or alter one. Domains above 30 candidates are reduced in
   batches and merged deterministically; a batch whose JSON truncates is split in half and
   retried down to a floor of five (`internal/reducer/reducer.go`).
5. **crosscheck** (optional) — a fresh-context model receives only the rule and the lines
   it cites, marked `>`, with ten lines of `·` context each side, and votes
   `supported | partial | unsupported`. A disputed rule stays in the graph, flagged
   (`internal/crosscheck/crosscheck.go`).
6. **repair** (optional, needs SCIP) — an `unsupported` rule gets one chance to re-cite;
   the new span is accepted only if it mechanically overlaps a real symbol body.
7. **build / verify / render** — pure Go: unique ids, resolvable edges, citations that fit
   real files, frontmatter round-trip; nothing is written unless verify passes. Domain
   `depends_on` edges come from import facts crossing domain boundaries, never from the
   model. Output is `nodes/{domains,entities,endpoints,rules}/*.md` with YAML
   frontmatter, `graph.json`, `llms.txt`, and a README with coverage and a Mermaid domain
   graph.
8. **drift** — each rule stores a SHA-256 of its cited lines; `codetospec drift` recomputes
   them and reports `ok | stale | broken`, exits 1 on drift, and emits JSON for CI
   (`internal/drift/drift.go`).

Runs are resumable through a per-unit content-hashed cache and byte-deterministic on a warm
cache. Token usage is tracked per phase; the README's sample run is 1.6M input and 450k
output tokens.

### The findings that are worth more than the code

[docs/03-failure-modes.md](https://github.com/edouard-claude/codetospec/blob/main/docs/03-failure-modes.md)
records what broke on real runs. Five of its findings bear directly on any rule extraction
Sextant would build:

- **The line-number trap.** Sending a chunk headed `lines 659–1548` with un-numbered code
  makes the model *count* lines, and it under-counts with depth. The reviewer then
  correctly rejects true rules for wrong citations, and the quality metric lies. Prefixing
  every line with its absolute number turned ~500 "unsupported" rules back to supported on
  one real run. Their rule: *if the model has to compute a coordinate you could have given
  it, give it.*
- **Citations are constrained by construction at every stage** — inside the chunk at map,
  verbatim-from-candidates at reduce, overlapping a symbol body at repair. Never checked
  afterwards; always impossible to be otherwise.
- **Model-reported confidence carries no signal** — every rule on a real run scored ≥ 0.9.
  `explicit/implicit` degenerates to ~99% explicit. The signals that discriminate are
  `nature` and the adversarial verdict. *"A field you added is not a signal until you've
  measured its distribution."*
- **Over-extraction is the default failure.** Hundreds of "the system shall return `$this`
  for chaining." The `nature` classification exists to deliver the ~100 business rules out
  of 700 candidates, not to drop the other 600.
- **Do not cache verdicts by cited-code digest.** Two different rules citing the same span
  may legitimately receive different verdicts.

Its own stated limits ([docs/05-limits.md](https://github.com/edouard-claude/codetospec/blob/main/docs/05-limits.md)):
structural coherence is 100% (every citation resolves), semantic coherence "lands well
short of 100%" (the cited lines actually prove the rule), and **completeness is not
measured** — the tool reports what it found, not how much business code has no rule
attached.

## Side-by-side

| Dimension | codetospec | Sextant | Assessment |
| --- | --- | --- | --- |
| What it produces | Rule nodes in EARS with citations, plus domain, entity and endpoint nodes; markdown graph, `graph.json`, `llms.txt`. | A queryable model of boundaries, shapes, calls and traces; markdown and HTML documents; export bundle; typed Python API. Model prose arrives as four overlay claim kinds — `component`, `section`, `diagram`, `verdict` (`src/sextant/enrich/INSTRUCTIONS.md:137-197`). | codetospec has a rule artifact; Sextant has none. Sextant's `section` kind already names "an algorithm description" as a purpose (`INSTRUCTIONS.md:156`). |
| Input | Source text via tree-sitter; optional external extractors and a SCIP index. | Compiled classes, build metadata, configuration, schemas, framework catalogs; the enrich agent reads source through jailed `find`/`grep`/`read_file` tools. | codetospec works on any source tree, including ones that do not build. Sextant needs a build and is Java/Kotlin today. |
| Deterministic anchors | Symbols, routes, tables, imports. No call graph, no control flow, no dispatch. | Symbols with bytecode line extents ([D00 §5a](../components/D00-fact-schema.md), line 456), call sites with `invoke_kind` including `throw`, `control_flow_kind` (line 320), resolved dispatch, traces with typed terminals ([D01 §3](../components/D01-graph-schema.md)). | Sextant's anchors are an order of magnitude richer. A `throw` under a `conditional` is where a validation rule lives; codetospec has to find that by reading. |
| Unit of model work | One chunk (a definition, or 250 lines). Rules for one behaviour scatter across controller, service and model chunks and are reassembled by a second model call. | Not applicable today — enrich is one agentic session per module. A trace from one inbound endpoint to its terminals is the natural unit for "what governs this operation". | Sextant can scope rule extraction to a trace and bound the number of model calls by candidate sites, not lines of code. |
| Citation grounding | Inside the chunk (map); verbatim from candidates (reduce); overlapping a SCIP symbol body (repair). | `cites` on a `section` must be a real file under the module; `members` must be known symbols; nothing checks a line range yet. | Sextant can check a cited range against a symbol's `line_start..line_end` from the class file — codetospec's SCIP repair check, with no indexer. |
| Semantic check | Fresh-context adversarial reviewer per rule; verdict recorded, never dropped. | `verdict` claims answer open questions with `because` or an honest `unanswered` and `searched` (`INSTRUCTIONS.md:197`). No second pass reviews first-pass claims. | Sextant's `verdict` shape is most of a refutation pass already. |
| Staleness | SHA-256 of cited lines per rule; `drift` command; CI exit code. | `content_hash` on components regenerates prose only when the graph slice changed ([D03 §5](../components/D03-overlay-schema.md), line 143). No digest over cited source. | Small extension. Note Sextant's **Drift** already means declared-contract-versus-implemented ([CONTEXT.md:156](../../CONTEXT.md)); this needs a different word. |
| Scoring | `confidence` in [0,1] from the model, which its author measured as noise; `nature`; `origin`. | Three separate trust properties — resolution, evidence, precedence — and "confidence" banned by name ([CONTEXT.md:120-137](../../CONTEXT.md)). | Sextant's position is the one codetospec's own measurements argue for. |
| Domains | A namespace segment, depth configurable; import-derived `depends_on` edges. | Components are judgements with listed membership changes, never structural ([CONTEXT.md](../../CONTEXT.md) "Component"; [D03 §5](../components/D03-overlay-schema.md)). | Sextant's shape is right; do not adopt namespace-as-domain. |
| Cost | Every chunk is a model call. 1.6M+450k tokens for the README's sample run. | Enrich is one bounded agent session with a `max_tool_rounds` cap (`src/sextant/agents/tradewind.py`). | Per-chunk map is the expensive design. GUIDELINES §8.7 requires the call count to be designed before building. |
| Maturity | v0.1, one author, one week of commits, three stars. Well-argued docs. | `0.1.0`, unreleased, 700+ commits, extensive fixtures and gates. | Take ideas, not code. |

## What Sextant should borrow

### 1. Traces as the unit of rule extraction, terminals as the anchors

This is the one place Sextant can do better than codetospec rather than copy it.
codetospec maps per chunk because chunks are all it has. Sextant already has the trace
from `POST /api/activate` to every terminal. Along that trace, a `throw` call site under a
`conditional` control-flow row is a validation rule's location; a `persistence` terminal
under a conditional is a state transition; an `outbound_call` is a side effect. Those are
deterministic candidate rule sites, computed before any model call. The model's job
shrinks to "state the rule at this site in EARS, citing these lines" — a stronger form of
codetospec's *the LLM consumes facts, it never produces them* than codetospec achieves.

It also answers codetospec's unsolved completeness gap: a conditional `throw` site with no
rule attached is a measurable hole, where codetospec can only report what it found. And it
bounds cost — model calls scale with candidate sites, not lines of code, which is the
design-time count GUIDELINES §8.7 asks for.

### 2. A `rules` overlay kind, rank 10, validated like every other overlay

[D03](../components/D03-overlay-schema.md) has four kinds. A fifth would carry: EARS kind and
requirement, `cites: [path:lines]`, `anchored_to` (an endpoint or symbol id that must
exist), `nature`, and acceptance criteria. Validation adds one check M01 does not have:
**each cited line range must fall inside the `line_start..line_end` of a symbol the graph
knows** — codetospec's SCIP-grounded repair check, available from the class file's
`LineNumberTable` with no indexer. The caveat is stated at D00 §5a: `line_start` is the
first *statement* line, not the signature, and it is `0` for abstract methods and fields,
so the check is "overlaps a method body", never "exact statement".

### 3. Absolute line numbers in every tool result the model reads

`read_file` already takes a line range; the returned text should carry the absolute
number on every line so the model never counts. Trivial to do, and codetospec's single
highest-impact fix.

### 4. Adversarial refutation as a second enrich pass

A rule-refutation pass — fresh context, sees only the rule and its cited lines with ten
lines of marked context, votes `supported | partial | unsupported` — would make the rules
overlay the first model output in Sextant with a **measured** semantic-coherence rate
rather than an asserted one. The existing `verdict` claim (`assessment` / `because` /
`searched`) is most of the shape. codetospec's finding to respect: never cache verdicts by
cited-code digest.

### 5. Stale detection through a cited-code digest

A rule's hash over its cited source lines gives `ok | stale | broken` at render or export
time, the same way `content_hash` already gates component prose. It needs its own name —
"Drift" is taken.

### 6. Deterministic constraints if rules are ever consolidated

If rules are merged across traces, citations must be a verbatim subset of the inputs and
the merge must be a deterministic union, never a rewrite. Batch by candidate count; halve
a batch on truncation rather than raising the output limit.

## What Sextant should not follow

- Do not add model-reported confidence. CONTEXT.md bans it; codetospec measured it as noise.
- Do not add an `explicit/implicit` axis. It degenerates.
- Do not derive domains from namespace segments. Components with listed membership changes
  are the right shape.
- Do not adopt tree-sitter chunking for JVM code. Bytecode symbol extents already give
  per-method scope over the source file the enrich tools can read. (tree-sitter remains
  the declared on-ramp for a second language's `syntax` tier, D00 §4 — a different
  purpose.)
- Do not adopt the extractor JSON protocol. Sextant's catalogs are richer and already data.
- Do not expect algorithms. codetospec produces requirements — *what* holds, in EARS —
  and nothing in its pipeline describes *how* a calculation proceeds. Sextant's `section`
  claim is the existing home for an algorithm description, and the trace plus
  control-flow rows are the grounding such a description needs; keep it a separate design
  question from rules.

## Recommended experiment

Take one existing fixture with a trace that ends in a conditional `throw` and a
`persistence` terminal. Compute the candidate rule sites from the graph alone and count
them. Hand one site at a time to the model with the enclosing method's source, absolutely
line-numbered, and ask for one EARS rule citing lines inside that method. Validate the
citation against the symbol's bytecode line extent. Run a fresh-context refutation on each
accepted rule. Record: candidate sites, rules produced, rules with a citation that fails
the extent check, and the verdict distribution. If the verdict distribution has no variance,
stop — the signal is decoration. If it does, the rules overlay is worth a spec.

## Where this sits

**Deferred, and gated (ruled 2026-09-18).** Recorded in [PROJECT.md](../PROJECT.md)
§ Deferred as "Business-rule extraction". It is built only after Java/Kotlin, Go, Rust,
Python and TypeScript/JavaScript are fully supported — a rules pipeline designed against
one extractor's facts would encode that extractor's shape, and the candidate-site idea in
§1 depends on `throw`, `control_flow_kind` and typed terminals being available from every
language, not one. No design has been done; the brainstorming starts when the gate opens,
and the "Recommended experiment" above is its first step.

Its companion — the deterministic query surface that lets an agent read less source — is
[spotify-portal-shunt.md](spotify-portal-shunt.md), under the same gate.

Deviations: none.
