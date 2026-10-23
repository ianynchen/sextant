// Exists where `orders.notify` resolves to `kafka`: `application-prod.yml` sets it, `application.yml`
// does not, and `matchIfMissing` is false, so the bean exists in `prod` and not in `default`.
package com.acme.orders.conditional;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "orders.notify", havingValue = "kafka")
public class KafkaNotificationSender implements NotificationSender {
    @Override
    public void send(String message) {
        // inert: the bean's existence is what this fixture pins, not what it sends
    }
}
