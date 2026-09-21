# Spring Integration adapters and flows: the destination behind a channel (register Group E)

**Status:** design. Approved in conversation 2026-09-21, section by section; scope widened by the
user from Pub/Sub alone to "Pub/Sub both directions + the AMQP container hop" and then to the
Java DSL flows ("C — which allows us to solve Kafka as well"). Self-review against the jars and
the engines is folded in (§0). Not yet planned.

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
| F3 | `BaseIntegrationFlowDefinition` declares **35** public step methods at 6.2.4 (`javap`, names: `aggregate barrier bridge channel claimCheckIn claimCheckOut controlBus convert delay enrich enrichHeaders filter fixedSubscriberChannel fluxTransform gateway handle handleReactive headerFilter intercept log nullChannel publishSubscribeChannel resequence route routeByException routeToRecipients scatterGather split splitWith to transform transformWith trigger wireTap`) | §5's step table classifies all 35 (D02 slice rule: every declared member is a rule, a pass-through or a divert) |
| F4 | AMQP outbound is `AmqpOutboundEndpoint(AmqpTemplate)` + `setExchangeName(String)`/`setRoutingKey(String)` (bean) and `Amqp.outboundAdapter(AmqpTemplate)` + `.exchangeName(String)`/`.routingKey(String)` (DSL) — two setters composing one address | §4/§5: `destination_setters: [exchangeName, routingKey]` joined `exchange/routingKey`, the form `spring-rabbit-template.yml` already publishes |
| F5 | `AbstractMessageListenerContainer` (spring-rabbit 3.x) declares `setQueueNames(String…)`, `addQueueNames(String…)`, `setQueues(Queue…)`; `ConsumerProperties`/`ContainerProperties` each have `(String…)`, `(Pattern)`, `(TopicPartitionOffset…)` constructors | §4's container setters include `addQueueNames`; a `Pattern` constructor → unresolved |
| F6 | Spring Cloud Gateway 5.0.0 binds its properties under **`spring.cloud.gateway.server.webflux`** (`GatewayProperties.PREFIX`, `javap -constants`); the pre-4.2 `spring.cloud.gateway.routes` is NOT that constant | §7b lists the 5.0.0 prefix; the legacy prefix is admitted only if CP-29 shows 5.0.0 still binds it |
| F7 | `PredicateDefinition(String)` splits the shortcut on the first `=` (`indexOf(61)`), tokenizes the rest on `,`, and names positional args `_genkey_N` (`NameUtils.generateName`); `RouteDefinition` carries `id`, `predicates`, `filters`, `uri`, `order`, `metadata` | §7b's grammar |
| F8 | `@Bean` declares `value()`/`name()` (both `String[]`, aliases) at spring-context 6.1.6; `@Qualifier` declares `value()` | §3's bean-name rule reads both `@Bean` attributes and `@Qualifier.value` |
| F9 | `HttpMethod.values()` at spring-web 6.1.6 is `GET HEAD POST PUT PATCH DELETE OPTIONS TRACE` (static initialiser `ldc` sequence) | recorded in CP-29; §7a does NOT use it (A1) |
| F10 | `PubSubInboundChannelAdapter(PubSubSubscriberOperations, String)` extends `MessageProducerSupport` (`setOutputChannel(MessageChannel)`, `setOutputChannelName(String)`); `PubSubMessageHandler(PubSubPublisherOperations, String)` extends `AbstractMessageHandler` with `setTopic(String)`, `setTopicExpression(Expression)`, `setTopicExpressionString(String)` — spring-cloud-gcp-pubsub 5.1.2 | §4 and §6; the two expression setters → unresolved |
| F11 | Placeholders are already resolved by the **field ladder** (`shapes/arguments.py`, `field_sources` on a catalog: a `@Value("${…}")` field/parameter or a `@ConfigurationProperties` getter becomes the `${…}` expression the row carries, substituted per environment by `resolved_peers`) — the user's "we must have resolution for placeholders" holds today for HTTP clients and holds here by reusing it | §3 |
| F12 | `config_join.gaps` files `channel_destination` questions from the `service_identity` seam **after** the pipeline's reset; the new engine's rows must be visible to it | §3: the `channel_destinations` derived table, read by `gaps` |

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
| A8 | future languages | `bean_wiring` is a framework term, not a language: the keys (`destination_arg`, `channel_links`, `containers`, `flows`) describe DI registrations by name and type, which .NET's container has too | kept; the engine names no language |

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

