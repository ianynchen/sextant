"""Every `file.py:NNN` a shipped document cites points inside that file (F9 §10.4, W52).

## Why this exists

The RESTATE batch is thirty-nine documentation claims that are untrue or unmeasured, and two
of them were citations that had simply drifted: `COVERAGE.md` said `resolved_config` is read
by *"only `config_join.py:528` and `derived_resource.py:578`"* — six modules read it and both
line numbers had moved — and it placed `_grpc_operation_row` at `schema_operations.py:164-197`
when it is at `:367`. Neither was wrong when written. A line number is a claim that decays on
its own, silently, every time somebody edits above it.

## What this catches, and what it cannot

It catches a citation pointing PAST THE END of the file it names: a deletion, a truncation, a
file that shrank. That is the failure mode a reader meets as "there is nothing there".

**It cannot catch semantic drift** — a citation that still lands inside the file and now
points at something else, which is what both of W52's own examples actually were. There is no
mechanical test for that, and pretending otherwise would be the kind of true-sounding sentence
this batch exists to remove. The remedy for semantic drift is not to cite a line at all: cite
the SYMBOL, which moves with the thing it names. Both corrected citations do.

## Scope

Shipped documents only. `docs/superpowers/` holds plans and specs that are RECORDS of what was
true when they were written — a stale citation there is history rather than a claim, and three
of them are genuinely stale for that reason.
"""

import collections
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]

# `` `path/to/file.py:120` `` or `` `file.sql:398-400` ``. Only inside backticks: prose that
# happens to contain a colon and a number is not a citation.
_CITATION = re.compile(r"`([\w./-]+\.(?:py|sql|java|kt|yml))[:](\d+)(?:-(\d+))?`")


def _tracked() -> dict[str, list[str]]:
    """Every tracked path, indexed by basename — a citation names `workspace.py:163`, not the
    whole path, and resolving it by hand would be a second map to keep true."""
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"], check=True, capture_output=True, text=True
    ).stdout
    found: dict[str, list[str]] = collections.defaultdict(list)
    for path in listed.split("\0"):
        if path:
            found[Path(path).name].append(path)
    return found


def _shipped_markdown() -> list[Path]:
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "*.md"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return sorted(
        REPO / name
        for name in listed.split("\0")
        if name and not name.startswith("docs/superpowers/")
    )


_MARKDOWN = _shipped_markdown()
_TRACKED = _tracked()


@pytest.mark.parametrize("path", _MARKDOWN, ids=lambda p: str(p.relative_to(REPO)))
def test_no_citation_points_past_the_end_of_the_file_it_names(path: Path):
    beyond = []
    for match in _CITATION.finditer(path.read_text(encoding="utf-8")):
        cited, first = match.group(1), int(match.group(2))
        candidates = [c for c in _TRACKED.get(Path(cited).name, []) if c.endswith(cited)]
        if not candidates:
            # Names a file this repository does not track — a jar's own source, a path in an
            # example. Nothing to check, and inventing a rule for it would fail on prose.
            continue
        # Same-basename ambiguity, resolved by SIZE and not by meaning: `workspace.py`
        # names both `application/ports/workspace.py` (47 lines) and
        # `storage/duckdb/workspace.py` (1,359). Taking the longest makes the test permissive
        # rather than wrong — a citation of the small file passes on any line up to the big
        # file's length. Every one of the eight `workspace.py:NNN` citations shipped today
        # means the duckdb one, so nothing is mis-resolved now; a citation of the port would
        # go unchecked, and that is the cost of never failing on an ambiguity a reader has no
        # trouble with. Found by the W52 review.
        longest = max(
            len((REPO / candidate).read_text(encoding="utf-8").splitlines())
            for candidate in candidates
        )
        if first > longest:
            beyond.append(f"{match.group(0)} — {candidates[0]} has {longest} lines")
    assert beyond == [], (
        f"{path.relative_to(REPO)} cites a line that does not exist:\n  "
        + "\n  ".join(beyond)
        + "\n\nCite the SYMBOL instead where you can — it moves with the thing it names."
    )


def test_the_citation_pattern_reads_a_citation_and_not_prose():
    """The near-miss: this must not fire on ordinary text, or it would be disabled the first
    time somebody wrote a ratio in backticks."""
    assert _CITATION.findall("see `workspace.py:163` and `derive.sql:12-20`") == [
        ("workspace.py", "163", ""),
        ("derive.sql", "12", "20"),
    ]
    assert _CITATION.findall("a `3:1` ratio, and `foo.py` on its own") == []
    assert _CITATION.findall("unbackticked workspace.py:163 is prose") == []
