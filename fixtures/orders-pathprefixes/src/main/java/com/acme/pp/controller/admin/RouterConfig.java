package com.acme.pp.controller.admin;

import static org.springframework.web.servlet.function.RequestPredicates.GET;

import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

/** **Served at `/fn/items`, with NO prefix, although this class sits in the `…controller.admin`
 * package that `/admin-api` names.**
 *
 * <p>`setPathPrefixes` is a field of `RequestMappingHandlerMapping` alone — `javap` on
 * spring-webmvc 7.0.9: `RouterFunctionMapping` has no `pathPrefixes` and no setter, and
 * `getPathPrefix` is called only from `RequestMappingHandlerMapping.getMappingForMethod`. A
 * functional route is therefore never prefixed, and the predicate's own annotation test is
 * what says so here: this class is not a `@RestController`, so the framework never asks the
 * predicate about it. Reading the package match alone published `/admin-api/fn/items`.
 */
public class RouterConfig {

    public RouterFunction<ServerResponse> items() {
        return RouterFunctions.route(GET("/fn/items"), request -> ServerResponse.ok().build());
    }
}
