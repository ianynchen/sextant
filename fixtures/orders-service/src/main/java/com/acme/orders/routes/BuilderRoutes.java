// The builder form of WebFlux functional routing (G-37, spec §1): the form Spring's own
// reference recommends, and the one that derived NOTHING until the combinator engine
// could root a walk at `build()` and extend a verb's receiver. Every shape spec §8
// names: all four verb overloads, `path` with a builder body, a filter MID-chain, a
// static resource, `build()`, and a catch-all in a chain of its own.
package com.acme.orders.routes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class BuilderRoutes {

    @Bean
    public RouterFunction<ServerResponse> builderRoutes(RouteHandlers h) {
        return RouterFunctions.route()
            .GET("/bld/orders", h::listOrders)                                            // GET(String, HandlerFunction)
            .GET("/bld/orders/{id}", RequestPredicates.accept(MediaType.APPLICATION_JSON),
                 h::listOrders)                                                           // GET(String, RequestPredicate, HandlerFunction)
            .GET(RequestPredicates.path("/bld/health"), h::health)                        // GET(RequestPredicate, HandlerFunction)
            .filter((request, next) -> next.handle(request))                              // mid-chain pass-through
            .POST("/bld/orders", h::createOrder)
            .PUT("/bld/orders/{id}", h::createOrder)
            .path("/bld/nested", builder -> builder
                .GET("/inner", h::health)                                                 // GET inside a Consumer<Builder> body
                .DELETE("/inner/{id}", h::health))
            .resources("/bld/static/**", new ClassPathResource("static/"))                // served, handler-less (spec §6)
            .build();
    }

    @Bean
    public RouterFunction<ServerResponse> catchAll(RouteHandlers h) {
        return RouterFunctions.route().GET(h::health).build();                            // GET(HandlerFunction): a catch-all
    }
}
