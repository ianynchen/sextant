# Value-Walk Cycle Regions and Memory Borders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `analyze` complete on repos with strongly-connected value regions (measured: home-assistant hangs >65 min today) and cut the cold-run memory peak, so Sextant runs to completion on resource-limited machines.

**Architecture:** Two independent defect groups, both measured on 2026-11-20 (evidence below). (A) The backward value walk discards every answer computed while a cycle back edge is open, so both memo layers accept nothing inside a strongly-connected region and the first resolution of the region costs one traversal per path — exponential. Fix: keep such answers provisionally, reusable only while the exact same back edges are still pending; plus a measured work budget as a safety net that publishes an honest `unresolved` instead of hanging. (B) The cold-run memory peak is at the Python/DuckDB border, not inside DuckDB: whole result sets materialized by `_run_named`, and single `json.dumps` parameter strings up to 536 MB from `_bound`. Fix: chunk the writes and keep reads from holding everything at once, outputs byte-identical.

**Tech Stack:** Python 3.14, DuckDB, pytest; memray (dev-only, via `uv run --with memray`, never a project dependency).

**Spec:** The measured findings in `~/.claude/projects/-Users-yining-programming-ai-sextant/memory/resource-profile-2026-11-20.md` and the Evidence section below. This plan amends the value-resolution design's keep rule (task 8 re-review R3-1 / ruling R39) — the amendment is stated in Task 2 and changes only WHEN an answer may be stored, never what any answer is. Rulings M-1 and §1c (answers are per-path; memo key includes the trail) stay untouched.

## Evidence (measured 2026-11-20, Apple Silicon, 24 GB)

- Cold peaks scale linearly with first-party source: redash package duplicated x1/x2/x4 → 0.96/1.27/2.27 GB, 8/11/18 s. py-polar 2.87 GB / 39 s is the largest pinned corpus.
- home-assistant (1,592 components): extraction finishes in ~2 min; resolve then runs >65 min at 100% of one core, flat ~54 MB RSS, no I/O. Truncations are linear (100→41 s, 200→50 s, 400→73 s, 800→127 s); the blow-up needs `components/template` (any one of the other 16 largest components adds 1–3 s). Inside template no single file is slow — the platform files (`sensor.py`, `switch.py`, …) must interact with `template_entity.py`/`trigger_entity.py`: it is a cycle across files.
- Instrumented 240 s sample of core+template: 53.1 M slot computes over 13,600 distinct positions; 50.3 M were pending-set cycle hits; 53.09 M of 53.10 M slot answers and 2.84 M of 2.84 M parameter answers were NOT kept; the R39 suffix memo was asked 5.3 M times for 2,264 distinct keys. Max trail length seen: 6 (explosion is branching, not depth).
- memray on py-polar cold (peak 2.7 GB): `_run_named` fetchall list-of-dicts 3.9 GB cumulative; `_bound` `json.dumps` single allocations to 536 MB (11 allocations >72 MB); `ast.parse` 5.4 GB cumulative churn. DuckDB workspace is file-backed; the in-Python materialization is the peak, not DuckDB.

## Global Constraints

