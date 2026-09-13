# W19 — the per-catalog enumeration pass (F2 §3.8)

Run: `scripts/probes/w19_catalog_surface/run.sh`. Everything below the rule is that
script's own output, pasted verbatim.

**Version scope (§5.4).** Read against **spring-jms 6.1.6**, **spring-amqp 3.1.4**,
**spring-rabbit 3.1.4**, **spring-cloud-aws-sqs 3.1.1**, **spring-cloud-gcp-pubsub
5.1.2**, **spring-webflux 6.1.6**, **sqs 2.25.31**, **kafka-streams 3.6.2** (added
2026-09-12 for `G-31`, w60), **javalin 6.4.0** (added 2026-09-12 for
`javalin-routing`, w61) and — added 2026-09-12 for `alpakka-pekko`, w62 —
**pekko-connectors-kafka_2.13 1.1.0** — each self-reported by the
archive, from `Implementation-Version:` where the publisher writes one, from
Maven's `pom.properties` where it does not (the AWS SDK writes no manifest version at
all), or from Kafka Streams' own `kafka/kafka-streams-version.properties` where it
writes neither (Javalin and pekko-connectors-kafka both write a manifest
`Implementation-Version:`). The run ABORTS when a jar's self-report disagrees with the
coordinate that resolved it. Every version here is one the catalog it measures already
names in its own `measured:` block, except the three that had none — so a surface
counted here is bounded by the same evidence as the rules it is counted against. A
release between any two of these is unverified: a class gaining a method changes the
denominator.

## The question, and why a slice needs a run to answer it

§3.8 ships six catalogs with a declared slice and says the cost is part of the work:
*"you cannot write a slice without enumerating the framework's surface."* This is that
enumeration for every slice that is a question about **methods on an owner type**.

A catalog with no slice claims its framework entire. A catalog with a slice written
from memory claims whatever its author last looked at. **Both read identically to a
consumer**, which is the whole reason presence has to stop meaning completeness. Both
halves of every ratio below come from the run — the surface out of the jar's bytecode,
the coverage out of the catalog as LOADED — so "reads 1 of 37" is measured rather than
maintained.

## The two things this probe got wrong before it got them right

Both are recorded because each would have shipped a confident number that was false,
and both are the shape this wave keeps finding.

**A silent filter that shrank both sides of the ratio.** The first signature pattern
did not allow for a `throws` clause. Every `JmsTemplate` method declares `throws
JmsException`, so none of them parsed — and the probe printed *"reads 0 of 27"* for a
catalog that plainly reads `convertAndSend`, because the method it reads had been
dropped from the denominator too. A skipped line now aborts the run instead (the guard in
`_members`), because a filter that quietly shrinks a published ratio is worse than no
ratio.

**A candidate test mirrored onto an API it does not fit.** Section 2 splits the unread
methods by whether they take a `String` at argument 0 — true of every
destination-carrying method on the Spring templates. Applied to the AWS SDK it
reported **zero candidates for `SqsClient`**, which would have read as "nothing
missing here" for the one catalog whose gap G-43 states in detail. The SDK addresses
the wire through a request OBJECT: `receiveMessage(ReceiveMessageRequest)` carries the
queue URL inside the argument. A second measured test now covers that style, and it
finds 24 per client — `receiveMessage` and `sendMessageBatch`, G-43's two named gaps,
among them. This is the same defect class as W13's and W14's: a rule taken from one
framework and applied to a set that is not that framework's set.

## What the split does and does not decide

A raw ratio overstates every gap: most of what a template declares is configuration
and lifecycle. `RabbitTemplate`'s 84 unread (§2 below) include `setChannelTransacted`,
`afterPropertiesSet` and every getter, and a method that takes no destination cannot
address a wire. So the unread half is split by two **measured** properties rather than
by judgement.

The split bounds the work of writing a slice; it does not write one. A candidate may
still be deliberately outside (a `receive` with no payload capture, a batch form), and
a non-candidate may still be a boundary reached another way (a destination-less `send`
on a template configured with a default). Those are judgements the catalogs state.
Note also that the arg-0 test admits setters — `setDefaultReceiveQueue`,
`setExchange`, `setRoutingKey` all take a `String` first — which is why the candidate
list is a list to read, not a count to subtract.

