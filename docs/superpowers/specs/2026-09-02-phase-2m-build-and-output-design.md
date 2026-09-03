# Phase 2M — Build systems, project shape, and rendered-output quality

Status: approved design, pre-plan, revised after adversarial review (2026-09-02).
Binding for the 2M implementation plan.

Phase 2M closes gap area A of the 2026-09-02 gap analysis (build/project shape) and the
rendered-output quality defects found the same day by viewing a real analysis
(examples/jhipster-sample-app, Spring Boot 4.1) in a real browser. The version-bump gate
is unchanged. 2N (enrichment polish), 2O (Spring surface), 2P (Spring Cloud) follow; 2J
(Micronaut + Quarkus, both) comes after the gap program.

User rulings folded in: Gradle learns the build by running the project's own wrapper with
a read-only init script (M02's mechanism, with the deviations from M02's full design
stated in §1b); a multi-module root is discovered and every service module analyzed,
each into its own workspace; the output-quality fixes are part of this phase.

## §1 GradleDetector

New `src/sextant/ingress/detect/gradle.py`, sibling of `MavenDetector`, implementing the
same `Detector` port (`application/ports/detector.py`).

- `accepts()`: `settings.gradle` / `settings.gradle.kts` at the root, or `build.gradle` /
  `build.gradle.kts` when no settings file exists (single-module build). When both a
  `pom.xml` and Gradle files exist, Maven wins and the coexistence is recorded as a
  detect note (§1c) — one build system per run, stated, never merged.
- Invocation: the project's own wrapper (`./gradlew`), falling back to a `gradle` on
  PATH with the fallback recorded as a detect note. One invocation per attempt, at most
  two attempts (offline, then the flagged online retry):
  `<gradle> --init-script <ours> --no-configuration-cache -q sextantModel
  -Psextant.out=<tmpfile>`. The init script registes a `sextantModel` task that writes
  ONE JSON document to the file named by `sextant.out` — never stdout, which Gradle,
  target build scripts, and JVM warnings all pollute. A `sextantModel` name collision
  with the target build surfaces as Gradle's own configuration error and is a detect
  refusal like any other.
