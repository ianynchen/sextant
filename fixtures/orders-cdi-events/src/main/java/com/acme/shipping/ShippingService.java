package com.acme.shipping;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Event;
import jakarta.inject.Inject;

@ApplicationScoped
public class ShippingService {

    @Inject
    Event<Shipped> shipped;

    @Inject
    Event<Object> events;

    /** Synchronous: every `@Observes` observer of a supertype of `Shipped`. */
    public void ship(String id) {
        shipped.fire(new Shipped(id));
    }

    /** Asynchronous: every `@ObservesAsync` observer of a supertype of `Shipped`. */
    public void shipLater(String id) {
        shipped.fireAsync(new Shipped(id));
    }

    public void note() {
        events.fire(new Note());
    }

    /** The value's class is not known here. */
    public void refire(Object event) {
        events.fire(event);
    }
}
