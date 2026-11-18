"""The dotenv reader (plan 3 Task 4, N3): a file the CODE names as its env file. The rules are
python-dotenv's, the library pydantic-settings reads the file with, measured in
`scripts/probes/pydantic_settings_rules.md` (section "dotenv file syntax")."""

from pathlib import Path

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.ingress.read.dotenv import DotenvReader
from sextant.ingress.read.registry import READERS


def _read(tmp_path: Path, text: str, name: str = ".env") -> dict[str, str]:
    file = tmp_path / name
    file.write_text(text, encoding="utf-8")
    [(document, facts)] = DotenvReader().read(
        ReadRequest(module_id="shop", version="1", files=(file,), root=tmp_path)
    )
    assert document.language == "dotenv"
    assert document.relative_path == name
    return {fact.key_path: fact.value for fact in facts}


def test_the_reader_claims_a_dot_env_name_and_no_extension():
    reader = DotenvReader()
    assert reader.accepts(".env") and reader.accepts(".env.local") and reader.accepts("prod.env")
    assert not reader.accepts("env") and not reader.accepts("yml") and not reader.accepts("")


def test_the_suffix_walk_never_hands_it_a_file():
    walked = [Path("a/.env"), Path("a/prod.env"), Path("a/.env.local"), Path("a/x.yml")]
    claimed = [
        owned
        for reader, owned in group_files_by_reader(walked, READERS)
        if isinstance(reader, DotenvReader)
    ]
    assert claimed == []


def test_key_value_comments_blank_lines_and_export(tmp_path: Path):
    text = "# a comment\n\nA=1\nexport B=two words\n  C = spaced  \nD=\nE\n"
    assert _read(tmp_path, text) == {"A": "1", "B": "two words", "C": "spaced", "D": ""}


def test_a_trailing_comment_needs_whitespace_before_the_hash(tmp_path: Path):
    assert _read(tmp_path, "A=b # c\nB=a#b\n") == {"A": "b", "B": "a#b"}


def test_quotes(tmp_path: Path):
    text = 'A="x # y"\nB=\'it\\\'s\'\nC=\'no\\nescape\'\nD="t\\tab"\nE="q" # c\nF="multi\nline"\n'
    assert _read(tmp_path, text) == {
        "A": "x # y",
        "B": "it's",
        "C": "no\\nescape",
        "D": "t\tab",
        "E": "q",
        "F": "multi\nline",
    }


def test_a_later_duplicate_wins_and_an_unparseable_line_is_skipped(tmp_path: Path):
    assert _read(tmp_path, "A=1\nA=2\nB='q'x\nC=3\n") == {"A": "2", "C": "3"}


def test_a_placeholder_is_kept_verbatim(tmp_path: Path):
    assert _read(tmp_path, "A=${B:-d}x\n") == {"A": "${B:-d}x"}
