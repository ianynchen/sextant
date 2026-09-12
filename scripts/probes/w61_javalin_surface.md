# W61 — Javalin's registration methods, and which argument (if any) carries the route

**Question.** `javalin.yml` (`javalin-routing`) reads `Javalin`/
`JavalinDefaultRoutingApi`/`JavalinDefaultRouting`'s flat verb methods — `get`,
`post`, `put`, `delete`, `patch`, `head`, `options` — each a `default` method
declared on `JavalinDefaultRoutingApi<API>`, an interface exactly TWO types
implement: `Javalin` (`app.get(...)`, the shape the front page shows) and
`public final class JavalinDefaultRouting`, reached through
`RouterConfig.mount(Consumer<JavalinDefaultRouting>)` —
`config.router.mount(router -> router.get(...))` — the SECOND flat registration
form, found on review of the first cut of this catalog, same descriptors, no
nesting. A `single_call` row can only address a wire off an argument the call
site itself carries, so before any row is written the question is mechanical:
of every method matching `get|post|put|delete|patch|head|options|
addHttpHandler|path|sse|ws` on `JavalinDefaultRoutingApi`,
`JavalinDefaultRouting`, `ApiBuilder` and `Javalin` itself, which parameter
position (if any) carries a value shaped like a route — a plain `String` path?

**Version scope (§5.4).** Read against **javalin 6.4.0** — the version the jar
reports for itself, checked against the coordinate before any table is printed.
`fixtures/orders-javalin/pom.xml` pins the same version.

