# Temporal workflows and the Vert.x event bus: two new protocols (register Group D)

**Status:** design. Approved in conversation 2026-09-22, section by section. Scope set by the
user's four rulings, each recorded where it binds: Temporal derives **workflows, activities,
signals, queries and updates** (§2); **Cadence is a stated boundary**, not a second member (§1);
Vert.x covers **the raw API, Quarkus `@ConsumeEvent` and the two-step consumer** (§3); and the
capability is built as **a shared contract model plus one word per engine** (approach A), never a
second chain walker (§2). Not yet planned.

**Closes:** `temporal-cadence` and `vertx-eventbus`, the two entries the register's §4 order table
calls "D. New `Protocol` members and two naming words", and with them Category C's last two
items. **Rows it changes:** the **Async** column of the register's ```delivery``` block empties —
the row closes. COVERAGE §5.12 gains two shipped framework lines; the `Temporal / Cadence` and
`Vert.x` rows of the Java/Kotlin framework matrix lose their `◐`.

Every factual claim below carries the command that produces it, or names the probe (§9) that must
record it before the key it forces is written. Claims marked **measured 2026-09-22** were verified
during this design conversation, by `javap` on the jars named beside them.
**A probe that contradicts a section here changes the section, not the probe** (GUIDELINES §1.1).

**Standing requirements.** Nothing that works today may move. **No false positives** (user rule,
2026-09-20): a workflow type, an activity name, an address or a handler is written only where the
code states it and the framework honours it; every ambiguity is an unresolved column or an absent
row, never a guess. Misses are acceptable and are stated on the catalog and in COVERAGE. The
resolve layer names no framework and no language (`tests/architecture/test_source_rules.py`,
`test_language_confinement.py`) — §1 records the one place that constraint chose a name.

---

## 0. What the jars say

Measured 2026-09-22 on: temporal-sdk 1.27.0, temporal-spring-boot-autoconfigure 1.27.0,
vertx-core 4.5.10 and 5.0.0, quarkus-vertx 3.17.5, quarkus-vertx-deployment 3.17.5,
smallrye-mutiny-vertx-core 3.16.0. Each row is the finding and the section that carries it.

