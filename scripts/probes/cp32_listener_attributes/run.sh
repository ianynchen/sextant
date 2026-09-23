#!/usr/bin/env bash
# CP-32 harness — see ../cp32_listener_attributes.md for the questions, the version
# scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each jar's
# own manifest `Implementation-Version` rather than trusting the coordinate that resolved
# it, and aborts when a jar reports a version other than the one the run expected — so a
# stale or mis-resolved archive cannot fill a column labelled with a version it never was.
# CP-31's shape exactly, one framework family over; like CP-31 and unlike CP-30, every jar
# below DOES state an `Implementation-Version`, so no SHA-1 fallback is reached here.
#
# EIGHT jar specs — the three Spring listener modules whose annotations `spring-kafka.yml`,
# `spring-jms.yml` and `spring-rabbit.yml` read, the two Micronaut modules
# `micronaut-kafka.yml` and `micronaut-jms.yml` read, and three Micronaut core modules that
# arrived with fix round 1: `micronaut-core-processor`, whose
# `AbstractAnnotationMetadataBuilder` is what actually RESOLVES an `@AliasFor` (Q13), plus
# `micronaut-core` and `micronaut-inject`, which fill no cell of their own and are here only
# to complete Q12's compile classpath.
#
# THREE class-directory specs — `fixtures/orders-service` and `fixtures/orders-micronaut`,
# the committed repositories whose own compiled classes carry the shipped listener
# declarations (CP-31's Q9 / CP-27's row-16 pattern: they are what say which shipped
# endpoints a `metadata_from` line would move), and a THIRD that is not a fixture at all —
# `AliasProbe.java`, compiled here into a temporary directory so Q12 can read what javac
# writes for a declaration that sets BOTH aliased elements. That compile is the one thing
# this probe creates rather than reads, and it creates it because the alternative was a
# catalog sentence nobody had measured.
#
# THE VERSION OF `spring-jms` IS 6.1.6, NOT 3.1.4. The design's §6 sketch names "spring-jms
# 3.1.4"; no such artifact exists — `spring-jms` is versioned with Spring Framework, and
# `spring-jms.yml`'s own `measured:` rows say 6.1.6 and 7.0.9. Each jar below is read at the
# version the CATALOG that reads it already claims to have measured, which is the only
# version a `measured:` row may cite.
#
# Needs a JDK (for `javap` and Q12's one `javac`) and Maven (for the `dependency:get`
# fallback and the fixtures' own offline compiles); network only if a jar is missing from
# `~/.m2` (all eight were already resolved locally as of this write-up — the fixtures are
# primed by `tests/fixture_build.py`'s `PRIMED_FIXTURES`). Nothing is EXECUTED — every cell
# is a `javap` read of a class file, including Q12's, whose class file this run compiled a
# moment earlier. Not a test: nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<version>`
ARTIFACTS=(
  "kafka|org.springframework.kafka|spring-kafka|3.1.4"
  "jms|org.springframework|spring-jms|6.1.6"
  "rabbit|org.springframework.amqp|spring-rabbit|3.1.4"
  "mnkafka|io.micronaut.kafka|micronaut-kafka|5.6.0"
  "mnjms|io.micronaut.jms|micronaut-jms-core|4.2.0"
  # Q13's artifact, and Q12's compile classpath. 4.7.6 is the version
  # `fixtures/orders-micronaut`'s own POM resolves, so the alias behaviour read here is the
  # one that repository would get.
  "mnprocessor|io.micronaut|micronaut-core-processor|4.7.6"
  "mncore|io.micronaut|micronaut-core|4.7.6"
  "mninject|io.micronaut|micronaut-inject|4.7.6"
)

# `<key>|<fixture directory name>`
FIXTURES=(
  "spring|orders-service"
  "micronaut|orders-micronaut"
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

for entry in "${FIXTURES[@]}"; do
  IFS='|' read -r key name <<<"$entry"
  (cd "$REPO/fixtures/${name}" && mvn -q -o compile >&2)
  specs+=("fixture:${key}|com.acme|${name}|-|${REPO}/fixtures/${name}/target/classes")
done

# Q12's compile. `-proc:none` and NO annotation processor on the path, so what lands in the
# class file is javac's own output and nothing Micronaut rewrote — which is exactly what a
# scan reads. Into a temporary directory: nothing here is committed as a fixture, and a
# re-run must not depend on what a previous one left behind.
ALIAS_OUT="$(mktemp -d)"
trap 'rm -rf "$ALIAS_OUT"' EXIT
alias_cp=""
for key in mnkafka mncore mninject; do
  for spec in "${specs[@]}"; do
    IFS='|' read -r k _ _ _ jar <<<"$spec"
    [ "$k" = "$key" ] && alias_cp="${alias_cp:+$alias_cp:}${jar}"
  done
done
javac -proc:none -nowarn -cp "$alias_cp" -d "$ALIAS_OUT" AliasProbe.java >&2
specs+=("fixture:alias|-|AliasProbe.java (compiled by this run)|-|${ALIAS_OUT}")

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
