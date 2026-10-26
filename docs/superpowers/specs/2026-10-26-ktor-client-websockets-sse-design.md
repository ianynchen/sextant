# Ktor's HTTP client, WebSockets and SSE — design

**Status: DRAFT 2026-10-26.** Closes Plane OI-206 (SEXTANT-199), Java/Kotlin framework order 1
(`docs/COVERAGE.md` "Priority order"). Moves COVERAGE §2c's Ktor row from
`✅ ✗ … ✗ ✗` (REST in only) to ✅ on REST in, REST out, WebSocket and SSE.

## 1. The rulings (2026-10-26)

| # | Question | Ruling |
|---|---|---|
| 1 | Scope | **All three, every direction.** The HTTP client's calls (outbound), WebSocket servers and clients, and SSE servers and clients. |
| 2 | Corpora | **Download the official samples and real open-source Ktor apps.** The user also allowed building them with their own Gradle wrappers. |

**My calls**, for review:
- **The verb fix in shipped code is in this item.** The fix that reads a verb from a static field (§3a) also fixes a gap in the shipped routing catalog (§2d).
- **The fixture moves to current Ktor.** `fixtures/orders-ktor` goes from Ktor 3.0.3 to Ktor 3.6.0 and Kotlin 2.4.20, the versions the real corpora build against. The 3.0.3 getter vocabulary stays, so older code keeps reading.
- **Manual SSE is a stated boundary, not built.** Ktor's older form is a normal `get` route that writes `ContentType.Text.EventStream`. It stays an `http` row (§4).

## 2. Measured first

### 2a. Bytecode, from a probe module

A throwaway module compiled against Ktor 3.6.0 (Kotlin 2.4.20), read with `javap`. It is
recorded as probe CP-54 in Task 1.

| Written | Compiles to |
|---|---|
| `client.get("https://h/orders")`, `client.post(url) { setBody(x) }`, `client.get { url(u) }`, `client.request(u) { method = HttpMethod.Put }`, `client.prepareGet(u)` | **Fully inlined at the call site.** All five forms compile to the same sequence (list below). |
| `client.webSocket("ws://h/chat") { }` | `io/ktor/client/plugins/websocket/BuildersKt.webSocket$default(client, "ws://…", …)` |
| `client.webSocket(host = h, port = p, path = "/x") { }` | `BuildersKt.webSocket$default(client, method, host, port, path, …)` |
| `client.sse("https://h/stream") { }` | `io/ktor/client/plugins/sse/BuildersKt."sse-Mswn-_c$default"(client, url, …)`. The mangled name comes from Kotlin's handling of an inline-class (`Duration`) parameter. |
| `routing { webSocket("/ws/chat") { } }` | `io/ktor/server/websocket/RoutingKt.webSocket$default(route, "/ws/chat", protocol, handler, …)` |
| `routing { sse("/sse/events") { } }` | `io/ktor/server/sse/RoutingKt.sse(route, "/sse/events", handler)` |

The inlined HTTP client sequence is the same for all five forms:
1. `new HttpRequestBuilder()`;
2. `HttpRequestKt.url(builder, "…")`, a static extension function whose receiver is its first argument;
3. `builder.setMethod(getstatic HttpMethod.<Verb>)`;
4. optionally `setBody`/`setBodyType`;
5. `new HttpStatement(builder, client).execute()`.

There is no `get(...)` call to match.

### 2b. Confirmed on real code

Two corpora were built with their own Gradle wrappers, at Ktor 3.6.0:
- **`ktor-samples/client-tools`:** the same inlined sequence, with `getstatic HttpMethod.Get`.
- **`kotlin-ktor-exposed-starter`:** its WebSocket server is `RoutingKt.webSocket$default(route, "/updates", …)`, inside a nested route. Its WebSocket client is only in `src/test`, which Sextant does not analyse.
- **`ktor-samples/sse`:** uses the older manual form, `get("/sse") { call.respondBytesWriter(contentType = ContentType.Text.EventStream) … }`. It has no SSE plugin calls (§4).

