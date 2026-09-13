# Overload discrimination in the `combinator` engine, the builder form of functional routing, and the call nested in a lambda

**Status:** design. Part I approved in conversation 2026-09-11; Part II approved in
conversation 2026-09-12 (revised in place — one spec, one mechanism, ruled by the user).
Not yet planned.
**Closes — Group A of the register, nine items:** `G-37` (the builder form derives
nothing, both stacks), `W44-verb-overloads` (the seven `RouterFunctionDsl` verb rules
read one overload of five and mis-grade the rest), `GAP-1b` (the WebFlux half of the non-coroutine Kotlin
`router { }` gap), `G-30` and `G-30-outbound` (Spring Cloud Gateway, both halves),
`javalin-apibuilder`, `ktor-routing`, `sqs-template-receive`, `jdk-httpclient`.
**Rows it empties:** REST outbound. REST inbound 9 → 3, SQS 2 → 1.

Every factual claim below carries the command that produces it, per PV-1's
standing remedy: a claim that goes stale is then detectable rather than silently
wrong.

**Standing requirement (ruled 2026-09-12): nothing that works today may move.** Part II
adds two optional fields to one fact; §11 states the proof that every existing row, every
extracted fixture fact and every derived table on both corpora is unchanged by them, and
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

| overload | what the shipped rule derives — MEASURED 2026-09-13 on hand-built facts against `spring-mvc-router` | correct? |
|---|---|---|
| `GET(Function1)` | `GET`, path NULL, handler read, **`unresolved`** — a deliberate catch-all reported as unreadable (§7 case 3's damaging direction) | no |
| `GET(String, Function1)` | the route | **yes** |
| `GET(RequestPredicate, Function1)` | `GET`, path NULL, the predicate's own constraints lost, `unresolved` | no |
| `GET(String, RequestPredicate, Function1)` | `GET /x`, **handler NULL** (`handler_arg: 1` is the predicate), the predicate lost, marked `resolved` | no |
| `GET(String)` | a predicate factory | n/a |

*This table said the rules "publish a lambda or a predicate as a URL". They do not:
`_argument_constraints` turns only a string literal into a path and poisons anything
else, so the defect is under-reporting and mis-grading — three rows wrong in what they
claim about themselves — not fabrication. Corrected when the plan's first test was
written against the engine rather than against this table.*

> `verify: javap -cp $(find ~/.m2 -name 'spring-webmvc-6*.jar' | head -1) org.springframework.web.servlet.function.RouterFunctionDsl | grep -E " GET\("`

The catalog says so itself, and says why it has not bitten: *"No live instance:
the only Kotlin router in this repository is the reactive `coRouter`."* Untested,
not safe. **Adding the WebFlux twin gives it a live instance**, which is why the
two cannot be sequenced apart — shipping the twin alone would activate rules that
grade a catch-all as unreadable and a handler-less row as complete.

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

**3c. Selection, and what happens when it cannot decide.** Never file order —
order-dependence makes a catalog's behaviour unreadable from the catalog, which is
the recurring defect this register keeps recording. *Ruled 2026-09-13 (plan Task 3),
replacing a "most specific `arg_types` wins" tie-break this paragraph used to state:*
there is **no tie-break at match time**. Two rules sharing owner, method and arity
must type at least one shared position with different types, or the catalog is
**refused at load, naming both** — a call has one type per position, so at most one
rule can then ever accept it. A catalog author's obligation follows: a rule must type
enough positions to be unambiguous, and the load error is what enforces it.

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

**The statement form roots at each verb (ruled 2026-09-13, plan Task 4 review).** The
builder is mutable and every method returns `this`, so real code also writes
`var b = route(); b.GET("/a", h); b.POST("/b", h); return b.build();` — the form
conditional registration takes. Measured before the ruling: zero rows, silence. So a
receiver-extending verb **roots when its own result is consumed by nothing AND its
receiver is produced by a call in the same method**. In the chained form every
intermediate verb's result is consumed, so only `build()` roots, as before; in the
statement form each verb's receiver is the origin's result and nothing consumes the
verb's own, so each roots and derives its route; a mixed form roots at the last verb of
each statement and `build()`, and identity dedup removes the routes both reach. Checkpoint
F4 holds: inside a `Consumer<Builder>` body the chain's HEAD sits on the lambda's own
parameter (`receiver_parameter`, no producing call), and the test is on that head rather
than on the verb's own receiver — a body's second verb (`b.GET(…).DELETE(…)`) has a
same-method receiver exactly as a statement-form verb does — so no body verb roots, and
the body is folded through `_body_routes` alone. *Ruled at the A1 final review (I-1): the
head test protects only receiver-extending verbs and prefixes, and a body holding a whole
chain of its own — the `Supplier<RouterFunction>` overload's `route().GET(…).build()`, an
`add(router)` on the body's parameter — rooted beside the prefix's fold and derived its
route twice. A method some linking call names as its body is now skipped by the root scan
whole: folded exactly once, by whichever root reaches the linking call.*

**Two equal verbs merge** (same ruling): `_merged` poisoned `method` whenever both sides
carried a verb, so `resource(RequestPredicates.GET("/favicon.ico"), r)` — the `resource`
rule's own `GET` against the predicate's — derived `unresolved`. A request carries one
verb, and `GET` ∧ `GET` is that verb; only two DIFFERENT verbs poison.

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
`{owner, method, arity, arg_types?}` — a rule, discriminated exactly as §3's verbs
are. *Ruled 2026-09-13 (plan Task 4): this said `{owner, method}`. Matched on owner and
name alone, `RouterFunctions.route` as an origin swallowed `route(predicate, handler)` —
the head of every `andRoute` chain — as a chain start, and three live routes vanished
(`GET /fn/orders`, `GET /mvcfn/invoices`, `GET /extra`). The argument-less `route()` is
`arity: 0`; the two-argument form stays the entry it always was.* `_chained_routes`
returns `[]` rather than poison when the receiver's producing site matches a declared origin. This is the difference between
*"the chain starts here"* and *"I could not read the receiver"* — a distinction
the code cannot currently draw because until now nothing needed it to.

`RouterFunctions.route()` (the argument-less overload) is the only origin either
catalog declares.

**Consequence worth stating: the same `or` clause makes declaring the
pass-throughs mandatory.** An undeclared call in a chain — `filter`, `before`,
`after`, `onError`, `withAttribute`, `withAttributes`, or an undeclared head —
contributes zero routes, so every route to its LEFT is replaced by one unresolved row;
the routes to its right still derive, each on its own turn. (Stated precisely 2026-09-13,
plan Task 4: "the whole chain" overstated it — the chain right of the gap is intact.)

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
3. **A catch-all is not an unknown — and not an absence.** `GET(handler)` declares a
   route with no path constraint: it serves EVERY path, and the row says so with the
   framework's own any-path pattern, **`path: /**`, `resolution: resolved`**. An
   unreadable path is `path` NULL with `resolution: unresolved`. Getting this backwards
   would publish "we could not read this" for a route the author deliberately wrote
   open — a lie in the more damaging direction. *Ruled 2026-09-13 (plan Task 3): this
   case said `path` NULL, `resolved`. That row is exactly what the call-side
   addresses-nothing gate (`derive_call_endpoints.sql`) drops by doctrine — a resolved
   row with no address claims "read, and there is none" — so the catch-all never reached
   the `endpoints` table. `/**` is the address the framework serves it at; `combinator`
   now never emits a resolved row with a NULL path, which keeps the gate's invariant
   whole.* The same rule reaches `route(accept(JSON), h)` — a media-only route serves
   every path, and reads `/**` with its media, where it used to be dropped silently.
   *Ruled 2026-09-13 (A2 Task 3): a framework whose path-less verb serves the PREFIX
   it sits under rather than every path — Javalin's `get(handler)` is
   `get(prefixPath(""), handler)`, Ktor's the same shape — is not a catch-all, and its
   catalog spells that with the empty literal `path: ""` on the rule; and a framework
   that JOINS segments itself — Javalin's `prefixPath` puts a `/` in front of a
   segment lacking one, so `path("api", …)` is `path("/api", …)` — declares
   `path_join: leading_slash`, without which the glued `/users{id}` is a resolved wrong
   row (Task 3 fix round 1).*
4. **A builder split across methods** — `private Builder base() {…}` then
   `base().POST(…)` — is one unresolved row, per the existing rule. Stated
   explicitly because a builder invites that factoring far more than
   `route(predicate, handler)` ever did, so a theoretical case becomes routine.
   Same for `add(RouterFunction)` whose argument is built elsewhere. **A stated
   boundary beside it:** a statement-form builder held in a FIELD or received as a
   PARAMETER — `this.b.GET("/a", h);`, `void routes(Builder b) { b.GET("/a", h); }` —
   derives nothing, not even the unresolved row. In the facts that verb is
   indistinguishable from a body's: its chain's head is no call in the method, which
   is exactly what keeps a `Consumer<Builder>` body from rooting. The `base().POST(…)`
   spelling, whose receiver IS a call in the method, is the one that yields the row.
5. **An undeclared pass-through** costs the routes to its left (§4b as ruled): the
   chain to its right still declares its own routes, and the unread receiver is one
   unresolved row beside them. Which is why all seven are declared.

**Unchanged:** `request_shape`/`response_shape` stay NULL for every functional
route — *"a functional handler's payloads live inside its body, not in its
signature"* — and `caller` remains the containing method of the tree's root call,
which for a builder chain is the method holding `build()`.

---

## 8. Fixtures and proof for Part I

**Precedent:** W44 added `mvcroutes/MvcInvoiceRoutes.java` + `MvcRouteHandlers.java`
to `fixtures/orders-service`. Extracted facts are **not committed** — `.sextant/` is
gitignored (`verify: git check-ignore -v fixtures/orders-service/.sextant/facts`) — so a
new source costs a recompile and a re-analysis in every test that runs one, and every
test asserting a fixture total moves with it. That cost is named here rather than
discovered mid-wave.

**Two new fixture sources:**
- A builder router per stack exercising all four verb shapes, `nest`, `path`, a
  `filter` **mid-chain**, a `resources`, and `build()`.
- The WebFlux non-coroutine `router { }` Kotlin source, which gives the corrected
  `RouterFunctionDsl` rules their first live instance — whose absence is why W44's
  seven rules shipped wrong without anything catching it.

**Seven tests. The first is written before any engine change.**

1. **The overload test, first and failing.** All four `GET` overloads in one
   router; assert `GET(handler)` derives path NULL **`resolved`**, `GET("/x", predicate,
   handler)` derives its handler and the predicate's constraints, and `GET(predicate,
   handler)` derives the predicate's path. Written against the *existing* shipped MVC
   Kotlin rules, where it must fail on all three — demonstrating the defect rather than
   asserting it.
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
is a call **nested inside a lambda handed to an outer call**. Four of them need the
top-down walk Part I roots at `build()`; two (§12) are read by a word `single_call`
already has, and are listed here because the lambda is what hid them:

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
Kotlin, the fixture's own router (class file under `target/classes`):
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

1. **Additive-only extraction.** Every fixture root is scanned twice — with the jar built
   before the change and with the jar built after — into two trees. A script strips the two
   keys from the second tree and asserts it is **byte-identical** to the first: no other
   key, value, ordering or line moves. (Fact trees are not committed; the proof is the
   double scan, kept as a script so the plan and a reviewer can re-run it.)
2. **Both corpora.** `.superpowers/perf/table_diff.py` on `orders-service` and
   `mall-admin` (+3 siblings): every derived table identical; the fact tables differ only
   by the two new keys — the script strips `receiver_parameter` and `captures` from every
   payload (and the two projected columns) before comparing, and asserts identity.
3. **The suite** green with the new extractor and no other change — `test_language_confinement`,
   `test_application_reads_no_files`, the projection ratchet and the fact-file round-trip
   tests all cover the new fields the way they cover existing ones.
4. **One test per field** pinning the extractor's answer on the six shapes of §9b: no
   capture, captured local, captured `this`, instance method reference, static method
   reference, Kotlin captured `this`. These are the cases a fixed-index design gets wrong,
   so they are the ones pinned.

If step 1 or 2 fails, the plan stops there; nothing in §12–§14 starts on a wrong foundation.

## 12. Which engine reads each item, and the four words `combinator` gains

**Two of the six are catalog data.** `single_call` already reads a destination named
inside a lambda handed to the call — `lambda_arg` names the lambda, `lambda_steps` the
owner-checked calls to read in its body (W57) — and `spring-sqs-template.yml` derives
`SqsTemplate.send(opts -> opts.queue("q")…)` that way today:

> `verify: grep -n "lambda_steps" src/sextant/catalogs/spring-sqs-template.yml src/sextant/application/resolve/engines/single_call.py | head -3`

`sqs-template-receive` is the receive twin of that rule and `G-30-outbound` the same word
on `route(id, fn)`. The row's `caller` is the method holding the outer call (`poll()`,
`routes()`), not the compiler's lambda. The plan writes each rule first and measures; if
it derives, no engine work exists for either.

| item | engine | rule | row |
|---|---|---|---|
| `G-30-outbound` | `single_call`, `lambda_steps` | `RouteLocatorBuilder$Builder.route(String, Function)` and `route(Function)` with `lambda_arg` 1 / 0 and `lambda_steps: [{owner: UriSpec, method: uri, channel_arg: 0}]` (also the `uri(URI)` overload, if the fixture shows it used) → outbound; its own catalog, `spring-cloud-gateway-outbound.yml`, because a catalog has one style | `outbound · http://…` or `lb://…`, caller = `routes()` |
| `sqs-template-receive` | `single_call`, `lambda_steps` | in `spring-sqs-template.yml`: `receive` / `receiveMany` / `receiveAsync` / `receiveManyAsync` `(Consumer<SqsReceiveOptions>[, Class])` with `lambda_steps: [{owner: SqsReceiveOptions, method: queue, channel_arg: 0}]`; the direct `receive(String, …)` overloads by `arity` | `inbound · orders-queue`, caller = `poll()` — the `send` rule's receive twin |
| `G-30` | `combinator` | `route(String, Function)` and `route(Function)` body-linked with `origin_param: 0`; inside: `PredicateSpec.path(String…)` path, `method(HttpMethod…)` verb via **`verb_arg`**, `and()`/`or()` composers, `not(…)` a **negator**, `filters(…)` a pass-through; `RouteLocatorBuilder.routes()` origin, `build()` root; its own catalog, `spring-cloud-gateway.yml` | `inbound · GET /orders/**`; method NULL `resolved` when no `method()` predicate (a catch-all, §7 case 3); handler NULL, as `resources` rows |
| `javalin-apibuilder` | `combinator` | `apiBuilder(EndpointGroup)` body-linked; `ApiBuilder.path(String, EndpointGroup)` prefix with `body_arg`; `get/post/…(String, Handler)` verbs; `get(Handler)` inherits the prefix alone. All static — `ApiBuilder` keeps its own prefix stack, so no receiver to verify | `inbound · GET /orders/{id}`; handler = the `Handler` lambda body; caller = the method holding `apiBuilder` (the root's method, per the engine's `caller` rule) |
| `ktor-routing` | `combinator` | `routing(Application, Function1)` origin, body-linked, `origin_param: 0`; `route(Route, String, Function1)` prefix (`path_arg: 1`, `body_arg: 2`, `receiver_arg: 0`, and `origin_param: 0` for its own body); `get/post/…(Route, String, Function2)` verbs with `receiver_arg: 0`; fixture `fixtures/orders-ktor` | `inbound · GET /api/orders`; **handler NULL** — a Kotlin `suspend` lambda compiles to a class, not an `invokedynamic`, and links to nothing until item G (`kotlin-null-handler`). Stated on the row's test, not hidden |
| `jdk-httpclient` | **`fluent`** (measured 2026-09-13: `okhttp.yml` is this exact shape — a static or `<init>` root, verb-setting steps, a `build` terminal joined to the client's `send`) | JDK: root `HttpRequest.newBuilder` (`captures: {http_method: GET, url: arg0}`; the argument-less overload's `arg0` reads nothing and the `uri` step overwrites it), steps `uri` (`url: arg0`), `GET`/`DELETE`/`POST(body)`/`PUT(body)`/`method(verb, body)` (`http_method`, `body`), `header`/`headers`/`timeout`/`version`/`expectContinue` pass through undeclared, terminal `build` with `terminal_via_argument: {owner: java.net.http.HttpClient, method: [send, sendAsync]}`. `uri(URI.create("…"))` and `uri(new URI("…"))` reach the step as `unresolved`+`source`, so `fluent` gains **`url_via`** — the `channel_via` ladder for the `url` capture, verbatim (`{owner: java.net.URI, method: create, arg: 0}`, `{owner: java.net.URI, method: <init>, arg: 0, arity: 1}` — *amended 2026-09-13, A2 Task 8 fix round 2: the constructor form carries `arity`, since `URI` declares four multi-argument constructors whose argument 0 is the scheme*). Apache 5: static roots `ClassicRequestBuilder.get/post/put/delete/patch(String)` (`url: arg0`, verb literal) with `build` terminal via `CloseableHttpClient.execute`; constructor roots `HttpGet/HttpPost/…(String)` as `<init>` roots that are themselves the terminal via `execute` — the walk already checks the root site against `terminal` | `outbound · POST https://…/orders`, peer/path split by `url_of` as every `fluent` row is; caller = the method holding the chain |
> `verify: grep -n "Every row of one tree carries the containing method" src/sextant/application/resolve/engines/combinator.py`

