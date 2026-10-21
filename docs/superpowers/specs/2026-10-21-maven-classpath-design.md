# The Maven classpath, asked of Maven — design

**Status: RULED 2026-10-21.** The user agreed to the recommendation and its three rulings
(§5) after the measurements in §1 and §2. This document records the design those rulings
fix; the plan beside it (`../plans/2026-10-21-maven-classpath.md`) sequences the work.

**Goal.** Close `OI-167`: on Maven, the `type_header` read (D00 §5; PR #57) sees only a
module's DIRECT declarations, and Spring Boot's starters are classless jars that put nearly
every type one hop out of reach. The mechanism is right and its yield on the field corpus is
near zero. `M02` already names the fix — *"Maven needs no such artifact —
`mvn dependency:build-classpath -o` … answer[s] directly"* — and the detector's own docstring
says *"classpath resolution via `mvn -o` lands when a fixture needs it"*. This is that.

---

## 1. What it closes, measured before it is built

Of the dependency types a module's own classes NAME, how many the header read finds in some
archive. The `direct` row is today's classpath (`dependency_versions`, jars present in
`~/.m2`); the `full` row is the file `mvn dependency:build-classpath` wrote for the same
module. Same extractor, same classes, nothing else changed.

| module | classpath | archives | headers read | named but in no archive |
|---|---|---|---|---|
| petclinic `genai` | direct | 24 | **9** | 80 |
| | Maven's | 290 | **94** | 29 |
| `spring-petclinic-rest` | direct | 25 | **13** | 186 |
| | Maven's | 150 | **197** | 61 |
| `yudao-module-system` | direct | 0 | **0** | 445 |
| | Maven's | 278 | **335** | 176 |

