# Configured schedules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `@Scheduled` expression written with a placeholder is read per environment from the module's configuration, through the project's one placeholder rule, and shown in the document as what the repository configures.

**Architecture:** `resolve/config.py`'s `_substitute` is split into a parsing rule `substitute(raw, placeholders, lookup)` plus lookups. A new pass writes `resolved_schedules(handler, trigger, environment, value, unresolved_reason)` from `scheduled_work` × `resolved_config`. The document's scheduled-work section renders the per-environment values; the bundle exports the table; the diff is unchanged.

**Tech Stack:** Python 3.13, DuckDB, pytest; Java fixtures built with JDK 21.

**Spec:** `docs/superpowers/specs/2026-10-23-configured-schedules-design.md`

## Global Constraints

- Gate: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh` (pre-commit needs `PATH=/Users/yining/programming/ai/sextant/.venv/bin:$PATH`).
- Fixtures are built with JDK 21, never 27.
- Framework knowledge is catalog data: placeholder delimiters and `default_separator` come from the config model's `placeholders` (D02 §2i), never literals in the new pass.
- `GRAPH_SCHEMA_VERSION` 6 → 7 (a new derived table). `SEXTANT_VERSION`, `FACT_SCHEMA_VERSION` and `BOUNDARY_VOCABULARY_VERSION` do NOT move.
- `scheduled_work` keeps one row per job and its `resolution` stays `unresolved` for a placeholder expression. The diff's `schedule` kind is unchanged.
- Every new rule gets a guard in `scripts/guard_check.py`, measured killed; a pinned test whose expectation changes is re-pinned, never deleted.
- Every exit masks: the bundle export of `resolved_schedules.value` goes through `redact_text`, the document through the render redactor.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- **A default in the annotation.** `${orders.sweep.cron:0 0 * * * *}` with the key set in no environment resolves to `0 0 * * * *` in every environment, not `missing_key`.
- **A default containing the separator.** `${k:0 0 * * * *}` splits at the FIRST `:` only; a cron has no colon, but `${k:a:b}` must give default `a:b`.
- **Relaxed key matching.** `${orders.sweep-cron}` against a configured `orders.sweep.cron` under a relaxed model resolves; under an exact model it is `missing_key`.
- **Two placeholders in one expression** (`${a} ${b}`) resolve both; one missing makes the whole value unresolved, never half-substituted.
- **A job with no placeholder** gets no `resolved_schedules` row, and the document's line for it is unchanged byte for byte.

---

### Task 1: One placeholder rule — `substitute(raw, placeholders, lookup)`

**Files:**
- Modify: `src/sextant/application/resolve/config.py` (`_substitute` ~364-422, `_resolve_reference` ~424-455)
- Test: `tests/application/test_config*.py` (find with `grep -rln "_substitute\|resolve_config" tests/application`)

**Interfaces:**
- Produces: `substitute(raw: str, placeholders: Mapping[str, str], lookup: Callable[[str], tuple[str | None, str | None]]) -> tuple[str | None, str | None]` (public, in `config.py`); `_resolve_reference` becomes the lookup `resolve_config` passes (a closure or `functools.partial` over its merged map, index, key matching and stack). Behaviour of `resolve_config` is byte-identical.

- [ ] **Step 1: Write failing unit tests** for `substitute` with a dict-backed lookup: `${a}` → value; `${missing:fallback}` → `fallback` (and the default is not re-substituted: `${missing:${a}}` → the literal `${a}`); `${k:a:b}` with `k` missing → `a:b`; `${a} and ${b}` → both substituted; `${a} and ${missing}` → `(None, "missing_key")`; no closing delimiter → literal; custom delimiters from `placeholders` (`{"open": "#[", "close": "]", "default_separator": "|"}`) honoured.
- [ ] **Step 2: Run them.** Expected: FAIL, `substitute` not defined.
- [ ] **Step 3: Implement** by extracting the walk from `_substitute` unchanged and passing the lookup. `resolve_config` keeps calling it with its recursive lookup.
- [ ] **Step 4: Run** the new tests and every existing config test. Expected: all PASS, no existing expectation edited.
- [ ] **Step 5: Run the full gate and the field pins** (`scripts/field_check.py`, six `ok`): `resolved_config` must not move on any corpus.
- [ ] **Step 6: Commit** `refactor(config): one placeholder rule, parameterised by its lookup`.

### Task 2: `resolved_schedules` — the table, the pass, the export

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql` (new table beside `scheduled_work`, with a comment in the file's style), the reset/insert SQL the other derived tables use (find with `ls src/sextant/storage/duckdb/*scheduled*`), `src/sextant/storage/duckdb/workspace.py` (`_NAMED_QUERIES["resolved_schedules"]`, `_EXPORT_QUERIES["resolved_schedules"]` masked by the address/text map as the file's pattern dictates, derive names)
- Create: `src/sextant/application/resolve/resolved_schedules.py`
- Modify: `src/sextant/application/resolve/pipeline.py` (call the pass after the scheduled-work engine and `resolve_config`; reset once per resolve)
- Modify: `src/sextant/domain/version.py` (`GRAPH_SCHEMA_VERSION = 7`, comment row: "`resolved_schedules`: a scheduled job's placeholder expression per environment (spec 2026-10-23-configured-schedules)"), `docs/components/D01-graph-schema.md` (the table's row in the derived-tables table, and the "What moved `graph_schema_version`" row), D06 masked-columns table
- Modify: tests hard-coding `"schema_version": 6` (`grep -rn '"schema_version": 6\|schema_version=6\|this build is 6' tests`)
- Test: `tests/application/test_resolved_schedules.py` (new), `tests/storage/test_workspace.py`

**Interfaces:**
- Consumes: `substitute` (Task 1); `workspace.query("scheduled_work")`, `workspace.query("resolved_config")`; the config model's `placeholders` and `key_matching` from the declared catalogs, read the way `resolve_config` reads them (reuse its accessor; do not restate defaults).
- Produces: `record_resolved_schedules(workspace: Workspace, catalogs: list[Catalog]) -> None`; table `resolved_schedules(handler VARCHAR, trigger VARCHAR, environment VARCHAR, value VARCHAR, unresolved_reason VARCHAR)`; named query `resolved_schedules` ordered by `handler, trigger, environment`.

- [ ] **Step 1: Write failing tests** in `tests/application/test_resolved_schedules.py`, with workspaces built from facts the way `tests/application/test_bean_conditions.py` builds them (a `@Scheduled` fact plus `config_entry` facts):
  - `${orders.sweep.cron}` set to `0 0 * * * *` in base and `0 */5 * * * *` in `prod` → rows `(…, "default", "0 0 * * * *", None)` and `(…, "prod", "0 */5 * * * *", None)`.
  - `${orders.sweep.cron:0 0 * * * *}` with the key set nowhere → `0 0 * * * *` in every environment.
  - `${orders.purge.rate}` set nowhere → `(…, value None, "missing_key")` in every environment.
  - A literal cron → no rows. A `#{…}` SpEL expression → no rows.
  - No resolved environment → no rows.
  - Relaxed matching (`${orders.sweep-cron}` vs configured `orders.sweep.cron`) resolves under the Spring model.
  - `scheduled_work`'s own row for each job is unchanged (`resolution` still `unresolved` for a placeholder).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the table, the pass and the pipeline call. A job qualifies when its `expression` contains the model's `placeholders.open`; the lookup for environment `e` reads `resolved_config` rows of `e`, keyed by `normalize_key` when the model's `key_matching` is `relaxed`; a row whose resolved value is NULL answers `(None, its unresolved_reason or "missing_key")`.
- [ ] **Step 4: Export.** Add `_EXPORT_QUERIES["resolved_schedules"]` with `value` masked by `redact_text` through a staged map, the way `_REDACTED_ADDRESSES` does it. Add a test in `tests/storage/test_workspace.py`: a value containing `https://u:p@h` exports masked. The export ratchet test (`test_every_table_and_view_in_the_schema_is_exported`) must pass.
- [ ] **Step 5: Bump `GRAPH_SCHEMA_VERSION` to 7**, update the docs and the hard-coded `6`s, run the full gate. Expected: all pass.
- [ ] **Step 6: Guards** — `schedules.a-PLACEHOLDER-expression-is-read-per-environment` (edit: the pass writes no rows) and `schedules.an-ANNOTATION-default-applies-where-no-environment-sets-the-key` (edit: the lookup ignores the default). Pin and measure: killed.
- [ ] **Step 7: Commit** `feat(schedules): a placeholder schedule is read per environment through the one placeholder rule`.

### Task 3: The document, the fixture, the record

**Files:**
- Modify: `src/sextant/egress/render/document.py` (`_scheduled_work_sections` ~1726; the report carries `resolved_schedules` beside `scheduled_work` — add the field where `pipeline.py`'s report and `api.py:~1075` build it)
- Modify: the fixture `tests/e2e/test_vertical_slice.py` reads scheduled work from (find its `@Scheduled` class) — add the two annotations of spec §3e and the profile-file key; rebuild with `JAVA_HOME=/opt/homebrew/opt/openjdk@21`
- Modify: `docs/COVERAGE.md` §5.12 row 3 → ✅ shipped (cite the spec and pins), then regenerate the §2c grid with `scripts/coverage_matrix.py`; `CHANGELOG.md` (Unreleased `### Added`); `docs/open-issues.md` (new OI: `resolved_peers`' SQL substitution cannot read a `:default`; closes when a reader exists, by moving it onto `substitute`); the spec's Status → BUILT
- Test: `tests/egress/test_render.py`, `tests/e2e/test_vertical_slice.py`

**Interfaces:**
- Consumes: the `resolved_schedules` named query (Task 2).

- [ ] **Step 1: Write failing render tests**: a job with `cron ${orders.sweep.cron:0 0 * * * *}` and rows `default → 0 0 * * * *`, `prod → 0 */5 * * * *` renders, under its row, exactly `as configured in this repository: \`0 0 * * * *\` in \`default\`; \`0 */5 * * * *\` in \`prod\``; two environments sharing a value share one entry (`\`0 0 * * * *\` in \`default\`, \`dev\``); an unresolved environment reads `not set in \`prod\` (missing_key)`; a job with no rows renders byte-identical to today. Values pass the render redactor.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** in `_scheduled_work_sections` and thread `resolved_schedules` through the report.
- [ ] **Step 4: Fixture and e2e.** Add the two annotations and the key, rebuild with JDK 21, and pin in `test_vertical_slice.py`: the document carries both lines (`0 */5 * * * *` from the profile file, the default elsewhere; `missing_key` for the purge rate) and the bundle's `resolved_schedules.parquet` holds the rows. Re-pin any vertical-slice count that moves.
- [ ] **Step 5: Guard** `schedules.the-DOCUMENT-states-a-schedules-configured-values` (edit: the section ignores `resolved_schedules`). Pin and measure: killed.
- [ ] **Step 6: Record.** COVERAGE row → ✅; regenerate §2c and confirm the Spring Boot Async cell reads ✅ (quote the regenerated line in the report); CHANGELOG; the OI; spec Status BUILT.
- [ ] **Step 7: Run** the full gate, `scripts/field_check.py` (six `ok`) and the full guard sweep (`0 survived`).
- [ ] **Step 8: Commit** `feat(render): a configured schedule is stated per environment; Spring Boot Async ✅`.
