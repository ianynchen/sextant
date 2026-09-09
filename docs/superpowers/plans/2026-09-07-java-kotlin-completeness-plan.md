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

**Every factual claim here is checked against the repository, not against the conversation
that produced it.** The first draft of this plan asserted that Wave 1 changed no derived
output; it was false for two of eight items, and it told a reviewer not to look. The same rule
the spec carries applies here: a claim about our own code is either verified or removed.

### The gate — this plan is proved on real projects, not on tests

**Ruled 2026-09-07.** The suite is 2,346 tests, 82 guards at 0 survived, byte-stable,
contracts clean — and it notices neither of the two hardest Criticals, because our corpora do
not contain the shape. `scripts/field_check.py` already validates output against real
upstream repositories at pinned commits; it holds **three** projects, all inbound-only HTTP
CRUD, with **zero outbound rows between them**. Every messaging and RPC catalog we ship is
exercised by no real project.

- **At least twelve projects**, chosen by the surfaces they exercise — one per protocol with a
  shipped catalog, plus Boot 2, plus Kotlin, plus a real multi-module build. A surface with no
  findable example becomes a stated boundary, never a silent zero.
- **Selected when the work is done**, not now.
- **Run after every wave**, not only at the end.
- **A pin freezes behaviour**, so a defect visible in a pin is fixed before the pin is
  refreshed.

Spec §1.4 carries the evidence.

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

## Wave 0 — the precondition

*Both items landed before Wave 1 and were never ticked. Confirmed against their own
acceptance criteria at W22: `fact_schema_version` is a plain `int` and the extractor takes
it as `--fact-schema-version` rather than holding a copy, so Python owns the number
(`api.py:472` compares it for equality); `_EXPORTED_TABLES` is derived from the query dict
and `Workspace.schema_objects()` reads DuckDB's own catalog, with
`tests/storage/test_workspace.py:819` running the direction that catches the defect. An
unticked row that is done misleads a reader exactly as badly as a ticked row that is not.*

Lands **before** Wave 1. Wave 1 makes the largest fact-shape change the project has had, and
bumping a stamp that is already inconsistent means the bump cannot be verified — a correct new
value would be indistinguishable from a fourth wrong one.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W0** ✅ | `fact_schema_version` becomes a **single monotonically increasing integer, set to 2** — no semver, because the value is never parsed or ordered anywhere and `api.py:472` compares it for equality only. **Remove the Java copy**: the extractor takes it as a command-line option, so Python owns the number. **A test asserts the remaining copies are equal.** Existing workspaces stamped `1.0.0` / `1.1.0` are refused by the stamp gate and re-analysed — not migrated | §1.3 | — | a workspace's documents and its `metadata.json` stop disagreeing about which schema produced them. Measured today: four copies, two values, and the one producer whose shape actually changed (`ingress/read/*`, which gained `operation`) is the copy that was never bumped |

| **W34** ✅ | `_EXPORTED_TABLES` becomes **every table and view in the schema**, each with a deterministic order. **The ratchet inverts:** a table in the schema and absent from the export is a **test failure**. Redaction is unaffected — it replaces values, it never drops a table | §9.1 | — | the 1,916 rows G-8 silently dropped (`call_edges` 1,393 · `return_flows` 444 · `roots` 79) travel, so a consumer can recompute and check what the pictures assert |

**Why W34 is here and not in Wave 7.** Its dependency column is `—`: nothing blocks it. It was
in Wave 7 because it is thematically "export", grouped by subject rather than by need — and
two later items add tables (**W22** in Wave 3: `type_hierarchy`, `method_resolution`; **W29**
in Wave 5: request metadata). A safety net installed after the things it protects is not a
safety net, and for four waves we would have been recreating G-8 exactly. Moving it first also
delivers the 1,916 rows on day one, which is one of the few items here with immediate visible
value.

**Adding a table now asks two questions at once**, both answered by whoever writes the
`CREATE TABLE`:

1. **Does it export?** Automatically, and the ratchet fails the build if it somehow does not.
2. **Does analysis read its values?** Yes → keep the real value, redact at export. No → redact
   at origin. There is no third answer (§6.2).

