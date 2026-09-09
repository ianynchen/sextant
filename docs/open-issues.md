# Open issues — the standing register

**What this is.** One place for every known defect that is open, and every defect
this project introduces as it works. Created 2026-09-06 on the user's
instruction: *"Do record all new issues that are introduced, and I mean record
them in files in this repo, not in your memory file."*

**The rule.** A defect found or introduced during a task is entered here **in the
same commit group that found it**, with an id, its evidence, what it costs, and
what closes it. An issue leaves this file only when its fix ships, and the row
moves to CLOSED with the commit that closed it. A register that lies about its
own state is the defect it exists to catch.

**Relationship to the other registers.** `docs/principles-sweep-2026-09-05.md` is
the triage of one audit and stays frozen as that audit's record.
`docs/documented-not-implemented.md` holds one class — mechanisms documents
describe that code does not implement. `docs/COVERAGE.md` states BOUNDARIES: what
we cannot see and say so. **This file holds what is WRONG**, whether or not it is
also stated elsewhere.

**Not an issue: a fact or table whose reader is planned in the roadmap.** Ruled
2026-09-06 (user): *"as long as reader is planned in the roadmap, it's not an
issue, simply because the planning is not aligned yet."* A producer that ships
before its consumer is a sequencing artefact, not a defect — PROVIDED the consumer
is a named item in `docs/superpowers/plans/`. A producer whose consumer is named
nowhere is the `detect.coordinates` defect and stays an issue.

**Stop rules (§13.8).** Third occurrence of an error class → stop and raise.
**Second principle violation → stop and raise.** The running count is below and is
kept here rather than in an agent's head.

### Principle-violation count: 1 confirmed

**PV-1 (2026-09-07) — claims about our own system asserted without measuring them.**
Seven false statements were written into `docs/superpowers/specs/2026-09-06-java-kotlin-completeness-design.md`
and its plan, all of the same class: written from the conversation that produced them rather
than from the repository. Found by a systematic audit of every claim in both documents
(`8701c0a`), not by review.

Counted as **one** violation, not seven: one error class. Counting instances would inflate the
register and make §13.8's stop rule meaningless. **The consequence stands — the next principle
violation stops work.**

| | claimed | measured |
|---|---|---|
| 1 | "capability 9.19, extracted today with no consumer" | no 9.19 exists; `_CAPABILITIES` holds 14, highest 9.18 |
| 2 | W1 opens with "bump asm 9.7 → 9.10.1" | already shipped in `0674bfd`; `build.gradle.kts` pins 9.10.1 |
| 3 | `terminal_kind`'s set "derived from the corpora, not invented here" — `database`, `remote`, `queue`, `cache` | already declared at `D00-fact-schema.md:205`; the four names match neither it nor `target_kind`, and a second definition fails `test_source_rules.py:158` |
| 4 | `dependents_of` and `blast_radius` are D01 named queries | neither exists |
| 5 | "`_NO_DECLINING_TEST_YET` lists 25 of the 55 catalogs" | 27 |
| 6 | "Nothing in Wave 1 changes derived output" | false for 2 of 8 items — the worst, because it told a reviewer not to look |
| 7 | "grepping 200KB instead of 50MB is the entire point" | never measured; removed rather than dressed up |

**Closed by** `8701c0a`, `e2530f6`, `0444e63`. **What prevents recurrence:** every factual
claim in the spec and plan now carries the `verify:` command that produces it, so a claim that
goes stale is detectable rather than silently wrong (user ruling, option C). All seven were in
planning documents and none reached shipped code or output.

*Four further errors were in spoken review findings rather than in the documents, each
corrected in the same exchange: the stale-stamp guard called "silent" when it refuses loudly;
cross-repo boundary identity called unspecified when `D06 §5b` defines it; three commitments
called "open-ended" when all three are countable (14 twins, 19 catalogs, 36 attributes); and
the W3→W39 window described as leaving a bug persisting when it is today's behaviour plus a
label.*

Five candidates were judged NOT violations and are recorded so the judgement can be
overturned rather than forgotten:
- **`entry_point` ships as a `RootKind` member with no producer** (OI-22). §5.3's
  defect is an *unstated* claim; this one is stated in D00, COVERAGE §7, the enum,
  a test asserting no such row can appear, and its own register row. Producing it
  would have required a language rule in `resolve/`, which ARCHITECTURE §10
  forbids — so the alternative was violating a different principle.
- **F2's merge changed behaviour for 38 catalogs and moved zero tests** (OI-12).
  Brushes §10. Judged a coverage gap rather than a violation because the widening
  is a union of declarations already shipped elsewhere, and it is registered.
- **`roots` copies three wire columns off `endpoints`** (2Q close, defect 1).
  Brushes D01 §6's "no fact that was merely copied", which the table's own
  schema comment cites as its reason for carrying no trust columns. Judged NOT a
  violation on three grounds, recorded so the judgement can be overturned rather
  than forgotten: (1) §6's rule is about a claim that can DIVERGE, and these
  cannot — one pass writes both halves, from one read of `endpoints`, replacing
  the table whole, below every pass that writes any of the three; (2) an address
  is the row's own identity, while `resolution`/`evidence` are judgements about a
  different row, which is the distinction the schema comment draws; (3) the
  alternative — the renderer joining `roots` to `endpoints` — violates the
  ENFORCED "Egress is read-only" contract, so the choice was between a brush and
  a breach. The drift the rule warns about was real and is now measured:
  `roots.the-address-is-the-one-the-endpoint-row-ends-with`.
- **`## Traces` shipped a bounded document as its DEFAULT** (2Q close, defect 2;
  OI-30, now closed). Judged NOT a violation and instead §13.8's step 4 — *"if no
  existing principle covers it, the missing principle is the finding"*. The
  candidates were checked and none reached it: §8's *exclude only on proof* governs
  what is DERIVED, not what a rendering of derived rows chooses to draw; §8.1 rule 3
  requires a stated omission, and this one was stated three ways. Nothing written
  down said the default must be the complete form. GUIDELINES **§8.4** is that
  missing rule, and it ships with the audit list §8.3 requires — one live entry, the
  budget itself, closed the same day and its site deleted the day after with
  `render --brief`. If this judgement is ever overturned the consequence is §13.8
  step 3, not another correction: the rule now exists, and what enforces it is
  that there is no bound left in `## Traces` to flip — the guard that ratcheted the
  default went with the behaviour it pinned.

- **Stage 4 measured `microprofile-graphql`'s naming rule, found it WRONG, and shipped
  the wrong rule anyway** (`OI-5`). Brushes the cardinal sin directly: a wrong address
  keeps going out, now with a measurement saying so. Judged NOT a violation on three
  grounds, recorded so the judgement can be overturned rather than forgotten: (1) the
  defect is pre-existing and the pass neither introduced nor widened it — what changed is
  that it is measured, stated in `docs/COVERAGE.md` §5.4, and **asserted by a test**, so it
  can no longer be lost; (2) the exact rule is direction-dependent per annotation and
  `mapping.path_fallback` is one catalog-level word, so every available encoding makes a
  case that is right today newly wrong, which §8.1 rule 1 forbids in as many words; (3) the
  alternative of dropping `path_fallback` trades one wrong address for the silent loss of
  every correctly-named un-annotated operation, which is the second sin bought with the
  first. If this judgement is overturned the consequence is that `OI-5` becomes a blocker
  rather than a backlog row, not that a different approximation ships.
  **Discharged 2026-09-06** by the `annotation_driven` vocabulary pass: `OI-5` is closed,
  the wrong address no longer ships, and the grammar gap the judgement rested on is gone. The
  judgement is left standing rather than deleted, because what it argued — that raising a
  grammar gap beats encoding an approximation — is the reasoning the pass then acted on, and
  a register that erased it would lose the only record of why the defect was allowed to stand
  for a month. The count stays **0**.

### The §13.8 stop rule fired in Stage 4: THREE catalogs whose real rule the grammar cannot say

Recorded here rather than in an agent's head, because §13.8 says the third occurrence of an
error class is a diagnosis rather than a third correction. One dispatch found three, in three
different catalogs, all the same shape — **the framework's rule is known exactly and the
catalog vocabulary has no word for it**:

| # | issue | the rule | the word that is missing |
|---|---|---|---|
| 1 | `OI-5` | the un-named-operation fallback strips a bean-accessor prefix, and WHICH prefix depends on which annotation matched | `mapping.path_fallback` is one scalar per catalog; it would have to be per annotation |
| 2 | `OI-35` | the operation name may come from any of four OTHER annotations on the same method, in a fixed order | `mapping.path_from` names attributes on the MATCHED annotation only |
| 3 | `OI-36` | two listener annotations on one method are folded by javac into a container the framework reads | `annotation_driven` has no `container` word; `scheduled_work` has one, for this exact reason |

**The cause is one thing, not three.** `annotation_driven` is the style twenty-one catalogs
use, and its vocabulary grew a key at a time against whichever framework was in front of the
implementer. Each of the three above was reachable by adding one more key — and each was left
open instead, because §8.1 rule 1 forbids the approximation and adding a key mid-dispatch
would widen the engine every one of those twenty-one catalogs runs through, on one framework's
evidence. **The mechanism §13.8 asks for is a design pass over `annotation_driven`'s
vocabulary that takes all three at once**, with the three measurements above as its input;
`scheduled_work`'s `container` and `disabled` keys are the shape it would follow. Until then
the three rows stay open and none of them is fixed in isolation.

**The audit table the pass left behind is now CLOSED too, 2026-09-06, by CP-17.** That
report named four annotations whose repeatability *nothing had measured* — `@PulsarListener`,
`@SqsListener`, `@KafkaHandler`, `@RabbitHandler` — and called them measurement gaps rather
than grammar ones. All four are measured: **none of them is `@Repeatable`**, at any of the ten
versions read. Three of the four answers say the catalogs' silence was right and it is now a
claim rather than an absence of evidence; the fourth, `@PulsarListener`, turned out to have a
container the framework reads and the language never writes (`OI-38`), which is why the
prediction that it would be "the Kafka case" was worth refusing to encode. Two further defects
came out of the same reading and neither was on any backlog: `OI-39` (a whole inbound
annotation named nowhere) and `OI-40` (a class-level shape that did not exist when the comment
denying it was written).

**THE PASS RAN, 2026-09-06, and all three rows are CLOSED below.** Three words, designed
together and each naming the measurement that forces it —
`mapping.annotations[].container` (`OI-36`, CP-16), `mapping.path_from_siblings` (`OI-35`,
CP-15 rows 1-2 and the new row 6), and `mapping.annotations[].path_fallback` with the two
measured accessor words (`OI-5`, CP-15 rows 3-5). Every word is optional and inert while
absent, so the other seventeen `annotation_driven` catalogs derive byte-identically; the
design, what was rejected, and the §8.3 audit of which catalogs gained expressiveness are in
`.superpowers/sdd/2026-09-03-phase-2o-spring-surface/vocabulary-pass-report.md`, and the
vocabulary itself is D02 §2. **`OI-37` was in the pass's input and is NOT closed by it** —
its row says why, and the reason is a missing measurement rather than a missing word.

Severity: **Critical** = publishes a wrong row a reader would act on ·
**Major** = wrong under a realistic input, or a silent drop · **Minor** = stale
prose or a latent shape with no live consequence.

---

## OPEN

### OI-42 — a class file above the ceiling is refused, and the refusal kills the whole scan
**Critical · pre-existing, entered here 2026-09-06 · `docs/java-gap-analysis-2026-09-06.md`
`G-3` (audit 4 `F1`), root cause `RC-6`**

Two defects in one line of build configuration, and they need two different fixes.

**The ceiling.** `org.ow2.asm:asm:9.7` refuses `major_version` above **67** (JDK 23).
`major = JDK + 44`, so a module compiled by JDK 24, by the current LTS 25, or by 26 could not
be scanned at all. **8 of 1,792 locally cached jars already carry a major above 67.**

**The fatality.** One refused entry propagates to `Main`'s catch-all: exit 1, **zero fact
files**, for a jar of which every other class was readable. Measured on
`byte-buddy-1.18.11.jar`: `Unsupported class file major version 68`, 0 documents.
`Main.java`'s own stated rule — a finding ABOUT the input rides `uncovered` rather than
failing the request — was already the answer and was not applied here.

**Half closed 2026-09-06** by the approved bump to `asm`/`asm-tree`/`asm-analysis` 9.10.1,
which reads majors 45-71 (measured; 72 throws). `byte-buddy-1.18.11.jar` now yields 3,074
documents and 114,805 facts.

**Still open: the fatality.** A bump moves the wall to JDK 27; it does not remove it, and the
next JDK arrives on a schedule. **Closes by** an unreadable class being skipped with its
reason stated — `uncovered` plus a `partial` document — so a scan reports what it read
instead of nothing. **Falsified by** a jar with one unreadable class producing facts for
every other class in it.

### OI-3 — the multi-path WebSocket rule is documentation, not measurement
**Minor · introduced 2026-09-06 by 2O Task 13 (`2a1c918`)**

`channels_of` derives one row per registered WebSocket path. The behaviour rests
on Spring's documented registration semantics, **not on a live scan** — no pom in
this repository depends on `spring-websocket`, so nothing measured it. §8.1: a
rule taken from documentation is a prediction, and two of 2O's checkpoints
falsified exactly such predictions.
**Closes by** a fixture or probe that depends on `spring-websocket` and measures
the registration. **Falsified by** a real multi-path registration behaving
otherwise.

### OI-4 — one identity, two string spellings, and nothing enforces which you hold
**Major · SECOND OCCURRENCE (§13.8) · found 2026-09-06**

A symbol fact carries the full SCIP spelling
(`sextant-jvm maven com.acme/orders-service 1.0.0 com/acme/orders/X#m(sig_…).`)
while a call target carries the bare one (`com/acme/orders/X#m`). A join across
the two matches nothing.

- **Occurrence 1:** round 1 `F6` — the member selector compared raw parameter
  symbols against a normalised supertype.
- **Occurrence 2:** 2O Task 10 — the handler map was keyed module-prefixed and
  joined against bare descriptors. **No match on any real module, six green
  tests**, because the fixture spelled every symbol bare.

**Root cause:** synthetic fixtures are not in the same coordinate space as real
extraction, so a cross-space join bug is invisible to any test built on them —
which is most of our tests. It is a type-safety problem expressed as strings.
**Closes by** making the two spellings distinct types so mypy refuses the
comparison, or by fixture builders emitting module-prefixed symbols so tests
exercise the real space. §13.8 says diagnose at the second occurrence rather than
fix the instance twice — this row IS that diagnosis.

**Third crossing, 2026-09-06, 2Q G3 — no defect, and the row stays open.** G3's
whole subject is a join between a call target (bare, composed) and a
`method_return` (module-prefixed), and G1/G2 had deliberately pointed the two
new symbols in OPPOSITE directions, so "strip both sides" is not available as a
rule. It was discharged by doing both things this row's close condition asks
for: the strip happens in exactly one function (`return_flow._bodies_by_
descriptor`), guarded by `return_flow.callee-descriptor-is-stripped-to-bare` —
which is measured to KILL its near-miss, so deleting the strip fails a test
rather than emptying a table — and the near-miss runs on hand-built facts that
are MODULE-PREFIXED, which is this row's own prescribed fixture remedy. A second
test proves the composed descriptor agrees with what the EXTRACTOR wrote, on a
real scan, because hand-built facts compute the `sig_` hash with the same
function under test and would agree with themselves either way.

**What that does NOT do is close this row.** Nothing stops the fourth crossing:
mypy still sees two `str`s, and the next join is as free to compare them as the
first two were.

