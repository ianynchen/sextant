"""COVERAGE §2's matrices are generated from §5, and this is what runs the generator.

`tests/architecture/test_coverage_versions.py` names the hole in its own opening
paragraph: `scripts/coverage_matrix.py` regenerates §2 and **nothing runs it** — not
`check.sh`, not the suite — so the matrices can fall behind the checklist they summarise
without anything saying so. RUNBOOK records the lesson in another context: *an opt-in check
that nobody runs is not a net*.

W41 is the wave that makes it matter. §5 gained eight non-protocol axes (F6 §7.2), and the
generator reads EVERY `### 5.x` heading — so a section it has no column for is
indistinguishable from a section whose column was forgotten, and `render` emits only what it
was given. Both halves are checked here: that the matrices are current, and that every §5
heading is either wired to a column or declared non-protocol.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "COVERAGE.md"

# F6 §7.2's axes. The protocol axis is §5.1-§5.12 and is named by the matrices themselves;
# these are the eight that had nowhere to exist before W41.
_AXES = {
    "Language construct",
    "Shape and contract",
    "Configuration source",
    "Trace and diagram",
    "Bundle and export",
    "Question ledger",
    "Rendered document",
    "Query and findings",
}


def _generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "coverage_matrix.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )


def test_the_matrices_are_generated_from_the_checklist_they_summarise():
    """§2 is derived from §5, so a checklist row added without regenerating leaves the
    matrix asserting a spread that is no longer there."""
    result = _generator("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_section_5_heading_feeds_nothing_without_saying_so():
    """The silent half. A protocol section with no column produces no output and no error;
    the generator now refuses rather than dropping it."""
    result = _generator("--check")
    assert "no matrix column" not in result.stderr, result.stderr


def test_section_5_carries_every_axis_the_design_names():
    """F6 §7.5: *§5 carries at least the eight axes in §7.2.*

    Asserted against the HEADINGS rather than against a count, so renumbering the sections
    keeps the test true and deleting an axis does not.
    """
    headings = {
        match.group(2).strip()
        for match in re.finditer(r"^### (5\.\d+) (.+)$", DOC.read_text(), re.MULTILINE)
    }
    assert _AXES <= headings, f"missing from COVERAGE §5: {sorted(_AXES - headings)}"