| **W0b** | **Re-run `field_check.py` against all three existing pins and establish the real baseline.** Two are stale: `spring-petclinic-rest` and `jhipster-sample-app` were recorded 2026-09-03 06:17, and the canonical-address gate — which normalises a leading separator — landed 2026-09-03 22:06. The petclinic pin still records 25 of 44 routes with no leading slash and 8 bare `/` routes, one per HTTP verb. Find what actually differs, fix what is a real defect, re-record deliberately | §1.4 | — | we learn whether the field check passes today. Every later pin is recorded against known-good behaviour instead of freezing whatever is there |

**Wave 0 acceptance:** every producer stamps the same value; a workspace written before
Step 0 is refused with the stamp named, not silently accepted. Every table and view in the
schema is exported with a deterministic order, and a table absent from the export fails a
test.

### Wave 0 — DONE 2026-09-07. Four rulings taken during execution, all by the user.

1. **The stamp is a JSON number**, not a numeric string. `Document.fact_schema_version` is
   `int`; the extractor parses its option and refuses a non-integer rather than emitting an
   unparseable fact file.
2. **`graph_schema_version` becomes an integer too, also `2`.** Same three properties as the
   fact stamp — never parsed, never ordered, compared for equality at `api.py:470` and
   nowhere else — so the spec's "the ruling named the fact schema only" was drawing a line
   its own reasoning did not support.
3. **There are no remaining Python copies to test for equality**, so the planned equality
   test does not exist and is not owed. The spec assumed the two restatements had to stay;
   they did not. `domain` sits at the bottom of the import-linter layering with both
   restating modules above it, and only `application` importing `ingress` was ever forbidden.
   Both now import `sextant.domain.version`, which makes drift **structurally impossible**
   rather than merely detected — the same argument that chose C over B for the Java copy,
   applied consistently. `SEXTANT_VERSION` moves the same way and is read from the installed
   distribution, so `pyproject.toml` owns it.
4. **`raw_facts` exports as parquet as well as travelling as the fact stream**, so the
   ratchet has no exclusion class at all. Both join the same redaction map, so the two shapes
   of one table cannot disagree.

**W34's redaction, which the plan did not enumerate and the schema demanded:** `roots.path`
joins the address map its value is carried from; `return_flows.value` and
`method_returns.value` join the JSON map (all four columns of that grammar come from the same
string constants); `config_entries.value` takes the same `redact_value` keyed on the same
`key_path` that masks it in the fact stream. Each answers §6.2's one question — *does analysis
read this?* — and each new guard was mutation-checked to confirm it discriminates.

**W0b's baseline is three of three green**, and it corrected two claims rather than merely
confirming them — see spec §1.4. `OI-32` is closed; its own count was wrong (13 recorded, 25
measured) and repeated in `docs/RUNBOOK.md`, both corrected.

---

## Wave 1 — F1: the extractor reads the class file as a specified format

Six later items consume facts produced here, and three of them are impossible without it.

