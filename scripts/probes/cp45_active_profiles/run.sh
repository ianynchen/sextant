#!/usr/bin/env bash
# CP-45. Prints the observation table of `scripts/probes/cp45_active_profiles.md`; nothing in
# that section is typed by hand. Reads `spring-core` and `spring-boot` out of the local Maven
# repository with `javap`; the version in every column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