`single_call` gains nothing; `fluent` gains `url_via` (above). `combinator` gains the
words below, beside Part I's `arity`, `arg_types`, `extends_receiver` and `origins`.
*Withdrawn 2026-09-13: `path_through` and an origin's `path_arg` — both existed only for
the JDK client, which is a `fluent` catalog; `fluent`'s `url_via` is the same read in the
engine that already owns builder chains.*

1. **`origin_param: k`** on a body-linked entry or prefix — "inside the body this call
   links, the chain starts at the lambda's parameter *k*". The engine resolves *k* to the
   body method's parameter `captures + k`, `captures` read off the linking site's own
   `lambda` argument. A chain in that body whose leftmost call has
   `receiver_parameter == captures + k` is rooted there; a leftmost receiver that is null,
   another parameter, or a call the vocabulary does not know, poisons — today's rule,
   unchanged. Users: `route(String, Function<PredicateSpec, …>)`, `route(Function<…>)`,
   `routing(Application, Function1<Route, …>)` — **and every shipped body-linked rule whose
   body's parameter is the builder** (`coRouter`, `router`, the DSL `nest`, the builder's
   `Consumer<Builder>` `path`/`nest`), which declare `origin_param: 0` in this PR: Part I
   read "no receiver" inside a body as clean, which is exact only while a body never holds
   a field receiver. A `Supplier` body has no parameter and declares none. Nothing shipped
   moves — the fixtures' bodies all sit on parameter `captures + 0` (measured in Part I's
   Task 1 on javac and the fixture's Kotlin).
