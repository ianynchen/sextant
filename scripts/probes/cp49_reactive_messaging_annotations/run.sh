#!/usr/bin/env bash
# CP-49. Prints the observation table of `scripts/probes/cp49_reactive_messaging_annotations.md`;
# nothing in that section is typed by hand. Reads `microprofile-reactive-messaging-api`,
# `smallrye-reactive-messaging-{api,provider,kafka}` and `quarkus-messaging(-deployment)` out of
# the local Maven repository with `javap`; the version in every column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
