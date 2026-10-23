// The interface a handler calls through. Two implementations exist, each under its own
// `@ConditionalOnProperty` on `orders.notify` (spec 2026-10-22-conditional-beans), so the call
// `NotifyController.notify` makes narrows to a different candidate in each environment.
package com.acme.orders.conditional;

public interface NotificationSender {
    void send(String message);
}
