# CP-7 — the rules the `@HttpExchange` direction flip mirrors

**Question.** 2O Task 10 flips a locally-implemented `@HttpExchange` interface's
rows from OUTBOUND to INBOUND. Spec §6 gated that flip on
`owner_implemented_in_module: true`, which is a condition SEXTANT invented:
Spring does not serve an interface because somebody implemented it, it serves it
because the implementation is a handler bean. GUIDELINES §8.1 rule 1 says mirror
the framework's own predicate and rule 4 says never add behaviour the framework
does not have under the exact circumstances, so every clause of the flip is a
measurement here rather than a prediction.

The original CP-7 asked something else — whether 2E's inheritance walk carries
an interface's annotations onto the implementing class — and that question is
**unanswerable as posed**: the walk runs only for a catalog declaring a
type-level gate (`resolve/engines/annotation_driven.py`'s `_synthetic_annotations`,
`run_inheritance = type_annotation_fqn is not None`), `spring-http-interface.yml`
deliberately declares none, and a shipped test pins that a gateless catalog must
never synthesize onto an implementer. So the checkpoint is restated as four
questions about Spring instead.

| # | what the flip claims | why it is worth a probe |
|---|---|---|
| 1 | the implementing class must be a CONTROLLER | GUIDELINES §8.1 stated this rule for a month as "`@Controller` **or** a type-level `@RequestMapping`", corrected in `8b4d174`. A disjunct that is not there is exactly what a plain `@Service` implementation would pass, and deriving an inbound route for one invents an endpoint nothing serves |
| 2 | the SERVER side reads `@HttpExchange` at all, through the type hierarchy | if it does not, the flipped row is a fabrication twice over — the address is served by nothing, and the interface's annotations never reach the implementing class |
| 3 | a `default` method the controller inherits and never overrides is still served | decides whether the handler symbol may be the INTERFACE's own method. A join that insisted on a method the implementing class declares would silently drop a route the container serves |
| 4 | one address attribute serves both directions | the client invoker reads `url()` and the server's mapping builder reads `value()`. `spring-http-interface.yml` declares `path_from: [value, url]` for the outbound row, and the flipped row reads the same list |

**Version scope (§5.4).** Read against **spring-webmvc 6.1.6, 6.2.15, 7.0.2 and
7.0.9, spring-core 6.2.15 and spring-web 6.2.15**. Four webmvc minors rather
than one for `A-C7`'s own reason: the claim under test is that the handler
predicate is STABLE and the catalogs' literal compare is not, and a verdict from
a single minor could not say that. Questions 3 and 4 are evidence about the one
jar that declares the class they read, at the version named beside them, and
about no other. **No Spring Boot version is in scope and none is needed** — every
rule here is Framework's, read out of Framework's own jars; Boot contributes
auto-configuration, not the handler predicate.

**How to run.** `bash scripts/probes/cp7_http_exchange/run.sh`. It resolves each
artifact through Maven (network on the first run only, cached in `~/.m2`
afterwards), reads each jar's self-reported version out of the archive it
opened, aborts if that disagrees with the coordinate that resolved it, and asks
`javap` the four questions. Needs a JDK and Maven. Not a test: nothing in the
suite runs it, and NFR-1's no-network rule governs the suite rather than
evidence gathering.

`tests/architecture/test_http_exchange_direction_rules.py` is the offline half.
It pins the shipped catalog against the table below, so a flip condition edited
without re-running this harness fails the suite rather than going quiet.

## Expectation table

