// The raw PubSub publisher half: one method builds and publishes off a
// freshly built `Publisher` in the same call chain, the other publishes off
// a field-held `Publisher` — the two shapes downstream `channel_via`/
// `all_strings` readers must each resolve on their own.
package com.acme.orders.messaging.raw;

import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import java.io.IOException;

public class RawPubSubPublishers {
    private final String project;
    private final Publisher publisher;

    public RawPubSubPublishers(String project, Publisher publisher) {
        this.project = project;
        this.publisher = publisher;
    }

    public void publishToNewTopic(PubsubMessage message) throws IOException {
        Publisher.newBuilder(TopicName.of(project, "raw-events")).build().publish(message);
    }

    public void publishToFieldPublisher(PubsubMessage message) {
        publisher.publish(message);
    }
}
