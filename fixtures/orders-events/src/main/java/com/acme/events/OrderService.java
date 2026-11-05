package com.acme.events;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final ApplicationContext context;

    public OrderService(ApplicationEventPublisher publisher, ApplicationContext context) {
        this.publisher = publisher;
        this.context = context;
    }

    /** A new event published in place: its class is read where it is constructed. */
    public void place(String id) {
        publisher.publishEvent(new OrderPlaced(this, id));
    }

    /** An event a module factory makes, held in a local: its class is read through the
     * factory's own return. */
    public void placeThroughFactory(String id) {
        OrderPlaced event = OrderPlaced.of(this, id);
        publisher.publishEvent(event);
    }

    /** A second event class: its own listener, and the listener of `Object`. */
    public void ship(String id) {
        publisher.publishEvent(new OrderShipped(id));
    }

    /** A plain object, through `publishEvent(Object)`: only the listener of `Object`. */
    public void note() {
        publisher.publishEvent(new Note());
    }

    /** An event handed in by the caller: its class is not read here. */
    public void republish(Object event) {
        publisher.publishEvent(event);
    }

    /** The same publish through the context, which inherits it. */
    public void placeThroughContext(String id) {
        context.publishEvent(new OrderPlaced(this, id));
    }
}
