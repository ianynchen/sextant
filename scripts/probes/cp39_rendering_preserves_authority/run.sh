#!/usr/bin/env bash
# CP-39. Prints the observation table of
# `scripts/probes/cp39_rendering_preserves_authority.md`; nothing in that section is typed
# by hand. Needs `fixtures/orders-discovery` built (JDK 21, as every fixture is).
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
