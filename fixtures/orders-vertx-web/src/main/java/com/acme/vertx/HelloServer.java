package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;

/** The official hello world: a server whose only route is `router.route().handler(…)`. */
public class HelloServer {

    public void start(Vertx vertx) {
        Router router = Router.router(vertx);
        router.route().handler(rc -> rc.response().end("hi"));
        vertx.createHttpServer().requestHandler(router).listen(8080);
    }
}
