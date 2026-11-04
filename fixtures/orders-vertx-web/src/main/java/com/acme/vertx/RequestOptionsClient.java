package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.core.http.HttpMethod;
import io.vertx.core.http.RequestOptions;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * A request's own options with its host set on one branch (rules 4 and 9): a run with
 * {@code direct} sends to {@code direct}, a run without it to the client's default host.
 */
public class RequestOptionsClient {

    private final WebClient client;

    public RequestOptionsClient(Vertx vertx) {
        this.client = WebClient.create(
            vertx, new WebClientOptions().setDefaultHost("ro-default").setDefaultPort(9200));
    }

    public Future<HttpResponse<Buffer>> fetch(boolean direct) {
        RequestOptions options = new RequestOptions().setURI("/ro");
        if (direct) {
            options.setHost("direct");
        }
        return client.request(HttpMethod.GET, options).send();
    }
}
