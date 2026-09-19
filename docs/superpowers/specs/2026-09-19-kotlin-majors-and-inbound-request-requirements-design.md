# Kotlin call-site projections, Ktor routing structure, and inbound request requirements

**Status:** design. Approved in conversation 2026-09-19, section by section; Approach B of
three ruled by the user. Self-review against the frameworks' jars, kotlinc 2.2.0 output in
the fixtures, the JVM extractor and the engines is folded in (§0). Not yet planned.

**Closes — the four Kotlin/Ktor Majors, the one Group G item, and one new item:**
`ktor-route-extensions` (a `fun Route.api()` helper called from `routing { }` derives
nothing — the shape is not Ktor-only: Javalin's static `ApiBuilder` helpers and the Spring
Kotlin router DSL carry it too), `ktor-selector-blocks` (the six selectors `method`,
`param`, `optionalParam`, `header`, `accept`, `contentType` lose every route under them),
`kotlin-class-lambdas` (a lambda compiled as a class arrives as `kind: instance`, and no
engine reads its body), `kotlin-default-bridge-calls` (a Kotlin call that omits a defaulted
argument targets `name$default`, which no rule matches), `kotlin-null-handler` (every
Kotlin route row carries a NULL handler), and — added by user ruling 2026-09-19 —
**`inbound-request-requirements`**: no REST inbound row anywhere records that the endpoint
requires a header, a query parameter or a cookie, while every REST outbound row already
records the headers and query parameters the call sends (`endpoint_metadata`, W29).
Two Minors ride along because the same words close them: `ktor-route-with-verb` (the
four-argument `route(path, method) { }`) and — unchanged — nothing else.

**Rows it changes:** REST inbound 8 → 3 (`conditional-controllers`, `dsl-media-route`,
`gateway-properties-routes` stay). Ktor and Javalin rollups go ✅.

Every factual claim below carries the command that produces it, or names the probe (§7)
that must record it before the key it forces is written. Claims marked **measured
2026-09-19** were verified during the self-review against the artifacts named. **A probe
that contradicts a section here changes the section, not the probe** (GUIDELINES §1.1).

**Standing requirement: nothing that works today may move.** Every new key is optional and
inert unless declared; the two projections in §3 change what an engine *sees* only where a
`$default` bridge or a Kotlin lambda class is present, and §8 states how the proof is run
before any engine work.

---

## 0. What the self-review found

