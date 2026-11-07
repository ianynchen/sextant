# Python performance baseline (OI-208, plan 1, task 0)

Date: 2026-11-06. Machine: the development Mac. Python 3.15.2.

## Question

Can a Python scanner meet the budget in spec section 5?
Cold analysis: ceiling 300 s, target 60 s. Warm analysis: ceiling 30 s, target 10 s.
Test project: `examples/py-polar/server`.

## How it was measured

- Probe: `scripts/probes/python_timing.py <path>`. It reads, parses (`ast.parse`) and walks every
  `.py` file once. It never imports the scanned code. Run with `python -I`.
- The probe counts every `ast.Call` node. It counts test files too.
- JVM rate: the workspaces store no timing. So I timed a real run. I deleted
  `examples/mall/mall-admin/.sextant`, then ran
  `sextant module analyze examples/mall/mall-admin`. Wall time: 6.14 s (scan 1.5 s, resolve 4.1 s).
  The workspace holds 25,057 call sites. Rate: 25,057 / 6.14 = about 4,080 call sites per second.
  This includes about 1 s of program start.

## Numbers

| Tree | Files | Call sites (all) | Cold read+parse+walk | Warm (hash cache) |
|---|---|---|---|---|
| examples/py-polar/server | 2,053 | 113,448 | 1.64 s | 0.03 s |
| src/sextant | 161 | 18,552 | 0.28 s | 0.00 s |

- Parse speed: about 65,000 to 69,000 call sites per second, on one core, no parallelism.
- JVM resolver: about 4,080 call sites per second.

Two counts differ from the spec. The spec says 2,382 files and 47,716 call sites.
This probe finds 2,053 `.py` files (1,411 outside `tests/` and `test/`) and 113,448 `ast.Call`
nodes. The spec's counts probably use another filter. I use the spec's 47,716 for the projection,
as the brief says. Using 113,448 is shown as a worst case.

## Projection for polar, cold

- Parse and walk: 1.6 s (measured; this already covers all 2,053 files).
- Resolve at the JVM rate: 47,716 / 4,080 = 11.7 s.
- Total: about 13 s.
- Worst case, 113,448 call sites at the JVM rate: 27.8 s + 1.6 s = about 29 s.

## Verdict

- The 60 s target is reachable. The projection is 13 s, which is 4.6 times under the target.
  The worst case (29 s) is still under the target.
- The 300 s ceiling is not at risk.
- Warm analysis: reading and hashing all files takes 0.03 s. The 10 s warm target is limited
  by the resolver, not by the scanner. If the resolver is not cached, warm is about 12 s, so
  a resolver cache or a smaller re-resolve is needed to meet the 10 s warm target. The 30 s
  warm ceiling is met either way.

## Caveats

- The JVM rate is a proxy. The Python resolver will bind receivers across 257 packages
  and may cost more per call site. The budget has room for about 4.6 times more cost per call site.
- The JVM run is from one machine and one project. Re-measure after each task that changes a pass.

## Final measurements (plan 1 task 10, 2026-11-07)

Machine: the development Mac (Apple M4, 10 cores). Python 3.14.10, the `.venv` the gate runs on.
Commit 2c6774a1 plus this task's test and probe (no reader code changed). One run each unless
stated. "Cold" is `sextant module analyze <path> --workspace <new folder>`; "warm" is the same
command again into the same workspace, with no file changed. Times are wall time of the whole
command, start-up included. The breakdown is the command's own stage lines and the resolve
passes' `_timed` log lines (`resolve/pipeline.py`, logged at INFO).

### Against the budget (spec §5)

| Tree | Files read | Call sites | Cold | Warm | Cold target 60 s / ceiling 300 s | Warm target 10 s / ceiling 30 s |
|---|---|---|---|---|---|---|
| Sextant (repository root) | 171 files | 23,482 | 8.7 s | 8.8 s | met | target met (8.8 s) |
| polar `server/` | 2,053 files | 129,009 | 27.2 s | 27.6 s | met (2.2 times under the target) | **target missed**; ceiling met by 2.4 s |

polar was read with no installed environment (`examples/py-polar/server` has no `.venv`), so
its libraries come from typeshed alone. Sextant's own `.venv` is read (click, duckdb, pydantic
and the others).

**Warm is the same as cold, because nothing from the first run is reused.** The scanner
re-reads every file and the resolver re-derives every table on every run. The spec's §5 says
the scanner is "cached by content hash, as the JVM extractor caches per class, run in
parallel". Neither is built: `PythonScanner.scan` (`ingress/extract/python/scanner.py`) reads
the files one after another on one core, and computes each file's content hash only to write
it into the document fact.

### Where the time goes

| Stage | Sextant | polar |
|---|---|---|
| start-up, detection, metadata | 1.1 s | 0.5 s |
| scan | 4.8 s | 13.8 s |
| resolve | 2.8 s | 12.9 s |
| render (`sextant module render`, separately) | 0.3 s | 0.3 s |

**The resolve, by pass (polar, cold):**

| Pass | Time |
|---|---|
| `load_facts` | 1.0 s |
| `record_return_flows` | 1.2 s |
| `record_call_edges` | 0.8 s |
| `bind_receivers` (round 1 2.9 s, 10,074 bound; round 2 0.16 s, 0 bound; edges again 0.9 s) | 4.4 s |
| `derive_endpoints` | 2.7 s |
| `derive_endpoint_shapes` | 1.4 s |
| `record_service_identity_gaps` | 0.5 s |
| `record_reachability` | 0.4 s |
| the other 20 passes | 0.3 s in all |

