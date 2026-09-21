package com.acme.jaxrs;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.HeaderParam;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.sse.Sse;
import jakarta.ws.rs.sse.SseEventSink;
import java.util.List;

/** JAX-RS as Quarkus, Helidon, Jersey and RESTEasy all use it: the verb is a MARKER
 *  annotation carrying nothing, the path is a SEPARATE `@Path` on the class and/or the
 *  method, and the two combine. `@Produces(SERVER_SENT_EVENTS)` is how SSE is declared. */
@Path("/jaxrs/orders")
@Produces(MediaType.APPLICATION_JSON)
public class OrderResource {

    @GET
    public List<String> list() { return List.of(); }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public String create(String body) { return body; }

    @GET
    @Path("/{id}")
    public String byId(@PathParam("id") String id) { return id; }

    @DELETE
    @Path("/{id}")
    public void remove(@PathParam("id") String id) {}

    @GET
    @Path("/events")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    public void events(SseEventSink sink, Sse sse) {}

    // Spec 2026-09-19 §5b: JAX-RS's binder rule is `optional` for every named parameter —
    // absent → null, or the SEPARATE `@DefaultValue`, never a 400 (CP-25 rows 9–10). Both
    // rows below are `optional`; the default is information, not a requirement.
    @GET
    @Path("/search")
    public List<String> search(@QueryParam("q") @DefaultValue("*") String q,
                               @HeaderParam("X-Tenant") String tenant) { return List.of(); }
}