**Six of these eight items are purely additive. Two are not, and they need golden-file
review:** W4 (`InnerClasses`/`EnclosingMethod`, which removes the downstream `$`-splitting)
and W7 (`ACC_ANNOTATION` changes what an `@interface` reports, and `module-info.class` stops
emitting a fabricated `class` symbol — `construct_kind` is read by `derive_endpoints.sql` at
`:1076` and `:1099`). An earlier draft of this plan said Wave 1 changed no derived output.
That was wrong for those two, and it told a reviewer not to look.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W1** ✅ | The accepted major range becomes a test; the observed major is recorded per document (a **new** capability, not an existing one); `partial` / `partial_reason` get a code path that can set them; `Main.java:83`'s blanket `catch` stops taking the whole scan down with one unreadable class; **`scanner_version` stops naming a library version that does not exist** — it reads `"9.18"`, a capability number, while the pinned ASM is 9.10.1. *(The ASM bump itself is already done — commit `0674bfd`.)* | §2.1 | W0 | one unreadable class stops killing the scan; a skipped class says why, in the manifest and the document; a bundle's provenance names the scanner that actually produced it |
| **W2** ✅ | Override `visitAnnotableParameterCount`; align parameter annotations from the end (JVMS 4.7.18). Test uses an **enum** constructor, not only an inner class | §2.2 | — | annotations on inner-class and enum constructors stop landing on the wrong parameter |
| **W3** ✅ | Multi-release jars, extractor half: read `Multi-Release` once at `JarSource` open as a parsed attribute; absent → skip `META-INF/versions/` entirely; tag every document with `class_release`; strip the prefix in `sourcePathOf` | §2.4 | — | `testcontainers-2.0.5.jar` stops emitting 1,198 phantom documents; overlay documents stop naming impossible `.java` paths |
| **W3b** ✅ | **Read the build's declared release.** `maven.compiler.release`, `maven.compiler.target`, `maven.compiler.source`, `java.version`, and maven-compiler-plugin's `<configuration><release>`; on Gradle, `targetCompatibility` / `release`. Nothing reads any of them today — `verify: grep -rn "maven.compiler\|targetCompatibility\|sourceCompatibility" src/` returns nothing. Both halves use machinery that exists: the Maven detector already merges `<properties>` across parent inheritance (`maven.py:576-602`), and the Gradle detector already runs Gradle with an init script and reads JSON back, so Gradle itself can be asked. A module whose build declares none reports absence, never a guess | §2.4 | — | the selection target in W3c gets its primary source; `class_release` selection stops depending on a capability nothing builds |
| **W3c** ✅ | Multi-release **selection**, at resolve: highest `N ≤ target` among copies of one name, else base; a name with exactly one candidate is always kept, so the 626 versioned-only classes survive. Target from W3b's declared release, then the module's own class-file major (W1), then base with an `open_question` on every class where base and an overlay disagree | §2.4 | W3, W3b | the duplicates W3 labelled are actually filtered. **Without this, G-62 is renamed rather than fixed** — which is why it sits beside W3 rather than six waves away |
| **W4** ✅ | JVMS 4.7, the four that already force an invented rule: `AnnotationDefault`, `InnerClasses` + `EnclosingMethod`, `StringConcatFactory`'s recipe, `ConstantValue`. **Each read gets a declared capability**, or no catalog can require it | §2.3 | — | the `constant` fact kind gets its FIRST producer; a nested class states its encloser — including, for an anonymous one, the enclosing METHOD; an assembled address reads as a template (`/api/{}/orders`) instead of `unresolved`; an annotation element's declared default becomes readable. **The two CONSUMERS this row used to claim — catalogs reading real defaults, and nesting no longer split on `$` — are W4a and W4b below, not W4** |
| **W5** ✅ | `Signature` completed: method and constructor **parameter** types, and class/method formal type parameters with bounds | §2.3 | — | **Not only foundation, as it turned out**: two frozen gaps in the messaging fixture close outright — a batch listener's `List<OrderEvent>` now carries its element, and a `ConsumerRecord` envelope now reaches its payload through the catalog's own `payload_arg`. `type_parameters` is the foundation half, and **W25** cashes that in (OI-46). Alignment is by `MethodParameters` flags, never by counting — a local class that captures puts its synthetics LAST (OI-47 records the two consumers that compare type-variable symbols across declarations) |
| **W6** ✅ | `LineNumberTable`, `SourceFile`, `LocalVariableTable` / `LocalVariableTypeTable` | §2.3 | — | §9.2's keystone finding closed: **every line number in the estate was 0**, and 707 fixture symbols / 7,525 of spring-web's 8,320 now carry real ones. `SourceFile` replaces a derivation that named `.java` files that do not exist for every Kotlin class. `LocalVariableTable` supplies 1,048 of spring-web's 9,164 parameter names that no other attribute states. **W35** cashes the index in. **`LocalVariableTypeTable` is deliberately not read**: measured, it adds a local's generic signature where the plain table has the erased one, while the NAMES W6 wants are in the plain table and the generic parameter types already come from `Signature` (W5) — so it would duplicate what is read, and it goes to W8's ledger as a stated skip rather than an omission |
| **W7** ✅ | The remainder of JVMS 4.7: `NestHost`, `NestMembers`, `PermittedSubclasses`, `Exceptions`, `Record`, `Module`, `ModulePackages`, `ModuleMainClass`, `SourceDebugExtension`, `Deprecated`, class-level type annotations, `visitAttribute`; plus the 11 dropped access flags | §2.3 | — | `ACC_VARARGS` unblocks capability 9.15; an `@interface` stops emitting `construct_kind: "interface"`; `record` and the eleven flags get their first producers; `module-info` and `package-info` stop minting phantom types (G-61). **Three named items are deliberately NOT read, each with its reason**: `Module`/`ModulePackages`/`ModuleMainClass` (module identity comes from the build's coordinates, and `module-info.class` is suppressed whole so `ModuleMainClass` has no visitor to read it from — measured over 1,672 cached jars, 383 carry a module descriptor and 6 of those do declare a main class, so OI-22 stays open on that ground rather than on nobody declaring one), `LocalVariableTypeTable` (duplicates `Signature`), and class-level type annotations (no consumer reads a supertype's). They go to W8's ledger as stated skips |
| **W8** ✅ | The read/not-read ledger: one enumerated `deliberately-not-read` set with a stated reason per entry, and a test that fails on "declared, never read". `module-info.class` stops minting a fabricated `class` symbol (G-61) | §2.3, §2.5 | W4–W7 | `✅ ASM` in COVERAGE becomes a claim that means something |

