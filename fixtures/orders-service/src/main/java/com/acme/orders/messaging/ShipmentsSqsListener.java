// The SQS half: `@SqsListener`'s queue-name attribute — a single scalar,
// same shape family as JMS's `destination` and Kafka's scalar `topics`.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import io.awspring.cloud.sqs.annotation.SqsListener;

public class ShipmentsSqsListener {

    @SqsListener("shipments-inbound")
    public void onShipment(OrderEvent event) {
    }
}
