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
the value walk's chain reader (`values.producer_paths(..., along_receivers=True)`): every
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
  `partial`, rather than being dropped. A trigger handed no schedule at all runs on the
  catalog's `default_schedule` (Quartz's `build()` uses `simpleSchedule()`), written as
  that call.
- `name` — `group.name`, where both are constants; a key written with no group is in the
  catalog's `default_group`.

- `handler` — the body Quartz runs for the trigger's job (§3c), or NULL where the job is
  not found.

**The job** is found from whatever pairs it with the trigger, as Quartz pairs them, and
every pairing is machinery that already exists:
- a pairing call (`scheduleJob(job, trigger)`) is the chain walk's execute-join: the catalog's
  `pairing` entries become a `terminal_via_argument` join on the trigger chain, so the chain
  end lists every such call the value walk traces the built trigger to (`ChainEnd
  .consumers`), across returns and parameters; the walk from that call's job argument
  reaches the `build()` of a job chain;
- `forJob(JobDetail)` is the walk from its argument, and where that argument is a `@Bean`
  method's own parameter, the bean the container injects there (`beans.injected_bean`);
- `forJob(name[, group])` and `forJob(JobKey)` name the job chain anywhere in the module
  whose key is that key, a name with no group in the default group.

A job chain is the same chain walk again, from the catalog's `job_root`, and its class is
the value walk's answer for the root's class argument — several classes on one branch
arrive `narrowed`, one answer each (ruling 7).

**The handler** is the body the JVM's dispatch rule picks for the job class's
`entry_method` (`dispatch.Dispatch.resolve`), never a walk of superclasses here. Where that
body is in a jar, the type the search left the workspace at (`Dispatch.boundary`) is looked
up in `supertype_dispatch`: a framework template the catalog says calls a subclass method
hands the handler to that method, resolved the same way; any other unread body gives none.
Several job classes reaching ONE body are one row, at the row's own resolution; several
bodies from one branch are a row each, `narrowed` (§3c).

**A row is `resolved` only from ONE binding.** The key, the literal root's argument and the
job root's class are read in one `values.resolve_positions` call, WITHIN the path the
schedule took to `withSchedule` and the path the trigger and the job took to the call that
paired them (`values.producer_paths`): each row holds the values one path gives.
`addJob(jobClass, cron)` called twice is two rows, never four, and a trigger built in a
helper and scheduled by each caller keeps each caller's cron with that caller's job. A
trigger and a job that reached the pairing call through different callers are no pairing;
a pairing no one path holds only because each passed through one helper on its own call is
read part by part, `partial`, and a part no binding ties to
the row — the name, the cron, the job's class — is kept only where every path agrees on it,
else NULL; rows equal but for their resolution are one, at the weaker word. A job named by a
key a `job_key` call builds is paired on the path to that call.

**`resolution`** (§3a): `resolved` with handler and expression both known and no
placeholder; `unresolved` where the only gap is a placeholder; `narrowed` where the only gap
is a branch; `partial` otherwise. A chain whose job and kind are both unknown says nothing
and is not derived.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.beans import (
    BeanTable,
    Unresolved,
    bean_table,
    injected_bean,
)
from sextant.application.resolve.config import config_model_of, placeholder_rule
from sextant.application.resolve.dispatch import Dispatch, dispatch_of
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
    RECEIVER,
    STRING,
    SYMBOL,
    Answer,
    Path,
    ValueIndex,
    cached_value_index,
    producer_paths,
    producers_of,
    resolve_positions,
)
from sextant.domain.symbols import (
    bare_descriptor,
    method_descriptor,
    method_type_descriptor,
    parameter_types,
    returned_type,
    type_descriptor,
)

_KINDS = "kinds"
_LITERAL_EXPRESSION = "literal_expression"
_DEFAULT_GROUP = "default_group"
_DEFAULT_SCHEDULE = "default_schedule"
# The capture fields this engine reads off a chain end — the catalog's steps name the
# argument each one reads (`argN`), and the chain walk folds them, last wins.
_NAME = "name"
_GROUP = "group"
_SCHEDULE = "schedule"
# The job keys (spec §3c), each its own catalog key.
_JOB_ROOT = "job_root"
_JOB_IDENTITY_STEP = "job_identity_step"
_FOR_JOB = "for_job"
_JOB_KEY = "job_key"
_PAIRING = "pairing"
_ENTRY_METHOD = "entry_method"
_SUPERTYPE_DISPATCH = "supertype_dispatch"
# The capture fields the `for_job` steps write on the trigger chain: the `JobDetail` handed
# over, a key's name and group, a `JobKey`.
_JOB_DETAIL = "job_detail"
_JOB_NAME = "job_name"
_JOB_GROUP = "job_group"
_JOB_KEY_FIELD = "job_key"
_ARG = re.compile(r"^arg(\d+)$")
# The two positions read with the trigger's key on each path (`_on_paths`): the literal
# root's argument and the job root's class.
_VALUE = "value"
_CLASS = "class"

