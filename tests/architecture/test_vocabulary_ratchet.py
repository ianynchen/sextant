"""No new word reaches Sextant without the user's approval (GUIDELINES §8.9, §1.1).

## The defect this makes permanent

On the Django plan (branch `cov/python-django`, 2026-11-22/23) an agent added catalog words,
an open-question kind and a truth rule during the work and reported them afterwards — although
§1.1 already forbade decide-then-inform for exactly this ("extending a set the spec calls
closed"). The rule was written, agreed and broken; §13.8 says such a rule needs enforcement,
because prose has already been tried and lost. This is that enforcement for the words it can
see; §8.9 names what it cannot see, and review is the control there.

## What counts as a word

Three kinds, compared against `vocabulary.yml` beside this file:

1. **Every mapping KEY used in a shipped catalog** (`src/sextant/catalogs/**/*.yml`), found by
   walking the parsed documents. The loader refuses a key it does not read, so the keys the
   shipped catalogs use are the catalog words in real use. Recorded by NAME, not by where
   the key sits: a known word reused in a new block (`{arg, keyword}` in a fortieth place) is
   the reuse §8.8 rule 3 asks for, and a ratchet that fired on it would punish exactly that.
   A new BLOCK still needs its own key name, and that name is caught.
2. **The VALUES of the closed-value keys** listed in `vocabulary.yml` (`closed_value_keys`):
   every string a shipped catalog writes under such a key (in a list too, and under a
   data-keyed mapping, where the mapping's own key is the one that counts). `arg<N>` is an
   argument position, not a word, and is not recorded, so a key whose values are all
   positions is listed with no words and any WORD written there fails. The list is data in
   the file, not chosen at test time. It was made on 2026-11-23 by the rule "every string
   value of this key in every shipped catalog is a lower-case identifier", minus
   `_OPEN_VALUE_KEYS` below, whose values are the framework's or the user's names. A NEW key
   that takes word values is caught as a new key; its approval says whether it is
   closed-valued, and if so it is added to the list in the same change.
3. **The members of every closed set in code** in `_scanned_modules()`: every module under
   `src/sextant/application/resolve/`, the catalog loader, and the domain's closed sets.
   A closed set is a module-level name, or a name in the body of a module-level class, whose
   value is a non-empty tuple, list, set or frozenset of strings, a dict whose keys are
   strings (its members are the keys and the string values), a `Literal[...]` alias, or an
   `Enum` (its values). Found by reading the module, not by a list typed here, so a NEW set
   is caught on the day it appears: it is in neither the baseline nor `_NOT_VOCABULARY`, and
   every member reads as a new word. Any spelling of the name counts, lower case too; only a
   dunder name (`__all__`, `__slots__`) is skipped, because its strings are Python's export
   and attribute protocol.

## What is data, not vocabulary

A catalog mapping whose keys are the FRAMEWORK's or the USER's names (a class, an annotation
attribute, a configured value, an argument position, a character) holds no Sextant word in
its keys: adding `org.example.NewRepository` to `repositories` is a catalog fact, not a new
concept. `_DATA_KEYED_MAPPINGS` lists each such mapping by its exact path, with the D02
statement that makes its keys data. Its VALUES are still walked, so a word nested under a
data key (`requirements.Header.kind`) is still a word. Exact paths, not a pattern: a new data
map elsewhere fails until someone adds it here with its reason. `_OPEN_VALUE_KEYS` and
`_NOT_VOCABULARY` do the same for values and code sets; when in doubt a set is vocabulary.

## The baseline and the approvals

`vocabulary.yml` holds `baseline` — the words on `main` on 2026-11-23, generated once by
`_document()` and never regenerated, because regenerating is how a word would slip in — and
`approvals`, one entry per word added since, each naming `word`, `where`, `approved_by`,
`approved_on` (a date after 2026-11-23) and `reference`. The test compares the live words with
baseline + approvals in both directions: a new word with no entry fails, and an entry for a
word that is gone fails, so the file stays the truth. A word removed from the code is removed
from the file by hand; a set that MOVES to another module has its baseline entry moved, and
the failure says so. Any diff of `vocabulary.yml` is reviewed as an approval.

It is OFFLINE and deterministic: it reads the shipped catalogs and imports the scanned modules.
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

CATALOG_KEY = "catalog key"
CATALOG_VALUE = "catalog value: "
RULE_DATE = datetime.date(2026, 11, 23)

_SCANNED_TREES = ("sextant/application/resolve",)
_SCANNED_FILES = ("sextant/ingress/catalogs/yaml_source.py", "sextant/domain/closed_sets.py")


def _scanned_modules() -> list[str]:
    files = [*(path for tree in _SCANNED_TREES for path in (SRC / tree).rglob("*.py"))]
    files += [SRC / one for one in _SCANNED_FILES]
    names = {".".join(path.relative_to(SRC).with_suffix("").parts) for path in files}
    return sorted(name.removesuffix(".__init__") for name in names)


_R = "src/sextant/application/resolve/"
_COLUMNS = "names of workspace table columns, not words a catalog writes or a row publishes"
_LANGUAGE = "the language's or the platform's own spellings"
# Each is `where` (see `_closed_sets`) -> why its members are not Sextant words.
_NOT_VOCABULARY = {
    f"{_R}dispatch_hops.py::_KEPT_COLUMNS": _COLUMNS,
    f"{_R}engines/combinator.py::_GROUPED_FIELDS": _COLUMNS,
    f"{_R}format.py::_PAYLOAD_COLUMNS": _COLUMNS,
    f"{_R}format.py::_MEDIA_COLUMNS": _COLUMNS,
    f"{_R}format.py::_MATCH_COLUMNS": _COLUMNS,
    f"{_R}path_prefix.py::_MATCH_COLUMNS": _COLUMNS,
    f"{_R}protocol_hint.py::_MEDIA_COLUMNS": _COLUMNS,
    f"{_R}protocol_hint.py::_MATCH_COLUMNS": _COLUMNS,
    f"{_R}self_calls.py::_ROW_COLUMNS": _COLUMNS,
    f"{_R}shapes/parse_binding.py::_MATCH_COLUMNS": _COLUMNS,
    f"{_R}values.py::_UNCHANGEABLE": f"{_LANGUAGE}: JVM descriptors of immutable types",
    f"{_R}values.py::_CALLABLES": f"{_LANGUAGE}: Python's symbols for a callable type",
    f"{_R}effective_calls.py::_BOXING": f"{_LANGUAGE}: JVM boxing descriptors",
    f"{_R}dispatch.py::_NOT_INHERITED": f"{_LANGUAGE}: JVM initializer names",
    f"{_R}receiver_binding.py::_PROTOCOL": f"{_LANGUAGE}: Python dunder protocol methods",
    f"{_R}receiver_binding.py::_SYNTAX": f"{_LANGUAGE}: Python dunder protocol methods",
    f"{_R}bean_conditions.py::_COMPOSITION": f"{_LANGUAGE}: Spring condition operators `&|()`",
    f"{_R}self_calls.py::_LOOPBACK": "a standard's spellings: loopback host names and addresses",
    f"{_R}request_requirements.py::_NEGOTIATION_HEADERS": "a standard's spellings: HTTP header names",
    f"{_R}shapes/made_by.py::_SCHEMES": "a standard's spellings: URL schemes",
    f"{_R}engines/fluent.py::_DIRECTIONS": "computed from `Direction`, which is recorded itself",
    f"{_R}engines/single_call.py::_DIRECTIONS": "computed from `Direction`, which is recorded itself",
    "src/sextant/domain/closed_sets.py::_RANKS": "a rank per `Evidence` member, recorded there",
    f"{_R}shapes/chains.py::_RULE_9": "internal NUL-prefixed keys, never written nor published",
    f"{_R}request_requirements.py::BOUND": "a value (a pair of empty strings), not a set of words",
}

_POSITION = re.compile(r"arg\d+")
_WORD = re.compile(r"[a-z][a-z0-9_]*")
_ATTRIBUTE = "an annotation's or a connector's attribute name"
# Keys whose every value is a lower-case identifier but names the framework's or the user's own
# things, so a new value is a catalog fact, not a word; excluded from `closed_value_keys`.
_OPEN_VALUE_KEYS = {
    **dict.fromkeys(
        (
            "annotation_attrs",
            "connector_attribute",
            "consumes_from",
            "destination_from",
            "discriminators",
            "exported_attribute",
            "expressions",
            "method_from",
            "name_attrs",
            "names",
            "packages_from",
            "path_attribute",
            "produces_from",
            "required_attr",
            "status_from",
            "stereotype_name_attrs",
            "type_attrs",
        ),
        _ATTRIBUTE,
    ),
    "absent_value": "the framework's value for an absent attribute (`true`)",
    "config_field": "a field name in the framework's settings class",
    "delegate_field": "a field name in the framework's class",
    "field": "a field name in the framework's configuration",
    "keyword": "a keyword argument name of the framework's function",
    "from_argument": "a keyword argument name of the framework's function",
    "name_from": "a keyword argument or attribute name of the framework",
    "getter_prefixes": "a prefix of the framework's accessor names (`get`, `is`)",
    "drop_suffixes": "a suffix of the user's class names",
    "handler_methods": "a method name of the framework",
    "serializers": "a method name of the framework",
    "search_segment": "a path segment the framework serves",
    "scheme": "a URL scheme",
    "default_profile": "the framework's default profile name",
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

_APPROVAL_FIELDS = ("word", "where", "approved_by", "approved_on", "reference")


def _catalog_words(root: Path) -> tuple[set[str], dict[str, set[str]], set[tuple[str, ...]]]:
    """Every key name under `root`, every word value by the key that holds it, and the
    data-keyed paths that were seen."""
    keys: set[str] = set()
    values: dict[str, set[str]] = {}
    seen: set[tuple[str, ...]] = set()

    def walk(node: Any, path: tuple[str, ...], holder: str | None) -> None:
        if isinstance(node, dict):
            data = path in _DATA_KEYED_MAPPINGS
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
        return {str(one) for one in value} | {one for one in value.values() if isinstance(one, str)}
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
    modules: list[str] | None = None, exclude: Mapping[str, str] = _NOT_VOCABULARY
) -> dict[str, set[str]]:
    """Every closed set each module DEFINES (an import is the defining module's), by `where`."""
    found: dict[str, set[str]] = {}
    for name in _scanned_modules() if modules is None else modules:
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
            if members is not None and where not in exclude:
                found[where] = members
    return found


def _live(baseline: dict[str, Any]) -> dict[str, set[str]]:
    keys, values, _ = _catalog_words(CATALOGS)
    listed = baseline.get("closed_value_keys") or {}
    return {
        CATALOG_KEY: keys,
        **{CATALOG_VALUE + key: values.get(key, set()) for key in listed},
        **_closed_sets(),
    }


def _document() -> dict[str, Any]:
    """The file's content as the baseline, with no approvals — run once, 2026-11-23."""
    keys, values, _ = _catalog_words(CATALOGS)
    closed = {
        key: sorted(words)
        for key, words in sorted(values.items())
        if all(_WORD.fullmatch(one) for one in words) and key not in _OPEN_VALUE_KEYS
    }
    sets = _closed_sets()
    return {
        "baseline": {
            "catalog_keys": sorted(keys),
            "closed_value_keys": closed,
            "closed_sets": {where: sorted(sets[where]) for where in sorted(sets)},
        },
        "approvals": [],
    }


def _expected_baseline(baseline: dict[str, Any]) -> dict[str, set[str]]:
    expected = {CATALOG_KEY: set(baseline.get("catalog_keys") or [])}
    for key, words in (baseline.get("closed_value_keys") or {}).items():
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
                "baseline.closed_sets in tests/architecture/vocabulary.yml to the new place"
            )
            continue
        here, wanted = live.get(where, set()), expected.get(where, set())
        new_set = where.startswith("src/") and where not in recorded
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
    assert problems(_live(document["baseline"]), document) == []


