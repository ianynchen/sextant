package com.acme.shipping;

/** The application's own event: a plain object, as CDI events are. */
public class Shipped {
    private final String id;

    public Shipped(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