| # | Finding | Carried by |
|---|---|---|
| M1 | `@WorkflowMethod`'s default name is the **workflow interface's simple name**, not the method's: `POJOWorkflowMethodMetadata.<init>` branches on `getType() == WORKFLOW` and calls `Class.getSimpleName()` on the interface at offset 101, falling to `Method.getName()` at 122 for every other kind | §2's `interface_simple_name` / `member_name` naming words |
| M2 | An `@ActivityMethod(name = "X")` with a non-empty name is used **verbatim, with no prefix**: `POJOActivityMethodMetadata.<init>` tests `name().isEmpty()` at offset 50 and returns the annotation's own value at 58; only the empty branch composes `namePrefix()` + `getActivityNameFromMethod(...)` | §2's `name_skips_prefix` |
| M3 | The activity default is `namePrefix` + the method name with its **first character upper-cased**: `getActivityNameFromMethod` = `substring(0,1).toUpperCase()` + `substring(1)` | §2's `prefixed_capitalized_member_name` |
| M4 | **Every** non-static, non-synthetic declared method of an `@ActivityInterface` is an activity, annotated or not: `validateAndQualifiedForActivityMethod` returns `true` at offset 73 for an unannotated method and `false` only for static or synthetic ones. A **workflow** interface is the opposite — an unannotated method qualifies for nothing | §2's `all_members: true`, declared on the activity interface alone |
| M5 | The task queue is named on `WorkerFactory.newWorker(String[, WorkerOptions])`, on `WorkflowOptions$Builder.setTaskQueue(String)`, on `ActivityOptions$Builder.setTaskQueue(String)` and on `ChildWorkflowOptions$Builder.setTaskQueue(String)` — never on any annotation of the SDK | §1's task-queue-as-metadata ruling; §2's `argument_chain` |
| M6 | The Spring Boot starter's `@WorkflowImpl`, `@ActivityImpl` and `@NexusServiceImpl` each declare exactly two attributes, `String[] workers()` and `String[] taskQueues()` | §2's `annotated_contract` engine |
| M7 | `EventBus.consumer(String, Handler)` **is** `consumer(String)` followed by `MessageConsumer.handler(h)`: `EventBusImpl.consumer(String, Handler)` calls `consumer:(Ljava/lang/String;)` at offset 9 and `MessageConsumer.handler` at 15 | §3's two-step chain and its terminal |
| M8 | vertx-core 4.5.10 and 5.0.0 differ in the surface: 4.5 has the callback `request(String, Object, Handler)` and `(String, Object, DeliveryOptions, Handler)` and `MessageProducer.write(T, Handler)`, none of which exist at 5.0.0; 5.0.0 adds `consumer(MessageConsumerOptions[, Handler])`, whose address sits in `MessageConsumerOptions.setAddress(String)` | §3's per-version rows; §2's `argument_chain` reads the options object |
| M9 | Quarkus `@ConsumeEvent`'s default address is the **declaring bean class's fully-qualified name**: `VertxProcessor` calls `AnnotationProxyBuilder.withDefaultValue("value", BeanInfo.getBeanClass().toString())` at offsets 63–76. `@ConsumeEvent`'s own `AnnotationDefault` for `value()` is the empty string, and for `local()` is **`true`** | §3's `declaring_type_qualified_name` word and the `delivery: local` metadata row |
| M10 | The Mutiny facade `io.vertx.mutiny.core.eventbus.EventBus` declares `send`/`publish`/`consumer`/`localConsumer` with its own descriptors — `request` returns `io.smallrye.mutiny.Uni`, `consumer`'s handler is a `java.util.function.Consumer` — and declares **no `sender`/`publisher` at all** | §3's second owner |
| M11 | `WorkflowStub`'s untyped methods name the member as a plain string at argument 0: `signal(String, Object...)`, `query(String, Class, Object...)`, `update(String, Class, Object...)`, `startUpdate`, `signalWithStart` | §2's untyped-stub rows |

---

## 1. Schema: two `Protocol` members, and what a row's identity is

### 1a. The members

`closed_sets.py` gains `TEMPORAL = "temporal"` and `EVENTBUS = "eventbus"`, added in **one edit**
for the reason the file already states twice (the 2H and 2O blocks): the set is closed, so a member
a later task needs costs one line now and a schema change if it arrives alone.

Each is its own protocol on the DR-5 argument the `AMQP`/`PULSAR` and `RSOCKET` blocks make: linking
gates on protocol equality, and a Temporal workflow type can only ever be answered by a Temporal
worker, an event-bus address only by an event-bus consumer. Publishing one as the other is the
wrong-protocol fabrication the member exists to end.

**`eventbus` rather than `vertx_eventbus`, and the reason is a project rule rather than taste.**
`tests/architecture/test_source_rules.py` forbids the token `vertx` anywhere in Python or SQL:
framework knowledge is catalog data, never code. The member is therefore named for the *kind of
wire* — an addressed in-process/clustered event bus — exactly as `amqp` is named for the protocol
rather than for Rabbit. The comment beside it names Vert.x as the framework whose bus this is, in
the same breath as the constraint, so the next reader does not "fix" the name.

**`temporal` is a product name and is allowed**, on the `pulsar`/`rsocket` precedent: those members
name products too, because the wire protocol has no other name. The member's comment says so.

### 1b. Cadence is a boundary, not a member

Cadence (`com.uber.cadence`) declares annotations with the same simple names under a different
package and speaks a different wire protocol (Thrift, against a different service). It gets **no
rows at all**: the contract model (§2) names `io.temporal.*` coordinates only, so a Cadence module
records nothing and says so. COVERAGE's `Temporal / Cadence` row carries the boundary in words.

Rejected: folding Cadence under `temporal`, which would let a Cadence worker answer a Temporal
caller's row — a wrong-protocol link, which is the one thing the member exists to prevent. Also
rejected: a second member, which costs a second SDK measurement and a second fixture for a legacy
SDK that the Spring Boot estate this phase serves has left.

### 1c. Rendering