# The path that constrains nothing: a value read on it may be on any path.
_ANY_PATH = Path()

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
    finds several on separate paths (§1c's multiplicity: several paths are several values),
    and per distinct handler where the job is several classes.

    `catalogs` is every catalog of the resolve, for the config model's placeholder opener
    (`config_model_of`, the choice the annotation engine and `resolved_schedules` make);
    a caller handing one catalog gets that catalog's model."""
    kinds, literal, default_group, default_schedule = _validated(catalog)
    rules = _job_rules(catalog)
    trigger_walk, job_walk = _walks(catalog, rules)
    ends = list(chain_ends(workspace, trigger_walk))
    if not ends:
        # Most modules build no trigger: nothing below is read for them (GUIDELINES §8.7).
        return []
    opener = placeholder_rule(config_model_of(catalogs if catalogs is not None else [catalog]))[0][
        "open"
    ]
    index = cached_value_index(workspace)
    job_ends = list(chain_ends(workspace, job_walk))
    context = _Context(
        workspace=workspace,
        catalog=catalog,
        index=index,
        kinds=kinds,
        literal=literal,
        default_group=default_group,
        default_schedule=default_schedule,
        opener=opener,
        field_sources=field_facts(workspace, catalog),
        # Every call identity the module makes, for naming the call a walk to the
        # expression stopped at (`_source`); the kinds' owners, for the call that built a
        # schedule (`_schedules`). Both read off the index the resolve already built.
        every_call=frozenset((str(s["owner"]), str(s["name"])) for s in index.sites.values()),
        builder_calls=frozenset(
            (str(s["owner"]), str(s["name"])) for s in index.sites.values() if s["owner"] in kinds
        ),
        rules=rules,
        job_ends=job_ends,
        # The `build()` calls the two walks ended at, by identity: where a walk from a
        # pairing call's argument stops, so it names the built value and never reads past.
        built=frozenset(
            (str(end.terminal["owner"]), str(end.terminal["name"]))
            for end in (*ends, *job_ends)
            if end.terminal is not None
        ),
        dispatch=dispatch_of(workspace),
        # The container's beans, read only where a trigger names its job by a `JobDetail`.
        # No channel names: they answer only a reference typed as a message channel, and
        # what this reads is a job.
        beans=(
            bean_table(workspace, catalog, frozenset())
            if any(_JOB_DETAIL in end.captures for end in ends)
            else None
        ),
    )
    by_key: dict[str, list[ChainEnd]] = {}
    for job in job_ends:
        key = _key(job.captures.get(_NAME), job.captures.get(_GROUP), context)
        if key is not None:
            by_key.setdefault(key, []).append(job)
    context = replace(context, jobs_by_key=by_key)
    return [entry for end in ends for entry in _entries_of(end, context)]


@dataclass(frozen=True)
class _Method:
    """A method a catalog names: its name and the JVM descriptor `dispatch.py` resolves."""

    name: str
    descriptor: str


@dataclass(frozen=True)
class _Pairing:
    """A call that pairs a built job with a built trigger, and the argument each is."""

    owners: tuple[str, ...]
    method: str
    descriptor: str
    job: int
    trigger: int


@dataclass(frozen=True)
class _KeyBuilder:
    """A call that builds a job key, and the argument each half of the key is."""

    owners: tuple[str, ...]
    method: str
    name: int
    group: int | None


@dataclass(frozen=True)
class _JobRules:
    root: Mapping[str, Any]  # `{owner, method}`, as the chain walk reads a root
    class_arg: int
    identity_step: Mapping[str, Any]
    for_job: tuple[Mapping[str, Any], ...]
    key_builders: tuple[_KeyBuilder, ...]
    pairing: tuple[_Pairing, ...]
    entry: _Method
    # The bare supertype -> the method its template calls on the subclass.
    templates: Mapping[str, _Method]


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
    # The schedule a trigger built with no `withSchedule` runs on, as a row writes it.
    default_schedule: "_Schedule"
    opener: str
    field_sources: FieldFacts | None
    every_call: frozenset[tuple[str, str]]
    builder_calls: frozenset[tuple[str, str]]
    rules: _JobRules
    job_ends: list[ChainEnd]
    built: frozenset[tuple[str, str]]
    dispatch: Dispatch
    beans: BeanTable | None
    # `group.name` -> the job chains with that key, in walk order.
    jobs_by_key: Mapping[str, list[ChainEnd]] | None = None


def _walks(catalog: Catalog, rules: _JobRules) -> tuple[Catalog, Catalog]:
    """The catalog as the chain walk reads it, twice: the trigger chain, whose steps gain
    the `for_job` overloads and whose terminal gains the pairing calls as an execute-join
    (`terminal_via_argument`), so each end lists the calls that pair its trigger; and the
    job chain, from `job_root` with `job_identity_step`, ending where the trigger chain
    ends. Both are the catalog's own words, rearranged for the one walk every builder
    catalog uses — nothing here walks a chain."""
    matches = catalog.matches
    terminal = list(matches.get("terminal", []))
    plain = [entry for entry in terminal if isinstance(entry, str)]
    # In the catalog's own dotted spelling, which the join converts (`rules.pairing` holds
    # them converted).
    declared = matches[_PAIRING]
    join = {
        "owner": sorted({str(owner) for entry in declared for owner in _names(entry["owner"])}),
        "method": sorted({pairing.method for pairing in rules.pairing}),
    }
    trigger_walk = replace(
        catalog,
        matches={
            **matches,
            "steps": [*matches.get("steps", []), *rules.for_job],
            "terminal": [
                *terminal,
                *({"method": name, "terminal_via_argument": join} for name in plain),
            ],
        },
    )
    job_walk = replace(
        catalog,
        matches={
            "roots": [dict(rules.root)],
            "steps": [dict(rules.identity_step)],
            "terminal": plain,
        },
    )
    return trigger_walk, job_walk


@dataclass(frozen=True)
class _Schedule:
    """One schedule handed to a trigger: its kind, and its expression where that is known
    whatever path reached it."""

    kind: str | None
    expression: str | None = None
    resolution: str = _PARTIAL
    source: str | None = None
    # The `literal_expression` root whose argument IS the expression, read on each path
    # together with the trigger's key and the job's class (`_on_paths`); None where the
    # expression above is already the answer.
    literal: tuple[str, int] | None = None
    # The path the walk took from `withSchedule` to the builder chain: the trigger's key
    # and the literal's argument are read within it.
    path: Path = _ANY_PATH


@dataclass(frozen=True)
class _Found:
    """One path's row, before rows equal but for their resolution are one (`_entries_of`)."""

    name: str | None
    trigger: str | None
    expression: str | None
    resolution: str  # the expression's own
    source: str | None
    handler: str | None
    narrowed: bool
    # Every part above came from ONE binding of one read (`_on_paths`); False where they
    # were read apart (`_apart`), which is never `resolved`.
    tied: bool = True
    # The parts read apart that are NULL because the paths disagree on them, not because the
    # code states none (`_apart`), in the table's column order.
    untied: tuple[str, ...] = ()


def _entries_of(end: ChainEnd, context: _Context) -> Iterator[TriggerEntry]:
    """The rows of one chain end, one per distinct row the paths give.

    **A row is `resolved` only when every part of it comes from ONE binding of one read**
    (`_on_paths`): the trigger's key, the literal cron and the job's class, read together
    WITHIN the path the schedule took to the trigger and the path the trigger and the job
    took to the call that paired them (`_pairings`). So the `addJob(jobClass, cron)` helper
    two callers call is two rows, and a trigger built in `trigger(cron)` and scheduled by
    each of its callers keeps each caller's cron with that caller's job. A pairing no path
    can hold is read part by part (`_apart`), and such a row is never `resolved`."""
    pairings = _pairings(end, context)
    found: list[_Found] = []
    for schedule in _schedules(end.captures, context):
        rows: list[_Found] = []
        for job, path in pairings:
            if path is None:
                rows.extend(_apart(end, schedule, job, context))
                continue
            anchor = schedule.path.joined(path)
            # A schedule and a pairing on paths that disagree are never one trigger's: no
            # row.
            if anchor is not None:
                rows.extend(_on_paths(end, schedule, job, anchor, context))
        # A schedule no pairing's path reaches is a trigger nothing on its path schedules:
        # its row names no job.
        found.extend(rows or _on_paths(end, schedule, None, schedule.path, context))
    # Neither a kind nor a job: the chain says nothing a reader could use (§3a), and a row
    # of NULLs would claim work nobody can name.
    found = [row for row in found if row.trigger is not None or row.handler is not None]
    # Classes on one branch (`narrowed` answers) reaching ONE body are one row at its own
    # resolution; reaching several, each row is `narrowed` (§3c).
    branched = {row.handler for row in found if row.narrowed}
    rows_by_key: dict[
        tuple[str | None, str | None, str | None, str | None, str | None, tuple[str, ...]], str
    ] = {}
    for row in found:
        resolution = (
            _row_resolution(row.handler, row.narrowed and len(branched) > 1, row.resolution)
            if row.tied
            else _PARTIAL
        )
        key = (row.name, row.trigger, row.expression, row.source, row.handler, row.untied)
        # One body found exactly on one path and through a branch on another is one row,
        # at the weaker word: that it may not run is the true half.
        rows_by_key[key] = (
            resolution if key not in rows_by_key else _weaker(rows_by_key[key], resolution)
        )
    for (name, trigger, expression, source, handler, untied), resolution in rows_by_key.items():
        yield TriggerEntry(
            caller=end.caller,
            row={
                "handler": handler,
                "trigger": trigger,
                "name": name,
                "expression": expression,
                "expression_source": source,
                "resolution": resolution,
                "evidence": "compiler",
                "catalog_id": context.catalog.id,
                "untied": list(untied) or None,
            },
        )


def _positions(
    end: ChainEnd, schedule: _Schedule, job: ChainEnd | None, context: _Context
) -> tuple[dict[str, tuple[Mapping[str, Any], int | str]], Mapping[str, Any] | None]:
    """The positions a row is read from — the trigger's key, the literal root's argument,
    the job root's class — and the literal root, where the schedule has one."""
    positions: dict[str, tuple[Mapping[str, Any], int | str]] = {}
    name = _position(end.captures.get(_NAME), context)
    group = _position(end.captures.get(_GROUP), context)
    if name is not None:
        positions[_NAME] = name
        if group is not None:
            positions[_GROUP] = group
    root = None if schedule.literal is None else context.index.sites[schedule.literal]
    slot = int(context.literal["arg"])
    if root is not None and slot < len(root["arguments"] or []):
        positions[_VALUE] = (root, slot)
    if job is not None and context.rules.class_arg < len(job.root["arguments"] or []):
        positions[_CLASS] = (job.root, context.rules.class_arg)
    return positions, root


def _on_paths(
    end: ChainEnd,
    schedule: _Schedule,
    job: ChainEnd | None,
    anchor: Path,
    context: _Context,
) -> list[_Found]:
    """A row per binding of ONE read of every position (`values.resolve_positions`),
    within `anchor`: on each, the values that binding gives and no other's. Where no
    binding reaches every position at once, the parts are read apart (`_apart`)."""
    positions, root = _positions(end, schedule, job, context)
    paths = (
        resolve_positions(context.workspace, positions, context.index, within=anchor)
        if positions
        else [{}]
    )
    if not paths:
        return _apart(end, schedule, job, context)
    slot = int(context.literal["arg"])
    found: list[_Found] = []
    for answers in paths:
        expression, resolution, source = schedule.expression, schedule.resolution, schedule.source
        if root is not None:
            expression, resolution, source = _expression(answers.get(_VALUE), root, slot, context)
        job_class, narrowed = _job_class(answers.get(_CLASS))
        found.append(
            _Found(
                name=_key_of(answers, context),
                trigger=schedule.kind,
                expression=expression,
                resolution=resolution,
                source=source,
                handler=None if job_class is None else _handler(job_class, context),
                narrowed=narrowed,
            )
        )
    return found


def _apart(
    end: ChainEnd, schedule: _Schedule, job: ChainEnd | None, context: _Context
) -> list[_Found]:
    """The row of a pairing no single binding holds, every part read on its own, `partial`.

    **A part no binding ties to the row is kept only where every path agrees on it;
    otherwise it is NULL** — the name (`_keys`), the cron, the job's class alike. Two paths
    giving two values say nothing about which one THIS pairing ran with, and publishing each
    beside the other parts would state pairings no execution builds. A cron that varies is
    NULL with `expression_source` naming where the walk stopped (`_varies_at`). **Each part
    NULL for that reason is named in `untied`**: the code does state it, so the row must not
    read as though it did not."""
    positions, root = _positions(end, schedule, job, context)
    slot = int(context.literal["arg"])
    expression, resolution, source = schedule.expression, schedule.resolution, schedule.source
    cron_varies = False
    if root is not None:
        read = (
            resolve_positions(
                context.workspace,
                {_VALUE: positions[_VALUE]},
                context.index,
                within=schedule.path,
            )
            if _VALUE in positions
            else []
        )
        expressions = {
            _expression(answers.get(_VALUE), root, slot, context) for answers in read or [{}]
        }
        cron_varies = len(expressions) > 1
        expression, resolution, source = (
            expressions.pop()
            if len(expressions) == 1
            else (None, _PARTIAL, _varies_at(root, slot, context))
        )
    read = (
        resolve_positions(context.workspace, {_CLASS: positions[_CLASS]}, context.index)
        if _CLASS in positions
        else []
    )
    classes = {_job_class(answers.get(_CLASS)) for answers in read or [{}]}
    job_class, narrowed = classes.pop() if len(classes) == 1 else (None, False)
    names = _keys(end.captures.get(_NAME), end.captures.get(_GROUP), context)
    untied = {
        "handler": len(classes) > 1,
        "name": len(names) > 1,
        "expression": cron_varies,
    }
    return [
        _Found(
            name=names.pop() if len(names) == 1 else None,
            trigger=schedule.kind,
            expression=expression,
            resolution=resolution,
            source=source,
            handler=None if job_class is None else _handler(job_class, context),
            narrowed=narrowed,
            tied=False,
            untied=tuple(part for part, varies in untied.items() if varies),
        )
    ]


def _varies_at(root: Mapping[str, Any], slot: int, context: _Context) -> str | None:
    """Where the walk to a cron that differs between paths stopped being one value: the
    method whose PARAMETER the argument is, where it is one (each caller hands its own), as
    its bare symbol; else the call `_source` names."""
    arguments = root["arguments"] or []
    argument = arguments[slot] if slot < len(arguments) else None
    if isinstance(argument, Mapping) and argument.get("kind") == "parameter":
        return bare_descriptor(str(root["caller"]))
    return _source(root, slot, context)


# The resolution words from the strongest claim to the weakest.
_STRENGTH = (_RESOLVED, _UNRESOLVED, _NARROWED, _PARTIAL)


def _weaker(one: str, other: str) -> str:
    return max(one, other, key=_STRENGTH.index)


def _row_resolution(handler: str | None, narrowed: bool, expression: str) -> str:
    """§3a, from the handler and the expression's own resolution: one gap of one kind is
    that kind's word, a missing half or two gaps at once are `partial`."""
    if handler is None or expression == _PARTIAL:
        return _PARTIAL
    if narrowed:
        return _NARROWED if expression in (_RESOLVED, _NARROWED) else _PARTIAL
    return expression


def _pairings(end: ChainEnd, context: _Context) -> list[tuple[ChainEnd | None, Path | None]]:
    """The job chains the trigger of `end` runs, by every pairing Quartz honours (§3c), each
    with the path that ties it to the trigger, in order and once each: the pairing calls its
    built value reaches, then its `forJob`. `(None, _ANY_PATH)` where no job is found.

    A pairing call's path is the trigger's path to it JOINED with the job's: both values
    are what one call was handed. Where every join disagrees on a caller crossed out to,
    the two came from different executions and there is no pairing; where they disagree
    only on which call of one helper handed each back, the pairing is real but no one path
    holds it, and the path is None (`_apart` reads the row). A job named by a constant
    `forJob(name)` key, or injected as a bean, is paired on any path, being the same on
    every one; a job named by a key a `job_key` call builds is paired on the path to that
    call (`_built_keys`)."""
    found: list[tuple[ChainEnd | None, Path | None]] = []
    for consumer in end.consumers:
        for pairing in context.rules.pairing:
            if not (
                consumer["owner"] in pairing.owners
                and consumer["name"] == pairing.method
                and consumer.get("descriptor") == pairing.descriptor
            ):
                continue
            triggers = _trigger_paths(consumer, pairing.trigger, end, context)
            for job, path in _built_jobs(consumer, pairing.job, context) if triggers else []:
                joined = [
                    both for trigger in triggers if (both := trigger.joined(path)) is not None
                ]
                found.extend((job, both) for both in joined)
                # A trigger and a job that reached this call through DIFFERENT callers of
                # the method holding it are two executions: no pairing. Only where the
                # paths disagree solely on which call of one helper handed each back (the
                # M-1 bound) is the pairing real and read apart (`_apart`).
                if not joined and any(
                    trigger.two_calls_of_one_helper(path) for trigger in triggers
                ):
                    found.append((job, None))
    position = _position(end.captures.get(_JOB_DETAIL), context)
    if position is not None:
        found.extend(_built_jobs(*position, context))
        # A bean is the one the container injects, whichever path reached the method that
        # takes it: the pairing holds on any path.
        found.extend((job, _ANY_PATH) for job in _injected_jobs(*position, context))
    # A `forJob(name[, group])` key is one constant on EVERY path (`_key`), so the job it
    # names is paired on any path; a key built by a `job_key` call is paired on the path
    # the walk took to that call (`_built_keys`).
    key = _key(end.captures.get(_JOB_NAME), end.captures.get(_JOB_GROUP), context)
    position = _position(end.captures.get(_JOB_KEY_FIELD), context)
    keys = [(key, _ANY_PATH)] if key is not None else []
    if position is not None:
        keys.extend(_built_keys(*position, context))
    for named, path in keys:
        found.extend((job, path) for job in (context.jobs_by_key or {}).get(named, ()))
    unique = {
        (None if job is None or job.terminal is None else _site_key(job.terminal), path): (
            job,
            path,
        )
        for job, path in found
    }
    return list(unique.values()) or [(None, _ANY_PATH)]


def _trigger_paths(
    consumer: Mapping[str, Any], slot: int, end: ChainEnd, context: _Context
) -> list[Path]:
    """The paths by which the value walk from `consumer`'s argument at `slot` reaches
    `end`'s own `build()`: a pairing call joins the trigger it is handed in its trigger
    argument, on each such path."""
    if end.terminal is None:
        return []
    terminal = _site_key(end.terminal)
    return [
        path
        for producer, path in producer_paths(
            context.index,
            consumer,
            slot,
            context.built,
            past_accessors=context.dispatch.ancestors,
        )
        if (producer.caller, producer.ordinal) == terminal
    ]


def _built_jobs(
    site: Mapping[str, Any], slot: int, context: _Context
) -> list[tuple[ChainEnd, Path]]:
    """The job chains whose `build()` the value walk from `site`'s argument at `slot`
    reaches, in this method or across returns and parameters, each with its path.

    An accessor on the built detail is let past (`past_accessors`): RuoYi's
    `jobDetail.getJobDataMap().put(KEY, job)` does not change which `build()` made it.
    `_trigger_paths` asks the same question of the trigger and walks the same way."""
    ends = {_site_key(job.terminal): job for job in context.job_ends if job.terminal}
    return [
        (ends[(producer.caller, producer.ordinal)], path)
        for producer, path in producer_paths(
            context.index, site, slot, context.built, past_accessors=context.dispatch.ancestors
        )
        if producer.caller is not None
        and producer.ordinal is not None
        and (producer.caller, producer.ordinal) in ends
    ]


def _injected_jobs(site: Mapping[str, Any], slot: int, context: _Context) -> list[ChainEnd]:
    """The job chain a `@Bean` method's own parameter is injected with (Controller ruling
    R2): Spring calls a factory method with the bean it picks for each parameter, by the
    bean model's rungs (`beans.injected_bean`), and the job is the chain that bean's own
    method builds and returns. None for an argument that is not a parameter, or a method
    that declares no bean — nothing injects it."""
    arguments = site["arguments"] or []
    argument = arguments[slot] if slot < len(arguments) else None
    caller = str(site["caller"])
    beans = context.beans
    if (
        beans is None
        or not isinstance(argument, Mapping)
        or argument.get("kind") != "parameter"
        or not isinstance(argument.get("value"), int)
        or beans.bean_called(caller) is None
    ):
        return []
    bean = injected_bean(
        beans,
        caller,
        context.workspace.once(declared_parameters_of).get(caller, ()),
        int(argument["value"]),
        context.catalog.bean_model,
    )
    if isinstance(bean, Unresolved) or bean.method is None:
        return []
    returned = {
        entry.get("source") for _, entry in context.index.returned_values.get(bean.method, ())
    }
    return [
        job
        for job in context.job_ends
        if job.caller == bean.method
        and job.terminal is not None
        and job.terminal["result"] in returned
    ]


def _built_keys(site: Mapping[str, Any], slot: int, context: _Context) -> list[tuple[str, Path]]:
    """The keys a `JobKey` argument is built from, each with the path the walk took to it:
    the value walk to the catalog's `job_key` call that made it, and that call's name and
    group as constants on that path. A key handed into a helper by several callers is one
    key per caller, and the path keeps each with its own caller's other arguments."""
    declared = {
        (owner, builder.method)
        for builder in context.rules.key_builders
        for owner in builder.owners
    }
    keys: list[tuple[str, Path]] = []
    for producer, path in producer_paths(context.index, site, slot, declared):
        if producer.caller is None or producer.ordinal is None or producer.identity is None:
            continue
        built = context.index.sites[(producer.caller, producer.ordinal)]
        for builder in context.rules.key_builders:
            if producer.identity[0] not in builder.owners or producer.identity[1] != builder.method:
                continue
            group = builder.group
            arity = len(built["arguments"] or [])
            key = _key_at(
                (built, builder.name) if builder.name < arity else None,
                (built, group) if group is not None and group < arity else None,
                context,
                within=path,
            )
            if key is not None:
                keys.append((key, path))
    return keys


def _job_class(answer: Answer | None) -> tuple[str | None, bool]:
    """`(class, narrowed)` for one answer for the job root's class argument — a class
    literal by its bare type; None for anything else."""
    if (
        answer is not None
        and answer.kind == LITERAL
        and answer.literal_kind == SYMBOL
        and not answer.inexact
    ):
        return str(answer.value), answer.narrowed
    return None, False


def _handler(job_class: str, context: _Context) -> str | None:
    """The body Quartz runs for an instance of `job_class` (§3c, DR-6): the entry method's
    body by the JVM's own dispatch rule; where that is in a jar, the method the catalog
    says that jar type's template calls on the subclass, resolved the same way; else
    None. The module-prefixed symbol of the one body read, as every handler is spelled."""
    dispatch = context.dispatch
    method = context.rules.entry
    declaring, _ = dispatch.resolve(job_class, method.name, method.descriptor)
    if declaring is None:
        template = context.rules.templates.get(
            dispatch.boundary(job_class, method.name, method.descriptor) or ""
        )
        if template is None:
            return None
        method = template
        declaring, _ = dispatch.resolve(job_class, method.name, method.descriptor)
        if declaring is None:
            return None
    bodies = dispatch.bodies.get(method_descriptor(declaring, method.name, method.descriptor), [])
    return bodies[0] if len(bodies) == 1 else None


def _site_key(site: Mapping[str, Any]) -> tuple[str, int]:
    return (str(site["caller"]), int(str(site["ordinal"])))


def _key(
    name: Mapping[str, Any] | None, group: Mapping[str, Any] | None, context: _Context
) -> str | None:
    """The key two captures name, `group.name` (`_key_at`)."""
    return _key_at(_position(name, context), _position(group, context), context)


def _keys(
    name: Mapping[str, Any] | None, group: Mapping[str, Any] | None, context: _Context
) -> set[str]:
    """Every key two captures name on some path (`_keys_at`)."""
    return _keys_at(_position(name, context), _position(group, context), context)


def _key_at(
    name: tuple[Mapping[str, Any], int] | None,
    group: tuple[Mapping[str, Any], int] | None,
    context: _Context,
    within: Path | None = None,
) -> str | None:
    """`group.name` where the walk reads both as one string each, on every path (within
    `within`, where given); a key with no group is in the default group (Quartz's `Key`,
    CP-55 rows 10-18). NULL for no name, or a key read at runtime."""
    names = _keys_at(name, group, context, within)
    return names.pop() if len(names) == 1 else None


def _keys_at(
    name: tuple[Mapping[str, Any], int] | None,
    group: tuple[Mapping[str, Any], int] | None,
    context: _Context,
    within: Path | None = None,
) -> set[str]:
    """Each `group.name` the walk reads as one string each on some path (within `within`,
    where given): one where every path agrees, several where they differ, none for no name
    or a key read at runtime."""
    if name is None:
        return set()
    positions = {_NAME: name}
    if group is not None:
        positions[_GROUP] = group
    return {
        key
        for answers in resolve_positions(context.workspace, positions, context.index, within=within)
        if (key := _key_of(answers, context)) is not None
    }


def _key_of(answers: Mapping[str, Answer], context: _Context) -> str | None:
    """`group.name` on one path, where it reads both as one string each; a name with no
    group is in the default group. NULL for no name, or a key read at runtime."""
    if _NAME not in answers:
        return None
    name = _constant(answers[_NAME])
    group = _constant(answers[_GROUP]) if _GROUP in answers else context.default_group
    return None if name is None or group is None else f"{group}.{name}"


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


def _schedules(captures: Mapping[str, Any], context: _Context) -> list[_Schedule]:
    """Each distinct schedule the walk finds handed to the trigger, in its order; the
    catalog's `default_schedule` where none is (Quartz's own `build()`, CP-55).

    The builder chain is read by the value walk ALONG RECEIVERS (`producer_paths`), each
    with the path it took: every call
    on a `kinds` type that built the value, root first, across returns and helpers and in
    the path's own calling contexts — a helper's parameter is the argument at the call the
    walk came through, never another caller's."""
    if _SCHEDULE not in captures:
        return [context.default_schedule]
    position = _position(captures.get(_SCHEDULE), context)
    if position is None:
        return []
    site, slot = position
    declared_kind = _declared_kind(site, slot, context)
    found: list[_Schedule] = []
    chains = [
        (producer, path)
        for producer, path in producer_paths(
            context.index, site, slot, context.builder_calls, along_receivers=True
        )
        if producer.chain
    ]
    for producer, path in chains:
        sites = [context.index.sites[key] for key in producer.chain]
        if not producer.rooted:
            # A builder call was found and its root was not: the kind is the builder call's
            # own type, which is a `kinds` key by construction of the stop set.
            found.append(_Schedule(context.kinds.get(str(sites[0]["owner"])), path=path))
            continue
        kind = context.kinds[str(sites[0]["owner"])]
        if _is_literal_root(sites[0], context):
            found.append(replace(_literal(sites[0], kind, context), path=path))
            continue
        # A chain passed through a branch is not the chain as written: which step ran is not
        # known, so it has no text.
        text = None if producer.inexact else _text(sites, context)
        found.append(
            _Schedule(kind, text, _RESOLVED, path=path)
            if text is not None
            else _Schedule(kind, path=path)
        )
    if not chains:
        # The walk ends before any builder call (§3b): a factory in a jar, a helper whose body
        # it cannot read. The kind is still the type the producing call is declared to return.
        found.append(_Schedule(declared_kind))
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


def _literal(root: Mapping[str, Any], kind: str, context: _Context) -> _Schedule:
    """The `literal_expression` root's schedule: the field ladder's `${…}` for a configured
    field or parameter, which no path changes; else its argument, read on each path with
    the trigger's key and job (`_on_paths`, `_expression`). Steps after the root are not
    part of the expression, as they are not for `@Scheduled` (§3b)."""
    slot = int(context.literal["arg"])
    arguments = root["arguments"] or []
    argument = arguments[slot] if slot < len(arguments) else None
    caller = str(root["caller"])
    configured = field_expression(
        argument, context.field_sources, _call_facts(caller, context), caller
    )
    if configured is not None:
        return _Schedule(kind, configured, _resolution_of(configured, False, context))
    return _Schedule(kind, literal=_site_key(root))


def _expression(
    answer: Answer | None, root: Mapping[str, Any], slot: int, context: _Context
) -> tuple[str | None, str, str | None]:
    """`(expression, resolution, expression_source)` for one path's answer for the literal
    root's argument: a string verbatim, a `${…}` verbatim, else read at runtime (ruling 2) —
    the entry stays, naming where the walk stopped."""
    if (
        answer is not None
        and answer.kind == LITERAL
        and answer.literal_kind == STRING
        and not answer.inexact
    ):
        return str(answer.value), _resolution_of(str(answer.value), answer.narrowed, context), None
    if (
        answer is not None
        and answer.kind == EXPRESSION
        and context.opener in str(answer.value)
        and not answer.inexact
    ):
        return str(answer.value), _UNRESOLVED, None
    return None, _PARTIAL, _source(root, slot, context)


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
        for site in _reading_calls(root, slot, context, frozenset())
    }
    return called.pop() if len(called) == 1 else None


