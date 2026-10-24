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

**Relationship to the other registers.** `docs/open-issues.md` OI-84 is
the triage of one audit and stays frozen as that audit's record.
`docs/open-issues.md` OI-83 holds one class — mechanisms documents
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

---

# GAPS — what Sextant does not yet read

**Read this section first when planning new work.** Everything below is a
CAPABILITY GAP rather than a defect: the code is correct as far as it goes, and
these are the places it does not go. They are separated from the defect register
beneath because they answer a different question — not *"what is broken"* but
*"what would make this more complete"*.

**Every figure here is measured against the framework's own jars** by
`scripts/probes/w19_catalog_surface/run.sh`, which reads each owner's declared
methods and cross-references the catalog as loaded. Re-run it rather than trusting
this table: a release that adds an addressable method widens a gap without
touching this file.

**Why this section exists.** `docs/COVERAGE.md` states nine of these as
"partially supported", and that word carries no magnitude — 0-of-20 and 19-of-20
read identically. A reader could not tell, from the coverage document, the
difference between a framework shape we mostly read and one we do not read at all.

---

## GAP-1 — functional routing's BUILDER form is unread, on both stacks · **0 of 20, twice**

`RouterFunctions$Builder` — `route().GET("/orders", handler).POST(…)` — is read by
NEITHER `spring-mvc-router` nor `spring-webflux-router`. Zero of its twenty methods
on each side.

**It is not an exotic shape.** It has been the reference documentation's
recommended Java form for functional routing since Spring 5.2. A module written
that way has its **entire routing surface absent from the export**, with nothing
saying so — the catalog matches nothing and a reader sees a service with no
inbound HTTP at all.

**Why it is not just a wider `entries` list.** `combinator`'s grammar is
argument-rooted (`RouterFunctions.route(predicate, handler)`) or body-linked
(`coRouter { }`). A builder is neither: the verb call sits on a RECEIVER returned
by an argument-less `route()`, and this grammar has no word for that. Closing it
is engine work plus a probe of which overload position carries the path.

**Closes by** a `combinator` rooting form for a receiver-chained builder.
**Falsified by** measuring that the builder form is rare in real Java codebases,
which would lower its priority without making the row wrong.

## GAP-2 — the linking tier does not exist · FR-8, M05, M06

Sextant reads that service A calls `POST /orders` and that service B serves
`POST /orders`, and **nothing joins those two facts**. FR-8 — *"matches each
outbound endpoint to the inbound endpoints it may reach"* — is unbuilt; `M05`
(sync) and `M06` (stitcher) are both `planned` in `docs/PROJECT.md`.

**The groundwork is present.** Outbound rows carry protocol, wire identity and
payload contracts; DR-5 already specifies the matching rule (protocol equality,
wire identity, directional payload compatibility). What is missing is the tier
that runs it across bundles.

~~**Nothing in the corpora demonstrates it either way.** All three pinned repositories
are single REST applications with genuinely zero outbound calls.
`examples/spring-petclinic-microservices` has nine modules and real cross-service
traffic, and has never been used for this.~~

**CORRECTED 2026-10-19 — both sentences were true when written and neither is now.** There
are six pinned corpora, three of them carry outbound calls, and
`examples/spring-petclinic-microservices` is cloned, built and pinned twice
(`petclinic-api-gateway`, `petclinic-genai-service`). The two sides of a real cross-service
call are both published and both `resolved`:

| | published |
|---|---|
| `genai` outbound | `POST /owners/{ownerId}/pets` · peer `customers-service` · resolved |
| `customers-service` inbound | `POST /owners/{ownerId}/pets` · `@PostMapping` · resolved |

A reader joins those by eye; nothing in Sextant joins them. **So the corpus blocker named
here is gone and the tier is what is missing** — which changes this entry from "unreachable"
to "the next thing between Spring Boot and end-to-end".

**One prerequisite, measured:** `OI-151`. `api-gateway` calls
`/pets/visits?petId={petId}` and `visits-service` serves `/pets/visits` with the parameter as
`endpoint_metadata`, so `DR-5`'s rule fails on the address for a call that is exact in the
code. The stitcher would miss it.

**Closes by** M05/M06. This is phase L work and was never a row in the Java/Kotlin
completeness plan, which is why finishing that plan did not produce it.

**BUILT 2026-10-20 — the REACTOR case only**, spec
`docs/superpowers/specs/2026-10-19-reactor-linking-design.md`, plan
`docs/superpowers/plans/2026-10-19-reactor-linking.md`. Eight decisions settled by the user;
`M00`, `M05`, `M06` and `D01` carry the amendments, each naming its decision.

**Measured through `sextant system analyze` on two real systems:**

| | participants | links | unmatched | uncalled |
|---|---|---|---|---|
| `spring-petclinic-microservices` | 8 | **23** | 0 | 36 |
| `mall-swarm` | 9 | **258** | 0 | 40 |

The link a reader wanted all along:

| From | Calls | Endpoint |
|---|---|---|
| `genai-service` POST `/owners/{ownerId}/pets` | `customers-service` | POST `/owners/{ownerId}/pets` |

Of those, 22 come from the outbound rows (13 endpoint, 9 participant) and the rest from the
gateway prefix join: `petclinic` 13, `mall-swarm` 245. **Zero narrowed on either system** —
`M06`'s claim that uniqueness needs no threshold, measured rather than reasoned. `apollo`
scores 0, which is decision 6 working: all ten of its outbound rows have an unread authority
or no address at all.

**What it leaves open, so this entry is not read as `FR-8` delivered:** no cross-repository
participants (`M05`, `system.yml`, `system.state.json`, staleness); no overlay or curation
(`M01`, `D03`, `proposals.yml`, human-asserted links); no structural compatibility (`M06`
step 3); no path-SHAPE matching; no external participants; and **no link for an address whose
authority went unread** (decision 6, refused — the reason it costs Apollo all ten of its
rows). `GAP-2` stays open until those land.

## GAP-3 — the async SQS client is read for one call · **1 of 28**

`SqsAsyncClient.sendMessage` derives since `G-43` (closed on CI run 34669970510):
`aws-sqs-sdk`'s `matches.terminal` names `SqsClient` and `SqsAsyncClient` together as
the builder chain's terminal owner. `SqsClient` itself is still **1 of 29**. What is
still outside, on both clients: the entire inbound direction, including
`receiveMessage`, and every batch form.

**Closes by** widening the slice, which is catalog data rather than engine work —
the request-object shape each of these takes is the same one `sendMessage` already
reads.

## GAP-4 — the messaging templates' receive halves: three of four read, SQS's not

Measured, read of declared (COVERAGE §3b):

| Owner | Read |
|---|---|
| `RabbitTemplate` | 4 of 88 |
| `JmsTemplate` | 5 of 49 |
| `SimpMessagingTemplate` | 3 of 14 |
| `SqsTemplate` | 1 of 12 |
| `PubSubTemplate` | 11 of 20 |

**The raw ratio overstates every row here and the probe says so.** Most of what a
template declares is configuration and lifecycle — `RabbitTemplate`'s 84 unread
include `setChannelTransacted` and its kin, which address no wire. `RabbitTemplate`'s
and `JmsTemplate`'s receive halves derive since `G-44`'s Tasks 1–2 (`371cfaf`,
`760c884`): the overloads that name the queue or destination at an argument, one
inbound row each. What is still outside: `SqsTemplate`'s receive half, where the
queue is named inside a `Consumer<SqsReceiveOptions>` lambda rather than at any
argument — the delivery register's `sqs-template-receive`, Category B — plus the
request/reply, batch and async forms on every template.

**Closes by** the receiver-chain read the combinator overload spec describes, for
SQS; the other three templates needed only a fixture each, and have one.

## GAP-5 — Spring Integration reads 7 of 11 channel annotations

`spring-integration` declares seven of the eleven channel-declaring annotations in
spring-integration-core 6.2.4 (COVERAGE §3b); `G-47` closed on CI run 34669970510
when `@Aggregator`, `@BridgeFrom`, `@BridgeTo`, `@Filter`, `@Router`, `@Splitter` and
`@Transformer` began deriving. What is still outside: `@Gateway`, `@MessagingGateway`,
`@Poller` and `@Publisher`, whose cost is bounded — this catalog files
`channel_destination` questions and mints no endpoint rows, so each under-reports a
question list rather than producing a wrong row.

**Closes by** widening the catalog to the remaining four, from the same enumeration.

## GAP-6 — Spring Data REST derives for JPA and MongoDB repositories, 7 of 28 contracts

`spring-data-rest` reads the base contracts plus `JpaRepository` and
`MongoRepository` (COVERAGE §3b); `G-45` closed on CI run 34669970510 when a Data
REST resource over MongoDB derived its route table. What is still outside: every
R2DBC, Cassandra, Elasticsearch and Neo4j repository contract, and every reactive,
coroutine and RxJava3 variant — `ReactiveMongoRepository` included — which derive
nothing.

**Closes by** enumerating each remaining store module's own repository contracts. The
`repositories` map is catalog data; the rule that reads it is store-neutral
already.

## GAP-7 — analysing a reactor module costs ~111s · **NOT A GAP — moved to `docs/performance.md` P-1**

Kept under this number so old references resolve. A performance cost, not a missing feature:
the output is the same with or without it (user ruling 2026-09-12). The register no longer
carries it; [`performance.md`](performance.md) does.

---

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
| 5 | "`_NO_DECLINING_TEST_YET` lists 25 of the 55 catalogs" (as written then) | 27 when re-counted; **24 of 64 today** — the backlog shrinks as waves add declining tests, so the figure is dated rather than standing |
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

### OI-150 — the value walk does not cross a lambda's CAPTURE, so a value a lambda closes over is `external` · **CLOSED 2026-10-18**
**Major · entered 2026-10-18, measured on a probe module built from `ruoyi`'s own shape · `src/sextant/application/resolve/values.py::_Walk._parameter`**

A lambda's body is a synthetic method whose first parameters are the values it captured. The
facts record the capture — the `invokedynamic` site carries the captured values as arguments,
and the lambda entry of the argument grammar carries `captures: 2` — but `value_edges` emits
no `bound_to_parameter` edge for it, so `ValueIndex.callers` has **no entry at all** for a
lambda body's parameters and the walk answers `external`:

```java
putPathPrefix(prefixes, "/admin-api", "**.controller.admin.**", matcher);   // two Strings
...
private void putPathPrefix(Map<String, Predicate<Class<?>>> prefixes,
        String prefix, String pattern, AntPathMatcher matcher) {
    prefixes.put(prefix, clazz -> … && matcher.match(pattern, clazz.getPackage().getName()));
}                                        // `pattern` is CAPTURED — unresolved(external)
```

**Measured**, on a probe that differs from `fixtures/orders-pathprefixes` only in holding the
two strings as parameters rather than on an object:

```
prefix  (an argument of `put`, resolved through callers)  ->  /admin-api, /app-api
pattern (captured by the lambda)                          ->  unresolved(external)
```

so both controllers publish `/orders/{id}` and the two collapse into one path — exactly
`OI-148`'s symptom, one spelling to the side. `ruoyi` itself dodges it because its pattern
comes off a captured OBJECT (`api.getController()`), which resolves through the field and
`<init>` edges instead, and the fixture dodges it because `javac` inlines a `static final`
String into the lambda body.

**Real triggering input:** ordinary. Capturing a local or a parameter in a lambda is the most
common thing a lambda does; this is visible only where a catalog asks about a value inside
one.

**Why it is filed rather than fixed inside `OI-148`:** it is a WALK EDGE, the same shape of
work as the sixth edge (`2026-10-18-the-sixth-edge-design.md` — its own spec, its own
additivity proof, its own PR). The honest accounting is that §4's reader is complete for the
declarations it can see, and this is the seventh edge.

**Closes when** a `bound_to_parameter`-equivalent edge binds a lambda body's parameters to the
values the capture site hands it, and the probe above resolves both patterns. The `captures`
count on the lambda entry is already in the facts, so this is an edge-query and walk change
rather than an extractor one — to be confirmed by measuring, not assumed.

### OI-152 — a host assembled through a map, three providers and a health check is not traceable, and is now NAMED
**Minor · entered 2026-10-18, measured on `apolloconfig/apollo` · `src/sextant/application/resolve/shapes/arguments.py::url_of`**

> **BUILT the same day — the walk's SEVENTH edge.** Measured first, as the line above asked:
> the facts carry the whole edge, so nothing in the schema moved and the extractor was not
> touched. A `lambda` entry names its synthetic body and how many values it captured, and the
> value it came from was PRODUCED by the capture site, whose arguments are those values in
> order — so **body parameter *i* is argument *i* of the capture site**, identity, measured on
> four shapes across two modules. `value_index` folds those into `callers` beside the
> `bound_to_parameter` edges, and the walk treats them identically because to it they ARE
> identical: a parameter, and the sites that hand it a value.
>
> Parameters at or past the capture count are deliberately NOT bound — those are the lambda's
> own arguments, handed in by whoever invokes it, and `external` is the true answer for them.
>
> **What it fixed:** `fixtures/orders-pathprefixes` now publishes `/text-api/text/{id}`, where
> the declaration holds its prefix and its pattern as plain `String` parameters. The prefix
> resolves by following the helper's callers; the pattern needs the capture crossing, so this
> is the one row in the suite where the two halves of one declaration need two different
> crossings. Guard `values.a-lambda-body-reaches-the-values-it-CAPTURED`, plus a unit test on
> the hop itself in `tests/application/test_values.py`.
>
> **What it changes in the estate, measured by running every corpus twice — once with the
> pass live, once with it disabled in process — and diffing every published row:**
>
> | corpus | call sites | parameter bindings | rows / shape fields | analyse |
> |---|---|---|---|---|
> | `yudao-module-system` | 39,266 | 3,678 → 3,862 (+184) | 212 / 807, unchanged | 6.3s → 6.3s |
> | `mall-admin` | 25,057 | 10,531 → 10,541 (+10) | 160 / 629, unchanged | 5.0s → 5.0s |
> | `apollo-portal` | 15,574 | 3,044 → 3,159 (+115) | 298 / 650, unchanged | 3.3s → 3.3s |
>
> **No existing binding is widened — 0 of them, in all three** — so the edge adds reach and
> never changes an answer that already existed. **Exactly one row moves in the whole measured
> estate**, the fixture's, and that is the honest reading: the 309 new bindings are real, and
> no catalog asks about those particular captured values today. All six field pins are
> unchanged, the gate is 4160 tests, and the guard registry is 176 killed / 0 survived.
>
> **Still unread, and it belongs to the extractor:** a closure a compiler lowers to a CLASS
> rather than to an `invokedynamic` has no capture list in the facts at all — it arrives as an
> `instance` entry — so there is nothing for this fold to read. Filed where it belongs if a
> corpus ever needs it; no corpus here does.
### OI-153 — a hole in an assembled address is NAMED after the value that fills it
**Minor · entered and BUILT 2026-10-18, measured on `fixtures/orders-pathvars` and `spring-petclinic-microservices` · `src/sextant/application/resolve/values.py::_joined`**

**Entered as a closed item because it is the user's ruling carried one position over**, after
they asked why an interior hole should be anonymous at all:

```java
restTemplate.getForObject("http://customers-service/owners/" + ownerId + "/pets", …);
```

| | published |
|---|---|
| before | `/owners/{}/pets` · peer `customers-service` · partial |
| after | `/owners/{ownerId}/pets` · peer `customers-service` · partial |

