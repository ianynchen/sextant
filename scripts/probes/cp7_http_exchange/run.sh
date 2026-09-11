#!/usr/bin/env bash
# CP-7 harness (2O Task 10, the `@HttpExchange` direction flip) — see
# ../cp7_http_exchange.md for the questions, the version scope and the verdicts.
#
# THE QUESTIONS. Task 10 flips an `@HttpExchange` interface's rows from OUTBOUND
# to INBOUND when the module implements that interface with a controller. Every
# clause of that sentence is a claim about Spring, and DR-6 says mirror what the
# framework does rather than predict it: (1) what the server-side handler
# predicate actually is — `@Controller` alone, or `@Controller` OR a type-level
# `@RequestMapping`; (2) whether the server side reads `@HttpExchange` at all,
# and with which annotation search; (3) whether a `default` method a controller
# inherits and never overrides is a handler candidate; (4) which attribute of
# `@HttpExchange` carries the address, on each side of the wire.
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
# `tests/architecture/test_http_exchange_direction_rules.py` is the offline
# half, and it pins the shipped catalog against the table this prints.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here.
#
# FOUR spring-webmvc minors, for `A-C7`'s own reason: the whole claim about the
# handler predicate is that it is STABLE and that a literal annotation compare
# is not, and a verdict from a single minor could not say that. 6.1.6 is the
# version `fixtures/orders-service/pom.xml` pins and the first Spring line with
# server-side `@HttpExchange` at all. spring-core carries the handler-method
# scan (Q3) and spring-web the annotation itself (Q4); each is resolved at the
# 6.2.15 that spring-webmvc's own middle column reports, because a question
# about one class is evidence about the jar that declares it and no other.
ARTIFACTS=(
  "org.springframework|spring-core|6.2.15|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-web|6.2.15|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|6.2.15|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|7.0.2|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|7.0.9|META-INF/MANIFEST.MF|Implementation-Version"
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
