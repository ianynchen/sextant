# W19b — the three slices that are not about methods (F2 §3.8: G-47, G-45, G-41)

Run: `scripts/probes/w19b_type_and_annotation_surface/run.sh`. Everything below the
rule is that script's own output, pasted verbatim.

**Version scope (§5.4).** Read against **spring-integration-core 6.2.4**,
**spring-data-commons 3.2.5**, **spring-data-jpa 3.2.5**, **spring-data-mongodb
4.2.5**, **spring-data-r2dbc 3.2.5**, **spring-data-cassandra 4.2.5**,
**spring-data-elasticsearch 5.2.5**, **spring-data-neo4j 7.2.5** and **graphql-dgs
8.7.1** — each self-reported by the archive, from `Implementation-Version:` or Maven's
`pom.properties`, and the run ABORTS when a jar's self-report disagrees with the
coordinate that resolved it. An artifact that does not resolve is REPORTED rather than
skipped, because a short list of gaps and an absence of gaps look identical.

## Why a second probe

`w19_catalog_surface` asked one question: *of the methods this framework declares on
this owner, how many does the catalog read?* Three of §3.8's six slices do not have
that shape, and answering them from that table would be the "counted the wrong set"
error this wave keeps producing — the same one that made the first probe report
`SqsTemplate` as having no unread addressable methods.

- **G-47** is about ANNOTATIONS in a package.
- **G-45** is about repository CONTRACTS across seven artifacts.
- **G-41** is about one annotation's own meta-annotations, and turns out not to be a
  set at all.

## What each one found

**G-47 — `spring-integration` reads 7 of the 11 channel-declaring annotations
(re-measured 2026-09-12 after `G-47`/`G-45` shipped).**
Measured from each annotation's own declared attributes rather than from a list: an
annotation counts as channel-declaring when the framework NAMED an attribute for a
channel (`inputChannel`, `outputChannel`, `channel`, `discardChannel`,
`requestChannel`, `replyChannel`, `defaultRequestChannel`, `defaultReplyChannel`).
`@Aggregator`, `@Filter`, `@Router`, `@Splitter` and `@Transformer` are read since
`G-47` shipped; `@Gateway`, `@MessagingGateway`, `@Poller` and `@Publisher` are the
four still unread.

*The attribute list was written out by hand first and missed `errorChannel`, which
removed `@Poller` from the table, the count and the slice together; it also missed
`channelMappings`, which hid a whole routing table on `@Router`. The rule is now "any
attribute whose name contains channel", measured rather than listed — the same error
this probe's own docstring says it exists to avoid, committed twice by the probe.* Two more — `@BridgeFrom` and
`@BridgeTo` — carry their channel in a bare `value()`, which the attribute-name test
cannot see; they are reported separately rather than folded in, because *the framework
named this attribute a channel* is a measurement and *this `value()` means a channel*
is a reading of the annotation's name. That makes thirteen. The gap analysis estimated "~12", and the difference is
`@Poller`, which no hand-written list contained.

The cost here is bounded and worth stating plainly: this catalog mints no endpoint
rows, it files `channel_destination` questions. So four unread annotations are an
under-reported QUESTION list, not four wrong rows.

**G-45 — `spring-data-rest`'s roster names 7 of the 28 repository contracts
(re-measured 2026-09-12 after `G-47`/`G-45` shipped).**
Every store module ships its own: `MongoRepository`, `R2dbcRepository`,
`CassandraRepository`, `ElasticsearchRepository`, `Neo4jRepository`, their reactive
twins, plus the coroutine and RxJava3 contracts in `spring-data-commons` itself. The
roster names `MongoRepository` since `G-45` shipped, beside `JpaRepository` and five
base contracts; a repository interface extending any of the other 21 derives NOTHING,
because the roster is the whole rule — this style's evidence mentions no HTTP
anywhere, so what turns an interface into an API is exactly the contract it extends.

