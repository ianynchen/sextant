#!/usr/bin/env bash
# CP-47. Prints the observation table of `scripts/probes/cp47_deployment_overrides.md`; nothing
# in that section is typed by hand. Reads `spring-core`, `spring-boot` and
# `spring-boot-autoconfigure` out of the local Maven repository with `javap`; the version in
# every column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
