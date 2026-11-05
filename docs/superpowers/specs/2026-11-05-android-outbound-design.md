# Android modules — outbound — design

**Status: DRAFT 2026-11-05, for the user's approval.** Plane OI-274 = SEXTANT-268, the last open
item of "Java/Kotlin complete" (SEXTANT-265) besides Akka (PR #91). Android **inbound** (deep
links, manifest, exported components) stays post-MVP (COVERAGE §6); this design is outbound only.
Branch `cov/android-outbound`, cut from `fix/gradle-no-group` (PR #90), which it needs.

## 1. The gap, measured

- An Android module applies `com.android.application`, `com.android.library` or
  `com.android.kotlin.multiplatform.library`, never Gradle's `java` plugin. The init script
  (`ingress/detect/sextant-model.init.gradle`) reads source sets, class directories and the compile
  classpath only for `java` projects, so an Android module reports nothing and is skipped ("no
  source and no compiled classes"). No Android app can be analysed today.
- AGP 9 (kotlinconf-app uses 9.3.3) removed the old variant API (`applicationVariants`); the
  supported API is `androidComponents.onVariants { variant -> … }`.
- The classes exist before dexing as ordinary JVM classes (built kotlinconf-app
  `:app:androidApp:assembleRelease` with JDK 21 and the user's SDK, 2026-11-05):
  `app/androidApp/build/intermediates/built_in_kotlinc/release/compileReleaseKotlin/classes`, and the
  KMP library's Android half under `app/shared/build/classes/kotlin/android/main`. The extractor
  reads them unchanged (COVERAGE §6: "Android needs no new scanner").
- The outbound catalogs already exist: Retrofit, OkHttp, Ktor client.

**Corpus** (examples/, 2026-11-04): 4 Android builds — NotyKT (Retrofit), kotlinconf-app (Ktor
client in KMP `shared`), koog demo-compose-app, ktor-samples client-mpp. **No product flavors, no
debug- or release-only source folders**: debug and release compile the same code in every one.

## 2. Design

### 2a. Ask AGP, never guess paths (the OI-273 rule: "what's the truth?")

The init script gains an Android branch, registered with `plugins.withId(...)` for each of the
three Android plugin ids, reading through `androidComponents.onVariants` at configuration time and
reporting in the same JSON record the `java` branch writes:

| Field | From AGP |
|---|---|
| `classesDirs` | the directories in the variant's project classes — `variant.artifacts.forScope(PROJECT).use(task).toGet(ScopedArtifact.CLASSES, …)`: what AGP itself hands to bytecode instrumentation, every language included. Jars in that list are not read (see 2e.5) |
| `sourceRoots` / `sourceLanguages` | `variant.sources.java` / `variant.sources.kotlin` directories (language = the set that registered it, as for `java` projects) |
| `classpath` | the variant's compile classpath (2e.7), artifacts and sibling projects, read as the `java` branch reads `compileClasspath` |
| `declaredRelease` | the variant's Java target, where AGP states one; else null |

The callbacks are registered at configuration time; the values are read when the consumer task
runs. `toGet` wires the consumer task to the tasks that produce the classes, so detection compiles
what it reads without a separate `dependsOn`.

**One record builder (my call).** The `java` branch and the Android branch differ only in where
they get three inputs: the source directories per language set, the class directories and the
compile-classpath configuration. One Groovy closure turns those inputs into the record (generated
directories, language attribution, classpath entries). Neither branch has its own copy of that
logic.

### 2b. Which variant — **my recommendation: the release build type**

What ships to users is the release build; debug adds only debugging aids. So the module is read
from its **release** variant. Where a project has product flavors, each flavor's release variant is
a separate shipped app; the module is then read once per release variant, its module id the
project's id plus the flavor name (`Noty.app` → `Noty.app:free`). **0 flavored builds in the
corpus**, so the flavored branch is built with a fixture only. A project with no release variant
(a test-only module) is skipped with its reason.

### 2c. Identity — unchanged

The module id is what Gradle reports, by the OI-273 rule (group from Gradle, default group for a
subproject); the Android `applicationId` is not used for identity (it can differ per variant and
is not what a sibling module or a Maven consumer references). It is recorded as module metadata.

### 2d. Not in this design

- Android inbound (manifest, deep links, exported components, `Worker`s) — post-MVP.
- Debug variants, instrumented-test and unit-test classes.
- KMP targets that are not JVM bytecode (iOS, JS, wasm).
- An APK/AAB reader (DEX) — never needed, the build has the classes.

### 2e. Calls after the builder check (2026-11-05, my calls under the user's rulings)

Measured against the AGP 9.3.3 API (javap) and init-script probes on kotlinconf-app:

1. **The variant read:** the release build type; **or the only variant, where the project has no
   build types** — a KMP Android library (`com.android.kotlin.multiplatform.library`) has exactly one
   variant, `androidMain`, `buildType=null` (kotlinconf `:core`, `:app:shared`, `:app:ui-components`).
2. **Detection runs Gradle with `--no-parallel`.** With `org.gradle.parallel=true` (kotlinconf, koog)
   the root task's `doLast` cannot resolve another project's configuration ("without an exclusive
   lock") — this already breaks detection of kotlinconf's plain JVM `:backend` today. The probe is a
   one-shot read; correctness over speed. M02 and the pinned argv change.
3. **AGP 7.4 and newer** (where `ScopedArtifacts` and `androidComponents` both exist): AGP 8.12/8.13
   (koog, ktor-samples client-mpp) and 9.x (kotlinconf, NotyKT). An older AGP is skipped with its
   reason. `ScopedArtifact.CLASSES` is every project class whichever plugin compiled it (built-in
   kotlinc in AGP 9, the Kotlin plugin in AGP 8).
4. **KMP targets are modules as Kotlin publishes them.** A KMP project publishes one artifact per
   target (`core-jvm`, `core-android`); each JVM-bytecode target (`jvm()`, Android) becomes its own
   module record, named as its publication names it (the OI-273 rule: the build tool's own identity).
   Today neither target is read (the init script reads only `java` projects). iOS/JS targets: out.
5. **The consumer:** a typed per-project task defined in the init script receives
   `ScopedArtifact.CLASSES` (`ListProperty<RegularFile>` jars, `ListProperty<Directory>` dirs);
   Groovy passes `onVariants(selector, Action)` and `Function1` closures explicitly. **Only the
   directories are read (self-review, my call).** The module scan reads directories only
   (`analyze.py` keeps `output_dirs` that are directories), so a jar reported beside them would
   need a new fact field (a fact-schema change) for no gain: the project-scope jar AGP adds is
   `R.jar`, generated resource-id constants with no calls in it. A project-scope jar is named in a
   detect note, never dropped silently.
6. **Generated source dirs** (`build/generated/...`) are treated as for `java` projects: language
   attribution yes, source roots no. AGP's `java` set also holds `src/main/kotlin`, so that
   directory is attributed to both `java` and `kotlin`, the mirror of the Kotlin plugin adding
   `src/main/java` to its own set on a `java` project. Same rule, same result.
7. **Classpath:** `variant.compileConfiguration` resolved through `incoming.artifacts` (component
   identifiers, so sibling projects join as today), artifact type classes-jar. The Android SDK's
   `android.jar` (the boot classpath) is not on it and is not added: `java.*` types come from the
   extractor's own JDK as for every module, and no outbound catalog matches an `android.*` type.
   `android.*` supertypes stay unread, a stated boundary.
8. NotyKT: one library (`:app`) consumed by two apps (`composeapp`, `simpleapp`) — two app modules
   each reading the library's release classes as a sibling.
9. The configuration cache is safe because the argv already passes `--no-configuration-cache`.

## 3. Done when

- A Gradle fixture with an Android app and an Android library (JDK 21, SDK at
  `/opt/homebrew/share/android-commandlinetools`), a Retrofit interface and an OkHttp call:
  detection reports both modules with their release classes; analysis gives the outbound rows.
- kotlinconf-app and ktor-samples client-mpp analysed: every outbound row checked against the
  source by hand, the KMP `jvm` modules included (kotlinconf `:backend` reads `:core`'s JVM classes,
  `:app:androidApp` reads `:app:shared`'s Android classes). NotyKT needs a JDK 17 toolchain, not
  installed — analysed if the user installs `openjdk@17`, otherwise stated.
- CI: GitHub's Ubuntu runners carry the Android SDK (`ANDROID_HOME`); the Android fixture joins the
  existing Gradle priming step, so its offline test has AGP cached. Locally the test is skipped
  when no SDK is found, with that reason.
- Gate green, six field pins unchanged (no pin is Android), M02 (detector) and the `gradle.py`
  docstring ("Android variants are not modelled" is no longer true), COVERAGE §6, CHANGELOG.

**Catalogs.** None added and none changed: Android outbound goes through Retrofit, OkHttp and Ktor
client, which already exist. Everything Android-specific is in the detector. The four Android
builds have no Volley, `HttpURLConnection` or Apollo call in app code (one koog test file uses
`HttpURLConnection`), so no catalog gap is measured.

## 4. Self-review 2026-11-05 — open for the user's decision

Five Major findings (no Critical). Minor findings are fixed above, marked "self-review, my call".

- **M1. A KMP project gives two modules under one Gradle path.** kotlinconf `:core` has `jvm()` and
  `android`; `:backend` uses its JVM half, `:app:androidApp` uses `:app:shared`'s Android half. The
  detector joins a sibling by project path only (`_sibling_roots`, `_identity`'s `{path: record}`),
  so one of the two records is lost and a part can be given the other version's classes.
  **Ruled 2026-11-05: A.** The init script records the label Gradle puts on the version it picked
  (`org.jetbrains.kotlin.platform.type`, `jvm` / `androidJvm`) and the lookup uses path plus label.
  A label Sextant does not know is reported ("could not tell which version"), never guessed.
- **M2. The identity of a KMP target module is not defined.** "Named as its publication names it"
  holds only where `maven-publish` is applied, and §2c says identity is unchanged. Recommendation:
  the OI-273 identity with `-<target name>` added to the name, which is the artifact id the Kotlin
  plugin itself gives each target (`core-jvm`, `core-android`); for an ungrouped project the same
  suffix on the last path segment.
- **M3. Flavored apps get an invented id (`Noty.app:free`).** Nothing in Gradle or AGP spells it so,
  and `:` already separates path segments in ungrouped ids. 0 flavored builds in the corpus.
  Recommendation: refuse a flavored project with a named reason now and log an OI; design the id when
  a real flavored build is in the corpus.
- **M4. Two collection paths, and `--no-parallel` on every Gradle build.** The `java` branch reads
  every project from the root task's `doLast`; the Android branch reads from a per-project task.
  Reading another project's configuration from the root is what breaks under
  `org.gradle.parallel=true`, and `--no-parallel` fixes it by compiling every Gradle build serially.
  Recommendation: one per-project task for every project (each resolves its own configurations,
  which Gradle permits in parallel), the root task only assembles the records. One path, parallel
  kept.
- **M5. An Android compile failure refuses detection of the whole repository.** Today Android
  modules are not compiled, so a mixed repository (backend plus app) is detected. After this design
  any failure in the Android release compile refuses all of it. Realistic causes: a gitignored
  `google-services.json` (common in public Firebase apps), a missing JDK toolchain (NotyKT, koog).
  Recommendation: with M4's per-project tasks, run with `--continue`; a project whose task failed is
  skipped with Gradle's own error as its reason, and the others are read.
