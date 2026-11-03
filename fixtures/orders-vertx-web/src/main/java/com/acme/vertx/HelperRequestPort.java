package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpRequest;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;

/**
 * A request's port set by a helper from its caller's argument (item 2 review, C2 and m4): the
 * step inside the helper reads the helper's parameter, so each caller's request carries that
 * caller's port and no other's.
 */
public class HelperRequestPort {

    private final WebClient client;

    public HelperRequestPort(Vertx vertx) {
        this.client = WebClient.create(vertx);
    }

    public Future<HttpResponse<Buffer>> first() {
        HttpRequest<Buffer> request = client.get("fw", "/fw1");
        port(request, 61);
        return request.send();
    }

    public Future<HttpResponse<Buffer>> second() {
        HttpRequest<Buffer> request = client.get("fw", "/fw2");
        port(request, 62);
        return request.send();
    }

    private static void port(HttpRequest<Buffer> request, int port) {
        request.port(port);
    }
}
