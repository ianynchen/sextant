"""A dotenv file the code names (plan 3 Task 4, N3). Hand-rolled like `.properties`: the rules are
python-dotenv's, the library pydantic-settings reads the file with, measured in
`scripts/probes/pydantic_settings_rules.md`.

**Claimed by NAME, never by suffix.** `Path(".env").suffix` is empty, so the suffix walk
(`group_files_by_reader`, which passes a bare extension) cannot hand this reader a file, and the
built-in ignore layer hides every `.env` from that walk besides. `analyze` asks `accepts` with the
whole file name, for a file a settings class named, and only for that file. A bare extension
(`env`, what the walk passes) is not a name this reader claims, so `prod.env` in a resource root
is not read; `prod.env` NAMED by the code is."""

import re

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import ConfigEntryFact, Document, Fact
from sextant.ingress.read import build_document

# One statement: optional `export`, a key, `=`, then a value (python-dotenv's own grammar). A line
# that matches none of the value forms is skipped, as python-dotenv skips it.
_KEY = r"(?:export[ \t]+)?([^=#\s]+)[ \t]*=[ \t]*"
_SINGLE = r"'((?:\\'|[^'])*)'"
_DOUBLE = r'"((?:\\"|[^"])*)"'
_TAIL = r"[ \t]*(?:#[^\r\n]*)?(?:\r\n|\n|\r|$)"
_STATEMENT = re.compile(
    rf"[ \t]*(?:#[^\r\n]*)?(?:\r\n|\n|\r)"  # a blank or comment line
    rf"|[ \t]*{_KEY}(?:{_SINGLE}|{_DOUBLE}){_TAIL}"
    rf"|[ \t]*{_KEY}(?!['\"])([^\r\n]*)(?:\r\n|\n|\r|$)"  # an unquoted value
    rf"|[^\r\n]*(?:\r\n|\n|\r|$)"  # anything else: skipped
)
_SINGLE_ESCAPES = re.compile(r"\\([\\'])")
_DOUBLE_ESCAPES = re.compile(r"\\([\\'\"abfnrtv])")
_CONTROL = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_TRAILING_COMMENT = re.compile(r"\s+#.*")


def _entries(text: str) -> dict[str, str]:
    """Key -> value, in file order, a later duplicate replacing the earlier one's value. A key
    with no `=` has no value and is left out."""
    entries: dict[str, str] = {}
    position = 0
    while position < len(text):
        match = _STATEMENT.match(text, position)
        assert match is not None  # the last alternative matches anything
        position = max(match.end(), position + 1)
        if match.group(1) is not None and match.group(3) is not None:
            entries[match.group(1)] = _DOUBLE_ESCAPES.sub(
                lambda m: _CONTROL.get(m.group(1), m.group(1)), match.group(3)
            )
        elif match.group(1) is not None:
            entries[match.group(1)] = _SINGLE_ESCAPES.sub(lambda m: m.group(1), match.group(2))
        elif match.group(4) is not None:
            entries[match.group(4)] = _TRAILING_COMMENT.sub("", match.group(5)).rstrip()
    return entries


class DotenvReader:
    """The i-th file of a request carries `doc_index` i: the order the code names its files in,
    which is their precedence (a later file overrides an earlier one, probe "env_file tuple").
    Keyed by file name (`.env`, `.env.<x>`, `<x>.env`), asked only for a file the code names."""

    reads_schema_sources = False

    def accepts(self, file_kind: str) -> bool:
        return file_kind == ".env" or file_kind.startswith(".env.") or file_kind.endswith(".env")

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        pairs: list[tuple[Document, list[Fact]]] = []
        for place, file in enumerate(request.files):
            content = file.read_bytes()
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                document = build_document(
                    file=file,
                    root=request.root,
                    module_id=request.module_id,
                    language="dotenv",
                    content=content,
                    partial=True,
                    partial_reason=f"not valid utf-8: {error}",
                )
                pairs.append((document, []))
                continue
            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language="dotenv",
                content=content,
            )
            facts: list[Fact] = [
                ConfigEntryFact(
                    document_id=document.document_id,
                    key_raw=key,
                    key_path=key,
                    value=value,
                    doc_index=place,
                )
                for key, value in _entries(text).items()
            ]
            pairs.append((document, facts))
        return pairs
