#!/usr/bin/env bash
# W16 — what tells a Spring RSocket controller from a STOMP one? (F2 §3.6)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.springframework:spring-messaging:6.1.6" \
  "org.springframework.boot:spring-boot-autoconfigure:3.2.5" \
  "org.springframework:spring-websocket:6.1.6" \
  "io.rsocket:rsocket-core:1.1.4"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
