#!/usr/bin/env bash
# OI-64 — does constructing a `Subscriber` subscribe to anything, and does Spring
# start one declared as a `@Bean`?
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "com.google.cloud:google-cloud-pubsub:1.127.3" \
  "com.google.api:api-common:2.31.0" \
  "com.google.cloud:spring-cloud-gcp-pubsub:5.1.2"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
