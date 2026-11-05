#!/usr/bin/env bash
# CP-59. Prints the observation tables of `scripts/probes/cp59_dispatch.md`; nothing in them is
# typed by hand. Compiles `fixtures/orders-events` (Spring Boot 4.0.0's managed versions),
# reads the spring-context and spring-tx jars it resolves, and runs `javap` on every type the
# `spring-events` catalog names, on `java.util.EventObject`, and on the fixture's own classes.
# Then the same for CDI events: compiles `fixtures/orders-cdi-events` (Quarkus 3.17.5's managed
# versions), reads the Jakarta CDI API and ArC jars it resolves and the javax CDI API 1.0 jar
# (copied into that fixture's `target/`), for the `cdi-events` and `cdi-async-events` catalogs.
# Needs a JDK 21 at $JAVA_HOME, Maven, and network on the first run only. Starts no context.
set -euo pipefail
cd "$(dirname "$0")"
: "${JAVA_HOME:?JAVA_HOME must name the JDK whose javap the probe runs}"
if ! "$JAVA_HOME/bin/java" -version 2>&1 | head -1 | grep -q 'version "21[."]'; then
  echo "JAVA_HOME must be a JDK 21: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)" >&2
  exit 1
fi
FIX=../../../fixtures/orders-events
(cd "$FIX" && { mvn -q -B -o clean compile >&2 || mvn -q -B clean compile >&2; }
 mvn -q -B -o dependency:build-classpath -Dmdep.outputFile="$PWD/target/probe.cp" >&2)
CDI=../../../fixtures/orders-cdi-events
JAVAX=javax.enterprise:cdi-api:1.0
(cd "$CDI" && { mvn -q -B -o clean compile >&2 || mvn -q -B clean compile >&2; }
 mvn -q -B -o dependency:build-classpath -Dmdep.outputFile="$PWD/target/probe.cp" >&2
 { mvn -q -B -o dependency:copy -Dartifact="$JAVAX" -DoutputDirectory="$PWD/target/probe-javax" >&2 ||
   mvn -q -B dependency:copy -Dartifact="$JAVAX" -DoutputDirectory="$PWD/target/probe-javax" >&2; })
if [ -x ../../../.venv/bin/python ]; then PY=../../../.venv/bin/python; else PY=python3; fi
exec "$PY" probe.py "FIX=$(cd "$FIX" && pwd)" "CDI_FIX=$(cd "$CDI" && pwd)" "JAVA_HOME=$JAVA_HOME"
