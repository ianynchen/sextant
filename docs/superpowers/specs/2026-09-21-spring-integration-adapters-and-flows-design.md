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
| B3 | `channel_destinations` + a `gaps` skip patched two engines together; the general object is the channel EDGE | `channel_bindings(channel, role fed_by/read_by/sends_to, …)`: fluent writes `fed_by`, `config_join` writes `read_by`, a join pass mints rows, `gaps` asks only about unfed channels; `sends_to` is the slot for later writers (§3b) |
| B4 | the flow walk and the bean-wired walk are BOTH "walk forward from a root along result→receiver, capture from arguments, join argument chains" — `fluent`'s definition; a second walker would drift | **ruled by the user: extend `fluent`** — one root kind, one continuation kind, three capture kinds, one step effect, inbound rows (§2, §4, §5); no new engine |
| B5 | adversarial: `@Profile`-conditional twin beans; a spec configurer adding queues (`configureContainer(c -> c.addQueueNames(…))`); Gateway `filters` rewriting the upstream path; a link set in a different method; `${…}` channel names | the first shares `conditional-controllers`' exposure and is stated with it; the second and fourth are misses, stated; the third matches the DSL outbound catalog's rendering, stated; the fifth is resolved through `_agreed` before the join (§3b) |

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
| walk forward from a root along `result → receiver`, folding captures | `fluent._walk` | a **constructor root** (`new: <type>`) beside the call roots |
| a value built by one chain consumed as another call's argument | `terminal_via_argument` (the join ends the chain) | **`continue_via_argument`**: the consuming call's own chain continues the walk with the same captures (`from(<spec>) … .handle(h)`) |
| an argument that is a bean built elsewhere | — | **`resolve/beans.py`** (§3), and the capture kind **`bean_via`**: fold the captures of that bean's own construction chain |
| the consumer attached to the chain | — (rows carry `caller`; `handler` NULL) | capture kinds **`handler`** (a lambda body or a bean's method) and **`channel_link`** (a channel name or channel bean); a **`poisons:`** step effect (a `divert` poisons `handler`); an inbound row carries `handler` |
| a channel named on the constructing method's annotation | — | root option `method_annotation: { annotation, arg, into }` |
| the channel edge between an adapter and its consumer | `config_join` files a question per `read_by` | **`channel_bindings`** (§3): `fed_by` rows from fluent, `read_by` from the channel index; a join pass mints rows and `gaps` asks only about unfed channels |
| placeholders | the field ladder (`field_sources`) | reused unchanged (F11) |

Units:

| # | Unit | Where |
|---|---|---|
| 1 | `resolve/beans.py` — bean table and resolution rungs | new module (§3) |
| 2 | `channel_bindings` table; `read_by` from `config_join`'s index; join pass; `gaps` reads it | `config_join.py`, new `resolve/channel_bindings.py`, SQL (§3) |
| 3 | fluent: `new:` roots, `continue_via_argument`, `bean_via`, `handler`, `channel_link`, `poisons`, `method_annotation`, inbound rows | `engines/fluent.py` (§4–§5) |
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

- a **channel** reference (erased type `MessageChannel` or a subtype): `@Qualifier` → the
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
  land later.

`resolve/channel_bindings.py` joins `fed_by ⋈ read_by` on `channel` and mints one endpoint row per
pair: inbound, `protocol`/`destination` from the feeder, `handler` = the reader, `caller` = the
feeder's method. A `fed_by` with no reader still has its adapter row (the adapter exists — the
chain derived it with `handler` NULL); a `read_by` with no feeder keeps its `channel_destination`
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

- **`new:` root** — the chain starts at an `<init>` site of the type; `arg0…` are the
  constructor's arguments (the receiver slot is not an argument). The chain is the value's later
  calls (`result → receiver`, as today). A root may carry `direction:` to override the catalog's
  for that registration (the outbound handler in an inbound catalog).
- **`channel_link: arg0`** — a string literal is the channel name; **`{ bean_via: arg0 }`** — the
  argument is a bean reference (a `@Bean` method call in the class, or an injected parameter) →
  `beans.py` → the channel's bean name. Unresolved → the row derives with `handler` NULL, no
  `fed_by` written (a channel we cannot name is not a channel we can bind).
- **`method_annotation`** — on a root: the constructing method's own annotation supplies a
  capture (`@ServiceActivator(inputChannel)` → `channel_link`, direction outbound).