- House rules apply: GUIDELINES §1–4 and §7; truth first (a wrong `resolved` row is a lie — `unresolved` with a reason is always preferable); match existing patterns (§13.5); no refactoring of adjacent code.
- NO new unresolved-reason vocabulary and NO new catalog vocabulary: budget exhaustion reuses `NON_ENUMERABLE` (`values.py:173`) — it is the same truth ("the paths exceed what can be enumerated within bounds").
- NO `FACT_SCHEMA_VERSION` bump: facts are unchanged; only resolve behavior and storage I/O shape change.
- Determinism: analyze on the same input twice produces identical rows. The budget counts computes (deterministic), never wall time.
- Outputs stay byte-identical for inputs that complete within budget today: the gate (7,330 tests) and all 9 field pins are the identity check; any pin diff must be explained row by row or the change is wrong.
- memray and profiling runs use `uv run --with memray`; nothing profiling-related enters pyproject.
- Gate: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`. Never run the gate while an implementer is editing. Never pipe `scripts/field_check.py` through `tail`/`head` (eats the exit code) — redirect to a file, then `echo $?`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Review Focus

1. **A provisionally kept answer reused under the wrong pending context** publishes a wrong `resolved` row (a lie). Pinned by Task 2 step 1's adversarial test (`test_provisional_answer_not_reused_after_region_completes`).
2. **Budget nondeterminism**: two runs of the same input disagreeing on which rows are `NON_ENUMERABLE`. Pinned by Task 3 step 1 (`test_budget_is_deterministic`).
3. **Chunked writes changing row content or multiplicity** (e.g. a batch boundary splitting a JSON value or dropping the tail chunk). Pinned by Task 4 step 1 (`test_chunked_params_write_identical_rows`).
4. **Provisional entries leaking across walk instances or binding rounds** (stale answers after a binding round changes the index). Pinned by Task 2 step 5 (the existing architecture test `tests/architecture/test_nested_walks_pass_their_reads.py` must stay green, plus `test_provisional_entries_die_with_their_back_edges`).
5. **The budget silently converting rows that used to resolve** on the pinned corpora. Pinned by Task 3 step 4: all 9 field pins green with zero expectation edits.

---

### Task 1: Reproduction — a strongly-connected fixture and the failing cost test

**Files:**
- Test: `tests/application/test_walk_cost.py`

**Interfaces:**
- Produces: `make_ring_module(tmp_path, classes: int, calls_per_method: int) -> Path` (module-level helper in the test file) — writes a small Python package whose value edges form one strongly-connected region: `classes` classes in separate files, each method passing a shared dict to `calls_per_method` methods of the next class in the ring, with the last class calling back into the first (mirror of template's platform ↔ entity shape).
- Produces: `count_computes(monkeypatch) -> Callable[[], int]` — wraps `_Walk._guarded` (`src/sextant/application/resolve/values.py:3717`) with a counter, the same wrapping the 2026-11-20 instrumented run used.

- [ ] **Step 1: Write the failing test**

```python
def test_cycle_region_cost_is_bounded(tmp_path, monkeypatch):
    # 8 classes x 3 calls each: ~24 positions in one SCC. Today this walk
    # recomputes per path: measured >500_000 computes. Bounded, it is
    # a small multiple of the positions.
    module = make_ring_module(tmp_path, classes=8, calls_per_method=3)
    computes = count_computes(monkeypatch)
    analyze(module)          # the same entry tests/application uses today
    assert computes() < 50_000
```

The counter must also hard-fail fast: when computes exceed 2_000_000, raise from the wrapper so the pre-fix test fails in seconds instead of minutes.

- [ ] **Step 2: Run it, verify it fails by cost** — `uv run pytest tests/application/test_walk_cost.py -v`; expected: FAIL with the compute ceiling exceeded (NOT an error in fixture plumbing). Tune `classes`/`calls_per_method` upward only until the pre-fix count exceeds 500k; record the pre-fix count in the test's docstring.
- [ ] **Step 3: Commit** (`test: pin the walk's cost on a strongly-connected value region (fails pre-fix)`), marked `xfail(strict=True)` with reason "cycle-region answers are not kept yet — Task 2" so the branch stays green between tasks.

### Task 2: Keep answers inside cycle regions (the fix)

**Files:**
- Modify: `src/sextant/application/resolve/values.py` — `Kept` (:609), `_Walk._guarded` (:3717), `_Walk._joined_upward` (:3756)
- Test: `tests/application/test_walk_cost.py` (un-xfail), `tests/application/test_walk_provisional.py` (new)

**Interfaces:**
- Consumes: Task 1's fixture helper and counter.
- Produces: the amended keep rule, documented on `Kept` itself.