**Fourth crossing, 2026-09-06, 2Q `G4` — no defect, and the row still stays
open.** `call_edges` joins the same two spellings and carries BOTH on every row
— `target` bare (what the compiler wrote at that line) and `callee`
module-prefixed (what a walk joins to for the next hop) — which is the sharpest
form the trap has taken yet, since one row now holds both members of the pair.
It was discharged the same way: the strip is still in exactly one function,
which MOVED to `dispatch._bodies_by_descriptor` when `G4` needed the same
answer, and its guard moved with it and is measured to kill
(`dispatch.callee-descriptor-is-stripped-to-bare`). The near-misses in
`tests/application/test_call_edges.py` are module-prefixed hand-built facts, and
a real-scan half asserts the composed descriptor against what the extractor
wrote. Four crossings, four discharges, and still no type.

### OI-6 — 6 Class A Minors remain open
**Minor · pre-existing · `docs/principles-sweep-2026-09-05.md` §13**

`A-Mi17/18/19/20/21` (extractor, engine and ratchet code rather than text),
`A-Mi22` (a published contract column, waiting on the serializer question).
**None is a fabrication.**

**Two closed by F5** (`measured:` on the catalog schema). `A-Mi4` — "D02 has no
field for the version a rule was measured against" — closed by D02 §1a and
`tests/architecture/test_catalog_measurement_coverage.py`, which is the field's
consumer. `A-Mi8` — "the modern `@SqsListener` catalog names no version where
its legacy sibling names two" — closed by `spring-sqs.yml`'s row citing CP-12's
measurement of `io.awspring.cloud:spring-cloud-aws-sqs 3.1.1`, which is a
measurement that already existed rather than a version anybody chose.
The sweep document itself is frozen as that audit's record and is not edited;
this row is where their state is now kept.
### OI-7 — the Maven set carries test-scoped dependencies and the Gradle set does not
**Minor · introduced 2026-09-06 by F1**

`MavenDetector._declared_versions` does not read `<scope>`, so a `test`-scoped
dependency is in `dependency_coordinates` exactly as a compile-scoped one is.
The Gradle side reports the resolved COMPILE classpath and excludes it. The two
build systems therefore answer a slightly different question, which is the
thing `ports/detector.py` says it will not smooth over — and here it is not
smoothing it over so much as not having noticed it until F1 widened the set.

Kept deliberately: it is what a POM parse recorded before F1 too, and narrowing
it is a decision with its own evidence rather than a detail to slip into a
widening. **Cost:** a dependency-gated catalog can pass its gate on a framework
a module only test-depends on. `derived_resource` and `config_join` are the two
gated styles; a module test-depending on Spring Data REST and never using it is
the shape that would derive a fabricated API.
**Closes by** filtering `test` (and deciding `provided`/`system` with it, since
Gradle's compile classpath includes `compileOnly`) — and by a test per scope.
**Falsified by** a module whose only Spring Data REST declaration is
`<scope>test</scope>` deriving REST routes.

### OI-8 — library archive resolution still reads one pom
**Minor · found 2026-09-06 during F1**

F1 resolves a version through parents, `<dependencyManagement>`, imported BOMs
and `${…}` properties for the module's own dependency set.
`MavenDetector._library_roots` does not use it: it still calls
`_dependency_versions`, which reads the module's own pom alone. So a
`.sextant.yml` naming `groupId:artifactId` for a library whose version only a
parent manages is still reported in `libraries_not_resolved` asking the author
to pin it — a shortfall the same change could have closed one call away.

Left open on purpose rather than fixed in passing: `_dependency_versions` also
refuses a `<classifier>` and a non-default `<type>`, because those make the
ARCHIVE name wrong however well the version resolves, and routing library
extraction through the fuller resolution would widen it on the same change that
widened the dependency gate with neither widening measured.
**Closes by** composing the two — the fuller resolution for the version, the
existing classifier/type refusal for the archive name — with a test for a
library whose version a parent manages. **Falsified by** exactly that library
landing in `libraries_not_resolved`. Stated in `docs/COVERAGE.md` §5.3.

### OI-9 — what a Maven analysis records now depends on the local repository
**Minor · introduced 2026-09-06 by F1**

An ancestor pom or an imported BOM from OUTSIDE the repository is read from
`~/.m2/repository`. Two machines analysing the same commit therefore record
different `dependency_versions`, and — where the ancestor itself declares
`<dependencies>` — different `dependency_coordinates`, which the dependency
gate reads. A machine that has never built the module resolves least.

**This does not breach NFR-1 in its own terms** (same inputs, byte-identical
outputs) and the local repository was already an input, for `library_roots`.
What is new is that it now reaches the GATE, so which catalogs run for a module
can differ by machine. Visible rather than silent: every unopened pom is named
in `metadata.json`'s `dependencies_not_resolved`, and the module fact's
`content_hash` covers the versions, so a run that reached further is a
different document rather than the same one.
**Closes by** either declaring the local repository a stated input of Maven
analysis in REQUIREMENTS (documentation, and probably the right answer), or
restricting the walk to poms inside the repository and losing
`spring-boot-starter-parent` with it. **Falsified by** two machines deriving
different endpoint sets from one commit.

### OI-10 — 19 shipped catalogs state no measured version at all
**Major · pre-existing, made countable 2026-09-06 by F5 ·
`tests/architecture/test_catalog_measurement_coverage.py::_NOT_MEASURED_YET`**

F5 gave the catalog schema a `measured:` block (D02 §1a) and twenty-nine
catalogs a row citing a committed probe. **Twenty-six have none, because no
probe has ever opened the artifact whose rule they encode** — every
`@KafkaListener`, `@JmsListener`, `@RabbitListener`, gRPC, GraphQL and schema
catalog among them. Their rules are claimed for every version of their
framework on evidence from none.

This is not a new defect and F5 did not introduce it; what F5 changed is that
the twenty-six are now a named list with a reason each, and a NEW catalog cannot
join them silently. **Cost:** a framework rule that moved between versions —
`isHandler` losing a disjunct, `WebClient.exchange` disappearing at 7.0.2 — is
undetectable in these twenty-six, and the failure is silent in both directions
(a rule that stopped firing under-reports; a rule whose meaning changed
fabricates). The two the plan already names as live are `A-C5`
(`spring-cloud-stream`) and `OI-5` (`microprofile-graphql`).
**Closes by** the Stage 4 per-catalog pass — one probe per catalog against a
named artifact at a version the artifact itself reports — retiring entries from
that list as it goes. **Falsified by** a shipped catalog deriving a wrong row on
a framework version nobody in this repository has opened.

**Stage 4 progress (2026-09-06).** Twenty-six when F5 counted them. Retired
since: `spring-scheduling` (CP-14, spring-context 6.1.6/6.2.19/7.0.9),
`microprofile-graphql` (CP-15, smallrye-graphql-schema-builder 2.0.0/2.18.5),
and `spring-kafka`, `spring-jms` and `spring-rabbit` (CP-16, spring-kafka
3.1.4/4.1.1, spring-jms 6.1.6/7.0.9, spring-rabbit 3.1.4/4.1.1), and
`spring-pulsar` and `spring-sqs-legacy` (CP-17, spring-pulsar 1.2.11/2.0.7 and
both legacy messaging artifacts at 2.2.6.RELEASE and 2.4.4). The
heading above is the count as it stands and is edited down with each entry, so
this row cannot go stale about its own subject.

**A catalog measured and found CORRECT retires an entry too**, and that is worth
saying because the list's name suggests otherwise: `spring-sqs-legacy` needed no
change at all — both annotations are exactly what its `CHECKPOINT FACT` comment
claimed. What changed is that the claim now cites a run, which is the whole
point of the block. A pass that only retired entries it had to FIX would leave
the correct catalogs permanently unmeasured.

### OI-11 — nothing compares a catalog's measured version against the module's
**Major · pre-existing, stated 2026-09-06 by F5 · D02 §1a**

`measured:` records the version a catalog's rule was verified against. F1 made a
module's RESOLVED dependency versions reach `metadata.json`'s
`module.dependencies` (`mall-admin` records `spring-boot-configuration-processor
= 3.5.14`). **The two are never compared.** So a module on Spring Framework 7
is analysed by `spring-webclient.yml`, whose `exchange` terminal CP-12 measured
as REMOVED at 7.0.2, and the output says nothing about it: the row is simply
absent, indistinguishable from a call site that was never written.

Deliberately not wired in F5, on the task's own instruction — this is the
catalog's side only. Recorded here rather than left implicit because §8.1 rule 3
makes an unstated boundary a defect, and the boundary is now stateable for the
first time.
**What a later comparison needs**, so it is not re-derived: (a) a join key —
`measured[].artifact` is `groupId:artifactId` and `module.dependencies` is keyed
the same way, so the join exists today; (b) a version-ordering decision, since
"6.1.6 measured, 7.0.2 resolved" is a comparison and Maven version ordering is
not string ordering, and §7 forbids a new dependency to do it; (c) a verdict
vocabulary — the honest answer for an unmeasured version is `narrowed` or an
open question, never a suppressed row, because a rule that still holds and a
rule that broke look identical from here; (d) a decision about
`identity: assumed` rows, which name a version no archive confirmed and
therefore cannot bound anything on their own.
**Falsified by** a module resolving a version outside every `measured:` row of a
catalog that ran on it, with nothing in `metadata.json` saying so.

### OI-12 — F2 unified three divergent shape tables, and no test exercises the widening
**Major · introduced 2026-09-06 by F2 · `src/sextant/catalogs/shape-models/json.yml`**

Extracting the payload-type blocks meant merging what forty-two catalogs
actually held, and they did not all hold the same thing. Measured before the
edit: `serialization` had **one** variant across all 42; `nullability` had one
across 37 with **five declaring none** (`okhttp`, `retrofit`,
`spring-restclient`, `spring-resttemplate`, `spring-webclient`); `known_types`
had **three** — 33 catalogs with the boxes and `Void`, 8 with `LocalDate` and
`UUID` instead, and `retrofit` with two entries. The shipped model is the UNION,
so three widenings landed:

1. the 33 messaging/outbound catalogs gained `java.time.LocalDate` → `string`/
   `date` and `java.util.UUID` → `string`/`uuid`;
2. the 8 HTTP/GraphQL catalogs gained `String`, the boxes and `Void` — these
   mirror `WireTypes.objectLike`'s projection exactly
   (`test_known_types_mirror_the_projection.py`), so they change nothing for a
   scanned field and answer for a bare `class`-literal symbol, which is why the
   33 carried them;
3. the five outbound HTTP catalogs gained `nullability`. The test this replaces
   said in its own docstring that giving them one "is a behaviour change owed
   its own change — every field nullability answer on a type they reach first
   would move". F2 is that change, and it was not measured before being made.

**The whole suite passed unchanged across the edit, which is the defect.** Not
one derived row moved, so no fixture reaches a `LocalDate` or a `UUID` through a
messaging catalog, and none reaches a `@Nullable` field first through one of
those five. The widening is therefore live and untested in both directions: a
`LocalDate` in a Kafka payload now publishes `string`/`date` where it published
an expanded object, and nobody has seen either answer.

**Not merging was the worse option**, and it is worth saying why: expansion is
global and insert-if-absent, so before F2 a payload type shared between an HTTP
endpoint and a Kafka listener was described by whichever catalog sorted first —
the answer for one `LocalDate` field depended on a filename. That is a second
`A-C3` with a different symbol, and it is now impossible rather than merely
unobserved.
**Closes by** a fixture carrying a `LocalDate`, a `UUID` and an annotated
nullable field on a payload reached through a messaging catalog and through an
outbound HTTP one, asserting the shape both ways. **Falsified by** a shipped
`LocalDate` shape that a reader says is wrong under the module's serialiser
configuration.

### OI-16 — two dispatch rules will exist, and only one is designed
**Minor · introduced 2026-09-06 by 2Q G3 · amended 2026-09-06 by 2Q `G4` ·
`docs/components/M04-resolver.md` §4, `docs/components/D01-graph-schema.md` §3,
`src/sextant/application/resolve/dispatch.py`**

M04 §4 designs dispatch resolution in full — a `dispatch` table of candidates, a
`dispatch_site` table carrying the tier, rapid type analysis narrowing candidates
to types the program actually constructs, and a tier that follows M02's indexed
boundary. **None of it is built**, and neither is the `edges` layer beside it.

G3 needed the same question answered — which method could have produced this
returned value — and answered it inline: the opcode table M04 §4 already states
(exact for static/special, the declared body plus in-module overrides for
virtual/interface), the two tiers D00's closed set already has, and **no RTA**.
So `return_flows.resolution` is a dispatch tier computed by a pass that is not
the dispatch pass, and its `narrowed` sets are WIDER than the designed pass's
would be — a candidate that no `new` in the module ever creates still appears.

This is over-report rather than a wrong value, which is why it is Minor: every
candidate listed is a method the JVM could reach at that site given the declared
type. It becomes wrong the day `dispatch` ships and the two disagree about one
call, and a reader has no way to know which table to believe.
**Amended 2026-09-06 by 2Q `G4`, and it did NOT become three.** `call_edges`
needed the same question answered, so the rule moved out of `return_flow.py`
into `resolve/dispatch.py` and both derived tables read it — one inline rule,
two readers, rather than a second copy that could drift from the first. The
move also fixed a defect the single reader had hidden: `dispatch`'s "is this a
method this workspace scanned" set was built from `method_symbols` alone, which
excludes constructors by construct kind, so every `new` on a type the module
declares read as the third-party boundary. Harmless for `return_flows` (a
constructor call site carries no `result`); a silent under-report for a trace,
and 13 of `mall-admin`'s 1,979 boundary edges. Fixed in the same commit group,
recorded here rather than as its own row because it is this row's subject.
**Closes by** the designed pass landing and both tables reading its candidates
instead of re-deriving them. **Falsified by** a call site where the tables list
different candidates.

### OI-17 — an in-module override of a library-declared method is not linked
**Minor · introduced 2026-09-06 by 2Q G3 · `docs/COVERAGE.md` §7 ·
`src/sextant/application/resolve/dispatch.py`, `Dispatch.candidates` (the rule
moved out of `return_flow.py` at `G4`; it is unchanged, and it now governs
`call_edges` and therefore every trace as well)**

A return flow considers candidates only where the DECLARED callee is a method
this workspace scanned. So a virtual call through a library-declared type is a
terminal even when the module itself overrides it: `mall-admin`'s
`AdminUserDetails` implements Spring Security's `UserDetails`, and the three
calls to `getPassword`, `isEnabled` and `getAuthorities` link to nothing though
the body that runs is in the module. **Measured: 3 of 2,065 value-producing call
sites, and all three are genuine.**

**It is the conservative side of a rule with one corpus behind it, chosen under
§8.1's "never derive on half a measured rule".** Dropping the conjunct is one
line, and on `mall-admin` it adds exactly those 3 correct rows. What is NOT
measured is its cost on a codebase that calls `java/lang/Object#toString()` on a
receiver of declared type `Object` — every `toString` the module declares
becomes a candidate for it, honestly reachable and useless, and a `narrowed` set
of a hundred is noise that hides the sets worth reading. One corpus cannot size
that.
**Closes by** a second acceptance corpus measuring the candidate-count
distribution with the conjunct removed — `mall-portal` is the natural one, and
2Q's own acceptance already asks for it. **Falsified by** a trace that stops at
an in-module body a reader can see.

### OI-18 — the several-implementations rule still has no real-code exercise
**Minor · restated 2026-09-06 by 2Q G3 · `docs/COVERAGE.md` §7,
`fixtures/orders-service/.../trace/Splitter.java`**

2Q's roadmap recorded "several implementers → narrowed branch: 0 — the rule is
UNTESTED on real code", and told the phase it "must not ship unexercised". G3
ships it: a call whose dispatch reaches more than one in-module body lists all of
them at `narrowed` and picks none. **Measured again at G3, and the count has not
moved: 0 of `mall-admin`'s 166 dispatched calls have more than one
implementation.** Every one of the module's service interfaces has exactly one
`*Impl`.

So the rule is exercised by a FIXTURE — `Splitter` with `FirstSplitter` and
`SecondSplitter`, a shape written for this test — and by nothing that anybody
wrote for its own reasons. That is more than the roadmap's "unexercised" and
less than what it asked for, and the honest record is a row saying which.
Graded Minor because the failure mode is over-report and it is labelled: a
`narrowed` row states its own uncertainty, so a reader is never told a candidate
is THE answer.
**Closes by** the rule firing on a real module — `mall-portal`, or any estate
with two implementations of one service interface — with the candidate list
checked against source. **Falsified by** a real `narrowed` row whose candidate
set is wrong.

---
### OI-19 — `sig_` is computed in two languages and only an uncatchable test guards the drift
**Major · found 2026-09-06 by G3 (`4e644fd`)**

The overload disambiguator `sig_<hex>` — the first four bytes of SHA-256 of the
JVM method descriptor — is now computed **twice**: in Java by
`ClassScanner.disambiguatorOf`, and in Python by `domain/symbols.method_descriptor`
for G3's cross-method join. The two must agree byte for byte or every caller→callee
link silently returns nothing.

**Why it is not covered.** Only a test that scans real compiled classes catches
drift, and that test **cannot be a `pins` guard** — the guard harness copies no
compiled fixture. So the one mechanism that would make this permanent is
structurally unavailable to it.

**Widened 2026-09-06 by 2Q `G4`, not closed.** The same arithmetic now decides
`call_edges` and therefore every trace: a drift would not merely empty
`return_flows`, it would make every call in every module read as the third-party
boundary, so every trace would be one hop deep and every root would appear to
reach a database it never touches. The tests that would notice are still the
real-scan halves (`test_call_edges.py`, `test_trace.py`), and a real scan still
cannot be a `pins` guard.
**Closes by** either deriving the Python side from a value the extractor emits
(so there is one producer), or a build-time conformance check that hashes the
same descriptor in both languages and compares. **Falsified by** a change to
either implementation that the other does not follow: the join returns zero rows
on every real module while fixtures spelling symbols bare stay green — OI-4's
shape, one layer down.

### OI-22 — `root_kind`'s third member has no producer
**Minor · introduced 2026-09-06 by 2Q `I1` · `src/sextant/domain/closed_sets.py`
(`RootKind`), `docs/components/D00-fact-schema.md` §4, `docs/COVERAGE.md` §7**

`I1` built the `root_kind` producer that D00 documented and nothing wrote —
closing register entry #7 — and two of the set's three members are produced from
real facts: `inbound_endpoint` from every exposed `endpoints` row, `scheduled`
from every `scheduled_work` row. **`entry_point` is produced by nothing.**

**Why it was not built rather than built badly.** Which signature starts a
program is a rule of a LANGUAGE, not of this analysis, and ARCHITECTURE §10
keeps language knowledge out of the language-blind half — the descriptor a
runtime looks for is catalog data exactly as a framework's annotation is, and
`tests/architecture/test_source_rules.py::test_jvm_names_stay_in_the_jvm_extractor`
is the rule that says so. The cheap alternative, matching a method by NAME
alone, would derive a root for any method that happens to be called that, which
is a fabrication with an unusually low bar. The member stays in the set because
the traversal branches on no kind at all: it costs nothing to keep and a
removal would have to be undone.

**Cost:** a module whose only starting point is a program entry point — a batch
job, a command-line tool — produces no root and therefore no trace, and the
output does not say why. That is an under-report, which is the second sin, and
it is stated in `docs/COVERAGE.md` §7 rather than silent.
**Closes by** a catalog declaring the entry-point signature and a producer
reading it, with the catalog carrying a `measured:` row like any other.
**Falsified by** a module whose `main` starts real work and appears in no trace.

### OI-23 — a functional route is an endpoint with no handler, so it has no root
**Minor · found 2026-09-06 by 2Q `I1` · `docs/COVERAGE.md` §7,
`src/sextant/application/resolve/roots.py`**

A root is derived from an `endpoints` row that NAMES a handler. A functional
route does not: `RouterFunctions.route(GET("/kt/orders"), handler)` derives a
correct inbound row whose handler is a **lambda** the chain reader never named,
so the row carries `caller` — the method that BUILT the router — and a NULL
`handler`. **Measured on the orders-service fixture: 5 of 82 exposed rows**,
four functional routes and one binding whose destination configuration named
nothing. Each is a real served address that will appear in no trace.

**Not fixed by reading `caller` instead, which is why this is a row and not a
patch.** The router-building method runs ONCE at startup; a trace rooted there
would report route registration as the work a request does, and would do it at
`resolved`/`compiler` beside traces that are real. The honest fix is upstream —
the chain reader naming the lambda it already reads as the row's handler, which
capability 9.17 makes nameable — and then these become roots with no change to
`roots.py` at all.

Graded Minor rather than Major because the endpoint row itself is correct and
published: what is missing is its trace, the absence is stated in COVERAGE, and
nothing wrong is derived.
**Closes by** the `combinator` engine writing the handler symbol onto a
functional-route row. **Falsified by** a functional route whose real work is
invisible in every trace — which is today's state, stated.

**NOT closed by 2Q's close (defect 1), and the reason is worth stating.** That
change put a wire address ON a root, which is the opposite direction: it names
the roots that exist by the addresses that reach them. This row is about an
address that reaches NO root, because the row naming it names no handler — so
there is nothing for an address to be carried on. The close condition is
unchanged and remains upstream, in the chain reader.

### OI-27 — FR-6 says a trace is unbounded and stops only at a terminal; three things stop it earlier
**Minor · found 2026-09-06 by 2Q's rendered trace, verifying the walk against
its requirement · `docs/REQUIREMENTS.md` FR-6,
`src/sextant/application/query/trace.py::DEFAULT_MAX_DEPTH`**

FR-6 is two sentences long on this point: *"Traces are not bounded by depth. A
trace stops only at a terminal."* The shipped walk stops at a terminal
(`boundary`) and at **three other places**: a depth bound of 64, a `cycle`, and
a `revisited` method expanded elsewhere in the same trace. None is a terminal.

**Recorded now rather than earlier because rendering is what makes it visible.**
While the walk had no reader the divergence cost nothing; `## Traces` puts all
four stop reasons in front of a person, with a `Complete` column whose only
possible "no" is the depth bound — so a reader comparing the document to FR-6
finds the document right and the requirement stale, or the reverse, and nothing
tells them which.

**Which of the three is actually a defect is not obvious, and that is the
point.** `cycle` and `revisited` are defensible: recursion does not terminate if
followed, and expanding per-route is exponential on an ordinary diamond (D01's
own stated reason for a trace being a walk rather than a table). The depth bound
is a safety limit that fires on nothing measured — 0 of `mall-admin`'s 160, the
deepest being 5 — and it is never silent. So the likely close is an AMENDED
FR-6 rather than changed code, and it is entered here because §5 makes that
amendment a change to `REQUIREMENTS.md` somebody has to decide on, not something
an implementer settles in a docstring.
**Closes by** FR-6 naming the four stop reasons, or by the walk stopping only at
terminals. **Falsified by** a real module deeper than 64 edges, which would make
the depth bound a live under-report rather than a latent one.

**Checked against the trace step budget and UNAFFECTED — deliberately, and
re-checked twice: when §8.4 made that budget `render --brief`'s alone, and when
the flag was deleted and the budget with it.** The budget looked like a fifth
stop and never was one: it bounded the DOCUMENT, never the walk. Every trace was
walked in full, every trace kept its summary row with the depth and step count
that walk found, and a trace the budget did not reach was not drawn rather than
cut short. So FR-6's subject, where a trace stops, was untouched throughout, and
the two claims stay separate columns: `Complete` is the WALK's answer (its only
"no" is still the depth bound) and `Detail` is this document's. A budget that
had truncated a trace's steps would have been a fifth stop reason and a change
to this row; it was rejected for exactly that reason. Removing the budget
altogether raises this row's priority rather than lowers it: `DEFAULT_MAX_DEPTH`
is the ONLY bound left anywhere on the document, which is why GUIDELINES §8.4's
audit list names it and files it as a termination bound rather than a size one.

