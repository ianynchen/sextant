package com.example.siprobe;

import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.dsl.IntegrationFlow;

/** Shape 1 — the Java DSL flow. The channels between the adapter and the
 *  handler are anonymous: the flow object itself is the connection, and no
 *  channel name is written anywhere. */
@Configuration
public class Shape1DslFlows {

    /** Inbound: the queue name is a literal at the adapter factory's call
     *  site. Note the factory's signature is
     *  {@code inboundAdapter(ConnectionFactory, String... queueNames)}. */
    @Bean
    public IntegrationFlow ordersInboundDslFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, "dsl.orders.queue"))
                .handle(String.class, (payload, headers) -> payload.toUpperCase())
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** Outbound: exchange and routing key are literals at two chained
     *  builder calls, each a plain single-argument String method. */
    @Bean
    public IntegrationFlow shipmentsOutboundDslFlow(AmqpTemplate amqpTemplate) {
        return flow -> flow.handle(
                Amqp.outboundAdapter(amqpTemplate)
                        .exchangeName("dsl.shipments.exchange")
                        .routingKey("dsl.shipments.rk"));
    }

    /** A DSL flow that DOES name its channel — the same DSL, opted into a
     *  named channel, so the probe can tell "the DSL cannot name channels"
     *  apart from "this flow did not". */
    @Bean
    public IntegrationFlow namedChannelDslFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, "dsl.named.queue"))
                .channel("dslNamedChannel")
                .handle(String.class, (payload, headers) -> null)
                .get();
    }
}
