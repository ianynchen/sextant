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


def schema_fact_target(fact_root: Path, relative_path: str) -> Path:
    """Where a schema document's facts live under `fact_root/schema` — the
    same append-the-full-path, keep-the-source-extension discipline
    `config_fact_target` keeps for a config document, in its own subtree so a
    schema file never competes with a same-named config file for one target
    (2F's collision rule, generalized)."""
    return fact_root / "schema" / (relative_path + ".jsonl")


def read_fact_tree(fact_root: Path) -> list[tuple[Document, list[Fact]]]:
    """Every fact file already written under `fact_root`, read back. The
    means by which a later stage — `analyze`'s descriptor interpretation,
    which needs to see the `embedded_descriptor` facts a scanner already
    wrote to disk before it ever calls this — can read the fact tree without
    touching the filesystem itself (ARCHITECTURE §10's application-reads-no-
    files rule, `test_application_reads_no_files`). Sorted by path for
    NFR-1: two runs over the same tree read facts in the same order
    regardless of the filesystem's own directory-entry order."""
    return [read_fact_file(path) for path in sorted(fact_root.rglob("*.jsonl"))]


def append_fact_file(path: Path, document: Document, facts: Iterable[Fact]) -> None:
    """Adds `facts` to the fact file at `path`, which may already carry some
    (a schema reader's own document, given `declared_shape` facts later in
    the same `analyze` run) or may not exist yet at all (a compiled
    document's facts live wherever the scanner wrote them, never under this
    path, so the first write here creates it). Either way the result keeps
    `write_fact_file`'s self-describing invariant: `document` first, every
    fact — old and new — after it."""
    existing: list[Fact] = []
    if path.is_file():
        _, existing = read_fact_file(path)
    write_fact_file(path, document, [*existing, *facts])
