#!/usr/bin/env bash
# W53 — every verb-setting method `okhttp3.Request$Builder` declares (G-22)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in "com.squareup.okhttp3:okhttp:3.14.9" "com.squareup.okhttp3:okhttp:4.12.0"; do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
