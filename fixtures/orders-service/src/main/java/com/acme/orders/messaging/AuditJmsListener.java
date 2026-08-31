// The JMS half: a typed listener (payload converted to OrderEvent) beside a
// raw one (the `jakarta.jms.Message` envelope itself), same `destination`
// attribute shape on both. `onAudit`'s destination is a placeholder
// (application.yml supplies `orders.audit.topic: audit-events`) — the
// row's own identity stays the expression verbatim per M04, never the
// resolved value.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;

public class AuditJmsListener {

    @JmsListener(destination = "${orders.audit.topic}")
    public void onAudit(OrderEvent event) {
    }

    @JmsListener(destination = "audit.raw")
    public void onRaw(Message message) {
    }
}
