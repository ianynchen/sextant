// The messaging half of the composition proof: meta-annotated with
// `@KafkaListener` so the same pre-pass mechanism widens `annotation_driven`
// catalogs generally, not just HTTP.
package com.acme.orders.composed;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.kafka.annotation.KafkaListener;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@KafkaListener(topics = "composed-orders")
public @interface OrderTopicListener {
}
