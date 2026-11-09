"""Receiver binding (spec 2026-11-06 §3b): the owner of a call one file cannot know.

A Python call on a value names its receiver's value id and the method name, and leaves the
owner out (D00 §5): the type of the value is decided in another file, by what produced it.
This pass follows the receiver back on the EXISTING value walk (`resolve/values.py`,
`producer_paths`) — a construction to its class, a call to its callee's returns
(`return_flows`, and `_Walk._bound_returns` for a callee bound here), a parameter to the
arguments at its callers, a field to its `field_write`s — and writes the type it reaches on
each path into `bound_receivers`. It never writes a fact: `call_edges` reads a site's owner
as the fact's where it names one and as these rows' where it does not, one edge per owner.

**Per path, never combined (ruling M-1).** A parameter whose callers pass a `Session` on one
path and a `Client` on another is two rows, each on its own path. Several types from a closed
set are `narrowed`; a path the walk ends without a type is a row of its own, with one reason
of the general list and a detail for a person, and the site's bound rows are then `partial`.
A receiver that is a parameter whose written type is a union is each member of the union, one
row each, `narrowed` (carried item (c)): the written type is the closed list.

**A `__call__` on a function value runs that function** (ruling R29): the walk asks what a
call of the value runs (`producer_paths(..., functions=True)`), and a path that ends at a
function value (`lambda`) names its body, as a JVM functional interface's method on a lambda
reaches the lambda's body. No owner is written for it: the path is an edge to that body
(`call_edges`), per path, beside the owners other paths bound, and it counts toward the
site's tier as one more thing the call may run.

**Which callers count** is the walk's rule: a call in the scanned code whose edge `call_edges`
holds. No caller is `external`. A function the module hands on as a value (a `lambda`
argument, or a name of it read as a module field) is called by whoever received it, so a
receiver that is its parameter is `escapes`, and so is one more path of a receiver whose path
crossed out of such a function: its other callers are not in the module.

**Rounds.** A call bound here becomes an edge, and an edge is a caller: `r.run(s)` is an edge
only once `r` is bound, and `Runner.run`'s parameter has a caller only then. So binding runs
in rounds until one binds no new owner (`bind_until_settled`), at most `ROUNDS`. After the
first round only a site whose walk depended on a new caller is walked again (R25): one whose
paths crossed out of, or ended at a parameter of, a method a newly bound call reaches. The new
callers are added to the walk's index directly, from the same dispatch answer `call_edges`
draws, so the edges are drawn once, after the last round. Where the last round still bound
something, every receiver it left unbound says so: it may be bound by a round not run.
"""

import logging
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.call_edges import FunctionCalls, record_call_edges
from sextant.application.resolve.values import (
    ABSENT,
    ESCAPES,
    EXTERNAL,
    NOT_READABLE,
    RECEIVER,
    Producer,
    ValueIndex,
    bind_by_name,
    bound_owner,
    called_function,
    producer_paths,
    reset_value_index,
    value_index,
)
from sextant.domain.closed_sets import Evidence, Resolution
from sextant.domain.symbols import (
    ANY_TYPE,
    UNION_TYPE,
    bare_descriptor,
    is_type_descriptor,
    member_name,
    method_descriptor,
    method_name,
    owner_of,
)

_log = logging.getLogger(__name__)

# The spec's bound on rounds (§5: "its pass count is bounded by the depth of producer
# chains"); the brief's eight.
ROUNDS = 8
_VIRTUAL = "virtual"
_CALL = "__call__"
# The calls the scanner writes for syntax (`xs[i]`, `for x in xs`), which Python looks up on
# the value's type: on a class object that is the metaclass, or `__class_getitem__` for a
# subscript, never the class body's own method (ruling R37).
_PROTOCOL = frozenset({"__getitem__", "__iter__", "__next__", "__aiter__", "__anext__"})
_SYNTAX = _PROTOCOL | {_CALL}
# The receiver reader's key in the index's shared upward paths (`ValueIndex.suffixes`, R39):
# every site's walk over one round's index reads them.
_RECEIVER_READER = "receiver"