| # | Under test | Expected |
|---|---|---|
| 1 | `RequestMappingHandlerMapping.isHandler`, per minor | one `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call and nothing else — no `@RequestMapping` disjunct on any minor in scope |
| 2 | the annotation search that builds a `RequestMappingInfo` | `MergedAnnotations.from(element, SearchStrategy.TYPE_HIERARCHY, …)` filtered by `typeIn(RequestMapping, HttpExchange)` |
| 3 | `MethodIntrospector.selectMethods(Class, MetadataLookup)` | the walked type set includes `ClassUtils.getAllInterfacesForClassAsSet(targetType)` |
| 4 | `@HttpExchange`'s attributes | `value` and `url` are `@AliasFor` each other, so only the one the author typed reaches the bytecode and one alias list serves both directions |

## Observations

Verbatim from `run.sh`'s generated tables (`probe.py` prints them; nothing here
is typed by hand). **Every column header of the first table is a version the JAR
itself reported**, out of its manifest's `Implementation-Version`, and not the
version the coordinate list asked for; `probe.py` ABORTS the whole run when the
two disagree rather than filling a mislabelled column.

| what the run read | 6.1.6 | 6.2.15 | 7.0.2 | 7.0.9 |
|---|---|---|---|---|
| artifacts reporting this version | spring-webmvc | spring-core, spring-web, spring-webmvc | spring-webmvc | spring-webmvc |
| identity read from the archive itself | yes | yes | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1a | `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 6.1.6 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 1b | `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 6.2.15 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 1c | `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 7.0.2 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 1d | `RequestMappingHandlerMapping.isHandler` | `spring-webmvc` | 7.0.9 | `aload_1 ; ldc class org/springframework/stereotype/Controller ; invokestatic Method org/springframework/core/annotation/AnnotatedElementUtils.hasAnnotation:(Ljava/lang/reflect/AnnotatedElement;Ljava/lang/Class;)Z ; ireturn` |
| 2a | the mapping's annotation search and its accepted types | `spring-webmvc` | 6.1.6 | `private static java.util.List<org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping$AnnotationDescriptor> getAnnotationDescriptors(java.lang.reflect.AnnotatedElement); ; getstatic Field org/springframework/core/annotation/MergedAnnotations$SearchStrategy.TYPE_HIERARCHY:Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy; ; invokestatic Method org/springframework/core/annotation/RepeatableContainers.none:()Lorg/springframework/core/annotation/RepeatableContainers; ; invokestatic InterfaceMethod org/springframework/core/annotation/MergedAnnotations.from:(Ljava/lang/reflect/AnnotatedElement;Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy;Lorg/springframework/core/annotation/RepeatableContainers;)Lorg/springframework/core/annotation/MergedAnnotations; ; invokeinterface InterfaceMethod org/springframework/core/annotation/MergedAnnotations.stream:()Ljava/util/stream/Stream; ; iconst_2 ; anewarray class java/lang/Class ; dup ; iconst_0 ; ldc_w class org/springframework/web/bind/annotation/RequestMapping ; aastore ; dup ; iconst_1 ; ldc_w class org/springframework/web/service/annotation/HttpExchange ; aastore ; invokestatic Method org/springframework/core/annotation/MergedAnnotationPredicates.typeIn:([Ljava/lang/Class;)Ljava/util/function/Predicate;` |
| 2b | the mapping's annotation search and its accepted types | `spring-webmvc` | 6.2.15 | `private static java.util.List<org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping$AnnotationDescriptor> getAnnotationDescriptors(java.lang.reflect.AnnotatedElement); ; getstatic Field org/springframework/core/annotation/MergedAnnotations$SearchStrategy.TYPE_HIERARCHY:Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy; ; invokestatic Method org/springframework/core/annotation/RepeatableContainers.none:()Lorg/springframework/core/annotation/RepeatableContainers; ; invokestatic InterfaceMethod org/springframework/core/annotation/MergedAnnotations.from:(Ljava/lang/reflect/AnnotatedElement;Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy;Lorg/springframework/core/annotation/RepeatableContainers;)Lorg/springframework/core/annotation/MergedAnnotations; ; invokeinterface InterfaceMethod org/springframework/core/annotation/MergedAnnotations.stream:()Ljava/util/stream/Stream; ; iconst_2 ; anewarray class java/lang/Class ; dup ; iconst_0 ; ldc_w class org/springframework/web/bind/annotation/RequestMapping ; aastore ; dup ; iconst_1 ; ldc_w class org/springframework/web/service/annotation/HttpExchange ; aastore ; invokestatic Method org/springframework/core/annotation/MergedAnnotationPredicates.typeIn:([Ljava/lang/Class;)Ljava/util/function/Predicate;` |
| 2c | the mapping's annotation search and its accepted types | `spring-webmvc` | 7.0.2 | `private org.springframework.web.servlet.mvc.method.RequestMappingInfo createRequestMappingInfo(java.lang.reflect.AnnotatedElement); ; getstatic Field org/springframework/core/annotation/MergedAnnotations$SearchStrategy.TYPE_HIERARCHY:Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy; ; invokestatic Method org/springframework/core/annotation/RepeatableContainers.none:()Lorg/springframework/core/annotation/RepeatableContainers; ; invokestatic InterfaceMethod org/springframework/core/annotation/MergedAnnotations.from:(Ljava/lang/reflect/AnnotatedElement;Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy;Lorg/springframework/core/annotation/RepeatableContainers;)Lorg/springframework/core/annotation/MergedAnnotations; ; invokeinterface InterfaceMethod org/springframework/core/annotation/MergedAnnotations.stream:()Ljava/util/stream/Stream; ; iconst_2 ; anewarray class java/lang/Class ; dup ; iconst_0 ; ldc_w class org/springframework/web/bind/annotation/RequestMapping ; aastore ; dup ; iconst_1 ; ldc_w class org/springframework/web/service/annotation/HttpExchange ; aastore ; invokestatic Method org/springframework/core/annotation/MergedAnnotationPredicates.typeIn:([Ljava/lang/Class;)Ljava/util/function/Predicate;` |
| 2d | the mapping's annotation search and its accepted types | `spring-webmvc` | 7.0.9 | `private org.springframework.web.servlet.mvc.method.RequestMappingInfo createRequestMappingInfo(java.lang.reflect.AnnotatedElement); ; getstatic Field org/springframework/core/annotation/MergedAnnotations$SearchStrategy.TYPE_HIERARCHY:Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy; ; invokestatic Method org/springframework/core/annotation/RepeatableContainers.none:()Lorg/springframework/core/annotation/RepeatableContainers; ; invokestatic InterfaceMethod org/springframework/core/annotation/MergedAnnotations.from:(Ljava/lang/reflect/AnnotatedElement;Lorg/springframework/core/annotation/MergedAnnotations$SearchStrategy;Lorg/springframework/core/annotation/RepeatableContainers;)Lorg/springframework/core/annotation/MergedAnnotations; ; invokeinterface InterfaceMethod org/springframework/core/annotation/MergedAnnotations.stream:()Ljava/util/stream/Stream; ; iconst_2 ; anewarray class java/lang/Class ; dup ; iconst_0 ; ldc_w class org/springframework/web/bind/annotation/RequestMapping ; aastore ; dup ; iconst_1 ; ldc_w class org/springframework/web/service/annotation/HttpExchange ; aastore ; invokestatic Method org/springframework/core/annotation/MergedAnnotationPredicates.typeIn:([Ljava/lang/Class;)Ljava/util/function/Predicate;` |
| 3 | `MethodIntrospector.selectMethods` — the handler-candidate walk | `spring-core` | 6.2.15 | `invokestatic Method org/springframework/util/ClassUtils.getUserClass:(Ljava/lang/Class;)Ljava/lang/Class; ; invokestatic Method org/springframework/util/ClassUtils.getAllInterfacesForClassAsSet:(Ljava/lang/Class;)Ljava/util/Set; ; getstatic Field org/springframework/util/ReflectionUtils.USER_DECLARED_METHODS:Lorg/springframework/util/ReflectionUtils$MethodFilter; ; invokestatic Method org/springframework/util/ReflectionUtils.doWithMethods:(Ljava/lang/Class;Lorg/springframework/util/ReflectionUtils$MethodCallback;Lorg/springframework/util/ReflectionUtils$MethodFilter;)V` |
| 4 | `@HttpExchange`'s attributes and their `@AliasFor` pairing | `spring-web` | 6.2.15 | `value() @AliasFor url, url() @AliasFor value, method(), contentType(), accept(), headers()` |

