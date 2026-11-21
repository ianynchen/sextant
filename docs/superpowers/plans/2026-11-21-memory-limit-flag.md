# `--memory-limit` Flag Implementation Plan (OI-493)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One opt-in `--memory-limit <MiB>` flag on `module analyze` that keeps the three measured memory holders (JVM extractor heap, DuckDB, the Python library-AST cache) inside the cap, so analyze completes on limited-memory machines — slower past the cap, never killed, never erroring.

**Architecture:** The flag rides the path `--shadow` already takes (`cli/app.py` → `api._analyze` → `_run_analyze`/`_analyzed`) and never reaches the application stage: both consumers it feeds are constructed in `api.py`. Three levers, split by constant: JVM `-Xmx` = 1/2 of the cap, DuckDB `memory_limit` = 1/4, library-AST cache = 1/4 (entry count from the measured ~0.5 MiB mean parsed module). With the flag absent every lever is off and behavior is byte-identical.

**Tech Stack:** Python 3.14, click, DuckDB, pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-memory-limit-flag-design.md`

## Global Constraints

- Flag absent ⇒ byte-identical behavior: gate green AND all 12 field pins green with zero expectation edits.
- Every lever degrades to slower, never to an error: an absurdly low cap must still complete.
- The split is ONE constant set stated in `api.py` (1/2 JVM, 1/4 DuckDB, 1/4 AST cache; AST entries = share ÷ 0.5 MiB measured mean), never three flags.
- `AnalyzeOptions` gains the fourth knob; its docstring's "and no fourth" line is updated to name this spec (the 2026-10-22 line was scoped to that spec; the user ordered this knob 2026-11-21).
- The AST-cache bound exists ONLY when the flag is set (measured 2026-11-20: an always-on LRU would thrash).
- No `FACT_SCHEMA_VERSION` bump; no new published vocabulary.
- House rules: GUIDELINES §1–4, §7; match existing patterns (§13.5); no refactoring of adjacent code.
- Gate: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh` redirected to a FILE, then `echo $?` — never piped through tail/head. Same for `scripts/field_check.py`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Review Focus

1. **A tiny cap (16 MiB) erroring instead of slowing** — DuckDB config or `-Xmx` rejecting the value, violating the anti-goal. Pinned by Task 1 step 1 (`test_a_tiny_memory_limit_still_opens_and_applies_schema`) and Task 4's CLI test at 256 MiB.
2. **A Python-only repo with the flag set** — no JVM launches; the unused JVM share must not error or warn. Pinned by Task 4 step 1 (`test_memory_limit_on_a_python_module_completes`).
3. **Eviction changing answers** — a `_Table` evicted and re-parsed must answer identically, including the cached-`None` failed-parse case. Pinned by Task 3 step 1 (`test_eviction_then_reparse_answers_identically`, `test_a_failed_parse_stays_failed_after_eviction`).
4. **A multi-module reactor** — each module's `_run_analyze` opens its own workspace; the cap must reach every one, not only the first. Pinned by Task 4 step 3's wiring (one code path: `_run_analyze` takes the value) and its test asserting the workspace setting inside a two-module analyze.
5. **The flag silently off** — plumbing drops the value somewhere between click and the constructors, and nothing notices because results are identical anyway. Pinned by Task 4's end-to-end assertions reading the live DuckDB setting and the recorded extractor argv, never only the exit status.

---

### Task 1: DuckDB lever

**Files:**
- Modify: `src/sextant/storage/duckdb/workspace.py:2401-2403` (`DuckDbWorkspace.__init__`)
- Test: `tests/storage/test_workspace.py`

**Interfaces:**
- Produces: `DuckDbWorkspace(path: Path, memory_limit_mb: int | None = None)` — when set, the connection opens with `config={"memory_limit": f"{memory_limit_mb}MiB"}`; when `None`, exactly today's `duckdb.connect(str(path))`.

- [ ] **Step 1: Write the failing tests**

