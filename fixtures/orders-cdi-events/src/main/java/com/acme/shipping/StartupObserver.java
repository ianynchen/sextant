package com.acme.shipping;

import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

@ApplicationScoped
public class StartupObserver {

    /** Quarkus fires `StartupEvent`; nothing in this module does. The second parameter is
     *  injected, as in the Quarkus quickstarts' `init(@Observes StartupEvent ev, Vertx vertx)`. */
    void onStart(@Observes StartupEvent event, ShippingService service) {
    }
}
