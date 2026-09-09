# Java/Kotlin v1 completeness — specification

**Status:** draft for review
**Date:** 2026-09-06
**Input:** [`docs/java-gap-analysis-2026-09-06.md`](../../java-gap-analysis-2026-09-06.md)
(123 gaps, nine root causes) plus the 26 decisions agreed with the user on 2026-09-06.
**Output:** an implementation plan (step 3), then execution one item at a time (step 4).

---

## 0. What this document is

The gap analysis says what is wrong. This says what we build, in enough detail that a
sequenced plan can be derived from it without re-opening a decision.

Three rules govern everything below.

1. **Every G-number in the gap analysis appears exactly once in §11.** A gap that is not
   worth fixing is recorded as a stated boundary with a support level, never dropped.
   (GUIDELINES §8.4 — completeness is the deliverable.)
2. **Nothing here is a prediction.** Where a framework's behaviour decides the shape of a
   fix, this document either cites the measurement or names the measurement as work.
   (GUIDELINES §8.1 rule 5 — the provider has a way to tell them apart; go and find it.)
3. **Foundations before instances.** The gap analysis found nine root causes and 123
   symptoms. Work is organised by cause. Fixing G-12 without fixing RC-2 is how four
   javax/jakarta instances accumulated one at a time.

### What this is not

Not a plan. There is no ordering, no task decomposition and no estimate here; §10 states
the dependency edges a plan must respect, and nothing more.

---

## 1. Scope, ruled

These were decided with the user and are not reopened by this document.

| # | Question | Ruling |
|---|---|---|
| Q1 | Spring Boot 2 / Java EE in scope? | **Yes**, as a standing rule: every Jakarta EE API we touch carries **both** spellings. Blast radius is JMS and SOAP-client identity only — Spring's own annotations never moved packages. Each twin is measured, never assumed. |
| Q2 | Kotlin in v1, how deep? | **In scope at the "same bytecode" level.** Kotlin works wherever it compiles to the shapes Java does. Kotlin-specific constructs are stated boundaries. `suspend fun` contract shape stays unmeasured, **but the call edge must be recorded and verified**. |
| Q3 | Which unbuilt surfaces enter v1? | **The five asymmetries only** — the missing half of a surface we already claim. Everything else is a stated boundary. |
| Q4 | Must a catalog cover its whole framework? | **A stated slice is allowed**, declared in the catalog and in COVERAGE with what falls outside it. Presence stops meaning completeness. Cost: a per-catalog enumeration pass. |
| Q5 | Catalog grammar gains supertype/alternates vocabulary? | **`owner` accepts a list of alternates**, declared in the catalog, each carrying its own `measured:` provenance. Not "any supertype" — those owners live in jars we do not scan. |
| Q6 | How much of JVMS 4.7 does the extractor read? | **All of it.** The scanner is the foundation every tier stands on; a complete scanner means catalogs and engines grow later without re-touching it. |
| Q7 | How deep must a response contract go? | **Full generic substitution, across module boundaries** — reaching sibling modules in the same repo plus any declared `extract_libraries`. Never arbitrary third-party jars. |
| Q8a | FR-17 clause 3, the resolution distribution? | **Yes, in v1.** One `GROUP BY` on a column that already exists. It is the standing instrument for C3. |
| Q8b | How much query surface does v1 owe? | **An index bundle plus a handful of lookups over it**, not ten named queries — so a developer's agent finds blast radius, call patterns and remote hops without grepping a repo we already scanned. |

### 1.1 The standing COVERAGE requirement

> *"i want each and everything that we aren't going to deliver in v1 to be recorded in
> docs/COVERAGE.md … each item marked supported, partially supported or unsupported."*

Three levels: **supported · partially supported · unsupported**. The list must be
complete, not exemplary. This forces the §5 restructure in F6 — today §5 has one axis
(protocol), so a language construct, a shape, a configuration source, the question ledger,
the bundle and the rendered document have nowhere to be recorded at all.

### 1.2 One thing flagged, not open

**Spring Cloud Gateway (G-30) is out of v1 under Q3.** It is the largest single hole and the
commonest edge component, so it is flagged here rather than left to §13 alone. The ruling
stands unless the user changes it.

### 1.3 Step 0 — the precondition every wave depends on

**Ruled by the user 2026-09-07: `fact_schema_version` becomes a single monotonically
increasing integer, not semver, and it is set to `2` to begin with.**

**Why it exists.** The stamp is maintained by hand in four places and they hold two values:

| Copy | Value | Stamps |
|---|---|---|
| `domain/version.py:6` | **1.1.0** | `metadata.json`, and the comparison at `api.py:472` |
| `ingress/read/__init__.py:15` | **1.0.0** | WSDL/XSD, proto, Avro and GraphQL SDL shape documents |
| `application/stages/analyze.py:68` | **1.0.0** | module documents |
| `extractor-jvm/Main.java:181` | **1.0.0** (a string literal) | every class document |

The duplication is deliberate — `application` may not import `ingress` under the layering
contract — and `analyze.py:64` states the invariant in its own comment: *"They must stay equal
to that module's own copies — a document written with a different `fact_schema_version` than
its siblings would claim a schema nobody shipped."* **That invariant is violated today.** The
1.1.0 bump was for `DeclaredShapeFact` gaining `operation`; `DeclaredShapeFact` is produced by
`ingress/read/*`, and commit `d91f3b7` touched `domain/version.py` **only**. So the one
producer whose shape actually changed is the one copy that did not move, and a WSDL or proto
document on disk today carries the `operation` field while stamping `1.0.0`.

Nothing catches it: the staleness gate reads `metadata.json`, never the documents, and no test
asserts the four agree.

**What Step 0 does.**

1. `fact_schema_version` becomes **an integer**, set to **2**, and increases by one for every
   fact-shape change thereafter. No semver — the value is never parsed, ordered or compared
   for compatibility anywhere; `api.py:472` compares it for equality and that is all it has
   ever done, so three numbers were carrying one bit of meaning.
2. **The Java copy is removed.** The extractor takes the value as a command-line option the
   way it already takes its other version options, so Python owns the number and Java is
   handed it. Nothing in `extractor-jvm` can see a Python constant, which is why that copy
   drifted and why a test alone would not stop it happening again.
3. **A test asserts the remaining copies are equal**, and fails the moment they are not.
4. Existing workspaces stamped `"1.0.0"` or `"1.1.0"` mismatch, so the gate refuses them
   naming the stamp and asks for a re-analysis. That is the designed behaviour, not a
   migration, and nothing is rewritten in place.

**It lands before Wave 1, not inside it.** Wave 1 makes the largest fact-shape change the
project has had, and bumping a stamp that is already inconsistent means the bump cannot be
verified — a correct new value would be indistinguishable from a fourth wrong one.

**Two sub-decisions this raised, both since RULED by the user (2026-09-07, during Wave 0).**

- **JSON number, not a numeric string.** `facts.py:83` typed the field `str` and `Main.java`
  wrote it through `JsonOut.string`. A value that must always parse as an integer but is
  typed as text is the weaker of the two, and nothing orders it. Changed: the dataclass field
  is `int`, the Java writer emits it through `String.valueOf` after parsing (so a
  non-integer is a failed request rather than an unparseable fact file), and the 65 test
  fixtures holding `"1.0.0"` hold `2`.
- **`graph_schema_version` becomes an integer too, also `2`.** *"I think graph schema should
  be integer as well, not semver."* It has the same three properties the fact stamp had —
  never parsed, never ordered, compared for equality at `api.py:470` and nowhere else — so
  the argument for the fact stamp was the argument for this one, and the spec's original
  "the ruling named the fact schema only" was drawing a line the reasoning did not support.
  Both start at `2`: the second generation, after the semver one.
- **`sextant_version` keeps semver, and stops being a copy.** It is the tool's own release
  and moves on its own cadence — `D01` §7 makes a `fact_schema_version` change force
  re-extraction, while a `sextant_version` change need not — so collapsing the two would
  re-scan the estate on every release. But the literal `"0.1.0"` in `domain/version.py`
  duplicated `pyproject.toml:7`, which is the same defect class Step 0 exists to kill. It is
  now read from the installed distribution, so `pyproject.toml` owns it outright.

**AMENDMENT, ruled during Wave 0: step 3 above is replaced. There are no remaining Python
copies to test for equality.** The spec assumed the two restatements had to stay and asked
for an equality test; that assumption was wrong. The import-linter contract
(`pyproject.toml:147`) puts `domain` at the bottom with `ingress` and `application` both
above it, and `egress/render/metadata.py:12` already imports the constants directly. Only
`application` importing `ingress` was ever forbidden — which is all `analyze.py:64`'s comment
claimed. So both restatements import `sextant.domain.version` instead, and the drift becomes
STRUCTURALLY IMPOSSIBLE rather than merely detected — the same reasoning that chose C over B
for the Java copy: *"B fixes detection and leaves the cause."* Applying it to the Java copy
and not to the two Python copies beside it was an inconsistency in the original ruling.

### 1.4 What "done" means — the field corpus

**Ruled by the user 2026-09-07: the plan is proved on at least a dozen real open-source
projects, not on tests.** *"You've been building shit with perfectly fine test cases."* The
measurement in this analysis proves the point: 2,346 tests, 82 guards at 0 survived,
byte-stable, contracts clean — and the suite notices **neither** of the two hardest Criticals,
because `orders-service` and `mall-admin` both score 0 on the superclass-call shape while
`spring-petclinic-rest` scores 96. *Measured at W21: **131** — see §4.2; the 96 dropped
every subclass that declares no method of its own. The 0s hold.*

**The machinery already exists and needs nothing new.** `scripts/field_check.py` validates
Sextant's output against real upstream repositories at pinned commits, handling per-repo build
quirks — module path, Maven launcher, and the required JDK (`macrozheng/mall` dies in Lombok
on anything newer than 21). It is opt-in and outside the suite, which is how it satisfies the
no-network-in-tests rule.

**What it holds today, and both facts are damning.**

| pin | inbound | outbound |
|---|---|---|
| `jhipster-sample-app` | `http: 38` | **`{}`** |
| `mall-admin` | `http: 160` | **`{}`** |
| `spring-petclinic-rest` | `http: 44` | **`{}`** |

`verify: python3 -c "import json,glob;[print(f, json.load(open(f))['endpoints']) for f in sorted(glob.glob('scripts/field-expectations/*.json'))]"`

1. **Three projects, all inbound-only HTTP CRUD, and zero outbound rows between them.** Every
   messaging and RPC catalog we ship — Kafka, RabbitMQ, SQS, Pub/Sub, JMS, gRPC, GraphQL,
   SOAP, WebSocket, STOMP, RSocket, Pulsar — is exercised by **no real project at all**. That
   is a larger corpus hole than the superclass one, and it has been visible in these files the
   whole time.
2. **Two of the three pins are stale across a change that alters what they record.**
   `spring-petclinic-rest` and `jhipster-sample-app` were recorded 2026-09-03 06:17; the
   canonical-address gate — which exists to normalise a leading separator, *"an address that
   omits its leading separator names the same thing as one that spells it"* — landed
   2026-09-03 22:06. The petclinic pin still records 25 of 44 routes with no leading slash
   (`GET api/pets` beside `GET /api/owners/{ownerId}`) and 8 bare `/` routes, one per HTTP
   verb. So either the check has not been run since, or it failed and nothing happened.
   `verify: git log -1 --format=%ci -- scripts/field-expectations/spring-petclinic-rest.json; git log -1 --format=%ci -S'THE CANONICAL-ADDRESS GATE' -- src/sextant/storage/duckdb/derive_endpoints.sql`

**MEASURED 2026-09-07, running Wave 0's W0b. The baseline is now green, and two of the four
claims above needed correcting.**

`verify: JAVA_HOME=/opt/homebrew/opt/openjdk@21 PATH=/opt/homebrew/opt/openjdk@21/bin:$PATH python3 scripts/field_check.py`

1. **`spring-petclinic-rest` was stale, exactly as predicted, and it was ONLY staleness.**
   25 of its 44 recorded routes had no leading slash. Current output spells all 44 with one,
   and the two sets are **identical once the leading separator is normalised** — no route
   gained, none lost, the count unchanged at 44. So the canonical-address gate had done its
   job and the pin had frozen the behaviour from before it. Re-recorded deliberately.
