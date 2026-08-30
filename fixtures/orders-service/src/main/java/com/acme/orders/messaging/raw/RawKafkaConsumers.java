// The raw Kafka consumer half: `KafkaConsumer#subscribe` called directly,
// once with a topic list and once with a `Pattern` — the raw-client sibling
// of `OrderEventsListener`'s `@KafkaListener` shapes.
package com.acme.orders.messaging.raw;

import com.acme.orders.contracts.OrderEvent;
import java.util.List;
import java.util.regex.Pattern;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class RawKafkaConsumers {
    private final KafkaConsumer<String, OrderEvent> consumer;

    public RawKafkaConsumers(KafkaConsumer<String, OrderEvent> consumer) {
        this.consumer = consumer;
    }

    public void subscribeToTopics() {
        consumer.subscribe(List.of("raw-t1", "raw-t2"));
    }

    public void subscribeToPattern() {
        consumer.subscribe(Pattern.compile("raw-.*"));
    }
}
