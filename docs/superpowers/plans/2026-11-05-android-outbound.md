# Android modules (outbound) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sextant reads Android parts (release build, one module per edition), Kotlin Multiplatform
JVM and Android versions, and keeps reading every other part when one part fails to build.

**Architecture:** The Gradle init script gives every part its own task that answers only for that
part and writes one file per module; a root task with no dependencies writes the list of parts.
Gradle runs with `--continue`; the detector assembles the files into today's `{projects, includedBuilds}`
document, so `_repository_model` keeps its input shape. Modules sharing one folder keep their
results in sub-folders of that folder's `.sextant`.

**Tech Stack:** Groovy init script (Gradle 9.x, AGP 7.4+ `androidComponents`, Kotlin Gradle plugin),
Python 3 detector and api, pytest, a new Gradle fixture built with JDK 21.

**Spec:** `docs/superpowers/specs/2026-11-05-android-outbound-design.md` (approved 2026-11-05,
M1–M6 ruled). Read §2, §2e and §4 before any task.

## Global Constraints

- Fixtures build with JDK 21 only (`JAVA_HOME=$(/usr/libexec/java_home -v 21)`), never 27.
- Android SDK: `ANDROID_HOME=/opt/homebrew/share/android-commandlinetools` locally (platform
  `android-37.0`, build-tools 36.0.0); never commit `local.properties`.
- Identity is what Gradle reports (OI-273): `group:name`, or `<root name><project path>` with no
  group. A part with several modules adds `-<version or edition name>` to the name (M2, M3).
- A wrong value is a lie: where Sextant cannot tell which version a part uses, it says so
  (`libraries_not_resolved`), never picks one (M1).
- Every comment and doc line is ASD-STE-100 plain English; no new invented terms.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Gate: `scripts/check.sh` green; `scripts/field_check.py` six pins unchanged.
- `modules.json` gains exactly one key, `results` (M6, user-approved). No other persisted format
  changes (no fact-schema, graph-schema or catalog change).

## Review Focus

1. A Gradle build that works today (`fixtures/gradle-orders`, examples' Gradle builds) gives the
   same detection after Task 1 — pinned by the existing capture and e2e test (Task 1).
2. A part whose compile fails while another part uses it: both skipped, each with a true reason
   (Task 2 test `test_a_part_that_uses_a_failed_part_is_skipped_with_that_reason`).
3. Offline run where only one part lacks a cached dependency, without `--allow-resolve`: that part
   is skipped with Gradle's words and a note names `--allow-resolve` (Task 2 test
   `test_an_offline_refusal_in_one_part_names_allow_resolve`).
4. A part with two modules used by a part that has no platform label: no join, a named gap (Task 4
   test `test_a_two_module_part_with_no_label_is_a_named_gap`).
5. `module render <folder>` where the folder holds two modules: refusal listing both `--workspace`
   commands (Task 3 test `test_render_at_a_shared_folder_lists_each_module`).

---

### Task 1: One task per part, assembled by the detector

**Files:**
- Modify: `src/sextant/ingress/detect/sextant-model.init.gradle`
- Modify: `src/sextant/ingress/detect/gradle.py` (`_compose_argv`, `_invoke`, `_read_json`, new `_assemble`)
- Modify: `.github/workflows/pr.yml` (priming step argv)
- Test: `tests/ingress/test_gradle_detector.py`, `tests/e2e/test_gradle_fixture_builds.py`

