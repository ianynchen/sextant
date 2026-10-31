package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * A helper that builds and mounts a router per call, called twice. Each router's routes
 * belong under its own prefix only, never the other's (OI-222's mixing).
 */
public class PerCallSubRouters {

    private Router createSubRouter(Router root, Vertx vertx, String mountPoint) {
        Router sub = Router.router(vertx);
        root.route("/" + mountPoint + "*").subRouter(sub);
        return sub;
    }

    public void register(Router root, Vertx vertx) {
        Router users = createSubRouter(root, vertx, "users");
        users.get("/:userUuid").handler(this::user);

        Router groups = createSubRouter(root, vertx, "groups");
        groups.get("/:groupUuid/members").handler(this::members);
    }

    private void user(RoutingContext ctx) {
        ctx.response().end("user");
    }

    private void members(RoutingContext ctx) {
        ctx.response().end("members");
    }
}
