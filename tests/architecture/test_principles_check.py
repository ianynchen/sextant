"""Every design and plan written from 2026-11-23 carries a `## Principles check` (GUIDELINES §8.9).

§8.9 says a design without the check is not ready for review. A check nobody can see is the
state the Django plan was in when seven new concepts reached review unexamined, so this makes
its ABSENCE fail. It is a presence check only: an empty or untrue section passes, and whether
the check is honest is the reviewer's question — a test that tried to judge prose would be
gamed or disabled.

## Which files

Every `*.md` and `*.markdown` under `docs/superpowers/specs/` and `docs/superpowers/plans/`, at
any depth. The date is the file's `YYYY-MM-DD-` name prefix, the repository's naming for both
folders. A file dated ON or after 2026-11-23 is checked, so a document written on the day the
rule was approved is not exempt; an earlier one is exempt BY THE DATE, not by a list — on
2026-11-23 the newest file on `main` in either folder is dated 2026-11-21, so the date rule
exempts exactly the files written before the rule. A file with no date prefix fails: every
file in both folders has one, so an undated file is new, and exempting it would let a document
skip the check by being misnamed.

The heading counts only as a heading line outside a fenced code block: a fence that QUOTES the
heading (a template, an example) is not the section.

It is OFFLINE and deterministic: it reads files and runs nothing.
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[2]
FOLDERS = (REPO / "docs" / "superpowers" / "specs", REPO / "docs" / "superpowers" / "plans")

_RULE_DATE = "2026-11-23"
_DATED = re.compile(r"(\d{4}-\d{2}-\d{2})-")
_FENCE = re.compile(r"\s{0,3}(```|~~~)")
_HEADING = "## Principles check"


def _has_heading(text: str) -> bool:
    fenced = False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and line.rstrip() == _HEADING:
            return True
    return False


def missing_checks(folders: tuple[Path, ...]) -> list[str]:
    found = []
    for folder in folders:
        paths = sorted(path for path in folder.rglob("*") if path.suffix in (".md", ".markdown"))
        for path in paths:
            dated = _DATED.match(path.name)
            if dated and dated.group(1) < _RULE_DATE:
                continue
            if not _has_heading(path.read_text(encoding="utf-8")):
                why = (
                    "is dated on or after 2026-11-23" if dated else "has no YYYY-MM-DD- date prefix"
                )
                found.append(
                    f"{path.relative_to(REPO) if path.is_relative_to(REPO) else path} {why} and has "
                    f"no `{_HEADING}` heading: GUIDELINES §8.9 requires one in every design and plan"
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
    assert "2026-11-24-x-design.md is dated on or after 2026-11-23" in only
    assert "GUIDELINES §8.9" in only


def test_a_file_dated_on_the_rule_day_is_checked(tmp_path: Path):
    assert len(missing_checks(_folder(tmp_path, "2026-11-23-x.md", "# X\n"))) == 1


def test_a_later_file_with_the_heading_passes(tmp_path: Path):
    text = "# X\n\n## Principles check\n\n| rule | how |\n"
    assert missing_checks(_folder(tmp_path, "2026-11-24-x-design.md", text)) == []


def test_an_earlier_file_is_exempt(tmp_path: Path):
    _folder(tmp_path, "2026-11-22-x.md", "# X\n")
    assert missing_checks(_folder(tmp_path, "2026-08-27-y.md", "# Y\n")) == []


def test_an_undated_file_fails(tmp_path: Path):
    (only,) = missing_checks(_folder(tmp_path, "notes.md", "# Notes\n"))
    assert "notes.md has no YYYY-MM-DD- date prefix" in only


def test_a_markdown_extension_is_read_too(tmp_path: Path):
    (only,) = missing_checks(_folder(tmp_path, "2026-12-01-x.markdown", "# X\n"))
    assert only.endswith(
        "2026-12-01-x.markdown is dated on or after 2026-11-23 and has no `## Principles check` "
        "heading: GUIDELINES §8.9 requires one in every design and plan"
    )


def test_the_heading_must_be_a_heading_line_not_a_mention(tmp_path: Path):
    text = "# X\n\nThis plan has no ## Principles check yet.\n### Principles check\n"
    assert len(missing_checks(_folder(tmp_path, "2026-12-01-x.md", text))) == 1


def test_a_heading_inside_a_code_fence_does_not_count(tmp_path: Path):
    text = "# X\n\n```markdown\n## Principles check\n```\n"
    (only,) = missing_checks(_folder(tmp_path, "2026-12-01-x.md", text))
    assert only.endswith(
        "2026-12-01-x.md is dated on or after 2026-11-23 and has no `## Principles check` "
        "heading: GUIDELINES §8.9 requires one in every design and plan"
    )
    text += "\n## Principles check\n"
    assert missing_checks(_folder(tmp_path, "2026-12-01-x.md", text)) == []