2. **`receiver_arg: 0`** on a verb or prefix — the extension-receiver form: "argument 0
   must be the enclosing body's origin parameter". The same `captures + k` check on an
   argument of `kind: parameter` instead of on the receiver. Users: every Ktor rule.
   `get(someOtherRoute, "/x")` inside `route("/api") { }` is not under `/api`, and the
   engine will not say it is: that row poisons.
3. **`negators`** — a fourth composer role beside `and`/`or`: the operand's routes are
   dropped and the row poisoned. `BooleanSpec.not(…)` / `PredicateSpec.not(…)`. Poisoned,
   not omitted: a route with a negated path predicate still serves *something*; what it
   serves is not readable from the negation, so the row says `unresolved`.
4. **Chain-form composers and a terminal** — measured on `spring-cloud-gateway-server-webflux`
   5.0.0 (`javap`): a gateway route is `r.path("/a").and().method(GET).filters(f).uri(x)`
   — predicates are calls on a RECEIVER chain, composed by the zero-argument `and()`/`or()`
   (left-associative: `(a or b) and GET`), and the route is emitted by the chain's last
   call. Part I's composers compose ARGUMENTS (`p1.and(p2)`), and a receiver-extending verb
   emits one route per verb; neither reads this. So: `chain_composers: {and: [{owner,
   method}], or: […]}`; `negators: [{owner, method}]` (`not(fn)`, `negate()`, and
   `predicate(…)` — a served set the walk cannot read — all poison identity); and
   `terminal: true` on a rule with `handler_arg` or `handler: none`: the call's routes are
   its receiver chain folded as CONSTRAINTS — start at the origin (or the body's origin
   parameter), pass-throughs stepped over, every other rule's constraints merged into each
   branch, `or()` opening a new branch, an unread head poisoning all — merged with the
   terminal's own. A route whose constraints read no path serves every path: `/**` (§7
   case 3), so a route with only `method(GET)` or only `host(…)` publishes `GET /**`;
   `host`, `order`, `metadata`, `alwaysTrue`, `filters(fn)` are pass-throughs. A path
   argument that is an ARRAY of string literals (`path("/a", "/b")`) is one branch per
   element, in `_argument_constraints`, for every rule that reads a path.
