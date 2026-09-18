#!/usr/bin/env bash
# CP-20 harness — see ../cp20_spring_kafka_batch.md for the questions, the
# version scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact's
# `META-INF/MANIFEST.MF` `Implementation-Version` is read by `probe.py` out of
# the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column. Row 5 is not a jar read — it is a grep over this repository's own
# catalog files, so its identity is the git commit `run.sh` resolves HEAD to.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

ARTIFACTS=(
  "kafka314|org.springframework.kafka|spring-kafka|3.1.4"
  "kafka411|org.springframework.kafka|spring-kafka|4.1.1"
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

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}" "REPO=${REPO}"
