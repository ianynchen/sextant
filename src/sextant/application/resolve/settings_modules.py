"""A settings module is a source of configuration (ruling R3 of 2026-11-25, design note
approved 2026-11-25): the config-model source form `{from_module_holding: <catalog word>}`.

Each module that holds the setting a catalog names with that word (`matches.root_setting`,
Django's `ROOT_URLCONF`) is a source, and its module name is the environment, as a profile
file's name is on the JVM. A module holds a name it writes, and a name a `from m import *`
gives it (the scanner writes that binding as a field write, as an import of one variable).
Each name the module holds is a key: one `resolved_config` row per name per settings module (where the source says
`key_names: upper_case`, per upper-case name, the framework's own rule),
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

from collections.abc import Sequence

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import (
    FROM_MODULE,
    KEY_NAMES,
    config_model_of,
    not_set,
)
from sextant.application.resolve.values import (
    ABSENT,
    EXPRESSION,
    EXTERNAL,
    LITERAL,
    NOT_READABLE,
    SYMBOL,
    UNRESOLVED,
    Answer,
    Path,
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
    paths = {
        str(row["document_id"]): str(row["relative_path"]) for row in workspace.query("documents")
    }
    one = catalogs[0]
    index = cached_value_index(
        workspace,
        one.not_hand_offs,
        one.hand_off_effects,
        one.bean_models,
        one.value_annotations,
        returns_arguments=one.returns_arguments,
    )
    # `key_names: upper_case`: a name the framework does not take as a setting is no key.
    upper = any(
        FROM_MODULE in source and KEY_NAMES in source
        for source in config_model_of(catalogs).get("sources", [])
    )
    keys = sorted(
        {name for module in modules for name in held[module] if name.isupper() or not upper}
    )
    rows: list[dict[str, object]] = []
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
            for name, (value, reason, detail) in _keys(key, reached, spread).items():
                rows.append(_row(name, environment, value, paths.get(document), reason, detail))
    workspace.derive("resolved_config_insert", rows=rows)


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
    if not all(members) or any(path.written_under() for path, _ in reached):
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
    return str(answer.value), None, None


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
