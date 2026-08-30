// The class-level `@KafkaListener` + `@KafkaHandler` polymorphic shape: the
// listener annotation sits on the class (its own `topics` becomes the path
// prefix — and, in a multi-topic declaration, only element 0 of it, a known
// limitation), and each handler method is picked out by `@KafkaHandler`
// instead, which carries no path attribute of its own.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import org.springframework.kafka.annotation.KafkaHandler;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "order-polymorphic")
public class ClassLevelListener {

    @KafkaHandler
    public void onEvent(OrderEvent event) {
    }

    @KafkaHandler(isDefault = true)
    public void onDefault(Object event) {
    }
}
