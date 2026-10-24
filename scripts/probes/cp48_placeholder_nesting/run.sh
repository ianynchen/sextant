#!/usr/bin/env bash
# CP-48. Prints the observation table of `scripts/probes/cp48_placeholder_nesting.md`; nothing in
# that section is typed by hand. Reads `spring-core` out of the local Maven repository with
# `javap`; the version in every column is the jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
