#!/usr/bin/env bash
# CP-51. Prints the observation tables of `scripts/probes/cp51_smallrye_connectors.md`; nothing in
# that section is typed by hand. Reads each `smallrye-reactive-messaging-<connector>` jar (and the
# `-api` jar) out of the local Maven repository with `javap` and `jdeps`, and the
# `quarkus-messaging-*` poms beside them; the version in every column is each jar's own manifest.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
