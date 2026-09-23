#!/usr/bin/env bash
# CP-10 harness (descriptor sweep, ruling R7) — see
# ../cp10_catalog_descriptors.md for the question, the version scope and the
# verdict.
#
# THE QUESTION. `_validate_methods` checks only that a `descriptor:` is a string
# opening with `(`. A wrong return type, a misspelled package or a stale erasure
# passes that check, CLAIMS its candidate set in `_matching_method`, and makes
# every overload of that name derive nothing — silently, with no error and no
# COVERAGE row. This harness answers the one question that check cannot: does
# each descriptor a shipped catalog declares actually name a method the
# framework's own bytecode declares?
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Every artifact
# below names WHERE it writes its own version — Maven's `pom.properties`, the
# manifest's `Implementation-Version`, Kafka's own `kafka-version.properties` —
# and `descriptors.py` reads the VALUE out of the archive it opened. A jar whose
# self-report disagrees with the coordinate that resolved it ABORTS the run
# rather than filling a mislabelled column.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite, not evidence gathering.
# `tests/architecture/test_catalog_descriptors.py` is the offline half, and it
# pins the shipped catalogs against the table this prints.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# The artifacts this probe's verdict is scoped to, as
# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here. Every version matches what a fixture
# pom pins, EXCEPT spring-websocket, which no fixture depends on at all — it is
# pinned to the Spring Framework version the fixtures do use, and that is a
# stated assumption rather than a measurement.
ARTIFACTS=(
  "com.google.cloud|google-cloud-pubsub|1.129.3|pom.properties|version"
  "com.google.cloud|spring-cloud-gcp-pubsub|5.1.2|pom.properties|version"
  "io.awspring.cloud|spring-cloud-aws-sqs|3.1.1|pom.properties|version"
  "jakarta.jms|jakarta.jms-api|3.1.0|pom.properties|version"
  # W12's twin. `javax.jms-api 2.0.1` is the LAST release under that coordinate —
  # the line does not ship again — so it is the only version a Spring Boot 2
  # codebase can be on. Its descriptors are not `jakarta`'s with the package
  # swapped as a matter of faith: `Session`'s own parameter and return types moved
  # with the API, so all four differ, and this harness is what checks each one
  # against the jar rather than against that expectation.
  "javax.jms|javax.jms-api|2.0.1|pom.properties|version"
  "org.apache.kafka|kafka-clients|3.6.2|kafka/kafka-version.properties|version"
  # G-31 (w60). Kafka Streams writes its OWN version file, at a different path than
  # the raw client jar's `kafka/kafka-version.properties` — measured with `unzip -l`
  # rather than assumed from the sibling artifact.
  "org.apache.kafka|kafka-streams|3.6.2|kafka/kafka-streams-version.properties|version"
  # javalin-routing (w61). Javalin writes BOTH a `pom.properties` and a manifest
  # `Implementation-Version:` — measured with `unzip -l` rather than assumed;
  # `pom.properties` is read here, the same order w61's own harness checks first.
  "io.javalin|javalin|6.4.0|pom.properties|version"
  # alpakka-pekko (w62). pekko-connectors-kafka_2.13 writes no `pom.properties` (a
  # Scala/sbt-built artifact, not `mvn`-built) but does write a manifest
  # `Implementation-Version:` — measured with `unzip -l`, the same rung w61's own
  # harness checks second.
  "org.apache.pekko|pekko-connectors-kafka_2.13|1.1.0|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-jms|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  # W43. `SimpMessagingTemplate` lives here, and `convertAndSend` is declared one
  # level up on `MessageSendingOperations<D>` — so the harness's superclass walk is
  # what reaches it, exactly as it does for `SqsTemplate.send`. Pinned to the version
  # the fixture's own pom declares.
  "org.springframework|spring-messaging|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  # W46. `WebSocketContainer.connectToServer` lives here, and the annotations the
  # server catalog matches on do too — the `-api` jar at 2.2.0 holds ONLY
  # `jakarta/websocket/server/**`, measured.
  "jakarta.websocket|jakarta.websocket-client-api|2.2.0|META-INF/MANIFEST.MF|Implementation-Version"
  # `jakarta-websocket-programmatic.yml` matches `ServerEndpointConfig$Builder.create`,
  # declared in the SERVER api jar rather than the client one above; this entry was
  # missing (the catalog's own `measured:` cites this file, but the harness could not
  # reach its jar), which aborted every run of this probe rather than any one catalog.
  "jakarta.websocket|jakarta.websocket-api|2.1.1|pom.properties|version"
  "org.springframework|spring-web|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-websocket|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.amqp|spring-rabbit|3.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  # W10. `AmqpTemplate` is the interface a codebase declares its field as, and it
  # lives in spring-amqp rather than in spring-rabbit where the template class is.
  # The harness ABORTED rather than leave it unmeasured, which is how the wrong
  # artifact was caught — a provenance naming spring-rabbit could not be checked.
  "org.springframework.amqp|spring-amqp|3.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.kafka|spring-kafka|3.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.ws|spring-ws-core|4.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  # G-30-outbound (A2 Task 7). `RouteLocatorBuilder$Builder.route` in both overloads;
  # the jar writes BOTH a `pom.properties` and a manifest `Implementation-Version:`
  # (measured with `unzip -l`), and the manifest is read here. Pinned to the version
  # `fixtures/orders-gateway/pom.xml` declares.
  "org.springframework.cloud|spring-cloud-gateway-server-webflux|5.0.0|META-INF/MANIFEST.MF|Implementation-Version"
  # `temporal-untyped.yml` (Group D Task 5). `WorkflowClient.newUntypedWorkflowStub`
  # lives here. THE SELF-REPORT ENTRY IS `-`/`-`, and that is a measurement rather
  # than a shortcut: this archive states no version anywhere in its own bytes — its
  # manifest carries only `Manifest-Version` and `Multi-Release`, it ships no
  # `META-INF/maven/*/pom.properties`, and no class constant pool holds the literal
  # `1.27.0` (CP-30's Version scope section checked all three exhaustively). The
  # sentinel routes `descriptors.py` to the SHA-1 check against Maven's own
  # `.jar.sha1` sidecar, which is what CP-30 does with the same two archives.
  # Pinned to the version `fixtures/temporal-probe/pom.xml` declares.
  "io.temporal|temporal-sdk|1.27.0|-|-"
  # `vertx-eventbus.yml` (Group D Task 8), and the FIRST artifactId this harness
  # reads at TWO versions. That is the catalog's own shape rather than an
  # accident: spec 2026-09-22 §3a puts 4.5-only and 5.0-only overloads of
  # `io.vertx.core.eventbus.EventBus` in one file, because an overload absent
  # from the version a module builds against simply never matches. `descriptors.py`
  # keys its jars by `<artifactId>:<version>` for exactly this pair and gives each
  # candidate its own classpath, so a row is filed against the version that
  # actually declares its descriptor and a sibling version can never answer for
  # it. Both versions are the ones CP-31 measured; 4.5.10 is also what
  # `fixtures/orders-eventbus/pom.xml` pins.
  "io.vertx|vertx-core|4.5.10|META-INF/MANIFEST.MF|Implementation-Version"
  "io.vertx|vertx-core|5.0.0|META-INF/MANIFEST.MF|Implementation-Version"
  # `vertx-eventbus-mutiny.yml` (Group D Task 8 fix round 1). The Mutiny facade a
  # Quarkus service injects is a DIFFERENT artifact from the interface it wraps and
  # shares no descriptor with it (CP-31 Q8), which is why it is a catalog of its own
  # and why its coordinate is one of its own here. Pinned to the version CP-31
  # measured and `fixtures/orders-eventbus/pom.xml` declares.
  "io.smallrye.reactive|smallrye-mutiny-vertx-core|3.16.0|META-INF/MANIFEST.MF|Implementation-Version"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r group name version entry key <<<"$artifact"
  jar="${M2}/${group//.//}/${name}/${version}/${name}-${version}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${group}|${name}|${version}|${entry}|${key}|${jar}")
done

# The repository's own interpreter, so `yaml` resolves the way it does for the
# suite that reads the same catalogs.
if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" descriptors.py "${specs[@]}"
