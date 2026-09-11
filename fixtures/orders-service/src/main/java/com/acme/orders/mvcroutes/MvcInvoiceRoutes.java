// Spring MVC functional routing (W44, `G-29`). The same DSL the reactive
// `routes/OrderRoutes` uses, one package along: a nested prefix, one `accept`
// and one `contentType` predicate, a method-ref handler, and a `PUT` — the verb
// whose absence from the reactive catalog was `A-M9`, pinned here so the
// servlet twin cannot ship the same fixture-shaped verb list.
package com.acme.orders.mvcroutes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RequestPredicates;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration
public class MvcInvoiceRoutes {

    @Bean
    public RouterFunction<ServerResponse> invoiceRoutes(MvcRouteHandlers h) {
        return RouterFunctions.nest(RequestPredicates.path("/mvcfn"),
            RouterFunctions.route(RequestPredicates.GET("/invoices")
                    .and(RequestPredicates.accept(MediaType.APPLICATION_JSON)), h::listInvoices)
                .andRoute(RequestPredicates.POST("/invoices")
                    .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)),
                    h::createInvoice)
                .andRoute(RequestPredicates.PUT("/invoices/{id}"), h::archive));
    }
}
