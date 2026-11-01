package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * Two routers made by one factory helper are two routers (final review I1): each call of
 * {@code make} runs {@code Router.router} again. The same verb and path on each is each
 * router's own answer. One router from the helper, given the path inside the helper and
 * again by its caller, is still one router.
 */
public class RouterFactory {

    private Vertx vertx;

    public void start(Vertx vertx) {
        this.vertx = vertx;
        Router a = make();
        Router b = make();
        a.get("/factory-ping").handler(this::aPing);
        b.get("/factory-ping").handler(this::bPing);

        Router c = makeWithRoute();
        c.get("/factory-same").handler(this::callerSame);
    }

    private Router make() {
        return Router.router(vertx);
    }

    private Router makeWithRoute() {
        Router router = Router.router(vertx);
        router.get("/factory-same").handler(this::helperSame);
        return router;
    }

    private void aPing(RoutingContext ctx) {
        ctx.response().end("a");
    }

    private void bPing(RoutingContext ctx) {
        ctx.response().end("b");
    }

    private void helperSame(RoutingContext ctx) {
        ctx.response().end("helper");
    }

    private void callerSame(RoutingContext ctx) {
        ctx.response().end("caller");
    }
}
