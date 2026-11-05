"""Message handler registrations, read per behavior (spec 2026-11-04 §3b, §3d items 1-3).

A behavior binds message classes, or values equal to a constant, to handlers, in order, and
a message is handled by the FIRST case it matches. This pass reads the cases into the
`message_handlers` table, one row per case with its place in its behavior; `reachable_handlers`
is the first-match rule over those rows, which the hop pass and the inbound key rows both
apply. Nothing here names a framework type: every owner, method and argument position is the
catalog's.

## A behavior is a chain

A catalog of the `message_handlers` style declares the chain that builds a behavior in the
fluent words (`roots`, `steps`, `terminal`; D02 §2) and, under `message_handlers`, what each
registration call's arguments mean (`Catalog.message_handlers`). The chain is the shared walk
(`shapes/chains.chain_ends`), receiver to result: a registration returning a NEW builder is
followed through its result, one declared `returns_receiver: true` configures the builder it
is called on, so a builder held in a local and given its cases statement by statement is one
chain. Each registration step carries its own call in the `case` capture, and `repeats` keeps
the calls in chain order, so a case's position is its place in that capture. Each executable
chain's end is one behavior, named `<root's caller>#<root's ordinal>`.

**A root inherited by the module's own class** is a call naming that class, because javac
writes the class a call is made through (`this.newReceiveBuilder()` is a call on the
subclass). The language resolves it up the class's ancestry to the declaration (JVMS
5.4.3.3), so a declared root owner matches a call on any class whose `type_hierarchy` ancestry
reaches it. A class of the module that declares the same method itself would answer the call
with its own body; that is not checked, which holds as long as no module overrides a builder's
factory method.

## What a row says

- `message_type` — the class literal at `class_arg` (a `class` argument's symbol); NULL for
  a value case, a predicate-only case, or a class argument that is not a literal.
- `message_value` — the constant at `value_arg`, by identity (rule 8): the symbol of the
  `enum` or `field` argument the call reads. NULL for anything else.
- `predicated` — the registration declares a `predicate_arg`.
- `handler` — the method the handler argument names (`combinator._handler_of`: a method
  reference names the method, a lambda its synthetic body), module-prefixed; NULL if not read.
- `delivers` — `returns_message`: the handler's return is a message to its own receiver.

A case the walk could not read (the builder handed to code we do not have, spec 2026-11-02
rule 2) keeps its position with every column NULL: its class is unknown, so it matches nothing
and shadows nothing.

## Cost (GUIDELINES §8.7)

One `chain_ends` walk per declaring catalog, only where the module calls one of its roots'
owners (two catalogs; a module calling neither pays one index lookup each), and one read of
`type_hierarchy` per resolve that has a declaring catalog.
"""

from collections.abc import Iterator, Mapping
from dataclasses import replace
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.engines.combinator import _handler_of
from sextant.application.resolve.shapes.arguments import _CAPTURED_AT, _arg_at, call_site_index
from sextant.application.resolve.shapes.chains import _method_symbols, chain_ends
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.domain.symbols import parameter_types, without_type_marker

# The capture each registration step carries its own call in (the catalog's `case: argN`).
_CASE = "case"
# The argument kinds that name a constant by identity (D00 §5): a named constant of its own
# type, and any other static field.
_CONSTANT_KINDS = ("enum", "field")


