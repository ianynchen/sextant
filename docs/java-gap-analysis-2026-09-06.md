# The Java/Kotlin gap analysis — 2026-09-06

## 0. What this is, and what it is not

Five read-only audits ran on 2026-09-06 against `feat/phase-2o-spring-surface`
(`src`/`tests` at `973e36b`; `abfd93c` since, `docs/` only). This file is their durable
form: consolidation, de-duplication and classification. **Nothing here is new analysis of
the code.** Where an audit measured something, the measurement is carried verbatim with its
evidence; where an audit could not measure something, it stays marked unverified here, because
a guessed gap becomes a wrong spec item.

| audit | lane | what it produced |
|---|---|---|
| **A1** | every Java/Kotlin row of `docs/COVERAGE.md` §5 | 170 rows verified · KEEP 120 / CORRECT 11 / BUILD 28 / RESTATE 11 · 22 rows with a wrong claimed status · 5 Critical, 14 Major |
| **A2** | all 55 catalogs against their jars | KEEP 30 / EXTEND 15 / CORRECT 2 / MEASURE 8 · 25 enumerated, 10 incomplete · 2 Critical, 10 Major, 11 Minor |
| **A3** | 13 engine styles + 14 passes, driven | KEEP 12 / CORRECT 9 / EXTEND 7 · 2 Critical, 4 Major, 3 Minor · 28 vocabulary gaps, 4 invented-language-rule sites |
| **A4** | the ASM extractor against JVMS 4.7 | `✅` not earned, honest marking `◐` · 4 of 30 attributes read fully, 18 silently dropped · 2 Critical, 11 Major |
| **A5** | committed scope across four registers | 76 committed items, 15 scope disagreements · 3 Critical, 8 Major, 6 Minor |

This is step 1 of the four-step process the user asked for. **Step 2's spec is written from
this file**, so a gap that is wrong here becomes a spec item that is wrong, and a gap missing
here is never built. §3 is the enumeration; §4 is what the spec should actually fix; §5 is
what the spec must not touch.

Two rules were applied throughout. **No severity was re-scored without saying so** — every
re-score and every split of one finding into several rows is disclosed in §3.1. **No gap was
invented**: where two reports disagree, or where the brief that commissioned them was wrong,
§7 says so and leaves it open.

---

## 1. The verdict, in one paragraph

