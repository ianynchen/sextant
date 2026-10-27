package probe

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngineCapability
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.DefaultRequest
import io.ktor.client.plugins.HttpSend
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.plugin
import io.ktor.client.plugins.sse.SSE as ClientSSE
import io.ktor.client.plugins.sse.SSECapability
import io.ktor.client.plugins.sse.serverSentEvents
import io.ktor.client.plugins.sse.sse
import io.ktor.client.plugins.sse.sseSession
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket as clientWebSocket
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.client.plugins.websocket.ws
import io.ktor.client.plugins.websocket.wss
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.get
import io.ktor.client.request.request
import io.ktor.client.request.url
import io.ktor.http.HttpMethod
import io.ktor.http.URLProtocol
import io.ktor.server.application.Application
import io.ktor.server.application.createApplicationPlugin
import io.ktor.server.application.hooks.CallFailed
import io.ktor.server.application.install
import io.ktor.server.cio.CIO as ServerCIO
import io.ktor.server.engine.embeddedServer
import io.ktor.server.routing.Route
import io.ktor.server.routing.RoutingRoot
import io.ktor.server.routing.method
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.sse.SSE as ServerSSE
import io.ktor.server.sse.sse
import io.ktor.server.testing.testApplication
import io.ktor.server.websocket.WebSockets as ServerWebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.server.websocket.webSocketRaw
import java.net.Socket
import java.util.concurrent.atomic.AtomicReference
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

// Row group (j): joins row group (g) does not cover, each a shape a reader of (g) would
// otherwise have to predict — an address with a scheme and no host (`gemini-pro:generate`),
// a protocol-relative address and an address starting with three slashes. Ktor may refuse
// one; a refusal is recorded as what Ktor did (`Ktor threw …`), never as a probe failure,
// and only an address the engine never saw AND Ktor never refused aborts the run.
private fun join(label: String, base: String, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val client = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
        defaultRequest { url(base) }
    }
    val outcome = try {
        client.get(relative)
        seen
    } catch (e: Throwable) {
        "Ktor threw " + e.javaClass.name + ": " + e.message
    }
    client.close()
    println("JOIN\t$label\t$base\t$relative\t$outcome")
}

// Row group (j), continued: ONE `defaultRequest` block calling `url(…)` twice — which address
// the base is when a block sets it more than once.
private fun setTwice(label: String, first: String, second: String, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val client = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
        defaultRequest {
            url(first)
            url(second)
        }
    }
    val outcome = try {
        client.get(relative)
        seen
    } catch (e: Throwable) {
        "FAILED " + e.javaClass.name + ": " + e.message
    }
    client.close()
    println("TWICE\t$label\t$first\t$second\t$relative\t$outcome")
}

// Row group (i): the base a DERIVED client sends to — `parent.config { … }`, koog's shape. The
// parent carries a `defaultRequest` base; the derived client declares its own or none, and the
// engine records where Ktor sent the request. Whether `config` keeps the parent's plugin block,
// and which `url` wins when both declare one, is exactly what this answers.
private fun derived(label: String, parentBase: String, childBase: String?, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val parent = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
        defaultRequest { url(parentBase) }
    }
    val child = parent.config {
        if (childBase != null) defaultRequest { url(childBase) }
    }
    val outcome = try {
        child.get(relative)
        seen
    } catch (e: Throwable) {
        "FAILED " + e.javaClass.name + ": " + e.message
    }
    child.close()
    parent.close()
    println("DERIVED\t$label\t$parentBase\t${childBase ?: "(no defaultRequest)"}\t$relative\t$outcome")
}

// Row group (k): the engine-less factory, `HttpClient { … }`. It takes the first engine the
// classpath registers, a real one, so the request is stopped inside Ktor's `HttpSend`, after
// `DefaultRequest` has merged the address and before any engine runs: the URL is read there
// and the call refused, so nothing reaches the network. The engine the factory chose is
// recorded with it.
private object Recorded : RuntimeException("recorded")

private fun engineless(label: String, base: String, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val client = HttpClient { defaultRequest { url(base) } }
    client.plugin(HttpSend).intercept { request ->
        seen = request.url.buildString()
        throw Recorded
    }
    try {
        client.get(relative)
    } catch (e: Recorded) {
        // the URL was recorded; no engine ran
    } catch (e: Throwable) {
        seen = "FAILED " + e.javaClass.name + ": " + e.message
    }
    val engine = client.engine.javaClass.name
    client.close()
    println("ENGINELESS\t$label\t$base\t$relative\t$engine\t$seen")
}