Sextant's are the same passes, smaller: `bind_receivers` 1.0 s, `derive_endpoints` 0.7 s,
`load_facts` 0.3 s, `record_return_flows` 0.2 s.

**The scan (polar, under `cProfile`, which roughly doubles it):** reading the bodies of
functions and classes (calls, values, control flow: `calls._statement`) is about 70% of it;
the library type headers (`Libraries.headers`) about 7%; writing the fact files about 7%;
parsing is small (Task 0 measured read, parse and walk at 1.6 s). On Sextant the library
headers are about a third of the scan, because Sextant's own environment holds pydantic, duckdb
and click, whose types are read.

### What changed since the Task 0 projection

Task 0 projected 13 s cold for polar from a parse-only probe and the JVM resolver's rate. The
measured 27.2 s is about twice that:
- The scan went from 1.6 s (parse and walk) to 13.8 s, because it now writes every fact the
  resolver needs: values, flow, library types (Tasks 4 to 7).
- The resolve went from the projected 11.7 s to 12.9 s, of which receiver binding is 4.4 s
  (Task 8; R25 limited rounds 2 and later to the sites that depend on a newly bound one).

### What would reach the 10 s warm target

Warm polar is 27.6 s. Reaching 10 s needs both of these; either alone does not:
1. **Reuse the scan where nothing changed.** Skip a file whose content hash matches the
   previous run's document and keep its fact file. This removes most of the 13.8 s. A file's
   facts also depend on which other files exist (the module index) and on the libraries
   read, so the cache key must include both, not only the file's own hash.
2. **Skip the resolve when the fact set is unchanged.** With every fact file the same as the
   previous run's, and the same catalogs and Sextant version, the workspace's derived tables
   are already the answer. This removes the 12.9 s.

With both, a warm run with no file changed is start-up plus hashing (Task 0: 0.03 s for every
file), well under 10 s. With only the first, it is about 13.5 s: the resolve alone is over the
target. A run where some file changed still pays the full resolve: making that run fast needs
an incremental resolve, which is a design question, not a cache.

Running the scan in parallel (the spec's other half) helps cold, not warm: about 70% of
13.8 s is per-file work that has no dependency between files.

### The call table, from the real resolver

`python -I scripts/probes/python_call_kinds.py --workspace <workspace folder>...` counts every
`call_site` of an analysed workspace once (per caller and ordinal), split by what the scanner
wrote (before receiver binding) and by what the resolver bound (after it). This replaces the
AST-only table of Task 0 with the resolver's own answer (spec §7 item 1).

**Before receiver binding** (what the scanner wrote):

| | Sextant | | polar `server/` | |
|---|---|---|---|---|
| owner written: `static` (module functions, classes called) | 9,149 | 39.0% | 53,642 | 41.6% |
| owner written: `special` (constructors, `super()`) | 4,749 | 20.2% | 7,652 | 5.9% |
| owner written: `virtual` (a typed receiver) | 4,097 | 17.4% | 14,229 | 11.0% |
| owner written: `dynamic` (f-strings) | 1,434 | 6.1% | 3,696 | 2.9% |
| **owner left to the resolver** | **4,053** | **17.3%** | **49,790** | **38.6%** |
| total | 23,482 | | 129,009 | |

**After receiver binding:**

| | Sextant | | polar `server/` | |
|---|---|---|---|---|
| owner written by the scanner | 19,429 | 82.7% | 79,219 | 61.4% |
| bound: `resolved` (one owner on every path) | 110 | 0.5% | 9,580 | 7.4% |
| bound: `narrowed` (a closed list of owners) | 1 | 0.0% | 32 | 0.0% |
| bound: `partial` (some path names none) | 15 | 0.1% | 100 | 0.1% |
| a function value called (its edge enters the function's body, ruling R29) | 34 | 0.1% | 304 | 0.2% |
| unresolved: `not_readable` | 2,996 | 12.8% | 6,929 | 5.4% |
| unresolved: `external` | 727 | 3.1% | 15,058 | 11.7% |
| unresolved: `no_writer` | 36 | 0.2% | 17,427 | 13.5% |
| unresolved: `non_enumerable` | 21 | 0.1% | 20 | 0.0% |
| unresolved: `escapes` | 9 | 0.0% | 168 | 0.1% |
| unresolved: several reasons, one per path | 104 | 0.4% | 172 | 0.1% |
| **no owner and no reason** | **0** | | **0** | |

**What the unresolved rows are** (measured on these two workspaces):
- **Sextant, `not_readable`:** 2,541 of the 2,996 sites call a `dict`, `list`, `str`, `set`
  or `tuple` method, and 248 a `pathlib.Path` method. A small probe (five functions) shows the
  shapes behind them: an element taken out of a container (`xs[0].strip()`, `for x in xs:
  x.strip()`), and a field declared only by a class-level annotation on a dataclass or a
  `NamedTuple` (`b.beans.get(...)`). Both end `not_readable`. A value typed `Any` and narrowed
  by `isinstance` ends `external`, and so does the result of `dict.get`: a library method whose
  return is a type variable gives no type (Task 7: "a TypeVar … gives None").
- **polar, `no_writer`:** 12,683 of the 17,436 binding rows read an attribute of a library
  module, such as `pytest.mark` (4,516), `alembic.op` (4,046), `tagflow.tag` (2,152) and
  `sqlalchemy.func` (597). A library field has no writer in the scanned code, which is the
  JVM's answer for `System.out` (ruling R26, kept and logged). With no installed environment,
  polar's libraries have no symbols, so more of its calls are `external` and `no_writer` than
  Sextant's.
- **Several reasons:** one row per path, each with its own reason (ruling M-1: per path,
  never combined).
