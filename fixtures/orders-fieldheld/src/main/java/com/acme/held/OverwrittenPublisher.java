package com.acme.held;

import org.springframework.kafka.core.KafkaTemplate;

/**
 * A field with a constant initialiser that the constructor immediately overwrites.
 *
 * <p>javac puts the initialiser into the one constructor, two instructions before the
 * constructor's own assignment and in the same basic block:
 *
 * <pre>
 *   5: ldc       "never-reached-default"
 *   7: putfield  topic
 *  10: aload_1
 *  11: putfield  topic
 * </pre>
 *
 * <p>so no read anywhere can observe `never-reached-default`. Reporting it published a
 * destination the code cannot produce, at `resolved` — found by review before the constant
 * write shipped. The extractor now drops a write its own block overwrites, which is why this
 * fixture publishes `orders-overwritten` alone.
 *
 * <p>A later write behind a BRANCH is a different case and is still reported: when the
 * branch is not taken the earlier value is live. The register's `OI-138` carries the one
 * shape still over-reported — an initialiser overwritten on every branch of an if/else.
 */
public class OverwrittenPublisher {

    private String topic = "never-reached-default";
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OverwrittenPublisher(String topic, KafkaTemplate<String, String> kafkaTemplate) {
        this.topic = topic;
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String payload) {
        kafkaTemplate.send(topic, payload);
    }
}