**Interfaces:**
- Produces (init script): task `sextantBuild` on the root project only, no dependencies, writes
  `<outDir>/build.json` = `{"projects": [{path, group, name, version, dir}], "includedBuilds": [...]}`.
  Task `sextantModel` on EVERY project; it resolves only its own project's configurations and
  writes `<outDir>/projects/<path with ":" → "_", root = "_">.json` = a JSON list of records,
  each record today's project record plus `"target": null` and `"platform": null` (later tasks fill
  them). A project with no compiling plugin writes one record with empty lists (today's shape).
- Produces (init script): one Groovy closure `sextantRecord(p, Map inputs)` building a record from
  `{sourceSets: Map<String language, Collection<File>>, classesDirs, classpathConfiguration,
  declaredRelease, target, platform}`. Later branches call only this closure.
- Produces (Python): `_compose_argv(gradle_command, init_script, out_dir: Path, offline) -> list[str]`
  = `[*gradle, (--offline), --init-script, <script>, --no-configuration-cache, --continue, -q,
  sextantBuild, sextantModel, -Psextant.outDir=<out_dir>]`.
- Produces (Python): `_assemble(out_dir: Path) -> dict[str, Any]` returning
  `{"projects": [records...], "includedBuilds": [...]}`, records sorted by `(path, target or "")`;
  a project listed in `build.json` with no file under `projects/` gets one record with empty
  lists and `"buildFailure": None` placeholder for Task 2 (Task 1 never produces one: exit code 0).
- `_repository_model` input shape unchanged.

- [ ] **Step 1: Update the argv pin tests** (`test_the_offline_argv_carries_offline_before_the_shared_flags`
  and its online twin) to the argv above with `Path("/out")`, and add
  `test_assemble_reads_one_file_per_project` writing a `build.json` and two project files in
  `tmp_path` and asserting `_assemble(tmp_path)["projects"]` equals the two records in path order.
- [ ] **Step 2: Run** `uv run pytest tests/ingress/test_gradle_detector.py -q` — the new and changed tests FAIL.
- [ ] **Step 3: Rewrite the init script** as above. Keep every existing rule and comment of the
  `java` branch (source sets, language sets, generated dirs, `declaredRelease`, classpath entries),
  moved into `sextantRecord`. The `java` project's `sextantModel` task depends on `classes`.
  `sextantBuild` reads only project properties of other projects, never a configuration.
- [ ] **Step 4: Implement** `_compose_argv`, `_assemble`, and make `_invoke` read
  `_assemble(out_dir)` where it read `_read_json(out_file)`; a missing `build.json` with exit code
  0 is the existing "wrote no model" refusal.
- [ ] **Step 5: Run** the unit tests, then the real Gradle check:
  `uv run pytest tests/ingress/test_gradle_detector.py tests/e2e/test_gradle_fixture_builds.py tests/e2e/test_gradle_kotlin_convention.py -q`
  — PASS. Then the before/after guard: for every Gradle build under `examples/` with no Android
  plugin, run `GradleDetector().detect()` on the base commit and on this commit and compare the
  `RepositoryModel`s (modules, ids, roots, output dirs, library roots, notes): identical, except a
  build that refused before because of `org.gradle.parallel=true`, which now detects. Write the
  list and the result to the task report.
- [ ] **Step 6: Update the CI priming step** to the new argv (`sextantBuild sextantModel
  -Psextant.outDir=/tmp/sextant-model-prime`, `--continue`).
- [ ] **Step 7: Commit** `feat(gradle): one model task per part; the detector assembles (Android M4)`.

### Task 2: A part that fails to build is skipped with Gradle's reason (M5)

**Files:**
- Modify: `src/sextant/ingress/detect/gradle.py` (`_invoke`, `_assemble`, new `_failures_by_project`)
- Modify: `src/sextant/application/ports/detector.py` (`ModuleModel.build_failure: str | None = None`)
- Modify: `src/sextant/api.py` (`_skip_reason`: `build_failure` first)
- Test: `tests/ingress/test_gradle_detector.py`, `tests/cli/test_app.py`, new `tests/e2e/test_gradle_part_failure.py`

**Interfaces:**
- Produces: `_failures_by_project(output: str) -> dict[str, str]` — project path → Gradle's own
  text for every `Execution failed for task '<task path>'.` block in Gradle's output (the lines
  after it starting with `> `, joined by newlines). The project path is the task path without its
  last segment (`:app:compileReleaseKotlin` → `:app`; `:compileJava` → `:`).
