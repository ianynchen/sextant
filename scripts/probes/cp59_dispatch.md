# CP-59 — Spring application events (spring-context, spring-tx 7.0.1) and CDI events (CDI API 4.1.0, 2.0.0 and 1.0.0, ArC 3.17.5), measured

**Number.** The in-process dispatch plan (2026-11-05) names this probe CP-58; that number was
already taken by `scripts/probes/cp58-inherited-mappings/` (cited by four HTTP catalogs), so it
is CP-59. Later tasks of the plan add their rows here.

**Version scope.** `org.springframework:spring-context` **7.0.1** and `spring-tx` **7.0.1**, the
versions Spring Boot 4.0.0 manages, as `fixtures/orders-events` resolves them; each version below
is read from the jar's own `MANIFEST.MF` by the harness, which aborts if a jar or the key is
missing. JDK 21.0.13 for `java.util.EventObject`. Spring 5.x and 6.x are outside this measurement:
the descriptors below have been stable since 4.2 (`publishEvent(Object)`), but that is not read
here. The fixture is compiled by javac 21 (`--release 21`). For CDI events (findings 8-11):
`jakarta.enterprise:jakarta.enterprise.cdi-api`
**4.1.0** and `io.quarkus.arc:arc` **3.17.5**, the versions Quarkus 3.17.5 manages, as
`fixtures/orders-cdi-events` resolves them, and `javax.enterprise:cdi-api` **1.0.0** (coordinate
version `1.0`, the javax name `examples/camelinaction2` compiles against) and **2.0.0** (coordinate
`2.0`, Java EE 8). Each version is read from the jar's own `MANIFEST.MF`: `Implementation-Version`
for ArC and the javax 1.0 API, the OSGi `Bundle-Version` for the Jakarta API, which states no
`Implementation-Version`, and for javax 2.0, whose `Implementation-Version` is an unexpanded
`${parsedVersion.osgiVersion}`; the harness aborts if a jar or its key is missing. Jakarta CDI
3.x-4.0, javax 1.1-1.2, and other CDI containers (Weld) are outside this
measurement: which observers a `fire` notifies is read from ArC's bytecode; neither the CDI
specification's text nor Weld's code is read here.

**Why it was measured.** The `spring-events` catalog (spec 2026-11-05 §4 item 5) declares the two
`publishEvent` overloads as sends, `@EventListener` / `@TransactionalEventListener` methods and
`ApplicationListener` implementations as registrations keyed by an event type. Each word in it
cites a finding below instead of a recollection.

**What this probe does not settle.** It reads bytecode; no application context starts. Which
listener Spring actually calls for a `PayloadApplicationEvent` (a published non-event object) is
resolved by `ResolvableType` at run time and is not read here: the catalog keys a listener by its
parameter's erased type and matches by assignability, so a listener of a generic payload type
(`PayloadApplicationEvent<Foo>`, `List<Foo>`) is matched by its erasure.

**Why it was measured, CDI.** The `cdi-events` and `cdi-async-events` catalogs (spec 2026-11-05
§4 item 6) declare `Event.fire` / `fireAsync` as sends and methods with an `@Observes` /
`@ObservesAsync` parameter as registrations keyed by that parameter's type; findings 8-11 are what
each word cites. No container starts: event QUALIFIERS (`@Observes @Named("x") E`), which narrow
which observers a fire reaches at run time, are not read (a stated bound of the catalogs).

