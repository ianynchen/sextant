# Akka and Pekko actors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Named cluster keys become `actor` endpoint rows, and every actor message send becomes a trace hop to the handler its message class reaches.

**Architecture:** Catalogs declare the Akka and Pekko API (endpoint rows through the existing `single_call`/`fluent` engines; two new catalog words, `message_handlers` and `message_sends`). One new pass reads handler registrations into a new graph table `message_handlers`; a second writes hops into the existing `rpc_hops` table, which `trace.py` already reads. No Python names a framework.

**Tech Stack:** Python 3 resolver (DuckDB, YAML catalogs), ASM extractor facts (fact schema 6, unchanged), Maven fixtures built with JDK 21.

**Spec:** `docs/superpowers/specs/2026-11-04-akka-pekko-actors-design.md` (approved 2026-11-04). §3d's seven calls are binding.

## Global Constraints

- Read `GUIDELINES.md` and `CLAUDE.md` first. Match existing patterns; do not refactor adjacent code.
- No `.py` or `.sql` file names a framework, protocol or product (`tests/architecture/test_source_rules.py`); `actor` appears only as the `Protocol` member and in catalogs/docs.
- Graph schema 14 → 15 (`src/sextant/domain/version.py` `GRAPH_SCHEMA_VERSION`), for the `message_handlers` table only. Fact schema stays 6. Boundary vocabulary stays 4.
- Fixtures build with JDK 21: `JAVA_HOME=/opt/homebrew/opt/openjdk@21`.
- Versions: Akka **2.6.21** (`com.typesafe.akka`, `_2.13`, Maven Central, Apache-2.0); Pekko **1.1.3** (`org.apache.pekko`, `_2.13`). If either version is not resolvable, use the newest resolvable 2.6.x / 1.1.x and say so.
- Every descriptor and every "returns this" claim in a catalog is measured with `javap -c -p` and recorded in probe CP-57 (`scripts/probes/cp57_actors.md`).
- Grading (user ruling 2026-11-03): a finding is Critical/Major only for shapes real code produces — check `examples/pekko-samples` and `examples/akka-samples`.
- A hop is never guessed: unknown message class → a stop that says so. Never a fan-out.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Gate: `scripts/check.sh` green; `scripts/guard_check.py` kills guards for new code; `scripts/field_check.py` all ok.

## Review Focus

1. A behavior built with the immutable `Behaviors.receive(C.class).onMessage(…)` chain — every case one behavior, first match wins (Task 4 test `test_an_immutable_builder_chain_is_one_behavior`).
2. A predicated case before an unpredicated one for the same class — both are hop targets (Task 4 `test_a_predicated_case_never_shadows`).
3. `replyTo.tell(new Reply(...))` where no behavior handles `Reply` — a stop with `via actor <class>`, no handler, no crash (Task 5 `test_a_reply_nobody_handles_is_a_stop`).
4. A send whose message comes from a parameter — a stop naming the unread class, no hop (Task 5 `test_an_unread_message_class_is_a_stop`).
5. A module that inits an entity key and calls `entityRefFor` on it — no outbound row; the sends are hops (Task 3 `test_a_key_the_module_serves_is_no_outbound_row`).

---

### Task 1: Probe CP-57 and the two fixtures

**Files:**
- Create: `scripts/probes/cp57_actors.md`
- Create: `fixtures/orders-actors-pekko/` (Maven module: `pom.xml`, `src/main/java/com/acme/actors/...`)
- Create: `fixtures/orders-actors-akka/` (the same sources, `akka.*` imports)
- Modify: `fixtures/pom.xml` (add both modules), `tests/fixture_build.py` if fixtures are registered there (follow `orders-pekko`)

**Interfaces:**
- Produces: the probe's measured descriptors (Tasks 2-5 copy them verbatim), and the fixture class names below, which Tasks 3-6 assert on.