2. **`jhipster-sample-app` was NOT stale**, though it was recorded in the same minute. Its
   controllers already spell `@RequestMapping("/api/...")` with the separator, so the gate
   changed nothing for it. The claim above — *"two of the three pins are stale across a
   change that alters what they record"* — was true about recording TIME and false about
   effect; only one pin actually differed. Corrected here rather than left standing.
3. **The 8 bare `/` routes are correct, not a defect.** `RootRestControllerV1` carries
   `@RequestMapping(value = "/")` with **no `method` attribute**, which Spring matches
   against every verb; `spring-mvc.yml:34`'s `all_methods` is Spring's own `RequestMethod`
   enum, all eight values. One row per verb mirrors the framework (§8.1 rule 5) rather than
   inventing a ninth meaning for "any".
4. **`mall-admin` needs `JAVA_HOME` on a JDK 21**, or its own `jdk` check refuses before the
   build — which is the check working, not a failure. The invocation is in the verify line
   above and in `RUNBOOK.md`; it was undiscoverable before, and "run the field check" gave a
   refusal with no way to act on it.

So the honest baseline is **three of three green**, and every later pin is now recorded
against known-good behaviour rather than against whatever happened to be there.

**The requirement.**

- **At least twelve projects, selected by what they exercise** — one per protocol we ship a
  catalog for, plus Spring Boot 2, plus Kotlin, plus a genuine multi-module build. A surface
  with no findable open-source example becomes a **stated boundary**, never a silent zero.
- **Selection happens when the work is done**, not now. Naming repositories from memory is
  how the six corrected claims in this document got written.
- **It runs after every wave, not only at the end.** Petclinic is the argument: it scores 96
  on a shape our other corpora score 0 on, and that was learned by looking. *W21 re-measured
  it at **131**, and the point survives its own correction: the number was learned by
  looking, and looking more carefully moved it 27%.* Discovering twelve
  projects' worth of defects after 54 items is the same mistake at a larger scale.
- **A pin freezes behaviour, so a defect visible in a pin is fixed before the pin is
  refreshed.** Recording twelve projects against current output would make twelve projects'
  worth of it permanent — which is exactly what the petclinic pin did.

---

## 2. F1 — the extractor reads the class file as a specified format

**Root cause:** RC-6 — the class file is read as an opinion about the code, not as a format
with a specification. **Closes:** C1, C6, Q6, G-52…G-57, G-60, G-62, and the producers four
other foundations wait on.

Everything else in this spec stands on the fact stream. F1 is first because six later items
consume facts F1 produces, and because `✅ ASM` in COVERAGE is currently a claim about a
scanner that reads 4 of 30 attributes fully.

### 2.1 The version ceiling (C1)

Measured: ASM 9.7 accepts class-file majors 45–67 and **refuses 68+** — JDK 24, 25 and 26.
ASM 9.10.1 was verified reading majors 52, 61, 65, 68, 69 and 70 from real jars.

- **The bump is already done** — `build.gradle.kts:28-34` pins 9.10.1, landed in commit
  `0674bfd` as the one approved exception to the standing no-version-bumps-before-2J rule.
  It is named here only so the record is complete; it is not remaining work.
- **Pin the supported range as a test**, so the ceiling is a value a test asserts rather
  than a number that drifts.
- **Record the observed major per document.** This is a **new** capability — `_CAPABILITIES`
  in `ingress/extract/jvm/scanner.py:8` holds fourteen entries ending at 9.18
  (`method_returns`), so 9.19 is the next number to **allocate**, not one we already have.
  `verify: python3 -c "import re;s=open('src/sextant/ingress/extract/jvm/scanner.py').read();b=re.search(r'_CAPABILITIES = \{(.*?)\n\}',s,re.S).group(1);print(len(re.findall(r'^\s+\"',b,re.M)),'capabilities; highest',max(re.findall(r'9\.\d+',b)))"`
  It gains three consumers in this spec: the ceiling test above, the multi-release target
  fallback in §2.4, and Kotlin/language labelling in F8.

**What actually remains is the half that lasts, and none of it exists.** `Main.java:83` still
wraps the entire scan loop in `catch (Exception failure)` and exits 1, so one unreadable class
still takes the whole scan with it. An unreadable class becomes **skipped, not fatal**, with
its reason reaching both the manifest and the document. `partial` / `partial_reason`
(`Main.java:205-206`) are the literal strings `"false"` and `"null"` with no code path able to
set either; they become real.