### OI-29 — `analyze` over a workspace whose graph schema moved crashes instead of rebuilding
**Major · introduced 2026-09-06 by 2Q's close, defect 1; found the same day by
defect 2's acceptance run · `src/sextant/api.py::_run_analyze`,
`src/sextant/storage/duckdb/schema.sql`**

`schema.sql` is `CREATE TABLE IF NOT EXISTS` throughout, and `analyze` reuses
the `workspace.duckdb` it finds. That is exactly right for a NEW table — 2Q
added two and every existing workspace grew them — and wrong for a new COLUMN,
which is what defect 1 added to `roots`. Re-analysing `mall-admin` in place
raised `_duckdb.BinderException: Table "roots" does not have a column with name
"protocol"` from inside the resolve, on the first real workspace tried.

**The rule is already written; only the mechanism is missing.** D01 §7: *"A
mismatch never produces a mixed-vintage graph. It forces the affected
rebuild"* — and `GRAPH_SCHEMA_VERSION` moved to 1.2.0 in the same change to say
so. `api._stale_stamps` enforces it at the READ gate, so `render`, `enrich` and
`export` refuse such a workspace with a message; `analyze`, which is the verb
that would fix it, has no such gate and meets the schema instead.

**Cost:** every existing workspace, on the first analyze after this change. It
is loud rather than silent and the workaround is one line — delete
`.sextant/workspace.duckdb`, or analyze into a fresh `--workspace` — but it is a
stack trace where the project's own rule promises a rebuild, and the next column
added to any table reproduces it exactly.
**Closes by** `analyze` comparing the stamps it already writes and starting from
a fresh database file when they disagree (the `_run_analyze` render-directory
precedent, which already deletes derived output it is about to replace).
**Falsified by** a column added to a derived table with no user hitting this.

### OI-31 — `architecture.html` inlines 3.5 MB of mermaid and renders every diagram on load
**Minor · found 2026-09-06 while inverting the trace default (GUIDELINES §8.4) ·
`src/sextant/egress/render/html.py::html_document`,
`src/sextant/egress/render/assets/panzoom.js`**

`mall-admin`'s complete document is a 4.6 MB `architecture.html`: **3.5 MB of it
is the vendored `mermaid.min.js`**, inlined verbatim so the page opens offline
(2K design §6b), and the remaining ~1 MB is the document itself. On load,
`mermaid.run({ querySelector: ".mermaid" })` renders all **161** diagrams before
the page settles.

**This is a PAYLOAD question and not a completeness one**, which is why it is
here rather than an argument for drawing fewer diagrams. No row is withheld and
no diagram is: what is expensive is when the rendering happens, and how much
JavaScript rides along to do it. Recording it because it is the cost that made
bounding the document look attractive in the first place — and because
GUIDELINES §8.4's audit list names it as the one entry whose close must never be
"draw less". **That is now the only close available**: `render --brief`, the one
command that produced a smaller HTML, was deleted 2026-09-06, so this row's
priority rises and its close condition does not move.
**Closes by** rendering each diagram lazily — an `IntersectionObserver` over
`pre.mermaid` calling `mermaid.run({ nodes: [node] })` on approach, with
`panzoom.js`'s `fit()` moving from the one global
`sextant:diagrams-rendered` announcement to a per-container event. **Not taken in
the change that found it**: the suite has no browser and cannot execute either
form (`tests/egress/test_render_html.py` asserts the coordination as STRINGS),
so the ordering claim that makes the per-container event safe — that an
`IntersectionObserver` callback cannot be delivered before both `DOMContentLoaded`
handlers have run — would ship measured by nothing, which §8.1's *"measured
before it is built on"* forbids. **Falsified by** a document whose diagrams all
render fast enough that nobody notices, or by that ordering being measured in a
real browser, which turns this into a small edit.

### OI-32 — `spring-petclinic-rest`'s pinned routes are stale and the pin has been failing since 2O
**Major · found 2026-09-06 by running the field check while adding the `mall`
pin · `scripts/field-expectations/spring-petclinic-rest.json`**

`python scripts/field_check.py spring-petclinic-rest` FAILS today, and has since
2O's identity migration: 13 of its 44 recorded inbound routes are spelled without
their leading separator (`GET api/pets`), and the renderer now emits every one
with it (`GET /api/pets`). The counts match — 44 either way, and no route
appeared or disappeared — so this is the migration CHANGELOG's own documented
consequence (*"Every recorded INBOUND HTTP path that omitted its leading
separator now carries one"*) reaching a recorded expectation nobody re-recorded.
`jhipster-sample-app` is clean and `mall-admin` is clean; this is the only stale
pin.

**Major rather than Minor because of what a red pin costs.** The field check is
the only always-available evidence for §5's beyond-fixture claims, and a suite
that is known-red is a suite nobody reads: the next real regression in these two
repositories lands in a check that was already failing, and looks identical to
this. It also means nothing has run this pin for the whole of 2O — an opt-in
check that is never run is not a net.

**Not fixed here, deliberately.** `field_check.py`'s own docstring reserves
refreshing a pin — *"a new `commit`, and the counts/routes re-recorded against
it"* — as *"a deliberate, reviewed act"*, and re-recording an expectation to
match today's output is exactly the move that would hide a real regression if
this were one. Someone has to look at the rows and agree the new spelling is
right.
**Closes by** the routes re-recorded with their leading separators, under
review, in a commit that says the migration is why. **Falsified by** the new
spelling being wrong, which would make this a renderer defect rather than a
stale pin.

**CLOSED 2026-09-07 by Wave 0 / W0b.** The rows were looked at and the new
spelling agreed: the two sets are **identical once the leading separator is
normalised** — 44 either way, no route gained or lost, and every difference is
the separator alone. Re-recorded deliberately.

**Two corrections to this entry's own numbers, found by measuring rather than
re-reading it.** It says **13** routes; the count is **25** of 44
(`verify: python3 -c "import json,subprocess;r=json.loads(subprocess.run(['git','show','89a35a5:scripts/field-expectations/spring-petclinic-rest.json'],capture_output=True,text=True).stdout)['routes']['inbound'];print(sum(1 for x in r if not x.split(' ',1)[1].startswith('/')))"`).
The same wrong number is repeated four times in this entry and once in
`docs/RUNBOOK.md`; both are corrected. And *"`mall-admin` is clean"* was recorded
without the pin's own `jdk: "21"` gate having been satisfied — on this machine
the default JDK is 26, so the check refuses before it builds. It IS clean, but
that had not been observed when the sentence was written.

### OI-33 — `enrich`'s brief now carries the complete document, and nothing has measured that
**Minor · introduced 2026-09-06 by inverting the trace default (GUIDELINES
§8.4) · `src/sextant/api.py::_enrich`, `src/sextant/api.py::_assembled_sections`**

`enrich` composes its brief around an in-memory `architecture.md` assembled by
the same `_assembled_sections` `render` uses — deliberately, so *"the two can
never disagree"* (2K design §8). That document is now the complete one, so for
`mall-admin` the brief's document grew from **230 KB to 711 KB**, roughly
180,000 tokens of markdown before the instructions, the tool definitions and the
model's own turns.

**Kept consistent rather than capped, and that is the judgement to overturn if
it is wrong.** GUIDELINES §8.4 exempts a bound taken against a HARD EXTERNAL
limit — a context window is exactly that, and
`application/enrich/tools.py::MAX_RESULT_BYTES` is the shipped precedent — so a
cap here would be permitted. It was not taken because **nothing has measured
that the brief overflows anything**: `enrich` needs an API key and a network, so
this repository cannot run it, and §8.1's *"measured before it is built on"*
makes an unmeasured cap a prediction. Capping the model's document while the
person's is complete would also re-introduce the exact split the 2K design
rejected.

**Cost if the prediction is wrong:** a large module's `enrich` fails at the
provider rather than at Sextant, with a context-length error naming nothing
about which section is large.
**Closes by** a measurement — one `enrich --dry-run` over `mall-admin` and a
token count of `enrich-brief.json`, which needs no key — and then either a
recorded "it fits" or a stated, `MAX_RESULT_BYTES`-style cap on the document the
brief carries. `--dry-run` writes that file already, so the measurement is one
command. **Falsified by** the brief fitting comfortably, which turns this row
into a recorded bound.

**Checked against the deletion of `render --brief` and NOT closed by it
(2026-09-06).** The flag never reached this path: `_assembled_sections` has
always handed `enrich` the complete document, so deleting the flag changes
neither the 711 KB nor the fact that nothing has measured it — this row's close
is still one `enrich --dry-run` and a token count. What the deletion does change
is the shape of the answer if that measurement comes back over the limit: there
is no longer a bounded rendering to reach for, so a cap here would be a new,
separately argued bound on what a MODEL is handed, and §8.4's audit list is
where it would have to be entered.

### OI-26 — `SEXTANT_VERSION` is declared three times
**Minor · found 2026-09-06 by 2Q `G4` while verifying OI-24 ·
`src/sextant/domain/version.py:1`, `src/sextant/ingress/read/__init__.py:16`,
`src/sextant/application/stages/analyze.py:67`**

The same constant, `"0.1.0"`, is written literally in three modules. Two of them
stamp it onto every `document` fact (`ingress/read`, `stages/analyze`) and the
third is the one `egress` reads. They must agree or two documents in one
workspace disagree about which version produced them — and nothing makes them.

Pre-existing and found rather than introduced; it is recorded because OI-24's
close condition is a version comparison, and a comparison against a constant
with three definitions would compare one of them. **Cost today is latent**: the
three literals happen to match, and the version-bump gate has not opened, so the
first bump is when they can diverge — silently, in a stamp nothing reads.
**Closes by** the two stamping sites importing `domain/version.SEXTANT_VERSION`.
**Falsified by** a version bump that moves one literal and not the others.


### OI-34 — a DISABLED cron beside a live rate is a declaration the container refuses, and we publish its other row
**Minor · found 2026-09-06 by Stage 4's `spring-scheduling` pass (CP-14 rows
4-5) · `src/sextant/catalogs/spring-scheduling.yml`, `docs/COVERAGE.md`**