## Verdicts

**Q1 — the flip condition is the CONTROLLER check.** `isHandler` is four
instructions on every minor in scope, and the whole of it is
`AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)`. There is no
`@RequestMapping` disjunct anywhere in it. So a class implementing an
`@HttpExchange` interface is served **only** where it is a controller, and spec
§6's `owner_implemented_in_module: true` would have published an inbound route
for a `@Service` implementation — an endpoint nothing serves (§8.1 rule 4).
`spring-http-interface.yml` gates the flip on the controller annotations
instead, and reads them as catalog data rather than as an engine literal.

**`hasAnnotation` is meta-annotation AND type-hierarchy aware, and we mirror
only the first half.** The composition half is shipped: the flip's controller
test runs through the same effective-annotations pre-pass `A-C7` widened the
type gate with, so a controller wearing a module-local `@ApiController` composed
from `@Controller` flips. The HIERARCHY half is **not** — a class whose only
stereotype is inherited from a `@Controller` superclass or interface derives
nothing, exactly as `docs/COVERAGE.md`'s existing inherited-stereotype row
states, and for the reason that row states: whether component scanning admits
such a bean at all is unmeasured, and `@Component` is not `@Inherited`. This
probe does not widen that boundary; it aligns with it.

**Q2 — the server side really does read `@HttpExchange`, through the type
hierarchy.** The mapping is built from
`MergedAnnotations.from(element, SearchStrategy.TYPE_HIERARCHY, RepeatableContainers.none())`
filtered by `typeIn(RequestMapping, HttpExchange)`, on all four minors. The
method that holds that sequence MOVED — 6.1.6 and 6.2.15 declare a private
static `getAnnotationDescriptors`, 7.0.x inlines it into
`createRequestMappingInfo` — which is why the harness searches the disassembly
for the search strategy instead of naming a method: keying on the name would
have printed an empty cell for half the scope and read as "the rule is gone".
`TYPE_HIERARCHY` is what carries the interface's own `@HttpExchange` (type-level
prefix included) onto the implementing class without the class repeating it.