# What a path's crossings are joined by in `path_id`, outermost first.
_JOIN = " > "

# One path's end: (path_id, owner, reason, detail), owner None exactly where reason is set,
# and the end's evidence where it is not the walk's own (`declared`, OI-324 part 2).
_Found = (
    tuple[str, str | None, str | None, str | None]
    | tuple[str, str | None, str | None, str | None, Evidence]
)
# A written union a parameter carries: its member types, and whether `None` is one.
_Union = tuple[tuple[str, ...], bool]


@dataclass(frozen=True)
class _Walked:
    """One site's walk: its ends, and the methods whose callers it read — a path crossed out
    of one, or ended at one of its parameters. None where that is not known (a path the walk
    could not hold), and the site is walked again every round. `functions` are the bodies,
    bare, of the function values a `__call__`'s paths ended at (ruling R29), in path order."""

    found: tuple[_Found, ...]
    depends_on: frozenset[str] | None
    functions: tuple[str, ...] = ()

    @property
    def owners(self) -> frozenset[str]:
        return frozenset(owner for _, owner, *_ in self.found if owner is not None)

    @property
    def reached(self) -> frozenset[str]:
        """What a round counts as newly bound: each owner, and each function body."""
        return self.owners | frozenset(_FUNCTION_MARK + body for body in self.functions)


# What marks a function body among a site's owners when rounds compare what they bound.
_FUNCTION_MARK = "function:"


def bind_receivers(workspace: Workspace) -> int:
    """One round: `bound_receivers` rewritten whole from the walk over the edges
    `call_edges` holds now. Returns how many call sites gained an owner they did not have
    before this round."""
    before: dict[tuple[str, int], set[str]] = {}
    for row in workspace.query("bound_receivers"):
        if row["owner"] is not None:
            key = (str(row["caller"]), int(str(row["ordinal"])))
            before.setdefault(key, set()).add(str(row["owner"]))
    index = value_index(workspace)
    walked = _walk(index, _context(workspace, index), None, {})
    _write(workspace, index, walked, capped=False)
    return sum(1 for key, one in walked.items() if one.owners - before.get(key, set()))


def bind_until_settled(
    workspace: Workspace, catalogs: Sequence[Catalog] = (), *, incremental: bool = True
) -> tuple[int, ...]:
    """The rounds (the module docstring), at most `ROUNDS`. `call_edges` must already hold
    the edges of every call the facts give an owner. Returns each round's count of sites
    that gained an owner; each round's count and time are logged at INFO, as a pipeline pass
    is (`pipeline._timed`). `incremental` False walks every site each round over an index
    rebuilt from `call_edges` redrawn after every round — the reference the R25 rule is
    proved against; the table it leaves is the same."""
    if not incremental:
        return _every_round_whole(workspace, catalogs)
    started = time.perf_counter()
    index = value_index(
        workspace, returns_arguments=_returns_arguments(catalogs), **_beans(catalogs)
    )
    context = _context(workspace, index)
    walked: dict[tuple[str, int], _Walked] = {}
    gained: frozenset[str] | None = None
    counts: list[int] = []
    capped = False
    for round_number in range(1, ROUNDS + 1):
        before = {key: one.reached for key, one in walked.items()}
        walked.update(_walk(index, context, gained, walked))
        newly = [key for key, one in walked.items() if one.reached - before.get(key, frozenset())]
        counts.append(len(newly))
        _log.info(
            "bind_receivers round %d  %d newly bound  %.2fs",
            round_number,
            len(newly),
            time.perf_counter() - started,
        )
        started = time.perf_counter()
        if not newly:
            break
        if round_number == ROUNDS:
            capped = True
            break
        index, gained = _with_new_callers(index, newly, before, walked)
    _write(workspace, index, walked, capped)
    if any(counts):
        started = time.perf_counter()
        record_call_edges(workspace, catalogs, _functions(walked))
        _log.info("record_call_edges after binding  %.1fs", time.perf_counter() - started)
    # Every index a later pass asks for is built from the edges as they now stand.
    reset_value_index()
    return tuple(counts)