- [ ] **Step 1:** Resolve the jars (`actor-typed`, `cluster-typed`, `cluster-sharding-typed`, `cluster-tools`, `persistence-typed`, and classic `actor`) for both families; `javap -c -p` every class the spec §3a-§3d names. Record per method: owner, name, descriptor, and whether the bytecode returns `this` (`aload_0; areturn`) or a new object. Mandatory rows: `BehaviorBuilder.onMessage` (2 and 3 args), `onMessageEquals`, `ReceiveBuilder.onMessage`, `CommandHandlerBuilderByState.onCommand` (2 and 3 args), classic `ReceiveBuilder.match`/`matchEquals`, `ActorRef.tell` (typed, classic), `EntityRef.tell/ask`, `RecipientRef.ask`, `ActorContext.ask/messageAdapter/pipeToSelf`, `TimerScheduler.startTimerWithFixedDelay/startTimerAtFixedRate/startSingleTimer`, `Scheduler.scheduleOnce`, `ServiceKey.create`, `EntityTypeKey.create`, `Entity.of`, `ClusterSharding.init/entityRefFor`, `Receptionist.register/subscribe/find`, `DistributedPubSubMediator.Publish/Subscribe/Send/Put` constructors, `Patterns.ask`. Also record how javac compiles `replyTo -> new Query(…, replyTo)` passed to `ask`, and a two-`return` mapper lambda.
- [ ] **Step 2:** Write `fixtures/orders-actors-pekko`, package `com.acme.actors`, with these classes, each one shape:
  - `Stock` — typed actor: `Behaviors.receive(Stock.Command.class).onMessage(Reserve.class, …).onMessage(Release.class, p -> p.urgent, …).onMessage(Release.class, …).onMessageEquals(Stock.Tick.INSTANCE, …).build()`; registers `ServiceKey.create(Stock.Command.class, "stock")` with the Receptionist; a timer `startTimerWithFixedDelay(Tick.INSTANCE, …)`.
  - `Orders` — persistence `EventSourcedBehavior` with `forAnyState().onCommand(Place.class, …)` and two `forState(...)` chains on one local builder.
  - `OrderEntity` + `OrderRoutes` — `EntityTypeKey.create(OrderEntity.Command.class, "order")`, `ClusterSharding.init(Entity.of(KEY, ctx -> OrderEntity.create(...)))`, `entityRefFor(KEY, id).ask(replyTo -> new OrderEntity.Get(id, replyTo), timeout)` (reply class handled by nobody).
  - `Frontend` — `Receptionist.subscribe(Stock.KEY, adapter)`, `messageAdapter(Receptionist.Listing.class, l -> new Workers(l))`, `context.ask(Stock.Reply.class, stock, timeout, r -> new Stock.Reserve(…, r), (res, ex) -> res != null ? new Reserved(res) : new Failed(ex))`, `pipeToSelf`.
  - `Relay` — `forward(Object msg, ActorRef<Object> to) { to.tell(msg); }` (unknown class).
  - `ClassicBroker` — classic `AbstractActor` with `receiveBuilder().match(Price.class, …).build()`, `getSender().tell(new Ack(), getSelf())`, pub-sub `new DistributedPubSubMediator.Subscribe("prices", getSelf())`, `Publish("prices", new Price(…))`, `Put(getSelf())`, `Send("/user/broker", new Price(…), false)`.
- [ ] **Step 3:** Copy it to `fixtures/orders-actors-akka` with `akka.*` imports; build both with `JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q -o package` (online once if missing). Expected: BUILD SUCCESS, `target/classes` populated.
- [ ] **Step 4:** Commit: `test(fixtures): Akka and Pekko actor fixtures; probe CP-57`.

### Task 2: The `actor` protocol

**Files:**
- Modify: `src/sextant/domain/closed_sets.py` (`Protocol.ACTOR = "actor"` with a comment in the style of `EVENTBUS`)
- Modify: `src/sextant/egress/render/document.py`, `tests/architecture/test_source_rules.py` (`PROTOCOLS`), `tests/domain/test_closed_sets.py`, `tests/egress/test_render.py` — the five files commit `12d72679` touched
- Modify: `docs/components/D00-fact-schema.md` protocol list (add `temporal`, `eventbus`, `actor`), `docs/components/D01-*.md` wire-identity table (`actor`: identity = key name or topic)

**Interfaces:**
- Produces: `Protocol.ACTOR` (`"actor"`), loadable as `protocol: actor` in a catalog.

