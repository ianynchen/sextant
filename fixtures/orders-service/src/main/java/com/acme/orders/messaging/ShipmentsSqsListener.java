// The SQS half: `@SqsListener`'s queue-name attribute — a single scalar,
// same shape family as JMS's `destination` and Kafka's scalar `topics`. A
// second, bare `Acknowledgement` parameter alongside the payload proves
// `spring-sqs.yml`'s own exclude is load-bearing — the same shape Kafka's
// `onEvent(OrderEvent, Acknowledgment)` already exercises.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.Acknowledgement;

public class ShipmentsSqsListener {

    @SqsListener("shipments-inbound")
    public void onShipment(OrderEvent event, Acknowledgement ack) {
    }
}
