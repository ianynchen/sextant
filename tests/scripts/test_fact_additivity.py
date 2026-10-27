"""`scripts/probes/fact_additivity/run.py` strips each added key only where it lives.

It once stripped every added key by NAME at every depth, and `value` is a key the argument
grammar has always used: an argument's `value` vanished from the after line while the before
line kept it, so the first release to add a key to call sites with literal arguments
(`receiver_field`, 2026-10-26) read as "differs beyond the keys" on every such line. These
pin the narrower strip, on facts built here and on a two-tree comparison, so the committed
harness reproduces the proof it is run for.

`scripts/` carries no package `__init__.py`, so the module is loaded from its file path, as
`test_field_check.py` loads its own script.
"""

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "probes" / "fact_additivity" / "run.py"
)
_spec = importlib.util.spec_from_file_location("fact_additivity", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

_BEFORE_SITE = {
    "kind": "call_site",
    "ordinal": 0,
    "receiver": 4,
    "arguments": [
        {"kind": "int", "value": 0},
        {"kind": "lambda", "symbol": "a/B#c().", "source": 2},
    ],
}
_AFTER_SITE = {
    **_BEFORE_SITE,
    "receiver_field": "a/B#client.",
    "arguments": [
        {"kind": "int", "value": 0},
        {"kind": "lambda", "symbol": "a/B#c().", "source": 2, "captures": 1},
    ],
}


def test_a_key_is_stripped_where_it_lives_and_an_arguments_value_is_kept():
    assert harness.without_the_new_keys(_AFTER_SITE) == _BEFORE_SITE
    assert harness.carries_a_new_key(_AFTER_SITE)
    assert not harness.carries_a_new_key(_BEFORE_SITE)


def test_a_field_writes_own_value_is_stripped_but_not_a_call_sites_argument_value():
    write = {"kind": "field_write", "field": "a/B#f.", "value": {"kind": "string", "value": "x"}}
    assert harness.without_the_new_keys(write) == {"kind": "field_write", "field": "a/B#f."}
    assert harness.carries_a_new_key(write)


def _tree(root: Path, facts: list[dict]) -> Path:
    root.mkdir(parents=True)
    (root / "A.jsonl").write_text("".join(json.dumps(f) + "\n" for f in facts), encoding="utf-8")
    return root


def test_a_keyed_line_compares_as_additive_and_a_changed_argument_does_not(tmp_path: Path):
    before = _tree(tmp_path / "before", [_BEFORE_SITE])
    after = _tree(tmp_path / "after", [_AFTER_SITE])
    problems, identical, keyed, added, _ = harness.compare_trees(before, after)
    assert (problems, identical, keyed, added) == ([], 0, 1, 0)
    changed = {
        **_AFTER_SITE,
        "arguments": [{"kind": "int", "value": 9}, _AFTER_SITE["arguments"][1]],
    }
    moved = _tree(tmp_path / "moved", [changed])
    problems, _, keyed, _, _ = harness.compare_trees(before, moved)
    assert keyed == 0 and len(problems) == 1
