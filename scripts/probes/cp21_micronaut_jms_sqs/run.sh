#!/usr/bin/env bash
# CP-21 harness — see ../cp21_micronaut_jms_sqs.md for the questions, the
# version scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact's
# `META-INF/MANIFEST.MF` `Implementation-Version` is read by `probe.py` out of
# the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column.
#
# Row 4 reads Task 1's fixture (`fixtures/orders-micronaut`), whose
# `target/` is gitignored — not itself committed — so this harness recompiles
# it with `mvn compile` when the class is missing, exactly as Task 1's own
# build step did, rather than depending on a stale local build artifact.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

ARTIFACTS=(
  "core|io.micronaut.jms|micronaut-jms-core|4.2.0"
  "sqs|io.micronaut.jms|micronaut-jms-sqs|4.2.0"
  "amq|io.micronaut.jms|micronaut-jms-activemq-classic|4.2.0"
  "artemis|io.micronaut.jms|micronaut-jms-activemq-artemis|4.2.0"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r key group name version <<<"$artifact"
  base="${M2}/${group//.//}/${name}/${version}/${name}-${version}"
  jar="${base}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${key}|${group}|${name}|${version}|${jar}")
done

fixture_dir="${REPO}/fixtures/orders-micronaut"
fixture_classes="${fixture_dir}/target/classes"
if [ ! -f "${fixture_classes}/com/acme/mn/OrderMessaging\$SqsConsumer.class" ]; then
  echo "compiling fixtures/orders-micronaut" >&2
  (cd "$fixture_dir" && mvn -q -B compile) >&2
fi

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}" "FIXTURE=${fixture_classes}"
