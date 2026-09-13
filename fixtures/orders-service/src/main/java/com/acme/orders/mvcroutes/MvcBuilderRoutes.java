// The servlet twin of `routes/BuilderRoutes` (G-37, spec §1): the same builder form one
// package along, `org.springframework.web.servlet.function`, with the same shapes spec
// §8 names — all four verb overloads, `path` with a builder body, a filter MID-chain, a
// static resource, `build()`, and a catch-all in a chain of its own — so the MVC
// catalog cannot ship a builder surface its reactive twin has and it lacks.
package com.acme.orders.mvcroutes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RequestPredicates;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration
public class MvcBuilderRoutes {

    @Bean
    public RouterFunction<ServerResponse> mvcBuilderRoutes(MvcRouteHandlers h) {
        return RouterFunctions.route()
            .GET("/mvcbld/orders", h::listInvoices)                                       // GET(String, HandlerFunction)
            .GET("/mvcbld/orders/{id}", RequestPredicates.accept(MediaType.APPLICATION_JSON),
                 h::listInvoices)                                                         // GET(String, RequestPredicate, HandlerFunction)
            .GET(RequestPredicates.path("/mvcbld/health"), h::archive)                    // GET(RequestPredicate, HandlerFunction)
            .filter((request, next) -> next.handle(request))                              // mid-chain pass-through
            .POST("/mvcbld/orders", h::createInvoice)
            .PUT("/mvcbld/orders/{id}", h::createInvoice)
            .path("/mvcbld/nested", builder -> builder
                .GET("/inner", h::archive)                                                // GET inside a Consumer<Builder> body
                .DELETE("/inner/{id}", h::archive))
            .resources("/mvcbld/static/**", new ClassPathResource("static/"))             // served, handler-less (spec §6)
            .build();
    }

    @Bean
    public RouterFunction<ServerResponse> mvcCatchAll(MvcRouteHandlers h) {
        return RouterFunctions.route().GET(h::archive).build();                           // GET(HandlerFunction): a catch-all
    }
}
