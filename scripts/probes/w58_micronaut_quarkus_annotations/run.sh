#!/usr/bin/env bash
# W58 — the annotation surface nine Micronaut and Quarkus catalogs are written against.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "io.micronaut:micronaut-http:4.7.6" \
  "io.micronaut:micronaut-http-client-core:4.7.6" \
  "io.micronaut.kafka:micronaut-kafka:5.6.0" \
  "io.micronaut.jms:micronaut-jms-core:4.2.0" \
  "io.micronaut.gcp:micronaut-gcp-pubsub:5.8.0" \
  "io.quarkus:quarkus-reactive-routes:3.17.5" \
  "io.quarkus:quarkus-reactive-routes-deployment:3.17.5"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
