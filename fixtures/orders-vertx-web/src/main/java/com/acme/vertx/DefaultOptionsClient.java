package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * Options built by the no-argument constructor that set no address (rule 5): every call on them
 * is read and none sets a default, so Vert.x sends to its own, {@code localhost:80} (CP-56
 * row 132).
 */
public class DefaultOptionsClient {

    private final WebClient client;

    public DefaultOptionsClient(Vertx vertx) {
        this.client = WebClient.create(vertx, new WebClientOptions().setConnectTimeout(5000));
    }

    public Future<HttpResponse<Buffer>> query() {
        return client.get("/local").send();
    }
}