- [ ] **Step 1:** Write `test_actor_is_a_protocol` in `tests/domain/test_closed_sets.py`: `assert Protocol.ACTOR.value == "actor"`; add `"actor"` to `PROTOCOLS`. Run them; expected FAIL (no member).
- [ ] **Step 2:** Add the member and the render case following `12d72679`. Run `uv run pytest tests/domain tests/architecture tests/egress -q`: PASS.
- [ ] **Step 3:** Update D00/D01. Commit `feat(domain): actor joins the closed Protocol set`.

### Task 3: Endpoint rows for named keys and topics

**Files:**
- Create: `src/sextant/catalogs/akka-actors.yml`, `src/sextant/catalogs/pekko-actors.yml` (more than one file per family if the engines need one style per catalog: e.g. `pekko-actors-pubsub.yml` for the classic constructor rows)
- Modify: `src/sextant/application/resolve/self_calls.py` (`_PROTOCOLS = ("grpc", "actor")`) and its test
- Test: `tests/e2e/test_actors_delivered.py`

**Interfaces:**
- Consumes: `Protocol.ACTOR`; probe CP-57 descriptors; `channel_via` (`single_call.py` ~:566-612) for `ServiceKey.create` arg 1, `EntityTypeKey.create` arg 1, and `Entity.of` arg 0 → `EntityTypeKey.create` arg 1.
- Produces: inbound rows `protocol='actor'`, `path` = key name or topic, `handler` NULL (Task 6 fills it); outbound rows for keys the module does not serve.

- [ ] **Step 1:** Write, for both fixtures (parametrize on the fixture name), in `tests/e2e/test_actors_delivered.py`:
  - `test_a_registered_service_key_is_an_inbound_row`: inbound `actor` row with path `stock`, resolution `resolved`.
  - `test_an_initialised_entity_type_is_an_inbound_row`: inbound `order`.
  - `test_a_pubsub_subscription_is_an_inbound_row`: inbound `prices`, `resolved`. `Put(getSelf())` names no path in its arguments (the actor's path is set where it was started): its row is inbound, path NULL, `unresolved` — kept, never dropped.
  - `test_a_key_the_module_serves_is_no_outbound_row`: no outbound `actor` row for `order` or `stock` (the module serves both); outbound `prices` from `Publish` is also served (subscribed) here, so none either.
  - `test_a_key_the_module_does_not_serve_is_an_outbound_row`: a unit test on a stub workspace (follow `tests/application/test_self_calls*.py`), outbound `actor` row `inventory` kept when nothing inbound serves it.
  Run: FAIL.
- [ ] **Step 2:** Write the catalogs from CP-57 (one per family; `detect.coordinates` per artifact); add `actor` to `self_calls._PROTOCOLS`. Run the tests: PASS.
- [ ] **Step 3:** Commit `feat(catalogs): Akka and Pekko named cluster keys are actor endpoint rows`.

### Task 4: `message_handlers` — the catalog word, the table, the reader

**Files:**
- Modify: `src/sextant/ingress/catalogs/yaml_source.py` (load and validate `matches.message_handlers`, the `not_hand_offs` style: owner, method, descriptor, `class_arg` | `value_arg`, `handler_arg`, optional `predicate_arg`, optional `returns_message`), `src/sextant/application/ports/catalogs.py`
- Modify: catalogs from Task 3 (or a new `*-actor-handlers.yml` each): roots `Behaviors.receive`, `newReceiveBuilder`, `forAnyState`, `forState`, classic `receiveBuilder`; steps = the registrations; terminal `build`; `returns_receiver` only where CP-57 shows `this`
- Create: `src/sextant/application/resolve/message_handlers.py` — `record_message_handlers(workspace: Workspace, catalogs: list[Catalog]) -> None`
- Create: `src/sextant/storage/duckdb/reset_message_handlers.sql`, `insert_message_handlers.sql`; modify `schema.sql` (table below), `workspace.py` (export query, follow `rpc_hops`), `src/sextant/domain/version.py` (`GRAPH_SCHEMA_VERSION = 15`)
- Modify: `src/sextant/application/resolve/pipeline.py` — call it after `record_rpc_hops`' position, before `apply_path_prefixes`
- Test: `tests/application/test_message_handlers.py`, e2e cases in `tests/e2e/test_actors_delivered.py`

**Table:**
```sql
CREATE TABLE IF NOT EXISTS message_handlers (
    behavior      TEXT,     -- the chain: `<caller>#<root ordinal>`, module-prefixed caller
    position      INTEGER,  -- 0-based place of the case in the chain
    message_type  TEXT,     -- the class literal's symbol; NULL for a value case
    message_value TEXT,     -- the constant's identity (`<owner>#<field>`); NULL for a class case
    predicated    BOOLEAN,  -- a predicate argument is present: never shadows
    handler       TEXT,     -- module-prefixed handler method; NULL if not read
    delivers      BOOLEAN,  -- `returns_message`: the handler's return is delivered to its own actor
    evidence      TEXT
);
```

**Interfaces:**
- Consumes: `shapes.chains.chain_ends` (walks receiver → result; captures with `repeats` keep order), `combinator._handler_of` / `method_symbols` for the handler, `shapes.arguments._reference_of` for a class literal.
- Produces: `record_message_handlers`; `message_handlers` rows; `reachable_handlers(rows, message_type: str | None, message_value: str | None, supertypes: Mapping[str, set[str]]) -> list[dict]` in `message_handlers.py` — per behavior, the first unpredicated case the message matches plus every predicated case before it that matches. Task 5 and Task 6 call it.

- [ ] **Step 1:** Write unit tests (stub facts, follow `tests/application` stubs):
  - `test_an_immutable_builder_chain_is_one_behavior`: three `onMessage` steps on new-object results → three rows, one `behavior`, positions 0-2.
  - `test_first_match_wins_within_a_behavior`: `onMessage(Command)` at 0 then `onMessage(Reserve)` at 1; `reachable_handlers(type=Reserve)` → only position 0.
  - `test_a_predicated_case_never_shadows`: `onMessage(Release, pred)` at 1, `onMessage(Release)` at 2 → both reachable.
  - `test_a_value_case_matches_its_constant_only`: `onMessageEquals(Tick.INSTANCE)` reachable for value `Tick#INSTANCE`, not for type `Tick` from `new Tick()`.
  - `test_each_for_state_chain_is_its_own_behavior`.
  - `test_a_statement_builder_is_one_behavior_only_where_it_returns_this`.
  Run: FAIL.