```python
def test_memory_limit_reaches_duckdb(tmp_path):
    ws = DuckDbWorkspace(tmp_path / "w.duckdb", memory_limit_mb=512)
    value = ws._connection.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert value == "476.8 MiB" or value.startswith("512")  # read the real format once and pin it

def test_a_tiny_memory_limit_still_opens_and_applies_schema(tmp_path):
    ws = DuckDbWorkspace(tmp_path / "w.duckdb", memory_limit_mb=16)
    # the schema applied and a trivial query runs — no error path
    assert ws._connection.execute("SELECT 1").fetchone() == (1,)

def test_no_memory_limit_leaves_the_default(tmp_path):
    ws = DuckDbWorkspace(tmp_path / "w.duckdb")
    value = ws._connection.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert value not in ("16.0 MiB", "512.0 MiB")
```

Before committing, run DuckDB once by hand to pin the exact `current_setting` format and write the first assertion against it (no `or`).

- [ ] **Step 2: Run tests to verify they fail** — `uv run pytest tests/storage/test_workspace.py -k memory_limit -v`; expected: TypeError (no such parameter).
- [ ] **Step 3: Implement** — add the keyword-only parameter, pass `config={"memory_limit": f"{memory_limit_mb}MiB"}` to `duckdb.connect` when set. Touch none of the other five `DuckDbWorkspace(...)` construction sites.
- [ ] **Step 4: Run tests to verify they pass.**
- [ ] **Step 5: Commit** (`feat(storage): DuckDbWorkspace takes an optional memory limit (OI-493)`).

### Task 2: JVM lever

**Files:**
- Modify: `src/sextant/ingress/extract/jvm/scanner.py:31` (`AsmScanner.__init__`), `:84-88` (extraction argv)
- Test: `tests/ingress/extract/jvm/test_scanner.py` (or the existing scanner test file — find it with `grep -rl AsmScanner tests/`)

**Interfaces:**
- Produces: `AsmScanner(jar, max_heap_mb: int | None = None)` — when set, the extraction argv is `["java", f"-Xmx{max_heap_mb}m", "-jar", ...]`; the `--capabilities` probe argv (`scanner.py:49`) is unchanged (it reads a help text, not a repo).

- [ ] **Step 1: Write the failing test** — monkeypatch `subprocess.run` to record argv; assert `-Xmx1024m` sits between `java` and `-jar` when `max_heap_mb=1024`, and is absent when `None`.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** (`feat(extract): the JVM extractor takes an optional -Xmx (OI-493)`).

### Task 3: Bounded library-AST cache