### 2c. How much real code uses each form

Source census of nine corpora under `examples/`:
- `ktor-samples` @ `1c9df7c`
- `NotyKT`, `kotlin-ktor-exposed-starter`, `ktor-arrow-example`, `CCC`, `dogbin`, `playport`
- JetBrains' `koog` and `kotlinconf-app`

They mostly build Ktor 3.6.0; `dogbin` is 1.3.0 and `koog` up to 3.4.2.

| Form | Where it is used |
|---|---|
| HTTP client | `koog` (78 `HttpClient(`, 66 verb calls, 6 `defaultRequest`), `kotlinconf-app` (42), `ktor-samples` (361 verb-shaped calls) |
| WebSocket server | `ktor-samples`, `kotlin-ktor-exposed-starter`, `dogbin`, `playport` |
| WebSocket client | `ktor-samples` (6), the starter's tests |
| SSE server | `koog` (2 `sse("…")`, 29 `install(SSE)`) |
| SSE client | `koog` (6 `.sse(`) |

### 2d. A gap in the shipped routing catalog

In Ktor 3.6.0 the verbs are static fields: `public static final HttpMethod Get, Post, Put, …`
on `io.ktor.http.HttpMethod`. User code reads the field (`getstatic HttpMethod.Put`).
`ktor-routing.yml`'s `verb_values` lists only the Ktor 3.0.3 Companion getters
(`HttpMethod$Companion#getGet`, …). So on current Ktor, `method(HttpMethod.Get) { … }` and
`route(path, HttpMethod.Put) { … }` read no verb. Real input reaches it once:
`ktor-samples/youkube/Login.kt:50`. The call-site facts already carry a static-field
argument (`CallArgument` kind `field`, with its symbol).

## 3. What changes

### 3a. A verb read from a static field

Verb vocabularies gain the field form beside the getter form, as catalog data. For example,
`"io.ktor.http.HttpMethod#Get": GET` sits alongside the existing `HttpMethod$Companion#getGet`.
It applies in two places:
- **`combinator`'s `verb_values`:** the shipped routing gap of §2d.
- **`fluent`'s verb captures:** the client's `setMethod(field)`. Today a non-literal verb argument is `unresolved`, which `spring-webclient.yml`'s comment states.

This is one rule ("a closed set of static fields that name verbs, per catalog"), not one per
engine. The builder decides where the shared reader lives.

### 3b. WebSocket and SSE servers

These join Ktor's routing vocabulary as verbs whose protocol is `websocket` or `sse`, with
`path_arg: 1`. So `route("/api") { webSocket("/chat") }` nests as HTTP routes already do, through the same
`prefixes`. Both JVM names are listed: `webSocket` and `webSocket$default`.
- **The requirement:** one list of prefixes and entries for all three protocols, never a copy per protocol.
- **The mechanism is the builder's choice:** a per-verb `protocol` in the combinator vocabulary, or a catalog that reuses another's vocabulary. The builder measures which the engine supports.

### 3c. The HTTP client (`ktor-client.yml`, style `fluent`)

- **root:** `io.ktor.client.request.HttpRequestBuilder#<init>`. With no verb set, Ktor's default is GET; measure it in the probe before stating it.
- **steps:**
  - `io.ktor.client.request.HttpRequestKt#url` captures the URL. Its receiver is argument 0: a Kotlin extension function compiles to a static method whose first parameter is the receiver. That is one general Kotlin rule, stated once, for any `fluent` step owner.
  - `HttpRequestBuilder#setMethod` captures the verb, from a static field (§3a).
  - `setBody`/`setBodyType` capture the body, where the facts let it be read.
