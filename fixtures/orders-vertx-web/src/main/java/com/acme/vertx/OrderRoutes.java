package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.http.HttpMethod;
import io.vertx.ext.web.Route;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * The single-handler shapes of Vert.x Web (spec 2026-10-30 §3f): one route, one handler
 * that answers. Each shape sits on its own path, so one expected row names one shape.
 */
public class OrderRoutes {

    static final String ITEMS = "/items";
    static final String P = "id";

    public void register(Router router) {
        router.get("/orders").handler(this::list);
        router.post("/orders").handler(this::create);

        router.route(HttpMethod.PUT, "/orders/:id").handler(this::update);

        router.route("/orders/:id").method(HttpMethod.GET).method(HttpMethod.DELETE).handler(this::find);

        // The same route as separate statements on a `Route` local, with a self-returning
        // call between each pair: one chain, not four.
        Route r = router.route("/statement/:id");
        r.method(HttpMethod.GET);
        r.failureHandler(this::failed);
        r.setName("statement");
        r.method(HttpMethod.DELETE);
        r.handler(this::statement);

        router.route("/any").handler(this::any);

        router.get("/health").respond(ctx -> Future.succeededFuture("up"));

        router.get("/gone").handler(this::gone).disable();

        router.get("bad").handler(this::bad);

        router.getWithRegex("\\/files\\/.+").handler(this::file);

        router.get("/v").virtualHost("api.example.com").handler(this::virtualHost);

        router.get(ITEMS).handler(this::items);
        router.get(String.format("/a/:%s", P)).handler(this::formatted);

        router.get("/search").handler(this::search);
    }

    private void list(RoutingContext ctx) {
        ctx.response().end("[]");
    }

    private void create(RoutingContext ctx) {
        ctx.response().end("{}");
    }

    private void update(RoutingContext ctx) {
        ctx.response().end("{}");
    }

    private void find(RoutingContext ctx) {
        ctx.response().end("{}");
    }

    private void statement(RoutingContext ctx) {
        ctx.response().end("{}");
    }

    private void failed(RoutingContext ctx) {
        ctx.response().setStatusCode(500).end();
    }

    private void any(RoutingContext ctx) {
        ctx.response().end("any");
    }

    private void gone(RoutingContext ctx) {
        ctx.response().end("gone");
    }

    private void bad(RoutingContext ctx) {
        ctx.response().end("bad");
    }

    private void file(RoutingContext ctx) {
        ctx.response().end("file");
    }

    private void virtualHost(RoutingContext ctx) {
        ctx.response().end("v");
    }

    private void items(RoutingContext ctx) {
        ctx.response().end("items");
    }

    private void formatted(RoutingContext ctx) {
        ctx.response().end("formatted");
    }

    // The handler reads a query parameter and a header: both reach the route's row.
    private void search(RoutingContext ctx) {
        String q = ctx.queryParam("q").get(0);
        String tenant = ctx.request().getHeader("X-T");
        ctx.response().end(q + tenant);
    }
}
