"""No new word reaches Sextant without the user's approval (GUIDELINES §8.9, §1.1).

## The defect this makes permanent

On the Django plan (branch `cov/python-django`, 2026-11-22/23) an agent added catalog words,
an open-question kind and a truth rule during the work and reported them afterwards — although
§1.1 already forbade decide-then-inform for exactly this ("extending a set the spec calls
closed"). The rule was written, agreed and broken; §13.8 says such a rule needs enforcement,
because prose has already been tried and lost. This is that enforcement for the words: a word
cannot arrive silently in a diff.

## What counts as a word

Two kinds, compared against `vocabulary.yml` beside this file:

1. **Every mapping KEY used in a shipped catalog** (`src/sextant/catalogs/**/*.yml`), found by
   walking the parsed documents. The loader refuses a key it does not read, so the keys the
   shipped catalogs use are the catalog words in real use. Recorded by NAME, not by where
   the key sits: a known word reused in a new block (`{arg, keyword}` in a fortieth place) is
   the reuse §8.8 rule 3 asks for, and a ratchet that fired on it would punish exactly that.
   A new BLOCK still needs its own key name, and that name is caught.
2. **The members of every module-level closed set** in `_CLOSED_SET_MODULES`: each name
   spelled like a constant (`_?UPPER_CASE`) whose value is a non-empty tuple, list, set or
   frozenset of strings, or a dict whose keys are strings (the keys and the string values
   are its members), and each `Enum` class the module defines (its values). Found by reading
   the module, not by a list typed here, so a NEW closed set in one of these modules is
   caught on the day it appears: it is in neither the baseline nor `_NOT_VOCABULARY`, and
   every member reads as a new word. The modules were chosen as the homes of the words §8.9
   names — catalog structure (`yaml_source.py`), the published parts and `url_is`
   (`fluent.py`), open-question kinds, reasons, and the domain's closed sets with the
   resolution words (`closed_sets.py`). A closed set that moves to a module not listed here
   is not seen; a module that starts holding one is added to the list.

## What is data, not vocabulary

A catalog mapping whose keys are the FRAMEWORK's or the USER's names (a class, an annotation
attribute, a configured value, an argument position, a character) holds no Sextant word in
its keys: adding `org.example.NewRepository` to `repositories` is a catalog fact, not a new
concept. `_DATA_KEYED_MAPPINGS` lists each such mapping by its exact path, with the D02
statement that makes its keys data. Its VALUES are still walked, so a word nested under a
data key (`requirements.Header.kind`) is still a word. Exact paths, not a pattern: a new data
map elsewhere fails until someone adds it here with its reason, which is harder to slip than
a rule that guesses data from spelling. `_NOT_VOCABULARY` does the same for code constants.

## The baseline and the approvals

`vocabulary.yml` holds `baseline` — the words on `main` on 2026-11-23, generated once by
`_document()` and never regenerated, because regenerating is how a word would slip in — and
`approvals`, one entry per word added since, each naming `word`, `where`, `approved_by`,
`approved_on` and `reference`. The test compares the live words with baseline + approvals in
both directions: a new word with no entry fails, and an entry for a word that is gone fails,
so the file stays the truth. A word removed from the code is removed from the file by hand.
Editing `baseline` directly is a diff a reviewer sees; it is never the way to add a word.

It is OFFLINE and deterministic: it reads the shipped catalogs and imports five modules.
"""

import ast
import datetime
import enum
import importlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
VOCABULARY = Path(__file__).parent / "vocabulary.yml"

CATALOG_KEY = "catalog key"

_CLOSED_SET_MODULES = (
    "sextant.ingress.catalogs.yaml_source",
    "sextant.application.resolve.engines.fluent",
    "sextant.application.resolve.open_questions",
    "sextant.application.resolve.values",
    "sextant.domain.closed_sets",
)

# Each is `where` (see `_where`) -> why its members are not Sextant words.
_NOT_VOCABULARY = {
    "src/sextant/application/resolve/values.py::_UNCHANGEABLE": (
        "JVM type descriptors of immutable types (`Ljava/lang/String;`, `I`): Java's spelling"
    ),
    "src/sextant/application/resolve/values.py::_CALLABLES": (
        "Python's own symbols for a callable type (`typing/Callable#`): Python's names"
    ),
    "src/sextant/application/resolve/engines/fluent.py::_DIRECTIONS": (
        "computed from `Direction` at import; `Direction` is recorded itself"
    ),
    "src/sextant/domain/closed_sets.py::_RANKS": (
        "a rank per `Evidence` member; the words are `Evidence`'s, recorded there"
    ),
}