// Row group (k), continued: an address that is a query and nothing else, over a base with and
// without a trailing `/` — whether the base's path survives.
private fun queryOnly(label: String, base: String, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val client = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
        defaultRequest { url(base) }
    }
    val outcome = try {
        client.get(relative)
        seen
    } catch (e: Throwable) {
        "FAILED " + e.javaClass.name + ": " + e.message
    }
    client.close()
    println("QUERY\t$label\t$base\t$relative\t$outcome")
}

// Row group (l): the DefaultRequest plugin installed with `install(DefaultRequest) { url(…) }`
// — whether a base set that way is joined as `defaultRequest { url(…) }`'s is (row 51).
private fun installed(label: String, base: String, relative: String) = runBlocking {
    var seen = "NOT REACHED"
    val client = HttpClient(MockEngine { request -> seen = request.url.toString(); respondOk() }) {
        install(DefaultRequest) { url(base) }
    }
    val outcome = try {
        client.get(relative)
        seen
    } catch (e: Throwable) {
        "FAILED " + e.javaClass.name + ": " + e.message
    }
    client.close()
    println("INSTALLED\t$label\t$base\t$relative\t$outcome")
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

// Row group (h): which verb a WebSocket or SSE route answers, asked of Ktor itself. Each tree is
// installed in a Ktor application and sent real requests. Two things are recorded per request,
// both by Ktor: the verb the SERVER received (an `onCall` hook, before routing), and the route
// node the router SELECTED (`RoutingCallStarted`, fired after resolution and before the handler
// runs; no event means no route matched) — so the answer is the router's own, not inferred from
// a status code, and a request whose verb was rewritten on the way is visible as such.
//
// SSE goes through Ktor's own test host, a plain request with the verb. WebSocket goes through a
// real CIO server and a raw socket writing the RFC 6455 handshake with the verb under test: Ktor's
// clients refuse to set `Upgrade` by hand, and the test host's WebSocket client sends its handshake
// as GET whatever verb it is handed — `testHostWebSocket` below records that, so the choice is
// measured rather than asserted. A call that fails after routing has its cause recorded too
// (`CallFailed`), so a 500 says which part of Ktor refused it.
private val failure = AtomicReference("")

private fun Application.observed(seen: AtomicReference<String>, selected: AtomicReference<String>, tree: Route.() -> Unit) {
    install(ServerWebSockets)
    install(ServerSSE)
    install(
        createApplicationPlugin("received") {
            onCall { call -> seen.set(call.request.local.method.value) }
            on(CallFailed) { _, cause -> failure.set("; the call failed: " + cause.javaClass.simpleName + ": " + cause.message) }
        },
    )
    monitor.subscribe(RoutingRoot.RoutingCallStarted) { call -> selected.set(call.route.toString()) }
    routing { tree() }
}

private fun report(label: String, verb: HttpMethod, path: String, seen: String, selected: String, outcome: String) =
    println("DISPATCH\t$label\t${verb.value} $path\t$seen\t$selected\t$outcome${failure.getAndSet("")}")

private fun testHostSse(label: String, requests: List<Pair<HttpMethod, String>>, tree: Route.() -> Unit) =
    testApplication {
        val seen = AtomicReference("NOT RECEIVED")
        val selected = AtomicReference("NONE")
        application { observed(seen, selected, tree) }
        val http = createClient { }
        for ((verb, path) in requests) {
            seen.set("NOT RECEIVED"); selected.set("NONE"); failure.set("")
            val outcome = try {
                "status " + http.request(path) { method = verb }.status.value
            } catch (e: Throwable) {
                "FAILED " + e.javaClass.name + ": " + e.message
            }
            report(label, verb, path, seen.get(), selected.get(), outcome)
        }
    }

private fun testHostWebSocket(label: String, verb: HttpMethod, path: String, tree: Route.() -> Unit) =
    testApplication {
        val seen = AtomicReference("NOT RECEIVED")
        val selected = AtomicReference("NONE")
        application { observed(seen, selected, tree) }
        val http = createClient { install(WebSockets) }
        val outcome = try {
            http.clientWebSocket(method = verb, path = path) { }
            "upgraded"
        } catch (e: Throwable) {
            "refused: " + e.message
        }
        report(label, verb, path, seen.get(), selected.get(), outcome)
    }

private fun socketWebSocket(label: String, requests: List<Pair<HttpMethod, String>>, tree: Route.() -> Unit) {
    val seen = AtomicReference("NOT RECEIVED")
    val selected = AtomicReference("NONE")
    val server = embeddedServer(ServerCIO, port = 0, host = "127.0.0.1") { observed(seen, selected, tree) }.start(wait = false)
    try {
        val port = runBlocking { server.engine.resolvedConnectors().first().port }
        for ((verb, path) in requests) {
            seen.set("NOT RECEIVED"); selected.set("NONE"); failure.set("")
            val outcome = try {
                Socket("127.0.0.1", port).use { socket ->
                    socket.soTimeout = 5000
                    socket.getOutputStream().write(
                        ("${verb.value} $path HTTP/1.1\r\nHost: 127.0.0.1:$port\r\nConnection: Upgrade\r\n" +
                            "Upgrade: websocket\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" +
                            "Sec-WebSocket-Version: 13\r\nContent-Length: 0\r\n\r\n").toByteArray(Charsets.US_ASCII),
                    )
                    socket.getOutputStream().flush()
                    "status line `" + socket.getInputStream().bufferedReader(Charsets.US_ASCII).readLine() + "`"
                }
            } catch (e: Throwable) {
                "FAILED " + e.javaClass.name + ": " + e.message
            }
            report(label, verb, path, seen.get(), selected.get(), outcome)
        }
    } finally {
        server.stop(100, 1000)
    }
}

// Row group (m): a WebSocket call's address joined onto a `defaultRequest` base, for every form
// and base shape a reader would otherwise have to predict from rows 61-63 — the `webSocket` and
// `webSocketSession` address forms beside `ws` and `wss`, both scheme pairs, a base with its own
// port, a path without `/`, a query on both sides, the parts form with only a path, a host given
// in the parts form, and absolute addresses of each scheme. The mock engine records the URL the
// request carries when it reaches the engine; it completes no handshake, so the call then fails,
// and only an address the engine never saw aborts the run.
private fun wsJoin(label: String, base: String, address: String, call: suspend (HttpClient) -> Unit) =
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
        println("WSJOIN\t$label\t$base\t$address\t$seen")
    }

