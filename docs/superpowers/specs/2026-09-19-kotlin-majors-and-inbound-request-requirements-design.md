# Kotlin call-site projections, Ktor routing structure, and inbound request requirements

**Status:** design. Approved in conversation 2026-09-19, section by section; Approach B of
three ruled by the user. Self-review against the frameworks' jars, kotlinc 2.2.0 output in
the fixtures, the JVM extractor and the engines is folded in (§0); a second review against
four lenses — no false positives, future languages, conflicts, over-engineering — found two
issues the user ruled on 2026-09-19 (R1, R2) and twelve the author resolved (§0b). Not yet
planned. *(amended 2026-09-20 during implementation: implemented on `feat/kotlin-majors-and-request-requirements`, Tasks 1–15; every
place the built code differs from the section as approved carries a note like this one, and
§0c lists them all with the task that forced each.)*

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
| R1 | **False positive:** a Kotlin `@RequestParam page: Int = 0` is optional to Spring (F6, `KotlinDelegate.isOptional`) and to Micronaut, but the facts carry nullability and not "declares a default", so §5b would have written `required` | **Ruled A:** the extractor publishes `declares_default: true` on the parameter (§3c); `binder` reads it |
| R2 | **Conflict with D00 §5** ("every extractor normalizes its own mechanism into `lambda`") and with language-blindness: §3b keyed the resolve layer on the literal class names `kotlin.jvm.internal.Lambda`/`SuspendLambda` | **Ruled B:** the extractor marks the lambda **class** with a shared field `lambda_body` when it scans that class, as it marks a bridge with `bridge_of`; resolve joins on the field and names no language (§3b) |
| F10 | Every engine reads call sites through one named query — `workspace.query("call_sites")` or `parsed_call_sites(workspace)` (`grep -rn 'query("call_sites")\|parsed_call_sites' src/sextant/application/resolve`) — so there is exactly one projection point, and the pattern already exists as `resolve/effective_annotations.py` | §3 is `resolve/effective_calls.py`, a second named query |

### 0b. The four-lens review — resolved by the author

| # | Lens | Finding | Resolution |
|---|---|---|---|
| A1 | no FP | Following *every* module-local call from an origin-less body was justified by Javalin's thread-local `ApiBuilder`; the Spring router's `Supplier<RouterFunction>` bodies are origin-less too and a callee there may build routers that are never returned | origin-less following is **opt-in per entry** (`follow_calls: all`, declared by `javalin-apibuilder.yml` only); the default follows origin-carrying calls only (§4a) |
| A2 | no FP | An unresolved endpoint row on depth exhaustion or on a verb conflict is a phantom — a claim that an endpoint may exist where none was read, or where Ktor can never dispatch | depth exhaustion → one `open_questions` row (`routing_depth`); verb conflict → **silence**, stated on the catalog and in COVERAGE (§4a, §4b) |
| A3 | no FP | A bare read in a handler body (`call.request.headers["X"]`, `ctx.queryParam("q")`, `getParameter`) says the handler *reads* the value; `optional` would claim the framework serves the request without it, which the handler may not (`?: throw`) | such rows carry `requirement` **NULL**; only what the framework itself enforces is stated — `required` for the throwing APIs (`getOrFail`, `Validator.get()`), `optional`/`required` for annotations and selectors. D01 says so (§5a, §5d) |
| A4 | no FP | `HeadersRequestCondition` drops `Accept` and `Content-Type` expressions (Spring routes them into produces/consumes) | those two names are skipped when reading `headers=` (§5c; CP-25 records it) |
| A5 | no FP | `$default` sibling lookup when **both** receiver candidates exist in `symbols` | the site is left untouched, the extractor's own "ambiguity is not a guess" (§3a) |
| A6 | no FP | Ktor path variables spell `{id?}` (optional) and `{rest...}` (tailcard) | `skip_path_variables` strips `?` and `...` before comparing (§5d) |
| A7 | conflict | `requires:` already exists at catalog top level (capabilities); the same word inside a prefix entry invites a mis-read | the entry key is **`request_requirement`**, matching `request_params`/`request_reads` (§4b, §5c) |
| A8 | conflict | `spring-web.yml` (`@RestController`) and `spring-mvc.yml` (`@Controller`) can both match one class; identical endpoint rows already meet insert-if-absent, but two identical metadata rows would not | `insert_endpoint_metadata.sql` becomes insert-if-absent on the full row (§5a) |
| A9 | conflict | Quarkus REST binds `@RestQuery`/`@RestHeader`/`@RestCookie` beside the JAX-RS names (already in its `bound_by`) | added to `quarkus-rest.yml`'s `request_params` (§5b) |
| A10 | no FP | A helper call whose target is an interface/abstract method has no body; following "an implementation" would be dispatch, which is another pass's word | not followed, stated (§4a) |
| A11 | over-eng. | CP-24 proposed an embedded-server run to show `method(Post) { get {} }` never dispatches | read `HttpMethodRouteSelector.evaluate` bytecode instead — it compares the call's method to the selector's and returns `Failure` (§7) |
| A12 | over-eng. | reviewed: `absent` (Spring `!name` is real and one enum value); Javalin's `then: { method: get }` (the idiomatic typed-parameter form); the `-Xlambdas=class` fixture variant (Kotlin < 2.0 builds are common and it is CP-23's harness anyway); the two-mask unit test (cheap) | all **kept**; nothing else was found that real input does not produce |

**Future languages (lens 2), checked:** every new key is language-neutral — `header/query/cookie/param`, `required/optional/absent`, `declares_default`, `lambda_body`, `bridge_of`; the resolve layer names no language. A .NET extractor would set `declares_default` from a parameter's `HasDefault` flag and `lambda_body` on a display class if it chose to emit `instance` for closures (it need not — emitting `lambda` directly is the D00 rule). C#'s optional arguments are filled at the call site, so §3a simply never fires.

### 0c. Amended during implementation

Every sentence the implementation changed carries an inline note; this table is the index
(GUIDELINES §1.1: a probe or a measured fact that contradicts the spec changes the spec).

