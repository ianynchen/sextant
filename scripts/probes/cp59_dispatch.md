# CP-59 — Spring application events (spring-context, spring-tx 7.0.1), CDI events (CDI API 4.1.0, 2.0.0 and 1.0.0, ArC 3.17.5) and Java blocking queues (JDK 21.0.13, Guava 32.0.0), measured

**Number.** The in-process dispatch plan (2026-11-05) names this probe CP-58; that number was
already taken by `scripts/probes/cp58-inherited-mappings/` (cited by four HTTP catalogs), so it
is CP-59. Later tasks of the plan add their rows here.

**Version scope.** `org.springframework:spring-context` **7.0.1** and `spring-tx` **7.0.1**, the
versions Spring Boot 4.0.0 manages, as `fixtures/orders-events` resolves them; each version below
is read from the jar's own `MANIFEST.MF` by the harness, which aborts if a jar or the key is
missing. JDK 21.0.13 for `java.util.EventObject`, and the same JDK's `java.base` (`java.version`
`21.0.13.0.3`) for the blocking queues, findings 12-15, and Guava `32.0.0.jre` (its
`Bundle-Version`) for its drain helpers, finding 16, scoped below. Spring 5.x and 6.x are outside this measurement:
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

**Version scope, queues (findings 12-15).** `java.util.concurrent` of the JDK the harness runs,
**21.0.13** (`java.version` `21.0.13.0.3`, as the running `java` reports it with
`-XshowSettings:properties`; the JDK is no jar with a manifest, and the harness aborts if it
reports none). `fixtures/orders-queues` and a generated class are compiled by that javac
(`--release 21`); Guava's `Queues` (32.0.0-jre, the version `examples/apollo` pins) is on the
fixture's class path as a factory the fixture calls and for finding 16: its `Queues.drain` /
`drainUninterruptibly` descriptors and what they call on the queue, read from that jar, whose
manifest states `Bundle-Version: 32.0.0.jre` (no `Implementation-Version`). Other
JDKs are outside this measurement: the `BlockingQueue` descriptors have been stable since Java 5,
but that is not read here.

**Why it was measured, queues.** The `jdk-blocking-queue` catalog (spec 2026-11-05 §4 item 7)
declares `put`/`offer`/`add` as sends and `take`/`poll` as receives keyed by the queue
object; which OWNER javac writes at a call decides which entries match it, so findings 12-15 read
it off bytecode rather than off the javadoc.

