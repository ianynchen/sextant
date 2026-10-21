#!/usr/bin/env bash
# CP-41. Prints the observation table of `scripts/probes/cp41_merge_candidates.md`; nothing
# in that section is typed by hand. Needs `fixtures/orders-service` built (JDK 21, as every
# fixture is) and the extractor jar at `src/sextant/extractor-jvm/sextant-extractor.jar`.
# `examples/apollo` is measured too where it is cloned and built, and reported absent otherwise.
set -euo pipefail
exec "${PYTHON:-.venv/bin/python}" "$(dirname "$0")/probe.py"
