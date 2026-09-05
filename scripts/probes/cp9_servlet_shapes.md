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

**Three questions were added by fix round 1**, each because a verdict below had
been decided on something other than a measurement. **Does `HttpServlet.service`
dispatch TRACE to `doTrace`** when the connector is not the thing refusing the
method — that is, is the 405 the first run recorded a fact about the servlet or
a fact about the deployment? **Does the `javax.servlet` spelling behave the
same**, on the container the legacy estate actually runs? And **does a
deployment descriptor declaring `metadata-complete="true"` really suppress
every annotated servlet**, which is the one shape in which this catalog
fabricates an entire module's surface?

**Version scope (§5.4).** Run against **Apache Tomcat 10.1.50 (Servlet 6.0),
11.0.24 (Servlet 6.1) and 9.0.121 (Servlet 4.0)** — three different majors and
therefore three independent `jakarta`/`javax` `HttpServlet` implementations,
which is where implicit verb dispatch lives. 9.0.121 is the `javax.servlet`
spelling and is the reason a second catalog ships rather than a stated
boundary. The verdict below is evidence about those three containers and no
other. Widening it means adding an entry to `VERSIONS` in
`scripts/probes/cp9_servlet/run.sh` and re-running, never assuming.

**No Spring anywhere, deliberately.** The catalogs this probe precedes are
`jakarta-servlet.yml` and `javax-servlet.yml`, and the rule they model belongs
to the Servlet specification and to `HttpServlet`'s own dispatch. The harness
therefore deploys a real webapp directory through `Tomcat.addWebapp`, so the
CONTAINER's own annotation deployment scan is what discovers each
`@WebServlet` — the spec's own mechanism. Spring Boot's `@ServletComponentScan`
is a second registration route; measuring through it would have confounded the
rule under test with Spring's re-implementation of it, and (as it happens) that
annotation moved package between Boot 3 and Boot 4, which is itself a reason
not to make a container-level verdict depend on it.

**How to run.** `bash scripts/probes/cp9_servlet/run.sh`. Per container version
it compiles the probe webapp (nine servlet classes, listed in the expectation
table below), lays them out under `WEB-INF/classes`, starts embedded Tomcat,
curls one request per live row, then runs the committed extractor over the very
same build's `target/classes` and prints — through
`scripts/probes/cp9_servlet/facts.py` — the literal fact values for each
fact-shape row. It ends by printing the observation table itself. Needs a JDK
21+, Maven, and network on the first run. Not a test: nothing in the suite runs
it, and NFR-1's no-network rule governs the suite, not evidence gathering.

Three details of the harness are themselves part of the evidence. The
`javax.servlet` column compiles the SAME committed sources under the other
package name — one `sed` in `run.sh`, into `target/generated-javax/java` —
because "identical modulo the spelling" is precisely the claim that column
measures, and a second hand-maintained copy could stop being identical without
anyone noticing. The probe opens a SECOND connector differing in exactly one
setting, `allowTrace="true"`, so a connector default can be told apart from the
specification's dispatch. And it deploys the same `WEB-INF/classes` a SECOND
time under `/metadata-complete`, beneath a descriptor declaring
`metadata-complete="true"`, so the only difference between the two webapps is
that descriptor — a descriptor that ALSO registers one servlet by hand, which
is row 34 and is a control rather than a measurement: `metadata-complete`
suppresses the annotation scan and never the descriptor's own `<servlet>`
declarations, so a 200 there is what tells row 33's 404 apart from a context
that failed to start.

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
| 30 | the running container's own servlet API package | which spelling that column measured | the one the build asked for, or the run is mislabelled |
| 31-32 | a connector with `allowTrace="true"` | TRACE `/explicit` (overridden) and `/getonly` (not) | **unknown — whether the 405 is the connector or the dispatch** |
| 33 | the same classes under `metadata-complete="true"` | GET `/metadata-complete/getonly` | **unknown — whether the annotation scan is suppressed wholesale** |
| 34 | the same class registered by that descriptor's own `<servlet>` | GET `/metadata-complete/descriptor-registered` | 200 — `metadata-complete` suppresses the ANNOTATION scan, not the descriptor; row 33's positive control |
| 35 | `service()` overridden AND `doGet`/`doPost` declared, the override DELEGATING through `super.service` | GET `/delegating` | 200 — added 2026-09-05 for `A-M2` |
| 36 | the same class | POST `/delegating` | 200 |
| 37 | the same class, a verb it declares no `doXxx` for | PUT `/delegating` | **405** — row 35's discriminator: a refusal is what says `HttpServlet`'s own dispatch still ran |
| 38 | the SECOND bypass signature: the public `service(ServletRequest, ServletResponse)` overridden and delegating, `doGet`/`doPost` declared | GET `/delegating-agnostic` | 200 |
| 39 | the same class | POST `/delegating-agnostic` | 200 |
| 40 | the same class, a verb it declares no `doXxx` for | PUT `/delegating-agnostic` | **405** — row 38's discriminator |