What remains "in no archive" on Maven's classpath is the JDK's own types — the walk stops
there on purpose (the catalog's declared roots are the JDK boundary) — plus, on
`yudao-module-system`, the reactor siblings Maven lists as `target/classes` DIRECTORIES
rather than jars (15 of its 293 entries; 80 of its unread owners sat in them). §3c says what
happens to those.

**Three other places state the same boundary and move with it** (verified, not assumed —
`verify-what-it-closes` rule): `resolve/dependencies.py`'s gate ("a framework that reaches
the classpath only as another artifact's own transitive … the answer is still *we could not
tell*"), COVERAGE's Data REST row *"a module whose build declares the framework only
TRANSITIVELY, on Maven"*, and the `module_dependencies` comment every version-scoped rule
reads. Gradle already answers all three from its resolved compile classpath (`gradle.py`:
"dependency coordinates come from the resolved compile classpath"); Maven will answer them
the same way, from the same file.

> **BUILT 2026-10-21 — measured through `analyze` itself, not the extractor alone:**
>
> | module | headers / in no archive | `dependency_source` | wall time, fresh |
> |---|---|---|---|
> | `genai` | **94 / 29** (was 9 / 80) | `maven`, 286 coordinates | 1.5s |
> | `spring-petclinic-rest` | **197 / 61** (was 13 / 186) | `maven`, 150 | 1.9s |
> | `yudao-module-system` | **335 / 176** (was 0 / 445) | `maven`, 278 | 7.8s (reactor `-pl … -am` with `compile`) |
> | `mall-admin` | 233 / 113 | `declared` — offline plugin refusal, `--allow-resolve` escapes | 6.5s |
> | `spring-petclinic-api-gateway` | 0 / 64 | `declared` — offline refusal on a test-scoped artifact `mvn compile` never fetched (§2, fact 1) | 2.4s |
>
> The three predictions held to the number (§1 was the extractor on the same files). The two
> fallbacks are §3c as ruled — labelled, with the reason, in the document. `orders-service`'s
> `spring-integration` catalog, skipped for a month on a framework that was on its classpath
> through `spring-cloud-stream`, runs; the Data REST boundary row and `dependencies.py`'s
> caveat now describe the fallback only.

## 2. The cost, measured

`mvn -o -q -B dependency:build-classpath -Dmdep.outputFile=target/sextant-classpath.txt
-Dmdep.includeScope=compile`, on this machine (`mvn -v` starts in 0.2s):

| invocation | first run | steady state |
|---|---|---|
| `genai`, from its own directory | 4.4s | **1.1s** |
| `spring-petclinic-rest`, from its own directory | 2.0s | **1.0s** |
| `ruoyi-vue-pro`, 46 modules, ONE invocation from the root with `compile` attached | 20.7s | **2.4s** |
| `ruoyi-vue-pro`, root, `-pl yudao-module-system -am` | — | **2.1–2.4s** |

The extractor's header read on the full classpath adds 0.2–0.7s per module. None of this is
a scale problem (§8.7), and §4 says why the suite pays it once rather than per test.

**Two facts about the goal that shape the mechanism:**

1. **It resolves EVERY scope before filtering.** `includeScope=compile` filters the output;
   the mojo's own resolution is `test`-scoped. So a machine that only ever ran `mvn compile`
   fails OFFLINE on the first attempt — all three corpora did, each on a test- or
   runtime-scoped artifact (`spring-boot-starter-test`, a `netty` native, the plugin itself).
   One online run per repository cures it.
2. **In a reactor, siblings resolve only with a lifecycle phase attached.** Run bare from
   the reactor root, the goal fails on the first sibling (`yudao-common … could not resolve`);
   `compile dependency:build-classpath` attaches `target/classes` as each sibling's artifact
   and succeeds. Run from a MODULE directory inside a reactor it fails whichever way (the
   module's import-POM is a reactor sibling not in `~/.m2`). Single-module repositories need
   no phase, and attaching one costs them ~2s of up-to-date checking.

The alternatives were measured out, not argued out: `mvn -o compile -X` prints no classpath
on an up-to-date build (checked: 4,332 debug lines, zero classpath entries), so there is
nothing to read off a finished build the way Gradle's init script leaves one; and resolving
POMs ourselves from `~/.m2` is the resolver `maven.py` already refuses to be ("nearest-wins,
scopes, exclusions, optionality, version ranges — a resolver, not a parse, and a wrong one
silently ADDS coordinates the classpath does not have"). A wrong archive here is a wrong
HIERARCHY fact, which `M06` calls fabrication.

## 3. The mechanism

### 3a. One invocation per reactor, from its root, offline first

`MavenDetector.detect(path)` learns the reactor root the way `_reactor_modules` already does —
up the `<parent>` chain, each `<relativePath>` accepted only when the POM there declares the
coordinates named (`OI-149`'s own walk). From that root:

```
mvn -o -q -B [compile] dependency:build-classpath
    -Dmdep.outputFile=target/sextant-classpath.txt
    -Dmdep.includeScope=compile
    [-pl <module, relative to the root> -am]
```

* `compile` is attached only when the root IS a reactor (declares `<modules>`); a single
  module needs none and pays none.
* `-pl … -am` limits a reactor run to the module being analysed and what it depends on,
  when `analyze` was handed one module; a reactor-wide `analyze` runs once for all.
* `-Dmdep.outputFile` is RELATIVE, so Maven writes one file per module under that module's
  own `target/`, which is the build's output directory and already ignored by every
  checkout's `.gitignore` that ignores `target/`.
* **Offline first; online once, and only under `--allow-resolve`** — exactly `M02`'s rule
  and `GradleDetector._invoke`'s shape. The offline refusal is recognised by Maven's own
  phrase ("in offline mode") the way Gradle's is.

### 3b. What the file feeds

Each line of the file is one entry on the compile classpath; a jar under the local
repository yields `group:artifact`, version and archive from its path (the layout
`_repository_layout` already spells), and nothing is guessed about one that is not.

| entry | feeds | replacing |
|---|---|---|
| a jar in `~/.m2` | `dependency_archives` — the header read's classpath | today's "declared, and the jar happens to be present" |
| the same jars | `dependency_coordinates` and `dependency_versions` — the TRANSITIVE closure, with the version Maven chose | the POM-declared-or-inherited set (F1) |
| a `…/target/classes` directory | the sibling library roots `_sibling_roots` walks for today | the declared-dependency walk over sibling POMs |

The second row is what moves `dependencies.py`, the Data REST row and every version-scoped
rule; it is how Gradle has always answered, so the two detectors finally say the same thing.
The third row needs no extractor change: a sibling's output is already SCANNED whole as a
library root (`W24`), which is more than a header, so the directory entries only replace how
that set is found — by Maven's answer rather than by walking POMs.

### 3c. When Maven does not answer — the user's ruling (b)

The POM parse stays, as the fallback it has been all along. When the goal fails offline and
`--allow-resolve` is not set, or fails online too, or `mvn` is not on `PATH`, or the module
has no `target/classes` (nothing was built, so there is nothing a classpath could be read
FOR): the module keeps today's declared-or-inherited set and its direct-declaration archives,
and **the reason is recorded**, on the module — `dependency_source: "declared"` with
`dependency_source_reason: <Maven's own last line, or the named precondition>` — and in the
document's coverage section. `M02`'s "a reported failure, never a partial model" is amended
for Maven to this: the declared set is not a partial model assembled by guessing, it is the
model this detector has always published, and it is LABELLED as the weaker one.

**Sextant never reaches the network on its own.** The flag is the only door, as it already is
for Gradle.

### 3d. Re-use, not re-run

`target/sextant-classpath.txt` is re-used when it is newer than every POM the detector read
for that module — its own, each ancestor it opened on disk, and the reactor root's. A POM
edit re-runs Maven; nothing else does. This is what keeps the suite from spawning `mvn`
hundreds of times (§4): CI's priming step produces the file once per fixture, under the same
stamp that already stops the suite re-compiling them.

### 3e. The honesty count travels

The extractor already reports `type_headers_unlocated` (added for §1's measurement). It
moves onto the header document's own payload, so it reaches the workspace through the fact
stream like every other count and the `coverage` query reads it beside `type_headers`; the
header document is written whenever a classpath was handed over, even with zero headers, so
"0 of 445" is SAID rather than being a missing file. The rendered document gains one line
under Coverage, present only when a header read ran:

```
- Dependency types the header read reached: 89 — header read for 9, found in no dependency archive 80 (dependencies: the build file's declared set — <Maven's reason>)
```

## 4. Performance (§8.7, decided here)

* Steady state per fresh repository: one `mvn` start (~1–2.4s measured) per `analyze`,
  amortised to ZERO on every later run by §3d while no POM changes.
* The suite: 28 test files call `analyze` and the detector unit file calls `detect` 64
  times. Without §3d that is minutes of JVM starts; with it, none — fixtures carry a primed
  file, and temporary POMs in unit tests have no `target/classes`, so the gate in §3c
  refuses before any process starts. The detector keeps Gradle's seam: the subprocess half
  and the "translate this file into a model" half are separate functions, and unit tests
  drive the second from a captured file.
* The header read itself: unchanged algorithm, more jars opened (278 vs 0 on yudao), 0.7s
  measured.

## 5. Decisions, as ruled 2026-10-21

| # | decision | ruling |
|---|---|---|
| a | `analyze` may run Maven, offline by default, online once under `--allow-resolve` | **agreed** — it is `M02`'s existing posture, and Gradle already does it |
| b | when Maven does not answer, keep the POM-declared set, label it, record the reason; never go online unflagged | **agreed** |
| c | sibling `target/classes` entries are read now, not logged | **agreed** — and they fold into the existing sibling scan (§3b), so no extractor work |

## 6. What this does NOT do

* No resolver of our own. If Maven cannot say, the answer is the declared set, labelled.
* No change to what a header IS (D00 §5 `type_header`): still superclass, interfaces,
  class-level annotations, never a member.
* No Gradle change: it already answers from its resolved classpath.
* No `help:effective-pom`; versions come from the archive paths Maven resolved.
* `mall-swarm`'s modules, `apollo`, and every other pinned corpus are re-measured after, not
  predicted here — the yield table in §1 is three modules, and §1's own warning applies: a
  prediction about "what it closes" is checked at the end, not assumed.