# Catalog mappings whose KEYS are framework or user data, by exact path from the document root
# (list items do not add a step), each with the D02 statement that makes them data.
_DATA_KEYED_MAPPINGS = {
    (
        "stereotype_name_attrs",
    ): "D02 §1c: stereotype annotation name -> the attribute naming the bean",
    ("matches", "entries", "arg_types"): "D02 §2: argument position -> parameter type",
    (
        "matches",
        "vocabulary",
        "prefixes",
        "arg_types",
    ): "D02 §2: argument position -> parameter type",
    ("matches", "vocabulary", "verbs", "arg_types"): "D02 §2: argument position -> parameter type",
    ("matches", "vocabulary", "request_requirement", "arg_types"): (
        "D02 §2: argument position -> parameter type"
    ),
    ("matches", "indexed", "item", "requirements"): (
        "D02 `config_join` indexed: the gateway's predicate factory name (`Header`) -> its reader"
    ),
    ("matches", "kinds"): "D02 Quartz: schedule builder type -> the framework's kind word",
    ("matches", "media_from_config", "format_from"): "D02 §2d: serializer class -> format",
    ("matches", "media_from_config", "values"): "D02 §2d: serializer class -> media",
    ("matches", "path_fallback", "replace"): "D02: a character of the name -> its replacement",
    ("matches", "request_params", "spelling", "replace"): (
        "D02 `spelling: {replace: {<from>: <to>}}`: a character -> its replacement"
    ),
    (
        "matches",
        "repositories",
    ): "D02 Spring Data REST: contract fqn -> the CRUD operations it licenses",
    (
        "matches",
        "triggers",
    ): "D02 scheduled: annotation attribute -> the framework's word for the kind",
    (
        "matches",
        "disabled",
    ): "D02 scheduled: annotation attribute -> the value the framework reads as never",
    ("matches", "verb_values", "fields"): 'D02: `"<owner>#<field>"` -> verb',
    (
        "matches",
        "vocabulary",
        "verb_values",
        "fields",
    ): 'D02 `combinator`: `"<owner>#<field>"` -> verb',
    (
        "matches",
        "vocabulary",
        "verb_values",
        "getters",
    ): 'D02 `combinator`: `"<owner>#<method>"` -> verb',
    ("matches", "vocabulary", "media_values", "getters"): (
        'D02 `combinator`: `"<owner>#<method>"` -> media value'
    ),
    ("matches", "vocabulary", "media_values", "values"): (
        "D02 `combinator`: a constant of `media_values.owner` -> media value"
    ),
    ("media_formats",): "D02 format ladder rung 2: media type -> format",
    ("matches", "address_from_config", "binder_protocols"): (
        "D02 `config_join`: a configured binder name -> protocol"
    ),
    ("matches", "detection_strategy", "strategies"): (
        "D02 Spring Data REST: a value of the configured key -> flags"
    ),
    ("matches", "mapping", "request_requirement_attrs"): (
        "D02 `annotation_driven`: mapping annotation attribute -> requirement kind"
    ),
    ("client_base", "default_ports"): "D02 client model: `{scheme: port}`",
}

_CONSTANT = re.compile(r"_?[A-Z][A-Z0-9_]*")
_APPROVAL_FIELDS = ("word", "where", "approved_by", "approved_on", "reference")