def _every_round_whole(workspace: Workspace, catalogs: Sequence[Catalog]) -> tuple[int, ...]:
    counts: list[int] = []
    walked: dict[tuple[str, int], _Walked] = {}
    for round_number in range(1, ROUNDS + 1):
        started = time.perf_counter()
        before = {key: one.reached for key, one in walked.items()}
        index = value_index(
            workspace, returns_arguments=_returns_arguments(catalogs), **_beans(catalogs)
        )
        walked = _walk(index, _context(workspace, index), None, {})
        newly = sum(1 for key, one in walked.items() if one.reached - before.get(key, frozenset()))
        counts.append(newly)
        _write(workspace, index, walked, capped=round_number == ROUNDS and newly > 0)
        _log.info(
            "bind_receivers round %d  %d newly bound  %.1fs (whole)",
            round_number,
            newly,
            time.perf_counter() - started,
        )
        if newly == 0:
            break
        record_call_edges(workspace, catalogs, _functions(walked))
    reset_value_index()
    return tuple(counts)


def _returns_arguments(catalogs: Sequence[Catalog]) -> tuple[dict[str, Any], ...]:
    """The library calls the value models state hand back an argument (`Catalog
    .returns_arguments`, the same on every catalog): a call of a wrapper one of them made runs
    the function it wraps (design 2026-11-06-reading-decorators §3e)."""
    return catalogs[0].returns_arguments if catalogs else ()


def _beans(catalogs: Sequence[Catalog]) -> dict[str, Any]:
    """The bean models and value annotations every catalog carries (`Catalog.bean_models`,
    `Catalog.value_annotations`): a parameter a framework fills is read as it fills it, a
    recipe a marker call names beside the callers (plan 2026-11-08 N5), as every other reader
    of the index reads it. None and empty with no catalog."""
    if not catalogs:
        return {}
    return {
        "bean_models": catalogs[0].bean_models,
        "value_annotations": catalogs[0].value_annotations,
    }


def _functions(walked: Mapping[tuple[str, int], _Walked]) -> dict[tuple[str, int], FunctionCalls]:
    """Each site a path of which ended at a function value: its bodies, and its tier."""
    return {
        key: FunctionCalls(one.functions, _tier(one))
        for key, one in walked.items()
        if one.functions
    }


@dataclass(frozen=True)
class _Context:
    """What every round reads and no round changes: the functions handed on as values, and
    each parameter's written union."""

    handed_on: frozenset[tuple[str, str]]
    unions: Mapping[tuple[str, int], _Union]
    # The methods, bare, that some call site in the module names, and those with no normal
    # return (`ValueIndex.never_return`): a parameter of one is called, though no edge may
    # reach it.
    named: frozenset[str] = frozenset()
    never_return: frozenset[str] = frozenset()


def _context(workspace: Workspace, index: ValueIndex) -> _Context:
    open_types = {ANY_TYPE} | ({index.dispatch.root} if index.dispatch is not None else set())
    return _Context(
        frozenset(_handed_on_as_values(index)),
        _declared_unions(workspace, frozenset(open_types)),
        frozenset(
            method_descriptor(str(site["owner"]), str(site["name"]), str(site["descriptor"]))
            for site in index.sites.values()
            if site.get("owner") is not None and site.get("name") is not None
        ),
        index.never_return,
    )


