package com.acme.qk;

import io.quarkus.vertx.web.Body;
import io.quarkus.vertx.web.Header;
import io.quarkus.vertx.web.Param;
import io.quarkus.vertx.web.Route;
import io.quarkus.vertx.web.Route.HttpMethod;
import io.quarkus.vertx.web.RouteBase;

/**
 * Quarkus reactive routes the way the Quarkus guide writes them: `@RouteBase` prefixes
 * the class, each `@Route` names its path and verb(s). No CDI scope annotation — Quarkus
 * makes any class with a `@Route` method a singleton bean, so there is nothing else to
 * gate on.
 *
 * Measured at quarkus-reactive-routes 3.17.5 (`javap`): `@Route` declares `path`,
 * `regex`, `methods` (an `HttpMethod[]`), `type`, `order`, `produces`, `consumes`;
 * `@RouteBase` declares `path`, `produces`, `consumes`; `@Route.Routes` is the
 * `@Repeatable` container.
 */
@RouteBase(path = "/qk/orders", produces = "application/json")
public class OrderRoutes {

    @Route(path = "/", methods = HttpMethod.GET)
    public String list() {
        return "[]";
    }

    // `id` names the path segment — Vert.x serves it through the same `getParam` — and
    // gets no row; `verbose` is the query parameter beside it (spec 2026-09-19 §5b,
    // `skip_path_variables`).
    @Route(path = "/:id", methods = HttpMethod.GET)
    public String find(@Param String id, @Param String verbose) {
        return "{}";
    }

    @Route(path = "/", methods = HttpMethod.POST, consumes = "application/json")
    public String place(@Body String order) {
        return order;
    }

    // Two verbs on one handler, the array form; and two routes on one handler, the
    // repeatable form — both are ordinary in the guide.
    @Route(path = "/:id", methods = {HttpMethod.PUT, HttpMethod.DELETE})
    public String update(@Param String id, @Body String order) {
        return order;
    }

    @Route(path = "/:id/cancel", methods = HttpMethod.POST)
    @Route(path = "/:id/void", methods = HttpMethod.POST)
    public String cancel(@Param String id) {
        return "{}";
    }

    // Spec 2026-09-19 §5b: a `@Param` that IS a query parameter (the ones above name path
    // segments, which Vert.x also serves through `getParam`) and a `@Header`. The generated
    // read is `HttpServerRequest.getParam`/`getHeader`, `@Nullable` returns — absent → null,
    // never a 400 (CP-25 rows 11–12): both `optional`.
    @Route(path = "/search", methods = HttpMethod.GET)
    public String search(@Param String q, @Header("X-Tenant") String tenant) {
        return "[]";
    }
}
