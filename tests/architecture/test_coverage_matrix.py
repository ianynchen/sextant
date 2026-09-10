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

# F6 §7.5's third clause: *every item named in Q2, Q3, Q4 and F1's not-read set appears with
# a support level.* Named here rather than counted, so deleting one fails and renumbering the
# sections does not. The strings are what the design itself names each item by.
_MUST_BE_ENUMERATED = {
    # Q2 — the Kotlin boundaries.
    "suspend fun": "§5.13",
    "extension functions": "§5.13",
    "$default": "§5.13",
    "DefaultImpls": "§5.13",
    # Q3 — the four surfaces ruled out of v1.
    "Spring Cloud Gateway": "§5.21",
    "Kafka Streams": "§5.21",
    "Programmatic Jakarta WebSocket registration": "§5.21",
    "@DgsEntityFetcher": "§5.21",
    # F1 — the five attributes deliberately not read.
    "StackMapTable": "§5.22",
    "LocalVariableTypeTable": "§5.22",
    "ModulePackages": "§5.22",
    "ModuleMainClass": "§5.22",
    # Q4 — the declared slices, by the gap each answers.
    "G-44": "§5.23",
    "G-37": "§5.23",
    "G-43": "§5.23",
    "G-45": "§5.23",
    "G-47": "§5.23",
    "G-41": "§5.23",
}

# The three levels §7.2 declares. A row naming an item and no level is the state this rule
# exists to refuse — it reads as coverage while committing to nothing.
_LEVELS = ("**supported**", "**partially supported**", "**unsupported")


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


def test_every_item_the_design_names_carries_a_support_level():
    """F6 §7.5: *every item named in Q2, Q3, Q4 and F1's not-read set appears with a support
    level* (W42).

    Twelve committed items were enumerated NOWHERE before W41, which is how a reader came to
    have no way of looking one up. Naming them in a document is half the fix; the other half
    is that each row COMMITS — `supported`, `partially supported` or `unsupported` — because
    a row that names an item and states no level reads as coverage while promising nothing.

    Checked against the row rather than the section: the item must appear on a line that also
    carries one of the three levels.
    """
    text = DOC.read_text()
    rows = [line for line in text.splitlines() if line.startswith("|")]
    missing = []
    for item, section in sorted(_MUST_BE_ENUMERATED.items()):
        carried = [row for row in rows if item in row and any(level in row for level in _LEVELS)]
        if not carried:
            named = any(item in row for row in rows)
            missing.append(
                f"{item} ({section}): "
                + ("named in a row with no support level" if named else "not enumerated at all")
            )
    assert missing == [], "COVERAGE §5 items with no support level:\n  " + "\n  ".join(missing)


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
