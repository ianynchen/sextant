# CP-25 — binder rules: Javalin's `ApiBuilder` guard, and what six frameworks' parameter binders enforce

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
class itself is not compiled here. The §5d rows (Javalin `Validator.get()`,
`jakarta.servlet` reads) are not in this table yet and join with that mechanism's task.

**Version scope (§5.4).** Fourteen archives, each filed under the `Implementation-Version`
its own `META-INF/MANIFEST.MF` reports, read as: `io.javalin:javalin` **6.4.0**;
`org.springframework:spring-web`, `spring-core` and `spring-webmvc` **6.1.6**;
`io.micronaut:micronaut-http`, `micronaut-core`, `micronaut-router` and
`micronaut-core-processor` **4.7.6**; `io.quarkus.resteasy.reactive:resteasy-reactive`
and `resteasy-reactive-common`, `io.quarkus:quarkus-reactive-routes` and
`quarkus-reactive-routes-deployment` **3.17.5**; `io.vertx:vertx-core` **4.5.11** (the
Vert.x the Quarkus 3.17.5 BOM pins); `jakarta.ws.rs:jakarta.ws.rs-api` **3.1.0**. The
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
| what the run read | 3.1.0 | 3.17.5 | 4.5.11 | 4.7.6 | 6.1.6 | 6.4.0 |
|---|---|---|---|---|---|---|
| artifacts reporting this version | jakarta.ws.rs:jakarta.ws.rs-api | io.quarkus.resteasy.reactive:resteasy-reactive, io.quarkus.resteasy.reactive:resteasy-reactive-common, io.quarkus:quarkus-reactive-routes, io.quarkus:quarkus-reactive-routes-deployment | io.vertx:vertx-core | io.micronaut:micronaut-core, io.micronaut:micronaut-core-processor, io.micronaut:micronaut-http, io.micronaut:micronaut-router | org.springframework:spring-core, org.springframework:spring-web, org.springframework:spring-webmvc | io.javalin:javalin |
| identity read from the archive itself (`Implementation-Version`) | yes | yes | yes | yes | yes | yes |

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

`measured: 2026-09-20`, rows 1–12, on the fourteen archives the scope names.
