package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Handler;
import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * vertx-examples' `sqlclient` server, shape for shape (OI-266): three handler locals captured
 * by an INSTANCE lambda — one that reads `this.vertx` — which registers them. javac hands the
 * lambda `this` ahead of the three captures, so each row must name its own handler, never its
 * neighbour's.
 */
public class CapturedRoutes {

    private Vertx vertx;

    public Future<?> start() {
        Handler<RoutingContext> getProductRoute = CapturedRoutes.this::handleGetProduct;
        Handler<RoutingContext> addProductRoute = CapturedRoutes.this::handleAddProduct;
        Handler<RoutingContext> listProductsRoute = CapturedRoutes.this::handleListProducts;

        return Future.succeededFuture().compose(v -> {
            Router router = Router.router(vertx);
            router.get("/products/:productID").handler(getProductRoute);
            router.post("/products").handler(addProductRoute);
            router.get("/products").handler(listProductsRoute);
            return vertx.createHttpServer().requestHandler(router).listen(8080);
        });
    }

    private void handleGetProduct(RoutingContext ctx) {
        ctx.response().end("{}");
    }

    private void handleAddProduct(RoutingContext ctx) {
        ctx.response().end("{}");
    }

    private void handleListProducts(RoutingContext ctx) {
        ctx.response().end("[]");
    }
}
