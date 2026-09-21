#!/usr/bin/env bash
# CP-24 harness — see ../cp24_ktor_routing.md for the questions, the version scope
# and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each
# jar's own manifest `Implementation-Version` rather than trusting the coordinate
# that resolved it, and aborts when a jar reports a version other than the one the
# run expected — so a stale or mis-resolved archive cannot fill a column labelled
# with a version it never was.
#
# Needs a JDK (for `javap`), and Maven plus network on first run only; the three
# jars are cached in ~/.m2 afterwards. Nothing is executed — every cell is a
# `javap` read of a class file. Not a test: nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"
VERSION="3.0.3"

# `<key>|<groupId>|<artifactId>`
ARTIFACTS=(
  "server|io.ktor|ktor-server-core-jvm"
  "http|io.ktor|ktor-http-jvm"
  "utils|io.ktor|ktor-utils-jvm"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r key group name <<<"$artifact"
  jar="${M2}/${group//.//}/${name}/${VERSION}/${name}-${VERSION}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${VERSION}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${VERSION}" >&2
  fi
  specs+=("${key}|${group}|${name}|${VERSION}|${jar}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