def test_every_data_keyed_mapping_still_ships():
    _, _, seen = _catalog_words(CATALOGS)
    unused = sorted(set(_DATA_KEYED_MAPPINGS) - seen)
    assert unused == [], (
        f"{unused} no longer appear in any shipped catalog: delete them from "
        "_DATA_KEYED_MAPPINGS, so the list cannot hide a later word"
    )


def test_every_open_value_key_still_ships():
    _, values, _ = _catalog_words(CATALOGS)
    unused = sorted(set(_OPEN_VALUE_KEYS) - set(values))
    assert unused == [], (
        f"{unused} no longer appear in any shipped catalog: delete them from _OPEN_VALUE_KEYS"
    )


def test_every_not_vocabulary_set_still_exists():
    scanned = {name.replace(".", "/") for name in _scanned_modules()}
    for where in _NOT_VOCABULARY:
        path = where.split("::")[0].removeprefix("src/").removesuffix(".py")
        assert path in scanned and where in _closed_sets_including_excluded(), (
            f"{where} is no longer a closed set in a scanned module: if it moved, move its "
            "_NOT_VOCABULARY entry to the new place; if it is gone, delete the entry"
        )


def _closed_sets_including_excluded() -> set[str]:
    paths = {where.split("::")[0] for where in _NOT_VOCABULARY}
    names = [path.removeprefix("src/").removesuffix(".py").replace("/", ".") for path in paths]
    return set(_closed_sets(names, exclude={}))


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
    return {"baseline": baseline, "approvals": approvals or []}


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
            "new word 'mount_kind' in catalog key: GUIDELINES §8.9 requires the principles check "
            "and the user's approval; add an approval entry with approved_by/approved_on/reference "
            "to tests/architecture/vocabulary.yml"
        )
    ]


