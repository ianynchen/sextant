#!/usr/bin/env bash
# W53 — do the gRPC annotation FQNs two catalogs name actually exist? (G-91)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "net.devh:grpc-client-spring-boot-starter:3.1.0.RELEASE" \
  "net.devh:grpc-server-spring-boot-starter:3.1.0.RELEASE" \
  "org.springframework.grpc:spring-grpc-core:0.10.0" \
  "org.springframework.grpc:spring-grpc-spring-boot-starter:0.10.0"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
