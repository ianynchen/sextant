package com.acme.vertx;

import com.acme.vertx.base.BaseRoutes;
import com.acme.vertx.base.HttpUtils;
import io.vertx.core.Future;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;
import io.vertx.ext.web.handler.BodyHandler;

/**
 * Which handler answers on a route (spec 2026-10-30 §3b): handlers that call `next()` pass
 * the request on, and the route's row names the first one that does not. Extends the base
 * jar's `BaseRoutes`, whose factories are inherited and whose bodies this module cannot read.
 */
public class PassThroughRoutes extends BaseRoutes {

    static final String EVENTS = "/events";

    interface Authenticator {
        Future<String> authenticate(RoutingContext ctx);
    }

    private final Authenticator authenticator = ctx -> Future.succeededFuture("user");

    // Hono's pair, registered in one method: the middleware chain gives no row.
    public void sameMethod(Router router) {
        router.post(EVENTS).handler(this::authenticate).handler(BodyHandler.create());
        router.post(EVENTS).handler(this::ingest);
    }

    // The same pair split across two methods, both answering: the order is not in the code.
    public void firstMethod(Router router) {
        router.post("/telemetry").handler(this::acceptFirst);
    }

    public void secondMethod(Router router) {
        router.post("/telemetry").handler(this::acceptSecond);
    }

    public void register(Router router) {
        router.get("/two").handler(this::a).handler(this::b);

        router.route("/t/*").handler(this::assertTenant);

        String p = "/u/:id";
        router.put(p).handler(this::extractJson).handler(this::updateU);

        String p2 = "/u2/:id";
        router.put(p2).handler(this::check).handler(this::updateU2);

        router.get("/reply").handler(this::viaHelper);

        router.get("/lambda").handler(this::authenticated);

        router.route("/cors").handler(createCorsHandler("https://example.com"));
        router.route("/plain").handler(baseFactory());

        router.route().handler(BodyHandler.create());
    }

    private void authenticate(RoutingContext ctx) {
        ctx.next();
    }

    private void ingest(RoutingContext ctx) {
        ctx.response().end("ingested");
    }

    private void acceptFirst(RoutingContext ctx) {
        ctx.response().end("first");
    }

    private void acceptSecond(RoutingContext ctx) {
        ctx.response().end("second");
    }

    private void a(RoutingContext ctx) {
        ctx.response().end("a");
    }

    private void b(RoutingContext ctx) {
        ctx.response().end("b");
    }

    private void assertTenant(RoutingContext ctx) {
        ctx.next();
    }

    // Hands the context to an in-module helper that calls `next()`.
    private void extractJson(RoutingContext ctx) {
        passOn(ctx);
    }

    private void passOn(RoutingContext ctx) {
        ctx.next();
    }

    private void updateU(RoutingContext ctx) {
        ctx.response().end("updated");
    }

    // Hands the context to the base jar's helper: whether it passes on is not readable here.
    private void check(RoutingContext ctx) {
        HttpUtils.nextRoute(ctx);
    }

    private void updateU2(RoutingContext ctx) {
        ctx.response().end("updated");
    }

    // Hands the context to an in-module helper that replies.
    private void viaHelper(RoutingContext ctx) {
        replyTo(ctx);
    }

    private void replyTo(RoutingContext ctx) {
        ctx.response().end("replied");
    }

    // A `next()` inside a lambda that captured the context.
    private void authenticated(RoutingContext ctx) {
        authenticator.authenticate(ctx).onSuccess(u -> ctx.next());
    }
}