def _walk(
    index: ValueIndex,
    context: _Context,
    gained: frozenset[str] | None,
    previous: Mapping[tuple[str, int], _Walked],
) -> dict[tuple[str, int], _Walked]:
    """Every call the facts leave without an owner, walked — or, with `gained` set, only
    those whose previous walk read the callers of a method in it, or is not known not to."""
    walked: dict[tuple[str, int], _Walked] = {}
    for key, site in index.sites.items():
        wrapper = _calls_a_library_wrapper(index, key, site)
        if not wrapper and (site.get("owner") is not None or site.get("invoke_kind") != _VIRTUAL):
            continue
        if gained is not None:
            depends_on = previous[key].depends_on
            if depends_on is not None and not depends_on & gained:
                continue
        walked[key] = _wrapped(index, site) if wrapper else _paths(index, site, context)
    return walked


def _calls_a_library_wrapper(
    index: ValueIndex, key: tuple[str, int], site: Mapping[str, Any]
) -> bool:
    """Whether `site` calls a value whose type the facts name and whose `__call__` no body
    here has: a library type's, such as `functools.cache`'s `_lru_cache_wrapper` or a
    parameter written `Callable[...]`. Calling a function value runs it (ruling R29), and a
    value model may state that calling a wrapper runs the function it wraps (`result_calls`,
    design 2026-11-06-reading-decorators §3e), so the call is walked for the functions its
    receiver is, and only for them: its owner is already known."""
    return (
        site.get("name") == _CALL and site.get("owner") is not None and not index.callees.get(key)
    )


def _wrapped(index: ValueIndex, site: Mapping[str, Any]) -> _Walked:
    """The function bodies a call of a library-typed value runs (`_calls_a_library_wrapper`):
    the ends of its receiver's paths that name a function — a function passed in, or the one a
    `result_calls` wrapper runs. No path names an owner here, so the site keeps the one its
    facts name and gets no `bound_receivers` row."""
    functions: list[str] = []
    depends_on: set[str] = set()
    for producer, path in producer_paths(
        index, site, RECEIVER, frozenset(), which_object=True, functions=True
    ):
        depends_on.update(path.crossed_out_of())
        body = None if producer.ended_at is None else called_function(producer.ended_at)
        if body is not None and body not in functions:
            functions.append(body)
    return _Walked((), frozenset(depends_on), tuple(functions))


def _with_new_callers(
    index: ValueIndex,
    newly: Sequence[tuple[str, int]],
    before: Mapping[tuple[str, int], frozenset[str]],
    walked: Mapping[tuple[str, int], _Walked],
) -> tuple[ValueIndex, frozenset[str]]:
    """`index` as `value_index` would build it once `call_edges` held the edges of every
    owner `newly` gained, and the methods those edges reach: each new owner's bodies, by the
    dispatch answer `call_edges` draws them with, as callers of their parameters and as the
    bodies the site reaches."""
    dispatch = index.dispatch
    assert dispatch is not None
    edges: list[dict[str, object]] = []
    callees = {key: list(value) for key, value in index.callees.items()}
    for key in newly:
        site = index.sites[key]
        gained_here = walked[key].reached - before.get(key, frozenset())
        bodies = [
            callee
            for mark in sorted(gained_here)
            if mark.startswith(_FUNCTION_MARK)
            for callee in dispatch.bodies.get(mark[len(_FUNCTION_MARK) :], ())
        ]
        for callee in bodies:
            if callee not in callees.get(key, ()):
                callees.setdefault(key, []).append(callee)
                edges.append(
                    {
                        "caller": key[0],
                        "ordinal": key[1],
                        "callee": callee,
                        "invoke_kind": site["invoke_kind"],
                    }
                )
        for owner in sorted(walked[key].owners - before.get(key, frozenset())):
            for callee in dispatch.candidates({**site, "owner": owner}):
                if callee in callees.get(key, ()):
                    continue
                callees.setdefault(key, []).append(callee)
                edges.append(
                    {
                        "caller": key[0],
                        "ordinal": key[1],
                        "callee": callee,
                        "invoke_kind": site["invoke_kind"],
                    }
                )
    callers = {key: list(value) for key, value in index.callers.items()}
    if index.by_name:
        bind_by_name(
            callers,
            edges,
            index.sites,
            index.call_parameters,
            index.instance_methods,
            index.class_receivers,
        )
    else:
        for edge in edges:
            arguments = index.sites[(str(edge["caller"]), int(str(edge["ordinal"])))]["arguments"]
            for slot in range(len(arguments or [])):
                callers.setdefault((str(edge["callee"]), slot), []).append(
                    (str(edge["caller"]), int(str(edge["ordinal"])), slot)
                )
    writing = (
        {method for entries in index.writers.values() for method, _ in entries}
        | {str(writer) for entries in index.constants.values() for writer, _ in entries if writer}
        | {writer for entries in index.produced.values() for writer, _ in entries}
    )
    called_at = {key: list(value) for key, value in index.called_at.items()}
    for edge in edges:
        if edge["callee"] in writing:
            called_at.setdefault(str(edge["callee"]), []).append(
                (str(edge["caller"]), int(str(edge["ordinal"])))
            )
    patched = replace(
        index,
        callers={key: tuple(value) for key, value in callers.items()},
        callees={key: tuple(value) for key, value in callees.items()},
        called_at={key: tuple(value) for key, value in called_at.items()},
        reached=index.reached | {(str(e["caller"]), int(str(e["ordinal"]))) for e in edges},
        objects={},
        slots_memo={},
        suffixes={},
        markers=[],
        recipes_read={},
    )
    return patched, frozenset(str(edge["callee"]) for edge in edges)


