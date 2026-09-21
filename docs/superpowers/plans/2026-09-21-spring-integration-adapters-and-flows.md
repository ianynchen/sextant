# Spring Integration adapters and flows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `pubsub-channel-adapter`, the §5.12 "destination behind a channel" boundary for the AMQP/Kafka Spring Integration adapters (bean-wired and DSL flows), `dsl-media-route` and `gateway-properties-routes`.

**Architecture:** The `fluent` engine gains general words — constructor roots (already `{owner, method: <init>}`), `continue_via_argument`, capture kinds `handler`/`channel_link`, `bean_via`, `poisons:`, `compose:`, `method_annotation`, `direction:` per root, inbound rows carrying `handler` — and three `style: fluent` broker catalogs use them. Bean identity is a shared fold (`resolve/beans.py`, driven by a `bean-models/spring.yml`). The channel edge is data (`channel_bindings`: `fed_by` from fluent, `read_by` from `config_join`); a join pass mints the rows and `gaps` asks only about unfed channels. `config_join` gains the general `indexed:` address form for Gateway's property routes.

**Tech Stack:** Python 3.14, DuckDB, pydantic; YAML catalogs; Maven fixtures (Spring Boot 3.2.5 BOM: spring-integration 6.2.4, spring-cloud-gcp-pubsub 5.1.2; spring-cloud-gateway-server-webflux 5.0.0).

**Spec:** `docs/superpowers/specs/2026-09-21-spring-integration-adapters-and-flows-design.md` — the authority; §0/§0b/§0c carry the rulings (F1–F12, A1–A8, B1–B5).

## Global Constraints

- **Full gate at every commit, exit code read:** `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh` (never `| tail`); `bash scripts/check.sh --guards` when a guard-covered file changes. No worktrees (GUIDELINES §13.9); branch `feat/group-e-spring-integration-adapters`, already created off `main`.
- **No false positives.** A destination, handler or link is written only where the code states it and the framework honours it; ambiguity → unresolved column, never a guess (spec §0b A1–A4, §0c B5).
- **Byte-identical goldens for the thirteen shipped fluent catalogs** at every fluent commit: every new key is optional and no shipped catalog declares one until Task 6.
- **The resolve layer names no language** (`tests/architecture/test_language_confinement.py`) **and no framework**: `@Bean`/`@Qualifier` spellings live in `catalogs/bean-models/spring.yml`; flow step names in `catalogs/step-models/spring-integration.yml`; the engines read them as data.
- **DR-6:** every rule mirrors the framework's own behaviour, cited to a CP-27/28/29 row.
- GUIDELINES §3 / §13.5: match the surrounding file's voice; do not refactor adjacent code. §8.7: count reads per resolve — every new fold is a `workspace.once`.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## File map

| Path | Responsibility |
|---|---|
| `src/sextant/catalogs/bean-models/spring.yml` | **new** — the DI model: bean-declaring annotation and its name attributes, the qualifier annotation (T1) |
| `src/sextant/ingress/catalogs/yaml_source.py`, `application/ports/catalogs.py` (Catalog) | load `bean_model` and `step_model` the way `shape_model` is loaded (T1, T6) |
| `src/sextant/application/resolve/beans.py` | **new** — the bean table and `bean_of` (T1) |
| `src/sextant/storage/duckdb/schema.sql`, `reset_channel_bindings.sql`, `insert_channel_bindings.sql`, `workspace.py` | the `channel_bindings` temp table, its reset/insert/named query (T2) |
| `src/sextant/application/resolve/engines/config_join.py` | write `read_by`; `gaps` asks only unfed; `indexed:` address form (T2, T8) |
| `src/sextant/application/resolve/channel_bindings.py` | **new** — the `fed_by ⋈ read_by` join pass (T2) |
| `src/sextant/application/resolve/endpoints.py` | call the join pass after the engine loop; reset the table (T2) |
| `src/sextant/application/resolve/engines/fluent.py` | the new words (T3, T4, T5) |
| `src/sextant/catalogs/step-models/spring-integration.yml` | **new** — the 35 flow steps classified (T6) |
| `src/sextant/catalogs/spring-integration-{pubsub,amqp,kafka}.yml` | **new** (T6) |
| `src/sextant/catalogs/spring-{webflux,mvc}-router.yml` | `dsl-media-route` verb rules (T7) |
| `src/sextant/catalogs/spring-cloud-gateway-properties.yml` | **new** (T8) |
| `fixtures/spring-integration-probe/…` | Pub/Sub shapes, AMQP DSL + outbound, Kafka pass-through/divert/channel flows, near-misses (T6) |
| `fixtures/orders-service/…`, `fixtures/orders-gateway/src/main/resources/application.yml` | ride-along fixtures (T7, T8) |
| `scripts/probes/cp27_spring_integration_wiring{.md,/}`, `cp28_gcp_pubsub_integration{.md,/}`, `cp29_gateway_properties{.md,/}` | probes (T6, T8) |
| `docs/…` register, COVERAGE, D01, D02, CHANGELOG, `scripts/coverage_matrix.py` | (T9) |

