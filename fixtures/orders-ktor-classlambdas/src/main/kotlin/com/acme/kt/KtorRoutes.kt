// Ktor's routing DSL (`ktor-routing`, spec §14): every verb is a STATIC extension function
// whose receiver is the Route the enclosing block was handed — argument 0 in the bytecode —
// and every block is a `Function1<Route, Unit>` lambda the extractor links. Handlers are
// `suspend` lambdas, which compile to classes rather than `invokedynamic` bodies; the
// extractor marks each class with the `invokeSuspend` holding its body (`lambda_body`) and
// every engine reads the instance as that lambda (spec 2026-09-19 §3b), so each row's
// handler is the body's own symbol (`KtorRoutesKt$orders$1$1$1#invokeSuspend`).
package com.acme.kt

import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.server.application.Application
import io.ktor.server.response.respondText
import io.ktor.server.routing.Route
import io.ktor.server.routing.accept
import io.ktor.server.routing.contentType
import io.ktor.server.routing.delete
import io.ktor.server.routing.get
import io.ktor.server.routing.header
import io.ktor.server.routing.method
import io.ktor.server.routing.optionalParam
import io.ktor.server.routing.param
import io.ktor.server.routing.post
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.util.getOrFail

fun Application.orders() {
    routing {
        route("/api") {
            get("/orders") { call.respondText("[]") }
            post("/orders") { call.respondText("created") }
            route("/v2") {
                get("/orders") { call.respondText("[]") }
                delete("/orders/{id}") { call.respondText("gone") }
            }
            // Slashless segments: Ktor's `RoutingPath.parse` splits on `/` and drops the
            // empty parts, so `route("legacy") { get("orders") { } }` is `/api/legacy/orders`
            // — the catalog's `path_join: leading_slash`, exercised here.
            route("legacy") {
                get("orders") { call.respondText("[]") }
            }
            get { call.respondText("root") }                                  // get(Route, Function2): the prefix itself
        }
        get("/health") { call.respondText("ok") }
        api()
        route("/api") { v2() }
    }
}

// A Route-extension helper called from inside `routing { }` — Ktor's own recommended way to
// split a routing tree (`ktor-route-extensions`, spec 2026-09-19 §4a). `api()` compiles to a
// STATIC `api(Route)` whose one argument is the block's own parameter — the origin — so the
// walk follows the call into this body with parameter 0 as the new origin, and `/helper`
// derives resolved on `orders()`. (Before the walk followed helper calls this was pinned as
// silence: spec §7 case 4's boundary for a builder received as a parameter.)
fun Route.api() {
    get("/helper") { call.respondText("helper") }
}

// A second-level helper under a prefix: `route("/api") { v2() }` → `v2()` → `orders2()`,
// two module-local calls deep, and the prefix that reached the first call carries all the
// way down — `GET /api/deep`.
fun Route.v2() {
    orders2()
}
fun Route.orders2() {
    get("/deep") { call.respondText("deep") }
}

// The wrong-receiver case (spec §14 test 13): a verb registered on ANOTHER route from inside
// a block is not under that block's prefix, and the engine must not say it is.
fun Application.elsewhere(other: Route) {
    routing {
        route("/api") {
            other.get("/stray") { call.respondText("stray") }
        }
    }
}

// A module-local DSL function with a DEFAULT parameter (`kotlin-default-bridge-calls`): a
// call that omits `version` compiles to `mount$default(this, "/d", null, build, 2, null)` —
// a different name and arity, which no rule matched until the bridge projection. `version`
// does not shape the path, so a rule reading `path_arg: 1` states the truth. Under the
// shipped catalog, which has no rule for `mount`, each call is a helper call the walk
// FOLLOWS: inside, `route(path, build)` sits on the origin but its path is this function's
// PARAMETER, unreadable there — one unresolved row per call, honestly, never silence.
val mountedVersions = mutableListOf<String>()
fun Route.mount(path: String, version: String = "v1", build: Route.() -> Unit): Route {
    mountedVersions += version
    return route(path, build)
}
fun Application.defaults() {
    routing {
        mount("/d") { get("/x") { call.respondText("x") } }         // version defaulted → mount$default
        mount("/e", "v2") { get("/y") { call.respondText("y") } }   // both passed → plain mount
    }
}

