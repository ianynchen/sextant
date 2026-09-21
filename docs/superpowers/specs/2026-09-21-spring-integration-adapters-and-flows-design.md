# Spring Integration adapters and flows: the destination behind a channel (register Group E)

**Status:** design. Approved in conversation 2026-09-21, section by section; scope widened by the
user from Pub/Sub alone to "Pub/Sub both directions + the AMQP container hop" and then to the
Java DSL flows ("C — which allows us to solve Kafka as well"). Self-review against the jars and
the engines is folded in (§0). Not yet planned. *(amended 2026-09-21 during implementation:
implemented on `feat/group-e-spring-integration-adapters`, Tasks 1–8 (commits `2a07658`..`e68e527`);
every place the built code differs from the section as approved carries a note like this one,
and §0d lists them all with the task that forced each.)*

**Closes:** `pubsub-channel-adapter` (the Pub/Sub row of the register — `PubSubInboundChannelAdapter`
+ `@ServiceActivator`, whose subscription is a constructor argument no engine reads) and, on
the same words, COVERAGE §5.12's boundary "the DESTINATION behind a channel" for the AMQP and
Kafka Spring Integration adapters — bean-wired and DSL-flow spellings alike. **Rides along:**
`dsl-media-route` (a Spring router route declared under a media guard alone) and
`gateway-properties-routes` (Spring Cloud Gateway routes declared in configuration).

**Rows it changes:** Pub/Sub closes (register row empty). REST inbound 3 → 1
(`conditional-controllers` stays). §5.8 gains a shipped "Spring Integration Kafka" line; §5.9 the
AMQP adapter line; §5.12 the channel-destination boundary becomes shipped for the three brokers.

Every factual claim below carries the command that produces it, or names the probe (§9) that must
record it before the key it forces is written. Claims marked **measured 2026-09-21** were verified
during the self-review. **A probe that contradicts a section here changes the section, not the
probe** (GUIDELINES §1.1).

**Standing requirements.** Nothing that works today may move (the four-lens review in §0b
removed the one pin move the conversation had approved — see A1). **No false positives** (user rule,
2026-09-20): a destination, a handler or a channel link is written only where the code states it
and the framework honours it; every ambiguity is an unresolved column, never a guess. The resolve
layer names no language (`tests/architecture/test_language_confinement.py`).

---

## 0. What the self-review found

| # | Finding | Folded in as |
|---|---|---|
| F1 | `IntegrationFlows` (the older static factory) **does not exist** in spring-integration-core 6.2.4 (`javap` → class not found); only `IntegrationFlow.from(…)` does | §5 declares `IntegrationFlow.from` alone; no alias |
| F2 | `Kafka.messageDrivenChannelAdapter` has **ten** overloads at 6.2.4; the destination is a `String[]` at slot 1 in `(ConsumerFactory, String…)`, at slot 2 in `(ConsumerFactory, ListenerMode, String…)`, a `Pattern` in two, `TopicPartitionOffset[]` in two, a `ContainerProperties` in two (whose `String…` constructor carries the topics — one producing-site hop), and a whole container in two | §6's Kafka `sources` list every overload by descriptor with `destination_arg`, `destination_via_properties` or `unresolved: true` (a `Pattern`/`TopicPartitionOffset[]` is not a topic name) |
| F3 | `BaseIntegrationFlowDefinition` declares **35** public step methods at 6.2.4 (`javap`, names: `aggregate barrier bridge channel claimCheckIn claimCheckOut controlBus convert delay enrich enrichHeaders filter fixedSubscriberChannel fluxTransform gateway handle handleReactive headerFilter intercept log nullChannel publishSubscribeChannel resequence route routeByException routeToRecipients scatterGather split splitWith to transform transformWith trigger wireTap`) *(amended 2026-09-21 during implementation: **34**, not 35 — the name list here has 34 entries and CP-27 row 2 counts 34 and confirms the names; the probe contradicts the number, so the number changes, M11)* | §5's step table classifies all 35 *(amended 2026-09-21: all 34, as 55 entries over the three owners in `catalogs/step-models/spring-integration.yml`, M11)* (D02 slice rule: every declared member is a rule, a pass-through or a divert) |
| F4 | AMQP outbound is `AmqpOutboundEndpoint(AmqpTemplate)` + `setExchangeName(String)`/`setRoutingKey(String)` (bean) and `Amqp.outboundAdapter(AmqpTemplate)` + `.exchangeName(String)`/`.routingKey(String)` (DSL) — two setters composing one address | §4/§5: `destination_setters: [exchangeName, routingKey]` joined `exchange/routingKey`, the form `spring-rabbit-template.yml` already publishes |
| F5 | `AbstractMessageListenerContainer` (spring-rabbit 3.x) declares `setQueueNames(String…)`, `addQueueNames(String…)`, `setQueues(Queue…)`; `ConsumerProperties`/`ContainerProperties` each have `(String…)`, `(Pattern)`, `(TopicPartitionOffset…)` constructors | §4's container setters include `addQueueNames`; a `Pattern` constructor → unresolved |
| F6 | Spring Cloud Gateway 5.0.0 binds its properties under **`spring.cloud.gateway.server.webflux`** (`GatewayProperties.PREFIX`, `javap -constants`); the pre-4.2 `spring.cloud.gateway.routes` is NOT that constant | §7b lists the 5.0.0 prefix; the legacy prefix is admitted only if CP-29 shows 5.0.0 still binds it |
| F7 | `PredicateDefinition(String)` splits the shortcut on the first `=` (`indexOf(61)`), tokenizes the rest on `,`, and names positional args `_genkey_N` (`NameUtils.generateName`); `RouteDefinition` carries `id`, `predicates`, `filters`, `uri`, `order`, `metadata` | §7b's grammar |
| F8 | `@Bean` declares `value()`/`name()` (both `String[]`, aliases) at spring-context 6.1.6; `@Qualifier` declares `value()` | §3's bean-name rule reads both `@Bean` attributes and `@Qualifier.value` |
| F9 | `HttpMethod.values()` at spring-web 6.1.6 is `GET HEAD POST PUT PATCH DELETE OPTIONS TRACE` (static initialiser `ldc` sequence) | recorded in CP-29; §7a does NOT use it (A1) |
| F10 | `PubSubInboundChannelAdapter(PubSubSubscriberOperations, String)` extends `MessageProducerSupport` (`setOutputChannel(MessageChannel)`, `setOutputChannelName(String)`); `PubSubMessageHandler(PubSubPublisherOperations, String)` extends `AbstractMessageHandler` with `setTopic(String)`, `setTopicExpression(Expression)`, `setTopicExpressionString(String)` — spring-cloud-gcp-pubsub 5.1.2 | §4 and §6; the two expression setters → unresolved |
| F11 | Placeholders are already resolved by the **field ladder** (`shapes/arguments.py`, `field_sources` on a catalog: a `@Value("${…}")` field/parameter or a `@ConfigurationProperties` getter becomes the `${…}` expression the row carries, substituted per environment by `resolved_peers`) — the user's "we must have resolution for placeholders" holds today for HTTP clients and holds here by reusing it | §3 |
| F12 | `config_join.gaps` files `channel_destination` questions from the `service_identity` seam **after** the pipeline's reset; fluent's rows must be visible to it | §3b: the `channel_bindings` derived table, read by `gaps` |

### 0b. The four-lens review — resolved by the author (2026-09-21)

