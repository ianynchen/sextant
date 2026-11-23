"""No new word reaches Sextant without the user's approval (GUIDELINES §8.9, §1.1).

## The defect this makes permanent

On the Django plan (branch `cov/python-django`, 2026-11-22/23) an agent added catalog words,
an open-question kind and a truth rule during the work and reported them afterwards — although
§1.1 already forbade decide-then-inform for exactly this ("extending a set the spec calls
closed"). The rule was written, agreed and broken; §13.8 says such a rule needs enforcement,
because prose has already been tried and lost. This is that enforcement for the words it can
see; §8.9 names what it cannot see, and review is the control there.

## One file holds the truth

`vocabulary.yml` beside this file has three sections, and ANY diff of it is reviewed as an
approval (§8.9):

- `baseline` — the words on `main` on 2026-11-23, generated once by `_document()` and never
  regenerated, because regenerating is how a word would slip in;
- `approvals` — one entry per word added since: `word`, `where`, `approved_by`, `approved_on`
  (a date after 2026-11-23) and `reference`;
- `exemptions` — what is NOT a Sextant word, each with its reason: catalog mappings whose keys
  are data (`data_keyed_mappings`), catalog keys whose values are the framework's or the
  user's names (`open_value_keys`), and sets in a pinned module whose strings are not words
  (`not_vocabulary`). Kept beside the approvals, not in this file, so an exemption is as
  visible as an approval.

## What counts as a word

1. **Every mapping KEY used in a shipped catalog** (`src/sextant/catalogs/**/*.yml`), found by
   walking the parsed documents, except the keys of a data-keyed mapping (whose VALUES are
   still walked). Recorded by NAME, not by where the key sits: a known word reused in a new
   block is the reuse §8.8 rule 3 asks for. A new block still needs its own key name.
2. **The string VALUES of catalog keys.** Every key that takes a string value anywhere is in
   exactly ONE of three lists, and a key in none of them fails, so no key falls between them:
   `baseline.closed_value_keys` (every value pinned), `baseline.mixed_value_keys` (the values
   that are lower-case identifiers are pinned; the others — a separator, a config key, an
   upper-case HTTP verb — are skipped by that stated rule), or `exemptions.open_value_keys`.
   `arg<N>` is an argument position and is never recorded. A value under a data-keyed mapping
   counts under the mapping's own key (`repositories` -> `save`).
3. **The members of the closed sets in the two places that hold them** (`_PINNED`): every
   closed set in `domain/closed_sets.py`, the file the project names as the home of its closed
   sets (`test_source_rules.py` keeps the schema's sets there), and the open-question kinds,
   `QUESTIONS` in `application/resolve/open_questions.py`. A closed set is a module-level
   name, or a name in the body of a module-level class, whose value is a non-empty tuple,
   list, set or frozenset of strings, a dict whose keys are strings (its members are the keys
   and the string values without whitespace — a sentence is prose, not a word), a
   `Literal[...]` alias, or an `Enum` (its values). A dunder name is skipped.

**The rest of the code is NOT scanned, on purpose** (ruled by the user 2026-11-23). A word can
be written in code in too many forms — a single constant, a tuple of pairs, an inline
comparison — and three review rounds each found new ones; a scan that chases them all grows
without end and makes an approval of every new table. A word in other code is controlled by
the principles check and by review (§8.9). A closed set of PUBLISHED words belongs in
`domain/closed_sets.py`, where this test sees it.

When in doubt a key is vocabulary: a false exemption hides a word, a false pin costs one
approval. The baseline is compared with the live words in both directions: a word removed
from the code fails until the file drops it, and a set that MOVES says so.

It is OFFLINE and deterministic: it reads the shipped catalogs and imports the pinned modules.
"""

import ast
import datetime
import enum
import importlib
import re
import typing
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).parents[2]
SRC = REPO / "src"
CATALOGS = SRC / "sextant" / "catalogs"
VOCABULARY = Path(__file__).parent / "vocabulary.yml"
FILE = "tests/architecture/vocabulary.yml"

