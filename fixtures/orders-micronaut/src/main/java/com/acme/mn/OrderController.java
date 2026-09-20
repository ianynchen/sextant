package com.acme.mn;

import io.micronaut.core.annotation.Nullable;
import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Delete;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Header;
import io.micronaut.http.annotation.Post;
import io.micronaut.http.annotation.Produces;
import io.micronaut.http.annotation.QueryValue;
import java.util.List;

/** Micronaut's HTTP server side, as an application writes it. */
@Controller("/mn/orders")
@Produces(MediaType.APPLICATION_JSON)
public class OrderController {

    @Get
    public List<String> list() { return List.of(); }

    @Get("/{id}")
    public String byId(String id) { return id; }

    // Bare `@Post`, the ordinary spelling for "the controller's own path". Whether
    // Micronaut normalises an explicit `uri = "/"` to the same address is a framework rule
    // this fixture does not exercise and the catalog does not claim.
    @Post(consumes = MediaType.APPLICATION_JSON)
    public String create(@Body String body) { return body; }

    @Delete("/{id}")
    public void remove(String id) {}

    // Spec 2026-09-19 §5b: Micronaut's binder has no `required` attribute — an absent
    // `@QueryValue` is null only when the argument is nullable (`Argument.isNullable()`,
    // the `jakarta.annotation.Nullable` stereotype Micronaut's own `@Nullable` maps onto),
    // `Optional.empty()` for an `Optional`, and otherwise `UnsatisfiedRouteException`, a
    // 400 (CP-25 rows 6–8). `q` is optional, `tenant`, `pageSize` and the header are
    // required — but `pageSize` is served by `?pageSize=` OR `?page-size=`, the binder
    // retrying an unwritten name in its hyphenated spelling (CP-25 row 18), so its row
    // names nothing rather than one of the two.
    @Get("/search")
    public String search(@QueryValue @Nullable String q,
                         @QueryValue String tenant,
                         @QueryValue String pageSize,
                         @Header("X-Tenant") String tenantHeader) { return q + pageSize; }
}
