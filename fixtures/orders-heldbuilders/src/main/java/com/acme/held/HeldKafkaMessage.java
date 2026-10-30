package com.acme.held;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.support.MessageBuilder;

/** `spring-kafka-message.yml` in the variable style: the topic header is set on the held
 *  `MessageBuilder`. One row, the topic `orders`. */
public class HeldKafkaMessage {
    private final KafkaTemplate<String, Order> kafkaTemplate;

    public HeldKafkaMessage(KafkaTemplate<String, Order> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void send(Order order) {
        MessageBuilder<Order> builder = MessageBuilder.withPayload(order);
        builder.setHeader(KafkaHeaders.TOPIC, "orders");
        kafkaTemplate.send(builder.build());
    }
}
