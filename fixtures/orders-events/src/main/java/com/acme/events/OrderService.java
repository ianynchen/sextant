package com.acme.events;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final ApplicationContext context;
    private OrderShipped lastShipped = new OrderShipped("none");

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
        ApplicationEvent event = OrderPlaced.of(this, id);
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

    /** An event handed in by the caller: its class is the parameter's declared type,
     * `Object`, so only a listener of `Object` is certainly reached. */
    public void republish(Object event) {
        publisher.publishEvent(event);
    }

    /** An event handed in by the caller as an array element: no call, parameter or field
     * produces the value itself, so its class is not read here. */
    public void republishFirst(Object[] events) {
        publisher.publishEvent(events[0]);
    }

    /** An event built with chained setters: the value is the last setter's result, whose
     * declared return type is the event's class. */
    public void queueMail(String to) {
        publisher.publishEvent(new MailQueued().setTo(to).setSubject("order"));
    }

    /** The same, held in a local and given its last setter statement by statement. */
    public void queueMailHeld(String to) {
        MailQueued mail = new MailQueued().setTo(to);
        mail.setSubject("order");
        publisher.publishEvent(mail);
    }

    /** An event held in an instance field: its class is the field's declared type. */
    public void publishLast() {
        publisher.publishEvent(lastShipped);
    }

    /** The same publish through the context, which inherits it. */
    public void placeThroughContext(String id) {
        context.publishEvent(new OrderPlaced(this, id));
    }
}
