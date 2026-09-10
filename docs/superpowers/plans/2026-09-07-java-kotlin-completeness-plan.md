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

The largest single visible improvement in the plan. Measured before Wave 4 on mall-admin:
160 of 160 endpoints carry a response shape, **one** distinct shape, **zero** fields.

*Re-measured after W24 (2026-09-09), because the wave's headline claim is now wrong in
both directions and the next reader should not have to find that out:*

- **"100% of mall's response contracts go from empty to real" is ACHIEVED**, and the
  measurement that defined the problem is the one that says so: the complaint was one
  distinct shape with **zero fields**, and all 160 now carry real fields — `code`,
  `message`, `data`. That half landed with W24, reading `mall-common`.
- **Of those 160, 57 additionally carry a resolved payload type** and 100 do not, because
  `mall-admin`'s own source declares **100 bare `CommonResult`** against 60 parameterised
  — counted in the source, not inferred. A raw `CommonResult` states no payload type;
  recording its `data` as an undescribed field on an OPEN shape is the correct answer,
  not a shortfall. Inventing a type the code does not declare would be the fabrication
  §8 forbids.
- Response shape ids went **1 → 58** across the 160 endpoints. The distinct-parameterisation
  count in the source is **59** across 174 declaring methods, of which 10 are
  `CommonResult<T>` — an unbound variable, which roots no shape (§8.1 rule 2).