| # | Lens | Finding | Resolution |
|---|---|---|---|
| A1 | no FP | §7a as approved in conversation declared `all_methods` on the router catalogs so a media-guarded route fans out to eight rows — and so would EVERY verb-less route on those catalogs, including `RouterFunctions.resources(…)`, whose `ResourceHandlerFunction` serves **GET, HEAD and OPTIONS only** (spring-webflux 6.1.6) — five wrong rows per static-resource route | **no `all_methods` on the router catalogs, no pin move**: the media route is a `verb: null` rule → one row, `method` NULL, `/**`, media set — exactly how `route(predicate, handler)` renders today. The conversation's "eight rows" ruling is withdrawn by this finding (§7a) |
| A2 | no FP | by-type bean resolution (rung 3) for a `MessageChannel` parameter would pick the module's single `@Bean MessageChannel` while Spring sees more candidates (Spring Integration auto-registers `errorChannel` and `nullChannel`, both `MessageChannel`s) and falls back to the parameter NAME | rungs are per reference kind: a **channel** reference resolves by `@Qualifier`, else by parameter name (a `@Bean` name or a channel name the handler index knows — Spring auto-creates a channel of that name); never by type. A **container** reference (a catalog `containers` type, which no framework bean shares) resolves by `@Qualifier`, else unique type, else name — Spring's own order (§3) |
| A3 | no FP | AMQP outbound with one of `setExchangeName`/`setRoutingKey` unset was to keep an empty half; the framework fills an unset half from the `RabbitTemplate`'s own defaults (`setExchange`/`setRoutingKey` on the template bean) | an unset half → `path` unresolved (§4) |
| A4 | no FP | `channel` steps were described as ending the flow "for this row's purposes"; a flow may continue after `.channel("x")` (a bridge) and a later `.handle(h)` is a handler too | the link is recorded and the walk continues (§5) |
| A5 | over-eng. | following `to(IntegrationFlow)` into the target flow through bean rules | `to` is a `divert` (handler unresolved); `trigger`, `controlBus` likewise; `nullChannel` is its own kind `discard` (no handler — TRUE, not unresolved); `fixedSubscriberChannel()` no-arg is pass-through, the `(String)` form a `channel` |
| A6 | conflict | a catalog carries one `style`; §7b hedged between adding `indexed_routes` to the combinator Gateway catalog and a sibling | a sibling `spring-cloud-gateway-properties.yml` (`config_join`), emitting inbound and outbound rows per rule — `config_join` already carries `direction` per rule (`_row(catalog, protocol, channel.direction, …)`) |
| A7 | consistency | properties routes with no `Method=` were to fan out through `all_methods`; the DSL Gateway catalog renders a method-less route with `method` NULL | properties routes render the same: `method` NULL, resolved — one family, one rendering |
| A8 | future languages | the keys describe DI registrations by name and type (`new:` roots, `bean_via`, `channel_link`), which .NET's container has too; no language word reaches the engine | kept |

### 0c. First-principles and adversarial review (user request, 2026-09-21)