| # | Section | Amendment | Forced by |
|---|---|---|---|
| M1 | §3a | Mask bits index the DECLARED parameters, which exclude an extension-receiver slot carrying `receiver: true` on the sibling's declaration; when both receiver readings name a declared sibling the site is left untouched | Task 6 (`b81a2ae`), the fixture's `mount$default` bridge |
| M2 | §3b | `lambda_body` is the body method's bare SCIP symbol (`owner#name(sig_xxxxxxxx).`), not a bare descriptor; the recognised superclasses are `Lambda`, `SuspendLambda`, `FunctionReferenceImpl` and `AdaptedFunctionReference`; a non-capturing class-compiled lambda is a singleton read as `GETSTATIC …$1.INSTANCE`, an `enum`-kind argument, and is projected the same way | Tasks 2, 5, 6 (`645dd1d`, `eefca79`, `b81a2ae`), CP-23 Q9 (`e6497f0`) |
| M3 | §4a | The origin must flow into the helper as an ARGUMENT `{parameter, value: k}`; a member call ON the origin is a stated boundary. Depth exhaustion files ONE `routing_depth` question per run with every deep chain as a candidate `{callee, caller, depth}`, identity NULL. `reset_open_questions` runs before `derive_endpoints` | Task 8 (`11cc5ce`, `f488c3e`) |
| M4 | §4b, §4c | `handle` carries `path: ""` (it registers on the receiver node itself); a NON-terminal verb rule with neither `verb` nor `verb_arg` is refused at load; a predicate- or variable-valued requirement is name-only and `resolved` | Task 10 (`e727f1c`), fix round (`c2d6792`) |
| M5 | §4d | Alternatives collapsing to ONE address keep the INTERSECTION of their requirements, never the union; fan-out over `all_methods` copies the full set | fix round (`c2d6792`), the Gateway header-versioning idiom |
| M6 | §5a | One writer, `record_request_requirements`, runs once per resolve below `apply_protocol_hints`, joining the combinator's `route_requirements` stash to `endpoints`; `evidence` is `compiler` (D00 §4's closed set) on every requirement row | Tasks 7, 11 (`51f363b`, `c3546e7`) |
| M7 | §5b | `binder` never reads the type reference's `nullable` (Java's every reference type is `nullable: true` by rule); `optional` flips on a DECLARATION annotation in the shape model's `nullability.nullable` list, widened to every spelling Spring's simple-name rule and Micronaut's transformers accept (CP-25 rows 3, 8); the type names live on the catalog as `optional_types` and `skip_types`; `skip_path_variables` on an entry whose read serves path and query alike | Task 12 (`a45c0a3`, `6107170`) |
| M8 | §5c | The servlet router twin (`spring-mvc-router.yml`) reads `RequestPredicates.param`, kind `param` — it has no `queryParam` (CP-26 row 2b) | Task 11 (`c3546e7`) |
| M9 | §5d | `via` is a mapping `{ owner, method }`; Ktor's `via` owners are the 3.0.3 class overrides a handler body names (`RoutingCall`, `RoutingRequest`), not the interfaces; `required_when_thrown: <exception>` marks an INLINED throwing read (`getOrFail` is `inline`); a read's `requirement` is `required` or `optional`, never `absent`; a Javalin flat (`single_call`) row's lambda reads are invisible, a stated boundary | Tasks 13–14 (`d4ffd1a`, `e8cf642`) |
| M10 | §7 | CP-25 is shared by three sections: row 1 (Javalin `ApiBuilder`'s thread-local guard behind `follow_calls: all`), rows 2–12 (§5b's binder rules), rows 13–17 (§5c's expression grammar and §5d's reads) | Tasks 8, 12, 13–14 |
| M11 | §1, §9 | The Ktor fixture gained `selectors()`, `reads()`, `defaults()` and the `mount` DSL function; the test-only catalog is built inside `tests/application/test_ktor_defaults_fixture.py`; a new `fixtures/orders-servlet` carries the Servlet reads; `KotlinParamController.kt` carries the R1 case | Tasks 6, 12, 14 |
| M12 | §10 | The "request requirements" line is a hand-written `Request requirements` row per REST-inbound framework line in COVERAGE §5.1's table (nine ✅, nine Not recorded), not a line in the generated rollup, which has no place for one | Task 15 |
| M13 | §5b | `declares_default` → `optional` assumes `kotlin-reflect` on the runtime classpath: Spring reads a Kotlin default only behind `KotlinDetector.isKotlinReflectPresent()` (CP-25 row 3); stated on `spring-mvc.yml`/`spring-web.yml`, COVERAGE and `OI-105` | whole-branch review, item 2 |
| M14 | §5a, §5c | An inbound `value` is the framework's OWN spelling of the demand — a literal for Ktor and Spring, the regex as written for Spring Cloud Gateway (matched as a whole-string regex); D01 §3, D02 §2k and M06 say so, and M06 compares equality only where the spelling is a literal | whole-branch review, item 3 |
| M15 | §5d | "A cross-framework match is impossible in practice" corrected: every catalog loads on every resolve, so a Spring MVC handler's `HttpServletRequest.getParameter`/`getHeader` calls ARE recorded through the Servlet catalogs' entries — true rows, kind `param`/`header`, `requirement` NULL; what cannot happen is a wrong one | whole-branch review, item 4 |
| M16 | §5b, §7 | A parameter's own name is refused where the binder respells it: `fallback_spelling: hyphenated \| hyphenated-capitalized` on `micronaut-http.yml`'s three entries mirrors `AbstractArgumentBinder.doResolve` retrying `NameUtils.hyphenate` (the header binder's `capitalize` first) — a name the fallback respells writes `name` NULL, `unresolved`; one it does not (`tenant`) stands; a written name is kept (`OI-104`). CP-25 gains row 18 | whole-branch review, item 1 (Critical) |

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
| 2 | class-compiled Kotlin lambdas → `lambda` arguments | extractor `lambda_body` on the class (§3b, R2) + `resolve/effective_calls.py` |
| 2′ | `declares_default` on Kotlin parameters | extractor `KotlinNullability.java` + D00 (§3c, R1) |
| 3 | follow origin-carrying module-local calls | `engines/combinator.py` (§4a) |
| 4 | selector prefixes, `getters:` value tables, verb-less `handle`, `all_methods` | `engines/combinator.py` + `ktor-routing.yml` (§4b–c) |
| 5 | `endpoint_metadata.requirement` + inbound writer | `schema.sql`, `insert_endpoint_metadata.sql`, `workspace.py`, `resolve/request_requirements.py` (§5a) |
| 6 | `request_params` — parameter annotations | `shapes/contracts.py` + seven catalogs (§5b) |
| 7 | route-tree predicates as requirements | combinator `_Route.requirements`, annotation engine, Gateway (§5c) |
| 8 | `request_reads` — handler-body reads | `resolve/request_requirements.py` + four catalogs: `ktor-routing`, `javalin`, `jakarta-servlet`, `javax-servlet` (§5d) |
| 9 | probes, fixtures, register, COVERAGE, D00/D01/D02/M06 | §7, §9, §10 |

Approach B stands: the two projections stay one join each in resolve, keyed on **shared
fields the extractor publishes on the declaration it scans** (`bridge_of`, `lambda_body`),
never on a language's class names. Where the extractor lacked a fact (R1, R2), the fact is
added there — the pattern OI-81 set.

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
  receiver question is settled by which of the two candidate siblings exists in `symbols`;
  when **both** exist the site is left untouched — the extractor's own "ambiguity is not a
  guess", A5).
- Arguments: the mask arguments are `kind: int` (D00 §5 — "constant instructions"), value
  read as an integer; for declared parameter *i* with bit *i* of mask ⌊i/32⌋ set, the
  argument becomes `{kind: unresolved, reason: defaulted}`; mask and marker slots are
  dropped. *(amended 2026-09-20 during implementation: *i* counts the parameters the author DECLARED — an
  extension receiver, the sibling's slot 0 carrying `receiver: true`, is not one of them, so
  bit 0 is the first slot after it; measured on the fixture's `mount$default`, M1.)* A defaulted path therefore reaches a rule as unresolved — an unresolved row, never
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

### 3b. Class-compiled Kotlin lambdas — `lambda_body` (R2)

**Extractor.** When `ClassScanner` scans a class whose superclass chain reaches
`kotlin.jvm.internal.Lambda` or `kotlin.coroutines.jvm.internal.SuspendLambda` *(amended 2026-09-20 during implementation: or `kotlin.jvm.internal.FunctionReferenceImpl` or
`kotlin.jvm.internal.AdaptedFunctionReference` — a function reference `::listOrders` compiles
to a `FunctionReferenceImpl` subclass in both lambda modes, with no `invokeSuspend` even when
the referenced function suspends; its typed `invoke` is the body, and that body's call to the
referenced function is the trace layer's to follow, CP-23 Q9, M2)* (both
`public abstract class` in kotlin-stdlib 2.2.0 — `javap -cp ~/.m2/repository/org/jetbrains/kotlin/kotlin-stdlib/2.2.0/kotlin-stdlib-2.2.0.jar kotlin.jvm.internal.Lambda kotlin.coroutines.jvm.internal.SuspendLambda`;
the direct superclass is read off the class file, and the two names are the extractor's
knowledge of its own compiler, where D00 §5 puts it), the class's **type** symbol fact
carries **`lambda_body: "<body method's bare descriptor>"`** *(amended 2026-09-20 during implementation: the body method's bare SCIP
symbol, `owner#name(sig_xxxxxxxx).`, the spelling a `lambda` argument's `symbol` already has,
so the join is on equal strings, M2)*, absent otherwise — the same
shape and placement as `bridge_of`. The body method is:
- `invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;` when the class declares one (a
  suspend lambda: `invoke` only builds the continuation and calls `invokeSuspend`; the
  author's statements are in `invokeSuspend`) — **CP-23 records this**;
- otherwise the one `invoke` that is not `ACC_SYNTHETIC` (the typed one; the erased
  `invoke(Object)` is the compiler's bridge and is synthetic) — **CP-23**.
A class with neither (unreadable) carries no `lambda_body` and is left alone. D00 §5 gains
the field beside `bridge_of`; a Gradle test on a `-Xlambdas=class` sample pins both shapes.

**Resolve.** An argument `{kind: instance, symbol: C, source}` whose type fact carries
`lambda_body: B` becomes `{kind: lambda, symbol: B, captures: 0, source}`. *(amended 2026-09-20 during implementation: so does an `enum`-kind argument naming `C` — a NON-capturing class-compiled lambda is
a singleton the call site reads as `GETSTATIC C.INSTANCE`, which D00 §5 classifies as `enum`;
the join key is the same shared field, M2.)* The join names no
language: any extractor that emits `instance` for its own closure classes and marks them the
same way gets the same projection; one that already emits `lambda` (D00's rule) never needs
it.

`captures: 0` is exact: constructor-captured values are fields of `C`, never leading
parameters of `B`, so the interface's own parameters start at index 0 and a routing walk's
`origin_param: 0` lands on the `Route` unchanged. A body that reads a captured field where a
rule wants a path gets a `field` argument and an unresolved row — honest, not silent.

**Left alone, stated:** a Java anonymous class implementing `Function1` (not a Kotlin lambda
class); a Kotlin `fun interface` SAM conversion (already `invokedynamic`); a lambda class
from a library (its type fact is scanned too, so it IS marked — but its body has no
`call_sites` in the module facts, so a walk into it reads nothing).

### 3c. `declares_default` on parameters (R1)

`KotlinNullability.java` already iterates every function's `KmValueParameter`
(`declaredTypes`, line 306) to project nullability; it additionally reads
`kotlin.metadata.Attributes.getDeclaresDefaultValue(parameter)` and the scanner writes
**`declares_default: true`** on that parameter fact, absent otherwise (as `receiver` is).
D00 §6 documents it beside the nullability projection: a shared field, not `ext.kotlin`,
because a binder rule compares it across languages (a .NET extractor sets it from a
parameter's `HasDefault`). Consumed by §5b's `binder` only.

### 3d. What each engine sees afterwards

A plain call to the real function with some arguments unreadable, and a plain lambda body to
walk. No engine learns the word "Kotlin". `kotlin-default-bridge-calls` and
`kotlin-class-lambdas` close for all thirteen engines at once; `kotlin-null-handler` closes
because `handler_arg` now names `B`, which `roots`/`reachability` can walk (F1).

**Cost per resolve:** one join `call_sites × symbols` on target (3a), one join of `instance`
arguments × `symbols` on `lambda_body` (3b). Both once, set-based, before any engine.

---

## 4. The combinator engine — helpers, selectors, `handle`

### 4a. Following helper calls

In `_body_routes`, a call site that is not a catalog word and whose target is a module-local
method with a body is **followed**:

- **Body with an origin** (Ktor `Route`; Spring DSL receiver): followed when the origin flows
  into the call — as the site's `receiver`, or as argument *i* (`{kind: parameter, value:
  origin}` after `captures` adjustment, exactly the test `_receiver_argument_is_the_origin`
  already makes). *(amended 2026-09-20 during implementation: as an ARGUMENT only — a member call ON the origin, the
  origin as the callee's receiver, is not followed, since no receiver-to-`this` mapping is
  guessed; a stated boundary, M3.)* Inside the callee, that parameter index is the new `origin_parameter` and
  the same walk runs. A verb on any other `Route` inside the callee is silence, as today.
- **Body without an origin:** followed only where the entry declares **`follow_calls:
  all`** — `javalin-apibuilder.yml`'s `apiBuilder`/`path` bodies, because `ApiBuilder.get`
  throws outside `apiBuilder { }` (thread-local), so a helper reaching it can only ever be
  called from inside the block. The Spring router's `Supplier<RouterFunction>` bodies are
  origin-less and declare nothing: a callee there may build routers that are never
  returned, and following it would attach them (A1). They stay a miss, as today.
- The caller's accumulated scope — path prefix, verb, media, requirements (§5c) — carries
  into the callee: `route("/api") { api() }` gives `/api/helper`.
- **Guards, no semantics:** a visited set keyed `(callee symbol, origin index)`; depth bound
  16 (Ktor's own documented structures nest 3–4). Exhausting the bound publishes **no
  endpoint row** — a row there would claim an address nobody read (A2) — but one
  `open_questions` row of a new kind **`routing_depth`** (endpoint identity = the entry's
  caller; candidates = the callee symbol; one renderer arm, as every kind costs). *(amended 2026-09-20 during implementation: ONE row per run, method and path NULL — both genuinely unread — so every deep chain
  of the run shares one identity and is one candidate `{callee, caller, depth}` of it, the
  `service_identity._merged` shape; and `reset_open_questions` now runs ABOVE
  `derive_endpoints`, because the combinator files this question while deriving, M3.)*
- **Boundaries stated:** a routing block held in a variable and invoked later (`val b:
  Route.() -> Unit = {…}; b()`) is `Function1.invoke` on a local — not followed; a callee
  that is an interface or abstract method has no body — not followed (A10).

### 4b. Selector prefixes

A `prefixes:` entry may now declare, besides `path_arg`, any of `verb_arg`, `media_arg` +
`fills`, `request_requirement` (A7 — `requires:` is already the top-level capabilities key),
or none of them (a pure scope). Measured signatures (F4, F5):

```yaml
prefixes:
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: route,  arity: 4, receiver_arg: 0, path_arg: 1, verb_arg: 2, body_arg: 3, origin_param: 0 }   # ktor-route-with-verb
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: method, arity: 3, receiver_arg: 0, verb_arg: 1, body_arg: 2, origin_param: 0 }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: accept,      arity: 3, receiver_arg: 0, media_arg: 1, fills: produces, body_arg: 2, origin_param: 0 }   # ContentType[] vararg
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: contentType, arity: 3, receiver_arg: 0, media_arg: 1, fills: consumes, body_arg: 2, origin_param: 0 }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: header,        arity: 4, receiver_arg: 0, body_arg: 3, origin_param: 0,
      request_requirement: { kind: header, name_arg: 1, value_arg: 2, requirement: required } }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: param,         arity: 3, receiver_arg: 0, body_arg: 2, origin_param: 0,
      request_requirement: { kind: query, name_arg: 1, requirement: required } }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: param,         arity: 4, receiver_arg: 0, body_arg: 3, origin_param: 0,
      request_requirement: { kind: query, name_arg: 1, value_arg: 2, requirement: required } }
  - { owner: io.ktor.server.routing.RoutingBuilderKt, method: optionalParam, arity: 3, receiver_arg: 0, body_arg: 2, origin_param: 0,
      request_requirement: { kind: query, name_arg: 1, requirement: optional } }