Reproduce: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 scripts/probes/cp59_dispatch/run.sh` (rebuilds
both fixtures, prints every table below).

## Findings (the facts the catalog uses)

1. **Sends.** `ApplicationEventPublisher` declares `publishEvent(ApplicationEvent)` (a default
   method, `ACC_PUBLIC` with a body) and `publishEvent(Object)` (abstract). Both hand their
   argument 0 to the context; javac picks the `ApplicationEvent` overload for an argument whose
   static type is one (table 7), so both are declared.
2. **Who else answers `publishEvent`.** `ApplicationContext` extends `ApplicationEventPublisher`;
   `ConfigurableApplicationContext` extends `ApplicationContext`; `AbstractApplicationContext`
   implements `ConfigurableApplicationContext`. javac writes the receiver's static type as the
   call's owner (table 7: a field typed `ApplicationContext` gives
   `ApplicationContext.publishEvent`), and `Dispatch.heirs` widens an owner only by MODULE
   subtypes, so each library interface is listed. A call through a field typed by a concrete
   context class (`GenericApplicationContext`, …) is not declared: a stated boundary.
3. **The listener's event type.** `ApplicationListenerMethodAdapter.resolveDeclaredEventTypes`
   throws where the method declares more than one parameter (a Kotlin `suspend` function's
   continuation not counted); where the annotation's `classes()` (aliased by `value()`) is
   non-empty it returns those classes, in order; otherwise it throws where the method declares
   no parameter, and returns parameter 0's type. So the catalog reads `path_from: [classes,
   value]` first and falls back to the one parameter (`request_body: {fallback:
   sole_unannotated}`, `path_fallback: payload_type`).
4. **`@TransactionalEventListener`** is `@Target({METHOD, ANNOTATION_TYPE})`,
   `@Retention(RUNTIME)` and meta-annotated `@EventListener`; it declares `value()`/`classes()`
   (`Class[]`) as `@EventListener` does. The meta-annotation sits on a library annotation type the
   composition pass does not scan, so the catalog lists the annotation itself.
5. **The interface form.** `ApplicationListener<E extends ApplicationEvent>` declares
   `onApplicationEvent(ApplicationEvent)`. The fixture's `MailListener implements
   ApplicationListener<OrderPlaced>` compiles to `onApplicationEvent(OrderPlaced)` (`ACC_PUBLIC`)
   and `onApplicationEvent(ApplicationEvent)` flagged `ACC_BRIDGE, ACC_SYNTHETIC`. The bridge
   carries no `bridge_of` (D00 §5a: that key is written only on Kotlin's `$default` bridges and
   `DefaultImpls` bodies); its fact carries `modifiers.synthetic: true`, which is what the
   registration reader reads to carry the bridge to the method it forwards to.
6. **The root of an event's ancestry.** `ApplicationEvent`'s `super_class` is
   `java/util/EventObject` (the spring-context header the workspace reads says so too);
   `EventObject`'s is `java/lang/Object`, in a JDK nothing scans; and the fixture's plain
   `OrderShipped` has `java/lang/Object` too, which its symbol fact does not carry (D00 §5a
   writes no `superclass` for the root). So no scanned or headered ancestry reaches the root
   type, and `type-models/conformance.yml` declares it once for every type (`subtype: "*"`,
   JLS 4.10.2): a listener of `Object` receives a plain event and one extending
   `ApplicationEvent` alike.
7. **What javac writes at a publish site** (the fixture's `OrderService`): `invokeinterface
   ApplicationEventPublisher.publishEvent(ApplicationEvent)` for `new OrderPlaced(…)`,
   `publishEvent(Object)` for an `Object` parameter, and
   `ApplicationContext.publishEvent(ApplicationEvent)` through a field typed `ApplicationContext`.

8. **CDI sends.** The Jakarta `Event<T>` declares `fire(T)`, erased `(Ljava/lang/Object;)V`, and
   two `fireAsync` overloads, `(Object)` and `(Object, NotificationOptions)`, each returning a
   `CompletionStage`; each hands argument 0 to the container (the options choose an executor).
   The javax `Event` 1.0.0 declares `fire` only: no `fireAsync` and no `@ObservesAsync` (CDI 1.x).
   The javax 2.0.0 API declares both `fireAsync` overloads (`NotificationOptions` under
   `javax.enterprise.event`) and `@ObservesAsync`, so the asynchronous catalog names the Jakarta
   API and javax 2.x.
9. **Observer annotations.** `@Observes` (Jakarta and javax) and `@ObservesAsync` (Jakarta and
   javax 2.0) are
   `@Target(PARAMETER)`, `@Retention(RUNTIME)`: javac writes them in the method's
   `RuntimeVisibleParameterAnnotations`, on the one parameter carrying them, and the method has
   no annotation of its own. The fixture's `onStart(@Observes StartupEvent, ShippingService)`
   carries it on parameter 0 and nothing on the injected parameter 1. So an observer is
   selected by a parameter annotation and keyed by that parameter's type
   (`mapping.selected_by_parameter`).
10. **`fire` and `fireAsync` reach different observers.** ArC's `EventImpl.fire` calls
   `Notifier.notify(event, handler, false)` and the supplier `fireAsync` runs calls it with
   `true`; `notify` filters the observers by `ObserverMethod::isAsync` when that flag is true and
   by `Predicate.not(ObserverMethod::isAsync)` when false. So a `fire` notifies only `@Observes`
   observers and a `fireAsync` only `@ObservesAsync` ones: two mechanisms, `cdi-events` and
   `cdi-async-events`, so that neither's sends reach the other's registrations.
11. **What javac writes at a fire site** (the fixture's `ShippingService`): `invokeinterface
   jakarta/enterprise/event/Event.fire:(Ljava/lang/Object;)V` and `Event.fireAsync:
   (Ljava/lang/Object;)Ljava/util/concurrent/CompletionStage;` through fields typed `Event<…>`:
   the owner is `Event` itself, so no other owner is declared.

## Observations (generated by `run.sh`; not edited)

Verbatim from `run.sh`'s generated output. The `7.0.1` column is the version each jar
reported in its own `MANIFEST.MF` (`Implementation-Version`), which `probe.py` reads and
aborts without, not the version the fixture's pom asked for.

### Identity (from each jar's own MANIFEST.MF)

- `spring-context`: `Implementation-Version: 7.0.1`
- `spring-tx`: `Implementation-Version: 7.0.1`

### 1. Sends

| owner `publishEvent` | 7.0.1 |
|---|---|
| `org.springframework.context.ApplicationEventPublisher` | `(Lorg/springframework/context/ApplicationEvent;)V` (0x0001) ACC_PUBLIC |
| `org.springframework.context.ApplicationEventPublisher` | `(Ljava/lang/Object;)V` (0x0401) ACC_PUBLIC, ACC_ABSTRACT |

### 2. Who inherits `publishEvent`

- public interface org.springframework.context.ApplicationContext extends org.springframework.core.env.EnvironmentCapable,org.springframework.beans.factory.ListableBeanFactory,org.springframework.beans.factory.HierarchicalBeanFactory,org.springframework.context.MessageSource,org.springframework.context.ApplicationEventPublisher,org.springframework.core.io.support.ResourcePatternResolver {
- public interface org.springframework.context.ConfigurableApplicationContext extends org.springframework.context.ApplicationContext,org.springframework.context.Lifecycle,java.io.Closeable {
- public abstract class org.springframework.context.support.AbstractApplicationContext extends org.springframework.core.io.DefaultResourceLoader implements org.springframework.context.ConfigurableApplicationContext {

### 3. How the listener's event type is read

`ApplicationListenerMethodAdapter.resolveDeclaredEventTypes(Method, EventListener)`:

- `1: invokestatic #111 // Method org/springframework/core/KotlinDetector.isSuspendingFunction:(Ljava/lang/reflect/Method;)Z`
- `4: ifeq 16`
- `8: invokevirtual #117 // Method java/lang/reflect/Method.getParameterCount:()I`
- `17: invokevirtual #117 // Method java/lang/reflect/Method.getParameterCount:()I`
- `23: if_icmple 43`
- `26: new #123 // class java/lang/IllegalStateException`
- `31: invokestatic #125 // Method java/lang/String.valueOf:(Ljava/lang/Object;)Ljava/lang/String;`
- `34: invokedynamic #129, 0 // InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;)Ljava/lang/String;`
- `39: invokespecial #133 // Method java/lang/IllegalStateException."<init>":(Ljava/lang/String;)V`
- `42: athrow`
- `44: ifnull 117`
- `48: invokeinterface #136, 1 // InterfaceMethod org/springframework/context/event/EventListener.classes:()[Ljava/lang/Class;`
- `56: ifle 117`
- `59: new #140 // class java/util/ArrayList`
- `65: invokespecial #142 // Method java/util/ArrayList."<init>":(I)V`
- `85: if_icmpge 114`
- `99: invokestatic #145 // Method org/springframework/core/ResolvableType.forClass:(Ljava/lang/Class;)Lorg/springframework/core/ResolvableType;`
- `102: invokeinterface #151, 2 // InterfaceMethod java/util/List.add:(Ljava/lang/Object;)Z`
- `116: areturn`
- `118: ifne 138`
- `121: new #123 // class java/lang/IllegalStateException`
- `126: invokestatic #125 // Method java/lang/String.valueOf:(Ljava/lang/Object;)Ljava/lang/String;`
- `129: invokedynamic #157, 0 // InvokeDynamic #1:makeConcatWithConstants:(Ljava/lang/String;)Ljava/lang/String;`
- `134: invokespecial #133 // Method java/lang/IllegalStateException."<init>":(Ljava/lang/String;)V`
- `137: athrow`
- `140: invokestatic #158 // Method org/springframework/core/ResolvableType.forMethodParameter:(Ljava/lang/reflect/Method;I)Lorg/springframework/core/ResolvableType;`
- `143: invokestatic #162 // Method java/util/Collections.singletonList:(Ljava/lang/Object;)Ljava/util/List;`
- `146: areturn`

