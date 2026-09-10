# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/) (GUIDELINES §5).

Nothing has been released yet: `0.1.0` is the working version and the
version-bump gate has not opened, so everything below sits under Unreleased.
This file starts at Phase 2O — earlier phases are recorded in
`docs/superpowers/plans/` and `docs/superpowers/specs/`, and backfilling them
here would restate those documents rather than add anything.

## [Unreleased]

### Added

- **A WebClient URL built inside a `uri(Function)` lambda went unread** (`OI-73`, W29).
  `uri(b -> b.path("/orders").queryParam("q", term).build())` is the idiomatic way to build
  a URL with query parameters, and the row derived with `path` NULL and
  `resolution: unresolved` — the call recorded and its whole address lost. That address is
  the row's identity: DR-5 matches on the wire contract, so a pathless outbound row links
  to nothing and tells a reader only that this method calls out over HTTP. The lambda's own
  synthetic method is now walked as a chain of its own and its declared captures folded
  back, one hop, never spliced — chain reconstruction stays within-method (D00 §5).
  Measured on the fixture: `InventoryWebClient#search` went from `path` NULL to
  `/v2/inventory/search`. Reading it is reading rather than guessing, which was the
  objection the earlier behaviour was written against: the lambda is one argument of one
  call and the fact stream names the method it compiled to.

