# CP-57 — Akka 2.6.21 and Pekko 1.1.3 actor API shapes, measured

**Version scope.** Akka **2.6.21** (`com.typesafe.akka`, `_2.13`: `akka-actor`, `akka-actor-typed`,
`akka-cluster-typed`, `akka-cluster-sharding-typed`, `akka-cluster-tools`, `akka-persistence-typed`) and
Pekko **1.1.3** (`org.apache.pekko`, `_2.13`: the same six). Both resolved from Maven Central; the versions are
the ones the plan asked for, so no fallback was needed. These are the shapes of those releases; 2.6.x
other than 2.6.21, Akka 2.7+ (a different licence, not read) and Pekko 1.0.x or 1.2+ are free to change any
of them. The probe module is compiled by javac 21 (`--release 21`).

**Why it was measured.** The Akka and Pekko actors design (spec 2026-11-04, §3a-§3d) rests on facts about the
libraries' own bytecode: which builder methods answer their receiver (so a chain is read as one behavior),
which methods take a message class, a predicate and a handler, and what javac writes for `replyTo -> new
Query(.., replyTo)`. The catalogs cite this record instead of guessing.

**What this probe does not settle.** It reads bytecode; no actor system runs. "returns `this`" is read as: the
`areturn` is preceded (through an optional `checkcast`) by `aload_0`, or by a call, on the same class, of a method
that itself returns `this`. "new/other" is anything else (a new builder, a built value, a call outside the class).
"abstract" is an interface method with no body. Scala-compiled classes show Scala bookkeeping in their bytecode;
only the `areturn` is read.