---

### Task 1: `bean-models/spring.yml` and `resolve/beans.py`

**Files:**
- Create: `src/sextant/catalogs/bean-models/spring.yml`
- Modify: `src/sextant/ingress/catalogs/yaml_source.py` (`_shape_models` → generalise to `_models("shape-models")`/`_models("bean-models")`; `Catalog` gains `bean_model: dict`), `src/sextant/application/ports/catalogs.py` (the `Catalog` dataclass field)
- Create: `src/sextant/application/resolve/beans.py`
- Test: `tests/application/test_beans.py`, `tests/ingress/test_yaml_source.py` (a catalog naming an unknown `bean_model` is refused naming the file)

**Interfaces:**
- Produces: `beans.bean_table(workspace, catalog) -> BeanTable` (a `once` fold keyed by the model), `BeanTable.bean_of(reference: BeanReference) -> BeanRef | Unresolved`, where `BeanReference` is `Parameter(method_symbol, index, erased_type, name, qualifier)` or `Call(method_symbol)` and `BeanRef(method: str, name: str, erased_return: str)`; `Unresolved(reason: 'ambiguous' | 'none')`. `BeanTable.kind_of(erased_type) -> 'channel' | 'other'` uses the model's `channel_types`.

- [ ] **Step 1: The model**

```yaml
# src/sextant/catalogs/bean-models/spring.yml — D02 §1c. The dependency-injection vocabulary a
# catalog's `bean_via` resolves through (spec 2026-09-21 §3a). A MODEL rather than engine
# constants for the reason shape models are: the resolve layer names no framework, and a
# second container (a .NET DI registration) is a second file, not a second engine.
id: spring
declaring_annotation: org.springframework.context.annotation.Bean      # spring-context 6.1.6: `value()`/`name()`, aliases — CP-27 row N
name_attrs: [name, value]
qualifier_annotation: org.springframework.beans.factory.annotation.Qualifier   # `value()` — CP-27 row N
# A parameter of one of these erased types is a CHANNEL reference: never resolved by type
# (Spring Integration auto-registers `errorChannel` and `nullChannel`, both MessageChannels, so
# the module's single @Bean MessageChannel is never Spring's unique candidate — spec §0b A2).
channel_types: [org.springframework.messaging.MessageChannel]
```

- [ ] **Step 2: Failing tests** (`tests/application/test_beans.py`, synthetic facts built the way `tests/application/test_combinator_engine.py` builds them; a catalog dict with `bean_model: spring`):

```python
def test_a_qualifier_names_the_bean(tmp_path): ...            # @Qualifier("ordersChannel") on the parameter → BeanRef(name="ordersChannel")
def test_a_channel_parameter_resolves_by_name_never_by_type(tmp_path): ...
    # one @Bean MessageChannel `ordersChannel()`, parameter named `inputChannel` → Unresolved('none'); named `ordersChannel` → BeanRef
def test_a_channel_name_the_index_knows_resolves_without_a_bean(tmp_path): ...  # parameter `auditChannel`, no @Bean, `known_channels={"auditChannel"}` → BeanRef(name="auditChannel", method=None)
def test_a_container_parameter_resolves_by_unique_type_then_name(tmp_path): ...  # one @Bean SimpleMessageListenerContainer → BeanRef; two → Unresolved('ambiguous'); two but one named like the parameter → that one
def test_a_bean_named_by_the_name_attribute_wins_over_the_method_name(tmp_path): ...  # @Bean(name="x") String y() → bean name x
def test_a_direct_call_to_a_bean_method_names_it(tmp_path): ...
def test_a_nameless_parameter_skips_the_name_rung(tmp_path): ...  # name None, one container by type → BeanRef; channel → Unresolved
```

