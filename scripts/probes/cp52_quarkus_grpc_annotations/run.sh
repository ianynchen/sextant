#!/usr/bin/env bash
# CP-52. Prints the observation table of `scripts/probes/cp52_quarkus_grpc_annotations.md`;
# nothing in that section is typed by hand. Reads `quarkus-grpc-api`, `quarkus-grpc` and
# `quarkus-grpc-deployment` out of the local Maven repository with `javap`; the version in every
# column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
