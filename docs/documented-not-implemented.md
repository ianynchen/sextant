# Documented but not implemented

**Status: a factual register, opened 2026-09-04 during Phase 2O; entries #1, #2, #3 and #6
updated the same day when Task 6 built what it needed rather than citing it. Fourteen rows
as of the 2O documentation sweep (2026-09-05), which added #10, #11 and #14 and put #8 back
in numeric order** — the file previously held ten rows numbered 1,2,3,4,5,6,7,9,12,8, with
10 and 11 allocated by the pre-dispatch audit and never written, so a reader looking for
either found a gap and no explanation. `docs/RUNBOOK.md` counts six instances of this error
class and every one of them now has a row. Every entry
below was verified in the code at the time of writing — not inferred from a
document. Each names where it is documented, what the code actually does, the
impact, and its disposition.

**Why this file exists.** Phase 2O's spec was written against two mechanisms
this repository documents and has never implemented, and four rounds of
adversarial review did not catch it — because the reviewer read the same
documents the author did and cited the same lines back. A shared false premise
survives review; only execution exposed it. Every entry here was found the same
way: something tried to *use* the mechanism.

The lesson generalises: **for this codebase, a document is not evidence that a
mechanism exists.** A spec that depends on one must verify it in `src/` first.

---

## The register