## Observations

Verbatim from `run.sh`'s generated table — every column header is the container
the process under test reported through its own `ServletContext.getServerInfo()`,
not the version the loop asked for, and the harness aborts rather than
mislabelling a column when the two disagree. It aborts on the same terms when
the servlet API package the process reported loading (row 30) is not the
spelling that column claims. The fact-shape rows are filed under the same
identity because `facts.py` reads them from the class files that build
produced.

| # | probe | 10.1.50 | 11.0.24 | 9.0.121 |
|---|---|---|---|---|
| 1 | `GET /multi-a` — `urlPatterns = {"/multi-a", "/multi-b"}` | 200 | 200 | 200 |
| 2 | `GET /multi-b` — the same class's second pattern | 200 | 200 | 200 |
| 3 | `GET /aliased` — `@WebServlet("/aliased")`, the `value` spelling | 200 | 200 | 200 |
| 4 | `GET /verbs` — `doGet` overridden | 200 | 200 | 200 |
| 5 | `POST /verbs` — `doPost` overridden | 200 | 200 | 200 |
| 6 | `PUT /verbs` — no `doPut` on the class | 405 | 405 | 405 |
| 7 | `HEAD /getonly` — `doGet` only — implicit | 200 | 200 | 200 |
| 8 | `OPTIONS /getonly` — `doGet` only — implicit | 200 | 200 | 200 |
| 9 | `Allow` header on `OPTIONS /getonly` — `doGet` only | `GET, HEAD, OPTIONS` | `GET, HEAD, OPTIONS` | `GET, HEAD, OPTIONS` |
| 10 | `TRACE /getonly` — `doGet` only — implicit | 405 | 405 | 405 |
| 11 | `HEAD /explicit` — `doHead` overridden | 200 | 200 | 200 |
| 12 | `OPTIONS /explicit` — `doOptions` overridden | 200 | 200 | 200 |
| 13 | `TRACE /explicit` — `doTrace` overridden | 405 | 405 | 405 |
| 14 | `GET /service-only` — `service()` overridden, no `doXxx` | 200 | 200 | 200 |
| 15 | `PUT /service-only` — `service()` overridden, no `doXxx` | 200 | 200 | 200 |
| 16 | `GET /generic` — `GenericServlet` subclass | 200 | 200 | 200 |
| 17 | `PUT /generic` — `GenericServlet` subclass | 200 | 200 | 200 |
| 18 | `GET /decoy` — only `doGet(String, HttpServletResponse)` | 405 | 405 | 405 |
| 19 | `GET /unannotated` — extends `HttpServlet`, no `@WebServlet` | 404 | 404 | 404 |
| 20 | `@WebServlet`'s own fact target | `TYPE` | `TYPE` | `TYPE` |
| 21 | `args` of `urlPatterns = {"/multi-a", "/multi-b"}` | `{"urlPatterns": ["/multi-a", "/multi-b"]}` | `{"urlPatterns": ["/multi-a", "/multi-b"]}` | `{"urlPatterns": ["/multi-a", "/multi-b"]}` |
| 22 | `args` of `@WebServlet("/aliased")` | `{"value": ["/aliased"]}` | `{"value": ["/aliased"]}` | `{"value": ["/aliased"]}` |
| 23 | `args` of `urlPatterns = "/verbs"` (one element) | `{"urlPatterns": ["/verbs"]}` | `{"urlPatterns": ["/verbs"]}` | `{"urlPatterns": ["/verbs"]}` |
| 24 | `GetOnlyServlet#doGet`'s recorded `visibility` | `other` | `other` | `other` |
| 25 | `GetOnlyServlet#doGet`'s signature parameter symbols | `jakarta/servlet/http/HttpServletRequest#, jakarta/servlet/http/HttpServletResponse#` | `jakarta/servlet/http/HttpServletRequest#, jakarta/servlet/http/HttpServletResponse#` | `javax/servlet/http/HttpServletRequest#, javax/servlet/http/HttpServletResponse#` |
| 26 | `DecoyOverloadServlet#doGet`'s signature parameter symbols | `java/lang/String#, jakarta/servlet/http/HttpServletResponse#` | `java/lang/String#, jakarta/servlet/http/HttpServletResponse#` | `java/lang/String#, javax/servlet/http/HttpServletResponse#` |
| 27 | `GetOnlyServlet`'s own `superclass` | `jakarta/servlet/http/HttpServlet#` | `jakarta/servlet/http/HttpServlet#` | `javax/servlet/http/HttpServlet#` |
| 28 | `GenericProbeServlet`'s own `superclass` | `jakarta/servlet/GenericServlet#` | `jakarta/servlet/GenericServlet#` | `javax/servlet/GenericServlet#` |
| 29 | `args` on `UnannotatedServlet` (no annotation written) | `ABSENT` | `ABSENT` | `ABSENT` |
| 30 | the servlet API package the running container reported loading | `jakarta.servlet` | `jakarta.servlet` | `javax.servlet` |
| 31 | `TRACE /explicit` on a connector with `allowTrace="true"` — `doTrace` overridden | 200 | 200 | 200 |
| 32 | `TRACE /getonly` on a connector with `allowTrace="true"` — no `doTrace` — `HttpServlet`'s own | 200 | 200 | 200 |
| 33 | `GET /metadata-complete/getonly` — the same classes under `metadata-complete="true"` | 404 | 404 | 404 |
| 34 | `GET /metadata-complete/descriptor-registered` — the same class registered by that descriptor's own `<servlet>` — row 33's positive control | 200 | 200 | 200 |
| 35 | `GET /delegating` — `service()` delegates to `super`, `doGet`/`doPost` declared | 200 | 200 | 200 |
| 36 | `POST /delegating` — `service()` delegates to `super`, `doGet`/`doPost` declared | 200 | 200 | 200 |
| 37 | `PUT /delegating` — `service()` delegates to `super`, no `doPut` — row 35's discriminator | 405 | 405 | 405 |
| 38 | `GET /delegating-agnostic` — the PUBLIC `service(ServletRequest, ServletResponse)` delegates to `super`, `doGet`/`doPost` declared | 200 | 200 | 200 |
| 39 | `POST /delegating-agnostic` — the PUBLIC `service` delegates to `super`, `doGet`/`doPost` declared | 200 | 200 | 200 |
| 40 | `PUT /delegating-agnostic` — the PUBLIC `service` delegates to `super`, no `doPut` — row 38's discriminator | 405 | 405 | 405 |

