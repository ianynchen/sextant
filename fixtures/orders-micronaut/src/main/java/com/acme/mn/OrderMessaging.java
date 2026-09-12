package com.acme.mn;

import io.micronaut.configuration.kafka.annotation.KafkaClient;
import io.micronaut.configuration.kafka.annotation.KafkaListener;
import io.micronaut.configuration.kafka.annotation.Topic;
import io.micronaut.gcp.pubsub.annotation.PubSubClient;
import io.micronaut.gcp.pubsub.annotation.PubSubListener;
import io.micronaut.gcp.pubsub.annotation.Subscription;
import io.micronaut.jms.annotations.JMSListener;
import io.micronaut.jms.annotations.JMSProducer;
import io.micronaut.jms.annotations.Queue;

/** Micronaut's three messaging integrations, each as an application declares it: a
 *  class-level marker naming the role, and a method annotation naming the destination. */
public class OrderMessaging {

    @KafkaListener(groupId = "orders")
    public static class KafkaConsumer {
        @Topic("mn.orders.placed")
        public void onPlaced(String event) {}
    }

    @KafkaClient
    public interface KafkaSender {
        @Topic("mn.orders.shipped")
        void shipped(String event);
    }

    @JMSListener("orders-connection")
    public static class JmsConsumer {
        @Queue("mn.orders.queue")
        public void onQueued(String body) {}
    }

    @JMSProducer("orders-connection")
    public interface JmsSender {
        @Queue("mn.orders.audit")
        void audit(String body);
    }

    @PubSubListener
    public static class PubSubConsumer {
        @Subscription("mn-orders-sub")
        public void onMessage(byte[] data) {}
    }

    @PubSubClient
    public interface PubSubSender {
        @io.micronaut.gcp.pubsub.annotation.Topic("mn-orders-topic")
        void publish(byte[] data);
    }
}
