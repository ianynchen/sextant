#!/usr/bin/env bash
# W14 — do class-level and method-level listeners register independently? (F2 §3.5)
#
# Resolves the three messaging libraries and runs the sweep, which prints the
# `## Observations` tables of `scripts/probes/w14_listener_registration.md`
# verbatim. The versions are the ones the fixture poms pin, so a verdict here and
# a verdict from the fixture describe the same libraries.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.springframework.kafka:spring-kafka:3.1.4" \
  "org.springframework.amqp:spring-rabbit:3.1.4" \
  "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
