package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * Options kept in a field and configured through it (item 2 review, C1): the constructor sets
 * the host and port on {@code this.opts}, calls the walk does not read on the object it reaches,
 * and {@code init} may set the port again. Once in a field anything can change the object, so
 * no part of it is proven unset: Vert.x's default is not this client's.
 */
public class FieldOptionsClient {

    private final WebClientOptions opts;
    private final WebClientOptions held = new WebClientOptions().setDefaultHost("held");
    private WebClientOptions holder;

    public FieldOptionsClient() {
        opts = new WebClientOptions();
        opts.setDefaultHost("ctor");
        opts.setDefaultPort(9002);
    }

    public void init() {
        held.setDefaultPort(9001);
    }

    public Future<HttpResponse<Buffer>> viaConstructor(Vertx vertx) {
        return WebClient.create(vertx, opts).get("/field-ctor").send();
    }

    public Future<HttpResponse<Buffer>> viaField(Vertx vertx) {
        return WebClient.create(vertx, held).get("/field-held").send();
    }

    /** Stored from a local, a store the facts do not record, then configured through the field. */
    public Future<HttpResponse<Buffer>> viaHolder(Vertx vertx) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("hd");
        this.holder = options;
        this.holder.setDefaultPort(5);
        return WebClient.create(vertx, options).get("/field-holder").send();
    }
}
