package com.acme.held;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;

/**
 * The constructions. TWO of them, with different topics, which is §4 case 1 of spec
 * 2026-10-18: the set of possible values is CLOSED and readable, so enumerating both is the
 * exact answer rather than an ambiguity to hedge — one row per topic.
 */
@Configuration
public class PublisherWiring {

    @Bean
    public OrderPublisher ordersPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        return new OrderPublisher("orders-v2", kafkaTemplate);
    }

    @Bean
    public OrderPublisher auditPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        return new OrderPublisher("orders-audit", kafkaTemplate);
    }

    /** The field whose constant initialiser its own constructor overwrites: the row is
     *  `orders-overwritten`, and `never-reached-default` is a value no read can observe. */
    @Bean
    public OverwrittenPublisher overwrittenPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        return new OverwrittenPublisher("orders-overwritten", kafkaTemplate);
    }
}
