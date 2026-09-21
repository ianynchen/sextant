// The Kotlin coRouter surface -- the fixture's first non-contract Kotlin.
// Mirrors the core shapes proven in OrderRoutes: one nest prefix, two verbs,
// one media predicate, a suspend handler reference and a suspend lambda -- and, at the
// top level, `accept(MediaType.APPLICATION_JSON) { … }`: the DSL's route-declaring media
// overload (`accept(MediaType, Function2)V`, CP-29 row 10), a route under a media guard
// alone, which derives `method` NULL, path `/**`, `produces: application/json` with its
// suspend lambda as the handler (`dsl-media-route`).
package com.acme.orders.routes

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.MediaType
import org.springframework.web.reactive.function.server.CoRouterFunctionDsl
import org.springframework.web.reactive.function.server.ServerRequest
import org.springframework.web.reactive.function.server.ServerResponse
import org.springframework.web.reactive.function.server.buildAndAwait
import org.springframework.web.reactive.function.server.coRouter

@Configuration
class KotlinOrderRoutes {

    suspend fun listOrders(request: ServerRequest): ServerResponse =
        ServerResponse.ok().buildAndAwait()

    @Bean
    fun ktRoutes() = coRouter {
        "/kt".nest {
            GET("/orders", ::listOrders)
            POST("/orders") {
                ServerResponse.ok().buildAndAwait()
            }
            accept(MediaType.APPLICATION_JSON).nest {
                GET("/rich") {
                    ServerResponse.ok().buildAndAwait()
                }
            }
        }
        extra()
        accept(MediaType.APPLICATION_JSON) { listOrders(it) }
    }
}

// A DSL-receiver helper called from inside `coRouter { }` (spec 2026-09-19 §4a): a top-level
// extension compiles to a STATIC `extra(CoRouterFunctionDsl)` whose one argument is the
// block's own parameter -- the origin -- so the walk follows the call and `GET("/kt/extra")`,
// a member call on that parameter, derives on `ktRoutes`.
fun CoRouterFunctionDsl.extra() {
    GET("/kt/extra") {
        ServerResponse.ok().buildAndAwait()
    }
}
