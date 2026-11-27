"""A settings module is a source of configuration (ruling R3 of 2026-11-25, design note
approved 2026-11-25): the config-model source form `{from_module_holding: <catalog word>}`.

Each module that holds the setting a catalog names with that word (`matches.root_setting`,
Django's `ROOT_URLCONF`) is a source, and its module name is the environment, as a profile
file's name is on the JVM. A module holds a name it writes, and a name a `from m import *`
gives it (the scanner writes that binding as a field write, as an import of one variable).
Each name the module holds is a key: one `resolved_config` row per name per settings module
(where the source says `key_names: upper_case`, per upper-case name, the framework's own rule),
and, as for a profile, an `external` row where another settings module holds a name this
one does not. Nothing here names a framework: the word and the setting are catalog data.

**The value is the value walk's**, read at the module's own name: a written literal is its
text, a read of the process environment its expression (`${KEY:-default}`), which is the
repository's statement and never the deployed value (deployment decides). A name with no one
value keeps a reason from the general list and a detail for a person: several values (a
list, a write under a test), a class or function reference, and a name written with no
value (`None`, an empty list) are `not_readable`.

**Cost (§8.7).** Only for a module whose config model declares the form and whose catalogs
name a setting some module holds: one pass over `field_writes`, and one walk per name held
(measured 2026-11-25: zulip 608 names, 893 computes, 0.01 s; weblate 620 names, 1,274
computes, 0.02 s), on the index the engines share."""

import json
from collections.abc import Mapping, Sequence

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import (
    FROM_MODULE,
    KEY_NAMES,
    TEST_TOOL_LANGUAGE,
    config_model_of,
    not_set,
)
from sextant.application.resolve.registration_conditions import (
    NOT_EVALUATED,
    TEST,
    UNCONDITIONAL,
    Conditions,
    Conjunction,
    conditions_of,
)
from sextant.application.resolve.values import (
    ABSENT,
    EXPRESSION,
    EXTERNAL,
    LITERAL,
    NOT_READABLE,
    SYMBOL,
    UNPACKED_SLOT,
    UNRESOLVED,
    Answer,
    Path,
    Tests,
    ValueIndex,
    argument_slot,
    cached_value_index,
    resolve_positions_on_paths,
)
from sextant.domain.symbols import bare_descriptor, dotted_type, member_name, owner_of