// Row group (n): an SSE call's address joined onto a `defaultRequest` base. Ktor's SSE plugin
// refuses an engine that does not declare `SSECapability` before the request reaches it, and the
// plain mock engine declares only HTTP-timeout and WebSocket capabilities, so this engine is the
// mock engine with `SSECapability` added and nothing else changed. The capabilities it declares
// are printed with each row. The engine answers 200 with no event stream, so the call then fails;
// only an address the engine never saw aborts the run.
private class SseMockEngine(config: MockEngineConfig) : MockEngine(config) {
    override val supportedCapabilities: Set<HttpClientEngineCapability<out Any>> =
        super.supportedCapabilities + SSECapability
}

private fun sseJoin(label: String, base: String, address: String, call: suspend (HttpClient) -> Unit) =
    runBlocking {
        var seen = "NOT REACHED"
        val config = MockEngineConfig().apply { addHandler { request -> seen = request.url.toString(); respondOk() } }
        val engine = SseMockEngine(config)
        val capabilities = engine.supportedCapabilities.map { it.toString() }.sorted().joinToString(", ")
        val client = HttpClient(engine) {
            install(ClientSSE)
            defaultRequest { url(base) }
        }
        try {
            call(client)
        } catch (e: Throwable) {
            // no event stream came back; the URL was recorded before this
        }
        client.close()
        println("SSEJOIN\t$label\t$base\t$address\t$capabilities\t$seen")
    }