**W4a and W4b — fast-follow, after the W items** (ruled 2026-09-07). W4's Delivers column
claimed two user-visible changes that the ATTRIBUTE READS alone cannot produce, and a review
caught the row claiming them. Both are larger than the phrase implied, which is why they are
their own items rather than a finishing touch:

| # | Item | Why it is not a one-liner |
|---|---|---|
| **W4a** | A catalog reads an annotation element's DECLARED DEFAULT instead of a number typed in from documentation | Nothing in `resolve/` reads `annotation_default`, so this needs catalog-grammar vocabulary — and `D02:634` currently states *"a declared default is not written into the class file"*, which W4 made false, so it needs a D02 amendment too. Until then a framework changing a default makes our answer **silently wrong** |
| **W4b** | Nesting comes from the `enclosing` fact, not from splitting a class name on `$` | `outer_type_of("A$B$C#")` answers `A#` — the TOP-LEVEL type, from a string — while the fact gives `A$B#`, the immediate encloser; reaching top-level is a walk of repeated joins. The function also lives in `domain/`, which the import-linter contract forbids from querying the workspace, so this is a layering change |

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
| **W9** ✅ | **Nineteen** of §3.1's 21 sites accept a scalar **or** a list, plus `matches.steps[].owner` which the design did not list — twenty keys in all; each alternate carries its own `measured:` provenance; a scalar stays valid. The other two (`identity_marker`, `supertype_marker`) hold a mapping of CALL specs, not a type name — the design's list named the wrong level, recorded as OI-51's sibling **OI-54** | §3.1 | — | (foundation — W10–W12 cash it in) |
| **W10** ✅ | Owner alternates applied: `JmsOperations`, `SqsOperations`, `AmqpTemplate`, `KafkaOperations`, `RestOperations`, Kafka's `Consumer<K,V>` and `Producer<K,V>` | §3.2 | W9 | interface-typed clients — the idiomatic Spring construction — stop deriving nothing |
| **W11** ✅ | **MEASURE:** the javax/jakarta mechanical sweep. For every `jakarta.*` type any catalog names, does a `javax.*` counterpart exist, is it handled, and which failure mode applies — *renamed, nothing published* versus *renamed, partial data published* | §3.3 | — | the table that decides W12's scope, and stops the one-at-a-time habit that let four instances accumulate |
| **W12** ✅ | `javax-jms.yml`, and every twin W11 found — **three gaps, and W11 showed they fail in three DIFFERENT ways**, the third of which §3.3 does not name: a NEGATIVE list (`excludes`) naming one spelling publishes a wrong contract rather than nothing. COVERAGE's false indicative corrected with the three-way table | §3.3 | W9, W11 | Boot 2's raw-JMS surface becomes visible; pre-Jakarta outbound SOAP operations get their identity back; a Boot 2 `@JmsListener` stops publishing the JMS envelope as its payload |
| **W13** ✅ | Spring Cloud Stream: `mapping.unselected_binds: sole` mirrors the framework's measured rule (`eligibleFunction.size() == 1` — one binds, two or more bind nothing); the protocol default is REMOVED, so an unmapped binder derives no row and files a new `binder_protocol` question. The ratchet hole is closed by two guards rather than by the offline audit, which reads catalogs and could not see a default living in an engine's fallback — recorded in that file's own docstring | §3.4 | W9 | the one defect that leaves our bundle and corrupts another consumer's data is gone |
| **W14** ✅ | **MEASURE:** per framework, do class-level and method-level listeners register independently — Kafka, Rabbit, SQS — and does `@KafkaHandler` / `@RabbitHandler` behave differently from a second `@KafkaListener`? | §3.5 | — | the measurement W15 encodes |
| **W15** ✅ | The relationship conjunct: `mapping.class_level` declares **`prefix`** (compose, the HTTP shape) or **`sibling`** (a method naming its own destination stands alone). Declared by `spring-kafka`, `spring-rabbit` AND `spring-sqs` — the last because `@SqsListener` gains `TYPE` at 4.1.1, a version its `measured:` block already names. Refused in the pre-flight, before any table is emptied. The addresses-nothing gate is UNCHANGED, and that is the finding: both instances §3.5 named are closed at their sources — the `StringConcatFactory` recipe by W7/W8 reading `BootstrapMethods` (holes arrive as `{}`, and "the template is the wire identity" is a stated rule), and `orderspayments` by the conjunct. An empty HTTP address canonicalises to `/`, which a controller genuinely serves, so the gate is correctly scoped to non-canonical protocols | §3.5 | W14 | `"orderspayments"` stops being published; a class listener and a method listener derive two rows |
| **W16** ✅ | RSocket versus STOMP, told apart by the BUILD — measured: Spring does not distinguish them on the class at all, both handler predicates test `@Controller` byte for byte, so no evidence gate could ever have worked. `spring-rsocket.yml` ships, `spring-stomp.yml` is re-gated, `rsocket` joins D00's protocol set, `@ConnectMapping` is RSocket-only positive evidence, both libraries present derives TWO rows, and a build recording NO coordinates earns a `handler_protocol` question rather than a guess. `detect.required` makes the gate real per-catalog: `detect.coordinates` was read by no `annotation_driven` catalog, so both gates were inert when written and the new catalog derived a SECOND row for the same controller | §3.6 | — | RSocket controllers stop being published as `websocket` |
| **W17** ✅ | WebFlux `@Controller` — **measured, and the stated bug does not exist.** All four shapes G-38 names derive identically in a `spring-webflux`-only build and a `spring-webmvc`-only one: this catalog's `detect.coordinates` is read by nothing (`DEPENDENCY_GATED` holds two other styles and it sets no `detect.required`), so the gate G-38 described never existed and the item was predicted from a key with no consumer. The widened-coordinates branch shipped anyway for a different reason — both stacks serve `@Controller` (the two `isHandler` predicates are four identical instructions at two versions each), so the one-stack list was false whether or not anything read it, and `detect.required` put it one line from being the real bug. G-38 withdrawn in the gap analysis; a second WebFlux catalog refused, because the insert dedups on protocol/direction/method/path and a twin would be silent dead weight | §3.7 | — | a WebFlux `@Controller` derives its endpoints |
| **W18** ✅ | `PubSubTemplate`'s nine unread inbound methods — all ten consuming methods now declared, descriptors measured at 5.1.2 and re-verified by CP-10 against real bytecode. The two families need DIFFERENT §8.6 chains and saying otherwise would have been wrong about two rows: the eight `pull*` calls ARE the consumption, while `subscribe`/`subscribeAndConvert` return a `Subscriber` and are boundaries only via the measured rule that `PubSubSubscriberTemplate.subscribe` starts it itself (offset 26) — recorded with its citation, and `OI-65` filed because nothing re-checks that link. **Second clause descoped to `OI-64`, pending approval** — it says to "replace the unread `.startAsync()` conjunct", and `google-pubsub-subscriber.yml` has no such conjunct; it states the opposite position outright. The over-report is real but closing it needs a terminal conjunct `interface_implementation` cannot express | §3.9 | — | pull-based Pub/Sub consumers stop deriving nothing |
| **W19** ✅ | The per-catalog enumeration pass; all six slices declared. `slice.outside` names, with a reason, every part of a framework's surface a catalog leaves out, and two enumeration probes measure it from the jars: **`RouterFunctions$Builder` 0 of 20** (the builder DSL derives nothing), **`SqsAsyncClient` 0 of 28** (`sendMessage` included, while the sync client derives), **`SqsClient` 1 of 29** (the whole inbound direction unread), **`RabbitTemplate` 1 of 88**, **`JmsTemplate` 1 of 49**, **`SqsTemplate` 1 of 12**, **spring-integration 2 of 13** channel-declaring annotations, **spring-data-rest 6 of 28** repository contracts. `netflix-dgs` is a stated boundary rather than a slice — it reads every name; the gap is a use site. **The probes were wrong six times before they were right, every one the same defect: a rule applied to a set that is not the framework's set** — a `throws` clause, an owner-blind name match, no superclass walk, a hand-written attribute list (twice), and a hand-picked artifact list. Each would have published a confident false zero, and three were caught only in review. G-41's recorded mechanism was falsified outright (`OI-67`) | §3.8 | W9 | catalog presence stops meaning completeness and starts meaning "this much, exactly" |

