# CP-25 — binder rules: Javalin's `ApiBuilder` guard, what six frameworks' parameter binders enforce, and what the handler-body reads and mapping expressions of §5c/§5d state

**Question.** Two questions share this harness because they read the same kind of
evidence — one class file's instructions — off jars of the same families.

*Row 1.* Spec 2026-09-19 §4a lets `javalin-apibuilder.yml` declare `follow_calls:
all` on the `apiBuilder` entry and the `path` prefix — an origin-less body whose
module-local helper calls the combinator follows — on the argument that `ApiBuilder`'s
static verbs register on a THREAD-LOCAL instance the builder refuses to hand out when no
block is open, so a helper that reaches a verb can only ever have been called from inside
one. Row 1 records that argument off the jar: what `ApiBuilder.staticInstance()` reads,
what it throws when the thread-local is empty (the exception class and the message
literal), and a verb's first instruction showing every static verb goes through it.

*Rows 2–12.* Spec §5b writes a `requirement` column on every parameter annotation an
inbound handler carries — `required` where the framework rejects a request without the
value, `optional` where it serves the request without it — and §5a forbids either word
where the framework does not decide. So each catalog's `request_params` rule has to be
the framework's OWN predicate, read off its binder: Spring's
`AbstractNamedValueMethodArgumentResolver` (F6) and what `MethodParameter.isOptional()`
asks; Micronaut's route match and what `Argument.isNullable()`/`isOptional()` read (F8);
RESTEasy Reactive's extractors and `ParameterHandler` (F9, A9); quarkus-reactive-routes'
generated read. Row 4 is A4 for §5c — `HeadersRequestCondition` dropping `Accept` and
`Content-Type`. Row 5 is the one cell that COMPILES something: whether Spring's
`defaultValue` reaches the class file when the author did not write it, which decides
whether "`default_attr` present in `args`" is a sound test. Row 8 is the set of
`@Nullable` spellings Micronaut honours, which the shape model's `nullability.nullable`
list has to cover for the binder rule to read them.

*Rows 13–17.* Spec §5c reads Spring's `@RequestMapping(params=, headers=)` expressions as
requirements and §5d reads what a handler BODY reads off the request, `requirement` only
where the API itself refuses the request (A3). Row 13 is the grammar of a `params`/
`headers` expression, read off `AbstractNameValueExpression`'s constructor — the four
forms `name`, `name=v`, `!name`, `name!=v` the mapping reader has to parse the same way.
Row 14 is F7 measured: Javalin's `Context` declares `header(String)` as a READ and
`header(String, String)` as a response SET, `cookie` likewise by arity, so a
`request_reads` entry that named the method alone would record every response header the
handler sets as a request requirement. Row 15 is what `Validator.get()` does with an
absent value — the one Javalin read that is `required`. Rows 16–17 are the Servlet API's
`getParameter`/`getHeader`: abstract on the interface, so the API states nothing, and
null-on-absent in the container that implements them, under both package spellings.

*Row 18* (added 2026-09-20 at the whole-branch review, back in §5b). A `request_params` row
names the parameter's OWN name when the annotation writes none — and that is a claim
about what the framework requires by that name. Micronaut's binders take the written
`value` (`@Header`: `value`, then `name`), else the parameter's name, and hand it to
`AbstractArgumentBinder.doBind`; row 18 reads what `doResolve` does when that name finds
nothing — it retries with `getFallbackFormat(argument)` — and what the two spellings of
that fallback are: `NameUtils.hyphenate(name)` on the base class (`@QueryValue`,
`@CookieValue`) and `hyphenate(capitalize(name), false)` on the header binder's override.
The cell quotes `hyphenate`'s two paths, `isHyphenatedLowerCase`'s regex, `capitalize`'s
early return, the `Character` predicates of both `separateCamelCase` loops, and the
comparator behind the framework's own `CaseInsensitiveMutableHttpHeaders` — the rule
`micronaut-http.yml`'s `fallback_spelling` mirrors in `request_requirements.py`.

**What this probe does not settle.** Nothing framework-side was run; every cell but row 5
is a `javap` read of a class file, and row 5 reads the class file `javac` produced from a
six-line sample. Row 1 shows the guard and that ONE verb (`get(String, Handler)`) opens by
calling it; the other twenty-three verb overloads were read by hand for the catalog
comment (each opens with `invokestatic staticInstance`) and are not in the table. Row 3
reads `hasNullableAnnotation()`'s loop over `getParameterAnnotations()` — DECLARATION
annotations; a TYPE_USE-only `@Nullable` (JSpecify's is) lands in
`RuntimeVisibleTypeAnnotations` and this method never sees it at 6.1.6, so a parameter
carrying only that spelling is `required` to Spring and the shape model listing it does
not make it optional there — stated, not measured on a compiled sample. Row 7 is the
route match's decision; how a Kotlin nullable type reaches `isNullable()` under KSP
rather than kapt is the processor's business and is not read here (row 8 shows kapt's
path: the `org.jetbrains.annotations.Nullable` kotlinc emits maps to the stereotype).
Row 10 shows RESTEasy Reactive storing a null with no throw and substituting only a
`@DefaultValue`; a `@NotNull` bean-validation constraint on the same parameter would
reject the request later, which is Hibernate Validator's rule and not the binder's. Row
12 reads what the deployment GENERATES (`Methods.REQUEST_GET_PARAM` is the descriptor
the generated handler invokes) and Vert.x's declared return nullability; the generated
class itself is not compiled here. Row 13 reads the constructor and not
`ParamsRequestCondition`'s match: that `name!=v` is served when the parameter is ABSENT
(`matchValue` false, negated → match) is read off `AbstractNameValueExpression.match` by
hand for the catalog comment and is not a cell. Rows 16–17 measure Tomcat, the container
CP-9 measured; another container's `getParameter` is its own implementation of the same
abstract method; that every container answers alike rests on the API's own documented
contract for `getParameter` and `getHeader` — null when the request carries no such name
— which the class file does not carry and this probe states rather than measures. Row
18 quotes `separateCamelCase`'s branch predicates, not its whole 355-byte body; the Python
mirror (`request_requirements.py::_separate_camel_case`) was written from the full `javap
-c` listing and checked against the real `NameUtils` on fourteen names (`xTenant` →
`x-tenant` / `x-Tenant`, `pageSize` → `page-size` / `Page-Size`, `contentType` →
`Content-Type`, `apiKEY` → `api-key` / `Api-KEY`, `HTTPClient` → `httpclient`, …) in a
scratch `java -cp micronaut-core-4.7.6.jar` run outside this harness — every cell here is
still a `javap` read. Row 18 reads Micronaut's own header map; the Netty-backed headers a
running server hands the binder are `micronaut-http-netty`'s and are not read here — that
HTTP header names compare case-insensitively is the protocol's rule (RFC 9110 §5.1), and the
row shows the framework honouring it in the one implementation it ships in this jar.

