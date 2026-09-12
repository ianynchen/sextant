package com.acme.jv;

import io.javalin.Javalin;
import io.javalin.apibuilder.ApiBuilder;

public class OrderApp {
    public Javalin flat() {
        Javalin app = Javalin.create();
        app.get("/jv/orders", ctx -> ctx.result("[]"));
        app.get("/jv/orders/{id}", ctx -> ctx.result("{}"));
        app.post("/jv/orders", ctx -> ctx.status(201));
        app.delete("/jv/orders/{id}", ctx -> ctx.status(204));
        return app;
    }

    /** The nested form — Category B (`javalin-apibuilder`); derives nothing until then. */
    public Javalin nested() {
        return Javalin.create(config -> config.router.apiBuilder(() -> {
            ApiBuilder.path("/jv/nested", () -> {
                ApiBuilder.get("/{id}", ctx -> ctx.result("{}"));
            });
        }));
    }
}
