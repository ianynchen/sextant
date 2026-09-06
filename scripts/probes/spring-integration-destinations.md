# Spring Integration — where a flow's destination and channel names are (and are not) in the fact stream

**Question this probe answers.** Where does a Spring Integration flow send or receive
messages, and is that readable from compiled bytecode alone? The design kept being written
against a prediction; GUIDELINES §8.1 says a framework rule is measured before it is built
on, so this measures it.

**One-line verdict — CURRENT, at extractor scanner_version 9.16.** The channel names survive
perfectly, and **so do the destination names**: every AMQP and Kafka *inbound* destination
reaches the fact stream as the elements of an array argument,
`{"kind":"array","elements":[{"kind":"string","value":"dsl.orders.queue"}]}`, with the same
producer discrimination a single-`String` parameter gives and the arity readable beside it.
The one-line falsifier below returns **3**, not 0. Nested annotation arguments — a
`@Poller`, a `@RabbitListener`'s `@QueueBinding`, a folded `@Schedules` — are readable too.
Two boundaries stand unchanged and are unrelated to either: an XML-configured flow
contributes **zero** facts, and no shipped consumer reads an array's `elements` yet, so
having the facts is not the same as any derivation using them.

> **Superseded, kept as history — the verdict this probe shipped with, measured at 9.14.**
> *"The channel names survive perfectly. **The destination names mostly do not** — every AMQP
> and Kafka inbound destination in Spring Integration is passed through a **varargs
> `String...` parameter**, and a varargs array is `unresolved` in the fact stream. The literal
> is not merely unresolved at the call site; the string is **absent from the fact stream
> entirely**, and all seven ways of spelling the destination collapse to one indistinguishable
> shape."*
>
> That was true of 9.14 and is false of 9.15 onward. **Capability 9.15 shipped BECAUSE of
> it** — it teaches `MethodFlow.argumentJson` the `ANEWARRAY`/`AASTORE` construction the "Why"
> paragraph in Q1 identified as the cause — and the re-run recording the flip is a section of
> this same file, near the end. Everything between here and that section is left exactly as it
> was measured: it is a measurement, not a design, and the 9.14 reading is what the 9.15
> reading is a comparison against. **Read Q1 and Q5 as history and the re-run sections as the
> answer.** A reader who stops at a headline gets the opposite of the truth, which is the §9
> defect this correction closes.

---

## Harness, committed (R7)

`fixtures/spring-integration-probe/` — a standalone Maven fixture, own coordinates
(`com.example:spring-integration-probe`), the same standalone shape `fixtures/grpc-probe`
uses for CP-3/CP-8. Nine classes, deliberately spread across the shapes under test:

| File | What it measures |
| --- | --- |
| `Shape1DslFlows.java` | the Java DSL flow, anonymous channels (Q1, Q4) |
| `Shape2AdapterAndHandler.java` | adapter bean + `@ServiceActivator`, joined by a named channel (Q1, Q2, Q3) |
| `Shape3PolledAndOtherBrokers.java` | `@InboundChannelAdapter` + `@Poller`, Kafka and JMS beside AMQP (Q2, Q5) |
| `AmqpTopologyBeans.java` | `new Queue("…")` / `BindingBuilder` — the non-varargs AMQP spellings |
| `VarianceSources.java` | seven non-literal destination spellings, into a `String...` sink (Q5) |
| `SingleStringControl.java` | the same seven into a single-`String` sink — the control arm (Q5) |
| `Destinations.java` | a compile-time constant and a non-compile-time one |
| `ProbeProperties.java` | a `@ConfigurationProperties` destination holder |
| `ProbeApplication.java` + `src/main/resources/integration-context.xml` | the XML-configured arm |

### Versions this evidence is bounded by (§5.4)

Resolved through the **Spring Boot 3.2.5** BOM, the same Boot line `fixtures/orders-service`
builds against (`mvn -o dependency:list`):

```
org.springframework.integration:spring-integration-core   6.2.4
org.springframework.integration:spring-integration-amqp   6.2.4
org.springframework.integration:spring-integration-kafka  6.2.4
org.springframework.integration:spring-integration-jms    6.2.4
org.springframework.amqp:spring-amqp / spring-rabbit      3.1.4
org.springframework.kafka:spring-kafka                    3.1.4
org.springframework:spring-core / -context / -jms         6.1.6
org.springframework.boot:spring-boot(-autoconfigure)      3.2.5
jakarta.jms:jakarta.jms-api                               3.1.0
javac release 21; extractor scanner_version 9.14
```

Nothing here is asserted beyond those versions. The finding that turns on the shape of a
*method signature* (varargs) would change only if Spring changed those signatures.

### How to re-run

```bash
mvn -q -B -f fixtures/spring-integration-probe/pom.xml compile   # drop -o on a cold ~/.m2
java -jar src/sextant/extractor-jvm/sextant-extractor.jar \
  --module-id com.example:spring-integration-probe \
  --coordinates com.example/spring-integration-probe --version 1.0.0 \
  --classes fixtures/spring-integration-probe/target/classes --out /tmp/si_probe_out \
  > /tmp/si_probe_report.json
```

