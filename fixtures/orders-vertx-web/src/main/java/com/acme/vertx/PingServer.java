package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/** A server of its own with its own router: vertx-examples' shape, one router per example. */
public class PingServer {

    public void start(Vertx vertx) {
        Router router = Router.router(vertx);
        router.get("/ping").handler(PingServer::ping);
        vertx.createHttpServer().requestHandler(router).listen(8082);
    }

    private static void ping(RoutingContext ctx) {
        ctx.response().end("pong");
    }
}
