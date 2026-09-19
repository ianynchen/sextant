// The Kafka half of the messaging surface: every `@KafkaListener` attribute
// shape (a scalar `topics`, an array `topics`, `topicPattern`, a
// value-returning handler with a static `@SendTo`, and one with neither —
// the dynamic-reply row) in one listener class.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import com.acme.orders.contracts.ReceiptView;
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.messaging.handler.annotation.SendTo;

public class OrderEventsListener {

    @KafkaListener(topics = {"order-events", "order-audit"})
    public void onEvent(OrderEvent event, Acknowledgment ack) {
        ack.acknowledge();
    }

    @KafkaListener(topics = "order-returns")
    @SendTo("order-return-receipts")
    public ReceiptView onReturn(OrderEvent event) {
        return new ReceiptView();
    }

    @KafkaListener(topicPattern = "order-.*-dlq")
    public void onDeadLetter(ConsumerRecord<String, OrderEvent> record) {
    }

    @KafkaListener(topics = "order-batches")
    public void onBatch(List<OrderEvent> events) {
    }

    // `kafka-batch-generics`: `batch = "true"` makes this a BATCH listener — one element
    // per record, so the topic's wire payload is OrderEvent and `List` is the
    // container's envelope. `onBatch` above, with no attribute, is a RECORD listener
    // taking a list: its wire payload IS the list. Same parameter type, two contracts
    // (spec §5a).
    @KafkaListener(topics = "order-batch-records", batch = "true")
    public void onRecords(List<OrderEvent> events) {
    }

    // Spring parses the attribute with Boolean.parseBoolean — case-insensitive (M5).
    @KafkaListener(topics = "order-batch-records-upper", batch = "TRUE")
    public void onRecordsUpper(List<OrderEvent> events) {
    }

    // Value-returning, no `@SendTo`: the dynamic-reply row — the reply topic
    // comes from the record's KAFKA_REPLY_TOPIC header at runtime, not from
    // any annotation attribute.
    @KafkaListener(topics = "order-escalations")
    public ReceiptView escalate(OrderEvent event) {
        return new ReceiptView();
    }
}
