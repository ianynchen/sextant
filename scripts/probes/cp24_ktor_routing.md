# CP-24 — the Ktor 3.0.3 routing surface: selectors, `handle`, the getters, `getOrFail`, and what a method mismatch evaluates to

**Question.** Spec 2026-09-19 §4b reads Ktor's selector blocks (`method`, `param`,
`optionalParam`, `header`, `accept`, `contentType`, and the four-argument `route`) as
prefixes carrying a verb, a media constraint or a request requirement; §4c reads
`Route.handle` as a verb-less terminal and expands it over `all_methods`; §5d reads a
handler's `call.request.headers[…]`, `call.request.queryParameters[…]`,
`call.parameters[…]` and `call.parameters.getOrFail(…)` as request reads, `required` only
for the throwing form. Each rests on a shape of the 3.0.3 jars no probe had recorded:
Q1 the exact selector and terminal descriptors (F4 — `handle` is a MEMBER of the `Route`
interface, `accept` takes a vararg); Q2 what `HttpMethod.DefaultMethods` holds, and in
what order; Q3/Q4 that `HttpMethod.Get` and `ContentType.Application.Json` reach a call
site as GETTER calls on a companion/nested object (F5), and what string each field was
built from; Q5 `getOrFail`'s two overloads and the exception type each throws; Q6 that
the three containers a handler reads are `Headers`/`Parameters`, both `StringValues`, so
one `get(String)` owner covers all three reads; Q7 `HttpMethodRouteSelector.evaluate`'s
bytecode — the A11 question ("does `method(Post) { get { } }` ever dispatch?") answered
from the class file instead of an embedded server run.

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file in one of three jars. It measures Ktor's compiled 3.0.3 surface, not the
Kotlin source or Ktor's documentation. Q7 shows that the selector returns the failure
constant when the request's method differs from the selector's; that a routing node's
selectors are evaluated conjunctively is Ktor's routing-resolve contract, which this
probe reads off ONE selector and does not re-derive from `RoutingResolveContext`. Q4
reads `ContentType$Application` alone — `Text`, `Image`, `Audio`, `Video`, `MultiPart`,
`Message` and `Font` have the same getter shape by name and are not read here. Q5 reads
the `Parameters` extension; `Headers` has no `getOrFail`. Nothing here measures the
resolve-layer rules the spec specifies, which did not yet exist when this was recorded.

