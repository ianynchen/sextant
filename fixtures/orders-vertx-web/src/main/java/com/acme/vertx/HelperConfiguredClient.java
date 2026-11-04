package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * A helper sets the default port its caller hands it (review of item 1, concern 6): the
 * setter's argument is the helper's parameter, so each caller's options carry that caller's
 * port and no other's.
 */
public class HelperConfiguredClient {

    public Future<HttpResponse<Buffer>> first(Vertx vertx) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("helper");
        port(options, 1001);
        return WebClient.create(vertx, options).get("/first").send();
    }

    public Future<HttpResponse<Buffer>> second(Vertx vertx) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("helper");
        port(options, 1002);
        return WebClient.create(vertx, options).get("/second").send();
    }

    private static void port(WebClientOptions options, int port) {
        options.setDefaultPort(port);
    }
}
