# M02 — Detector

## Purpose

Work out what a repository contains, before anything reads code.

## Interface

```
Detector
  accepts(path)  -> bool            # can this backend read this build system?
  detect(path)   -> RepositoryModel
```

Implementations are keyed by **build system**, not by language: `MavenDetector`,
`GradleDetector`, `PythonDetector`, `GoWorkDetector`. One Gradle build may hold Java and Kotlin modules, and
the detector reads it once.

## Inputs

Build files. `.sextantignore` and `sextant.yml` ([D04](D04-config-and-exclusion.md)).
**No code.**

## Output

Two forms of the same conclusions.

**The `RepositoryModel`**, in memory, for [M03](M03-scanner.md) in the same run.

**`<repo-root>/.sextant/modules.json`** — the module inventory: ids, paths, kinds,
languages, workspace locations (`results`, Android design M6), per-module commits
([D05](D05-manifest-and-state.md)).
Written once per invocation; read by `module list`, by `--refresh-stale` orchestration, and
by anything needing to find every workspace in one hop.

**`module` facts** ([D00](D00-fact-schema.md)), written to each module's workspace. This is not
duplication: [M04](M04-resolver.md) needs the classpath tiering to decide `narrowed` against
`partial`, [M07](M07-renderer.md) needs the first-party package set to filter noise, and
[M06](M06-stitcher.md) needs both on another machine. None of them ever runs the detector,
and a stage resumed with `--from-stage` does not either.

The model itself:

| Part | Contents |
|---|---|
| Modules | Identifier, root path, kind, languages present, source sets, compiled output directories, resource roots |
| Classpath | Per module, resolved and **split into three tiers** |
| Dependencies | Coordinates, scope, and which tier each fell into |
| Frameworks | The active catalog set for each module |
| File inventory | Every file, with its kind, after exclusion |

## Behaviour

### It asks the build tool. It does not parse build files.

`pom.xml` is XML and could be parsed. **A Gradle build cannot be**, and pretending otherwise
would fail on ordinary projects: `build.gradle.kts` is a Kotlin program, versions come from
version catalogs, plugins add source sets and dependencies, and `subprojects` blocks
configure modules that never name themselves.

So the detector **invokes the build tool** and asks it for the module list, the resolved
classpath, the source sets and the output directories. Those are the four things everything
downstream depends on, and only the build tool knows them.

**The Gradle mechanism is an init script, run through the project's own wrapper**:
`<gradle> [--offline] --init-script <ours> --no-configuration-cache --continue -q
sextantBuild sextantModel -Psextant.outDir=<tmpdir>` (2M design §1; `--offline` governs only
the first of at most two attempts — the second is the flagged online retry). The script
registers one `sextantModel` task in every project (one per read build in an Android part), which writes that project's own records to
`projects/<path>.json`, and a `sextantBuild` task in the root project, which writes
`build.json` naming every project (Android design M4). The detector joins the files into one
document. Nothing goes to stdout, which Gradle, the target build's own scripts, and JVM
warnings all pollute. It rides
whatever Gradle version the project pins, so there is no client-library compatibility
matrix — the audit found that the official Tooling API route would *also* need an injected
model builder for source-set precision, making it this mechanism plus a dependency.

**The Maven mechanism is `dependency:build-classpath`, built 2026-10-21**
(spec `2026-10-21-maven-classpath-design.md`): one `mvn -o -q -B [compile]
dependency:build-classpath -Dmdep.outputFile=target/sextant-classpath.txt
-Dmdep.includeScope=compile -Dmdep.regenerateFile=true [-pl <module> -am]` per analysis, from the reactor root, with
`compile` attached only inside a reactor (the goal resolves a sibling only as a built artifact
of the same session) and `-pl` when `analyze` was handed one module. The file it leaves beside
each module's classes is re-used while it is newer than every POM that module is read from,
which is why the suite and a second run start no `mvn`. **Maven differs from Gradle in having
a fallback, and the fallback is labelled** (user ruling, 2026-10-21): where `mvn` is not on
`PATH`, nothing is built, no module declares a dependency, or Maven refuses offline and
`--allow-resolve` is not set, the detector publishes the POM-declared-and-inherited set it has
always read, as `dependency_source: declared` with Maven's own last error line as the reason —
not a partial model assembled by guessing, but the weaker claim, named as such, and the
document's coverage line says which one a reader holds. The detector never builds the
analysed code: a module with nothing under `target/classes` ends the question before any
process starts.