`temporal` joins `_VERBED_PROTOCOLS` in `egress/render/document.py`: every Temporal row carries a
kind in `method` — one of `workflow`, `signal`, `query`, `update`, `activity` — on the GraphQL
precedent, where `query`/`mutation`/`subscription` occupy the same column. The kind is part of what
the wire names: a signal `cancel` and a query `cancel` on one workflow type are two different
operations, and only the kind tells them apart.

`eventbus` is verbless. It is NOT added to `_VERBED_PROTOCOLS`, so it falls into
`_VERBLESS_PROTOCOLS` by construction (that set is the union's complement, which is why adding a
member to one list is enough), and an event-bus row renders its address alone.

### 1d. Temporal identity: `path` is the type, the task queue is metadata

**The decision, and the two candidates.** A task queue routes a workflow *start* and an activity
*task*; a signal, query or update goes to a running execution by workflow id and names no queue at
all, and `Workflow.newActivityStub(Iface.class)` with no options inherits the enclosing workflow's
queue, which the call site cannot see (M5). So queue-in-the-path would make most stub rows
`unresolved` and would give one protocol two path grammars.

**Chosen (D).** `path` is what the wire names as the type:

| kind | `path` | example |
|---|---|---|
| `workflow` | the workflow type | `OrderWorkflow` |
| `signal` / `query` / `update` | `<workflow type>/<member name>` | `OrderWorkflow/cancel` |
| `activity` | the activity type | `billing_ChargeCard` |

An activity's row carries the activity type **alone**: the interface name is not on the wire (M2,
M3 — the type is the prefix plus the member, or the explicit name), so putting it in the path would
publish an identity no worker polls for.

The task queue, wherever the code states it, is an `endpoint_metadata` row with
`kind: task_queue`, on inbound and outbound rows alike, `name` NULL (a queue has a value, not a
name — the Kafka-key precedent this column already documents) and `value` the queue. A placeholder
stays its `${…}` expression at `unresolved`, the ladder's ordinary behaviour.
`endpoint_metadata.kind` is catalog-declared and not a closed set in D00 — the column's own comment
says so — so `task_queue` needs no schema change.

**What (D) costs, stated rather than glossed.** Two modules serving the same workflow type on
different task queues produce rows that compare equal on identity. That is a *linking*-tier
question — both sides carry their queue, and a link whose two sides state different queues is
refusable there — and it is recorded as an open issue for that tier rather than built here. The
alternative cost was worse: a queue-less activity stub is the common spelling, and (C) would have
published every one of them as `unresolved`.

`peer` cannot carry the queue. D01 states it is the outbound target hint and **not part of wire
identity** (RC-5); a queue in `peer` would be invisible to the inbound side and would make one row's
identity depend on a column the merge deliberately ignores.

### 1e. Event-bus identity

`path` is the address string, verbatim. Nothing is composed and nothing is split: an event-bus
address is opaque, the `channel` rule `fluent` and `single_call` already keep for destinations.

A `localConsumer(...)` call, and a `@ConsumeEvent` whose `local` is `true` (its default — M9),
write an `endpoint_metadata` row `kind: delivery, value: local`. The linking tier can then refuse a
cross-module link into a consumer the bus will never deliver to from another node. A
`@ConsumeEvent(local = false)` writes `value: clustered`; a raw `consumer(...)` writes nothing,
because the raw call's reach depends on whether the Vert.x instance was built clustered, which the
call site does not state.

Inbound rows carry `request_shape` from the handler's payload parameter; outbound rows carry it from
the send's own `body_arg`. `request(...)` additionally carries `response_shape` from its declared
reply type.

---

## 2. Temporal: the contract model, and one word per engine

### 2a. What the capability is, and why it is shared

Every Temporal form has the same missing piece: code names a **type**, and the wire identities are
that type's **members**. `registerWorkflowImplementationTypes(OrderWorkflowImpl.class)` names one
class and registers four operations. No engine can do this today, and it is not a Temporal idea: a
JAX-WS `@WebService` endpoint interface, a gRPC service interface and a .NET service contract are
the same shape.

So the fold is shared, exactly as Group E shared `resolve/beans.py` behind `bean_via`:

**`resolve/contracts.py`** takes a type symbol and returns
`[(member_method_symbol, kind, wire_name, resolution)]`. It walks `type_hierarchy` upward from an
implementation class to the annotated interface — the SDK's own `getInterfaces()` recursion (§0 M1's
neighbourhood), and the reason the Spring Boot starter form resolves at all — reads the member
annotations, and applies the naming word. It names no framework: the annotations, the attributes
and the choice of naming word are all data.

**`catalogs/contract-models/temporal.yml`** is that data. It is a **model file, not a catalog**, in
the `bean-models`/`step-models` precedent exactly: no `style`, no `matches`, no boundary; outside
the `*.yml` glob that loads catalogs; named by a catalog with `contract_model: temporal` and handed
through by the loader as `Catalog.contract_model`; an id no file here carries is refused by file.

```yaml
id: temporal
interfaces:
  - annotation: io.temporal.workflow.WorkflowInterface
    members:
      - { annotation: io.temporal.workflow.WorkflowMethod, kind: workflow,
          name_attrs: [name], naming: interface_simple_name }
      - { annotation: io.temporal.workflow.SignalMethod, kind: signal,
          name_attrs: [name], naming: member_name }
      - { annotation: io.temporal.workflow.QueryMethod, kind: query,
          name_attrs: [name], naming: member_name }
      - { annotation: io.temporal.workflow.UpdateMethod, kind: update,
          name_attrs: [name], naming: member_name }
  - annotation: io.temporal.activity.ActivityInterface
    prefix_attrs: [namePrefix]
    all_members: true
    members:
      - { annotation: io.temporal.activity.ActivityMethod, kind: activity,
          name_attrs: [name], naming: prefixed_capitalized_member_name,
          name_skips_prefix: true }
```

`all_members: true` is declared on the activity interface and **not** on the workflow interface,
because M4 measured exactly that asymmetry: an unannotated method of an `@ActivityInterface` is an
activity; an unannotated method of a `@WorkflowInterface` is nothing. Declaring it on both would
publish every helper on a workflow interface as an operation — a false positive of the kind the
standing rule forbids.

### 2b. The naming words

Three words, a **closed vocabulary in engine code** with the model choosing one per member — the
`_PATH_FALLBACKS` pattern in `annotation_driven.py`, for its stated reason: the mechanics are
conventions of the language these facts come from, while *which* convention a framework picked is
the framework's own fact, and a typo must be refused rather than read as "no fallback".

| word | rule | measured |
|---|---|---|
| `interface_simple_name` | the declaring interface's simple name | M1 |
| `member_name` | the member method's own name | M1 |
| `prefixed_capitalized_member_name` | the interface's prefix attribute + the member name with its first character upper-cased | M2, M3 |

`name_skips_prefix: true` is a flag on the member rather than a fourth word: it is the same naming
rule with one branch — an explicitly named member takes its name verbatim and the prefix is not
applied (M2). Spelling it as a word would claim two rules where the SDK has one.

The first-character upper-casing is spelled where the member's own name is read, beside the
`getURL -> uRL` edge the accessor-strip rule already pins, and the Temporal edge that tells this
rule from every paraphrase of it is asserted: a member named `chargeCard` under
`namePrefix = "billing_"` is `billing_ChargeCard`, while `@ActivityMethod(name = "Charge")` under
the same prefix is `Charge`.

### 2c. The three reach forms

**1. The Spring Boot starter → a new engine, `engines/annotated_contract.py`.**
`@WorkflowImpl(taskQueues = {...})` / `@ActivityImpl(taskQueues = {...})` on an implementation class
(M6). The class annotation supplies the queues, the contract fold supplies the rows, `handler` is
the implementation's own override of the member — found through `type_hierarchy`, the same join the
fold already walks — and `direction` is `inbound`. One `task_queue` metadata row per array element.

`workers()` is **not** read: it names worker *beans*, configured elsewhere, and reading it would
publish a bean name as a task queue.

A new engine rather than a mode on `annotation_driven` (rejected approach C): every catalog that
engine serves assumes a construct's members are its own annotated methods, and "members come from an
implemented interface, the handler is the override" would be a second model inside a file eight
catalogs depend on. The new engine is `scheduled_work.py`-sized and reads the shared fold.