def _write(
    workspace: Workspace,
    index: ValueIndex,
    walked: Mapping[tuple[str, int], _Walked],
    capped: bool,
) -> None:
    """`bound_receivers`, whole. `capped`: the last round still bound something, so a round
    not run might bind what it left, and no reason the walk gave a path is known to hold."""
    rows: list[dict[str, object]] = []
    for (caller, ordinal), one in sorted(walked.items()):
        found = list(one.found)
        if capped:
            name = str(index.sites[(caller, ordinal)]["name"])
            found = [
                end
                if end[1] is not None
                else (
                    end[0],
                    None,
                    NOT_READABLE,
                    f"receiver of {name} not followed after {ROUNDS} rounds",
                )
                for end in found
            ]
        rows.extend(_rows(caller, ordinal, list(dict.fromkeys(found)), one.functions))
    workspace.derive("bound_receivers_reset")
    if rows:
        workspace.derive("bound_receivers_insert", rows=rows)


def _paths(index: ValueIndex, site: Mapping[str, Any], context: _Context) -> _Walked:
    """Every path the walk reaches `site`'s receiver by, as the type it is there or the
    reason it is none — `which_object`, since what is done to an object never makes it an
    object of another type — and the methods whose callers those paths read."""
    name = str(site["name"])
    parameter = site.get("receiver_parameter")
    if parameter is not None and site.get("receiver_field") is None:
        union = context.unions.get((str(site["caller"]), int(str(parameter))))
        if union is not None:
            return _Walked(_members(name, union), frozenset())
    found: list[_Found] = []
    depends_on: set[str] = set()
    dropped: list[Producer] = []
    handed_on = context.handed_on
    functions: list[str] = []
    for producer, path in producer_paths(
        index,
        site,
        RECEIVER,
        frozenset(),
        which_object=True,
        dropped=dropped,
        functions=True,
        declared_types=True,
        shared=_RECEIVER_READER,
    ):
        path_id = _JOIN.join(path.labels())
        crossed = path.crossed_out_of()
        depends_on.update(crossed)
        if producer.parameter is not None:
            depends_on.add(producer.parameter[0])
        ended = producer.ended_at
        owner = None if ended is None else bound_owner(ended)
        body = None if ended is None or name != _CALL else called_function(ended)
        if owner is not None and name == _CALL and ended is not None and ended.class_object:
            # Calling a class constructs it (ruling R37): the call runs the class's
            # constructor, found by its lookup order, never the instance's `__call__`.
            built = _constructors(index, site, owner)
            if built:
                functions.extend(body for body in built if body not in functions)
            else:
                found.append(
                    (
                        path_id,
                        None,
                        NOT_READABLE,
                        (
                            f"receiver of {name} is the class {bare_descriptor(owner)} itself: "
                            "calling it constructs it, and no constructor of it was read"
                        ),
                    )
                )
        elif owner is not None and ended is not None and ended.declared and name in _SYNTAX:
            # A declared type does not say whether the value is the class or an instance of
            # it (the facts write `type[X]` as `X`), and a call syntax makes differs between
            # the two (ruling R37): not followed on a declaration alone.
            found.append(
                (
                    path_id,
                    None,
                    NOT_READABLE,
                    (
                        f"receiver of {name} is declared {bare_descriptor(owner)}, which does "
                        "not say whether it is the class or an instance of it"
                    ),
                )
            )
        elif owner is not None and name in _PROTOCOL and ended is not None and ended.class_object:
            found.append(
                (
                    path_id,
                    None,
                    NOT_READABLE,
                    _class_object_detail(name, bare_descriptor(owner)),
                )
            )
        elif owner is not None:
            if ended is not None and ended.declared:
                found.append((path_id, owner, None, None, Evidence.DECLARED))
            else:
                found.append((path_id, owner, None, None))
        elif body is not None:
            if body not in functions:
                functions.append(body)
        elif ended is not None and ended.kind == ABSENT:
            # The code states the value on this path: `None` (a default the call leaves, `=
            # None`, ruling R16, or a `None` written), which has no method to bind, or an
            # empty collection (`()`, `[]`), whose type the facts do not write.
            found.append(
                (
                    path_id,
                    None,
                    NOT_READABLE,
                    f"receiver of {name} is None on this path"
                    if ended.null
                    else f"receiver of {name} is an empty collection on this path, of a type "
                    "the facts do not write",
                )
            )
        else:
            found.append(
                (
                    path_id,
                    None,
                    *_reason(
                        name,
                        site.get("receiver_field"),
                        producer.reason,
                        producer.parameter,
                        context,
                        _library_call(index, name, producer.made_by),
                    ),
                )
            )
        # A path through a function handed on as a value has callers besides the ones it
        # crossed through or the call that left a parameter unfilled: that function's own,
        # which the module does not show. (One that ended at no caller says so itself.)
        through = list(crossed)
        if producer.parameter is not None and producer.reason != EXTERNAL:
            through.append(producer.parameter[0])
        for method in through:
            if _function(method) in handed_on:
                found.append(_escapes(name, method))
    if dropped:
        # `producer_paths` holds no path that enters one function through two of its calls
        # (`Path.two_calls_of_one_helper`'s bound), so the paths it returns may not be all of
        # them: the site is never a complete list while one is missing.
        found.append(
            (
                "",
                None,
                NOT_READABLE,
                (
                    f"receiver of {name} not followed on every path: a path to it enters one "
                    "function through two of its calls"
                ),
            )
        )
    return _Walked(
        tuple(dict.fromkeys(found)), None if dropped else frozenset(depends_on), tuple(functions)
    )


