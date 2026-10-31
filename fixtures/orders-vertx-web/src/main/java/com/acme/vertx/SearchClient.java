package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * A client configured by an options object handed to its factory: the request names only
 * a path, and the host and port are on the options.
 */
public class SearchClient {

    private final WebClient client;

    public SearchClient(Vertx vertx) {
        this.client = WebClient.create(
            vertx, new WebClientOptions().setDefaultHost("search").setDefaultPort(9200));
    }

    public Future<HttpResponse<Buffer>> query() {
        return client.get("/q").send();
    }
}