**2. The programmatic worker → `fluent`, two new words.**

```
factory.newWorker("orders")          → root, channel/queue from arg 0
       .registerWorkflowImplementationTypes(A.class, B.class)
       .registerActivitiesImplementations(new ChargeActivitiesImpl())
```

- `contract: argN` — read the argument as a **type**: a class literal directly, or an instance
  argument's declared type — and mint one row per member the fold returns. `direction: inbound`.
- `all_args: true` on a capture — read **every** element of a varargs call, not just the declared
  position: `registerWorkflowImplementationTypes(A.class, B.class)` is two types, one call. This is
  the `channel_via: {arg: all_strings}` idea one capture over, and it is spelled as a flag on the
  capture rather than a second sentinel value so that a future capture kind inherits it.

The queue is the root call's own argument: `fluent`'s native receiver tracking, unchanged.

**3. Client and workflow stubs → `fluent`, `direction: outbound`.**

```
client.newWorkflowStub(OrderWorkflow.class,
       WorkflowOptions.newBuilder().setTaskQueue("orders").build())
```

- `argument_chain: { arg: 1, owner: io.temporal.client.WorkflowOptions$Builder,
  method: setTaskQueue, arg: 0 }` — the third new word: walk the chain that **produced** an
  argument and read a value out of it. This is not a Temporal trick, which is why it is a word: the
  same walk reads Vert.x 5's `MessageConsumerOptions.setAddress` (§3, M8), and it is the natural
  generalisation of `channel_via`'s one-hop link to a chain of hops.

`caller` is the calling method; `handler` is NULL, the outbound shape. Untyped stubs need no
contract at all: `newUntypedWorkflowStub("OrderWorkflow", options)` and
`WorkflowStub.signal("cancel", …)` / `.query(…)` / `.update(…)` (M11) are plain `channel` captures
with the kind fixed per row. `Workflow.newActivityStub(Iface.class[, options])`,
`newLocalActivityStub` and `newChildWorkflowStub` are the same shape as the typed workflow stub,
with their own options owners (M5).

### 2d. Stated boundaries

Each of these is a form a reader would expect to derive, and each derives **nothing**, because
reading it would fabricate. All are recorded on the catalogs and in COVERAGE.

- `newWorkflowStub(Class, String workflowId)` and `newWorkflowStub(Class, String, Optional)`, and
  both `newExternalWorkflowStub` overloads: these address an **already-running execution** by id.
  They start nothing and name no queue; a row for them would claim an outbound start that the code
  does not make.
- `registerWorkflowImplementationFactory(Class, Func[, options])`: the type is readable, but the
  factory decides what is actually served. Left for a later measurement.
- An activity or child-workflow stub with no `setTaskQueue`: the row is derived with **no**
  `task_queue` metadata. The queue is inherited from the enclosing workflow at runtime and the call
  site does not state it; writing the enclosing worker's queue would be a guess that reads as an
  observation.
- Nexus services (`@NexusServiceImpl`, `newNexusServiceStub`), dynamic implementations
  (`DynamicWorkflow`/`DynamicActivity`, which declare no typed members at all), and Cadence.
- A workflow interface that **extends** another: the fold walks ancestors, so inherited members are
  found; but the SDK's duplicate-name validation is not reproduced — a module the SDK would refuse
  to start produces rows here.

---

## 3. The Vert.x event bus: three catalogs, no new engine

### 3a. `vertx-eventbus.yml` — the one-call forms (`single_call`)

`protocol: eventbus`, coordinate `io.vertx:vertx-core`. Every method here overloads on argument
type, so **every row declares its own erased JVM descriptor**, the rule `spring-rabbit-template.yml`
established after an overload collision published a payload as a destination.