Report: `{"documents":9,"facts":284,"scanner_id":"asm","scanner_version":"9.14","uncovered":[]}`
— 140 `call_site`, 93 `symbol`, 49 `annotation`, 9 `document`, 2 `field_write`. The one-line
falsifier is reproducible without reading any JSON:

```bash
grep -r "dsl.orders.queue\|bean.orders.queue\|kafka.orders.topic" /tmp/si_probe_out | wc -l   # -> 0
```

---

## Q1 — Destination literals

### Verdict: **FALSIFIED for the inbound adapters of both shapes; CONFIRMED for outbound and for non-varargs setters.**

The dividing line is not DSL-vs-bean and not AMQP-vs-Kafka-vs-JMS. It is **whether the API
parameter is `String...` or `String`.**

**Shape 1, inbound — the literal is gone.** `Amqp.inboundAdapter(ConnectionFactory, String... queueNames)`:

```json
{"kind":"call_site","caller":"…/Shape1DslFlows#ordersInboundDslFlow(sig_e0da9c6d).",
 "invoke_kind":"static","ordinal":0,"receiver":null,"result":9,
 "target":{"owner":"org/springframework/integration/amqp/dsl/Amqp#","name":"inboundAdapter",
   "descriptor":"(Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;[Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpInboundChannelAdapterSMLCSpec;"},
 "arguments":[{"kind":"parameter","value":0},{"kind":"unresolved"}]}
```

Source was `Amqp.inboundAdapter(connectionFactory, "dsl.orders.queue")`. Argument position 1
is `unresolved` — **and note it has no `source` key**, so there is not even an instruction id
to chase. `"dsl.orders.queue"` appears in **no fact of any kind**.

**Shape 2, inbound — the literal is gone, identically.** `SimpleMessageListenerContainer.setQueueNames(String...)`:

```json
{"kind":"call_site","caller":"…/Shape2AdapterAndHandler#ordersContainer(sig_5375941c).",
 "invoke_kind":"virtual","ordinal":1,"receiver":2,"result":null,
 "target":{"owner":"org/springframework/amqp/rabbit/listener/SimpleMessageListenerContainer#",
           "name":"setQueueNames","descriptor":"([Ljava/lang/String;)V"},
 "arguments":[{"kind":"unresolved"}]}
```

**Kafka inbound — same, and worse: two topics collapse into one `unresolved` slot.**
`Kafka.messageDrivenChannelAdapter(ConsumerFactory, String... topics)` called with
`"kafka.orders.topic", "kafka.orders.retry.topic"`:

```json
{"arguments":[{"kind":"parameter","value":0},{"kind":"unresolved"}],
 "target":{"owner":"org/springframework/integration/kafka/dsl/Kafka#","name":"messageDrivenChannelAdapter",
   "descriptor":"(Lorg/springframework/kafka/core/ConsumerFactory;[Ljava/lang/String;)L…KafkaMessageDrivenChannelAdapterListenerContainerSpec;"}}
```

The arity is unreadable too: one `unresolved` says nothing about whether the flow consumes
one topic or twenty.

**Why** — this is a property of the extractor, confirmed against the bytecode rather than
inferred. `javap -c` of `ordersContainer`:

```
10: iconst_1
11: anewarray  #12   // class java/lang/String
14: dup
15: iconst_0
16: ldc        #14   // String bean.orders.queue
18: aastore
19: invokevirtual  setQueueNames:([Ljava/lang/String;)V
```

The value reaching the argument slot is produced by `ANEWARRAY`, not by the `LDC`.
`MethodFlow.argumentJson`'s `TypeInsnNode` branch matches `Opcodes.NEW` only, so `ANEWARRAY`
falls through every branch to the closing `switch`'s `default -> argument("unresolved", null, null, null)`.
The `AASTORE`d element is never inspected by any pass. This is a general varargs gap, not a
Spring Integration one.

**Where the literal DOES survive — every single-`String` parameter.** All of these are exact,
verbatim, first-argument-position reads:

```json
{"target":{"owner":"org/springframework/integration/amqp/dsl/AmqpOutboundChannelAdapterSpec#","name":"exchangeName",
           "descriptor":"(Ljava/lang/String;)L…AmqpBaseOutboundEndpointSpec;"},
 "arguments":[{"kind":"string","value":"dsl.shipments.exchange"}],"receiver":6,"result":10}

{"target":{"owner":"org/springframework/integration/amqp/dsl/AmqpOutboundChannelAdapterSpec#","name":"routingKey",
           "descriptor":"(Ljava/lang/String;)L…"},"arguments":[{"kind":"string","value":"dsl.shipments.rk"}],"receiver":10,"result":15}

{"target":{"owner":"org/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec#","name":"topic",
           "descriptor":"(Ljava/lang/String;)L…"},"arguments":[{"kind":"string","value":"kafka.shipments.topic"}]}

{"target":{"owner":"org/springframework/integration/jms/dsl/JmsInboundChannelAdapterSpec$JmsInboundChannelSpecTemplateAware#",
           "name":"destination","descriptor":"(Ljava/lang/String;)L…"},
 "arguments":[{"kind":"string","value":"jms.orders.queue"}]}

{"target":{"owner":"org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec$JmsOutboundChannelSpecTemplateAware#",
           "name":"destination","descriptor":"(Ljava/lang/String;)L…"},
 "arguments":[{"kind":"string","value":"jms.shipments.queue"}]}
```

