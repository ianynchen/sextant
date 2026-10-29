"""`scheduled_chain` engine (D02 §2's `scheduled_chain` style; Quartz spec 2026-10-28 §3a,
§3b, §3d).

The second shape of evidence for `scheduled_work`, beside the annotation engine
(`engines/scheduled_work.py`): a schedule BUILT in code rather than declared on a method. A
style is a shape of evidence, not a framework, so this engine names no framework type —
every owner, method and kind word is the catalog's.

**It is built only on machinery that already exists** (§3d, ruling 6). The trigger chain is
the chain walk every builder catalog uses (`shapes/chains.py`): the catalog's `roots`,
`steps` and `terminal`, with three capture fields this engine reads — `name` and `group`
(the trigger's key) and `schedule` (the builder handed to it). Each chain end is one entry
(ruling 3): two triggers built alike are two rows, and nothing here collapses them. The
schedule builder is a nested chain, the ARGUMENT of a step (§2b), so it is followed with
the value walk's chain reader (`values.producers_of(..., along_receivers=True)`): every
builder call that built it, back along `receiver` links to its root, across returns, helpers
and parameters, in the path's own calling contexts. A cron handed in
as a configured field or parameter reads through the field ladder (`shapes/arguments.py`),
a non-cron chain is written by `shapes/chain_text.py`, and a placeholder is told by the
resolve's config model (`config.placeholder_rule`), never by a hard-coded opener.

**What a row says** (§3b):
- `trigger` — the kind, `kinds[...]` of the schedule chain's root owner, or of the first
  builder call found where no root is; where the walk reaches no builder call (a factory in
  a jar), of the type the call that produced the builder is DECLARED to return, which the
  compiler wrote; else NULL.
- `expression` — for the `literal_expression` root, its argument as the walk finds it:
  a string literal verbatim (`resolved`), or a `${…}` placeholder (`unresolved`). For any
  other root, the chain as written (ruling 4). NULL where the code does not hold it, with
  `expression_source` naming the call the walk stopped at (ruling 2): the row stays,
  `partial`, rather than being dropped.
- `name` — `group.name`, where both are constants; a key written with no group is in the
  catalog's `default_group`.

**`handler` is NULL in every row this engine writes today**, and so a chain whose kind is
not found says nothing and is not derived (§3a). Finding the job a trigger runs, and with
it the handler, is the next step of the same design and lands in this file.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import config_model_of, placeholder_rule
from sextant.application.resolve.shapes.arguments import (
    _CAPTURED_AT,
    CallFacts,
    FieldFacts,
    call_site_index,
    declared_parameters_of,
    field_expression,
    field_facts,
    supertypes_of,
)
from sextant.application.resolve.shapes.chain_text import chain_text
from sextant.application.resolve.shapes.chains import ChainEnd, chain_ends
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.application.resolve.values import (
    EXPRESSION,
    LITERAL,
    STRING,
    Answer,
    ValueIndex,
    cached_value_index,
    producers_of,
    resolve_positions,
)
from sextant.domain.symbols import method_descriptor, parameter_types, returned_type

_KINDS = "kinds"
_LITERAL_EXPRESSION = "literal_expression"
_DEFAULT_GROUP = "default_group"
# The capture fields this engine reads off a chain end — the catalog's steps name the
# argument each one reads (`argN`), and the chain walk folds them, last wins.
_NAME = "name"
_GROUP = "group"
_SCHEDULE = "schedule"

_RESOLVED = "resolved"
_UNRESOLVED = "unresolved"
_PARTIAL = "partial"
_NARROWED = "narrowed"


@dataclass(frozen=True)
class TriggerEntry:
    """One `scheduled_work` row and the method whose `newTrigger()`-style chain it came
    from — the row carries no location of its own, and a reader asking which trigger is
    which needs one."""

    caller: str
    row: dict[str, Any]


def run(workspace: Workspace, catalog: Catalog, catalogs: Sequence[Catalog] | None = None) -> None:
    """Every entry `entries` derives, appended to `scheduled_work` in the walk's order
    (NFR-1). The table is emptied once per resolve by the pipeline, never here: the
    annotation engine writes to it too."""
    rows = [entry.row for entry in entries(workspace, catalog, catalogs)]
    workspace.derive("scheduled_work_insert", rows=rows)


def entries(
    workspace: Workspace, catalog: Catalog, catalogs: Sequence[Catalog] | None = None
) -> list[TriggerEntry]:
    """One entry per chain end the walk yields, or one per distinct schedule where the walk
    finds several on separate paths (§1c's multiplicity: several paths are several values).

    `catalogs` is every catalog of the resolve, for the config model's placeholder opener
    (`config_model_of`, the choice the annotation engine and `resolved_schedules` make);
    a caller handing one catalog gets that catalog's model."""
    kinds, literal, default_group = _validated(catalog)
    ends = list(chain_ends(workspace, catalog))
    if not ends:
        # Most modules build no trigger: nothing below is read for them (GUIDELINES §8.7).
        return []
    opener = placeholder_rule(config_model_of(catalogs if catalogs is not None else [catalog]))[0][
        "open"
    ]
    index = cached_value_index(workspace)
    context = _Context(
        workspace=workspace,
        catalog=catalog,
        index=index,
        kinds=kinds,
        literal=literal,
        default_group=default_group,
        opener=opener,
        field_sources=field_facts(workspace, catalog),
        # Every call identity the module makes, for naming the call a walk to the
        # expression stopped at (`_source`); the kinds' owners, for the call that built a
        # schedule (`_schedules`). Both read off the index the resolve already built.
        every_call=frozenset((str(s["owner"]), str(s["name"])) for s in index.sites.values()),
        builder_calls=frozenset(
            (str(s["owner"]), str(s["name"])) for s in index.sites.values() if s["owner"] in kinds
        ),
    )
    return [entry for end in ends for entry in _entries_of(end, context)]


@dataclass(frozen=True)
class _Context:
    workspace: Workspace
    catalog: Catalog
    index: ValueIndex
    # Builder owner (the call site's own `owner` spelling) -> the kind word.
    kinds: Mapping[str, str]
    # `{owners, method, descriptor, arg}`, the owners converted.
    literal: Mapping[str, Any]
    default_group: str
    opener: str
    field_sources: FieldFacts | None
    every_call: frozenset[tuple[str, str]]
    builder_calls: frozenset[tuple[str, str]]


def _entries_of(end: ChainEnd, context: _Context) -> Iterator[TriggerEntry]:
    name = _name(end.captures, context)
    for trigger, expression, resolution, source in _schedules(end.captures, context):
        if trigger is None:
            # Neither a kind nor (yet) a job: the chain says nothing a reader could use
            # (§3a), and a row of NULLs would claim work nobody can name.
            continue
        yield TriggerEntry(
            caller=end.caller,
            row={
                "handler": None,
                "trigger": trigger,
                "name": name,
                "expression": expression,
                "expression_source": source,
                "resolution": resolution,
                "evidence": "compiler",
                "catalog_id": context.catalog.id,
            },
        )


def _name(captures: Mapping[str, Any], context: _Context) -> str | None:
    """`group.name` where the walk reads both as one string each, on every path; a key with
    no group is in the default group (Quartz's `Key`, CP-55 rows 10-18). NULL for a chain
    with no key step, or a key read at runtime."""
    name = _position(captures.get(_NAME), context)
    if name is None:
        return None
    positions = {_NAME: name}
    group = _position(captures.get(_GROUP), context)
    if group is not None:
        positions[_GROUP] = group
    names = {
        f"{_constant(answers.get(_GROUP)) if _GROUP in answers else context.default_group}"
        f".{_constant(answers[_NAME])}"
        for answers in resolve_positions(context.workspace, positions, context.index)
        if _constant(answers[_NAME]) is not None
        and (_GROUP not in answers or _constant(answers[_GROUP]) is not None)
    }
    return names.pop() if len(names) == 1 else None


def _position(
    argument: Mapping[str, Any] | None, context: _Context
) -> tuple[Mapping[str, Any], int] | None:
    """The `(site, slot)` a capture was read at (`chains._captured_at`), or None for a
    capture the chain does not carry, or one at a position its call does not have."""
    if not isinstance(argument, Mapping) or _CAPTURED_AT not in argument:
        return None
    caller, ordinal, slot = argument[_CAPTURED_AT]
    site = context.index.sites.get((str(caller), int(str(ordinal))))
    return None if site is None else (site, int(slot))


def _constant(answer: Answer | None) -> str | None:
    """A string the code states, exactly: one literal, not one of several candidates and not
    a value derived from one."""
    if (
        answer is None
        or answer.kind != LITERAL
        or answer.literal_kind != STRING
        or answer.inexact
        or answer.narrowed
    ):
        return None
    return str(answer.value)


def _schedules(
    captures: Mapping[str, Any], context: _Context
) -> list[tuple[str | None, str | None, str, str | None]]:
    """`(trigger, expression, resolution, expression_source)` for each distinct schedule the
    walk finds handed to the trigger, in its order.

    The builder chain is read by the value walk ALONG RECEIVERS (`producers_of`): every call
    on a `kinds` type that built the value, root first, across returns and helpers and in
    the path's own calling contexts — a helper's parameter is the argument at the call the
    walk came through, never another caller's."""
    position = _position(captures.get(_SCHEDULE), context)
    if position is None:
        return []
    site, slot = position
    declared_kind = _declared_kind(site, slot, context)
    found: list[tuple[str | None, str | None, str, str | None]] = []
    chains = [
        producer
        for producer in producers_of(
            context.index, site, slot, context.builder_calls, along_receivers=True
        )
        if producer.chain
    ]
    for producer in chains:
        sites = [context.index.sites[key] for key in producer.chain]
        if not producer.rooted:
            # A builder call was found and its root was not: the kind is the builder call's
            # own type, which is a `kinds` key by construction of the stop set.
            found.append((context.kinds.get(str(sites[0]["owner"])), None, _PARTIAL, None))
            continue
        kind = context.kinds[str(sites[0]["owner"])]
        if _is_literal_root(sites[0], context):
            found.extend((kind, *schedule) for schedule in _literal(sites[0], context))
            continue
        # A chain passed through a branch is not the chain as written: which step ran is not
        # known, so it has no text.
        text = None if producer.inexact else _text(sites, context)
        found.append(
            (kind, text, _RESOLVED, None) if text is not None else (kind, None, _PARTIAL, None)
        )
    if not chains:
        # The walk ends before any builder call (§3b): a factory in a jar, a helper whose body
        # it cannot read. The kind is still the type the producing call is declared to return.
        found.append((declared_kind, None, _PARTIAL, None))
    return list(dict.fromkeys(found))


def _text(sites: list[Mapping[str, Any]], context: _Context) -> str | None:
    """The chain as written: each method's run of calls by `chain_text`, whose nested
    arguments are value ids of that method alone, joined in chain order."""
    parts: list[str] = []
    run: list[Mapping[str, Any]] = []
    for site in sites:
        if run and run[-1]["caller"] != site["caller"]:
            part = chain_text(run, _effective(str(run[-1]["caller"]), context))
            if part is None:
                return None
            parts.append(part)
            run = []
        run.append(site)
    part = chain_text(run, _effective(str(run[-1]["caller"]), context))
    return None if part is None else ".".join([*parts, part])


def _declared_kind(site: Mapping[str, Any], slot: int, context: _Context) -> str | None:
    """The kind of the type the call producing `site`'s argument at `slot` is DECLARED to
    return, read off that call's descriptor — a fact the compiler wrote, not a model of the
    call's body (§3b, §3g). None where the argument is not a call's result in this method,
    or the type is not a kind the catalog names (the interface every builder implements)."""
    arguments = site["arguments"] or []
    source = arguments[slot].get("source") if slot < len(arguments) else None
    if source is None:
        return None
    ordinals = context.index.producers.get((str(site["caller"]), int(str(source))), ())
    if not ordinals:
        return None
    producer = context.index.sites.get((str(site["caller"]), min(ordinals)))
    if producer is None or not producer.get("descriptor"):
        return None
    return context.kinds.get(returned_type(str(producer["descriptor"])) or "")


def _is_literal_root(root: Mapping[str, Any], context: _Context) -> bool:
    literal = context.literal
    return (
        root["owner"] in literal["owners"]
        and root["name"] == literal["method"]
        and (
            literal["descriptor"] is None
            or parameter_types(str(literal["descriptor"]))
            == parameter_types(str(root.get("descriptor") or "()"))
        )
    )


def _literal(
    root: Mapping[str, Any], context: _Context
) -> list[tuple[str | None, str, str | None]]:
    """`(expression, resolution, expression_source)` for the `literal_expression` root's
    argument, one per distinct answer: the field ladder's `${…}` for a configured field or
    parameter, else the value walk's string, verbatim. Steps after the root are not part of
    the expression, as they are not for `@Scheduled` (§3b)."""
    slot = int(context.literal["arg"])
    arguments = root["arguments"] or []
    argument = arguments[slot] if slot < len(arguments) else None
    caller = str(root["caller"])
    configured = field_expression(
        argument, context.field_sources, _call_facts(caller, context), caller
    )
    if configured is not None:
        return [(configured, _resolution_of(configured, False, context), None)]
    found: list[tuple[str | None, str, str | None]] = []
    for answers in resolve_positions(context.workspace, {"value": (root, slot)}, context.index):
        answer = answers["value"]
        if answer.kind == LITERAL and answer.literal_kind == STRING and not answer.inexact:
            found.append(
                (
                    str(answer.value),
                    _resolution_of(str(answer.value), answer.narrowed, context),
                    None,
                )
            )
        elif (
            answer.kind == EXPRESSION and context.opener in str(answer.value) and not answer.inexact
        ):
            found.append((str(answer.value), _UNRESOLVED, None))
        else:
            # Read at runtime (ruling 2): the entry stays, naming where the walk stopped.
            found.append((None, _PARTIAL, _source(root, slot, context)))
    return list(dict.fromkeys(found))


def _resolution_of(expression: str, narrowed: bool, context: _Context) -> str:
    if narrowed:
        return _NARROWED
    return _UNRESOLVED if context.opener in expression else _RESOLVED


def _source(root: Mapping[str, Any], slot: int, context: _Context) -> str | None:
    """The method whose result the argument is — the call the walk reached and could read
    no value from (`row.getCron()`), as its bare symbol; None where the walk ends anywhere
    else (a parameter nothing calls, a field), or at several such calls."""
    called = {
        method_descriptor(
            str(site["owner"]), str(site["name"]), str(site.get("descriptor") or "()")
        )
        for producer in producers_of(context.index, root, slot, context.every_call)
        if producer.caller is not None
        and producer.ordinal is not None
        and (site := context.index.sites.get((producer.caller, producer.ordinal))) is not None
    }
    return called.pop() if len(called) == 1 else None


def _effective(caller: str, context: _Context) -> dict[Any, Mapping[str, Any]]:
    """`caller`'s call sites by the value id each one produces, for `chain_text`'s nested
    arguments: a constructor's value is its `receiver` (CP-3), every other call's its
    `result`."""
    sites = context.workspace.once(call_site_index).by_caller.get(caller, [])
    return {
        (site["receiver"] if site["name"] == "<init>" else site["result"]): site
        for site in sites
        if (site["receiver"] if site["name"] == "<init>" else site["result"]) is not None
    }


def _call_facts(caller: str, context: _Context) -> CallFacts:
    """The field ladder's per-caller facts — its getter rung reads the caller's own sites."""
    workspace = context.workspace
    return CallFacts(
        supertypes=workspace.once(supertypes_of),
        caller_call_sites=workspace.once(call_site_index).by_caller.get(caller, []),
        referenced=[],
        caller_parameters=workspace.once(declared_parameters_of).get(caller, ()),
    )


def _validated(catalog: Catalog) -> tuple[dict[str, str], dict[str, Any], str]:
    """`kinds`, `literal_expression` and `default_group`, refused when malformed — each
    reaches a published column, where a typo is indistinguishable from an observation (the
    `scheduled_work._validate_matches` precedent). The chain's own keys are the walk's to
    check (`chain_ends`)."""
    matches = catalog.matches
    kinds = matches.get(_KINDS)
    if not (
        isinstance(kinds, dict)
        and kinds
        and all(isinstance(owner, str) and isinstance(kind, str) for owner, kind in kinds.items())
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_KINDS}` must be a non-empty mapping of "
            f"`builder type: kind word`, got {kinds!r} (D02 §2's `scheduled_chain` style)"
        )
    owned = {
        symbol: str(kind)
        for owner, kind in kinds.items()
        for symbol in catalog_symbols(owner, f"{catalog.source}: {_KINDS}")
    }
    literal = matches.get(_LITERAL_EXPRESSION)
    if not (
        isinstance(literal, dict)
        and isinstance(literal.get("method"), str)
        and isinstance(literal.get("arg"), int)
        and not isinstance(literal.get("arg"), bool)
        and literal["arg"] >= 0
        and (literal.get("descriptor") is None or isinstance(literal.get("descriptor"), str))
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_LITERAL_EXPRESSION}` must be "
            f"`{{owner, method, arg, descriptor?}}` with `arg` an argument index, got "
            f"{literal!r} (D02 §2's `scheduled_chain` style)"
        )
    default_group = matches.get(_DEFAULT_GROUP)
    if not isinstance(default_group, str) or not default_group:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_DEFAULT_GROUP}` must name the group a key "
            f"written without one is in, got {default_group!r} (D02 §2's `scheduled_chain` "
            f"style)"
        )
    return (
        owned,
        {
            "owners": catalog_symbols(
                literal.get("owner"), f"{catalog.source}: {_LITERAL_EXPRESSION}.owner"
            ),
            "method": literal["method"],
            "descriptor": literal.get("descriptor"),
            "arg": literal["arg"],
        },
        default_group,
    )