## The sixth slice is not here

Five of §3.8's six gaps are questions about methods on an owner type. The sixth,
**G-41**, asks whether `@DgsData` and `@DgsQuery` are `@Inherited` — a question about
one annotation's meta-annotations, already measured (`javap -v` at 8.7.1 shows
`@Inherited` on both) and answered in `netflix-dgs.yml` rather than here. **G-45**
(the Data REST repository roster) and **G-47** (Spring Integration's channel
annotations) are also not method-on-owner questions: one enumerates interfaces
reachable through a jar hop, the other annotations in a package. Each needs its own
read, and calling them done by this table would be the "counted the wrong set" error
this probe already made once.

---
## Observations

Generated by `scripts/probes/w19_catalog_surface/run.sh` — every cell below is that run's own output, and this document pastes it verbatim.

**Each column header is the version the JAR ITSELF reported**, read out of its own `META-INF/MANIFEST.MF` `Implementation-Version` — not the version the loop asked for, which is only the path this machine cached the artifact at. The run ABORTS when the two disagree rather than printing a row.

Methods every class carries are excluded from both sides of every count: <clinit>, <init>, clone, equals, finalize, getClass, hashCode, main, notify, notifyAll, toString, wait. Kotlin's own compiler synthetics — `getX$annotations` and `f$default` — are excluded too: neither is API, and no author writes a call to one.

### 1. How much of each owner's surface the catalog reads

| gap | catalog | owner | 1.1.0 | 2.25.31 | 3.1.1 | 3.1.4 | 3.6.2 | 5.1.2 | 6.1.6 | 6.4.0 | reads |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G-44 | `spring-jms-template` | `JmsTemplate` | — | — | — | — | — | — | 49 | — | **5 of 49** |
| G-44 | `spring-jms-template` | `JmsOperations` | — | — | — | — | — | — | 10 | — | **5 of 10** |
| G-44 | `spring-rabbit-template` | `RabbitTemplate` | — | — | — | 88 | — | — | — | — | **4 of 88** |
| G-44 | `spring-rabbit-template` | `AmqpTemplate` | — | — | — | 8 | — | — | — | — | **4 of 8** |
| G-44 | `spring-sqs-template` | `SqsTemplate` | — | — | 12 | — | — | — | — | — | **1 of 12** |
| G-44 | `spring-sqs-template` | `SqsOperations` | — | — | 4 | — | — | — | — | — | **1 of 4** |
| G-44 | `spring-sqs-template-receive` | `SqsTemplate` | — | — | 12 | — | — | — | — | — | **4 of 12** |
| G-44 | `spring-pubsub` | `PubSubTemplate` | — | — | — | — | — | 20 | — | — | **11 of 20** |
| G-33 | `spring-stomp-template` | `SimpMessagingTemplate` | — | — | — | — | — | — | 14 | — | **3 of 14** |
| G-33 | `spring-stomp-template` | `SimpMessageSendingOperations` | — | — | — | — | — | — | 3 | — | **3 of 3** |
| G-37 | `spring-mvc-router` | `RouterFunctions` | — | — | — | — | — | — | 6 | — | **4 of 6** |
| G-37 | `spring-mvc-router` | `RouterFunctions$Builder` | — | — | — | — | — | — | 20 | — | **20 of 20** |
| G-37 | `spring-webflux-router` | `RouterFunctions` | — | — | — | — | — | — | 8 | — | **4 of 8** |
| G-37 | `spring-mvc-router` | `RouterFunctionDsl` | — | — | — | — | — | — | 42 | — | **11 of 42** |
| G-37 | `spring-mvc-router` | `RouterFunctionDslKt` | — | — | — | — | — | — | 2 | — | **1 of 2** |
| G-37 | `spring-webflux-router` | `CoRouterFunctionDsl` | — | — | — | — | — | — | 45 | — | **10 of 45** |
| G-37 | `spring-webflux-router` | `CoRouterFunctionDslKt` | — | — | — | — | — | — | 2 | — | **1 of 2** |
| G-37 | `spring-webflux-router` | `RouterFunctionDsl` | — | — | — | — | — | — | 42 | — | **11 of 42** |
| G-37 | `spring-webflux-router` | `RouterFunctionDslKt` | — | — | — | — | — | — | 1 | — | **1 of 1** |
| G-37 | `spring-webflux-router` | `RouterFunctions$Builder` | — | — | — | — | — | — | 20 | — | **20 of 20** |
| G-43 | `aws-sqs-sdk` | `SqsClient` | — | 29 | — | — | — | — | — | — | **1 of 29** |
| G-43 | `aws-sqs-sdk` | `SqsAsyncClient` | — | 28 | — | — | — | — | — | — | **1 of 28** |
| G-31 | `kafka-streams` | `StreamsBuilder` | — | — | — | — | 6 | — | — | — | **3 of 6** |
| G-31 | `kafka-streams-sink` | `KStream` | — | — | — | — | 28 | — | — | — | **1 of 28** |
| G-31 | `kafka-streams-topology` | `Topology` | — | — | — | — | 7 | — | — | — | **2 of 7** |
| javalin-routing | `javalin` | `Javalin` | — | — | — | — | — | — | — | 32 | **7 of 32** |
| javalin-routing | `javalin` | `JavalinDefaultRoutingApi` | — | — | — | — | — | — | — | 23 | **7 of 23** |
| javalin-routing | `javalin` | `JavalinDefaultRouting` | — | — | — | — | — | — | — | 23 | **7 of 23** |
| javalin-routing | `javalin` | `ApiBuilder` | — | — | — | — | — | — | — | 18 | **0 of 18** |
| javalin-nested | `javalin-apibuilder` | `ApiBuilder` | — | — | — | — | — | — | — | 18 | **7 of 18** |
| alpakka-pekko | `pekko-connectors-kafka` | `Consumer` | 14 | — | — | — | — | — | — | — | **5 of 14** |
| alpakka-pekko | `pekko-connectors-kafka` | `Producer` | 6 | — | — | — | — | — | — | — | **0 of 6** |