- [ ] **Step 3: Implement `beans.py`**

```python
"""Bean identity (spec 2026-09-21 §3a): which declared factory method built the value an
injected parameter names. One fold per resolve over the annotation index and
`method_declarations`, driven by the catalog's bean model — the resolve layer names no
container. Consumed by fluent's `bean_via`; the field ladder's bean rung is a named follow-up."""

@dataclass(frozen=True)
class BeanRef:
    method: str | None      # the declaring method's full symbol; None for a channel the index knows but no method declares
    name: str
    erased_return: str | None

@dataclass(frozen=True)
class Unresolved:
    reason: str             # 'none' | 'ambiguous'

@dataclass(frozen=True)
class Parameter:
    method: str; index: int; erased_type: str; name: str | None; qualifier: str | None

class BeanTable:
    def __init__(self, by_name, by_type, channel_types, known_channels): ...
    def kind_of(self, erased_type: str) -> str: return "channel" if erased_type in self._channel_types else "other"
    def bean_of(self, reference: Parameter) -> BeanRef | Unresolved:
        if reference.qualifier is not None:
            found = self._by_name.get(reference.qualifier)
            return found or (BeanRef(None, reference.qualifier, None) if reference.qualifier in self._known_channels else Unresolved("none"))
        if self.kind_of(reference.erased_type) == "channel":
            if reference.name is None: return Unresolved("none")
            found = self._by_name.get(reference.name)
            if found: return found
            return BeanRef(None, reference.name, None) if reference.name in self._known_channels else Unresolved("none")
        by_type = self._by_type.get(reference.erased_type, ())
        if len(by_type) == 1: return by_type[0]
        if reference.name is not None and reference.name in self._by_name: return self._by_name[reference.name]
        return Unresolved("ambiguous" if len(by_type) > 1 else "none")
    def bean_called(self, method_symbol: str) -> BeanRef | None: ...   # a direct call to a declaring method
```

