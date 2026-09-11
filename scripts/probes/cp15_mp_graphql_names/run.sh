#!/usr/bin/env bash
# CP-15 harness (Stage 4, the per-catalog pass; `OI-5` / `A-Mi9`) — see
# ../cp15_mp_graphql_names.md for the questions, the version scope and the
# verdicts.
#
# THE QUESTION. `microprofile-graphql.yml` publishes an operation at the
# annotated method's OWN name when `@Query`/`@Mutation` names none
# (`path_fallback: construct_name`), and the catalog's own comment says that is
# a prediction: "the fallback publishes the method's own name because that is
# Spring's rule, and MicroProfile is a different implementation". `OI-5` ranks
# it the highest-value item in the probe backlog because it would publish a
# WRONG ADDRESS rather than a missing one. So: (1) every source the schema
# builder consults for an operation's name, in order; (2) which annotation type
# each of those sources is; (3) what the name is when none supplied one; (4) the
# transformation that fallback applies; and (5) what the implementation
# ACTUALLY RETURNS for a table of method names — compiled against the resolved
# jar and run, because `OI-5`'s close condition is a name and not a reading.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact
# below names WHERE it writes its own version, and `probe.py` reads the VALUE
# out of the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column.
#
# WHY SMALLRYE AND NOT THE API JAR. MicroProfile GraphQL's API artifact —
# the one `detect.coordinates` names — declares the annotations and NO naming
# rule; the rule belongs to an implementation. `measured:`'s own contract is
# that `artifact` is the artifact a rule was READ OUT OF rather than the
# declared dependency, and `spring-web.yml`'s handler gate living in
# spring-webmvc is the shipped precedent. SmallRye is ONE implementation, so
# every verdict is scoped to it and the row saying so is part of the verdict.
#
# Needs a JDK (for `javap`, and for `javac`/`java` in question 5), Maven, and
# network on first run; the jars are cached in ~/.m2 afterwards. Not a test:
# nothing in the suite runs it, and NFR-1's no-network rule governs the suite
# rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here.
#
# TWO SmallRye minors, for CP-12's reason: a naming rule is a version-scoped
# fact and one reading cannot say whether it is stable. 2.0.0 is the first
# release of the line implementing MicroProfile GraphQL 2.0 — the specification
# version `microprofile-graphql.yml` gates on — and 2.18.5 is the last release
# of that line at the time of the run, so the two columns bound the generation
# at both ends.
ARTIFACTS=(
  "io.smallrye|smallrye-graphql-schema-builder|2.0.0|META-INF/MANIFEST.MF|Implementation-Version"
  "io.smallrye|smallrye-graphql-schema-builder|2.18.5|META-INF/MANIFEST.MF|Implementation-Version"
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