Reproduce: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 scripts/probes/cp57_actors/run.sh` (rebuilds both fixtures,
compiles `TwoReturns.java`, prints every table below). Notation: `P.` = `org.apache.pekko.`, `~` inside a
descriptor = `org/apache/pekko`; Akka's rows are the same with `akka.` / `akka`.

## Findings (the facts the catalogs and Tasks 2-5 use)

1. **Two builders, two behaviours.** `Behaviors.receive(Class)` returns `javadsl.BehaviorBuilder`: **immutable**, every
   `onMessage` / `onMessageEquals` returns a **new** `BehaviorBuilder` (`new BehaviorBuilder(cases.+:(case), ..)`).
   `AbstractBehavior.newReceiveBuilder()` returns `javadsl.ReceiveBuilder`: **mutable**, every `onMessage` and
   `onMessageEquals` returns **`this`** (the cases are appended to the builder's own list; `onMessageEquals` returns
   the result of its private `withMessage`, which returns `this`). So the immutable builder must be read as a
   chain (spec §3d.1); the mutable one is `returns_receiver`.
2. **Persistence.** `CommandHandlerBuilder.forAnyState()` / `forState(Predicate)` / `forStateType(Class)` each return a
   **new** `CommandHandlerBuilderByState`; `CommandHandlerBuilderByState.onCommand` (every overload) returns **`this`**.
   So two `forState` calls on one builder are two behaviors, and `onCommand` steps on one `ByState` are one.
3. **The 3-argument `onCommand(Class, Predicate, handler)` does not exist** in either family. The overloads are:
   `onCommand(Class, BiFunction)` (arg 0 class, arg 1 handler `(state, cmd) -> Effect`), `onCommand(Class, Function)`
   (handler `cmd -> Effect`), `onCommand(Class, Supplier)` (handler `() -> Effect`), plus the predicate-first
   `onCommand(Predicate, BiFunction)` / `onCommand(Predicate, Function)` (a predicate on the command, no class).
   The brief's `onCommand` "3 args" row is therefore absent; the plan's `predicate_arg` for `onCommand` has nothing to
   declare. `onMessage(Class, Predicate, Function)` (typed `BehaviorBuilder` and `ReceiveBuilder`) does exist.
   `onCommandEquals` is absent too. The fixture's `Orders` therefore has no predicated `onCommand`.
4. **Classic `japi.pf.ReceiveBuilder`** (`AbstractActor.receiveBuilder()`): `match`, `matchEquals`, `matchAny` all
   return **`this`** (directly, or through a same-class call); `match(Class, UnitApply)` and
   `match(Class, TypedPredicate, UnitApply)` exist.
5. **`RecipientRef.ask` does not exist.** `ask` on an entity is `EntityRef.ask(Function, Duration)`; the
   actor-level typed ask is the static `javadsl.AskPattern.ask(RecipientRef, Function, Duration, Scheduler)`.
   `RecipientRef` and `ActorRef` (typed) declare only `tell(Object)`; `EntityRef` too.
6. **Sends.** typed `ActorRef.tell(Object)`; `EntityRef.tell(Object)` and `.ask(Function, Duration)`; classic
   `ActorRef.tell(Object, ActorRef)`; `ActorContext.ask(Class, RecipientRef, Duration, Function, Function2)` — arg 3
   is the message-building lambda, arg 4 the reply mapper; `messageAdapter(Class, Function)`;
   `pipeToSelf(CompletionStage, Function2)`.
7. **Timers.** `TimerScheduler.startTimerWithFixedDelay(Object key, Object msg, Duration)` and the key-less
   `(Object msg, Duration)` default method; likewise `startTimerAtFixedRate`; `startSingleTimer(Object msg, Duration)`
   and `(key, msg, Duration)`. In the key-less form the message is **arg 0**; in the keyed form it is **arg 1**.
   `startPeriodicTimer` exists only keyed (deprecated). `Scheduler.scheduleOnce`: typed `(Duration, Runnable,
   ExecutionContext)` (no actor, no message); classic `(Duration, ActorRef, Object, ExecutionContext, ActorRef)`
   — receiver arg 1, message arg 2.
8. **Keys.** `ServiceKey.create(Class, String)`, `EntityTypeKey.create(Class, String)`,
   `Entity.of(EntityTypeKey, Function)` are static factories (a new object); `ClusterSharding.init(Entity)` and
   `entityRefFor(EntityTypeKey, String)` are interface methods; `Receptionist.register(ServiceKey, ActorRef)`
   (and the 3-arg form with a reply-to), `subscribe(ServiceKey, ActorRef)`, `find(ServiceKey, ActorRef)` are static
   factories returning a `Receptionist.Command` that is then `tell`-ed to `system.receptionist()`.
9. **Classic pub-sub** constructors (Scala case classes): `Publish(String, Object)` / `(String, Object, boolean)`,
   `Subscribe(String, ActorRef)` / `(String, Option, ActorRef)` / `(String, String, ActorRef)`, `Send(String, Object,
   boolean)` / `(String, Object)`, `Put(ActorRef)`. They are `tell`-ed to the mediator, classic `tell(Object, ActorRef)`.
10. **Akka and Pekko agree.** Every descriptor is identical after the package prefix. The only differences are in
    how the classifier reads Akka's bytecode: `BehaviorBuilder.onMessage` / `onMessageEquals` and `AbstractActor.getSender`
    reach their `new` through a same-class call in 2.6.21 (still a new immutable builder), and Akka's mutable
    `ReceiveBuilder.onMessage` reaches `this` through a same-class call. No verdict differs.

## How javac compiles the lambdas (Pekko build; Akka's differs only in package names)

- `replyTo -> new OrderEntity.Get(id, replyTo)` passed to `EntityRef.ask` compiles to a **synthetic static method**
  `lambda$summary$<hash>$1(String id, ActorRef replyTo)` returning `OrderEntity$Command` (the lambda's *erased
  target type*, not the class it builds) whose body is `new OrderEntity$Get; invokespecial <init>; areturn`. The
  send site holds `invokedynamic apply(String)Function` capturing `id`. The class of the message is the `new` inside
  the lambda body, never its return type.
- `context.ask(Stock.Reply.class, stock, timeout, r -> new Stock.Reserve(..), (res, ex) -> ..)`: arg 3 compiles to
  `lambda$onStart$<hash>$1(Start captured, ActorRef r) -> Stock$Command` with one `new Stock$Reserve`; arg 4 to
  a second synthetic `(Stock$Reply, Throwable) -> Frontend$Command` (hash-named; the `pipeToSelf` mapper is another).
- The ternary mapper `res != null ? new Reserved(res) : new Failed(ex)` compiles to **one `areturn`** with **two
  `new`s** (javac joins the branches). A block mapper with two `return` statements (`TwoReturns`, measured below)
  compiles to **two `areturn`s**, each preceded by its own `new`. Both forms: every `new` in the body that feeds an
  `areturn` is a message class.
- `messageAdapter(Receptionist.Listing.class, l -> new Workers(l))` compiles to `lambda$new$<hash>$1(Listing)
  -> Frontend$Command`, one `new Frontend$Workers`.
- `pipeToSelf(stage, (body, ex) -> new Loaded(body))` compiles to `lambda$onStart$<hash>$N(String, Throwable) ->
  Frontend$Command`, one `new`.
- `Stock.Tick.INSTANCE` at the timer and at `onMessageEquals` is `getstatic Stock$Tick.INSTANCE`, a field of the enum.
  `onMessageEquals(Tick.INSTANCE, Stock::onTick)` passes the constant then an `invokedynamic create()Creator`.
- The predicate `p -> p.urgent()` compiles to `lambda$behavior$<hash>$1(Stock$Release) -> boolean`.
- A handler method reference `Stock::onReserve` compiles to an `invokedynamic` whose bootstrap names the method
  directly (no synthetic method); a lambda `message -> onGet(orderId, message)` compiles to a synthetic method that
  calls `onGet`.
- `Relay.forward(Object msg, ActorRef<Object> to)` is one `invokeinterface ActorRef.tell(Object)V` whose argument
  is the parameter: no `new`, no constant.

## Observations

Verbatim from the table `scripts/probes/cp57_actors/run.sh` generates (its `probe.py` runs `javap -c -p -s` on each
class and classifies every `areturn`); the rows below are that output with the two families laid side by side, and
nothing in the cells is typed by hand. The `1.1.3` column is Pekko and the `2.6.21` column is Akka. The column headers are the versions each family's jars REPORTED in their
own `META-INF/MANIFEST.MF` `Implementation-Version` (read for all six artifacts of each family: every one of the
twelve states `1.1.3` or `2.6.21`), not the version the fixtures' `pom.xml` asked for. The jars are the ones
`fixtures/orders-actors-pekko` and `fixtures/orders-actors-akka` resolve, and `run.sh` rebuilds both with `clean`
before it reads them, so no cell can come from a stale build. Descriptors are shown with the package prefix
(`org/apache/pekko` or `akka`) written `~`; they are identical in both columns. "(via call)" means the `areturn` is
the result of a call on the same class whose own result is that verdict.

| owner.method descriptor | 1.1.3 | 2.6.21 |
|---|---|---|
| `actor.typed.javadsl.BehaviorBuilder.onMessage` `(Ljava/lang/Class;L~/japi/function/Function;)L~/actor/typed/javadsl/BehaviorBuilder;` | new/other | via call: new/other |
| `actor.typed.javadsl.BehaviorBuilder.onMessage` `(Ljava/lang/Class;L~/japi/function/Predicate;L~/japi/function/Function;)L~/actor/typed/javadsl/BehaviorBuilder;` | new/other | via call: new/other |
| `actor.typed.javadsl.BehaviorBuilder.onMessageEquals` `(Ljava/lang/Object;L~/japi/function/Creator;)L~/actor/typed/javadsl/BehaviorBuilder;` | new/other | via call: new/other |
| `actor.typed.javadsl.BehaviorBuilder.build` `()L~/actor/typed/Behavior;` | new/other | new/other |
| `actor.typed.javadsl.ReceiveBuilder.onMessage` `(Ljava/lang/Class;L~/japi/function/Function;)L~/actor/typed/javadsl/ReceiveBuilder;` | this | this (via call) |
| `actor.typed.javadsl.ReceiveBuilder.onMessage` `(Ljava/lang/Class;L~/japi/function/Predicate;L~/japi/function/Function;)L~/actor/typed/javadsl/ReceiveBuilder;` | this | this (via call) |
| `actor.typed.javadsl.ReceiveBuilder.onMessageEquals` `(Ljava/lang/Object;L~/japi/function/Creator;)L~/actor/typed/javadsl/ReceiveBuilder;` | this (via call) | this (via call) |
| `actor.typed.javadsl.ReceiveBuilder.build` `()L~/actor/typed/javadsl/Receive;` | new/other | new/other |
| `actor.typed.javadsl.Behaviors.receive` `(Ljava/lang/Class;)L~/actor/typed/javadsl/BehaviorBuilder;` | new/other | new/other |
| `actor.typed.javadsl.Behaviors.receive` `(L~/japi/function/Function2;L~/japi/function/Function2;)L~/actor/typed/Behavior;` | new/other | new/other |
| `actor.typed.javadsl.Behaviors.receive` `(L~/japi/function/Function2;)L~/actor/typed/Behavior;` | new/other | new/other |
| `actor.typed.javadsl.Behaviors.receiveMessage` `(L~/japi/Function;)L~/actor/typed/Behavior;` | new/other | new/other |
| `actor.typed.javadsl.Behaviors.setup` `(L~/japi/function/Function;)L~/actor/typed/Behavior;` | new/other | new/other |
| `actor.typed.javadsl.Behaviors.withTimers` `(L~/japi/function/Function;)L~/actor/typed/Behavior;` | new/other | new/other |
| `actor.typed.javadsl.AbstractBehavior.newReceiveBuilder` `()L~/actor/typed/javadsl/ReceiveBuilder;` | new/other | new/other |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onCommand` `(Ljava/util/function/Predicate;Ljava/util/function/BiFunction;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | this | this |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onCommand` `(Ljava/util/function/Predicate;Ljava/util/function/Function;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | this | this |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onCommand` `(Ljava/lang/Class;Ljava/util/function/BiFunction;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | this | this |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onCommand` `(Ljava/lang/Class;Ljava/util/function/Function;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | this (via call) | this (via call) |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onCommand` `(Ljava/lang/Class;Ljava/util/function/Supplier;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | this (via call) | this (via call) |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onAnyCommand` `(Ljava/util/function/BiFunction;)L~/persistence/typed/javadsl/CommandHandler;` | via call: new/other | via call: new/other |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onAnyCommand` `(Ljava/util/function/Function;)L~/persistence/typed/javadsl/CommandHandler;` | via call: new/other | via call: new/other |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onAnyCommand` `(Ljava/util/function/Supplier;)L~/persistence/typed/javadsl/CommandHandler;` | via call: new/other | via call: new/other |
| `persistence.typed.javadsl.CommandHandlerBuilderByState.onCommandEquals` `-` | NOT FOUND | NOT FOUND |
| `persistence.typed.javadsl.CommandHandlerBuilder.forAnyState` `()L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | new/other | new/other |
| `persistence.typed.javadsl.CommandHandlerBuilder.forState` `(Ljava/util/function/Predicate;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | new/other | new/other |
| `persistence.typed.javadsl.CommandHandlerBuilder.forState` `(Ljava/lang/Class;Ljava/util/function/Predicate;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | new/other | new/other |
| `persistence.typed.javadsl.CommandHandlerBuilder.forStateType` `(Ljava/lang/Class;)L~/persistence/typed/javadsl/CommandHandlerBuilderByState;` | new/other | new/other |
| `persistence.typed.javadsl.CommandHandlerBuilder.build` `()L~/persistence/typed/javadsl/CommandHandler;` | new/other | new/other |
| `japi.pf.ReceiveBuilder.match` `(Ljava/lang/Class;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this (via call) | this (via call) |
| `japi.pf.ReceiveBuilder.match` `(Ljava/lang/Class;L~/japi/pf/FI$TypedPredicate;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this (via call) | this (via call) |
| `japi.pf.ReceiveBuilder.match` `(Ljava/lang/Class;Ljava/util/function/BooleanSupplier;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this (via call) | this (via call) |
| `japi.pf.ReceiveBuilder.matchEquals` `(Ljava/lang/Object;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this | this |
| `japi.pf.ReceiveBuilder.matchEquals` `(Ljava/lang/Object;L~/japi/pf/FI$TypedPredicate;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this | this |
| `japi.pf.ReceiveBuilder.matchEquals` `(Ljava/lang/Object;Ljava/util/function/BooleanSupplier;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this | this |
| `japi.pf.ReceiveBuilder.matchAny` `(L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this | this |
| `japi.pf.ReceiveBuilder.matchAny` `(Ljava/util/function/BooleanSupplier;L~/japi/pf/FI$UnitApply;)L~/japi/pf/ReceiveBuilder;` | this | this |
| `japi.pf.ReceiveBuilder.build` `()L~/actor/AbstractActor$Receive;` | new/other | new/other |
| `actor.AbstractActor.receiveBuilder` `()L~/japi/pf/ReceiveBuilder;` | new/other | new/other |
| `actor.AbstractActor.getSender` `()L~/actor/ActorRef;` | new/other | via call: new/other |
| `actor.AbstractActor.getSelf` `()L~/actor/ActorRef;` | via call: new/other | via call: new/other |
| `actor.typed.ActorRef.tell` `(Ljava/lang/Object;)V` | abstract | abstract |
| `actor.ActorRef.tell` `(Ljava/lang/Object;L~/actor/ActorRef;)V` | void/prim | void/prim |
| `actor.ActorRef.forward` `(Ljava/lang/Object;L~/actor/ActorContext;)V` | void/prim | void/prim |
| `actor.typed.RecipientRef.tell` `(Ljava/lang/Object;)V` | abstract | abstract |
| `actor.typed.RecipientRef.ask` `-` | NOT FOUND | NOT FOUND |
| `actor.typed.javadsl.AskPattern.ask` `(L~/actor/typed/RecipientRef;L~/japi/function/Function;Ljava/time/Duration;L~/actor/typed/Scheduler;)Ljava/util/concurrent/CompletionStage;` | new/other | new/other |
| `cluster.sharding.typed.javadsl.EntityRef.tell` `(Ljava/lang/Object;)V` | abstract | abstract |
| `cluster.sharding.typed.javadsl.EntityRef.ask` `(L~/japi/function/Function;Ljava/time/Duration;)Ljava/util/concurrent/CompletionStage;` | abstract | abstract |
| `actor.typed.javadsl.ActorContext.ask` `(Ljava/lang/Class;L~/actor/typed/RecipientRef;Ljava/time/Duration;L~/japi/function/Function;L~/japi/function/Function2;)V` | abstract | abstract |
| `actor.typed.javadsl.ActorContext.messageAdapter` `(Ljava/lang/Class;L~/japi/function/Function;)L~/actor/typed/ActorRef;` | abstract | abstract |
| `actor.typed.javadsl.ActorContext.pipeToSelf` `(Ljava/util/concurrent/CompletionStage;L~/japi/function/Function2;)V` | abstract | abstract |
| `actor.typed.javadsl.TimerScheduler.startTimerWithFixedDelay` `(Ljava/lang/Object;Ljava/lang/Object;Ljava/time/Duration;)V` | abstract | abstract |
| `actor.typed.javadsl.TimerScheduler.startTimerWithFixedDelay` `(Ljava/lang/Object;Ljava/lang/Object;Ljava/time/Duration;Ljava/time/Duration;)V` | abstract | abstract |
| `actor.typed.javadsl.TimerScheduler.startTimerWithFixedDelay` `(Ljava/lang/Object;Ljava/time/Duration;)V` | void/prim | void/prim |
| `actor.typed.javadsl.TimerScheduler.startTimerWithFixedDelay` `(Ljava/lang/Object;Ljava/time/Duration;Ljava/time/Duration;)V` | void/prim | void/prim |
| `actor.typed.javadsl.TimerScheduler.startTimerAtFixedRate` `(Ljava/lang/Object;Ljava/lang/Object;Ljava/time/Duration;)V` | abstract | abstract |
| `actor.typed.javadsl.TimerScheduler.startTimerAtFixedRate` `(Ljava/lang/Object;Ljava/lang/Object;Ljava/time/Duration;Ljava/time/Duration;)V` | abstract | abstract |
| `actor.typed.javadsl.TimerScheduler.startTimerAtFixedRate` `(Ljava/lang/Object;Ljava/time/Duration;)V` | void/prim | void/prim |
| `actor.typed.javadsl.TimerScheduler.startTimerAtFixedRate` `(Ljava/lang/Object;Ljava/time/Duration;Ljava/time/Duration;)V` | void/prim | void/prim |
| `actor.typed.javadsl.TimerScheduler.startSingleTimer` `(Ljava/lang/Object;Ljava/lang/Object;Ljava/time/Duration;)V` | abstract | abstract |
| `actor.typed.javadsl.TimerScheduler.startSingleTimer` `(Ljava/lang/Object;Ljava/time/Duration;)V` | void/prim | void/prim |
| `actor.typed.javadsl.TimerScheduler.startPeriodicTimer` `(Ljava/lang/Object;Ljava/lang/Object;Ljava/time/Duration;)V` | abstract | abstract |
| `actor.typed.Scheduler.scheduleOnce` `(Lscala/concurrent/duration/FiniteDuration;Ljava/lang/Runnable;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | abstract | abstract |
| `actor.typed.Scheduler.scheduleOnce` `(Ljava/time/Duration;Ljava/lang/Runnable;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | abstract | abstract |
| `actor.typed.Scheduler.scheduleWithFixedDelay` `(Lscala/concurrent/duration/FiniteDuration;Lscala/concurrent/duration/FiniteDuration;Ljava/lang/Runnable;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | abstract | abstract |
| `actor.typed.Scheduler.scheduleWithFixedDelay` `(Ljava/time/Duration;Ljava/time/Duration;Ljava/lang/Runnable;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | abstract | abstract |
| `actor.Scheduler.scheduleOnce` `(Lscala/concurrent/duration/FiniteDuration;L~/actor/ActorRef;Ljava/lang/Object;Lscala/concurrent/ExecutionContext;L~/actor/ActorRef;)L~/actor/Cancellable;` | new/other | new/other |
| `actor.Scheduler.scheduleOnce` `(Ljava/time/Duration;L~/actor/ActorRef;Ljava/lang/Object;Lscala/concurrent/ExecutionContext;L~/actor/ActorRef;)L~/actor/Cancellable;` | new/other | new/other |
| `actor.Scheduler.scheduleOnce` `(Lscala/concurrent/duration/FiniteDuration;Lscala/Function0;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | new/other | new/other |
| `actor.Scheduler.scheduleOnce` `(Lscala/concurrent/duration/FiniteDuration;Ljava/lang/Runnable;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | abstract | abstract |
| `actor.Scheduler.scheduleOnce` `(Ljava/time/Duration;Ljava/lang/Runnable;Lscala/concurrent/ExecutionContext;)L~/actor/Cancellable;` | new/other | new/other |
| `actor.typed.receptionist.ServiceKey.create` `(Ljava/lang/Class;Ljava/lang/String;)L~/actor/typed/receptionist/ServiceKey;` | new/other | new/other |
| `cluster.sharding.typed.javadsl.EntityTypeKey.create` `(Ljava/lang/Class;Ljava/lang/String;)L~/cluster/sharding/typed/javadsl/EntityTypeKey;` | new/other | new/other |
| `cluster.sharding.typed.javadsl.Entity.of` `(L~/cluster/sharding/typed/javadsl/EntityTypeKey;L~/japi/function/Function;)L~/cluster/sharding/typed/javadsl/Entity;` | new/other | new/other |
| `cluster.sharding.typed.javadsl.ClusterSharding.init` `(L~/cluster/sharding/typed/javadsl/Entity;)L~/actor/typed/ActorRef;` | abstract | abstract |
| `cluster.sharding.typed.javadsl.ClusterSharding.entityRefFor` `(L~/cluster/sharding/typed/javadsl/EntityTypeKey;Ljava/lang/String;)L~/cluster/sharding/typed/javadsl/EntityRef;` | abstract | abstract |
| `cluster.sharding.typed.javadsl.ClusterSharding.entityRefFor` `(L~/cluster/sharding/typed/javadsl/EntityTypeKey;Ljava/lang/String;Ljava/lang/String;)L~/cluster/sharding/typed/javadsl/EntityRef;` | abstract | abstract |
| `actor.typed.receptionist.Receptionist.register` `(L~/actor/typed/receptionist/ServiceKey;L~/actor/typed/ActorRef;L~/actor/typed/ActorRef;)L~/actor/typed/receptionist/Receptionist$Command;` | new/other | new/other |
| `actor.typed.receptionist.Receptionist.register` `(L~/actor/typed/receptionist/ServiceKey;L~/actor/typed/ActorRef;)L~/actor/typed/receptionist/Receptionist$Command;` | new/other | new/other |
| `actor.typed.receptionist.Receptionist.subscribe` `(L~/actor/typed/receptionist/ServiceKey;L~/actor/typed/ActorRef;)L~/actor/typed/receptionist/Receptionist$Command;` | new/other | new/other |
| `actor.typed.receptionist.Receptionist.find` `(L~/actor/typed/receptionist/ServiceKey;L~/actor/typed/ActorRef;)L~/actor/typed/receptionist/Receptionist$Command;` | new/other | new/other |
| `cluster.pubsub.DistributedPubSubMediator$Publish.<init>` `(Ljava/lang/String;Ljava/lang/Object;Z)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Publish.<init>` `(Ljava/lang/String;Ljava/lang/Object;)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Subscribe.<init>` `(Ljava/lang/String;Lscala/Option;L~/actor/ActorRef;)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Subscribe.<init>` `(Ljava/lang/String;L~/actor/ActorRef;)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Subscribe.<init>` `(Ljava/lang/String;Ljava/lang/String;L~/actor/ActorRef;)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Send.<init>` `(Ljava/lang/String;Ljava/lang/Object;Z)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Send.<init>` `(Ljava/lang/String;Ljava/lang/Object;)V` | void/prim | void/prim |
| `cluster.pubsub.DistributedPubSubMediator$Put.<init>` `(L~/actor/ActorRef;)V` | void/prim | void/prim |
| `pattern.Patterns.ask` `(L~/actor/ActorSelection;Ljava/lang/Object;J)Lscala/concurrent/Future;` | new/other | new/other |
| `pattern.Patterns.ask` `(L~/actor/ActorSelection;Ljava/lang/Object;Ljava/time/Duration;)Ljava/util/concurrent/CompletionStage;` | new/other | new/other |
| `pattern.Patterns.ask` `(L~/actor/ActorSelection;Ljava/lang/Object;L~/util/Timeout;)Lscala/concurrent/Future;` | new/other | new/other |
| `pattern.Patterns.ask` `(L~/actor/ActorRef;Ljava/lang/Object;J)Lscala/concurrent/Future;` | new/other | new/other |
| `pattern.Patterns.ask` `(L~/actor/ActorRef;Ljava/lang/Object;Ljava/time/Duration;)Ljava/util/concurrent/CompletionStage;` | new/other | new/other |
| `pattern.Patterns.ask` `(L~/actor/ActorRef;Ljava/lang/Object;L~/util/Timeout;)Lscala/concurrent/Future;` | new/other | new/other |
| `pattern.Patterns.pipe` `(Ljava/util/concurrent/CompletionStage;Lscala/concurrent/ExecutionContext;)L~/pattern/PipeToSupport$PipeableCompletionStage;` | new/other | new/other |
| `pattern.Patterns.pipe` `(Lscala/concurrent/Future;Lscala/concurrent/ExecutionContext;)L~/pattern/PipeToSupport$PipeableFuture;` | new/other | new/other |


## Compiled fixture shapes (`fixtures/orders-actors-pekko`)


### Stock

- `create` `()L~actor/typed/Behavior;`
    invokedynamic #7,  0              // InvokeDynamic #0:apply:()L~japi/function/Function;
    invokestatic  #11                 // Method ~actor/typed/javadsl/Behaviors.setup:(L~japi/function/Function;)L~actor/typed/Behavior;
    areturn
- `behavior` `(L~actor/typed/javadsl/ActorContext;)L~actor/typed/Behavior;`
    ldc           #17                 // class com/acme/actors/Stock$Command
    invokestatic  #19                 // Method ~actor/typed/javadsl/Behaviors.receive:(Ljava/lang/Class;)L~actor/typed/javadsl/BehaviorBuilder;
    ldc           #23                 // class com/acme/actors/Stock$Reserve
    invokedynamic #25,  0             // InvokeDynamic #1:apply:()L~japi/function/Function;
    invokevirtual #26                 // Method ~actor/typed/javadsl/BehaviorBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/BehaviorBuilder;
    ldc           #32                 // class com/acme/actors/Stock$Release
    invokedynamic #34,  0             // InvokeDynamic #2:test:()L~japi/function/Predicate;
    invokedynamic #38,  0             // InvokeDynamic #3:apply:()L~japi/function/Function;
    invokevirtual #39                 // Method ~actor/typed/javadsl/BehaviorBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Predicate;L~japi/function/Function;)L~actor/typed/javadsl/BehaviorBuilder;
    ldc           #32                 // class com/acme/actors/Stock$Release
    invokedynamic #42,  0             // InvokeDynamic #4:apply:()L~japi/function/Function;
    invokevirtual #26                 // Method ~actor/typed/javadsl/BehaviorBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/BehaviorBuilder;
    getstatic     #43                 // Field com/acme/actors/Stock$Tick.INSTANCE:Lcom/acme/actors/Stock$Tick;
    invokedynamic #49,  0             // InvokeDynamic #5:create:()L~japi/function/Creator;
    invokevirtual #53                 // Method ~actor/typed/javadsl/BehaviorBuilder.onMessageEquals:(Ljava/lang/Object;L~japi/function/Creator;)L~actor/typed/javadsl/BehaviorBuilder;
    invokevirtual #57                 // Method ~actor/typed/javadsl/BehaviorBuilder.build:()L~actor/typed/Behavior;
    areturn
- `lambda$behavior$b0625256$1` `(Lcom/acme/actors/Stock$Release;)Z`
    invokevirtual #174                // Method com/acme/actors/Stock$Release.urgent:()Z
- `lambda$create$563c651a$1` `(L~actor/typed/javadsl/ActorContext;)L~actor/typed/Behavior;`
    invokeinterface #178,  1          // InterfaceMethod ~actor/typed/javadsl/ActorContext.getSystem:()L~actor/typed/ActorSystem;
    invokevirtual #182                // Method ~actor/typed/ActorSystem.receptionist:()L~actor/typed/ActorRef;
    getstatic     #187                // Field KEY:L~actor/typed/receptionist/ServiceKey;
    invokeinterface #192,  1          // InterfaceMethod ~actor/typed/javadsl/ActorContext.getSelf:()L~actor/typed/ActorRef;
    invokestatic  #195                // Method ~actor/typed/receptionist/Receptionist.register:(L~actor/typed/receptionist/ServiceKey;L~actor/typed/ActorRef;)L~actor/typed/receptionist/Receptionist$Command;
    invokeinterface #74,  2           // InterfaceMethod ~actor/typed/ActorRef.tell:(Ljava/lang/Object;)V
    invokedynamic #146,  0            // InvokeDynamic #6:apply:(L~actor/typed/javadsl/ActorContext;)L~japi/function/Function;
    invokestatic  #201                // Method ~actor/typed/javadsl/Behaviors.withTimers:(L~japi/function/Function;)L~actor/typed/Behavior;
    areturn
- `lambda$create$d0607d02$1` `(L~actor/typed/javadsl/ActorContext;L~actor/typed/javadsl/TimerScheduler;)L~actor/typed/Behavior;`
    getstatic     #43                 // Field com/acme/actors/Stock$Tick.INSTANCE:Lcom/acme/actors/Stock$Tick;
    ldc2_w        #204                // long 30l
    invokestatic  #206                // Method java/time/Duration.ofSeconds:(J)Ljava/time/Duration;
    invokeinterface #212,  3          // InterfaceMethod ~actor/typed/javadsl/TimerScheduler.startTimerWithFixedDelay:(Ljava/lang/Object;Ljava/time/Duration;)V
    invokestatic  #218                // Method behavior:(L~actor/typed/javadsl/ActorContext;)L~actor/typed/Behavior;
    areturn

### OrderRoutes

- `summary` `(Ljava/lang/String;)Ljava/util/concurrent/CompletionStage;`
    getstatic     #31                 // Field com/acme/actors/OrderEntity.KEY:L~cluster/sharding/typed/javadsl/EntityTypeKey;
    invokevirtual #51                 // Method ~cluster/sharding/typed/javadsl/ClusterSharding.entityRefFor:(L~cluster/sharding/typed/javadsl/EntityTypeKey;Ljava/lang/String;)L~cluster/sharding/typed/javadsl/EntityRef;
    invokedynamic #55,  0             // InvokeDynamic #1:apply:(Ljava/lang/String;)L~japi/function/Function;
    invokevirtual #58                 // Method ~cluster/sharding/typed/javadsl/EntityRef.ask:(L~japi/function/Function;Ljava/time/Duration;)Ljava/util/concurrent/CompletionStage;
    areturn
- `lambda$summary$f5b3167d$1` `(Ljava/lang/String;L~actor/typed/ActorRef;)Lcom/acme/actors/OrderEntity$Command;`
    new           #124                // class com/acme/actors/OrderEntity$Get
    invokespecial #126                // Method com/acme/actors/OrderEntity$Get."<init>":(Ljava/lang/String;L~actor/typed/ActorRef;)V
    areturn
- `lambda$new$5b82b54a$1` `(L~cluster/sharding/typed/javadsl/EntityContext;)L~actor/typed/Behavior;`
    invokevirtual #129                // Method ~cluster/sharding/typed/javadsl/EntityContext.getEntityId:()Ljava/lang/String;
    invokestatic  #134                // Method com/acme/actors/OrderEntity.create:(Ljava/lang/String;)L~actor/typed/Behavior;
    areturn

### Frontend

- `create` `()L~actor/typed/Behavior;`
    invokedynamic #1,  0              // InvokeDynamic #0:apply:()L~japi/function/Function;
    invokestatic  #5                  // Method ~actor/typed/javadsl/Behaviors.setup:(L~japi/function/Function;)L~actor/typed/Behavior;
    areturn
- `createReceive` `()L~actor/typed/javadsl/Receive;`
    invokevirtual #54                 // Method newReceiveBuilder:()L~actor/typed/javadsl/ReceiveBuilder;
    ldc           #60                 // class com/acme/actors/Frontend$Workers
    invokedynamic #62,  0             // InvokeDynamic #2:apply:(Lcom/acme/actors/Frontend;)L~japi/function/Function;
    invokevirtual #65                 // Method ~actor/typed/javadsl/ReceiveBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/ReceiveBuilder;
    ldc           #71                 // class com/acme/actors/Frontend$Start
    invokedynamic #73,  0             // InvokeDynamic #3:apply:(Lcom/acme/actors/Frontend;)L~japi/function/Function;
    invokevirtual #65                 // Method ~actor/typed/javadsl/ReceiveBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/ReceiveBuilder;
    ldc           #74                 // class com/acme/actors/Frontend$Reserved
    invokedynamic #76,  0             // InvokeDynamic #4:apply:()L~japi/function/Function;
    invokevirtual #65                 // Method ~actor/typed/javadsl/ReceiveBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/ReceiveBuilder;
    ldc           #77                 // class com/acme/actors/Frontend$Failed
    invokedynamic #79,  0             // InvokeDynamic #5:apply:()L~japi/function/Function;
    invokevirtual #65                 // Method ~actor/typed/javadsl/ReceiveBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/ReceiveBuilder;
    ldc           #80                 // class com/acme/actors/Frontend$Loaded
    invokedynamic #82,  0             // InvokeDynamic #6:apply:()L~japi/function/Function;
    invokevirtual #65                 // Method ~actor/typed/javadsl/ReceiveBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/ReceiveBuilder;
    invokevirtual #83                 // Method ~actor/typed/javadsl/ReceiveBuilder.build:()L~actor/typed/javadsl/Receive;
    areturn
- `onStart` `(Lcom/acme/actors/Frontend$Start;)L~actor/typed/Behavior;`
    invokevirtual #115                // Method getContext:()L~actor/typed/javadsl/ActorContext;
    ldc           #119                // class com/acme/actors/Stock$Reply
    ldc2_w        #121                // long 3l
    invokestatic  #123                // Method java/time/Duration.ofSeconds:(J)Ljava/time/Duration;
    invokedynamic #129,  0            // InvokeDynamic #7:apply:(Lcom/acme/actors/Frontend$Start;)L~japi/function/Function;
    invokedynamic #132,  0            // InvokeDynamic #8:apply:()L~japi/function/Function2;
    invokeinterface #135,  6          // InterfaceMethod ~actor/typed/javadsl/ActorContext.ask:(Ljava/lang/Class;L~actor/typed/RecipientRef;Ljava/time/Duration;L~japi/function/Function;L~japi/function/Function2;)V
    invokevirtual #115                // Method getContext:()L~actor/typed/javadsl/ActorContext;
    invokevirtual #139                // Method com/acme/actors/Frontend$Start.sku:()Ljava/lang/String;
    invokevirtual #143                // Method load:(Ljava/lang/String;)Ljava/util/concurrent/CompletionStage;
    invokedynamic #147,  0            // InvokeDynamic #9:apply:()L~japi/function/Function2;
    invokeinterface #148,  3          // InterfaceMethod ~actor/typed/javadsl/ActorContext.pipeToSelf:(Ljava/util/concurrent/CompletionStage;L~japi/function/Function2;)V
    areturn
- `lambda$onStart$d0bd6b17$2` `(Ljava/lang/String;Ljava/lang/Throwable;)Lcom/acme/actors/Frontend$Command;`
    new           #80                 // class com/acme/actors/Frontend$Loaded
    invokespecial #253                // Method com/acme/actors/Frontend$Loaded."<init>":(Ljava/lang/String;)V
    areturn
- `lambda$onStart$d0bd6b17$1` `(Lcom/acme/actors/Stock$Reply;Ljava/lang/Throwable;)Lcom/acme/actors/Frontend$Command;`
    new           #74                 // class com/acme/actors/Frontend$Reserved
    invokespecial #254                // Method com/acme/actors/Frontend$Reserved."<init>":(Lcom/acme/actors/Stock$Reply;)V
    new           #77                 // class com/acme/actors/Frontend$Failed
    invokespecial #257                // Method com/acme/actors/Frontend$Failed."<init>":(Ljava/lang/Throwable;)V
    areturn
- `lambda$onStart$13760579$1` `(Lcom/acme/actors/Frontend$Start;L~actor/typed/ActorRef;)Lcom/acme/actors/Stock$Command;`
    new           #260                // class com/acme/actors/Stock$Reserve
    invokevirtual #139                // Method com/acme/actors/Frontend$Start.sku:()Ljava/lang/String;
    invokespecial #262                // Method com/acme/actors/Stock$Reserve."<init>":(Ljava/lang/String;L~actor/typed/ActorRef;)V
    areturn
- `lambda$createReceive$f0fefa0b$3` `(Lcom/acme/actors/Frontend$Loaded;)L~actor/typed/Behavior;`
    invokestatic  #265                // Method ~actor/typed/javadsl/Behaviors.same:()L~actor/typed/Behavior;
    areturn
- `lambda$createReceive$f0fefa0b$2` `(Lcom/acme/actors/Frontend$Failed;)L~actor/typed/Behavior;`
    invokestatic  #265                // Method ~actor/typed/javadsl/Behaviors.same:()L~actor/typed/Behavior;
    areturn
- `lambda$createReceive$f0fefa0b$1` `(Lcom/acme/actors/Frontend$Reserved;)L~actor/typed/Behavior;`
    invokestatic  #265                // Method ~actor/typed/javadsl/Behaviors.same:()L~actor/typed/Behavior;
    areturn
- `lambda$new$b45bb4f0$1` `(L~actor/typed/receptionist/Receptionist$Listing;)Lcom/acme/actors/Frontend$Command;`
    new           #60                 // class com/acme/actors/Frontend$Workers
    invokespecial #269                // Method com/acme/actors/Frontend$Workers."<init>":(L~actor/typed/receptionist/Receptionist$Listing;)V
    areturn

### Relay

- `forward` `(Ljava/lang/Object;L~actor/typed/ActorRef;)V`
    invokeinterface #7,  2            // InterfaceMethod ~actor/typed/ActorRef.tell:(Ljava/lang/Object;)V

### ClassicBroker

- `preStart` `()V`
    new           #32                 // class ~cluster/pubsub/DistributedPubSubMediator$Subscribe
    ldc           #34                 // String prices
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokespecial #39                 // Method ~cluster/pubsub/DistributedPubSubMediator$Subscribe."<init>":(Ljava/lang/String;L~actor/ActorRef;)V
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokevirtual #42                 // Method ~actor/ActorRef.tell:(Ljava/lang/Object;L~actor/ActorRef;)V
    new           #48                 // class ~cluster/pubsub/DistributedPubSubMediator$Put
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokespecial #50                 // Method ~cluster/pubsub/DistributedPubSubMediator$Put."<init>":(L~actor/ActorRef;)V
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokevirtual #42                 // Method ~actor/ActorRef.tell:(Ljava/lang/Object;L~actor/ActorRef;)V
- `createReceive` `()L~actor/AbstractActor$Receive;`
    invokevirtual #53                 // Method receiveBuilder:()L~japi/pf/ReceiveBuilder;
    ldc           #57                 // class com/acme/actors/ClassicBroker$Price
    invokedynamic #59,  0             // InvokeDynamic #0:apply:(Lcom/acme/actors/ClassicBroker;)L~japi/pf/FI$UnitApply;
    invokevirtual #63                 // Method ~japi/pf/ReceiveBuilder.match:(Ljava/lang/Class;L~japi/pf/FI$UnitApply;)L~japi/pf/ReceiveBuilder;
    invokevirtual #69                 // Method ~japi/pf/ReceiveBuilder.build:()L~actor/AbstractActor$Receive;
    areturn
- `onPrice` `(Lcom/acme/actors/ClassicBroker$Price;)V`
    invokevirtual #73                 // Method getSender:()L~actor/ActorRef;
    new           #76                 // class com/acme/actors/ClassicBroker$Ack
    invokespecial #78                 // Method com/acme/actors/ClassicBroker$Ack."<init>":()V
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokevirtual #42                 // Method ~actor/ActorRef.tell:(Ljava/lang/Object;L~actor/ActorRef;)V
- `announce` `(Ljava/lang/String;D)V`
    new           #79                 // class ~cluster/pubsub/DistributedPubSubMediator$Publish
    ldc           #34                 // String prices
    new           #57                 // class com/acme/actors/ClassicBroker$Price
    invokespecial #81                 // Method com/acme/actors/ClassicBroker$Price."<init>":(Ljava/lang/String;D)V
    invokespecial #84                 // Method ~cluster/pubsub/DistributedPubSubMediator$Publish."<init>":(Ljava/lang/String;Ljava/lang/Object;)V
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokevirtual #42                 // Method ~actor/ActorRef.tell:(Ljava/lang/Object;L~actor/ActorRef;)V
    new           #87                 // class ~cluster/pubsub/DistributedPubSubMediator$Send
    ldc           #89                 // String /user/broker
    new           #57                 // class com/acme/actors/ClassicBroker$Price
    invokespecial #81                 // Method com/acme/actors/ClassicBroker$Price."<init>":(Ljava/lang/String;D)V
    invokespecial #91                 // Method ~cluster/pubsub/DistributedPubSubMediator$Send."<init>":(Ljava/lang/String;Ljava/lang/Object;Z)V
    invokevirtual #36                 // Method getSelf:()L~actor/ActorRef;
    invokevirtual #42                 // Method ~actor/ActorRef.tell:(Ljava/lang/Object;L~actor/ActorRef;)V

### OrderEntity

- `create` `(Ljava/lang/String;)L~actor/typed/Behavior;`
    ldc           #7                  // class com/acme/actors/OrderEntity$Command
    invokestatic  #9                  // Method ~actor/typed/javadsl/Behaviors.receive:(Ljava/lang/Class;)L~actor/typed/javadsl/BehaviorBuilder;
    ldc           #15                 // class com/acme/actors/OrderEntity$Get
    invokedynamic #17,  0             // InvokeDynamic #0:apply:(Ljava/lang/String;)L~japi/function/Function;
    invokevirtual #21                 // Method ~actor/typed/javadsl/BehaviorBuilder.onMessage:(Ljava/lang/Class;L~japi/function/Function;)L~actor/typed/javadsl/BehaviorBuilder;
    invokevirtual #27                 // Method ~actor/typed/javadsl/BehaviorBuilder.build:()L~actor/typed/Behavior;
    areturn
- `lambda$create$a78569a$1` `(Ljava/lang/String;Lcom/acme/actors/OrderEntity$Get;)L~actor/typed/Behavior;`
    invokestatic  #106                // Method onGet:(Ljava/lang/String;Lcom/acme/actors/OrderEntity$Get;)L~actor/typed/Behavior;
    areturn


### Orders (persistence builder held in locals; Pekko build)

`commandHandler()` keeps the `CommandHandlerBuilder` in local 1 and each `forState` result in its own local (2 and 3).
`forAnyState().onCommand(..)` is a chain whose result is dropped; the `onCommand` calls on the locals are separate statements.

- `commandHandler` `()LPK/persistence/typed/javadsl/CommandHandler;`
    invokevirtual newCommandHandlerBuilder:()CommandHandlerBuilder ; astore_1
    aload_1 ; invokevirtual CommandHandlerBuilder.forAnyState:()CommandHandlerBuilderByState
    ldc Orders$Place ; invokedynamic apply(Orders)BiFunction ; invokevirtual CommandHandlerBuilderByState.onCommand:(Class,BiFunction)CommandHandlerBuilderByState
    aload_1 ; invokedynamic test()Predicate ; invokevirtual CommandHandlerBuilder.forState:(Predicate)CommandHandlerBuilderByState ; astore_2
    aload_2 ; ldc Orders$Cancel ; invokedynamic apply(Orders)BiFunction ; invokevirtual CommandHandlerBuilderByState.onCommand:(Class,BiFunction)CommandHandlerBuilderByState
    aload_1 ; invokedynamic test()Predicate ; invokevirtual CommandHandlerBuilder.forState:(Predicate)CommandHandlerBuilderByState ; astore_3
    aload_3 ; ldc Orders$Cancel ; invokedynamic apply(Orders)BiFunction ; invokevirtual CommandHandlerBuilderByState.onCommand:(Class,BiFunction)CommandHandlerBuilderByState
    aload_1 ; invokevirtual CommandHandlerBuilder.build:()CommandHandler ; areturn

The `onCommand` results are not used (no `astore`), so a read that follows `onCommand` through its return value finds
nothing; the behavior is the local the call is made on. The handler references (`this::onPlace` etc.) are
`invokedynamic` bootstraps naming the private methods directly.

### TwoReturns (scratch, compiled by run.sh)

- `lambda$run$b007125f$1` `(Ljava/lang/String;Ljava/lang/Throwable;)Lprobe/TwoReturns$Command;`
    ifnull        13
    new           #70                 // class probe/TwoReturns$Failed
    invokespecial #72                 // Method probe/TwoReturns$Failed."<init>":(Ljava/lang/Throwable;)V
    areturn
    new           #75                 // class probe/TwoReturns$Done
    invokespecial #77                 // Method probe/TwoReturns$Done."<init>":(Ljava/lang/String;)V
    areturn