def record_module_config(workspace: Workspace, catalogs: Sequence[Catalog]) -> None:
    """Adds the `resolved_config` rows of every settings module (the module docstring).
    Runs after `resolve_config`, which empties the table, and after the call edges are
    drawn, which the walk reads."""
    settings = _settings_named(catalogs)
    if not settings:
        return
    declared = {
        bare_descriptor(str(row["symbol"])): str(row["document_id"])
        for row in workspace.query("fields")
        if row["static"]
    }
    # module descriptor -> name -> (field symbol, writer, document) of one write of it.
    held: dict[str, dict[str, tuple[str, str, str]]] = {}
    for row in workspace.query("field_writes"):
        bare = bare_descriptor(str(row["field"]))
        module = owner_of(bare)
        if (
            module is None
            or bare != f"{module}{member_name(bare)}."
            or bare not in declared
            or row["written_by"] is None
        ):
            continue  # a field of a class, or a write no method is named for
        held.setdefault(module, {}).setdefault(
            member_name(bare), (str(row["field"]), str(row["written_by"]), declared[bare])
        )
    modules = sorted(module for module, names in held.items() if settings & names.keys())
    if not modules:
        return
    one = catalogs[0]
    index = cached_value_index(
        workspace,
        one.not_hand_offs,
        one.hand_off_effects,
        one.bean_models,
        one.value_annotations,
        returns_arguments=one.returns_arguments,
    )
    modules = _environments(workspace, catalogs, index, modules, held)
    paths = {
        str(row["document_id"]): str(row["relative_path"]) for row in workspace.query("documents")
    }
    # `key_names: upper_case`: a name the framework does not take as a setting is no key.
    upper = any(
        FROM_MODULE in source and KEY_NAMES in source
        for source in config_model_of(catalogs).get("sources", [])
    )
    keys = sorted(
        {name for module in modules for name in held[module] if name.isupper() or not upper}
    )
    # The tests the module's writes run under, read once (`conditions_of`): a value read
    # through a write under a test not decided exists where that test goes its way.
    conditions = conditions_of(workspace, Tests(index))
    rows: list[dict[str, object]] = []
    existence: list[dict[str, object]] = []
    for module in modules:
        environment = dotted_type(module)
        for key in keys:
            if key not in held[module]:
                rows.append(_row(key, environment, None, None, EXTERNAL, not_set(key)))
                continue
            symbol, writer, document = held[module][key]
            site = {
                "caller": writer,
                "ordinal": -1,
                "arguments": [{"kind": "field", "symbol": symbol}],
            }
            reached = [
                (path, answers[key])
                for path, answers in resolve_positions_on_paths(workspace, {key: (site, 0)}, index)
            ]
            # Every write of the list unpacks the name itself (`K = K + [...]` on a list a
            # star import gives): the walk reads the added members alone, at no known place.
            lists = [
                entry.get("elements") or []
                for _, entry in index.constants.get(symbol, ())
                if entry.get("kind") == "array"
            ]
            spread = bool(lists) and all(
                any(e.get("keyword") and e.get("symbol") == symbol for e in elements)
                for elements in lists
            )
            stated = _keys(key, reached, spread)
            if list(stated) == [key] and stated[key][1] is None:
                stated[key] = _with_default(key, stated[key], reached, workspace, index)
            for name, (value, reason, detail) in stated.items():
                rows.append(_row(name, environment, value, paths.get(document), reason, detail))
            # Every key of the name, read or not: its writes run under the same tests.
            under = _existence(environment, [path for path, _ in reached], conditions)
            existence += [{"key": name, **entry} for name in stated for entry in under]
    workspace.derive("resolved_config_insert", rows=rows)
    if existence:
        workspace.derive("config_existence_insert", rows=existence)


def _environments(
    workspace: Workspace,
    catalogs: Sequence[Catalog],
    index: ValueIndex,
    modules: list[str],
    held: Mapping[str, Mapping[str, tuple[str, str, str]]],
) -> list[str]:
    """`modules`, the settings modules, without the building blocks and the test settings
    (ruled 2026-11-26, D3).

    A building block is a module another settings module takes a name of (`from m import
    *`), unless code starts a process with it. A start is a stated environment read of a key
    the model's `profiles.active_keys` names whose default is the module's name as a written
    text (`os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")`).

    Test settings are the module the test tool's settings file names with such a key
    (`DJANGO_SETTINGS_MODULE = app.settings_test` under `[pytest]`), where it builds on
    another settings module: only the tests select it, so it is test code, and a start with
    it (a benchmark script) is test code too. It is no environment and no builder. A module
    the file names that builds on no other is the one the deployment runs as well
    (bookwyrm). A model with no such key keeps every module."""
    selectors = set(config_model_of(catalogs).get("profiles", {}).get("active_keys") or ())
    if not selectors:
        return modules
    # settings module -> the settings modules it takes a name of.
    builds_on: dict[str, set[str]] = {}
    for module in modules:
        for name, (symbol, _, _) in held[module].items():
            for _, entry in index.constants.get(symbol, ()):
                source = bare_descriptor(str(entry.get("symbol") or ""))
                giver = owner_of(source) if entry.get("kind") == "field" else None
                if giver in modules and giver != module and member_name(source) == name:
                    builds_on.setdefault(module, set()).add(giver)
    tool = {
        str(row["document_id"])
        for row in workspace.query("documents")
        if row["language"] == TEST_TOOL_LANGUAGE
    }
    named = {
        str(row["value"])
        for row in workspace.query("config_entries")
        if str(row["document_id"]) in tool and row["key_path"] in selectors
    }
    tests = {m for m in modules if dotted_type(m) in named and builds_on.get(m)}
    blocks = {
        giver for module, givers in builds_on.items() if module not in tests for giver in givers
    }
    started: set[str] = set()
    for row in index.sites.values() if blocks else ():
        stated = index.environment_reads.get((str(row.get("owner")), str(row["name"])))
        if stated is None or stated[1] is None:
            continue
        arguments = row["arguments"] or []
        written = [
            None if slot is None or slot == UNPACKED_SLOT else arguments[slot].get("value")
            for slot in (argument_slot(arguments, stated[0]), argument_slot(arguments, stated[1]))
        ]
        if written[0] in selectors and written[1] is not None:
            started.add(str(written[1]))
    return [m for m in modules if m not in tests and (m not in blocks or dotted_type(m) in started)]