| row | direction | reads |
|---|---|---|
| `send(String, Object)`, `send(String, Object, DeliveryOptions)` | outbound | `channel_arg: 0`, `body_arg: 1` |
| `publish(String, Object)`, `publish(String, Object, DeliveryOptions)` | outbound | `channel_arg: 0`, `body_arg: 1` |
| `request(String, Object)`, `request(String, Object, DeliveryOptions)` | outbound | `channel_arg: 0`, `body_arg: 1`; reply type → `response_shape` |
| `request(String, Object, Handler)`, `request(String, Object, DeliveryOptions, Handler)` | outbound | **4.5 only** (M8) |
| `consumer(String, Handler)`, `localConsumer(String, Handler)` | inbound | `channel_arg: 0`, handler at 1 |
| `consumer(MessageConsumerOptions[, Handler])` | inbound | **5.0 only** (M8); address through `argument_chain` into `setAddress` |

Both major versions are declared in one file. A declared overload absent from the version a module
builds against simply never matches — the ordinary "undeclared arity" shape, here turned around.

**Second owner:** `io.vertx.mutiny.core.eventbus.EventBus`, with its own descriptors (M10) — this is
what a Quarkus service injects. Its `request` returns `Uni`, its consumer handler is a
`java.util.function.Consumer`, and it declares no `sender`/`publisher`, so those rows are
raw-API-only.

### 3b. `vertx-eventbus-chain.yml` — the two-step forms (`fluent`)

M7 is the finding that decides this file's shape: `consumer(String, Handler)` **is**
`consumer(String).handler(h)`, so registration happens in `handler`. A `MessageConsumer` that never
receives a handler is registered with nothing and receives nothing — so a bare `consumer(addr)`
must derive **no row at all** until the chain reaches its terminal. That is `fluent`'s
`terminal` machinery, unchanged, and it is the same judgement `interface_implementation` records as
`registration.started_by` (`OI-64`): construction is not a boundary until something activates it.

- root `consumer(String)` / `localConsumer(String)` → `channel: arg0`; terminal
  `io.vertx.core.eventbus.MessageConsumer.handler`, `handler` captured from the terminal's arg 0;
  `direction: inbound`.