**JMS inbound is fully readable and AMQP/Kafka inbound is not** — because JMS spells the
destination as a builder method `.destination(String)` while AMQP and Kafka spell it as a
varargs factory parameter. Any mechanism must be told this per adapter; there is no uniform
"the destination is argument N" rule across brokers.

**The non-varargs AMQP spellings are readable too**, which matters because it is the only
route by which an AMQP queue name reaches the facts at all:

```json
{"caller":"…/AmqpTopologyBeans#topologyOrdersQueue(sig_babe1e9d).","invoke_kind":"special","receiver":2,
 "target":{"owner":"org/springframework/amqp/core/Queue#","name":"<init>","descriptor":"(Ljava/lang/String;Z)V"},
 "arguments":[{"kind":"string","value":"topology.orders.queue"},{"kind":"boolean","value":true}]}

{"target":{"owner":"org/springframework/amqp/core/TopicExchange#","name":"<init>","descriptor":"(Ljava/lang/String;)V"},
 "arguments":[{"kind":"string","value":"topology.orders.exchange"}]}

{"target":{"owner":"org/springframework/amqp/core/BindingBuilder$TopicExchangeRoutingKeyConfigurer#","name":"with",
           "descriptor":"(Ljava/lang/String;)Lorg/springframework/amqp/core/Binding;"},
 "arguments":[{"kind":"string","value":"topology.orders.rk"}],"receiver":7,"result":11}
```

But the hop that would connect a declared `Queue` bean to the container that consumes it is
`setQueues(Queue...)` — varargs again, so it is lost as well, and this time even the bean
reference is lost, not just a string:

```json
{"target":{"owner":"org/springframework/amqp/rabbit/listener/SimpleMessageListenerContainer#","name":"setQueues",
           "descriptor":"([Lorg/springframework/amqp/core/Queue;)V"},
 "arguments":[{"kind":"unresolved"}],"receiver":2}
```

---

## Q2 — Channel names from annotations

### Verdict: **CONFIRMED, exactly and completely.**

`@ServiceActivator`'s and `@InboundChannelAdapter`'s channel arguments are ordinary
`annotation`-fact args, verbatim, keyed by attribute name:

```json
{"kind":"annotation","retention":"runtime",
 "target":"sextant-jvm maven com.example/spring-integration-probe 1.0.0 com/example/siprobe/Shape2AdapterAndHandler#handleOrder(sig_7b622a99).",
 "use":{"annotation":"org/springframework/integration/annotation/ServiceActivator#",
        "args":{"inputChannel":"amqpInputChannel","outputChannel":"amqpAuditChannel"}}}

{"kind":"annotation","retention":"runtime",
 "target":"…/Shape3PolledAndOtherBrokers#tick(sig_0e30dfc9).",
 "use":{"annotation":"org/springframework/integration/annotation/InboundChannelAdapter#",
        "args":{"channel":"tickChannel"}}}
```

Both output and input channels are present. A constant-valued channel name is inlined by
javac and reads identically to a literal — `@ServiceActivator(inputChannel = Destinations.ORDERS_CHANNEL)`
gives `"args":{"inputChannel":"constOrdersChannel"}`, which is the value, not the constant's
name. A placeholder survives verbatim and unresolved, which is the honest answer:
`@ServiceActivator(inputChannel = "${probe.audit-channel}")` gives
`"args":{"inputChannel":"${probe.audit-channel}"}`.

### Caveat found in passing: **nested annotation arguments are silently dropped.**

The source is `@InboundChannelAdapter(channel = "tickChannel", poller = @Poller(fixedDelay = "5000"))`.
The fact carries `channel` and **not** `poller` — there is no key for it at all.
`ClassScanner.useCollectingVisitor` overrides `visit`, `visitEnum` and `visitArray` but not
`visitAnnotation`, so ASM's nested-annotation callback returns `null` and the whole nested
value vanishes without a trace. Anything reading `@Poller`, or any other annotation-valued
attribute, cannot do so today. Reported, not fixed — this probe modifies nothing under `src/`
or `extractor-jvm/`.

---

## Q3 — The join, for Shape 2

### Verdict: **CONFIRMED — the channel name appears on BOTH sides, with the same string.**

This is the one part of the hypothesis that measured out exactly as predicted. The adapter
side:

```json
{"kind":"call_site","caller":"…/Shape2AdapterAndHandler#ordersInboundAdapter(sig_4eda9f33).",
 "invoke_kind":"virtual","ordinal":1,"receiver":2,"result":null,
 "target":{"owner":"org/springframework/integration/amqp/inbound/AmqpInboundChannelAdapter#",
           "name":"setOutputChannelName","descriptor":"(Ljava/lang/String;)V"},
 "arguments":[{"kind":"string","value":"amqpInputChannel"}]}
```

The handler side (above): `"args":{"inputChannel":"amqpInputChannel", …}`. Same literal, both
sides, joinable on the string. `setOutputChannelName(String)` is single-argument, so it
escapes the varargs problem entirely.