`OI-2`'s close drops the row a disabled `cron` would have published. CP-14 then
measured the half `OI-2` never asked about: reaching the sentinel still counts
as having declared a schedule. Row 4 ends `... iconst_1 ; istore ; ldc_w
String - ; aload ; String.equals` — the flag is written BEFORE the comparison,
for any non-empty cron including `-` — and row 5 carries the read, where after
`fixedDelay()` is found non-negative that flag is loaded, negated and passed to
`Assert.isTrue`, which fails. So `@Scheduled(cron = "-", fixedDelay = 1000)`
starts no task at all, because the post-processor throws and the context does
not come up, while this repository publishes the `fixedDelay` row.

**Not encoded, deliberately.** Every conjunct `scheduled_work` has is per
ATTRIBUTE — `triggers` is an alias set and `disabled` is keyed the same way —
and this rule is about a DECLARATION as a whole: one attribute's value
withdrawing a different attribute's row. Building half of it (dropping the
sibling rows without also modelling which combinations the framework accepts)
is what §8.1 rule 4 forbids, so it is stated in `docs/COVERAGE.md` §5.12 and
registered here.

**Cost:** bounded to a declaration that writes the disable sentinel AND a
second trigger — code that cannot start, so the module it describes is not
running anywhere. That is why it is a Minor rather than the Major `OI-2` was:
the wrong row describes an application no reader can be looking at.
**Closes by** either a declaration-level refusal in `scheduled_work` with the
accepted-combination rule measured beside it, or a recorded ruling that
non-starting code is out of scope for every catalog rather than for this one.
**Falsified by** such a declaration exporting a `scheduled_work` row.


### OI-37 — an INHERITED `@RabbitListener` registers a listener we do not see
**Minor · found 2026-09-06 by Stage 4's listener pass (CP-16 row 4e) ·
`src/sextant/catalogs/spring-rabbit.yml`**

spring-rabbit 3.1.4 finds its annotation through
`MergedAnnotations.from(element, SearchStrategy.TYPE_HIERARCHY)`, and the
strategy arrives as a bytecode CONSTANT the probe could read rather than a
contract it had to assume. So a `@RabbitListener` declared on a superclass
method or an interface method registers a listener on the implementing bean,
while this repository holds an annotation fact only on the declaration that
carries it — the queue is under-reported for the implementing module.

**Scoped, and the scope is the point.** Kafka's `findMergedAnnotation` and JMS's
`getMergedRepeatableAnnotations` carry NO strategy constant, so what those two
search is Spring's own contract and CP-16 did not measure it; spring-rabbit
4.1.1 moved its search into `spring-amqp`'s
`AbstractListenerAnnotationBeanPostProcessor`, an artifact CP-16 does not open.
This row therefore claims spring-rabbit 3.1.4 and nothing else, which is §5.4
working rather than a hedge.

**Cost:** bounded to a module whose listener declaration is inherited — and the
ancestor is often in the same module, in which case its own row is derived and
only the ATTRIBUTION is wrong rather than the destination being absent. That is
why it is a Minor.
**Closes by** measuring the other two searches (one probe question each,
against the same jars CP-16 already resolves) and then, if the answer is the
same, a rule that walks a scanned ancestor's annotations — which is `A-M13`'s
mechanism one table over, and should be one decision rather than two.
**Falsified by** an inherited listener declaration appearing in an export
against the implementing bean.

**NOT closed by the 2026-09-06 `annotation_driven` vocabulary pass, and the
reason is a missing measurement rather than a missing word.** This row was in
that pass's input beside `OI-5`, `OI-35` and `OI-36`, and the pass rejected a
`search:` word for it explicitly. The mechanism already exists —
`effective_annotations.inherited_rows` walks a scanned ancestor's mappings, and
`annotation_driven._synthetic_annotations` gates it on the catalog declaring a
`type_annotation` — so a word turning that gate into a catalog declaration is
one line. What is missing is the evidence to point it at: two of the three
searches carry no strategy constant (CP-16's own boundary (b)), spring-rabbit
4.1.1's moved into an artifact the probe does not open, and the rule needs a
SECOND answer nothing has measured — whether the ancestor's own declaration
still derives a row of its own, and which symbol is the handler when it does.
Deriving on half of that is what §8.1 rule 4 forbids in as many words, and it is
the same judgement `OI-34` records one style over.

**What the pass DID establish, and it narrows this row.**
`annotation_driven._synthetic_annotations`' own docstring justified the gate
partly on the claim that *"a messaging listener annotation is never
interface-inherited by its own framework either"* — CP-16 row 4e falsifies that
for spring-rabbit 3.1.4, and the comment is corrected to say so rather than left
as a rationale that has quietly become false (§9). The gate itself is unchanged
and still right for the reason its OTHER half gives: an ungated walk synthesises
a listener onto every implementer, which is a different fabrication from this
under-report.

### OI-41 — the probe-provenance rule accepted a version spelling it could not then verify
**Minor · found and FIXED 2026-09-06 by Stage 4 batch 2 ·
`tests/architecture/test_probe_provenance.py`**

`_IDENTITY` admits a column header of the form `2.2.6.RELEASE` — the Spring
spelling — while the check that the header also appears in the version-scope
paragraph re-extracted versions from that paragraph with the NARROWER
`\d+(?:\.\d+)+`, which yields `2.2.6`. So a probe measuring such an artifact
failed the rule *for stating exactly what §5.4 asks it to state*, and the two
patterns had disagreed since the file was written.

Latent until CP-17 measured
`org.springframework.cloud:spring-cloud-aws-messaging 2.2.6.RELEASE`, which is
one of the two artifacts `spring-sqs-legacy.yml` names. **Fixed** by comparing
the claimed identity as a LITERAL spelling against the scope paragraph — the
same comparison `test_catalog_measurement_coverage.py` already makes on the
catalog side of the pairing, and the stricter reading of the rule's own message:
`4.1` is not agreement with `4.1.1`.

Recorded rather than fixed silently because it is a rule that would have
rejected honest evidence, which is the failure mode a rule about provenance can
least afford.


## CLOSED

### OI-40 — `@SqsListener` grew a class-level, polymorphic form and the catalog said it had none
**Major · found and CLOSED 2026-09-06 by Stage 4 batch 2 ·
`scripts/probes/cp17_containers_and_class_level.md`,
`src/sextant/catalogs/spring-sqs.yml`**

`io.awspring.cloud:spring-cloud-aws-sqs` **4.1.1** ships
`io.awspring.cloud.sqs.annotation.SqsHandler` and widens `@SqsListener`'s
`@Target` from `{METHOD}` to `{METHOD, TYPE}`; its post-processor takes the
class-level annotation's own `value()` as the queue names of a
`MultiMethodSqsEndpoint` and dispatches to every `@SqsHandler` method of the
class. That is `spring-kafka.yml`'s class-level shape one framework over, and
`spring-sqs.yml` stated in a comment that *"No class-level listener shape for
SQS"* exists.

**The comment was true when it was written and had stopped being true**, which
is the version-scope failure §5.4 exists for and is why it took a probe rather
than a review to find. CP-17 rows 2e/2f, 4e/4f and 5f measure the three halves
in the class files, and row 6f is the branch itself, out of the sources jar —
against row 6e, the *same method* at 3.1.1, which has no `classListener` at all.

**Cost while it stood:** every `@SqsHandler` method in a module on Spring Cloud
AWS 4.x was absent from the export, and so was the class-level `@SqsListener`
that names the queue, because the derivation joins method symbols only. A whole
shape missing, not an attribute of one.

**Closed** by the `spring-kafka.yml` shape, as the row asked: `prefix_from:
[value, queueNames]`, `prefix_annotation` naming `@SqsListener`, and an
`@SqsHandler` entry carrying no address of its own. **No version constraint**,
per the plan's own rule — code built against 3.1.1 cannot carry an annotation
that artifact does not declare, and a class-level `@SqsListener` is illegal
there under `@Target(METHOD)`, so the entries are inert against a 3.x module
rather than wrong about one. One test and one §10 near-miss, the guard
`spring-sqs.class-level-listener-is-the-prefix` mutation-proved to kill.

**CP-17 gained a family in the course of closing this**, which is worth
recording because it is §8.1 rule 4 catching a real omission mid-fix: the `sqs`
family asks `@Repeatable` of `@SqsListener` and reads `@SqsHandler`'s
attributes only, so the new handler entry would have declined a container on no
evidence. Rows 2n and 3n answer it — `@Target(METHOD)`, no `@Repeatable`, no
`SqsHandlers` in the jar — and appending the family left every earlier row
letter naming the same cell, checked by diffing the two runs rather than assumed.

**The residual boundaries, stated in `docs/COVERAGE.md` rather than left
silent:** a class-level listener naming more than one queue is read element-0
only (`spring-kafka.yml`'s own limitation, and row 6f shows the framework
resolving all of them), and a class carrying BOTH a class-level and a
method-level `@SqsListener` composes the two where the framework registers them
independently — the same seam `spring-kafka.yml` and `spring-rabbit.yml` already
carry a row for.

### OI-38 — a second `@PulsarListener` written into the container derived nothing
**Major · found and CLOSED 2026-09-06 by Stage 4 batch 2 ·
`scripts/probes/cp17_containers_and_class_level.md`,
`src/sextant/catalogs/spring-pulsar.yml`**

`OI-36`'s silent drop, one framework over and by a different mechanism. CP-17
rows 2a/2b read **no** `@Repeatable` on `@PulsarListener` at spring-pulsar
1.2.11 or 2.0.7 — so the vocabulary pass's guess that this would be the Kafka
case was wrong — while rows 3a/3b read
`org.springframework.pulsar.annotation.PulsarListeners` out of the same jars
declaring `value(): PulsarListener[]`, the JLS 9.6.3 container SHAPE on an
annotation the language never folds into. Rows 6a/6b, out of the sources jar at
the same coordinate, settle what the framework does with it:
`findListenerAnnotations` registers the **union** of a direct `@PulsarListener`
and every member of a hand-written `@PulsarListeners`.

A method declaring its topics that way therefore derived NOTHING, beside a
single-listener neighbour deriving normally.

**Closed** by `container:` — the key the vocabulary pass shipped, unchanged. A
class file does not record whose container it is, so the engine already read
this shape and only the DOCUMENTATION was narrower than the key (D02 §2 and two
engine docstrings now say so). Two tests, both mutation-proved against
`spring-pulsar.container-is-the-frameworks-own`: the container alone derives
both topics, and a container BESIDE a direct listener derives the union — the
case that cannot exist for a `@Repeatable` annotation and is the reason this
entry means something slightly different from `spring-kafka.yml`'s.

### OI-39 — `@PulsarReader` is a whole inbound surface the Pulsar catalog named nowhere
**Major · found and CLOSED 2026-09-06 by Stage 4 batch 2 ·
`scripts/probes/cp17_containers_and_class_level.md`,
`src/sextant/catalogs/spring-pulsar.yml`**

`org.springframework.pulsar.annotation.PulsarReader` ships in the artifact
`spring-pulsar.yml`'s `detect.coordinates` already names, declares
`topics(): java.lang.String[]` (CP-17 rows 1c/1d), and has its own
post-processor, endpoint type and registrar — rows 5c/5d show
`PulsarReaderAnnotationBeanPostProcessor` reading `PulsarReader.topics()` and
feeding `MethodPulsarReaderEndpoint.setTopics([Ljava/lang/String;)` before
registering. The catalog named the annotation nowhere, so **every reader in a
scanned module was absent from the export entirely** — not wrong, missing, which
is the second sin rather than the first and the harder of the two to notice.

**Not found by any review.** It was found by enumerating the annotation package
of a jar the catalog already depended on, which is the reading Stage 4 is sized
as. A file that describes one annotation of a framework says nothing at all
about the ones it does not mention, and nothing in this repository asked it to.

**Closed** by one more `annotations` entry. It needs no new word: `path_from:
[topics, topicPattern]` reads `topics` first-present-wins, and `@PulsarReader`
declares no `topicPattern`. It declares no container either, and that absence is
a measured claim — rows 3c/3d looked for a `PulsarReaders` and found none, rows
6c/6d show a discovery method reading the annotation alone (§8.1 rule 4). One
test and one §10 near-miss, the guard
`spring-pulsar.reader-is-a-second-inbound-surface` mutation-proved to kill.

**The residual worry this leaves, stated rather than closed:** nothing has
enumerated the annotation packages of the other twenty `annotation_driven`
frameworks, so a second `@PulsarReader` elsewhere would look exactly like this
one did — invisible. That is a COVERAGE question for the remaining Stage 4
passes, and it is why this row is written as a class rather than an instance.

### OI-5 — MicroProfile GraphQL published a wrong address for an un-named operation
**Major · pre-existing (`A-Mi9`) · measured 2026-09-06 by Stage 4's
`microprofile-graphql` pass · CLOSED 2026-09-06 by the `annotation_driven`
vocabulary pass · `scripts/probes/cp15_mp_graphql_names.md`,
`src/sextant/catalogs/microprofile-graphql.yml`**

`path_fallback: construct_name` was a prediction, CP-15 made it an observation
(`getOrders -> orders`, compiled and RUN against smallrye-graphql-schema-builder
2.0.0 and 2.18.5), and the observation said the prediction was right about the
direction and wrong about the size: the rule is **direction-dependent, and the
direction is chosen by WHICH operation annotation matched** — `@Query` and
`@Subscription` take `Direction.OUT` (strips `get`, `is`), `@Mutation` takes
`Direction.IN` (strips `set`). So no single catalog-level word could be right,
and the row stayed open with the measurement asserted in the suite rather than
a plausible half-fix shipped.

**Closed the way the row asked, by option (a).** `mapping.path_fallback` is now
a DEFAULT and `mapping.annotations[].path_fallback` overrides it per
annotation, and the closed vocabulary gained the two measured words —
`read_accessor_property` (`get`, `is`) and `write_accessor_property` (`set`).
The strip's three conditions are the framework's own and every edge of CP-15
row 5 is a parametrised assertion, `getURL -> uRL` included, which is the case
that tells this rule apart from every plausible paraphrase of it.
`test_a_microprofile_query_naming_nothing_publishes_the_wrong_address` — the
characterisation test that asserted the WRONG output so the defect could not be
lost — is now
`test_a_microprofile_operation_falls_back_to_the_name_smallrye_serves`, and it
asserts `orders`. Two guards, both measured to kill:
`derive_endpoints.path-fallback-is-per-annotation` (the engine reads the
annotation's word, not the catalog's) and
`derive_endpoints.accessor-strip-is-the-measured-one` (the length and seam
tests, without which `get` composes the empty address and `gettotal` is
republished as `total`).

**What the close does NOT settle**, stated rather than implied. Nothing was
deployed: CP-15 row 5 is the schema builder's own answer and row 3 is what says
nothing transforms the name between that call and the `Operation`'s own. And
**SmallRye is one implementation** of a specification several vendors implement,
so the rule this catalog now encodes is scoped to the two versions its
`measured:` block names — a second implementation is a second row there, not an
assumption. A live SmallRye run stays rank 2 of the sweep's probe backlog.
**Falsified by** a SmallRye deployment serving `getOrders` under its written
name.

### OI-35 — four of MicroProfile GraphQL's five operation-name sources were not read
**Major · found 2026-09-06 by Stage 4's `microprofile-graphql` pass (CP-15 rows
1-2) · CLOSED 2026-09-06 by the `annotation_driven` vocabulary pass ·
`src/sextant/catalogs/microprofile-graphql.yml`**