5. **`verb_arg: n`** on a verb rule — the verb is the argument at *n*: an enum member's
   name (`method(HttpMethod.GET)`), a string literal, or an ARRAY of those (the gateway's
   `method(HttpMethod...)` is a vararg: `method(GET, POST)` is one branch per verb);
   anything else there poisons `method`. Today the grammar reads a verb only as a literal beside the
   owner, and says so as a coverage boundary on both Spring routers
   (`verify: grep -n "stay OUT" src/sextant/catalogs/spring-webflux-router.yml`); the word
   lifts that boundary for `RequestPredicates.method/methods` as a side effect, which the
   plan records as a moved coverage cell.

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
   case 4. Same for a request stored in a field. *Ruled 2026-09-13 (A2 Task 8): the JDK
   and Apache clients are `fluent` catalogs, and `fluent`'s stated rule governs them —
   a request built in one method and sent in another derives NOTHING, as OkHttp's does
   (D02 §4, guard `fluent.a-built-request-is-not-an-issued-one`); §7 case 4's unresolved
   row is `combinator`'s alone. Pinned absent in `tests/e2e/test_rest_outbound_delivered.py`.*
10. **A lambda the extractor did not link** — Kotlin `-Xlambdas=class`, the default before
    Kotlin 2.0: the body-linked entry's argument is `kind: instance`, not `lambda`; the
    entry roots and derives zero routes, which under §4b is poison, so one unresolved row
    says the router exists and could not be read. The honest answer for a logged item
    (§15), not a defect of this spec.

