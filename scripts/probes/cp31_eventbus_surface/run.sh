#!/usr/bin/env bash
# CP-31 harness — see ../cp31_eventbus_surface.md for the questions, the version
# scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each jar's
# own manifest `Implementation-Version` rather than trusting the coordinate that resolved
# it, and aborts when a jar reports a version other than the one the run expected — so a
# stale or mis-resolved archive cannot fill a column labelled with a version it never was.
# Unlike CP-30's two Temporal archives, every jar below DOES state an
# `Implementation-Version`, so no SHA-1 fallback is reached here.
#
# FIVE jar specs — vertx-core at BOTH major versions in scope (the whole point of M7:
# `vertx-eventbus.yml` declares 4.5-only and 5.0-only overloads in one file, and a row
# that exists in neither jar is a row that matches nothing), the Mutiny facade, the
# Quarkus runtime module that declares `@ConsumeEvent`, and the Quarkus DEPLOYMENT module
# whose `VertxProcessor` is what fills the annotation's default address — plus a sixth,
# fixture spec: `fixtures/orders-eventbus`'s own compiled classes, the same way CP-30's
# last spec is that probe's fixture `target/classes`. Needs a JDK (for `javap`) and Maven
# (for the `dependency:get` fallback and the fixture's own offline compile); network only
# if a jar is missing from `~/.m2` (all five were already resolved locally as of this
# write-up — the fixture is primed by `tests/fixture_build.py`'s `PRIMED_FIXTURES`).
# Nothing is executed — every cell is a `javap` read of a class file. Not a test: nothing
# in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"
FIXTURE="$REPO/fixtures/orders-eventbus"

# `<key>|<groupId>|<artifactId>|<version>`
ARTIFACTS=(
  "core45|io.vertx|vertx-core|4.5.10"
  "core50|io.vertx|vertx-core|5.0.0"
  "mutiny|io.smallrye.reactive|smallrye-mutiny-vertx-core|3.16.0"
  "quarkus|io.quarkus|quarkus-vertx|3.17.5"
  "deployment|io.quarkus|quarkus-vertx-deployment|3.17.5"
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
specs+=("fixture|com.acme|orders-eventbus|-|${FIXTURE}/target/classes")

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