def _reading_calls(
    site: Mapping[str, Any],
    slot: int | str,
    context: _Context,
    seen: frozenset[tuple[str, int]],
) -> list[Mapping[str, Any]]:
    """The calls the walk from `site`'s `slot` stops at, each read back past a call made ON
    the value: one that takes nothing and hands back its own receiver's type
    (`getCron().trim()`) does not say where the value came from, so the call that produced
    its receiver is named instead."""
    found: list[Mapping[str, Any]] = []
    for producer in producers_of(context.index, site, slot, context.every_call):
        if producer.caller is None or producer.ordinal is None:
            continue
        key = (producer.caller, producer.ordinal)
        call = context.index.sites.get(key)
        if call is None or key in seen:
            continue
        if not (call["arguments"] or []) and returned_type(
            str(call.get("descriptor") or "()")
        ) == str(call["owner"]):
            found.extend(_reading_calls(call, RECEIVER, context, seen | {key}))
            continue
        found.append(call)
    return found


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


def _validated(catalog: Catalog) -> tuple[dict[str, str], dict[str, Any], str, _Schedule]:
    """`kinds`, `literal_expression`, `default_group` and `default_schedule`, refused when
    malformed — each
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
    default = matches.get(_DEFAULT_SCHEDULE)
    default_owners = (
        catalog_symbols(default.get("owner"), f"{catalog.source}: {_DEFAULT_SCHEDULE}.owner")
        if isinstance(default, dict)
        else ()
    )
    if not (
        isinstance(default, dict)
        and isinstance(default.get("method"), str)
        and len(default_owners) == 1
        and default_owners[0] in owned
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_DEFAULT_SCHEDULE}` must be `{{owner, "
            f"method}}`, the static factory the framework builds a trigger's schedule with "
            f"where none is handed to it, its owner one of `{_KINDS}`, got {default!r} (D02 "
            f"§2's `scheduled_chain` style)"
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
        # Written as the chain it stands for, a root with no argument (ruling 4).
        _Schedule(owned[default_owners[0]], f"{default['method']}()", _RESOLVED),
    )


def _job_rules(catalog: Catalog) -> _JobRules:
    """The job keys (spec §3c), refused when malformed, on the same terms as `_validated`:
    each decides which job a published row names, where a typo would read as an
    observation. The `for_job` and `job_identity_step` entries are chain-walk steps, checked
    by the walk itself (`chain_ends`)."""
    matches = catalog.matches
    where = f"loading catalog {catalog.source}"
    root = matches.get(_JOB_ROOT)
    if not (
        isinstance(root, dict)
        and isinstance(root.get("owner"), str | list)
        and isinstance(root.get("method"), str)
        and _slot(root.get("class_arg")) is not None
    ):
        raise CatalogError(
            f"{where}: `{_JOB_ROOT}` must be `{{owner, method, class_arg: argN}}`, got "
            f"{root!r} (D02 §2's `scheduled_chain` style)"
        )
    identity = matches.get(_JOB_IDENTITY_STEP)
    for_job = matches.get(_FOR_JOB)
    if not isinstance(identity, dict) or not (
        isinstance(for_job, list) and all(isinstance(step, dict) for step in for_job)
    ):
        raise CatalogError(
            f"{where}: `{_JOB_IDENTITY_STEP}` must be one chain step and `{_FOR_JOB}` a list "
            f"of them, got {identity!r} and {for_job!r} (D02 §2's `scheduled_chain` style)"
        )
    return _JobRules(
        root={"owner": root["owner"], "method": root["method"]},
        class_arg=int(str(_slot(root["class_arg"]))),
        identity_step=identity,
        for_job=tuple(for_job),
        key_builders=tuple(_key_builder(entry, where) for entry in _list(matches, _JOB_KEY, where)),
        pairing=tuple(_pairing(entry, where) for entry in _list(matches, _PAIRING, where)),
        entry=_method(matches.get(_ENTRY_METHOD), f"{where}: `{_ENTRY_METHOD}`"),
        templates={
            type_descriptor(str(entry["supertype"])): _method(
                entry.get("calls"), f"{where}: `{_SUPERTYPE_DISPATCH}[].calls`"
            )
            for entry in _list(matches, _SUPERTYPE_DISPATCH, where)
            if _named_type(entry.get("supertype"), f"{where}: `{_SUPERTYPE_DISPATCH}`")
        },
    )


def _names(declared: Any) -> list[Any]:
    """A catalog site naming one value or a list of them (§3.1), as a list."""
    return declared if isinstance(declared, list) else [declared]


def _slot(value: Any) -> int | None:
    """`argN`'s N, or None for anything else."""
    match = _ARG.match(value) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def _list(matches: Mapping[str, Any], key: str, where: str) -> list[dict[str, Any]]:
    entries = matches.get(key)
    if not (isinstance(entries, list) and entries and all(isinstance(e, dict) for e in entries)):
        raise CatalogError(
            f"{where}: `{key}` must be a non-empty list of mappings, got {entries!r} (D02 §2's "
            f"`scheduled_chain` style)"
        )
    return entries


