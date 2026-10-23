#!/usr/bin/env bash
# CP-46. Prints the observation table of `scripts/probes/cp46_repository_interface_beans.md`;
# nothing in that section is typed by hand. Reads `spring-data-commons`, `spring-context` and
# `spring-core` out of the local Maven repository with `javap`; the version in every column is
# each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