## 2. Approach — one join, two entry shapes, existing pieces plus bean identity

Weighed: (A) a `bean_wiring:` block inside `config_join`; (B) a new style for the bean-wired
adapters; (C) also the DSL flows. **C was ruled** ("which allows us to solve Kafka as well").
The engine is new because its evidence spans **several methods of a class through bean identity**
— no shipped style crosses methods that way — but every piece except bean identity exists:

| Piece | Exists as | Used for |
|---|---|---|
| receiver-chain walk inside one method | `fluent` (`result → receiver`), `_producing_site` | `new Adapter(…)` then its setters; the flow chain |
| a value built by one chain and consumed as another's argument | `fluent`'s `terminal_via_argument` | `from(<spec chain>)`, `handle(<sink spec chain>)` |
| placeholder resolution | the field ladder (`field_sources`), `resolved_peers` | every destination argument (F11) |
| the handler side of a channel | `config_join._channels` | `@ServiceActivator(inputChannel)` and siblings |
| class-compiled lambdas as `lambda` arguments | `effective_calls.py` (2026-09-19 spec) | `.handle((p, h) -> …)` bodies |
| **bean identity** — which bean an injected parameter or a `@Bean` call names | **new** (§3) | `setOutputChannel(param)`, `new AmqpInboundChannelAdapter(container)`, `from(adapterBean)` |

Units:

| # | Unit | Where |
|---|---|---|
| 1 | bean table + resolution rungs | `engines/bean_wiring.py` (§3) |
| 2 | bean-wired adapter walk, inbound + outbound, container hop | `engines/bean_wiring.py` (§4) |
| 3 | DSL flow walk, sources / steps / handler / sinks | `engines/bean_wiring.py` (§5) |
| 4 | `channel_destinations` table; `gaps` reads it; rows join `_channels` | `config_join.py`, SQL (§3) |
| 5 | three broker catalogs + `flows.steps` on `spring-integration.yml` | `catalogs/` (§6) |
| 6 | `dsl-media-route` — `verb: null` rules on the media overloads | router catalogs (§7a) |
| 7 | `gateway-properties-routes` — `indexed_routes` in `config_join` | `config_join.py`, Gateway catalogs (§7b) |
| 8 | probes CP-27..29, fixtures, register, COVERAGE, D02 | §9, §11, §12 |

---

## 3. The join and bean identity

**Three facts joined.** A destination (subscription / queue / topic / exchange+routingKey), the
channel it is linked to, and the handler reading that channel. The link and the handler are
absent when a flow's handler is inline: the row is then emitted directly.

**Output rows.** Inbound: `protocol` from the adapter's catalog, `direction: inbound`, `path` =
destination, `handler` = the activator method (the `_channels` index) or the inline handler's
body, `caller` = the `@Bean` method that built the adapter/flow, `evidence: compiler`. Outbound:
`path` = topic / `exchange/routingKey`, `caller` = the `@Bean` method that built the handler
or the flow, `handler` NULL. `request_shape`/`response_shape` NULL (a channel handler's
signature is the framework's convention; no probe measured one — the same statement
`config_join._derive_channels` makes). Media NULL.

**Destinations go through the field ladder.** The adapter catalogs declare `field_sources`
exactly as `spring-resttemplate.yml` does. A `string` literal is the address; a `@Value("${…}")`
field or parameter, or a `@ConfigurationProperties` getter, is the `${…}` expression the row
carries and `resolved_peers` substitutes per environment; a vararg `array` is one row per
element (each through the ladder); anything else poisons `path` → an unresolved row. The row is
never absent for a declared adapter: the adapter's existence is the declaration.

