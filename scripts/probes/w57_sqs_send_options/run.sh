#!/usr/bin/env bash
# W57 — what does `SqsSendOptions` declare, and at which versions? (OI-74)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1" \
  "io.awspring.cloud:spring-cloud-aws-sqs:4.1.1"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
