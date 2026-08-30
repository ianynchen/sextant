// The `Message`-builder half of the Kafka producer surface: the topic comes
// from a `MessageBuilder` header, not the `KafkaTemplate#send` argument list
// itself — the shape `EventProducers`' direct-argument sends don't exercise.
package com.acme.orders.messaging.raw;

import com.acme.orders.contracts.OrderEvent;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.support.MessageBuilder;

public class RawKafkaMessageSender {
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public RawKafkaMessageSender(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void send(OrderEvent event) {
        kafkaTemplate.send(
                MessageBuilder.withPayload(event).setHeader(KafkaHeaders.TOPIC, "raw-messages").build());
    }
}