| # | Mechanism | Documented in | What the code does | Disposition |
|---|---|---|---|---|
| 1 | `detect:` / `detect.coordinates` | D02; declared by all 55 shipped catalogs | **PARTLY CLOSED, 2O Task 6.** Now on the `Catalog` model and read by the loader, and it GATES the **two** styles whose framework rule is conditional on the library — `derived_resource` and `config_join`, `application/resolve/dependencies.py:83`'s `DEPENDENCY_GATED`, applied at `:108-137`. That reaches four catalogs of the 55: `spring-data-rest`, `spring-cloud-stream`, `spring-kafka-media` and `spring-integration`. The loader VALIDATES the coordinate shape for all 55 (`ingress/catalogs/yaml_source.py::_coordinates`) while only those four values are ever compared — the form-two trap in §5.3, worth stating because a grep for a read finds the validation. The MODULE-WIDE catalog activation D02 §12 describes is still not implemented — applied today it would deactivate `spring-mvc.yml` on any Maven module declaring only `spring-boot-starter-web`, because a parsed POM records direct declarations only. | Open, narrowed — needs a resolved classpath under both build systems |
| 2 | `ClasspathEntry` | `domain/facts.py:49` | Still **constructed nowhere**, deliberately (2O Task 6): an entry names a resolved ARCHIVE and its tier, which the Gradle report carries and a parsed POM does not, so filling it from Maven would mean inventing a path. The coordinate half a gate needs is `ModuleFact.dependency_coordinates` instead. | Open — classpath TIERING waits on a resolved classpath |
| 3 | `ModuleFact` | `domain/facts.py:83` | **CLOSED, 2O Task 6.** Written by `application/stages/analyze.py` on every run, carrying the module's identity, kind, languages, roots and `dependency_coordinates`; read back by the `module_dependencies` named query. `classpath` stays empty — entry #2. | Closed (partly: tiering is #2) |
| 4 | `constant` fact kind (`Symbol, value`) | D00 §5 | No `ConstantFact` class. `ClassScanner.visitField` receives ASM's `Object value` — the field's `ConstantValue` attribute — and never reads it. | **Deliberately routed around** in 2O (ruling R11); still unimplemented |
| 5 | `resolves:` / `resolves.direction` | D02 §2c | **CLOSED, 2O Task 10 — and the documented CONDITION was wrong, not merely unbuilt.** `resolves.direction` is on the `Catalog` model, read by the loader, validated and evaluated by `engines/annotation_driven.py` (`_direction_rule`, `_served_owners`) and bound into `derive_endpoints.sql` as `$flip_direction`/`$flip_owners`/`$flip_handlers`. What did NOT ship is `when: {owner_implemented_in_module: true}`: measured (CP-7), Spring serves an implemented interface only where the implementer is a handler bean, so that condition would publish an inbound route for a `@Service` implementation — an endpoint nothing serves. The shipped word is `owner_implemented_by_type_annotated`, naming the controller annotations as catalog data. `resolves.format` is separately retired in D02 §2c itself. | Closed |
| 6 | `default_produces` | D02; 2E's spec and plan | **CLOSED, 2O Task 6.** Read as a TOP-LEVEL catalog key (not under `mapping:`, where D02 first sketched it — the catalog that needed it declares no `mapping` at all) and written into `produces` by `derived_resource`, which refuses a catalog of its own style that declares none. `default_consumes` stays specified-not-used: Data REST negotiates the request side, so no catalog could declare one honestly. | Closed; `default_consumes` open |
| 7 | `root_kind` | D00:181, with a full member list | The token appears **nowhere in `src/`** — not merely the `scheduled` member, the whole concept. | **Open — must be resolved before 2P's Meridian vocabulary is specified** |
| 8 | Rung 5 marker semantics | D02: markers are "package families whose presence **anywhere in the module** is evidence" | Code read annotation FQNs only — narrower than documented. | **CLOSED, 2O Task 2** |
| 9 | Routing-ambiguity "finding" | D01:296 — "that collision is a routing-ambiguity finding" | No findings mechanism exists anywhere in `src/`. D01 describes a *property* of content-derived identity (two handlers sharing one wire contract merge into a single row), not a detector that reports anything. Found 2026-09-04 by the mechanism-existence pass, **before** Task 10 was dispatched against it. Task 10 shipped without one and needed none: where an `@HttpExchange` interface and the controller implementing it derive one route, the two rows share a wire identity and the existing dedup folds them, with the implementing class's method surviving as handler. | Open — no detector, and 2O Task 10 landed on merge precedence instead |
| 10 | Project catalogs — D02 §6's repository-supplied catalog directory | D02 §6; reached through D04 §2's `catalogs:` key | **No repository-supplied catalog is ever loaded.** The catalog set is hard-wired to the installed package's own directory: `api.py:565` → `resources.py::catalogs_dir` (`:34-46`), which resolves `<package root>/catalogs` and raises if it is absent. There is no parameter, no merge and no search path, so a `catalogs:` key has nothing to reach — and the file it would be written in is entry #13's, which aborts every command on an unknown key. Found by the pre-dispatch mechanism-existence audit; the number was allocated then and the row never written. | **Retired — standing ruling** (2O roadmap `:201-205`), recorded with #13, whose amendment boxes carry it: a repository-supplied catalog makes D02's schema a public API, after which every schema change is breaking. NFR-9's stated case is knowingly unmet |
| 11 | D01 §5's ten named queries — `callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`, `paths_between`, `endpoint_for_address`, `trace_of`, `who_uses_shape`, `who_reads_config` | D01 §5 (the enumeration itself, plus §3's "this is what lets `trace_of` …"); repeated in `M09`; built on by `M07:86`, `M04:184`, `D06:206`, `D06:213`, `components/README.md:97` | **None of the ten exists.** Across `src/` and `tests/` the ten names occur exactly once, and that occurrence is `engines/scheduled_work.py:13` citing `trace_of` as a thing that does not exist. The real registry is `storage/duckdb/workspace.py:10`'s `_NAMED_QUERIES`, a different and resolver-internal set (`documents`, `endpoints`, `shapes`, `annotations`, …) read through `Workspace.query`. `trace_of` in particular is cited by five documents, and by `engines/scheduled_work.py`'s docstring as half of the reason scheduled rows are not roots. Found by the pre-dispatch audit; the number was allocated then and the row never written (`B-C1`, principles sweep). | Open — FR-9 and FR-10 have no surface at all. The documentation-debt checkpoint's call: built / designed / retired, per query |
| 12 | `publishing` in the Gradle init script | `sextant-model.init.gradle:100` emits `publishing: p.plugins.hasPlugin("maven-publish")` | **Deliberately unconsumed since 2026-09-04.** Its only reader was `GradleDetector._classify`, removed by the user ruling that publishing says where artifacts go rather than what a module contains. Listed here so it is not rediscovered as an accidental phantom: the emission stays only because removing it is a build-script change (§7). | Open — remove the emission when a build-script change is next authorised |
| 13 | `~/.sextant/config.yml` and the repository-root `sextant.yml` — **both files, whole** | D04 §2 (the table, the precedence rule at `:33`, the merge rule at `:70`); depended on by D02 §6 for project catalogs | **Neither file is ever opened.** `grep -rn "sextant\.yml" src/ \| grep -v "\.sextant\.yml"` → 0; `grep -rEn "\.sextant/(config\|cache)\|expanduser" src/` → 0. The catalog set is hard-wired to the installed package's own directory (`api.py:565` → `resources.py` → `ingress/catalogs/yaml_source.py`; the line was `:554` when this row was written and is corrected here rather than left to drift), `scanners.pin` has no parameter to reach (`ports/scanner.py::select_scanner`), `tools.helm` has no reader. Worse than absent: the file that IS read is the per-module `.sextant.yml`, one character away, with a closed key set — so following D04 §2 in a single-module repository writes those keys into it and **aborts every command**, since all four share the reader. | **Retire the `catalogs:` half — standing ruling** (2O roadmap `:201-205`): a repository-supplied catalog makes D02's schema a public API, after which every schema change is breaking, so it is deliberately unscheduled and NFR-9's stated case is knowingly unmet. The rest of both files is the documentation-debt checkpoint's call. **Done in this pass** (principles sweep `A-C9`): amendment boxes in D04 §2 and D02 §6, and `sextant_config.py` now names this specific mistake instead of saying only that the key is read nowhere |
| 14 | The `filesystem` catalog style | D02 §2, with a full `matches:` grammar — `manifest`, `walk`, `verb_from`, four `segment` patterns | **No engine.** `filesystem` is absent from `application/resolve/endpoints.py`'s `_ENGINES` (`:214-253`), which is the dict a catalog's `style:` is resolved against, so a catalog declaring it raises `CatalogError` from `_engine_for` (`:196-211`) at the top of `derive_endpoints` (`:83`), before `endpoints_reset` — the run aborts rather than degrading, and leaves no half-emptied table. No shipped catalog declares it. Recorded in this sweep after the same pass found D02 §2 counting engines by counting headings. | **Deliberately ahead of implementation** — it is the design for the first non-JVM route shape. **Done in this pass:** D02 §2's section now opens with a "specified here, not yet used" box in the `default_produces` model (#6), and §2's own preamble names the two sections that are not engines |

