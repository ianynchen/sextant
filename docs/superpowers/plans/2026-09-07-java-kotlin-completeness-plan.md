# Java/Kotlin v1 completeness — sequenced plan

**Spec:** [`docs/superpowers/specs/2026-09-06-java-kotlin-completeness-design.md`](../specs/2026-09-06-java-kotlin-completeness-design.md)
**Gap analysis:** [`docs/java-gap-analysis-2026-09-06.md`](../../java-gap-analysis-2026-09-06.md)
**Date:** 2026-09-07

Step 3 of four. The spec says what we build; this says in what order, and what each item
owes before it is called done. Step 4 executes these one at a time, verifying each and
ticking it off in COVERAGE.

## How to read this

Each item is a unit that carries its own test cycle and could be rejected on its own. The
**Delivers** column is what changes for someone using Sextant — an item whose delivers
column is empty is a foundation, and the item that cashes it in is named.

**Nothing here is optional.** Where an item looks skippable, §17 of the spec records why it
is not.

### Global constraints

Carried into every item, from spec §15.

- **NFR-1** — every new table and export gets an explicit deterministic order; byte-stability
  is a test.
- **NFR-2** — what we cannot determine becomes a stated boundary or an open question. Never a
  default, never a silence.
- **NFR-5** — every new vocabulary is a closed set with a test rejecting anything outside it.
- **§8.1 rule 5** — where two things look identical to us, the provider distinguishes them.
  Find it; never invent one.
- **§8.2** — code, compiled code and repository configuration are truth. Anything a
  deployment can overwrite is a possibility, stated as one.
- **§8.6** — a boundary is real when a chain of evidence reaches where it provably happens.
- No network in tests, ever. No version bumps beyond the approved ASM 9.7 → 9.10.1.
- `uv.lock` is never committed. Never `git add -A` or `git add -u`.
- **§13.8** — a second occurrence of an error class is a diagnosis, a third is a stop; a
  second principle violation is a stop.

---

## Wave 1 — F1: the extractor reads the class file as a specified format

