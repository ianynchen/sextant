#!/usr/bin/env bash
# W60 — which topic-addressing methods across Kafka Streams' four builder/topology
# types take the topic at a position `single_call` can read, and which do not.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.apache.kafka:kafka-streams:3.6.2"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
