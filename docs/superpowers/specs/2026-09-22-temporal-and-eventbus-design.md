# Temporal workflows and the Vert.x event bus: two new protocols (register Group D)

**Status:** design. Approved in conversation 2026-09-22, section by section, then **rewritten after
an adversarial self-review** whose three Major findings the user ruled on one at a time (§0a). Scope
set by the user's rulings, each recorded where it binds: Temporal derives **workflows, activities,
signals, queries and updates** (§2); **Cadence is a stated boundary**, not a second member (§1b);
Vert.x covers **the raw API, Quarkus `@ConsumeEvent` and the two-step consumer** (§3); the Temporal
capability is built **on `annotation_driven`**, not on a new engine (§0a M-1); qualifying attributes
are recorded by **one generic `metadata_from` key applied across every listener catalog at once**
(§0a M-2); and member enumeration is fenced by a **new `declared_type_methods` word** (§0a M-3).

**Closes:** `temporal-cadence` and `vertx-eventbus`, the two entries the register's §4 order table
calls "D. New `Protocol` members and two naming words", and with them Category C's last two items.
**Rides along:** the qualifying attributes the shipped listener catalogs drop today — Kafka's
consumer group, JMS's selector and durable subscription, Rabbit's exclusivity (§2e).
**Rows it changes:** the **Async** column of the register's ```delivery``` block empties — the row
closes. COVERAGE §5.12 gains two shipped framework lines; §§5.8–5.9 gain the recorded attributes.

Every factual claim below carries the command that produces it, or names the probe (§6) that must
record it before the key it forces is written. Claims marked **measured 2026-09-22** were verified
during this design conversation, by `javap` on the jars named beside them.
**A probe that contradicts a section here changes the section, not the probe** (GUIDELINES §1.1).

**Standing requirements.** **No false positives** (user rule, 2026-09-20): a workflow type, an
activity name, an address or a handler is written only where the code states it and the framework
honours it; every ambiguity is an unresolved column or an absent row, never a guess. Misses are
acceptable and are stated on the catalog and in COVERAGE. The resolve layer names no framework and
no language (`tests/architecture/test_source_rules.py`, `test_language_confinement.py`) — §1a
records the one place that constraint chose a name. **Existing output moves only where §2e says it
does**, and where it does, the e2e tests that pin it move with it in the same task.

---

## 0. What the jars say

Measured 2026-09-22 on: temporal-sdk 1.27.0, temporal-spring-boot-autoconfigure 1.27.0,
vertx-core 4.5.10 and 5.0.0, quarkus-vertx 3.17.5, quarkus-vertx-deployment 3.17.5,
smallrye-mutiny-vertx-core 3.16.0.

