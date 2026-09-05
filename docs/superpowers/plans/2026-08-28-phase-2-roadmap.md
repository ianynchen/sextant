# The coverage program — from Spring Boot to the full estate

What began as "Phase 2 — Spring Boot completeness" is now the roadmap for the whole
committed surface: Java + Kotlin across Spring Boot, Spring Cloud, Micronaut and Quarkus;
Kafka, JMS, SQS and Pub/Sub; protobuf and Avro; GraphQL, WebSocket, SSE and SOAP — plus
the linking tier that turns per-service analyses into a system. Each phase is its own
plan, ships one *capability* and the frameworks that ride it, and ends with the same
review discipline.

**Where we actually are.** Forty-two of the seventy-nine Java rows in
[COVERAGE.md](../../COVERAGE.md) §5 are shipped — about 53%. An endpoint carries request and
response contracts field by field, in both directions, with `required` and `nullable`
resolved; Feign, Retrofit and `@HttpExchange` outbound clients are read (a path a module
both exposes and calls merges into one endpoint), and a module's analysis exports as a D06
bundle. **2G moved none of those rows, and the count is re-derived rather than carried**:
its flips land in COVERAGE §4 — the format-detection regimes, the protobuf and Avro
spec-binding rows, the Kafka serializer table now live as `format_from`, and a new parser
table carrying Jackson 3 — because §5's checklist is one library per row and wire format is
not a library. Every §5 row it touches was already ✅. **2H then moved nine of them**, and
the headline count is re-derived from those flips rather than carried: four in §5.4 (all
three GraphQL annotation frameworks plus the `graphql-java` SDL row), three in §5.5
(jakarta `@ServerEndpoint`, Spring STOMP, the programmatic `addHandler`) and two in §5.6
(Spring MVC's `SseEmitter` and WebFlux's `Flux<ServerSentEvent<T>>`) — 28 + 9 = 37. **2I
then took §5.3 from `2A` to shipped outright, and moved the denominator with it**: its two
existing Java rows flipped (JAX-WS, Spring-WS) and three more were added for surfaces the
phase also ships and the checklist had never enumerated — `@SoapAction` as a second
identity axis, `WebServiceTemplate` outbound, and JAX-WS generated client stubs — so 37 + 5
= 42 of 79. The WSDL/XSD artifact row flipped too (`C` → shipped) and is counted in no
language's cell. The version bump is gated on the full
program below (user decision, twice reaffirmed): no version moves until Java + Spring Boot
and the listed protocols and frameworks are done.

## Why this order

[DR-5](../../ARCHITECTURE.md) links an outbound endpoint to an inbound one only when
**protocol, wire identity and payload compatibility** all agree — *"the failure mode is
fabrication, not imprecision."* That rule ordered the early phases (shapes before
outbound), and it orders the rest: capabilities first, then the frameworks that ride
them; linking only once peers are real and the edge kinds that carry most estates (HTTP +
messaging) both exist.

