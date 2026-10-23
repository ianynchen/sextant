// The other half of the pair: exists where `orders.notify` is `log` OR absent (`matchIfMissing`),
// so in `default` (key absent) and not in `prod` (key is `kafka`).
package com.acme.orders.conditional;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "orders.notify", havingValue = "log", matchIfMissing = true)
public class LogNotificationSender implements NotificationSender {
    @Override
    public void send(String message) {
        // inert: see KafkaNotificationSender
    }
}
