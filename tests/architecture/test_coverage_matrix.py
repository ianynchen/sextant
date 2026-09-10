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

import importlib.util
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


def _matrix():
    """`scripts/coverage_matrix.py` as a module. It lives outside the package, so it is
    loaded by path rather than imported — the same thing `--check` runs."""
    spec = importlib.util.spec_from_file_location(
        "coverage_matrix", REPO / "scripts" / "coverage_matrix.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    the generator refuses rather than dropping it.

    Called DIRECTLY rather than through `--check`, so this can fail on its own: `main`
    returns on the first guard that trips, which made the CLI form fail only in company
    with the staleness test and never for its own reason.
    """
    assert _matrix().unwired(_matrix().parse(DOC.read_text())[1]) == []


def test_no_row_in_a_non_protocol_section_is_counted_as_a_language():
    """The half W41 claimed and did not have.

    A row is counted by its FIRST CELL wherever that cell names a language, in every
    `### 5.x` section — so `| Java | … |` written under an axis section is counted into a
    matrix cell that has no column and then dropped by `render`. Declaring the section
    non-protocol does not stop that; only looking at the row does.
    """
    assert _matrix().misfiled(DOC.read_text()) == []


def test_section_5_carries_every_axis_the_design_names():
    """F6 §7.5: *§5 carries at least the eight axes in §7.2.*

    Asserted against the HEADINGS rather than against a count, so renumbering the sections
    keeps the test true and deleting an axis does not.
    """
    text = DOC.read_text()
    headings = {
        match.group(2).strip() for match in re.finditer(r"^### (5\.\d+) (.+)$", text, re.MULTILINE)
    }
    assert _AXES <= headings, f"missing from COVERAGE §5: {sorted(_AXES - headings)}"
    # And each axis holds a TABLE, not only a heading. Asserted because the first version
    # matched heading strings alone: deleting §5.18's whole table and leaving its title
    # kept every test green, which is a section that exists and enumerates nothing.
    rows = _matrix().parse(text)[0]
    sections = re.split(r"^### 5\.\d+ ", text, flags=re.MULTILINE)[1:]
    empty = [
        section.split("\n", 1)[0].strip()
        for section in sections
        if section.split("\n", 1)[0].strip() in _AXES
        and not any(line.startswith("|") for line in section.splitlines())
    ]
    assert empty == [], f"axis sections in COVERAGE §5 with no table: {empty}"
    del rows
