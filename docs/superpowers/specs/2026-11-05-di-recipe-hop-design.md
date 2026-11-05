# A container-filled parameter receives what the container's recipe makes — design

**Status: APPROVED 2026-11-05 (user: "A, approve").** Plane OI-304 = SEXTANT-298. Branch
`cov/hilt-provides`, cut from `cov/android-outbound` (PR #93), which it needs (`made_by`).
Investigation with all measurements: `.superpowers/sdd/2026-11-05-android-outbound/oi-304-investigation.md`.

## 1. The gap

Real Android apps let Hilt/Dagger make their clients:

```kotlin
@Provides fun retrofit(): Retrofit = Retrofit.Builder().baseUrl(API_URL).build()
@Provides fun api(retrofit: Retrofit): OrdersApi = retrofit.create(OrdersApi::class.java)
```

The value walk (`values._Walk._parameter`) answers a parameter with no in-module caller as
`external`. The only callers of `api(retrofit)` are Dagger's generated factories, so `made_by`
reads no base and every such Retrofit row is `partial` ("server address not read"). Measured on a
scratch Hilt build: 4 of 4 rows partial. Corpus: NotyKT (8 Retrofit rows; needs a JDK 17
toolchain, not installed — so this design is checked on fixtures only, stated).

## 2. Design (option A, approved)

**One rule in the shared value walk: a parameter the container fills receives the value of the one
recipe (provider method) the container chooses for it, by that container's own rules.**

- The value index gains `injected[(method, index)]` → the provider method, built once per resolve
  from **every** bean model in `catalogs/bean-models/` (estate-wide, like `value-models/`, D02 §1f).
- `_parameter` consults it **before** `callers`: a resolved entry adds a path step and resolves the
  provider's returned values in the provider's own context (no frame). The provider's own
  parameters are container-filled again — a further hop, bounded by the walk's trail.
- An `ambiguous` or `none` entry answers `unresolved` with its reason: the row stays `partial`,
  never a guess. Generated factory code is not followed (option B, rejected: a parser of one
  library's runtime).

### 2a. Dagger mirrored exactly (framework-behavior-mirroring)

- Key = (qualifier annotation with all its attributes, full type including type arguments).
  A qualifier is any annotation whose type carries `javax.inject.Qualifier` or
  `jakarta.inject.Qualifier` (the existing `qualifier_meta_annotations`, read for a library type
  through `type_header` as the dispatch reader does).
- Unqualified matches unqualified only. No name rung, no primary.
- Multibinding contributions (`@IntoSet`, `@IntoMap`, `@ElementsIntoSet`) are never a candidate
  for `T`.
- Dagger's DuplicateBindings/MissingBinding make the key unique per component; Sextant sees the
  whole module, so it resolves only a key unique module-wide; several → `ambiguous`, none → `none`.
- `@Inject` constructors: their parameters are container-filled too.

### 2b. Spring

Spring `@Bean` parameters cross through the existing ladder (qualifier, the only bean of the type,
`@Primary`, name). This moves Spring results in every value reader, so every changed row on the
fixtures and the six field pins is judged true/false before it ships. Spring constructor
injection is not built (logged).

### 2c. Approved catalog words (user, 2026-11-05)

1. `catalogs/bean-models/dagger.yml` — `declaring_annotation: dagger.Provides`,
   `qualifier_meta_annotations`, plus the new keys below.
2. `injection: exact_key | candidates` — how a container matches a parameter to a recipe:
   Dagger's exact (qualifier, type) key, or Spring's ladder. `spring.yml` declares `candidates`;
   its ladder keys (`qualifier_annotation`, `name_attrs`, `primary_annotation`) are required only
   for `candidates`.
3. `multibinding_annotations` — recipes that add to a collection, never a candidate for `T`.
4. `injecting_annotations` — annotations marking a constructor whose parameters the container fills
   (`javax.inject.Inject`, `jakarta.inject.Inject`).
5. D02 §1c: bean models are read estate-wide by the value walk (a module's container, not a
   catalog's choice).

## 3. Not in this design (each stays partial with its reason; logged)

A provider in a jar the analysis does not scan (not a reactor sibling, not opted in; a sibling
the module depends on IS scanned and its recipes are read, see §5); `Provider<T>`/`Lazy<T>`; `@BindsInstance`, component
dependencies, `@Binds` (abstract), field/member injection; Spring constructor injection; Koin
(a lookup call, not a filled parameter; 0 corpus builds need it); the argument hop OI-306 still
needs for `@HttpExchange`; Metro (a second bean-model file later).

## 4. Done when

- A Kotlin + Dagger fixture (JDK 21; kapt or KSP): Kotlin `object`, `class` and Java static modules;
  `@Named`, a custom qualifier, a qualified base `String`, an `@Inject` constructor; a duplicate
  binding and a cross-module provider giving `partial`. Its Retrofit rows are resolved with the
  right address; the e2e test pins them.
- Every changed row on all fixtures and the six field pins judged true; gate green.
- D02 §1c/§1f, COVERAGE (Retrofit under DI), CHANGELOG. NotyKT stated unverified (no JDK 17).

## 5. As built

Tasks 1–4, branch `cov/hilt-provides` (9cd89f2e, bab3160d, b6911ba4, then Task 4).

- **Words** as approved (§2c): `catalogs/bean-models/dagger.yml`, `injection`,
  `multibinding_annotations`, `injecting_annotations`. `injection` is required on a model that
  declares `declaring_annotation`; `exact_key` also requires `qualifier_meta_annotations`.
  `Catalog.bean_models` (every model, by id) and `Catalog.value_annotations` (the union of the
  catalogs' `value_annotation`s) are port fields derived at load; no YAML word beyond §2c.
- **The table** `beans.injected_parameters` → `ProvidedBy | Ambiguous | NotProvided`, once per
  load. A slot that carries a configuration annotation (`@Value`) has no entry, for every model.
  Under `candidates`, a slot whose type has type arguments has no entry. A Kotlin `@JvmStatic`
  companion recipe and its static forwarder are one recipe (measured: Dagger 2.57.2 calls the
  forwarder).
- **The hop** in `values._parameter`: the frame, then `stop_at_parameters_of`, then the table,
  then callers. `ProvidedBy` resolves each return of the recipe in its own body (step
  `<recipe> returns <n>`). `Ambiguous` answers `unresolved`, reason `non_enumerable` (the
  existing word: several values the walk does not choose between). `NotProvided` or no entry
  reads as before.
- **Spring ladder (Task 4, review m3):** the qualifier and name rungs of a non-channel reference
  choose only among the beans of the parameter's type or a subtype of it
  (`dispatch.ancestry_of`), as `determineAutowireCandidate` does.
- **Fixture:** `fixtures/orders-dagger` (Maven, Kotlin 2.4.20 with kapt, Dagger 2.57.2, Retrofit
  2.11.0, JDK 21; plain Dagger `@Component`s, and Hilt's `@InstallIn` modules were measured on the
  Task 3 kapt probe). The
  unscanned-jar recipe is in the library `fixtures/orders-dagger-network` (Java, installed by
  `tests/fixture_stub.py`). `tests/e2e/test_dagger_recipes.py` pins its eight Retrofit rows: six
  resolved, `region` (two recipes of one key) and `shared` (recipe in the library) partial.
- **Measured:** see the Task 4 report (`.superpowers/sdd/2026-11-05-di-recipe-hop/task-4-report.md`).
- **Not verified:** NotyKT (needs a JDK 17 toolchain).
- **Reactor siblings (whole-branch review I1):** the detectors scan a reactor sibling the module
  depends on as a library root (Maven W24, Gradle W55), so its `@Provides` methods are in the
  workspace and are read as recipes, and a key's uniqueness is decided over the module and those
  siblings together. `fixtures/orders-dagger-reactor` pins it: a sibling's recipe resolves the
  row, and one key with a recipe in the sibling and one in the app stays `partial`.
- **Ladder (whole-branch review m1, m3, m4; scoped re-review I-1, m-a, m-c, m-d):**
  `beans.TypeLattice` answers assignable, not assignable, or unread (a type on the walk whose
  supertypes were not read). Not assignable also where no unread type can reach the parameter's
  type: it is the module's own or a sibling's, or it was read on a classpath the build tool
  resolved (a type with no header is then the platform's). A lone unread candidate answers
  `unread` (`unread_type` in the table). The type, qualifier and
  name rungs weigh the beans of the type or a subtype; the qualifier rung keeps an unread one,
  the type and name rungs choose only a known one. `Unresolved` carries the beans an ambiguous
  rung weighed, which `Ambiguous` reports (one encoding of the ladder).
- **Unread qualifier (m2):** an annotation whose type was not read, with no read qualifier
  beside it, makes the slot (or every unqualified slot of a recipe's type) `unread_type`.
- **Logged:** OI-315 (recipe in a jar the analysis does not scan, `Provider<T>`/`Lazy<T>`, `@Binds`, field injection),
  OI-316 (qualifier defaults, wildcard variance, primitive and boxed), OI-317 (Spring constructor
  injection), OI-318 (Koin, Metro), OI-319 (an unreachable difference between the recipe step
  and the caller loop).
