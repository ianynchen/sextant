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
  "org.springframework|spring-jms|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  # W43. `SimpMessagingTemplate` lives here, and `convertAndSend` is declared one
  # level up on `MessageSendingOperations<D>` — so the harness's superclass walk is
  # what reaches it, exactly as it does for `SqsTemplate.send`. Pinned to the version
  # the fixture's own pom declares.
  "org.springframework|spring-messaging|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
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
