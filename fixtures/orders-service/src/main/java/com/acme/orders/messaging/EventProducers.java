// The producer half of the messaging surface: one method per overload shape
// the outbound messaging catalogs (Tasks 6-11) must each match on its own —
// same "one field, one call, never conjured per call" discipline as
// BillingRestTemplate's single_call surface.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import com.acme.orders.contracts.ReceiptView;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.requestreply.ReplyingKafkaTemplate;

public class EventProducers {
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final ReplyingKafkaTemplate<String, OrderEvent, ReceiptView> replyingTemplate;
    private final KafkaProducer<String, OrderEvent> rawProducer;
    private final JmsTemplate jmsTemplate;
    private final SqsTemplate sqsTemplate;
    private final PubSubTemplate pubSubTemplate;

    public EventProducers(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            ReplyingKafkaTemplate<String, OrderEvent, ReceiptView> replyingTemplate,
            KafkaProducer<String, OrderEvent> rawProducer,
            JmsTemplate jmsTemplate,
            SqsTemplate sqsTemplate,
            PubSubTemplate pubSubTemplate) {
        this.kafkaTemplate = kafkaTemplate;
        this.replyingTemplate = replyingTemplate;
        this.rawProducer = rawProducer;
        this.jmsTemplate = jmsTemplate;
        this.sqsTemplate = sqsTemplate;
        this.pubSubTemplate = pubSubTemplate;
    }

    public void send(OrderEvent event) {
        kafkaTemplate.send("order-events", event);
    }

    public void sendKeyed(String key, OrderEvent event) {
        kafkaTemplate.send("order-events", key, event);
    }

    public void sendDefault(OrderEvent event) {
        kafkaTemplate.sendDefault(event);
    }

    public void sendAudit(OrderEvent event) {
        kafkaTemplate.send(new ProducerRecord<>("order-audit", event));
    }

    public void sendRaw(String key, OrderEvent event) {
        rawProducer.send(new ProducerRecord<>("order-raw", key, event));
    }

    public void sendReturn(OrderEvent event) {
        replyingTemplate.sendAndReceive(new ProducerRecord<>("order-returns", event));
    }

    public void sendAuditMessage(OrderEvent event) {
        jmsTemplate.convertAndSend("audit.queue", event);
    }

    public void sendToDefaultDestination(OrderEvent event) {
        jmsTemplate.convertAndSend(event);
    }

    public void sendShipment(OrderEvent event) {
        sqsTemplate.send("shipments-outbound", event);
    }

    // The consumer-builder overload. The queue name is set INSIDE the lambda,
    // not at the call site's own arg 0 — the SDK's own fluent form.
    //
    // This comment used to end "an honest unresolved row, not a fabricated
    // \"shipments-lambda\" path", and that was the defect rather than the
    // discipline (`OI-74`, closed in W57). The literal is in the lambda's own
    // synthetic method, which the fact stream records under the symbol this
    // call's argument names, so reading it is reading. The row derives
    // `shipments-lambda` at `resolved` now, with the payload's contract too.
    public void sendShipmentViaBuilder(OrderEvent event) {
        sqsTemplate.send(to -> to.queue("shipments-lambda").payload(event));
    }

    public void publishNotification(OrderEvent event) {
        pubSubTemplate.publish("order-notifications", event);
    }
}