def _settings_named(catalogs: Sequence[Catalog]) -> set[str]:
    """The settings whose holders are sources: what each catalog names with a word a
    `from_module_holding` source of the module's config model gives."""
    words = [
        str(source[FROM_MODULE])
        for source in config_model_of(catalogs).get("sources", [])
        if FROM_MODULE in source
    ]
    return {
        str(catalog.matches[word])
        for catalog in catalogs
        for word in words
        if isinstance(catalog.matches.get(word), str)
    }


def _existence(
    environment: str, paths: Sequence[Path], conditions: Conditions
) -> list[dict[str, object]]:
    """The `config_existence` entries of one name, for each of its keys: where the writes its
    paths read the value through run, OR-ed across the paths, as a registered row's are
    (`existence_rows`). The writes alone (`Path.writes_under`): a `return` under a test in a
    helper changes the value, not whether the key is written. Nothing where one path read
    it under no test. A test of the code: not evaluated."""
    found: set[Conjunction] = set()
    for path in paths:
        found |= conditions.of_sites(path.writes_under(), path.calls_into(), on=path)
    if not found or () in found or frozenset(found) == UNCONDITIONAL:
        return []
    # Written in both arms of one test (`if T: K = a` / `else: K = b`): always written.
    if any(
        len(one) == 1 and ((*one[0][:2], not one[0][2], *one[0][3:]),) in found for one in found
    ):
        return []
    return [
        {
            "environment": environment,
            "route": route,
            "position": position,
            "via": guard[0],
            "kind": TEST,
            "expression": json.dumps(
                {"holds": guard[2], "reads": list(guard[3]), "test": guard[1]}, sort_keys=True
            ),
            "holds": "unresolved",
            "resolution": "unresolved",
            "evidence": f"{NOT_EVALUATED}`{guard[1]}`",
        }
        for route, conjunction in enumerate(sorted(found))
        for position, guard in enumerate(conjunction)
    ]


# The hole the walk leaves in a text where a part was not read, and its name in a row.
_HOLE = "{}"
_NOT_READ = "<not read>"
_Stated = tuple[str | None, str | None, str | None]


def _keys(key: str, reached: Sequence[tuple[Path, Answer]], spread: bool) -> dict[str, _Stated]:
    """The keys of one name, each with its `_stated`. A written list is one key per member,
    `K[0]`, `K[0][1]`, the form a YAML list has (ruled 2026-11-25, Q4 part 2); where a member
    was not read, the read members and `K` itself with that member's reason. A list a write
    under a test changes, or one every write of adds to (`spread`), has no one
    membership: the name alone, with its reason."""
    if spread:
        detail = f"{key} adds to a list this module does not write: its members were not read"
        return {key: (None, NOT_READABLE, detail)}
    members = [path.members() for path, _ in reached]
    # One list written under a test (`if T: K = ['a']`) is one membership, under that test
    # (`config_existence`); a list one write under a test changes has none.
    if not all(members) or len({path.written_under() for path, _ in reached}) > 1:
        return {key: _stated(key, [answer for _, answer in reached])}
    by_member: dict[str, list[Answer]] = {}
    unread: Answer | None = None
    for member, (_, answer) in zip(members, reached, strict=True):
        if member is None or None in member:
            unread = unread or answer
        else:
            by_member.setdefault(key + "".join(f"[{i}]" for i in member), []).append(answer)
    keys = {name: _stated(name, answers) for name, answers in by_member.items()}
    if unread is not None:
        keys[key] = (None, unread.reason or NOT_READABLE, f"a member of {key} was not read")
    return keys


