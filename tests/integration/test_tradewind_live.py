"""The one opt-in integration test for the real Tradewind adapter (2N design
§1, replacing `tests/integration/test_claude_api_live.py`): "one opt-in
integration test for the real adapter, gated on `ANTHROPIC_API_KEY`
presence, skipped otherwise (and skipped in the standard suite run)" — the
identical 2K design §9 rule, carried over to the api-key auth path.

**Skipped by default, on purpose, via the mechanism this suite already has.**
`tests/cli/test_resources.py::test_the_wheel_carries_the_catalogs_and_the_extractor`
self-skips when its own precondition (a built wheel) is not on disk — the
"N skipped" a plain `pytest -q` already shows before this file exists. This
test follows the identical mechanism (`pytest.skip` at the top of the test
body, no marker, no collection-time magic) rather than inventing a second
one: whoever runs the default suite sees one MORE skip, never a network call
that quietly succeeded or failed depending on their shell's environment.

**No content assertions.** A live model's own words vary run to run and
model to model — pinning them would make this test fail on nothing but that
variance, which is the opposite of what an integration test is for. What is
asserted is the CONTRACT the port promises: a valid overlay is written, it
carries at least one accepted claim, and a transcript exists — proof the
real Tradewind loop drove itself end to end, once, against a real account.

The `--auth subscription` path (the machine's logged-in Claude Code) is
exercised separately, as a phase ACT rather than a suite fixture (2N design
§5's flight) — its results land in the phase report, not in this file: a
subscription login is a workstation's own state, not something a CI
environment or another contributor's machine can be expected to carry.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.domain.enrichment import ENRICHMENT_FILE, load_overlay

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"

# Passed to the API verbatim (2K design §3: "provider model catalogs are not
# re-implemented here"), so this is a starting point to run the test with,
# not a claim about which models exist — override it with the env var below
# once a model this default names is retired.
_DEFAULT_MODEL = "claude-haiku-4-5"


def test_tradewind_api_key_enriches_the_fixture_module_live(tmp_path: Path):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip(
            "ANTHROPIC_API_KEY not set — this is the one opt-in live test (2K design §9); "
            "set it and re-run to exercise the real tradewind api-key adapter"
        )

    module_root = tmp_path / "orders-service"
    shutil.copytree(
        FIXTURE,
        module_root,
        ignore=shutil.ignore_patterns(".sextant", ENRICHMENT_FILE),
    )
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=module_root, check=True)

    runner = CliRunner()
    for command in ("analyze", "render"):
        result = runner.invoke(cli, ["module", command, str(module_root)])
        assert result.exit_code == 0, result.output

    model = os.environ.get("SEXTANT_LIVE_TEST_MODEL", _DEFAULT_MODEL)
    result = runner.invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--agent",
            "tradewind",
            "--auth",
            "api-key",
            "--model",
            model,
        ],
    )
    assert result.exit_code == 0, result.output

    overlay = load_overlay(module_root)
    assert overlay is not None
    assert len(overlay.claims) >= 1

    transcript_path = module_root / ".sextant" / "enrich-transcript.jsonl"
    assert transcript_path.is_file()
    assert transcript_path.read_text(encoding="utf-8").strip() != ""

    # The api-key profile's own session mirror (2N design §1) — proof the
    # store landed where the adapter promises, on a real run.
    store_path = module_root / ".tradewind" / "sessions.sqlite"
    assert store_path.is_file()
