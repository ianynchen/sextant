# Overload discrimination in the `combinator` engine, the builder form of functional routing, and the call nested in a lambda

**Status:** design. Part I approved in conversation 2026-09-11; Part II approved in
conversation 2026-09-12 (revised in place — one spec, one mechanism, ruled by the user).
Not yet planned.
**Closes — Group A of the register, nine items:** `G-37` (the builder form derives
nothing, both stacks), `W44-verb-overloads` (the latent wrong-row defect in the seven
`RouterFunctionDsl` verb rules), `GAP-1b` (the WebFlux half of the non-coroutine Kotlin
`router { }` gap), `G-30` and `G-30-outbound` (Spring Cloud Gateway, both halves),
`javalin-apibuilder`, `ktor-routing`, `sqs-template-receive`, `jdk-httpclient`.
**Rows it empties:** REST outbound. REST inbound 9 → 3, SQS 2 → 1.

Every factual claim below carries the command that produces it, per PV-1's
standing remedy: a claim that goes stale is then detectable rather than silently
wrong.

**Standing requirement (ruled 2026-09-12): nothing that works today may move.** Part II
adds two optional fields to one fact; §11 states the proof that every existing row, every
committed fixture fact and every derived table on both corpora is unchanged by them, and
the plan runs that proof before any engine or catalog work starts.

# Part I — overloads and the builder chain (`G-37`, `W44-verb-overloads`, `GAP-1b`)

---

## 1. What is wrong today

A module that writes its routes as

```java
RouterFunctions.route()
    .GET("/orders", handler::list)
    .POST("/orders", handler::create)
    .build();
```

derives **nothing**. Not a partial row, not a question — its entire inbound HTTP
surface is absent from the export with nothing saying so. This is true on both
stacks and has been since functional routing was first catalogued.

**Measured, both stacks, at two different Spring versions:** `RouterFunctions$Builder`
declares **20 method names across 48 overloads**, and the two stacks are identical
in both counts.

> `verify: javap -cp $(find ~/.m2 -name 'spring-webflux-6*.jar' | head -1) 'org.springframework.web.reactive.function.server.RouterFunctions$Builder' | grep -c "public abstract"`
> `verify: javap -cp $(find ~/.m2 -name 'spring-webmvc-6*.jar' | head -1) 'org.springframework.web.servlet.function.RouterFunctions$Builder' | grep -c "public abstract"`

**It is not an exotic shape.** Spring's own reference documentation recommends it:
*"It is generally recommended to use the `route()` constructor as it provides
convenient shortcuts for typical mapping scenarios without the need for
hard-to-detect static imports."*

### 1b. A second defect, already shipped, which the same mechanism fixes

W44 added seven verb rules for the Kotlin `RouterFunctionDsl` with
`path_arg: 0, handler_arg: 1`. That type declares **five** `GET` overloads, and
the rule is correct for exactly one of them:

| overload | what `path_arg: 0` reads | correct? |
|---|---|---|
| `GET(Function1)` | a LAMBDA | no |
| `GET(String, Function1)` | the path | **yes** |
| `GET(RequestPredicate, Function1)` | a PREDICATE | no |
| `GET(String, RequestPredicate, Function1)` | the path, but `handler_arg: 1` reads the predicate | no |
| `GET(String)` | a predicate factory | n/a |

> `verify: javap -cp $(find ~/.m2 -name 'spring-webmvc-6*.jar' | head -1) org.springframework.web.servlet.function.RouterFunctionDsl | grep -E " GET\("`

The catalog says so itself, and says why it has not bitten: *"No live instance:
the only Kotlin router in this repository is the reactive `coRouter`."* Untested,
not safe. **Adding the WebFlux twin gives it a live instance**, which is why the
two cannot be sequenced apart — shipping the twin alone would activate a defect
that publishes a handler object in a URL column.

---

## 2. The blocker is structural, not a missing key

`combinator` holds its vocabulary as dictionaries keyed by `(owner, name)`:

```python
verbs: dict[tuple[str, str], dict[str, Any]]
prefixes: dict[tuple[str, str], dict[str, Any]]
```

> `verify: sed -n '190,191p' src/sextant/application/resolve/engines/combinator.py`

One rule per name. A second rule for `GET` does not lose an argument match — it
**overwrites the first at load time**. No new discriminator key can help while
that shape stands.

**`single_call` already hit this wall and wrote down the fix**, which is why this
design is mostly mirroring a shape this codebase has already chosen once:

> *"A list, not a dict-by-name (Task 6): `arity` lets two rows share a `name` —
> `send(topic, payload)` and `send(topic, key, payload)` — and a dict keyed by
> name would let the second overwrite the first."*

> `verify: grep -n "A list, not a dict-by-name" src/sextant/application/resolve/engines/single_call.py`