CATALOG_KEY = "catalog key"
CATALOG_VALUE = "catalog value: "
RULE_DATE = datetime.date(2026, 11, 23)

# Module -> the names pinned in it; None is every closed set the module defines.
_PINNED: Mapping[str, frozenset[str] | None] = {
    "sextant.domain.closed_sets": None,
    "sextant.application.resolve.open_questions": frozenset({"QUESTIONS"}),
}

_POSITION = re.compile(r"arg\d+")
_WORD = re.compile(r"[a-z][a-z0-9_]*")
_APPROVAL_FIELDS = ("word", "where", "approved_by", "approved_on", "reference")
_ASK = (
    "GUIDELINES §8.9 requires the principles check and the user's approval; add an approval "
    "entry with approved_by/approved_on/reference to tests/architecture/vocabulary.yml, or — "
    "only for something that is not a Sextant word — an exemption with its reason; either is "
    "reviewed as an approval (GUIDELINES §8.9)"
)


def _file() -> dict[str, Any]:
    return yaml.safe_load(VOCABULARY.read_text(encoding="utf-8"))


def _data_keyed(exemptions: Mapping[str, Any]) -> set[tuple[str, ...]]:
    return {tuple(path.split(".")) for path in exemptions.get("data_keyed_mappings") or {}}


def _catalog_words(
    root: Path, exemptions: Mapping[str, Any]
) -> tuple[set[str], dict[str, set[str]], set[tuple[str, ...]]]:
    """Every key name under `root`, every string value by the key that holds it (positions
    left out), and the data-keyed paths that were seen."""
    data_keyed = _data_keyed(exemptions)
    keys: set[str] = set()
    values: dict[str, set[str]] = {}
    seen: set[tuple[str, ...]] = set()

    def walk(node: Any, path: tuple[str, ...], holder: str | None) -> None:
        if isinstance(node, dict):
            data = path in data_keyed
            if data:
                seen.add(path)
            for key, value in node.items():
                if not data:
                    keys.add(str(key))
                walk(value, (*path, str(key)), holder if data else str(key))
        elif isinstance(node, list):
            for value in node:
                walk(value, path, holder)
        elif isinstance(node, str) and holder is not None:
            words = values.setdefault(holder, set())
            if not _POSITION.fullmatch(node):
                words.add(node)

    for path in sorted(root.rglob("*.yml")):
        walk(yaml.safe_load(path.read_text(encoding="utf-8")), (), None)
    return keys, values, seen


def _literal(value: Any) -> set[str] | None:
    value = getattr(value, "__value__", value)  # a `type X = Literal[...]` alias
    if typing.get_origin(value) is typing.Literal:
        return {str(one) for one in typing.get_args(value)}
    return None


def _members(value: Any) -> set[str] | None:
    """The words a closed set holds, or None when the value is not a closed set of strings."""
    if isinstance(value, type) and issubclass(value, enum.Enum):
        return {str(member.value) for member in value}
    if isinstance(value, tuple | list | set | frozenset) and value:
        return {str(one) for one in value} if all(isinstance(one, str) for one in value) else None
    if isinstance(value, Mapping) and value and all(isinstance(one, str) for one in value):
        words = {one for one in value.values() if isinstance(one, str) and not one.split()[1:]}
        return {str(one) for one in value} | words
    return _literal(value)