`getOperationName` consults five sources in order and takes the first with a
value: the operation annotation's own `value`, then
`org.eclipse.microprofile.graphql.Name`, then
`jakarta.json.bind.annotation.JsonbProperty`, then its `javax` spelling, then
`com.fasterxml.jackson.annotation.JsonProperty`. The catalog read the first
alone, so `@Query @Name("allOrders") List<Order> orders()` was served as
`allOrders` while we published `orders` — a wrong address, reached by a
different route from `OI-5`'s.

**Closed the way the row asked**, with the shape it named: `path_from_siblings`
is an ORDERED list of `{annotation, arg}` entries, consulted in the order the
catalog writes and only where every `path_from` alias is absent — which is
exactly the measured order, since CP-15 row 1 puts the matched annotation's own
`value` at index 0 of the source array. `derive_endpoints.sibling-name-source-order`
is the guard, measured to kill, and the test that kills it declares BOTH sibling
sources at once, because that is the only input an ordered list and a set answer
differently.

**One question the row did not ask, and the close needed: WHICH member of each
of those four annotations carries the name.** `@JsonProperty` declares six, so
reading `value` off the method's own name (`getOneOfTheseMethodAnnotationsValue`)
would have been §5.3's "assumed a mechanism's behaviour from its name" — the
inference that produced that rule in the first place. **CP-15 row 6** was added
for it and disassembles the loop: the selection predicate is
`containsKeyAndValidValue` (the annotation is present AND
`AnnotationInstance.value()` is non-null) and the read is the same no-argument
`value()`, at both versions. So `arg: value` on all four is measured rather than
assumed.

**What the close does NOT settle.** Row 6 shows the call and not jandex's own
contract for it: that `AnnotationInstance.value()` returns the member literally
named `value` is jandex's API rather than something this probe executed, and the
`value(String)` sibling that takes a member name — which the class also calls,
elsewhere — is what makes the distinction visible rather than assumed. And the
`javax`/`jakarta` pair is listed because the framework lists both, so a catalog
dropping either would under-report a source the schema builder still consults.
**Falsified by** a `@Query @Name("x")` method exporting anything but `x`.

### OI-36 — a method carrying TWO listener annotations derived nothing, in all three frameworks
**Major · found 2026-09-06 by Stage 4's listener pass (CP-16 rows 2 and 4) ·
CLOSED 2026-09-06 by the `annotation_driven` vocabulary pass ·
`src/sextant/catalogs/spring-kafka.yml`, `spring-jms.yml`, `spring-rabbit.yml`**

`@KafkaListener`, `@JmsListener` and `@RabbitListener` are each `@Repeatable` at
every one of the six versions CP-16 read, and each framework's post-processor
reads the container. javac writes the CONTAINER and not the annotation (JLS
9.7.5), so the class file carried no listener annotation at all, the mapping
join matched nothing, and **both** destinations vanished from the export beside
a single-listener neighbour deriving normally — a silent under-report, the
second sin and the harder of the two to notice.

**Closed the way the row asked**, with the key `spring-scheduling.yml` already
had one style over: `mapping.annotations[].container` names the container, and
the engine unfolds each container use into ordinary `{target, annotation, args}`
rows BEFORE composition and inheritance, so a folded use is an ordinary
annotation everywhere downstream and there is no container in the SQL at all.
The three catalogs now `requires` capability 9.16, for `spring-scheduling.yml`'s
stated reason: a scanner that cannot read a nested annotation must skip the
catalog VISIBLY rather than report part of a module's listener surface and stay
silent about the rest. Five guards measured to kill, two of them this row's own
— `annotation_driven.folded-uses-are-read` and
`annotation_driven.folded-entry-is-the-declared-annotation`, the second being
`scheduled_work._folded`'s conjunct that stops any array-of-annotations argument
contributing destinations — plus one per catalog on the container fqn itself.

**What the close does NOT settle**, and each is an absence claimed rather than
overlooked. `@KafkaHandler` and `@RabbitHandler` declare NO container here,
because CP-16 row 2 measured `@Repeatable` on the listener annotations only and
row 3 read the handler annotations' whole declaration without asking whether
they are repeatable — an unmeasured container is not one a catalog names (§8.1
rule 4). And the folding is deliberately NOT restricted to method targets, since
`@KafkaListener` and `@RabbitListener` are `@Target`-legal on a TYPE (CP-16 rows
2a/2e): a class carrying two class-level listeners folds identically and the
prefix join composes both, which is the framework's answer rather than a
widening. **Falsified by** a two-listener method exporting neither destination.

### OI-2 — a DISABLED scheduled job was reported as live work
**Major · introduced 2026-09-06 by 2O Task 8 (`35fa4d5..4e51317`) · CLOSED
2026-09-06 by Stage 4's `spring-scheduling` pass ·
`scripts/probes/cp14_schedule_sentinel.md`,
`src/sextant/catalogs/spring-scheduling.yml`**

`spring-scheduling.yml` treated no cron value as the framework's "never schedule
this" sentinel, because no probe had measured which value the framework so
reads and encoding one from memory is what §8.1 forbids. So a schedule the
framework would never run published a `scheduled_work` row saying it does.

**Closed the way the row asked — one probe question and one catalog key.**
CP-14 reads `@Scheduled.CRON_DISABLED` off the annotation's own class file at
spring-context 6.1.6, 6.2.19 and 7.0.9 (byte-identical: `-`), puts the
comparison between the `cron()` read and `ScheduledTaskRegistrar.scheduleCronTask`
with no other `schedule*` call downstream of it, and — the converse question
CP-10's table is criticised for never asking — enumerates every string
comparison in the post-processor and finds exactly ONE, which is what bounds
the new `disabled:` key to `cron` by measurement rather than by choice.
`spring-scheduling.the-disable-sentinel-is-the-frameworks-own` and
`scheduled_work.a-disabled-trigger-declares-no-task` are the two guards, both
measured to kill; the falsifier this row named — a disabled schedule appearing
in an export — is now a failing test rather than a hope.

**What the close did NOT settle**, and both are stated rather than implied: a
`${...}` placeholder whose deployed value is `-` is disabled by the same rule
and stays `unresolved` here (§8.2), and a disabled cron sitting beside a live
rate is `OI-34`.

### OI-30 — the default document drew the steps of a minority of a large module's traces
**Minor · introduced 2026-09-06 by 2Q's close, defect 2 · found AND closed
2026-09-06 by GUIDELINES §8.4 (same commit group) ·
`src/sextant/egress/render/document.py::BRIEF_TRACE_STEP_BUDGET`**

`mall-admin` rendered 37 of 160 traces in full and left 123 as a summary row
each, and the cost this row recorded was borne by a reader: **the trace you came
for may be one of the 123**. It was recorded as a Minor with the cost accepted;
the user overruled the trade a day later — *"we should be focused on telling the
truth, not the amount of information"* — and the register's own suggested close
("a rendering that needs no budget") turned out to be the answer read backwards.
There was never a budget the document needed.

**Closed by inverting the default rather than by any of the three renderings
this row proposed.** `## Traces` now draws all 160. Its own falsifier — *"a
reader who could not find what they needed in the summary row and did not know
the flag existed"* — is now unreachable by construction, since nothing is left
out to find.

**Amended 2026-09-06, same day: the budget is gone rather than opt-in.** The
close above left it as `render --brief`, ratcheted by
`render_trace.the-default-document-draws-every-trace`; the user then deleted the
flag — *"deleting that --brief if it only cuts the first N. that's same as
lying"* — because what it drew was a prefix of the summary table in table order,
which no in-band statement turns into a summary. `BRIEF_TRACE_STEP_BUDGET`, the
`trace_step_budget` parameter, the CLI flag, the banner and the three guards
that pinned the bounded form are all deleted; there is one render and it is the
complete one. This row stays CLOSED and its close is now stronger, not weaker.
A trimmed document is enrichment work — *"that's a different story and a
different ask"* — and would be an overlay, never a render flag.

**The lesson is in GUIDELINES §8.4 and not in this row**: the omission was
stated three ways (a `Detail` column, a sentence, M07) and the default was still
wrong, because a stated omission is honest and is not thereby acceptable. What
remains of the cost is `OI-31`, which is the payload question this row's
`4.5 MB` measurement was actually about.

### OI-28 — a root's copied wire address could be taken before the row finished being written
**Major · found AND closed 2026-09-06 by 2Q's close, defect 1 (same commit
group) · `src/sextant/application/resolve/pipeline.py`**

Recorded even though it never shipped, because the register is where a
near-miss is remembered and because it is the live instance of the rule the
header's third judged-not-violation argues from. `record_roots` ran directly
below `derive_endpoints`, on the stated grounds that "nothing below this line
writes either column" — true of `handler` and `direction`, and false the moment
the pass began copying `protocol`: `apply_protocol_hints` reclassifies rows
other engines minted, six passes further down. The first run of the changed pass
against the orders-service fixture put `http /events/emitter` in `roots` while
`endpoints` said `sse /events/emitter` — one address, two spellings, one
workspace, and the rendered trace would have quoted the stale half.

**Caught by an existing test rather than by review**
(`test_the_table_is_replaced_whole_rather_than_appended_to`, which re-runs the
pass and compares: the re-run read the final column and the pipeline's run had
not). The pass moved below `apply_protocol_hints`, and the position is now a
measured guard — `roots.the-address-is-the-one-the-endpoint-row-ends-with` —
because no property of either pass in isolation can catch an ordering.

### OI-25 — the traversal had no reader outside its own tests
**Minor · introduced 2026-09-06 by 2Q `G4`/`I3` · CLOSED 2026-09-06 by 2Q's
rendered trace · `src/sextant/egress/render/document.py::_trace_sections`**

`application/query/trace.py` was called by its tests and by nothing in `src/`.
It is now called by `api._assembled_sections`, at the composition root, and its
answer is handed to `assemble_module_document(traces=…)` as data — so `## Traces`
renders one trace and one Mermaid `sequenceDiagram` per row of `roots`, in both
`architecture.md` and `architecture.html`.

**Closed on its own condition** — "a rendered trace or a query surface reading
it" — by the first of the two. Its two named blockers were both decisions rather
than work: `I4`'s enrichment anchor is not needed for a machine section (this one
carries none, and adding an anchor is a separate change), and no public API verb
was added, so GUIDELINES §7 is untouched.

**What the close does not claim.** `egress` still never sees a workspace: the
walk runs at the composition root and the import contract "Egress is read-only"
is unchanged. And the rendering applies none of M07's designed noise filters and
draws no `alt`/`opt`/`loop` structure — both are recorded in M07 rather than
here, the first as a deliberate choice and the second as D00 §5's already-priced
`ordinal` enrichment.

### OI-24 — D01 §7's conservative re-derivation rule was not enforced anywhere
**Major · found 2026-09-06 by 2Q `G4` · CLOSED 2026-09-06 by 2Q's rendered trace ·
`src/sextant/api.py::_stale_stamps`**

`_refuse_if_unanalyzed` checked that `metadata.json` and `workspace.duckdb`
**exist**, and nothing anywhere compared a recorded version against the running
one. `api._stale_stamps` now compares all three — `schema_version`,
`provenance.sextant_version`, `provenance.fact_schema_version` — inside that same
gate, so `render`, `enrich` and `export` refuse a workspace a different build
wrote, naming the stamp that moved. An ABSENT stamp counts as a mismatch.

**It closed here because this is the change that made it live**, exactly as the
row predicted: `## Traces` reads `roots` and `call_edges`, and a 1.0.0 workspace
answers both with no rows — which renders `None found.` for a module with 160
endpoints. `GRAPH_SCHEMA_VERSION` moved to `1.1.0` in the same change, so an
existing workspace is refused rather than silently rendered short.

**The falsification condition is recorded as NOT met and now unreachable by
construction**: "a workspace analysed by one version and rendered by another
producing a document that is wrong rather than refused" is what the gate now
forbids, and four tests pin it (`api.workspace-stamp-matches-the-running-build`,
measured killed) against one near-miss proving a workspace this build wrote is
still rendered.

**What it does NOT close.** `OI-26` stays open: `SEXTANT_VERSION` is still
declared three times, and the two other literals stamp `document` FACTS rather
than `metadata.json`. The comparison above reads the one constant
`egress/render/metadata.py` writes with, so the gate is sound today and the
divergence `OI-26` describes would show up in a fact stamp instead.

### OI-14 — capability 9.17 produced a fact nothing read
**Minor · introduced 2026-09-06 by 2Q G1 · CLOSED 2026-09-06 by 2Q `G4` ·
`src/sextant/application/resolve/call_edges.py`**

`call_site.implementation` named the lambda body a `dynamic` site dispatches
into and nothing consumed it. The row's own close condition was "G4's traversal
following `implementation` into the body, with a trace that reaches a terminal
only reachable through a lambda", and that is exactly what closed it, not a
re-reading of the condition.

`resolve/call_edges.py` makes an `invokedynamic` site an edge into the body it
CREATES rather than into the bootstrap factory its own target names — which
would make every lambda in every module a platform terminal. **Measured on
`macrozheng/mall`'s `mall-admin`: 15 lambda bodies reached, and 7 of the 160
traces reach a terminal that no other path in the trace reaches**, including the
module's one recursive cycle (`UmsMenuServiceImpl#covertMenuNode`, a menu tree
built through a lambda). The condition asked for one; there are seven.

**The amendment stands and is not weakened by the close.** `return_flow.py`
still excludes `dynamic` sites whole, and for the reason the amendment gave: an
`invokedynamic`'s `result` is the functional-interface INSTANCE, not anything
the body handed back. Reachability is a different claim from provenance, and
`call_edges` carries `invoke_kind` on the row so a reader is never told the body
runs at that line.

### OI-20 — `return_flows` had no reader until G4
**Minor · introduced 2026-09-06 by G3 (`4e644fd`) · CLOSED 2026-09-06 by 2Q `G4` ·
`src/sextant/application/query/trace.py`**

`return_flows` was derived every resolve and queried by nobody but its tests.
The row named its own closer — "G4 reading it" — and that is what closed it:
`application/query/trace.py` joins it on (`caller`, `ordinal`, `callee`) so
every trace step carries what its callee hands back, which is the "→ response"
half of request-to-response the phase promised.

**The falsification condition is worth recording as NOT met**: the row said it
would be falsified by "G4 shipping and reading something else, which would mean
the table's shape was designed against a guess". G4 reads the shape as designed,
on the key as designed, and needed no column added to it.


