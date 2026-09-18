package com.acme.jaxrs;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.sse.SseEventSink;
import java.util.List;

// M3's generated-interface pattern: every annotation on the interface, none on the
// class. JAX-RS §3.6 and all three implementations make the class a root resource and
// inherit the interface method's WHOLE annotation set.
@Path("/api/orders")
public interface OrdersApi {
    @GET
    List<String> list();

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    String byId(@PathParam("id") String id);

    @GET
    @Path("/events")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    void events(@Context SseEventSink sink);
}
