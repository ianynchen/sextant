# In-process dispatch — design note

**Status: APPROVED 2026-11-05** ("Yes, but why kotlin later? We said we want to achieve Java and kotlin complete"): every JVM kind is built on this branch; only Go waits for a Go scanner. Amends the Akka/Pekko actors design
(`2026-11-04-akka-pekko-actors-design.md`, built on `cov/akka-actors`). The user ruled **A** on
2026-11-05: the catalog pieces built for actors (`message_handlers` style, `message_sends`,
`message_class_via`) were *"invented just for one framework"* and read too close to
messaging. Make them one general mechanism that reuses existing words, prove it with a
second framework, and take Go channels into account.

## 1. The one idea

**In-process dispatch:** code hands a value to a framework or a channel, and the framework
calls the handler(s) that receive it. No address goes on a wire. It is a trace **hop**, never
an endpoint row (the self-call ruling of 2026-10-25). It is not messaging: messaging names an
address a broker or bus routes on (Kafka topic, JMS queue, event-bus address) and keeps its
endpoint rows.

Two things decide which handler receives the value:

| Key | Who receives | Examples | In `examples/` (main code) |
|---|---|---|---|
| **type** — the value's class | handlers registered for that class | Akka/Pekko `tell` → `onMessage(C.class, h)`; Spring `publishEvent(e)` → `@EventListener m(E e)`; CDI `fire(e)` → `@Observes E` | Spring 21 send / 14 listen (apollo-portal, dolphinscheduler, yudao, petclinic-genai); CDI 30; Akka 83 |
| **object** — which channel object | code that receives from the same object | Kotlin `Channel.send` → `receive`/`for (x in ch)`; Java `BlockingQueue.put` → `take`; Go `ch <- v` → `<-ch` | Kotlin Channel 8, SharedFlow 39, BlockingQueue 8 (apollo, dolphinscheduler); Go: no project yet |

And one rule says how many receive:

| Match | Meaning | Who |
|---|---|---|
| `first` | the first registration in its group that matches | Akka/Pekko behaviors |
| `all` | every registration that matches | Spring, CDI listeners; a broadcast flow |
| `one` | exactly one receiver takes each value (any of them) | a queue/channel with several consumers: a hop to each, since which one takes it is decided at run time |

## 2. Catalog words — reuse first

