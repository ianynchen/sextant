// The reactive Kotlin router DSL WITHOUT coroutines (`GAP-1b`): `router { }` from
// `RouterFunctionDslKt`, the twin of the `coRouter { }` in KotlinOrderRoutes.kt. Derived
// nothing until this file's catalog entry existed; the corrected verb rules land with it
// because this is their first reactive live instance (spec §1b).
package com.acme.orders.routes

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.MediaType
import org.springframework.web.reactive.function.server.ServerResponse
import org.springframework.web.reactive.function.server.router

@Configuration
class KotlinWebFluxRoutes {

    @Bean
    fun ktFluxRoutes() = router {
        "/ktflux".nest {
            GET("/orders") { ServerResponse.ok().build() }                                // GET(String, handler)
            GET("/orders/{id}", accept(MediaType.APPLICATION_JSON)) { ServerResponse.ok().build() }
            POST("/orders") { ServerResponse.ok().build() }
        }
        GET { ServerResponse.ok().build() }                                               // catch-all
    }
}
