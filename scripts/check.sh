#!/usr/bin/env bash
# Every gate, in one place, so the pre-commit hook, CI and a developer at a
# terminal all run the same checks. Ordered cheapest-first: a formatting slip
# should not wait behind the test suite.
#
#   scripts/check.sh          all gates
#   scripts/check.sh --lint   lint only, no tests (what the pre-commit hook runs)
set -euo pipefail
cd "$(dirname "$0")/.."

# Prefer the project virtual environment; fall back to whatever is on PATH so
# CI, which installs into the job's own environment, needs no special casing.
if [ -x .venv/bin/python ]; then BIN=.venv/bin/; else BIN=""; fi

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "ruff format"; "${BIN}ruff" format --check .
step "ruff lint";   "${BIN}ruff" check .
step "mypy";        "${BIN}mypy" src
step "import contracts"; "${BIN}lint-imports"

if [ "${1:-}" = "--lint" ]; then
    printf '\n\033[32mlint gates passed\033[0m\n'
    exit 0
fi

# Before pytest, not after: the end-to-end tests load the shaded jar, so a
# stale one makes them pass or fail on the previous build's extractor.
step "extractor build and tests"; (cd extractor-jvm && ./gradlew --quiet build)
step "pytest"; "${BIN}pytest" -q
printf '\n\033[32mall gates passed\033[0m\n'