def _members(name: str, union: _Union) -> tuple[_Found, ...]:
    """A written union's members, one row each (carried item (c)); a `None` member has no
    method, which the detail says."""
    members, nullable = union
    written = " | ".join(members) + (" | None" if nullable else "")
    detail = f"receiver of {name} is declared {written}" + (
        f"; None has no {name}, so it is left out" if nullable else ""
    )
    return tuple(("", member, None, detail) for member in members)


def _declared_unions(
    workspace: Workspace, open_types: frozenset[str]
) -> dict[tuple[str, int], _Union]:
    """Each parameter whose written type is a union of two or more types, every one a type
    and none of `open_types` — the unknown type, or the root type every value is — either of
    which makes the list open, by (method, index)."""
    found: dict[tuple[str, int], _Union] = {}
    for row in workspace.query("method_declarations"):
        signature = row.get("signature")
        if not isinstance(signature, Mapping):
            continue
        for position, declared in enumerate(signature.get("parameters") or []):
            written = declared.get("type") if isinstance(declared, Mapping) else None
            if not isinstance(written, Mapping) or written.get("symbol") != UNION_TYPE:
                continue
            members = tuple(str(member.get("symbol")) for member in written.get("arguments") or [])
            if len(members) > 1 and all(
                is_type_descriptor(member) and member not in open_types for member in members
            ):
                found[(str(row["symbol"]), position)] = (members, bool(written.get("nullable")))
    return found