def _stated(key: str, answers: Sequence[Answer]) -> _Stated:
    """`(value, reason, detail)` of one name: its one value as text, or why it has none."""
    distinct = list(dict.fromkeys(answers))
    if len(distinct) != 1:
        detail = (
            f"{key} has {len(distinct)} values in this module (a list, or a write under a "
            f"test): not one value"
        )
        return None, NOT_READABLE, detail
    answer = distinct[0]
    if answer.kind == UNRESOLVED:
        return None, answer.reason, f"the value written to {key} was not read"
    if answer.kind == ABSENT:
        return None, NOT_READABLE, f"{key} is written with no value (`None` or empty)"
    if (
        answer.inexact
        or answer.narrowed
        or (answer.kind == LITERAL and answer.literal_kind == SYMBOL)
    ):
        return None, NOT_READABLE, f"the value written to {key} is not one written text"
    if answer.kind not in (LITERAL, EXPRESSION):
        return None, NOT_READABLE, f"the value written to {key} was not read"
    if answer.kind == EXPRESSION and _HOLE in str(answer.value):
        # A `partial` row: the text the code states, the part not read named.
        detail = f"a part of the value written to {key} was not read"
        return str(answer.value).replace(_HOLE, _NOT_READ), NOT_READABLE, detail
    return str(answer.value), None, None


# The default of an environment read the walk did not read, named in the row.
_DEFAULT = "<default>"


def _with_default(
    key: str,
    stated: _Stated,
    reached: Sequence[tuple[Path, Answer]],
    workspace: Workspace,
    index: ValueIndex,
) -> _Stated:
    """`stated`, the one value of `key`, with the default of the environment read it is where
    the expression does not state one (`Answer.default_at`; ruled 2026-11-27: the row read
    `${KEY}`, as a key the deployment must set). `None` and a written list of literals are
    said as written; any other default is read by the walk (another read nests,
    `${A:-${B:-5}}`); one not read is the hole `<default>` on a `partial` row."""
    at = reached[0][1].default_at
    marks = index.placeholders
    value = str(stated[0])
    if at is None or marks is None or not value.endswith(marks["close"]):
        return stated
    site = index.sites.get((at[0], at[1]))
    written = None if site is None else (site["arguments"] or [])[at[2]]
    text: str | None = None
    if written is not None and written.get("kind") == "null":
        text = "None"
    elif written is not None and written.get("kind") == "array":
        elements = written.get("elements") or []
        if all(e.get("kind") in ("string", "int", "long", "boolean") for e in elements):
            text = json.dumps([e.get("value") for e in elements])
    elif site is not None:
        answers = list(
            dict.fromkeys(
                found[key]
                for _, found in resolve_positions_on_paths(workspace, {key: (site, at[2])}, index)
            )
        )
        if len(answers) == 1:
            read = _stated(key, answers)
            text = read[0] if read[1] is None else "None" if answers[0].kind == ABSENT else None
            if text == value:
                # `K = read("K", K)`: the default is what the name held before, and the
                # walk reads the name as this write. Not read.
                text = None
    close = marks["close"]
    joined = value[: -len(close)] + marks["default_separator"] + (text or _DEFAULT) + close
    if text is not None:
        return joined, None, None
    return joined, NOT_READABLE, f"the default of {key} was not read"


def _row(
    key: str,
    environment: str,
    value: str | None,
    source: str | None,
    reason: str | None,
    detail: str | None,
) -> dict[str, object]:
    return {
        "key": key,
        "value": value,
        "source": source if value is not None or reason != EXTERNAL else None,
        "environment": environment,
        "unresolved_reason": reason,
        "unresolved_detail": detail,
    }
