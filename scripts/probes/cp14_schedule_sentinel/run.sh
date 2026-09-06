#!/usr/bin/env bash
# CP-14 harness (Stage 4, the per-catalog pass; `OI-2`) — see
# ../cp14_schedule_sentinel.md for the questions, the version scope and the
# verdicts.
#
# THE QUESTION. `spring-scheduling.yml` reads five attributes of `@Scheduled`
# as schedules and treats NO value as the framework's "never schedule this"
# sentinel, so a declaration the framework will never run publishes a
# `scheduled_work` row saying it does (`OI-2`). Encoding a sentinel from memory
# is what §8.1 forbids, so this measures it: (1) what `@Scheduled` declares —
# its compile-time constants and its attributes; (2) which attribute the
# sentinel is compared against and what the comparison stands in front of,
# because a constant named `CRON_DISABLED` is a name and not a behaviour; and
# (3) the converse CP-10's table is criticised for never asking — whether that
# value is the ONLY one this post-processor reads as an absence, or whether a
# fixed rate or a fixed delay has a sentinel of its own.
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
# NFR-1's no-network rule governs the suite, not evidence gathering.
# `tests/application/test_scheduled_work.py` is the offline half.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here.
#
# THREE spring-context minors, for CP-12's reason: a sentinel is a version-
# scoped fact and one reading cannot say whether it is stable. 6.1.6 is what
# `fixtures/orders-service/pom.xml` pins; 6.2.19 and 7.0.9 are the two later
# generations, so the three columns span every Spring line this repository
# claims to read.
ARTIFACTS=(
  "org.springframework|spring-context|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-context|6.2.19|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-context|7.0.9|META-INF/MANIFEST.MF|Implementation-Version"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r group name version entry key <<<"$artifact"
  jar="${M2}/${group//.//}/${name}/${version}/${name}-${version}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${group}|${name}|${version}|${entry}|${key}|${jar}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
