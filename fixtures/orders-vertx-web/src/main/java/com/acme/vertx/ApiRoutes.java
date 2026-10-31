package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;
import io.vertx.ext.web.impl.RouterImpl;

import com.acme.vertx.base.RouterSource;

/** Sub-routers mounted by object identity (spec 2026-10-30 §3c). */
public class ApiRoutes {

    // Built here, mounted below.
    static Router build(Vertx vertx) {
        Router api = Router.router(vertx);
        api.get("/status").handler(ApiRoutes::status);
        return api;
    }

    public void mount(Vertx vertx, Router root) {
        Router api = build(vertx);
        root.route("/api/*").subRouter(api);

        Router impl = new RouterImpl(vertx);
        impl.get("/impl").handler(ApiRoutes::status);
        root.route("/m/*").subRouter(impl);
    }

    // The prefixes come from the base jar, so the mount found has a prefix nothing here reads.
    public void mountEach(Vertx vertx, Router root) {
        Router edge = Router.router(vertx);
        edge.get("/edge").handler(ApiRoutes::status);
        RouterSource.prefixes().forEach(p -> root.route(p + "*").subRouter(edge));
    }

    // A router handed in from the base jar and given routes here is served at its root.
    public void provided(Vertx vertx) {
        Router handedIn = RouterSource.provided(vertx);
        handedIn.get("/provided").handler(ApiRoutes::status);
    }

    private static void status(RoutingContext ctx) {
        ctx.response().end("ok");
    }
}
