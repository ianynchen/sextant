# Boundary vocabulary, derivation diff, observability map, in-process query — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close register group H — `FR-21` a closed, versioned vocabulary of boundary kinds; `FR-22` `sextant module diff` between two analyses of one module; `FR-23` an observability map per kind written at `analyze`; `FR-24` `diff`, `observability`, a six-question `query` and an options object on `sextant.api`.

**Architecture:** One registry (`application/boundary/vocabulary.py`) names seven kinds with their identity, attribute and evidence columns; one read-only source (`application/boundary/source.py`) opens a workspace or a bundle and answers each kind through a named query; the diff (`application/boundary/diff.py`) is a dictionary join on identity, with both sides masked through the module's redactor; the map (`application/boundary/observability.py`) is a pure function of `metadata.json`; `query` (`application/query/questions.py`) is six functions over tables that exist.

**Tech Stack:** Python 3.13, DuckDB (workspace `.duckdb`, bundle Parquet via `read_parquet`), click, pytest with xdist; fixtures compiled with JDK 21 (`JAVA_HOME=/opt/homebrew/opt/openjdk@21`).

**Spec:** `docs/superpowers/specs/2026-10-22-boundary-vocabulary-and-diff-design.md` — all five decisions ruled 2026-10-22 (§7), builder-check answers in §8.

## Global Constraints

