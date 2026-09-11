#!/usr/bin/env bash
# W17 — does a WebFlux `@Controller` derive? (F2 §3.7, G-38)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

# Compile-time classpath for the four controller shapes, and the two jars whose
# `isHandler` predicates the first question compares. `@Controller` lives in
# spring-context, the mapping annotations in spring-web, `Mono` in reactor-core.
for artifact in \
  "org.springframework:spring-context:6.1.6" \
  "org.springframework:spring-core:6.1.6" \
  "org.springframework:spring-web:6.1.6" \
  "org.springframework:spring-webmvc:6.1.6" \
  "org.springframework:spring-webflux:6.1.6" \
  "org.springframework:spring-webmvc:7.0.2" \
  "org.springframework:spring-webflux:7.0.2" \
  "io.projectreactor:reactor-core:3.6.5" \
  "org.reactivestreams:reactive-streams:1.0.4"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
