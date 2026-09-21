# CP-26 — route-tree predicates as request requirements: `RequestPredicates.queryParam`/`param`, the gateway's `header`/`query`/`cookie`, and the properties spellings

**Question.** Spec 2026-09-19 §5c reads three families of route-tree predicates as
INBOUND REQUEST REQUIREMENTS — what a framework's routing tree demands of a request
before the route serves it (`endpoint_metadata.requirement`): the Spring functional
router's `RequestPredicates.queryParam(String, String)` and `queryParam(String,
Predicate)` on the reactive stack and whatever the servlet twin spells them as; Spring
Cloud Gateway's `PredicateSpec` `header`/`query`/`cookie` overloads, and the same names
reached after an `and()`/`or()` under the static type `BooleanSpec$BooleanOpSpec`. Each
rests on a shape of the jars no probe had recorded: Q1 the reactive overloads, and the
`QueryParamPredicate.test` bytecode that makes the requirement `required` (the predicate
is false without the parameter, so the route does not match); Q2 the SERVLET twin's
overloads — which turn out to be `param`, not `queryParam` — and Q2b what
`ServerRequest.param` reads, which decides the `kind` (`query` vs `param`, §5a); Q3 the
gateway's six overloads and which carry a value; Q4 whether `BooleanOpSpec` overrides
them (if not, the catalog declares the same rule on both owners because the facts carry
the receiver's static type); Q5 the `Header=`/`Query=`/`Cookie=` properties spellings,
recorded for `gateway-properties-routes` — out of §5c's scope, and left here so the item
that lands it starts from a measurement; Q6 (added 2026-09-20, after the whole-branch
review) how each of the three factories MATCHES the regex a route hands it — the reading
the `value` column's "regex as written" rule rests on (spec §5a, D01 §3, D02 §2k, M06),
which those documents had cited as a `javap` read with no row to point at.

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file in one of three jars. It measures the compiled surface, not the source or the
documentation. Q1/Q2 read the predicate's `test` body and stop there: that the router
falls through to the next route (and to 404) when a predicate is false is the functional
router's dispatch contract, read off one predicate here and not re-derived from
`RouterFunctions`. Q3 reads the overload SIGNATURES; what the `*RoutePredicateFactory`
each builds does with an absent header (the route does not match) is the gateway's
documented predicate contract and is not re-read off the factory bodies — Q6 reads those
bodies for ONE thing, the call that matches a present value against `regexp`, and stops
there. Q5 reads the shortcut field ORDER only, not the properties binder that consumes
it. Nothing here measures the resolve-layer rules the spec specifies, which did not yet
exist when this was recorded.

**Version scope (§5.4).** `org.springframework:spring-webflux` and
`org.springframework:spring-webmvc` at Maven coordinate `6.1.6`, and
`org.springframework.cloud:spring-cloud-gateway-server-webflux` at `5.0.0` — and, as the
identity the harness files every cell under, the `Implementation-Version` each jar's own
`META-INF/MANIFEST.MF` reports, read as **6.1.6** for the two Spring jars and **5.0.0**
for the gateway jar. The harness aborts when an archive reports a version other than the
one the run expected. Every verdict below is bounded by those three archives; they are the
artifacts `spring-webflux-router.yml`, `spring-mvc-router.yml` and
`spring-cloud-gateway.yml` are measured against.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp26_route_predicates/run.sh`. It resolves the three jars into `~/.m2`
(Maven and network on the first run only), then runs `probe.py`, which reads each jar's
`Implementation-Version` off its manifest before it measures anything and prints the
table below. Needs a JDK for `javap`. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version each jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's artifact list asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column. Every cell is a `javap -p -s`/`-c` read of the named class in the
named artifact.

