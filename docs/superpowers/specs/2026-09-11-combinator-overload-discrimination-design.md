# Overload discrimination in the `combinator` engine, and the builder form of functional routing

**Status:** design, approved in conversation 2026-09-11. Not yet planned.
**Closes:** `G-37` (the builder form derives nothing, both stacks), the latent
wrong-row defect in the seven `RouterFunctionDsl` verb rules W44 shipped, and the
WebFlux half of the non-coroutine Kotlin `router { }` gap.

Every factual claim below carries the command that produces it, per PV-1's
standing remedy: a claim that goes stale is then detectable rather than silently
wrong.

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

> `verify: sed -n '316,340p' src/sextant/application/resolve/engines/combinator.py`

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

> `verify: sed -n '563,566p' src/sextant/application/resolve/engines/combinator.py`

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

## 8. Fixtures and proof

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

## 9. What this design does not do

- **It does not touch the extractor**, the schema, or any named query. Everything
  it needs is already in the facts.
- **It does not address `GAP-2`** (the linking tier, FR-8/M05/M06). That is phase L.
- **It does not address the other catalog-data gaps** — `SqsAsyncClient` (GAP-3),
  Spring Integration's channel annotations (GAP-5), Data REST's non-JPA stores
  (GAP-6), Kafka Streams (G-31), programmatic Jakarta WebSocket (G-34),
  `@DgsEntityFetcher` (G-40). Each is independent of this one.
- **It does not make `combinator` a general expression reader.** A router composed
  from another method's return still derives one unresolved row; this design makes
  that outcome honest, not absent.

---

## 10. Sizing

One structural engine change (dicts → scanned lists), three catalog keys
(`arity` reused, `arg_types`, `extends_receiver`) plus one new vocabulary role
(`origins`), roughly 98 catalog rules before arity absorbs any, two fixture
sources, regenerated committed facts, seven tests, one probe re-run, and the
`resources` slice rewrite.

**This is a multi-item wave, not a single commit.** The plan must break it so each
piece gates, is reviewed and commits on its own, per the per-item loop.
