# In-process dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the actor-only catalog words with one general in-process dispatch mechanism (key by type or by object; match first/all/one), keep Akka/Pekko's results identical, and add Spring events, CDI events, Kotlin channels/flows and Java blocking queues.

**Architecture:** Neutral catalog blocks (`dispatch_sends`, `dispatch_registrations`, `dispatch_receives`) and one catalog setting `dispatch: {key, match}`, read by the existing chain walk, annotation engine and value walk; one graph table `dispatch_registrations`; hops in `hops` (renamed `rpc_hops`). No Python names a framework.

**Tech Stack:** Python resolver (DuckDB, YAML catalogs), ASM facts (fact schema 6, unchanged), Maven/Gradle fixtures (JDK 21).

**Spec:** `docs/superpowers/specs/2026-11-05-in-process-dispatch-design.md` (approved 2026-11-05), amending `docs/superpowers/specs/2026-11-04-akka-pekko-actors-design.md` (its As-built section records what exists).

## Global Constraints

- Read `GUIDELINES.md` and `CLAUDE.md` first. Match existing patterns; do not refactor adjacent code.
- No `.py`/`.sql` names a framework, protocol or product (`tests/architecture/test_source_rules.py`). No catalog word or table starts with `message_`.
- Graph schema stays **15** (unreleased): the table is `dispatch_registrations(group, position, key_type, key_value, key_object, predicated, handler, delivers, match)`. Fact schema stays 6.
- `rpc_hops` is renamed `hops`; columns unchanged; `evidence` stays in the closed `Evidence` set (`compiler`).
- A dispatch is a hop, never an endpoint row. An unread key is a stop that says so (path NULL, handler NULL); never a fan-out.
- Akka/Pekko results must stay identical: the fixture pins in `tests/e2e/test_actors_delivered.py` and the 33 rows/hops checked on `examples/pekko-samples` (see `.superpowers/sdd/2026-11-04-akka-pekko-actors/corpus.md`).
- Every descriptor in a catalog is measured with `javap -c -p` and recorded in a probe (`scripts/probes/`, provenance per GUIDELINES §5.4; the harness prints versions from MANIFEST.MF).
- Fixtures build with JDK 21: `JAVA_HOME=/opt/homebrew/opt/openjdk@21`.
- Grading: Critical/Major only for shapes real code produces (`examples/`).
- Gate per task: `scripts/check.sh` green, `scripts/guard_check.py` kills guards for new code, `scripts/field_check.py` all ok (apollo-portal is a pin: any moved row checked true or false by hand).
- Docs with the change (GUIDELINES §5.1): D01, D02, CHANGELOG in the task that changes them.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Stage files by name.

## Review Focus

1. A Spring listener whose parameter is a supertype of the published class — reached (`match: all` uses assignability) (Task 2 `test_a_listener_of_a_supertype_receives`).
2. `publishEvent` with a value from a parameter — a stop "key not read", no fan-out to every listener (Task 2 `test_an_unread_event_class_is_a_stop`).
3. A blocking queue held in a field, put in one class's method and taken in another's — one hop across classes (Task 4 `test_a_field_held_queue_links_across_methods`).
4. Two queues of the same type in one module — sends on one never hop to takes on the other (Task 4 `test_two_queues_of_one_type_stay_apart`).
5. A Kotlin `for (x in channel)` loop — read as a receive (Task 5 `test_a_for_loop_over_a_channel_receives`).

---

### Task 1: The general words; Akka on them

**Files:** rename `src/sextant/application/resolve/message_handlers.py` → `dispatch_registrations.py`, `message_hops.py` → `dispatch_hops.py`; `ingress/catalogs/yaml_source.py`, `application/ports/catalogs.py`; `engines/single_call.py` (`channel_via` entries gain `class_arg`); `storage/duckdb/schema.sql`, its `*.sql`, `workspace.py`; `pipeline.py`; the actor catalogs; tests; D01, D02, CHANGELOG, `version.py` comment.