**Q3 — an inherited `default` method IS a handler candidate.**
`MethodIntrospector.selectMethods` adds `ClassUtils.getAllInterfacesForClassAsSet(targetType)`
to the set of types it walks and runs `ReflectionUtils.doWithMethods` over each,
so a `default` method declared on the interface and never overridden is selected
and mapped. The consequence for Task 10 is precise: the flip is keyed on the
OWNER — the interface a controller implements — and the handler symbol is the
implementing class's own method **where it declares one**, falling back to the
interface's method where it does not. Keying the flip itself on the method join
would have dropped every inherited-default route.

**Q4 — one alias list serves both directions.** `value` and `url` are
`@AliasFor` each other, so only the one the author typed reaches the bytecode,
and `path_from: [value, url]` reads whichever it is. That the client invoker
calls `url()` and the server's mapping builder calls `value()` is therefore not
a divergence we have to model: it is the same attribute under two names.

**The dependency-jar half of the original CP-7, answered from code rather than
from bytecode.** An `@HttpExchange` interface living in a dependency reaches us
only where the user opted that jar in with `.sextant.yml`'s `extract_libraries`
(`ingress/detect/sextant_config.py:212`); absent that, the interface has no
symbol fact, no annotation fact, and the flip has nothing to key on — the
implementing controller's own mappings still derive, and the interface's do not.
That is a USER ACTION, so §8.1 rule 3 puts it in the usage docs as well as in
COVERAGE. When the jar IS opted in, its `interfaces` entries are prefixed with
the SCANNING module's coordinates while the interface's own symbols carry the
library's, so every comparison the flip makes is on the BARE descriptor — the
strip `_locally_implemented` already makes, for the same reason.