### 4. The listener annotations

#### `org.springframework.context.event.EventListener`

- elements: `value()` `()[Ljava/lang/Class;`, `classes()` `()[Ljava/lang/Class;`, `condition()` `()Ljava/lang/String;`, `defaultExecution()` `()Z`, `id()` `()Ljava/lang/String;`
- on the type: `java.lang.annotation.Target(`
- on the type: `value=[Ljava/lang/annotation/ElementType;.METHOD,Ljava/lang/annotation/ElementType;.ANNOTATION_TYPE]`
- on the type: `java.lang.annotation.Retention(`
- on the type: `value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME`
- on the type: `java.lang.annotation.Documented`
- on the type: `org.springframework.aot.hint.annotation.Reflective`

#### `org.springframework.transaction.event.TransactionalEventListener`

- elements: `phase()` `()Lorg/springframework/transaction/event/TransactionPhase;`, `value()` `()[Ljava/lang/Class;`, `classes()` `()[Ljava/lang/Class;`, `condition()` `()Ljava/lang/String;`, `fallbackExecution()` `()Z`, `id()` `()Ljava/lang/String;`
- on the type: `java.lang.annotation.Target(`
- on the type: `value=[Ljava/lang/annotation/ElementType;.METHOD,Ljava/lang/annotation/ElementType;.ANNOTATION_TYPE]`
- on the type: `java.lang.annotation.Retention(`
- on the type: `value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME`
- on the type: `java.lang.annotation.Documented`
- on the type: `org.springframework.context.event.EventListener`

