// The Java functional-routing surface: a nested prefix, an `or`'d verb, one
// `accept` and one `contentType` predicate, a method-ref handler and a
// lambda handler, and a cross-method composition -- `other()`'s
// RouterFunction crossing into `composite` below is the honest-unresolved
// case the walk must not silently attribute to one method.
package com.acme.orders.routes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class OrderRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes(RouteHandlers h) {
        return RouterFunctions.nest(RequestPredicates.path("/fn"),
            RouterFunctions.route(RequestPredicates.GET("/orders")
                    .and(RequestPredicates.accept(MediaType.APPLICATION_JSON)), h::listOrders)
                .andRoute(RequestPredicates.POST("/orders")
                    .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)), h::createOrder)
                .andRoute(RequestPredicates.GET("/health").or(RequestPredicates.HEAD("/health")),
                    request -> ServerResponse.ok().build()));
    }

    @Bean
    public RouterFunction<ServerResponse> composite(RouteHandlers h) {
        return RouterFunctions.route(RequestPredicates.GET("/extra"), h::health).and(other());
    }

    private RouterFunction<ServerResponse> other() {
        return RouterFunctions.route(RequestPredicates.GET("/other"),
            request -> ServerResponse.ok().build());
    }
}