**Questions become rows, once.** The engine writes `channel_destinations(channel, direction,
protocol, destination, catalog_id)` — a temp table reset with the endpoint tables. `config_join.gaps`
skips a `(channel, direction)` present there, so the `channel_destination` question is not filed
for a channel an adapter feeds; a channel nothing feeds keeps its question. `spring-integration.yml`
is otherwise unchanged.

**Bean identity — the new capability, and its no-guess rule.** A *bean reference* is an
injected parameter of a `@Bean` method, or the argument of a channel link / constructor. A direct
call `amqpInputChannel()` to a `@Bean` method of the same class names that bean. A parameter
resolves by rungs that depend on WHAT is referenced (A2 — Spring's candidates include beans the
module never declares):

- a **channel** reference (`setOutputChannel(param)`, `from(param)` where the parameter's erased
  type is `MessageChannel` or a subtype): (1) `@Qualifier("name")` → `name`; (2) the parameter's
  declared name (`signature.parameters[i].name`) when it is a `@Bean` method's bean name
  (`name()`/`value()` element, else the method name — F8) OR a channel name the handler index
  (`_channels`) already knows — Spring auto-creates a `DirectChannel` under a referenced name, and
  resolves an ambiguous `MessageChannel` injection by parameter name (`errorChannel` and
  `nullChannel` are always candidates too); **never by type**;
- a **container / adapter** reference (a catalog `containers` or `adapters` type — types no
  framework bean shares): (1) `@Qualifier`; (2) exactly one `@Bean` method of that erased return
  type in the module; (3) the parameter's name as a bean name — Spring's own order
  (`DefaultListableBeanFactory.determineAutowireCandidate`, CP-27).

No rung answers, or a rung has two candidates → the reference is **unresolved**: an adapter row
still derives with its destination (handler NULL); a container hop yields `path` unresolved. A
parameter compiled without `-parameters` has `name: null` and skips the name rung.
The bean table — `@Bean` methods by name and by erased return type, plus `@Qualifier`s — is one
fold over the annotation index and `method_declarations`, built once per resolve.

**Cost per resolve:** one pass over the `@Bean` methods' call sites (already loaded), the
annotation index (a `once` fold), the bean table (one dict), one `channel_destinations` insert.

---

## 4. Entry shape 1 — the bean-wired adapter

Inside one `@Bean` method, rooted at the construction of a catalog-declared type.

```yaml
# spring-integration-pubsub.yml — style: bean_wiring, protocol: pubsub
adapters:
  inbound:
    - type: com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter
      destination_arg: 1                                   # (PubSubSubscriberOperations, String) — F10
  outbound:
    - type: com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler
      destination_arg: 1                                   # (PubSubPublisherOperations, String)
      destination_setters: [setTopic]                      # setTopic(String) overrides; the two *Expression setters → unresolved
channel_links:                                              # MessageProducerSupport, core 6.2.4 (F10)
  - { method: setOutputChannelName, arg: 0, kind: name }
  - { method: setOutputChannel,     arg: 0, kind: bean }
field_sources:
  value_annotation: org.springframework.beans.factory.annotation.Value
  properties_annotation: org.springframework.boot.context.properties.ConfigurationProperties
  prefix_from: prefix
  getter_prefixes: [get, is]
```

**Inbound.** An `<init>` site of an `adapters.inbound` type → destination = `arguments[destination_arg]`
through the ladder. Every later site in the method whose receiver is that value is matched against
`channel_links`: `kind: name` reads a string literal (else the link is unresolved); `kind: bean`
resolves the argument by §3 (a `@Bean` method call in the class, or an injected parameter). The
channel name joins `_channels` → one inbound row per handler on that channel; the pair goes into
`channel_destinations`. No link, or an unresolved one → one row with the destination and handler
NULL; no question is answered.

