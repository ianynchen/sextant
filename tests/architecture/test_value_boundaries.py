"""COVERAGE §3c states which asked positions the value walk could not answer, and
this is what stops it drifting from the snapshot it is generated from.

Spec 2026-09-22 §3d requires those boundary statements to be generated rather than
hand-written. `test_coverage_versions.py` states the rule this follows — "a generator
without a gate is exactly that", an opt-in check nobody runs — so the gate lands in the
same commit as the generator.

**What this gate does and does not catch.** It catches a document edited by hand and a
snapshot refreshed without regenerating the document. It does NOT catch an engine change
that would move the figures, because re-measuring needs the analyser over eighteen
compiled fixtures and this suite may not run Maven. That alarm is
`tests/application/test_shadow_mode.py::test_the_ask_reader_still_sees_every_position_the_shipped_catalogs_spell`,
which fails the moment a catalog gains, loses or re-spells a position — and whoever
changes one re-runs `python scripts/value_boundaries.py --measure`.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_value_boundary_table_matches_its_snapshot():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "value_boundaries.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
