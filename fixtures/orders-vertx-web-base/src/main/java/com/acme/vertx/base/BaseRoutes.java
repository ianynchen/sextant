package com.acme.vertx.base;

import io.vertx.core.Handler;
import io.vertx.ext.web.RoutingContext;
import io.vertx.ext.web.handler.CorsHandler;

/** Hono's inherited handler factories: the subclass calls them, their bodies are here. */
public abstract class BaseRoutes {

    protected CorsHandler createCorsHandler(String origin) {
        return CorsHandler.create().addOrigin(origin);
    }

    protected Handler<RoutingContext> baseFactory() {
        return new PlainHandler();
    }
}
