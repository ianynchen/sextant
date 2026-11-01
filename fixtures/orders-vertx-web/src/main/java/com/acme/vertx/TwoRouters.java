package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * Vert.x orders routes within one router (OI-263): one verb and path on two routers is two
 * answering routes, each its router's own. The same path given two handlers on ONE router,
 * from two methods, is in no order the code states.
 */
public class TwoRouters {

    public void start(Vertx vertx) {
        Router admin = Router.router(vertx);
        Router api = Router.router(vertx);
        admin.get("/ping").handler(this::adminPing);
        api.get("/ping").handler(this::apiPing);

        Router shared = Router.router(vertx);
        first(shared);
        second(shared);
    }

    private void first(Router router) {
        router.get("/same-router").handler(this::firstShared);
    }

    private void second(Router router) {
        router.get("/same-router").handler(this::secondShared);
    }

    private void adminPing(RoutingContext ctx) {
        ctx.response().end("admin");
    }

    private void apiPing(RoutingContext ctx) {
        ctx.response().end("api");
    }

    private void firstShared(RoutingContext ctx) {
        ctx.response().end("first");
    }

    private void secondShared(RoutingContext ctx) {
        ctx.response().end("second");
    }
}
