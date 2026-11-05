package com.acme.shipping;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

@ApplicationScoped
public class ExpressObserver {

    /** Notified only of `Shipped` events fired with `@Express`, which no fire here names. */
    void on(@Observes @Express Shipped event) {
    }
}
