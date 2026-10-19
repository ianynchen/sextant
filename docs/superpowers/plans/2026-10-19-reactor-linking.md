# Reactor linking — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: BLOCKED on the six decisions in the spec's §7.** Tasks 2 onward must not start
before they are approved — each one builds a mechanism those decisions shape.

**Goal:** Join the two sides of a cross-service call. Sextant reads that `genai` calls
`POST /owners/{ownerId}/pets` at `customers-service` and that `customers-service` serves
exactly that, and nothing connects them. Measured target: **27 of 32 outbound rows across
three real systems gain a link**, from 0 today.

**The deliverable is the document and the `links` table, not a COVERAGE cell.** No cell in
§5.1 or §5.2 moves — they count whether a row appears, never whether anything joins two rows.
The measure is the yield table in the spec's §1, re-run per task, plus the field pins.

**Spec:** `docs/superpowers/specs/2026-10-19-reactor-linking-design.md` — read §1 (what is
measured), §4 (a gateway route is a path prefix, and why these links are `resolved` and not
`narrowed`) and §7 (the decisions) before Task 1.

**Tech Stack:** Python 3.14, DuckDB over Parquet (federated views, no import), existing
`Workspace` port; `javap` for Task 4's probe.

## Global Constraints

- **No false positives** (standing user rule). **This plan's specific danger is new in kind:**
  every other pass publishes a fact about one module, and a wrong link invents an
  architectural dependency *between* modules, which `M06` calls fabrication rather than
  imprecision — "and an agent will then reason from it". Every ambiguity is `narrowed` with
  candidates or unmatched with a reason; never a pick.
- **No heuristic linking above `name_match`** (`M06`). No scoring, no thresholds, no
  tie-breaking.
- **No runtime prediction.** Report what a router could match; never simulate the router.
  Task 4's `StripPrefix` work is a GATE on a composition, not a rewrite — if it starts
  looking like a filter chain, stop and re-read the spec's §4.
- **The resolve and stitch layers name no framework and no language**
  (`tests/architecture/test_source_rules.py`, `test_language_confinement.py`). Task 4's
  framework knowledge lives in a catalog with a probe, never in `stitch/`.
- **Every framework claim carries a probe with §5.4 provenance**
  (`tests/architecture/test_probe_provenance.py`): a generated table, the version read back
  from the run's own output, never from a parameter.
- **`D01`'s storage rule holds:** two native tables, everything else a view over the bundles.
  The system workspace copies no participant's graph.
- **Fixtures are built with JDK 21** (`JAVA_HOME=/opt/homebrew/opt/openjdk@21`) — javac 27
  renumbers lambdas per method and the stamp hides the mismatch.
- **The gate is** `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh` — run it
  whole and read the exit code. `scripts/check.sh --guards` runs the mutation guards;
  `python scripts/field_check.py` runs the six field pins.
- **New branch** — PR #55 carries `OI-151` and the register corrections.
- **Match the surrounding style** (GUIDELINES §3, §13.5); do not refactor adjacent code.

---

## File Structure

| file | responsibility |
|---|---|
| `src/sextant/application/stitch/__init__.py` | **new** — the matcher; `M06`'s "matching is core computation" |
| `src/sextant/application/stitch/participants.py` | **new** — the reactor's modules and their bundles |
| `src/sextant/application/stitch/links.py` | **new** — steps 1, 2, 4 |
| `src/sextant/application/stitch/gateway.py` | **new** — the route prefix join and its `StripPrefix` gate |
| `src/sextant/application/ports/workspace.py` | the federated view and the two new derivations |
| `src/sextant/storage/duckdb/schema.sql` | `participants`, `links` |
| `src/sextant/storage/duckdb/queries/` | the federated `endpoints` view; the two inserts |
| `src/sextant/cli/app.py` | `system analyze` |
| `src/sextant/egress/render/` | the system document |
| `src/sextant/catalogs/spring-cloud-gateway-properties.yml` | Task 4 — the filters this reads, and the refusal list |
| `scripts/probes/cp40_strip_prefix/` | **new** — Task 4's measurement |
| `docs/components/M00-cli.md`, `M05-sync.md`, `M06-stitcher.md` | the approved amendments, Task 0 |
| `docs/components/D01-graph-schema.md` | `participants`, `links` as built |
| `fixtures/reactor-twoservice/` | **new** — a two-module reactor, one calling the other |

---

## Task 0 — the approved amendments, and nothing else

- [ ] Apply **only** the amendments the user approved in the spec's §7, each naming the
      decision it implements. A refused decision leaves its document untouched and the
      corresponding task below is removed from this plan rather than quietly narrowed.
- [ ] `docs/open-issues.md`: `GAP-2` records which case this closes and which it leaves —
      the register must not read as if `FR-8` were done.