| # | Finding | Resolution |
|---|---|---|
| B1 | Bean identity — "a value built in one `@Bean` method, injected into another" — is the shape behind several EXISTING boundaries (the field-held `Publisher`, `WebClient`, `KafkaTemplate` gaps), not this feature's private need | `resolve/beans.py`, a shared fold with a narrow API; this spec is its first consumer, the field ladder's bean rung a named follow-up (§3a) |
| B2 | "adapters + channel links" is a special case of "a registration object wired to a consumer" — raw listener containers (`DefaultMessageListenerContainer.setDestinationName` + `setMessageListener`, Kafka's `ConcurrentMessageListenerContainer`) are the same walk | the vocabulary is capture KINDS (`channel`, `channel_link`, `handler`), not framework words; a listener container is one more catalog on the same keys (§4) |
| B3 | `channel_destinations` + a `gaps` skip patched two engines together; the general object is the channel EDGE | `channel_bindings(channel, role fed_by/read_by/sends_to, …)`: fluent writes `fed_by`, `config_join` writes `read_by`, a join pass mints rows, `gaps` asks only about unfed channels; `sends_to` is the slot for later writers (§3b) *(amended 2026-09-21 during implementation: `sends_to` has its first writer — fluent writes it for a `channel_link` captured AFTER a handler, that handler's output channel (Task 4–5 fix round, `059342a`, M4); it still has no reader)* |
| B4 | the flow walk and the bean-wired walk are BOTH "walk forward from a root along result→receiver, capture from arguments, join argument chains" — `fluent`'s definition; a second walker would drift | **ruled by the user: extend `fluent`** — one root kind, one continuation kind, three capture kinds, one step effect, inbound rows (§2, §4, §5); no new engine |
| B5 | adversarial: `@Profile`-conditional twin beans; a spec configurer adding queues (`configureContainer(c -> c.addQueueNames(…))`); Gateway `filters` rewriting the upstream path; a link set in a different method; `${…}` channel names | the first shares `conditional-controllers`' exposure and is stated with it; the second and fourth are misses, stated; the third matches the DSL outbound catalog's rendering, stated; the fifth is resolved through `_agreed` before the join (§3b) *(amended 2026-09-21 during implementation: each of the five is now also an open issue in `docs/open-issues.md` — `OI-108` (`@Profile` twins), `OI-109` (`configureContainer` queue additions), `OI-111` (Gateway `filters`), the "different method" link a stated boundary on each catalog, `OI-114` (`${key:default}` in a channel name never applies the default) — so a reader looking for the exposure finds it in the register, not only here)* |

**Two rulings the plan made on the spec's words, recorded here (2026-09-21, plan
self-review; carried into §2, §5 and §6 as amendment notes):** (1) the spec's `new: <type>`
root is the EXISTING `{owner: <type>, method: <init>}` form — no sugar was added, and a
constructor root names `<init>` in `terminal:` to be its own terminal (Task 3's carry);
(2) there is no separate `sinks:` word — a sink is a root whose continuation is the flow
(`via_argument_of: {owner, method: handle}, continue: true`), so the §5 sketch's `sinks:`
block is the `roots:` list.

### 0d. Amended during implementation

Every sentence the implementation changed carries an inline note; this table is the index
(GUIDELINES §1.1: a probe or a measured fact that contradicts the spec changes the spec).

| # | Section | Amendment | Forced by |
|---|---|---|---|
| M1 | §2, §4, §6 | Fluent's words as BUILT: a root is `{owner, method: <init>}` (no `new:` sugar) and names `<init>` in `terminal:`; roots and steps match by `descriptor:` (parameter types only) where a name has overloads; captures `channel`/`channel_link`/`channel_source`/`handler` read `argN`, `none` (handler only) or `{bean_via: argN}`; `poisons:` is STICKY; `compose:`; `undeclared_steps:`; `beans:`; `method_annotation:`; a terminal entry's `terminal_via_argument … continue: true` and a root's or step's `via_argument_of {owner, method}, continue: true` are the continuation (no `continue_via_argument` key, no `sinks:` word); `channel_via` accepts `method: <init>` with a `descriptor`; `field_sources` on every broker catalog; `bean_model`/`step_model` loaded like `shape_model` | Tasks 3–6 (`2789c20`, `fafeef8`, `d5a3d4a`, `059342a`, `c4b0d36`); plan rulings (1), (2) above |
| M2 | §3a | `channel_types` is the model's list of channel INTERFACES (`MessageChannel`, `SubscribableChannel`, `PollableChannel`), exact membership — not "or a subtype": a parameter declared as a concrete channel class has no framework bean beside the module's own and IS unique by type | Task 1 fix round (`2ef49fc`) |
| M3 | §3b | `read_by` is written by `config_join` from its channel index with `${…}` names resolved through `_agreed`; readers are deduped in the mint pass (one row however many catalogs wrote the reader); `gaps` skips on a `fed_by` of ANY direction; the channels catalog (`spring-integration.yml`) runs FIRST in the engine loop — order-dependent by construction; a channels catalog that also declares a `key` is a stated boundary | Task 2 (`e330c48`, `4b8719c`), Task 4–5 (`fafeef8`), Task 6 fix round (`c100aab`) |
| M4 | §3b, §5 | A `channel_link` BEFORE any handler is the wire's feed — `fed_by`, and the chain writes NO row (the join pass owns rows for linked registrations, so a linked adapter is never counted twice); a `channel_link` AFTER a handler is that handler's OUTPUT channel — `sends_to`, the row kept with that handler; `.channel("x").handle(h)` writes `fed_by(x)` and `read_by(x, h)` and the join mints the row | Task 3 (`2789c20`), Task 4–5 fix round (`059342a`) |
| M5 | §4 | The container hop resolves the collected destination to an ADDRESS in the container bean's OWN method (value ids are per method); `addQueueNames` is last-wins (no `collects` on a destination — an under-report, stated); `setTopicExpression(e); setTopic("t")` derives unresolved (sticky poisons — a miss, stated on the catalog); an unset AMQP half → unresolved (A3 stands) | Task 3 (`2789c20`), Task 4–5 fix round (`059342a`), Task 6 (`c4b0d36`) |
| M6 | §5 | A channel-sourced flow uses a new capture `channel_source` (not `direction: outbound` on `from(String)`): a sink's wire captured → the outbound row + an outbound `fed_by` for the source; a handler only → `read_by`; neither → nothing (a bridge, a stated boundary); the `from(String)`/`from(MessageChannel)` roots live in ALL THREE broker catalogs; flow-step entries carry `owner` (only owned steps fold backward into a continuation's prefix); a value-returning call on the bean before its last setter forks the chain (boundary); `IntegrationFlow.from(<adapter bean>)` is NOT declared — a stated boundary and `OI-112` | Task 4–5 fix round (`059342a`), Task 6 (`c4b0d36`, `c100aab`) |
| M7 | §7a | The servlet media row folds its enclosing nest: the fixture's `accept(APPLICATION_JSON) { }` sits inside `"/ktmvc".nest { }`, so its row is `/ktmvc/**`, not `/**` | Task 7 (`c093f8d`) |
| M8 | §7b | Outbound property rows mirror the DSL outbound catalog: the URI VERBATIM as `path`, `peer` NULL (the "peer `orders`" parenthetical was wrong); a fifteenth predicate `Version` exists at 5.0.0 and is left unknown → unresolved; the map form's field is `args.patterns` (measured); gather predicates collect EVERY `args` value (CP-29 row 7: `ShortcutType.normalize` ignores keys); the `list_tail_flag` is found by VALUE because `resolved_config` carries no declaration order (`OI-113`); a gather left EMPTY after flag removal is unread (`Path=true`, `Method=`); items collapsing to one address INTERSECT their requirements and any unresolved alternative makes the row unresolved; an unresolved-everywhere key renders unresolved while only TRUE divergence drops the item's rows (one `environment_divergence` question, filed from `config_join.gaps`); a NULL-path row carries no requirements; the comma-scalar → unread rule applies to verbs only | Task 8 (`91ace03`) and its three fix rounds (`dc07300`, `b98bba0`, `e68e527`) |
| M9 | §6 | `steps_from: spring-integration` is spelled `step_model: spring-integration`; the loader MERGES the model's `steps` and `undeclared_steps` into the catalog's `matches` (no `Catalog.step_model` field — nothing else would read it); the Pub/Sub catalog names the model too (for its channel-sourced `from` roots) | Task 6 (`c4b0d36`, `c100aab`) |
| M10 | §11 | The `.transform(…)` pass-through sits on the AMQP DSL flow in the fixture (`Shape5Flows`), not the Kafka one; the Gateway fixture's map form spells `args.patterns`; the fixture files are `Shape4PubSub.java`, `Shape5Flows.java` and `fixtures/orders-gateway/src/main/resources/application.yml` | Task 6 (`2bbd0b4`), Task 8 (`91ace03`) |
| M11 | §0 F3, §5 | 34 flow-definition members, not 35 (CP-27 row 2) | Task 6 (`2bbd0b4`) |
| M12 | §6, §12 | D00 carries no fact change; D01 gains `channel_bindings` with `resolution` role-dependent (the wire's on `fed_by`, the NAME's on `read_by`); the fluent parameter rung (`@Value` on the method's own parameter) now answers in fluent for every fluent catalog | Task 6 (`c4b0d36`, `c100aab`), Task 9 |

---

## 1. What is wrong today, in three places

1. **The destination behind a channel is unread.** `spring-integration.yml` (`config_join`) indexes
   `@ServiceActivator(inputChannel=…)` and its six sibling annotations, and — because Spring
   Integration has no configuration key for a channel's destination — files one
   `channel_destination` question per handler (`engines/config_join.py::gaps`). The destination
   IS in the facts: a constructor argument (`new PubSubInboundChannelAdapter(t, "sub")`), a
   container setter (`container.setQueueNames("q")` — a 9.15 `array` argument,
   `scripts/probes/spring-integration-destinations.md`), or a DSL factory argument
   (`Kafka.messageDrivenChannelAdapter(cf, "topic")`). No engine joins it to the channel.
   COVERAGE §5.11 tiers the Pub/Sub adapter B; §5.12 states the boundary for AMQP and Kafka.
2. **Java DSL flows derive nothing** (§5.12: "the DSL chain is FULLY recorded" as a boundary).
   `fixtures/spring-integration-probe/.../Shape3PolledAndOtherBrokers.java` has had a Kafka
   inbound flow and a Kafka outbound flow since the probe.
3. **Two REST leftovers.** `accept(MediaType…, Function1)` / `contentType(…)` on the router DSLs
   derive one unresolved row (`combinator._carries_a_handler`); Gateway routes declared in
   `application.yml` derive nothing (`gateway-properties-routes`).

---

## 2. Approach — extend `fluent`; bean identity as a shared fold; the channel as a table

Weighed in conversation: (A) a `bean_wiring:` block inside `config_join`; (B) a new style for
bean-wired adapters; (C) also the DSL flows. **C was ruled.** The first-principles review (§0c)
then asked what the walk IS: a value constructed at a root, configured along a receiver chain,
its address captured from arguments, and consumers attached by further calls — which is the
`fluent` engine's own definition, already with argument-chain joins (`terminal_via_argument`),
lambda-body captures (`lambda_steps`), destination-via-producing-call (`channel_via`) and the
field ladder. **Ruled (user, 2026-09-21): extend `fluent`; no new engine.** The broker catalogs
are `style: fluent`. Three general additions carry the whole feature:

| Piece | Exists as | Added here |
|---|---|---|
| walk forward from a root along `result → receiver`, folding captures | `fluent._walk` | a **constructor root** (`new: <type>`) beside the call roots *(amended 2026-09-21 during implementation: spelled `{owner: <type>, method: <init>}` — the existing form, no sugar — with `<init>` named in `terminal:`; and a VOID call on the constructed value folds into its chain (setters), only a value-producing call forks — Task 3's ruling, proven inert for every shipped fluent catalog, M1)* |
| a value built by one chain consumed as another call's argument | `terminal_via_argument` (the join ends the chain) | **`continue_via_argument`**: the consuming call's own chain continues the walk with the same captures (`from(<spec>) … .handle(h)`) *(amended 2026-09-21 during implementation: spelled `continue: true` beside `terminal_via_argument` on a terminal entry, or `via_argument_of: {owner, method}, continue: true` on a root or step; the consumer IS the terminal, M1)* |
| an argument that is a bean built elsewhere | — | **`resolve/beans.py`** (§3), and the capture kind **`bean_via`**: fold the captures of that bean's own construction chain |
| the consumer attached to the chain | — (rows carry `caller`; `handler` NULL) | capture kinds **`handler`** (a lambda body or a bean's method) and **`channel_link`** (a channel name or channel bean); a **`poisons:`** step effect (a `divert` poisons `handler`); an inbound row carries `handler` *(amended 2026-09-21 during implementation: a third channel-naming kind, **`channel_source`** — the channel a flow CONSUMES (`from("ch")`), M6; `handler` reads a lambda's body symbol only — a bean's method is NULL, resolved, M1)* |
| a channel named on the constructing method's annotation | — | root option `method_annotation: { annotation, arg, into }` |
| the channel edge between an adapter and its consumer | `config_join` files a question per `read_by` | **`channel_bindings`** (§3): `fed_by` rows from fluent, `read_by` from the channel index; a join pass mints rows and `gaps` asks only about unfed channels |
| placeholders | the field ladder (`field_sources`) | reused unchanged (F11) |

Units:

| # | Unit | Where |
|---|---|---|
| 1 | `resolve/beans.py` — bean table and resolution rungs | new module (§3) |
| 2 | `channel_bindings` table; `read_by` from `config_join`'s index; join pass; `gaps` reads it | `config_join.py`, new `resolve/channel_bindings.py`, SQL (§3) |
| 3 | fluent: `new:` roots, `continue_via_argument`, `bean_via`, `handler`, `channel_link`, `poisons`, `method_annotation`, inbound rows *(amended 2026-09-21: as built — `<init>` roots, `via_argument_of … continue: true`, `bean_via`, `beans:`, `handler`, `channel_link`, `channel_source`, `poisons`, `compose`, `undeclared_steps`, `method_annotation`, root/step `descriptor:`, per-root `direction:`, M1)* | `engines/fluent.py` (§4–§5) |
| 4 | three broker catalogs + `flows.steps` on `spring-integration.yml` | `catalogs/` (§6) |
| 5 | `dsl-media-route` — `verb: null` rules on the media overloads | router catalogs (§7a) |
| 6 | `gateway-properties-routes` — `indexed:` address form in `config_join` | `config_join.py`, `spring-cloud-gateway-properties.yml` (§7b) |
| 7 | probes CP-27..29, fixtures, register, COVERAGE, D02 | §9, §11, §12 |

---

## 3. Bean identity, the channel table, and the rows

### 3a. `resolve/beans.py` — a shared fold

One `once` fold over the annotation index and `method_declarations`: every `@Bean` method of the
module (name from `name()`/`value()` else the method name — F8; erased return type; `@Profile`/
conditional annotations recorded but not evaluated), every `@Qualifier` on a parameter. API:
`bean_of(reference) → BeanRef(method symbol) | Unresolved(reason)` where a reference is an
injected parameter of a `@Bean` method (or any method — the fold is engine-neutral) or a direct
call to a `@Bean` method of the same class. Rungs depend on WHAT is referenced (§0b A2):

- a **channel** reference (erased type `MessageChannel` or a subtype) *(amended 2026-09-21
  during implementation: erased type IN the model's `channel_types` list, exact membership — the
  channel INTERFACES `MessageChannel`, `SubscribableChannel`, `PollableChannel`, which the
  framework's own `errorChannel`/`nullChannel` implement; a parameter declared as a concrete
  channel CLASS (`DirectChannel`) has no framework bean beside the module's own and IS Spring's
  unique candidate by type, so it takes the other kind's rungs; `bean-models/spring.yml`, M2)*:
  `@Qualifier` → the
  parameter's declared name, when it is a `@Bean` name OR a channel name the channel index knows
  (Spring auto-creates a channel under a referenced name and resolves an ambiguous `MessageChannel`
  injection by parameter name — `errorChannel`/`nullChannel` are always candidates); never by type;
- any **other** reference (a catalog-declared registration or container type — nothing a
  framework bean shares): `@Qualifier` → exactly one `@Bean` method of that erased type → the
  parameter's name — Spring's own order (`DefaultListableBeanFactory.determineAutowireCandidate`,
  CP-27).

No rung answers, or a rung has two candidates → `Unresolved`. A parameter compiled without
`-parameters` skips the name rung. **This module is the general answer to "a value built in one
`@Bean` method and used in another"** — the field ladder's missing rung for the field-held
`Publisher`/`WebClient`/`KafkaTemplate` boundaries in COVERAGE. It is built here and consumed by
fluent's `bean_via`; adding it as a ladder rung is a named follow-up, not part of this spec.
*(amended 2026-09-21 during implementation: the follow-up is `OI-106`; the "channel name the
channel index knows" rung reads the RESOLVED `read_by` names off `channel_bindings` — not the
index's raw spelling — which is why the channels catalog runs first, §3b, M3.)*

### 3b. `channel_bindings` — the channel edge as data

A derived temp table `channel_bindings(channel, role, symbol, protocol, destination, direction,
catalog_id, resolution)`, reset with the endpoint tables:

- `fed_by` — written by fluent when a chain captured `channel_link` (an adapter or flow feeding
  the channel): `symbol` = the constructing method, `destination` = the captured address (through
  the ladder; may be a `${…}` expression or unresolved), `protocol` = the catalog's;
- `read_by` — written by `config_join` from the index it already builds (`_channels`): the
  handler and the direction the annotation means; a channel name spelled `${…}` is first resolved
  through `_agreed` (the fixture's `@ServiceActivator(inputChannel = "${probe.audit-channel}")`
  now joins);
- `sends_to` — no writer in this spec; the slot where `@MessagingGateway` and `channel.send(…)`
  land later. *(amended 2026-09-21 during implementation: one writer — fluent, for a
  `channel_link` captured AFTER a handler: that handler's output channel, `symbol` the handler,
  `destination` NULL; the row keeps that handler. No reader yet, `OI-107`. M4)*

*(amended 2026-09-21 during implementation, M3: `read_by` is written INSIDE `config_join`'s one
channel walk (`_derive_channels`), `${…}` names resolved through `_agreed` with the family's
placeholder delimiters — a name configuration never answered stays as written, `unresolved`, and
joins nothing; `resolution` on the edge is therefore the NAME's on `read_by` and the WIRE's on
`fed_by` (the edge stands in for the row the chain would have written). The mint pass keys readers
per channel so one reader written by several catalogs mints one row. `gaps` skips a channel any
`fed_by` names, whatever its direction. And the channels catalog — a `config_join` file whose whole
effect on the loop is the `read_by` end: annotation-valued binding, no `key`, no media block —
runs FIRST in the engine loop (`resolve/endpoints.py`, `config_join.writes_only_the_channel_edge`),
because fluent's name rung reads those names in the same loop; a channels catalog that ALSO
declares a `key` keeps the style's last turn and its names reach no engine that ran before it — a
stated boundary with no shipped instance.)*

`resolve/channel_bindings.py` joins `fed_by ⋈ read_by` on `channel` and mints one endpoint row per
pair: inbound, `protocol`/`destination` from the feeder, `handler` = the reader, `caller` = the
feeder's method. A `fed_by` with no reader still has its adapter row (the adapter exists — the
chain derived it with `handler` NULL) *(amended 2026-09-21 during implementation: the JOIN PASS
mints that row too — a chain that captured a resolved `channel_link` before any handler writes the
edge and NO row of its own, so a linked adapter is never counted twice; the pass mints one row per
reader, or one with `handler` NULL for a feeder nobody reads, M4)*; a `read_by` with no feeder keeps its `channel_destination`
question — `config_join.gaps` asks only for those. Outbound handler beans (`@ServiceActivator` on
the `@Bean` method that builds a `PubSubMessageHandler`) write a `fed_by`-shaped row with
`direction: outbound` so the question is not asked, and derive their outbound row in the chain.

### 3c. Rows

Inbound: `protocol` from the catalog, `path` = destination, `handler` = the consumer (a lambda
body — class-compiled lambdas already arrive as `lambda`; a bean's method; or the channel's
reader), `caller` = the constructing/flow method, `evidence: compiler`, shapes NULL (a channel
handler's signature is the framework's convention — `_derive_channels`' own statement). Outbound:
`path` = topic / `exchange/routingKey`, `caller` = the method, `handler` NULL. **Destinations go
through the field ladder** (`field_sources` on each catalog as `spring-resttemplate.yml`): a
literal; a `@Value("${…}")` field/parameter or properties getter → the `${…}` expression,
substituted per environment by `resolved_peers`; a vararg `array` → one row per element; anything
else → `path` unresolved. A declared registration always derives a row.

---

## 4. Entry shape 1 — the bean-wired registration

```yaml
# spring-integration-pubsub.yml — style: fluent, protocol: pubsub, direction: inbound
matches:
  roots:
    - { new: com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter,   # (PubSubSubscriberOperations, String) — F10
        captures: { channel: arg1 } }
    - { new: com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler,         # (PubSubPublisherOperations, String)
        captures: { channel: arg1 }, direction: outbound,
        method_annotation: { annotation: org.springframework.integration.annotation.ServiceActivator, arg: inputChannel, into: channel_link } }
  steps:
    - { method: setOutputChannelName, captures: { channel_link: arg0 } }                       # MessageProducerSupport — F10
    - { method: setOutputChannel,     captures: { channel_link: { bean_via: arg0 } } }
    - { method: setTopic,             captures: { channel: arg0 } }                            # last wins — Spring setter semantics
    - { method: setTopicExpression,       poisons: [channel] }                                  # a function is not a literal
    - { method: setTopicExpressionString, poisons: [channel] }
  field_sources: { value_annotation: org.springframework.beans.factory.annotation.Value,
                   properties_annotation: org.springframework.boot.context.properties.ConfigurationProperties,
                   prefix_from: prefix, getter_prefixes: [get, is] }
```

*(amended 2026-09-21 during implementation, M1: the two YAML sketches above and in the container
hop below are the design's shorthand; as built in `catalogs/spring-integration-pubsub.yml` and
`spring-integration-amqp.yml` a root is `{owner: <type>, method: <init>, descriptor: "(…)V",
captures: …}`, the catalog names `terminal: ["<init>", get]`, every step carries the `owner` javac
names at the call site (the adapter's own class for the inherited setters, CP-28 row 1; both the
concrete and the abstract owner where a library declares a setter on one and code calls it on the
other, CP-27 rows 9, 10, 12), `addQueueNames` is `captures: {channel: arg0}` (last-wins; no
`collects` on a destination — the under-report is stated on the catalog, M5), and each catalog
declares `bean_model: spring`, `step_model: spring-integration` and `shape_model: json`.)*

- **`new:` root** — the chain starts at an `<init>` site of the type; `arg0…` are the
  constructor's arguments (the receiver slot is not an argument). The chain is the value's later
  calls (`result → receiver`, as today). A root may carry `direction:` to override the catalog's
  for that registration (the outbound handler in an inbound catalog). *(amended 2026-09-21 during
  implementation: the later calls are VOID setters on one value, which the walk used to read as a
  fork per sibling; a void call now folds into the chain and only a value-producing call forks —
  so a value-returning call on the bean BEFORE its last setter forks the chain and the later
  setters are lost, a stated boundary, M1.)*
- **`channel_link: arg0`** — a string literal is the channel name; **`{ bean_via: arg0 }`** — the
  argument is a bean reference (a `@Bean` method call in the class, or an injected parameter) →
  `beans.py` → the channel's bean name. Unresolved → the row derives with `handler` NULL, no
  `fed_by` written (a channel we cannot name is not a channel we can bind).
- **`method_annotation`** — on a root: the constructing method's own annotation supplies a
  capture (`@ServiceActivator(inputChannel)` → `channel_link`, direction outbound).
- **`poisons: [field]`** on a step — the capture is marked unreadable from here on; for
  `channel` the row is unresolved on `path`. *(amended 2026-09-21 during implementation: STICKY
  — a later capture does not lift a catalog poison, the no-false-positive direction, so
  `setTopicExpression(e); setTopic("t")` derives `unresolved`, not `t` — a miss, stated on the
  catalog and logged as `OI-120`, M5. An UNRESOLVED bean reference is not a poison: it is that
  setter's own read failure and a later literal overrides it, Spring's setter semantics.)*

The container hop (AMQP), same words:

```yaml
# spring-integration-amqp.yml — style: fluent, protocol: amqp, direction: inbound
matches:
  roots:
    - { new: org.springframework.integration.amqp.inbound.AmqpInboundChannelAdapter,
        captures: { channel: { bean_via: arg0 } } }                        # the container BEAN's own chain supplies `channel`
    - { new: org.springframework.integration.amqp.outbound.AmqpOutboundEndpoint, direction: outbound,
        captures: {}, compose: { channel: [exchange, routing_key], join: "/" },
        method_annotation: { annotation: org.springframework.integration.annotation.ServiceActivator, arg: inputChannel, into: channel_link } }
  beans:                                                                    # chains `bean_via` may fold from — rooted at THEIR constructors
    - { new: org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer, captures: {} }
    - { new: org.springframework.amqp.rabbit.listener.DirectMessageListenerContainer, captures: {} }
  steps:
    - { method: setQueueNames, captures: { channel: arg0 } }                # String… → one row per element (9.15 arrays)
    - { method: addQueueNames, collects: { channel: arg0 } }
    - { method: setQueues,     captures: { channel: { channel_via: [{ owner: org.springframework.amqp.core.Queue, method: <init>, arg: 0 }] } } }
    - { method: setExchangeName, captures: { exchange: arg0 } }
    - { method: setRoutingKey,   captures: { routing_key: arg0 } }
    - { method: setOutputChannelName, captures: { channel_link: arg0 } }
    - { method: setOutputChannel,     captures: { channel_link: { bean_via: arg0 } } }
```

`bean_via` on a `captures.channel` value means: resolve the argument as a bean; find that bean's
`@Bean` method; walk ITS chain from the matching `beans:` root and fold the captures it produced
into this chain (one hop; a container built in a third bean is `Unresolved`). *(amended 2026-09-21
during implementation, M5: the fold hands over an ADDRESS, not a raw argument — the container
chain's `channel` is read in the container method's own context (the field ladder, the array
read, the `Queue` `channel_via` against THAT method's sites) because value ids are per method and
a cross-method `source` read is a fabrication path; every chain end must agree or the field is
`unresolved`; a `bean_via` met inside the container's chain is a poison there. Two-hop container
sources are `OI-110`.)* `compose:` builds
one field from two captured halves in order; a half never captured leaves `channel` unresolved
(§0b A3 — the framework fills it from the `RabbitTemplate`'s defaults, which the walk does not
read). `channel_via` on the `Queue` constructor is the existing word (`TopicName.of(p, t)` uses it).

**Boundaries stated:** a registration built outside a `@Bean` method or through a factory method;
a link set in a different method than the construction (`@PostConstruct`, a second `@Bean` taking
the adapter); `setOutputChannel(new DirectChannel())` (anonymous — the destination row derives, no
`fed_by`); XML beans.

---

## 5. Entry shape 2 — the DSL flow

```yaml
# spring-integration-kafka.yml — style: fluent, protocol: kafka, direction: inbound
matches:
  roots:                                          # the SOURCE spec chains — every overload declared (F2, D02 slice rule)
    - { owner: org.springframework.integration.kafka.dsl.Kafka, method: messageDrivenChannelAdapter,
        descriptor: "(Lorg/springframework/kafka/core/ConsumerFactory;[Ljava/lang/String;)…", captures: { channel: arg1 } }
    - { …, descriptor: "(…ConsumerFactory;…ListenerMode;[Ljava/lang/String;)…", captures: { channel: arg2 } }
    - { …, descriptor: "(…ConsumerFactory;…ContainerProperties;)…",
        captures: { channel: { channel_via: [{ owner: org.springframework.kafka.listener.ContainerProperties, method: <init>, descriptor: "([Ljava/lang/String;)V", arg: 0 }] } } }
    - { …, descriptor: "(…ConsumerFactory;Ljava/util/regex/Pattern;)…", captures: { channel: unresolved } }          # a Pattern is not a topic
    - …  # the TopicPartitionOffset[], container and ListenerMode twins likewise (ten in all)
    - { owner: …Kafka, method: inboundChannelAdapter, descriptor: "(…ConsumerFactory;…ConsumerProperties;)…",
        captures: { channel: { channel_via: [{ owner: org.springframework.kafka.listener.ConsumerProperties, method: <init>, descriptor: "([Ljava/lang/String;)V", arg: 0 }] } } }   # polled; + 3 siblings
    - { owner: org.springframework.integration.dsl.IntegrationFlow, method: from, descriptor: "(Ljava/lang/String;)…",
        captures: { channel_link: arg0 }, direction: outbound }            # an OUTBOUND flow reads a channel …
    - { owner: …IntegrationFlow, method: from, descriptor: "(Lorg/springframework/messaging/MessageChannel;)…",
        captures: { channel_link: { bean_via: arg0 } }, direction: outbound }
  terminal:
    - { method: build, continue_via_argument: { owner: org.springframework.integration.dsl.IntegrationFlow, method: from } }   # spec → from(spec) → the flow chain continues
  sinks:                                          # `handle(<sink spec>)` — the spec chain's own captures
    - { owner: org.springframework.integration.kafka.dsl.Kafka, method: outboundChannelAdapter, captures: {} }
    - { method: topic, captures: { channel: arg0 } }                       # `.topic(Function)` → poisons
```

*(amended 2026-09-21 during implementation, M1/M6: the sketch above is the design's shorthand. As
built in `catalogs/spring-integration-kafka.yml`: the ten `messageDrivenChannelAdapter` and four
`inboundChannelAdapter` roots each carry their full `descriptor:` and `via_argument_of: {owner:
IntegrationFlow, method: from}, continue: true` — there is no `terminal: build` join, the `from`
call is the consumer; a `Pattern`/`TopicPartitionOffset[]`/container root captures the slot the
destination sits in (fluent refuses a literal `unresolved` capture) and a non-string slot reads to
nothing, so the row is `unresolved`; `from(String)` is `captures: {channel_source: arg0}` and
`from(MessageChannel)` `{channel_source: {bean_via: arg0}}`, with NO `direction: outbound` — what
the chain then captures decides the row (below); there is no `sinks:` block — `Kafka.outboundChannelAdapter`
is a root with `direction: outbound` and `via_argument_of: {owner: [IntegrationFlowDefinition,
BaseIntegrationFlowDefinition, IntegrationFlowBuilder], method: handle}, continue: true`, and
`topic(String)`/`topic(Function)`/`topicExpression` are its steps (`channel: arg0`; poisons);
`terminal: [get]`.)*

- **`continue_via_argument`** — the spec chain reaches `IntegrationFlow.from(spec)`: instead of
  ending there (`terminal_via_argument`), the walk continues along `from(…)`'s own result chain with
  the same captures. (A source spec is consumed by `from` directly, without `build()` — the
  terminal is the `from` call itself, so the entry is `{ via_argument_of: { owner: IntegrationFlow,
  method: from }, continue: true }`; the plan spells one form.) *(amended 2026-09-21 during
  implementation: that one form is what was built — on a root or a step, `via_argument_of {owner,
  method}` with `continue: true` required; on a `terminal:` entry, `terminal_via_argument: {owner,
  method}` with `continue: true`, a bare `true` refused. The continuation is tested at every row
  the walk reaches; the consumer's pre-root prefix folds first (roots included, so `from("ch")`
  before `handle(sink)` is seen), the handed-on captures on top, then the consumer's own step, and
  the consumer IS the terminal. Spec statements before `from(spec)` that are not chained onto the
  spec are not folded — a stated boundary. M1)*
- **Steps** — declared once on `spring-integration.yml` under `flows.steps`, imported by the three
  broker catalogs (the flow definition is core's — F3, all 35) *(amended 2026-09-21 during
  implementation, M9/M11: declared once in `catalogs/step-models/spring-integration.yml` — a
  model file, not a block on the channels catalog — named by each broker catalog as
  `step_model: spring-integration` and MERGED into its `matches` by the loader; 55 entries over
  the 34 names, every entry carrying `owner` (the three types javac names at a flow's call sites,
  CP-27 row 16 — only an owned step folds backward into a sink's continuation) and `handle`/
  `channel` keyed by `descriptor` (the handler sits at slot 0 or 1 by overload, CP-27 rows 3, 3b))*:

| Kind | Members | Effect |
|---|---|---|
| `pass_through` | `aggregate barrier bridge claimCheckIn claimCheckOut convert delay enrich enrichHeaders filter fluxTransform headerFilter intercept log resequence split splitWith transform transformWith wireTap`, `fixedSubscriberChannel()` (no-arg) | no captures |
| `channel_link` | `channel(String)`, `channel(MessageChannel)` (`bean_via`), `channel(MessageChannelSpec)` (its `id`), `fixedSubscriberChannel(String)` | captures `channel_link`; **the walk continues** (§0b A4) |
| `handler` | `handle(GenericHandler)`, `handle(Class, GenericHandler)`, `handle(MessageHandler)`, `handle(Object, String)`, `handleReactive` | captures `handler` from the lambda argument (its body symbol) or the bean + method name; `handle(MessageHandlerSpec)` → the `sinks` chain's captures fold in (an OUTBOUND row) |
| `discard` | `nullChannel` | `handler` NULL is the TRUE answer; the row is resolved |
| `divert` | `route routeByException routeToRecipients gateway scatterGather publishSubscribeChannel controlBus trigger to` | `poisons: [handler]` — the message may leave the linear flow (§0b A5) |

An undeclared member is `divert`. `get()` and the builder return end the chain. A flow whose source
is a channel (`from(String)`) and whose handler is a `sinks` spec derives the **outbound** row
(`caller` = the flow method) and a `fed_by` row with `direction: outbound`; a channel-sourced flow
with an inline handler is a channel consumer, not a wire — it writes `read_by` (handler = the
lambda body) so the inbound adapter feeding that channel gains it as a handler through the join.
*(amended 2026-09-21 during implementation, M6: this is the `channel_source` capture's rule as
built — a sink's wire captured → the outbound row plus an outbound `fed_by` for the source;
a handler and no wire → `read_by(source, handler)` and no row; neither → nothing, the bridge
form, a stated boundary. `.channel("x").handle(h)` on a WIRE-sourced flow writes `fed_by(x)`
and `read_by(x, h)`, no row of its own, and the join mints the row naming both beside any
`@ServiceActivator(inputChannel = "x")`; `handle(h).channel("y")` keeps the row with `h` and
writes `sends_to(y, h)`, M4. `channel_link` is a last-wins slot: `.channel("x").handle(h).channel("y")`
loses `fed_by(x)` — `OI-115`.)*

The AMQP DSL twin: `Amqp.inboundAdapter(ConnectionFactory, String…)` `captures: { channel: arg1 }`;
`(ConnectionFactory, Queue…)` through the `Queue` `channel_via`; `(SimpleMessageListenerContainer)`
/ `(DirectMessageListenerContainer)` through `bean_via`; `Amqp.outboundAdapter(AmqpTemplate)` as a
sink with `exchangeName`/`routingKey` steps and `compose`. Pub/Sub: `from(<bean>)` resolves through
`bean_via` to the §4 root's captures. *(amended 2026-09-21 during implementation, M6: the last
sentence is NOT built. `IntegrationFlow.from(MessageProducerSupport)` is the one `from` overload
every broker's adapter satisfies (CP-28 row 2), and a root matched by descriptor cannot tell whose
adapter arrived — an AMQP adapter bean handed to a root declared in the Pub/Sub catalog would
derive an unresolved row under `protocol: pubsub`, a wrong row. Stated as a boundary on the
catalog; the general fix — derive only when `bean_via` resolved to a `beans:` root of THIS catalog
— is `OI-112`. The `from(String)`/`from(MessageChannel)` roots live in all THREE broker catalogs,
and the mint pass dedupes the reader each one writes. A `Queue…` varargs slot is one array whose
elements each carry their own constructor; `linked_channels` walks the elements, one queue per
element, an element built by anything but a `Queue` constructor its own unresolved row.)*

**Boundaries stated:** the lambda flow form (`return f -> f.handle(…)`; implicit `<beanName>.input`);
`from(Supplier)`/`from(MessageSource)`; two-hop container sources; `Pattern`/partition
subscriptions; `configureContainer(c -> c.addQueueNames(…))` inside a source spec (a MISS — fewer
queues, never a wrong one); `handle(Object bean, String method)` where the bean is not the
module's. *(amended 2026-09-21 during implementation: and `from(<adapter bean>)`, above; the
lambda flow form's `handle(sink)` DOES derive its outbound row — `caller` the lambda body — the
implicit input channel is what stays unread; two-hop containers are `OI-110`, the configurer
`OI-109`.)*

---

## 6. Catalogs and validation

Three catalogs of `style: fluent`: `spring-integration-pubsub.yml` (detect
`com.google.cloud:spring-cloud-gcp-pubsub`), `spring-integration-amqp.yml`
(`org.springframework.integration:spring-integration-amqp`), `spring-integration-kafka.yml`
(`org.springframework.integration:spring-integration-kafka`), each `measured:` at §9's versions.
`spring-integration.yml` (still `config_join`) gains `flows.steps` — the shared step table — which
the three import by reference (`steps_from: spring-integration`; the loader already lets catalogs
share a shape model by name — the same mechanism). *(amended 2026-09-21 during implementation, M9:
the table is its own model file, `catalogs/step-models/spring-integration.yml`, named as
`step_model: spring-integration` and merged into `matches` by the loader — which refuses an
unknown id by file, a duplicate `(owner, method, descriptor)` from both sides, and a catalog
declaring `undeclared_steps` beside a model that has one; `spring-integration.yml` itself is
unchanged. `api._catalog_hash` and the two-loaders test walk `bean-models/` and `step-models/`
as they walk `shape-models/`.)* New fluent keys, all optional and validated with
`CatalogError` naming the file: root `new:` (a type; exclusive with `owner`/`method`), root
`direction:`, root `method_annotation: {annotation, arg, into}`, capture values `{ bean_via: argN }`
and `unresolved`, capture fields `channel_link` and `handler`, step `poisons: [fields]`,
`compose: { field: [halves], join }`, `beans:` (roots reachable only through `bean_via`),
`continue_via_argument`/`via_argument_of … continue: true`, `sinks:`. *(amended 2026-09-21 during
implementation, M1 — the keys as BUILT, D02's `fluent` section is the reference: root/step
`descriptor:`; root `direction:`; root `method_annotation:`; capture values `argN`,
`{bean_via: argN}` on any field, and `none` on `handler` (a literal `unresolved` is REFUSED — a
root whose destination sits in a non-string slot captures the slot and reads to nothing);
capture fields `channel_link`, `channel_source`, `handler`; step `poisons:` (on a root, silently
dropped — logged); root `compose:`; catalog `undeclared_steps: {owner, poisons}`; `beans:`
(validated like `roots`; refuses `direction`/`compose`/`method_annotation`/`via_argument_of`);
`via_argument_of … continue: true` on a root or step and `continue: true` on a terminal's
`terminal_via_argument`; no `new:`, no `sinks:`. `channel_via` gained an optional `descriptor`
beside `arity`.)* A `direction: inbound`
fluent catalog writes `handler` on its rows; today's outbound catalogs are untouched (byte-identical
goldens are the proof — §10). *(amended 2026-09-21 during implementation, M12: two changes in the
fluent walk ARE observable by every shipped fluent catalog, both in the ladder's own direction and
both pinned on a shipped catalog — a `parameter` capture carries its site's caller so the field
ladder's `@Value`-parameter rung answers in fluent (`webClient.get().uri(url)` with `url` the
method's own `@Value("${svc.url}")` parameter now reads the expression), and a varargs array's
elements each take the ladder. Goldens stayed byte-identical because no fixture exercised either.)*

---

## 7. The two ride-alongs

### 7a. `dsl-media-route`

`RouterFunctionDsl`/`CoRouterFunctionDsl`/servlet `RouterFunctionDsl` declare
`accept(MediaType…, Function1)` and `contentType(MediaType…, Function1)`: a route under a media
guard with no verb and no path. Every word exists since the 2026-09-19 spec: a **verb rule** on
those overloads — `{ owner, method: accept, arity: 2, media_arg: 0, fills: produces, handler_arg: 1,
verb: null }` and the `contentType` twin with `fills: consumes` — one row, `method` NULL, path `/**`
(the served any-path pattern, `_served`), media set: exactly how `route(predicate, handler)` renders
today. `_carries_a_handler`'s unresolved row goes away for these two names. **No `all_methods` on
the router catalogs and no pin moves** (A1: `resources(…)` routes are verb-less rows too and serve
GET/HEAD/OPTIONS only — a fan-out would publish five wrong rows per static route). F9's
`HttpMethod.values()` measurement stays in CP-29 as the record of why not. *(amended 2026-09-21
during implementation, M7: six verb rules on the two router catalogs (`CoRouterFunctionDsl`,
`RouterFunctionDsl` on WebFlux; the servlet `RouterFunctionDsl` on MVC — CP-29 row 10: exactly
two overloads each, the vararg factory and the `(MediaType, Function1)` form). The servlet
fixture's `accept(APPLICATION_JSON) { }` sits inside `"/ktmvc".nest { }`, so its row is
`/ktmvc/**` — the enclosing prefix folds in front, the correct rendering. Two engine changes:
`_validate_matches` admits `media_arg`/`fills` on a verb and REFUSES a verb rule on a name a
`media` rule also reads unless it declares an `arity` (else the media rule is unreachable); and
a call on such a name that no verb overload accepts falls to the media rule (`_falls_to_media`),
so the arity-1 vararg `accept(JSON)` still reads as media beside its arity-2 twin. The
`_carries_a_handler` arm stays for any media name WITHOUT a verb rule; its guard is pinned on a
synthetic catalog now. The one pin that moved: the router fixtures' unresolved row became the
resolved one, spec §10 item 2.)*

### 7b. `gateway-properties-routes`

Routes declared in configuration are `config_join`'s territory. A new, general address form — `indexed:`, "items under a list prefix, each with fields" — of which Gateway's route list is the first instance; the shortcut grammar (`Name=args`) is catalog data:

```yaml
# spring-cloud-gateway-properties.yml — style: config_join, protocol: http (A6: one style per
# catalog; `config_join` carries `direction` per rule, so this one file emits the served path
# rows AND the `uri` peer rows, as the DSL pair `spring-cloud-gateway.yml` +
# `spring-cloud-gateway-outbound.yml` does between them)
indexed:
  prefix: spring.cloud.gateway.server.webflux.routes        # F6; a second prefix only if CP-29 shows 5.0.0 binds it
  predicates: predicates                                    # `[N].predicates[M]`
  uri: uri
```

Per `[N]` (the config layer already flattens lists to `key[N]` — `ingress/read/yaml_config.py`):
each `predicates[M]` is a shortcut `Name=a,b` (split on the first `=`, tokenized on `,` — F7) or the
map form `predicates[M].name` + `predicates[M].args.<field>` (the `shortcutFieldOrder` names:
`Path` → `patterns`/`_genkey_0…`, `Method` → `methods`, `Header` → `header`,`regexp`, `Query` →
`param`,`regexp`, `Cookie` → `name`,`regexp`). `Path` → one inbound row per pattern; `Method` →
verbs (none → `method` NULL, resolved — exactly the DSL catalog's rendering, A7); `Header`/`Query`/`Cookie` → `request_requirement`
rows through the combinator's stash table (`route_requirements`; `caller`/`handler` NULL join by
`None == None` in `_from_stash`, as the DSL Gateway rows do today); `Host After Before Between
RemoteAddr Weight XForwardedRemoteAddr CloudFoundryRouteService ReadBody` pass-through; an unknown
name → the route's rows unresolved. `uri` → the outbound row exactly as
`spring-cloud-gateway-outbound.yml` reads the DSL's `uri(…)` (`lb://orders` → peer `orders`;
`http(s)://host…` → peer host) *(amended 2026-09-21 during implementation, M8: the parenthetical
was wrong about what the DSL sibling publishes — it carries the URI VERBATIM as `path` with
`peer` NULL, a routing destination kept whole (pinned by `test_gateway_targets_derive_outbound`),
and the property rows mirror that exactly: `lb://orders` and `http://items.internal:8080` as
`path`, `peer` NULL; CP-29 row 8 records what the scheme means)*. Values pass through `_agreed`: a route that differs between
environments is one `environment_divergence` question, no row — the existing `config_join` rule.
*(amended 2026-09-21 during implementation, M8: `config_join` filed no such question before this
— the kind existed only in `derived_resource.gaps`; it is filed from `config_join.gaps` per ITEM
(key `…routes[N]`, candidates `{key, values}` per diverging key). And three answers, not two: one
agreed value → the value; two or more distinct values → the item is diverged, no rows, one
question; a key resolved in NO environment → the item's other rows are minted and that field
renders `unresolved` — `uri` unread → a `path` NULL target row, a predicate unread → the inbound
rows `unresolved` with `path` NULL where no pattern was read.)*
`filters[M]` are not read (they rewrite paths at runtime — a boundary, stated: `RewritePath`,
`StripPrefix` change the *upstream* path, not the served one; the served path is the predicate's).

*(amended 2026-09-21 during implementation, M8 — the grammar as measured and built, CP-29 rows
3–7 and `catalogs/spring-cloud-gateway-properties.yml`: the block is `indexed: {prefix, item:
{predicates: {field, grammar: shortcut, positional: _genkey_}, path: {name: Path, args: [patterns,
matchTrailingSlash], gather: list_tail_flag}, method: {name: Method, args: [methods], gather:
list}, requirements: {Header: {kind: header, args: [header, regexp]}, Query: {kind: query, args:
[param, regexp, predicate]}, Cookie: {kind: cookie, args: [name, regexp]}}, pass_through: [the
nine names], peer: {field: uri, direction: outbound}}}`. The map form's `Path` field is
`args.patterns` (the 5.0.0 `Config` has no `pattern`). A GATHERING predicate collects EVERY
`args` value whatever its key — `ShortcutType.normalize` reads `args.values()` and tests no key
(row 7) — positional `_genkey_K` by K, then the remaining keys in flattened order; the tail flag is
found BY VALUE (the one `true`/`false` literal among the gathered values), because
`resolved_config` carries no declaration order (`OI-113`) — two such literals, one under a gather
with no flag (`Method=true`), or a gather left EMPTY once the flag is removed (`Path=true`, `Method=`)
read as unread: the inbound rows `unresolved`, `path` NULL where no pattern was read, the target
row untouched. A scalar is ONE value, never split on `,` — `methods: PUT,PATCH` binds a verb that
matches nothing, so `method` reads NULL and the row `unresolved`; a `patterns: /a/**,/b/**`
scalar is one verbatim pattern the framework parses and is published as written (the rule is
verbs only). `Version` — a fifteenth factory at 5.0.0 (row 6), absent from the pass-through list
above — is left an unknown name, so a route carrying it derives `unresolved` rows, stated on the
catalog. Two items collapsing to one address keep the INTERSECTION of their requirements (spec
2026-09-19 §4d's rule), and any unresolved alternative makes the row `unresolved`; a row whose
`path` is NULL carries no requirements (the stash joins on `path`). Requirement rows reach
`endpoint_metadata` through the combinator's `route_requirements` stash with `caller`/`handler`
NULL, `required`, the regexp as written. The legacy prefix `spring.cloud.gateway.routes` binds
nowhere in the 5.0.0 jar (row 2) and is not declared. Gateway `filters` are `OI-111`.)*

---

## 8. What this design does not do, and what it logs

| Not built | Why | Where |
|---|---|---|
| Kafka `Pattern`/`TopicPartitionOffset` subscriptions; container-built sources (two hops) | not a topic name / a second bean hop | catalog `unresolved:` reasons, COVERAGE |
| the lambda flow form; `from(Supplier)`/`from(MessageSource)` | different shapes | COVERAGE boundary |
| `@MessagingGateway` senders; `channel.send(…)` callers | the trace layer's question | — |
| Gateway `filters` (path rewrites) and the map form's `args` beyond the four shortcut families | runtime path rewrite; other factories' field orders unmeasured | catalog comment, OI |
| `setTopicExpression*`, `.topic(Function)`, `.routingKey(Function)` | a function is not a literal | catalog |
| Spring Integration XML | no facts | — |

---

## 9. Probes

| Probe | Records |
|---|---|
| **CP-27** spring-integration-core / -kafka / -amqp 6.2.4, spring-rabbit 3.x, spring-kafka 3.x | F1–F5 and F8 as generated tables: `IntegrationFlow.from` overloads; the 35 `BaseIntegrationFlowDefinition` members with each one's classification justification (what `route`/`gateway`/`scatterGather` do with the message — bytecode of their handler construction); `MessageProducerSupport` setters; the ten `Kafka.messageDrivenChannelAdapter` descriptors and the four `inboundChannelAdapter`; `Amqp` factories and spec setters; `AmqpOutboundEndpoint` setters; container setters; `ConsumerProperties`/`ContainerProperties`/`Queue` constructors; `@Bean`/`@Qualifier` attributes; Spring's autowiring-by-type rule (`DefaultListableBeanFactory.determineAutowireCandidate` — one candidate or a failure) |
| **CP-28** spring-cloud-gcp-pubsub 5.1.2 | F10: the two constructors, `setTopic` and the two expression setters, `from(MessageProducerSupport)` accepting the adapter |
| **CP-29** spring-cloud-gateway-server-webflux 5.0.0 | F6/F7: `GatewayProperties.PREFIX`, whether a legacy prefix binds, `PredicateDefinition(String)`, the five predicate factories' `shortcutFieldOrder`/`shortcutType`, `RouteDefinition` fields, `uri` scheme handling; spring-web 6.1.6 `HttpMethod.values()` (F9) |

---

## 10. Nothing existing moves — the proof

1. Every new fluent key is optional; the thirteen shipped fluent catalogs *(amended 2026-09-21
   during implementation: EIGHT fluent catalogs shipped before the branch — `grep -l "^style: fluent"` at
   `cebc7b5` — and eleven ship now, the three broker catalogs added)* declare none and their
   goldens stay byte-identical (the plan lands the keys before any catalog uses them and runs the
   gate). `config_join` changes only in `gaps` (ask only for a `read_by` with no `fed_by`) and the
   `indexed:` form.
2. The only intended change to an existing pin: the Spring Integration probe fixture's
   `channel_destination` questions become rows (asserted gone where rows appear); the router
   fixtures' `accept(...) { }` unresolved row becomes a resolved one. *(amended 2026-09-21 during
   implementation: both moved as intended — `amqpInputChannel`'s question became the row
   `(inbound, bean.orders.queue, handleOrder, ordersInboundAdapter)`, and the two router rows
   `(None, /**)` and `(None, /ktmvc/**)` moved the fixture-wide counts in `test_pipeline.py`,
   `test_app.py`, `test_vertical_slice.py` and `test_asm_scanner.py` by the one route and its
   suspend-lambda class. Two pins moved that were NOT foreseen, both about the loop's shape
   and no row: `metadata.json`'s `skipped_catalogs` list ORDER (`spring-integration` now heads
   it — M3's ordering), and the fourth `config_join` catalog joining the skipped lists of every
   fixture that declares no Gateway. Every golden stayed byte-identical.)*
3. Full gate at every commit.

---

## 11. Fixtures and tests

- **`spring-integration-probe`** already carries Shape 2 (AMQP bean + container, `setOutputChannelName`,
  three `@ServiceActivator` spellings) and Shape 3 (Kafka inbound/outbound flows). Add: a Pub/Sub
  inbound adapter with `setOutputChannel(<injected channel param>)`, a second with
  `setOutputChannelName`, a `@Value("${probe.subscription}") String` subscription with the value in
  `application.properties`; a `PubSubMessageHandler` outbound bean under `@ServiceActivator`; an AMQP
  DSL flow (`Amqp.inboundAdapter(cf, "q1", "q2")`) and an AMQP outbound bean (`exchange/rk`); a
  Kafka flow with a `.transform(…)` pass-through and one with `.route(…)` (handler unresolved); a
  flow ending in `.channel("x")` feeding a `@ServiceActivator`; the ambiguous-bean case (two
  `MessageChannel` beans, an unnamed parameter → unresolved link); a `Pattern` source (unresolved).
  *(amended 2026-09-21 during implementation, M10: as built in `Shape4PubSub.java` and
  `Shape5Flows.java` — the `.transform(…)` pass-through sits on the AMQP DSL flow
  (`ordersInboundDslFlow`), not a Kafka one; the fixture pins
  `com.google.cloud:spring-cloud-gcp-pubsub:5.1.2`, `probe.subscription=orders-sub`, and
  `probe.audit-channel=amqpAuditChannel`; a variance arm of AMQP flows exercises every ladder
  rung on a varargs element — literal, inlined constant, raw placeholder, `@Value` field,
  `@Value` parameter, properties getter, late constant, concatenation.)*
- **Router fixtures** (`orders-service` Java + Kotlin): an `accept(APPLICATION_JSON) { }` route
  (one resolved row, `method` NULL, `/**`, `produces: application/json`).
- **`orders-gateway`**: `src/main/resources/application.yml` with two routes — shortcut form
  (`Path=/cfg/orders/**`, `Method=GET,POST`, `Header=X-Api,v2`) and map form — and a `lb://orders` uri.
  *(amended 2026-09-21 during implementation, M10: the map form spells `name: Path` +
  `args.patterns: /cfg/items/**` (the measured field name) with `uri: http://items.internal:8080`;
  the fixture had no resources directory before.)*
- **Unit tests** on synthetic facts: each bean rung and each ambiguity (channel vs container
  kinds); the ladder on a destination (literal, `@Value`, properties getter, unread); vararg
  elements; the container hop (`bean_via`); `new:` roots; `continue_via_argument`; every step
  kind incl. unknown → divert; sink setters last-wins and `compose`; `channel_bindings` join
  (fed ⋈ read; unfed → question; unread → adapter row alone); `indexed:` shortcut and map parsing, unknown predicate → unresolved,
  environment disagreement → no row.
- **e2e**: rows per fixture; questions gone; `endpoint_metadata` rows for the Gateway properties
  `Header=`; the register's pins for the closed items.

---

## 12. Cells moved, register, documents

| Item / cell | Before → after |
|---|---|
| `pubsub-channel-adapter` | Pub/Sub §5.11 "Spring Integration" 0/1 → ✅ (inbound + outbound); register row empty |
| §5.12 "the DESTINATION behind a channel" | boundary → shipped for AMQP / Kafka / Pub/Sub, bean-wired and DSL |
| §5.8 | new framework line "Spring Integration Kafka (DSL + adapters)" ✅ |
| §5.9 | AMQP adapter line ✅ |
| `dsl-media-route`, `gateway-properties-routes` | closed; REST inbound holds `conditional-controllers` only; Gateway rollup ✅ |
| D02 | fluent's new keys (`new:` roots, `bean_via`, `channel_link`, `handler`, `poisons`, `compose`, `beans:`, `continue_via_argument`, `sinks:`, `method_annotation`); `config_join`'s `indexed:`; the media-overload verb rules *(amended 2026-09-21 during implementation, M1/M12: the keys as built — `<init>` roots, `descriptor:`, `direction:`, `bean_via`, `beans:`, `channel_link`, `channel_source`, `handler`, `poisons`, `compose`, `undeclared_steps`, `via_argument_of … continue: true`, `method_annotation` — under the `fluent` style; `bean_model` (§1c) and `step_model` (§1d) beside `shape_model`; `indexed:` under `config_join`; the verb-rule `media_arg`/`fills` and the arity refusal under `combinator`)* |
| D01 | `channel_bindings` (derived, temp; roles `fed_by`/`read_by`/`sends_to`) *(amended 2026-09-21 during implementation, M12: `resolution` is role-dependent — the wire's on `fed_by`, the NAME's on `read_by`)* |
| D00 | *(amended 2026-09-21 during implementation, M12: NO fact change — every input this spec reads (`call_site` arguments and `source` ids, `annotation_index`, `method_declarations`, `resolved_config`) was already published; the spec adds no fact and changes no fact's shape)* |

## 13. Sizing and order

1. `beans.py`; `channel_bindings` + `read_by` from `config_join` + the join pass + `gaps` (inert until fluent writes `fed_by`); fluent's new keys with unit tests and the byte-identical proof.
2. §4 Pub/Sub inbound → outbound → AMQP container hop (CP-27/28 with it).
3. §5 flows: Kafka sources/sinks, steps table, AMQP DSL, `from(bean)`.
4. §7a, §7b (CP-29).
5. Docs, register, COVERAGE.

About the size of B+C (2026-09-18): one new engine of two shapes, three catalogs, two `config_join`
words, three probes, one fixture module extended and one resource file added. *(amended
2026-09-21 during implementation: no new engine — `fluent` extended (+~1,170 lines, half of
them its own documentation), `beans.py` and `channel_bindings.py` new; three broker catalogs, one
Gateway properties catalog, one bean model, one step model; CP-27, CP-28, CP-29; the
`spring-integration-probe` fixture extended and `orders-gateway` given its resources file. Order
as planned: Tasks 1 → 2 → 3 → 4–5 → 6 → 7–8 → 9.)*
