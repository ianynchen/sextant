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
            });
        }));
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
