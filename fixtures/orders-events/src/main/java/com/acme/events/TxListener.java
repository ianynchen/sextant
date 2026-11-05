package com.acme.events;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class TxListener {
    @TransactionalEventListener
    public void on(OrderPlaced event) {
        System.out.println("after commit " + event.id());
    }
}
