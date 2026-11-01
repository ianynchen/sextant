package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Handler;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * Anonymous classes on a route (spec 2026-10-30 §3b): one IS the handler, so Vert.x calls its
 * `handle`; another is a callback inside a handler that captured the context and calls
 * `next()` on it, which javac compiles to a synthetic field set by the class's constructor.
 */
public class AnonymousRoutes {

    public void register(Router router) {
        router.get("/anon").handler(new Handler<RoutingContext>() {
            @Override
            public void handle(RoutingContext ctx) {
                ctx.response().end("anon");
            }
        });

        router.get("/anon-next").handler(this::viaAnonymous).handler(this::after);
    }

    private void viaAnonymous(RoutingContext ctx) {
        Future.succeededFuture("user").onSuccess(new Handler<String>() {
            @Override
            public void handle(String user) {
                ctx.next();
            }
        });
    }

    private void after(RoutingContext ctx) {
        ctx.response().end("after");
    }
}
