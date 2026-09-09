"""Fact files are JSONL, one file per source file (D00 §7). The document
record is the first line, so a fact file is self-describing."""

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from pydantic import TypeAdapter

from sextant.domain.facts import Document, Fact
from sextant.domain.redaction import Redactor

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


def redact_config_entry_line(
    payload_json: str, redactor: Redactor, *, compact: bool = False
) -> str:
    """One fact-file LINE's own JSON payload, with its `value` masked by
    `redactor.redact_value` when — and only when — the line is a
    `config_entry` fact (2K Task 7 fix round 2, CRITICAL). The one place "a
    config_entry's value, masked by its OWN key" is expressed, so the bundle
    export path (`storage/duckdb/workspace.py`'s `_stage_fact_redactions`,
    2K Task 1) and the enrichment jail's fact-serving path
    (`application/enrich/tools.py`, 2K Task 5/7) call the SAME function
    rather than each carrying its own copy of the same shape — a value
    masked leaving through one door and not the other is exactly the gap
    spec §1 names "config-entry facts served by tools" to close.

    Anything else — a line that is not valid JSON, whose `kind` is not
    `config_entry`, or whose `value` is absent — is returned UNCHANGED, byte
    for byte: this is a targeted rewrite of one fact kind's one field, never
    a JSON-wide transform, and a line this cannot parse is not this
    function's business to reject (the caller decides what an unparseable
    line means for its own purpose).

    `compact` picks the re-serialization spelling (2K Task 7 fix round 3,
    minor 2) — the two callers want two different ones, and getting either
    wrong is observable: the bundle export's default (`ensure_ascii=False`,
    default separators) is proven byte-compatible with 2K Task 1's own pins
    and MUST NOT change; the jail's fact-serving path wants `compact=True`
    — `_line`'s own spelling (`sort_keys=True, separators=(",", ":")`,
    `ensure_ascii` at its default) — so a masked line matches the style of
    the UNMASKED neighbours around it in the same served file, which
    `_line` wrote in that style to begin with.

    Leaving `ensure_ascii` at its default (True) means a `compact=True`
    line's `«redacted»` marker is written JSON-escaped — `\\u00abredacted
    \\u00bb`, never the literal guillemets — exactly as `_line` spells any
    non-ASCII byte on disk: a grep over compact-served content (the jail's
    own fact-serving path) has to match the escaped spelling, not
    `REDACTED` itself.
    """
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return payload_json
    if not isinstance(payload, dict) or payload.get("kind") != "config_entry":
        return payload_json
    value = payload.get("value")
    if value is None:
        return payload_json
    masked = redactor.redact_value(str(payload.get("key_path")), str(value))
    if masked == str(value):
        return payload_json
    payload["value"] = masked
    if compact:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False)


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


def discard_library_facts(fact_root: Path, coordinate: str | None = None) -> None:
    """Remove the library fact subtree — the whole of it, or one coordinate's.

    A fact file is written whole and never appended to, so a document that is
    re-scanned overwrites itself. A library that is no longer scanned overwrites
    NOTHING, and that is the difference this exists for: a run whose
    `.sextant.yml` was edited or deleted would otherwise read the previous run's
    library facts straight back out of the same workspace and derive rows for a
    library nobody opted into any more. **Opting out has to retract**, or the
    opt-in is not a decision the reader can reverse.

    Also the only correct answer to a scan that FAILED partway through an
    archive: the extractor writes each class's fact file as it goes, so a
    failure at the tenth entry leaves nine documents claiming to describe a
    library nothing successfully read. Discarding that coordinate's subtree is
    what makes the failure total rather than partial — a fraction of a library,
    indistinguishable from all of a smaller one, is exactly the silent wrongness
    the surrounding honesty rules exist to refuse.

    Missing directories are not an error: nothing to retract is the ordinary
    case, and it is the same answer as having retracted it.
    """
    target = fact_root / "lib"
    if coordinate is not None:
        target = library_fact_root(fact_root, coordinate)
    shutil.rmtree(target, ignore_errors=True)


def discard_scanned_facts(fact_root: Path, classes_dir: Path) -> None:
    """Remove every fact file a PREVIOUS scan of `origin_entry` left behind.

    `discard_library_facts` above, generalised to the module's own classes, and for its
    own stated reason: *a fact file is written whole and never appended to, so a document
    that is re-scanned overwrites itself — one that is no longer scanned overwrites
    NOTHING.* A class that was deleted, renamed, or moved to another package is exactly
    that case, and without this its facts stay in the workspace and keep deriving rows
    for source that is not there.

    **Measured, in this repo's own fixture:** `Shapes.jsonl` survived the class being
    renamed and went on contributing two inbound Pub/Sub endpoints — 143 endpoints from
    the fixture's own `.sextant` workspace against 141 from a fresh one, on identical
    source. Two runs of one command over one input disagreeing is NFR-1; publishing a
    boundary for a class that does not exist is worse than that, and it is silent.

    **Keyed on the document's own `origin_entry`, not on a list of the directories other
    writers own.** The scanner stamps each document with the classes directory it read
    (the extractor's `--classes`), so this retracts exactly what a scan of that directory
    wrote and cannot reach a config or schema document written from a `src` root,
    whatever subtree a later phase adds. A rule spelled "delete everything except `lib`,
    `config` and `schema`" would delete the next subtree somebody adds without one line
    of this file changing.

    Compared as RESOLVED paths, so a workspace first written through a relative path and
    re-analysed through an absolute one still retracts. Where a stale value resolves to
    something else the file is left alone: failing to retract repeats the behaviour this
    replaces, while deleting a fact file this scan does not own loses a document nothing
    will rewrite.

    Only the document record is read — the first line, which is what makes a fact file
    self-describing (D00 §7) — so this costs one line per file rather than a parse of
    every fact in the tree.
    """
    if not fact_root.exists():
        return
    target = classes_dir.resolve()
    for path in sorted(fact_root.rglob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as handle:
                first = handle.readline()
            record = json.loads(first)
        except (OSError, json.JSONDecodeError):
            # Unreadable or not JSONL: not something a scan of this entry wrote, and
            # deleting a file nothing here can identify is the destructive guess.
            continue
        entry = record.get("origin_entry")
        if not isinstance(entry, str):
            continue
        if entry == str(classes_dir) or Path(entry).resolve() == target:
            path.unlink(missing_ok=True)


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
