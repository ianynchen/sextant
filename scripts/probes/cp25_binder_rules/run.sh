#!/usr/bin/env bash
# CP-25 harness — see ../cp25_binder_rules.md for the questions, the version scope
# and the verdicts. Row 1 (Javalin's `ApiBuilder` guard) is here now; the binder
# rows the request-requirements work adds join this same harness.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE JAR'S OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads the
# jar's own manifest `Implementation-Version` rather than trusting the coordinate
# that resolved it, and aborts when the jar reports a version other than the one
# the run expected.
#
# Needs a JDK (for `javap`), and Maven plus network on first run only; the jar is
# cached in ~/.m2 afterwards. Nothing is executed — every cell is a `javap` read of
# a class file. Not a test: nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<version>`
ARTIFACTS=(
  "javalin|io.javalin|javalin|6.4.0"
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

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