**Outbound.** An `<init>` of an `adapters.outbound` type inside a `@Bean` method that itself
carries `@ServiceActivator(inputChannel = "x")` (read from the annotation index): destination
from `destination_arg`, overridden by the LAST `destination_setters` call on the same value
(Spring setter semantics); the row is outbound with `caller` = the `@Bean` method; `x` is recorded
outbound in `channel_destinations`. Who sends to `x` is the trace layer's question.

**The container hop (AMQP).**

```yaml
# spring-integration-amqp.yml — protocol: amqp
adapters:
  inbound:
    - type: org.springframework.integration.amqp.inbound.AmqpInboundChannelAdapter
      destination_via: { arg: 0, setters: [setQueueNames, addQueueNames, setQueues] }   # F5
  outbound:
    - type: org.springframework.integration.amqp.outbound.AmqpOutboundEndpoint
      destination_setters: [setExchangeName, setRoutingKey]          # composed `exchange/routingKey` — F4
      destination_join: "/"
containers:
  - org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer
  - org.springframework.amqp.rabbit.listener.DirectMessageListenerContainer
```

`destination_via` resolves `arguments[arg]` as a bean (§3), finds that bean's `@Bean` method,
and in it the `<init>` of a `containers` type plus the `setters` calls on that value:
`setQueueNames`/`addQueueNames(String…)` → one row per element; `setQueues(Queue…)` → each
element's producing `new Queue("name")` (`org.springframework.amqp.core.Queue(String…)`) or a
`@Bean` `Queue` method resolved by §3, else unresolved. One hop only. Outbound composition:
`destination_setters` in the declared order joined by `destination_join`; a half whose setter is
absent is filled by the framework from the `RabbitTemplate` bean's own defaults
(`RabbitTemplate.setExchange`/`setRoutingKey`), which this walk does not read → `path` unresolved
(A3). Both halves set → `exchange/routingKey`, the form `spring-rabbit-template.yml` publishes.

**Boundaries stated:** an adapter built outside a `@Bean` method or through a factory method; a
container configured in a third bean; `setOutputChannel(new DirectChannel())` (anonymous — the
destination row derives, no handler); XML beans; `setTopicExpression*`.

---

## 5. Entry shape 2 — the DSL flow

One receiver chain inside a `@Bean` method returning `IntegrationFlow`:
`IntegrationFlow.from(<source>) … .handle(<handler>) … .get()` (F1: only `IntegrationFlow.from`
exists at 6.2.4). Rooted at `from`, walked forward along `result → receiver`; `from`'s and
`handle`'s arguments are chains of their own, joined as `terminal_via_argument` joins the SQS
request builder to its send.

```yaml
# spring-integration-kafka.yml — protocol: kafka
flows:
  sources:                                     # measured F2; every overload declared (D02 slice rule)
    - { owner: org.springframework.integration.kafka.dsl.Kafka, method: messageDrivenChannelAdapter,
        descriptor: "(Lorg/springframework/kafka/core/ConsumerFactory;[Ljava/lang/String;)…", destination_arg: 1 }
    - { …, descriptor: "(…ConsumerFactory;…ListenerMode;[Ljava/lang/String;)…", destination_arg: 2 }
    - { …, descriptor: "(…ConsumerFactory;…ContainerProperties;)…", destination_via_properties: 1 }   # `new ContainerProperties(String…)` one hop
    - { …, descriptor: "(…ConsumerFactory;…ContainerProperties;…ListenerMode;)…", destination_via_properties: 1 }
    - { …, descriptor: "(…ConsumerFactory;Ljava/util/regex/Pattern;)…", unresolved: pattern }          # a Pattern is not a topic name
    - { …, descriptor: "(…ConsumerFactory;…ListenerMode;Ljava/util/regex/Pattern;)…", unresolved: pattern }
    - { …, descriptor: "(…ConsumerFactory;[…TopicPartitionOffset;)…", unresolved: partitions }
    - { …, descriptor: "(…ConsumerFactory;…ListenerMode;[…TopicPartitionOffset;)…", unresolved: partitions }
    - { …, descriptor: "(…AbstractMessageListenerContainer;)…", unresolved: container }                # two hops — stated
    - { …, descriptor: "(…AbstractMessageListenerContainer;…ListenerMode;)…", unresolved: container }
    - { owner: …Kafka, method: inboundChannelAdapter, descriptor: "(…ConsumerFactory;…ConsumerProperties;)…", destination_via_properties: 1 }   # polled; + its 3 siblings
  sinks:
    - { owner: org.springframework.integration.kafka.dsl.Kafka, method: outboundChannelAdapter, destination_setters: [topic] }   # `.topic(String)`; `.topic(Function)` → unresolved
```

