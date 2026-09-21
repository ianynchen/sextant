# CP-27 — the Spring Integration wiring surface: `IntegrationFlow.from`, the flow definition's members and what its diverts build, the Kafka and AMQP factories by descriptor, the container and endpoint setters, `@Bean`/`@Qualifier`, and Spring's autowire-candidate order

**Question.** Spec 2026-09-21 §4 reads a bean-wired registration as a constructor root
configured by setters (`MessageProducerSupport.setOutputChannel`/`setOutputChannelName`,
`AmqpOutboundEndpoint.setExchangeName`/`setRoutingKey`, the container's `setQueueNames`);
§5 reads a Java DSL flow as a source spec handed to `IntegrationFlow.from`, walked through
the flow definition's members — each one a pass-through, a channel link, a handler, a
discard or a DIVERT — and §3a resolves an injected bean by Spring's own candidate order.
Each rests on a shape of the jars no probe had recorded: Q1 that `IntegrationFlows` (the
older static factory) does not exist at 6.2.4 and which `from` overloads do (F1); Q2/Q3/Q3b
the flow definition's member set, with the exact descriptors the step model keys `handle`,
`channel`, `fixedSubscriberChannel`, `handleReactive` and `nullChannel` by — on the base
type AND on the subclass every flow is compiled against (F3); Q4 what each divert member
constructs, so the `divert` classification is read off bytecode rather than off the
reference; Q5 the producer support's setters (F10); Q6/Q7 the ten
`Kafka.messageDrivenChannelAdapter` and four `inboundChannelAdapter` overloads with the
slot the destination sits in, and the producer spec's `topic` forms (F2); Q8–Q11 the
`Amqp` factories, where the outbound spec's and the outbound endpoint's address setters
are declared, and the inbound adapter's one constructor (F4); Q12/Q13 the container's
queue setters and the `ConsumerProperties`/`ContainerProperties`/`Queue` constructors (F5);
Q14 `@Bean`'s two name attributes and `@Qualifier.value` (F8); Q15 the calls
`determineAutowireCandidate` makes, in order (§3a); Q16 which OWNER types the fixture's
own compiled flows name at their `integration.dsl` call sites — the owner list the step
model must declare, measured rather than inferred from the declaring type.

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file in one of eight jars, or of the committed fixture's own compiled classes. It
measures the compiled 6.2.4 / 3.1.4 / 6.1.6 surface, not the Java source or the reference
documentation. Q4 lists what a divert member's bodies `new` — it says a router, a
gateway, a scatter-gather handler or a recipient-list spec is constructed, which is the
evidence that the message may leave the linear chain; it does not trace where such a
handler sends. `to` and `nullChannel` construct nothing themselves (both delegate — `to`
to `bridge` and a channel, `nullChannel` to `channel(...)` with the framework's
`nullChannel` bean); their classification rests on the reference's statement of what the
delegate does, not on a `new` in their own body. Q15 reads the invoke sequence of ONE
method; that the qualifier is applied earlier, in `findAutowireCandidates` →
`isAutowireCandidate`, is the framework's contract this probe does not re-derive. Q16
reads the fixture's flows as compiled by javac release 21: a different compiler may name
the receiver's static type differently, and Kotlin certainly does. Nothing here measures
the resolve-layer rules the spec specifies.

**Version scope (§5.4).** `org.springframework.integration:spring-integration-core`,
`spring-integration-kafka` and `spring-integration-amqp` at Maven coordinate `6.2.4`;
`org.springframework.amqp:spring-rabbit` and `spring-amqp` and
`org.springframework.kafka:spring-kafka` at `3.1.4`; `org.springframework:spring-context`
and `spring-beans` at `6.1.6` — the versions the Spring Boot 3.2.5 BOM the fixture builds
against manages — and, as the identity the harness files every cell under, the
`Implementation-Version` each jar's own `META-INF/MANIFEST.MF` reports, read as **6.2.4**,
**3.1.4** and **6.1.6** respectively. The harness aborts when an archive reports a version
other than the one the run expected. The fixture's classes carry no manifest: Q16's cell
is filed under the class-file major version `javap -v` reports for them (65, javac
release 21), the one identity a compiled class states itself. Every verdict below is
bounded by those eight archives and that one compile.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp27_spring_integration_wiring/run.sh`. It resolves the eight jars into
`~/.m2` (Maven and network on the first run only), compiles
`fixtures/spring-integration-probe` offline, then runs `probe.py`, which reads each jar's
`Implementation-Version` off its manifest before it measures anything and prints the
table below. Needs a JDK for `javap` and Maven for the fixture. Not a test: nothing in
the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version each jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's `ARTIFACTS` parameter asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column. Every cell is a `javap -p -s`/`-c` read of the named class in the
named artifact, or (row 16) of the fixture's `target/classes`.

```
| what the run read | 3.1.4 | 6.1.6 | 6.2.4 |
|---|---|---|---|
| artifacts reporting this version | org.springframework.amqp:spring-amqp, org.springframework.amqp:spring-rabbit, org.springframework.kafka:spring-kafka | org.springframework:spring-beans, org.springframework:spring-context | org.springframework.integration:spring-integration-amqp, org.springframework.integration:spring-integration-core, org.springframework.integration:spring-integration-kafka |
| identity read from the archive itself (`Implementation-Version`) | yes | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | F1: `IntegrationFlows` present?; `IntegrationFlow.from` public overloads | `org.springframework.integration:spring-integration-core` | 6.2.4 | `IntegrationFlows: absent ; from ×16 ; from(Ljava/lang/String;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/dsl/MessageChannelSpec;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Ljava/lang/String;Z)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/messaging/MessageChannel;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/dsl/MessageSourceSpec;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/dsl/MessageSourceSpec;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/core/MessageSource;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/core/MessageSource;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/dsl/MessageProducerSpec;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/endpoint/MessageProducerSupport;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/dsl/MessagingGatewaySpec;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/gateway/MessagingGatewaySupport;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Ljava/lang/Class;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Ljava/lang/Class;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/reactivestreams/Publisher;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder; ; from(Lorg/springframework/integration/dsl/IntegrationFlow;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder;` |
| 2 | F3: `BaseIntegrationFlowDefinition` public instance members, with overload counts | `org.springframework.integration:spring-integration-core` | 6.2.4 | `34 public instance members ; aggregate ×3 ; barrier ×2 ; bridge ×2 ; channel ×4 ; claimCheckIn ×2 ; claimCheckOut ×3 ; controlBus ×2 ; convert ×2 ; delay ×3 ; enrich ×1 ; enrichHeaders ×5 ; filter ×9 ; fixedSubscriberChannel ×2 ; fluxTransform ×1 ; gateway ×6 ; handle ×13 ; handleReactive ×4 ; headerFilter ×4 ; intercept ×1 ; log ×13 ; nullChannel ×1 ; publishSubscribeChannel ×3 ; resequence ×2 ; route ×13 ; routeByException ×1 ; routeToRecipients ×1 ; scatterGather ×6 ; split ×17 ; splitWith ×1 ; to ×1 ; transform ×10 ; transformWith ×1 ; trigger ×4 ; wireTap ×7` |
| 3 | F3: the descriptors the step model keys by — `handle`, `handleReactive`, `channel`, `fixedSubscriberChannel`, `nullChannel` | `org.springframework.integration:spring-integration-core` | 6.2.4 | `handle(Lorg/springframework/integration/dsl/MessageHandlerSpec;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Lorg/springframework/messaging/MessageHandler;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/String;Ljava/lang/String;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/String;Ljava/lang/String;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/Object;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/Object;Ljava/lang/String;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/Object;Ljava/lang/String;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/Class;Lorg/springframework/integration/core/GenericHandler;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Ljava/lang/Class;Lorg/springframework/integration/core/GenericHandler;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Lorg/springframework/integration/dsl/MessageProcessorSpec;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Lorg/springframework/integration/dsl/MessageProcessorSpec;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Lorg/springframework/integration/dsl/MessageHandlerSpec;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handle(Lorg/springframework/messaging/MessageHandler;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; handleReactive(Lorg/springframework/integration/dsl/ReactiveMessageHandlerSpec;)Lorg/springframework/integration/dsl/IntegrationFlow; ; handleReactive(Lorg/springframework/integration/dsl/ReactiveMessageHandlerSpec;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlow; ; handleReactive(Lorg/springframework/messaging/ReactiveMessageHandler;)Lorg/springframework/integration/dsl/IntegrationFlow; ; handleReactive(Lorg/springframework/messaging/ReactiveMessageHandler;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlow; ; channel(Ljava/lang/String;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; channel(Lorg/springframework/integration/dsl/MessageChannelSpec;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; channel(Lorg/springframework/messaging/MessageChannel;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; channel(Ljava/util/function/Function;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; fixedSubscriberChannel()Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; fixedSubscriberChannel(Ljava/lang/String;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition; ; nullChannel()Lorg/springframework/integration/dsl/IntegrationFlow;` |
| 3b | F3: `IntegrationFlowDefinition`'s OWN public members (the subclass every flow is compiled against) | `org.springframework.integration:spring-integration-core` | 6.2.4 | `public abstract class org.springframework.integration.dsl.IntegrationFlowDefinition<B extends org.springframework.integration.dsl.IntegrationFlowDefinition<B>> extends org.springframework.integration.dsl.BaseIntegrationFlowDefinition<B> ; transform(Lorg/springframework/integration/core/GenericTransformer;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; transform(Lorg/springframework/integration/core/GenericTransformer;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; filter(Lorg/springframework/integration/core/GenericSelector;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; filter(Lorg/springframework/integration/core/GenericSelector;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; handle(Lorg/springframework/integration/core/GenericHandler;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; handle(Lorg/springframework/integration/core/GenericHandler;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; split(Ljava/util/function/Function;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; route(Ljava/util/function/Function;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; route(Ljava/util/function/Function;Ljava/util/function/Consumer;)Lorg/springframework/integration/dsl/IntegrationFlowDefinition; ; lambda$transform$0(Lorg/springframework/integration/core/GenericTransformer;Lorg/springframework/integration/dsl/TransformerEndpointSpec;)V` |
| 4 | F3: what each divert member (and `nullChannel`) constructs — `new` in its bodies | `org.springframework.integration:spring-integration-core` | 6.2.4 | `route -> org/springframework/integration/router/MethodInvokingRouter, org/springframework/integration/handler/BeanNameMessageProcessor, org/springframework/integration/dsl/RouterSpec, org/springframework/integration/router/ExpressionEvaluatingRouter, org/springframework/integration/handler/LambdaMessageProcessor, org/springframework/integration/handler/BridgeHandler, java/util/LinkedHashMap, org/springframework/integration/channel/FixedSubscriberChannel ; routeByException -> org/springframework/integration/dsl/RouterSpec, org/springframework/integration/router/ErrorMessageExceptionTypeRouter ; routeToRecipients -> org/springframework/integration/dsl/RecipientListRouterSpec ; gateway -> org/springframework/integration/dsl/GatewayEndpointSpec ; scatterGather -> org/springframework/integration/dsl/AggregatorSpec, org/springframework/integration/scattergather/ScatterGatherHandler, org/springframework/integration/dsl/ScatterGatherSpec, org/springframework/integration/dsl/RecipientListRouterSpec ; publishSubscribeChannel -> org/springframework/integration/dsl/PublishSubscribeSpec, org/springframework/integration/dsl/BroadcastPublishSubscribeSpec ; controlBus -> org/springframework/integration/handler/ServiceActivatingHandler, org/springframework/integration/handler/ExpressionCommandMessageProcessor, org/springframework/integration/expression/ControlBusMethodFilter ; trigger -> org/springframework/integration/handler/BeanNameMessageProcessor, org/springframework/integration/handler/ServiceActivatingHandler, org/springframework/integration/handler/LambdaMessageProcessor ; to -> (delegates; constructs nothing) ; nullChannel -> (delegates; constructs nothing)` |
| 5 | F10/§4: `MessageProducerSupport` output-channel setters | `org.springframework.integration:spring-integration-core` | 6.2.4 | `setOutputChannel(Lorg/springframework/messaging/MessageChannel;)V ; setOutputChannelName(Ljava/lang/String;)V` |
| 6 | F2: `Kafka` source and sink factories by descriptor; the other factories | `org.springframework.integration:spring-integration-kafka` | 6.2.4 | `messageDrivenChannelAdapter ×10 ; messageDrivenChannelAdapter(Lorg/springframework/kafka/listener/AbstractMessageListenerContainer;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/listener/AbstractMessageListenerContainer;Lorg/springframework/integration/kafka/inbound/KafkaMessageDrivenChannelAdapter$ListenerMode;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/kafka/listener/ContainerProperties;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/kafka/listener/ContainerProperties;Lorg/springframework/integration/kafka/inbound/KafkaMessageDrivenChannelAdapter$ListenerMode;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;[Lorg/springframework/kafka/support/TopicPartitionOffset;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/integration/kafka/inbound/KafkaMessageDrivenChannelAdapter$ListenerMode;[Lorg/springframework/kafka/support/TopicPartitionOffset;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;[Ljava/lang/String;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/integration/kafka/inbound/KafkaMessageDrivenChannelAdapter$ListenerMode;[Ljava/lang/String;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Ljava/util/regex/Pattern;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; messageDrivenChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/integration/kafka/inbound/KafkaMessageDrivenChannelAdapter$ListenerMode;Ljava/util/regex/Pattern;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec; ; inboundChannelAdapter ×4 ; inboundChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/kafka/listener/ConsumerProperties;)Lorg/springframework/integration/kafka/dsl/KafkaInboundChannelAdapterSpec; ; inboundChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/kafka/listener/ConsumerProperties;Z)Lorg/springframework/integration/kafka/dsl/KafkaInboundChannelAdapterSpec; ; inboundChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/kafka/listener/ConsumerProperties;Lorg/springframework/integration/kafka/inbound/KafkaMessageSource$KafkaAckCallbackFactory;)Lorg/springframework/integration/kafka/dsl/KafkaInboundChannelAdapterSpec; ; inboundChannelAdapter(Lorg/springframework/kafka/core/ConsumerFactory;Lorg/springframework/kafka/listener/ConsumerProperties;Lorg/springframework/integration/kafka/inbound/KafkaMessageSource$KafkaAckCallbackFactory;Z)Lorg/springframework/integration/kafka/dsl/KafkaInboundChannelAdapterSpec; ; outboundChannelAdapter ×2 ; outboundChannelAdapter(Lorg/springframework/kafka/core/KafkaTemplate;)Lorg/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec; ; outboundChannelAdapter(Lorg/springframework/kafka/core/ProducerFactory;)Lorg/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec$KafkaProducerMessageHandlerTemplateSpec; ; other factories: channel, inboundGateway, outboundGateway, pollableChannel, publishSubscribeChannel` |
| 7 | §5: `KafkaProducerMessageHandlerSpec.topic`/`topicExpression` overloads | `org.springframework.integration:spring-integration-kafka` | 6.2.4 | `topic(Ljava/lang/String;)Lorg/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec; ; topic(Ljava/util/function/Function;)Lorg/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec; ; topicExpression(Ljava/lang/String;)Lorg/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec; ; topicExpression(Lorg/springframework/expression/Expression;)Lorg/springframework/integration/kafka/dsl/KafkaProducerMessageHandlerSpec;` |
| 8 | §5: `Amqp` adapter factories by descriptor; the other factories | `org.springframework.integration:spring-integration-amqp` | 6.2.4 | `inboundAdapter ×4 ; inboundAdapter(Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;[Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpInboundChannelAdapterSMLCSpec; ; inboundAdapter(Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;[Lorg/springframework/amqp/core/Queue;)Lorg/springframework/integration/amqp/dsl/AmqpInboundChannelAdapterSMLCSpec; ; inboundAdapter(Lorg/springframework/amqp/rabbit/listener/SimpleMessageListenerContainer;)Lorg/springframework/integration/amqp/dsl/AmqpInboundChannelAdapterSMLCSpec; ; inboundAdapter(Lorg/springframework/amqp/rabbit/listener/DirectMessageListenerContainer;)Lorg/springframework/integration/amqp/dsl/AmqpInboundChannelAdapterDMLCSpec; ; outboundAdapter ×1 ; outboundAdapter(Lorg/springframework/amqp/core/AmqpTemplate;)Lorg/springframework/integration/amqp/dsl/AmqpOutboundChannelAdapterSpec; ; other factories: asyncOutboundGateway, channel, inboundGateway, inboundPolledAdapter, outboundGateway, pollableChannel, publishSubscribeChannel` |
| 9 | F4: the outbound spec's address setters and the type each is declared on | `org.springframework.integration:spring-integration-amqp` | 6.2.4 | `public class org.springframework.integration.amqp.dsl.AmqpOutboundChannelAdapterSpec extends org.springframework.integration.amqp.dsl.AmqpOutboundEndpointSpec<org.springframework.integration.amqp.dsl.AmqpOutboundChannelAdapterSpec> ; public abstract class org.springframework.integration.amqp.dsl.AmqpBaseOutboundEndpointSpec<S extends org.springframework.integration.amqp.dsl.AmqpBaseOutboundEndpointSpec<S, E>, E extends org.springframework.integration.amqp.outbound.AbstractAmqpOutboundEndpoint> extends org.springframework.integration.dsl.MessageHandlerSpec<S, E> ; AmqpBaseOutboundEndpointSpec.exchangeName(Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.exchangeNameExpression(Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.exchangeNameExpression(Lorg/springframework/expression/Expression;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.exchangeNameFunction(Ljava/util/function/Function;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.routingKey(Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.routingKeyExpression(Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.routingKeyExpression(Lorg/springframework/expression/Expression;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec; ; AmqpBaseOutboundEndpointSpec.routingKeyFunction(Ljava/util/function/Function;)Lorg/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec;` |
| 10 | F4: `AmqpOutboundEndpoint` constructors and address setters (declared on the abstract base) | `org.springframework.integration:spring-integration-amqp` | 6.2.4 | `constructors: (Lorg/springframework/amqp/core/AmqpTemplate;)V ; AbstractAmqpOutboundEndpoint.setExchangeName(Ljava/lang/String;)V ; AbstractAmqpOutboundEndpoint.setExchangeNameExpression(Lorg/springframework/expression/Expression;)V ; AbstractAmqpOutboundEndpoint.setExchangeNameExpressionString(Ljava/lang/String;)V ; AbstractAmqpOutboundEndpoint.setRoutingKey(Ljava/lang/String;)V ; AbstractAmqpOutboundEndpoint.setRoutingKeyExpression(Lorg/springframework/expression/Expression;)V ; AbstractAmqpOutboundEndpoint.setRoutingKeyExpressionString(Ljava/lang/String;)V` |
| 11 | §4: `AmqpInboundChannelAdapter` constructors | `org.springframework.integration:spring-integration-amqp` | 6.2.4 | `<init>(Lorg/springframework/amqp/rabbit/listener/MessageListenerContainer;)V` |
| 12 | F5: `AbstractMessageListenerContainer` queue setters; the two containers' constructors | `org.springframework.amqp:spring-rabbit` | 3.1.4 | `setQueueNames([Ljava/lang/String;)V ; addQueueNames([Ljava/lang/String;)V ; removeQueueNames([Ljava/lang/String;)Z ; setQueues([Lorg/springframework/amqp/core/Queue;)V ; addQueues([Lorg/springframework/amqp/core/Queue;)V ; removeQueues([Lorg/springframework/amqp/core/Queue;)Z ; SimpleMessageListenerContainer.<init>: ()V, (Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;)V ; DirectMessageListenerContainer.<init>: ()V, (Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;)V` |
| 13 | F5: `ConsumerProperties`, `ContainerProperties` and `Queue` constructors | `org.springframework.kafka:spring-kafka` | 3.1.4 | `ConsumerProperties.<init>: ([Ljava/lang/String;)V, (Ljava/util/regex/Pattern;)V, ([Lorg/springframework/kafka/support/TopicPartitionOffset;)V ; ContainerProperties.<init>: ([Ljava/lang/String;)V, (Ljava/util/regex/Pattern;)V, ([Lorg/springframework/kafka/support/TopicPartitionOffset;)V ; Queue.<init>: (Ljava/lang/String;)V, (Ljava/lang/String;Z)V, (Ljava/lang/String;ZZZ)V, (Ljava/lang/String;ZZZLjava/util/Map;)V` |
| 14 | F8: `@Bean` and `@Qualifier` attributes | `org.springframework:spring-context` | 6.1.6 | `@Bean: value()[Ljava/lang/String;, name()[Ljava/lang/String;, autowireCandidate()Z, initMethod()Ljava/lang/String;, destroyMethod()Ljava/lang/String; ; @Qualifier: value()Ljava/lang/String;` |
| 15 | §3a: `DefaultListableBeanFactory.determineAutowireCandidate` — the calls its body makes, in order | `org.springframework:spring-beans` | 6.1.6 | `DependencyDescriptor.getDependencyType ; determinePrimaryCandidate ; determineHighestPriorityCandidate ; Map.entrySet ; Set.iterator ; Iterator.hasNext ; Iterator.next ; Map$Entry.getKey ; Map$Entry.getValue ; Map.containsValue ; DependencyDescriptor.getDependencyName ; matchesBeanName` |
| 16 | §5: the owners the fixture's compiled flows name at their `integration.dsl` call sites | `fixtures/spring-integration-probe` (target/classes) | class file 65 | `IntegrationFlow: from ; IntegrationFlowBuilder: channel, get, handle, route, transform ; IntegrationFlowDefinition: handle ; PollerFactory: fixedDelay ; SourcePollingChannelAdapterSpec: poller` |
```

## Verdicts

**Q1 — `IntegrationFlows` is gone; `from` has sixteen overloads (F1, §5).** `javap` finds
no `org.springframework.integration.dsl.IntegrationFlows` at 6.2.4, so the catalogs
declare `IntegrationFlow.from` alone and no alias. Of the sixteen `from` overloads, the
two spec §5 declares as ROOTS are `from(String)` and `from(MessageChannel)` — a flow that
CONSUMES a channel; `from(MessageProducerSpec)`, `from(MessageSourceSpec[, Consumer])` and
`from(MessageProducerSupport)` are the consumers a source spec's chain CONTINUES into
(`via_argument_of: {owner: IntegrationFlow, method: from}, continue: true` — the join is
by owner and name, so every overload consuming the spec's value continues it). The
remaining overloads — `from(String, boolean)`, `from(MessageChannelSpec)`,
`from(MessageSource[, Consumer])`, `from(MessagingGatewaySpec)`,
`from(MessagingGatewaySupport)`, `from(Class[, Consumer])`, `from(Publisher)`,
`from(IntegrationFlow)` — are stated boundaries on the catalogs, not roots.

**Q2/Q3/Q3b — thirty-FOUR members, not thirty-five (F3).** The base type declares 34
public instance members, and they are exactly the 34 names spec §0's F3 lists (its own
list has 34 entries; the "35" beside it is a miscount — the probe contradicts the number
and confirms the names). `IntegrationFlowDefinition`, the subclass every flow is compiled
against, redeclares `transform`, `filter`, `handle`, `split` and `route` for the
functional-interface argument (`handle(GenericHandler)`,
`handle(GenericHandler, Consumer)`) with return type `IntegrationFlowDefinition` — so the
lambda `handle` a flow most often writes is NOT on the base type, and the step model
declares it by its own descriptor. Every `handle` form and its slot: `handle(GenericHandler)`
and `handle(GenericHandler, Consumer)` (subclass) → the handler at 0;
`handle(Class, GenericHandler[, Consumer])` → at 1; `handle(MessageHandler[, Consumer])` →
at 0; `handle(Object, String[, Consumer])`, `handle(Object)`, `handle(String, String[,
Consumer])`, `handle(MessageProcessorSpec[, Consumer])` → a bean or a spec at 0, which the
walk cannot name (`handler` NULL); `handle(MessageHandlerSpec[, Consumer])` → the SINK
spec's own chain continues into it (`captures: {}`). `handleReactive` likewise at 0.
`channel(String)` and `fixedSubscriberChannel(String)` are links at 0;
`channel(MessageChannel)` a link through the bean fold; `channel(MessageChannelSpec)` and
`channel(Function)` carry a spec the walk does not open (`poisons: [channel_link]`);
`fixedSubscriberChannel()` is a pass-through; `nullChannel()` is the discard.

**Q4 — what a divert builds (F3, §0b A5).** `route` constructs a `MethodInvokingRouter`
or an `ExpressionEvaluatingRouter` (and a `BridgeHandler` for the default-output form);
`routeByException` an `ErrorMessageExceptionTypeRouter`; `routeToRecipients` a
`RecipientListRouterSpec`; `gateway` a `GatewayEndpointSpec` (a gateway to another flow);
`scatterGather` a `ScatterGatherHandler` over a `RecipientListRouterSpec`;
`publishSubscribeChannel` a `PublishSubscribeSpec`/`BroadcastPublishSubscribeSpec` (a
fan-out channel); `controlBus` a `ServiceActivatingHandler` around an
`ExpressionCommandMessageProcessor` (commands, not the payload's consumer); `trigger` a
`ServiceActivatingHandler` around a `MessageTriggerAction`. Each is a component that sends
the message somewhere the linear chain does not state — the router's output channels, the
gateway's request channel, the recipients — so a `handle` folded AFTER one of these is not
certainly what receives the message, and the step poisons `handler`. `to` constructs
nothing (it bridges to another flow's input) and `nullChannel` constructs nothing (it
links the framework's `nullChannel` bean); `to` is a divert on the reference's word,
`nullChannel` the discard whose `handler: none` is the TRUE answer.

**Q5 — the producer support's setters (F10, §4).** `setOutputChannel(MessageChannel)` and
`setOutputChannelName(String)`, both on `MessageProducerSupport`, both `void` — the
bean-wired adapter's chain is a constructor and void setters on its value, which is why a
void call folds into its chain rather than forking it (Task 3's ruling 1). The Pub/Sub
and AMQP inbound adapters inherit both (CP-28 row 1 for the Pub/Sub one).

**Q6/Q7 — the Kafka factories by descriptor (F2, §5).** Ten `messageDrivenChannelAdapter`
overloads: the topic list is a `String[]` at slot 1 in `(ConsumerFactory, String...)` and
at slot 2 in `(ConsumerFactory, ListenerMode, String...)`; a `Pattern` at slot 1 / slot 2
in two more (not a topic name — the row's `path` is unresolved); a `TopicPartitionOffset[]`
at 1 / 2 in two more (a partition subscription, unresolved likewise); a
`ContainerProperties` at slot 1 in two (its own `(String...)` constructor carries the
topics — one producing-site hop through `channel_via` by descriptor, since the
`(Pattern)` and `(TopicPartitionOffset...)` constructors share its arity); and a whole
`AbstractMessageListenerContainer` at slot 0 in two (a container bean — a hop the catalog
does not take; unresolved). Four `inboundChannelAdapter` overloads all carry a
`ConsumerProperties` at slot 1, read the same way. `outboundChannelAdapter` takes a
`KafkaTemplate` or a `ProducerFactory`; the sink's topic is `topic(String)` on the
producer spec — `topic(Function)`, `topicExpression(String)` and
`topicExpression(Expression)` are not literals and poison it. `channel`,
`publishSubscribeChannel`, `pollableChannel`, `inboundGateway` and `outboundGateway` are
stated boundaries (a Kafka-backed channel and the request-reply gateways).

**Q8–Q11 — the AMQP side (F4, §4, §5).** `Amqp.inboundAdapter` has four overloads:
`(ConnectionFactory, String...)` (queues at slot 1), `(ConnectionFactory, Queue...)` (queue
objects at slot 1 — read through the `Queue(String, …)` constructors' first argument),
and one each taking a `SimpleMessageListenerContainer` or a `DirectMessageListenerContainer`
(a container bean at slot 0 — the bean fold, then the container's own chain).
`Amqp.outboundAdapter(AmqpTemplate)` returns `AmqpOutboundChannelAdapterSpec`, and the
address setters — `exchangeName(String)`, `routingKey(String)` and their
`Expression`/`Function` twins — are declared on `AmqpBaseOutboundEndpointSpec`, its
abstract ancestor; the fixture's compiled call sites name `AmqpOutboundChannelAdapterSpec`
as the owner (the receiver's static type, after the checkcast that follows each generic
`S` return), so the catalog names both. `AmqpOutboundEndpoint(AmqpTemplate)` is the one
constructor, and its setters — `setExchangeName`, `setRoutingKey`, and the four
expression forms — are declared on `AbstractAmqpOutboundEndpoint`; a call site names the
concrete type, so the catalog names both there too. `AmqpInboundChannelAdapter` has ONE
constructor, `(MessageListenerContainer)` — the interface, so a `SimpleMessageListenerContainer`
or `DirectMessageListenerContainer` bean is what arrives at slot 0. `inboundGateway`,
`outboundGateway`, `asyncOutboundGateway`, `inboundPolledAdapter`, `channel`,
`publishSubscribeChannel` and `pollableChannel` are stated boundaries.

**Q12/Q13 — the container and the constructors (F5).** `setQueueNames(String...)`,
`addQueueNames(String...)`, `setQueues(Queue...)` and `addQueues(Queue...)` on
`AbstractMessageListenerContainer` — the two `remove*` forms take a queue AWAY and are not
destinations. Both containers construct from `()` or `(ConnectionFactory)`.
`ConsumerProperties` and `ContainerProperties` each have exactly the three constructors
F5 names — `(String...)`, `(Pattern)`, `(TopicPartitionOffset...)` — all of arity one, which
is why the `channel_via` form names the `([Ljava/lang/String;)V` descriptor and not an
arity. `Queue`'s four constructors all take the name at slot 0.

**Q14 — `@Bean` and `@Qualifier` (F8, §3a).** `@Bean` declares `value()` and `name()`, both
`String[]` (aliases of each other — either present names the bean), beside
`autowireCandidate`, `initMethod` and `destroyMethod`; `@Qualifier` declares one
`value()`, a `String`. `bean-models/spring.yml`'s `name_attrs: [name, value]` and
`qualifier_annotation` are these.

**Q15 — the autowire candidate order (§3a).** With more than one candidate,
`determineAutowireCandidate` tries `determinePrimaryCandidate`, then
`determineHighestPriorityCandidate`, then walks the candidates comparing each to the
dependency's NAME (`matchesBeanName`, after a `containsValue` check for a pre-resolved
instance) — row 15's invoke sequence, in that order; `javap -c -p` on the 6.1.6 class puts
the three calls at bytecode offsets 8, 24 and 119. The bean model's container rungs
(`bean-models/spring.yml`, `resolve/beans.py`) are this order: a qualifier, else exactly
one bean of the type, else the one of several marked `@Primary`, else the bean whose name
is the parameter's. Two primaries fail the injection — read by hand off the same jar, not
a row of the table: `determinePrimaryCandidate` constructs and throws
`NoUniqueBeanDefinitionException` when both candidates are the factory's own definitions
(`javap -c -p` offsets 98–123) — so the fold answers `ambiguous` and does not fall through
to the name rung. `@Priority` is the one rung the fold does not read: with no primary among
them, two candidates go to the name rung, which is the container's next step only when no
candidate carries `@Priority` — stated on the model as a boundary. *(This paragraph
previously said a module using `@Primary` was `Unresolved`; the fold fell from the
two-candidate type rung to the name rung and, for a parameter named after the
non-primary bean, named that bean — the final-review fix corrected the code to the row and
this text to the code.)*

**Q16 — the owners a compiled flow names (§5).** The fixture's flows, compiled with javac
release 21, name `IntegrationFlow` for `from`; `IntegrationFlowBuilder` for `channel`,
`get`, `handle`, `route` and `transform` (the receiver's static type after `from(...)`,
and again after every generic `B` return's checkcast); and `IntegrationFlowDefinition` for
the `handle` inside a `flow -> flow.handle(...)` lambda (the lambda's parameter type).
`BaseIntegrationFlowDefinition` — the DECLARING type of most members — is named at no call
site here; the step model declares all three so a flow compiled against any of them
matches. `PollerFactory` and `SourcePollingChannelAdapterSpec` appear only inside the JMS
flow's endpoint configurer, which no catalog of this feature reads.

`measured: 2026-09-21`, all seventeen rows, on the eight archives and the one fixture
compile the scope names.
