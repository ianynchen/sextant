// Ktor client calls whose response a later line uses (fix/chain-window-at-request, 2026-11-05).
//
// A `suspend` function whose suspension is not its last call compiles to a coroutine state
// machine: `invokeSuspend` branches on `label`, and the resume branch goes straight to the code
// after the suspension. So no call made before the request is sent runs on every path to the
// method's exit. Each call in `KtorClient.kt` is a tail call and compiles with no state
// machine, which is why no fixture had this shape before. Real Ktor code has it everywhere
// (kotlinconf-app, ktor-samples' client-mpp).
//
// `failover` sends ONE builder from two places, `HttpStatement(builder, client)` twice, with
// the address changed between the two sends.
package com.acme.kt

import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.client.statement.HttpStatement
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpMethod

suspend fun createOrder(): String {
    val response = client.post("https://orders.example.com/created") { setBody("order") }
    return response.bodyAsText()
}

suspend fun orderStatus(): String {
    val response = client.get("https://orders.example.com/status")
    return response.bodyAsText()
}

suspend fun failover(): String {
    val builder = HttpRequestBuilder()
    builder.method = HttpMethod.Post
    builder.url("https://orders.example.com/failover")
    val first = HttpStatement(builder, client).execute()
    if (first.status.value < 500) return first.bodyAsText()
    builder.url("https://mirror.example.com/failover")
    return HttpStatement(builder, client).execute().bodyAsText()
}
