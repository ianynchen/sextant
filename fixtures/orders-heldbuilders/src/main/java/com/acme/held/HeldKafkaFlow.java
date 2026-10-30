package com.acme.held;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.kafka.dsl.Kafka;
import org.springframework.kafka.core.KafkaTemplate;

/** `spring-integration-kafka.yml` in the variable style: the sink spec is held and its topic
 *  set in a statement of its own before the flow hands it to `handle`. One outbound row,
 *  the topic `orders`. */
@Configuration
public class HeldKafkaFlow {

    @Bean
    public IntegrationFlow heldKafkaOutboundFlow(KafkaTemplate<String, String> kafkaTemplate) {
        return flow -> {
            var sink = Kafka.outboundChannelAdapter(kafkaTemplate);
            sink.topic("orders");
            flow.handle(sink);
        };
    }
}
