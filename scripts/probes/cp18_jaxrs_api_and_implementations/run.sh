#!/usr/bin/env bash
# CP-18 harness — see ../cp18_jaxrs_api_and_implementations.md for the
# questions, the version scope and the verdicts.
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

# `<key>|<groupId>|<artifactId>|<version>|<manifest entry>|<manifest key>`.
# jersey-server carries no `Implementation-Version`, only OSGi's own
# `Bundle-Version` — read where the archive actually writes it, not where a
# sibling artifact happens to.
ARTIFACTS=(
  "jakarta40|jakarta.ws.rs|jakarta.ws.rs-api|4.0.0|META-INF/MANIFEST.MF|Implementation-Version"
  "jakarta31|jakarta.ws.rs|jakarta.ws.rs-api|3.1.0|META-INF/MANIFEST.MF|Implementation-Version"
  "javax211|javax.ws.rs|javax.ws.rs-api|2.1.1|META-INF/MANIFEST.MF|Implementation-Version"
  "jersey40|org.glassfish.jersey.core|jersey-server|4.0.0|META-INF/MANIFEST.MF|Bundle-Version"
  "resteasy|org.jboss.resteasy|resteasy-core|6.2.12.Final|META-INF/MANIFEST.MF|Implementation-Version"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r key group name version entry mkey <<<"$artifact"
  base="${M2}/${group//.//}/${name}/${version}/${name}-${version}"
  jar="${base}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${key}|${group}|${name}|${version}|${entry}|${mkey}|${jar}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