**Interfaces — Produces:**
- Catalog blocks: `dispatch_sends: [{owner, method, descriptor, value_arg}]`; `dispatch_registrations: [{owner, method, descriptor, class_arg | value_arg, handler_arg, predicate_arg?, returns_value?}]` carried by an ordinary `style: fluent` chain catalog (the chain walk gives group + position) or standalone (each call its own group); `dispatch_receives: [{owner, method, descriptor, object: receiver, handler: enclosing | lambda_arg}]` (loaded and validated here, read in Task 4); setting `dispatch: {key: type | object, match: first | all | one}`.
- A fluent catalog that declares `dispatch_registrations` produces registrations, not endpoint rows (one branch where the engine decides what a chain end becomes; no endpoint validation runs for it).
- `channel_via: [{owner, method, arg, class_arg?}]` reads the class from the same producing call in the same walk; `message_class_via` and its second walk and `_paired` are removed.
- `reachable_handlers(rows, key_type, key_value, supertypes, match)`: `first` = as now; `all` and `one` = every matching registration.
- Table `dispatch_registrations` (Global Constraints); `hops` (renamed).

- [ ] **Step 1:** Change the tests first: the existing actor tests renamed to the new words/tables, plus `test_no_catalog_word_or_table_starts_with_message` (architecture), `test_match_all_reaches_every_matching_registration`, `test_channel_via_reads_the_class_in_the_same_walk`. Run: FAIL.
- [ ] **Step 2:** Implement; re-express the 12 key catalogs and 2 handler catalogs. Run the actor suites: every Akka/Pekko fixture pin identical. Re-analyse `examples/pekko-samples` killrweather and cluster-java: the 5 rows and 28 hops identical to `corpus.md`.
- [ ] **Step 3:** Gate; commit `refactor(resolve): in-process dispatch — one mechanism, neutral words; actors on it`.

### Task 2: Spring application events

**Files:** `engines/annotation_driven.py` (registration output; `path_fallback: payload_type`); new `src/sextant/catalogs/spring-events.yml` (and a sends catalog if one style per file requires it); probe `scripts/probes/cp58_dispatch.md` (+ harness); fixture `fixtures/orders-events/` (Spring Boot, JDK 21); tests `tests/e2e/test_spring_events_delivered.py`, unit tests beside the engine.

**Interfaces — Consumes:** Task 1's blocks and table. **Produces:** registrations from annotation catalogs: key = the payload parameter's type (`request_body` picks it) or `@EventListener(classes=…)` via `path_from`; `ApplicationListener` implementations keyed by the parameter type of their own non-bridge `onApplicationEvent` (skip `bridge_of`); `match: all`.

- [ ] **Step 1:** Fixture classes: `OrderPlaced` (event), `OrderService` (`publisher.publishEvent(new OrderPlaced(id))`, `publishEvent(param)`), `AuditListener` (`@EventListener void on(OrderPlaced e)`), `AnyListener` (`@EventListener void on(Object e)` — supertype), `ClassesListener` (`@EventListener(classes = OrderPlaced.class) void on()`), `TxListener` (`@TransactionalEventListener`), `MailListener implements ApplicationListener<OrderPlaced>`. Tests: `test_a_published_event_hops_to_every_listener_of_its_class` (Audit, Any, Classes, Tx, Mail), `test_a_listener_of_a_supertype_receives`, `test_an_unread_event_class_is_a_stop`, `test_an_application_listener_is_keyed_by_its_own_method`. Run: FAIL.
- [ ] **Step 2:** Measure `ApplicationEventPublisher.publishEvent` (both), `ApplicationContext` inheritance, the annotations, in CP-58. Implement. Run: PASS.
- [ ] **Step 3:** Analyse `examples/apollo` (apollo-portal, apollo-biz) and `examples/dolphinscheduler` (dolphinscheduler-api) — check every new hop by hand against the source; record in the workspace `corpus.md`. `scripts/field_check.py`: any moved pin row checked. Gate; commit `feat(catalogs): Spring application events are in-process dispatch`.

### Task 3: CDI events

**Files:** `engines/annotation_driven.py` (`selected_by_parameter: <annotation fqn>` mapping word); new `src/sextant/catalogs/cdi-events.yml` (jakarta + javax if both measured); probe rows in CP-58; fixture `fixtures/orders-cdi-events/` (Quarkus, Maven, JDK 21); tests `tests/e2e/test_cdi_events_delivered.py`.