- A version column holds the count of public methods that owner OFFERS at that version — its own and every one it inherits from a non-platform supertype; `—` means this owner was not measured there.

**Supertypes this run could not open, so the surfaces below them are LOWER BOUNDS.** Each lives in an artifact this probe does not resolve. None of them is a messaging or routing type — they are the Spring and AWS lifecycle interfaces (`InitializingBean`, `Lifecycle`, `AwsClient` and the like) — so no addressable method is expected to be hiding behind one. That expectation is stated rather than measured, and it is the same kind of statement that was wrong about `AbstractMessagingTemplate`.

- `org.springframework.amqp.rabbit.core.RabbitTemplate`: `org.springframework.amqp.core.AmqpTemplate`, `org.springframework.amqp.core.MessageListener`, `org.springframework.beans.factory.BeanFactoryAware`, `org.springframework.beans.factory.BeanNameAware`, `org.springframework.beans.factory.DisposableBean`, `org.springframework.beans.factory.InitializingBean`, `org.springframework.context.ApplicationContextAware`, `org.springframework.context.Lifecycle`
- `org.springframework.jms.core.JmsTemplate`: `org.springframework.beans.factory.InitializingBean`
- `software.amazon.awssdk.services.sqs.SqsAsyncClient`: `software.amazon.awssdk.awscore.AwsClient`
- `software.amazon.awssdk.services.sqs.SqsClient`: `software.amazon.awssdk.awscore.AwsClient`

### 2. Of the unread, which could carry a destination

A raw ratio overstates every gap here: most of what a template class declares is configuration and lifecycle, not boundaries. `RabbitTemplate`'s 84 include `setChannelTransacted`, `afterPropertiesSet` and every getter. So the unread half is split by a MEASURED property rather than by judgement — **does the method take a `String` at argument 0**, the position every destination-carrying method in these APIs uses (measured across all ten owners; it is the position `spring-pubsub.yml`, `spring-jms-template.yml` and `spring-sqs-template.yml` already read). A method that takes no name cannot address a wire, so it is not a candidate boundary and its absence needs no slice.