def record_message_handlers(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Replaces `message_handlers` whole, from every catalog declaring `message_handlers`."""
    workspace.derive("message_handlers_reset")
    declaring = [catalog for catalog in catalogs if catalog.message_handlers]
    if not declaring:
        return
    ancestors = _ancestors(workspace)
    rows: list[dict[str, Any]] = []
    # Two ends of one chain that read the same cases (two paths through one builder) are one
    # behavior's rows once.
    seen: set[tuple[Any, ...]] = set()
    for catalog in declaring:
        for row in _rows_of(workspace, catalog, ancestors):
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                rows.append(row)
    if rows:
        workspace.derive("message_handlers_insert", rows=rows)


def reachable_handlers(
    rows: list[dict[str, Any]],
    message_type: str | None,
    message_value: str | None,
    supertypes: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    """The cases a message reaches, per behavior in `rows`' order: the first unpredicated case
    it matches, and every predicated case before it that matches (a predicate may decline, so
    it never shadows, spec §3d item 2). A class case matches when the message's class is that
    class or one of `supertypes[message_type]`; a value case when `message_value` is its
    constant; a predicate-only case (no class, no value, predicated) matches every message.
    A case whose class is unknown matches nothing. `rows` are `message_handlers` rows."""
    reached: list[dict[str, Any]] = []
    behaviors: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        behaviors.setdefault(str(row["behavior"]), []).append(row)
    assignable = (
        set() if message_type is None else {message_type, *supertypes.get(message_type, ())}
    )
    for cases in behaviors.values():
        for case in sorted(cases, key=lambda case: int(case["position"])):
            if not _matches(case, assignable, message_value):
                continue
            reached.append(case)
            if not case["predicated"]:
                break
    return reached


def _matches(case: Mapping[str, Any], assignable: set[str], message_value: str | None) -> bool:
    if case["message_type"] is not None:
        return case["message_type"] in assignable
    if case["message_value"] is not None:
        return message_value is not None and case["message_value"] == message_value
    return bool(case["predicated"])


def _rows_of(
    workspace: Workspace, catalog: Catalog, ancestors: Mapping[str, tuple[str, ...]]
) -> Iterator[dict[str, Any]]:
    """One catalog's cases, behavior by behavior, in the walk's order."""
    registrations = catalog.message_handlers
    _check_steps(catalog)
    walked = _with_inherited_roots(catalog, ancestors)
    index = workspace.once(call_site_index)
    roots = walked.matches.get("roots", [])
    if not any(
        owner in index.positions_by_owner
        for root in roots
        for owner in catalog_symbols(root.get("owner"), f"{catalog.source}: roots[].owner")
    ):
        return
    method_symbols = workspace.once(_method_symbols)
    for end in chain_ends(workspace, walked):
        behavior = f"{end.root['caller']}#{end.root['ordinal']}"
        # A builder built with no case on it (an immutable builder whose registrations'
        # results were dropped) is a behavior with nothing to write.
        cases = end.captures.get(_CASE)
        if cases is None:
            continue
        for position, captured in enumerate(cases if isinstance(cases, tuple) else (cases,)):
            site = _site_of(captured, index.by_caller)
            registration = None if site is None else _registration_of(site, registrations)
            if site is None or registration is None:
                yield _unread_case(behavior, position)
                continue
            yield _case(behavior, position, site, registration, method_symbols)


def _case(
    behavior: str,
    position: int,
    site: Mapping[str, Any],
    registration: Mapping[str, Any],
    method_symbols: dict[str, str],
) -> dict[str, Any]:
    arguments = site["arguments"]
    message_type = None
    if registration["class_arg"] is not None:
        literal = _arg_at(arguments, registration["class_arg"])
        if literal is not None and literal.get("kind") == "class":
            message_type = literal.get("symbol")
    message_value = None
    if registration["value_arg"] is not None:
        constant = _arg_at(arguments, registration["value_arg"])
        if constant is not None and constant.get("kind") in _CONSTANT_KINDS:
            message_value = constant.get("symbol")
    return {
        "behavior": behavior,
        "position": position,
        "message_type": message_type,
        "message_value": message_value,
        "predicated": registration["predicate_arg"] is not None,
        "handler": _handler_of(arguments, frozenset({registration["handler_arg"]}), method_symbols),
        "delivers": registration["returns_message"],
        "evidence": "compiler",
    }


def _unread_case(behavior: str, position: int) -> dict[str, Any]:
    return {
        "behavior": behavior,
        "position": position,
        "message_type": None,
        "message_value": None,
        "predicated": False,
        "handler": None,
        "delivers": False,
        "evidence": "compiler",
    }


def _site_of(captured: Any, by_caller: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    """The registration call a `case` capture was read at, or None for a part the walk did
    not read (it carries no place)."""
    if not isinstance(captured, Mapping) or _CAPTURED_AT not in captured:
        return None
    caller, ordinal, _ = captured[_CAPTURED_AT]
    return next(
        (site for site in by_caller.get(caller, ()) if int(site["ordinal"]) == int(ordinal)),
        None,
    )


def _registration_of(
    site: Mapping[str, Any], registrations: tuple[dict[str, Any], ...]
) -> dict[str, Any] | None:
    """The declared registration `site` calls: its owner, its name and its parameter types."""
    recorded = site.get("descriptor")
    if recorded is None:
        return None
    return next(
        (
            registration
            for registration in registrations
            if registration["owner"] == site["owner"]
            and registration["method"] == site["name"]
            and parameter_types(registration["descriptor"]) == parameter_types(str(recorded))
        ),
        None,
    )


def _check_steps(catalog: Catalog) -> None:
    """Refuses a step carrying a `case` that names no single declared registration: its calls
    would be cases nothing says how to read, and a step and its registration spelled two ways
    would read every call of the overload as an unread case."""
    for step in catalog.matches.get("steps", []):
        if _CASE not in (step.get("captures") or {}):
            continue
        owners = catalog_symbols(step.get("owner"), f"{catalog.source}: steps[].owner")
        declared = step.get("descriptor")
        matching = [
            registration
            for registration in catalog.message_handlers
            if registration["owner"] in owners
            and registration["method"] == step.get("method")
            and declared is not None
            and parameter_types(registration["descriptor"]) == parameter_types(str(declared))
        ]
        if len(owners) != len(matching):
            raise CatalogError(
                f"loading catalog {catalog.source}: step `{step.get('method')}` "
                f"`{declared}` captures `{_CASE}` but {len(matching)} `message_handlers` "
                f"entries say how to read it on its {len(owners)} owner(s); each owner needs "
                f"exactly one (spec 2026-11-04 §3b)"
            )


def _ancestors(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Every class's direct ancestors in `type_hierarchy`, bare."""
    ancestors: dict[str, list[str]] = {}
    for row in workspace.query("type_hierarchy"):
        ancestors.setdefault(str(row["child"]), []).append(str(row["ancestor"]))
    return {child: tuple(parents) for child, parents in ancestors.items()}


def _with_inherited_roots(catalog: Catalog, ancestors: Mapping[str, tuple[str, ...]]) -> Catalog:
    """`catalog` with each root's owners widened by every class whose ancestry reaches one
    of them, so a call made through a subclass (`this.newReceiveBuilder()`) is the root it
    resolves to."""
    roots = catalog.matches.get("roots", [])
    widened = []
    for root in roots:
        owners = catalog_symbols(root.get("owner"), f"{catalog.source}: roots[].owner")
        heirs = sorted(child for child in ancestors if _reaches(child, owners, ancestors))
        if not heirs:
            widened.append(root)
            continue
        declared = root["owner"] if isinstance(root["owner"], list) else [root["owner"]]
        # A catalog names a type dotted and `catalog_symbols` converts it; a symbol without
        # its type marker converts to itself, so a class the facts name is written that way.
        widened.append({**root, "owner": [*declared, *map(without_type_marker, heirs)]})
    return replace(catalog, matches={**catalog.matches, "roots": widened})


def _reaches(child: str, owners: tuple[str, ...], ancestors: Mapping[str, tuple[str, ...]]) -> bool:
    """Whether `child`'s ancestry, followed to its end, reaches one of `owners`."""
    seen: set[str] = set()
    pending = list(ancestors.get(child, ()))
    while pending:
        current = pending.pop()
        if current in owners:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(ancestors.get(current, ()))
    return False
