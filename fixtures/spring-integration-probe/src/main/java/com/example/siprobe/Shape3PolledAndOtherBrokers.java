package com.example.siprobe;

import jakarta.jms.ConnectionFactory;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.integration.kafka.dsl.Kafka;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;

/** Shape 3 — the remaining real-world variants: a polled
 *  {@code @InboundChannelAdapter} whose destination is not a broker at all,
 *  and Kafka/JMS adapters alongside the AMQP ones so the probe can say whether
 *  the answer is AMQP-shaped or general. */
@Configuration
public class Shape3PolledAndOtherBrokers {

    /** A polled source. The channel name is an annotation argument; there is
     *  no destination string at all — the "destination" is this method. */
    @Bean
    @InboundChannelAdapter(channel = "tickChannel", poller = @Poller(fixedDelay = "5000"))
    public String tick() {
        return "tick";
    }

    /** Kafka inbound: {@code messageDrivenChannelAdapter(ConsumerFactory, String... topics)}
     *  — varargs again, and with TWO topics so the probe can see what a
     *  multi-destination call site looks like. */
    @Bean
    public IntegrationFlow kafkaInboundFlow(ConsumerFactory<String, String> consumerFactory) {
        return IntegrationFlow
                .from(Kafka.messageDrivenChannelAdapter(consumerFactory,
                        "kafka.orders.topic", "kafka.orders.retry.topic"))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** Kafka outbound: {@code .topic(String)} is a plain single-argument
     *  builder call, unlike the varargs inbound above. */
    @Bean
    public IntegrationFlow kafkaOutboundFlow(KafkaTemplate<String, String> kafkaTemplate) {
        return flow -> flow.handle(
                Kafka.outboundChannelAdapter(kafkaTemplate).topic("kafka.shipments.topic"));
    }

    /** JMS inbound: {@code .destination(String)}, a plain single-argument
     *  builder call. */
    @Bean
    public IntegrationFlow jmsInboundFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow
                .from(Jms.inboundAdapter(connectionFactory).destination("jms.orders.queue"),
                        e -> e.poller(p -> p.fixedDelay(1000)))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** JMS outbound. */
    @Bean
    public IntegrationFlow jmsOutboundFlow(ConnectionFactory connectionFactory) {
        return flow -> flow.handle(
                Jms.outboundAdapter(connectionFactory).destination("jms.shipments.queue"));
    }

    /** A destination read out of a config map rather than passed to an
     *  adapter — the shape a hand-rolled consumer factory takes. */
    @Bean
    public java.util.Map<String, Object> consumerConfig() {
        return java.util.Map.of(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "broker:9092",
                ConsumerConfig.GROUP_ID_CONFIG, "si-probe-group");
    }
}