### OI-15 — capability 9.18 produced a fact kind nothing read
**Minor · introduced 2026-09-06 by 2Q G2 · CLOSED 2026-09-06 by 2Q G3 ·
`src/sextant/application/resolve/return_flow.py`**

`method_return` recorded what a method hands back and nothing consumed it. The
row named its own closer exactly — "G3 reading it: a callee's returned value
linked to the caller's `result` id, with a trace that crosses a method
boundary" — and that is what closed it, not a re-reading of the condition.

`resolve/return_flow.py` reads the fact through a new `method_returns` named
query (the projection the row noted no query reached) and joins it to
`call_sites`, once per resolve, from the pipeline. On `macrozheng/mall`'s
`mall-admin` it links **552 call sites and 566 returns**, `OmsOrderController
#list`'s value 7 among them: value 7 is now stated to be what
`OmsOrderServiceImpl#list` hands back, which is in turn the result of
`OmsOrderDao#getList` — the MyBatis terminal — read against the source.

The row's "two things it deliberately does NOT do" are both now done: the join
to a caller exists, and a named query is registered because there is finally a
consumer to register it for. **What did not close is OI-14**, which is the
sibling row and names a different reader: `call_site.implementation` is
deliberately NOT read here, because an `invokedynamic`'s `result` is the lambda
INSTANCE and not anything the body returns — following the body is a traversal
step, which is G4's.

### OI-13 — the plan cites `A-C2` for a defect the sweep files under `A-C3`
**Minor · found 2026-09-06 during F2 · CLOSED 2026-09-06 by `3b3ba58` ·
`docs/superpowers/plans/2026-09-05-java-completion-plan.md:87`, `:354`**

F2's own entry said "Sweep 2's `A-C2` is the consequence: the `Void` mapping
replicated in 28 with 9 missing", and the stage-2 summary said the same of
"`A-C2`'s nine-catalog defect". `A-C2` in
`docs/principles-sweep-2026-09-05.md:122` is the OkHttp
`.method("DELETE", …)` → `GET` fabrication; the `Void` finding is `A-C3` at
`:123` and `:352`. The collision is a sweep-2-local numbering (`A-C2` is
labelled "Sweep 2, C-1" and `A-C3` "Sweep 2, C-2") leaking into a document that
uses the global ids everywhere else.

Cost was a reader's, not a run's: following the citation landed on a different
Critical in the same table, and both are about a wrong value in a catalog, so
the mistake did not announce itself. Closed as this row said it would be — by
correcting **both** references, the plan being revised for Stage 3. The sweep
document itself is untouched: it stays frozen as that audit's record, and its
own numbering was never wrong.

### OI-1 — every Spring Integration channel question was filed under `amqp`
**Major · introduced 2026-09-06 by 2O Task 9 (`bd61663`) · CLOSED 2026-09-06 by
`947102f` · COVERAGE.md:1933**

`spring-integration.yml` declared `protocol: amqp` and stamped it on **every**
`channel_destination` question it filed, a Kafka- or JMS-fed channel's included.
Closed by option (a), the rule Task 8 already agreed read one level finer:
`resolve/endpoints.py`'s check is keyed on whether the CATALOG derives endpoint
rows rather than on whether its style is nominally a wire one, so a catalog that
mints none declares neither `protocol` nor `direction`, and the question's column
is empty instead of guessed.

**A second defect fell out of it, fixed in the same commit.**
`config_join.derives_rows` answered "derives" for any catalog with an
`address_from_config` block, which is wrong by its own docstring: with no `key`
the engine asks configuration nothing and answers no channel. That wrong answer
is exactly what demanded a protocol of a file that mints nothing. Its other
reader is the engine ordering, where a catalog writing no rows may sort anywhere
— so the ordering half was harmless and the wire-identity half was not.