**Version scope (§5.4).** Sixteen archives, each filed under the `Implementation-Version`
its own `META-INF/MANIFEST.MF` reports, read as: `io.javalin:javalin` **6.4.0**;
`org.springframework:spring-web`, `spring-core` and `spring-webmvc` **6.1.6**;
`io.micronaut:micronaut-http`, `micronaut-core`, `micronaut-router` and
`micronaut-core-processor` **4.7.6**; `io.quarkus.resteasy.reactive:resteasy-reactive`
and `resteasy-reactive-common`, `io.quarkus:quarkus-reactive-routes` and
`quarkus-reactive-routes-deployment` **3.17.5**; `io.vertx:vertx-core` **4.5.11** (the
Vert.x the Quarkus 3.17.5 BOM pins); `jakarta.ws.rs:jakarta.ws.rs-api` **3.1.0**;
`org.apache.tomcat.embed:tomcat-embed-core` **10.1.50** (the `jakarta.servlet` API and
its container) and **9.0.121** (the `javax.servlet` spelling) — the two CP-9 measured. The
harness aborts when any archive reports a version other than the one the run expected.
Every verdict below is bounded by those archives.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp25_binder_rules/run.sh`. It resolves the jars into `~/.m2` (Maven and
network on the first run only), then runs `probe.py`, which reads each jar's
`Implementation-Version` off its manifest before it measures anything and prints the
table below. Needs a JDK for `javac` and `javap`. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version each jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's artifact list asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column.

```
| what the run read | 10.1.50 | 3.1.0 | 3.17.5 | 4.5.11 | 4.7.6 | 6.1.6 | 6.4.0 | 9.0.121 |
|---|---|---|---|---|---|---|---|---|
| artifacts reporting this version | org.apache.tomcat.embed:tomcat-embed-core | jakarta.ws.rs:jakarta.ws.rs-api | io.quarkus.resteasy.reactive:resteasy-reactive, io.quarkus.resteasy.reactive:resteasy-reactive-common, io.quarkus:quarkus-reactive-routes, io.quarkus:quarkus-reactive-routes-deployment | io.vertx:vertx-core | io.micronaut:micronaut-core, io.micronaut:micronaut-core-processor, io.micronaut:micronaut-http, io.micronaut:micronaut-router | org.springframework:spring-core, org.springframework:spring-web, org.springframework:spring-webmvc | io.javalin:javalin | org.apache.tomcat.embed:tomcat-embed-core |
| identity read from the archive itself (`Implementation-Version`) | yes | yes | yes | yes | yes | yes | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | ApiBuilder.staticInstance(): the thread-local field, what it throws with no block open, and a verb's first instruction | `io.javalin:javalin` | 6.4.0 | `field: private static final java.lang.ThreadLocal<io.javalin.router.JavalinDefaultRoutingApi<?>> staticJavalin; ; staticInstance(): getstatic Field staticJavalin:Ljava/lang/ThreadLocal; ; invokevirtual Method java/lang/ThreadLocal.get:()Ljava/lang/Object; ; checkcast class io/javalin/router/JavalinDefaultRoutingApi ; astore_0 ; aload_0 ; ifnonnull ; new class java/lang/IllegalStateException ; dup ; ldc String The static API can only be used within a routes() call. ; invokespecial Method java/lang/IllegalStateException."<init>":(Ljava/lang/String;)V ; athrow ; aload_0 ; areturn ; get(String, Handler) opens with: invokestatic Method staticInstance:()Lio/javalin/router/JavalinDefaultRoutingApi;` |
| 2 | AbstractNamedValueMethodArgumentResolver.resolveArgument: the null-value branch, DEFAULT_NONE, RequestParam's attributes | `org.springframework:spring-web` | 6.1.6 | `resolveArgument null-value branch (offsets 92-147): aload ; ifnonnull ; aload ; getfield Field org/springframework/web/method/annotation/AbstractNamedValueMethodArgumentResolver$NamedValueInfo.defaultValue:Ljava/lang/String; ; ifnull ; aload_0 ; aload ; getfield Field org/springframework/web/method/annotation/AbstractNamedValueMethodArgumentResolver$NamedValueInfo.defaultValue:Ljava/lang/String; ; invokevirtual Method resolveEmbeddedValuesAndExpressions:(Ljava/lang/String;)Ljava/lang/Object; ; astore ; goto ; aload ; getfield Field org/springframework/web/method/annotation/AbstractNamedValueMethodArgumentResolver$NamedValueInfo.required:Z ; ifeq ; aload ; invokevirtual Method org/springframework/core/MethodParameter.isOptional:()Z ; ifne ; aload_0 ; aload ; getfield Field org/springframework/web/method/annotation/AbstractNamedValueMethodArgumentResolver$NamedValueInfo.name:Ljava/lang/String; ; aload ; aload_3 ; invokevirtual Method handleMissingValue:(Ljava/lang/String;Lorg/springframework/core/MethodParameter;Lorg/springframework/web/context/request/NativeWebRequest;)V ; iload ; updateNamedValueInfo: defaultValue equal to ValueConstants.DEFAULT_NONE (javap: \n\t\t\n\t\t\n\n\t\t\t\t\n) becomes null ; RequestParam attributes: java.lang.String value, java.lang.String name, boolean required, java.lang.String defaultValue` |
| 3 | MethodParameter.isOptional(): Optional type, an annotation whose simple name is Nullable, the Kotlin delegate | `org.springframework:spring-core` | 6.1.6 | `isOptional(): aload_0 ; invokevirtual Method getParameterType:()Ljava/lang/Class; ; ldc class java/util/Optional ; if_acmpeq ; aload_0 ; invokevirtual Method hasNullableAnnotation:()Z ; ifne ; invokestatic Method org/springframework/core/KotlinDetector.isKotlinReflectPresent:()Z ; ifeq ; aload_0 ; invokevirtual Method getContainingClass:()Ljava/lang/Class; ; invokestatic Method org/springframework/core/KotlinDetector.isKotlinType:(Ljava/lang/Class;)Z ; ifeq ; aload_0 ; invokestatic Method org/springframework/core/MethodParameter$KotlinDelegate.isOptional:(Lorg/springframework/core/MethodParameter;)Z ; ifeq ; iconst_1 ; goto ; iconst_0 ; ireturn ; hasNullableAnnotation(): invokevirtual Method getParameterAnnotations:()[Ljava/lang/annotation/Annotation; ; ldc String Nullable ; invokevirtual Method java/lang/Class.getSimpleName:()Ljava/lang/String; ; KotlinDelegate.isOptional(): invokeinterface InterfaceMethod kotlin/reflect/KType.isMarkedNullable:()Z ; invokeinterface InterfaceMethod kotlin/reflect/KType.isMarkedNullable:()Z ; invokeinterface InterfaceMethod kotlin/reflect/KParameter.isOptional:()Z` |
| 4 | HeadersRequestCondition.parseExpressions: the two header names it drops (A4) | `org.springframework:spring-webmvc` | 6.1.6 | `new class org/springframework/web/servlet/mvc/condition/HeadersRequestCondition$HeaderExpression ; invokespecial Method org/springframework/web/servlet/mvc/condition/HeadersRequestCondition$HeaderExpression."<init>":(Ljava/lang/String;)V ; ldc String Accept ; getfield Field org/springframework/web/servlet/mvc/condition/HeadersRequestCondition$HeaderExpression.name:Ljava/lang/String; ; invokevirtual Method java/lang/String.equalsIgnoreCase:(Ljava/lang/String;)Z ; ldc String Content-Type ; getfield Field org/springframework/web/servlet/mvc/condition/HeadersRequestCondition$HeaderExpression.name:Ljava/lang/String; ; invokevirtual Method java/lang/String.equalsIgnoreCase:(Ljava/lang/String;)Z` |
| 5 | javac against spring-web, javap -v: RequestParam's element_value_pairs with and without a written defaultValue | `org.springframework:spring-web` | 6.1.6 | `written: #14(#15=s#16) ; unwritten: #14()` |
| 6 | @QueryValue/@Header/@CookieValue attributes (F8) | `io.micronaut:micronaut-http` | 4.7.6 | `@QueryValue: java.lang.String value, java.lang.String defaultValue ; @Header: java.lang.String value, java.lang.String name, java.lang.String defaultValue ; @CookieValue: java.lang.String value, java.lang.String defaultValue` |
| 7 | AbstractRouteMatch.setBindingResultOfFail: nullable → null, Optional → empty, else UnsatisfiedRouteException; what isNullable/isOptional read | `io.micronaut:micronaut-router`, `io.micronaut:micronaut-core` | 4.7.6 | `AbstractRouteMatch.setBindingResultOfFail: invokeinterface InterfaceMethod io/micronaut/core/type/Argument.isNullable:()Z ; aconst_null ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.isOptional:()Z ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; invokestatic Method io/micronaut/web/router/exceptions/UnsatisfiedRouteException.create:(Lio/micronaut/core/type/Argument;)Lio/micronaut/web/router/exceptions/UnsatisfiedRouteException; ; athrow ; AnnotatedElement.isNullable(): ldc String jakarta.annotation.Nullable ; invokeinterface InterfaceMethod io/micronaut/core/annotation/AnnotationMetadata.hasStereotype:(Ljava/lang/String;)Z ; TypeInformation.isOptional(): ldc class java/util/Optional` |
| 8 | The annotation spellings Micronaut's processor maps onto the jakarta.annotation.Nullable stereotype | `io.micronaut:micronaut-core-processor` | 4.7.6 | `CoreNullableTransformer: io.micronaut.core.annotation.Nullable -> jakarta.annotation.Nullable ; JavaxNullableTransformer: javax.annotation.Nullable -> jakarta.annotation.Nullable ; KotlinNullableMapper: org.jetbrains.annotations.Nullable -> jakarta.annotation.Nullable ; JspecifyNullableTransformer: org.jspecify.annotations.Nullable -> jakarta.annotation.Nullable ; SpotbugsNullableTransformer: edu.umd.cs.findbugs.annotations.Nullable -> jakarta.annotation.Nullable ; AndroidxNullableTransformer: androidx.annotation.Nullable -> jakarta.annotation.Nullable ; JdtNullableTransformer: org.eclipse.jdt.annotation.Nullable -> jakarta.annotation.Nullable ; ReactorNullableTransformer: reactor.util.annotation.Nullable -> jakarta.annotation.Nullable ; ReactivexNullableTransformer: io.reactivex.annotations.Nullable -> jakarta.annotation.Nullable ; Rxjava3NullableTransformer: io.reactivex.rxjava3.annotations.Nullable -> jakarta.annotation.Nullable` |
| 9 | @QueryParam/@HeaderParam/@CookieParam/@DefaultValue and @RestQuery/@RestHeader/@RestCookie attributes (F9, A9) | `jakarta.ws.rs:jakarta.ws.rs-api`, `io.quarkus.resteasy.reactive:resteasy-reactive-common` | 3.1.0, 3.17.5 | `@QueryParam: java.lang.String value ; @HeaderParam: java.lang.String value ; @CookieParam: java.lang.String value ; @DefaultValue: java.lang.String value ; @RestQuery: java.lang.String value ; @RestHeader: java.lang.String value ; @RestCookie: java.lang.String value` |
| 10 | RESTEasy Reactive extractors hand the request's read through; ParameterHandler.handleResult substitutes only a defaultValue | `io.quarkus.resteasy.reactive:resteasy-reactive` | 3.17.5 | `QueryParamExtractor.extractParameter: invokevirtual Method org/jboss/resteasy/reactive/server/core/ResteasyReactiveRequestContext.getQueryParameter:(Ljava/lang/String;ZZLjava/lang/String;)Ljava/lang/Object; ; areturn ; HeaderParamExtractor.extractParameter: invokevirtual Method org/jboss/resteasy/reactive/server/core/ResteasyReactiveRequestContext.getHeader:(Ljava/lang/String;Z)Ljava/lang/Object; ; areturn ; CookieParamExtractor.extractParameter: areturn ; invokevirtual Method org/jboss/resteasy/reactive/server/core/ResteasyReactiveRequestContext.getCookieParameter:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; getQueryParameter single-valued path: invokeinterface InterfaceMethod org/jboss/resteasy/reactive/server/spi/ServerHttpRequest.getQueryParam:(Ljava/lang/String;)Ljava/lang/String; ; ifnull ; areturn ; ParameterHandler.handleResult (offsets 0-35): aload_0 ; getfield Field defaultValue:Ljava/lang/String; ; ifnull ; aload_1 ; ifnull ; aload_0 ; getfield Field isCollection:Z ; ifeq ; aload_1 ; checkcast class java/util/Collection ; invokeinterface InterfaceMethod java/util/Collection.isEmpty:()Z ; ifeq ; aload_0 ; getfield Field defaultValue:Ljava/lang/String; ; astore_1 ; aconst_null` |
| 11 | @Param/@Header attributes | `io.quarkus:quarkus-reactive-routes` | 3.17.5 | `@Param: java.lang.String value ; @Header: java.lang.String value` |
| 12 | The read the deployment generates for @Param/@Header, and Vert.x's declared return nullability | `io.quarkus:quarkus-reactive-routes-deployment`, `io.vertx:vertx-core` | 3.17.5, 4.5.11 | `Methods.REQUEST_GET_PARAM = ofMethod(owner io/vertx/core/http/HttpServerRequest, name getParam, returns java/lang/String, params java/lang/String) ; Methods.REQUEST_GET_HEADER = ofMethod(owner io/vertx/core/http/HttpServerRequest, name getHeader, returns java/lang/String, params java/lang/String) ; Methods.OPTIONAL_OF_NULLABLE = ofMethod(owner java/util/Optional, name ofNullable, returns java/util/Optional, params java/lang/Object) ; ParamAndHeaderProvider wraps an Optional parameter: getstatic Field io/quarkus/arc/processor/DotNames.OPTIONAL:Lorg/jboss/jandex/DotName; ; getstatic Field io/quarkus/vertx/web/deployment/Methods.OPTIONAL_OF_NULLABLE:Lio/quarkus/gizmo/MethodDescriptor; ; HttpServerRequest.getParam(String) return: @io.vertx.codegen.annotations.Nullable ; HttpServerRequest.getHeader(String) return: @io.vertx.codegen.annotations.Nullable` |
| 13 | AbstractNameValueExpression(String): where a params/headers expression's `=` and `!` are read (§5c) | `org.springframework:spring-webmvc` | 6.1.6 | `bipush ; invokevirtual Method java/lang/String.indexOf:(I)I ; if_icmpne ; ldc String ! ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; putfield Field isNegated:Z ; ifeq ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; putfield Field name:Ljava/lang/String; ; putfield Field value:Ljava/lang/Object; ; ifle ; invokevirtual Method java/lang/String.charAt:(I)C ; bipush ; if_icmpne ; putfield Field isNegated:Z ; ifeq ; invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; putfield Field name:Ljava/lang/String; ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; putfield Field value:Ljava/lang/Object;` |
| 14 | Context.queryParam/header/cookie by arity: the one-argument reads, the two- and three-argument sets, the AsClass validators (F7) | `io.javalin:javalin` | 6.4.0 | `queryParam/1: invokeinterface InterfaceMethod queryParams:(Ljava/lang/String;)Ljava/util/List; ; invokestatic Method kotlin/collections/CollectionsKt.firstOrNull:(Ljava/util/List;)Ljava/lang/Object; ; header/1: invokeinterface InterfaceMethod req:()Ljakarta/servlet/http/HttpServletRequest; ; invokeinterface InterfaceMethod jakarta/servlet/http/HttpServletRequest.getHeader:(Ljava/lang/String;)Ljava/lang/String; ; cookie/1: invokeinterface InterfaceMethod req:()Ljakarta/servlet/http/HttpServletRequest; ; invokestatic Method io/javalin/http/CookieKt.getCookie:(Ljakarta/servlet/http/HttpServletRequest;Ljava/lang/String;)Ljava/lang/String; ; header/2: invokeinterface InterfaceMethod res:()Ljakarta/servlet/http/HttpServletResponse; ; invokeinterface InterfaceMethod jakarta/servlet/http/HttpServletResponse.setHeader:(Ljava/lang/String;Ljava/lang/String;)V ; cookie/3: invokespecial Method io/javalin/http/Cookie."<init>":(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;IZIZLjava/lang/String;Ljava/lang/String;Lio/javalin/http/SameSite;ILkotlin/jvm/internal/DefaultConstructorMarker;)V ; invokeinterface InterfaceMethod cookie:(Lio/javalin/http/Cookie;)Lio/javalin/http/Context; ; queryParamAsClass/2: invokeinterface InterfaceMethod queryParam:(Ljava/lang/String;)Ljava/lang/String; ; invokevirtual Method io/javalin/validation/Validation.validator:(Ljava/lang/String;Ljava/lang/Class;Ljava/lang/String;)Lio/javalin/validation/Validator; ; headerAsClass/2: invokeinterface InterfaceMethod header:(Ljava/lang/String;)Ljava/lang/String; ; invokevirtual Method io/javalin/validation/Validation.validator:(Ljava/lang/String;Ljava/lang/Class;Ljava/lang/String;)Lio/javalin/validation/Validator;` |
| 15 | Validator.get(): getOrThrow with a ValidationException function; NULLCHECK_FAILED on a null typed value outside NullableValidator (A3) | `io.javalin:javalin` | 6.4.0 | `Validator.get(): invokespecial Method io/javalin/validation/BaseValidator.get:()Ljava/lang/Object; ; invokestatic Method kotlin/jvm/internal/Intrinsics.checkNotNull:(Ljava/lang/Object;)V ; BaseValidator.get(): invokevirtual Method getOrThrow:(Lkotlin/jvm/functions/Function1;)Ljava/lang/Object; ; get$1.invoke: new class io/javalin/validation/ValidationException ; errors$2.invoke (offsets 229-259): invokevirtual Method io/javalin/validation/BaseValidator.getTypedValue$javalin:()Ljava/lang/Object; ; ifnonnull ; instanceof class io/javalin/validation/NullableValidator ; ifne ; ldc String NULLCHECK_FAILED` |
| 16 | jakarta.servlet getParameter/getHeader: abstract on the API; Tomcat's connector returns null for an absent name | `org.apache.tomcat.embed:tomcat-embed-core` | 10.1.50 | `declared: public abstract java.lang.String getParameter(java.lang.String); ; public abstract java.lang.String getHeader(java.lang.String); ; connector.Request.getParameter: invokevirtual Method org/apache/tomcat/util/http/Parameters.getParameter:(Ljava/lang/String;)Ljava/lang/String; ; Parameters.getParameter tail: ifnull ; areturn ; areturn ; aconst_null ; areturn ; connector.Request.getHeader: invokevirtual Method org/apache/coyote/Request.getHeader:(Ljava/lang/String;)Ljava/lang/String; ; MimeHeaders.getHeader tail: ifnull ; aconst_null ; areturn` |
| 17 | javax.servlet getParameter/getHeader: the same, under the other package spelling | `org.apache.tomcat.embed:tomcat-embed-core` | 9.0.121 | `declared: public abstract java.lang.String getParameter(java.lang.String); ; public abstract java.lang.String getHeader(java.lang.String); ; connector.Request.getParameter: invokevirtual Method org/apache/tomcat/util/http/Parameters.getParameter:(Ljava/lang/String;)Ljava/lang/String; ; Parameters.getParameter tail: ifnull ; areturn ; areturn ; aconst_null ; areturn ; connector.Request.getHeader: invokevirtual Method org/apache/coyote/Request.getHeader:(Ljava/lang/String;)Ljava/lang/String; ; MimeHeaders.getHeader tail: ifnull ; aconst_null ; areturn` |
| 18 | Micronaut's unwritten-name fallback: AbstractArgumentBinder.doResolve retries getFallbackFormat — NameUtils.hyphenate, the header binder's capitalize — and header names compare case-insensitively (§5b, fallback_spelling) | `io.micronaut:micronaut-core`, `io.micronaut:micronaut-http` | 4.7.6 | `AbstractArgumentBinder.doResolve: invokevirtual Method resolveValue:(Lio/micronaut/core/convert/ArgumentConversionContext;Lio/micronaut/core/convert/value/ConvertibleValues;Ljava/lang/String;)Ljava/lang/Object; ; ifnonnull ; invokevirtual Method getFallbackFormat:(Lio/micronaut/core/type/Argument;)Ljava/lang/String; ; invokevirtual Method java/lang/String.equals:(Ljava/lang/Object;)Z ; ifne ; invokevirtual Method resolveValue:(Lio/micronaut/core/convert/ArgumentConversionContext;Lio/micronaut/core/convert/value/ConvertibleValues;Ljava/lang/String;)Ljava/lang/Object; ; AbstractArgumentBinder.getFallbackFormat: aload_1 ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.getName:()Ljava/lang/String; ; invokestatic Method io/micronaut/core/naming/NameUtils.hyphenate:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; HeaderAnnotationBinder.bind names by: invokeinterface InterfaceMethod io/micronaut/core/annotation/AnnotationMetadata.stringValue:(Ljava/lang/Class;)Ljava/util/Optional; ; invokevirtual Method java/util/Optional.orElseGet:(Ljava/util/function/Supplier;)Ljava/lang/Object; ; invokevirtual Method doBind:(Lio/micronaut/core/convert/ArgumentConversionContext;Lio/micronaut/core/convert/value/ConvertibleValues;Ljava/lang/String;)Lio/micronaut/core/bind/ArgumentBinder$BindingResult; ; lambda$bind$0: ldc String name ; invokeinterface InterfaceMethod io/micronaut/core/annotation/AnnotationMetadata.stringValue:(Ljava/lang/Class;Ljava/lang/String;)Ljava/util/Optional; ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.getName:()Ljava/lang/String; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; HeaderAnnotationBinder.getFallbackFormat: aload_1 ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.getName:()Ljava/lang/String; ; invokestatic Method io/micronaut/core/naming/NameUtils.capitalize:(Ljava/lang/String;)Ljava/lang/String; ; iconst_0 ; invokestatic Method io/micronaut/core/naming/NameUtils.hyphenate:(Ljava/lang/String;Z)Ljava/lang/String; ; areturn ; QueryValueArgumentBinder.bind names by: invokeinterface InterfaceMethod io/micronaut/core/annotation/AnnotationMetadata.stringValue:(Ljava/lang/Class;)Ljava/util/Optional; ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.getName:()Ljava/lang/String; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; invokevirtual Method doBind:(Lio/micronaut/core/convert/ArgumentConversionContext;Lio/micronaut/core/convert/value/ConvertibleValues;Ljava/lang/String;Lio/micronaut/core/bind/ArgumentBinder$BindingResult;)Lio/micronaut/core/bind/ArgumentBinder$BindingResult; ; getFallbackFormat: not overridden (AbstractArgumentBinder's) ; CookieAnnotationBinder.bind names by: invokeinterface InterfaceMethod io/micronaut/core/annotation/AnnotationMetadata.stringValue:(Ljava/lang/Class;)Ljava/util/Optional; ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.getName:()Ljava/lang/String; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; invokevirtual Method doBind:(Lio/micronaut/core/convert/ArgumentConversionContext;Lio/micronaut/core/convert/value/ConvertibleValues;Ljava/lang/String;)Lio/micronaut/core/bind/ArgumentBinder$BindingResult; ; getFallbackFormat: aload_1 ; invokeinterface InterfaceMethod io/micronaut/core/type/Argument.getName:()Ljava/lang/String; ; invokestatic Method io/micronaut/core/naming/NameUtils.hyphenate:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; NameUtils.hyphenate(String): aload_0 ; iconst_1 ; invokestatic Method hyphenate:(Ljava/lang/String;Z)Ljava/lang/String; ; areturn ; NameUtils.hyphenate(String, boolean): invokestatic Method isHyphenatedLowerCase:(Ljava/lang/String;)Z ; ifeq ; invokevirtual Method java/util/regex/Pattern.matcher:(Ljava/lang/CharSequence;)Ljava/util/regex/Matcher; ; ldc String - ; invokevirtual Method java/util/regex/Matcher.replaceAll:(Ljava/lang/String;)Ljava/lang/String; ; bipush ; invokevirtual Method java/util/regex/Pattern.matcher:(Ljava/lang/CharSequence;)Ljava/util/regex/Matcher; ; ldc String - ; invokevirtual Method java/util/regex/Matcher.replaceAll:(Ljava/lang/String;)Ljava/lang/String; ; invokestatic Method separateCamelCase:(Ljava/lang/String;ZC)Ljava/lang/String; ; NameUtils.isHyphenatedLowerCase: invokestatic Method io/micronaut/core/util/StringUtils.isNotEmpty:(Ljava/lang/CharSequence;)Z ; invokevirtual Method java/util/regex/Pattern.matcher:(Ljava/lang/CharSequence;)Ljava/util/regex/Matcher; ; invokevirtual Method java/util/regex/Matcher.matches:()Z ; invokevirtual Method java/lang/String.charAt:(I)C ; invokestatic Method java/lang/Character.isLetter:(C)Z ; NameUtils patterns (static init, in order): \\.[A-Z\\$] | [\\p{javaLowerCase}\\d-]+ | ^[\\p{Lu}_{0-9}]+ | ^(([a-z0-9])+([-.:])?)*([a-z0-9])+$ | [_ ] ; NameUtils.capitalize: iconst_1 ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; iconst_0 ; invokevirtual Method java/lang/String.charAt:(I)C ; invokestatic Method java/lang/Character.isLowerCase:(C)Z ; ifeq ; invokevirtual Method java/lang/String.isEmpty:()Z ; ifne ; iconst_0 ; invokevirtual Method java/lang/String.charAt:(I)C ; invokestatic Method java/lang/Character.isUpperCase:(C)Z ; ifeq ; areturn ; iconst_0 ; iconst_1 ; invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; invokevirtual Method java/lang/String.toUpperCase:(Ljava/util/Locale;)Ljava/lang/String; ; invokedynamic InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String; ; areturn ; separateCamelCase lowerCase=false loop (offsets 47-144): ifeq ; if_icmpeq ; invokestatic Method java/lang/Character.isUpperCase:(C)Z ; ifeq ; invokestatic Method java/lang/Character.isUpperCase:(C)Z ; ifne ; if_icmpeq ; bipush ; if_icmpne ; if_icmpeq ; if_icmpne ; separateCamelCase lowerCase=true loop (offsets 191-330): invokestatic Method java/lang/Character.isLowerCase:(C)Z ; ifne ; invokestatic Method java/lang/Character.isLetter:(C)Z ; ifne ; if_icmpeq ; if_icmpne ; invokestatic Method java/lang/Character.toLowerCase:(C)C ; ifeq ; invokestatic Method java/lang/Character.isUpperCase:(C)Z ; ifne ; bipush ; if_icmpne ; invokestatic Method java/lang/Character.isDigit:(C)Z ; ifeq ; invokestatic Method java/lang/Character.isUpperCase:(C)Z ; ifne ; if_icmpne ; CaseInsensitiveMutableHttpHeaders backing map: getstatic Field java/lang/String.CASE_INSENSITIVE_ORDER:Ljava/util/Comparator; ; invokespecial Method java/util/TreeMap."<init>":(Ljava/util/Comparator;)V` |
```

## Verdicts

**Q1 — `follow_calls: all` on `javalin-apibuilder.yml` (§4a).** `ApiBuilder` keeps the
current instance in `private static final ThreadLocal<JavalinDefaultRoutingApi<?>>
staticJavalin`; `staticInstance()` reads it, and when it is `null` — no `apiBuilder { }`
block open on this thread — throws `java.lang.IllegalStateException("The static API can
only be used within a routes() call.")`; `get(String, Handler)` opens with `invokestatic
staticInstance`, and so does every other verb overload (read by hand, see the boundary
above). Therefore a module-local helper whose body reaches an `ApiBuilder` verb can only
have run inside a block — outside one it throws before registering anything — and the
combinator following the CALL from inside the block, with no origin to check because
there is none, attaches only routes Javalin itself registers. That is the one condition
under which origin-less following is honest (A1 excludes it for the Spring router's
`Supplier` bodies, which hand a value back and have no such guard), and it is the fact
the catalog's two `follow_calls: all` declarations cite.

**Q2 — Spring's `binder` rule (§5b, F6).** With a null value (offset 94 `ifnonnull`
falls through), `resolveArgument` takes `NamedValueInfo.defaultValue` when it is non-null
(99–116), else calls `handleMissingValue` — the 400 — when `required` is true AND
`MethodParameter.isOptional()` is false (121–144). `updateNamedValueInfo` turns a
`defaultValue` equal to `ValueConstants.DEFAULT_NONE` into null, and `@RequestParam`
declares `value`, `name`, `required`, `defaultValue`. So `requirement: binder` is exactly:
`optional` when `required` is literally `false`, when a `defaultValue` is written (Q5
says when that is), or when Q3's predicate holds; else `required`.

**Q3 — what `isOptional()` reads (§5b).** Three disjuncts, in the bytecode's order: the
parameter type is `java.util.Optional` (`if_acmpeq`); `hasNullableAnnotation()` — a loop
over `getParameterAnnotations()` comparing each annotation type's `getSimpleName()` to
the literal `"Nullable"`, ANY package; or, on a Kotlin class with kotlin-reflect present,
`KotlinDelegate.isOptional` — `KType.isMarkedNullable()` or `KParameter.isOptional()` (a
declared default). **The predicate reads a DECLARATION annotation, never the Java type
system**: an unannotated Java `String` parameter is `required`, although D00 §5 records
its type reference as `nullable: true` by language rule — which is why the catalog rule
reads the parameter's `annotations` against the shape model's `nullability.nullable`
spellings and does not read `type.nullable` (ruled 2026-09-20). The Kotlin disjuncts are
covered without naming the language: kotlinc emits `@org.jetbrains.annotations.Nullable`
on a public nullable parameter (in the list) and the extractor publishes
`declares_default: true` for a defaulted one (D00 §5a).

**Q4 — `HeadersRequestCondition` (§5c, A4).** `parseExpressions` builds a
`HeaderExpression` per string and drops it when its name `equalsIgnoreCase` `Accept` or
`Content-Type` — Spring routes those two into `consumes`/`produces` — so the mapping's
`headers=` reader skips the same two names.

**Q5 — `defaultValue` reaches the class file only when written (§5b, resolution 1).** The
sample's `written(@RequestParam(defaultValue = "0") String)` compiles to
`RuntimeVisibleParameterAnnotations … #14(#15=s#16)` — one element_value_pair — and
`unwritten(@RequestParam String)` to `#14()` — none. `DEFAULT_NONE` is the annotation
interface's `AnnotationDefault`, applied by reflection at runtime and never copied into a
use site, so "`default_attr` present in the annotation's `args`" is a sound test and the
`DEFAULT_NONE` sentinel never has to be compared.

**Q6–Q8 — Micronaut's `binder` rule with no `required_attr` (§5b, F8).** `@QueryValue` and
`@CookieValue` declare `value` and `defaultValue`; `@Header` declares `value`, `name`,
`defaultValue`; none declares `required` (Q6). An unsatisfied binding reaches
`AbstractRouteMatch.setBindingResultOfFail`, which sets null when `Argument.isNullable()`,
`Optional.empty()` when `isOptional()`, and otherwise throws
`UnsatisfiedRouteException.create(argument)` — the 400 (Q7). `isNullable()` is
`hasStereotype("jakarta.annotation.Nullable")`; `isOptional()` is `type == Optional.class`.
The processor maps ten further spellings onto that stereotype (Q8):
`io.micronaut.core.annotation.Nullable`, `javax.annotation.Nullable`,
`org.jetbrains.annotations.Nullable` (kotlinc's, so a Kotlin `String?` under kapt binds
as optional), `org.jspecify.annotations.Nullable`, `edu.umd.cs.findbugs.annotations.Nullable`,
`androidx.annotation.Nullable`, `org.eclipse.jdt.annotation.Nullable`,
`reactor.util.annotation.Nullable`, `io.reactivex.annotations.Nullable`,
`io.reactivex.rxjava3.annotations.Nullable`. A Micronaut `defaultValue` is read by the
binder itself (`QueryValueArgumentBinder`, not quoted) and its presence in `args` is the
same test Q5 justifies for Spring. So Micronaut's rule is Spring's minus the `required`
attribute — the same `binder` predicate with `required_attr` unset — and the catalog says
so on each entry.

**Q9–Q10 — JAX-RS and RESTEasy Reactive: `optional` (§5b, F9, A9).** `@QueryParam`,
`@HeaderParam`, `@CookieParam` declare `value` only, `@DefaultValue` is a separate
annotation with `value`, and Quarkus REST's `@RestQuery`/`@RestHeader`/`@RestCookie`
declare `value` only (Q9). Each extractor returns the request context's read verbatim
(`getQueryParameter`, `getHeader`, `getCookieParameter`); the single-valued query path is
`ServerHttpRequest.getQueryParam(name)` with an `ifnull` guarding only the encoder;
`ParameterHandler.handleResult` substitutes `defaultValue` when the value is null and
otherwise stores the null into the parameter array — no branch throws for an absent value
(Q10). So absent → null or `@DefaultValue`, never a 400: `requirement: optional` on every
entry, `default_annotation` informational.

**Q11–Q12 — quarkus-reactive-routes: `optional` (§5b).** `@Param` and `@Header` declare
`value` only (Q11). The deployment generates, for a `String` parameter, a call to
`HttpServerRequest.getParam(String)` / `getHeader(String)` — whose returns Vert.x declares
`@io.vertx.codegen.annotations.Nullable` and whose bodies are `params().get(name)` /
`headers().get(name)` — and wraps an `Optional` parameter in `Optional.ofNullable` (Q12).
Absent → null (or `Optional.empty()`), no throw: `requirement: optional`, confirming what
§5b's table asked this probe to confirm.

**Q13 — the expression grammar (§5c).** The constructor finds `=` (`indexOf(61)`); with
none, `isNegated` is `startsWith("!")` and the name is the rest (`!name` → absent-required;
`name` → required); with one, `isNegated` is a `!` (33) at the character before it, the
name is the text before `!=`/`=`, the value the text after (`name=v` → required with the
value; `name!=v` → the value must NOT be `v`, which the framework serves when the
parameter is absent — `optional`, the excluded value lost, stated on the catalog). An
empty name parses (the constructor does not check it) and matches nothing a client could
send, so the mapping reader SKIPS it rather than writing a nameless requirement.

**Q14 — Javalin's reads by arity (§5d, F7).** `queryParam(String)` is
`queryParams(key).firstOrNull()`, `header(String)` is `req().getHeader(name)`,
`cookie(String)` is `CookieKt.getCookie(req(), name)` — three READS of the request, and
all three hand a null through. `header(String, String)` is `res().setHeader` and
`cookie(String, String, int)` builds a `Cookie` and hands it to `cookie(Cookie)` — SETS
on the response. The same name, two directions, told apart by nothing but the argument
count: every `request_reads` entry carries `arity`. `queryParamAsClass`/`headerAsClass`
read through the one-argument read and hand back a `Validator`.

**Q15 — `Validator.get()` throws (§5d, A3).** `Validator.get()` is `BaseValidator.get()`
under a `checkNotNull`; `BaseValidator.get()` is `getOrThrow(get$1)`, and `get$1` builds a
`ValidationException` from the error map; the lazily computed map (`errors$2`, offsets
229–259) adds `NULLCHECK_FAILED` when the typed value is null and the validator is not a
`NullableValidator`. So `ctx.queryParamAsClass("n", Integer.class).get()` cannot run
without `n`: the FRAMEWORK refuses the request (`ValidationException` → 400 through
Javalin's default mapper), and `required` is Javalin's word — declared as `then: { method:
get, requirement: required }` on the `AsClass` entries, one result-to-receiver step. A
chain ending in `getOrDefault`, `allowNullable()` or nothing at all stays NULL.

**Q16–Q17 — the Servlet API's reads (§5d).** `ServletRequest.getParameter(String)` and
`HttpServletRequest.getHeader(String)` are `public abstract` on both spellings: the API
states nothing about an absent name. Tomcat's `connector.Request.getParameter` is
`Parameters.getParameter`, whose tail is `ifnull … aconst_null ; areturn`; `getHeader` is
`coyote.Request.getHeader` → `MimeHeaders.getHeader`, `ifnull ; aconst_null ; areturn`.
Null on absent, no throw, on 10.1.50 and 9.0.121 alike: `requirement` NULL on both
servlet catalogs' entries — the handler reads the value, and the container decides
nothing.

**Q18 — the second spelling of an unwritten name (§5b, `fallback_spelling`).** Every binder
resolves the name it binds by the same way — `stringValue(@X)` (the written `value`; the
header binder tries `name` next in `lambda$bind$0`), `orElse(argument.getName())` — and hands
it to `doBind` (the query binder to its four-argument overload; the cell shows the call for
all three). `doResolve` calls `resolveValue(name)`; on null it computes
`getFallbackFormat(argument)`, and when that differs from the name it retries `resolveValue`
with it. The base class's fallback is `NameUtils.hyphenate(argument.getName())`, which
`@QueryValue` inherits and `@CookieValue` restates; the header binder's override is
`hyphenate(capitalize(argument.getName()), false)`. `hyphenate(String)` is `hyphenate(s,
true)`; `hyphenate(s, lowerCase)` returns `s` with `[_ ]` replaced by `-` when
`isHyphenatedLowerCase(s)` (non-empty, `[\p{javaLowerCase}\d-]+` throughout, first
character a letter), else `separateCamelCase(replaced, lowerCase, '-')` — whose
`lowerCase = false` loop puts the separator before an upper-case character following a
non-upper-case one and keeps case, and whose `lowerCase = true` loop lower-cases every
letter and puts the separator before an upper-case character unless it follows an
upper-case character, a `.`, or a digit after an upper-case character or the separator.
`capitalize` returns `s` unchanged when its first character is lower-case and its second
upper-case (`xTenant`), else upper-cases the first. So `@QueryValue String pageSize` is
served by `?pageSize=` OR `?page-size=`, and `@Header String xTenant` by `xTenant` or
`x-Tenant` — two names, and `pageSize required` states one of them as if it were the only
one. **The catalog rule:** where the fallback of the parameter's own name differs from it,
the row keeps its requirement and names nothing (`name` NULL, `resolution: unresolved`);
where the two coincide — `tenant` → `tenant`; a header's `tenant` → `Tenant`, header names
comparing case-insensitively in the framework's `CaseInsensitiveMutableHttpHeaders`
(`TreeMap(String.CASE_INSENSITIVE_ORDER)`) — the name stands. A WRITTEN name stands as
written, though `doResolve` retries the parameter's hyphenated name after it too
(`@Header("X-Tenant") String tenantHeader` also accepts `Tenant-Header`): stated as
`docs/open-issues.md` OI-104, not built.

`measured: 2026-09-20`, rows 1–18, on the sixteen archives the scope names.
