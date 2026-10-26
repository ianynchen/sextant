package probe

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.client.plugins.websocket.ws
import io.ktor.client.plugins.websocket.wss
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.get
import io.ktor.client.request.url
import kotlinx.coroutines.runBlocking

// Runs Ktor's own `DefaultRequest` plugin: a client with a mock engine, whose handler records the
// URL the request carries by the time it reaches the engine. Nothing here re-implements the
// merge; every output line is what Ktor produced.

private fun merge(label: String, base: String?, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val client = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
        if (base != null) defaultRequest { url(base) }
    }
    val outcome = try {
        client.get(relative)
        seen
    } catch (e: Throwable) {
        "FAILED " + e.javaClass.name + ": " + e.message
    }
    client.close()
    println("MERGE\t$label\t${base ?: "(no defaultRequest)"}\t$relative\t$outcome")
}

// The WebSocket and SSE calls resolve a relative address through the same plugin; the engine only
// records the URL the request carries and refuses to open a connection.
private fun resolveWith(label: String, base: String, relative: String, call: suspend (HttpClient) -> Unit) =
    runBlocking {
        var seen = "NOT REACHED"
        val client = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
            install(WebSockets)
            defaultRequest { url(base) }
        }
        try {
            call(client)
        } catch (e: Throwable) {
            // the mock engine completes no handshake; the URL was recorded before this
        }
        client.close()
        println("PROTOCOL\t$label\t$base\t$relative\t$seen")
    }

fun main() {
    println("IDENTITY\tktor-client-core\t" + HttpClient::class.java.`package`.implementationVersion)
    println("IDENTITY\tkotlin-stdlib\t" + KotlinVersion.CURRENT)

    val fresh = HttpRequestBuilder()
    println("DEFAULT\tverb\t" + fresh.method.value)
    println("DEFAULT\turl\t" + fresh.url.buildString())

    merge("base ends in /, path without /", "https://api.example.com/v1/", "orders")
    merge("base ends in /, path with /", "https://api.example.com/v1/", "/orders")
    merge("base without trailing /, path without /", "https://api.example.com/v1", "orders")
    merge("base without trailing /, path with /", "https://api.example.com/v1", "/orders")
    merge("absolute URL", "https://api.example.com/v1/", "https://other.example.com/x/y")
    merge("path with query", "https://api.example.com/v1/", "orders?limit=5&sort=asc")

    merge("extra: no base at all", null, "orders")
    merge("extra: base is a bare host", "https://api.example.com", "orders")
    merge("extra: base has a query", "https://api.example.com/v1/?key=1", "orders?limit=5")
    merge("extra: deeper path", "https://api.example.com/v1/a/b/", "c/d")

    resolveWith("ws relative, https base", "https://api.example.com/v1/", "/chat") { it.ws("/chat") { } }
    resolveWith("wss relative, http base", "http://api.example.com/v1/", "/chat") { it.wss("/chat") { } }
    resolveWith("webSocket absolute ws URL", "https://api.example.com/v1/", "ws://chat.example.com/room") {
        it.webSocketSession("ws://chat.example.com/room")
    }
}