**And `scanner_version` stops lying** (folded here on the user's ruling). `Main.java:182-183`
writes `scanner_id: "asm"`, `scanner_version: "9.18"`. ASM 9.18 does not exist — the pinned
library is 9.10.1 — because commit `2cda8a2` set the field to 9.18 when *capability* 9.18
(`method_returns`) landed. A third value, `"9.7"`, sits in `tests/egress/test_manifest.py:14`.
Every fact document therefore names a scanner version that is neither the library in use nor
anything a reader can resolve, and it looks exactly like a library version, which is why it
went unnoticed. This is provenance: a consumer deciding whether to trust a bundle reads it.

*Honest note:* the bump alone would have hidden the second half. A newer ASM raises the
ceiling; it does not make a refusal visible. Both halves ship together or the next ceiling
is silent again.

### 2.2 Parameter annotations (C6)

`Runtime[In]VisibleParameterAnnotations` is read **wrongly**, not partially. JVMS 4.7.18
allows the annotation table to be shorter than the descriptor's parameter list, because
javac omits synthesised leading parameters — the outer instance on an inner class, and
`$enum$name` / `$enum$ordinal` on an enum. We never override
`visitAnnotableParameterCount` and index from zero, so annotations land on the wrong
parameter.

- Override `visitAnnotableParameterCount`; align entries **from the end**.
- The test must use an **enum** constructor, not only an inner class: there the first hidden
  parameter is also a `String`, so the misalignment cannot be detected downstream by type.

Scope stated so it is not oversold: this needs a constructor that is both annotated *and* on
an inner class or enum. Real-world hit rate is low. It is a genuine fabrication with a small
blast radius.

### 2.3 The rest of JVMS 4.7 (Q6 = A)

Current state: **4 of 30 attributes read fully · 7 partial · 1 deliberately ignored with a
stated reason (`StackMapTable`, correct) · 18 silently dropped.** Plus 11 access flags.

**Eighteen silently dropped:** `ConstantValue` · `NestHost` · `NestMembers` ·
`PermittedSubclasses` · `Exceptions` · `InnerClasses` · `EnclosingMethod` · `Record` ·
`SourceFile` · `LineNumberTable` · `LocalVariableTable` · `LocalVariableTypeTable` ·
`SourceDebugExtension` · `Deprecated` · `AnnotationDefault` · `Module` · `ModulePackages` ·
`ModuleMainClass`. Plus unknown and vendor attributes via `visitAttribute`.

**Partial and load-bearing:**

- **Kotlin function metadata is unread, and it costs two things.**
  `KotlinNullability.propertyNullability` reads only
  `classMetadata.getKmClass().getProperties()` — it never touches `getFunctions()`.
  `verify: grep -n 'getProperties\|getFunctions' extractor-jvm/src/main/java/dev/sextant/extractor/KotlinNullability.java`
  Reading functions as well closes **G-63** (nullability applied to fields only, so `getId()`
  reports `nullable: true, nullable_resolution: "resolved"` beside an `@NotNull` in the same
  fact) **and** Q2's `suspend fun` obligation: a suspend function's declared return is erased
  to `Object` in the descriptor, and `KmFunction.getReturnType()` is where the real one is
  written down. Put it back and a `suspend fun` is an ordinary function with one extra
  parameter — the trailing `Continuation` is symmetric, appearing identically in the
  declaration and at every call site, so descriptor matching and resolution never see it.
  **Still a verification, not an assumption** (Q2's own wording): a `suspend fun` with a real
  suspension point has its body moved into a generated `invokeSuspend`, so the calls it makes
  may be attributed to the synthetic rather than to the function — the same orphaning
  capability 9.17 fixed for lambdas. That half is measured in F3, not assumed here.
- **`Signature` is the largest single hole.** Read for field types, method *return* types,
  generic superclass and superinterfaces. **Not** read for method or constructor *parameter*
  types, nor for class and method formal type parameters and their bounds. F4 cannot do
  generic substitution without the missing half.
- `Code` misses `ATHROW` and `PUTSTATIC` in `<clinit>`.
- `BootstrapMethods` misses `StringConcatFactory`'s recipe — half a composed address (RC-7).
- Class-level type annotations (`CLASS_EXTENDS`, `CLASS_IMPLEMENTS`, `TYPE_PARAMETER`) dropped.

**Eleven access flags dropped:** `ACC_ABSTRACT` (so an interface's `default` and `abstract`
methods emit identical modifiers) · `ACC_FINAL` · `ACC_VARARGS` (named at
`MethodFlow.java:578` as the reason capability 9.15 cannot tell a varargs call from
`new String[]{…}`) · `ACC_SYNCHRONIZED` · `ACC_NATIVE` · `ACC_VOLATILE` · `ACC_STRICT` ·
`ACC_ANNOTATION` (so an `@interface` emits `construct_kind: "interface"`).

**`ACC_ANNOTATION` is not a free addition, and this is the one place F1 changes derived
output.** `construct_kind` is a **declared closed set** — `D00-fact-schema.md:168` lists
fourteen values and **none of them is `annotation`** — and the derivation reads the field:
`derive_endpoints.sql:1076` joins on `construct_kind IN ('method','function')` and `:1099`
filters catalogs on `$declared_on`. So reading the flag has exactly two paths, and there is no
third: emit a value outside the set, which fails NFR-5's test; or **add `annotation` to
D00 §4**, which is a fact-schema change and therefore another increment under Step 0's rule.
**Ruled: add it.** Q6 commits us to reading all of 4.7, and reading a flag then discarding its
meaning is the *"declared, never read"* defect §2.3's ledger exists to catch; and §8.1 rule 5
says that where the provider distinguishes two things — here, with a flag — we follow it
rather than flattening them.
Blast radius, measured: three catalogs use `declared_on: interface` — `retrofit.yml`,
`spring-http-interface.yml`, `jakarta-jws-client.yml` — and all three match ordinary service
interfaces, never annotation types. No shipped catalog changes behaviour.
`verify: grep -rh 'declared_on:' src/sextant/catalogs/*.yml | sort | uniq -c`

**`module-info.class` is the other one** (G-61): it currently emits a fabricated `class`
symbol. `module` is **already** in D00's set, so that fix needs no schema change — but it
removes a symbol from the graph, which is a derived-output change too.

**Four already force an invented rule downstream**, which is why they are not merely absences:

| Unread | The invention it forces |
|---|---|
| `AnnotationDefault` | catalogs hardcode framework defaults — a prediction §8.1 forbids |
| `InnerClasses` / `EnclosingMethod` | downstream splits class names on `$` |
| `StringConcatFactory` recipe | a composed address published with half its components |
| `ConstantValue` | the `constant` resolution has no producer at all |

**Risk, stated:** reading all of 4.7 emits facts nothing consumes yet. The mitigation is a
distinction the codebase must be able to express: **"read, no consumer yet"** — a fact
available to a future tier, legitimate under Q6's own rationale — versus **"declared, never
read"**, which is the defect. The second is a test failure; the first is not.

### 2.4 Multi-release jars (Fork 4, G-62)

`JarSource.names()` is `filter(name -> name.endsWith(".class"))` and nothing else. Every
copy of an overlaid class is scanned; `document_id = sha256(classRelative)` gives the copies
**different ids** while they mint the **same** type symbol; no table downstream has a
uniqueness constraint, so they become duplicate rows. `sourcePathOf` also yields
`META-INF/versions/21/…/VirtualThreadDelegate.java` — a source file that cannot exist.

Measured across 2,402 jars in the local Maven and Gradle caches:

| | |
|---|---|
| multi-release jars | 351 (300 carry one release, 51 carry two to six) |
| overlaid names that also have a base copy — true duplicates | 10,308 |
| overlaid names with **no** base copy | 626, across 314 jars |
| jars with `META-INF/versions/` entries and **no** `Multi-Release: true` | 6 |

`spring-core-7.0.2.jar`: base `VirtualThreadDelegate` (major 61) throws
`UnsupportedOperationException` from every method — *"Virtual threads not supported on JDK
<21"* — while the `versions/21` copy (major 65) holds a `Thread$Builder` and the real
implementation. Eight of its ten overlaid names have no base copy and are major 68.

**The rules, in order.**

1. **The manifest attribute gates everything, and it is read once when `JarSource` opens the
   zip.** Absent or not true → `names()` returns **only** entries not under
   `META-INF/versions/`; the overlays are not scanned at all. Not "treat them as ordinary
   classes": without the attribute the JVM never searches `versions/`, so those classes sit
   at a path no loader will look in and are unreachable.
   `testcontainers-2.0.5.jar` is the case that proves it — 1,198 entries under
   `META-INF/versions/` (shaded snakeyaml and jackson paths copied in by the shade plugin)
   under a manifest carrying only `Manifest-Version` and `Implementation-Version`. Today we
   scan all 1,198 and collide their symbols with the reachable base copies. This one check
   removes 1,198 phantom documents from a single jar.
   *Implementation:* the jar specification makes the attribute name case-insensitive, and
   manifest values fold at 72 bytes with a leading-space continuation — so this is a parsed
   attribute lookup, never a `grep`. No manifest at all takes the same branch as absent.
2. **Tag, do not drop.** Every document gains `class_release` — `base`, or the integer N.
3. **Select by the JVM's own rule (JEP 238), among copies of the same name:** highest
   `N ≤ target`, else base. A name with exactly one candidate is **always** emitted with its
   tag — there is nothing to select between. Fallback-to-root must not be implemented as
   "base copies only": that silently deletes the 626 versioned-only classes and asserts they
   do not load, which is a stronger claim than keeping them labelled.
4. **The target comes from code, never from a default.** In order: the build's declared
   release (`maven.compiler.release`, `maven.compiler.target`, `maven.compiler.source`,
   `java.version`, maven-compiler-plugin's `<configuration><release>`; on Gradle,
   `targetCompatibility` / `release`) — a value in the pom or build script, so GUIDELINES
   §8.2 admits it; then the module's own class-file major (§2.1); then base, with an
   `open_question` naming every class where base and an overlay actually disagree.

   **Reading it is a capability we do not have, and it is now its own work item.** Nothing
   in the codebase reads any of those keys —
   `verify: grep -rn "maven.compiler\|targetCompatibility\|sourceCompatibility" src/`
   returns nothing. Both halves use machinery that exists:
   `MavenDetector._inherited_model` (`maven.py:576-602`) already merges `<properties>` across
   parent inheritance, so the Maven value is in a dict we build and never read; and the Gradle
   detector already runs Gradle with an init script and reads JSON back, so Gradle itself can
   be asked rather than its build file parsed. A module whose build declares none reports
   absence, never a guess.
5. **Fix `sourcePathOf`** to strip the `META-INF/versions/N/` prefix before deriving the
   source path.

**Placement:** the extractor **tags**; the **filter** runs downstream at resolve. The target
release is a property of the module doing the depending, not of the jar — one `jackson-core`
scan can serve two modules declaring different releases, and deciding in the extractor would
force a re-scan per consumer and put a config-derived judgement inside the fact layer, which
records and never decides.

**Caution, and it decides the sequencing:** the tag alone changes nothing. With no uniqueness
constraint anywhere, the duplicates merely become labelled duplicates. The filter must be real
wherever the type and method tables are built, or the bug has only been renamed — **so the
filter is built beside the tag, not later.** *Where* it runs (at resolve) and *when* it is
built are unrelated questions; an earlier draft of the plan conflated them and parked the
filter six waves away behind a dependency on the export work that does not exist.

**Scope:** every one of the 351 measured jars is a library, so this lives entirely on the
dependency tier and cannot perturb `module_output` byte-stability. **Unmeasured:** whether
Spring Boot's repackage sets the attribute on a fat jar. Probe when a fat-jar scan is on the
table.

### 2.5 Acceptance for F1

- A test pins the accepted class-file major range; a class outside it is skipped with its
  reason in the manifest, the document, and `partial_reason`.
- An enum constructor with an annotated parameter resolves to the right parameter.
- Every attribute in JVMS 4.7 is either read, or listed in a single enumerated
  `deliberately-not-read` set with a stated reason. No third category exists.
- Every access flag is either emitted or in that same set.
- Scanning `testcontainers-2.0.5.jar` emits no document from `META-INF/versions/`.
- Scanning `spring-core-7.0.2.jar` emits exactly one document per class name, each carrying
  `class_release`, and the eight versioned-only classes are present.

---

## 3. F2 — a catalog may spell a type exactly once

**Root cause:** RC-2, **21 sites of one shape**. **Closes:** C4, C5, C7, C9, Q1, Q5, Fork 1,
G-51, G-21, G-89. (*G-38 was listed here and is not closed by this section: W17 measured it
and it was not an RC-2 site — `spring-mvc.yml` spelled a LIST of coordinates already, and
nothing read it. §3.7 records what W17 did change.*)

This is the single highest-leverage change in the spec. Twenty-one catalog keys accept one
string where the world offers several, and every javax/jakarta miss, every
interface-typed-owner miss and every renamed-coordinate miss is the same missing word.

### 3.1 The vocabulary

The 21 scalar sites: `matches.owner` · `matches.root.owner` · `matches.type_annotation` ·
`mapping.prefix_annotation` · `reply.annotation` · `matches.interface` ·
`registration.owner` · `field_annotation` · `identity_marker` · `annotation` · `container` ·
`handler_annotation` · `status_annotation` · `supertype_marker` · `matches.supertype` ·
`no_repository_bean` · `resource_annotation` · `member_annotation` · `when.implements` ·
`rule.annotation` · `media_values.owner`.

The asymmetry that proves this is accident rather than design: `error_advice`'s advice and
controller **lists are plural** while its two annotation keys are scalar.

**Each of the 21 accepts either a scalar or a list.** A scalar stays valid — this is not a
migration. Each alternate carries its own `measured:` provenance: the coordinate and version
it was read from, or it is a prediction with a longer list (§8.1).

**What this is not.** A list of alternates means *"the same library, held by its interface or
under its old package"*. It does **not** replace the javax/jakarta twin catalogs (§3.3):
those are different jars, at different versions, needing separate measurements.

### 3.2 The owner problem (Q5, G-51, G-89)

`matches.owner` is one string compared with `==`, so:

```java
JmsOperations jms = ...;
jms.convertAndSend("orders", payload);   // matches nothing
```

Spring Boot autowires by interface at least as often as by class, and
`SqsTemplate.newSyncTemplate()` **returns** `SqsOperations`, so the idiomatic construction
misses entirely. Same for `AmqpTemplate`, `KafkaOperations`, `RestOperations` and Kafka's
`Consumer<K,V>`.

Rejected: *"or any supertype, resolved from the hierarchy"* — every one of these owners lives
in a dependency jar we do not scan, so the hierarchy is not in the facts. It works for the
in-module minority and fails on the actual population.

### 3.3 The javax/jakarta standing rule (C7, C9, Q1)

**Every Jakarta EE API we touch carries both spellings**, as a rule rather than as three
files. Measured state at decision time — already half-done by accident:

| | |
|---|---|
| both spellings ✓ | `jakarta-jws`, `jakarta-jws-client`, `jakarta-servlet` + `javax-servlet`, `jakarta-websocket` (javax detection-only), `microprofile-graphql` |
| jakarta only ✗ | `jakarta-jms`, `spring-jms`, `spring-ws-template` |

- Add `javax-jms.yml` beside `jakarta-jms.yml`, following the established `javax-servlet.yml`
  pattern.
- **Run a mechanical sweep across every catalog:** for each `jakarta.*` type named, does a
  `javax.*` counterpart exist, and is it handled? Fixing instances one at a time is how four
  accumulated.
- The sweep must **classify two distinct failure modes separately**:
  - *renamed, nothing published* — JMS. Silence, which at least reads as absence.
  - *renamed, partial data published* — the javax JAXB spelling (G-14): a SOAP endpoint that
    exists **with no operation name**, so a reader concludes we could not resolve it when we
    never looked in that spelling. Worse than silence.
- COVERAGE's prose asserts *"Both must be matched"* in the indicative. **That sentence is
  false** and is the reason nobody looked. It is corrected in F8 whichever way the sweep goes.

### 3.4 Cardinality and the protocol default (C4, Spring Cloud Stream)

Two changes, and the second is the one that leaves our bundle.

1. **Mirror the measured binding rule:** exactly one candidate binds; two or more bind
   **nothing**. This needs a cardinality conjunct the grammar does not have — the same
   vocabulary family as §3.1.
2. **Remove the protocol default entirely.** An unmapped binder yields **no row plus an open
   question**. Protocol is identity, and DR-5 gates linking on protocol equality, so a
   defaulted protocol is the one defect in this whole analysis that corrupts *another
   consumer's* data.

Rejected: treating a measured rule as unmeasurable; and both variants that knowingly leave a
fabrication standing.

**Close the ratchet hole in the same change:** the defaulted-value rule watches engines, and
this default lives in **catalog data**.

### 3.5 Class-level plus method-level listeners (C5)

A class-level `@KafkaListener(topics="orders")` and a method-level
`@KafkaListener(topics="payments")` are two **independent registrations**. We glue them into
one row addressing `"orderspayments"` — a destination that does not exist.

- The catalog **declares which relationship it has**: **PREFIX** (HTTP, where composition is
  real and a separator exists) or **SIBLING REGISTRATION** (messaging, where it is not).
  One new conjunct.
- This fixes the category, not the instance: the engine currently assumes every class-level
  annotation prefixes its methods, which is wrong for a whole protocol family, and the next
  messaging catalog would inherit it by default.

Rejected: inserting a separator (`orders.payments` addresses nothing either); and dropping
the row (trades a fabrication for a silent loss of two readable topics).

**Attached, and both are required:**

- **MEASURE per framework before encoding** — whether Kafka, Rabbit and SQS each register
  class- and method-level listeners independently, and `@KafkaHandler` / `@RabbitHandler`
  (the documented class-level pattern) **separately**, because it behaves differently from a
  second `@KafkaListener`.
- **Fix the gate.** The addresses-nothing guard fires only on an **empty** path, so a
  composed address that is merely *wrong* sails through. It must catch both. This is RC-7's
  general form and it also guards `StringConcatFactory` addresses from §2.3.

### 3.6 RSocket versus STOMP (Fork 1, G-16)

Measured on spring-messaging 7.0.2: `SimpAnnotationMethodMessageHandler.isHandler` is
`hasAnnotation(beanType, Controller.class)`, and RSocket's chain sets an equivalent
predicate. **Spring does not distinguish them on the class at all.**

The discriminator is **which handler bean auto-configuration registered** — a dependency
fact — plus `@ConnectMapping` as an RSocket-only positive marker.

- RSocket starter present → RSocket row. WebSocket/STOMP present → STOMP row.
- **Both present → two rows.** Both handlers scan the same beans; the method really does
  serve both. This is a correct answer, not an ambiguity.
- `@ConnectMapping` anywhere is positive RSocket evidence regardless of the build.
- Neither resolvable (parent-POM inheritance, a stated refusal that survives F1) →
  **open question, not a guess**.

### 3.7 WebFlux `@Controller` (Q4 amendment, G-38)

**Measured, and the bug is not there** (`scripts/probes/w17_webflux_controller.md`). This
section said `spring-mvc` *is gated on* the `spring-webmvc` coordinate, so a WebFlux
`@Controller` derives nothing. It is not gated on anything: `detect.coordinates` is read by
the two styles in `resolve/dependencies.py`'s `DEPENDENCY_GATED` and by any catalog setting
`detect.required`, and `spring-mvc` is `annotation_driven` and sets neither. Compiled against
the real jars and run through the real scanner and the real derivation, all four shapes G-38
names — `@Controller` + `@GetMapping`, `+ @ResponseBody`, returning `Mono<String>`, and
`@RestController` — derive the same rows in a `spring-webflux`-only build as in a
`spring-webmvc`-only one.

**Where the prediction came from is the reusable part.** G-38 was written by reading a
`detect.coordinates` line and reasoning about what a gate keyed on it would do, without
asking whether a consumer reads it. GUIDELINES §8.1 — measure, never predict — and the mirror
of §2: a capability with no consumer is half-shipped, and a *declared gate* with no consumer
misleads its own readers into predicting behaviour the code does not have.

**The widened-coordinates branch shipped anyway, for a different reason.** The list named one
stack while both serve `@Controller` — the two `RequestMappingHandlerMapping.isHandler`
implementations are four identical instructions at 6.1.6 and 7.0.2 in each artifact — so the
sentence was false whether or not anything read it. §3.6 shipped `detect.required`, which is
one line an author can add to have their coordinate list honoured; adding it to this file
would have made G-38's prediction true for the first time. The list now names both, pinned
by `test_the_shipped_coordinate_list_names_both_web_stacks` (the list's content, asserted
offline) and by `test_narrowing_the_list_and_gating_on_it_is_what_would_lose_the_webflux_rows`
(the pair of changes that would lose the rows — narrowing ALONE changes nothing, because
nothing reads this catalog's list).

A second WebFlux catalog was the other branch offered and is refused, on the mechanism the
SQL actually has rather than the one first written here. `derive_endpoints.sql`'s insert ends
`AND NOT EXISTS (… protocol = … AND direction = … AND method IS NOT DISTINCT FROM … AND
path = …)`, and `catalog_id` is not in that key — so a twin catalog claiming the same
`@Controller` + `@GetMapping` evidence on the same `http` protocol derives **no duplicate and
no extra row at all**: it is silent dead weight, and the only thing it changes is which id
gets the attribution, through `endpoints.py`'s filename tiebreak. (*This paragraph said the
twin "would derive a duplicate row", citing §3.6. It would not, and §3.6 does not transfer:
`spring-stomp` and `spring-rsocket` produce two rows because their PROTOCOLS differ, so that
dedup key never applied to them.*)

### 3.8 Stated slices (Q4)

Six catalogs ship a declared slice, stated in the catalog and in COVERAGE with what falls
outside it: G-44 (four template catalogs, send half only) · G-37 (the `route()` builder DSL) ·
G-43 (`SqsAsyncClient`, batch, and the entire inbound direction) · G-45 (Data REST, JPA only) ·
G-47 (2 of ~12 channel annotations) · G-41 (`@DgsData` is `@Inherited`).

**The cost is real and is part of this work:** you cannot write a slice without enumerating
the framework's surface. That is the jar-listing technique that found `@PulsarReader`. Q4
implies a per-catalog enumeration pass, and Fork 2 is what it looks like when it is done.

### 3.9 Pub/Sub, and the general rule for "is this boundary real" (Fork 2, G-23)

Measured on `spring-cloud-gcp-pubsub 5.1.2`: `PubSubTemplate` declares **ten** inbound
methods — `subscribe`, `subscribeAndConvert`, `pull`, `pullAsync`, `pullAndConvert`,
`pullAndConvertAsync`, `pullAndAck`, `pullAndAckAsync`, `pullNext`, `pullNextAsync` — and the
catalog reads **one**. All take the subscription name at argument 0, the shape already read.
Nine methods, one file, no engine change. Pull-based consumers derive nothing today.

The unread `.startAsync()` conjunct is replaced by **GUIDELINES §8.6**: a boundary is real
when a chain of evidence reaches the point where it provably happens, and every link is
either a traced call or a **measured** framework rule.

- `pull*` **is** the consumption — the chain ends at the call itself.
- A built `Subscriber` is real only if a trace reaches `startAsync`.
- A `@Bean` returning a `Subscriber` is real via the measured rule that Spring starts it —
  a traced chain whose last link is a framework rule, not an exception to the rule.

### 3.10 Acceptance for F2

- All 21 sites accept a list; a scalar still validates; every alternate carries `measured:`.
- `JmsOperations`-typed and `SqsOperations`-typed sends derive rows.
- The javax/jakarta sweep produces a table of every Jakarta type we name, its javax
  counterpart, whether it is handled, and which failure mode applies where it is not.
- An unmapped Spring Cloud Stream binder produces zero rows and one open question.
- A class-level plus method-level Kafka listener derives **two** rows.
- A method annotated for both RSocket and STOMP in a build carrying both starters derives
  **two** rows.
- A WebFlux `@Controller` derives its endpoints.
- Each of the six sliced catalogs declares its slice, and COVERAGE states what is outside it.
- All ten `PubSubTemplate` inbound methods derive rows.

---

## 4. F3 — method identity and method resolution

**Root cause:** RC-3. **Closes:** C3, C8, G-1, G-48, and the 27 rows already corrected off
arity. **Depends on:** F1 (`Signature` parameter types, `ACC_ABSTRACT`, `ACC_VARARGS`).

### 4.1 Identity is name plus parameter types (C8)

JLS 8.4.2 identifies a method by its name and parameter types. The return type is in the JVM
descriptor and is **not** part of method identity.

The descriptor sweep over-corrected: from *arity* past *parameter types* to *the whole
descriptor string*. That made every catalog row version-dependent, because a return-type
change is invisible in source and changes the descriptor entirely — which is why every Spring
Kafka 2.x producer derives nothing (`send` returns `ListenableFuture` in 2.x and
`CompletableFuture` in 3.x).

**Match on parameter types only, ignoring the return type.** A spike measured all three
risks before this was decided:

| Question | Measured answer |
|---|---|
| Collisions after stripping the return type | 75 declared descriptors across all 55 catalogs → **zero** ambiguity. 12 carry `CompletableFuture` — those are the rows that die on Kafka 2.x. *Re-measured at implementation (W20): **96** descriptors, in the **14** catalogs that declare any — the 55 was the catalog total, not the denominator, and descriptors have never appeared in more than a quarter of them — and **16** carry `CompletableFuture` (10 `spring-kafka-template`, 6 `spring-pubsub`). The finding that decided the change is unchanged: still **zero** collisions, now held by `tests/architecture/test_catalog_descriptor_identity.py`.* |
| What consumes the declared descriptor | Compared verbatim in **one** place (`single_call.py:528`) plus a load-time validator. `dispatch.py` and `call_edges.py` use the **call site's** descriptor from facts, never the catalog's. Nothing reads the return portion. |
| Bridge methods | A covariant return does put two same-name, same-parameter methods in one class file — but call sites are disambiguated by **owner** (`Derived.get:()Ljava/lang/String;` vs `Base.get:()Ljava/lang/Object;`), and owner is already in the match. Using the return value is unaffected: `result` ids, `return_flows` and traces read the fact stream, not the catalog match. |

Caveat recorded: a generic-erasure call site could target a bridge on the **same** owner.
Both are semantically one method — the bridge delegates — so matching either row is correct.

**Fail-safe.** Where a rule genuinely *is* version-specific (a method present in 3.x, absent
in 2.x), the `measured:` block plus resolved dependency versions states the range. It must
not carry weight that belongs to getting identity right.

### 4.2 JVMS 5.4.3.3 / 5.4.3.4 resolution (C3, G-1, G-48)

We have exactly one word for *"the body is not here"* and it does three jobs. For a method
the module itself declares in a superclass, that word is **false** — 21% of one real
*[Re-measured at W22: **15.0%** on `spring-petclinic-rest` (1939 → 1649 boundary steps),
and 0% on `mall-admin`. The 21% names no corpus and reproduces on neither.]*
document's boundary steps.

**Two derived tables, computed in one pass, never cached:**

| Table | Columns |
|---|---|
| `type_hierarchy` | child, ancestor, kind (extends/implements), search position, **and whether the ancestor was scanned** |
| `method_resolution` | (class, name, descriptor) → declaring class, **or a stated reason there is none** |

Storing *resolutions* rather than only ancestors is required, not a convenience: 5.4.3.4's
maximal-specificity rule is a partial order that a flat ancestor list cannot express.

**Separate "external boundary" from "unresolved".** One value means both today, and that is
what makes it a fabrication rather than a miss.

**Wire at least one waiting consumer in the same change** — the servlet intermediate base.
Six stated COVERAGE boundaries depend on `type_hierarchy`, and G-48 is the same defect
costing `return_flows` its inherited accessors.

**Corpus:** add `spring-petclinic-rest`. Measured: it scores **96** instances of the
superclass-call shape; `fixtures/orders-service` and `mall-admin` both score **0**.
*Re-measured at implementation (W21) by walking the scanned ancestor closure and
matching name AND descriptor (JVMS 5.4.3.3), which is what the sentence above describes:
**petclinic scores 131**, not 96. `orders-service` and `mall-admin` both score **0**, as
stated. The 96 came from a rule that dropped any subclass declaring no method of its own
— `PetType` and `Specialty` inherit everything and declare only a constructor, and 35 of
the corpus's calls land on them — so the payoff was understated by 27%.*

*Two approximations were tried first and both were wrong, in opposite directions, which
is why the number is now computed the way the definition reads. Testing the ancestor by
NAME rather than by name-and-descriptor reported `mall-admin` at 5: its `SmsCouponParam`
extends `SmsCoupon`, which lives in another module and is not scanned, and `getId`/`setId`
matched two unrelated classes that happen to declare those names. That "correction" was
the error; §4.2's original 0 was right. §8.1's language rule applies to our own
measurements too — a name alone is weaker than name-plus-arity, which that section
already forbids.* The
current suite passes — 2,346 tests, 82 guards, byte-stable, contracts clean — and notices
neither of this foundation's Criticals. That is corpus blindness, and adding the corpus is
part of the fix, not an extra.

### 4.3 Acceptance for F3

- Catalog matching ignores the return portion of the descriptor; a Spring Kafka 2.x
  `KafkaTemplate.send` derives the same row as 3.x.
- `type_hierarchy` and `method_resolution` exist, and a call to a method declared in a
  scanned superclass resolves to its declaring class.
- A call whose owner was never scanned is labelled **external boundary**; a call we scanned
  and could not resolve is labelled **unresolved**, with a reason. The two are distinguishable
  in the data.
- `spring-petclinic-rest` is in the acceptance corpus and its 96 instances resolve.

---

## 5. F4 — the module edge

**Root cause:** RC-1. **Closes:** Q7, G-66, G-67, and the hard half of G-1. **Depends on:**
F1 (`Signature` formal type parameters and bounds), F3 (`type_hierarchy`).

### 5.1 What is wrong

Measured on mall-admin: **160 of 160 endpoints carry a response shape · one distinct shape
(`CommonResult#`) · zero fields on it.** Request shapes are fine — real DTOs, real fields.

Two compounding causes:

1. `CommonResult<T>` is generic and we do not substitute the type parameter, so
   `CommonResult<OmsOrderDetail>` and `CommonResult<Integer>` collapse to one shape.
2. The envelope lives in `mall-common`, a **sibling Maven module we do not scan**, so we
   cannot expand even `code` / `message` / `data`.

This is the standard multi-module Spring layout, and DR-5 gates linking on payload
compatibility — so an empty response shape is not a gap, it makes the conjunct
**unsatisfiable**. On mall, stitching could not work at all.

### 5.2 What we build

**Full generic substitution, reaching across the module edge.**

**Reach:** sibling modules in the same repo, **plus** any `extract_libraries` the user
declared. Not arbitrary third-party jars. Both halves use machinery that exists — sibling
modules are already detected (the Maven `<modules>` walk, Gradle settings) and their compiled
output is on disk; `extract_libraries` is already an opt-in `.sextant.yml` key.

**Guardrails:**

1. Read a sibling's **types**, never derive its **rows**. D06's attribution rule already says
   a module is never reported as having changed a boundary its own build did not declare.
2. Carry `origin_tier` on an expanded shape, so a consumer knows which half of a contract
   came from this module's own output.
3. When the type is unreachable, emit a **stated boundary naming `extract_libraries` as the
   escape**. Today it silently yields an empty shape, which is the defect. §8.1: a
   user-actionable escape belongs in user-facing documentation, not only in COVERAGE.

**Build the sibling-reading once.** Shapes, `type_hierarchy` (F3) and traces all want the
same reach. Three implementations of "look next door" is the wrong outcome.

Also covers `Page` / `Slice` / `ResponseEntity` / HATEOAS envelopes (G-66) — **but not the
way this row first said.** Measured in W26: `ResponseEntity` is a declared wrapper in 40
catalogs and already works, and `Page`/`Slice`/HATEOAS are not wrappers at all. A `wrappers`
entry means the type *vanishes* on the wire; `Page` does not, and declaring it as one would
publish the element type as the response body — a contract no handler produces. What these
types have in common is that their wire contract lives in **accessors**, not fields: they are
interfaces, and expansion read fields only. So the mechanism is a `serialization.accessors`
rule in the shape model (D02 §2f), read where a type's fields describe nothing, collected
across the scanned ancestry, with the same substitution as fields.

**HATEOAS is covered by the same rule and measured by nothing.** `EntityModel`,
`CollectionModel` and `PagedModel` appear in no corpus here — zero files across all six —
so no row claims them. The rule is generic and does not name them; whether it describes them
correctly is unmeasured until a corpus carries one.

### 5.3 Acceptance for F4

- `CommonResult<OmsOrderDetail>` and `CommonResult<Integer>` are distinct shapes with
  distinct fields.
- mall-admin's 160 endpoints carry more than one distinct response shape, and the shapes
  carry fields.
- An expanded shape carries `origin_tier`.
- A type reachable through neither a sibling nor `extract_libraries` produces a stated
  boundary naming `extract_libraries`, not an empty shape.
- A payload type with no fields — an interface — carries the wire contract its bean
  accessors describe, its own and its scanned ancestors', with the type arguments
  substituted. Measured on the fixture with spring-data-commons in reach:
  `Page<OrderView>` carries 11 fields and its `content` is an array of `OrderView`.

---

## 6. F5 — endpoint identity, and never merging what we cannot observe

**Root cause:** RC-5 (`peer` is not part of endpoint identity). **Closes:** C2, G-2 and the
dedup sites.

### 6.1 The rule

> *"You can't merge even if they are the same, because they may or may not be the same —
> maybe they just happen to be the same."*

An outbound HTTP call is matched by URL, path, protocol **and** request/response types.
Never by path and protocol alone.

1. **Outbound: never merge.** One row per (caller, target). Collapse only **within one
   caller**, where both sides are observable.
2. **Delete `merge_endpoints.sql`'s `both` merge.** It merges a declaration we can fully see
   with an observation we fundamentally cannot. `both` is reserved for the linking tier,
   where a schema match or human curation can justify it.
3. **Inbound is asymmetric and knowable.** Duplicates there are a **conflict to report**
   (DR-6 — Spring refuses an ambiguous mapping), not a row to drop. This builds the
   documented-but-unimplemented routing-ambiguity detector. *Built in W28 as the
   `routing_conflict` question, and "not a row to drop" was already true. The word
   "duplicates" needed narrowing: two handlers on one address is ORDINARY wherever the
   framework dispatches on something else — `@KafkaHandler` on payload type, which this
   repo's fixture has — so the rule is catalog data and only Spring MVC's two catalogs
   declare it. Measured across four corpora first: zero genuine conflicts, which is why
   the detector's design is mostly about what it must NOT report.*
4. **Self-publish / self-consume is real** — a service publishes to a topic and reads it
   back. Record **both** rows and file an open question. Never merge. Curation or the linking
   tier decides. *Built in W27 as the `self_exchange` question kind, and it covers every
   protocol rather than messaging alone: the fixture's six merged rows were four genuine
   self-publish pairs AND two fabrications — a SOAP operation merged with a call to
   `${soap.billing.uri}`, and `POST /v1/orders` merged with a call to `orders-loop`. The
   question names each side and the address it reaches, because the address is what
   separates the two readings and is the column the merge never compared.*

### 6.2 Request metadata, on every outbound protocol

There is nowhere to put any of this today, and it is what makes an outbound row identifiable:

| Protocol | Recorded |
|---|---|
| HTTP | headers, query parameters |
| Kafka | record headers, partition key |
| AMQP | routing key, properties |
| JMS | properties |
| SQS | message attributes |
| Pub/Sub | attributes |

A side table keyed by endpoint, **each entry carrying its own resolution and evidence** — so
a header whose value we could not resolve is visibly unresolved rather than absent.

*Built in W29, and the table above is optimistic — measured, six of its seven entry kinds
are not readable. AMQP's routing key was already delivered as the address (`address_arg_2`).
HTTP query parameters, Kafka record headers, SQS message attributes, Pub/Sub attributes and
JMS properties are each built as a map, a collection, or by mutation OUTSIDE the call the
endpoint row came from, and chain reconstruction is within-method (D00 §5) — so reading them
is flow analysis this system does not do, and each is a stated boundary in COVERAGE §3a-vii.
Kafka's partition key is blocked by `OI-72`. What ships is HTTP headers, the table, and the
origin-redaction, which is what the `Authorization: Bearer …` sentence below is about.*

**Redacted at the origin, not at export.** Nothing in Sextant reads a header *value*, so the
redacted value is the only one ever written down. There is no export query to add and nothing
to forget. This matters because a compiled-in `Authorization: Bearer …` literal is realistic,
and the bundle is the trust boundary. The rules need no change: `BUILTIN_KEY_PATTERNS` already
contains `authorization`, `token`, `secret`, `apikey`, `credential`, `password`, `passphrase`
and `privatekey`, and `redact_value(key, value)` replaces the value whole when the name
matches — which is exactly this table's shape.
`verify: sed -n '44,53p' src/sextant/domain/redaction.py`

**The general rule, which this is an instance of:** *redact when the value is read; keep the
real value only where analysis provably consumes it, and there redact at export.* The five
columns redacted at export today are redacted late **because analysis reads them** —
`resolved_config.value` is substituted into an address by the `resolved_peers` query, and
`call_sites.arguments` is where topic names, URLs and paths come from. Redacting those at
origin would be destructive rather than safe: the rules match on the **name**, deliberately
loosely (`aws.secretsmanager.endpoint` contains `secret` and is replaced whole though the
value is a hostname), so peer resolution would substitute the literal string `REDACTED` into
an address and publish a **fabricated** peer, which NFR-2 rates worse than a missing one.

Every new value column answers one question — *does analysis read this?* Yes, redact at
export. No, redact at origin. There is no third answer.

### 6.3 Acceptance for F5

- Two outbound calls to the same path from different callers are two rows.
- `merge_endpoints.sql` contains no `both` merge.
- Two inbound handlers claiming one route produce a reported conflict.
- An outbound HTTP call with a literal header and an unresolved header records both, with
  different resolutions.

---

## 7. F6 — the checklist gains axes beyond protocol

**Root cause:** RC-4. **Closes:** the standing COVERAGE requirement (§1.1), G-11, and the
recording half of Q2, Q3 and Q4.

### 7.1 Why this is structural, not editorial

COVERAGE §5 has **one axis, protocol**. So a non-protocol row has nowhere to exist:
`suspend fun` is a language construct; shapes, configuration, the question ledger, the bundle
and the rendered document have no section at all. That is why audit 5 found **12 committed
items enumerated nowhere**.

Delivering *"each and everything we aren't going to deliver in v1, marked supported /
partially supported / unsupported"* therefore means §5 **gains axes**, not merely more rows.

### 7.2 The axes

At minimum: **protocol · language construct · shape and contract · configuration source ·
trace and diagram · bundle and export · question ledger · rendered document.** Each row
carries one of the three support levels and, where it is not `supported`, what falls outside.

### 7.3 The table defect (G-11)

The §5.12 header declares four columns and **14 rows carry five**, so 11 Java rows lose their
status cell in any GFM renderer — each renders its *Shape* value under *Tier* and discards
its verdict. What disappears includes 2O Task 9's whole delivery record, OI-1's record
(*"Boundary — the column is EMPTY"*), and a row reading *"✅ shipped — **none of them is
read**"*, which renders as `annotation`, i.e. as if `initialDelay` **were** read.

`coverage_matrix.py` takes `cells[-1]`, so §2 stays right and the two cannot disagree loudly.
The same defect sits at §5.2 and in §8's precedence table. Documentation-only; no wrong
derived row. It is fixed mechanically, and a test asserts column count against header count
so it cannot recur.

### 7.4 What must be enumerated

- **Q2's Kotlin boundaries:** `suspend fun` contracts, extension functions, `$default`
  synthetic methods, `DefaultImpls`. Plus: §5 has **0 Kotlin rows of 170** while
  `coverage_matrix.py` **aliases Kotlin to Java**, so the matrix asserts a parity nobody
  checked. Enumerate what actually works.
- **Q3's four out-of-scope surfaces:** G-30 Spring Cloud Gateway · G-31 Kafka Streams ·
  G-34 programmatic Jakarta WebSocket registration · G-40 `@DgsEntityFetcher`.
- **Q4's six slices** (§3.8), each with what is outside it.
- **The residue of F1's `deliberately-not-read` set**, so a reader can see which parts of the
  class file we decline to read and why.

### 7.5 Acceptance for F6

- Every row in §5 has the same column count as its header, asserted by a test.
- §5 carries at least the eight axes in §7.2.
- Every item named in Q2, Q3, Q4 and F1's not-read set appears with a support level.
- No item is `supported` without a shipped row or a passing test naming it.

---

## 8. F7 — the trace tier actually meets FR-6 and FR-7

**Closes:** Fork 3 / G-50, the `terminal_kind` producer, and C11's finding that **2Q is not
delivered**. **Depends on:** F1 (`LineNumberTable`, `SourceFile`, `InnerClasses`), F3.

PROJECT.md marks 2Q `in-progress` and gives its reason; the roadmap says *"delivered
2026-09-06"*. Under C11 the stricter register wins, so **the roadmap row is what changes**.
Two requirements are unmet.

### 8.1 FR-6 — a trace bounded by a terminal, not by a depth counter

Today the walk stops at a depth bound, a cycle and a revisit. FR-6 requires a trace bounded
only by reaching a terminal. Cycle and revisit refusal stay — they are correctness. The
**depth bound** is what must go, replaced by termination at a terminal or at a stated
boundary.

### 8.2 `terminal_kind` gets a producer

Not a new mechanism. Two halves, both already decided:

1. **Deterministic, as ordinary catalog data.** A MyBatis mapper, a Spring Data repository, a
   JDBC driver, an `EntityManager` are known types in known packages. *"Calls to this owner
   are a `database` terminal"* is the same shape as everything else in a catalog — and it
   keeps framework names out of engine code, which ARCHITECTURE requires regardless.
2. **The residue goes to enrichment.** An unresolved terminal is classified by the LLM at
   `evidence: llm`, beside the deterministic ones with its tier visible, carrying its
   grounding per the K2 decision. That enriched output then feeds the next model doing the
   refactor or the optimisation.

It does not need to be complete to be useful. **And the closed set is not ours to choose —
it already exists.** `D00-fact-schema.md:205` declares it:

```
terminal_kind — outbound_call, returns, ends_silently, persistence,
                throws, unresolved, async_handoff, cycle
persistence carries target_kind: database, cache, file
```

`verify: sed -n '205,220p' docs/components/D00-fact-schema.md`

So W30 **produces the specified set**; it does not derive a new one. NFR-5 gives a closed set
exactly one definition and `tests/architecture/test_source_rules.py:158` enforces that by
file, so a second definition fails the build rather than shipping.

D00 also names the blocker, and it is exactly the user's ruling: *"three of its members —
`persistence`, `async_handoff`, and `outbound_call` — need framework knowledge no pass has
applied at a call site: a data-access call is `persistence` only to something that knows the
callee is one."* That knowledge is catalog data.

**`target_kind` (`database`, `cache`, `file`) is produced in v1.** `persistence` alone says a
call reaches storage but not whether it is a database or a cache, and that distinction is the
whole reason this was asked for.

### 8.3 FR-7 — divergent paths draw as `alt` (Fork 3, G-50)

A `narrowed` step — one of N implementations, and we cannot tell which — is drawn today as
**N consecutive arrows**, which reads as *"it calls all three, in that order."* The renderer
never reads `step.resolution`, and the caption says *"nothing is filtered."*

**Ruled: a Mermaid `alt` block, falling back to a single arrow labelled with the alternatives
where we lack the information.** This was specified at the outset — *"use alt to indicate
different path, unless we don't have that information, then fall back to A"* — and was not
built.

Whichever form is drawn, **the caption stops claiming "nothing is filtered."**

*Honest note:* `narrowed` has **never fired on real code** — four corpora measured, zero
occurrences in mall, orders-service, petclinic and jhipster. It ships with a test that
constructs the shape rather than one that waits for a corpus to produce it.

### 8.4 Class diagrams of inheritance (G-121)

FR-7 commits to *"sequence diagrams at module and system level, **and class diagrams**"*. We
already emit class diagrams — `egress/render/diagrams.py:31 class_diagram()` writes
`classDiagram` with fields and edges, tested against a hand-written view model. What is
missing is **inheritance**, and only two things are missing for it:

1. The only edge the emitter knows is `source --> target` — an *association* between shape
   types. Inheritance needs `<|--` (extends) and `<|..` (implements).
2. Nothing records who extends whom. That is **`type_hierarchy`, which F3 builds** — child,
   ancestor, kind, search position, and whether the ancestor was scanned.

So this is a projection over a table F3 creates plus two arrow kinds in an emitter that
already works, and it is **sequenced after F3**. The honesty machinery is also already
present: the `<<open>>` stereotype means *"the expansion stopped here"*, which is exactly what
an unscanned ancestor is — F3's `scanned` column feeds it directly.

**FR-7's inline note is now false regardless.** It still says module-scope diagrams ship flat,
*"no `alt`/`opt`/`loop`"*. Fork 3 overturned that, so F9's RESTATE batch corrects it.

### 8.5 Acceptance for F7

- A trace terminates at a terminal or a stated boundary; no depth counter bounds it. Cycles
  and revisits are still refused.
- Every `call_edges` row reaching a known database, remote, queue or cache owner carries a
  `terminal_kind` from the closed set.
- A `narrowed` step renders as an `alt` when alternatives are known and as one labelled
  arrow when they are not; no diagram draws N sequential arrows for one call site.
- No caption asserts "nothing is filtered" where something was.
- PROJECT.md and the roadmap agree on 2Q's status, and the status is derived from these
  tests.
- A class carrying a scanned superclass and an interface renders `<|--` and `<|..` edges; an
  unscanned ancestor renders with the `<<open>>` stereotype rather than being omitted.

---

## 9. F8 — the bundle carries everything, and an index an agent can use

**Closes:** C10, Q8a, Q8b, G-8. **Depends on:** F1 (`LineNumberTable`, `SourceFile`,
`InnerClasses`), F3, F7 (`terminal_kind`).

### 9.1 Nothing is dropped on export (C10)

> Ruled by the user: **nothing is dropped.** Parquet, DuckDB and indices exist so an agent
> or a program can query fast; making a consumer re-derive anything is the friction the
> format removes.

`_EXPORTED_TABLES` — 11 hardcoded names — becomes **every table in the schema**.
`call_edges` (1,393 rows), `return_flows` (444) and `roots` (79) travel, and so do the three
views `config_entries`, `field_writes` and `method_returns`. That is the 1,916 rows currently
dropped.

- Each needs a **deterministic `ORDER BY`** — NFR-1 applies to all of them, and is not
  grounds to exclude one.
- **Redaction is orthogonal and unaffected.** It masks *values* in five tables plus the fact
  stream; it never drops a table.
- **The ratchet inverts:** a table in the schema and absent from the export is a **test
  failure**. There is no exclusion class, so there is nothing to relitigate.

**This lands first, before anything that adds a table.** It depends on nothing, and two later
items add tables — F3's `type_hierarchy` and `method_resolution`, and F5's request-metadata
side table. A ratchet installed after the things it protects is not a ratchet, and building it
late would have recreated G-8 for four waves in a row.

**Adding a table therefore asks two questions at once**, both answered by whoever writes the
`CREATE TABLE`: *does it export?* — automatically, and the ratchet fails the build otherwise;
and *does analysis read its values?* — yes keeps the real value and redacts at export, no
redacts at origin (§6.2). There is no third answer to either.

Two corrections kept on the record, because they shaped the wrong argument first: the
rendered document and the queryable dataset are two different things and the bundle carries
both; and linking is **not** blocked without the trace tables — DR-5 matches on `endpoints`
and `shapes`, which already travel. What the trace tables unblock is cross-module tracing and
blast radius.

### 9.2 The keystone finding

**Every line number in the estate is 0.** Measured on mall-admin: 1,428 symbols, `line_start:
0`, `line_end: 0`, all of them. Paths are package paths (`com/macro/mall/….java`), not
openable files.

So Sextant can say **what** exists and not **where**. An index that cannot produce
`file:line` saves no grep at all, and the whole of §9.3 depends on F1 reading
`LineNumberTable` and `SourceFile`.

### 9.3 The index bundle (Q8b)

Reframed by the user away from *"ten named queries"*: **an index bundle plus a handful of
lookups over it**, so a developer's agent finds blast radius, call patterns and remote hops
without grepping a repository Sextant has already scanned.

| # | Index | What it answers |
|---|---|---|
| 1 | **Symbol index** | symbol → file path, line range, kind, enclosing. Pays for everything else. |
| 2 | **Reverse indexes** | who **calls** this (resolved, not text) · who **implements** this interface · which endpoints **carry** this shape · which classes carry this annotation |
| 3 | **Address index** | `GET /order/list` → root → handler → `file:line`. The agent starts from what a human said. |
| 4 | **File digest** | per file: symbols declared, boundaries contributed, annotations present — so the agent decides whether to **open** a file at all. Cheapest win; most of an agent's budget goes on files opened and discarded. |
| 5 | **Change-impact starting points** | "change `Order`" → shape, fields, endpoints carrying it, handlers, callers — as a list of `file:line` ready to open. |

**Format, ruled:** the index is a **derived NDJSON projection**, not a table — generated at
export from the tables and listed in the manifest exactly as `render/` already is. The bundle
already has this shape: `graph/*.parquet` is the dataset, `render/…` is the projection for a
human, and the index is a third projection for a machine reader. NDJSON because a grep hit
returns one complete self-describing record, which is what matters when an agent opens the
file cold with no schema.

Ships as **files the agent loads once**, not a database it must learn. A compact index is
itself greppable, which a Parquet table is not. *(An earlier draft put a "200KB instead of
50MB" figure here. That was illustration, never measured, and it is removed rather than
dressed up as evidence.)*

**Accepted cost:** the index cannot be joined against the tables in DuckDB. The index's job is
to reach a `file:line` fast; after that the consumer opens the file, or queries the tables by
the exact id the index just handed back.

Also wanted, from the same framing: `repeated_terminals(root)` (the N+1 signal, computable
today), `coupling(symbol)` fan-in and fan-out, and **`blind_spots(scope)`** — where the
analysis is blind within a scope, because a performance answer that silently ignores
unresolved calls is worse than no answer.

### 9.4 Materialisation, not indexes

DuckDB over Parquet has no B-trees. The levers are **sort order, zone maps and precomputed
tables**:

- `call_edges` ordered by caller, **and a second ordering by callee** — traversal runs both
  ways.
- A **materialised reachability table** (root → reachable symbol, depth, terminal flag). The
  trace walk already computes this and throws it away.
- `roots` addressable by wire address.

### 9.5 The resolution distribution (Q8a)

FR-17 clause 3, in v1. One `GROUP BY` on `call_edges.resolution`, a column that already
exists. Today `coverage` reports `{documents, partial_documents}` — how many files we
**opened**, and nothing about how much we **understood**.

It is the standing instrument for F3, and it is also a warning: measured on mall-admin it
reads **2,608 of 2,608 resolved — 100%**, which looks perfect and is the corpus being blind.
Every resolution number in the gap analysis came from a throwaway script written once and
discarded. This makes the number standing.

### 9.6 Acceptance for F8

- Every table and view in the schema is exported, each with a deterministic order; a new
  table absent from the export fails a test.
- A redacted bundle contains the same tables as an unredacted one.
- Symbols carry real line numbers and openable file paths on all four corpora.
- The five indexes exist as files in the bundle; an agent can go from `GET /order/list` to a
  handler's `file:line` without reading source.
- `coverage` reports the resolution distribution, and it is non-trivial on
  `spring-petclinic-rest`.

---

## 10. F9 — the registers tell the truth, and the measurement debt is paid

**Root causes:** RC-8 (measurement debt), RC-9 (the registers disagree). **Closes:** C11,
C12, and the RESTATE and MEASURE dispositions.

### 10.1 PROJECT.md becomes the delivery authority again (C11)

Update PROJECT.md to the evidence, keep it as the authority, and maintain it with every
change rather than letting it drift. **Where PROJECT.md and the roadmap disagree, the
stricter wins** — because the stale document turned out to be the right one.

Evidence gathered for the rewrite:

```
11 tables: raw_facts endpoints shapes shape_fields resolved_config open_questions
           scheduled_work error_handlers return_flows roots call_edges
D01 named queries: 1 of 10  — `trace_of` exists; callers_of, callees_of,
                             implementations_of, uses_of, impact_of, paths_between,
                             endpoint_for_address, who_uses_shape, who_reads_config do not.
                             (D01:778 says so outright: "nine of the ten below do not exist")
CLI verbs: 4
present: detector scanner resolver renderer exporter query redaction ignorefile manifest
absent:  overlay (M01/D03)  sync (M05)  stitcher (M06)  state.json (D05)
→ delivered:   D04 D06 M02 M07 M08
→ in-progress: D01 D02 D05 M00 M03 M04 M09
→ planned:     D03 M01 M05 M06   (stays correct)
```

COVERAGE follows PROJECT.md, both reflecting truth. Whether COVERAGE keeps citing PROJECT.md
as its authority does not matter — both must be true regardless.

### 10.2 FR-11…FR-14 are usage scenarios, not requirements (C12)

> Ruled by the user: **these are not requirements of Sextant. They are usage scenarios
> Sextant enables.** *"Sextant can only provide the ammo, but won't be pulling the trigger."*

They were written as things Sextant **reports**; they are things a consumer **derives** from
what Sextant reports — consistent with the whole design, where Sextant observes and judgement
belongs to enrichment, curation or a downstream tool.

Move them out of the FR section of REQUIREMENTS.md and state them as usage scenarios, each
naming the capability it depends on:

| | Scenario | Depends on |
|---|---|---|
| FR-11 | drift — Meridian generates a design, something implements it, Sextant derives the architecture from the **built** code, then they are compared | FR-22's derivation diff |
| FR-12 | refactor — the user reads architecture plus `call_edges` | `call_edges` exported (F8) |
| FR-13 | design — needs stitching between services | phase L |
| FR-14 | performance risk — needs cross-module call hops | phase L plus traces |

`M04-resolver.md:213-215` and `D01:597` must stop asserting the resolver computes them, and
the `findings` table stops being documented as something we produce.

### 10.3 FR-21…FR-24 are real requirements (C12)

`docs/meridian-integration.md` is now tracked, committed verbatim. Meridian needs Sextant's
output structured enough to compare: a boundary vocabulary, a typed derivation diff, an
observability map. **Fold FR-21…FR-24 into REQUIREMENTS.md as real requirements with
traceability rows.**

State from audit 5: FR-21 unimplemented · FR-22 unimplemented · FR-23 unimplemented ·
FR-24 **partial** (`sextant.api` ships analyze/render/enrich/export; `query` and `diff`
absent). FR-21's `dependency` kind derives from edges and dispatch, which did not exist when
the document was written and does now — so the thing that would have blocked it is gone.

### 10.4 The RESTATE batch

Thirty-nine gaps are documentation that is untrue or unmeasured. They are corrected as one
batch, not one at a time, because each is a sentence and the risk is in the aggregate:

- **Critical:** G-9 (§10.1), G-11 (§7.3).
- **Major:** G-15, G-18, G-19, G-24, G-25, G-26, G-65, G-69, G-70, plus the restate halves of
  G-16, G-20, G-21, G-27, G-49, G-64.
- **Minor:** G-85, G-87, G-92, G-94, G-95, G-97…G-102, G-105…G-109, G-113…G-116, G-118,
  G-119.
- **G-117 — FR-20 clause 2.** Rewrite it to say that approximate lookup happens against the
  index bundle (§9.3), and that commands take exact identifiers. Clause 3 already holds:
  symbols are minted as exact ids that can be given straight back.

**Rule for the batch:** a sentence in the indicative that describes behaviour we have not
tested is either given a test or rewritten to say what is true. C7's *"Both must be
matched"* is the template — a true-sounding sentence that stopped anyone from looking.

### 10.5 The MEASURE batch

Ten gaps are claims we believe but have not measured: G-22, G-27, G-43, G-45, G-46, G-67,
G-88, G-91, G-122, plus C5's per-framework listener measurement (§3.5) and Q1's per-twin
measurement (§3.3).

**Rule for the batch:** measurement means reading the framework's own class files at a named
coordinate and version, recorded in the catalog's `measured:` block. *"It is just a rename"*
and *"it presumably behaves like its sibling"* are predictions §8.1 forbids.

### 10.6 The test-debt batch

Two gaps are the same failure as an untrue register — a claim standing with nothing that
would fail if it broke.

- **G-110** — rows that verify in code but have no test: an *active* lexicographic tie-break
  between two candidates, and the other cases named at `COVERAGE.md:846,848`.
- **G-112** — `_NO_DECLINING_TEST_YET` lists **27** of the 55 catalogs (the gap analysis says
  25; re-counted 2026-09-07 — `verify: sed -n '71,110p' tests/architecture/test_catalog_near_miss_coverage.py | grep -c '^\s*"'`), and it **over-states** the
  gap for `jakarta-websocket`. Correct the markers, then build the remaining tests.

**Rule for the batch:** a row marked `supported` in COVERAGE has a test that names it. This
is the same rule the mutation harness already enforces for guards (82 guards, 0 survived,
empty allowlist) — extended from guards to coverage claims.

### 10.7 Acceptance for F9

- PROJECT.md, the roadmap and COVERAGE agree, and each claim of delivery is backed by a test
  or a shipped row.
- REQUIREMENTS.md contains FR-21…FR-24 with traceability rows, and FR-11…FR-14 appear as
  usage scenarios, not requirements.
- No document asserts in the indicative a behaviour with no test.
- Every catalog rule introduced or changed by this spec carries a `measured:` block naming a
  coordinate and version.

---

## 11. F10 — the five asymmetries

**Closes:** Q3's `IN` list. **Depends on:** F2 (vocabulary), F3 (identity).

A half-shipped surface is worse than an absent one: we say STOMP is supported, and a service
that both receives and sends STOMP gets half its messaging surface with nothing saying which
half. Each of these is small — the engine and the vocabulary already exist for the other
direction.

| Gap | What is missing | The twin that already ships |
|---|---|---|
| G-33 | `SimpMessagingTemplate.convertAndSend` — STOMP outbound | `KafkaTemplate.send` |
| G-29 | Spring MVC functional routing | the WebFlux `coRouter {}` / `router {}` catalog |
| G-42 | `StompEndpointRegistry.addEndpoint` — the URL clients actually connect to | HTTP mappings |
| G-32 | the WebSocket **client** direction | the WebSocket server direction |
| G-35 | `@MessageExceptionHandler` | `@ControllerAdvice` |

Each ships with the `measured:` discipline of §10.5 and a stated slice per Q4 where it does
not cover its whole surface.

### 11.1 Acceptance for F10

- A service that sends and receives STOMP derives both directions.
- A Spring MVC `RouterFunction` derives its routes.
- `addEndpoint("/ws")` appears as the connect address for STOMP destinations.
- `@MessageExceptionHandler` produces error-handling rows the way `@ControllerAdvice` does.

---

## 12. F11 — the curation file · **NOT IN v1**

**Ruled 2026-09-07: the curation file moves to phase L, designed together with the stitcher.**
Its only consumer is M06, which does not exist — C11's own evidence reads *"absent: overlay
(M01/D03), sync (M05), stitcher (M06), state.json (D05)"*. Building the format first would
ship a schema, an evidence tier and a no-mutation test with nothing that reads any of them:
the same capability-with-no-consumer defect this whole analysis keeps finding. The stitcher is
the only thing that can say what the format needs.

**What stays in v1:** FR-16's **wording**, corrected in F9 §10.4. The shipped text describes
something we have now ruled we will never build, and correcting a false requirement is
documentation work, not a build.

**Accepted consequence:** the open questions this spec creates — C2's self-publish/self-consume,
Fork 1's unresolvable starter, F4's unreachable type — have no *human* channel during v1. They
still reach the enrichment seat at `evidence: llm`, so they are not silent; what is absent is
a person's answer outranking a machine's.

*The design below stands as the phase-L input. Nothing in it is built in v1.*

**Closes:** G-120, and rewrites FR-16. **Not a Java/Kotlin gap** — it is here because this
spec keeps producing links that cannot be derived, and gives them nowhere to go.

### 12.1 Why DR-5 structurally cannot link some channels

Measured in our own catalogs:

| | reads | wire identity |
|---|---|---|
| `google-pubsub-publisher.yml` | `TopicName.of(project, topic)` arg 1 | a **topic** |
| `google-pubsub-subscriber.yml` | `ProjectSubscriptionName.of(project, subscription)` arg 1 | a **subscription** |

DR-5 links only when *protocol, wire identity and payload compatibility all agree*. A topic
name and a subscription name are **different strings**, and the binding between them is
created in GCP — gcloud, Terraform, the console — never in the code. Even the project id is
usually `spring.cloud.gcp.project-id`, which §8.2 classes as a deployment possibility.

**No better analysis fixes this.** It is not a knowledge gap; it is a channel whose two ends
are named differently and bound elsewhere.

### 12.2 The scope curation gets

A precise class, not an escape hatch — **indirect channels, where producer and consumer name
different ends of a binding made outside the code**:

| Protocol | Producer names | Consumer names | Derivable? |
|---|---|---|---|
| Kafka | topic | the same topic | **Yes** — DR-5 links it. No curation. |
| Pub/Sub | topic | subscription | **Never** |
| SNS → SQS | topic ARN | queue URL | **Never** |
| AMQP | exchange + routing key | queue | **Sometimes** — declared in code via `@QueueBinding`, or only in the broker. We can tell which. |

Because the class is identifiable, **Sextant emits the open question itself**, listing
candidate pairs, **in the curation file's own schema**. That makes FR-16's second paragraph
nearly free: we already write `open_questions`.

### 12.3 The rewritten FR-16

FR-16 currently says *"A person may assert, correct, or delete a statement in the graph."*
**A human cannot change a fact file.** Facts are derived deterministically from bytecode; a
hand-edit breaks NFR-1 and the evidence chain that makes every row defensible.

> A person may supply a **curation file** stating what Sextant cannot derive — chiefly that an
> outbound boundary in one module and an inbound boundary in another are the same channel,
> where the binding between them is created outside the code.
>
> Curation is an additional **input**, never a mutation. It never edits, overrides or deletes
> a fact file or a derived row. A curated statement enters at its own evidence tier, ranked
> above derived and enriched claims, and is presented to consumers as curated, carrying what
> it linked and why.
>
> Where a derived statement and a curated statement disagree, **both are kept** and the
> disagreement is reported.
>
> Where Sextant finds a link it cannot derive, it writes the open question in the curation
> file's own schema, so accepting it requires review rather than transcription.

**Two verbs are deliberately dropped.** "Correct" and "delete" are gone because a wrong
derived row is a **bug in the derivation**, not something curation papers over. Letting
curation overwrite a derived row would let derivation defects hide behind a human edit — the
opposite of the ratchet. A human answering an open question, *including* answering it "not
linked", is an assertion, not a correction.

**Evidence tier.** `facts.py:422` is `Literal["compiler", "declared"]` and `enrichment.py:80`
is `Literal[Evidence.LLM]`. Curation adds one more value, closed per NFR-5.

### 12.4 Boundary identity is already specified

A curation file needs a stable, human-writable name for each end. **D06 §5b already defines
one**, and it is what the rendered document prints: `GET /v1/orders` for http and grpc,
`pubsub order-events` verbless for kafka/pubsub/amqp/jms/sqs, `graphql query orders`. A person
can copy those strings out of the document.
`verify: sed -n '284,296p' docs/components/D06-bundle-format.md`

Open for phase L: whether `module_id` is stable across re-analysis. It comes from a
`--module-id` argument, so the key is only as stable as what the user supplied.

### 12.5 Acceptance for F11 (phase L, not v1)

- A curation file linking a named Pub/Sub topic to a named subscription produces a link
  carrying the curated evidence tier and its stated reason.
- No curation input can change a fact file or delete a derived row; a test asserts it.
- A derived link and a curated link that disagree both survive, and the disagreement is
  reported.
- An unlinkable Pub/Sub publisher/consumer pair emits an open question **in the curation
  file's schema**, so answering it is an edit rather than an authoring job.
- REQUIREMENTS.md carries the rewritten FR-16.

---

## 13. Non-goals for v1

Stated here and recorded in COVERAGE with a support level (§7), so none of them is answered
by silence.

| | Why it is out |
|---|---|
| **G-30 Spring Cloud Gateway** | Q3 = B. Routes live in configuration and call chains and would need measurement first. **Flagged:** the largest single hole and the commonest edge component. Out unless the user corrects it. |
| **G-31 Kafka Streams** | Q3 = B. A topology is a different derivation from an endpoint. |
| **G-34 programmatic Jakarta WebSocket registration** | Q3 = B. |
| **G-40 `@DgsEntityFetcher`** | Q3 = B. |
| **Kotlin-specific constructs** | Q2 = B. `suspend fun` contract shape, extension functions, `$default` synthetics, `DefaultImpls` — the **call edge across a `suspend fun` is in scope and must be verified**, only the contract shape is not. |
| **Arbitrary third-party jar expansion** | Q7. Sibling modules and declared `extract_libraries` only. |
| **Cross-service stitching** | Phase L. F5 deliberately records what stitching will need and refuses to pre-merge it. |
| **Ten named queries** | Q8b reframed them into the index bundle. D01's nine unbuilt queries — `callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`, `paths_between`, `endpoint_for_address`, `who_uses_shape`, `who_reads_config` — are served by §9.3's indexes, not by named query verbs. |

---

## 14. Dependency edges a plan must respect

Not an ordering — the constraints an ordering has to satisfy.

```
F1  extractor completeness ──┬─→ F3  method identity & resolution ──┬─→ F4  module edge
                             │                                      ├─→ F7  trace tier
                             ├─→ F4  (Signature parameter types,    │      (incl. §8.4 class
                             │        formal type parameters)       │       diagrams, which
                             │                                      │       ARE type_hierarchy)
                             │                                      └─→ F8  export & index
                             ├─→ F7  (LineNumberTable, SourceFile, InnerClasses)
                             └─→ F8  (the same three — §9.2)

F2  catalog vocabulary ──────┬─→ F10 the five asymmetries
                             └─→ F5  endpoint identity (metadata needs the vocabulary)

F7  terminal_kind ───────────→ F8  (blind_spots, repeated_terminals)

F11 curation file ───────────→ consumes the open questions F2 §3.9, F4 §5.2, F5 §6.1 and
                               Fork 1 emit; independent of F1's chain otherwise

F6  COVERAGE axes ───────────→ every foundation reports into it
F9  register truth ──────────→ runs alongside; its RESTATE batch lands after the
                               foundation whose claim it restates
```

**Hard constraints:**

1. **F1 is first.** Six items consume facts it produces, and three of them (F4's generic
   substitution, F7's and F8's line numbers) are impossible without it.
2. **F2 before F10.** Building five new surfaces on scalar vocabulary would create five more
   instances of RC-2.
3. **F3 before F4.** Generic substitution across the module edge needs `type_hierarchy`.
4. **F9's RESTATE entries follow their foundations.** Restating a claim before the code makes
   it true just moves the untruth.
5. **F11 lands after the foundations that produce open questions**, not before — its value is
   answering questions this spec creates, and building the file first would ship a schema
   with nothing to put in it.
6. **`spring-petclinic-rest` enters the corpus with F3, not after it.** The current suite
   passes and notices neither of F3's Criticals; without the corpus the acceptance tests
   cannot fail for the right reason.

---

## 15. Global constraints

Carried verbatim into every task the plan derives.

- **NFR-1 determinism.** Every new table and export gets an explicit deterministic order.
  Byte-stability across runs is a test, not an aspiration.
- **NFR-2 honest failure.** A thing we cannot determine becomes a stated boundary or an open
  question. It never becomes a default, a guess or a silence.
- **NFR-5 closed sets.** Every new vocabulary — `terminal_kind`, support levels, resolution
  values, `class_release` — is a closed set with a test that rejects anything outside it.
- **§8.1 rule 5.** Where two things look identical to us, the provider has a way to tell them
  apart. Find it; never invent one.
- **§8.2.** Code, compiled code and configuration in the repository are truth. Anything a
  deployment can overwrite is a possibility and is stated as one.
- **§8.6.** A boundary is real when a chain of evidence reaches the point where it provably
  happens, and every link is a traced call or a measured framework rule.
- **No network in tests, ever.** Probes may use the network — that is evidence gathering.
- **No version bumps** beyond the approved ASM 9.7 → 9.10.1.
- **`uv.lock` is never committed.** Never `git add -A` or `git add -u`.

---

## 16. Rulings needed — none

All three items that reached a fork are now ruled.

| | Ruling |
|---|---|
| **G-117** — FR-20 clause 2 | **Do not build.** Nothing in the derivation ever picks between candidates by name — call edges, endpoints and resolution are keyed on FQN plus descriptor. FR-20's ambiguity is a property of a string a human types, and today no command takes a name at all. Q8b already settles it: the index ships as greppable files, so approximate lookup happens against the index and commands take exact identifiers. Restated in F9 §10.4, not built. |
| **G-120** — FR-16 | **F11 §12** — curation is a file that adds links, never verbs that edit the graph. |
| **G-121** — FR-7 | **F7 §8.4** — class diagrams of inheritance, on top of F3's `type_hierarchy`. |

Plus §1.2's flag: Spring Cloud Gateway is out of v1 under Q3, and it is the biggest hole we
are choosing to leave.

---

## 17. Traceability — every gap, placed

All 123 gaps from the analysis. A gap that is not built is recorded as a stated
boundary with a support level (F6), never dropped.

| Gap | Severity | Area | Where it is answered |
|---|---|---|---|
| G-1 | Critical | `resolve/dispatch.py` | F3 §4.2 |
| G-2 | Critical | `storage/duckdb/merge_endpoints.sql` | F5 §6 |
| G-3 | Critical | `extractor-jvm` | F1 §2.1 |
| G-4 | Critical | `extractor-jvm/ClassScanner.java` | F1 §2.2 |
| G-5 | Critical | `spring-kafka.yml`, `spring-rabbit.yml`, `spring-sqs.yml` | F2 §3.5 |
| G-6 | Critical | `spring-cloud-stream.yml:29-34` | F2 §3.4 |
| G-7 | Critical | `spring-cloud-stream.yml:55-70` | F2 §3.4 |
| G-8 | Critical | `storage/duckdb/workspace.py:539-551` | F8 §9.1 |
| G-9 | Critical | `docs/PROJECT.md` | F9 §10.1 |
| G-10 | Critical | FR-11 · FR-12 · FR-13 · FR-14 | F9 §10.2 |
| G-11 | Critical | `docs/COVERAGE.md` §5.12 (also §5.2, §8) | F6 §7.3 |
| G-12 | Critical | `jakarta-jms.yml`, `spring-jms-template.yml` | F2 §3.3 |
| G-13 | Critical | `spring-kafka-template.yml` | F3 §4.1 |
| G-14 | Critical | `spring-ws-template.yml` | F2 §3.3 |
| G-15 | Major | `COVERAGE.md:836` vs `spring-actuator.yml:64-73` | F9 §10.4 |
| G-16 | Major | `spring-stomp.yml` | F2 §3.6 |
| G-17 | Major | `javax.websocket` | F2 §3.3 |
| G-18 | Major | `COVERAGE.md:1453-1454`, `:2422` | F9 §10.4 |
| G-19 | Major | `COVERAGE.md:283-306` | F9 §10.4 |
| G-20 | Major | `scripts/coverage_matrix.py` + §2b | F9 §10.4 |
| G-21 | Major | `spring-pubsub.yml` | F2 §3.3 |
| G-22 | Major | `okhttp.yml:24-27` | F9 §10.5 |
| G-23 | Major | `COVERAGE.md:1926` | F2 §3.9 |
| G-24 | Major | `COVERAGE.md:869` | F9 §10.4 |
| G-25 | Major | `COVERAGE.md:835` | F9 §10.4 |
| G-26 | Major | `COVERAGE.md:1559` | F9 §10.4 |
| G-27 | Major | `COVERAGE.md:2255-2258`, `open-issues.md` OI-10 body | F9 §10.4 |
| G-28 | Major | `COVERAGE.md:1828` | F9 §10.4 |
| G-29 | Major | Spring MVC functional routing | F10 §11 |
| G-30 | Major | Spring Cloud Gateway | §13 |
| G-31 | Major | Kafka Streams | §13 |
| G-32 | Major | the WebSocket client direction | F10 §11 |
| G-33 | Major | `SimpMessagingTemplate.convertAndSend` | F10 §11 |
| G-34 | Major | programmatic Jakarta WebSocket registration | §13 |
| G-35 | Major | `@MessageExceptionHandler` | F10 §11 |
| G-36 | Major | `spring-ws.yml` | F2 §3.1 |
| G-37 | Major | `spring-webflux-router.yml` | F2 §3.8 |
| G-38 | Major (measured away; the coordinate list was corrected) | `spring-mvc.yml` | F2 §3.7 |
| G-39 | Major | `netflix-dgs.yml` | F2 §3.1 |
| G-40 | Major | `netflix-dgs.yml` | §13 |
| G-41 | Major | `netflix-dgs.yml` | F2 §3.8 |
| G-42 | Major | `spring-websocket.yml` | F10 §11 |
| G-43 | Major | `aws-sqs-sdk.yml` | F2 §3.8 |
| G-44 | Major | `spring-jms-template`, `spring-rabbit-template`, `spring-sqs-template`, `spring-pubsub` | F2 §3.8 |
| G-45 | Major | `spring-data-rest.yml` | F2 §3.8 |
| G-46 | Major | `spring-data-rest.yml` | F9 §10.5 |
| G-47 | Major | `spring-integration.yml` | F2 §3.8 |
| G-48 | Major | `resolve/return_flow.py` | F3 §4.2 |
| G-49 | Major | `single_call.py:456-459`, `fluent.py:471-474`, `derive_call_endpoints.sql` | F9 §10.4 |
| G-50 | Major | `egress/render/document.py::_sequence_view` | F7 §8.3 |
| G-51 | Major | `single_call.py:109/:206`, `fluent.py:128/:605` | F2 §3.2 |
| G-52 | Major | `extractor-jvm/MethodFlow` | F1 §2.3 |
| G-53 | Major | `extractor-jvm/ClassScanner.java` | F1 §2.3 |
| G-54 | Major | `extractor-jvm/MethodFlow` | F1 §2.3 |
| G-55 | Major | `extractor-jvm/ClassScanner.signatureJson` | F1 §2.3 |
| G-56 | Major | `extractor-jvm` | F1 §2.3 |
| G-57 | Major | `extractor-jvm/ClassScanner.java` | F1 §2.3 |
| G-58 | Major | `docs/COVERAGE.md` §2 + `scripts/coverage_matrix.py` | F6 §7.1 |
| G-59 | Major | `extractor-jvm/Main.java` | F1 §2.3 |
| G-60 | Major | `extractor-jvm/ClassScanner.java` | F1 §2.3 |
| G-61 | Major | `extractor-jvm/ClassScanner.java` | F1 §2.3 |
| G-62 | Major | `extractor-jvm/Main.JarSource` | F1 §2.4 |
| G-63 | Major | `extractor-jvm/TypeRefs` + `ClassScanner` | F1 §2.3 |
| G-64 | Major | Kotlin, as committed scope | F7 §8.1 |
| G-65 | Major | `docs/meridian-integration.md` | F9 §10.3 |
| G-66 | Major | `spring-web.yml:54-70` | F4 §5 |
| G-67 | Major | `resolve/shapes` | F4 §5 |
| G-68 | Major | FR-17 clause 3 | F8 §9.5 |
| G-69 | Major | `docs/COVERAGE.md:361` | F9 §10.4 |
| G-70 | Major | D06 | F9 §10.4 |
| G-71 | Major | FR-9 · FR-10 · M00 | F8 §9.3 |
| G-72 | Moderate | `extractor-jvm/ClassScanner.java:648-649` | F1 §2.3 / F8 §9.2 |
| G-73 | Moderate | `extractor-jvm` access flags | F1 §2.3 |
| G-74 | Moderate | `extractor-jvm/ClassScanner.java:205` | F1 §2.3 |
| G-75 | Minor | `derive_endpoints.sql:1222` | F2 §3.5 |
| G-76 | Minor (latent) | `derive_endpoints.sql:1222` | F2 §3.5 |
| G-77 | Minor (inert today) | `combinator.py:263` | F2 §3.1 |
| G-78 | Minor | `extractor-jvm` | F1 §2.3 |
| G-79 | Minor | `extractor-jvm/JsonOut.java:20-21` | F1 §2.3 |
| G-80 | Minor | `extractor-jvm` | F1 §2.3 |
| G-81 | Minor | `extractor-jvm` | F1 §2.3 |
| G-82 | Minor | `extractor-jvm` | F1 §2.3 |
| G-83 | Minor | `extractor-jvm` | F1 §2.3 |
| G-84 | Minor | `extractor-jvm/Main.java:207-208` | F1 §2.3 |
| G-85 | Minor | `spring-restclient.yml` | F9 §10.4 |
| G-86 | Minor | `spring-webflux-router.yml` | F2 §3.8 |
| G-87 | Minor | `jakarta-jms.yml` | F9 §10.4 |
| G-88 | Minor | `spring-kafka-media.yml` | F9 §10.5 |
| G-89 | Minor | `okhttp.yml` | F2 §3.2 |
| G-90 | Minor | `spring-kafka-message.yml` | F2 §3.8 |
| G-91 | Minor | `grpc-spring.yml`, `grpc-net-devh.yml` | F9 §10.5 |
| G-92 | Minor | `microprofile-graphql.yml` | F9 §10.4 |
| G-93 | Minor | `spring-actuator.yml` | F6 §7.4 |
| G-94 | Minor | `COVERAGE.md:886` + `javax-servlet.yml:16-20` | F9 §10.4 |
| G-95 | Minor | `COVERAGE.md:899` | F9 §10.4 |
| G-96 | Minor | `COVERAGE.md:866` | F9 §10.4 |
| G-97 | Minor | `COVERAGE.md:1844` + three code sites + GUIDELINES §10 | F9 §10.4 |
| G-98 | Minor | GUIDELINES §10 | F9 §10.4 |
| G-99 | Minor | `COVERAGE.md:1614` + `injected_client.py:17-18` | F9 §10.4 |
| G-100 | Minor | `COVERAGE.md:1927` | F9 §10.4 |
| G-101 | Minor | eight §5 tier cells | F9 §10.4 |
| G-102 | Minor | `docs/principles-sweep-2026-09-05.md` | F9 §10.4 |
| G-103 | Minor | `COVERAGE.md:1657` | F9 §10.4 |
| G-104 | Minor | `COVERAGE.md:1826` | F9 §10.4 |
| G-105 | Minor | `COVERAGE.md:1988` | F9 §10.4 |
| G-106 | Minor | `COVERAGE.md:1889` / §5.10 | F9 §10.4 |
| G-107 | Minor | the Shape column, whole document | F9 §10.4 |
| G-108 | Minor | `COVERAGE.md:1779`, `:1807-1817`, `:1754-1760`, `:1322`, `:1331`, `:1218`, `:1349`, `:1917`, `:2031` | F9 §10.4 |
| G-109 | Minor | `COVERAGE.md:145-146` + `OI-32` | F9 §10.4 |
| G-110 | Minor | tests | F9 §10.6 |
| G-111 | Minor | `scripts/coverage_matrix.py` | F6 §7.1 |
| G-112 | Minor | `tests/architecture/test_catalog_near_miss_coverage.py` | F9 §10.6 |
| G-113 | Minor | `COVERAGE.md:2068` vs `:2131` | F9 §10.4 |
| G-114 | Minor | `roadmap.md:554-556` | F9 §10.4 |
| G-115 | Minor | batch-listener generics | F9 §10.4 |
| G-116 | Minor | `COVERAGE.md` §8 | F9 §10.4 |
| G-117 | Minor | FR-20 clause 2 | F9 §10.4 |
| G-118 | Minor | `docs/components/M04-resolver.md:210` | F9 §10.4 |
| G-119 | Minor | FR-18 | F9 §10.4 |
| G-120 | Minor | FR-16 | §12 (phase L) + F9 §10.4 wording |
| G-121 | Minor | FR-7 | F7 §8.4 |
| G-122 | Minor | measurement debt, as a standing item | F9 §10.5 |
| G-123 | Minor | `tests/architecture/` | F2 §3.1 |