**Two shipped catalogs are governed** (§8.3's audit list, checked by
`test_call_engines`'s whole-estate run): `spring-integration.yml` and
`spring-kafka-media.yml`, whose top-level `direction: inbound` sat beside one
inbound and one outbound stamping rule.

**Not closed by this, and it is not a defect:** which broker feeds a channel is
still unread. That is the Stage 4 adapter split, and it stays in `COVERAGE.md`
as an ABSENCE — the honest state — rather than here as a wrong value.

### OI-43 — FR-19 describes a redaction mechanism the project deliberately does not build
**Major · found 2026-09-07 while wiring Wave 0's W34 redaction · `docs/REQUIREMENTS.md:293`**

FR-19's second paragraph reads: *"Sextant redacts values matching configured
patterns at the moment facts are produced, so that a secret appearing inside a
file that is otherwise analysed never reaches storage."*

**Both halves are false of the shipped design, and deliberately so.** 2K design
§1 ruled the opposite and gave its reason: the workspace stays **verbatim**
because analysis needs the real values — peer resolution substitutes a real
address into `${aws.secretsmanager.endpoint}` — and *"the analyst's own disk is
not the trust boundary. The bundle is."* So redaction happens at the **exits**,
not at production, and a matching secret **does** reach storage by design. The
code says so plainly (`storage/duckdb/workspace.py`'s `_stage_redactions`, and
`export_facts`'s own docstring); the requirement was never restated to match.
`verify: grep -n "the workspace itself keeps verbatim values" src/sextant/storage/duckdb/workspace.py`

**Major because of who reads it.** FR-19 is the requirement a reader consults to
decide whether a workspace directory is safe to keep, share or back up. It
currently tells them a secret never reaches storage, and one does. That is the
one direction a wrong claim about redaction must never point.

**Not tracked anywhere before this.** FR-19 appears in no other document except
a Phase 1 plan listing it as not-yet-covered — not in `open-issues.md`, not in
`documented-not-implemented.md`, not in `COVERAGE.md`.

**Not fixed here, deliberately.** Correcting an FR's wording is F9's RESTATE
batch (spec §12, `W51`), which is where every other false requirement statement
in this plan is being repaired; fixing this one ahead of that batch would split
the work and leave the batch's own list incomplete. It also interacts with a
ruling not yet built: spec §6.2 rules that columns analysis does **not** read
are redacted at the ORIGIN (W29's request-metadata table is the first), which
makes FR-19's wording true of the new columns and still false of the existing
five — so the restatement has to describe the split, not simply invert.

**Closes by** FR-19 restated to say redaction happens at the exits for values
analysis consumes and at the origin for values it does not, with the
verbatim-workspace consequence stated where a reader deciding what to do with a
workspace will see it. **Falsified by** a decision to actually redact at
production for all five existing columns, which 2K considered and rejected on
the grounds that it breaks peer resolution.

### OI-44 — a catalog still hardcodes a framework default that the jar now states (W4a)
**Major · found 2026-09-07 by code review of W4 · `src/sextant/catalogs/*.yml`,
`src/sextant/application/resolve/`, `docs/components/D02-catalog-schema.md:634`**

A catalog that needs a framework's default — *"an unspecified `@KafkaListener`
concurrency is 1"* — carries the number typed in from documentation. W4 made the
real value readable: `AnnotationDefault` (JVMS 4.7.22) is now extracted and
declared as the `annotation_default` capability. **Nothing reads it.**
`verify: grep -rn "annotation_default" src/sextant/application/resolve/ | wc -l`

**Why it is Major rather than tidy-up.** A hardcoded default is a prediction
about a framework at a version nobody measured, which GUIDELINES §8.1 forbids
for exactly this reason: when a framework changes a default in a new release,
every row derived from it is **silently wrong** — no gap, no open question, no
signal. The jar states the truth and we ignore it.

**Not a catalog edit, which is why it is its own item.** There is no vocabulary
for it: a catalog cannot say "take this element's declared default". That is
catalog-grammar work in the resolve engines. And `D02:634` currently states the
rule as *"a declared default is not written into the class file, so …"* — a
sentence **W4 made false** — so the amendment lands with the grammar.

**Closes by** a catalog reading `annotation_default` for at least one element
that is hardcoded today, D02 §2 gaining the vocabulary, and `D02:634` corrected.
**Falsified by** measuring that no shipped catalog actually hardcodes a default
an annotation declares — in which case the capability has no consumer and the
question becomes whether to keep it.

### OI-45 — nesting is still derived by splitting a class name on `$` (W4b)
**Major · found 2026-09-07 by code review of W4 · `src/sextant/domain/symbols.py:69`,
`src/sextant/application/resolve/shapes/identity_calls.py:72`**

`outer_type_of` finds a nested type's enclosing type by splitting its name at the
first `$`. W4 made the class file's own statement available — `InnerClasses` and
`EnclosingMethod`, declared as the `enclosing_class` capability — and the split
is still what runs.

**Two things the split gets wrong.** `$` is legal in a Java identifier, so a
top-level class genuinely named `Foo$Bar` is reported as nested inside `Foo`,
which does not exist. And the split can only ever name a TYPE: for an anonymous
class it cannot reach the enclosing METHOD, which the class file states and
which W4 demonstrated reading (`BillingRestTemplate$1` →
`BillingRestTemplate#batchSettlements(sig_a3660822).`).

**Not a swap, which is why it is its own item.** The two do not answer the same
question: `outer_type_of("A$B$C#")` returns `A#`, the TOP-LEVEL type, while the
fact gives `A$B#`, the immediate encloser — reaching top-level is a walk of
repeated joins. And `outer_type_of` lives in `domain/`, which the import-linter
layering contract forbids from querying the workspace, so the consumer
(`identity_calls`) has to do the join and the domain helper has to lose its
guessing half.

**Closes by** `identity_calls` reading the `enclosing` fact, with `outer_type_of`
either deleted or reduced to a string helper nothing derives nesting from.
**Falsified by** the `$` split being provably correct for every symbol the one
consumer sees — it reads gRPC generated classes, where the shape is regular — in
which case this is a stated boundary rather than a defect.

### OI-46 — `type_parameters` is read, declared, and read by nothing (W5)
**Minor · found 2026-09-07 by code review of W5 · `src/sextant/domain/facts.py`,
`extractor-jvm/.../Capabilities.java`, `docs/components/M03-scanner.md`**

W5 reads the formal type parameters a class or method declares — name, bounds,
declaration order — and declares the `type_parameters` capability so a catalog
can require it. **Nothing requires it.**
`verify: grep -rn "type_parameters" src/sextant/catalogs/ src/sextant/application/ | wc -l`

**This is the legitimate half of the design's §2.3 distinction**, not the defect:
*"read, no consumer yet"* — a fact available to a future tier — as against
*"declared, never read"*, which is an attribute the scanner ignores. The plan
names the consumer: **W25**, generic substitution, which cannot bind `T` without
knowing what declared it. It is filed because the previous commit set that
precedent for W4's two (OI-44, OI-45) and a foundation item's missing consumer
should be a row in this register rather than a sentence in a code comment.

**Closes by** W25 reading it. **Falsified by** W25 landing without needing it, in
which case the question is whether to keep emitting it at all.

### OI-47 — `_is_bridge` guessed structurally when the fact already stated the answer
**CLOSED 2026-09-07 · `src/sextant/application/resolve/effective_annotations.py`**

**This entry's own account of the consequence was wrong, and measuring it is
what found the real defect.** As filed, it said reading `modifiers.synthetic`
would recover the mappings finding I1 loses. It would have recovered nothing: a
probe over the real function showed the bridge excluded either way, and the real
override unable to resolve regardless, because the ancestor lookup joins by name
AND descriptor and a covariant override's descriptor is not its ancestor's.

**The actual cause.** The bridge is the only method that can resolve — and it is
the wrong target, because it names a method nobody wrote. Nothing carried the
mapping across to the real one. Measured, both directions were wrong:

| Bridge differs from the real method in | Structural rule saw it? | Shipped result |
|---|---|---|
| return type (covariant override) | yes | both excluded — **mapping lost** |
| parameter types (generic interface) | **no** | row published **naming the bridge** |

The second was a fabrication, not an under-report: a class implementing
`Api<String>` published its handler as `handle(Object)`, javac's forwarder.

**Fixed** by reading `modifiers.synthetic` (D00 §5a; `ACC_BRIDGE` folded in) and
treating a bridge as EVIDENCE rather than a target — the resolved mapping is
carried to the same-class, same-name, same-ARITY, non-synthetic method it
forwards to. Exactly one, or nothing (§8). The structural rule stays as the
fallback where nothing was reported about a method.

**Proved end to end, on a compiled fixture, because the first attempt was not.**
That attempt added `modifiers` to the `method_declarations` query and stopped
there: `annotation_driven._method_declaration_rows` is the only producer of
these rows and rebuilt them without it, so every real run still fell back to the
structural rule while every assertion about the fix passed — they hand-build
their own rows. The tell was already in the repository: `test_pipeline` asserted
`GET /api/orders/{id}` ABSENT from the fixture, and that assertion did not
budge. It derives now, its handler naming `OrdersApiController#find(sig_95a78dff)`
— the covariant override, never the bridge (`sig_4cb6f523`) — and the fixture's
endpoint count moves 122 to 123 with nothing else changing.

**Two boundaries remain, both measured.** Two ancestors whose mappings DIFFER
still derive nothing (identical ones now derive one row). And a bridge forwarding
to a method its class INHERITS rather than declares resolves nothing: the arity
guard refuses an unrelated same-named sibling there, which is the §8 direction —
`class Sub extends Base implements IGet<String>` carrying an unrelated `get(int)`
would otherwise have taken the mapping.

**What did NOT change: finding I1's outcome.** A class overriding one method
against two mapped ancestors grows two bridges that redirect to one method, and
still derives nothing — now because two ancestors give one method two different
answers and this pass does not read the framework's own annotation search order,
which is the §8 rule, rather than because every bridge was discarded. Closing
that is DR-6 work (mirror the framework's search exactly), not this.

**Lesson recorded (§13.8).** An open-issue entry asserted a consequence nobody
measured, and it was believed for two waves. The entry's `verify:` line proved
the CAUSE and not the EFFECT. A row claiming "fixing X recovers Y" needs a probe
that shows Y actually appearing.

### OI-48 — Spring's spelling of a package-level nullability scope was undeclared
**CLOSED 2026-09-07 · `src/sextant/catalogs/shape-models/json.yml`,
`fixtures/orders-service/src/main/java/com/acme/orders/`**

**As first filed, this entry's premise was wrong, and correcting it is most of the
value.** It said no shipped catalog declares a `nullability` block. They all do —
42 of them name `shape_model: json`, and that model declares the nullable and
not-null annotation lists (JSpecify, Spring, javax, jakarta, JetBrains) and a
`@NullMarked` scope. The mistake was grepping `src/sextant/catalogs/*.yml` for
`nullability:` and concluding from its absence, without looking for the indirection
D02 §1b describes — the same "asserted without measuring" this branch has been
correcting all week.

**What was actually missing: Spring's spelling of the scope.** JSpecify's
`@NullMarked` was declared; `org.springframework.lang.NonNullApi` and
`NonNullFields` were not. Spring is the dominant framework this reads, and it
declares package-level nullability in its own vocabulary — measured on spring-web
6.1.6, **58** `package-info` classes carrying both, and `HttpHeaders` declaring 68
fields of which **zero** carry an annotation of their own, because the entire point
of a scope is that you annotate the exceptions rather than the rule.

**And nothing exercised the rule end to end.** `ScopedRequest` — a fixture built to
demonstrate exactly this, in a package called `scoped` — was referenced by NOTHING,
so no endpoint rooted it, so `derive_shapes` never expanded it and the scope ran
only in a hand-built unit test with an invented catalog. The fixture could not see
the thing it existed for, which is the RUNBOOK entry on fixtures that cannot see
their own defect, reached a third time.

**Fixed** by declaring Spring's two scope annotations, making `ScopedRequest` a
request body (`POST /v1/orders/scoped`), and adding `com/acme/orders/springscoped/`
— a package declaring itself non-null in Spring's spelling, reached through the
payload graph rather than a second endpoint. Measured after:

```
ScopedRequest#code        nullable = False   (JSpecify @NullMarked)
SpringScopedDetail#label  nullable = False   (Spring @NonNullApi/@NonNullFields)
```

Removing the two Spring entries puts `label` back to `nullable = True`, so they are
load-bearing rather than decorative.

**Left open deliberately:** JSpecify's `@NullUnmarked`, which re-enables
nullability inside a marked scope, has no `means:` value to declare —
`_SCOPE_MEANINGS` holds one meaning, `not_null_by_default`. A codebase using it
would read as non-null where it says otherwise. Filed as OI-50.

### OI-49 — twelve W7 fields are read and nothing reads them back
**Minor · found 2026-09-07 by code review of W7 · `src/sextant/domain/facts.py`,
`extractor-jvm/.../ClassScanner.java`**

Counted across `src/`, excluding the declarations themselves, the readers are:

| field | readers |
|---|---|
| `nest_host`, `nest_members`, `unread_attributes` | 0 |
| `permits`, `signature.throws` | 0 |
| `modifiers.abstract`, `varargs`, `final`, `native`, `synchronized`, `volatile`, `deprecated` | 0 |

Every apparent hit is prose in a docstring or a SQL comment. The only W7 output
with a live consumer is `construct_kind: annotation`, through `interface_symbols`.

**The rule was applied to three items and not to twelve.** `Module`,
`LocalVariableTypeTable` and class-level type annotations were dropped for having
no consumer; these were kept on justifications that are capability-shaped —
*"`varargs` unblocks capability 9.15"*, *"`abstract` tells a `default` method from
a declared one"* — which is the same "somebody could want this" argument the rule
exists to refuse. §2.3's "read, no consumer yet" is legitimate; asserting a
consumer that does not exist is not, and the CHANGELOG entries for W7 read as
though these were delivered capabilities.

**And no capability string was declared for any of them.** W5 and W6 each added
one (`type_parameters`, `line_numbers`, `local_variable_names`, `source_file`);
W7 added none, so `--capabilities` returns what it did before the wave. A catalog
cannot `requires:` any of this even once a consumer appears — which is exactly the
gap E3 was raised to close for W4.

**Closes by** either a consumer for each, or a capability name plus a row in W8's
ledger marking it read-with-no-consumer, or removal. **Falsified by** finding a
reader this count missed — the count is a grep and greps under-report.

**Not proposed for removal here.** Several are one line and obviously correct, and
`varargs` in particular is the recorded blocker for capability 9.15. What is wrong
is the claim, not the code.

### OI-50 — a scope can only be turned on, never off
**Minor · found 2026-09-07 while closing OI-48 ·
`src/sextant/application/resolve/shapes/expansion.py` (`_SCOPE_MEANINGS`)**

D02 §2e's scope vocabulary has exactly one meaning, `not_null_by_default`, so a
catalog can say "this package is non-null" and cannot say the opposite. JSpecify
ships `@NullUnmarked` precisely to re-open a nested scope inside a marked one, and
Spring has no equivalent.

**Consequence:** a package or class marked `@NullUnmarked` inside a `@NullMarked`
parent reads as non-null, which is the WRONG direction — a consumer told a field
cannot be null when the author said it can. Sextant does not declare
`@NullUnmarked` at all today, so the current answer for such a package is the
permissive default and therefore accidentally right; the defect appears the moment
someone adds it to the list without adding the meaning.

**Closes by** `_SCOPE_MEANINGS` gaining `nullable_by_default` and `@NullUnmarked`
declared. (The other half this entry used to ask for — longest matching prefix
rather than any match — already shipped in `_scope_nullable`, and describing
shipped work as remaining is what made this entry look bigger than it is.)
**Falsified by** measuring that no codebase Sextant reads nests scopes — which
JSpecify's own design contradicts.

### OI-51 — a nested type's own access modifier is read from nowhere
**Minor · found 2026-09-08 in the W8 review ·
`extractor-jvm/.../ClassScanner.java` (`visitInnerClass`)**

A `private` or `protected` nested type states that modifier in ONE place: the
`InnerClasses` table (JVMS 4.7.6). The class file's own access word cannot carry
it — a private nested class is written package-private there, a protected one is
written public — so `modifiers` and `visibility` for every nested type are the
outer approximation rather than what the source said.

The field that held it (`nestedAccess`) was removed rather than left unread, because
both attempts to consume it were wrong in opposite directions: read as VISIBILITY it
flipped protected nested types to `other` (the class file says public), and read as
the CONSTRUCT KIND it reported every nested record as `class` (that table has no
`Record` attribute for ASM to synthesise `ACC_RECORD` from — 1,262 of 1,739 records
in the local dependency cache). Two wrong consumers is a signal that the right one
has to be chosen deliberately, not that the data is worthless.

**Consequence:** measured over javac 21 output, a `private record Inner(int y)`
reports `visibility: other` and no `private` modifier — the same as a
package-private one. Nothing downstream distinguishes them today, which is why
this is Minor rather than Major.

**Closes by** `visitInnerClass` reading `access` into a field that feeds
`modifiers` ONLY for the nesting modifiers (`ACC_PRIVATE`, `ACC_PROTECTED`,
`ACC_STATIC`), never the whole word, with a fixture per modifier. **Falsified by**
finding a consumer that already needs a nested type's declared visibility, which
would make this Major instead.

### OI-52 — the ledger's `jvms` section numbers and 18 of its access flags resolve against nothing
**Minor · found 2026-09-08 in the W8 review ·
`extractor-jvm/.../AttributeLedger.java`, `AttributeLedgerTest.java`**

Two claims in the ledger are checked by nothing, and both are the same shape as the
defect the ledger exists to catch — a value written down that no test can falsify.

* `Entry::jvms` (the section number, `"4.7.30"`) is read by no test and by no
  caller. `RuntimeInvisibleTypeAnnotations` carried `4.7.20` — its neighbour's
  number, not its own `4.7.21` — from the day it was written until this review.
  It is corrected now; nothing stops the next one.
* Every `ATTRIBUTES` entry marked read has its reader resolved against the
  scanner's source (`readerExists`). The 18 read `ACCESS_FLAGS` entries do not:
  their `evidence` names a FACT KEY (`modifiers.varargs`, `construct_kind`) and
  no test checks that the key is one the scanner emits. A flag whose writer was
  deleted would still read as read.

**Consequence:** neither is wrong today — both were checked by hand during this
review — but "checked by hand once" is the state §2.3's ledger was built to
replace.

**Closes by** a test resolving each `jvms` value against JVMS 4.7's own numbering
(the list is already in `every_attribute_jvms_defines_is_in_the_ledger_exactly_once`,
keyed by name; pairing it with the number costs one column), and a test resolving
each read flag's `evidence` against the fact keys the scanner actually writes —
which the fixture fact files already enumerate. **Falsified by** showing the fact
keys are not enumerable from the emitted facts, which the existing fixture-based
assertions contradict.

### OI-53 — 45 catalog conversion sites name no file and no key when they refuse
**Minor · found 2026-09-08 in the W9/W10 review · re-measured after W9 ·
`src/sextant/application/resolve/` (14 files)**

`domain/symbols.type_descriptor` now REFUSES a non-string outright rather than
stringifying it — which is what turned a silent `"['a/B']#"` into a loud failure.
The refusal is loud but anonymous: it names the offending value's type and neither
the catalog file nor the key. `catalog_symbols` takes a `where` string and says both.

**Measured, not estimated.** 48 call sites across 15 files convert a catalog type
name directly; 3 of them are `rooting.py`'s own, inside `catalog_symbols`, leaving
**45 direct sites in 14 files**. (An earlier draft of this entry said "20 sites"
from memory and listed keys rather than counting them — the mistake §8.1 rule 1
names. W9 then routed 19 keys through `catalog_symbols`, which is why the count
moved from 64 to 45 rather than staying put.)

**These are not the §3.1 keys.** Every one of the 21 that holds a type name is
widened and named. What remains reads keys that are single-valued by design — a
wrapper's `type`, a `known_types` entry's `type`, `channel_via`'s `owner`, a
combinator step's `owner`, `parse_binding`'s hierarchy names.

**Consequence:** none to the derived facts. A list written at any of these is
refused either way; the cost is what a reader holding 56 catalogs is told.

**Closes by**, for each file below, either routing its sites through
`catalog_symbols` with a `where` string or recording why that key's refusal needs
no file name. The allowlist SHRINKS and never grows (§8.3); a new entry is a review
finding, and the counts are what a check compares against:

| file | direct sites |
|---|---|
| `resolve/engines/combinator.py` | 7 |
| `resolve/shapes/expansion.py` | 6 |
| `resolve/engines/annotation_driven.py` | 6 |
| `resolve/engines/single_call.py` | 5 |
| `resolve/engines/error_advice.py` | 4 |
| `resolve/engines/fluent.py` | 4 |
| `resolve/shapes/parse_binding.py` | 3 |
| `resolve/shapes/arguments.py` | 2 |
| `resolve/shapes/contracts.py` | 2 |
| `resolve/engines/supertype_dispatch.py` | 2 |
| `resolve/protocol_hint.py` | 1 |
| `resolve/shapes/identity_calls.py` | 1 |
| `resolve/engines/derived_resource.py` | 1 |
| `resolve/engines/interface_implementation.py` | 1 |

**Falsified by** finding that one of these keys is already list-valued in a shipped
catalog, which would make it a live defect rather than a message-quality one.

### OI-54 — `identity_marker` and `supertype_marker` were named as type-name sites and are not
**Minor · found 2026-09-08 while delivering W9 ·
`docs/superpowers/specs/2026-09-06-java-kotlin-completeness-design.md` §3.1**

F2 §3.1 lists 21 scalar sites to widen. Nineteen hold a dotted type name and are
widened (`matches.steps[].owner` is widened too and is a twentieth key the design
did not list). The other two do not hold a type name at all: each is a mapping of CALL
specs, and the type sits one level below.

```yaml
identity_marker:
  service_name_call: { owner: io.grpc.ServiceDescriptor, method: newBuilder }
supertype_marker:
  service_name_call: { owner: io.grpc.ServiceDescriptor, method: newBuilder }
  method_name_call:  { owner: io.grpc.MethodDescriptor,  method: generateFullMethodName }
```

Widening the named key would mean accepting a list of MAPPINGS, which is a
different feature and not what §3.1 describes. The widenable site is the nested
`owner`, one level down, in `grpc-net-devh.yml` and `grpc-java.yml` — the only two
catalogs that declare either key.

**Consequence:** none. gRPC's descriptor classes have one spelling each, so no
alternate is wanted today. The defect is in the design's own list, which is why
`docs/components/D02-catalog-schema.md` states twenty — nineteen of §3.1's plus one it
did not list — and says why, rather than
matching the design's count and being wrong.

**Closes by** correcting F2 §3.1's list to name `identity_marker.*.owner` and
`supertype_marker.*.owner`, or recording that a nested call spec's owner is out of
scope. **Falsified by** a gRPC descriptor class shipping under a second name, which
would make this a live gap.

### OI-55 — `media_values.owner` is widened and no shipped catalog declares it
**Minor · found 2026-09-08 in the W9 review ·
`src/sextant/application/resolve/engines/combinator.py`**

`test_every_widened_key_a_shipped_catalog_declares_honours_a_second_spelling`
drives each widened key by rewriting it, in every shipped catalog, from `X` to
`[<an absent name>, X]` and asserting the fixture's endpoint rows are unchanged.
Measured: 19 of the 20 keys in `endpoints._WIDENED_KEYS` are declared by at least
one shipped catalog and are therefore driven. **`media_values.owner` is declared
by none**, so nothing reaches `combinator.py`'s `media_owners` membership test.

That test is the only mechanism covering the widening — before it, mutating
`catalog_symbols` to return only its first element failed 4 tests out of 2,407,
and two of those were unit tests of `catalog_symbols` itself.

**Consequence:** if `media_owners` were reverted to a single comparison, nothing
would fail. The key has no consumer in the shipped estate either, so no derived
fact is wrong today.

**Closes by** a catalog declaring `media_values.owner` (which would make it
covered automatically, the test reading `_WIDENED_KEYS` rather than a list of its
own), or a hand-built `combinator` catalog in the suite that declares one.
**Falsified by** finding a shipped catalog that does declare it, which would mean
the measurement above is wrong.

### OI-56 — `scheduled_work` pairs `annotation` and `container` as independent lists
**Minor · found 2026-09-08 in the W9 review ·
`src/sextant/application/resolve/engines/scheduled_work.py`**

A repeatable annotation and the container javac folds its repeats into are ONE
declaration read two ways: `@Scheduled` and `@Schedules`. §3.1 widened both keys
independently, so `annotations` and `containers` are now two unrelated tuples and
a container from one list may fold an entry named in the other.

Under §3.1's own reading — a list is several spellings of ONE thing — every
element of each list denotes the same annotation, so a cross-match is not wrong.
It is only unenforced: a catalog author writing `annotation: [A, B]` and
`container: [As, Bs]` might reasonably expect `As` to fold only `A`.

**Consequence:** none today. `spring-scheduling.yml` is the only catalog
declaring either key and it writes one scalar at each.

**Closes by** a paired grammar (`repeatable: [{annotation, container}, ...]`) if a
second framework ever needs one, or by a comment stating that the two lists are
deliberately independent. **Falsified by** a framework whose two spellings fold
into DIFFERENT containers, which would make the cross-match a live defect.

### OI-57 — three boundaries were justified by "this key is single-valued", and W9 widened them all
**Minor · found 2026-09-08 in the W11/W12 review ·
`docs/COVERAGE.md`, `src/sextant/catalogs/`**

W9 widened twenty-one type-name keys from a scalar to "a name or a list of them".
Several recorded boundaries existed *because* a key was scalar, and none of them
was revisited when that stopped being true. One is now closed and one remains:

* **`javax.websocket`** was detection-only because `mapping.prefix_annotation` was
  single-valued. Closed in W12's second pass — a pure catalog edit once the reason
  was gone, and the annotations were measured before the names were added.
* **`@SendToUser` is not read as a reply destination**, because `reply.annotation`
  was single-valued. Still open. It is a Spring annotation and not a javax/jakarta
  twin, so it was outside W12's scope; adding it is a catalog edit plus a
  measurement of what `@SendToUser` declares against `@SendTo`.
* **A class-level array-valued prefix contributes element 0 only.** NOT the same
  shape and not unblocked: that is one annotation with several VALUES, which §3.1
  says nothing about — a list of alternate NAMES is a different thing from a list
  of addresses. Recorded here so the next reader does not group it with the other
  two.

**Consequence:** none wrong today; each boundary describes behaviour accurately.
What was wrong is the stated reason, which is what a reader uses to decide whether
the work is cheap. The websocket one cost a wave: W11's sweep would have found it
had the sweep read values rather than prose.

**Closes by** measuring `@SendToUser` and adding it to `spring-stomp.yml`'s `reply`
block, or recording a reason that is still true. **Falsified by** finding a fourth
boundary of this shape, which would make it Major — a mechanism, not a list.

### OI-58 — `resolved_config.parquet` differed between two runs, once, and I could not reproduce it
**Major · found 2026-09-08 during the W12 gate ·
`src/sextant/storage/duckdb/workspace.py` (export), `tests/e2e/test_vertical_slice.py`**

`test_output_is_byte_identical_when_the_pipeline_runs_twice` failed one full-gate
run. The differing file was `graph/resolved_config.parquet` (and at least one more
the assertion truncated); 265 other files were identical. **It has not reproduced
since**, and it is recorded rather than closed because a green re-run is not
evidence that a determinism defect is absent — it is one sample.

**What was measured, and what it rules out:**

| tried | result |
|---|---|
| the test alone | passes |
| the two-run comparison in a loop, 6 attempts | byte-identical every time |
| the whole `tests/e2e` directory, 6 consecutive runs | 26 passed each time |
| the whole suite again after the failure | 2,411 passed |
| `PYTHONHASHSEED` 0-5 on the test | passes at every seed — and the two runs share a process, so a per-process seed cannot differ between them anyway |
| is the export's `ORDER BY environment, key` a TOTAL order? | yes — 0 duplicate `(environment, key)` pairs across all 26 rows, so row sequence is fixed |
| does DuckDB's thread count change parquet BYTES for an ordered query? | no — `threads` 1/2/4/8 over a 2,000-row table shaped like this one produced one identical digest |

So it is not hash ordering, not row ordering, and not the parquet writer reacting to
parallelism — the three explanations that fit "only under full-suite load". The
redaction map the export left-joins (`redacted_config_values`) is built by a
`SELECT DISTINCT key, value` with no `ORDER BY`, which makes the STAGED table's row
order unstable; that should not reach the output, since the join is keyed on a pair
`DISTINCT` makes unique, but it is the only unordered read on this path and is the
first place to look next.

**Consequence if real:** two runs of the same analysis over the same input produce
bundles that differ byte for byte, which NFR-1 exists to forbid and which a
consumer diffing two bundles would read as a change in the module.

**Closes by** a reproduction — run the full suite in a loop and capture the two
workspaces when it next fails, then diff the parquet CONTENT (not bytes) to see
whether a value or only the encoding moved. **Falsified by** showing the one
observed failure was environmental (a truncated write, a full disk), which the
captured workspaces would also settle.

### OI-59 — a measurement bounded to one version, read as if it were general
**Minor · found 2026-09-08 in the W14 review · this file, and
`scripts/probes/w14_listener_registration.md`**

This entry originally said `spring-sqs.yml` declares a `prefix_annotation` that can
never match, because `@SqsListener` is `@Target(METHOD)`. That is true at
spring-cloud-aws-sqs **3.1.1** and false at **4.1.1**, which
`scripts/probes/cp17_containers_and_class_level.md` had already measured (rows
2e/2f) and which `spring-sqs.yml`'s own `measured:` block names. The key is live,
and the catalog now declares `class_level: sibling` because of it.

**The entry is kept, rewritten, because the mistake is the reusable part.** W14's
sweep read one version, its version-scope paragraph correctly bounded the reading
to 3.1.1 — and then three sentences of its verdict, the ones W15 was going to
consume, were written unbounded: "the question does not arise for SQS", "a rule
encoded for SQS would be a rule with no reachable case". A bounded measurement
narrated as a general fact is how a §5.4 scope statement stops protecting anything,
and it nearly shipped a catalog that composes two SQS registrations into one
address at 4.1.1.

**Consequence:** none now — the verdict is corrected and the conjunct declared.
The residual is that no mechanism connects a probe's verdict to the versions its
own scope paragraph names.

**Closes by** a check that a probe's Verdict does not assert about an artifact at
versions outside its `## Observations` — which `tests/architecture/test_probe_provenance.py`
already has the pieces for, since it parses both. **Falsified by** showing the
existing scope test already catches this, which it does not: it compares column
headers to the scope paragraph, never the prose to either.

### OI-60 — the Stream candidate set counts methods where the framework counts beans
**Major · found 2026-09-08 in the W13 review ·
`src/sextant/application/resolve/engines/config_join.py` (`_candidates`)**

`_candidates` keeps every declared method whose return type is `Function`,
`Consumer` or `Supplier`. There is no `@Bean`, `@Component` or visibility conjunct,
so an ordinary helper method that happens to return a functional interface is a
candidate. `docs/COVERAGE.md` has recorded that over-count since `A-C5`.

W13 made the over-count cost something new. The cardinality rule (`unselected_binds:
sole`) mirrors the framework's "exactly one eligible function binds by default" — but
the framework counts REGISTERED BEANS and this counts DECLARED METHODS. Measured: a
module with one real `Consumer` bean and one helper returning `Function`, with no
`spring.cloud.function.definition`, derives **no row** where the framework binds the
bean.

**The first version of the rule made that loss silent**, on the reasoning that the
framework binds nothing so no row is the complete answer — reasoning that needed the
two counts to be equal. It now files one `unselected_binding` question per candidate,
so the loss is visible; the loss itself remains.

**Consequence:** a single-function Spring Cloud Stream application that also declares
any function-shaped helper method loses its real binding from the export, with
questions in its place. `spring.cloud.function.definition` is optional exactly for
single-function applications, so this is a common shape.

**Closes by** measuring which registration forms Spring Cloud Function actually binds
— `@Bean`, `@Component`, a programmatic `FunctionRegistry` entry — and adding the
conjunct, at which point the count here becomes the count the framework takes and the
question stops being filed for a module that has one real bean. §8.1 forbids inventing
it. **Falsified by** showing the framework binds any function-shaped method regardless
of registration, which would make the current count right and this entry wrong.

### OI-61 — `detect.satisfied_by` is unmeasured beyond the one annotation that uses it

**Found by** the W16 review, extended by the W17 fix round.

`detect.satisfied_by` is a new catalog key with one user:
`spring-rsocket.yml` names `@ConnectMapping`. The soundness of the key rests on a claim
about that annotation — that exactly one framework defines it — and W16's probe measured
that claim for `@ConnectMapping` and for nothing else. There is no audit that a value
placed in this key is actually sole-claim: a future author who adds an annotation two
catalogs name would silently un-gate a catalog, which is the failure `detect.required`
exists to prevent, arriving through the door built to bypass it.

**Consequence today: none.** The one shipped value is measured. The exposure is the next
one.

**Closes by** an offline audit asserting that no `detect.satisfied_by` value appears in
more than one shipped catalog's `matches` — the same shape
`test_catalog_measurement_coverage.py` already applies to `measured:` rows. **Falsified
by** a framework pair that legitimately shares a sole-claim annotation, which would make
the audit wrong rather than the key.

### OI-62 — the `handler_protocol` question is filed per class, and a class may serve both wires

**Found by** the W16 review's finding 3, while fixing it.

Two catalogs asking `handler_protocol` about one class are now folded into one question
carrying both wires as candidates (`resolve/service_identity.py`'s `_merged`). That is
right for the case the fold was written for — the build settles neither framework, so
one of the two is the answer. It is not right for a class that genuinely serves both:
§3.6 records that case explicitly ("Both present → two rows. Both handlers scan the same
beans; the method really does serve both. This is a correct answer, not an ambiguity"),
and a reader answering the merged question has no way to say "both".

**Consequence:** only where the build settles NEITHER framework, since a build that names
both derives two rows and files no question at all. So the ambiguous-and-genuinely-both
case cannot be expressed, and a reader would answer it by picking one.

**Closes by** deciding whether `handler_protocol`'s answer vocabulary admits "both" —
which is a question about the verdict schema (D01 §7), not about this fold. **Falsified
by** showing a class serving both wires always has both coordinates recorded, which would
make the case unreachable.

### OI-63 — `displayName` is declared by every catalog and read by nothing

**Found by** the W17 review (m4), while checking whether renaming `spring-mvc.yml`'s
`displayName` had any shipped effect.

`grep displayName` across `src/`, `scripts/` and `tests/` finds the loader and no
consumer. All 57 catalogs declare one. GUIDELINES §2 — a capability with no consumer is
half-shipped — applies to catalog keys as much as to scanner capabilities, and W17's own
finding was a reader predicting behaviour from an unread key.

**Consequence:** none to output. The cost is to readers: a name that looks like it
reaches an export does not, so it can drift arbitrarily far from what the catalog derives
without any gate noticing. `spring-mvc.yml`'s said "server-rendered controllers" while
deriving reactive WebFlux routes.

**Closes by** either giving it a consumer (the rendered document names catalogs by id
today) or removing it from all 57 files and from D02. **Falsified by** finding a consumer
this grep missed.

### OI-64 — a `Subscriber` built and never started derives a live inbound endpoint · **CLOSED**

**Found by** W18, while implementing F2 §3.9's other half.

`google-pubsub-subscriber.yml` derives an inbound row from
`Subscriber.newBuilder(subscription, receiver)`. That call is CONSTRUCTION, and
construction subscribes to nothing: the messages arrive only once something calls
`startAsync()`, or once Spring starts a `Subscriber` returned from a `@Bean` method.
GUIDELINES §8.6 states the rule and names this catalog as the example that breaks it.

**The design's description of the defect does not match the file.** §8.6 and F2 §3.9
both say the catalog "named `.startAsync()` as a required conjunct and never read
it". It names no such conjunct, and its comment states the opposite position
outright — "the registration is the evidence, so this style needs no
execute-terminal". The over-report is real; the mechanism recorded for it is not, and
W18 declined to fix a conjunct that is not there.

**Consequence, and it is not hypothetical — MEASURED after this entry was first
written, which is what it should have opened with.** Our OWN acceptance fixture is an
instance. `fixtures/orders-service/.../raw/RawPubSubSubscribers.java` builds two
`Subscriber`s — `raw-notify` and `raw-notify-lambda` — and starts NEITHER: there is no
`startAsync()` call anywhere in the fixture, and both are plain methods rather than
`@Bean` methods, so no framework rule starts them either. Both are published today as
live inbound `pubsub` endpoints, and `tests/application/test_interface_engine.py`
asserts that they are. **The suite pins the fabrication as correct behaviour**, which
is why nothing has flagged it.

That makes this an over-report rather than an under-report, and this project ranks
those the other way round from most: ARCHITECTURE's "the failure mode is fabrication,
not imprecision", and GUIDELINES §8's *unresolved is an answer, invention is not*. A
missing row is silence; these two rows are a claim that a wire exists. And `protocol`
is the column DR-5 links on, so a fabricated inbound `pubsub` endpoint can merge into
another consumer's graph — the same shape as W16's wrong-protocol RSocket rows.

**Severity: this is a Major, and the first draft of this entry did not say so because
it treated the defect as possible rather than checking whether it had already
happened.** That is §8.1 — measure, never predict — applied to our own output instead
of to a framework.

**CLOSED.** `registration.started_by` (D02 §1b-i) declares the calls that must follow a
registration before it is a boundary; `google-pubsub-subscriber.yml` declares
`Subscriber$Builder.build` then `Subscriber.startAsync`. Because chain reconstruction is
within-method only, there are three outcomes rather than two: started here → a row;
returned to a caller → a `registration_activation` question, since a factory's caller may
start it and answering "no boundary" would swap the fabrication for a silent false
negative; built and dropped → silence, because nothing can start it. The fixture now
models all three and a test pins each, every one verified to fail with the conjunct
removed.

**The `@Bean` half of the planned fix was DROPPED, because it was measured and is false.**
This entry, and GUIDELINES §8.6, both said a `@Bean` method returning a `Subscriber` is
started by Spring and that this was "a measured rule". Nobody had measured it.
`Subscriber` implements no Spring lifecycle interface anywhere in its hierarchy —
`AbstractApiService` implements `ApiService` and nothing else — and spring-cloud-gcp-pubsub
5.1.2 ships no `BeanPostProcessor` that would start one
(`scripts/probes/oi64_subscriber_activation.md`). Spring does not start arbitrary beans.
A `@Bean` returning a `Subscriber` is the same unstarted object as any other, and §8.6's
example is corrected in place. **Falsified by** measuring that
`Subscriber.newBuilder(...)` itself begins delivery, which the probe's section 2 answers
directly: it does not.

### OI-65 — nothing detects a release that moves `Subscriber.startAsync` out of the template

**Found by** the W18 review (MAJ-6), while correcting the §8.6 chain recorded for
`PubSubTemplate.subscribe`.

`spring-pubsub.yml`'s `subscribe` and `subscribeAndConvert` rows are boundaries because
of a two-link chain: the traced call, plus the measured rule that
`PubSubSubscriberTemplate.subscribe` calls `Subscriber.startAsync()` itself before
returning (`javap -c`, spring-cloud-gcp-pubsub 5.1.2, offset 26). That second link is a
claim about the library's INTERNALS, and it is the only thing separating these two rows
from the over-report recorded as `OI-64`.

**Nothing re-checks it.** `scripts/probes/w18_pubsub_inbound/run.sh` reads descriptors
and runs the derivation; it never opens `PubSubSubscriberTemplate`'s bytecode.
`cp10_catalog_descriptors` checks that a declared descriptor names a real method, which
would still pass. So a release that moved the start into the caller — a plausible change,
since it would let callers configure the subscriber before starting it — would turn both
rows into fabrications, and every gate in the tree would stay green.

**Consequence today: none.** The rule holds at 5.1.2, measured. The exposure is the next
version anyone measures against.

**Closes by** adding the instruction-sequence read to
`scripts/probes/w18_pubsub_inbound/sweep.py` — the shape
`scripts/probes/w17_webflux_controller/sweep.py` already uses for `isHandler`, aborting
when the expected call is absent — so that re-running the probe against a new version is
what answers the question. **Falsified by** showing the two rows would still be correct
with the start moved, which they would not be.

### OI-66 — `config_join` has no container vocabulary, so a repeated channel annotation drops

**Found by** the W19b review, while declaring `spring-integration`'s slice.

Measured at spring-integration-core 6.2.4: `@ServiceActivator` and
`@InboundChannelAdapter` — **both annotations `spring-integration.yml` reads** — are
`@Repeatable`, with containers `@ServiceActivators` and `@InboundChannelAdapters`. So
are `@Router`, `@Splitter`, `@Transformer`, `@Filter`, `@Aggregator`, `@BridgeFrom` and
`@BridgeTo`. Two `@ServiceActivator` annotations on one method compile to a single
`@ServiceActivators` container, and the individual annotations are not present on the
method at all.

`config_join` has no `container` word. `annotation_driven` does — `spring-jms`,
`spring-rabbit`, `spring-scheduling`, `spring-kafka` and `spring-pulsar` all declare one
— but `grep container src/sextant/application/resolve/engines/config_join.py` finds
nothing.

**Consequence:** a method carrying two of the same channel annotation contributes NO
`channel_destination` questions rather than two. This is the half of G-47 that reads
"and no containers", and W19b closed the other half (the annotation roster) without it.

**Closes by** giving `config_join` the same `container` conjunct `annotation_driven`
already has, and declaring it on the two rows this catalog reads. **Falsified by**
measuring that Spring Integration also writes the individual annotations alongside the
container, which would make today's read complete.

### OI-67 — a DGS fetcher declared on a superclass method registers, and we do not see it

**Found by** the W19b review, which falsified the mechanism first recorded for it.

Measured at graphql-dgs 8.7.1 and spring-core 6.1.6:
`DgsSchemaProvider$Companion$DgsBean` calls
`ReflectionUtils.getUniqueDeclaredMethods(clazz, USER_DECLARED_METHODS)`, and
`ReflectionUtils.doWithMethods` calls `Class.getSuperclass()` and
`Class.getInterfaces()`. So DGS enumerates the whole hierarchy's methods when it
registers fetchers. This analysis reads annotations where they are WRITTEN, so a
codebase with an abstract base fetcher and ten thin subclasses derives one fetcher's
worth of rows instead of ten, with nothing saying a row is missing. It is `OI-37`'s
shape in a third framework.

**The mechanism the gap analysis recorded is not this one, and does not work.** G-41
says `@DgsData` and `@DgsQuery` are `@Inherited`. They are — all five DGS annotations
are, which is three more than recorded — but `java.lang.annotation.Inherited` "has no
effect if the annotated type is used to annotate anything other than a class", and it
inherits from superclasses, never through methods. `@DgsData`, `@DgsQuery`,
`@DgsMutation` and `@DgsSubscription` all declare `@Target(METHOD)`, so on four of the
five that bit is inert. An earlier draft of `netflix-dgs.yml` reproduced the false
mechanism as though it had been measured.

**This changes the fix.** Resolving `@Inherited` through `type_hierarchy` — the
remediation that draft named — closes nothing here. What is needed is a superclass
METHOD walk: the annotations sit on methods the subclass does not declare at all.

**Closes by** that walk, over `type_hierarchy` (W22). **Falsified by** a DGS codebase
with no inheritance among its fetchers, for which today's rows are already complete.
