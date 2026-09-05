#!/usr/bin/env bash
# CP-13 harness (principles sweep round-1b fix pass) — see
# ../cp13_inherited_members.md for the question, the version scope and the
# verdicts.
#
# THE QUESTION, asked once of three sites: **when a type inherits a member,
# does the framework treat it as the type's own?** Three Class A Majors encode
# the same invented rule — a type's members are the ones it DECLARES — and the
# sweep graded all three `read`, with the framework half explicitly unverified:
# `A-M13` (a repository's query methods), `A-M14` (which methods are the base
# contract's, and therefore NOT query methods) and `A-M15` (a `@WebService`
# class's exposed SOAP operations).
#
# The language half was never in doubt (JLS 8.2, 9.2, 9.4.1, and 8.4.2 for the
# signature). What needed measuring is whether each framework ACTS on it, and
# that is answerable from bytecode: the question in every case is which
# reflective enumeration the framework calls — `Class.getMethods()`, which
# includes inherited public methods, or `getDeclaredMethods()`, which does not
# — and what it then filters out. Both are instructions.
#
# WHAT IT DOES NOT SETTLE, and the verdict must not be read past this: nothing
# here is deployed. It records the enumeration and the filters, never a served
# route or a published WSDL. A live run stays rank 2 and 11 of the sweep's own
# probe backlog.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads
# each version out of the archive it opened and ABORTS when it disagrees with
# the coordinate that resolved the jar, rather than filling a mislabelled
# column.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite, not evidence gathering.
# `tests/architecture/test_sweep_round1b_framework_surfaces.py` is the offline
# half.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`.
#
# TWO spring-data-commons minors, and the reason is the same one CP-12 gives
# for two Spring minors: an enumeration is a version-scoped fact, and one
# reading cannot say whether it is stable. 3.2.5 is what
# `fixtures/orders-service` resolves through Boot 3.x; 4.1.1 is the current
# generation. jaxws-rt 4.0.2 is the Jakarta EE 10 reference implementation —
# the one `jakarta-jws.yml`'s own comment claims to have been "verified against
# BOTH reference implementations" without naming either (`A-Mi7`); this probe
# names one and measures it, and the CXF half stays unmeasured.
ARTIFACTS=(
  "org.springframework.data|spring-data-commons|3.2.5|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework.data|spring-data-commons|4.1.1|META-INF/MANIFEST.MF|Implementation-Version"
  "com.sun.xml.ws|jaxws-rt|4.0.2|META-INF/MANIFEST.MF|Implementation-Version"
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
