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
 * A request's own options kept in a field and changed through it elsewhere (item 2 review, C1):
 * after {@code init} the request goes to {@code elsewhere}, so the client's default host is not
 * proven to be the one it takes.
 */
public class StoredRequestOptionsClient {

    private final RequestOptions options = new RequestOptions().setURI("/stored");

    public void init() {
        options.setHost("elsewhere");
    }

    public Future<HttpResponse<Buffer>> fetch(Vertx vertx) {
        WebClient client = WebClient.create(
            vertx, new WebClientOptions().setDefaultHost("sr").setDefaultPort(41));
        return client.request(HttpMethod.GET, options).send();
    }
}
