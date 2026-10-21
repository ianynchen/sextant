#!/usr/bin/env bash
# CP-40. Prints the observation table of `scripts/probes/cp40_strip_prefix.md`; nothing in
# that section is typed by hand. Needs the gateway artifact in the local Maven repository
# and `javap` on PATH.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