| # | Finding | Carried by |
|---|---|---|
| M1 | `@WorkflowMethod`'s default name is the **workflow interface's simple name**, not the method's: `POJOWorkflowMethodMetadata.<init>` branches on `getType() == WORKFLOW` and calls `Class.getSimpleName()` on the interface at offset 101, falling to `Method.getName()` at 122 for every other kind | §2b's `declaring_type_simple_name` / `construct_name` |
| M2 | An `@ActivityMethod(name = "X")` with a non-empty name is used **verbatim, with no prefix**: `POJOActivityMethodMetadata.<init>` tests `name().isEmpty()` at offset 50 and returns the annotation's own value at 58; only the empty branch composes `namePrefix()` + `getActivityNameFromMethod(...)` | §2b — the prefix lives *inside* the fallback word, so a named member skips it by construction |
| M3 | The activity default is `namePrefix` + the method name with its **first character upper-cased**: `getActivityNameFromMethod` = `substring(0,1).toUpperCase()` + `substring(1)` | §2b's `prefixed_capitalized_construct_name` |
| M4 | **Every** non-static, non-synthetic declared method of an `@ActivityInterface` is an activity, annotated or not: `validateAndQualifiedForActivityMethod` returns `true` at offset 73 for an unannotated method and `false` only for static or synthetic ones. An unannotated method of a **workflow** interface mints nothing — *but not for the reason this row first gave, and CP-30 Q5 is the correction: `validateAndQualifiedForWorkflowMethod` returns `true` at offset 82 for an unannotated method too, structurally identical to the activity predicate. The annotated-only filter is a separate `getType() == NONE` check in `getWorkflowInterfaceMethods`, after the predicate returns. The outcome the design rests on is unchanged; the citation was wrong* | §2c's `members: declared_type_methods`, declared on the activity catalogs alone |
| M5 | The task queue is named on `WorkerFactory.newWorker(String[, WorkerOptions])` and on **four** options builders' `setTaskQueue(String)` — `ActivityOptions`, `WorkflowOptions`, `ChildWorkflowOptions` and `ContinueAsNewOptions` (*this row said three; CP-30 Q8 counted the fourth. No design consequence — the queue is read only from the starter annotations*) — never on an SDK annotation. The Spring Boot starter's `@WorkflowImpl`/`@ActivityImpl`/`@NexusServiceImpl` each declare `String[] workers()` and `String[] taskQueues()` | §1d's rule; §2d's `metadata_from` |
| M6 | `EventBus.consumer(String, Handler)` **is** `consumer(String)` followed by `MessageConsumer.handler(h)`: `EventBusImpl.consumer(String, Handler)` calls `consumer:(Ljava/lang/String;)` at offset 9 and `MessageConsumer.handler` at 15 | §3b's two-step chain and its terminal |
| M7 | vertx-core 4.5.10 and 5.0.0 differ: 4.5 has the callback `request(String, Object, Handler)`, `(String, Object, DeliveryOptions, Handler)` and `MessageProducer.write(T, Handler)`, none of which exist at 5.0.0; 5.0.0 adds `consumer(MessageConsumerOptions[, Handler])`, whose address sits in `MessageConsumerOptions.setAddress(String)` | §3a's per-version rows; §3d's builder-tail boundary |
| M8 | Quarkus `@ConsumeEvent`'s default address is the **declaring bean class's fully-qualified name**: `VertxProcessor` calls `AnnotationProxyBuilder.withDefaultValue("value", BeanInfo.getBeanClass().toString())` at offsets 63–76. `@ConsumeEvent`'s own `AnnotationDefault` for `value()` is `""` and for `local()` is **`true`** | §3c's `declaring_type_qualified_name` and its `metadata_from` entry's `absent_value` |
| M9 | The Mutiny facade `io.vertx.mutiny.core.eventbus.EventBus` declares `send`/`publish`/`request`/`consumer`/`localConsumer` with its own descriptors — `request` returns `io.smallrye.mutiny.Uni`, `consumer`'s handler is a `java.util.function.Consumer` — and declares **no `sender`/`publisher` at all** | §3a's second owner |
| M10 | `WorkflowClient.newUntypedWorkflowStub(String, …)` names the **workflow type** at argument 0; `WorkflowStub.signal/query/update(String, …)` name a **member** at argument 0 with no workflow type at the call site | §2f: the first derives, the second does not |

### 0a. What the adversarial self-review changed

| # | Finding | Severity | Ruling |
|---|---|---|---|
| M-1 | §2 built a new engine, a new `contract-models/` file kind and a shared `resolve/contracts.py` for what `annotation_driven` already does — the interface→implementor annotation inheritance walk (`effective_annotations.py`, interfaces *and* superclasses), `members` with its ancestry walk, per-annotation `method: [kind]` and per-annotation `path_fallback`, and the `declared_on: class`/`declared_on: interface` partition `jakarta-jws.yml`/`jakarta-jws-client.yml` already use to split one annotation into an inbound and an outbound catalog | **Major** | **(a)** Rewrite onto `annotation_driven`. The new engine, model kind and fold are deleted before they are written; §2 is four catalogs plus three words in vocabularies that already exist |
| M-2 | With M-1 resolved, nothing could write the task queue at all — `endpoint_metadata` has exactly two producers (`request_requirements.py`, `fluent`) and neither is reachable from `annotation_driven`. The same hole silently drops `@KafkaListener(groupId)`, `@JmsListener(selector)`/`(subscription)` and `@ConsumeEvent(local)` | **Major** | **(b)** Build a generic `metadata_from` key and **apply it across every listener catalog in this group**, not only the new ones. §1f states the rule that decides path-vs-metadata; §2e lists the attributes and the tests that move with them |
| M-3 | `members: public_methods` enumerates the **gated class's** members, and the gate fires on the impl class (the annotation is inherited onto it) — so a public helper on an activity implementation would publish as an activity nothing polls. JAX-WS does not have this problem because the framework really does expose every public method; Temporal exposes the interface's | **Major** | **(a)** A new member word `declared_type_methods`: enumerate only members whose declaring type carries the type annotation **directly**, never by inheritance |
| m-1 | `argument_chain` (a new `fluent`/`single_call` word) was proposed for reading a value out of an argument's producing chain | minor | Deleted. The existing `channel_via` reads a value off an argument's producing call, which covers `new MessageConsumerOptions().setAddress("x")`; the builder-tail spelling is a stated boundary (§3d) |
| m-2 | `contract: argN` and `all_args: true` (two more new `fluent` words) | minor | Deleted — both existed only for `registerWorkflowImplementationTypes(A.class, B.class)`, which is no longer a row source |
| m-3 | Activity naming needed a prefix key plus a `name_skips_prefix` flag | minor | Collapsed into one `path_fallback` word that composes the prefix itself, so an explicitly named member skips it by construction — which is the branch M2 measured |
| m-4 | The naming words were named for Temporal's own vocabulary | minor | Renamed into the existing one: `declaring_type_simple_name`, `declaring_type_qualified_name`, `prefixed_capitalized_construct_name`, all beside `construct_name` in `_PATH_FALLBACKS` |
| m-5 | `tests/architecture/test_source_rules.py`'s `PROTOCOLS` set would not contain the two new names, leaving them the only protocol names a storage file may mention | minor | Both added in the same edit as the members |
| p-1 | CP-30 falsified two §0 rows during implementation: M4's workflow half cited the wrong method, and M5 counted three options builders where the jar declares four. Both rows amended in place with the probe's finding; neither changes a catalog | measurement | Amended 2026-09-22 (Task 2). The probe changes the spec, never the reverse (GUIDELINES §1.1) |
| m-6 | Untyped stubs were specified as one family | minor | Split by what the call site states (M10): `newUntypedWorkflowStub("OrderWorkflow", …)` derives; `WorkflowStub.signal("cancel", …)` does not, because a bare member name with no workflow type would be an identity that collides with every other workflow's signal |

