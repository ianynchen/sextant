package com.acme.mn;

import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Delete;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Post;
import io.micronaut.http.annotation.Produces;
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
}