- **terminal:** the builder passed as argument 0 to `io.ktor.client.statement.HttpStatement#<init>`. That is the `terminal_via_argument` shape OkHttp's `newCall` uses.
- **The base address.** `HttpStatement`'s argument 1 is the `HttpClient`.
  - **Where it comes from:** if the value walk reaches its construction, and the client's configuration lambda calls `defaultRequest { url("…") }`, that string is the base. It joins a relative call's URL the way `spring-webclient.yml`'s `base` joins `url`. This follows "configured at wiring" (memory): a base set once at construction is configuration, and must be derived.
  - **When it can't be read:** a client injected from elsewhere, or a base built by computation, behaves as `computed_base_addresses_not_traced` already does. A relative call then keeps its relative path, unresolved. How far the walk reaches, and the join rule, are settled in §3g.
  - **No `defaultRequest` at all:** what Ktor itself does is mirrored, measured in the probe (Ktor's `URLBuilder` defaults), never assumed.

### 3d. WebSocket and SSE clients (style `single_call`)

- **WebSocket:** `io.ktor.client.plugins.websocket.BuildersKt#webSocket$default` and its siblings, giving an outbound `websocket` row, from a URL argument joined to the client's base (§3g item 2). The `host`/`port`/`path` form is a stated boundary (§3g item 4).
- **SSE:** `io.ktor.client.plugins.sse.BuildersKt#sse-Mswn-_c$default` and siblings, giving an outbound `sse` row.
- **The full set of JVM names** (`ws`, `wss`, `webSocketSession`, `sseSession`, and the mangled suffixes) is read off the Ktor 3.6.0 jars by CP-54 and listed as data. A suffix is a compiler's encoding of the parameter types, so the probe records it per version.

### 3e. Probe CP-54

`scripts/probes/cp54_ktor_client_ws_sse/` reads the Ktor 3.6.0 jars and the probe module's
bytecode. It records:
- the verb fields;
- the builder sequence;
- the WebSocket and SSE function names on both sides;
- `DefaultRequest`'s `url` setter;
- the default verb and default URL when nothing is set.

It is cited in every new or changed catalog's `measured:` block.

### 3f. Fixture

`fixtures/orders-ktor` moves to Ktor 3.6.0 and Kotlin 2.4.20. It is rebuilt with JDK 21; the pom
pins the compiler release, so JDK 21 builds it. It gains:
- a WebSocket route and an SSE route under a nested `route("/api")`;
- a `method(HttpMethod.Get) { … }` block (§2d);
- an `HttpClient` with `defaultRequest { url("https://pricing.example.com/") }`, plus calls in each of §2a's five forms, one of them relative;
- a WebSocket client and an SSE client call.

Every routing count the version bump moves is re-pinned, never deleted.

### 3g. Settled after the builder check (my calls, by standing rules)

1. **A relative call joins the base by Ktor's own URL resolution, not by concatenation.** The rule is DR-6 (mirror the framework).
   - **What Ktor's `DefaultRequest` does:** a path starting with `/` replaces the base's path. A path without one replaces the base's last segment, unless the base ends in `/`. So `https://api.openai.com/v1/` plus `get("/chat")` is `https://api.openai.com/chat`.
   - **Measurement:** CP-54 measures this rule against Ktor's `URLBuilder` before it is written.
   - **Placement:** it is a new join beside `fluent`'s concatenating `base` join. Spring's join is unchanged.
2. **WebSocket and SSE client calls join the same base.** Real calls are relative: `client.ws("/opentelemetry/websocket")` under a `defaultRequest`, and koog's `httpClient.sse(path = …)`. Ktor resolves them through the same plugin.
   - **The base reader is shared** between the `fluent` and `single_call` catalogs: one reader, not two copies.
   - **Each row keeps its protocol's existing shape:**
     - HTTP: split into peer and path, as OkHttp's rows are;
     - WebSocket: the whole URL in `path`, `peer` NULL, as `jakarta-websocket-client.yml`;
     - SSE: as the existing SSE rows.
3. **How far the base walk reaches**, under the rule "trace the value to its source" (memory). A configuration lambda's body is read only where a catalog declares it, as a ladder; it is not a general rule for walking into lambdas.
   - **Ktor's ladder, as data:**
     - `HttpClient(engine, block)`'s block;
     - inside that block, `DefaultRequestKt.defaultRequest(config, block)`'s block;
     - inside that, `DefaultRequestBuilder.url(String)` (or `url { … }`, if CP-54 shows it is a separate setter).
   - **Required forms for "done":**
     - a client held in a field or a top-level `val`, constructed with a literal or config-key base;
     - `client.config { defaultRequest { … } }`, a derived client (koog);
     - a client passed in as a constructor or method parameter, followed through the value walk's existing parameter handling as far as it already reaches.
   - **What happens where the chain leaves the code:** the base is unread. A relative row keeps its relative path, unresolved, and the reason is stated, as `computed_base_addresses_not_traced` is today.
4. **`webSocket(host, port, path)` is a stated boundary, not built.**
   - **Why:** no shipped rule assembles scheme, host, port and path. In the bytecode the port is `Boxing.boxInt(8080)`, and an omitted part falls back to the base.
   - **Cost:** the only real use found (`ktor-samples/reverse-proxy-ws`) passes computed values anyway.
   - **What the row gets:** the `path` part, where readable, joined to the base; otherwise unresolved with the reason.
5. **Verbs on WebSocket and SSE server rows follow the existing conventions.**
   - **WebSocket rows are verbless,** as every shipped WebSocket catalog is (`all_methods: []`).
   - **SSE rows carry GET,** as JAX-RS SSE rows do. Ktor registers both under GET.
   - **What the builder must make the combinator engine do:** a verbless WebSocket route under a verb scope does not take the scope's verb. It is never expanded into seven rows, and it is never dropped under `method(HttpMethod.Post)`.

**Corrections from the check, for the builder:**
- `path_arg: 1` does not hold for every overload: in `webSocket(Route, String, Function2)` argument 1 is the protocol. And `sse` has two arity-3 overloads that only `arg_types` tells apart. CP-54 lists every overload with its argument roles.
- Ktor 3.6.0 also has `Trace` and `Query` verb fields, and `webSocketRaw` routes. Both are in scope: verbs as data, `webSocketRaw` as a WebSocket verb.
- The media getters (`ContentType$Application.getJson`) are still getters in 3.6.0, so the fixture bump does not regress media reads.

## 4. What it does NOT do

- **Manual SSE.** A `get` route whose handler writes `ContentType.Text.EventStream` (Ktor's pre-plugin form, `ktor-samples/sse`) stays an `http` row. Logged as a Plane item.
- **Ktor 1.x and 2.x client names.** `dogbin` is on 1.3.0. Only 3.x is measured; older forms are a stated boundary.
- **A Ktor client calling the same module's own routes** keeps W27's `self_exchange` question for HTTP (OI-198). Ruling C for HTTP is its own item.
- **Per-call headers, query parameters and timeouts** on the client. Only the address, the verb and the body are read here.

## 5. Cost (§8.7)

- The client is one `fluent` catalog over facts already read.
- The base-address walk is one value walk per distinct client argument, cached per resolve.
- The servers are vocabulary entries in an existing combinator pass.
- No new table, so `GRAPH_SCHEMA_VERSION` does not move. If the builder adds one, the version moves with it.

## 6. Verify what it closes

- **Fixture e2e pins (§3f):**
  - inbound WebSocket and SSE rows at their nested paths;
  - the `method(HttpMethod.Get)` route with verb GET;
  - one outbound HTTP row per client call, with the base joined to the relative call;
  - outbound WebSocket and SSE rows.
- **Re-measure the built corpora** and record the results under "As built":
  - `ktor-samples/client-tools`: client rows;
  - `kotlin-ktor-exposed-starter`: the WebSocket server at its nested path;
  - `ktor-samples/youkube`, if it builds: the `method(HttpMethod.Get)` route.
- **Records:**
  - COVERAGE §5.2/§5.5/§5.6's Ktor rows move to ✅ shipped, and §2c is regenerated, with the Ktor family row reading ✅.
  - CHANGELOG.
  - Plane: OI-206 goes to Done.