- The init script (a packaged resource, versioned beside the detector) reports, per
  included project: group / name / version, project directory, source and resource roots
  by source set, the resolved `compileClasspath` (file path + component coordinates
  where Gradle reports them), the compiled-classes output directories, whether a
  publishing plugin is applied (§2's kind evidence), and the schema-root conventions
  (`src/main/proto`, `src/main/avro`, classpath-resource WSDL/XSD/SDL) the Maven
  detector already reads.
- Classpath → the shapes that EXIST: MavenDetector emits `LibraryRoot`s (it never runs
  Maven and produces no classpath facts; the `module`-fact/`ClasspathEntry` route is
  documented dead in the 2I spec). GradleDetector builds `LibraryRoot`s directly from
  the init-script classpath report — jar path from Gradle, coordinates from the
  component id; a path Gradle reports without coordinates joins `libraries_not_resolved`
  with a path-only reason. `extract_libraries` therefore works for Gradle through its
  OWN route: coordinates match against the reported components, and the jar is read
  from the path Gradle already resolved (`~/.gradle/caches` layout is never guessed —
  we only ever open paths Gradle handed us).
- Network posture: attempt one runs `--offline`; if Gradle refuses (dependencies not in
  its caches), detection fails loudly with Gradle's own words as the reason unless
  `allow_resolve` permits one online retry. `allow_resolve` gets its missing plumbing:
  a `--allow-resolve` analyze flag threaded through `stages/analyze.py` to `detect()`
  (today the port parameter exists and nothing passes it — for Maven too).
  DR-6 applies to the build tool itself: we report what Gradle reports — a failing
  build is a loud detect refusal carrying Gradle's error, never a partial guess.
- Cold-start taxonomy (distinct failure classes, distinct messages): (1) the WRAPPER
  distribution is absent and must itself be downloaded before any task can run —
  `--offline` does not govern this; having the distribution is treated like having
  `mvn` installed, so a refused wrapper download is reported as "Gradle distribution
  not present" naming the wrapper properties file, not as a dependency failure;
  (2) offline dependency resolution failure (the retry ladder above); (3) build
  configuration failure (Gradle's error verbatim).
- Coordinates Gradle leaves loose: a project with no `group` or with version
  `unspecified` is a loud detect refusal naming the missing coordinate — the Maven
  detector refuses on missing POM elements and Gradle gets the same discipline, never
  a `:name`-shaped module id.
- Compiled classes: Gradle layouts (`build/classes/java/main`, Kotlin equivalents) join
  the existing compiled-first reading. The enrichment jail's derived-output exclusion
  already hides `build/` from the MODEL; the analysis walk reads the class output dirs
  the init script names, exactly as Maven reads `target/classes`.

### §1a Honesty

Invoking `./gradlew` executes the target repository's build code — the same trust
already extended when the suite compiles fixtures with `mvn` (build plugins are code).
Sextant adds no sandbox; analyzing a repository means trusting its build, and the docs
say so in exactly those words. Nor is Gradle detection filesystem-read-only for the
target: Gradle writes `.gradle/` state into the repo and may start a daemon. Both facts
land in the detector's documentation.

### §1b Deviations from M02's full design (stated, not silent)

M02 designs per-Gradle-major conformance fixtures, a convention-path sanity warning, a
three-tier classpath, `modules.json`, and `module` facts. 2M ships one fixture on one
pinned Gradle version, the `modules.json` artifact (§2 needs it), and none of the rest;
each remaining item stays in M02 as future work with a one-line status note.

### §1c Detect notes

`RepositoryModel` gains a `notes: tuple[str, ...]` field (schema work, named here):
build-system coexistence, wrapper fallback, and boundary refusals land there and are
carried into `metadata.json`. Boundaries (2M refuses, with notes where they arise):
composite builds (`includeBuild`), Android variants, introspecting `buildSrc`
convention-plugin sources (the init script reads the EVALUATED model, so their effects
are visible; their sources are not read), and Gradle versions too old to run the init
script (the error is Gradle's own).

## §2 Multi-module discovery and the CLI

- `MavenDetector` gains the `<modules>` walk: the parent's `<modules>` entries name the
  child directories (recursive, cycle-refusing); each child is read with the existing
  parent-inheritance rules, which already follow the child's own `<parent>` block.
  `RepositoryModel.modules` finally carries more than one entry — and
  `stages/analyze.py`, which today silently analyzes `modules[0]` only, learns to loop.
  GradleDetector reports modules from the settings evaluation in the same shape.
- Module kinds: Maven's documented rule stands (`library` is never returned — publishing
  evidence is unreadable from a POM alone), so Maven reactor siblings classify
  `service` or `undetermined`. Gradle CAN read publishing evidence from the evaluated
  model (a publishing plugin applied), so GradleDetector may return `library` — a
  stated deviation, pinned by the Gradle fixture, not a change to Maven.
- `sextant module analyze <repo-root>`: detection runs FIRST (today the workspace is
  created and `render/` cleared before detection — that reorders); a single-module
  result then behaves byte-identically to today (golden-pinned). The multi-module gate
  is whether the TARGETED root itself declared `<modules>` (`RepositoryModel.
  multi_module`), never a module count — a reactor naming exactly one child is still a
  reactor, and that child analyzes into its OWN workspace, never the aggregator's
  (`fixtures/pom.xml` is exactly this shape today, naming one: `orders-soap-client`).
  With a multi-module root, every module that is not KNOWN not to be a service is
  analyzed into its own `<module-dir>/.sextant` workspace exactly as a single-module
  run would, with a per-module summary line and a final table — REVISED after fix
  round 1: the original "only `service` is analyzed" rule returned ZERO analyzed
  output against `spring-petclinic-microservices` itself, since all eight of its
  modules classify `undetermined`. The kind gate is therefore an EXCLUSION list, not
  an allow-list: skip `library` (Gradle-only — Maven never returns it) and a leaf
  `<packaging>pom</packaging>` (a BOM or aggregation-only sibling with no classes to
  scan; without this exception a reactor containing a BOM hard-fails the whole run, a
  missing `target/classes` stopping the module's own scan) — reported skip-listed with
  that reason (`"kind is library"` / `"packaging is pom"`). Every other module is
  analyzed regardless of kind; `kind` stays honestly `undetermined` in `modules.json`
  and `metadata.json` either way — only `analyzed` flips. One failing module fails
  loudly and stops the run (`--keep-going` is NOT offered in 2M), and a run that fails
  partway leaves no stale `modules.json` from a prior run claiming a module analyzed
  that this run never reached. The root gets M02's designed `modules.json` (module
  dirs — ROOT-RELATIVE, stable across however the root was itself spelled on the
  command line — kinds, analyzed-or-skipped) — the artifact §2's refusals below read.
  `--workspace` at a multi-module root is refused (the flag is per-module).
- `render` / `enrich` / `export` stay strictly per-module and never re-detect: at a
  directory with a `modules.json` and no workspace they refuse WITH the module list
  read from that file; anywhere else workspace-less they keep today's "no analysis
  found" message. L owns cross-module composition.

## §3 Boot 4 currency

No fixture migration: the goldens' value is stability, and the 2026-09-02 field runs
(JHipster sample app and spring-petclinic-rest, both Boot 4.1) already exercise Boot 4
live. 2M ships:

- `scripts/field_check.py`: opt-in (never a check.sh gate; network-using by nature and
  documented as such). Each expectation file under `scripts/field-expectations/` PINS
  THE UPSTREAM COMMIT it was recorded against; the script checks out that commit, so
  upstream drift can never masquerade as a Sextant regression — refreshing a pin is a
  deliberate, reviewed act. Checks: endpoint counts, route sets, and the §5 output
  assertions (zero `<pre>`-outside-code-blocks in the HTML, first diagram parses).
- Because this script is opt-in, the spec says plainly: §5's beyond-fixture claims are
  verified only when someone runs it. The fixture pins are the always-on net.
- COVERAGE.md and README state the tested surface honestly: fixtures pin Boot 3.x
  semantics; Boot 4.1 is field-validated for the HTTP inbound surface; anything
  Boot-4-specific found missing becomes a catalog row in 2O, never a special case.

## §4 Testing (build-systems half)

- A real Gradle fixture: `fixtures/gradle-orders/` — Kotlin-DSL settings, pinned wrapper
  version, two modules (a Java service with a handful of Spring MVC endpoints; a
  library applying a publishing plugin, pinning the Gradle-only `library` kind). CI
  gains a Gradle prime step beside the Maven one (the ONE fetch-allowed step per build
  system): it warms the wrapper distribution and the fixture's dependencies so the
  offline integration test can run offline honestly. The fixture pins: init-script JSON
  shape, offline-refusal wording (a stable SUBSTRING, not Gradle's full sentence),
  LibraryRoot rows with coordinates, service vs library kinds, compiled-classes
  discovery under `build/`, and the missing-coordinate refusal.
- A Maven reactor fixture: an AGGREGATION-ONLY parent (`<modules>` without the children
  declaring a `<parent>`) adopting `fixtures/orders-service` unchanged — its standing
  comment says gaining a parent would change its coordinates, and aggregation-only
  keeps that true (the comment is updated to say so) — plus one new sibling module that
  DOES declare the parent, pinning inheritance and the walk. Both classify
  `undetermined` (no service evidence) and, per §2's post-fix-round-1 kind gate, are
  BOTH analyzed — `undetermined` is no longer a skip reason on its own; only `library`
  and a leaf `<packaging>pom</packaging>` are.
- Unit tests drive the detector over captured init-script outputs (no Gradle invocation
  in unit tests); exactly one integration test per build system runs the real tool, and
  a stale-workspace guard mirrors the session-fixture precedent.

## §5 Rendered-output quality

Found by viewing examples/jhipster-sample-app's outputs in a real browser (mermaid
11.17.2, our vendored build). Four defect classes; all four are fixed in 2M because
2N–2P and 2J all produce documents through this renderer.

### §5a Mermaid identifiers: JVM `$` breaks the class diagram

`class AuthenticateController$JWTToken {` is a mermaid parse error — the bare identifier
grammar refuses `$`, so any project with a nested class gets a "Syntax error" bomb as
its first diagram in BOTH outputs. Verified against the vendored mermaid build in a live
browser session (a one-off manual verification; the unit pins below are the durable
record): backtick-quoted identifiers parse and keep the true name as the node id.

- The classDiagram builder (`egress/render/diagrams.py` — today's only diagram emitter)
  backtick-quotes every identifier not matching `[A-Za-z_][A-Za-z0-9_.]*` (dotted names
  verified legal bare), in class declarations, relationship lines, AND the
  `<<stereotype>> Name` production (each quoted production covered by a unit pin).
- Sequence diagrams have no machine emitter yet (they await the call graph) — the alias
  form is an LLM-authored concern, so the rule lands in the validator and INSTRUCTIONS:
  `_declared_nodes` learns backtick-stripping, and for `participant X as Y` it accepts
  a node cited by EITHER spelling (the conservative reading — today's code treats the
  alias as a human label and checks the left side; an LLM copying machine-quoted names
  or writing `participant J as Real$Name` must not be refused for it). INSTRUCTIONS
  states the backtick convention in one sentence.
- Test: a fixture shape with a `$` inner-class name pinning the emitted, quoted diagram
  text; validator pins for backtick-stripped and either-side-alias citation.

### §5b The HTML machine half is three giant `<pre>` blocks

The browser inventory of the JHipster page: 0 headings, 0 tables, 0 lists in a 15,574px
document. Cause: `MachineSection` is opaque lines, so the HTML emitter can only
escape-and-`<pre>` them.

Fix at the source: the assembly builds TYPED sections at the sites that already know the
structure. Text everywhere is RUNS — `(code | text, content)` pairs the builders
already distinguish (symbols, paths, and keys are code) — so the HTML serializer writes
`<code>` without parsing anything:

- `MachineHeading(level, text)`
- `MachineParagraph(runs)`
- `MachineTable(headers, rows_of_runs)`
- `MachineList(items)` — an item is runs
- `MachineDetail(entries)` — the nesting the real document demands (adversarial-review
  C2): an entry is (title runs, optional body runs, optional `MachineTable`), rendering
  as the existing two-level list with indented tables in markdown and as a definition
  block with a real `<table>` in HTML. Endpoint details, response shapes, and the
  Shapes subsection (§5c) are `MachineDetail`s.
- `MachineDiagram` (exists)

Placement rework, named: anchors and diagram spans are today integer offsets into one
flat line list; with typed sections that list dissolves, so claim placement and the
staleness interleave key on SECTION INDEX instead of line offset. This is a
`document.py` internal — anchor semantics (the four names, their meaning) do not change,
and the overlay schema does not change.

`markdown_document` serializes the typed sections to byte-identical markdown under this
refactor ALONE (the golden proves it; this refactor and §5c's changes land as separate
commits so the byte-identity claim stays provable — the golden then updates once,
deliberately, for §5c). `html_document` gets real `<h1>-<h3>`, `<table>`, `<ul>`, `<p>`,
`<code>`, styled. `MachineSection` (opaque lines) remains only as the escape hatch, and
two checks make "zero `<pre>` machine content" true beyond the fixture: an emitter test
counts untyped sections for the fixture workspace (zero), and the §3 field check asserts
zero `<pre>`-outside-code-blocks over the regenerated JHipster page.

### §5c Readability defects in both outputs

- Handler cells read as machine identity:
  `io/github/jhipster/sample/web/rest/UserResource#deleteUser(sig_4a71b976).` — package
  path, opaque `sig_` hash, and a stray trailing `.` in every row. The endpoint table
  shows the HUMAN spelling — `UserResource#deleteUser` — as a code run. To keep the
  full identity, EVERY endpoint now emits a detail entry (today only endpoints with
  recorded shapes or via get one — adversarial-review C3), and the full symbol
  (package and signature hash included) lives there. Ruled consequences, stated: the
  goldens change structurally for this (every endpoint gains a detail line), and
  same-name overloads become indistinguishable in the TABLE spelling — the detail
  entries keep the `sig_` hashes that distinguish them.
- Empty response tables: a shape with no recorded fields renders one line —
  `Response: none recorded` — per the NFR-7 empty-section discipline.
- Repeated shape tables: named shapes live in a `### Shapes` subsection after the
  per-endpoint details, each emitted exactly once; per-endpoint entries render as
  `Response: AdminUserDTO`, linking (HTML) / naming (markdown) the shapes entry.
  Anonymous shapes stay inline where they occur.
- Media cells: an empty SIDE renders as `—` (so `application/json → —`, and `— → —`
  when both are empty) — one glyph, one meaning — with a one-line legend under the
  table defining request → response and `—` as "none recorded".

### §5d Enrichment prose formatting

LLM claim bodies render as flat text in HTML (backticks show literally). 2M draws the
line at inline code and fenced blocks, nothing more: in claim bodies, `` `code` ``
spans become `<code>` and triple-backtick fences become `<pre><code>` in HTML (markdown
output already renders them natively). No other markdown-ism is interpreted; the
INSTRUCTIONS gain one sentence saying exactly that. Redaction is unaffected (formatting
runs after the existing redaction pass, on the same text).

## §6 Non-goals

Spring surface rows (2O), Spring Cloud (2P), enrichment INSTRUCTIONS/verdict-flight work
beyond §5a/§5d's single sentences (2N), `--keep-going` multi-module tolerance, composite
builds, repo-level workspaces (L), syntax highlighting of Java source (we render no Java
source), machine sequence-diagram emission (awaits the call graph), and any resolve
engine change. Touched surfaces: detectors, `stages/analyze`, CLI, renderer, and —
scoped to §5a's citation rules — `application/enrich/validate.py`.

## §7 Testing (output half)

Golden updates happen exactly twice, each a deliberate reviewed ruling: once for §5c's
spellings-and-structure changes (handler cells, always-emitted details, Shapes
subsection, empty-shape lines, media glyphs) and never for the §5b typed-section
refactor, whose byte-identity the unchanged golden proves first. New pins: the
typed-section zero-`<pre>` check, `MachineDetail` round-trip (markdown nesting and HTML
table), the `$`-identifier diagram text, quoted stereotype and relationship productions,
either-side alias citation, the emitted-once shape rule, `Response: none recorded`, the
per-side media glyph, HTML table/heading presence for the fixture (a real `<table>` with
the fixture's endpoint count), and enrichment inline-code rendering. The JHipster field
check (§3) is the real-world net for all of §5, verified when run.
