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

## A pipe inside a code span still splits the cell

That is GFM's rule, and it is the surprising one — so it is stated here rather than
discovered. The spec is explicit: inside a table row, EVERY unescaped `|` divides a cell,
including one inside a code span, and the only way to put a pipe in a cell is to write
`\\|` — *including* inside backticks. cmark-gfm implements that, and so does markdown-it,
which is what VS Code's preview uses.

**The first version of this counter tracked backtick spans and skipped the pipes inside
them, on the reasoning that "a pipe inside a code span is text, which is what a renderer
does".** It is not what a renderer does, and the consequence is the exact defect this file
exists to catch, inverted: the counter declared well-formed precisely the rows a renderer
breaks. Three shipped rows were rendering wrong while it passed — a W33 plan row whose
`` `<|--` `` split it into eight cells under a five-column header, so three labelled columns
showed wrong values and the whole `Delivers` cell vanished; **W40's own row**, cut off at
``a naive `line.count("`` ; and a probe row containing `contains("|")`. Each renders as a
truncated row, which is what the wrapped-row and extra-cell shapes below also do.

So the counter now honours ESCAPES and nothing else, and a document that needs a literal
pipe writes `\\|` wherever it sits.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]


def _shipped() -> list[Path]:
    """Every markdown file the repository SHIPS, asked of git rather than of the tree.

    Including the ones under `docs/superpowers`: a plan or a spec whose table renders wrong
    misleads exactly as a component document does, and the plan's own rows are where this
    project records what it delivered.

    **Asked of git, because a walk of the tree is a walk of whatever happens to be sitting
    in it.** `rglob` collected 259 files where the repository ships 98. Of the extra 161,
    **99** were copies of these same documents inside `.claude/worktrees/`, where a review
    agent had a checkout of an older commit, and **62** were untracked working files —
    `.pytest_cache/README.md` among them. That makes the subject of this test depend on
    whether some other process is running: a scratch file with a malformed table fails the
    gate for a document nobody ships, while the duplicates are checked at a revision that
    is not this one. Excluding those directories by name would fix the instance and not the
    class; the repository's own answer to "what do we ship" is git's.

    A tracked file MISSING from the working tree is reported as that, rather than raised as
    a bare `FileNotFoundError` from whichever test happened to reach it first.
    """
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "*.md"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return sorted(REPO / name for name in listed.split("\0") if name)


_MARKDOWN = _shipped()

_SEPARATOR = re.compile(r"\s*\|[\s:|-]+\|\s*")
# What legitimately ends a table: a line opening another block. A list item, an ordered
# item, a heading, a quote, a fence, or raw HTML — everything markdown treats as a new
# block rather than as more of the paragraph before it.
_BLOCK_START = re.compile(r"([-*+>#]|\d+[.)]|```|~~~|<)")


def _cells(row: str) -> int:
    """How many cells a renderer reads in `row`.

    Every unescaped `|` divides a cell — a backtick span does NOT protect one (see the
    header) — and only `\\|` is a literal. The leading and trailing pipes are delimiters,
    so N pipes make N-1 cells.
    """
    row = row.strip()
    pipes, index = 0, 0
    while index < len(row):
        character = row[index]
        if character == "\\" and index + 1 < len(row):
            index += 2
            continue
        if character == "|":
            pipes += 1
        index += 1
    return max(pipes - 1, 0)


