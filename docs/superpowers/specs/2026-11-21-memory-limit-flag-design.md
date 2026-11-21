# A `--memory-limit` Flag for Limited-Memory Machines (OI-493)

**Status:** approved by the user 2026-11-21 ("Do 493 and 494 now"). This is the short design
for a small change.

## Intent

On a limited-resource device or a memory-limited CI container, `analyze` must complete —
maybe slower, never killed by the OS and never exiting without a result. Today the two
largest consumers size themselves from the HOST: DuckDB's own limit defaults to 80% of host
RAM, and the JVM extractor's heap defaults to 25% of host RAM. The third consumer, the
Python scanner's library-AST cache (`Libraries._tables`), grows without bound within one
module scan (~1 GB on py-polar, the remaining cold-run peak after PR #105).

## Goals / non-goals

- **Goal:** one opt-in cap the user sets once; with it set, the three consumers stay inside it.
- **Goal:** with the flag absent, behavior is byte-identical to today.
- **Non-goal:** capping CPU or wall time (WALK_BUDGET already bounds the walk).
- **Non-goal:** bounding every Python-side allocation. The flag bounds the three measured
  holders; the rest of the resolve stage peaked well under them (profile 2026-11-20).
- **Anti-goal:** a cap that makes `analyze` fail. Every lever degrades to slower, never to error.

## The change

One flag, `--memory-limit <MiB>` (integer), on `module analyze`
(`src/sextant/cli/app.py:62`), riding the same path `--shadow` takes into `_run_analyze` /
`_analyzed` (`src/sextant/api.py`). `AnalyzeOptions` gains the matching field — the fourth
knob; the 2026-10-22 spec's "no fourth invented here" was scoped to that spec, and the user
ordered this one (2026-11-21). The flag never reaches the application stage: both consumers
it feeds are constructed in `api.py`.

Three levers, split by measured need (my call; the split is a constant, stated in code):

| Consumer | Share | Mechanism |
|---|---|---|
| JVM extractor | 1/2 | `-Xmx<n>m` inserted in the extractor argv (`ingress/extract/jvm/scanner.py:84`); `AsmScanner` gains an optional `max_heap_mb`, passed from `_scanners()` (`api.py:519`). Extraction is the JVM-heavy phase and does not overlap the resolve peak. |
| DuckDB | 1/4 | `duckdb.connect(path, config={"memory_limit": "<n>MiB"})` in `DuckDbWorkspace.__init__` (`storage/duckdb/workspace.py:2401`), optional parameter, passed only by the analyze construction site (`api.py:932`). DuckDB is floored at 768 MiB: polar's `load_facts` fails at 608 MiB and completes at 640 (measured 2026-11-21), so a lower share would die, not spill. |
| Library-AST cache | 1/4 | `Libraries._tables` becomes bounded ONLY when the flag is set: entry cap = share ÷ 0.5 MiB (the measured mean parsed-module size on py-polar: ~2,000 modules ≈ 1 GB), least-recently-used eviction, re-parse on miss. Unbounded (today's dict) when the flag is absent — the 2026-11-20 measurement showed an always-on LRU would thrash. |

**Known limit, stated up front:** sibling caches in `libraries.py` (`_shapes`, `_answers`,
…) hold references into evicted ASTs and keep some of them alive. The plan therefore
contains a measurement task: py-polar cold with a low cap must show a real peak reduction,
or the third lever is dropped and the measurement recorded (escape hatch — the flag ships
with two levers and the cache lever stays in OI-493's trail).

## Approaches considered

1. **One flag with a stated split (chosen).** One number the user reasons about ("the
   container has 4 GB, give Sextant 3"). The split is a constant, not three more flags.
2. **Three flags, one per consumer.** Honest but asks the user to know Sextant's internals;
   rejected for now — a per-consumer override can be added later without breaking the one-flag form.
3. **Auto-detect host memory (cgroup limits) and self-cap.** Attractive for CI but guesses;
   rejected: an explicit flag tells no lies, and auto-detection can be a later default that
   feeds the same levers.

## Acceptance

- Flag absent: gate green, all 12 field pins green with zero expectation edits.
- Flag set to 2048 on py-polar: analyze completes, results identical to the uncapped run,
  process-tree peak RSS measurably below the uncapped 2.21 GB.
- Flag set absurdly low (e.g. 256): analyze still completes (slower), never OOM-kills, never
  errors.
