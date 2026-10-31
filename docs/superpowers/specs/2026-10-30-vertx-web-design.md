# Vert.x Web and WebClient — design

**Status: DRAFT 2026-10-30; reviewed 2026-10-30 (three user rulings: §3a item 5, §3b, §3c);
self- and adversarial review 2026-10-31 (§8), every finding resolved below.** On
2026-10-31 the user delegated the remaining rulings for Vert.x only: *"fix the issues
yourself … continue on with the spec, plan and subagent driven execution. but only for
vert.x."* Each ruling taken under that delegation is marked **[ruled 2026-10-31, my call]**
and is listed in §8 for the user's review when Vert.x is done.

Java/Kotlin framework order 3 (`docs/COVERAGE.md` "Priority order"). Moves two COVERAGE
lines: §5.1's **Vert.x Web** (`◐ 0/1`, tier B) and §5.2's **Vert.x WebClient** (`✗`, no
row). The §2c Vert.x family row goes from `◐ (1 not shipped) | ✗ | … | ✅` to
`✅ | ✅ | … | ✅`. The language-level REST in cell stays `◐`, because Spring Data REST, Servlet
and Akka HTTP each still hold one tier-C row.

## 1. What this is for, and what it narrows

A Vert.x service's architecture document should show the HTTP routes it serves and the
HTTP calls it makes, exactly as it does for a Spring, Quarkus, Micronaut, Ktor or Javalin
service. Today a Vert.x Web module shows **no** inbound HTTP rows and **no** outbound HTTP
rows. Only its event-bus traffic appears, because `vertx-eventbus*.yml` already ship.

**Success:** every route a Vert.x `Router` serves is one inbound row per wire identity, with
Vert.x's verb, path and the handler that answers. Every `WebClient` request the module
builds and sends is one outbound row, with verb, address (the client's configured base
included) and body. Nothing is published that Vert.x would not serve or send, and nothing
that Vert.x would refuse to register.

**Anti-goals:**
- **No row for middleware.** An auth, body, CORS or logging handler on a route is not an
  endpoint, and must not read as one.
- **No path invented by joining a prefix to a router it was never mounted on, and no child
  path published bare when it is mounted under a prefix we could not read.**