def test_a_new_value_of_a_closed_value_key_fails_and_its_approval_passes():
    live = {**_FAKE, CATALOG_VALUE + "url_is": {"pattern", "expression"}}
    (only,) = problems(live, _baseline_of(_FAKE))
    assert only.startswith("new word 'expression' in catalog value: url_is: GUIDELINES §8.9")
    approval = _approval("expression", CATALOG_VALUE + "url_is")
    assert problems(live, _baseline_of(_FAKE, [approval])) == []


def test_a_catalog_value_is_recorded_under_its_key_and_a_position_is_not_a_word(tmp_path: Path):
    (tmp_path / "c.yml").write_text(
        "matches:\n  repositories:\n    org.example.Repo: [save]\n"
        "  roots:\n    - { captures: { url_is: expression, url: arg0 } }\n",
        encoding="utf-8",
    )
    keys, values, _ = _catalog_words(tmp_path)
    assert values["url_is"] == {"expression"}
    assert values["url"] == set()
    assert values["repositories"] == {"save"}
    assert "org.example.Repo" not in keys


def test_a_new_closed_value_fails_and_its_approval_passes():
    live = {**_FAKE, _SET: {"a", "b", "c"}}
    (only,) = problems(live, _baseline_of(_FAKE))
    assert only.startswith(f"new word 'c' in {_SET}")
    assert problems(live, _baseline_of(_FAKE, [_approval("c", _SET)])) == []