- **A per-direction format split stopped being hidden** (F5 §6.1, W27). A merged row
  carried one `format` column for two directions, and the ladder's rung order decided what
  it said — a media type carried across from the outbound twin answering at rung 2 before
  the consumer's own configured deserializer was reached. Measured on this repo's own
  fixture, which publishes JSON to `order-events`/`order-audit`/`order-returns` and
  consumes **protobuf** from them: all three merged rows read `json`. Each direction is
  its own row now and answers off its own evidence, so the disagreement is on the page.
  The COVERAGE caveat that stated this ("a reader must not read a merged row's `format` as
  a statement about both directions") retires with it.
- **A trace stops where the evidence stops, not at a counter** (FR-6, F7 §8.1, W31).
  The walk carried a depth bound of 64, and FR-6 says a trace should not be bounded by
  depth at all — a divergence `REQUIREMENTS.md` had carried an admonition about for the
  whole of 2Q, and `OI-27` had been open on since. `_walk` is an explicit stack now, so
  the interpreter's own recursion limit is out of the failure modes and nothing needs a
  counter to stay finite. **Measured before removing it**: the deepest trace is **9
  edges** across `mall-admin` (160 traces), `spring-petclinic-rest` (37) and
  `jhipster-sample-app` (38), and no trace was ever truncated. Step order was verified
  rather than argued — a faithful reimplementation of the recursive form produces
  identical step sequences over all 235 roots.
  `TraceStop.DEPTH_LIMIT`, `Trace.truncated`, the rendered `Complete` column, the
  `trace_depth_is_bounded` known gap and one `guard_check.py` guard all retired with it.
  Cycle and revisit refusal stay, because those are correctness rather than bounds:
  without them the walk does not terminate, and expanding a shared subtree once per route
  is exponential on an ordinary diamond.

- **Every markdown table row has as many cells as its header** (F6 §7.3, W40). A row with
  an extra cell looks fine in a diff and in an editor — every cell is there, on one line —
  and looks broken only in a RENDERER, which drops what will not fit. In `COVERAGE.md` the
  dropped cell was the STATUS, so eleven Java rows were reporting their delivery state to
  nobody, 2O Task 9's record and `OI-1`'s among them. 19 rows across four files, plus three
  shapes the plan row did not name: a row with no trailing pipe, a row missing a cell, and
  two rows wrapped across source lines. A test asserts every row against its own header
  across every markdown file the repository ships — with a counter that respects code
  escapes: GFM splits a table row on every unescaped pipe, backticks included.

- **Coverage reports how much was UNDERSTOOD** (FR-17 clause 3, F8 §9.5, W38). It carried
  how many files were opened and nothing about how much of the call graph was read. The
  design asked for one `GROUP BY` on `call_edges.resolution` and warned in the same breath
  that it looks perfect — it does: **100% `resolved` on two of the four corpora**, while two
  thirds of the graph ends at a boundary. `resolution` says whether dispatch settled a call,
  and naming the compiler's target is easy; reading the body is the work. So the reach rate
  leads (78% on `mall-admin`, 32% on the other three), the named distribution follows, and
  `method_resolution`'s reasons say why a body was missed. All three reach `metadata.json`,
  the manifest and the rendered `## Coverage` — composed by one function on both paths,
  since `render` reads the workspace back rather than re-resolving.

- **A row carrying a payload no longer calls itself unresolved** (`OI-77`'s second half,
  found by W43's review). `_capture_resolved` failed a declared body capture whose argument
  was a bare `parameter`, and the whole justification was that the payload column stayed
  NULL either way — so the ROW was the only place a read failure could be recorded. Once
  the column is filled, that premise is gone and the row claims a failure that did not
  happen. The estate proved it inconsistent inside one fixture: `spring-ws-template` reads
  a parameter payload through `path_from_argument_type` and answers `resolved`, while every
  other outbound catalog answered `unresolved` for the identical fact. `_capture_resolved`
  now asks what a capture PRODUCED rather than what kind it read. Measured both ways round: **16** outbound rows had a
  resolved address, a real payload and `unresolved`, and 0 do. *The figure first published
  here was "eight", which was never measured — only the after-state was, and the before was
  asserted.*
  An ADDRESS capture is untouched, because a destination IS its value.

- **PROJECT.md is the delivery authority again, and a test keeps it one** (F9 §10.1, W50).
  Every one of its seventeen component rows read `planned` — including D04, D06, M02, M07 and
  M08, which had shipped for phases. That is C11's finding entire: the file stopped being
  maintained and kept being cited as evidence, and a register that is WRONG is worse than one
  that is absent.
  **Re-measured rather than copied**, because the design's own evidence block had gone stale
  in the same way: **15 tables and 11 views** where it recorded 11 tables. D01's named queries
  are still **1 of 10** — only `trace_of` — but that number alone misleads, so the file now
  also records that five of the nine missing questions ARE answerable today from the index
  bundle, as NDJSON rather than as a named query: callers, implementors, impact, addresses
  and shape carriers. 4 CLI verbs, 64 catalogs, 26 of 26 designed scanner capabilities with
  the three unshipped ones named, and `overlay`/`sync`/`stitcher`/`state.json` absent.
  Statuses are now 8 delivered, 5 in-progress and 4 planned, and each `in-progress` says what
  distance remains rather than rounding in either direction.
  The test checks the two things that can be mechanically wrong — a row claiming more than
  the code carries, and a row understating one that shipped — and deliberately does not
  arbitrate `delivered` against `in-progress`, which is a judgement the file states its
  reasoning for so a reader can disagree with it.

- **Everything the design names now carries a support level, and a test says so**
  (F6 §7.4/§7.5, W42). W41 built the axes and homed twelve items; this is the rest of the
  sets §7.4 lists. Three new sections: **§5.21** Q3's four out-of-scope surfaces — Spring
  Cloud Gateway, Kafka Streams, programmatic Jakarta WebSocket registration,
  `@DgsEntityFetcher` — each `unsupported` with what it would take; **§5.22** the five
  class-file attributes F1 deliberately does not read, with the measurement behind each;
  **§5.23** Q4's declared slices, with what falls outside each.
  The acceptance clause is now mechanical: every item the design names must appear on a ROW
  that also carries one of the three levels, because a row naming an item and stating no
  level reads as coverage while committing to nothing. Verified against both failure modes.
  **The Kotlin parity claim, finally measured.** §5.1–§5.12 hold **186 rows spelled `Java`
  and 0 spelled `Kotlin`** while `coverage_matrix.py` aliases Kotlin into the same matrix
  row — the design calls that "a parity nobody checked". Checked: it is honest for the
  PROTOCOL axis, because these catalogs match fully qualified names in compiled bytecode and
  Kotlin compiles to the same class files, which the fixture's three `coRouter` routes
  demonstrate live. What the merged row cannot show is where Kotlin DIVERGES, and that is
  what §5.13 is for.
  One correction that took three attempts: **exactly one Kotlin row has a live instance** —
  `suspend fun`, whose `$completion` parameter and erased `java/lang/Object` return are
  published for `GET /kt/orders`. Property nullability is NOT exercised: `KotlinOrder` is
  declared, used by nothing, reaches no wire boundary, and contributes none of the fixture's
  54 shape fields. The capability is real and no row in this estate consumes it.

- **STOMP's error contract is in the checklist** (F10 §11, `G-35`, W47). §5.1 has shipped
  `error_handlers` for `@ControllerAdvice` since 2O while `@MessageExceptionHandler` was
  absent from §5 entirely, so a service whose messaging errors ARE handled looked exactly
  like one whose are not. `spring-stomp-advice.yml` reads it through the same
  `error_advice` engine.
  **The advice container is measured rather than assumed from the twin.**
  `AbstractMethodMessageHandler` looks for a `MessagingAdviceBean`, an interface, which
  says nothing about annotations; what supplies them is `spring-websocket`'s
  `WebSocketAnnotationMethodMessageHandler.initControllerAdviceCache()`, whose bytecode
  calls the SAME `org.springframework.web.method.ControllerAdviceBean.findAnnotatedBeans`
  the MVC side calls. `@ControllerAdvice` is the container here because the framework makes
  it one, not because the file was copied.
  **`status_annotation` and `status_from` became OPTIONAL in the engine**, declared together
  or not at all. `@ResponseStatus` sets an HTTP response code and a STOMP handler answers
  over a broker, so declaring one would encode a rule Spring does not apply — every row this
  derives records `status` NULL, and an `@ResponseStatus` written beside a
  `@MessageExceptionHandler` is ignored exactly as the framework ignores it. Requiring the
  pair had forced a catalog to invent that rule or leave the surface uncatalogued.
  One more thing the fixture surfaced: this is its **first `error_handlers` row**. The HTTP
  twin has shipped since 2O and the fixture declares no `@ExceptionHandler` anywhere, so
  that engine was proved by unit tests over synthetic facts and never end to end.

- **The WebSocket client direction exists** (F10 §11, `G-32`, W46). §5.5 held three
  inbound Java rows and ZERO outbound, with no boundary saying the direction derived
  nothing — unlike REST, SOAP and Kafka, each of which states its client side explicitly.
  A module that opened a WebSocket had that call in no export at all.
  **`@ClientEndpoint` is not where the address is**, which is why this is three
  `single_call` catalogs and not an annotation rule: measured at
  jakarta.websocket-client-api 2.2.0, the annotation declares `subprotocols`, `decoders`,
  `encoders` and `configurator` and no address of any kind, so a rule minting a row from it
  would publish an endpoint addressed at nothing. The URL is at `connectToServer`, one hop
  behind `URI.create(...)` or `new URI(...)` — compiled and read back — and `channel_via`
  joins by owner and method NAME, so one entry covers the factory and one the constructor.
  `jakarta-websocket-client`, `spring-websocket-client` and `spring-stomp-client`. The last
  two were ONE file with a two-entry `owner` list until CP-10 refused it: the probe checks
  every declared descriptor against every listed owner, so the file was claiming `execute`
  on `WebSocketStompClient` and `connectAsync` on `WebSocketClient`, neither of which
  declares the other's method. **`peer` is NULL on every client row and the whole URL is the
  `path`** — a deliberate choice, stated in COVERAGE: the address ladder's `channel_via`
  rung is peerless by construction, so splitting the literal rows would publish two address
  SHAPES for one boundary depending on which overload a caller reached.
  And `G-32`'s second half: `jakarta-websocket.yml` named `jakarta.websocket-api`, whose
  2.2.0 jar contains **only `jakarta/websocket/server/**`** — so `@OnMessage`, `@OnOpen`,
  `@OnClose` and `@OnError` were in no coordinate it named. Nothing derived wrongly, because
  `annotation_driven` is not dependency-gated and the file declares no `detect.required`, so
  the coordinates are provenance rather than a fence; corrected because a provenance record
  that omits the jar carrying four of the six annotations is wrong as a record.

- **The URL a STOMP client actually opens is in the export** (F10 §11, `G-42`, W45). A
  module's `@MessageMapping` destinations have derived since 2H and the transport endpoint
  they arrive on existed nowhere, so a reader could see `/orders/place` and had no way to
  learn that reaching it means opening `/ws`. `spring-stomp-endpoint.yml` reads
  `StompEndpointRegistry.addEndpoint`. It is a separate file from `spring-websocket.yml`
  rather than another owner on it, because that file names the RAW handler registry — a
  different interface, and mistaking the two for each other is the gap itself.
  **Varargs collapse into one argument**, compiled against spring-websocket 6.1.6 and read
  back rather than assumed: `addEndpoint("/a", "/b")` records a single array argument and
  derives TWO rows, one per URL registered. Live on the fixture: `/ws`, `/ws-alt`,
  `/ws-legacy`. What is NOT modelled, and says so: nothing links a connect URL to the
  destinations served over it — both read `websocket inbound`, and one is a handshake URL
  while the other is a broker destination. Two true rows rather than one invented relation.

- **Spring MVC functional routing derives** (F10 §11, `G-29`, W44). `spring-webflux-router`
  has read functional routing since 2E and only the REACTIVE package, so a servlet
  application using the same DSL derived nothing at all — its whole routing surface absent,
  with nothing saying so. `spring-mvc-router.yml` reads
  `org.springframework.web.servlet.function`: the argument-rooted
  `RouterFunctions.route(predicate, handler)`, `nest`, all seven `RequestPredicates` verb
  factories, the media predicates, and Kotlin's `router { }`.
  **Measured against spring-webmvc 6.1.6 rather than mirrored from the twin**, which is the
  discipline W43 had just made the case for: the two packages really are structurally
  identical here, and the one thing a copy would have got wrong is the Kotlin entry point —
  `router`, not `coRouter`. Live on the fixture: `GET /mvcfn/invoices` carrying `produces`,
  `POST /mvcfn/invoices` carrying `consumes`, and `PUT /mvcfn/invoices/{id}`.
  **Two defects in the EXISTING reactive catalog fell out of measuring instead of copying.**
  It declared `accept` alone for the Kotlin DSL, on the stated ground that *"Kotlin only
  declares `accept`… no `contentType` call exists anywhere in the checkpoint's Kotlin
  scan"* — the second half is about a fixture and true, the first is about the framework
  and false: `CoRouterFunctionDsl` declares `contentType` too, two overloads. That is §8.1
  rule 1's failure, the examples in front of the author encoded as the framework's rule.
  And neither catalog declared `andOther`, which merges a whole router of a different
  response type along `and`'s exact signature. *What that costs was first stated as "every
  route merged that way was lost", which is not what happens.* Measured by driving the
  engine both ways: undeclared, a merged router still derives at TOP LEVEL — an unclaimed
  continuation consumes neither its receiver nor its argument — and what is lost is a
  PREFIX, `nest(path("/p"), a.andOther(b))` coming out at `/a` and `/b` rather than `/p/a`
  and `/p/b`, with one spurious handler-less row beside them. Neither had a live instance in any fixture or corpus, so nothing published was
  wrong; both are under-reports, and both are closed.
  The surface enumeration gained `RouterFunctions` itself on both sides: only `$Builder`
  was enumerated, so `route()`, `resource`, `resources`, `resourceLookupFunction` and
  `changeParser` sat outside the slice AND outside the enumeration — the one place a reader
  could not have found them. The builder DSL stays outside both catalogs, 0 of 20 each, and
  that is engine work (`G-37`): this grammar roots a route at an argument or a lambda body
  and has no word for a receiver chain.

- **A service that sends STOMP is published sending it** (F10 §11, `G-33`, W43). The
  inbound half — `@MessageMapping`, `@SubscribeMapping`, the `@SendTo` reply — has shipped
  since 2H, and nothing read the outbound half at all, so a service doing both was published
  with half its messaging surface and nothing saying which half. `spring-stomp-template.yml`
  is that half: twelve overloads of `convertAndSend`, `send` and `convertAndSendToUser`.
  **The descriptors could not be copied from the twin the design points at.**
  `KafkaTemplate.send(String, V)` erases to a `String` destination, so mirroring it would
  have declared `(Ljava/lang/String;Ljava/lang/Object;)V` here — and matched nothing:
  `convertAndSend` is declared on `MessageSendingOperations<D>`, `D` erases to
  `java.lang.Object`, and `SimpMessagingTemplate` declares no bridge for it, so a call site
  written `convertAndSend("/topic/orders", payload)` compiles to two `Object` parameters.
  Compiled against spring-messaging 6.1.6 and read out of the bytecode rather than reasoned
  about, and that `String` descriptor is now the near-miss the suite pins — every conjunct
  of the shipped row holds and only the descriptor differs.
  The four `convertAndSendToUser` overloads ship with **no destination capture at all**,
  deliberately: Spring's `UserDestinationMessageHandler` rewrites a user destination before
  the broker sees it, so publishing the literal `/queue/orders` would name an address no
  subscriber holds — an over-report that looks resolved, which is worse than silence. They
  carry the payload and say `unresolved`. The default-destination overloads do the same, as
  `KafkaTemplate.sendDefault` already does. Fixture: 55 outbound endpoints to 57.
  **And a defect found while checking the new rows against their siblings — fixed, not
  filed.** An outbound payload handed straight through from a parameter carried no contract
  at all: `send(OrderEvent event)` calling `template.send(topic, event)` passes
  `{"kind": "parameter"}`, which names no type of its own, and `_reference_of` answered for
  a class literal, a scalar and an `instance` and returned nothing for that — even though
  the type is stated in the CALLER's own signature. `CallFacts` carries those parameters
  now. Measured before and after on the fixture: **3 of the fixture's 25 outbound `single_call` rows carried a payload, and 19 do.** *Re-measured after W46 and W47 added rows: the fixture now has 28 such rows, 19 with a payload, and 47 across `single_call` and `fluent` with 24. The 25/19 figures are the measurement AT THE TIME the rung landed, and are labelled as that rather than silently re-scaled — three earlier attempts at this sentence each named a set that had already moved or never existed.* * The 25/19 figures are the measurement AT THE TIME the rung landed, and are labelled as that rather than silently re-scaled — three earlier attempts at this sentence each named a set that had already moved or never existed.* *Published first as "3 of 27 … `single_call`" and then as "27 across the
  `single_call` AND `fluent` engines" — both wrong. 27 is 25 plus the two `fluent`
  catalogs that happened to be in the list, and across BOTH engines the fixture has 44
  outbound rows with 24 payloads. One wrong label was replaced with a differently wrong
  one; this is the set that exists.* Across six catalogs. The six that still do not have no
  body capture at all. The DESTINATION half is deliberately untouched — a destination IS
  its value and a value lives in whatever called the method, so `parameter` stays in
  `_UNREAD_KINDS` and a `channel_arg` reading one is still `unresolved`. `OI-77`, closed.

- **The checklist gains seven axes beside protocol, and a home for what had none**
  (F6 §7.2, W41). COVERAGE §5 had one axis, so a cross-cutting item could not be a row at
  all: a Kotlin language construct is not a protocol, and neither is a payload wrapper, a
  configuration key, a trace, the bundle, the open-question ledger, the rendered document,
  or a finding about the code's shape. Twelve items were committed in `REQUIREMENTS.md`, a
  design document or the roadmap and enumerated NOWHERE, which is why nobody could look up
  their support level. All twelve now have a row, each carrying one of three levels with
  what falls outside where it is not `supported`. **Eight sections, not the seven the design
  lists**: FR-11 to FR-14 — drift detection, refactor findings, design findings, structural
  performance risk — fit none of the named axes and are four of the twelve, so `§5.20 Query
  and findings` says outright that none of them has a producer, and what each would need.
  Measured while writing them rather than assumed: `suspend fun`, extension functions,
  `$default` synthetics and `DefaultImpls` have no mention anywhere in `extractor-jvm`,
  while Kotlin property nullability is genuinely read from the `@Metadata` blob; HATEOAS
  appears in zero files across all six corpora, so the rule that covers `Page` has never
  been exercised on it and the row says so instead of claiming it works.
  **The first column is never `Language` outside the protocol axis.**
  `scripts/coverage_matrix.py` builds §2 by reading every `### 5.x` heading and counting
  rows by language, so a non-protocol row spelled `Java` would be counted into a cell §2 has
  no column for and then dropped — and a new PROTOCOL section with no column would be
  dropped the same silent way. The generator now refuses either, and it finally has a gate:
  `test_coverage_versions.py` had named its absence in its own opening paragraph as the
  warning it was written against.

- **Reachability is kept, and the tables carry a second ordering** (F8 §9.4, W37). The
  trace walk already computed what each root reaches and threw it away, so "what does
  changing this method affect" was a walk over the whole graph once per question. The
  `reachability` table is that walk's own answer, written by the SAME function the renderer
  calls — a second traversal with its own rules about cycles and revisits would be a second
  opinion, and the day the two disagreed both would be defensible and one wrong. 190 rows
  over 77 roots on the fixture, 3,892 over 160 on `mall-admin`. A root records itself at
  depth 0, and a terminal is recorded by the TARGET the compiler wrote, since no body was
  read to name a callee. `depth` is the SHALLOWEST route, not the first one a depth-first
  walk happens to see: recording the first put 51 rows on `mall-admin` deeper than the
  truth, 26 of them symbols the root calls directly and filed at depth 2 or more, so a
  consumer asking `depth = 1` for "what does this handler call directly" missed every one.
  The table is cleared before it is written, as `roots` is — without that a second
  `analyze` over one workspace doubled every row and the duplicates shipped. Beside it,
  `call_edges_by_callee` and `roots_by_address`: DuckDB over Parquet has no B-trees, so a
  second FILE in a second order is the index, and both are views over the base tables
  rather than copies of them. **The zone-map skipping that ordering enables is inoperative
  at today's sizes and the docs say so rather than implying a benefit**: DuckDB writes one
  row group per 122,880 rows and the largest exported table is 24,591, so every parquet is
  a single group with nothing to skip. What the second file gives today is a second order.

- **The bundle says WHERE, not only what** (F8 §9.3, W35). Sextant could name every symbol
  in a repository without saying which file to open, so an agent holding the bundle still
  had to grep source it had already been told about. `index/` is six NDJSON files beside
  `graph/` and `render/` — symbols, callers, implementors, annotated declarations, shape
  carriers, and addresses — each record self-describing, so a grep hit is a complete answer.
  `GET /v1/orders/{id}` returns `src/main/java/com/acme/orders/OrderController.java:40`.
  **The design's keystone finding, "every line number in the estate is 0", is half fixed and
  half never a gap**: methods and constructors carry real lines, while types and fields carry
  none and correctly so — a class file has no `LineNumberTable` for either — so a type reads
  `line: null` rather than borrowing its first method's. **Placement was the work.** Joining
  the module's `source_roots` placed 157 of `mall-admin`'s 648 documents; a reactor sibling's
  sources live under the SIBLING's root, and resolving through `origin_entry` took it to
  25,521 of 25,521, 24,093 through a sibling. Never an absolute path — a bundle travels. Unplaced
  symbols have two causes: generated code under `target/generated-sources/` (1,285 of
  1,287), deliberately left null because an agent sent to edit a generated file edits what
  the next build overwrites, and a LIBRARY's own classes read out of a jar (2), whose
  sources are not in the repository at all. **The index masks like every other exit** — it reads the same rows `graph/`
  does, and an address published unmasked here would be the bytes the parquet beside it
  takes trouble to strip. **Two more files assemble the join the others leave to a consumer** (W36):
  `files.ndjson`, per file, so an agent decides not to open one — the cheapest win, since
  most of what an assistant spends goes on files opened and discarded — and `impact.ndjson`,
  one record per contract, because nobody says "change `OrderView#totalAmount`" but
  "change `Order`", and what comes back is every place that reaches, already placed.

- **The contract class diagram draws inheritance** (F7 §8.4, W33). The emitter knew one
  arrow — `-->`, the association a field makes — and two more say what a type IS: `<|--`
  extends, `<|..` implements. The work was deciding which ancestors earn one.
  `type_hierarchy` holds all of them and drawing all of them buries the diagram: 30 of
  `mall-admin`'s 34 shape ancestors are a single marker interface, and drawing the
  fixture's put four `<<open>>` boxes above four shapes the `.proto` describes completely.
  An ancestor is drawn when it CONTRIBUTES — it is itself a contract here, or it is an
  unscanned SUPERCLASS of a shape that is already `open`, which is where the unread
  contract lives. Read from that one flag, so the arrow and the `<<open>>` box beside it
  cannot disagree. One arrow each on the three corpora that have any; `<|..` has no live
  instance anywhere and ships pinned rather than deferred, with the absence recorded.
  Verified against the vendored mermaid build in a live browser.

- **A payload publishes the fields it INHERITS** (F4 §5.2). A payload class extending
  another published only its OWN fields and claimed the description was complete.
  `mall-admin`'s `dto/OmsOrderDetail` — a real endpoint's response — published two fields
  with `open: false` where the merged contract is 46 — its scanned parent declares 45, one
  of them a static `serialVersionUID` that reaches no wire; `PmsProductParam` published 7
  of 49, `jhipster-sample-app`'s `ManagedUserVM` 1 of 14.
  DR-5 links services on this comparison, so a 2-field contract that is really 46 fields
  is a match made on almost nothing. **The accessor half hid it**: the fallback to
  accessors runs only where the field pass found NOTHING, and W26 gave that fallback an
  ancestry walk — so a payload with no field of its own came out right and only one with
  SOME field of its own was wrong. The fixture had the first shape; `DetailedOrderResult`
  now carries a field of its own so the always-on gate has the second. The field pass
  walks the scanned ancestry in the order `_closure_of` uses — the superclass chain
  before interfaces — first declaration of a name winning:
  **153 wire fields recovered on mall-admin, 17 on jhipster**. An unscanned SUPERCLASS now
  opens its subtype — fields nobody can see are fields nobody can claim to have described,
  a rule that fires on ZERO shapes across all four corpora and is recorded as such —
  while an unscanned INTERFACE does not (its fields are constants, so a marker interface
  says nothing, and counting it opened 30 of mall-admin's shapes for one), and neither does
  a type whose contract comes from a schema rather than its class file.

- **A call with several possible bodies stops reading as several calls** (F7 §8.3, W32).
  A `narrowed` call site is several candidate bodies with none picked, and the walk records
  one step per candidate. Drawn flat they read as a SEQUENCE — and this was live:
  `spring-petclinic-rest`'s `ClinicServiceImpl#saveOwner` drew `save` to the JDBC
  repository and, eight arrows later, `save` to the JPA one, with the first candidate's
  whole subtree in between, so the diagram said the service saves twice when exactly one
  repository is active. **W32's plan row said this shape "has never fired on real code
  (four corpora, zero occurrences)"; measured, it is 68 edges across 34 call sites on
  petclinic-rest and 2 in this repo's own fixture**, every one of the 34 a repository
  interface narrowing to a JDBC implementation and a JPA one. They draw as mermaid's
  `alt`/`else` now, each branch carrying the candidate's arrow and everything below it —
  nothing reordered, nothing dropped, verified against the vendored mermaid build in a
  live browser. The caption stopped saying "nothing is filtered", which is true and
  useless to a reader who has read the arrows as a sequence, and names the number of
  choices instead. A SINGLE narrowed candidate is not drawn as a choice — a
  defensive guard rather than a live case, since `call_edges.py` writes `NARROWED if
  len(callees) > 1 else RESOLVED` and a lone row cannot occur. §8.3's other clause, "one
  arrow labelled with them when they are not known", has no implementation because it has
  no state to render: a site whose bodies could not be named is `resolved` with a NULL
  callee, already drawn as one `[boundary]` arrow.

- **A terminal says what it reaches, not just that it is one** (F7 §8.2, W30).
  [D00](docs/components/D00-fact-schema.md) §4 declared `terminal_kind` for as long as the
  fact schema has existed and **nothing produced one for two phases** — the note it carried
  gave the right reason, *a data-access call is `persistence` only to something that knows
  the callee is one*, and the renderer said what that cost: "a JDK call and a MyBatis mapper
  call both read `boundary`… the distinction is the reader's to make." That knowledge is
  catalog data now (`terminals`, D02 §2j) and the classification is read, on `call_edges`
  and in the trace tables' new `Reaches` column, with `persistence`'s own `target_kind`
  answering database-or-cache. Measured: **240 of `mall-admin`'s 5,352 terminals** (199
  database, 41 cache), 102 of `spring-petclinic-rest`'s, 70 of `jhipster-sample-app`'s.
  The remaining 94-96% is `StringBuilder`, `Object` and `List`, and reads `unresolved` —
  which says the terminal was examined, where NULL says the edge is not a terminal at all.
  **Three routes and none of them a name match**: an owner type, a supertype read from the
  `superclasses`/`implementations` facts, or the packages a scan annotation registers.
  `mall-admin`'s mappers carry no annotation at all — `@MapperScan`'s own package list is
  how MyBatis finds them — and matching `*Mapper` would have claimed every unrelated type
  ending that way. **Six of `TerminalKind`'s eight members have no producer** and three of
  those are unreachable by any catalog rule (`OI-75`); `target_kind: file` has none either.

- **An outbound call's headers are recorded, each with its own trust columns** (F5 §6.2,
  W29). `endpoint_metadata` is a side table, one row per entry. Measured on the fixture's
  `GET /v2/inventory/tagged`: `Authorization` = `«redacted»`, `X-Tenant` = `acme`, and
  `X-Trace-Id` **present and unresolved** — which is the row the table exists for, because
  "sends a header we could not read" is not "sends no header".
  **Redacted at the origin**: nothing here reads a metadata value, so masking costs no
  analysis and this column needs no export query. It was NOT the only copy — the same
  literal is a `call_site` fact, and shipped verbatim in `call_sites.arguments` and
  `raw_facts.payload` until `redact_json` gained its paired name/value rule. `collects` is a new
  catalog capture kind, distinct from `captures` because every existing capture is
  last-wins — on three headers that keeps the third and says nothing about the other two.
  A varargs position contributes one entry per value, since `header(String, String…)` is
  what the API declares.
  **Query parameters are read too, and with them the URL** — see the Fixed entry below.
  AMQP's routing key was already delivered as part of the address. Kafka record headers,
  SQS attributes, Pub/Sub attributes and JMS properties remain unread and share one cause
  (COVERAGE §3a-vii): they are built as a map, a collection, or by mutation OUTSIDE the
  call the row came from, which is flow analysis this system deliberately does not do.
  Kafka's partition key is blocked by `OI-72`.

- **Two handlers a framework would refuse to register are reported** (F5 §6.1, W28).
  D01 has said since it was written that two handlers declaring one wire contract is a
  routing-ambiguity finding, and nothing detected one —
  `docs/documented-not-implemented.md` row 9 recorded exactly that, and now closes.
  `resolve/routing_conflicts.py` files a `routing_conflict` question naming both handlers.
  **It is catalog data, not a rule**: two rows on one address is ordinary wherever the
  framework dispatches on something else, and this repo's own fixture has such a pair —
  `@KafkaHandler` dispatches by payload type on `order-polymorphic`. Only `spring-web` and
  `spring-mvc` declare `mapping.duplicate: conflict`, because only their annotations reach
  `RequestMappingHandlerMapping`, whose `validateMethodMapping` throws at startup. The
  comparison follows `RequestMappingInfo.equals` read from spring-webmvc 6.1.6 bytecode:
  five and a half of its seven conditions are readable, with `params`/`headers` unioned
  across class and method levels as `ParamsRequestCondition.combine` does, and the seventh
  — a custom `RequestCondition`, which is code — silences the analysis rather than being
  guessed at. The half is the methods condition: it reaches this pass only as
  `derive_endpoints.sql`'s eight-verb expansion, which `_verbs_of` groups back into the
  declared set, and a mapping naming all eight verbs explicitly stays indistinguishable
  from one naming none. Measured across four corpora before building: **zero genuine
  conflicts** and zero uses of `params=` or `headers=`, so the fixture gained the case
  nothing else had.

  Two false positives followed in review and are fixed: the identity compared the FANNED
  verb, so a verbless `@RequestMapping("/x")` collided with `@GetMapping("/x")` — mappings
  Spring registers side by side — and one genuine conflict filed eight questions; and
  discriminators were read from the raw `annotations` view while the endpoint row derived
  through the effective one, so a composed, folded or interface-inherited `params=` read as
  absent.

- **A wire identity served AND called is two rows and a question** (F5 §6.1, W27). It was
  one row, `direction: both`, keeping the handler and carrying the caller and its address
  onto it — which asserts that the thing called IS the thing served, a claim about the far
  end of a call that a module's own bytecode cannot show. The merge keyed on
  `(protocol, method, path)` because `peer` is not part of endpoint identity (RC-5), so a
  path this module serves collided with the same path anywhere in the world. Measured on
  the fixture: of six merged rows, the SOAP one carried `peer: ${soap.billing.uri}` — the
  module's own served operation and a call to the BILLING service published as one
  endpoint, because they share a payload QName — and `POST /v1/orders` merged the module's
  own handler with a call to `orders-loop`. The other four are genuine
  self-publish/self-consume. The rows now stand apart (141 endpoints became 147) and
  `resolve/self_exchange.py` files a `self_exchange` question naming each side and its
  address, because both readings are real and the evidence does not separate them.
  `Direction.BOTH` stays in D00 §4 for the linking tier; no pass here produces it.

- **A payload type whose wire contract is in its accessors, not its fields** (F4 §5.2,
  W26). `Page<T>` and `Slice<T>` are interfaces, so they declare no fields, and shape
  expansion read fields only — the most common paginated Spring response expanded to a
  **zero-field** shape however well the type was reached, naming spring-data-commons in
  `extract_libraries` included. The shape model now declares which methods name a
  property ([D02](docs/components/D02-catalog-schema.md) §2f) and expansion reads them
  where a type's fields describe nothing, across the scanned ancestry, with the same
  substitution W25 gives fields. Measured on the fixture with the jar in reach:
  `Page<OrderView>` goes from an open shape with **0 fields to a closed one with 11**,
  `content` an **array of `OrderView`** — the payload type reaching the reader at last.
  The rule is read from jackson-databind's own bytecode rather than its documentation:
  `is` names a property only on a boolean, a bare `get()` names nothing, and the leading
  run of capitals is lowercased whole, so `getURLValue` is `urlvalue`. G-66 recorded this
  gap with the **wrong cause** — "declared as wrappers nowhere" — and the remedy that
  implies is a fabrication: a `wrappers` entry means the type vanishes on the wire, which
  is true of `ResponseEntity` (already declared by 40 catalogs) and false of `Page`.

- **A generic envelope's parameterisations are distinct contracts** (F4 §5.2, W25).
  `mall-admin`'s 160 endpoints all carried one response shape id; they now carry **58**,
  and `CommonResult<UmsAdmin>`'s `data` field points at `UmsAdmin` where it held an
  unbound `T`. DR-5 gates stitching on payload equality, so one id standing for 59
  payloads asserted that two services exchange the same thing when they do not. A shape
  now records the `origin_tier` of the class file declaring it — **89 of mall-admin's 107
  shapes come from across the module edge** — and a payload type nothing could open names
  the lever that would open it rather than only stating that it is missing.
- **A module reads its declared reactor siblings' types** (F4 §5.2, W24). `CommonResult<T>`
  is compiled in `mall-common`, so 160 of `mall-admin`'s 160 endpoints carried an envelope
  with **zero fields**; all of them now carry `code`, `message` and `data`. Siblings are
  resolved from the DECLARED dependency list, transitively — walking the whole reactor put
  two modules `mall-admin` does not depend on into its workspace, deriving 246 endpoints
  against its own 160 and rendering a neighbour's cron task in its document.
- **A catalog now declares what it does NOT read.** `slice.outside` names, method by
  method with a reason, the part of its framework's surface a catalog leaves out
  ([D02](docs/components/D02-catalog-schema.md) §1c, W19). Catalog presence used to
  mean completeness and never was: `spring-webflux-router` reads **none** of
  `RouterFunctions$Builder`'s 20 methods, so the builder DSL derives nothing;
  `aws-sqs-sdk` reads one of `SqsClient`'s 29 and none of `SqsAsyncClient`'s 28, so an
  SDK-level SQS consumer is invisible and so is every module on the async client; the
  JMS, AMQP and SQS templates model the send half only. `scripts/probes/w19_catalog_surface/`
  enumerates each owner's surface from the jar and
  `tests/architecture/test_catalog_slice_coverage.py` requires every addressable method
  the catalog does not read to be declared.
- **`detect.satisfied_by`** — the annotations that answer a catalog's dependency gate on
  their own. `@ConnectMapping` is RSocket-only, and F2 §3.6 said so, but the gate ran
  before any matching, so a `@ConnectMapping` class in a module whose build named no
  RSocket coordinate derived nothing and asked nothing (W16 review).

### Added

- **`type_hierarchy` and `method_resolution`** (F3 §4.2, W22) — JVMS 5.4.3.3 over the
  scanned closure, computed in one pass and never cached. A call to a method declared on a
  scanned superclass now reaches its body instead of reading as a third-party boundary:
  **131 call sites in `spring-petclinic-rest`**. And "the body is not here" now says which
  kind of not-here, from a closed set of four reasons — 158 calls in the fixture are
  generated code inheriting from library supertypes, which used to be indistinguishable
  from a call into a library we never scanned.

### Removed

- **`TraceStop.DEPTH_LIMIT` and `Trace.truncated`** (W31), with the depth bound they
  reported. `trace_depth_is_bounded` retires from the known-gap list with nothing taking
  its place, and `trace_terminals_are_unclassified_and_cross_module_stops_look_third_party`
  narrows to `cross_module_stops_look_third_party` — W30 classified the terminals, so only
  the sibling-module half of that sentence is still true.

- **The known gap `merged_endpoints_keep_only_the_handlers_contract`** (W27), retired by
  name rather than narrowed: it said a path the module both exposes and calls keeps only
  the handler's declared contract, discarding the client's where the two differ. There is
  no merge to discard it any more — each row keeps its own, so nothing takes its place.

### Fixed

- **A reactor sibling's controllers, schemas and error advice were published as this
  module's** (W24), once siblings were scanned for their types. A sibling's rows are
  dropped before the endpoint merge: after it, a sibling serving an address this module
  CALLS took the module's own outbound row with it, silently. `schema_operations` filters
  its own roots, since it mints rows carrying neither handler nor caller. **A jar named in
  `extract_libraries` is deliberately untouched** — keying the guardrail on the origin
  tier, which both kinds share, deleted a SOAP operation the vertical-slice test asserts
  an opted-in library contributes, and that surface is what a person asked for. A sibling
  is scanned because it is on the classpath and nobody was asked; consent is the
  difference, and it is not readable from the tier.
- **A type variable could be published as a shape id** (W25). A raw `CommonResult`'s `data`
  is declared `T` and bound to nothing; rooting it collides every unrelated `T` in a
  codebase onto one shape. It roots none now, and its owner is reported OPEN rather than
  claiming a complete description of a payload nobody stated.
- **A deleted or renamed class kept publishing its endpoints** (W26). A fact file is
  written whole and never appended to, so a class that is re-scanned overwrites itself —
  but one that was deleted, renamed, or moved to another package overwrites NOTHING, and
  its facts stayed in the workspace deriving rows for source that is not there.
  `discard_library_facts` had this reasoning for an opted-out library since W24; the
  module's own classes had no equivalent. Measured in this repo's own fixture: a renamed
  `Shapes` class went on publishing **two inbound Pub/Sub endpoints**, so the fixture's
  own workspace answered **143** where a fresh one answered 141 on identical source. The
  retraction is keyed on the document's own `origin_entry` — the classes directory the
  scan read — rather than on a list of the subtrees other writers own, so the next
  subtree somebody adds is not deleted by an omission here.
- **A workspace written by an earlier build crashed instead of migrating** (W26).
  `schema.sql` is all `CREATE TABLE IF NOT EXISTS`, which does nothing to a table that
  already exists, so every column added to it since a workspace file was written was
  missing from that file and the first statement selecting one died with
  `Binder Error: Table "shapes" does not have a column with name "origin_tier"`. Columns
  the schema has gained are now added on open. Adding is the whole migration and it is
  enough, because every table but `raw_facts` is rebuilt from the facts on each
  `analyze` and `raw_facts` is emptied and reloaded — nothing is dropped or retyped.
- **A shape holding a collection of an unbound type variable claimed to be complete**
  (W25, found in W26). The guard that marks an owner OPEN read the field's own
  `wire_type`, so a raw type's `List<T>` came out `array` holding an undescribed `object`
  and its owner was reported CLOSED — a complete description of a payload whose element
  type is unnamed. It now follows the element chain. An over-claim is the direction NFR-2
  rates worst, and this one hid itself: `open` is what puts a shape in the gap report.
- **A servlet reaching `HttpServlet` through an intermediate base derived nothing** — a
  stated boundary that existed only while the hierarchy was unavailable (W22).
- **Every Spring Kafka 2.x producer derived nothing** (F2 §4.1). Catalog descriptors were
  compared verbatim, return type included, which made every row version-dependent by
  accident — `spring-kafka-template` declares the 3.x `CompletableFuture` return and a 2.x
  module's identical `send` returns `ListenableFuture`, matching no row and falling through
  to none. Matching is now on parameter types only, which is what JLS 8.4.2 calls method
  identity. Measured across all 96 declared descriptors: zero become ambiguous.
- **A `Subscriber` built and never started was published as a live inbound endpoint**
  (`OI-64`). Construction subscribes to nothing — `Subscriber` delivers no message until
  `startAsync()` runs — and our own acceptance fixture built two, started neither, and
  had both published as endpoints the test suite asserted were correct. Catalogs may now
  declare `registration.started_by`; a registration that is returned rather than started
  files a `registration_activation` question instead of deriving, and one that is built
  and dropped derives nothing.
- **Nine of `PubSubTemplate`'s ten consuming methods were unread**, so every pull-based
  Pub/Sub consumer derived nothing at all — the same output a module consuming no
  Pub/Sub produces (W18).

- **Every Spring RSocket controller was published as `websocket`** — a wrong-PROTOCOL
  fabrication, and `protocol` is the column DR-5 links on, so those rows reached other
  consumers' graphs (W16).

  `@MessageMapping` is the routing annotation for Spring RSocket and Spring STOMP alike, and
  `spring-stomp.yml` claimed it. `docs/COVERAGE.md` had stated the defect in place since
  `A-C1` together with the reason it stayed open: "separating them needs a fact that tells an
  RSocket registration from a STOMP one, and neither catalog reads one."

  **Measured (`scripts/probes/w16_rsocket_versus_stomp.md`): Spring does not distinguish them
  on the class at all.** STOMP's `SimpAnnotationMethodMessageHandler.isHandler` tests
  `@Controller`; the reactive handler RSocket builds on defaults its bean predicate to a
  lambda testing `@Controller` — the same stereotype through the same
  `AnnotatedElementUtils.hasAnnotation` call. So `A-C1`'s type gate could never have separated
  them, and no fact about the class can. What does is which handler auto-configuration would
  REGISTER, which is a dependency fact.

  `spring-rsocket.yml` ships gated on the RSocket libraries, `spring-stomp.yml` is re-gated on
  `spring-websocket`, and both name the STARTERS beside the libraries — F1 does not resolve
  transitives, so a module declaring `spring-boot-starter-rsocket` records only the starter,
  and gating on the library alone would decline exactly the applications the catalog is for.
  `rsocket` joined D00's protocol set in the same change.

  **`detect.coordinates` was read by NO `annotation_driven` catalog**, so both gates were inert
  when first written and the new catalog derived a SECOND row for the same controller — the
  fabrication doubled rather than fixed. Only `derived_resource` and `config_join` are
  `DEPENDENCY_GATED`, and gating the whole style would have been wrong: 20 of the 22 need no
  gate because their evidence NAMES their framework (D02 ruling R9). `detect.required` marks
  the two whose evidence does not.

  The fixture was itself the ambiguous case: its POM declared `spring-messaging` and nothing
  saying which wire `OrderStompController` served, so its five rows were `websocket` on no
  evidence. It declares `spring-websocket` now, as a real STOMP application does — nothing in
  the sources needed it to compile, which is why it was missing.

  A module whose build records NO coordinates earns a new `handler_protocol` question rather
  than a row. That is a different finding from a build that records coordinates and names
  neither library: the second has said something, the first has said nothing, and parent-POM
  inheritance is the real case F1 cannot settle. Both libraries present derives TWO rows,
  which §3.6 calls a correct answer rather than an ambiguity — nothing implements it, so it is
  asserted rather than assumed.

  `spring-stomp` also left `_NO_DECLINING_TEST_YET`: its near-miss is the discriminator
  itself, where every conjunct of the rule holds and only the build differs.

- **A binder nobody mapped was published on the catalog's default protocol** — the one
  defect in this analysis that leaves the bundle and lands in someone else's data (W13).

  `spring-cloud-stream.yml` mapped binder names to protocols and, for a name the map did
  not carry, fell back to its own declared `protocol: kafka`. Measured
  (`scripts/probes/w13_stream_binding.md`): a module bound to `rocketmq` derived a row on
  **`kafka`** — complete, confident, with no open question anywhere saying the protocol
  had not been read. The catalog described this in place as "a gap to grow this map from,
  never a guessed protocol", and a test pinned it under a name that stated the fallback
  outright.

  `protocol` is IDENTITY. DR-5 gates linking on protocol equality, so that row links into
  another consumer's graph against endpoints this module never speaks to, and fails to
  link to the ones it does — in a graph assembled from bundles this analysis never sees.
  No row now, and a new `binder_protocol` question carrying the binding and the configured
  name. The question's own `protocol` is NULL: one that named a protocol would assert the
  very thing it reports as unread.

- **Two function beans and no `spring.cloud.function.definition` derived two endpoints for
  an application that binds neither.**

  The catalog said "absent — every candidate binds, **the framework's own default**". Read
  verbatim out of the framework's own selection code, `normalizeFunctionDefinition` opens
  its guard with `eligibleFunction.size() == 1`: it defaults the definition to a bean only
  where there is exactly one, and with two the definition stays empty and nothing binds. A
  sentence naming the framework as its authority, saying what the framework does not do —
  and nothing had compared it to the code.

  `mapping.unselected_binds` declares the cardinality: `all` (the default, the old
  behaviour) or `sole`. Three utility methods returning functional interfaces no longer
  derive four boundaries — which an existing test recorded as "the honest half" the
  dependency gate does not close.

  **Both cases file a question, and the reasoning that said otherwise was wrong.** The
  first version of this change filed one only for the binder, on the grounds that with two
  or more candidates the framework binds nothing, so no row is the complete answer. That
  needed the count taken here to EQUAL the framework's, and it does not: the framework
  counts registered BEANS while `_candidates` counts every declared method returning one
  of the declared interfaces, an over-count `docs/COVERAGE.md` has recorded since `A-C5`.

  Measured — a module with one real `Consumer` bean beside one ordinary helper returning
  `Function`, no definition configured — derived **nothing at all**, where the framework
  binds the bean. A known over-report traded for an unknown SILENT under-report, which §8
  ranks worse: an absent row nothing explains cannot be told from a module that has no
  such boundary. `sole` files one `unselected_binding` question per candidate now. The
  loss itself needs the `@Bean` conjunct, which is unmeasured (OI-60).

  Two more paths were publishing the default that the first version missed: the
  degrade row for a composed or ghost entry took `catalog.protocol` unconditionally,
  bypassing the binder resolution entirely, and `gaps` filed questions for a catalog the
  dependency gate had SKIPPED — asserting a binding exists for a module that declares no
  Spring Cloud Stream. Both fixed, both tested.

  The ratchet hole §3.4 names in the same breath is closed by two guards, not by
  `test_defaulted_identity_values.py`: that audit reads shipped CATALOGS offline, and
  nothing in the data was wrong — `protocol: kafka` is a correct declaration and
  `binder_protocols` a correct map. The default lived in the engine's fallback. That
  file's docstring now records the blind spot so the next reader does not conclude the
  offline audit covers every defaulted identity value.

- **A class-level and a method-level listener were glued into one address that
  addresses nothing** — `@KafkaListener(topics="orders")` on the class and
  `@KafkaListener(topics="payments")` on a method published **`orderspayments`**, a
  topic no broker carries, at `resolution: resolved` (W14/W15).

  Measured per framework before encoding anything
  (`scripts/probes/w14_listener_registration.md`), from the shipped bytecode rather
  than from documentation. `@KafkaHandler` and `@RabbitHandler` declare exactly ONE
  attribute each — `isDefault()` — and no destination, against `@KafkaListener`'s
  twenty; an annotation that names no destination cannot be an independent
  registration, which settles §3.5's question about them without appealing to any
  behaviour. Both registrars run their per-method loop regardless of any
  class-level annotation, so a method-level listener is always its own
  registration.

  **The three frameworks do not share a gate, and reading method signatures said
  they did.** The first version of the probe inferred "two paths, neither excluding
  the other" from a table of parameter types. Kafka's guard is `iload; ifeq` on the
  class-level annotation's presence, so it registers even with zero handler
  methods; Rabbit's is `getfield handlerMethods; arraylength; ifle`, so it does not
  register at all without one. The probe prints the guard's own instructions now —
  CP-17's convention for exactly this question — instead of describing them.

  `mapping.class_level` declares the relationship: `prefix` composes (the default,
  and what HTTP needs), `sibling` lets a method naming its own destination stand
  alone. The distinction is **whether the member names a destination**, not
  "messaging versus HTTP" — which is why `@KafkaHandler` needs no special case, and
  why the three-member shape (class listener + handler + method listener) now
  derives **two** rows, `orders` and `payments`, rather than trading a fabrication
  for the silent loss §3.5 rejects just as firmly.

  **`spring-sqs.yml` needed it too, and a bounded measurement read as a general one
  nearly hid that.** `@SqsListener` is `@Target(METHOD)` at 3.1.1 — so the shape
  cannot arise — and `@Target({METHOD, TYPE})` at 4.1.1, with an `SqsHandler` and a
  `hasClassLevelListeners` branch, which `scripts/probes/cp17_containers_and_class_level.md`
  had already measured and the catalog's own `measured:` block already names. The
  probe's version scope said 3.1.1; three sentences of its verdict did not, and
  those were the sentences the next wave was going to consume (OI-59).

  The addresses-nothing gate is unchanged, and that is a finding rather than an
  omission: both instances §3.5 named are closed at their sources. The
  `StringConcatFactory` recipe is read since W7/W8, so a hole arrives as `{}` and
  "the template is the wire identity" is a stated rule rather than half an address;
  `orderspayments` never forms now. An empty HTTP address canonicalises to `/`,
  which a controller genuinely serves, so the gate is correctly scoped to the
  non-canonical protocols where an empty address really is nothing.

- **Spring Boot 2's JMS surface was invisible, its SOAP operations were nameless, and its
  JMS envelope was published as a payload contract** — one package rename, three different
  failure modes (W11/W12).

  Jakarta EE renamed `javax.*` to `jakarta.*`; a catalog names types by their fully
  qualified name and compares them exactly, so a catalog naming one spelling does not match
  the other. `docs/COVERAGE.md` asserted *"Both must be matched"* in the indicative — a
  requirement written as a description of what the catalogs did, which is why nobody
  checked. A mechanical sweep of every Jakarta EE type any of the 56 catalogs names found
  **three families in one spelling only**: `jms`, JAXB's `XmlRootElement`, and `websocket`.

  The third was found only after the sweep itself was corrected, and how it hid is the more
  useful half. The sweep read raw catalog TEXT, so a type named in a COMMENT counted as
  named — and `jakarta-websocket.yml` names both `javax` spellings inside a comment saying,
  in as many words, that they derive no endpoint. It reported websocket as carrying both
  spellings while `docs/COVERAGE.md` said "javax.websocket is detection-only". **A sweep
  that reads prose reports a gap as closed because somebody wrote about it.** It parses the
  YAML and reads rule-bearing values now, and counts a Maven coordinate as detection rather
  than as a matched type — which removed four more families from the table that named no
  type at all. That boundary had also outlived its own reason: it rested on
  `mapping.prefix_annotation` being single-valued, which W9 had already widened.

  The failure modes were measured by running the derivation, not by reading catalogs, and
  they are not the same:

  | the rule that named one spelling | what a Boot 2 codebase got |
  |---|---|
  | `jakarta-jms.yml`'s `matches.owner` — a POSITIVE match | **0 rows.** The whole route invisible, which at least reads as absence |
  | `spring-ws-template.yml`'s `@XmlRootElement` read — an IDENTITY rule | **1 row**, right peer, `path` NULL at `unresolved`. Reads as "we looked and the operation was unreadable" when it was never looked for |
  | `spring-jms.yml`'s `request_body.excludes` — a NEGATIVE list | the opaque `javax.jms.Message` envelope published **as** the payload contract |

  **The third is the one nobody would have predicted, and it is worse than either of the
  two the design anticipated.** `excludes` names types in order to REFUSE them, so a missing
  spelling stops the refusal rather than stopping the match: not silence, not a hole, a
  wrong contract at `resolved`. Any rule that names a type to reject it inverts the failure
  this way, and a sweep reading only `matches` will keep missing that class.

  All three are closed. `javax-jms.yml` is a separate FILE, not a second name on the
  jakarta one — those are two jars at two versions needing two measurements, and every one
  of its twelve descriptors was checked against `javax.jms-api 2.0.1` rather than copied,
  because `Session`'s own parameter and return types moved with the API and all four
  compared descriptors differ. The SOAP fix is two names on three rules, since an
  annotation attribute returns `java.lang.String` in either spelling and nothing needed
  re-measuring; it required widening `path_from_argument_type.annotation`, a type-name key
  F2 §3.1's list of twenty-one missed. The `excludes` fix is two more entries in a list.

- **A catalog may spell one type under several names** (F2 §3.1, W9/W10).

  `matches.owner` was one string compared with `==`, and a call site's owner is the
  DECLARED type. `JmsOperations jms = ...; jms.convertAndSend(...)` — the construction
  Spring's own guides show, and what autowiring by interface produces — named a type no
  catalog listed, so it derived **nothing at all**: not a wrong row, no row, silently.

  Twenty-one catalog keys now accept a list of dotted names as well as one, across every
  engine that reads a type name (`docs/components/D02-catalog-schema.md` lists them). A
  scalar stays valid and is what almost every shipped catalog writes. Seven catalogs gained
  an alternate — `JmsOperations`, `AmqpTemplate`, `SqsOperations`, `RestOperations`,
  `KafkaOperations`, and Kafka's own `Consumer` and `Producer` — each measured against the
  library's own bytecode by `scripts/probes/cp10_catalog_descriptors`, which checks every
  alternate separately because an interface declaring a SUBSET of the class's methods would
  match some call sites and miss the rest. All 53 alternate rows come back `declared`.

  Nineteen of the twenty-one are the design's own list. It missed two: `matches.steps[].owner`,
  widened with the `roots[].owner` it sits beside, and
  `matches.methods[].path_from_argument_type.annotation`, which W12 needed. Two of the design's 21 named
  sites are **not** widened: `identity_marker` and
  `supertype_marker` hold a mapping of call specs rather than a type name, so the type sits
  one level below the key the design named (OI-54).

  Where a widened value reaches its consumer the variable is now PLURAL (`owners`,
  `handler_fqns`, `supertypes`). The rename is the mechanism: a consumer still comparing
  with `==` fails loudly instead of comparing a string against a tuple and matching nothing.

  *Its own review found two of the twenty keys widened at the READ site and still refused
  at LOAD — `config_join`'s validators required a string, so the list branch and its helper
  were dead for every catalog that could have used them. It also measured the coverage:
  reverting `catalog_symbols` to return only its first element failed **4 tests out of
  2,407**, and two of those four were unit tests of `catalog_symbols` itself. One test now
  drives every widened key at once — each key in every shipped catalog rewritten from `X`
  to `[<an absent name>, X]`, the fixture resolved twice, the rows required to be identical
  — which fails on exactly that mutation and covers 19 of the 20 keys, all but the one no
  shipped catalog declares (OI-55). The pre-flight that keeps a broken catalog from
  half-emptying the endpoints table checked one key and its docstring claimed the whole
  failure class was closed; it walks all twenty now, and setting `registration.owner` to a
  number in `google-pubsub-subscriber.yml` no longer takes the previous run's rows with it.*

- **Every NESTED record reported `class`** — 73% of all records, introduced by W8 and
  caught by its own review.

  The construct kind was read from the `InnerClasses` access word (JVMS 4.7.6) rather than
  from the class file's own. Measured over javac 21 output for a nested interface, enum,
  `@interface`, record and plain class: the two words agree on `ACC_INTERFACE`, `ACC_ENUM`
  and `ACC_ANNOTATION` — so four of five were right — and differ on `ACC_RECORD`, which
  only the class file's word carries. ASM synthesises that flag in `visit` from the
  `Record` attribute, and the `InnerClasses` table has no attribute to synthesise it from.
  **1,262 of the 1,739 records in the local dependency cache are nested.**

  Zero fixture covered a nested type of any kind, which is why a word that answers four
  questions of five looked like it answered all five. `NestingHost` nests all five now and
  the test asserts every one, because the point is the word, not the record.

- **A package declaring `@NonNullApi` alone had every one of its fields called not-null**,
  and a scoped package claimed its subpackages too.

  Spring scopes parameters and return values with `@NonNullApi` and fields with
  `@NonNullFields`; this scope is applied to a field symbol and to nothing else. The
  justification for listing both — that a payload shape is also built from accessor
  returns — had no consumer: nothing reads an accessor's return nullability. Measured over
  1,672 cached jars: all 613 packages declaring `@NonNullFields` also declare
  `@NonNullApi`, so dropping it costs no field scope anywhere, while **197 packages declare
  `@NonNullApi` alone** — spring-data-mongodb (28), spring-data-repository (14), the
  MongoDB driver (10), spring-hateoas (9) — and every field in them read `nullable: false`
  at `resolution: resolved`.

  Separately, a package scope was matched with `startswith`, so it claimed every deeper
  package under it. `a/b/` and `a/b/c/` are two packages sharing a name prefix and nothing
  else; **462 unmarked deeper packages were claimed by one**. The fixture declared both
  annotations and had no subpackage, so neither half was exercised; it has both now.

- **A malformed `matches.owner` half-emptied the endpoints table.** The conversion ran
  inside the call-site engine, after `endpoints_reset` — so a broken catalog took the
  previous run's rows with it and wrote none, the exact outcome `derive_endpoints`
  resolves every style up front to prevent. It is refused in that same pre-flight now, and
  the refusal names the catalog file and the key instead of only the offending type.

- **A Spring package that declares itself non-null is believed** (OI-48).

  D02 §2e's scope rule inverts Java's permissive default: inside a `@NullMarked` or
  `@NonNullFields` package, a field with NO annotation of its own is not-null, and only the
  exceptions are marked. That is the whole mechanism — measured on spring-web 6.1.6,
  `HttpHeaders` declares 68 fields and **zero** carry an annotation, because the package
  declares the rule once.

  JSpecify's `@NullMarked` was declared in `shape-models/json.yml`. **Spring's
  `@NonNullFields` was not** — and Spring is the framework this reads
  most, with 58 such `package-info` classes in spring-web alone. So a Spring codebase
  declaring its packages non-null read as fully nullable, at `resolution: resolved`, which
  D00 defines as a certain claim rather than a guess.

  **Nothing exercised the rule end to end.** `ScopedRequest` — a fixture built to
  demonstrate exactly this, in a package called `scoped` — was referenced by nothing, so no
  endpoint rooted it, so the shape was never expanded and the rule ran only in a hand-built
  unit test. It is a request body now (`POST /v1/orders/scoped`), and
  `com/acme/orders/springscoped/` declares the same rule in Spring's spelling, reached
  through the payload graph rather than a second endpoint. Both now report
  `nullable: false`; removing the Spring entry puts one back to `true`.

  *The entry that started this was itself wrong, and the correction is on it: it claimed no
  shipped catalog declares nullability, from grepping the catalogs for the block without
  looking for the `shape_model:` indirection that 42 of them use.*

- **Four W7 kinds read a flag, a name or a callback count where the class file states the
  answer** — the same defect class three earlier reviews caught, found again by review.

  **A record with no components read `class`.** `visitRecordComponent` fires once per
  component, so `record Empty() {}` never fires it while carrying the `Record` attribute, and
  `Class.isRecord()` returns true. Measured: 16 such classes in the local dependency cache, in
  Hibernate and Spring Boot — and a marker record is the shape a sealed hierarchy uses most.
  A record's superclass is `java/lang/Record`, which JLS 8.1.4 makes a compile-time error to
  write by hand, so it identifies one outright.

  **An enum constant with a BODY read `enum`.** javac compiles each into an anonymous class
  carrying `ACC_ENUM` whose superclass is the enum, not `java/lang/Enum`; `Class.isEnum()`
  refuses to call those enums for that reason, and kotlinc does not set the bit at all.
  Measured across 1,681 cached jars: 16,563 real enum types and **5,895 classes carrying the
  flag that are not one** — a quarter of every row the `enum_types` query returns.

  **`module-info` and `package-info` were matched by FILE NAME.** A real module descriptor
  states `ACC_MODULE` and a real package file class states `ACC_INTERFACE | ACC_SYNTHETIC`
  with no members. Measured: a legitimate Kotlin class named `` `Xmodule-info` `` produced
  zero documents, zero facts and an EMPTY `uncovered` — a silent total loss through the exact
  hole `Main`'s own comment says was closed. And suppressing a same-named class's TYPE left
  its methods behind with an `enclosing` naming a symbol that no longer existed, because the
  suppression runs after they are emitted. Both now read the flags, and a module descriptor's
  document is written and counted rather than skipped.

  Also closed: `deprecated` on a type and on a field, and the guard keeping class-level keys
  off member facts, were asserted nowhere — deleting any of the three left the whole suite
  green.

- **Two reserved file classes stop putting phantom types into the graph** (W7).

  `module-info.class` and `package-info.class` have a class file's shape and a `this_class`
  naming no type any source declares — `module-info`, `com/acme/orders/package-info` — so
  scanning them minted `class` symbols by those names. A consumer could look for either
  forever (G-61).

  **`module-info` is not read at all.** The first attempt at this read `Module`,
  `ModulePackages` and `ModuleMainClass` and emitted a `module` symbol carrying the module's
  declared name, version and entry point. That was the wrong shape of fix: the phantom
  existed *because* the file was parsed, and nothing here wants a module descriptor. Module
  identity comes from the build's own coordinates, and `requires`/`exports` say less about
  dependencies than the build file already does. Skipping is one line and loses nothing.

  *`ModuleMainClass` would have given OI-22's `entry_point` a producer that is a declaration
  rather than a guess. Measured before deciding: of 52 jars here carrying a module descriptor,
  NONE declares a main class — it is set for an executable module, not a library — so the
  producer would have been correct and fired on nothing. OI-22 stays open.*

  **`package-info` IS still read**, and only its invented symbol is dropped. It is where a
  compiler puts a package's ANNOTATIONS, and a package-level nullability scope (D02 §2e) is
  declared through exactly that target — `shapes/nullability.py` strips the trailing
  `package-info#` to recover the package it claims. Skipping the file would take the scope
  with it, so the two files are treated differently on purpose.

- **Four more JVMS 4.7 attributes, and `construct_kind: record` gets its first producer**
  (W7, second part).

  **`Record` (4.7.30).** There is no `ACC_RECORD` — the attribute's presence is the whole
  signal — so every record in the estate reported `class`. `record` has been in D00 §4's
  closed set since it was written and had no producer at all, which is the "declared, never
  read" defect reached from the other side. Its components are **not** emitted as a second
  fact shape: they are already here as the record's private final fields, in declaration
  order, with their types (measured on the fixture), and a second spelling of one declaration
  would be two vocabularies for it.

  **`Exceptions` (4.7.5).** ASM has always handed this to `visitMethod`; the parameter was
  accepted and discarded. A method's declared `throws` is its own statement about how it can
  fail — the same question `error_advice` answers from the handler side, and unreadable from
  the declaring side until now. It rides inside the signature, because it is part of what a
  caller must handle in order to call the method.

  **`PermittedSubclasses` (4.7.31).** A sealed type names every type allowed to extend it,
  which is the one case where "every implementation of this" is a closed answer rather than
  whatever the scan happened to reach — every other implementation question here is the
  latter.

  **`Deprecated` (4.7.15).** Distinct from the `@Deprecated` annotation a catalog reads
  separately: a class file can carry either, both, or neither.

- **An `@interface` stops reporting itself as an interface, and ten other access flags are
  read** (W7, first part).

  `@interface` compiles to an interface extending `java.lang.annotation.Annotation`, so it
  carries `ACC_INTERFACE` as well — and testing that flag first made every annotation type in
  the estate report `construct_kind: "interface"`. `ACC_ANNOTATION` is the distinction the
  class file makes, and §8.1 rule 5 says to follow one the provider makes rather than flatten
  it. `construct_kind` gains a fifteenth member, which is a fact-schema change and was ruled
  in the design.

  **Measured before trusting it**, because this is the one W7 flag that changes a derived
  value rather than adding one: the fixture's two annotation types move, interfaces go 18 to
  16, and three endpoints DISAPPEARED — `GET /api/composed`, `GET /composed` and the
  `composed-orders` listener. The meta-annotation composition pass finds an annotation type
  through a query named `interface_symbols`, named for what annotation types used to report.
  It now selects both kinds, and the three rows are back. The design's own blast-radius note
  covered catalogs declaring `declared_on: interface` and missed this one, which is why the
  fixture was run rather than the note believed.

  **`varargs` unblocks capability 9.15.** `f(String...)` and `f(String[])` compile to one
  descriptor — in the fixture both hash to `sig_05a88677` — so a call passing three strings
  and one passing `new String[]{…}` were the same declaration. **`abstract`** tells an
  interface's `default` method from its declared ones, which emitted identical modifiers.
  `final`, `native` and `synchronized` join them on a method; `final` and `volatile` on a
  field; `abstract` and `final` on a type, which carried no modifiers at all.

- **Sextant can say WHERE, not only what** (W6). Three JVMS 4.7 attributes that were being
  dropped, and one derived answer that was wrong rather than absent.

  **`LineNumberTable` (4.7.12) — §9.2's keystone finding.** Every line number in the estate
  was `0`: measured on mall-admin, 1,428 symbols, `line_start: 0` and `line_end: 0` on all of
  them. An index that cannot produce `file:line` saves nobody a grep. Methods and constructors
  now carry their real extent — 707 of the fixture's 766, and 7,525 of 8,320 across spring-web
  6.1.6's 1,117 classes, the remainder being abstract or native methods that carry no `Code`
  attribute to hold a table. It is the extent of the CODE: a signature compiles to no bytecode, so the first
  line a method can state is its first statement, and subtracting to reach the declaration
  would be a guess about formatting. `0` still means "not stated" and cannot collide with a
  real answer, since source lines are numbered from 1.

  **`SourceFile` (4.7.10) — a fact that was WRONG, not missing.** `relative_path` was derived
  from the class's own path: `.class` swapped for `.java`, everything from the first `$` cut
  off. That is javac's conventions written into the scanner, and every other JVM compiler
  defeats it — measured on this repository's own fixtures, `KotlinOrder.class` was reported as
  `com/acme/orders/contracts/KotlinOrder.java`, naming a file that exists in no module, and
  every `KotlinOrderRoutes$…` lambda class named the same non-existent file. The class file
  states the name outright; only the directory is ours to supply. Blast radius measured: the
  fixture's 79 distinct source paths, the 2 Kotlin ones gain `.kt` and the other 77 are
  unchanged. A value carrying a path
  separator is refused and the derivation stands in — what a class file says about itself is
  evidence, not an instruction.

  **`LocalVariableTable` (4.7.13) — parameter names nothing else supplies.** It fills a name
  only where `MethodParameters` stated none, that attribute being the specific one. Measured
  on spring-web 6.1.6: 1,048 of 9,164 names come from here and from nowhere else — established
  by turning the fill off and re-running, not by counting what ended up named. A slot is not
  a parameter index — a `long` or `double` takes two (JVMS 2.6.1), and an instance method's
  slot 0 is the receiver — so the slots are walked with the descriptor rather than counted;
  and a slot is reused once a variable leaves scope, so the entry taken is the one scoped from
  the method's first instruction, which only a parameter's is.

  **Also caught, in passing:** `Capabilities.ALL` states in its own javadoc that it is sorted
  for byte-stability (NFR-1), and nothing checked it. W6's own additions broke it. It now has
  a guard, along with one for duplicates — which would read as one name to every consumer
  (they all take a set) and as two in the report.

- **A compiler-generated bridge is read from the fact, and its mapping now lands on the
  method someone actually wrote** (OI-47, closed).

  Spring's annotations are inherited from an interface or superclass, and Sextant walks that
  hierarchy to work out a handler's effective mapping. The ancestor lookup joins by method
  name AND descriptor — so for a covariant or generic override, whose descriptor is by
  definition not its ancestor's, the only thing that can match is the forwarder javac
  generates beside it. The bridge is therefore the only method that resolves, and it is the
  wrong answer to publish.

  Which method is the bridge was inferred from shape — same class, same name, same
  parameters, different return — and that was wrong in **both** directions, measured:

  | Bridge differs from the real method in | Rule saw it? | What shipped |
  |---|---|---|
  | return type (covariant override) | yes | both excluded — the mapping was **lost** |
  | parameter types (generic interface) | **no** | the row named **the synthetic bridge** |

  The second is a fabrication: a class implementing `Api<String>` published its handler as
  `handle(Object)`, a method no source file contains.

  A method fact has stated the answer since the `modifiers` slot shipped — `modifiers.synthetic`,
  with `ACC_BRIDGE` folded in because javac sets the two together — and the rule's own comment
  claimed the opposite (*"Bytecode carries no other marker — no `modifiers`"*). It is read now,
  and a bridge is treated as **evidence rather than a target**: the mapping it resolves is
  carried across to the same-class, same-name, non-synthetic method it forwards to. Exactly one
  such method, or nothing at all — several same-named methods a human wrote leave nothing
  saying which the bridge stands for (§8). The structural rule stays as the fallback for a fact
  carrying no `modifiers` key at all.

  **The wiring is the part that had to be proved.** The first attempt added the column to the
  query and stopped: `annotation_driven._method_declaration_rows` is the only producer of these
  rows and rebuilt them without it, so every real run kept the old behaviour while every test
  about the new one passed — they hand-build their own rows. Measured on the fixture now:
  `GET /api/orders/{id}` derives where it did not before, its handler naming the covariant
  override rather than javac's bridge, and the module's endpoint count moves 122 to 123 with
  nothing else moving.

  **Finding I1's outcome is unchanged for DIFFERING mappings, and its reason is now honest.** A class overriding one
  method against two mapped ancestors grows two bridges that redirect to one method; it still
  derives nothing, but because two ancestors give one method two different answers and this
  pass does not read the framework's own annotation search order — not because every bridge was
  discarded. Closing that means mirroring the framework exactly (DR-6), which is its own work.

- **The `Signature` attribute is read for the half of it that was being dropped** (W5).
  It was already read for field types, method RETURN types, the generic superclass and the
  generic superinterfaces. It was not read for method or constructor **parameter** types, nor
  for the formal type parameters a class or method declares. A fact could therefore say a
  method returns `Map<K, T>` while being unable to say what `K` or `T` were, and every
  parameter arrived erased.

  **Two documented gaps close outright**, both in the messaging fixture and both previously
  frozen as honest limitations with a test asserting the wrong answer:
  `onBatch(List<OrderEvent>)` now reports `wire_type: array` **carrying its element**, and
  `onDeadLetter(ConsumerRecord<String, OrderEvent>)` now reaches its payload through the
  catalog's declared `payload_arg: 1` and reports `OrderEvent` instead of nothing. The
  checkpoint's own expectation for that row had been recorded as not holding against the
  scanner's real output; it holds now.

  **`type_parameters` is new on a class or method symbol fact** — an ordered `{name, bounds}`
  per formal type parameter, emitted only where a declaration has any. Bounds are recorded as
  the signature states them, an explicit root-type bound included, because `<T>` and
  `<T extends Object>` compile to identical bytes and an empty list would otherwise mean
  either "unbounded" or "not read". It is declared as a capability so a catalog can require
  it, and it has **no consumer yet** — W25 is where generic substitution reads it, recorded
  as OI-46 rather than left to be discovered.

  **Aligning the descriptor's parameters against the signature's is done with the class
  file's own flags, not by counting**, and the first attempt here did count. JVMS 4.7.9.1
  lets a signature omit implicitly declared parameters, and a compiler may also omit ones it
  synthesised — but the difference in LENGTH does not say which. Measured: an inner class's
  constructor carries the enclosing instance first and an enum's constructor its name and
  ordinal first, while a local class that captures carries its captures **last**. Counting
  from the end is right for the first two and puts a collection's element type onto an `int`
  in the third — a perfectly well-formed fact that is false. `MethodParameters` (JVMS 4.7.24)
  distinguishes them: `ACC_MANDATED` and `ACC_SYNTHETIC` mark exactly the parameters a
  signature may omit, wherever they sit. Where the attribute is absent, or its flags do not
  account for the difference, every parameter keeps its erased type — less specific, never
  wrong. A local class inside a **static** method is the real case that needs that fallback:
  captures at the end and no `MethodParameters` at all.

  **A parameter keeps the descriptor's symbol too, as `erased_symbol`.** Reading the
  signature was first written as REPLACING the parameter's type, and that deleted something
  four consumers were using. A parameterized type is unaffected — `List<String>` was and
  still is `java/util/List#`, it merely keeps `String` now — but a bare **type variable**
  changes from its erasure to its name, and **a type variable's name is scoped to the
  declaration that introduced it**: an interface calls it `E` where its implementation calls
  it `T`, for one method. Four consumers compare or look up by a parameter's symbol ACROSS
  declarations, and each broke differently:

  | Consumer | What it does | What replacing the symbol did |
  |---|---|---|
  | `derive_endpoints.sql` overload dedup | partitions on the parameter symbols | `m(E)` and `m(T)` land in two partitions: one method, two published rows |
  | `effective_annotations._is_bridge` | matches an override's parameters against its bridge's | the bridge carries no signature, so the pair stops matching and the **synthetic bridge stops being excluded** |
  | `supertype_dispatch` selector | matched against a catalog-declared parameter type | a variable's name matches no declared type |
  | `single_call` payload lookup | reads annotations OFF the named type | `<T extends OrderEvent> handle(T)` resolved through `OrderEvent`; `T` resolves through nothing |

  A second review found the sweep was short: there are **six** such consumers, not four.
  `interface_implementation` compares an interface's parameter tuple against an
  implementation's — a `Handler<E>` read `E`, matched neither the override nor its bridge, and
  the subscription's handler attribution was lost outright. `error_advice` tests a parameter
  against the set of throwable types the workspace declares — a generic advice base
  (`handle(E ex)` where `E extends BusinessException`) matched nothing and its exception list
  emptied. Two more compare against catalog-declared type names
  (`shapes/contracts.py`'s `sole_unannotated` exclusions, `shapes/parse_binding.py`'s
  `bytes_payloads`).

  So the fact carries both: `type` is the signature's answer, which is what a substitution
  binds and what closed the two gaps above, and `erased_symbol` is the descriptor's, which is
  what can be compared between declarations. All six read `erased_symbol` and are back to
  exactly their previous answers — restored, not improved: `_is_bridge` keeps its structural
  rule rather than switching to the `modifiers.synthetic` the fact already carries, because
  that would also erase a documented over-exclusion, which is its own change (OI-47).

  **One place deliberately does NOT switch**, and gains a guard instead. `_body_type` roots a
  request shape at the parameter's declared type — reading the signature there is what closed
  the two gaps above — but a shape is identified BY its symbol, and `@RequestBody T body` on a
  generic base controller would mint a shape whose id is `T`, which every unrelated `T` in the
  module then collides onto. It now roots no shape at a type variable: no answer rather than
  one shape claiming to describe several unrelated payloads.

  `erased_symbol` is written on **every** parameter, not only where the two differ: a JSON
  path wildcard drops elements whose key is absent (measured in DuckDB — three parameters,
  two entries returned), so a sparse key yields a shorter list that misaligns against the
  parameters it describes. That is the same class of defect as the descriptor/signature skew
  above, reached a different way.

  **`ACC_MANDATED` does not mean "omitted from the tables", and reading it that way deleted
  a fact.** The first version of this fix stated that premise and acted on it, and a record's
  COMPACT canonical constructor disproves it: javac flags EVERY slot mandated there — what is
  implicit is the constructor, not its parameters — while the tables omit nothing (measured:
  two parameters, both mandated, a full-length parameter-annotation table, a type annotation
  at `param_index=1`). `Signature` and the parameter-annotation table each carry a count to
  corroborate the flags against and were unaffected; `METHOD_FORMAL_PARAMETER` (4.7.20.1)
  carries none, read the flags blind, concluded the method declares no parameters, and
  **dropped every type annotation on a record component** — a type-use `@Nullable`, gone. An
  empty flag result now means "the flags say nothing", never "there are no parameters".

  **The parameter-ANNOTATION table was wrong the same way, and is fixed with it.** Three
  attributes are indexed by declared parameters rather than by descriptor slots —
  `Signature` (4.7.9.1), `Runtime[In]VisibleParameterAnnotations` (4.7.18) and
  `METHOD_FORMAL_PARAMETER` type annotations (4.7.20.1) — and each was aligned by its own
  arithmetic on counts. Measured: `@Labelled` written on a capturing local class's
  `List<String>` parameter was landing on the captured `int`, in both the instance form and
  the static form. All three now read one helper over the `MethodParameters` flags, so they
  cannot disagree with each other. Where no flags exist the index is taken as the slot,
  stated as measured rather than as a property of the format: every shape that omits from
  the FRONT carries flags saying so, and the one measured shape that carries none — a local
  class in a static method — appends its synthetics.

  Kotlin needs no alignment and is pinned saying so: kotlinc writes a full-length signature
  (a `suspend fun`'s trailing `Continuation` appears in both lists) and its `$default` bridge
  carries no signature at all, so neither path reaches the flag-based alignment.

- **The field check stops refusing a pin it does not need to build** (`scripts/field_check.py`).
  Its JDK guard ran before `_ensure_compiled` decided whether a build was needed at all, so
  `mall-admin` — already compiled at the pinned commit by a JDK 21 — was refused on a machine
  whose Maven reports 26. Nothing was going to invoke Maven, so there was no wrong toolchain
  to prevent, and the message reported "this pin cannot be validated" for what was really
  "this machine cannot BUILD this pin". The guard now runs on the build path, where it
  belongs, and both arms are tested. The field baseline is 3/3 from the script again.

- **Four JVMS 4.7 attributes that each stood in for an invented rule are now read** (W4).
  Every one was already in the class file, and one was being handed to us by ASM as a
  parameter we ignored.

  **`ConstantValue` (4.7.2)** gives D00 §5's `constant` fact its first producer — a declared
  fact kind with nothing emitting it. `static final String TOPIC = "orders"` is how a great
  many real listeners name their destination. 19 such facts from the fixture; a field
  initialised in `<clinit>` correctly yields none, because what a static initialiser computes
  is a different question.

  **`InnerClasses` (4.7.6) and `EnclosingMethod` (4.7.7)** give a nested class the enclosing
  symbol it reported as `null`. `OrderResult$Detail` → `OrderResult#`, and — the half that
  splitting a binary name on `$` can never recover — `BillingRestTemplate$1` → its enclosing
  METHOD. The class symbol is now emitted at `visitEnd` and re-inserted at index 0, because
  ASM fires `visit` before those attributes arrive; the fact stream's order is unchanged.

  **`AnnotationDefault` (4.7.22)** reads what an annotation element falls back to, which
  catalogs currently hardcode — a claim about a framework at a version nobody measured.
  All four value shapes verified: string, int, array, boolean.

  **`StringConcatFactory`'s recipe** turns an assembled address into a template. Before this,
  `"/api/" + version + "/orders"` reached a catalog as `{"kind": "unresolved"}` — an outbound
  call naming nothing at all. It now reads `/api/{}/orders`.

  **The hole stays unnamed deliberately.** A path variable's name was never part of the
  address — a server routes `/api/owners/42` to `/api/owners/{ownerId}` by POSITION and could
  rename the variable without changing the wire — so `{}` is exactly what both sides share.
  Normalising the name away lines a client template up with a server route
  (`/api/owners/{ownerId}` ↔ `/api/owners/{}`), which is what makes the recorded address
  matchable at all. Naming it would also invent a name: the class file carries a parameter's
  name only when the build asked for it, and the filler is often not a parameter.

  **The matching itself is phase L, not this.** Whether a template is ambiguous depends on
  the set of routes it is compared against, and those live in another service's bundle. What
  W4 delivers is an address recorded in a shape that will match, instead of one lost entirely.


- **Multi-release selection is applied, so G-62 is fixed rather than renamed** (W3c, Fork 4
  rule 3). W3 tagged every copy and dropped none, which by itself left LABELLED duplicates —
  two documents minting the SAME type symbol, and no table downstream has a uniqueness
  constraint. That was the caution Fork 4 attached to its own ruling, and this is what
  discharges it. Measured on a jar holding one class at base and at release 21: **12 symbols
  with 6 duplicated, becoming 6 with none.**

  The JVM's own rule (JEP 238): among copies of one class name, the highest release not
  exceeding the module's target wins, else base. The target is W3b's declared release —
  which until now had no consumer at all.

  **Applied where the tables are built**, not merely computed: `symbols`, `annotations`,
  `call_sites`, `method_returns` and `field_writes` each exclude documents that lost. A
  selection nothing acts on would have renamed the bug.

  **Nothing is deleted.** Every copy stays in `documents` with its release, so a reader can
  see what was selected between rather than only the winner, and `selected_documents` travels
  in the bundle so a consumer can tell which copy the derived rows came from.

  Three branches, each pinned by a test and each mutation-checked. A class overlaid ONLY
  above the target — 626 such names in the measured corpus — keeps its lowest copy rather
  than vanishing: dropping it would assert the class does not exist, which is false. A module
  declaring no target reaches the highest overlay rather than base, which is the JVM's
  behaviour on a modern runtime and beats preferring a base copy the build may have overlaid
  precisely because it does not work — `spring-core`'s own base `VirtualThreadDelegate`
  throws from every method.

### Added

- **The build's declared Java release is read** (W3b) — `maven.compiler.release` and its
  siblings on Maven, Gradle's own evaluated model on Gradle. **Nothing read any of them
  before**: `grep -rn "maven.compiler\|targetCompatibility\|sourceCompatibility" src/`
  returned nothing. §8.2 admits the value — it is written in the pom or build script, so it
  is code rather than a deployment possibility.

  **Maven** reads it from the `<properties>` already merged across parent inheritance, so no
  second walk of the ancestor chain is needed. maven-compiler-plugin's
  `<configuration><release>` is read FIRST, because `maven.compiler.release` is only the
  default expression for that parameter and an explicit configuration overrides it — then
  `release`, `target`, `source`, and `java.version`, which is the one Spring Boot's parent
  sets. `1.8` and `8` both reduce to 8; the legacy spelling is still what older builds carry
  and reading one form only would miss half the estate. A `${property}` nothing defines
  yields absence, not a guess.

  **Gradle is ASKED rather than parsed**: the value can come from a convention plugin, a
  toolchain or a property, and only the evaluated model knows which won. The init script
  reports `options.release`, falling back to `targetCompatibility`. Verified by a live run
  against `fixtures/gradle-orders` — both Java projects report 21, the root project (no Java
  plugin) reports absence — and the committed capture was brought in step with those
  measured values.

  A module whose build declares none reports `None`, which sends multi-release selection to
  its next source rather than to a wrong answer. **Its consumer is W3c**, still to come.

### Fixed

- **Multi-release jars stopped being scanned whole** (Fork 4, G-62), `fact_schema_version`
  4 → 5. `JarSource.names()` filtered on `.class` and nothing else, so every overlaid copy
  was scanned: the copies got different `document_id`s while minting the SAME type symbol,
  and no table downstream has a uniqueness constraint, so they became duplicate rows.

  **The manifest attribute gates everything, and it is read once per archive.** Without
  `Multi-Release: true` the JVM never searches `META-INF/versions/`, so those entries sit at
  a path no loader will look in — unreachable code whose symbols collide with the reachable
  base copies. They are now not scanned at all, which is different from treating them as
  ordinary classes. Measured on the real case: `testcontainers-2.0.5.jar` carries **1,218**
  versioned `.class` entries under a manifest holding only `Manifest-Version` and
  `Implementation-Version`; all 1,218 were scanned before and none are now. It is a parsed
  attribute lookup, never a grep — the jar spec makes attribute names case-insensitive and
  manifest values fold at 72 bytes with a leading-space continuation.

  **Where the attribute IS present, every copy is kept and TAGGED** with `class_release`.
  Nothing is selected here: which copy loads depends on the release the depending module
  targets, so one scan serves modules targeting different ones, and deciding in the
  extractor would force a re-scan per consumer and put a config-derived judgement inside the
  fact layer. Verified on `spring-core-7.0.9.jar`: 1,223 documents, tagged `base` 1,213 ·
  `21` 1 · `24` 9.

  **And an overlay stops naming a source file that cannot exist.** `sourcePathOf` yielded
  `META-INF/versions/21/org/…/VirtualThreadDelegate.java`, which names no file in any
  repository; the prefix is stripped first, so it now reads
  `org/springframework/core/task/VirtualThreadDelegate.java`. An overlay is a different
  COMPILATION of one source, not a different source.

  **Not yet done, and the tag alone changes nothing without it:** the duplicates are now
  LABELLED duplicates. The filter that acts on the label — highest `N ≤ target`, else base —
  is W3c, and the target it needs is W3b's declared-release read.

- **A parameter annotation on an enum or inner-class constructor landed on the wrong
  parameter** (Critical 6, JVMS 4.7.18). The parameter-annotation attribute may be SHORTER
  than the descriptor's parameter list, because javac omits parameters it synthesised, and
  the omitted ones are always LEADING — so entries align from the END. We never overrode
  `visitAnnotableParameterCount` and indexed from zero.

  Measured on a new fixture, and the shift is not a constant: **0** for a top-level class,
  **1** for an inner class (the outer instance), **2** for an enum (`$enum$name` and
  `$enum$ordinal`). All three are now pinned, including the shift-0 case — a fix that
  aligned from the end unconditionally would have broken every ordinary constructor, and
  one that hardcoded any single shift would pass one of the three tests.

  **The enum case is the one that mattered and the reason the spec required it.** There the
  hidden first parameter is also a `String`, so `@Labelled("display")` landed on
  `$enum$name` and no downstream type check could tell. Before: `param 0` carried the
  annotation and the real `display` at `param 2` carried none. After: it is on `param 2`.

  Scope stated rather than oversold: this needs a constructor that is BOTH annotated AND on
  an inner class or enum, so the real-world hit rate is low. It was a genuine fabrication
  with a small blast radius, not a widespread one.

### Added

- **`docs/COVERAGE.md` §3a — what we support, and at which versions**, so a user can see
  what they are accepting rather than inferring it from a tick in a matrix. Three things a
  coverage tick never said: the **language versions** the scanner can read at all (Java
  class-file majors 45–71, i.e. through JDK 27; Kotlin ≤ 2.2 for nullability, both bounded
  by the pinned libraries and both degrading to a named gap rather than a failed run); the
  **exact framework and library versions each catalog's rules were measured against**; and
  which catalogs measured **nothing**.

  **Measured points, not ranges** (ruled): every version listed is one whose bytecode was
  read. A version in between is *unverified, not unsupported* — stating a range would be a
  prediction about bytecode nobody opened, which §8.1 forbids and which produced several of
  the defects this plan exists to fix.

  Two findings the table makes unavoidable rather than merely available. **19 of 55 catalogs
  record no version** — including all four gRPC catalogs, both Pub/Sub halves, DGS, Spring
  GraphQL, Spring Integration, Cloud Stream and OpenFeign. That is a statement about our
  RECORD, not about the knowledge: several are bounded by a library Sextant itself ships and
  declares (`grpc-schema` by `grpcio-tools`/`protobuf`, `graphql-schema` by `graphql-core`),
  so the bound is already determinable and merely unwritten. Separating those from the ones
  that genuinely rest on documentation is deferred work, not unknowable work. And **Spring
  Boot 2 / Framework 5 is ruled in scope but measured almost nowhere**: the only pre-Jakarta
  evidence in the estate is Tomcat 9 for `javax-servlet`.

  Generated by `scripts/coverage_versions.py` from the catalogs' own `measured:` blocks and
  gated by `tests/architecture/test_coverage_versions.py`, so it cannot drift. The gate ships
  in the same commit as the generator deliberately: `scripts/coverage_matrix.py` regenerates
  §2 and **nothing runs it**, which is the "opt-in check nobody runs is not a net" lesson
  RUNBOOK already records, one document over.

### Changed

- **One unreadable class no longer takes the whole scan with it** (Critical 1's half that
  lasts). `Main`'s scan loop was wrapped whole in `catch (Exception)` and exited 1, so a
  single class file from a JDK ahead of our ASM destroyed every other class in the module —
  measured on `byte-buddy-1.18.11.jar`: exit 1, zero fact files. It is now a finding about
  ONE class, on the channel findings already ride (FR-17), carrying ASM's own words rather
  than a message of ours predicting them. **The document is still written**: its id, path,
  content hash and class-file major are all knowable without parsing it, and a class that
  vanishes silently is what FR-17 exists to prevent.

  The bump alone would have hidden this. A newer ASM raises the ceiling; it does not make a
  refusal visible.

- **A library no longer loses every readable class because one entry is bad, and the
  "discard the whole subtree" rule is GONE.** It existed because "a fraction of a library is
  indistinguishable, once loaded, from all of a smaller one" — true when a mid-archive
  failure meant the extractor died, leaving an arbitrary prefix. Measured on a three-entry
  jar with one corrupt entry: **exit 1, one document on disk**, nothing recording that two
  more were never attempted.

  The rule was never implemented; it was a side effect of that death. Removing the death
  without closing the hole beside it would have left the prefix silent, so **the archive read
  moved inside the per-entry guard**: a bad CRC or truncated deflate stream now yields a
  labelled `partial` document like any other failure. Same jar, re-measured: **exit 0, three
  of three documents**, the corrupt entry named in `uncovered`.

  With the scan complete, nothing is indistinguishable and the discard has nothing to
  protect — while discarding would MAXIMISE the gap it claimed to prevent, throwing away
  every readable class to hide one labelled one. A consumer resolving a type gets "not
  found" either way; the discard made that true for the whole jar instead of one class.

- **`partial` and `partial_reason` have a producer.** They were the literal strings `false`
  and `null` in every class document, with no code path able to set either — so
  `partial_documents` reached the rendered gaps list and a bundle's `coverage.partial` as a
  number that could only ever be zero. Two producers now, both matching D00's definition
  ("analysed incompletely, with a reason"): a class this build cannot parse, and a Kotlin
  class whose metadata a newer compiler wrote in a form it cannot decode.

- **A document records the class-file version it was read from** — `class_major`, a new
  `class_file_version` capability, `fact_schema_version` 3 → 4. Read from JVMS 4.1's fixed
  offset rather than from ASM's constant set, which runs ahead of the reader beside it: that
  is what makes the value available for a class the reader REFUSED, which is the case it
  exists to describe.

- **The accepted class-file range is a test, against real bytes.** `build.gradle.kts` has
  claimed since the ASM bump that the range "is pinned by a test in this same source tree"
  and **no such test existed** — the same class of unchecked claim about our own code this
  plan keeps finding. `ClassFileVersionTest` now rewrites the two `major_version` bytes of a
  real class file and asks the pinned ASM to read it, asserting both ends and deliberately
  probing past the ceiling so a library bump that moves it fails here instead of passing
  untested. Measured independently: **ASM 9.10.1 accepts majors 45–71 and refuses 72+.**

- **A version is recorded only where the thing can move independently of Sextant** (Step 1
  of Wave 1, ruled by the user). `scanner_version` is REMOVED from a document, and
  `fact_schema_version` goes to `3`. It named a version for facilities that ship inside the
  wheel and therefore have none of their own — `sextant-config-reader` and
  `sextant-detector` each stamped `"0.1.0"`, a hand-maintained copy of `sextant_version`
  that had never once differed from it. On the one facility that does run third-party code
  it read `"9.18"`, which is **capability** 9.18 wearing a library version's name while the
  pinned ASM was **9.10.1** — a value naming no ASM release at all, in the field a consumer
  reads to decide whether to trust a bundle. Tests held nine different fabricated values for
  it (9.7, 9.8, 9.12, 9.14, 9.16, 9.18, 1.0, 0.1.0, "0"), none of them the real one.

- **`metadata.json` records every facility that produced a document, not one.** The field has
  always been a LIST and was always handed a single entry, so on a fixture module two of the
  three producers were absent from provenance — `sextant-config-reader` (10 documents across
  avro, graphql, proto, wsdl, xsd and yaml) and `sextant-detector` (1). Only a facility
  running third-party code carries `libraries`, and those are the coordinates **Gradle
  resolved**, written into the jar manifest at build time so nothing in Java maintains a
  copy. `scanner_id` now names the facility rather than the library (`"asm"` →
  `"sextant-jvm-extractor"`), which is D00 §2's own rule and what made a library version
  look like the right thing to put beside it.

- **The extractor declares its own capabilities, over the subprocess contract it already
  answers scans on** (`--capabilities`, measured at 0.02s, cached per scanner). This
  implements a day-one contract that had never been built: D02 §3 says *"capabilities are
  scanner-declared — earned once, up front, by the scanner that produced a module's facts"*,
  and M03 puts `capabilities()` on the scanner's interface — but the fourteen-name set lived
  in Python, making an unverified claim about a subprocess built by a separate manual step.
  Capabilities gate which catalogs run, so a stale jar did not fail: it ran catalogs against
  fact kinds that jar never emitted, and the module reported an absence nothing could
  distinguish from a real one. A jar that is behind now reports fewer capabilities and the
  catalogs needing them are reported in `skipped_catalogs` — the visible degradation D02 §2
  already defines, so no new refusal was needed.

  **Consequence, recorded rather than discovered later** (M03): a command-line protocol
  assumes we control the scanner's entry point, so adopting a third-party analyzer we did
  not write means writing a WRAPPER that declares what it can read. Accepted deliberately —
  a third-party analyzer does not emit D00 facts either, so something has to stand between
  it and the workspace regardless, and inferring capabilities from a version string instead
  is precisely the mechanism that produced `"9.18"`: a version cannot be interrogated, only
  looked up in a hand-maintained table that is a second copy of the declaration with none
  of its authority.

- **`fact_schema_version` and `graph_schema_version` are single monotonically increasing
  integers, both set to `2`** (Step 0 of the Java/Kotlin v1 completeness plan, ruled by the
  user). Neither is ever parsed, ordered or compared for compatibility — `api._stale_stamps`
  compares each for equality and always has — so a dotted triple carried two numbers that
  meant nothing, in a text type that let copies of one stamp disagree unnoticed. **Every
  workspace written before this change is refused by the stamp gate, naming the stamp, and
  must be re-analysed.** That is the designed behaviour, not a migration: nothing is
  rewritten in place. Measured, so the shape of the refusal is not a surprise: `render`,
  `enrich` and `export` refuse at `api._stale_stamps` naming the stamp and both values, and a
  re-`analyze` over a workspace still holding pre-Step-0 fact files fails in
  `read_fact_file` with `fact_schema_version — Input should be a valid integer ... input_value='1.0.0'`.
  Both are loud and both name the field; neither migrates anything.

  The divergence this settles was live and undetected: `fact_schema_version` was maintained
  by hand in **four** places holding **two** values, and the one producer whose shape had
  actually changed — `ingress/read/*`, which gained `DeclaredShapeFact.operation` — was the
  copy that was never bumped. So every `.proto`, WSDL, Avro and GraphQL document on disk
  carried `operation` while stamping the version that predates it, with the whole suite
  green: nothing compared the copies, and the staleness gate reads `metadata.json` and never
  the documents.

- **The four copies of that stamp are gone, not merely tested.** `extractor-jvm`'s literal is
  deleted — the extractor is HANDED the value as a required `--fact-schema-version` option
  and refuses without it, so Python owns the number and nothing in a repository that cannot
  see a Python constant is asked to track one. The two Python restatements
  (`ingress/read/__init__.py`, `application/stages/analyze.py`) now import from
  `sextant.domain.version`; the layering always permitted it, and only `application`
  importing `ingress` was ever forbidden. `SEXTANT_VERSION` gets the same treatment in both
  directions: `--sextant-version` becomes required rather than defaulted in Java, and the
  Python constant is read from the installed distribution so `pyproject.toml` owns it.

- **Nothing is dropped on export (C10).** `_EXPORTED_TABLES` was eleven hand-written names;
  it is now **every table and view in the schema**, derived from the export queries
  themselves so the two cannot fall out of step. The seven that were silently omitted now
  travel: `raw_facts`, `call_edges` (1,393 rows on `mall-admin`), `return_flows` (444),
  `roots` (79), and the three views `config_entries`, `field_writes` and `method_returns`.
  A consumer can now recompute and check what a rendered trace asserts.

  **The ratchet inverts**: a table in the schema and absent from the export is a test
  failure, so the list cannot fall behind a new `CREATE TABLE`. It lands before anything that
  adds a table — two later items add three — because a safety net installed after the things
  it protects is not one.

  Redaction extends with it, answering the same question per column: `roots.path` joins the
  address map its value was carried from; `return_flows.value` and `method_returns.value`
  join the JSON map, since all four columns of that grammar are built from the same string
  constants; `config_entries.value` is masked by the same `redact_value` keyed on the same
  `key_path` that masks it in the fact stream; and `graph/raw_facts.parquet` joins the very
  map `facts/*.parquet` joins, so the two shapes of one table cannot disagree.

### Added

- **The vocabulary pass's own audit table is closed: none of the four annotations it left
  unmeasured is `@Repeatable`.** `spring-kafka.yml` and `spring-rabbit.yml` each gain a
  **CP-17** `measured:` row beside their CP-16 one — same artifact, same two versions,
  different question — and their handler entries stop saying "not measured at all".
  `@KafkaHandler` and `@RabbitHandler` are `@Target({METHOD, ANNOTATION_TYPE})` with no
  `@Repeatable` at spring-kafka 3.1.4/4.1.1 and spring-rabbit 3.1.4/4.1.1, and no
  `KafkaHandlers`/`RabbitHandlers` exists in any of the four jars. So the two catalogs'
  silence about a container is a **claim about the framework**, and `docs/COVERAGE.md`'s row
  asking for exactly this `javap` question is retired rather than restated.

  Of the four the audit named, three answers say the catalog was already right; the fourth
  (`@PulsarListener`) turned out to have a container the framework reads and the language
  never writes, which is why refusing to encode the predicted answer was worth the round.

- **Both legacy `@SqsListener` spellings are measured, and were already right** —
  `spring-sqs-legacy.yml` gains a `measured:` row per artifact (**CP-17**,
  `org.springframework.cloud:spring-cloud-aws-messaging` 2.2.6.RELEASE and
  `io.awspring.cloud:spring-cloud-aws-messaging` 2.4.4, each version read out of that jar's
  own manifest). Nothing about the catalog changed: both annotations declare exactly
  `value(): String[]` and a `deletionPolicy()` and nothing else, both are `@Target(METHOD)`
  so a class-level use is illegal rather than merely unmodelled, neither is `@Repeatable`,
  neither jar holds a container-shaped sibling, and `QueueMessageHandler` reads those two
  attributes and no third in either generation.

  Recorded as a result rather than passed over, because a pass that only retired entries it
  had to FIX would leave the correct catalogs permanently unmeasured. `_NOT_MEASURED_YET`
  drops to **19**.

- **SQS listeners have a class-level, polymorphic form, and this catalog said they had
  none** (`OI-40`) — Stage 4's per-catalog pass, measured by **CP-17** at
  spring-cloud-aws-sqs 3.1.1 and 4.1.1. `io.awspring.cloud.sqs.annotation.SqsHandler` was
  added at 4.1.1, `@SqsListener`'s `@Target` widened from `{METHOD}` to `{METHOD, TYPE}`, and
  the post-processor grew a branch that builds a `MultiMethodSqsEndpoint` from the
  **class-level** annotation's own `value()` and dispatches to every `@SqsHandler` method —
  read verbatim out of the sources jar, against the *same method* at 3.1.1, which has no such
  branch. `spring-sqs.yml`'s comment was true when it was written and had stopped being true,
  which is the version-scope failure §5.4 exists for; every `@SqsHandler` method in a 4.x
  module was absent from the export. Closed with the `spring-kafka.yml` prefix shape, and
  **no version constraint** — code built against 3.1.1 cannot carry an annotation that
  artifact does not declare.

  Also measured and found CORRECT: the `value`/`queueNames` `@AliasFor` pair at a second
  version, confirmed *by omission* — the post-processor reads `value()` alone at both, because
  the merge happens inside `findMergedAnnotation`. And `@SqsListener` names no container in
  any of its three spellings, which CP-17 measured rather than assumed. One new guard,
  mutation-proved: `spring-sqs.class-level-listener-is-the-prefix`.

- **Spring for Apache Pulsar's second inbound annotation, and its container** — Stage 4's
  per-catalog pass, measured by **CP-17**
  (`scripts/probes/cp17_containers_and_class_level.md`, spring-pulsar 1.2.11 and 2.0.7,
  both versions read out of each jar's own manifest).

  - **`@PulsarReader` is derived at all** (`OI-39`). It ships in the artifact
    `spring-pulsar.yml` already depends on, declares `topics(): java.lang.String[]`, and has
    its own post-processor, endpoint type and registrar — and the catalog named it **nowhere**,
    so every reader in a scanned module was absent from the export. A whole shape missing, not
    an attribute of one.
  - **A second `@PulsarListener` written into `@PulsarListeners` is derived** (`OI-38`) —
    `OI-36`'s silent drop one framework over, and by a **different mechanism**:
    `@PulsarListener` is *not* `@Repeatable`, so the container is one an author writes by hand
    and the framework registers the **union** of it and any direct use (read verbatim out of
    the sources jar at the same coordinate). The `container:` key the vocabulary pass shipped
    says that exactly — a class file does not record whose container it is — and only the
    documentation was narrower than the key. D02 §2 and two engine docstrings now say so; the
    key, the engine and every other catalog are unchanged. Needs extractor capability 9.16,
    which the catalog now `requires`.

  Also measured and found CORRECT, which is what makes the audit re-runnable rather than
  repeated: `@PulsarListener`'s `topics`/`topicPattern` split at a second version, and the
  claim that the framework ships **no** class-level handler annotation —
  `org.springframework.pulsar.annotation.PulsarHandler` is absent from both jars, so
  `prefix_from: []` is the framework's own rule rather than a simplification.

  Two new guards, both mutation-proved: `spring-pulsar.container-is-the-frameworks-own` and
  `spring-pulsar.reader-is-a-second-inbound-surface`. `spring-pulsar` leaves
  `_NOT_MEASURED_YET`, which drops to **20** (`OI-10`).

- **`annotation_driven` gains three words, designed as one pass** (D02 §2). The style
  **21 catalogs** share grew a key at a time against whichever framework was in front of its
  author, and Stage 4 found three catalogs at once whose framework rule was known exactly and
  whose grammar had no word for it — which is GUIDELINES §13.8's third occurrence. Each word
  names the measurement that forces it, each is optional, and each is inert while absent, so
  every catalog that declares none derives byte-identically.

  - **`mapping.annotations[].container`** — the repeatable container javac folds two uses of
    that annotation into. **CP-16**, six versions across three frameworks: the three listener
    annotations are each `@Repeatable` and each post-processor reads the container, while
    javac writes the container and *not* the member (JLS 9.7.5) — so a method carrying two
    listeners derived **nothing at all** (`OI-36`). The engine unfolds each container use into
    ordinary annotation rows before composition and inheritance, so there is no container in
    the query at all. Needs extractor capability 9.16.
  - **`mapping.path_from_siblings`** — ordered `{annotation, arg}` name sources that live on
    *other* annotations of the same declaration, consulted only where every `path_from` alias
    is absent. **CP-15 rows 1-2**: `getOperationName` consults five sources in order and takes
    the first with a value; the catalog read the first alone (`OI-35`).
  - **`mapping.annotations[].path_fallback`, and two new fallback words** —
    `read_accessor_property` (strips `get`, `is`) and `write_accessor_property` (strips
    `set`). **CP-15 rows 3-5**, row 5 *compiled and run*: the un-named-operation fallback is
    direction-dependent and the direction is chosen by which annotation matched, so one
    catalog-level word made one of two annotations newly wrong (`OI-5`).

  Five new guards, all measured to kill: `annotation_driven.folded-uses-are-read`,
  `annotation_driven.folded-entry-is-the-declared-annotation`,
  `derive_endpoints.sibling-name-source-order`,
  `derive_endpoints.path-fallback-is-per-annotation` and
  `derive_endpoints.accessor-strip-is-the-measured-one`.

- **`## Traces` draws every trace, and `render` has no display flag at all** (GUIDELINES
  §8.4, ruled 2026-09-06). `mall-admin` — one module, 157 classes — walks **160 traces**,
  and the document draws all of them: a **711 KB** `architecture.md` and a **4.6 MB**
  `architecture.html` with **161 diagrams**. That was briefly bounded to 37 traces by
  default, on the grounds that 711 KB is a document nobody opens, and the ruling reversed
  it: *"we should be focused on telling the truth, not the amount of information ... which
  is why we have indices planned for sextant, such that agents can leverage the truth +
  indices to quickly find things"*. **Completeness is the deliverable; a document too large
  to read linearly is a navigation problem**, solved by indices and by the agents that read
  it, never by leaving 123 walked traces undrawn.

  The bound survived one day longer as `sextant module render --brief` and was then
  **deleted outright** — *"deleting that --brief if it only cuts the first N. that's same
  as lying"*. What it drew was whole traces while a 500-step budget lasted, taken in the
  summary table's own order: an arbitrary **prefix**, presented as a reduced document.
  Saying in-band that it was reduced made the omission honest and never made the prefix a
  summary, and which traces a reader can spare is a judgement no renderer can compute — so
  a trimmed document is enrichment work (an LLM overlay), not a render flag: *"that's a
  different story and a different ask"*. Nothing in `## Traces` takes a bound now; every
  trace keeps its summary row, is drawn whole, and the section states the two counts —
  drawn and walked — that would differ if that ever stopped being true.

  Closes `OI-30`. Records `OI-31` (the 3.5 MB of inlined mermaid and the 161 eagerly
  rendered diagrams — a payload question, whose close is lazy per-diagram rendering and is
  **never** drawing fewer diagrams) and `OI-32` (`spring-petclinic-rest`'s pinned routes
  have been stale since 2O's identity migration, so that field pin has been failing
  unnoticed for a phase).

- **`macrozheng/mall` is a pinned, reproducible example** (`scripts/field-expectations/mall-admin.json`).
  It is the corpus every claim about document size in this repository is measured on, and
  it existed only in one session's scratch directory — so nobody else could re-measure any
  of them, which GUIDELINES §8.4 rule 4 forbids. It is carried exactly as every other
  example is (`examples/` is gitignored; the pin holds the `remote`, the `commit`, and the
  counts and routes recorded against it), with three new optional keys `field_check.py`
  needed to reach it: **`module`** (`mall-admin`, whose own `target/classes` decides
  whether a build is needed — the reactor root has none), **`maven`** (`mall` ships no
  `mvnw`), and **`jdk`** (`21` — a newer JDK breaks Lombok's annotation processor, and the
  pin is refused against Maven's own `-v` banner before anything is built rather than
  failing several screens into a stack trace). `README.md` carries the four commands.


- **A trace can be found by the URL a reader knows** (2Q close, defect 1). `## Traces`
  named every trace by its handler descriptor and its kind, so `GET /order/list` appeared
  nowhere in `mall-admin`'s section: finding the trace for an endpoint required already
  knowing the descriptor. **`roots` now carries the wire address** — `protocol`, `method`
  and `path`, one ROW per address and still one ROOT per (handler, kind), collapsed by
  `roots_of` so a handler serving three paths is one walk listing three ways in. The
  summary table gains a `Reached by` column and every block header names its addresses;
  both are composed by the same `_wire_address` the inbound endpoint table uses, so one
  address is never spelled two ways, and a `path` still passes the render exit's redactor.
  **A root nothing addresses says `no wire address`** rather than the em dash that means
  "nothing recorded" everywhere else: a scheduled job is started by a clock, and inventing
  a label for it would be fabrication. `OI-23` — an exposed address whose handler no chain
  reader named, and which therefore has no root at all — is unchanged and stays open.
  The join is made in `resolve/`, never in `egress`: a renderer that joins is deriving.
  `GRAPH_SCHEMA_VERSION` moves to **1.2.0**, because a 1.1.0 workspace's `roots` has no
  address columns at all and the read gate must refuse it rather than fail reading it.

- **A trace, in front of a reader** (2Q, closing `OI-25`). Everything before this produced
  tables; `sextant module render` now writes a **`## Traces`** section into
  `architecture.md` and `architecture.html` alike — one rendered trace and one Mermaid
  `sequenceDiagram` **per ROOT**, so a scheduled job gets both for the same reason an
  endpoint handler does.
  **Every step is a row and an arrow. Nothing is filtered.** The step table carries `Depth`,
  `Caller`, `Call`, `Dispatch`, `Resolution`, `Value`, `Returns` and `Stop`, and the walk's
  2,147 steps on `mall-admin` are 2,147 rows: a hidden call and an absent call are the same
  bytes to a reader, and this is the first document anyone reads a trace in.
  **The four places a reader could be misled are stated where they render.** A trace is
  reachability and never execution — said in the section preamble and again under every
  diagram; `revisited` keeps its row and says the subtree is at the callee's first
  appearance; nothing classifies a terminal, because `terminal_kind` has no producer and
  inventing one in `egress` would be derivation hiding in presentation; and a sibling
  build module reads `boundary` exactly as the JDK does, which the preamble says in
  capitals because `/order/list`'s own response composition is where it bites.
  **`MachineDiagram` gains `elides`**, mirroring `DiagramClaim.elides` field for field —
  markdown writes an `Elides:` line, HTML passes it to the diagram caption — and every
  trace diagram carries one, counted from that trace's own stops. `## Structure`'s class
  diagram passes `None` and is byte-identical to before.
  **An arrow ends at the body the walk expanded**, not at the interface the compiler named,
  with `(declared X)` on the message: drawing the interface leaves the implementation
  sending messages nobody sent it, which is a diagram a reader cannot follow. Two types
  whose simple names collide fall back to full descriptors, `_disambiguated_shape_names`'
  rule per diagram, because two lifelines labelled `Order` assert a call between things
  that never touched.
  **Verified against the vendored mermaid 11.17.2 build in a live browser**: all 161
  diagrams in `mall-admin`'s document render, 0 syntax errors, 160 captions. Two renders
  of one workspace are byte-identical (NFR-1).
  Two gaps retire BY NAME — `sequence_diagrams_pending_call_graph` and
  `call_graph_not_implemented` — and **five narrower ones** take their place, because what
  is still true of a trace is five separate things a reader can act on. Records `OI-27`
  (FR-6 says a trace is unbounded and stops only at a terminal; three things stop it
  earlier).

- **A stale workspace is refused instead of rendered short** (2Q, closing `OI-24`).
  [D01](docs/components/D01-graph-schema.md) §7 has said since Phase 1 that *"any Sextant
  version change re-derives, because derivation logic may have changed and there is no cheap
  way to know"* — and nothing compared a stamp. `api._stale_stamps` now does, inside the read
  gate `render`, `enrich` and `export` already share: `schema_version`,
  `provenance.sextant_version` and `provenance.fact_schema_version` are checked against the
  running build, an absent stamp counts as a mismatch, and a disagreement is a refusal naming
  the stamp that moved rather than a silent re-analysis.
  **It closes here because this is the change that made it live.** A workspace derived before
  `roots` and `call_edges` existed answers both queries with no rows, and an empty table is
  byte-identical to a module that has none — so `## Traces` would have rendered `None found.`
  for a service with 160 endpoints. `GRAPH_SCHEMA_VERSION` moves to **1.1.0** for the same
  reason: the two new derived tables are purely additive, and additive is exactly the shape a
  stamp has to catch, because nothing in the output looks wrong.

- **A trace, from a root to every terminal** (2Q, `G4` + `I3`). The thing this project has
  been asked for since day one, and the missing half of what `CONTEXT.md` promises. New
  derived table **`call_edges`** ([D01](docs/components/D01-graph-schema.md) §3) — one row
  per (call site, candidate callee), carrying `caller`, `ordinal`, `invoke_kind`, the bare
  `target` the compiler wrote, the module-prefixed `callee` whose body it reaches, `result`,
  `resolution` and `evidence` — and **`application/query/trace.py`**, a bounded,
  cycle-refusing walk over it.
  **It takes a ROOT, not an endpoint** (`I3`, the user's ruling: *a scheduled job still
  contains business logic, so there should still be sequence diagrams*). The walk reads
  `Root.kind` for exactly one purpose — carrying it back on the answer — and branches on it
  nowhere, so the third root kind costs nothing on the day it gains a producer.
  **`callee IS NULL` is the third-party boundary and the row is still written**: "this call
  leaves the module here" and "this method makes no calls" are different answers, and a
  table recording neither would report them identically.
  **A lambda body is reached, not stopped at.** An `invokedynamic` edge names the body the
  site CREATES (capability 9.17's `implementation`), never the bootstrap factory — closing
  `OI-14`, whose condition was a terminal reachable only through a lambda. Seven of
  `mall-admin`'s 160 traces have one.
  **Each step says why it was not expanded**, from a new closed set `TraceStop` —
  `boundary`, `cycle`, `revisited`, `depth_limit`. It is deliberately NOT D00 §4's
  `terminal_kind`, which classifies what a call REACHES and still has no producer, because
  three of its members need framework knowledge nothing has applied at a call site.
  **The depth bound is never silent**: `Trace.truncated` answers whether a walk is whole.
  **Measured on `macrozheng/mall`'s `mall-admin`**: 2,608 edges over 2,664 call sites (the
  56 without one are `invokedynamic` string concatenation, whose bootstrap is a compiler
  artifact); 1,966 boundary rows; 160 roots, all producing a trace, deepest 5 against a
  bound of 64. `GET /order/list` derives exactly the source: `OmsOrderService#list` →
  `OmsOrderServiceImpl#list` (sole implementation) → `PageHelper.startPage` and
  `OmsOrderDao#getList`, with `CommonPage#restPage` and `CommonResult#success` as the
  sibling-module terminals that compose the response. 155 roots reach a mapper or DAO
  terminal and three more an object-store client, which is the roadmap's 158 reproduced
  when the classification it used is applied by hand; the two that reach neither are
  `/admin/refreshToken` and `/aliyun/oss/callback`, as recorded.
  Closes `OI-14` and `OI-20`. Records `OI-24` (D01 §7's re-derivation rule is documentation,
  not code — G3's concern 3, verified), `OI-25` (nothing outside tests reads the walk) and
  `OI-26` (`SEXTANT_VERSION` is declared three times).

- **A scheduled job is a root, not a table nobody walks** (2Q, `I1`).
  [D00](docs/components/D00-fact-schema.md) §4 has documented a `root_kind` set for as long
  as the fact schema has existed and **nothing produced one** — entry #7 of
  [documented-not-implemented.md](docs/documented-not-implemented.md), and the reason
  `resolve/engines/scheduled_work.py` carried a docstring saying its own rows fed no root
  set. New derived table **`roots`** ([D01](docs/components/D01-graph-schema.md) §3): one
  row per (`handler`, `root_kind`), written from every `endpoints` row the module exposes
  and names a handler for, and from every `scheduled_work` handler.
  **A root is a place a walk starts, not an address.** A method serving three paths is ONE
  root — the walk is the same whichever path invoked it — so the fixture's 77
  handler-bearing endpoint rows collapse to 66 roots. A method that is both exposed and
  scheduled is two rows, because those are two different answers to "what starts this".
  **The member list is corrected as part of shipping it.** `http_inbound`, `soap_inbound`,
  `grpc_inbound` and `message_inbound` collapse to one `inbound_endpoint`: protocol is a
  property of an endpoint (`CONTEXT.md`), an inbound row already carries it, and
  `message_inbound` named a `message` protocol family this schema had already retired.
  `cli_entry` becomes `entry_point`, which is what `CONTEXT.md` calls it and claims no
  command-line surface nobody measured.
  **`entry_point` has no producer, deliberately.** Which signature starts a program is a
  LANGUAGE rule and ARCHITECTURE §10 keeps those out of the resolver, so it needs a
  catalog and none declares one. Recorded as `OI-22` and in
  [COVERAGE](docs/COVERAGE.md) §7 rather than left for a reader to discover. Closes
  register entry #7.

- **A value chain now crosses a method boundary** (2Q, `G3`). Within a method the chain was
  already complete — a `call_site` carries the value id its call produced, and every
  argument carries the `source` id of the call that produced it — so
  `OmsOrderService#list` → `CommonPage#restPage` → `CommonResult#success` was three facts.
  What nothing said is where the FIRST of those values came from. New derived table
  **`return_flows`** ([D01](docs/components/D01-graph-schema.md) §3): one row per (call
  site, candidate callee, callee return), carrying the caller's `result` id, the callee, its
  `return_ordinal`, what it hands back in D00 §5's argument grammar, and the site's
  `resolution`/`evidence`. It is the only thing licensed to cross a method boundary, and it
  does so by naming both sides — a `source` inside `value` is a value id in the CALLEE.
  **Caller to callee is arithmetic, not a lookup.** `domain/symbols.method_descriptor`
  composes the callee's descriptor from the call target's triple with the same first-four-
  bytes-of-SHA-256 disambiguator the extractor writes, so a callee outside the workspace
  matches nothing instead of raising.
  **The JVM's dispatch rule is mirrored, not approximated** (DR-6). `invokestatic` and
  `invokespecial` name the method that runs; `invokevirtual` and `invokeinterface` take the
  declared body plus every in-module override — one candidate is `resolved`, several are
  `narrowed` with all of them listed and none picked. `invokedynamic` contributes nothing:
  its `result` is the lambda INSTANCE, never anything the body returns.
  **Measured on `macrozheng/mall`'s `mall-admin`** (160 endpoints, Boot 3.x, JDK 21): 566
  rows over 552 call sites, of which 386 are direct and 166 resolve through a sole
  implementation. `OmsOrderController#list`'s value 7 is now stated to be what
  `OmsOrderServiceImpl#list` hands back, which is the result of `OmsOrderDao#getList` — the
  MyBatis terminal, checked against source. 1,411 of 2,065 value-producing call sites
  contribute no row, which is the ruled third-party boundary and the common case.
  Closes `OI-15`; `OI-14` is amended and stays open. `OI-16`, `OI-17` and `OI-18` recorded.
  **No consumer yet** — the reader is 2Q's `G4`.

- **What a method hands back is a fact — extractor capability 9.18** (2Q, `G2`). `ARETURN`
  appeared in the extractor only inside a comment, so the last link of a round trip was
  missing: an argument already carries the `source` id of the call that produced it, and
  nothing said which of a method's call results the METHOD returns. New fact kind
  **`method_return`** ([D00](docs/components/D00-fact-schema.md) §5), one per return
  instruction, carrying `method`, `ordinal` and `value`.
  **`value` is an entry of the argument grammar, not a bare id**, and that is what keeps two
  real answers apart: `null` means a `void` return pops nothing, `{"kind": "unresolved"}`
  means it pops something the pass could not name, and `{"kind": "unresolved", "source": N}`
  is the join. A returned literal, field, parameter or lambda reads exactly as it would in
  an argument slot in the same position, against the method's own declared return type.
  **Every return form, and nothing collapsed.** All six return opcodes; a method with two
  `return` statements yields two facts, told apart by `ordinal`, because a branch gives two
  possible answers and no single one. `ATHROW` is deliberately not one of them.
  807 facts on the orders-service fixture, 176 of them void returns and 62 methods carrying
  more than one. `scanner_version` moves `9.17` → `9.18`.
  **No consumer yet** — the reader is 2Q's `G3`, recorded as `OI-15`.

- **A lambda's body is named by the site that creates it — extractor capability 9.17**
  (2Q, `G1`). An `invokedynamic` call site recorded the BOOTSTRAP method and discarded the
  implementation, so the synthetic method javac lifts a lambda body into was extracted with
  its own symbol and its own call sites and referenced by nothing. `call_site` gains an
  optional **`implementation`** ([D00](docs/components/D00-fact-schema.md) §5): the symbol
  of the method the dispatch will run, read from the bootstrap's second argument. Seventeen
  bodies on the orders-service fixture, four of them Spring Cloud Stream `@Bean` methods
  that RETURN their lambda — the shape the existing `lambda` argument kind cannot see at
  all, because the lambda fills no argument slot.
  **Written only where the bootstrap names a method.** A `StringConcatFactory` site's
  bootstrap arguments are a format recipe, so the key is absent there and on every ordinary
  invoke, whose `target` already is the answer. Strictly additive: an engine that does not
  read it sees exactly what it saw before, and `scanner_version` moves `9.16` → `9.17` so a
  stale jar's silence is distinguishable from a module with no lambdas.
  **No consumer yet** — the reader is 2Q's `G3`/`G4`, and the honest state is recorded as
  `OI-14` rather than claimed here.

- **`@HttpExchange` faces both ways: `resolves.direction`, the direction flip** (2O design §6,
  Task 10). An `@HttpExchange` interface a local CONTROLLER implements now derives the INBOUND
  routes Spring actually serves, at the composed address, handled by the implementing class's
  own method — where before the module was published as CALLING a service it serves, and, after
  `A-C1`'s SEI fence turned that fabrication into silence, as neither. [D02](docs/components/D02-catalog-schema.md)
  §2c's `resolves.direction` is the mechanism, shipped on `spring-http-interface.yml` and read
  by no other catalog; the register entry that recorded it as documented-and-unbuilt closes with
  it.
  **The CONDITION is not the one D02 sketched, and that is the point.**
  `owner_implemented_in_module: true` is weaker than Spring's own rule and fabricates: measured
  on spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9 (`scripts/probes/cp7_http_exchange.md`),
  `isHandler` is one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call with
  no `@RequestMapping` disjunct, so a `@Service` implementing an exchange interface is
  dispatched to by nothing and an inbound row for one would invent an endpoint. The shipped
  condition names the controller annotations as catalog data — the same fqns `spring-mvc.yml`
  and `spring-web.yml` already declare — and resolves them through the composition pre-pass, so
  a module-local stereotype composed from `@Controller` counts. The type-HIERARCHY half of that
  predicate is deliberately not mirrored and aligns with COVERAGE's existing
  inherited-stereotype boundary.
  **Behaviour change for real modules:** on a module that both declares an `@HttpExchange`
  interface and implements it with a controller, rows that were absent become inbound endpoints;
  nothing moves in the other direction, and an interface with no local controller implementation
  keeps deriving exactly the outbound row it always did. Where the controller ALSO writes its
  own mapping for the same route, the two rows share a wire identity and the existing dedup
  folds them into one, with the implementing class's method surviving as handler — no collision
  detector is involved, because there is none.

- **Spring Integration's channels, enumerated and handed off** (2O design §5, Task 9).
  `config_join` gains a second binding-name source, **`binding.from: annotation_value`** — the
  name is the value of a declared argument on a declared annotation instead of a bean's own
  method name — and the destination side is unchanged, still `resolved_config` alone. The
  measured basis is `scripts/probes/spring-integration-destinations.md`: the channel join is
  real in both shapes, with the SAME literal on the annotation side and the call-site side.
  The new built-in `spring-integration.yml` declares **no `key`**, because Spring Integration
  defines no standard configuration key for a channel's destination and any template would be a
  project convention. It therefore derives **no endpoint row and no ghost row** and files one
  **`channel_destination` open question** per channel, carrying the channel name and the handler
  symbol — the enrichment seat's inbox, which is how "we cannot see it" becomes a route to an
  answer rather than a dead end. Never a fabricated wire, never `peer: in-process`. Three rules
  separate this source from the bean one and each is stated in [D02](docs/components/D02-catalog-schema.md):
  the annotation's target must be a METHOD, the value must be a non-empty string taken verbatim,
  and an unanswered name derives nothing at all. The questions ride the existing `gaps` seam
  (`resolve/service_identity.py`), which is the only place a pass may write to a ledger the
  pipeline resets after the engine loop.

- **The two NON-WIRE families: `scheduled_work` and `error_handlers`** (2O design §4). Work a
  framework starts on a clock, and the exceptions a module answers, each in a table of its own
  with the full derive → render → export chain: two engine styles (`scheduled_work`,
  `error_advice`), two catalogs (`spring-scheduling.yml`, `spring-advice.yml`), two D01 tables,
  two bundle artifacts and two document sections. **Neither reaches `endpoints`, and that is the
  design** — the endpoint table is wire-true, a scheduled method speaks no protocol and has no
  address, and an error handler is not a boundary anyone can address but what happens inside one
  that already exists. Giving either a wire identity would invent a route nothing serves.
  Schedule expressions are carried verbatim, with a property placeholder reported `unresolved`
  rather than substituted; an error handler's exception comes from the annotation's value, else
  from a parameter this workspace can PROVE is a throwable. Both tables are reset once per
  resolve from the pipeline, never by the engine, so a second catalog describing the same family
  cannot erase the first's rows.

- **`protocol` and `direction` may be ABSENT from a catalog, and only from a non-wire one**
  ([D02](docs/components/D02-catalog-schema.md) §1). Absence is a claim — "this catalog derives
  nothing addressable" — checked in `resolve/endpoints.py`, which refuses a wire style declaring
  neither and a non-wire style declaring either. A value outside D00's closed sets is still
  refused at the loader: a typo is not an absence. Writing one of the twelve protocols on a
  scheduling catalog to satisfy a required field would have put a wire claim in a shipped file
  that nothing reads and every reader believes.

- **CP-12: the framework surfaces the round-1b fix pass mirrors are measured**
  (`scripts/probes/cp12_sweep_round1b.md`). Eight Class A Majors share one shape — the catalog
  encodes a SUBSET of the framework's surface and no COVERAGE row names the rest — and CP-10's
  green table could not have caught any of them, because it asks whether every descriptor a
  catalog declares names a real method and never whether the framework declares one the catalog
  does not (`A-Mi5`). CP-12 asks that second question twelve times, and every answer is the
  framework's WHOLE set: `WebClient`/`RestClient`'s request starters and response-obtaining
  methods, Retrofit's method-targeted annotations with what each declares, every
  `KafkaProducer.send`, `KafkaConsumer.subscribe`/`assign` and `KafkaTemplate.send` overload,
  every `jakarta.jms.Session` receiver factory, `@SqsListener`'s attributes and its `@AliasFor`
  pair, and both WebFlux router DSLs' per-verb factories. Two Spring minors rather than one,
  because `A-M4` is a version finding in both directions at once. `tests/architecture/
  test_sweep_round1b_framework_surfaces.py` is the offline half.

- **CP-11: the four framework rules the principles-sweep fix pass mirrors are measured**
  (`scripts/probes/cp11_sweep_round1.md`). Each of `A-C2`, `A-C7`, `A-C1` and `A-C6` encoded a
  framework rule taken from documentation, a checkpoint note or memory, and each was plausible
  and wrong. The committed harness resolves each artifact through Maven, reads every jar's
  self-reported version out of the archive it opened — aborting rather than filling a
  mislabelled column — and asks `javap` four questions: OkHttp's complete `Request.Builder`
  verb-setter set, `RequestMappingHandlerMapping.isHandler`'s body across four Spring minors,
  which jakarta.websocket artifact declares which annotation and what each targets, and what
  `Retrofit.create` does with a non-interface. `tests/architecture/
  test_sweep_round1_framework_rules.py` is the offline half and pins the shipped catalogs
  against the generated table.

- **CP-10: every catalog `descriptor:` is now pinned to bytecode somebody read**
  (`scripts/probes/cp10_catalog_descriptors.md`, descriptor sweep R7). Load-time validation
  refuses a `descriptor` that is not a string opening with `(`, and that is all it can do: a
  wrong return type, a misspelled package or a stale erasure is well-formed and WRONG — it
  claims its candidate set in `_matching_method` and every overload of that name then derives
  nothing, with no error, no COVERAGE row, and every absence-asserting test still passing.
  The committed harness resolves each artifact through Maven, reads every `descriptor:` out
  of the shipped catalogs, indexes class → jar off the archives it opened, and asks
  `javap -p -s` whether the owner — or a superclass on the same classpath, which is what
  `SqsTemplate`'s inherited `send` needs — declares that exact erased descriptor. Each
  column is the version the JAR reported about itself, and a jar disagreeing with the
  coordinate that resolved it ABORTS the run (§5.4). `tests/architecture/test_catalog_descriptors.py`
  is the offline half: it pins the shipped catalogs against the generated table in both
  directions and fails on any verdict other than `declared`, so a descriptor added without
  re-running the harness fails the suite rather than going quiet.
- **Servlets: the oldest HTTP surface on the platform derives, under both package
  spellings** (2O design §3b, Task 7b). A new `supertype_dispatch` engine style
  (`jakarta-servlet.yml` and `javax-servlet.yml`) reads three pieces of evidence jointly —
  a TYPE-level `@WebServlet` for the address, `HttpServlet` for the dispatch contract, and
  the `doXxx` methods the class overrides for the verbs — none of which any shipped style
  could join: an annotation-driven derivation joins METHOD symbols and mints no row for a
  type-level annotation, and `supertype_derived`'s match requires a supertype whose own
  facts are in the module, which a container's abstract base never is. Every `urlPatterns`
  entry is its own endpoint; `value` is its alias, and a declaration writing BOTH derives
  nothing, because that is a deployment the container refuses and either value would then
  be a fabricated address. The member selector matches a name AND its parameter types in
  order, because that is how the language identifies a method (GUIDELINES §8.1):
  `doGet(String, HttpServletResponse)` overrides nothing and derives nothing, where a
  name-keyed selector would have published an address the container answers 405 to.
- **CP-9, measured live on three container majors** (`scripts/probes/cp9_servlet_shapes.md`,
  Apache Tomcat 10.1.50, 11.0.24 and 9.0.121, each column identified by the container the
  process itself reported). Its harness is committed beside it, deploys a real webapp so the
  CONTAINER's own annotation scan is what registers each servlet, and runs the committed
  extractor over the same build to record what actually reaches the fact stream. The
  questions the design left open are answered by measurement: **HEAD, OPTIONS and TRACE ARE
  served implicitly from `doGet`** and are deliberately NOT derived (the code serving them
  is in a container jar nothing scans, so the row would carry either no handler or a
  handler that does not serve that verb — the same ruling Task 6 made for Data REST); **an
  explicitly overridden `doTrace` IS dispatched to**, 200 over a connector that permits the
  method, so it is in the verb map with `allowTrace` recorded as a stated dependency rather
  than treated as proof the address is unserved; **the `javax.servlet` spelling behaves
  identically**, all 33 rows, which is why a second catalog ships instead of a stated
  boundary; and **a `protected` handler's recorded visibility is `other`, not
  `protected`**, so the style reads no visibility at all — an override may never narrow
  visibility, which makes the check both impossible and unnecessary.
- A class overriding `service()` derives **nothing**, and so does a `GenericServlet`
  subclass: the first replaces the verb dispatch itself and serves every verb alike
  (measured), so the verb map would publish a wrong verb set rather than a partial one;
  the second declares no HTTP verb semantics at all.
- **The one shape these catalogs over-report is stated and measured**: a module whose
  `WEB-INF/web.xml` declares `metadata-complete="true"` serves none of its annotated
  servlets — 404 on all three containers, same classes, one descriptor — and nothing in the
  pipeline reads a deployment descriptor, so every row is derived anyway. A COVERAGE
  boundary row in the over-report direction, closed by a descriptor reader.

- **The API nobody wrote a controller for: Spring Data REST routes derive** (2O design §2,
  Task 6). A new `derived_resource` engine style (`spring-data-rest.yml`) derives the CRUD
  route table from a repository INTERFACE — six routes per exposed repository plus one
  `/search/{query}` per query method — in a module that contains no controller, no mapping
  annotation and no string that is a URL. Every rule was verified against a live Boot 4.0.1
  / spring-data-rest 5.0.1 application (`scripts/probes/cp2_data_rest.md`): which item
  routes exist follows which CRUD contract is extended (a `PagingAndSortingRepository`-only
  repository serves a collection GET and nothing else), `path=` overrides the derived path,
  `exported = false` removes the repository, `@RestResource` renames or removes a search
  route, and which repositories are exposed at all follows
  `spring.data.rest.detection-strategy` — whose default exposes PUBLIC repositories only.
- **The dependency gate is real** (ruling R9). `detect.coordinates` was declared by every
  shipped catalog and read by nothing; it is now on the `Catalog` model and gates the one
  style whose framework rule is conditional on the library being present. The coordinates a
  module's build declares reach the workspace as D00 §5's `module` fact —
  constructed for the first time, from both detectors (Gradle's resolved compile classpath,
  Maven's direct POM declarations). A gated catalog whose question cannot be answered is
  reported SKIPPED with its reason, never derived and never silently omitted.
- **`domain/pluralize.py`** — a port of Evo Inflector's rule set, pinned by a differential
  run against the real library over every word in `/usr/share/dict/words`.
  `spring-data-rest-core` depends on that library non-optionally, so a working Data REST
  application always pluralizes its collection paths. A ported rule set is a derivative
  work, so Apache-2.0 §4's attribution travels with it:
  `src/sextant/domain/LICENSE-evo-inflector` carries the origin and the licence in full,
  named by the module docstring and by README's Dependencies section.
- **D02's `default_produces` is implemented** after being specified-not-used since 2E: read
  as a top-level catalog key, filling `produces` for rows no mapping declares a media type
  for. `application/hal+json → json` joins the shared `media_formats` table.
- A `static` helper declared on a Spring Data repository derives **no** `/search/` route:
  it is bound to the type, never to the repository's instance contract, so the framework
  serves nothing for it. The `method_visibility` query now projects the `static` modifier
  the extractor already emitted. A `default` method is still over-reported — `ACC_ABSTRACT`
  is not recorded, so nothing in the facts tells one from an abstract method — and that is
  now a stated boundary in COVERAGE rather than an undeclared one.
- The `environment_divergence` pass re-applies the CAPABILITY gate as well as the
  dependency gate, so a catalog `derive_endpoints` skipped for a missing capability can no
  longer file a question about a route it derived nothing for.
- A gated catalog's SKIPPED reason now carries Maven's direct-declarations-only caveat in
  the message itself, so "this module's build declares none of them" cannot be read as a
  confident negative for a starter inherited through a parent or a BOM. A module fact
  carrying no `dependency_coordinates` key at all degrades to that same SKIPPED path
  instead of aborting the resolve.
- **A new open-question kind is written**: `environment_divergence`, filed when
  `spring.data.rest.base-path` differs between environments — the derived rows then carry
  the configuration expression as their prefix at `unresolved`, rather than one
  environment's URL.
- **gRPC's JVM bytecode surface derives** (2O design §1b/§1c, Task 5), closing FR-3's
  last open protocol on the JVM alongside Task 4's schema half. Two new, framework-neutral
  engine styles: `supertype_derived` matches any class extending a generated
  `<Service>ImplBase` (`grpc-java.yml`) and derives one inbound row per overridden RPC
  method, reading the service identity and each wire method name off the generated
  class's own identity-building call-site arguments (`ServiceDescriptor.newBuilder`,
  `MethodDescriptor.generateFullMethodName`) rather than a field value — D00 §5's
  `constant` fact kind has no producer in this codebase (ruling R11). `injected_client`
  matches a net.devh `@GrpcClient`-injected stub field (`grpc-net-devh.yml`) and derives
  one outbound, service-level row (`method` NULL), fenced by symbol name against a service
  this module implements locally. Both merge with Task 4's descriptor-derived rows on the
  identical wire identity where both exist — and the merged row keeps BOTH halves: the
  bytecode's handler symbol plus the descriptor's request contract, response contract and
  streaming word, carried across by `stamp_declared_response.sql` and its new sibling
  `stamp_declared_request.sql` rather than by an insert the identity guard rejects. An
  unreadable identity derives an honest `unresolved` row plus a `service_identity` open
  question, never a fabricated package — and `supertype_derived` matches ONLY where the
  supertype's own generated class makes one of the marker calls, so ordinary class
  inheritance derives no row and files no question at all. Where two wire method names
  collapse onto one candidate override neither is attributed, and an override no wire
  name reaches is filed as a question rather than dropped silently.
- **`@GrpcService` corroboration** (`grpc-spring.yml`, Spring gRPC and net.devh
  spellings): a new `corroborates` block on `annotation_driven`, plus a `gaps` entry
  point beside `supertype_derived`'s and `injected_client`'s. It derives NO endpoint rows
  — the annotation names no service — and files a `service_identity` question for any
  class it flags that no gRPC endpoint names as a handler, which is the published-stubs
  case that previously produced nothing at all.
- **Five messaging and annotation catalogs** (2O Task 7): `spring-rabbit.yml`
  (`@RabbitListener`, plus the class-level `@RabbitListener` + `@RabbitHandler` shape),
  `spring-pulsar.yml` (`@PulsarListener`), `spring-rabbit-template.yml`
  (`RabbitTemplate.convertAndSend`), `spring-sqs-legacy.yml` (both older `@SqsListener`
  packages, so all three generations of the annotation now ship) and `spring-actuator.yml`
  (`@Endpoint` + `@ReadOperation`/`@WriteOperation`/`@DeleteOperation`). Every annotation's
  attribute shape was read off the real class files with `javap`, and the Actuator address
  and verb rules were confirmed live against Boot 3.5.10 AND 4.1.1
  (`scripts/probes/cp5_actuator_paths.md`, harness committed beside it).
- **`address_arg_2` — a composite outbound destination** (`single_call`). AMQP's wire
  identity is the exchange AND the routing key, which the one-address contract could not
  express: a row now names a second capture and a catalog-declared `address_separator`
  renders the pair as `exchange/routingKey`. An overload with no exchange is the routing key
  alone, and an explicitly empty exchange renders as the routing key alone too, so the two
  spellings of one destination stay one identity. If either half cannot be read the row
  publishes NO address — half a composite identity is a different destination, not a partial
  answer.
- **`path_prefix` — a framework's constant base path** (`annotation_driven`). A catalog may
  declare a fixed prefix that no annotation carries; it joins the front of the type-level
  prefix under the same deduping seam. Refused at load without a `path_separator`, since the
  two halves would otherwise concatenate bare.

- **A varargs argument's own elements are read, by all three consumers that wanted them**
  (2O Task 13). Extractor capability 9.15 models the array a varargs call site builds
  (`{"kind":"array","elements":[…]}`); nothing read it, so three declarations sitting in the
  facts derived nothing. All three now read it, through one conjunct
  (`resolve/shapes/arguments.py`'s `_array_elements`, guarded by the `array` kind and only
  that kind — an array the extractor could not read END TO END never reaches it and still
  degrades to `unresolved`):
  - `combinator`'s **media predicates** — `accept(MediaType...)`/`contentType(...)` fill
    `produces`/`consumes` where they always declared them.
  - `channel_via`'s **`all_strings`** — `Arrays.asList("t1","t2")` is genuine varargs and now
    resolves per topic, as `List.of` already did. The two spellings of one subscription answer
    alike.
  - `single_call`'s **`channel_arg`** — a destination slot holding an array derives ONE ROW PER
    ELEMENT, via the new `channels_of`. `WebSocketHandlerRegistry.addHandler(handler,
    String... paths)` registers one handler at every path named, so every path is a row.
  **Behaviour change for real modules**, all in the direction of columns that were NULL
  carrying values, none of it a new or changed endpoint identity: a WebFlux functional route
  declaring `accept`/`contentType` gains `produces`/`consumes` (and, with them, a rung-2
  answer from the format ladder where it previously fell to `unresolved`); a Kafka consumer
  subscribing through `Arrays.asList` gains one row per topic where it had one unresolved row;
  a Spring WebSocket registration gains its dispatch path, and a multi-path registration gains
  one row per path. `url_arg` is deliberately untouched — no shipped address capture is
  varargs, and CP-2's peer/path split has no measured meaning applied element-wise.

### Changed

- **One dispatch rule, in one place** (2Q, `G4`). Which method a call site can run moved out
  of `resolve/return_flow.py` into **`resolve/dispatch.py`**, unchanged, so `call_edges` and
  `return_flows` read the same answer rather than deriving it twice — `OI-16` already
  records that M04 §4's designed pass will one day be a second answer, and this keeps it
  from being a third. The move exposed one defect and fixed it: the "is this a method this
  workspace scanned" set was built from `method_symbols`, which excludes constructors by
  construct kind, so every `new` on a type the module declares read as the third-party
  boundary — 13 of `mall-admin`'s 1,979 boundary edges, and a constructor doing real work
  invisible to a trace. `return_flows` is unaffected and byte-identical (566 rows over 552
  sites, measured before and after). The two guards moved with the rule and are renamed
  `dispatch.callee-descriptor-is-stripped-to-bare` and
  `dispatch.exact-dispatch-admits-no-override`.

### Fixed

- **The extractor could not read a class file built by the current LTS JDK at all** (`OI-42`,
  the gap analysis's `G-3`). `org.ow2.asm:asm`, `asm-tree` and `asm-analysis` move **9.7 ->
  9.10.1** — the one dependency change in this group, approved by the user for exactly this
  reason (GUIDELINES §7 otherwise forbids it), with no other version touched.

  ASM's version *is* the class-file ceiling: 9.7 refuses `major_version` above **67** (JDK
  23), so a module compiled by JDK 24, 25 or 26 was refused outright — and the refusal took
  the whole scan with it, exit 1 with zero fact files. Measured before, on
  `byte-buddy-1.18.11.jar` from the local repository: `Unsupported class file major version
  68`, 0 documents. Measured after, same jar: **3,074 documents, 114,805 facts**. Eight of
  1,792 locally cached jars already carry a major above 67.

  **Measured, not assumed:** 9.10.1 parses majors **45 through 71** (`major = JDK + 44`, so
  Java 1.1 through JDK 27) and throws at 72 — measured by rewriting the two `major_version`
  bytes JVMS 4.1 fixes at offset 6 on a real class file and scanning it, at every major from
  45 to 72. The range is pinned as a test by the change below, so a later bump that moves the
  ceiling is caught rather than silently skipping class files ASM could have read.

  **The visitor API level is deliberately unchanged.** `Opcodes.ASM9` says which visitor
  callbacks this code is written against; it is a different concept from the class-file
  ceiling and raising it is not a side effect of reading newer bytecode. 9.10.1 offers no
  higher *stable* level: the only constant above `ASM9` is the deprecated
  `ASM10_EXPERIMENTAL`, and constructing a visitor with it throws — measured, this jar —
  `IllegalStateException: ASM10_EXPERIMENTAL can only be used by classes compiled with
  --enable-preview`. Taking it would therefore cost a `--enable-preview` compile and runtime
  for the whole extractor, on an API ASM itself marks unstable and deprecated, in exchange for
  callbacks describing JDK *preview* constructs this codebase reads nothing of. Not taken.

  **This moves the wall; it does not remove it.** The next JDK arrives on a schedule. The
  durable half — a class file above the ceiling is skipped rather than fatal — is `OI-42`'s
  remaining half and ships separately, so that this dependency change can be reverted on its
  own.

- **Four catalogs adopt the three new words, and three register rows close.**
  `spring-kafka.yml`, `spring-jms.yml` and `spring-rabbit.yml` each name their
  repeatable container, so a method carrying two listeners now exports both
  destinations instead of none (`OI-36`); all three gain a `nested_annotation_args`
  requirement, so a scanner that cannot read a folded use skips the catalog visibly
  rather than reporting half a module's listener surface.
  `microprofile-graphql.yml` reads all five of the operation-name sources SmallRye
  consults, in the measured order (`OI-35`), and falls back per annotation —
  `@Query` stripping `get`/`is`, `@Mutation` stripping `set` (`OI-5`). The
  characterisation test that asserted the wrong address now asserts the served one.

  **CP-15 gains a sixth question**, added because `OI-35`'s close needed an
  attribute name and rows 1-2 give annotation types: `getOneOfTheseMethodAnnotationsValue`
  reads each source's member named `value`, and an empty value stops the search
  rather than falling through. Taking that from the method's own name would have
  been §5.3's own failure, and Jackson's `@JsonProperty` declares six members.

  Five more guards, all measured to kill — one per catalog on the container fqn,
  plus `microprofile-graphql.fallback-direction-is-per-annotation` and
  `microprofile-graphql.name-sources-are-the-measured-annotations`.

  **`OI-37` is NOT closed**, and its row says why: two of the three annotation
  searches carry no strategy constant, so what they search is unmeasured. What the
  pass did settle is that `annotation_driven._synthetic_annotations`' claim that "a
  messaging listener annotation is never interface-inherited by its own framework"
  is false (CP-16 row 4e), and the comment no longer says it.

- **`config_join` asked the canonical-path seam nothing, on rows whose protocol and direction
  are both per-row** (2O Task 9 step 4; the Task 2 carry). `single_call` had the identical
  shape and the identical bug — its rows carried a per-row `direction` override while its seam
  read `catalog.direction`, so the gate answered about a different row from the one being
  minted — and `config_join` writes `path` from a destination whose protocol comes from the
  binder configuration and whose direction comes from a suffix or channel rule, with no seam at
  all. `_addressed` now asks `serves_urls` of the ROW's own two values. **No shipped catalog
  reaches the canonicalizing branch and no real module's output moves**: the branch is inbound
  HTTP alone and both shipped `config_join` catalogs speak broker protocols. It is pinned by
  two synthetic catalogs, one per binding source, each failing under either half of the wrong
  gate.

- **Two schema-describing documents said `open_questions.question` was a two-value set** while
  `resolve/open_questions.py` had enforced five since the start of Phase 2O
  (`docs/principles-sweep-2026-09-05.md`, `B-M1`). Corrected in
  [D01](docs/components/D01-graph-schema.md) and `storage/duckdb/schema.sql`, in the commit that
  shipped the writer the last of the three 2O kinds was waiting for — D01 now also names each
  kind's own `candidates` keys, which is what a reader of that table needs and what the
  renderer switches on.

- **`docs/COVERAGE.md` gave a stale reason for the WebFlux predicate-media boundary.** It said
  the `MediaType` vararg constants "compile through an `ANEWARRAY` the extractor cannot read",
  which stopped being true at extractor capability 9.15: the slot now carries
  `{"kind":"array","elements":[…]}`, and `combinator._media_value` answers for `string` and
  `enum` kinds with no case for `array`. What the row reports is unchanged; what would close it
  is engine work rather than an extractor candidate.

- **Five stale or unstated rationales corrected** (round-1 review, the minors it named).
  `spring-kafka-template.yml` said `sendDefault`'s arities 2/3/4 "remain undeclared" thirty
  lines above the rows declaring them, and its counts said "held six" and "the four that were
  missing" while enumerating five — it held five and five were added. `retrofit.yml` said
  "MEASURED, at retrofit 2.11.0" where the artifact states no version anywhere in its own
  bytes and CP-12's identity row prints `assumed` for that column alone: the label is the
  coordinate that was requested, which §5.4 separates from the observation. CP-12's
  `_declared` reads a type's DECLARED members and walks no supertype, which bounds every "the
  framework's whole set" answer in that probe and was disclosed nowhere — the probe and its
  document now say so, with the condition that falsifies it. `jakarta-jms.yml` justified one
  `channel_via` pair for all eleven consumer rows with "`Topic` and `Queue` both extend
  `Destination`", which is false for the eight `Topic`-typed rows: `createQueue` returns a
  `Queue`, so that half can never link there. And `A-M10`'s old-workspace incomparability was
  in COVERAGE only, where the person who can act on it — by re-running `analyze` — does not
  look; `README.md` now carries it, which is what §8.1 rule 3 asks of an escape that is a
  user action.

- **The call-site insert had no addresses-nothing gate, and `combinator` reached it**
  (round-1 review, MAJOR 6). `derive_endpoints.sql` has carried mechanism 3's gate since
  `A-C1` — a row whose address is empty and whose `peer` is NULL names no endpoint, and
  publishing one at `resolved`/`compiler` presents a boundary the running system does not
  serve as an observation. `derive_call_endpoints.sql`, which every call-site engine inserts
  through, had none: its only `WHERE NOT` was the dedup.

  `combinator` stamps `resolution: resolved` whenever nothing poisoned the read and returns a
  NULL path when a folded route accumulated no path part, so
  `RouterFunctions.route(RequestPredicates.accept("application/json"), handler)` inserted an
  inbound-HTTP row with a NULL method AND a NULL path, at the top evidence tier — and NULL
  paths skip the dedup key, so N such routes inserted N of them. Round 1b called this
  pre-existing and out of scope; it is the exact shape mechanism 3 exists for, and mechanism 3
  made the asymmetry sharper rather than softer.

  The gate is **scoped to `resolved`**, and the scope is the whole difference between a gate
  and a silent under-report: an `unresolved` row with no path is a real, distinct fact — "this
  method calls something whose destination nobody could read" — which the same file's dedup
  paragraph already turns on. A `resolved` row with no path claims the address was read and
  that there is none. It is also scoped to a **NULL** path rather than to an empty one: on
  this side a `path` is either an address an engine read or NULL, and whether an empty address
  is real is a protocol question `domain/paths.py` owns — `supertype_dispatch` publishes its
  patterns verbatim, so `@WebServlet(urlPatterns = "")` reaches this insert as `''` and no
  probe has measured what we should publish for it. The under-report the gate does trade for
  is stated in `docs/COVERAGE.md`: a constraint-only WebFlux route IS served and we cannot
  express its address.

  The test that asserted the old row now asserts emptiness, and `scripts/guard_check.py` kills
  it with the gate disabled. `spring-webflux-router` leaves the near-miss backlog.

- **`A-M9` closed one of FOUR WebFlux routing surfaces and COVERAGE claimed all four**
  (round-1 review, MAJOR 3). `docs/COVERAGE.md` listed
  `RouterFunctions.route().GET(…)` — the BUILDER DSL — as "✅ shipped", and the `A-M9` pass
  added "Both routing DSLs now read all seven verbs" beside it. `RouterFunctions$Builder`
  (seven verbs x four overloads) and `RouterFunctionDslKt.router` with `RouterFunctionDsl`
  (seven x five) are undeclared in `spring-webflux-router.yml`, unmentioned in any probe, and
  derive **nothing** — verified with `javap`/`unzip` against spring-webflux 6.1.6 and by
  driving the builder shape through the shipped catalog.

  **Both claims are corrected rather than the surfaces closed**, which is the honest half of
  the choice: the builder's verb call sits on a receiver returned by an argument-less
  `route()`, and the `combinator` grammar's entries are argument-rooted or body-linked with no
  word for that, so closing it is engine work plus a probe of which overload position carries
  the path. Two boundary rows name each surface with what falsifies it, and a test pins the
  builder DSL's silence so that closing it shows up as a failure rather than as nothing.

  This is an under-report and not a fabrication: the argument-less `route()` is not a root
  candidate, so no poisoned row is minted either.

- **Two near-misses declared coverage the guard harness measured as absent** (round-1 review,
  findings 7 and 8 — the harness's own first audit found both).

  The `spring-rabbit` `@RabbitHandler` near-miss named `derive_endpoints.qualifier-scope`, and
  `spring-rabbit.yml` declares no `requires_qualifier` at all — so that conjunct is a no-op
  for the catalog and the guard name was simply false. It names
  `derive_endpoints.addresses-nothing` now, the gate that really holds it up; that guard is
  registered for the first time, which closes one of sweep 1's four unnamed
  fabrication-prevention guards, and the qualifier gate is named by the invented-catalog
  near-miss that does reach it.

  The `spring-actuator` empty-`@Endpoint` near-miss is guarded twice over and pins neither
  half: making `@Endpoint` a mapping annotation mints a CLASS-target declaration, and the
  `construct_kind IN ('method', 'function')` join drops every one of those on its own account.
  Since `@Endpoint` is `@Target(TYPE)`, that weakening can never produce a row —
  `spring-actuator.operations-are-the-mapping-annotations` was a **no-op mutation**, which the
  harness's own design forbids counting, so the registry entry is removed and the test carries
  no marker and says why.

  `_DOES_NOT_DISCRIMINATE_YET` is now **empty**: `scripts/check.sh --guards` reports **31
  killed, 0 survived, 0 unmeasurable**. The harness's own self-test no longer depends on a live
  defect existing — it constructs a guard whose edit rewrites a comment, so that "the edit
  changes no behaviour" is a property the test guarantees rather than a fact about another
  test that any commit may change.

- **`A-M2`: a servlet whose `service()` override does NOT delegate published verbs the
  container does not dispatch, and `bypassed_by` was inert** (round-1 review, MAJOR 5 and
  MAJOR 4 — one change, because they are one defect seen from two ends).

  CP-9 rows 35-40 measured a DELEGATING `service()` wrapper — `super.service(req, resp)` with
  `doGet`/`doPost` declared — serving GET 200, POST 200 and refusing PUT with 405, and round
  1b correctly stopped discarding such a class. It then applied that verdict to every
  `service()` override declaring `doXxx`, which is §5.4's failure with the arrow reversed, and
  recorded the residual in COVERAGE as an accepted over-report. **CP-9 rows 41-43 now measure
  it**: the same class with the delegation removed serves GET 200, POST 200 and **PUT 200** on
  all three containers. The dispatch never runs, the `doXxx` methods are unreachable, and
  publishing the declared verbs while withholding one the container serves is a wrong answer
  rather than a partial one.

  **The distinguishing fact was always in the stream, and CP-9 rows 44-46 measure that too**:
  a delegating override's `super` call arrives as `invoke_kind: special` on an
  `HttpServlet#service` target — both entry-point signatures, both package spellings — where
  the non-delegating one's reads `ABSENT`. So the bypass now asks it, and `call_site` joins
  both servlet catalogs' `requires`; a scan producing no call sites SKIPS the catalog and says
  so rather than reading every wrapper as a replacement. No new catalog key: `bypassed_by`
  names the members, and what delegation means is `supertype_dispatch`'s own semantics.

  **This is also the `bypassed_by` decision (§5.3).** Under round 1b's `and not handlers`
  qualifier the key reached only classes another branch reached anyway — provably inert, dead
  catalog vocabulary that looked live, with three near-misses claiming to pin it and the guard
  harness measuring that none of them did. It is **kept and made load-bearing** rather than
  retired: the retirement case rested on the narrowing, and the narrowing was itself the
  defect. All three near-misses are rewritten to declare a `doXxx` — so there is something to
  lose — and `scripts/check.sh --guards` now kills all three.

- **`A-M13`'s own regression: a Spring Data custom-fragment method was published as a
  `/search/` route** (round-1 review, CRITICAL 2). The `A-M13` fix widened the query-method
  walk to cross every module-local superinterface, so
  `interface OrderRepository extends CrudRepository<Order, Long>, OrderRepositoryCustom`
  derived `GET /orders/search/searchByFullText` — a route Spring Data REST does not serve, on
  a method whose body lives in a hand-written `OrderRepositoryCustomImpl`. **Before the
  `A-M13` fix that input derived no search route at all.**

  CP-13 Q1 recorded `calculateQueryMethods`' filter and named `isCustomMethod` inside it; the
  fix read the ENUMERATION beside it and reasoned about the rest. Q6 and Q7 now open the
  filter, identical bytecode at spring-data-commons 3.2.5 and 4.1.1: `isCustomMethod` is
  `RepositoryComposition.getMethod(m) != null`, so a method the custom-fragment composition
  resolves is not a query method; and `FragmentMetadata.getFragmentInterfaces` is the
  repository interface's own `getInterfaceNames()` filtered to those NOT carrying
  `@NoRepositoryBean`. So the annotation — already catalog data, as `no_repository_bean` — is
  the whole of what tells a shared base from a fragment, and the walk now crosses only the
  annotated ones. Pinned by
  `derived_resource.inherited-interfaces-are-no-repository-beans` in `scripts/guard_check.py`.

  An under-report rides with it and is stated in `docs/COVERAGE.md`: a module-local base that
  extends a contract WITHOUT the annotation is a fragment by the same measured rule, so its
  query methods reach no `/search/` route on the repository deriving from it.

- **`A-M15`'s own regression: an OVERRIDDEN SOAP operation was published twice, and an
  `@WebMethod(exclude = true)` override republished the operation it withdraws** (round-1
  review, CRITICAL 1). The `A-M15` fix below widened the member rule to walk a gated class's
  superclass closure — correctly — and then enumerated **one row per declaration** where the
  enumeration it mirrors yields **one per signature**.

  MEASURED rather than reasoned (CP-13 Q5, on the JDK the probe process itself reported):
  `Class.getMethods()` over `class BillingWebService extends AbstractBilling`, both declaring
  `public String refund(String)`, returns `BillingWebService#refund` and NOT the base's. So a
  `@WebService` class overriding a base operation shipped **two** rows for one operation, the
  second handled by a class the RI never exposes; and where the override carried
  `@WebMethod(exclude = true)`, the annotated rule withdrew the override's row while the base's
  identical declaration walked past the member rule's anti-join and published the withdrawn
  operation at `resolved`/`compiler`, attributed to the base. **Before the `A-M15` fix that
  input derived nothing at all**, which makes this the one place the sweep's fix pass left the
  project worse than it found it.

  A new `exposed_members` CTE keeps the nearest declaration of each `(name, parameter types)` —
  the language's own key (GUIDELINES §8.1), never the descriptor hash, which covers the return
  type and would leave a covariant-return override undeduplicated — and the exclusions and the
  annotation anti-join are asked of that one member. `gate_ancestry` gained a `depth` and, with
  it, an explicit `walked` cycle guard, since the plain `UNION`'s deduplication stopped being
  one the moment two visits to an ancestor differed in a column. Pinned by
  `derive_endpoints.one-exposed-member-per-signature` in `scripts/guard_check.py`.

- **`A-M15`: a `@WebService` class's INHERITED operations were absent from its SOAP surface**
  (principles sweep §3.3). `derive_endpoints.sql`'s member rule joined the class gate on
  `s.enclosing`, which reads "the public methods of C" as "the public methods DECLARED in C" —
  JLS 8.2 says the members of a class include those inherited from its superclass, and
  `jakarta-jws.yml`'s own comment argues at length that an unannotated public method IS an
  operation ("a catalog that derived only the annotated methods would report a service missing
  one of its own operations") while the join made exactly that mistake one axis over.

  Measured rather than read off the specification's wording (CP-13 Q3/Q4, jaxws-rt 4.0.2):
  `RuntimeModeler.processClass` walks the implementor class's `Class.getMethods()`, drops only
  those declared by `java.lang.Object`, then applies `isWebMethodBySpec`. A new `gate_ancestry`
  CTE is that walk — the transitive superclass closure over capability 9.13's erased edge,
  `UNION` rather than `UNION ALL` so a fact stream disagreeing with its own language about
  cycles terminates instead of looping. Rows now carry the type that ANNOTATED them beside the
  method symbol, because an inherited member's declaring class carries no scope, prefix or
  construct gate; every catalog written before this carries it NULL and nothing about them
  changes.

  Two divergences from the RI are stated rather than closed: a `public final` method is exposed
  by us and not by JAX-WS, because `ClassScanner.methodModifiersJson` records neither
  `ACC_FINAL` nor `ACC_ABSTRACT`; and Apache CXF is not measured, so `jakarta-jws.yml` stops
  claiming it was "verified against BOTH reference implementations" without naming either
  (`A-Mi7`) and is scoped to the one CP-13 opened.

- **`A-M2`: a servlet that wraps `service()` and delegates lost its whole surface** (principles
  sweep §3.3). CP-9's verdict 8 — "a class overriding `service()` derives NOTHING" — was measured
  against `ServiceOnlyServlet`, which overrides `service()` and declares no `doXxx` **at all**,
  and was then applied to every `service()` override. The commonest real form is a cross-cutting
  wrapper that calls `super.service(req, resp)` and declares `doGet`/`doPost`, and it derived
  nothing: address, verbs and handlers, all silently absent. §5.4 in one line — a verdict is
  bounded by the configuration it measured.

  Re-measured rather than reasoned. CP-9 gains a delegating servlet on **both** `service`
  signatures (rows 35-40), because `HttpServlet` has two and a verdict read against one must not
  be applied to the other — which is this finding's own mistake. All three containers agree:
  GET 200, POST 200, **PUT 405**. The 405 is the discriminator: `HttpServlet`'s dispatch still
  runs, so the verb table describes such a class exactly. The bypass now discards a class only
  where it declares no member of the dispatch table.

  Three shipped tests asserted the defect — each declared a `doGet` beside the `service`
  override and expected nothing — and are corrected to the configuration CP-9 actually measured.
  The residual is stated in COVERAGE and is deliberate: a `service()` override that does NOT
  delegate and declares `doXxx` anyway now over-reports, because nothing in the fact stream
  separates it from the delegating form without `call_site` in the catalog's `requires`.

- **`A-M10`: an array had exactly one dimension** (principles sweep §3.3). ASM's
  `Type#getElementType` returns an array's **innermost** element type rather than its component
  type, and both `TypeRefs.descriptorName` and `TypeRefs.elementArguments` built their fact from
  it — so `descriptorName(getElementType()) + "[]"` appended exactly one `[]` however many the
  descriptor carried. `String[][]` and `String[]` produced **byte-identical** facts, symbol and
  argument alike, and JVMS 4.3.2 and JLS 10.1 make the number of `[` part of the type's
  identity: a DR-5 contract comparison of a caller sending `String[][]` against a callee
  expecting `String[]` read equal, and `shapes/expansion.py` hashed the wrong shape. The two
  seams also disagreed with each other — `NodeCollector.visitArrayType` recurses one dimension
  at a time on the signature path and was right, while the descriptor path, which is the one
  every plain array takes because javac writes no `Signature` attribute for one, was wrong.
  Both now drop one leading `[` and recurse.

- **`A-M16`: `.sextantignore` was loaded at the module root, so a reactor's never reached a
  submodule** (principles sweep §3.3). D04 §3 is emphatic and is itself an amendment — "One
  file, at the **repository root**, and every pattern in it is matched against a path made
  relative to THAT root" — and `analyze` loaded it at `module.root` while `api.py` analyzes each
  submodule with its own root. Both halves failed: the file was never read, and a pattern
  written relative to the reactor root would not have matched if it had been. The rules are now
  loaded at the root the run was invoked against, and the walk relativizes against
  `ignore.repo_root` rather than `module.root` so the two cannot drift apart by construction.
  A single-module repository is unchanged — the two roots coincide, which is why the old spelling
  looked right. **A module OUTSIDE the analysed root keeps its own**:
  `<module>../orders-service</module>` is legal Maven and `fixtures/orders-reactor` is exactly
  that shape, and a path outside a root has no root-relative form for a pattern to address. The
  built-in layer applies at every depth and always did, so this was a coverage gap in the
  repository-authored layer and never a credential leak. The enrichment jail's own
  load is unchanged and stated in D04: `enrich` is invoked against one module and has no reactor
  model to ask.

- **`stamp_media.sql`'s reach is settled** (principles sweep §7.4, where two sweeps touched the
  file and neither read it). Sweep 2's claim — "a stamp lands only where every resolved
  environment agrees, and never over a non-NULL column" — is TRUE, and two shipped tests already
  proved each half. Sweep 1's is half true: the UPDATE really does match on
  `(protocol, direction)` alone, so it stamps rows other catalogs derived — which is the
  mechanism, since `spring-kafka-media.yml` derives none of its own — but the CROSS-MODULE half
  is impossible, because `endpoints` has no module column, every module gets its own workspace,
  and `resolve()` runs once per module. What remains is an over-report onto a raw
  `KafkaProducer` row within one module, on a carried column rather than an identity one,
  bounded by the dependency gate and now stated in COVERAGE and pinned in both directions.

- **CP-13: what three frameworks do with an INHERITED member is now measured**
  (`scripts/probes/cp13_inherited_members.md`). `A-M13`, `A-M14` and `A-M15` encode the same
  invented rule — a type's members are the ones it DECLARES — and the sweep graded all three
  `read`, with the framework half explicitly unverified. The language half was never in doubt
  (JLS 8.2, 9.2, 9.4.1, 8.4.2); what needed measuring turns out to be answerable from bytecode
  without deploying anything, because in every case the question reduces to which reflective
  enumeration the framework calls and what it filters out of the result. Spring Data's
  `calculateQueryMethods` is `getRepositoryInterface().getMethods()`; its base-method lookup
  compares name, parameter count AND parameter types; the JAX-WS RI's `RuntimeModeler` walks the
  implementor's `getMethods()`, drops only `java.lang.Object`'s, and then excludes `static` and
  `final`. What it does NOT settle is stated in the probe: nothing was deployed, so a live run
  stays on the backlog and `A-M14` is left open on the strength of this rather than closed by it.

- **`A-M13`: a repository's query methods were the ones it DECLARED** (principles sweep §3.3).
  `derived_resource._methods` keys on `enclosing`, so
  `interface OrderRepository extends BaseRepo<Order, Long> {}` — the ordinary shared-base
  repository layer — exposed no search routes at all while the framework served every one of the
  base's. Silent, with no COVERAGE row. The walk now crosses module-local superinterfaces,
  own-first so an override shadows what it overrides, and stops short of a `contracts` entry.
  Measured, not assumed (CP-13 Q1): the framework enumerates `getMethods()`, which returns
  inherited interface methods, at both measured spring-data-commons minors.

- **`A-M12`: the payload-binding ancestry walk had `A-C4`'s invented rule too** (principles
  sweep §3.3). `shapes/parse_binding.py` built its ancestry from `supertypes` +
  `implementations` and never from `superclasses`, so a payload type whose only route to a
  protobuf marker is a non-generic `extends GeneratedMessage` reached nothing and bound nothing
  — an under-report, silent, with the endpoint keeping the bytes shape its signature declared.
  Two stale sentences went with it, both asserting that "a plain `extends` is NOT in the fact
  stream at all": the walk's own docstring and `spring-web.yml`'s protobuf comment. That was
  true when written and capability 9.13 falsified it — `supertype` is D00 §5a's
  parameterised-type carrier, `superclass` is the inheritance edge, and reading the first as
  the second is the rule `A-C4` names. `spring-web.yml` also stops asserting that the protobuf
  LITE runtime "reaches none of these and binds nothing", which nothing measured (`A-Mi2`).

- **`A-M1`: an overloaded receiver's handler was picked by descriptor hash order** (principles
  sweep §3.3). `interface_implementation` resolved a registration's receiver to a handler with a
  prefix scan over `method_symbols` ordered by symbol — a SHA-256 of the descriptor — taking the
  first match, and the comment defending it reasoned about the INTERFACE while the lookup ran
  against the implementing CLASS. Nothing stops a class declaring a private helper, a
  convenience form or a javac bridge beside its real override, so the "tiebreak" was a coin flip
  between two methods, one of which is wrong, published at `resolved`/`compiler` and carried
  into this engine's dedup key. The selector is now name AND parameter types (JLS 8.4.2), the
  rule `supertype_dispatch._members` already applies and which sweep 6 clears as this tree's
  reference implementation. One candidate resolves as before; several resolve only when the
  interface is itself scanned and its declared parameter types name one; otherwise the handler
  is NULL and the row still derives — which is what the engine's own docstring already promised
  and did not do.

- **`A-M9`: the WebFlux router catalog's verb vocabulary was the fixture's verb vocabulary**
  (principles sweep §3.3). `RequestPredicates` and `CoRouterFunctionDsl` each declare seven
  per-verb factories at spring-webflux 6.1.6 and 7.0.2 (CP-12 Q11/Q12), and
  `spring-webflux-router.yml` encoded GET/POST/HEAD in Java and GET/POST in Kotlin — exactly
  what `fixtures/orders-service`'s own two route files declare. An ordinary
  `RouterFunctions.route(RequestPredicates.PUT(…), …)` derived a row with neither verb nor
  address, and COVERAGE stated two WebFlux boundaries and named no verb gap. The catalog's own
  comment states the standard it was built to — "exactly what 2E's checkpoint froze against a
  real scan… nothing here is invented past that" — which, applied to a fixture rather than to
  the framework, is §8.1 rule 1's failure in the catalog's own words. Pure catalog data: nine
  new vocabulary rows, no engine change. `method(HttpMethod)`/`methods(HttpMethod...)` stay a
  stated boundary, because their verb is an enum constant argument and this grammar reads a verb
  only as a literal declared beside its owner.

- **`A-M6` / `A-M7`: four broker catalogs declared the arity their fixture happened to call**
  (principles sweep §3.3). `_matching_method` filters candidates on
  `row.get("arity") in (None, len(arguments))` **before** it consults a descriptor, so a call at
  an undeclared arity reaches no row at all and derives nothing. That silenced
  `producer.send(record, callback)` and `consumer.subscribe(topics, rebalanceListener)` — the
  idiomatic asynchronous producer call and the idiomatic consumer-group call — the four
  partition- and timestamp-carrying `KafkaTemplate.send`/`sendDefault` forms, and ten of
  `jakarta.jms.Session`'s eleven consumer factories, which is every selector-carrying consumer
  and every durable or shared subscription. COVERAGE listed all four catalogs "✅ shipped" with
  no arity qualification. Measured at kafka-clients 3.6.2, spring-kafka 3.1.4 and
  jakarta.jms-api 3.1.0 (CP-12 Q6-Q9), with every new descriptor pinned to bytecode by a
  re-run of CP-10. Each addition is a TRAILING argument, so every new row reads its
  destination at the position its sibling already does.

  Two exclusions are stated and pinned rather than left silent.
  `KafkaConsumer.assign(Collection<TopicPartition>)` carries its topic inside a constructor two
  hops from the call site, where every `channel_via` form is one hop; `Session.createBrowser`
  returns a `QueueBrowser`, which enumerates a queue without consuming from it, so an inbound
  row would claim a delivery the broker does not make.

- **`A-M5` / `A-M8`: two annotation catalogs read a subset of their annotation set** (principles
  sweep §3.3). `retrofit.yml` declared six of Retrofit's eight request-method annotations, so an
  `@OPTIONS("/x")` method derived nothing at all with no boundary stated; `@OPTIONS` now derives,
  and `@HTTP` is a boundary the suite pins rather than a silence — its verb is a plain `String`
  and `$method_from`'s read extracts an enum constant's name, so declaring it would ship
  `method: ''`, and a test goes red the moment somebody adds the row without changing the engine.
  `spring-sqs.yml` read `@SqsListener.value` alone while `queueNames()` carries
  `@AliasFor(value = "value")` — one attribute under two spellings, measured at
  spring-cloud-aws-sqs 3.1.1 (CP-12 Q10) — so a listener using the spelling AWS's own
  documentation uses composed an empty destination and the addresses-nothing gate withheld it:
  absent from the export, not present with a blank address. Both spellings are now read, `value`
  first, which mirrors `@AliasFor`'s own rule that the two can never carry different values.
  `retrofit` and `spring-sqs` leave the near-miss backlog.

- **`A-M3` / `A-M4`: the two Spring HTTP clients knew five of eight verbs, and a terminal set
  that was wrong at both measured Spring minors** (principles sweep §3.3). `spring-webclient.yml`
  and `spring-restclient.yml` each declared five request-starting roots —
  GET/POST/PUT/DELETE/PATCH, exactly the verb vocabulary the fixture happens to use — while both
  clients declare eight at 6.1.6 and 7.0.2 (CP-12 Q1/Q3). A chain rooted on an undeclared starter
  is never rooted at all, so `webClient.head().uri("/health").retrieve()` derived NO row and
  nothing said so. `head()` and `options()` now derive their own verb; `method(HttpMethod)`
  derives its address at `unresolved` with `method: NULL`, because its verb is an enum constant
  a string-literal scanner cannot read and withholding the call entirely would trade nothing for
  a silent drop. WebClient's `terminal: [retrieve, exchange]` was wrong in both directions at
  once: `exchangeToMono`/`exchangeToFlux` were in the list at neither version and are the only
  exchange-style terminals at 7.0.2, while `exchange` was **removed** in Spring 7. And
  `spring-restclient.yml` stated "no `exchange` on this synchronous surface" about a type
  declaring two `exchange` overloads at both minors. Every list is now measured, version-scoped
  in the catalog, and pinned against the **7.0.2** column so a dead entry is never made
  compulsory.

- **`A-C8`: ARCHITECTURE said redaction happens during extraction; it does not** (principles
  sweep §3.2). Masking runs at the two EXITS — `render` and `export` — and the workspace holds
  verbatim values, which D04 §4 has recorded as an approved amendment since 2026-09-02 and
  ARCHITECTURE was never updated (a §5.1 miss). The second sentence described a cache key, and
  there is no cache. A confidentiality claim (NFR-8) that was false in the first document a
  reader opens, and the one that decides whether somebody believes `<module>/.sextant/facts/**`
  is safe to copy, share or commit. Corrected in place, with the old text quoted so the
  correction is visible rather than silent.

- **`A-C9`: following the documented configuration aborted every command** (principles sweep
  §3.2). D04 §2 specifies `~/.sextant/config.yml` and a repository-root `sextant.yml`; neither
  is ever opened by anything. The file that IS read is the per-module `.sextant.yml` — one
  character from the documented repository name, with a closed key set — so in a single-module
  repository, where the two roots coincide, writing any documented key raised
  `SextantConfigError` and stopped the run, with a message saying only that the key is "read
  nowhere". That is equally true of a typo and points at nothing. The refusal now names the
  mistake: which file the key belongs to, and that Sextant does not read that file either.
  Amendment boxes in D04 §2 and D02 §6 say the same to a reader, and the register gains its
  missing row — including the standing ruling that project catalogs are deliberately
  unscheduled, so NFR-9's stated extension path is knowingly unmet.

- **`A-C3`: an endpoint returning no body was published as returning an object** (principles
  sweep §3.2). `WireTypes` mapped the primitive `void` to the empty string and let
  `java/lang/Void` fall through to `default -> "object"`, so `ResponseEntity<Void>` /
  `Mono<Void>` / `Call<Void>` — the idiomatic "no body" in nine catalogs' frameworks — published
  an object response shape AND filed `java/lang/Void#` as an unexpanded type, a gap report
  pointing at a type with nothing to expand. Thirty-three catalogs carried a `known_types`
  repair for it and nine did not; `derive_shapes` is global and insert-if-absent, so the first
  catalog to reach the type described it for every other one. Fixed in the projection, where it
  belongs: `java.lang.Void` is an uninstantiable placeholder whose only value is null, which is
  language knowledge and not catalog knowledge. A new architecture test refuses any catalog
  `known_types` entry that contradicts the extractor's own switch — the invariant twenty-eight
  catalog comments already claimed and nothing enforced.

- **`A-C1` / `A-C6`: four catalogs derived from evidence the framework does not act on**
  (principles sweep §3.2). `jakarta-websocket` and `spring-stomp` declared no type-level gate at
  all, so a lone method annotation minted a declaration — and with no class-level annotation to
  prefix it, at the EMPTY address. Worst of them: a `@ClientEndpoint` class, one that dials OUT,
  carrying the `@OnMessage` callback was published as an INBOUND WebSocket endpoint, direction
  inverted and address invented in one row. `retrofit` and `spring-http-interface` declared no
  `declared_on`, so an exchange annotation on a concrete CLASS derived an outbound row for a
  client the framework would never create. All four gates are now measured rather than chosen
  (CP-11): `@OnMessage` is `@Target(METHOD)`, addressless, and ships in the CLIENT api jar, so
  `@ServerEndpoint` is what makes a class served; Spring STOMP's `isHandler` is byte for byte
  the `@Controller` predicate Spring MVC runs; `Retrofit.create` throws on a non-interface; and
  `HttpServiceProxyFactory` proxies through Spring AOP's `ProxyFactory`, which asserts
  `isInterface`. **Output changes for real modules**: a WebSocket client, a STOMP handler on a
  non-`@Controller` class, and an exchange annotation on a concrete class all stop deriving. The
  stated cost is on the two outbound catalogs — `declared_on: interface` also engages the SEI
  fence, so a module that ships a local implementation of its own Retrofit or `@HttpExchange`
  client loses that client's rows; recorded in COVERAGE §5.2. Two under-reports `A-C1` names are
  stated rather than closed: a `@ServerEndpoint` class whose only lifecycle method is
  `@OnOpen`/`@OnClose`, and Spring RSocket controllers, whose routing annotation
  `spring-stomp.yml` claims and whose derived output is unverified.

- **`A-C7`: a custom stereotype deleted its controller's entire HTTP surface** (principles sweep
  §3.2). `spring-web`, `spring-mvc` and `spring-graphql` gated on string equality against one
  annotation FQN over a type's own direct annotations. Spring's rule is
  `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` — a four-instruction body,
  measured identical across spring-webmvc 6.1.6, 6.2.15, 7.0.2 and 7.0.9 (CP-11 Q2) — and that
  predicate is meta-annotation aware, so a controller wearing a module-local `@MyApi` composed
  from `@RestController` matched nothing and every one of its endpoints was silently absent from
  the export. The type gate now seeds the same composition closure the method-level mapping
  annotations already used, so the composition it was always able to see reaches it. **Output
  changes for real modules**: a module with its own composed stereotype gains its whole
  controller surface. Two of the three divergences the sweep names stay OPEN on purpose and are
  stated in COVERAGE §5.1: a stereotype inherited from a superclass or an interface makes
  `isHandler` true, but `@Component` is not `@Inherited` and whether component scanning admits
  such a class is unmeasured — deriving on half a rule is what §8.1 rule 4 forbids.

- **`A-C4`: a class inherited from its superclass only when the superclass was generic**
  (principles sweep §3.2). The annotation-inheritance walk read the `supertype` fact, which the
  extractor emits only where the superclass carries type ARGUMENTS, so `class OrderController
  extends PrefixBase` had no superclass edge at all — and since an absent prefix composes as the
  empty string, the child published `/{id}` where the framework serves `/api/orders/{id}`. A
  confidently wrong address at `resolved`/`compiler`, reached by a route neither `path_fallback`
  nor `canonical_path` guards. The walk now reads capability 9.13's erased `superclass` field,
  written for every non-`Object` superclass. **Output changes for real modules**: controllers
  extending a non-generic base gain the prefix and the inherited mappings the framework serves.
  The same edge retires the bare-to-prefixed lookback the old one needed, so an abstract base
  that declares no method at all — one whose only purpose is to carry a type-level
  `@RequestMapping` — is reachable too (`A-M11`).

- **Mechanism 3: the empty-address guard was keyed on a formatting property** (principles sweep
  §4, §7.7). `derive_endpoints.sql` dropped a row with an empty address only when the catalog
  declared no `path_separator` — a property about how two halves of an address are JOINED, which
  says nothing about whether the empty address means anything. The result was that a broker
  catalog whose destinations have no slashes was protected and its structural twin on a
  slash-separated protocol was not, because declaring a separator to compose destinations
  switched the twin's own validity gate off in the same line. Seven shipped catalogs declared one
  and were all unguarded. The gate now asks whether anything in the row names an endpoint at all:
  an empty address ships only where a resolved `peer` names the service, and the one protocol for
  which the empty address is real — an inbound HTTP root route — has already been spelled `/` by
  the canonical-address gate before this runs. **Output changes for real modules**: a
  `websocket`- or outbound-HTTP-shaped annotation catalog that composed an empty address stops
  publishing that row (`A-C1`'s fabrication half); inbound HTTP root routes, named destinations
  and Feign clients calling their base address are all unaffected. `docs/COVERAGE.md`'s claim
  that an unlisted destination attribute "derives a resolved row with an empty path today" was
  already false before this change and is corrected with it.

- **`A-C5`: a module with no Spring Cloud Stream asserted four Kafka boundaries** (principles
  sweep §3.2). `config_join`'s candidate scan reads every declared method and keeps the ones
  returning `Function`/`Consumer`/`Supplier` — platform interfaces, not framework ones — and with
  no `spring.cloud.function.definition` present the framework's own default binds every
  candidate, so three ordinary utility methods on a plain class published four boundaries the
  module does not have. `config_join` joins `derived_resource` in `DEPENDENCY_GATED`: the two
  styles whose evidence names no framework are the two gated on the build declaring it, and
  `resolve/dependencies.py` now records that test applied to all eleven styles. **Output changes
  for real modules**: a module whose recorded coordinates do not name
  `org.springframework.cloud:spring-cloud-stream` derives no Stream bindings and is reported
  SKIPPED with its reason; the same applies to `spring-kafka-media`'s media stamps and
  `org.springframework.kafka:spring-kafka`. Under Maven only DIRECT declarations are recorded,
  so a module inheriting either through a parent or a starter is skipped — the skip message says
  so, and the rows it loses are a Stream binding set or a carried media decoration, never a row
  another engine derived. `fixtures/orders-service` gained the `spring-cloud-stream` dependency
  it had always been modelling and never declared.

- **`A-C2`: OkHttp's `.method("DELETE", body)` no longer publishes `GET`** (principles sweep
  §3.2). `okhttp3.Request$Builder`'s generic verb setter was not a declared step, so it passed
  through uncaptured (D02 §4) and the chain root's `http_method: GET` — OkHttp's real default
  for a bare builder — stood uncorrected: a module issuing DELETE was published as issuing GET
  at `resolved`/`compiler`, where nothing downstream can tell an asserted verb from an observed
  one. The `fluent` grammar now accepts `http_method: argN` beside the literal spelling, and
  `okhttp.yml` declares the step. A verb the scanner cannot read as a string literal derives
  `method: NULL` at `unresolved` — the honest gap the catalog's own comment claimed to be
  taking while publishing a guess. Rows change for any module using
  `Request.Builder.method(...)`: previously one `GET` row per such call, now the real verb, or
  an unresolved row where the verb is computed.

- **A client held by its INTERFACE derives nothing, and that is now written down** (descriptor
  sweep R8). A call site records the compile-time qualifying type javac emitted, and every
  `single_call` client catalog declares a single concrete `matches.owner` — so
  `SqsOperations`, `AmqpTemplate`, `JmsOperations`, `KafkaOperations`, `RestOperations`,
  `WebServiceOperations`, `PubSubOperations`, `org.apache.kafka.clients.consumer.Consumer` and
  `jakarta.jms.QueueSession`/`TopicSession` calls match nothing at all. The highest-risk case
  is `SqsTemplate.newSyncTemplate(...)`, which **returns `SqsOperations`** — the idiomatic
  construction misses entirely, and both `send` arities are inherited so nothing anchors them
  to the class. This is an owner problem a descriptor cannot fix, and making `matches.owner`
  multi-valued is engine work that was out of scope for the sweep; recorded as a
  `docs/COVERAGE.md` boundary with its falsifier rather than left silent (§8.1 rule 3). The
  descriptors themselves are identical through either type, so they carry over unchanged when
  it closes.
- **`spring-resttemplate.yml` converts wholesale: seven rows become twenty-six** (descriptor
  sweep R4). Its rows carried neither `arity` nor `descriptor`, which makes each of them a
  candidate at EVERY argument count — so adding one descriptor to one row would have claimed
  every argument count for that name and silenced every other overload of it, with no error
  path. A half-conversion of this file is strictly worse than none, which is why it is all at
  once. The file was benign as it stood and that is said plainly rather than dressed up: what
  closes here is the shape that produced the AMQP, JMS and SOAP fabrications, not a live
  defect. Every `getForObject`, `getForEntity`, `postForObject`, `postForEntity`, `put`,
  `delete` and `exchange` overload `RestTemplate` declares now has its own row with both
  `arity` and `descriptor`; the two `exchange(RequestEntity, …)` forms, whose position 0 is
  not a url, declare no captures at all and keep deriving exactly the honest empty row they
  derived before. No golden-fixture output moved.
- **`spring-websocket.yml` said varargs make a three-argument call; they do not** (descriptor
  sweep R6). The catalog, a COVERAGE bullet and three tests all asserted that a multi-path
  `.addHandler(h, "/a", "/b")` "is a THREE-argument call this row's own `arity: 2` does not
  match at all", and that the two-argument shape was unverified. Measured by compiling both
  calls against spring-websocket 6.1.6 and running the shipped extractor: varargs collapse
  into ONE argument, so one path and two paths alike record exactly two arguments with an
  `array` at position 1. The row has always matched the multi-path call. The real boundary is
  narrower and worse — `channel_of` resolves only a `kind: "string"` argument, so
  `channel_arg: 1` can never resolve a path for ANY call, and every registration derives one
  honest row with `path` NULL. Stated in the catalog and in `docs/COVERAGE.md` with its
  falsifier, and named as Task 13's to close by wiring capability 9.15's `elements` read. The
  row also gains the erased descriptor of the interface's one declared method. **Not fixed
  here**: the capture is engine work, and this is a catalog sweep.
- **`JmsTemplate` publishes through two more overloads than the catalog admitted** (descriptor
  sweep R5). `convertAndSend(Destination, Object)` is an ordinary destination-carrying call
  whose argument 0 is a `Queue`/`Topic` instance and therefore can never fabricate anything;
  it derived an honest path-NULL row until the arity-2 descriptor claimed the arity, and that
  was a regression rather than a boundary. It has its own row again.
  `convertAndSend(String, Object, MessagePostProcessor)` was never declared at ANY arity, so
  every such call derived nothing at all — a recall gap nothing recorded — and the destination
  it carries is genuinely at position 0 and genuinely readable. Both are recall with no
  fabrication risk. The file now documents its own remaining boundaries, which it did not,
  though it makes the same claim `spring-rabbit-template.yml` documents in full.
- **A row that meant several overloads is now several rows** (descriptor sweep R3). Five
  catalogs carried one `methods` row standing for two real overloads, which is the language's
  own rule missing rather than a simplification: `KafkaConsumer.subscribe(Collection)` and
  `(Pattern)`; `PubSubTemplate.publish(String, T)` and `(String, PubsubMessage)`;
  `SqsTemplate.send` at both arity 1 and arity 2; and the `Message` siblings of
  `KafkaTemplate.send(ProducerRecord)` and `ReplyingKafkaTemplate.sendAndReceive(ProducerRecord)`.
  Each is now one row per overload, each with its own descriptor. **A single descriptor would
  have been the wrong fix in every one of these**: it claims the arity, so the undeclared
  sibling goes silent. `kafka-consumer`'s `channel_via` resolver list splits with the row —
  `List.of`/`Arrays.asList`/`Collections.singletonList` to the `Collection` overload,
  `Pattern.compile` to the `Pattern` one — and the two `Message` rows declare no capture keys
  at all (`spring-sqs-template.yml`'s precedent), which preserves today's honest empty row
  rather than spending recall to close an ambiguity. Three catalog comments asserting a second
  row at the same arity "would never be reached" were true of arity matching and are false
  under descriptor matching; all three are corrected.
- **Every unique-overload `methods` row now names the overload it means** (descriptor sweep
  R2). A row matched on name and argument COUNT is matching on a rule Java does not have —
  the language identifies a method by name and parameter types in order (GUIDELINES §8.1's
  language rule) — and the rows below happened to be unambiguous only because their jars
  declare one overload at that arity today. `google-pubsub-client`, `jakarta-jms` (both
  rows), `kafka-clients`, `spring-rabbit-template`'s arity-1 row and `spring-ws-template`'s
  arity-1 and arity-3 rows each declare their own erased descriptor. Nothing derived changes:
  a unique overload's descriptor can only equal what a matching call carries. What changes is
  the release that adds a sibling — it derives NOTHING instead of having its own argument 0
  read as a destination or a payload. The comments that said a unique overload needs no
  descriptor are corrected, each with the condition that falsifies it.
- **A SOAP request PAYLOAD could be published as the SOAP service's address** (descriptor
  sweep R1, §8). The same overload collision Task 7 closed for AMQP and JMS was still live
  in `spring-ws-template.yml`: `WebServiceTemplate.marshalSendAndReceive` declares
  `(String uri, Object payload)` AND `(Object payload, WebServiceMessageCallback after)` at
  arity 2 (javap -p -s, spring-ws-core 4.1.4), and the shipped row read position 0 as the
  address for both. `marshalSendAndReceive("PAYLOAD", message -> {...})` binds the callback
  form — a lambda is not compatible with the other overload's `Object` parameter, so javac
  picks it unambiguously — and the message body was published whole as `peer`, the remote
  service the module calls, at `evidence: compiler`. Reproduced end-to-end before it was
  fixed. The arity-2 row now declares its own erased descriptor. The file's own comment
  asserted this collision "never publishes a wrong row" and also counted arity 3 into it;
  both claims were false and are corrected — arity 3 is the only three-argument overload in
  that jar. The claimed arity's cost, a callback-form call now deriving nothing, is a stated
  boundary in `docs/COVERAGE.md`.
- **A message PAYLOAD could be published as a wire destination** (2O Task 7 review,
  §8). `single_call` selected a `methods` row by name and ARITY only, and both
  `RabbitTemplate.convertAndSend` and `JmsTemplate.convertAndSend` overload on argument type
  at the arities the shipped catalogs declare — arity 2 as well as arity 3, which neither
  file admitted. A call passing a `MessagePostProcessor` therefore reached a row expecting a
  destination at that position, and a string-literal payload was published as an AMQP or JMS
  destination at `resolved`/`compiler`, indistinguishable from an observation. A `methods`
  row may now declare the overload's own erased JVM `descriptor`, compared verbatim against
  the call site's `target.descriptor`; both shipped catalogs declare one per
  address-carrying row. Once any row for a name and arity declares a descriptor that arity
  is CLAIMED — an unmatched call derives NOTHING rather than falling through to a
  descriptor-less sibling, which is the fabrication the key exists to stop. The cost is a
  stated under-report in `docs/COVERAGE.md`: the undeclared overloads, which used to derive
  an `unresolved` row, now derive none.
- **The Actuator catalog's rows are now stated as conditional on WEB EXPOSURE** (§8, 2O
  Task 7 review). `management.endpoints.web.exposure.include` is Boot's gate on whether a
  custom `@Endpoint` is served over HTTP at all, and its default is `health` alone: measured
  on Boot 3.5.10 and 4.1.1, `/actuator/probe` is a **404** under the default while
  `/actuator/health` is a 200. Nothing in Sextant reads the key, so under a module's own
  defaults every `/actuator/<id>` published at `resolved`/`compiler` is a URL nothing
  serves. No derivation changed; the over-report is now a stated boundary in
  `docs/COVERAGE.md`, in the catalog and in the probe verdict, together with
  `@Endpoint(defaultAccess = Access.NONE)`, the same conjunct in miniature.
- **An annotation-derived path carrying an expression is no longer published as an
  observation** (§8). Every such row was stamped `resolved`/`compiler` unconditionally, so a
  destination written as SpEL `#{…}` or a property `${…}` was published as though the
  characters of the expression were the address. It now publishes `unresolved` with the
  expression VERBATIM — uncanonicalized, and never resolved: the config ladder is a
  call-site mechanism this derivation does not invoke. `domain/paths.py` learned the `#{`
  notation beside the `${` it already refused to rewrite.
- **A declaration that composes an EMPTY name derives no row.** For a catalog whose address
  is an opaque name rather than a sequence of segments (no `path_separator`), an empty
  composition is not a destination — nothing subscribes to it and nothing publishes to it —
  so the row is dropped instead of published as an endpoint addressing nothing. Two real
  shapes reached it: a member-level handler annotation outside the class-level annotation
  that would have named its destination, and a listener declaring its destination only
  through nested annotations no catalog reads yet. Segmented addresses are untouched: an
  empty segmented address is the base address itself.

### Changed

- **Endpoint identity for INBOUND `http` is now the URL the framework serves**
  (2O design §8, checkpoint CP-1 confirmed live against Boot 4.0.1).
  `@RequestMapping("users")` and `@RequestMapping("/users")` were two endpoint
  identities and are one; every combine boundary carries exactly one `/`; a
  trailing slash stays DISTINCT, because Framework 6 removed trailing-slash
  matching. A `path` holding a whole address or a placeholder-bearing
  composition (`https://${billing.host}/orders`) is untouched, and GraphQL
  (field names) and websocket/STOMP (a shared protocol with handshake-path
  rows) are out of scope. **Client-side HTTP rows are out of scope too**: a
  client's slashless path resolves against its configured base address's own
  path while a leading separator is root-relative, so canonicalizing one would
  rewrite an address rather than normalize a spelling. The rule and its gate
  live in `sextant.domain.paths`.
- **Spring Cloud Stream's `rabbit` binder now derives `amqp`, not `jms`**
  (2O design §3a). The `jms` stopgap was chosen when D00 had no AMQP member;
  keeping it would leave a Stream producer and a `@RabbitListener` consumer on
  different protocols permanently, and DR-5 gates linking on protocol equality.
- **The format ladder's rung 5 reads the evidence its documentation always
  described** (2O design §7, checkpoint CP-6). A `json_default_markers` entry
  may now be a dependency coordinate (`{coordinate: "group:artifact"}`) as well
  as a package family, and a package family is matched against every fqn the
  module names rather than annotations alone. Boot auto-configures Jackson's
  converter from the jar's mere presence, so a module carrying it answers
  `json` at `narrowed` even with no annotation anywhere.

- **Every rendered `architecture.md` now states the catalog-matching gap
  truthfully** (2O Task 12). `egress/render/document.py`'s `_GAPS` said *"every
  catalog's `detect.coordinates` is declared and read by nobody, so every
  catalog runs against every module"*. That has been false since 2O Task 6:
  the key IS read, by `application/resolve/dependencies.py`, and it skips —
  visibly, with a reason — the catalogs whose framework rule is conditional on
  the library being declared (`derived_resource` and `config_join` styles, four
  of the 55 shipped catalogs). **This changes the "what this cannot see" list of
  every document Sextant renders**, which is why it is here and not only in the
  sweep report; the `gaps` KEY in `metadata.json` is unchanged, because
  module-wide catalog activation is still unimplemented and that is what the key
  names. No endpoint row, count or identity moves.
- **`docs/components/D00-fact-schema.md`'s `protocol` list now names `amqp` and
  `pulsar`** (2O Task 12). Both have been in `domain/closed_sets.py` since Task 1
  and both are live; the schema document omitted them, which is a §5.1 violation
  rather than a schema change. `D06`'s verbless-render row gains them too. No
  code changes: the closed set is unchanged.
- **`docs/components/D02-catalog-schema.md` §2 no longer counts engines by
  counting headings** (2O Task 12). The two non-wire styles Task 8 shipped —
  `scheduled_work` and `error_advice` — have sections; the heading says "The
  styles" rather than "The thirteen styles"; and the preamble names the two
  sections that are NOT engines, `protocol_hint` (a resolve pass) and
  `filesystem` (specified, never implemented, and now carrying the
  "specified here, not yet used" box §5.3 asks for).

### Consequences of the identity migration — please read before upgrading

These four are the whole blast radius 2O design §8 names, and each is a
consequence of the same one change:

1. **Goldens moved.** Every recorded INBOUND HTTP path that omitted its
   leading separator now carries one. On this repository's own fixture that is
   no rows at all: every inbound route it declares already spelled its leading
   separator, and the two slashless declarations it has are client-side, which
   this change deliberately does not touch. A codebase with a slashless
   `@RequestMapping` will see those rows move.
2. **Curation and view overlays naming an old endpoint id are REJECTED WHOLE**
   by M01's existing rule — an overlay is validated as a unit, so one stale
   anchor rejects the file rather than silently dropping a claim. Re-anchor the
   overlay on the new id and re-apply.
3. **2N enrichment overlays anchored on old paths go STALE** and are dropped
   honestly at render (`stale_claims`) rather than rendered against a row they
   no longer name. Re-enriching is the documented remedy.
4. **`open_questions` snapshots re-derive** on the next analysis: the ledger is
   keyed on the wire identity, so a snapshot taken before this change names
   rows that no longer exist under those ids.