fun main() {
    // The version each Ktor jar in use states, as the running process sees it. The server jars are
    // only loaded, not run.
    val loaded = listOf(
        "ktor-http" to io.ktor.http.HttpMethod::class.java,
        "ktor-client-core" to HttpClient::class.java,
        "ktor-client-mock" to MockEngine::class.java,
        "ktor-server-websockets" to Class.forName("io.ktor.server.websocket.RoutingKt", false, HttpClient::class.java.classLoader),
        "ktor-server-sse" to Class.forName("io.ktor.server.sse.RoutingKt", false, HttpClient::class.java.classLoader),
        "ktor-server-test-host" to Class.forName("io.ktor.server.testing.TestApplicationKt", false, HttpClient::class.java.classLoader),
        "ktor-server-cio" to Class.forName("io.ktor.server.cio.CIO", false, HttpClient::class.java.classLoader),
    )
    for ((name, type) in loaded) println("IDENTITY\t$name\t" + type.`package`.implementationVersion)
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
    resolveWith("webSocketSession absolute ws URL", "https://api.example.com/v1/", "ws://chat.example.com/room") {
        it.webSocketSession("ws://chat.example.com/room")
    }

    val get = HttpMethod.Get
    val post = HttpMethod.Post
    socketWebSocket("`method(HttpMethod.Post) { webSocket(\"/ws\") { } }`", listOf(post to "/ws", get to "/ws")) {
        method(HttpMethod.Post) { webSocket("/ws") { } }
    }
    socketWebSocket("`webSocket(\"/ws\") { }`", listOf(get to "/ws", post to "/ws")) { webSocket("/ws") { } }
    socketWebSocket("`webSocketRaw(\"/raw\") { }`", listOf(get to "/raw", post to "/raw")) { webSocketRaw("/raw") { } }
    socketWebSocket("`route(\"/p\") { webSocket { } }`", listOf(get to "/p", post to "/p")) { route("/p") { webSocket { } } }
    socketWebSocket("`route(\"/r\") { method(HttpMethod.Post) { webSocket { } } }`", listOf(post to "/r", get to "/r")) {
        route("/r") { method(HttpMethod.Post) { webSocket { } } }
    }
    testHostSse("`sse(\"/e\") { }`", listOf(get to "/e", post to "/e")) { sse("/e") { } }
    testHostSse("`route(\"/q\") { sse { } }`", listOf(get to "/q", post to "/q")) { route("/q") { sse { } } }
    testHostWebSocket("test host client, `webSocket(\"/ws\") { }`", post, "/ws") { webSocket("/ws") { } }

    // Last, so rows 1-78 keep their numbers.
    derived("its own defaultRequest base", "https://parent.example.com/p/", "https://child.example.com/c/", "orders")
    derived("no defaultRequest of its own", "https://parent.example.com/p/", null, "orders")

    val models = "https://generativelanguage.googleapis.com/v1beta/models/"
    join("a scheme and no host, base ending in /", models, "gemini-pro:generateContent")
    join("a scheme and no host, base without trailing /", models.removeSuffix("/"), "gemini-pro:generateContent")
    join("protocol-relative", "https://api.example.com/v1/", "//other.example.com/x/y")
    join("three leading slashes", "https://api.example.com/v1/", "///x/y")
    setTwice("two absolute addresses", "https://first.example.com/a/", "https://second.example.com/b/", "orders")
    setTwice("an absolute then a relative address", "https://first.example.com/a/", "b/", "orders")

    engineless("its own defaultRequest base", "https://engineless.example.com/e/", "orders")
    queryOnly("base without trailing /", "https://api.example.com/v1/items", "?q=1")
    queryOnly("base ending in /", "https://api.example.com/v1/", "?q=1")
    queryOnly("base with its own query", "https://api.example.com/v1/items?key=1", "?q=1")

    installed("`install(DefaultRequest) { url(…) }`", "https://installed.example.com/i/", "orders")

    // Row group (m), after every earlier row so their numbers hold. First the default port of each
    // scheme the joins below render, as Ktor's own `URLProtocol` states it: a joined address writes
    // its port only where it differs from its scheme's default.
    for (protocol in listOf(URLProtocol.HTTP, URLProtocol.HTTPS, URLProtocol.WS, URLProtocol.WSS)) {
        println("PORT\t${protocol.name}\t${protocol.defaultPort}")
    }
    val https = "https://api.example.com/v1/"
    val http = "http://api.example.com/v1/"
    val httpsPort = "https://api.example.com:8443/v1/"
    val httpPort = "http://api.example.com:8080/v1/"
    wsJoin("`webSocket(\"/chat\")`, https base", https, "/chat") { it.clientWebSocket("/chat") { } }
    wsJoin("`webSocketSession(\"/chat\")`, https base", https, "/chat") { it.webSocketSession("/chat") }
    wsJoin("`ws(\"/chat\")`, http base", http, "/chat") { it.ws("/chat") { } }
    wsJoin("`wss(\"/chat\")`, https base", https, "/chat") { it.wss("/chat") { } }
    wsJoin("`ws(\"chat\")`, https base", https, "chat") { it.ws("chat") { } }
    wsJoin("`ws(\"/chat\")`, https base with its own port", httpsPort, "/chat") { it.ws("/chat") { } }
    wsJoin("`wss(\"/chat\")`, https base with its own port", httpsPort, "/chat") { it.wss("/chat") { } }
    wsJoin("`ws(\"/chat\")`, http base with its own port", httpPort, "/chat") { it.ws("/chat") { } }
    wsJoin("`wss(\"/chat\")`, http base with its own port", httpPort, "/chat") { it.wss("/chat") { } }
    wsJoin("`ws(\"/chat?room=1\")`, https base with a query", "$https?key=1", "/chat?room=1") {
        it.ws("/chat?room=1") { }
    }
    wsJoin("`ws(path = \"/parts\")`, the parts form with only a path, https base", https, "/parts") {
        it.ws(path = "/parts") { }
    }
    wsJoin("`wss(path = \"/parts\")`, the parts form with only a path, http base", http, "/parts") {
        it.wss(path = "/parts") { }
    }
    wsJoin("`webSocket(path = \"/parts\")`, the parts form with only a path, https base", https, "/parts") {
        it.clientWebSocket(path = "/parts") { }
    }
    wsJoin("`webSocketSession(path = \"/parts\")`, the parts form with only a path, https base", https, "/parts") {
        it.webSocketSession(path = "/parts")
    }
    wsJoin("`webSocket(host = \"chat.example.com\", path = \"/parts\")`, https base", https, "/parts") {
        it.clientWebSocket(host = "chat.example.com", path = "/parts") { }
    }
    wsJoin("`ws(\"https://other.example.com/x\")`, an absolute https address", https, "https://other.example.com/x") {
        it.ws("https://other.example.com/x") { }
    }
    wsJoin("`wss(\"ws://other.example.com/x\")`, an absolute ws address", https, "ws://other.example.com/x") {
        it.wss("ws://other.example.com/x") { }
    }
    wsJoin("`webSocket(\"wss://other.example.com/x\")`, an absolute wss address", https, "wss://other.example.com/x") {
        it.clientWebSocket("wss://other.example.com/x") { }
    }
    wsJoin("`ws(\"//other.example.com/x\")`, a protocol-relative address", https, "//other.example.com/x") {
        it.ws("//other.example.com/x") { }
    }

    // Row group (n).
    sseJoin("`sse(\"/stream\")`, base ending in /", https, "/stream") { it.sse("/stream") { } }
    sseJoin("`sse(\"stream\")`, base ending in /", https, "stream") { it.sse("stream") { } }
    sseJoin("`sse(\"stream\")`, base without trailing /", https.removeSuffix("/"), "stream") { it.sse("stream") { } }
    sseJoin("`sse(\"/stream\")`, http base with its own port", httpPort, "/stream") { it.sse("/stream") { } }
    sseJoin("`sse(\"stream?x=1\")`, base with a query", "$https?key=1", "stream?x=1") { it.sse("stream?x=1") { } }
    sseJoin("`sse(\"https://events.example.com/stream\")`, an absolute address", https, "https://events.example.com/stream") {
        it.sse("https://events.example.com/stream") { }
    }
    sseJoin("`sseSession(\"/stream\")`", https, "/stream") { it.sseSession("/stream") }
    sseJoin("`serverSentEvents(\"/stream\")`", https, "/stream") { it.serverSentEvents("/stream") { } }
    sseJoin("`sse(path = \"/parts\")`, the parts form with only a path", https, "/parts") { it.sse(path = "/parts") { } }
    sseJoin("`sse(scheme = \"http\", path = \"/parts\")`, the parts form with a scheme", https, "/parts") {
        it.sse(scheme = "http", path = "/parts") { }
    }
}
