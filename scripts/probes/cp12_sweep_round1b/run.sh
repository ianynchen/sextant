#!/usr/bin/env bash
# CP-12 harness (principles sweep round-1b fix pass) — see
# ../cp12_sweep_round1b.md for the questions, the version scope and the
# verdicts.
#
# THE QUESTIONS. Eight Class A Majors whose catalog encodes a SUBSET of the
# framework's surface and says nothing about the rest (GUIDELINES §8.1 rule 3,
# DR-6): `spring-webclient`/`spring-restclient`'s five-of-eight request
# starters and version-wrong terminal set (`A-M3`, `A-M4`), `retrofit`'s
# six-of-eight request-method annotations (`A-M5`), the Kafka catalogs' missing
# callback and rebalance-listener overloads (`A-M6`), `jakarta-jms`'s one of
# eleven consumer factories (`A-M7`), `spring-sqs`'s one half of an `@AliasFor`
# pair (`A-M8`), and `spring-webflux-router`'s verb vocabulary, which is
# exactly the FIXTURE's verb vocabulary (`A-M9`).
#
# EVERY ANSWER IS THE FRAMEWORK'S WHOLE SET, not a check of what we declared.
# That is the difference from CP-10, whose green table asks only whether every
# descriptor a catalog declares names a real method and never the converse — and
# all eight findings above live on the converse side (`A-Mi5`).
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact
# below names WHERE it writes its own version, and `probe.py` reads the VALUE
# out of the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column. Two artifacts are not the manifest: kafka-clients writes no manifest
# version and states one in `kafka/kafka-version.properties`; retrofit writes
# one NOWHERE — no manifest entry, no `pom.properties`, no constant — so it is
# declared `-` here and the run prints "assumed" for that column instead of
# claiming a measurement, exactly as CP-11 does for the same jar.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite, not evidence gathering.
# `tests/architecture/test_sweep_round1b_framework_surfaces.py` is the offline
# half, and it pins the shipped catalogs against the table this prints.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here.
#
# TWO Spring minors, not one, and the reason is `A-M4` exactly: WebClient's
# terminal set CHANGED between them — `exchange()` exists at 6.1.6 and is gone
# at 7.0.2 — and a catalog that states no version cannot be read against
# either. 6.1.6 is what `fixtures/orders-service/pom.xml` pins and is the only
# version anywhere near those two catalogs today; 7.0.2 is the current major.
# The remaining coordinates are the versions CP-10 already pinned for the same
# catalogs (kafka-clients 3.6.2, spring-kafka 3.1.4, jakarta.jms-api 3.1.0,
# spring-cloud-aws-sqs 3.1.1) and retrofit 2.11.0, which is CP-11's.
ARTIFACTS=(
  "org.springframework|spring-web|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-web|7.0.2|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webflux|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webflux|7.0.2|META-INF/MANIFEST.MF|Implementation-Version"
  "com.squareup.retrofit2|retrofit|2.11.0|-|-"
  "org.apache.kafka|kafka-clients|3.6.2|kafka/kafka-version.properties|version"
  "org.springframework.kafka|spring-kafka|3.1.4|META-INF/MANIFEST.MF|Implementation-Version"
  "jakarta.jms|jakarta.jms-api|3.1.0|META-INF/MANIFEST.MF|Implementation-Version"
  "io.awspring.cloud|spring-cloud-aws-sqs|3.1.1|META-INF/MANIFEST.MF|Implementation-Version"
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