- Produces: `_assemble(out_dir, output: str = "")` — a project in `build.json` with no record file
  gets `"buildFailure"`: its own failure text if `_failures_by_project` has it, else
  `"not built: a part it needs failed to build (<comma-separated failed paths>)"`.
- `_invoke`: exit code ≠ 0 with `build.json` present is a PARTIAL result, read with `_assemble`;
  exit code ≠ 0 with no `build.json` keeps today's taxonomy (distribution absent, offline retry,
  verbatim refusal). An offline refusal in the output with `allow_resolve` still retries online once.
  An offline refusal without `allow_resolve` adds the note
  `"some parts need dependencies that are not in the local Gradle cache; --allow-resolve lets Gradle download them"`.
- `_module_of` copies `buildFailure` into `ModuleModel.build_failure`; `_skip_reason` returns it
  before any other rule.

- [ ] **Step 1: Write failing tests:**
  - `test_failures_by_project_reads_each_failed_task` — two numbered `* What went wrong:` blocks
    (`:app:compileReleaseKotlin` with `> File google-services.json is missing.`, `:compileJava`),
    expect `{":app": "File google-services.json is missing.", ":": ...}`.
  - `test_a_part_that_uses_a_failed_part_is_skipped_with_that_reason` — `build.json` with `:lib`
    and `:app`, no record files, output failing `:lib:compileJava`; `:lib` reason is Gradle's text,
    `:app` reason starts `not built: a part it needs failed to build (:lib)`.
  - `test_an_offline_refusal_in_one_part_names_allow_resolve` — the note above is in `RepositoryModel.notes`.
  - `test_skip_reason_puts_a_build_failure_first` in `tests/cli/test_app.py` (or the api test file that
    already tests `_skip_reason`).
  - e2e `test_one_broken_part_does_not_stop_the_others` — copy `fixtures/gradle-orders/gradlew` and
    `gradle/` into `tmp_path`, two plain `java` parts `:good` and `:bad` (`bad` has a syntax error),
    `sextant module analyze`: `good` analysed, `bad` skipped with javac's error text; skips the same
    way the existing Gradle e2e test skips on an unprimed machine.
- [ ] **Step 2: Run** them — FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run** the Task 1 command plus the new tests — PASS.
- [ ] **Step 5: Update** `docs/components/M02-detector.md` (Gradle section: one task per part,
  `--continue`, skipped parts) and the `gradle.py` module docstring paragraph that says one
  project's compile failure refuses detection for the whole repository.
- [ ] **Step 6: Commit** `feat(gradle): a part that fails to build is skipped with Gradle's reason (Android M5)`.

### Task 3: Results sub-folder per module in a shared folder (M6)

**Files:**
- Modify: `src/sextant/application/ports/detector.py` (`ModuleModel.results_name: str | None = None`)
- Modify: `src/sextant/api.py` (`_workspace_dir_of`, `_analyze_reactor`, `_module_json_row`,
  `ModuleOutcome`, the system-analyze reader of `modules.json`, `_refuse_if_unanalyzed`)
- Modify: `docs/ARCHITECTURE.md` §8 (file layout) and `docs/components/M00-cli.md` (modules.json row)
- Test: the api/cli test files that already cover `_analyze_reactor`, `modules.json` and `system analyze`

**Interfaces:**
- `ModuleModel.results_name`: the version or edition name when the module's folder holds more
  than one module, else `None`. Set by the detector in Task 4/5; tests here build `ModuleModel`s by hand.
- `_workspace_dir_of(module_root, workspace_dir, results_name=None)` → `workspace_dir` if given,
  else `<root>/.sextant/<results_name>` when `results_name`, else `<root>/.sextant`.
