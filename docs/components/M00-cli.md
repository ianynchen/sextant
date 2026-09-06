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
```

`system analyze --refresh-stale` runs the service pipeline for stale participants and then
the system pipeline. **[M05](M05-sync.md) fetches only** — it never triggers a build.
Putting that orchestration here keeps Sync testable without a JDK, and keeps a surprising
side effect out of a module.

Pipeline stages are internal. `--from-stage` and `--to-stage` exist for debugging and are
not part of the surface.

### `module render --brief` ([GUIDELINES](../../GUIDELINES.md) §8.4)

The one DISPLAY flag on `render`, and [M07](M07-renderer.md)'s `--env` rule applied to a
second choice. **The default draws every trace**; `--brief` draws whole traces while a
stated step budget lasts and stops. It re-reads the same workspace and derives nothing —
the walk, the roots and the steps are identical either way; only how much of the answer
this document spends its bytes on changes, and every trace keeps its summary row in both.

**Opt-in, and named for what it withholds.** It was briefly the other way round —
`--all-traces`, over a bounded default — and §8.4 reversed it: completeness is the
deliverable, a document too large to read linearly is a navigation problem, and a flag
whose name asserts the default is incomplete is the tell that the default is wrong.
**The brief document opens its trace section by saying it is the brief one**, how many of
how many it drew, and the command that draws them all, because a reader handed the file
never ran the command and has no other way to know.

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