| | Phase | Status | Delivers | The one new mechanism |
|---|---|---|---|---|
| **2A** | Shapes and nullability | delivered | field-by-field contracts with `required`/`nullable` | field symbols, type annotations, Kotlin nullability |
| **2B** | Outbound annotation clients + export | delivered (PR #3) | Feign, `@HttpExchange`, Retrofit; the D06 bundle exporter | generalized `annotation_driven`; payload descriptors |
| **2C** | Call-site HTTP clients | delivered — [spec](../specs/2026-08-29-phase-2c-call-site-clients-design.md) | RestTemplate, WebClient, RestClient, OkHttp; PTR payloads; lambda-body calls | linked `call_site` facts (the dataflow pass); `single_call` + `fluent` engines |
| **2D** | Messaging | delivered | `@KafkaListener` (class-level + `@KafkaHandler` included), `@JmsListener`, `@SqsListener`, Pub/Sub `subscribeAndConvert`; `KafkaTemplate`/`ReplyingKafkaTemplate`/raw `KafkaProducer`/`JmsTemplate`/`SqsTemplate`/`PubSubTemplate` producers riding 2C's `single_call` engine unchanged; `@SendTo` replies | non-HTTP **wire identity**: NULL method + the path column carrying the destination, no new `endpoints` column |
| **2E-prep** | Hardening + raw messaging drivers | delivered | `catalog_id` provenance on every `endpoints` row; `channel_via`/`when` catalog vocabulary; six surfaces (seven catalog files) of raw drivers — direct jakarta.jms, AWS SDK v2 `SqsClient`, `KafkaConsumer.subscribe`, Google `Publisher`, `Subscriber`+`MessageReceiver`, `KafkaTemplate.send(Message)`; the session-scoped pipeline fixture (suite ~140s → ~50s) | the sixth engine style, `interface_implementation`, gated by a new `implemented_interfaces` capability |
| **2E** | Spring HTTP inbound completeness | delivered | WebFlux functional routing (`RouterFunctions`, `coRouter`, Java and Kotlin), module-local meta-annotations, inherited `@RequestMapping`, `produces`/`consumes` — GraphQL, WebSocket and SSE deferred to 2H; SOAP to 2I | the `combinator` engine, on 2C's indy groundwork |
| **2F** | Configuration resolution | delivered | `application.yml`/properties into `resolved_config`, every profile, environment expressions; declared outbound HTTP bases (a field, a constructor-injected value, `@ConfigurationProperties`) become real peers through the field ladder; Spring Cloud Stream's functional bindings resolve their destination through `config_join` — spring-cloud-aws's own channel-adapter bindings and Spring Integration ride the same engine once catalogued, not yet shipped | the `config_join` engine; D02 §2d made real |
| **2G** | Wire formats | delivered — [spec](../specs/2026-08-31-phase-2g-wire-formats-design.md) | `format`/`format_resolution` on every endpoint row from a six-rung catalog-driven ladder; protobuf and Avro schemas — embedded descriptors and `.proto`/`.avsc` sources, compiled winning per DR-4 — landing in 2A's own `shapes`/`shape_fields` with `field_number` and `json_name` wire names; parse-call payload binding at the handler and one hop; the `open_questions` ledger (table, bundle artifact, document section) for what no pass could answer | format as an inferred channel property, stamped by one late pass rather than per match (D02 §2c) |
| **2H** | HTTP-adjacent protocols | delivered — [spec](../specs/2026-09-01-phase-2h-http-adjacent-design.md) | GraphQL inbound across Spring GraphQL, Netflix DGS and MicroProfile plus the `.graphqls` SDL reader (the field is the endpoint); WebSocket/STOMP `@ServerEndpoint`/`@MessageMapping`/`@SubscribeMapping`/`@SendTo` and the programmatic `addHandler`; SSE by reclassification from a `produces` string or a return-type marker — nine §5 rows flipped | both reserved mechanisms, and neither landed as sketched: operation-as-endpoint identity became the `schema_operations` engine style (the ninth), and `protocol_hint` became a post-merge **resolve pass** rather than an engine |
| **2I** | SOAP | delivered — [spec](../specs/2026-09-01-phase-2i-soap-design.md) | JAX-WS (`@WebService`/`@WebMethod`, both spellings, bare public methods included) and Spring-WS (`@PayloadRoot`, `@SoapAction`) inbound; `WebServiceTemplate` and generated client stubs outbound; a stdlib-XML `.wsdl`/`.xsd` reader and interpreter branch whose input elements derive schema-first operations — five §5.3 rows shipped, on the QName wire identity | **`.sextant.yml`** — opt-in, per-library extraction of a dependency's own bytecode, the first analysis-configuration file living in the analysed repository |
| **2K** | Enrich | delivered — [spec](../specs/2026-09-02-phase-2k-enrich-design.md) | `sextant module enrich` — a jailed, tool-using agent behind the `EnrichmentAgent` port writes add-only overlay claims (components, sections, diagrams, verdicts) at `evidence: llm`, auto-assembled into `architecture.md`/`architecture.html`; the LLM verification seat D02 §2d reserved for doubtful config joins, now real (2F records the evidence, 2K judges it); internal redaction at every trust-boundary exit (render, export, the enrichment tools' own read path) and `.sextantignore`, both default-on | redaction-before-wire; the enrichment jail; first network dependency, wrapped behind a port with `--dry-run`/`--ingest` doors for any other agent |
| **2M** | Build systems and output quality | delivered — [spec](../specs/2026-09-02-phase-2m-build-and-output-design.md) | `GradleDetector` (the project's own wrapper + a read-only init script, offline-first, three honest failure classes); Maven's recursive `<modules>` walk with each non-library, non-BOM module analyzed into its own workspace and pinned in `modules.json`; the four rendered-output fixes — backtick-quoted mermaid identifiers, typed HTML sections replacing the `<pre>` blocks, endpoint/shape readability, inline-code in LLM prose; commit-pinned field checks against two live Boot 4.1 repos | detection by asking the build tool itself — DR-6 applied to Gradle |
| **2N** | Enrichment polish | delivered — [spec](../specs/2026-09-03-phase-2n-enrichment-polish-design.md) | the Tradewind adapter replacing `claude-api` (subscription and api-key auth, module-local session store, the redesigned no-progress guard); config-shaped verdict identities so unresolved-configuration rows become LLM-answerable; the flight-1 INSTRUCTIONS fixes; the `sextant.api` library facade (embed the four verbs, typed errors, CLI byte-unchanged); the first verdict-engine validation flight | the agent behind the port becomes swappable in practice, not just in design |
| **2O** | Spring surface | in progress — [spec](../specs/2026-09-03-phase-2o-spring-surface-design.md) · [plan](2026-09-03-phase-2o-spring-surface.md) | gRPC both halves (descriptor + bytecode, both starters); Spring Data REST's controller-less API; `@RabbitListener`/`@PulsarListener`, legacy `@SqsListener`, Actuator `@Endpoint`; servlets; `@Scheduled` and `@ControllerAdvice` as their own non-wire tables; Spring Integration channels; the `@HttpExchange` direction flip; the served-path identity migration — **details below the table** | **NOT catalogs-only** — that prediction was wrong. Five new engine styles, two extractor capabilities (9.15 varargs, 9.16 nested annotations), and three closed-set amendments |
| **2P** | Spring Cloud + Meridian contract + docs-honesty backlog | planned | Spring Cloud Gateway's config-declared proxy routes (today invisible — a live gateway analysis showed four `lb://` routes the tables cannot see); `lb://` discovery URIs; the Config Server honesty story; **the Meridian integration** ([docs/meridian-integration.md](../../meridian-integration.md), ruled into 2P 2026-09-03): boundary vocabulary (FR-21), derivation diff (FR-22), observability map (FR-23) — FR-24's library embedding largely delivered by 2N's `sextant.api` facade | config-declared endpoints — routes that exist in YAML, not code — plus the typed diff/observability contract a consumer can gate PRs on |
| **2J** | Second frameworks | planned | Micronaut, Quarkus/JAX-RS, MicroProfile REST Client — **zero engine changes is the acceptance test**; then the typed-Catalog refactor | none — that is the point |
| **2Q** | Call graph | planned — ruled 2026-09-04, after 2J and before L | edge resolution over the already-extracted `call_site` facts (declared edge always; a sole in-module implementer resolves, multiple implementers list as a branch, never a pick); a derived `call_edges` table with bounded, cycle-refusing traversal; machine sequence diagrams per endpoint with machine-stated elision; parse binding past one hop, computed base addresses and reactive flow all upgraded by the same walk | the graph itself — six of the sixteen Known-gaps lines retire or shrink |
| **L** | Linking and system scope | planned | `participants`, `links`, DR-5 over bundles; the system document; shape provenance fixed structurally | M05/M06 over federated Parquet |

## What 2O actually carries

**2O gains extractor capability 9.15 — varargs argument modelling — on measured
evidence, and it is the phase's most reusable single change** (ruled 2026-09-04
from `scripts/probes/spring-integration-destinations.md`). `MethodFlow.argumentJson`
does not model the `ANEWARRAY` that builds a varargs array, so every `String...`
destination — `Amqp.inboundAdapter`, `setQueueNames`, `Kafka.messageDrivenChannelAdapter`
— emits one opaque `unresolved` and the literal never enters the fact stream. A
control arm proved the cause is the varargs shape alone: the same eight
destination spellings into a single-`String` sink discriminate every one. So JMS
reads and AMQP does not, purely on signature shape, and today a hard-coded
literal is indistinguishable from an externally configured value for any varargs
API. 9.15 repairs all of them at once — it is not a Spring Integration feature.
**Where a value is still not statically knowable after 9.15, it is marked, not
guessed:** a `channel_destination` open question carrying the channel and
handler, which is already the enrichment pass's inbox (2K §8, 2N's verdict
engine), so the model is pointed at exactly the uncertainties rather than at the
whole document.

### The principles sweep — a checkpoint between 2O and 2P, not a new phase

**Ruled 2026-09-04.** Phases 2A–2N were built before the principles now written
into GUIDELINES §5.3, §5.4, §8, §8.1, §9 and §10 — because **those principles
were derived from 2O's failures**. Every rule there exists because something
shipped without it. So the same defect classes are presumed present in earlier
work, undetected, and 2O already produced the evidence: eleven documented
mechanisms that were never built, a `publishing → library` inference asserting
more than its evidence, a rung-5 doc/code divergence, a path rule applied to a
client library it was never measured against, and a renderer that raised on a
question kind the same phase had added.

**Why before 2P specifically, and not at the version-bump gate:** 2P derives the
Meridian boundary vocabulary from 2O's tables and hands it to an outside
consumer. A fabrication that survives to that point stops being our bug and
becomes someone else's data. Auditing after 2J would be cheaper per phase and
far more expensive per defect.

Five sweeps, each mechanical enough to run independently, ordered by what
actually found defects in 2O:

1. **Near-miss coverage (§10) — highest yield.** For every engine style and
   every catalog: does a test prove it DECLINES on near-miss input? 2O's C-1
   fabricated a gRPC endpoint from an ordinary `extends` pair and the golden
   fixture missed it *by luck*. Every fixture in this repo demonstrates
   detection firing; almost none demonstrates it correctly declining.
2. **Fabrication audit (§8).** For every derivation: what evidence justifies
   each row, and does the rule assert more than that evidence supports?
   **Negative claims deserve the hardest look** — `library` meant "publishes AND
   has no endpoints" and was asserted from publishing alone.
3. **Mechanism existence and behaviour (§5.3).** Extend
   `documented-not-implemented.md` beyond the eleven found: cite the CONSUMER,
   and hunt the costlier second form — mechanisms that ARE read but are gated,
   scoped, or answer differently than the citing document assumes.
4. **Framework fidelity (§8.1).** For every catalog: is its rule MEASURED or
   assumed, and is its version scope stated? A rule taken from documentation is
   a prediction; two of 2O's checkpoints falsified exactly such predictions.
5. **Stale rationale (§9).** Comments justifying an omission whose condition a
   later change silently falsified. Two shipped instances in 2O alone — the
   renderer's "unreached while QUESTIONS stays the two-kind set", and
   `# No stamp — the row already carries its own value`, true under one minter
   and false under two.

The output is corrections, not a report: each finding either fixes shipped
behaviour, retires a boundary, or lands in the register with its evidence.

**2O also wires the two consumers 9.15 unblocked.** Capability 9.15 emits the
varargs elements, but `spring-webflux-router.yml`'s `media_values` and
`kafka-consumer.yml`'s `all_strings` read POSITIONAL arguments, not `elements`,
so their derived output is unchanged — WebFlux media columns are still NULL
even though `MediaType.APPLICATION_JSON` is now in the facts, and Kafka's
multi-topic arity is readable but unread. Their comments and a COVERAGE row had
asserted the extractor could not read varargs, which 9.15 made false and which
that commit corrected in place. Reading `elements` is engine work, small and now
unblocked, and it stays in 2O rather than becoming a note nobody actions —
without it 9.15 is a capability with no visible output.

**2O also gains capability 9.16 — nested annotation arguments** (folded in
2026-09-04, same probe). The annotation-argument collector overrides `visit`,
`visitEnum` and `visitArray` but not `visitAnnotation`, so an annotation nested
in another is dropped entirely rather than recorded as unreadable. That one
missing override is the cause behind three boundaries the spec was about to
state separately: `@Poller` inside `@InboundChannelAdapter`, `@RabbitListener`'s
`bindings = @QueueBinding(@Queue(…))`, and `@Schedules` — which matters most,
because javac folds two or more repeatable `@Scheduled` into it, so the
multi-trigger case currently yields no readable trigger at all. Fixing the
override retires all three. It carries a fact-schema decision with it: D00's
literal model has no annotation-valued argument, so one must be added
recursively, reusing D00's existing vocabulary.

**Nothing from 2O is deferred to a new phase. Two items were mis-sized inside
it, not misplaced (ruled 2026-09-04):** servlets (`@WebServlet`) and Spring
Integration destinations are Spring surface, so they stay in **2O** and their
tasks are re-scoped to state the engine work each needs, rather than being cut
to a later letter. Servlets need a member selector that admits `protected` plus
the Servlet spec's own address/verb rule; Spring Integration needs whatever the
committed destination probe (`scripts/probes/spring-integration-destinations.md`)
shows is actually readable. **Project catalogs — letting a repo declare its own
catalogs — are deliberately NOT scheduled anywhere.** The probe may make them
unnecessary for Integration, and they carry a commitment worth deciding on its
own merits: they would turn D02's catalog schema into a public API, after which
every schema change is a breaking change for users.


## What 2P carries first


**2P carries the documented-but-unimplemented backlog, and it runs FIRST within
the phase** ([docs/documented-not-implemented.md](../../documented-not-implemented.md),
opened 2026-09-04). The sequencing is not arbitrary: 2P's Meridian work (FR-21)
specifies a boundary vocabulary derived from D00/D01/D06, and `root_kind` is
documented in D00 with a full member list while existing nowhere in `src/`. A
vocabulary written from those documents the way 2O's spec was would be specified
against fiction, and would fail at a consumer rather than in our tests. So the
register is settled before the vocabulary is written, not after. Carried in:
`root_kind` (#7), `ClasspathEntry`/`ModuleFact` (#2/#3, if 2O's R9 does not
retire them), the `constant` fact kind (#4, which 2O routed around rather than
implemented), and the recurrence-prevention architecture test — every catalog
key D02 declares must be read by the loader, every fact field D00 declares must
exist on its model. 2O closes #1, #5, #6 and #8 as part of its own tasks.

**The gap program (2M–2P) sits in the table where it runs — ahead of 2J.** A 2026-09-02 gap analysis found build systems and
project shape (gap area A) never priced into that table, plus four rendered-output defects
a live analysis of `examples/jhipster-sample-app` surfaced in a real browser. **2M —
delivered** ([spec](../specs/2026-09-02-phase-2m-build-and-output-design.md)):
`GradleDetector` beside `MavenDetector`, learning a Gradle build by running the project's
own wrapper against a read-only init script; Maven's `<modules>` walk (now recursive) and
Gradle's own settings-evaluation module list, each non-library, non-BOM module analyzed
into its own workspace and pinned in `modules.json`; and the four rendered-output fixes —
backtick-quoted mermaid identifiers so a `$`-named inner class no longer breaks the first
diagram, typed HTML sections (`<h1>`-`<h3>`, real `<table>`s) replacing the machine half's
three giant `<pre>` blocks, endpoint/shape readability (human handler spelling, an
always-emitted detail block, a `### Shapes` subsection), and inline-code/fenced-block
formatting in LLM claim prose. 2N (enrichment polish), 2O (Spring surface) and 2P (Spring
Cloud) follow the same gap program before 2J resumes; the call graph (2Q) lands after
2J and before L, ruled 2026-09-04 — L consumes its traces; the version-bump gate below
is unchanged by any of it.

**The remaining sequence, and its three milestones** (2K deliberately moved ahead of 2J,
ruled 2026-08-31: a complete end-to-end flow for module-level Java/Spring — coverage,
enrichment, docs and export together — comes before any second Java framework; L moved
after 2J, ruled 2026-08-31 post-2F: everything module-level for Java lands first, then
linking services into a system-level architecture begins):

1. After **2I**: Spring Boot module-level *coverage* is complete — every declaration
   form a Spring service uses derives, modulo the named A-tier catalog rows (RabbitMQ,
   Pulsar, Micronaut variants — one YAML file each) and the ledgered extractor
   candidates (vararg constants, batch-listener generics).
   **DECLARED, 2026-09-02.** 2I shipped, and with it the last protocol on **this
   roadmap's** committed list: REST in both directions, GraphQL, WebSocket, SSE, SOAP,
   Kafka, JMS, SQS and Pub/Sub all derive from a Spring service's own declarations,
   carrying configuration-resolved peers, wire formats and field-by-field payload
   contracts. Forty-two of seventy-nine Java rows, and SOAP's §2a column joins
   GraphQL's and WebSocket's as one with no unshipped row left in it.

   **That list is narrower than [REQUIREMENTS.md](../../REQUIREMENTS.md)'s version-1
   scope, which also names gRPC** (§ Scope, and FR-3). gRPC has no shipped Java row at
   all, so it is named in the modulo below rather than folded into this declaration.
   Whether v1 scope should still carry it is the user's decision and is not taken here.

   **What the "modulo" actually covers, stated rather than waved at**, because the
   sentence above is a claim about *committed* coverage and not about every line a
   Spring codebase can contain. Still open and still Spring: the A-tier catalog rows
   this milestone always excepted (`@Scheduled`, `@RabbitListener`/`@PulsarListener`,
   the two older `@SqsListener` package spellings, Actuator `@Endpoint`, Spring 7's
   `version =` and `ImportHttpServices`, and both Spring-side gRPC rows —
   `org.springframework.grpc.server.service.GrpcService` and the Spring Boot starter's
   `net.devh.boot.grpc.{server.service.GrpcService, client.inject.GrpcClient}` — one
   YAML file and a fixture each); two B-tier Spring rows that need a catalog on an
   existing engine rather than an engine (Spring Integration's channel adapters, Spring
   Cloud GCP's `PubSubTemplate.subscribe`); the JVM's own inheritance-shaped gRPC
   server, which is the B-tier row under those two and leaves gRPC — a protocol
   REQUIREMENTS' v1 scope names — with no shipped Java row at all; and the four C-tier
   REST forms where the boundary is not a declaration at all (`@RepositoryRestResource`,
   `@ControllerAdvice` error contracts, servlets and filters, environment-conditional
   controllers). The ledgered engine-side candidates are unchanged — vararg media
   constants and batch-listener generics in the extractor — and 2I adds two on the
   interpreter side: `xsd:attribute` and `complexContent`, which gap a schema file
   today and are cheap to project.

   What this milestone is NOT: it is coverage, not the end-to-end flow, which is
   milestone 2's.
2. After **2K**: the module-level flow is complete *end to end* — analyze → resolve →
   enrich → render → export, nothing stubbed.

   **DECLARED, 2026-09-02.** 2K shipped: `analyze` derives the graph, `resolve` (inside
   `analyze`) applies engines and catalogs, `enrich` runs a jailed agent (or the
   `--dry-run`/`--ingest` door) to add LLM-authored sections behind validation-by-construction,
   `render` assembles both `architecture.md` and `architecture.html` — machine text and
   `evidence: llm` claims together, nothing stubbed in between — and `export` writes the D06
   bundle, `render/` included when it exists. Every stage a module-level analysis needs runs
   start to finish against a real, compiled fixture, with no manual step and no stubbed
   stage — a Known-gaps section stating what a stage honestly could not do is the opposite
   of a placeholder, and stays exactly where NFR-2 puts it.
3. After **2J**: the catalog thesis is proven on second frameworks and the
   **version-bump gate opens** (unchanged anchor — the gate is about Java coverage,
   which linking is not part of).

   **The gate is also the named C-tier descope checkpoint** (ruled 2026-09-04): the
   still-unscheduled rows — `@RepositoryRestResource`, `@ControllerAdvice` error
   contracts, servlets and filters, environment-conditional controllers — plus the
   `json (assumed)` media weakness, Maven profiles/property interpolation, and
   diagram inheritance edges are either scheduled or explicitly descoped BY THE USER
   at the gate, never silently. The permanent honesty boundaries (config constructed
   in code, reflection, DI-proxy indirection, the two-parse refusal) are not on that
   list: they are design, not debt, and the enrichment verdict seat is their answer.

L now comes last, after the gate: linking services into a system-level architecture
starts only once everything module-level for Java is built. Its precondition never
weakens by waiting — 2F's real peers are already in the bundles, and every phase
between here and L only makes the links denser (wire formats make payloads
comparable, 2H/2I add edge kinds, 2J adds frameworks emitting the same tables).

## What each phase is really blocked on

**2C** was the largest single piece of in-house work in
[M03](../../components/M03-scanner.md): `call_site` is
[D00](../../components/D00-fact-schema.md)'s *"load-bearing one"*, and
`chain_reconstruction` *"gates every builder-based client library"*
([D02](../../components/D02-catalog-schema.md)). It shipped as a per-method dataflow pass
emitting linked call sites, with the engines staying catalog-driven joins.

**2D** was blocked on something structural rather than large: the `endpoints` table has a
`method` column because it was built for HTTP; a Kafka topic has no method, and
[D01](../../components/D01-graph-schema.md) already defined wire identity as *"the path
template, the topic expression, the fully-qualified remote method, or the operation
name"*. The catalogs were trivial; the identity was not — and the bet held without a schema
change: `method` reads NULL on a messaging row and the rendered identity drops the verb
(`kafka order-events`, not `kafka NULL order-events`), so `path` alone carries the
destination. 2D's producers rode 2C's `single_call` engine pointed at `send`-shaped methods,
unmodified.

**2F** is the phase that unlocks three stuck things at once: outbound peers for a
DECLARED base address (`client_base_addresses_not_resolved` retires into two narrower
gaps — a base built by computation, `computed_base_addresses_not_traced`, and
configuration constructed in code, `config_as_code_not_read`), Spring Cloud Stream's
functional bindings (`config_join` — code names a key, the value lives in
configuration; spring-cloud-aws's own bindings and Spring Integration ride the same
engine once catalogued), and the environment expressions D06 already reserves a
manifest field for, now populated live from `resolved_config`'s own distinct
environments. It is also what makes **L** viable whenever L runs: links drawn without
real peers are sparse, and links drawn with them are dense.

**2G** exists because two contracts in different formats are not comparable until one is
projected into the other — proto3's JSON mapping renames `total_amount` to `totalAmount`,
so a service defined by a `.proto` but exposed over REST carries different field names
than its own schema states (D02 §2c). Declared shapes land in the same `shapes` tables 2A
built; no second schema. It shipped that way, and the projection is **read, not
reimplemented**: `json_name` comes off the descriptor. Two design points moved during the
build, both recorded in the spec: format is stamped by one late pass over the finished
table rather than resolved per match, and a payload the code parses further out than one
delegation hop is **refused and ledgered** rather than followed — `open_questions` is the
hand-off that makes 2K's seat an inbox rather than a re-analysis.

**2I was billed as "catalog work only, by then", and that was wrong** — an honesty edit
made when the phase shipped rather than an excuse written after it. Roughly two-thirds of
the phase is data, which is the half the prediction got right: five catalog files, seven
framework-neutral vocabulary words on three existing engines, and no framework name
anywhere in engine code. The other third is real code in two places the roadmap had not
counted. The **WSDL/XSD branch** is a reader plus an ~800-line interpreter branch over
stdlib XML — the fourth format the one descriptor interpreter understands, and the reason
the module had to split one file per format — because a contract this protocol is defined
by cannot be read by a catalog. And **opt-in library extraction** is a subsystem, not a
setting: a configuration file in the analysed repository, coordinate resolution in the
detector, jar reading and an origin stamp in the extractor, a scan loop and a discardable
fact subtree, and the attribution that carries the reader's assertion into the document and
the bundle. The prediction was made before anyone asked where a generated stub actually
lives.

**2J** is the payoff proof of the catalog thesis: if Micronaut and Quarkus need engine
changes, the architecture failed its own test. It also marks the point where the catalog
vocabulary is stable enough to justify typing the `Catalog` model.

## History — decisions this roadmap already survived

Shapes came before outbound (2A before 2B) because DR-5 without payload compatibility
fabricates links. Nullability rode shapes because a field set without `required` cannot be
compared directionally. Call-site clients were pulled ahead of messaging by user priority
(functional Spring Boot support first). The 2A scoping round also found the D02
serialisation-naming gap (`wire_name` had no catalog vocabulary), amended before code —
the pattern every later phase kept.