| # | Finding | Folded in as |
|---|---|---|
| F1 | Kotlin 2.2.0 compiles **suspend** lambdas as classes even though plain lambdas are `invokedynamic`: in `fixtures/orders-service/.sextant/facts/.../KotlinOrderRoutes*.jsonl` the `coRouter` argument is `kind: lambda` and every `GET`/`POST` handler is `kind: instance` (`KotlinOrderRoutes$ktRoutes$1$1$1#`). So `kotlin-class-lambdas` is not a pre-2.0 concern — it is **every Kotlin handler today**, and `kotlin-null-handler` is the same defect seen from the handler column | §3b is the one mechanism; Group G folds in (user ruling) |
| F2 | The extractor already recognises `$default` bridges on the **declaration** side (`KotlinDefaultBridge.java`, OI-81) and publishes `bridge_of` on the bridge's symbol fact; the fixture's `KotlinOrder#copy$default` carries `"bridge_of": "copy"`. The call-site side can join to it instead of re-deriving the shape | §3a joins on `bridge_of`; a bridge without one is left alone |
| F3 | Mask semantics, read off the compiled bridge (`javap -c -p fixtures/orders-service/target/classes/com/acme/orders/contracts/KotlinOrder.class`, `copy$default`): `iload_3; iconst_1; iand; ifeq` then `getfield id; astore_1` — **a set bit means the caller did NOT supply that parameter** and the default is substituted; bit 0 is the first declared parameter after the receiver | §3a |
| F4 | Ktor 3.0.3 `handle` is a **member** of the `Route` interface, not an extension in `RoutingBuilderKt` (`javap io.ktor.server.routing.Route`: `public abstract void handle(Function2<RoutingContext, Continuation, Object>)`); `accept` takes a **vararg** `ContentType[]`; `HttpMethod.DefaultMethods` is seven members (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS — the static initialiser's `ldc` sequence) | §4c terminal declared on `Route` with no `receiver_arg`; `media_arg` reuses the vararg reader; `all_methods` lists seven, not Spring's eight |
| F5 | Ktor's `HttpMethod.Get` and `ContentType.Application.Json` are **getter calls** on companion/nested objects (`HttpMethod$Companion.getGet()`, `ContentType$Application.getJson()`), never `GETSTATIC` of a constant, so the existing `media_values` member-name table cannot read them | §4b adds a `getters:` key form resolved through `_producing_site` |
| F6 | Spring's binder rule, read off `AbstractNamedValueMethodArgumentResolver.resolveArgument` (spring-web 6.1.6): a null value takes `defaultValue` when one is declared, else `if (required && !parameter.isOptional()) handleMissingValue(...)`; `MethodParameter.isOptional()` is `Optional` type, a `@Nullable`-family annotation, or Kotlin nullability/default (`KotlinDelegate.isOptional`) | §5b's `requirement: binder` is exactly that predicate |
| F7 | Javalin 6.4.0 `Context.header(String)` **reads** and `header(String, String)` **sets** a response header; `cookie(String)` reads, `cookie(String, String[, int])`/`cookie(Cookie)` set. A `request_reads` entry must carry arity | §5d entries carry `arity` |
| F8 | Micronaut `@QueryValue`/`@CookieValue` declare `value` + `defaultValue`; `@Header` declares `value`, `name`, `defaultValue`; none declares `required` — required-ness is nullability/`Optional`/default only | §5b Micronaut entries have no `required_attr` |
| F9 | JAX-RS `@QueryParam`/`@HeaderParam`/`@CookieParam` declare `value` only; `@DefaultValue` is a separate annotation | §5b `default_annotation` key for JAX-RS |
| F10 | Every engine reads call sites through one named query — `workspace.query("call_sites")` or `parsed_call_sites(workspace)` (`grep -rn 'query("call_sites")\|parsed_call_sites' src/sextant/application/resolve`) — so there is exactly one projection point, and the pattern already exists as `resolve/effective_annotations.py` | §3 is `resolve/effective_calls.py`, a second named query |

---

## 1. What is wrong today, in six places

1. **A helper method derives nothing.** `fixtures/orders-ktor/src/main/kotlin/com/acme/kt/KtorRoutes.kt`
   declares `fun Route.api() { get("/helper") { … } }` and calls it from `routing { … api() }`;
   the row is pinned as silence. `_body_routes` (`combinator.py` ~989–1026) walks the
   body's own call sites and reads only catalog words; a call to a module-local method is
   skipped. Javalin's `apiBuilder(() -> { userRoutes(); })` with a static helper and the
   Spring Kotlin DSL's `fun RouterFunctionDsl.orders()` are the same shape.
2. **Selector blocks lose their subtree.** `method`, `param` (two arities), `optionalParam`,
   `header`, `accept`, `contentType` (`javap -cp ~/.m2/repository/io/ktor/ktor-server-core-jvm/3.0.3/ktor-server-core-jvm-3.0.3.jar io.ktor.server.routing.RoutingBuilderKt`)
   each take a `Function1<Route, Unit>` body and are not `prefixes`, so the body is never
   walked. `handle` (F4) is not a `terminal`.
3. **A class-compiled lambda has no body.** `{kind: instance}` (D00 §5, "NEW/constructor
   result") reaches `_body_routes` and `handler_arg` alike; neither follows it. F1: this is
   every Kotlin suspend handler today, which is why every Kotlin route's `handler` is NULL.
4. **A `$default` call matches no rule.** `name$default(recv?, args…, int mask…, Object)` is a
   different name and arity from `name`. The register measured `RoutingBuilderKt` declares
   zero `$default` bridges at 3.0.3, so no Ktor route is affected today; any module-local
   Kotlin DSL with a default parameter is.
5. **No inbound row records what it requires from the request.** `endpoint_metadata` is
   written by `engines/fluent.py` only (`grep -rln endpoint_metadata src/sextant` →
   `fluent.py`, `pipeline.py`, `workspace.py`, the SQL). Spring's
   `@RequestMapping(params=, headers=)` is read only as `discriminators` for the
   duplicate-route check (`spring-mvc.yml:76`); JAX-RS's `@QueryParam`/`@HeaderParam` only
   as `bound_by` to disqualify a body candidate; `@RequestParam`/`@RequestHeader` not at
   all (`grep -rn RequestParam src/sextant` → nothing); Gateway's `header`/`query`/`cookie`
   predicates are `pass_through`. The M06 stitcher (planned, `docs/PROJECT.md:103`) will
   compare request shapes with nothing to compare headers against.
6. **Two Minors on the same words:** the four-argument `route(Route, String, HttpMethod,
   Function1)` derives one unresolved row (`ktor-route-with-verb`).

---

## 2. Approach B — Kotlin at one projection point, routing in the engine

Three approaches were weighed: (A) everything inside the combinator; (B) two Kotlin
projections applied once, where every engine reads call sites, with routing semantics in the
combinator; (C) the same projections emitted by the Java extractor. **B was ruled.** A makes
`$default` and class lambdas Ktor-only fixes when the user ruled them generic; C rewrites
facts at emission and so loses the evidence that a call *was* a bridge (GUIDELINES §8: facts
are what the bytecode says).

Units, each understandable alone:

| # | Unit | Where |
|---|---|---|
| 1 | `$default` bridge calls → the function they stand for | `resolve/effective_calls.py` (§3a) |
| 2 | class-compiled Kotlin lambdas → `lambda` arguments | `resolve/effective_calls.py` (§3b) |
| 3 | follow origin-carrying module-local calls | `engines/combinator.py` (§4a) |
| 4 | selector prefixes, `getters:` value tables, verb-less `handle`, `all_methods` | `engines/combinator.py` + `ktor-routing.yml` (§4b–c) |
| 5 | `endpoint_metadata.requirement` + inbound writer | `schema.sql`, `insert_endpoint_metadata.sql`, `workspace.py`, `resolve/request_requirements.py` (§5a) |
| 6 | `request_params` — parameter annotations | `shapes/contracts.py` + seven catalogs (§5b) |
| 7 | route-tree predicates as requirements | combinator `_Route.requirements`, annotation engine, Gateway (§5c) |
| 8 | `request_reads` — handler-body reads | `resolve/request_requirements.py` + four catalogs: `ktor-routing`, `javalin`, `jakarta-servlet`, `javax-servlet` (§5d) |
| 9 | probes, fixtures, register, COVERAGE, D00/D01/D02/M06 | §7, §9, §10 |

---

## 3. Effective call sites — `resolve/effective_calls.py`

A new named query, **`call_sites_effective`**, that every engine reads in place of
`call_sites` (the ~8 read sites in F10 change name; `parsed_call_sites` wraps the new one).
`call_sites` itself is untouched: the exported bundle (`_EXPORTED["call_sites"]`), the raw
tables and every existing test on them stay byte-identical. The view is built once per
resolve, before any engine runs, by two set-based rewrites.

### 3a. `$default` bridge calls

**Input.** A `call_sites` row whose `target` resolves to a symbol fact carrying `bridge_of`
(module facts or library facts — the scanner runs the same `KotlinDefaultBridge.recognise`
on both). The join is on the target's owner + name + descriptor against `symbols`.

**Rewrite.**
- `target.name` ← `bridge_of`; `target.descriptor` ← the bridge descriptor with the
  receiver slot (when the sibling is an instance method), the `ceil(n/32)` mask slots and
  the trailing `Object` marker removed — the same trimming `KotlinDefaultBridge.solve`
  performs, re-done here from the facts it published (`receiverSlots`, `declaredSlots` are
  not published; the trimming is recomputed from the descriptor and `bridge_of`, and the
  receiver question is settled by which of the two candidate siblings exists in `symbols`,
  exactly the extractor's rule).
- Arguments: the mask arguments are `kind: int` (D00 §5 — "constant instructions"), value
  read as an integer; for declared parameter *i* with bit *i* of mask ⌊i/32⌋ set, the
  argument becomes `{kind: unresolved, reason: defaulted}`; mask and marker slots are
  dropped. A defaulted path therefore reaches a rule as unresolved — an unresolved row, never
  a guessed default (user ruling).
- `receiver`: for an instance sibling, argument 0 (the receiver slot) becomes the row's
  `receiver`/`receiver_parameter` and `invoke_kind` becomes `virtual`; for a static sibling
  nothing moves.
- `evidence` keeps the original bridge target so a reader can see the call *was* a bridge.

**Left alone, stated:** a `$default` target with no `bridge_of` in the facts (library not
scanned; the extractor's "both candidates keyed" ambiguity; a suspend function with exactly
32·k declared parameters, which the extractor declines — its Javadoc, measured); a mask
argument that is not an `int` literal (the whole site is left as is — a wrong trimming is
worse than the silence there is today); constructor defaults (`<init>(…, int,
DefaultConstructorMarker)`), which carry no `$default` name and no `bridge_of`.

### 3b. Class-compiled Kotlin lambdas

**Input.** An argument `{kind: instance, symbol: C, source}` where `C` is a module-local type
whose `type_hierarchy` ancestors include `kotlin.jvm.internal.Lambda` or
`kotlin.coroutines.jvm.internal.SuspendLambda` (both `public abstract class` in
kotlin-stdlib 2.2.0 — `javap -cp ~/.m2/repository/org/jetbrains/kotlin/kotlin-stdlib/2.2.0/kotlin-stdlib-2.2.0.jar kotlin.jvm.internal.Lambda kotlin.coroutines.jvm.internal.SuspendLambda`).

**Rewrite.** The argument becomes `{kind: lambda, symbol: B, captures: 0, source}` where `B`
is the body method of `C`:
- `invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;` when `C` declares one (a suspend
  lambda: `invoke` only builds the continuation and calls `invokeSuspend`; the author's
  statements are in `invokeSuspend`) — **probe CP-23 records this**;
- otherwise the one `invoke` that is not `modifiers.synthetic` (the typed one; the erased
  `invoke(Object)` is the compiler's bridge and is synthetic) — **CP-23**.

`captures: 0` is exact: constructor-captured values are fields of `C`, never leading
parameters of `B`, so the interface's own parameters start at index 0 and a routing walk's
`origin_param: 0` lands on the `Route` unchanged. A body that reads a captured field where a
rule wants a path gets a `field` argument and an unresolved row — honest, not silent.

**Left alone, stated:** a Java anonymous class implementing `Function1` (not a Kotlin lambda
class); a Kotlin `fun interface` SAM conversion (already `invokedynamic`); a lambda class
from a library (not module-local — no body to walk).

### 3c. What each engine sees afterwards

A plain call to the real function with some arguments unreadable, and a plain lambda body to
walk. No engine learns the word "Kotlin". `kotlin-default-bridge-calls` and
`kotlin-class-lambdas` close for all thirteen engines at once; `kotlin-null-handler` closes
because `handler_arg` now names `B`, which `roots`/`reachability` can walk (F1).

**Cost per resolve:** one join `call_sites × symbols` on target (3a), one join of `instance`
arguments × `type_hierarchy` × `symbols` (3b). Both once, set-based, before any engine.

---

## 4. The combinator engine — helpers, selectors, `handle`

### 4a. Following helper calls

In `_body_routes`, a call site that is not a catalog word and whose target is a module-local
method with a body is **followed**:

- **Body with an origin** (Ktor `Route`; Spring DSL receiver): followed when the origin flows
  into the call — as the site's `receiver`, or as argument *i* (`{kind: parameter, value:
  origin}` after `captures` adjustment, exactly the test `_receiver_argument_is_the_origin`
  already makes). Inside the callee, that parameter index is the new `origin_parameter` and
  the same walk runs. A verb on any other `Route` inside the callee is silence, as today.
- **Body without an origin** (Javalin `ApiBuilder`, thread-local): every module-local call is
  followed — `ApiBuilder.get` throws outside `apiBuilder { }`, so a helper reaching it can
  only ever be called from inside the block.
- The caller's accumulated scope — path prefix, verb, media, requirements (§5c) — carries
  into the callee: `route("/api") { api() }` gives `/api/helper`.
- **Guards, no semantics:** a visited set keyed `(callee symbol, origin index)`; depth bound
  16 (Ktor's own documented structures nest 3–4). Exhausting the bound publishes one
  unresolved row with poison `helper_depth`, not silence.
- **Boundary stated:** a routing block held in a variable and invoked later (`val b:
  Route.() -> Unit = {…}; b()`) is `Function1.invoke` on a local — not followed.

### 4b. Selector prefixes

A `prefixes:` entry may now declare, besides `path_arg`, any of `verb_arg`, `media_arg` +
`fills`, `requires`, or none of them (a pure scope). Measured signatures (F4, F5):

```yaml
prefixes:
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: route,  arity: 4, receiver_arg: 0, path_arg: 1, verb_arg: 2, body_arg: 3, origin_param: 0 }   # ktor-route-with-verb
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: method, arity: 3, receiver_arg: 0, verb_arg: 1, body_arg: 2, origin_param: 0 }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: accept,      arity: 3, receiver_arg: 0, media_arg: 1, fills: produces, body_arg: 2, origin_param: 0 }   # ContentType[] vararg
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: contentType, arity: 3, receiver_arg: 0, media_arg: 1, fills: consumes, body_arg: 2, origin_param: 0 }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: header,        arity: 4, receiver_arg: 0, body_arg: 3, origin_param: 0,
      requires: { kind: header, name_arg: 1, value_arg: 2, requirement: required } }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: param,         arity: 3, receiver_arg: 0, body_arg: 2, origin_param: 0,
      requires: { kind: query, name_arg: 1, requirement: required } }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: param,         arity: 4, receiver_arg: 0, body_arg: 3, origin_param: 0,
      requires: { kind: query, name_arg: 1, value_arg: 2, requirement: required } }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: optionalParam, arity: 3, receiver_arg: 0, body_arg: 2, origin_param: 0,
      requires: { kind: query, name_arg: 1, requirement: optional } }
