# A bean that exists in some environments only — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace PR #61's controller-only conditions with the general rule — every bean Spring registers conditionally, every row and every call candidate derived from it — and close `OI-108`.

**Architecture:** One `bean_conditions` table keyed by the bean (the class whose code runs), written by one pass that reads the condition vocabulary from the Spring bean model; rows and call candidates find their conditions through `symbols.enclosing`; `endpoint_conditions` becomes a view over that join; the documents state conditions on every derived row and, per environment, which candidates of a narrowed call exist.

**Tech Stack:** Python 3.13, DuckDB (floor `>=1.1` — no newer function), JDK 21 for fixtures, `javap` probes.

**Spec:** `docs/superpowers/specs/2026-10-22-conditional-beans-design.md` — all three decisions ruled 2026-10-22 (§6); §2a registration rule, §2b probe, §2c bean-presence rule.

## Global Constraints

- **General rule, never a special case** (standing user rule): any bean, any derived row (inbound and outbound endpoints, scheduled work, error handlers), any call candidate.
- **Stated, not decided**: no row, link or call edge is dropped or added in any environment; `call_edges.resolution` is never changed.
- **One table keyed by the bean** (decision 3); readers JOIN; `endpoint_conditions` keeps its name as a view.
- **Framework knowledge is data**: condition annotations, the configuration annotation and the stereotype set live in `catalogs/bean-models/spring.yml`, each claim citing a probe; resolve code names no framework.
- **Profile/property evaluated exactly as PR #61** (CP-42, CP-43) — the code MOVES, it is not copied.
- **`@ConditionalOnMissingBean`/`@ConditionalOnBean`** from the module's own beans, `partial`, the stated reason (decision 2, §2c).
- Determinism; layering; symbol grammar in `domain/symbols`; fixtures with JDK 21; every moved pin re-pinned with its cause; every new rule a guard; field pins.

## Review Focus

1. A `@Bean` method whose body constructs helper objects beside the bean it returns (`new KafkaTemplate(new DefaultKafkaProducerFactory(...))`) — only the class assignable to the return type is the bean (Task 2 `test_a_factory_conditions_only_the_class_it_returns`).
2. A class both scanned and constructed by a conditional factory — `unresolved` with the reason, never conditional (Task 2 `test_a_class_registered_two_ways_is_unresolved`).
3. Two beans each `@ConditionalOnMissingBean` of one type — `unresolved`, never a pick (Task 3 `test_two_missing_bean_defaults_are_unresolved`).
4. A workspace analysed before this branch (has `endpoint_conditions` as a TABLE) federated into a system run — refused by name as today, not a bare error (Task 2 keeps `StaleParticipantError` working with the view).
5. A narrowed call whose candidates carry no condition at all — renders exactly as today, no empty per-environment block (Task 5 `test_an_unconditional_narrowed_site_renders_unchanged`).

---

### Task 1: Probe CP-44 and the condition vocabulary in the bean model

