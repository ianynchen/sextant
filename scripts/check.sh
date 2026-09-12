#!/usr/bin/env bash
# Every gate, in one place, so the pre-commit hook, CI and a developer at a
# terminal all run the same checks. Ordered cheapest-first: a formatting slip
# should not wait behind the test suite.
#
#   scripts/check.sh          all gates
#   scripts/check.sh --lint   lint only, no tests (what the pre-commit hook runs)
#   scripts/check.sh --guards guard discrimination only — NOT part of the default
#                             run, because it spawns a pytest per guard and its
#                             failures mean something different from a test's:
#                             a near-miss that no longer notices the loss of the
#                             guard it names. `scripts/guard_check.py` has the
#                             whole story.
set -euo pipefail
cd "$(dirname "$0")/.."

# Prefer the project virtual environment; fall back to whatever is on PATH so
# CI, which installs into the job's own environment, needs no special casing.
if [ -x .venv/bin/python ]; then BIN=.venv/bin/; else BIN=""; fi

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

# Before the lint gates rather than after them: this answers a question about
# the test suite, not about this tree's formatting, and somebody asking it
# should not have to make the tree lint-clean first.
if [ "${1:-}" = "--guards" ]; then
    step "guard discrimination"; "${BIN}python" scripts/guard_check.py
    exit 0
fi

# `--tests` runs ONLY the test stage: CI runs each stage as its own workflow step so a
# lint failure shows in seconds and the pytest log streams on its own while it runs
# (docs/performance.md P-2). Locally, no flag runs every stage in one go, as before.
if [ "${1:-}" = "--tests" ]; then
    step "pytest"; "${BIN}pytest" -q -n 4 --dist loadfile --durations=20 ${CI:+--maxfail=1}
    printf '\n\033[32mtest gate passed\033[0m\n'
    exit 0
fi
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
if [ "${1:-}" = "--extractor" ]; then
    printf '\n\033[32mlint and extractor gates passed\033[0m\n'
    exit 0
fi
# Parallel, by FILE. `--dist loadfile` keeps every test in a file on one worker, which
# is what lets the module-scoped shared-workspace fixtures run once per file rather than
# once per worker — and what keeps the two determinism tests, each of which needs its own
# two runs, from racing another worker for the same fixture `target/`.
#
# MEASURED 2026-09-11, same 2997 tests, zero failures either way:
#   serial        15:57
#   -n 4 loadfile  5:10   (4 to match the GitHub runner's cores, not this machine's)
#
# `-n auto` would read the core count, and on a 10-core laptop it hides the CI number.
# 4 is what CI has, so 4 is what is measured here.
#
# `--durations=20` because the next stall has to be NAMED, not guessed at: PR #20's run
# 34665949923 sat at 78% for nineteen minutes and the log could not say which tests those
# were. `--maxfail=1` is CI's, not the laptop's: a run that is going to fail should say so
# in minutes, not after the whole suite (ruled by the user 2026-09-12, "I can't wait until
# 40 minutes later to see the CI job failed"). Locally the full picture is worth the wait.
step "pytest"; "${BIN}pytest" -q -n 4 --dist loadfile --durations=20 ${CI:+--maxfail=1}
printf '\n\033[32mall gates passed\033[0m\n'
