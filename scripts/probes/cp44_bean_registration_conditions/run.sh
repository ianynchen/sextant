#!/usr/bin/env bash
# CP-44. Prints the observation table of `scripts/probes/cp44_bean_registration_conditions.md`;
# nothing in that section is typed by hand. Reads `spring-context`, `spring-beans`, `spring-web`,
# `spring-core` and `spring-boot-autoconfigure` out of the local Maven repository with `javap`;
# the version in every column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
