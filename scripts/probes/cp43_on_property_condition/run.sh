#!/usr/bin/env bash
# CP-43. Prints the observation table of `scripts/probes/cp43_on_property_condition.md`; nothing
# in that section is typed by hand. Reads `spring-boot-autoconfigure` out of the local Maven
# repository with `javap`; the version in every row is the jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
