# One reason list everywhere (OI-321) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Every "not resolved" answer carries one general reason from `values._REASONS` plus a
detail text that says where; no other reason word is written anywhere.

**Architecture:** three producers change (config resolution + the peer join, method lookup,
pass-through), each gains a detail; storage gains detail columns; graph schema 15 → 16; the
document reads the stored detail.

**Tech Stack:** Python resolve layer, DuckDB SQL, Markdown document renderer.

**Spec:** `docs/superpowers/specs/2026-11-05-one-reason-list-design.md` (approved).

## Global Constraints

- The only reason words: `external`, `non_enumerable`, `not_readable`, `escapes`, `no_writer`,
  `cycle` (import from `sextant.application.resolve.values` — never retype a list).
- `external` vs `not_readable` (spec §2): external when the code/file that would answer is not in
  what Sextant reads; not_readable when it is there but not followed — decided from the facts at
  the place the answer is made, never from a table of old words.
- A found answer has no reason. Detail is free text for a person; no code branches on it.
- No change to which rows resolve. Before/after: run
  `<scratchpad>/oi321-sweep.sh <src-dir> <out-dir>` (baseline already in
  `<scratchpad>/oi321-out-before`, made from `<scratchpad>/oi321-before/src`), then
  `diff -r`; every changed line must be a reason/detail column or document text about a reason.
- JDK 21 first on PATH (`JAVA_HOME=/opt/homebrew/opt/openjdk@21`) for tests and sweeps.
- ASD-STE-100 comments; GUIDELINES §1–4, §13.5; guards per `scripts/guard_check.py`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A config key set in one environment and missing in another: `external` + a detail naming the
   environment, per row (Task 1).
2. `placeholder_cycle` → `cycle`; a peer with two placeholders → `not_readable` (Task 1).
3. Coverage figure keeps "scanning decision" (`external`) apart from "defect" (`not_readable`)
   and counts found bodies as `resolved` (Task 2).
4. A pass-through `produced_by` whose maker IS in the module but not followed →
   `not_readable`; one in a library → `external` (Task 3).
5. A guard test that fails if any table/graph attribute in spec §4 holds a word outside the list
   (Task 3).

---

### Task 1: Configuration values

**Files:** `application/resolve/config.py` (`UNRESOLVED_REASONS` removed; each unresolved row
carries `unresolved_reason` ∈ general list and `unresolved_detail`), `resolve/resolved_schedules.py`,
`storage/duckdb/schema.sql` (+`unresolved_detail TEXT` on `resolved_config`, `resolved_schedules`),
`insert_resolved_config.sql`, `insert_resolved_schedules.sql`, `workspace.py` (`resolved_peers`
query: reasons and detail; the `'missing_key'` defaults), `application/boundary/vocabulary.py` +
`source.py` (attribute `unresolved_detail`), `domain/version.py` (`GRAPH_SCHEMA_VERSION = 16`,
with its history note), `bean_conditions.py:1613`, `enrich/brief.py:217`,
`egress/render/document.py` (≈2084–2094, 3171: show reason then detail), D01 (≈760, 1199, 1355),
D02 ≈5580, D06 ≈403, CHANGELOG.

Mapping (spec §3a): missing_key/environment/remote_source → `external`; placeholder_cycle →
`cycle`; multi_placeholder → `not_readable`. Details as the spec's examples (key, environment,
variable / config-server URL, the cycle's keys, the expression).

- [ ] Tests first (red): unit tests per mapping row; the peer join's two-placeholder row; a key
  resolved in `dev`, missing in `prod`.
- [ ] Implement; tests green; sweep diff judged; commit.

### Task 2: Method lookup

**Files:** `domain/closed_sets.py` (the method-resolution set reduced to what is still needed),
`application/resolve/dispatch.py`, `call_edges.py`, `pipeline.py` (coverage buckets:
`resolved` or the reason), `storage/duckdb/schema.sql` (`method_resolution.reason` NULL when found,
+`detail TEXT`), `insert_method_resolution.sql`, `workspace.py` (`method_resolution_distribution`:
`coalesce(reason, 'resolved')`), `bean_conditions.py` (≈354, any use of the words),
`egress/render/document.py` (≈3139), D00 §4 (drop the `method_resolution` list; say found = no
reason, else general reason + detail).

Mapping (spec §3b): declared_here/inherited → no reason; owner_not_scanned/ancestor_not_scanned →
`external`; no_declaration_found → `not_readable`; details name the class (and the unscanned
ancestor).

- [ ] Tests first (red): each of the five old outcomes; coverage distribution buckets.
- [ ] Implement; tests green; sweep diff judged; commit.

### Task 3: Pass-through, the guard, documents

**Files:** `application/resolve/shapes/pass_through.py` (`unread` entries `{reason, detail}`; the
`how` constants and `_UNREAD_PHRASES` become the detail made once at the place the answer is made),
`egress/render/document.py` (`_PASS_THROUGH_PHRASES` removed; reads the stored detail),
`engines/config_join.py:1942` if it carries a `how`; a new guard test
`tests/application/test_one_reason_list.py`; COVERAGE/M-docs that list the old words;
`docs/open-issues.md` rows for anything logged.

Mapping (spec §3c): handed_to/stored_in → `escapes`; produced_by/of_type/from_field/no_body/argument
→ `external` when the method or type is not in the scanned code (no document for it in the
workspace), otherwise `not_readable`.

- [ ] Tests first (red): one per old `how`, both sides of the external/not_readable split where the
  shape allows it.
- [ ] Guard test: on the fixtures the e2e suite already analyses, read every column/attribute in
  spec §4 and fail on any value outside `values._REASONS` (and NULL where a body/value was found).
- [ ] `rg` the repo for each old word; none is left in code or current-state docs (CHANGELOG
  history and the spec's mapping tables excepted).
- [ ] Full gate; `scripts/field_check.py` six pins ok; sweep diff judged; commit.
