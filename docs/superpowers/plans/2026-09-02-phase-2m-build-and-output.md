# Phase 2M Implementation Plan — Build systems, project shape, rendered-output quality

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gradle detection via the wrapper + init script, Maven reactor discovery with per-module analysis, and the rendered-output quality fixes (mermaid `$`, typed HTML sections, readability rulings), per the approved spec.

**Architecture:** a second `Detector` implementation beside Maven's; `stages/analyze` learns to loop over modules; the assembled-section model gains typed machine kinds so the HTML serializer never sees opaque markdown; readability changes land as one deliberate golden update after the byte-identity of the typed refactor is proven.

**Tech Stack:** existing (Python 3.12, DuckDB, pydantic, click); Gradle invoked as a subprocess (the target's own wrapper); no new Python dependencies.

**Spec:** docs/superpowers/specs/2026-09-02-phase-2m-build-and-output-design.md (binding; revised after adversarial review — its rulings are requirements, including §1's failure taxonomy, §1c's notes field, §2's modules.json, §5b's MachineDetail and section-index placement, §5c's always-emitted detail entries).

## Global Constraints

- No network in tests; the two per-build-system CI prime steps are the only fetch-allowed places; `field_check.py` is opt-in and never a check.sh gate.
- Determinism NFR-1: all outputs byte-stable; init-script JSON written to a named file, never stdout.
- DR-6: build-tool failures are reported in the tool's own words — never repaired, never guessed.
- Unresolved-is-an-answer: refusals name their reason; module kinds are never guessed.
- Framework names in catalogs only; no resolve-engine changes anywhere in this phase.
- Match existing style (GUIDELINES §13.5); no adjacent refactors; scripts/check.sh green at every commit; suite baseline 1314 passed / 2 skipped, zero regressions.
- uv.lock is never committed. No version bumps.
- Golden files change in exactly one commit (Task 6's), per spec §7.

---

### Task 1: Detect notes, allow_resolve plumbing, detection-first analyze

**Files:**
- Modify: `src/sextant/application/ports/detector.py` (RepositoryModel gains `notes: tuple[str, ...] = ()`), `src/sextant/application/stages/analyze.py` (thread `allow_resolve`; run detection FIRST), `src/sextant/cli/app.py` (`--allow-resolve` flag on `module analyze`; workspace create / render-clear moved AFTER detection succeeds), `src/sextant/ingress/detect/maven.py` (accept + forward `allow_resolve`; emit a note when Gradle files coexist), metadata write site (notes land in `metadata.json` as `detect_notes`).
- Test: `tests/application/test_analyze_stage.py`, `tests/cli/test_app.py`, `tests/ingress/test_maven_detector.py`.

**Interfaces:**
- Consumes: existing `Detector` port, `detect(path)` call in `stages/analyze.py:133`.
- Produces: `RepositoryModel.notes: tuple[str, ...]`; `detect(path, allow_resolve: bool = False)` signature on the port (Maven forwards it to its existing parameter); `metadata.json` key `detect_notes: [str]` (empty list when none). Task 3 consumes both.

- [ ] **Step 1: failing tests** — a repo dir containing BOTH `pom.xml` and `build.gradle` detects as Maven with one note (`"gradle build files present; maven selected"` — exact string in the test); `detect_notes` appears in metadata.json (empty for the plain fixture); `sextant module analyze --allow-resolve` reaches the detector (spy); a failing detection leaves NO workspace directory behind (today's order creates one first — pin the new order by asserting the dir is absent after a refused detect).
- [ ] **Step 2: implement** (notes threaded detector → model → metadata; flag threaded CLI → stage → detect; reorder module_analyze).
- [ ] **Step 3: suite; hooks; commit** `feat: detect notes, --allow-resolve, detection-first analyze`.

### Task 2: Maven reactor walk, per-module analyze, modules.json

**Files:**
- Modify: `src/sextant/ingress/detect/maven.py` (the `<modules>` walk), `src/sextant/application/stages/analyze.py` (loop over service modules instead of `modules[0]`), `src/sextant/cli/app.py` (multi-module summary output; `--workspace` refused at a multi-module root; `modules.json` written at the root; `render`/`enrich`/`export` refuse-with-module-list when `modules.json` exists and no workspace does).
- Create: `fixtures/orders-reactor/` — aggregation-only parent `pom.xml` (`<modules><module>../orders-service</module><module>billing-lib</module></modules>` is NOT the shape: the parent lives at `fixtures/orders-reactor/pom.xml` with `<module>orders-service-link</module>` — see Step 1; the spec requires adopting `fixtures/orders-service` unchanged, so the reactor references it by relative path `<module>../orders-service</module>`, which Maven permits) plus `fixtures/orders-reactor/billing-lib/` (a `<parent>`-declaring sibling with one class, no endpoints).
- Test: `tests/ingress/test_maven_detector.py`, `tests/cli/test_app.py` (multi-module e2e over the reactor fixture).

**Interfaces:**
- Consumes: Task 1's notes + detection-first order.
- Produces: `RepositoryModel.modules` with N entries (each `ModuleModel` carrying its dir); `modules.json` at the analyzed root: `{"modules": [{"dir": str, "module_id": str, "kind": str, "analyzed": bool}]}`, sorted by dir; the refusal message form `"<path> is a multi-module root; analyze it, then run this command against one of: <dirs>"`. Task 3 emits the same shapes for Gradle.

- [ ] **Step 1: failing detector tests** — the reactor parent yields modules [orders-service (service), billing-lib (undetermined — Maven never returns library, spec §2)]; cycle in `<modules>` refused with the cycle named; child coordinates inherit per existing rules; `fixtures/orders-service/pom.xml` byte-unchanged in this task (its standing no-parent comment updated to say "aggregation-only reactors may reference this module; it must never gain a `<parent>`" — the ONLY edit).
- [ ] **Step 2: failing CLI tests** — analyze at the reactor root: orders-service analyzed into its own `.sextant` (endpoint count matches the single-module run exactly), billing-lib skip-listed with kind, summary table printed, `modules.json` written; analyze at plain `fixtures/orders-service` byte-identical behaviour to today (golden pin untouched); `render` at the reactor root refuses naming both module dirs; one module failing (poison a copy) stops the run with that module named.
- [ ] **Step 3: implement; suite; hooks; commit** `feat: maven reactor discovery — every service module, its own workspace`.

### Task 3: GradleDetector

**Files:**
- Create: `src/sextant/ingress/detect/gradle.py`, `src/sextant/ingress/detect/sextant-model.init.gradle` (packaged resource; plain Groovy so it runs on both DSLs), `fixtures/gradle-orders/` (Kotlin-DSL settings; `service-app/` with 3 Spring MVC endpoints; `pricing-lib/` applying `maven-publish`), captured init-script outputs under `tests/ingress/gradle-captures/`.
- Modify: `src/sextant/cli/resources.py` or detector-local resource loading (init script path), `.github/workflows/pr.yml` (Gradle prime step: warm wrapper distribution + fixture dependencies — the one fetch-allowed Gradle step), detector selection (Gradle after Maven, per §1 accepts()).
- Test: `tests/ingress/test_gradle_detector.py` (unit, over captures), one integration test invoking the real wrapper (marked, offline, depends on the primed caches; stale-guard per the session-fixture precedent).

**Interfaces:**
- Consumes: Task 1's `notes`/`allow_resolve`; Task 2's multi-module analyze loop and `modules.json` (Gradle modules flow through the same code).
- Produces: `GradleDetector.accepts()/detect()` returning the same `RepositoryModel`/`ModuleModel`/`LibraryRoot` shapes Maven produces. Init-script JSON schema (pinned by capture tests): `{"projects": [{"path", "group", "name", "version", "dir", "sourceRoots": [..], "resourceRoots": [..], "classesDirs": [..], "publishing": bool, "classpath": [{"path", "group?", "name?", "version?"}]}]}`.

- [ ] **Step 1: the init script** — registers `sextantModel` on the root project; at execution time walks `allprojects`, resolves `compileClasspath` (Java plugin projects only; a project without it reports empty classpath and no classesDirs), writes the JSON to the file named by `-Psextant.out`. No stdout. Hand-verify once against `fixtures/gradle-orders` and commit the captured JSON as the first capture file.
- [ ] **Step 2: failing unit tests over captures** — coordinates, LibraryRoots (coordinates from component ids; path-only entries → `libraries_not_resolved`), service/library kinds (publishing → library — the Gradle-only deviation, spec §2), classes dirs, missing-`group` refusal (`"gradle project <name> declares no group — cannot form a module id"`), version `unspecified` refusal, wrapper-absent fallback note, cold-distribution failure class (`"gradle distribution not present"` — simulate by capture of the wrapper error), offline-refusal substring (`"--offline"` in Gradle's own message), `--no-configuration-cache` + `-q` + `-Psextant.out` present in the composed argv (argv pinned as data).
- [ ] **Step 3: the integration test + CI** — real `./gradlew` run over `fixtures/gradle-orders` (offline, after priming); pin endpoint count 3 end-to-end through `module analyze`; add the CI prime step; document the `.gradle/`-state + daemon honesty note in the detector docstring (spec §1a wording).
- [ ] **Step 4: suite; hooks; commit** `feat: gradle detection — the wrapper, one init script, honest failure classes`.

### Task 4: Mermaid `$` quoting and either-side alias citation

**Files:**
- Modify: `src/sextant/egress/render/diagrams.py` (backtick-quote every identifier not matching `[A-Za-z_][A-Za-z0-9_.]*` in class declarations, relationship lines, and `<<stereotype>>` productions), `src/sextant/application/enrich/validate.py` (`_declared_nodes`: strip backtick quoting; for `participant X as Y` accept a cite of EITHER spelling), `src/sextant/enrich/INSTRUCTIONS.md` (one sentence: backtick-quote non-bare identifiers in diagrams; `$` names appear quoted).
- Test: `tests/egress/test_diagrams.py`, `tests/application/test_enrich_validate.py`.

**Interfaces:** consumes/produces nothing cross-task; goldens untouched (the fixture has no `$` names — the new tests use a synthetic shape).

- [ ] **Step 1: failing tests** — a shape named `Outer$Inner` emits `` class `Outer$Inner` `` (declaration + a relationship + a stereotype line, each pinned); a dotted name stays unquoted; validator accepts a claim diagram citing `Outer$Inner` from a machine-quoted declaration, accepts `participant J as Real` cited as either `J` or `Real`, still refuses a phantom node.
- [ ] **Step 2: implement; suite; hooks; commit** `fix: mermaid identifiers — quote what the grammar refuses`.

### Task 5: Typed machine sections and the HTML serializer

**Files:**
- Modify: `src/sextant/egress/render/document.py` (build `MachineHeading`/`MachineParagraph`/`MachineTable`/`MachineList`/`MachineDetail` at the sites that already know the structure; text as `(code|text, content)` runs; placement/staleness interleave keyed on SECTION INDEX — the flat line list goes away), `src/sextant/egress/render/html.py` (serialize each kind: `<h1>-<h3>`, `<p>`, `<table>`, `<ul>`, definition blocks with nested `<table>` for MachineDetail; `<code>` for code runs; drop the machine `<pre>` path to the escape hatch only).
- Test: `tests/egress/test_render_assembly.py`, `tests/egress/test_render_html.py`.

**Interfaces:**
- Consumes: the existing assembled-section model (`MachineSection`, `MachineDiagram`, claim sections).
- Produces: the five typed kinds above (frozen dataclasses beside the existing ones, exact fields per spec §5b: `MachineDetail(entries)`, entry = `(title_runs, body_runs | None, table: MachineTable | None)`); anchors expressed as section indices. Task 6 reshapes content through these types.

- [ ] **Step 1: failing byte-identity pin** — `markdown_document(assemble(...))` over the golden workspace equals the CHECKED-IN golden byte-for-byte with the typed sections in place (the golden does not change in this task — that is the whole point); the existing add-only and no-overlay pins keep passing.
- [ ] **Step 2: failing HTML tests** — fixture page: zero untyped machine sections (the emitter test from spec §5b), a real `<table>` with the fixture's endpoint-row count, `<h2>` for every `##`, `<code>` runs inside cells, MachineDetail as a definition block with a nested table, enrichment sections unchanged.
- [ ] **Step 3: implement — one structure at a time** (headings → paragraphs/lists → endpoint table → details → shapes), keeping the markdown byte-pin green at every step; then the placement/staleness rework on section indices with the existing anchor tests as the net.
- [ ] **Step 4: suite; hooks; commit** `feat: typed machine sections — HTML renders structure, markdown proves identity`.

### Task 6: Readability rulings (the one golden update)

**Files:**
- Modify: `src/sextant/egress/render/document.py` (human handler spelling in the table; a detail entry for EVERY endpoint carrying the full symbol; `Response: none recorded`; the `### Shapes` subsection with emit-once + named references; per-side `—` media glyph + legend line), `src/sextant/egress/render/html.py` (shape references as in-page links), goldens (`tests/egress/golden/architecture-minimal.md` — updated ONCE, reviewed as a ruling).
- Test: `tests/egress/test_render_assembly.py`, `tests/egress/test_render_format.py`.

**Interfaces:** consumes Task 5's typed kinds; produces the final 2M document shape Task 7 field-checks.

- [ ] **Step 1: failing tests** — table cell reads `` `UserResource#deleteUser` `` (short class name, no package, no `sig_`, no trailing dot); every endpoint has a detail entry whose first line carries the full symbol; two same-named handlers stay distinguishable in details (synthetic overload test); an empty shape renders `Response: none recorded` and NO table header; a shape returned by two endpoints appears once under `### Shapes` and is named at both endpoints; `application/json → —` and `— → —` forms; the legend line under the table.
- [ ] **Step 2: implement; regenerate the golden ONCE; every diff line accounted for in the commit message body; suite; hooks; commit** `feat: the document reads for humans — rulings from the JHipster field run`.

### Task 7: Enrichment prose formatting, field check, docs

**Files:**
- Modify: `src/sextant/egress/render/html.py` (claim bodies: `` `code` `` → `<code>`, fenced blocks → `<pre><code>`, nothing else), `src/sextant/enrich/INSTRUCTIONS.md` (the one formatting sentence), `docs/components/M02-detector.md` (Gradle delivered + §1b deviation notes), COVERAGE.md + README (§3 tested-surface statements; Gradle usage; multi-module usage), roadmap (2M delivered).
- Create: `scripts/field_check.py` + `scripts/field-expectations/*.json` (upstream commit pinned inside each file; endpoint counts + route sets + zero-`<pre>`-outside-code-blocks + first-diagram-parses).
- Test: `tests/egress/test_render_html.py` (formatting); the field check itself is opt-in and NOT in the suite.

**Interfaces:** consumes everything; the docs sentences are checked against shipped code (a false sentence is a Critical, standing rule).

- [ ] **Step 1: failing formatting tests** — a claim body with an inline span renders `<code>`, a fenced block renders `<pre><code>` escaped, a stray unpaired backtick renders literally (no half-open tags), markdown links/bold stay literal.
- [ ] **Step 2: field_check.py** — run it once for real against both pinned upstreams; commit the expectation files it validates against; record the JHipster zero-`<pre>` and diagram-parse assertions passing in the task report.
- [ ] **Step 3: docs; suite; hooks; commit** `feat: enrich prose formatting; field checks; 2M delivered`.

---

## Plan Self-Review (run before execution)

1. **Spec coverage:** §1/§1a/§1b/§1c→T3+T1 (notes T1, honesty+deviations T3 docs in T7 where doc-homed); §2→T2 (+T3 for Gradle modules); §3→T7; §4→T2+T3; §5a→T4; §5b→T5; §5c→T6; §5d→T7; §6 respected (no engine files touched); §7→T5 (byte pin), T6 (the one golden update), T7 (field net).
2. **Placeholder scan:** exact strings and schemas carried where tests pin them; the init-script JSON schema is stated in T3's Interfaces; no TBDs.
3. **Type consistency:** `RepositoryModel.notes` (T1) consumed by T2/T3 metadata; `modules.json` schema stated once (T2) and reused by T3; `MachineDetail(entries)` shape stated in T5 and consumed by T6; `detect(path, allow_resolve)` stated in T1 and used by T3.
4. **Ordering:** T1→T2→T3 build the detector chain; T4 independent; T5 before T6 (byte-identity proof precedes the golden change); T7 last. Golden changes only in T6, per the Global Constraint.