### What is already available and simply unread

The call site's own erased JVM descriptor is projected onto every `call_sites`
row, and the engine's site dicts are built by spreading that row whole
(`{**site, "arguments": …}`), so **`site["descriptor"]` is already present and
never read.** No schema change, no query change, no extractor change, no new
capability.

> `verify: sed -n '/CREATE.*VIEW call_sites/,/;/p' src/sextant/storage/duckdb/schema.sql | grep descriptor`
> `verify: sed -n '247,250p' src/sextant/application/resolve/engines/combinator.py`

---

## 3. The discriminator

Three changes.

**3a. `verbs` and `prefixes` become lists, scanned per site.** The same
`_matching_method` scan `single_call` performs. `media`, `composers` and
`media_values` stay dictionaries; nothing overloads them.

**3b. `arity` is the primary discriminator; `arg_types` is the tie-breaker.**
`arity` already exists in this repository's catalog vocabulary. The four builder
`GET` overloads are arity 1, 2, 2 and 3 — so arity alone separates `GET(Handler)`
and `GET(String, Predicate, Handler)` outright, and a type check is needed only
to split the two arity-2 forms:

```yaml
- owner: …RouterFunctions$Builder
  method: GET
  verb: GET
  arity: 2
  arg_types: { 0: java.lang.String }     # splits this from GET(Predicate, Handler)
  path_arg: 0
  handler_arg: 1
```

A rule applies when owner, name and arity match **and** every position named in
`arg_types` carries that type in the call's own erased descriptor. Positions not
named are unconstrained, so a rule stays as loose as it can afford to be — which
is what keeps it alive across Spring releases. Leading with arity rather than
with types keeps the version-brittle surface as small as possible.

**3c. Selection, and what happens when it cannot decide.** Among applicable rules:
arity match first, then the most specific `arg_types` (most positions named), then
**a catalog load error naming both rules**. Never file order — order-dependence
makes a catalog's behaviour unreadable from the catalog, which is the recurring
defect this register keeps recording. A catalog author's obligation follows from
this: a rule must type enough positions to be unambiguous, and the load error is
what enforces it.

### The G-13 guard

`G-13` is graded **Critical** for exactly this failure mode: *"once any row claims
the (name, arity), an unmatched call falls through to no row at all."* Silent
absence is the one outcome this engine's doctrine forbids.

So this design states the opposite rule outright. **A site whose `(owner, name)`
matches a declared vocabulary name but which no rule accepts derives one row with
the columns it could read and `resolution: unresolved` — never silence.** This
extends the engine's existing doctrine (*"a routing expression the walk cannot
read at all derives ONE unresolved row rather than a silent absence"*) from
"unreadable" to "unrecognised overload", and it carries a test that fails the
G-13 way.

---

## 4. Rooting a builder chain

**The chain roots at `build()`, not at `route()`.** In
`route().GET(…).POST(…).build()`, the outermost call whose result nothing consumes
is `build()` — its value is returned from the `@Bean` method. That is exactly the
case the rooting doctrine already names: *"`route(...).and(...)` is rooted at the
`and`, since the `route` is consumed as its receiver."* `_is_root_candidate`
already returns true for an owner-declaring continuation.

**A `return` never consumes.** `consumed` is populated only from the arguments and
receivers of calls the catalog's own vocabulary claims, and a return is not a call
site at all. So `build()`'s result is unconsumed and `build()` roots.

> `verify: grep -n -A12 "def _is_root_candidate" src/sextant/application/resolve/engines/combinator.py`

**A verb must be able to extend its receiver.** Today `_routes_of` dispatches a
verb to `_verb_routes`, which returns that verb's own constraints and never walks
`site["receiver"]`. In a builder chain each verb both declares its own route *and*
carries the chain onward. `_declared_routes` already takes an `extends_receiver`
flag and `_chained_routes` already walks receivers, so this is a catalog key
(`extends_receiver: true`) plus routing that case through machinery that exists.

### 4b. `origins` — the fix for a defect this design had until self-review

`_chained_routes` ends:

```python
return chained or [_Route(poisons=_IDENTITY_POISON)]
```

with `_IDENTITY_POISON = ("method", "path")`.

> `verify: grep -n "_IDENTITY_POISON)\]" src/sextant/application/resolve/engines/combinator.py`

**Zero routes from a receiver becomes a poisoned, identity-less row.** An earlier
version of this design declared `RouterFunctions.route()` as a plain continuation
*precisely because* it contributes zero routes — which would have put a spurious
unresolved row with no verb and no path at the head of **every** builder chain.

