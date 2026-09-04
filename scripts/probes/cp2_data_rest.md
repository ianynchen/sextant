# CP-2 — Spring Data REST derivation (2O design §0a, §2)

**Questions.** (0) Which repositories does Spring Data REST expose, by what
DETECTION STRATEGY, and what does each setting do? (a) Is the collection path
the Evo Inflector pluralization of the uncapitalized entity simple name, and is
that conditional on `org.atteo:evo-inflector` being on the classpath? (b) How do
`path=`, `exported=false`, query methods and the extended CRUD interface shape
the route table?

**How it was run.** A minimal Boot 4.0.1 app (`spring-boot-starter-data-jpa` +
`spring-boot-starter-data-rest` + H2, resolved from Maven Central into `~/.m2`)
with one entity and one repository per row below, started on an embedded Tomcat
and interrogated with `GET /` (the HAL index — which repositories are exposed,
at which paths), `OPTIONS <route>` (the `Allow` header — which verbs each route
serves) and `GET /orders/search` (the search index). Versions observed:
`spring-data-rest-webmvc` 5.0.1, `spring-data-rest-core` 5.0.1,
`spring-hateoas` 3.0.1, `spring-data-commons` 4.0.1.

---

## (0) The detection strategy — the default, and every setting

Set with `spring.data.rest.detection-strategy`. Each row is the observed HAL
index of one run of the SAME app; the repositories are: five public and
un-annotated (`Order`, `Category`, `Box`, `Person`, `Sheep`), one public and
`@RepositoryRestResource(path = "gadgets")` (`Widget`), one public and
`@RepositoryRestResource(exported = false)` (`Secret`), one PACKAGE-PRIVATE and
un-annotated (`Hidden`).

| Setting | Observed exposed set | Rule it confirms |
|---|---|---|
| *(absent — the DEFAULT)* | orders, categories, boxes, persons, sheep, gadgets | every **public** repository, minus `exported = false` |
| `default` | identical to absent | `default` IS the default |
| `all` | the above **plus** secrets **plus** hiddens | every repository, ignoring visibility AND `exported` |
| `annotated` | gadgets only | only `@(Repository)RestResource`-annotated, minus `exported = false` |
| `visibility` | the default set **plus** secrets | every **public** repository, ignoring `exported` |

**Verdict: CONFIRMED, and §2's derivation is SOUND under the default** — an
un-annotated public repository IS exposed, which is the case §2 exists to
surface. Two consequences the spec did not state, both now derived from:

1. **Visibility is part of the default rule.** `HiddenRepository`, identical to
   the others but declared package-private, is exposed by NO strategy except
   `all`. A derivation that ignored the interface's own visibility would invent
   a whole API for every non-public repository in a module.
2. **One configuration line changes the answer**, and it is a key this analysis
   already reads (`resolved_config`). Under `annotated`, five of the six
   exposed collections above disappear.

## (a) Pluralization — the classpath condition, FALSIFIED as stated

The spec predicted two classpath states with two verdicts: pluralized WITH
`org.atteo:evo-inflector`, the bare uncapitalized simple name WITHOUT it.
Observed instead:

- **With the Data REST starter and nothing else declared, evo-inflector is
  ALREADY on the classpath**: `spring-data-rest-core` depends on
  `org.atteo:evo-inflector` at **compile scope, non-optional** (checked in the
  published POMs of 5.0.1, 4.2.7, 4.1.10 and 3.7.12 — the same in all four).
  `mvn dependency:tree` shows it arriving transitively with no declaration of
  its own. Paths observed: `/orders`, `/categories`, `/boxes`, `/persons`,
  `/sheep` — pluralized.
- **Removing the jar from the classpath does not fall back — the application
  fails**: `NoClassDefFoundError: org/atteo/evo/inflector/English`, thrown from
  `EvoInflectorLinkRelationProvider.getCollectionResourceRelFor` via
  `DelegatingLinkRelationProvider`, reached from
  `TypeBasedCollectionResourceMapping`. Spring HATEOAS's provider selection by
  classpath presence is real in general; for a Data REST application the
  optional half is unreachable, because Data REST's own dependency puts the jar
  there.

**Verdict: the two-state prediction is FALSIFIED for Spring Data REST.** A
working Data REST application always pluralizes. `domain/pluralize.py` is
therefore applied whenever the Data REST gate passes, not conditionally on a
second recorded coordinate — which is also the only sound reading under Maven,
where the recorded coordinates are the module's DIRECT declarations and a
transitive evo-inflector would never appear in them (deriving `/order` there
would be a fabricated path).

`persons`, not `people`: Evo Inflector has no `person`/`people` irregular. The
brief's illustrative test snippet asserted `people`; the library's own answer is
what this port pins.

### The pluralizer port, pinned against the library