```

*(amended 2026-09-20 during implementation: `request_requirement` is `{kind, name_arg, value_arg?,
requirement}` on a prefix, on a `pass_through` continuation (the Gateway's `header`/`query`/
`cookie`) and as a verb-shaped `vocabulary.request_requirement` rule (§5c); `name_arg` must be a
string literal or the row is `name` NULL, `unresolved`; a `value_arg` the call does not carry
reads value NULL, and one it carries as anything but a string literal — a predicate, a variable
— reads value NULL too and the row stays `resolved`: name-only, "name required, value unread",
M4.)*

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
dispatch — `HttpMethodRouteSelector.evaluate` compares the call's method to its own and
returns `Failure` (**CP-24 reads the bytecode**). It publishes **nothing** (A2): a row of
either verb would be an endpoint that is not on the wire, and an unresolved row a phantom.
Stated on the catalog and in COVERAGE.

### 4c. `handle` — a verb-less terminal

```yaml
terminals:
  - { owner: io.ktor.server.routing.Route, method: handle, arity: 1, terminal: true, path: "", handler_arg: 0 }   # amended 2026-09-20: `terminal: true`, `path: ""` (M4)
all_methods: [GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS]   # HttpMethod.DefaultMethods, 3.0.3 (F4)
```

A terminal (or verb) entry with no `verb` takes the scope's verb; with none in scope it
expands through the catalog's `all_methods` — the word `spring-mvc.yml` already uses for a
bare `@RequestMapping`, one row per method (user ruling). The owner is the `Route`
interface (F4); the receiver is the site's own `receiver`, tested against the origin as
member verbs already are. `all_methods` is now a combinator key too, validated as a
non-empty list of upper-case tokens. *(amended 2026-09-20 during implementation: `handle` carries `path: ""` — it registers on the receiver
node itself and serves exactly the prefix chain, `/` at the root, never `/**`; and the loader
now refuses a NON-terminal verb rule with neither `verb` nor `verb_arg`, which it used to read
silently as `verb: null`, M4.)*

### 4d. `_Route.requirements`

`_Route` gains `requirements: tuple[_Requirement, ...]`, each `(kind, name, value,
requirement, resolution, evidence)`, inherited down scopes and written per emitted row (§5a)
with `caller` = the row's handler symbol — which keeps two `GET /orders` under different
`header` selectors apart in the side table after they collapse to one address in
`endpoints` (Ktor does not refuse the pair at startup; there is no `duplicate: conflict` on
the catalog and nothing to mirror). *(amended 2026-09-20 during implementation: two routes with the SAME handler that
collapse to one row are two alternatives for one address, and a request satisfying either is
served — so the kept row carries the INTERSECTION of their requirement sets, never the union;
the Gateway's header-versioning idiom, two `route()`s on `/api/**` differing in
`header("X-Version", …)`, published `/api/**` demanding both versions until this. Fan-out over
`all_methods` is one route seven times and copies the whole set, M5.)*

---

## 5. Inbound request requirements

### 5a. Schema and writer

`endpoint_metadata` gains **`requirement TEXT`**, closed set `required | optional | absent`,
NULL on every outbound row (an outbound entry is something *sent*). `schema.sql`,
`insert_endpoint_metadata.sql`, the `endpoint_metadata` named query and D01 §3 learn the
column; the table is rebuilt every resolve, so nothing migrates. Inbound rows: `direction =
inbound`; `caller` = handler symbol; `kind ∈ {header, query, cookie, param}` — `param` only
for the two APIs that cannot tell query from form (Spring `@RequestParam`, Servlet
`getParameter`), said on the catalog entry; `value` = a fixed demanded value or NULL *(amended 2026-09-20 at the whole-branch review: the framework's OWN spelling of the demanded value — a literal for Ktor's `header(name, value)` and Spring's `params = "view=summary"`, and the regex AS WRITTEN for Spring Cloud Gateway's `header("X-Request-Id", "\\d+")`, which the framework matches as a whole-string regex (`Pattern.asMatchPredicate` in `HeaderRoutePredicateFactory`, `String.matches` in the query and cookie factories — spring-cloud-gateway-server-webflux 5.0.0, `javap`); M14)*. A read
whose name is not a string literal/constant produces `name` NULL, `resolution = unresolved`
— "this handler reads a header it does not name" is a different statement from "reads
none", the reasoning the outbound table was built on.

**What `requirement` means, and NULL.** The column states what the **framework enforces**
— its binder or its routing tree — never what the handler body does with the value.
`required`: the framework rejects a request without it; `optional`: the framework serves
the request without it (a binder default, `required=false`, `optionalParam`);
`absent`: the framework requires it to be missing. **NULL** on an inbound row means the
code states nothing about it — a bare read in a handler body (§5d) is such a row: *this
handler reads header X* is all it says (A3). NULL on an outbound row is the existing
meaning (an entry sent).

`resolve/request_requirements.py` owns the writer: one function taking `(endpoint identity,
handler, entries)` from the three mechanisms and one `derive("endpoint_metadata_insert")`
call per engine run, after the engine's endpoints (the fluent engine's order, for the same
reason: an entry names a row that has to exist). *(amended 2026-09-20 during implementation: one call per RESOLVE, not per
engine — `record_request_requirements` runs once, below `apply_protocol_hints`, because an
entry names its row by the identity columns and `protocol` is final only there; the
combinator writes its selector and predicate requirements to a `route_requirements` stash
beside its rows, re-created by `derive_endpoints`, and the writer joins the stash to
`endpoints`. Every requirement row's `evidence` is `compiler`, D00 §4's closed set, M6.)* The insert is **insert-if-absent on the
full row** (A8): `spring-web.yml` and `spring-mvc.yml` can both match one `@RestController`
class, and their identical endpoint rows already meet the same guard.

### 5b. Mechanism 1 — parameter annotations (`request_params`)

Read in `shapes/contracts.py`, beside `request_body`, over the handler's `parameters`:

```yaml
request_params:
  - { annotation: org.springframework.web.bind.annotation.RequestParam,  kind: param,  name_attrs: [name, value], requirement: binder, required_attr: required, default_attr: defaultValue }
  - { annotation: org.springframework.web.bind.annotation.RequestHeader, kind: header, name_attrs: [name, value], requirement: binder, required_attr: required, default_attr: defaultValue }
  - { annotation: org.springframework.web.bind.annotation.CookieValue,   kind: cookie, name_attrs: [name, value], requirement: binder, required_attr: required, default_attr: defaultValue }
```

- **`requirement: binder`** is F6 exactly: `optional` when `required_attr` is `false`, when
  `default_attr` is present, when the parameter type is `java.util.Optional`, when the
  parameter's type reference is `nullable: true` (Kotlin `?` and `@Nullable` both land
  there, D00 §6), or when the parameter carries `declares_default: true` (§3c, R1); else
  `required`. *(amended 2026-09-20 during implementation: the type reference's `nullable` is NOT read — D00 §5 records
  every Java reference type `nullable: true` by language rule, so reading it would make every
  `@RequestParam String` optional; the disjunct is a DECLARATION annotation on the parameter
  whose descriptor is in the shape model's `nullability.nullable` list, which is what Spring's
  `hasNullableAnnotation()` reads by simple name (CP-25 row 3) and what Micronaut's transformers
  map onto `jakarta.annotation.Nullable` (row 8) — the list widened to every measured
  spelling; kotlinc's `@Nullable` lands there too. `java.util.Optional` is named on the entry as
  `optional_types`, because the pass names no language's types, M7.)* *(amended 2026-09-20 at the whole-branch review: the
  `declares_default` → `optional` step has a RUNTIME prerequisite the row does not check — Spring
  reads a Kotlin default and `KParameter.isOptional()` only behind
  `KotlinDetector.isKotlinReflectPresent()` (CP-25 row 3), so without `kotlin-reflect` on the
  runtime classpath `@RequestParam page: Int = 0` is `required`. The row assumes it present —
  nearly always true, Initializr and `jackson-module-kotlin` both bring it — stated on the two
  Spring catalogs, in COVERAGE, and as `docs/open-issues.md` OI-105; a coordinate-gated variant
  needs transitive dependency resolution, M13.)*
- **`requirement: optional`** is JAX-RS's rule: absent → null or `@DefaultValue`, never a
  400 (`default_annotation: jakarta.ws.rs.DefaultValue`, informational — it does not change
  the requirement).
- **Name:** the first present of `name_attrs`, else the parameter's declared `name`; a
  parameter compiled without names → unresolved row. *(amended 2026-09-20 at the whole-branch review: else the
  parameter's declared name ONLY where the binder requires it by that name alone. Micronaut's
  `AbstractArgumentBinder.doResolve` reads the parameter's own name and, finding nothing,
  retries `getFallbackFormat(argument)` — `NameUtils.hyphenate(name)` for `@QueryValue`/
  `@CookieValue` (`pageSize` → `page-size`), `hyphenate(capitalize(name), false)` for `@Header`
  (`xTenant` → `x-Tenant`; CP-25 row 18) — so `@QueryValue String pageSize` is served by
  `?page-size=` alone and `query pageSize required` would state a name the framework does not
  require by itself. The entry's `fallback_spelling: hyphenated | hyphenated-capitalized`
  names the binder's second spelling, mirrored from the bytecode in
  `request_requirements.py`; where it differs from the declared name (exactly for a query
  parameter or cookie, case-insensitively for a header — the framework's own
  `CaseInsensitiveMutableHttpHeaders`) the row keeps its requirement and names nothing
  (`name` NULL, `unresolved`); where the two coincide (`tenant`) the name stands. A WRITTEN
  name stands as written; that `doResolve` retries the parameter's hyphenated name after a
  written one too is `docs/open-issues.md` OI-104, stated not built. Only `micronaut-http.yml`
  declares the key, M16.)*
- **Skipped, stated on the catalog:** whole-map bindings (`Map`, `MultiValueMap`,
  `HttpHeaders` types — no name); Micronaut's *unannotated* by-name binding. *(amended 2026-09-20 during implementation: the whole-map types are the entry's `skip_types` list, by exact erased type;
  `skip_path_variables: true` on an entry whose read serves path and query alike — reactive
  routes' `@Param`, Vert.x's `getParam` — drops a name that is one of the row's own path
  variables; and an annotation use the scanner did not read (`args` absent) writes nothing, M7.)*

Catalogs and their entries (attributes measured 2026-09-19, F8/F9):

| Catalog | Entries | Rule |
|---|---|---|
| `spring-mvc.yml`, `spring-web.yml` | `@RequestParam`→param, `@RequestHeader`→header, `@CookieValue`→cookie | binder |
| `jakarta-jaxrs.yml`, `javax-jaxrs.yml`, `quarkus-rest.yml` | `@QueryParam`→query, `@HeaderParam`→header, `@CookieParam`→cookie (`value` only) | optional |
| `quarkus-rest.yml` additionally | `org.jboss.resteasy.reactive.RestQuery`→query, `RestHeader`→header, `RestCookie`→cookie (`value` only; the name defaults to the parameter's — A9) | optional |
| `micronaut-http.yml` | `@QueryValue`→query (`value`, `defaultValue`), `@Header`→header (`value`, `name`, `defaultValue`), `@CookieValue`→cookie | binder, no `required_attr` |
| `quarkus-reactive-routes.yml` | `@Param`→query, `@Header`→header | optional — **CP-25 confirms** absent → null |

### 5c. Mechanism 2 — route-tree predicates

- **Spring `@RequestMapping(params=, headers=)`**, read where `discriminators` already reads
  the two attributes (annotation engine): `name` → required; `name=v` → required, value `v`;
  `!name` → `absent`; `name!=v` → `optional`, the excluded value lost (stated). Class-level
  and method-level union, as `ParamsRequestCondition.combine` does. A `headers=` expression
  naming `Accept` or `Content-Type` is **skipped**: `HeadersRequestCondition` drops them and
  Spring reads them as produces/consumes instead (A4; CP-25 records it).
- **Spring router DSL, Java:** `RequestPredicates.queryParam(String, String)` → query,
  required, value; `queryParam(String, Predicate)` → query, required, value NULL;
  `headers(Predicate<Headers>)` — an arbitrary function, unreadable — nothing, stated.
  *(amended 2026-09-20 during implementation: a `value_arg` the call carries as anything but a string
  literal — the `Predicate` here, a variable in the String overload's value position — reads
  value NULL and the row stays `resolved`: the name is what the requirement is keyed on and it
  was read, "name required, value unread", M4.)*
  Declared as a new `request_requirement:` list beside `media:` in both router catalogs. *(amended 2026-09-20 during implementation: the servlet twin, `spring-mvc-router.yml`, declares `RequestPredicates.param`,
  kind `param` — it has no `queryParam`, and `ParamPredicate.test` reads `ServerRequest.param`,
  backed by `getParameterMap`, query and form alike (CP-26 rows 2, 2b), M8.)* (Kotlin's
  `queryParam` is the route-declaring overload already in `slice.outside`; unchanged.)
- **Spring Cloud Gateway** (`PredicateSpec` and `BooleanSpec$BooleanOpSpec`, 5.0.0 — F-row
  measured: `header(String)`, `header(String, String)`, `query(String)`, `query(String,
  String)`, `query(String, Predicate)`, `cookie(String, String)`): the `pass_through: true`
  continuations become `request_requirement:` continuations — header/query/cookie, required, value =
  the regex string where one is given, NULL for the `Predicate` form. *(amended 2026-09-20 at the whole-branch review: the
  `value` column carries the regex AS WRITTEN — `"\\d+"` for `header("X-Request-Id", "\\d+")`
  — because that is the framework's own spelling of the demand (`HeaderRoutePredicateFactory`
  matches it as a whole-string regex, `Pattern.compile(regex).asMatchPredicate()`; the query
  and cookie factories use `String.matches` — spring-cloud-gateway-server-webflux 5.0.0,
  `javap`); it is not a literal a client must send, and a consumer
  comparing values for equality (M06's request test) does so only where the spelling is a
  literal, M14.)* The properties side
  (`Header=X,regex`, `Query=x[,regex]`, `Cookie=name,regex`) is **not** in scope: property-
  declared routes derive nothing today (`gateway-properties-routes`, open), and their
  predicates land with that item, on the same `request_requirement:` word.
- **Ktor:** §4b.

### 5d. Mechanism 3 — handler reads (`request_reads`)

One set-based pass in `resolve/request_requirements.py`: for every emitted inbound row with a
handler, the handler body's `call_sites_effective` rows are matched against the catalog's
list. For Ktor the handler is the §3b body method (or the invokedynamic synthetic).

```yaml
request_reads:
  # Ktor 3.0.3 — the three containers all end in `StringValues.get(String)`, so the
  # receiver's PRODUCING call says which one (`via`, one `_producing_site` step)
  # amended 2026-09-20 (M9): `via` is a mapping, and the owners are the 3.0.3 CLASS overrides
  # a handler body's bytecode names — `RoutingContext.getCall()` is a `RoutingCall` —
  # never the interfaces this block first listed
  - { via: { owner: io.ktor.server.routing.RoutingRequest, method: getHeaders },         method: get, arity: 1, name_arg: 0, kind: header }   # requirement NULL: a read states nothing (A3)
  - { via: { owner: io.ktor.server.routing.RoutingRequest, method: getQueryParameters }, method: get, arity: 1, name_arg: 0, kind: query,
      required_when_thrown: io.ktor.server.plugins.MissingRequestParameterException }
  - { via: { owner: io.ktor.server.routing.RoutingCall,    method: getParameters },      method: get, arity: 1, name_arg: 0, kind: query, skip_path_variables: true,
      required_when_thrown: io.ktor.server.plugins.MissingRequestParameterException }
  - { owner: io.ktor.server.util.ParametersKt, method: getOrFail, arity: 2, name_arg: 1, kind: query, requirement: required }
```

- `skip_path_variables: true`: `call.parameters` merges path and query; a name equal to a
  `{name}` segment of the row's path — `?` and `...` suffixes stripped (`{id?}`,
  `{rest...}`, A6) — is the path variable and is not recorded.
- An entry with no `requirement` writes NULL (A3). `requirement: required` is declared only
  on APIs that reject the request themselves: `getOrFail` (`MissingRequestParameterException`
  → 400), Javalin's `Validator#get()`. *(amended 2026-09-20 during implementation: `getOrFail` is `inline`, so a Kotlin caller
  carries its BODY — `Parameters.get(name); ifnonnull; new MissingRequestParameterException;
  athrow` — and never a call to `ParametersKt.getOrFail`; the `owner` entry matches only a
  caller that emits the call. **`required_when_thrown: <exception>`** on a `via` entry reads
  the inlined shape: the read is `required` when the SAME body constructs that exception with
  the read's own literal name as its first argument; a bare `get` with the handler's own
  `?: throw` stays NULL. A read's `requirement` is `required` or `optional`, never `absent` —
  no read API demands absence, M9.)*
- **Javalin 6.4.0** (F7): `Context#queryParam(String)`→query, `header(String)`→header,
  `cookie(String)`→cookie, all `arity: 1`, requirement NULL; `queryParamAsClass(String,
  Class)` / `headerAsClass(String, Class)` → `required` **when** the result chain reaches
  `Validator#get()` (`then: { method: get, requirement: required }`, one result→receiver
  step), else NULL (`getOrDefault`, `allowNullable`, or an unread chain).
- **Servlet ×2:** `HttpServletRequest#getParameter(String)`→param, `getHeader(String)`→header,
  requirement NULL.
- **One list per framework, applied by handler, not by catalog.** The `request_reads` of
  every loaded catalog are unioned and matched against every inbound row's handler body:
  Javalin declares its list once in `javalin.yml` and the rows `javalin-apibuilder.yml`
  derives get the same reads without a second copy; a cross-framework match is impossible
  in practice (`via`/`owner` are framework types), and each written row's `evidence` names
  the catalog its entry came from. *(amended 2026-09-20 during implementation: `evidence` is `compiler`, D00 §4's closed set —
  a catalog id is not one of its values — M6.)* *(amended 2026-09-20 at the whole-branch review: "impossible in
  practice" is false as written. Every catalog loads on every resolve, so the Servlet
  catalogs' `getParameter`/`getHeader` entries match ANY handler body that calls them — a
  Spring MVC handler taking `HttpServletRequest` included — and that is a TRUE row: the
  handler reads the value, kind `param`/`header`, `requirement` NULL (rows 16–17). What
  cannot happen is a WRONG cross-framework row, because `owner`/`via` name the API type
  the read is made on and a body either calls it or does not, M15.)*
- **Boundaries stated:** the handler body only, never methods it delegates to; frameworks
  whose handlers bind by annotation declare no `request_reads` in this spec. *(amended 2026-09-20 during implementation: and a Javalin FLAT row's reads are invisible — a `single_call` row's `handler` is the
  registering method (`OrderApp#flat`), not the `Handler` lambda it passes, so
  `app.get("/x", ctx -> ctx.queryParam("q"))` writes nothing; the `ApiBuilder` rows carry
  the lambda body as `handler` and read fully, M9.)*

### 5e. Downstream

The bundle exports the column with the table (already whole, `_EXPORTED`). The module
document does not render metadata for outbound today and will not here. `M06-stitcher.md`
gets one paragraph: when built, a client lacking a server's `required` header/query/cookie
entry fails the request-compatibility test the way a missing required body field does;
`optional` and `absent` entries do not affect matching. D01 §3 documents the column and the
inbound `caller` meaning; D02 documents `request_params`, `request_reads`, `request_requirement`,
`verb_values`/`media_values.getters`, verb-less terminals and `all_methods` on combinator
catalogs.

**Cost per resolve:** 5b reads parameters already loaded with the handler; 5c runs inside
walks that already run; 5d is one query joining handler symbols × `call_sites_effective` ×
the catalog's `(owner|via, method, arity)` list.

---

## 6. What this design does not do, and what it logs

| Not built | Why | Where recorded |
|---|---|---|
| `name!=value` loses the excluded value; `headers(Predicate)` unread | no column / unreadable function | catalog comments, COVERAGE |
| `call.request.headers` reads outside the handler body | the walk's boundary is the handler | COVERAGE boundary |
| a route under disagreeing `method` selectors | Ktor never dispatches it; a row would be a phantom | catalog comment, COVERAGE |
| helper calls from the Spring router's `Supplier` bodies | origin-less and not thread-local | COVERAGE boundary |
| `dsl-media-route` (the `accept(JSON) { }` handler-taking overloads) | a media rule that is also a route — not this spec's words | stays on the register |
| Java anonymous `Function1` classes; library lambda classes | not module-local Kotlin lambda classes | §3b |
| `$default` calls with no `bridge_of` | the extractor's stated declines | §3a |

---

## 7. The four probes — recorded before any key is written

Each is a committed harness under `scripts/probes/cpNN_*/` with a generated observation
table naming the jar-reported version (`tests/architecture/test_probe_provenance.py`, §5.4).

| Probe | Records | Forces |
|---|---|---|
| **CP-23** kotlinc 2.2.0 call-site shapes — a Maven module beside `orders-ktor` compiled twice, default and `-Xlambdas=class` | a `$default` call's mask literal and bit meaning (F3), receiver vs static sibling, a two-mask (33-parameter) function; a lambda class's superclass (`Lambda`/`SuspendLambda`), its `invoke`/`invokeSuspend` methods and synthetic flags, constructor-captured fields; `@kotlin.Metadata`'s `declaresDefaultValue` flag on a defaulted parameter | §3a, §3b, §3c |
| **CP-24** Ktor 3.0.3 routing surface | the selector signatures (F4), `HttpMethod.DefaultMethods`, the `HttpMethod$Companion.get*` and `ContentType$Application.get*` getters (F5), `ParametersKt.getOrFail` and what it throws, the `StringValues.get` owners of the three containers; `HttpMethodRouteSelector.evaluate` returning `Failure` on a method mismatch (A11 — bytecode, no server run) | §4b, §4c, §5d |
| **CP-25** binder rules — spring-web 6.1.6, micronaut-http 4.7.6, RESTEasy Reactive, quarkus-reactive-routes, javalin 6.4.0, jakarta.servlet | F6's predicate; `HeadersRequestCondition` dropping `Accept`/`Content-Type` (A4); Micronaut's required-ness (nullability/`Optional`/default); JAX-RS and reactive-routes absent-parameter behaviour; Javalin `Validator.get()` throwing; `getParameter`/`getHeader` returning null. *(amended 2026-09-20 during implementation: shared by three sections — row 1 is Javalin `ApiBuilder`'s thread-local guard, the measured fact behind `follow_calls: all` (§4a); rows 2–12 are §5b's binder rules; rows 13–17 are `AbstractNameValueExpression`'s grammar (§5c), Javalin's `Context` read/set overloads by arity and `Validator.get()` throwing, and the Servlet API's `getParameter`/`getHeader` null-on-absent on Tomcat 10.1.50 and 9.0.121 (§5d), M10; row 18, added at the whole-branch review, is Micronaut's unwritten-name fallback — `AbstractArgumentBinder.doResolve` retrying `NameUtils.hyphenate`, the header binder's `capitalize` — behind `fallback_spelling`, M16)* | §4a, §5b, §5c, §5d |
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
  (`tests/catalogs/kt-defaults.yml`), called with and without the argument. *(amended 2026-09-20 during implementation: as built, `KtorRoutes.kt` holds the blocks in `orders()`, `selectors()`, `reads()` and
  `defaults()`, plus `fun Route.mount(path, version = "v1", build)` — the defaulted DSL
  function — and `elsewhere()` for the wrong-receiver case; the test-only catalog naming
  `mount` is built inside `tests/application/test_ktor_defaults_fixture.py`, not committed
  under `tests/catalogs/`, M11.)*
- **`orders-ktor-classlambdas`**: the same sources compiled with `-Xlambdas=class`
  (CP-23's harness doubles as the fixture) — the e2e asserts **identical endpoint rows** to
  `orders-ktor`.
- **`orders-service`** Kotlin router: a `Route`-receiver helper in `KotlinOrderRoutes.kt`;
  Java `OrderRoutes.java` gains `queryParam("v", "2")`; Spring MVC controller gains
  `@RequestParam` required/optional/`Optional`/nullable-Kotlin variants and one
  `@RequestMapping(params = "v=1", headers = "!X-Legacy")`.
- **Javalin fixture:** a static helper called from `apiBuilder`; `ctx.queryParam("q")`,
  `ctx.queryParamAsClass("n", Integer.class).get()`, `ctx.header("X-Api")`.
- **Servlet, JAX-RS, Micronaut, Gateway fixtures:** one read/annotation of each kind. *(amended 2026-09-20 during implementation: the Servlet reads live in a NEW fixture, `fixtures/orders-servlet`
  (`@WebServlet("/sv/orders") OrderServlet.doGet`, the Servlet API taken from
  `tomcat-embed-core` as CP-9 does), so no pinned count on `orders-service` moves; the
  R1 case is `fixtures/orders-service/…/mvcroutes/KotlinParamController.kt`
  (`page: Int = 0`, `tag: String?`); the Spring MVC conditions are
  `MappingConditionsController.java`, M11.)*
- **Extractor (Gradle) tests:** `lambda_body` on a `Lambda` and a `SuspendLambda` class,
  absent on an ordinary class; `declares_default` on a defaulted parameter, absent
  otherwise.
- **Unit tests** on synthetic facts: §3a masks 0/1/mixed/two masks, static vs instance
  sibling, no `bridge_of` untouched, both candidates untouched, non-int mask untouched; §3b
  `lambda_body` join, `instance` without it untouched; §4a visited set, depth bound →
  `routing_depth` question and no row, `follow_calls: all` vs default; §4b getter tables,
  unknown getter, verb conflict → silence; §4c `all_methods` expansion; §5b binder predicate
  table-driven including `declares_default`; §5d `via`, `then`, `skip_path_variables`
  with `?`/`...`, NULL requirement on bare reads.
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
| `inbound-request-requirements` (new, REST in) | — → a "request requirements" line on every REST-inbound framework rollup: ✅ for the fourteen catalogs in §5, "not recorded" for the rest. *(amended 2026-09-20 during implementation: the generated rollup has one row per framework and no place for a capability line, so the line is a hand-written `Request requirements` ROW per framework line in §5.1's table — eighteen rows, nine ✅ shipped and nine **Not recorded**, which the rollup counts as shipped rows and as nothing respectively, M12)* |

Register: the five ids leave the REST in ```delivery``` block; `inbound-request-requirements`
is added and closed in the same PR; `ktor-route-with-verb` closes. `scripts/coverage_matrix.py`
`ITEM_FRAMEWORKS` drops the closed ids. Docs: D00 (`lambda_body` beside `bridge_of`; `declares_default` beside the
nullability projection), D01 (`requirement` and its NULL meaning, inbound `caller`), D02
(the new keys), M06 (§5e paragraph), COVERAGE §5.1 rows and rollups, `PROJECT.md`
component table if `effective_calls` earns a line, the `routing_depth` question kind.

---

## 11. Sizing and the plan's order

1. Extractor first: `lambda_body` and `declares_default` with their Gradle tests and D00
   (R1, R2), then the fixtures' facts regenerated. Then §3 as a rename (proof step 1) → §3a
   → §3b, each with unit tests; the Kotlin handler column changes here
   (`kotlin-null-handler`, `kotlin-class-lambdas`, `kotlin-default-bridge-calls` close).
2. §5a schema + writer (inert until a mechanism writes).
3. §4a helpers → §4b selectors + getter tables → §4c `handle` + `all_methods` → §4d, with
   `ktor-routing.yml` and `KtorRoutes.kt` growing per task (`ktor-route-extensions`,
   `ktor-selector-blocks`, `ktor-route-with-verb` close; Ktor requirements written).
4. §5b catalog by catalog (Spring, JAX-RS ×3, Micronaut, reactive routes) → §5c (Spring
   annotations, router Java, Gateway) → §5d (Ktor, Javalin, Servlet ×2).
5. Probes are written in the task that first needs each key (CP-23 with step 1, CP-24 with
   step 3, CP-25/26 with step 4); register, COVERAGE, D-docs, M06 last, in one docs task
   gated by the full check.

Roughly twice B+C: two small extractor units, two projection units, four combinator units,
one schema unit, three mechanism units over fourteen catalogs, four probes, two fixture
variants.