`bean_table(workspace, catalog, known_channels: frozenset[str])` builds `by_name` from methods carrying `declaring_annotation` (name = first present `name_attrs` string/array-first element, else the method's bare name), `by_type` from those methods' erased return symbols (`method_declarations.signature.returns.erased_symbol` — check the exact key the signature JSON carries), qualifiers from parameter annotations. `known_channels` comes from the caller (fluent hands it `config_join`'s channel names via `channel_bindings` `read_by` rows, or the catalog's own `channel_link` captures — Task 3 wires it; here it is a parameter).

- [ ] **Step 4: Loader** — `Catalog.bean_model` (dict, `{}` when absent); `yaml_source` reads `catalogs/bean-models/*.yml` by `id` as `_shape_models` does (factor the directory read into `_models(subdir)` — one function, two calls — and keep `_shape_model_of`'s error shape for `bean_model`). Refusal test for an unknown id.

- [ ] **Step 5: Gate, commit** `feat(resolve): bean identity — bean-models/spring.yml and resolve/beans.py, channel references by name only (spec §3a)`.

---

### Task 2: `channel_bindings` and the join pass

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql` (documentation only — the table is TEMP), create `reset_channel_bindings.sql`, `insert_channel_bindings.sql`; `workspace.py` `_NAMED_DERIVATIONS` (`channel_bindings_reset`, `channel_bindings_insert`) and `_NAMED_QUERIES["channel_bindings"]` (not fact-only; ordered on every column)
- Modify: `src/sextant/application/resolve/engines/config_join.py` — `run` writes `read_by` rows from `_channels` (channel names spelled `${…}` resolved through `_agreed(config, key)` first; unresolved → the raw spelling with `resolution: unresolved`); `gaps` skips a `(channel, direction=inbound)` that has a `fed_by` row; export `channel_index(workspace, catalog) -> list[_Channel]` (a public alias of `_channels`)
- Create: `src/sextant/application/resolve/channel_bindings.py` — `mint_channel_rows(workspace, catalogs)`
- Modify: `src/sextant/application/resolve/endpoints.py` — `derive("channel_bindings_reset")` beside the endpoint resets; call `mint_channel_rows` after the engine loop
- Test: `tests/application/test_channel_bindings.py`, `tests/storage/test_workspace.py`

**Interfaces:**
- Table: `channel_bindings(channel TEXT, role TEXT, symbol TEXT, protocol TEXT, direction TEXT, destination TEXT, catalog_id TEXT, resolution TEXT)`; `role ∈ {fed_by, read_by, sends_to}`.
- `mint_channel_rows`: for every `fed_by` (direction inbound) join every `read_by` (direction inbound) on `channel` → a `call_endpoints` row `{protocol: fed.protocol, direction: inbound, method: NULL, path: fed.destination, handler: read.symbol, caller: fed.symbol, resolution: fed.resolution, evidence: compiler, catalog_id: fed.catalog_id, shapes NULL, media NULL}`; a `fed_by` with no `read_by` → the same row with `handler` NULL. Both through `derive("call_endpoints")` (insert-if-absent). Outbound `fed_by` rows mint nothing here (the chain derived the outbound row) — they exist so `gaps` stops asking.

- [ ] Steps: reset/insert SQL (copy `reset_route_requirements.sql`'s shape); config_join `read_by` write inside `run` (the `_channels` loop already exists — add the rows list and one `derive`) and the `gaps` skip (`fed = {(r["channel"]) for r in workspace.query("channel_bindings") if r["role"] == "fed_by" and r["direction"] == "inbound"}`); the pass; tests: fed⋈read → one row with handler; two readers → two rows; unfed read → question kept (run `gaps`); fed without reader → adapter row, handler NULL; `${probe.audit-channel}` read_by resolved via a config entry → joins; unresolved placeholder → no join, question kept; outbound fed_by suppresses the question and mints nothing.
- [ ] Gate (no golden moves — nothing writes `fed_by` yet; `read_by` rows are invisible outside the temp table), commit `feat(resolve): channel_bindings — the channel edge as data; read_by from config_join; the fed⋈read join pass; gaps asks only about unfed channels (spec §3b)`.

---

### Task 3: fluent — `direction:` per root, `handler`, `channel_link`, `poisons:`, `compose:`, `undeclared_steps`, inbound rows

**Files:**
- Modify: `src/sextant/application/resolve/engines/fluent.py` — `run` (root/step parsing + validation), `_walk`, `_derive`, `_step_captures`, `_validate_captures`
- Test: `tests/application/test_call_engines.py` (fluent's home — check where fluent unit tests live; add a `test_fluent_registrations.py` if the file is already large)

**Interfaces (catalog words, all optional):**
- root: `direction: inbound|outbound` (overrides the catalog's for chains from this root); `captures.handler: argN` (a `lambda` argument → its `symbol` joined through `method_symbols`; else `{kind: parameter}`/bean → Task 4; else unresolved); `captures.channel_link: argN` (a `string` literal → the name; else unresolved).
- step: `poisons: [field, …]` — marks each field unreadable from this step on (`captures[field] = _POISONED`); `compose: { field: [half, half], join: "/" }` on the ROOT — at derive, `field` is the halves joined when every half was captured as a literal, else unresolved.
- catalog: `undeclared_steps: { owner: [types], poisons: [handler] }` — a site on one of those owners that matches no declared step applies the poisons (the flow-definition rule: an unknown member is a `divert`).
- rows: when the effective direction is `inbound`, `handler` = the captured handler's method symbol (or NULL); when `channel_link` was captured (resolved), the chain writes a `channel_bindings` `fed_by` row `(channel=link, symbol=caller, protocol, direction, destination=path, catalog_id, resolution)` INSTEAD of an endpoint row — Task 2's pass mints the rows (spec §3b, and the plan's ruling: the pass owns rows for linked registrations so a linked adapter is never counted twice); an unresolved `channel_link` → the endpoint row with `handler` NULL and no binding.

- [ ] **Tests first** (synthetic facts; a fluent catalog dict built inline): a `<init>` root with `captures: {channel: arg1}` on an inbound catalog and a `handle`-like step capturing `handler: arg0` from a `lambda` argument → one inbound row with `handler` = the lambda body's symbol; a `poisons: [handler]` step before the handler step → handler NULL, row resolved (path known); `undeclared_steps` on the owner → same; `channel_link` literal → no row, one `fed_by` binding; `channel_link` from an unresolved argument → row with handler NULL, no binding; `compose` both halves → `a/b`; one half missing → path unresolved; a root `direction: outbound` inside an inbound catalog → outbound row; **the thirteen shipped fluent catalogs' e2e goldens unchanged** (the full gate).
- [ ] Implement in the file's voice; `_derive` gains the inbound branch and the binding write (`context.bindings.append(...)`, derived once in `run` after `call_endpoints`).
- [ ] Gate, commit `feat(fluent): handler and channel_link captures, per-root direction, poisons, compose, undeclared_steps; inbound rows and fed_by bindings (spec §2, §4)`.

---

### Task 4: fluent — `bean_via` and `method_annotation`

**Files:**
- Modify: `fluent.py`; Test: the fluent test file

**Interfaces:**
- capture value `{ bean_via: argN }`: the argument must be `{kind: parameter, value: i}` (the caller's parameter i, with `caller_parameters` giving its erased type/name/qualifier — `declared_parameters_of` already supplies them) or a call site in the same caller whose target is a declaring method (`bean_called`). Resolution through `beans.bean_table(workspace, catalog, known_channels)`, where `known_channels` = every `read_by` channel name in `channel_bindings` plus every literal `channel_link` this catalog's chains captured so far — build it once per run BEFORE the walk from `config_join.channel_index` over the loaded catalogs (the engine loop order: `config_join` may not have run yet → read the channel names directly through `channel_index(workspace, <spring-integration catalog>)`; the endpoints loop hands each engine the full catalog list — check `derive_endpoints`' signature and pass `catalogs` through `run`'s context if needed).
  - on `channel_link`: the value is the bean's **name**;
  - on any other field (`channel`): the value is the CAPTURES of the bean's own chain — find the `BeanRef.method`'s sites (`context.by_caller`), the root there matching the catalog's `beans:` list (roots reachable only through `bean_via`, same shape as `roots`), walk it with a fresh capture dict and a collecting context (`_walk` with a `sink` that records final captures instead of deriving), and take `captures[field]`; several ends → the first, if all agree, else unresolved.
  - `Unresolved` → the field is unresolved (`_POISONED` with reason).
- root option `method_annotation: { annotation, arg, into }`: the constructing method's annotation `arg` (through the annotation index, `bare_descriptor(caller)`) supplies `captures[into]` as a string literal.

- [ ] Tests: `setOutputChannel(param)` with `@Qualifier` → link name; by parameter name matching a `@Bean` → name; by name known to the index only → name; two candidates → unresolved (row, handler NULL, no binding); container hop: `new Adapter(containerParam)` + `beans:` root `SimpleMessageListenerContainer` with `setQueueNames("q1","q2")` in the container's method → two rows `q1`,`q2`; container built in a third bean → unresolved; `method_annotation` → `channel_link` from `@ServiceActivator(inputChannel)` on the constructing method → outbound row + outbound `fed_by`.
- [ ] Gate (goldens unchanged), commit `feat(fluent): bean_via through the shared bean table; method_annotation captures (spec §3a, §4)`.

---

### Task 5: fluent — `continue_via_argument`, `sinks:`, `channel_via` on constructors

**Files:** `fluent.py`; tests.

**Interfaces:**
- terminal entry `{ method: <name> | via_argument_of: {owner, method}, continue: true }`: when the chain's value is consumed as an argument of the named call (the `_has_execute_join` test), the walk CONTINUES from the consuming site along its own result chain with the same captures, first folding `_prefix_captures(consuming_site)` (the consumer's receiver ancestry — `from("ch")` before `handle(spec)`); derivation happens at the continued chain's end. Two forms: a spec chain that ends WITHOUT its own terminal (`Kafka.messageDrivenChannelAdapter(cf, "t")` handed straight to `from`) — `via_argument_of` names the consumer and the join is tested on the root/step site itself; a spec chain ending in `build()` — `method: build, continue_via_argument: {owner, method}`.
- `sinks:` — root-shaped entries whose chains are consumed by a `handle`-like step: declared as ordinary `roots` with `via_argument_of: {owner: IntegrationFlowDefinition owners, method: handle}, continue: true` — no new key: a sink is a root whose continuation is the flow. (Drop the spec's separate `sinks:` word; the plan's ruling: one mechanism.)
- `channel_via` already accepts `{owner, method, arg}`; allow `method: <init>` with an optional `descriptor` so `new ContainerProperties("t")` / `new Queue("q")` resolve the destination (check `linked_channels` in `shapes/…` for where the producing-site match lives and add the descriptor filter).

- [ ] Tests: spec chain → `from(spec)` → `.transform(...)` (pass-through) → `.handle(lambda)` → one inbound row, handler = lambda body; `.route(...)` before `handle` → handler NULL; `.channel("x")` → `fed_by` for `x` AND the walk continues to a later `handle` → row too; `from("ch")` (root, `channel_link`, `direction: outbound`) → `.handle(sinkSpec)` where the sink chain `outboundChannelAdapter(t).topic("out")` joins → one OUTBOUND row `path=out` + outbound `fed_by(ch)`; `build()`-terminated spec → same as direct; `channel_via` on `new ContainerProperties("t")`.
- [ ] Gate (goldens unchanged), commit `feat(fluent): continue_via_argument — an argument join that continues the walk; constructor channel_via (spec §5)`.

---

### Task 6: The three broker catalogs, the step model, fixtures, CP-27 and CP-28

**Files:**
- Create: `src/sextant/catalogs/step-models/spring-integration.yml` (id `spring-integration`; `owners: [org.springframework.integration.dsl.IntegrationFlowDefinition, org.springframework.integration.dsl.BaseIntegrationFlowDefinition, org.springframework.integration.dsl.IntegrationFlowBuilder]`; `steps:` — the 35 members as fluent step entries: pass-through members with `captures: {}`; `channel(String)` `captures: {channel_link: arg0}`; `channel(MessageChannel)` `{channel_link: {bean_via: arg0}}`; `channel(MessageChannelSpec)` unresolved link; `fixedSubscriberChannel(String)` link; `handle(GenericHandler)`/`handle(Class, GenericHandler)`/`handle(MessageHandler)`/`handle(Object, String)`/`handleReactive` `captures: {handler: argN}` per descriptor; `nullChannel` `captures: {handler: none}` (a literal NULL handler, resolved — a new capture literal `none`; add to Task 3 if missed); `route routeByException routeToRecipients gateway scatterGather publishSubscribeChannel controlBus trigger to` `poisons: [handler]`; `undeclared_steps: {owner: <the owners>, poisons: [handler]}`), loaded like `bean_model` (`step_model: spring-integration` merges the model's steps into `matches.steps`)
- Create: the three catalogs exactly as spec §4/§5 (with `{owner, method: <init>}` for the spec's `new:` roots; `via_argument_of … continue: true` per Task 5; every Kafka overload by descriptor from CP-27's table; `field_sources` copied from `spring-resttemplate.yml`; `bean_model: spring`; `step_model: spring-integration`; `beans:` for AMQP containers; `measured:` blocks)
- Modify: `fixtures/spring-integration-probe/pom.xml` (+ `com.google.cloud:spring-cloud-gcp-pubsub:5.1.2`), `src/main/resources/application.properties` (+ `probe.subscription=orders-sub`, `probe.audit-channel=amqpAuditChannel`), new `Shape4PubSub.java` (inbound adapter with `setOutputChannel(@Qualifier("pubsubInputChannel") MessageChannel c)`; a second with `setOutputChannelName("pubsubInputChannel")` and a `@Value("${probe.subscription}") String` subscription; `@Bean MessageChannel pubsubInputChannel()`; `@ServiceActivator(inputChannel = "pubsubInputChannel")` handler; `@Bean @ServiceActivator(inputChannel = "pubsubOutputChannel") PubSubMessageHandler out(PubSubTemplate t) { return new PubSubMessageHandler(t, "orders-topic"); }`), new `Shape5Flows.java` (AMQP DSL `Amqp.inboundAdapter(cf, "dsl.q1", "dsl.q2")` → `.transform(...)` → `.handle(lambda)`; AMQP outbound bean `AmqpOutboundEndpoint` with both setters under `@ServiceActivator`; Kafka flow with `.route(...)`; Kafka flow ending `.channel("kafkaInputChannel")` + a `@ServiceActivator` on it; a `Pattern` source; the ambiguous-bean case — two `MessageChannel` beans and an adapter taking an unnamed-match parameter)
- Create: `scripts/probes/cp27_spring_integration_wiring{.md,/run.sh,/probe.py}` (jars in `~/.m2`: spring-integration-core/-kafka/-amqp 6.2.4, spring-rabbit, spring-kafka, spring-context 6.1.6, spring-beans 6.1.6; rows: F1–F5, F8, the 35 members with each divert member's constructed handler class, `determineAutowireCandidate`'s order, `MessageProducerSupport` setters), `cp28_gcp_pubsub_integration{.md,/}` (spring-cloud-gcp-pubsub 5.1.2: F10 + `from(MessageProducerSupport)`); identities from each jar's manifest, `test_probe_provenance.py` green
- Test: `tests/e2e/test_async_delivered.py` — rows per shape (Pub/Sub inbound `orders-sub`→handler; `${probe.subscription}` expression row; outbound `orders-topic`; AMQP `bean.orders.queue` (Shape 2 now derives!) with handler `handleOrder`; DSL `dsl.q1`/`dsl.q2`; Kafka topics with handler / NULL-after-route / channel-joined handler; the `Pattern` source unresolved; the ambiguous case handler NULL); the `channel_destination` questions that remain are exactly the unfed ones (`handleConstantChannel`'s `Destinations.ORDERS_CHANNEL`? — it is a constant; check whether the index resolves constants; whatever it is today stays); every moved pin reported.

- [ ] Gate, commit `feat(catalogs): Spring Integration Pub/Sub, AMQP and Kafka adapters and flows on fluent; the flow step model; CP-27/CP-28 (spec §4–§6)`.

---

### Task 7: `dsl-media-route`

**Files:** `spring-webflux-router.yml`, `spring-mvc-router.yml`; `fixtures/orders-service` router classes (`OrderRoutes.java`: `.add(route(accept(APPLICATION_JSON), h))`? — no: the DSL overload is Kotlin's `accept(MediaType, Function1)`; add to `KotlinOrderRoutes.kt` `accept(MediaType.APPLICATION_JSON) { ok() }` inside `coRouter {}` and the servlet twin if a Kotlin servlet router fixture exists); `combinator.py` — remove the `_carries_a_handler` unresolved-row arm for names now declared as verb rules (the arm stays for any other media rule); tests.

- [ ] Catalog: on `CoRouterFunctionDsl`, `RouterFunctionDsl` (both stacks): `{ owner, method: accept, arity: 2, media_arg: 0, fills: produces, handler_arg: 1, verb: null }` and the `contentType` twin `fills: consumes` — check `_validate_matches` allows `media_arg`/`fills` on a VERB rule (Task 9 of the previous spec added them to prefixes; extend to verbs if refused, with a test).
- [ ] e2e: one resolved row `(None, "/**", produces ["application/json"])` per stack with the handler; the previous unresolved-row pin moves and says why; no other row moves (spec §0b A1).
- [ ] Gate, commit `feat(combinator): a router route declared under a media guard alone derives its any-path row with its media (dsl-media-route)`.

---

### Task 8: `gateway-properties-routes` — `indexed:` in `config_join`, CP-29

**Files:** `config_join.py` (`indexed:` address form), `spring-cloud-gateway-properties.yml` (style `config_join`, protocol `http`, detect the Gateway coordinates, `indexed: { prefix: spring.cloud.gateway.server.webflux.routes, item: { path: {field: predicates, grammar: gateway_shortcut, name: Path}, method: {…, name: Method}, requirements: {…, names: {Header: header, Query: query, Cookie: cookie}}, pass_through: [Host, After, Before, Between, RemoteAddr, Weight, XForwardedRemoteAddr, CloudFoundryRouteService, ReadBody], peer: {field: uri} } }`), `fixtures/orders-gateway/src/main/resources/application.yml`, CP-29, tests.

- [ ] CP-29 first: `GatewayProperties.PREFIX`, whether `spring.cloud.gateway.routes` still binds at 5.0.0 (a legacy `@ConfigurationProperties` or `DeprecatedConfigurationProperty`? read the class list), `PredicateDefinition(String)` grammar, the five factories' `shortcutFieldOrder`/`shortcutType`, `RouteDefinition` fields, `HttpMethod.values()`.
- [ ] Engine: iterate `resolved_config` keys under `<prefix>[N].` (the config layer flattens lists to `key[N]`); per item: predicates `[M]` as shortcut strings (`Name=a,b`) or map form (`[M].name`, `[M].args.<field>`/`_genkey_K`); `Path` → one inbound row per pattern (`_agreed` per key; disagreement → no row + `environment_divergence` as today); `Method` → one row per method, else `method` NULL (A7); `Header`/`Query`/`Cookie` → `route_requirements` stash rows (`caller`/`handler` NULL; `value` = the regex spelling per the D01 amendment); unknown predicate → the item's rows unresolved; `uri` → an outbound row (direction per rule — `config_join` carries it) with `peer` from the scheme as `spring-cloud-gateway-outbound.yml` derives (`lb://name` → `name`; `http(s)://host` → host); `filters` unread (stated).
- [ ] Fixture `application.yml`: two routes — shortcut (`Path=/cfg/orders/**`, `Method=GET,POST`, `Header=X-Api,v2`, `uri: lb://orders`) and map form (`name: Path`, `args.pattern: /cfg/items/**`; `uri: http://items.internal:8080`).
- [ ] e2e: rows `(GET|POST, /cfg/orders/**)`, `(NULL, /cfg/items/**)`, outbound peers `orders`, `items.internal`; `endpoint_metadata` `header X-Api v2 required` on the two `/cfg/orders/**` rows.
- [ ] Gate, commit `feat(config_join): indexed configuration routes — Spring Cloud Gateway property routes with their predicates, requirements and peers (gateway-properties-routes; CP-29)`.

---

### Task 9: Register, COVERAGE, D01, D02, CHANGELOG, coverage matrix

- [ ] Register: `pubsub-channel-adapter`, `dsl-media-route`, `gateway-properties-routes` closed with pinning tests and `<pending PR CI>`; the Pub/Sub ```delivery``` row empties; REST in keeps `conditional-controllers`; new OIs: the field ladder's bean rung (follow-up), `sends_to` writers, `@Profile`-twin beans (with `conditional-controllers`), spec-configurer queue additions, two-hop container sources, Gateway `filters`.
- [ ] COVERAGE: §5.11 Spring Integration line ✅; §5.12 boundary row → shipped (both spellings, three brokers) with the tests; §5.8 "Spring Integration Kafka" line; §5.9 AMQP adapter line; §5.1 router `dsl-media-route` row and Gateway properties row; the framework rollups regenerated (`scripts/coverage_matrix.py`; `ITEM_FRAMEWORKS` drops the three ids).
- [ ] D02: fluent's new keys; `bean_model`/`step_model`; `config_join` `indexed:`; the router media verb rules. D01: `channel_bindings`. CHANGELOG entry. Spec §0c note on the plan's two rulings (no `sinks:` word; `new:` is `{owner, method: <init>}`).
- [ ] Gate incl. `--guards`; commit `docs(register): pubsub-channel-adapter, dsl-media-route and gateway-properties-routes close; the destination behind a channel is read for Pub/Sub, AMQP and Kafka`.

---

## Self-review

**Spec coverage:** §3a→T1; §3b→T2; §3c→T3 (rows) + T2 (join); §4→T3+T4+T6; §5→T5+T6; §6→T6; §7a→T7; §7b→T8; §8→catalog comments + T9 OIs; §9→T6 (CP-27/28), T8 (CP-29); §10→each fluent task's byte-identical gate; §11→T6/T7/T8; §12/§13→T9.

**Plan-level rulings (recorded here, to be carried into the spec's §0c by T9):** (1) the spec's `new:` root is the existing `{owner, method: <init>}` form — no sugar; (2) no separate `sinks:` word — a sink is a root whose continuation is the flow (`via_argument_of … continue: true`); (3) the join pass owns the rows for linked registrations (a chain that captured a resolved `channel_link` writes a binding and no row), so a linked adapter is never counted twice; (4) `known_channels` for bean resolution comes from `config_join`'s channel index read directly, so the engine order in the loop does not matter.

**Type consistency:** `BeanRef(method, name, erased_return)` (T1) is what `bean_via` reads (T4); `channel_bindings` columns (T2) are what fluent writes (T3) and the pass joins (T2); `Catalog.bean_model`/`step_model` (T1/T6) are read by fluent's `run` through `catalog.bean_model` / merged steps.
