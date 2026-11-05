package com.acme.events;

import java.util.List;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

/** Publishes events handed in by their interface or by `Object`: the declared type has no
 * listener of its own, while its implementations do. */
@Component
public class DomainEvents {
    private final ApplicationEventPublisher publisher;

    public DomainEvents(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    /** Declared `DomainEvent`; at run time a `Parcel`, whose listener runs. */
    public void publish(DomainEvent event) {
        publisher.publishEvent(event);
    }

    /** Each element read by `Iterator.next()`, declared `Object`. */
    public void publishAll(List<Object> events) {
        for (Object event : events) {
            publisher.publishEvent(event);
        }
    }
}