> **2M delivery status (§1b of the [2M design](../superpowers/specs/2026-09-02-phase-2m-build-and-output-design.md)):**
> `GradleDetector` itself shipped in 2M — `src/sextant/ingress/detect/gradle.py`, this same
> init-script mechanism, live against a real fixture (`fixtures/gradle-orders/`). What did
> **not** ship, and stays open M02 future work: conformance fixtures pinned **per Gradle
> major** (2M pins exactly one fixture on one Gradle version), and the convention-path
> sanity check the paragraph above describes — 2M's init script is the only source of truth
> for a Gradle module's classpath and source sets; nothing cross-checks it against
> `build/classes/java/main` or warns on disagreement.

**Offline by default.** The build tool is invoked in its offline mode (`--offline`, `-o`):
it may read the local dependency cache, and it may not reach the network. The prerequisite
is already "a successful build", and a machine that just built the module has the classpath
cached — so the default costs nothing in the common case, keeps detection deterministic
(a `SNAPSHOT` re-resolution can change the classpath between two runs on one commit), and
adds no credential or network requirement the documents never stated.

**`--allow-resolve` opts in to network resolution.** The failure message names the flag, so
the escape is one retry away; snapshot-metadata failures additionally say *why* the network
was needed. The mode used is recorded in `state.json`, the same pattern as
`--allow-uncovered` — a resolution-permitted analysis stays identifiable afterwards.

For Gradle, "the cache lacked it" has two wordings, both retried: a dependency ("No cached
version of … available for offline mode") and a plugin ("could not resolve plugin artifact",
measured on Gradle 8.14.1 and 9.5.0). And a wrapper that downloaded its distribution before the
build failed is a build failure — Gradle's banner says the engine ran — never "distribution not
present".

Where resolution fails either way, that is a reported failure carrying the tool's own
output, never a partial model assembled by guessing.

**One Gradle project that fails to build does not stop the others** (Android design M5, ruled
2026-11-05). `--continue` lets every project that can build finish. When the run fails but
`build.json` was written, each project with no file of its own was not built: it is skipped,
and its reason is Gradle's own message for its failed task (javac's error lines included), or
`not built: a part it needs failed to build (failed: <paths>)` for a project that needs one
that failed. The other projects are analysed. A skipped project's results from an earlier
run are removed, so `system analyze` and `render` never read them as current. A project that
uses a skipped one gets "<path> was not built: <reason>" in `libraries_not_resolved`. A root project that was not built is never a
module in a build with subprojects, so its reason becomes the note "gradle root project at
<dir> was not built: <reason>". Without `--allow-resolve`, a part the cache could not serve has
"(--allow-resolve lets Gradle download it)" after its reason, and the run gets the note "some
parts need dependencies that are not in the local Gradle cache; --allow-resolve lets Gradle
download them"; with it, the whole run is retried online once, into an empty folder, so no file
from the offline attempt is read. A failed run that wrote no `build.json` (a build script that
does not evaluate, a missing distribution), or in which no project that was built has a source
root or a classes directory (a root or folder-only project with no compiling plugin writes its
record anyway), is still a refusal with Gradle's own words: a build broken everywhere must not
end with success.

**The Python mechanism reads the build files, because there is no build tool to ask**
(Python design §3e, built 2026-11-06, `src/sextant/ingress/detect/python.py`). Python has no
one tool that knows the module list, so `PythonDetector` reads `pyproject.toml` and `Pipfile`
with `tomllib`, `setup.cfg` with `configparser`, and `requirements*.txt` as lines. It never
imports or runs scanned code, and nothing is downloaded: `--allow-resolve` does nothing for
Python.

