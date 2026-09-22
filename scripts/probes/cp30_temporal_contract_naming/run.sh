#!/usr/bin/env bash
# CP-30 harness — see ../cp30_temporal_contract_naming.md for the questions, the version
# scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each jar's
# own manifest `Implementation-Version` rather than trusting the coordinate that resolved
# it, and aborts when a jar reports a version other than the one the run expected — so a
# stale or mis-resolved archive cannot fill a column labelled with a version it never was.
# NEITHER jar below states an `Implementation-Version` at all (unlike every jar CP-27
# through CP-29 read this way): `probe.py` falls back to verifying the resolved jar's own
# SHA-1 against the `.jar.sha1` sidecar `mvn dependency:get` wrote beside it, aborting on a
# mismatch the same way — see `cp30_temporal_contract_naming.md`'s Version scope section.
#
# Two specs only, for now: `temporal-sdk` (the naming rules themselves) and
# `temporal-spring-boot-autoconfigure` (the three starter annotations). Task 6 appends a
# third spec line — the fixture's own compiled classes — the same way CP-27's last spec
# is the fixture's `target/classes`; until then this script's `specs` array ends after the
# two jars, and `cp30_temporal_contract_naming.md` says the fixture row is pending. Needs
# a JDK (for `javap`) and Maven for the `dependency:get` fallback; network only if a jar is
# missing from `~/.m2` (both are already resolved locally as of this write-up). Nothing is
# executed — every cell is a `javap` read of a class file. Not a test: nothing in the suite
# runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<version>`
ARTIFACTS=(
  "sdk|io.temporal|temporal-sdk|1.27.0"
  "boot|io.temporal|temporal-spring-boot-autoconfigure|1.27.0"
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

# Task 6 appends the fixture spec here, e.g.:
#   (cd "$FIXTURE" && mvn -q -o compile >&2)
#   specs+=("fixture|com.example|temporal-eventbus-probe|-|${FIXTURE}/target/classes")

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
