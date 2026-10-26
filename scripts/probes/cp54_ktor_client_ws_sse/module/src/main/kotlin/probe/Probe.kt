package probe

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.sse.SSE as ClientSSE
import io.ktor.client.plugins.sse.sse
import io.ktor.client.plugins.sse.sseSession
import io.ktor.client.plugins.websocket.WebSockets as ClientWebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.client.plugins.websocket.ws
import io.ktor.client.plugins.websocket.wss
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.head
import io.ktor.client.request.options
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.prepareGet
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.http.HttpMethod
import io.ktor.server.application.Application
import io.ktor.server.application.install
import io.ktor.server.routing.Route
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.sse.SSE
import io.ktor.server.sse.sse
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.server.websocket.webSocketRaw
import io.ktor.sse.ServerSentEvent

// One function per measured shape, so `javap` shows each in isolation.

val client = HttpClient(CIO) {
    install(ClientWebSockets)
    install(ClientSSE)
    defaultRequest { url("https://api.example.com/") }
}

// A client derived from another one (koog's shape): `config` re-runs the plugin block.
val derivedClient = client.config {
    defaultRequest { url("https://derived.example.com/") }
}

// ---- (b) the HTTP client's five forms, and a relative call ---------------------------------

suspend fun clientGetString() = client.get("https://orders.example.com/orders")

suspend fun clientPostWithBody() = client.post("https://orders.example.com/orders") { setBody("x") }

suspend fun clientGetBlockUrl() = client.get { url("https://orders.example.com/blockurl") }

suspend fun clientRequestPut() = client.request("https://orders.example.com/put") { method = HttpMethod.Put }

suspend fun clientPrepare() = client.prepareGet("https://orders.example.com/prepared").execute()

suspend fun clientPostNoBody() = client.post("https://orders.example.com/post-plain")

suspend fun clientPutString() = client.put("https://orders.example.com/put-string") { setBody("x") }

suspend fun clientPatchString() = client.patch("https://orders.example.com/patch-string") { setBody("x") }

suspend fun clientDeleteString() = client.delete("https://orders.example.com/delete-string")

suspend fun clientHeadString() = client.head("https://orders.example.com/head-string")

suspend fun clientOptionsString() = client.options("https://orders.example.com/options-string")

suspend fun clientRelative() = client.get("relative/path")

suspend fun clientDerivedRelative() = derivedClient.get("/derived/path")

// ---- (d) WebSocket and SSE clients ---------------------------------------------------------

suspend fun clientWebSocket() = client.webSocket("ws://chat.example.com/chat") { }

suspend fun clientWebSocketParts() = client.webSocket(host = "chat.example.com", port = 8080, path = "/parts") { }

suspend fun clientWebSocketRequestLambda() = client.webSocket({ url("ws://chat.example.com/lambda") }) { }

suspend fun clientWs() = client.ws("/opentelemetry/websocket") { }

suspend fun clientWss() = client.wss("/secure/websocket") { }

suspend fun clientWebSocketSession() = client.webSocketSession("ws://chat.example.com/session")

suspend fun clientSse() = client.sse("https://events.example.com/stream") { }

suspend fun clientSseParts() = client.sse(host = "events.example.com", port = 8080, path = "/sse-parts") { }

suspend fun clientSseRequestLambda() = client.sse({ url("https://events.example.com/lambda") }) { }

suspend fun clientSseSession() = client.sseSession("https://events.example.com/session")

// ---- (c) the server's WebSocket and SSE routes ---------------------------------------------

fun Route.serverWsPath() { webSocket("/ws/chat") { } }

fun Route.serverWsPathAndProtocol() { webSocket("/ws/protocol", protocol = "chat") { } }

fun Route.serverWsPathless() { webSocket { } }

fun Route.serverWsProtocolOnly() { webSocket(protocol = "pathless") { } }

fun Route.serverWsRawPath() { webSocketRaw("/ws/raw") { } }

fun Route.serverWsRawFull() { webSocketRaw("/ws/raw-auto", "chat", true) { } }

fun Route.serverSsePath() { sse("/sse/events") { send(ServerSentEvent("x")) } }

fun Route.serverSsePathless() { sse { send(ServerSentEvent("pathless")) } }

fun Route.serverNested() {
    route("/api") {
        webSocket("/nested") { }
        sse("/nested-events") { }
    }
}

fun Application.serverModule() {
    install(WebSockets)
    install(SSE)
    routing {
        serverWsPath()
        serverNested()
    }
}
