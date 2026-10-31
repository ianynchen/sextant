package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;

/**
 * Hono's shape (spec 2026-10-30 §3c): the router is built in a base class and kept in a
 * field, handed to the subclass's `addRoutes(router)`, and mounted by a third method. The
 * subclass's routes serve under the mount's prefix.
 */
public abstract class MountingVerticle {

    protected Router router;

    void build(Vertx vertx) {
        router = Router.router(vertx);
    }

    protected abstract void addRoutes(Router router);

    public void start(Vertx vertx, Router root) {
        build(vertx);
        addRoutes(router);
        mount(root);
    }

    void mount(Router root) {
        root.route("/hono/*").subRouter(router);
    }
}