- **Where.** `accepts` finds a Python build file at any depth, by name only (Maven and Gradle
  look at the root only). The walk does not enter `.git`, `node_modules`, `.sextant`,
  `__pycache__`, `.venv`, `.tox`, `.nox`, any folder that holds `pyvenv.cfg` (a virtual
  environment, whatever its name), or another checkout: a folder below the analysed folder
  that holds `.git`, a folder (a clone, a submodule) or a file (a git worktree, such as
  `.claude/worktrees/agent-…`). Each one is a note ("another repository, not analysed:
  <folder>"). The analysed folder is always read, whatever it holds. The scanner shares the
  rule (`is_skipped_folder`); the Maven and Gradle detectors do not use it.
- **What is a module.** A `pyproject.toml` with `[project]`, `[tool.poetry]` or
  `[build-system]`, or a `setup.cfg` with `[metadata]`, marks a module. A file with only tool
  settings marks nothing (CTFd's `setup.cfg` holds only `[nosetests]`). A uv workspace root is
  a module only when it marks one and has Python files of its own outside its members
  (`[tool.uv.workspace]` `members`, less `exclude`). A `requirements*.txt` or `Pipfile` marks
  a module only when its folder holds Python code of its own (not inside a module below it),
  whatever is above it: each service under a project is its own module, and a root lint or
  test list with no code of its own marks nothing ("requirements with no python code of its
  own, not a module: <files>"). A `setup.py` marks a module only when no folder above it is a
  module and it is not inside a package (no `__init__.py` beside it or above it). The `kind`
  is `pyproject`, `setup_cfg`, `setup_py` or `requirements`, strongest first. A repository
  where nothing marks a module is refused: "no Python module found".
- **Unreadable build files.** A nested build file that is not valid TOML or `setup.cfg`, or
  not UTF-8 (a project template with `{{ }}` in it, a tool's test data), is a note ("build
  file not read, so its folder is not a module: <file> (<error>)"), and the rest of the
  repository is detected. Only the build file of the folder that was asked for is a refusal.
- **Identity.** `[project]`, then `[tool.poetry]`, then `setup.cfg [metadata]`, the name
  normalized by PEP 503 (`Shop_Orders.API` is `shop-orders-api`); the name is both the
  `module_id` and the coordinates. A dynamic version (`dynamic = ["version"]`, `attr:`,
  `file:`) is the version in the project's own installed `.dist-info`, else `.`. A module with
  no name (requirements only, or `setup.py` only) is unpublished: coordinates and version
  `.`, and its id is its folder relative to the repository root (its folder name when it is
  the root).
- **Import roots** (`source_roots`): the package settings of setuptools (`package-dir`,
  `packages.find.where`, and the same keys in `setup.cfg`), hatch (`packages`) or Poetry
  (`packages.from`); else `src/` when it holds Python files; else the module folder.
  `output_dirs` are the same folders, because Python runs from source and they are what the
  scanner reads; `packaging` is `wheel`. `lookup` is `c3` (D00 §5 `module`).
- **Entry points** (`entry_points`, D00 §5 `module`; design
  `2026-11-06-reading-decorators-design.md` §7a): each program the module folder's build
  files declare, its name to its target as written (`sextant = "sextant.cli.app:cli"`), from
  `[project.scripts]`, `[tool.poetry.scripts]` (the string form) and `setup.cfg`
  `[options.entry_points] console_scripts`; a name in two tables keeps the first. The target
  is not turned into a symbol here. GUI scripts and `setup.py` `entry_points=` are not read.
  A module that declares none has `{}`.
- **Which folders are searched for modules.** The detector's skip list (version control, tool
  caches, `node_modules`, every folder that holds `pyvenv.cfg`), every path `.sextantignore`
  excludes, and every path a `.gitignore` file at or below the analysed folder names are not
  entered: a git-ignored clone or worktree is not part of the project. The analysed folder
  itself is always read. Git's global excludes file is not read.
- **Environment** (`ModuleModel.environment`): `.venv`, `venv` or `env` beside the build file
  when it holds `pyvenv.cfg` (Poetry's `in-project = true` folder is `.venv`); for a uv
  workspace member, the same names at the workspace root (uv's documented default; the
  process environment, `UV_PROJECT_ENVIRONMENT`, is not read). For a Poetry project
  (`[tool.poetry]`, a `poetry.toml`, or Poetry's build backend), the folder Poetry itself
  names: under `poetry.toml [virtualenvs] path`, else Poetry's default cache
  (`~/Library/Caches/pypoetry/virtualenvs` on macOS, `~/.cache/pypoetry/virtualenvs` on
  Linux), the name from Poetry's own `generate_env_name` (the PEP 503 name, `-`, the first 8
  characters of the URL-safe base64 SHA-256 of the project folder's real path) and then
  `-py<major>.<minor>`. Two such folders are a list this detector cannot narrow, so none is
  read and a note names them; none found is a note too. Poetry's global `config.toml` is not
  read. `.python-version` names an interpreter and is never an environment.
- **Dependencies.** `dependency_coordinates` is every name the module folder's build files
  declare: `[project] dependencies`, Poetry's dependency table, `setup.cfg install_requires`,
  each `requirements*.txt`, and `Pipfile [packages]`. `dependency_versions` is the installed
  version of each, from `<env>/lib/python*/site-packages/*.dist-info/METADATA` (`Name`,
  `Version`), and `dependency_archives` has one `LibraryRoot` per installed one, its archive
  the `site-packages` folder. Where an environment was found, each declared name it does not
  hold is a note, `<name> is not installed in the scanned environment`: that library has no
  symbols (M03 "Libraries").
- **Opted-in libraries** (`.sextant.yml` `extract_libraries`, D04 §2a): each named
  distribution the module declares and its environment holds is a `library_roots` entry,
  its archive the `site-packages` folder; any other is in `libraries_not_resolved` with its
  reason (`<name>: the module declares no such dependency`, `<name>: not installed in the
  scanned environment`, `<name>: its installed RECORD is missing or unreadable, so its files
  are not known`).
- **Notes.** Every top folder of Python files in no module ("python files in a folder with no
  project file, not analysed: <folder>"), every `sys.path.insert`/`append` found by a text
  search of the `.py` files beside a build file (the change is not followed).
- **No module.** A repository where `accepts()` is true but every candidate is ruled out
  (a Maven repository with `docs/requirements.txt` and no code) raises `NoModulesFound`,
  which carries the notes made so far.

### How a repository is detected

`detect_repository` runs EVERY detector whose `accepts()` is true and merges their modules
and notes. A repository with a Maven build and a Python service gives both. The Maven and
Gradle detectors accept only a build file at the root; `PythonDetector` accepts a Python
build file at any depth.

- `multi_module` is true when the merged list has more than one module, or when a detector
  reported it (a reactor that names one child is still a reactor).
- A detector that raises `NoModulesFound` adds no modules when another detector found some.
  When none did, its refusal is the answer.
- **One id for two modules.** Two modules can have one `module_id`, from one detector or
  from two (`examples/py-polar` has two `polar-sdk` projects). Both are kept. Each id that
  more than one module has gets `@<its folder, relative to the repository root>` added
  (`polar-sdk@sdk/python`; `@.` for the root folder). An id that no other module has does
  not change, and `coordinates` stay what the build file says. If the ids are still equal
  after that (two detectors, one folder), the detection is refused and names the id.
- **One folder, several modules.** Modules from different detectors can share a folder (a
  Maven build and a root `requirements.txt`). Each then gets a `results_name`, and its results
  go in `<folder>/.sextant/<results_name>` (Android design M6), the module id with every
  character that is not a letter, digit, `.`, `_` or `-` changed to `-`. A module alone in its
  folder keeps `<folder>/.sextant`. The `@` and `/` of an id never reach a folder name.
- **A detector that fails stops detection.** Only `NoModulesFound` (a detector with nothing
  to report) is tolerated when another detector found modules. Any other error (a malformed
  `pom.xml`, a Gradle run that fails, an unreadable root `pyproject.toml`) is raised with its
  own message, so a partial answer never looks complete. The user can point Sextant at a
  sub-folder.
- **A JVM repository with a Python project is multi-module.** A project file marks a module
  (user ruling), so a Maven repository with a root `requirements.txt` and scripts, or a
  `tools/pyproject.toml`, has two modules. `--workspace` is refused for it and `modules.json`
  is written, as for any multi-module repository.

`select_detector` (the first detector that accepts) stays for a module that is already known.

### Discovery reads the build, never a convention

| Build system | Where the module list lives |
|---|---|
| Maven | `<modules>` in the parent POM |
| Gradle | `include` lines in `settings.gradle` |
| Go | `go.work`, or each `go.mod` |
| Node | `pnpm-workspace.yaml`, or `workspaces` |
| Cargo | `members` in the workspace manifest |
| Python | each `pyproject.toml`, `setup.cfg [metadata]`, `setup.py`, `requirements*.txt` or `Pipfile`, at any depth; `[tool.uv.workspace]` members |

### A module's identity is the one its build tool gives it

The module id and the symbol's `<package-manager> <package> <version>` ([D00](D00-fact-schema.md)
§1) are formed from what the build tool itself does with the project, never from a guess
(OI-273, user ruling 2026-11-03, measured on Gradle 9.8.2):

| Gradle project | `module_id` | symbol manager, package, version |
|---|---|---|
| group and version set | `group:name` | `maven group/name version` |
| group set, no version | `group:name` | `maven group/name unspecified` — Gradle publishes it as `unspecified` |
| no group | a root project is its name alone (`kotlin-ktor-exposed-starter`); a subproject that sets `group = ''` is the root project's name, then its full project path (`Acme:empty`, `Acme:libs:core`) | `. . .` — Gradle refuses to publish it ("groupId cannot be empty"), so it has no coordinates |

Both names in the no-group row are Gradle's own records — the root project name and every
project's path arrive in the init script's document (the root is the entry at path `:`),
never parsed from `settings.gradle`. Every path segment is kept, so `:libs:core` and
`:core` stay distinct.

**In practice the no-group row is a ROOT project.** Gradle gives every subproject a default
group — the root project's name, then its parent's path, dotted: `Acme` for `:lib`,
`Acme.libs` for `:libs:core` — and publishes it under that group (measured on Gradle 9.8.2:
`:lib` of root `Acme`, with no group written anywhere, publishes
`Acme/lib/unspecified/lib-unspecified.jar`). So such a subproject takes the second row,
`Acme:lib` / `maven Acme/lib unspecified`, because that is what Gradle reports. Only a project
whose group is empty — a root project, or a subproject that sets `group = ''` — takes the third.

**A reactor sibling with no group is read as a library root too** (OI-273 round 2): it is on
the compile classpath like any other. It is named by its module id — which is also its
`origin` and its `sibling_coordinates` entry — and marked unpublished (`LibraryRoot.package`
and `version` both `.`), so its classes carry `. . .`, the same symbols they have when that
sibling is analysed as a module of its own. Its facts live under
`facts/lib/(unpublished)/<module id>/`, never parsed as `group:artifact`: the root project — the
one no-group sibling Gradle produces by default, reached through `implementation project(':')` —
has a module id with no `:` at all.

**A Kotlin Multiplatform part gives one module per JVM version** (Android design M1 and M2, ruled
2026-11-05). The init script writes one record per Kotlin version (target) whose platform type
is `jvm`, with its own source, classes and compile classpath. A part that also applies `java`
(`withJava()`) is read only as Kotlin Multiplatform, so its classes are not written twice. A part
with more than one record has one module per version: a dash and the version name from the
build file are added to the last part of the name (`com.acme:shared-jvm`, `ShopApp:shared-jvm`),
the spelling Kotlin uses when it uploads each version, and the results go in
`<folder>/.sextant/<version name>`. An Android record with no version name beside other records
(a Kotlin Multiplatform part with `com.android.library` and no `androidTarget()`) is named
`android`. A part with one record keeps its name. A build whose only
project gives more than one record (a one-project Kotlin Multiplatform library, or a one-project
app with editions) is walked as a reactor, so each of its modules is analysed.

**A sibling with more than one version is joined by Gradle's label.** For each inter-project
classpath entry, the init script records the label Gradle put on the version it picked: the
artifact variant attribute named `org.jetbrains.kotlin.platform.type` (measured on the
`gradle-android` fixture: `jvm` for a Kotlin JVM part, `androidJvm` for an Android part). The
record with that label is joined. No label, or a label that no record carries, is not guessed:
`libraries_not_resolved` gets "could not tell which version of `<path>` this part uses".

**An Android part is read through the Android Gradle Plugin (AGP), never by folder names** (Android
design §2a to §2e; applies to `com.android.application`, `com.android.library`,
`com.android.kotlin.multiplatform.library` and `com.android.dynamic-feature`). Such a part has no `java` plugin, so the init script asks AGP's
`androidComponents.onVariants` for each build it reads, and reports it in the same record a `java`
project gets, through one shared record builder:

- **Which build.** The release build type. A part with no build types (the Kotlin Multiplatform
  Android library has one build, with no build type) is read from that one build. A part with no
  release build is skipped: "no release build: nothing that ships to read". The part was built,
  so this is a skip reason (`skipReason`), not a build failure. A part with product
  editions (flavors) gives one module per release edition, named as for a Kotlin Multiplatform
  version, with Android's own edition name: `Noty.app-free`, `Noty.app-freeStaging`. Code shared
  by every edition is read once for each edition. Debug builds and test classes are not read.
- **Classes.** The directories in AGP's project classes (`ScopedArtifact.CLASSES`): the classes AGP
  itself hands to bytecode instrumentation, whichever plugin compiled them. A directory that
  holds no `.class` file is dropped (the Kotlin plugin adds its tooling metadata as a "class"
  folder). Only directories are read: a jar in the list (AGP adds `R.jar`, the resource-id
  constants) is named in a detect note, never dropped silently.
- **Sources.** AGP's Java and Kotlin source directories, with the language of the set that listed
  each. For a Kotlin Multiplatform part, the Android version's source sets (`commonMain`
  included) are added, because AGP 8 does not list them.
- **Classpath.** The build's `compileConfiguration`, read as a `java` project's compile
  classpath, so a sibling project joins as before. The Android SDK's `android.jar` is not on it
  and is not added: `java.*` types come from the extractor's own JDK, so `android.*` supertypes
  stay unread, and no outbound catalog matches an `android.*` type.
- **AGP floor.** AGP 7.4 or newer (the first with `ScopedArtifacts`). An older AGP is skipped with
  "Android Gradle Plugin <version> is older than 7.4, which Sextant needs to read Android parts",
  also a skip reason, not a build failure.
  AGP 8.13 and 9.3 are measured; 7.4 to 7.x are not.
- **Identity** is the Gradle identity as for any project. The Android `applicationId` is not used.

**A Kotlin Multiplatform part that has no JVM-bytecode version is skipped with a true reason**:
"no JVM or Android target: Sextant reads JVM bytecode only (targets: js)" (the target names are
Kotlin's). A JS, wasm or Kotlin/Native version is never read. This is a stated gap, not a failure.
Three limits are logged (OI-311): Java files in `jvmMain` are not attributed to the module; a part
with two `jvm()` versions gives a gap, not a guess, when a sibling is joined; and the `-<version>`
suffix may collide with the name of a real project.

**Every compiled output directory the build reports is scanned, in one scan** (OI-273). Gradle's
`classesDirs` is a set — one directory per compiling plugin — so a Kotlin JVM project reports
`build/classes/java/main` and `build/classes/kotlin/main`. Every one that exists goes to the
extractor in the same run, so the dependency-header read sees every class's references and the
module's own types across all of them; one that does not exist holds no classes and is skipped.
Maven reports one, `target/classes`.

**A module with nothing to scan is skipped with its reason, never fatal.** No source root and no
compiled output on disk is provably nothing to read — a Maven `pom` module's evidence in another
build's words. `subprojects { apply plugin: 'java' }` gives a folder-only Gradle project such a
shape, and analysing it used to stop the whole reactor. A single-module run with such a
module is refused with the same reason, never a traceback, before anything is written. So is
a module whose classes are in a language no scanner reads (a Scala-only or Groovy-only
module): the reactor skips it with the scanner choice's own words and analyses the rest.

**A Gradle module's languages are the source-directory sets Gradle reports**, never a
directory's name (OI-273 round 2). The init script reports, per source root, which set
registered it — the Java plugin's `java`, and every `SourceDirectorySet` another plugin hangs on
the source set under its own name (`kotlin`, `groovy`), as an extension or, for an older plugin
(Kotlin 1.6.21 on Gradle 8.14.1, measured), as a convention — and a module's languages are those
of its roots that exist on disk, together with those of any generated directory Gradle reports
(under the build directory, so never a source root) that holds a file — a module whose only code
is generated (OpenAPI generator, jOOQ, protobuf) is written in the language of the set that
compiles it. An empty generated directory, such as the annotation-processor output the java
plugin creates on every compile, names nothing.

`kotlin.srcDirs("src")` is therefore `kotlin`, and `src/main/java` in a Kotlin JVM project is
both `java` and `kotlin`, because the Kotlin plugin registers it too. Maven still names a root's
language by its directory, as before.

A repository holding three services produces three modules, **each with its own
workspace**. A sibling module enters a dependent's analysis as a first-party dependency
through its build output — **by build declaration, no group pattern needed** — so
cross-module calls resolve inside each workspace, while each module remains a separate
participant at the system tier. The monorepo is not a special case: a sibling is exactly a
first-party library whose repository happens to be shared.

### Service or library, from evidence

A module is a **service** if it produces something deployable — a boot plugin applied, a
declared main class, a container file, or inbound endpoints. It is a **library** if it
publishes an artifact and does none of those.

**Where the evidence does not decide, the answer is `undetermined`, never a guess.**
`sextant.yml` can override it; a curation can too.

### Classpath tiering — the input to almost everything downstream

| Tier | Read how | Decided by |
|---|---|---|
| Module output | Fully, bodies included | It is the subject |
| **First-party dependency** | **Fully, bodies included** | `first_party.groups` patterns |
| Third-party dependency | Signatures only | Everything else on the classpath |
| Platform | Not read; recorded by name | `java.*`, `javax.*`, `jdk.*` |

> **2M delivery status:** this three-tier split and the `module` facts below are Maven's
> route, and — per the 2M design's own §1 — not even Maven's: `MavenDetector` never runs
> Maven and produces no classpath facts of its own; the `module`-fact/`ClasspathEntry` route
> is documented dead already (2I spec). `GradleDetector` does not tier at all — it builds
> `LibraryRoot`s directly from the init script's own classpath report (jar path from
> Gradle, coordinates from the component id it names), through its own route, stated in 2M
> design §1. A three-tier classpath and `module` facts for Gradle stay open M02 future
> work.

**First-party jars are read in full because the code that matters is often inside them.** A
shared client library wraps the HTTP call; if only its signatures are read, the calling
service appears to have no outbound endpoints at all and the system tier loses the link.
Nothing needs to be fetched or rebuilt — the jar is already on the classpath.

**Transitivity is free.** The build tool already resolved the closure, so a first-party
library two levels down is on the classpath and matches the same pattern.

**A first-party dependency becomes a module** in the workspace, classified as a library, so
its symbols carry their own coordinates and join across services.

**This tiering is what makes `narrowed` mean something.** A type nothing outside the indexed
set can implement has a complete candidate set; otherwise the set is `partial`. Without
the boundary, that distinction is a judgement call at every call site.

### Framework detection

Dependency coordinates against each catalog's `detect` block ([D02](D02-catalog-schema.md)).
Several may match — a repository may use Spring and Micronaut — and the result is a **set**.
Engines join the whole set.

### Source sets, for the coverage check

The detector records which source sets the build compiles. [M03](M03-scanner.md) compares
against **that**, not against every file on disk — otherwise test sources, other-platform
source sets, and modules outside the requested build all report as uncovered, and an alarm
everybody silences is worse than no alarm.

### Resource roots, for the config reader

Where the build's own resource directories live — `src/main/resources` for Maven — so
[M03](M03-scanner.md)'s `ArtifactReader` port knows where to look for configuration files
without parsing a build file itself (Phase 2F). A build system that names none reports the
empty tuple, never a guess.

## What it must not do

- **No reading code.** Not source, not bytecode. It reads build files and lists files.
- **No network by default.** The build tool runs offline; dependency download happens only
  under `--allow-resolve`, and the use of that flag is recorded. If the build has not been
  run, that is a reported failure naming the fix, never a silent download.
- **No guessing a classification.** `undetermined` is a value.
- **No language branching.** Keyed by build system; a module records the languages present.

## Honesty obligations

- Modules whose kind is `undetermined`, and why.
- Classpath entries that failed to resolve — every unresolved entry becomes an
  `external` call site later, and this is where it can still be fixed
  with a setting.
- Dependencies matching no first-party pattern but sharing a group prefix with one, as a
  likely misconfiguration.
- Sub-projects found in the build but excluded by `.sextantignore`.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether a module with no compiled output is an error at detection or at scanning | M03 |
| Whether classification looks at inbound endpoints, which are not known until after M04 | The service and library split |
| Whether an offline mode is possible, given that resolution may need to reach a repository | Air-gapped use |
