package com.acme.vertx;

import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/** The subclass that registers its routes on the router its base class built and mounts. */
public class TelemetryVerticle extends MountingVerticle {

    @Override
    protected void addRoutes(Router router) {
        router.post("/telemetry-in").handler(this::accept);
    }

    private void accept(RoutingContext ctx) {
        ctx.response().end();
    }
}
