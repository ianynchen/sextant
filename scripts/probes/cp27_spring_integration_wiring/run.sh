#!/usr/bin/env bash
# CP-27 harness — see ../cp27_spring_integration_wiring.md for the questions, the
# version scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each
# jar's own manifest `Implementation-Version` rather than trusting the coordinate
# that resolved it, and aborts when a jar reports a version other than the one the
# run expected — so a stale or mis-resolved archive cannot fill a column labelled
# with a version it never was.
#
# The last row reads the committed fixture's OWN compiled classes: this script
# compiles `fixtures/spring-integration-probe` (Maven, offline — its dependencies
# are the same jars) and `probe.py` javaps `target/classes` for the owners the
# flows' call sites actually name. Needs a JDK (for `javap`) and Maven; network on
# first run only, for the jars. Nothing is executed — every cell is a `javap` read
# of a class file. Not a test: nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"
FIXTURE="$REPO/fixtures/spring-integration-probe"

# `<key>|<groupId>|<artifactId>|<version>` — the versions the Spring Boot 3.2.5 BOM
# the fixture builds against manages, which is what `mvn dependency:list` on the
# fixture resolves (scripts/probes/spring-integration-destinations.md).
ARTIFACTS=(
  "core|org.springframework.integration|spring-integration-core|6.2.4"
  "kafka-dsl|org.springframework.integration|spring-integration-kafka|6.2.4"
  "amqp-dsl|org.springframework.integration|spring-integration-amqp|6.2.4"
  "rabbit|org.springframework.amqp|spring-rabbit|3.1.4"
  "amqp|org.springframework.amqp|spring-amqp|3.1.4"
  "kafka|org.springframework.kafka|spring-kafka|3.1.4"
  "context|org.springframework|spring-context|6.1.6"
  "beans|org.springframework|spring-beans|6.1.6"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r key group name version <<<"$artifact"
  jar="${M2}/${group//.//}/${name}/${version}/${name}-${version}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${key}|${group}|${name}|${version}|${jar}")
done

(cd "$FIXTURE" && mvn -q -o compile >&2)
specs+=("fixture|com.example|spring-integration-probe|-|${FIXTURE}/target/classes")

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
