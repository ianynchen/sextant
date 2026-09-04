package com.example.siprobe;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.inbound.AmqpInboundChannelAdapter;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

/** Shape 2 — an adapter bean and an annotated handler, joined by a NAMED
 *  channel. The destination lives on the container; the channel name lives on
 *  the adapter (as a setter argument) and on the handler (as an annotation
 *  argument). Whether the SAME string is readable on both sides is Q3. */
@Configuration
public class Shape2AdapterAndHandler {

    /** {@code setQueueNames} is varargs: {@code setQueueNames(String...)}. */
    @Bean
    public SimpleMessageListenerContainer ordersContainer(ConnectionFactory connectionFactory) {
        SimpleMessageListenerContainer container = new SimpleMessageListenerContainer(connectionFactory);
        container.setQueueNames("bean.orders.queue");
        return container;
    }

    @Bean
    public AmqpInboundChannelAdapter ordersInboundAdapter(SimpleMessageListenerContainer ordersContainer) {
        AmqpInboundChannelAdapter adapter = new AmqpInboundChannelAdapter(ordersContainer);
        adapter.setOutputChannelName("amqpInputChannel");
        return adapter;
    }

    @Bean
    public MessageChannel amqpInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel amqpAuditChannel() {
        return new DirectChannel();
    }

    /** The other side of the join: the channel name as an annotation
     *  argument, with an output channel named too. */
    @ServiceActivator(inputChannel = "amqpInputChannel", outputChannel = "amqpAuditChannel")
    public String handleOrder(String payload) {
        return payload.trim();
    }

    /** A second handler whose channel name is a compile-time constant rather
     *  than a literal — annotation arguments must be constants, so this is the
     *  only alternative spelling the language allows. */
    @ServiceActivator(inputChannel = Destinations.ORDERS_CHANNEL)
    public void handleConstantChannel(String payload) {
        payload.isEmpty();
    }

    /** A third whose channel name is a property placeholder — legal, and
     *  resolved by Spring at runtime, not by javac. */
    @ServiceActivator(inputChannel = "${probe.audit-channel}")
    public void handlePlaceholderChannel(String payload) {
        payload.isEmpty();
    }
}
