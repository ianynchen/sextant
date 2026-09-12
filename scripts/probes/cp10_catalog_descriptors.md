# CP-10 — every catalog `descriptor:`, against the bytecode it claims (descriptor sweep, R7)

**Question.** A `methods` row may pin itself to one overload by declaring that
overload's erased JVM `descriptor`, compared verbatim against a call site's own
`target.descriptor`. Load-time validation checks only that the value is a string
opening with `(`. So: **does every descriptor a shipped catalog declares name a
method the framework's own bytecode actually declares, at that name, on that
owner or a supertype of it?**

The question is worth a probe because of the failure mode, not the likelihood. A
descriptor with a wrong return type, a misspelled package or a stale erasure is
*well-formed and wrong*: it passes validation, it CLAIMS its candidate set in
`_matching_method` — every row sharing the name that admits this argument count
— and every overload of that name then derives **nothing at all**. No error, no
`docs/COVERAGE.md` row, and every test asserting absence still passes. Twenty-
three rows gained a descriptor in one sweep; a check that each opens with `(`
would have waved all twenty-three through.

**Version scope (§5.4).** Read against **google-cloud-pubsub 1.129.3,
jakarta.jms-api 3.1.0, javax.jms-api 2.0.1, spring-cloud-aws-sqs 3.1.1, spring-kafka 3.1.4,
spring-rabbit 3.1.4, kafka-clients 3.6.2, kafka-streams 3.6.2, spring-ws-core 4.1.4,
spring-cloud-gcp-pubsub 5.1.2, spring-jms 6.1.6, spring-messaging 6.1.6,
spring-web 6.1.6, spring-websocket 6.1.6, jakarta.websocket-client-api 2.2.0,
jakarta.websocket-api 2.1.1, javalin 6.4.0 and pekko-connectors-kafka_2.13 1.1.0**
(`pekko-connectors-kafka_2.13` added 2026-09-12 for `alpakka-pekko`, w62 — it writes
no `pom.properties` (a Scala/sbt-built artifact, not `mvn`-built) but does write a
manifest `Implementation-Version:`, measured with `unzip -l`; `javalin` added
2026-09-12 for
`javalin-routing`, w61 — it writes BOTH a `pom.properties` and a manifest
`Implementation-Version:`, measured with `unzip -l` rather than assumed, and
`pom.properties` is read first; `kafka-streams` added 2026-09-12 for `G-31`, w60 —
its own version file at `kafka/kafka-streams-version.properties`, a different path
than the raw client's `kafka/kafka-version.properties`, measured with `unzip -l`
rather than assumed from the sibling artifact; before that, the last added was
2026-09-11 for row 189, `G-34`, opened with
`javap -s` rather than assumed from the client-api sibling). `javax.jms-api 2.0.1` is the LAST release under that
coordinate — the line does not ship again — so it is the only version a Spring Boot 2
codebase can be on, and W12's `javax-jms.yml` is measured against it here rather than
being trusted as `jakarta-jms.yml` with the package swapped. A descriptor is
version-scoped in the strongest sense:
an overload added or a parameter re-typed in a later release is a different
answer, and every verdict below is evidence about those seventeen artifacts and no
other. Widening it means adding a coordinate to `ARTIFACTS` in
`scripts/probes/cp10_catalog_descriptors/run.sh` and re-running, never assuming.

Ten of the twelve are the versions a fixture pom already pins. **Two are not, and
each says why rather than being carried silently.** `spring-websocket` 6.1.6 is what
`fixtures/orders-service/pom.xml` declares directly, and has since W16 — *this paragraph
called it "a stated assumption rather than a measurement: no fixture, and no pom anywhere in
this repository, depends on it at all", which stopped being true then. The version is right
and the reason given for it was not*, and if a WebSocket fixture is ever built at a different
Spring version that row is re-measured rather than carried over. `javax.jms-api
2.0.1` is not a choice at all: it is the last release under that coordinate, so
there is no other version for a row to be measured at.

