package com.acme.held;

import org.springframework.kafka.core.KafkaTemplate;

/**
 * A publisher with a `private` reset helper that NOTHING calls.
 *
 * <p>`switchToBackup` cannot run: it is private, so every possible caller is in this class,
 * and no instruction here references it. Its constant was published as a `resolved`
 * destination all the same — found by review — because a constant write needs no crossing
 * and so skipped the reachability question the parameter arm answers for free.
 *
 * <p>The published row is `orders-live` alone. A PUBLIC method with no caller stays reported:
 * it is called by something outside what was scanned — a container, a test, another module —
 * which is a different statement from "it cannot run".
 */
public class ResettablePublisher {

    private String topic = "orders-live";
    private final KafkaTemplate<String, String> kafkaTemplate;

    public ResettablePublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    private void switchToBackup() {
        this.topic = "orders-backup-nothing-calls";
    }

    public void publish(String payload) {
        kafkaTemplate.send(topic, payload);
    }
}