def _catalog_keys(root: Path) -> tuple[set[str], set[tuple[str, ...]]]:
    """Every key name in every `*.yml` under `root`, and the data-keyed paths that were seen."""
    keys: set[str] = set()
    seen: set[tuple[str, ...]] = set()

    def walk(node: Any, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            data = path in _DATA_KEYED_MAPPINGS
            if data:
                seen.add(path)
            for key, value in node.items():
                if not data:
                    keys.add(str(key))
                walk(value, (*path, str(key)))
        elif isinstance(node, list):
            for value in node:
                walk(value, path)

    for path in sorted(root.rglob("*.yml")):
        walk(yaml.safe_load(path.read_text(encoding="utf-8")), ())
    return keys, seen


def _where(module: Any, name: str) -> str:
    return f"{Path(module.__file__).relative_to(REPO).as_posix()}::{name}"


def _members(value: Any) -> set[str] | None:
    """The words a closed set holds, or None when the value is not a closed set of strings."""
    if isinstance(value, type) and issubclass(value, enum.Enum):
        return {str(member.value) for member in value}
    if isinstance(value, tuple | list | set | frozenset) and value:
        return set(value) if all(isinstance(one, str) for one in value) else None
    if isinstance(value, Mapping) and value and all(isinstance(one, str) for one in value):
        return {str(one) for one in value} | {one for one in value.values() if isinstance(one, str)}
    return None


def _closed_sets(modules: tuple[str, ...] = _CLOSED_SET_MODULES) -> dict[str, set[str]]:
    """Every closed set each module DEFINES (an import is the defining module's), by `where`."""
    found: dict[str, set[str]] = {}
    for name in modules:
        module = importlib.import_module(name)
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [one.id for one in node.targets if isinstance(one, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            else:
                continue
            for one in names:
                value = getattr(module, one)
                is_enum = isinstance(value, type) and issubclass(value, enum.Enum)
                if not (is_enum or _CONSTANT.fullmatch(one)):
                    continue
                members = _members(value)
                where = _where(module, one)
                if members is not None and where not in _NOT_VOCABULARY:
                    found[where] = members
    return found


def _live() -> dict[str, set[str]]:
    keys, _ = _catalog_keys(CATALOGS)
    return {CATALOG_KEY: keys, **_closed_sets()}


def _document(live: dict[str, set[str]]) -> dict[str, Any]:
    """The file's content for `live` as the baseline, with no approvals — run once, 2026-11-23."""
    return {
        "baseline": {
            "catalog_keys": sorted(live[CATALOG_KEY]),
            "closed_sets": {
                where: sorted(live[where]) for where in sorted(live) if where != CATALOG_KEY
            },
        },
        "approvals": [],
    }


def problems(live: dict[str, set[str]], document: dict[str, Any]) -> list[str]:
    """What differs between the live words and `document`'s baseline + approvals, as instructions."""
    found: list[str] = []
    baseline = document.get("baseline") or {}
    expected: dict[str, set[str]] = {CATALOG_KEY: set(baseline.get("catalog_keys") or [])}
    for where, words in (baseline.get("closed_sets") or {}).items():
        expected[where] = set(words)
    approved: set[tuple[str, str]] = set()
    for index, entry in enumerate(document.get("approvals") or []):
        entry = entry if isinstance(entry, dict) else {}
        missing = [one for one in _APPROVAL_FIELDS if not entry.get(one)]
        if not isinstance(entry.get("approved_on"), datetime.date):
            missing += [] if "approved_on" in missing else ["approved_on (a date, YYYY-MM-DD)"]
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

    for where in sorted(set(live) | set(expected)):
        here, wanted = live.get(where, set()), expected.get(where, set())
        new_set = where != CATALOG_KEY and where not in baseline.get("closed_sets", {})
        for word in sorted(here - wanted):
            hint = (
                f"; if {where} holds no Sextant word, list it in _NOT_VOCABULARY in "
                "tests/architecture/test_vocabulary_ratchet.py with the reason"
                if new_set
                else ""
            )
            found.append(
                f"new word {word!r} in {where}: GUIDELINES §8.9 requires the principles check and "
                "the user's approval; add an approval entry with approved_by/approved_on/reference "
                f"to tests/architecture/vocabulary.yml{hint}"
            )
        for word in sorted(wanted - here):
            source = "approvals" if (where, word) in approved else "baseline"
            found.append(
                f"stale word {word!r} in {where}: it is no longer in the code; remove it from the "
                f"{source} in tests/architecture/vocabulary.yml"
            )
    return found


def test_every_word_is_in_the_baseline_or_approved():
    document = yaml.safe_load(VOCABULARY.read_text(encoding="utf-8"))
    assert problems(_live(), document) == []


def test_every_data_keyed_mapping_still_ships():
    # An exclusion nothing uses any more is removed, so the list cannot hide a later word.
    _, seen = _catalog_keys(CATALOGS)
    assert set(_DATA_KEYED_MAPPINGS) - seen == set()


def test_every_not_vocabulary_constant_still_exists():
    modules = {name.replace(".", "/") for name in _CLOSED_SET_MODULES}
    for where in _NOT_VOCABULARY:
        path, name = where.split("::")
        assert path.removeprefix("src/").removesuffix(".py") in modules, where
        module = importlib.import_module(
            path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        )
        assert _members(getattr(module, name, None)) is not None, where


# --- tests of the test: each failure it exists for, shown to happen ---------------------------

_FAKE = {CATALOG_KEY: {"owner", "method"}, "m.py::_KINDS": {"a", "b"}}


def _baseline_of(
    live: dict[str, set[str]], approvals: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {**_document(live), "approvals": approvals or []}


def _approval(word: str, where: str, **override: Any) -> dict[str, Any]:
    entry = {
        "word": word,
        "where": where,
        "approved_by": "the user",
        "approved_on": datetime.date(2026, 11, 24),
        "reference": "spec 2026-11-24 §3",
    }
    return {key: value for key, value in {**entry, **override}.items() if value is not None}


def test_the_baseline_alone_passes():
    assert problems(_FAKE, _baseline_of(_FAKE)) == []


def test_a_new_catalog_key_fails_with_the_instruction():
    live = {**_FAKE, CATALOG_KEY: {"owner", "method", "mount_kind"}}
    assert problems(live, _baseline_of(_FAKE)) == [
        (
            "new word 'mount_kind' in catalog key: GUIDELINES §8.9 requires the principles check and "
            "the user's approval; add an approval entry with approved_by/approved_on/reference to "
            "tests/architecture/vocabulary.yml"
        )
    ]


def test_a_new_closed_value_fails_and_its_approval_passes():
    live = {**_FAKE, "m.py::_KINDS": {"a", "b", "c"}}
    assert [one[:28] for one in problems(live, _baseline_of(_FAKE))] == [
        "new word 'c' in m.py::_KINDS"
    ]
    assert problems(live, _baseline_of(_FAKE, [_approval("c", "m.py::_KINDS")])) == []


def test_a_new_closed_set_fails_for_each_member_and_names_the_exemption():
    live = {**_FAKE, "m.py::_NEW": {"x"}}
    (only,) = problems(live, _baseline_of(_FAKE))
    assert only.startswith("new word 'x' in m.py::_NEW")
    assert "list it in _NOT_VOCABULARY" in only


def test_a_word_removed_from_the_code_fails_until_removed_from_the_file():
    live = {**_FAKE, CATALOG_KEY: {"owner"}}
    assert problems(live, _baseline_of(_FAKE)) == [
        (
            "stale word 'method' in catalog key: it is no longer in the code; remove it from the "
            "baseline in tests/architecture/vocabulary.yml"
        )
    ]


def test_a_stale_approval_entry_fails():
    assert problems(_FAKE, _baseline_of(_FAKE, [_approval("gone", CATALOG_KEY)])) == [
        (
            "stale word 'gone' in catalog key: it is no longer in the code; remove it from the "
            "approvals in tests/architecture/vocabulary.yml"
        )
    ]


def test_an_approval_missing_a_field_fails_and_approves_nothing():
    live = {**_FAKE, CATALOG_KEY: {"owner", "method", "mount_kind"}}
    found = problems(
        live, _baseline_of(_FAKE, [_approval("mount_kind", CATALOG_KEY, approved_by=None)])
    )
    assert found[0].startswith("approval entry 0 ('mount_kind') lacks approved_by")
    assert found[1].startswith("new word 'mount_kind' in catalog key")


def test_an_approval_date_must_be_a_date():
    entry = _approval("c", "m.py::_KINDS", approved_on="yesterday")
    (only,) = problems(_FAKE, _baseline_of(_FAKE, [entry]))
    assert "lacks approved_on (a date, YYYY-MM-DD)" in only


def test_an_approval_of_a_baseline_word_fails():
    (only,) = problems(_FAKE, _baseline_of(_FAKE, [_approval("a", "m.py::_KINDS")]))
    assert only == "approval entry 0: 'a' in m.py::_KINDS is already recorded; delete it"


def test_a_key_under_a_data_keyed_mapping_is_not_a_word_but_its_value_keys_are(tmp_path: Path):
    (tmp_path / "c.yml").write_text(
        "matches:\n  repositories:\n    org.example.Repo: [save]\n"
        "  indexed:\n    item:\n      requirements:\n        Header: { kind: header }\n",
        encoding="utf-8",
    )
    keys, _ = _catalog_keys(tmp_path)
    assert keys == {"matches", "repositories", "indexed", "item", "requirements", "kind"}


def test_the_scan_finds_the_closed_sets_named_in_guidelines_8_9():
    found = _closed_sets()
    assert (
        "payload_binding" in found["src/sextant/application/resolve/open_questions.py::QUESTIONS"]
    )
    assert "cycle" in found["src/sextant/application/resolve/values.py::_REASONS"]
    assert "resolved" in found["src/sextant/domain/closed_sets.py::Resolution"]
    assert "pattern" in found["src/sextant/application/resolve/engines/fluent.py::_URL_IS"]
    assert (
        "returns_receiver" in found["src/sextant/ingress/catalogs/yaml_source.py::_RETURNS_FORMS"]
    )
