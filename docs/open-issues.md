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

Severity: **Critical** = publishes a wrong row a reader would act on ·
**Major** = wrong under a realistic input, or a silent drop · **Minor** = stale
prose or a latent shape with no live consequence.

---

## OPEN

### OI-2 — a DISABLED scheduled job is reported as live work
**Major · introduced 2026-09-06 by 2O Task 8 (`35fa4d5..4e51317`) · COVERAGE.md:1922**

`spring-scheduling.yml` treats no cron value as the framework's "never schedule
this" sentinel, because no probe has measured which value the framework so reads
and encoding one from memory is what §8.1 forbids. So a schedule the framework
will never run publishes a `scheduled_work` row saying it does.

**This is not the Actuator case.** A disable sentinel is not deployment-
overridable — it is a code fact we are misreading, so §8.2 does not excuse it.
The implementer chose correctly under "measure or do not encode", but the honest
close is a probe, and it is among the cheapest on the list.
**Closes by** one probe question and one catalog key. **Falsified by** a disabled
schedule appearing in an export.

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

### OI-5 — MicroProfile GraphQL publishes a wrong address
**Major · pre-existing (`A-Mi9`) · stated, not closed**

`microprofile-graphql.yml`'s `path_fallback: construct_name` is a prediction: MP
GraphQL likely strips a `get`/`is` prefix, so `@Query List<Order> getOrders()`
would be served as `orders` while we publish `getOrders`. **A wrong address, not
an under-report** — the highest-value item in the probe backlog.
**Closes by** a live SmallRye run.

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

### OI-10 — 26 shipped catalogs state no measured version at all
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

### OI-14 — capability 9.17 produces a fact nothing reads
**Minor · introduced 2026-09-06 by 2Q G1 · `docs/components/M03-scanner.md`, the
capability table**

`call_site.implementation` names the lambda body a `dynamic` site dispatches
into. **Nothing consumes it.** Its planned reader is 2Q's `G3` (cross-method
return propagation) and `G4` (the `call_edges` traversal), and neither exists —
G1 was scheduled ahead of both because the fact is what G3 consumes.

**This is the `detect.coordinates` shape, and it is entered here rather than
argued away.** §5.3's rule is to cite the CONSUMER, not the declaration; there
is no consumer to cite, so the honest record is a row saying so. It is graded
Minor rather than Major because the failure mode is silence, not a wrong value:
no output moves, the key is absent wherever no body is named, and an engine that
ignores it sees exactly the facts it saw before.

What makes it a debt rather than a neutral wait is M03's own rule — a capability
with no consumer is a half-shipped feature — and the fact that `lambda_body` is
now declared, so a catalog **can** require it and be told the scan provides it
while nothing in the pipeline acts on it.
**Closes by** G4's traversal following `implementation` into the body, with a
trace that reaches a terminal only reachable through a lambda. **Falsified by**
nothing today; it becomes falsifiable the moment a consumer exists.

**Amended 2026-09-06 by 2Q G3, and NOT closed by it.** The row named G3 and G4
jointly as its readers; G3 has now shipped and deliberately does not read this
key, so the remaining reader is G4 alone. An `invokedynamic`'s `result` is the
functional-interface INSTANCE the bootstrap builds, not anything the lambda body
hands back — the body runs later, elsewhere, if at all — so linking the body's
returns to that site's `result` would state that a `Supplier` call site produced
the supplier's value. `return_flow.py` excludes `dynamic` sites for exactly that
reason and says so. Following `implementation` INTO the body is a traversal
step, which is what this row's close condition already asked for.


### OI-16 — two dispatch rules will exist, and only one is designed
**Minor · introduced 2026-09-06 by 2Q G3 · `docs/components/M04-resolver.md` §4,
`docs/components/D01-graph-schema.md` §3, `src/sextant/application/resolve/return_flow.py`**

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
**Closes by** the designed pass landing and `return_flows` reading its
candidates instead of re-deriving them. **Falsified by** a call site where the
two tables list different candidates.

### OI-17 — an in-module override of a library-declared method is not linked
**Minor · introduced 2026-09-06 by 2Q G3 · `docs/COVERAGE.md` §7 ·
`src/sextant/application/resolve/return_flow.py`, `_callees`**

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

## CLOSED

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
