# The Maven classpath, asked of Maven — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Status: BUILT 2026-10-21** — rulings a, b, c agreed, all four tasks done; the measured
result is in the spec's §1 BUILT block and `OI-167` is closed.

**Goal:** `OI-167`. On Maven the `type_header` read sees a module's direct declarations only;
asked of Maven itself, the classpath is the real one. Measured target (spec §1): `genai`
9 → 94 headers, `spring-petclinic-rest` 13 → 197, `yudao-module-system` 0 → 335; and the
same file answers `dependencies.py`'s transitive gate and the Data REST boundary row.

**The deliverable is the document**, not a detector field: the coverage line of spec §3e on a
real module, and the `@ControllerAdvice` rows producing on the field corpus.

**Spec:** `docs/superpowers/specs/2026-10-21-maven-classpath-design.md` — read §2 (the two
facts about the goal), §3c (the fallback ruling) and §3d (why the suite never spawns `mvn`)
before Task 1.

## Global Constraints

- **Offline by default; online once under `--allow-resolve`; never otherwise** (M02, ruling
  a/b). The offline refusal is recognised by Maven's own phrase, as Gradle's is.
- **No resolver of our own.** A line of Maven's file is read; nothing is inferred about one
  that is not under the local repository.
- **The detector names no language** (`test_language_confinement`, `test_source_rules`);
  `java`/`classpath` leaks are pinned per file in `known_leak`; `maven.py` gained `classpath`
  there for the reason Gradle's entry has it (the goal's own name), and nothing else did —
  the two model fields were named `dependency_source`/`dependency_source_reason` for that.
- **No `mvn` in unit tests** (2M design §4's rule for Gradle, applied here): the subprocess
  half and the file-to-model half are separate functions; a test that drives `detect` on a
  temporary POM must be shown not to start a process.
- **Fixtures are built with JDK 21.** The gate is
  `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`; `scripts/check.sh --guards`
  and `python scripts/field_check.py` close every task that changes what is read.
- **Branch `cov/maven-classpath`**, from `main` after PR #57.
- Match the surrounding style (GUIDELINES §3, §13.5); do not refactor adjacent code.

## File Structure

| file | responsibility |
|---|---|
| `src/sextant/ingress/detect/maven.py` | the invocation, the re-use rule, the file-to-model translation, the fallback label |
| `src/sextant/application/ports/detector.py` | `ModuleModel.dependency_source`, `dependency_source_reason` |
| `src/sextant/domain/facts.py` | the same two on `ModuleFact`; `Document.type_headers_unlocated` |
| `src/sextant/application/stages/analyze.py` | writes the two onto the module fact |
| `extractor-jvm/.../Main.java` | header document always written when a classpath was given; the unlocated count on it |
| `src/sextant/storage/duckdb/{schema.sql,workspace.py}` | the column, and `coverage` reading it |
| `src/sextant/egress/render/document.py` | the one coverage line (spec §3e) |
| `tests/fixture_build.py` | priming runs the classpath goal, so CI has the plugin and the files |
| `fixtures/orders-advice/pom.xml` | drops the direct `spring-context`; the chain now crosses a TRANSITIVE |
| `tests/ingress/test_maven_detector.py`, `tests/e2e/test_type_headers.py` | the pins |
| `docs/components/M02-detector.md`, `D00-fact-schema.md`, `docs/COVERAGE.md`, `docs/open-issues.md`, `CHANGELOG.md` | as built |

---

## Task 1 — the detector asks Maven, and says when it could not · **DONE**

- [x] Reactor root: reuse `_reactor_modules`' `<parent>` walk to find the root; the module's
      path relative to it is the `-pl` argument.
- [x] `_classpath_file(...)`: the subprocess half — offline first, online once under
      `allow_resolve`, `compile` attached only for a reactor root; a failure returns the
      reason (Maven's own last `[ERROR]` line, or the named precondition: no `mvn`, no
      `target/classes`), never raises.
- [x] Re-use rule (spec §3d): the file is newer than every POM read for the module.
- [x] `_classpath_entries(file)`: the translate half — jars under the local repository to
      `(coordinate, version, archive)`; directories to sibling roots; anything else named
      in `libraries_not_resolved` with its reason, as Gradle's path-only entries are.
- [x] `_module_of` fed from the entries when present: `dependency_archives`,
      `dependency_coordinates`/`dependency_versions` (the closure), sibling roots; the
      declared set and `dependency_source="declared"` + reason otherwise.
- [x] Unit tests from a CAPTURED file; a test proving a temporary-POM `detect` starts no
      process; a test that the offline refusal is retried online only under the flag.
- [x] `test_a_transitive_is_not_recorded` (line ~53) inverts, with the reason: under Maven's
      answer `evo-inflector` IS recorded, which is the point.
- [x] Gate.

## Task 2 — the honesty count reaches the document · **DONE**

- [x] `Main.java`: write the header document whenever `--classpath-file` was given, carrying
      `type_headers_unlocated`; `TypeHeadersTest` pins "0 located is still a document".
- [x] `Document.type_headers_unlocated`, the `documents` view column, `coverage` reading
      `type_headers` and `type_headers_unlocated`, `ModuleFact.dependency_source` and
      `dependency_source_reason` written by `analyze`.
- [x] `document.py`: the one coverage line, present only when a header read ran. Goldens that
      have no header read are unchanged.
- [x] D00 §2 (document field) and §5 (`module` row) amended as built.
- [x] Gate.

## Task 3 — fixtures, priming, and the chain that crosses a transitive · **DONE**

- [x] `orders-advice/pom.xml` drops `spring-context`; `test_type_headers` pins that the
      `BindException` hop now comes through `spring-boot`'s transitive — the case OI-167
      named — and pins the coverage line's numbers.
- [x] `fixture_build.compile_and_stamp` runs the classpath goal beside `compile` (online in
      CI's priming, offline in the suite), so the plugin and every scope are in `~/.m2` and
      each fixture carries its file under the stamp.
- [x] Guards: Maven's file feeding `dependency_archives`; the fallback label when the file is
      absent; the coverage line. (Seven guards in all, every one shown to catch its break;
      the dependency-set guard's pin moved to `orders-advice`, a fixture the harness carries.)
- [x] Gate, guards.

## Task 4 — close-out, measured · **DONE**

- [x] Re-run spec §1 on the three modules through `analyze` itself (not the extractor
      alone), and on the other pinned corpora; record the table in the spec under §1.
- [x] Field pins re-run; any moved expectation re-recorded with its cause named.
- [x] `OI-167` closed; `dependencies.py`'s docstring, the Data REST boundary row and the
      `@ControllerAdvice` boundary text in COVERAGE updated to what is now true on Maven.
- [x] `M02`: the Maven mechanism as built, and the fallback rule (ruling b) stated.
- [x] CHANGELOG. Full gate, full guard sweep, all six field pins.
