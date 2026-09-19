package com.acme.quarkus;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.util.List;
import org.eclipse.microprofile.rest.client.inject.RegisterRestClient;

// `mp-rest-client` (spec §3f): a client is an INTERFACE carrying the JAX-RS annotations,
// gated by @RegisterRestClient. The same words as the resource catalogs, direction out.
@RegisterRestClient(configKey = "orders")
@Path("/remote/orders")
@Produces(MediaType.APPLICATION_JSON)
public interface OrdersClient {
    @GET
    List<OrderResource.Order> list();

    @GET
    @Path("/{id}")
    OrderResource.Order byId(@PathParam("id") String id);
}