def _named_type(value: Any, where: str) -> bool:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{where}: `supertype` must be one dotted type name, got {value!r}")
    return True


def _method(declared: Any, where: str) -> _Method:
    """`{name, parameters, returns}` — `jakarta-servlet.yml`'s `{name, parameters}` method
    selector, with the return type the JVM's resolution also matches on — as the name and
    JVM descriptor `dispatch.py` resolves."""
    if not (
        isinstance(declared, dict)
        and isinstance(declared.get("name"), str)
        and isinstance(declared.get("parameters"), list)
        and all(isinstance(parameter, str) for parameter in declared["parameters"])
        and isinstance(declared.get("returns"), str)
    ):
        raise CatalogError(
            f"{where} must be `{{name, parameters: [dotted types], returns: dotted type}}`, "
            f"got {declared!r} (D02 §2's `scheduled_chain` style)"
        )
    return _Method(
        name=declared["name"],
        descriptor=method_type_descriptor(declared["parameters"], declared["returns"]),
    )


def _pairing(entry: dict[str, Any], where: str) -> _Pairing:
    job, trigger = _slot(entry.get("job")), _slot(entry.get("trigger"))
    if not (
        isinstance(entry.get("method"), str)
        and isinstance(entry.get("descriptor"), str)
        and job is not None
        and trigger is not None
    ):
        raise CatalogError(
            f"{where}: a `{_PAIRING}` entry must be `{{owner, method, descriptor, job: argN, "
            f"trigger: argN}}`, got {entry!r} (D02 §2's `scheduled_chain` style)"
        )
    return _Pairing(
        owners=catalog_symbols(entry.get("owner"), f"{where}: {_PAIRING}[].owner"),
        method=entry["method"],
        descriptor=entry["descriptor"],
        job=job,
        trigger=trigger,
    )


def _key_builder(entry: dict[str, Any], where: str) -> _KeyBuilder:
    name = _slot(entry.get("name"))
    group = _slot(entry.get("group")) if "group" in entry else None
    if (
        not isinstance(entry.get("method"), str)
        or name is None
        or ("group" in entry and group is None)
    ):
        raise CatalogError(
            f"{where}: a `{_JOB_KEY}` entry must be `{{owner, method, name: argN, group?: "
            f"argN}}`, got {entry!r} (D02 §2's `scheduled_chain` style)"
        )
    return _KeyBuilder(
        owners=catalog_symbols(entry.get("owner"), f"{where}: {_JOB_KEY}[].owner"),
        method=entry["method"],
        name=name,
        group=group,
    )
