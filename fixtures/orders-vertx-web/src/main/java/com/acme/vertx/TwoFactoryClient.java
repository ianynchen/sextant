package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * One client field written by two factories (spec 2026-11-02-per-path-truth rule 4): one sets
 * the default port, the other sets none. A run through {@code secure} sends to port 8443, a run
 * through {@code plain} to Vert.x's own default, 80. Neither is the other's answer.
 */
public class TwoFactoryClient {

    private WebClient client;

    public void secure(Vertx vertx) {
        this.client = WebClient.create(
            vertx, new WebClientOptions().setDefaultHost("two").setDefaultPort(8443));
    }

    public void plain(Vertx vertx) {
        this.client = WebClient.create(vertx, new WebClientOptions().setDefaultHost("two"));
    }

    public Future<HttpResponse<Buffer>> query() {
        return client.get("/two").send();
    }
}
