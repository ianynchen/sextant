package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;

/**
 * A url handed to a helper as its parameter, by callers that do not all hand a literal
 * (final review I2). Every caller's value is part of the set: each literal is a call of its
 * own, and the value nobody reads is a call whose path is unread. The client is a field, so
 * nothing ties the helper to one caller.
 */
public class ParameterUrls {

    private final WebClient client;

    public ParameterUrls(Vertx vertx) {
        this.client = WebClient.create(vertx);
    }

    public Future<HttpResponse<Buffer>> known() {
        return call("/param-known");
    }

    public Future<HttpResponse<Buffer>> other() {
        return call("/param-other");
    }

    public Future<HttpResponse<Buffer>> computed() {
        return call(System.getenv("PARAM_URL"));
    }

    private Future<HttpResponse<Buffer>> call(String url) {
        return client.get(url).send();
    }

    /** One literal caller and one unread: the literal alone is not the whole answer. */
    public Future<HttpResponse<Buffer>> lone() {
        return single("/param-lone");
    }

    public Future<HttpResponse<Buffer>> loneComputed() {
        return single(System.getenv("PARAM_LONE"));
    }

    private Future<HttpResponse<Buffer>> single(String url) {
        return client.delete(url).send();
    }
}
