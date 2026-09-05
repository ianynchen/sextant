# CP-9 — `@WebServlet` shapes, `HttpServlet` dispatch, and what reaches the facts (2O Task 7b, Step 0)

**Question.** Two halves, because the style this checkpoint precedes reads
both. **The container's rule:** does `@WebServlet` register every one of an
array-valued `urlPatterns`? Is `value` the same address as `urlPatterns`? Does
an overridden `doXxx` serve exactly its own verb and nothing else? Does
`HttpServlet` serve **HEAD and OPTIONS implicitly from `doGet`** — the question
the design left open and forbade assuming either way? What does a class
overriding `service()`, or extending `GenericServlet`, serve instead?
**The fact stream's shape:** does `@WebServlet` reach us as a TYPE-level
annotation carrying its arguments? Are array-valued patterns readable? Is
`value` distinguishable from `urlPatterns`? Is a `protected` handler's
visibility recorded, and as what?

**Version scope (§5.4).** Run against **Apache Tomcat 10.1.50 (Servlet 6.0) and
11.0.24 (Servlet 6.1)**, two different majors and therefore two independent
`jakarta.servlet.http.HttpServlet` implementations — which is where implicit
verb dispatch lives. The verdict below is evidence about those two containers
and no other: implicit dispatch is implemented by the container's own servlet
API jar, and the TRACE row in particular is a **connector** default that
another container may set the other way. Widening the verdict means adding a
version to `VERSIONS` in `scripts/probes/cp9_servlet/run.sh` and re-running,
never assuming.

**No Spring anywhere, deliberately.** The catalog this probe precedes is
`jakarta-servlet.yml`, and the rule it models belongs to the Servlet
specification and to `HttpServlet`'s own dispatch. The harness therefore
deploys a real webapp directory through `Tomcat.addWebapp`, so the CONTAINER's
own annotation deployment scan is what discovers each `@WebServlet` — the
spec's own mechanism. Spring Boot's `@ServletComponentScan` is a second
registration route; measuring through it would have confounded the rule under
test with Spring's re-implementation of it, and (as it happens) that annotation
moved package between Boot 3 and Boot 4, which is itself a reason not to make a
container-level verdict depend on it.

**How to run.** `bash scripts/probes/cp9_servlet/run.sh`. Per container version
it compiles the probe webapp (nine servlet classes, listed in the expectation
table below), lays them out under `WEB-INF/classes`, starts embedded Tomcat,
curls one request per live row, then runs the committed extractor over the very
same build's `target/classes` and prints — through
`scripts/probes/cp9_servlet/facts.py` — the literal fact values for each
fact-shape row. It ends by printing the observation table itself. Needs a JDK
21+, Maven, and network on the first run. Not a test: nothing in the suite runs
it, and NFR-1's no-network rule governs the suite, not evidence gathering.

## Expectation table

| # | Declaration | Under test | Expected |
|---|---|---|---|
| 1-2 | `@WebServlet(urlPatterns = {"/multi-a", "/multi-b"})` + `doGet` | GET on each pattern | 200, 200 — each pattern is its own address |
| 3 | `@WebServlet("/aliased")` + `doGet` | GET `/aliased` | 200 — `value` is `urlPatterns` |
| 4-6 | `doGet` and `doPost`, no `doPut` | GET, POST, PUT `/verbs` | 200, 200, 405 |
| 7-10 | `doGet` ONLY | HEAD, OPTIONS, `Allow`, TRACE on `/getonly` | **unknown — the ruling** |
| 11-13 | `doHead`, `doOptions`, `doTrace` all overridden | HEAD, OPTIONS, TRACE `/explicit` | **unknown — the ruling** |
| 14-15 | `service(HttpServletRequest, HttpServletResponse)` overridden, no `doXxx` | GET, PUT `/service-only` | 200, 200 — the verb map cannot describe this |
| 16-17 | `GenericServlet` subclass, `@WebServlet` alike | GET, PUT `/generic` | 200, 200 — no HTTP verb semantics at all |
| 18 | ONLY `doGet(String, HttpServletResponse)` | GET `/decoy` | 405 — Java identifies a method by name AND parameter types (§8.1) |
| 19 | extends `HttpServlet`, no `@WebServlet` | GET `/unannotated` | 404 — the annotation is the registration |
| 20-23 | the annotation as it reaches the fact stream | target level, `args` of each spelling | type-level, arguments readable |
| 24-26 | the handler as it reaches the fact stream | `visibility`, signature parameter symbols | **unknown — `protected` may not survive as such** |
| 27-28 | the `extends` edge | `superclass` on each probe class | present, though the target is in a container jar |
| 29 | a class carrying no `@WebServlet` | its `args` | absent, not empty |