Every row identical on all three containers, and the `javax` column identical
to the other two modulo the package name (rows 25-28 and 30, which are the only
rows where a package name is part of the value). Six expectations were open
going in (rows 7-13, 24-26, 31-33) and all six are now answered; nothing was
falsified.

## Verdict

1. **Each `urlPattern` is its own address** (rows 1-2). One class, two served
   URLs — so one `@WebServlet` is N endpoints, never one.
2. **`value` and `urlPatterns` are the same address** (row 3), and they reach
   the facts as DIFFERENT argument keys (rows 21-22), both list-valued even
   when written as a single string (row 23). A reader must accept either key
   and must not require the array spelling. They are ALIASES, so a declaration
   writes exactly one: writing both is a deployment error the container
   refuses, at which point the module serves nothing and either value would be
   a fabricated address.
3. **The verb is the overridden `doXxx`, and nothing else** (rows 4-6). A verb
   the class does not override is a 405, which is `HttpServlet`'s own default
   `doPut` answering — the framework serves no verb it was given no override
   for.
4. **HEAD and OPTIONS ARE served implicitly from `doGet`** (rows 7-9): 200 on
   all three, with `Allow: GET, HEAD, OPTIONS` naming exactly the implicit set.
   This settles the design's open question **in the affirmative as a matter of
   FACT**, and the ruling about what to DERIVE from it is (5) below.