- [ ] **Step 2:** Implement the loader, table, version bump, reader and `reachable_handlers`. Run unit tests: PASS. Run `uv run pytest tests/e2e/test_actors_delivered.py -q` with new e2e `test_stock_handlers_are_read_in_order` (Stock: 4 rows, positions 0-3, position 1 `predicated`): PASS.
- [ ] **Step 3:** Commit `feat(resolve): message handler registrations are read per behavior (graph schema 15)`.

### Task 5: Hops — a send reaches its handlers

**Files:**
- Modify: `yaml_source.py`/`catalogs.py` — `matches.message_sends`: owner, method, descriptor, `message_arg` (index), optional `to_self: true` (timers, `pipeToSelf`)
- Modify: the actor catalogs — sends: typed `tell`, `EntityRef.tell/ask`, `RecipientRef.ask`, `ActorContext.ask` (arg 3 the request lambda; arg 4 declared under `message_handlers` with `returns_message`), `pipeToSelf` (mapper `returns_message`), timers (`to_self`), classic `tell(msg, sender)`, `Patterns.ask`, pub-sub `Publish`/`Send` message arg
- Create: `src/sextant/application/resolve/message_hops.py` — `record_message_hops(workspace: Workspace, catalogs: list[Catalog]) -> None`
- Modify: `rpc_hops.py` (remove its own `workspace.derive("rpc_hops_reset")`), `pipeline.py` (one `rpc_hops_reset` before both; `record_message_hops` after `record_message_handlers`), the `schema.sql` comment on `rpc_hops` (two writers)
- Test: `tests/application/test_message_hops.py`, `tests/e2e/test_actors_delivered.py`, a trace test (follow `tests/application/query` trace tests for gRPC hops)

