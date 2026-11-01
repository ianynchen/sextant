package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Handler;
import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * A route path handed in rather than written at the route (OI-265): held in a local that a
 * lambda captures, or passed to a helper as its parameter. Either way the path is a literal
 * this module states, reached over one value edge.
 */
public class CapturedPaths {

    public Future<?> start(Vertx vertx) {
        String reportsPath = "/reports";
        Handler<RoutingContext> reports = CapturedPaths::reports;
        Router helped = Router.router(vertx);
        register(helped, "/audits", CapturedPaths::audits);
        return Future.succeededFuture().compose(v -> {
            Router router = Router.router(vertx);
            router.get(reportsPath).handler(reports);
            return vertx.createHttpServer().requestHandler(router).listen(8081);
        });
    }

    private static void register(Router router, String path, Handler<RoutingContext> handler) {
        router.get(path).handler(handler);
    }

    private static void reports(RoutingContext ctx) {
        ctx.response().end("[]");
    }

    private static void audits(RoutingContext ctx) {
        ctx.response().end("[]");
    }
}
