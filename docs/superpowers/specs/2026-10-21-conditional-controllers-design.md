# A controller that exists in one environment only — design

**Status: RULED 2026-10-22.** Decision 1: stated on the row, **as a structured table a machine
reads**, with the architecture document the one verbose rendering of it. Decision 2: a
condition is a property of the INBOUND ENDPOINT and travels with it as data; matching never
reads it, in a reactor or anywhere — *"an endpoint is an endpoint … what matters is only the
schema, path, protocol, not how the endpoints are implemented."* §6 records both; the plan
beside this file (`../plans/2026-10-22-conditional-controllers.md`) sequences the work.

**Goal.** Close the last open cell on the Spring MVC row for real code: COVERAGE's
`conditional-controllers` (`@ConditionalOnProperty` / `@Profile` controllers — "exists in one
environment only", status C). Today such a controller's endpoints are published as if they
always existed. The ruling this builds on is spec 2026-09-21 §0c B5's own words: *a row's
existence conditional on configuration, stated on the row rather than decided.*

---

## 1. What exists, measured across every cloned corpus

| corpus | classes carrying `@Profile(…)` / `@ConditionalOnProperty(…)` | of them controllers |
|---|---|---|
| `apollo` (8 modules) | 17 | **1** — `apollo-configservice`'s `HomePageController` |
| `spring-petclinic-rest` | 31 | 0 |
| `ruoyi-vue-pro` | 16 | 0 |
| `jhipster-sample-app` | 4 | 0 |
| `spring-petclinic-microservices` | 1 | 0 |
| `mall`, `mall-swarm`, `spring-petclinic`, `tradewind` | 0 | 0 |

**One real controller, 69 real conditional classes.** The conditional CONTROLLER is rare; the
conditional BEAN (`OI-108`: a `@Profile("local")` in-memory adapter beside its
`@Profile("prod")` broker one) is the common shape, 68 of the 69. The design below is built
for the row — the cell — with the bean fold as the stated next consumer of the same
mechanism, because the two are one question (`OI-108`: *"closes with
`conditional-controllers`' mechanism"*).

The instance:

```java
@Profile({"kubernetes", "nacos-discovery", "consul-discovery", "zookeeper-discovery",
    "custom-defined-discovery", "database-discovery",})
@RestController
public class HomePageController {
  @GetMapping("/")
  public List<ServiceDTO> listAllServices() { … }
```

What `apollo-configservice`'s document says today (measured 2026-10-21):

```
- Environments resolved: `consul-discovery`, `custom-defined-discovery`, `database-discovery`,
  `default`, `github`, `kubernetes`, `nacos-discovery`, `zookeeper-discovery`.
…
| `GET /` | `HomePageController#listAllServices` | — → — | json (assumed) | resolved |
```

The eight environments are the module's own `application-<profile>.properties` files
(`config_model.profiles.from_filename`, Spring's rule). The controller names six of them. The
row says nothing about any of this.

## 2. What is published

The condition is a FACT about the row, not a decision about it. **The stored form is a table,
not a sentence** (ruling 1): one row per (endpoint, condition, environment), exported to
Parquet with the rest of the bundle, so a machine reads it without parsing prose.

```
endpoint_conditions
protocol | direction | method | path | handler | kind | expression | environment | holds | resolution | evidence
```

* `kind` is `profile`, `property`, or `other`; `expression` is JSON text typed per kind —
  **as built**: `profile`: `{"expressions": [...]}` (the strings as the code spells them,
  `!` and all — a `none_of` split would re-spell the framework's own grammar); `property`:
  `{"keys": [...], "having_value": "true", "match_if_missing": false}` (several names are
  several keys the framework requires ALL of, CP-43); `other`: `{"annotation": "...",
  "args": {...}}` verbatim, for a condition this analysis does not evaluate.
* `environment` is one of the module's resolved environments; `holds` is `true`, `false` or
  `unresolved`; `resolution` is `resolved` where the verdict was read off the framework's own
  rule and `unresolved` where it was not (`other`, or a key resolving to a placeholder).
* For Apollo's `GET /`: eight rows, `holds = true` in six, `false` in `default` and `github`.

The architecture document is the one VERBOSE rendering, in the endpoint's detail block:

```
- `GET /` — `HomePageController#listAllServices`
  - Exists only when the active profile is one of: `kubernetes`, `nacos-discovery`,
    `consul-discovery`, `zookeeper-discovery`, `custom-defined-discovery`, `database-discovery`.
    Of this module's environments: holds in 6 of 8 — not in `default`, `github`.
```

Two halves, both derived from the table and nothing else: the condition as the code
spells it, and whether it HOLDS in each environment this module resolves — which for
`@Profile` is exact (an environment IS a profile, by the rule the config layer already
applies), and for `@ConditionalOnProperty` is the key's resolved value in that environment,
which `resolved_config` already holds per environment. No row is dropped and no row is
asserted: `default`'s reader sees that this endpoint is not served there, `kubernetes`'s
that it is.

## 3. The mechanism

### 3a. Framework knowledge is catalog data

A `conditions:` block on the inbound HTTP catalogs (`spring-web.yml`, `spring-mvc.yml`),
beside `request_requirement_attrs`:

```yaml
conditions:
  profile:  { annotation: org.springframework.context.annotation.Profile,
              arg: value, grammar: any_of_negatable,
              by: scripts/probes/cp42_profile_condition.md }
  property: { annotation: org.springframework.boot.autoconfigure.condition.ConditionalOnProperty,
              args: [prefix, name, value, havingValue, matchIfMissing],
              by: scripts/probes/cp43_on_property_condition.md }
```

Two probes, §5.4 provenance read off the jars themselves: CP-42 — `@Profile`'s `value` is
any-of, `!p` negates, read off `ProfileCondition`/`Profiles.of` in `spring-context`; CP-43 —
`@ConditionalOnProperty`'s `name`/`value` alias, `prefix`, `havingValue` (empty means "any
value but `false`"), `matchIfMissing`, read off `OnPropertyCondition` in
`spring-boot-autoconfigure`. Versions as the probe reads them from the jars, never a
parameter.

### 3b. One pass, after the rows exist

`resolve/endpoint_conditions.py`, run where `request_requirements` runs (after
`apply_protocol_hints`, before the open-questions reset): for every inbound row whose
catalog declares `conditions`, read the class-level annotations of the handler's type
through the existing `conditions.py::annotation_index` (one decode per load), and write
`endpoint_conditions` rows (§2): one per (condition, environment the module resolved).
`profile` holds where the environment's name is in `any_of` and not in `none_of` — exact,
by the config layer's own filename rule; `property` holds where the key's `resolved_config`
value in that environment equals `having_value` (empty meaning any value but `false`,
CP-43), and an ABSENT key is decided by `match_if_missing` (the framework's own rule); a key
resolving to a placeholder nobody filled is `unresolved` there — stated, not guessed.
`other` is written verbatim with `holds = unresolved` in every environment.

Cost (§8.7): one read of `endpoints`, one `annotation_index` lookup per inbound handler
type, one `resolved_config` read per `property` condition per environment; nothing per
catalog.

### 3c. The documents

The module document's detail block gains the two lines of §2, derived from the table. The
inbound table's columns are unchanged: a condition is a fact about where the row exists, not
a sixth column every unconditional row would carry empty.

**The system document (ruling 2).** The matcher is untouched — it joins an outbound endpoint
to an inbound one on protocol, verb and path, and nothing about either side's implementation
or environment enters that join. A link whose inbound endpoint carries conditions states them
beside the link ("inbound endpoint holds in `kubernetes`, not in `github`"), read from the
participant's own `endpoint_conditions` through the federated view, exactly as the inbound
row itself is read. No link is dropped or added for it.

## 4. What it does NOT do

* **Does not drop a row or a link** anywhere, in any environment. Stated, not decided (B5).
* **Does not make matching environment-aware.** An endpoint is an endpoint (ruling 2); the
  condition is data on the inbound side and the link carries it.
* **Does not read `@Conditional(SomeClass.class)`**, `@ConditionalOnBean`,
  `@ConditionalOnExpression`, or a custom condition: each is code, not configuration, and
  publishing a verdict would be guessing. A row carrying one gets `endpoint_conditions` rows
  of kind `other`, `expression` the annotation and its arguments verbatim, `holds =
  unresolved` in every environment — present, named, unevaluated. The set is catalog data
  (`conditions.other.annotations`: `@Conditional` and the eighteen autoconfigure conditions
  CP-43 row 5 enumerates). Measured: none of the 69 classes carries one of these on a
  controller.
* **Does not touch the bean fold** (`OI-108`). Same mechanism, next consumer; stated so the
  cell's closure is not read as the bean case's.
* **Does not infer the active profile from `spring.profiles.active`** when it is an
  expression (`${apollo_profile}`, as Apollo's is): the environments are the files that exist,
  which is what the config layer already resolves.

## 5. Performance

Linear in inbound rows; the annotation index is already built once per load for the body
rule and `protocol_hint`. No new query shape, no new table — `endpoint_metadata` and
`resolved_config` as they are.

## 6. Decisions, as ruled 2026-10-22

| # | decision | ruling |
|---|---|---|
| 1 | The condition is stated on the row, no row dropped or added | **agreed, with a correction**: the stored form must be STRUCTURED for a machine — a flat table (§2), not sentences in a metadata value; the architecture document is where the words go |
| 2 | How the system document treats a conditional inbound endpoint | **reframed by the user**: matching is about the endpoint — protocol, path, schema — never about implementation or reactor; the condition is a property of the inbound endpoint, travels with it as data, and the link states it. No environment-aware gate anywhere |

## 7. What it closes, predicted

COVERAGE's `conditional-controllers` row C → ✅ (Spring MVC 13/14 → 14/14), measured on
`fixtures/orders-service` (two controllers, one under `@Profile("ops")`, one under
`@ConditionalOnProperty(name = "orders.legacy", havingValue = "true")`, against the
fixture's `default`/`prod` environments) and on `apollo-configservice`'s `GET /` — "holds in
6 of 8, not in `default`, `github`". `OI-108` stays open with its closure named. Amendments:
D01 (`endpoint_conditions`, and the export map), D02 (`conditions`), the spring catalogs,
M06/M07 (a link states its inbound endpoint's conditions), COVERAGE, CHANGELOG.