---

## 1. Schema

### 1a. The two members

`closed_sets.py` gains `TEMPORAL = "temporal"` and `EVENTBUS = "eventbus"`, added in **one edit**
for the reason the file already states twice (the 2H and 2O blocks): the set is closed, so a member
a later task needs costs one line now and a schema change if it arrives alone.

Each is its own protocol on the DR-5 argument the `AMQP`/`PULSAR` and `RSOCKET` blocks make: linking
gates on protocol equality, and a Temporal workflow type can only ever be answered by a Temporal
worker, an event-bus address only by an event-bus consumer.

**`eventbus` rather than `vertx_eventbus`, and the reason is a project rule rather than taste.**
`test_source_rules.py` forbids the token `vertx` anywhere in Python or SQL. The member is named for
the *kind of wire* — an addressed in-process/clustered event bus — exactly as `amqp` is named for the
protocol rather than for Rabbit; its comment names Vert.x so the next reader does not "fix" it.
**`temporal` is a product name and is allowed**, on the `pulsar`/`rsocket` precedent: those name
products too, because the wire has no other name.

Both names are added to `test_source_rules.PROTOCOLS` in the same edit (m-5).

### 1b. Cadence is a boundary, not a member

Cadence (`com.uber.cadence`) declares annotations with the same simple names under a different
package and speaks a different wire protocol. It gets **no rows at all**: every catalog here names
`io.temporal.*` coordinates only. COVERAGE's `Temporal / Cadence` row carries the boundary in words.
Folding it under `temporal` would let a Cadence worker answer a Temporal caller — the wrong-protocol
link the member exists to prevent; a second member costs a second measurement and a second fixture
for an SDK this phase's estate has left.

### 1c. Rendering

`temporal` joins `_VERBED_PROTOCOLS`: every Temporal row carries its kind in `method` — `workflow`,
`signal`, `query`, `update` or `activity` — on the GraphQL precedent, where `query`/`mutation`
occupy the same column. The kind is part of what the wire names: a signal `cancel` and a query
`cancel` on one type are different operations. `eventbus` is verbless and is added to no list —
`_VERBLESS_PROTOCOLS` is the complement, so one edit is enough.

### 1d. Temporal identity

| kind | `path` | example |
|---|---|---|
| `workflow` | the workflow type | `OrderWorkflow` |
| `signal` / `query` / `update` | `<workflow type>/<member name>` | `OrderWorkflow/cancel` |
| `activity` | the activity type | `billing_ChargeCard` |

An activity's row carries the activity type **alone** — the interface name is not on the wire (M2,
M3), so putting it in the path would publish an identity no worker polls for.

The task queue is **not** in the path, and §1f states the rule that decides this rather than leaving
it as a Temporal preference. It is recorded as an `endpoint_metadata` row (`kind: task_queue`,
`name` NULL, `value` the queue) wherever a declaration states it (M5) — §2d.

### 1e. Event-bus identity

`path` is the address string, verbatim; nothing is composed and nothing is split, the `channel` rule
every destination protocol already keeps. Inbound rows carry `request_shape` from the handler's
payload parameter, outbound rows from the send's own `body_arg`, and `request(...)` carries
`response_shape` from its declared reply type.