- [ ] Gate. No code yet, so this is the docs tests only.

## Task 1 — the participant set, and the cost measurement the spec promised

- [ ] `stitch/participants.py`: the reactor's non-BOM modules from the same `<modules>` walk
      `analyze` uses, each with its bundle; a module with no bundle is `absent` with that
      reason.
- [ ] `participants` in `schema.sql` per `D01`: service or external, name, aliases, bundle
      location, commit.
- [ ] The federated `endpoints` view over the bundles' Parquet — one view over `M` paths, no
      import, and a bundle unreachable at query time fails naming it (`D01`'s obligation).
- [ ] **Measure `ruoyi-vue-pro`**, the scale case at 7,244 files, and record reads and wall
      time in the spec's §6 beside the counted figures. §8.7 says the number is a design
      input, and this is the one place this design guessed.
- [ ] Gate.

## Task 2 — steps 1, 2 and 4

- [ ] `stitch/links.py`: protocol equality, the discovery-name key, the verb-and-path key,
      and `M06`'s step 4 tier rule. Decision 6's path-only key only if approved.
- [ ] `links` in `schema.sql` per `D01`: outbound endpoint, inbound endpoint, trust fields,
      candidates.
- [ ] `fixtures/reactor-twoservice`: two modules, one calling an address the other serves, so
      the mechanism has a fixture that does not depend on `examples/` being cloned.
- [ ] **Re-run the spec's §1 yield table.** The 18 endpoint links and 9 participant links are
      the acceptance measure; a number below them is a defect in this task, not a new
      baseline.
- [ ] Guards for: a link is never minted where the protocols differ; several survivors are
      `narrowed` with every candidate and never a pick; an unmatched call into an `absent`
      participant is attributed to the gap.
- [ ] Gate, guards, field pins.

## Task 3 — `system analyze`, and the system document

- [ ] `system analyze <reactor-root> [--environment NAME]` in `cli/app.py`, per `M00`'s
      `system` verb set. `--environment` defaults to `default` and selects the
      `resolved_config` values every comparison uses (`M06` step 0).
- [ ] The system document: participants, links, and the honesty lists —
      **unmatched outbound and uncalled inbound separately**, absent participants apart from
      real findings.
- [ ] **The document is the result, not the table** (user ruling, 2026-10-17). A green `links`
      table with a blank document is a failed task.
- [ ] Gate.

## Task 4 — the gateway route as a path prefix

- [ ] `scripts/probes/cp40_strip_prefix/`: what `StripPrefix` removes from a path, read off
      `spring-cloud-gateway-server-webflux`'s own class with `javap`, version stated, §5.4
      provenance. Answer first: does it strip before or after the predicate matched; what on a
      path with fewer than `N` segments; what happens to a trailing slash.
- [ ] `spring-cloud-gateway-properties.yml`: the filters this reads and **the refusal list** —
      `RewritePath`, `SetPath`, `PrefixPath` and anything else unmeasured publish the
      participant link only.
- [ ] `stitch/gateway.py`: the route's literal prefix joined to each inbound row of the named
      service, **gated** on `N` equalling the prefix's segment count. Where it does not, the
      participant link and a recorded refusal naming both numbers.
- [ ] Measured acceptance: `petclinic`'s four routes publish 13 endpoint links
      (`customers` 8, `visits` 3, `vets` 1, `genai` 1); `mall-gateway`'s five publish theirs;
      **every one `resolved`, none `narrowed`** — the spec's §4 states why, and a `narrowed`
      here means the implementation took the wrong reading.
- [ ] A fixture route whose `StripPrefix` disagrees with its prefix, proving the refusal.
- [ ] Gate, guards, field pins.

## Task 5 — close-out

- [ ] `GAP-2` and the register updated with what shipped and what did not, per decision.
- [ ] `COVERAGE.md`: the linking tier's boundary stated — which cases link, which do not, and
      that `M05`'s cross-repository participant set is still unbuilt.
- [ ] CHANGELOG.
- [ ] Full gate, full guard sweep, all six field pins, and the §1 yield table re-run and
      recorded.

---

## What this plan does NOT do

Stated here so no reader takes `FR-8` as delivered:

- **no cross-repository linking** — `M05`, `system.yml`, `system.state.json`, staleness;
- **no overlay or curation** — `M01`, `D03`, `proposals.yml`, human-asserted links;
- **no structural compatibility** — `M06` step 3, and its open decision 4;
- **no path-shape matching** — `/v1/orders/42` against `/v1/orders/{id}`;
- **no external participants**;
- **no message, gRPC or SOAP keys** beyond what protocol equality and wire identity already
  give; `M06`'s open decisions 2 and 3 are untouched.
