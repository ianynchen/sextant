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

    /** The value is a parameter declared `Object`: only an observer of `Object` is certainly
     * notified. */
    public void refire(Object event) {
        events.fire(event);
    }

    /** The value is an array element: no call, parameter or field produces it, so its class
     * is not known here. */
    public void refireFirst(Object[] pending) {
        events.fire(pending[0]);
    }
}
