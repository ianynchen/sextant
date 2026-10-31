package com.acme.vertx.base;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;

import java.util.List;

/** A router built in this jar and handed in, and the prefixes it is mounted under. */
public final class RouterSource {

    private RouterSource() {
    }

    public static Router provided(Vertx vertx) {
        return Router.router(vertx);
    }

    public static List<String> prefixes() {
        return List.of("/sigfox", "/lora");
    }
}