## 14. Fixtures and proof for Part II

**Fixture sources** (facts are not committed; each new source is scanned by the tests that
analyse its module). SQS receive and the JDK/Apache client go into `fixtures/orders-service`;
Javalin into the existing `fixtures/orders-javalin`; Ktor into a **new `fixtures/orders-ktor`**
and the gateway into a **new `fixtures/orders-gateway`** (`spring-cloud-gateway-server-webflux`
5.0.0 targets the 7.x framework line, not `orders-service`'s pinned 6.1.6 — measured
2026-09-13, the only version in the local repository), both Maven, both added to
`tests/fixture_build.py`'s `PRIMED_FIXTURES` so CI primes them with the others. Versions
recorded by the plan.

| file | exercises |
|---|---|
| `orders-gateway` · `GatewayRoutes.java` | `routes().route(id, r -> …)` and `route(r -> …)` (both overloads); one route with `path` only; one with `path().and().method(GET)`; one with `or()` (two paths); one with `not()`; one lambda capturing a local (`prefix + "/**"`) and one capturing `this` — the two capture shapes that break a fixed index; every route ends in `.uri(…)`, `http://` on one, `lb://` on another |
| `orders-javalin` · `apibuilder/JavalinApi.java` | `apiBuilder(() -> path("/orders", () -> { get("/{id}", h); post(h); path("/{id}/items", () -> get(h)); }))` — two nesting levels, one verb with no path |
| `orders-ktor` · `KtorRoutes.kt` | `routing { route("/api") { get("/orders") { … }; route("/v2") { post("/orders") { … } } } }` plus one `get(otherRoute, "/x") { }` inside the body with `otherRoute` a local — the wrong-receiver case |
| `orders-service` · `httpclient/JdkOrdersClient.java` (JDK) and `httpclient/ApacheOrdersClient.java` | `newBuilder().uri(URI.create(…)).POST(…).build()` sent inline; the `newBuilder(URI)` overload; `.method("PATCH", …)`; one request built in a helper and sent elsewhere; Apache `new HttpGet(…)` and `ClassicRequestBuilder.get(…)` |
| `orders-service` · `sqs/OrderPoller.java` | `receive(opts -> opts.queue("orders-queue"), Order.class)`, `receiveMany(opts -> …)`, `receiveAsync`, and the direct `receive("direct-queue", Order.class)` overload |