**The amendment (state it verbatim in `Kept`'s docstring):** an answer computed for a key while back edges `B` were open, having entered positions `D` (the pending-misses of that compute), MAY be kept and reused for a later ask of the same key iff at that later ask `B ⊆ pending` and `pending ∩ D = ∅`. Under that condition a fresh compute would retrace the identical walk (the walk is deterministic; every open position answers the same CYCLE marker; every entered position is entered again), so reuse changes nothing but the cost. When any position in `B` completes, the condition can never hold again and the entry is dead. The existing unconditional keep is the `B = ∅, D` irrelevant case.

- [ ] **Step 1: Write the adversarial tests first** in `tests/application/test_walk_provisional.py`:

```python
def test_provisional_answer_not_reused_after_region_completes(...):
    # Ask P while H is pending (gets a CYCLE-tainted answer), complete H,
    # ask P again on a fresh path: the second answer must be the post-H
    # answer, not the tainted one. Drive _Walk directly on a hand-built
    # ValueIndex (the pattern tests/application already uses for the walk).

def test_provisional_answer_not_reused_when_new_position_is_pending(...):
    # P's first compute ENTERED R (R in D). Ask P again while R is pending:
    # must recompute (fresh answer has CYCLE at R), never reuse.

def test_provisional_entries_die_with_their_back_edges(...):
    # After H completes, the store holds no entry whose B contains H
    # (or the entry is never again accepted — assert via a second ask).
```

- [ ] **Step 2: Run them, verify they fail or error pre-change** (they pin behavior the current code happens to satisfy by never keeping — the first two must PASS pre-change and stay green; the point is they must still pass POST-change. Mark which in a comment.)
- [ ] **Step 3: Implement.** Extend `Kept` so an entry can carry `(B, D)` and an acceptance check against the asker's current pending set (the walk hands `Kept.get` a `pending` view; thread it as a parameter, matching how `deps` is threaded today). `_guarded` returns `(reached, keep)` today; change it to also return `(B, D)` for the provisional case — `B = unresolved_back_edges` (already computed, :3740), `D` = the positions whose `pending.add` happened inside this compute (collect on the walk, a list-of-sets stack exactly like `_deps`). `_joined_upward`'s suffix memo and `_resolve`'s per-(position, trail) memo both go through the same `Kept`, so one mechanism serves both.
- [ ] **Step 4: Un-xfail Task 1's cost test; run it** — expected: PASS with computes < 50_000. Record the post-fix count next to the pre-fix count in the docstring.
- [ ] **Step 5: Run the walk's own suites** — `uv run pytest tests/application tests/architecture -x -q`; expected: all green, including `tests/architecture/test_nested_walks_pass_their_reads.py` (provisional entries must carry their `reads` exactly as kept entries do — a hit hands the asker the entry's reads).
- [ ] **Step 6: The field proof.** `examples` holds the corpora. Run analyze on the 2026-11-20 repro: hass core + `components/template` only (rebuild per the memory note: clone `home-assistant/core`, keep `homeassistant/`, `script/`, `packages/`, delete `tests/` and all of `components/` except `template`). Expected: completes in under 2 minutes (was: >5 min for the 17-file half, >65 min full). Record wall time in the ledger.
- [ ] **Step 7: Full gate + all 9 field pins** (to files, `echo $?`). Expected: gate green, pins green with zero expectation edits.
- [ ] **Step 8: Commit** (`fix(resolve): keep cycle-region answers while their back edges are pending (R39 amendment)`).

### Task 3: The work budget (safety net)

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (`_Walk`, constant `WALK_BUDGET` beside `PATH_CAP` :353)
- Test: `tests/application/test_walk_cost.py`

**Interfaces:**
- Consumes: Task 2's fix (budget is sized AFTER the fix).
- Produces: `WALK_BUDGET: int` — computes per root `at()` call; on exhaustion the root's remaining answer is `((trail, _unresolved(NON_ENUMERABLE)),)`, exactly the shape `_windowed` already returns at `PATH_CAP` (:4541).

- [ ] **Step 1: Write the tests**

```python
def test_budget_exhaustion_is_an_honest_unresolved(tmp_path, monkeypatch):
    # Shrink WALK_BUDGET via monkeypatch to force exhaustion on the ring
    # fixture; the affected rows are unresolved with reason non_enumerable;
    # analyze exits 0.

def test_budget_is_deterministic(tmp_path, monkeypatch):
    # Two analyzes of the same module under the same shrunken budget:
    # identical rows (compare the full endpoint/requirement row sets).
```

- [ ] **Step 2: Implement** — a per-`at()` compute counter on `_Walk`; checked in `_guarded` before computing; when exhausted, every further compute returns the NON_ENUMERABLE answer unkept, so the root unwinds quickly and deterministically.
- [ ] **Step 3: Size it from measurement.** Instrument max computes per root across py-polar, py-dispatch, py-mealie, py-redash, py-ctfd, mall-admin, apollo-portal (one analyze each, counter per `at()`). `WALK_BUDGET` = 10× the observed maximum, stated with the measured numbers in the constant's comment.
- [ ] **Step 4: Gate + all 9 pins; zero expectation edits.** Any pin row that newly reads `non_enumerable` means the budget is too small — resize, do not edit the pin.
- [ ] **Step 5: Commit** (`feat(resolve): a measured work budget per root resolve — exhaustion is an honest non_enumerable`).

### Task 4: Border crossing IN — chunk the giant parameter strings

**Files:**
- Modify: `src/sextant/storage/duckdb/workspace.py` (`_bound` :2141, the write paths memray names)
- Test: `tests/storage/test_workspace.py` (extend)

**Interfaces:**
- Consumes: nothing from earlier tasks (independent).
- Produces: no API change — same `derive`/`_run_named` signatures, same rows.

