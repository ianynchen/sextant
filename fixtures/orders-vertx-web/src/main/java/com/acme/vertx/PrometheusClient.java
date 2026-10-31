package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.buffer.Buffer;
import io.vertx.core.json.JsonObject;
import io.vertx.ext.web.client.HttpRequest;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.codec.BodyCodec;

/**
 * Hono's shape: a helper builds a request with self-returning calls in statement style and
 * returns it; its caller sends it.
 */
public class PrometheusClient {

    static final String QUERY = "http://prometheus:9090/api/v1/query";

    private final WebClient client;

    public PrometheusClient(WebClient client) {
        this.client = client;
    }

    private HttpRequest<JsonObject> request(String expression) {
        HttpRequest<Buffer> r = client.postAbs(QUERY).addQueryParam("query", expression);
        r.timeout(5000);
        r.basicAuthentication("user", "secret");
        return r.as(BodyCodec.jsonObject());
    }

    public Future<HttpResponse<JsonObject>> query(String expression) {
        return request(expression).send();
    }
}
