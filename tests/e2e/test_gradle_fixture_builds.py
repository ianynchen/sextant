"""The one opt-in integration test per build system for Gradle (2M design
§4): every other Gradle test in this suite drives `GradleDetector` from a
CAPTURED init-script document (`tests/ingress/gradle-captures/`) — this is
the one place the real `./gradlew` actually runs, offline, over
`fixtures/gradle-orders`, through `sextant module analyze` end to end.

**Self-skipping, the same mechanism the suite already has** (no marker, no
collection-time magic — `tests/integration/test_tradewind_live.py`'s own
docstring names the precedent): if the offline run fails because the
wrapper distribution or the fixture's dependencies are not already in the
local Gradle caches, this test skips rather than failing red on an
unprimed machine. CI primes both in a dedicated step (`.github/workflows/
pr.yml`, beside the Maven priming step) before the suite runs, so it never
skips there. `GradleDetector` itself is what tells the difference — its own
cold-start/offline-refusal classification is DR-6's "Gradle's own words",
read back out of the `ClickException` this test's own failed attempt
raises, never a guess about whether a machine is primed.

**Stale-workspace guard, mirroring `tests/conftest.py`'s session fixture**:
that fixture guards a build-once precondition so a stale local-repository
jar never masks a real failure; this test guards the analogous risk for a
repeatable local run — a `.sextant/` workspace or `modules.json` left behind
by an earlier (possibly interrupted) run of THIS test must not let a stale
`analyzed: true` row or an old endpoint count stand in for what this run
actually produced. Both are removed before analysis runs, never after.
"""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.ingress.detect.gradle import _OFFLINE_REFUSAL_SUBSTRING

FIXTURE = Path(__file__).parents[2] / "fixtures" / "gradle-orders"


def _clear_stale_workspaces() -> None:
    for module_dir in (FIXTURE, FIXTURE / "service-app", FIXTURE / "pricing-lib"):
        shutil.rmtree(module_dir / ".sextant", ignore_errors=True)


def test_the_real_wrapper_analyzes_both_modules_and_pins_three_endpoints():
    _clear_stale_workspaces()
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "analyze", str(FIXTURE)])

    if result.exit_code != 0:
        message = str(result.exception)
        if "Gradle distribution not present" in message or _OFFLINE_REFUSAL_SUBSTRING in message:
            pytest.skip(
                "the Gradle wrapper distribution or fixtures/gradle-orders's dependencies "
                "are not primed on this machine — this is the one opt-in Gradle integration "
                "test (2M design §4); run `./gradlew build` once inside fixtures/gradle-orders "
                "with network access (or see the CI prime step in .github/workflows/pr.yml) "
                f"to warm them first. Gradle said: {message}"
            )
        raise AssertionError(f"module analyze failed: {result.output}\n{message}")

    # `pricing-lib` applies `maven-publish` — Gradle's own publishing
    # evidence makes it `kind == "library"` (2M design §2's Gradle-only
    # deviation), which the CLI's `_skip_reason` gate skips outright: no
    # classes to scan, no workspace of its own.
    assert "skipped pricing-lib (com.acme:pricing-lib): kind is library" in result.output
    # `service-app` carries no such evidence, so it is `undetermined` and
    # still analyzed (2M design §2's post-fix-round-1 kind gate) — its three
    # Spring MVC endpoints are what this test exists to pin end to end,
    # through the real wrapper, not a capture.
    assert "analyzed service-app (com.acme:service-app): 3 endpoints" in result.output

    modules_path = FIXTURE / ".sextant" / "modules.json"
    assert modules_path.is_file()
    assert not (FIXTURE / "pricing-lib" / ".sextant" / "metadata.json").exists()
    assert (FIXTURE / "service-app" / ".sextant" / "metadata.json").is_file()