- **`poisons: [field]`** on a step — the capture is marked unreadable from here on; for
  `channel` the row is unresolved on `path`.

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
into this chain (one hop; a container built in a third bean is `Unresolved`). `compose:` builds
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

- **`continue_via_argument`** — the spec chain reaches `IntegrationFlow.from(spec)`: instead of
  ending there (`terminal_via_argument`), the walk continues along `from(…)`'s own result chain with
  the same captures. (A source spec is consumed by `from` directly, without `build()` — the
  terminal is the `from` call itself, so the entry is `{ via_argument_of: { owner: IntegrationFlow,
  method: from }, continue: true }`; the plan spells one form.)
- **Steps** — declared once on `spring-integration.yml` under `flows.steps`, imported by the three
  broker catalogs (the flow definition is core's — F3, all 35):

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

The AMQP DSL twin: `Amqp.inboundAdapter(ConnectionFactory, String…)` `captures: { channel: arg1 }`;
`(ConnectionFactory, Queue…)` through the `Queue` `channel_via`; `(SimpleMessageListenerContainer)`
/ `(DirectMessageListenerContainer)` through `bean_via`; `Amqp.outboundAdapter(AmqpTemplate)` as a
sink with `exchangeName`/`routingKey` steps and `compose`. Pub/Sub: `from(<bean>)` resolves through
`bean_via` to the §4 root's captures.

**Boundaries stated:** the lambda flow form (`return f -> f.handle(…)`; implicit `<beanName>.input`);
`from(Supplier)`/`from(MessageSource)`; two-hop container sources; `Pattern`/partition
subscriptions; `configureContainer(c -> c.addQueueNames(…))` inside a source spec (a MISS — fewer
queues, never a wrong one); `handle(Object bean, String method)` where the bean is not the
module's.

---

## 6. Catalogs and validation

Three catalogs of `style: fluent`: `spring-integration-pubsub.yml` (detect
`com.google.cloud:spring-cloud-gcp-pubsub`), `spring-integration-amqp.yml`
(`org.springframework.integration:spring-integration-amqp`), `spring-integration-kafka.yml`
(`org.springframework.integration:spring-integration-kafka`), each `measured:` at §9's versions.
`spring-integration.yml` (still `config_join`) gains `flows.steps` — the shared step table — which
the three import by reference (`steps_from: spring-integration`; the loader already lets catalogs
share a shape model by name — the same mechanism). New fluent keys, all optional and validated with
`CatalogError` naming the file: root `new:` (a type; exclusive with `owner`/`method`), root
`direction:`, root `method_annotation: {annotation, arg, into}`, capture values `{ bean_via: argN }`
and `unresolved`, capture fields `channel_link` and `handler`, step `poisons: [fields]`,
`compose: { field: [halves], join }`, `beans:` (roots reachable only through `bean_via`),
`continue_via_argument`/`via_argument_of … continue: true`, `sinks:`. A `direction: inbound`
fluent catalog writes `handler` on its rows; today's outbound catalogs are untouched (byte-identical
goldens are the proof — §10).

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

1. Every new fluent key is optional; the thirteen shipped fluent catalogs declare none and their
   goldens stay byte-identical (the plan lands the keys before any catalog uses them and runs the
   gate). `config_join` changes only in `gaps` (ask only for a `read_by` with no `fed_by`) and the
   `indexed:` form.
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
| D02 | fluent's new keys (`new:` roots, `bean_via`, `channel_link`, `handler`, `poisons`, `compose`, `beans:`, `continue_via_argument`, `sinks:`, `method_annotation`); `config_join`'s `indexed:`; the media-overload verb rules |
| D01 | `channel_bindings` (derived, temp; roles `fed_by`/`read_by`/`sends_to`) |

## 13. Sizing and order

1. `beans.py`; `channel_bindings` + `read_by` from `config_join` + the join pass + `gaps` (inert until fluent writes `fed_by`); fluent's new keys with unit tests and the byte-identical proof.
2. §4 Pub/Sub inbound → outbound → AMQP container hop (CP-27/28 with it).
3. §5 flows: Kafka sources/sinks, steps table, AMQP DSL, `from(bean)`.
4. §7a, §7b (CP-29).
5. Docs, register, COVERAGE.

About the size of B+C (2026-09-18): one new engine of two shapes, three catalogs, two `config_join`
words, three probes, one fixture module extended and one resource file added.
