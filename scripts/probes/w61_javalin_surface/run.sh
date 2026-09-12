#!/usr/bin/env bash
# W61 — which of Javalin's registration methods take the route at a position
# `single_call` can read, across the flat form (`JavalinDefaultRoutingApi`,
# reached through `Javalin` itself) and the nested `ApiBuilder` form.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "io.javalin:javalin:6.4.0"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
