# Open issues — tracked in Plane

**Plane is the source of truth for open issues.** Ruled 2026-10-24 (user): *"move all
recorded issues to plane, and use it as source of truth for all open issues, and close them
accordingly as we progress."* The project is **Sextant** (`SEXTANT`) in the `portolan`
workspace. Every issue open on that date is a Plane work item, with its body, its
severity as priority (Critical → urgent, Major → high, Minor → low) and the label
`needs-triage`. That is 166 OIs, the six capability gaps GAP-1 to GAP-6, `P-2` from
[`performance.md`](performance.md), and the 15 open items on
[`java-kotlin-delivery-list.md`](java-kotlin-delivery-list.md) that have no OI entry.
Their bodies no longer live here. `needs-triage` means the item was carried over without
being verified again, so some may already be fixed.

**Logging a new issue.** Create a Plane work item and add its row to the id map below; never
write its body here. Keep the id scheme in the title (`OI-236 — …`, the next number), because
code comments and documents cite issues by id.

**Closing one.** Move the item to Done in Plane and name the PR that closed it. If the delivery list
names the item, its `closed` block still takes the test and the CI run, as
`tests/architecture/test_feature_delivery.py` requires.

**What this file still holds:** the id map below, so an id cited in code resolves to its
Plane item; the stop-rule count; and the closed entries, as history.

**Not an issue: a fact or table whose reader is planned in the roadmap.** Ruled
2026-09-06 (user): *"as long as reader is planned in the roadmap, it's not an
issue, simply because the planning is not aligned yet."* A producer that ships
before its consumer is a sequencing artefact, not a defect — PROVIDED the consumer
is a named item in `docs/superpowers/plans/`. A producer whose consumer is named
nowhere is the `detect.coordinates` defect and stays an issue.

## Id map

