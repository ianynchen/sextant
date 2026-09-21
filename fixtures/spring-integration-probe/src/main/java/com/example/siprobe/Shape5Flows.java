package com.example.siprobe;

import java.util.regex.Pattern;

import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.amqp.outbound.AmqpOutboundEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.kafka.dsl.Kafka;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.messaging.MessageChannel;

/** Shape 5 — the flows and beans spec 2026-09-21 §11 adds: an AMQP DSL flow
 *  over two queues with a pass-through step, an AMQP outbound BEAN composing
 *  its address from two setters, a Kafka flow whose router diverts the message
 *  (handler unresolved), a Kafka flow that ends in a named channel a
 *  {@code @ServiceActivator} reads, a {@code Pattern} subscription (not a topic
 *  name), and the ambiguous-bean near-miss (two channel beans, a parameter
 *  naming neither). */
@Configuration
public class Shape5Flows {

    /** Two queues in one varargs call; {@code transform} is a pass-through and
     *  the lambda after it is the consumer. */
    @Bean
    public IntegrationFlow twoQueueDslFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, "dsl.q1", "dsl.q2"))
                .transform(String.class, payload -> payload.trim())
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** The AMQP outbound bean: {@code exchange/routingKey} from two setters,
     *  consumed from the channel the method's own annotation names. */
    @Bean
    @ServiceActivator(inputChannel = "amqpOutboundChannel")
    public AmqpOutboundEndpoint shipmentsOutbound(AmqpTemplate amqpTemplate) {
        AmqpOutboundEndpoint endpoint = new AmqpOutboundEndpoint(amqpTemplate);
        endpoint.setExchangeName("bean.shipments.exchange");
        endpoint.setRoutingKey("bean.shipments.rk");
        return endpoint;
    }

    /** A router DIVERTS: the {@code handle} after it is not certainly what
     *  receives the message, so the row's handler is unresolved. */
    @Bean
    public IntegrationFlow kafkaRoutedFlow(ConsumerFactory<String, String> consumerFactory) {
        return IntegrationFlow.from(Kafka.messageDrivenChannelAdapter(consumerFactory, "kafka.routed.topic"))
                .route(String.class, payload -> payload.isEmpty() ? "emptyOrders" : "fullOrders")
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** The flow ends in a NAMED channel; the consumer is the annotated handler
     *  below, joined through the channel. */
    @Bean
    public IntegrationFlow kafkaToChannelFlow(ConsumerFactory<String, String> consumerFactory) {
        return IntegrationFlow.from(Kafka.messageDrivenChannelAdapter(consumerFactory, "kafka.channelled.topic"))
                .channel("kafkaInputChannel")
                .get();
    }

    @ServiceActivator(inputChannel = "kafkaInputChannel")
    public void handleKafkaOrder(String payload) {
        payload.isEmpty();
    }

    /** A {@code Pattern} subscription is not a topic name: the destination is
     *  unresolved, never a guess. */
    @Bean
    public IntegrationFlow kafkaPatternFlow(ConsumerFactory<String, String> consumerFactory) {
        return IntegrationFlow.from(Kafka.messageDrivenChannelAdapter(consumerFactory,
                        Pattern.compile("kafka\\.pattern\\..*")))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    // --- the ambiguous-bean near-miss --------------------------------------

    @Bean
    public MessageChannel firstAmbiguousChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel secondAmbiguousChannel() {
        return new DirectChannel();
    }

    /** Two channel beans of the interface, and a parameter named for neither:
     *  no qualifier, no bean of that name, never by type — the link is
     *  unresolved and the adapter's row keeps {@code handler} NULL. */
    @Bean
    public PubSubInboundChannelAdapter ambiguousChannelAdapter(PubSubTemplate pubSubTemplate,
                                                               MessageChannel someChannel) {
        PubSubInboundChannelAdapter adapter = new PubSubInboundChannelAdapter(pubSubTemplate, "ambiguous-sub");
        adapter.setOutputChannel(someChannel);
        return adapter;
    }
}
