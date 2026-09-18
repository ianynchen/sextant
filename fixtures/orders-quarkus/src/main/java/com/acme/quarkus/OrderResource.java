package com.acme.quarkus;

import io.smallrye.mutiny.Multi;
import io.vertx.ext.web.RoutingContext;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.jboss.resteasy.reactive.RestStreamElementType;

// The five Quarkus REST cases the spec §3e names. The class keeps @Path (R1: Quarkus
// does not relax it for servers).
@Path("/q/orders")
public class OrderResource {
    public static class Order { public String sku; }
    public static class OrderEvent { public String sku; }

    // implicit path binding: `id` matches `{id}`, so it is a path param and there is no body
    @GET
    @Path("/{id}")
    public Order byId(String id) { return new Order(); }

    // implicit path binding beside a real body
    @PUT
    @Path("/{id}")
    public Order replace(String id, Order order) { return order; }

    // container: no body
    @POST
    @Path("/upload")
    public String upload(Upload form) { return form.fileName; }

    // Vert.x context type, injected without @Context: no body
    @GET
    @Path("/whoami")
    public String whoami(RoutingContext rc) { return rc.normalizedPath(); }

    // M1: no @Produces — the element type alone makes this SSE
    @GET
    @Path("/events")
    @RestStreamElementType(MediaType.APPLICATION_JSON)
    public Multi<OrderEvent> events() { return Multi.createFrom().empty(); }

    // the explicit SSE form, for the media hint
    @GET
    @Path("/ticks")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    public Multi<String> ticks() { return Multi.createFrom().empty(); }
}
