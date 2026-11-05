package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** A listener of the second marker interface. */
@Component
public class AuditableListener {
    @EventListener
    public void on(Auditable event) {
        System.out.println("audited " + event);
    }
}