**How to run.** `bash scripts/probes/cp10_catalog_descriptors/run.sh`. It
resolves each artifact above through Maven (network on the first run only,
cached in `~/.m2` afterwards), reads every `descriptor:` out of
`src/sextant/catalogs/*.yml`, indexes class → jar off the archives it opened,
and asks `javap -p -s` for the descriptors the owner declares — walking BOTH
superclasses and interfaces while they are on the same classpath, because
`SqsTemplate.send(String, T)` is declared on `AbstractMessagingTemplate` and a
walk blind to inheritance would report a real descriptor as missing. **The
interface half was added 2026-09-12 for `javalin-routing` (w61):**
`io.javalin.Javalin implements JavalinDefaultRoutingApi<Javalin>` and never
redeclares `get`/`post`/etc — they exist only as `default` methods on the
interface — so a superclass-only walk reported all fourteen of `javalin.yml`'s
`Javalin`-owned rows `NOT DECLARED` even though every call `Javalin.create().
get(…)` compiles and runs; walking `implements` the same way
`w19_catalog_surface/sweep.py`'s own `declared_methods` already does closed it,
for every existing catalog and this one alike (measured: zero rows for any
other catalog changed verdict). **`pekko-connectors-kafka.yml` (`alpakka-pekko`,
w62) needed no further harness change**: its owner, `org.apache.pekko.kafka.
javadsl.Consumer`, is a `final class` that declares its five matched methods
directly rather than through an interface, so the existing `implements`-walk
covers it with no new gap — all five new rows came back `declared`, and adding
its artifact changed the verdict of zero other rows. It ends by printing the
two tables below — **only the tables**, not this surrounding prose, which is
why they are fenced between `<!-- table:start -->`/`<!-- table:end -->`
markers rather than trusted to end where the last committed table happened to
end: `descriptors.py` has no notion of this file's own sections, so a
regeneration that pastes over "the rest of the file" rather than between the
markers silently deletes everything below them (found on review after `alpakka-
pekko` landed — the Verdict section, its numbered notes and the two closing
sections were dropped from the committed file for one commit; restored here,
verbatim, from the commit before that fix). Needs
a JDK and Maven. Not a test: nothing in the suite runs it, and NFR-1's no-network
rule governs the suite rather than evidence gathering.

`tests/architecture/test_catalog_descriptors.py` is the offline half. It pins
the shipped catalogs against the table below in both directions and fails on any
row whose verdict is not `declared`, so a descriptor added without re-running
this harness fails the suite rather than going quiet.

## Expectation table

| # | Under test | Expected |
|---|---|---|
| 1 | every `descriptor:` in every shipped catalog | named by `javap -p -s` on the owner or a supertype (superclass or interface) |
| 2 | the jar each owner was resolved out of | the artifact the run opened, not one mapped by hand |
| 3 | the version filed against each row | what that jar reports about itself |
| 4 | a descriptor the jar does not declare | reported `NOT DECLARED`, and fatal to the suite |

## Observations

Verbatim from `run.sh`'s generated tables. **Every column header of the first
table is a version the JAR itself reported** — out of Maven's `pom.properties`,
the manifest's `Implementation-Version`, or Kafka's own
`kafka-version.properties`, whichever that artifact writes — and
**not the version the coordinate list asked for**.
`descriptors.py` reads the value out of
the archive it opened and ABORTS the whole run when it disagrees with the
coordinate that resolved the jar, rather than filling a mislabelled column; that
is CP-5's failure, which printed a version it believed beside output from a
version it had not run. The second table's `artifact` column is likewise the jar
the run found the owner class in, discovered by indexing the archives rather than
by a hand-written owner→artifact map.

