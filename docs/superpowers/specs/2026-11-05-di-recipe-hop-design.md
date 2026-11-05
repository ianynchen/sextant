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

Provider in another Gradle module; `Provider<T>`/`Lazy<T>`; `@BindsInstance`, component
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
