#!/usr/bin/env bash
# CP-56. Prints the observation table of `scripts/probes/cp56_vertx_web.md`; nothing in that
# section is typed by hand.
#
# THE COLUMN HEADERS COME FROM THE JARS' OWN MANIFESTS (GUIDELINES §5.4, and CP-5's failure it
# exists to prevent). `probe.py` reads each jar's version out of its manifest in the local Maven
# repository and aborts if a jar states another version than the one it was fetched as; the probe
# module is rebuilt with `clean` first, so no cell can come from a stale build. Class files must be
# major version 65 (Java 21).
#
# Needs a JDK 21 at `$JAVA_HOME` (for `javac` via Maven and `javap`), Maven, and network on the
# first run only: Vert.x 4.5.10, 5.0.0 and 5.2.1, their RxJava 3 wrappers, and Mutiny 3.23.1 and 4.0.2 are cached
# in ~/.m2 afterwards. Not a test: nothing in the suite runs it. It starts no Vert.x instance.
set -euo pipefail

cd "$(dirname "$0")"

: "${JAVA_HOME:?JAVA_HOME must name the JDK whose javap and javac the probe runs}"

if ! "$JAVA_HOME/bin/java" -version 2>&1 | head -1 | grep -q 'version "21[."]'; then
  echo "JAVA_HOME must be a JDK 21: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)" >&2
  exit 1
fi

# Every jar the probe reads, fetched into ~/.m2 when it is not there yet (offline first).
fetch() {
  mvn -q -B -o org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get -Dartifact="$1" >&2 \
    || mvn -q -B org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get -Dartifact="$1" >&2
}
for v in 4.5.10 5.0.0 5.2.1; do
  for a in vertx-web vertx-web-client vertx-web-common vertx-core vertx-rx-java3; do
    fetch "io.vertx:$a:$v"
  done
done
for v in 3.23.1 4.0.2; do
  fetch "io.smallrye.reactive:smallrye-mutiny-vertx-web:$v"
  fetch "io.smallrye.reactive:smallrye-mutiny-vertx-web-client:$v"
done

echo "compiling the probe module" >&2
(cd module && { mvn -q -B -o clean package >&2 || mvn -q -B clean package >&2; })

if [ -x ../../../.venv/bin/python ]; then PY=../../../.venv/bin/python; else PY=python3; fi

exec "$PY" probe.py "CLASSES=$PWD/module/target/classes" "JAVA_HOME=$JAVA_HOME"