```

**Value tables gain a getter form.** `HttpMethod.Get` compiles to `GETSTATIC
HttpMethod.Companion; INVOKEVIRTUAL HttpMethod$Companion.getGet()`, so the argument is the
*result* of a call. `media_values` and a new `verb_values` accept, beside the member-name
table, `getters: { "<owner>#<method>": <value> }`, resolved through `_producing_site`
(which already follows an argument's `source` to the call that produced it). Unknown getter →
media NULL / verb unresolved, the existing under-report rule.

```yaml
verb_values:
  getters:
    "io.ktor.http.HttpMethod$Companion#getGet": GET
    "io.ktor.http.HttpMethod$Companion#getPost": POST
    # … Put, Patch, Delete, Head, Options — the seven `HttpMethod$Companion.get*` (F4)
media_values:
  getters:
    "io.ktor.http.ContentType$Application#getJson": application/json
    # one measured member at a time, as the Spring table is
```

**Scope semantics.** A selector's verb, media and requirements sit in the scope and apply to
every route beneath, like a path prefix. A route whose own verb disagrees with the scope's
(`method(HttpMethod.Post) { get("/x") { } }`) is a subtree Ktor registers but can never
dispatch; it publishes one **unresolved** row with poison `verb_conflict` rather than
either verb — **CP-24 records the non-dispatch**.

### 4c. `handle` — a verb-less terminal

```yaml
terminals:
  - { owner: io.ktor.server.routing.Route, method: handle, arity: 1, handler_arg: 0 }
