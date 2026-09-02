# Phase 2M — Build systems, project shape, and rendered-output quality

Status: approved design, pre-plan. Binding for the 2M implementation plan.

Phase 2M closes gap area A of the 2026-09-02 gap analysis (build/project shape) and the
rendered-output quality defects found the same day by viewing a real analysis
(examples/jhipster-sample-app, Spring Boot 4.1) in a real browser. The version-bump gate
is unchanged. 2N (enrichment polish), 2O (Spring surface), 2P (Spring Cloud) follow; 2J
(Micronaut + Quarkus, both) comes after the gap program.

User rulings folded in: Gradle learns the build by running the project's own wrapper with
a read-only init script (M02's designed mechanism); a multi-module root is discovered and
every service module analyzed, each into its own workspace; the output-quality fixes are
part of this phase.

## §1 GradleDetector

New `src/sextant/ingress/detect/gradle.py`, sibling of `MavenDetector`, same
`RepositoryDetector` port.

- `accepts()`: `settings.gradle` / `settings.gradle.kts` at the root, or `build.gradle` /
  `build.gradle.kts` when no settings file exists (single-module build). When both a
  `pom.xml` and Gradle files exist, Maven wins and the Gradle files are recorded as a
  detect note — one build system per run, stated, never merged.
- Invocation: the project's own wrapper (`./gradlew`), falling back to a `gradle` on PATH
  with the fallback recorded in the detect output (wrapper-less builds are real but the
  wrapper is the project's own pinned truth). One invocation per attempt, at most two
  attempts (offline, then the flagged online retry of the network-posture rule below):
  `<gradle> --init-script <ours> -q sextantModel` where our init script registers a
  `sextantModel` task that prints one JSON document to stdout and changes nothing.
- The init script (a packaged resource, versioned beside the detector) reports, per
  included project: group / name / version, project directory, source and resource roots
  by source set, the `compileClasspath` resolved file paths with their component
  coordinates where Gradle knows them, the compiled-classes output directories, and the
  schema-root conventions (`src/main/proto`, `src/main/avro`, classpath-resource
  WSDL/XSD/SDL) the Maven detector already reads.
- Network posture mirrors Maven: the first attempt runs `--offline`; if Gradle refuses
  (dependencies not in its caches), detection fails loudly with Gradle's own words as the
  reason unless `allow_resolve` permits one online retry. DR-6 applies to the build tool
  itself: we report what Gradle reports — a failing build is a loud detect refusal
  carrying Gradle's error, never a partial guess.
- Classpath entries land in the same `ClasspathEntry` shape Maven produces. A path Gradle
  reports without coordinates is recorded path-only; anything unresolvable joins
  `libraries_not_resolved` with a reason. `extract_libraries` (2I) works unchanged — it
  keys on coordinates, and coordinate-less entries are refused by name.
- Compiled classes: Gradle layouts (`build/classes/java/main`, Kotlin equivalents) join
  the existing compiled-first reading; the derived-output jail exclusion already covers
  `build/`, and the analysis walk is unaffected (jail-specific rule, not an analysis one).
- Module kind: the same cheap evidence rules as Maven (`service` / `library` /
  `undetermined`, never guessed), reading the init-script output instead of the POM.

Boundaries (2M refuses, stated in the detect output where they arise): composite builds
(`includeBuild`), Android variants, introspecting `buildSrc` convention plugins beyond
what the resolved model already reflects (the init script reads the EVALUATED model, so
convention-plugin effects are visible; their sources are not read), and Gradle versions
too old to run the init script (the error is Gradle's own).

## §2 Multi-module discovery and the CLI

- `MavenDetector` gains the `<modules>` walk: recursive, honoring `<relativePath>`,
  cycle-refusing, each child read with the existing parent-inheritance rules.
  `RepositoryModel.modules` finally carries more than one entry. GradleDetector reports
  modules from the settings evaluation in the same shape.
- `sextant module analyze <repo-root>`: when detection finds one module, behaviour is
  byte-identical to today (golden-pinned). When it finds several, every `service` module
  is analyzed into its own `<module-dir>/.sextant` workspace exactly as a single-module
  run would, with a per-module summary line (endpoints, facts) and a final table; modules
  skipped as `library`/`undetermined` are listed with their kind as the reason. One
  failing module fails loudly and stops the run (partial output across modules is worse
  than a clear failure; `--keep-going` is NOT offered in 2M).
- `render` / `enrich` / `export` stay strictly per-module; pointing them at a multi-module
  root refuses with the module list. L owns cross-module composition.

## §3 Boot 4 currency

No fixture migration: the goldens' value is stability, and the 2026-09-02 field runs
(JHipster sample app and spring-petclinic-rest, both Boot 4.1) already exercise Boot 4
live. 2M ships:

- `scripts/field_check.py`: opt-in (never a check.sh gate), clones/updates the two
  example projects, compiles, analyzes, and compares endpoint counts and route sets
  against pinned expectation files under `scripts/field-expectations/`. Drift fails with
  a diff. Network-using by nature; documented as such.
- COVERAGE.md and README state the tested surface honestly: fixtures pin Boot 3.x
  semantics; Boot 4.1 is field-validated for the HTTP inbound surface; anything
  Boot-4-specific found missing becomes a catalog row in 2O, never a special case.

## §4 Testing (build-systems half)

- A real Gradle fixture: `fixtures/gradle-orders/` — Kotlin-DSL settings, two modules
  (one service with a handful of Spring MVC endpoints, one library), built in CI by the
  existing Gradle provisioning (the extractor already needs it). The fixture pins: init
  script JSON shape, offline-refusal wording, coordinates and classpath rows, service
  vs library kinds, compiled-classes discovery under `build/`.
- A Maven reactor fixture: a parent POM adopting `fixtures/orders-service` as a child
  plus one sibling library module, pinning the walk, inheritance, and skip-listing.
- Unit tests drive the detector over captured init-script outputs (no Gradle invocation
  in unit tests); exactly one integration test per build system runs the real tool, and
  a stale-workspace guard mirrors the session-fixture precedent.

## §5 Rendered-output quality

Found by viewing examples/jhipster-sample-app's outputs in a real browser (Chrome via the
dev preview; mermaid 11.17.2, our vendored build). Four defect classes; all four are
fixed in 2M because 2N–2P and 2J all produce documents through this renderer, and every
later field validation would re-hit them.

### §5a Mermaid identifiers: JVM `$` breaks the class diagram

`class AuthenticateController$JWTToken {` is a mermaid parse error — its bare identifier
grammar refuses `$`, so any project with a nested class (most real projects) gets a
"Syntax error" bomb as its first diagram in BOTH outputs. Verified against the vendored
mermaid build: backtick-quoted identifiers parse and keep the true name as the node id
(`` class `AuthenticateController$JWTToken` ``), and sequence diagrams accept the alias
form (`participant J as AuthenticateController$JWTToken`).

- The diagram builder backtick-quotes every classDiagram identifier that is not a bare
  mermaid identifier (`[A-Za-z_][A-Za-z0-9_]*` — dots are also legal bare; quote
  anything else), and uses the alias form for such names in sequence diagrams. Node ids
  remain the TRUE names, so the enrichment validator's node comparison is unchanged;
  its `_declared_nodes` scan learns to strip backtick quoting and read `as` aliases.
- Test: a fixture shape with a `$` inner-class name; pin that the emitted diagram parses
  (a mermaid-grammar smoke pin at the unit level: the emitted identifier matches the
  quoted grammar; the existing browser-verified fixture covers rendering).

### §5b The HTML machine half is three giant `<pre>` blocks

The browser inventory of the JHipster page: 0 headings, 0 tables, 0 lists in a 15,574px
document — headings, the 38-row endpoint table, and every bullet render as literal
markdown text in monospace. Cause: `MachineSection` is opaque lines, so the HTML emitter
can only escape-and-`<pre>` them (T4's no-parse rule made visible).

Fix at the source, the same move as `MachineDiagram` in 2K: the assembly builds TYPED
sections at the sites that already know the structure —

- `MachineHeading(level, text)`
- `MachineParagraph(text)` (text runs carry inline-code spans: the builder already knows
  which fragments are code — symbols, paths, keys — and emits `(code, text)` runs, so
  the HTML serializer writes `<code>` without parsing anything)
- `MachineTable(headers, rows)` (cells are the same runs)
- `MachineList(items)`
- `MachineDiagram` (exists)

`markdown_document` serializes these to byte-identical markdown under the typed-section
refactor ALONE (the golden proves it; this refactor and §5c's spelling changes land as
separate commits so the byte-identity claim stays provable — the golden then updates
once, deliberately, for §5c). `html_document` gets real `<h1>-<h3>`, `<table>`, `<ul>`,
`<p>`, styled. `MachineSection` (opaque lines) remains only as the
escape hatch for anything not yet typed, and the JHipster page must come out of 2M with
zero `<pre>`-rendered machine content (checked by an emitter test counting untyped
sections for the fixture workspace: zero).

### §5c Readability defects in both outputs

- Handler cells read as machine identity:
  `io/github/jhipster/sample/web/rest/UserResource#deleteUser(sig_4a71b976).` — the
  package path, the opaque `sig_` hash, and a trailing `.` in every row. The endpoint
  table shows the HUMAN spelling — `UserResource#deleteUser` — as a code run; the full
  symbol (package and signature hash included) moves to the per-endpoint detail entry
  that already exists below the table, where evidence belongs. No identity is lost;
  it changes column, not existence.
- Empty response tables: five DELETE endpoints each print a header-only
  `| Field | Type | Required | Nullable |` table. A shape with no recorded fields
  renders one line — `Response: none recorded` — per the NFR-7 empty-section
  discipline already used elsewhere.
- Repeated shape tables: the same DTO field table repeats verbatim under every endpoint
  returning it (AdminUserDTO appears in full four times). Each named shape's table is
  emitted ONCE (in the per-endpoint details of its first appearance or a shapes
  section — implementation's choice, stated); later references render as
  `Response: AdminUserDTO` linking (HTML) / naming (markdown) the earlier table.
  Named shapes live in a `### Shapes` subsection after the per-endpoint details, each
  emitted exactly once; per-endpoint entries name the shape. Anonymous shapes stay
  inline where they occur.
- Media `- → -` cells: an empty media pair renders as `—` (one em dash), and the column
  header gains a legend line under the table stating what request → response media
  means and that `—` is "none recorded".

### §5d Enrichment prose formatting

LLM claim bodies render as flat text in HTML (backticks show literally — the T4 M-7
documented consequence). 2M draws the line at inline code and fenced blocks, nothing
more: in claim bodies, `` `code` `` spans become `<code>` and triple-backtick fences
become `<pre><code>` in HTML (markdown output already renders them natively). No other
markdown-ism is interpreted; the INSTRUCTIONS gain one sentence saying exactly that.
Redaction is unaffected (formatting runs after the existing redaction pass, on the same
text).

## §6 Non-goals

Spring surface rows (2O), Spring Cloud (2P), enrichment INSTRUCTIONS/verdict-flight work
beyond §5d's one sentence (2N), `--keep-going` multi-module tolerance, composite builds,
repo-level workspaces (L), syntax highlighting of Java source (we render no Java source),
and any engine change (there is none in this phase — detectors, CLI, renderer only).

## §7 Testing (output half)

Golden updates are expected ONLY where §5c changes spellings (handler cells, empty
tables, media cells) — each golden change reviewed as a deliberate readability ruling,
never a drift. New pins: the typed-section zero-`<pre>` check, the `$`-identifier
diagram, the emitted-once shape rule, the `Response: none recorded` line, HTML
table/heading presence for the fixture (a real `<table>` with the fixture's endpoint
count), and the enrichment inline-code rendering. The JHipster field check (§3) doubles
as the real-world regression net for all of §5.
