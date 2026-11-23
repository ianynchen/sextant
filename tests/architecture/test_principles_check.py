"""Every design and plan written after 2026-11-23 carries a `## Principles check` (GUIDELINES §8.9).

§8.9 says a design without the check is not ready for review. A check nobody can see is the
state the Django plan was in when seven new concepts reached review unexamined, so this makes
its ABSENCE fail. It is a presence check only: whether the check is honest is the reviewer's
question, and a test that tried to judge prose would be gamed or disabled.

## Which files

Every `*.md` under `docs/superpowers/specs/` and `docs/superpowers/plans/`, at any depth. The
date is the file's `YYYY-MM-DD-` name prefix, the repository's naming for both folders. A file
dated 2026-11-23 or earlier is exempt BY THE DATE, not by a list: it was written before the
rule. A file with no date prefix fails: on 2026-11-23 every file in both folders has one, so an
undated file is new, and exempting it would let a document skip the check by being misnamed.

It is OFFLINE and deterministic: it reads files and runs nothing.
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[2]
FOLDERS = (REPO / "docs" / "superpowers" / "specs", REPO / "docs" / "superpowers" / "plans")

_RULE_DATE = "2026-11-23"
_DATED = re.compile(r"(\d{4}-\d{2}-\d{2})-")
_HEADING = "## Principles check"


def missing_checks(folders: tuple[Path, ...]) -> list[str]:
    found = []
    for folder in folders:
        for path in sorted(folder.rglob("*.md")):
            dated = _DATED.match(path.name)
            if dated and dated.group(1) <= _RULE_DATE:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            if _HEADING not in (line.rstrip() for line in lines):
                why = "is dated after 2026-11-23" if dated else "has no YYYY-MM-DD- date prefix"
                found.append(
                    f"{path.relative_to(REPO) if path.is_relative_to(REPO) else path} "
                    f"{why} and has no `{_HEADING}` heading: GUIDELINES §8.9 requires one in every "
                    "design and plan"
                )
    return found


def test_every_later_design_and_plan_has_a_principles_check():
    assert missing_checks(FOLDERS) == []


# --- tests of the test --------------------------------------------------------------------------


def _folder(tmp_path: Path, name: str, text: str) -> tuple[Path, ...]:
    folder = tmp_path / "specs"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    return (folder,)


def test_a_later_file_without_the_heading_fails_and_names_the_file(tmp_path: Path):
    (only,) = missing_checks(_folder(tmp_path, "2026-11-24-x-design.md", "# X\n\n## Design\n"))
    assert "2026-11-24-x-design.md is dated after 2026-11-23" in only
    assert "GUIDELINES §8.9" in only


def test_a_later_file_with_the_heading_passes(tmp_path: Path):
    text = "# X\n\n## Principles check\n\n| rule | how |\n"
    assert missing_checks(_folder(tmp_path, "2026-11-24-x-design.md", text)) == []


def test_a_file_dated_on_or_before_the_rule_is_exempt(tmp_path: Path):
    _folder(tmp_path, "2026-11-23-x.md", "# X\n")
    assert missing_checks(_folder(tmp_path, "2026-08-27-y.md", "# Y\n")) == []


def test_an_undated_file_fails(tmp_path: Path):
    (only,) = missing_checks(_folder(tmp_path, "notes.md", "# Notes\n"))
    assert "notes.md has no YYYY-MM-DD- date prefix" in only


def test_the_heading_must_be_a_heading_line_not_a_mention(tmp_path: Path):
    text = "# X\n\nThis plan has no ## Principles check yet.\n### Principles check\n"
    assert len(missing_checks(_folder(tmp_path, "2026-12-01-x.md", text))) == 1