The facts named the operand the whole time — `signature.parameters[0].name == "ownerId"`,
from the parameter names the compiler records — so `{}` said *something here* about a value
this analysis could read. And the named form is **the server's own spelling of the same
route**: `@GetMapping("/owners/{ownerId}/pets")` publishes `/owners/{ownerId}/pets`, so the
two sides of one call finally read as one address (`OI-151`'s goal, from the other end).

**Three refusals, each measured rather than reasoned:**

* **A LEADING hole is never named.** It is the authority, and `<host>` is what a reader needs
  there (`OI-152`, the user's own ruling). Measured on `apollo-portal`: naming it turned four
  rows into `{metaServerAddress}/services/admin`, which reads like a route variable and
  answers nothing about who is called.
* **A hole with no name to take keeps `{}`.** `"?petId=" + join(petIds)` fills from a call's
  RESULT; naming it after the method would invent a variable the code does not have.
* **A jar built without parameter names keeps `{}`** — the signature then records none, and
  `arg0` is not a name the author wrote.

**What it was worth the day it shipped: no row in the pinned corpora moved.** The estate's
outbound rows either carried a URI template already (`/owners/{ownerId}`) or held a leading
host hole (`apollo-portal`'s eight), and the shape this fixes — the most ordinary outbound
path there is, three of `spring-petclinic-microservices`'s four genai addresses — was blocked
behind `OI-144`.

**`OI-144` then closed, and the yield landed with it (2026-10-19):** genai publishes
`POST /owners/{ownerId}/pets`, and `spring-petclinic-customers-service` serves
`@PostMapping("/owners/{ownerId}/pets")` — the two sides of one call, character for character.
The pin was re-recorded; it had been asserting the older `{}` text against correct output.

### OI-154 — a peer was published for a helper whose host ANOTHER caller supplies · **CLOSED 2026-10-19**
**Major · entered and closed 2026-10-19, found by review of `spec/discovery-peer-and-fluent` before it merged, measured on a probe and then on `fixtures/orders-discovery` · `src/sextant/application/resolve/shapes/arguments.py::authority_of`, `src/sextant/application/resolve/values.py::_Walk._value`**

`authority_of`'s own docstring promised to refuse "several answers (several peers for one call
is not a peer)". It could not keep that promise, and the reason is worth stating exactly:
**both multiplicity checks ran AFTER the competing answers had already been removed.**

```java
private String fetch(URI host) {                        // the concat is HERE
    return restTemplate.getForObject(host + "/orders", String.class);
}
public String viaDiscovery() {
    return fetch(discoveryClient.getInstances("customers-service").get(0).getUri());
}
public String viaCallersHost(URI supplied) {            // nothing in the facts reads this
    return fetch(supplied);
}
```

| | published for `fetch` |
|---|---|
| `main` | peer NULL · `<host>/orders` · partial — true |
| the branch, as reviewed | peer **`customers-service`** · `/orders` · **resolved** |
| after this fix | peer NULL · `<host>/orders` · partial |

A parameter is one path per calling context, so operand 0 answered twice: `customers-service`
yielding an authority, and `external` from the unbound parameter. Then

1. the `preserves` filter in `_value` kept the pairs whose `yields` matched and **dropped the
   rest**, where the two arms beside it return all of `identified`; and
2. the peer question collected only the authority-yielding answers, so `len(answers) == 1`
   was true of a set it had just made singular.

Either layer alone hid the second path, so the fix is both: a path the entry cannot carry is
**replaced** with an unresolved answer rather than dropped, and the peer question **refuses
unless every path answers an authority and they all agree**.

**Two other routes to the same false fact, both measured on probes:** a field written once in
the constructor from a lookup and once by a `reconfigure(URI)` setter ("several writers are
several answers"), and a helper with two returns — `if (legacy) return
URI.create("http://legacy-gateway:8080");` then the lookup. All three now publish
`<host>/orders` with no peer. Guards
`arguments.a-PEER-is-refused-where-ANY-path-did-not-answer-one` and
`values.a-path-a-RENDERING-cannot-carry-is-replaced-never-dropped`, both pinned by
`test_a_host_another_caller_supplies_refuses_the_peer` on a fixture class added for it.

*The two-branch shape is an UNDER-report once refused, and deliberately so: one branch names
`legacy-gateway` and the other `customers-service`, and the honest row for a single peer
column is neither. Publishing one row per branch is a feature, entered as `OI-157`.*

### OI-158 — two calls differing ONLY in their query string now dedup to one row
**Minor · entered 2026-10-19 while closing `OI-151`, zero occurrences measured · `src/sextant/application/resolve/engines/single_call.py`, `src/sextant/application/resolve/engines/fluent.py` (the dedup key)**

The query string leaves the address (`OI-151`), and the dedup key is built from the address.
So one caller making two calls that differ only in their query —

```java
restTemplate.getForObject(base + "/search?env=DEV", String.class);
restTemplate.getForObject(base + "/search?env=PROD", String.class);
```

— now publishes ONE row with two `query` entries named `env` beside it, and nothing says
which call sent which. Before `OI-151` these were two rows, because the query was in the key.

**Zero occurrences, measured rather than assumed:** exactly two rows in the six pinned
corpora carry a query at all and they are in different modules, and no fixture has a second.
It is an under-report with a row to hang it on — the `OI-109` shape, "fewer facts, never a
wrong one" — rather than a false fact, which is why it is Minor and was accepted knowingly
as part of closing a Major.

**Closes when** the entries carry enough to tell the calls apart — an ordinal, or the call
site — or when the key keeps the query while the published path does not. **Falsified by** a
module making two such calls and the document showing one row.

### OI-167 — on Maven the header read sees only DIRECT declarations, and Spring Boot's starters put every type one hop behind · **CLOSED 2026-10-21**
**Major · entered and closed 2026-10-21 (spec `2026-10-21-maven-classpath-design.md`, rulings a/b/c) · `src/sextant/ingress/detect/maven.py` (`dependency_archives`), `extractor-jvm/.../TypeHeaders.java`**

**Closed by asking Maven itself** — `mvn -o dependency:build-classpath` once per analysis from
the reactor root, re-used while no POM is newer, the POM-declared set kept as a LABELLED
fallback (`dependency_source: declared`, with Maven's reason) where Maven cannot be asked. Not
by the resolver the entry below proposed: the detector's own comment calls that "a resolver,
not a parse", and a wrong archive here is a wrong hierarchy fact. **Measured through `analyze`
itself after the build:**

| module | before: headers / in no archive | after | dependency set |
|---|---|---|---|
| `spring-petclinic-genai-service` | 9 / 80 | **94 / 29** | Maven's, 286 coordinates |
| `spring-petclinic-rest` | 13 / 186 | **197 / 61** | Maven's, 150 |
| `yudao-module-system` | 0 / 445 | **335 / 176** | Maven's, 278 |
| `mall-admin` | — | 233 / 113 | **declared** — Maven refused offline: the dependency plugin version its POM pins is not in the local repository; `--allow-resolve` fetches it |
| `spring-petclinic-api-gateway` | — | 0 / 64 | **declared** — Maven refused offline on a TEST-scoped artifact `mvn compile` never fetched (spec §2, fact 1); same escape |

*Both fallbacks closed 2026-10-21: the field checker primes the classpath goal beside `mvn compile` (the one step it may reach the network from), and the default offline analysis then answers from the file — `mall-admin` 139 headers, `petclinic-api-gateway` 68, both `dependency_source: maven`. Nothing about `analyze` changed.*

The two fallbacks are the ruling working as ruled: the weaker set, named as such, in the
document's own coverage line. The "in no archive" that remains on Maven's answer is the
platform's own types, which the walk stops at on purpose. Both `@ControllerAdvice` rows now
produce on the field corpus, and the same file answers `resolve/dependencies.py`'s gate — on
`orders-service`, Spring Integration was on the compile classpath through `spring-cloud-stream`
and its catalog was SKIPPED for a month; it runs.

*The entry as written when it was opened:*


The `type_header` read (D00 §5) looks up every dependency type a module refers to in the
jars on its classpath. On Maven that classpath is built from `dependency_versions` — the
module's **direct** declarations — because the POM parse records direct declarations only
(the boundary `Data REST — a module whose build declares the framework only TRANSITIVELY`
already states for one catalog). A Spring Boot module declares `spring-boot-starter-web`, a
jar with no classes, and gets `spring-web`, `spring-context`, `spring-beans` as that starter's
transitives — none of which is on the list this reads.

**Measured, and it is the whole yield:**

| module | direct deps | jars on the classpath | headers read | unscanned owners |
|---|---|---|---|---|
| `spring-petclinic-genai-service` | 24 | 20 | **9** | 73 |
| `spring-petclinic-rest` | 25 | 25 | **13** | 234 |
| `yudao-module-system` | 1 (a sibling) | **0** | **0** | 2,146 |

So the mechanism works to the framework's rule where a type's jar is declared directly
(`fixtures/orders-advice` declares `spring-context` for exactly this reason, and says so),
and reaches almost nothing on the corpus it was built for — Maven-built Spring Boot — until
the classpath is the RESOLVED one. Gradle has no such gap: its init script reports
`compileClasspath`'s resolved artifacts with their files.

**Real triggering input:** every Maven module using a starter, which is every Spring Boot
module in the pinned corpora. **Not a false fact** — a type that is not found gets no fact and
the walk stops where it always did — but it caps the two `@ControllerAdvice` rows this read
closed at "true where declared directly".

**Closes by** resolving Maven's transitive closure from the local repository's own POMs
(`_local_repository_pom` already reads them for BOM imports): each direct dependency's POM
names its compile/runtime dependencies and `dependencyManagement`, and the walk is the one
Maven itself performs — scopes, `optional`, exclusions — which is why it is its own item and
not a line in this one. **Falsified by** `genai` reading headers for the Spring types its
handlers and clients name, and `yudao-module-system` reading more than zero.

### OI-168 — a module resolving NO configuration key still gets a `default` verdict per condition
**Minor · logged 2026-10-22 (review of spec 2026-10-21-conditional-controllers, Minor 3) ·
`src/sextant/application/resolve/bean_conditions.py::record_bean_conditions` (moved there from `endpoint_conditions.py` by `conditional-beans`)**

The pass takes its environments from `resolved_config`'s rows and falls back to `["default"]`
when there are none, so a `@Profile("prod")` controller in a module whose config files
declare no key at all gets one row, `default | false`, while the same document's coverage
section says *Environments resolved: none.* Two statements about the same module that do not
agree. The fallback is there on purpose — Spring's `default` profile is active whatever the
files say, and dropping the row would make the condition invisible — but the environment list
should come from one place.

**What happens today:** every fixture and corpus declares at least one key; nothing wrong on them.

**Real triggering input:** a Boot module with an empty `application.yml` (or none) and a
conditional controller.

**Verify:** `grep -n 'or \["default"\]' src/sextant/application/resolve/bean_conditions.py`.
**Closes** when the config layer publishes the module's environments as a fact of its own
(the profile files it saw, `default` included) and both the pass and the document read it.

**2026-10-22 — re-read against the active-profiles rule (`conditional-beans`, spec §2d,
CP-45); the issue stands, and its boundary is the same.** An environment is still a profile
FILE: what changed is which profiles are ACTIVE in each — read from the base's
`spring.profiles.active`, `.include` and `.default`, not taken from the file's name alone. So a
profile that no file is named for (`ldap`, `oidc`) is no longer "absent in every environment";
it is `false` or "not evaluated" according to what the base's keys say, and `unresolved`
wherever those keys hold a placeholder nothing fills. What this entry still describes is the
environment LIST: a module with no resolved key gets the one environment `default` (now with
its active profiles read the same way), while its coverage section says *Environments
resolved: none.* The wider consequence is the same too — an environment the deployment adds
(a profile with no file) is not one the document can speak about, only a profile the base
names can be left open.

**2026-10-23 — re-read against `deployment-set-conditions`; it stands.** Every profile and property verdict in a module that resolves no key is now "not evaluated" (with the module's own default as evidence) rather than `default | false`; the environment LIST is unchanged.

### OI-169 — the exporter masks `endpoints.path` but ships `endpoint_metadata.path` verbatim · **CLOSED 2026-10-23**
**Re-rated Major and closed 2026-10-23** (branch `fix/peer-userinfo`): the entry understated it. `endpoint_metadata` carries OUTBOUND rows, and an outbound `path` may be a whole address, so an outbound call that sets a header shipped `https://svc:s3cret@…` in `endpoint_metadata.parquet` — a credential in the bundle, which by the standing ruling is never Minor. Its export now masks `path` by `_REDACTED_ADDRESSES`, and its paths join the map; pinned by `redaction.endpoint-METADATA-and-CONDITIONS-mask-the-endpoints-path`. The `endpoint_conditions` half was closed by `conditional-beans` (below).

**Originally Minor · logged 2026-10-22 (final review of spec 2026-10-22-boundary-vocabulary-and-diff);
restated 2026-10-23 when `cov/conditional-beans` merged `main` ·
`src/sextant/storage/duckdb/workspace.py::_EXPORT_QUERIES`, `src/sextant/application/boundary/source.py`**

`export` passes `endpoints.path` (and `peer`) through the `_REDACTED_ADDRESSES` map, while
`endpoint_metadata` and `endpoint_conditions` are exported whole, `path` included. Both are
tied to their endpoint by carrying its identity columns rather than a key, and the boundary
source joins them on `path` — so on a BUNDLE side, an endpoint whose path the redactor
changed (userinfo in a path, a value pattern matching it) carries the masked path while its
requirement and condition rows carry the verbatim one, and the join misses them: the
endpoint reads with no requirements and no conditions, and a diff against the workspace it
came from reports them removed.

**What happens today:** 0 such paths across 44 workspaces, measured by the whole-branch
review of `h/meridian` on 2026-10-22 (not re-measured when this entry was logged) — no inbound
path in that set is changed by masking, so nothing misses.

**Real triggering input:** an endpoint path the redactor rewrites, e.g. a `redact:` value
pattern a route segment matches, on a module with a requirement or a condition on that route.

**The `endpoint_conditions` half is closed** (no longer part of this entry): spec
2026-10-22-conditional-beans exports the `endpoint_conditions` view with `path` masked through
the same `_REDACTED_ADDRESSES` map `endpoints.path` uses, so a bundle's condition rows join
their endpoint on the masked spelling. `endpoint_metadata.path` is still exported verbatim.

**Verify:** `grep -n '"endpoint_metadata": _NAMED_QUERIES' src/sextant/storage/duckdb/workspace.py`.
**Closes** when the exporter masks `endpoint_metadata.path` through the one
`_REDACTED_ADDRESSES` map as well, so it stays spelled like `endpoints.path` in a bundle.

### OI-170 — a call declared on a generic framework type lists every repository that extends it
**Minor · logged 2026-10-22 (review of `conditional-beans`' framework-implemented interface
beans, spec §4) · `src/sextant/storage/duckdb/schema.sql` (`candidate_presence`, the proxy arm),
`src/sextant/application/resolve/bean_conditions.py::_registered_interfaces`**

A call whose receiver is declared as a GENERIC framework type — `JpaRepository<User, Long>
repository` — names `JpaRepository`, so every module repository interface extending it is a
candidate for the call: the type argument is not used to narrow. The site then lists
framework-generated implementations of repositories that cannot answer it, and states a
per-environment line for each.

**What happens today:** measured, it triggers nowhere — **0 of 69** proxy sites on
`jhipster-sample-app` and **0 of 34** on `spring-petclinic-rest` has a framework generic type as
its receiver.

**Real triggering input:** a service that holds a `JpaRepository<X, Y>` or `CrudRepository<X, Y>`
field in a module that has more than one repository.

**Verify:** `grep -n "interface_beans" src/sextant/storage/duckdb/schema.sql` — the match is on
`split_part(c.target, '#', 1)` alone. **Closes** when the arm also requires the interface's
type arguments (`generic_interfaces`) to agree with the receiver's, or the receiver's type
arguments are carried on `call_edges`.

### OI-171 — relaxed spellings of the profile keys are not read
**Minor · logged 2026-10-22 (Task 7b of `conditional-beans`, CP-45 row 5); restated
2026-10-23 when profile groups were built (CP-45 row 8) ·
`src/sextant/application/resolve/bean_conditions.py::active_profiles`,
`src/sextant/catalogs/spring-web.yml` (`config_model.profiles`)**

The active, include, default and group keys are matched exactly (or as `key[N]` for a list): a
spelling Boot's relaxed binding accepts (`SPRING_PROFILES_ACTIVE` written inside a
configuration file, camelCase variants) is not matched, so a profile it names reads as not
active. Also not read: a group whose value is a placeholder nothing fills adds no member.

**Profile groups are read** (no longer part of this entry): `spring.profiles.group.<name>`
makes its members active wherever `<name>` is, transitively, each as certain as `<name>`.
Measured when built: five modules set a group — `apollo-portal`, `apollo-configservice`,
`apollo-adminservice` and `apollo-assembly` (`spring.profiles.group.github = mysql`) and
`jhipster-sample-app` (`spring.profiles.group.dev`, a list, in `config/application.yml`) — and
**0 verdicts change** on fresh analyses of the first three (`bean_conditions`,
`bean_presence`, `candidate_presence` and `endpoint_conditions` identical before and after):
Apollo's active list is the unfilled `${apollo_profile}`, which already leaves every profile
not decided by the environment's own name open, and no bean of those modules carries
`@Profile("mysql")`. `apollo-assembly` is not analysed, and `jhipster-sample-app` resolves no
environment (its configuration sits under `config/`), so neither moved either.

**What happens today:** no configuration file a module ships writes a relaxed spelling of
the keys (`grep -rln "SPRING_PROFILES\|springProfiles" examples` over `.yml`, `.yaml` and
`.properties` files under `src/main/resources` finds none; the hits elsewhere are Docker and
CI environment variables, which no module's configuration reads).

**Real triggering input:** a Boot application whose `application.yml` sets
`SPRING_PROFILES_ACTIVE: prod` or `spring.profiles.ACTIVE`.

**Verify:** `grep -n "key_matching" src/sextant/catalogs/spring-web.yml` says `relaxed`, and
`active_profiles` matches `re.escape(key)` exactly. **Closes** when the profile keys are matched
by the config model's relaxed key normalization.

### OI-172 — the `@ConditionalOnBean(annotation = …)` criterion ignores the type hierarchy
**Minor · logged 2026-10-22 (Task 3 of `conditional-beans`) ·
`src/sextant/application/resolve/bean_conditions.py::_presence_verdicts`**

The annotation criterion matches the annotations the competitor's OWN type carries (composed
annotations included). Spring's `findAnnotationOnBean` also looks on the type's superclasses
and interfaces, so a bean whose superclass carries the annotation is a competitor in Spring and
not here: a `@ConditionalOnMissingBean(annotation = X)` can read as holding where the container
skips it.

**What happens today:** no `@ConditionalOnBean` / `@ConditionalOnMissingBean` in the analysed
corpora (`examples/`, every `.java` file, multi-line arguments included) names the `annotation`
attribute: 0 uses.

**Real triggering input:** `@ConditionalOnMissingBean(annotation = SomeMarker.class)` where the
marker sits on a base class of the existing bean.

**Verify:** `grep -n "other.annotations" src/sextant/application/resolve/bean_conditions.py` —
the criterion reads the competitor's own `annotations`, filled from the annotations recorded
on its type alone. **Closes** when the
criterion reads the annotations of the type and every ancestor `type_hierarchy` reaches (the
set `_supertypes_of` already computes), with a test for an annotation on a superclass.

### OI-173 — symbol parsing in SQL: the `candidate_presence` view cuts a symbol on `#`
**Minor · logged 2026-10-22 (Task 7b review of `conditional-beans`) ·
`src/sextant/storage/duckdb/derive_endpoints.sql`, `src/sextant/storage/duckdb/schema.sql`
(`candidate_presence`)**

The symbol grammar belongs in `domain/symbols`. Two places cut a symbol in SQL. The
`candidate_presence` VIEW (`schema.sql` ~1359) adds `split_part(c.target, '#', 1) || '#'` to
match a call's named type to `interface_beans.type`. `derive_endpoints.sql` (~853, which
predates the branch) is a derivation script, not a view: it splits on `(` after a
`regexp_extract` of the part after the last `#`. A change to how a type is spelled in a
symbol would need both found by text search, not by a test. A known exception, recorded so it
is not mistaken for a pattern.

**What happens today:** correct for every symbol the extractors write; nothing wrong.

**Real triggering input:** a change to the symbol spelling of a type (a new language's scanner,
or a generics suffix) that the SQL does not cut the same way as `domain/symbols`.

**Verify:** `grep -n "split_part" src/sextant/storage/duckdb/*.sql` (the view's `#` cut is the
`schema.sql` hit). **Closes** when the type of
a target is a column the extractors or `call_edges` carry (so no SQL cuts a symbol), or the
two cuts are routed through one user-defined function declared next to `domain/symbols`'s
grammar and tested against it.

### OI-174 — a body a conditional bean declares and an unconditional subclass bean inherits reads only the declaring bean's conditions
**Minor · logged 2026-10-23 (whole-branch review of `conditional-beans`) ·
`src/sextant/application/resolve/bean_conditions.py::_inherited_rows`**

`_inherited_rows` gives an inherited body the routes of the beans that run it only where the
body's declaring class is NOT itself a bean (`if declaring in beans or body in routes:
continue`). A body declared on a CONDITIONAL concrete bean `B` — say `@Component
@Profile("prod") class B { void send() {…} }` — and inherited, not overridden, by an
UNCONDITIONAL bean `@Component class S extends B` runs as part of `S` too, so it exists in
every environment; but the body maps to `B` through its owner class (`symbol_beans`) and reads
`B`'s condition: absent outside `prod`. A decided wrong answer, not an open one.

**What happens today:** measured 0 such hierarchies. On fresh analyses of `apollo-portal`,
`apollo-configservice`, `apollo-adminservice`, `jhipster-sample-app`, `yudao-module-system`,
`yudao-spring-boot-starter-websocket` and `spring-petclinic-rest`, no class carrying a
condition is the ancestor of any module class in `type_hierarchy`, so no body is affected;
the whole-branch review found the same on the six field corpora.

**Real triggering input:** a conditional base implementation extended by an unconditional
bean — e.g. `@ConditionalOnMissingBean` default sender subclassed by a plain `@Component`.

**Verify:** `grep -n "if declaring in beans or body in routes"
src/sextant/application/resolve/bean_conditions.py`. **Closes** when a body declared on a bean is given the OR of its declaring bean's routes and
those of every subclass bean that resolves the method to it, as for a body declared on no
bean.

### OI-175 — a bare `user:pass@host` configuration value under a key naming no secret is not masked
**Minor · logged 2026-10-23 (review of `fix/peer-userinfo`) · `src/sextant/domain/redaction.py::_USERINFO`**

A deliberate trade-off, pinned by `tests/domain/test_redaction.py::test_text_with_no_scheme_keeps_its_at_sign`.
There is no userinfo rule without a `scheme://`, because in text `svc:s3cret@billing.internal`
cannot be told from `mailto:ops@billing.internal` or `jdbc:oracle:thin:@localhost:1521:XE`, and
the version that tried rewrote both. So `billing.authority=svc:s3cret@billing.internal` ships
unmasked in `resolved_config` and `config_entries`. A key naming a secret still masks it whole,
and a repo's own `redact:` value pattern still applies. `resolved_peers` substitutes such a value
into a `${…}` peer and is read by nothing today, so it is not an exit yet.

**What happens today:** not measured across the corpus for config values.
**Real triggering input:** a configuration value written as a scheme-less authority with a
password, under a key with no secret-like name.
**Closes** when the configuration layer knows a value is an authority (a key the catalogs
declare as one) and drops the userinfo there, as `split_url` does.

### OI-176 — a raw `/` inside a URL's password splits the authority early
**Minor · logged 2026-10-23 (review of `fix/peer-userinfo`) · `src/sextant/application/resolve/shapes/arguments.py::_ABSOLUTE_URL`**

`https://u:p/w@billing/x` splits at the first `/`, giving peer `u:p` (user and half the
password) and path `/w@billing/x`. RFC 3986 forbids the raw `/`, and `java.net.URI` ends the
authority at the same place, so the call cannot reach `billing` as written: the code would not
work. Logged rather than fixed by the incidental-findings rule; DR-6 says predict the
framework, and the framework reads it as we do. The same holds for a raw `?` or `#` in a
password (`https://u:p?ss@billing/x`), which now keeps `u:p?ss@billing` as the peer text:
Spring reads host `u`, port `p` and a query.

**Closes** if a framework is found that accepts the form.

### OI-177 — a malformed `redact:` value pattern in one module fails `system analyze` without naming the module
**Minor · logged 2026-10-23 (review of `fix/peer-userinfo`) · `src/sextant/api.py::_redactor_for`**

The system document masks by every participant's rule set, so one module's bad `.sextant.yml`
now fails the whole run, before anything is written, as `render` fails for that module. The
type error names the file; the regular-expression error ("redact value pattern … is not a
regular expression") does not, so a reactor with many modules leaves the reader to search.

**Closes** when `RedactionError` carries the path it was read from.

### OI-178 — the URL userinfo strip can eat the next value in compact raw text
**Minor · logged 2026-10-23 (review of `fix/peer-userinfo`) · `src/sextant/domain/redaction.py::_USERINFO`**

`_USERINFO` strips to the authority's LAST `@` and admits any character but a delimiter or
whitespace before it, because a password carries what it carries (a first version that stopped
at `"`, `\`, `<`, `>` kept the NTLM proxy form `http://CORP\jdoe:pass@proxy`). So in raw text
with no delimiter between a bare-host URL and a later `@` —
`{"url":"https://svc","owners":["a@x.com"]}`, `url='https://svc',owner='a@x.com'` — the strip
runs into the next value and removes it. Text is lost, nothing leaks. It reaches the enrichment
tools' results, which pass fact lines and file text through `redact_text`; `redact_json` walks
decoded leaf strings and is not affected.

**Closes** when raw-text exits strip by a tokenizer that knows where a URL ends (a JSON fact
line through `redact_json` rather than `redact_text`), not by a wider character class: `'` and
`,` are legal in userinfo, so no class can end the authority there.

### OI-179 — `resolved_peers`' SQL substitution cannot read a `:default`
**Minor · logged 2026-10-23 (spec `2026-10-23-configured-schedules` §4) · `src/sextant/storage/duckdb/workspace.py` `_NAMED_QUERIES["resolved_peers"]`**

The `resolved_peers` named query substitutes a `${…}` in an outbound row's `path` or `peer`
in SQL: one placeholder, `regexp_extract('\$\{([^}]*)\}')`, the whole inside of the braces as
the key, `${`/`}` hard-coded. So `${billing.url:http://localhost:8080}` looks up the key
`billing.url:http://localhost:8080`, which no configuration declares, and reads `missing_key`
in an environment where Spring would use the default. It is also a second placeholder rule
beside `resolve/config.py::substitute`, which the scheduled-work pass now uses.

**What happens today:** nothing reads the query — no `workspace.query("resolved_peers")`
outside its definition, and it is not exported — so no output is wrong yet.
**Real triggering input:** an outbound client whose address placeholder carries a default,
`@Value("${billing.url:http://localhost:8080}")`, the ordinary Spring form.
**Closes** when something reads the query, by moving the substitution onto `substitute` (in
Python, over one environment's `resolved_config`, as `resolve/resolved_schedules.py` does).

### OI-180 — `config_join._channel_name` is a second placeholder walk beside `substitute`
**Minor · logged 2026-10-23 (controller review of configured schedules, task 3) · `src/sextant/application/resolve/engines/config_join.py::_channel_name`**

`_channel_name` walks a channel name's `${…}` itself: it reads the config model's delimiters,
splits the default off and drops it, and asks its own per-environment map. The project's one
placeholder rule is `resolve/config.py::substitute` (spec 2026-10-23-configured-schedules
§3a). The walk differs from it on purpose in one place — a spelled default is not applied, so
such a name stays `unresolved` — and on the rest (nesting, an unclosed opener) by having been
written separately, so the two can drift.

**What happens today:** not measured — whether any fixture or corpus channel name carries a
default or a nested placeholder was not checked.
**Real triggering input:** a Spring Integration channel named through configuration,
`@ServiceActivator(inputChannel = "${orders.channel:orders}")`.
**Closes** when `_channel_name` calls `substitute` with its own lookup, its "no default"
choice stated as that lookup's (or ruled away), so one walk serves every reader.

### OI-181 — a relaxed-key collision reads a different spelling in `resolved_schedules` than in `resolve_config`
**Minor · logged 2026-10-23 (configured schedules, task 2) · `src/sextant/application/resolve/resolved_schedules.py::_environment_lookup`**

Where `key_matching: relaxed` folds two configured spellings onto one key —
`orders.sweepCron` and `orders.sweep-cron`, both normalizing to `orders.sweepcron` (the dot
stays a separator) — `_environment_lookup` takes the first row in the `resolved_config` query's
order, the alphabetically first spelling, while `resolve/config.py::_normalized_index` takes
the first in merged-layering order. Both are deterministic; they can name different values for
the same reference.

**What happens today:** not measured, in the fixtures or the corpus. `resolved_config` keeps
no layering order, so the lookup cannot match the other rule.
**Real triggering input:** one environment's configuration spelling a key two relaxed-equal
ways, e.g. `orders.sweep-cron` in `application.yml` and `orders.sweepCron` in a profile file.
**Closes** when `resolved_config` carries the order (or the winning spelling) the layering
chose, and the lookup reads it.

### OI-182 — only the first declared config model is read for a scheduled expression, and `resolved_config` has no model column
**Minor · logged 2026-10-23 (configured schedules, task 2) · `src/sextant/application/resolve/resolved_schedules.py::record_resolved_schedules`**

`record_resolved_schedules` reads the delimiters, `default_separator` and `key_matching` of
the FIRST catalog that declares a `config_model`. `resolve_config` resolves every declaring
catalog into the one `resolved_config`, which carries no model column, so a second family's
rows cannot be told apart and would be looked up under the first family's rule.

**What happens today:** only `spring-web.yml` declares a `config_model` (D02 §2i: one per
framework family), so the first is the only one and nothing is wrong yet.
**Real triggering input:** a second framework family's config model shipping (Quarkus,
Micronaut) in a module that also uses Spring's.
**Closes** when `resolved_config` names the model each row came from and the pass reads each
job's expression under its own catalog's model.

### OI-183 — the boundary vocabulary's `schedule` identity collides under `@Schedules`
**Minor · logged 2026-10-23 (controller review of configured schedules) · `src/sextant/application/boundary/vocabulary.py` (`Kind(name="schedule")`)**

The `schedule` kind's identity is `(handler, trigger)`. Under `@Schedules`, one method carries
two jobs of the same trigger — two crons — and `scheduled_work` holds both rows, which differ
only in `expression`. The diff groups them into ONE entry whose `expression` is
`{"several": [...]}`, so a change to one of the two crons reads as a change to a single
schedule with several attributes rather than as the job it is. `resolved_schedules` already
tells them apart by `expression`.

**What happens today:** not measured on the field corpora; the hand-built `@Schedules` pin in
`tests/application/test_resolved_schedules.py` has such a method.
**Real triggering input:** `@Scheduled(cron = "0 0 1 * * *") @Scheduled(cron = "0 0 13 * * *")`
on one method, an ordinary way to run a job twice a day.
**Closes** by adding `expression` to the kind's identity — a change to what a diff entry
IS, so a `BOUNDARY_VOCABULARY_VERSION` 2 → 3 decision for the user, not made here.

### OI-184 — `substitute` does not model two `PlaceholderParser` behaviours CP-48 read: the whole-inside lookup and the escape character
**Minor · logged 2026-10-23 (final review of configured schedules, CP-48 rows 9-10) · `src/sextant/application/resolve/config.py::substitute`**

CP-48 read Spring's placeholder parser to make `substitute` match it on nesting and defaults.
Two more of its behaviours are not modelled. Row 9: for `${a:b}` with no placeholder inside,
`SimplePlaceholderPart` first looks up a property named `a:b` — the whole inside — and only
then `a`. Row 10: the parser skips an opener or separator preceded by its escape character;
which character, if any, Boot's binder and the bean factory's embedded value resolver pass is
a constructor argument CP-48 did not read.

**What happens today:** not measured on the fixtures or the corpus. A configuration declaring
a key spelled with the separator in it reads the key before the separator instead; an escaped
`\${…}` is substituted where Spring leaves it as text.
**Real triggering input:** row 9, a key spelled with a colon (a quoted YAML key `"a:b"`); row
10, a value meant to carry a literal `${`, written `\${literal}`.
**Closes** when a probe reads the escape character the two callers construct the parser with,
and `substitute` honours it and the whole-inside lookup, each pinned.

### OI-185 — a `${…}` naming the activation key resolves inside `resolve_config` but reads `missing_key` in `resolved_schedules`
**Minor · logged 2026-10-23 (final review of configured schedules) · `src/sextant/application/resolve/config.py::_resolve_model`, `src/sextant/application/resolve/resolved_schedules.py::_environment_lookup`**

`resolve_config` keeps the activation key (the model's `from_document_key`,
`spring.config.activate.on-profile`) in its layered map, so a configuration value
referencing it resolves, but writes no `resolved_config` row for it (M-c, fix round 1: a
directive, not configuration a module reads). `resolved_schedules` looks keys up in
`resolved_config`'s rows, so a scheduled expression referencing the same key reads
`missing_key` — the one placeholder rule answering one reference two ways, by its lookup.

**What happens today:** no real input known; not measured on the fixtures or the corpus.
**Real triggering input:** `@Scheduled(cron = "${spring.config.activate.on-profile}")`, or a
cron whose default names the key — a profile name is not a schedule, so no ordinary job does.
**Closes** when the two lookups answer the activation key alike: `resolve_config` writes its
row, or the schedules lookup is handed the layered map's answer for it.

### OI-186 — a gRPC client's configured address is not read as its peer, for net.devh and Quarkus
**Minor · logged 2026-10-24 (spec `2026-10-24-quarkus-messaging-and-grpc` §1 ruling 3C, not built) · `src/sextant/catalogs/grpc-net-devh.yml`, `src/sextant/catalogs/grpc-quarkus-client.yml`**

Both `injected_client` catalogs derive one service-level outbound row per injected stub, whose
identity is the stub's own `SERVICE_NAME`; neither row carries a `peer`. The client's address is
configured by NAME: net.devh's `grpc.client.<name>.address`, Quarkus's
`quarkus.grpc.clients.<name>.host` and `.port`. The name is the `@GrpcClient` value, or for
Quarkus a value left out names the client by the field (CP-52 rows 2, 5; net.devh's own
omitted-value rule is not measured). So the row has the name to look the address up by and
nothing reads it. The user ruled this one item for both frameworks together, not one at a time.

**What happens today:** a gRPC client row names the service it calls and not the service it
reaches; the stitcher matches it by path alone. Not measured on the fixtures or the corpus.
**Real triggering input:** `@GrpcClient("hello") HelloGrpc.HelloBlockingStub hello;` beside
`grpc.client.hello.address=static://hello:9000` (net.devh) or
`quarkus.grpc.clients.hello.host=hello` and `.port=9000` (Quarkus), two services in one
system that implement the same generated service.
**Closes** when the injected stub's client name reaches the row, the address keys of both
frameworks are measured by a probe (net.devh's key and its `static://` / `dns:///` forms are
not yet), and the value goes through the one placeholder rule, `config.substitute`, as a peer.

### OI-159 — framework and build-tool knowledge in the common stitch tier, three instances
**Major · entered 2026-10-20, found by the design review of PR #56 · `src/sextant/application/stitch/links.py`, `gateway.py`, `participants.py`**

**A principle violation, not a defect in output** — and the second class of its kind this
register has recorded, which §13.8 says to raise rather than quietly fix. GUIDELINES §10 and
`D02`'s whole premise: framework knowledge is catalog data, never code. The architecture test
that enforces it (`test_no_framework_is_named_anywhere_in_code`) scans for framework
NAMES — "spring", "kafka" — and all three of these spell none, which is how they passed it.

| where | what | whose knowledge it is |
|---|---|---|
| `links.py:35`, `gateway.py:241` | `"lb://"` hardcoded | Spring Cloud LoadBalancer's URI scheme |
| `gateway.py` | the `/**` wildcard tail; the `Name=arg` shortcut regex | Spring's Ant-path grammar; Spring Cloud Gateway's shortcut form, which the catalog ALREADY declares as `grammar: shortcut` and `stitch` re-implements |
| `participants.py` | `module_id.rsplit(":", 1)[-1]` as the participant's name | `group:artifact` is Maven/Gradle coordinate syntax. A Go module id has no colon; this returns the whole path and calls it a name |

**Real triggering input:** the third is triggered by the first non-JVM detector; the first two
by the first non-Spring gateway. None fabricates today because the corpus is all Spring on
Maven — which is exactly the condition under which creep goes unnoticed.

**Closes by** the scheme and the grammar moving to the gateway catalog beside
`participant_name_key` and `strip`, and the participant name being produced by the DETECTOR
that produced `module_id` (ingress knows what a coordinate is; `stitch` should not). And by
the architecture test learning to refuse a URI scheme or a glob tail in `application/`, since
a name-based scan has now been shown insufficient.

### OI-160 — `system_analyze` is 95 lines of pipeline inside the API facade
**Minor · entered 2026-10-20, design review of PR #56 · `src/sextant/api.py::system_analyze`**

It reads `modules.json`, builds participants, federates, loads every catalog, resolves
aliases, matches, composes gateway routes, counts uncalled endpoints, writes two tables and
renders. `module analyze` keeps that sequence in `application/stages/analyze.py`, testable
without the CLI's file layout; the system tier has no stage and the sequence lives where only
an end-to-end test can reach it. **Real triggering input:** every change to the sequence.
**Closes by** `application/stages/system.py` owning it, with `api.py` reduced to paths in and
a result out, as `analyze` already is.

### OI-161 — `stitch` reads another engine's private block and a sibling's internal constant
**Minor · entered 2026-10-20, design review of PR #56 · `src/sextant/application/stitch/gateway.py::route_model`, `links.py`**

`route_model` walks `catalog.matches["indexed"]["item"]["peer"]["field"]` — `config_join`'s
undocumented dict shape. Rename a key there and composition returns `None`: no error, no
refusal, no links, and nothing says why. `links.py` imports `UNREADABLE_HOST` from
`resolve/shapes/arguments.py`, a published convention of the `path` column living in a
sibling package's internals. **Real triggering input:** any edit to `config_join`'s block.
**Closes by** the route model being a declared catalog form the loader validates (as
`participant_name_key` is), and `<host>` moving to `domain/` beside the other published
markers.

### OI-162 — a composed gateway link's `from_*` matches no endpoint row
**Minor · entered 2026-10-20, design review of PR #56, measured on `petclinic` · `src/sextant/application/stitch/gateway.py`, `D01` system scope**

`D01` says `links` joins "outbound endpoint, inbound endpoint". For the 15 gateway endpoint
links on `petclinic`, **13 have a `from_path` that exists in no `endpoints` row of the
gateway's own workspace** — `GET /api/customer/owners/{ownerId}` is synthesised from the
prefix, while the gateway's real row is `GET /api/customer/**`. A consumer joining
`links.from_*` back to `endpoints` finds nothing, and `from_caller` is NULL. The document is
correct; the TABLE's join semantics are not. **Real triggering input:** any gateway route.
**Closes by** a ruling: either the from-end is the gateway's inbound `/**` row (an inbound
endpoint acting as a forwarder) with the composed address in its own column, or `D01`
states that a link's from-end may be a derived address. Either way `D01` must say which.

### OI-163 — `StripPrefix` declared as a default filter is not read, so the route is refused
**Minor · entered 2026-10-20, review probe · `src/sextant/application/stitch/gateway.py::_routes`**

`spring.cloud.gateway.server.webflux.default-filters[N]` applies to every route, and the join
reads `routes[N].filters[M]` only. A gateway stripping its prefix globally has every route
refused with "declares no StripPrefix filter" — a false REFUSAL, not a false link, so an
under-report. **Real triggering input:** ordinary; `petclinic` uses `default-filters` for
`CircuitBreaker` and `Retry` today and could move `StripPrefix` there tomorrow. **Closes by**
the catalog declaring the default-filters key and the join reading both, route-level winning.

### OI-164 — a `Path` predicate with several comma-separated patterns is read as one
**Minor · entered 2026-10-20, review probe · `src/sextant/application/stitch/gateway.py::_one`**

`Path=/a/**,/b/**` is two patterns (the catalog's own `gather: list_tail_flag` says so). The
join takes the whole argument, sees it end in `/**`, and reads the prefix as `/a/**,/b` — three
"segments". Today that is refused because the count mismatches `StripPrefix=1`, **with a wrong
reason**; with a strip count that happened to equal 3 it would compose
`/a/**,/b/orders`, an address that exists nowhere. **Real triggering input:** uncommon but
legal. **Closes by** splitting on `,` as the catalog grammar does and composing one prefix per
pattern, or refusing a multi-pattern predicate with that as the stated reason.

### OI-165 — a participant's name is interpolated into the federated view's SQL
**Minor · entered 2026-10-20, review · `src/sextant/storage/duckdb/workspace.py::federate`**

`f"SELECT '{name}' AS participant …"` — the name is a VALUE, as the surrounding comment says,
and then it is spliced into the statement rather than bound. A name containing `'` breaks the
view; one containing `' UNION …` is worse. Maven forbids quotes in an artifactId, which is why
this has not fired. **Real triggering input:** a Gradle project name, or `OI-159`'s next
detector. **Closes by** binding the literal or escaping it.

### OI-166 — loading 101 catalogs is more than half of a system run
**Minor · entered 2026-10-20, measured · `src/sextant/api.py::system_analyze`**

`system analyze` on `mall-swarm` takes 206 ms; 113 ms of it is `YamlCatalogSource.load()`,
to read two declarations (`participant_name_key` and the route model). Not a defect at this
scale — recorded because it is the dominant cost of every system run and grows with every
catalog added. **Closes by** a loader entry point that reads only the system-tier declarations,
or a cached load shared with `module analyze` in one process.

### OI-155 — `preserves` is the only identity key with no closed-set validation
**Minor · entered 2026-10-19, found by review of `spec/discovery-peer-and-fluent` · `src/sextant/ingress/catalogs/yaml_source.py::_identities`**

`yields` is validated against `("address", "authority")`, with the stated reason that "a typo
is a refusal rather than a silent `address`". The sibling key added three lines away gets
nothing: `preserves: address` on `java.lang.String#valueOf` loads cleanly and would carry a
JMS destination's vendor `toString()` into a joined address at `resolved` — the exact defect
`OI-142` refused and that CP-39 and guard
`values.a-RENDERING-carries-an-authority-and-nothing-else` exist to forbid.

**Logged rather than fixed, by the rule for it:** it takes a catalog edit to trigger, not real
input. A misspelling (`preserves: authoirty`) fails safe — everything becomes unresolved — so
only the `address` spelling is dangerous, and only a shipped catalog could carry it.

### OI-156 — `authority_of` reads operand 0 as the authority without checking it is the one `<host>` names
**Minor · entered 2026-10-19, found by review of `spec/discovery-peer-and-fluent`, no triggering input found · `src/sextant/application/resolve/shapes/arguments.py::authority_of`**

`_joined` refuses an operand/piece count mismatch outright, on the ground that "guessing an
alignment would publish operands in the wrong places". The peer question makes that guess: it
reads slot 0, and `with_authority` fires on nothing but `path.startswith("<host>")`. Two ways
slot 0 is not the `<host>` hole:

* `url_of` writes `<host>` for ANY leading hole, not only an authority one. `scheme + "://" +
  host + "/owners"` does not match `_ABSOLUTE_URL` (the optional scheme group cannot begin
  with `{`), so the path becomes `<host>://{}/owners` and the peer is asked of the **scheme**;
* a recipe/operand count mismatch, where `_joined` falls back to the raw template and the
  holes no longer correspond positionally.

**No shipped entry mints an authority for a scheme or an index**, so neither reaches a false
peer today. Logged as the one place this work asserts a positional correspondence it does not
check — and the fix, if it is ever needed, is to carry the hole's own index rather than assume
zero.

### OI-157 — a destination that differs per BRANCH publishes one row or none, never one row per branch
**Minor · entered 2026-10-19, measured on a probe while closing `OI-154` · `src/sextant/application/resolve/shapes/arguments.py::authority_of`**

```java
private URI host() {
    if (legacy) { return URI.create("http://legacy-gateway:8080"); }
    return discoveryClient.getInstances("customers-service").get(0).getUri();
}
```

Two destinations, both stated in the code, both read by the walk — and the row publishes
`<host>/orders` with no peer, because a single peer column cannot hold two peers and `OI-154`
ruled that guessing one of them is a false fact. The honest answer is TWO rows, which is what
the walk's own paths already describe; nothing downstream fans a peer out that way yet.

*Related but not the same: `OI-154` is about a path nobody read (refusing is the only honest
answer there). This is about two paths both read, where refusing under-reports.*

### OI-151 — an outbound row keeps its query string in `path`, where the inbound row records the same parameter as metadata · **CLOSED 2026-10-19**
**Major · entered 2026-10-18, measured on `spring-petclinic-microservices` and `apollo-portal` · `src/sextant/application/resolve/shapes/arguments.py::url_of`, `src/sextant/application/resolve/request_requirements.py`**

**Nothing is wrong at runtime, and the first version of this entry implied otherwise.** The
call succeeds: the server declares `@RequestParam("petId")` and the caller sends `?petId=…`,
which is the same contract from both ends. What disagrees is how Sextant RECORDS the two
ends.

| | `endpoints.path` | `endpoint_metadata` |
|---|---|---|
| `visits-service` serves | `/pets/visits` | `inbound, GET, /pets/visits, kind=param, name=petId, required` |
| `api-gateway` calls | `/pets/visits?petId={petId}` | *nothing* |

So the two rows cannot be compared on the address, and the linking tier (`GAP-2`) would miss
a link that is exact in the code. A reader diffing the two columns sees a mismatch that is
not one.

`apollo-portal` carries the same shape at `partial`: `POST {}?env={env}`.

**Not caused by the constant work that exposed it** — `{}?env={env}` predates it; what
changed is that the first fully RESOLVED row of this shape now exists, which is how the
disagreement became visible.

**It needs no ruling, which the first version of this entry got wrong too.** The model
already has the right home and the inbound half already uses it: `endpoint_metadata` carries
`kind=param` rows — 299 of them across the corpora — and its `direction` column is written
`inbound` every time, because nothing outbound writes one. The outbound side should do what
the inbound side does: `path` without the query, plus one `param` row per query parameter,
`value` NULL where the value is a runtime expression exactly as a declared `@RequestParam`
records none.

**Real triggering input:** ordinary — any client that passes a query parameter in the URI
template, which is how `RestTemplate` and `WebClient` are normally used.

**Closes when** `/pets/visits?petId={petId}` publishes as `/pets/visits` plus an outbound
`param` row named `petId`, the two sides compare equal on the address, and `apollo-portal`'s
`{}?env={env}` does the same.

> **CLOSED 2026-10-19.** Measured on the pinned commits, both sides read from the workspace:
>
> | | row | entry |
> |---|---|---|
> | `api-gateway` calls | `GET /pets/visits` · peer `visits-service` · resolved | `outbound, query, petId, value NULL, unresolved` |
> | `visits-service` serves | `GET /pets/visits` · resolved | `inbound, param, petId, value NULL, resolved, required` |
>
> The addresses the two modules share went from none to `{('GET', '/pets/visits')}`.
> `apollo-portal`'s row is `POST <host>` with one `query` entry named `env`. Both pins were
> re-recorded; the other four are unchanged.
>
> **One deviation from this entry's own prediction, and it is deliberate: `kind` is `query`,
> not `param`.** The looser word has a stated rule — "`param` only for the two APIs that
> cannot tell the query string from a form body" (`@RequestParam`, `params=`, the Servlet's
> `getParameter`) — and an outbound URI template is not one of them: `?petId={petId}` is the
> query string and nothing else, so writing `param` would say LESS than the class file does.
> **The consequence lands on `M06`:** the two sides do not compare equal on `kind` alone, and
> a client's `query` SATISFIES a server's `param` because `param` is the union of query and
> form. That is a matching rule for the stitcher, recorded here and in `GAP-2` rather than
> paid for with a looser column.
>
> **Three refusals, each leaving the query ON the path** rather than guessing — stripping a
> query this cannot describe would delete evidence the row had: a parameter whose NAME
> carries a hole or a `${…}`, one written with no `=` at all (`?debug` states a parameter
> with no value, and neither `resolved` with a NULL value nor `unresolved` says that — no
> corpus or fixture carries one, so the word is not invented), and an empty name.
>
> **It made `single_call` a FOURTH origin writing `endpoint_metadata`**, which
> `test_every_origin_writing_endpoint_metadata_holds_a_redactor` caught: the first draft
> built the row in a shared helper that held the only redactor, so the engine would have
> written values it never read and the rule would have been vacuous for the next origin. The
> address rule is shared and each engine builds and masks its own row — which is what both
> already did for every other row they write. `?token=sk-live-…` is pinned in both fixtures.
>
> Guards `arguments.a-QUERY-STRING-is-not-part-of-the-address` and
> `arguments.a-QUERY-parameters-value-is-masked-by-its-own-name`.

### OI-149 — a nested aggregator's modules are invisible, so 323 endpoints' response contracts are open
**Major · entered 2026-10-18, measured on `YunaiV/ruoyi-vue-pro` (Spring Boot 2.7.18, 7,244 non-test Java files) · `src/sextant/application/resolve/../ingress/detect/maven.py::_reactor_modules`**

`yudao-module-system` publishes 212 inbound rows and **85 of its shapes are open**;
`yudao-module-infra` 116 rows and 45 open. Every one is the envelope those endpoints return —
`CommonResult#<PageResult#<DictDataRespVO#>>` and 129 siblings of it. So the document names
every endpoint correctly and describes the response of **none** of them.

**The mechanism that should cover this already exists and is right.** `_sibling_roots` reads
the compiled output of every reactor sibling a module depends on, transitively, with no
opt-in — and it works: `mall-swarm/mall-admin` reads `CommonResult`'s three fields out of
`mall-common` that way, reached through `mall-security`, exactly as its docstring says.

**The cause is one level of nesting.** `_reactor_modules` resolves the PARENT's `<modules>`
entries and stops:

```
ruoyi-vue-pro/pom.xml        <modules>: yudao-framework, yudao-module-system, yudao-server, …
yudao-framework/pom.xml      <packaging>pom</packaging>   <modules>: yudao-common, yudao-spring-boot-starter-web, …
```

`yudao-module-system` depends on `yudao-spring-boot-starter-biz-tenant` and friends, which
live one level further down. The root's module list names `yudao-framework` — an aggregator
with no `target/classes` — so `by_coordinate` never contains the children and
`_sibling_roots` finds nothing to read. **`mall-swarm` is flat, which is the only reason it
works there**, and a flat reactor is not the common shape in large Java projects.

**Not reachable by the two obvious workarounds, both measured.** A reactor-root
`analyze` leaves the figure at 85 — each module still gets its own workspace.
`extract_libraries` cannot substitute: the two-part coordinate defers to the build for a
version the module does not declare (the dependency is transitive), and the pinned three-part
form needs an archive in the local repository, which `mvn compile` never installs. The
pinned form DOES work where a jar exists — proved on `mall-admin`, where it read
`com.macro.mall:mall-common:1.0-SNAPSHOT` and the scan went from 74,464 facts to 75,417 —
so the opt-in is sound and is simply not the right tool for a sibling.

*The two-part form's failure here is `OI-8`'s shortfall seen from the field, and this entry
first described it as though it were new: that entry says `_library_roots` resolves a version
from the module's own pom alone, so a coordinate whose version a parent manages — or, as here,
one the module does not declare at all — lands in `libraries_not_resolved` asking the author to
pin it. Recorded there as evidence rather than restated as a finding.*

**Real triggering input:** ordinary. A `framework/` or `common/` aggregator holding the shared
envelope is a standard layout for a large multi-module build.

**Verify:**
```
.venv/bin/sextant module analyze examples/ruoyi-vue-pro/yudao-module-system
.venv/bin/sextant module render examples/ruoyi-vue-pro/yudao-module-system
grep -c "shapes referring to it are open" examples/ruoyi-vue-pro/yudao-module-system/.sextant/render/architecture.md
```
**Closes when** `_reactor_modules` descends into a `<module>` that is itself an aggregator.
**Falsified by** that count reaching 0 while `mall-swarm`'s own figures do not move.

> **FIX IN FLIGHT (2026-10-18), and it took two halves rather than one.**
>
> * **Descend.** `_reactor_modules` now walks every aggregator's `<modules>`
>   breadth-first, each aggregator's own directory being the base its relative paths
>   resolve against.
> * **And start at the TOP.** The entry above described only the downward half, and the
>   same project has the other: `yudao-module-mall/yudao-module-promotion` depends on
>   `yudao-module-system`, a ROOT-level module, and `yudao-module-product` on
>   `yudao-framework/yudao-spring-boot-starter-web`, a different subtree entirely.
>   Descending from `yudao-module-mall` reaches neither. The walk now climbs the
>   `<parent>` chain first.
>
> **Measured on `yudao-module-system`, same commit before and after:**
>
> | | shapes | open | shape fields | `DictDataRespVO` fields |
> |---|---|---|---|---|
> | before | 122 | 89 | 212 | **0** |
> | after | **167** | **60** | **807** | **10** |
>
> `yudao-module-infra`: 422 shape fields where it had 212-ish, and its unexpanded list
> falls from 45 entries to 5. The six and five that REMAIN are correct — `java/util/List#`,
> `java/lang/Object#`, `java/time/LocalDateTime#` and a third-party captcha library — none
> of which is in the reactor, and all of which `extract_libraries` exists for.
>
> **The climb broke a pinned corpus on its first attempt, and the pin is what caught it.**
> `macrozheng/mall`'s root pom inherits from `spring-boot-starter-parent` with an empty
> `<relativePath/>`, so an unconditional climb landed `parent_path` inside `~/.m2`,
> discarded the real reactor root, and took `mall-admin` from **629 shape fields to 73** —
> every wire contract that module publishes, silently. The rule that fixes it is
> containment: an ancestor replaces this one only where it declares `<modules>` AND its
> directory contains the module being analysed. Guard
> `maven.a-climb-stops-at-the-aggregator-that-contains-this-module` kills on it, because a
> field pin is not something the suite runs.
>
> **The remaining 60 open shapes are a DIFFERENT, pre-existing limit** and are not this
> entry's: `CommonResult#<PageResult#<DictDataRespVO#>>`'s `data` field points at the RAW
> `PageResult#`, so the page's element type is not reachable from the envelope. `mall-swarm`
> does the same with `CommonPage#` and did so before this change. `expansion.py` states the
> rule it follows ("a field holding an unbound type variable gets no shape id"); whether a
> NESTED generic's binding should travel is its own question, unentered until someone
> measures what it would buy.

*The openness that remains in `mall-swarm` after the fix is CORRECT and must not be chased: a
raw `CommonResult`'s `data` field is an unbound `T`, and `expansion.py` names that case
("a shape with an undescribed field is OPEN") as a deliberate refusal to claim more than the
evidence supports.*

### OI-148 — a configured path prefix is never applied, so every path in a module can be wrong · **CLOSED 2026-10-18, both halves**
**Major · entered 2026-10-18, measured on `ruoyi-vue-pro` and on the PINNED `spring-petclinic-rest` · `src/sextant/application/resolve/engines/annotation_driven.py`**

Three spellings of one gap. An inbound path is read from annotations alone, and a prefix the
framework prepends at runtime is never added:

| spelling | evidence | where it is live |
|---|---|---|
| `server.servlet.context-path` | **pure configuration, one line** | `spring-petclinic-rest`, a PINNED corpus: `application.properties` sets `/petclinic/` and all **44** pinned routes lack it |
| `spring.mvc.servlet.path`, `spring.webflux.base-path` | pure configuration | not yet seen in the corpus |
| `management.endpoints.web.base-path` | pure configuration | already a stated boundary (COVERAGE §5.1, CP-5 rows 7-8) |
| `RequestMappingHandlerMapping.setPathPrefixes` | a Spring MVC API, values from configuration, predicate in application code | `ruoyi-vue-pro`: **all 480** inbound rows across three modules |

**What the document says versus what the app serves.** `/system/user/page` against
`/admin-api/system/user/page`. Worse than incomplete: ruoyi's admin and app controllers both
map `/system/tenant/get-by-website`, distinguished ONLY by their prefixes, so the two collapse
into one path in the document and a reader sees one endpoint where two exist.

**The cause is one boundary already written down** — `annotation_driven` never reads
`resolved_config` (COVERAGE §5.1 states it for Actuator's base path and §9 restates it as
per-ENGINE). The first three rows above need nothing but that read. The fourth needs a ruling:
the prefix VALUES are configuration, but which classes receive which prefix is a lambda over
package names (`clazz.getPackage().getName()` matched against `**.controller.admin.**` from
config), and evaluating it is business logic. The honest stop for that one may be to STATE the
prefix in the gaps section rather than publish a path nobody serves.

**Real triggering input:** ordinary, and a pinned corpus already carries it.

*The INBOUND half of the family `OI-111` holds the other half of: there, a gateway's
`StripPrefix`/`PrefixPath` filters change the path sent UPSTREAM while the outbound row carries
the `uri` verbatim. Same shape — a path the framework transforms and the document publishes
untransformed — in the other direction, by another mechanism, and neither fix is the other's.
Filed apart deliberately, cross-referenced so a reader costing "paths we publish wrong" finds
both.*

**Verify:** `grep context-path examples/spring-petclinic-rest/src/main/resources/application.properties`
against `scripts/field-expectations/spring-petclinic-rest.json`'s `routes.inbound`.

**Closes when** a `context-path`-setting module publishes its paths with the prefix, the pin
moves with it, and `ruoyi-vue-pro`'s own prefix is either applied or named as a gap.

> **THE CONFIGURATION HALF IS BUILT (2026-10-18)**, spec
> `2026-10-18-configured-path-prefixes-design.md`.
>
> `catalogs/server-models/spring-boot.yml` declares the keys with the framework and version
> range they were measured on (CP-38, from Boot's own
> `META-INF/spring-configuration-metadata.json` at 2.7.18, 3.5.14 and 4.1.1), and
> `resolve/path_prefix.py` applies them to every inbound row of the protocols the entry
> names — one pass, so a catalog written later is covered without knowing anything about it.
> It runs immediately after `derive_endpoints` and before `record_roots`,
> `record_routing_conflicts` and `record_self_exchange`, which key on the address.
>
> **Measured: `spring-petclinic-rest` publishes all 44 inbound rows under `/petclinic`**,
> where all 44 lacked it. The pin moved in the same commit, reviewed by `OI-32`'s procedure
> and asserted rather than eyeballed: 44 rows before and after, and **every change is the
> prefix alone** — no route gained, lost or otherwise altered.
>
> **What it refuses, which is the half that could have published a wrong address.** A key
> whose environments DISAGREE is refused outright and the row keeps the path it had, because
> choosing one environment's value publishes an address the others do not serve; a module
> whose framework version is outside the measured range takes no prefix (guard
> `path_prefix.a-version-outside-the-measured-range-takes-no-prefix`); `websocket` is not in
> the shipped protocol list, because a handshake path is *probably* under the context path
> and probably is not a measurement.
>
> **`setPathPrefixes` IS BUILT TOO (2026-10-18)**, §4 of the same spec, once the walk's sixth
> edge landed and `getAdminApi()` → the field → the constructor that wrote it began to resolve.
>
> `class_path_prefixes` in `catalogs/server-models/spring-boot.yml` names five framework
> symbols and `resolve/path_prefix.py` reads them: the installer call is the gate, each
> `Map#put` whose second argument is a lambda is an entry, the prefix is that site's argument 0
> and the pattern is the `AntPathMatcher#match` argument inside the lambda body. What makes it
> a READING rather than a guess is the discriminator — `match`'s second argument must come
> from `Package#getName` on `Class#getPackage`, so a map of strings to predicates that is about
> anything else contributes nothing (guard
> `path_prefix.a-package-predicate-is-what-identifies-a-declaration`).
>
> **Measured on `ruoyi-vue-pro`, the three built modules, 480 inbound rows: 472 now carry the
> prefix the app serves them under** — 466 `/admin-api`, 6 `/app-api` — and the 8 that do not
> are `yudao-server`'s own `DefaultController`, whose package (`…server.controller`) matches
> neither pattern and which the app genuinely serves unprefixed. Every row was `/system/...`
> before. `spring-petclinic-rest` and the other five field pins are unchanged.
>
> **One correction to the spec, declared rather than quietly made (GUIDELINES §1.1).** §4 said
> the prefix and its pattern pair *by the site*, on the reasoning that "each `put` is its own
> site". Measured, that is false for the corpus the whole item exists for: ruoyi has ONE `put`
> site, inside a `putPathPrefix` helper called once per API group, so the walk answers both
> prefixes AND both patterns there and pairing by site is a cross product — two of its four
> pairings would serve a package family under another family's prefix. They are paired BY PATH
> instead, through a new `values.resolve_positions`, which is `resolve_site`'s several-sites
> case: both values leave through the same context (the two `new Api(…)` sites in
> `WebProperties#<init>`) and a pair that chose differently there is refused. That is the
> spec's own stated requirement — *"two entries cannot cross"* — met by a mechanism the spec's
> premise did not need to be right about. Pinned by the e2e fixture, whose four controllers
> cover both shapes, and by guard
> `path_prefix.a-prefix-pairs-with-the-pattern-on-ITS-OWN-path`.
>
> **Three wrong rows were reachable from ordinary Java in the first build of this, all three
> found by review on probe modules and all three fixed before the commit.** Each is now a
> conjunct with its own guard and its own controller in the fixture asserting the path it
> keeps:
>
> | what published a wrong address | the row it published | what refuses it now |
> |---|---|---|
> | a map of the same shape handed to NOBODY (`auditCategories()`) | `GET /AUDIT/audit-logs/{id}`, and the same path into `roots` | an entry counts only where the map it writes into is the map an installer receives, compared by the object's ORIGIN — `_origins`, which follows a return into its callee and a parameter to its callers, because `ruoyi`'s `put` is two frames away from its installer |
> | a prefix that is a placeholder | `${api.ext-prefix}/ext/{id}` — not even path-shaped | a prefix must be path-shaped; Spring resolves the key through `embeddedValueResolver` first, so an unresolved one is refused |
> | a functional route whose class merely SITS in a prefixed package | `GET /admin-api/fn/items`, where `RouterFunctionMapping` has no prefixes at all | the predicate's OTHER conjunct, `clazz.isAnnotationPresent(RestController.class)`, read off the lambda and required of the handler's class |
>
> Two under-reports came with them, both ordinary Java and both fixed: a map variable declared
> as `LinkedHashMap` rather than `Map` (javac emits `LinkedHashMap.put`, so the entry is now
> matched on the method name with the identity join doing the identifying), and
> `class MyMapping extends RequestMappingHandlerMapping` (the gate now resolves a subclass
> through the module's own hierarchy). The reactive stack's own `RequestMappingHandlerMapping`
> is declared beside the servlet one for the same reason.
>
> **What §4 still will not do:** read a predicate that tests no annotation at all (what it
> means is "every handler this mapping serves", which is not a set these facts can name), and
> settle a package two patterns claim — the framework applies the first entry of a
> `LinkedHashMap` and the facts do not record that order, so the row keeps the path it had.
> A pattern or prefix a lambda CAPTURES is `OI-150`.

### OI-147 — RocketMQ is catalogued nowhere, and it is absent from COVERAGE as well
**Major · entered 2026-10-18, measured on `ruoyi-vue-pro` · `src/sextant/catalogs/`**

`@RocketMQMessageListener(topic = "${yudao.websocket.sender-rocketmq.topic}")` and
`RocketMQTemplate` derive **nothing** — no row, no gap line. `ruoyi-vue-pro` uses RocketMQ in
19 files and ships it as one of three interchangeable broker backends for its websocket
fan-out; the other two (Kafka, RabbitMQ) both derive rows, so the document presents a
two-broker module where the code offers three.

**Cause:** there is no `rocketmq` catalog, and — unlike every other unsupported surface —
**no COVERAGE row says so either**: `grep -i rocketmq docs/*.md` is empty. Apache RocketMQ is
a mainstream broker, dominant in the ecosystem these corpora come from.

**Real triggering input:** ordinary for any project using it.

**Closes when** a `rocketmq` catalog derives the listener and the template, with the usual
`measured:` block. A COVERAGE row stating the absence is worth having even before that.

### OI-146 — a destination a catalog cannot address drops the row and says nothing
**Major · entered 2026-10-18, measured on `ruoyi-vue-pro` · `src/sextant/application/resolve/engines/annotation_driven.py` (the addresses-nothing gate)**

```java
@RabbitListener(bindings = @QueueBinding(
        value = @Queue(name = "${yudao.websocket.sender-rabbitmq.queue}" + "-" + "#{T(java.util.UUID).randomUUID()}"),
        exchange = @Exchange(name = "${yudao.websocket.sender-rabbitmq.exchange}", type = ExchangeTypes.TOPIC)))
public class RabbitMQWebSocketMessageConsumer { @RabbitHandler public void onMessage(…) { … } }
```

`yudao-spring-boot-starter-websocket`'s document lists two inbound endpoints — the Kafka
consumer and the websocket handler. **This consumer appears nowhere: not as a row, not as an
unresolved derivation, not in Known gaps.** A reader cannot tell the difference between "this
module does not consume from AMQP" and "it does, and the destination could not be read".

**The ADDRESSING boundary is already documented and is not what this entry is about.**
COVERAGE §5.9 states it exactly: no `path_from` alias can name an attribute inside a nested
annotation, and `declaring path_from: [bindings]` would publish a `@QueueBinding`'s JSON text
as a queue name. That reasoning is right. What is wrong is the SILENCE: the addresses-nothing
gate drops the would-be row, and nothing downstream records that a listener was seen.

**Why it matters more than the missing address.** An `unresolved` row with a named handler is
usable — it says a boundary exists here and its destination is unknown, which is what every
other engine does when it cannot read a value (`single_call` publishes `amqp (unresolved)` for
the SENDER in this very module). A dropped row is indistinguishable from absence.

**Real triggering input:** ordinary. `bindings = @QueueBinding(…)` is the idiomatic form for a
listener that declares its own queue, and it is in Spring AMQP's own reference documentation.

**Closes when** a listener whose destination no `path_from` can reach derives an `unresolved`
row naming its handler, or is listed in Known gaps by name. Addressing it properly is the
separate, already-stated COVERAGE item.

*`OI-109` is the nearby case and is NOT this one: a configurer that adds a second queue leaves
the row with its first queue — *"fewer queues, never a wrong one"*. That is an under-report with
a row to hang it on; this is no row at all, which a reader cannot tell from absence.*

### OI-144 — `fluent` takes a whole assembled address or nothing, where `single_call` now takes the half it read · **CLOSED 2026-10-19**
**Major · raised from Minor on measurement (the row is DROPPED, not degraded) · entered 2026-10-18 while implementing spec 2026-10-18 · `src/sextant/application/resolve/engines/fluent.py::_url_argument`**

Spec 2026-10-18 gave `single_call` and `url_of` a third answer for an assembled address:
where the walk read part of it, the row publishes the part it read at `partial`
(`{}/services/admin`). `fluent`'s concat arm asks the same walk one commit earlier and
still takes only a WHOLE literal:

```python
settled = [literal for _, literal, resolution in assembled if resolution == "resolved" and literal]
return {"kind": "string", "value": settled[0]} if len(settled) == 1 else argument
```

So `WebClient.create().uri(host + "/owners/{id}")` publishes `path` NULL where the same
assembly through `restTemplate.exchange` now publishes `/owners/{id}`. **Two engines, two
answers about one piece of evidence** — which is the disease the walk was built to end
(spec 2026-09-22 §0a).

**Why it was NOT widened in the same change, stated rather than quietly skipped.** `fluent`
composes `base + path` and reads both halves with `_string_value`, so carrying an expression
through means deciding what a partly-known base composed with a known path IS — three new
cases (expression base, expression path, both) in a function the spec did not design.

**Re-measured 2026-10-18, and it is worse than this entry said: the row is DROPPED, not
degraded.** One address through the two engines:

```java
restTemplate.getForObject("http://customers-service/owners/" + ownerId + "/pets", …);  // single_call
builder.build().get().uri("http://customers-service/owners/" + ownerId + "/pets");      // fluent
```
```
single_call:  path='/owners/{ownerId}/pets'  peer='customers-service'  partial
fluent:       path=NULL                      peer=NULL                unresolved
```

`customers-service` and the path pattern are both in the facts, and the fluent row publishes
neither. That is three of `spring-petclinic-microservices`'s four genai calls. The
cross-engine lesson of `OI-143` is to carry the QUESTION across engines, and this is it
carried, with its answer deferred rather than guessed.

**Real triggering input:** any fluent client whose address is assembled from a value and a
literal.

> **CLOSED 2026-10-19, and it was the READER rather than the walk.** Two one-line causes, each
> measured on `fixtures/orders-fluentaddress`, where one address is written once through each
> engine:
>
> 1. the assembled-address arm asked `channel_of_answer`, which refuses a template **on
>    purpose** — a broker resolves a destination it is GIVEN and half of one is not a
>    destination — where an HTTP address has the url reader for exactly this case. It now asks
>    `_assembled_text`, which hands back the template VERBATIM: passing `url_of_answer`'s own
>    output back in split the address twice and published nothing, which is why that reader
>    exists rather than reusing the other;
> 2. the row then recomputed `resolved`/`unresolved` from the address, throwing away `partial`
>    even when the reader answered it. It now carries the address's own word, which is
>    `single_call`'s rule verbatim (spec 2026-10-18 §5).
>
> **Measured on a PINNED corpus:** `petclinic-genai-service`'s three blank outbound rows now
> carry their paths —
>
> | | before | after this cause | after `OI-138` cause 3 |
> |---|---|---|---|
> | genai → customers | `GET (unresolved)`, `POST (unresolved)` ×2 | `GET <host>/owners`, `POST <host>/owners`, `POST <host>/owners/{ownerId}/pets` | `GET customers-service /owners`, `POST customers-service /owners`, `POST customers-service /owners/{ownerId}/pets` |
>
> — and the expectation was re-recorded. The other five pins are unchanged, which is the thing
> to check for a change inside an engine every fluent catalog shares.
>
> **The third column is a SECOND cause, closed in the next commit on the same branch**, and
> the middle column is what this one is worth on its own: the path, with the host still
> unread. `OI-138` cause 3 then read the host's service NAME out of
> `discoveryClient.getInstances("customers-service")…getUri()`, so the rows now name the peer
> too. Guard `fluent.an-assembled-address-is-read-with-the-URL-reader`.

### OI-145 — three field pins fail on `terminal_kinds`, and have since a terminal kind landed · **CLOSED 2026-10-18**
**Minor · entered 2026-10-18, found while running the field check for spec 2026-10-18 · `scripts/field-expectations/{jhipster-sample-app,mall-admin,spring-petclinic-rest}.json`**

`scripts/field_check.py` fails on three of its six pins, each the same way:

```
jhipster-sample-app  expected {'persistence/database': 70, 'unresolved': 1071}
                     got      {'persistence/database': 70, 'throws': 40, 'unresolved': 1071}
```

`mall-admin` gains `'throws': 242` and `spring-petclinic-rest` `'throws': 15`. **Endpoint
counts and route sets agree on all six** — only the terminal classification moved.

**It is a stale pin, not a regression.** `throws` became a terminal kind in `211ac499`
(2026-09-12, G-74) and these three pins were never re-recorded against it. Verified by
running the check at `HEAD` with the branch's own changes stashed: byte-identical failure.

**Why it matters, and `OI-32` already argued it.** That entry is the same situation on the
same corpus — `spring-petclinic-rest`'s pinned ROUTES, stale through the whole of 2O — and it
states the cost: *"a suite that is known-red is a suite nobody reads: the next real regression
in these two repositories lands in a check that was already failing, and looks identical to
this."* Written 2026-09-06, closed 2026-09-07, and re-derived here from scratch on 2026-10-18
instead of cited, which is what a duplicate costs even when the instances differ. The instance
IS different — `OI-32` was route spellings after an identity migration, this is
`terminal_kinds` after a terminal kind landed — and the ruling is the same one.

**Real triggering input:** running `scripts/field_check.py`, which is how the pins exist.

**Fix: `OI-32`'s procedure, applied to `terminal_kinds`.** Re-record on the three pins against
current `main`, in a commit that says what moved and why — `field_check.py` calls refreshing a
pin *"a deliberate, reviewed act"*, and `OI-32` is the worked example of doing it properly:
someone looked at the rows, agreed the new values were right, and recorded that they had.

**CLOSED 2026-10-18. The rows were looked at; here is what was seen.**

**Nothing was reclassified — `throws` is purely additive.** Every count these pins already
recorded is identical today, which is the measurement that separates "the corpus gained a kind"
from "a rule stopped matching and its rows fell into `unresolved`":

| pin | unchanged | added |
|---|---|---|
| `jhipster-sample-app` | `persistence/database` 70, `unresolved` 1071 | `throws` **40** |
| `mall-admin` | `persistence/cache` 41, `persistence/database` 199, `unresolved` 5112 | `throws` **242** |
| `spring-petclinic-rest` | `persistence/database` 102, `unresolved` 1972 | `throws` **15** |

*The re-recording script asserts both halves rather than trusting the eye: each prior count must
match, and `throws` must be the only new key.*

**Spot-checked against the upstream source, and each is a real throw exit:**

* `BankAccountResource#updateBankAccount` — 3 terminals, 3 explicit
  `throw new BadRequestAlertException(…)` (lines 80, 83, 87); `partialUpdateBankAccount` the
  same three (114, 117, 121).
* `GeneratedCriteria#addCriterion` — **228** of `mall-admin`'s 242, one per MyBatis-generated
  `*Example` class, each `throw new RuntimeException("Value for condition cannot be null")`.
* `JdbcOwnerRepositoryImpl#findById` — `throw new ObjectRetrievalFailureException(…)` in the
  `EmptyResultDataAccessException` catch; `EntityUtils#getById` — the trailing `throw` after
  its loop.
* `CallMonitoringAspect#invoke` — 3 terminals and **no `throw` in the source**: the method is
  `try { return joinPoint.proceed(); } finally { … synchronized … }`, which javac compiles to
  handler code ending in `athrow`. A true "this trace exits by throwing" and worth naming,
  because the kind holds two shapes — a source `throw` and a compiler-generated rethrow — and
  a reader counting `throws` against source statements will not find them all.

**Cause, for the record:** `throws` became a terminal kind in `211ac499` (2026-09-12, `G-74`),
and nothing re-recorded the pins. Five weeks of red.

**All six pins pass**, which is the first time the field check has been green since
`apollo-portal` joined it.

### OI-143 — a project's own HTTP client wrapper derives nothing, and it is the dominant real shape · **CLOSED 2026-10-21**
**Major · entered 2026-10-18, measured on `apolloconfig/apollo` (530 non-test Java files, 8 modules, commit `ea35677`) · `src/sextant/application/resolve/values.py::_joined`**

> **CLOSED 2026-10-21 — the fifth cause, by the design the user ruled "take your partial
> approach"** (spec `docs/superpowers/specs/2026-10-21-merged-values-design.md`). The
> extractor writes a merged value's CANDIDATES (capability 9.19) instead of a sourceless
> `unresolved`; the walk resolves a merge whose candidates share a ROOT — `x` beside a call
> on `x`, read off two facts and never off what the call does — to `x`'s answers marked
> inexact, published at `partial`; a merge with no root stays `unresolved`, ruling 1
> unchanged. No `substring` entry anywhere: the user refused one parser per string
> manipulation, and the rule never asks what `f` is. Found on the way: the wrapper hands the
> VERB through as a parameter too, so `single_call` now reads it from the same walked
> binding as the path.
>
> **Measured through `analyze` on `apollo-portal` at `ea35677`:** the two addressless
> wrapper rows are **68 rows at `partial`, every one with its verb** — GET 39, POST 14,
> DELETE 8, PUT 7; 65 distinct verb + path pairs — against 68 call sites in the module's
> main sources. The falsifier this entry set ("publishing the 64 call sites' own paths") is
> met, at this commit's 68. `partial`, not `resolved`, on purpose: the authority is a
> discovered service (decision 6 stands) and what `substring` did to the path was never
> read — the row carries each caller's literal as written. The field pin
> (`apollo-portal.json`) moved 10 → 69 outbound rows with this cause beside it.


**The inbound half works on real production code and the outbound half does not.** Measured
across Apollo's four code-bearing modules:

| | rows | resolved |
|---|---|---|
| inbound | **411** | **411 — all of them** |
| outbound | 8 | **0** |

Apollo makes **64** outgoing HTTP calls whose verb AND path are both written at the call
site:

```java
restTemplate.get(env, "apps/{appId}/clusters/{clusterName}/namespaces", ...)
restTemplate.post(env, "apps", app, AppDTO.class)
restTemplate.delete(env, "/apps/{appId}?operator={operator}", appId, operator)
```

64 call sites, 64 distinct verb+path pairs. **None derives a row.** The eight rows that DO
derive point at the wrapper's own internals — `RetryableRestTemplate#doExecute`,
`#exchangeGet` — each with `path` NULL. So the document says this module makes eight calls
to unknown destinations, when it makes 64 to known paths.

**The shape, and why it is not a catalog problem.** `restTemplate` here is not Spring's — it
is Apollo's own `RetryableRestTemplate`, injected through an abstract `API` base class. A
framework catalog cannot name it: it is application code, one project's abstraction. Sextant
catalogs frameworks.

**But the facts are all there, and the blocker is one deferral of mine.** The wrapper funnels
every call into:

```java
restTemplate.exchange(parseHost(service) + path, method, entity, responseType, uriVariables)
```

a concatenation whose `path` operand is a PARAMETER tracing back to those 64 literals
(`bound_to_parameter`, which the walk crosses) and whose host operand is a discovered
service address. `_joined` refuses it, by this rule written into it on 2026-10-17:

> *"an operand that is not exactly one answer — several enumerable answers are several
> possible addresses, and one row per combination is ruling 1's multiplicity rule applied
> across operands. That product is deliberately NOT built here: it needs a path-merge across
> operands that disagree, **nothing in the 27 measured corpora reaches it**, and carrying the
> template under-reports rather than inventing."*

**"Nothing in the 27 measured corpora reaches it" was true and misleading.** The first real
production codebase tried after that sentence was written reaches it 64 times. The corpora
were fixtures plus three field pins that are inbound-only (`OI-138`) — a set that could not
contain the shape, so measuring it said nothing about how rare the shape is. *The lesson is
about the denominator, not the deferral: "nothing in the corpus does X" is a statement about
the corpus whenever the corpus was not chosen to contain X.*

**What happens today:** any project with its own HTTP client wrapper — a very common
structure, and the one Apollo, and most codebases of that size, actually use — publishes its
real outgoing calls nowhere.

**Real triggering input:** ordinary. The thinner the wrapper, the more total the loss.

**Verify:**
```
git clone --depth 1 https://github.com/apolloconfig/apollo.git examples/apollo
cd examples/apollo && mvn -q -B -DskipTests compile
.venv/bin/sextant module analyze examples/apollo/apollo-portal
```
**WHY IT WAS MISSED, which is four parts and the first is the one that stings.** Measured
by probing each in turn on this module:

1. **`single_call` asks the walk only where a catalog declares `channel_via`**
   (`elif "channel_via" in method:`). `spring-resttemplate`'s `exchange` row declares
   `url_arg`, so the walk is never consulted and `url_of` sees a `concat` and gives up.
   **The identical hole was found and fixed in `fluent` on 2026-10-17**, with the reasoning
   written into that file — *"An ASSEMBLED address is not a hop, so it needs no `url_via`"* —
   and the question was never carried to the other two engines. One engine fixed, three
   engines affected, and the argument was already in hand.
2. **`_joined` is all-or-nothing.** The template here is `{}{}` — `parseHost(service) +
   path`, two holes and no literal text. One hole never resolves, so nothing is filled even
   though the other hole is known 64 ways.
3. **Multiplicity across operands was deferred** on "nothing in the 27 measured corpora
   reaches it" — a corpus that could not contain the shape (see above).
4. **An expression address is unpublishable by this engine.** `url_of` requires a plain
   string; `fluent._address_of` publishes a `${…}` expression as a path with `peer` NULL and
   `single_call` has no equivalent. `Resolution.PARTIAL` exists in the closed set and is
   what a half-known address should carry.
5. **A local REASSIGNED between the literal and the call reaches the call as a merge of two
   producers, and no edge follows a merge.** Found by fixing 1–4 and measuring, not by
   reading. It is what still blocks the 64, and it is below the walk — see the block at the
   end of this entry.

*A probe confirmed 2 and 3 alone are not enough: partial fill plus the product, applied
without 1 and 4, left the module at 8 rows and 0 paths — because the walk is not asked and
the answer could not be published if it were. Measured, then reverted.*

**ALL FOUR ARE FIXED, AND IT DOES NOT CLOSE** (spec
`docs/superpowers/specs/2026-10-18-partly-known-addresses-design.md`, 2026-10-18). The
sentence above said *"closes with all four"*; implementing them found a FIFTH cause nobody
had looked for, measured on the same module:

```java
private <T> T execute(HttpMethod method, Env env, String path, …) {
  if (path.startsWith("/")) {
    path = path.substring(1);        // ← reassigned, so the call sees a MERGE
  }
  …
  doExecute(method, extraHeaders, serviceDTO, path, request, responseType, uriVariables);
```

`path` is reassigned one frame above the concat, so the fact for that argument is a bare
`{kind: unresolved}` with **no `source` at all** — one of two producers, and no edge to
follow. The crossing reaches `execute` and stops. **The 64 rows are still not derived.**

**What the four causes DID move, measured on `apollo-portal` before and after on the same
commit:**

| | rows | carrying a path |
|---|---|---|
| before | 8 | **0** |
| after | 10 | **8, at `partial`** |

The eight are real addresses the source states and the document never showed:
`{}/health`, `{}/services/admin`, `{}/services/config`, `{}?env={env}` — each a
`parseHost(service) + "/literal"` whose host is a discovered service. Two rows
(`doExecute`, `exchangeGet`) stay addressless, and they are the 64's funnel. The count rises
by two because `PortalManagementController#getServerAddress` and
`SystemInfoController#getServerAddress` each make TWO calls that were indistinguishable
while both paths were NULL.

**What closing now needs** — one of two pieces of work, neither designed:

* the extractor reporting a merge's CANDIDATES rather than collapsing them to
  `{kind: unresolved}`; or
* a transform model that knows `String#substring` returns a substring of its receiver,
  which is `OI-142`'s identity-versus-rendering question in another form.

Guessing either from here publishes a wrong address at `resolved`, which is the one failure
this work risks. **Falsified by** `apollo-portal` publishing the 64 call sites' own paths.

> **STILL OPEN, re-measured 2026-10-19, and the parenthetical remnant is the only part that
> closed.** The mirror this entry left standing — *"`fluent`'s concat arm still takes only a
> WHOLE literal, so a fluent chain whose assembled address is partly known publishes `path`
> NULL"* — closed as `OI-144`. That is a cross-engine fix and not this entry's own subject.
>
> **The 64 are still not derived.** `apollo-portal` publishes ten outbound rows, and reading
> their callers says exactly which ten they are:
>
> | rows | caller | published |
> |---|---|---|
> | 8 | `SystemInfoController`, `PortalManagementController`, `AdminServiceAddressLocator`, `ConfigReleaseWebhookNotifier` | `<host>/health`, `<host>/services/admin`, `<host>/services/config`, `<host>?env={env}` — at `partial` |
> | 2 | `RetryableRestTemplate#exchangeGet`, `#doExecute` | `path` NULL, `unresolved` |
>
> The eight are calls a controller makes on `restTemplate` DIRECTLY. The two addressless rows
> are the wrapper, and they are the 64's funnel — which is what this entry said when it was
> written and is still what blocks it. So the eight pathful rows are evidence that `partial`
> works, not that this closed; counting them as the 64 would be reading the row total instead
> of the callers.
>
> *Checked because the remnant's closure made the entry look closable. It is not.*

*A mirror left standing, named rather than quietly widened: `fluent`'s concat arm still
takes only a WHOLE literal (`_url_argument`, `len(settled) == 1`), so a fluent chain whose
assembled address is partly known publishes `path` NULL where `single_call` now publishes
the half it read. It needs `_url_argument` to carry an expression through the `base`
composition, which this spec did not design — `OI-144`.*

*Carried across in passing, since it was the same cross-engine miss in the same file pair:
`interface_implementation` and `single_call` were still calling `value_index` rather than the
shared `cached_value_index` that `fluent` got on 2026-10-17. **Measured, and it buys nothing
worth naming** — 0.05s on `mall-admin`, 0.02s on `apollo-portal`, because one already folded
lazily once per run and the other only fires for catalogs that reach the walk. Kept for
consistency, and recorded as no speed-up rather than claimed as one.*

### OI-142 — a service name five calls back resolves; publishing it as a PEER does not · **CLOSED 2026-10-19**
**Minor · entered 2026-10-17, HALF BUILT the same day · `src/sextant/catalogs/value-models/spring-cloud.yml`, `src/sextant/application/resolve/values.py`, probe `scripts/probes/cp36_discovery_client.md`**

> **The grammar half is built and measured. The publishing half is not, and it needs
> ruling 2's plumbing rather than more identity work.**
>
> **What shipped.** `identified_by` gained a third form, `from_receiver: true` — "my
> result stands for whatever my RECEIVER stands for" — because `arg` could not express
> it: `List.get(int)`'s argument is an index and `ServiceInstance.getUri()` takes nothing
> (CP-36 rows 1 and 3). Three entries declare the chain, and
> `values._through_receiver` resolves it.
>
> **What makes an entry on a JDK accessor safe, measured rather than argued.** The
> user's point of 2026-10-17: every instance of a service IS that service, so element
> access preserves the identity. The gate is the walk's own multiplicity — a
> SINGLE-VALUED identity resolves to one answer and propagates; an ENUMERATING one
> (`all_strings`) resolves to several and is refused, because an element of a collection
> identified as many things is one of them and which one is unknowable. Over the shipped
> table of 23 entries: three are enumerating and all three are topic lists (`List.of`,
> `Arrays.asList`, `Subscriptions.topics`), and of the twenty single-valued ones exactly
> one produces a collection — `Collections.singletonList` at `arg: 0`, where
> `singletonList("x").get(0)` IS `x`. The gate is therefore the exact line between the
> entries that must not propagate and every other entry. Guard
> `values.an-enumerating-identity-is-not-preserved-through-a-receiver` kills on it.
>
> **PROVEN end to end, by a throwaway entry that was measured and reverted.** With one
> more identity — `java.lang.String#valueOf` at `arg: 0`, which javac inserts around a
> non-String concat operand — the chain resolves **five hops**:
>
> ```
> uri(concat "{}/owners")  ->  makeConcatWithConstants  ->  String.valueOf
>   ->  getCustomerServiceUri()  ->  getUri()  ->  get(0)  ->  getInstances("customers-service")
> ```
>
> and answers `customers-service/owners`.
>
> **And that is why it is not shipped.** `customers-service` is a service NAME, not a
> host with a scheme, so joining it into the template produces a string `split_url` reads
> as a relative path: `peer` stays NULL and the path column carries both halves. The row
> would be more informative than today's NULL and still miss the arrow, which is the
> thing the document is for.
>
> **What remains is ruling 2, and it cannot be inferred from the string.** The user
> granted "peer and path from separate evidence" for exactly this case. The engine would
> need to know that the resolved operand MEANS a peer — and no shape test can tell it:
> `basePath + "/orders"` where `basePath = "/api/v1"` has the same shape and `/api/v1` is
> not a peer. `role` is not the hook either: it says WHICH PART of a composite value an
> argument is (`new ProducerRecord(topic, …, payload)`), not what the value means to a
> consumer, and `_identity_matches` skips roled entries by design.
>
> **THE AUTHORITY WORD IS NOW BUILT TOO** (`yields: authority`, 2026-10-17): an identity
> entry declares what KIND of thing it yields, the answer carries it through every hop, and
> a join whose hole yields an authority is written scheme-relative — `//customers-service/owners`,
> RFC 3986 §4.2, a real URI form rather than an invention, with the `//` saying exactly
> where the authority ends. `split_url`'s scheme is now optional so one splitter answers
> both shapes, and the `/api/v1` counter-example is pinned: an identity yielding an
> `address` is joined verbatim, because marking it would publish `api` as a service.
>
> **AND THE CHAIN STILL CANNOT BE CLOSED, for a reason that is worth more than the three
> rows.** javac inserts `String.valueOf` around a non-String concat operand, so the chain
> runs through it — and `String.valueOf` cannot be declared as an identity for this purpose.
> Read off the JDK's own bytecode, `valueOf(Object)` returns `arg.toString()`. An
> `identified_by` entry says what a value STANDS FOR; a join publishes text as an ADDRESS;
> **those are different claims and they part company exactly where it matters.** For a
> `URI` the identity and the rendering coincide. For a messaging destination whose identity
> is `"orders"`, `toString()` is a vendor debug string — so joining the identity would
> publish an address that never existed, at `resolved`, which is the one failure spec §7
> names.
>
> **What keeps the shipped join sound is `fluent._url_argument` passing NO identities** for
> an assembled address, so only text the code literally states is ever joined. That was
> chosen for a different reason (not following undeclared hops) and is load-bearing for
> this one; the comment there now says so.
>
> **Closes** when the walk can distinguish a value's IDENTITY from its textual RENDERING —
> the conflation above — so a join may use the second and a peer the first. That is a
> third property on an answer, not a fourth identity form, and it is design work rather
> than a key. **Falsified by** those three rows publishing peer `customers-service` with
> paths `/owners` and `/owners/{}/pets`.
>
> **CLOSED 2026-10-19 BY ITS OWN FALSIFIER**: those three rows publish peer
> `customers-service` with paths `/owners` and `/owners/{}/pets`, and
> `spring-petclinic-customers-service` serves exactly those. `OI-138` cause 3 carries what was
> built.
>
> **The closure line above predicted the wrong mechanism, which is worth more than the three
> rows.** It asked for a third property on an answer so that *a join may use the rendering and
> a peer the identity*. What the ruling actually needed was not to make the join carry the peer
> at all: the join still gets no identities, and the PEER is asked as its own question of the
> address's first operand, accepting only an answer that yields an authority — "peer and path
> from separate evidence" taken literally rather than as a property threaded through one value.
> The only new key is `preserves: authority` on the one rendering entry, which bounds
> `String.valueOf` to the case this entry's own objection does not reach. That objection was
> right, which is why the gate exists rather than the entry shipping bare.

#### How it was first measured, 2026-10-17 — and the words that were missing then
*This was filed as a second entry under the number `OI-142`, which made every citation of
`OI-142` ambiguous. It is the same defect at an earlier stage, so it is folded in here
rather than left as a rival entry; nothing below is edited, only re-headed. The grammar it
says is missing — "my result stands for whatever my RECEIVER stands for" — SHIPPED on
2026-10-17 as `from_receiver`, with the type gate this block asks for, which is the
"HALF BUILT" above.*

**Minor · entered 2026-10-17, measured at plan `2026-10-17-outgoing-endpoint-addresses.md` Task 4 · `src/sextant/catalogs/value-models/`, `docs/components/D02-catalog-schema.md` §1f**

`spring-petclinic-genai-service` calls `customers-service` three times, and the document
publishes `path` NULL for all three. The code:

```java
private URI getCustomerServiceUri() {
    return discoveryClient.getInstances("customers-service").get(0).getUri();
}
...
.uri(getCustomerServiceUri() + "/owners")
```

**Everything needed is readable.** There is no URL in that class file at all — verified,
zero occurrences of `http://` — because the address is resolved from a registry at run
time. What IS there: the service name as a plain literal, and the path in the concat's
template. `ServiceInstance.createUri` builds from `%s://%s:%s`, so the runtime URI carries
no path and `/owners` is the WHOLE path rather than a suffix of one (measured from
spring-cloud-commons 5.0.0).

**The obstacle is the identity grammar, measured on the facts.** The chain is three call
sites:

```
ord=0  getInstances("customers-service")   result=5
ord=1  get(0)         receiver=5           result=7
ord=2  getUri()       receiver=7           result=9
```

`identified_by` answers *"which ARGUMENT of a call carries the value its result stands
for"* (D02 §1f). `getInstances` fits — argument 0. The other two do not: `get(0)`'s
argument is an int index, and `getUri()` has no arguments at all. What both need to say is
*"my result stands for whatever my RECEIVER stands for"*, and the grammar has no such
entry — `method` and `arg` are required, and `role` names a purpose rather than a source.

**And the obvious widening is a fabrication.** An entry declaring that `List.get`
preserves its receiver's identity is read by every catalog at once, over every list in the
estate. A `List<String>` of topics whose identity is `all_strings` would then answer the
whole list for `get(0)` — one element reported as every element. The type that makes it
safe here (`List<ServiceInstance>`) is not something the entry can name: `arity` and
`descriptor` discriminate overloads, and `List.get(int)` has exactly one.

**What happens today:** three outbound rows carry `path` NULL and `peer` NULL, so the
document says this service calls something over HTTP three times and will not say what.

**Real triggering input:** ordinary for a service-discovery client that resolves addresses
itself rather than through a load-balanced template.

**Verify:** `grep -n "getCustomerServiceUri" -A 2` on `AIDataProvider.java`, then
`grep -c "http://"` on its class file (0).
**Closes** by a receiver-preserving identity entry plus the type gate that keeps it off
every other `List` — Task 8 of the previous plan built `_producer_conforms` for exactly
this class of borrow, so the gate exists and the entry does not. **Falsified by** those
three rows publishing peer `customers-service` with paths `/owners` and `/owners/{}/pets`.

*Ruling 2 (peer and path from separate evidence) was granted for this case and is NOT the
blocker — there is simply no evidence to put in the peer column until the identity above
can be stated.*

### OI-141 — a binding's literal value is not a fact, and it is worth one row today
**Minor · entered 2026-10-17, measured at plan `2026-10-17-outgoing-endpoint-addresses.md` Task 3 · `extractor-jvm/.../MethodFlow.java::fieldWrites`, `src/sextant/storage/duckdb/value_edges.sql`, `src/sextant/application/resolve/values.py`**

`field_write` can say *"field F holds parameter N"* and cannot say *"field F holds this
constant"*. `MethodFlow.fieldWrites` requires the middle instruction of its triple to be a
`VarInsnNode`; an `ldc` is not one, so a field initialised with a literal emits nothing.
Measured at `scripts/probes/cp33_binding_writes.md` row 8, the shape is
`aload_0; invokespecial; aload_0; ldc; putfield` — **inside `<init>`**, so the existing
constructor filter already admits it and only the grammar refuses. **This is NOT capability
9.19** (`OI-136`), which is a write OUTSIDE an initialiser and a method-filter change.

**The yield, measured over every built corpus.** Shadow mode answers `no_writer` at 11
positions. One is this shape:

| shape | positions | reached by this? |
|---|---|---|
| `@Value("${…}")` field or parameter | 5 | no — configuration, which §8.2 forbids joining |
| a `static final` that is not a compile-time constant | 1 | no — `ldc; putstatic`, no receiver load (CP-33 row 6) |
| shadow over-match (a catalog the engines never run there) | 4 | no — not a real ask |
| **a plain instance-field initialiser** | **1** | **yes** — `VisitsServiceClient#hostname` |

**Three structural costs against that one row**, which is why it is filed rather than built:

1. a fact-grammar change in the extractor;
2. a **partial** `written_by` arm in `value_edges.sql`, whose own comment explains the kind
   is absent rather than empty *because "the walk has not looked"* — a partial arm makes
   `no_writer` mean either "no constant write" or "the capability is absent";
3. a second reader of `field_write`. `values.py` refuses one by name: *"giving it a second
   home in the walk is how one answer becomes two spellings that drift."* The field ladder
   reads `from_parameter` for `@Value` expressions today.

*Cost 3 may be smaller than it reads, and whoever picks this up should check rather than
inherit the sentence: the two arms would be DISJOINT — a field assigned a parameter carries
no constant and a field assigned a constant names no parameter — so they are two readers of
two fields, not two spellings of one answer.*

**What happens today:** `VisitsServiceClient` publishes an outbound row with `path` NULL. The
walk joins the concat around the hole (`OI-138` cause 1, shipped) and the hole itself answers
`no_writer`, so the template is carried verbatim and no address is published.

**Real triggering input:** ordinary — a client holding its base URL in a non-final field. It
is one row in this estate, which is the whole reason this is deferred.

**Verify:** `grep -n "VarInsnNode valueLoad" extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java`.
**Closes** by `field_write` carrying a constant value beside the parameter ordinal, an arm
in `value_edges.sql` reading it, and `values._resolve`'s binding arm following that edge —
with `no_writer`'s two meanings separated. **Falsified by** `VisitsServiceClient` publishing
`http://visits-service/pets/visits?petId={petId}`.

**Note for the shape, not the fix:** that field also has a package-private `setHostname`
written "for testing purpose" and called from no main-source code, so the binding has two
writers. Resolving it is ruling 1's multiplicity — one row per enumerable answer — not a
single address, the day capability 9.19 makes the setter visible.

*A THIRD shape in this family, measured 2026-10-18 (`ruoyi-vue-pro`): a field holding a
CONSTRUCTED object. `WebProperties` declares
`private Api adminApi = new Api("/admin-api", "**.controller.admin.**")`, which compiles to
`aload_0; new; dup; ldc; ldc; invokespecial; putfield` — the middle instruction is an
`invokespecial`, so `fieldWrites`' `VarInsnNode` requirement refuses it exactly as it refuses
the `ldc` shape. Both literals are in the facts at `WebProperties#<init>` ordinals 1 and 2 and
neither is reachable from the field. It is the same capability as this entry's own shape.
**Measured again 2026-10-18 after the sixth edge landed: both literals now resolve** —
`getPrefix()` answers `/admin-api` and `/app-api` — because the field's writer is the
constructor and its parameter follows its callers to those two sites. That unblocked
`setPathPrefixes` (`OI-148` §4, now closed); what this entry still holds is the shape where
nothing is written from a PARAMETER at all.*

*A real-project instance, 2026-10-18 (`ruoyi-vue-pro`): the websocket endpoint's own path.
`YudaoWebSocketAutoConfiguration` registers the handler with*

```java
.addHandler(webSocketHandler, webSocketProperties.getPath())      // WebSocketProperties: private String path = "/ws";
```

*and the row publishes `websocket (unresolved)` where the served path is `/ws`. The default is
a FIELD INITIALISED WITH A LITERAL — exactly the `ldc` shape this entry is about — so the value
is in the bytecode and the grammar cannot say it. The getter hop on top of it is `OI-106`'s
rung. One row, and it is the whole websocket surface of that module.*

### OI-140 — a resolved gateway route renders as three kinds of "unresolved" · **CLOSED 2026-10-17**

> **CLOSED. The verb was the last of the four and the user ruled it: fan out, but only to
> methods that are SUPPORTED, not invalid ones.** Both gateway catalogs now declare
> `all_methods`, so a route declaring no `Method=` is one row per method — the config form
> through a new fan-out in `config_join`, the DSL form through `combinator._fanned`, which
> already had it. `scripts/probes/cp29_gateway_properties.md` Q11 is what makes all eight
> honest: `HttpMethod` appears **zero** times in `RouteDefinitionRouteLocator`, so route
> construction cannot constrain a method it never names. The route that declares
> `Method=GET,POST` is NOT widened, the unresolved routes are NOT fanned (one doubt must
> not read as eight facts), and the outbound forward targets are NOT fanned (one
> destination, not eight rows saying it). `RouterFunctions.resources(...)` is why the router
> catalog still declines `all_methods`: it serves three methods, so a fan-out there would
> publish five routes nobody can call.
>
> `spring-petclinic-api-gateway` now reads `GET /api/vet/**` … `TRACE /api/vet/**` where it
> read `(unresolved) /api/vet/**` — 36 inbound rows where there were 8 this morning and 4
> yesterday.
>
> **Closed earlier the same day: the format and the two symbol columns.** `Format.ANY` now carries "no format
> constraint exists" as a resolved answer (user ruling), and `_peer_cell` /
> `_handler_fallback` carry "this evidence held no such symbol" instead of printing
> `unresolved` or the literal `None`. **Still open: the VERB.** It renders
> `(unresolved)` and the choice between fanning the route out over `all_methods` and
> rendering one row's absent verb as `any` is unmade — see the bottom of this entry.
>
> **The peer half was far wider than this entry's title.** Measured: EVERY messaging
> outbound row in the estate printed `Peer: unresolved` — `kafka order-events`,
> `jms audit.queue`, `websocket /topic/order-placed`, `soap {…}stubCharge` — while D02 §3
> keeps messaging peers NULL *deliberately*. Nothing in the codebase ever tries and fails
> to read a peer: one appears only when the address was absolute and `split_url` had an
> authority to separate off. So `unresolved` reported a failure that never happened, on
> every such row, and the gateway rows were how it was noticed rather than its extent.
**Major · entered 2026-10-17, found at plan `2026-10-17-outgoing-endpoint-addresses.md` Task 1 · `src/sextant/egress/render/`**

With `OI-139` fixed, `spring-petclinic-api-gateway`'s four routes derive correctly — and the
document renders them like this:

```
| Endpoint                             | Peer       | Caller | Format     | Resolution |
| `(unresolved) lb://vets-service`     | unresolved | `None` | unresolved | resolved   |
```

**Every cell on that row is literally correct and the row as a whole is unreadable.** The
stored row is `{method: None, path: 'lb://vets-service', peer: None, caller: None,
format: None, format_resolution: 'unresolved', resolution: 'resolved'}` — **three deliberate
blanks, one genuine unknown, and one "yes, we worked it out", with the first four printed
using the same word**:

* **the method** is blank BY DESIGN — a gateway route with no `Method=` predicate forwards
  every verb, which is the framework's own catch-all and is recorded as resolved on purpose
  (COVERAGE §5.1). The renderer prints `(unresolved)` in the verb's position, so the
  Endpoint cell reads as a failure while carrying a perfectly good address;
* **the peer** is blank BY DESIGN — D02 §3 keeps a routing destination whole, so
  `lb://vets-service` is the `path` and splitting it would publish an empty path;
* **the caller** is blank BY DESIGN — a route declared in configuration has no handler
  method — and it prints as the bare string `None`, a Python value reaching a published
  document, which is a defect on any reading;
* **the format** is the one HONEST unknown: a gateway forwards whatever body arrives and
  nothing declares a format, so `format_resolution` really is `unresolved`.

*(Corrected 2026-10-17: this paragraph first said "three NULLs" and then listed four cells,
without separating the deliberate blanks from the genuine unknown. The distinction is the
whole fix, so conflating them in the entry that asks for it was worth putting right.)*

A reader concludes the target is unknown. It is the one thing on the row that IS known.

**Pre-existing, not introduced by `OI-139`.** Measured: `fixtures/orders-gateway` renders
`(unresolved) http://ab-service | unresolved | … | unresolved | resolved` and has since
gateway support shipped. `OI-139` only made it visible on a real system, where four of the
module's six outgoing rows are gateway routes.

**On the grade.** Major on the deliverable's own terms (user ruling 2026-10-17: *"the table
isn't the result. it's intermediary"*). No row is wrong, but the document communicates the
opposite of what it derived, which is a worse outcome than a blank — a blank invites a
question, a contradiction invites a wrong conclusion. And `None` in a published cell is a
defect on any reading.

**What happens today:** every Spring Cloud Gateway module's route table reads as unresolved.

**Real triggering input:** ordinary — every gateway module, in either the DSL or the
properties form.

**Verify:** `sed -n '/## Outbound endpoints/,/^---/p'` on any rendered gateway module.
**Closes** by rendering a deliberate blank differently from a failed read — the data already
distinguishes them, since `resolution` is `resolved` while `format_resolution` is
`unresolved` on the very same row — and by never printing `None`. "Not applicable" and
"could not read it" must not share a word. **Moves existing pinned output** (`orders-gateway`'s e2e rows and the
`petclinic-api-gateway` field pin both record today's text verbatim), so it is a task of its
own rather than a fix in passing.

### OI-139 — a chain of imported BOMs is not followed, so a gateway's whole route table derives nothing · **CLOSED 2026-10-19**
**Major · entered 2026-10-17, measured on `spring-petclinic-microservices` · `src/sextant/ingress/detect/` Maven version resolution, `src/sextant/catalogs/spring-cloud-gateway-properties.yml` `detect.coordinates`**

**Measured on Spring's own reference microservice app.** `spring-petclinic-api-gateway`
declares four routes in `application.yml`, and all 24 config entries are read into
`config_entries` — every `uri: lb://…` and every `Path=…` predicate is present in the
workspace:

```
spring.cloud.gateway.server.webflux.routes[0].uri          lb://vets-service
spring.cloud.gateway.server.webflux.routes[0].predicates[0] Path=/api/vet/**
…routes[1] visits-service · routes[2] customers-service · routes[3] genai-service
```

**Nothing derives from any of them, in either direction.** Not the four inbound paths the
gateway serves, not the four outbound targets it forwards to. That is the entire
service-to-service topology of the application — eight rows — and the document shows none of
it. (In the pinned corpus the four `lb://` routes appear only in an LLM *enrichment*
paragraph, which is evidence of the gap rather than cover for it.)

**TWO causes, both small, both PROVEN end to end 2026-10-17 by a throwaway patch that was
measured and reverted: 6 endpoints → 14, every one of the eight missing rows appearing as
`resolved`.** *(This entry first named "one level of BOM import is followed, a chain is not".
That was wrong — inferred from the symptom instead of read from the code. Nested imports,
BOM-scoped properties and a depth cap of 16 are all already implemented and correct.)*

**Cause 1 — `${project.version}` is a Maven BUILT-IN that `_interpolated` does not define.**
`detect/maven.py::_interpolated` substitutes only from a pom's `<properties>` block, so
`${project.version}` never resolves and returns `None`. `_managed_versions` then does this:

```python
settled = _interpolated(managed_raw, bom_properties)
if settled is not None:
    imported.setdefault(managed_coordinate, settled)
```

No `else`. **The managed entry is dropped with no message**, which is why the symptom read as
"the BOM was never opened". Measured: every one of the four dependencies this module reports
unresolved is managed as `version: ${project.version}` — 6 of 8 entries in
`spring-cloud-gateway-dependencies`, 4 of 29 in `spring-cloud-netflix-dependencies`, 4 of 13 in
`spring-cloud-config-dependencies`, 5 of 8 in `spring-cloud-circuitbreaker-dependencies`.
It is the standard way a Spring Cloud component BOM versions its own artifacts.

Injecting `project.version` into the BOM's own property scope (the version the import names)
took `dependencies_not_resolved` from **4 to 0**.

**Cause 2 — the catalog's `detect.coordinates` omits the new starter name.** With the versions
resolved the catalog was still skipped, and `metadata.json` named the reason exactly:

> a build declaration of one of `spring-cloud-gateway-server-webflux`,
> `spring-cloud-starter-gateway`, `spring-cloud-gateway-server` — this module's build declares
> and inherits none of them

The module declares **`spring-cloud-starter-gateway-server-webflux`**, the 5.0.0 starter, which
is none of those three (`spring-cloud-starter-gateway` is the pre-5.0 name). A transitive-only
arrival is deliberately not counted, so the starter must be listed. COVERAGE already carries
this half as `gateway-detect-4x-coordinate`, Minor — the register read it as cosmetic because
nobody had measured what it costs.

Adding the coordinate, on top of cause 1, produced all eight rows:

| direction | derived |
|---|---|
| inbound | `/api/customer/**`, `/api/genai/**`, `/api/vet/**`, `/api/visit/**` |
| outbound | `lb://customers-service`, `lb://genai-service`, `lb://vets-service`, `lb://visits-service` |

**On the grade.** Major, and the grade is about cause 1: a silently dropped managed version makes
every gated catalog miss on any Spring Cloud module that versions through the documented BOM, not
only this one. Cause 2 is one line in one catalog.

**What happens today:** a Spring Cloud module pinning versions the documented way reports four
dependencies unresolved and derives nothing from any catalog gated on them.

**Verify:**
```
.venv/bin/sextant module analyze examples/spring-petclinic-microservices/spring-petclinic-api-gateway
.venv/bin/python -c "import json;print(json.load(open('…/.sextant/metadata.json'))['skipped_catalogs'])"
```
**Closes** by defining Maven's built-in `project.*` properties per pom as the inheritance walk
visits it, by REPORTING a managed entry whose version cannot be interpolated instead of dropping
it, and by listing the 5.0.0 starter in the catalog. The walk itself needs no change: it already
follows `<parent>` links and `<scope>import</scope>` entries to a depth of 16, and this chain is
2. Spec `docs/superpowers/specs/2026-10-17-outgoing-endpoint-addresses-design.md` §5a.

**Falsified by** that module deriving four inbound and four outbound rows for its declared
routes.

> **CLOSED 2026-10-19 — and it closed in the code on 2026-10-17, with nothing written here.**
> Both causes are implemented and carry their own dated comments: `maven.py` defines Maven's
> `project.*` built-ins per pom (`"project.version": version`, with the BOM's own scope getting
> the version the import names), and the catalog lists
> `org.springframework.cloud:spring-cloud-starter-gateway-server-webflux` beside the three it
> had. Re-measured today on the pinned commit:
>
> | | entered 2026-10-17 | 2026-10-19 |
> |---|---|---|
> | `dependencies_not_resolved` | 4 | **0** |
> | `spring-cloud-gateway-properties` skipped | yes | **no** |
> | rows for the four declared routes | 0 | **4 outbound `lb://…`, 32 inbound** |
>
> The inbound count is 32 rather than 4 and that is the shipped rule, not a surprise: a
> `Path=` predicate names no method, so Spring accepts every method and each is its own row
> (8 verbs x 4 routes). The whole service-to-service topology this entry said the document
> showed none of is in the document.
>
> **The register went two days saying a fixed Major was open**, which is the failure its own
> header names — and it mattered: this entry was still being counted against Spring Boot
> while the work it describes was already shipped. Found by re-reading the register's open
> Majors against measurement rather than against itself.

### OI-138 — outbound addresses are 1 of 6 on a real multi-service Spring Boot system
**Major · entered 2026-10-17, measured on `spring-petclinic-microservices` at `c649978a` · `src/sextant/application/resolve/shapes/arguments.py::channel_of_answer`, spec `2026-09-22-value-resolution-design.md` §6, `docs/components/D00-fact-schema.md` §5's `field_write`**

**Measured, on eight built modules of a real Spring Boot microservice system:**

| | derived | resolved |
|---|---|---|
| inbound | 17 | **17 — 100%** |
| outbound | 6 | **1 — 17%** |

The inbound half is complete. The one outbound that resolved,
`GET /owners/{ownerId}` from `spring-petclinic-api-gateway`, matches
`spring-petclinic-customers-service`'s own inbound row — **so the service-to-service link
mechanism works**; five of six addresses are simply unreadable. And the one that worked is
the only one written as a plain literal: `.uri("http://customers-service/owners/{ownerId}",
ownerId)`.

**Why this was not visible before.** No field pin exercised an outbound address. The three
pinned upstreams are inbound-only *because the upstreams are* — `jhipster-sample-app` and
`spring-petclinic-rest` contain no `RestTemplate`/`WebClient`/`@FeignClient`, and `mall`'s
eleven are in `mall-demo` rather than the pinned `mall-admin`. So every "what would this
buy" figure measured over fixtures plus these corpora was weighted toward inbound, which is
how `OI-136` priced a capability at 2% that is a third of this system's outbound column.
**Closed as of this entry**: `petclinic-api-gateway` and `petclinic-genai-service` are now
pinned, so a change here moves a field number.

**Four distinct causes, each with its own closure. They interlock — the second fills the
first's hole — which is why they are one entry.**

**1. A concatenation is never evaluated, even when every operand resolves.** Affects **5 of
6**. The walk already does the hard part: on `VisitsServiceClient#getVisitsForPets` the
shadow table holds `answer_kind: expression`, `value: {}pets/visits?petId={petId}`,
`outcome: would_resolve`. `channel_of_answer` then refuses it — *"a template is not [a
destination], and filling a hole is what §8.2 forbids"* — and `path` publishes NULL rather
than the template. **Closes** by a ruling on spec §6: §8.2 bounds CONFIGURATION a deployment
overrides, and a field initialiser's literal is a code fact, so evaluating a concatenation
all of whose operands resolved to code literals fills no deployment hole. The narrow version
publishes the template; the full version evaluates it.

**2. `field_write` cannot carry a constant, only `from_parameter`.** Affects **1 of 6** — the
hole in cause 1's template. `private String hostname = "http://visits-service/"`. **This is
NOT capability 9.19 and not what `OI-136` deferred**: measured at `cp33_binding_writes.md`
row 8, a field initialiser compiles to `aload_0; invokespecial; aload_0; ldc; putfield` —
inside `<init>`, so the existing constructor filter already passes it. The fact grammar is
the whole obstacle. **Closes** by `field_write` carrying a constant value beside the
parameter ordinal — strictly smaller than lifting the `<init>` guard. With cause 1, this
yields `http://visits-service/pets/visits?petId={petId}` from code facts alone, which
matches `spring-petclinic-visits-service`'s own inbound rows.

> **BUILT 2026-10-18, and cause 1 was already closed before it.** `field_write` now carries
> `value` — the constant as an argument-grammar entry — beside `from_parameter`, exactly one
> of the two per fact, both optional, so `FACT_SCHEMA_VERSION` does not move. `value_index`
> folds those constants and `_binding` answers with the literal directly: a constant write
> needs no crossing, because the value is in the fact. Guard
> `values.a-binding-written-from-a-CONSTANT-answers-that-constant`, pinned by
> `fixtures/orders-fieldheld`'s `DeadLetterPublisher`, whose field is non-`final` for a
> reason the fixture states (a `final` constant-initialised String field is a *constant
> variable*, JLS 4.12.4, and javac resolves reads of one at the use site).
>
> **Cause 1 needed nothing: it closed on 2026-10-18 in `#43`**, the day after this entry was
> written. `_joined` fills every hole it can read and a fully-read template becomes a
> `literal` — the code says so in as many words. Verified by probe rather than by reading:
> `.uri(base + "pets/visits")` with `base` a local holding a literal publishes
> `peer=visits-service, path=/pets/visits, resolved` through the fluent engine. The entry's
> *"a concatenation is never evaluated, even when every operand resolves"* was true when
> written and stale within a day.
>
> **Measured, the pinned corpus moved:** `petclinic-api-gateway`'s
> `VisitsServiceClient.getVisitsForPets` published `path` NULL and now publishes
> `GET /pets/visits?petId={petId}` with `peer='visits-service'` at `resolved` — and
> `spring-petclinic-visits-service` serves `GET /pets/visits`, so the two sides agree on the
> peer and on the path. The field expectation was re-recorded in the same commit
> (`GET (unresolved)` → `GET /pets/visits?petId={petId}`), the other five pins unchanged.
> **Outbound across the system is now 3 of 6**, not 1: the two literal-addressed calls plus
> this one. The three left are cause 3's.
>
> **The yield is one row, measured before building rather than claimed after.** A census over
> every compiled module under `examples/` — 3,568 classes in 56 modules, 9 corpora — counts
> **25** constant field writes (23 String, 2 long) and exactly one of them an ADDRESS: javac
> resolves a `final` constant-initialised field at the use site, and most hosts arrive by
> injection or configuration. The change ships anyway because `no_writer` about a literal in
> the same file is a FALSE statement at any frequency, and the fixtures gained 44 new facts
> on the same shape.
>
> **Review found four wrong rows before this was committed, all four fixed in it.** Each
> published a value at `resolved` that the code cannot produce, and none was reachable by any
> test in the suite:
>
> | what published a wrong value | the fix |
> |---|---|
> | a constant a LATER write in the same basic block overwrites (`private String topic = "default";` beside `this.topic = topic;` in one constructor) | the extractor drops a write its own block overwrites; a later write behind a BRANCH leaves the earlier live, so that one is still reported |
> | a constant written by a `private` method nothing calls — a reset helper, a test hook | the fold skips a write whose method is private AND uncalled: private is unreachable from outside its class, so no caller means no execution. A public uncalled method is merely called by something unscanned, and is kept |
> | a `class` constant (`private Class<Order> t = Order.class;`) made `_binding` return an EMPTY tuple, which dropped **every slot of the site** — losing an address the sixth edge had resolved | an entry the walk cannot read answers `not_readable`, never nothing |
> | `field_writes.value` exported **unredacted**: `private String endpoint = "https://alice:s3cr3t@…"` reached the bundle in the clear beside the same literal masked in `raw_facts` | the column joined the redaction union and the export's masking join, and `test_the_three_unpinned_redaction_joins_actually_mask` carries a row for it |
>
> Two more came with them: the additivity harness had been blinded on exactly the files this
> change touches (`value` is also an ARGUMENT-grammar key, so stripping it from BOTH sides
> let a silently changed address read as additive — it now strips only the after side and
> prints which KINDS were added), and `docs/components/D00-fact-schema.md` still described
> the fact as constructors-only with "anything but a parameter load emits nothing".
>
> **Still over-reported, and narrower than what was fixed:** an initialiser overwritten on
> EVERY branch of an if/else (`f = "a"; if (p) f = "b"; else f = "c";` publishes three values
> where two are live). Dropping it needs post-dominance rather than a block comparison.
> **Still under-reported:** an inherited field, where javac spells the subclass's write
> against the subclass symbol while the superclass's read names its own — so the two do not
> join. That shape applied to parameter writes before this change too.

**3. `DiscoveryClient` is catalogued nowhere.** Affects **4 of 6**.
`discoveryClient.getInstances("customers-service").get(0).getUri()` answers `external` —
correctly, the URL is assigned at runtime. But **the service NAME is a literal argument we
already read**, and a peer of `customers-service` with path `/owners` is exactly what an
architecture document wants. Only Spring Cloud Gateway's `lb://` form is modelled
(`spring-cloud-gateway-outbound.yml`). **Closes** with one catalog reading
`getInstances(String)`/`DiscoveryClient` into `peer` — tier A, one YAML and a probe.


> **BUILT 2026-10-19, and cause 3's own closure line was wrong — it is not "one YAML and a
> probe".** The catalog half shipped a day earlier (`OI-142`: `from_receiver`,
> `yields: authority`, three entries in `value-models/spring-cloud.yml`). Measured on the
> genai module with the whole identity table passed, the chain still answered `{}/owners`:
> two things blocked it, and `OI-142` had named one of them.
>
> **1. javac's `String.valueOf`.** It sits between `getUri()` and the template, inserted
> around every non-`String` concat operand (CP-39 row 2). `OI-142` refused an identity entry
> over it, correctly: read off the platform's own bytecode it returns `arg.toString()`, so for
> a destination identified as `"orders"` the text is a vendor debug string and carrying it
> would publish an address that never existed. The entry now declares `preserves: authority`
> — it may propagate an identity of that kind and may mint none — which bounds it to the case
> where the claim is sound, because WHO is called does not change when a value is rendered.
> Guard `values.a-RENDERING-carries-an-authority-and-nothing-else`.
>
> **2. The join is handed no identities, deliberately.** That is what keeps it honest
> (`OI-142`'s own note), so the peer could never come through it. It does not: **the peer is
> asked as its OWN question** — `arguments.authority_of`, of the address's first operand
> alone, accepting only an answer that yields an authority — which is the user's ruling of
> 2026-10-17, *"peer and path from separate evidence"*, implemented literally. The path still
> comes from a walk with no identities at all, so nothing an identity says ever reaches the
> text. Guard `arguments.a-PEER-is-asked-of-its-own-evidence`, one copy shared by both
> engines because two engines disagreeing about one address is `OI-144`.
>
> **Measured, on the pinned corpus and against the callee's own rows:**
>
> | | before | after |
> |---|---|---|
> | genai → customers ×3 | `GET <host>/owners`, `POST <host>/owners`, `POST <host>/owners/{}/pets` · peer NULL | peer **`customers-service`** · `/owners`, `/owners`, `/owners/{}/pets` |
>
> and `spring-petclinic-customers-service` serves `/owners` and `/owners/{ownerId}/pets` — so
> the two sides of each call now name the same peer and the same path, which is the arrow the
> document exists for. The expectation was re-recorded; the other five pins are unchanged.
>
> **`OI-142` closes with this**, by a route its own closure line did not predict: it asked for
> a third property on an answer distinguishing identity from rendering, and what the ruling
> actually needed was to ask the peer separately rather than to make the join carry it.
>
> **Open question this leaves, deliberately unanswered:** the rows read `partial` while
> carrying a peer and a path with no marker left in them. `partial` is true of the address
> TEXT — the host was never rendered — but a reader seeing peer and path filled may read it as
> a defect. Whether a row whose peer and path are both known is `resolved` is a resolution
> question for the user, not one to settle in passing.
**4. The field corpus could not see any of this.** **Closed by this entry** (two pins above).

**What happens today:** a Spring Boot service that holds a peer's base URL in a field or
builds a URL by concatenation exports an outbound row with `path` NULL. The call is
reported; where it goes is not.

**Real triggering input:** ordinary, and arguably the common case — `spring-petclinic-microservices`
is Spring's own reference microservice sample, and 5 of its 6 outbound calls are written
this way.

**On the grade.** Major: no row is WRONG, but the outbound column is the half of the document
that answers *what does this service call*, and it is 17% resolved on the only real system we
measure it against. Under-reporting at this magnitude on the product's central question is
not a stated boundary.

**Verify:** `.venv/bin/python scripts/field_check.py petclinic-api-gateway petclinic-genai-service`,
then `grep -n "an \`expression\` is" -A 3 src/sextant/application/resolve/shapes/arguments.py`.
**Falsified by** an outbound row on that system carrying a resolved path for
`VisitsServiceClient` or `AIDataProvider`.

### OI-137 — CI does not read `uv.lock`, so an upstream release breaks a file the branch never touched · **CLOSED 2026-10-18**
**Major · entered 2026-10-17, measured on PR #38 on 2026-10-16 · `.github/workflows/pr.yml:43`, `pyproject.toml:17`, `:40`**

> **CLOSED.** `.github/workflows/pr.yml` installs with `uv sync --frozen --extra dev`,
> so CI and a developer read the same lock. `--frozen` also refuses to re-resolve, which
> turns a `pyproject.toml` edited without `uv lock` into a loud failure rather than a
> silent install of something the lock never saw.
>
> **And closing it surfaced the mirror of the same bug.** The local `.venv` carried ruff
> 0.16.5 while the lock pins 0.16.6, so after the change CI would have run a ruff the
> developer does not — the same divergence, one patch version wide instead of unbounded.
> The local environment was synced to the lock too, and the gate re-run with the locked
> tool versions found nothing new. *Fixing one side of a two-sided problem looks like a
> fix and is half of one; the check that caught it was asking what the lock pins and
> comparing, which took one command and was nearly skipped.*
>
> Verified before committing, in an isolated environment via
> `UV_PROJECT_ENVIRONMENT`: the project imports, `graphql-core` installs at the locked
> 3.2.12 rather than the newest, and all four tools CI invokes are present.

Was: CI installs with `pip install -e ".[dev]"`. That **ignores `uv.lock`** and resolves the
newest release satisfying each floor in `pyproject.toml`, and the floors are loose:
`graphql-core>=3.2.6`, `mypy>=1.10`, `ruff>=0.5`, `import-linter>=2.0`. The local `.venv`
resolves from the lock. **They are therefore not the same environment**, and a green local
gate is not evidence about CI.

**It has already happened once, and the symptom is misleading.** `graphql-core` 3.3.0 made
`EnumTypeDefinitionNode.values` `tuple[...] | None`. CI resolved 3.3.0, this machine had
3.2.12, and mypy failed in `ingress/interpret/graphql_sdl.py` — a file the branch had not
touched, and broken on `main` too, whose last green run was three weeks earlier. The full
local gate had passed: 4088 tests, mypy on 133 files, guards 161/0. The fix that landed
(`de6c3a2b`) corrected the one call site; the cause is untouched.

**On the grade.** Major, because the failure is a wrong RESULT rather than a miss: the gate
reports a branch as broken on the strength of a file it did not change, and the honest signal
— does this branch pass? — is unavailable until someone diagnoses it. It also degrades with
time rather than staying put: every loose floor is a future failure on an unrelated file,
arriving whenever an upstream release lands.

**What happens today:** every PR's gate result depends on what PyPI published that week.

**Real triggering input:** ordinary — an upstream minor release.

**Verify:** `grep -n "pip install" .github/workflows/pr.yml` beside
`grep -n "graphql-core" pyproject.toml`, then compare against the lock's pin.
**Closes** by CI installing the resolved set (`uv sync --frozen`, with the lock as the
single source of truth for both environments). **It is CI configuration, which GUIDELINES
§7 puts out of scope without the user's explicit instruction** — raised 2026-10-16, raised
again here, and entered in the register so it stops living in commit messages. Falsified by
a CI run whose installed `graphql-core` matches `uv.lock`.

### OI-136 — the sixth edge is deferred: 16 of 756 asked positions, and the endpoints publish either way · **THE EDGE LANDED 2026-10-18; capability 9.19's remaining shapes stay open**
**Minor · entered 2026-10-17 · plan `2026-09-22-value-resolution.md` Tasks 11-12, spec §4 · probe `scripts/probes/cp33_binding_writes.md`**

Capability 9.19 (`written_by` — a binding assigned outside an initialiser) and the task that
wires it into `value_edges` are **deferred by ruling, not blocked**. The walk ships with five
of its six edge kinds and `no_writer` is the honest answer at the sixth.

**The yield, measured across all 27 corpora.** At positions a shipped catalog asks about:

| | count |
|---|---|
| resolve as a literal at the call site | 537 |
| resolve by crossing at least one edge | 203 |
| …of which cross a caller or return boundary | 77 |
| answer `no_writer` — what 9.19 would address | **16** |

So the capability addresses **16 of 756** asked positions, about 2%.

**And it costs no endpoint.** `call_sites`, `call_edges` and `return_flows` are read from
bytecode, and endpoint rows come from annotations and matched call sites; value resolution
fills in the ADDRESS column of a row that already exists. A field-held destination costs the
address, never the endpoint — the row publishes with `path` NULL at `unresolved`, which is
D02 §2's unresolved-is-an-answer working as designed.

**What is NOT the gap, because it reads like it is.** "A value passed as a parameter" and "a
compile-time constant" both resolve today. The walk follows a value out of one method into
another — 77 crossings in this estate, e.g. `'pet'` reached through `Owner#getPet`'s return —
and javac INLINES a `static final String TOPIC = "orders"` at every use site, so it arrives
as a literal with no field read at all (`shapes/identity_calls.py`). The gap is narrower:
**a value stored into a mutable field in one method and read in another.**

**Two things settled while deferring it, both recorded so they are not re-litigated.**

*A field with several writers is not a hazard.* It is several POSSIBLE values, and ruling 1
(multiplicity) already says several enumerable answers yield one row per answer — so the
rows publish each possibility rather than picking one. This was raised as a fabrication risk
and it is not one; the design answers it.

*A literal assigned in a method body is a code fact, not configuration.* An argument was
made that resolving `this.topic = "default"` in `@PostConstruct` would assert a property of
the running system under §8.2. That is wrong: §8.2 bounds CONFIGURATION a deployment
overrides, and a literal in a method body is a code fact like any literal at a call site.
Applied consistently that argument would forbid reading call-site literals, which is most of
what the system does.

**AND THE EDGE IS NOT ONE EDGE. A BACKEND ALREADY REPORTS THE COMMONEST SHAPE, AND THE WALK
HAS NEVER READ IT** (measured 2026-10-18, spec `2026-10-18-the-sixth-edge-design.md`). This
entry and `value_edges.sql`'s header both say *"no fact behind it"*; that is true of a write
OUTSIDE an initialiser and false of the edge. `MethodFlow.fieldWrites` emits `field_write`
for every constructor that assigns a parameter straight to a field — the shape every
constructor-injected Spring bean has — and:

* `grep -c field_writes src/sextant/storage/duckdb/value_edges.sql` is **0**;
* `values._binding` returns `no_writer` without being handed the binding's symbol at all,
  though its own position carries one.

**Measured at positions a shipped catalog asks about**, instrumented at `_binding` across
every built corpus: **276** binding reads, of which `field_writes` already describes the
writer for **112 (41%)** — 94 of them in `apollo-portal` alone. So wiring one arm over an
existing fact is most of this entry's value, with no extractor change and no schema change.

*`mall-admin` and `jhipster-sample-app` answer 0 of 17 and 0 of 28, and that is not a gap:
they use `@Autowired` FIELD injection, which the container writes reflectively, so no method
contains a write instruction to report. §8.2 bounds it and no capability reaches it.*

**BOTH GROUNDS FOR THE DEFERRAL ARE WEAKER THAN THEY READ, measured 2026-10-18 on
`YunaiV/ruoyi-vue-pro`** (spec `2026-10-18-configured-path-prefixes-design.md` §4):

* *"16 of 756 asked positions"* — two things are wrong with it. The denominator is positions
  **a shipped catalog asks about**, and no catalog asks about `Map#put`'s key, which is where
  this case needs it. And the NUMERATOR was measured before `apollo-portal` joined the
  corpora: re-measured with it in, **226** asked positions answer `no_writer`, 17× the figure
  the deferral rests on. The same bounded-measurement mistake as `OI-143`'s *"nothing in the
  27 measured corpora reaches it"*, which the first real production codebase hit 64 times —
  the third instance of it, and the reason
  [[nothing-in-the-corpus-is-about-the-corpus]] exists.
* *"And it costs no endpoint"* — true for a DESTINATION and **false for a PREFIX**. ruoyi
  configures `/admin-api` and `/app-api` through
  `RequestMappingHandlerMapping.setPathPrefixes`, whose prefix and package pattern are
  literals in `WebProperties#<init>` (`new Api("/admin-api", "**.controller.admin.**")`).
  Walking either half answers `unresolved(no_writer)` at exactly this edge — the key on TWO
  coherent paths, one per `putPathPrefix` call, so the crossing and the pairing already work
  — and the consequence is not a NULL column. **480 inbound rows publish a path that looks
  resolved and is wrong by its prefix.** Nothing in the row says to doubt it.

So the honest statement of the yield is now "16 positions of the 756 we ask about, plus the
prefix on every row of a module that configures one", and the honest statement of the cost is
no longer "never an endpoint".

> **BUILT 2026-10-18** (spec `2026-10-18-the-sixth-edge-design.md`), and in two halves the
> user's question forced together: *"Why does this have to be constructor? Whether it's a
> constructor or a setter, this is a write to a field and both are the same."*
>
> * **The `<init>` filter lifted**, which this entry had always described as what 9.19 needs —
>   *"a method-filter change"*. Measured: `field_writes` went 86 to **237** on
>   `spring-petclinic-rest`, 553 to **1,638** on `apollo-portal`. The guard was hiding about
>   two thirds of the writes on real code.
> * **The writing METHOD recorded** (`written_by`), which the lift makes necessary rather than
>   merely precise: a field commonly has several writers once every instance method is
>   eligible, and crossing to the wrong one's callers would publish a value the field never
>   held. Optional and absent by default, so no schema version moved — proved by
>   `scripts/probes/fact_additivity/run.py` over all 23 fixture trees, every one additive.
> * **The arm and `_binding`**, plus two things the build found: `value_index` parsed
>   `to_ordinal` for every edge before dispatching on kind (a crash on the first module with a
>   field write), and `single_call` had to CONSULT the walk for a `field` argument — `OI-143`'s
>   cause 1 in a second guise, since the engine asks only where a row declares a hop.
>
> **Measured at asked positions: `no_writer` fell from 226 to 110**, and `apollo-portal`'s from
> 132 to 19. `fixtures/orders-fieldheld` publishes both of its topics resolved where it
> published one row with no destination. All six field pins unmoved; guards 167 killed / 0
> survived.
>
> **Cost, since §3a's ruling was "no cap, measure first":** over 1,610 positions the walk takes
> 0.09s and `resolve_site` 0.18s. The tail moved more than the total — `apollo-portal`'s worst
> site returns **11,913** bindings where the worst was 685, at 0.05s for that site. Still no
> cap, now with a figure behind it.
>
> **What stays open here is capability 9.19's REMAINDER**, which is narrower than this entry
> was written for: a write whose VALUE is not a bare parameter load — a literal (`OI-141`), a
> call's result, a static initialiser (CP-33 rows 2, 6, 7, 8). `@Autowired` field injection is
> not on that list and never will be: the container writes it reflectively and no bytecode
> shows it (§8.2), which is why `mall-admin` answers 0 of 17 binding reads. The deferral may still be right; the two sentences it rested on
are not the ones to rest it on. The user ruled this case IN scope on 2026-10-18, which makes
this edge a blocker rather than a nicety: *"the lambda is still config … I said business logic
in the other case because the path was dependent upon the path being called, a runtime logic,
whereas this one is configured."*

**The probe is already written and committed**, so whoever picks this up does not re-measure:
`cp33_binding_writes.md` records that a setter presents the existing `ALOAD 0; xLOAD k;
PUTFIELD` triple verbatim (so the capability is a guard removal plus a per-method
`firstSlot`, since a static method's parameters start at slot 0); that `@PostConstruct` and
static initialisers assign CONSTANTS, which `{field, from_parameter}` cannot express; and
that a computed assignment never presents the triple, so "direct traces only" holds outside
`<init>` for free.

**One claim the spec made for this capability is WITHDRAWN, measured 2026-10-17** (probe
row 7, added at Task 13). Spec §4 says the sixth edge *"is what closes
`akka-pekko-actors`"*. It does not. `ActorRef ref = system.actorOf(props, "worker")`
assigns a CALL'S RESULT, and `javap` shows `aload_0; aload_1; iconst_0; invokeinterface;
checkcast; putfield` — a call between the receiver load and the `putfield`, so the
`ALOAD 0; xLOAD k; PUTFIELD` triple never presents, exactly as it does not for
`@PostConstruct`'s `ldc`. A setter-injected `ActorRef` would be reached; one from the
factory the framework's own documentation uses would not. **So that framework's tier does
not move on this capability**, and the spec is corrected rather than left to be read as a
promise (`docs/COVERAGE.md` §5.12, `docs/java-kotlin-delivery-list.md`'s
`akka-pekko-actors` row).

**THE YIELD FIGURE ABOVE IS CORPUS-BIASED, measured 2026-10-17 — read `OI-138` beside
it.** "16 of 756" was computed over the fixtures and the three field pins, and **not one of
those pins contains a single outbound call** (the upstreams genuinely make none). On
`spring-petclinic-microservices`, Spring's own reference microservice sample, the outbound
column is 1 of 6 resolved and field-held or concatenated addresses are what cost the other
five. The deferral still stands — this entry's capability (a write OUTSIDE an initialiser)
is not what that system needs; `OI-138` cause 2 is, and that one is INSIDE `<init>` and
strictly smaller. But the 2% was measured on a corpus that could not see the half of the
product the question was about, and that is recorded here rather than left for the next
person to re-derive.

**Closes when** someone wants those 16 addresses enough to add an extractor capability, or
when a corpus arrives where the count is materially larger. The yield is what makes this
Minor; the work is understood and the probe is done.
### OI-135 — an invented hop key loads silently, and neither cheap way of closing that works
**Minor · entered 2026-10-17 · spec `2026-09-22-value-resolution-design.md` §2a step 3, §5b**

**The gap, measured.** A catalog carrying an invented `invented_hop_via` block loads clean:
all 101 catalogs shipping then parse, the key is silently ignored, and nothing refuses a key no style
declares. So §2a step 3's "one way, enforced by the loader" is not enforced by anything
today — and the old plan of refusing the four known keys BY NAME would not have enforced it
either, since it says nothing about an eighth word. §2a and §5b were corrected on 2026-10-17
to say the vocabulary is what must close; this entry records that closing it is harder than
it looks.

**Both cheap designs were tried on paper and both fail. Measured, not argued.**

*A per-style key allowlist, generated from the shipped catalogs* — 295 distinct keys across 13
styles. It fails because a flat walk of `matches` CANNOT TELL GRAMMAR FROM DATA. Among those
295 are `io.confluent.kafka.serializers.KafkaAvroDeserializer`,
`io.ktor.http.HttpMethod$Companion#getGet`,
`org.springframework.data.repository.CrudRepository`, and `0`, `1`, `Cookie`, `kafka`,
`rabbit` — map keys inside catalog mappings, not vocabulary. An allowlist of those would
carry framework class names and would need an edit every time a catalog maps a new
serializer. No style shares a single key with every other, so there is not even a universal
core to anchor on: 253 of the 295 appear in exactly one style.

*A naming check refusing an unknown `*_via` / `*_wrappers` key* — the shipped grammar uses
exactly five such words (`bean_via`, `channel_via`, `url_via`, `call_wrappers`,
`record_wrappers`), so the convention looks real. It fails against the very history it would
protect: the seven words §0a names are `channel_via`, `url_via`, `type_carriers`,
`call_wrappers`, `getters`, `indexed`, `compose`, and **four of the seven follow no such
convention**. A check keyed on the suffix would have missed `type_carriers`, `getters`,
`indexed` and `compose` — which is an invented discriminator of exactly the kind §8.1 rule 5
forbids, with the counter-evidence sitting in the spec's own sentence.

**What closing it actually needs.** A declared per-style SCHEMA — which keys are grammar,
at which depth, and which nested objects are data — so a validator can refuse an unknown
grammar key without choking on a mapping whose keys are class names. That is real design
work on 13 styles, not a step inside another task, and it is what this entry is for.

**Severity is Minor because the failure is inert, and that is worth stating.** An invented
hop key does nothing: no engine reads it, so a catalog carrying one derives exactly what it
would without it. The cost is an author believing a declaration works when it is ignored —
a wasted afternoon and a silent miss — not a wrong row. §0a's seven words grew because
there was no generic operation to reach for; after this work there is one, which lowers the
pressure that produced them even while the loader stays silent.

**Closes when** a per-style schema exists and the loader refuses an unknown grammar key,
with a test that an invented hop word is rejected and that a REDEFINED `channel_via` still
loads.

### OI-134 — one identity is written on up to 26 rows, and 10 of the 18 cannot move without a measurement
**Minor · entered 2026-10-17 · spec `2026-09-22-value-resolution-design.md` §2a, `value-models/`**

**Not a defect, and nothing is broken.** The loader already folds every row-level hop
declaration into one identity table, so the engines see the same 18 identities whichever way
they are written. This is a maintenance hazard, logged rather than fixed because no input
triggers it.

**The duplication, measured.** 124 row-level `channel_via`/`url_via` declarations across the
shipped catalogs carry only **18 distinct identities** between them. `java.net.URI.create`
and `java.net.URI.<init>` are each written out on **26 rows across 5 files**;
`jakarta.jms.Session.createTopic` on 12 rows of one file. Only 3 of the 18 are declared by a
single row. The hazard is ordinary drift: edit one of the 26 `URI` rows and not the others
and they disagree, with nothing to catch it.

**The proposed fix.** `value-models/` exists to hold each identity once, and 2 of the 18 are
already there. Move the rest in, and drop `arg` from the rows. **The rows keep naming their
producers** — `{owner, method}` stays, because that is the restriction `fluent` depends on
(spec §2a, and D02's note at `channel_via` carries the two guards that measured it). So this
deduplicates ONE FIELD out of 124 rows; all 124 rows remain.

**Why it is not done yet, which is the substance of this entry.** Every `value-models/` entry
must carry `by:` — the measurement behind the claim — and that requirement is stated there as
the whole reason the directory exists. All 18 were checked by reading the probe files:

| | count | state |
|---|---|---|
| real evidence stating the claim | **8** | `URI.create`/`<init>` (`a2t8` expectation 3, and already relocated); `Subscriptions.topics`/`topicPattern` (`w62` row 2); `MessageConsumerOptions.setAddress` (`cp31` 5a/5b, two vertx versions); `ConsumerProperties`/`ContainerProperties`/`amqp.core.Queue` constructors (`cp27` row 13 + §§162,167) |
| signature measured, claim not | **4** | both `jakarta.jms` and both `javax.jms` `createQueue`/`createTopic`. `w11` measured the descriptor `(String) -> Queue`; no probe states the PRODUCING claim. **CP-12 row 9 is a near-miss and must not be cited for it** — "`jakarta.jms.Session`'s receiver factories, every one taking its destination at argument 0" is about `createConsumer` taking a `Destination`, not about `createQueue` taking a name |
| no evidence at all | **6** | `List.of`, `Arrays.asList`, `Collections.singletonList`, `Pattern.compile` (JDK API contracts, currently folk knowledge); `TopicName.of`, `ProjectSubscriptionName.of` |

So **10 of 18 need a measurement first**, and citing an existing probe that does not state the
claim is the one thing `by` exists to prevent — a reader trusts an entry *because* of its
citation, so a wrong one stops the checking rather than merely failing to help.

**Riskiest of the ten**: `TopicName.of(project, topic)` and
`ProjectSubscriptionName.of(project, subscription)` take their identity at argument **1**. An
off-by-one there publishes a PROJECT ID as a topic name — a wrong address at `resolved`.
`ProjectSubscriptionName.of` has no probe line mentioning it at all.

**Closes when** the 10 are measured and all 18 sit in `value-models/` with honest citations.
Best taken by whoever is next working on one of those frameworks with the jar already open,
which is when the measurement is cheap and sound; written now, by someone not otherwise
touching them, is the circumstance an asserted-from-memory claim slips in.

### OI-42 — a class file above the ceiling is refused, and the refusal kills the whole scan
**Critical · pre-existing, entered here 2026-09-06 · `docs/java-kotlin-delivery-list.md`
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
**Minor · pre-existing · `docs/open-issues.md` OI-84 §13**

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

### OI-10 — shipped catalogs that state no measured version at all
**Major · pre-existing, made countable 2026-09-06 by F5 ·
`tests/architecture/test_catalog_measurement_coverage.py::_NOT_MEASURED_YET`**

F5 gave the catalog schema a `measured:` block (D02 §1a) and twenty-nine of
the fifty-five catalogs shipping THEN a row citing a committed probe. **Twenty-six
had none, because no probe had ever opened the artifact whose rule they encode.**

*The live count is deliberately not repeated here* — `COVERAGE.md` §3a's generated
block holds it and names every catalog on each side, regenerated from the catalogs
by `scripts/coverage_versions.py` and checked by a test. This entry's title carried
19 and its body 29/26 at the same time, which is what `G-27` recorded; W53 removed
the numbers rather than refreshing them, because a hand-maintained count of a
generated fact decays every time a wave adds a catalog.

The twenty-six F5 counted included every
`@KafkaListener`, `@JmsListener`, `@RabbitListener`, gRPC, GraphQL and schema
catalog. Each one still on the list claims its rule for every version of its
framework on evidence from none.

This is not a new defect and F5 did not introduce it; what F5 changed is that
they became a named list with a reason each, and a NEW catalog cannot
join them silently. **Cost:** a framework rule that moved between versions —
`isHandler` losing a disjunct, `WebClient.exchange` disappearing at 7.0.2 — is
undetectable in whichever catalogs remain on that list, and the failure is silent in both directions
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
both legacy messaging artifacts at 2.2.6.RELEASE and 2.4.4).

**W53 retired three more, and all three had been recorded as UNMEASURABLE**
rather than merely unmeasured — the audit could not resolve their artifacts in
either local repository, so it filed their FQNs as predictions. All three resolve:
`grpc-spring` and `grpc-net-devh` (`net.devh` 3.1.0.RELEASE, Spring gRPC 0.10.0 —
all three `@GrpcService`/`@GrpcClient` spellings confirmed) and `spring-kafka-media`
(Confluent 7.6.0 from `packages.confluent.io`, spring-kafka 3.1.4, kafka-clients
3.6.2 — all fourteen serializer classes confirmed). `spring-data-rest` was already
measured and gained a second block, because W53's probe found its collection-read
rule WRONG (`G-46`). **"No artifact available" was worth re-testing rather than
trusting**: it is a statement about one machine on one day.

*The heading above no longer carries a count.* It did, and the body carried a
different one at the same time (`G-27`). `COVERAGE.md` §3a is the live figure, and
it is generated.

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

### OI-27 — FR-6 says a trace is unbounded and stops only at a terminal; three things stop it earlier · **CLOSED, W31**
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

**CLOSED in W31** (F7 §8.1). The depth bound is gone: `_walk` is an explicit stack, so the
interpreter's own recursion limit is out of the failure modes and nothing needs a counter
to stay finite. `TraceStop.DEPTH_LIMIT`, `Trace.truncated`, the rendered `Complete` column
and the `trace_depth_is_bounded` known gap all retired with it.

**Measured before removing it**, which is what said the bound was safe to lose: the deepest
trace is **9 edges** across `mall-admin` (160 traces), `spring-petclinic-rest` (37) and
`jhipster-sample-app` (38), against a bound of 64, and no trace was ever truncated.

**Two of the three stops stay, and they were never the issue**: `cycle` and `revisited` are
correctness. Without them the walk does not terminate, and expanding a shared subtree once
per route is exponential on an ordinary diamond — which is D01's own reason for a trace
being a walk rather than a stored table. FR-6 asks not to be bounded by DEPTH, and neither
of these is.

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

### OI-26 — `SEXTANT_VERSION` is declared three times · **CLOSED 2026-10-23**
**Closed** by the first version bump (0.1.0 → 0.2.0, the Spring Boot milestone): both stamping sites import `domain/version.SEXTANT_VERSION`, which reads the package metadata, so moving `pyproject.toml`'s one `version` moved every stamp — the condition this entry said would falsify it did not occur.

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

### OI-85 — three inputs the `DefaultImpls` holder rule would misread, none of which a real module presents
**Minor · logged 2026-09-12 at Task 15's review (`kotlin-defaultimpls`, `b6be0e1`) ·
`extractor-jvm/.../KotlinDefaultImpls.java`, `ClassScanner.java`, `workspace.py`**

Logged rather than fixed, under the ruling of 2026-09-12 that an issue whose triggering
input does not occur in real codebases is recorded, not worked. The holder is recognised
from three conjuncts — the `<Iface>$DefaultImpls` name, the `InnerClasses` entry naming
the interface as the outer class, and every method `static` with the interface at slot 0
(COVERAGE §5.13, D00 §5). Each bullet names the input that gets past one of them, and why
it is not seen in practice.

- **A hand-written nested class named `<Iface>$DefaultImpls`** whose static methods take
  the interface first and are declared BEFORE an explicit constructor. The method facts are
  emitted as the methods are visited, so those methods carry `bridge_of` while the type's
  `implements_default_of` is withheld at `visitEnd` by the constructor. No compiler emits
  this and nobody writes it: the name is the Kotlin compiler's own reserved spelling, and a
  Java author declaring a nested `DefaultImpls` with that method shape is copying kotlinc by
  hand. **Fix when wanted:** a fourth conjunct in `holderOf`'s gate — `@kotlin.Metadata`
  kind `k=3` (a synthetic class), which `KotlinNullability.collector` already reads off the
  annotation before any method is visited.
- **A losing multi-release overlay copy of the holder's TYPE fact.** `workspace.py`'s
  `default_bodies` query filters its method side (`m`) by `selected_documents` and joins the
  enclosing type's side (`t`) without that filter, so a holder type fact from a losing
  overlay copy can pair with the winning copy's method fact. The projected columns come from
  the pair's `t.implements_default_of` and `m.*`, which the two copies agree on, so the
  result is a DUPLICATE row and never a different one; `dispatch._default_bodies` keys a
  set-like list and dedupes it. A Kotlin holder in a `META-INF/versions/` overlay is the
  input, and no module here or in the corpora carries one.
- **Under `-jvm-default=disable`, a default body containing a lambda.** A non-capturing
  lambda inside the body is expected to put its `private static synthetic` body method into
  the holder, with slot 0 not the interface; "every method shaped" then fails and the holder
  is silently unrecognised — it fails CLOSED, with no `implements_default_of` and no
  `bridge_of`, never a wrong fact. Unmeasured (§5.4: the shape is assumed from how kotlinc
  places a lambda body in its enclosing class, not read from a class file): the mode has not
  been any supported compiler's default since 2.2, and no scanned module was built under it.

**Verify** each by building the input and scanning it; **closes** when the fourth conjunct
lands for (a), when the `t` side takes the `selected_documents` filter for (b), and when (c)
is measured.

### OI-86 — `sole_unannotated` still governs Feign and Micronaut messaging, and loses a Kotlin body the same way JAX-RS used to
**Minor — reachable input unmeasured; Major if it turns out common · logged 2026-09-18 at
B/C Task 13's review (spec `docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md`
§6) · `spring-cloud-openfeign.yml`, `micronaut-jms.yml`, `micronaut-jms-producer.yml`,
`micronaut-kafka.yml`, `micronaut-kafka-client.yml`, `micronaut-pubsub.yml`,
`micronaut-pubsub-client.yml`**

M2 (this branch's own §0) found that `sole_unannotated` disqualifies a parameter for ANY
annotation at all, so kotlinc's synthetic `@NotNull` — which reaches the facts at
`retention: class` on every non-null Kotlin declaration — erases a Kotlin request body from
under it; the fix, `sole_unbound`, measures against the framework's own binding annotations
instead and shipped on the three JAX-RS catalogs (`jakarta-jaxrs.yml`, `javax-jaxrs.yml`,
`quarkus-rest.yml`) and MicroProfile REST Client. **The other seven catalogs above still
declare `sole_unannotated`** (measured by `grep -n fallback` on each), so the identical loss
applies to a Kotlin `@FeignClient` interface's request body and a Kotlin
`@KafkaListener`/`@JMSListener`/`@PubSubListener`-style Micronaut handler's body — `@Valid`
on a Java body has the same effect, framework-independent.

**Real triggering input:** a Kotlin Feign client interface, or a Kotlin Micronaut Kafka/JMS/
Pub-Sub listener or client, declaring a non-null body parameter with no `@RequestBody`/
`@MessageBody` annotation of its own — exactly the shape `fixtures/orders-service`'s
`KotlinOrderResource` had under JAX-RS before this branch's fix, and no fixture here has the
Feign or Micronaut equivalent: `find fixtures -iname "*.kt"` returns six files, none under
`fixtures/orders-micronaut` and none naming `FeignClient`, so the input is real and
plausible (Micronaut's Kotlin-first documentation, Feign's common use from Kotlin services)
but its frequency in real estates is not measured here — no probe or corpus scan has counted
Kotlin Feign/Micronaut modules the way CP-18's own measurement did for JAX-RS. Per the
register's own severity rule (measure before assigning), that absence of a measurement is
why this logs as **Minor rather than Major**: the fix is Major-when-reachable specifically
for a Kotlin Feign outbound body (blocking REST outbound) or a Kotlin Micronaut listener
body (blocking Kafka/JMS/SQS/Pub-Sub inbound or outbound, whichever catalog is in play), and
should be re-graded Major the moment a corpus or fixture shows the shape is common.

**Verify:** `grep -n fallback src/sextant/catalogs/{spring-cloud-openfeign,micronaut-jms,micronaut-jms-producer,micronaut-kafka,micronaut-kafka-client,micronaut-pubsub,micronaut-pubsub-client}.yml`
— all seven still read `sole_unannotated`. **Closes** when each catalog's `request_body`
switches to `fallback: sole_unbound` with that framework's own `bound_by` list, measured the
way CP-18 measured JAX-RS's.

### OI-87 — `@RestStreamElementType`'s value is not carried as the per-event SSE format
**Minor · logged 2026-09-18 at B/C Task 13's review (spec §3c, §6) ·
`src/sextant/catalogs/quarkus-rest.yml`**

Quarkus REST's `@RestStreamElementType` (or the deprecated `@RestSseElementType`) is now
read for its PRESENCE — `protocol_hint.hint_annotations`, shipped B/C Task 10 — which
correctly classifies the response as SSE even with no `@Produces` at all. Its VALUE, the
per-event element type, is not carried anywhere: an SSE row's per-event payload still falls
to the format ladder's rung 5 (`json`, `narrowed`, rendered `json (assumed)`), the same as
every other undeclared payload, rather than reading the annotation's own value as a rung-2
source the way `@Produces`/`@Consumes` already are for the envelope. No wrong output either
way — rung 5's `json (assumed)` is honest about its own uncertainty — so this is a trust-
marker upgrade left undone, not a defect in what ships.

**Real triggering input:** any `@RestStreamElementType(OrderEvent.class)` (or
`@RestSseElementType`) method with no declared `@Produces` — `fixtures/orders-quarkus`'s
`OrderResource#events` is exactly this shape today, and its per-event contract reads at
rung 5 rather than rung 2.

**Verify:** `json.loads(row["response_shape"])` on the SSE row in
`fixtures/orders-quarkus` shows the rung-5 trust marker, not rung 2. **Closes** when a new
rung-2 source reads `@RestStreamElementType`'s (and `@RestSseElementType`'s) declared value
the next time the format ladder is touched (spec §3c names this a named follow-up, not in
this group).

### OI-88 — Quarkus REST's return-type-keyed default `produces` is not read
**Minor · logged 2026-09-18 at B/C Task 13's review (spec §3c, §6) ·
`src/sextant/catalogs/quarkus-rest.yml`**

`EndpointIndexer.applyDefaultProduces` (`EndpointIndexer.java:853`, measured 2026-09-18)
fills an undeclared route's `produces` from its RETURN TYPE — `String` becomes
`text/plain`, anything else becomes JSON where a JSON provider is present — a framework
default keyed on the return type rather than on any declared value, which no
`default_produces`-shaped key in this engine states. An undeclared Quarkus route's
`produces` stays NULL here and the row falls to the format ladder's rung 5 exactly as an
undeclared Spring route does, rather than the return-type-keyed default a real Quarkus
deployment computes. Stated as a boundary in `docs/COVERAGE.md` §5.1 (the Quarkus
"stated-not-built surface" row) and in `quarkus-rest.yml`'s own comments; this entry is the
register's own record of the same gap.

**Real triggering input:** any Quarkus REST method with no `@Produces` at all — the request
body rule's own excludes and implicit bindings are unaffected, only the response media type.

**Verify:** `grep -n applyDefaultProduces` against a `quarkus-rest` sources jar shows the
rule; no key in `quarkus-rest.yml` reads a return type. **Closes** when a return-type-keyed
default-media word is designed — a further measurement and a schema addition, not a catalog
edit alone.

### OI-89 — `annotation_arg.equals` compares Python's `str()` of a non-string fact value, which is not Java's string form
**Minor — unreachable by any shipped catalog today · logged 2026-09-18, ruled by the
controller during B/C Task 7's review (SDD ledger; spec §2) ·
`src/sextant/application/resolve/conditions.py:204`**

`_compare`'s `equals` arm reads `any(v is not None and str(v) == condition.equals for v in
values)`, where `v` is the extracted fact's own Python-typed value. For a `String`
attribute this is correct — the fact and the catalog's YAML string agree. For a `boolean`
attribute, `v` extracts as a Python `bool`, and `str(True)` is `"True"`, capitalised,
where Java's own `Boolean.toString()` — and thus the bytecode's own constant-value form — is
lower-case `"true"`. A catalog declaring `equals: "true"` against a boolean attribute would
therefore compare `"True" == "true"`, false, and the condition would never hold, silently:
the row it gates would read as though the attribute were always absent or always the other
value.

**Why logged rather than fixed:** measured against every catalog on this branch —
`grep -n 'equals:' src/sextant/catalogs/*.yml` returns SEVEN hits, not the six an earlier
draft of this entry undercounted:

```
src/sextant/catalogs/jakarta-jws.yml:223:          unless: { attribute: exclude, equals: true } }
src/sextant/catalogs/jakarta-jws.yml:225:          unless: { attribute: exclude, equals: true } }
src/sextant/catalogs/jakarta-jws-client.yml:111:          unless: { attribute: exclude, equals: true } }
src/sextant/catalogs/jakarta-jws-client.yml:113:          unless: { attribute: exclude, equals: true } }
src/sextant/catalogs/micronaut-jms.yml:59:      equals: sqsJmsConnectionFactory
src/sextant/catalogs/micronaut-jms-producer.yml:54:      equals: sqsJmsConnectionFactory
src/sextant/catalogs/spring-kafka-message.yml:54:    - { method: setHeader, when: { arg: 0, equals: "kafka_topic" }, captures: { channel: arg1 } }
```

Four of the seven (`jakarta-jws.yml` ×2, `jakarta-jws-client.yml` ×2) are a DIFFERENT word,
`unless.attribute`, not `annotation_arg` — a pre-existing mechanism this branch did not
touch. Two (`micronaut-jms.yml`, `micronaut-jms-producer.yml`) are the `annotation_arg`
consumers this branch added, both `hint_when.equals: sqsJmsConnectionFactory` against a
`String` attribute. **The seventh, `spring-kafka-message.yml:54`, is a THIRD word again** —
`single_call`'s own `when: { arg: 0, equals: … }`, an argument-equality guard on a call-site
step (`setHeader`'s first argument matching the literal `"kafka_topic"`), not
`annotation_arg`'s attribute-on-an-annotation read at all; `_compare` above is never called
for it. So of the seven hits, exactly two exercise `annotation_arg`'s `equals`, and both are
`String` attributes — no shipped consumer of `annotation_arg`'s `equals` compares a
non-string attribute, so the register's own rule (an issue real input cannot trigger is
logged, not fixed) applies: the input a future boolean-`equals` catalog would supply does
not exist yet.

**Verify:** `grep -n "equals:" src/sextant/catalogs/*.yml` — seven hits, sorted above by
which word each belongs to; the two `annotation_arg` consumers are both `String` attributes.
**Closes** with two changes together: `_compare`
reads Java's own string form for a non-string value (`"true"`/`"false"` for `bool`, decimal
for numeric types) rather than Python's `str()`, and `parse_condition` refuses a non-string
`equals` value at catalog load until that mapping is declared — a parse-time refusal rather
than a silent runtime mismatch, `parse_condition`'s own closed-vocabulary discipline (spec
§2) extended to the comparator's operand.

### OI-90 — `POST /kt/orders` derives TWO inbound rows in `orders-service`, one per engine
**Minor · logged 2026-09-18, found at B/C Task 10's review · `fixtures/orders-service`,
`src/sextant/storage/duckdb/insert_endpoints.sql`**

`fixtures/orders-service`'s Kotlin JAX-RS resource, `KotlinOrderResource`, and its
pre-existing Kotlin functional-routing fixture, `KotlinOrderRoutes#ktRoutes`, both register
`POST /kt/orders` — a coincidental address collision between two unrelated fixture files
sharing one Maven module, not a wire-identity conflict either framework would actually
suffer in a real deployment. Both rows survive because `insert_endpoints.sql`'s inbound
identity guard is the SECOND HALF of the `annotation_driven` engine specifically (its own
header comment: "the second half of the annotation_driven engine") and runs once per
annotation-driven catalog's own turn, comparing only against rows already in the table at
that turn — it never runs for, and never sees, a row the functional-routing DSL engine
inserted through its own path. So two DIFFERENT engines minting the identical `(http,
inbound, POST, /kt/orders)` identity do not merge and do not conflict-flag; both stand,
distinguished only by `handler` (JAX-RS's `KotlinOrderResource#createOrder` symbol) versus
`caller` (the DSL route, `handler` NULL).

**Real triggering input:** live today, in `fixtures/orders-service`. `test_a_kotlin_jaxrs_body_under_kotlincs_notnull_keeps_its_contract`
(`tests/application/test_pipeline.py`) filters on `handler is not None` specifically to pick
the JAX-RS row out of the pair rather than assuming the address names exactly one row — the
test's own comment names the collision. Graded Minor rather than Major because both rows are
individually honest about a real registration and the collision is a property of this
fixture's own address choice (two independent framework samples sharing one path string
inside one Maven module for coverage convenience) rather than a shape a single real Spring
Boot module would present — the pre-existing engine property (identity dedup is scoped to
`annotation_driven`'s own inserts) is broader than this one collision and would repeat for
any two catalogs from different engines sharing an inbound address, which is unmeasured
beyond this one instance.

**Verify:** `[r for r in report.endpoints if r["path"] == "/kt/orders" and r["method"] ==
"POST"]` returns two rows in `fixtures/orders-service`. **Closes** when the inbound identity
guard (or a merge pass after it) compares across every engine's inserts, not only
`annotation_driven`'s own turn-by-turn ones — an engine change, not a fixture edit, since the
fixture's own collision is incidental rather than the shape worth chasing on its own.

### OI-91 — Quarkus REST's own inheritance rule diverges from JAX-RS §3.6, and the engine emulates the specification, not Quarkus
**Minor · logged 2026-09-18 (CP-19 row 6, spec §3b word 3's boundary note) ·
`src/sextant/catalogs/quarkus-rest.yml`, `docs/COVERAGE.md` §5.1**

JAX-RS §3.6 is all-or-nothing PER METHOD: an implementor method carrying any of its own
JAX-RS annotations gets none of the interface method's, whichever level they are declared
at. Quarkus's own `EndpointIndexer.collectEndpoints` (measured, CP-19 row 6) is a different
walk: self → superclass → every interface, and AT EACH LEVEL it scans that class's OWN
methods for the sought HTTP-verb annotation; the FIRST level whose own method carries the
verb wins, and EVERY OTHER JAX-RS annotation on the endpoint — `@Path`, `@Produces`,
`@Consumes` sibling included — is read off that SAME winning method, never off an override
at any other level. Word 3 (this branch's sibling-inheritance engine change) reproduces
JAX-RS §3.6 exactly, which is the specification's own answer and the right one for the two
plain catalogs; on Quarkus REST specifically it is a stated, measured divergence rather than
a built one: an implementor overriding an interface method with its own `@Produces` (or any
other non-verb annotation) but no verb annotation of its own has that override silently
ignored by Quarkus — word 3 would look for the implementor's own annotations, find one
(`@Produces`), and — following §3.6 — derive NOTHING for that method (no own verb), where
Quarkus's real walk would still find the verb at the interface level and apply it there,
producing a row this engine does not.

`quarkus-rest.yml` states the divergence in a comment (`src/sextant/catalogs/quarkus-rest.yml`,
the `collectEndpoints` block) rather than reproducing Quarkus's own per-level walk, and
`docs/COVERAGE.md` §5.1's "Quarkus's own §3.6 divergence" row states it beside the JAX-RS
rows. This entry is the register's own record of the same measured gap, since spec §6 named
it as one of the items the closing task logs.

**Real triggering input:** an implementor overriding an interface method with its own
`@Produces` (or similar) and no verb annotation of its own — not present in
`fixtures/orders-quarkus`, whose own inheritance case is a bare `@Override` with no
annotations at all, so word 3's §3.6 emulation and Quarkus's real rule agree on the fixture
either way (COVERAGE §5.1 states this explicitly).

**Verify:** `grep -n "collectEndpoints" src/sextant/catalogs/quarkus-rest.yml` shows the
comment; CP-19 row 6 (`scripts/probes/cp19_quarkus_rest.md`) has the measurement. **Closes**
when `quarkus-rest.yml` gains its own per-level annotation walk distinct from word 3's
shared §3.6 emulation — a catalog-scoped variant of sibling inheritance, not a change to the
word every other catalog relies on.

### OI-92 — annotation readers fold the RAW `annotations` table, so an inherited marker and a repeated container both read false (merged with `OI-93`)
**Minor · logged 2026-09-18, found at the final whole-branch review of Groups B and C ·
`src/sextant/application/resolve/protocol_hint.py::apply_protocol_hints`,
`src/sextant/application/resolve/conditions.py::annotation_index`**

`apply_protocol_hints` reads `annotation_index`, a fold over the raw `annotations` table.
The inheritance walk (`effective_annotations.py::inherited_rows_over`) synthesizes an
interface method's mapping — and, for a catalog declaring `inherit_siblings:
all_or_nothing`, its declared siblings, `protocol_hint.hint_annotations` among them — onto
an annotation-free implementor method, but those rows exist only as the `$synthetic`
parameter `derive_endpoints.sql` binds; nothing persists them, and the hint pass never sees
them. So the walk carries `@RestStreamElementType` onto the implementor for the SQL's
purposes and the pass, asked about the same handler a moment later, finds nothing there.
The three documents that said the pass "needs no inheritance awareness" (D02 §3b word 3,
spec §3b, the module docstring) are corrected with this entry.

**Real triggering input:** a Quarkus REST interface declaring `@GET @Path("/events")
@RestStreamElementType(APPLICATION_JSON) Multi<T> events()` and a class implementing it
with a bare `@Override` — the `OrdersApi`/`OrdersResource` shape `fixtures/orders-spring7`
carries, with the element-type marker on the interface method. The implementor's row
derives with the right verb and address (the walk carried both) and `protocol: http`, where
Quarkus serves SSE (CP-19 row 2a). Not present in any fixture: `fixtures/orders-quarkus`'s
`OrderResource#events` writes the marker on the class's own method.

**Cost:** an `http` row where the framework serves an event stream — under-classified,
never fabricated; the address and verb are right, the protocol column is the pre-`jaxrs-sse`
answer for that one row.

**Verify:** `grep -n "annotation_index(workspace)" src/sextant/application/resolve/protocol_hint.py`
— the pass's one annotation read; `grep -n "synthetic" src/sextant/storage/duckdb/derive_endpoints.sql`
— the only consumer of the walk's rows. **Closes** when the pass reads the composed
annotation universe (`_synthetic_annotations`'s output folded into the index it consults)
or the walk persists its synthesized rows into a table every downstream reader folds — one
change, made once, rather than a second inheritance walk inside the pass.

#### The repeated-container symptom, filed separately as `OI-93` and merged here 2026-10-18

`@KafkaListener(topics = "a", batch = "true") @KafkaListener(topics = "b")` compiles to a
`@KafkaListeners` CONTAINER, which the SQL side unfolds and `conditions.holds` does not: the
fold over the raw `annotations` table finds `@KafkaListeners` and never `@KafkaListener`, with
`batch` inside the container's `value` array where the condition's `names` lookup cannot reach.
So `wrappers[].when` is false, the `List` wrapper stays off, and the row publishes the array —
`array<X>` where the listener takes a batch.

**WHY THE TWO ARE ONE ITEM.** `OI-93`'s own closing line said it: *"Closes with `OI-92`'s fix
and by the same change: one composed annotation universe (folded, composed, inherited) that
every annotation reader folds, rather than a second unfold inside `conditions.py`."* One cause
— every annotation reader folds the raw table rather than a composed one — two symptoms, one
edit. Separate numbers made it look like two, and the pattern this register keeps hitting is
that the narrower of a pair gets fixed and the other is discovered again later.

**Both symptoms close together**, and a fix that cures one and not the other has not made the
composed universe it claims to.

### OI-93 — a REPEATED `@KafkaListener(batch = "true")` never satisfies `wrappers[].when` · **MERGED INTO `OI-92` (2026-10-18)**
**Minor · logged 2026-09-18 · the body now lives under `OI-92`**

One cause (every annotation reader folds the RAW `annotations` table), two symptoms (an
inherited marker, a repeatable container), one edit — which this entry's own closing line
already named as `OI-92`'s. Nothing cites `OI-93` outside this file; the stub is kept so the
number resolves rather than looking lost.

### OI-94 — a batch listener's reply row roots its payload with the unconditional wrappers, so `@SendTo` on a `List<X>`-returning batch listener publishes `X` as the response and `array<X>` on the reply
**Minor · logged 2026-09-18, found at the final whole-branch review of Groups B and C ·
`src/sextant/application/resolve/engines/annotation_driven.py::_derive_replies`,
`src/sextant/application/resolve/shapes/contracts.py::_contracts_of`**

`_contracts_of` roots one handler's request AND response with `_wrappers_for(rules, owner,
index)` — the unconditional wrappers plus each conditional one whose `when` holds on the
owner (spec §5a, once per owner for both columns). `_derive_replies` roots the same
handler's return type for the reply row with `rules.wrappers` alone — the unconditional
list, `conditional_wrappers` never consulted. For a listener declaring `batch = "true"` and
returning `List<X>` under `@SendTo`, the conditional `List` wrapper holds on the handler:
the response column unwraps to `X`, and the reply row, rooted a moment later without it,
publishes `array<X>`. One handler, one return type, two answers.

**Real triggering input:** `@KafkaListener(topics = "t", batch = "true") @SendTo("replies")
List<Reply> onBatch(List<OrderEvent> events)` — a batch listener that replies. Not present
in any fixture: `fixtures/orders-service`'s batch methods return `void`, and its `@SendTo`
listener is a record listener. Whether Spring's batch reply is one message per element or
one message carrying the list is itself unmeasured — the two rows disagree with EACH OTHER,
which is the defect here, before either is checked against the framework.

**Cost:** two columns describing one return type differently; both are real types the
handler names, neither fabricated.

**Verify:** `grep -n "rules.wrappers" src/sextant/application/resolve/engines/annotation_driven.py`
— the reply rooting's wrapper argument; `grep -n "_wrappers_for" src/sextant/application/resolve/shapes/contracts.py`
— the per-owner list the response uses. **Closes** when `_derive_replies` roots with the
same per-owner `_wrappers_for` list `_contracts_of` uses, after CP-20 says which of the two
answers Spring's batch reply actually is.

### OI-95 — a `jakarta.*` API coordinate at a Jakarta EE 8 version is `javax`-packaged, and the family's coordinate lists cannot say so
**Minor · logged 2026-09-18, found at the final whole-branch review of Groups B and C, logged
once for the whole `javax`/`jakarta` family · `src/sextant/catalogs/jakarta-jaxrs.yml`,
`javax-jaxrs.yml`, `jakarta-jms.yml`, `javax-jms.yml`; `src/sextant/application/resolve/dependencies.py`**

`jakarta.ws.rs:jakarta.ws.rs-api` 2.1.x (Jakarta EE 8) ships `javax.ws.rs.*` classes under
the `jakarta` coordinate; the `jakarta.ws.rs.*` packages arrive at 3.0. The same is true of
`jakarta.jms:jakarta.jms-api` 2.0.x. `detect.coordinates` is `group:artifact` with no
version, so a module on the EE 8 artifact matches `jakarta-jaxrs.yml`'s coordinate and
declares nothing that matches `javax-jaxrs.yml`'s (`javax.ws.rs:javax.ws.rs-api`), while its
bytecode carries `javax/ws/rs/GET` — the spelling only `javax-jaxrs.yml` reads.
`javax-jaxrs.yml`'s own header comment records that CP-18 never opened the 2.1.6 artifact,
which is why the coordinate is not simply added to that file (§5.4).

**What happens today:** nothing wrong. An `annotation_driven` catalog gates on the
annotation fqn, not the coordinate (`dependencies.py::gate_reason` reads coordinates only
for `DEPENDENCY_GATED` styles and `detect.required` catalogs, and neither JAX-RS catalog
declares the latter), so `javax-jaxrs.yml` runs, matches every `javax.ws.rs` use and
derives every row; `jakarta-jaxrs.yml` runs, matches nothing and derives nothing. The
`jms` pair is the same shape on `single_call`, which gates on descriptors. **The shape is
unhandled, not wrong**: the day `detect.coordinates` becomes the module-wide activation
gate D02 §12 describes (`OI-83`), or any coordinate read of the `superseded_by` kind is
applied to this family, the EE 8 module activates the `jakarta` catalog and not the `javax`
one, and derives nothing — an under-derivation the coordinate lists as written cannot
prevent, because neither can say "this coordinate below 3.0 is the other spelling".

**Real triggering input:** a Jakarta EE 8 module — `jakarta.ws.rs:jakarta.ws.rs-api:2.1.6`
or `jakarta.jms:jakarta.jms-api:2.0.3` in its POM, `javax.*` imports in its sources. Not
present in any fixture.

**Verify:** `grep -n "coordinates" src/sextant/catalogs/jakarta-jaxrs.yml src/sextant/catalogs/javax-jaxrs.yml`
— one unversioned coordinate each; `grep -n "DEPENDENCY_GATED = " src/sextant/application/resolve/dependencies.py`
— the two styles coordinates gate today. **Closes** when the coordinate grammar can carry a
version bound (`jakarta.ws.rs:jakarta.ws.rs-api:>=3.0` on the `jakarta` file, `<3.0` on the
`javax` one) and the EE 8 artifact's packaging is measured on the artifact itself, or when
the activation gate is designed to fall back to the annotation fqn for this family.

### OI-96 — `apply_protocol_hints` can reclassify an OUTBOUND row after `fluent` wrote its metadata
**Minor · logged 2026-09-20, found at the Kotlin/Ktor spec's Task 7 review (W29 order, unchanged
there) · `src/sextant/application/resolve/pipeline.py`, `engines/fluent.py`**

The fluent engine writes an outbound row's `endpoint_metadata` entries (W29) inside
`derive_endpoints`, keyed by the row's identity columns, `protocol` among them.
`apply_protocol_hints` runs BELOW `derive_endpoints` and reclassifies `protocol` on rows the
engines minted. A `fluent` row a hint reclassified would leave its metadata entries naming a
`protocol` the row no longer carries — entries nobody can join back. The inbound writer
(`record_request_requirements`, spec 2026-09-19 §5a) was placed below the hint pass for exactly
this reason; the outbound writer was not moved because W29's order is pinned and no shipped
hint reaches a `fluent` row.

**What happens today:** nothing wrong. `protocol_hint` catalogs (`hint_when`,
`hint_annotations`) target annotation-derived rows — `@JMSListener`/`@JMSProducer` over SQS,
the SSE markers; no `fluent` catalog's rows are reclassified by any shipped hint.

**Real triggering input:** none today; a future hint over a `fluent` client (a WebClient call
reclassified as SSE by its `Accept: text/event-stream` header, say) would produce orphaned
metadata rows.

**Verify:** `grep -n "endpoint_metadata_insert" src/sextant/application/resolve/engines/fluent.py
src/sextant/application/resolve/request_requirements.py` — the outbound insert inside the
engine (`fluent.py:~305`, called from `derive_endpoints`), the inbound one in
`request_requirements.py:~55`, whose caller `pipeline.py` places below `apply_protocol_hints`. **Closes** when the outbound entries are written through the
same post-hint writer, or when a hint pass rewrites the side table's `protocol` with the row's.

### OI-97 — two `combinator` catalogs exhausting the helper depth in one resolve file two `routing_depth` rows under one identity
**Minor · logged 2026-09-20, found at the Kotlin/Ktor spec's Task 8 review ·
`src/sextant/application/resolve/engines/combinator.py::_routing_depth_rows`,
`storage/duckdb/insert_open_questions.sql`**

A `routing_depth` question's identity is `(protocol, NULL, NULL, routing_depth)` on purpose
— every deep chain of a run is one candidate of ONE row (spec 2026-09-19 §4a, M3). But the row
is built per catalog: two `http` combinator catalogs (`ktor-routing.yml` and
`spring-webflux-router.yml`, say) each exhausting the bound in one module would each file a
row, and `insert_open_questions.sql` appends, so the ledger would hold two rows with one
identity. The rendered document would then show two `routing_depth` lines for one module
with nothing to say which catalog each came from — the same problem `service_identity._merged`
solved by merging one kind's rows into one, only here across two catalogs.

**What happens today:** nothing wrong. No fixture and no real module analysed so far nests
routing helpers sixteen deep in any catalog, let alone two.

**Real triggering input:** a module using two combinator-style routers of one protocol, each
with a helper chain deeper than sixteen calls.

**Verify:** `grep -n "_routing_depth_rows\|record_open_questions" src/sextant/application/resolve/engines/combinator.py`
— one call per `run`, i.e. per catalog. **Closes** by merging the question across catalogs
before the insert (a per-resolve accumulator, as the stash is), or by putting the catalog id
into the identity.

### OI-98 — the whole-map skip in `request_params` is by EXACT erased type, where Spring's is `isAssignableFrom`
**Minor · logged 2026-09-20, found at the Kotlin/Ktor spec's Task 12 review ·
`src/sextant/application/resolve/request_requirements.py::_from_parameters`,
`src/sextant/catalogs/spring-mvc.yml`, `spring-web.yml`**

`skip_types: [java.util.Map, org.springframework.util.MultiValueMap]` on `@RequestParam`
skips a parameter whose erased type IS one of those names. Spring's
`RequestParamMapMethodArgumentResolver.supportsParameter` uses
`Map.class.isAssignableFrom(parameter.getParameterType())` (spring-web 6.1.6 source, read; not a
CP-25 row — one would settle it), so a `@RequestParam HashMap<…>`
or `LinkedMultiValueMap` is a whole-map binding to Spring and not to this pass, which would
write one `param` row named after the parameter — a requirement Spring never enforces.

**What happens today:** the fixtures spell `Map`/`MultiValueMap`/`HttpHeaders`, the idiomatic
declared types; nothing wrong on them.

**Real triggering input:** `@RequestParam HashMap<String, String> all` — legal, unidiomatic.

**Verify:** `grep -n "skip_types" src/sextant/application/resolve/request_requirements.py` — a
set membership on the erased symbol. **Closes** when the skip walks the parameter type's
supertype chain (the facts carry `superclass`/`interfaces` for module types; a JDK type's
hierarchy would need the extractor's knowledge of the platform) or the catalog lists the
concrete spellings a codebase uses.

### OI-99 — a helper reached as a member call ON the routing origin is not followed
**Minor · logged 2026-09-20, a stated boundary of spec 2026-09-19 §4a (M3) ·
`src/sextant/application/resolve/engines/combinator.py::_helper_routes`**

Helper following requires the origin to flow into the callee as an ARGUMENT
(`{kind: parameter, value: origin}`), which is what a Kotlin extension function and a static
helper compile to. A helper written as a MEMBER of the routing type — `class MyRoutes :
Route { fun api() { get("/x") { } } }` called as `this.api()` inside a block — puts the origin
in the callee's `this`, which no parameter index names; the walk does not guess a
receiver-to-`this` mapping and the helper's routes are silence, as every helper's were before.

**Real triggering input:** a module subclassing the framework's route type and declaring
routing methods on it. Ktor's `Route` is an interface with a private implementation, so this
is rare there; a Javalin or Spring DSL module could write it.

**Verify:** `grep -n "member call ON the origin" src/sextant/application/resolve/engines/combinator.py`.
**Closes** with a `this`-origin rule: a member call whose receiver is the origin makes the
callee's `this` the origin, at the cost of a second origin form every head check must know.

### OI-100 — the Spring router's `Supplier<RouterFunction>` bodies do not follow helpers
**Minor · logged 2026-09-20, a stated boundary of spec 2026-09-19 §4a (A1) ·
`src/sextant/catalogs/spring-webflux-router.yml`, `spring-mvc-router.yml`**

A `Supplier` body is origin-less — it returns a router rather than mutating one — and
follows module-local calls only where its rule declares `follow_calls: all`, which the
Spring router catalogs do not: a callee there may build routers that are never returned, and
following it would attach routes the framework never registered. So `route().nest(path("/api"),
() -> helper())` with `static RouterFunction helper() { return route(GET("/x"), h); }` derives
the nest and not `/api/x`.

**Real triggering input:** a Java functional-routing module factoring its routers into static
helpers called from `Supplier` bodies — a common Java style.

**Verify:** `grep -n "follow_calls" src/sextant/catalogs/spring-*router.yml` — none.
**Closes** by following a `Supplier` callee whose RETURN VALUE reaches the body's own return
(the return-flow facts exist), which is the honest version of "the router it builds is the one
the supplier hands back".

### OI-101 — Ktor 2.x handler bodies name the interface receivers, which are not `via` owners
**Minor · logged 2026-09-20, found at Task 14 when the `via` owners were measured ·
`src/sextant/catalogs/ktor-routing.yml` (`request_reads`)**

The `via` owners are the 3.0.3 CLASS overrides a handler body's bytecode names:
`RoutingContext.getCall()` is a `RoutingCall`, so `call.parameters` is `invokevirtual
RoutingCall.getParameters` and `call.request.headers` reaches `RoutingRequest.getHeaders`. In
Ktor 2.x a handler is `PipelineContext<Unit, ApplicationCall>.() -> Unit`, `call` is typed
`ApplicationCall`, and the same source compiles to `invokeinterface
ApplicationCall.getParameters`/`ApplicationRequest.getHeaders` — owners no entry names, so a 2.x
handler's reads write nothing. The catalog's `measured:` block is 3.0.3 alone (§5.4).

**Real triggering input:** any Ktor 2.x module, a large share of Ktor estates.

**Verify:** `grep -n "via:" src/sextant/catalogs/ktor-routing.yml` — `RoutingCall`,
`RoutingRequest` only. **Closes** when a 2.x jar is measured (the w19-style probe over
`ktor-server-core-jvm:2.3.x`) and the interface owners are added as further `via` entries —
each one measured, never mirrored from 3.0.3.

### OI-102 — a Javalin FLAT row's `Handler` lambda reads are invisible
**Minor · logged 2026-09-20, a stated boundary of spec 2026-09-19 §5d (M9) ·
`src/sextant/catalogs/javalin.yml`**

`request_reads` scans the HANDLER BODY of every inbound row. A `single_call` row's `handler`
is the registering method — `app.get("/x", ctx -> ctx.queryParam("q"))` derives with
`handler = OrderApp#flat`, not the lambda — so the lambda's `queryParam`/`header`/`cookie`
calls are in a body this pass never opens, and the flat forms write no requirement rows. The
`ApiBuilder` rows (`javalin-apibuilder.yml`, a `combinator` catalog) carry the lambda body as
`handler` and read fully.

**Real triggering input:** every Javalin module written in the flat style, which is the
framework's own first example.

**Verify:** `tests/e2e/test_rest_inbound_delivered.py::test_javalin_handler_reads_reach_endpoint_metadata`
asserts reads on `/jv/nested/reads` (`ApiBuilder`) and none on the flat rows. **Closes** when
`single_call` rows carry the handler lambda in a column of their own (the `handler_arg` word
the combinator has), or when the reads pass follows a row's `handler_arg`-shaped argument.

### OI-103 — `AdaptedFunctionReference` is recognised by name and unmeasured
**Minor · logged 2026-09-20, found at CP-23 Q9 (`e6497f0`) ·
`extractor-jvm/…/ClassScanner.java` (the `lambda_body` superclass set), `scripts/probes/cp23_kotlin_call_shapes.md`**

The extractor marks a class with `lambda_body` when its superclass is `Lambda`,
`SuspendLambda`, `FunctionReferenceImpl` or `AdaptedFunctionReference`. The first three are
measured on kotlinc 2.2.0 output in CP-23; the fourth — the class kotlinc emits for an ADAPTED
function reference (a reference whose signature needs coercion: a defaulted parameter left
out, a vararg spread, a `Unit` return adapted) — is present in kotlin-stdlib 2.2.0 by `javap`
(CP-23 Q9) and no fixture produces a subclass of it: its emission is unobserved, and its
body-method rule (the one non-synthetic `invoke`) is assumed, not read off a class file (§5.4).

**Real triggering input:** `GET("/x", ::handlerWithDefaults)` where the referenced function
declares a default the reference omits, under `-Xlambdas=class` or as a suspend reference.

**Verify:** `grep -n "AdaptedFunctionReference" extractor-jvm/src/main/java -r`;
`grep -n AdaptedFunctionReference scripts/probes/cp23_kotlin_call_shapes.md` — named as "not exercised by this source", no measured row.
**Closes** when CP-23 gains a Q compiling an adapted reference and the marked body is asserted
in `KotlinLambdaBodyTest`.

### OI-104 — a WRITTEN Micronaut name also accepts the parameter's hyphenated name, and the row states the written one alone
**Minor · logged 2026-09-20, found at the whole-branch review (item 1, CP-25 row 18) ·
`src/sextant/catalogs/micronaut-http.yml` (`request_params`),
`src/sextant/application/resolve/request_requirements.py::_name`**

`AbstractArgumentBinder.doResolve` (micronaut-core 4.7.6) reads the name the binder resolved
— the written `value`/`name`, else the parameter's own — and, finding nothing, retries with
`getFallbackFormat(argument)`, which is ALWAYS the hyphenated form of the PARAMETER'S name
(`NameUtils.hyphenate`; the header binder capitalizes first), whether or not a name was
written. So `@Header("X-Tenant") String tenantHeader` is served by `X-Tenant` OR
`Tenant-Header`, and `@QueryValue("q") String query` by `?q=` or `?query=`. The row states the
written name alone. Where NO name is written the branch already refuses the parameter's own
name when the fallback respells it (`fallback_spelling`); the written case was ruled stated,
not built: the written name is the one every client of the API is told to send, and a second
accepted spelling is a leniency, not a requirement on it.

**What happens today:** `header X-Tenant required` on the fixture's `search` — true of a
client that sends `X-Tenant`; a client sending `Tenant-Header` is also served and the row
does not say so.

**Real triggering input:** any annotated Micronaut parameter with a written name whose
declared name hyphenates to something a client actually sends — rare by construction, since
the written name is the documented one.

**Verify:** `grep -n "fallback_spelling" src/sextant/application/resolve/request_requirements.py`
— read only where no name attribute was written. **Closes** when the writer records the
fallback as a second accepted spelling (a second row, or a column for it) — a schema question,
D01 §3.

*Measured on real code 2026-10-18 (`ruoyi-vue-pro`), which adds a case the entry did not
name: the ladder reads a `@ConfigurationProperties` getter and **not a nested one**.
`yudao-spring-boot-starter-websocket` sends with*

```java
kafkaTemplate.send(topic, mqMessage)   // topic ← websocketProperties.getSenderKafka().getTopic()
rabbitTemplate.convertAndSend(topicExchange.getName(), null, mqMessage)
```

*and both rows publish no destination. The first is a getter on a getter — the properties
class nests `SenderKafka` inside `WebSocketProperties`, which is how every multi-transport
`@ConfigurationProperties` tree is written. The second is this entry's own bean rung
(`TopicExchange` is a `@Bean` whose name comes from configuration), so it is already covered.
Both are honest `unresolved` rows with a named caller, which is the behaviour `OI-146` asks for
elsewhere.*

### OI-105 — `optional` for a Kotlin default parameter assumes `kotlin-reflect` at runtime
**Minor · logged 2026-09-20, found at the whole-branch review (item 2, CP-25 row 3) ·
`src/sextant/catalogs/spring-mvc.yml`, `spring-web.yml` (`request_params`),
`src/sextant/application/resolve/request_requirements.py::_requirement`**

`MethodParameter.isOptional()` (spring-core 6.1.6) reaches its Kotlin branch —
`KotlinDelegate.isOptional`, which reads `KType.isMarkedNullable()` and
`KParameter.isOptional()` — only behind `KotlinDetector.isKotlinReflectPresent()`, and
`resolveArgument`'s default-value read is gated the same way. Without `kotlin-reflect` on the
RUNTIME classpath, `@RequestParam page: Int = 0` is `required` to Spring (a `@RequestParam
tag: String?` stays `optional`: kotlinc's `@Nullable` declaration annotation is read by
`hasNullableAnnotation()` without reflection; the declared default has no such second path).
The binder rule writes `optional` for `declares_default: true` unconditionally.

**What happens today:** every Kotlin Spring module this repository has seen carries
`kotlin-reflect` — Initializr adds it, `jackson-module-kotlin` depends on it — so the row is
right on all of them; nothing checks.

**Real triggering input:** a Kotlin Spring module that excludes `kotlin-reflect` (a
size-trimmed image) and declares a defaulted `@RequestParam`.

**Verify:** `grep -n "declares_default" src/sextant/application/resolve/request_requirements.py`
— no dependency gate around it. **Closes** when the pass can gate the `declares_default`
disjunct on `org.jetbrains.kotlin:kotlin-reflect` being on the module's RESOLVED runtime
classpath — which needs transitive dependency resolution: the Gradle detector reports the
resolved compile classpath, the Maven one declared-plus-inherited coordinates and no
transitives (`resolve/dependencies.py`, F1), and `kotlin-reflect` most often arrives
transitively through `jackson-module-kotlin`, exactly where a Maven-side gate would be blind.

### OI-106 — the field ladder has no bean rung: a `Publisher`, `WebClient` or `KafkaTemplate` built in one `@Bean` method and injected into another is still unresolved
**Minor · logged 2026-09-21, the named follow-up of spec 2026-09-21 §3a (its §0c B1) ·
`src/sextant/application/resolve/shapes/arguments.py::address_argument` (the ladder),
`src/sextant/application/resolve/beans.py` (the fold it would read)**

The field ladder reads a literal, a `@Value` field or parameter, and a `@ConfigurationProperties`
getter. A value BUILT in one `@Bean` method and injected into the method under analysis —
`google-pubsub-publisher.yml`'s config-built `Publisher`, `spring-webclient.yml`'s `WebClient`
bean with a `baseUrl`, a `KafkaTemplate` with a default topic — has no rung, and each is a stated
boundary in COVERAGE (§5.11, §5.2, §5.8). `resolve/beans.py` now answers "which `@Bean` method
built this parameter" for the fluent engine's `bean_via`, and `_bean_chain_capture` walks that
method's chain for a capture; the ladder does not call either.

**What happens today:** those rows derive `path` NULL, `unresolved`, as their COVERAGE rows say.

**Real triggering input:** the commonest Spring style — a client bean configured once and
injected everywhere.

**Verify:** `grep -n "bean" src/sextant/application/resolve/shapes/arguments.py` — no reference
to the bean fold. **Closes** when the ladder gains a rung that resolves the parameter through
`bean_of` and folds the bean method's chain as `fluent._bean_chain_capture` does, once, in the
bean method's own context.

*Not the same item as `OI-110`, which is the fluent engine's `bean_via` folding only ONE hop (a
container built in a third bean). Same root — a bean-graph join is not a value edge, so the
value walk reaches neither, and `OI-110` carries that measurement — but a different file, a
different mechanism and a different fix: this is a MISSING rung, that is a rung that stops too
early. Cross-referenced rather than merged.*

### OI-107 — `sends_to` edges have no reader
**Minor · logged 2026-09-21, found at the Task 4–5 fix round (`059342a`) ·
`src/sextant/application/resolve/engines/fluent.py::_edge`,
`src/sextant/application/resolve/channel_bindings.py::mint_channel_rows`**

A `channel_link` captured AFTER a handler is that handler's output channel, written as a
`channel_bindings` row with `role: sends_to` (spec §3b's reserved slot, first writer). The mint
pass reads `fed_by` and `read_by` only, and `config_join.gaps` skips a channel on a `fed_by`
alone — so a `sends_to` edge is recorded and consulted by nothing: the channel it names, if a
`@ServiceActivator` reads it, is still asked about as a `channel_destination` question.

**What happens today:** `handle(h).channel("out")` in the fixture writes the edge; no fixture
handler reads `out`, so nothing is visibly wrong.

**Real triggering input:** a flow whose handler's output channel is read by an annotated
handler — the classic two-stage Spring Integration pipeline.

**Verify:** `grep -n "sends_to\|_SENDS_TO" src/sextant/application/resolve/channel_bindings.py` —
empty; in `engines/config_join.py` the role is named only in the comment above `_READ_BY`, which
says it is read by nothing there — no `_SENDS_TO` constant, no query on the role. **Closes** when the mint pass
or `gaps` reads the role — a `sends_to` is a feeder whose wire is the sender's own row, so the
reader's question is answerable by that row — and `@MessagingGateway`/`channel.send(…)` gain
writers on the same role.

### OI-108 — `@Profile`-conditional twin beans are reported unconditionally · **CLOSED 2026-10-22**
**Minor · logged 2026-09-21, a stated boundary of spec 2026-09-21 §0c B5 (shares
`conditional-controllers`' exposure) · `src/sextant/application/resolve/beans.py::declared_beans`,
`src/sextant/application/resolve/engines/fluent.py`**

The bean fold reads `@Bean` and `@Qualifier` and nothing conditional: two `@Bean` methods of one
NAME under different `@Profile`s are `Unresolved(ambiguous)` to every reference (a miss, safe),
but two adapter beans under different profiles each derive their own row, and one channel bean
per profile with distinct names resolves whichever a parameter names. A registration that exists
in one deployment and not another is reported as existing — exactly `conditional-controllers`'
question for `@ConditionalOnProperty`/`@Profile` controllers, one table over.

**What happens today:** no fixture declares `@Profile` on a `@Bean`; nothing wrong on them.

**Real triggering input:** a module with a `@Profile("local")` in-memory adapter beside its
`@Profile("prod")` broker one.

**Verify:** `grep -n "Profile\|Conditional" src/sextant/application/resolve/beans.py` — empty.
**Closes** with `conditional-controllers`' mechanism: a row's existence conditional on
configuration, stated on the row rather than decided.

**2026-10-22 — the mechanism exists, this issue stays open.** `conditional-controllers`
shipped (spec `2026-10-21-conditional-controllers-design.md`): the `endpoint_conditions`
table, the `mapping.conditions` catalog block with CP-42/CP-43, and `_holds` in
`resolve/endpoint_conditions.py` evaluate `@Profile` and `@ConditionalOnProperty` per
environment for a CONTROLLER. The bean fold is the next consumer of the same table — 68 of
the 69 conditional classes measured across the cloned corpora are beans, not controllers —
and it is not written: `beans.py` still reads nothing conditional. Closes when a `@Bean`
under `@Profile`/`@ConditionalOnProperty` writes rows stating where it exists.

**2026-10-22 — CLOSED by `cov/conditional-beans`** (spec `2026-10-22-conditional-beans-design.md`).
The bean fold was not the thing to change: the condition is stated on the BEAN, once, in
`bean_conditions`, by one pass for every bean (a scanned class, a `@Bean` method, a `@Bean`
inside a conditional configuration, an interface the framework implements), and everything
derived from a bean finds it by a join — `beans.py` still reads nothing conditional, and does
not need to. The case this entry named — an adapter bean under `@Profile("local")` beside
`@Profile("prod")` — derives its rows as before and now states, on each, where its bean
exists; a call whose candidates are such beans states which exist in each environment. A row
whose code is the `@Bean` method's OWN body — an inline adapter flow it builds and returns —
states the factory's condition too: each conditional `@Bean` method is written as a bean of
its own, `via` itself, the way the lambdas it creates are (`symbol_beans` finds the method
before its configuration class).
Measured on `apollo-portal`, `yudao-module-system`, `yudao-spring-boot-starter-websocket`
and `spring-petclinic-rest` (spec §1, "As built"); the fixture
`orders-service/.../conditional/` pins each shape. The part of this entry that stays true is
the one it stated: nothing is DROPPED — a registration that exists in one deployment is still
reported, with the deployments it exists in.

### OI-109 — a spec configurer adding queues is a miss
**Minor · logged 2026-09-21, a stated boundary of spec 2026-09-21 §5 (adversarial B5) ·
`src/sextant/catalogs/spring-integration-amqp.yml`,
`src/sextant/application/resolve/engines/fluent.py::_walk`**

`Amqp.inboundAdapter(cf, "q1").configureContainer(c -> c.addQueueNames("q2"))` adds a queue
inside a lambda the walk does not open: the row reports `q1` alone. Fewer queues, never a wrong
one.

**What happens today:** no fixture writes the form.

**Real triggering input:** a DSL flow tuning its container in a configurer that also names
queues — uncommon but legal.

**Verify:** `grep -n "configureContainer" src/sextant/catalogs/spring-integration-amqp.yml` —
named as a boundary, declared by no step. **Closes** with a read of the configurer's lambda
body against the container's own steps — the shape `single_call`'s `lambda_arg`/`lambda_steps`
already read for `spring-cloud-gateway-outbound.yml`, brought to a fluent step.

### OI-110 — a container built two beans away is unresolved
**Minor · logged 2026-09-21, a stated boundary of spec 2026-09-21 §4 (one hop) ·
`src/sextant/application/resolve/engines/fluent.py::_bean_chain_capture`**

`bean_via` folds ONE hop: the adapter's argument resolves to a container bean, and that bean's
own chain supplies the queues. A container whose queues come from a THIRD bean (a `Queue` bean
injected into the container's method, a container factory bean) is `unresolved(bean_second_hop)`
— a `bean_via` met inside the collecting walk is a poison there. The adapter's row derives with
`path` NULL.

**What happens today:** the fixture's `topologyContainer` takes a `Queue` parameter and derives
unresolved, as pinned; nothing references it.

**Real triggering input:** the Spring AMQP style that declares `Queue` beans for auto-declaration
and injects them into the container.

**STILL OPEN after the value walk, and the measurement says why** (Task 13, 2026-10-17).
The walk named in spec 2026-09-22 was expected to close this and does not. Measured on
`fixtures/spring-integration-probe` with `--shadow`:

| position | answer |
|---|---|
| `AmqpTopologyBeans#topologyContainer`@1 slot 0 — the `setQueues(topologyOrdersQueue)` argument | `unresolved(external)` |
| `AmqpTopologyBeans#topologyOrdersQueue`@0 slot 0 — the `new Queue("topology.orders.queue")` literal | `would_resolve` → `topology.orders.queue` |

**The value is one bean away and readable; the walk cannot get to it, and the reason is
structural rather than a missing edge.** A `@Bean` method's parameter is bound by the
CONTAINER, reflectively — there is no call site in the module's bytecode, so no
`bound_to_parameter` edge exists to cross and `external` is the correct answer. The
remaining hop is a bean-graph join (by type, name, qualifier or `@Primary`), which is
`bean_via`'s own mechanism and not a value edge. So the walk made this issue no easier and
no harder, and the fix is still the one below.

**Verify:** `grep -n "One hop only" src/sextant/application/resolve/engines/fluent.py` — the
docstring of `_fold_bean_captures`, which still reads *"a container built in a third bean is
unresolved"*. (This line cited `second_hop` until 2026-10-17; the reason string is built as
`f"bean_{reason}"`, so the grep matched nothing and looked like a closed issue.)
**Closes** with a bounded multi-hop fold (the depth guard the combinator's helper walk already
has), each hop in its own bean method's context.

*`OI-126` states that it closes WITH this one — *"one mechanism answers both, and answering
them separately would be two"* — and the back-reference was missing here, so a reader costing
this item saw one symptom instead of two. They are kept apart rather than merged because the
two differ in how the OTHER body is found: a bean-graph join here, a value handed to a method
there. What they share is folding a chain in a body that is not the caller's, which is the
piece neither has.*

### OI-111 — Gateway `filters` rewrite the upstream path and are not read
**Minor · logged 2026-09-21, a stated boundary of spec 2026-09-21 §7b ·
`src/sextant/catalogs/spring-cloud-gateway-properties.yml`, `spring-cloud-gateway.yml`,
`src/sextant/application/resolve/engines/config_join.py::_indexed_items`**

`RewritePath`, `StripPrefix`, `PrefixPath` and `SetPath` change the path the gateway sends
UPSTREAM; the served path is the predicate's, and that is what the inbound row publishes. The
outbound row carries the `uri` verbatim, so a route `Path=/api/orders/**` + `StripPrefix=1` +
`uri: lb://orders` reports the target as `lb://orders` and says nothing about `/orders/**` being
what the upstream sees — the stitcher matching this outbound row to the upstream's inbound row
has no path to compare. The DSL catalog has the same boundary for `.filters(f -> f.stripPrefix(1))`.

**What happens today:** the fixture's routes declare no filters.

**Real triggering input:** nearly every real gateway configuration — prefix-stripping is the
framework's own first example.

**Verify:** `grep -n "filters" src/sextant/catalogs/spring-cloud-gateway-properties.yml` — named
unread. **Closes** when the outbound row can carry the rewritten path (a `path` on a `lb://` target
row, which D02 keeps whole today) — a schema question before a catalog one.

### OI-112 — `IntegrationFlow.from(<adapter bean>)` is not declared
**Minor · logged 2026-09-21, a stated boundary of spec 2026-09-21 §5 (Task 6 deviation 1,
ratified) · `src/sextant/catalogs/spring-integration-pubsub.yml`, `spring-integration-amqp.yml`,
`spring-integration-kafka.yml`; `src/sextant/application/resolve/engines/fluent.py::_matching_root`**

`from(MessageProducerSupport)` is the one `from` overload EVERY broker's adapter satisfies (CP-28
row 2). A root matched by descriptor cannot tell whose adapter arrived: declared in the Pub/Sub
catalog, an AMQP adapter bean handed to it would match, the bean fold would find no Pub/Sub
constructor in that bean's method, and the catalog would derive an unresolved row under
`protocol: pubsub` for another broker's wire — a wrong row. So no catalog declares it, and a flow
sourced from an adapter BEAN derives its adapter's own row (`handler` NULL) and nothing for the
flow's handler.

**What happens today:** no fixture writes the form.

**Real triggering input:** `IntegrationFlow.from(pubSubAdapter).handle(…)` — a documented
Spring Cloud GCP idiom.

**Verify:** `grep -n "MessageProducerSupport" src/sextant/catalogs/spring-integration-*.yml` —
named as a boundary, declared by no root. **Closes** with the general fix: derive only when
`bean_via` resolved to a `beans:` root of THIS catalog — the bean fold gating on the bean's
constructor owner — after which each broker catalog declares the overload safely.

### OI-113 — `resolved_config` carries no declaration order
**Minor · logged 2026-09-21, found at the Task 8 fix round 2 (`b98bba0`) ·
`src/sextant/application/resolve/engines/config_join.py::_fields_of`, `_flattened_order`;
`src/sextant/storage/duckdb/schema.sql` (`config_entries.seq`)**

`config_entries` carries `seq` (declaration order within the file, `rowid`), and
`resolved_config` — the one input `config_join` reads — does not: the resolver keys by
`(key, environment)` and the order of a flattened list's non-positional map-form keys is lost.
The `indexed:` form therefore finds Gateway's `Path` tail flag BY VALUE (the one `true`/`false`
literal among the gathered values) rather than as the LAST value the author wrote, and reads
two such literals as unread; the gather order of non-positional keys is flattened-key order, not
as written. Only the flag depends on it today.

**What happens today:** the documented map form (`patterns`, `matchTrailingSlash`) reads
correctly by value; a route whose `args` carry two booleans is unread, stated.

**Real triggering input:** none known — no predicate factory at 5.0.0 gathers two boolean
fields.

**Verify:** `grep -n "declaration order" src/sextant/application/resolve/engines/config_join.py`.
**Closes** when `resolved_config` carries the winning entry's `seq` (one column, threaded from
`config_entries` through the resolver) and `_fields_of` orders gathered values by it.

### OI-114 — `${key:default}` in a channel name never applies the default
**Minor · logged 2026-09-21, found at Task 2 review · `src/sextant/application/resolve/engines/config_join.py::_channel_name`**

A channel named `${probe.audit-channel:auditChannel}` on a `@ServiceActivator` is looked up under
`probe.audit-channel`; configuration answering it resolves the name. Configuration NOT answering
it leaves the name as written, `unresolved`, and joins nothing — the spelled default is never
substituted, though Spring would use it. A miss (the channel is asked about under its raw
spelling), never a false join.

**What happens today:** the fixture's `${probe.audit-channel}` spells no default; nothing wrong.

**Real triggering input:** a channel name with a default, unset in every environment file.

**Verify:** `grep -n "default_separator" src/sextant/application/resolve/engines/config_join.py`
— the separator splits the key off; the default is not read. **Closes** when `_channel_name`
applies the default where no environment answers — the same rule the field ladder's
`resolved_peers` substitution would need, and D02 §2i's placeholder model already names the
separator.

### OI-115 — `_fold`'s captures are LAST-WINS, so a second `channel` and a second `handle` each overwrite the first (merged with `OI-121`)
**Minor · logged 2026-09-21, found at the Task 4–5 review · `src/sextant/application/resolve/engines/fluent.py::_fold_site`, `_derive`**

`.channel("x").handle(h).channel("y")` captures `channel_link` twice; the capture dict keeps `y`,
so the flow writes `sends_to(y, h)` and `read_by(x, h)` (the link `h` followed rides in its own
marker, `_READS_LINK`, which a later link no longer resets — residual fix, 2026-09-21) and the
row with `h` as the wire's handler; `fed_by(x)` — the channel the wire feeds BEFORE the handler —
is lost, and the row credits the wire with a consumer the framework subscribed to `x`. The
framework wires `fed_by(x)`, `read_by(x, h)`, `sends_to(y, h)` and no direct wire-to-`h` row. So:
two edges right, one edge missing, and the row's `handler` one hop too close — the same
mis-attribution as `OI-121`'s, from the other side. Under a channel source
(`from("a").channel("x").handle(h).channel("y")`) the shape is now correct — `read_by(x, h)`
and `sends_to(y, h)`, nothing for `a` (the bridge) — pinned by
`tests/application/test_fluent_registrations.py::test_a_channel_sourced_flow_that_links_before_and_after_its_handler_writes_both_edges`;
before the residual fix the reset credited `h` to `a`, a wrong edge.

**What happens today:** no fixture flow links two channels; measured on the invented flow
catalog, the wire shape writes `read_by(x, h)`, `sends_to(y, h)` and the row.

**Real triggering input:** a bridge-then-handle flow — uncommon; the idiomatic flow links once.

**Verify:** `grep -n "_LINK_SENDER\|_READS_LINK" src/sextant/application/resolve/engines/fluent.py`
— `_READS_LINK` holds the link the handler followed (the value, so `x` is in hand), `_LINK_SENDER`
the handler the later link followed. **Closes** when the wire branch writes `fed_by(x)` from
`_READS_LINK` and withholds the row where the `_LINK_SENDER` handler itself followed a link —
the value the fix needs is already there; what is missing is the wire branch reading it.

#### The `handler` slot, filed separately as `OI-121` and merged here 2026-10-18

`from("ch").channel("x").handle(h1).handle(h2)` captures `handler` twice; the capture dict keeps
`h2` (last wins, D02 §4), so the flow writes `read_by(x, h2)` and nothing for `h1`. The framework
subscribes `h1` to `x` and hands `h1`'s reply to `h2` on an anonymous channel — so `x`'s reader
is `h1`, and the row the join mints against `x` names `h2` as its handler and `h1` nowhere. A
mis-attribution one step along the chain: the wire and the channel are right, the handler column
is the next consumer rather than the first.

**What happens today:** no fixture flow handles twice in one chain; measured on the invented flow
catalog, the bindings table holds the one `read_by(x, h2)` edge.

**Real triggering input:** a flow that chains two `handle(...)` steps — the second a service
activator on the first's reply. Uncommon under a channel source; the idiomatic flow handles once
or transforms between. The Kafka catalog's boundary list states `handle(Object bean, String
method)` where the bean is the module's and the lambda flow form; this is the third `handle`
shape it does not read whole.

**Verify:** `grep -n '"handler" in folded' src/sextant/application/resolve/engines/fluent.py` —
one slot, folded by `_fold` last-wins.

**WHY THE TWO ARE ONE ITEM, and why they are now one entry.** Same function, same cause —
`_fold` keeps the last capture for a slot a chain may fill twice — and the same fix, which
`OI-121` already stated as *"Closes with `OI-115`: the chain's handlers as a LIST in walk order,
the first after a link its reader and each later one the previous one's consumer."* Two numbers
for one edit made it look like two pieces of work and invited half of it. **Closes** with that
one change: both slots folded as lists in walk order, the wire branch reading `_READS_LINK` for
`fed_by`, and the handler column taking the FIRST handler after a link.

### OI-116 — `read_by`/`sends_to` edges are written once per vararg destination
**Minor · logged 2026-09-21, found at the Task 4–5 review · `src/sextant/application/resolve/engines/fluent.py::_derive`**

`_derive` loops over the destinations a varargs capture yields (one row per element, spec §3c)
and writes the chain's channel edges inside that loop, so `Amqp.inboundAdapter(cf, "q1",
"q2")` … `.channel("x").handle(h)` writes `read_by(x, h)` twice. The mint pass keys readers per
channel and the `call_endpoints` guard dedupes rows, so no row doubles; the table carries the
duplicate edges.

**What happens today:** the two-queue fixture flow writes its `fed_by` per queue (correct — each
queue feeds the channel) and its reader edge per queue (redundant); one row per queue derives.

**Real triggering input:** every varargs registration that also links a channel — the duplicate
is invisible in the export.

**Verify:** `grep -n "for peer, path, url_resolution in destinations" src/sextant/application/resolve/engines/fluent.py`
— the edge appends sit inside that loop.
**Closes** by writing the reader-side edges once, outside the per-destination loop.

### OI-117 — the container hop re-walks the bean's chain per reference
**Minor · logged 2026-09-21, found at the Task 4–5 review (§8.7) · `src/sextant/application/resolve/engines/fluent.py::_bean_chain_capture`**

Every `bean_via` reference to one container bean walks that bean's method's sites again — no
memo keyed on `(bean method, field)`. Per resolve, per adapter referencing it: a module with N
adapters on one container walks it N times.

**What happens today:** the fixture has one adapter per container; the cost is one walk.

**Real triggering input:** a module wiring many adapters to one shared container — the walk is
linear in the container method's sites, so this is a constant-factor cost, not a regression.

**Verify:** `grep -n "once\|memo\|cache" src/sextant/application/resolve/engines/fluent.py` around
`_bean_chain_capture` — none. **Closes** with a per-run dict on `_ChainContext` keyed on the bean
method and field.

### OI-118 — `_REQUIREMENT_KINDS` is spelled in two engines
**Minor · logged 2026-09-21, found at the Task 8 review · `src/sextant/application/resolve/engines/combinator.py::_REQUIREMENT_KINDS`, `src/sextant/application/resolve/engines/config_join.py::_REQUIREMENT_KINDS`**

The closed set `("header", "query", "cookie", "param")` that `endpoint_metadata.kind` admits for
an inbound requirement is declared once in the combinator (for `request_requirement` rules) and
once in `config_join` (for the `indexed:` form's `requirements`), both private; the second was
written rather than imported to avoid a cross-engine import of a private name. Two copies that
drift would let one engine write a kind the reader does not know.

**What happens today:** both tuples are identical.

**Real triggering input:** none — a drift is a future edit.

**Verify:** `grep -rn "_REQUIREMENT_KINDS = " src/sextant/application/resolve/engines/` — two.
**Closes** by moving the tuple to `resolve/request_requirements.py` (the pass that reads the
stash) and importing it in both engines.

### OI-119 — the descriptor gate reads `matches.methods` only, so a `fluent` catalog's `roots:`/`steps:`/`beans:` descriptors are outside it entirely (merged with `OI-129`)
**Minor · logged 2026-09-21, found at the Task 6 self-review · `tests/architecture/test_catalog_descriptors.py`, `scripts/probes/cp10_catalog_descriptors.md`**

CP-10's ratchet reads `matches.methods` rows only. The three broker catalogs and the step model
declare some seventy `descriptor:` strings on `roots:`, `steps:` and `beans:` entries — the
ten `messageDrivenChannelAdapter` overloads, the fifteen `handle` forms — checked against
CP-27/CP-28's tables by eye and by the positive halves of `tests/application/test_spring_integration_adapters.py`
(a wrong descriptor matches nothing and the positive would fail), never by a test that reads the
probe table. A descriptor edited after the fact fails only if a fixture happens to exercise it.

**What happens today:** every declared descriptor was copied from a probe row and the positives
pass.

**Real triggering input:** a future edit — a version bump that changes a return type in a
descriptor.

**Verify:** `grep -n '"methods"' scripts/probes/cp10_catalog_descriptors/descriptors.py
tests/architecture/test_catalog_descriptors.py` — one key, read twice. **Closes** by extending
the harness AND the architecture test to `roots`, `steps` and `beans` (and the step-model
files), the same two-direction agreement over more rows.

#### The wider statement, filed separately as `OI-129` and merged here 2026-10-18

Both halves of the two-direction agreement read the same one key:

```python
for method in matches.get("methods") or []:
```

So the descriptors are not merely UNPINNED, they are **outside the gate**: in
`vertx-eventbus-chain.yml` alone that is **seven erased descriptors** (four roots, three
steps), and the three Spring Integration broker catalogs plus the step model carry some
seventy more. It is **pre-existing** — Group D (2026-09-22) is where somebody read the loop,
not where it started.

**WHY THE TWO ARE ONE ITEM.** `OI-129`'s own text said it: *"`OI-119` logs the missing
mechanical PIN between those descriptors and the probe tables; this is the wider statement of
the same absence"*, and its closing line was *"Closes with `OI-119`"*. One edit, two numbers,
and the narrower of the two understated the problem — which is the real cost of a duplicate
here, not the untidiness.

### OI-120 — `setTopicExpression(e)` followed by `setTopic("t")` reads unresolved
**Minor · logged 2026-09-21, ruled at Task 3 (sticky poisons) · `src/sextant/application/resolve/engines/fluent.py` (`_POISONED`, `_fold`), `src/sextant/catalogs/spring-integration-pubsub.yml`, `spring-integration-amqp.yml`**

A catalog `poisons:` is sticky by identity: a later capture does not lift it. That is the
no-false-positive direction for a `divert` (the message may have left the flow) and a miss for a
setter pair — Spring's setters are last-wins, so `setTopicExpression(e); setTopic("t")` publishes
to `t` and the row reads `unresolved`. Stated on both catalogs.

**What happens today:** no fixture writes an expression setter before a literal one.

**Real triggering input:** unusual — a bean configured with an expression and then overridden.

**Verify:** `grep -n "sticky" src/sextant/application/resolve/engines/fluent.py`. **Closes** if
setter-shaped poisons are declared liftable (`poisons: {channel: liftable}`, say) while
divert-shaped ones stay sticky — a catalog word, once a real module needs it.

### OI-121 — `handler` is a last-wins slot · **MERGED INTO `OI-115` (2026-10-18)**
**Minor · logged 2026-09-21 · the body now lives under `OI-115`**

One defect, one function, one fix: `_fold` keeps the last capture, and a chain may fill
`channel_link` twice or `handler` twice. This entry's own closing line already said *"Closes
with `OI-115`"*, so two numbers only made one edit look like two items. The stub stays because
`docs/java-kotlin-delivery-list.md` and the Group E design both cite `OI-121` by name.

### OI-122 — the linking tier's metadata refinement rule is stated twice and built nowhere
**Minor · logged 2026-09-22, found at Group D Task 10 · `docs/components/D02-catalog-schema.md` §2l (line ~4798), spec `docs/superpowers/specs/2026-09-22-temporal-and-eventbus-design.md` §1f, `GAP-2`**

§1f splits a qualifying attribute into **routing** (it changes which endpoint a message arrives at
— a Temporal task queue: a worker on `orders` never sees `orders-staging` work) and
**behavioural** (it changes what happens once the message has arrived — a Kafka `groupId`, a JMS
`selector`). A routing fact enters the PATH only when both sides of the wire can read it; where
only one side can, it is an `endpoint_metadata` entry, and — quoting D02 §2l — *"the linking tier
uses it as a refinement (two rows whose stated values differ do not link; a row that states
nothing links as before)"*. **Nothing implements that sentence**, because the tier it names does
not exist (`GAP-2`, FR-8/M05/M06, phase L, never started). Eight shipped catalogs now write
`task_queue`, `consumer_group`, `selector`, `subscription`, `exclusive` and `local` entries with no
reader at all.

This is filed rather than left to the tier's own design because the rule is not obvious from the
rows: a `task_queue` entry looks exactly like a `consumer_group` entry in the table, and the two
must be used differently — `orders` against `orders-staging` is NOT a wire and must not be linked,
while two consumer groups on one topic ARE both real consumers of it and must both link. A tier
written without this rule links the first pair.

**What happens today:** nothing links anything, so nothing is wrong yet.

**Real triggering input:** the first linking tier — two modules, one declaring
`@WorkflowImpl(taskQueues = "orders")` and the other `@WorkflowImpl(taskQueues = "orders-staging")`
over the same `@WorkflowInterface`, which would be reported as one wire.

**Verify:** `grep -rn "linking tier uses it as a refinement" docs/components/D02-catalog-schema.md`
— the rule; `grep -rn "linking tier" src/` — no implementation. **Closes** with `GAP-2`, by that
tier reading `endpoint_metadata` and distinguishing routing kinds from behavioural ones, which
needs one more column or one declared list: **the kinds are catalog data and nothing today says
which of them is routing.**

### OI-123 — Cadence is excluded by fqn, and nobody has measured whether it is one protocol or two
**Minor · logged 2026-09-22, found at Group D Task 5 · `src/sextant/catalogs/temporal-workflow.yml` (the `CADENCE` boundary bullet), `temporal-activity.yml`, spec §1b**

`temporal-workflow.yml` states it plainly: *"CADENCE (`com.uber.cadence`) gets no rows: every fqn
here is `io.temporal.*`, and folding Cadence under this protocol would let a Cadence worker answer
a Temporal caller (§1b)."* Cadence declares annotations with the **same simple names** —
`@WorkflowInterface`, `@ActivityInterface`, `@WorkflowMethod` — under a different package, and
speaks a different wire to a different cluster. Excluding it by fully-qualified name is the
no-false-link choice and it is the right one; what is unmeasured is the question underneath it.

**The unmeasured question, stated so the next reader does not re-derive it:** is Cadence a second
set of catalogs under a `cadence` protocol member of its own, or the same catalogs widened to a
second `io`/`com.uber` owner pair? Nothing here can answer that from a Temporal jar — it needs a
`com.uber.cadence-client` archive, its own probe (do the annotations declare the same elements? is
there a `namePrefix`? does the default workflow type follow the same rule?) and its own fixture.
**The two must not be the same `Protocol` member either way**, which is the part that IS settled.

**What happens today:** a Cadence module derives **nothing** — no inbound row, no outbound row, no
metadata. It is a total miss, not a partial one, and the catalogs say so.

**Real triggering input:** a module on `com.uber.cadence`. Uber's own fork is in maintenance and
this estate has left it, which is why this is Minor rather than Major.

**Re-measure when** such a module appears, or when a `Protocol` member is added for any other
workflow engine — whichever comes first, the same probe answers both. **Verify:**
`grep -n "CADENCE" src/sextant/catalogs/temporal-workflow.yml`.

### OI-124 — the programmatic Temporal worker derives nothing, and the mechanism that would fix it does not exist
**Minor · logged 2026-09-22, found at Group D Task 5 · `src/sextant/catalogs/temporal-workflow.yml` (the `THE PROGRAMMATIC WORKER` boundary bullet, lines ~207–214), `temporal-activity.yml`, `scripts/probes/cp30_temporal_contract_naming.md` Q8**

**On the grade, because Minor will read as wrong beside the size of the miss.** No row this
produces is incorrect — the module simply has fewer of them, and the alternative was measured and
is worse (an implementation nobody registered, published as a live served endpoint). That is the
definition of a stated boundary rather than a defect, which is why it is graded here the way
`OI-110` and `OI-126` are and why the magnitude is written out below instead of being carried by
the word.

**This is the sharpest boundary Group D shipped, and it costs a whole module rather than an
attribute.** The catalog states it: *"`WorkerFactory.newWorker("orders")` +
`registerWorkflowImplementationTypes(…)` is read by nothing here: CP-30 Q8 confirms the queue a
worker POLLS is named on `WorkerFactory` at argument 0, and this catalog reads the queue only off
the starter annotation. A module that registers its workers programmatically therefore derives no
`task_queue` entry — and, since the flip is keyed on the starter annotation, no INBOUND row for
its own implementations either."*

Both halves matter and the second is the larger. A module that wires its workers in code rather
than through `temporal-spring-boot-starter`:

* records no `task_queue` for anything, and
* records **no inbound row at all** — its `@WorkflowInterface` and `@ActivityInterface` contracts
  are subtracted by the SEI fence (the module implements them) and never flipped to inbound (no
  `@WorkflowImpl`/`@ActivityImpl` on the implementor), so its workflows and activities are neither
  served nor called in the export. Measured on the fixture: `ShippingActivities`, implemented
  in-module by a class carrying no `@ActivityImpl`, derives nothing in either direction.

That is a deliberate under-report chosen over the alternative — publishing an implementation
nobody registered as a live served endpoint — and Task 3's ruling priced it. It is recorded here
because a stated miss of this size is still a miss.

**The mechanism it needs, named rather than hand-waved:** one engine attaching metadata read at a
CALL SITE (`WorkerFactory.newWorker(String)`, a `single_call`- or `fluent`-shaped read) to rows
another engine derived from a DECLARATION (`annotation_driven`'s contract rows), and joining the
two by the implementation types the registration call names. **No such cross-engine attachment
exists.** `endpoint_metadata` is written by `endpoint_attributes.py` from annotation arguments
only; `channel_via` joins within one `single_call` catalog; `bean_via` joins within one `fluent`
walk. Nothing crosses from a call site to an annotation-derived row. The same absence would also
close the inbound half, by making a registration call evidence for the flip the way the starter
annotation is.

**What happens today:** a Spring Boot Temporal module (the fixture's shape, and the common one)
derives everything; a plain-SDK module derives nothing.

**Real triggering input:** ordinary — any Temporal module not on the Spring Boot starter. That is
the criterion that makes this worth logging at all, and it is why the magnitude is stated in words
above rather than left to be inferred from the grade.

**STILL OPEN after the value walk** (Task 13, 2026-10-17), and this entry already said why
before the work started: *"No such cross-engine attachment exists."* The walk answers *what
is this value?* at a position a catalog asks about. It does not attach a value read at a
CALL SITE to a row another engine derived from a DECLARATION, which is the whole of this
issue. `resolve/endpoint_attributes.py` is unchanged and still writes
`endpoint_metadata` from annotation attributes only (`_from_annotation_attributes`,
`effective_annotation_uses`). Spec 2026-09-22's header listed this among the issues it
closes; that claim is withdrawn, and nothing about the capability it would need has changed.

**Verify:** `grep -n "PROGRAMMATIC WORKER" -A 8 src/sextant/catalogs/temporal-workflow.yml`,
and `grep -n "_from_annotation_attributes" -A 20 src/sextant/application/resolve/endpoint_attributes.py`.
**Closes** with the cross-engine attachment above, which is a spec of its own.

### OI-125 — `request(...)` derives no reply shape, because the reply type is the call's RETURN type
**Minor · logged 2026-09-22, found at Group D Task 8 (concern C2) · `src/sextant/catalogs/vertx-eventbus.yml` (the `A REPLY'S SHAPE` boundary bullet), `vertx-eventbus-mutiny.yml`, `src/sextant/application/resolve/engines/single_call.py`**

`response_shape` is NULL on every event-bus row, `orders.lookup` included. The catalog states why:
*"`request(...)`'s reply type is the call's return type, and no `single_call` word reads one."*
Concretely — the core interface's `request` returns `Future<Message<T>>` and the Mutiny facade's
returns `Uni<Message<T>>`; `single_call`'s only response word is **`response_arg`, an argument
POSITION**, and no argument of a `request` call carries the reply type: there is no `Class`
literal and no `ParameterizedTypeReference` to read. Reading argument 1 would publish the
REQUEST's shape as the reply's, which is a wrong row rather than a missing one.

**What happens today:** a request/reply event-bus call publishes its request body's shape and
states no reply shape. The request half is right; the reply half is absent, not wrong.

**Real triggering input:** ordinary — any `bus.request(...)`. It is Minor because the row is
correct as far as it goes and the absence is stated on the catalog and in COVERAGE §5.12.

**This boundary retires deliberately rather than quietly**, which is the part worth recording:
`tests/e2e/test_async_delivered.py::test_every_eventbus_row_is_verbless_and_states_no_reply_shape`
asserts `response_shape is None` over **every** row, so the day an engine word for "the declared
return type" lands, that test FAILS and somebody has to come back to this issue and to the
COVERAGE line rather than leaving both stale.

**Verify:** `grep -n "A REPLY'S SHAPE" -A 2 src/sextant/catalogs/vertx-eventbus.yml`. **Closes**
by a `single_call` word naming the declared return type (and, for it to be useful, an unwrap of
`Future`/`Uni` and `Message` to reach `T`) — an engine change with its own measurement.

### OI-126 — a `MessageConsumer` or `MessageProducer` handed to another method before its terminal derives nothing
**Minor · logged 2026-09-22, found at Group D Task 8 · `src/sextant/catalogs/vertx-eventbus-chain.yml` (the first boundary bullet), `src/sextant/application/resolve/engines/fluent.py`**

The catalog states it: *"`MessageConsumer<T> c = bus.consumer("a"); register(c);` — the chain walk
is per method body (value ids are per method; a cross-body `source` read is a fabrication path),
so the registration inside `register` is not joined to this root and the row is never written."*
Both halves are lost, not one: the root names the address but never reaches a terminal, and the
`handler` call in the other method has no root to attach to, so **no row is written for either**.

`OI-110`'s shape one framework over — there a Spring Integration container built two beans away is
unresolved; here a consumer passed one method along is invisible. The cause is the same and it is
a deliberate one: value ids are per method body, and reading a `source` across bodies is how a
chain walk starts fabricating chains that were never written.

**What happens today:** `fixtures/orders-eventbus` builds its consumers and their handlers in one
body, so every row derives. The cross-method form derives nothing and is not exercised.

**Real triggering input:** a registration helper — `void register(MessageConsumer<?> c)` called
from several places — which is a real idiom in Vert.x verticles, though the one-body form is the
common one.

**STILL OPEN after the value walk** (Task 13, 2026-10-17). Spec 2026-09-22's header named
this as one of the three issues it closes, and it does not. **What was lost here was never a
VALUE; it was the chain's root.** The walk resolves a value to its source across method
boundaries — 77 such crossings in this estate (`OI-136`) — so it could tell you what address
`bus.consumer("a")` named. What no mechanism does is join a `handler` terminal in one body
to a root in another, and `engines/fluent.py` still keys every chain on `context.caller`
(`_fold_bean_captures` answers `bean_across_bodies` for exactly this shape). A value walk
cannot supply a root, so this issue was mis-scoped against that spec rather than left
undone by it.

**Verify:** `grep -n "HANDED TO ANOTHER METHOD" -A 6 src/sextant/catalogs/vertx-eventbus-chain.yml`,
and `grep -n "across_bodies" src/sextant/application/resolve/engines/fluent.py`.
**Closes** with `OI-110`, by whatever cross-method value tracking that issue settles on — one
mechanism answers both, and answering them separately would be two.

### OI-127 — `registerWorkflowImplementationFactory` and the SDK's own start-up validations are reproduced by nothing
**Major · logged 2026-09-22 as Minor, REGRADED at the branch review 2026-09-22 · `src/sextant/catalogs/temporal-workflow.yml` (the `THE SDK'S OWN VALIDATIONS` boundary bullet), `temporal-activity.yml`**

> **Why the regrade.** Severity follows measurement, and the measurement is in this
> entry's own text: the factory arm produces a row of the WRONG DIRECTION — a contract
> the module SERVES read as one it calls — where every other Group D Minor is a miss. A
> wrong-direction row links a caller to a caller and is the false-positive class the
> group's standing requirement forbids; a miss is honest under-reporting. And the arm
> clears the real-input bar: `registerWorkflowImplementationFactory` exists for
> implementations that need constructor injection the SDK cannot do, which is ordinary
> code rather than a module nobody runs. The VALIDATIONS half of this entry stays what it
> was — reproducing them needs a module the SDK would refuse to start — and the grade
> here is set by the factory arm.

The catalog states it: *"THE SDK'S OWN VALIDATIONS are not reproduced — duplicate workflow-type
names, a `@WorkflowInterface` with more than one `@WorkflowMethod`, `DynamicWorkflow`,
`registerWorkflowImplementationFactory` and Nexus services. A module the SDK would refuse to start
still produces rows here."*

`registerWorkflowImplementationFactory` is the one worth naming on its own, because it is not a
validation but a **registration form**: it registers a workflow implementation by FACTORY rather
than by type, so there is no implementation class for the SEI fence or the direction flip to find
even in a Spring Boot module. A contract registered that way therefore reads as an **outbound**
row — a workflow this module calls — when the module actually serves it. That is the one arm of
this bullet that produces a row of the WRONG DIRECTION rather than a missing one, and it is why
this is filed rather than left as prose.

**What happens today:** `fixtures/temporal-probe` uses neither the factory form nor any invalid
declaration, so nothing is measured either way.

**Real triggering input:** uncommon — the factory form exists for workflows whose implementation
needs constructor injection the SDK cannot do itself. The validations proper (duplicate names, two
`@WorkflowMethod`s on one interface) need a module the SDK would refuse to start, which is a
module nobody runs.

**Verify:** `grep -n "SDK'S OWN VALIDATIONS" -A 4 src/sextant/catalogs/temporal-workflow.yml`.
**Closes** for the factory arm by reading `Worker.registerWorkflowImplementationFactory(Class, …)`
as evidence for the flip — the same cross-engine attachment `OI-124` needs, and it should be built
once for both. The validations proper close by a conformance pass that is not this project's job.

### OI-128 — CP-10 files a descriptor two versions both declare under the FIRST version alone
**Minor · logged 2026-09-22, found at Group D Task 8 · `scripts/probes/cp10_catalog_descriptors/descriptors.py` (the candidate loop, lines ~343–351), `scripts/probes/cp10_catalog_descriptors.md`**

Since Task 8 keyed CP-10's jars by `<artifactId>:<version>`, one artifactId can be resolved at two
versions at once — `io.vertx:vertx-core` at 4.5.10 and 5.0.0, which is what spec §3a's
one-file/two-versions rule requires. The candidate loop then does this:

```python
chosen = candidates[0]
for candidate in candidates:
    ...
    if row["descriptor"] in cache[(candidate, owner)].get(str(row["name"]), set()):
        chosen, found = candidate, True
        break
```

It stops at the **first** candidate that declares the descriptor. So a descriptor both releases
declare — which is most of them; CP-31 measured every descriptor the core catalogs read as
byte-identical across 4.5.10 and 5.0.0 — is filed under 4.5.10's column only, and 5.0.0's column
does not show it. The column heading says *"checked against"*, and what the column actually means
is *"the first resolved version that declares it"*. The two readings differ exactly where a
version is resolved twice.

**What happens today:** no descriptor is reported wrong — `NOT declared` is 0 in every column, and
a descriptor NO candidate declares still fails, because `found` stays `False`. What is lost is
COVERAGE: 5.0.0's column under-counts, so a reader cannot tell from the table which of the two
releases a shared descriptor was actually verified against, and a descriptor that 5.0.0 drops
would keep passing on 4.5.10's evidence alone.

**Real triggering input:** a version bump — the next `vertx-core` release that removes a method
the catalog declares. The harness would go on reporting it `declared`, off the older jar.

**Verify:** `grep -n "chosen, found = candidate, True" -B 4
scripts/probes/cp10_catalog_descriptors/descriptors.py`. **Closes** by checking every candidate
rather than breaking at the first, and reporting per candidate — one cell per `(descriptor,
version)` — with the caption corrected to match whichever it ends up meaning.

### OI-129 — the descriptor gate reads `matches.methods` only · **MERGED INTO `OI-119` (2026-10-18)**
**Minor · logged 2026-09-22 · the body now lives under `OI-119`**

The same absence stated twice: `OI-119` filed the missing pin, this entry filed the fact that
the descriptors are outside the gate altogether, and both closed with the same widening of
`catalog_descriptors()` and its architecture test. Folded so the item is costed once.

### OI-130 — `@KafkaListener(value = "a", groupId = "b")` writes two contradicting consumer groups where Micronaut resolves one
**Minor · logged 2026-09-22, found at Group D Task 9 fix round 1 · `src/sextant/catalogs/micronaut-kafka.yml` (the both-written paragraph beside the two `metadata_from` entries), `scripts/probes/cp32_listener_attributes.md` Q12, Q13**

`value()` and `groupId()` are `@AliasFor` **one another** (CP-32 Q4a), and the alias is applied by
Micronaut's annotation-metadata layer, not by javac — so `micronaut-kafka.yml` must carry BOTH
names or miss every `@KafkaListener("orders")`, the ordinary short spelling. Two measurements
then bound the cost:

* **Q12 — javac accepts a declaration that writes both, and writes both.** `AliasProbe$Both`,
  compiled with `-proc:none` so what lands is javac's own output, carries
  `KafkaListener(value="by-value" groupId="by-group-id")` in one `RuntimeVisibleAnnotations` entry
  with both elements intact.
* **Q13 — Micronaut does not refuse such a declaration; it overwrites.** In
  `AbstractAnnotationMetadataBuilder.processAnnotationAlias` (micronaut-core-processor 4.7.6), a
  WITHIN-annotation alias — which `value`↔`groupId` is — reaches offsets 164–195, and that whole
  branch is a `Map.put(aliasedMemberName, value)` into the same members map. A `put` overwrites;
  nothing compares, warns or refuses.

So such a declaration resolves to exactly ONE group at runtime, and we write **two contradicting
`consumer_group` rows** on one endpoint. Pinned as behaviour by
`test_micronaut_kafka_writes_both_groups_where_one_declaration_names_two`, so a later rule changes
it visibly.

**What happens today:** bounded. It needs a module that already contradicts itself, and both
elements written with the SAME value yield one row through the insert-if-absent guard. **Dropping
the `value` entry would not be safer** — it would turn a bounded self-contradictory case into a
silent miss on the common spelling.

**Real triggering input:** rare — a `@KafkaListener` naming two different groups under the two
alias names, which a developer writes by accident and Micronaut then silently collapses.

**What closes it is a MEASUREMENT, and naming it is the point of this entry.** The missing fact is
**which of the two the `put` lands on** — that is, the order in which Micronaut's metadata builder
processes an annotation's elements, and whether that order is the class file's element order, a
sorted order, or the alias declaration's. One probe question against
`AbstractAnnotationMetadataBuilder` answers it, and the answer is a rule
`metadata_from` could then encode.

**A first-present-wins rule invented here would be wrong even if it happened to be right.** DR-6
is the standing rule — *predict the framework's error handling exactly, never our own* — and
picking a winner because it is the first entry in our list is our tie-break, not Micronaut's. The
framework's behaviour is knowable from its own bytecode, so guessing at it is the one thing not
allowed.

**Three options, and the measurement still decides between them** — added at the branch review,
because this entry had argued against one option without recording that it has a precedent here
and without recording the third option at all:

1. **Write both rows** (what ships). Over-reports on a self-contradictory declaration; never
   misses the ordinary short spelling.
2. **First-present-wins.** This entry called that machinery "`path_from`'s, one key over" as
   though it were foreign. It is not foreign, it is this engine's OWN PRECEDENT — and it is
   declared two lines below the `metadata_from` block **in this same catalog** — the key
   at line 112, its two entries ending at 116, `path_from` at 118:
   `path_from: [value, patterns]`, first present wins. So adopting it here would be reusing a
   rule the file already applies to the address, not inventing one. DR-6's objection still
   stands and is unchanged: the rule would pick a winner by OUR list order rather than by the
   order Micronaut's metadata builder puts the elements in.
3. **Write NO row for that endpoint's group.** Neither of the two, on the grounds that the
   standing requirement says *every ambiguity is an unresolved column or an absent row, never a
   guess* — and two aliased entries disagreeing on one endpoint is exactly an ambiguity. Neither
   the catalog nor this entry had considered it. It costs the group on a declaration that has
   one, which is why it is not obviously right either.

**The shipped behaviour does not change on this entry.** What closes it is still the
measurement named above — WHICH of the two the `put` lands on — and that answer picks among the
three rather than being one of them.

**Verify:** `grep -n "both" src/sextant/catalogs/micronaut-kafka.yml`, the `path_from` line
two lines below the `metadata_from` block in the same file (line 118 against 112-116),
and CP-32 Q12/Q13.

### OI-131 — `uniqueGroupId = true` makes the recorded consumer group a PREFIX of the one joined
**Minor · logged 2026-09-22 at the Group D branch review · `src/sextant/catalogs/micronaut-kafka.yml`
(the `STATED BOUNDARY` paragraph above `metadata_from`), `docs/COVERAGE.md` §5.8**

`@KafkaListener` declares `uniqueGroupId(): boolean`, default `false`. CP-32 Q9 (offsets
146-167, micronaut-kafka 5.6.0) reads the processor composing `<declared>-<random UUID>`
when it is `true`, and joining `<declared>` when it is not. We record the declared value
either way, so under `uniqueGroupId = true` the `consumer_group` row states a **prefix** of
the group the consumer is actually in.

**Filed rather than left as prose, and that is the whole point of this entry.** Two
documents already say it — the catalog paragraph and COVERAGE §5.8 — and neither is the
register. `OI-130` files the both-written alias case from the same annotation, the same
probe and the same review; this is the same class of defect (a `consumer_group` value that
is not the group) and was the only one of the two living in prose alone.

**What happens today:** a peer reading the row looks for a group nobody is in. The
direction is not the dangerous one — linking gates on the value, so a prefix under-links
rather than mis-links, and the declared value is still the name a human would search for —
but it is a value stated as the group when it is not the group.

**Real triggering input:** ordinary, unlike `OI-130`'s. `uniqueGroupId = true` is the
supported way to make every instance of a service its own consumer group, which is what a
broadcast-to-all-replicas listener needs; a repository using it is not contradicting
itself.

**Why it is not encoded:** `metadata_from` has no conditional form — an entry names one
annotation, one attribute and one `kind`, and cannot read a SECOND attribute to decide what
to do with the first. Nor could it spell the value: the suffix is a UUID minted at startup.

**Closes** either by a `metadata_from` entry that may be gated on a sibling attribute — the
`annotation_driven` conditional machinery B/C already built for `wrappers[].when`, one key
over — recording the group at `unresolved` where the gate fires, or by recording
`uniqueGroupId` as a `kind` of its own beside the group so a reader sees both facts. Both
are catalog-shaped; neither is written.

**Verify:** `grep -n "uniqueGroupId" src/sextant/catalogs/micronaut-kafka.yml docs/COVERAGE.md`
and CP-32 Q9.

## CLOSED

### OI-132 — `request_requirements` wrote its `endpoint_metadata` values UNREDACTED into the export
**Major · found and CLOSED 2026-09-22 by the Group D branch re-review ·
`src/sextant/application/resolve/request_requirements.py`,
`src/sextant/storage/duckdb/insert_endpoint_metadata.sql`,
`src/sextant/storage/duckdb/workspace.py` (the export map's `endpoint_metadata` entry)**

`_entry` wrote `"value": value` verbatim, with no redactor anywhere in the module. Three
documents state the opposite invariant — `schema.sql`'s `value` column ("redacted at the
ORIGIN, never at export"), `insert_endpoint_metadata.sql`'s header ("already redacted by
the pass that read it"), and `workspace.py`'s export map, which exports the table **whole
and unmasked on exactly that stated ground**.

**Reproduced on the shipped test, not argued from the code.** Running
`tests/application/test_request_requirements.py`'s mapping-attribute case with
`headers=["X-Api-Key=s3cret-literal"]`:

```
('GET', '/orders', …, 'header', 'X-Api-Key', 's3cret-literal', 'required', 'resolved')
```

`spring-mvc.yml:140` and `spring-web.yml:136` both declare
`request_requirement_attrs: {params: param, headers: header}`, so
`@GetMapping(headers = "X-Api-Key=…")` is ORDINARY Spring input — this is not a shape a
repository has to contrive. The row reached `graph/*.parquet` in the clear, and the bundle
is the trust boundary.

**Cost while it stood:** every literal a route predicate carried left in the clear in every
exported bundle. Bounded only by how often a credential is written into a routing
predicate, which is a real if uncommon way to gate an internal endpoint.

**Pre-existing**, not introduced by Group D — this branch found it, because the sibling
fix at the other origin (`endpoint_attributes`, same commit group) shipped a comment
claiming it was the last one. That claim is corrected in place rather than deleted: a
wrong rationale is what stops the next reader looking.

**Closed** by the same rule the other two origins apply: `Redactor.from_rules()` in
`_entry`, which every one of the four mechanisms funnels through. It is the name/value pair
`redaction.py`'s `redact_json` docstring calls *how a credential actually reaches this
grammar*, and here there is a real header or parameter NAME to key on, so `redact_value`
does the work directly. A value whose name could not be read — the combinator reads both
literals off a call argument and writes `name` NULL where the name was not one — is masked
WHOLE, `engines/fluent.py`'s rule for `fluent`'s own reason.

**No existing assertion moved**, which was the stop condition: the whole suite is green at
3979 passed, 8 skipped, 4 xfailed, and the two new tests both fail — and only those two —
with the redaction removed. Nothing reads `endpoint_metadata.value` downstream, so no
derived row could move: the table's only consumer is the export map.

**And the cause is removed, not only the instance.** The invariant was stated in three
documents and tied to no writer, which is how two of the three origins came to violate it.
`tests/architecture/test_source_rules.py::test_every_origin_writing_endpoint_metadata_holds_a_redactor`
now requires a module reaching `endpoint_metadata_insert` to build a `Redactor`, so a
fourth origin cannot be written without meeting it.

**Verify:** `grep -rn "endpoint_metadata_insert" src/sextant | grep -v workspace.py` names
the three origins; each holds a `Redactor`.

### OI-133 — a VOID ordinary method is read as a construction, so an identity entry naming one would answer what the receiver is
**Major · found and LOGGED 2026-09-23 by the Task 7 round-2 review ·
`src/sextant/application/resolve/values.py` (`_Walk._construction`)**

The backward value walk resolves a produced value through §2's `identified_by` table. A
CONSTRUCTED value has no `produced_by` edge — `call_sites.result` is null for an initialiser
— so `_construction` finds the site another way: the value has no producer edge, the site is
the earliest one the value is the receiver of, and **that site produced no value of its own**.

The third conjunct is what stopped the fabrication the same review round found
(`session.createProducer(session.createQueue("raw-audit"))` reading `createQueue` as the
SESSION's construction, and answering `raw-audit` as what the session is — closed, and
pinned by `values.a-construction-hands-nothing-back`). **But "produced no value of its own"
is narrower than "is an initialiser".** A void ORDINARY method also produces nothing, so a
field- or parameter-held value whose first call happens to return nothing is read here as
having been constructed by that call.

**MEASURED, over all 27 corpora**: of the **3,283** values this rule names as constructed,
**395 are not initialisers**. By callee name: `clear` 159, `debug` 65, `info` 22, `remove`
11, `error` 10, `warn` 9, `delete` 9, `persist` 7, `save` 7, `convertAndSend` 5, `increment`
4, `deleteById` 4, `set` 4, and a tail.

**Demonstrated, not argued**, on `examples/mall/mall-portal`'s
`CancelOrderSender#sendMessage`, whose ordinal 4 is `LOGGER.info("send orderId:{}", orderId)`
— void, receiver value id 17, a field-held logger:

```
the void call: org/slf4j/Logger#info  result=None  receiver=17  arg0={'kind': 'string', 'value': 'send orderId:{}'}
`_construction` says the logger was CONSTRUCTED at ordinal 4
one synthetic identity entry, exactly a hoisted `channel_via` shape:
    {'owner': 'org/slf4j/Logger#', 'method': 'info', 'arg': 0}
asking what the LOGGER is  ->  kind=literal literal_kind=string value='send orderId:{}'
```

A log format string answered as the identity of a logger, at `resolved`, where nothing
downstream can tell it from an observation. That is `raw-audit`-as-the-Session one shape
along, and the existing guard does not notice it.

**Real triggering input: none today, and the reason is on the CATALOG side rather than in
the rule.** Checked exhaustively — all **fourteen** shipped non-`<init>` `identified_by`
entries, against every site each matches in every corpus. **Eight match at least one site,
and every one of the eight has a non-null result at every site it matches**: `URI.create`
(14 sites), `List.of` (23), `ProjectSubscriptionName.of` (3), `Session.createQueue` (2),
`Arrays.asList` (2), `Pattern.compile` (2), `Subscriptions.topics` (2), `TopicName.of` (1).
**The other six match no site in any corpus**, so nothing about them is measured here and
nothing can be: `Session.createTopic` and both `javax.jms` siblings,
`Collections.singletonList`, `Subscriptions.topicPattern`, and
`MessageConsumerOptions.setAddress` — the one that names a SETTER, and the shape this issue
is about. That it matches nothing is what makes the conclusion hold today; it is not a
property anyone chose. The synthetic entry above is the only way to reach the gap now.

**MEASURED both ways, so the exposure is sized rather than asserted:** replacing the rule
with one that accepts only an initialiser changes **0 of 98,454** ceiling positions across
all 27 corpora. Neither an identity answer nor the `escapes` window (whose start moved to the
construction in the same change) moves for any of the 395.

**LOGGED rather than fixed**, by this repository's own criterion — the test is whether real
input triggers it, and no shipped catalog entry does. **What reopens it** is the next
`channel_via` or `url_via` hoisted onto a producer that hands nothing back: a void sender
(`convertAndSend` is already in the 395) or a void setter is exactly the shape a messaging
catalog would write. Three places now state what the conjunct really excludes rather than
implying it settles the question: `_construction`'s docstring, the guard's `why`, and D02
§1f, which warns a catalog author to check that the producer an entry names hands something
back.

**Closes** by giving the walk a fact that says a site is an initialiser rather than inferring
it. The candidates, in preference order: a `construct` invoke kind or an `initialiser` flag
on `call_sites` (a scanner capability, the D00 9.19 pattern — the JVM backend already knows,
since `MethodInsnNode.INVOKESPECIAL` on `<init>` is what it reads); or, failing a fact, the
identity entry's own declared `method` deciding, which works because an entry naming an
initialiser spells it and one naming a void setter does not — but that makes the rule depend
on a catalog spelling rather than on the facts, which is the coupling §5a exists to avoid.

**Verify:** the demonstration above, and
`grep -n "A VOID ORDINARY METHOD is not excluded" src/sextant/application/resolve/values.py`.

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

**Amended 2026-10-22 (Group H): `trace_of` is no longer the only named query with a reader.**
Six module-scope questions — `source`, `callers`, `callees`, `implementations`, `uses`,
`impact` — are answered from the workspace through `sextant.api.query`, in process, with no
command-line form (D01 §5; M09). The statement above that "no public API verb was added"
was true on 2026-09-06 and is not now: `query` is a public verb, ruled in on 2026-10-22 as a
partial reopening of the language gate for that function alone.

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
`docs/open-issues.md` OI-84:122` is the OkHttp
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
`open-issues.md` OI-83, not in `COVERAGE.md`.

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
| `permits` | 0 |
| `modifiers.abstract`, `varargs`, `final`, `native`, `synchronized`, `volatile`, `deprecated` | 0 |
| `signature.throws` | 1 — the module document's `Fails with:` line, `G-74`, **closed 2026-09-12** |

Eleven of the twelve remain at zero. `signature.throws` closed by
`egress/render/document.py`'s `_fails_with_entry`, pairing the DECLARED clause with the
OBSERVED throw-exit call sites `G-52` gave the call graph — `reachable_throws`
(`storage/duckdb/workspace.py`) joins `reachability` to `call_sites` at the composition
root, and `egress/render/document.py` renders the answer. Proved by
`tests/egress/test_render.py`'s `test_a_handlers_declared_exception_renders_as_fails_with`,
`test_a_reachable_throw_exit_joins_the_same_line_after_the_declared_half`,
`test_a_throw_site_whose_target_was_unread_says_so_in_words` and
`test_no_fails_with_line_where_neither_half_has_anything`.

Every apparent hit among the remaining eleven is prose in a docstring or a SQL comment. The
only other W7 output with a live consumer is `construct_kind: annotation`, through
`interface_symbols`.

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
reports `visibility: package` (`G-73` gave the class-file word its other three
values; the class file itself still writes a private nested type
package-private, so the word this reports did not change) and no `private`
modifier — the same as a package-private one. Nothing downstream distinguishes
them today, which is why this is Minor rather than Major.

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
refused either way; the cost is what a reader holding the shipped catalogs is told.

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
consumer. Every shipped catalog declares one. GUIDELINES §2 — a capability with no consumer is
half-shipped — applies to catalog keys as much as to scanner capabilities, and W17's own
finding was a reader predicting behaviour from an unread key.

**Consequence:** none to output. The cost is to readers: a name that looks like it
reaches an export does not, so it can drift arbitrarily far from what the catalog derives
without any gate noticing. `spring-mvc.yml`'s said "server-rendered controllers" while
deriving reactive WebFlux routes.

**Closes by** either giving it a consumer (the rendered document names catalogs by id
today) or removing it from all 64 catalog files and from D02. **Falsified by** finding a consumer
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

### OI-68 — analysing a reactor module costs 14× what it did · **MOVED to `docs/performance.md` P-1 (2026-09-12)**

Not a defect in output — the same rows derive, slower. The measurement, every refuted lever,
the profile to the query and the agreed fix shape (root side filtered in SQL at the first read,
lookup side open, one read per fact table per resolve) live in
[`performance.md`](performance.md) §P-1, which is worked after the delivery register is empty.

### OI-69 — Gradle modules cross no module edge · **SCHEDULED as W55 (Wave 12)**

**Found by** the W24 review.

`MavenDetector` resolves reactor siblings that this module declares as dependencies;
`GradleDetector` does not, so `ModuleModel.sibling_roots` is empty for every Gradle build
and the empty-envelope defect F4 §5.2 describes remains for all of them. The plan row for
W24 names "Gradle settings" as existing sibling detection, so this is a descope of half
the item's reach rather than a shape nobody considered.

**Consequence:** a Gradle multi-project build gets exactly today's behaviour — a response
shape with no fields wherever the type is compiled in another subproject. No output is
wrong; it is the absence W24 exists to remove, still present.

**And there is no manual route to it**, which is what turned this from a deferral into a
scheduled item. `extract_libraries` cannot name a sibling project: `gradle.py`'s
`_library_roots` keys its lookup on classpath entries carrying both `group` and `name`,
and an inter-project dependency has neither. The coordinate misses, pinning a version does
not help, and the user is told the compile classpath does not resolve the dependency.
Reaching the module edge on Gradle today means publishing the subproject to a local
repository and depending on it by coordinate — changing the build, not using the tool.

Scheduled as **W55** in the plan's Wave 12, to run after v1's waves.

**Closes by** reading what the detector is ALREADY given, and it is materially easier
than the Maven side was. `sextant-model.init.gradle` asks each project for its
`compileClasspath` and records every entry's resolved artifact PATH; an inter-project
dependency arrives as a `ProjectComponentIdentifier` and is marked `internal: true`
(`gradle.py:505-521` already reads that flag, to keep such entries out of the gap list).
So Gradle hands over the sibling set, resolved, with paths — no `<modules>` walk, no
parent-POM resolution, no transitive closure to compute by hand, all of which the Maven
implementation had to do. What is missing is turning those `internal` entries into
`LibraryRoot`s and naming them in `sibling_coordinates`.

The one thing Gradle does NOT hand over is a coordinate for such an entry — a
`ProjectComponentIdentifier` carries a project path (`:mall-common`), not
`group:artifact:version` — so `sibling_coordinates` needs a spelling that is stable and
distinguishable, and `origin` must not become a path (D00 §2).

**Falsified by** measuring that Gradle multi-project builds put their shared types on the
compile classpath in a form the existing `extract_libraries` path already reaches.

### OI-70 — the workspace migrates ADDED columns and nothing else

**Found by** the W26 review, after a stale `.sextant/workspace.duckdb` crashed 65 tests
with `Binder Error: Table "shapes" does not have a column with name "origin_tier"`.

`schema.sql` is all `CREATE TABLE IF NOT EXISTS`, so it does nothing to a table that
already exists. W26 added a migration that opens a workspace, compares its columns against
DuckDB's own parse of the current `schema.sql`, and `ALTER TABLE ... ADD COLUMN`s whatever
is missing. That covers the case that has actually occurred — every schema change so far
has added columns — and it is safe because every table but `raw_facts` is rebuilt from the
facts on each `analyze`.

**What it does not cover**, in the order it would bite:

1. **A column whose TYPE changed.** The old column stays, the new statement writing it may
   or may not fail, and if the types are assignment-compatible it silently keeps whichever
   representation the old workspace used.
2. **A column the schema no longer declares.** Left in place deliberately — deleting data
   to satisfy a shape is the destructive direction — but a `SELECT *` reader sees a column
   the schema does not describe.
3. **A table renamed or split.** The old table survives with its rows, and
   `schema_objects()` reports it, so the export ratchet sees an object with no query.

**Consequence today: none observed.** No shipped change has done any of the three, which
is exactly why the additive rule is enough and why this is recorded rather than built.

**Closes by** stamping the workspace with a fingerprint of `schema.sql` and, where it
differs in any way the additive rule cannot express, refusing with a sentence that says
what to do — re-run `sextant module analyze` — rather than by guessing at a migration. The
workspace is a derived cache: rebuilding it is always correct and always available, so the
honest failure is cheap. `_add_columns_the_schema_has_gained` already computes the expected
shape from DuckDB's own parse, so the comparison it would need exists.

**Falsified by** a schema change that removes or retypes a column, which would make this a
live defect rather than a stated limit.

**It runs on EVERY workspace open, not only when a migration is needed** (W26 review): a
throwaway in-memory DuckDB, a full `schema.sql` parse and two `information_schema` queries,
per `DuckDbWorkspace(...)`. Cheap and unconditional. A cheap guard would be to compare a
hash of `schema.sql` against one stored in the workspace and skip the whole thing when they
agree, which is the shape the eventual versioned migration wants anyway — recorded here
rather than done, because the cost is small and the guard is only worth writing once, with
the mechanism that replaces this.

### OI-71 — a module's own `redact:` additions do not widen metadata masking

**Found by** building W29 (F5 §6.2).

`endpoint_metadata.value` is redacted at the ORIGIN — where the value is read, in
`resolve/engines/fluent._metadata_row` — because nothing in this system consumes a
metadata value, so the masked string is the only one ever written down. That much works:
the fixture's compiled-in `Authorization: Bearer sk-live-fixture-secret` reaches the table
as `«redacted»`.

**It masks by the BUILT-IN rule set only.** A module's `.sextant.yml` `redact.key_patterns`
additions reach the export's redactor through the composition root (`api.py::_redactor_for`),
and no redactor reaches a resolve engine at all — `resolve()` takes none, and the engine
protocol is `Callable[[Workspace, Catalog], None]` for all thirteen engines.

**Consequence:** a repository that adds a pattern of its own for a header name gets no
masking from it. The built-ins already cover the credential names —`authorization`,
`token`, `secret`, `apikey`, `credential`, `password`, `passphrase`, `privatekey` — which
the design calls "exactly this table's shape", so the gap is narrow. It is still an
under-mask, which is the dangerous direction.

**Closes by** threading the redactor from the composition root into `resolve` and on to
the engines. That widens all thirteen engine signatures for one engine's need, which is
why it was not done inside W29; the alternative is an engine-context object, which is a
larger change to a seam nothing else is asking to change.

**Falsified by** a repository whose `redact:` section names a header rather than a config
key — at which point the under-mask is live rather than theoretical.

### OI-72 — `payload_ctor_arg: last` reads a Kafka record's HEADERS as its payload

**Found by** W29's measurement of `ProducerRecord`'s constructor family.

`spring-kafka-template.yml` declares
`{ type: org.apache.kafka.clients.producer.ProducerRecord, channel_ctor_arg: 0,
payload_ctor_arg: last }`, and `last` means the constructor's own final argument
(`single_call._record_arguments`). Read from kafka-clients' own bytecode, that type has
**five public constructors**:

| Constructor | Value index | `last` |
|---|---|---|
| `(String, K, V)` | 2 | ✅ 2 |
| `(String, Integer, K, V)` | 3 | ✅ 3 |
| `(String, Integer, Long, K, V)` | 4 | ✅ 4 |
| `(String, Integer, K, V, Iterable<Header>)` | 3 | ❌ 4 — the headers |
| `(String, Integer, Long, K, V, Iterable<Header>)` | 4 | ❌ 5 — the headers |

**Consequence:** a producer that attaches record headers — ordinary Kafka — has its
`Iterable<Header>` published as the request payload TYPE. That is a fabricated contract,
not a missing one, and DR-5 gates linking on payload compatibility, so it reaches other
services' graphs.

**No live instance.** The fixture uses only the 2- and 3-argument forms, and no corpus
here has a Kafka producer at all. It is reachable by ordinary code, which is why it is
recorded at this severity rather than as a curiosity.

**Arity cannot fix it, and that is the interesting part:** `(String, Integer, K, V,
Iterable<Header>)` and `(String, Integer, Long, K, V)` are BOTH arity 5 with the value at
different indices. Only the erased descriptor separates them.

**Closes by** letting a `record_wrappers` entry declare its positions per DESCRIPTOR, the
same discipline the `methods` rows already keep — "each row declares its own erased JVM
descriptor, so each overload reaches its own row" (`spring-kafka-template.yml`'s own note,
descriptor sweep R3). The engine reads the linked `<init>` call site, which carries its
descriptor, so the join exists.

**Falsified by** measuring that `last` is correct for every constructor a real corpus uses
— which would make this a latent rather than an actual over-report, not a non-issue.

### OI-73 — a WebClient URL built in a `uri(Function)` lambda is never read · **CLOSED, W29**

**Found by** W29's query-parameter measurement, and **it is pre-existing** — the fixture
has carried the case since the fluent engine shipped, with a comment stating it.

`webClient.get().uri(b -> b.path("/v2/inventory/search").queryParam("q", term).build())`
derives an endpoint row with `path` NULL and `resolution: unresolved`. Nothing false is
published: the call is recorded and its address is honestly unread. What is lost is the
address itself, and with it every query parameter.

**Why it is not a smaller gap than it looks.** The address IS the row's identity. A
pathless outbound row cannot link (DR-5 matches on the wire contract) and tells a reader
only "this method calls out over HTTP". And `uri(Function)` is the idiomatic way to add a
query parameter in WebClient — a service that uses them loses those addresses, not just
their parameters.

**Measured frequency: zero.** All three `uri(...)` calls across the six repositories in
`examples/` pass a string literal; none passes a lambda. That bounds what can be claimed
about how often it bites, not whether it is real.

**Why it is unread, and why the current answer is the honest one.** Chain reconstruction
is within-method (D00 §5) and a lambda body is its own synthetic method, so the builder
chain is not the client chain — the two are joined by the lambda being an ARGUMENT, not by
a receiver link the walk follows. The engine follows one hop from a captured argument and
stops rather than reaching into the body for a literal it cannot attribute.

**Closes by** following the `lambda`-kind argument to its synthetic method and walking the
builder chain there as a chain of its own, folding its `path`/`queryParam` captures back
into the calling chain. `resolve/engines/fluent.py` already reaches one hop into a lambda
for a different capture (`lambda$reserveAfterLevels$0` derives a row of its own today), so
the fact stream supports it; what is missing is folding the inner chain's captures OUT to
the caller rather than deriving a second row.

**Falsified by** measuring that a corpus's WebClient calls resolve their addresses without
this — which would mean the lambda form is rarer in practice than its idiomatic status
suggests.

**CLOSED in W29, the same session that opened it.** It was first recorded and deferred,
which was wrong twice over: the fixture derives two such rows, so it had live instances in
our own output and was Major by the standing rule, and the rule says a Major is fixed the
moment it is identified rather than filed.

`resolve/engines/fluent._fold_lambda_captures` follows a `lambda`-kind captured argument to
the synthetic method it names, walks that method's own call sites as a chain of its own,
and folds back what the catalog declared steps for. `spring-webclient.yml` now declares
`UriBuilder.path` and `UriBuilder.queryParam`, owner-gated because both names are generic.
Measured on the fixture: `InventoryWebClient#search` went from `path` NULL to
`/v2/inventory/search`, and its `q` parameter is recorded present-and-unresolved;
`#lookup` records `region = eu` resolved beside `sku` unresolved.

Chain reconstruction stays within-method (D00 §5): the lambda body is walked as its own
chain and only its captures return, one hop, never spliced.

### OI-74 — a `single_call` destination built inside a lambda argument is never read · **CLOSED, W57**

**Found by** closing `OI-73`, by asking whether that defect class had siblings.

`sqsTemplate.send(to -> to.queue("shipments-lambda").payload(event))` derives an outbound
SQS row with **no destination** — `path` NULL, `resolution: unresolved`. The queue name is
a string literal in the lambda's own synthetic method, and the fact stream records it
there, keyed by the symbol the `lambda`-kind argument names.

**It is the same defect as `OI-73`, in a different engine.** That one was in `fluent` and
cost a WebClient call its whole URL; this is in `single_call` and costs an SQS send its
whole queue. Both were written down as deliberate — the fixture's own comment here says
"an honest unresolved row, not a fabricated `shipments-lambda` path" — and the framing is
the same mistake: the lambda is ONE argument of ONE call, the fact stream names the method
it compiled to, and reading that method's call sites is reading rather than guessing.

**Live instance:** one, in this repository's own fixture output, on every run.
`EventProducers#sendShipmentViaBuilder`.

**Consequence:** the address IS the row's identity. DR-5 matches on the wire contract, so a
destination-less outbound row links to nothing and tells a reader only that this method
sends to SQS. `SqsTemplate.send(Consumer<SqsSendOptions>)` is the SDK's own fluent
overload, not an exotic shape.

**CLOSED by W57**, by the mechanism `OI-73` built one engine over, and the detail this entry
warned about did cost a cycle in the writing: the lookup is by bare descriptor, because
`call_sites.caller` carries module coordinates a call argument's `symbol` does not.

`single_call` reads declared POSITIONS off named methods rather than walking a chain, so the
vocabulary mirrors that rather than `fluent`'s: `lambda_arg` names the argument that IS the
builder lambda, and `lambda_steps` names the builder methods called inside it with the
positions each carries. One hop, no chain linking, and a lambda inside a lambda is not
followed.

**Measured on the fixture, before and after.** `EventProducers#sendShipmentViaBuilder`:
`path` NULL → `shipments-lambda`, `resolution` unresolved → resolved, `peer` NULL throughout
because a channel is peerless by construction. The PAYLOAD came back with it — `lambda_steps`
names `payload(arg0)` beside `queue(arg0)` — so the row gained its request shape as well as
its address, and moved from the format ladder's unanswerable rung to `narrowed`. No
destination-less SQS row survives anywhere in the fixture, which is the defect's own measure.

**What made it declarable at all was already there.** The catalog's comment said the two
arity-1 overloads were "indistinguishable by name+arity alone", so it declared no position
for either — and that stopped being true when descriptors arrived: `_matching_method` claims
an arity once any candidate row declares a descriptor, and the destination-less `send(T)` is
`(Ljava/lang/Object;)` where the builder form is `(Ljava/util/function/Consumer;)`. The
reason for the silence had expired and nothing re-asked the question.

**The conjunct that keeps this reading rather than guessing is the STEP NAME**, measured by
`single_call.lambda-step-is-the-declared-method` and, since W57's own review, by
`single_call.lambda-step-owner-is-the-declared-type` beside it. `SqsSendOptions` declares
**seven** methods and **four** take a `String` at a top-level parameter position — `queue`,
`header`, `messageGroupId`, `messageDeduplicationId`, measured at spring-cloud-aws-sqs 3.1.1
and 4.1.1 in `scripts/probes/w57_sqs_send_options.md`, which states that definition because
three plausible readings of "takes a string" give 3, 4 and 5. So a reader taking the first
literal in the body has four chances to publish something that is not a queue as one. The
review measured the owner half of that happening: a body touching a metrics recorder with a
`queue` method published `internal-metrics` as this module's SQS queue.

*`single_call` reads its positions off one call site rather than walking a chain, so this
entry predicted the fix "needs a declared way to say `this argument is a builder lambda, and
the destination is at `queue(arg0)` inside it`". That is what shipped, near enough to quote —
`lambda_arg` and `lambda_steps` — and the paragraph is kept for that rather than repeated as
an open question.*

### OI-75 — five of `TerminalKind`'s eight members, and one of `TargetKind`'s three, have no producer

**Found by** W30's review, which asked the question `RootKind`'s own docstring already
answers for `entry_point` and this set did not answer for anything: which members are
actually written, and why the rest are not.

**What is written.** `persistence` and `unresolved`, and `database` and `cache`. One
catalog declares a `terminals` block, all twelve of its rules say `persistence`, and the
measured output across `mall-admin`, `spring-petclinic-rest` and `jhipster-sample-app`
contains no other value.

**The five absentees (six until `G-52`) are absent for two different reasons, and conflating them was the
finding.** The published note said only that "no shipped catalog declares a rule that mints
one", which is true of half of them and false of the other half:

| member | why it is absent |
|---|---|
| `outbound_call`, `async_handoff` | one catalog rule away — an `owner` rule naming `ExecutorService` mints `async_handoff` today |
| ~~`throws`~~ | **produced since `G-52`, 2026-09-12** — and by the second route below, not a catalog rule: `resolve/terminals.classify` returns it for a `throw` site from the site's own `invoke_kind`, because how a body exits is not a property of any callee's type. This entry read "six" until then |
| `TargetKind.file` | likewise: `io.minio.MinioClient` and `com.aliyun.oss.OSSClient` are live on `mall-admin` and read `unresolved` |
| `cycle` | unreachable BY CONSTRUCTION — a cyclic edge has a non-NULL `callee`, so `resolve/terminals.classify` returns NULL for it and always will |
| `returns`, `ends_silently` | unreachable by any rule — they describe how a BODY exits, and all three catalog routes are predicates on the callee's TYPE |

**Consequence:** none to today's output, which is why this is an open issue rather than a
defect. It matters to a reader of `call_edges` deciding whether an absent value means the
analysis found nothing or cannot express it, and to a catalog author wondering whether a
rule of theirs could produce one.

**Closes by** two separate acts: declaring the rules for the first three (cheap, and
`file` has live candidates waiting), and — for the last three — a mechanism that classifies
a BODY's exit rather than a callee's type, which is a different pass, not a different rule.
Either half may close on its own. `throws` closed by the second: the throw site (`G-52`)
is exactly such a mechanism for the one exit the instruction stream states.

**Falsified by** finding that `returns`/`ends_silently` were never meant for `call_edges`
at all, in which case the fix is to narrow the set the way `RootKind` was narrowed from six
to three — the precedent this issue is written against.

### OI-76 — `Direction.both` has no producer

**Found by** W27's review, which asked the question the repo's own precedent already
answers for `entry_point` (`OI-22`) and nobody had asked here.

**What happened.** W27 deleted `merge_endpoints.sql`, the only pass that ever wrote
`both`. It folded a declaration this module can fully see together with an observation it
fundamentally cannot — one module serving an address it also calls, and one module calling
another service's copy of a shared address, are indistinguishable from inside a single
module — so F5 §6.1 made the two rows stand and `resolve/self_exchange.py` file the
question instead.

**Consequence:** none to today's output. `both` never appears in an `endpoints` row, and
nothing downstream branches on it in a way that would notice. It matters to a reader of the
column, and to anyone wondering whether an absent value means "not found" or "not
expressible here".

**Why the member stays.** `both` is a claim about TWO modules, and the linking tier is
where both are visible: a schema match or human curation can justify it there. Removing it
would mean adding it back with the linking tier, and the set is the same set.

**Closes by** the linking tier writing one, at which point this is not an issue but a
feature. It could also close the way `RootKind` was narrowed from six to three — by
deciding the member belongs to a different schema than this one — but that decision has not
been made and the linking tier is the expected answer.

**Falsified by** a linking design that gives the joined claim its own row kind rather than
a direction, which would leave `both` genuinely unreachable and make narrowing the set the
right close.

---

### OI-77 — an outbound `single_call` payload passed as a method PARAMETER carries no contract · **CLOSED, W43**

**Found by** W43, while checking that the new STOMP outbound rows behaved like their twin.
They do — which is the point: the gap is uniform, and it is six catalogs wide.

`_reference_of` (`application/resolve/shapes/arguments.py`) turns a call argument into the
type reference `_payload_descriptor` roots at. It answers for three kinds — a `class`
literal, a scalar literal, and an `instance` — and returns `None` for everything else. Its
own comment enumerates what falls through as *"`unresolved`, `null`, `lambda`"*, and
`parameter` is not in that list, which is what makes this look like an omission rather than
a decision: the kind is simply not handled.

**Measured.** On the fixture, **22 of 25 outbound `single_call` rows carry no request shape**
— `spring-kafka-template`, `spring-jms-template`, `spring-pubsub`, `kafka-clients`,
`spring-kafka-message` and `spring-stomp-template`. The three that do carry one all pass a
`new` expression: `restTemplate.exchange(..., new HttpEntity<>(new OrderRequest()), ...)`
and two `spring-ws-template` calls. `mall-admin`, `spring-petclinic-rest` and
`jhipster-sample-app` derive **no outbound `single_call` row at all**, so every live
instance is in the fixture.

**Why it is a real loss rather than an unknowable.** The value of a parameter does live in
whatever called the method — which is why `parameter` belongs in `_UNREAD_KINDS`, and that
ruling is right for a `channel_arg`, where the DESTINATION is the value. A payload is a
different question: what a contract needs is the TYPE, and the type is stated in the
caller's own descriptor. `announce(OrderView order)` calling
`convertAndSend(dest, order)` names `OrderView` in its own signature, and
`declared_parameters` already indexes exactly that, keyed by the full symbol.

The failure direction is honest — the row ships with a NULL contract rather than a wrong
one — so this is an under-report, not a fabrication.

**Verify:** analyse `fixtures/orders-service` and count outbound rows whose `catalog_id` is a
`single_call` catalog and whose `request_shape` is NULL.

**Falsified by** a ruling that a declared parameter type is too weak a claim to publish —
which would have to explain why the same declared type is published everywhere else a shape
is derived from a signature.

**CLOSED in the same commit that found it.** `CallFacts` carries the caller's own declared
parameters, and `_reference_of` answers a `parameter` argument with the `type` member of the
one it names. Re-measured on the fixture: **3 of 25 outbound `single_call` rows carried a payload, and 19
do.** *Published first as "3 of 27 outbound `single_call` rows", then corrected to "27 across
the `single_call` AND `fluent` engines" — which names no set either: 27 is 25 plus the two
`fluent` catalogs that happened to be in the list, and across both engines the fixture has 44
outbound rows with 24 payloads. Two wrong labels over one right arithmetic; this is the set
that exists (W44's review).* The six that still do not have no body capture at all — a
`send(Message)` whose payload rides inside the message — which is a different question and
not this one.

The DESTINATION half is deliberately unchanged: `parameter` stays in `_UNREAD_KINDS`, so a
`channel_arg` reading one still resolves to `path` NULL at `unresolved`. That ruling was
right and is about the VALUE. This was about the TYPE.

---

### OI-78 — `requires:` means two different things across the estate

**Found by** W47's review, while checking a rule W46's review had introduced.

`requires` gates a catalog on the extractor's declared capabilities: a catalog whose
requirement is unmet is SKIPPED with a reason rather than deriving less. D02 §1 states the
purpose — *"`requires` is the mechanism that keeps degradation visible … Silently finding
fewer endpoints is the failure this prevents"* — and W47 narrowed the test to a measurement:
withhold the capability, re-resolve, and see whether the ROW COUNT changes.

**By that test, thirty catalogs declare a capability they do not need.** Measured, on facts
where every `string`-kind call argument arrives as one opaque `unresolved`:

| catalog | rows with `string_constants` | without |
|---|---|---|
| `spring-resttemplate` | 6 | 6 |
| `spring-kafka-template` | 5 | 5 |
| `spring-webclient` | 12 | 12 |
| `spring-mvc-router` | 3 | 3 |
| `spring-stomp-endpoint` | 2 | 2 |

Every row survives; what goes is the ADDRESS, to NULL at `unresolved`. That is a strictly
worse degradation than the media column `array_arguments` was reverted for, and yet
`string_constants` stays declared on all thirty.

**So `requires` is being used for two things at once**: "this catalog cannot find its
boundaries without X" and "this catalog reads X". Both are defensible. The first keeps a
weak extractor from publishing a thinner estate that looks complete; the second is a
provenance record of what a catalog consumes. What is not defensible is applying one
reading's rule to the other reading's files, which is what a general rule stated in either
form does — W46's review stated the narrow rule and it was false of thirty catalogs the
moment it was written.

**Not a defect with a wrong row anywhere**, which is why this is an open question rather
than a fix: the shipped extractor declares every capability any catalog requires, so no
catalog is skipped in practice and no estate is thinner than it should be. It matters the
day a second extractor exists, or the day someone applies the rule literally and strips
`string_constants` from thirty files.

**Verify:** rewrite every `kind: "string"` call argument in the fixture's facts to
`{"kind": "unresolved"}`, re-resolve with the full capability set, and compare row counts
per catalog.

**Falsified by** a ruling that `requires` is a provenance record, in which case the four
array-reading catalogs should all declare `array_arguments` and the rule W47 measured is
the wrong test.

### OI-84 — the principles sweep of 2026-09-05, folded

**Folded 2026-09-11** when `docs/open-issues.md` OI-84 was removed. It was 2,195
lines: the triage of one audit, frozen as that audit's record. Its findings were acted on at
the time and its remaining value was two things, both preserved rather than the whole file.

**1. The anchors two tests cite.** `tests/architecture/test_guard_pins.py` cites `S1-MAJ-1`
for a backlog entry, and `tests/architecture/test_defaulted_identity_values.py` cites §4 for
the rule it enforces. Both are prose citations in docstrings — neither opened the file — and
both now point here. The rules themselves live where they are enforced: in the tests, and in
`GUIDELINES.md` §8.3, which the sweep produced.

**2. The rule it exists to have produced**, already in `GUIDELINES.md` §8.3: *a new principle
ships with its retroactive audit list.* That is the sweep's actual output; the 2,195 lines
were the audit, and an audit's job ends when its findings are placed.

**Why it is not archived instead.** A frozen record nobody reads, that forty files cite, is
the documentation sprawl this consolidation exists to end. Its history is in git — `git show
HEAD~1:`docs/open-issues.md` OI-84 — which is where a frozen record belongs.

### OI-83 — documented mechanisms that do not exist, folded from `open-issues.md` OI-83

**Folded 2026-09-11** when that file was removed. It opened 2026-09-04 with fourteen rows,
seven of which closed. The seven that did not are below, verbatim in substance, because its
own lesson is the one this register exists to carry: **for this codebase, a document is not
evidence that a mechanism exists** — four rounds of adversarial spec review missed two
phantom mechanisms because every reviewer read the same documents the author did. A shared
false premise is invisible to review and visible to a grep.

**The standing rule it produced, which moves to `GUIDELINES.md` rather than dying here:**
before a spec cites a mechanism as shipped, grep for it in `src/`.

| # | Mechanism | What the code does |
|---|---|---|
| 1 | `detect:` / `detect.coordinates` | **PARTLY CLOSED, 2O Task 6.** Now on the `Catalog` model and read by the loader, and it GATES the **two** styles whose framework rule is conditional on the library — `derived_resource` and `config_join`, `application/resolve/dependencies.py::DEPENDENCY_GATED`, applied in `gate_reason`. **Re-measured |
| 2 | `ClasspathEntry` | Still **constructed nowhere**, deliberately (2O Task 6): an entry names a resolved ARCHIVE and its tier, which the Gradle report carries and a parsed POM does not, so filling it from Maven would mean inventing a path. The coordinate half a gate needs is `ModuleFact.dependency_coordinates` instead. |
| 10 | Project catalogs — D02 §6's repository-supplied catalog directory | **No repository-supplied catalog is ever loaded.** The catalog set is hard-wired to the installed package's own directory: `api.py:565` → `resources.py::catalogs_dir` (`:34-46`), which resolves `<package root>/catalogs` and raises if it is absent. There is no parameter, no merge and no search path,  |
| 11 | D01 §5's ten named queries — `callers_of`, `callees_of`, `implementations_of`, `uses_of`,  | **None of the ten existed when this was folded; five more do now, so six have a reader (amended 2026-10-22, below).** Across `src/` and `tests/` the ten names occur exactly once, and that occurrence is `engines/scheduled_work.py:13` citing `trace_of` as a thing that does not exist. The real registry is `storage/duckdb/workspace.py:10`'s `_NAMED_QUERIES`, a different and resolver-internal |
| 12 | `publishing` in the Gradle init script | **Deliberately unconsumed since 2026-09-04.** Its only reader was `GradleDetector._classify`, removed by the user ruling that publishing says where artifacts go rather than what a module contains. Listed here so it is not rediscovered as an accidental phantom: the emission stays only because removin |
| 13 | `~/.sextant/config.yml` and the repository-root `sextant.yml` — **both files, whole** | **Neither file is ever opened.** `grep -rn "sextant\.yml" src/ \ |
| 14 | The `filesystem` catalog style | **No engine.** `filesystem` is absent from `application/resolve/endpoints.py`'s `_ENGINES` (`:214-253`), which is the dict a catalog's `style:` is resolved against, so a catalog declaring it raises `CatalogError` from `_engine_for` (`:196-211`) at the top of `derive_endpoints` (`:83`), before `endpo |

**Where each is tracked now.** #10 and #13 are standing retirements (a repository-supplied
catalog would make D02's schema a public API). #11's ten named queries are `FR-9`/`FR-10`'s
missing surface and sit with `G-71` on the delivery list. **Amended 2026-10-22 (Group H):
five more of the ten now ship, in process only, as `question_callers`, `question_callees`,
`question_implementations`, `question_uses` and `question_impact_step` in
`storage/duckdb/workspace.py`'s `_NAMED_QUERIES`, answered by
`application/query/questions.py` through `sextant.api.query` — beside `trace_of`, which is a
Python walk (OI-25), and a sixth question, `source`, that was never one of the ten. The
four that remain absent are `paths_between`, `endpoint_for_address`, `who_uses_shape` and
`who_reads_config`; no command-line noun or plugin reads any of them, which the language gate
of 2026-09-18 still holds (reopened for the function alone).** D01 §5 and PROJECT.md carry the
count. #2's classpath tiering waits on a
resolved classpath under both build systems. #12 is an emission to delete when a
build-script change is next authorised. #14 is the `filesystem` engine, deliberately ahead
of implementation.

### OI-80 — a suspending function's primitive return publishes the BOXED type, its non-suspending twin the primitive · **CLOSED, 2026-09-12**

**Found by** the review of `G-63` (`7716ab3`), measured rather than reasoned.

`suspend fun suspCount(): Int` publishes `symbol: java/lang/Integer#`; `fun plainCount(): Int`
publishes `symbol: int#`. Same for `Boolean` and `Long`. `wire_type` agrees on both
(`integer`), so a consumer reading the wire projection sees no difference — but
`ClassScanner.java` names FOUR consumers that compare parameter and return SYMBOLS across
declarations (an overload dedup key, a bridge-recognition rule, a supertype selector matched
against catalog-declared types, and a payload-type lookup), and those see two spellings of one
declared type.

**The cause is the source, not a bug in the read.** A suspending function's declared return is
recovered from the `Continuation`'s type argument, and a type argument cannot be a primitive —
the class file genuinely says `Ljava/lang/Integer;` there.

**Strictly better than what it replaced**, which was `java/lang/Object#` for every suspending
return, so this is an unfinished improvement rather than a regression. **Closes by** reading
the declared return's classifier from `@kotlin.Metadata` for the primitive cases only, where
the boxed-versus-primitive answer is exactly what `Attributes.isNullable` already supplies.

**CLOSED by** `feat(extractor): a suspend fun returning Int reads as int, not Integer, where
the source declared it non-null (OI-80)`, proved by
`extractor-jvm/src/test/java/dev/sextant/extractor/KotlinSuspendPrimitiveTest.java`.
`KotlinNullability.Decoded` now keeps each function's declared return CLASSIFIER beside its
nullability, and `KOTLIN_PRIMITIVES` names the eight classifiers (`kotlin/Int`, `Long`,
`Boolean`, `Double`, `Float`, `Short`, `Byte`, `Char`) that compile to a JVM primitive when
declared non-null. Where a suspend function's classifier is one of those AND its declared
return is non-null, the recovered reference is the primitive's — `suspCount(): Int` reads
`int#` with the same whole reference as `plainCount(): Int`. `suspMaybeCount(): Int?` keeps
`java/lang/Integer#`, nullable: a nullable `Int` genuinely boxes, so the `Integer` the
signature spelled is the right answer there.

Found and closed in the same change, one position along: a return declared as a bare type
variable (`fun <T> ranked(x: T): T`) read `nullable: false` from metadata, which describes the
variable and not what a caller binds it to (`ranked<String?>(null)` is legal). A bare `T`
now keeps Java's rule on the return, parameter and field projections — the field of a
`val x: T` carries no `ext.kotlin` block at all, so a getter, a constructor parameter and a
field of one declared type do not disagree, which is the intra-class disagreement `G-63`
was opened for; `T?` still reads `true`. A bound that would settle it (`T : Any`) is not
read.

### OI-81 — a `$default` bridge and the function beside it disagree about one declared type · **CLOSED, 2026-09-12**

**Found by** the review of `G-63` (`7716ab3`).

Measured on `KotlinSample`: `copy` returns `nullable: false` and `copy$default` returns
`nullable: true`. The bridge is a compiler synthetic with no entry in `@kotlin.Metadata`'s
function list, so it falls back to Java's rule while its sibling reads the declared type.

**Before this it was uniformly wrong rather than inconsistent** — both said `true` — so the
register records a NEW disagreement, not a new error. Contained by the bridge carrying
`synthetic: true`, which a consumer can already filter on, and by §5.13's `$default` row which
states the bridge is read as a second symbol at all.

**Closes by** the same work that closes `$default` generally: recognising the suffix and the
mask parameter, at which point the bridge stops being published as an independent declaration.

**CLOSED by** `feat(extractor): a Kotlin $default bridge names the function it stands for and
takes its declared types (OI-81)`, proved by
`extractor-jvm/src/test/java/dev/sextant/extractor/KotlinDefaultBridgeTest.java`. Measured
first, on kotlinc 2.2.0: `fun greet(name: String = "x", loud: Boolean = false): String` emits
`greet$default`, flags `ACC_PUBLIC | ACC_STATIC | ACC_SYNTHETIC`, descriptor
`(Ldev/sextant/extractor/KotlinDefaultsSample;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String;`
— the receiver, the function's own slots, one `int` mask per 32 parameters (a 33-parameter
function carries two), an `Object` marker; a `@JvmStatic` function's bridge has no receiver
slot, and a `suspend fun`'s carries its `Continuation` before the mask. `KotlinDefaultBridge`
recognises that shape (the mask count is solved from the slot count, not counted as trailing
`int`s, which a function whose last parameters are `Int` would defeat), derives the sibling's
`name + descriptor` by dropping the receiver and the masks and marker, and settles the
receiver question by which ONE candidate `@kotlin.Metadata` keyed — where it keys both
(review case: an `object`'s `@JvmStatic fun js(a: String, b: Int = 0): String` beside an
arity overload `fun js(b: Int): String`, whose key the receiver-dropped candidate derives),
there is no sibling and the bridge carries only its name, because ambiguity is not a guess.
The bridge is then read under its sibling's key: `greet$default` reads `name: String` as
`nullable: false` and its return `false`, where both read `true`; `maybe$default` borrows
`true` for `note: String?` and `String?`. The receiver, the masks, the marker and a suspend
sibling's `Continuation` are nobody's declaration and keep Java's rule. A suspend sibling's
bridge returns the erased `java/lang/Object#` with the declared nullability over it —
accurate for the erased protocol, not the declared type, which only the sibling's
`Signature` holds.

**Departing from the "closes by" above in one respect, deliberately:** the bridge is still
published as its own symbol, now carrying `bridge_of: "greet"` beside its `synthetic: true`
(D00 §5a). A call site names the bridge by its own descriptor, so a fact for it has to exist
for the call to resolve to anything; `bridge_of` is what lets a consumer follow it back to the
declaration. Every consumer that filters `synthetic: true` (`derive_endpoints.sql`'s
member rule, `shapes/expansion.py`, `effective_annotations._is_synthetic`) already excludes
it, so the field is informational until dispatch reuses it. The bridge's parameterized slots
stay erased at the type level — it carries no `Signature`, and a `List<String?>`'s element
is not invented from metadata; only the declared nullability at each level the two agree on
is applied, which for an erased `List` is the top.

### OI-82 — `G-63`'s PARAMETER half: a Kotlin function's and constructor's value parameters still take Java's rule · **CLOSED, 2026-09-12**

**Found by** implementing `G-63`'s return half (`7716ab3`), which closed the half it names and
left this one measurable.

`KotlinOrder#<init>`'s parameters and `copy`'s read `nullable: true, nullable_resolution:
"resolved"` regardless of what the source declared, carrying kotlinc's own `@NotNull` in the
same fact — the identical defect the return half just closed, one position along.

**The mechanism is now in place and unused for this:** `KotlinNullability.Decoded` already
decodes the function list; what is missing is `KmValueParameter`'s type per position and the
alignment from a metadata parameter index to a descriptor slot, which is not the identity
where a synthetic leads or trails.

**Recorded rather than absorbed into the return half's commit**, because a claim that `G-63`
is closed when half of what its row names is still live is the register defect this file
exists against. `docs/java-kotlin-delivery-list.md`:241`'s `G-63` row names both.

**CLOSED by** `feat(extractor): a Kotlin parameter carries the nullability its source
declared, type arguments included (OI-82)`, proved by
`extractor-jvm/src/test/java/dev/sextant/extractor/KotlinParameterNullabilityTest.java`.
`KotlinNullability.Decoded` now keeps each function's and constructor's declared parameter
types (`KmType`, whole — not a boolean), and `TypeRefs.withDeclaredNullability` walks that
tree beside the `Node` tree built from `Signature`, before serialization, applying the
declared nullability at every level where the two trees agree on shape: `List<String?>` and
`List<String>?` now read differently, where one descriptor and one signature spelled them
the same. Where metadata's parameter count differs from the descriptor's declared slots
(an extension function's receiver, an inner class's enclosing instance, an enum's
name/ordinal), nothing is applied and every parameter keeps Java's rule. A `var`
property's SETTER is neither a function nor a constructor in metadata and still takes
Java's rule — the same shape `G-63` closed for getters, one position along; not
re-opened here because no fixture exhibits it (§4.1). `GenericSignatureTest`'s pin on
`batched(List<String>)`'s element moved from `nullable: true` to `false` — the pin was
carrying the defect.

### G-52 — a `throw` is an exit the call graph did not record · **CLOSED, 2026-09-12**

**Found by** the completeness audit of 2026-09-06 (F1 §2.3): every `ATHROW` was dropped by
`extractor-jvm/.../MethodFlow.java`, so a method whose only exit is a throw published a call
to the exception's CONSTRUCTOR and nothing saying the method then left through it — the same
facts as a method that builds an exception to hand somewhere else. A trace that ended in a
throw looked like one that fell off the end. D00 §5 had reserved `invoke_kind: throw` for
exactly this and nothing produced it; the same paragraph also claimed a throw site is "what
gives traces their `throws` terminal", which was false — `terminal_kind` came only from
`rules.of(target)`, which never reads an invoke kind.

**CLOSED by** `feat(extractor): a throw is an exit — every ATHROW is a call-site fact whose
target is the thrown type, and traces stop on it (G-52)`, proved by
`extractor-jvm/src/test/java/dev/sextant/extractor/MethodFlowTest.java`'s
`publishes_a_throw_as_an_exit_naming_the_thrown_type_and_no_method`,
`tests/domain/test_facts.py`'s `test_a_throw_site_round_trips_naming_a_type_and_no_method` and
`test_a_throw_site_may_name_no_type_and_a_dispatching_call_may_not`,
`tests/application/test_terminals.py`'s
`test_a_throw_edge_is_throws_from_its_invoke_kind_and_not_from_a_rule`,
`tests/application/test_call_edges.py`'s
`test_a_throw_site_is_one_resolved_edge_to_the_thrown_type_and_reads_throws`,
`tests/application/test_trace.py`'s `test_a_throw_with_no_target_stays_null_on_its_step`,
`tests/application/test_reachability.py`'s `test_a_throw_whose_type_was_unread_reaches_no_symbol`,
`tests/egress/test_render_traces.py`'s
`test_a_throw_step_is_an_arrow_labelled_throw_into_the_thrown_type` and
`test_a_throw_whose_type_was_unread_is_a_self_arrow_said_in_words`, and the counts pinned in
`tests/e2e/test_vertical_slice.py`. Every `ATHROW` is now a `call_site` fact with
`invoke_kind: "throw"` whose target is the thrown TYPE — read from the value's producer, a
`NEW` or an invoke's declared return type, and NULL for a rethrow whose type lives in the
try-catch table this pass does not read — with no `name` and no `descriptor`, absent rather
than empty; `CallSiteFact` enforces that only a throw omits them. `call_edges` skips dispatch
for it and gives it a row with no candidates, `classify` returns `terminal_kind: throws` from
the invoke kind rather than a catalog rule, and the document renders a type-unread throw in
words rather than as a symbol named `None`: the step's `target` stays NULL from
`query/trace.py` onward, the step table's call cell reads `throws (type unread)`, the
sequence diagram draws a self-arrow on the method that exits labelled `throw (type unread)`
(a lifeline is a type that holds state and receives calls, and a type nobody named is not
one), and `reachability` records no symbol for it — the exit is on the step row, and that
table is what a root REACHES. D00 §5 now states the shape and no longer claims the catalog
path produces `throws`. Measured on the fixture: 39 throw sites, 8 named types, 5 rethrows
unread, call edges 1486 → 1525 and `resolved` 1484 → 1523, both by exactly 39;
`owner_not_scanned` unmoved at 345, because a throw dispatches to no method and records no
lookup.

*Logged, not fixed, because no fixture needs either: `CHECKCAST` is transparent to the
producer walk, so `throw supplier.get()` where the cast names `X` publishes the invoke's
declared `java/lang/Object#` rather than `X`; and ASM's
`Interpreter.newExceptionValue(TryCatchBlockNode, Frame, Type)` would hand the rethrow's
type over at the source, closing the 5 unread. Both are one override away.*

### G-73 — `visibility` was two-valued for a four-valued concept · **CLOSED, 2026-09-12**

**Found by** the completeness audit of 2026-09-06 (F1 §2.3): `ClassScanner.java` wrote
`(access & ACC_PUBLIC) != 0 ? "public" : "other"` on every symbol fact — method, field and
type alike — collapsing `protected`, package-private and `private` into one word that says
nothing about which. JVMS 4.1 states all three of the other access flags in the same class
file `visibility` already reads; there was never a reason to fold them together.

**CLOSED by** `feat(extractor): visibility is the four words the language has, not
public-or-other (G-73)`, proved by
`extractor-jvm/src/test/java/dev/sextant/extractor/AccessFlagTest.java`'s
`visibility_is_the_four_words_the_language_has_not_public_or_other` and the sibling
`MethodModifierScanTest.java`'s pin, `reports_a_private_method_as_private`, corrected rather
than left asserting the two-valued reading. `ClassScanner.visibilityOf` now tests
`ACC_PUBLIC`, `ACC_PROTECTED` and `ACC_PRIVATE` in turn and falls back to `package`, the one
case none of the three is set — the same JVM word every scanner emits for the symbol,
whether method, field or type, since all three share the one `emit`. `AttributeLedger`'s
`ACC_PRIVATE` and `ACC_PROTECTED` entries move from `skipped` to `read("visibility")`,
naming the reader that now exists rather than the reason it did not. `Visibility`
(`src/sextant/domain/closed_sets.py`) is the new closed set (NFR-5) and
`SymbolFact.visibility` (`src/sextant/domain/facts.py`) is typed to it rather than to `str`,
so a fact naming a fifth word fails validation rather than being silently accepted.

**Left exactly where it was: a NESTED type's visibility.** The class file's own word for a
nested type is still the coarse one — a `private` or `protected` nested type is written
package-private or public respectively at that level (`OI-51`, unchanged by this) — so a
nested type's `visibility` fact is its OUTER word until `OI-51` recovers `InnerClasses`'
own source modifier. D00 §5 states this beside the four-valued rule so the two are not read
as one claim.

**`fact_schema_version` is not bumped.** `src/sextant/domain/version.py`'s own ruling (user,
2026-09-07) freezes both schema stamps until release — "a fact-shape change lands WITHOUT an
increment, deliberately" — and this change rides at the same integer every value-level
change since has. The one place that matters: within a single `analyze` run the JVM
extractor's own JSONL output is parsed straight back through `SymbolFact` (`factfile.py`'s
`read_fact_tree`), so a STALE, unrebuilt extractor jar run beside the rebuilt Python would
still emit `"other"` and now fail that validation instead of silently writing it — the
`./gradlew build` this task's own gate runs before `check.sh` is what prevents that in
practice. A previously-analyzed `workspace.duckdb` is unaffected either way: render, enrich
and export read its `visibility` column as a plain string over SQL and never reconstruct a
`SymbolFact` from it, so an old workspace simply keeps answering `other` for anything that
was not `public` until it is re-analyzed.

### OI-79 — a figure DERIVED is published as a figure MEASURED, and nothing checks the difference · **§13.8 VIOLATION COUNT: 8**

**Found by** the reviews of W50, W53, W54, W56 and W57, each of which caught the same shape
independently. Counted here rather than only in `docs/RUNBOOK.md` because §13.8's 2026-09-06
ruling says violations are counted where someone other than the agent that committed them can
see them.

**The defect:** a number reached by arithmetic on other numbers, or by comparing two
measurements that are not alike, written in the voice of a direct reading. The full table is in
the RUNBOOK entry *"A figure derived is not a figure measured"*; the eight are `26 of 26`
capabilities, `8/5/4` component statuses, "retired four entries", "478 of 481 citations", "five
near-misses cover fourteen", "four methods take a `String`", "a 7s saving", and "would delete
54% of the graph".

**Why it is a VIOLATION and not an error.** §8.1 already rules that a rule taken from memory or
documentation is a prediction, and the RUNBOOK already generalises it — *"Half a measured rule
is a prediction"*. The principle exists and was agreed. What neither reaches is a number in
PROSE: §8.1 governs what a catalog may claim about a framework, and these are sentences in
changelog entries, plan rows, register tables and code comments. Those are where this project
keeps its evidence, and they are checked by nothing.

**Why prose will not fix it.** Every one of the eight was written by someone who had just done
real measurement a few lines earlier. A measured figure and a derived figure are the same
sentence once written — "23 entries" and "26 minus the 3 unshipped" — so the text carries no
mark of which kind it is, and the derived one inherits the authority of the measured one.

**What exists already, and what it does not reach.** `test_shipped_counts.py` checks a stated
catalog total; `test_source_citations.py` checks a `file.py:NNN`. Both were written *after* this
class had already recurred, both cover one narrow referent, and neither reaches a percentage, a
wall-clock timing, a count of tests, or a ratio whose denominator is a judgement.

**Closes by** a mechanism settled with the user, per §13.8 step 3 — a rule already written,
already agreed and broken eight times is not fixed by writing it a ninth. **Falsified by** a
ninth instance arising in a place a mechanism could not have reached, which would make this a
hard problem rather than an unenforced rule.
