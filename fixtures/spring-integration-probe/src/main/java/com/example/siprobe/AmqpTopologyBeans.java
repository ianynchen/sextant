package com.example.siprobe;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** The declared-topology arm. Every AMQP API that takes a queue NAME takes it
 *  as varargs; the APIs that take a queue OBJECT do not. This class exists so
 *  the probe can say whether that distinction is the difference between a
 *  visible and an invisible destination, rather than assuming it. */
@Configuration
public class AmqpTopologyBeans {

    /** {@code new Queue(String)} — a single-argument constructor, not varargs. */
    @Bean
    public Queue topologyOrdersQueue() {
        return new Queue("topology.orders.queue", true);
    }

    @Bean
    public TopicExchange topologyOrdersExchange() {
        return new TopicExchange("topology.orders.exchange");
    }

    @Bean
    public Binding topologyOrdersBinding(Queue topologyOrdersQueue, TopicExchange topologyOrdersExchange) {
        return BindingBuilder.bind(topologyOrdersQueue)
                .to(topologyOrdersExchange)
                .with("topology.orders.rk");
    }

    /** {@code setQueues(Queue...)} is varargs too — but its elements are bean
     *  references rather than strings, so the destination is one hop away in
     *  the bean graph even when the array itself does not resolve. */
    @Bean
    public SimpleMessageListenerContainer topologyContainer(ConnectionFactory connectionFactory,
                                                            Queue topologyOrdersQueue) {
        SimpleMessageListenerContainer container = new SimpleMessageListenerContainer(connectionFactory);
        container.setQueues(topologyOrdersQueue);
        return container;
    }
}