So the design adds a third vocabulary role: **`origins`**, declared as
`{owner, method}`. `_chained_routes` returns `[]` rather than poison when the
receiver's producing site is a declared origin. This is the difference between
*"the chain starts here"* and *"I could not read the receiver"* — a distinction
the code cannot currently draw because until now nothing needed it to.

`RouterFunctions.route()` (the argument-less overload) is the only origin either
catalog declares.

**Consequence worth stating: the same `or` clause makes declaring the
pass-throughs mandatory.** An undeclared mid-chain call — `filter`, `before`,
`after`, `onError`, `withAttribute`, `withAttributes` — contributes zero routes
and therefore poisons the **whole chain's** wire identity, costing every route to
its left, not just itself.

---

## 5. The catalog surface

Per stack:

| group | rules | note |
|---|---|---|
| 7 verbs × 4 overloads | 28 | arity splits three ways; `arg_types` splits the arity-2 pair |
| `route(Predicate, Handler)`, `add(RouterFunction)` | 2 | `add` folds its argument's routes through the existing argument fold |
| `nest` ×2, `path` ×2 | 4 | `Consumer<Builder>` and `Supplier<RouterFunction>` are both lambda-bodied — `body_arg` handles them |
| `resources` ×4, `resource` ×2 | 6 | see §6 |
| pass-throughs: `filter`, `before`, `after`, `onError` ×2, `withAttribute`, `withAttributes` | 7 | declare no route; mandatory per §4b |
| `build()` continuation, `RouterFunctions.route()` origin | 2 | |

**Arithmetic, not a measurement:** 49 per stack, ~98 across both, before arity
absorbs any. The real count drops in authoring and the plan should record what it
actually lands at.

**Also in scope, because §1b makes them inseparable:** the seven shipped
`RouterFunctionDsl` verb rules are replaced by five-per-verb rules on both stacks,
and `spring-webflux-router.yml` gains the `RouterFunctionDslKt.router` body-linked
entry its MVC twin has carried since W44.

> `verify: grep -cE "\bRouterFunctionDslKt" src/sextant/catalogs/spring-mvc-router.yml src/sextant/catalogs/spring-webflux-router.yml`
> (3 and 0. The word boundary is load-bearing: `CoRouterFunctionDslKt` contains
> `RouterFunctionDslKt` as a substring, and an unanchored grep reports 2 for
> WebFlux and appears to contradict a correct claim.)

**The slice moves with the code.** `RouterFunctions$Builder`'s `slice.outside`
entries are removed, and `scripts/probes/w19_catalog_surface/run.sh` must report
20 of 20 on both stacks where it reports 0 of 20 today. The "0 of the 20" header
comment moves with it.

---

## 6. Static resources

**Ruled in conversation 2026-09-11: `resources`/`resource` derive rows with a NULL
handler.** A client can `GET /files/**` and receive bytes; that is an inbound
boundary, and omitting it means a module's export understates what it serves.

This **reverses a shipped ruling** at `spring-webflux-router.yml`, which put
`RouterFunctions.resource/resources/resourceLookupFunction` outside the slice on
the ground that *"this analysis has no row shape for 'these bytes are served
here'"*. That ground is false: rows already ship without a handler — `derived_resource`
mints Spring Data REST routes with no handler method, and `schema_operations`
mints rows with neither handler nor caller. The row shape exists.

So the static `RouterFunctions.resource/resources` entries come **in line with the
builder's**, rather than leaving the same shape reading two different ways
depending on which spelling the author wrote.

`resources(Function<ServerRequest, Mono<Resource>>)` computes its location at
runtime and has no readable address: it derives a row with `path` NULL and
`resolution: unresolved`, and must not fabricate an address from the one thing
that is readable.

---

## 7. How it degrades

The engine's per-column poisoning is unchanged. A row carries
`"resolution": "unresolved" if route.poisons else "resolved"`. Five cases are new:

