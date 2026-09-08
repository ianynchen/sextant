#!/usr/bin/env bash
# W11 — the javax/jakarta mechanical sweep (F2 §3.3).
#
# Resolves the `javax` counterpart artifacts it needs (they are not build
# dependencies of anything here) and runs the sweep, which prints the
# `## Observations` tables of `scripts/probes/w11_javax_jakarta.md` verbatim.
#
# The counterpart versions, named here rather than in the Python so a re-run
# states which artifact answered, the way every other probe's coordinate list
# does.
#
# `javax.jms-api 2.0.1` IS the last release under its coordinate — Maven Central
# reports it as both `latest` and `release`. `jaxb-api 2.3.1` is NOT: the metadata
# reports `2.4.0-b180830.0359`, a beta build. 2.3.1 is the last GA and what Boot 2
# manages, which is the claim that survives checking.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "javax.jms:javax.jms-api:2.0.1" \
  "javax.xml.bind:jaxb-api:2.3.1" \
  "jakarta.jms:jakarta.jms-api:3.1.0" \
  "jakarta.xml.bind:jakarta.xml.bind-api:4.0.1"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