### 1f. The rule that decides path versus metadata

A qualifying attribute is either **routing** (it changes which endpoint a message arrives at) or
**behavioural** (it changes what happens once the message arrives):

| attribute | class | why |
|---|---|---|
| Temporal task queue | routing | a worker on `orders` never sees `orders-staging` work |
| Kafka `groupId` | behavioural | every consumer group on a topic receives every message |
| JMS `selector` | behavioural | the message arrives at the destination, then is filtered |
| JMS `subscription` | behavioural | names a durable subscription's state, not the destination |
| `@ConsumeEvent(local)` | behavioural | scopes reachability; it does not re-address |

> **A routing fact enters the path only when BOTH sides of the wire can read it. Where only one side
> can, it is an `endpoint_metadata` entry, and the linking tier uses it as a refinement: two rows
> whose stated values differ do not link; a row that states nothing links as before.**

The task queue is a routing fact that fails the both-sides test, and the reason is structural rather
than incidental. Under §2 an outbound row comes from the **interface declaration**, so the caller's
side can never read `setTaskQueue` at all: a queue in the path would make the inbound row
`{orders}OrderWorkflow` and the outbound row `OrderWorkflow`, and the two halves of one wire would
never match. An identity half only one side can spell is not an identity. Everything in the table
therefore lands in `endpoint_metadata`, for two different stated reasons.

`endpoint_metadata.kind` is catalog-declared and not a closed set in D00 — the column's own comment
says so — so `task_queue`, `consumer_group`, `selector`, `subscription` and `delivery` need no
schema change. The linking refinement is recorded as an open issue for that tier, not built here.

---

## 2. Temporal, on `annotation_driven`

### 2a. Why no new engine

Every piece Temporal needs already ships, is measured against a framework, and is pinned by tests:

| need | mechanism | shipped in |
|---|---|---|
| a class gate that fires on an annotation the class inherits from its interface | `type_annotation` + the inheritance walk over interfaces *and* superclasses (`run_inheritance` turns on exactly when a catalog declares `type_annotation`) | `effective_annotations.py`, `jakarta-jaxrs.yml` |
| the interface method's annotation reaching the implementor's override | synthetic annotation rows (`_synthetic_annotations`) | same |
| one kind per annotation in the `method` column | `annotations: [{fqn, method: [kind]}]` with `all_methods: []` | `microprofile-graphql.yml` |
| a different naming rule per annotation | per-entry `path_fallback` | same (CP-15, measured per direction) |
| unannotated interface methods as members | `members` + the ancestry walk | `jakarta-jws.yml` (CP-13) |
| one annotation split into an inbound and an outbound catalog without double-publishing | `declared_on: class` / `declared_on: interface`, the latter subtracting every interface the module implements | `jakarta-jws.yml` + `jakarta-jws-client.yml` |

**What that costs, stated.** Rows come from the declaration, not from the registration call:
`WorkerFactory.newWorker("orders")` + `registerWorkflowImplementationTypes(…)` is no longer a row
source (it contributes nothing this design reads — §2g). An impl class registered with no worker
derives rows, the same exposure `@WebService` and `@Path` classes already carry. A client module
that depends on a contract **jar** rather than declaring the interface locally derives nothing —
the limitation Feign and the JWS client already have, stated in COVERAGE.

### 2b. The naming words

Three additions to `_PATH_FALLBACKS`, the closed vocabulary that already refuses a typo rather than
reading it as "no fallback":

| word | rule | measured |
|---|---|---|
| `declaring_type_simple_name` | the simple name of the type that **declared** the annotated member — the interface, not the implementor | M1 |
| `prefixed_capitalized_construct_name` | the declaring type's prefix attribute + the member name with its first character upper-cased | M2, M3 |
| `declaring_type_qualified_name` | the declaring type's fully-qualified name (Quarkus, §3c) | M8 |

The prefix lives **inside** the second word rather than in `path_prefix`/`path_separator`, and that
is what makes M2 free: a member carrying an explicit name never reaches its fallback, so the prefix
is skipped by construction instead of by a flag. The edge that tells this rule from every paraphrase
is asserted: `chargeCard` under `namePrefix = "billing_"` is `billing_ChargeCard`, while
`@ActivityMethod(name = "Charge")` under the same prefix is `Charge`.

`declaring_type_*` reads the type that declared the annotation, which under the inheritance walk is
the interface even though the row's handler is the implementor's override. That distinction is the
whole of M1 and is asserted on the fixture's two-workflow arm.

