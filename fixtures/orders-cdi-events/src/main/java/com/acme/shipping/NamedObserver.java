package com.acme.shipping;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import jakarta.inject.Named;

@ApplicationScoped
public class NamedObserver {

    /** `@Named` is a library qualifier: notified only of events fired with `@Named("audit")`. */
    void on(@Observes @Named("audit") Shipped event) {
    }
}
