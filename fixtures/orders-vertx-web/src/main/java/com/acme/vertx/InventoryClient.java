package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.core.buffer.Buffer;

/** Outbound WebClient calls whose address is in the call (spec 2026-10-30 §3d). */
public class InventoryClient {

    private final WebClient client;

    public InventoryClient(WebClient client) {
        this.client = client;
    }

    public Future<HttpResponse<Buffer>> stock(String sku) {
        return client.get(8080, "inventory", "/stock/" + sku).send();
    }

    public Future<HttpResponse<Buffer>> charge(Charge charge) {
        return client.postAbs("http://billing/charges").sendJson(charge);
    }
}
