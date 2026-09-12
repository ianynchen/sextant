#!/usr/bin/env bash
# W62 — which of Pekko Connectors Kafka's consumer-source, subscription-factory and
# producer-sink methods take a topic (or a subscription built from one) at a position
# `single_call` can read.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