## Observations

Verbatim from `run.sh`'s generated table — every column header is the container
the process under test reported through its own `ServletContext.getServerInfo()`,
not the version the loop asked for, and the harness aborts rather than
mislabelling a column when the two disagree. The fact-shape rows are filed
under the same identity because `facts.py` reads them from the class files that
build produced.

| # | probe | 10.1.50 | 11.0.24 |
|---|---|---|---|
| 1 | `GET /multi-a` — `urlPatterns = {"/multi-a", "/multi-b"}` | 200 | 200 |
| 2 | `GET /multi-b` — the same class's second pattern | 200 | 200 |
| 3 | `GET /aliased` — `@WebServlet("/aliased")`, the `value` spelling | 200 | 200 |
| 4 | `GET /verbs` — `doGet` overridden | 200 | 200 |
| 5 | `POST /verbs` — `doPost` overridden | 200 | 200 |
| 6 | `PUT /verbs` — no `doPut` on the class | 405 | 405 |
| 7 | `HEAD /getonly` — `doGet` only — implicit | 200 | 200 |
| 8 | `OPTIONS /getonly` — `doGet` only — implicit | 200 | 200 |
| 9 | `Allow` header on `OPTIONS /getonly` — `doGet` only | `GET, HEAD, OPTIONS` | `GET, HEAD, OPTIONS` |
| 10 | `TRACE /getonly` — `doGet` only — implicit | 405 | 405 |
| 11 | `HEAD /explicit` — `doHead` overridden | 200 | 200 |
| 12 | `OPTIONS /explicit` — `doOptions` overridden | 200 | 200 |
| 13 | `TRACE /explicit` — `doTrace` overridden | 405 | 405 |
| 14 | `GET /service-only` — `service()` overridden, no `doXxx` | 200 | 200 |
| 15 | `PUT /service-only` — `service()` overridden, no `doXxx` | 200 | 200 |
| 16 | `GET /generic` — `GenericServlet` subclass | 200 | 200 |
| 17 | `PUT /generic` — `GenericServlet` subclass | 200 | 200 |
| 18 | `GET /decoy` — only `doGet(String, HttpServletResponse)` | 405 | 405 |
| 19 | `GET /unannotated` — extends `HttpServlet`, no `@WebServlet` | 404 | 404 |
| 20 | `@WebServlet`'s own fact target | `TYPE` | `TYPE` |
| 21 | `args` of `urlPatterns = {"/multi-a", "/multi-b"}` | `{"urlPatterns": ["/multi-a", "/multi-b"]}` | `{"urlPatterns": ["/multi-a", "/multi-b"]}` |
| 22 | `args` of `@WebServlet("/aliased")` | `{"value": ["/aliased"]}` | `{"value": ["/aliased"]}` |
| 23 | `args` of `urlPatterns = "/verbs"` (one element) | `{"urlPatterns": ["/verbs"]}` | `{"urlPatterns": ["/verbs"]}` |
| 24 | `GetOnlyServlet#doGet`'s recorded `visibility` | `other` | `other` |
| 25 | `GetOnlyServlet#doGet`'s signature parameter symbols | `jakarta/servlet/http/HttpServletRequest#, jakarta/servlet/http/HttpServletResponse#` | `jakarta/servlet/http/HttpServletRequest#, jakarta/servlet/http/HttpServletResponse#` |
| 26 | `DecoyOverloadServlet#doGet`'s signature parameter symbols | `java/lang/String#, jakarta/servlet/http/HttpServletResponse#` | `java/lang/String#, jakarta/servlet/http/HttpServletResponse#` |
| 27 | `GetOnlyServlet`'s own `superclass` | `jakarta/servlet/http/HttpServlet#` | `jakarta/servlet/http/HttpServlet#` |
| 28 | `GenericProbeServlet`'s own `superclass` | `jakarta/servlet/GenericServlet#` | `jakarta/servlet/GenericServlet#` |
| 29 | `args` on `UnannotatedServlet` (no annotation written) | `ABSENT` | `ABSENT` |

