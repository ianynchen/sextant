package com.acme.jv;

import io.javalin.Javalin;
import io.javalin.apibuilder.ApiBuilder;
import io.javalin.security.RouteRole;

public class OrderApp {
    public Javalin flat() {
        Javalin app = Javalin.create();
        app.get("/jv/orders", ctx -> ctx.result("[]"));
        app.get("/jv/orders/{id}", ctx -> ctx.result("{}"));
        app.post("/jv/orders", ctx -> ctx.status(201));
        app.delete("/jv/orders/{id}", ctx -> ctx.status(204));
        return app;
    }

    /** A role for the role-carrying verb overload below; `RouteRole` is a marker interface,
     *  and an enum is how Javalin's own documentation implements it. */
    enum Role implements RouteRole { ADMIN }

    /** The nested form (`javalin-apibuilder`, spec §14): two nesting levels, a path-less verb,
     *  and the role-carrying overload. Javalin's own rule, read off `ApiBuilder.prefixPath` in
     *  the 6.4.0 jar: every verb registers `join("", pathDeque) + path`, and `post(handler)`
     *  is `post(prefixPath(""), handler)` — so a path-less verb serves exactly the prefix it
     *  sits under. `post(ctx -> …)` here registers `POST /jv/nested`, not `/jv/nested/**`,
     *  and the inner `get(ctx -> …)` registers `GET /jv/nested/{id}/items`. The same
     *  `prefixPath` puts a `/` in front of a segment written without one, so the slashless
     *  `path("plain", …)` over `get("x", …)` registers `GET /jv/nested/plain/x` — Javalin's
     *  documentation calls `path("api", …)` and `path("/api", …)` the same registration. */
    public Javalin nested() {
        return Javalin.create(config -> config.router.apiBuilder(() -> {
            ApiBuilder.path("/jv/nested", () -> {
                ApiBuilder.get("/{id}", ctx -> ctx.result("{}"));
                ApiBuilder.post(ctx -> ctx.status(201));                     // post(Handler): no path of its own
                ApiBuilder.path("/{id}/items", () -> {
                    ApiBuilder.get(ctx -> ctx.result("[]"));                 // get(Handler): both prefixes, nothing more
                    ApiBuilder.delete("/{itemId}", ctx -> ctx.status(204), Role.ADMIN);
                });
                ApiBuilder.path("plain", () -> {                             // slashless: Javalin joins it as /plain
                    ApiBuilder.get("x", ctx -> ctx.result("plain"));
                });
                // HANDLER-BODY READS (`request_reads`, spec 2026-09-19 §5d; CP-25 rows 14–15).
                // `queryParam("q")` and `header("X-Api")` are one-argument READS: query and
                // header rows, `requirement` NULL — Javalin hands a null through and the
                // handler decides (A3). `queryParamAsClass("n", Integer.class).get()` is the
                // one read Javalin itself refuses a request over: `Validator.get()` throws
                // `ValidationException` on an absent value → `required`, through the
                // catalog's `then: { method: get }`; the same chain ended in `getOrDefault`
                // (`X-Page`) stays NULL. `header("X-Set", "1")` is the two-argument SET on
                // the response (F7) — no entry at that arity, no row. This handler is an
                // `ApiBuilder` one on purpose: a `combinator` row's `handler` is the lambda
                // body itself, where a flat `app.get(...)` row's `handler` is the registering
                // method and the lambda's reads are out of its body (stated in COVERAGE).
                ApiBuilder.get("/reads", ctx -> {
                    String q = ctx.queryParam("q");
                    int n = ctx.queryParamAsClass("n", Integer.class).get();
                    int page = ctx.headerAsClass("X-Page", Integer.class).getOrDefault(1);
                    String api = ctx.header("X-Api");
                    ctx.header("X-Set", "1");
                    ctx.result(q + n + page + api);
                });
            });
            ApiBuilder.path("/jv/helped", () -> helped());                       // a static helper CALLED from the block
        }));
    }

    /** A static helper called from inside an `EndpointGroup` block (spec 2026-09-19 §4a,
     *  `follow_calls: all` on `javalin-apibuilder`): `ApiBuilder`'s verbs register on a
     *  thread-local instance that `staticInstance()` refuses outside a block
     *  (`IllegalStateException`, measured on the 6.4.0 jar), so a helper reaching `get` can
     *  only have been called from inside one, and the walk follows the CALL with no origin to
     *  check — `GET /jv/helped/h`, under the prefix that reached the call. A method REFERENCE
     *  (`path("/x", OrderApp::helped)`) would be a linked body already; the call is the shape
     *  the word exists for. */
    static void helped() {
        ApiBuilder.get("/h", ctx -> ctx.result("h"));
    }

    /** The SECOND flat form — `RouterConfig.mount`, the same descriptors as {@link #flat()}
     * on a different implementing type ({@code JavalinDefaultRouting}), no nesting. */
    public Javalin mounted() {
        return Javalin.create(config -> config.router.mount(router -> {
            router.get("/jv/mounted", ctx -> ctx.result("[]"));
            router.post("/jv/mounted", ctx -> ctx.status(201));
        }));
    }
}