**But the join is only half a fact.** It connects an adapter bean to a handler method; it does
**not** carry a destination, because the destination lives on the container the adapter wraps
(`setQueueNames`), and that is the varargs call that resolved to `unresolved`. So for Shape 2
the fact stream says *"this handler is fed by this adapter"* and cannot say *"…from
`bean.orders.queue`"*. **The join you hypothesised exists. The thing you wanted to join to
does not.**

---

## Q4 — Shape 1's connection with anonymous channels

### Verdict: **CONFIRMED as recoverable — a within-method chain join on `result` ↔ `receiver` / `arguments[].source`.**

The DSL chain reconstructs exactly, with no channel name anywhere, because the extractor
assigns each call's produced value an id (`result`) and records the id each call consumes
(`receiver`, or `arguments[].source`). `ordersInboundDslFlow` in full:

| ordinal | target | receiver | result | notable argument |
| --- | --- | --- | --- | --- |
| 0 | `Amqp#inboundAdapter` | – | **9** | `[{parameter 0},{unresolved}]` |
| 1 | `IntegrationFlow#from` | – | **10** | `[{"kind":"unresolved","source":9}]` |
| 2 | `LambdaMetafactory#handle` (indy) | – | 12 | – |
| 3 | `IntegrationFlowBuilder#handle` | **10** | **15** | `[{class String},{"kind":"lambda","source":12,"symbol":"…#lambda$ordersInboundDslFlow$0(sig_1fee8f7b)."}]` |
| 4 | `LambdaMetafactory#handle` (indy) | – | 18 | – |
| 5 | `IntegrationFlowBuilder#handle` | **15** | **21** | `[{class String},{"kind":"lambda","source":18,"symbol":"…#lambda$ordersInboundDslFlow$1(…)."}]` |
| 6 | `IntegrationFlowBuilder#get` | **21** | 25 | – |

`9 → from(source:9) → 10 → handle(receiver:10) → 15 → handle(receiver:15) → 21 → get(receiver:21)`.
Unbroken, deterministic, no name matching. The handler bodies are named too: `{"kind":"lambda","symbol":"…#lambda$…$0(…)."}`
points at the synthetic method holding the handler code, and that method is itself a `symbol`
fact with its own `call_site` facts (`lambda$ordersInboundDslFlow$0` contains
`java/lang/String#toUpperCase`). So the flow's *topology* is fully recoverable; only its
*destination* is not.

**Two breaks worth naming:**

1. **A flow written as a lambda bean loses the link from bean method to flow body.** For
   `@Bean IntegrationFlow shipmentsOutboundDslFlow(AmqpTemplate t) { return flow -> flow.handle(…); }`
   the whole chain lives in the synthetic `lambda$shipmentsOutboundDslFlow$0`, a *different*
   `caller` symbol. The bean method's only call site is the indy, and an indy's target is
   recorded as `{"owner":"java/lang/invoke/LambdaMetafactory#","name":"configure"}` with **no
   implementation symbol** — the implementation symbol is written only when the lambda value
   is consumed *as an argument*, and here it is returned. The link survives as the
   `lambda$<method>$<n>` naming convention alone, which is a javac convention, not a fact.
2. **A named channel in the DSL is readable**, so "the DSL cannot name channels" would be
   wrong: `.channel("dslNamedChannel")` reads
   `{"target":{"owner":"org/springframework/integration/dsl/IntegrationFlowBuilder#","name":"channel"},"arguments":[{"kind":"string","value":"dslNamedChannel"}]}`.
   Shape 1 and Shape 2 are therefore not two disjoint worlds; a real app mixes them.

---

## Q5 — Variance: where the destination comes from when it is not a literal

### Verdict: **FALSIFIED, and this is the sharpest result in the probe.**

`VarianceSources` calls `Amqp.inboundAdapter` seven times with seven genuinely different
expressions. **All seven emit a byte-for-byte identical argument list.**

| # | source expression | emitted `arguments` |
| --- | --- | --- |
| a | `Destinations.ORDERS_QUEUE` (compile-time constant, inlined by javac) | `[{"kind":"parameter","value":0},{"kind":"unresolved"}]` |
| b | `Destinations.LATE_QUEUE` (static final, *not* compile-time) | identical |
| c | `this.valueQueue` (`@Value`-injected field) | identical |
| d | `paramQueue` (`@Value`-annotated bean-method parameter) | identical |
| e | `"${probe.placeholder-queue}"` (a literal placeholder) | identical |
| f | `this.properties.getQueue()` (`@ConfigurationProperties` getter) | identical |
| g | `env + ".orders.queue"` (concatenation) | identical |

The varargs array erases the distinction *before* any of the extractor's producer branches
run, so the fact stream cannot even distinguish **"the destination was a hard-coded literal"**
from **"the destination is externally configured and unknowable"**. That distinction is
normally exactly what `unresolved` is for — the value being genuinely unknown is a fact worth
reporting — and here it is unavailable in both directions.

**Where the variance IS visible — measured, not predicted.** `SingleStringControl` sends the
same seven expressions (plus a plain literal) into a **single-`String`** sink,
`JmsOutboundChannelAdapterSpec#destination(String)`, so the difference is attributable to the
varargs array and nothing else. Every one of them discriminates:

