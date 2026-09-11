// The raw PubSub subscriber half: `Subscriber#newBuilder` registered once with the
// named `RawPubSubReceiver` and once with a lambda `MessageReceiver` — the two
// receiver-argument shapes downstream readers must each resolve — plus one that is
// built and handed back without being started.
//
// Construction is not subscription: a `Subscriber` delivers nothing until
// `startAsync()` runs (GUIDELINES §8.6, `OI-64`). This file used to build two
// subscribers, start NEITHER, and have both published as live inbound endpoints that
// the test suite asserted were correct. The two that derive rows now start what they
// build, and the third is the case we cannot answer from one method.
package com.acme.orders.messaging.raw;

import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;

public class RawPubSubSubscribers {
    private final String project;

    public RawPubSubSubscribers(String project) {
        this.project = project;
    }

    // A named `MessageReceiver` implementation, started here. A real boundary.
    public void startNamedReceiver() {
        Subscriber.newBuilder(
                        ProjectSubscriptionName.of(project, "raw-notify"), new RawPubSubReceiver())
                .build()
                .startAsync();
    }

    // A lambda `MessageReceiver`, started here — and with a builder setter in between,
    // which is the spelling Google's own documentation uses and the one an earlier
    // version of the activation walk could not follow.
    public void startLambdaReceiver() {
        Subscriber.newBuilder(
                        ProjectSubscriptionName.of(project, "raw-notify-lambda"),
                        (MessageReceiver) (m, c) -> c.ack())
                .setParallelPullCount(2)
                .build()
                .startAsync();
    }

    // Built and handed back. Nothing here starts it and the caller may; chain
    // reconstruction is within-method only, so this is a `registration_activation`
    // question rather than either a row or silence.
    public Subscriber withNamedReceiver() {
        return Subscriber.newBuilder(
                        ProjectSubscriptionName.of(project, "raw-notify-factory"),
                        new RawPubSubReceiver())
                .build();
    }
}
