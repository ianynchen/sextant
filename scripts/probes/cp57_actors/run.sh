#!/usr/bin/env bash
# CP-57. Prints the observation tables of `scripts/probes/cp57_actors.md`; nothing in them is
# typed by hand. Reads the Akka 2.6.21 and Pekko 1.1.3 jars the two fixtures resolve
# (`fixtures/orders-actors-{akka,pekko}/pom.xml`), runs `javap -c -p -s` on every class the
# design names, and prints each method's descriptor and whether every `areturn` returns `this`.
# Needs a JDK 21 at $JAVA_HOME, Maven, and network on the first run only. Starts no actor system.
set -euo pipefail
cd "$(dirname "$0")"
: "${JAVA_HOME:?JAVA_HOME must name the JDK whose javap the probe runs}"
if ! "$JAVA_HOME/bin/java" -version 2>&1 | head -1 | grep -q 'version "21[."]'; then
  echo "JAVA_HOME must be a JDK 21: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)" >&2
  exit 1
fi
FIX=../../../fixtures
for fam in akka pekko; do
  (cd "$FIX/orders-actors-$fam" && { mvn -q -B -o clean package >&2 || mvn -q -B clean package >&2; }
   mvn -q -B -o dependency:build-classpath -Dmdep.outputFile="$PWD/target/probe.cp" >&2)
done
# The two-`return` mapper lambda, compiled against the Pekko jars (Akka's javac output is identical).
rm -rf target-two && mkdir target-two
"$JAVA_HOME/bin/javac" --release 21 -cp "$(cat "$FIX/orders-actors-pekko/target/probe.cp")" -d target-two TwoReturns.java
if [ -x ../../../.venv/bin/python ]; then PY=../../../.venv/bin/python; else PY=python3; fi
exec "$PY" probe.py "FIX=$(cd "$FIX" && pwd)" "JAVA_HOME=$JAVA_HOME" "TWO=$PWD/target-two"