1. **Unrecognised overload** → one row, `resolution: unresolved` (§3's G-13 guard).
2. **Two equally specific rules** → catalog load error naming both, never file order.
3. **A catch-all is not an unknown.** `GET(handler)` declares a route with no path
   constraint; it is `path` NULL with **`resolution: resolved`**, because nothing
   was poisoned. An unreadable path is `path` NULL with `resolution: unresolved`.
   No new field is needed, and getting this backwards would publish "we could not
   read this" for a route the author deliberately wrote open — a lie in the more
   damaging direction.
4. **A builder split across methods** — `private Builder base() {…}` then
   `base().POST(…)` — is one unresolved row, per the existing rule. Stated
   explicitly because a builder invites that factoring far more than
   `route(predicate, handler)` ever did, so a theoretical case becomes routine.
   Same for `add(RouterFunction)` whose argument is built elsewhere.
5. **An undeclared pass-through** poisons the whole chain (§4b), which is why all
   seven are declared.

**Unchanged:** `request_shape`/`response_shape` stay NULL for every functional
route — *"a functional handler's payloads live inside its body, not in its
signature"* — and `caller` remains the containing method of the tree's root call,
which for a builder chain is the method holding `build()`.

---

## 8. Fixtures and proof for Part I

**Precedent:** W44 added `mvcroutes/MvcInvoiceRoutes.java` + `MvcRouteHandlers.java`
to `fixtures/orders-service`. Extracted facts are **committed** as
`.sextant/facts/**/*.jsonl`, so new sources mean regenerated fact files and every
test asserting a fixture total moves with them. That cost is named here rather
than discovered mid-wave.

**Two new fixture sources:**
- A builder router per stack exercising all four verb shapes, `nest`, `path`, a
  `filter` **mid-chain**, a `resources`, and `build()`.
- The WebFlux non-coroutine `router { }` Kotlin source, which gives the corrected
  `RouterFunctionDsl` rules their first live instance — whose absence is why W44's
  seven rules shipped wrong without anything catching it.

**Seven tests. The first is written before any engine change.**

1. **The wrong-row test, first and failing.** All four `GET` overloads in one
   router; assert no row carries a handler object as its path. Written against the
   *existing* shipped MVC Kotlin rules, where it must fail — demonstrating the
   defect rather than asserting it.
2. **The G-13 test.** Call an overload the catalog does not name; assert a row
   appears with `resolution: unresolved`. Fails if the fall-through ever goes
   silent again.
3. **The catch-all test.** `GET(handler)` → `path` NULL / `resolved`; unreadable
   path → `path` NULL / `unresolved`. Both in one test so the distinction cannot
   rot into one behaviour.
4. **Ambiguity refusal.** Two equally specific rules fail catalog load, naming both.
5. **Mid-chain filter.** A chain containing `filter(…)` derives its routes, not one
   poisoned row.
6. **A declining test** per W54's rule — `@pytest.mark.declines` plus exactly one
   `@pytest.mark.pins`, verified by `scripts/guard_check.py`, which has refused
   markers before and will refuse a vacuous one here.
7. **The probe.** `scripts/probes/w19_catalog_surface/run.sh` reports 20 of 20 on
   both stacks.

---

# Part II — the call nested in a lambda (the other six)

## 9. What is wrong today, and why it is one mechanism

The six items were grouped with Part I on 2026-09-12 because measurement showed each
is a call **nested inside a lambda handed to an outer call**, read by the same top-down
walk Part I roots at `build()`:

```java
// Spring Cloud Gateway (G-30, G-30-outbound)
return builder.routes()
    .route("orders", r -> r.path("/orders/**").uri("http://orders-service"))
    .build();

// Javalin ApiBuilder (javalin-apibuilder)
config.router.apiBuilder(() -> path("/orders", () -> get("/{id}", handler)));

// Ktor (ktor-routing)
routing { route("/api") { get("/orders") { … } } }

// SqsTemplate (sqs-template-receive)
template.receive(opts -> opts.queue("orders-queue"), Order.class);

// JDK HttpClient (jdk-httpclient)
HttpRequest.newBuilder().uri(URI.create("https://…/orders")).POST(body).build();
```

Sextant reads compiled classes, and the compiler has moved each lambda into a hidden
method of its own, leaving an `invokedynamic` that names it. The extractor already
follows that link (`lambda`-kind argument → body method), and `combinator` already walks
into linked bodies for `nest`. What the walk cannot do today is **start a chain at the
lambda's own parameter** — `r`, `opts` — because the fact does not say that is what the
receiver is.

### 9a. The receiver blind spot

A call site's `receiver` is the id of the call that produced the receiver. A receiver
that *arrives as a parameter* is recorded as **null** — by design, with the reason stated:

> `verify: grep -n -A7 "private static Integer sourceId" extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java`
> ("a receiver that arrives as a parameter or as `this` stays null … Reporting the marker would emit an id that joins to nothing")

Null is also what a field receiver and an unreadable receiver get. So inside
`lambda$routes$0(PredicateSpec r)`, the call `r.path("/orders/**")` is indistinguishable
from `this.spec.path(…)` and from `(cond ? a() : b()).path(…)` — and the engine's rule
for an unreadable receiver is, correctly, to poison the row. No engine word can recover
what the fact threw away. The **arguments** side already records the answer for its own
slots — `{kind: parameter, value: N}`:

> `verify: grep -n 'argument("parameter"' extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java`

### 9b. A parameter's index is not a catalog constant — measured

The obvious fix, "the catalog names the lambda parameter's index", is **wrong** as soon
as a lambda captures anything. Both compilers put captured values *before* the
interface's parameters:

```
javac, four shapes of the same gateway lambda:
  r -> r.path("/a/**")…            private static Spec lambda$routes$0(Spec)                 r at 0
  r -> r.path(prefix + "/**")…     private static Spec lambda$routes$1(String, Spec)         r at 1
  r -> r.path("/c/**").uri(host)   private        Spec lambda$routes$2(Spec)                 r at 0, `this` is the receiver
  this::helper                                    Spec helper(Spec)                          r at 0
Kotlin, the fixture's own router (committed class file):
  ktRoutes$lambda$2(KotlinOrderRoutes, CoRouterFunctionDsl)                                 DSL receiver at 1 (captures `this`)
  ktRoutes$lambda$2$lambda$1$lambda$0(CoRouterFunctionDsl)                                  DSL receiver at 0
```

> `verify: javap -p -cp fixtures/orders-service/target/classes com.acme.orders.routes.KotlinOrderRoutes | grep 'lambda'`

Same file, same DSL, a different index per lambda. What IS stable is the contract both
compilers build on — `java.lang.invoke.LambdaMetafactory`: the implementation method's
parameters are the captured values, then the functional interface's parameters, in that
order. The interface's parameter `k` therefore sits at `captures + k`, and the number of
captured values is written on the `invokedynamic` the extractor already decodes to name
the body (`lambdaSymbol` reads its bootstrap arguments):

> `verify: grep -n "private static String lambdaSymbol" extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java`

## 10. The two fact additions

**10a. `CallSiteFact.receiver_parameter: int | None`.** Set when the receiver of a call is
the enclosing method's parameter N, D00 §5 numbering (`this` is not a parameter, so
`lambda$routes$2(Spec)` has `r` at 0). Absent in every other case — exactly where
`receiver` is null today. The extractor takes it from the same parameter marker
`argumentJson` already recognises; `sourceId` keeps emitting no *id* and gains a sibling
that emits the *index*.

