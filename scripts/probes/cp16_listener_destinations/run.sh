#!/usr/bin/env bash
# CP-16 harness (Stage 4, the per-catalog pass; probe-backlog rank 7) — see
# ../cp16_listener_destinations.md for the questions, the version scope and the
# verdicts.
#
# THE QUESTION, asked once of three sites. `spring-kafka.yml`, `spring-jms.yml`
# and `spring-rabbit.yml` each read a destination off a listener annotation, and
# each states its rule as a "CHECKPOINT FACT" comment with no version and no
# committed evidence — all three are entries in `_NOT_MEASURED_YET`, and the
# principles sweep ranks them together at rank 7 of its probe backlog. So, per
# framework: (1) every attribute the listener annotation declares, with its
# TYPE, because an alias set is only as trustworthy as the enumeration it was
# chosen from; (2) `@Target` and `@Repeatable` on it, because the container
# javac folds a repeated annotation into is a fact a catalog must NAME to see
# such a method at all; (3) what the sibling polymorphic-handler annotation
# declares, which each catalog claims is no address; and (4) how the
# post-processor FINDS the annotation and which of its attributes it reads.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact
# below names WHERE it writes its own version, and `probe.py` reads the VALUE
# out of the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here.
#
# TWO minors per framework, for CP-12's reason: an attribute set is a
# version-scoped fact and one reading cannot say whether it is stable. The
# lower column of each pair is the version the shipped catalog's own comment
# names or the fixture resolves (spring-kafka 3.1.4, spring-rabbit 3.1.4,
# spring-jms 6.1.6); the upper is the current generation, so each pair spans
# a major boundary rather than two patch releases.
ARTIFACTS=(
  "org.springframework.kafka|spring-kafka|3.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.kafka|spring-kafka|4.1.1|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-jms|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-jms|7.0.9|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.amqp|spring-rabbit|3.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.amqp|spring-rabbit|4.1.1|META-INF/MANIFEST.MF|Implementation-Version"
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

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
