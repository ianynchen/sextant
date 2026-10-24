package com.acme.quarkus.quotes;

import org.eclipse.microprofile.reactive.messaging.Incoming;

// The configured-destination channel (spec §3e): `application.properties` names its
// topic, so the row is at `orders.audit`, not at the channel name.
public class AuditListener {
    @Incoming("audit")
    public void onAudit(String event) {
        System.out.println(event);
    }
}