- [ ] **Step 1: Write the test** — `test_chunked_params_write_identical_rows`: a derivation/write that today passes one list of ≥3 chunk-sizes' worth of rows produces exactly the same table contents as before (compare full sorted row sets), including an empty list, exactly one chunk, and a non-multiple tail.
- [ ] **Step 2: Locate the giant strings** — `uv run --with memray memray run` + `stats` on a py-polar cold analyze; the top `iterencode` caller(s) through `_bound` are the target. Record which call sites pass multi-hundred-MB lists.
- [ ] **Step 3: Implement** — split those bulk list parameters into chunks (10_000 rows per execute, one transaction, same statement), or move the write to the existing `executemany` path (:2756) where the statement allows. Keep `_bound`'s JSON behavior for small params untouched.
- [ ] **Step 4: Verify by measurement** — memray stats on py-polar cold: max single allocation < 100 MB (was 536 MB). Gate + pins green.
- [ ] **Step 5: Commit** (`perf(storage): bulk parameters cross to DuckDB in chunks, not one giant JSON string`).

### Task 5: Border crossing OUT — the peak holder at high-water mark

**Files:**
- Modify: `src/sextant/storage/duckdb/workspace.py` (`_run_named` :2151) and/or the caller the measurement names
- Test: existing suites (behavior identical); measurement is the acceptance

**Interfaces:**
- Consumes: Task 4 landed (measure after it, so the peaks don't overlap).
- Produces: no API change visible to callers that need the whole result; a streaming read only where the measurement shows a whole-result list holding the peak AND the caller consumes it row-by-row.

- [ ] **Step 1: Attribute the peak** — `uv run --with memray memray flamegraph --temporal` (or `memray tree`) on py-polar cold AFTER Task 4; identify what holds memory at the high-water mark. This is the decision step: fix the top holder(s) only.
- [ ] **Step 2: Implement the targeted fix** — for a `_run_named` consumer that aggregates row-by-row: fetch in batches (`fetchmany`) and build the same output incrementally; for a holder that is better expressed in SQL: move the aggregation into the named query. No speculative changes anywhere the measurement did not name.
- [ ] **Step 3: Verify by measurement** — py-polar cold tree peak ≤ 1.8 GB (was 2.87 GB; Tasks 4+5 combined own this number). If the measured peak holder is the AST/extraction phase instead (out of this plan's scope), stop, record the attribution in the ledger, and let the controller rule — do not chase it.
- [ ] **Step 4: Gate + all 9 pins green, zero expectation edits. Commit** (`perf(storage): the cold-run peak no longer holds whole result sets at the border`).

### Task 6: Re-profile, the home-assistant field pin, documentation

**Files:**
- Create: `scripts/profile_analyze.sh` (the cold/warm wall + tree-peak-RSS sampler used 2026-11-20, cleaned up: args = module paths, output = one table)
- Create: `scripts/field-expectations/py-home-assistant.json`
- Modify: `CHANGELOG.md`, `docs/open-issues.md` (id map), `docs/coverage/python.md` (Open list if entries close/open)

**Interfaces:**
- Consumes: all earlier tasks landed.

- [ ] **Step 1: Commit `scripts/profile_analyze.sh`** — it reruns tomorrow what was hand-built today; keep it ≤ ~60 lines, no options beyond module paths.
- [ ] **Step 2: Re-profile** all 10 corpora (cold+warm) plus home-assistant full (clone at a pinned commit, tests excluded by the reader's own rules — `testpaths` is declared upstream). Acceptance: home-assistant completes; target < 15 min cold; every previously-measured corpus at or below its 2026-11-20 peak and wall. Record the table in the ledger and CHANGELOG.
- [ ] **Step 3: Add the py-home-assistant field pin** — upstream `home-assistant/core` at the measured commit; expectations are whatever is TRUE (likely near-zero inbound rows — aiohttp has no catalog yet — plus environment/config reads if any): state counts and the gap's cause in the JSON the way py-redash does. The pin's value is "the biggest known real repo completes and its numbers are pinned".
- [ ] **Step 4: Plane + id map** — file OI-491 (walk explosion — fixed by Tasks 1–3), OI-492 (border crossings — fixed by Tasks 4–5), OI-493 (resource-cap flag: decision deferred until the user sees the re-measure); Plane ids continue from SEXTANT-483; close 491/492 on merge, add the three id-map rows to `docs/open-issues.md`.
- [ ] **Step 5: Gate + pins one final time; commit** (`docs+pins: re-measured resource profile; py-home-assistant pinned; OI-491..493 filed`).
