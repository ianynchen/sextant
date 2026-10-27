// Ktor's HTTP client, WebSocket client and SSE client (spec 2026-10-26 §3c, §3d, §3f).
//
// The client is a top-level `val`: `<clinit>` calls `HttpClientKt.HttpClient(CIO, block)`
// and writes the result with `putstatic` (CP-33 row 7, D00 §5's field written from a
// call). Its block installs two plugins that set no base and declares the base with
// `defaultRequest { url(…) }`, the `client-models/ktor.yml` ladder.
//
// Every HTTP call below is an INLINE function, so its bytecode is the builder sequence
// Kotlin inlined (CP-54 row group (b)): `new HttpRequestBuilder()`, `HttpRequestKt.url(…)`,
// `setMethod(getstatic HttpMethod.<Verb>)`, `new HttpStatement(builder, client)`. One call
// per form; `client.get("quotes")` is the relative one, joined onto the base by Ktor's own
// rule. The WebSocket and SSE calls are `BuildersKt.webSocket$default(client, url, …)` and
// `BuildersKt."sse-Mswn-_c$default"(client, url, …)` (CP-54 row group (d)).
package com.acme.kt

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.sse.SSE
import io.ktor.client.plugins.sse.sse
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.prepareGet
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.http.HttpMethod

val client = HttpClient(CIO) {
    install(WebSockets)
    install(SSE)
    defaultRequest { url("https://pricing.example.com/") }
}

suspend fun quotes() = client.get("quotes")                                         // relative
suspend fun placeOrder() = client.post("https://orders.example.com/orders") { setBody("order") }
suspend fun stockLevels() = client.get { url("https://stock.example.com/levels") }
suspend fun replaceOrder() = client.request("https://orders.example.com/orders/7") { method = HttpMethod.Put }
suspend fun prepared() = client.prepareGet("https://orders.example.com/prepared").execute()

suspend fun chat() = client.webSocket("ws://chat.example.com/chat") { }
suspend fun events() = client.sse("https://events.example.com/stream") { }
