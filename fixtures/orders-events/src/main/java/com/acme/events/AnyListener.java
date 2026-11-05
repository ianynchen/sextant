package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** A listener of a supertype: every event the context publishes reaches it. */
@Component
public class AnyListener {
    @EventListener
    public void on(Object event) {
        System.out.println("any " + event);
    }
}
