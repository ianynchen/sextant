"""`docs/PROJECT.md` is the delivery authority, and this is what stops it drifting again
(F9 §10.1, W50).

## Why a test rather than a habit

Every one of PROJECT.md's seventeen component rows read `planned` until W50 — including five
that had shipped for phases. That is C11's finding: the file stopped being maintained and
kept being cited. A file nobody checks says whatever it said last time, and the register that
is WRONG is worse than one that is absent, because a reader takes it for evidence.

## What this checks, and what it deliberately does not

It checks the two claims that can be mechanically wrong: that a component marked `delivered`
or `in-progress` has an implementation behind it, and that one marked `planned` does not.
The first catches a status that fell behind the code; the second catches a status that ran
ahead of it — which is the direction that overclaims.

It does NOT check the boundary between `delivered` and `in-progress`. That is a judgement
about how much of a component's design is realised, and the file states its reasoning per row
so a reader can disagree with it. Encoding that judgement here would freeze one reading of it.

It also cannot tell D05 from M08, or D03 from M01: **each of those pairs is decided by one
path**, because a data definition and the module that realises it are the same code on disk.
Deleting `manifest.py` fails both D05 and M08 together and neither alone. Stated here rather
than papered over with a second path chosen only to look distinct.
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[2]
PROJECT = REPO / "docs" / "PROJECT.md"
SRC = REPO / "src" / "sextant"

# One path per component whose EXISTENCE decides `planned` against the other two. Chosen as
# the file that would not exist at all if the component were unbuilt — never a file that
# merely mentions it, which is how `overlay` and `sync` read as present in a grep.
_EVIDENCE = {
    "D00": SRC / "domain" / "facts.py",
    "D01": SRC / "storage" / "duckdb" / "schema.sql",
    "D02": SRC / "ingress" / "catalogs" / "yaml_source.py",
    "D03": SRC / "application" / "overlay",
    "D04": SRC / "domain" / "redaction.py",
    "D05": SRC / "egress" / "export" / "manifest.py",
    "D06": SRC / "egress" / "export" / "index.py",
    "M00": SRC / "cli" / "app.py",
    "M01": SRC / "application" / "overlay",
    "M02": SRC / "ingress" / "detect" / "maven.py",
    "M03": SRC / "ingress" / "extract" / "jvm" / "scanner.py",
    "M04": SRC / "application" / "resolve" / "pipeline.py",
    "M05": SRC / "application" / "sync",
    "M06": SRC / "application" / "stitch",
    "M07": SRC / "egress" / "render" / "document.py",
    "M08": SRC / "egress" / "export" / "manifest.py",
    "M09": SRC / "application" / "query" / "trace.py",
}
_ROW = re.compile(r"^\| \[([DM]\d\d)\]\([^)]+\)[^|]*\| \*{0,2}([a-z-]+)\*{0,2} \|")

# The only three a component row may carry. `deferred` and `cancelled` are legal statuses of
# the FILE (they appear on scope rows), but on a component they would suspend both checks
# below while still reading as a delivery claim — so a component that acquires one fails here
# and forces the question to be answered rather than routed around.
_COMPONENT_STATUSES = ("delivered", "in-progress", "planned")


def _rows() -> list[tuple[str, str]]:
    """A LIST, not a dict: a duplicated row is the thing the next test looks for, and a dict
    would silently keep the last one."""
    return [
        (match.group(1), match.group(2))
        for line in PROJECT.read_text(encoding="utf-8").splitlines()
        if (match := _ROW.match(line))
    ]


def _statuses() -> dict[str, str]:
    return dict(_rows())


def test_the_register_names_every_component_exactly_once():
    """A row that vanished takes its claim with it, silently — and a row that appears twice
    can carry two different statuses, of which a reader sees whichever they scroll to."""
    rows = _rows()
    names = [name for name, _ in rows]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    assert duplicated == [], f"PROJECT.md gives these components more than one row: {duplicated}"
    statuses = _statuses()
    assert sorted(statuses) == sorted(_EVIDENCE), (
        f"PROJECT.md's component rows do not match the known set: "
        f"missing {sorted(set(_EVIDENCE) - set(statuses))}, "
        f"unexpected {sorted(set(statuses) - set(_EVIDENCE))}"
    )


def test_no_component_claims_more_than_the_code_carries():
    """`delivered` or `in-progress` over nothing is the overclaim this file exists against."""
    wrong = [
        f"{component} is `{status}` and {_EVIDENCE[component].relative_to(REPO)} does not exist"
        for component, status in sorted(_statuses().items())
        if status in ("delivered", "in-progress") and not _EVIDENCE[component].exists()
    ]
    assert wrong == [], "PROJECT.md claims a component that is not built:\n  " + "\n  ".join(wrong)


def test_nothing_still_called_planned_has_already_shipped():
    """The direction W50 found: seventeen rows read `planned` and five had shipped."""
    wrong = [
        f"{component} is `planned` and {_EVIDENCE[component].relative_to(REPO)} exists"
        for component, status in sorted(_statuses().items())
        if status == "planned" and _EVIDENCE[component].exists()
    ]
    assert wrong == [], "PROJECT.md understates a component that is built:\n  " + "\n  ".join(wrong)


def test_no_component_carries_a_status_that_suspends_the_checks():
    """`deferred` and `cancelled` would exempt a row from both tests above while still
    reading, to a person, as a statement about delivery."""
    wrong = [
        f"{component} is `{status}`"
        for component, status in sorted(_statuses().items())
        if status not in _COMPONENT_STATUSES
    ]
    assert wrong == [], (
        f"a component row may only be one of {_COMPONENT_STATUSES}:\n  " + "\n  ".join(wrong)
    )
