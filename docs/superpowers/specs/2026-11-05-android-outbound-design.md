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
a separate shipped app; the module is then read once per release variant, its module named by
the M2 rule with Android's own name for the flavor combination (`variant.flavorName`):
`Noty.app` → `Noty.app-free`, two flavor lists → `Noty.app-freeStaging` (M3, ruled B). **0 flavored builds in the
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
2. **Each part answers for itself (M4, ruled B).** With `org.gradle.parallel=true` (kotlinconf, koog)
   the root task's `doLast` cannot resolve another project's configuration ("without an exclusive
   lock") — this already breaks detection of kotlinconf's plain JVM `:backend` today. So every
   project, `java`, Android and KMP alike, gets one task of its own that resolves only its own
   configurations and writes its record; the root task only assembles the records. Parallel builds
   stay parallel. Guard: every Gradle build in examples/ and `fixtures/gradle-orders` give the same
   detection before and after.
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

## 4. Self-review 2026-11-05 — all five ruled by the user

Five Major findings (no Critical), each ruled by the user 2026-11-05. Minor findings are fixed above, marked "self-review, my call".

- **M1. A KMP project gives two modules under one Gradle path.** kotlinconf `:core` has `jvm()` and
  `android`; `:backend` uses its JVM half, `:app:androidApp` uses `:app:shared`'s Android half. The
  detector joins a sibling by project path only (`_sibling_roots`, `_identity`'s `{path: record}`),
  so one of the two records is lost and a part can be given the other version's classes.
  **Ruled 2026-11-05: A.** The init script records the label Gradle puts on the version it picked
  (`org.jetbrains.kotlin.platform.type`, `jvm` / `androidJvm`) and the lookup uses path plus label.
  A label Sextant does not know is reported ("could not tell which version"), never guessed.
- **M2. The name of each version's module.** **Ruled 2026-11-05: A.** Today's name (OI-273) with a
  dash and the version name the build file gives (`jvm()`, `android {}`) added to the last part:
  kotlinconf `:core` → `KotlinConfApp:core-jvm` and `KotlinConfApp:core-android`; a grouped part →
  `org.jetbrains:core-jvm`. The same spelling Kotlin uses when it uploads each version. A part built
  once keeps today's name. Two modules with one name stop analysis with a clear message.
- **M3. Apps built in several editions (flavors).** **Ruled 2026-11-05: B.** One module per release
  edition, named by the M2 rule with Android's own name for the edition (`variant.flavorName`):
  `Noty.app-free`, `Noty.app-freeStaging`. Code shared by every edition appears once per edition,
  which is true: each shipped app makes the call. Checked on a test app only (0 flavored builds in
  the corpus), stated as such.
- **M4. One way to collect, parallel kept.** **Ruled 2026-11-05: B** (see 2e.2). Replaces the
  `--no-parallel` call.
- **M5. One part that fails to build no longer stops the others.** **Ruled 2026-11-05: B.** Gradle runs
  with `--continue` (needs M4's one task per part). A part whose task failed is skipped with Gradle's
  own error as its reason, through the existing skip reasons; a part that uses it is skipped with
  Gradle's reason too. The output states every skipped part at the top. Plain `java` builds gain the
  same: one broken part no longer blocks the rest.
- **M6. Two modules from one folder would overwrite each other's results.** Found while planning.
  Results live at `<module folder>/.sextant`, and `modules.json` names a module by its folder, so
  `core-jvm` and `core-android` (or `app-free` and `app-paid`) would share `core/.sextant`.
  **Ruled 2026-11-05: A.** A folder holding several modules keeps one `.sextant` folder with one
  sub-folder per module, named by the version or edition name (`core/.sextant/jvm/`,
  `core/.sextant/android/`); a folder with one module keeps `core/.sextant/` as today. Each
  `modules.json` row gains `results`, the results folder relative to the repository root
  (`"results": "core/.sextant/jvm"`) — **a change to the `modules.json` format, approved by the
  user** — and a row without it means `<dir>/.sextant`, so older files keep working.
  `system analyze` finds results through `results`. A single-module command (`render`, `enrich`,
  `export`, `diff`) at a folder whose `.sextant` holds several modules stops and lists each
  module with its exact `--workspace` command; it never picks one.
- **M7. The description file of two modules in one folder.** Found while building Task 3.
  `enrich` writes `.sextant-enrichment.json` in the module folder (meant for git review), so two
  modules in one folder would overwrite each other's descriptions. **Ruled 2026-11-05: A.** One file
  per module, named with the version or edition name: `core/.sextant-enrichment-jvm.json`,
  `core/.sextant-enrichment-android.json`; a folder with one module keeps
  `.sextant-enrichment.json`. `enrich`, `render` and `export` read and write the module's own file.
- **M8. Retrofit lines have no server address but are marked complete.** Found while building
  Task 5; pre-existing for every Retrofit line (and `@HttpExchange` / MicroProfile clients whose
  address is set where the client object is made). **Ruled 2026-11-05: A, in this pull request.**
  Follow a call such as `api.order(id)` back through `api` to `create(OrdersApi::class.java)` and
  the `baseUrl(...)` of the Retrofit object that made it, using the existing object-following
  rules, and join the address to the path. Where the address is not in code Sextant can follow, the
  line is marked partial ("server address not read"), never complete. A new setup-file (catalog)
  word, if one is needed, is shown to the user before use.
