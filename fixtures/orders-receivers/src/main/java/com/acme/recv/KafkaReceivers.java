package com.acme.recv;

import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.core.KafkaTemplate;

public class KafkaReceivers {
    private final KafkaTemplate<String, String> template;

    public KafkaReceivers(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public ConsumerRecord<String, String> peekOne() {
        return template.receive("recv.orders.replay", 0, 42L, Duration.ofSeconds(5));
    }
}
