# W58 — the annotation surface nine Micronaut and Quarkus catalogs are written against

**Question.** `micronaut-http.yml`, `micronaut-http-client.yml`, `micronaut-kafka.yml`,
`micronaut-kafka-client.yml`, `micronaut-jms.yml`, `micronaut-jms-producer.yml`,
`micronaut-pubsub.yml`, `micronaut-pubsub-client.yml` and `quarkus-reactive-routes.yml`
are all `annotation_driven`, and that style fails **silently** on a wrong FQN or a wrong
attribute name: the annotation never matches, or the attribute is never present, and the
catalog derives nothing while looking healthy (W53's finding, `G-91`). So: does every FQN
the nine name exist at the coordinate the catalog gates on, does every attribute they read
exist under that name, is `@Route`'s `@Repeatable` container the type the catalog names,
and do the three messaging pairs' `request_body.annotation` name the annotation the
framework's own body binder keys on?

**Version scope (§5.4).** Read against **micronaut-http 4.7.6, micronaut-http-client-core
4.7.6, micronaut-kafka 5.6.0, micronaut-jms-core 4.2.0, micronaut-gcp-pubsub 5.8.0,
quarkus-reactive-routes 3.17.5 and quarkus-reactive-routes-deployment 3.17.5** — each the
version the jar reports for itself, checked against the coordinate before any table is
printed. Attribute names are API surface and move between majors; these versions and no
other are what the nine catalogs claim. The fixture poms `fixtures/orders-micronaut/pom.xml`
and `fixtures/orders-quarkus/pom.xml` pin the same versions.

**How to run.** `bash scripts/probes/w58_micronaut_quarkus_annotations/run.sh`. Resolves
each artifact through Maven (network on the first run only), reads the version the jar
states for itself, and asks `javap` for each annotation's declared attributes. Everything
below the rule is that script's own output, pasted verbatim.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | every named annotation exists and every attribute read is declared | the nine catalogs are measured at these versions |
| 2 | an attribute is **ABSENT** on some annotation | that annotation carries no such value and the catalog's read of it is inert there — a stated boundary if the catalog's comment claims otherwise |
| 3 | `@Repeatable` names a type other than `Route$Routes` | two `@Route` on one handler derive nothing; the `container:` is wrong |
| 4 | a body binder references no `io.micronaut.messaging.annotation.*` type | the `request_body.annotation` is a guess and must be removed |

## What was found

* **Rows 33-34, 39, 43-44:** `@Head` and `@Trace` declare neither `consumes` nor
  `produces`; `@Options` declares `consumes` only. Both Micronaut HTTP catalogs claimed
  every verb annotation carried both — corrected in place to say which do.
* **Rows 45-46:** `@Client` declares `value` and `path` only, no media — so no class-level
  media applies on the client side, and the client catalog now says so.
* **The container is `Route$Routes`**, as declared. **`Route$HttpMethod` has six members
  and no `PATCH`** — the fixture's first draft used it and did not compile.
* **All three body binders key on `MessageBody`**, one annotation for three integrations.

---

## Observations

Verbatim from `scripts/probes/w58_micronaut_quarkus_annotations/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties` or its manifest's
`Implementation-Version`, and **not the version the coordinate list asked for**;
`checked` compares the two and ABORTS when they disagree.

| what the run read | 4.7.6 | 5.6.0 | 4.2.0 | 5.8.0 | 3.17.5 |
|---|---|---|---|---|---|
| artifacts reporting this version | micronaut-http, micronaut-http-client-core | micronaut-kafka | micronaut-jms-core | micronaut-gcp-pubsub | quarkus-reactive-routes, quarkus-reactive-routes-deployment |
| where the jar states it | MANIFEST.MF | MANIFEST.MF | MANIFEST.MF | MANIFEST.MF | pom.properties |

### Every annotation the nine catalogs name, and every attribute they read

| # | coordinate | annotation | catalog(s) | attribute the catalog reads | declared as |
|---|---|---|---|---|---|
| 1 | `micronaut-http` | `io.micronaut.http.annotation.Controller` | micronaut-http | `value` | `java.lang.String` |
| 2 | `micronaut-http` | `io.micronaut.http.annotation.Controller` | micronaut-http | `consumes` | `java.lang.String[]` |
| 3 | `micronaut-http` | `io.micronaut.http.annotation.Controller` | micronaut-http | `produces` | `java.lang.String[]` |
| 4 | `micronaut-http` | `io.micronaut.http.annotation.Body` | micronaut-http | *(gate only)* | exists, 1 attribute(s) |
| 5 | `micronaut-http` | `io.micronaut.http.annotation.Get` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 6 | `micronaut-http` | `io.micronaut.http.annotation.Get` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 7 | `micronaut-http` | `io.micronaut.http.annotation.Get` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 8 | `micronaut-http` | `io.micronaut.http.annotation.Get` | micronaut-http, micronaut-http-client | `consumes` | `java.lang.String[]` |
| 9 | `micronaut-http` | `io.micronaut.http.annotation.Get` | micronaut-http, micronaut-http-client | `produces` | `java.lang.String[]` |
| 10 | `micronaut-http` | `io.micronaut.http.annotation.Post` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 11 | `micronaut-http` | `io.micronaut.http.annotation.Post` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 12 | `micronaut-http` | `io.micronaut.http.annotation.Post` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 13 | `micronaut-http` | `io.micronaut.http.annotation.Post` | micronaut-http, micronaut-http-client | `consumes` | `java.lang.String[]` |
| 14 | `micronaut-http` | `io.micronaut.http.annotation.Post` | micronaut-http, micronaut-http-client | `produces` | `java.lang.String[]` |
| 15 | `micronaut-http` | `io.micronaut.http.annotation.Put` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 16 | `micronaut-http` | `io.micronaut.http.annotation.Put` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 17 | `micronaut-http` | `io.micronaut.http.annotation.Put` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 18 | `micronaut-http` | `io.micronaut.http.annotation.Put` | micronaut-http, micronaut-http-client | `consumes` | `java.lang.String[]` |
| 19 | `micronaut-http` | `io.micronaut.http.annotation.Put` | micronaut-http, micronaut-http-client | `produces` | `java.lang.String[]` |
| 20 | `micronaut-http` | `io.micronaut.http.annotation.Delete` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 21 | `micronaut-http` | `io.micronaut.http.annotation.Delete` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 22 | `micronaut-http` | `io.micronaut.http.annotation.Delete` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 23 | `micronaut-http` | `io.micronaut.http.annotation.Delete` | micronaut-http, micronaut-http-client | `consumes` | `java.lang.String[]` |
| 24 | `micronaut-http` | `io.micronaut.http.annotation.Delete` | micronaut-http, micronaut-http-client | `produces` | `java.lang.String[]` |
| 25 | `micronaut-http` | `io.micronaut.http.annotation.Patch` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 26 | `micronaut-http` | `io.micronaut.http.annotation.Patch` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 27 | `micronaut-http` | `io.micronaut.http.annotation.Patch` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 28 | `micronaut-http` | `io.micronaut.http.annotation.Patch` | micronaut-http, micronaut-http-client | `consumes` | `java.lang.String[]` |
| 29 | `micronaut-http` | `io.micronaut.http.annotation.Patch` | micronaut-http, micronaut-http-client | `produces` | `java.lang.String[]` |
| 30 | `micronaut-http` | `io.micronaut.http.annotation.Head` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 31 | `micronaut-http` | `io.micronaut.http.annotation.Head` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 32 | `micronaut-http` | `io.micronaut.http.annotation.Head` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 33 | `micronaut-http` | `io.micronaut.http.annotation.Head` | micronaut-http, micronaut-http-client | `consumes` | **ABSENT** |
| 34 | `micronaut-http` | `io.micronaut.http.annotation.Head` | micronaut-http, micronaut-http-client | `produces` | **ABSENT** |
| 35 | `micronaut-http` | `io.micronaut.http.annotation.Options` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 36 | `micronaut-http` | `io.micronaut.http.annotation.Options` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 37 | `micronaut-http` | `io.micronaut.http.annotation.Options` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 38 | `micronaut-http` | `io.micronaut.http.annotation.Options` | micronaut-http, micronaut-http-client | `consumes` | `java.lang.String[]` |
| 39 | `micronaut-http` | `io.micronaut.http.annotation.Options` | micronaut-http, micronaut-http-client | `produces` | **ABSENT** |
| 40 | `micronaut-http` | `io.micronaut.http.annotation.Trace` | micronaut-http, micronaut-http-client | `value` | `java.lang.String` |
| 41 | `micronaut-http` | `io.micronaut.http.annotation.Trace` | micronaut-http, micronaut-http-client | `uri` | `java.lang.String` |
| 42 | `micronaut-http` | `io.micronaut.http.annotation.Trace` | micronaut-http, micronaut-http-client | `uris` | `java.lang.String[]` |
| 43 | `micronaut-http` | `io.micronaut.http.annotation.Trace` | micronaut-http, micronaut-http-client | `consumes` | **ABSENT** |
| 44 | `micronaut-http` | `io.micronaut.http.annotation.Trace` | micronaut-http, micronaut-http-client | `produces` | **ABSENT** |
| 45 | `micronaut-http-client-core` | `io.micronaut.http.client.annotation.Client` | micronaut-http-client | `value` | `java.lang.String` |
| 46 | `micronaut-http-client-core` | `io.micronaut.http.client.annotation.Client` | micronaut-http-client | `path` | `java.lang.String` |
| 47 | `micronaut-kafka` | `io.micronaut.configuration.kafka.annotation.KafkaListener` | micronaut-kafka | *(gate only)* | exists, 19 attribute(s) |
| 48 | `micronaut-kafka` | `io.micronaut.configuration.kafka.annotation.KafkaClient` | micronaut-kafka-client | *(gate only)* | exists, 9 attribute(s) |
| 49 | `micronaut-kafka` | `io.micronaut.configuration.kafka.annotation.Topic` | micronaut-kafka, micronaut-kafka-client | `value` | `java.lang.String[]` |
| 50 | `micronaut-kafka` | `io.micronaut.configuration.kafka.annotation.Topic` | micronaut-kafka, micronaut-kafka-client | `patterns` | `java.lang.String[]` |
| 51 | `micronaut-jms-core` | `io.micronaut.jms.annotations.JMSListener` | micronaut-jms | *(gate only)* | exists, 1 attribute(s) |
| 52 | `micronaut-jms-core` | `io.micronaut.jms.annotations.JMSProducer` | micronaut-jms-producer | *(gate only)* | exists, 1 attribute(s) |
| 53 | `micronaut-jms-core` | `io.micronaut.jms.annotations.Queue` | micronaut-jms, micronaut-jms-producer | `value` | `java.lang.String` |
| 54 | `micronaut-jms-core` | `io.micronaut.jms.annotations.Topic` | micronaut-jms, micronaut-jms-producer | `value` | `java.lang.String` |
| 55 | `micronaut-gcp-pubsub` | `io.micronaut.gcp.pubsub.annotation.PubSubListener` | micronaut-pubsub | *(gate only)* | exists, 0 attribute(s) |
| 56 | `micronaut-gcp-pubsub` | `io.micronaut.gcp.pubsub.annotation.PubSubClient` | micronaut-pubsub-client | *(gate only)* | exists, 1 attribute(s) |
| 57 | `micronaut-gcp-pubsub` | `io.micronaut.gcp.pubsub.annotation.Subscription` | micronaut-pubsub | `value` | `java.lang.String` |
| 58 | `micronaut-gcp-pubsub` | `io.micronaut.gcp.pubsub.annotation.Topic` | micronaut-pubsub-client | `value` | `java.lang.String` |
| 59 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.Route` | quarkus-reactive-routes | `path` | `java.lang.String` |
| 60 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.Route` | quarkus-reactive-routes | `methods` | `io.quarkus.vertx.web.Route$HttpMethod[]` |
| 61 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.Route` | quarkus-reactive-routes | `consumes` | `java.lang.String[]` |
| 62 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.Route` | quarkus-reactive-routes | `produces` | `java.lang.String[]` |
| 63 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.Route$Routes` | quarkus-reactive-routes | `value` | `io.quarkus.vertx.web.Route[]` |
| 64 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.RouteBase` | quarkus-reactive-routes | `path` | `java.lang.String` |
| 65 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.RouteBase` | quarkus-reactive-routes | `consumes` | `java.lang.String[]` |
| 66 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.RouteBase` | quarkus-reactive-routes | `produces` | `java.lang.String[]` |
| 67 | `quarkus-reactive-routes` | `io.quarkus.vertx.web.Body` | quarkus-reactive-routes | *(gate only)* | exists, 0 attribute(s) |

### `@Route`'s repeatable container

`@Repeatable` on `io.quarkus.vertx.web.Route` names **`io.quarkus.vertx.web.Route$Routes`**; the catalog
declares `container: io.quarkus.vertx.web.Route$Routes`.

### `Route$HttpMethod`, the closed verb set `all_methods` lists

`GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `OPTIONS`

### The three message-body binders, and the annotation each keys on

| coordinate | binder | `io.micronaut.messaging.annotation.*` it references |
|---|---|---|
| `micronaut-kafka` | `KafkaMessagingBodyBinder` | MessageBody |
| `micronaut-jms-core` | `DefaultBodyArgumentBinder` | MessageBody |
| `micronaut-gcp-pubsub` | `PubSubBodyBinder` | MessageBody |

### Path composition, in the deployment processor

`ReactiveRoutesProcessor` calls `dashify(String)` on `MethodInfo.name()` **2**
time(s) — the absent-`path` form serves the method name dashed, which no
`path_fallback` word says, so the catalog derives that form as nothing rather than
as `/helloWorld`. The bytecode around each call appends `"/"` between the base
path and the route path, and prepends `"/"` to a route path that lacks one.
