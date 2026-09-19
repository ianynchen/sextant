package com.acme.quarkus;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import org.eclipse.microprofile.rest.client.inject.RegisterRestClient;

// The second `mp-rest-client` shape: a client whose peer is a literal `baseUri` rather
// than a config key.
@RegisterRestClient(baseUri = "http://billing.internal/api")
@Path("/invoices")
public interface BillingClient {
    @GET
    String list();
}
