# CP-28 — spring-cloud-gcp-pubsub 5.1.2: the inbound adapter, the message handler, their setters, and the `from` overload that accepts the adapter

**Question.** Spec 2026-09-21 §4 reads the Pub/Sub registration as two constructor
roots: `PubSubInboundChannelAdapter(PubSubSubscriberOperations, String)` — the
subscription at slot 1, the channel it feeds set by one of `MessageProducerSupport`'s two
setters — and `PubSubMessageHandler(PubSubPublisherOperations, String)` — the topic at
slot 1, overridable by `setTopic(String)` and made unreadable by `setTopicExpression` or
`setTopicExpressionString`; §5 lets a flow start from the adapter BEAN through
`IntegrationFlow.from(MessageProducerSupport)`. Each rests on a shape of the 5.1.2 jar no
probe had recorded (F10): Q1 the adapter's one constructor and that it EXTENDS
`MessageProducerSupport` without redeclaring the setters (so the catalog's steps are the
inherited ones, on the adapter's own owner); Q2 those setters' descriptors and the exact
`from` overload whose parameter type the adapter satisfies; Q3 the handler's constructor,
its `AbstractMessageHandler` ancestry, `setTopic` and the two expression setters; Q4
`PubSubMessageSource`'s constructor — the polled sibling with the SAME `(operations,
String)` shape on another type, which is the near-miss the catalog's declining test uses.

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file in one of two jars. It measures the compiled 5.1.2 surface, not the source or
the reference documentation. Q2 shows the `from(MessageProducerSupport)` overload exists
and Q1 that the adapter is a `MessageProducerSupport`; that javac selects that overload
for an argument statically typed as the adapter is the language's overload resolution,
not re-derived here. Nothing here measures the resolve-layer rules the spec specifies.

**Version scope (§5.4).** `com.google.cloud:spring-cloud-gcp-pubsub` at Maven coordinate
`5.1.2` (the version `fixtures/spring-integration-probe` and `fixtures/orders-service`
pin) and `org.springframework.integration:spring-integration-core` at `6.2.4` (the
version the Spring Boot 3.2.5 BOM manages) — and, as the identity the harness files every
cell under, the `Implementation-Version` each jar's own `META-INF/MANIFEST.MF` reports,
read as **5.1.2** and **6.2.4**. The harness aborts when an archive reports a version
other than the one the run expected. Every verdict below is bounded by those two
archives.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp28_gcp_pubsub_integration/run.sh`. It resolves the two jars into `~/.m2`
(Maven and network on the first run only), then runs `probe.py`, which reads each jar's
`Implementation-Version` off its manifest before it measures anything and prints the
table below. Needs a JDK for `javap`. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version each jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's `ARTIFACTS` parameter asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column. Every cell is a `javap -p -s` read of the named class in the named
artifact.

