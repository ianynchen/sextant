"""COVERAGE §3a states which framework versions our rules were measured at, and
this is what stops it drifting from the catalogs it describes.

`scripts/coverage_matrix.py` is the precedent and also the warning: it
regenerates §2 and NOTHING runs it — not `check.sh`, not the suite — so those
matrices can fall behind silently. RUNBOOK already records the lesson in another
context ("an opt-in check that nobody runs is not a net"). A generator without a
gate is exactly that, so this table gets its gate in the same commit that
creates it.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_measured_version_table_matches_the_catalogs():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "coverage_versions.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
