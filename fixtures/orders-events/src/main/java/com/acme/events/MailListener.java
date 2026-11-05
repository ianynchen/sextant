package com.acme.events;

import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

/** The interface form: javac writes `onApplicationEvent(OrderPlaced)` and a bridge
 * `onApplicationEvent(ApplicationEvent)` that calls it. */
@Component
public class MailListener implements ApplicationListener<OrderPlaced> {
    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("mail " + event.id());
    }
}
