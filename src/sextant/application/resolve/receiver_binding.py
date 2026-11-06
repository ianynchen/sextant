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

**Which callers count** is the walk's rule: a call in the scanned code whose edge `call_edges`
holds. No caller is `external`. A function the module hands on as a value (a `lambda`
argument, or a name of it read as a module field) is called by whoever received it, so a
receiver that is its parameter is `escapes`, and so is one more path of a receiver whose path
crossed out of such a function: its other callers are not in the module.

**Rounds.** A call bound here becomes an edge, and an edge is a caller: `r.run(s)` is an edge
only once `r` is bound, and `Runner.run`'s parameter has a caller only then. So the pipeline
runs `record_call_edges`, then this, then `record_call_edges` again, until a round binds no
new owner (`bind_until_settled`), at most `ROUNDS` times. Where the last round still bound
something, every receiver it left unbound says so: it may be bound by a round not run.
"""

import logging
import time
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.values import (
    ESCAPES,
    EXTERNAL,
    NOT_READABLE,
    RECEIVER,
    ValueIndex,
    bound_owner,
    producer_paths,
    reset_value_index,
    value_index,
)
from sextant.domain.closed_sets import Evidence, Resolution
from sextant.domain.symbols import (
    bare_descriptor,
    member_name,
    method_name,
    owner_of,
)

_log = logging.getLogger(__name__)

# The spec's bound on rounds (§5: "its pass count is bounded by the depth of producer
# chains"); the brief's eight.
ROUNDS = 8
_VIRTUAL = "virtual"
# What a path's crossings are joined by in `path_id`, outermost first.
_JOIN = " > "


def bind_receivers(workspace: Workspace) -> int:
    """One round: `bound_receivers` rewritten whole from the walk over the edges
    `call_edges` holds now. Returns how many call sites gained an owner they did not have
    before this round."""
    return _bind(workspace, last=False)


def bind_until_settled(workspace: Workspace, catalogs: Sequence[Catalog] = ()) -> tuple[int, ...]:
    """The rounds (the module docstring): bind, then re-derive `call_edges` from what was
    bound, until a round binds nothing new, at most `ROUNDS` binds. `call_edges` must already
    hold the first round's edges. Returns each round's count, in order; each round's count,
    rows and time are logged at INFO, as a pipeline pass is (`pipeline._timed`)."""
    counts: list[int] = []
    for round_number in range(1, ROUNDS + 1):
        started = time.perf_counter()
        bound = _bind(workspace, last=round_number == ROUNDS)
        counts.append(bound)
        _log.info(
            "bind_receivers round %d  %d newly bound  %.1fs",
            round_number,
            bound,
            time.perf_counter() - started,
        )
        if bound == 0:
            break
        started = time.perf_counter()
        record_call_edges(workspace, catalogs)
        _log.info("record_call_edges round %d  %.1fs", round_number, time.perf_counter() - started)
    # Every index a later pass asks for is built from the edges as they now stand.
    reset_value_index()
    return tuple(counts)


def _bind(workspace: Workspace, last: bool) -> int:
    before: dict[tuple[str, int], set[str]] = {}
    for row in workspace.query("bound_receivers"):
        if row["owner"] is not None:
            key = (str(row["caller"]), int(str(row["ordinal"])))
            before.setdefault(key, set()).add(str(row["owner"]))
    # Built fresh, never the per-resolve cache: the edges it reads changed since the last
    # round, and a caller is an edge.
    index = value_index(workspace)
    handed_on = _handed_on_as_values(index)
    sites: list[tuple[str, int, str, list[_Found]]] = []
    newly = 0
    for (caller, ordinal), site in index.sites.items():
        if site.get("owner") is not None or site.get("invoke_kind") != _VIRTUAL:
            continue
        found = _paths(index, site, handed_on)
        owners = {owner for _, owner, _, _ in found if owner is not None}
        if owners - before.get((caller, ordinal), set()):
            newly += 1
        sites.append((caller, ordinal, str(site["name"]), found))
    rows: list[dict[str, object]] = []
    for caller, ordinal, name, found in sites:
        if last and newly:
            # The last round still bound something, so a round not run might bind what it
            # left: no reason the walk gave a path is known to hold.
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
        rows.extend(_rows(caller, ordinal, list(dict.fromkeys(found))))
    workspace.derive("bound_receivers_reset")
    if rows:
        workspace.derive("bound_receivers_insert", rows=rows)
    return newly


# One path's end: (path_id, owner, reason, detail), owner None exactly where reason is set.
_Found = tuple[str, str | None, str | None, str | None]


def _paths(
    index: ValueIndex, site: Mapping[str, Any], handed_on: set[tuple[str, str]]
) -> list[_Found]:
    """Every path the walk reaches `site`'s receiver by, as the type it is there or the
    reason it is none — `which_object`, since what is done to an object never makes it an
    object of another type."""
    name = str(site["name"])
    found: list[_Found] = []
    for producer, path in producer_paths(index, site, RECEIVER, frozenset(), which_object=True):
        path_id = _JOIN.join(path.labels())
        ended = producer.ended_at
        owner = None if ended is None else bound_owner(ended)
        if owner is not None:
            found.append((path_id, owner, None, None))
            # A path out of a function handed on as a value has callers besides the ones it
            # crossed through: that function's own, which the module does not show.
            for crossed in path.crossed_out_of():
                if _function(crossed) in handed_on:
                    found.append(_escapes(name, crossed))
            continue
        found.append(
            (
                path_id,
                None,
                *_reason(
                    name, site.get("receiver_field"), producer.reason, producer.parameter, handed_on
                ),
            )
        )
    if not found:
        # `producer_paths` holds no path that enters one function through two of its calls
        # (`Path.two_calls_of_one_helper`'s bound), so a receiver reached only that way has
        # no path to report: it is code we have, not followed.
        found.append(
            (
                "",
                None,
                NOT_READABLE,
                (
                    f"receiver of {name} not followed: every path to it "
                    "enters one function through two of its calls"
                ),
            )
        )
    return list(dict.fromkeys(found))


def _reason(
    name: str,
    field: object,
    reason: str | None,
    parameter: tuple[str, int] | None,
    handed_on: set[tuple[str, str]],
) -> tuple[str, str]:
    """The reason and the detail of a path that reached no type. `field` is the field the
    receiver is read from, where it is one, for the detail."""
    if reason == EXTERNAL and parameter is not None:
        method, position = parameter
        shown = bare_descriptor(method)
        if _function(method) in handed_on:
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
    if reason == EXTERNAL:
        return EXTERNAL, f"receiver of {name} comes from code outside the scanned module"
    if reason is not None:
        read = "" if field is None else f" reading {field}"
        return reason, f"receiver of {name} not followed{read}: the walk ended at {reason}"
    return NOT_READABLE, f"receiver of {name} is a value of no type the scanned code declares"


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


def _rows(caller: str, ordinal: int, found: list[_Found]) -> list[dict[str, object]]:
    """A site's rows, with the site's own resolution on each (D01's rule: the tier
    describes the site): `resolved` for one type on every path, `narrowed` for several, and
    `partial` where some path reached none."""
    owners = {owner for _, owner, _, _ in found if owner is not None}
    open_path = any(owner is None for _, owner, _, _ in found)
    if open_path:
        bound_tier = Resolution.PARTIAL
    elif len(owners) > 1:
        bound_tier = Resolution.NARROWED
    else:
        bound_tier = Resolution.RESOLVED
    return [
        {
            "caller": caller,
            "ordinal": ordinal,
            "path_id": path_id,
            "owner": owner,
            "evidence": str(Evidence.SYNTAX),
            "resolution": str(bound_tier if owner is not None else Resolution.UNRESOLVED),
            "reason": reason,
            "detail": detail,
        }
        for path_id, owner, reason, detail in found
    ]


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
