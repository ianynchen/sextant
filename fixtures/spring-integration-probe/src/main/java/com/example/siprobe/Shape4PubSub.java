package com.example.siprobe;

import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

/** Shape 4 — the Pub/Sub bean-wired registration (spec 2026-09-21 §4, §11):
 *  the subscription is a CONSTRUCTOR argument, the channel it feeds is set by
 *  one of the two {@code MessageProducerSupport} setters, and the handler is a
 *  {@code @ServiceActivator} on that channel. Two adapters feed one channel so
 *  the join has two feeders and one reader. */
@Configuration
public class Shape4PubSub {

    /** The channel is an injected BEAN, named by its qualifier. */
    @Bean
    public PubSubInboundChannelAdapter ordersSubscriptionAdapter(PubSubTemplate pubSubTemplate,
                                                                 @Qualifier("pubsubInputChannel") MessageChannel channel) {
        PubSubInboundChannelAdapter adapter = new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
        adapter.setOutputChannel(channel);
        return adapter;
    }

    /** The channel is a NAME; the subscription is a {@code @Value} placeholder
     *  the field ladder reads as the {@code ${...}} expression it carries. */
    @Bean
    public PubSubInboundChannelAdapter placeholderSubscriptionAdapter(PubSubTemplate pubSubTemplate,
                                                                      @Value("${probe.subscription}") String subscription) {
        PubSubInboundChannelAdapter adapter = new PubSubInboundChannelAdapter(pubSubTemplate, subscription);
        adapter.setOutputChannelName("pubsubInputChannel");
        return adapter;
    }

    @Bean
    public MessageChannel pubsubInputChannel() {
        return new DirectChannel();
    }

    @ServiceActivator(inputChannel = "pubsubInputChannel")
    public void handlePubSubOrder(String payload) {
        payload.isEmpty();
    }

    /** The OUTBOUND handler bean: the topic is a constructor argument, and the
     *  channel it consumes is the constructing method's own annotation. */
    @Bean
    @ServiceActivator(inputChannel = "pubsubOutputChannel")
    public PubSubMessageHandler ordersTopicHandler(PubSubTemplate pubSubTemplate) {
        return new PubSubMessageHandler(pubSubTemplate, "orders-topic");
    }
}
