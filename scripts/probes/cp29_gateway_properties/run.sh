#!/usr/bin/env bash
# CP-29 harness — see ../cp29_gateway_properties.md for the questions, the version
# scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each
# jar's own manifest `Implementation-Version` rather than trusting the coordinate
# that resolved it, and aborts when a jar reports a version other than the one the
# run expected — so a stale or mis-resolved archive cannot fill a column labelled
# with a version it never was.
#
# Needs a JDK (for `javap`), and Maven plus network on first run only; the four
# jars are cached in ~/.m2 afterwards. Nothing is executed — every cell is a
# `javap` read of a class file, or a byte scan of the archive's own entries. Not a
# test: nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<version>` — the Gateway the fixture builds against
# (`fixtures/orders-gateway/pom.xml`), and the spring-web / -webflux / -webmvc the
# router catalogs are measured at (`scripts/probes/cp12_sweep_round1b.md`).
ARTIFACTS=(
  "gateway|org.springframework.cloud|spring-cloud-gateway-server-webflux|5.0.0"
  "web|org.springframework|spring-web|6.1.6"
  "webflux|org.springframework|spring-webflux|6.1.6"
  "webmvc|org.springframework|spring-webmvc|6.1.6"
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
