package com.acme.vertx.base;

import io.vertx.ext.web.RoutingContext;

/** Hono's `HttpUtils.nextRoute`: the body that passes the request on lives in this jar. */
public final class HttpUtils {

    private HttpUtils() {
    }

    public static void nextRoute(RoutingContext ctx) {
        ctx.next();
    }
}