**This split does not decide the slice**, it bounds the work of writing one: a candidate may still be deliberately outside (a `receive` with no payload capture, a batch form), and a non-candidate may still be a boundary reached another way (a destination-less `send` on a template configured with a default). Those are judgements a catalog states; this table says which methods the judgement is about.

| catalog | owner | unread | name at arg 0 | single `*Request` argument | declares a route | distinct |
| --- | --- | --- | --- | --- | --- | --- |
| `spring-jms-template` | `JmsTemplate` | 44 | **7** | **0** | **0** | **7** |
| `spring-jms-template` | `JmsOperations` | 5 | **5** | **0** | **0** | **5** |
| `spring-rabbit-template` | `RabbitTemplate` | 84 | **17** | **0** | **0** | **17** |
| `spring-rabbit-template` | `AmqpTemplate` | 4 | **4** | **0** | **0** | **4** |
| `spring-sqs-template` | `SqsTemplate` | 11 | **7** | **0** | **0** | **7** |
| `spring-sqs-template` | `SqsOperations` | 3 | **3** | **0** | **0** | **3** |
| `spring-sqs-template-receive` | `SqsTemplate` | 8 | **4** | **0** | **0** | **4** |
| `spring-pubsub` | `PubSubTemplate` | 9 | **0** | **0** | **0** | **0** |
| `spring-stomp-template` | `SimpMessagingTemplate` | 11 | **1** | **0** | **0** | **1** |
| `spring-stomp-template` | `SimpMessageSendingOperations` | 0 | **0** | **0** | **0** | **0** |
| `spring-mvc-router` | `RouterFunctions` | 2 | **1** | **0** | **1** | **2** |
| `spring-mvc-router` | `RouterFunctions$Builder` | 0 | **0** | **0** | **0** | **0** |
| `spring-webflux-router` | `RouterFunctions` | 4 | **1** | **0** | **3** | **4** |
| `spring-mvc-router` | `RouterFunctionDsl` | 31 | **7** | **0** | **6** | **10** |
| `spring-mvc-router` | `RouterFunctionDslKt` | 1 | **0** | **0** | **1** | **1** |
| `spring-webflux-router` | `CoRouterFunctionDsl` | 35 | **8** | **0** | **6** | **11** |
| `spring-webflux-router` | `CoRouterFunctionDslKt` | 1 | **0** | **0** | **1** | **1** |
| `spring-webflux-router` | `RouterFunctionDsl` | 31 | **7** | **0** | **6** | **10** |
| `spring-webflux-router` | `RouterFunctionDslKt` | 0 | **0** | **0** | **0** | **0** |
| `spring-webflux-router` | `RouterFunctions$Builder` | 0 | **0** | **0** | **0** | **0** |
| `aws-sqs-sdk` | `SqsClient` | 28 | **0** | **24** | **0** | **24** |
| `aws-sqs-sdk` | `SqsAsyncClient` | 27 | **0** | **24** | **0** | **24** |
| `kafka-streams` | `StreamsBuilder` | 3 | **0** | **0** | **0** | **0** |
| `kafka-streams-sink` | `KStream` | 27 | **1** | **0** | **0** | **1** |
| `kafka-streams-topology` | `Topology` | 5 | **2** | **0** | **0** | **2** |
| `javalin` | `Javalin` | 25 | **11** | **0** | **0** | **11** |
| `javalin` | `JavalinDefaultRoutingApi` | 16 | **10** | **0** | **0** | **10** |
| `javalin` | `JavalinDefaultRouting` | 16 | **10** | **0** | **0** | **10** |
| `javalin` | `ApiBuilder` | 18 | **15** | **0** | **0** | **15** |
| `javalin-apibuilder` | `ApiBuilder` | 11 | **8** | **0** | **0** | **8** |
| `pekko-connectors-kafka` | `Consumer` | 9 | **0** | **0** | **0** | **0** |
| `pekko-connectors-kafka` | `Producer` | 6 | **0** | **0** | **0** | **0** |

**`spring-jms-template` / `JmsTemplate`**

> by name at argument 0 (7): `browse`, `browseSelected`, `execute`, `send`, `sendAndReceive`, `setDefaultDestinationName`, `setSessionAcknowledgeModeName`

