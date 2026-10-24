#!/usr/bin/env bash
# CP-50. Prints the observation table of `scripts/probes/cp50_quarkus_channel_wiring.md`; nothing
# in that section is typed by hand. Reads `quarkus-messaging-deployment` and `quarkus-messaging`
# (3.17.5 and 3.40.1.1) and `quarkus-core` out of the local Maven repository with `javap`; the
# version in every column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