- **Identity is the exposed address** (decision 1): `(protocol, method, path)` for `endpoint`, plus `peer` for `dependency`; bodies are attributes compared by WIRE NAME; `handler`/`caller` are evidence, never compared. For every protocol.
- **Seven kinds, no more** (decision 2): `module`, `endpoint`, `dependency`, `data-contract`, `boundary-property`, `schedule`, `error-handler`. Requirements and conditions are attributes of `endpoint`. Open questions, roots, value resolutions never enter.
- **Refuse, never guess** (decision 3): schema or vocabulary version mismatch → refuse; `sextant_version`/`catalog_hash`/`redaction_set_hash` mismatch → refuse unless `allow_producer_change`, then `producer_changed: true` with both stamps. Different module ids → refuse.
- **The diff is an exit** (spec §3d): both sides pass through the module's redactor before comparison; the output is masked.
- **Measured inputs only** (decision 4): `KNOWN_GAPS` are `stated_boundaries`, never a verdict.
- **Six questions, module scope, in-process only** (decision 5 + sub-ruling): `source`, `callers`, `callees`, `implementations`, `uses`, `impact` (three partitions). No CLI noun, no plugin.
- **Determinism (NFR-1):** every list sorted; `diff(A, A)` is the empty change-set with every kind present at zero; an empty result is a file, never an absent one (NFR-7).
- **Nothing re-derived**: `diff`, `observability` and `query` read what `analyze` wrote (M00's no-analysis rule); `export` copies, never recomputes.
- **No new catalog key**; framework knowledge stays in catalogs (D02). Resolve-layer modules name no framework (`test_source_rules`, `test_language_confinement`); symbol grammar stays in `domain/symbols` (`test_symbol_grammar_confinement`).
- Gate `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`; every new rule carries a `scripts/guard_check.py` guard; six existing field pins plus the seventh this plan adds; per-item loop; branch `h/meridian` from `main` (PR #61 merged).

## Review Focus

1. **A CI bundle against a local workspace** — masked `peer`/`value` on one side, verbatim on the other; must produce zero entries for an unchanged module (Task 4 test `test_a_masked_bundle_and_its_verbatim_workspace_diff_empty`).
2. **A kind with zero rows on both sides** (a module with no schedules) — `summary.schedule` present at all zeros, not absent (Task 4 `test_every_kind_is_present_in_the_summary_at_zero`).
3. **An endpoint whose address is partly unread** (`path` NULL, `method` NULL — `sendDefault`) — identity with NULLs must still join row-to-row and never collapse distinct unread rows into one (Task 3 `test_an_unread_address_keeps_its_rows_apart`).
4. **A manifest written before this plan** (no `catalog_hash`, no `feeds`, no `boundary_vocabulary_version`) — `observability` degrades with the stated reason; `diff` refuses naming the absent stamp (Task 6 `test_an_old_manifest_gets_a_labelled_degraded_map`, Task 4 `test_a_side_missing_a_stamp_is_refused_by_name`).
5. **`impact` on a recursive call graph** — the closure terminates and lists each symbol once (Task 7 `test_impact_terminates_on_recursion`).

---

## File Structure

| file | responsibility |
|---|---|
| `src/sextant/domain/version.py` | `BOUNDARY_VOCABULARY_VERSION = 1` beside the two schema versions |
| `src/sextant/application/boundary/__init__.py` | package: vocabulary, source, diff, observability |
| `src/sextant/application/boundary/vocabulary.py` | the seven `Kind`s: table, identity, attributes, evidence; `KINDS`, `kinds_fed_by(catalog)` |
| `src/sextant/application/boundary/source.py` | `BoundarySource.open(path)` — workspace or bundle, read-only; `rows(kind)`, `producer`, `module_id`, `commit` |
| `src/sextant/application/boundary/diff.py` | `diff_sources(a, b, *, allow_producer_change) -> Diff`; entries, summary, labels, refusals |
| `src/sextant/application/boundary/observability.py` | `observability_of(metadata) -> ObservabilityMap` |
| `src/sextant/application/query/questions.py` | `answer(workspace, question, **args)` — the six questions |
| `src/sextant/storage/duckdb/workspace.py` | named queries `boundary_*`, `question_*`; `attach_read_only` helper for a bundle |
| `src/sextant/egress/render/metadata.py` | writes `boundary_vocabulary_version`, `catalog_hash`, `catalogs_run`, `skipped_catalogs[].feeds`, `observability` |
| `src/sextant/egress/export/manifest.py` | carries the new metadata fields into the manifest untouched |
| `src/sextant/application/stages/analyze.py` | hands `catalog_hash`, `catalogs_run`, `feeds` to `write_metadata` |
| `src/sextant/api.py` | `AnalyzeOptions`, `DiffOptions`, `DiffResult`, `diff()`, `observability()`, `query()` |
| `src/sextant/cli/app.py` | `module diff <a> <b> [--out] [--format json or text] [--allow-producer-change]` |
| `scripts/field_check.py`, `scripts/field-expectations/spring-petclinic-rest.json` | the seventh pin: `diff_against` an older commit |
| `scripts/guard_check.py` | guards `boundary.*`, `query.*` |
| docs | D01 (§3 vocabulary, §7 stamp row), D05 (`metadata.json` fields), D06 (manifest `observability`), M00 (`module diff`), M09 (six questions shipped), `PROJECT.md`, `REQUIREMENTS.md` (FR-10, FR-21–24), register, CHANGELOG |

---

### Task 1: The vocabulary registry and its version stamp

**Files:**
- Modify: `src/sextant/domain/version.py` (after `GRAPH_SCHEMA_VERSION = 3`)
- Create: `src/sextant/application/boundary/__init__.py`, `src/sextant/application/boundary/vocabulary.py`
- Modify: `src/sextant/egress/render/metadata.py:57-70` (signature), the top-level dict (`"schema_version"` sibling)
- Modify: `src/sextant/egress/export/manifest.py:15-40` (`producer`)
- Test: `tests/application/boundary/test_vocabulary.py`, `tests/egress/test_manifest.py`

**Interfaces:**
- Produces: `BOUNDARY_VOCABULARY_VERSION: int = 1`; `@dataclass(frozen=True) class Kind(name: str, table: str | None, where: str | None, identity: tuple[str, ...], attributes: tuple[str, ...], evidence: tuple[str, ...], grounded_in_code: bool)`; `KINDS: dict[str, Kind]` in the order `module, endpoint, dependency, data-contract, boundary-property, schedule, error-handler`; `kinds_fed_by(style: str, direction: str | None, has_shape_model: bool) -> tuple[str, ...]` (spec §4b: `scheduled_work`→`schedule`; `error_advice`→`error-handler`; else by direction → `endpoint`/`dependency`/both; `has_shape_model` adds `data-contract`).
- `metadata.json` top level gains `"boundary_vocabulary_version": 1`; manifest `producer` gains the same key, copied.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_seven_kinds_in_their_order():
    assert list(KINDS) == ["module", "endpoint", "dependency", "data-contract", "boundary-property", "schedule", "error-handler"]

def test_endpoint_identity_is_the_exposed_address_and_the_handler_is_evidence():
    assert KINDS["endpoint"].identity == ("protocol", "method", "path")
    assert "handler" in KINDS["endpoint"].evidence and "handler" not in KINDS["endpoint"].attributes
    assert KINDS["dependency"].identity == ("protocol", "method", "path", "peer")

def test_which_kinds_a_catalog_feeds():
    assert kinds_fed_by("scheduled_work", None, False) == ("schedule",)
    assert kinds_fed_by("error_advice", None, False) == ("error-handler",)
    assert kinds_fed_by("annotation_driven", "inbound", True) == ("endpoint", "data-contract")
    assert kinds_fed_by("single_call", "outbound", False) == ("dependency",)
    assert kinds_fed_by("fluent", "both", False) == ("endpoint", "dependency")

def test_metadata_and_manifest_carry_the_vocabulary_version(analyzed_workspace_copy):  # tests/egress/test_manifest.py
    assert metadata["boundary_vocabulary_version"] == 1
    assert manifest["producer"]["boundary_vocabulary_version"] == 1
```

- [ ] **Step 2: Run** `pytest tests/application/boundary/test_vocabulary.py tests/egress/test_manifest.py -q` — FAIL (`ModuleNotFoundError`, `KeyError`).
- [ ] **Step 3: Implement** `vocabulary.py` as a data table (one `Kind(...)` per row of spec §2), `kinds_fed_by` as a pure function; add the stamp to `version.py` with a comment row in the version table; write it in `metadata.py` beside `schema_version`; copy it in `manifest.py` from `metadata["boundary_vocabulary_version"]` into `producer`.
- [ ] **Step 4: Run** the two files — PASS. Run `pytest tests/architecture -q -n 4` — PASS (D01/D05/D06 rows come in Task 9; the architecture tests that read docs are not touched yet).
- [ ] **Step 5: Commit** `feat(boundary): the seven-kind vocabulary and its version stamp (FR-21)`.

### Task 2: `analyze` records what the map and the diff need

**Files:**
- Modify: `src/sextant/application/stages/analyze.py` (where `write_metadata(...)` is called; `SkippedCatalog` rows), `src/sextant/application/resolve/endpoints.py:95` (`SkippedCatalog` gains `feeds: tuple[str, ...] = ()`)
- Modify: `src/sextant/egress/render/metadata.py` (`write_metadata` gains `catalog_hash: str`, `catalogs_run: Mapping[str, int]`), `src/sextant/api.py:474` (`_catalog_hash` reused at analyze), `src/sextant/api.py:1529-1533` (export reads the hash from metadata, not recomputed)
- Test: `tests/egress/test_manifest.py`, `tests/application/test_pipeline.py`

**Interfaces:**
- Consumes: `kinds_fed_by` (Task 1).
- Produces: `metadata.json` → `"catalog_hash": "sha256:…"`, `"catalogs_run": {"endpoint": 14, "dependency": 11, "data-contract": 9, "schedule": 1, "error-handler": 2}` (counts of catalogs that RAN per kind; `module` and `boundary-property` absent — not catalog-fed), `"skipped_catalogs": [{"catalog_id", "missing_capabilities", "feeds": ["endpoint"]}]`. Manifest `producer.catalog_hash` is COPIED from metadata.

- [ ] **Step 1: Write the failing tests**

```python
def test_metadata_carries_the_catalog_hash_the_exporter_then_copies(analyzed_workspace_copy):
    assert metadata["catalog_hash"].startswith("sha256:")
    assert manifest["producer"]["catalog_hash"] == metadata["catalog_hash"]

def test_each_skipped_catalog_names_the_kinds_it_would_have_fed(analyzed_workspace_copy):
    rsocket = next(s for s in metadata["skipped_catalogs"] if s["catalog_id"] == "spring-rsocket")
    assert rsocket["feeds"] == ["dependency", "endpoint"]   # sorted

def test_catalogs_run_counts_per_kind(analyzed_workspace_copy):
    assert metadata["catalogs_run"]["schedule"] == 1 and metadata["catalogs_run"]["endpoint"] > 5
```

- [ ] **Step 2: Run** — FAIL (`KeyError: 'catalog_hash'`).
- [ ] **Step 3: Implement**: in `stages/analyze.py`, after catalogs load, compute `catalog_hash` (move `_catalog_hash` from `api.py` to `ingress/catalogs/yaml_source.py` as `catalog_hash(dir) -> str` so both call one function), build `catalogs_run` from the catalogs that were NOT skipped via `kinds_fed_by(c.style, c.direction, bool(c.shape_model))`, set `feeds` on each `SkippedCatalog`; `write_metadata` writes all three; `_export` passes `metadata["catalog_hash"]` to `write_manifest`.
- [ ] **Step 4: Run** the two files and `tests/api/test_facade.py` — PASS. The `metadata.json` key set is pinned somewhere? Run `pytest tests/cli tests/e2e -q -n 4` — fix any golden that lists keys, each with its cause.
- [ ] **Step 5: Commit** `feat(analyze): metadata records catalog_hash, catalogs_run and what each skipped catalog feeds`.

### Task 3: A read-only source over a workspace or a bundle, one named query per kind

**Files:**
- Modify: `src/sextant/storage/duckdb/workspace.py` (`_NAMED_QUERIES` gains `boundary_endpoint`, `boundary_dependency`, `boundary_contract`, `boundary_property`, `boundary_schedule`, `boundary_error_handler`; a module-level `open_read_only(path: Path) -> duckdb.DuckDBPyConnection` that ATTACHes a `.duckdb` READ_ONLY or creates views over `graph/*.parquet` for a bundle, so the SAME SQL runs on both)
- Create: `src/sextant/application/boundary/source.py`
- Test: `tests/application/boundary/test_source.py`

**Interfaces:**
- Produces: `class BoundarySource` with `@classmethod open(path: Path) -> BoundarySource` (accepts `<module>/.sextant`, `<module>` (resolves `.sextant`), or a bundle dir holding `manifest.json`), properties `module_id: str`, `commit: str`, `producer: dict[str, object]` (the five stamps; absent keys absent), `environments: list[str]`, `is_bundle: bool`, `module_root: Path | None` (None for a bundle), method `rows(kind: Kind) -> list[dict[str, object]]` — each row carries every identity, attribute and evidence column of the kind; for `endpoint`/`dependency` the body attributes are **field sets**: `request: list[{wire_name, wire_type, wire_format, required, nullable}] | None`, `response: …`, built by joining `request_shape`/`response_shape` to `shape_fields`; `requirements: list[{kind, name, requirement}]`, `conditions: list[{kind, expression}]` (from `endpoint_metadata`/`endpoint_conditions`); `evidence.symbols: sorted list`, `evidence.documents: sorted list of relative_path`; `origin: "module_output" | "dependency"` (from the grounding documents' `origin_tier`; `dependency` where EVERY grounding document is one). `close()`.
- Rows of one kind are GROUPED on identity: several handlers behind one wire identity are one row with several evidence symbols.

- [ ] **Step 1: Write the failing tests** (hand-built workspace via `DuckDbWorkspace.load_facts` as `tests/application/test_endpoint_conditions.py` does, then `derive_endpoints`; plus one on the session fixture's bundle)

```python
def test_a_workspace_and_its_bundle_answer_the_same_rows_for_every_kind(analyzed_fixture, exported_bundle):
    for kind in KINDS.values():
        assert BoundarySource.open(analyzed_fixture).rows(kind) == BoundarySource.open(exported_bundle).rows(kind)  # after masking — see Task 4; here compare identity sets only

def test_several_handlers_behind_one_wire_identity_are_one_row_with_several_symbols(tmp_path):
    # two @GetMapping("/**") handlers in two classes
    rows = source.rows(KINDS["endpoint"]); row = next(r for r in rows if r["path"] == "/**")
    assert len(row["evidence"]["symbols"]) == 2

def test_an_unread_address_keeps_its_rows_apart(tmp_path):
    # two outbound sendDefault calls: method NULL, path NULL, callers differ → still ONE dependency identity (NULL,NULL,NULL,peer)
    # with two evidence symbols — NULLs join as equal here, by design, because the wire is what identifies
    assert len([r for r in rows if r["path"] is None]) == 1 and len(row["evidence"]["symbols"]) == 2

def test_a_contract_row_lists_its_fields_by_wire_name(tmp_path):
    row = next(r for r in source.rows(KINDS["data-contract"]) if r["shape"].endswith("OrderResult#"))
    assert [f["wire_name"] for f in row["fields"]] == ["id", "status", "total"]  # sorted by wire_name

def test_opening_a_path_that_is_neither_workspace_nor_bundle_raises(tmp_path):
    with pytest.raises(NotAnalyzedError): BoundarySource.open(tmp_path)
```

- [ ] **Step 2: Run** `pytest tests/application/boundary/test_source.py -q` — FAIL.
- [ ] **Step 3: Implement**: six named queries in `workspace.py` (each `SELECT` with `ORDER BY` the identity columns, one row per table row — grouping happens in `source.py`); `open_read_only` creates an in-memory connection and either `ATTACH '…/workspace.duckdb' AS w (READ_ONLY)` plus `CREATE VIEW <t> AS SELECT * FROM w.<t>` for the tables the six queries read, or `CREATE VIEW <t> AS SELECT * FROM read_parquet('…/graph/<t>.parquet')`; `BoundarySource.rows` runs the kind's query, groups on identity, attaches bodies/requirements/conditions/evidence/origin from four further reads (`shape_fields`, `endpoint_metadata`, `endpoint_conditions`, `documents`), sorted. `producer` from `metadata.json` (`schema_version`, `provenance.*`, `catalog_hash`, `boundary_vocabulary_version`) or `manifest.json` `producer`.
- [ ] **Step 4: Run** — PASS. `pytest tests/storage -q` — PASS.
- [ ] **Step 5: Commit** `feat(boundary): a read-only source over a workspace or a bundle, one named query per kind`.

### Task 4: The diff

**Files:**
- Create: `src/sextant/application/boundary/diff.py`
- Test: `tests/application/boundary/test_diff.py`

**Interfaces:**
- Consumes: `BoundarySource`, `KINDS`, `Redactor` (`domain/redaction.py`: `redact_value(key, value)`, `redact_address(text)` — use the two the exporter uses in `_EXPORT_QUERIES`).
- Produces: `@dataclass(frozen=True) class Entry(kind: str, change: Literal["added","removed","changed"], identity: dict, from_: dict | None, to: dict | None, evidence: dict, origin: str, compatibility: Literal["compatible","breaking"] | None)`; `@dataclass(frozen=True) class Diff(boundary_vocabulary_version: int, a: dict, b: dict, producer_changed: bool, entries: tuple[Entry, ...], summary: dict[str, dict[str, int]])` with `to_json() -> dict` (keys exactly spec §3b) and `to_text() -> str`; `diff_sources(a: BoundarySource, b: BoundarySource, redactor: Redactor, *, allow_producer_change: bool = False) -> Diff`; exceptions `DiffRefused(SextantError)` carrying the named stamp(s).
- `compatibility` on an `endpoint`/`dependency` body change: `breaking` iff the request gained a field with `required = true` or the response lost a field; else `compatible`; `None` for non-body changes.

- [ ] **Step 1: Write the failing tests** (two hand-built workspaces written row-by-row through `workspace.derive`/direct inserts, as `test_workspace.py` does)

```python
def test_identical_sides_produce_the_empty_change_set_with_every_kind_at_zero(two_equal_sides):
    d = diff_sources(a, a, redactor)
    assert d.entries == () and d.summary == {k: {"added": 0, "removed": 0, "changed": 0} for k in KINDS}

def test_every_kind_is_present_in_the_summary_at_zero(two_equal_sides):  # even kinds with no rows anywhere
    assert set(d.summary) == set(KINDS)

def test_a_moved_controller_is_no_entry_and_a_new_route_is_added(moved_and_added):
    # side B: same routes, handler symbols renamed to …/v1/…V1; plus GET /api/v2/owners
    assert [(e.kind, e.change, e.identity["path"]) for e in d.entries] == [("endpoint", "added", "/api/v2/owners")]

def test_a_response_field_added_is_a_compatible_change_with_from_and_to(field_added):
    e = d.entries[0]
    assert (e.kind, e.change, e.compatibility) == ("endpoint", "changed", "compatible")
    assert [f["wire_name"] for f in e.from_["response"]] == ["id", "name"] and [f["wire_name"] for f in e.to["response"]] == ["id", "name", "phone"]

def test_a_required_request_field_added_is_breaking(required_added): assert d.entries[0].compatibility == "breaking"
def test_a_response_field_removed_is_breaking(field_removed): assert d.entries[0].compatibility == "breaking"

def test_a_contract_with_a_new_field_is_changed_and_names_the_field(contract_changed):
    assert d.entries[0].kind == "data-contract" and d.entries[0].to["fields"]["phone"]["wire_type"] == "string"

def test_a_masked_bundle_and_its_verbatim_workspace_diff_empty(fixture_workspace, fixture_bundle):
    assert diff_sources(BoundarySource.open(fixture_bundle), BoundarySource.open(fixture_workspace), redactor).entries == ()

def test_different_graph_schema_versions_refuse_by_name(stamped_sides):
    with pytest.raises(DiffRefused, match="graph_schema_version 2 vs 3"): ...

def test_different_sextant_versions_refuse_unless_allowed_and_then_label(stamped_sides):
    with pytest.raises(DiffRefused, match="sextant_version"): diff_sources(a, b, redactor)
    assert diff_sources(a, b, redactor, allow_producer_change=True).producer_changed is True

def test_different_module_ids_refuse(…); def test_a_side_missing_a_stamp_is_refused_by_name(…)  # "catalog_hash absent on a"

def test_entries_are_sorted_by_kind_change_identity(…); def test_to_json_has_exactly_the_spec_keys(…)
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `diff.py`: refusals first (version equality on the five stamps; `module_id` equality); mask both sides (`path`, `peer` through `redact_address`; `boundary-property.value` through `redact_value(key, value)`; a bundle side is already masked and masking is idempotent); index each side's rows by identity tuple; added = in b only, removed = in a only, changed = both and any attribute differs (`from_`/`to` carry ONLY differing attributes); body comparison on field sets keyed by `wire_name`; `compatibility` by the rule above; `summary` over `KINDS` in order; `to_text` prints the summary table then one line per entry.
- [ ] **Step 4: Run** — PASS. Measure on the two real pairs from spec §1 (fixture before/after #61 via the worktree recipe in the spec; petclinic `f957c77` vs `4cd8e1b`) and record the numbers in the spec's §1 if they differ from the pre-build measurement.
- [ ] **Step 5: Commit** `feat(boundary): the derivation diff — identity join, attribute-level changes, compatibility labels, refusals (FR-22)`.

### Task 5: `api.diff`, `DiffOptions`, `sextant module diff`

**Files:**
- Modify: `src/sextant/api.py` (dataclasses beside `ExportResult`; `diff()` beside `export()`; `_redactor_for` reused — for two bundle sides, the redactor is the built-in set, since no module root exists)
- Modify: `src/sextant/cli/app.py` (after `module_export`)
- Test: `tests/api/test_facade.py`, `tests/cli/test_app.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class DiffOptions(allow_producer_change: bool = False)`; `@dataclass(frozen=True) class DiffResult(diff: Diff, written: Path | None)`; `def diff(a: Path, b: Path, *, options: DiffOptions = DiffOptions(), out: Path | None = None) -> DiffResult` — writes `diff.json` to `out` when given; CLI `sextant module diff A B [--out PATH] [--format json or text] [--allow-producer-change]`, JSON to stdout by default, `click.ClickException` on `DiffRefused`.

- [ ] **Step 1: Write the failing tests**

```python
def test_diff_of_a_workspace_with_itself_is_empty_and_lists_every_kind(module_root):
    result = api.diff(module_root, module_root)
    assert result.diff.entries == () and set(result.diff.summary) == set(KINDS)

def test_cli_diff_prints_json_with_summary_and_entries(module_root):
    out = CliRunner().invoke(cli, ["module", "diff", str(module_root), str(module_root)])
    assert out.exit_code == 0 and json.loads(out.output)["summary"]["endpoint"] == {"added": 0, "removed": 0, "changed": 0}

def test_cli_diff_text_format_prints_the_summary_table(module_root): assert "| kind | added | removed | changed |" in out.output
def test_cli_diff_refusal_is_a_click_error_naming_the_stamp(stale_copy): assert out.exit_code != 0 and "graph_schema_version" in out.output
def test_diff_writes_the_file_when_out_is_given(module_root, tmp_path): assert (tmp_path / "diff.json").is_file()
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**. **Step 4: Run** `tests/api tests/cli -q -n 4` — PASS.
- [ ] **Step 5: Commit** `feat(api,cli): module diff (FR-22, FR-24)`.

### Task 6: The observability map

**Files:**
- Create: `src/sextant/application/boundary/observability.py`
- Modify: `src/sextant/egress/render/metadata.py` (writes `"observability": observability_of(metadata_so_far).to_json()` as the LAST key, computed from the dict being written), `src/sextant/egress/export/manifest.py` (copies `observability`), `src/sextant/api.py` (`observability(path: Path) -> ObservabilityMap` reading `metadata.json` or a bundle's `manifest.json`)
- Test: `tests/application/boundary/test_observability.py`, `tests/egress/test_manifest.py`, `tests/api/test_facade.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Verdict(verdict: Literal["observable","partial","not-observable"], reasons: tuple[str, ...])`; `@dataclass(frozen=True) class ObservabilityMap(boundary_vocabulary_version: int, kinds: dict[str, Verdict], attributes: dict[str, dict[str, Verdict]], stated_boundaries: tuple[str, ...])` with `to_json()`; `observability_of(metadata: Mapping[str, object]) -> ObservabilityMap`.
- Rules (spec §4a/§4b, decision 4): for each kind with `grounded_in_code`: `uncovered` non-empty → reason `uncovered files: N (first three named)`; `coverage.partial_documents > 0` → reason; each skipped catalog whose `feeds` contains the kind → reason `catalog skipped: <id> (<missing_capabilities joined>)`; `module.dependency_source == "declared"` → reason on `dependency` and `data-contract`; verdict `observable` with no reasons, `not-observable` when `catalogs_run.get(kind) == 0` and at least one skipped catalog feeds it, else `partial`. Attributes: `endpoint.format` partial with reason `N of M formats unresolved` when `coverage.format` (add the count to `coverage` in `metadata.py` from `report.endpoints`) has unresolved > 0; `dependency.peer` likewise from outbound rows with `peer IS NULL`. A metadata without `catalogs_run` → every code-grounded kind `partial` with reason `catalog kinds unrecorded: manifest predates boundary vocabulary 1`. `stated_boundaries = tuple(metadata["gaps"])`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_clean_manifest_is_observable_everywhere_except_what_it_measured(fixture_metadata):
    m = observability_of(fixture_metadata)
    assert m.kinds["endpoint"].verdict == "partial" and any("spring-rsocket" in r for r in m.kinds["endpoint"].reasons)
    assert m.kinds["boundary-property"].verdict == "observable"
    assert m.attributes["endpoint"]["format"].verdict == "partial"

def test_an_uncovered_file_degrades_every_code_grounded_kind_and_names_it(): ...
def test_a_kind_whose_every_catalog_was_skipped_is_not_observable(): ...
def test_the_static_gap_list_is_stated_never_a_verdict():
    m = observability_of({**base, "gaps": ["config_as_code_not_read"]})
    assert m.kinds["boundary-property"].verdict == "observable" and "config_as_code_not_read" in m.stated_boundaries
def test_an_old_manifest_gets_a_labelled_degraded_map():
    m = observability_of({k: v for k, v in base.items() if k not in ("catalogs_run",)})
    assert m.kinds["endpoint"].verdict == "partial" and "predates boundary vocabulary 1" in m.kinds["endpoint"].reasons[0]
def test_metadata_and_manifest_carry_the_map(analyzed_workspace_copy): assert manifest["observability"] == metadata["observability"]
def test_api_observability_reads_a_bundle_as_well_as_a_workspace(module_root, exported_bundle): ...
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** (pure function; no I/O in `observability.py`). **Step 4: Run** — PASS; `pytest tests/cli tests/e2e -q -n 4` for any key-set golden.
- [ ] **Step 5: Commit** `feat(boundary): the observability map, per kind from measured inputs, written at analyze and carried into the bundle (FR-23)`.

### Task 7: The six questions and the options object

**Files:**
- Create: `src/sextant/application/query/questions.py`
- Modify: `src/sextant/storage/duckdb/workspace.py` (`_NAMED_QUERIES`: `question_source`, `question_callers`, `question_callees`, `question_implementations`, `question_uses`, `question_impact_step`)
- Modify: `src/sextant/api.py` (`AnalyzeOptions`, `analyze(path, *, allow_resolve=False, options: AnalyzeOptions | None = None)`, `query(path: Path, question: str, **args) -> dict | list`)
- Test: `tests/application/query/test_questions.py`, `tests/api/test_facade.py`

**Interfaces:**
- Produces: `QUESTIONS = ("source", "callers", "callees", "implementations", "uses", "impact")`; `answer(workspace: Workspace, question: str, *, symbol: str) -> list[dict] | dict`; each list item `{"symbol", "file", "line_start", "line_end"}` (from `symbols` ⨝ `documents.relative_path`); `impact` returns `{"definite": [...], "possible": [...], "unknown_regions": [...]}` where `definite` = reached through `call_edges` with `resolution = 'resolved'` or `type_hierarchy`/signature uses only, `possible` = reached through at least one `narrowed` edge, `unknown_regions` = the `unresolved` call edges and `type_hierarchy` rows with `scanned = false` the walk met, each as `{"symbol", "reason"}`; every list sorted by symbol; an unknown question or an unknown symbol raises `ConfigurationError` naming the valid set / the symbol. `uses` = symbols whose `signature` JSON names the type in a parameter or return (`json_extract` over `parameters[*].type.symbol`, `returns.symbol`) plus `type_hierarchy` children. `AnalyzeOptions(allow_resolve: bool = False, shadow: bool = False, workspace_dir: Path | None = None)`.

- [ ] **Step 1: Write the failing tests** (on the session fixture `module_root`; symbols from `orders-service`)

```python
def test_source_names_the_file_and_lines_of_a_method(module_root):
    [row] = api.query(module_root, "source", symbol=ORDER_CONTROLLER_GET)
    assert row["file"].endswith("OrderController.java") and row["line_start"] <= row["line_end"]

def test_callers_and_callees_are_one_hop_each_way(module_root): ...
def test_implementations_lists_the_types_implementing_an_interface(module_root): ...  # BillingClient's implementors
def test_uses_asks_about_a_type_not_a_function(module_root): ...  # OrderResult: returned by N methods
def test_impact_returns_three_partitions_never_one_count(module_root):
    r = api.query(module_root, "impact", symbol=ORDER_RESULT)
    assert set(r) == {"definite", "possible", "unknown_regions"} and r["definite"]
def test_impact_terminates_on_recursion(tmp_path): ...  # hand-built a→b→a
def test_an_unknown_question_is_refused_naming_the_six(module_root):
    with pytest.raises(api.ConfigurationError, match="source, callers, callees, implementations, uses, impact"): api.query(module_root, "trace", symbol="x")
def test_analyze_accepts_an_options_object_equivalent_to_the_flags(module_root): ...
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**: six named queries; `impact` as a Python breadth-first walk over `question_callers` + `question_uses` results with a visited set, carrying the weakest resolution seen on the path. **Step 4: Run** — PASS; `pytest tests/architecture -q -n 4` — PASS (`test_language_confinement` etc.).
- [ ] **Step 5: Commit** `feat(api): six in-process questions and AnalyzeOptions (FR-24, FR-10 partial)`.

### Task 8: Guards and the seventh field pin

**Files:**
- Modify: `scripts/guard_check.py` (guards: `boundary.the-HANDLER-is-evidence-never-identity` — anchor: `KINDS["endpoint"]` identity tuple; `boundary.a-REQUIRED-request-field-added-is-breaking`; `boundary.both-sides-pass-through-the-REDACTOR`; `boundary.a-PRODUCER-mismatch-refuses-unless-allowed`; `boundary.the-static-GAP-list-is-stated-never-a-verdict`; `boundary.every-kind-is-in-the-summary-at-zero`; `query.impact-returns-THREE-partitions`), each pinned by a Task 4/6/7 test via `@pytest.mark.pins`
- Modify: `scripts/field_check.py` (`diff_against: {"commit", "expect": {"endpoint": {"added": 2, "removed": 0, "changed": 0}, "data-contract": {"added": 2, …}, …}}` — build the older commit in a worktree under `examples/<repo>-at-<commit>`, analyze, `api.diff(old, pinned)`, compare `summary`), `scripts/field-expectations/spring-petclinic-rest.json` (`f957c77`, the §1b numbers)
- Test: `tests/scripts/test_guard_check.py` unchanged; run `python scripts/guard_check.py boundary.* query.*`

- [ ] **Step 1: Add the guards and `pins` markers.** Run `JAVA_HOME=… .venv/bin/python scripts/guard_check.py <the seven ids>` — every one `killed`.
- [ ] **Step 2: Add the pin.** Run `JAVA_HOME=… .venv/bin/python scripts/field_check.py spring-petclinic-rest` — `ok`, with the diff summary matching spec §1b (`endpoint +2/−0/0`, `data-contract +2/−0/0`, `dependency`, `boundary-property`, `schedule`, `error-handler` all zero; record `changed` for `data-contract` as measured — §1b saw none).
- [ ] **Step 3: Commit** `test(boundary): seven guards and the petclinic two-commit field pin`.

### Task 9: Documents as built, register close

**Files:**
- Modify: `docs/components/D01-graph-schema.md` (new §3 subsection "The boundary vocabulary" with spec §2's table; §7 stamp table row `boundary_vocabulary_version`; §5 note: six questions now shipped), `docs/components/D05-manifest-and-state.md` (`metadata.json`: `catalog_hash`, `catalogs_run`, `skipped_catalogs[].feeds`, `observability`, `boundary_vocabulary_version`), `docs/components/D06-bundle-format.md` (manifest example gains `observability` and the two producer keys), `docs/components/M00-cli.md` (`module diff`), `docs/components/M09-query.md` (six questions shipped in-process; the rest named as waiting, the gate), `docs/PROJECT.md` (`module diff` delivered; agent-surface row amended), `docs/REQUIREMENTS.md` (FR-10 partial; FR-21–24 states; FR-24 clause table four of four), `docs/java-kotlin-delivery-list.md` (Meridian section DELIVERED; ```delivery row `Meridian | — |` empty; §4 row 7 DONE), `docs/open-issues.md` (OI-25/OI-83's `trace_of`/named-query notes updated), `CHANGELOG.md`
- Verify: `pytest tests/architecture -q -n 4` (feature-delivery, markdown tables, probe provenance, doc consistency); `python scripts/coverage_matrix.py --check`

- [ ] **Step 1: Write the docs.** **Step 2: Run** `tests/architecture` — PASS. **Step 3: Full gate** `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh` — green. **Step 4: Full guard sweep and all seven field pins** — green. **Step 5: Commit** `docs: boundary vocabulary, diff, observability and query as built; Meridian row closed`. Push `h/meridian`, open the PR with the measured numbers (§1 and Task 4 step 4) in its body.
