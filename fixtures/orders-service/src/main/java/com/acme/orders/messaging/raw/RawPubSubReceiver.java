// The named `MessageReceiver` implementation: the raw-client sibling of the
// lambda receiver registered alongside it in `RawPubSubSubscribers`.
package com.acme.orders.messaging.raw;

import com.google.cloud.pubsub.v1.AckReplyConsumer;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.pubsub.v1.PubsubMessage;

public class RawPubSubReceiver implements MessageReceiver {

    @Override
    public void receiveMessage(PubsubMessage message, AckReplyConsumer consumer) {
        consumer.ack();
    }
}
