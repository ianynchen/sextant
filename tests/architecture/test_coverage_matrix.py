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
    # Q3 — the four surfaces ruled out of v1. `Kafka Streams` shipped (`G-31`, w60)
    # and moved to §5.8, so its row is there now rather than in §5.21 — `_names`
    # matches anywhere in the document, so this still enforces a support level.
    "Spring Cloud Gateway": "§5.21",
    "Kafka Streams": "§5.8",
    "Programmatic Jakarta WebSocket registration": "§5.21",
    "@DgsEntityFetcher": "§5.21",
    # F1 — the five attributes deliberately not read.
    "StackMapTable": "§5.22",
    "LocalVariableTypeTable": "§5.22",
    "Module": "§5.22",
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

# The items whose name IS a first-cell value, so a substring elsewhere in the row must not
# satisfy them. Every F1 attribute is one; `Module` is why the distinction exists.
_FIRST_CELL_ITEMS = frozenset(
    {"StackMapTable", "LocalVariableTypeTable", "Module", "ModulePackages", "ModuleMainClass"}
)


def _names(row: str, item: str) -> bool:
    """Whether one COVERAGE row names `item`.

    An F1 attribute is matched on the whole FIRST CELL, never as a substring: `Module` is a
    substring of `ModulePackages` and `ModuleMainClass`, so a substring search let its own
    row be deleted while its two neighbours kept the check green. That is why `Module` was
    missing from the required list for a commit — and why a first attempt at this fix still
    passed, because the fallback it kept was the substring search again (W42's review).

    Everything else is matched anywhere in the row, because those name a construct a cell
    DESCRIBES — `suspend fun`, `$default`, a gap id — rather than a cell's own value.
    """
    if item in _FIRST_CELL_ITEMS:
        cells = [cell.strip().strip("`*") for cell in row.split("|")]
        return len(cells) > 1 and cells[1] == item
    return item in row


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
        # Matched on the FIRST CELL, compared whole. `Module` is a substring of
        # `ModulePackages` and `ModuleMainClass`, so a substring search let its own row be
        # deleted while its two neighbours kept the check green — which is why `Module` was
        # missing from this list for a commit, and why a first attempt at this fix still
        # passed: the fallback it kept was the substring search again (W42's review).
        #
        # An item that is not a first-cell value — `suspend fun`, `$default` — is matched
        # anywhere in the row, because those name a construct a cell DESCRIBES rather than a
        # cell's own value.
        naming = [row for row in rows if _names(row, item)]
        carried = [row for row in naming if any(level in row for level in _LEVELS)]
        if not carried:
            named = bool(naming)
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


# --- the per-framework rollup (2026-09-18) -------------------------------------------------
#
# The question "is Spring REST inbound complete?" could not be answered from COVERAGE: §2
# scores a LANGUAGE per protocol and §5 lists FORMS, and nothing rolled the forms up to the
# framework a reader actually asks about. The rollup under each `### 5.1`–`### 5.12` heading
# is generated from the `Framework` column of the rows below it plus the register's open
# ids, so it cannot drift; these tests pin the pieces `--check` alone would not name.

_PROTOCOL_SECTIONS = [f"5.{n}" for n in range(1, 13)]


def test_every_protocol_section_carries_a_generated_framework_rollup():
    text = DOC.read_text()
    for number in _PROTOCOL_SECTIONS:
        assert f"<!-- BEGIN GENERATED: frameworks {number} -->" in text, number
        assert f"<!-- END GENERATED: frameworks {number} -->" in text, number


def test_every_java_row_in_a_protocol_section_names_a_declared_framework():
    """A row tagged with a framework the target list does not declare is a rollup row nobody
    can find, and a target framework with no row is the `✗ unsupported` line the rollup
    exists to show — so the two must agree, and the generator refuses when they do not."""
    assert _matrix().undeclared_frameworks(DOC.read_text()) == []


def test_every_open_register_id_on_a_protocol_row_is_mapped_to_a_framework():
    """The rollup's `Missing` column reads the ```delivery block. An id it cannot place
    under a framework would vanish from every rollup while still blocking the row."""
    assert _matrix().unmapped_items() == []


def test_the_rollup_status_rule():
    """`✅ full` only when every row is shipped AND no open id names the framework;
    `✗ unsupported` when the target list names a framework with no row at all."""
    matrix = _matrix()
    from collections import Counter

    assert matrix.rollup_status(Counter({"shipped": 3}), []) == ("✅ full", "—")
    assert matrix.rollup_status(Counter({"shipped": 3}), ["quarkus-jaxrs"]) == (
        "◐ partial",
        "`quarkus-jaxrs`",
    )
    assert matrix.rollup_status(Counter({"shipped": 2, "A": 1, "partial": 1}), []) == (
        "◐ partial",
        "not shipped: 1 at A; 1 limited",
    )
    assert matrix.rollup_status(Counter(), []) == ("✗ unsupported", "no row yet")
    assert matrix.rollup_status(Counter({"shipped": 1, "boundary": 3}), []) == (
        "✅ full",
        "3 stated boundaries",
    )
    assert matrix.rollup_status(Counter({"shipped": 1, "boundary": 1}), ["x"]) == (
        "◐ partial",
        "`x`; 1 stated boundary",
    )
    assert matrix.classify_rollup("**Boundary — derives nothing.** …") == "boundary"
    assert matrix.classify("**supported** (3.6.2, w60)") == "shipped"


def test_spring_rest_inbound_reads_as_the_rollup_says():
    """The row that started this: Spring MVC / WebFlux annotations are shipped end to end,
    and the rollup must say so in one line a reader can find."""
    text = DOC.read_text()
    start = text.index("<!-- BEGIN GENERATED: frameworks 5.1 -->")
    end = text.index("<!-- END GENERATED: frameworks 5.1 -->", start)
    block = text[start:end]
    spring = [
        line
        for line in block.splitlines()
        if line.startswith("| Spring MVC / WebFlux (annotations) |")
    ]
    assert len(spring) == 1, block
    # Partial today for exactly two reasons a reader can act on, both named in the line:
    # the `@ConditionalOnProperty` / `@Profile` row is tier C, and the register holds
    # `conditional-controllers` open against it. Everything else on that line is shipped.
    assert "| ◐ partial |" in spring[0], spring[0]
    assert "`conditional-controllers`" in spring[0], spring[0]
    assert "not shipped: 1 at C" in spring[0], spring[0]
