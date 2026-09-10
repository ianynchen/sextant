"""Every markdown table row has as many cells as its header (F6 §7.3, W40).

## Why a test rather than a proofread

A row with an extra cell does not look broken in a diff and does not look broken in a plain
text editor — every cell is there, on one line, separated by pipes. It looks broken only in
a RENDERER, which drops what will not fit: a five-cell row under a four-column header loses
its LAST cell, and in these documents the last cell is the status. Eleven Java rows in
`COVERAGE.md` were reporting their delivery state to nobody, including 2O Task 9's record,
`OI-1`'s record, and a row whose whole content is *"none of them is read"*.

The other three shapes it catches, each found by this test on its first run:

* a row with no trailing pipe (`PROJECT.md`'s 2Q row) — its last cell is not a cell;
* a row missing a cell outright (`M07`'s open-decision row) — the column reads empty for
  that row and shifted for a reader scanning down it;
* a row wrapped across two source lines — markdown ends a row at the newline, so the
  continuation renders as a paragraph UNDER the table and the row loses its cell.

## Why the cell count is not `line.count("|")`

A pipe inside a code span is text, and these documents are full of them —
`` `a|b` ``, `` `Ljava/lang/String;` `` beside a `|`, a regular expression with an
alternation. Counting naively reported 1,961 malformed rows where there are none; the
counter here walks the row and tracks backtick spans and backslash escapes, which is what a
renderer does.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]

# Every markdown file the repository ships, including the ones under `docs/superpowers`:
# a plan or a spec whose table renders wrong misleads exactly as a component document does,
# and the plan's own rows are where this project records what it delivered.
_MARKDOWN = sorted(
    path
    for path in REPO.rglob("*.md")
    if ".venv" not in path.parts
    and "node_modules" not in path.parts
    and "examples" not in path.parts
)

_SEPARATOR = re.compile(r"\s*\|[\s:|-]+\|\s*")


def _cells(row: str) -> int:
    """How many cells a renderer reads in `row`.

    A `|` inside a backtick span is text, and a `\\|` is an escaped literal — neither
    divides a cell. The leading and trailing pipes are delimiters, so N pipes make N-1
    cells.
    """
    row = row.strip()
    pipes, in_code, depth, index = 0, False, 0, 0
    while index < len(row):
        character = row[index]
        if character == "\\" and index + 1 < len(row):
            index += 2
            continue
        if character == "`":
            run = len(row[index:]) - len(row[index:].lstrip("`"))
            if not in_code:
                in_code, depth = True, run
            elif run == depth:
                in_code = False
            index += run
            continue
        if character == "|" and not in_code:
            pipes += 1
        index += 1
    return max(pipes - 1, 0)


def _malformed(path: Path) -> list[str]:
    """Every row in `path` whose cell count differs from its own header's."""
    lines = path.read_text(encoding="utf-8").split("\n")
    found: list[str] = []
    index = 0
    while index < len(lines) - 1:
        if lines[index].strip().startswith("|") and _SEPARATOR.fullmatch(lines[index + 1]):
            header = _cells(lines[index])
            row = index + 2
            while row < len(lines) and lines[row].strip().startswith("|"):
                counted = _cells(lines[row])
                if counted != header:
                    found.append(
                        f"{path.relative_to(REPO)}:{row + 1}: header has {header} cells, "
                        f"row has {counted} — {lines[row].strip()[:90]}"
                    )
                row += 1
            index = row
        else:
            index += 1
    return found


@pytest.mark.parametrize("path", _MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_every_table_row_has_as_many_cells_as_its_header(path: Path):
    malformed = _malformed(path)
    assert malformed == [], "\n".join(malformed)


def test_the_counter_does_not_mistake_a_pipe_inside_code_for_a_cell_divider():
    """The near-miss, and the reason this file has a counter at all: a naive
    `line.count("|")` reported 1,961 malformed rows across documents that have none."""
    assert _cells("| a | b | c |") == 3
    assert _cells("| `a|b` | c | d |") == 3
    assert _cells("| a \\| b | c | d |") == 3
    assert _cells("| ``a ` b`` | c | d |") == 3
    # A row with no trailing pipe really is short one cell — that is not a counting
    # artefact, it is the defect this test found in `PROJECT.md`.
    assert _cells("| a | b | c") == 2
