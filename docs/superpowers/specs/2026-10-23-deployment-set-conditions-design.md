# What a deployment can set, the repository does not decide — design

**Status: BUILT 2026-10-23 (branch `fix/deployment-set-conditions`) — three rulings made (§1); the decision in §6 ruled A (bump).** Settles the
three rulings `conditional-beans` (PR #63) left open. It changes what already-shipped
documents say, so it comes before new coverage. It moves no COVERAGE cell: it corrects
verdicts the conditional-controllers and conditional-beans work publishes. §2 carries the
before and after measured on four corpora; §8 records what building it settled.

**The general concept.** Some inputs that decide whether a bean exists are set at deployment:
- active profiles;
- properties, which a Helm chart, a ConfigMap, an environment variable or a command-line
  argument can each override.

The repository's files state a default for these, never the production value. A claim about
the RUNNING system that rests on such an input ("this endpoint does not exist in `prod`") is
therefore never decided from the repository. A statement about what the REPOSITORY configures
("its `prod` file sets `billing.url` to `https://billing.internal`") stays a fact, labelled as
one.

---

## 1. The rulings (2026-10-23)

| # | Question | Ruling | The user's reason |
|---|---|---|---|
| 1 | In a profile environment `p`, what is a profile the module never names? | **C, extended to `default`, then widened to (b):** every EXISTENCE verdict resting on something a deployment can set is "not evaluated" — profile AND property conditions, in every environment `default` included. The repository's value is stated as evidence. Resolved values are untouched | "what we are ultimately interested in, is what's in production and this can be set anywhere, helm charts, configmaps etc. there's no way we can tell until deployment is known, which is not part of sextant's job for now" |
| 2 | Does the boundary vocabulary's `dependency` kind carry `conditions`? | **A:** yes; `BOUNDARY_VOCABULARY_VERSION` 1 → 2 | Conditions belong to beans (PR #63), so every row a bean produces carries them, in either direction |
| 3 | What does the diff compare for conditions? | **C:** the declared expressions `(kind, expression)` only. Per-environment verdicts are evidence | A configuration change is reported once, as the `boundary-property` change it is; a code change as a `conditions` change |

Rejected, for the record:
- for 1: A (unnamed profiles are "off"), B (open only where the base file sets
  `spring.profiles.active`), scope (a) profiles only — a special case of the same rule —
  and scope (c) values too, which would undo value resolution;
- for 2: B (leave the dependency kind as it is);
- for 3: A (keep per-environment verdicts) and B (compare `bean_presence`).

## 2. Measured first, then again after building

Read-only over every analysed workspace under `examples/` holding `bean_conditions`.
Before = measured before building (2026-10-23); after = the same counts from the four
corpora re-analysed with the built change (`JAVA_HOME=…openjdk@21 sextant module analyze`).
"Decided" is `holds in ('true','false')`; everything else is `unresolved`.

The harness query, run per workspace (`<dir>/.sextant/workspace.duckdb`, opened read-only):

```sql
select kind, holds, count(*) from bean_conditions group by 1, 2 order by 1, 2;
select holds, count(*) from bean_presence group by 1 order by 1;
```

| module | decided condition verdicts, before → after | `bean_presence` decided, before → after |
|---|---|---|
| `apollo-portal` | profile: 0 → 0 (its 414 were already open: `${apollo_profile}`); property: 240 (84 `false`, 156 `true`) → 0, all 240 now `unresolved` | 222 of 714 → 18 of 714 (all `true`) |
| `spring-petclinic-rest` | profile: 77 (70 `false`, 7 `true`) → 0 of 105; property: 40 (20 / 20) → 0 of 40 | 117 of 145 → 0 of 145 |
| `jhipster-sample-app` | profile: 4 → 0 of 6; property: 1 → 0 of 1 | 4 of 6 → 0 of 6 |
| `mall-admin` | none → none (its 12 `presence`-kind rows are decided by code, `true`) | 12 of 12 → 12 of 12, unchanged |

Totals: decided profile and property verdicts 362 → 0; decided `bean_presence` rows 355 → 30.

What is decided after the change:
- a `presence` verdict whose inputs are decided by code (an unconditional competitor, or none):
  `mall-admin`'s 12; `apollo-portal`'s 18 presence rows (its `presence`-kind condition rows: 96 `true`,
  222 `unresolved`);
- in profile environment `p`, a profile term naming `p` itself. None of the four corpora has
  one: no bean's `@Profile` names a profile whose file the module ships, so the "after"
  figure for profile verdicts is 0, and this rule is pinned on hand-built rows only.

## 3. What changes

### 3a. Which condition kinds a deployment can set — catalog data

Framework knowledge is data (D02), so the bean model states it per condition kind rather
than the pass knowing Spring's precedence rules:

```yaml
# catalogs/bean-models/spring.yml
conditions:
  profile:  { annotation: …Profile, expressions: value, set_by: deployment,
              by: scripts/probes/cp42_profile_condition.md }
  property: { annotation: …ConditionalOnProperty, …, set_by: deployment,
              by: scripts/probes/cp43_on_property_condition.md }
  other:    { … }        # unchanged: named, never evaluated
presence:   { … }        # unchanged: decided by what the code registers
```

`set_by: deployment` is backed by a probe, **CP-47** (`scripts/probes/cp47_deployment_overrides.md`).
It measures, on spring-boot 4.1.1, Spring Boot's externalised-configuration order:
- an OS environment variable (`SPRING_PROFILES_ACTIVE=jdbc`, `BILLING_ENABLED=true`) and a
  command-line argument each override `application.properties` and a profile file;
- relaxed binding maps `BILLING_ENABLED` to `billing.enabled`;
- a profile-specific file cannot set `spring.profiles.active`, so the deployment, not the
  repository, selects the profile file (CP-45 row 7).

### 3b. Evaluation

For a condition whose kind is `set_by: deployment`, the verdict is `unresolved` unless the
environment's own definition decides it:
- in profile environment `p`, a `profile` term naming `p` holds, and `!p` fails;
- nothing decides anything in `default` (ruled), not even the reserved `default` profile,
  which Spring activates only when the deployment activates none.

The repository's own reading is kept as evidence, in the `evidence` column:
- **profile:** the profiles the module itself activates, expanded through its groups —
  `active profiles are set by the deployment; this module's own default is
  `h2,spring-data-jpa``. Where the module names none: `… this module activates none`.
- **property:** the value the environment's file resolves, and what it would decide —
  `` `billing.enabled` is set by the deployment; this module's `prod` file sets `false` ``
  (or `sets nothing`).

`active_profiles` (CP-45) is unchanged: it now produces evidence, not verdicts. The
placeholder reason (`${apollo_profile}`, which this module does not fill) stays the evidence
where it applies. `presence` evaluation is unchanged: it already propagates `unresolved` from
the beans it depends on.

### 3c. What the documents say

The environments line (spec 2026-10-22 §3) keeps its shape. Almost every conditional bean
now reads:

```text
JdbcOwnerRepositoryImpl — not evaluated in any of the 5 environments:
  active profiles are set by the deployment; this module's own default is `h2,spring-data-jpa`
```

A bean decided by its environment's own name still reads decided:

```text
H2ConsoleConfig (@Profile("h2")) — exists in `h2`; not evaluated in `default`, `hsqldb`, `mysql`, `postgres`
```

The system document's per-link conditions read the same verdicts.

### 3d. The boundary vocabulary, version 2

```diff
 dependency  identity: protocol, method, path, peer
-            attributes: request_body, response_body, request_shape, response_shape, format, headers, resolution
+            attributes: request_body, response_body, request_shape, response_shape, format, headers, conditions, resolution
```

The rows already exist: `endpoint_conditions` is a view over rows of both directions since
graph schema 4 (an outbound row's code is its `caller`). `BOUNDARY_VOCABULARY_VERSION` 1 → 2,
with its comment-table row in `domain/version.py`. A diff across vocabulary versions is
refused, as `_VERSIONS` already does.

### 3e. What the diff compares

For `endpoint` and `dependency`, the `conditions` attribute is the set of
`{kind, expression}` the code declares. The per-environment `environment`/`holds` entries
leave the diffed attribute; they stay in the workspace, the bundle and the documents.

```text
code adds @ConditionalOnProperty("billing.enabled")   → endpoint changed: conditions
prod file flips billing.enabled                       → boundary-property changed (only)
```

## 4. What it does NOT do

- **Values are unaffected:** `resolved_config`, peers, paths and the system tier's links keep
  being read per environment from the repository (ruling 1, scope b).
- **The environment LIST is unchanged:** environments are still the profile files the module
  ships, so `OI-168` stays open.
- **`other` conditions** (`@ConditionalOnClass`, `@ConditionalOnExpression`, …) stay named and
  unevaluated, as before.
- **No deployment input is read.** Helm charts, ConfigMaps and manifests are not Sextant's job
  for now (ruling 1).

## 5. Cost (§8.7)

No new reads. The pass already reads every input. `active_profiles` and the property lookup
now write evidence strings where they wrote verdicts. The diff reads the same view, with
fewer columns.

## 6. Decision for the user — RULED A (bump), 2026-10-23

**Does the graph schema move 5 → 6?** No table changes, but every verdict changes. D01 §7:
"a mismatch never produces a mixed-vintage graph". Without a bump, a workspace analysed today
at schema 5 keeps its old decided verdicts and is read without complaint, beside new ones.
`SEXTANT_VERSION` is gated until the Spring Boot milestone, so the graph schema is the only stamp
that can force re-derivation.
- **Recommendation: bump.** PR #64 made every workspace re-analyse today, and nothing has
  been released since, so the second bump costs one more `module analyze`.
- **The alternative:** document that pre-change workspaces keep old verdicts until
  re-analysed. It is cheaper, but a document rendered from such a workspace states decided
  answers this design says the repository cannot give.

## 7. Verify what it closes (before planning)

Pinned tests this design changes on purpose, each to be re-pinned with its new expectation,
never deleted:
- `tests/e2e/test_system_document.py::test_a_link_to_a_conditional_endpoint_states_where_the_endpoint_exists`
  ("exists in `prod`; not in `default`" → `prod` decided by its own name; `default` not evaluated);
- `::test_a_link_from_a_conditional_caller_states_where_the_call_exists`;
- the conditional-beans and conditional-controllers e2e and unit pins on decided `false`/`true`;
- the diff's condition-set tests.

Field pins (`scripts/field_check.py`) read contract fields, not conditions; run them anyway.

## 8. As built

The rulings made while building, each with its pin:
- **One module-level profile reason.** A deployment-set profile's evidence is one string per
  module, the same in every environment: the module's own activation as read for its base
  environment (`h2,spring-data-jpa`, "this module activates none", or the placeholder
  reason). It is computed once and passed down, not rebuilt per environment.
- **The reserved `default` profile is no activation.** When the base environment holds
  `default` only because the module names no profile (CP-45 row 5), the evidence reads "this
  module activates none".
- **A quoted configured value is masked by its key.** A property's evidence quotes the value
  the environment's file resolves, so it is masked by that key where it is written, as every
  origin of a configured value is.
- **The diff masks a condition expression as the exporter does.** The exporter masked it; the
  diff compared and printed it verbatim, so a `havingValue` URL carrying a password made a
  workspace and its own bundle differ and printed the credential. Found by review of §3e's
  change; closed in the same branch.

The loader refuses a `set_by` other than `deployment`, and a `set_by` with no `set_by_probe`.
`by:` keeps naming the evaluation-rule probe; the new key `set_by_probe:` names CP-47.
