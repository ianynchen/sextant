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
`GradleDetector`, `GoWorkDetector`. One Gradle build may hold Java and Kotlin modules, and
the detector reads it once.

## Inputs

Build files. `.sextantignore` and `sextant.yml` ([D04](D04-config-and-exclusion.md)).
**No code.**

## Output

Two forms of the same conclusions.

**The `RepositoryModel`**, in memory, for [M03](M03-scanner.md) in the same run.

**`<repo-root>/.sextant/modules.json`** — the module inventory: ids, paths, kinds,
languages, workspace locations, per-module commits ([D05](D05-manifest-and-state.md)).
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
| Modules | Identifier, root path, kind, languages present, source sets, compiled output directories |
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
`./gradlew --offline -I sextant-model.gradle sextantModel`. The script registers a task
that walks the fully-evaluated model and prints one JSON document. It rides whatever Gradle
version the project pins, so there is no client-library compatibility matrix — the audit
found that the official Tooling API route would *also* need an injected model builder for
source-set precision, making it this mechanism plus a dependency. The script is tested
against conformance fixtures pinned per Gradle major, and convention paths
(`build/classes/java/main`) serve as a sanity check: disagreement with the script's output
is a warning, never a source of truth. Maven needs no such artifact —
`mvn dependency:build-classpath -o` and `help:effective-pom` answer directly.

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

Where resolution fails either way, that is a reported failure carrying the tool's own
output, never a partial model assembled by guessing.

### Discovery reads the build, never a convention

| Build system | Where the module list lives |
|---|---|
| Maven | `<modules>` in the parent POM |
| Gradle | `include` lines in `settings.gradle` |
| Go | `go.work`, or each `go.mod` |
| Node | `pnpm-workspace.yaml`, or `workspaces` |
| Cargo | `members` in the workspace manifest |

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

## What it must not do

- **No reading code.** Not source, not bytecode. It reads build files and lists files.
- **No network by default.** The build tool runs offline; dependency download happens only
  under `--allow-resolve`, and the use of that flag is recorded. If the build has not been
  run, that is a reported failure naming the fix, never a silent download.
- **No guessing a classification.** `undetermined` is a value.
- **No language branching.** Keyed by build system; a module records the languages present.

## Honesty obligations

- Modules whose kind is `undetermined`, and why.
- Classpath entries that failed to resolve — every unresolved entry becomes
  `unindexed_dependency` at some call site later, and this is where it can still be fixed
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
