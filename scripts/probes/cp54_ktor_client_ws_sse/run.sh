#!/usr/bin/env bash
# CP-54. Prints the observation table of `scripts/probes/cp54_ktor_client_ws_sse.md`; nothing in
# that section is typed by hand.
#
# THE COLUMN HEADER COMES FROM THE JARS' OWN MANIFESTS AND FROM THE PROCESS THAT RAN KTOR
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads each Ktor jar's
# `Implementation-Version` out of the local Maven repository, and aborts if the process that ran
# Ktor's `DefaultRequest` reports another; the probe module is rebuilt with `clean` first, so no
# cell can come from a stale build. `EXPECTED_KOTLIN_MV` is the metadata version kotlinc 2.4.20
# writes into a class file; a disagreement aborts the run.
#
# Needs a JDK at `$JAVA_HOME` (for `javap` and `java`), Maven, and network on the first run only
# (Ktor 3.6.0, Kotlin 2.4.20 and ktor-client-mock are cached in ~/.m2 afterwards). Not a test:
# nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

: "${JAVA_HOME:?JAVA_HOME must name the JDK whose javap and java the probe runs}"
EXPECTED_KOTLIN_MV=2.4.0

# The probe module is compiled for Java 21 (kotlin-maven-plugin `jvmTarget`), and `probe.py`
# checks the class files' major version; the JDK that runs it has to be 21 as well.
if ! "$JAVA_HOME/bin/java" -version 2>&1 | head -1 | grep -q 'version "21[."]'; then
  echo "JAVA_HOME must be a JDK 21: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)" >&2
  exit 1
fi

echo "compiling the probe module" >&2
(cd module \
  && { mvn -q -B -o clean package >&2 || mvn -q -B clean package >&2; } \
  && { mvn -q -B -o dependency:build-classpath -Dmdep.outputFile=target/classpath.txt >&2 \
       || mvn -q -B dependency:build-classpath -Dmdep.outputFile=target/classpath.txt >&2; })

if [ -x ../../../.venv/bin/python ]; then PY=../../../.venv/bin/python; else PY=python3; fi

exec "$PY" probe.py \
  "CLASSES=$PWD/module/target/classes" \
  "CLASSPATH=$PWD/module/target/classpath.txt" \
  "JAVA_HOME=$JAVA_HOME" \
  "EXPECTED_KOTLIN_MV=$EXPECTED_KOTLIN_MV"