Every row identical on both containers. Three expectations were open going in
(rows 7-13 and 24-26) and all three are now answered; nothing was falsified.

## Verdict

1. **Each `urlPattern` is its own address** (rows 1-2). One class, two served
   URLs — so one `@WebServlet` is N endpoints, never one.
2. **`value` and `urlPatterns` are the same address** (row 3), and they reach
   the facts as DIFFERENT argument keys (rows 21-22), both list-valued even
   when written as a single string (row 23). A reader must accept either key
   and must not require the array spelling.
3. **The verb is the overridden `doXxx`, and nothing else** (rows 4-6). A verb
   the class does not override is a 405, which is `HttpServlet`'s own default
   `doPut` answering — the framework serves no verb it was given no override
   for.
4. **HEAD and OPTIONS ARE served implicitly from `doGet`** (rows 7-9): 200 on
   both, with `Allow: GET, HEAD, OPTIONS` naming exactly the implicit set.
   This settles the design's open question **in the affirmative as a matter of
   FACT**, and the ruling about what to DERIVE from it is (5) below.
5. **RULING — this style derives one row per handler the MODULE DECLARES, so
   implicit HEAD and OPTIONS derive nothing and are a stated boundary.**
   Two reasons, and the first is the one that decides it. **There is no
   handler to attribute.** The code serving HEAD on `/getonly` is
   `HttpServlet.doHead`, in a container jar this workspace never scanned; a row
   for it would carry either a NULL handler or `doGet`'s symbol, and the second
   is false — `doGet` is *called by* the HEAD path, it does not *serve* HEAD.
   OPTIONS is worse: it is served by every `HttpServlet` alive, so an OPTIONS
   row would be a per-class constant carrying no evidence about the class at
   all. **And it is the ruling this phase already made once**, for the same
   verbs, on measured-live evidence: 2O Task 6 records Spring Data REST's own
   HEAD/OPTIONS as "observed live, deliberately not derived"
   (`docs/COVERAGE.md`). Two catalogs answering one question two ways would be
   the §6 blend. Under-reporting a STATED boundary is honest (§8.1 rule 3);
   the boundary is stated in `docs/COVERAGE.md`, and it is falsified the day an
   endpoint row can name a handler that lives outside the module.
6. **An EXPLICIT `doHead` or `doOptions` override IS served and IS derived**
   (rows 11-12). That is not a special case of (5) but its complement: the
   module declared the handler, so there is a symbol to attribute and a
   declaration to report.
7. **`doTrace` is NOT in the verb map** (rows 10 and 13). TRACE is a 405 on
   both containers *even with `doTrace` explicitly overridden*, because Tomcat's
   connector refuses the method before dispatch (`allowTrace`, default false).
   Deriving a TRACE row would publish an address the deployed container does
   not serve. Bounded by §5.4 to the two containers measured — another
   container, or a Tomcat with `allowTrace=true`, serves it and we would then
   under-report, which is the honest direction of the two.
8. **A class overriding `service()` derives NOTHING** (rows 14-15). It serves
   GET and PUT alike, because `HttpServlet.service` — the very method that
   reads `getMethod()` and dispatches to `doXxx` — is what the class replaced.
   The verb map does not describe this class, and applying it anyway would
   publish `GET` while withholding `PUT`: a wrong answer, not a partial one.
