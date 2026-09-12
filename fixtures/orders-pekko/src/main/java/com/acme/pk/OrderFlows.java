package com.acme.pk;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.pekko.kafka.ConsumerSettings;
import org.apache.pekko.kafka.Subscriptions;
import org.apache.pekko.kafka.javadsl.Consumer;
import org.apache.pekko.stream.javadsl.Source;

public class OrderFlows {
    public Source<ConsumerRecord<String, String>, Consumer.Control> placed(ConsumerSettings<String, String> settings) {
        return Consumer.plainSource(settings, Subscriptions.topics("pk.orders.placed"));
    }

    public Source<ConsumerRecord<String, String>, Consumer.Control> audit(ConsumerSettings<String, String> settings) {
        return Consumer.plainSource(settings, Subscriptions.topics("pk.audit.a", "pk.audit.b"));
    }
}