**`spring-jms-template` / `JmsOperations`**

> by name at argument 0 (5): `browse`, `browseSelected`, `execute`, `send`, `sendAndReceive`

**`spring-rabbit-template` / `RabbitTemplate`**

> by name at argument 0 (17): `addConsumerArg`, `convertSendAndReceive`, `convertSendAndReceiveAsType`, `nullSafeExchange`, `nullSafeRoutingKey`, `removeConsumerArg`, `send`, `sendAndReceive`, `setBeanName`, `setCorrelationKey`, `setDefaultReceiveQueue`, `setEncoding`, `setExchange`, `setMandatoryExpressionString`, `setReplyAddress`, `setRoutingKey`, `setUserIdExpressionString`

**`spring-rabbit-template` / `AmqpTemplate`**

> by name at argument 0 (4): `convertSendAndReceive`, `convertSendAndReceiveAsType`, `send`, `sendAndReceive`

**`spring-sqs-template` / `SqsTemplate`**

> by name at argument 0 (7): `receive`, `receiveAsync`, `receiveMany`, `receiveManyAsync`, `sendAsync`, `sendMany`, `sendManyAsync`

**`spring-sqs-template` / `SqsOperations`**

> by name at argument 0 (3): `receive`, `receiveMany`, `sendMany`

**`spring-sqs-template-receive` / `SqsTemplate`**

> by name at argument 0 (4): `send`, `sendAsync`, `sendMany`, `sendManyAsync`

**`spring-pubsub` / `PubSubTemplate`** — no unread method addresses a wire by either style.

**`spring-stomp-template` / `SimpMessagingTemplate`**

> by name at argument 0 (1): `setUserDestinationPrefix`

**`spring-stomp-template` / `SimpMessageSendingOperations`** — no unread method addresses a wire by either style.

**`spring-mvc-router` / `RouterFunctions`**

> by name at argument 0 (1): `resourceLookupFunction`

> by declaring a route (1): `changeParser`

**`spring-mvc-router` / `RouterFunctions$Builder`** — no unread method addresses a wire by either style.

**`spring-webflux-router` / `RouterFunctions`**

> by name at argument 0 (1): `resourceLookupFunction`

> by declaring a route (3): `changeParser`, `toHttpHandler`, `toWebHandler`

**`spring-mvc-router` / `RouterFunctionDsl`**

> by name at argument 0 (7): `and`, `invoke`, `or`, `param`, `pathExtension`, `resources`, `withAttribute`

> by declaring a route (6): `add`, `and`, `invoke`, `not`, `or`, `resource`

**`spring-mvc-router` / `RouterFunctionDslKt`**

> by declaring a route (1): `plus`

**`spring-webflux-router` / `CoRouterFunctionDsl`**

> by name at argument 0 (8): `and`, `invoke`, `or`, `path`, `pathExtension`, `queryParam`, `resources`, `withAttribute`

> by declaring a route (6): `add`, `and`, `invoke`, `not`, `or`, `resource`

**`spring-webflux-router` / `CoRouterFunctionDslKt`**

> by declaring a route (1): `plus`

**`spring-webflux-router` / `RouterFunctionDsl`**

> by name at argument 0 (7): `and`, `invoke`, `or`, `pathExtension`, `queryParam`, `resources`, `withAttribute`

> by declaring a route (6): `add`, `and`, `invoke`, `not`, `or`, `resource`

**`spring-webflux-router` / `RouterFunctionDslKt`** — no unread method addresses a wire by either style.

**`spring-webflux-router` / `RouterFunctions$Builder`** — no unread method addresses a wire by either style.

**`aws-sqs-sdk` / `SqsClient`**

> by a `*Request` object (24): `addPermission`, `cancelMessageMoveTask`, `changeMessageVisibility`, `changeMessageVisibilityBatch`, `createQueue`, `deleteMessage`, `deleteMessageBatch`, `deleteQueue`, `getQueueAttributes`, `getQueueUrl`, `listDeadLetterSourceQueues`, `listDeadLetterSourceQueuesPaginator`, `listMessageMoveTasks`, `listQueueTags`, `listQueues`, `listQueuesPaginator`, `purgeQueue`, `receiveMessage`, `removePermission`, `sendMessageBatch`, `setQueueAttributes`, `startMessageMoveTask`, `tagQueue`, `untagQueue`