Reproduce: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 scripts/probes/cp59_dispatch/run.sh` (rebuilds
the three fixtures, prints every table below).

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
12. **What `BlockingQueue` declares.** `put(E)`, `offer(E)`, `offer(E, long, TimeUnit)`,
   `add(E)`, `take()`, `poll(long, TimeUnit)`, `drainTo(Collection)` and
   `drainTo(Collection, int)`, each erased to `Object`, and `remove(Object)` (a value it is
   handed, discarded: no receive); the no-argument `poll()` and `remove()` are declared by
   `Queue`, which `BlockingQueue` extends, not by `BlockingQueue`.
13. **The JDK's blocking-queue types.** Two interfaces extend `BlockingQueue` (`BlockingDeque`,
   `TransferQueue`) and seven `java.util.concurrent` classes implement one of the three
   (`LinkedBlockingQueue`, `ArrayBlockingQueue`, `PriorityBlockingQueue`, `LinkedBlockingDeque`,
   `LinkedTransferQueue`, `SynchronousQueue`, `DelayQueue`). `DelayQueue<E extends Delayed>`
   bounds its element, so its methods erase to `Delayed`.
14. **javac writes the receiver's static type as the owner, for every declared call.** A generated
   class calling each of the seven calls through each of the ten types: `invokeinterface` on the
   interface, `invokevirtual` on the class, the owner always the type the receiver is declared
   as — `BlockingQueue.poll:()` though `Queue` declares it, `LinkedBlockingQueue.add` though
   `AbstractQueue` declares it — and `DelayQueue`'s descriptors naming `Delayed`. So the
   catalog lists every call on every one of the ten owners (`Dispatch.heirs` widens an owner only
   by types that do not declare the method, and each JDK class declares or is the owner of each).
   A receiver typed `Queue` writes `Queue` (the fixture's `Scratch`, table 15), which the
   catalog does not declare. The same holds for `drainTo` (both) and `remove()` (on
   `DelayQueue`, returning `Delayed`).
15. **What javac writes at the fixture's sites.** Fields typed `BlockingQueue` give
   `BlockingQueue` owners (`Pipeline`, `Worker`, `Cleaner`, `Relay`, `Batch`); the field
   typed `LinkedBlockingQueue` (`Alerts`, `dolphinscheduler-alert`'s shape) gives
   `LinkedBlockingQueue`; Guava's factory is an `invokestatic` of
   `Queues.newLinkedBlockingQueue`, the call the object walk ends at.
16. **Guava's drain helpers take from the queue they are handed.** `Queues.drain` and
   `drainUninterruptibly` are static, each in a `(BlockingQueue, Collection, int, long,
   TimeUnit)` and a `(BlockingQueue, Collection, int, Duration)` overload; the `long` form calls
   `BlockingQueue.drainTo(Collection, int)` and `BlockingQueue.poll(long, TimeUnit)` on argument 0,
   and the `Duration` form calls the `long` form. So each is a receive of the queue at argument
   0 (`object: arg0`, `guava-queues.yml`). The fixture's `Auditor` calls both (table 15).

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

### Identity, blocking queues (from the running JDK)

- `java.version`: `21.0.13.0.3`

### 12. What `BlockingQueue` declares

- public interface java.util.concurrent.BlockingQueue<E> extends java.util.Queue<E> {
- `BlockingQueue.put` `(Ljava/lang/Object;)V` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.offer` `(Ljava/lang/Object;)Z` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.offer` `(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.add` `(Ljava/lang/Object;)Z` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.take` `()Ljava/lang/Object;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.poll` `(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.drainTo` `(Ljava/util/Collection;)I` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.drainTo` `(Ljava/util/Collection;I)I` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `BlockingQueue.remove` `(Ljava/lang/Object;)Z` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `Queue.poll` `()Ljava/lang/Object;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT
- `Queue.remove` `()Ljava/lang/Object;` (0x0401) ACC_PUBLIC, ACC_ABSTRACT

### 13. The JDK's blocking-queue types

- public interface java.util.concurrent.BlockingDeque<E> extends java.util.concurrent.BlockingQueue<E>, java.util.Deque<E> {
- public interface java.util.concurrent.TransferQueue<E> extends java.util.concurrent.BlockingQueue<E> {
- public class java.util.concurrent.LinkedBlockingQueue<E> extends java.util.AbstractQueue<E> implements java.util.concurrent.BlockingQueue<E>, java.io.Serializable {
- public class java.util.concurrent.ArrayBlockingQueue<E> extends java.util.AbstractQueue<E> implements java.util.concurrent.BlockingQueue<E>, java.io.Serializable {
- public class java.util.concurrent.PriorityBlockingQueue<E> extends java.util.AbstractQueue<E> implements java.util.concurrent.BlockingQueue<E>, java.io.Serializable {
- public class java.util.concurrent.LinkedBlockingDeque<E> extends java.util.AbstractQueue<E> implements java.util.concurrent.BlockingDeque<E>, java.io.Serializable {
- public class java.util.concurrent.LinkedTransferQueue<E> extends java.util.AbstractQueue<E> implements java.util.concurrent.TransferQueue<E>, java.io.Serializable {
- public class java.util.concurrent.SynchronousQueue<E> extends java.util.AbstractQueue<E> implements java.util.concurrent.BlockingQueue<E>, java.io.Serializable {
- public class java.util.concurrent.DelayQueue<E extends java.util.concurrent.Delayed> extends java.util.AbstractQueue<E> implements java.util.concurrent.BlockingQueue<E> {

### 14. What javac writes for each declared call through each owner

- `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`
- `invokeinterface` `java/util/concurrent/BlockingDeque.put:(Ljava/lang/Object;)V`
- `invokeinterface` `java/util/concurrent/TransferQueue.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.put:(Ljava/lang/Object;)V`
- `invokevirtual` `java/util/concurrent/DelayQueue.put:(Ljava/util/concurrent/Delayed;)V`
- `invokeinterface` `java/util/concurrent/BlockingQueue.offer:(Ljava/lang/Object;)Z`
- `invokeinterface` `java/util/concurrent/BlockingQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokeinterface` `java/util/concurrent/BlockingDeque.offer:(Ljava/lang/Object;)Z`
- `invokeinterface` `java/util/concurrent/BlockingDeque.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokeinterface` `java/util/concurrent/TransferQueue.offer:(Ljava/lang/Object;)Z`
- `invokeinterface` `java/util/concurrent/TransferQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.offer:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.offer:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.offer:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.offer:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.offer:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.offer:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `invokevirtual` `java/util/concurrent/DelayQueue.offer:(Ljava/util/concurrent/Delayed;)Z`
- `invokevirtual` `java/util/concurrent/DelayQueue.offer:(Ljava/util/concurrent/Delayed;JLjava/util/concurrent/TimeUnit;)Z`
- `invokeinterface` `java/util/concurrent/BlockingQueue.add:(Ljava/lang/Object;)Z`
- `invokeinterface` `java/util/concurrent/BlockingDeque.add:(Ljava/lang/Object;)Z`
- `invokeinterface` `java/util/concurrent/TransferQueue.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.add:(Ljava/lang/Object;)Z`
- `invokevirtual` `java/util/concurrent/DelayQueue.add:(Ljava/util/concurrent/Delayed;)Z`
- `invokeinterface` `java/util/concurrent/BlockingQueue.take:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/BlockingDeque.take:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/TransferQueue.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.take:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/DelayQueue.take:()Ljava/util/concurrent/Delayed;`
- `invokeinterface` `java/util/concurrent/BlockingQueue.poll:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/BlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/BlockingDeque.poll:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/BlockingDeque.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/TransferQueue.poll:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/TransferQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.poll:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.poll:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.poll:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.poll:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.poll:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.poll:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/DelayQueue.poll:()Ljava/util/concurrent/Delayed;`
- `invokevirtual` `java/util/concurrent/DelayQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/util/concurrent/Delayed;`
- `invokeinterface` `java/util/concurrent/BlockingQueue.drainTo:(Ljava/util/Collection;)I`
- `invokeinterface` `java/util/concurrent/BlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokeinterface` `java/util/concurrent/BlockingDeque.drainTo:(Ljava/util/Collection;)I`
- `invokeinterface` `java/util/concurrent/BlockingDeque.drainTo:(Ljava/util/Collection;I)I`
- `invokeinterface` `java/util/concurrent/TransferQueue.drainTo:(Ljava/util/Collection;)I`
- `invokeinterface` `java/util/concurrent/TransferQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokevirtual` `java/util/concurrent/DelayQueue.drainTo:(Ljava/util/Collection;)I`
- `invokevirtual` `java/util/concurrent/DelayQueue.drainTo:(Ljava/util/Collection;I)I`
- `invokeinterface` `java/util/concurrent/BlockingQueue.remove:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/BlockingDeque.remove:()Ljava/lang/Object;`
- `invokeinterface` `java/util/concurrent/TransferQueue.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/ArrayBlockingQueue.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/PriorityBlockingQueue.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedBlockingDeque.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/LinkedTransferQueue.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/SynchronousQueue.remove:()Ljava/lang/Object;`
- `invokevirtual` `java/util/concurrent/DelayQueue.remove:()Ljava/util/concurrent/Delayed;`

### 15. What javac writes at the fixture's queue sites

- `Pipeline`: `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`
- `Pipeline`: `invokeinterface` `java/util/concurrent/BlockingQueue.offer:(Ljava/lang/Object;JLjava/util/concurrent/TimeUnit;)Z`
- `Pipeline`: `invokeinterface` `java/util/concurrent/BlockingQueue.offer:(Ljava/lang/Object;)Z`
- `Pipeline`: `invokeinterface` `java/util/concurrent/BlockingQueue.add:(Ljava/lang/Object;)Z`
- `Pipeline`: `invokeinterface` `java/util/concurrent/BlockingQueue.take:()Ljava/lang/Object;`
- `Pipeline`: `invokeinterface` `java/util/concurrent/BlockingQueue.poll:()Ljava/lang/Object;`
- `Worker`: `invokeinterface` `java/util/concurrent/BlockingQueue.take:()Ljava/lang/Object;`
- `Worker`: `invokeinterface` `java/util/concurrent/BlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `Alerts`: `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.put:(Ljava/lang/Object;)V`
- `Alerts`: `invokevirtual` `java/util/concurrent/LinkedBlockingQueue.take:()Ljava/lang/Object;`
- `Cleaner`: `invokeinterface` `java/util/concurrent/BlockingQueue.offer:(Ljava/lang/Object;)Z`
- `Cleaner`: `invokeinterface` `java/util/concurrent/BlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `Cleaner`: `invokestatic` `com/google/common/collect/Queues.newLinkedBlockingQueue:(I)Ljava/util/concurrent/LinkedBlockingQueue;`
- `Batch`: `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`
- `Batch`: `invokeinterface` `java/util/List.add:(Ljava/lang/Object;)Z`
- `Batch`: `invokeinterface` `java/util/concurrent/BlockingQueue.take:()Ljava/lang/Object;`
- `Relay`: `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`
- `Relay`: `invokeinterface` `java/util/concurrent/BlockingQueue.take:()Ljava/lang/Object;`
- `Scratch`: `invokeinterface` `java/util/Queue.offer:(Ljava/lang/Object;)Z`
- `Scratch`: `invokeinterface` `java/util/Queue.poll:()Ljava/lang/Object;`
- `Auditor`: `invokeinterface` `java/util/concurrent/BlockingQueue.offer:(Ljava/lang/Object;)Z`
- `Auditor`: `invokeinterface` `java/util/concurrent/BlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `Auditor`: `invokeinterface` `java/util/concurrent/BlockingQueue.drainTo:(Ljava/util/Collection;)I`
- `Auditor`: `invokestatic` `com/google/common/collect/Queues.drain:(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;IJLjava/util/concurrent/TimeUnit;)I`
- `Auditor`: `invokestatic` `com/google/common/collect/Queues.drainUninterruptibly:(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;IJLjava/util/concurrent/TimeUnit;)I`
- `Auditor`: `invokestatic` `com/google/common/collect/Queues.newLinkedBlockingQueue:(I)Ljava/util/concurrent/LinkedBlockingQueue;`
- `Mailbox`: `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`
- `Mailbox`: `invokeinterface` `java/util/concurrent/BlockingQueue.remove:()Ljava/lang/Object;`
- `Mailbox`: `invokeinterface` `java/util/concurrent/BlockingQueue.remove:(Ljava/lang/Object;)Z`
- `Outbox`: `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`
- `Outbox`: `invokeinterface` `java/util/concurrent/BlockingQueue.removeIf:(Ljava/util/function/Predicate;)Z`
- `Guarded`: `invokeinterface` `java/util/concurrent/BlockingQueue.take:()Ljava/lang/Object;`
- `Guarded`: `invokestatic` `java/util/Objects.requireNonNull:(Ljava/lang/Object;Ljava/lang/String;)Ljava/lang/Object;`
- `Dispatcher`: `invokeinterface` `java/util/concurrent/BlockingQueue.put:(Ljava/lang/Object;)V`

### Identity, Guava (from the jar's own MANIFEST.MF)

- `com.google.guava:guava`: `Bundle-Version: 32.0.0.jre`

### 16. Guava's drain helpers, and what they call on the queue

- `Queues.drain` `(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;ILjava/time/Duration;)I` (0x0009) ACC_PUBLIC, ACC_STATIC
- `Queues.drain` `(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;IJLjava/util/concurrent/TimeUnit;)I` (0x0009) ACC_PUBLIC, ACC_STATIC
- `Queues.drainUninterruptibly` `(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;ILjava/time/Duration;)I` (0x0009) ACC_PUBLIC, ACC_STATIC
- `Queues.drainUninterruptibly` `(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;IJLjava/util/concurrent/TimeUnit;)I` (0x0009) ACC_PUBLIC, ACC_STATIC
- `drain(…, long, TimeUnit)` calls `invokeinterface #34, 3 // InterfaceMethod java/util/concurrent/BlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `drain(…, long, TimeUnit)` calls `invokeinterface #35, 4 // InterfaceMethod java/util/concurrent/BlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `drain(…, Duration)` calls `invokestatic #30 // Method drain:(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;IJLjava/util/concurrent/TimeUnit;)I`
- `drainUninterruptibly(…, long, TimeUnit)` calls `invokeinterface #34, 3 // InterfaceMethod java/util/concurrent/BlockingQueue.drainTo:(Ljava/util/Collection;I)I`
- `drainUninterruptibly(…, long, TimeUnit)` calls `invokeinterface #35, 4 // InterfaceMethod java/util/concurrent/BlockingQueue.poll:(JLjava/util/concurrent/TimeUnit;)Ljava/lang/Object;`
- `drainUninterruptibly(…, Duration)` calls `invokestatic #37 // Method drainUninterruptibly:(Ljava/util/concurrent/BlockingQueue;Ljava/util/Collection;IJLjava/util/concurrent/TimeUnit;)I`