```
| what the run read | 5.0.0 | 6.1.6 |
|---|---|---|
| artifacts reporting this version | org.springframework.cloud:spring-cloud-gateway-server-webflux | org.springframework:spring-webflux, org.springframework:spring-webmvc |
| identity read from the archive itself (`Implementation-Version`) | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | reactive RequestPredicates.queryParam/param/headers overloads, and QueryParamPredicate.test | `org.springframework:spring-webflux` | 6.1.6 | `queryParam(Ljava/lang/String;Ljava/lang/String;)Lorg/springframework/web/reactive/function/server/RequestPredicate; ; queryParam(Ljava/lang/String;Ljava/util/function/Predicate;)Lorg/springframework/web/reactive/function/server/RequestPredicate; ; headers(Ljava/util/function/Predicate;)Lorg/springframework/web/reactive/function/server/RequestPredicate; ; QueryParamPredicate.test: invokeinterface InterfaceMethod org/springframework/web/reactive/function/server/ServerRequest.queryParam:(Ljava/lang/String;)Ljava/util/Optional; ; invokevirtual Method java/util/Optional.filter:(Ljava/util/function/Predicate;)Ljava/util/Optional; ; invokevirtual Method java/util/Optional.isPresent:()Z ; ireturn` |
| 2 | servlet RequestPredicates.queryParam/param/headers overloads, and ParamPredicate.test | `org.springframework:spring-webmvc` | 6.1.6 | `param(Ljava/lang/String;Ljava/lang/String;)Lorg/springframework/web/servlet/function/RequestPredicate; ; param(Ljava/lang/String;Ljava/util/function/Predicate;)Lorg/springframework/web/servlet/function/RequestPredicate; ; headers(Ljava/util/function/Predicate;)Lorg/springframework/web/servlet/function/RequestPredicate; ; ParamPredicate.test: invokeinterface InterfaceMethod org/springframework/web/servlet/function/ServerRequest.param:(Ljava/lang/String;)Ljava/util/Optional; ; invokevirtual Method java/util/Optional.filter:(Ljava/util/function/Predicate;)Ljava/util/Optional; ; invokevirtual Method java/util/Optional.isPresent:()Z ; ireturn` |
| 2b | servlet ServerRequest.param → params() → what DefaultServerRequest reads off HttpServletRequest | `org.springframework:spring-webmvc` | 6.1.6 | `ServerRequest.param: invokeinterface InterfaceMethod params:()Lorg/springframework/util/MultiValueMap; ; invokeinterface InterfaceMethod org/springframework/util/MultiValueMap.get:(Ljava/lang/Object;)Ljava/lang/Object; ; ServletParametersMap reads: jakarta/servlet/http/HttpServletRequest.getParameterMap:()Ljava/util/Map;, jakarta/servlet/http/HttpServletRequest.getParameterValues:(Ljava/lang/String;)[Ljava/lang/String;` |
| 3 | PredicateSpec header/query/cookie overloads | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `header(Ljava/lang/String;)Lorg/springframework/cloud/gateway/route/builder/BooleanSpec; ; header(Ljava/lang/String;Ljava/lang/String;)Lorg/springframework/cloud/gateway/route/builder/BooleanSpec; ; query(Ljava/lang/String;Ljava/util/function/Predicate;)Lorg/springframework/cloud/gateway/route/builder/BooleanSpec; ; query(Ljava/lang/String;Ljava/lang/String;)Lorg/springframework/cloud/gateway/route/builder/BooleanSpec; ; query(Ljava/lang/String;)Lorg/springframework/cloud/gateway/route/builder/BooleanSpec; ; cookie(Ljava/lang/String;Ljava/lang/String;)Lorg/springframework/cloud/gateway/route/builder/BooleanSpec;` |
| 4 | BooleanSpec$BooleanOpSpec: superclass, declared members, whether header/query/cookie are overridden | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `public class org.springframework.cloud.gateway.route.builder.BooleanSpec$BooleanOpSpec extends org.springframework.cloud.gateway.route.builder.PredicateSpec ; declares: asyncPredicate, nested, not, predicate ; header/query/cookie overridden here: none (inherited)` |
| 5 | Header/Query/Cookie RoutePredicateFactory.shortcutFieldOrder — the properties spellings | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `HeaderRoutePredicateFactory.shortcutFieldOrder: header, regexp ; QueryRoutePredicateFactory.shortcutFieldOrder: param, regexp, predicate ; CookieRoutePredicateFactory.shortcutFieldOrder: name, regexp` |
| 6 | Header/Query/Cookie RoutePredicateFactory: what apply builds and how its predicate matches regexp — Pattern.asMatchPredicate or String.matches | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `HeaderRoutePredicateFactory.apply: invokestatic Method java/util/regex/Pattern.compile:(Ljava/lang/String;)Ljava/util/regex/Pattern; ; invokespecial Method org/springframework/cloud/gateway/handler/predicate/HeaderRoutePredicateFactory$1."<init>":(Lorg/springframework/cloud/gateway/handler/predicate/HeaderRoutePredicateFactory;Lorg/springframework/cloud/gateway/handler/predicate/HeaderRoutePredicateFactory$Config;Ljava/util/regex/Pattern;)V ; $1.test: invokeinterface InterfaceMethod org/springframework/http/server/reactive/ServerHttpRequest.getHeaders:()Lorg/springframework/http/HttpHeaders; ; invokevirtual Method java/util/regex/Pattern.asMatchPredicate:()Ljava/util/function/Predicate; ; QueryRoutePredicateFactory.apply: invokespecial Method org/springframework/cloud/gateway/handler/predicate/QueryRoutePredicateFactory$1."<init>":(Lorg/springframework/cloud/gateway/handler/predicate/QueryRoutePredicateFactory;Lorg/springframework/cloud/gateway/handler/predicate/QueryRoutePredicateFactory$Config;)V ; $1.test: invokeinterface InterfaceMethod org/springframework/http/server/reactive/ServerHttpRequest.getQueryParams:()Lorg/springframework/util/MultiValueMap; ; invokeinterface InterfaceMethod org/springframework/http/server/reactive/ServerHttpRequest.getQueryParams:()Lorg/springframework/util/MultiValueMap; ; invokedynamic InvokeDynamic #0:test:(Lorg/springframework/cloud/gateway/handler/predicate/QueryRoutePredicateFactory$Config;)Ljava/util/function/Predicate; ; $1.lambda$test$0: invokevirtual Method java/lang/String.matches:(Ljava/lang/String;)Z ; CookieRoutePredicateFactory.apply: invokespecial Method org/springframework/cloud/gateway/handler/predicate/CookieRoutePredicateFactory$1."<init>":(Lorg/springframework/cloud/gateway/handler/predicate/CookieRoutePredicateFactory;Lorg/springframework/cloud/gateway/handler/predicate/CookieRoutePredicateFactory$Config;)V ; $1.test: invokeinterface InterfaceMethod org/springframework/http/server/reactive/ServerHttpRequest.getCookies:()Lorg/springframework/util/MultiValueMap; ; invokedynamic InvokeDynamic #0:test:(Lorg/springframework/cloud/gateway/handler/predicate/CookieRoutePredicateFactory$Config;)Ljava/util/function/Predicate; ; $1.lambda$test$0: invokevirtual Method org/springframework/http/HttpCookie.getValue:()Ljava/lang/String; ; invokevirtual Method java/lang/String.matches:(Ljava/lang/String;)Z` |
```

## Verdicts

**Q1 — the reactive `queryParam` (§5c).** Two overloads on
`org.springframework.web.reactive.function.server.RequestPredicates`:
`queryParam(String, String)` and `queryParam(String, Predicate<String>)`, sharing a name
and an arity and differing at position 1's type — so the catalog's two
`request_requirement` rules are told apart by `arg_types`, exactly as the router's
same-arity verb overloads are (spec §3c). `QueryParamPredicate.test` is
`ServerRequest.queryParam(name).filter(valuePredicate).isPresent()`: false when the
parameter is absent, false when present and not matching — so the requirement is
`required`, with the literal as its value for the String form and NULL for the Predicate
form (a function the walk cannot read). `headers(Predicate<Headers>)` is one overload
taking an arbitrary function over the whole header map; nothing about a specific header
is readable from it, and the catalog states it unread.

**Q2 / Q2b — the servlet twin spells it `param`, and it is kind `param` (§5a, §5c).**
`org.springframework.web.servlet.function.RequestPredicates` declares NO `queryParam`.
Its parameter predicate is `param(String, String)` / `param(String, Predicate<String>)`,
whose `ParamPredicate.test` is the same shape as Q1's — `ServerRequest.param(name).
filter(p).isPresent()`, `required`. But `ServerRequest.param` reads `params()`, which
`DefaultServerRequest` backs with a `ServletParametersMap` over
`HttpServletRequest.getParameterMap`/`getParameterValues` — the servlet container's
merged view of the query string AND a form body, the one API that cannot tell the two
apart. Spec §5a reserves `kind: param` for exactly this case, so `spring-mvc-router.yml`
declares `param` with `kind: param` where the reactive catalog declares `queryParam` with
`kind: query` (Q1's `ServerRequest.queryParam` reads the query string alone). A catalog
copied from the reactive twin — `queryParam`, kind `query` — would have matched nothing
on the servlet stack, silently; this is the row that stopped it.

**Q3 — the gateway's six overloads (§5c).** On `PredicateSpec`: `header(String)`,
`header(String, String)`, `query(String)`, `query(String, String)`, `query(String,
Predicate<String>)`, `cookie(String, String)` — every one returning `BooleanSpec`, so
each carries the chain on (a pass-through) AND names what the route demands. The
one-argument forms demand presence; the `(String, String)` forms demand a match against a
regex the catalog carries as the value, as written; the Predicate form demands a match the
walk cannot read. All `required`. A continuation is matched on name and owner alone, so
ONE rule per name covers every overload: `value_arg: 1` reads the regex where the call
carries a second String, NULL where it carries none, and NULL-unresolved where it carries
a predicate.

**Q4 — `BooleanOpSpec` inherits them (§5c).** `BooleanSpec$BooleanOpSpec extends
PredicateSpec` and declares only `asyncPredicate`, `nested`, `not` and `predicate`;
`header`/`query`/`cookie` are not overridden. A call after an `and()`/`or()` still
carries `BooleanOpSpec` as its owner — the receiver's static type, JLS 13.1, the rule
every predicate in `spring-cloud-gateway.yml` already declares twice for — so the same
`request_requirement` continuation is declared on both owners, and the second
declaration is the inheritance made explicit rather than a second measurement.

**Q5 — the properties spellings (recorded, out of scope).**
`HeaderRoutePredicateFactory.shortcutFieldOrder` is `header, regexp`;
`QueryRoutePredicateFactory`'s is `param, regexp, predicate`; `CookieRoutePredicateFactory`'s
is `name, regexp`. So `Header=X-Api,v2` binds `header=X-Api, regexp=v2`,
`Query=debug` binds `param=debug` alone, `Cookie=session,.*` binds `name=session,
regexp=.*`. Property-declared routes derive nothing today (`gateway-properties-routes`,
open); when that item lands, its predicates land as the same `request_requirement` word on
these spellings.

**Q6 — all three factories match the regex against the whole value (§5a, §5c; the
`value` column).** `HeaderRoutePredicateFactory.apply` compiles `regexp` with
`Pattern.compile` and hands the `Pattern` to its anonymous predicate, whose `test` reads
the request's headers and matches each value with `Pattern.asMatchPredicate()`.
`QueryRoutePredicateFactory$1.test` reads `getQueryParams` and tests each value through a
lambda, `lambda$test$0`, that calls `String.matches(regexp)`;
`CookieRoutePredicateFactory$1.test` reads `getCookies` and its `lambda$test$0` calls
`String.matches(regexp)` on `HttpCookie.getValue()`. Both JDK calls match the ENTIRE
input (`asMatchPredicate` is `matcher(s).matches()`, `String.matches` is
`Pattern.matches` — the JDK's documented contract, not re-read here). So
`header("X-Request-Id", "\\d+")` demands a
value the WHOLE of which is digits, and the catalog's `value` carries `\\d+` as written:
it is the framework's own spelling of the demand, not a literal a client must send, and a
consumer compares it for equality only where the spelling is a literal (M06).

`measured: 2026-09-20`, all six questions (seven rows), on the three archives the scope names.