| Id | Plane | Title |
|---|---|---|
| OI-1 | [SEXTANT-31](https://app.plane.so/portolan/browse/SEXTANT-31/) | every Spring Integration channel question was filed under `amqp` |
| OI-2 | [SEXTANT-5](https://app.plane.so/portolan/browse/SEXTANT-5/) | a DISABLED scheduled job was reported as live work |
| OI-3 | [SEXTANT-123](https://app.plane.so/portolan/browse/SEXTANT-123/) | the multi-path WebSocket rule is documentation, not measurement |
| OI-4 | [SEXTANT-141](https://app.plane.so/portolan/browse/SEXTANT-141/) | one identity, two string spellings, and nothing enforces which you hold |
| OI-5 | [SEXTANT-2](https://app.plane.so/portolan/browse/SEXTANT-2/) | MicroProfile GraphQL published a wrong address for an un-named operation |
| OI-6 | [SEXTANT-142](https://app.plane.so/portolan/browse/SEXTANT-142/) | 6 Class A Minors remain open |
| OI-7 | [SEXTANT-149](https://app.plane.so/portolan/browse/SEXTANT-149/) | the Maven set carries test-scoped dependencies and the Gradle set does not |
| OI-8 | [SEXTANT-150](https://app.plane.so/portolan/browse/SEXTANT-150/) | library archive resolution still reads one pom |
| OI-9 | [SEXTANT-151](https://app.plane.so/portolan/browse/SEXTANT-151/) | what a Maven analysis records now depends on the local repository |
| OI-10 | [SEXTANT-154](https://app.plane.so/portolan/browse/SEXTANT-154/) | shipped catalogs that state no measured version at all |
| OI-11 | [SEXTANT-155](https://app.plane.so/portolan/browse/SEXTANT-155/) | nothing compares a catalog's measured version against the module's |
| OI-12 | [SEXTANT-157](https://app.plane.so/portolan/browse/SEXTANT-157/) | F2 unified three divergent shape tables, and no test exercises the widening |
| OI-13 | [SEXTANT-23](https://app.plane.so/portolan/browse/SEXTANT-23/) | the plan cites `A-C2` for a defect the sweep files under `A-C3` |
| OI-14 | [SEXTANT-18](https://app.plane.so/portolan/browse/SEXTANT-18/) | capability 9.17 produced a fact nothing read |
| OI-15 | [SEXTANT-20](https://app.plane.so/portolan/browse/SEXTANT-20/) | capability 9.18 produced a fact kind nothing read |
| OI-16 | [SEXTANT-158](https://app.plane.so/portolan/browse/SEXTANT-158/) | two dispatch rules will exist, and only one is designed |
| OI-17 | [SEXTANT-160](https://app.plane.so/portolan/browse/SEXTANT-160/) | an in-module override of a library-declared method is not linked |
| OI-18 | [SEXTANT-161](https://app.plane.so/portolan/browse/SEXTANT-161/) | the several-implementations rule still has no real-code exercise |
| OI-19 | [SEXTANT-163](https://app.plane.so/portolan/browse/SEXTANT-163/) | `sig_` is computed in two languages and only an uncatchable test guards the drift |
| OI-20 | [SEXTANT-19](https://app.plane.so/portolan/browse/SEXTANT-19/) | `return_flows` had no reader until G4 |
| OI-22 | [SEXTANT-164](https://app.plane.so/portolan/browse/SEXTANT-164/) | `root_kind`'s third member has no producer |
| OI-23 | [SEXTANT-13](https://app.plane.so/portolan/browse/SEXTANT-13/) | a functional route is an endpoint with no handler, so it has no root |
| OI-24 | [SEXTANT-11](https://app.plane.so/portolan/browse/SEXTANT-11/) | D01 §7's conservative re-derivation rule was not enforced anywhere |
| OI-25 | [SEXTANT-10](https://app.plane.so/portolan/browse/SEXTANT-10/) | the traversal had no reader outside its own tests |
| OI-28 | [SEXTANT-8](https://app.plane.so/portolan/browse/SEXTANT-8/) | a root's copied wire address could be taken before the row finished being written |
| OI-29 | [SEXTANT-27](https://app.plane.so/portolan/browse/SEXTANT-27/) | `analyze` over a workspace whose graph schema moved crashes instead of rebuilding |
| OI-30 | [SEXTANT-6](https://app.plane.so/portolan/browse/SEXTANT-6/) | the default document drew the steps of a minority of a large module's traces |
| OI-31 | [SEXTANT-28](https://app.plane.so/portolan/browse/SEXTANT-28/) | `architecture.html` inlines 3.5 MB of mermaid and renders every diagram on load |
| OI-32 | [SEXTANT-29](https://app.plane.so/portolan/browse/SEXTANT-29/) | `spring-petclinic-rest`'s pinned routes are stale and the pin has been failing since 2O |
| OI-33 | [SEXTANT-30](https://app.plane.so/portolan/browse/SEXTANT-30/) | `enrich`'s brief now carries the complete document, and nothing has measured that |
| OI-34 | [SEXTANT-38](https://app.plane.so/portolan/browse/SEXTANT-38/) | a DISABLED cron beside a live rate is a declaration the container refuses, and we publish its other row |
| OI-35 | [SEXTANT-3](https://app.plane.so/portolan/browse/SEXTANT-3/) | four of MicroProfile GraphQL's five operation-name sources were not read |
| OI-36 | [SEXTANT-4](https://app.plane.so/portolan/browse/SEXTANT-4/) | a method carrying TWO listener annotations derived nothing, in all three frameworks |
| OI-37 | [SEXTANT-39](https://app.plane.so/portolan/browse/SEXTANT-39/) | an INHERITED `@RabbitListener` registers a listener we do not see |
| OI-38 | [SEXTANT-147](https://app.plane.so/portolan/browse/SEXTANT-147/) | a second `@PulsarListener` written into the container derived nothing |
| OI-39 | [SEXTANT-148](https://app.plane.so/portolan/browse/SEXTANT-148/) | `@PulsarReader` is a whole inbound surface the Pulsar catalog named nowhere |
| OI-40 | [SEXTANT-145](https://app.plane.so/portolan/browse/SEXTANT-145/) | `@SqsListener` grew a class-level, polymorphic form and the catalog said it had none |
| OI-41 | [SEXTANT-40](https://app.plane.so/portolan/browse/SEXTANT-40/) | the probe-provenance rule accepted a version spelling it could not then verify |
| OI-42 | [SEXTANT-122](https://app.plane.so/portolan/browse/SEXTANT-122/) | a class file above the ceiling is refused, and the refusal kills the whole scan |
| OI-43 | [SEXTANT-32](https://app.plane.so/portolan/browse/SEXTANT-32/) | FR-19 describes a redaction mechanism the project deliberately does not build |
| OI-44 | [SEXTANT-41](https://app.plane.so/portolan/browse/SEXTANT-41/) | a catalog still hardcodes a framework default that the jar now states (W4a) |
| OI-45 | [SEXTANT-44](https://app.plane.so/portolan/browse/SEXTANT-44/) | nesting is still derived by splitting a class name on `$` (W4b) |
| OI-46 | [SEXTANT-45](https://app.plane.so/portolan/browse/SEXTANT-45/) | `type_parameters` is read, declared, and read by nothing (W5) |
| OI-49 | [SEXTANT-56](https://app.plane.so/portolan/browse/SEXTANT-56/) | twelve W7 fields are read and nothing reads them back |
| OI-50 | [SEXTANT-57](https://app.plane.so/portolan/browse/SEXTANT-57/) | a scope can only be turned on, never off |
| OI-51 | [SEXTANT-58](https://app.plane.so/portolan/browse/SEXTANT-58/) | a nested type's own access modifier is read from nowhere |
| OI-52 | [SEXTANT-64](https://app.plane.so/portolan/browse/SEXTANT-64/) | the ledger's `jvms` section numbers and 18 of its access flags resolve against nothing |
| OI-53 | [SEXTANT-71](https://app.plane.so/portolan/browse/SEXTANT-71/) | 45 catalog conversion sites name no file and no key when they refuse |
| OI-54 | [SEXTANT-77](https://app.plane.so/portolan/browse/SEXTANT-77/) | `identity_marker` and `supertype_marker` were named as type-name sites and are not |
| OI-55 | [SEXTANT-78](https://app.plane.so/portolan/browse/SEXTANT-78/) | `media_values.owner` is widened and no shipped catalog declares it |
| OI-56 | [SEXTANT-85](https://app.plane.so/portolan/browse/SEXTANT-85/) | `scheduled_work` pairs `annotation` and `container` as independent lists |
| OI-57 | [SEXTANT-91](https://app.plane.so/portolan/browse/SEXTANT-91/) | three boundaries were justified by "this key is single-valued", and W9 widened them all |
| OI-58 | [SEXTANT-92](https://app.plane.so/portolan/browse/SEXTANT-92/) | `resolved_config.parquet` differed between two runs, once, and I could not reproduce it |
| OI-59 | [SEXTANT-98](https://app.plane.so/portolan/browse/SEXTANT-98/) | a measurement bounded to one version, read as if it were general |
| OI-60 | [SEXTANT-105](https://app.plane.so/portolan/browse/SEXTANT-105/) | the Stream candidate set counts methods where the framework counts beans |
| OI-61 | [SEXTANT-106](https://app.plane.so/portolan/browse/SEXTANT-106/) | `detect.satisfied_by` is unmeasured beyond the one annotation that uses it |
| OI-62 | [SEXTANT-112](https://app.plane.so/portolan/browse/SEXTANT-112/) | the `handler_protocol` question is filed per class, and a class may serve both wires |
| OI-63 | [SEXTANT-113](https://app.plane.so/portolan/browse/SEXTANT-113/) | `displayName` is declared by every catalog and read by nothing |
| OI-65 | [SEXTANT-119](https://app.plane.so/portolan/browse/SEXTANT-119/) | nothing detects a release that moves `Subscriber.startAsync` out of the template |
| OI-66 | [SEXTANT-124](https://app.plane.so/portolan/browse/SEXTANT-124/) | `config_join` has no container vocabulary, so a repeated channel annotation drops |
| OI-67 | [SEXTANT-125](https://app.plane.so/portolan/browse/SEXTANT-125/) | a DGS fetcher declared on a superclass method registers, and we do not see it |
| OI-68 | [SEXTANT-131](https://app.plane.so/portolan/browse/SEXTANT-131/) | analysing a reactor module costs 14× what it did · **MOVED to `docs/performance.md` P-1 (2026-09-12)** |
| OI-69 | [SEXTANT-134](https://app.plane.so/portolan/browse/SEXTANT-134/) | Gradle modules cross no module edge · **SCHEDULED as W55 (Wave 12)** |
| OI-70 | [SEXTANT-140](https://app.plane.so/portolan/browse/SEXTANT-140/) | the workspace migrates ADDED columns and nothing else |
| OI-71 | [SEXTANT-143](https://app.plane.so/portolan/browse/SEXTANT-143/) | a module's own `redact:` additions do not widen metadata masking |
| OI-72 | [SEXTANT-146](https://app.plane.so/portolan/browse/SEXTANT-146/) | `payload_ctor_arg: last` reads a Kafka record's HEADERS as its payload |
| OI-75 | [SEXTANT-152](https://app.plane.so/portolan/browse/SEXTANT-152/) | five of `TerminalKind`'s eight members, and one of `TargetKind`'s three, have no producer |
| OI-76 | [SEXTANT-153](https://app.plane.so/portolan/browse/SEXTANT-153/) | `Direction.both` has no producer |
| OI-78 | [SEXTANT-156](https://app.plane.so/portolan/browse/SEXTANT-156/) | `requires:` means two different things across the estate |
| OI-79 | [SEXTANT-165](https://app.plane.so/portolan/browse/SEXTANT-165/) | a figure DERIVED is published as a figure MEASURED, and nothing checks the difference · **§13.8 VIOLATION COUNT: 8** |
| OI-83 | [SEXTANT-162](https://app.plane.so/portolan/browse/SEXTANT-162/) | documented mechanisms that do not exist, folded from `open-issues.md` OI-83 |
| OI-84 | [SEXTANT-159](https://app.plane.so/portolan/browse/SEXTANT-159/) | the principles sweep of 2026-09-05, folded |
| OI-85 | [SEXTANT-42](https://app.plane.so/portolan/browse/SEXTANT-42/) | three inputs the `DefaultImpls` holder rule would misread, none of which a real module presents |
| OI-86 | [SEXTANT-43](https://app.plane.so/portolan/browse/SEXTANT-43/) | `sole_unannotated` still governs Feign and Micronaut messaging, and loses a Kotlin body the same way JAX-RS used to |
| OI-87 | [SEXTANT-50](https://app.plane.so/portolan/browse/SEXTANT-50/) | `@RestStreamElementType`'s value is not carried as the per-event SSE format |
| OI-88 | [SEXTANT-52](https://app.plane.so/portolan/browse/SEXTANT-52/) | Quarkus REST's return-type-keyed default `produces` is not read |
| OI-89 | [SEXTANT-53](https://app.plane.so/portolan/browse/SEXTANT-53/) | `annotation_arg.equals` compares Python's `str()` of a non-string fact value, which is not Java's string form |
| OI-90 | [SEXTANT-54](https://app.plane.so/portolan/browse/SEXTANT-54/) | `POST /kt/orders` derives TWO inbound rows in `orders-service`, one per engine |
| OI-91 | [SEXTANT-55](https://app.plane.so/portolan/browse/SEXTANT-55/) | Quarkus REST's own inheritance rule diverges from JAX-RS §3.6, and the engine emulates the specification, not Quarkus |
| OI-92 | [SEXTANT-59](https://app.plane.so/portolan/browse/SEXTANT-59/) | annotation readers fold the RAW `annotations` table, so an inherited marker and a repeated container both read false (merged with `OI-93`) |
| OI-93 | [SEXTANT-60](https://app.plane.so/portolan/browse/SEXTANT-60/) | a REPEATED `@KafkaListener(batch = "true")` never satisfies `wrappers[].when` · **MERGED INTO `OI-92` (2026-10-18)** |
| OI-94 | [SEXTANT-61](https://app.plane.so/portolan/browse/SEXTANT-61/) | a batch listener's reply row roots its payload with the unconditional wrappers, so `@SendTo` on a `List<X>`-returning batch listener publishes `X` as the response and `array<X>` on the reply |
| OI-95 | [SEXTANT-62](https://app.plane.so/portolan/browse/SEXTANT-62/) | a `jakarta.*` API coordinate at a Jakarta EE 8 version is `javax`-packaged, and the family's coordinate lists cannot say so |
| OI-96 | [SEXTANT-63](https://app.plane.so/portolan/browse/SEXTANT-63/) | `apply_protocol_hints` can reclassify an OUTBOUND row after `fluent` wrote its metadata |
| OI-97 | [SEXTANT-72](https://app.plane.so/portolan/browse/SEXTANT-72/) | two `combinator` catalogs exhausting the helper depth in one resolve file two `routing_depth` rows under one identity |
| OI-98 | [SEXTANT-73](https://app.plane.so/portolan/browse/SEXTANT-73/) | the whole-map skip in `request_params` is by EXACT erased type, where Spring's is `isAssignableFrom` |
| OI-99 | [SEXTANT-74](https://app.plane.so/portolan/browse/SEXTANT-74/) | a helper reached as a member call ON the routing origin is not followed |
| OI-100 | [SEXTANT-75](https://app.plane.so/portolan/browse/SEXTANT-75/) | the Spring router's `Supplier<RouterFunction>` bodies do not follow helpers |
| OI-101 | [SEXTANT-76](https://app.plane.so/portolan/browse/SEXTANT-76/) | Ktor 2.x handler bodies name the interface receivers, which are not `via` owners |
| OI-102 | [SEXTANT-86](https://app.plane.so/portolan/browse/SEXTANT-86/) | a Javalin FLAT row's `Handler` lambda reads are invisible |
| OI-103 | [SEXTANT-87](https://app.plane.so/portolan/browse/SEXTANT-87/) | `AdaptedFunctionReference` is recognised by name and unmeasured |
| OI-104 | [SEXTANT-88](https://app.plane.so/portolan/browse/SEXTANT-88/) | a WRITTEN Micronaut name also accepts the parameter's hyphenated name, and the row states the written one alone |
| OI-105 | [SEXTANT-89](https://app.plane.so/portolan/browse/SEXTANT-89/) | `optional` for a Kotlin default parameter assumes `kotlin-reflect` at runtime |
| OI-106 | [SEXTANT-90](https://app.plane.so/portolan/browse/SEXTANT-90/) | the field ladder has no bean rung: a `Publisher`, `WebClient` or `KafkaTemplate` built in one `@Bean` method and injected into another is still unresolved |
| OI-107 | [SEXTANT-93](https://app.plane.so/portolan/browse/SEXTANT-93/) | `sends_to` edges have no reader |
| OI-109 | [SEXTANT-94](https://app.plane.so/portolan/browse/SEXTANT-94/) | a spec configurer adding queues is a miss |
| OI-110 | [SEXTANT-95](https://app.plane.so/portolan/browse/SEXTANT-95/) | a container built two beans away is unresolved |
| OI-111 | [SEXTANT-96](https://app.plane.so/portolan/browse/SEXTANT-96/) | Gateway `filters` rewrite the upstream path and are not read |
| OI-112 | [SEXTANT-97](https://app.plane.so/portolan/browse/SEXTANT-97/) | `IntegrationFlow.from(<adapter bean>)` is not declared |
| OI-113 | [SEXTANT-107](https://app.plane.so/portolan/browse/SEXTANT-107/) | `resolved_config` carries no declaration order |
| OI-114 | [SEXTANT-108](https://app.plane.so/portolan/browse/SEXTANT-108/) | `${key:default}` in a channel name never applies the default |
| OI-115 | [SEXTANT-109](https://app.plane.so/portolan/browse/SEXTANT-109/) | `_fold`'s captures are LAST-WINS, so a second `channel` and a second `handle` each overwrite the first (merged with `OI-121`) |
| OI-116 | [SEXTANT-110](https://app.plane.so/portolan/browse/SEXTANT-110/) | `read_by`/`sends_to` edges are written once per vararg destination |
| OI-117 | [SEXTANT-111](https://app.plane.so/portolan/browse/SEXTANT-111/) | the container hop re-walks the bean's chain per reference |
| OI-118 | [SEXTANT-114](https://app.plane.so/portolan/browse/SEXTANT-114/) | `_REQUIREMENT_KINDS` is spelled in two engines |
| OI-119 | [SEXTANT-115](https://app.plane.so/portolan/browse/SEXTANT-115/) | the descriptor gate reads `matches.methods` only, so a `fluent` catalog's `roots:`/`steps:`/`beans:` descriptors are outside it entirely (merged with `OI-129`) |
| OI-120 | [SEXTANT-116](https://app.plane.so/portolan/browse/SEXTANT-116/) | `setTopicExpression(e)` followed by `setTopic("t")` reads unresolved |
| OI-121 | [SEXTANT-117](https://app.plane.so/portolan/browse/SEXTANT-117/) | `handler` is a last-wins slot · **MERGED INTO `OI-115` (2026-10-18)** |
| OI-122 | [SEXTANT-118](https://app.plane.so/portolan/browse/SEXTANT-118/) | the linking tier's metadata refinement rule is stated twice and built nowhere |
| OI-123 | [SEXTANT-126](https://app.plane.so/portolan/browse/SEXTANT-126/) | Cadence is excluded by fqn, and nobody has measured whether it is one protocol or two |
| OI-124 | [SEXTANT-127](https://app.plane.so/portolan/browse/SEXTANT-127/) | the programmatic Temporal worker derives nothing, and the mechanism that would fix it does not exist |
| OI-125 | [SEXTANT-128](https://app.plane.so/portolan/browse/SEXTANT-128/) | `request(...)` derives no reply shape, because the reply type is the call's RETURN type |
| OI-126 | [SEXTANT-129](https://app.plane.so/portolan/browse/SEXTANT-129/) | a `MessageConsumer` or `MessageProducer` handed to another method before its terminal derives nothing |
| OI-127 | [SEXTANT-130](https://app.plane.so/portolan/browse/SEXTANT-130/) | `registerWorkflowImplementationFactory` and the SDK's own start-up validations are reproduced by nothing |
| OI-128 | [SEXTANT-135](https://app.plane.so/portolan/browse/SEXTANT-135/) | CP-10 files a descriptor two versions both declare under the FIRST version alone |
| OI-129 | [SEXTANT-136](https://app.plane.so/portolan/browse/SEXTANT-136/) | the descriptor gate reads `matches.methods` only · **MERGED INTO `OI-119` (2026-10-18)** |
| OI-130 | [SEXTANT-137](https://app.plane.so/portolan/browse/SEXTANT-137/) | `@KafkaListener(value = "a", groupId = "b")` writes two contradicting consumer groups where Micronaut resolves one |
| OI-131 | [SEXTANT-138](https://app.plane.so/portolan/browse/SEXTANT-138/) | `uniqueGroupId = true` makes the recorded consumer group a PREFIX of the one joined |
| OI-132 | [SEXTANT-139](https://app.plane.so/portolan/browse/SEXTANT-139/) | `request_requirements` wrote its `endpoint_metadata` values UNREDACTED into the export |
| OI-133 | [SEXTANT-144](https://app.plane.so/portolan/browse/SEXTANT-144/) | a VOID ordinary method is read as a construction, so an identity entry naming one would answer what the receiver is |
| OI-134 | [SEXTANT-121](https://app.plane.so/portolan/browse/SEXTANT-121/) | one identity is written on up to 26 rows, and 10 of the 18 cannot move without a measurement |
| OI-135 | [SEXTANT-120](https://app.plane.so/portolan/browse/SEXTANT-120/) | an invented hop key loads silently, and neither cheap way of closing that works |
| OI-136 | [SEXTANT-133](https://app.plane.so/portolan/browse/SEXTANT-133/) | the sixth edge is deferred: 16 of 756 asked positions, and the endpoints publish either way · **THE EDGE LANDED 2026-10-18; capability 9.19's remaining shapes stay open** |
| OI-138 | [SEXTANT-132](https://app.plane.so/portolan/browse/SEXTANT-132/) | outbound addresses are 1 of 6 on a real multi-service Spring Boot system |
| OI-141 | [SEXTANT-104](https://app.plane.so/portolan/browse/SEXTANT-104/) | a binding's literal value is not a fact, and it is worth one row today |
| OI-146 | [SEXTANT-103](https://app.plane.so/portolan/browse/SEXTANT-103/) | a destination a catalog cannot address drops the row and says nothing |
| OI-147 | [SEXTANT-102](https://app.plane.so/portolan/browse/SEXTANT-102/) | RocketMQ is catalogued nowhere, and it is absent from COVERAGE as well |
| OI-149 | [SEXTANT-101](https://app.plane.so/portolan/browse/SEXTANT-101/) | a nested aggregator's modules are invisible, so 323 endpoints' response contracts are open |
| OI-152 | [SEXTANT-1](https://app.plane.so/portolan/browse/SEXTANT-1/) | a host assembled through a map, three providers and a health check is not traceable, and is now NAMED |
| OI-153 | [SEXTANT-7](https://app.plane.so/portolan/browse/SEXTANT-7/) | a hole in an assembled address is NAMED after the value that fills it |
| OI-155 | [SEXTANT-188](https://app.plane.so/portolan/browse/SEXTANT-188/) | `preserves` is the only identity key with no closed-set validation |
| OI-156 | [SEXTANT-99](https://app.plane.so/portolan/browse/SEXTANT-99/) | `authority_of` reads operand 0 as the authority without checking it is the one `<host>` names |
| OI-157 | [SEXTANT-100](https://app.plane.so/portolan/browse/SEXTANT-100/) | a destination that differs per BRANCH publishes one row or none, never one row per branch |
| OI-158 | [SEXTANT-9](https://app.plane.so/portolan/browse/SEXTANT-9/) | two calls differing ONLY in their query string now dedup to one row |
| OI-159 | [SEXTANT-69](https://app.plane.so/portolan/browse/SEXTANT-69/) | framework and build-tool knowledge in the common stitch tier, three instances |
| OI-160 | [SEXTANT-70](https://app.plane.so/portolan/browse/SEXTANT-70/) | `system_analyze` is 95 lines of pipeline inside the API facade |
| OI-161 | [SEXTANT-79](https://app.plane.so/portolan/browse/SEXTANT-79/) | `stitch` reads another engine's private block and a sibling's internal constant |
| OI-162 | [SEXTANT-80](https://app.plane.so/portolan/browse/SEXTANT-80/) | a composed gateway link's `from_*` matches no endpoint row |
| OI-163 | [SEXTANT-81](https://app.plane.so/portolan/browse/SEXTANT-81/) | `StripPrefix` declared as a default filter is not read, so the route is refused |
| OI-164 | [SEXTANT-82](https://app.plane.so/portolan/browse/SEXTANT-82/) | a `Path` predicate with several comma-separated patterns is read as one |
| OI-165 | [SEXTANT-83](https://app.plane.so/portolan/browse/SEXTANT-83/) | a participant's name is interpolated into the federated view's SQL |
| OI-166 | [SEXTANT-84](https://app.plane.so/portolan/browse/SEXTANT-84/) | loading 101 catalogs is more than half of a system run |
| OI-168 | [SEXTANT-12](https://app.plane.so/portolan/browse/SEXTANT-12/) | a module resolving NO configuration key still gets a `default` verdict per condition |
| OI-170 | [SEXTANT-14](https://app.plane.so/portolan/browse/SEXTANT-14/) | a call declared on a generic framework type lists every repository that extends it |
| OI-171 | [SEXTANT-15](https://app.plane.so/portolan/browse/SEXTANT-15/) | relaxed spellings of the profile keys are not read |
| OI-172 | [SEXTANT-16](https://app.plane.so/portolan/browse/SEXTANT-16/) | the `@ConditionalOnBean(annotation = …)` criterion ignores the type hierarchy |
| OI-173 | [SEXTANT-17](https://app.plane.so/portolan/browse/SEXTANT-17/) | symbol parsing in SQL: the `candidate_presence` view cuts a symbol on `#` |
| OI-174 | [SEXTANT-21](https://app.plane.so/portolan/browse/SEXTANT-21/) | a body a conditional bean declares and an unconditional subclass bean inherits reads only the declaring bean's conditions |
| OI-175 | [SEXTANT-22](https://app.plane.so/portolan/browse/SEXTANT-22/) | a bare `user:pass@host` configuration value under a key naming no secret is not masked |
| OI-176 | [SEXTANT-24](https://app.plane.so/portolan/browse/SEXTANT-24/) | a raw `/` inside a URL's password splits the authority early |
| OI-177 | [SEXTANT-25](https://app.plane.so/portolan/browse/SEXTANT-25/) | a malformed `redact:` value pattern in one module fails `system analyze` without naming the module |
| OI-178 | [SEXTANT-26](https://app.plane.so/portolan/browse/SEXTANT-26/) | the URL userinfo strip can eat the next value in compact raw text |
| OI-179 | [SEXTANT-33](https://app.plane.so/portolan/browse/SEXTANT-33/) | `resolved_peers`' SQL substitution cannot read a `:default` |
| OI-180 | [SEXTANT-34](https://app.plane.so/portolan/browse/SEXTANT-34/) | `config_join._channel_name` is a second placeholder walk beside `substitute` |
| OI-181 | [SEXTANT-35](https://app.plane.so/portolan/browse/SEXTANT-35/) | a relaxed-key collision reads a different spelling in `resolved_schedules` than in `resolve_config` |
| OI-182 | [SEXTANT-36](https://app.plane.so/portolan/browse/SEXTANT-36/) | only the first declared config model is read for a scheduled expression, and `resolved_config` has no model column |
| OI-183 | [SEXTANT-37](https://app.plane.so/portolan/browse/SEXTANT-37/) | the boundary vocabulary's `schedule` identity collides under `@Schedules` |
| OI-184 | [SEXTANT-46](https://app.plane.so/portolan/browse/SEXTANT-46/) | `substitute` does not model two `PlaceholderParser` behaviours CP-48 read: the whole-inside lookup and the escape character |
| OI-185 | [SEXTANT-47](https://app.plane.so/portolan/browse/SEXTANT-47/) | a `${…}` naming the activation key resolves inside `resolve_config` but reads `missing_key` in `resolved_schedules` |
| OI-186 | [SEXTANT-48](https://app.plane.so/portolan/browse/SEXTANT-48/) | a gRPC client's configured address is not read as its peer, for net.devh and Quarkus |
| OI-188 | [SEXTANT-49](https://app.plane.so/portolan/browse/SEXTANT-49/) | an `@GrpcClient` on a METHOD (net.devh setter injection) joins no stub type and derives nothing |
| OI-189 | [SEXTANT-51](https://app.plane.so/portolan/browse/SEXTANT-51/) | an empty `connector=` on a SmallRye channel is a question where Quarkus likely sees an orphan |
| OI-190 | [SEXTANT-65](https://app.plane.so/portolan/browse/SEXTANT-65/) | under the POM-reading fallback, a test-scoped in-memory connector counts toward the sole one |
| OI-192 | [SEXTANT-66](https://app.plane.so/portolan/browse/SEXTANT-66/) | Quarkus's Mutiny gRPC forms reach no service identity: the client is unresolved, the service unjoined · **CLOSED 2026-10-26** (PR #70, CI run 40253274692) |
| OI-194 | [SEXTANT-67](https://app.plane.so/portolan/browse/SEXTANT-67/) | an UNTABLED SmallRye connector beside a tabled one leaves the tabled one looking sole |
| OI-195 | [SEXTANT-68](https://app.plane.so/portolan/browse/SEXTANT-68/) | a Quarkus `%profile.`-prefixed key is read as a literal key, not as that profile's value |
| OI-196 | [SEXTANT-189](https://app.plane.so/portolan/browse/SEXTANT-189/) | a call through an injected client interface stays narrowed to every implementor, not the bean the framework injects |
| OI-197 | [SEXTANT-190](https://app.plane.so/portolan/browse/SEXTANT-190/) | curation (FR-15, FR-16; M01, D03) is designed and not built, including correcting a self-call pairing |
| OI-198 | [SEXTANT-191](https://app.plane.so/portolan/browse/SEXTANT-191/) | HTTP, SOAP and messaging self-calls are still a self_exchange question, not ruling C's hop |
| OI-199 | [SEXTANT-192](https://app.plane.so/portolan/browse/SEXTANT-192/) | a delegated identity is read only where the marker call sits on the outer class |
| OI-200 | [SEXTANT-193](https://app.plane.so/portolan/browse/SEXTANT-193/) | a MutinyBean implementor with no delegate field is skipped without a question |
| OI-201 | [SEXTANT-194](https://app.plane.so/portolan/browse/SEXTANT-194/) | a gRPC identity that is contended, not unreadable, still files the "SERVICE_NAME unreadable" question |
| OI-202 | [SEXTANT-195](https://app.plane.so/portolan/browse/SEXTANT-195/) | a gRPC service reaching the generated ImplBase through an intermediate class is not named as its RPC's handler |
| OI-203 | [SEXTANT-196](https://app.plane.so/portolan/browse/SEXTANT-196/) | a grpc-kotlin coroutine stub's self-call is fenced but gets no hop, so its trace ends at a library boundary |
| OI-204 | [SEXTANT-197](https://app.plane.so/portolan/browse/SEXTANT-197/) | an unknown key inside a catalog's delegating_bean block is not refused |
| OI-205 | [SEXTANT-198](https://app.plane.so/portolan/browse/SEXTANT-198/) | C#/.NET has no scanner (language order 7) |
| OI-206 | [SEXTANT-199](https://app.plane.so/portolan/browse/SEXTANT-199/) | Ktor: HTTP client, WebSockets and SSE are not read (Java/Kotlin framework order 1) |
| OI-207 | [SEXTANT-200](https://app.plane.so/portolan/browse/SEXTANT-200/) | Vert.x: one Web row and the WebClient are not read (Java/Kotlin framework order 3) |
| OI-208 | [SEXTANT-201](https://app.plane.so/portolan/browse/SEXTANT-201/) | Python has no scanner: FastAPI, Flask, Django (language order 2) |
| OI-209 | [SEXTANT-202](https://app.plane.so/portolan/browse/SEXTANT-202/) | JavaScript/TypeScript has no scanner: Node.js, Express, NestJS (language order 3) |
| OI-210 | [SEXTANT-203](https://app.plane.so/portolan/browse/SEXTANT-203/) | Go has no scanner (language order 4) |
| OI-211 | [SEXTANT-204](https://app.plane.so/portolan/browse/SEXTANT-204/) | Rust has no scanner (language order 5) |
| OI-212 | [SEXTANT-205](https://app.plane.so/portolan/browse/SEXTANT-205/) | Swift has no scanner (language order 6) |
| OI-213 | [SEXTANT-206](https://app.plane.so/portolan/browse/SEXTANT-206/) | the route-requirements store has no protocol column, so an HTTP and an SSE row with one handler at one path would share requirements |
| OI-214 | [SEXTANT-207](https://app.plane.so/portolan/browse/SEXTANT-207/) | a field-annotation lookup ignored which method wrote the field, so a static setter could borrow a constructor parameter's annotation (fixed on `cov/ktor-client-ws-sse`) |
| OI-215 | [SEXTANT-208](https://app.plane.so/portolan/browse/SEXTANT-208/) | Ktor client base: the last `url(…)` setter by position under a branch publishes one branch's base |
| OI-216 | [SEXTANT-209](https://app.plane.so/portolan/browse/SEXTANT-209/) | Ktor client base: four ladder shapes are read wrongly or declined (a caller-supplied block overriding a declared base — FIXED on `cov/ktor-client-ws-sse`; still open: `config += shared`, a non-parent rung nested in another rung's block, a `headers.append` decline losing a resolved base) |
| OI-217 | [SEXTANT-210](https://app.plane.so/portolan/browse/SEXTANT-210/) | the catalog hash omits `type-models/` and `server-models/`, so an edit there does not change it |
| OI-218 | [SEXTANT-211](https://app.plane.so/portolan/browse/SEXTANT-211/) | Ktor manual SSE (a `get` route writing `ContentType.Text.EventStream`) is an `http` row, not an `sse` row |
| OI-219 | [SEXTANT-212](https://app.plane.so/portolan/browse/SEXTANT-212/) | Kotlin 2.4 metadata is unreadable (`kotlin-metadata-jvm` 2.2.0): every class kotlinc 2.4 compiles is `partial`, loses nullability, suspend returns, parameter defaults and extension-receiver marks, and an extension's `$default` call is mis-projected (fixed on `fix/kotlin-2.4-metadata`) |
| OI-220 | [SEXTANT-213](https://app.plane.so/portolan/browse/SEXTANT-213/) | Ktor type-safe Resources routing (`get<T>`, `handle<T>`) derives nothing |
| OI-221 | [SEXTANT-214](https://app.plane.so/portolan/browse/SEXTANT-214/) | Ktor follow-ups from the final review: four client and verb gaps (logged, not fixed) |
| OI-222 | [SEXTANT-215](https://app.plane.so/portolan/browse/SEXTANT-215/) | dolphinscheduler: a Quartz trigger gains a false cron from an unrelated field writer — **closed 2026-10-29** (value walk: a read on an object from outside borrows no other object's writes) |
| OI-223 | [SEXTANT-216](https://app.plane.so/portolan/browse/SEXTANT-216/) | a nested type in a written chain reads Outer$Inner, not Outer.Inner |
| OI-224 | [SEXTANT-217](https://app.plane.so/portolan/browse/SEXTANT-217/) | two literal branches with different candidates on one path pair every way |
| OI-225 | [SEXTANT-218](https://app.plane.so/portolan/browse/SEXTANT-218/) | inexact answers are not refused by fluent._assembled_text and path_prefix, and with_authority can upgrade them |
| OI-226 | [SEXTANT-219](https://app.plane.so/portolan/browse/SEXTANT-219/) | values._through_receiver now answers not_readable where it passed non_enumerable through |
| OI-227 | [SEXTANT-220](https://app.plane.so/portolan/browse/SEXTANT-220/) | the shadow recorder files narrowed literals as would_resolve |
| OI-228 | [SEXTANT-221](https://app.plane.so/portolan/browse/SEXTANT-221/) | the value walk's memo is keyed without calling frames |
| OI-229 | [SEXTANT-222](https://app.plane.so/portolan/browse/SEXTANT-222/) | Quartz: a trigger chain must reach build() in its own method; a configured cron is read only as the root's direct argument |
| OI-230 | [SEXTANT-223](https://app.plane.so/portolan/browse/SEXTANT-223/) | the execute-join reads content past a getter view; safe only while built values are immutable |
| OI-231 | [SEXTANT-224](https://app.plane.so/portolan/browse/SEXTANT-224/) | constant field writes are not tied to the constructor that made them |
| OI-232 | [SEXTANT-225](https://app.plane.so/portolan/browse/SEXTANT-225/) | Quartz: one job key on two job chains publishes both jobs for one trigger |
| OI-233 | [SEXTANT-226](https://app.plane.so/portolan/browse/SEXTANT-226/) | Quartz: a branch between literals in one method reads as "not tied down" (class, cron) or "not in the code" (name) |
| OI-234 | [SEXTANT-227](https://app.plane.so/portolan/browse/SEXTANT-227/) | value walk: a chained constructor's default is dropped on an object from outside |
| OI-235 | [SEXTANT-228](https://app.plane.so/portolan/browse/SEXTANT-228/) | Quartz: a trigger name read at runtime on one path is ignored when another path states one |
| GAP-1 | [SEXTANT-179](https://app.plane.so/portolan/browse/SEXTANT-179/) | functional routing's BUILDER form is unread, on both stacks · 0 of 20, twice |
| GAP-2 | [SEXTANT-180](https://app.plane.so/portolan/browse/SEXTANT-180/) | the linking tier does not exist · FR-8, M05, M06 |
| GAP-3 | [SEXTANT-181](https://app.plane.so/portolan/browse/SEXTANT-181/) | the async SQS client is read for one call · 1 of 28 |
| GAP-4 | [SEXTANT-182](https://app.plane.so/portolan/browse/SEXTANT-182/) | the messaging templates' receive halves: three of four read, SQS's not |
| GAP-5 | [SEXTANT-183](https://app.plane.so/portolan/browse/SEXTANT-183/) | Spring Integration reads 7 of 11 channel annotations |
| GAP-6 | [SEXTANT-184](https://app.plane.so/portolan/browse/SEXTANT-184/) | Spring Data REST derives for JPA and MongoDB repositories, 7 of 28 contracts |
| G-10 | [SEXTANT-186](https://app.plane.so/portolan/browse/SEXTANT-186/) | FR-11 to FR-14 unbuilt |
| G-71 | [SEXTANT-187](https://app.plane.so/portolan/browse/SEXTANT-187/) | blast radius has no surface at all |
| P-2 | [SEXTANT-185](https://app.plane.so/portolan/browse/SEXTANT-185/) | the CI test job takes ~20 minutes |
| akka-pekko-actors | [SEXTANT-178](https://app.plane.so/portolan/browse/SEXTANT-178/) | register: akka-pekko-actors |
| apache-camel | [SEXTANT-171](https://app.plane.so/portolan/browse/SEXTANT-171/) | register: apache-camel |
| apache-execute-httphost-peer | [SEXTANT-175](https://app.plane.so/portolan/browse/SEXTANT-175/) | register: apache-execute-httphost-peer |
| gateway-and-of-two-paths | [SEXTANT-166](https://app.plane.so/portolan/browse/SEXTANT-166/) | register: gateway-and-of-two-paths |
| gateway-detect-4x-coordinate | [SEXTANT-168](https://app.plane.so/portolan/browse/SEXTANT-168/) | register: gateway-detect-4x-coordinate |
| gateway-order-mid-chain | [SEXTANT-167](https://app.plane.so/portolan/browse/SEXTANT-167/) | register: gateway-order-mid-chain |
| javalin-crud | [SEXTANT-170](https://app.plane.so/portolan/browse/SEXTANT-170/) | register: javalin-crud |
| jdk-body-publisher | [SEXTANT-173](https://app.plane.so/portolan/browse/SEXTANT-173/) | register: jdk-body-publisher |
| jdk-newbuilder-copy | [SEXTANT-174](https://app.plane.so/portolan/browse/SEXTANT-174/) | register: jdk-newbuilder-copy |
| ktor-wildcard-segment | [SEXTANT-169](https://app.plane.so/portolan/browse/SEXTANT-169/) | register: ktor-wildcard-segment |
| quarkus-grpc-mutiny | [SEXTANT-176](https://app.plane.so/portolan/browse/SEXTANT-176/) | register: quarkus-grpc-mutiny |
| quartz | [SEXTANT-177](https://app.plane.so/portolan/browse/SEXTANT-177/) | register: quartz |
| url-openconnection | [SEXTANT-172](https://app.plane.so/portolan/browse/SEXTANT-172/) | register: url-openconnection |

**Stop rules (§13.8).** Third occurrence of an error class → stop and raise.
**Second principle violation → stop and raise.** The running count is below and is
kept here rather than in an agent's head.

---

# GAPS — what Sextant does not yet read

GAP-1 to GAP-6 are Plane items now (the map above). Their figures were measured against the
frameworks' own jars by `scripts/probes/w19_catalog_surface/run.sh`; re-run it rather than
trusting a figure, because a release that adds an addressable method widens a gap without
touching any record.


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

## Closed while listed under OPEN

*Every open entry that stood under this heading is a Plane item now (the map above); what remains closed here, kept as history.*

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

### OI-187 — an `@GrpcClient` on a constructor or method PARAMETER derived nothing · **CLOSED 2026-10-24**
**Major · logged and closed 2026-10-24 (task review of Quarkus gRPC) · `src/sextant/application/resolve/engines/injected_client.py::_matches`**

`io.quarkus.grpc.GrpcClient` targets FIELD and PARAMETER (CP-52 row 2); `injected_client` joined an
annotation to a declared FIELD's type only, so a parameter-position client hit the
`stub_type is None` branch and was skipped: no row, no gap, no question. Measured at the time: 0 of
the 4 `@GrpcClient` uses in `examples/quarkus-quickstarts` were parameters.

**Closed** the same day, once the entry's own check found the parameter annotations were already
recorded: the extractor writes them on the method signature's `parameters[].annotations` (D00 §5a),
beside the declared type. `injected_client` now reads an annotated parameter of a method or
constructor, joined to that parameter's declared type, through the same fence and identity read as a
field — one rule for every `injected_client` catalog, with no per-catalog switch. net.devh's
`@GrpcClient` targets PARAMETER too (`javap` on 3.1.0.RELEASE), so it gains the same read. Pinned by
`tests/application/test_grpc_quarkus.py` and `tests/application/test_injected_client.py`, guard
`injected_client.a-PARAMETER-is-an-injection-point`.

### OI-191 — `injected_client`'s fence was tripped by protoc's own nested classes · **CLOSED 2026-10-24**
**Critical by effect · logged and closed 2026-10-24 (Task 4 field measurement of spec `2026-10-24-quarkus-messaging-and-grpc`) · `src/sextant/application/resolve/engines/injected_client.py::_fenced_outer_classes`**

The fence withholds an injected stub's outbound row when the module implements the service,
judged by any `extends` edge into the stub's outer class. protoc-gen-grpc-java emits
`<Service>FileDescriptorSupplier` and `<Service>MethodDescriptorSupplier`, each extending
`<Service>BaseDescriptorSupplier`, inside every full-protobuf `<Service>Grpc`. Those edges fenced
the outer class by themselves.
- On `grpc-plain-text-quickstart`, `examples/GreeterGrpc#` was in the fenced set, and only those
  two edges reached it.
- On a copy of `fixtures/orders-quarkus`, giving its stand-in stub that pair made the
  `acme.pricing.Pricing` client row vanish, and no question was filed.

So every module that compiles its own `.proto` lost every resolved gRPC client row, net.devh and
Quarkus alike. A published stubs jar gave an unresolved row, so on real code no client row was
ever resolved.

**Closed** the same day. An edge whose subclass is nested in the same outer class as its target
fences nothing, and a module class extending `<Service>ImplBase` from outside it still fences.
Pinned by `test_the_generated_classs_own_nested_extends_edges_do_not_fence` and
`test_a_genuine_implementer_beside_the_generated_suppliers_is_still_fenced`
(`tests/application/test_injected_client.py`), and by
`test_a_quarkus_client_beside_protocs_own_generated_nesting_derives_its_row`
(`tests/application/test_grpc_quarkus.py`). Guard:
`injected_client.a-GENERATED-class-own-nesting-does-not-fence`.

### OI-193 — `supertype_derived` read a generated base's own declarations only, so no real gRPC handler matched · **CLOSED 2026-10-24**
**Major by effect · logged and closed 2026-10-24 (Task 4 task review of spec `2026-10-24-quarkus-messaging-and-grpc`) · `src/sextant/application/resolve/engines/supertype_derived.py::_matches`**

`overridden_public_methods` compared an implementer's methods with those its supertype DECLARES.
protoc-gen-grpc-java emits every handler as a default method on the nested
`<Service>Grpc$AsyncService` interface; `<Service>ImplBase implements BindableService,
AsyncService` and declares only `<init>` and `bindService`.
- Measured on `fixtures/grpc-probe` (1.62.2): the module derived only `grpc-schema`'s row for
  `sextant.grpcprobe.OrderService/GetOrder`, with handler NULL, and no `supertype_derived` row.
- Every real ImplBase service lost its handler (grpc-java, Spring gRPC, net.devh, Quarkus).
  Where `@GrpcService` was present, the corroboration also filed a false `service_identity`
  question.
- The unit tests and `fixtures/orders-quarkus`'s first stand-in both declared the handler on the
  base class, a shape protoc no longer emits, so they passed.

**Closed** the same day. A supertype's members are now what a subclass inherits: the methods it
declares plus those of every type above it, its superclasses and implemented interfaces,
transitively, default methods included (`_inherited_names`, D02 `overridden_public_methods`). It
is pinned on real protoc output by
`tests/e2e/test_grpc_java_inherited_handlers.py::test_an_rpc_inherited_from_the_generated_interface_names_its_handler`,
and on the rebuilt Quarkus stand-in by
`tests/e2e/test_grpc_quarkus_delivered.py::test_a_quarkus_grpc_service_derives_and_is_corroborated`.
Guard: `supertype_derived.a-supertypes-members-are-what-it-INHERITS`. `grpc-java.yml` is the only
`supertype_derived` catalog, so no other catalog's rows can move.

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

## CLOSED

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
