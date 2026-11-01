package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/** One router built by a helper and mounted at two prefixes: its routes serve under both. */
public class MountedTwice {

    Router v(Vertx vertx) {
        Router versioned = Router.router(vertx);
        versioned.get("/ping").handler(this::ping);
        return versioned;
    }

    public void mount(Vertx vertx, Router root) {
        Router shared = v(vertx);
        root.route("/v1/*").subRouter(shared);
        root.route("/v2/*").subRouter(shared);
    }

    private void ping(RoutingContext ctx) {
        ctx.response().end("pong");
    }
}
