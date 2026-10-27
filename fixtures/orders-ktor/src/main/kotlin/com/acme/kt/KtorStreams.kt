// Ktor's WebSocket and SSE routes, and a verb read off Ktor 3.6.0's static field (spec
// 2026-10-26 §3b, §3f). Its own file, so `KtorRoutes.kt` stays the very source the
// class-lambda twin compiles on Ktor 3.0.3, which has no such routes to read.
//
// `webSocket(path) { }` is `io/ktor/server/websocket/RoutingKt.webSocket$default(route,
// path, protocol, handler, …)` and `sse(path) { }` is `io/ktor/server/sse/RoutingKt.sse(route,
// path, handler)` (CP-54 row group (c)); both are static extensions on the block's own
// Route, so they nest under `route("/api")` as `get` does. Ktor registers a WebSocket route
// with a path, and `sse(path)`, under a GET selector (CP-54 rows 64-78): the WebSocket row
// is verbless, the SSE row GET, and a WebSocket route under `method(HttpMethod.Post)` is a
// node Ktor never dispatches, so it is no row. `method(HttpMethod.Get)` reads
// `getstatic HttpMethod.Get`, the 3.x static field, where 3.0.3 called a Companion getter.
package com.acme.kt

import io.ktor.http.HttpMethod
import io.ktor.server.application.Application
import io.ktor.server.application.install
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.method
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.sse.SSE
import io.ktor.server.sse.sse
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.sse.ServerSentEvent

fun Application.streams() {
    install(WebSockets)
    install(SSE)
    routing {
        route("/api") {
            webSocket("/chat") { }                                         // websocket /api/chat
            sse("/events") { send(ServerSentEvent("tick")) }               // sse GET /api/events
        }
        method(HttpMethod.Get) { get("/legacy") { call.respondText("legacy") } }   // GET /legacy
        method(HttpMethod.Post) { webSocket("/never-ws") { } }                     // no row
    }
}
