// Ktor's routing DSL (`ktor-routing`, spec §14): every verb is a STATIC extension function
// whose receiver is the Route the enclosing block was handed — argument 0 in the bytecode —
// and every block is a `Function1<Route, Unit>` lambda the extractor links. Handlers are
// `suspend` lambdas, which compile to classes rather than `invokedynamic` bodies, so their
// rows carry a NULL handler (spec §13 case 8) until `kotlin-null-handler` lands.
package com.acme.kt

import io.ktor.server.application.Application
import io.ktor.server.response.respondText
import io.ktor.server.routing.Route
import io.ktor.server.routing.delete
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.route
import io.ktor.server.routing.routing

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
