package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * A client whose port is set on one branch only (spec 2026-11-02-per-path-truth rule 9,
 * review 2's M4): a run with {@code tls} sends to port 443, a run without it to the default.
 */
public class BranchedSearchClient {

    private final WebClient client;

    public BranchedSearchClient(Vertx vertx, boolean tls) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("branched");
        if (tls) {
            options.setDefaultPort(443);
        }
        this.client = WebClient.create(vertx, options);
    }

    public Future<HttpResponse<Buffer>> query() {
        return client.get("/b").send();
    }
}
