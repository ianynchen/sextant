package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AuditListener {
    @EventListener
    public void on(OrderPlaced event) {
        System.out.println("audit " + event.id());
    }
}
