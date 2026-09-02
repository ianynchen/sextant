"""`redact_config_entry_line` (2K Task 7 fix round 2, CRITICAL): the one
place "a `config_entry` fact's value, masked by its own key" is expressed,
shared by the bundle export path (`storage/duckdb/workspace.py`) and the
enrichment jail's fact-serving path (`application/enrich/tools.py`) —
neither carries its own copy of this shape. Both call sites get their own
integration-level coverage (`tests/storage/test_workspace.py`,
`tests/application/test_enrich_tools.py`); this file is the direct,
edge-case coverage of the shared function itself."""

import json

from sextant.domain.factfile import redact_config_entry_line
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
