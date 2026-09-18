#!/usr/bin/env bash
# CP-19 harness — see ../cp19_quarkus_rest.md for the questions, the version
# scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact's
# `META-INF/MANIFEST.MF` `Implementation-Version` is read by `probe.py` out of
# the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column.
#
# Rows 1, 2 and 4 (source reads) and row 3/6's bytecode reads run at BOTH
# 3.39.4 and 3.17.5 — one generation each side of the 3.9.0 relocation row 5
# finds — except row 6, which is scoped to 3.39.4 alone (the design spec's own
# reading of `AnnotationStore` is 3.39.4-specific and this probe does not
# re-derive it at 3.17.5).
#
# Needs a JDK (for `javap`), Maven, and network on first run (row 5 also reads
# Maven Central's plain metadata XML over HTTPS, every run — that IS the
# question, not a resolution step); the jars are cached in ~/.m2 afterwards.
# Not a test: nothing in the suite runs it, and NFR-1's no-network rule
# governs the suite rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<version>|<wants sources?>`
ARTIFACTS=(
  "rest39|io.quarkus|quarkus-rest|3.39.4|"
  "deploy39|io.quarkus|quarkus-rest-deployment|3.39.4|"
  "common39|io.quarkus.resteasy.reactive|resteasy-reactive-common|3.39.4|"
  "processor39|io.quarkus.resteasy.reactive|resteasy-reactive-common-processor|3.39.4|sources"
  "rest17|io.quarkus|quarkus-rest|3.17.5|"
  "deploy17|io.quarkus|quarkus-rest-deployment|3.17.5|"
  "common17|io.quarkus.resteasy.reactive|resteasy-reactive-common|3.17.5|"
  "processor17|io.quarkus.resteasy.reactive|resteasy-reactive-common-processor|3.17.5|sources"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r key group name version wants_sources <<<"$artifact"
  base="${M2}/${group//.//}/${name}/${version}/${name}-${version}"
  jar="${base}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  sources=""
  if [ -n "$wants_sources" ]; then
    sources="${base}-sources.jar"
    if [ ! -f "$sources" ]; then
      echo "resolving ${group}:${name}:${version}:jar:sources" >&2
      mvn -q -B dependency:get -Dtransitive=false \
        -Dartifact="${group}:${name}:${version}:jar:sources" >&2
    fi
  fi
  specs+=("${key}|${group}|${name}|${version}|${jar}|${sources}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
