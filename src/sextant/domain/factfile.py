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
    dumped = model.model_dump(mode="json")
    # A document with no `origin` carries no `origin` KEY, rather than one
    # spelled null: the extractor omits it for a module's own output, and this
    # writer rewrites documents the extractor already wrote (`analyze`'s
    # descriptor interpretation writes shape facts back into their own fact
    # file). Dumping the field unconditionally would make every rewritten
    # module document differ from the one on disk beside it — a byte change in
    # a module that has no library to extract at all (NFR-1).
    if isinstance(model, Document) and dumped["origin"] is None:
        del dumped["origin"]
    return json.dumps(dumped, sort_keys=True, separators=(",", ":"))


def config_fact_target(fact_root: Path, relative_path: str) -> Path:
    """Where a config document's fact file lives under `fact_root/config`.

    Appends `.jsonl` to the document's full relative path rather than
    swapping its suffix (`Path.with_suffix`): two source files that differ
    only in extension — `application.properties` and `application.yml`, the
    exact pair spring-web.yml's `config_model.sources` declares side by side
    — must not collapse onto one `application.jsonl` target, silently
    dropping whichever document `write_fact_file` wrote second."""
    return fact_root / "config" / (relative_path + ".jsonl")


def library_fact_root(fact_root: Path, coordinate: str) -> Path:
    """Where one extracted library's fact files live: `facts/lib/<groupId>/
    <artifactId>/`, with the scanner's own class-relative tree underneath.

    Its own subtree, for `schema_fact_target`'s reason generalised: a library
    is free to ship a class whose package matches one of the module's own, and
    two documents competing for one fact-file target leave only the second on
    disk. The coordinate's single `:` becomes the separator between the two
    segments, which is collision-free rather than merely tidy — neither half of
    a coordinate may contain a separator (`ingress/detect/sextant_config.py`
    refuses one that does), so no two coordinates can compose one path.
    """
    if ":" not in coordinate or "/" in coordinate or "\\" in coordinate:
        raise ValueError(f"not a library coordinate: {coordinate!r}")
    group, _, artifact = coordinate.partition(":")
    return fact_root / "lib" / group / artifact


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


def read_fact_tree(fact_root: Path) -> list[tuple[Path, Document, list[Fact]]]:
    """Every fact file already written under `fact_root`, read back — the
    path included, not only its content: a later stage that adds facts to a
    document already on disk (`analyze`'s descriptor interpretation) must
    write them back into that SAME file, never mint a second one — D00 §7
    permits exactly one document record per source file, and a second file
    carrying the identical `Document` would double-count it wherever the
    workspace counts documents. The means by which that stage can read the
    fact tree at all without touching the filesystem itself (ARCHITECTURE
    §10's application-reads-no-files rule, `test_application_reads_no_files`).
    Sorted by path for NFR-1: two runs over the same tree read facts in the
    same order regardless of the filesystem's own directory-entry order."""
    paths = sorted(fact_root.rglob("*.jsonl"))
    return [(path, *read_fact_file(path)) for path in paths]