**10b. `CallArgument.captures: int | None`.** On a `lambda`-kind argument only: **the
number of captured values that occupy leading parameter slots of the body.** That is the
`invokedynamic`'s own argument count, **minus one when the implementation handle is an
instance kind** (`H_INVOKEVIRTUAL`, `H_INVOKESPECIAL`, `H_INVOKEINTERFACE`) — because
then the first captured value becomes the body's `this`, not a parameter. Checked on all
six shapes of §9b: javac's captured `this` → instance handle, count 1 − 1 = 0, `r` at 0;
Kotlin's captured `this` → static synthetic, count 1, receiver at 1; `this::helper` →
`H_INVOKEVIRTUAL`, 1 − 1 = 0, `r` at 0; a captured local → static, 1, `r` at 1; a static
reference and a no-capture lambda → 0. Absent on every non-lambda argument.

*Stated limit:* an **unbound** instance reference used as the lambda (`PredicateSpec::something`
as the route function, count 0, instance handle) makes the interface's parameter 0 the
body's `this`, which no parameter index names; the origin check of §12 then matches
nothing and the row poisons — honest, and not a shape any of the six frameworks invites.

**The mapping, once, in the engine:** the functional interface's parameter `k` is the
body method's parameter **`captures + k`**.

**What does not change.** No stamp bump — `FACT_SCHEMA_VERSION` is frozen at 5 until
release and additive changes ride at it by ruling; an older workspace still validates and
answers with older facts:

> `verify: grep -n "FROZEN UNTIL RELEASE" src/sextant/domain/version.py`

No query, view or derived table changes shape beyond `call_sites` gaining two nullable
columns projected from the JSON like every other optional field
(`verify: grep -n "'receiver'" src/sextant/storage/duckdb/schema.sql`). A row without
them reads NULL, which is today's meaning.

## 11. The proof that nothing existing moves — run before any engine or catalog work

1. **Additive-only regeneration.** The extractor is rebuilt and every committed fixture
   fact regenerated. A script strips the two keys from the regenerated tree and asserts
   the result is **byte-identical** to the tree before the change: no other key, value,
   ordering or line moves.
2. **Both corpora.** `.superpowers/perf/table_diff.py` on `orders-service` and
   `mall-admin` (+3 siblings): every derived table identical; `call_sites` differs only in
   the two new columns (the script masks them and asserts identity).
3. **The suite** green with the new extractor and no other change — `test_language_confinement`,
   `test_application_reads_no_files`, the projection ratchet and the fact-file round-trip
   tests all cover the new fields the way they cover existing ones.
4. **One test per field** pinning the extractor's answer on the six shapes of §9b: no
   capture, captured local, captured `this`, instance method reference, static method
   reference, Kotlin captured `this`. These are the cases a fixed-index design gets wrong,
   so they are the ones pinned.

If step 1 or 2 fails, the plan stops there; nothing in §12–§14 starts on a wrong foundation.

