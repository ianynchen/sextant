package com.acme.mn;

import io.micronaut.http.annotation.Get;
import io.micronaut.http.client.annotation.Client;

/** Micronaut's declarative HTTP client: the SAME verb annotations as the server side, on an
 *  interface, with `@Client` naming the base. The direction is decided by the interface
 *  annotation, exactly as Spring's `@HttpExchange` interfaces are. */
@Client("/inventory")
public interface InventoryClient {
    @Get("/levels/{sku}")
    String level(String sku);
}