def test_a_new_closed_set_fails_for_each_member_and_names_the_exemption():
    live = {**_FAKE, "src/m.py::_NEW": {"x"}}
    (only,) = problems(live, _baseline_of(_FAKE))
    assert only.startswith("new word 'x' in src/m.py::_NEW")
    assert "list it in _NOT_VOCABULARY" in only


def test_a_moved_closed_set_says_to_move_its_entry():
    live = {key: value for key, value in _FAKE.items() if key != _SET}
    live["src/n.py::_KINDS"] = {"a", "b"}
    assert problems(live, _baseline_of(_FAKE)) == [
        (
            f"closed set moved from {_SET} to src/n.py::_KINDS: move its entry under "
            "baseline.closed_sets in tests/architecture/vocabulary.yml to the new place"
        )
    ]


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
    keys, _, _ = _catalog_words(tmp_path)
    assert keys == {"matches", "repositories", "indexed", "item", "requirements", "kind"}


def test_a_module_scan_sees_class_body_sets_literal_aliases_and_lower_case_names(
    tmp_path: Path, monkeypatch: Any
):
    (tmp_path / "fake_words.py").write_text(
        "from typing import Literal\n"
        "Kind = Literal['one', 'two']\n"
        "type Mode = Literal['fast']\n"
        "kinds = frozenset({'x'})\n"
        "__all__ = ['Kind']\n"
        "class Holder:\n"
        "    WORDS = ('held', 'pending')\n"
        "    __slots__ = ('a',)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found = _closed_sets(["fake_words"])
    assert found == {
        "fake_words.py::Kind": {"one", "two"},
        "fake_words.py::Mode": {"fast"},
        "fake_words.py::kinds": {"x"},
        "fake_words.py::Holder.WORDS": {"held", "pending"},
    }


def test_the_scan_reaches_shapes_and_engines():
    found = _closed_sets()
    assert "unrooted" in found[f"{_R}shapes/mounts.py::_REFUSES"]
    assert "exact" in found[f"{_R}engines/config_join.py::_NAME_MATCHING"]


def test_the_scan_finds_the_closed_sets_named_in_guidelines_8_9():
    found = _closed_sets()
    assert "payload_binding" in found[f"{_R}open_questions.py::QUESTIONS"]
    assert "cycle" in found[f"{_R}values.py::_REASONS"]
    assert "resolved" in found["src/sextant/domain/closed_sets.py::Resolution"]
    assert "pattern" in found[f"{_R}engines/fluent.py::_URL_IS"]
    assert (
        "returns_receiver" in found["src/sextant/ingress/catalogs/yaml_source.py::_RETURNS_FORMS"]
    )
