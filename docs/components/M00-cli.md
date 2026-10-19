# M00 — Command line

## Purpose

Assemble the modules and expose them as commands.

## The dependency rule

**The CLI imports every module. No module imports the CLI.**

It is numbered first for reading order — start here to see how the parts fit — but the code
dependency runs the other way. This is what makes every other module testable by
constructing it directly with fakes, with no wiring involved. If a module could reach back
into the CLI, you could not build one without building all of them.

An architecture test asserts the absence of that import.

## Interface

None. This is the composition root: the one place that knows every concrete type, reads
configuration, builds the registries, and chooses implementations.

Everything it wires is selected as a **set**, never as a single value. A repository may
hold Java and Kotlin, Spring and Micronaut. Scanners are chosen per language, artifact
readers per file kind, catalogs as the active set, overlays by rank.

## Inputs

Configuration ([D04](D04-config-and-exclusion.md)), the command line, and every module.

## Output

Exit status, and results on standard output.

## Behaviour

### The surface

Every command is *noun, verb, subject, options*.

| Noun | Verbs |
|---|---|
| `module` | `analyze` `list` `status` `render` `enrich` `export` `clean` |
| `system` | `analyze` `status` `render` `clean` |
| `symbol` | `find` `source` `callers` `callees` `implementations` `uses` `impact` `path` |
| `endpoint` | `list` `find` `match` `trace` |
| `overlay` | `validate` `list` |

Global: `--format json|text`, `--scope module|system`, `--workspace`.

### Orchestration is the CLI's job, not a module's

Two commands run more than one module, and both compositions belong here:

```
module analyze   →  M02 detector → M03 scanner → M04 resolver
system analyze   →  M05 sync → M06 stitcher
                 →  the REACTOR participant set → M06 stitcher
```

`system analyze --refresh-stale` runs the service pipeline for stale participants and then
the system pipeline. **[M05](M05-sync.md) fetches only** — it never triggers a build.

**Amendment 2026-10-19 (user decision 1, spec `2026-10-19-reactor-linking-design.md`): a
REACTOR is a second participant source, and the first one built.** `system analyze <reactor
root>` takes its participants from the same `<modules>` walk `module analyze` uses and reads
each module's own workspace, with no `system.yml` and no `M05`. `M05`'s manifest path stays
specified and unbuilt; the two differ only in where the participant set comes from, and the
stitcher is handed the same set either way.

`--environment NAME` (user decision 7) selects the environment every comparison resolves
values for, defaulting to `default`. It is the reactor form of what `system.yml`'s
single-environment declaration will supply once it exists, so nothing is re-plumbed when it
arrives.
Putting that orchestration here keeps Sync testable without a JDK, and keeps a surprising
side effect out of a module.

Pipeline stages are internal. `--from-stage` and `--to-stage` exist for debugging and are
not part of the surface.

### `module render` has no display flag ([GUIDELINES](../../GUIDELINES.md) §8.4)

**One module, one document, and that document is the complete one.** `render` takes a path
and a `--workspace`; it carries nothing that changes what the document shows.

There was one such flag, `--brief`, and it was deleted rather than repaired — *"deleting
that --brief if it only cuts the first N. that's same as lying"*. It drew whole traces
while a 500-step budget lasted, in the summary table's own order, which is an arbitrary
prefix and not a summary; saying so in the document's own text made the omission honest
and never made the prefix an answer. A **trimmed** document is still wanted and is
enrichment work — *"we may want to leverage llm to produce that trimmed down version,
that's a different story and a different ask"* — because which traces a reader can spare
is a judgement, and a renderer cannot compute one.

Volume itself stays a **navigation** problem, answered by indices and by the agents that
read the document, never by drawing less.

### `module enrich` (2K design §3/§8)

Requires a rendered workspace — refused, loudly, naming `render`, before composing anything,
if `render/architecture.md` is absent (an unrendered analysis, or one whose render went
stale after a re-analyze). Given one, it composes the brief, runs the requested `--agent`
through the `EnrichmentAgent` port or takes the `--dry-run`/`--ingest` door instead
([D04](D04-config-and-exclusion.md) §4b), validates the answer by construction, writes
`.sextant-enrichment.json` at the module root, and **assembles both rendered outputs
itself** — there is no second render command; `render`, run again later over a workspace
that already carries an overlay, takes the identical assembly path and reproduces the same
documents.

### Addressing

Subjects are named approximately. Where a name matches several things, **print the matches
and stop** — never choose. Every result carries an exact identifier that can be given
back.

```
$ sextant symbol impact OrderService#save
3 symbols match:
  sym_3f8b  com.acme.orders.OrderService#save(Order)
  sym_91b4  com.acme.orders.OrderService#save(Order, Context)
  sym_c02e  com.acme.legacy.OrderService#save(Order)
```

Short identifiers are always prefixed. Bare hexadecimal is never emitted, because it is
coerced to a number by YAML and by spreadsheets.

### The live task display

Long commands show their whole plan up front and update it in place — one line per task,
never a scrolling log:

```
  ✓ detect                 modules: 4                        1.2s
  ✓ scan :libs:shared      1,204 facts                       3.8s
  ⠸ scan :services:orders  731 / 1,283 files                12.4s
  ✗ scan :services:legacy  build output missing — run the build   0.3s
  · resolve                pending
  · render                 pending
```

The rules, in order of importance:

- **Modules never print.** Stages emit events through the `Progress` port — defined,
  started, finished, failed — and the CLI renders them. The display library can never leak
  into `application/`, and progress behaviour is tested by asserting on events, no terminal
  involved.
- **The display lives on stderr.** stdout carries results only, so `--format json` and
  piped output are never corrupted by a status line.
- **Every task shows elapsed time**, ticking while it runs and frozen at completion, so
  where the minutes went is visible without a profiler.
- **A failed task's line updates with a one-line reason** — the full detail prints below
  the display once it closes. Result and cost stay readable at a glance.
- **The plan is honest.** Per-module tasks are unknowable before detection, so the display
  opens with what is known (`detect` running, phases pending) and expands to the full tree
  the moment the module list lands. No invented totals.
- **Not a terminal → plain lines.** In CI or a pipe, each state transition prints once,
  sequentially, timestamped. No ANSI codes in a log file.

### Output format

`--format` defaults to `text` when standard output is a terminal and `json` when it is
piped, so an agent gets structured output without being told to ask for it.

### Failure

A missing workspace, an incompatible schema, or an ambiguous subject exits non-zero with a
message naming the next action. A partial analysis exits **non-zero unless
`--allow-uncovered` was given**.

## What it must not do

- **No analysis.** No parsing, no derivation, no matching. If logic is here, it cannot be
  tested without a command line.
- **No language names.** Not in a flag, not in a branch, not in a registry key. Scanners
  are selected by what they accept.
- **No writing to files the user owns.** After `render` it prints the line to add to
  `AGENTS.md`; `--link-agents-md` is an explicit opt-in.
- **No hidden orchestration.** A command that runs a build says so before doing it.

## Honesty obligations

- Every command that reads a workspace states the commit it was built from.
- A command reading a **partial** workspace says so in its output, not only in `status`.
- An ambiguous subject is never resolved by picking the first.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether `--refresh-stale` also runs `module export`, or expects the bundle to appear another way | M05 |
| Whether `--workspace` accepts a central cache location as well as a directory | [D04](D04-config-and-exclusion.md) |
| Whether verbs may be abbreviated | — |
