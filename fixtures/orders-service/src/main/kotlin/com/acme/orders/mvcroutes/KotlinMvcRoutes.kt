// The servlet-stack Kotlin router DSL, every `GET` overload it declares in one file
// (W44-verb-overloads, spec §1b): the shipped rules read one of five and mis-graded the
// rest. Paths under /ktmvc so the reactive twin's rows cannot be mistaken for these.
// The `accept(JSON) { … }` line is the DSL's route-declaring media overload, which the
// catalog has no word for yet (`dsl-media-route`): it derives one unresolved row, never
// silence, and the live test pins that row as the tracked gap.
//
// Handlers are lambdas delegating to the handler bean rather than `h::listInvoices`
// references, and that is measured, not stylistic: Kotlin 2.2.0 compiles a bound
// callable reference handed as a `Function1` into a class of its own
// (`KotlinMvcRoutes$ktMvcRoutes$1$1$1` and so on), which the walk reads as an
// `instance` of a generated type — handler NULL, never fabricated (checkpoint (1b)
// Tier-0, the same limitation `KotlinOrderRoutes.kt`'s `::listOrders` shows). A lambda
// compiles to an `invokedynamic` body whose synthetic method IS the handler symbol.
package com.acme.orders.mvcroutes

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.MediaType
import org.springframework.web.servlet.function.router

@Configuration
class KotlinMvcRoutes {

    @Bean
    fun ktMvcRoutes(h: MvcRouteHandlers) = router {
        "/ktmvc".nest {
            GET("/invoices") { h.listInvoices(it) }                                       // GET(String, handler)
            GET("/invoices/{id}", accept(MediaType.APPLICATION_JSON)) { h.listInvoices(it) } // GET(String, RequestPredicate, handler)
            GET(path("/health")) { h.listInvoices(it) }                                   // GET(RequestPredicate, handler)
            POST("/invoices") { h.createInvoice(it) }
            accept(MediaType.APPLICATION_JSON) { h.listInvoices(it) }                        // accept(MediaType, handler): a route under a media guard alone
        }
        GET { h.listInvoices(it) }                                                        // GET(handler): a catch-all
    }
}
