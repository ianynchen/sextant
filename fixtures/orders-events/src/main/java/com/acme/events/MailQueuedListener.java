package com.acme.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** The listener of the chained-setter event. */
@Component
public class MailQueuedListener {
    @EventListener
    public void on(MailQueued event) {
        System.out.println("mail " + event.to());
    }
}