9. **A `GenericServlet` subclass derives NOTHING** (rows 16-17). It serves
   every verb through one protocol-agnostic `service(ServletRequest,
   ServletResponse)`; `GenericServlet` declares no `doXxx` at all, so there is
   no verb evidence to read. It is excluded structurally rather than by a
   special case: its own `superclass` is `jakarta/servlet/GenericServlet#`
   (row 28), which is not the supertype the catalog names.
10. **The member selector must match parameter types, not just the name**
    (rows 18 and 26). `doGet(String, HttpServletResponse)` is not an override
    of anything — Java identifies a method by name and parameter types in
    order (GUIDELINES §8.1's language rule) — and the container answers 405.
    A selector keyed on the name alone would publish `GET /decoy`, an address
    nothing serves. The parameter symbols are readable off the signature
    (row 25), so the correct rule is also the implementable one.
11. **The annotation is the registration** (row 19). A class extending
    `HttpServlet` and overriding `doGet` with no `@WebServlet` is a 404 — and
    carries no annotation fact at all (row 29), so the absence is visible
    rather than inferred.
12. **`@WebServlet` reaches the facts as a TYPE-level annotation with its
    arguments** (row 20), which is exactly why `annotation_driven` cannot
    derive it: that engine's derivation joins method symbols and states so
    itself (`derive_endpoints.sql:398-400`).
13. **`protected` is NOT recorded as `protected`** (row 24). The extractor
    projects D00 §5a's two-valued `visibility`, and a `protected` handler is
    recorded as `other`. The design's expectation — "visibility IS in the fact
    stream, so the selector widens" — is therefore only half right: the column
    exists, but it cannot say "protected", so a selector cannot ask for it.
    It need not: a `doGet(HttpServletRequest, HttpServletResponse)` declared on
    a class extending `HttpServlet` IS the override at any visibility Java
    permits, because Java forbids narrowing one (JLS 8.4.8.3) — `private` and
    package-private do not compile, and `static` cannot hide an instance
    method. So the style reads no visibility at all, and that is mirroring
    rather than relaxing.
14. **The `extends` edge is present even though its target is in a container
    jar** (rows 27-28), carried module-prefixed like every `superclass`
    (capability 9.13). The match is therefore on the BARE descriptor, and the
    `supertype_derived` precondition that the supertype be a module-local
    symbol cannot apply here.

## What this probe deliberately did not measure

- **`web.xml` and `ServletContext.addServlet`.** The other two registration
  routes the Servlet specification defines. Neither probed and neither
  catalogued; stated boundaries in `docs/COVERAGE.md`, with the annotation
  named as one of three (§8.1 rule 3).
- **Transitive supertypes.** `class Foo extends AbstractBaseServlet extends
  HttpServlet` was not probed and is not derived: `superclasses` carries the
  DIRECT edge only. Stated boundary.
- **Pattern semantics.** `/legacy/*`, `*.do` and `/` are servlet pattern
  grammars with precedence rules; the probe measured only that a declared
  pattern is served at its own literal spelling, and the style publishes the
  pattern verbatim rather than interpreting it.
- **`@WebFilter`, `@WebListener`, `FilterRegistrationBean`,
  `ServletRegistrationBean`, `loadOnStartup`, `asyncSupported`, `initParams`.**
  Stated boundaries; `@WebFilter` already has a pinned no-derivation test
  against every shipped catalog.
- **Other containers.** Jetty, Undertow and a standalone (non-embedded) Tomcat
  were not run. Row 10/13's TRACE answer is the one most likely to differ.

## How the verdict is consumed

`src/sextant/catalogs/jakarta-servlet.yml` declares the supertype
(`jakarta.servlet.http.HttpServlet`), the address annotation and its two
argument spellings, the six-entry verb map, and the two `service` signatures
that bypass dispatch. `src/sextant/application/resolve/engines/supertype_dispatch.py`
is the engine; verdicts 1-3, 6 and 8-14 are each pinned by a test in
`tests/application/test_supertype_dispatch.py`, and verdicts 5 and 7 are the
two under-reports recorded in `docs/COVERAGE.md`.
