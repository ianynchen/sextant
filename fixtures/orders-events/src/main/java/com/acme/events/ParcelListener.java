package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** The listener of an implementation of `DomainEvent`, never of `DomainEvent` itself. */
@Component
public class ParcelListener {
    @EventListener
    public void on(Parcel parcel) {
        System.out.println("parcel " + parcel);
    }
}