### 5. The interface form

- public interface org.springframework.context.ApplicationListener<E extends org.springframework.context.ApplicationEvent> extends java.util.EventListener {
- `ApplicationListener.onApplicationEvent` `(Lorg/springframework/context/ApplicationEvent;)V` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- fixture `MailListener.onApplicationEvent` `(Lcom/acme/events/OrderPlaced;)V` (0x0001) ACC_PUBLIC
- fixture `MailListener.onApplicationEvent` `(Lorg/springframework/context/ApplicationEvent;)V` (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC

### 6. The root of an event's ancestry

- `org.springframework.context.ApplicationEvent` super_class: `java/util/EventObject`
- `java.util.EventObject` super_class: `java/lang/Object`
- fixture `com.acme.events.OrderShipped` super_class: `java/lang/Object`

### 7. What javac writes at the fixture's publish sites

- `OrderService`: `invokeinterface` `org/springframework/context/ApplicationEventPublisher.publishEvent:(Lorg/springframework/context/ApplicationEvent;)V`
- `OrderService`: `invokeinterface` `org/springframework/context/ApplicationEventPublisher.publishEvent:(Lorg/springframework/context/ApplicationEvent;)V`
- `OrderService`: `invokeinterface` `org/springframework/context/ApplicationEventPublisher.publishEvent:(Ljava/lang/Object;)V`
- `OrderService`: `invokeinterface` `org/springframework/context/ApplicationEventPublisher.publishEvent:(Ljava/lang/Object;)V`
- `OrderService`: `invokeinterface` `org/springframework/context/ApplicationEventPublisher.publishEvent:(Ljava/lang/Object;)V`
- `OrderService`: `invokeinterface` `org/springframework/context/ApplicationContext.publishEvent:(Lorg/springframework/context/ApplicationEvent;)V`

### Identity, CDI (from each jar's own MANIFEST.MF)

- `jakarta.enterprise.cdi-api`: `Bundle-Version: 4.1.0`
- `javax.enterprise:cdi-api`: `Implementation-Version: 1.0.0`
- `javax.enterprise:cdi-api` (2.x): `Bundle-Version: 2.0.0`
- `arc`: `Implementation-Version: 3.17.5`

### 8. Sends: `Event`

- `jakarta.enterprise.event.Event.fire` `(Ljava/lang/Object;)V` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `jakarta.enterprise.event.Event.fireAsync` `(Ljava/lang/Object;)Ljava/util/concurrent/CompletionStage;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `jakarta.enterprise.event.Event.fireAsync` `(Ljava/lang/Object;Ljakarta/enterprise/event/NotificationOptions;)Ljava/util/concurrent/CompletionStage;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `javax.enterprise.event.Event.fire` (1.0.0) `(Ljava/lang/Object;)V` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `javax.enterprise.event.Event.fireAsync` (1.0.0) none
- `javax.enterprise.event.Event.fire` (2.0.0) `(Ljava/lang/Object;)V` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `javax.enterprise.event.Event.fireAsync` (2.0.0) `(Ljava/lang/Object;)Ljava/util/concurrent/CompletionStage;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `javax.enterprise.event.Event.fireAsync` (2.0.0) `(Ljava/lang/Object;Ljavax/enterprise/event/NotificationOptions;)Ljava/util/concurrent/CompletionStage;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT

### 9. The observer annotations, and where javac writes them

#### `jakarta.enterprise.event.Observes`

- on the type: `java.lang.annotation.Target(`
- on the type: `value=[Ljava/lang/annotation/ElementType;.PARAMETER]`
- on the type: `java.lang.annotation.Retention(`
- on the type: `value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME`
- on the type: `java.lang.annotation.Documented`

#### `jakarta.enterprise.event.ObservesAsync`

- on the type: `java.lang.annotation.Target(`
- on the type: `value=[Ljava/lang/annotation/ElementType;.PARAMETER]`
- on the type: `java.lang.annotation.Retention(`
- on the type: `value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME`
- on the type: `java.lang.annotation.Documented`

#### `javax.enterprise.event.Observes`

- on the type: `java.lang.annotation.Target(`
- on the type: `value=[Ljava/lang/annotation/ElementType;.PARAMETER]`
- on the type: `java.lang.annotation.Retention(`
- on the type: `value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME`
- on the type: `java.lang.annotation.Documented`

#### `javax.enterprise.event.ObservesAsync`

- on the type: `java.lang.annotation.Target(`
- on the type: `value=[Ljava/lang/annotation/ElementType;.PARAMETER]`
- on the type: `java.lang.annotation.Retention(`
- on the type: `value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME`
- on the type: `java.lang.annotation.Documented`

- fixture `StartupObserver`: `(Lio/quarkus/runtime/StartupEvent;Lcom/acme/shipping/ShippingService;)V` parameter 0: `jakarta.enterprise.event.Observes`
- fixture `StartupObserver`: `(Lio/quarkus/runtime/StartupEvent;Lcom/acme/shipping/ShippingService;)V` parameter 1: `-`
- fixture `AsyncObserver`: `(Lcom/acme/shipping/Shipped;)V` parameter 0: `jakarta.enterprise.event.ObservesAsync`

### 10. Which observers ArC notifies

`EventImpl.fire(Object)`:

- `19: iconst_0`
- `20: invokevirtual #142 // Method io/quarkus/arc/impl/EventImpl$Notifier.notify:(Ljava/lang/Object;Lio/quarkus/arc/impl/EventImpl$ObserverExceptionHandler;Z)V`

`EventImpl$1.get()` (the supplier `fireAsync` runs):

- `16: iconst_0`
- `46: iconst_1`
- `47: invokevirtual #74 // Method io/quarkus/arc/impl/EventImpl$Notifier.notify:(Ljava/lang/Object;Lio/quarkus/arc/impl/EventImpl$ObserverExceptionHandler;Z)V`

`EventImpl$Notifier.notify(Object, ObserverExceptionHandler, boolean)`, up to the filter:

- `7: iload_3`
- `8: ifeq 19`
- `11: invokedynamic #129, 0 // InvokeDynamic #1:test:()Ljava/util/function/Predicate;`
- `16: goto 27`
- `19: invokedynamic #129, 0 // InvokeDynamic #1:test:()Ljava/util/function/Predicate;`
- `24: invokestatic #135 // InterfaceMethod java/util/function/Predicate.not:(Ljava/util/function/Predicate;)Ljava/util/function/Predicate;`
- `27: astore 4`

`EventImpl$Notifier` lambda bootstraps:

- 0: `REF_invokeVirtual io/quarkus/arc/impl/EventImpl$Notifier.isTxObserver:(Ljakarta/enterprise/inject/spi/ObserverMethod;)Z`
- 1: `REF_invokeInterface jakarta/enterprise/inject/spi/ObserverMethod.isAsync:()Z`
- 2: `REF_invokeVirtual io/quarkus/arc/impl/EventImpl$Notifier.isNotTxObserver:(Ljakarta/enterprise/inject/spi/ObserverMethod;)Z`
- 3: `REF_invokeVirtual io/quarkus/arc/impl/EventImpl$Notifier.isNotAfterSuccess:(Ljakarta/enterprise/inject/spi/ObserverMethod;)Z`

### 11. What javac writes at the fixture's fire sites

- `ShippingService`: `invokeinterface` `jakarta/enterprise/event/Event.fire:(Ljava/lang/Object;)V`
- `ShippingService`: `invokeinterface` `jakarta/enterprise/event/Event.fire:(Ljava/lang/Object;)V`
- `ShippingService`: `invokeinterface` `jakarta/enterprise/event/Event.fire:(Ljava/lang/Object;)V`
- `ShippingService`: `invokeinterface` `jakarta/enterprise/event/Event.fireAsync:(Ljava/lang/Object;)Ljava/util/concurrent/CompletionStage;`