### 2c. The member word

`members: declared_type_methods` — enumerate only members whose declaring type carries the catalog's
type annotation **directly**, never by inheritance. M4 is why the activity catalogs need a member
rule at all, and M-3 is why they cannot use `public_methods`:

```java
@ActivityInterface(namePrefix = "billing_")
interface BillingActivities { void chargeCard(Charge c); }

class BillingActivitiesImpl implements BillingActivities {
    public void chargeCard(Charge c) { … }   // billing_ChargeCard — an activity
    public void reloadRates() { … }          // declared here, not on the interface — NOT an activity
}
```

`public_methods` publishes `billing_ReloadRates`, an endpoint nothing polls. The new word is one
conjunct — the declaring type's annotation row must be a real one rather than a synthetic
(inherited) one — and it is the rule any contract-interface framework follows. It carries a negative
test as well as a positive one, because this vocabulary's own comment calls it the sharpest in the
engine: a word read as something it is not mints endpoints out of ordinary methods.

### 2d. `metadata_from`, and the four catalogs

`metadata_from` is a new `annotation_driven` key: a list of `{annotation, attribute, kind}`, with an
optional `absent_value` for an attribute whose `AnnotationDefault` carries the meaning. Each present
attribute becomes one `endpoint_metadata` row against the endpoint that declaration minted; an array
attribute becomes one row per element; a `${…}` value stays `unresolved`; the existing
`endpoint_metadata_insert` is reused unchanged.

The four Temporal catalogs, all `protocol: temporal`, all `style: annotation_driven`:

```yaml
# temporal-workflow.yml            direction: inbound      declared_on: class
# temporal-workflow-client.yml     direction: outbound     declared_on: interface
type_annotation: io.temporal.workflow.WorkflowInterface
mapping:
  method_from: method
  all_methods: []
  annotations:
    - { fqn: io.temporal.workflow.WorkflowMethod, method: [workflow],
        path_fallback: declaring_type_simple_name }
    - { fqn: io.temporal.workflow.SignalMethod, method: [signal], path_fallback: construct_name }
    - { fqn: io.temporal.workflow.QueryMethod,  method: [query],  path_fallback: construct_name }
    - { fqn: io.temporal.workflow.UpdateMethod, method: [update], path_fallback: construct_name }
metadata_from:                       # inbound file only — a client states no queue
  - { annotation: io.temporal.spring.boot.WorkflowImpl, attribute: taskQueues, kind: task_queue }

# temporal-activity.yml             direction: inbound      declared_on: class
# temporal-activity-client.yml      direction: outbound     declared_on: interface
type_annotation: io.temporal.activity.ActivityInterface
mapping:
  members: declared_type_methods
  path_fallback: prefixed_capitalized_construct_name
  method_from: method
  all_methods: []
  annotations:
    - { fqn: io.temporal.activity.ActivityMethod, method: [activity] }
metadata_from:
  - { annotation: io.temporal.spring.boot.ActivityImpl, attribute: taskQueues, kind: task_queue }
```

The signal/query/update path is composed `<workflow type>/<member>` by the existing prefix
machinery, with the workflow type supplied by the same `declaring_type_simple_name` read the
`@WorkflowMethod` row uses — one composition rule, not a second grammar.

### 2e. The same key, applied to the shipped listener catalogs

The user's ruling (M-2, option b) is that this lands in one change rather than as a follow-up. The
criterion for an attribute is stated so the list is not open-ended: **an attribute a peer would care
about** — whether and how a message reaches this handler — never a tuning knob. So the consumer
group, the selector, the durable subscription name and exclusivity are recorded; `concurrency`,
`ackMode`, `containerFactory`, `errorHandler` and `autoStartup` are not, and the catalogs say so.

| catalog | attribute | `kind` |
|---|---|---|
| `spring-kafka.yml`, `micronaut-kafka.yml` | `groupId` | `consumer_group` |
| `spring-jms.yml`, `micronaut-jms.yml` | `selector`, `subscription` | `selector`, `subscription` |
| `spring-rabbit.yml` | `exclusive` | `delivery` |
| `quarkus-consume-event.yml` | `local` (`absent_value: true`) | `delivery` |

**This moves shipped output**, which the standing requirements otherwise forbid: existing endpoints
gain `endpoint_metadata` rows. Every attribute is measured by probe (§6) before its line is written,
and the tests that read `endpoint_metadata` — `tests/e2e/test_vertical_slice.py`,
`tests/e2e/test_rest_inbound_delivered.py`, and the four `tests/application` suites — are updated in
the same task as the catalog line that moves them, never in a later one.

