package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** The class named on the annotation, the method taking no parameter. */
@Component
public class ClassesListener {
    @EventListener(classes = OrderPlaced.class)
    public void on() {
        System.out.println("classes");
    }
}