<!-- table:start -->
| what the run read | 1.1.0 | 1.129.3 | 2.0.1 | 2.1.1 | 2.2.0 | 3.1.0 | 3.1.1 | 3.1.4 | 3.6.2 | 4.1.4 | 5.1.2 | 6.1.6 | 6.4.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| artifacts reporting this version | pekko-connectors-kafka_2.13 | google-cloud-pubsub | javax.jms-api | jakarta.websocket-api | jakarta.websocket-client-api | jakarta.jms-api | spring-cloud-aws-sqs | spring-amqp, spring-kafka, spring-rabbit | kafka-clients, kafka-streams | spring-ws-core | spring-cloud-gcp-pubsub | spring-jms, spring-messaging, spring-web, spring-websocket | javalin |
| owner classes resolved out of them | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 5 | 7 | 1 | 1 | 10 | 3 |
| catalog descriptors checked against them | 5 | 1 | 12 | 1 | 4 | 12 | 8 | 48 | 33 | 3 | 12 | 104 | 42 |
| of those, NOT declared by the jar | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| # | catalog | owner | method | arity | descriptor | artifact | version | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | `google-pubsub-client` | `com.google.cloud.pubsub.v1.Publisher` | `publish` | 1 | `(Lcom/google/pubsub/v1/PubsubMessage;)Lcom/google/api/core/ApiFuture;` | `google-cloud-pubsub` | 1.129.3 | declared |
| 2 | `jakarta-jms` | `jakarta.jms.Session` | `createProducer` | 1 | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 3 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 1 | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 4 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 5 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 3 | `(Ljakarta/jms/Destination;Ljava/lang/String;Z)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 6 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedConsumer` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 7 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedConsumer` | 3 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 8 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableSubscriber` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/TopicSubscriber;` | `jakarta.jms-api` | 3.1.0 | declared |
| 9 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableSubscriber` | 4 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljakarta/jms/TopicSubscriber;` | `jakarta.jms-api` | 3.1.0 | declared |
| 10 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableConsumer` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 11 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableConsumer` | 4 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 12 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedDurableConsumer` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 13 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedDurableConsumer` | 3 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 14 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 2 | `(Ljava/lang/Object;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 15 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 2 | `(Ljava/lang/Class;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 16 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 3 | `(Ljakarta/websocket/Endpoint;Ljakarta/websocket/ClientEndpointConfig;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 17 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 3 | `(Ljava/lang/Class;Ljakarta/websocket/ClientEndpointConfig;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 18 | `jakarta-websocket-programmatic` | `jakarta.websocket.server.ServerEndpointConfig$Builder` | `create` | 2 | `(Ljava/lang/Class;Ljava/lang/String;)Ljakarta/websocket/server/ServerEndpointConfig$Builder;` | `jakarta.websocket-api` | 2.1.1 | declared |
| 19 | `javalin` | `io.javalin.Javalin` | `get` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 20 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `get` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 21 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `get` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 22 | `javalin` | `io.javalin.Javalin` | `get` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 23 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `get` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 24 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `get` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 25 | `javalin` | `io.javalin.Javalin` | `post` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 26 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `post` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 27 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `post` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 28 | `javalin` | `io.javalin.Javalin` | `post` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 29 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `post` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 30 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `post` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 31 | `javalin` | `io.javalin.Javalin` | `put` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 32 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `put` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 33 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `put` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 34 | `javalin` | `io.javalin.Javalin` | `put` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 35 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `put` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 36 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `put` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 37 | `javalin` | `io.javalin.Javalin` | `delete` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 38 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `delete` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 39 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `delete` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 40 | `javalin` | `io.javalin.Javalin` | `delete` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 41 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `delete` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 42 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `delete` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 43 | `javalin` | `io.javalin.Javalin` | `patch` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 44 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `patch` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 45 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `patch` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 46 | `javalin` | `io.javalin.Javalin` | `patch` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 47 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `patch` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 48 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `patch` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 49 | `javalin` | `io.javalin.Javalin` | `head` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 50 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `head` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 51 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `head` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 52 | `javalin` | `io.javalin.Javalin` | `head` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 53 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `head` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 54 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `head` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 55 | `javalin` | `io.javalin.Javalin` | `options` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 56 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `options` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 57 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `options` | 2 | `(Ljava/lang/String;Lio/javalin/http/Handler;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 58 | `javalin` | `io.javalin.Javalin` | `options` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 59 | `javalin` | `io.javalin.router.JavalinDefaultRoutingApi` | `options` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 60 | `javalin` | `io.javalin.router.JavalinDefaultRouting` | `options` | 3 | `(Ljava/lang/String;Lio/javalin/http/Handler;[Lio/javalin/security/RouteRole;)Lio/javalin/router/RoutingApi;` | `javalin` | 6.4.0 | declared |
| 61 | `javax-jms` | `javax.jms.Session` | `createProducer` | 1 | `(Ljavax/jms/Destination;)Ljavax/jms/MessageProducer;` | `javax.jms-api` | 2.0.1 | declared |
| 62 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 1 | `(Ljavax/jms/Destination;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 63 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 2 | `(Ljavax/jms/Destination;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 64 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 3 | `(Ljavax/jms/Destination;Ljava/lang/String;Z)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 65 | `javax-jms` | `javax.jms.Session` | `createSharedConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 66 | `javax-jms` | `javax.jms.Session` | `createSharedConsumer` | 3 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 67 | `javax-jms` | `javax.jms.Session` | `createDurableSubscriber` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/TopicSubscriber;` | `javax.jms-api` | 2.0.1 | declared |
| 68 | `javax-jms` | `javax.jms.Session` | `createDurableSubscriber` | 4 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljavax/jms/TopicSubscriber;` | `javax.jms-api` | 2.0.1 | declared |
| 69 | `javax-jms` | `javax.jms.Session` | `createDurableConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 70 | `javax-jms` | `javax.jms.Session` | `createDurableConsumer` | 4 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 71 | `javax-jms` | `javax.jms.Session` | `createSharedDurableConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 72 | `javax-jms` | `javax.jms.Session` | `createSharedDurableConsumer` | 3 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 73 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 74 | `kafka-clients` | `org.apache.kafka.clients.producer.Producer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 75 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 2 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;Lorg/apache/kafka/clients/producer/Callback;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 76 | `kafka-clients` | `org.apache.kafka.clients.producer.Producer` | `send` | 2 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;Lorg/apache/kafka/clients/producer/Callback;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 77 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 78 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 79 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 80 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 81 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 82 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 83 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 84 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 85 | `kafka-streams-sink` | `org.apache.kafka.streams.kstream.KStream` | `to` | 1 | `(Ljava/lang/String;)V` | `kafka-streams` | 3.6.2 | declared |
| 86 | `kafka-streams-sink` | `org.apache.kafka.streams.kstream.KStream` | `to` | 2 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Produced;)V` | `kafka-streams` | 3.6.2 | declared |
| 87 | `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `addSink` | 3 | `(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | `kafka-streams` | 3.6.2 | declared |
| 88 | `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `addSource` | 2 | `(Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | `kafka-streams` | 3.6.2 | declared |
| 89 | `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `addSource` | 3 | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | `kafka-streams` | 3.6.2 | declared |
| 90 | `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `addSource` | 3 | `(Lorg/apache/kafka/streams/processor/TimestampExtractor;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | `kafka-streams` | 3.6.2 | declared |
| 91 | `kafka-streams-topology` | `org.apache.kafka.streams.Topology` | `addSource` | 4 | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Lorg/apache/kafka/streams/processor/TimestampExtractor;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | `kafka-streams` | 3.6.2 | declared |
| 92 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `stream` | 1 | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KStream;` | `kafka-streams` | 3.6.2 | declared |
| 93 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `stream` | 2 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;` | `kafka-streams` | 3.6.2 | declared |
| 94 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `stream` | 1 | `(Ljava/util/Collection;)Lorg/apache/kafka/streams/kstream/KStream;` | `kafka-streams` | 3.6.2 | declared |
| 95 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `stream` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;` | `kafka-streams` | 3.6.2 | declared |
| 96 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `stream` | 1 | `(Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/kstream/KStream;` | `kafka-streams` | 3.6.2 | declared |
| 97 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `stream` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;` | `kafka-streams` | 3.6.2 | declared |
| 98 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `table` | 1 | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KTable;` | `kafka-streams` | 3.6.2 | declared |
| 99 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `table` | 2 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KTable;` | `kafka-streams` | 3.6.2 | declared |
| 100 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `table` | 2 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/KTable;` | `kafka-streams` | 3.6.2 | declared |
| 101 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `table` | 3 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/KTable;` | `kafka-streams` | 3.6.2 | declared |
| 102 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `globalTable` | 1 | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | `kafka-streams` | 3.6.2 | declared |
| 103 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `globalTable` | 2 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | `kafka-streams` | 3.6.2 | declared |
| 104 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `globalTable` | 2 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | `kafka-streams` | 3.6.2 | declared |
| 105 | `kafka-streams` | `org.apache.kafka.streams.StreamsBuilder` | `globalTable` | 3 | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | `kafka-streams` | 3.6.2 | declared |
| 106 | `pekko-connectors-kafka` | `org.apache.pekko.kafka.javadsl.Consumer` | `plainSource` | 2 | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;` | `pekko-connectors-kafka_2.13` | 1.1.0 | declared |
| 107 | `pekko-connectors-kafka` | `org.apache.pekko.kafka.javadsl.Consumer` | `committableSource` | 2 | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;` | `pekko-connectors-kafka_2.13` | 1.1.0 | declared |
| 108 | `pekko-connectors-kafka` | `org.apache.pekko.kafka.javadsl.Consumer` | `atMostOnceSource` | 2 | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;` | `pekko-connectors-kafka_2.13` | 1.1.0 | declared |
| 109 | `pekko-connectors-kafka` | `org.apache.pekko.kafka.javadsl.Consumer` | `plainPartitionedSource` | 2 | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/AutoSubscription;)Lorg/apache/pekko/stream/javadsl/Source;` | `pekko-connectors-kafka_2.13` | 1.1.0 | declared |
| 110 | `pekko-connectors-kafka` | `org.apache.pekko.kafka.javadsl.Consumer` | `committablePartitionedSource` | 2 | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/AutoSubscription;)Lorg/apache/pekko/stream/javadsl/Source;` | `pekko-connectors-kafka_2.13` | 1.1.0 | declared |
| 111 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/jms/core/MessagePostProcessor;)V` | `spring-jms` | 6.1.6 | declared |
| 112 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/jms/core/MessagePostProcessor;)V` | `spring-jms` | 6.1.6 | declared |
| 113 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 114 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 115 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 116 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 117 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 118 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 119 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receive` | 1 | `(Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 120 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receive` | 1 | `(Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 121 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receiveSelected` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 122 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receiveSelected` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 123 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 124 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 125 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receiveSelectedAndConvert` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 126 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receiveSelectedAndConvert` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 127 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Lorg/springframework/kafka/requestreply/RequestReplyFuture;` | `spring-kafka` | 3.1.4 | declared |
| 128 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/springframework/messaging/Message;)Lorg/springframework/kafka/requestreply/RequestReplyMessageFuture;` | `spring-kafka` | 3.1.4 | declared |
| 129 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 130 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 131 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 132 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 133 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 134 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 135 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 136 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 137 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 138 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 139 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 5 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 140 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 5 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 141 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 142 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 143 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 144 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 145 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 3 | `(Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 146 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 3 | `(Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 147 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 4 | `(Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 148 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 4 | `(Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 149 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `receive` | 4 | `(Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;` | `spring-kafka` | 3.1.4 | declared |
| 150 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `receive` | 4 | `(Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;` | `spring-kafka` | 3.1.4 | declared |
| 151 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 152 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Lcom/google/pubsub/v1/PubsubMessage;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 153 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribeAndConvert` | 3 | `(Ljava/lang/String;Ljava/util/function/Consumer;Ljava/lang/Class;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 154 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribe` | 2 | `(Ljava/lang/String;Ljava/util/function/Consumer;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 155 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pull` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 156 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAsync` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 157 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndConvert` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;Ljava/lang/Class;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 158 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndConvertAsync` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 159 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndAck` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 160 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndAckAsync` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 161 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullNext` | 1 | `(Ljava/lang/String;)Lcom/google/pubsub/v1/PubsubMessage;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 162 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullNextAsync` | 1 | `(Ljava/lang/String;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 163 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 164 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 165 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 166 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 167 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 168 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 169 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receive` | 1 | `(Ljava/lang/String;)Lorg/springframework/amqp/core/Message;` | `spring-rabbit` | 3.1.4 | declared |
| 170 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receive` | 1 | `(Ljava/lang/String;)Lorg/springframework/amqp/core/Message;` | `spring-amqp` | 3.1.4 | declared |
| 171 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receive` | 2 | `(Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;` | `spring-rabbit` | 3.1.4 | declared |
| 172 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receive` | 2 | `(Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;` | `spring-amqp` | 3.1.4 | declared |
| 173 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 174 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 175 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;J)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 176 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;J)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 177 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 178 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 179 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 3 | `(Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 180 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 3 | `(Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 181 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndReply` | 2 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z` | `spring-rabbit` | 3.1.4 | declared |
| 182 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndReply` | 2 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z` | `spring-amqp` | 3.1.4 | declared |
| 183 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndReply` | 4 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z` | `spring-rabbit` | 3.1.4 | declared |
| 184 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndReply` | 4 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z` | `spring-amqp` | 3.1.4 | declared |
| 185 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndReply` | 3 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z` | `spring-rabbit` | 3.1.4 | declared |
| 186 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndReply` | 3 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z` | `spring-amqp` | 3.1.4 | declared |
| 187 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 188 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 189 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 190 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 191 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 192 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 193 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 194 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 195 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 196 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 197 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 198 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 199 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 200 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 201 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 202 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 203 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 204 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 205 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 206 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 207 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 208 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 209 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 210 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 211 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 212 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 213 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 214 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 215 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 2 | `(Ljava/net/URI;Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 216 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 2 | `(Ljava/net/URI;Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 217 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 2 | `(Ljava/lang/String;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 218 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 2 | `(Ljava/lang/String;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 219 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 2 | `(Ljava/lang/String;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 220 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 2 | `(Ljava/lang/String;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 221 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 1 | `(Ljava/net/URI;)V` | `spring-web` | 6.1.6 | declared |
| 222 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 1 | `(Ljava/net/URI;)V` | `spring-web` | 6.1.6 | declared |
| 223 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 224 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 225 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 226 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 227 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 228 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 229 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 230 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 231 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 232 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 233 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 234 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 235 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 236 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 237 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 238 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 239 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 240 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 241 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 242 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 243 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 244 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 245 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 246 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 247 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 3 | `(Ljava/lang/String;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 248 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 4 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 249 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 3 | `(Ljava/lang/String;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 250 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 4 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 251 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 5 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 252 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 5 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 253 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 4 | `(Ljava/net/URI;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 254 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 4 | `(Ljava/net/URI;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 255 | `spring-stomp-endpoint` | `org.springframework.web.socket.config.annotation.StompEndpointRegistry` | `addEndpoint` | 1 | `([Ljava/lang/String;)Lorg/springframework/web/socket/config/annotation/StompWebSocketEndpointRegistration;` | `spring-websocket` | 6.1.6 | declared |
| 256 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 257 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 258 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 259 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 260 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 261 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 262 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 4 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 263 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 4 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 264 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 265 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 266 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 267 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 268 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 269 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `send` | 1 | `(Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 270 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `send` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 271 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `send` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 272 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 273 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 274 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 275 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 276 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 277 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 278 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 5 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 279 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 5 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 280 | `spring-websocket-client` | `org.springframework.web.socket.client.WebSocketClient` | `execute` | 3 | `(Lorg/springframework/web/socket/WebSocketHandler;Ljava/lang/String;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 281 | `spring-websocket-client` | `org.springframework.web.socket.client.WebSocketClient` | `execute` | 3 | `(Lorg/springframework/web/socket/WebSocketHandler;Lorg/springframework/web/socket/WebSocketHttpHeaders;Ljava/net/URI;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 282 | `spring-websocket` | `org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry` | `addHandler` | 2 | `(Lorg/springframework/web/socket/WebSocketHandler;[Ljava/lang/String;)Lorg/springframework/web/socket/config/annotation/WebSocketHandlerRegistration;` | `spring-websocket` | 6.1.6 | declared |
| 283 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 1 | `(Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 284 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 285 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/ws/client/core/WebServiceMessageCallback;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
<!-- table:end -->

## Verdict

**Re-run for W10 (owner alternates).** `matches.owner` may now name a LIST — one library
under the class name and under the interface a codebase more often declares its field as
(§3.1) — and this harness asks its question of each name separately, because an interface
declaring a SUBSET of the class's methods would match some call sites and silently miss the
rest. 53 of the rows above are alternate owners, and every one is `declared`.

`javax-jms.yml` is measured here too, and is NOT an alternate: an alternate is one library
under several names, while `javax.jms-api 2.0.1` and `jakarta.jms-api 3.1.0` are two jars at
two versions, each needing its own measurement (W12). All twelve of its rows come back
`declared`, and none of its descriptors is its `jakarta` counterpart with the package
swapped — `Session`'s own parameter and return types moved with the API.

Three alternates were applied after the first W10 run and are measured here for the first
time: `KafkaOperations` on `spring-kafka-template`, and Kafka's own `Consumer` and
`Producer` interfaces on `kafka-consumer` and `kafka-clients`. They were named in the
design and left out of the catalogs, which is the shape a declared-but-absent capability
takes — the same one the descriptor sweep exists to catch, from the other side.

The run also caught a wrong artifact before it could be committed: `AmqpTemplate` is in
`spring-amqp`, not in `spring-rabbit` where `RabbitTemplate` lives, so the harness ABORTED
with *"add its coordinate to run.sh rather than leaving it unmeasured"* rather than filling
a column it could not resolve. A provenance naming spring-rabbit would have been
uncheckable.

**`javalin.yml` (w61) found a real gap in this harness itself, not in a catalog.**
`declared_descriptors` walked `extends` only, because every owner measured here so
far reaches its methods through a superclass chain (`AbstractMessagingTemplate`,
`RestOperations` notwithstanding — `RestTemplate` REDECLARES its interface's methods
as its own concrete overrides, so the class itself already carries them). Javalin
does not: `io.javalin.Javalin implements JavalinDefaultRoutingApi<Javalin>` and never
overrides `get`/`post`/`put`/`delete`/`patch`/`head`/`options` at all — they run
purely as `default` methods on the interface — so the first run of this harness
after `javalin.yml` was written reported all fourteen `Javalin`-owned rows
`NOT DECLARED`, while the fourteen `JavalinDefaultRoutingApi`-owned alternates (the
same descriptors, the other name in the same `matches.owner` list) came back
`declared`. `javap -c` on the fixture settles which of the two readings is the live
one: `app.get(…)` on a `Javalin`-typed local compiles to `invokevirtual
io/javalin/Javalin.get` — so the call site DOES carry `Javalin` as its owner, and a
harness that could not see the method there would have called a correct row
`NOT DECLARED`. `declared_descriptors` now walks `implements` alongside `extends`
(mirroring `w19_catalog_surface/sweep.py`'s own `declared_methods`, which already
did), and re-running every other artifact above changed no verdict — the fix adds
supertypes to the walk, it does not touch what the walk already found.

**Found on review: a SECOND implementer of the same interface, same shape,
no further harness change needed.** `io.javalin.router.JavalinDefaultRouting`
(`public final class ... implements JavalinDefaultRoutingApi<JavalinDefaultRouting>`,
reached through `RouterConfig.mount(Consumer<JavalinDefaultRouting>)`) never
overrides the verb methods either — identical to `Javalin`'s own shape — and the
`implements`-walking fix above already covers it: all fourteen
`JavalinDefaultRouting`-owned rows came back `declared` on the run that added
them, with no second fix required.

**`pekko-connectors-kafka.yml` (`alpakka-pekko`, w62) added a fifth artifact and
five new rows, and moved no other verdict.** `org.apache.pekko.kafka.javadsl.
Consumer` is a `final class` declaring `plainSource`/`committableSource`/
`atMostOnceSource`/`plainPartitionedSource`/`committablePartitionedSource`
directly, not through an interface it never overrides — unlike `Javalin`'s own
shape — so this addition needed no walk fix, only the artifact's coordinate in
`run.sh`. All five rows came back `declared`, including the two
`plainPartitionedSource`/`committablePartitionedSource` rows whose own
descriptor takes `AutoSubscription` rather than the wider `Subscription` the
other three take (measured with `javap`, not assumed from the other three).
Diffed the regenerated table against the pre-change committed file: zero
verdict changes for any catalog other than `pekko-connectors-kafka`.


1. **Every descriptor a shipped catalog declares is real** — named by `javap -p
   -s` on the owner class or on a superclass reachable from the same jar set, at
   the versions above. Nothing in the sweep was mistyped, and nothing was
   transcribed from a source-level signature. **This is one direction only, and
   the zero failures are not a completeness result** (`A-Mi5`): the probe asks
   "is every declared descriptor real" and never "is every real overload
   declared". The second question is answered nowhere in this file — see "what
   this probe deliberately did not measure" — so a `0 NOT DECLARED` column
   means no row is wrong, not that no overload is missing. `A-M3`–`A-M7` are
   findings of exactly the second kind.
2. **An inherited method is still the owner's**, and the check has to know it.
   `SqsTemplate` declares only `send(Consumer)` itself; the arity-1 and arity-2
   forms come from `AbstractMessagingTemplate`. A call on a variable typed
   `SqsTemplate` records `SqsTemplate` as the owner all the same — javac emits
   the compile-time qualifying type — so a descriptor check that stopped at
   declared methods would have called a correct row wrong.
3. **The check is offline and the measurement is not.** The suite reads this
   file; only this harness reads a jar. That split is what keeps NFR-1's
   no-network rule and §5.4's measured-evidence rule from pulling against each
   other.

## What this probe deliberately did not measure

- **Whether the owner is the type a real call records — no longer a gap, and this
  entry is kept as the record of one.** A call made through an interface records
  THAT type, and this paragraph used to say those names "match no shipped catalog,
  whose `matches.owner` is single-valued". Both halves are now false: §3.1 widened
  `matches.owner` to a list, seven catalogs declare an alternate, and 53 of the rows
  in the table above are those very owners — `SqsOperations`, `AmqpTemplate`,
  `JmsOperations`, `RestOperations`, `KafkaOperations`, `Consumer`, `Producer` —
  every one `declared`. What the probe still does not measure is whether some FURTHER
  interface or supertype exists that no catalog names; the harness answers "is this
  owner real", never "is this the complete set of names this library is held under".
- **Whether an overload the catalogs do NOT declare exists.** The table answers
  "is this string real", never "is this the complete overload set". The catalogs'
  own comments carry the overload lists, and each names `javap` as its check.
- **`spring-webflux-router.yml`'s `methods: [route, nest]`.** A bare name list
  read by the `combinator` engine, which has no `descriptor` support at all
  (`engines/combinator.py` matches on owner and name alone). Different grammar,
  different engine; nothing here applies to it.
- **Any language but the JVM's.** `descriptor` is whatever a module's own
  extractor records at `target.descriptor`; this harness reads JVM bytecode
  because every catalog declaring one today names a JVM owner.

## How the verdict is consumed

`tests/architecture/test_catalog_descriptors.py` pins every shipped catalog
against the table above and fails on a descriptor that was never measured, a
measurement no catalog still declares, or a verdict other than `declared`.
