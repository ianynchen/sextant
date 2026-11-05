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
| `classesDirs` | the variant's project classes — `variant.artifacts.forScope(PROJECT).use(task).toGet(ScopedArtifact.CLASSES, …)`: the directories and jars AGP itself hands to bytecode instrumentation, every language included |
| `sourceRoots` / `sourceLanguages` | `variant.sources.java` / `variant.sources.kotlin` directories (language = the set that registered it, as for `java` projects) |
| `classpath` | the variant's compile classpath (`variant.compileClasspath`), artifacts and sibling projects, read as the `java` branch reads `compileClasspath` |
| `declaredRelease` | the variant's Java target, where AGP states one; else null |

`sextantModel` depends on the variant's class-producing tasks, as it depends on `classes` for a
`java` project, so detection compiles what it reads.

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
   Groovy passes `onVariants(selector, Action)` and `Function1` closures explicitly. Jars in the
   result (R.jar, others) are read as class sources too: the extractor already reads jars for
   libraries; the detector reports them beside `classesDirs`.
6. **Generated source dirs** (`build/generated/...`) are treated as for `java` projects: language
   attribution yes, source roots no.
7. **Classpath:** `variant.compileConfiguration` resolved through `incoming.artifacts` (component
   identifiers, so sibling projects join as today), artifact type classes-jar.
8. NotyKT: one library (`:app`) consumed by two apps (`composeapp`, `simpleapp`) — two app modules
   each reading the library's release classes as a sibling.
9. The configuration cache is safe because the argv already passes `--no-configuration-cache`.

## 3. Done when

- A Gradle fixture with an Android app and an Android library (JDK 21, SDK at
  `/opt/homebrew/share/android-commandlinetools`), a Retrofit interface and an OkHttp call:
  detection reports both modules with their release classes; analysis gives the outbound rows.
- kotlinconf-app and ktor-samples client-mpp analysed: every outbound row checked against the
  source by hand. NotyKT needs a JDK 17 toolchain, not installed — analysed if the user installs
  `openjdk@17`, otherwise stated.
- Gate green, six field pins unchanged (no pin is Android), M02 (detector), COVERAGE §6, CHANGELOG.