Six later items consume facts produced here, and three of them are impossible without it.
Nothing in Wave 1 changes derived output on its own; Waves 3, 4, 6 and 7 cash it in.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W1** | ASM 9.7 → 9.10.1; the accepted major range becomes a test; the observed major is recorded per document; `partial` / `partial_reason` get a code path that can set them | §2.1 | — | JDK 24/25/26 bytecode stops failing the whole scan; a skipped class says why, in the manifest and the document |
| **W2** | Override `visitAnnotableParameterCount`; align parameter annotations from the end (JVMS 4.7.18). Test uses an **enum** constructor, not only an inner class | §2.2 | — | annotations on inner-class and enum constructors stop landing on the wrong parameter |
| **W3** | Multi-release jars, extractor half: read `Multi-Release` once at `JarSource` open as a parsed attribute; absent → skip `META-INF/versions/` entirely; tag every document with `class_release`; strip the prefix in `sourcePathOf` | §2.4 | — | `testcontainers-2.0.5.jar` stops emitting 1,198 phantom documents; overlay documents stop naming impossible `.java` paths |
| **W4** | JVMS 4.7, the four that already force an invented rule: `AnnotationDefault`, `InnerClasses` + `EnclosingMethod`, `StringConcatFactory`'s recipe, `ConstantValue` | §2.3 | — | catalogs stop hardcoding framework defaults; nesting stops being derived by splitting on `$`; the `constant` resolution gets a producer |
| **W5** | `Signature` completed: method and constructor **parameter** types, and class/method formal type parameters with bounds | §2.3 | — | (foundation — **W25** cashes it in) |
| **W6** | `LineNumberTable`, `SourceFile`, `LocalVariableTable` / `LocalVariableTypeTable` | §2.3 | — | (foundation — **W35** cashes it in; also fixes Kotlin's `.java` mislabel) |
| **W7** | The remainder of JVMS 4.7: `NestHost`, `NestMembers`, `PermittedSubclasses`, `Exceptions`, `Record`, `Module`, `ModulePackages`, `ModuleMainClass`, `SourceDebugExtension`, `Deprecated`, class-level type annotations, `visitAttribute`; plus the 11 dropped access flags | §2.3 | — | `ModuleMainClass` gives OI-22's `entry_point` root kind its producer; `ACC_VARARGS` unblocks capability 9.15; an `@interface` stops emitting `construct_kind: "interface"` |
| **W8** | The read/not-read ledger: one enumerated `deliberately-not-read` set with a stated reason per entry, and a test that fails on "declared, never read". `module-info.class` stops minting a fabricated `class` symbol (G-61) | §2.3, §2.5 | W4–W7 | `✅ ASM` in COVERAGE becomes a claim that means something |

**Wave 1 acceptance:** every attribute in JVMS 4.7 is read or in the enumerated not-read set —
no third category. `spring-core-7.0.2.jar` emits exactly one document per class name, each
carrying `class_release`, with its eight versioned-only classes present.

---

## Wave 2 — F2: a catalog may spell a type exactly once

The highest-leverage change in the spec: 21 catalog keys accept one string where the world
offers several, and every javax/jakarta miss, interface-typed-owner miss and renamed-coordinate
miss is that same missing word.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W9** | All 21 scalar sites accept a scalar **or** a list; each alternate carries its own `measured:` provenance; a scalar stays valid | §3.1 | — | (foundation — W10–W12 cash it in) |
| **W10** | Owner alternates applied: `JmsOperations`, `SqsOperations`, `AmqpTemplate`, `KafkaOperations`, `RestOperations`, Kafka's `Consumer<K,V>` | §3.2 | W9 | interface-typed clients — the idiomatic Spring construction — stop deriving nothing |
| **W11** | **MEASURE:** the javax/jakarta mechanical sweep. For every `jakarta.*` type any catalog names, does a `javax.*` counterpart exist, is it handled, and which failure mode applies — *renamed, nothing published* versus *renamed, partial data published* | §3.3 | — | the table that decides W12's scope, and stops the one-at-a-time habit that let four instances accumulate |
| **W12** | `javax-jms.yml`, and every twin W11 found. Correct COVERAGE's false indicative *"Both must be matched"* | §3.3 | W9, W11 | Boot 2's raw-JMS surface becomes visible; pre-Jakarta outbound SOAP operations get their identity back |
| **W13** | Spring Cloud Stream: a cardinality conjunct mirroring the measured binding rule (one binds, two or more bind nothing); **remove the protocol default entirely** — an unmapped binder yields no row plus an open question. Close the ratchet hole: the defaulted-value rule must watch catalog data, not only engines | §3.4 | W9 | the one defect that leaves our bundle and corrupts another consumer's data is gone |
| **W14** | **MEASURE:** per framework, do class-level and method-level listeners register independently — Kafka, Rabbit, SQS — and does `@KafkaHandler` / `@RabbitHandler` behave differently from a second `@KafkaListener`? | §3.5 | — | the measurement W15 encodes |
| **W15** | The relationship conjunct: a catalog declares **PREFIX** (HTTP) or **SIBLING REGISTRATION** (messaging). Fix the addresses-nothing gate so it catches an address that is *wrong*, not only one that is *empty* | §3.5 | W14 | `"orderspayments"` stops being published; two real topics are derived instead. The gate fix also guards W4's composed addresses |
| **W16** | RSocket versus STOMP: gate on which handler auto-configuration the dependencies registered; `@ConnectMapping` as positive RSocket evidence; **both starters present → two rows**; neither resolvable → open question | §3.6 | — | RSocket controllers stop being published as `websocket` |
| **W17** | WebFlux `@Controller` — a WebFlux-coordinate catalog or widened coordinates, decided by measuring the two gates | §3.7 | — | a WebFlux `@Controller` derives its endpoints |
| **W18** | `PubSubTemplate`'s nine unread inbound methods; replace the unread `.startAsync()` conjunct with the §8.6 chain test | §3.9 | — | pull-based Pub/Sub consumers stop deriving nothing |
| **W19** | The per-catalog enumeration pass; declare the six slices in the catalogs | §3.8 | W9 | catalog presence stops meaning completeness and starts meaning "this much, exactly" |

**Wave 2 acceptance:** a `JmsOperations`-typed send derives a row; an unmapped binder derives
zero rows and one open question; a class-level plus method-level Kafka listener derives two
rows; a method serving both RSocket and STOMP in a build carrying both starters derives two.

---

## Wave 3 — F3: method identity and method resolution

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W20** | Catalog matching ignores the return portion of the descriptor — identity is name plus parameter types (JLS 8.4.2). Where a rule genuinely *is* version-specific, the `measured:` block plus resolved versions states the range | §4.1 | — | every Spring Kafka 2.x producer stops deriving nothing; 12 catalog rows stop being version-dependent by accident |
| **W21** | `spring-petclinic-rest` enters the acceptance corpus | §4.2 | — | the suite can fail for the right reason. Measured: petclinic scores 96 for the superclass-call shape; orders-service and mall-admin score 0, which is why the current suite notices neither of Wave 3's Criticals |
| **W22** | `type_hierarchy` (child, ancestor, kind, search position, **scanned**) and `method_resolution` ((class, name, descriptor) → declaring class, or a stated reason). JVMS 5.4.3.3/5.4.3.4, one pass, never cached. **Separate "external boundary" from "unresolved."** Wire the servlet intermediate base in the same change | §4.2 | W21 | 21% of one real document's boundary steps stop being false; six stated COVERAGE boundaries become derivable |
| **W23** | `return_flows` resolves inherited accessors | §4.2 | W22 | a getter declared in a superclass stops reading as a boundary |

**Wave 3 acceptance:** a call to a method declared in a scanned superclass resolves to its
declaring class; a call whose owner was never scanned is *external boundary*; a call we
scanned and could not resolve is *unresolved*, with a reason — and the two are distinguishable
in the data. petclinic's 96 instances resolve.

---

## Wave 4 — F4: the module edge

The largest single visible improvement in the plan. Measured today on mall-admin: 160 of 160
endpoints carry a response shape, **one** distinct shape, **zero** fields.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W24** | Read a sibling module's **types** — once, shared by shapes, `type_hierarchy` and traces. Sibling detection already exists (the Maven `<modules>` walk, Gradle settings) and the compiled output is on disk. Plus any declared `extract_libraries`. Never arbitrary third-party jars. Guardrail: read types, never derive rows | §5.2 | W5, W22 | (foundation — W25 and W26 cash it in; three implementations of "look next door" avoided) |
| **W25** | Full generic substitution across the module edge; `origin_tier` on an expanded shape; a **stated boundary naming `extract_libraries`** where a type is unreachable, replacing today's silent empty shape | §5.2 | W24 | `CommonResult<OmsOrderDetail>` and `CommonResult<Integer>` become distinct shapes with fields. DR-5's payload conjunct becomes satisfiable, so stitching becomes possible on a standard multi-module Spring layout |
| **W26** | `Page` / `Slice` / `ResponseEntity` / HATEOAS envelopes, several declared nowhere today | §5.2 | W25 | paged and wrapped responses carry their real payload type |

**Wave 4 acceptance:** mall-admin's 160 endpoints carry more than one distinct response shape,
and the shapes carry fields.

---

## Wave 5 — F5: endpoint identity, and never merging what we cannot observe

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W27** | Outbound is never merged — one row per (caller, target); collapse only **within** one caller. Delete `merge_endpoints.sql`'s `both` merge; reserve `both` for the linking tier | §6.1 | — | two callers hitting the same path stop being reported as one call |
| **W28** | Inbound duplicates become a **reported conflict**, not a dropped row — DR-6, mirroring Spring's own refusal of an ambiguous mapping. This is the documented-but-unimplemented routing-ambiguity detector | §6.1 | — | two handlers claiming one route surface as the error they are |
| **W29** | Request metadata on every outbound protocol — HTTP headers and query parameters, Kafka record headers and partition key, AMQP routing key and properties, JMS properties, SQS attributes, Pub/Sub attributes. A side table keyed by endpoint, **each entry carrying its own resolution and evidence** | §6.2 | W9 | an outbound call becomes identifiable; a header we could not resolve is visibly unresolved rather than absent |

**Wave 5 acceptance:** self-publish/self-consume produces two rows and one open question, never
a merge.

---

## Wave 6 — F7: the trace tier meets FR-6 and FR-7

2Q is **not delivered** until this wave lands; under C11 the roadmap row is what changes, not
PROJECT.md's.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W30** | `terminal_kind` gets a producer: known owners as ordinary **catalog data** (MyBatis mapper, Spring Data repository, JDBC driver, `EntityManager`), plus the closed set of kinds derived from the corpora — not invented. The residue goes to enrichment at `evidence: llm` | §8.2 | W19 | a performance query stops returning method names a human must classify by eye |
| **W31** | FR-6: the walk terminates at a terminal or a stated boundary. The **depth bound** goes; cycle and revisit refusal stay, because those are correctness | §8.1 | W22, W30 | a trace stops short only where the evidence stops |
| **W32** | Fork 3: a `narrowed` step renders as a Mermaid `alt` when the alternatives are known, and as **one arrow labelled with them** when they are not. The caption stops claiming "nothing is filtered". Ships with a test that constructs the shape — `narrowed` has never fired on real code (four corpora, zero occurrences) | §8.3 | — | a diagram stops reading as "it calls all three, in order" when the truth is "exactly one of these three" |
| **W33** | Class diagrams of inheritance: two arrow kinds (`<|--`, `<|..`) over `type_hierarchy`; an unscanned ancestor renders `<<open>>` rather than being omitted | §8.4 | W22 | FR-7's class-diagram clause is met |

**Wave 6 acceptance:** PROJECT.md and the roadmap agree on 2Q, and the status is derived from
these tests.

---

## Wave 7 — F8: the bundle carries everything, and an index an agent can use

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W34** | `_EXPORTED_TABLES` becomes every table and view in the schema, each with a deterministic order. **The ratchet inverts:** a table in the schema and absent from the export is a test failure | §9.1 | — | the 1,916 dropped rows travel; a consumer can recompute and check what the pictures assert |
| **W35** | The symbol index (symbol → file path, line range, kind, enclosing), the reverse indexes (callers, implementors, endpoints-carrying-shape, annotation holders) and the address index (`GET /order/list` → root → handler → `file:line`) | §9.3 | W6, W22 | Sextant can finally say **where**, not only **what** |
| **W36** | The file digest and the change-impact starting points | §9.3 | W35 | an agent decides whether to open a file at all; "change `Order`" returns a list of `file:line` ready to open |
| **W37** | Materialisation: `call_edges` ordered by caller **and** a second ordering by callee; a materialised reachability table (root → reachable symbol, depth, terminal flag) — **the trace walk already computes this and throws it away**; `roots` addressable by wire address | §9.4 | W31, W34 | traversal runs both directions at speed; blast radius stops being recomputed per question |
| **W38** | FR-17 clause 3 — the resolution distribution, one `GROUP BY` on a column that already exists | §9.5 | W22 | `coverage` reports how much we **understood**, not only how many files we opened. The standing instrument against corpus blindness |
| **W39** | Multi-release **selection** at resolve: highest `N ≤ target` among copies of one name, else base; a name with one candidate is always kept. Target from the build's declared release, then the module's class-file major, then base with an open question on disagreement | §2.4 | W3, W34 | the duplicates W3 labelled are actually filtered — without this the bug is only renamed |

**Wave 7 acceptance:** a redacted bundle contains the same tables as an unredacted one;
symbols carry real line numbers and openable paths on all four corpora.

---

## Wave 8 — F6: the checklist gains axes

Runs late because every foundation reports into it, except W40 which is independent and cheap.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W40** | Fix the malformed §5.12, §5.2 and §8 tables — 14 rows carry five columns under a four-column header, so 11 Java rows lose their status cell in any renderer. A test asserts column count against header count | §7.3 | — | 2O Task 9's delivery record, OI-1's record, and a row reading *"none of them is read"* stop rendering as their own Shape value |
| **W41** | §5 gains axes beyond protocol: language construct, shape and contract, configuration source, trace and diagram, bundle and export, question ledger, rendered document | §7.2 | — | a non-protocol item has somewhere to exist; the 12 committed items enumerated nowhere get a home |
| **W42** | Enumerate **everything** with a support level — supported, partially supported, unsupported. Q2's Kotlin boundaries, Q3's four out-of-scope surfaces, Q4's six slices, W8's not-read set. Enumerate what Kotlin actually supports: §5 has 0 Kotlin rows of 170 while `coverage_matrix.py` **aliases Kotlin to Java**, asserting a parity nobody checked | §7.4 | W41, all waves | the standing requirement is met: nothing we are not delivering is left to silence |

---

## Wave 9 — F10: the five asymmetries

A half-shipped surface is worse than an absent one. Each is small; the engine and vocabulary
already exist for the other direction.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W43** | `SimpMessagingTemplate.convertAndSend` — STOMP outbound | §11 | W9 | a service that both receives and sends STOMP gets its whole messaging surface |
| **W44** | Spring MVC functional routing (the WebFlux twin is catalogued) | §11 | W9 | `RouterFunction` routes derive |
| **W45** | `StompEndpointRegistry.addEndpoint` | §11 | W9 | the URL clients actually connect to |
| **W46** | The WebSocket client direction | §11 | W9 | outbound WebSocket |
| **W47** | `@MessageExceptionHandler` (the HTTP twin `@ControllerAdvice` ships) | §11 | W9 | messaging error handling |

---

## Wave 10 — F11: the curation file

Lands after the waves that produce open questions — building the schema first would ship a
file with nothing to put in it.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W48** | The curation file: schema, its own evidence tier ranked above derived and enriched, and a test that **no curation input can change a fact file or delete a derived row**. Where derived and curated disagree, both are kept and the disagreement is reported | §12 | W27, W29 | a human can state that a Pub/Sub publisher and its consumer are the same channel — which DR-5 structurally cannot derive, because a topic name is not a subscription name and the binding lives in GCP |
| **W49** | Sextant emits the open question **in the curation file's own schema**, listing candidate pairs for the identifiable indirect-channel class (Pub/Sub and SNS→SQS never derivable, AMQP sometimes, Kafka always) | §12 | W48 | accepting a proposal is an edit, not an authoring job |

---

## Wave 11 — F9: the registers tell the truth

Runs last for the RESTATE batch, because restating a claim before the code makes it true only
moves the untruth. W50 and W51 can start once their subject waves land.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W50** | PROJECT.md rewritten to the evidence and kept as the delivery authority. Where it and the roadmap disagree, the **stricter** wins | §10.1 | Waves 1–10 | the registers stop disagreeing about what shipped |
| **W51** | REQUIREMENTS.md: FR-11…FR-14 move out of the FR section and become **usage scenarios**, each naming the capability it depends on; FR-21…FR-24 fold in as **real FRs** with traceability rows; FR-16 is rewritten around the curation file; FR-20 clause 2 is restated to say approximate lookup happens against the index and commands take exact identifiers. `M04-resolver.md:213-215` and `D01:597` stop asserting the resolver computes findings | §10.2, §10.3, §10.4 | W48 | the requirements say what Sextant does, and what it merely enables |
| **W52** | The RESTATE batch — 39 documentation claims that are untrue or untested, corrected as one batch. **Rule:** a sentence in the indicative describing untested behaviour is either given a test or rewritten to say what is true | §10.4 | the wave whose claim it restates | C7's *"Both must be matched"* was the template: a true-sounding sentence that stopped anyone looking |
| **W53** | The MEASURE batch residue — G-22, G-46, G-88, G-91, G-122 and G-27. **Rule:** measurement means reading the framework's own class files at a named coordinate and version, recorded in `measured:` | §10.5 | — | *"it is just a rename"* stops being an argument |
| **W54** | The test-debt batch: G-110's untested rows, and G-112's `_NO_DECLINING_TEST_YET` markers (25 of 55 catalogs, and it **over-states** the gap for `jakarta-websocket`). **Rule:** a row marked `supported` has a test naming it — the rule the mutation harness already enforces for guards, extended to coverage claims | §10.6 | W42 | a claim of support cannot stand with nothing that would fail if it broke |

---

## Sequencing summary

```
W1 W2 W3 W4 W5 W6 W7 → W8            F1  extractor          (nothing derived changes yet)
W9 → W10 W12 W13 W15 W19 W29 W43-47  F2  vocabulary         (new rows appear)
W11 W14 (measure, no dependency)
W16 W17 W18 W20 W21 (independent)
W21 → W22 → W23                      F3  identity           (21% of boundaries stop being false)
W5 W22 → W24 → W25 → W26             F4  module edge        (mall's contracts become real)
W27 W28 W29                          F5  endpoint identity
W19 → W30 → W31; W22 → W33; W32      F7  trace tier         (2Q becomes delivered)
W34; W6 W22 → W35 → W36; W37 W38 W39 F8  export and index   (Sextant can say WHERE)
W40; W41 → W42                       F6  the checklist
W27 W29 → W48 → W49                  F11 curation
W50 W51 W52 W53 W54                  F9  registers
```

**Five hard constraints, from spec §14.** F1 is first. F2 before Wave 9. W21 (the corpus)
before W22, not after. F11 after the waves that produce open questions. Every RESTATE entry
after the foundation whose claim it restates.

**Where the visible value lands:** Wave 2 (new rows), Wave 3 (boundaries stop being false),
**Wave 4** (100% of mall's response contracts go from empty to real — the largest single
improvement), Wave 6 (2Q becomes true), Wave 7 (an agent can navigate the codebase).