5. **RULING — this style derives one row per handler the MODULE DECLARES, so
   implicitly dispatched verbs derive nothing and are a stated boundary.**
   Two reasons, and the first is the one that decides it. **There is no
   handler to attribute.** The code serving HEAD on `/getonly` is
   `HttpServlet.doHead`, in a container jar this workspace never scanned; a row
   for it would carry either a NULL handler or `doGet`'s symbol, and the second
   is false — `doGet` is *called by* the HEAD path, it does not *serve* HEAD.
   OPTIONS is worse: it is served by every `HttpServlet` alive, so an OPTIONS
   row would be a per-class constant carrying no evidence about the class at
   all. Row 32 shows implicit TRACE falls in the same category. **And it is the
   ruling this phase already made once**, for the same verbs, on measured-live
   evidence: 2O Task 6 records Spring Data REST's own HEAD/OPTIONS as "observed
   live, deliberately not derived" (`docs/COVERAGE.md`). Two catalogs answering
   one question two ways would be the §6 blend. Under-reporting a STATED
   boundary is honest (§8.1 rule 3); the boundary is stated in
   `docs/COVERAGE.md`, and it is falsified the day an endpoint row can name a
   handler that lives outside the module.
6. **An EXPLICIT `doHead`, `doOptions` or `doTrace` override IS served and IS
   derived** (rows 11-12 and 31). That is not a special case of (5) but its
   complement: the module declared the handler, so there is a symbol to
   attribute and a declaration to report.
7. **`doTrace` IS in the verb map, with the connector recorded as a stated
   dependency** (rows 13, 31, 32 — and this verdict is the one fix round 1
   reversed). The first run measured only row 13 — TRACE a 405 on the default
   connector even with `doTrace` overridden — and concluded that deriving a
   TRACE row would publish an address the deployment does not serve. That
   conclusion took a **deployment** fact for a **code** fact. Tomcat's
   `allowTrace` is connector configuration: any deployment can set it, it lives
   outside the module, and nothing in a repository can see it, so its default
   is not proof that the address is unserved — the same argument this phase
   settled for Actuator's `exposure.include` (`docs/COVERAGE.md`, and §8's
   "exclude only on proof, never on inference"). Row 31 measures what the
   specification actually does once the connector is out of the way:
   `service()` dispatches TRACE to `doTrace`, 200, on all three containers. A
   class overriding `doTrace` has declared a handler; we derive it and state
   the dependency. Row 32 keeps the complement honest — implicit TRACE, off
   `HttpServlet`'s own `doTrace`, is also 200 and is NOT derived, by (5).
8. **A class overriding `service()` AND DECLARING NO `doXxx` derives NOTHING**
   (rows 14-15). It serves GET and PUT alike, because `HttpServlet.service` —
   the very method that reads `getMethod()` and dispatches to `doXxx` — is what
   the class replaced. The verb map does not describe this class, and applying
   it anyway would publish `GET` while withholding `PUT`: a wrong answer, not a
   partial one.

   **Amended 2026-09-05 (`A-M2`), and the amendment is the CONFIGURATION rather
   than the finding.** The verdict above was originally written without the
   qualifier and applied to every `service()` override. Rows 35-37 measure the
   commonest real form — a cross-cutting wrapper that overrides `service()`,
   calls `super.service(req, resp)`, and declares `doGet`/`doPost`. It serves
   GET (200) and POST (200) and **REFUSES PUT (405)**, identically on all three
   containers: `HttpServlet`'s dispatch still runs and the verb table describes
   that class exactly. Deriving nothing for it lost its WHOLE surface — address,
   verbs and handlers — where the table was right. §5.4 in one line: a verdict
   is bounded by the configuration it measured, and this one was applied past it
   for a phase.

   **Both bypass signatures behave identically** (rows 38-40). `HttpServlet` has
   two `service` methods — the protected verb-dispatching one and the public
   `service(ServletRequest, ServletResponse)` it implements by casting and
   calling the first — and a verdict read against one must not be applied to
   the other, which is the mistake this whole amendment is about. Measured
   rather than reasoned: the public overload delegating through `super` serves
   GET and POST and refuses PUT, the same three answers on the same three
   containers.

   **What is still not measured** is the third configuration: a `service()`
   override that does NOT delegate and declares `doXxx` anyway. Nothing in the
   fact stream separates it from rows 35-37 — the distinguishing fact is a
   `super.service(...)` call, `invoke_kind: special` on an `HttpServlet#service`
   target, and the catalog would need `call_site` in `requires` to see it.
   Stated in `docs/COVERAGE.md` as the residual the narrowed rule accepts.
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
15. **The `javax.servlet` spelling behaves identically, and ships as its own
    catalog** (row 30, and every row above measured a third time on 9.0.121).
    Rows 1-29 and 31-33 are the same answers; rows 25-28 are the same shapes
    with `javax/servlet/...` where the others read `jakarta/servlet/...`. So
    `javax-servlet.yml` is the same document under a package rename — measured,
    not assumed, which is what §5.4 required before it could ship. Legacy
    servlets are the population that uses this spelling, so a jakarta-only
    catalog would have under-served the estate the style exists for.
