#!/usr/bin/env bash
# W59 — which RECEIVE-shaped methods across the four messaging templates take a
# destination name at argument 0, and are therefore addressable by `single_call`.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.springframework.amqp:spring-rabbit:3.1.4" \
  "org.springframework:spring-jms:6.1.6" \
  "org.springframework.kafka:spring-kafka:3.1.4" \
  "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
