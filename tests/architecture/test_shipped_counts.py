"""A shipped document that states how many catalogs ship states the real number
(F9 §10.4, W52).

## The gap class this closes

Four of the RESTATE batch's thirty-nine are the same defect wearing different numbers:
`principles-sweep` says 52 catalogs, `RUNBOOK` said 55, one `open-issues` entry said 56 and
another 57, `documented-not-implemented` said 55. Sixty-four ship. None was wrong when it was
written — a catalog count decays every time a wave adds a catalog, which this session did six
times.

A number that decays on its own needs a ratchet or it needs to not be a number. Where the
count is load-bearing — "all N catalogs declare X" — the ratchet is right, because the claim
is about the whole set. Where it is scene-setting, the honest fix is to stop counting, and
several documents now say "every shipped catalog" instead.

## What is in scope

Documents that describe the CURRENT state. Dated audit records — `docs/java-gap-analysis-*`,
`docs/principles-sweep-*`, and everything under `docs/superpowers/` — are excluded by name:
they are records of what was true on the day they were written, and rewriting their numbers
would destroy the evidence they exist to preserve. Their staleness is a property of a record,
not a defect.

## What it still cannot reach, stated rather than left to be discovered

A bare total with no noun — *"the loader validates the shape for all 55"* — carries no word
this pattern can anchor on, and a rule that fired on any two- or three-digit number after
"all" would be disabled the first week. That exact sentence was live in `GUIDELINES.md` and
was found by a reviewer, not by this test. The remedy is the same one the rest of this file
argues for: where the count is not load-bearing, stop counting.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# A dated record rather than a claim about today. Matched on the path, so a new audit follows
# the same naming and is excluded without editing this list.
_RECORDS = (
    "docs/superpowers/",
    "docs/java-gap-analysis-",
    "docs/principles-sweep-",
    # A changelog is a record by construction: each entry says what one wave did, and "19 of
    # 55 catalogs" in an entry written when 55 shipped is CORRECT history. Forcing those to
    # today's number would rewrite the past to match the present, which is the one thing a
    # changelog must not do. Found by this rule's own first run.
    "CHANGELOG.md",
)

# **Only phrasings that can mean the TOTAL.** The first version of this pattern matched any
# "<number> catalogs" and immediately reported fourteen failures — of which most were SUBSET
# claims: "a style 21 catalogs share", "already declared by 40 catalogs", "19 shipped catalogs
# state no measured version". Every one of those is true and none is about the total, so the
# rule was false of the estate the moment it was written — the same defect W47's review found
# in a `requires` rule, made twice.
#
# What survives is the quantifier: `all N`, `every one of the N`, `any of the N`, `of the N
# shipped`, and `N of the M` where M is the denominator. A subset count carries no quantifier
# and is left alone, which is why the near-miss below tests one.
_COUNT = re.compile(
    r"\ball (\d{2,3}) (?:shipped )?catalogs\b"
    r"|\bevery one of the (\d{2,3}) (?:shipped )?catalogs\b"
    r"|\bany of the (\d{2,3}) (?:shipped )?catalogs\b"
    r"|\bof the (\d{2,3}) shipped catalogs\b"
    r"|\b\d{1,3} of (?:the )?(\d{2,3}) (?:shipped )?catalogs\b"
    # W52 review: the numerator may be SPELLED OUT. `GUIDELINES.md` said "only for four of
    # the 55 catalogs" while 64 shipped, and the digit-only numerator above walked past it —
    # in the file `CLAUDE.md` designates as binding, whose own subject is citing accurately.
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
    r"|fifteen|sixteen|seventeen|eighteen|nineteen|twenty) of (?:the )?(\d{2,3})"
    r" (?:shipped )?catalogs\b"
)


# A count a sentence DATES is a historical statement inside a live document, not a claim about
# today: "declared by every one of the 41 catalogs shipping THEN". Those are the most valuable
# sentences in these files — they say when a thing became true — and a rule that forced them
# to the current number would destroy exactly that.
_DATED = re.compile(r"\b(then|at the time|when this was written|back then|as of)\b", re.IGNORECASE)

# The marker exempts its own SENTENCE, not the whole line. Found by the W52 review in
# `GUIDELINES.md`: one legitimately dated clause — "41 when this was written" — sat on a line
# that also carried two undated stale counts, and the line-wide exemption hid both. A markdown
# line is often a whole paragraph here, so line scope was never the right unit.
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s")


def _dated_around(line: str, match: re.Match[str]) -> bool:
    """Whether the count that matched sits in a sentence that dates itself."""
    start = 0
    for boundary in _SENTENCE_END.finditer(line):
        if boundary.end() > match.start():
            break
        start = boundary.end()
    end = next(
        (b.start() for b in _SENTENCE_END.finditer(line) if b.start() >= match.end()), len(line)
    )
    return bool(_DATED.search(line[start:end]))


def _stated(match: re.Match[str]) -> int:
    """The one group that matched — the alternation has five and exactly one fires."""
    return int(next(group for group in match.groups() if group is not None))


def _shipped_documents() -> list[Path]:
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "*.md"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return sorted(
        REPO / name for name in listed.split("\0") if name and not name.startswith(_RECORDS)
    )


def _shipped_catalogs() -> int:
    """Counted off the directory, never listed — the one thing this rule must not do is stop
    seeing a catalog. `shape-models/` holds payload-type blocks, not catalogs."""
    return len([path for path in CATALOGS.glob("*.yml")])


_DOCUMENTS = _shipped_documents()


@pytest.mark.parametrize("path", _DOCUMENTS, ids=lambda p: str(p.relative_to(REPO)))
def test_a_stated_catalog_count_is_the_real_one(path: Path):
    shipped = _shipped_catalogs()
    wrong = [
        f"line {number}: says {_stated(match)} catalogs, {shipped} ship — {line.strip()[:80]}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for match in _COUNT.finditer(line)
        if _stated(match) != shipped and not _dated_around(line, match)
    ]
    assert wrong == [], (
        f"{path.relative_to(REPO)} states a catalog count that is not the shipped one:\n  "
        + "\n  ".join(wrong)
        + "\n\nEither update it, or stop counting — 'every shipped catalog' does not decay."
    )


def test_the_pattern_catches_a_count_and_not_an_unrelated_number():
    """The near-miss. A rule that fired on any two-digit number near any word would be
    disabled the first time somebody wrote about 12 methods on a template."""
    assert [_stated(m) for m in _COUNT.finditer("all 64 catalogs declare one")] == [64]
    assert [_stated(m) for m in _COUNT.finditer("19 of the 64 catalogs")] == [64]
    assert [_stated(m) for m in _COUNT.finditer("four of the 64 catalogs")] == [64]
    assert [_stated(m) for m in _COUNT.finditer("a style 21 catalogs share")] == []


def test_a_dated_clause_exempts_its_own_sentence_and_not_its_neighbours():
    """The W52-review hole: one dated clause used to immunise a whole paragraph-length line."""
    line = "41 when this was written. It reaches four of the 55 catalogs today."
    matches = list(_COUNT.finditer(line))
    assert len(matches) == 1
    assert _dated_around(line, matches[0]) is False


def test_a_dated_clause_still_exempts_the_count_inside_it():
    line = "declared by every one of the 41 catalogs shipping at the time."
    matches = list(_COUNT.finditer(line))
    assert len(matches) == 1
    assert _dated_around(line, matches[0]) is True
    assert [_stated(m) for m in _COUNT.finditer("every one of the 64 shipped catalogs")] == [64]
    # SUBSET claims, all true, none about the total — the false positives that made the first
    # version of this rule unshippable.
    assert list(_COUNT.finditer("a style 21 catalogs share")) == []
    assert list(_COUNT.finditer("already declared by 40 catalogs")) == []
    assert list(_COUNT.finditer("19 shipped catalogs state no measured version")) == []
    assert list(_COUNT.finditer("the 12 methods `JmsTemplate` declares")) == []
    # And a DATED total is history, not a claim — the sentences worth keeping most.
    assert _DATED.search("declared by every one of the 41 catalogs shipping then") is not None
    assert _DATED.search("all 64 catalogs declare one") is None