`org.atteo:evo-inflector` 1.3 (the version `spring-data-rest-core` 5.0.1
resolves) was run over **every one of the 235,976 words in
`/usr/share/dict/words`**, and `sextant.domain.pluralize.pluralize` over the
same list: **0 mismatches**. Plus an edge list (empty string, `ORDER`, `CHILD`,
`Quiz`, `sheep`, `status`, `genus`, `mongoose`, `money`, `octopus`, `x`, `ss`,
`o`): 0 mismatches.

The expectation table committed as this checkpoint's own artifact —
`tests/domain/test_pluralize.py` — is a sample of that run, one word per rule
family, with the library's answer verbatim:

| word | Evo Inflector 1.3 |
|---|---|
| order | orders |
| category | categories |
| box | boxes |
| person | **persons** |
| child | children |
| sheep | sheep |
| man | men |
| mouse | mice |
| status | statuses |
| datum | data |
| medium | mediums |
| index | indexes |
| alumnus | alumni |
| genus | genera |
| quiz | quizzes |
| wolf | wolves |
| life | lives |
| roof | roofs |
| day | days |
| photo | photos |
| hero | heroes |
| piano | pianos |
| news | news |
| series | series |
| mongoose | mongoose |
| octopus | octopuses |
| ORDER | ORDERs |
| CHILD | Children |
| *(empty)* | *(empty)* |

**Reproduction.** `English.plural` over a word list, through a five-line Java
`main` on the 1.3 jar; the port through `sextant.domain.pluralize`. Neither the
harness nor the probe app is committed (the CP-1 precedent: scratch files, not
fixtures). No test in this repository requires either to run.

## (b) The route table

Observed `Allow` headers and search index, one run, default strategy:

| Repository (extends) | Route | Observed `Allow` |
|---|---|---|
| `OrderRepository` (`CrudRepository`) | `/orders` | HEAD, POST, **GET**, OPTIONS |
| | `/orders/{id}` | HEAD, **DELETE**, **GET**, OPTIONS, **PUT**, **PATCH** |
| `CategoryRepository` (`JpaRepository`) | `/categories` | HEAD, POST, GET, OPTIONS |
| | `/categories/{id}` | HEAD, DELETE, GET, OPTIONS, PUT, PATCH |
| `BoxRepository` (`PagingAndSortingRepository` ONLY) | `/boxes` | HEAD, **GET**, OPTIONS — **no POST** |
| | `/boxes/{id}` | **OPTIONS only** (GET → 405) |
| `WidgetRepository` (`path = "gadgets"`) | `/gadgets`, `/gadgets/{id}` | as `CrudRepository` above |
| `SecretRepository` (`exported = false`) | `/secrets` | **404 — no routes at all** |
| `HiddenRepository` (package-private) | `/hiddens` | **404 — no routes at all** |

Two further rows, added because §2a's derivation depends on both:

| Repository | Route | Observed |
|---|---|---|
| `OrderItemRepository` (entity `OrderItem`) | `/orderItems` | exposed — the simple name is **uncapitalized in its first character only**, then pluralized; never kebab- or snake-cased |
| `NoteRepository extends BaseRepository<Note, Long>`, where `@NoRepositoryBean BaseRepository<T, ID> extends CrudRepository<T, ID>` | `/notes`, `/notes/{id}` | exposed, with the FULL CrudRepository verb set — the within-module closure walk §2a describes is real, and the entity is the type argument the repository's OWN hop names |

Search routes (`GET /orders/search`):

| Query method | Observed route |
|---|---|
| `findByStatus` | `/orders/search/findByStatus` |
| `@RestResource(path = "by-id-greater-than") findByIdGreaterThan` | `/orders/search/by-id-greater-than` |
| `@RestResource(exported = false) findByIdLessThan` | **absent** |

**Verdict: CONFIRMED.** `path=` overrides; `exported=false` removes the whole
repository; query methods surface under `/search/` and honour `@RestResource`'s
`path`/`exported`; and item routes DO honour which CRUD interface is extended —
since Spring Data 3, `PagingAndSortingRepository` no longer extends
`CrudRepository`, so a repository extending only it serves a collection GET and
**nothing else**, not even an item GET.

A repository that declares no query method has **no `/search` index at all**
(`GET /persons/search` → 404), and a repository whose only declared method
OVERRIDES a CRUD-interface method is the same case: `BoxRepository` declares
`Page<Box> findAll(Pageable)` and `GET /boxes/search` → **404**. So a declared
method is a search route only when it is not one of the CRUD interfaces' own
method names — which is why the derivation carries that name list as catalog
data rather than treating every declared method as a query.

Two observations recorded but NOT derived from, so that a later reader does not
mistake omission for absence: Data REST also serves `HEAD` and `OPTIONS` on
every exposed route, and a `/{basePath}/search` index route. §2b's table names
neither, and this task derives exactly that table.