**Files:**
- Modify: `src/sextant/ingress/extract/python/libraries.py:284` (`_tables` declaration), `:1461-1478` (`_table()` insert path), the `Libraries.__init__` signature
- Modify: `src/sextant/ingress/extract/python/scanner.py:81-85` (`PythonScanner` passes the cap through to `Libraries`)
- Test: `tests/ingress/extract/python/test_libraries.py` (find the real file with `grep -rl "Libraries(" tests/`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Libraries(..., table_cap: int | None = None)` and `PythonScanner(table_cap: int | None = None)`. With a cap: `_tables` evicts least-recently-used past `table_cap` entries; a read re-parses on miss. With `None`: today's plain dict, untouched.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_table_cache_evicts_past_the_cap(...):
    # cap=2, touch 3 library modules, assert len(_tables) <= 2
def test_eviction_then_reparse_answers_identically(...):
    # resolve a name through a module, force its eviction, resolve again: same answer
def test_a_failed_parse_stays_failed_after_eviction(...):
    # a module cached as None, evicted, re-asked: None again, no exception
def test_no_cap_means_no_eviction(...):
    # default construction: touch 3 modules, all 3 stay
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** — the smallest LRU that keeps the dict interface `_version_tests` reads at `:338` (`self._tables.get(module)`): an ordered dict moved-to-end on `_table()` hits, popped from the front past the cap. Eviction applies to `_tables` only; the sibling caches are out of scope by design (the design doc's "known limit").
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** (`feat(extract): the library-AST cache takes an optional entry cap (OI-493)`).

### Task 4: The flag, the split, the plumbing

**Files:**
- Modify: `src/sextant/cli/app.py:62-93` (`module analyze` gains `--memory-limit`), `src/sextant/api.py` (`AnalyzeOptions:268-278`, `analyze:1168`, `_analyze:1090`, `_analyze_reactor:1130`, `_run_analyze:907` + its `DuckDbWorkspace(...)` at `:932`, `_analyzed:965` + `_scanners():519`)
- Test: `tests/cli/test_app.py` and/or `tests/test_api.py` (match where `--shadow` is tested today: `grep -rn "allow_resolve\|shadow" tests/cli tests/test_api.py`)

**Interfaces:**
- Consumes: Task 1's `memory_limit_mb`, Task 2's `max_heap_mb`, Task 3's `table_cap`.
- Produces: `--memory-limit <MiB>` (click `type=int`, default `None`); `AnalyzeOptions(memory_limit_mb: int | None = None)`; module-level split in `api.py`:

```python
# OI-493: the one split, measured 2026-11-20 — extraction (JVM) and the resolve peak do not
# overlap; the AST-cache share converts at the measured ~0.5 MiB mean parsed module.
def _memory_shares(limit_mb: int) -> tuple[int, int, int]:
    """(jvm_xmx_mb, duckdb_mb, ast_cache_entries)"""
    return limit_mb // 2, limit_mb // 4, max(32, (limit_mb // 4) * 2)
```

- [ ] **Step 1: Write the failing tests**

```python
def test_memory_shares_split():
    assert _memory_shares(2048) == (1024, 512, 1024)
    assert _memory_shares(256) == (128, 64, 128)
    assert _memory_shares(64) == (32, 16, 32)   # the floor keeps the cache usable

def test_memory_limit_on_a_python_module_completes(tmp_path):
    # the smallest existing Python fixture tests/ uses for analyze; flag set;
    # assert the run completes AND the workspace's memory_limit setting reflects the cap
    # (read it back through the workspace the way Task 1's test does)

def test_memory_limit_reaches_the_extractor(tmp_path, monkeypatch):
    # a JVM fixture analyze with the flag; recorded argv contains -Xmx<limit//2>m
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement the plumbing** — one keyword argument `memory_limit_mb: int | None = None` on the same five functions `shadow` rides (`_analyze`, `_analyze_reactor`, `_run_analyze`, `_analyzed`, plus `_scanners(memory_limit_mb)`); `_run_analyze` passes `_memory_shares(...)[1]` to `DuckDbWorkspace`, `_scanners` passes `[0]` to `AsmScanner` and `[2]` to `PythonScanner`. CLI flag + `AnalyzeOptions` field + docstring amendment (Global Constraints). Multi-module: the value flows through `_analyze_reactor` into each per-module `_run_analyze` call — one path, no special case.
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** (`feat(cli): --memory-limit caps the JVM, DuckDB and the library-AST cache (OI-493)`).

### Task 5: Measurement, escape hatch, docs, gate

**Files:**
- Modify: `CHANGELOG.md`, `docs/coverage/python.md:356` (the OI-493 row moves from "undecided" to built), `docs/open-issues.md:498`
- Uses: `scripts/profile_analyze.sh` (committed 2026-11-20; cold+warm, tree-RSS sampler, MiB)

- [ ] **Step 1: Measure py-polar cold, uncapped vs `--memory-limit 2048`** — run `scripts/profile_analyze.sh` on the polar corpus both ways (clone via `uv run python scripts/field_check.py py-polar-server` if `examples/` lacks it). Record both peaks in the task report. Expected: the capped peak is really below 2.21 GB (the uncapped measured value). **Escape hatch:** if the AST-cache lever moves the peak by under ~10% (sibling caches pinning the ASTs — the design doc's known limit), REMOVE the Task 3 wiring from `_memory_shares` (keep the Libraries parameter, tested but unfed), record the measurement in the OI-493 Plane item, and state it in the CHANGELOG line. Do not ship a lever that does nothing.
- [ ] **Step 2: Measure the absurd floor** — `--memory-limit 256` on the same corpus completes with exit 0. Record wall time.
- [ ] **Step 3: Docs** — CHANGELOG entry with both measured numbers; coverage row + open-issues row updated to built/measured wording.
- [ ] **Step 4: Gate + pins** — `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh > /tmp/gate.log 2>&1; echo $?` then `uv run python scripts/field_check.py > /tmp/pins.log 2>&1; echo $?`. Expected: 0 and 0, zero expectation edits.
- [ ] **Step 5: Commit** (`docs: --memory-limit measured and recorded (OI-493)`).