- root `sender(String)` / `publisher(String)` → `channel: arg0`; terminal
  `io.vertx.core.eventbus.MessageProducer.write` (and 4.5's `write(T, Handler)`), `body` from the
  terminal's arg 0; `direction: outbound`.

Group E's chain rules apply unchanged: `undeclared_steps`, sticky `poisons:`, and the cross-method
limit (a consumer handed to another method before `.handler` is not followed).

### 3c. `quarkus-consume-event.yml` — `@ConsumeEvent` (`annotation_driven`)

Coordinate `io.quarkus:quarkus-vertx`. `path_from: [value]`, `direction: inbound`, the request shape
from the method's sole parameter — or from the **second** parameter where the first is a `MultiMap`,
which is Quarkus's own headers/body split and is enforced by its processor.

Two measured rules carry this file, and getting either backwards would publish something false:

- **`path_fallback: declaring_type_qualified_name`** — a fourth word in `_PATH_FALLBACKS`, stripping
  no prefixes. The default address is the declaring bean class's **fully-qualified** name (M9), not
  the method name (`construct_name` would give that) and not the simple name.
- **`local()` defaults to `true`** (M9). An undecorated `@ConsumeEvent` is a local-only consumer, so
  the `delivery: local` metadata row of §1e is written **unless** `local = false` is stated. The
  reverse default would publish every Quarkus consumer as cluster-reachable.

A `${…}` address is carried verbatim at `unresolved` — the recorder resolves it at runtime against
the deployed configuration, and §8.2 keeps this repository out of guessing deployed values.

### 3d. Stated boundaries

- The SockJS/TCP **event-bus bridge** (`PermittedOptions.setAddressRegex`, `setAddress`): a regex is
  not an address, and the bridge's own permitted-address list is a policy rather than a consumer.
- `Message.reply(...)`: addresses a reply-to address the sender generated, which is on no
  declaration.
- A `MessageConsumer` or `MessageProducer` handed to another method before its terminal — Group E's
  cross-method limit, recorded as an open issue of the same shape as `OI-110`.
- `@ConsumeEvent` on a method of a `@Dependent`-scoped bean that is never instantiated.
- Vert.x 3.x, whose `send` carried a reply handler at a position 4.x and 5.x do not.

---

## 4. Fixtures

**`fixtures/temporal-probe`** (Maven, offline-buildable, the `spring-integration-probe` pattern):

- `OrderWorkflow` — `@WorkflowInterface` with `@WorkflowMethod` (no name → `OrderWorkflow`, M1), a
  `@SignalMethod` `cancel`, a `@QueryMethod` `status`, an `@UpdateMethod` `amend`.
- `ShipmentWorkflow` — `@WorkflowMethod(name = "ShipOrder")`, so the interface-name default is
  proved *against* an override rather than only by itself.
- `BillingActivities` — `@ActivityInterface(namePrefix = "billing_")` with
  `@ActivityMethod(name = "Charge") void charge(...)` (→ `Charge`, prefix skipped, M2) and a bare
  `void refundCard(...)` (→ `billing_RefundCard`, M3, M4).
- `OrderWorkflowImpl` — `@WorkflowImpl(taskQueues = "orders")`; `BillingActivitiesImpl` —
  `@ActivityImpl(taskQueues = {"billing", "billing-retry"})`.
- A programmatic worker: `factory.newWorker("orders")`,
  `registerWorkflowImplementationTypes(OrderWorkflowImpl.class, ShipmentWorkflowImpl.class)`,
  `registerActivitiesImplementations(new BillingActivitiesImpl())`.
- A client: a typed start with `setTaskQueue("orders")`; an untyped
  `newUntypedWorkflowStub("OrderWorkflow", …)`; a `stub.signal("cancel", …)`; a
  `Workflow.newActivityStub(BillingActivities.class)` with **no** options (the queue-less row).
- **Variance arms that must derive nothing:** `newWorkflowStub(OrderWorkflow.class, "wf-123")`, a
  `registerWorkflowImplementationFactory` call, and a helper method on a workflow interface carrying
  no member annotation.

**`fixtures/orders-eventbus`** (Maven):

- Raw: `send`, `publish`, `request`, `consumer(addr, handler)`, `localConsumer(addr, handler)`.
- Two-step: `consumer(addr)` … `.handler(…)`; `sender(addr).write(…)`.
- **Variance arm:** a `consumer(addr)` that is never given a handler — derives nothing (M7).
- Quarkus arm: `@ConsumeEvent("orders.created")`; a bare `@ConsumeEvent` (→ the class FQN, M9);
  `@ConsumeEvent(value = "orders.shipped", local = false)`; `@ConsumeEvent("${orders.address}")`
  staying `unresolved`; one method taking `(MultiMap, Order)`.

---

## 5. Tests

- `tests/e2e/test_async_delivered.py` gains `test_temporal_shapes_rows` and
  `test_eventbus_shapes_rows`, each asserting the full row set off a real analysis of its fixture —
  path, kind, direction, handler/caller and the `task_queue`/`delivery` metadata.
- A strict-xfail per boundary a reader would expect to derive: the queue-less activity stub's absent
  metadata, the running-execution stub, the handler-less consumer, the factory registration.
- Unit tests beside their peers for `resolve/contracts.py` (the four naming branches, the
  activity/workflow asymmetry, the ancestor walk) and for the three new `fluent` words plus the new
  `path_fallback` word — including each word's catalog-error path, since a closed vocabulary that
  does not refuse a typo is the hole it exists to close.
- `tests/architecture` needs no new rule, and the two it already enforces are the gate: no framework
  or language name enters `src/sextant` (§1a), and every probe cited carries §5.4 provenance.

---

## 6. Probes

**`scripts/probes/cp30_temporal_contract_naming/`** — pins M1–M6 by `javap` on temporal-sdk 1.27.0
and temporal-spring-boot-autoconfigure 1.27.0: the four naming branches, the activity qualification
rule, the two starter annotations' attributes, and every options builder's `setTaskQueue`.

**`scripts/probes/cp31_eventbus_surface/`** — pins M7–M10 by `javap` on vertx-core 4.5.10 **and**
5.0.0, smallrye-mutiny-vertx-core 3.16.0, quarkus-vertx 3.17.5 and quarkus-vertx-deployment 3.17.5:
every declared descriptor per version, the `consumer` → `handler` delegation, `@ConsumeEvent`'s
`AnnotationDefault` values, and the default-address call in `VertxProcessor`.

Both follow the CP-27 harness shape: the version column comes from each jar's own manifest and a jar
reporting another version aborts the run; the last row reads the committed fixture's own compiled
classes. Nothing is executed — every cell is a `javap` read.

---

## 7. Files

| file | change |
|---|---|
| `src/sextant/domain/closed_sets.py` | `TEMPORAL`, `EVENTBUS`, one edit, each with its DR-5 comment |
| `src/sextant/egress/render/document.py` | `temporal` into `_VERBED_PROTOCOLS` |
| `src/sextant/application/resolve/contracts.py` | **new** — the shared fold and the naming vocabulary |
| `src/sextant/catalogs/contract-models/temporal.yml` | **new** — the model file |
| `src/sextant/ingress/catalogs/yaml_source.py` | `contract_model` in `_MODEL_DIRECTORIES` |
| `src/sextant/application/ports/catalogs.py` | `Catalog.contract_model` |
| `src/sextant/application/resolve/engines/annotated_contract.py` | **new** — the class-annotation form |
| `src/sextant/application/resolve/engines/fluent.py` | `contract`, `all_args`, `argument_chain` |
| `src/sextant/application/resolve/engines/single_call.py` | `argument_chain` (shared with `fluent`) |
| `src/sextant/application/resolve/engines/annotation_driven.py` | `declaring_type_qualified_name` |
| catalogs | `temporal-worker.yml`, `temporal-client.yml`, `temporal-spring-boot.yml`, `vertx-eventbus.yml`, `vertx-eventbus-chain.yml`, `quarkus-consume-event.yml` |
| fixtures | `temporal-probe`, `orders-eventbus` |
| probes | `cp30_temporal_contract_naming`, `cp31_eventbus_surface` |
| docs | `java-kotlin-delivery-list.md`, `COVERAGE.md`, `open-issues.md` |

---

## 8. The register afterwards

```delivery``` loses `temporal-cadence` and `vertx-eventbus`; the **Async** column empties and the
row closes — what §4's order table row 4 promised. Category C loses its last two items, leaving
`apache-camel` (REST out) and `smallrye-reactive-messaging` (Kafka) as the only unsequenced work.

COVERAGE §5.12 gains two shipped framework lines with their boundaries; the `Temporal / Cadence` and
`Vert.x` rows of the Java/Kotlin framework matrix lose their `◐`. `scripts/coverage_matrix.py` already lists both
framework names under "Async and internal boundaries"; its `ITEM_FRAMEWORKS` entries for
`temporal-cadence` and `vertx-eventbus` go with the ids they map, since an entry for an id the
register no longer carries is data pointing at nothing.

New open issues expected: the cross-module task-queue link rule for the linking tier (§1d); a
Cadence re-measurement trigger (§1b); a `MessageConsumer`/`MessageProducer` handed across methods
(§3d); `registerWorkflowImplementationFactory` (§2d).

---

## 9. Self-review

**Placeholders:** none — every key, word and row above is named with its value or its measurement.

**Internal consistency:** §1c's verbed/verbless split matches §1d's kinds and §1e's silence;
§2c's three forms each name the engine §7 changes; §3's per-version rows match M8 and the fixture
arms in §4.

**No false positives, checked form by form:** the activity/workflow `all_members` asymmetry (M4);
the prefix-skipping branch (M2); `local()`'s true default (M9); the handler-less consumer deriving
nothing (M7); the running-execution stubs deriving nothing (§2d); the queue-less stub carrying no
guessed queue (§1d). Each is a place where the obvious reading would have published something the
framework does not do.

**Future-language compatibility:** the contract fold, the three naming words and `argument_chain`
are all framework-neutral; the two framework names that had to be written down live in catalogs and
in a model file. `eventbus`'s name is chosen so the architecture rule stays green (§1a).

**Over-engineering:** the two biggest candidates were rejected — a Cadence member (§1b) and
queue-in-the-path (§1d). `annotated_contract.py` is the one new engine, and §2c states why the
alternative was worse rather than merely different.