---

## Impact, calibrated

These are not uniform, and treating them as one severity would be wrong.

**One produced wrong output, and is now closed.** #5: a module that locally
*implements* an `@HttpExchange` interface (legal since Spring 6.1) had an
**outbound row fabricated** — Sextant reported it calling itself — and its
**inbound routes missed entirely**. Two errors in the same rows, and the only
entry where shipped output was actively false rather than merely thin. The
fabrication was closed first by `A-C1`'s SEI fence, which turned it into
silence, and the silence is closed by 2O Task 10's direction flip: such an
interface's rows are now the inbound routes Spring serves, handled by the
implementing class's own methods. The entry is a worked example of why this
register exists in the form it does — the mechanism was absent AND the condition
the document specified for it was itself wrong, so building what D02 said would
have replaced one fabrication with another.

**Three under-report.** #8 left Jackson-bearing modules `unresolved` where the
framework guarantees JSON (now fixed). #6 left format unresolved where a
framework contract is certain (now fixed). #1 meant no catalog could report
*"skipped: the framework is not present"* — **four now can**, and do: the
manifest names `spring-data-rest`, `spring-cloud-stream`, `spring-kafka-media`
or `spring-integration` with the reason whenever the module's build does not
declare that framework, or when the question cannot be answered at all. The
other fifty-one still evaluate against every module, always — which is what
`egress/render/document.py`'s `catalog_module_matching_not_implemented` gap
sentence now says, having claimed until this sweep that the key was read by
nobody.

**Three blocked or reshaped work.** #2/#3 meant no dependency-aware reasoning
existed anywhere; 2O Task 2 fell back to `documents.origin`, which covers only
opt-in extracted libraries. **#3 is now closed** — the module fact is written and
carries the build's declared coordinates — so a later pass could widen that
fallback (`resolve/format.py`'s rung-5 coordinate marker is the obvious
candidate); Task 6 did not, because widening a format rung was not its change.

#4 makes a compile-time constant's *value*
unreachable from field facts — mitigated in practice because JLS 13.1/13.4.9
requires javac to inline such constants at their use sites, so the literal
appears in `call_site` facts, but a constant declared and never used in its own
module stays invisible.

**One is a live risk to the NEXT phase.** #7: the Meridian integration scoped
into 2P specifies a boundary vocabulary derived from D00/D01/D06. `root_kind`
is documented in D00 with a full member list and does not exist in the code. A
vocabulary specified from those documents the way 2O's spec was would be built
against fiction, and the failure would surface at a *consumer* rather than in
our own tests.

---

## Preventing recurrence

Fixing fourteen instances does not fix the mechanism that produced them. Two
proposals, cheapest first:

1. **An architecture test that cross-checks documentation against code.** The
   two highest-value checks: every catalog key D02 declares must be read by
   `yaml_source.py` (or be explicitly listed as reserved-not-yet-read), and
   every fact field D00 declares must exist on the corresponding
   `domain/facts.py` model. Both are mechanical, and either would have caught
   #1, #4 and #7 the day they diverged.
2. **A convention for reserved vocabulary.** Where a document deliberately
   describes something ahead of its implementation, it says so in the document,
   in a form the test above can read. "Specified here, not yet used" (#6) is
   already exactly this — it was honest, and it is the model. The failure mode
   is silence, not intent.

---

## The check that works, demonstrated

Entry #9 was found by grepping `src/` for every mechanism the remaining tasks
cite — minutes of work, and it landed *before* a task was dispatched against a
detector that does not exist. The same pass applied at spec-writing time would
have caught six of the first eight.

This is worth stating because the alternative was tried and failed: **four
rounds of adversarial spec review did not catch entries #1 or #4**, because the
reviewer read the same documents the author did and cited the same lines back.
A shared false premise is invisible to review. It is only visible to a grep.

## Rule for future specs

**Before a spec cites a mechanism as shipped, grep for it in `src/`.** Phase
2O's own experience is the argument: two phantom mechanisms, four adversarial
review rounds, and neither the author nor the reviewers caught it, because all
of them were reading the same documentation.