**`aws-sqs-sdk` / `SqsAsyncClient`**

> by a `*Request` object (24): `addPermission`, `cancelMessageMoveTask`, `changeMessageVisibility`, `changeMessageVisibilityBatch`, `createQueue`, `deleteMessage`, `deleteMessageBatch`, `deleteQueue`, `getQueueAttributes`, `getQueueUrl`, `listDeadLetterSourceQueues`, `listDeadLetterSourceQueuesPaginator`, `listMessageMoveTasks`, `listQueueTags`, `listQueues`, `listQueuesPaginator`, `purgeQueue`, `receiveMessage`, `removePermission`, `sendMessageBatch`, `setQueueAttributes`, `startMessageMoveTask`, `tagQueue`, `untagQueue`

**`kafka-streams` / `StreamsBuilder`** — no unread method addresses a wire by either style.

**`kafka-streams-sink` / `KStream`**

> by name at argument 0 (1): `through`

**`kafka-streams-topology` / `Topology`**

> by name at argument 0 (2): `addProcessor`, `connectProcessorAndStateStores`

**`javalin` / `Javalin`**

> by name at argument 0 (11): `after`, `afterMatched`, `before`, `beforeMatched`, `sse`, `start`, `ws`, `wsAfter`, `wsAfterUpgrade`, `wsBefore`, `wsBeforeUpgrade`

**`javalin` / `JavalinDefaultRoutingApi`**

> by name at argument 0 (10): `after`, `afterMatched`, `before`, `beforeMatched`, `sse`, `ws`, `wsAfter`, `wsAfterUpgrade`, `wsBefore`, `wsBeforeUpgrade`

**`javalin` / `JavalinDefaultRouting`**

> by name at argument 0 (10): `after`, `afterMatched`, `before`, `beforeMatched`, `sse`, `ws`, `wsAfter`, `wsAfterUpgrade`, `wsBefore`, `wsBeforeUpgrade`

**`javalin` / `ApiBuilder`**

> by name at argument 0 (15): `after`, `before`, `crud`, `delete`, `get`, `head`, `patch`, `path`, `post`, `prefixPath`, `put`, `sse`, `ws`, `wsAfter`, `wsBefore`

**`javalin-apibuilder` / `ApiBuilder`**

> by name at argument 0 (8): `after`, `before`, `crud`, `prefixPath`, `sse`, `ws`, `wsAfter`, `wsBefore`

**`pekko-connectors-kafka` / `Consumer`** — no unread method addresses a wire by either style.

**`pekko-connectors-kafka` / `Producer`** — no unread method addresses a wire by either style.

### 3. Every unread candidate, one per row

