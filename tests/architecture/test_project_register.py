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


def _statuses() -> dict[str, str]:
    found = {}
    for line in PROJECT.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def test_the_register_names_every_component_exactly_once():
    """A row that vanished takes its claim with it, silently."""
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