| Need | Word | Reused from |
|---|---|---|
| Where a value is handed over | `dispatch_sends: [{owner, method, descriptor, value_arg}]` — a catalog block any style may carry (replaces `message_sends`/`message_arg`) | the per-entry owner/method/descriptor matching `declared_call_sites` already does; `value_arg` is `body_arg`'s position |
| A call-style registration (Akka) | `dispatch_registrations: [{owner, method, descriptor, class_arg \| value_arg, handler_arg, predicate_arg?, returns_value?}]` on an ordinary `fluent` chain (roots/steps/terminal, `case` capture) | `fluent` chains and `chain_ends`; `class_arg` is the existing name for a class literal |
| An annotation-style registration (Spring, CDI) | the `annotation_driven` style with three additions: select a method by a **parameter** annotation (`mapping.selected_by_parameter: [<annotation fqn>, …]`, built in Task 3: `@Observes`, keyed by that annotated parameter's type, wherever it sits); key = the payload parameter's type (`path_fallback: payload_type`); output = a dispatch registration, not an endpoint | `annotation_driven`, `request_body` (picks the parameter), `path_from` (reads `@EventListener(classes=…)`) |
| A registration made by implementing an interface (Spring `ApplicationListener<E>`; Micronaut's `ApplicationEventListener<E>` has the same shape) | `dispatch_implementations: [{owner, method, descriptor, value_arg}]` — each module type below the interface `owner` declaring the method registers it, keyed by its parameter at `value_arg` (added in Task 2, fix round 1 recorded it here) | the entry matching `dispatch_sends` uses; the bridge rule of the annotation inheritance walk (`effective_annotations._synthesis_target`, OI-47) |
| A receive site, object key | `dispatch_receives: [{owner, method, descriptor, object: receiver, handler: enclosing \| lambda_arg}]` | the same entry matching |
| How dispatch works for the catalog | `dispatch: { key: type \| object, match: first \| all \| one, mechanism: <name> }` — `mechanism` (Task 2 fix round 2) names the dispatch mechanism; a key catalog declares `{mechanism}` alone | — (the one genuinely new setting) |
| The class a key carries (Akka service key) | `channel_via` entries may also name `class_arg`, read from the same producing call in the same walk | `channel_via` (replaces `message_class_via` and its second walk) |

No `message_*` word remains. No word names a framework.

## 3. Tables

- `message_handlers` (graph schema 15, approved 2026-11-04) is renamed **`dispatch_registrations`**:
  `group` (was `behavior`), `position`, `key_type`, `key_value`, `predicated`, `handler`,
  `delivers`, `match`. Still one new table; schema stays 15 (not yet released).
- Hops stay in `rpc_hops`, renamed **`hops`** (it already has two writers: gRPC stubs and
  dispatch). `protocol` = the catalog's protocol (`grpc`, `actor`) or `in_process` for a
  catalog with none.
- `dispatch_registrations` also carries **`key_object`**: for an object key, the producing call
  `caller#ordinal` of the channel object, from `values.producer_paths(…, which_object=True)` (the
  object-following the Vert.x client reader already uses). NULL for a type key. Still schema 15.
- …and **`mechanism`** (Task 2 fix rounds 1-2): the dispatch mechanism the registration belongs
  to, the declaring catalog's `dispatch.mechanism` (`pekko-actors`, `akka-actors`,
  `spring-events`), declared in YAML and never derived: a key catalog (`pekko-receptionist`)
  declares `dispatch: {mechanism: pekko-actors}`, and the loader refuses a send or key
  catalog's mechanism no registering catalog names. A send reaches, and an inbound
  key is served by, only registrations of its own catalog's mechanism, so a module running two
  frameworks never has an actor `tell` land on an application-event listener of `Object`, or a
  published event on an actor case. The protocol cannot draw that line (Spring and CDI are both
  `in_process`), nor the catalog itself (a key's catalog is not the one registering its
  handlers). Still schema 15.

## 4. What changes in this branch

1. Rename the words, the table and the code (`message_handlers.py` → `dispatch_registrations.py`,
   `message_hops.py` → `dispatch_hops.py`), the docs (D01/D02, CHANGELOG, spec As-built).
2. Akka/Pekko catalogs re-expressed in the general words; their rows and hops must come out
   identical (the 33 checked on the Pekko samples, the fixture pins).
3. `channel_via` gains `class_arg`; `message_class_via` and its second walk go.
4. `reachable_handlers` gains `match: all` (and `one`).
5. **Spring application events.** `publishEvent(Object)` and `publishEvent(ApplicationEvent)` on
   `ApplicationEventPublisher` (and `ApplicationContext`, which inherits it) are sends;
   `@EventListener` and `@TransactionalEventListener` methods are registrations keyed by their
   parameter's type (or the annotation's `classes`), `match: all`. **`ApplicationListener<E>`
   implementations** are registrations keyed by the parameter type of their own
   `onApplicationEvent(E)` — the non-bridge method. A javac bridge carries no `bridge_of` (D00
   §5a writes it only on Kotlin's `$default` bridges and `DefaultImpls` bodies; CP-59 finding 5):
   it is found by `modifiers.synthetic` and carried to the method it forwards to by
   `effective_annotations._synthesis_target` (OI-47) — so no fact change is needed. Done when apollo-portal's and dolphinscheduler's publish sites
   hop to their listeners, each checked by hand, and the six field pins still pass (apollo-portal
   is one: any moved row is checked true or false).
   **Stated bound (review m5):** `publishEvent(pojo)` is wrapped by Spring in a
   `PayloadApplicationEvent`, so a listener of `ApplicationEvent` (or an
   `ApplicationListener<ApplicationEvent>`) receives it too. The hop pass matches the POJO's own
   ancestry, so those hops are missing: a missing hop, never a false one.
6. **CDI events (Quarkus).** `Event.fire`/`fireAsync` are sends; a method whose parameter carries
   `@Observes`/`@ObservesAsync` is a registration keyed by that parameter's type, `match: all`.
   Checked on the Quarkus examples. **As built (Task 3):** two catalogs, two mechanisms —
   `cdi-events` (`@Observes`, `fire`; Jakarta and javax) and `cdi-async-events`
   (`@ObservesAsync`, both `fireAsync` overloads; Jakarta and javax CDI 2.x, javax CDI 1.x has
   neither) —
   because ArC's `fire` notifies only synchronous observers and `fireAsync` only asynchronous
   ones (CP-59 finding 10). No example under `examples/` fires a CDI event (every observer there
   observes a framework event), so the Quarkus check covers registrations only; the hops are
   pinned on `fixtures/orders-cdi-events`. **Fix round 1 (review M1, m2; the user's rule: a
   wrong value is a lie, worse than unknown):** an observer whose event parameter also carries
   a qualifier (an annotation meta-annotated by one of the CDI bean model's
   `qualifier_meta_annotations`: `jakarta.inject.Qualifier`, `javax.inject.Qualifier`; final
   wave ruling 15 moved the word there from the catalogs), or whose observed type carries type
   arguments or is a type variable, keeps its registration with no key — a missing hop, never a false one. Reading the
   fire sites' qualifiers (receiver to field, `select(…)`) is deferred until a corpus has a fire
   site.
7. **Object keys: Kotlin `Channel`, Kotlin `SharedFlow`/`StateFlow`, Java `BlockingQueue`.**
   Sends: `send`/`trySend`, `emit`/`tryEmit`/`value =`, `put`/`offer`/`add`. Receives: `receive`/
   `tryReceive`/`for (x in ch)` (an `iterator()` call), `collect`, `take`/`poll`. A send hops to
   every receive site on the same object: `match: one` for a channel or queue (one consumer takes
   each value, decided at run time, so a hop to each), `all` for a shared flow. Checked on the
   koog/kotlinconf and apollo/dolphinscheduler examples.
   **As built (Task 4, Java blocking queues):** `jdk-blocking-queue.yml` (CP-59 findings 12-15).
   A receive site's key is the call that MADE the object its receiver reaches
   (`dispatch_registrations.ObjectKeys`, the value walk's object reader with `which_object`):
   a construction (the module's or a library's) or a call whose body is not here
   (`ValueIndex.unscanned`, the unseen-object rule's producers — Guava's
   `Queues.newLinkedBlockingQueue`, which makes all four of apollo's queues). A path ending
   anywhere else (a parameter nothing calls, an injected object) is `(key not read)`: a send's
   stop row, a receive's keyless row (but past a declared null check whose every path ends so,
   the check's own call is the key: final wave ruling 17). javac writes the receiver's static type as the owner of
   every call, so all ten JDK blocking-queue types are listed (`Dispatch.heirs` does not reach a
   JDK class that declares the method). The loader refuses `dispatch_receives` under `key: type`
   and a class-keyed block under `key: object`; a receive's `handler: lambda_arg` is refused
   where read until a catalog needs it (Task 5). A trace's unread hop now reads `(key not
   read)` for both key kinds. **Fix round 1:** `drainTo` (both) and `remove()` are receives on
   every owner; Guava's `Queues.drain`/`drainUninterruptibly` are receives of the queue at
   argument 0, a new `object: argN` form of the receive word (`guava-queues.yml`, the same
   mechanism); `remove(Object)` and `removeIf` discard values nothing handles and are not
   receives (ruled 2026-11-05). A declared null check returning its argument's type
   (`Objects.requireNonNull`, a `not_hand_offs` call) is passed through by the object walk.
   **Stated bounds:** the key has three stated bounds, each over-linking (two queues read as one, never one missed): a field read is answered by every write of that field, so two instances of one class each holding a queue in it are one object; two objects one module helper makes (`newQueue()` called twice) are one; and two objects one library call site hands back are one. A null check no catalog declares (Guava's `Preconditions.checkNotNull`) splits one queue into two keys instead, a missing hop. `peek`, the deque ends and `Queue`-typed
   receivers are not read (missing hops, never false ones).
   **As built (Task 5, Kotlin channels and flows):** `kotlinx-channels.yml` (`match: one`) and
   `kotlinx-flows.yml` (`match: all`), CP-59 findings 17-21 (kotlinx-coroutines 1.11.0, kotlinc
   2.4.20). kotlinc writes the receiver's static type as the owner and an inline-class result
   under its mangled JVM name (`trySend-JP2dKIU`), so `Channel`, `SendChannel`, `ProducerScope` and
   `ReceiveChannel` are each listed; `for (x in ch)` and the inlined `consumeEach` are an
   `iterator()` call on the channel; `value =` is `setValue` and `update { }` inlines to
   `compareAndSet`. The object walk needed no coroutine-specific rule: a send in a launched block's
   `invokeSuspend` reads the channel through `this$0` and the field's synthetic accessor, both
   followed already (a field read answers every write of the field), and a captured local is the
   lambda's `$ch` field, written by its constructor. Two general fixes: a path that comes back to
   where it started (the lambda's `create` copying `this.$ch`) adds no object instead of being read
   as "not read"; and kotlinc 2.4's `nullOutSpilledVariable` (body `aconst_null; areturn`) joins
   `not_hand_offs` as a compiler call that cannot change its value (an instance of the 2026-11-02
   ruling), passed through rather than named as the channel's maker. **`handler: lambda_arg` is
   built** for `collect { }`: the lambda is a module class implementing `FlowCollector` (finding
   20; not one of kotlinc's lambda base classes, so it carries no `lambda_body`), so a receive
   names the argument (`handler_arg`) and the method the library calls on it (`handler_method`,
   `handler_descriptor`), and the handler is that method on the argument's class, past the
   compiler's bridge. **Fix round 1 (rulings 1-2):** a call handing back a view of the same
   object is declared as catalog data (`dispatch_views: [{owner, method, descriptor, object}]`;
   `returns_receiver` is a chain-step word the object walk never reads, so it could not be
   reused) and passed through by `ObjectKeys`: `asSharedFlow`, `asStateFlow`, `receiveAsFlow`,
   `consumeAsFlow` (finding 22). The terminal receives `first`, `firstOrNull`, `single`, `toList`
   (enclosing) and `collectLatest` (`lambda_arg`, its block a compiled lambda read as its body)
   are declared (finding 23). The two catalogs share one mechanism, `kotlinx-coroutines`, because
   a channel read as a flow is collected by the flows catalog's receives. **Stated bounds:** a
   flow made by an operator (`map`, `filter`, `onEach`) is the operator's result, another key;
   `launchIn` and other terminal operators are not receives; a channel in a local or
   parameter of a `suspend` function used after a suspension point is a receiver the facts do not
   name (merged with its spilled slot), so its send is a stop (each a missing hop, never a false
   one). A data class's generated `copy(channel)` is a second writer of its field from a parameter
   nothing calls, so a send through such a property also keeps one `(key not read)` stop beside its
   hops (the established one-stop-per-unread-path rule).

## 5. Later

- **Go channels**, when the Go scanner lands: same tables, `key: object`.
- **Vert.x event-bus local consumers** keep their endpoint rows (they have an address); a send to
  an address the module consumes becomes a hop by the existing self-call rule.

## 6. Cost

Same as built: one chain walk per registration catalog, one value read per send. Spring and CDI
add one annotation pass each (the one `annotation_driven` already runs per catalog). Object keys
add one cached object walk per send and receive site, then a dictionary join on the producer.

## As built

Built 2026-11-05 on `cov/akka-actors` in five tasks (plan
`docs/superpowers/plans/2026-11-05-in-process-dispatch.md`), commits `0c83290b`..`aad0804f`,
this section the sixth. §1-§4 above carry each task's detail where the task changed the design;
this section is the one place to read what was ruled, what is new beyond §2, what the corpus
said, and what the mechanism does not do.

### Rulings made during the build

Each was the controller's, under the user's ruling A, and was recorded with its cost if wrong.

1. **`Protocol.IN_PROCESS` (`in_process`) arrives in Task 2**, where the first catalog with no
   wire protocol (Spring events) needs it; §3 names it. Cost if wrong: none.
2. **The registration reader stays its own pass**: a plain `fluent` catalog carries the
   registrations block and the endpoint loop skips it whole, so resets and detection behave as
   before. Cost if wrong: one more pass name in the pipeline list.
3. **The probe is CP-59**, not CP-58 (taken by `cp58-inherited-mappings`). Cost: none.
4. **A listener from a sibling module on the classpath counts as a registration**: at run time
   it is in the same JVM and receives the event. Cost if wrong: a hop to a listener not
   deployed with this module.
5. **Dispatch never crosses mechanisms, fixed now** although no analysed module mixes Spring
   and Akka: a crossing is a false hop, and the fix is one column in the unreleased schema 15.
   Cost: one fix round.
6. **`dispatch_implementations` is kept** (listed for the user's sign-off): it is general, and
   `interface_implementation` needs a registration call and mints endpoint rows. Cost if wrong:
   one block word to retire.
7. **`mechanism` is an explicit key on the `dispatch` setting**, required on every dispatch
   catalog and checked at load. A naming convention read off the catalog id would be hidden and
   unchecked, and would silently merge or split mechanisms (false or missing hops). Cost: one
   key inside an approved setting.
8. **A qualified or parameterized CDI observer is kept keyless**: a false hop is a lie, and
   the rule turns it into a missing hop with no row dropped. Cost if wrong: `@Observes @Any`
   loses its hop.
9. **`drainTo`, `remove()` and Guava's `Queues.drain` are receives; `removeIf` is not.**
   `removeIf` discards matching values and nothing handles them, so a hop would claim a handler.
   Cost if wrong: one missing hop class. The last is declared through `object: argN`, a
   generalisation of `object: receiver`.
10. **The Gradle Kotlin-only analysis gap found in Task 5 is OI-273**, fixed on open PR #90
    (this branch predates it); no new issue.
11. **Identity views keep the object's key and terminal flow receives are declared**:
    `asSharedFlow`, `asStateFlow`, `receiveAsFlow`, `consumeAsFlow`; `first`, `firstOrNull`,
    `single`, `collectLatest`, `toList`. `asSharedFlow` is the commonest Kotlin flow idiom and
    leaving it gives missing hops for real code. Derived flows (`map`, `filter`) stay a stated
    bound. Cost: one fix round.
12. **`nullOutSpilledVariable` joins `compiler-null-checks`** (an instance of the 2026-11-02
    ruling; no endpoint row moved), and `ProducerScope`, `receiveCatching` and
    `compareAndSet` are owners/receives/sends.
13. **One Kotlin mechanism, `kotlinx-coroutines`, and the `dispatch_views` word.** The object
    key keeps channels and flows apart; views serve Reactor, RxJava and JDK wrappers too.
    Cost: none observed.

Rulings of the final review's fix wave (2026-11-05, the controller's, under ruling A):

14. **A sent value no instance names is read by its declared type** (final review I-1:
    ruoyi-vue-pro builds every event as `new E().setA(..)`, an instance call's result): a call's
    declared return type (its descriptor), a parameter's or an instance field's declared type.
    **Corrected by the re-review (2026-11-05):** the hops written, to registrations of the
    type or a supertype, are exact under every `match`; but the declared type does not say
    whether a subtype's registration also runs, so where any registration of the mechanism
    names a strict subtype, the send ALSO writes the not-read row (`(key not read)`), never a
    stop naming the type with no handler, which would say nobody handles it
    (`publish(DomainEvent e)` with only implementations' listeners; `for (Object e : events)`).
    Under `first` a group is not read where a case before its first certain case may take a
    subtype: a strict subtype, or a type unrelated to the declared one unless both are known
    classes, or a value case whose constant's class is not such a class (`[Loggable, Command]`
    with a `Command` that is also `Loggable`). The first build applied the strict-subtype test
    whatever the case's position; a case after the first certain one is never reached, so
    position now counts. Finality is not read (a final declared type is treated as
    subclassable). Cost if wrong: a declared-type send's hops are incomplete, which the
    not-read row says.
15. **Qualifier-ness comes from the DI bean model** (final review I-2): `bean-models/cdi.yml`
    declares `qualifier_meta_annotations`, the CDI catalogs name it, and the catalog word
    `mapping.keyless_when_meta_annotated` is gone. Cost: one indirection.
16. **A type-variable or parameterized registration parameter is keyless for every
    registration kind** (final review m-1), as CDI's already was: a false hop is a lie. Cost: a
    generic base class's listeners get no hop.
17. **A null check over an object not read keeps its own key** (deferred minor, final wave):
    where every path past it ends at an object not read, the check's call is the key.

### Words beyond §2

The design's table named five words and one setting. What was built adds these, each general
(no word names a framework) and each documented in D02 §2m:

| Word | Why it was needed |
|---|---|
| `dispatch_implementations` | a registration made by implementing an interface (`ApplicationListener<E>`), keyed by its method's parameter (ruling 6) |
| `dispatch_views` | a call handing back the same object under another type, passed through by the object walk (ruling 13) |
| `qualifier_meta_annotations` (a DI bean model key, D02 §1c, not a catalog word) | the qualifier marker: an observer whose event parameter carries an annotation meta-annotated by it is kept with no key (ruling 8). Built first as the catalog word `mapping.keyless_when_meta_annotated`; moved to `bean-models/cdi.yml` by ruling 15 |
| `mapping.selected_by_parameter` | selects a method by a PARAMETER annotation (`@Observes`), keyed by that parameter's type |
| `dispatch: {mechanism}` | which registrations serve which sends (ruling 7); a key catalog declares it alone |
| `object: argN` | a receive of the object at argument N (Guava's `Queues.drain`), beside `object: receiver` (ruling 9) |
| `handler_arg`, `handler_method`, `handler_descriptor` | a receive hands its value to the function it is given (`collect { }`); `handler_arg` and `handler_method` are existing words of D02, only `handler_descriptor` is new |

Also beyond §2: **one Kotlin mechanism** where the first plan had a mechanism per file (ruling
13); the probe is **CP-59**, not CP-58 (ruling 3); a static module factory's result is read
through the factory's returns (apollo-portal's `ConfigPublishEvent.instance()`, seven of its
seventeen sends); `type-models/conformance.yml` declares the root type every class conforms to
so a listener of `Object` receives every event.

### The corpus

Every row and hop was read against the source by hand; the working record is
`.superpowers/sdd/2026-11-05-in-process-dispatch/corpus.md` (not in the repository). Each
module was analysed before and after each task and compared column for column.

| Kind | Where measured | True | False | Missing |
|---|---|---|---|---|
| Akka / Pekko | `pekko-sample-sharding-java/killrweather`, `pekko-sample-cluster-java` | 5 rows, 28 hops, 23 registrations, identical before and after | 0 | 0 |
| Spring application events | apollo-portal; ruoyi-vue-pro `yudao-module-system` (final wave) | apollo-portal 17 hops, one per publish site; yudao 3 publish sites: 2 hops and 1 stop naming its class (its listener is in `yudao-module-im`) | 0 | 0 (yudao's 3 were `(key not read)` before ruling 14) |
| CDI events | `stork-quickstart`, `reactive-routes-quickstart` | 5 of 5 registrations; **no fire site exists in `examples/`**, so the hops are pinned on `fixtures/orders-cdi-events` only | 0 | not measurable |
| Java blocking queues | apollo-biz, apollo-configservice, apollo-portal, dolphinscheduler-alert-server, dolphinscheduler-task-executor | 10 | 0 | 0 (5 found missing at the first count, fixed in fix round 1) |
| Kotlin channels and flows | playport/server, kotlinconf-app/backend | 7 (6 and 1) | 0 | 0 (1 found missing at the first count, fixed) |

No endpoint row moved on any module, and `scripts/field_check.py` read all six pins ok after
every task. **Not measured:** koog (its build needs a JDK 17 toolchain and Android targets),
ktor-samples `chat` and `reverse-proxy-ws` (Kotlin Multiplatform, no build; by reading, the
first sends on Ktor sessions that no catalog declares and the second only passes channels
through parameters, so a stop).

### Stated bounds

Each over-reports nothing: the result is a missing hop or a stop that says why, never a false
hop, except the three over-linking object-key bounds, which merge two objects into one.

- **Spring:** `publishEvent(pojo)` is wrapped in a `PayloadApplicationEvent`, so a listener of
  `ApplicationEvent` also receives it; those hops are missing (review m5). A generic listener
  parameter (`Base<E> implements ApplicationListener<E>`, `@EventListener on(T e)`,
  `on(Envelope<X> e)`) is kept with no key (ruling 16), so it gets no hop; a value read by its
  declared type (ruling 14: a parameter, a field, an instance call's result, a static factory
  called through a subclass) reaches the listeners of that type and its supertypes only, and
  writes the not-read row beside them where a subtype has a listener.
- **CDI:** the fire sites' qualifiers and type arguments are not read, so a qualified,
  parameterized or type-variable observer has a registration and no hop; `BeanManager.fireEvent` is not
  declared; `@Observes` and `@ObservesAsync` on one catalog's parameters would register twice
  (no catalog does).
- **Queues:** a field read is answered by every write of that field (two instances of one class
  holding a queue are one object); two queues one module helper makes are one; two objects one
  library call site hands back are one. A null check no catalog declares (Guava's
  `Preconditions.checkNotNull`) splits one queue into two keys instead, a missing hop. `peek`,
  the deque ends and `Queue`-typed receivers are not read. A declared null check over an
  object not read (an injected queue) is keyed by the check's own call (ruling 17), so the two
  sides still meet.
- **Kotlin:** a flow made by an operator (`map`, `filter`, `onEach`) is another key; `launchIn`
  and other terminal operators are not receives; a channel in a local of a `suspend` function
  used after a suspension point is a receiver the facts do not name, so its send is a stop; a
  data class's generated `copy(channel)` writes its field from a parameter nothing calls, so a
  send through the property keeps one `(key not read)` stop beside its hops. A `collect` lambda
  compiled by javac to an indy lambda (not a kotlinc class) has no handler read. Views are
  scoped per catalog, not per mechanism.
- **Every kind:** a class key no `new`, constant or module factory names is read by its
  declared type (ruling 14): its certain hops, plus the not-read row where a subtype's
  registration may also take it or, under `first`, an earlier case may; a key still not read
  (an array element, an injected object) is a stop that says so, `(key not read)`, never a fan-out. One class named by `class_arg` anywhere in a catalog makes all
  its inbound rows key rows (D02, `channel_via`).

### Deferred

Minor, from the task reviews, none produced by a real input: `test_source_rules` scans table
names by token position; `_payload_type` calls the private `_body_parameter` with placeholder
arguments; `_Reading` takes `catalogs[0].type_model`; `_registers` repeats the
`annotation_driven`/`key` condition that `endpoints.py` also holds; the `nullOutSpilledVariable`
entry was re-checked on two Kotlin modules only; the `receiveAsFlow` collector row is labelled
`match: all` (informational for an object key). Two for the log (OI): the generic-base-class
listener (now keyless by ruling 16: a missing hop, no longer a false one) and the static factory
called through a subclass (now read by its declared return type by ruling 14). Final wave, not
done: a `lambda_arg` receive whose handler is not read writes the same hop row as an object no
receive takes from (final review m-10): the registration row says which, the trace text does
not.
