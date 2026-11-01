package com.acme.vertx.base;

import io.vertx.core.Handler;
import io.vertx.ext.web.RoutingContext;

/** A handler that is not one of the framework's own. */
public class PlainHandler implements Handler<RoutingContext> {

    @Override
    public void handle(RoutingContext ctx) {
        ctx.response().end("base");
    }
}