**G-41 — the recorded mechanism does not exist, and the real one now does.** The gap
analysis says `@DgsData` and `@DgsQuery` are `@Inherited`. All five are, measured — and
on four of them that bit is INERT, because `java.lang.annotation.Inherited` "has no
effect if the annotated type is used to annotate anything other than a class" and those
four declare `@Target(METHOD)`. The outcome the gap analysis claimed is nonetheless
true, by a mechanism nobody had measured: DGS registers fetchers through
`ReflectionUtils.getUniqueDeclaredMethods`, whose `doWithMethods` walks
`getSuperclass()` and `getInterfaces()` — so a fetcher on a superclass method registers
on every subclass bean. That is `OI-67`, and the fix is a superclass METHOD walk rather
than the `@Inherited` resolution the first draft named. The catalog already names all
five annotations, so nothing is unread. The gap is a USE SITE we cannot see: an `@Inherited`
annotation on a superclass method registers a fetcher the subclass never declares, and
this analysis reads annotations where they are written. `slice.outside` means "names
this catalog does not read", and forcing a use-site gap into it would make the key mean
two different things — so G-41 is stated in `netflix-dgs.yml` and in COVERAGE, and is
deliberately absent from section 4's table.

---

## Observations

Generated by `scripts/probes/w19b_type_and_annotation_surface/run.sh` — every cell below is that run's own output, and this document pastes it verbatim.

**Each column header is the version the JAR ITSELF reported**, read out of its own `META-INF/MANIFEST.MF` or Maven `pom.properties` — not the version the loop asked for, which is only the path this machine cached the artifact at. The run ABORTS when the two disagree.

### 1. G-47 — channel-declaring annotations (`spring-integration`)

Cells are the channel-naming attributes the annotation declares, under the version that reported them.

| annotation | 6.2.4 | read by the catalog |
|---|---|---|
| `Aggregator` | `discardChannel`, `inputChannel`, `outputChannel` | yes |
| `Filter` | `discardChannel`, `inputChannel`, `outputChannel` | yes |
| `Gateway` | `replyChannel`, `requestChannel` | **NO** |
| `InboundChannelAdapter` | `channel` | yes |
| `MessagingGateway` | `defaultReplyChannel`, `defaultRequestChannel`, `errorChannel` | **NO** |
| `Poller` | `errorChannel` | **NO** |
| `Publisher` | `channel` | **NO** |
| `Router` | `channelMappings`, `defaultOutputChannel`, `inputChannel` | yes |
| `ServiceActivator` | `inputChannel`, `outputChannel` | yes |
| `Splitter` | `inputChannel`, `outputChannel` | yes |
| `Transformer` | `inputChannel`, `outputChannel` | yes |

- **7 of 11** channel-declaring annotations are read; 4 are not.
- The package holds 34 annotations in total (of 35 classes — the difference is `AnnotationConstants`, a plain final class); the rest declare no channel attribute.
- Invisible to the attribute-name test, and carrying a channel in a bare `value()`: `BridgeFrom`, `BridgeTo`. Counted separately because 'the framework named this attribute a channel' is a measurement and 'this `value()` means a channel' is a reading of the name.

### 2. G-45 — repository contracts (`spring-data-rest`)

| artifact | version | repository contracts it ships | named by the roster |
|---|---|---|---|
| `org.springframework.data:spring-data-commons` | 3.2.5 | 12 | **5** |
| | | `RevisionRepository` | **NO** |
| | | `CoroutineCrudRepository` | **NO** |
| | | `CoroutineSortingRepository` | **NO** |
| | | `ReactiveCrudRepository` | **NO** |
| | | `ReactiveSortingRepository` | **NO** |
| | | `RxJava3CrudRepository` | **NO** |
| | | `RxJava3SortingRepository` | **NO** |
| `org.springframework.data:spring-data-mongodb` | 4.2.5 | 2 | **1** |
| | | `ReactiveMongoRepository` | **NO** |
| `org.springframework.data:spring-data-r2dbc` | 3.2.5 | 1 | **0** |
| | | `R2dbcRepository` | **NO** |
| `org.springframework.data:spring-data-cassandra` | 4.2.5 | 3 | **0** |
| | | `CassandraRepository` | **NO** |
| | | `MapIdCassandraRepository` | **NO** |
| | | `ReactiveCassandraRepository` | **NO** |
| `org.springframework.data:spring-data-elasticsearch` | 5.2.5 | 3 | **0** |
| | | `CoroutineElasticsearchRepository` | **NO** |
| | | `ElasticsearchRepository` | **NO** |
| | | `ReactiveElasticsearchRepository` | **NO** |
| `org.springframework.data:spring-data-neo4j` | 7.2.5 | 2 | **0** |
| | | `Neo4jRepository` | **NO** |
| | | `ReactiveNeo4jRepository` | **NO** |
| `org.springframework.data:spring-data-jpa` | 3.2.5 | 1 | **1** |
| `org.springframework.data:spring-data-keyvalue` | 3.2.5 | 1 | **0** |
| | | `KeyValueRepository` | **NO** |
| `org.springframework.data:spring-data-redis` | 3.2.5 | 0 | **0** |
| `org.springframework.data:spring-data-ldap` | 3.2.5 | 1 | **0** |
| | | `LdapRepository` | **NO** |
| `org.springframework.data:spring-data-couchbase` | 5.2.5 | 2 | **0** |
| | | `CouchbaseRepository` | **NO** |
| | | `ReactiveCouchbaseRepository` | **NO** |
| `org.springframework.data:spring-data-rest-core` | 4.2.5 | 0 | **0** |