all_methods: [GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS]   # HttpMethod.DefaultMethods, 3.0.3 (F4)
```

A terminal (or verb) entry with no `verb` takes the scope's verb; with none in scope it
expands through the catalog's `all_methods` — the word `spring-mvc.yml` already uses for a
bare `@RequestMapping`, one row per method (user ruling). The owner is the `Route`
interface (F4); the receiver is the site's own `receiver`, tested against the origin as
member verbs already are. `all_methods` is now a combinator key too, validated as a
non-empty list of upper-case tokens.

### 4d. `_Route.requirements`

`_Route` gains `requirements: tuple[_Requirement, ...]`, each `(kind, name, value,
requirement, resolution, evidence)`, inherited down scopes and written per emitted row (§5a)
with `caller` = the row's handler symbol — which keeps two `GET /orders` under different
`header` selectors apart in the side table after they collapse to one address in
`endpoints` (Ktor does not refuse the pair at startup; there is no `duplicate: conflict` on
the catalog and nothing to mirror).

---

## 5. Inbound request requirements

### 5a. Schema and writer

`endpoint_metadata` gains **`requirement TEXT`**, closed set `required | optional | absent`,
NULL on every outbound row (an outbound entry is something *sent*). `schema.sql`,
`insert_endpoint_metadata.sql`, the `endpoint_metadata` named query and D01 §3 learn the
column; the table is rebuilt every resolve, so nothing migrates. Inbound rows: `direction =
inbound`; `caller` = handler symbol; `kind ∈ {header, query, cookie, param}` — `param` only
for the two APIs that cannot tell query from form (Spring `@RequestParam`, Servlet
`getParameter`), said on the catalog entry; `value` = a fixed demanded value or NULL. A read
whose name is not a string literal/constant produces `name` NULL, `resolution = unresolved`
— "this handler reads a header it does not name" is a different statement from "reads
none", the reasoning the outbound table was built on.

`resolve/request_requirements.py` owns the writer: one function taking `(endpoint identity,
handler, entries)` from the three mechanisms and one `derive("endpoint_metadata_insert")`
call per engine run, after the engine's endpoints (the fluent engine's order, for the same
reason: an entry names a row that has to exist).

### 5b. Mechanism 1 — parameter annotations (`request_params`)

Read in `shapes/contracts.py`, beside `request_body`, over the handler's `parameters`:

```yaml
request_params:
  - { annotation: org.springframework.web.bind.annotation.RequestParam,  kind: param,  name_attrs: [name, value], requirement: binder, required_attr: required, default_attr: defaultValue }
  - { annotation: org.springframework.web.bind.annotation.RequestHeader, kind: header, name_attrs: [name, value], requirement: binder, required_attr: required, default_attr: defaultValue }
  - { annotation: org.springframework.web.bind.annotation.CookieValue,   kind: cookie, name_attrs: [name, value], requirement: binder, required_attr: required, default_attr: defaultValue }