| source expression | emitted argument at `destination(String)` |
| --- | --- |
| `"control.literal.queue"` | `{"kind":"string","value":"control.literal.queue"}` |
| `Destinations.ORDERS_QUEUE` (compile-time constant) | `{"kind":"string","value":"const.orders.queue"}` |
| `Destinations.LATE_QUEUE` (static final, not compile-time) | `{"kind":"field","symbol":"com/example/siprobe/Destinations#LATE_QUEUE."}` |
| `this.valueQueue` (`@Value` field) | `{"kind":"field","symbol":"com/example/siprobe/SingleStringControl#valueQueue."}` |
| `paramQueue` (`@Value` parameter) | `{"kind":"parameter","value":1}` |
| `"${probe.placeholder-queue}"` | `{"kind":"string","value":"${probe.placeholder-queue}"}` |
| `this.properties.getQueue()` | `{"kind":"unresolved","source":7}` — and instruction 7 is its own `call_site` fact, `{"target":{"owner":"com/example/siprobe/ProbeProperties#","name":"getQueue"}}` |
| `env + ".orders.queue"` | `{"kind":"unresolved","source":6}` — instruction 6 is the `StringConcatFactory` indy |

Note the second row: a compile-time constant arrives as its **value**, and the constant's
*name* is gone — the same result CP-8(b) recorded for `SERVICE_NAME`. A mechanism cannot tell
row 1 from row 2. Rows 3 and 4 keep the symbol and lose the value; rows 7 and 8 keep a
followable `source` and lose both.


The two placeholder-bearing spellings are separately recoverable, but never from the adapter
call site:

```json
{"kind":"annotation","target":"…/VarianceSources#valueQueue.",
 "use":{"annotation":"org/springframework/beans/factory/annotation/Value#","args":{"value":"${probe.value-queue}"}}}
```

and on a bean-method parameter, inline in the method's `symbol` fact rather than as a fact of
its own:

```json
{"kind":"symbol","construct_kind":"method","symbol":"…/VarianceSources#valueParameterQueueFlow(sig_06c86cd7).",
 "signature":{"parameters":[
   {"name":"connectionFactory","annotations":[],"type":{"symbol":"org/springframework/amqp/rabbit/connection/ConnectionFactory#",…}},
   {"name":"paramQueue","type":{"symbol":"java/lang/String#","wire_type":"string",…},
    "annotations":[{"annotation":"org/springframework/beans/factory/annotation/Value#",
                    "args":{"value":"${probe.param-queue}"}}]}]}}
```

So `${probe.param-queue}` is on disk — but nothing in the facts links it to the
`Amqp.inboundAdapter` call site it feeds, because the argument slot that would carry
`{"kind":"parameter","value":1}` is the erased array.

**And even when the slot is not erased, the join to `@Value` is not free.** In
`SingleStringControl` the flow body is a lambda, so the resolved argument
`{"kind":"parameter","value":1}` numbers a parameter of the *synthetic* method
`lambda$controlValueParameter$0`, whose own `symbol` fact reads
`[{"name":null,"type":"jakarta/jms/ConnectionFactory#","annotations":[]},{"name":null,"type":"java/lang/String#","annotations":[]},{"name":null,"type":"org/springframework/integration/dsl/IntegrationFlowDefinition#","annotations":[]}]`
— names `null`, annotations empty. The `@Value` lives on the *enclosing bean method's*
parameter (`{"name":"paramQueue","annotations":[{"annotation":"…/Value#","args":{"value":"${probe.param-queue}"}}]}`).
Bridging the two means relying on javac's convention that captures are prefixed in
declaration order ahead of the SAM parameters; that ordering is not stated by any fact.

### The XML arm

`src/main/resources/integration-context.xml` declares a complete AMQP flow
(`queue-names="xml.orders.queue"`, `channel="xmlOrdersChannel"`, a service activator).
The scan reports `"documents":9` — one per class file, none for the XML. **An XML-configured
flow contributes exactly zero facts.** The extractor reads `target/classes/**/*.class`; the
XML is a resource sitting beside them, never parsed. Whatever mechanism is built, XML-configured
Spring Integration is outside bytecode extraction by construction, and would need a resource
reader of its own — the same category as the `.avsc` reader.

---

## Q6 — What the hypothesis got wrong

Stated plainly, because this is the deliverable that matters.

1. **"The destination is a string literal at a call site, and Sextant already records those"
   is wrong for the primary case.** It is right about *outbound* adapters and about JMS. It is
   wrong about **every AMQP and Kafka inbound destination**, in both shapes, because those
   APIs take `String...`. `grep` finds zero occurrences of `dsl.orders.queue`,
   `bean.orders.queue` or `kafka.orders.topic` anywhere in the emitted facts.
2. **The gap is a varargs gap, not a Spring Integration gap.** It is `MethodFlow.argumentJson`
   not modelling `ANEWARRAY`/`AASTORE`. It will bite identically for every other framework
   whose API takes `String... topics` / `String... queues` / `String... destinations` —
   `@KafkaListener` array attributes, `JmsListener`, anything similar. Fixing it once fixes it
   everywhere; working around it per-framework would be paying for the same thing repeatedly.