Java/Kotlin support is **broad, deterministic, honestly documented in most places, and
resting on a scanner and a dispatcher that each get one foundational rule of the platform
wrong**. Eighty-six §5 rows are genuinely shipped and 120 of the 170 rows need no change;
determinism holds end to end on real modules; `egress` never derives; the guard harness is at
82 killed / 0 survived with an empty allowlist and 2 346 tests pass. Underneath that, the
extractor **cannot read a class file produced by the current LTS JDK at all** — majors 68+ are
refused and one such entry fails the whole run with zero facts written — and the dispatcher
does not perform JVMS 5.4.3.3 method resolution, so a call to a method a superclass declares
is reported as a third-party boundary in a document that prints, in words, that a boundary
means the body is not here (34 of 161 boundary steps on spring-petclinic, 21%, are that claim
about the module's own code). Six further Criticals publish rows the framework does not serve:
a class-level plus method-level listener concatenates two destinations into a third nobody
wrote, in three shipped catalogs; the endpoint merge key omits `peer`, so a route a module
serves and a call to another service on the same path become one `both` row with the outbound
row deleted; Spring Cloud Stream binds every candidate where the framework binds exactly one
or none; parameter annotations are attached to the wrong parameter on inner-class and enum
constructors. Alongside those, whole spellings and whole directions are silently absent —
`javax.jms`, the `javax` JAXB spelling, Spring MVC functional routing, the receive half of
four template catalogs, the WebSocket client direction — and four committed v1 requirements
(FR-11..FR-14) have zero implementation and appear in no register at all, while the document
COVERAGE names as the delivery-status authority marks every data definition and module
`planned`. **The failure mode is not that the project claims too much protocol coverage; it
is that the instrument it counts coverage with — §5's protocol-axis checklist — has no place
for the things that are wrong.**

---

## 2. The census, corrected

Several previously-circulated numbers were wrong. The corrections matter more than the
originals because the originals were quoted in planning.

**§5 holds 170 Java/Kotlin rows.** Classifying the **tier cell alone** — which is what
`scripts/coverage_matrix.py` itself parses — gives:

| classification of the tier cell | rows |
|---|---|
| ✅ shipped | 86 |
| ◐ partly shipped | 3 |
| stated boundary (`Boundary` / `Stated dependency` / `Limitation` / `Version-scoped`) | 53 |
| pending A | 13 |
| pending B | 10 |
| pending C | 5 |
| **unclassifiable** | **0** |
| **total** | **170** |

The earlier headline — "59 shipped / 55 boundaries / 29 pending / 27 unclassified" — was a
**regex artefact**: it matched whole line text, so a shipped row whose prose contains the word
"Boundary" was counted as a boundary and vice versa. Every row classifies at the cell level.
Two structural facts travel with any count quoted off this document: `coverage_matrix.py`'s
`classify()` returns `None` for `Boundary — …` (it is `B` followed by `o`), so **53 of the 170
rows contribute nothing to §2 and a reader of §2 cannot see them**; and **every §5 row is
labelled `Java` — there is not one `Kotlin` row**.

Verified independently for this file: `awk` over §5.1–§5.12 counts **170** `| Java ` rows;
`ls src/sextant/catalogs/*.yml` counts **55**; `grep -c '^measured:'` counts **36**.

**36 of 55 catalogs carry a `measured:` block, not "10 of 55".** `_NOT_MEASURED_YET`
(`tests/architecture/test_catalog_measurement_coverage.py:95`) holds exactly **19** names, and
36 + 19 = 55 reconciles exactly. The "10" was what Stage 4's own two batches measured. The
roadmap's copy of this number was corrected at `abfd93c`, **after** the audits ran;
`docs/COVERAGE.md:2255-2258` and `docs/open-issues.md` OI-10's body still carry the old 29/26.

**`spring-mvc.yml` does cite evidence.** It carries `measured: {artifact:
org.springframework:spring-webmvc, versions: [6.1.6, 6.2.15, 7.0.2, 7.0.9], identity:
reported, by: scripts/probes/cp11_sweep_round1.md}` (`spring-mvc.yml:14-16`), as does
`spring-web.yml` via CP-7. The sweep's §6.2 table saying otherwise is stale — and that table
enumerates **52** catalogs, omitting `spring-advice`, `spring-integration` and
`spring-scheduling` entirely.

**WebSocket is NOT a complete cell.** §2 renders it `◐ —` — shipped, no gaps — because it
measures 3/0/0, and it measures 3/0/0 only because **§5.5 states its boundaries as prose
bullets rather than table rows and the generator counts rows**. The three rows are individually
true and all three KEEP. Behind them sit eight boundary bullets, every one verified true; an
entire spelling (`javax.websocket`) with no row and no catalog, where §5.1 gave the servlet
twin of that problem its own row *and* its own catalog; the whole client/outbound direction,
neither shipped nor stated as a boundary; and a live wrong-protocol fabrication (G-16).

**The guard harness is at 82 killed / 0 survived / 0 unmeasurable, empty allowlist.** The
sweep §12 records 31 and §13.1 records 41; both are stale.

---

## 3. Every gap, merged

### 3.1 How this table was built

**Verdicts.** **KEEP** = right as it stands (these are in §5, not here). **CORRECT** = shipped
behaviour or a shipped catalog that is wrong. **BUILD** = a surface that does not exist yet.
**RESTATE** = a document or register that says something untrue about a thing that is itself
fine. **MEASURE** = the rule is a prediction; no committed probe opened the artifact.

**Severity** is each audit's own, unchanged, except where the row's Notes say otherwise. A4
used a four-level scale (Critical / Major / Moderate / Minor); its **Moderate** is carried
verbatim rather than folded into Major or Minor.

**Merges made** (the same defect found twice, filed once):

| merged into | from | why they are one |
|---|---|---|
| G-29 | A1 M-6 (WebMvc.fn) · A2 F-4 | one absent catalog for `org.springframework.web.servlet.function`; A1 found it by enumerating the framework's surface, A2 by `grep -rl 'web.servlet.function' src/sextant/catalogs/` against `spring-webmvc` 6.2.15 |
| G-32 | A1 M-6 (WebSocket client) · A2 F-13 | one absent direction: A1 has no catalog and no boundary row for `@ClientEndpoint`/`connectToServer`/`WebSocketClient`; A2 measured that `jakarta-websocket.yml` detects the api jar while the annotations live in `-client-api` 2.2.0 |
| G-36 + G-39 grouped | A2 F-3 (`spring-ws`) · A2 F-7 (`netflix-dgs`) | both are `OI-36`'s shape one framework over — a `@Repeatable` annotation whose container nobody declared. Filed as two rows because they are two catalogs and two measurements, and as one root cause in §4 (RC-7) with A2 §6's structural remedy attached |
| G-16 | A1 M-2 · A1 M-6 (Spring RSocket) | "RSocket is absent" and "RSocket is mis-derived as `websocket`" are the same surface; the second is the actionable statement |
| G-27 + G-102 | A1 M-13 · A2 §0.2 · A5 D8/F-m4 · A5 D7/F-M6 | catalog counts drift, in four registers. Filed as the two documents that are still wrong (COVERAGE §7, the sweep) plus a closed note for the roadmap |

**Splits made** (one finding filed as several rows, no severity changed):

- **A1 M-6** (one Major, "eight surfaces absent from §5") → G-16 (RSocket, merged) and G-29
  … G-35 (seven rows). Each is separately buildable and two of them merge with A2 findings.
  Effect on the tally: +6 Major rows for one Major finding.
- **A1 M-3** → G-17 (the `javax.websocket` surface) and G-18 (the `detect.coordinates` claim,
  which occurs a second time at `COVERAGE.md:2422` about SQS). +1 Major.
- **A2 F-7** → G-39 (`@DgsData$List`), G-40 (`@DgsEntityFetcher`), G-41 (`@Inherited`). Three
  independent drops in one catalog. +2 Major.
- **A2 F-11** → G-45 (JPA-only repository roster) and G-46 (the ungated collection route,
  which A2 says is a **Critical if the engine really mints it** and which nobody has run). +1 Major.

**Re-scores and severities assigned here, all disclosed:**

- **G-58** (53 boundary rows structurally unrepresentable in §2, plus 4 rows dropped by
  `ALIASES`, two of them shipped readers) — A1 filed this as F-4 in its findings section and
  did not rank it. **Filed Major here**, because it is the instrument every coverage count is
  quoted from.
- **G-115 / G-116** (FR-16 curation; FR-7's missing class diagram) — A5 recorded these as
  requirement statuses in its §1b inventory and raised no finding. **Filed Minor here** so the
  spec sees them; the severity is mine.
- Nothing else was re-scored. G-11 is documentation-only and produces no wrong derived row;
  A1 ranked it Critical and it stays Critical, annotated.

**Not merged, deliberately.** A3's C-1 (no JVMS 5.4.3.3 method resolution) and A4's findings
both concern method identity and are **different defects**: C-1 is *resolution* — which method
a reference resolves to, in Python, at `dispatch.py:108-121`; A4's are *encoding and content* —
the `sig_` disambiguator (which A4 measured agreeing, §6), and descriptor content (parameter
types erased, G-55). Neither fix is the other. And C-1 is **not `OI-17`**: OI-17 is a call
through a **library-declared** type where the `declared` conjunct is a deliberate conservative
choice with a stated blast-radius argument; C-1 is entirely in-module, JVMS gives exactly one
answer, and the walk adds **no** `narrowed` fan-out — which is the whole of OI-17's stated
cost. C-1 also **falsifies OI-17's own close condition**: OI-17 says "*Falsified by* a trace
that stops at an in-module body a reader can see", and `architecture.md:389` is that trace.

### 3.2 The table

| id | sev | surface | what is wrong or missing | evidence | verdict | audits |
|---|---|---|---|---|---|---|
| **G-1** | Critical | `resolve/dispatch.py` | No JVMS 5.4.3.3/5.4.3.4 method resolution. `site["owner"]` is the receiver's static type; if that class does not itself declare the method, `candidates` returns `[]`, so a call to an inherited method is written `callee = NULL, resolution = resolved` — a positive third-party-boundary claim. The rendered document then prints a definition of `boundary` that this makes false | `dispatch.py:108-121`; `javap` on `adv1` (`invokevirtual Adv$Sub.doWork` where `doWork` is in `Base`); `run_adv1.py` → both probe calls write `callee NULL/resolved`; `measure_dispatch.py` recoverable-by-JVMS: petclinic **28**, petclinic-rest **96**, jhipster **8**, mall-admin **0**, orders-service **0**; `architecture.md:389` vs `:141`; **34 of 161 boundary steps (21%)** | **CORRECT** | A3 C-1 |
| **G-2** | Critical | `storage/duckdb/merge_endpoints.sql` | The merge key is `(protocol, method, path)` with no `peer` conjunct, so an inbound route and an outbound call to a **different** service on the same path become one `both` row and the outbound row is `DELETE`d. Reachable on any gateway, BFF or proxy, and on any two services sharing `/orders`, `/health`, `/v1/users` | the `UPDATE … GROUP BY protocol, method, path` and the `DELETE` under it; `dbg_merge2.py` through shipped `spring-mvc` + `spring-resttemplate`, three facts → `both GET /orders peer=payments.internal`; `dbg_merge.py` at the SQL level; D02 §3 describes the **self**-call case only; D02:962 "two deployments on one host are two peers" | **CORRECT** | A3 C-2 |
| **G-3** | Critical | `extractor-jvm` | Class-file majors **45–67 accepted, 68+ refused**, and one refused entry fails the **whole** scan: exception propagates to `Main`'s catch-all, exit 1, zero facts. A module built on JDK 24/25 (current LTS)/26 cannot be scanned at all | `org.ow2.asm:asm:9.7` pinned at `extractor-jvm/build.gradle.kts:15`; measured accept at 45/49/50/52/61/65/66/67, refuse at 68/69/70/71; real `openjdk@26` compile → major 70, exit 1; `byte-buddy-1.18.11.jar` → `Unsupported class file major version 68`, **0 facts**; **8 of 1 792** local jars already carry >67 | **CORRECT** (two fixes: raise the ceiling; per-entry `uncovered` + `partial: true`) | A4 F1 |
| **G-4** | Critical | `extractor-jvm/ClassScanner.java` | Parameter annotations are attached to the **wrong parameter** on inner-class and enum constructors. JVMS 4.7.18 permits `num_parameters` to be **less than** the descriptor's parameter count; javac omits synthesized leading parameters. `visitAnnotableParameterCount` is not overridden. Fabrication **and** a drop in one fact | `ClassScanner.java:220-224`; `Outer.Inner(@Q("first") String, @Q("second") int)` → descriptor arity 3, 2 annotation entries; emitted: `@Q("first")` on the synthetic outer instance, `@Q("second")` on `String`, the real second annotation **lost**. On an enum constructor the shift is two, onto `$enum$name`, which is also a `String` — undetectable downstream by type | **CORRECT** | A4 F2 |
| **G-5** | Critical | `spring-kafka.yml`, `spring-rabbit.yml`, `spring-sqs.yml` | A class-level plus method-level listener **concatenates two destinations into a third nobody wrote**, and drops both real ones. One row, `resolution: resolved`, `evidence: compiler`. The addresses-nothing gate cannot reach it — the composed path is non-empty | reproduced end to end against shipped catalogs + real engine + real SQL: `@KafkaListener("orders")` on the class + `@KafkaListener("payments")` on the method → **one row, `path: "orderspayments"`**; `spring-rabbit` `cls.q` + `mth.q` → `cls.qmth.q`; `spring-sqs` `class-q` + `method-q` → `class-qmethod-q`. Mechanism: `derive_endpoints.sql:745-757` (prefixes from any target incl. a TYPE), `:1089` join on `s.enclosing`, `:954-958` bare concatenation because no `path_separator` is declared; gate at `:1221` | **CORRECT** (+ **RESTATE** the three rows) | A1 C-1 |
| **G-6** | Critical | `spring-cloud-stream.yml:29-34` | "Absent from configuration, every candidate binds (the framework's own default)" is **falsified by the framework's own code**: exactly one function bean binds when the property is absent, and with two or more candidates **none** bind. A module with N ≥ 2 `Function`/`Consumer`/`Supplier` beans publishes up to 2N Kafka boundaries the running application creates none of, at `resolved` | `javap -p -c`, spring-cloud-stream **4.1.0** + spring-cloud-function-context 4.1.0: `FunctionConfiguration$FunctionBindingRegistrar.determineFunctionName` returns `hasText(definition)`; `SimpleFunctionRegistry.normalizeFunctionDefinition` substitutes the single name only under `if (list.size() != 1) goto end` (offsets 80-90). Rules 3 and 4 (`functionRouter`, `autodetect`) are modelled nowhere | **CORRECT** | A2 F-1 |
| **G-7** | Critical | `spring-cloud-stream.yml:55-70` | An **unmapped binder name publishes a `kafka` endpoint**. `binder_protocols` maps four names; the file's own rule leaves everything else on the catalog's declared protocol, which is `kafka` (`:7`). `kinesis`, `solace`, `rocketmq`, `jms`, `pulsar`, `eventhubs`, `servicebus` all land there — and DR-5 gates cross-module linking on protocol equality, so a Solace producer links to a Kafka consumer | read off the catalog's own stated rule and its `protocol: kafka` at `:7`. **The behaviour half is unverified** — A2 did not run the engine | **CORRECT** | A2 F-2 |
| **G-8** | Critical | `storage/duckdb/workspace.py:539-551` | The export **silently drops the three tables 2Q exists to produce**: `call_edges` (1 393 rows), `return_flows` (444), `roots` (79) — 1 916 rows — are populated base tables absent from the hardcoded 11-name `_EXPORTED_TABLES`. Nothing discloses it: not `KNOWN_GAPS`, not `manifest.json`, not `## Known gaps`. The rendered `architecture.md` with all 68 traces **does** ship, so a consumer receives the pictures and cannot recompute one of them | `workspace.py:539-551`; `egress/render/metadata.py:19-48`; D06 §5 rules on exactly this class: "omitting them is not an optimisation". (`config_entries`, `field_writes`, `method_returns` are also absent but are views over `raw_facts`, which travels — recoverable, not a loss) | **CORRECT** | A5 F-C1 |
| **G-9** | Critical | `docs/PROJECT.md` | The document COVERAGE names as the delivery-status authority says nothing is delivered: D00-D06 and M00-M09 all `planned` — including D06 (bundles ship, byte-deterministic), M00 (4 verbs ship), M02, M03, M04, M07, M08 — and 2Q `in-progress` against the roadmap's "delivered 2026-09-06" | `COVERAGE.md:4`; `PROJECT.md:41-62`; `roadmap.md:63`; `roadmap.md:390` (stage 3 "done") | **RESTATE** | A5 F-C2, D1, D2 |
| **G-10** | Critical | FR-11 · FR-12 · FR-13 · FR-14 | Four committed v1 functional requirements — drift detection, refactor findings, design findings, structural performance risk — have **zero implementation and zero tracking**, while `M04-resolver.md:213-215` asserts the resolver computes three of them and `D01:597` documents the `findings` table. FR-11 is the sharpest: **both sides are already recorded** (declared shapes from WSDL/proto/avsc/SDL alongside code shapes) and nothing compares them | no `findings` table in `schema.sql`; `grep -r "in a loop\|remote hops\|blocking call\|dependency cycle" src/` → 0; `grep -rn "FR-11\|FR-12\|FR-13\|FR-14" docs/COVERAGE.md docs/open-issues.md docs/documented-not-implemented.md docs/superpowers/plans/*.md` → **0 hits** | **BUILD** (or an explicit descope) + **RESTATE** M04, D01 | A5 F-C3, D15 |
| **G-11** | Critical | `docs/COVERAGE.md` §5.12 (also §5.2, §8) | The table header declares four columns and 14 rows carry five, so **11 Java rows lose their status cell** in any GFM renderer — each renders its *Shape* value under *Tier* and discards its verdict. What disappears includes 2O Task 9's whole delivery record (`:1998`), OI-1's whole record (`:2003` "Boundary — the column is EMPTY"), and `:1994`'s "✅ shipped — **none of them is read**", which renders as `annotation`, i.e. as if `initialDelay` *were* read. `coverage_matrix.py` takes `cells[-1]`, so §2 stays right and the two cannot disagree loudly | header `:1986`; rows 1993, 1994, 1995, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004 (Java) + 2005, 2006, 2014; same defect at §5.2 `:1138`, `:1139` and §8's precedence table `:2217-2221`. **Documentation-only — no wrong derived row** | **RESTATE** | A1 C-2 |
| **G-12** | Critical | `jakarta-jms.yml`, `spring-jms-template.yml` | **Nothing in the repository matches `javax.jms`**, while §5.9's prose says both spellings must be. A Spring 5 / Boot 2 module's entire raw-JMS surface — the producer and all eleven consumer factories — derives `[]` | `jakarta-jms.yml:17` `owner: jakarta.jms.Session`; `javax.jms` in no catalog; verified `javax/jms/Session#.createConsumer(Ljavax/jms/Destination;)Ljavax/jms/MessageConsumer;` → **`[]`**; `spring-jms-template.yml:79`'s `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` misses its javax twin the same way (verified `[]`) while the `(String,Object)` and arity-3 rows survive. `COVERAGE.md:1852-1853` states the requirement in the indicative with no ✅ and no boundary marker. The repository already has the pattern (`javax-servlet.yml`, `spring-sqs-legacy.yml`) | **BUILD** + **RESTATE** | A1 C-3 |
| **G-13** | Critical | `spring-kafka-template.yml` | Every descriptor pins the `CompletableFuture` return (spring-kafka ≥ 3.0), so a call compiled against 2.9 derives **`[]`** rather than an unresolved row — once any row claims the (name, arity), an unmatched call falls through to no row at all. The §5 row claims "all ten overloads" with **no version bound** | reproduced: `kafkaTemplate.send("orders", event)` at 2.9 → descriptor `(Ljava/lang/String;Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` → `[]`; `single_call.py:485-528` compares verbatim; catalog measures 3.1.4 only; `COVERAGE.md:1655` states no scope and `:1670` names the `ListenableFuture`/`CompletableFuture` split one line below without connecting the two. **Whether spring-kafka 2.x is in scope is undetermined — see §7** | **CORRECT** (or state a version floor) | A1 C-4 |
| **G-14** | Critical | `spring-ws-template.yml` | Reads one JAXB spelling, so a pre-Jakarta Spring-WS module's outbound SOAP operations have **no identity**, and no row says so. Sharpened by the row two lines above advertising "both `jakarta.jws` and `javax.jws`" | `spring-ws-template.yml:93,144,155` name `jakarta.xml.bind.annotation.XmlRootElement`; `javax.xml.bind.annotation.XmlRootElement` occurs nowhere in `src/`; `path_from_argument_type.annotation` is a scalar (`single_call.py:58`) so there is no list to widen. Reproduced: javax spelling → `('soap','outbound', path=None, peer='http://…', 'unresolved', request_shape=None)`; jakarta → `path='{http://acme.example/orders}placeOrderRequest'`, `resolved`. Not in `open-issues.md`, the sweep, or `documented-not-implemented.md` | **CORRECT** | A1 C-5 |
| **G-15** | Major | `COVERAGE.md:836` vs `spring-actuator.yml:64-73` | The document and the catalog it documents classify the **same fact** oppositely. COVERAGE calls `management.endpoints.web.exposure.include` a "Stated dependency, **NOT an over-report**"; the catalog calls the identical fact a stated **OVER-REPORT** and cites this row as its authority. `:885`'s `doTrace` row leans on `:836` as precedent, so the disagreement propagates | input: a Boot module with `@Endpoint(id="probe")` and no exposure override → `GET /actuator/probe` at `resolved`/`compiler` for a URL Boot's default 404s (CP-5 rows 9-10) | **RESTATE** | A1 M-1 |
| **G-16** | Major | `spring-stomp.yml` | A **Spring RSocket** controller publishes `websocket <route>` rows. The catalog matches `org.springframework.messaging.handler.annotation.MessageMapping` under a `@Controller` gate — which is RSocket's own routing declaration — and `annotation_driven` is not dependency-gated, so nothing requires `spring-websocket` on the classpath. Wrong protocol, live. It is also the only place RSocket appears at all | `resolve/dependencies.py:91` `DEPENDENCY_GATED = {"derived_resource", "config_join"}`; `COVERAGE.md:1437-1444` calls the output **unverified** and "Raised, not closed"; the sweep carries it as A-C1's residual; **absent from `docs/open-issues.md`**; invisible in §2 because it is a bullet, not a row | **CORRECT** + **RESTATE** (promote to a row and to the register) | A1 M-2, F-1 |
| **G-17** | Major | `javax.websocket` | An entire spelling of an entire protocol derives nothing and has **no table row** — only a prose bullet. §5.1 gave the identical problem for servlets its own row *and* its own catalog (`javax-servlet.yml`). A pre-Jakarta module's whole WebSocket surface is absent from the export and from every count | `COVERAGE.md:1451-1456`; `jakarta-websocket.yml`'s `mapping.annotations: [jakarta.websocket.OnMessage]` and nothing else | **BUILD** | A1 M-3 |
| **G-18** | Major | `COVERAGE.md:1453-1454`, `:2422` | A benefit is claimed from `detect.coordinates` **twice**, and the key is not read for either catalog. §5.5: "`detect.coordinates` still names the javax artifact, so such a module is recognised as WebSocket-shaped" — nothing recognises anything. §9: the same unread key given as the reason the two `@SqsListener` generations are separate files (the split is correct; the stated reason is a mechanism that does not run) | `detect_coordinates` is read at exactly one site, `resolve/dependencies.py:135-145`, which returns `None` for any style outside `DEPENDENCY_GATED`; `jakarta-websocket.yml`, `spring-sqs.yml`, `spring-sqs-legacy.yml` are all `annotation_driven`. `docs/documented-not-implemented.md:30` states the same reach (4 of 55). The same sentence was corrected in GUIDELINES, `yaml_source.py` and `document.py::_GAPS`; COVERAGE was never swept | **RESTATE** | A1 M-3, F-5 |
| **G-19** | Major | `COVERAGE.md:283-306` | §2's operator-facing "What a run produces" stops at 2F/2I plus 2O **Task 7 only**, and omits six shipped protocols and two shipped tables: GraphQL, WebSocket/STOMP, SSE, gRPC, Servlets, Spring Data REST, the server-side `@HttpExchange` flip, `error_handlers`, `scheduled_work`, and the `channel_destination` questions | all named ✅ in §5.1/§5.4/§5.5/§5.6/§5.7/§5.12; `coverage_matrix.py --check` cannot see this — it regenerates the two matrices only | **RESTATE** | A1 M-4, F-3 |
| **G-20** | Major | `scripts/coverage_matrix.py` + §2b | **Pulsar has shipped as a protocol with no column.** `spring-pulsar.yml` declares `protocol: pulsar`; its four rows are filed under §5.9 "JMS and AMQP", and the script keys on the §5 heading, never on the catalog's declared protocol. A §2 reader cannot see Pulsar is supported, and Pulsar's gaps are attributed to JMS/AMQP — under a note ("SNS and Redis are out of scope … each would be a new column") that reads as if the column set were deliberate | rows `:1837`, `:1839`, `:1840`, `:1841`; `--check` has no view of `protocol:` | **CORRECT** (script) + **RESTATE** | A1 M-5, F-2 |
| **G-21** | Major | `spring-pubsub.yml` | The Spring Cloud GCP **1.x generation derives nothing**, and no row says so. `:1924` says "✅ shipped" and `:1934` says "Both generations are in the wild" and stops. §5.10 is the document's own model for how this should read — the two legacy SQS generations got a catalog **and** their own rows | `spring-pubsub.yml:17` matches `com.google.cloud.spring.pubsub.core.PubSubTemplate` only; `org.springframework.cloud.gcp.*` occurs nowhere in `src/` | **RESTATE** (+ **BUILD** if 1.x is in scope) | A1 M-7 |
| **G-22** | Major | `okhttp.yml:24-27` | An **unmeasured version is presented as measured**: the comment cites CP-11 for "okhttp 3.14.9 and 4.12.0"; CP-11 measured 4.12.0 alone and the file's own `measured:` block records `["4.12.0"]`. `3.14.9` appears nowhere else in the repository. Completeness of the verb-setter set is what keeps the root's `http_method: GET` honest — an uncovered setter leaves a confidently wrong verb at `resolved`/`compiler` | `cp11_sweep_round1.md:25,76,83`; `COVERAGE.md:1026` states "All eight verb-setting methods … (CP-11)" with no version. Neither provenance test reaches a free-text comment | **MEASURE** + **RESTATE** | A1 M-8 |
| **G-23** | Major | `COVERAGE.md:1926` | `.startAsync()` is named as if it were a conjunct of the Pub/Sub subscriber rule; it is **read nowhere** — the string occurs exactly once in the repository, in that row. A `Subscriber` built, wired to a `MessageReceiver` and never started is exported as a live inbound boundary | `google-pubsub-subscriber.yml:19-33` registers on `Subscriber.newBuilder` alone; `test_interface_engine.py:217` derives a `resolved` inbound row from facts containing no such call | **CORRECT** (row) — or BUILD the conjunct | A1 M-9 |
| **G-24** | Major | `COVERAGE.md:869` | The Maven boundary is **stale and contradicts `:367` of the same document**: it says "the POM parse records direct declarations only", so a module inheriting `spring-boot-starter-data-rest` from a company parent POM is described as SKIPPED. F1 shipped: the parent chain, parent `<dependencies>`, `<dependencyManagement>`, imported BOMs and `${…}` all resolve | `detect/maven.py:470-497`; `resolve/dependencies.py:101-109`; `COVERAGE.md:367` | **RESTATE** | A1 M-10 |
| **G-25** | Major | `COVERAGE.md:835` | The `resolved_config` citation is false — "only `config_join.py:528` and `derived_resource.py:578` read it" against **seven call sites in five files**, and both line numbers are stale as well. `A-Mi11` is recorded FIXED; its fix touched `derive_endpoints.sql` and `spring-actuator.yml` and left this copy | actual readers: `config_join.py:811`, `derived_resource.py:686`, `enrich/validate.py:192`, `enrich/brief.py:181,253`, `api.py:610,847`. The operative claim (`annotation_driven` is not among them) survives | **RESTATE** | A1 M-11 |
| **G-26** | Major | `COVERAGE.md:1559` | Cites `engines/schema_operations.py:164-197` for `_grpc_operation_row`, which is at **`:361-395`**; `:164-197` is the WSDL branch inside `run`. The sibling citation in the same sentence is byte-exact, which makes the wrong one harder to notice. This is the failure GUIDELINES §5.3 legislates against, inside the document that cites it | | **RESTATE** | A1 M-12 |
| **G-27** | Major | `COVERAGE.md:2255-2258`, `open-issues.md` OI-10 body | The measured-version counts are stale — 29/26 stated, **36/19** today — and the unmeasured set is **where the ✅ rows are**: every gRPC catalog (§5.7's four ✅ rows), three of four GraphQL catalogs, `spring-ws` and `wsdl-schema` (§5.3), `spring-advice` (§5.1's error-handling ✅ rows), `spring-cloud-openfeign` (§5.2's ✅ Feign row), `spring-cloud-stream` (§5.8's ✅ row). Under GUIDELINES §8.1 those ✅ rows rest on unmeasured framework rules, and nothing a reader of a ✅ can see says so | `grep -c '^measured:' src/sextant/catalogs/*.yml` → 36; `_NOT_MEASURED_YET` holds 19; OI-10's *title* already carries 19 while its body carries 29/26 | **RESTATE** + **MEASURE** | A1 M-13, F-8; A2 §0 |
| **G-28** | Major | `COVERAGE.md:1828` | Claims a form that does not ship and under-states the ones that do: the Library cell claims `JmsTemplate.send` under ✅ (no `send` row exists; `:1843` says so), and the Form cell names one declared overload where **four** ship | `spring-jms-template.yml:73-81` declares `(String,Object,MessagePostProcessor)`, `(String,Object)`, `(Destination,Object)`, `(Object)` | **CORRECT** | A1 M-14 |
| **G-29** | Major | Spring MVC functional routing | **No catalog at all** for `org.springframework.web.servlet.function`. A servlet-stack module that routes functionally derives **zero** inbound HTTP endpoints, and no `skipped` row says so because no catalog claims the surface. Structurally identical to the WebFlux DSL that §5.1 does ship | `RouterFunctions`, `RouterFunctions$Builder`, `RequestPredicates` present in `spring-webmvc` **6.2.15** (`unzip -Z1`); `grep -rl 'web.servlet.function' src/sextant/catalogs/` → nothing; every `owner:` in `spring-webflux-router.yml` names `…web.reactive.function.server.*` | **BUILD** | A1 M-6; A2 F-4 |
| **G-30** | Major | Spring Cloud Gateway | An entire inbound **and** outbound HTTP surface, and the commonest edge component in a Spring estate: `RouteLocatorBuilder.routes().route(...)` and `spring.cloud.gateway.routes[]`. The string `Gateway` occurs twice in COVERAGE, both times about gRPC-Gateway/NestJS | absent from `src/` and from §5. Scheduled in the roadmap's **2P** ("a live gateway analysis showed four `lb://` routes the tables cannot see") — so this is a named-but-unenumerated surface, not an unknown one | **BUILD** | A1 M-6 |
| **G-31** | Major | Kafka Streams | `StreamsBuilder.stream("topic")` / `.to("topic")`, `@EnableKafkaStreams` — a real Kafka inbound+outbound surface with the destination in a call literal, the easiest shape in §5.8. Absent entirely | nearest shipped analogue `KafkaConsumer.subscribe` ✅ | **BUILD** | A1 M-6 |
| **G-32** | Major | the WebSocket client direction | `@ClientEndpoint` + `WebSocketContainer.connectToServer`, Spring's `WebSocketClient`/`StandardWebSocketClient`, `WebSocketStompClient` appear nowhere in `docs/` or `src/`. §5.5's Java rows are 3 inbound, 0 outbound, with **no boundary saying the direction derives nothing** — unlike §5.2/§5.3/§5.8, each of which carries its client side explicitly. Compounding it, the catalog detects the wrong jar | measured: `jakarta.websocket:jakarta.websocket-api` **2.2.0** contains only `jakarta/websocket/server/**`; `@OnMessage`, `@OnOpen`, `@OnClose`, `@OnError`, `@ClientEndpoint` live in `jakarta.websocket-client-api` 2.2.0, which `detect.coordinates` does not name — so a pure WebSocket client module is not detected at all | **BUILD** | A1 M-6; A2 F-13 |
| **G-33** | Major | `SimpMessagingTemplate.convertAndSend` | The outbound STOMP push — the single commonest server→client STOMP call, the direct analogue of `KafkaTemplate.send` (shipped) and `RabbitTemplate.convertAndSend` (shipped) — **appears nowhere in the repository**. A STOMP service's outbound surface is silently absent | | **BUILD** | A1 M-6 |
| **G-34** | Major | programmatic Jakarta WebSocket registration | `ServerApplicationConfig` / `ServerEndpointConfig.Builder.create(Endpoint.class, "/path")` and `Endpoint` subclasses — the WebSocket analogue of servlets' `web.xml`/`addServlet` third registration route, which §5.1 **does** carry a boundary row for (`:882`) | | **BUILD** | A1 M-6 |
| **G-35** | Major | `@MessageExceptionHandler` | STOMP's error contract, absent from §5 entirely, while §5.1 ships `error_handlers` for the HTTP twin (`@ControllerAdvice` ✅) | | **BUILD** | A1 M-6 |
| **G-36** | Major | `spring-ws.yml` | `@PayloadRoot` and `@SoapAction` are `@Repeatable`, **Spring-WS reads the containers**, and the catalog names neither. By JLS 9.7.5 javac writes only the container, so a handler with two `@PayloadRoot`s carries no `@PayloadRoot` fact at all and **both** SOAP addresses vanish | measured, `spring-ws-core` **4.1.4**: `javap -v PayloadRoot` → `@Repeatable(PayloadRoots.class)`; `SoapAction` → `Repeatable(SoapActions.class)`; `PayloadRootAnnotationMethodEndpointMapping` → `ldc PayloadRoots; AnnotationUtils.findAnnotation; checkcast PayloadRoots; invokeinterface PayloadRoots.value:()[LPayloadRoot;`; same shape for `SoapActions`. `spring-ws.yml:91-97` declares two `mapping.annotations` and **no `container:`** — the key five other catalogs carry. `spring-ws` is on `_NOT_MEASURED_YET`, so nothing looked | **CORRECT** | A2 F-3 |
| **G-37** | Major | `spring-webflux-router.yml` | Misses the `RouterFunctions.route()` **builder** DSL — likely the majority of real functional routers, since it has been the reference documentation's recommended Java shape since Spring 5.2. Each derives nothing. The catalog's `measured:` block measured the verb *predicate set*, not the *entry points* — `A-Mi5`'s "measured in one direction only", in a catalog that reads as measured | measured, `spring-webflux` **6.1.6**: `RouterFunctions.route()` (no-arg) returns `RouterFunctions$Builder`, which declares four overloads each of `GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS` plus `path`, `nest`, `resources`, `before`/`after`/`filter`, `build`. The catalog's `matches.entries` names only `RouterFunctions.{route, nest}` with `handler_arg: 1`; `RouterFunctions$Builder` appears nowhere. **`COVERAGE.md:853` states this as a Boundary deriving NOTHING and pins it (`test_combinator_engine.py:2153`)** — so the row is honest; what is new is A2's sizing of it | **BUILD** | A2 F-5; A1 row 853 |
| **G-38** | Major — **WITHDRAWN at W17, measured false** | `spring-mvc.yml` | **The claim below was predicted from the catalog file, not run.** A WebFlux `@Controller` derives its routes and always did: `detect.coordinates` is read only by the two styles in `DEPENDENCY_GATED` and by catalogs setting `detect.required`, and `spring-mvc` is `annotation_driven` and sets neither, so the gate this row describes never existed. Compiled against the real jars and run through the real scanner and derivation, all four shapes named here derive identically in a `spring-webflux`-only build and a `spring-webmvc`-only one (`scripts/probes/w17_webflux_controller.md` section 3). What was true is the smaller half: the coordinate list named one stack while both serve `@Controller`, a false sentence that `detect.required` (W16) turned into a one-line trap — so the list was widened and a test pins it. *Original text:* A WebFlux `@Controller` derives nothing. WebFlux's handler gate is byte-for-byte identical to MVC's, but `spring-mvc.yml` carries the `@Controller` gate behind `detect.coordinates: [org.springframework:spring-webmvc]`, which a WebFlux module does not have, and `spring-web.yml`'s gate is the literal `@RestController`. So `@Controller` + `@ResponseBody`, or `@Controller` returning `Mono<String>`, matches neither catalog and its whole HTTP surface is absent, while the identical class in an MVC module derives normally | measured `protected boolean isHandler(Class<?>)`: `spring-webmvc` 6.1.6/6.2.15/7.0.2/7.0.9 → `aload_1; ldc Controller.class; invokestatic AnnotatedElementUtils.hasAnnotation; ireturn`; **`spring-webflux` 6.1.6/7.0.2 byte-for-byte the same**. No catalog or probe document in the tree records the WebFlux row | **BUILD** (a webflux-coordinate catalog, or widened coordinates) | A2 F-6 |
| **G-39** | Major | `netflix-dgs.yml` | `@DgsData` is `@Repeatable(DgsData$List)` and the catalog declares no `container:`, so **two `@DgsData` on one method drop both**. `@DgsQuery`/`@DgsMutation`/`@DgsSubscription` are meta-annotated `@DgsData` with `@AliasFor`, read through `MergedAnnotations`, so the catalog's own "KNOWN LIMITATION" note about `@DgsData(parentType="Query")` is a real divergence | measured, `graphql-dgs` **8.7.1**: `javap -v DgsData` → `@Target({METHOD, ANNOTATION_TYPE})`, `@Repeatable(DgsData$List.class)`, `@Inherited`; `DgsSchemaProvider:1275` `MergedAnnotations.stream(Class)`. `netflix-dgs` is on `_NOT_MEASURED_YET` | **CORRECT** | A2 F-7 |
| **G-40** | Major | `netflix-dgs.yml` | `@DgsEntityFetcher` — Apollo Federation's `_entities` registration path, a separate `DgsSchemaProvider.findEntityFetchers(...)` — is **named by no catalog**. The `@PulsarReader` shape (`OI-39`) in a second framework | the jar declares it at 8.7.1 | **BUILD** | A2 F-7 |
| **G-41** | Major | `netflix-dgs.yml` | `@DgsData` and `@DgsQuery` are `@Inherited`, so a fetcher inherited from a superclass method registers and we do not see it — the `OI-37` shape in a third framework | `javap -v` at 8.7.1 shows `@Inherited` on both | **BUILD** | A2 F-7 |
| **G-42** | Major | `spring-websocket.yml` | Names the **raw handler registry** and not the STOMP endpoint registry. `registry.addEndpoint("/ws")` is the URL clients actually connect to, and it is named by no catalog — so a STOMP module's `@MessageMapping` destinations derive while the transport endpoint they arrive on does not exist in the export | the catalog's whole `matches` is `WebSocketHandlerRegistry.addHandler(WebSocketHandler, String...)`, `channel_arg: 1`. Measured, `spring-websocket` **6.1.6**: `…config.annotation.StompEndpointRegistry` declares `StompWebSocketEndpointRegistration addEndpoint(String...)` | **BUILD** | A2 F-8 |
| **G-43** | Major | `aws-sqs-sdk.yml` | Models one request type in one direction. Missing: `SqsAsyncClient` as a second terminal owner, `SendMessageBatchRequest`, and the **entire inbound direction** (`ReceiveMessageRequest` → `SqsClient.receiveMessage`). An SDK-level SQS consumer is invisible | the catalog's entire `matches`: root `SendMessageRequest.builder()`, steps `queueUrl`/`messageBody`, terminal `build` via `SqsClient.sendMessage`. The jars are local (`software.amazon.awssdk:sqs` 2.21.46 and 2.25.31) — **A2 did not enumerate them**, so the missing set is stated from the API surface, not measured | **BUILD** (+ **MEASURE**) | A2 F-9 |
| **G-44** | Major | `spring-jms-template`, `spring-rabbit-template`, `spring-sqs-template`, `spring-pubsub` | The four template catalogs **model the send half only**. Each missing row is a receive-side boundary a module really has: `send(String, MessageCreator)`/`receive`/`receiveSelected`/`receiveAndConvert`/`sendAndReceive`/`convertSendAndReceive`; `send`/`receive`/`receiveAndConvert`/`sendAndReceive`/`convertSendAndReceive`; `sendAsync`/`receive`/`receiveAsync`/`receiveMany`; `subscribe`/`pull`/`pullAndConvert`/`publish(String, T, Map)` | read off each catalog's own `matches.methods`. `spring-jms-template` and `spring-rabbit-template` carry a stated under-report (`COVERAGE.md:1491`); **the other two do not**. This is the converse question CP-10's descriptor probe never asks (`A-Mi5`) | **BUILD** | A2 F-10 |
| **G-45** | Major | `spring-data-rest.yml` | The repository roster is **JPA-only**. `MongoRepository`, `R2dbcRepository`, `ReactiveCrudRepository`, `CoroutineCrudRepository`, `CassandraRepository`, `ElasticsearchRepository`, `Neo4jRepository` are all absent, and they reach `ListCrudRepository` only through a *jar* hop the fact stream does not carry (D02 §7) — so a Mongo/R2DBC Spring Data REST module very likely derives nothing | read from the catalog's `matches.repositories`. **The exact shape of the drop is a prediction** — A2 did not open `spring-data-mongodb` to confirm which base each store module extends | **BUILD** + **MEASURE** | A2 F-11 |
| **G-46** | Major | `spring-data-rest.yml` | `matches.routes[0]` is `{method: GET, item: false}` with **no `needs:`**, while `repositories["…repository.Repository"]` declares no capabilities. A bare `interface Foo extends Repository<Foo, Long>` declares no `findAll` and Spring Data REST exposes no collection GET for it — but the table appears to publish one. **Unverified: A2 read the catalog, not a run. If the engine really mints it this is a Critical, not a Major** — the highest-value single thing to run in the spec pass | | **MEASURE** | A2 F-11 |
| **G-47** | Major | `spring-integration.yml` | Reads **2 of ~12** channel-declaring annotations and no containers. Severity capped at Major-low because this catalog mints no endpoint rows — it files `channel_destination` questions — so the cost is an under-reported question list, not a wrong row | enumerated, `spring-integration-core` **6.2.4**, `org.springframework.integration.annotation`: 35 types, channel-declaring endpoints `ServiceActivator`, `InboundChannelAdapter`, `Router`, `Splitter`, `Transformer`, `Filter`, `Aggregator`, `BridgeFrom`, `BridgeTo`, `Publisher`, `MessagingGateway`/`Gateway`, plus nine repeatable containers. Catalog names `ServiceActivator` and `InboundChannelAdapter` | **BUILD** | A2 F-12 |
| **G-48** | Major | `resolve/return_flow.py` | The same defect as G-1 costs `return_flows` its in-module accessor links, and it has its **own COVERAGE row** that will need its own correction. Every one of the 28 is an accessor inherited from `BaseEntity`/`Person`/`NamedEntity` — precisely the values a reader follows to see what a response is built from | measured on spring-petclinic: 214 value-producing non-dynamic call sites, 176 with no candidate, **28 recoverable by JVMS resolution**, against **45** `return_flows` rows actually recorded; `COVERAGE.md:2130-2140` | **CORRECT** (rides G-1) | A3 M-1 |
| **G-49** | Major | `single_call.py:456-459`, `fluent.py:471-474`, `derive_call_endpoints.sql` | None of the three dedup keys includes `peer`, so **two calls to one path on two different hosts keep one and the loser is deleted** with no row, no `open_questions` entry and no `SkippedCatalog`. The rule is half-stated and the stated half has the tie-break wrong | `dbg_two_peers.py` through shipped `spring-resttemplate.yml`: two `getForObject` sites, `payments.internal` and `billing.internal` → **1 row**, `peer = billing.internal`. `COVERAGE.md:1264` carries the rule inside the **JAX-WS/SOAP** bullet list although it reaches every HTTP and messaging client catalog, and says the surviving address is "whichever call was read first" — actually the **alphabetically lowest caller symbol** (`workspace.py:76` `ORDER BY caller, ordinal`) | **CORRECT** + **RESTATE** | A3 M-2 |
| **G-50** | Major | `egress/render/document.py::_sequence_view` | A `narrowed` step is drawn as **N sequential arrows** and the diagram never reads `step.resolution`. A reader sees `Ctl` calling `ImplA` and then calling `ImplB`; the truth is one call reaching exactly one of them. The `Elides:` line — the place the renderer states what a reader could be misled by — says "nothing is filtered" | `_sequence_view:1602-1652`, `_message_label:1687-1716` reads `target`/`invoke_kind`/`stop` only; `grep -n narrowed document.py` → one hit, an unrelated docstring; `_GAPS` at `:1255-1282` does not name it though `trace.py`'s docstring states the rule correctly and the step TABLE renders the column. **Fires on the project's own fixture**: `record_call_edges` over `fixtures/orders-service/target/classes` produces two narrowed edges from one call site | **CORRECT** | A3 M-3 |
| **G-51** | Major | `single_call.py:109/:206`, `fluent.py:128/:605` | `matches.owner` is **one string compared with `==`**, so a call through an interface or a second spelling matches nothing. The grammar cannot say "or any supertype of this" and cannot say "or this second spelling" — and for a third-party owner the module never scanned, no widening is derivable from facts at all, so **only the catalog can name the alternatives and the grammar refuses to let it**. A field declared `RestOperations` rather than `RestTemplate` is a whole outbound surface deriving nothing, with no skip reported | mechanism read off the two lines. **The live consequence is unverified** — no Spring bytecode in this tree to compile a `RestOperations`-typed field against | **CORRECT** (engine vocabulary) | A3 M-4, VG-1/2/22 |
| **G-52** | Major | `extractor-jvm/MethodFlow` | `ATHROW` is handled nowhere, so `invoke_kind: throw` — documented in D00 §5's own table and deferred to explicitly at `MethodFlow.java:136-140` — is **never produced**, and D00 §4's `terminal_kind: throws` is unreachable. Every trace through a method that throws ends silently rather than at a `throws` terminal | measured: a method with two `athrow` emits two `call_site`s for the exception **constructors** and no `method_return` and no throw fact — its exit is unrecorded | **BUILD** | A4 F3 |
| **G-53** | Major | `extractor-jvm/ClassScanner.java` | `InnerClasses` and `EnclosingMethod` unread (`visitInnerClass`/`visitOuterClass` not overridden), so **no nested type is linked to its enclosing type**; static-vs-inner is lost and the nested class's own source-declared access flags are lost. Downstream the only substitute is `domain/symbols.outer_type_of`, which splits on `$` — a string heuristic standing in for an attribute the class file states outright, and wrong for any language permitting `$` in identifiers (Kotlin, Scala) | measured: `Shapes$Nested`, `Shapes$Inner`, `Shapes$1`, `Shapes$1Local` all `encl=None` | **BUILD** | A4 F4 |
| **G-54** | Major | `extractor-jvm/MethodFlow` | `StringConcatFactory`'s recipe and constant arguments are dropped, so the **literal half of every runtime concatenation vanishes** — the exact shape D00 §5's `constant` kind names ("Topic and URL resolution"). `lambdaSymbol` gates on `LambdaMetafactory` and returns null for everything else, though the recipe is in the same `BootstrapMethods` table 9.17 already reads | measured: `"bad " + x` → the message argument emits `{"kind":"unresolved","source":7}`; `"orders." + System.getenv("ENV")` the same. Declared unshipped as `constant_propagation` in M03/COVERAGE §2 — **a stated boundary, but stated as a capability rather than as a row naming the shape** | **BUILD** | A4 F5 |
| **G-55** | Major | `extractor-jvm/ClassScanner.signatureJson` | Method and constructor **parameter types are erased while return types are not**. The `Signature` attribute carries both; `:527` builds parameters from `Type.getArgumentTypes(descriptor)` and `:539` builds the return from `TypeRefs.returnFromSignature`. Adjacent, same attribute: class and method **formal type parameters and their bounds** are never read | measured: `Map<String,List<T>> grouped(List<T>, Map<String,T>)` → params `java/util/List#`, `java/util/Map#` with **0 arguments**, return `java/util/Map#` with 2. `TypeRefs.fieldRef`'s own docstring states the rule this violates. Cost: every request-body contract derived from a parameter type is rooted one level too shallow, and **DR-5 compares `List` against `List` and matches when the elements differ** | **CORRECT** | A4 F6 |
| **G-56** | Major | `extractor-jvm` | `ConstantValue` is handed to `visitField` and discarded (`ClassScanner.java:287`), and `MethodFlow.fieldWrites` gates on `"<init>"` and matches only `PUTFIELD`, so `<clinit>` is invisible. **D00 §5's `constant` fact kind therefore has no producer.** The only thing that works is javac's own inlining, which happens for compile-time constants of primitive or `String` type within the compiling module only | measured: `TOPIC`, `QUEUES`, `BASE` emit three `field` symbols with **no value on any**; for `QUEUES` the `<clinit>` call site captures `List#of ["q1","q2"]` but nothing says the result is assigned to the field | **BUILD** | A4 F7 |
| **G-57** | Major | `extractor-jvm/ClassScanner.java` | `visitRecordComponent` not overridden, so a `@Target(RECORD_COMPONENT)` annotation is emitted **nowhere**, and `construct_kind` is `class` though D00 §4's closed set declares `record` | measured: `record RC(@Wire(name="order_id") @Any(v="both") String id)` → `@Any` (untargeted) appears three times via javac's replication; **`@Wire` appears zero times**. Records are the modern spelling of a DTO, which is the shape this project exists to read | **BUILD** | A4 F8 |
| **G-58** | Major | `docs/COVERAGE.md` §2 + `scripts/coverage_matrix.py` | **53 stated boundaries are structurally unrepresentable in §2** (`classify()` returns `None` for `Boundary — …`), so every Java cell reads `◐` plus a tier spread counting **only unbuilt libraries**, never known-wrong or known-narrow behaviour of what shipped. §2's own "Reading the matrices" prose explains `◐ —` as coverage news and does not say a cell may carry a dozen stated over-reports. **Four more rows are dropped by `ALIASES`, two of them shipped capabilities** | WebSocket (`◐ —`, 8 boundary bullets) and SOAP (`◐ —`, ~20) are the worst. Dropped by `ALIASES`: `:1169` WSDL/XSD documents (**✅ shipped**, `ingress/read/wsdl_xsd.py`), `:1624` `.proto`/`FileDescriptorSet` (**✅ shipped**, `ingress/interpret/protobuf.py`), `:1139` and `:2014` labelled `Any`. **A1 did not rank this; filed Major here — see §3.1** | **CORRECT** (instrument) | A1 F-4 |
| **G-59** | Major | `extractor-jvm/Main.java` | `SourceFile` is unread: `sourcePathOf` reconstructs the name and hardcodes `.java` (`:250-262`), and `writeFactFile` writes `"language": "java"` unconditionally (`:173`). **Both of D00 §2's definitions are false for every Kotlin document**, silently, and the scanner already decodes `@Metadata` so it already knows the language | measured on the repo's own Kotlin fixture: `DOC lang=java rel=com/acme/orders/contracts/KotlinOrder.java` against `javap`'s `SourceFile: "KotlinOrder.kt"` | **CORRECT** | A4 F9 |
| **G-60** | Major | `extractor-jvm/ClassScanner.java` | `AnnotationDefault` unread, so an omitted annotation element has **no value**, and every catalog needing a framework annotation's default must hardcode it as a prediction — which GUIDELINES §8.1 forbids, while the measurement sits in the annotation's own class file | measured: `@interface Trigger { String value(); String group() default "default-group"; int retries() default 3; Class<?> handler() default Object.class; }` emits four `method` symbols and **no default for any**; a use site `@Trigger(value="c", retries=9)` gives a consumer no way to learn `group` | **BUILD** | A4 F10 |
| **G-61** | Major | `extractor-jvm/ClassScanner.java` | `module-info.class` becomes a **fabricated `class` symbol** — a claim known to be false entering the symbol graph. `visitModule` not overridden, `ACC_MODULE` not tested, though D00 §4's construct-kind set has `module`. Also lost: `ModuleMainClass`, which names the program entry point D00 §4's producerless `entry_point` root kind (`OI-22`) is waiting for | measured: `{"construct_kind":"class", …"symbol":"… module-info#"…}`; fires again inside multi-release jars (`commons-codec-1.16.1.jar` → `META-INF/versions/9/module-info.jsonl`) | **CORRECT** | A4 F11 |
| **G-62** | Major | `extractor-jvm/Main.JarSource` | **Multi-release jars emit every overlaid class twice under one symbol.** `names()` filters on `.endswith(".class")` and never reads the manifest's `Multi-Release` attribute or recognises `META-INF/versions/N/`. Both copies mint the same symbol string with different `document_id`s and different bodies, and nothing marks either as an overlay | measured on `byte-buddy-agent-1.17.8.jar`: **72 of 73** type symbols emitted from more than one document; `byte-buddy-1.17.8.jar` duplicates **2 970** classes. **281 of 1 792** local jars are multi-release. `relative_path` also names a source file that cannot exist | **CORRECT** | A4 F12 |
| **G-63** | Major | `extractor-jvm/TypeRefs` + `ClassScanner` | Kotlin nullability is applied to **fields only**; a property getter's return and a constructor parameter keep `nullable: true` with `nullable_resolution: "resolved"` **beside an `@NotNull` in the same fact**. The fact does not merely under-report — it stamps a certainty marker on a value contradicted by evidence it carries | measured on `data class KotlinOrder(val id: String, val note: String?)`: field `id` `{"kotlin":{"nullable":false}}` correct; `getId()` returns `nullable:true, nullable_resolution:"resolved"`; `<init>` param 0 the same, carrying `org/jetbrains/annotations/NotNull#`. `TypeRefs.toJson`'s comment argues `resolved` is always right "because Java's type system settles nullability outright" — true for Java, false for the Kotlin half the same file reads | **CORRECT** | A4 F13 |
| **G-64** | Major | Kotlin, as committed scope | Kotlin is committed v1 scope with **0 of 170 §5 rows**, and `ALIASES` maps `Kotlin → ["Java / Kotlin"]` so §2a/§2b render Kotlin's tier spread from **Java's evidence**. Every Kotlin behaviour that is not Java's is invisible to every count the project quotes | `REQUIREMENTS.md:14`; `scripts/coverage_matrix.py:38-40`; verified absent from catalogs, `src/` and COVERAGE alike: `kotlinx.serialization`/`@Serializable` (0/0/0), `suspend`/`Continuation` (0/1/0), `value class`, `data class` (0/0/0). Only `coRouter` (2E) and `@Metadata` nullability (2A) are Kotlin-specific and shipped, and both live in prose, never as a tickable row | **BUILD** + **RESTATE** | A5 F-M1, D12; A1 §0 |
| **G-65** | Major | `docs/meridian-integration.md` | **Four committed requirements live only in an untracked file.** `roadmap.md:57` rules FR-21..FR-24 into 2P and names this file as the statement of record; `git log -- docs/meridian-integration.md` is empty. `grep "FR-2[1-9]" docs/REQUIREMENTS.md` → 0, while REQUIREMENTS' traceability table asserts it is complete in both directions. One `git clean` deletes the statement of record for a requirement set an outside consumer is waiting on | | **RESTATE** (commit the file, or fold FR-21..24 into REQUIREMENTS) | A5 F-M2, D6 |
| **G-66** | Major | `shape-models/json.yml` | A paginated handler publishes `Page#` — a type with no field facts — as its response contract. It degrades *visibly* (an open shape in Known gaps), so this is under-report rather than fabrication, but the most common paginated Spring response has no contract and **no COVERAGE row states it**. **The cause first recorded here was wrong** and so was the remedy it implied: these types are not undeclared *wrappers*, they are types whose wire contract is in their ACCESSORS. `Page` and `Slice` are interfaces and declare no fields, and expansion read fields only. A `wrappers` entry means the type vanishes on the wire, which is true of `ResponseEntity` and false of `Page` — Spring sends `{content: [...], totalElements: ...}`, and its own `PagedModel<T>` (spring-data-commons 3.5) is `{content: List<T>, metadata}`. Rooting through `Page` would have published the element type as the response body, trading this visible under-report for a fabrication | measured W26: with the jar in reach, `Page<OrderView>` gained 11 fields with `content` an array of `OrderView`; `javap` on spring-data-commons 3.2.5 shows `Slice` declaring `getContent`/`getNumber`/`getSize` and no field | **BUILT** (W26) | A5 F-M3a |
| **G-67** | Major | `resolve/shapes` | **No type-parameter substitution**, so a generic envelope loses its payload: `Result<T>`/`ApiResponse<T>`/`CommonResult<T>` — the dominant Spring REST envelope — declares `T data`, which erases to `Object`, so the payload becomes `java/lang/Object#`, an open shape. Capability 9.14 reads a parameterized *superinterface*; nothing resolves a type variable at a **field** | `COVERAGE.md:868` states the same limit for the Data REST case only. **Mechanism verified; the end-to-end effect is unverified** — no shipped fixture contains a generic envelope, and `macrozheng/mall`, which uses `CommonResult<T>` on essentially every controller, is not built in this tree. **Measure before the spec commits a size** | **BUILD** + **MEASURE** | A5 F-M3b |
| **G-68** | Major | FR-17 clause 3 | "The distribution of call sites across the resolution values" is unbuilt and named in **exactly one line of the tree** — the requirement itself. `coverage` is `{documents, partial_documents}`; `call_edges.resolution` exists, so the aggregate is a `GROUP BY` away and nobody is asking for it | `grep -rn "distribution of call sites" docs/` → `REQUIREMENTS:272` only; `workspace.py:343-347`; `schema.sql:461` | **BUILD** | A5 F-M4, D13 |
| **G-69** | Major | `docs/COVERAGE.md:361` | Two gap names **retired in code by name** are still published as current gaps: the document says the product cannot do a thing the product's own gap catalogue stopped claiming | `egress/render/metadata.py:24-25` retires `sequence_diagrams_pending_call_graph` and `call_graph_not_implemented` and explains that keeping them "would be the catalog lying in the opposite direction from usual" | **RESTATE** | A5 F-M5, D4 |
| **G-70** | Major | D06 | D06 describes a bundle that **cannot be produced** and is missing a promised field. §3's example `contents.tables` names `edges`, `dispatch`, `trace_summary`; §5 adds `deployments`; none exists in `schema.sql`. §3's per-document `redaction_set_hash` has no column — actual columns are `document_id, relative_path, module_id, language, origin_tier, origin, partial` (`schema.sql:467`), so a consumer following D06's cache-validity instruction finds nothing | sweep `B-C5`/`B-M7` found the first half (`principles-sweep:1206, 1220`); **D06 itself was never corrected**, and the second half is new | **RESTATE** | A5 F-M7, D9, D10 |
| **G-71** | Major | FR-9 · FR-10 · M00 | Blast radius has **no surface at all** (`grep -r "blast\|impact_of" src/` → 0) and the query surface is **1 of D01 §5's ten** named queries (`trace_of`/`traces_of`); the command surface is **4 of M00's 25** verbs. Major rather than Critical only because register #11 tracks it — but its disposition is "the documentation-debt checkpoint's call", i.e. retire-or-build is undecided for a v1 requirement | | **BUILD** or explicit descope | A5 F-M8 |
| **G-72** | Moderate | `extractor-jvm/ClassScanner.java:648-649` | `line_start`/`line_end` are hardcoded `"0"` while `LineNumberTable` is present in ordinary javac output (10 entries in the `Flow` probe) and already recorded in the `MethodNode`. D00 §5 says a `symbol` carries a **range**; every range in the estate is `0..0`, and both producerless kinds `occurrence` and `string_literal` are blocked on it | | **BUILD** | A4 F14 |
| **G-73** | Moderate | `extractor-jvm` access flags | `visibility` is two-valued (`public` / `"other"`) for a four-valued language concept, and `ACC_ABSTRACT`, `ACC_FINAL`, `ACC_VARARGS`, `ACC_SYNCHRONIZED`, `ACC_NATIVE`, `ACC_VOLATILE`, `ACC_STRICT`, `ACC_ANNOTATION`, `ACC_RECORD`, `ACC_SEALED` and field-`ACC_ENUM` are all dropped | measured: `private`, `protected` and package-private methods are **byte-identical**; an interface's `default` and `abstract` methods are byte-identical; `MethodFlow.java:578` names `ACC_VARARGS` as the reason 9.15 cannot tell a varargs call from `new String[]{…}` while the flag sits on the method being visited; an `@interface` is emitted as `construct_kind: "interface"` | **BUILD** | A4 F15 |
| **G-74** | Moderate | `extractor-jvm/ClassScanner.java:205` | The `Exceptions` attribute (the declared `throws` clause) is forwarded into the `MethodNode` and never read. It is part of a method's contract in the JLS and is one line from being a fact | | **BUILD** | A4 F16 |
| **G-75** | Minor | `derive_endpoints.sql:1222` | The addresses-nothing gate is **structurally off for any catalog declaring `$path_prefix`**: the gate is `WHERE NOT (d.path = '' AND d.peer IS NULL)` and a constant prefix composes to something that is never `''`. The gate's reasoning ("whether anything in the row names an endpoint at all") is defeated by a constant prefix, and the next catalog to declare one inherits the hole | reproduced (`bare_annotation_probe.py`): `spring-actuator`, given its type gate with no arguments and its first mapping annotation with no arguments, publishes **`GET /actuator`** at `resolved`/`compiler`. Minor because the shape needs an `@Endpoint` whose id never reached the bytecode, which Spring Boot itself refuses at startup — **that last clause is unverified**. The file names the right home for the fix: beside `serves_urls` in `domain/paths.py` | **CORRECT** | A3 Mi-1, VG-28 |
| **G-76** | Minor (latent) | `derive_endpoints.sql:1222` | With `d.path` SQL NULL, `NOT (NULL AND TRUE)` is NULL and `WHERE NULL` **excludes** the row — a silent drop rather than the `''` case's deliberate one. The file asserts this cannot happen and the assertion is true today and **undefended**; A3 could not construct a reachable NULL (it needs a NULL inside an annotation's `value` array, which Java annotations cannot express) | | **CORRECT** (defend the assertion) | A3 Mi-2 |
| **G-77** | Minor (inert today) | `combinator.py:263` | Two scanned coordinates declaring one bare descriptor pick a winner silently via `setdefault` — deterministic and commented, unstated in output. `dispatch._bodies_by_descriptor` keeps both, which is the right answer. Inert while one module is scanned at a time; **live with `extract_libraries` or a bundle** | | **CORRECT** | A3 Mi-3 |
| **G-78** | Minor | `extractor-jvm` | Class-level `RuntimeVisible/InvisibleTypeAnnotations` are dropped — `ClassVisitor.visitTypeAnnotation` not overridden, so `CLASS_EXTENDS`, `CLASS_IMPLEMENTS` and `CLASS_TYPE_PARAMETER` produce nothing | measured: `class GenericBox<…> extends Base<@Nn T>` has `RuntimeVisibleTypeAnnotations: 0: CLASS_EXTENDS, location=[TYPE_ARGUMENT(0)]` and emits no `annotation` fact. (Bounds/receiver/throws targets are refused *with a stated reason* at `ClassScanner.java:246-250` — correct) | **BUILD** | A4 F17 |
| **G-79** | Minor | `extractor-jvm/JsonOut.java:20-21` | Escapes only `< 0x20`, so a constant-pool modified-UTF-8 string decoding to an unpaired surrogate is replaced with `?` by `String.getBytes("UTF-8")` — silent single-character corruption. **Unverified** — A4 did not build a class file with an unpaired surrogate | | **CORRECT** | A4 F18 |
| **G-80** | Minor | `extractor-jvm` | `PermittedSubclasses` dropped: `sealed interface Sealed permits Impl1, Impl2` produces nothing naming either, so the closed-world claim — the thing that makes a sealed type worth declaring — is gone | | **BUILD** | A4 §2a |
| **G-81** | Minor | `extractor-jvm` | `NestHost` and `NestMembers` dropped; no nest relationship is recorded | | **BUILD** | A4 §2a |
| **G-82** | Minor | `extractor-jvm` | `LocalVariableTable` and `LocalVariableTypeTable` unread — the fallback for parameter names when `MethodParameters` is absent. Maven and Gradle both default to `-g`, so this table is present in most real builds and is never opened | | **BUILD** | A4 §2a |
| **G-83** | Minor | `extractor-jvm` | Unknown/vendor attributes pass unseen and unlogged (`visitAttribute` not overridden — a Scala `ScalaSig` or a Kotlin `SourceDebugExtension`), and the `minor_version` preview flag `0xFFFF` is ignored, so a preview-feature class file is accepted and scanned as if final. `Deprecated` (the attribute javac writes for a `@deprecated` javadoc with no annotation) is also dropped | | **BUILD** | A4 §2a |
| **G-84** | Minor | `extractor-jvm/Main.java:207-208` | `partial` / `partial_reason` are always `false` / `null` and **no code path anywhere sets either**, so D00 §2's "True when the file was analysed incompletely" can never fire — including in G-3's whole-scan-fatal case, where a partial document is exactly the honest answer | also always-literal: `nullable_resolution: "resolved"` (`TypeRefs.java:202`), `line_start`/`line_end` `"0"` (G-72), and `wire_format` `""` for every non-numeric type (a legitimate "not applicable", indistinguishable from unread) | **BUILD** | A4 §4 |
| **G-85** | Minor | `spring-restclient.yml` | The terminal list is version-mixed and says so nowhere: `RestClient$RequestHeadersSpec` declares `retrieve` + `exchange` at spring-web **6.1.6** and adds **`exchangeForRequiredValue`** at **7.0.2**; the catalog declares all three with no note. Dead data at 6.1.6, not a wrong row — but `spring-webclient.yml` states exactly this situation in a long comment for its own `exchange`, and this file's silence is the inconsistency | | **RESTATE** | A2 F-14 |
| **G-86** | Minor | `spring-webflux-router.yml` | Reads **1 of ~40** `MediaType` constants (`APPLICATION_JSON`) and declares no `RequestPredicates.method(HttpMethod)` / `methods(HttpMethod...)`, both present at 6.1.6 and 7.0.2 — so those routes **vanish rather than arriving unresolved**, where `spring-webclient.yml` handles the analogous unreadable-enum case with `http_method: arg0` + `unresolved`. (The seven named verb predicates ARE the framework's complete verb set — no `TRACE` predicate exists — that half is confirmed complete) | | **BUILD** | A2 F-15 |
| **G-87** | Minor | `jakarta-jms.yml` | Models **12 of `Session`'s 14** destination-taking factories; `createBrowser(Queue)` and `createBrowser(Queue, String)` are absent. Whether a `QueueBrowser` is an endpoint is a judgement, and the file states no judgement. (`A-M7` is otherwise closed — the 11 consumer factories and the producer are all there with full descriptors) | measured, `jakarta.jms:jakarta.jms-api` 3.1.0. Note the exclusion **is** pinned as deliberate at `test_sweep_round1b_framework_surfaces.py:320-345` and `test_call_engines.py:7569` — what is missing is the stated judgement in the catalog | **RESTATE** | A2 F-16 |
| **G-88** | Minor | `spring-kafka-media.yml` | The eight Confluent rows are **unverifiable and asymmetric**: no `io.confluent` artifact resolves in `~/.m2` or the Gradle cache, so the four serializer/deserializer pairs are unverified; and `values:` (media) holds 6 rows while `format_from:` holds 14 — the eight Confluent classes get a format and no media, which nothing in the file explains. On `_NOT_MEASURED_YET` | | **MEASURE** | A2 F-17 |
| **G-89** | Minor | `okhttp.yml` | `terminal_via_argument.owner` is the concrete class `okhttp3.OkHttpClient`; OkHttp's own abstraction is `okhttp3.Call$Factory`, which `OkHttpClient` implements, so a field or parameter declared as `Call.Factory` — the testable, idiomatic injection — matches nothing. **Unverified against the fact stream's receiver-type resolution.** An instance of G-51 | | **CORRECT** | A2 F-18 |
| **G-90** | Minor | `spring-kafka-message.yml` | Declares only `MessageBuilder.setHeader`; `setHeaderIfAbsent`, `copyHeaders`, `copyHeadersIfAbsent` and the `fromMessage` root are absent. (The `kafka_topic` literal **is** correct: measured `KafkaHeaders.TOPIC = "kafka_topic"` at spring-kafka 3.1.4) | | **BUILD** | A2 F-19 |
| **G-91** | Minor | `grpc-spring.yml`, `grpc-net-devh.yml` | Name FQNs that **cannot be opened here**: neither `net.devh:*` nor `org.springframework.grpc:*` resolves in either local repo, so `org.springframework.grpc.server.service.GrpcService` and `net.devh.boot.grpc.client.inject.GrpcClient` are unverified and A2's belief that both spellings are right is a **prediction**. Both are `MEASURE` rows today | | **MEASURE** | A2 F-20 |
| **G-92** | Minor | `microprofile-graphql.yml` | The subscription boundary is unstated: Query+Mutation is the complete MP GraphQL root set (there is no `@Subscription` in the MP API), but SmallRye adds `io.smallrye.graphql.api.Subscription` **outside that artifact** and the file does not say so. `@Source` (a field resolver on a non-root type) is also unmodelled | enumerated: `org.eclipse.microprofile.graphql` declares 16 annotations; the catalog names `GraphQLApi`, `Query`, `Mutation`, `Name` plus the three `Jsonb`/`Json` name sources `OI-35` added | **RESTATE** + **BUILD** | A2 F-21 |
| **G-93** | Minor | `spring-actuator.yml` | The missing registration annotations are already a stated boundary (`COVERAGE.md:839`) — recorded here so the spec can size it: the jar declares `@WebEndpoint`, `@ControllerEndpoint`, `@RestControllerEndpoint`, `@ServletEndpoint`, `@EndpointWebExtension` at both 3.5.10 and 4.1.1, and `@JmxEndpoint` at 3.5.10 (gone at 4.1.1). Separately, the **`@Selector` path segment** (`/actuator/health/{component}`) is modelled nowhere and A2 found no statement of it | parameter annotations live in `Signature.parameters[].annotations` (`domain/facts.py:52-56`), invisible to the `annotations` view (`workspace.py:69-71`) — which is why `@Selector` is not merely uncatalogued. **What a `@Selector` parameter does to the served path is unverified** (CP-5 may answer it) | **BUILD** | A2 F-22; A1 row 838 |
| **G-94** | Minor | `COVERAGE.md:886` + `javax-servlet.yml:16-20` | The CP-9 count is stale and **under-states its own evidence**: "all **33** rows … (rows 25-28 and 30)" where CP-9 now measures **46** rows on all three columns, package-bearing rows "25-28, 30 and 44-46". Rows `:890`/`:891` two lines below already cite 41-46 | `cp9_servlet_shapes.md:163-168` | **RESTATE** | A1 Minor |
| **G-95** | Minor | `COVERAGE.md:899` | Overstates its own test: "asserts it against **EVERY** shipped catalog at once" — measured, **51 of 55 run and 4 SKIP** on the dependency gate (`spring-cloud-stream`, `spring-data-rest`, `spring-integration`, `spring-kafka-media`) because that workspace records no coordinates. No under-report risk; the sentence claims a property the test lacks | `test_endpoints.py:5556`; `resolve/dependencies.py:143` | **RESTATE** | A1 Minor |
| **G-96** | Minor | `COVERAGE.md:866` | "`crud_methods`, **25** bare identifiers" — `spring-data-rest.yml` declares **20**. Miscounted in the sweep (`principles-sweep:1007`, `:2000`) and copied here. The behaviour claim and `A-M14`'s OPEN status are unaffected | exclusion at `derived_resource.py:620` | **CORRECT** | A1 Minor |
| **G-97** | Minor | `COVERAGE.md:1844` + three code sites + GUIDELINES §10 | A stale citation propagated to four places: the call-site descriptor projection is at **`schema.sql:547`**, not the cited `:243` (now an unrelated `scope JSON` column). Copied at `single_call.py:89`, `:520`, `test_call_engines.py:1095`; and GUIDELINES §10's `single_call.py:601/:502/:504` are stale the same way (`_matching_method` is at `:485`, the comparison at `:528`) | | **RESTATE** | A1 Minor |
| **G-98** | Minor | GUIDELINES §10 | Says "each of the three shipped `descriptor:` rows"; there are **seven** in `spring-rabbit-template.yml` and `spring-jms-template.yml` alone and many more elsewhere. Every one of the seven was verified to have both halves of its near-miss pair, so this is a stale count, not a coverage gap | | **RESTATE** | A1 Minor |
| **G-99** | Minor | `COVERAGE.md:1614` + `injected_client.py:17-18` | "Waits on 2Q's call graph" is stale — 2Q shipped (`resolve/call_edges.py`; COVERAGE's own `:2049,2065,2085,2137`). The status is still true; the boundary reads as scheduled when it is unowned | | **RESTATE** | A1 Minor |
| **G-100** | Minor | `COVERAGE.md:1927` | Bundles two mechanisms under one shape and one tier. `PubSubTemplate.subscribe(String, Consumer)` is `single_call`/**A** — `spring-pubsub.yml:55-58` says it is undeclared only for want of a fixture, so no `config_join` is involved; the `PubSubInboundChannelAdapter` + `@ServiceActivator` half **is** already catalogued (2O Task 9) and by design derives no endpoint row. "Rides 2F's `config_join` once catalogued" is stale in both | | **RESTATE** | A1 M-minor, row 1927 |
| **G-101** | Minor | eight §5 tier cells | Eight pending rows carry a wrong or stale tier: `:830` Spring 7 `version=` (needs an `endpoints` column and an identity word — `schema.sql:12-64`, `derive_endpoints.sql:1156-1171` — so **not** "no code"); `:857` Ktor **B** (the document's own formula at `:509-513` gives C and the shipped `coRouter` vocabulary argues A — **B is a value neither rule produces**); `:858` Javalin B (the document says at `:526-530` such rows "become A the day call-site extraction ships", and it has); `:1131` bundles JDK `HttpClient` (nearly A) with `URL.openConnection()` (nearly C); `:1902` Micronaut SQS B (the raw SDK route already ships; `micronaut-jms-sqs` is a pure `annotation_driven` file → A); `:1995` Quartz "A for the annotation half" is **unreachable** (`scheduled_work` requires a `triggers:` attribute carrying an expression and `@DisallowConcurrentExecution` declares none); `:1996` Temporal A and `:1997` Vert.x B both need a `Protocol` closed-set member that does not exist (`domain/closed_sets.py:56-87`), which `endpoints.py:187-231` makes load-blocking — **schema work, not catalog work** — and `:1997` additionally contradicts `:1998`'s shipped ruling that an in-process pipe has no wire identity | | **RESTATE** | A1 Minor |
| **G-102** | Minor | `docs/principles-sweep-2026-09-05.md` | The sweep says **52** catalogs throughout (`:1237, 1255, 1461, 1475, 1798`) where 55 ship, and its §6.2 table omits `spring-advice`, `spring-integration` and `spring-scheduling` entirely. Its derived ratios (33 without a declining test, 32 unmeasured) are stated against the smaller denominator. **Any spec written off §6.2's table silently omits three catalogs** | `docs/RUNBOOK.md:314` and `roadmap.md:61` say 55; `ls` says 55 | **RESTATE** | A2 §0, F-23; A5 D8, F-m4 |
| **G-103** | Minor | `COVERAGE.md:1657` | The Shape column says `fluent_chain` where the shipped mechanism is `single_call` + one constructor hop (`record_wrappers`) = `registration_call`. **§2's matrix derives from this column** | `kafka-clients.yml:50-58`; `test_call_engines.py:7425` | **CORRECT** | A1 Minor |
| **G-104** | Minor | `COVERAGE.md:1826` | The `@JmsListener` parenthetical implies four read attributes (`destination`, `selector`, `subscription`, `concurrency`); only `destination` is in `path_from`, and `test_endpoints.py:5321` exists specifically to prove `subscription` derives nothing. The `@KafkaListener` row's parenthetical **is** a list of read attributes, so the two rows read as parallel and are not | `spring-jms.yml:29` | **CORRECT** | A1 Minor |
| **G-105** | Minor | `COVERAGE.md:1988` | Names only the `String` spellings of `fixedRate`/`fixedDelay`; the numeric forms are read too (`spring-scheduling.yml:45-50`) | | **RESTATE** | A1 Minor |
| **G-106** | Minor | `COVERAGE.md:1889` / §5.10 | The row names `SqsTemplate` and §5.10 states **none** of its boundaries — they live in §5.9 at `:1701` and `:1845`, the latter flagged there as "the highest-risk row" — with no pointer | | **RESTATE** | A1 Minor |
| **G-107** | Minor | the Shape column, whole document | It **changes meaning mid-document**. §1 `:55-70` declares "eight shapes"; §5.1/§5.9/§5.12 use `error_advice`, `supertype_dispatch`, `derived_resource`, `combinator`, `resolves.direction`, `annotation + hierarchy`, `annotation (recursive)` — engine style names, not survey shapes — while §5.2 stays with the legend's vocabulary, which is why its `RestTemplate` row reads `registration_call` where the prose says `single_call` | | **RESTATE** | A1 Minor |
| **G-108** | Minor | `COVERAGE.md:1779`, `:1807-1817`, `:1754-1760`, `:1322`, `:1331`, `:1218`, `:1349`, `:1917`, `:2031` | Seven stale or misfiled prose passages: `stamp_media.sql`'s description omits the first-writer `IS NULL` guard (`:56-57`); the duplicate `KafkaTemplate.send(Message)` explanation attributes it to a name+arity match that stopped being the mechanism when `spring-kafka-template.yml:87-88` gained its own arity-1 `Message` descriptor row (same stale text at `test_pipeline.py:322-330`); the `@SqsListener` alias paragraph sits in §5.8 (Kafka); "Phase 2H ships all four Java rows" where §5.4 now has six, and "zero further engine change" sits directly beneath the two rows recording the vocabulary pass (`path_from_siblings`, `path_fallback`) that MicroProfile forced; "conventional directories only" is exact on Maven (`detect/maven.py:38-41`) and **false on Gradle** (`detect/gradle.py:453-457` iterates build-reported `resourceRoots`); `:1917` says "B in every language" while `:1923` is A; §6's Android Retrofit row says A for a catalog that ships | | **RESTATE** | A1 Minor |
| **G-109** | Minor | `COVERAGE.md:145-146` + `OI-32` | The **headline end-to-end verification is unrunnable**: "Verified end-to-end on spring-petclinic: 17 endpoints, byte-identical across runs" has no expectation file in `scripts/field-expectations/` (which holds `jhipster-sample-app.json`, `mall-admin.json`, `spring-petclinic-rest.json`), and the one always-available beyond-fixture pin has been **red since 2O** (`OI-32`, Major, open) — whose own reasoning is the point: "a suite that is known-red is a suite nobody reads" | | **RESTATE** + fix the pin | A1 Minor |
| **G-110** | Minor | tests | **Test gaps behind rows that verify in code**: `:846`, `:848` (an *active* lexicographic tie-break between two controllers implementing one exchange interface), `:849` (no test derives a route from a nested controller), `:865`, `:876` (only the advice half of the composition is tested), `:892` and `:1989` (the SKIP is entailed by a generic gate, never asserted for these catalogs), `:855` (the non-coroutine Kotlin `router { }` DSL's silence is unpinned while its builder twin is pinned at `test_combinator_engine.py:2153`) | | **BUILD** (tests) | A1 Minor |
| **G-111** | Minor | `scripts/coverage_matrix.py` | Two latent parser defects, no wrong output today: `parse()` sets `section` on a `### 5.x` heading and **never clears it**, so it keeps attributing every pipe-leading line below §5.12 to "Async and internal boundaries" (§6 is a protocol-boundary table one `Java` label away from silently moving a §2 cell, with `--check` reporting the new number as current — one `if line.startswith("## ")` reset closes it); and it splits table rows on every pipe character, not honouring the backslash-escaped pipe that §5.8 `:1656` uses (harmless today — the escape sits early in that row, so `cells[-1]` is still the tier — and latent if an escaped pipe ever lands in the last two cells) | | **CORRECT** | A1 F-7, Minor |
| **G-112** | Minor | `tests/architecture/test_catalog_near_miss_coverage.py` | `_NO_DECLINING_TEST_YET` lists **25 of the 55** catalogs, and it **over-states the gap for `jakarta-websocket` and `spring-stomp`** — both have a near-miss and a paired positive (`test_endpoints.py:5789`/`:5811` and `:5825`/`:5843`); they simply carry no `@pytest.mark.declines(...)` marker. Benign direction, but the list is not a reliable measure of where the §10 discipline reaches | | **CORRECT** (markers) + **BUILD** (the remaining 23) | A1 §3.4, §2 |
| **G-113** | Minor | `COVERAGE.md:2068` vs `:2131` | The document states **opposite things** about whether a trace is named by a wire identity. Code sides with `:2068` (`document.py:1409`, `:1475` → `_root_addresses`); `:2131` was true before the 2Q close — GUIDELINES §9's stale-rationale class | | **RESTATE** | A5 F-m1, D5 |
| **G-114** | Minor | `roadmap.md:554-556` | Still says "gRPC has no shipped Java row at all, so it is named in the modulo" while §5.7 and `src/sextant/catalogs/grpc-*.yml` ship four gRPC rows, and `REQUIREMENTS.md:14`/FR-3 name gRPC in v1 scope | | **RESTATE** | A5 F-m2, D3 |
| **G-115** | Minor | batch-listener generics | A ledgered extractor candidate named twice in the roadmap (`:548`, `:577`) and once in the 2D spec appears in **no register**: not COVERAGE, not open-issues, not documented-not-implemented, not the completion plan | | **RESTATE** (file it) | A5 F-m3 |
| **G-116** | Minor | `COVERAGE.md` §8 | "Open questions" as a section title (unresolved **research** questions) collides by name with the `open_questions` ledger rendered in every document — one name, two meanings, in the document a reader consults | | **RESTATE** | A5 F-m5 |
| **G-117** | Minor | FR-20 clause 2 | Approximate subject naming, and listing ambiguity rather than choosing, has **no implementation and no gap row** | `grep -n "ambiguous\|approximate\|fuzzy" src/sextant/cli/app.py src/sextant/api.py` → 0 | **BUILD** or descope | A5 F-m6 |
| **G-118** | Minor | `docs/components/M04-resolver.md:210` | Asserts a walk property the code contradicts: "**No depth bound.** … It stops at a terminal" against `DEFAULT_MAX_DEPTH = 64` (`query/trace.py:88`). `OI-27` records the FR-6 side of this; M04's own line was not corrected with it | | **RESTATE** | A5 D14 |
| **G-119** | Minor | FR-18 | The **vintage-refusal half** — refusing to link bundles of mixed vintages — has no consumer until Phase L, and **L's scope line does not name it** (it names `participants`/`links`/DR-5) | `REQUIREMENTS:298` | **RESTATE** (name it in L) | A5 §5 row 12 |
| **G-120** | Minor | FR-16 | Curation and proposals: **no verb asserts, corrects or deletes a graph statement.** A5 recorded this as a status in its inventory and raised no finding; **filed Minor here — severity mine** (§3.1) | | **BUILD** or descope | A5 §1b |
| **G-121** | Minor | FR-7 | Diagrams are partly delivered: 68 mermaid sequence diagrams render, but there is **no class diagram of inheritance** (contract types only) and no `alt`/`opt`/`loop`. Named at the version-bump gate as a descope candidate (`roadmap.md:630-637`). A5 recorded this as a status and raised no finding; **filed Minor here — severity mine** | | **BUILD** or descope | A5 §1b |
| **G-122** | Minor | measurement debt, as a standing item | **19 catalogs carry no `measured:` block** and A2 could show neither an error nor an omission for **8** of them — which is not evidence they are correct, only that this audit did not falsify them. A2's ranked backlog (its §6, 14 ranks) is the sizing input for the spec, and its ranks 1-2 are corrections rather than probes | `_NOT_MEASURED_YET`; GUIDELINES §8.1 ("a rule taken from memory or documentation is a *prediction*") | **MEASURE** | A2 §1, §6 |
| **G-123** | Minor | `tests/architecture/` | **No architecture test asks whether a `@Repeatable` annotation's container is declared**, and no conformance fixture asks the class-file format what it carries. Both are the discipline that would have found G-36, G-39 and most of A4's list mechanically — the same shape `_NOT_MEASURED_YET` already has | A2 §6: enumerate each catalog's `mapping.annotations[].fqn`, ask the jar whether it is `@Repeatable`, require a `container:` or an allowlist row. A4 §6 item 24: one compiled source set exercising every JVMS 4.7 attribute and every JLS construct, with a test per attribute asserting either a fact or an explicit, cited "deliberately ignored" | **BUILD** | A2 §6; A4 §6 |

### 3.3 Tally

| severity | rows |
|---|---|
| Critical | 14 |
| Major | 57 |
| Moderate (A4's scale) | 3 |
| Minor | 49 |
| **total** | **123** |

| verdict (primary) | rows |
|---|---|
| **BUILD** | 47 |
| **CORRECT** | 36 |
| **RESTATE** | 35 |
| **MEASURE** | 5 |

**KEEP** appears nowhere in this table by construction — a gap is not a KEEP; §5 is where the
KEEPs are. Fifteen rows carry a **second** verdict (most often **RESTATE** beside **CORRECT**,
where a defect and the sentence describing it are both wrong, or **MEASURE** beside **BUILD**,
where what to build depends on a measurement nobody has taken); those are counted once, at the
primary verdict.
**Duplicates merged: 5** (see §3.1). **Findings split into several rows: 4**, adding 10 rows.

---

## 4. Grouped by root cause

Several distinct symptoms share one cause. The spec must fix causes; fixing symptoms one at a
time is what produced the state §3 describes.

### RC-1 — the module edge: what happens when a body or a value is not in this workspace

**Members:** G-1, G-48, G-8, and the definition of `boundary` the rendered document prints
(`architecture.md:141`).

Sextant has exactly one word for "the body is not here" and it is doing three jobs. G-1 makes
it **false** for a method the module itself declares in a superclass — 21% of one real
document's boundary steps. G-48 is the same defect costing `return_flows` its inherited
accessors, with its own COVERAGE row. G-8 means a consumer who receives the bundle **cannot
recompute or check any of it**: the pictures ship and the 1 916 rows behind them do not. The
document's own sentence — "a third-party library, the JDK, a MyBatis mapper and a SIBLING
BUILD MODULE all read alike there" — is the honest statement of the *design*, and it is
precisely what Phase L exists to fix; G-1 is not that, it is the same word applied to code
that **is** here.

*The brief that commissioned this consolidation paired A5's "empty response contracts" with
A3's "trace stops" as one cross-module item. They are not the same thing and I have not merged
them: A5's contract holes (G-66, G-67) are about a **type** that cannot be expanded, and A3's
are about a **body** that was not resolved. They share only the shape of the symptom — a
visible stop at a module edge — which is why they belong in the same section and not in the
same row.*

### RC-2 — a catalog may spell a type or an annotation exactly once

**Members:** the vocabulary gap itself (A3's VG-1 … VG-21, **21 sites of one shape**), plus
every instance already costing output: G-12 (`javax.jms`), G-14 (the javax JAXB spelling),
G-51 (`matches.owner`, and G-89 as its concrete case), G-21 (the Spring Cloud GCP 1.x rename),
and A3's VG-4 (`prefix_annotation`, the javax/jakarta
case the SQL's own comment at `derive_endpoints.sql:431` names: *"a framework whose gate has
TWO spellings (one library renamed, both still in the wild) cannot be named by it"*).

*G-38 was a member of this list and is removed: W17 measured it and it costs no output —
`spring-mvc.yml`'s `detect.coordinates` was already a LIST at the time this was written and
is read by nothing for that catalog, so it was neither an RC-2 site nor a cost.*

Every one of these is the same missing word. The 21 sites are: `matches.owner`,
`matches.root.owner`, `matches.type_annotation`, `mapping.prefix_annotation`,
`reply.annotation`, `matches.interface`, `registration.owner`, `field_annotation`,
`identity_marker`, `annotation`, `container`, `handler_annotation`, `status_annotation`,
`supertype_marker`, `matches.supertype`, `no_repository_bean`, `resource_annotation`,
`member_annotation`, `when.implements`, `rule.annotation`, `media_values.owner`. Note the
asymmetry that proves it is accident rather than design: `error_advice`'s advice and controller
**lists are plural** while its two annotation keys are scalar.

Two structural relatives sit in the same group and are **not** the same fix: **VG-22** — no
engine can say "this type or any subtype of it", and for a third-party owner no widening is
derivable from facts either, so the catalog is the only place it could be said; and **VG-25** —
`fluent`, `combinator` and `interface_implementation` have **no `descriptor` and no `arity`
key at all**, so a catalog cannot separate two overloads of a chain step, a vocabulary method
or a registration method.

### RC-3 — method identity and method resolution

**Members:** G-1 (JVMS 5.4.3.3/5.4.3.4 absent — A3's ILR-1), G-48, A3's **ILR-2**
(`fluent.py:626`, `combinator.py:306`, `interface_implementation.py:89` identify a method by
*owner and name*, where JLS 8.4.2/15.12.2 says name **and parameter types in order** — the
arity defect's own family, one notch weaker, since arity is not even asked), A3's **ILR-3**
(`parse_binding.py:576`, owner+name+arity, `A-Mi18`, under-reports rather than choosing
wrongly), A3's **ILR-4** (`parse_binding.py:566`, the exact-owner rule in a second module),
and G-55 (parameter types erased, so **DR-5 compares `List` against `List`**).

`OI-19` belongs here too, but as a **non-defect**: the two `sig_` implementations agree (§6).

Three sites in this area are **clean and must stay that way**: `single_call.py:524-532` (a
descriptor claims an arity; a call matching none falls through to nothing — the original arity
defect genuinely closed), `dispatch.py:114-119` (covariant returns reached through the
compiler's bridge, which is what the JVM enters), and `dispatch.py:113` (no override walk for
`invokestatic`/`invokespecial`, correct per JVMS).

### RC-4 — the checklist has one axis, and the axis is protocol

**Members:** G-11, G-58, G-19, G-20, G-64, plus the twelve committed items A5 found enumerated
nowhere.

COVERAGE §5 — the checklist every count is quoted from — is organised on the protocol axis
alone. It has no section for shapes, for configuration resolution, for the open-question
ledger, for the bundle, or for the rendered document; traces get §7 prose rather than rows;
only wire format has a checklist of its own (§4). **So a cross-cutting gap has nowhere to be a
row**, and twelve committed items are therefore enumerated nowhere at all:

| # | committed at | enumerated in | this file |
|---|---|---|---|
| 1-4 | FR-11..FR-14, `REQUIREMENTS:212/222/230/236` | nothing | G-10 |
| 5 | FR-17 clause 3, `REQUIREMENTS:272` | nothing | G-68 |
| 6 | FR-20's ambiguity rule, `REQUIREMENTS:315` | nothing | G-117 |
| 7 | Kotlin-specific surfaces, `REQUIREMENTS:14` | nothing; 0 of 170 rows | G-64 |
| 8 | `Page`/`Slice`/HATEOAS wrappers, implied by FR-4 | nothing | G-66 |
| 9 | generic type-parameter substitution, implied by FR-4 | one adjacent sentence at `COVERAGE.md:868`, about Data REST only | G-67 |
| 10 | batch-listener generics, `roadmap.md:548, 577` | nothing | G-115 |
| 11 | the export's dropped trace tables — D06 §5 forbids the omission | nothing | G-8 |
| 12 | FR-18's vintage-refusal half, `REQUIREMENTS:298` | L's scope line names `participants`/`links`/DR-5, not this | G-119 |

Three instrument defects compound it: 53 boundary rows cannot reach §2 at all (G-58), 11 rows
lose their status cell to a column mismatch (G-11), and a fifth messaging protocol has shipped
inside another column (G-20).

### RC-5 — `peer` is not part of endpoint identity

**Members:** G-2 (the merge key), G-49 (three dedup keys and a misfiled, mis-stated rule).

A3 is explicit that this is **not** a catalog-expressiveness question: it is an identity
decision and belongs in the spec beside D02 §5. D02 already treats `peer` as identity-bearing
("two deployments on one host are two peers", D02:962) and the implementation does not.

### RC-6 — the class file is read as an opinion about the code, not as a format with a spec

**Members:** G-3, G-4, G-52 … G-63, G-72 … G-74, G-78 … G-84, and the missing conformance
fixture (G-123).

**4 of the 30 attributes JVMS 4.7 defines are read fully, 7 partially, 1 deliberately ignored
with a stated reason, and 18 silently dropped** — one omission (`StackMapTable`) is stated
anywhere. The pattern is not carelessness in the code that exists: A4 is emphatic that the
dataflow layer's refusals are careful and honest and that the 9.15/9.16 annotation model is
correct. The pattern is the **perimeter** — how much of the format was never approached, and
the absence of any test that asks the format what it carries. Six D00 §5 fact kinds have no
producer, and four of those six are pure extractor work (`constant`, `string_literal`,
`occurrence`, and `call_site` with `invoke_kind: throw`).

Two fixes in this group are **not the same fix and must not be conflated**: raising the ASM
version moves the class-file ceiling; it does not stop the *next* ceiling from being
whole-scan-fatal. A per-entry catch that records an `uncovered` row and a `partial: true`
document is the durable half, and it is what `Main.java:29-47`'s own stated rule already
implies.

### RC-7 — a composed address is published without asking whether each component addressed anything

**Members:** G-5 (class-level + method-level concatenation, three catalogs), G-75 (the
addresses-nothing gate is exempt by construction for any catalog declaring `$path_prefix`),
and the `@Repeatable` container family — G-36, G-39 — where the composition *loses* an address
instead of inventing one.

The addresses-nothing gate asks "is the composed string empty", which is a question about the
**result**. The three defects above are all cases where the result is non-empty (or absent)
while a component was never declared: two prefixes concatenated bare, a constant prefix with
nothing under it, a container javac wrote that no catalog names. A2's structural remedy for the
container half (an architecture test that asks the jar whether each matched annotation is
`@Repeatable`) is in G-123.

### RC-8 — measurement debt

**Members:** G-122 (19 unmeasured catalogs, 8 of them with no falsification found), G-27
(COVERAGE §7 and OI-10 still carry 29/26), G-22 (an unmeasured version presented as measured),
G-88, G-91, G-45, G-46, G-67 — every row above whose verdict is or includes **MEASURE**.

The consequential fact is not the count: it is **which** catalogs are unmeasured. The 19 include
every gRPC catalog, three of four GraphQL catalogs, `spring-ws`, `wsdl-schema`, `spring-advice`,
`spring-cloud-openfeign` and `spring-cloud-stream` — i.e. the catalogs behind a large share of
§5.3/§5.4/§5.7's ✅ rows. Under GUIDELINES §8.1 those rows rest on framework rules no committed
probe has opened a jar for, and nothing a reader of a ✅ can see says so. A2 ranks the backlog
in its §6; ranks 1-2 (`spring-cloud-stream`'s binding rule; `spring-data-rest`'s collection-GET
gate) are **corrections**, not probes.

### RC-9 — the registers disagree about what shipped

**Members:** G-9, G-69, G-70, G-113, G-114, G-102, G-65, G-118, G-115, and the corrected
counts in §2.

A5 reconciled 76 committed items across four registers and found **15 disagreements**. The
sharpest is G-9: the document COVERAGE names as the delivery-status authority marks everything
`planned`. The most dangerous is G-65: four committed requirements whose statement of record is
an **untracked file**. This group is cheap to close and expensive to leave: every one of these
is a document that will be read by whoever writes step 2's spec.

---

## 5. What is RIGHT and stays

Half the question the user asked. **A reader must be able to see what not to touch.**

**The §5 checklist is mostly correct.** **120 of 170 rows KEEP** — 78 of the 89 ✅/◐ rows and
42 of the 53 boundary rows. Every WSDL/XSD boundary bullet has a named refusal in
`interpret/wsdl_xsd.py` and a test. Every §5.4 GraphQL boundary holds at its refusal. **§5.6
(SSE) is the cleanest section in the document** — five bullets, all true, each with a named
consumer and a pinned test. Every §5.5 WebSocket boundary bullet is true (the cell's problem is
that they are bullets). All three §5.7 gRPC boundaries are true and falsifiable.

**30 of 55 catalogs KEEP** — they encode what the framework does, within a stated bound.
`spring-webclient.yml` is explicitly "the model in the tree": 8 starters and 4 terminals at two
minors, with the version difference stated in a comment. Enumerated complete against their
jars: `spring-web`/`spring-mvc`'s mapping family (6 of 6 at 6.2.15 **and** 7.0.9),
`spring-advice` (4 of 4), `spring-http-interface` (6 of 6 at both minors), `spring-kafka`,
`spring-rabbit`, `spring-pulsar`, `spring-jms`, `spring-sqs`, `spring-graphql` (6 of 6),
`retrofit` (8 of 8 request-method annotations), `spring-cloud-openfeign`, `spring-scheduling`,
`microprofile-graphql`'s root set, `spring-restclient`'s starter set,
`spring-webflux-router`'s verb-predicate set (7, and there is no `TRACE` predicate to miss).

**12 of 27 engine units KEEP**, including the whole `pipeline.py` ordering (every constraint is
a stated dependency and each holds), `roots.py`, `derived_resource`, `resolve/config.py`,
`open_questions`, `service_identity`, `environment_divergence`, `protocol_hint`, `format`, and
the trace walk itself — `query/trace.py`'s stop ordering (boundary → cycle → revisited →
depth_limit) is right, each is reported, the depth bound never fired (max depth 2 of 64), and
`truncated` is correct. **The walk is not the problem; what it is handed is.**

**Determinism holds, measured three ways.** `api.analyze` + `api.render` from scratch on two
independent copies of `examples/spring-petclinic`: `architecture.md` **and**
`architecture.html` byte-identical, and again across a re-render. Two full extractor runs over
16 class files: `diff -r` byte-identical, with ordering defended structurally (`TreeMap`
everywhere, `sorted()` on both class sources, POSIX path normalisation, instruction indices as
value ids — no `HashMap` reaches output). Three bundle exports to separate paths: `diff -r -q`
exit 0 and identical sha256 across **132 files** including `manifest.json`.

**`egress` never derives.** Import-linter contracts pass; `egress` imports from `application`
only `ResolveReport`, `Trace`/`Step`, `Root`, `ModuleModel` — no workspace, no engine, no
derivation. The one classifier in the renderer (`_handler_fallback`, `document.py:611`) reads
two columns of a row it was handed and is presentational.

**The guard harness is at 82 killed / 0 survived / 0 unmeasurable, with an empty allowlist**,
and `pytest -q` is at **2 346 passed, 2 skipped, 0 failed**. Where a near-miss exists it
discriminates.

**The original arity defect is genuinely closed.** `single_call.py:524-532`: a descriptor
claims an arity and a call matching none falls through to nothing (A3's ILR-5, verified). So
are `dispatch.py`'s covariant-bridge handling (ILR-6, verified on real bytecode) and its
refusal to walk overrides for `invokestatic`/`invokespecial` (ILR-7).

**The `path_fallback` trap was measured clean, twice.** `spring-graphql`'s
`path_fallback: construct_name` is **correct**: `AnnotatedControllerConfigurer.getMappingInfo`
at spring-graphql 1.2.6 is `field = StringUtils.hasText(a.field()) ? a.field() :
method.getName()` — `method.getName()` verbatim, **no accessor-prefix stripping**, so
SmallRye's `getOrders → orders` behaviour is SmallRye's alone and does not generalise.
`netflix-dgs`'s is correct for the same reason (`DgsSchemaProvider.registerDataFetcher`,
`CharSequence.length() == 0 → method.getName()`, offsets 0-48 at 8.7.1). **The remedy for both
is a `measured:` block, not a change.**

**The addresses-nothing gate is right and its re-key was right.** Driven against **all 20**
`annotation_driven` catalogs with the exact `A-C1` shape: 12 correctly derive 0 rows, 7
correctly derive a real address (`spring-mvc`/`spring-web` → `/` × 8 verbs, the CP-1 root route
exactly as the gate's comment predicts; five more → the method name via `path_fallback`), and
**one** hole remains (G-75). The gate no longer turns on a formatting property, and the
separator-declaring catalogs are no longer the exempt set — they fall on both sides on the
merits of what their declarations address.

**The `measured:` machinery is the strongest single piece of the catalog layer.** `A-Mi4` is
closed: `measured:` is a real, loader-visible, test-enforced field; 36 of 55 catalogs carry
one; the allowlist is at 19 and the test refuses growth. **Every finding in §3 against a
catalog should be filed against this machinery, not beside it.**

**The open-question ledger is the healthiest capability audited.** Five kinds, closed at
`open_questions.py:30-42`, **every one with a live producer** — no dead members. Enforcement is
two-sided: `record_open_questions` raises on anything outside the set, and the renderer has one
arm per kind with a fall-through `raise ValueError(...)`, so a sixth kind cannot ship
half-wired. The enrichment seat genuinely consumes it in both directions, redacted first, and
the graph stays immutable — a verdict never feeds resolve.

**Wire formats (2G).** The six-rung ladder is real and correctly ordered, NULL and `unresolved`
pair 1:1 across 111 rows, and the conflict rule is the strongest discipline in the capability:
a rung producing more than one distinct format returns `unresolved` **and stops the ladder** —
"a rung BELOW a disagreement would be breaking a tie that stronger evidence could not".

**Configuration resolution (2F).** A generic interpreter over one catalog-declared
`config_model`, naming Spring nowhere; layering verified across two environments, and asymmetry
is **recorded rather than hidden** (`only.in.default` → `(NULL, NULL, missing_key)` under
`prod`). Its stated caveats each name what falsifies them — **keep them as they are**.

**Shapes and contracts (2A).** `required` and `nullable` populated on every row and
independent; evidence tiered honestly (`compiler` for an explicit `@JsonProperty`, `declared`
for the default strategy); wrapper unwrapping is a **generic recursive interpreter over catalog
data** naming no framework; nested expansion is by reference so cycles terminate by
construction with no depth counter; and expansion stops **visibly** — an unexpandable type gets
an `open=True` zero-field row, `open` is direct and never transitive, and all six open shapes
in the run are named in `## Known gaps`.

**Redaction and the bundle.** Masking confirmed at all three exits with file:line evidence;
`hunter2` appears in **0** bundle columns and **0** fact parquets and in the workspace as
designed; `producer.redaction_set_hash` is real and tracks the repository's own widening. D06
§7's hygiene rules hold — no absolute paths, no `.duckdb`, no overlay file, no `metadata.json`
— and `module.dependencies` is over-delivery beyond D06 §3.

**The recent closes are real, verified at their consumers**: `OI-5` (`path_fallback`), `OI-35`
(`path_from_siblings` — reversing the list reverses the winner), `OI-36` (`@RabbitListeners`),
`OI-38` (`@PulsarListeners`, where the pass ADDS and never replaces), `OI-39`
(`@PulsarReader`), `OI-40` (class-level `@SqsListener`), `A-M13`, `A-M15`, `A-M7` (eleven
consumer factories, row for row), `A-M2`, and `OI-4`'s explicit handling in `combinator`.

---

## 6. Stale beliefs the audits corrected

These are things the registers currently assert that the audits found untrue. **This file does
not edit `docs/open-issues.md`, `docs/COVERAGE.md` or any plan** — it records what the
correcting pass must change.

**`OI-17` should be narrowed, and its falsifier has already fired.** OI-17 argues the
conservative side of a rule about a call through a **library-declared** type, with a stated
blast-radius cost (`java/lang/Object#toString` fan-out) that one corpus cannot size. G-1 is a
different defect in the same function: entirely in-module, JVMS gives exactly one answer, the
walk stops at the first declaring type with a body so it adds **no** `narrowed` fan-out, and it
therefore carries **none** of OI-17's cost. OI-17 says "**Falsified by** a trace that stops at
an in-module body a reader can see" — `architecture.md:389` is that trace. The pass should
narrow OI-17 to the library case it actually argues and file G-1 as its own row.
`COVERAGE.md:2145` names only the library case; the in-module case is stated nowhere.

**`OI-19` is not producing wrong answers, and its "structurally uncatchable" reasoning is half
false.** The two `sig_` implementations — `ClassScanner.disambiguatorOf` and
`domain/symbols.disambiguator_of` — were cross-checked over **200 000 random strings** (lengths
1-40, code points 32-231, so multi-byte UTF-8 included): **0 mismatches**. Java's
`String.format("%02x", byte)` applies the unsigned correction, so it matches Python's
`hexdigest()[:8]` byte for byte. **The exposure is entirely the missing test**, which changes
the fix from "reconcile two implementations" to "pin the agreement" — and the harness
constraint OI-19 cites can be sidestepped: **the test needs no compiled fixture at all**, only
a table of descriptor strings and their expected `sig_` values, asserted on **both** sides
against the same table. A drifting Java change then fails the Gradle suite and a drifting
Python change fails pytest, with no cross-language fixture copying.

**The `combinator` NULL-method / NULL-path `resolved` row is CLOSED.** The sweep §12 finding 6
records it FIXED at `8d1aeb2` (`derive_call_endpoints.sql` gained the addresses-nothing twin),
and A3 confirmed by reproduction: the `route(accept(JSON), handler)` shape it was added for now
emits **0 rows** where it used to insert a `resolved` row with NULL method and NULL path,
undeduplicated. The cost is the stated under-report it was traded for (`COVERAGE.md:854`). Any
belief that this is still live is out of date; **do not re-open it in the spec.**

**The empty-address guard reaches ELEVEN separator-declaring catalogs, not seven.** The sweep
says "exactly seven catalogs declare one" (`:1719`), builds `A-C1`'s blast radius on that
(`:1732`) and records the fix "across all seven" (`:1890`). There are **eleven**:
`spring-mvc`, `spring-web`, `spring-actuator`, `spring-http-interface`,
`spring-cloud-openfeign`, `spring-stomp`, `spring-rabbit`, `spring-kafka`, `spring-sqs`,
`spring-ws`, `jakarta-websocket`. And the number is now beside the point: after the re-key from
`path_separator` to protocol meaning, **the separator-declaring set is no longer the exempt
set** — its members fall on both sides of the gate on the merits of what their declarations
address, and the one exemption left is keyed on `$path_prefix` (G-75).

**`OI-10`'s body and `COVERAGE.md:2255-2258` carry 29/26; it is 36/19.** OI-10's *title*
already carries 19, so the register contradicts itself, and COVERAGE contradicts the register it
cites. The roadmap's copy of this number was corrected at `abfd93c`, after the audits ran.

**`OI-36`'s shape is open in two more frameworks** — `spring-ws` (`@PayloadRoot`,
`@SoapAction`) and `netflix-dgs` (`@DgsData$List`). This is **not** a re-opening of OI-36,
which is genuinely closed for the three frameworks it names; it is a new row and a new
architecture test (G-36, G-39, G-123).

**`_NO_DECLINING_TEST_YET` over-states the gap for `jakarta-websocket` and `spring-stomp`.**
Both have a near-miss and a paired positive; they simply carry no `@pytest.mark.declines(...)`
marker. Benign direction, but the list is quoted as a measure of where the §10 discipline
reaches and it is not one (G-112).

**`A-Mi4` is closed** — `measured:` is real, loader-visible and test-enforced. **The sweep's
§6.2 table is stale by three catalogs and its whole document uses a 52-catalog denominator**
(G-102). **`spring-mvc.yml` does cite evidence** (§2).

**Two gap names are retired in code and still published** (`sequence_diagrams_pending_call_graph`,
`call_graph_not_implemented`, G-69), and **`OI-32` is red and has been since 2O**, which
matters because it is the only always-available beyond-fixture pin (G-109).

---

## 7. What could not be determined

Nothing in this section is a gap. Each item is a question whose answer changes a gap's size,
severity or existence, with what would settle it.

**Things the audits measured a mechanism for but could not measure the consequence of:**

1. **The generic-envelope effect end to end** (G-67). The mechanism gap is verified; the
   consequence is not. No shipped fixture contains a `Result<T>`-shaped envelope, and
   `macrozheng/mall` — which uses `CommonResult<T>` on nearly every controller — is gitignored
   and not built in this tree. **Settled by**: building mall and re-measuring. A5 calls this
   the single highest-value thing to measure before the spec commits a size.
2. **Whether `spring-data-rest` really mints an ungated collection GET** (G-46). **Critical if
   it does, Major if not.** **Settled by**: one engine run against a `Repository`-only fixture.
   A2 ranks it 2 of 14.
3. **Whether the unmapped-binder row really publishes `kafka`** (G-7) — read off the catalog's
   own stated rule, not run. **Settled by**: one engine run with a binder name outside the four
   mapped ones.
4. **G-51's blast radius.** No Spring bytecode in this tree to compile a `RestOperations`-typed
   field against. **Settled by**: a module that injects a client by its interface type.
5. **Whether any shipped consumer is currently wrong because of G-4 or G-55.** A4 measured the
   extractor's output only; establishing the downstream cost means walking the engines.
   **Settled by**: a pass over the engines for parameter-annotation and parameter-type readers.
6. **Whether fixing G-1 regresses anything.** A3 was read-only and did not apply the JVMS walk
   and re-run the suite. The number that matters **is** measured: on four corpora it adds
   28 / 96 / 8 / 0 edges, each with exactly **one** candidate, so it introduces no `narrowed`
   fan-out. **Settled by**: applying it and running the suite.

**Things nobody has measured at all:**

7. **Whether `SqsTemplate.newSyncTemplate` returns `SqsOperations`** at spring-cloud-aws-sqs
   3.1.1 (`COVERAGE.md:1845`). The row carries a `javap -p -s` citation; **no probe records the
   output**, and `cp10_catalog_descriptors.md:190-197` explicitly lists this as unmeasured.
   The mechanism half of the row is verified; this sub-claim is **UNVERIFIED**. **Settled by**:
   one `javap`.
8. **Whether okhttp 3.14.9's `Request$Builder` declares the same eight verb setters** (G-22).
   Probably true; certainly not evidenced, which is the finding.
9. **Whether spring-kafka 2.x is in scope at all** (G-13). No document states a Spring Kafka or
   Boot version floor. **If 2.x is deliberately out of scope, G-13 is a missing sentence rather
   than a defect — but nothing says so.** This is a scope decision the spec must make, not a
   measurement.
10. **`grpc-spring`, `grpc-net-devh`, `grpc-java`** (G-91) — no `net.devh:*` and no
    `org.springframework.grpc:*` in either local cache; `io.grpc:*` is present but the two
    catalogs' rules are about the *starter* annotations.
11. **`spring-kafka-media`'s Confluent half** (G-88) — no `io.confluent` artifact in either
    cache; the eight class names are A2's **prediction**. Needs a network fetch.
12. **`spring-data-rest`'s store-module hierarchy** (G-45) — A2 reasoned about the jar-hop and
    did not open `spring-data-mongodb` to confirm which base each store module extends.
13. **`spring-actuator`'s `@Selector` path composition** (G-93) — the annotation exists at both
    versions and no catalog names it; what a `@Selector` parameter does to the served path was
    not read (CP-5 may already answer it).
14. **Whether `@WebEndpoint` is meta-annotated `@Endpoint`** (`COVERAGE.md:839`). No actuator
    jar in the tree; `A-Mi6` records it unverified. The composition mechanism is confirmed
    either way, so the row's boundary is unconditioned regardless.
15. **Whether Javalin and Ktor really reduce to a catalog today** (G-101). The engines are
    close; settling it needs a probe of the two call-site shapes plus a ruling on whether
    `single_call`'s "the handler is the registering method" is acceptable for a
    lambda-registered route.
16. **The library facts behind five pending rows** — Micronaut, Quartz, Temporal, Vert.x,
    Akka/Pekko. No jar was opened and no probe covers any of them.
17. **Kotlin coroutines' `Continuation` parameter and `suspend` shape** (RC-6). No
    coroutine-bearing class file exists on this machine. A4 predicts the `Continuation` is
    emitted as an ordinary declared parameter and the `Object`/`Any?` return erasure is
    unrecoverable without `@Metadata`'s function table — **unverified**.
18. **Kotlin's true reach** (G-64). No Kotlin-only fixture was analysed, so A5 can say Kotlin
    has no §5 rows and no catalogs naming Kotlin-specific constructs, but **not what a real
    Kotlin Spring module actually derives today**.
19. **`ConstantDynamic` as a value producer**, the **lone-surrogate escaping path** (G-79), and
    **`ACC_STRICT` / `SourceDebugExtension` / pre-49 `Synthetic` spellings** — read as dropped
    from the code, not exercised with a compiled input.
20. **G-75 against a running app** — whether Spring Boot can start with an `@Endpoint` whose id
    never reached the bytecode. The derivation is reproduced either way.
21. **G-76's reachability.** No constructible NULL `path`. Latent.
22. **`@RabbitListener(bindings = …)` on real bytecode.** The `[]` verdict is unaffected (no
    `path_from` alias can name a nested attribute), but the reproduction used a hand-built
    nested fact.
23. **Determinism under the two recorded flakes.** Three exports were byte-identical; the
    repository's own note (`workspace.py:62-71`) records two unexplained e2e flakes whose cause
    is open. Three runs cannot close that.
24. **`mall-portal`** was never built, so every mall number in the tree — including 2Q's
    acceptance evidence — comes from one module. This is also `OI-17`'s and `OI-18`'s stated
    close condition.

**Things this consolidation could not reconcile:**

25. **Seven engine styles were read but not driven adversarially** — `schema_operations`,
    `derived_resource`, `config_join`, `supertype_derived`, `injected_client`, `error_advice`,
    `scheduled_work` — plus the `shapes` and `format` ladders. Their KEEP verdicts are
    source-traced, not run. A3's own warning stands: of the six units it *did* drive, five
    produced a finding, "which is a weak signal that the untried seven are not clean."
26. **The brief that commissioned these audits asserted that the class-level plus method-level
    listener fabrication appears in both A1 and A2. It does not.** A2 contains no such finding
    — `grep` for `class-level`, `concat`, `composed destination` and `path_separator` over
    `audit2-catalogs.md` returns nothing. G-5 is A1's alone; A2's nearest relative is the
    shared container/prefix vocabulary (RC-7). Recorded so nobody looks for a corroborating
    measurement that was never taken.
27. **A5's independent recount of §5's shipped/boundary split disagrees with A1's**, and A5
    says so: its classifier is crude (status text is not in a fixed column) and it makes no
    claim about which is right. **A1's count is the one carried in §2 here**, because A1
    classified the tier cell alone, which is what `coverage_matrix.py` parses, and because it
    reconciles to 170 with zero unclassifiable rows. The underlying point survives either way:
    **the 59/55/29 headline has no generator**, so unlike §2 (which `--check` confirms is
    regenerable) it cannot be re-derived and will drift exactly the way §2 was built not to.
28. **`config_join` publishes a config-file-derived address at `evidence: compiler`**, where
    D00:569 defines `compiler` as a compiled origin and `declared` as a source one — **but
    D02:993 specifies `compiler`, so the engine mirrors its spec.** A3 files this as a **spec
    question, not a defect**, and it is left open here for the same reason.
29. **Probe re-runs.** Every CP-5 / CP-9 / CP-10 / CP-11 / CP-12 / CP-13 / CP-15 / CP-16 /
    CP-17 citation in A1 is read from the committed probe file, not re-measured, and A1's test
    citations are from reading the assertions rather than running them. `coverage_matrix.py
    --check` and `check.sh --guards` *were* run (both pass), as was A3's full `pytest -q`.