| catalog | owner | method | addressed by |
|---|---|---|---|
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `browse` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `browseSelected` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `execute` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `send` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `sendAndReceive` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `setDefaultDestinationName` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `setSessionAcknowledgeModeName` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `browse` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `browseSelected` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `execute` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `send` | `argument 0` |
| `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `sendAndReceive` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `addConsumerArg` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertSendAndReceive` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertSendAndReceiveAsType` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `nullSafeExchange` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `nullSafeRoutingKey` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `removeConsumerArg` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `send` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `sendAndReceive` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setBeanName` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setCorrelationKey` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setDefaultReceiveQueue` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setEncoding` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setExchange` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setMandatoryExpressionString` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setReplyAddress` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setRoutingKey` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `setUserIdExpressionString` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertSendAndReceive` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertSendAndReceiveAsType` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `send` | `argument 0` |
| `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `sendAndReceive` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `receive` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `receiveAsync` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `receiveMany` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `receiveManyAsync` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `sendAsync` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `sendMany` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `sendManyAsync` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `receive` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `receiveMany` | `argument 0` |
| `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `sendMany` | `argument 0` |
| `spring-sqs-template-receive` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | `argument 0` |
| `spring-sqs-template-receive` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `sendAsync` | `argument 0` |
| `spring-sqs-template-receive` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `sendMany` | `argument 0` |
| `spring-sqs-template-receive` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `sendManyAsync` | `argument 0` |
| `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `setUserDestinationPrefix` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctions` | `resourceLookupFunction` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctions` | `changeParser` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctions` | `resourceLookupFunction` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctions` | `changeParser` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctions` | `toHttpHandler` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctions` | `toWebHandler` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `and` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `invoke` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `or` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `param` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `pathExtension` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `resources` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `withAttribute` | `argument 0` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `add` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `and` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `invoke` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `not` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `or` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDsl` | `resource` | `route declaration` |
| `spring-mvc-router` | `org.springframework.web.servlet.function.RouterFunctionDslKt` | `plus` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `and` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `invoke` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `or` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `path` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `pathExtension` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `queryParam` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `resources` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `withAttribute` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `add` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `and` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `invoke` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `not` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `or` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDsl` | `resource` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.CoRouterFunctionDslKt` | `plus` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `and` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `invoke` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `or` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `pathExtension` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `queryParam` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `resources` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `withAttribute` | `argument 0` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `add` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `and` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `invoke` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `not` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `or` | `route declaration` |
| `spring-webflux-router` | `org.springframework.web.reactive.function.server.RouterFunctionDsl` | `resource` | `route declaration` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `addPermission` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `cancelMessageMoveTask` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `changeMessageVisibility` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `changeMessageVisibilityBatch` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `createQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `deleteMessage` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `deleteMessageBatch` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `deleteQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `getQueueAttributes` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `getQueueUrl` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `listDeadLetterSourceQueues` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `listDeadLetterSourceQueuesPaginator` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `listMessageMoveTasks` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `listQueueTags` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `listQueues` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `listQueuesPaginator` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `purgeQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `receiveMessage` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `removePermission` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `sendMessageBatch` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `setQueueAttributes` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `startMessageMoveTask` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `tagQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsClient` | `untagQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `addPermission` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `cancelMessageMoveTask` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `changeMessageVisibility` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `changeMessageVisibilityBatch` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `createQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `deleteMessage` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `deleteMessageBatch` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `deleteQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `getQueueAttributes` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `getQueueUrl` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `listDeadLetterSourceQueues` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `listDeadLetterSourceQueuesPaginator` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `listMessageMoveTasks` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `listQueueTags` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `listQueues` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `listQueuesPaginator` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `purgeQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `receiveMessage` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `removePermission` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `sendMessageBatch` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `setQueueAttributes` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `startMessageMoveTask` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `tagQueue` | `request object` |
| `aws-sqs-sdk` | `software.amazon.awssdk.services.sqs.SqsAsyncClient` | `untagQueue` | `request object` |
| `kafka-streams-sink` | `org.apache.kafka.streams.kstream.KStream` | `through` | `argument 0` |
| `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `addProcessor` | `argument 0` |
| `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `connectProcessorAndStateStores` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `after` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `afterMatched` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `before` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `beforeMatched` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `sse` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `start` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `ws` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `wsAfter` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `wsAfterUpgrade` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `wsBefore` | `argument 0` |
| `javalin` | `io.javalin.Javalin` | `wsBeforeUpgrade` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `after` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `afterMatched` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `before` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `beforeMatched` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `sse` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `ws` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `wsAfter` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `wsAfterUpgrade` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `wsBefore` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `wsBeforeUpgrade` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `after` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `afterMatched` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `before` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `beforeMatched` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `sse` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `ws` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `wsAfter` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `wsAfterUpgrade` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `wsBefore` | `argument 0` |
| `javalin` | `io.javalin.router.JavalinDefaultRouting` | `wsBeforeUpgrade` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `after` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `before` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `crud` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `delete` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `get` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `head` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `patch` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `path` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `post` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `prefixPath` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `put` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `sse` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `ws` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `wsAfter` | `argument 0` |
| `javalin` | `io.javalin.apibuilder.ApiBuilder` | `wsBefore` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `after` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `before` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `crud` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `prefixPath` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `sse` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `ws` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `wsAfter` | `argument 0` |
| `javalin-apibuilder` | `io.javalin.apibuilder.ApiBuilder` | `wsBefore` | `argument 0` |