3. **The varargs `unresolved` is worse than an ordinary `unresolved`.** It carries **no
   `source`**, so unlike a chained builder call (`{"kind":"unresolved","source":15}`) there is
   no instruction id to follow. There is nothing to join to and nothing to degrade to.
4. **The two shapes do not need two different destination mechanisms — they need the same
   one, and it is missing for both.** They differ only in the *connection* mechanism (Shape 1:
   a within-method `result`/`receiver` chain; Shape 2: a channel-name string join). Both of
   those work today.
5. **`@Poller` and every other annotation-valued attribute is silently absent** — the
   annotation collector has no `visitAnnotation` override. This was not in the hypothesis at
   all.
6. **The good news the hypothesis under-claimed:** the DSL's anonymous-channel chain is
   *fully* reconstructable without any names, and the Shape 2 named-channel join holds on both
   sides exactly as predicted.

---

## What a correct mechanism would have to read

Stated as observations of the fact stream, not as a design.

**For the connection (both shapes, works today):**

- Shape 1 needs the within-method value-id join: a call's `result` equals the next call's
  `receiver`, or equals an `arguments[i].source`. That reaches from the adapter factory
  through `IntegrationFlow#from` and every `IntegrationFlowBuilder` call to `get()`, and names
  the handler bodies through `{"kind":"lambda","symbol":…}`.
- Shape 2 needs a string join across two fact kinds: a `call_site` argument at
  `setOutputChannelName(String)`/`setInputChannelName(String)` on one side, and an
  `annotation` fact's `args.inputChannel`/`args.outputChannel` on the other. A DSL
  `.channel("…")` argument participates in the same join, so the two shapes are not disjoint.
- Neither join is name-based guessing; both are exact.

**For the destination (does not work today):**

- Where the destination is a **single-`String`** parameter — `.destination(…)`, `.topic(…)`,
  `.exchangeName(…)`, `.routingKey(…)`, `new Queue(…)`, `new TopicExchange(…)`,
  `BindingBuilder…with(…)` — a mechanism reads `arguments[N]` and gets a full producer
  discrimination: `string` / `field` / `parameter` / `unresolved`+`source`. Which N, and
  which method, differs per adapter and per broker; there is no uniform position.
- Where the destination is a **`String...` parameter** — `Amqp.inboundAdapter`,
  `Kafka.messageDrivenChannelAdapter`, `setQueueNames`, `setQueues` — **there is nothing to
  read.** No literal, no source id, no arity. A mechanism reading this today can only report
  "an AMQP inbound adapter exists in this flow, destination unknown", and cannot distinguish
  that from a genuinely dynamic destination.
- Recovering it requires the *extractor* to model array construction at an argument slot:
  when the producer is `ANEWARRAY`/`NEWARRAY` and every `AASTORE` into it before the invoke is
  a resolvable value, the slot is an array of those values. That is a `MethodFlow` capability,
  not a catalog row, and it is a prerequisite to any Spring Integration destination work
  rather than something a derivation can route around.
