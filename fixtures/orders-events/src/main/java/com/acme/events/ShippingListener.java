package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** A listener of the second event only: an `OrderPlaced` never reaches it. */
@Component
public class ShippingListener {
    @EventListener
    public void on(OrderShipped event) {
        System.out.println("shipping " + event.id());
    }
}