The AMQP twin: `Amqp.inboundAdapter(ConnectionFactory, String…)` `destination_arg: 1`;
`(ConnectionFactory, Queue…)` elements as §4; `(SimpleMessageListenerContainer)` /
`(DirectMessageListenerContainer)` through `destination_via`; `Amqp.outboundAdapter(AmqpTemplate)`
with `destination_setters: [exchangeName, routingKey]`. Pub/Sub has no DSL factory:
`from(<bean reference>)` where the reference resolves (§3) to a `@Bean` method whose §4 walk gives
the destination.

**Steps — declared once on `spring-integration.yml`** (`BaseIntegrationFlowDefinition`, core
6.2.4, all 35 — F3):

| Kind | Members (all 35 — F3) | Effect |
|---|---|---|
| `pass_through` | `aggregate barrier bridge claimCheckIn claimCheckOut convert delay enrich enrichHeaders filter fluxTransform headerFilter intercept log resequence split splitWith transform transformWith wireTap`, `fixedSubscriberChannel()` (no-arg) | none — the message still reaches what follows |
| `channel` | `channel(String)`, `channel(MessageChannel)`, `channel(MessageChannelSpec)`, `fixedSubscriberChannel(String)` | the source's destination is joined to that channel (§3) — and the walk CONTINUES: a later `handle` is a handler too (A4) |
| `handler` | `handle(GenericHandler)`, `handle(Class, GenericHandler)`, `handle(MessageHandler)`, `handle(Object, String)`, `handle(MessageHandlerSpec)`, `handleReactive` | the row's handler: the lambda body, the bean's method, or the sink spec (outbound) |
| `discard` | `nullChannel` | the message is dropped: handler NULL is the TRUE answer, the row is resolved |
| `divert` | `route routeByException routeToRecipients gateway scatterGather publishSubscribeChannel controlBus trigger to` | the message may not reach what follows, or goes to a flow this walk does not enter: handler **unresolved**, destination row kept (A5) |