- **No Vert.x-specific engine.** The work reuses the shared chain walk, value walk and
  producer reader (ruling 6 of the Quartz design, *"call chains are the same, assignments are
  the same … the different pieces should connect"*). Every engine change in §3g is named
  for what it does, and names no Vert.x type.

**The narrowing, measured per production corpus [ruled 2026-10-31, my call].** The three
production corpora of §2b put most of their HTTP surface somewhere this work does not read:

| Corpus | Inbound routes | Where they are | Rows this work gives |
|---|---|---|---|
| Strimzi bridge | all | `openapi.json` via `RouterBuilder` | none — §4 row 1 (an OpenAPI document reader, tier B) |
| Mesh `core` | mostly through `InternalEndpointRoute` | another Maven module's jar | its direct `route("…")` chains only; the monitoring routes as `<prefix>/status` etc. (§3c) |
| Hono adapters | constant and regex routes; helpers in `service-base` | the adapter module, with pass-through decided in a dependency | every route, regex ones as patterns (§3a), out-of-module pass-through at `partial` (§3b) |
| Hono WebClient | one production call | `adapter-base`, client from an options object | one row, host from the options object (§3d) |

The yield the build measures is stated in §6 and checked at the end; the ✅ is claimed for
the shapes Vert.x Web's own API declares, with §4's rows standing beside it. Both cross-module
gaps (Mesh's wrapper, Hono's `service-base`) are one capability — reading a sibling module's
bytecode — logged as **OI-253**, not built here.

## 2. Measured first

### 2a. The API (to be pinned by probe CP-56)

`javap` over `io.vertx:vertx-web` and `vertx-web-client` **4.5.10** and **5.0.0**, read
2026-10-30 and re-read 2026-10-31 (`javap -c -p`). The probe adds the corpora's newest line,
**5.2.x**.

**`Router`** (`io.vertx.ext.web.Router`):
- `static router(Vertx)`; the implementation `RouterImpl` is also constructed directly
  (`new RouterImpl(vertx)`, Mesh);
- `route()`, `route(String)`, `route(HttpMethod, String)`, `routeWithRegex(String)`,
  `routeWithRegex(HttpMethod, String)`;
- for each of `get post put delete patch head options trace connect`: `x()`, `x(String)` and
  `xWithRegex(String)`.
- **4.5 only:** `mountSubRouter(String, Router)`.

**`Route`** (`io.vertx.ext.web.Route`): every builder method returns `this`. The probe lists
them all (the 2026-10-31 read: `method`, `path`, `pathRegex`, `produces`, `consumes`,
`virtualHost`, `order`, `last`, `setName`, `useNormalizedPath`, `putMetadata`, `handler`,
`blockingHandler` ×2, `respond`, `failureHandler`, `subRouter`, `disable`, `enable`,
`remove`, …). `RouteState`: an empty method set matches **any** method; a null path matches
**any** path. `RouteImpl.checkPath` throws for a path that is empty or lacks a leading `/`;
`subRouter` throws on an exact (non-wildcard) path and on a regex path; 4.5's
`mountSubRouter` throws when its mount point ends with `*`.

**`WebClient`** (`io.vertx.ext.web.client.WebClient`):
- `create(Vertx[, WebClientOptions[, PoolOptions]])`, `wrap(HttpClient[, WebClientOptions])`;
- per verb `get post put delete patch head`, each returning `HttpRequest<Buffer>`:
  - `x(String uri)`, `x(String host, String uri)`, `x(int port, String host, String uri)`;
  - each of those again taking `UriTemplate` instead of `String uri`;
  - `xAbs(String url)` and `xAbs(UriTemplate)`;
- `request(HttpMethod, …)` with the same address forms, plus `SocketAddress` and
  `RequestOptions` forms, and `requestAbs(HttpMethod, …)`.

**`HttpRequest<T>`** (`HttpRequestImpl`): 24 methods return `this` (`as` included:
`putfield codec; aload_0; areturn`), among them `method`, `uri`, `host`, `port`, `ssl`,
`putHeader`, `addQueryParam`, `setQueryParam`, `setTemplateParam`, `timeout`,
`basicAuthentication`, `bearerTokenAuthentication`, `followRedirects`, `expect`. Terminals
`send()`, `sendJson(Object)`, `sendJsonObject(JsonObject)`, `sendBuffer(Buffer)`,
`sendForm(MultiMap[, String])`, `sendMultipartForm(…)`, `sendStream(…)`. 4.5 has each with
and without a trailing callback; 5.0 has the `Future` forms only.

**`WebClientOptions`**: `setDefaultHost(String)`, `setDefaultPort(int)`, `setSsl(boolean)`,
each returning `this`. The probe records where `HttpRequestImpl` takes the default host and
port (a request naming its own host or port keeps it).

**`HttpMethod`** (vertx-core) is a class with **31** static constants and
`valueOf(String)` for any other token; it is not an enum, so the set a route with no verb
serves is open (§3a).

The probe must also record:
- whether `io.vertx.rxjava3.ext.web.*` and `io.vertx.mutiny.ext.web.*` declare the same
  names, and their descriptors — Mutiny's `Route.handler` takes `java.util.function.Consumer`
  and its `RoutingContext.next()` is on `io.vertx.mutiny.ext.web.RoutingContext` (§3e);
- how javac compiles `router.get("/x").handler(this::h)` and a lambda handler;
- the full self-returning method list of `Route`, `HttpRequest` and `WebClientOptions`, per
  owner and version.

### 2b. Corpora (pulled 2026-10-30, shallow, into `examples/`), measured PER MAVEN MODULE

| Corpus | Commit | Vert.x | What its main code does |
|---|---|---|---|
| `vert-x3/vertx-examples` | `091b03f` | 5.x | The official shapes. 66 files use Vert.x Web: 121 `verb("…")` routes, 43 `route()`, 32 `route("…")` (12 of them verbless with an answering handler), 11 `subRouter` (most mount a SockJS bridge or an OpenAPI-built router), 29 `WebClient.create`, 24 `client.verb(port, host, uri)`, 3 `*Abs`, 29 `send*`, 12 RxJava, 9 Kotlin coroutine, 9 `RouterBuilder`. **7 servers' only route is `router.route().handler(…)` answering** (`helloworld/Server.java:22-24`, `blockinghandler`, `templating/rocker`, `sessions`, the rxjava-2/3 hello worlds) |
| `strimzi/strimzi-kafka-bridge` | `d55d42b` | 5.2.2 | Routes come from `src/main/resources/openapi.json` through `RouterBuilder` (`routerBuilder.getRoute(operationId).addHandler(h)`); no `router.verb(…)` route |
| `eclipse-hono/hono` | `e1c98be` | per its build | `adapters/http-base`: `VertxBasedHttpProtocolAdapter` registers `router.post(ROUTE_TELEMETRY_ENDPOINT).handler(this::handlePostTelemetry)`, the same verb and path twice (once with auth and body handlers, once answering), `putWithRegex("\\/telemetry\\/.+")` answering routes, `String.format` paths; ONE `next()` call in the module (`:415`). The match-all route's lambda hands `ctx` to `HttpUtils.nextRoute(ctx)` in **`service-base`**, another module (`AbstractVertxBasedHttpProtocolAdapter.java:287-299`). `services/device-registry-base` registers routes whose handlers (`extractRequiredJson…`, `createDefaultCorsHandler`) are inherited from `service-base` (`AbstractHttpEndpoint.java:130-190, 357-390`). `adapters/sigfox`, `lora` register routes on a router built in `http-base`. `adapter-base`: the one production `WebClient` call, `client.post(QUERY_URI).addQueryParam(…)` then `timeout`, `basicAuthentication`, `return request.as(BodyCodec.jsonObject())` (`PrometheusBasedAsyncCacheLoader.java:148-164`), the client built from `WebClientOptions` whose host comes from `config.getHost()` (`AbstractProtocolAdapterApplication.java:639-647`) |
| `gentics/mesh` | `315fc22` | 5.1.5 | Most routes go through Mesh's own wrapper (`InternalEndpointRoute`, in `mesh/common`, called from `mesh/core`). Direct: 26 `route("…")`, 12 `subRouter`. `MonitoringRoutes.java:54-59` builds routers with `new RouterImpl(vertx)` and mounts `apiRouter` at each element of `VersionUtils.generateVersionMountpoints()` (another module, an `IntStream` mapped to strings) inside a `forEach` lambda; its routes `/status`, `/health/live`, … answer in-module |
| `quarkus-quickstarts` | — | Quarkus 3.x | `@Observes Router router` (`reactive-routes-quickstart/MyRouteRegistar.java:11-12`, `vertx-quickstart/SockJsExample.java:20`): the CDI-provided root router; `ResourceUsingWebClient.java` builds a `WebClient` from `WebClientOptions().setDefaultHost(…)`. `quarkus-vertx-http` pulls vertx-web, so this catalog activates on every Quarkus HTTP module |

`setDefaultHost/Port` appear in 4 main-code files (Hono `adapter-base`, Hono's client
example, a Mesh test, the Quarkus quickstart).

**What the corpora say about the design:**
- **Several routes, one identity, is the common production shape, not a corner** (Hono).
  Vert.x runs every matching route in order, and a handler that calls `ctx.next()` passes
  the request on. So the route that answers is not always the first one registered.
- **Constant, computed and regex paths dominate** (Hono). The value walk, not a literal-only
  reader, has to read the path, and a regex is a real answering route.
- **Pass-through is often decided outside the module** (Hono's `service-base`). The rule
  needs a third outcome, "not readable here" (§3b).
- **A router is often built or provided outside the module** (Quarkus, Hono's adapters).
- **Two real route sources are outside the code's calls:** an OpenAPI file read by
  `RouterBuilder`, and an in-house wrapper library. Both are stated boundaries (§4).

## 3. The design

### 3a. Inbound — catalog `vertx-web.yml`, style `fluent`, direction `inbound`

This is the shape `vertx-eventbus-chain.yml` already ships: a root call that names the
address, steps that refine it, and a terminal that names the handler.

**Why `fluent` and not `combinator` (my call, after the builder check).** `combinator` folds
one *tree* of calls — Ktor's nested `route { get { } }`, Spring's `route().GET(…)`. A Vert.x
router is not a tree: each route is its own statement on a shared `Router` object, joined to
a mount only by object identity (§3c), which is a per-chain walk plus the producer reader.
So routes stay on `fluent`, and `fluent` gains the general features listed in §3g.

**A call that returns its own receiver configures it** (user ruling 2026-10-30, review issue
3; **built** by object-identity ruling 4, PR #80, in both the forward and the backward walk).
This work adds only catalog flags: **every** method `javap` shows returning `this` on
`Route`, `HttpRequest` and `WebClientOptions` (§2a's list, per owner and version) is a
`returns_receiver` step, capture-less where it carries nothing — not a hand-picked subset
[ruled 2026-10-31, my call: an unflagged self-returning call in statement style forks the
chain (`shapes/chains.py:1031-1033`) and, on the backward walk, answers `escapes`
(`values.py:1971`), so Hono's `failureHandler`-before-`handler` route and its
`timeout`/`basicAuthentication`/`as` request would lose their rows]. The same flags go on
`vertx-eventbus-chain.yml`'s self-returning `MessageConsumer` calls, which ruling 4 did not
flag. (Ktor has nothing to flag: every step `ktor-client.yml` declares returns `void`.)
Without them, the Vert.x docs' own style —

```java
Route route = router.route("/orders/:id");
route.method(HttpMethod.GET);
route.handler(this::readOrder);
```

— is two forks of one root. With them it is one chain. One-statement chains are unchanged.

- **Roots** (owner `io.vertx.ext.web.Router`, and the wrapper owners of §3e):
  - each `x(String)` with `http_method: X`;
  - `route(HttpMethod, String)`, with the verb captured through `verb_values.fields`;
  - `route(String)`;
  - the `…WithRegex` forms, each capturing the path as a **pattern** (below);
  - the argument-less forms (`route()`, `get()`), so that a later `.path(…)` / `.method(…)`
    step can supply what they lack.
- **Steps:**
  - `method(HttpMethod)` adds a verb (accumulating, §3g item 1);
  - `path(String)` sets the path, `pathRegex(String)` sets it as a pattern;
  - `produces` / `consumes` add media, as the media columns already carry for Spring;
  - `virtualHost(String)` is a requirement on the row (`endpoint_metadata`, kind `host`),
    because it restricts which `Host` the route serves [ruled 2026-10-31, my call];
  - `order(int)` and `last()` are captured for §3b's ordering only;
  - `disable()` and `remove()` end the chain with **no row**: Vert.x serves nothing for a
    disabled or removed route (DR-6). `enable()` after `disable()` restores it (last wins);
  - every other self-returning call (`setName`, `useNormalizedPath`, `putMetadata`, …) is a
    capture-less `returns_receiver` step.
- **Terminals** — `handler`, `blockingHandler`, `respond`, each capturing `handler: arg0`,
  accumulating in call order (`.handler(auth).handler(body).handler(this::h)` is three
  handlers on one route). `failureHandler` is a capture-less step, not a terminal (§4).
- **A route with no verb serves any verb, and is ONE row with method NULL** [ruled
  2026-10-31, my call]. Vert.x's set is open (31 declared constants plus `valueOf`), so a
  fan-out to a list would publish a closed answer for an open set (enumerable-is-exact) and
  silently omit the rest. The precedent is the Spring functional router's verbless route
  (`dsl-media-route`): one row, method NULL. **The same Vert.x dispatcher backs Quarkus
  Reactive Routes**, whose catalog fans a `@Route` with no `methods` out to 6 verbs
  (`quarkus-reactive-routes.yml:48-50`) while its own comment says Vert.x registers it for
  any method; DR-6 allows one framework one behaviour, so that catalog moves to the same
  one-row rule in this work, and its goldens move with a stated reason. **"Any method" is
  said explicitly, never by NULL alone**: `stitch/links.py` (`_verb`) reads a NULL method as
  "nobody read the verb" and deliberately links it to no verb, and a row is identified by
  what it is, not by an absent value. So the row carries an **any-method marker** (stored
  where §3g item 3's path kind is stored), and the linker matches an outbound call of any
  verb to an inbound row with that marker on the same path; a plain NULL-method row keeps
  today's meaning and today's linking.
- **A route with no path serves any path.** Its row's path is `/*`, Vert.x's own spelling of
  "every path" (`route("/*")` is the same route) [ruled 2026-10-31, my call, replacing the
  draft's "no path, no row" — that rule dropped the official hello world and six other
  example servers]. Middleware is kept out by §3b, not by the absence of a path:
  `router.route().handler(BodyHandler.create())` passes on, so it is no row.
- **Paths are published as written, and as Vert.x would accept them:**
  - `/orders/:id` keeps Vert.x's `:id`, which `_path_variables` already reads as a path
    variable (`test_request_requirements.py`, "colon");
  - `/static/*` keeps its `*`;
  - **a path Vert.x refuses to register** — empty, or not starting with `/` — is an error, as
    DR-6 requires where the framework raises: no row, and the declaration is recorded the
    way other refused declarations are. `canonical_http_path`'s leading-slash repair
    (`domain/paths.py:82-87`) is NOT applied to a Vert.x route; the catalog declares that
    Vert.x refuses rather than repairs (catalog data, the `path_separator` precedent).
  - **a regex route's path is the regex verbatim, `resolved`, and marked as a pattern**
    [ruled 2026-10-31, my call]. The regex is read exactly, so its resolution is
    `resolved`; what differs is what the path IS, so that goes on the row as data (a path
    kind), never in the trust column. A pattern path is **not canonicalised**
    (`engines/fluent.py:474` today canonicalises every inbound path, which would turn
    `\/telemetry\/.+` into `/\/telemetry\/.+`) and **not linked by path**. The draft's
    `partial` is withdrawn. `quarkus-reactive-routes.yml`'s `@Route(regex = …)`, which
    derives nothing today, publishes the same pattern row, for the same dispatcher.
- **Request requirements** — `RoutingContext.queryParam(String)`, `pathParam(String)`
  (skipping the route's own path variables) and `request().getHeader(String)` (`via` the
  producing `request()` call) — are `request_reads` entries, the mechanism `javalin.yml`
  already ships (catalog data only; it fills the COVERAGE line that reads "Not recorded").

### 3b. Which handler answers — a route chain's pass-through rule (new, general)

Vert.x calls a route's handlers in order, then the next matching route's, for as long as
each handler calls `RoutingContext.next()`. **A handler whose body calls `next()` on the
context it received passes the request on; it is middleware.** (DR-6: Vert.x's own dispatch
rule, not ours.)

- **New catalog key on the `fluent` style:**
  `passes_on: [{ owner: io.vertx.ext.web.RoutingContext, method: next }, …]` — a LIST, one
  entry per owner (the Mutiny and Rx3 `RoutingContext`s, §3e). (Not `pass_through`, which
  `combinator` already uses for a filter step that carries a chain on.) The key names no
  framework type in the engine; Express's `next()` has the same shape.
- **Which code a handler runs** (user ruling 2026-10-30, review issue 1): Vert.x calls
  `handle(ctx)` on the object passed, so the handler argument is followed to that object
  with the producer reader. `this::h` runs `h`, a lambda its own synthetic body, `new X(…)`
  `X.handle`, and a field, local or factory call the object it holds or returns.
- **Three outcomes, not two** [ruled 2026-10-31, my call]:
  1. **passes on** — `next()` is reached on the context the handler received: in its own
     body, in a module method it hands the context to, or in a lambda that captured it; or
     the handler is an object of a **Vert.x** class (`BodyHandler`, `CorsHandler`,
     `AuthenticationHandler` — the owner prefix the catalog declares as the framework's own
     handlers), which by Vert.x's contract carry the request on or fail it;
  2. **answers** — the handler's body is in the module, and no `next()` is reachable on the
     received context along any path the module can see, and the context never leaves the
     module;
  3. **not readable here** — the context is handed to a method whose body is outside the
     module (Hono's `HttpUtils.nextRoute(ctx)` in `service-base`), or the handler object is
     produced outside the module and is not a framework handler (Hono's inherited
     `createDefaultCorsHandler()`). Calls ON the context (`ctx.response().end()`,
     `ctx.fail(…)`) do not count: they are the framework's API, and only `next` passes on.
- **Computing it — backwards, once per module.** Each `passes_on` call site's receiver is
  walked back to where it came from with the producer reader. This needs one **reader
  extension**: the walk's end must name the `(method, parameter index)` it reached when it
  stops at a parameter, so a handler whose context parameter is reached is known; today
  `producer_paths` answers `Producer(reason="external")` there and its `Path` is opaque
  (`values.py:991-995, 1058-1060`). The "context leaves the module" test is the forward
  question "is the received context passed as an argument to an out-of-module method", read
  from the handler's own call sites and those of the module methods it hands the context to
  — the same edges the backward walk follows, recorded once. A forward walk from every
  handler through everything it calls was rejected: it costs most of the module per
  handler, and it would count a `next()` on some other request's context.
- **Which handler answers on a chain.** Vert.x runs a chain's handlers in order and stops at
  the first that does not pass on; later handlers on that chain never run. So the chain's
  answering handler is the **first** handler that answers or is not readable here. A chain
  whose handlers all pass on is middleware: no row.
- **Several chains with one `(verb, path)`** — Hono's two `router.post(TELEMETRY)` — are one
  wire identity. Vert.x tries them in registration order (or by `order(int)`, with `last()`
  last). Registration order is the call order, and **within one method body that is the
  ordinal order of the root calls** — exact. So:
  - the middleware-only chain gives no row, and the first chain with an answering (or
    not-readable) handler gives the one row, `resolved`;
  - where the candidate chains are registered in **different methods** and no `order(int)`
    settles them, the order is not in the code: each candidate is a row, `narrowed` (one of
    them answers; we cannot say which — the word's proper use);
  - `order(int)` with literal values orders the chains by value, as Vert.x does.
- **The row's resolution.** An answering handler gives `resolved`. A **not-readable-here**
  handler gives `partial`, with the reason naming the out-of-module method or producer
  ("whether `HttpUtils.nextRoute` passes on is decided in a module this analysis does not
  read") [ruled 2026-10-31, my call: the handler's identity is read exactly, its outcome is
  not; dropping the row would lose most of Hono, and calling it `resolved` would assert a
  dispatch outcome nothing read]. A `/*` any-path row from a not-readable handler (Hono's
  match-all) is therefore `partial` and, being `/*`, links to nothing by path.
- **Dedup — by semantics, for every inbound fluent row** [ruled 2026-10-31, my call]. An
  inbound row's wire identity does not depend on which method registered it, so the
  inbound dedup key is `(protocol, verb, path, handler)`, for the event-bus chain too (two
  consumers of one address with one handler are one consumer twice; different handlers stay
  two rows). If any event-bus golden moves, the plan says which row and why; the key is not
  chosen to keep goldens still. The SQL guard (`derive_call_endpoints.sql:125-132`) is
  brought to the same key.
- **The admitted incompleteness** (OI-143's rule: a structural rule, stated): a handler that
  calls `next()` on one branch and answers on another is middleware here (the request may
  be answered by it on the other branch). It loses a row; it never invents one.

### 3c. Sub-routers — a prefix joined by object identity (new, general)

`router.route("/api/*").subRouter(sub)` (4.5 and 5.0) and `router.mountSubRouter("/api", sub)`
(4.5) serve every route registered on `sub` under `/api`.

- **A router is identified by what it is: the object a producer made, reached along a call
  path** — never by which factory made it. Each route root's **receiver** is followed to its
  producer with `producer_paths`, whatever that producer is (`Router.router(vertx)`,
  `new RouterImpl(vertx)`, a wrapper's factory); no `router_root` list [ruled 2026-10-31, my
  call; the draft's `router_root: Router.router` missed Mesh's `new RouterImpl`]. The
  producer reader stops at a `declared` set of `(owner, method)`; that set is **derived from
  the facts by type** — every call site in the module whose descriptor returns the
  catalog's `router_type` (`io.vertx.ext.web.Router` and the wrapper types), and every
  constructor of a class the module's facts show implementing it — once per resolve, cached.
  A router handed in as a parameter with no caller in the module, or read from something
  outside, ends `external`: that is the "produced outside the module" case below.
- **Same object means the same producer reached along the same call path** (user ruling
  2026-10-30, review issue 2). The mount call's router argument is followed the same way,
  and routes whose receiver reaches the same producer on the same path take that mount's
  prefix. The mount's prefix arguments are read **within that path**
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
  to the routes on the first router only, never `/groups/:userUuid` (OI-222's mixing, which
  the fixture pins against). This crosses locals, parameters and fields: Hono builds its
  router in a base class and hands it to `addRoutes(router)`.
- **Nested mounts compose.** The prefix is the mount path with its trailing wildcard
  removed: `*`, and a `/` right before it, so `/api/*`, `/api*` and `"/" + name + "*"` all
  give `/api` or `/<name>`; or the `mountSubRouter` string. It is joined by `leading_slash`,
  the rule Ktor and Javalin already use. A mount Vert.x refuses (`subRouter` on an exact or
  regex path, 4.5 `mountSubRouter` with a trailing `*`) adds no prefix and is recorded as an
  error (DR-6).
- **New catalog keys:** `router_type: [io.vertx.ext.web.Router, …]` and
  `mount: [{ method: subRouter, router_arg: 0, prefix_from: receiver_path },
  { method: mountSubRouter, router_arg: 1, prefix_arg: 0 }]`. The engine reads "routes built
  on the object a mount call received take its prefix". **Generalisation check:** Express's
  `app.use('/api', router)` is the same rule.
- **One router mounted at several prefixes** — a helper called and mounted twice at `/v1`
  and `/v2` — is served under every one of them: one row per prefix, each **`resolved`**
  (enumerable is exact). The join is per call path, so a route reached on caller A's path
  takes caller A's mount and never caller B's.
- **Where the router is served without a mount it is served at its root, as read** — a router
  handed to `HttpServer.requestHandler`, a router this module builds and never mounts, and a
  router **produced outside the module** (Quarkus's `@Observes Router`, a router handed in
  from another module as Hono's sigfox/lora adapters receive theirs). Those rows are
  **`resolved`** [ruled 2026-10-31, my call, replacing the draft's `partial`]. The standing
  bound — *a router built outside this module may be mounted under a prefix this module
  cannot see, and Quarkus's `quarkus.http.root-path` is not applied* — is stated once, in
  the catalog and in COVERAGE, rather than downgrading every row (enumerable-is-exact's "say
  so as the standing bound").
- **A mount found, its prefix not read** — Mesh's `forEach` over a stream built in another
  module — publishes the route with a **named hole**: `<prefix>/status`, at `partial`, the
  reason naming the unread argument (trace-the-value rung 5: a placeholder says WHAT is
  missing, never a complete-looking path) [ruled 2026-10-31, my call]. A path holding a
  named hole is **never linked by path** (the `<host>` refusal, user decision 6, applied to
  a path segment); the builder adds that to `links.py`'s served index generally.
- **A mount whose argument is not a router this module builds** (a SockJS bridge, an
  OpenAPI-built router) adds no prefix to anything, and produces no row: those routes are not
  in the module.

### 3d. Outbound — catalog `vertx-webclient.yml`, style `fluent`, direction `outbound`

The cross-method walk back from a terminal along receivers is **built** (object-identity
ruling 5, PR #81, `shapes/chains.py`), and a value read per object and a value id with its
method are built (rulings 1 and 2, PRs #84 and #78). This catalog uses them.

- **Roots** (owner `io.vertx.ext.web.client.WebClient`):
  - each verb method, with `http_method` preset;
  - `request(HttpMethod, …)`, with the verb through `verb_values.fields`.
  - **Captures by form** (new `host`/`port` captures, §3g item 6):
    - `(uri)` → `url`;
    - `(host, uri)` → `host` + `url`;
    - `(port, host, uri)` → `port` + `host` + `url`;
    - `xAbs(url)` → the whole address, split by the existing `split_url`.
  - **One peer per call, whichever form** [ruled 2026-10-31, my call]: `peer` is `host`, or
    `host:port` where a port is stated, which is the authority `split_url` already gives an
    absolute URL (`getAbs("http://inventory:8080/…")` → `inventory:8080`). So
    `client.get(8080, "inventory", "/stock")` and `getAbs("http://inventory:8080/stock")`
    give the same peer. The probe confirms Vert.x composes them the same way (DR-6).
  - The `UriTemplate` forms read the template through `UriTemplate.of(String)` (an identity
    entry). Its `{var}` holes stay holes, as named path variables already do;
    `setTemplateParam` is a capture-less self-returning step (§4).
  - The `RequestOptions` form reads the options object the same way the client's options
    are read (below): `setHost`, `setPort`, `setURI` on that object. The `SocketAddress`
    form reads no address; it derives a row only where a later `uri(…)` step names one.
- **Steps:** `method(HttpMethod)`, `uri(String)`, `host(String)`, `port(int)` refine; `putHeader`
  feeds `endpoint_metadata` and `addQueryParam`/`setQueryParam` feed the query parameters,
  both through the `collects` step key `spring-webclient.yml` already uses
  (`{ kind: header | query, name: arg0, value: arg1 }`); every other self-returning method
  (`as`, `timeout`, `basicAuthentication`, …) is a capture-less `returns_receiver` step.
- **Terminals:** every `send*` (and the wrapper terminals, §3e).
  - `sendJson(obj)`, `sendJsonObject(obj)` and `sendBuffer(b)` capture `body: arg0`.
  - `sendForm`/`sendMultipartForm`/`sendStream` carry no body shape (my call: a form or a
    stream has no contract type to publish).
- **The client's base address IS read** [ruled 2026-10-31, my call, replacing the draft's
  "not read"]. A `WebClient` is configured by an **options object** handed to its factory:
  `WebClient.create(vertx, options)`. The request's receiver is followed to the factory with
  the producer reader (the Ktor client's route, `client-models/ktor.yml`), the factory's
  options argument is followed to its producer (`new WebClientOptions()`), and the
  configuring calls made **on that same object** — `setDefaultHost`, `setDefaultPort`,
  `setSsl` — are gathered by the backward walk's configuring-call reader
  (`values.producers_of(…, configuring=)`, ruling 4). Each value is then traced to its
  source as every value is: a literal, a resolved config value, or the config key where the
  chain leaves the repo (Hono's `config.getHost()`). This is a new rung shape in the
  `client_base` model, **an options-object rung** (`options_arg` plus the setters), beside
  Ktor's block rung — general, named for what it does, declared in a new
  `client-models/vertx-web.yml` [§3g item 7]. **The join is Vert.x's**: the default host and
  port fill a request that names none; a request naming its own host or port keeps it; an
  absolute (`*Abs`) request ignores both. The probe pins it against `HttpRequestImpl`.
  Where the options object is not reached, the row's peer is NULL, as Ktor's is.
- **A request built in a helper and sent by its caller** — Hono's
  `request = client.post(QUERY_URI)…; return request.as(…)` then `.send()` in the caller —
  is reached by ruling 5's walk, given the flags above.
- **A call to the module's own server** (the vertx-examples web-client modules start a server
  and call `localhost` in the same module): the self-call rule is built for gRPC only
  (OI-198). Named in §4 as that open issue; not built here.

### 3e. RxJava 3 and Mutiny

`io.vertx.rxjava3.ext.web.*` and `io.vertx.mutiny.ext.web.*` are generated wrappers with the
same method names. **If CP-56 confirms the names**, each is another `owner` in the same two
catalogs, with its own descriptors (`javalin.yml`'s "one library, three names"), and each
wrapper's `RoutingContext.next()` is another `passes_on` entry. RxJava's `rxSend()` and
Mutiny's `sendAndAwait()` / `send()` returning `Uni` are terminals of the same kind. (My
call. If the probe finds a shape difference — Mutiny's `Consumer`-taking `handler` is one to
check — that wrapper becomes a stated boundary instead.)

### 3f. Fixture `fixtures/orders-vertx-web` (GUIDELINES §4.1: failing first)

Java, Vert.x 5.0.0 (the newer API; my call — 4.5's extra `mountSubRouter` is pinned by a unit
test instead). **Two Maven modules** [ruled 2026-10-31, my call]: `orders-vertx-web` (the
module analysed) depends on a small `orders-vertx-web-base` jar holding the shapes Hono puts
in `service-base` — an inherited CORS-handler factory, a helper that calls `ctx.next()`, a
router built and handed in — so the fixture fails where Hono does.

| Shape | Expected rows |
|---|---|
| `router.get("/orders").handler(this::list)` and `router.post("/orders").handler(this::create)` | two rows |
| `router.route(HttpMethod.PUT, "/orders/:id").handler(…)` | one row, verb from the constant |
| `router.route("/orders/:id").method(GET).method(DELETE).handler(…)` | two rows |
| The same route as separate statements on a `Route` local, with `failureHandler(…)` and `setName(…)` between: `r.method(GET); r.failureHandler(…); r.method(DELETE); r.handler(…)` | the same two rows, no others |
| `router.route("/any").handler(this::any)` (no verb) | one row, method NULL, any-method marker |
| `router.route().handler(rc -> rc.response().end("hi"))` as a server's only route | one row, path `/*`, method NULL |
| `router.get("/health").respond(ctx -> Future.succeededFuture(status))` | one row |
| Hono's pair: `router.post(EVENTS).handler(auth).handler(BodyHandler.create())` then `router.post(EVENTS).handler(this::ingest)`, same method | one row, handler `ingest`, `resolved` |
| The same pair registered in two different methods, both answering | two rows, each `narrowed` |
| `.handler(this::a).handler(this::b)` where both answer | one row, handler `a` |
| An in-module `assertTenant` that calls `ctx.next()`, as the only handler of a `route("/t/*")` | no row |
| `put(p).handler(this::extractJson).handler(this::update)`, where `extractJson` hands `ctx` to an in-module helper that calls `ctx.next()` | one row, handler `update`, `resolved` |
| `put(p2).handler(this::check).handler(this::update)`, where `check` hands `ctx` to the base jar's helper that calls `next()` | one row, handler `check`, `partial`, reason naming the helper |
| An answering handler that hands `ctx` to an in-module helper and the helper replies | that handler's row, `resolved` |
| A `next()` inside a lambda that captured `ctx` (`auth.authenticate(c).onSuccess(u -> ctx.next())`) | no row for that handler |
| `route(p).handler(createCorsHandler(origin))`, an inherited base-jar method returning a library `CorsHandler`, as the only handler | no row: a framework handler passes on |
| `route(p).handler(baseFactory())`, a base-jar method returning a non-framework handler, as the only handler | one row, `partial` |
| `router.route().handler(BodyHandler.create())` | no row |
| `router.get("/gone").handler(this::g).disable()` | no row |
| `router.get("bad").handler(this::b)` (no leading `/`) | no row; recorded as refused |
| A sub-router built in `ApiRoutes.build(vertx)` and mounted as `root.route("/api/*").subRouter(api)` | its routes under `/api` |
| A router built with `new RouterImpl(vertx)` and mounted at `/m` | its routes under `/m` |
| A router mounted inside `prefixes.forEach(p -> root.route(p + "*").subRouter(r))` over a list from the base jar | its routes as `<prefix>/…`, `partial` |
| A router received from the base jar and given routes here | its routes at the root, `resolved` |
| `router.getWithRegex("\\/files\\/.+")` | one row, path the regex verbatim, `resolved`, marked a pattern, not canonicalised |
| `router.get("/v").virtualHost("api.example.com").handler(…)` | one row, host requirement in metadata |
| A path constant `static final String`, and a `String.format("/a/:%s", P)` | resolved through the walk |
| A handler reading `ctx.queryParam("q")` and `ctx.request().getHeader("X-T")` | query and header requirements on its row |
| `client.get(8080, "inventory", "/stock/" + sku).send()` | outbound `GET` `/stock/{…}`, peer `inventory:8080` |
| `client.postAbs("http://billing/charges").sendJson(charge)` | outbound `POST`, peer `billing`, body `Charge` |
| Hono's shape: a helper doing `r = client.post(Q).addQueryParam(…); r.timeout(…); r.basicAuthentication(…); return r.as(BodyCodec.jsonObject());`, sent by its caller | one outbound row |
| `WebClient.create(vertx, new WebClientOptions().setDefaultHost("search").setDefaultPort(9200))` then `client.get("/q").send()` | `GET /q`, peer `search:9200` |
| The same with the host from a config getter backed by `application.properties` | the configured value, or its key |
| A router built by `v(vertx)` and mounted at `/v1` and `/v2` | its routes under both, each `resolved` |
| `createSubRouter(name)` building and mounting a router at `"/" + name`, called for `users` and `groups`, each getting its own routes | each route under its own prefix only; no `/groups/:userUuid` |

Plus `quarkus-reactive-routes`'s existing fixture: its verbless `@Route` moves from 6 rows to
one NULL-method row, and a `@Route(regex = …)` gains its pattern row.

Pinned by e2e intention tests in `tests/e2e/test_rest_inbound_delivered.py` and the outbound
twin, beside the Ktor and Javalin ones.

### 3g. Engine changes, each general, each costed in §5

1. **Accumulating steps and terminals** — today every fluent capture is last-wins
   (`shapes/chains.py`), except a `collects` step, which accumulates `{kind, name, value}`
   entries. The builder first tries to express "this capture accumulates" by generalising
   `collects` (removing-the-cause); only if `collects`' entry shape cannot carry a verb list
   or a handler list does it add a per-capture `repeats: true`, and the plan says why.
2. **Verb fan-out and media for inbound fluent rows** — the combinator's media columns and
   `leading_slash` join are moved to a shared module and called from both engines, never
   copied. The verbless-route rule is now one NULL-method row (§3a), so `all_methods`
   fan-out is not needed by `fluent`; the SQL fan-out in `annotation_driven`
   (`derive_endpoints.sql`) stays where it is, for Spring's closed enum.
3. **Row markers** — a path kind (pattern) and an any-method marker, stored once, read by
   the canonicaliser and the linker; canonicalisation and path linking skip a pattern path.
4. **`passes_on`** and the reader extension (a walk end naming `(method, parameter index)`),
   the three outcomes, and chain/cross-chain ordering (§3b).
5. **`mount`** — the per-path prefix join through `producer_paths`, nested composition, the
   named-hole prefix (§3c).
6. **`host` and `port` captures** composed into one peer (§3d).
7. **The options-object `client_base` rung** (§3d).
8. **Linking**: an inbound row with the any-method marker matches any verb; a path holding a named hole is
   never linked by path; a pattern path is never linked by path (`stitch/links.py`).
9. **The inbound dedup key** (§3b) and its SQL twin.
10. **A refused path is recorded, not repaired** — a catalog flag that a framework refuses
    a path without a leading `/` (§3a).

## 4. What it does NOT do (stated boundaries)

Each is a **stated boundary row** under the Vert.x Web or Vert.x WebClient line in COVERAGE
§5.1/§5.2, as Quartz's five are — not a new line on `scripts/coverage_matrix.py`'s target
list. The tier says what closing it would take.

| Shape | Why | Tier |
|---|---|---|
| **Routes from an OpenAPI file** (`RouterBuilder`, vertx-web-openapi(-router)) — Strimzi, 9 examples | The verb and path are in `openapi.json`/`.yaml`, not in a call; the code only names an `operationId`. Reading it is a document reader, a capability of its own | B |
| **Routes registered through an in-house wrapper library**, and pass-through decided in a sibling module (Mesh's `InternalEndpointRoute`; Hono's `service-base`) | The calls are in another Maven module's jar, which a per-module analysis does not read; pass-through there gives `partial` rows (§3b). OI-253 | C |
| **A router mounted under a prefix outside the module, or Quarkus's `quarkus.http.root-path`** | §3c's standing bound; such rows are published at the root | B |
| **Vert.x core `HttpClient`** (`vertx.createHttpClient().request(GET, port, host, uri).compose(req -> req.send())`) | A different API whose send sits inside a lambda passed to `compose`. It shares the address forms and would be a catalog of its own | B |
| **A path served only by a library handler** (`StaticHandler`, `ProxyHandler`) | §3b: a framework handler passes on; nothing in the module answers | C |
| **A handler that calls `next()` on one branch** | §3b: read as middleware | C |
| **The request body an inbound handler reads** (`ctx.body().asPojo(T.class)`) | No request contract on a Vert.x row, as on Ktor's and Javalin's rows; `respond`'s `Future<T>` gives a response shape only where the existing shape pass reads a handler's return type | B |
| **`failureHandler`, `errorHandler(int, …)`** | Error handling, not routes; `error_handlers` has no Vert.x catalog | A |
| **Kotlin coroutine helpers** (`coHandler`, `coRespond`, `coAwait`) | Extension functions in `vertx-lang-kotlin-coroutines` wrap the handler. A plain Kotlin `router.get("/x").handler { }` is the same bytecode as Java's and is covered | A |
| **SockJS, the event-bus bridge, WebSockets on a Vert.x `HttpServer`** | Not on the Vert.x target list for those columns | — |
| **`setTemplateParam`** | A template hole filled per request; the hole stays a hole | A |
| **A WebClient call to the module's own server** | The self-call rule covers gRPC only (OI-198) | B |

## 5. Cost (§8.7)

Counts per resolve, on the largest Vert.x corpus module (Mesh `core`) and on a Quarkus HTTP
module (where the catalog activates because vertx-web is transitive). The plan's first task
times a baseline `module analyze` on both and on Hono `http-base`; the last task times them
again, and the delta is recorded in `docs/performance.md`.

- **Inbound fluent pass:** one pass over the module's `Router` roots, as for the event-bus
  chain — O(route roots), each walk bounded by its chain.
- **Pass-through:** one backward producer walk per `passes_on` call site (Hono `http-base`:
  1; a typical module: a handful), cached for the resolve; one producer read per handler
  argument (O(handlers)); the "context leaves the module" test reads the call sites of the
  methods those walks visited, already in hand. Never a forward walk per handler.
- **Mount join:** one `producer_paths` read per route-root receiver (O(routes): Hono ~40,
  the largest example ~30, Mesh's direct 26) plus one per mount argument (Mesh 12), each on
  the shared cached `value_index`; plus one `resolve_positions(within=)` per (mount, path)
  pair actually joined — bounded by routes × the prefixes reaching each, which the corpora
  put at 1–2. Nested mounts recurse once per nesting level.
- **Client base:** one producer read per client receiver (cached per producer) plus one
  configuring-call read per options object.
- **Quarkus modules:** the catalog activates but finds roots only where the module calls the
  `Router` API; with no roots, the pass reads nothing beyond the fluent pass's root lookup
  (the same indexed lookup every fluent catalog does).

`measure_value_walk.py` is re-run, and the six field pins must hold.

## 6. Predictions — to verify, not to trust

- **The fixture:** every row in §3f.
- **vertx-examples `web-examples`:** every `router.verb("…").handler(…)` whose handler is in
  the module is a row; the 7 hello-world-style servers are one `/*` row each; the SockJS
  mounts add none; the OpenAPI examples add none (§4).
- **Hono `adapters/http-base`:** `POST /telemetry`, `POST /event` and the command routes with
  their answering handlers; the `putWithRegex` routes as pattern rows; the match-all route
  one `/*` row at `partial` (its pass-through is in `service-base`); no CORS-only or
  auth-only rows.
- **Hono `services/device-registry-base`:** rows whose handlers are inherited from
  `service-base` at `partial`; CORS-only routes none.
- **Hono `adapter-base`:** one outbound row for the Prometheus query, its host the config
  key or value `config.getHost()` reaches.
- **Strimzi:** no inbound rows; the document names the OpenAPI boundary.
- **Mesh `core`:** rows for its direct `route("…")` chains with an answering handler; the
  monitoring routes as `<prefix>/status`, `<prefix>/health/live`, … at `partial`.
- **quarkus-quickstarts `reactive-routes-quickstart`:** the `@Observes Router` routes at the
  root, `resolved`.

Each prediction is measured on the real corpus before the coverage cell is claimed; a miss is
a finding for the per-item loop, not an edit to this list. The pinned field corpora have no
Vert.x Web, so they must not move.

**Coverage after:** §5.1 Vert.x Web `✅` and §5.2 Vert.x WebClient `✅`, each with §4's stated
boundary rows. (Camel's removal from `scripts/coverage_matrix.py`'s target list, ruled
2026-10-26, is a separate one-line commit, not part of this work.)

## 7. Left to the builder

- **The wrapper descriptors and self-returning method lists:** CP-56 decides them.
- **Engine placement.** Whether `passes_on`, accumulation and `mount` live in
  `engines/fluent.py` or in `shapes/` beside `chains.py`. None may name a Vert.x type.
- **Where the path kind lives** (a column, or an `endpoint_metadata` entry the canonicaliser
  and linker read), choosing the one that adds no per-row read.
- **Kotlin:** whether the fixture also gets a Kotlin twin, as the Ktor fixtures did.

## 8. Review record (2026-10-31)

A self-review against the user's rulings and an independent adversarial review against the
code, the Vert.x jars and the corpora (1 Critical, 10 Major, 18 Minor). Every finding is
resolved in the text above; the rulings taken under the 2026-10-31 delegation, for the user to
review after Vert.x:

1. A route with no verb is one row, method NULL plus an explicit any-method marker, linked
   by any verb; Quarkus Reactive Routes moves to the same rule (§3a).
2. A route with no path is a `/*` row; middleware is excluded by pass-through (§3a).
3. A regex path is `resolved` and marked as a pattern, never canonicalised or path-linked;
   Quarkus's `@Route(regex)` gains the same row (§3a).
4. Pass-through has three outcomes; "not readable here" gives a `partial` row (§3b).
5. The first answering handler on a chain answers; across chains, ordinal order within one
   method is exact, different methods are `narrowed` (§3b).
6. Inbound dedup is `(protocol, verb, path, handler)` for every inbound fluent row (§3b).
7. A router is identified by its producer, any producer; one from outside the module is
   served at its root, `resolved`, with the bound stated once (§3c).
8. A mount whose prefix is unread gives `<prefix>/…` at `partial`, never linked (§3c).
9. The WebClient's options object is read (a new options-object `client_base` rung), and one
   call gives one peer, `host[:port]` (§3d).
10. Every self-returning method is flagged, not a subset (§3a).
11. A path Vert.x refuses is recorded as refused, never repaired (§3a).
12. `virtualHost` is a host requirement; `disable`/`remove` derive nothing (§3a).
13. Request requirements are read through `request_reads` (§3a).
14. The fixture has a dependency jar holding Hono's out-of-module shapes (§3f).
15. Camel's removal is its own commit (§6).

Logged, not built: **OI-253** (read a sibling module's bytecode: Mesh's wrapper, Hono's
`service-base`); **OI-254**, the stale "the chain walk is per method body" note in
`vertx-eventbus-chain.yml`, which predates ruling 5 (incidental).
