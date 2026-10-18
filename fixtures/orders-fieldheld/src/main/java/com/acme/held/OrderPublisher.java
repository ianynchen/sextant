package com.acme.held;

import org.springframework.kafka.core.KafkaTemplate;

/**
 * A publisher whose destination is a FIELD, assigned once by the constructor.
 *
 * <p>Nothing at the `send` call site names the topic: the argument is a field read, and the
 * only statement of its value is the literal a caller passed to this constructor. That is
 * the walk's sixth edge — `field_writes` already records "this field holds parameter 0", and
 * until the edge existed `_binding` answered `no_writer` and the row published no
 * destination at all.
 */
public class OrderPublisher {

    private final String topic;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(String topic, KafkaTemplate<String, String> kafkaTemplate) {
        this.topic = topic;
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String payload) {
        kafkaTemplate.send(topic, payload);
    }
}
