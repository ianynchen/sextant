package com.acme.shipping;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.ObservesAsync;

@ApplicationScoped
public class AsyncObserver {

    void on(@ObservesAsync Shipped event) {
    }
}
