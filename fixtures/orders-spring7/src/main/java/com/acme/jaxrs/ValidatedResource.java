package com.acme.jaxrs;

import jakarta.validation.Valid;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;

// M2's Java case: the entity parameter carries a Bean Validation annotation. To JAX-RS
// `@Valid` is not a parameter-binding annotation, so `order` is the body; under the
// shipped `sole_unannotated` rule any annotation disqualified it.
@Path("/validated/orders")
public class ValidatedResource {
    public static class Order { public String sku; public int quantity; }

    @POST
    public Order create(@Valid Order order) { return order; }
}
