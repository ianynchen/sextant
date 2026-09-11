# W53 — does every exposed Spring Data repository serve a collection GET? (G-46)

**Question.** `spring-data-rest.yml`'s route table gave the collection `GET` **no
`needs:` at all**, and the file said why in so many words: *"the collection read is
the one route every exposed repository serves, whatever it extends."* Every other
route names the CRUD operation it requires; this one was unconditional.

That sentence came from CP-2, which is a live probe and a good one — but it
exercised `CrudRepository`, `JpaRepository` and `PagingAndSortingRepository`, and
**all three declare a `findAll`**. It never exercised a repository extending the
bare marker `Repository<T, ID>`. A rule read off the cases a probe happened to
cover is a prediction about the ones it did not (GUIDELINES §8.1), and the gap
analysis filed it as `G-46` with the right escalation attached: *"if the engine
really mints it this is a Critical, not a Major."*

**It mints it.** `derived_resource.py`'s route loop reads
`needed = route.get("needs")` and skips the filter entirely when that is `None`, so
a bare `interface Foo extends Repository<Foo, Long>` derived `GET /foos`.

**Version scope (§5.4).** Read against **spring-data-rest-core 5.0.1** — the
version CP-2's live application ran — and **spring-data-commons 3.2.5 and 4.0.1**,
the two the catalog already cites, plus **spring-data-jpa 4.1.1** for
`JpaRepository`. Which methods a framework exposes is framework behaviour and can
change between releases, which is why the contract table below is read at two
commons versions rather than one.

**Nothing wrong was ever published — and the reason is the gate, not the absence
of the shape.** The fixture's `OrderRepository` extends `com.acme.orders.data.Repository`,
its OWN stand-in, so that one never matched. But **`examples/spring-petclinic`'s
`VetRepository` extends Spring's real marker** (`vet/VetRepository.java:38`), as do
several repositories in `spring-petclinic-rest`. Those derived no wrong row for a
different reason: neither pom declares a Spring Data REST coordinate, and
`derived_resource` is in `DEPENDENCY_GATED`, so the catalog is SKIPPED on both. The
shape the defect needed is in this repository; only the gate kept it out of the
output. Stated this way because "the FQN occurs nowhere" was the first
explanation written here and it was wrong.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | the collection GET is added unconditionally | the catalog was right and this probe closes `G-46` as a non-defect |
| 2 | it is added behind a predicate | that predicate is the operation the route needs, and the catalog must name it |
| 3 | the predicate reduces to looking up a METHOD on the repository interface | a marker interface declaring none cannot satisfy it |
| 4 | a contract declares `findAll` only through a supertype | inheritance counts, because the lookup is `ReflectionUtils.findMethod` over the interface hierarchy |

## Observations

Verbatim from `scripts/probes/w53_data_rest_collection_read/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — read out of its own `pom.properties` or manifest, and
**not the version the coordinate list asked for**; `checked` compares the two
and ABORTS when they disagree, rather than printing a version it did not read.

| what the run read | 5.0.1 | 3.2.5 | 4.0.1 | 4.1.1 |
|---|---|---|---|---|
| artifact reporting this version | spring-data-rest-core | spring-data-commons | spring-data-commons | spring-data-jpa |
| where the jar states that version | pom.properties | pom.properties | pom.properties | pom.properties |

### 1. What decides a COLLECTION's methods

`CrudMethodsSupportedHttpMethods.getMethodsFor` adds `GET` and `HEAD` to a
collection **only behind `exposesFindAll()`** — the predicate is called, the result
is branched on, and only then are the methods added.

### 2. What the guard reduces to

| spring-data-commons | what `DefaultCrudMethods` looks up for the findAll slot |
|---|---|
| 3.2.5 | `findAll`, `Pageable`, `Sort` |
| 4.0.1 | `findAll`, `Pageable`, `Sort` |

### 3. Which contracts declare a `findAll`

| interface | declares `findAll` (3.2.5) | declares `findAll` (4.0.1) | methods it declares |
|---|---|---|---|
| `Repository` | **no** | **no** | 0 |
| `CrudRepository` | yes | yes | 12 |
| `ListCrudRepository` | yes | yes | 6 |
| `PagingAndSortingRepository` | yes | yes | 2 |
| `ListPagingAndSortingRepository` | yes | yes | 2 |
| `JpaRepository` *(one jar; spring-data-jpa 4.1.1)* | yes | yes | 14 |

**Verdict: CONFIRMED, and the catalog was wrong.** The collection `GET` is guarded
by `exposesFindAll()`, which resolves to a `findMethod` lookup for `findAll` — with
no arguments, and with `Pageable`/`Sort` — over the repository interface and
everything it extends. `Repository` declares **zero methods** at both commons
versions read, so a repository extending only it exposes `OPTIONS` on its
collection and nothing else. Every other contract the catalog enumerates declares
or inherits a `findAll`, which is why the missing `needs:` never showed up as a
wrong row on a real repository and why CP-2 could not have caught it.

`spring-data-rest.yml` now carries a `collection_read` operation: `Repository` has
none, the two paging contracts have exactly that one, and the three CRUD contracts
have it alongside `item_read`, `save` and `delete`.

## What this probe does NOT establish

It reads the class files, not a running application. It does not re-confirm CP-2's
live observations, and it does not answer what a bare `Repository` returns for
`OPTIONS` — only that `GET` is not among the methods assembled for it. A
`@RepositoryRestResource(exported = false)` still removes the repository entirely,
which is a different gate the catalog already reads and this probe did not touch.
