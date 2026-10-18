# CP-29 — Spring Cloud Gateway 5.0.0 property routes: the prefix, the shortcut grammar, the five predicate factories, the `uri` scheme, `HttpMethod` at spring-web 6.1.6, and the router DSLs' media overloads

**Question.** Spec 2026-09-21 §7b reads routes declared in configuration —
`spring.cloud.gateway.server.webflux.routes[N]` — through `config_join`'s new `indexed:`
address form: each item's `predicates[M]` is a shortcut string (`Name=a,b`) or a map
(`name` + `args.<field>`), `Path` supplies the served pattern(s), `Method` the verbs,
`Header`/`Query`/`Cookie` the route's request requirements, and `uri` the target. §7a
reads the router DSLs' `accept(MediaType, Function)`/`contentType(MediaType, Function)` as
verb-less routes under a media guard. Each rests on a shape of the jars no probe had
recorded: Q1 the prefix `GatewayProperties` binds under (F6); Q2 whether the pre-4.2 prefix
`spring.cloud.gateway.routes` binds ANYWHERE in the 5.0.0 jar — a legacy properties class, a
`@DeprecatedConfigurationProperty`, a metadata deprecation, an environment post-processor
that migrates it (F6's condition for admitting a second prefix); Q3 `PredicateDefinition(
String)`'s grammar (F7); Q4 `RouteDefinition`'s fields and its own `String` constructor; Q5
the five factories' `shortcutFieldOrder`/`shortcutType` and the `Config` each binds into;
Q6 every predicate factory the jar declares, by the name the framework derives from the
class name; Q7 what each `ShortcutType` normaliser does with the positional `_genkey_N`
arguments; Q8 how the `uri` scheme is read (`lb`); Q9 `HttpMethod.values()` at spring-web
6.1.6 (F9 — recorded, and NOT used by §7a per §0b A1), `HttpMethod.valueOf(String)`, and
the comparison the `Method` predicate makes; Q10 the `accept`/`contentType` descriptors on
`RouterFunctionDsl`, `CoRouterFunctionDsl` (spring-webflux) and the servlet
`RouterFunctionDsl` (spring-webmvc) at 6.1.6 (§7a).

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file, or a byte scan of the archive's own entries, in one of four jars. It measures
the compiled 5.0.0 / 6.1.6 surface, not the Java source or the reference documentation.
Q2's negative is bounded to THIS artifact: `spring-cloud-gateway-server-webflux` 5.0.0
carries the legacy prefix nowhere (no class, no metadata, no post-processor migrates it), so
a module whose only Gateway dependency is this jar does not bind it; whether some OTHER
artifact on a module's classpath (a deprecated shim, a starter of an earlier line) would
bind it is not measured here and the catalog states that boundary rather than declaring
the prefix. Q5 reads the field ORDER off each factory's `shortcutFieldOrder`; that Spring
Boot's `Binder` then binds the normalised map onto `Config` by relaxed name is the
framework's own binding contract, which this probe reads at one call
(`ConfigurationService.bindOrCreate` constructs a `Binder` over a
`MapConfigurationPropertySource`) and does not re-derive. Q8 reads the `lb` scheme test
and the request-URL filter's scheme regex; the load balancer's own resolution of the host
that follows `lb://` is not measured. Nothing here measures the resolve-layer rules the
spec specifies.

