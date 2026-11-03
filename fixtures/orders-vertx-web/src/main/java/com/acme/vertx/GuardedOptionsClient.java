package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * Options configured on several branches (spec 2026-11-02-per-path-truth rule 9, the
 * several-splits rule as narrowed to published parts on 2026-11-03). The facts say a call is
 * on a branch, never which branch, so two guarded calls that each set an address part give
 * combinations no run may make, and every row is {@code partial}. A guarded call that sets no
 * address part ({@code setSsl}) is no split for those rows.
 */
public class GuardedOptionsClient {

    public Future<HttpResponse<Buffer>> twoParts(Vertx vertx, boolean a, boolean b) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("g");
        if (a) {
            options.setDefaultPort(1);
        }
        if (b) {
            options.setDefaultHost("h");
        }
        return WebClient.create(vertx, options).get("/two-parts").send();
    }

    public Future<HttpResponse<Buffer>> sslAndPort(Vertx vertx, boolean a, boolean b) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("s");
        if (a) {
            options.setSsl(true);
        }
        if (b) {
            options.setDefaultPort(443);
        }
        return WebClient.create(vertx, options).get("/ssl-and-port").send();
    }

    /** Nine guarded ports are 512 paths, past the cap: one row, its peer not known. */
    public Future<HttpResponse<Buffer>> capped(Vertx vertx, boolean[] f) {
        WebClientOptions options = new WebClientOptions().setDefaultHost("c");
        if (f[0]) { options.setDefaultPort(1); }
        if (f[1]) { options.setDefaultPort(2); }
        if (f[2]) { options.setDefaultPort(3); }
        if (f[3]) { options.setDefaultPort(4); }
        if (f[4]) { options.setDefaultPort(5); }
        if (f[5]) { options.setDefaultPort(6); }
        if (f[6]) { options.setDefaultPort(7); }
        if (f[7]) { options.setDefaultPort(8); }
        if (f[8]) { options.setDefaultPort(9); }
        return WebClient.create(vertx, options).get("/capped").send();
    }
}