- *An earlier revision of this note called the 100% claim "not achievable". That was
  wrong: it read "real" as "carries a payload type", where the wave measured it as
  "carries fields". Both halves are worth stating, which is why both are above.*

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W24** ✅ | Read a sibling module's **types** — once, shared by shapes, `type_hierarchy` and traces. Sibling detection already exists (the Maven `<modules>` walk, Gradle settings) and the compiled output is on disk. Plus any declared `extract_libraries`. Never arbitrary third-party jars. Guardrail: read types, never derive rows | §5.2 | W5, W22 | (foundation — W25 and W26 cash it in). **The set is the DECLARED dependencies, transitively, not the reactor**: walking `<modules>` put two modules `mall-admin` does not depend on into its workspace — 246 endpoints against its own 160, and a neighbour's cron task in its document. Siblings ship as library roots with their own POM coordinates, so no new tier and no extractor change: a sibling you depend on IS a dependency, built from source. The guardrail runs BEFORE the endpoint merge (after it, a dependency serving an address this module calls took the module's own outbound row with it) and `schema_operations` filters its own roots (it mints rows with neither handler nor caller). `extract_libraries` is deliberately NOT covered: keying on the tier deleted the SOAP operation `test_vertical_slice.py` asserts an opted-in library contributes, and that surface is what a person asked for — consent is the difference, so the guardrail keys on `sibling_coordinates`. **Gradle not implemented (`OI-69`); analyse costs 67s against ~6s (`OI-68`)** |
| **W25** ✅ | Full generic substitution across the module edge; `origin_tier` on an expanded shape; a **stated boundary naming `extract_libraries`** where a type is unreachable, replacing today's silent empty shape | §5.2 | W24 | `CommonResult<OmsOrderDetail>` and `CommonResult<Integer>` become distinct shapes with fields. DR-5's payload conjunct becomes satisfiable, so stitching becomes possible on a standard multi-module Spring layout. **Scope, measured:** the ENVELOPE's fields landed with W24, so all 160 endpoints already carried a described contract; W25 distinguishes the parameterisations and substitutes the variable, taking response shape ids from **1 to 58**. The 57 bound shapes close; the 100 raw ones stay OPEN with an undescribed `data`, which is what a handler returning raw `CommonResult` actually states |
| **W26** ✅ | A payload type whose wire contract is in its **accessors**, not its fields — read where the fields describe nothing, across the scanned ancestry, with the same substitution W25 gives fields | §5.2 | W25 | **Both halves of this row's own premise were false, and measuring first is what caught them.** `ResponseEntity` is not "declared nowhere": **40 catalogs** declare it and it works. And `Page`/`Slice`/HATEOAS are not undeclared *wrappers* — declaring them as wrappers would be a **fabrication**, since a `wrappers` entry means the type vanishes on the wire and `Page` does not (Spring sends `{content: [...], totalElements: ...}`; spring-data-commons 3.5 added `PagedModel<T>` = `{content: List<T>, metadata}` for exactly this). The real cause: they are **interfaces**, so they declare no fields, and expansion read fields only. Measured on the fixture with the jar in reach: `Page<OrderView>` goes from an open shape with **0 fields to a closed one with 11**, `content` an **array of `OrderView`**. The rule is read from jackson-databind's own bytecode (`is` only on a boolean, bare `get()` names nothing, the leading run of capitals lowercased whole) and the ancestry walk is mandatory — `getContent()` is on `Slice`, not `Page`. Fixed on the way: W25's undescribed-object guard looked only at a field's own `wire_type`, so a raw `List<T>` reported its owner **closed**. HATEOAS appears in **zero files across all six corpora**, so nothing claims it |

**Wave 4 acceptance:** mall-admin's 160 endpoints carry more than one distinct response shape,
and the shapes carry fields.

---

## Wave 5 — F5: endpoint identity, and never merging what we cannot observe

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W27** ✅ | Outbound is never merged — one row per (caller, target); collapse only **within** one caller. Delete `merge_endpoints.sql`'s `both` merge; reserve `both` for the linking tier | §6.1 | — | **The row's first half was reported done and was not** — corrected by a dispatched reviewer. `derive_endpoints.sql`'s `unioned` does group by `caller` and `peer`, but that is the annotation-driven path; every outbound HTTP call comes from the CALL-SITE engines, whose `seen` set spanned the module and keyed on `(protocol, direction, verb, path)`. Measured: two callers, two hosts, one path → **one row**, second caller dropped outright with no gap row. RC-5 again, in a second place, worse than the merge it replaced. `caller` and `peer` are in the key now (`single_call`, `fluent`, `derive_call_endpoints.sql`), which brought back **four rows the fixture had been losing** including a SOAP call to a different billing address. The `both` merge was the real work, and the fixture had **six merged rows of which two were fabrications**: `{...}placeOrderRequest` carried `peer: ${soap.billing.uri}` — the module's own served SOAP operation and a call to the BILLING service as ONE endpoint, because they share a payload QName — and `POST /v1/orders` merged the module's handler with a call to `orders-loop`. The merge keyed on `(protocol, method, path)` and `peer` is not part of endpoint identity (RC-5), so a served path collided with the same path anywhere in the world. 141 endpoints became 147. The other four rows are genuine self-publish/self-consume, so the answer is a **question, not a rule**: a new `self_exchange` kind names each side and the address it reaches, and curation or the linking tier decides. `Direction.BOTH` stays in D00 §4 for that tier with no producer here. One gap retires by name: `merged_endpoints_keep_only_the_handlers_contract` — there is no merge to discard the client's contract any more |
| **W28** ✅ | Inbound duplicates become a **reported conflict**, not a dropped row — DR-6, mirroring Spring's own refusal of an ambiguous mapping. This is the documented-but-unimplemented routing-ambiguity detector | §6.1 | — | "Not a dropped row" was already true — `unioned` groups by `handler`, so two handlers on one address have always been two rows. The REPORTING half is the work, and it closes `documented-not-implemented` row 9. **Measured first, across four corpora: ZERO genuine conflicts, and one pair that looks like one and is not** — `@KafkaHandler` dispatches by payload type, so the fixture's `order-polymorphic` is correctly served by two methods. A global rule would have opened with a false finding against correct code, so `mapping.duplicate: conflict` is catalog data and only `spring-web`/`spring-mvc` declare it. The comparison follows `RequestMappingInfo.equals` read from spring-webmvc 6.1.6 bytecode — seven conditions, five and a half readable, `params`/`headers` unioned across class and method as `ParamsRequestCondition.combine` does — and the seventh, a custom `RequestCondition` that is code rather than an attribute, silences the analysis rather than being guessed at. Zero uses of `params=`/`headers=` in six repositories, so the fixture gained the near-miss nothing else had. **Its review found two false positives, both fixed**: the identity compared the FANNED-OUT verb, so a verbless `@RequestMapping` collided with a `@GetMapping` on the same path (mappings Spring registers side by side) and one conflict filed eight questions; and discriminators were read from the RAW annotation view while the row derived through the effective one, so a composed, folded or inherited `params=` read as absent. The methods condition is the "half": it reaches the detector only as its eight-verb expansion. Row 9 of `documented-not-implemented` is **narrowed, not closed** — the finding exists, the shared `endpoint_id` D01:296 also describes does not |
| **W29** ✅ | Request metadata on every outbound protocol — HTTP headers and query parameters, Kafka record headers and partition key, AMQP routing key and properties, JMS properties, SQS attributes, Pub/Sub attributes. A side table keyed by endpoint, **each entry carrying its own resolution and evidence**. **Redacted at the origin** | §6.2 | W9 | **Built: the table, the redaction, and HTTP headers.** On the fixture's `GET /v2/inventory/tagged` — `Authorization` = `«redacted»` (a compiled-in Bearer token that never reaches the table), `X-Tenant` = `acme`, and `X-Trace-Id` present-and-**unresolved**, which is the row the design is for: "sends a header we could not read" is not "sends no header". `collects` is a new capture kind because every existing one is LAST-WINS, which on three headers keeps the third and says nothing about the other two; a varargs position contributes one entry per value, since `header(String, String…)` is what the API declares. **The row said "every outbound protocol" and six of its seven entry kinds are not readable — measured, not assumed.** AMQP's routing key was ALREADY delivered (it is the address, at `address_arg_2`). HTTP query parameters ARE read, and so is the URL they are built with: `uri(Function)` hands a `UriBuilder` to a lambda, and the whole address used to go unread — the row derived with `path` NULL, which costs it the identity DR-5 links on. That was recorded as `OI-73` and then **fixed in the same session**, because the fixture derives two such rows and a Major with live instances is not a thing to file. The lambda's own synthetic method is walked as a chain of its own and its declared captures folded back. Kafka headers, SQS attributes, Pub/Sub attributes and JMS properties remain unread and share one cause: the entries are built as a map, a collection, or by mutation OUTSIDE the call the row came from, and chain reconstruction is within-method (D00 §5). Kafka's partition key is blocked by `OI-72`. Each is a stated boundary in COVERAGE §3a-vii rather than a guess. Two defects recorded on the way: **`OI-72`** — `payload_ctor_arg: last` reads a Kafka record's HEADERS as its payload, since two different 5-arity `ProducerRecord` constructors put the value at different indices; **`OI-71`** — metadata masking uses the built-in patterns only |

**Wave 5 acceptance:** self-publish/self-consume produces two rows and one open question, never
a merge.

---

## Wave 6 — F7: the trace tier meets FR-6 and FR-7

2Q is **not delivered** until this wave lands; under C11 the roadmap row is what changes, not
PROJECT.md's.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W30** ✅ | `terminal_kind` gets a producer for **the set D00 §4 already declares** (`outbound_call`, `returns`, `ends_silently`, `persistence`, `throws`, `unresolved`, `async_handoff`, `cycle`) — not a new one; NFR-5 gives it exactly one definition and `test_source_rules.py:158` enforces that. Known owners as ordinary **catalog data** (MyBatis mapper, Spring Data repository, JDBC driver, `EntityManager`), which is the framework knowledge D00 names as the missing piece. **`target_kind` (`database`, `cache`, `file`) is produced too.** Residue goes to enrichment at `evidence: llm` | §8.2 | W19 | Produced on `call_edges` and shown in the trace tables' new `Reaches` column, beside `Stop` — the two answer different questions and a step carries both. **Measured: 240 of `mall-admin`'s 5,352 terminals** (199 database, 41 cache), 102 of `spring-petclinic-rest`'s (82 `EntityManager`, 17 `ResultSet`, 3 `JdbcTemplate`), 70 of `jhipster-sample-app`'s (68 supertype, 2 `EntityManager`). The other 94-96% is `StringBuilder`/`Object`/`List` and reads `unresolved` — the terminal was examined and unclaimed, where NULL means it is not a terminal at all. **Three routes, one per framework, none a name match**: an `owner` type, a `supertype` read from the `superclasses`/`implementations` facts, or the packages a `scanned_by` annotation registers. mall-admin's mappers carry NO annotation — `@MapperScan`'s package list is how MyBatis registers them — and jhipster's repositories carry none either, but the class file says they implement `JpaRepository`. **Two things measurement caught that reasoning had wrong**: naming Spring Data's base `Repository` classified ZERO, because the supertype walk stops at the first UNSCANNED type — so a catalog must name the level a user extends; and the first version read the `type_hierarchy` TABLE, written after the edges by the same pass, so it read nothing. `java.sql.Date` is deliberately unclassified beside `java.sql.ResultSet`: same package, one is an API that reaches a store and one is a date. **TWO CLAUSES OF THE SPEC ARE NOT DELIVERED, and were deleted from this cell when it was ticked — restored here, W30 review.** (1) `target_kind: file` has no producer: no rule names an object-store client, though `io.minio.MinioClient` and `com.aliyun.oss.OSSClient` are both live on `mall-admin`. (2) **The residue does not go to enrichment at `evidence: llm`** — nothing hands the 94-96% `unresolved` to anything; the classification is catalog-only. Both are `OI-75`. Six of the eight `TerminalKind` members have no producer, three of them unreachable by any catalog rule. The shipped rules are pinned by the corpus expectations' `terminal_kinds` (verified: a typo in each of the three routes' fqns moves its own number to zero), because every unit test here invents its type names on purpose and a wrong real one is inert rather than invalid |
| **W31** ✅ | FR-6: the walk terminates at a terminal or a stated boundary. The **depth bound** goes; cycle and revisit refusal stay, because those are correctness | §8.1 | W22, W30 | `_walk` is an explicit stack, so the interpreter's own recursion limit is out of the failure modes and nothing needs a counter to stay finite. **The stack had to come first**: while the bound was there the recursion could never exceed 64 frames against a limit of 1000, so deleting it from the recursive form would have traded a stated, truncated answer for a crash on a long chain of distinct methods. **Measured before removing it**: deepest trace **9 edges** across `mall-admin` (160 traces), `spring-petclinic-rest` (37) and `jhipster-sample-app` (38), never truncated. Step order verified rather than argued — a faithful reimplementation of the recursive form gives identical sequences over all 235 roots. `TraceStop.DEPTH_LIMIT`, `Trace.truncated`, the `Complete` column, the `trace_depth_is_bounded` gap and one `guard_check.py` guard retire with it; **`OI-27` closes**, FR-6's "Not met as shipped" admonition comes off `REQUIREMENTS.md`, and `G-118` closes having INVERTED — the code moved to agree with `M04`. **A dispatched reviewer caught seven things this item's own inline review missed**, including a comment claiming the old bound risked a `RecursionError` (it could not — that is what the bound prevented) and another describing a row-reversal the code does not do |
| **W32** ✅ | Fork 3: a `narrowed` step renders as a Mermaid `alt` when the alternatives are known, and as **one arrow labelled with them** when they are not. The caption stops claiming "nothing is filtered". **The row's own premise was FALSE and is corrected here**: `narrowed` fires on real code — 68 edges across 34 call sites on `spring-petclinic-rest`, where every repository interface narrows to a JDBC impl AND a JPA impl, and 2 in this repo's own fixture. It is LIVE IN RENDERED OUTPUT: `ClinicServiceImpl#saveOwner` draws `a8->>a9: save` and `a8->>a15: save`, eight arrows apart, reading as two saves in sequence when exactly one repository is active | §8.3 | — | Drawn as mermaid's `alt`/`else`, each branch carrying the candidate's arrow AND its whole subtree — possible because the walk is depth-first, so a candidate's range is contiguous. Nothing reordered, nothing dropped; verified against the vendored mermaid build in a live browser. The caption stopped saying "nothing is filtered" (true, and useless to a reader who has read the arrows as a sequence) and names the number of CHOICES, per site rather than per candidate. A SINGLE `narrowed` candidate is not drawn as a choice — a DEFENSIVE guard, not a live case: `call_edges.py` writes `NARROWED if len(callees) > 1 else RESOLVED`, so a lone row cannot occur and the review found this cell claiming otherwise. **The row's second clause is NOT delivered**: "one arrow labelled with them when they are not [known]" has no state to render — a site whose bodies could not be named is `resolved` with a NULL callee, which the diagram already draws as one `[boundary]` arrow — and no code was written for it. Measured: 34 sites in petclinic-rest's `call_edges`, 31 reached by a trace, 62 `alt` blocks rendered, 4 of them nested; both counts pinned in the corpus expectations. Tests mutation-checked against flat rendering, a branch losing its subtree, a lone candidate grouping, `_grouped`'s and `_named`'s recursion, and the `(caller, ordinal)` site key |
| **W33** ✅ | Class diagrams of inheritance: two arrow kinds (`<\|--`, `<\|..`) over `type_hierarchy`; an unscanned ancestor renders `<<open>>` rather than being omitted | §8.4 | W22 | Both arrows ship, and the work was deciding WHICH ancestors earn one: `type_hierarchy` holds them all, and drawing them all buries the diagram — 30 of `mall-admin`'s 34 shape ancestors are one marker interface, and drawing the fixture's put four `<<open>>` boxes above four shapes the `.proto` describes completely. The rule is what an ancestor CONTRIBUTES (COVERAGE §3a-xi), and it draws one arrow each on the three corpora that have any. **An unscanned superclass is drawn only where the shape is `open`**, read from that one flag so the arrow and the stereotype cannot disagree. `<\|..` has NO live instance on any corpus — no payload implements an interface that is itself a payload — and is shipped and pinned rather than deferred, with the absence recorded. Verified against the vendored mermaid build in a live browser. **Starting this found a Critical in the shape expansion**: a payload class extending another published only its OWN fields and claimed `open: false` — `mall-admin`'s `dto/OmsOrderDetail` published 2 of 46 — fixed in its own commit, 153 wire fields recovered. Its review found the "of N" totals one high everywhere (each parent declares one static `serialVersionUID`) and the unscanned-superclass rule firing on ZERO shapes across all four corpora; both corrected, the rule kept and its absence recorded |

**Wave 6 acceptance:** PROJECT.md and the roadmap agree on 2Q, and the status is derived from
these tests.

---

## Wave 7 — F8: the index an agent can use

*(F8's other half, W34, moved to Wave 0 — see there for why.)*

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W35** ✅ | The symbol index (symbol → file path, line range, kind, enclosing), the reverse indexes (callers, implementors, endpoints-carrying-shape, annotation holders) and the address index (`GET /order/list` → root → handler → `file:line`) | §9.3 | W6, W22 | Six NDJSON files under `index/`, the third projection beside `graph/` and `render/`, listed in the manifest. **§9.2's keystone finding is half stale and half never a gap**: methods and constructors carry real lines (20,961 of 22,059 on `mall-admin`; 818 of 818), while types and fields carry none and correctly so — a class file has no `LineNumberTable` for either, so a type's record says `line: null` rather than borrowing its first method's. **Placement is where the work was**: `source_roots` in metadata alone placed 157 of `mall-admin`'s 648 documents, because a reactor sibling's sources are under the SIBLING's root; resolving through `origin_entry` — searching UP for the module root rather than computing a depth, since `target/classes` and `build/classes/java/main` differ — took it to **25,521 of 25,521, 24,093 through a sibling**. Never an absolute path: a bundle travels. Unplaced symbols have TWO causes: generated code under `target/generated-sources/` (1,285 of 1,287, deliberately left null because an agent sent to edit a generated file edits what the next build overwrites) and a LIBRARY's own classes read out of a jar (2, whose sources are not in the repository at all — a different and permanent reason). An earlier version of this cell claimed one cause. **The index is an EXIT and masks like one**: it reads the same rows `graph/` does, so an address published unmasked would be the bytes the parquet beside it strips — caught before review, a root at `https://user:hunter2@…` reached `addresses.ndjson` whole |
| **W36** ✅ | The file digest and the change-impact starting points | §9.3 | W35 | Two more NDJSON files, and both exist because the JOIN is the work rather than the data. `files.ndjson` is per file — what it declares by kind, and which annotations appear in it — carrying counts and annotation NAMES rather than the symbols, since `symbols.ndjson` already holds each with its own location; a file nothing could place contributes no record, there being no decision to support about a file the reader cannot open. `impact.ndjson` is one record per contract: the declaration, the fields, the endpoints carrying it and the handlers and callers of those, each PLACED, because a list of symbols an agent must then look up one by one is a list it makes six more requests about. **A shape id is a bare descriptor and a symbol carries module coordinates**, so the location map is keyed on both spellings — on the whole symbol alone every contract reported itself undeclared, while aliasing one map emitted every symbol twice in the listing. `impact` carries endpoint paths of its own and takes the exit's mask like the two files that already carry one |
| **W37** ✅ | Materialisation: `call_edges` ordered by caller **and** a second ordering by callee; a materialised reachability table (root → reachable symbol, depth, terminal flag) — **the trace walk already computes this and throws it away**; `roots` addressable by wire address | §9.4 | W31, W34 | `reachability` is the trace walk's own answer, written by the SAME function the renderer calls — a second traversal with its own cycle and revisit rules would be a second opinion about what is reachable. 190 rows over 77 roots on the fixture, 3,892 over 160 on `mall-admin`, deepest 8. One row per (root, symbol), the root itself at depth 0, and a terminal recorded by the TARGET since no body was read to name a callee. The two orderings are VIEWS — the rows stay the base tables' own — so what ships is a second parquet in a different order, which is the artifact Parquet's zone maps live in — though the SKIPPING those maps buy is inoperative at today's sizes and the docs now say so outright: DuckDB writes one row group per 122,880 rows and `mall-admin`'s `call_edges` is 24,591, so every exported parquet is a single group with nothing to skip, and what the second file gives today is a second ORDER. `roots_by_address` masks its `path` exactly as `roots` does |
| **W38** ✅ | FR-17 clause 3 — the resolution distribution, one `GROUP BY` on a column that already exists | §9.5 | W22 | Three buckets, not the one the row names — **because the one it names reads 100% `resolved` on two of the four corpora** (mall-admin 24,591 of 24,591, jhipster 1,686 of 1,686), exactly as §9.5 warned. `resolution` says whether DISPATCH settled a call, and naming the compiler's target is easy; reading the BODY is the work, and the reach rate is 78% on mall-admin and 31-32% on the other three. Shipping the named distribution alone would satisfy the row's letter and leave the standing instrument reading 100% forever. So reach LEADS, dispatch follows, and `method_resolution`'s reasons say why a body was missed — `owner_not_scanned` is a scanning decision, `no_declaration_found` would be a defect and no corpus has one. All three reach `metadata.json`, the manifest AND the rendered `## Coverage`, composed by one function on both paths: composed only in the resolve pipeline it reached the manifest and never the document a person opens |

**Wave 7 acceptance:** symbols carry real line numbers and openable paths on all four corpora;
an agent reaches a handler's `file:line` from `GET /order/list` without reading source.
*(The "a redacted bundle contains the same tables as an unredacted one" check moved to Wave 0
with W34.)*

---

## Wave 8 — F6: the checklist gains axes

Runs late because every foundation reports into it, except W40 which is independent and cheap.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W40** ✅ | Fix the malformed §5.12, §5.2 and §8 tables — 14 rows carry five columns under a four-column header, so 11 Java rows lose their status cell in any renderer. A test asserts column count against header count | §7.3 | — | **19 rows across four files, not 14 in one.** Sixteen in COVERAGE carried an extra cell, and the fold into the mechanism cell after an em dash is the convention every well-formed row beside them already used. THREE MORE SHAPES the row did not name, each found by the test on its first run: a row with no trailing pipe (`PROJECT.md`'s 2Q row), a row missing a cell outright (`M07`'s open decisions), and two rows WRAPPED across source lines — markdown ends a row at the newline, so the continuation renders as a paragraph under the table. `tests/architecture/test_markdown_tables.py` asserts every row against its own header, over every markdown file the repository ships, and is verified against all four shapes. **W43's review corrected the counter itself**: it skipped pipes inside code spans, on the reasoning that a renderer treats them as text. A renderer does not — GFM splits on every unescaped pipe, backticks included, and only `\|` is a literal — so the counter was declaring well-formed exactly the rows a renderer breaks, and three shipped rows were rendering truncated while it passed, this row among them. The claim that a naive count reported 1,961 malformed rows did not reproduce either: measured, the two rules differ only on escapes |
| **W41** ✅ | §5 gains axes beyond protocol: language construct, shape and contract, configuration source, trace and diagram, bundle and export, question ledger, rendered document | §7.2 | — | **Eight new sections, not seven.** The design's list leaves FR-11 to FR-14 — drift detection, refactor findings, design findings, structural performance risk — with nowhere to live, and four of the twelve homeless items are exactly those, so §5.20 *Query and findings* exists and says all four are unsupported with what each would take. All twelve items now carry a level. **The first column is never `Language` outside the protocol axis**: `coverage_matrix.py` counts rows by language across every `### 5.x` heading, so a non-protocol row spelled `Java` would be counted into a cell §2 has no column for and dropped silently — the generator now REFUSES a section it has no column for unless the section is declared non-protocol, verified by adding one. And the generator finally has a gate: `test_coverage_versions.py` had named its absence as the warning it was written against, so §2 could fall behind §5 with nothing saying so |
| **W42** | Enumerate **everything** with a support level — supported, partially supported, unsupported. Q2's Kotlin boundaries, Q3's four out-of-scope surfaces, Q4's six slices, W8's not-read set. Enumerate what Kotlin actually supports: §5 has 0 Kotlin rows of 170 while `coverage_matrix.py` **aliases Kotlin to Java**, asserting a parity nobody checked | §7.4 | W41, all waves | the standing requirement is met: nothing we are not delivering is left to silence |

---

## Wave 9 — F10: the five asymmetries

A half-shipped surface is worse than an absent one. Each is small; the engine and vocabulary
already exist for the other direction.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W43** ✅ | `SimpMessagingTemplate.convertAndSend` — STOMP outbound | §11 | W9 | a service that both receives and sends STOMP gets its whole messaging surface. **The descriptor could not be mirrored from the twin the design names.** `KafkaTemplate.send(String, V)` erases to a `String` destination; `convertAndSend` is declared on `MessageSendingOperations<D>`, `D` erases to `Object`, and `SimpMessagingTemplate` declares no bridge — so a real call site emits `(Ljava/lang/Object;Ljava/lang/Object;)V` for a `String` argument, compiled and read at spring-messaging 6.1.6, and the copied rule would have matched nothing. That String descriptor is the near-miss the suite now pins. Twelve overloads; the four `convertAndSendToUser` forms ship with NO destination capture, because Spring rewrites a user destination before the broker sees it and publishing the literal would name an address no subscriber holds. Fixture: two live rows, 55 outbound endpoints to 57. Found while verifying it and FIXED in the same commit: `OI-77`, an outbound payload handed through from a method PARAMETER carried no contract, because `_reference_of` answered for a class literal, a scalar and an `instance` and not for a parameter whose type the caller's own signature states. 3 of the fixture's 27 outbound rows carried a payload; 21 do (the count spans the `single_call` and `fluent` engines — 3 of 25 and 19 of 25 for `single_call` alone). Six catalogs, not this one's |
| **W44** ✅ | Spring MVC functional routing (the WebFlux twin is catalogued) | §11 | W9 | `RouterFunction` routes derive. **Measured against spring-webmvc 6.1.6, not mirrored from the twin** — the packages really are structurally identical here, and the one thing a copy would have got wrong is the Kotlin entry point, which is `router` and not `coRouter`. Live on the fixture: `GET /mvcfn/invoices` with `produces`, `POST` with `consumes`, `PUT /mvcfn/invoices/{id}`. **Two defects in the EXISTING reactive catalog fell out of measuring rather than copying**: it declared `accept` alone for the Kotlin DSL on the stated ground that *"Kotlin only declares `accept`"* — false of the framework, true only of the 2E fixture, §8.1 rule 1 again — and neither catalog declared `andOther`, which merges a whole router along `and`'s exact signature, so every route merged that way was lost. Both fixed here. The surface enumeration also gained `RouterFunctions` itself on both sides: only `$Builder` was enumerated, so five addressable methods sat outside the slice AND outside the enumeration |
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

## Wave 12 — the module edge, finished · **scheduled after v1's waves**

Added 2026-09-09, from what W24 measured on the way in, and joined by **W57** from what W29 measured. All three run after every wave
above rather than beside W24, by decision: neither changes what any v1 item can claim,
and both are bounded by measurements already taken.

W56 is a cost, W55 is a capability, and they are separate decisions — W56 makes every
reactor module cheaper to analyse whichever build system it uses, while W55 is the
difference between a Gradle team reaching the module edge and not being able to.

| # | Item | Spec | Depends on | Delivers |
|---|---|---|---|---|
| **W56** | **A dependency root is scanned for its TYPES, not scanned entirely.** F4 §5.2's own wording is "read a sibling module's **types**"; W24 implemented "scan a sibling module". Measured on `mall-admin`, same fact tree with and without the sibling subtree: `derive_endpoints` 2.1s → **15.2s** for **zero** extra rows, `record_call_edges` 1.6s → **16.7s** (2,608 → 24,591 edges, none traced), `record_return_flows` 0.3s → **5.8s** — roughly **33 of ~61 seconds of derivation buying nothing**, and the fact volume going 6,388 → 79,315. Only `derive_endpoint_shapes` (~16.5s) is doing what the module edge is crossed for. **Two levers, in value order:** (1) a types-only extraction mode for a dependency root — signatures, fields and hierarchy, no call sites and no method-level annotations — which cuts every downstream pass at once; (2) filter derivation ROOTS to the module's own documents at each row-minting pass, which removes `derive_endpoints`'s 13s outright and makes `drop_borrowed_endpoints.sql` a belt-and-braces check rather than the mechanism. **Falsified by** measuring that a real trace crosses into a dependency's body, which would make its call graph recall rather than waste | §5.2 | W24 | analysing a reactor module stops costing 10× what it did |
| **W57** | **A destination built inside a lambda ARGUMENT is read, in `single_call` as it now is in `fluent`** (`OI-74`). `sqsTemplate.send(to -> to.queue("shipments-lambda").payload(event))` derives an outbound row with NO destination — `path` NULL, `resolution: unresolved` — and the queue name is a string literal in the lambda's own synthetic method, which the fact stream records under the symbol the argument names. It is `OI-73`'s defect one engine over: that one cost a WebClient call its whole URL and was fixed in W29 by walking the lambda body as a chain of its own; this costs an SQS send its whole queue. Both were written down as deliberate ("an honest unresolved row, not a fabricated path") and the framing is the same mistake — the lambda is ONE argument of ONE call, so reading the method it compiled to is reading rather than guessing. **One live instance** in the fixture's own output on every run (`EventProducers#sendShipmentViaBuilder`), and `SqsTemplate.send(Consumer<SqsSendOptions>)` is the SDK's own fluent overload. `single_call` reads its positions off one call site rather than walking a chain, so the fix needs a declared way to say "this argument is a builder lambda, and the destination is at `queue(arg0)` inside it" | §6.2 | W29 | a consumer-builder send stops being an address-less row |
| **W55** | `GradleDetector` resolves reactor siblings the way `MavenDetector` does — the `compileClasspath` entries the init script already marks `internal: true`, turned into `LibraryRoot`s and named in `sibling_coordinates`. **Design question to settle first:** a `ProjectComponentIdentifier` carries a project PATH (`:mall-common`), not `group:artifact:version`, so a stable spelling for `sibling_coordinates` has to be chosen, and `origin` must not become a path (D00 §2 — `origin` survives being read on another machine) | §5.2 | W24 | a Gradle multi-project build stops carrying empty response envelopes |

**Why this is not a nice-to-have, stated once so the next reader does not have to
re-derive it.** The two build systems do not differ by convenience here; they differ by
whether the thing is possible at all.

`extract_libraries` cannot name a sibling project. `gradle.py`'s `_library_roots` builds
its lookup only from classpath entries carrying both `group` and `name`, and an
inter-project dependency has neither — so the coordinate misses, pinning a version does
not help (the candidate list is empty before the version is consulted), and the user is
told "this module's compile classpath does not resolve this dependency". **There is no
workaround inside Sextant**: reaching the module edge on Gradle means publishing the
subproject to a local repository and depending on it by coordinate, which is changing the
build rather than using the tool.

And if that lookup were merely fixed, the semantics would still diverge:
`extract_libraries` carries CONSENT — an opted-in library's own controllers and SOAP
operations DO derive as endpoints, which `tests/e2e/test_vertical_slice.py` asserts — while
a Maven sibling's do not. The same source layout would produce different endpoint rows
depending on the build system, which is the shape §8.1's language rule exists to refuse.

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