**Files:** Create `scripts/probes/cp44_bean_registration_conditions/{run.sh,probe.py}`, `scripts/probes/cp44_bean_registration_conditions.md` (reuse `scripts/probes/_spring_jar.py`); modify `src/sextant/catalogs/bean-models/spring.yml`, `src/sextant/catalogs/spring-web.yml`, `spring-mvc.yml` (remove `matches.mapping.conditions`), `src/sextant/application/resolve/endpoint_conditions.py::_models` (read from `bean_model`), the loader's validation if `bean_model` keys are validated; every Spring catalog that runs on a Spring module and must hand the bean model to the pass names `bean_model: spring`.
**Probe rows:** (1) `OnBeanCondition` deduces the type of an unannotated use on a `@Bean` method from the return type; (2) `value`/`type`/`name` matching; (3) the bean-factory search sees definitions registered so far (order caveat); (4) `ConditionEvaluator.shouldSkip` call sites: component scanning, `@Import`/configuration class processing, `@Bean` method loading — none on a class constructed inside a `@Bean` body. Version from the jar manifests; table headers are the versions (`test_probe_provenance.py`).
**Bean model keys:** `conditions:` (CP-42/43's `profile`, `property`, `other` entries moved verbatim) plus `presence: {missing: …ConditionalOnMissingBean, present: …ConditionalOnBean, type_attrs: [value, type], name_attrs: [name], by: cp44}`, `configuration_annotation`, `stereotypes: [...]` (`@Component`, `@Service`, `@Repository`, `@Controller`, `@RestController`, `@Configuration`, `@ControllerAdvice`, `@RestControllerAdvice` — by CP-44 row 4).
- [ ] Probe written, run, document generated; `tests/architecture` green.
- [ ] Vocabulary moved; PR #61's tests still pass unchanged (behaviour identical).
- [ ] Commit `feat(catalogs): the condition vocabulary moves to the Spring bean model; CP-44`.

### Task 2: `bean_conditions` and the general pass

**Files:** Create `src/sextant/application/resolve/bean_conditions.py` (the pass; `_holds`/`_expression`/`_config_by_environment` MOVE here from `endpoint_conditions.py`, which is deleted); `schema.sql` (`bean_conditions` table; `endpoint_conditions` dropped as a table and re-created as a VIEW: endpoints ⨝ `symbols` on handler/caller → `enclosing` ⨝ `bean_conditions`, same columns as before); `insert_bean_conditions.sql`, `reset_bean_conditions.sql`; `workspace.py` (named queries, export map exports both, `_FEDERATED_VIEWS` unchanged by name); `pipeline.py` (one pass replaces `record_endpoint_conditions`; `ResolveReport.bean_conditions`); `domain/version.py` (`GRAPH_SCHEMA_VERSION` 3 → 4).
**Rule:** spec §2a — beans = conditional stereotype classes (`class`) and classes a conditional `@Bean` (or a `@Bean` in a conditional configuration class) constructs AND that are assignable to its return type (`factory`/`configuration`); a class registered two ways → `unresolved` row with the reason. One row per (bean, condition, environment). Rows of every kind find their bean through the owner class of their handler/caller/advice symbol.
**Tests (hand-built facts through the shipped catalogs):** a conditional scanned class's outbound endpoint and scheduled job carry its condition; a `@Profile` `@Bean` factory's constructed class carries the factory's; a `@Bean` in a `@ConditionalOnProperty` configuration class inherits it; `test_a_factory_conditions_only_the_class_it_returns`; `test_a_class_registered_two_ways_is_unresolved`; the `endpoint_conditions` view returns exactly PR #61's rows on PR #61's own test facts (re-run those tests unchanged against the view).
- [ ] RED, GREEN, gate, commit `feat(resolve): conditions belong to the bean — one table, every derived row (OI-108)`.

### Task 3: Bean-presence conditions at `partial`

**Files:** `bean_conditions.py` (a second phase after profile/property), tests.
**Rule:** spec §2c exactly; type match through `type_hierarchy` (a bean of the type or a subtype); `resolution = partial`, `evidence` = the stated reason; a competitor `unresolved` there → `unresolved`; two `OnMissingBean` of one type → `unresolved` with the reason.
**Tests:** a default `@ConditionalOnMissingBean(UserService)` beside a `@Profile("ldap")` `UserService` → default holds everywhere but `ldap`, `partial`; `@ConditionalOnBean` the inverse; `test_two_missing_bean_defaults_are_unresolved`; a competitor under an `other` condition → `unresolved`.
- [ ] RED, GREEN, gate, commit.

### Task 4: Every derived row states its condition in the documents

**Files:** `egress/render/document.py` (PR #61's two detail lines on outbound rows, scheduled jobs, error handlers — the same function, fed by a by-owner index rather than by-handler), `egress/render/system.py` and `api.py` (`_with_inbound_conditions` generalized to both ends of a link: `Link.from_conditions` beside `to_conditions`), tests in `tests/egress`, `tests/e2e/test_system_document.py`.
- [ ] RED, GREEN, gate, commit.

### Task 5: A narrowed call states which candidates exist in each environment

**Files:** a named query joining `call_edges` candidates' callee owner to `bean_conditions`; the trace renderer in `egress/render/document.py` (the narrowed-site block, ~line 2026 onward) adds, under a site whose candidates carry conditions, one line per environment naming the candidates that exist there (`holds = true`), those not evaluated, and none dropped; `diagrams.py` unchanged.
**Tests:** a two-implementation `@ConditionalOnProperty` site renders per environment; a `partial` verdict says so; `test_an_unconditional_narrowed_site_renders_unchanged`.
- [ ] RED, GREEN, gate, commit.

### Task 6: Fixtures and moved pins

**Files:** `fixtures/orders-service`: a `WebSocketMessageSender`-shaped interface with two `@ConditionalOnProperty` implementations on a narrowed call reached from a handler; a `@Bean @Profile("prod")` factory whose class makes an outbound call; a `@ConditionalOnMissingBean` default beside a `@Profile` override; `application-prod.yml` values. Build with JDK 21; every moved count re-pinned with its cause (`tests/cli/test_app.py`, `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`, `tests/ingress/test_asm_scanner.py`); an e2e test on the rendered document text.
- [ ] Gate, commit.

### Task 7: Guards and field measurement

**Files:** `scripts/guard_check.py` — guards: a factory conditions only the class it returns; two registrations → unresolved; `OnMissingBean` reads competitors; `partial` carried; outbound rows read the view; narrowed sites state per-environment candidates. `scripts/field-expectations/apollo-portal.json`: the measured per-environment candidates of `checkUserExists` (`ldap`, `oidc`, default) recorded under `notes` + an assertion key if the checker gains one cheaply; re-measure spec §1's table with `scripts/probes/measure_conditional_beans.py` and record it.
- [ ] Guards killed; all six field pins ok; commit.

### Task 8: Documents as built

**Files:** D01 (`bean_conditions`, the view, the join), D02 (`bean_model` keys; `mapping.conditions` removed), D05/D06 if metadata/manifest change, M06 (outbound side of a link), M07 (rows and narrowed sites), COVERAGE (the `conditional-controllers` row generalized to conditional beans; rollups regenerated), `docs/open-issues.md` (`OI-108` CLOSED, `OI-168` re-read against the new pass), the delivery list, CHANGELOG, the spec §1 "as built" numbers.
- [ ] `tests/architecture` green, `coverage_matrix.py --check`, full gate, commit; push; PR.
