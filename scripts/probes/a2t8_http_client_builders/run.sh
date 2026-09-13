#!/usr/bin/env bash
# A2 Task 8 — the JDK `HttpRequest.Builder` and Apache HttpClient 5 request surfaces
# (`jdk-httpclient`, `apache-httpclient`; spec §12).
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.apache.httpcomponents.core5:httpcore5:5.2.4" \
  "org.apache.httpcomponents.client5:httpclient5:5.2.3"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