**Wave 2 acceptance:** a `JmsOperations`-typed send derives a row; an unmapped binder derives
zero rows and one open question; a class-level plus method-level Kafka listener derives two
rows; a method serving both RSocket and STOMP in a build carrying both starters derives two.

---

## Wave 3 — F3: method identity and method resolution

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W20** ✅ | Catalog matching ignores the return portion of the descriptor — identity is name plus parameter types (JLS 8.4.2), compared through `domain/symbols.parameter_types`. **Re-measured before the change rather than trusted: 96 declared descriptors in the 14 catalogs that declare any (§4.1 said 75 across 55 — the 55 was the catalog total, not the denominator), 16 carrying `CompletableFuture` rather than 12, and still ZERO collisions once the return type is dropped** — now a ratchet (`test_catalog_descriptor_identity.py`) so a later catalog cannot introduce one. Both Spring Kafka majors derive the same row from the same source; a call whose PARAMETER type differs still derives nothing | §4.1 | — | every Spring Kafka 2.x producer stops deriving nothing; **16** catalog rows stop being version-dependent by accident |
| **W21** ✅ | `spring-petclinic-rest` enters the acceptance corpus — **and the fixture gains the shape, because the corpus alone would not have delivered the item.** `scripts/field_check.py` is opt-in and network-using and is never part of `check.sh`, so pinning petclinic there leaves the GATE exactly as blind; `fixtures/orders-service` now carries the same shape (`model/BaseEntity` ← `Customer`, called through the subclass) and `tests/e2e/test_corpus_shapes.py` stops it returning to zero. **Petclinic scores 131, not the 96 §4.2 recorded** — the old rule dropped every subclass declaring no method of its own, and `PetType`/`Specialty` inherit everything — pinned in its expectation file and computed by walking the scanned ancestor closure on name AND descriptor (JVMS 5.4.3.3). `orders-service` and `mall-admin` both score 0, as §4.2 said: two cheaper rules were tried first and each was wrong in a different direction, one under-counting petclinic by 27% and the other reporting 5 phantom calls in mall-admin from a name-only match | §4.2 | — | the suite can fail for the right reason |
| **W22** ✅ | `type_hierarchy` (child, ancestor, kind, search position, **scanned**) and `method_resolution` ((class, name, descriptor) → declaring class, or a stated reason). JVMS 5.4.3.3/5.4.3.4, one pass, never cached. **Separate "external boundary" from "unresolved."** Wire the servlet intermediate base in the same change | §4.2 | W21 | **131 call sites in `spring-petclinic-rest`** stop reading as a third-party boundary and reach a body; **158 in the fixture** stop being indistinguishable from one. The servlet intermediate base closes. *Re-measured: the boundary-step figure is **15.0%** on petclinic (1939 → 1649) and **0%** on mall-admin; §4.2's 21% names no corpus and reproduces on neither.* 5.4.3.4's maximal-specificity rule is stated as NOT implemented rather than claimed |
| **W23** ✅ | `return_flows` resolves inherited accessors — **delivered by W22 with no change to `return_flow.py` at all**, which is what the gap analysis predicted when it ruled G-48 "CORRECT (rides G-1)": that module reads the same `dispatch_of`, so fixing resolution fixed it. Measured: `spring-petclinic-rest` gained **78** `return_flows` rows arising from inherited accessors (`Owner#getFirstName` → `Person#getFirstName`, `Owner#getId` → `BaseEntity#getId`); G-48 predicted 28, counting call sites where a row is emitted per return instruction. **An item delivered as a side effect has nothing holding it**, so a test pins the property on real bytecode and fails when superclass resolution is disabled | §4.2 | W22 | a getter declared in a superclass stops reading as a boundary |

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
| **W29** | Request metadata on every outbound protocol — HTTP headers and query parameters, Kafka record headers and partition key, AMQP routing key and properties, JMS properties, SQS attributes, Pub/Sub attributes. A side table keyed by endpoint, **each entry carrying its own resolution and evidence**. **Redacted at the origin** — nothing reads a header value, so only the redacted value is ever written; no export query, nothing to forget | §6.2 | W9 | an outbound call becomes identifiable; a header we could not resolve is visibly unresolved rather than absent; a compiled-in `Authorization: Bearer …` never reaches the bundle |

