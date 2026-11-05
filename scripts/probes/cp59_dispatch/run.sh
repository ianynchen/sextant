#!/usr/bin/env bash
# CP-59. Prints the observation tables of `scripts/probes/cp59_dispatch.md`; nothing in them is
# typed by hand. Compiles `fixtures/orders-events` (Spring Boot 4.0.0's managed versions),
# reads the spring-context and spring-tx jars it resolves, and runs `javap` on every type the
# `spring-events` catalog names, on `java.util.EventObject`, and on the fixture's own classes.
# Then the same for CDI events: compiles `fixtures/orders-cdi-events` (Quarkus 3.17.5's managed
# versions), reads the Jakarta CDI API and ArC jars it resolves and the javax CDI API 1.0 and 2.0
# jars (copied into that fixture's `target/`), for the `cdi-events` and `cdi-async-events`
# catalogs.
# Then Java blocking queues: compiles `fixtures/orders-queues` and a generated class calling each
# declared method through each declared owner, and runs `javap` on the JDK's queue types, for the
# `jdk-blocking-queue` catalog (the JDK is no jar with a manifest: its version is the one the
# running `java` reports as `java.version`).
# Then Kotlin channels and flows: compiles `fixtures/orders-kotlin-channels` and the probe module
# `kotlin-owners` (each declared call through each owner type), both by kotlinc 2.4.20 against
# kotlinx-coroutines-core-jvm 1.11.0, and runs `javap` on the coroutines jar, on kotlin-stdlib's
# `SpillingKt`, and on both modules' classes, for the `kotlinx-channels` and `kotlinx-flows`
# catalogs.
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
copy() {  # copy <coordinate> <directory>: offline first, online once
  mvn -q -B -o dependency:copy -Dartifact="$1" -DoutputDirectory="$PWD/target/$2" >&2 ||
    mvn -q -B dependency:copy -Dartifact="$1" -DoutputDirectory="$PWD/target/$2" >&2
}
(cd "$CDI" && { mvn -q -B -o clean compile >&2 || mvn -q -B clean compile >&2; }
 mvn -q -B -o dependency:build-classpath -Dmdep.outputFile="$PWD/target/probe.cp" >&2
 copy javax.enterprise:cdi-api:1.0 probe-javax
 copy javax.enterprise:cdi-api:2.0 probe-javax2)
QUEUES=../../../fixtures/orders-queues
(cd "$QUEUES" && { mvn -q -B -o clean compile >&2 || mvn -q -B clean compile >&2; }
 mvn -q -B -o dependency:build-classpath -Dmdep.outputFile="$PWD/target/probe.cp" >&2)
KOTLIN=../../../fixtures/orders-kotlin-channels
(cd "$KOTLIN" && { mvn -q -B -o clean compile >&2 || mvn -q -B clean compile >&2; }
 mvn -q -B -o dependency:build-classpath -Dmdep.outputFile="$PWD/target/probe.cp" >&2)
(cd kotlin-owners && { mvn -q -B -o clean compile >&2 || mvn -q -B clean compile >&2; })
if [ -x ../../../.venv/bin/python ]; then PY=../../../.venv/bin/python; else PY=python3; fi
exec "$PY" probe.py "FIX=$(cd "$FIX" && pwd)" "CDI_FIX=$(cd "$CDI" && pwd)" \
  "QUEUES_FIX=$(cd "$QUEUES" && pwd)" "KOTLIN_FIX=$(cd "$KOTLIN" && pwd)" \
  "OWNERS=$PWD/kotlin-owners/target/classes" "JAVA_HOME=$JAVA_HOME"