- Independently, `@Value` placeholders reach the facts (on a field's `annotation` fact, or
  inline on a `symbol` fact's parameter) but are joinable to a call site only through the
  ordinary `field`/`parameter` argument kinds — which is another thing the varargs array
  currently erases.
- An XML-configured flow is not in scope for any bytecode mechanism at all; it needs a
  resource reader.

---

## Re-run after extractor capability 9.15 — 2026-09-04

Everything above records what the fact stream said at **scanner_version 9.14**, and it is
left unedited: it is a measurement, not a design. This section records the same harness
re-run against **9.15**, which teaches `MethodFlow.argumentJson` the `ANEWARRAY`/`AASTORE`
construction Q1's "Why" paragraph identified as the cause.

One fixture change, and it is the reason the comparison is now row-for-row: `VarianceSources`
gained a **plain literal** bean (`literalQueueFlow`, `"variance.literal.queue"`), which the
control arm always had and the varargs arm did not. Eight spellings each side now.

```
Report: {"documents":9,"facts":292,"scanner_id":"asm","scanner_version":"9.15","uncovered":[]}
        — 145 call_site, 95 symbol, 50 annotation, 9 document, 2 field_write
```

The one-line falsifier **flips**, which is the whole verdict:

```bash
grep -r "dsl.orders.queue\|bean.orders.queue\|kafka.orders.topic" /tmp/si_probe_out | wc -l   # -> 3   (was 0)
```

### Q5's table, re-measured — the varargs arm now discriminates all eight

Same eight expressions, same `Amqp.inboundAdapter(ConnectionFactory, String...)` sink,
argument position 1:

| # | source expression | emitted `arguments[1]` |
| --- | --- | --- |
| 0 | `"variance.literal.queue"` | `{"elements":[{"kind":"string","value":"variance.literal.queue"}],"kind":"array"}` |
| a | `Destinations.ORDERS_QUEUE` (compile-time constant) | `{"elements":[{"kind":"string","value":"const.orders.queue"}],"kind":"array"}` |
| b | `Destinations.LATE_QUEUE` (static final, not compile-time) | `{"elements":[{"kind":"field","symbol":"com/example/siprobe/Destinations#LATE_QUEUE."}],"kind":"array"}` |
| c | `this.valueQueue` (`@Value` field) | `{"elements":[{"kind":"field","symbol":"com/example/siprobe/VarianceSources#valueQueue."}],"kind":"array"}` |
| d | `paramQueue` (`@Value` parameter) | `{"elements":[{"kind":"parameter","value":1}],"kind":"array"}` |
| e | `"${probe.placeholder-queue}"` | `{"elements":[{"kind":"string","value":"${probe.placeholder-queue}"}],"kind":"array"}` |
| f | `this.properties.getQueue()` | `{"elements":[{"kind":"unresolved","source":9}],"kind":"array"}` |
| g | `env + ".orders.queue"` | `{"elements":[{"kind":"unresolved","source":8}],"kind":"array"}` |

Compare row for row with the control arm's table in Q5: **identical discrimination**, with
each answer wrapped in the array slot it actually occupies. Rows 0 and a still collapse to
each other, and that is javac inlining a compile-time constant — the same collapse the
single-`String` control arm has, recorded there as "a mechanism cannot tell row 1 from row 2".
It is not a varargs property and 9.15 does not change it. The control arm itself re-measures
byte-identical: nothing outside an array-valued slot moved.

### What else the flip recovers

- **Shape 1** — `Amqp.inboundAdapter`: `[{"kind":"parameter","value":0},{"elements":[{"kind":"string","value":"dsl.orders.queue"}],"kind":"array"}]`.
- **Shape 2** — `setQueueNames(String...)`: `[{"elements":[{"kind":"string","value":"bean.orders.queue"}],"kind":"array"}]`. Q3's "the join you hypothesised exists, the thing you wanted to join to does not" is now half wrong in the good direction: the destination is there.
- **Kafka, and the arity with it** — `Kafka.messageDrivenChannelAdapter`: `{"elements":[{"kind":"string","value":"kafka.orders.topic"},{"kind":"string","value":"kafka.orders.retry.topic"}],"kind":"array"}`. Two topics read as two elements; Q1's "the arity is unreadable too" no longer holds.
- **`setQueues(Queue...)`** — `{"elements":[{"kind":"parameter","value":1}],"kind":"array"}`. Not a string, and it was never going to be: it is a bean reference, and the element now names the parameter carrying it, where before even that was erased.

### What did NOT change, and stays a stated boundary

- **The XML arm** still contributes zero facts. Unrelated to varargs.
- **Nested annotation arguments** (`@Poller`) are still silently dropped — Q2's caveat is untouched; 9.15 is a `MethodFlow` change and that gap is in `ClassScanner.useCollectingVisitor`.
- **A `@Value` placeholder still does not join to the call site by itself.** `{"kind":"parameter","value":1}` inside `elements` numbers a parameter exactly as the control arm's did, so Q5's closing note about bridging a lambda's synthetic parameters to the enclosing bean method's `@Value` applies unchanged.
- **The consumers have not moved.** `spring-webflux-router.yml`'s `media_values` table and `kafka-consumer.yml`'s `all_strings` read positional arguments, not `elements`, so their derived output is byte-identical. The facts are there; reading them is engine work.

### Bounds (§5.4)

Same fixture, same BOM (Spring Boot 3.2.5, Spring Integration 6.2.4, spring-amqp 3.1.4,
spring-kafka 3.1.4, Spring Framework 6.1.6), **javac release 21**, extractor
scanner_version 9.15. The array-construction shape 9.15 reads is javac's, and it is the
shape the JVM specification requires any compiler to emit for a varargs call site — but
only javac 21 was measured. A compiler that spilled the array through a local, populated it
across a branch, or reordered the stores would fall to the near-miss rules and read
`unresolved`, which is the honest degradation rather than a wrong answer.

---

## Re-run after extractor capability 9.16 — 2026-09-04

Q2's caveat above — *"nested annotation arguments are silently dropped"* — is the thing
this section closes. It was reported, not fixed, when the probe was written, and the
9.15 re-run listed it under "what did NOT change" because 9.15 is a `MethodFlow` change
and the gap was in `ClassScanner.useCollectingVisitor`. Both earlier measurements are
left unedited.

**One missing override, three separate losses.** `useCollectingVisitor` overrode `visit`,
`visitEnum` and `visitArray` but not `visitAnnotation`, so ASM's nested-annotation
callback returned `null` and the value vanished **with no key at all** — not even an
`unresolved` to chase. Capability 9.16 adds the override, at both levels (a scalar
argument and an element inside an array), recursively.

One fixture class added, `NestedAnnotationShapes.java`, carrying the two shapes the
harness did not already have; the polled adapter Q2 measured is unchanged on
`Shape3PolledAndOtherBrokers#tick`.

```
Report: {"documents":10,"facts":302,"scanner_id":"asm","scanner_version":"9.16","uncovered":[]}
        — 146 call_site, 100 symbol, 54 annotation, 10 document, 2 field_write
```

Nothing gained a **fact** — a dropped nested value never removed the annotation fact that
should have carried it, only its key. Scanning this same fixture with a 9.15 jar and a
9.16 jar and sorting each stream, `call_site`, `symbol` and `field_write` are
**byte-identical** (md5-equal, all three), and exactly **three** `annotation` facts differ:
the three below.

### Loss 1 — `@Poller` inside `@InboundChannelAdapter`, the one Q2 measured

```json
{"kind":"annotation","retention":"runtime",
 "target":"…/Shape3PolledAndOtherBrokers#tick(sig_0e30dfc9).",
 "use":{"annotation":"org/springframework/integration/annotation/InboundChannelAdapter#",
        "args":{"channel":"tickChannel",
                "poller":{"annotation":"org/springframework/integration/annotation/Poller#",
                          "args":{"fixedDelay":"5000"}}}}}
```

The nested value carries **its own fqn and its own args**, in the same
`{"annotation":…,"args":{…}}` shape the outer use has. Q2's `channel` is byte-identical to
what it was; `poller` is the added key.

### Loss 2 — the queue name inside `@RabbitListener`, three levels down

`@RabbitListener(bindings = @QueueBinding(value = @Queue(name = …, arguments = @Argument(…))))`
is the deepest nesting the estate produces, and for this listener it is the **only** place
an AMQP queue name is written — there is no `setQueueNames` call site to fall back to, so
before 9.16 the name was unreachable by any route at all:

```json
{"use":{"annotation":"org/springframework/amqp/rabbit/annotation/RabbitListener#","args":{"bindings":[
  {"annotation":"…/QueueBinding#","args":{
    "exchange":{"annotation":"…/Exchange#","args":{"name":"nested.orders.exchange","type":"topic"}},
    "key":["nested.orders.rk"],
    "value":{"annotation":"…/Queue#","args":{
      "arguments":[{"annotation":"…/Argument#","args":{"name":"x-dead-letter-exchange",
                                                        "value":"nested.orders.dlx"}}],
      "durable":"true","name":"nested.orders.queue"}}}}]}}}
```

Note `bindings` and `arguments`: **arrays of annotations**, so 9.15's array handling and
9.16 compose — and `key` is an array of plain strings beside them, unchanged.

### Loss 3 — every trigger on a method with two `@Scheduled`, the sharpest case

`@Scheduled` is `@Repeatable`, so **javac folds two or more onto one method into a single
`@Schedules`** holding an array of them (JLS 9.7.5). Verified against this fixture's own
bytecode with `javap -v` before it was pinned. A method with one schedule was readable
before 9.16; a method with two carried **no trigger at all**:

```json
{"target":"…/NestedAnnotationShapes#twoTriggers(sig_da8c82d5).",
 "use":{"annotation":"org/springframework/scheduling/annotation/Schedules#","args":{"value":[
   {"annotation":"…/Scheduled#","args":{"cron":"0 0 * * * *"}},
   {"annotation":"…/Scheduled#","args":{"fixedRate":5000}}]}}}
```

Both triggers, both expressions. The control arm beside it — `singleTrigger`, one
`@Scheduled` — is still an unwrapped `{"annotation":"…/Scheduled#","args":{"cron":"0 15 * * * *"}}`,
which is what makes the loss a defect rather than a uniform limitation. Note that only
**explicitly written** elements are stored: `@Scheduled(fixedRate = 5000L)` carries
`fixedRate` and no `cron`, because annotation defaults never reach the class file.

A falsifier in the same one-line style as Q1's:

```bash
grep -r "nested.orders.queue\|0 0 \* \* \* \*" /tmp/si_probe_out | wc -l   # -> 2   (was 0)
```

### The bound, and what is emitted at it

The recursion is capped at **five levels of nesting below the outermost annotation** —
past the deepest shape here (`@RabbitListener` → `@QueueBinding` → `@Queue` → `@Argument`,
depth 3). The language bounds nesting on its own, because javac rejects a cyclic
annotation element type, but a class file need not have come from javac and an unbounded
descent is a stack overflow mid-scan rather than a fact. At the bound the value is
`{"annotation":"<fqn>","unresolved":"depth_limit"}`: the type was read off the descriptor
and is kept, the arguments were never read and get **no `args` key** — an empty `args`
would be indistinguishable from an annotation genuinely written with none (§8). Nothing
in this fixture reaches it; the extractor's own `NestedAnnotated` fixture carries a
seven-deep chain that does.

### What did NOT change

- **The XML arm** still contributes zero facts. Unrelated to annotations.
- **Q1 and Q5 are untouched.** 9.16 is a `ClassScanner` change; every `call_site`,
  `symbol` and `field_write` fact in the harness is byte-identical to its 9.15 form,
  checked by scanning the fixture with both jars rather than reasoned from the diff.
- **The consumers have not moved.** No catalog reads a nested use yet, so no derived
  output changed. The facts are there; reading them is engine work.

### Bounds (§5.4)

Same fixture, same BOM (Spring Boot 3.2.5, Spring Integration 6.2.4, spring-amqp 3.1.4,
spring-kafka 3.1.4, Spring Framework 6.1.6), **javac release 21** — compiled here by
javac 26.0.2.1 with `--release 21`, which is what the `@Repeatable` folding above was
confirmed against — extractor scanner_version 9.16. The folding is required of every
conforming compiler by JLS 9.7.5 rather than being a javac choice, but only this compiler
was measured. The nested-annotation encoding itself is JVMS 4.7.16.1's `element_value`
with tag `@`, which ASM surfaces as `visitAnnotation` for every class file regardless of
producer.