A member not in the table (a future minor's addition) is `divert`. The flow's `get()` and the
`IntegrationFlowBuilder` return are the chain's end. CP-27 records, for each `divert` member, the
handler class it constructs (the justification that the message leaves the linear flow).

**Rows.** Inbound: `path` = the source's destination, `handler` = the first `handler` step reached
without a `divert`, `caller` = the flow's `@Bean` method. Outbound: a flow whose source is
`from(String)` / `from(MessageChannel)` and whose handler is a `sinks` spec → `path` = the
setters' value, `caller` = the flow method, channel recorded outbound. A flow from a channel
whose handler is inline is a channel *consumer*, not a wire: no row, and its channel joins the
inbound adapter that feeds it (the composition case resolves through the channel join).

**Boundaries stated:** the lambda form (`return f -> f.handle(…)`, implicit `<beanName>.input`);
`from(Supplier)`/`from(MessageSource)` generic sources; two-hop container sources; `Pattern` and
partition-offset subscriptions; `handle(Object bean, String method)` where the bean is not a
`@Bean` of the module.

---

## 6. Catalogs and the engine home

`engines/bean_wiring.py` — one engine, `style: bean_wiring`; §4 and §5 are two entry points into
one join. It imports `fluent`'s chain helpers and the field ladder; it reads `_channels` through
a small public function exported from `config_join.py` (`channel_index(workspace, catalog)`),
and `config_join.gaps` reads `channel_destinations`. Catalog keys — all optional, validated
with `CatalogError` naming the file: `adapters.{inbound,outbound}[]` (`type`, one of
`destination_arg` | `destination_via{arg, setters}`, optional `destination_setters`,
`destination_join`), `containers[]`, `channel_links[]` (`method`, `arg`, `kind ∈ {name, bean}`),
`flows.sources[]` (`owner`, `method`, `descriptor`, one of `destination_arg` |
`destination_via_properties` | `unresolved: <reason>`), `flows.sinks[]`, `field_sources` (the
ladder's own validator), and on `spring-integration.yml` `flows.steps.{pass_through, channel,
handler, divert}` — the union must equal the measured member list (a `slice` check like the
combinator's: every declared member classified).

Detection: `spring-integration-pubsub.yml` on `com.google.cloud:spring-cloud-gcp-pubsub`;
`spring-integration-amqp.yml` on `org.springframework.integration:spring-integration-amqp`;
`spring-integration-kafka.yml` on `org.springframework.integration:spring-integration-kafka`;
each `measured:` at the versions §9 records. `spring-integration.yml` keeps `config_join`.

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
`HttpMethod.values()` measurement stays in CP-29 as the record of why not.

### 7b. `gateway-properties-routes`

Routes declared in configuration are `config_join`'s territory. A new address form:

```yaml
# spring-cloud-gateway-properties.yml — style: config_join, protocol: http (A6: one style per
# catalog; `config_join` carries `direction` per rule, so this one file emits the served path
# rows AND the `uri` peer rows, as the DSL pair `spring-cloud-gateway.yml` +
# `spring-cloud-gateway-outbound.yml` does between them)
indexed_routes:
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
`http(s)://host…` → peer host). Values pass through `_agreed`: a route that differs between
environments is one `environment_divergence` question, no row — the existing `config_join` rule.
`filters[M]` are not read (they rewrite paths at runtime — a boundary, stated: `RewritePath`,
`StripPrefix` change the *upstream* path, not the served one; the served path is the predicate's).

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

1. Every new key is optional; a catalog that declares none derives as before. The new engine
   runs only for catalogs of its style; `config_join` changes only in `gaps` (skip when
   `channel_destinations` has the channel) and the `indexed_routes` form.
2. The only intended change to an existing pin: the Spring Integration probe fixture's
   `channel_destination` questions become rows (asserted gone where rows appear); the router
   fixtures' `accept(...) { }` unresolved row becomes a resolved one.
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
- **Router fixtures** (`orders-service` Java + Kotlin): an `accept(APPLICATION_JSON) { }` route
  (one resolved row, `method` NULL, `/**`, `produces: application/json`).
- **`orders-gateway`**: `src/main/resources/application.yml` with two routes — shortcut form
  (`Path=/cfg/orders/**`, `Method=GET,POST`, `Header=X-Api,v2`) and map form — and a `lb://orders` uri.
- **Unit tests** on synthetic facts: each bean rung and each ambiguity; the ladder on a destination
  (literal, `@Value`, properties getter, unread); vararg elements; the container hop; every step
  kind incl. unknown → divert; sink setters last-wins and composition; `channel_destinations`
  suppressing a question; `indexed_routes` shortcut and map parsing, unknown predicate → unresolved,
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
| D02 | `bean_wiring` style and its keys; `indexed_routes`; the media-overload verb rules |
| D01 | `channel_destinations` (derived, temp) |

## 13. Sizing and order

1. §3 bean table + `channel_destinations` + `gaps` skip (inert until an engine writes).
2. §4 Pub/Sub inbound → outbound → AMQP container hop (CP-27/28 with it).
3. §5 flows: Kafka sources/sinks, steps table, AMQP DSL, `from(bean)`.
4. §7a, §7b (CP-29).
5. Docs, register, COVERAGE.

About the size of B+C (2026-09-18): one new engine of two shapes, three catalogs, two `config_join`
words, three probes, one fixture module extended and one resource file added.
