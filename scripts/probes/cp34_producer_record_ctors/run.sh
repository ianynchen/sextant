#!/usr/bin/env bash
# CP-34 — which argument of each `ProducerRecord` constructor is the VALUE, and
# whether `payload_ctor_arg: "last"` lands on it.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.apache.kafka:kafka-clients:3.6.2"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
