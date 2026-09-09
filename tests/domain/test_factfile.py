"""`redact_config_entry_line` (2K Task 7 fix round 2, CRITICAL): the one
place "a `config_entry` fact's value, masked by its own key" is expressed,
shared by the bundle export path (`storage/duckdb/workspace.py`) and the
enrichment jail's fact-serving path (`application/enrich/tools.py`) —
neither carries its own copy of this shape. Both call sites get their own
integration-level coverage (`tests/storage/test_workspace.py`,
`tests/application/test_enrich_tools.py`); this file is the direct,
edge-case coverage of the shared function itself."""

import json
from pathlib import Path

from sextant.domain.factfile import discard_scanned_facts, redact_config_entry_line
from sextant.domain.redaction import Redactor

_REDACTOR = Redactor.from_rules()


def _line(**overrides: object) -> str:
    payload = {
        "kind": "config_entry",
        "document_id": "d",
        "key_raw": "db.password",
        "key_path": "orders.db.password",
        "value": "hunter2",
        "doc_index": 0,
        **overrides,
    }
    return json.dumps(payload)


def test_a_key_matching_a_built_in_pattern_masks_the_value():
    masked = redact_config_entry_line(_line(), _REDACTOR)
    payload = json.loads(masked)
    assert payload["value"] == "«redacted»"
    assert payload["key_path"] == "orders.db.password"  # the key itself is never touched


def test_a_key_matching_nothing_is_returned_byte_identical():
    line = _line(key_path="orders.public.name", value="orders-service")
    assert redact_config_entry_line(line, _REDACTOR) == line


def test_a_non_config_entry_kind_is_returned_byte_identical():
    line = json.dumps({"kind": "symbol", "document_id": "d", "symbol": "com/acme/Order#"})
    assert redact_config_entry_line(line, _REDACTOR) == line


def test_a_line_that_is_not_valid_json_is_returned_byte_identical():
    """A `read_file` window can cut a fact line in half — the caller's
    problem to worry about, never this function's to raise over."""
    line = '{"kind":"config_entry","key_path":"a.password","value":"hun'
    assert redact_config_entry_line(line, _REDACTOR) == line


def test_json_that_is_not_an_object_is_returned_byte_identical():
    line = json.dumps(["config_entry", "not", "an", "object"])
    assert redact_config_entry_line(line, _REDACTOR) == line


def test_a_config_entry_with_no_value_is_returned_byte_identical():
    line = _line(value=None)
    assert redact_config_entry_line(line, _REDACTOR) == line


def test_compact_masking_matches_the_writers_own_serialization_style():
    """2K Task 7 fix round 3, minor 2: `compact=True` must reproduce
    `_line`'s own spelling exactly — `sort_keys=True`, no whitespace after
    `:`/`,`, `ensure_ascii` at its default (so a non-ASCII masking marker is
    escaped the same way an unmasked neighbour's own non-ASCII value would
    be) — so a masked line never stands out from the unmasked lines beside
    it in the same served fact file. The DEFAULT (export) spelling stays
    the byte-compatibility promise it always was, proven separately by
    `tests/storage/test_workspace.py`."""
    unmasked = _line()
    compact = redact_config_entry_line(unmasked, _REDACTOR, compact=True)
    default = redact_config_entry_line(unmasked, _REDACTOR)
    assert compact != default  # sanity: the two spellings really do differ
    assert compact == json.dumps(json.loads(compact), sort_keys=True, separators=(",", ":"))
    assert "«" not in compact and "\\u00ab" in compact  # ensure_ascii at its default


# A class that is deleted, renamed, or moved to another package overwrites nothing —
# a fact file is written whole, never appended to — so its facts stay in the workspace
# and keep deriving rows for source that is not there. Measured in this repo's own
# fixture: a renamed `Shapes` class went on publishing two inbound Pub/Sub endpoints,
# 143 endpoints from the fixture's own `.sextant` workspace against 141 from a fresh
# one, on identical source (W26).
_CLASSES = "build/classes"


def _fact_file(path: Path, origin_entry: str) -> Path:
    """One fact file, self-describing: the document record is its first line (D00 §7),
    and `origin_entry` is what says which scan wrote it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"kind": "document", "origin_entry": origin_entry}) + "\n",
        encoding="utf-8",
    )
    return path


def test_a_previous_scans_fact_file_is_retracted(tmp_path: Path):
    root = tmp_path / "facts"
    stale = _fact_file(root / "com" / "acme" / "Gone.jsonl", _CLASSES)

    discard_scanned_facts(root, Path(_CLASSES))

    assert not stale.exists(), (
        "a class no longer compiled must not keep deriving rows from the last run"
    )


def test_the_same_directory_spelled_differently_is_still_this_scans_own(tmp_path: Path):
    """A workspace first written through a relative path and re-analysed through an
    absolute one still retracts — the comparison is on resolved paths, not on the
    string the last run happened to use."""
    root = tmp_path / "facts"
    stale = _fact_file(root / "com" / "acme" / "Gone.jsonl", _CLASSES)

    discard_scanned_facts(root, Path(_CLASSES).resolve())

    assert not stale.exists()


def test_a_fact_file_another_writer_owns_is_left_alone(tmp_path: Path):
    """The near-miss, and the one worth being sure of: retracting is deleting, and the
    only thing worse than keeping a stale document is losing a live one.

    Each of these is written from a DIFFERENT origin — a config document from a `src`
    root, a schema document from another, an extracted library from its jar — so none is
    this scan's to retract. Keying on the document's own origin rather than on "every
    subtree except `lib`, `config` and `schema`" is what makes that true of the next
    subtree somebody adds, too.
    """
    root = tmp_path / "facts"
    others = [
        _fact_file(root / "config" / "application.yml.jsonl", "src/main/resources"),
        _fact_file(root / "schema" / "order.avsc.jsonl", "src/main/avro"),
        _fact_file(root / "lib" / "com.acme" / "shared" / "Api.jsonl", "shared-1.0.jar"),
        _fact_file(root / "elsewhere" / "Later.jsonl", "some/future/root"),
    ]

    discard_scanned_facts(root, Path(_CLASSES))

    for path in others:
        assert path.exists(), f"{path} was not written by a scan of {_CLASSES}"


def test_a_file_that_says_nothing_identifiable_is_left_alone(tmp_path: Path):
    """Deleting a file nothing here can identify is the destructive guess. An empty
    file, one that is not JSON, and one whose first line is JSON without an
    `origin_entry` all survive."""
    root = tmp_path / "facts"
    root.mkdir(parents=True)
    empty = root / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    garbage = root / "garbage.jsonl"
    garbage.write_text("not json at all\n", encoding="utf-8")
    silent = root / "silent.jsonl"
    silent.write_text(json.dumps({"kind": "document"}) + "\n", encoding="utf-8")

    discard_scanned_facts(root, Path(_CLASSES))

    assert empty.exists() and garbage.exists() and silent.exists()


def test_a_missing_fact_root_is_not_an_error(tmp_path: Path):
    """Nothing to retract is the ordinary first run, and it is the same answer as
    having retracted it — `discard_library_facts`' own rule."""
    discard_scanned_facts(tmp_path / "never-written", Path(_CLASSES))
