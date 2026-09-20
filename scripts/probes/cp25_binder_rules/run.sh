#!/usr/bin/env bash
# CP-25 harness — see ../cp25_binder_rules.md for the questions, the version scope
# and the verdicts. Row 1 is Javalin's `ApiBuilder` guard; rows 2–12 are the
# parameter-annotation binder rules of spec 2026-09-19 §5b (spring-web/spring-core/
# spring-webmvc 6.1.6, micronaut 4.7.6, RESTEasy Reactive and reactive-routes
# 3.17.5, vertx-core 4.5.11, jakarta.ws.rs-api 3.1.0) plus the `defaultValue`
# element_value_pairs check, which is the one cell that COMPILES something: a
# two-method Java sample under `javac` against spring-web, then `javap -v`. Rows
# 13–17 are the §5c/§5d rows: Spring's expression parse, Javalin's `Context`
# read/set overloads and `Validator.get()`, and the Servlet API's reads on Tomcat
# 10.1.50 (`jakarta`) and 9.0.121 (`javax`) — the two containers CP-9 measured. Row
# 18 is §5b again: the second spelling Micronaut's binders retry an unwritten name
# under (`NameUtils.hyphenate`, the header binder's `capitalize`).
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE JAR'S OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads the
# jar's own manifest `Implementation-Version` rather than trusting the coordinate
# that resolved it, and aborts when the jar reports a version other than the one
# the run expected.
#
# Needs a JDK (for `javac` and `javap`), and Maven plus network on first run
# only; the jars are cached in ~/.m2 afterwards. Nothing framework-side is
# executed — every cell but row 5 is a `javap` read of a class file, and row 5
# compiles a sample and reads the class file it produced. Not a test: nothing in
# the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<key>|<groupId>|<artifactId>|<version>`
ARTIFACTS=(
  "javalin|io.javalin|javalin|6.4.0"
  "spring-web|org.springframework|spring-web|6.1.6"
  "spring-core|org.springframework|spring-core|6.1.6"
  "spring-webmvc|org.springframework|spring-webmvc|6.1.6"
  "micronaut-http|io.micronaut|micronaut-http|4.7.6"
  "micronaut-core|io.micronaut|micronaut-core|4.7.6"
  "micronaut-router|io.micronaut|micronaut-router|4.7.6"
  "micronaut-core-processor|io.micronaut|micronaut-core-processor|4.7.6"
  "resteasy-reactive|io.quarkus.resteasy.reactive|resteasy-reactive|3.17.5"
  "resteasy-reactive-common|io.quarkus.resteasy.reactive|resteasy-reactive-common|3.17.5"
  "jaxrs-api|jakarta.ws.rs|jakarta.ws.rs-api|3.1.0"
  "reactive-routes|io.quarkus|quarkus-reactive-routes|3.17.5"
  "reactive-routes-deployment|io.quarkus|quarkus-reactive-routes-deployment|3.17.5"
  "vertx-core|io.vertx|vertx-core|4.5.11"
  "tomcat-jakarta|org.apache.tomcat.embed|tomcat-embed-core|10.1.50"
  "tomcat-javax|org.apache.tomcat.embed|tomcat-embed-core|9.0.121"
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

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
