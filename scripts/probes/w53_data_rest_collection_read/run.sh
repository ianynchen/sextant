#!/usr/bin/env bash
# W53 — does every exposed Spring Data repository serve a collection GET?
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.springframework.data:spring-data-rest-core:5.0.1" \
  "org.springframework.data:spring-data-commons:3.2.5" \
  "org.springframework.data:spring-data-commons:4.0.1" \
  "org.springframework.data:spring-data-jpa:4.1.1"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
