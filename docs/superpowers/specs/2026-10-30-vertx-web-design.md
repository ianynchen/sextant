# Vert.x Web and WebClient — design

**Status: DRAFT 2026-10-30, for the user's approval.** Java/Kotlin framework order 3
(`docs/COVERAGE.md` "Priority order"). Moves two COVERAGE lines: §5.1's **Vert.x Web**
(`◐ 0/1`, tier B) and §5.2's **Vert.x WebClient** (`✗`, no row). The §2c Vert.x family row
goes from `◐ (1 not shipped) | ✗ | … | ✅` to `✅ | ✅ | … | ✅`. The language-level REST in
cell stays `◐`, because Spring Data REST, Servlet and Akka HTTP each still hold one tier-C
row; REST out goes from `◐ (1B)` to `✅` only if the Camel line also leaves the target list
(§6).

The user opted out of the question round (2026-10-30: "write the spec, then explain to me
your design"). Every decision below not taken from an earlier ruling is **my call**, and is
marked so.

## 1. What this is for

A Vert.x service's architecture document should show the HTTP routes it serves and the
HTTP calls it makes, exactly as it does for a Spring, Quarkus, Micronaut, Ktor or Javalin
service. Today a Vert.x Web module shows **no** inbound HTTP rows and **no** outbound HTTP
rows. Only its event-bus traffic appears, because `vertx-eventbus*.yml` already ship.

**Success:** on the fixture and the measured corpora, every route a Vert.x `Router` serves
from a handler in the module is one inbound row, with the right verb, path and handler. Every
`WebClient` request the module builds and sends is one outbound row, with the right verb,
address and body. Nothing is published that Vert.x would not serve or send.

**Anti-goals:**
- **No row for middleware.** An auth, body, CORS or logging handler on a route is not an
  endpoint, and must not read as one.
- **No path invented by joining a prefix to a router it was never mounted on.**
- **No Vert.x-specific engine.** The work reuses the shared chain walk, value walk and
  producer reader (ruling 6 of the Quartz design, *"call chains are the same, assignments are
  the same … the different pieces should connect"*).

## 2. Measured first

### 2a. The API (to be pinned by probe CP-56)

`javap` over `io.vertx:vertx-web` and `vertx-web-client` **4.5.10** and **5.0.0**, read
2026-10-30. The probe adds the corpora's newest line, **5.2.x**.

**`Router`** (`io.vertx.ext.web.Router`):
- `static router(Vertx)`;
- `route()`, `route(String)`, `route(HttpMethod, String)`, `routeWithRegex(String)`,
  `routeWithRegex(HttpMethod, String)`;
- for each of `get post put delete patch head options trace connect`: `x()`, `x(String)` and
  `xWithRegex(String)`.
- **4.5 only:** `mountSubRouter(String, Router)`.

**`Route`** (`io.vertx.ext.web.Route`), each returning the `Route`:
- `method(HttpMethod)`, `path(String)`, `pathRegex(String)`;
- `produces(String)`, `consumes(String)`, `virtualHost(String)`, `order(int)`, `setName(String)`;
- `handler(Handler<RoutingContext>)`, `blockingHandler(…)` (two arities),
  `respond(Function<RoutingContext, Future<T>>)`, `failureHandler(…)`;
- `subRouter(Router)` (4.5 and 5.0).

**`WebClient`** (`io.vertx.ext.web.client.WebClient`):
- `create(Vertx[, WebClientOptions[, PoolOptions]])`, `wrap(HttpClient[, WebClientOptions])`;
- per verb `get post put delete patch head`, each returning `HttpRequest<Buffer>`:
  - `x(String uri)`, `x(String host, String uri)`, `x(int port, String host, String uri)`;
  - each of those again taking `UriTemplate` instead of `String uri`;
  - `xAbs(String url)` and `xAbs(UriTemplate)`;
- `request(HttpMethod, …)` with the same address forms, plus `SocketAddress` and
  `RequestOptions` forms, and `requestAbs(HttpMethod, …)`.

**`HttpRequest<T>`**:
- `method(HttpMethod)`, `uri(String)`, `host(String)`, `port(int)`, `ssl(Boolean)`;
- `putHeader(String, String)`, `addQueryParam`, `setQueryParam`;
- `as(BodyCodec<U>)`, `copy()`;
- terminals `send()`, `sendJson(Object)`, `sendJsonObject(JsonObject)`, `sendBuffer(Buffer)`,
  `sendForm(MultiMap[, String])`, `sendMultipartForm(…)`, `sendStream(…)`. 4.5 has each
  with and without a trailing callback; 5.0 has the `Future` forms only.

**`HttpMethod`** is a class with static fields (`HttpMethod.GET`, …), not an enum: the verb
is a `getstatic`, read through the `verb_values.fields` map Ktor's client already uses.

The probe must also record:
- whether `io.vertx.rxjava3.ext.web.Router` / `WebClient` and
  `io.vertx.mutiny.ext.web.Router` / `WebClient` declare the same names, and their
  descriptors (§3a, §3d);
- `WebClientOptions#setDefaultHost(String)` / `setDefaultPort(int)`;
- how javac compiles `router.get("/x").handler(this::h)` and a lambda handler.

### 2b. Corpora (pulled 2026-10-30, shallow, into `examples/`)

| Corpus | Commit | Vert.x | What its main code does |
|---|---|---|---|
| `vert-x3/vertx-examples` | `091b03f` | 5.x | The official shapes. 66 files use Vert.x Web: 121 `verb("…")` routes, 43 `route()`, 32 `route("…")`, 11 `subRouter` (most mount a SockJS bridge or an OpenAPI-built router), 29 `WebClient.create`, 24 `client.verb(port, host, uri)`, 3 `*Abs`, 29 `send*`, 12 RxJava, 9 Kotlin coroutine, 9 `RouterBuilder` |
| `strimzi/strimzi-kafka-bridge` | `d55d42b` | 5.2.2 | Routes come from `src/main/resources/openapi.json` through `RouterBuilder` (`routerBuilder.getRoute(operationId).addHandler(h)`); no `router.verb(…)` route |
| `eclipse-hono/hono` | `e1c98be` | per its build | A production HTTP adapter (`VertxBasedHttpProtocolAdapter`): `router.post(ROUTE_TELEMETRY_ENDPOINT).handler(this::handlePostTelemetry)`, the same verb and path registered twice (once with auth and body handlers, once with the answering handler), `routeWithRegex`/`putWithRegex`, a path built with `String.format`, 24 verb calls on constant paths, and `client.post(QUERY_URI)` WebClient calls built in a helper |
| `gentics/mesh` | `315fc22` | 5.1.5 | Most routes go through Mesh's own wrapper (`InternalEndpointRoute`, a library jar), whose `Router` calls are inside that jar. 26 direct `route("…")` and 12 `subRouter` calls |

**What the corpora say about the design:**
- **Several routes, one identity, is the common production shape, not a corner** (Hono).
  Vert.x runs every matching route in order, and a handler that calls `ctx.next()` passes
  the request on. So the route that answers is not always the first one registered.
- **Constant and computed paths dominate** (Hono's constants and `String.format`). The value
  walk, not a literal-only reader, has to read the path.
- **Two real route sources are outside the code's calls:**
  - an OpenAPI file read by `RouterBuilder` (Strimzi, and 9 examples);
  - an in-house wrapper library (Mesh).

  Both are stated boundaries (§4), each with a COVERAGE row of its own.

## 3. The design

### 3a. Inbound — catalog `vertx-web.yml`, style `fluent`, direction `inbound`

This is the shape `vertx-eventbus-chain.yml` already ships: a root call that names the
address, steps that refine it, and a terminal that names the handler.

**Why `fluent` and not `combinator` (my call, after the builder check).** `combinator` folds
one *tree* of calls — Ktor's nested `route { get { } }`, Spring's `route().GET(…)` — and
already has verb fan-out (`all_methods`), media and the `leading_slash` prefix join. A Vert.x
router is not a tree: each route is its own statement on a shared `Router` object, joined
to a mount only by object identity (§3c), which is a per-chain walk plus the producer
reader. So routes stay on `fluent`, and `fluent` gains four GENERAL features, each named for
what it does rather than for Vert.x:

1. **Repeating steps** — a step declared `repeats: true` adds each call's capture to a list
   instead of replacing it (today every fluent step is "last wins", `shapes/chains.py`).
   Vert.x needs it for `method(…)` (several verbs) and for `handler(…)` (several handlers on
   one route).
2. **Verb fan-out** — `all_methods` and one row per captured verb, for an inbound fluent row.
3. **Media** — `consumes`/`produces` captures filling the row's media columns (today
   `fluent` sets both NULL).
4. **A prefix join** — `leading_slash`, applied to the prefix §3c finds.

`all_methods` expansion, the media columns and the `leading_slash` join already exist in
`engines/combinator.py`; they are **moved into a shared module and called from both engines**,
never copied (the "removing the cause beats detecting it" rule).

- **Roots** (owner `io.vertx.ext.web.Router`):
  - each `x(String)` with `http_method: X`;
  - `route(HttpMethod, String)`, with the verb captured through `verb_values.fields`;
  - `route(String)`;
  - the `…WithRegex` forms, each capturing `path_regex`.

  The argument-less forms (`route()`, `get()`) are roots too, so that a later
  `.path(…)` / `.method(…)` step can supply what they lack.
- **Steps:**
  - `method(HttpMethod)` adds a verb (`repeats: true`); several calls are several verbs
    (Vert.x's own rule);
  - `path(String)` / `pathRegex(String)` set the path;
  - `produces` / `consumes` add media, as the media columns already carry for Spring;
  - `virtualHost`, `order`, `setName`, `useNormalizedPath`, `putMetadata`, `disable`/`enable`
    pass through (my call: they change neither identity nor contract).
- **Terminals** — `handler`, `blockingHandler`, `respond`, each capturing `handler: arg0`
  (`repeats: true`: `.handler(auth).handler(body).handler(this::h)` is three handlers on one
  route, in order); `failureHandler` is not a terminal (§4). The chain's END is its last
  terminal call.
- **A route with no verb serves every verb.** That is Vert.x's rule, and the catalog declares
  `all_methods` as `spring-web.yml` does for a `@RequestMapping` with no `method`: one row
  per verb in the list. (My call: the list is the `HttpMethod` constants Vert.x 4.5/5.0
  declare as standard. The probe fixes it.)
- **A route with no path is not a row.** `router.route().handler(BodyHandler.create())` is
  global middleware, with no wire identity of its own.
- **Paths are published as written:**
  - `/orders/:id` keeps Vert.x's `:id`, which `_path_variables` already reads as a path
    variable (`test_request_requirements.py`, "colon");
  - `/static/*` keeps its `*`;
  - a regex route's path is the regex verbatim, at **`partial`** (my call, after the builder
    check: `resolved` would let the path canonicaliser and the linker treat a regex as a
    path template, and `getWithRegex("/health")` would match a literal `/health`
    elsewhere). The builder confirms that a `partial` path is neither canonicalised into a
    template nor linked; if either happens, that is fixed for every partial path, not for
    Vert.x.

### 3b. Which handler answers — a route chain's pass-through rule (new, general)

Vert.x calls a route's handlers in order, then the next matching route's, for as long as
each handler calls `RoutingContext.next()`. **A handler whose body calls `next()` passes the
request on; it is middleware.** (DR-6: Vert.x's own dispatch rule, not ours.)

- **New catalog key on the `fluent` style:**
  `passes_on: { owner: io.vertx.ext.web.RoutingContext, method: next }`. (Not
  `pass_through`, which `combinator` already uses for a filter step that carries a chain on.)
  - **Which code a handler runs** (ruled 2026-10-30, review issue 1): Vert.x calls
    `handle(ctx)` on the object passed, so the handler argument is followed to that object
    with the producer reader. `this::h` runs `h`, a lambda its own synthetic body, `new X(…)`
    `X.handle`, and a field, local or factory call (`createDefaultCorsHandler(origin)`) the
    object it holds or returns. An object of a class **not in the module**
    (`BodyHandler.create()`, the `CorsHandler` Hono's factory returns, an
    `AuthenticationHandler`) passes on: nothing in the module answers through it.
  - **Whether it passes on** (same ruling): a handler passes on if `next()` is called on
    **the `RoutingContext` it received**, wherever that happens: in its own body, in a method
    it hands the context to (Hono's `extractRequiredJsonPayload` → `extractRequiredJson` →
    `ctx.next()`), or in a lambda that captured it. This follows the call graph only along
    the edges that carry the context, and is computed **backwards**: once per module, each
    `passes_on` call site's receiver is walked to the parameters it came from with
    `producer_paths(along_receivers=True)`, and every handler whose context parameter is
    reached is a pass-through handler. A forward walk from every handler through everything
    it calls was rejected: it costs most of the module per handler, and it would count a
    `next()` on some other request's context.
  - The key names no framework type in the engine. Express's `next()` (JS, priority 3) has
    the same shape.
- **A route chain is a row only if at least one of its handlers answers**, meaning its body
  is in the module and does not call `next()`. The row's handler is that one. Two answering
  handlers on one chain (unusual) are two rows, each `narrowed` (the existing rule for
  several handler bodies).
- **Several chains with one `(verb, path)`** — Hono's two `router.post(TELEMETRY)` — are one
  wire identity. The middleware-only chain produces no row, and the answering chain produces
  the one row. `fluent`'s own dedup key includes the caller and the peer, so for an INBOUND
  row the builder dedups on `(verb, path, handler)` instead, wherever the chains were
  registered. Two different answering handlers on one `(verb, path)` stay two rows, each
  `narrowed`: Vert.x dispatches to whichever was registered first, and registration order
  across methods is not in the code.
- **The admitted incompleteness** (OI-143's rule: a structural rule, stated):
  - a handler that calls `next()` on one branch and answers on another is middleware here;
  - a path served only by a library handler (`StaticHandler`, a proxy) has no row.

  Both lose a row; neither invents one.

### 3c. Sub-routers — a prefix joined by the producer of the router (new, general)

`router.route("/api/*").subRouter(sub)` (4.5 and 5.0) and `router.mountSubRouter("/api", sub)`
(4.5) serve every route registered on `sub` under `/api`.

- **Which routes are `sub`'s** is a question of object identity. It is answered by the
  producer reader already built for Quartz's pairing (`values.producers_of`, the execute-join):
  - each route root's **receiver** is followed to the `Router.router(vertx)` call that built
    it;
  - the mount call's **router argument** is followed the same way;
  - routes whose receiver reaches the same object as a mount's argument take that mount's
    prefix.

  **Same object means the same producer reached along the same call path** (ruled
  2026-10-30, review issue 2), never merely the same `Router.router(vertx)` line. Both reads
  use `producer_paths`, which returns each producer with the path it was reached by, and
  the mount's prefix arguments are then read **within that path**
  (`resolve_positions(..., within=path)`, as Quartz's pairing reads a trigger's parts). A
  helper that builds and mounts a router per call —

  ```java
  Router createSubRouter(String mountPoint) {
      Router sub = Router.router(vertx);
      root.route("/" + mountPoint + "*").subRouter(sub);
      return sub;
  }
  ```

  — called as `createSubRouter("users")` and `createSubRouter("groups")` gives `/users/…`
  to the routes on the first router only. Reading the prefix without the path would answer
  `mountPoint` with every caller's argument and publish `/groups/:userUuid` at `resolved`;
  that is the mixing OI-222 fixed for fields, and the fixture pins against it.

  This crosses locals, parameters and fields: Hono builds its router in a base class and
  hands it to `addRoutes(router)`.
- **Nested mounts compose.** The prefix is `/api` from `/api/*` (the trailing `/*` is the
  mount wildcard) or the `mountSubRouter` string. It is joined by `leading_slash`, the rule
  Ktor and Javalin already use.
- **New catalog key:** `mount: [{ method: subRouter, router_arg: 0, prefix_from: receiver_path },
  { method: mountSubRouter, router_arg: 1, prefix_arg: 0 }]`, with `router_root` naming
  `Router.router`.
  - (My call: the engine reads "routes built on the object a mount call received take its
    prefix". The keys name the calls, as `job_root` and `pairing` do for Quartz.)
  - **Generalisation check:** Express's `app.use('/api', router)` is the same rule.
- **A router with no mount** is served as it is: `server.requestHandler(router)`, no prefix.
- **A mount whose argument is not a router this module builds** (a SockJS bridge, an
  OpenAPI-built router) adds no prefix to anything, and produces no row: those routes are not
  in the module.
- **One router mounted at several prefixes** — a helper that builds a router, called and
  mounted twice at `/v1` and `/v2` — is served under every one of them, so the route is one
  row per prefix, each **`resolved`**: every one is real ("enumerable is exact"). The join is
  per call path, through `producer_paths(along_receivers=True)` as Quartz's pairing does, so
  a route reached on caller A's path takes caller A's mount and never caller B's.
- **Where the producer is unreadable**, the route is published without a prefix and
  `partial`, with the path as read (my call; a NULL prefix would drop the route).

### 3d. Outbound — catalog `vertx-webclient.yml`, style `fluent`, direction `outbound`

This is the shape `ktor-client.yml` and `spring-webclient.yml` already ship.

- **Roots** (owner `io.vertx.ext.web.client.WebClient`):
  - each verb method, with `http_method` preset;
  - `request(HttpMethod, …)`, with the verb through `verb_values.fields`.
  - **Captures by form:**
    - `(uri)` → `url`;
    - `(host, uri)` → `peer` + `url`;
    - `(port, host, uri)` → `port` + `peer` + `url`;
    - `xAbs(url)` → the whole address, split by the existing `split_url`.
  - The `UriTemplate` forms read the template through `UriTemplate.of(String)` (an identity
    entry). Its `{var}` holes stay holes, as named path variables already do.
  - The `SocketAddress` and `RequestOptions` forms are roots with no address capture, and
    derive a row only where a later `uri(…)` step names one. Otherwise they are `partial` with
    the path unread.
- **Steps:** `method(HttpMethod)`, `uri(String)`, `host(String)`, `port(int)` refine; `putHeader`
  feeds `endpoint_metadata` and `addQueryParam`/`setQueryParam` feed the query parameters,
  both through the `collects` step key `spring-webclient.yml` already uses
  (`{ kind: header | query, name: arg0, value: arg1 }`); `as(BodyCodec)` passes through.
- **Terminals:** every `send*`.
  - `sendJson(obj)`, `sendJsonObject(obj)` and `sendBuffer(b)` capture `body: arg0`.
  - `sendForm`/`sendMultipartForm`/`sendStream` carry no body shape (my call: a form or a
    stream has no contract type to publish).
- **The client's base address is NOT read** (my call, after the builder check).
  `WebClientOptions.setDefaultHost/Port` is an options object handed to `create`, which
  `client_base` (a lambda block to one URL setter) does not model; the corpora use it once
  (Hono). A request naming no host has `peer` NULL, the row otherwise as read. Stated (§4).
- **A request built in a helper and sent by its caller** — Hono's
  `newQueryRequest(query).send()` — needs one engine change: `fluent` today crosses methods
  only through an argument (`terminal_via_argument`), so a `send()` whose RECEIVER is a
  helper's return is never reached. The terminal side walks back along receivers across
  methods with `producer_paths(along_receivers=True)`, the reader `scheduled_chain` already
  uses — a general `fluent` capability, not a Vert.x one.

### 3e. RxJava 3 and Mutiny

`io.vertx.rxjava3.ext.web.*` and `io.vertx.mutiny.ext.web.*` are generated wrappers with the
same method names. **If CP-56 confirms the names**, each is another `owner` in the same two
catalogs, with its own descriptors: `javalin.yml`'s "one library, three names". RxJava's
`rxSend()` and Mutiny's `sendAndAwait()` / `send()` returning `Uni` are terminals of the same
kind. (My call. If the probe finds a shape difference, that wrapper becomes a stated
boundary instead.)

### 3f. Fixture `fixtures/orders-vertx-web` (GUIDELINES §4.1: failing first)

Java, Vert.x 5.0.0 (the newer API; my call — 4.5's extra `mountSubRouter` is pinned by a unit
test instead).

| Shape | Expected rows |
|---|---|
| `router.get("/orders").handler(this::list)` and `router.post("/orders").handler(this::create)` | two rows |
| `router.route(HttpMethod.PUT, "/orders/:id").handler(…)` | one row, verb from the constant |
| `router.route("/orders/:id").method(GET).method(DELETE).handler(…)` | two rows |
| `router.get("/health").respond(ctx -> Future.succeededFuture(status))` | one row |
| Hono's pair: `router.post(EVENTS).handler(auth).handler(BodyHandler.create())` then `router.post(EVENTS).handler(this::ingest)` | one row, handler `ingest` |
| An in-module `assertTenant` that calls `ctx.next()`, as the only handler of a `route("/t/*")` | no row |
| Hono's `put(p).handler(this::extractJson).handler(this::update)`, where `extractJson` hands `ctx` to a helper that calls `ctx.next()` | one row, handler `update`, `resolved` |
| An answering handler that hands `ctx` to a helper and the helper replies | that handler's row |
| A `next()` inside a lambda that captured `ctx` (`auth.authenticate(c).onSuccess(u -> ctx.next())`) | no row for that handler |
| Hono's `route(p).handler(createCorsHandler(origin))`, a module method returning a library `CorsHandler` | no row |
| `router.route().handler(BodyHandler.create())` | no row |
| A sub-router built in `ApiRoutes.build(vertx)` and mounted as `root.route("/api/*").subRouter(api)` | its routes under `/api` |
| `router.getWithRegex("\\/files\\/.+")` | one row, path the regex |
| A path constant `static final String`, and a `String.format("/a/:%s", P)` | resolved through the walk |
| `client.get(8080, "inventory", "/stock/" + sku).send()` | outbound `GET` `/stock/{…}`, peer `inventory` |
| `client.postAbs("http://billing/charges").sendJson(charge)` | outbound `POST`, body `Charge` |
| A request built in `newRequest()` and sent by its caller | one outbound row |
| `WebClient.create(vertx, new WebClientOptions().setDefaultHost("search"))` then `client.get("/q").send()` | `GET /q`, peer NULL (the stated boundary) |
| A router built by `v(vertx)` and mounted at `/v1` and `/v2` | its routes under both, each `resolved` |
| `createSubRouter(name)` building and mounting a router at `"/" + name`, called for `users` and `groups`, each getting its own routes | each route under its own prefix only; no `/groups/:userUuid` |

Pinned by an e2e intention test, `tests/e2e/test_rest_inbound_delivered.py` and
`…outbound…`, beside the Ktor and Javalin ones.

## 4. What it does NOT do (stated boundaries)

Each is a **stated boundary row** under the Vert.x Web or Vert.x WebClient line in COVERAGE
§5.1/§5.2, as Quartz's five are — not a new line on `scripts/coverage_matrix.py`'s target
list, so it does not hold either line below `✅`. The tier says what closing it would take.

| Shape | Why | Tier |
|---|---|---|
| **Routes from an OpenAPI file** (`RouterBuilder`, vertx-web-openapi(-router)) — Strimzi, 9 examples | The verb and path are in `openapi.json`/`.yaml`, not in a call; the code only names an `operationId`. Reading it is a document reader, a capability of its own | B |
| **Routes registered through an in-house wrapper library** (Mesh's `InternalEndpointRoute`) | The `Router` calls are inside a jar Sextant does not read; the module only calls the wrapper | C |
| **Vert.x core `HttpClient`** (`vertx.createHttpClient().request(GET, port, host, uri).compose(req -> req.send())`) | A different API whose send sits inside a lambda passed to `compose`. It shares the address forms and would be a catalog of its own | B |
| **A path served only by a library handler** (`StaticHandler`, `ProxyHandler`) | §3b: nothing in the module answers | C |
| **A handler that calls `next()` on one branch** | §3b: read as middleware | C |
| **The request body an inbound handler reads** (`ctx.body().asPojo(T.class)`, `ctx.body().asJsonObject()`) | No request contract on a Vert.x row in v1; the row's `request_shape` is NULL. `respond`'s `Future<T>` gives a response shape where the existing shape pass reads a handler's return type, else NULL (the builder settles which; no new shape rule) | B |
| **`failureHandler`, `errorHandler(int, …)`** | Error handling, not routes; `error_handlers` has no Vert.x catalog | A |
| **Kotlin coroutine helpers** (`coHandler`, `coRespond`, `coAwait`) | Extension functions in `vertx-lang-kotlin-coroutines` wrap the handler. A plain Kotlin `router.get("/x").handler { }` is the same bytecode as Java's and is covered | A |
| **SockJS, the event-bus bridge, WebSockets on a Vert.x `HttpServer`** | Not on the Vert.x target list for those columns | — |
| **A regex path, for linking** | §3a: published verbatim at `partial` and never matched to another module's literal path | — |
| **`WebClientOptions.setDefaultHost/Port`** | §3d: the options object's host is not read; such a row's `peer` is NULL | A |

## 5. Cost (§8.7)

- **Inbound:** one fluent pass over the module's `Router` roots, as for the event-bus chain.
- **The pass-through check:** one backward producer walk per `passes_on` call site in the
  module, done once and cached (Hono: 6 `next()` calls, each a few methods deep), plus one
  producer read per handler argument to find the object it runs. Never a forward walk from
  each handler.
- **The mount join:** one producer-reader read per route root receiver, plus one per mount
  argument. That is bounded by the number of routes: Hono has ~40, the largest example ~30.
  Each read shares the cached `value_index`.
- **Outbound:** the fluent walk already priced for Ktor's client.

`measure_value_walk.py` is re-run, and the six field pins must hold.

## 6. Predictions — to verify, not to trust

- **The fixture:** every row in §3f.
- **vertx-examples `web-examples`:**
  - every `router.verb("…").handler(…)` whose handler is in the module is a row;
  - the SockJS mounts add none;
  - the OpenAPI examples add none (§4).
- **Hono's HTTP adapter:**
  - telemetry and event: `POST /telemetry`, `PUT` on the regex, `POST /event`, `PUT` on the
    regex, each with its answering handler;
  - command routes likewise;
  - no CORS-only or auth-only rows.
- **Strimzi:** no inbound rows; the document names the OpenAPI boundary.
- **Mesh:** rows only for its 26 direct `route("…")` chains with an in-module answering
  handler, under any module-built sub-router's prefix.

The pinned field corpora have no Vert.x Web, so they must not move.

**Coverage after:**
- §5.1 Vert.x Web `✅` and §5.2 Vert.x WebClient `✅`, each with §4's stated boundary rows.
- **Camel** is still on `scripts/coverage_matrix.py`'s target list although ruled out of
  scope on 2026-10-26. Taking it off is a one-line change made in this work, so REST out
  reads `✅`.

## 7. Left to the builder

- **The exact `all_methods` list and the wrapper descriptors:** CP-56 decides them.
- **Engine placement.** Whether `passes_on`, `repeats` and `mount` live in `engines/fluent.py` or in
  `shapes/` beside `chains.py`. Neither may name a Vert.x type (the catalog does).
- **Whether `respond`'s `Future<T>` reaches a response shape** through the existing handler
  shape pass, or stays NULL and stated.
- **Kotlin:** whether the fixture also gets a Kotlin twin, as the Ktor fixtures did.
