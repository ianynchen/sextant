#!/usr/bin/env bash
# CP-5 harness (2O Task 7 Step 0) — see ../cp5_actuator_paths.md for the
# question, the version scope, and the recorded verdict.
#
# Builds the probe app twice at the Boot versions named below, runs each on an
# embedded Tomcat, and curls one URL per row of the expectation table. Every
# line it prints is `<verb> <url> -> <status>`; the table in the .md records
# what those statuses were on the run that produced the verdict.
#
# Needs a JDK 21+, Maven, and network on first run (the Boot artifacts are
# fetched from Maven Central and cached in ~/.m2 afterwards). Not a test: no
# test in this repository runs it, and NFR-1's no-network rule is about the
# suite, not about evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

# The two versions this probe's verdict is scoped to (§5.4). The base-path
# property name and the `/actuator` default are version-scoped, so widening
# the verdict means adding a version here and re-running, never assuming.
VERSIONS=("3.5.10" "4.1.1")
PORT=18085

probe() {
  printf '%-7s %-26s -> %s\n' "$1" "$2" \
    "$(curl -s -o /dev/null -m 5 -w '%{http_code}' -X "$1" "http://localhost:$3$2")"
}

for version in "${VERSIONS[@]}"; do
  echo "=== Spring Boot $version ==="
  mvn -q -DskipTests -Dboot.version="$version" package
  jar=target/cp5-actuator-0.0.1.jar

  # Run 1 — the default base path.
  java -jar "$jar" --server.port="$PORT" >"target/run-$version-default.log" 2>&1 &
  pid=$!
  trap 'kill $pid 2>/dev/null || true' EXIT
  until curl -s -o /dev/null -m 2 "http://localhost:$PORT/actuator"; do sleep 1; done
  probe GET    /actuator/probe "$PORT"
  probe POST   /actuator/probe "$PORT"
  probe DELETE /actuator/probe "$PORT"
  probe PUT    /actuator/probe "$PORT"
  probe GET    /probe          "$PORT"
  probe GET    /actuator/empty "$PORT"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true

  # Run 2 — the base path overridden, which is the boundary this task records
  # rather than reads: nothing in Sextant reads `resolved_config` for an
  # annotation-derived row.
  java -jar "$jar" --server.port="$((PORT + 1))" \
    --management.endpoints.web.base-path=/manage >"target/run-$version-basepath.log" 2>&1 &
  pid=$!
  until curl -s -o /dev/null -m 2 "http://localhost:$((PORT + 1))/manage"; do sleep 1; done
  probe GET /manage/probe   "$((PORT + 1))"
  probe GET /actuator/probe "$((PORT + 1))"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  trap - EXIT
done
