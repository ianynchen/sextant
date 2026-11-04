# Akka and Pekko actors — design

**Status: DRAFT 2026-11-04.** Plane SEXTANT-178 (register `akka-pekko-actors`), the fourth
item of "Java/Kotlin complete" (SEXTANT-265). The user ruled **B** on 2026-11-04 ("I want
it complete"): named cluster keys are endpoint rows, **and** every message send is followed
to the actor that handles it, so a trace crosses actors.

Moves COVERAGE §5's **Akka / Pekko actors** row (`◐ 0/1`, tier C, "possibly permanent").
The Akka HTTP route DSL (the other half of the SEXTANT-178 title) is a separate design after
this one; it is a route combinator, not a message send.

## 1. What this is for

An actor-based module talks to itself and to its cluster through messages. Today its
architecture document shows the HTTP or broker edges at its rim and nothing between: every
`tell`, `ask` and handler is invisible, and a trace from an HTTP route stops at the first
`ref.ask(...)`.

**Success:**
1. Every named cluster address the module serves or uses is an endpoint row (protocol
   `actor`): a Receptionist service key, a sharded entity type, a distributed pub-sub topic.
2. Every send (`tell`, `ask`, and their classic forms) is a trace hop to each handler in the
   module that the message's class reaches, so `WeatherRoutes.query` traces through
   `ref.ask(r -> new Query(...))` into `WeatherStation`'s query handler.

**Anti-goals:**
- **No endpoint row for an in-process send.** A `tell` to a `replyTo` or to an actor the
  module started is a hop, never an outbound row (the self-call ruling of 2026-10-25).
- **No hop to a handler the message cannot reach.** Within one behavior, Akka tries cases in
  the order they were added and stops at the first match; a handler shadowed by an earlier
  case for the same message is not a hop target.
- **No guessed message class.** Where the facts cannot name the message's class, the hop is
  a stop that says so, never a fan-out to every handler.
- **No Akka-specific engine.** Python names no framework (`test_source_rules.py`). Catalogs
  declare the API; engines read declared shapes.

## 2. Measured (2026-11-04)

Corpus: `examples/pekko-samples` and `examples/akka-samples` (cloned 2026-11-04; the
official samples). 83 Java files import the actor API; most Java samples build with Maven.
No other repository under `examples/` uses actors. Scala samples are out of reach (no Scala
scanner) and out of scope.

| Shape | Count |
|---|---|
| `.tell(` sends | 164 — to a `replyTo` 72, to a module-started actor ~60, to a system actor (receptionist, cluster subscriptions, event stream, pub-sub mediator) ~30 |
| `ask` (`EntityRef.ask`, `context.ask`, `Patterns.ask`) | 11 |
| typed `onMessage(Class, h)` / `onMessageEquals(v, h)` | 100 / 24 |
| persistence `onCommand(Class, h)` | 57 |
| classic `match(Class, h)` / `matchEquals` | 3 / 1 |
| `messageAdapter(Class, f)` | 16 |
| `ServiceKey.create(Class, "name")` | 6 |
| `EntityTypeKey.create(Class, "name")` / `entityRefFor` / `Entity.of` | 2 / 4 / 2 |
| classic `DistributedPubSubMediator.Publish/Subscribe/Send/Put` | 6 |

Most sends pass `new Msg(...)` directly, so the facts name the runtime class (`instance`
argument kind, D00 §5). An `ask` passes a lambda that builds the message
(`replyTo -> new Query(..., replyTo)`); the class is the `new` inside that lambda.

## 3. Design

### 3a. Endpoint rows — protocol `actor`

A new `Protocol.ACTOR = "actor"` (closed set; template commit `12d72679`). The address is
the key's name; the payload is the key's message class.

| API | Direction | Address read from |
|---|---|---|
| `Receptionist.register(ServiceKey, ActorRef)` | inbound | the key: `ServiceKey.create(Class, String)` arg 1, through `channel_via` (static final field in `<clinit>`, already read by `values.py`) |
| `ClusterSharding.init(Entity.of(EntityTypeKey, factory))` | inbound | `Entity.of` arg 0 → `EntityTypeKey.create` arg 1 (two `channel_via` steps) |
| `Receptionist.subscribe(key, ref)`, `Receptionist.find(key, ref)` | outbound | the key, as above |
| `ClusterSharding.entityRefFor(EntityTypeKey, id)` | outbound | the key, as above |
| classic `new DistributedPubSubMediator.Subscribe(topic, ref)` / `Put(ref)` | inbound | the topic string / the actor's path |
| classic `new DistributedPubSubMediator.Publish(topic, msg)` / `Send(path, msg)` | outbound | the topic / path string |

An inbound row's `handler` is each handler the key's message class reaches (§3c), one row
per handler, the way a route with two handlers is two rows. Linking across modules is by
protocol and address, unchanged.

Catalogs: one per published artifact, Akka (`akka.*`, 2.6.x on Maven Central) and Pekko
(`org.apache.pekko.*`, 1.x): `*-actor-typed`, `*-cluster-typed`, `*-cluster-sharding-typed`,
`*-cluster-tools` (classic pub-sub). Each method row measured with `javap` (probe CP-57).

### 3b. Message handlers — a new fact the catalogs declare

A **handler registration** binds a message class (or an equal value) to a handler inside one
behavior. A catalog declares it with a new row kind:

```yaml
message_handlers:
  - { owner: …ReceiveBuilder, method: onMessage, class_arg: 0, handler_arg: 1 }
  - { owner: …ReceiveBuilder, method: onMessageEquals, value_arg: 0, handler_arg: 1 }
  - { owner: …CommandHandlerBuilderByState, method: onCommand, class_arg: 0, handler_arg: 1 }
  - { owner: …japi.pf.ReceiveBuilder, method: match, class_arg: 0, handler_arg: 1 }
  - { owner: …ActorContext, method: messageAdapter, class_arg: 0, handler_arg: 1, returns_message: true }
```

The resolver reads each registration with the existing pieces: the class argument as a
type reference (`_reference_of`), the handler as a method reference or lambda
(`combinator._handler_of`), and the **behavior** it belongs to as the fluent chain it is on
(the builder object; `which_object`), with its position in that chain. It writes one row per
registration to a new graph table:

`message_handlers(behavior, position, message_type, message_value, handler, evidence)`

**Graph schema 14 → 15 (persisted; needs the user's approval with this design).**

A `messageAdapter` handler returns a message delivered to its own actor
(`returns_message: true`): the hop continues from the adapter to the handlers of the class
it returns, read from the `new` in its body.

### 3c. Hops — a send reaches the handlers of its message's class

For each send site a catalog declares (`tell`, `ask`, `EntityRef.tell/ask`, classic
`tell(msg, sender)`, `Patterns.ask`, `context.ask`, pub-sub `Publish`/`Send`), the resolver
reads the message's class:
- an `instance` argument: its class;
- a lambda argument (`ask`): the class of the `new` the lambda returns;
- anything else: **unknown**.

It writes hops into the existing hop table, which the trace already reads (`rpc_hops`,
`trace.py` `_Index`), one per reachable handler, `protocol = actor`,
`path = the message class`. A handler is reachable when, in its behavior, it is the
**first** registration whose class the message's class is assignable to (or whose value
equals a constant message). One hop per behavior that has such a handler; several behaviors
give several hops, as virtual dispatch gives several callees.

- No behavior handles the class (a reply to an `ask`, a message for a system actor): the
  send stays a stop, `via actor <class>`, with no handler.
- Unknown class: a stop that says the message class was not read. Never a fan-out.

`rpc_hops` keeps its name and columns; the code that fills it gains a second producer.
`record_self_calls` is unchanged (gRPC only).

### 3d. Calls made after the builder check (2026-11-04, my calls under the user's rulings)

1. **A behavior is a fluent chain, walked receiver → result.** `Behaviors.receive(C.class)
   .onMessage(…)` returns a NEW immutable builder at each step, so `which_object` would make
   each case its own behavior. The registrations are read as steps of a fluent chain (root
   `Behaviors.receive` / `newReceiveBuilder` / `forAnyState` / `forState` / classic
   `receiveBuilder`, steps the registrations, terminal `build`), which already follows a
   step's result; position is the step's place in the chain. A builder used statement by
   statement (persistence `b.onCommand(…); b.onCommand(…)`) is flagged `returns_receiver`
   only where `javap` shows it returns `this` (D02 rule unchanged). Each `forState` chain is
   its own behavior; states are alternatives, so a class handled in two states is two hops,
   each exact.
2. **The predicate forms** `onMessage(Class, Predicate, h)` and `onCommand(Class, Predicate,
   h)` are declared with `predicate_arg`. **A predicated case never shadows a later case**
   (its predicate may be false); it is itself a hop target.
3. **A constant message is read by identity** (rule 8): `Tick.INSTANCE`, an enum constant,
   a static final field. Its class is the field's type; it reaches `onMessageEquals` cases
   whose value is the same constant, and `onMessage` cases by class. **Timers are sends to
   the actor itself**: `startTimerWithFixedDelay(msg, …)`, `startTimerAtFixedRate`,
   `startSingleTimer`, `scheduleOnce(delay, ref, msg)`.
4. **Every lambda that delivers a message is declared** with `returns_message`:
   `messageAdapter`'s, `context.ask`'s reply mapper (arg 4), `pipeToSelf`'s mapper. A lambda
   with several `return`s gives one hop per returned class (each exact). Send rows declare the
   message position with `message_arg` (a lambda there is read through its returns).
5. **A key the module itself registers or inits is a hop, not an outbound row** (the
   self-call ruling of 2026-10-25): `entityRefFor(TypeKey)` in killrweather, where the same
   module inits `TypeKey`, gives no outbound row; its `tell`/`ask` are hops. The self-call
   pass gains `actor` beside `grpc`.
6. **An inbound row's handlers are found by class, the same rule as hops**: each
   non-shadowed registration whose class is the key's message class or a subtype of it. Which
   behavior a ref holds is not read (§4), so hops and endpoint rows agree.
7. **`rpc_hops` has one reset**, run before both producers; each producer only inserts. The
   class in `path` is masked by redaction like any path; that is harmless.

### 3e. What a builder decides

- Module layout of the hop producer and the handler reader, and how the two share the
  first-match rule.
- Whether `onMessageEquals` value matching reads enum constants and `INSTANCE` singletons
  (both appear in the samples) — read them as identities (the rule-8 "identity is not
  content" reading) if the existing value walk gives them.
- Kotlin: the same Java API; a Kotlin lambda handler normalises through `lambda_body`.

## 4. Not in this design

- **Akka HTTP / Pekko HTTP routes** — next design.
- **Scala sources** — no scanner.
- **`actorSelection("akka://…/user/x")` path strings** — 0 in the corpus; logged, not built.
- **The behavior an `ActorRef` points at.** Hops go by message class, not by which actor a
  ref holds; a ref is a value passed between methods (COVERAGE §7). Two behaviors handling
  one class both get a hop. That is exact where messages belong to one actor's protocol (the
  samples' style: a nested `Command` interface per actor).
- **Cluster singleton, distributed data** — no named address beyond what §3a reads; logged.

## 5. Done when

- Fixtures: one Pekko and one Akka 2.6 Maven module (JDK 21), covering every §2 row.
- `examples/pekko-samples` `pekko-sample-sharding-java/killrweather` and
  `pekko-sample-cluster-java` analyse; every endpoint row and every hop checked against the
  source by hand. A trace from killrweather's `WeatherRoutes.query` reaches
  `WeatherStation`'s query handler (the route itself is Akka HTTP, the next design).
- Gate green, guards killed, six field pins unchanged.
- D00 §4 (protocol list, including the missing `temporal` and `eventbus`), D01 (wire-identity
  table, new table), D02 (the `message_handlers` catalog word), COVERAGE, CHANGELOG.