## 12. Which engine reads each item, and the four words `combinator` gains

**Three of the six need no chain.** `single_call` reads them today with one row each; the
lambda only ever *contained* the call. `caller` is then the lambda body, which is already
a row shape in the workspace:

> `verify: .venv/bin/python -c "import duckdb; c=duckdb.connect('fixtures/orders-service/.sextant/workspace.duckdb', read_only=True); print(c.execute(\"select path, handler from endpoints where handler like '%lambda%' limit 3\").fetchall())"`

| item | engine | rule | row |
|---|---|---|---|
| `G-30-outbound` | `single_call` | `UriSpec.uri(String)` → outbound, path = the argument | `outbound · http://…` or `lb://…`, caller = the lambda body |
| `sqs-template-receive` | `single_call` | `SqsReceiveOptions.queue(String)` → inbound SQS; plus the direct `SqsTemplate.receive(String, …)` overloads by `arity` | one rule covers `receive`, `receiveMany`, `receiveAsync`, `receiveManyAsync` — all four take the same options object |
| `G-30` | `combinator` | `route(String, Function)` and `route(Function)` body-linked with `origin_param: 0`; inside: `PredicateSpec.path(String…)` path, `method(HttpMethod…)` verb, `and()`/`or()` composers, `not(…)` a **negator**; `RouteLocatorBuilder.routes()` origin, `build()` root | `inbound · GET /orders/**`; method NULL `resolved` when no `method()` predicate (a catch-all, §7 case 3); handler NULL, as `resources` rows |
| `javalin-apibuilder` | `combinator` | `apiBuilder(EndpointGroup)` body-linked; `ApiBuilder.path(String, EndpointGroup)` prefix with `body_arg`; `get/post/…(String, Handler)` verbs; `get(Handler)` inherits the prefix alone. All static — `ApiBuilder` keeps its own prefix stack, so no receiver to verify | `inbound · GET /orders/{id}`; handler = the `Handler` lambda body; caller = the method holding `apiBuilder` (the root's method, per the engine's `caller` rule) |
| `ktor-routing` | `combinator` | `routing(Application, Function1)` origin, body-linked, `origin_param: 0`; `route(Route, String, Function1)` prefix (`path_arg: 1`, `body_arg: 2`, `receiver_arg: 0`); `get/post/…(Route, String, Function2)` verbs with `receiver_arg: 0` | `inbound · GET /api/orders`; **handler NULL** — a Kotlin `suspend` lambda compiles to a class, not an `invokedynamic`, and links to nothing until item G (`kotlin-null-handler`). Stated on the row's test, not hidden |
| `jdk-httpclient` | `combinator` + `single_call` | JDK: origin `HttpRequest.newBuilder()` / `newBuilder(URI)`, `uri(URI)` read through `path_through` over `URI.create(String)` and `new URI(String)`, verbs `GET()`, `POST(…)`, `PUT(…)`, `DELETE()`, `method(String, …)`, root `build()` — the result handed to `client.send(…)` is still a root because `send` is not in the vocabulary (§4's consumption rule). Apache: `HttpGet(String)`, `HttpPost(String)`, … and `ClassicRequestBuilder.get(String)` are `single_call` rows | `outbound · POST https://…/orders`, caller = the method holding `build()` |

> `verify: grep -n "Every row of one tree carries the containing method" src/sextant/application/resolve/engines/combinator.py`

`single_call` gains nothing. `combinator` gains **four words**, beside Part I's `arity`,
`arg_types`, `extends_receiver` and `origins`:

1. **`origin_param: k`** on a body-linked entry or prefix — "inside the body this call
   links, the chain starts at the lambda's parameter *k*". The engine resolves *k* to the
   body method's parameter `captures + k`, `captures` read off the linking site's own
   `lambda` argument. A chain in that body whose leftmost call has
   `receiver_parameter == captures + k` is rooted there; a leftmost receiver that is null,
   another parameter, or a call the vocabulary does not know, poisons — today's rule,
   unchanged. Users: `route(String, Function<PredicateSpec, …>)`, `route(Function<…>)`,
   `routing(Application, Function1<Route, …>)`.
2. **`receiver_arg: 0`** on a verb or prefix — the extension-receiver form: "argument 0
   must be the enclosing body's origin parameter". The same `captures + k` check on an
   argument of `kind: parameter` instead of on the receiver. Users: every Ktor rule.
   `get(someOtherRoute, "/x")` inside `route("/api") { }` is not under `/api`, and the
   engine will not say it is: that row poisons.
3. **`negators`** — a fourth composer role beside `and`/`or`: the operand's routes are
   dropped and the row poisoned. `BooleanSpec.not(…)` / `PredicateSpec.not(…)`. Poisoned,
   not omitted: a route with a negated path predicate still serves *something*; what it
   serves is not readable from the negation, so the row says `unresolved`.
4. **`path_through`** — `{owner, method, path_arg}`: a call whose *result* appears as a
   path argument is read through to its own argument. `URI.create(String)`, `new URI(String)`.
   The same `source` → producing-site join the engine already makes for predicates,
   applied to a path value; without it `uri(URI.create("https://…"))` is a chain with an
   unreadable path.

Each word has one test that fails without it and one that shows it refusing the wrong
input (§14).

## 13. How the six degrade — continuing §7's list

6. **A chain in a linked body that does not start at the origin parameter** — a field, a
   helper's result, another parameter → one row, `resolution: unresolved`. Never silent,
   never attributed to the origin.
7. **A gateway route with no `method()` predicate** → method NULL, `resolved` (a
   deliberate catch-all, §7 case 3 one column over). With `not(…)` anywhere in its
   predicate tree → `unresolved`.
8. **A Kotlin `suspend` handler** → handler NULL, row otherwise complete, `resolved`: the
   address is read exactly; only the handler symbol is unreadable until item G. The Ktor
   test asserts NULL explicitly so G's landing moves a pinned value rather than silently
   improving one.
9. **A JDK request built in one method and sent in another** — `HttpRequest build()` in a
   helper, `client.send(helper())` elsewhere — one unresolved row at the helper, per §7
   case 4. Same for a request stored in a field.
10. **A lambda the extractor did not link** — Kotlin `-Xlambdas=class`, the default before
    Kotlin 2.0: the body-linked entry's argument is `kind: instance`, not `lambda`; the
    entry roots and derives zero routes, which under §4b is poison, so one unresolved row
    says the router exists and could not be read. The honest answer for a logged item
    (§15), not a defect of this spec.

## 14. Fixtures and proof for Part II

**Fixture sources, all in `fixtures/orders-service`** (committed facts regenerate with
them; Ktor and Javalin become dependencies of the fixture POM, versions recorded by the
plan; CI's priming step compiles the fixture online, so nothing else moves):

| file | exercises |
|---|---|
| `gateway/GatewayRoutes.java` | `routes().route(id, r -> …)` and `route(r -> …)` (both overloads); one route with `path` only; one with `path().and().method(GET)`; one with `or()` (two paths); one with `not()`; one lambda capturing a local (`prefix + "/**"`) and one capturing `this` — the two capture shapes that break a fixed index; every route ends in `.uri(…)`, `http://` on one, `lb://` on another |
| `apibuilder/JavalinApi.java` | `apiBuilder(() -> path("/orders", () -> { get("/{id}", h); post(h); path("/{id}/items", () -> get(h)); }))` — two nesting levels, one verb with no path |
| `ktor/KtorRoutes.kt` | `routing { route("/api") { get("/orders") { … }; route("/v2") { post("/orders") { … } } } }` plus one `get(otherRoute, "/x") { }` inside the body with `otherRoute` a local — the wrong-receiver case |
| `httpclient/JdkOrdersClient.java` | `newBuilder().uri(URI.create(…)).POST(…).build()` sent inline; the `newBuilder(URI)` overload; `.method("PATCH", …)`; one request built in a helper and sent elsewhere; Apache `new HttpGet(…)` and `ClassicRequestBuilder.get(…)` |
| `sqs/OrderPoller.java` | `receive(opts -> opts.queue("orders-queue"), Order.class)`, `receiveMany(opts -> …)`, `receiveAsync`, and the direct `receive("direct-queue", Order.class)` overload |

**Tests, continuing §8's numbering:**

8. **Extractor, the six capture shapes** — `receiver_parameter` and `captures` pinned on
   no capture, captured local, captured `this`, instance method reference, static method
   reference, Kotlin captured `this`. Written first; fails on the current extractor.
9. **Additive-only regeneration** — §11 steps 1 and 2 as a test and a script.
10. **Gateway inbound** — the `(method, path, resolution)` set from `GatewayRoutes`:
    `GET /orders/**` resolved; `NULL /billing/**` resolved (catch-all); both `or`
    branches; the `not` route unresolved; the captured-local and captured-`this` routes
    **resolved with the right path** — the two rows a fixed-index design gets wrong.
11. **Gateway outbound** — the `uri` rows via `single_call`: `http://…` and `lb://…`,
    outbound, caller = the lambda body.
12. **Javalin nesting** — `/orders/{id}`, `/orders` (the path-less `post`),
    `/orders/{id}/items`; every row's caller is the method holding `apiBuilder`.
13. **Ktor** — `/api/orders`, `/api/v2/orders`, handler NULL asserted; the `otherRoute`
    row `unresolved` and without the `/api` prefix (`receiver_arg`'s refusal).
14. **JDK client** — `POST https://…/orders` resolved through `URI.create`; `PATCH` via
    `method(String, …)`; the split request one unresolved row; Apache rows via `single_call`.
15. **SQS** — four rows on `orders-queue` (one per receive form) plus `direct-queue`;
    inbound; the lambda-body caller.
16. **Unlinked lambda** — a hand-built fact set where the body-linked entry's argument is
    `kind: instance`: one unresolved row, not silence (§13 case 10). Pinned so the logged
    Kotlin-1.x item (§15) has a measurable starting point.
17. **Declining tests** per W54's rule for each new catalog — `spring-cloud-gateway`,
    `javalin-apibuilder`, `ktor-routing`, `jdk-httpclient`, `aws-sqs-template` — each
    `@pytest.mark.declines` with exactly one `@pytest.mark.pins`, `scripts/guard_check.py` clean.
18. **Coverage cells** — the register's ```delivery block loses the nine ids;
    `scripts/coverage_matrix.py` moves REST outbound to `✅`; `tests/architecture/test_feature_delivery.py`
    proves both directions.

## 15. What this design does not do

- **Gateway routes declared in properties or YAML** (`spring.cloud.gateway.routes[0].predicates[0]=Path=/orders/**`).
  `config_join` territory, not this walk, and more common than the Java DSL in some
  estates — its own register item rather than a silent rider on `G-30`.
- **`URL.openConnection()`** from `jdk-httpclient`'s original list. Its verb is set by a
  *later statement* on the same connection (`conn.setRequestMethod("POST")`), default GET
  if never set — a walk forwards from a receiver, not backwards to a root, and a new
  default-verb rule. Its own item.
- **Kotlin lambdas compiled as classes** (`-Xlambdas=class`, the default before Kotlin
  2.0): the extractor links a body only from an `invokedynamic`, so a class-form lambda
  arrives as `kind: instance` and reaches no body — which also means W44's shipped DSL
  catalogs derive nothing on such a module today. Real input; its own register item, with
  §13 case 10's unresolved row as the starting point.
- **`GAP-2`** (the linking tier, FR-8/M05/M06) — phase L. A gateway route's inbound and
  outbound rows are not joined to each other here; that is what stitching is for.
- **A general expression reader.** A router or request composed from another method's
  return still derives one unresolved row; this design makes that outcome honest, not absent.
- **The extractor beyond §10.** No other fact, no schema stamp, no named query.

## 16. Sizing and the plan's order

Part I: one structural engine change (dicts → scanned lists), three catalog keys
(`arity` reused, `arg_types`, `extends_receiver`) plus one vocabulary role (`origins`),
roughly 98 catalog rules before arity absorbs any, two fixture sources, seven tests, one
probe re-run, the `resources` slice rewrite. Part II: two optional fact fields, four
`combinator` words, five catalogs (two of them `single_call`), five fixture sources,
eleven tests.

**Group A is one spec and two PRs.** Nine items are too many gates for one PR to be
reviewable, and Part I stands on its own:

**PR A1 — the mechanism, on the shapes already in the register**
1. The two fact fields: extractor, `facts.py`, `schema.sql`, regenerated fixture facts,
   tests 8 and 9. Nothing downstream reads them yet — the smallest item, and it de-risks
   everything after it.
2. `verbs`/`prefixes` → lists with `arity` + `arg_types`, the G-13 guard, ambiguity
   refusal — tests 1–4, the wrong-row test first and failing.
3. The builder form: `extends_receiver`, `origins`, pass-throughs, `resources`, both
   stacks — tests 5 and 7; `G-37` closes.
4. The corrected `RouterFunctionDsl` rules and the WebFlux `router { }` fixture —
   `W44-verb-overloads` and `GAP-1b` close.

**PR A2 — the six, mechanism first, cheapest exact rows first**
5. `origin_param`, `receiver_arg`, `negators` in the engine on hand-built facts — test 16
   and the refusal halves of tests 10 and 13.
6. Javalin — no parameter check, so it proves body nesting alone: test 12.
7. Ktor — the first user of `receiver_arg`: test 13; `ktor-routing` closes with a NULL
   handler stated on its row.
8. Gateway inbound — the first user of `origin_param` and `negators`: test 10. Then the
   two `single_call` rows (gateway `uri`, SQS `queue`): tests 11 and 15. `G-30`,
   `G-30-outbound`, `sqs-template-receive` close; **REST outbound's row empties**.
9. `path_through` and the JDK/Apache client — test 14; `jdk-httpclient` closes.
10. Register, coverage matrix, closed block — test 18.

Each numbered item is one implement → gate → review → fix → commit loop, and each ends
with a row the register can name. The plan records the real catalog rule counts where this
spec gives arithmetic.