**Tests, continuing §8's numbering:**

8. **Extractor, the six capture shapes** — `receiver_parameter` and `captures` pinned on
   no capture, captured local, captured `this`, instance method reference, static method
   reference, Kotlin captured `this`. Written first; fails on the current extractor.
9. **Additive-only regeneration** — §11 steps 1 and 2 as a test and a script.
10. **Gateway inbound** — the `(method, path, resolution)` set from `GatewayRoutes`:
    `GET /orders/**` resolved; `NULL /billing/**` resolved (catch-all); both `or`
    branches; the `not` route unresolved; the captured-local and captured-`this` routes
    **resolved with the right path** — the two rows a fixed-index design gets wrong.
11. **Gateway outbound** — the `uri` rows via `lambda_steps`: `http://…` and `lb://…`,
    outbound, caller = `routes()`.
12. **Javalin nesting** — `/orders/{id}`, `/orders` (the path-less `post`),
    `/orders/{id}/items`; every row's caller is the method holding `apiBuilder`.
13. **Ktor** — `/api/orders`, `/api/v2/orders`, handler NULL asserted; the `otherRoute`
    row `unresolved` and without the `/api` prefix (`receiver_arg`'s refusal).
14. **JDK client** — `POST https://…/orders` resolved through `URI.create`; `PATCH` via
    `method(String, …)`; the split request one unresolved row; Apache rows via `single_call`.
15. **SQS** — four rows on `orders-queue` (one per receive form) plus `direct-queue`;
    inbound; caller = `poll()`.
16. **Unlinked lambda** — a hand-built fact set where the body-linked entry's argument is
    `kind: instance`: one unresolved row, not silence (§13 case 10). Pinned so the logged
    Kotlin-1.x item (§15) has a measurable starting point.
17. **Declining tests** per W54's rule for each new catalog — `spring-cloud-gateway`,
    `spring-cloud-gateway-outbound`, `javalin-apibuilder`, `ktor-routing`,
    `jdk-httpclient` — and for the new rules in `spring-sqs-template.yml`, each
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
probe re-run, the `resources` slice rewrite. Part II: two optional fact fields, five
`combinator` words plus `path_arg` on an origin, five new catalogs and new rules in one
existing catalog, five fixture sources in three fixture modules (one new), eleven tests.

**Group A is one spec and two PRs.** Nine items are too many gates for one PR to be
reviewable, and Part I stands on its own:

**PR A1 — the mechanism, on the shapes already in the register**
1. The two fact fields: extractor, `facts.py`, `schema.sql`, the double-scan proof,
   tests 8 and 9. Nothing downstream reads them yet — the smallest item, and it de-risks
   everything after it.
2. `verbs`/`prefixes` → lists with `arity` + `arg_types`, the G-13 guard, ambiguity
   refusal — tests 1–4, the wrong-row test first and failing.
3. The builder form: `extends_receiver`, `origins`, pass-throughs, `resources`, both
   stacks — tests 5 and 7; `G-37` closes.
4. The corrected `RouterFunctionDsl` rules and the WebFlux `router { }` fixture —
   `W44-verb-overloads` and `GAP-1b` close.

**PR A2 — the six, mechanism first, cheapest exact rows first**
5. `origin_param`, `receiver_arg`, `negators`, `verb_arg` in the engine on hand-built
   facts — test 16 and the refusal halves of tests 10 and 13. Before it, the two catalog-data
   items: the `receive` rules in `spring-sqs-template.yml` and `spring-cloud-gateway-outbound.yml`
   (tests 15 and 11) — written first and measured; if they derive, `sqs-template-receive`
   and `G-30-outbound` close with no engine change, and **REST outbound's row empties** as
   soon as `jdk-httpclient` does.
6. Javalin — no parameter check, so it proves body nesting alone: test 12.
7. Ktor — the first user of `receiver_arg`: test 13; `ktor-routing` closes with a NULL
   handler stated on its row.
8. Gateway inbound — the first user of `origin_param`, `negators` and `verb_arg`:
   test 10. `G-30` closes.
9. `fluent`'s `url_via`, and the JDK/Apache client as `fluent` catalogs — test 14;
   `jdk-httpclient` closes; **REST outbound's row empties**.
10. Register, coverage matrix, closed block — test 18.

Each numbered item is one implement → gate → review → fix → commit loop, and each ends
with a row the register can name. The plan records the real catalog rule counts where this
spec gives arithmetic.
