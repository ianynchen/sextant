package com.acme.events;

/** A second event, a plain object: Spring wraps it in a `PayloadApplicationEvent` on
 * publish, and its listeners are keyed by its own class. */
public class OrderShipped {
    private final String id;

    public OrderShipped(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