**Wave 5 acceptance:** self-publish/self-consume produces two rows and one open question, never
a merge.

---

## Wave 6 — F7: the trace tier meets FR-6 and FR-7

2Q is **not delivered** until this wave lands; under C11 the roadmap row is what changes, not
PROJECT.md's.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W30** | `terminal_kind` gets a producer for **the set D00 §4 already declares** (`outbound_call`, `returns`, `ends_silently`, `persistence`, `throws`, `unresolved`, `async_handoff`, `cycle`) — not a new one; NFR-5 gives it exactly one definition and `test_source_rules.py:158` enforces that. Known owners as ordinary **catalog data** (MyBatis mapper, Spring Data repository, JDBC driver, `EntityManager`), which is the framework knowledge D00 names as the missing piece. **`target_kind` (`database`, `cache`, `file`) is produced too.** Residue goes to enrichment at `evidence: llm` | §8.2 | W19 | a performance query stops returning method names a human must classify by eye, and says whether a call hits a database or a cache |
| **W31** | FR-6: the walk terminates at a terminal or a stated boundary. The **depth bound** goes; cycle and revisit refusal stay, because those are correctness | §8.1 | W22, W30 | a trace stops short only where the evidence stops |
| **W32** | Fork 3: a `narrowed` step renders as a Mermaid `alt` when the alternatives are known, and as **one arrow labelled with them** when they are not. The caption stops claiming "nothing is filtered". Ships with a test that constructs the shape — `narrowed` has never fired on real code (four corpora, zero occurrences) | §8.3 | — | a diagram stops reading as "it calls all three, in order" when the truth is "exactly one of these three" |
| **W33** | Class diagrams of inheritance: two arrow kinds (`<|--`, `<|..`) over `type_hierarchy`; an unscanned ancestor renders `<<open>>` rather than being omitted | §8.4 | W22 | FR-7's class-diagram clause is met |

