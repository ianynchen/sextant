#!/usr/bin/env bash
# CP-22 harness — see ../cp22_microprofile_rest_client.md for the questions,
# the version scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads
# each jar's own manifest entry rather than trusting the coordinate that
# resolved it. `microprofile-rest-client-api`'s Maven coordinate is "4.0" —
# there is no "4.0.0" directory in the repository — but the jar's own OSGi
# `Bundle-Version` pads that to "4.0.0" (a normal OSGi convention, not a
# mislabel); `REQUESTED_IDENTITY` below is what the ARCHIVE reports, decoupled
# from `VERSION`, which is only the Maven coordinate used to resolve it.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<Maven VERSION>|<REQUESTED_IDENTITY>|<manifest key>`
ARTIFACTS=(
  "mp40|org.eclipse.microprofile.rest.client|microprofile-rest-client-api|4.0|4.0.0|Bundle-Version"
  "mp301|org.eclipse.microprofile.rest.client|microprofile-rest-client-api|3.0.1|3.0.1|Bundle-Version"
  "qrc|io.quarkus|quarkus-rest-client|3.39.4|3.39.4|Implementation-Version"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r key group name version identity mkey <<<"$artifact"
  base="${M2}/${group//.//}/${name}/${version}/${name}-${version}"
  jar="${base}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${key}|${group}|${name}|${identity}|${jar}|${mkey}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}" "REPO=${REPO}"
