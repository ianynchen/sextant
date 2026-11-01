package com.acme.vertx;

import io.vertx.core.Handler;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;
import io.vertx.ext.web.handler.BodyHandler;
import io.vertx.ext.web.handler.CorsHandler;

/**
 * Hono's shapes of a framework handler the producer walk cannot pin to one call (spec
 * 2026-10-30 §3b): a handler configured after it is built, handed in as a `Handler`
 * parameter, returned by a factory, or held in a field set from a constructor nothing here
 * calls. Each is identified by its declared static type.
 */
public class StaticTypeRoutes {

    private final CorsHandler cors;

    public StaticTypeRoutes(CorsHandler cors) {
        this.cors = cors;
    }

    public void start(Router router) {
        BodyHandler body = BodyHandler.create();
        body.setBodyLimit(1024);
        addRoutes(router, body);
    }

    private void addRoutes(Router router, Handler<RoutingContext> auth) {
        router.post("/typed").handler(auth).handler(bodyHandler());
        router.post("/typed").handler(this::accept);
        router.get("/typed-field").handler(cors).handler(this::accept);
    }

    private BodyHandler bodyHandler() {
        BodyHandler handler = BodyHandler.create();
        handler.setBodyLimit(1);
        return handler;
    }

    private void accept(RoutingContext ctx) {
        ctx.response().end("accepted");
    }
}
