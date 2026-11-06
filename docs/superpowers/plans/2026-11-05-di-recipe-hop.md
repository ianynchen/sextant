# Container recipe hop (OI-304) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A parameter the DI container fills receives the value of the recipe the container
chooses, so Retrofit made through Hilt/Dagger `@Provides` gets its server address.

**Architecture:** bean models become estate-wide inputs to the shared value walk; `beans.py` gains
Dagger's exact-key matching beside Spring's ladder; `values._parameter` consults an `injected`
table before callers.

**Tech Stack:** Python resolve layer, YAML bean models, a Kotlin + Dagger Gradle/Maven fixture (JDK 21).

**Spec:** `docs/superpowers/specs/2026-11-05-di-recipe-hop-design.md` (approved).

## Global Constraints

- Fixtures built with JDK 21 only (`JAVA_HOME=/opt/homebrew/opt/openjdk@21`, first on PATH).
- A wrong value is a lie: ambiguous/none → `unresolved` with its reason, never a guess.
- Mirror Dagger exactly (spec §2a); Spring keeps its ladder (§2b).
- Only the approved words (spec §2c); no fact or graph schema change.
- Every row that changes on any fixture or the six field pins (`scripts/field_check.py`) is listed and judged true.
- ASD-STE-100 comments; GUIDELINES §1–4, §13.5; guards per `scripts/guard_check.py`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Two providers of one type, unqualified → ambiguous, partial (Task 2 test).
2. Qualifier with attributes (`@Named("a")` vs `@Named("b")`) → each its own (Task 2).
3. A Spring module whose `@Bean` parameters now cross: rows that change (Task 3 measurement).
4. A recipe whose own parameter is container-filled (two hops) → resolved through both (Task 3).
5. A provider in another module → `none`, partial with reason (Task 4 fixture).

---

### Task 1: Bean-model words and the Dagger model

**Files:** `src/sextant/catalogs/bean-models/dagger.yml` (new), `spring.yml` (`injection: candidates`),
`src/sextant/ingress/catalogs/yaml_source.py` (load checks), `docs/components/D02-catalog-schema.md` §1c/§1f.

**Produces:** a loader that reads every bean model estate-wide (one function returning all models
by id), validating `injection` ∈ {`exact_key`, `candidates`}, `multibinding_annotations`,
`injecting_annotations`, and requiring the ladder keys only for `candidates`.

- [ ] Tests: `dagger.yml` loads; an unknown `injection` value is refused; `candidates` without
  `qualifier_annotation` is refused; `exact_key` without it is accepted.
- [ ] Implement; covering tests; commit.

### Task 2: Exact-key matching in `beans.py`

**Files:** `src/sextant/application/resolve/beans.py`; tests under `tests/application/`.

**Produces:** `injected_parameters(workspace, models) -> Mapping[(method, index), Injection]` where
`Injection` is `resolved(provider_method)` | `ambiguous(candidates)` | `none(reason)`, catalog-free,
built once per resolve (`workspace.once`), covering `@Provides`/`@Bean` method parameters and
`injecting_annotations` constructors; Dagger key = (qualifier identity with attributes, full type);
qualifier-ness from `qualifier_meta_annotations` (reuse the dispatch reader's rule, including
`type_header` for library annotation types); multibinding providers excluded; Spring through the
existing ladder.

- [ ] Tests: unqualified unique → resolved; two unqualified → ambiguous; `@Named("a")` vs `("b")`;
  custom qualifier; generic type `List<String>` vs `List<Int>` distinct; `@IntoSet` provider not a
  candidate; `@Inject` constructor parameter; Spring ladder unchanged.
- [ ] Implement; covering tests; commit.

### Task 3: The hop in the shared value walk

**Files:** `src/sextant/application/resolve/values.py` (`_parameter`, the index); tests.

**Produces:** `_parameter` consults `injected` before `callers`: resolved → a path step and the
provider's returned values in the provider's context; ambiguous/none → `unresolved` with reason.
Recursion bounded by the trail.

- [ ] Tests: `made_by` reads `baseUrl` through a `@Provides` parameter (one hop, two hops, a
  qualified base `String`); ambiguous → partial "server address not read".
- [ ] Measure: all fixtures row diff before/after and `scripts/field_check.py`; list every changed
  row with a true/false judgement (Spring `@Bean` parameters now cross).
- [ ] Implement; full gate; commit.

### Task 4: Dagger fixture, end to end, documents

**Files:** a new fixture (Kotlin + Dagger, kapt or KSP, JDK 21) under `fixtures/`; e2e test; COVERAGE
(Retrofit under DI), CHANGELOG, D02, M04 if it lists value-walk hops; `docs/open-issues.md` id rows
for anything logged.

- [ ] Fixture shapes: Kotlin `object` module, `class` module, Java static `@Provides`; `@Named`,
  custom qualifier, qualified base `String`, `@Inject` constructor making the client; a duplicate
  binding; a provider in another module (partial). E2e pins every Retrofit row's address/status.
- [ ] CI priming/build as other fixtures are built; full gate; field pins; commit.
