// The Kotlin coRouter surface -- the fixture's first non-contract Kotlin.
// Mirrors the core shapes proven in OrderRoutes: one nest prefix, two verbs,
// one media predicate, a suspend handler reference and a suspend lambda.
package com.acme.orders.routes

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.MediaType
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
    }
}