```
| what the run read | 5.1.2 | 6.2.4 |
|---|---|---|
| artifacts reporting this version | com.google.cloud:spring-cloud-gcp-pubsub | org.springframework.integration:spring-integration-core |
| identity read from the archive itself (`Implementation-Version`) | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | F10: `PubSubInboundChannelAdapter` — supertype, constructor, whether it redeclares the output-channel setters | `com.google.cloud:spring-cloud-gcp-pubsub` | 5.1.2 | `public class com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter extends org.springframework.integration.endpoint.MessageProducerSupport ; <init>: (Lcom/google/cloud/spring/pubsub/core/subscriber/PubSubSubscriberOperations;Ljava/lang/String;)V ; redeclares output-channel setters: none (inherited)` |
| 2 | F10/§5: `MessageProducerSupport`'s setters, and the `IntegrationFlow.from` overload accepting it | `org.springframework.integration:spring-integration-core` | 6.2.4 | `public abstract class org.springframework.integration.endpoint.MessageProducerSupport extends org.springframework.integration.endpoint.AbstractEndpoint implements org.springframework.integration.core.MessageProducer,org.springframework.integration.support.management.TrackableComponent,org.springframework.beans.factory.SmartInitializingSingleton,org.springframework.integration.IntegrationPattern,org.springframework.integration.support.management.IntegrationInboundManagement ; setOutputChannel(Lorg/springframework/messaging/MessageChannel;)V ; setOutputChannelName(Ljava/lang/String;)V ; IntegrationFlow.from accepting it: (Lorg/springframework/integration/endpoint/MessageProducerSupport;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder;` |
| 3 | F10: `PubSubMessageHandler` — supertype, constructor, `setTopic` and the two expression setters | `com.google.cloud:spring-cloud-gcp-pubsub` | 5.1.2 | `public class com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler extends org.springframework.integration.handler.AbstractMessageHandler ; <init>: (Lcom/google/cloud/spring/pubsub/core/publisher/PubSubPublisherOperations;Ljava/lang/String;)V ; setTopic(Ljava/lang/String;)V ; setTopicExpression(Lorg/springframework/expression/Expression;)V ; setTopicExpressionString(Ljava/lang/String;)V` |
| 4 | the near-miss shape: `PubSubMessageSource` — supertype and constructor | `com.google.cloud:spring-cloud-gcp-pubsub` | 5.1.2 | `public class com.google.cloud.spring.pubsub.integration.inbound.PubSubMessageSource extends org.springframework.integration.endpoint.AbstractFetchLimitingMessageSource<java.lang.Object> ; <init>: (Lcom/google/cloud/spring/pubsub/core/subscriber/PubSubSubscriberOperations;Ljava/lang/String;)V` |
```

## Verdicts

**Q1 — the inbound adapter (F10, §4).** One public constructor,
`(PubSubSubscriberOperations, String)` — the subscription at slot 1, so the root captures
`channel: arg1`. The class extends `MessageProducerSupport` and redeclares neither setter,
so `setOutputChannel`/`setOutputChannelName` reach a call site with the ADAPTER as owner
(javac names the receiver's static type) and the catalog's steps declare them on
`PubSubInboundChannelAdapter`, not on the ancestor.

**Q2 — the setters, and `from` (F10, §5).** `setOutputChannel(MessageChannel)` names a
channel BEAN (`channel_link: {bean_via: arg0}`), `setOutputChannelName(String)` a channel
NAME (`channel_link: arg0`); both `void`, so both fold into the constructor's chain.
`IntegrationFlow.from(MessageProducerSupport)` is the one `from` overload whose parameter
the adapter satisfies: a flow starting from an injected adapter bean is
`from(<the parameter>)`, and the catalog's `from` root by that descriptor reads the
subscription through the bean fold (`channel: {bean_via: arg0}`) from the adapter's own
constructor chain, declared under `beans:`.

**Q3 — the outbound handler (F10, §4).** One constructor,
`(PubSubPublisherOperations, String)` — the topic at slot 1; `setTopic(String)` overrides
it (last wins, Spring's setter semantics); `setTopicExpression(Expression)` and
`setTopicExpressionString(String)` make it unreadable (`poisons: [channel]`, sticky —
`setTopicExpression(e); setTopic("t")` derives unresolved, the no-false-positive
direction). It extends `AbstractMessageHandler`, a consumer: the root carries
`direction: outbound` and reads the channel it consumes off the constructing method's
`@ServiceActivator(inputChannel)`.

**Q4 — the near-miss (§10).** `PubSubMessageSource(PubSubSubscriberOperations, String)` has
the adapter's exact constructor shape on a different type — a polled `MessageSource`,
consumed through `from(MessageSource, Consumer)`, which spec §5 states as a boundary. A
root that matched on the constructor shape alone would publish it as the adapter's row;
the catalog's declining test constructs one and asserts nothing derives.

`measured: 2026-09-21`, all four rows, on the two archives the scope names.