// The SELECTOR blocks (`ktor-selector-blocks`, `ktor-route-with-verb`; spec 2026-09-19 §4b,
// §4c), in a routing tree of their own so `orders()`'s pins above stay readable. Each
// selector is a prefix that sets something other than a path: `method`/the four-argument
// `route` set the VERB, `accept`/`contentType` set a media column (`ContentType.Application.
// Json` is a GETTER call on the nested object, CP-24 Q4, read through the catalog's
// `media_values.getters`), and `header`/`param`/`optionalParam` are REQUIREMENTS the
// routing tree enforces — `endpoint_metadata` rows, `required` for the three that refuse a
// request without the value and `optional` for `optionalParam`. `handle { }` is Ktor's
// verb-less terminal (a MEMBER of `Route`, CP-24 Q1b): under `method(Get)` it takes the
// scope's verb and serves the prefix chain itself — here the root, `/`; under a bare
// `route("/health2")` it serves every method, one row per member of
// `HttpMethod.DefaultMethods` (seven, CP-24 Q2). The last block is the CONFLICT: a `get`
// under `method(Post)` is a node Ktor registers and can never dispatch
// (`HttpMethodRouteSelector.evaluate` returns the failure constant on a mismatch, CP-24
// Q7), and the honest row for it is NO row — `/never` is asserted absent.
fun Application.selectors() {
    routing {
        method(HttpMethod.Get) { handle { call.respondText("m") } }               // GET /
        route("/health2") { handle { call.respondText("any") } }                  // seven rows
        accept(ContentType.Application.Json) { get("/j") { call.respondText("j") } }
        contentType(ContentType.Application.Json) { post("/c") { call.respondText("c") } }
        header("X-Api-Version", "2") { get("/orders") { call.respondText("v2") } }
        param("debug") { get("/dbg") { call.respondText("dbg") } }
        param("mode", "fast") { get("/fast") { call.respondText("fast") } }
        optionalParam("page") { get("/paged") { call.respondText("paged") } }
        route("/legacy2", HttpMethod.Put) { handle { call.respondText("put") } }  // PUT /legacy2
        method(HttpMethod.Post) { get("/never") { call.respondText("never") } }   // no row
    }
}

// HANDLER-BODY READS (`request_reads`, spec 2026-09-19 §5d; CP-24 Q5/Q6). What a handler
// READS off the request is one `endpoint_metadata` row per read, `requirement` NULL unless
// the API itself refuses the request (A3): `call.request.headers["X-Trace"]` → header,
// `call.request.queryParameters["q"]` → query, `call.parameters["page"]` → query — all
// three end in `StringValues.get(String)`, told apart by the getter that PRODUCED the
// receiver (the catalog's `via`) — and `call.parameters.getOrFail("cursor")` → query,
// `required`. NOT through a call to `ParametersKt.getOrFail`: the function is `inline`, so
// this class carries its body — `Parameters.get("cursor") ; ifnonnull ; new
// MissingRequestParameterException("cursor") ; athrow` (CP-24 Q5's throw, compiled in) —
// and the catalog's `required_when_thrown` reads the exception the body constructs with
// the read's own name. `call.parameters["id"]` names the route's own `{id}`:
// `call.parameters` merges path and query, so that read is the path variable and gets NO
// row (`skip_path_variables`, A6). Each read's static receiver type — `RoutingCall`,
// `RoutingRequest`, `Parameters`/`Headers` — is what kotlinc wrote at the call site, and
// the catalog's `via`/`owner` spellings are read off THIS class's bytecode.
fun Application.reads() {
    routing {
        get("/reads/orders/{id}") {
            val id = call.parameters["id"]
            val page = call.parameters["page"]
            val trace = call.request.headers["X-Trace"]
            val q = call.request.queryParameters["q"]
            val cursor = call.parameters.getOrFail("cursor")
            call.respondText("$id $page $trace $q $cursor")
        }
    }
}