**How to run.** `bash scripts/probes/w61_javalin_surface/run.sh`. Resolves the
artifact through Maven (network on the first run only), reads the version the
jar states for itself, and asks `javap -p -s` for every method on the four
classes matching the shared name pattern above.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | the first `String`-shaped parameter is at position 0 and IS the route (`get(String, Handler)`, `ApiBuilder.get(String, Handler)`) | addressable at `url_arg: 0` — the shape `javalin.yml`'s verb rows use |
| 2 | the first parameter is an ENUM naming the verb, with the route one position later (`addHttpHandler(HandlerType, String, Handler)`) | this column's own "first `String` at 0" measurement does not fire at all — the route sits at argument 1, and no `single_call` word reads a VERB off an argument, so a row here is engine work, not a catalog fix |
| 3 | no parameter is a plain `String` at all, or the method never runs standalone (`ApiBuilder.get(Handler)`, called only inside `path(…)`'s lambda) | not addressable by this style; declaring a row would publish either an unrelated value or a segment missing its `path(…)` prefix |

**The column is a MEASUREMENT of shape, not of meaning.** `ApiBuilder`'s verbs
carry the identical shapes `JavalinDefaultRoutingApi`'s do — a `String` route at
argument 0 — and this table reports them exactly the same way. What the table
cannot say is that `ApiBuilder.get` only means anything when called inside a
`path(prefix, () -> { … })` lambda: reading it as a flat `single_call` row would
compile, match, and publish the inner segment with no prefix — the wrong row
GUIDELINES §8 forbids, not a missing one. That is `javalin-apibuilder`,
Category B, stated in `javalin.yml`'s own `slice.outside` rather than matched
here.

---

## Observations

Verbatim from `scripts/probes/w61_javalin_surface/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `META-INF/maven/.../pom.properties` or its
manifest's `Implementation-Version` — and **not the version the coordinate
list asked for**; `checked` compares the two and ABORTS when they disagree.

| what the run read | 6.4.0 |
|---|---|
| artifacts reporting this version | javalin |
| where the jar states it | pom.properties |

### Every method matching `get|post|put|delete|patch|head|options|
### addHttpHandler|path|sse|ws`, and which position (if any) carries a route

**`io.javalin.router.JavalinDefaultRoutingApi`** (io.javalin:javalin:6.4.0)

| # | method | descriptor | route argument |
|---|---|---|---|
| 1 | `addHttpHandler` | `(Lio/javalin/http/HandlerType;Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 1 |
| 2 | `addHttpHandler` | `(Lio/javalin/http/HandlerType;Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 1 |
| 3 | `get` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 4 | `post` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 5 | `put` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 6 | `patch` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 7 | `delete` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 8 | `head` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 9 | `options` | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | 0 |
| 10 | `get` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 11 | `post` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 12 | `put` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 13 | `patch` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 14 | `delete` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 15 | `head` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 16 | `options` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 17 | `sse` | `(Ljava/lang/String;Ljava/util/function/Consumer;)Lio/javalin/router/RoutingApi;` | 0 |
| 18 | `sse` | `(Ljava/lang/String;Lio/javalin/http/sse/SseHandler;)Lio/javalin/router/RoutingApi;` | 0 |
| 19 | `sse` | `(Ljava/lang/String;Ljava/util/function/Consumer;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |
| 20 | `ws` | `(Ljava/lang/String;Ljava/util/function/Consumer;)Lio/javalin/router/RoutingApi;` | 0 |
| 21 | `ws` | `(Ljava/lang/String;Ljava/util/function/Consumer;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | 0 |

**`io.javalin.router.JavalinDefaultRouting`** (io.javalin:javalin:6.4.0)

| # | method | descriptor | route argument |
|---|---|---|---|
| — | *(no `get\|post\|put\|delete\|patch\|head\|options\|addHttpHandler\|path\|sse\|ws` method found)* | — | — |

**`io.javalin.apibuilder.ApiBuilder`** (io.javalin:javalin:6.4.0)

| # | method | descriptor | route argument |
|---|---|---|---|
| 1 | `path` | `(Ljava/lang/String;Lio/javalin/apibuilder/EndpointGroup;)V` | 0 |
| 2 | `get` | `(Ljava/lang/String;Lio/javalin/http/Handler;)V` | 0 |
| 3 | `get` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | 0 |
| 4 | `get` | `(Lio/javalin/http/Handler;)V` | *(none)* |
| 5 | `get` | `(Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 6 | `post` | `(Ljava/lang/String;Lio/javalin/http/Handler;)V` | 0 |
| 7 | `post` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | 0 |
| 8 | `post` | `(Lio/javalin/http/Handler;)V` | *(none)* |
| 9 | `post` | `(Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 10 | `put` | `(Ljava/lang/String;Lio/javalin/http/Handler;)V` | 0 |
| 11 | `put` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | 0 |
| 12 | `put` | `(Lio/javalin/http/Handler;)V` | *(none)* |
| 13 | `put` | `(Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 14 | `patch` | `(Ljava/lang/String;Lio/javalin/http/Handler;)V` | 0 |
| 15 | `patch` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | 0 |
| 16 | `patch` | `(Lio/javalin/http/Handler;)V` | *(none)* |
| 17 | `patch` | `(Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 18 | `delete` | `(Ljava/lang/String;Lio/javalin/http/Handler;)V` | 0 |
| 19 | `delete` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | 0 |
| 20 | `delete` | `(Lio/javalin/http/Handler;)V` | *(none)* |
| 21 | `delete` | `(Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 22 | `head` | `(Ljava/lang/String;Lio/javalin/http/Handler;)V` | 0 |
| 23 | `head` | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | 0 |
| 24 | `head` | `(Lio/javalin/http/Handler;)V` | *(none)* |
| 25 | `head` | `(Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 26 | `ws` | `(Ljava/lang/String;Ljava/util/function/Consumer;)V` | 0 |
| 27 | `ws` | `(Ljava/lang/String;Ljava/util/function/Consumer;[Lio/javalin/security/RouteRole;)V` | 0 |
| 28 | `ws` | `(Ljava/util/function/Consumer;)V` | *(none)* |
| 29 | `ws` | `(Ljava/util/function/Consumer;[Lio/javalin/security/RouteRole;)V` | *(none)* |
| 30 | `sse` | `(Ljava/lang/String;Ljava/util/function/Consumer;)V` | 0 |
| 31 | `sse` | `(Ljava/lang/String;Ljava/util/function/Consumer;[Lio/javalin/security/RouteRole;)V` | 0 |
| 32 | `sse` | `(Ljava/util/function/Consumer;)V` | *(none)* |
| 33 | `sse` | `(Ljava/util/function/Consumer;[Lio/javalin/security/RouteRole;)V` | *(none)* |

**`io.javalin.Javalin`** (io.javalin:javalin:6.4.0)

| # | method | descriptor | route argument |
|---|---|---|---|
| — | *(no `get\|post\|put\|delete\|patch\|head\|options\|addHttpHandler\|path\|sse\|ws` method found)* | — | — |

`io.javalin.Javalin` and `io.javalin.router.JavalinDefaultRouting` both print no
matching method at all — measured, not an oversight, and true for the SAME
reason on both: `javap -p -s` on a class file lists only what the class ITSELF
declares, and neither type overrides `get`/`post`/etc; both run purely as
`default` methods inherited from `JavalinDefaultRoutingApi<API>`. A call still
compiles to a call ON the receiver's DECLARED type regardless — `javap -c` on
`fixtures/orders-javalin`'s own `OrderApp.class` shows `invokevirtual
io/javalin/Javalin.get:(Ljava/lang/String;Lio/javalin/http/Handler;)…` for
`app.get(...)` on a `Javalin`-typed local, AND `invokevirtual
io/javalin/router/JavalinDefaultRouting.get:(Ljava/lang/String;Lio/javalin/http/
Handler;)…` for `router.get(...)` inside `config.router.mount(router -> …)` —
which is why `javalin.yml`'s `owner` names all three: `io.javalin.Javalin`,
`io.javalin.router.JavalinDefaultRoutingApi` and
`io.javalin.router.JavalinDefaultRouting`. The constant pool records whichever
type the call site's receiver was DECLARED as, not where the method body lives,
and `RouterConfig.mount(Consumer<JavalinDefaultRouting>)` is exactly such a
second declared type — found only because the jar was re-checked for every
implementer of the interface (`grep`-shaped: which types `implements
JavalinDefaultRoutingApi`), not assumed to be `Javalin` alone.

## Verdict

`get`/`post`/`put`/`delete`/`patch`/`head`/`options`, both arities, carry their
route at argument 0 on `JavalinDefaultRoutingApi` exactly as this column
reports — `javalin.yml` reads all fourteen at `url_arg: 0`, the same word
`spring-resttemplate.yml` and `jakarta-websocket-programmatic.yml` use for an
HTTP-addressed `single_call`.

**The SECOND flat form derives identically, and needed its own owner rather
than a wider one.** `RouterConfig.mount(Consumer<JavalinDefaultRouting>)` hands
the lambda a `JavalinDefaultRouting` — the interface's OTHER implementer — and
`router.get("/x", h)` inside it compiles to the identical fourteen descriptors
at the identical position, with no nesting: unlike `ApiBuilder`, `mount`'s
lambda argument IS the routing receiver itself, not a static-method namespace
composing a prefix. `javalin.yml`'s `owner` list names
`io.javalin.router.JavalinDefaultRouting` for exactly this reason, and its
`slice.outside` entry for that owner cross-references `Javalin`'s rather than
repeating the reasoning, since both are the SAME `default` methods reached
through the SAME interface.

`addHttpHandler` (rows 1-2) carries its VERB at argument 0 as a `HandlerType`
enum, with the route one position later — no `single_call` word reads a verb
off an argument, so this row is stated `slice.outside` with the reason in
prose (no mechanical entry: its own descriptor does not open with
`Ljava/lang/String;`, so it is not a candidate the enumeration in
`scripts/probes/w19_catalog_surface.md` counts at all — declaring it there
would be the STALE entry `test_no_slice_names_a_method_the_enumeration_does_not_
list` refuses, Task 5's `repartition` precedent applied here).

`sse` and `ws` (rows 17-21) carry a route at argument 0 too, by this column's
own measurement — and are declared `slice.outside` anyway, because they
register OTHER protocols this catalog does not derive as `http` (SSE and
WebSocket have their own catalogs, the same ruling `jakarta-servlet.yml` makes
for `@WebFilter`).

`ApiBuilder`'s verbs (rows 2-3, 6-7, 10-11, 14-15, 18-19, 22-23) carry the
IDENTICAL shape at the IDENTICAL position — a route `String` at argument 0 —
which is exactly the trap this probe exists to catch: the shape alone cannot
tell a flat registration from one that only means anything nested inside
`path(prefix, () -> { … })`. `path` (row 1) is the nesting primitive itself,
composing the prefix these verbs are called under; reading either on its own
publishes a wrong row, not a missing one — by Javalin's own `path` rule (the
fixture's `nested()` method never runs; the composed address,
`/jv/nested/{id}` rather than bare `/{id}`, is what the library itself would
serve for `ApiBuilder.get("/{id}", h)` sitting inside `path("/jv/nested", …)`,
per Javalin's own documented behaviour, not an observation off a live process).
`javalin.yml`'s own
`test_javalin_flat_registrations_derive_every_route` pins the negative;
`javalin-apibuilder` (Category B, the register §4) is what closes it, needing
the same receiver-chain walk `G-37`/`GAP-1b`/`G-30` wait on.
