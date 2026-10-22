# A controller that exists in one environment only — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Status: ruled 2026-10-22** (spec §6: structured table; a condition is data on the inbound
endpoint, matching never reads it).

**Goal:** COVERAGE's `conditional-controllers` cell (Spring MVC 13/14 → 14/14): a controller
under `@Profile`/`@ConditionalOnProperty` publishes its endpoints with the condition STATED,
structured, and evaluated per environment the module resolves — exact for `@Profile` by the
config layer's own filename rule, read from `resolved_config` for `@ConditionalOnProperty`.

**The deliverable is the document**: Apollo `configservice`'s `GET /` reading "holds in 6 of 8 —
not in `default`, `github`", derived from `endpoint_conditions` rows a machine can read.

**Spec:** `docs/superpowers/specs/2026-10-21-conditional-controllers-design.md` — §2 (the table),
§3b (the pass), §4 (what is NOT evaluated), §6 (the rulings).

## Global Constraints

- **Framework knowledge is catalog data** (D02): the annotations, their argument names and
  their semantics live in a `conditions:` block with a §5.4 probe each, never in code.
- **Stated, not decided**: no row and no link is dropped or added anywhere.
- **Matching never reads a condition** (ruling 2). The stitch tier carries it on the link.
- **Structured first**: the table is the result; the document's two lines are derived from it.
- **Resolve names no framework or language** (`test_source_rules`, `test_language_confinement`).
- Fixtures with JDK 21; gate `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`;
  guards; six field pins.
- **Branch `cov/conditional-controllers`** from `main` after PR #59; PR #60 carries the
  proposal version of the spec — this branch's ruled version wins at merge.

## File Structure

| file | responsibility |
|---|---|
| `scripts/probes/cp42_profile_condition/`, `cp43_on_property_condition/` | §5.4 probes off the Spring jars |
| `src/sextant/catalogs/spring-web.yml`, `spring-mvc.yml` | `conditions:` block |
| `src/sextant/application/ports/catalogs.py` | load and validate `conditions` |
| `src/sextant/storage/duckdb/schema.sql`, `insert_endpoint_conditions.sql`, `workspace.py` | `endpoint_conditions`, its insert, the export map |
| `src/sextant/application/resolve/endpoint_conditions.py` | the pass |
| `src/sextant/application/resolve/pipeline.py` | runs it after `apply_protocol_hints` |
| `src/sextant/egress/render/document.py` | the two detail lines |
| `src/sextant/application/stitch/`, `egress/render/system.py` | a link states its inbound endpoint's conditions |
| `fixtures/orders-service/.../OpsController.java`, `LegacyOrdersController.java` + `application-prod.*` | the fixture pair under `default`/`prod` |
| `docs/components/D01`, `D02`, `M06`/`M07`, `docs/COVERAGE.md`, `docs/open-issues.md`, `CHANGELOG.md` | as built |

---

## Task 1 — the probes and the catalog data

- [ ] CP-42: `@Profile` — `value` is any-of; `!p` negates; read off `spring-context`'s
      `ProfileCondition`/`Profiles.of` with `javap`; version from the jar's own manifest.
- [ ] CP-43: `@ConditionalOnProperty` — `name`/`value` alias, `prefix`, `havingValue` (empty:
      any value but `false`), `matchIfMissing`; read off `spring-boot-autoconfigure`'s
      `OnPropertyCondition`.
- [ ] `conditions:` on `spring-web.yml` and `spring-mvc.yml`, each entry citing its probe;
      the loader validates the block (`profile`/`property` shapes, `by:` required).
- [ ] Gate.

## Task 2 — the table and the pass

- [ ] `endpoint_conditions` in `schema.sql` (spec §2's columns), its insert, the export map,
      D01 row.
- [ ] `resolve/endpoint_conditions.py`: for each inbound row of a catalog declaring
      `conditions`, read the handler type's class-level annotations via
      `conditions.annotation_index`; one row per (condition, environment); `profile` and
      `property` evaluated per §3b, `other` verbatim with `holds = unresolved`.
- [ ] Pipeline: after `apply_protocol_hints`, before the open-questions reset.
- [ ] Unit tests on hand-built facts: any-of, negation, property with `havingValue`, absent
      key with `matchIfMissing` both ways, a placeholder key → `unresolved`, an `other`
      condition verbatim, an unconditional controller writes nothing.
- [ ] Gate.

## Task 3 — the documents, the fixture, the guards

- [ ] Module document: the two detail lines derived from the table; absent on unconditional
      rows.
- [ ] System document: a link whose inbound endpoint carries conditions states them, read
      through the federated view; the matcher untouched.
- [ ] Fixture: `OpsController` under `@Profile("prod")`, `LegacyOrdersController` under
      `@ConditionalOnProperty(name = "orders.legacy", havingValue = "true")` with
      `orders.legacy=true` in `application-prod`; the e2e pin on the document text; every moved
      pin re-pinned with its cause.
- [ ] Guards: the pass writes rows; `profile` negation; `match_if_missing`; a condition never
      drops a row; the matcher ignores conditions.
- [ ] Gate, guards.

## Task 4 — measured close-out

- [ ] `apollo-configservice` through `analyze` + `render`: `GET /` holds in 6 of 8.
- [ ] The field pins; COVERAGE `conditional-controllers` C → ✅ and the rollup regenerated;
      `OI-108` stays open with its closure named; CHANGELOG.
- [ ] Full gate, full guard sweep, six field pins.