```

- **`requirement: binder`** is F6 exactly: `optional` when `required_attr` is `false`, when
  `default_attr` is present, when the parameter type is `java.util.Optional`, or when the
  parameter's type reference is `nullable: true` (Kotlin `?` and `@Nullable` both land
  there, D00 §6); else `required`.
- **`requirement: optional`** is JAX-RS's rule: absent → null or `@DefaultValue`, never a
  400 (`default_annotation: jakarta.ws.rs.DefaultValue`, informational — it does not change
  the requirement).
- **Name:** the first present of `name_attrs`, else the parameter's declared `name`; a
  parameter compiled without names → unresolved row.
- **Skipped, stated on the catalog:** whole-map bindings (`Map`, `MultiValueMap`,
  `HttpHeaders` types — no name); Micronaut's *unannotated* by-name binding.
- **Boundary (OI):** a Kotlin parameter with a **default value** and a non-null type is
  `optional` to Spring (F6, `KotlinDelegate.isOptional`) but reads `required` here — the
  per-parameter `declaresDefaultValue` flag is in `@kotlin.Metadata`, which the extractor
  decodes for nullability and not for defaults. Over-reports the requirement; falsified by
  any Kotlin controller with a defaulted `@RequestParam`.

Catalogs and their entries (attributes measured 2026-09-19, F8/F9):

| Catalog | Entries | Rule |
|---|---|---|
| `spring-mvc.yml`, `spring-web.yml` | `@RequestParam`→param, `@RequestHeader`→header, `@CookieValue`→cookie | binder |
| `jakarta-jaxrs.yml`, `javax-jaxrs.yml`, `quarkus-rest.yml` | `@QueryParam`→query, `@HeaderParam`→header, `@CookieParam`→cookie (`value` only) | optional |
| `micronaut-http.yml` | `@QueryValue`→query (`value`, `defaultValue`), `@Header`→header (`value`, `name`, `defaultValue`), `@CookieValue`→cookie | binder, no `required_attr` |
| `quarkus-reactive-routes.yml` | `@Param`→query, `@Header`→header | optional — **CP-25 confirms** absent → null |

### 5c. Mechanism 2 — route-tree predicates

- **Spring `@RequestMapping(params=, headers=)`**, read where `discriminators` already reads
  the two attributes (annotation engine): `name` → required; `name=v` → required, value `v`;
  `!name` → `absent`; `name!=v` → `optional`, the excluded value lost (stated). Class-level
  and method-level union, as `ParamsRequestCondition.combine` does.
- **Spring router DSL, Java:** `RequestPredicates.queryParam(String, String)` → query,
  required, value; `queryParam(String, Predicate)` → query, required, value NULL;
  `headers(Predicate<Headers>)` — an arbitrary function, unreadable — nothing, stated.
  Declared as a new `requires:` list beside `media:` in both router catalogs. (Kotlin's
  `queryParam` is the route-declaring overload already in `slice.outside`; unchanged.)
- **Spring Cloud Gateway** (`PredicateSpec` and `BooleanSpec$BooleanOpSpec`, 5.0.0 — F-row
  measured: `header(String)`, `header(String, String)`, `query(String)`, `query(String,
  String)`, `query(String, Predicate)`, `cookie(String, String)`): the `pass_through: true`
  continuations become `requires:` continuations — header/query/cookie, required, value =
  the regex string where one is given, NULL for the `Predicate` form. The properties side
  (`Header=X,regex`, `Query=x[,regex]`, `Cookie=name,regex`) is **not** in scope: property-
  declared routes derive nothing today (`gateway-properties-routes`, open), and their
  predicates land with that item, on the same `requires:` word.
- **Ktor:** §4b.

### 5d. Mechanism 3 — handler reads (`request_reads`)

One set-based pass in `resolve/request_requirements.py`: for every emitted inbound row with a
handler, the handler body's `call_sites_effective` rows are matched against the catalog's
list. For Ktor the handler is the §3b body method (or the invokedynamic synthetic).

```yaml
request_reads:
  # Ktor 3.0.3 — the three containers all end in `StringValues.get(String)`, so the
  # receiver's PRODUCING call says which one (`via`, one `_producing_site` step)
  - { via: io.ktor.server.request.ApplicationRequest#getHeaders,         method: get, arity: 1, name_arg: 0, kind: header, requirement: optional }
  - { via: io.ktor.server.request.ApplicationRequest#getQueryParameters, method: get, arity: 1, name_arg: 0, kind: query,  requirement: optional }
  - { via: io.ktor.server.application.ApplicationCall#getParameters,     method: get, arity: 1, name_arg: 0, kind: query,  requirement: optional, skip_path_variables: true }
  - { owner: io.ktor.server.util.ParametersKt, method: getOrFail, arity: 2, name_arg: 1, kind: query, requirement: required }
```

- `skip_path_variables: true`: `call.parameters` merges path and query; a name equal to a
  `{name}` segment of the row's path is the path variable and is not recorded.
- **Javalin 6.4.0** (F7): `Context#queryParam(String)`→query, `header(String)`→header,
  `cookie(String)`→cookie, all `arity: 1`, optional; `queryParamAsClass(String, Class)` /
  `headerAsClass(String, Class)` → required **when** the result chain reaches
  `Validator#get()` (`then: { method: get }`, one result→receiver step), else optional
  (`getOrDefault`, `allowNullable`).
- **Servlet ×2:** `HttpServletRequest#getParameter(String)`→param, `getHeader(String)`→header,
  optional.
- **One list per framework, applied by handler, not by catalog.** The `request_reads` of
  every loaded catalog are unioned and matched against every inbound row's handler body:
  Javalin declares its list once in `javalin.yml` and the rows `javalin-apibuilder.yml`
  derives get the same reads without a second copy; a cross-framework match is impossible
  in practice (`via`/`owner` are framework types), and each written row's `evidence` names
  the catalog its entry came from.
- **Boundaries stated:** the handler body only, never methods it delegates to; a read behind
  a branch still counts as `optional`; frameworks whose handlers bind by annotation declare
  no `request_reads` in this spec.

### 5e. Downstream

The bundle exports the column with the table (already whole, `_EXPORTED`). The module
document does not render metadata for outbound today and will not here. `M06-stitcher.md`
gets one paragraph: when built, a client lacking a server's `required` header/query/cookie
entry fails the request-compatibility test the way a missing required body field does;
`optional` and `absent` entries do not affect matching. D01 §3 documents the column and the
inbound `caller` meaning; D02 documents `request_params`, `request_reads`, `requires`,
`verb_values`/`media_values.getters`, verb-less terminals and `all_methods` on combinator
catalogs.

**Cost per resolve:** 5b reads parameters already loaded with the handler; 5c runs inside
walks that already run; 5d is one query joining handler symbols × `call_sites_effective` ×
the catalog's `(owner|via, method, arity)` list.

---

## 6. What this design does not do, and what it logs

| Not built | Why | Where recorded |
|---|---|---|
| Kotlin defaulted-but-non-null parameters read `required` (§5b) | `@kotlin.Metadata` default flag not decoded | new OI; falsifiable by a fixture |
| `name!=value` loses the excluded value; `headers(Predicate)` unread | no column / unreadable function | catalog comments, COVERAGE |
| `call.request.headers` reads outside the handler body | the walk's boundary is the handler | COVERAGE boundary |
| `dsl-media-route` (the `accept(JSON) { }` handler-taking overloads) | a media rule that is also a route — not this spec's words | stays on the register |
| Java anonymous `Function1` classes; library lambda classes | not module-local Kotlin lambda classes | §3b |
| `$default` calls with no `bridge_of` | the extractor's stated declines | §3a |

---

## 7. The four probes — recorded before any key is written

Each is a committed harness under `scripts/probes/cpNN_*/` with a generated observation
table naming the jar-reported version (`tests/architecture/test_probe_provenance.py`, §5.4).

| Probe | Records | Forces |
|---|---|---|
| **CP-23** kotlinc 2.2.0 call-site shapes — a Maven module beside `orders-ktor` compiled twice, default and `-Xlambdas=class` | a `$default` call's mask literal and bit meaning (F3), receiver vs static sibling, a two-mask (33-parameter) function; a lambda class's supertype (`Lambda`/`SuspendLambda`), its `invoke`/`invokeSuspend` methods and synthetic flags, constructor-captured fields | §3a, §3b |
| **CP-24** Ktor 3.0.3 routing surface | the selector signatures (F4), `HttpMethod.DefaultMethods`, the `HttpMethod$Companion.get*` and `ContentType$Application.get*` getters (F5), `ParametersKt.getOrFail`, the `StringValues.get` owners of the three containers; that a `method(Post) { get {} }` subtree never dispatches (a run against an embedded server) | §4b, §4c, §5d |
| **CP-25** binder rules — spring-web 6.1.6, micronaut-http 4.7.6, RESTEasy Reactive, quarkus-reactive-routes, javalin 6.4.0, jakarta.servlet | F6's predicate; Micronaut's required-ness (nullability/`Optional`/default); JAX-RS and reactive-routes absent-parameter behaviour; Javalin `Validator.get()` throwing; `getParameter`/`getHeader` returning null | §5b, §5d |
| **CP-26** predicates — spring-webflux 6.1.6, gateway 5.0.0 | `RequestPredicates.queryParam` overloads; `PredicateSpec`/`BooleanOpSpec` header/query/cookie overloads; the properties spellings | §5c |

---

## 8. The proof that nothing existing moves — run before any engine work

1. Land §3's `call_sites_effective` as a **pure rename** first: the view is `SELECT * FROM
   call_sites` and every engine reads it. Full gate green, every golden byte-identical.
2. Land the two projections behind the view. Re-run the full gate: the only rows that may
   change are those on which a `$default` target with `bridge_of` or a Kotlin lambda class
   occurs — enumerated by a one-off query and listed in the commit message. In the fixtures
   today that is the `KotlinOrder#copy$default` site (a data-class `copy`, no route) and the
   Kotlin handlers of `KotlinOrderRoutes.kt` and `KtorRoutes.kt`, whose `handler` column
   goes from NULL to a symbol — the `kotlin-null-handler` closure, pinned.
3. Every catalog key here is optional; a catalog that declares none derives as before.
   `scripts/check.sh --guards` and the full gate at every commit.

---

## 9. Fixtures and tests

- **`orders-ktor`** (`KtorRoutes.kt`): one block per selector — `method(Get) { handle {} }`,
  `route("/health") { handle {} }` (seven rows), `accept(Json) { get("/j") {} }`,
  `contentType(Json) { post("/c") {} }`, `header("X-Api-Version", "2") { get("/orders") {} }`,
  `param("debug") { … }`, `param("mode", "fast") { … }`, `optionalParam("page") { … }`, the
  four-argument `route("/legacy", HttpMethod.Put) { handle {} }`, the verb-conflict case; the
  existing `api()` helper now derives `/helper`, plus a second-level helper under a prefix
  (`route("/api") { v2() }`, `fun Route.v2() { orders() }`); handler bodies reading
  `call.request.headers["X-Trace"]`, `call.request.queryParameters["q"]`,
  `call.parameters["id"]` (path — skipped), `call.parameters.getOrFail("cursor")`; a
  module-local DSL function with a default parameter under a **test-only catalog**
  (`tests/catalogs/kt-defaults.yml`), called with and without the argument.
- **`orders-ktor-classlambdas`**: the same sources compiled with `-Xlambdas=class`
  (CP-23's harness doubles as the fixture) — the e2e asserts **identical endpoint rows** to
  `orders-ktor`.
- **`orders-service`** Kotlin router: a `Route`-receiver helper in `KotlinOrderRoutes.kt`;
  Java `OrderRoutes.java` gains `queryParam("v", "2")`; Spring MVC controller gains
  `@RequestParam` required/optional/`Optional`/nullable-Kotlin variants and one
  `@RequestMapping(params = "v=1", headers = "!X-Legacy")`.
- **Javalin fixture:** a static helper called from `apiBuilder`; `ctx.queryParam("q")`,
  `ctx.queryParamAsClass("n", Integer.class).get()`, `ctx.header("X-Api")`.
- **Servlet, JAX-RS, Micronaut, Gateway fixtures:** one read/annotation of each kind.
- **Unit tests** on synthetic facts: §3a masks 0/1/mixed/two masks, static vs instance
  sibling, no `bridge_of` untouched, non-int mask untouched; §3b `Lambda` vs `SuspendLambda`,
  synthetic-bridge skipped, non-Kotlin `instance` untouched; §4a visited set, depth bound,
  origin-less following; §4b getter tables, unknown getter; §4c `all_methods` expansion;
  §5b binder predicate table-driven; §5d `via`, `then`, `skip_path_variables`.
- **e2e:** `test_rest_inbound_delivered.py` gains one test per closed item, each asserting
  the `endpoint_metadata` rows for its fixture; the bundle golden pins the new column.
- **Gate:** `JAVA_HOME=… bash scripts/check.sh` at every commit — the lint gate is not the
  gate (Task 2 of B+C, PR #31).

---

## 10. Cells moved, register, documents

| Item | Rollups before → after (COVERAGE §5.1, §2c grid) |
|---|---|
| `ktor-route-extensions` | Ktor ◐, Spring functional ◐, Javalin ◐ → closed on all three |
| `ktor-selector-blocks` | Ktor ◐ → closed |
| `ktor-route-with-verb` (Minor) | Ktor stated boundary → closed |
| `kotlin-class-lambdas` | Spring functional ◐ → closed, engine-wide |
| `kotlin-default-bridge-calls` | Ktor ◐, Spring functional ◐ → closed, engine-wide |
| `kotlin-null-handler` | Spring functional ◐ → closed |
| `inbound-request-requirements` (new, REST in) | — → a "request requirements" line on every REST-inbound framework rollup: ✅ for the fourteen catalogs in §5, "not recorded" for the rest |

Register: the five ids leave the REST in ```delivery``` block; `inbound-request-requirements`
is added and closed in the same PR; `ktor-route-with-verb` closes. `scripts/coverage_matrix.py`
`ITEM_FRAMEWORKS` drops the closed ids. Docs: D00 (no fact change — a note that `bridge_of`
and `instance` are consumed by §3), D01 (`requirement`, inbound `caller`), D02 (the new
keys), M06 (§5e paragraph), COVERAGE §5.1 rows and rollups, `PROJECT.md` component table if
`effective_calls` earns a line, the new OI.

---

## 11. Sizing and the plan's order

1. §3 as a rename (proof step 1) → §3a → §3b, each with unit tests; the Kotlin handler
   column changes here (`kotlin-null-handler`, `kotlin-class-lambdas`,
   `kotlin-default-bridge-calls` close).
2. §5a schema + writer (inert until a mechanism writes).
3. §4a helpers → §4b selectors + getter tables → §4c `handle` + `all_methods` → §4d, with
   `ktor-routing.yml` and `KtorRoutes.kt` growing per task (`ktor-route-extensions`,
   `ktor-selector-blocks`, `ktor-route-with-verb` close; Ktor requirements written).
4. §5b catalog by catalog (Spring, JAX-RS ×3, Micronaut, reactive routes) → §5c (Spring
   annotations, router Java, Gateway) → §5d (Ktor, Javalin, Servlet ×2).
5. Probes are written in the task that first needs each key (CP-23 with step 1, CP-24 with
   step 3, CP-25/26 with step 4); register, COVERAGE, D-docs, M06 last, in one docs task
   gated by the full check.

Roughly twice B+C: two projection units, four combinator units, one schema unit, three
mechanism units over fourteen catalogs, four probes, two fixture variants.
