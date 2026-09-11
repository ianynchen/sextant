#!/usr/bin/env bash
# W13 — Spring Cloud Stream: cardinality, and the protocol default (F2 §3.4).
#
# Resolves the function-context artifact and its SOURCES jar — the rule this
# probe reads is an algorithm, and CP-17's convention for an algorithm is the
# method verbatim rather than a paraphrase — then runs the sweep, which prints
# the `## Observations` tables of `scripts/probes/w13_stream_binding.md`.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for target in \
  "org.springframework.cloud:spring-cloud-function-context:4.1.2" \
  "org.springframework.cloud:spring-cloud-function-context:4.1.2:jar:sources"
do
  echo "ensuring ${target}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${target}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