**Version scope (§5.4).** `org.springframework.cloud:spring-cloud-gateway-server-webflux`
at Maven coordinate `5.0.0` — the version `fixtures/orders-gateway/pom.xml` builds against —
and `org.springframework:spring-web`, `spring-webflux` and `spring-webmvc` at `6.1.6`, the
versions the router catalogs are measured at (`scripts/probes/cp12_sweep_round1b.md`); and,
as the identity the harness files every cell under, the `Implementation-Version` each jar's
own `META-INF/MANIFEST.MF` reports, read as **5.0.0** for the Gateway jar and **6.1.6** for
the three Spring jars. The harness aborts when an archive reports a version other than the
one the run expected. Every verdict below is bounded by those four archives.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp29_gateway_properties/run.sh`. It resolves the four jars into `~/.m2`
(Maven and network on the first run only), then runs `probe.py`, which reads each jar's
`Implementation-Version` off its manifest before it measures anything and prints the table
below. Needs a JDK for `javap`. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version each jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's `ARTIFACTS` parameter asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column. Every cell is a `javap -p -s`/`-c`/`-constants`/`-v` read of the named
class in the named artifact, or (row 2) a scan of every entry's bytes in the archive.

```
| what the run read | 5.0.0 | 6.1.6 |
|---|---|---|
| artifacts reporting this version | org.springframework.cloud:spring-cloud-gateway-server-webflux | org.springframework:spring-web, org.springframework:spring-webflux, org.springframework:spring-webmvc |
| identity read from the archive itself (`Implementation-Version`) | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 11 | does a route declaring only `Path=` constrain the method at all | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `combinePredicates empty-list arm: ['invokeinterface InterfaceMethod java/util/List.isEmpty:()Z', 'invokedynamic InvokeDynamic #9:test:()Ljava/util/function/Predicate;', 'invokestatic InterfaceMethod org/springframework/cloud/gateway/handler/AsyncPredicate.from:(Ljava/util/function/Predicate;)Lorg/springframework/cloud/gateway/handler/AsyncPredicate;', 'invokedynamic InvokeDynamic #10:apply:(Lorg/springframework/cloud/gateway/route/RouteDefinitionRouteLocator;Lorg/springframework/cloud/gateway/route/RouteDefinition;)Ljava/util/function/Function;', 'invokedynamic InvokeDynamic #11:test:()Ljava/util/function/Predicate;', 'invokestatic InterfaceMethod org/springframework/cloud/gateway/handler/AsyncPredicate.from:(Ljava/util/function/Predicate;)Lorg/springframework/cloud/gateway/handler/AsyncPredicate;', 'invokedynamic InvokeDynamic #12:apply:()Ljava/util/function/BinaryOperator;'] ; HttpMethod mentions in the whole class: 0` |
| 1 | F6: `GatewayProperties.PREFIX`, its `@ConfigurationProperties`, the `routes` field | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `public static final java.lang.String PREFIX = "spring.cloud.gateway.server.webflux" ; org.springframework.boot.context.properties.ConfigurationProperties( value="spring.cloud.gateway.server.webflux" ) ; private java.util.List<org.springframework.cloud.gateway.route.RouteDefinition> routes` |
| 2 | F6: does `spring.cloud.gateway.routes` bind anywhere in this jar — byte scan, metadata, post-processors | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `entries carrying `spring.cloud.gateway.routes`: none ; entries carrying `DeprecatedConfigurationProperty`: none ; class names matching Deprecated|Legacy|Compat|Migrat: ['GatewayLegacyControllerEndpoint.class'] ; metadata `*.routes` properties: ['spring.cloud.gateway.server.webflux.routes'] ; metadata deprecations: none ; EnvironmentPostProcessor: ['org.springframework.cloud.gateway.config.GatewayEnvironmentPostProcessor'] ; postProcessEnvironment ldc: ['ldc String gateway-properties', 'ldc String spring.webflux.hiddenmethod.filter.enabled', 'ldc String false']` |
| 3 | F7: `PredicateDefinition` fields and `PredicateDefinition(String)`'s grammar | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `fields ['java.lang.String name', 'java.util.Map<java.lang.String, java.lang.String> args'] ; public static final java.lang.String GENERATED_NAME_PREFIX = "_genkey_" ; bipush 61 ; invokevirtual Method java/lang/String.indexOf:(I)I ; athrow ; invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; invokevirtual Method setName:(Ljava/lang/String;)V ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; ldc String , ; invokestatic Method org/springframework/util/StringUtils.tokenizeToStringArray:(Ljava/lang/String;Ljava/lang/String;)[Ljava/lang/String; ; invokestatic Method org/springframework/cloud/gateway/support/NameUtils.generateName:(I)Ljava/lang/String; ; invokeinterface InterfaceMethod java/util/Map.put:(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` |
| 4 | F7: `RouteDefinition` fields and `RouteDefinition(String)`'s grammar | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `fields ['java.lang.String id', 'java.util.List<org.springframework.cloud.gateway.handler.predicate.PredicateDefinition> predicates', 'java.util.List<org.springframework.cloud.gateway.filter.FilterDefinition> filters', 'java.net.URI uri', 'java.util.Map<java.lang.String, java.lang.Object> metadata', 'int order', 'boolean enabled'] ; bipush 61 ; invokevirtual Method java/lang/String.indexOf:(I)I ; invokevirtual Method setId:(Ljava/lang/String;)V ; invokestatic Method org/springframework/util/StringUtils.tokenizeToStringArray:(Ljava/lang/String;Ljava/lang/String;)[Ljava/lang/String; ; invokestatic Method java/net/URI.create:(Ljava/lang/String;)Ljava/net/URI; ; invokevirtual Method setUri:(Ljava/net/URI;)V ; invokespecial Method org/springframework/cloud/gateway/handler/predicate/PredicateDefinition."<init>":(Ljava/lang/String;)V` |
| 5 | the five factories: `shortcutFieldOrder`, `shortcutType`, `Config` fields | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `Path: shortcutFieldOrder ['patterns', 'matchTrailingSlash'] / shortcutType ['GATHER_LIST_TAIL_FLAG'] / Config ['java.util.List<java.lang.String> patterns', 'boolean matchTrailingSlash'] ; Method: shortcutFieldOrder ['methods'] / shortcutType ['GATHER_LIST'] / Config ['org.springframework.http.HttpMethod[] methods'] ; Header: shortcutFieldOrder ['header', 'regexp'] / shortcutType ['inherited'] / Config ['java.lang.String header', 'java.lang.String regexp'] ; Query: shortcutFieldOrder ['param', 'regexp', 'predicate'] / shortcutType ['inherited'] / Config ['java.lang.String param', 'java.lang.String regexp', 'java.util.function.Predicate<java.lang.String> predicate'] ; Cookie: shortcutFieldOrder ['name', 'regexp'] / shortcutType ['inherited'] / Config ['java.lang.String name', 'java.lang.String regexp'] ; ShortcutConfigurable default shortcutType: ['DEFAULT']` |
| 6 | every predicate factory the jar declares, by the name the framework derives | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `names ['After', 'Before', 'Between', 'CloudFoundryRouteService', 'Cookie', 'Header', 'Host', 'Method', 'Path', 'Query', 'ReadBody', 'RemoteAddr', 'Version', 'Weight', 'XForwardedRemoteAddr'] ; normalizeRoutePredicateName: ['invokevirtual Method java/lang/Class.getSimpleName:()Ljava/lang/String;', 'ldc class org/springframework/cloud/gateway/handler/predicate/RoutePredicateFactory', 'invokevirtual Method java/lang/Class.getSimpleName:()Ljava/lang/String;', 'ldc String', 'invokevirtual Method java/lang/String.replace:(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;', 'invokestatic Method removeGarbage:(Ljava/lang/String;)Ljava/lang/String;']` |
| 7 | `ShortcutType`'s three normalisers and `normalizeKey` | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `members ['DEFAULT', 'GATHER_LIST', 'GATHER_LIST_TAIL_FLAG'] ; DEFAULT: ['invokestatic InterfaceMethod org/springframework/cloud/gateway/support/ShortcutConfigurable.normalizeKey:(Ljava/lang/String;ILorg/springframework/cloud/gateway/support/ShortcutConfigurable;Ljava/util/Map;)Ljava/lang/String;', 'invokeinterface InterfaceMethod java/util/Map.put:(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;'] ; GATHER_LIST: ['invokeinterface InterfaceMethod org/springframework/cloud/gateway/support/ShortcutConfigurable.shortcutFieldOrder:()Ljava/util/List;', 'ldc String Shortcut Configuration Type GATHER_LIST must have shortcutFieldOrder of size 1', 'invokestatic Method java/util/stream/Collectors.toList:()Ljava/util/stream/Collector;', 'invokeinterface InterfaceMethod java/util/Map.put:(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;'] ; GATHER_LIST_TAIL_FLAG: ['invokeinterface InterfaceMethod org/springframework/cloud/gateway/support/ShortcutConfigurable.shortcutFieldOrder:()Ljava/util/List;', 'ldc String Shortcut Configuration Type GATHER_LIST_HEAD must have shortcutFieldOrder of size 2', 'ldc String true', 'invokevirtual Method java/lang/String.equalsIgnoreCase:(Ljava/lang/String;)Z', 'ldc String false', 'invokevirtual Method java/lang/String.equalsIgnoreCase:(Ljava/lang/String;)Z', 'invokeinterface InterfaceMethod java/util/List.subList:(II)Ljava/util/List;', 'invokeinterface InterfaceMethod java/util/Map.put:(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;', 'invokestatic Method java/util/stream/Collectors.toList:()Ljava/util/stream/Collector;', 'invokeinterface InterfaceMethod java/util/Map.put:(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;'] ; normalizeKey: ['ldc String _genkey_', 'invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z', 'invokeinterface InterfaceMethod shortcutFieldOrder:()Ljava/util/List;', 'invokeinterface InterfaceMethod shortcutFieldOrder:()Ljava/util/List;', 'invokeinterface InterfaceMethod shortcutFieldOrder:()Ljava/util/List;', 'invokeinterface InterfaceMethod java/util/List.get:(I)Ljava/lang/Object;']` |
| 8 | the `uri` scheme: `lb` and the request-URL filter | `org.springframework.cloud:spring-cloud-gateway-server-webflux` | 5.0.0 | `ReactiveLoadBalancerClientFilter.filter: ['ldc String lb', 'invokevirtual Method java/net/URI.getScheme:()Ljava/lang/String;', 'invokevirtual Method java/lang/String.equals:(Ljava/lang/Object;)Z', 'ldc String lb', 'invokevirtual Method java/lang/String.equals:(Ljava/lang/Object;)Z', 'ldc class org/springframework/cloud/gateway/filter/ReactiveLoadBalancerClientFilter', 'ldc String requestUri can not be null', 'invokevirtual Method java/net/URI.getHost:()Ljava/lang/String;', 'ldc class org/springframework/cloud/client/loadbalancer/LoadBalancerLifecycle', 'ldc class org/springframework/cloud/client/loadbalancer/RequestDataContext', 'ldc class org/springframework/cloud/client/loadbalancer/ResponseData', 'ldc class org/springframework/cloud/client/ServiceInstance'] ; private static final java.lang.String SCHEME_REGEX = "[a-zA-Z]([a-zA-Z]|\\d|\\+|\\.|-)*:.*" ; RouteToRequestUrlFilter.filter: ['ldc String RouteToRequestUrlFilter start', 'invokestatic Method hasAnotherScheme:(Ljava/net/URI;)Z', 'invokevirtual Method java/net/URI.getScheme:()Ljava/lang/String;', 'invokevirtual Method java/net/URI.getSchemeSpecificPart:()Ljava/lang/String;', 'ldc String lb', 'invokevirtual Method java/net/URI.getScheme:()Ljava/lang/String;', 'invokevirtual Method java/net/URI.getScheme:()Ljava/lang/String;']` |
| 9 | F9: `HttpMethod.values()`, `valueOf(String)`, and how `Method` compares | `org.springframework:spring-web` | 6.1.6 | `values() ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE'] ; valueOf: 8 equals arms then ['new class org/springframework/http/HttpMethod'] ; MethodRoutePredicateFactory$1.lambda$test$0: ['aload_1', 'aload_0', 'if_acmpne 9', 'iconst_1', 'goto 10', 'iconst_0', 'ireturn']` |
| 10 | §7a: `accept`/`contentType` overloads on the three router DSL classes | `org.springframework:spring-webflux` | 6.1.6 | `RouterFunctionDsl.accept: ['(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function1;)V', '([Lorg/springframework/http/MediaType;)Lorg/springframework/web/reactive/function/server/RequestPredicate;'] ; RouterFunctionDsl.contentType: ['(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function1;)V', '([Lorg/springframework/http/MediaType;)Lorg/springframework/web/reactive/function/server/RequestPredicate;'] ; CoRouterFunctionDsl.accept: ['(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function2;)V', '([Lorg/springframework/http/MediaType;)Lorg/springframework/web/reactive/function/server/RequestPredicate;'] ; CoRouterFunctionDsl.contentType: ['(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function2;)V', '([Lorg/springframework/http/MediaType;)Lorg/springframework/web/reactive/function/server/RequestPredicate;'] ; RouterFunctionDsl.accept: ['(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function1;)V', '([Lorg/springframework/http/MediaType;)Lorg/springframework/web/servlet/function/RequestPredicate;'] ; RouterFunctionDsl.contentType: ['(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function1;)V', '([Lorg/springframework/http/MediaType;)Lorg/springframework/web/servlet/function/RequestPredicate;']` |

## Verdicts

**Q11 — a route declaring only `Path=` constrains no method, so a fan-out over all eight
is honest here.** Added 2026-10-17, for the user's rule: *fan out, but only to methods that
are supported, not invalid ones.* Two readings of `RouteDefinitionRouteLocator`, the class
that turns a definition into a `Route`. `combinePredicates` with an EMPTY predicate list
returns `AsyncPredicate.from(<invokedynamic #9:test>)` — a predicate that always holds — and
a non-empty list is those predicates reduced with a `BinaryOperator`, nothing more. And
**`HttpMethod` is mentioned ZERO times in the whole class**: route construction cannot
constrain a method it never names. A `Method=` predicate is the only thing that does, and
Q9 reads its comparison.

**That is what makes the gateway different from `RouterFunctions.resources(...)`**, which is
verb-less too and serves GET, HEAD and OPTIONS only (spec 2026-09-21 §0b A1) — so fanning
THAT out publishes five routes nobody can call, and its catalog declines `all_methods` for
exactly that reason. `all_methods` is declared per CATALOG, and the router catalog mixes
routes that accept everything with one that accepts three; the gateway catalogs have no such
mix.


**Q1 — the prefix is `spring.cloud.gateway.server.webflux` (F6, §7b).** `GatewayProperties.PREFIX`
is that constant, `@ConfigurationProperties(value = "spring.cloud.gateway.server.webflux")`
binds the class under it, and `routes` is a `List<RouteDefinition>` — so the route list
reaches configuration as `spring.cloud.gateway.server.webflux.routes[N]`, which is the
`indexed.prefix` `spring-cloud-gateway-properties.yml` declares. The metadata the jar ships
names `spring.cloud.gateway.server.webflux.routes` and no other `*.routes` property.

**Q2 — the legacy prefix is NOT declared (F6's condition fails).** A byte scan of every
entry in the 5.0.0 archive finds `spring.cloud.gateway.routes` in no class file and no
resource; no entry carries `DeprecatedConfigurationProperty`; the metadata declares no
deprecation; the one class whose name matches `Legacy` is
`GatewayLegacyControllerEndpoint` (an actuator endpoint, not a properties class); and the
jar's one `EnvironmentPostProcessor`, `GatewayEnvironmentPostProcessor`, adds a single
property source setting `spring.webflux.hiddenmethod.filter.enabled=false` — it migrates
nothing. Spec §7b admits a second prefix "only if CP-29 shows 5.0.0 binds it"; it does not,
so the catalog declares the 5.0.0 prefix alone and states the boundary (a module carrying
another artifact that binds the old prefix is not read).

**Q3 — the shortcut grammar (F7, §7b).** `PredicateDefinition(String)` splits on the FIRST
`=` (`bipush 61`, `indexOf`; none → `ValidationException`), the part before it is the name
(`setName`), the part after is tokenised on `,` (`StringUtils.tokenizeToStringArray`), and
each token is put under `NameUtils.generateName(i)` — `_genkey_` + the index
(`GENERATED_NAME_PREFIX = "_genkey_"`). `PredicateDefinition` carries `name` and
`Map<String, String> args`, which is what the map form (`name:` + `args:`) binds directly.
So `Path=/a/**,/b/**` is `{name: Path, args: {_genkey_0: /a/**, _genkey_1: /b/**}}`, and
the engine reads both spellings into that one shape.

**Q4 — `RouteDefinition` (F7).** Fields `id`, `predicates`, `filters`, `uri` (a
`java.net.URI`), `metadata`, `order`, `enabled` — F7 listed six; `enabled` is the seventh.
`RouteDefinition(String)` is the one-line form `id=uri,pred,pred`: split on the first `=`,
`setId`, tokenise on `,`, the first token to `URI.create` → `setUri`, the rest each to
`new PredicateDefinition(String)`. The YAML list form the catalog reads never goes through
this constructor (the binder sets the fields), so the engine does not parse it; recorded as
the grammar's other spelling.

**Q5 — the five factories.** `Path`: `shortcutFieldOrder [patterns, matchTrailingSlash]`,
`shortcutType GATHER_LIST_TAIL_FLAG`, `Config {List<String> patterns, boolean
matchTrailingSlash}` — every positional argument is a pattern EXCEPT a trailing
`true`/`false`, which is the flag (Q7). `Method`: `[methods]`, `GATHER_LIST`, `Config
{HttpMethod[] methods}` — every positional argument is a verb. `Header`: `[header, regexp]`;
`Query`: `[param, regexp, predicate]`; `Cookie`: `[name, regexp]` — all three inherit the
interface's `DEFAULT` shortcut type, so `_genkey_0` is the name and `_genkey_1` the regexp
(Q7). The catalog's `args:` lists are exactly these orders; the map form's keys are the
same names.

**Q6 — fifteen predicate factories; the pass-through list is missing one.** The name the
framework registers a factory under is its simple class name with `RoutePredicateFactory`
removed (`normalizeRoutePredicateName`: `Class.getSimpleName`, `replace`, `removeGarbage`),
so the 5.0.0 names are `After Before Between CloudFoundryRouteService Cookie Header Host
Method Path Query ReadBody RemoteAddr Version Weight XForwardedRemoteAddr`. Spec §7b's
pass-through list names nine of the ten that are neither `Path`/`Method` nor a requirement;
`Version` (an API-version predicate, new at this line) is not on it. The catalog declares
the list as the spec wrote it, so a route carrying `Version=…` derives its rows
`unresolved` (an unknown name) rather than a resolved row nobody measured — stated on the
catalog, and a one-word amendment once the spec admits it.

**Q7 — the three normalisers.** `DEFAULT` maps each `_genkey_N` key to
`shortcutFieldOrder().get(N)` (`normalizeKey`: `startsWith "_genkey_"`, then the field
list) and keeps any other key as written; `GATHER_LIST` requires ONE field and puts every
value, in order, into a list under it; `GATHER_LIST_TAIL_FLAG` requires TWO fields, and when
the LAST value `equalsIgnoreCase` `true` or `false` it goes under the second field and the
`subList` before it under the first — otherwise every value is the list. So the engine's
`Path` rule drops a trailing boolean token (`tail_flag: matchTrailingSlash` on the catalog)
and reads the rest as patterns, one row each.

**Q8 — the `uri` scheme.** `ReactiveLoadBalancerClientFilter.filter` tests
`uri.getScheme().equals("lb")` (twice — the route URI and the scheme-prefix attribute) and
then reads `getHost()` as the service id; `RouteToRequestUrlFilter` rewrites the request
URL from the route URI's scheme and authority for any scheme matching
`[a-zA-Z]([a-zA-Z]|\d|\+|\.|-)*:.*`. So `lb://orders` names the service `orders` and
`http://items.internal:8080` names the host `items.internal`. **What the catalog publishes
is nonetheless the URI verbatim, with `peer` NULL** — the shape the DSL sibling
`spring-cloud-gateway-outbound.yml` publishes for `uri("lb://orders-service")` and
`tests/e2e/test_rest_outbound_delivered.py::test_gateway_targets_derive_outbound` pins
(D02: a routing destination is kept whole, never split into a peer and an empty path).
Spec §7b's parenthetical "`lb://orders` → peer `orders`" describes what the scheme MEANS,
which this row records; the row shape follows the shipped sibling, per the controller's
ruling to mirror it exactly.

**Q9 — `HttpMethod` at spring-web 6.1.6 (F9).** `values()` is `GET HEAD POST PUT PATCH
DELETE OPTIONS TRACE`, from the static initialiser's `ldc` sequence — recorded as §0b A1's
reason for NOT fanning a verb-less route out: `resources(…)` routes are verb-less too and
serve three of these. `valueOf(String)` has eight `equals` arms for those exact spellings
and otherwise constructs a `new HttpMethod(name)`; `MethodRoutePredicateFactory$1`'s test
is `if_acmpne` — reference identity against the configured constants. A `Method=get` route
therefore binds a `HttpMethod("get")` that is never `==` the request's `GET` and never
matches; the engine publishes the verb exactly as written, as the DSL catalog does for
`method("get")` — a spelling the framework never matches, never a `GET` the route does not
declare.

**Q10 — the media overloads (§7a).** On all three DSL classes `accept` and `contentType`
each have exactly two overloads: the vararg factory `(MediaType[])RequestPredicate` the
`media:` rules read, and a `(MediaType, Function)V` route declaration — `Function1` on the
two `RouterFunctionDsl`s, `Function2` (a suspend lambda) on `CoRouterFunctionDsl`. The
declaring form is arity 2 with the media at 0 and the handler at 1, which is the verb rule
`{ method: accept, arity: 2, media_arg: 0, fills: produces, handler_arg: 1, verb: null }`
(`contentType` with `fills: consumes`); the vararg form is arity 1, so `arity` alone tells
the two apart and the media rule keeps reading the factory.