**Produces:** sends `Event.fire`/`fireAsync` (key = value's class); registrations = methods with an `@Observes`/`@ObservesAsync` parameter, key = that parameter's type, `match: all`.

- [ ] **Step 1:** Fixture: `event.fire(new Shipped(id))`, observers of `Shipped` and of `Object`, one `@ObservesAsync`, one `@Observes StartupEvent` (a framework event nobody in the module fires — a registration with no hop, no row). Tests: `test_a_fired_event_hops_to_every_observer`, `test_a_framework_event_observer_gets_no_hop`. Run: FAIL.
- [ ] **Step 2:** Measure; implement. PASS. Check on two Quarkus examples under `examples/` that fire events; record. Gate; commit `feat(catalogs): CDI events are in-process dispatch`.

### Task 4: Object keys; Java blocking queues

**Files:** `dispatch_registrations.py`/`dispatch_hops.py` (read `dispatch_receives`; `key_object` from `values.producer_paths(index, site, RECEIVER, declared, which_object=True)`); new `src/sextant/catalogs/jdk-blocking-queue.yml`; fixture classes in an existing Java fixture or `fixtures/orders-queues/`; tests `tests/application/test_dispatch_objects.py`, e2e.

**Produces:** a send whose catalog says `key: object` hops to every receive site whose receiver reaches the same producer (`caller#ordinal`); `match: one` (each value to one consumer, so a hop to each); an `external` receiver (DI, outside the module) → a stop "object not read".

- [ ] **Step 1:** Fixture: `Pipeline` holds `BlockingQueue<Job> jobs = new LinkedBlockingQueue<>()` (field), `submit()` puts, `Worker.run()` (another class, given the same queue by constructor) takes; a second queue of the same type, `audit`, with its own put/take. Tests: `test_a_field_held_queue_links_across_methods`, `test_two_queues_of_one_type_stay_apart`, `test_a_queue_from_outside_the_module_is_a_stop`. Run: FAIL.
- [ ] **Step 2:** Measure `BlockingQueue` put/offer/add/take/poll (interface owner; heirs cover implementations). Implement. PASS. Check apollo (apollo-biz/configservice) and dolphinscheduler queue sites by hand; record. Gate; commit `feat(resolve): object-keyed dispatch; Java blocking queues`.

### Task 5: Kotlin channels and flows

**Files:** new `src/sextant/catalogs/kotlinx-channels.yml`, `kotlinx-flows.yml`; probe rows (kotlinx-coroutines-core jar); fixture `fixtures/orders-kotlin-channels/` (Gradle or Maven, Kotlin, JDK 21); tests e2e.

**Produces:** sends `SendChannel.send`/`trySend`, `MutableSharedFlow.emit`/`tryEmit`, `MutableStateFlow.setValue`/`emit`; receives `ReceiveChannel.receive`/`tryReceive`/`iterator` (a `for` loop), `Flow.collect` (handler = the collector lambda); `match: one` for channels, `all` for flows.

- [ ] **Step 1:** Fixture: a `Channel<Order>` in a class field, a producer coroutine `send`s, a consumer `for (o in ch)`; a `MutableSharedFlow<Event>` with two `collect` sites; a `MutableStateFlow` set via `.value =`. Tests: `test_a_for_loop_over_a_channel_receives`, `test_a_shared_flow_reaches_every_collector`, `test_a_state_flow_value_set_is_a_send`. Run: FAIL.
- [ ] **Step 2:** Measure how kotlinc compiles each (suspend `send` with a continuation parameter; `for` → `iterator()`/`hasNext`; `value =` → `setValue`). Implement. PASS. Check koog and kotlinconf channel/flow sites by hand; record. Gate; commit `feat(catalogs): Kotlin channels and flows are object-keyed dispatch`.

### Task 6: Docs and corpus

**Files:** spec As-built (both specs), COVERAGE (Spring events, CDI events, queues, Kotlin channels rows; §7), CHANGELOG, D00 if needed.

- [ ] **Step 1:** Collect the corpus checks from Tasks 1-5 into the spec's As-built; COVERAGE rows for each new kind with counts. Gate; commit `docs: in-process dispatch as built`.
