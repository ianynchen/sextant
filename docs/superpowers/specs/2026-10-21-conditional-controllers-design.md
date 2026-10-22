# A controller that exists in one environment only — design

**Status: PROPOSAL. Two decisions in §6 need the user's ruling before Task 1** (GUIDELINES
§1.1). Nothing here amends `docs/components/*`; §7 lists what would.

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

## 2. What the row should say

The condition is a FACT about the row, not a decision about it. The document states it in
the endpoint's detail block, in words a reader can act on:

```
- `GET /` — `HomePageController#listAllServices`
  - Exists only when the active profile is one of: `kubernetes`, `nacos-discovery`,
    `consul-discovery`, `zookeeper-discovery`, `custom-defined-discovery`, `database-discovery`.
    Of this module's environments: holds in 6 of 8 — not in `default`, `github`.
```

Two halves, and the second is what makes the first useful: the condition as the code
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
through the existing `conditions.py::annotation_index` (one decode per load), and write one
`endpoint_metadata` row per condition: `kind: condition`, `name: profile | property`,
`value`: the condition as spelled (`kubernetes | nacos-discovery | …`, or
`apollo.feature.x = true`), `resolution: resolved`, `evidence: compiler`. Then the
evaluation, per environment the module resolved: `profile` — the environment's name is in
the set (or not in the negated set); `property` — the key's `resolved_config` value in that
environment against `havingValue`/`matchIfMissing`. The per-environment verdict is written
as a second metadata row, `kind: condition_holds`, `name: <environment>`, `value: true |
false | unresolved`. A `property` condition whose key is ABSENT in an environment is decided
by `matchIfMissing` (that is the framework's own rule, CP-43); one whose key resolves to a
placeholder nobody filled (`${…}` with no value in any source) is `unresolved` there —
stated, not guessed.

Cost (§8.7): one read of `endpoints`, one `annotation_index` lookup per inbound handler
type, one `resolved_config` read per `property` condition per environment; nothing per
catalog.

### 3c. The document

The detail block gains the two lines of §2. The inbound table's columns are unchanged: a
condition is a fact about where the row exists, not a sixth column every unconditional row
would carry empty. The system document (`system analyze --environment X`) is NOT changed
here — §6, decision 2.

## 4. What it does NOT do

* **Does not drop a row** anywhere, in any environment. Stated, not decided (B5).
* **Does not read `@Conditional(SomeClass.class)`**, `@ConditionalOnBean`,
  `@ConditionalOnExpression`, or a custom condition: each is code, not configuration, and
  publishing a verdict would be guessing. A row carrying one gets a `condition` row with
  `value: <the annotation, verbatim>` and `condition_holds` rows `unresolved` — present,
  named, unevaluated. Measured: none of the 69 classes carries one of these on a controller.
* **Does not touch the bean fold** (`OI-108`). Same mechanism, next consumer; stated so the
  cell's closure is not read as the bean case's.
* **Does not infer the active profile from `spring.profiles.active`** when it is an
  expression (`${apollo_profile}`, as Apollo's is): the environments are the files that exist,
  which is what the config layer already resolves.

## 5. Performance

Linear in inbound rows; the annotation index is already built once per load for the body
rule and `protocol_hint`. No new query shape, no new table — `endpoint_metadata` and
`resolved_config` as they are.

## 6. Decisions for the user

| # | decision | recommendation |
|---|---|---|
| 1 | The condition is stated on the row as `endpoint_metadata` (`condition`, and one `condition_holds` per environment), rendered as §2's two lines; no row is dropped or added | yes — B5 as ruled, and the per-environment verdict is exact for `@Profile` by Spring's own filename rule |
| 2 | `system analyze --environment X` leaves rows whose condition is false in `X` in the system document, marked (not dropped) | yes for now — the linking tier compares addresses, and a route absent in `X` should still not be matched there; that gate is one line in `links.py` once the metadata exists, and I would rather measure first on a reactor that has a conditional row (none of the pinned ones does) |

## 7. What it closes, predicted

COVERAGE's `conditional-controllers` row C → ✅ (Spring MVC 13/14 → 14/14), measured on
`fixtures/orders-service` (two controllers, one under `@Profile("ops")`, one under
`@ConditionalOnProperty(name = "orders.legacy", havingValue = "true")`, against the
fixture's `default`/`prod` environments) and on `apollo-configservice`'s `GET /` — "holds in
6 of 8, not in `default`, `github`". `OI-108` stays open with its closure named. Amendments:
D01 (`endpoint_metadata` kinds), D02 (`conditions`), M03 none, the spring catalogs, COVERAGE,
CHANGELOG.