def _constructors(index: ValueIndex, site: Mapping[str, Any], owner: str) -> list[str]:
    """The constructor bodies a call of the class `owner` runs: its `<init>` by lookup
    order, as a construction of it is dispatched."""
    dispatch = index.dispatch
    if dispatch is None:
        return []
    construction = {**site, "owner": owner, "name": "<init>", "invoke_kind": "special"}
    return [bare_descriptor(callee) for callee in dispatch.candidates(construction)]


def _class_object_detail(name: str, owner: str) -> str:
    """Why a call syntax makes on a class object binds no method of the class (ruling R37):
    a subscript of a class makes a type; iterating a class runs its metaclass's method."""
    if name == "__getitem__":
        return (
            f"receiver of {name} is the class {owner} itself: a subscript of a class is a "
            "type form (`__class_getitem__`), and the class's own method runs only on an "
            "instance"
        )
    return (
        f"receiver of {name} is the class {owner} itself: iterating a class runs its "
        "metaclass's method, which is not read, not the class's own"
    )


def _reason(
    name: str,
    field: object,
    reason: str | None,
    parameter: tuple[str, int] | None,
    context: _Context,
    made_by: str | None = None,
) -> tuple[str, str]:
    """The reason and the detail of a path that reached no type. `field` is the field the
    receiver is read from, where it is one, for the detail. A parameter no edge binds is
    `external` only where no call in the module names its method: a method that never
    returns normally has no body the edges reach, so a call of it binds nothing, and that is
    the code we have, not followed (`not_readable`)."""
    if reason == EXTERNAL and parameter is not None:
        method, position = parameter
        shown = bare_descriptor(method)
        if shown in context.never_return:
            return (
                NOT_READABLE,
                (
                    f"receiver of {name} is parameter {position} of {shown}, which never "
                    "returns normally, so no call of it reaches its body"
                ),
            )
        if shown in context.named:
            return (
                NOT_READABLE,
                (
                    f"receiver of {name} is parameter {position} of {shown}, which a call in "
                    "the module names, but no edge reaches its body"
                ),
            )
        if _function(method) in context.handed_on:
            return (
                ESCAPES,
                (
                    f"receiver of {name} is parameter {position} of {shown}, "
                    "which the module hands on as a value"
                ),
            )
        return (
            EXTERNAL,
            (
                f"receiver of {name} is parameter {position} of {shown}, "
                "which nothing in the scanned code calls"
            ),
        )
    if reason == EXTERNAL and made_by is not None:
        return (
            EXTERNAL,
            (
                f"receiver of {name} is what the library call {made_by} returns, which no "
                "value model states"
            ),
        )
    if reason == EXTERNAL:
        return EXTERNAL, f"receiver of {name} comes from code outside the scanned module"
    if reason == NOT_READABLE and parameter is not None:
        method, position = parameter
        return (
            NOT_READABLE,
            (
                f"receiver of {name} is parameter {position} of {bare_descriptor(method)}, "
                "which a call fills with no argument that can be named (a default, a ** "
                "mapping, or a place the facts do not decide)"
            ),
        )
    if reason is not None:
        read = "" if field is None else f" reading {field}"
        return reason, f"receiver of {name} not followed{read}: the walk ended at {reason}"
    return NOT_READABLE, f"receiver of {name} is a value of no type the scanned code declares"