**Wave 6 acceptance:** PROJECT.md and the roadmap agree on 2Q, and the status is derived from
these tests.

---

## Wave 7 — F8: the index an agent can use

*(F8's other half, W34, moved to Wave 0 — see there for why.)*

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W35** | The symbol index (symbol → file path, line range, kind, enclosing), the reverse indexes (callers, implementors, endpoints-carrying-shape, annotation holders) and the address index (`GET /order/list` → root → handler → `file:line`) | §9.3 | W6, W22 | Sextant can finally say **where**, not only **what** |
| **W36** | The file digest and the change-impact starting points | §9.3 | W35 | an agent decides whether to open a file at all; "change `Order`" returns a list of `file:line` ready to open |
| **W37** | Materialisation: `call_edges` ordered by caller **and** a second ordering by callee; a materialised reachability table (root → reachable symbol, depth, terminal flag) — **the trace walk already computes this and throws it away**; `roots` addressable by wire address | §9.4 | W31, W34 | traversal runs both directions at speed; blast radius stops being recomputed per question |
| **W38** | FR-17 clause 3 — the resolution distribution, one `GROUP BY` on a column that already exists | §9.5 | W22 | `coverage` reports how much we **understood**, not only how many files we opened. The standing instrument against corpus blindness |

**Wave 7 acceptance:** symbols carry real line numbers and openable paths on all four corpora;
an agent reaches a handler's `file:line` from `GET /order/list` without reading source.
*(The "a redacted bundle contains the same tables as an unredacted one" check moved to Wave 0
with W34.)*

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

## Wave 10 — F11: the curation file · **REMOVED FROM v1**

Ruled 2026-09-07. Its only consumer is the stitcher (M06), which does not exist — so W48 and
W49 would ship a format, a schema, an evidence tier and a no-mutation test with nothing that
reads any of them. It moves to phase L, designed together with M06, the only thing that can
say what the format needs. Spec §12 stands as the phase-L input.

**What stays in v1:** FR-16's *wording*, in W51. The shipped text describes something we have
now ruled we will never build, and correcting a false requirement is documentation work.

**Accepted:** the open questions this spec creates get no *human* channel in v1. They still
reach enrichment at `evidence: llm`, so they are not silent — what is absent is a person's
answer outranking a machine's.

---

## Wave 11 — F9: the registers tell the truth

Runs last for the RESTATE batch, because restating a claim before the code makes it true only
moves the untruth. W50 and W51 can start once their subject waves land.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W50** | PROJECT.md rewritten to the evidence and kept as the delivery authority. Where it and the roadmap disagree, the **stricter** wins | §10.1 | Waves 1–10 | the registers stop disagreeing about what shipped |
| **W51** | REQUIREMENTS.md: FR-11…FR-14 move out of the FR section and become **usage scenarios**, each naming the capability it depends on; FR-21…FR-24 fold in as **real FRs** with traceability rows; FR-16 is rewritten to describe a curation **file** that adds links and never edits a fact — the shipped text ("assert, correct, or delete a statement in the graph") describes something we have ruled we will never build; FR-20 clause 2 is restated to say approximate lookup happens against the index and commands take exact identifiers. `M04-resolver.md:213-215` and `D01:597` stop asserting the resolver computes findings | §10.2, §10.3, §10.4 | — | the requirements say what Sextant does, and what it merely enables |
| **W52** | The RESTATE batch — 39 documentation claims that are untrue or untested, corrected as one batch. **Rule:** a sentence in the indicative describing untested behaviour is either given a test or rewritten to say what is true | §10.4 | the wave whose claim it restates | C7's *"Both must be matched"* was the template: a true-sounding sentence that stopped anyone looking |
| **W53** | The MEASURE batch residue — G-22, G-46, G-88, G-91, G-122 and G-27. **Rule:** measurement means reading the framework's own class files at a named coordinate and version, recorded in `measured:` | §10.5 | — | *"it is just a rename"* stops being an argument |
| **W54** | The test-debt batch: G-110's untested rows, and G-112's `_NO_DECLINING_TEST_YET` markers (**27** of 55 catalogs — the gap analysis says 25; re-counted 2026-09-07 — and it **over-states** the gap for `jakarta-websocket`). **Rule:** a row marked `supported` has a test naming it — the rule the mutation harness already enforces for guards, extended to coverage claims | §10.6 | W42 | a claim of support cannot stand with nothing that would fail if it broke |

---

## Sequencing summary

```
W0 W34                               Step 0 stamp + export   (before everything)
W1 W2 W3 W3b → W3c; W4 W5 W6 W7 → W8 F1  extractor          (see the note below)
W9 → W10 W12 W13 W15 W19 W29 W43-47  F2  vocabulary         (new rows appear)
W11 W14 (measure, no dependency)
W16 W17 W18 W20 W21 (independent)
W21 → W22 → W23 W23b                 F3  identity           (21% of boundaries stop being false)
W5 W22 → W24 → W25 → W26             F4  module edge        (mall's contracts become real)
W27 W28 W29                          F5  endpoint identity
W19 → W30 → W31; W22 → W33; W32      F7  trace tier         (2Q becomes delivered)
W6 W22 → W35 → W36; W37 W38          F8  the index          (Sextant can say WHERE)
W40; W41 → W42                       F6  the checklist
W50 W51 W52 W53 W54                  F9  registers
```

**Seven hard constraints.** **W34 before any item that adds a table** — W22 and W29 both do,
and the ratchet has to exist before them or it protects nothing. **W0 before W1** — a stamp that is already inconsistent cannot be
verified when it is bumped. Then, from spec §14: F1 is first. F2 before Wave 9. W21 (the corpus)
before W22, not after. **W3c beside W3, not six waves later** — the tag alone renames G-62
rather than fixing it, and the only thing that had held the filter in Wave 7 was a dependency
on W34 that did not exist: an export list has nothing to do with a resolve-time filter.
*Where* the filter runs (at resolve, because the target belongs to the depending module) and
*when* it is built are unrelated, and an earlier draft conflated them.
Every RESTATE entry after the foundation whose claim it restates.
*(F11's constraint is gone with F11 — it moved to phase L.)*

**The gate runs after every wave.** A wave is not done because its items are done; it is done
when the field corpus still produces what it should. See "The gate" above.

**Where the visible value lands:** Wave 2 (new rows), Wave 3 (boundaries stop being false),
**Wave 4** (100% of mall's response contracts go from empty to real — the largest single
improvement), Wave 6 (2Q becomes true), Wave 7 (an agent can navigate the codebase).
