package com.acme.quarkus.quotes;

import org.eclipse.microprofile.reactive.messaging.Incoming;
import org.eclipse.microprofile.reactive.messaging.Outgoing;

// A processor (spec 2026-10-24 §3e): one method consumes a channel and produces another.
// Neither channel is configured, and no other channel in the module carries either name,
// so both are ORPHANS and Quarkus attaches the module's one connector, Kafka, to each
// (CP-50 rows 1, 7). Kafka's destination defaults to the channel name (CP-51 rows 4-5).
public class QuoteProcessor {
    @Incoming("requests")
    @Outgoing("quotes")
    public String process(String request) {
        return "quote for " + request;
    }
}
