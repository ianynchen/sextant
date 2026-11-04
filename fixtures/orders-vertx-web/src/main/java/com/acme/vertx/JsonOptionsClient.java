package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.core.json.JsonObject;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * Options built from a configuration object (rule 5): the constructor reads its port from the
 * JSON, which is not here, so the port is not Vert.x's default and who is called is unknown.
 */
public class JsonOptionsClient {

    private final WebClient client;

    public JsonOptionsClient(Vertx vertx, JsonObject config) {
        this.client = WebClient.create(vertx, new WebClientOptions(config).setDefaultHost("json"));
    }

    public Future<HttpResponse<Buffer>> query() {
        return client.get("/json").send();
    }
}