- `modules.json` row: adds `"results"` = results folder relative to the repository root
  (`core/.sextant/jvm`, or `core/.sextant` for a one-module folder), written for EVERY row.
  Readers use `entry.get("results") or f"{dir}/.sextant"`.
- A single-module command (`render`, `enrich`, `export`, `diff`) given a folder whose `.sextant`
  holds no `workspace.duckdb` but has sub-folders that do: refusal
  `"<folder> holds <n> modules: <module id> (--workspace <path>), ..."` (`diff`: "pass the results
  folder itself", since `diff` takes a workspace path directly).

- [ ] **Step 1: Write failing tests:** `test_two_modules_in_one_folder_get_their_own_results`
  (reactor with two hand-built modules, same root, `results_name` `jvm` and `android`: both
  workspaces exist, `modules.json` rows carry `core/.sextant/jvm` and `core/.sextant/android`);
  `test_a_modules_json_row_without_results_means_dir_sextant`;
  `test_system_analyze_reads_results`; `test_render_at_a_shared_folder_lists_each_module`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS, plus `scripts/check.sh --tests`.
- [ ] **Step 5: Commit** `feat(api): modules sharing a folder keep results in sub-folders (Android M6)`.

### Task 4: Android fixture and Kotlin Multiplatform JVM versions (M1, M2)

**Files:**
- Create: `fixtures/gradle-android/` — `settings.gradle.kts` (`rootProject.name = "ShopApp"`),
  `build.gradle.kts` (`allprojects { group = "com.acme" }`), `gradle.properties`
  (`org.gradle.parallel=true`, `android.useAndroidX=true`), wrapper copied from
  `examples/kotlinconf-app` (Gradle 9.6.1), `gradle/libs.versions.toml` (AGP 9.3.3, Kotlin 2.4.21,
  Ktor 3.6.0, Retrofit 2.x, OkHttp — versions already in `~/.gradle/caches` where possible),
  `.gitignore` (`build/`, `.gradle/`, `local.properties`, `.sextant/`). Parts:
  - `:shared` — `org.jetbrains.kotlin.multiplatform` + `com.android.kotlin.multiplatform.library`
    (copy the `kotlin { android { … } jvm() }` shape of kotlinconf `core/build.gradle.kts`,
    compileSdk 37, minSdk 28). `commonMain`: `expect fun pricingUrl(): String` and
    `class PricingClient(private val client: HttpClient) { suspend fun quote(id: String) = client.get(pricingUrl() + "/" + id) }`.
    `jvmMain` actual: `"https://pricing.internal.example/quote"`; `androidMain` actual:
    `"https://pricing.example.com/quote"`.
  - `:server` — `org.jetbrains.kotlin.jvm`, `implementation(project(":shared"))`, a `main` that calls `PricingClient.quote`.
  - `:app` — `com.android.application`, compileSdk 37, minSdk 28, `implementation(project(":shared"))`,
    flavor dimension `tier` with `free` and `paid`, each `buildConfigField("String", "API_URL", …)`
    (`"https://free.api.example/"`, `"https://paid.api.example/"`), `buildFeatures.buildConfig = true`;
    a Retrofit interface `OrdersApi` with `@GET("orders/{id}")`, built with `BuildConfig.API_URL`;
    a class calling OkHttp `Request.Builder().url("https://status.example.com/health")`.
- Modify: `sextant-model.init.gradle` (KMP branch), `gradle.py` (`_identity`, `_sibling_roots`, `_module_of`)
- Test: `tests/ingress/test_gradle_detector.py`; capture `tests/ingress/gradle-captures/gradle-android/`
  (written in Task 5 once Android parts are read; this task's tests use hand-built records)

**Interfaces:**
- Init script, `org.jetbrains.kotlin.multiplatform` applied: one record per target whose
  `platformType` is `jvm` — `target = target.name`, `platform = "jvm"`; sources: each
  `compilations.main.allKotlinSourceSets` `kotlin.srcDirs` under language `kotlin`; classes:
  `compilations.main.output.classesDirs`; classpath configuration:
  `configurations[compilations.main.compileDependencyConfigurationName]`; the task depends on
  `output.classesDirs`. The `java` branch is not used for a KMP project (its `withJava()` main IS the jvm target).
- Every classpath entry with a `ProjectComponentIdentifier` gets `"platform"`: the value of the
  artifact variant attribute named `org.jetbrains.kotlin.platform.type`, as a string, or null.
- `_identity(project, reactor)` — when the reactor holds more than one record for this project's
  path, the name part gets `-<target>` (`com.acme:shared-jvm`; ungrouped `ShopApp:shared-jvm`);
  `results_name = target`. One record: unchanged, `results_name = None`.
- `_sibling_roots` — candidates = records at `projectPath`; one candidate: joined as today; several:
  the one whose `platform` equals the entry's `platform`; none or no label: no root, and
  `libraries_not_resolved` gains `"could not tell which version of <path> this part uses"`.
- Reactor lookups keyed by path alone (`_identity`'s root lookup, `_sibling_roots`' `by_path`)
  become path → list of records.

- [ ] **Step 1: Create the fixture** and build it once:
  `cd fixtures/gradle-android && JAVA_HOME=$(/usr/libexec/java_home -v 21) ANDROID_HOME=/opt/homebrew/share/android-commandlinetools ./gradlew :shared:jvmJar :server:classes :app:assembleFreeRelease` — BUILD SUCCESSFUL.
- [ ] **Step 2: Write failing tests:** `test_a_two_version_part_gives_one_module_per_version_named_with_a_dash`
  (grouped and ungrouped); `test_a_part_uses_the_version_gradle_labelled` (`:server` entry `platform: "jvm"`
  joins `shared-jvm` classes only); `test_a_two_module_part_with_no_label_is_a_named_gap`;
  `test_a_one_version_part_keeps_its_name`.
- [ ] **Step 3: Run** — FAIL. **Step 4: Implement.** **Step 5: Run** — PASS.
- [ ] **Step 6: Real check:** detect `fixtures/gradle-android` with `ANDROID_HOME` set and print
  modules: `com.acme:shared-jvm` (classes under `shared/build/classes/kotlin/jvm/main`) and
  `com.acme:server` whose library roots include only `shared-jvm`'s classes.
- [ ] **Step 7: Commit** `feat(gradle): Kotlin Multiplatform JVM versions as modules, used by Gradle's label (Android M1, M2)`.

### Task 5: Android parts — release build, one module per edition (§2a, §2b, M3)

**Files:**
- Modify: `sextant-model.init.gradle` (Android branch), `gradle.py` (notes, `_module_of`)
- Modify: `.github/workflows/pr.yml` (prime `fixtures/gradle-android` too)
- Create: `tests/e2e/test_gradle_android_fixture.py`; capture `tests/ingress/gradle-captures/gradle-android/`
- Test: `tests/ingress/test_gradle_detector.py`

**Interfaces:**
- Init script: for each of `com.android.application`, `com.android.library`,
  `com.android.kotlin.multiplatform.library` (`plugins.withId`), read
  `androidComponents.onVariants(androidComponents.selector().all(), Action)` (measured on AGP 9.3.3
  for the application and KMP library plugins). Keep a variant when `buildType == "release"`, or when
  `buildType == null` (the KMP Android library's one variant, `androidMain`). One per-variant task
  `sextantModel<VariantName>` registered inside the callback, which `sextantModel` depends on, receives
  `variant.artifacts.forScope(ScopedArtifacts.Scope.PROJECT).use(task).toGet(ScopedArtifact.CLASSES.INSTANCE, jarsProperty, dirsProperty)`.
  Record: `classesDirs` = dirs; `sources` from `variant.sources.java` / `variant.sources.kotlin`
  (`.all` provider) under `java` / `kotlin`; classpath configuration `variant.compileConfiguration`;
  `target` = `variant.flavorName` when not empty, else for a KMP Android library the Kotlin target
  whose `platformType` is `androidJvm` (its `name`), else null; `platform = "androidJvm"`;
  `projectJars` = jar paths (Task 5 Python turns them into a note).
- AGP older than 7.4 (no `ScopedArtifacts` class): one record with `"buildFailure"`:
  `"Android Gradle Plugin <version> is older than 7.4, which Sextant needs to read Android parts"`.
- An Android part with no kept variant: one record with `"buildFailure"`: `"no release build: nothing that ships to read"`.
- Python: `projectJars` non-empty → note `"<module id>: AGP also lists class jars Sextant does not read: <file names>"`.
- `_identity` naming from Task 4 applies unchanged (`ShopApp`'s `:app` → `com.acme:app-free`,
  `com.acme:app-paid`; `:shared` → `com.acme:shared-jvm`, `com.acme:shared-android`).

- [ ] **Step 1: Write the e2e test** `test_the_android_fixture_gives_every_module_and_its_outbound_rows`
  (skips without `ANDROID_HOME` or on an unprimed cache, like the existing Gradle e2e): `module analyze`
  analyses `app-free`, `app-paid`, `shared-jvm`, `shared-android`, `server`; `app-free`'s outbound rows
  hold `https://free.api.example/orders/{id}` and `https://status.example.com/health`; `app-paid` holds
  `https://paid.api.example/orders/{id}`; `shared-android` holds `https://pricing.example.com/quote/{…}`
  and never `pricing.internal.example`; `server` reaches `pricing.internal.example` only. (Exact row
  spelling: read it off the first green run and pin it.)
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Capture** the assembled document for the unit suite with `{root}`/`{home}`
  placeholders (the `gradle-orders` capture's rule) and add `test_the_android_capture_names_five_modules`.
- [ ] **Step 6: CI:** priming step also runs the argv in `fixtures/gradle-android` with
  `ANDROID_HOME: ${{ env.ANDROID_HOME }}` (GitHub Ubuntu runners carry the SDK; AGP installs missing platforms).
- [ ] **Step 7: Commit** `feat(gradle): Android parts — release build, one module per edition (OI-274)`.

### Task 6: Documents

**Files:** `docs/components/M02-detector.md`, `gradle.py` docstring ("Android variants are not
modelled" removed), `docs/COVERAGE.md` §6 Android rows and the mobile page, `CHANGELOG.md`,
`docs/open-issues.md` (id-map rows for any OI logged during the build).

- [ ] **Step 1:** write them from the measured results (fixture and the corpus hand check).
- [ ] **Step 2:** `scripts/check.sh` green; commit `docs: Android outbound (OI-274)`.

### Task 5b: One description file per module in a shared folder (M7)

**Files:** `src/sextant/domain/enrichment.py` (`ENRICHMENT_FILE` users), `src/sextant/api.py`
(every `path / ENRICHMENT_FILE`), `src/sextant/application/enrich/tools.py`, M00/M09 docs where the
file is named. Test: the existing enrich/render/export tests' files.

**Interfaces:** `enrichment_file(module_root: Path, results_name: str | None) -> Path` in
`domain/enrichment.py` = `<root>/.sextant-enrichment.json` when `results_name` is None, else
`<root>/.sextant-enrichment-<results_name>.json`. Every reader and writer goes through it; the
module's `results_name` comes from the module being enriched/rendered (for a `--workspace` run,
from the results folder name when it is a sub-folder of `<root>/.sextant`).

- [ ] Tests: `test_two_modules_in_one_folder_keep_their_own_descriptions` (enrich A, enrich B,
  render A shows A's claims only); `test_a_one_module_folder_keeps_the_old_file_name`.
- [ ] Implement; covering tests and full gate; commit `feat(enrich): one description file per module in a shared folder (Android M7)`.