**Interfaces:**
- Consumes: `reachable_handlers` (Task 4); `supertypes_of` (`workspace.once`); call-site `arguments[]` kinds (D00 §5): `instance` → its symbol's class; `lambda` → each `method_return` of the body that is an `instance` (one hop per returned class); `field`/enum constant → identity `<owner>#<field>` and the field's type.
- Produces: `rpc_hops` rows `protocol='actor'`, `path` = the message class symbol (or value identity), `handler` = the reachable handler; a send with no reachable handler → one row with `handler` NULL; unread class → one row, `handler` NULL, `path` NULL, `evidence` saying the message class was not read. A `delivers` handler continues: its own returned classes are hops from that handler's return sites.

- [ ] **Step 1:** Write tests:
  - `test_a_tell_reaches_the_first_matching_handler` (Stock `Reserve`).
  - `test_an_ask_lambda_is_read_through_its_return` (OrderRoutes → OrderEntity's `Get` handler).
  - `test_a_two_return_mapper_gives_a_hop_per_class` (Frontend's `context.ask` mapper → `Reserved` and `Failed` handlers).
  - `test_a_timer_is_a_send_to_the_actor_itself` (`Tick.INSTANCE` → the `onMessageEquals` handler).
  - `test_a_reply_nobody_handles_is_a_stop`.
  - `test_an_unread_message_class_is_a_stop` (Relay).
  - `test_a_trace_crosses_the_ask` — `trace` from `OrderRoutes#get…` reaches `OrderEntity`'s handler with `via actor …`.
  - `test_grpc_hops_are_unchanged` — the existing gRPC hop tests still pass with the shared reset.
  Run: FAIL.
- [ ] **Step 2:** Implement. Run the new tests and `uv run pytest tests -q -k "hop or trace"`: PASS.
- [ ] **Step 3:** Commit `feat(resolve): an actor message send is a trace hop to the handler its class reaches`.

### Task 6: An inbound key row names its handlers

**Files:**
- Modify: `src/sextant/application/resolve/message_hops.py` (or a sibling function in it), `pipeline.py`, `storage/duckdb/*.sql` as needed
- Test: `tests/e2e/test_actors_delivered.py`

**Interfaces:**
- Consumes: the inbound `actor` rows (Task 3); the key's message class (`ServiceKey.create`/`EntityTypeKey.create` arg 0, a class literal); `message_handlers` rows.
- Produces: per inbound key row, one row per handler whose registered class is the key's class or a subtype (unshadowed, predicated included), as a route with two handlers is two rows; a key no handler serves keeps its one row, `handler` NULL.

- [ ] **Step 1:** Write `test_a_service_key_row_names_each_handler_of_its_class` (stock: the Reserve, both Release, and Tick handlers → 4 rows) and `test_an_entity_key_row_names_its_handlers`. Run: FAIL.
- [ ] **Step 2:** Implement; follow how a route with several handlers is written (`call_endpoints` insert, D02 §5). Run: PASS.
- [ ] **Step 3:** Commit `feat(resolve): an actor key row names every handler its message class reaches`.

### Task 7: The corpus, the docs, the gate

**Files:**
- Modify: `docs/components/D02-*.md` (`message_handlers`, `message_sends` words), `docs/components/D01-*.md` (`message_handlers` table, `rpc_hops` second writer), `docs/COVERAGE.md` (§5 actors row, §2c family row), `CHANGELOG.md`, the spec's "As built" section
- Create: `.superpowers/sdd/<workspace>/corpus.md` (the hand check)

- [ ] **Step 1:** `uv run sextant module analyze examples/pekko-samples/pekko-sample-sharding-java/killrweather` and `…/pekko-sample-cluster-java` (and the two `akka-samples` twins). List every `actor` row and every hop; check each against the source by hand; the trace from `WeatherRoutes.query` reaches `WeatherStation`'s query handler. Record counts and any wrong row. Any wrong row is fixed before Step 2.
- [ ] **Step 2:** Docs. Gate: `scripts/check.sh`, `scripts/guard_check.py` (new modules), `scripts/field_check.py`. Expected: all green, six pins ok.
- [ ] **Step 3:** Commit `docs: Akka and Pekko actors as built`.