def _assigned(body: list[ast.stmt]) -> list[str]:
    names: list[str] = []
    for node in body:
        if isinstance(node, ast.Assign):
            names += [one.id for one in node.targets if isinstance(one, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.TypeAlias):
            names.append(node.name.id)
    return [name for name in names if not (name.startswith("__") and name.endswith("__"))]


def _closed_sets(
    modules: Mapping[str, frozenset[str] | None] | None = None,
    exemptions: Mapping[str, Any] | None = None,
) -> dict[str, set[str]]:
    """Every pinned closed set each module DEFINES (an import is the defining module's), by
    `where`."""
    exemptions = _file()["exemptions"] if exemptions is None else exemptions
    excluded = exemptions.get("not_vocabulary") or {}
    found: dict[str, set[str]] = {}
    for name, pinned in (_PINNED if modules is None else modules).items():
        module = importlib.import_module(name)
        path = Path(module.__file__)
        prefix = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        candidates = [(one, getattr(module, one, None)) for one in _assigned(tree.body)]
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            owner = getattr(module, node.name, None)
            if isinstance(owner, type) and issubclass(owner, enum.Enum):
                candidates.append((node.name, owner))
            else:
                candidates += [
                    (f"{node.name}.{one}", getattr(owner, one, None))
                    for one in _assigned(node.body)
                ]
        for one, value in candidates:
            members = _members(value)
            where = f"{prefix}::{one}"
            if members and where not in excluded and (pinned is None or one in pinned):
                found[where] = members
    return found


def _live(document: dict[str, Any], root: Path = CATALOGS) -> dict[str, set[str]]:
    """The live words, by `where`, for the keys and sets `document` declares."""
    baseline, exemptions = document.get("baseline") or {}, document.get("exemptions") or {}
    keys, values, _ = _catalog_words(root, exemptions)
    live: dict[str, set[str]] = {CATALOG_KEY: keys}
    for key in baseline.get("closed_value_keys") or {}:
        live[CATALOG_VALUE + key] = values.get(key, set())
    for key in baseline.get("mixed_value_keys") or {}:
        live[CATALOG_VALUE + key] = {one for one in values.get(key, set()) if _WORD.fullmatch(one)}
    return {**live, **_closed_sets(None if root == CATALOGS else {}, exemptions)}


def _unlisted_value_keys(document: dict[str, Any], root: Path = CATALOGS) -> list[str]:
    """A key that takes string values and is in none, or more than one, of the three lists."""
    baseline, exemptions = document.get("baseline") or {}, document.get("exemptions") or {}
    _, values, _ = _catalog_words(root, exemptions)
    lists = {
        "baseline.closed_value_keys": set(baseline.get("closed_value_keys") or {}),
        "baseline.mixed_value_keys": set(baseline.get("mixed_value_keys") or {}),
        "exemptions.open_value_keys": set(exemptions.get("open_value_keys") or {}),
    }
    found = []
    for key in sorted(values):
        holding = [name for name, keys in lists.items() if key in keys]
        if len(holding) != 1:
            found.append(
                f"catalog key {key!r} takes string values and is in {holding or 'none'} of "
                f"{', '.join(lists)} in {FILE}: put it in exactly one — closed or mixed pins its "
                "words, open needs a reason; " + _ASK.split("; ", 1)[0]
            )
    for name, keys in lists.items():
        for key in sorted(keys - set(values)):
            found.append(
                f"{name} lists {key!r}, which no shipped catalog uses: delete it from {FILE}"
            )
    return found


def _document() -> dict[str, Any]:
    """The baseline for the words on `main`, with no approvals — run once, 2026-11-23."""
    file = _file()
    exemptions = file["exemptions"]
    keys, values, _ = _catalog_words(CATALOGS, exemptions)
    declared = file["baseline"]
    sets = _closed_sets(None, exemptions)
    return {
        "baseline": {
            "catalog_keys": sorted(keys),
            "closed_value_keys": {
                key: sorted(values[key]) for key in sorted(declared["closed_value_keys"])
            },
            "mixed_value_keys": {
                key: sorted(one for one in values[key] if _WORD.fullmatch(one))
                for key in sorted(declared["mixed_value_keys"])
            },
            "closed_sets": {where: sorted(sets[where]) for where in sorted(sets)},
        },
        "approvals": [],
        "exemptions": exemptions,
    }


def _expected_baseline(baseline: dict[str, Any]) -> dict[str, set[str]]:
    expected = {CATALOG_KEY: set(baseline.get("catalog_keys") or [])}
    for section in ("closed_value_keys", "mixed_value_keys"):
        for key, words in (baseline.get(section) or {}).items():
            expected[CATALOG_VALUE + key] = set(words or [])
    for where, words in (baseline.get("closed_sets") or {}).items():
        expected[where] = set(words)
    return expected


def problems(live: dict[str, set[str]], document: dict[str, Any]) -> list[str]:
    """What differs between the live words and `document`'s baseline + approvals, as instructions."""
    found: list[str] = []
    baseline = document.get("baseline") or {}
    expected = _expected_baseline(baseline)
    recorded = set(expected)
    approved: set[tuple[str, str]] = set()
    for index, entry in enumerate(document.get("approvals") or []):
        entry = entry if isinstance(entry, dict) else {}
        missing = [one for one in _APPROVAL_FIELDS if not entry.get(one)]
        on = entry.get("approved_on")
        if "approved_on" not in missing and not (isinstance(on, datetime.date) and on > RULE_DATE):
            missing.append("approved_on (a date after 2026-11-23, YYYY-MM-DD)")
        if missing:
            found.append(
                f"approval entry {index} ({entry.get('word')!r}) lacks {', '.join(missing)}: "
                "GUIDELINES §8.9 requires word, where, approved_by, approved_on and reference"
            )
            continue
        word, where = str(entry["word"]), str(entry["where"])
        if word in expected.get(where, set()) or (where, word) in approved:
            found.append(
                f"approval entry {index}: {word!r} in {where} is already recorded; delete it"
            )
        approved.add((where, word))
    for where, word in approved:
        expected.setdefault(where, set()).add(word)

    # A set whose name vanished from one module and appeared, same words, in another moved.
    gone = {where.split("::")[-1]: where for where in recorded - set(live) if "::" in where}
    moves = {
        new: gone[new.split("::")[-1]]
        for new in set(live) - recorded
        if new.split("::")[-1] in gone and live[new] == expected[gone[new.split("::")[-1]]]
    }
    for where in sorted(set(live) | set(expected)):
        if where in moves.values():
            continue
        if where in moves:
            found.append(
                f"closed set moved from {moves[where]} to {where}: move its entry under "
                f"baseline.closed_sets in {FILE} to the new place"
            )
            continue
        here, wanted = live.get(where, set()), expected.get(where, set())
        for word in sorted(here - wanted):
            found.append(f"new word {word!r} in {where}: {_ASK}")
        for word in sorted(wanted - here):
            source = "approvals" if (where, word) in approved else "baseline"
            found.append(
                f"stale word {word!r} in {where}: it is no longer in the code; remove it from the "
                f"{source} in {FILE}"
            )
    return found


def stale_exemptions(document: dict[str, Any], root: Path = CATALOGS) -> list[str]:
    """An exemption that no longer matches anything, so it cannot hide a later word."""
    exemptions = document.get("exemptions") or {}
    _, _values, seen = _catalog_words(root, exemptions)
    found = [
        f"exemptions.data_keyed_mappings lists {'.'.join(path)}, which no shipped catalog "
        f"has: delete it from {FILE}"
        for path in sorted(_data_keyed(exemptions) - seen)
    ]
    if root != CATALOGS:
        return found
    every = _closed_sets(None, {})
    for where in sorted(exemptions.get("not_vocabulary") or {}):
        if where not in every:
            found.append(
                f"exemptions.not_vocabulary lists {where}, which is not a closed set in a pinned "
                f"module: delete the entry from {FILE}"
            )
    return found


def test_every_word_is_in_the_baseline_or_approved():
    document = _file()
    assert problems(_live(document), document) == []


def test_every_catalog_key_with_string_values_is_in_exactly_one_list():
    assert _unlisted_value_keys(_file()) == []


def test_every_exemption_still_matches_something():
    assert stale_exemptions(_file()) == []


# --- tests of the test: each failure it exists for, shown to happen ---------------------------

_SET = "src/m.py::_KINDS"
_FAKE = {CATALOG_KEY: {"owner", "method"}, CATALOG_VALUE + "url_is": {"pattern"}, _SET: {"a", "b"}}


def _baseline_of(
    live: dict[str, set[str]], approvals: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    baseline = {
        "catalog_keys": sorted(live[CATALOG_KEY]),
        "closed_value_keys": {
            where.removeprefix(CATALOG_VALUE): sorted(words)
            for where, words in live.items()
            if where.startswith(CATALOG_VALUE)
        },
        "closed_sets": {where: sorted(words) for where, words in live.items() if "::" in where},
    }
    return {"baseline": baseline, "approvals": approvals or [], "exemptions": {}}


def _approval(word: str, where: str, **override: Any) -> dict[str, Any]:
    entry = {
        "word": word,
        "where": where,
        "approved_by": "the user",
        "approved_on": datetime.date(2026, 11, 24),
        "reference": "spec 2026-11-24 §3",
    }
    return {key: value for key, value in {**entry, **override}.items() if value is not None}


def _edited_catalogs(tmp_path: Path, relative: str, old: str, new: str) -> Path:
    root = tmp_path / "catalogs"
    for path in CATALOGS.rglob("*.yml"):
        target = root / path.relative_to(CATALOGS)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    edited = root / relative
    text = edited.read_text(encoding="utf-8")
    assert old in text
    edited.write_text(text.replace(old, new, 1), encoding="utf-8")
    return root


def test_the_baseline_alone_passes():
    assert problems(_FAKE, _baseline_of(_FAKE)) == []


def test_a_new_catalog_key_fails_with_the_instruction():
    live = {**_FAKE, CATALOG_KEY: {"owner", "method", "mount_kind"}}
    assert problems(live, _baseline_of(_FAKE)) == [f"new word 'mount_kind' in catalog key: {_ASK}"]
    assert "either is reviewed as an approval (GUIDELINES §8.9)" in _ASK


def test_a_new_value_of_a_closed_value_key_fails_and_its_approval_passes():
    live = {**_FAKE, CATALOG_VALUE + "url_is": {"pattern", "expression"}}
    assert problems(live, _baseline_of(_FAKE)) == [
        f"new word 'expression' in catalog value: url_is: {_ASK}"
    ]
    approval = _approval("expression", CATALOG_VALUE + "url_is")
    assert problems(live, _baseline_of(_FAKE, [approval])) == []


def test_a_new_join_word_in_a_mixed_key_fails_on_the_real_catalogs(tmp_path: Path):
    root = _edited_catalogs(
        tmp_path, "client-models/vertx-web.yml", "join: fill_authority", "join: brand_new_join"
    )
    document = _file()
    found = problems(_live(document, root), document)
    assert f"new word 'brand_new_join' in catalog value: join: {_ASK}" in found


def test_a_new_wire_word_fails_on_the_real_catalogs(tmp_path: Path):
    root = _edited_catalogs(
        tmp_path, "shape-models/json.yml", "wire: boolean }", "wire: flagword }"
    )
    document = _file()
    found = problems(_live(document, root), document)
    assert f"new word 'flagword' in catalog value: wire: {_ASK}" in found


def test_a_mixed_key_pins_its_words_and_skips_the_rest(tmp_path: Path):
    (tmp_path / "c.yml").write_text("join: [append_to_base, /, GET]\n", encoding="utf-8")
    document = {"baseline": {"mixed_value_keys": {"join": ["append_to_base"]}}, "exemptions": {}}
    assert _live(document, tmp_path)[CATALOG_VALUE + "join"] == {"append_to_base"}


def test_a_key_with_string_values_in_no_list_fails_and_in_two_lists_fails(tmp_path: Path):
    (tmp_path / "c.yml").write_text("join: fill_authority\nstyle: fluent\n", encoding="utf-8")
    document = {
        "baseline": {"closed_value_keys": {"style": []}, "mixed_value_keys": {"style": []}},
        "exemptions": {"open_value_keys": {"gone": "a reason"}},
    }
    found = _unlisted_value_keys(document, tmp_path)
    assert found[0].startswith("catalog key 'join' takes string values and is in none of")
    assert found[1].startswith(
        "catalog key 'style' takes string values and is in "
        "['baseline.closed_value_keys', 'baseline.mixed_value_keys'] of"
    )
    assert found[2] == (
        f"exemptions.open_value_keys lists 'gone', which no shipped catalog uses: delete it from {FILE}"
    )


def test_a_catalog_value_is_recorded_under_its_key_and_a_position_is_not_a_word(tmp_path: Path):
    (tmp_path / "c.yml").write_text(
        "matches:\n  repositories:\n    org.example.Repo: [save]\n"
        "  roots:\n    - { captures: { url_is: expression, url: arg0 } }\n",
        encoding="utf-8",
    )
    exemptions = {"data_keyed_mappings": {"matches.repositories": "fqn -> operations"}}
    keys, values, _ = _catalog_words(tmp_path, exemptions)
    assert values["url_is"] == {"expression"}
    assert values["url"] == set()
    assert values["repositories"] == {"save"}
    assert "org.example.Repo" not in keys


def test_a_new_closed_value_fails_and_its_approval_passes():
    live = {**_FAKE, _SET: {"a", "b", "c"}}
    assert problems(live, _baseline_of(_FAKE)) == [f"new word 'c' in {_SET}: {_ASK}"]
    assert problems(live, _baseline_of(_FAKE, [_approval("c", _SET)])) == []


def test_a_new_closed_set_fails_for_each_member():
    live = {**_FAKE, "src/m.py::_NEW": {"x", "y"}}
    assert problems(live, _baseline_of(_FAKE)) == [
        f"new word 'x' in src/m.py::_NEW: {_ASK}",
        f"new word 'y' in src/m.py::_NEW: {_ASK}",
    ]


def test_a_moved_closed_set_says_to_move_its_entry():
    live = {key: value for key, value in _FAKE.items() if key != _SET}
    live["src/n.py::_KINDS"] = {"a", "b"}
    assert problems(live, _baseline_of(_FAKE)) == [
        (
            f"closed set moved from {_SET} to src/n.py::_KINDS: move its entry under "
            f"baseline.closed_sets in {FILE} to the new place"
        )
    ]


def test_a_word_removed_from_the_code_fails_until_removed_from_the_file():
    live = {**_FAKE, CATALOG_KEY: {"owner"}}
    assert problems(live, _baseline_of(_FAKE)) == [
        (
            f"stale word 'method' in catalog key: it is no longer in the code; remove it from the "
            f"baseline in {FILE}"
        )
    ]


def test_a_stale_approval_entry_fails():
    assert problems(_FAKE, _baseline_of(_FAKE, [_approval("gone", CATALOG_KEY)])) == [
        (
            f"stale word 'gone' in catalog key: it is no longer in the code; remove it from the "
            f"approvals in {FILE}"
        )
    ]


def test_an_approval_missing_a_field_fails_and_approves_nothing():
    live = {**_FAKE, CATALOG_KEY: {"owner", "method", "mount_kind"}}
    entry = _approval("mount_kind", CATALOG_KEY, approved_by=None)
    found = problems(live, _baseline_of(_FAKE, [entry]))
    assert found[0].startswith("approval entry 0 ('mount_kind') lacks approved_by")
    assert found[1].startswith("new word 'mount_kind' in catalog key")


def test_an_approval_date_must_be_a_date_after_the_rule():
    for when in ("yesterday", datetime.date(2026, 11, 23), datetime.date(2026, 1, 1)):
        (only,) = problems(_FAKE, _baseline_of(_FAKE, [_approval("c", _SET, approved_on=when)]))
        assert "lacks approved_on (a date after 2026-11-23, YYYY-MM-DD)" in only


def test_an_approval_of_a_baseline_word_fails():
    (only,) = problems(_FAKE, _baseline_of(_FAKE, [_approval("a", _SET)]))
    assert only == f"approval entry 0: 'a' in {_SET} is already recorded; delete it"


def test_a_key_under_a_data_keyed_mapping_is_not_a_word_but_its_value_keys_are(tmp_path: Path):
    (tmp_path / "c.yml").write_text(
        "matches:\n  repositories:\n    org.example.Repo: [save]\n"
        "  indexed:\n    item:\n      requirements:\n        Header: { kind: header }\n",
        encoding="utf-8",
    )
    exemptions = {
        "data_keyed_mappings": {
            "matches.repositories": "fqn -> operations",
            "matches.indexed.item.requirements": "factory name -> reader",
        }
    }
    keys, _, _ = _catalog_words(tmp_path, exemptions)
    assert keys == {"matches", "repositories", "indexed", "item", "requirements", "kind"}


def test_a_module_scan_sees_class_body_sets_literal_aliases_and_lower_case_names(
    tmp_path: Path, monkeypatch: Any
):
    (tmp_path / "fake_words.py").write_text(
        "from typing import Literal\n"
        "Kind = Literal['one', 'two']\n"
        "type Mode = Literal['fast']\n"
        "kinds = frozenset({'x'})\n"
        "PROSE = {'gap_id': 'a sentence for a reader'}\n"
        "__all__ = ['Kind']\n"
        "class Holder:\n"
        "    WORDS = ('held', 'pending')\n"
        "    __slots__ = ('a',)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert _closed_sets({"fake_words": frozenset({"kinds"})}, {}) == {"fake_words.py::kinds": {"x"}}
    found = _closed_sets({"fake_words": None}, {})
    assert found == {
        "fake_words.py::Kind": {"one", "two"},
        "fake_words.py::Mode": {"fast"},
        "fake_words.py::kinds": {"x"},
        "fake_words.py::PROSE": {"gap_id"},
        "fake_words.py::Holder.WORDS": {"held", "pending"},
    }


def test_each_exemption_list_fails_when_stale(tmp_path: Path):
    (tmp_path / "c.yml").write_text("style: fluent\n", encoding="utf-8")
    document = {"exemptions": {"data_keyed_mappings": {"matches.gone": "a reason"}}}
    assert stale_exemptions(document, tmp_path) == [
        (
            f"exemptions.data_keyed_mappings lists matches.gone, which no shipped catalog has: "
            f"delete it from {FILE}"
        )
    ]
    document = {"exemptions": {"not_vocabulary": {"src/sextant/domain/gone.py::_X": "a reason"}}}
    assert stale_exemptions(document) == [
        (
            "exemptions.not_vocabulary lists src/sextant/domain/gone.py::_X, which is not a closed "
            f"set in a pinned module: delete the entry from {FILE}"
        )
    ]


def test_the_pinned_places_are_the_closed_sets_file_and_the_question_kinds():
    found = _closed_sets()
    places = {where.split("::")[0] for where in found}
    assert places == {
        "src/sextant/domain/closed_sets.py",
        "src/sextant/application/resolve/open_questions.py",
    }
    assert "resolved" in found["src/sextant/domain/closed_sets.py::Resolution"]
    questions = "src/sextant/application/resolve/open_questions.py"
    assert [where for where in found if where.startswith(questions)] == [f"{questions}::QUESTIONS"]
    assert "payload_binding" in found[f"{questions}::QUESTIONS"]