def _malformed(path: Path) -> list[str]:
    """Every row in `path` whose cell count differs from its own header's."""
    if not path.exists():
        # git lists it and the tree does not hold it — a deletion that was never staged,
        # or a half-finished rename. Said in the assertion rather than raised out of
        # `read_text`, which reports a path and not what is wrong with it.
        return [f"{path.relative_to(REPO)}: tracked by git and absent from the working tree"]
    lines = _outside_code_blocks(path.read_text(encoding="utf-8").split("\n"))
    found: list[str] = []
    index = 0
    while index < len(lines) - 1:
        if lines[index].strip().startswith("|") and _SEPARATOR.fullmatch(lines[index + 1]):
            header = _cells(lines[index])
            row = index + 2
            while row < len(lines):
                text = lines[row]
                if not text.strip().startswith("|"):
                    # **The table may not end here — a row can be WRAPPED.** Markdown ends
                    # a row at the newline, so a continuation line loses its cells; the
                    # first version stopped scanning at any non-pipe line, which left every
                    # row BELOW a wrapped row unchecked and is why W40 counted 19 rows
                    # where it had changed 20.
                    #
                    # A blank line ends the table, and so does the start of another BLOCK —
                    # a list item, a heading, a quote, a fence. Those are the legitimate
                    # ends, and treating them as wrapped rows flagged a golden document
                    # whose table sits inside a list beside a perfectly ordinary sibling
                    # item. What is left — a bare line of prose — is the wrap.
                    if not text.strip() or _BLOCK_START.match(text.strip()):
                        break
                    found.append(
                        f"{path.relative_to(REPO)}:{row + 1}: a row wrapped onto this "
                        f"line, so it renders as a paragraph under the table — "
                        f"{text.strip()[:70]}"
                    )
                    row += 1
                    continue
                counted = _cells(text)
                if counted != header:
                    found.append(
                        f"{path.relative_to(REPO)}:{row + 1}: header has {header} cells, "
                        f"row has {counted} — {text.strip()[:90]}"
                    )
                row += 1
            index = row
        else:
            index += 1
    return found


def _outside_code_blocks(lines: list[str]) -> list[str]:
    """`lines` with every fenced block's contents blanked out.

    A pipe table inside ``` ``` ``` is a code sample and no renderer makes a table of it,
    so checking it is checking the wrong thing — and a document that needs to SHOW a
    deliberately broken table cannot, because the example fails the suite. One is being
    checked today (a four-backtick fence in a 2O plan) and happens to be well formed.

    Blanked rather than dropped so every reported line number stays the file's own.
    """
    kept: list[str] = []
    fence: str | None = None
    for line in lines:
        stripped = line.lstrip()
        marker = stripped[:3]
        if fence is None and marker in ("```", "~~~"):
            fence = stripped[0]
            kept.append("")
            continue
        if fence is not None:
            # A closing fence is the same character, at least as long as the opener; a
            # longer opener (```` ```` ````) is closed only by one at least as long, which
            # a plain three-character run inside it does not do. Compared on the CHARACTER
            # because that is what decides, and length is checked by the run itself.
            if stripped and stripped[0] == fence and set(stripped.rstrip()) == {fence}:
                fence = None
            kept.append("")
            continue
        kept.append(line)
    return kept


@pytest.mark.parametrize("path", _MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_every_table_row_has_as_many_cells_as_its_header(path: Path):
    malformed = _malformed(path)
    assert malformed == [], "\n".join(malformed)


def test_a_pipe_inside_a_code_span_still_divides_a_cell():
    """GFM's own rule, and the one the first version of this counter got backwards.

    Every assertion here is what cmark-gfm and markdown-it actually produce, not what a
    reader of the source would guess. The consequence of guessing was three shipped rows
    rendering truncated while this test passed.
    """
    assert _cells("| a | b | c |") == 3
    # The surprising one. A renderer splits this into four cells, so a three-column
    # header truncates it — which is exactly what W33's plan row was doing.
    assert _cells("| `a|b` | c | d |") == 4
    # The escape is the ONLY thing that protects a pipe, inside backticks or out.
    assert _cells("| a \\| b | c | d |") == 3
    assert _cells("| `a \\| b` | c | d |") == 3
    assert _cells("| ``a ` b`` | c | d |") == 3
    # A row with no trailing pipe really is short one cell — that is not a counting
    # artefact, it is the defect this test found in `PROJECT.md`.
    assert _cells("| a | b | c") == 2
