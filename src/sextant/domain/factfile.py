"""Fact files are JSONL, one file per source file (D00 §7). The document
record is the first line, so a fact file is self-describing."""

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import TypeAdapter

from sextant.domain.facts import Document, Fact

_FACT_ADAPTER: TypeAdapter[Fact] = TypeAdapter(Fact)


def _line(model: Document | Fact) -> str:
    # sort_keys and no whitespace: byte-identical output for identical facts (NFR-1).
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def config_fact_target(fact_root: Path, relative_path: str) -> Path:
    """Where a config document's fact file lives under `fact_root/config`.

    Appends `.jsonl` to the document's full relative path rather than
    swapping its suffix (`Path.with_suffix`): two source files that differ
    only in extension — `application.properties` and `application.yml`, the
    exact pair spring-web.yml's `config_model.sources` declares side by side
    — must not collapse onto one `application.jsonl` target, silently
    dropping whichever document `write_fact_file` wrote second."""
    return fact_root / "config" / (relative_path + ".jsonl")


def write_fact_file(path: Path, document: Document, facts: Iterable[Fact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_line(document)] + [_line(fact) for fact in facts]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_fact_file(path: Path) -> tuple[Document, list[Fact]]:
    raw = path.read_text(encoding="utf-8").splitlines()
    if not raw:
        raise ValueError(f"empty fact file: {path}")
    document = Document.model_validate_json(raw[0])
    facts = [_FACT_ADAPTER.validate_json(line) for line in raw[1:] if line]
    return document, facts
