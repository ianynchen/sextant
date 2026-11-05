package com.acme.events;

import org.springframework.context.ApplicationEvent;

/** The event. It extends `ApplicationEvent` so that an `ApplicationListener` may name it
 * (the interface bounds its type variable there); an `@EventListener` takes any object. */
public class OrderPlaced extends ApplicationEvent {
    private final String id;

    public OrderPlaced(Object source, String id) {
        super(source);
        this.id = id;
    }

    /** A static factory, the shape apollo-portal's `ConfigPublishEvent.instance()` takes. */
    public static OrderPlaced of(Object source, String id) {
        return new OrderPlaced(source, id);
    }

    public String id() {
        return id;
    }
}