### 2f. The untyped stub

One `single_call` catalog, `temporal-untyped.yml`, `direction: outbound`, one row:
`WorkflowClient.newUntypedWorkflowStub(String, …)` with `channel_arg: 0` — the string is the
workflow type (M10), so the row's path matches what §2d's inbound catalog derives.

`WorkflowStub.signal/query/update(String, …)` are **not** declared. Their string is a member name
with no workflow type at the call site, so the row's path would be a bare `cancel` — an identity
that collides with every other workflow's signal of that name. Under-reporting is honest; a
colliding identity is the fabrication class the standing rule forbids.

### 2g. Stated boundaries

- **The programmatic worker.** `WorkerFactory.newWorker("orders")` +
  `registerWorkflowImplementationTypes(…)` / `registerActivitiesImplementations(…)` contributes
  nothing: the rows come from the impl class's own declaration, and the queue is read only from the
  starter annotations (M5). A module that registers its workers programmatically therefore derives
  its rows **without** a `task_queue` entry. Recorded as an open issue with the mechanism it would
  need (an engine attaching metadata to another engine's rows), which does not exist today.
- **A contract in a jar.** A client module that does not declare the `@WorkflowInterface` itself
  derives nothing — Feign's and the JWS client's own limitation.
- **`newWorkflowStub(Class, String workflowId)`, `newExternalWorkflowStub`**: these address a
  running execution and start nothing; no call site is read for them at all under §2.
- **`registerWorkflowImplementationFactory`**, Nexus services, dynamic (`DynamicWorkflow`)
  implementations, and Cadence.
- **The SDK's duplicate-name validation** is not reproduced: a module the SDK would refuse to start
  produces rows here.

---

## 3. The Vert.x event bus

### 3a. `vertx-eventbus.yml` — the one-call forms (`single_call`)

`protocol: eventbus`, coordinate `io.vertx:vertx-core`. Every method overloads on argument type, so
**every row declares its own erased JVM descriptor** — the rule `spring-rabbit-template.yml`
established after an overload collision published a payload as a destination.

| row | direction | reads |
|---|---|---|
| `send`, `publish` (both arities) | outbound | `channel_arg: 0`, `body_arg: 1` |
| `request(String, Object)`, `(String, Object, DeliveryOptions)` | outbound | same; reply type → `response_shape` |
| `request(String, Object, Handler)`, `(String, Object, DeliveryOptions, Handler)` | outbound | **4.5 only** (M7) |
| `consumer(String, Handler)`, `localConsumer(String, Handler)` | inbound | `channel_arg: 0`, handler at 1 |
| `consumer(MessageConsumerOptions[, Handler])` | inbound | **5.0 only** (M7); address through the existing `channel_via` into `setAddress` |

Both major versions are declared in one file; an overload absent from the version a module builds
against simply never matches. **Second owner:** the Mutiny facade (M9), which is what a Quarkus
service injects, with its own descriptors and no `sender`/`publisher`.

### 3b. `vertx-eventbus-chain.yml` — the two-step forms (`fluent`)

M6 decides this file's shape: `consumer(String, Handler)` **is** `consumer(String).handler(h)`, so
registration happens in `handler`, and a consumer never given one receives nothing. A bare
`consumer(addr)` therefore derives **no row** until the chain reaches its terminal — `fluent`'s
existing `terminal` machinery, and the same judgement `interface_implementation` records as
`registration.started_by` (`OI-64`).

- root `consumer(String)` / `localConsumer(String)` → `channel: arg0`; terminal
  `MessageConsumer.handler`, `handler` from its arg 0; `direction: inbound`.
- root `sender(String)` / `publisher(String)` → `channel: arg0`; terminal `MessageProducer.write`
  (and 4.5's `write(T, Handler)`), `body` from its arg 0; `direction: outbound`.

Group E's chain rules apply unchanged: `undeclared_steps`, sticky `poisons:`, the cross-method limit.

### 3c. `quarkus-consume-event.yml` (`annotation_driven`)

Coordinate `io.quarkus:quarkus-vertx`. `path_from: [value]`, `direction: inbound`, request shape from
the sole parameter — or the **second** where the first is a `MultiMap`, Quarkus's own headers/body
split, which its processor enforces. Two measured rules carry the file, and either one backwards
publishes something false:

- **`path_fallback: declaring_type_qualified_name`** — the default address is the declaring bean
  class's fully-qualified name (M8), not the method name and not the simple name.
- **`metadata_from: [{annotation: …ConsumeEvent, attribute: local, kind: delivery,
  absent_value: true}]`** — `local()` defaults to `true` (M8), so an undecorated `@ConsumeEvent` is a
  local-only consumer. The reverse default would publish every Quarkus consumer as cluster-reachable.

A `${…}` address is carried verbatim at `unresolved`.

### 3d. Stated boundaries

- An options object whose address is set before a later setter
  (`new MessageConsumerOptions().setAddress("a").setOrdered(true)`): `channel_via` reads the
  argument's producing call, which is then the last setter, so the address is `unresolved` (m-1).
- The SockJS/TCP **event-bus bridge** — a regex is not an address, and a permitted-address list is
  policy rather than a consumer.
- `Message.reply(...)`: a reply-to address the sender generated, on no declaration.
- A `MessageConsumer`/`MessageProducer` handed to another method before its terminal — Group E's
  cross-method limit, an open issue of the same shape as `OI-110`.
- Vert.x 3.x, whose `send` carried a reply handler at a position 4.x and 5.x do not.

---

## 4. Fixtures

**`fixtures/temporal-probe`** (Maven, offline-buildable, the `spring-integration-probe` pattern):

- `OrderWorkflow` — `@WorkflowInterface`, `@WorkflowMethod` with no name (→ `OrderWorkflow`, M1), a
  `@SignalMethod` `cancel`, a `@QueryMethod` `status`, an `@UpdateMethod` `amend`.
- `ShipmentWorkflow` — `@WorkflowMethod(name = "ShipOrder")`, proving the default *against* an
  override.
- `BillingActivities` — `@ActivityInterface(namePrefix = "billing_")` with
  `@ActivityMethod(name = "Charge") void charge(…)` (→ `Charge`, M2) and a bare `void refundCard(…)`
  (→ `billing_RefundCard`, M3, M4).
- `OrderWorkflowImpl` — `@WorkflowImpl(taskQueues = "orders")`; `BillingActivitiesImpl` —
  `@ActivityImpl(taskQueues = {"billing", "billing-retry"})` **and a public `reloadRates()` helper**,
  which must derive nothing (§2c).
- A client arm in a package that declares `PaymentsWorkflow` (a `@WorkflowInterface` this module
  does **not** implement) → outbound rows; plus one `newUntypedWorkflowStub("OrderWorkflow", …)`.
- **Variance arms deriving nothing:** `stub.signal("cancel", …)`; a
  `newWorkflowStub(OrderWorkflow.class, "wf-123")`; a helper method on a workflow interface carrying
  no member annotation.

**`fixtures/orders-eventbus`** (Maven): raw `send`/`publish`/`request`;
`consumer(addr, handler)`; `localConsumer`; a two-step `consumer(addr)` … `.handler(…)`;
`sender(addr).write(…)`; a **`consumer(addr)` never given a handler** (derives nothing, M6); and a
Quarkus arm with `@ConsumeEvent("orders.created")`, a bare `@ConsumeEvent` (→ the class FQN), a
`@ConsumeEvent(value = …, local = false)`, a `@ConsumeEvent("${orders.address}")` staying
`unresolved`, and one `(MultiMap, Order)` method.

The Kafka/JMS/Rabbit attributes of §2e need no new fixture: `fixtures/orders-receivers` already
declares the listeners whose attributes are now read.

---

## 5. Tests

- `tests/e2e/test_async_delivered.py` gains `test_temporal_shapes_rows` and
  `test_eventbus_shapes_rows` — path, kind, direction, handler/caller, and the `task_queue`/
  `delivery` metadata, asserted off a real analysis.
- A negative test per fabrication this design removes: the activity impl's helper method
  (§2c), the interface-only client module against the inbound catalog, the handler-less consumer
  (§3b), and `stub.signal(...)` (§2f).
- Unit tests beside their peers for the three `path_fallback` words, the `declared_type_methods`
  word and `metadata_from` — each including its catalog-error path, since a closed vocabulary that
  does not refuse a typo is the hole it exists to close.
- **The §2e moves:** every test that reads `endpoint_metadata` is updated in the same task as the
  catalog line that changes it — `tests/e2e/test_vertical_slice.py`,
  `tests/e2e/test_rest_inbound_delivered.py`, `tests/application/test_combinator_engine.py`,
  `test_call_engines.py`, `test_config_join.py`, `test_pipeline.py`, `test_request_requirements.py`.

---

## 6. Probes

- **`cp30_temporal_contract_naming/`** — M1–M5 by `javap` on temporal-sdk 1.27.0 and
  temporal-spring-boot-autoconfigure 1.27.0: the four naming branches, the activity qualification
  rule, the starter annotations' attributes, and `newUntypedWorkflowStub`'s argument 0 (M10).
- **`cp31_eventbus_surface/`** — M6–M9 by `javap` on vertx-core 4.5.10 **and** 5.0.0,
  smallrye-mutiny-vertx-core 3.16.0, quarkus-vertx 3.17.5 and quarkus-vertx-deployment 3.17.5.
- **`cp32_listener_attributes/`** — §2e's attributes on spring-kafka 3.1.4, spring-jms/spring-rabbit
  3.1.4 and the Micronaut equivalents: each attribute's declared type, its `AnnotationDefault`, and
  what the framework's own post-processor does with it, so that `kind` names what the framework
  means rather than what the attribute is called.

All three follow the CP-27 harness shape: the version column comes from each jar's own manifest, a
jar reporting another version aborts the run, and the last row reads the committed fixtures' own
compiled classes. Nothing is executed.

---

## 7. Files

| file | change |
|---|---|
| `domain/closed_sets.py` | `TEMPORAL`, `EVENTBUS`, one edit |
| `egress/render/document.py` | `temporal` into `_VERBED_PROTOCOLS` |
| `tests/architecture/test_source_rules.py` | both names into `PROTOCOLS` |
| `resolve/engines/annotation_driven.py` | three `_PATH_FALLBACKS` words, `declared_type_methods` in `_MEMBER_RULES`, the `metadata_from` key and its validation |
| `storage/duckdb/derive_endpoints.sql` | the three naming words' composition; the `declared_type_methods` conjunct |
| `resolve/` (metadata writer) | `metadata_from` rows into the existing `endpoint_metadata_insert` |
| catalogs, new | `temporal-workflow.yml`, `temporal-workflow-client.yml`, `temporal-activity.yml`, `temporal-activity-client.yml`, `temporal-untyped.yml`, `vertx-eventbus.yml`, `vertx-eventbus-chain.yml`, `quarkus-consume-event.yml` |
| catalogs, amended (§2e) | `spring-kafka.yml`, `micronaut-kafka.yml`, `spring-jms.yml`, `micronaut-jms.yml`, `spring-rabbit.yml` |
| fixtures | `temporal-probe`, `orders-eventbus` |
| probes | `cp30_temporal_contract_naming`, `cp31_eventbus_surface`, `cp32_listener_attributes` |
| docs | `java-kotlin-delivery-list.md`, `COVERAGE.md`, `open-issues.md` |

**Not created**, and each was in the previous draft: `resolve/contracts.py`,
`catalogs/contract-models/`, `resolve/engines/annotated_contract.py`, and the `fluent` words
`contract`, `all_args` and `argument_chain` (§0a).

---

## 8. The register afterwards

```delivery``` loses `temporal-cadence` and `vertx-eventbus`; the **Async** column empties and the
row closes. Category C loses its last two items, leaving `apache-camel` and
`smallrye-reactive-messaging` as the only unsequenced work. `scripts/coverage_matrix.py`'s
`ITEM_FRAMEWORKS` entries for the two ids go with them. COVERAGE §5.12 gains two shipped framework
lines with their boundaries; §§5.8–5.9 record the attributes §2e now reads.

New open issues: the linking-tier refinement rule (§1f); a Cadence re-measurement trigger (§1b);
the programmatic worker's unread task queue, with the mechanism it would need (§2g); a
`MessageConsumer` handed across methods (§3d); `registerWorkflowImplementationFactory` (§2g).

---

## 9. Self-review

**Placeholders:** none. **Internal consistency:** §1c's verbed/verbless split matches §1d's kinds
and §1e's silence; §2's four catalogs each name the word §7 adds; §3's per-version rows match M7 and
the fixture arms in §4; §1f's rule is what §1d, §2d, §2e and §3c all cite.

**No false positives, form by form:** the activity/workflow asymmetry (M4, §2c); the helper-method
fence (§2c); the prefix-skipping branch (M2, §2b); `local()`'s true default (M8); the handler-less
consumer (M6); `stub.signal` deriving nothing rather than a colliding identity (§2f); the
running-execution stubs (§2g).

**Existing functionality:** the only shipped output that moves is §2e's, which is the user's own
ruling; its tests move in the same task. Every other change is additive — two enum members, three
words and one key in closed vocabularies that refuse the unknown, and eight new catalogs.

**Reuse:** the adversarial pass deleted one engine, one model-file kind, one shared fold and three
engine words by finding the shipped mechanism that already did each job (§0a). What remains new is
genuinely new: a word for a naming rule no framework here had, a word for a member rule no framework
here had, and one key for a table no annotation-driven catalog could write to.
