package com.acme.quarkus.quotes;

import jakarta.inject.Inject;
import org.eclipse.microprofile.reactive.messaging.Channel;
import org.eclipse.microprofile.reactive.messaging.Emitter;

// An injected `Emitter` on `@Channel` (spec §3e): the injected TYPE makes it outgoing
// (CP-49 rows 21, 26). An orphan, attached to Kafka like the processor's two.
public class QuoteRequester {
    @Inject
    @Channel("quote-requests")
    Emitter<String> emitter;

    public void request(String id) {
        emitter.send(id);
    }
}
