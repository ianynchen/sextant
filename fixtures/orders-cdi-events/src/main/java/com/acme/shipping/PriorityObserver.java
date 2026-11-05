package com.acme.shipping;

import jakarta.annotation.Priority;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

@ApplicationScoped
public class PriorityObserver {

    /** `@Priority` orders observers and is no qualifier: every `Shipped` reaches it. */
    void on(@Observes @Priority(10) Shipped event) {
    }
}
