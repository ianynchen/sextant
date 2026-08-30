// The PubSub half: a typed `subscribeAndConvert` — the reply-less,
// converted-payload sibling of Kafka's plain listener and JMS's typed one.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;

public class NotificationsSubscriber {
    private final PubSubTemplate pubSubTemplate;

    public NotificationsSubscriber(PubSubTemplate pubSubTemplate) {
        this.pubSubTemplate = pubSubTemplate;
    }

    public void subscribe() {
        pubSubTemplate.subscribeAndConvert(
                "order-notifications", message -> message.ack(), OrderEvent.class);
    }
}