### 3. G-41 — is `@DgsData` inherited? (`netflix-dgs`)

| annotation | 8.7.1 `@Inherited` |
|---|---|
| `DgsData` | **yes** |
| `DgsQuery` | **yes** |
| `DgsMutation` | **yes** |
| `DgsSubscription` | **yes** |
| `DgsComponent` | **yes** |

- All five carry `@Inherited` — three more than the gap analysis recorded. **And on four of them that bit is INERT.** `java.lang.annotation.Inherited` "has no effect if the annotated type is used to annotate anything other than a class", and it inherits from superclasses, never through methods; `@DgsData`, `@DgsQuery`, `@DgsMutation` and `@DgsSubscription` all declare `@Target(METHOD)`. So this table measures a real bit that does not do the job it was cited for.

- **The outcome it was cited for is nonetheless true, by a different and now measured mechanism.** `DgsSchemaProvider$Companion$DgsBean` calls `ReflectionUtils.getUniqueDeclaredMethods(clazz, USER_DECLARED_METHODS)`, and `ReflectionUtils.doWithMethods` calls `Class.getSuperclass()` and `Class.getInterfaces()` (`javap -c`, spring-core 6.1.6) — so DGS enumerates the whole hierarchy's methods. A fetcher on a superclass method registers on every subclass bean, and we read annotations only where they are written. The fix is a superclass METHOD walk, not `@Inherited` resolution.

### 4. Every unread name, one per row

Prose is what a reader needs and a table is what a test can hold to; this is the second. `tests/architecture/test_catalog_slice_coverage.py` requires every row here to be named in its catalog's `slice.outside`, the same way it does for the method table `w19_catalog_surface.md` emits.

| catalog | kind | container | name |
|---|---|---|---|
| `spring-integration` | `annotation` | `org.springframework.integration.annotation` | `Gateway` |
| `spring-integration` | `annotation` | `org.springframework.integration.annotation` | `MessagingGateway` |
| `spring-integration` | `annotation` | `org.springframework.integration.annotation` | `Poller` |
| `spring-integration` | `annotation` | `org.springframework.integration.annotation` | `Publisher` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `RevisionRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `CoroutineCrudRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `CoroutineSortingRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `ReactiveCrudRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `ReactiveSortingRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `RxJava3CrudRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-commons` | `RxJava3SortingRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-mongodb` | `ReactiveMongoRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-r2dbc` | `R2dbcRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-cassandra` | `CassandraRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-cassandra` | `MapIdCassandraRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-cassandra` | `ReactiveCassandraRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-elasticsearch` | `CoroutineElasticsearchRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-elasticsearch` | `ElasticsearchRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-elasticsearch` | `ReactiveElasticsearchRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-neo4j` | `Neo4jRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-neo4j` | `ReactiveNeo4jRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-keyvalue` | `KeyValueRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-ldap` | `LdapRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-couchbase` | `CouchbaseRepository` |
| `spring-data-rest` | `type` | `org.springframework.data:spring-data-couchbase` | `ReactiveCouchbaseRepository` |

**G-41 is deliberately absent from this table.** `netflix-dgs`'s gap is not a set of names the catalog fails to read — it names all five annotations. It is a USE SITE we cannot see: an `@Inherited` annotation on a superclass method registers a fetcher the subclass never declares, and this analysis reads annotations where they are written. `slice.outside`'s vocabulary is "names this catalog does not read", and forcing a use-site gap into it would make the key mean two different things. It is stated in the catalog and in COVERAGE instead.
