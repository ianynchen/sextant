package com.acme.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RequestPredicates;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

/**
 * A functional route in the module whose configuration sets a context path and a servlet path:
 * served at `/shop/api/versioned`, and only to a request carrying `X-Ver=2`.
 *
 * <p>The requirement is a `param` predicate because that is the one Spring MVC's functional
 * routing can name: `RequestPredicates` in spring-webmvc 7.0.9 has no header-by-name predicate,
 * only `headers(Predicate)`, which the catalog does not read. What the route exists for is the
 * ORDER of two passes: the requirement is recorded against the route as minted (`/versioned`),
 * and the prefix moves the route to `/shop/api/versioned` before the requirement is joined to
 * it. Joined by path, the requirement was lost.
 */
@Configuration
public class RouterConfig {

    @Bean
    public RouterFunction<ServerResponse> versioned() {
        return RouterFunctions.route(
            RequestPredicates.GET("/versioned").and(RequestPredicates.param("X-Ver", "2")),
            request -> ServerResponse.ok().build());
    }
}
