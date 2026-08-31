// The raw PubSub subscriber half: `Subscriber#newBuilder` registered once
// with the named `RawPubSubReceiver` and once with a lambda `MessageReceiver`
// — the two receiver-argument shapes downstream readers must each resolve.
package com.acme.orders.messaging.raw;

import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;

public class RawPubSubSubscribers {
    private final String project;

    public RawPubSubSubscribers(String project) {
        this.project = project;
    }

    public Subscriber withNamedReceiver() {
        return Subscriber.newBuilder(
                        ProjectSubscriptionName.of(project, "raw-notify"), new RawPubSubReceiver())
                .build();
    }

    public Subscriber withLambdaReceiver() {
        return Subscriber.newBuilder(
                        ProjectSubscriptionName.of(project, "raw-notify-lambda"),
                        (MessageReceiver) (m, c) -> c.ack())
                .build();
    }
}
