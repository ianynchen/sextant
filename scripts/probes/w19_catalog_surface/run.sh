#!/usr/bin/env bash
# W19 — the per-catalog enumeration pass (F2 §3.8): what does each framework
# declare, and how much of it does the catalog read?
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.springframework:spring-jms:6.1.6" \
  "org.springframework.amqp:spring-amqp:3.1.4" \
  "org.springframework.amqp:spring-rabbit:3.1.4" \
  "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1" \
  "com.google.cloud:spring-cloud-gcp-pubsub:5.1.2" \
  "org.springframework:spring-webflux:6.1.6" \
  "org.springframework:spring-messaging:6.1.6" \
  "software.amazon.awssdk:sqs:2.25.31"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