**Version scope (§5.4).** `io.ktor:ktor-server-core-jvm`, `io.ktor:ktor-http-jvm` and
`io.ktor:ktor-utils-jvm` at Maven coordinate `3.0.3` — and, as the identity the harness
files every cell under, the `Implementation-Version` each jar's own `META-INF/MANIFEST.MF`
reports, read as **3.0.3** for all three. The harness aborts when an archive reports a
version other than the one the run expected. Every verdict below is bounded by those
three archives; `ktor-server-core-jvm` alone is what `ktor-routing.yml` is measured
against, and the `http`/`utils` jars are its own compile-scope dependencies at 3.0.3.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp24_ktor_routing/run.sh`. It resolves the three jars into `~/.m2` (Maven
and network on the first run only), then runs `probe.py`, which reads each jar's
`Implementation-Version` off its manifest before it measures anything and prints the
table below. Needs a JDK for `javap`. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version each jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's `VERSION` parameter asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column. Every cell is a `javap -p -s`/`-c` read of the named class in the
named artifact.

```
| what the run read | 3.0.3 |
|---|---|
| artifacts reporting this version | io.ktor:ktor-http-jvm, io.ktor:ktor-server-core-jvm, io.ktor:ktor-utils-jvm |
| identity read from the archive itself (`Implementation-Version`) | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1a | RoutingBuilderKt selector signatures: route ×2, method, param ×2, optionalParam, header, accept, contentType | `io.ktor:ktor-server-core-jvm` | 3.0.3 | `route(Lio/ktor/server/routing/Route;Ljava/lang/String;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; route(Lio/ktor/server/routing/Route;Ljava/lang/String;Lio/ktor/http/HttpMethod;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; method(Lio/ktor/server/routing/Route;Lio/ktor/http/HttpMethod;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; param(Lio/ktor/server/routing/Route;Ljava/lang/String;Ljava/lang/String;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; param(Lio/ktor/server/routing/Route;Ljava/lang/String;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; optionalParam(Lio/ktor/server/routing/Route;Ljava/lang/String;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; header(Lio/ktor/server/routing/Route;Ljava/lang/String;Ljava/lang/String;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; accept(Lio/ktor/server/routing/Route;[Lio/ktor/http/ContentType;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route; ; contentType(Lio/ktor/server/routing/Route;Lio/ktor/http/ContentType;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/Route;` |
| 1b | Route.handle: a member of the Route interface, its descriptor | `io.ktor:ktor-server-core-jvm` | 3.0.3 | `Route is an interface ; public abstract void handle(kotlin.jvm.functions.Function2<? super io.ktor.server.routing.RoutingContext, ? super kotlin.coroutines.Continuation<? super kotlin.Unit>, ? extends java.lang.Object>); ; (Lkotlin/jvm/functions/Function2;)V` |
| 2 | HttpMethod.DefaultMethods: members and values, from the static initialiser | `io.ktor:ktor-http-jvm` | 3.0.3 | `members in order: Get, Post, Put, Patch, Delete, Head, Options ; values: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS ; built by invokestatic Method kotlin/collections/CollectionsKt.listOf:([Ljava/lang/Object;)Ljava/util/List; ; putstatic Field DefaultMethods:Ljava/util/List;` |
| 3 | HttpMethod$Companion.get* getters and the literal each field was built from | `io.ktor:ktor-http-jvm` | 3.0.3 | `getGet() -> Get = "GET" ; getPost() -> Post = "POST" ; getPut() -> Put = "PUT" ; getPatch() -> Patch = "PATCH" ; getDelete() -> Delete = "DELETE" ; getHead() -> Head = "HEAD" ; getOptions() -> Options = "OPTIONS"` |
| 4 | ContentType$Application.get* getters and the type/subtype literals each field was built from | `io.ktor:ktor-http-jvm` | 3.0.3 | `getAny() -> Any = "application/*" ; getAtom() -> Atom = "application/atom+xml" ; getCbor() -> Cbor = "application/cbor" ; getJson() -> Json = "application/json" ; getHalJson() -> HalJson = "application/hal+json" ; getJavaScript() -> JavaScript = "application/javascript" ; getOctetStream() -> OctetStream = "application/octet-stream" ; getRss() -> Rss = "application/rss+xml" ; getSoap() -> Soap = "application/soap+xml" ; getXml() -> Xml = "application/xml" ; getXml_Dtd() -> Xml_Dtd = "application/xml-dtd" ; getZip() -> Zip = "application/zip" ; getGZip() -> GZip = "application/gzip" ; getFormUrlEncoded() -> FormUrlEncoded = "application/x-www-form-urlencoded" ; getPdf() -> Pdf = "application/pdf" ; getXlsx() -> Xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ; getDocx() -> Docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ; getPptx() -> Pptx = "application/vnd.openxmlformats-officedocument.presentationml.presentation" ; getProtoBuf() -> ProtoBuf = "application/protobuf" ; getWasm() -> Wasm = "application/wasm" ; getProblemJson() -> ProblemJson = "application/problem+json" ; getProblemXml() -> ProblemXml = "application/problem+xml"` |
| 5 | ParametersKt.getOrFail overloads and what their bodies throw on a missing name | `io.ktor:ktor-server-core-jvm` | 3.0.3 | `overloads: (Lio/ktor/http/Parameters;Ljava/lang/String;)Ljava/lang/String;, (Lio/ktor/http/Parameters;Ljava/lang/String;)Ljava/lang/Object; ; getOrFail: invokeinterface InterfaceMethod io/ktor/http/Parameters.get:(Ljava/lang/String;)Ljava/lang/String; ; ifnonnull ; new class io/ktor/server/plugins/MissingRequestParameterException ; athrow ; getOrFailImpl: invokeinterface InterfaceMethod io/ktor/http/Parameters.getAll:(Ljava/lang/String;)Ljava/util/List; ; ifnonnull ; new class io/ktor/server/plugins/MissingRequestParameterException ; athrow ; invokevirtual Method io/ktor/util/converters/DefaultConversionService.fromValues:(Ljava/util/List;Lio/ktor/util/reflect/TypeInfo;)Ljava/lang/Object; ; new class io/ktor/server/plugins/ParameterConversionException ; ifnonnull ; athrow` |
| 6 | StringValues.get owners: ApplicationRequest.getHeaders/getQueryParameters, ApplicationCall.getParameters | `io.ktor:ktor-server-core-jvm` | 3.0.3 | `ApplicationRequest.getHeaders()Lio/ktor/http/Headers; ; ApplicationRequest.getQueryParameters()Lio/ktor/http/Parameters; ; ApplicationCall.getParameters()Lio/ktor/http/Parameters; ; public interface io.ktor.http.Headers extends io.ktor.util.StringValues ; public interface io.ktor.http.Parameters extends io.ktor.util.StringValues ; StringValues.get(Ljava/lang/String;)Ljava/lang/String; ; StringValues.getAll(Ljava/lang/String;)Ljava/util/List;` |
| 7 | HttpMethodRouteSelector.evaluate bytecode: the failure constant on a method mismatch | `io.ktor:ktor-server-core-jvm` | 3.0.3 | `aload_1 ; invokevirtual Method io/ktor/server/routing/RoutingResolveContext.getCall:()Lio/ktor/server/application/PipelineCall; ; invokeinterface InterfaceMethod io/ktor/server/application/PipelineCall.getRequest:()Lio/ktor/server/request/PipelineRequest; ; checkcast class io/ktor/server/request/ApplicationRequest ; invokestatic Method io/ktor/server/request/ApplicationRequestPropertiesKt.getHttpMethod:(Lio/ktor/server/request/ApplicationRequest;)Lio/ktor/http/HttpMethod; ; aload_0 ; getfield Field method:Lio/ktor/http/HttpMethod; ; invokestatic Method kotlin/jvm/internal/Intrinsics.areEqual:(Ljava/lang/Object;Ljava/lang/Object;)Z ; ifeq ; getstatic Field io/ktor/server/routing/RouteSelectorEvaluation.Companion:Lio/ktor/server/routing/RouteSelectorEvaluation$Companion; ; invokevirtual Method io/ktor/server/routing/RouteSelectorEvaluation$Companion.getConstant:()Lio/ktor/server/routing/RouteSelectorEvaluation; ; areturn ; getstatic Field io/ktor/server/routing/RouteSelectorEvaluation.Companion:Lio/ktor/server/routing/RouteSelectorEvaluation$Companion; ; invokevirtual Method io/ktor/server/routing/RouteSelectorEvaluation$Companion.getFailedMethod:()Lio/ktor/server/routing/RouteSelectorEvaluation$Failure; ; areturn` |
```

## Verdicts

**Q1a — the selector signatures (§4b).** `RoutingBuilderKt` declares exactly the shapes
the spec's prefix rules read: `route(Route, String, Function1)` (the nesting primitive
already in `ktor-routing.yml`) and `route(Route, String, HttpMethod, Function1)` (a prefix
that ALSO sets the verb — `verb_arg: 2`); `method(Route, HttpMethod, Function1)` (a verb
with no path — `verb_arg: 1`, `path: ""`); `param(Route, String, Function1)` and
`param(Route, String, String, Function1)` (a query parameter present / equal to a
value); `optionalParam(Route, String, Function1)`; `header(Route, String, String,
Function1)`; `accept(Route, ContentType[], Function1)` — a VARARG, so `media_arg: 1` is an
array slot whose `elements` the existing vararg reader already walks (F4); and
`contentType(Route, ContentType, Function1)` — a single value. Every one takes the
receiver `Route` at argument 0 and the block at the last position, so `receiver_arg: 0`
and `body_arg: <arity − 1>` with `origin_param: 0` hold for all nine rules exactly as
they do for `route` today.

**Q1b — `handle` (§4c).** `Route` is an INTERFACE and `handle(Function2)V` is its
abstract member — not an extension on `RoutingBuilderKt`. A call site is therefore
`invokeinterface Route.handle` on the block's own parameter (`receiver_parameter`), so
the terminal rule is declared on owner `io.ktor.server.routing.Route` with NO
`receiver_arg` (the receiver is the receiver, not an argument) and `handler_arg: 0`.

**Q2 — `DefaultMethods` (§4c).** Seven members, in this order: `Get, Post, Put, Patch,
Delete, Head, Options`, built by `CollectionsKt.listOf` over the seven fields the static
initialiser had just written. `all_methods` for a verb-less `handle` under no `method`
selector is therefore seven rows — `GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS` — not
Spring's eight (there is no `TRACE`), and the verbs are the literals the fields were
built from, read off the same initialiser.

**Q3 — `HttpMethod.Get` is a getter (§4b, F5).** `HttpMethod$Companion.getGet()` is
`invokestatic HttpMethod.access$getGet$cp` — a synthetic accessor for the private static
field `Get`, which the initialiser built from `ldc "GET"`. The same for the other six.
A Kotlin call site writing `HttpMethod.Get` is therefore a CALL on the companion object
(`getstatic HttpMethod.Companion ; invokevirtual HttpMethod$Companion.getGet`), never a
`GETSTATIC` of a constant the existing `media_values` member-name table could read; the
value reaches a `method(...)`/`route(..., HttpMethod, ...)` argument as `{kind:
unresolved, source: <the getter's result>}`, and §4b's `getters:` key form — resolved
through `_producing_site` to the getter call and from its NAME to the value in this
table — is the reading that works. The name→value table is exactly Q3's cell:
`getGet → GET`, `getPost → POST`, `getPut → PUT`, `getPatch → PATCH`, `getDelete →
DELETE`, `getHead → HEAD`, `getOptions → OPTIONS`.

**Q4 — `ContentType.Application.Json` is a getter (§4b, F5).**
`ContentType$Application.getJson()` is `getstatic ContentType$Application.Json` — a
field the nested object's initialiser built from `ldc "application" ; ldc "json"`, the
type and subtype the `ContentType` constructor joins with `/`. The same shape for all
twenty-two getters; the cell lists each name with its `type/subtype`. A call site writing
`ContentType.Application.Json` is `getstatic ContentType$Application.INSTANCE ;
invokevirtual getJson`, so the `accept`/`contentType` media reader needs the same
`getters:` form as Q3, keyed on owner `io.ktor.http.ContentType$Application` and the
getter name, yielding the wire value in this table.

**Q5 — `getOrFail` throws (§5d, A3).** Two overloads on `io.ktor.server.util.ParametersKt`:
`getOrFail(Parameters, String): String` and the reified `getOrFail<R>(Parameters, String):
R` — whose inlined body is `getOrFailImpl(Parameters, String, TypeInfo)`. Both bodies read
the container (`Parameters.get` / `Parameters.getAll`), `ifnonnull` past a `new
io.ktor.server.plugins.MissingRequestParameterException ; athrow`. So a handler calling
`call.parameters.getOrFail("cursor")` cannot run without the value: the FRAMEWORK
refuses the request, and `requirement: required` is a statement about Ktor, not about the
handler's own `?: throw` (which is exactly the line A3 draws — a bare `get` stays NULL).
The typed overload additionally throws `ParameterConversionException` when the value is
present but does not convert, which is a different requirement (a type) this spec does
not record.

**Q6 — one `get` owner for three reads (§5d).** `ApplicationRequest.getHeaders()` returns
`io.ktor.http.Headers`, `ApplicationRequest.getQueryParameters()` and
`ApplicationCall.getParameters()` return `io.ktor.http.Parameters`, and both interfaces
extend `io.ktor.util.StringValues`, which declares `get(String): String` and `getAll(String):
List`. A Kotlin `headers["X-Trace"]` compiles to `invokeinterface StringValues.get` — or
`Headers.get`/`Parameters.get`, depending on the static receiver type kotlinc chose — on
the value the getter returned, so a `request_reads` entry names the container getter
(`via`) and the `get` the read is made through (`then`), and the three reads differ only
in WHICH getter produced the receiver: `getHeaders → header`, `getQueryParameters →
query`, `getParameters → param` (a path variable when the name is in the route's own
path, `skip_path_variables`). NULL requirement on all three: `get` returns `null` for an
absent name and the handler decides.

**Q7 — a method mismatch never dispatches (§4b, A11).** `HttpMethodRouteSelector.evaluate`
reads the request's method (`ApplicationRequestPropertiesKt.getHttpMethod`), compares it
to the selector's own `method` field with `Intrinsics.areEqual`, and returns
`RouteSelectorEvaluation.Companion.getConstant()` on a match and
`RouteSelectorEvaluation.Companion.getFailedMethod()` — a `RouteSelectorEvaluation$Failure`
— otherwise. A route under two `method` selectors that disagree (`method(Post) { get("/x")
{ } }`) has a node whose method selector fails for every request the other's would pass,
so Ktor never dispatches it: the honest row for that shape is NO row (a phantom would
claim an address that cannot be reached), stated on the catalog and in COVERAGE, as A2
rules. Read off the bytecode of one selector, without a server run — the A11 ruling.

`measured: 2026-09-20`, all seven questions, on the three archives the scope names.
