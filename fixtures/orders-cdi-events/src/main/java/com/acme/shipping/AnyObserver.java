package com.acme.shipping;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

@ApplicationScoped
public class AnyObserver {

    void on(@Observes Object event) {
    }
}