def _library_call(index: ValueIndex, name: str, made_by: tuple[str, int] | None) -> str | None:
    """The library call a `__call__`'s receiver path ended at, as `owner#name` (a decorator
    such as `click/decorators#pass_context`), for the detail; None for any other call, whose
    detail is as before."""
    row = None if made_by is None or name != _CALL else index.sites.get(made_by)
    if row is None or row.get("owner") is None:
        return None
    return f"{row['owner']}{row['name']}"


def _escapes(name: str, method: str) -> _Found:
    return (
        f"{method}@value",
        None,
        ESCAPES,
        (
            f"receiver of {name} may also come from callers of {bare_descriptor(method)}, "
            "which the module hands on as a value"
        ),
    )


def _rows(
    caller: str, ordinal: int, found: list[_Found], functions: tuple[str, ...] = ()
) -> list[dict[str, object]]:
    """A site's rows, with the site's own resolution on each (D01's rule: the tier
    describes the site): `resolved` for one type on every path, `narrowed` for several, and
    `partial` where some path reached none. A path that ended at a function value has no
    row (it binds no owner) and counts as one more thing the call may run."""
    bound_tier = _tier(_Walked(tuple(found), None, functions))
    return [
        {
            "caller": caller,
            "ordinal": ordinal,
            "path_id": end[0],
            "owner": end[1],
            "evidence": str(end[4] if len(end) > 4 else Evidence.SYNTAX),
            "resolution": str(bound_tier if end[1] is not None else Resolution.UNRESOLVED),
            "reason": end[2],
            "detail": end[3],
        }
        for end in found
    ]


def _tier(walked: _Walked) -> Resolution:
    """The site's tier over every path: owners and function bodies alike."""
    if any(owner is None for _, owner, *_ in walked.found):
        return Resolution.PARTIAL
    if len(walked.owners) + len(walked.functions) > 1:
        return Resolution.NARROWED
    return Resolution.RESOLVED


def _function(method: str) -> tuple[str, str]:
    """A method as `(owner, name)`, the spelling a value naming it is matched in."""
    bare = bare_descriptor(method)
    return str(owner_of(bare)), method_name(bare)


def _handed_on_as_values(index: ValueIndex) -> set[tuple[str, str]]:
    """Every function the module hands on as a VALUE, as `(owner, name)`: a `lambda`
    entry's body, anywhere in an argument, a field write or a return; and a binding nothing
    writes and declares as no field whose name its owner declares a method of — a function a
    file imports from another and uses as a value, read as a field because the file cannot
    see that it is a function (spec 2026-11-06 §3b)."""
    dispatch = index.dispatch
    found: set[tuple[str, str]] = set()
    for method, entry in _entries(index):
        kind = entry.get("kind")
        symbol = entry.get("symbol")
        if symbol is None:
            continue
        if kind == "lambda":
            found.add(_function(str(symbol)))
        elif kind == "field" and dispatch is not None:
            bare = bare_descriptor(str(symbol))
            owner = owner_of(bare)
            if (
                owner is not None
                and bare not in dispatch.scanned
                and member_name(bare) in dispatch.declared_names.get(owner, ())
            ):
                found.add((owner, member_name(bare)))
    return found


def _entries(index: ValueIndex) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Every argument-grammar entry the index holds, nested ones too, with the method it is
    read in (a field write naming no method is read in none, `""`)."""
    for (method, _), site in index.sites.items():
        for argument in site.get("arguments") or []:
            yield from _nested(method, argument)
    for method, returns in index.returned_values.items():
        for _, entry in returns:
            yield from _nested(method, entry)
    for writes in index.constants.values():
        for writer, entry in writes:
            yield from _nested(writer or "", entry)


def _nested(method: str, entry: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    yield method, entry
    for key in ("elements", "candidates"):
        for inner in entry.get(key) or []:
            if isinstance(inner, Mapping):
                yield from _nested(method, inner)
