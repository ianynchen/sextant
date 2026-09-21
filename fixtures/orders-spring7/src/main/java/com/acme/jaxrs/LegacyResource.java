package com.acme.jaxrs;

import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.QueryParam;
import javax.ws.rs.core.MediaType;

// The `javax.ws.rs` spelling (JAX-RS 2.1, Jakarta EE 8 and every 2.x-era Jersey/RESTEasy
// project). Same shape as `OrderResource`, other package.
@Path("/legacy/orders")
@Produces(MediaType.APPLICATION_JSON)
public class LegacyResource {
    @GET
    public String list() { return "[]"; }

    @POST
    public String create(String body) { return body; }

    @GET
    @Path("/{id}")
    public String byId(@PathParam("id") String id) { return id; }

    // Spec 2026-09-19 §5b, the `javax` spelling of the same `optional` rule.
    @GET
    @Path("/search")
    public String search(@QueryParam("q") String q) { return q; }
}