16. **A `metadata-complete="true"` descriptor suppresses every annotated
    servlet, and NOTHING IN THE FACTS CAN SEE IT** (rows 33-34). The same
    classes, the same container, one deployment descriptor: 404 on all three.
    **Row 34 is what makes that 404 mean the annotation was ignored.** Tomcat
    answers 404 for a context that is mapped and failed to start too, and
    nothing else here asserts the second context came up — `identify` speaks
    for the first webapp only. So the same descriptor registers
    `probe.GetOnlyServlet` by hand at `/descriptor-registered`, which
    `metadata-complete` does not suppress, and it answers **200 on all three**
    in the same run. 200 beside 404, one webapp, one descriptor: the scan was
    suppressed and the context was serving. This is
    the one shape in which these catalogs fabricate a whole module's surface
    rather than under-reporting it — nothing in the pipeline reads
    `WEB-INF/web.xml`, so every rule applies unconditionally. Stated as a
    boundary in `docs/COVERAGE.md` and in both catalog files, in the
    over-report direction; closed by a deployment-descriptor reader, which
    would also close the `web.xml` registration route we under-report.

## What this probe deliberately did not measure

- **`web.xml` `<servlet-mapping>` and `ServletContext.addServlet`.** The other
  two registration routes the Servlet specification defines. Neither probed and
  neither catalogued; stated boundaries in `docs/COVERAGE.md`, with the
  annotation named as one of three (§8.1 rule 3). Rows 33-34 measured a
  descriptor for what it SUPPRESSES; row 34 registers one servlet through it
  solely as row 33's positive control, and no `<servlet-mapping>` it declares
  is read by anything in the pipeline.
- **A `web-app` version below 3.0.** The specification's second route to the
  same suppression row 33 measured, and it is not separately probed: row 33's
  descriptor names its own build's current version and switches the scan off
  through `metadata-complete`. The COVERAGE row states both routes and is
  measured for one.
- **Transitive supertypes.** `class Foo extends AbstractBaseServlet extends
  HttpServlet` was not probed and is not derived: `superclasses` carries the
  DIRECT edge only. Stated boundary.
- **An abstract `@WebServlet` class.** Not probed and not derivable-against:
  `ACC_ABSTRACT` is not among the modifiers the extractor records, so the
  facts cannot tell one from a concrete class. Stated boundary in
  `docs/COVERAGE.md`, in the over-report direction.
- **Pattern semantics.** `/legacy/*`, `*.do` and `/` are servlet pattern
  grammars with precedence rules; the probe measured only that a declared
  pattern is served at its own literal spelling, and the style publishes the
  pattern verbatim rather than interpreting it.
- **`@WebFilter`, `@WebListener`, `FilterRegistrationBean`,
  `ServletRegistrationBean`, `loadOnStartup`, `asyncSupported`, `initParams`.**
  Stated boundaries; `@WebFilter` already has a pinned no-derivation test
  against every shipped catalog.
- **Other containers.** Jetty, Undertow and a standalone (non-embedded) Tomcat
  were not run. Rows 10 and 13 — a connector's `allowTrace` default — are the
  answers most likely to differ, which is exactly why the TRACE verdict is now
  written against rows 31-32 rather than against a default.

## How the verdict is consumed

`src/sextant/catalogs/jakarta-servlet.yml` and
`src/sextant/catalogs/javax-servlet.yml` declare the supertype
(`HttpServlet` under each spelling), the address annotation and its two
argument spellings, the seven-entry verb map, and the two `service` signatures
that bypass dispatch. `src/sextant/application/resolve/engines/supertype_dispatch.py`
is the engine; verdicts 1-3 and 6-15 are each pinned by a test in
`tests/application/test_supertype_dispatch.py`, and verdicts 5 and 16 are the
two boundaries recorded in `docs/COVERAGE.md`.
