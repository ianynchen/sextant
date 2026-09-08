#!/usr/bin/env bash
# W18 — which PubSubTemplate methods consume, and which does the catalog read? (F2 §3.9)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in "com.google.cloud:spring-cloud-gcp-pubsub:5.1.2"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
