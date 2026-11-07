"""2Q `I1`: the `root_kind` producer (D01 §3's `roots`).

**The set a trace starts from, made real.** [D00](docs/components/D00-fact-schema.md)
§4 has documented a `root_kind` set since the fact schema was written and
nothing produced it — entry #7 of `docs/open-issues.md` OI-83 — so a
scheduled method sat in a table nobody traced from while an endpoint handler
was the only thing anything ever started at. `CONTEXT.md` settles the model
this pass implements:

> **Root**: the kind of thing a trace starts from — an inbound endpoint, a
> scheduled job, or a program entry point.

## Why this is a table and not an argument to the walk

A traversal that took an ENDPOINT would have to be reopened the first time
something else started work, and the reopening would be the interesting part:
every question the walk asks (which method, how deep, where does it stop) is
identical for a request and for a clock. So the walk takes a row from here and
branches on the kind nowhere at all — which is also what makes the third kind
free the day it gains a producer.

## What is read

- **Inbound endpoints.** Every `endpoints` row the module EXPOSES and that
  names a handler. `direction <> outbound` rather than `= inbound`, the
  `resolved_peers` precedent: a `both` row is a path the module both exposes
  and calls, so it is as much a root as a purely inbound one and an equality
  test would silently drop it. **No pass writes one today** — W27 (F5 §6.1)
  deleted the merge that did, and a module serving and calling one identity now
  keeps two rows with a `self_exchange` question beside them — so the inequality
  guards the linking tier's row rather than one of this tier's. An outbound row
  carries no handler at all, so it could not be a root even if the test admitted
  it.
- **Scheduled work.** Every `scheduled_work` row's handler. A method the
  framework calls on a clock starts work, contains business logic, and gets a
  trace for the same reason an endpoint handler does — the user's own ruling,
  and the reason `I1` was promoted out of paperwork.
  Not a row the framework REFUSES (`scheduled_work.refused`, spec 2026-11-02 rule
  7, ruled by the user 2026-11-02): that job never runs on that clock.

**One ROOT per (handler, kind); one ROW per address that reaches it.** A method
serving three paths is ONE root: the walk that runs from it is the same walk
whichever address invoked it, and three traces would be three copies of one
answer. It is three ROWS, because the address is the only name a reader has for
a trace — a document that names one by its handler descriptor alone can be
searched for `GET /order/list` and answer nothing, which is exactly what 2Q
shipped. `roots_of` collapses the rows back, so the traversal above still sees
one root and produces one trace. A method that is both — a handler the module
exposes AND schedules — is two roots, because those are two different answers
to "what starts this".

**A root nothing addresses is a row with no address, never an invented one.** A
scheduled job is started by a clock; it has no protocol, no method and no path,
and all three are NULL rather than `(unresolved)` — which would report a gap
where there is none — or a label this pass made up, which would be
fabrication. `docs/open-issues.md` OI-23 carries the third shape: a functional
route is an address whose handler no chain reader named, so it is an endpoint
with no root at all, and this pass cannot give a trace to a method nothing
names.

## The third kind is a catalog's, not this pass's

`entry_point` — D00 §4's third member — is **not derived here**. Which
signature starts a program is a fact about a LANGUAGE or a framework, and
ARCHITECTURE §10 keeps that knowledge out of the language-blind half: it
belongs in a catalog, exactly as a framework's annotation does. A catalog that
says `root_kind: entry_point` (design 2026-11-06-reading-decorators §5,
`catalogs/click.yml`) has its engine write those rows into `roots` itself,
since no other table holds them. So this pass replaces the two kinds it
derives and KEEPS the entry points already there; the pipeline empties the
table once per resolve, before any engine runs, so none survives from an
earlier one (`docs/open-issues.md` OI-22, closed by that catalog).
"""

from dataclasses import dataclass

from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Direction, RootKind


@dataclass(frozen=True)
class RootIdentity:
    """One wire address that reaches a root, exactly as the `endpoints` row
    that named the handler spells it — three columns, uncomposed.

    **Uncomposed on purpose.** `GET /order/list` is one string in the rendered
    document and `egress/render/document.py::_wire_identity` is what builds it,
    from a protocol's own rules about whether it has a verb at all and through
    the render exit's redactor. Composing it here would put a second spelling
    of one address in the codebase (NFR-5) and would carry a `path` past the
    redactor that masks what one can contain.

    Any of the three may be NULL, and each NULL means what it means on the row
    it came from: a protocol that declares no verb has no `method`, and an
    address the analysis could not read has no `path`.

    `method_kind` and `path_kind` are that row's own markers (Vert.x spec §3a),
    carried because they say what the three mean: a NULL `method` beside `any`
    serves every verb, and a `pattern` path is a regular expression, not an
    address. None wherever the row carries none.
    """

    protocol: str | None
    method: str | None
    path: str | None
    method_kind: str | None = None
    path_kind: str | None = None


# The address of a root nothing addresses. Named once, so the two places that
# have to agree about what "no address" looks like — the pass that writes such a
# row and the reader that collapses it — cannot drift apart.
_NO_ADDRESS = RootIdentity(protocol=None, method=None, path=None)


@dataclass(frozen=True)
class Root:
    """One place a trace starts: the method, the kind of thing that starts it,
    and every address that reaches it.

    Carried together rather than as a bare symbol because the kind is what a
    reader needs to say WHAT a trace is a trace of, the addresses are what a
    reader SEARCHES for, and a traversal handed only a symbol could report back
    neither. Nothing in the walk branches on `kind` or reads `identities`; both
    travel through so the answer can name itself.

    `identities` is EMPTY for a root no address reaches — a scheduled job — and
    that emptiness is an answer rather than a gap, which is why it is an empty
    tuple and not a `None` a caller would have to interpret.
    """

    handler: str
    kind: RootKind
    identities: tuple[RootIdentity, ...] = ()


def _text(value: object) -> str | None:
    """One nullable column as itself. NULL stays NULL: an address half that was
    never read is not the empty string, and rendering it as one would publish a
    verb or a path nobody measured."""
    return None if value is None else str(value)


def _address_order(
    identity: tuple[str | None, ...],
) -> tuple[tuple[bool, str], ...]:
    """A total order over the address's nullable columns (NFR-1). Each half sorts as
    (present?, value) so a NULL never compares equal to the empty string — two
    rows differing only in that would otherwise tie, and a tie is an order that
    can change between runs."""
    return tuple((value is not None, value or "") for value in identity)


def record_roots(workspace: Workspace) -> None:
    """Derives `roots` — one row per (handler, kind, address) — and replaces
    the table whole.

    Runs unconditionally and reads no catalog: its inputs are two tables the
    catalog-driven half has already written, and there is no framework
    knowledge left in them to gate on. A module that exposes nothing and
    schedules nothing leaves an empty table rather than a stale one, the
    `resolve_config` discipline.

    **Ordering is part of the answer** (NFR-1): rows are sorted by handler,
    kind, then the address, so two runs over one workspace insert the same
    bytes in the same order.

    The `entry_point` rows a catalog's engine wrote (module docstring) are kept, in the same
    order with the rest: this pass derives the other two kinds and never those.
    """
    kept = {
        (
            _text(row["handler"]),
            RootKind.ENTRY_POINT,
            _text(row["protocol"]),
            _text(row["method"]),
            _text(row["path"]),
            _text(row["method_kind"]),
            _text(row["path_kind"]),
        )
        for row in workspace.query("roots")
        if str(row["root_kind"]) == str(RootKind.ENTRY_POINT)
    }
    workspace.derive("roots_reset")
    found = (
        {
            (
                str(row["handler"]),
                RootKind.INBOUND_ENDPOINT,
                _text(row["protocol"]),
                _text(row["method"]),
                _text(row["path"]),
                _text(row["method_kind"]),
                _text(row["path_kind"]),
            )
            for row in workspace.query("endpoints")
            if row["handler"] is not None and str(row["direction"]) != str(Direction.OUTBOUND)
        }
        | {
            # No address, and none invented: a clock reaches this method, so there
            # is no protocol, verb or path to carry (`RootIdentity`'s own rule).
            (str(row["handler"]), RootKind.SCHEDULED, None, None, None, None, None)
            for row in workspace.query("scheduled_work")
            # A schedule whose job was not found has no handler: there is no code to start a
            # trace at, and a root named "None" would claim one.
            if row["handler"] is not None
            # A schedule the framework REFUSES never starts its job (spec 2026-11-02 rule 7, the
            # `refused` column ruled by the user 2026-11-02): its handler's call graph is not code
            # that runs on this clock, so it is no root. The same handler stays a root through
            # any row the framework accepts.
            and row["refused"] is None
        }
        | kept
    )
    rows = [
        {
            "handler": handler,
            "root_kind": str(kind),
            "protocol": protocol,
            "method": method,
            "path": path,
            "method_kind": method_kind,
            "path_kind": path_kind,
        }
        for handler, kind, protocol, method, path, method_kind, path_kind in sorted(
            found,
            key=lambda entry: (
                entry[0] is not None,
                entry[0] or "",
                str(entry[1]),
                _address_order(entry[2:]),
            ),
        )
    ]
    if rows:
        workspace.derive("roots_insert", rows=rows)


def roots_of(workspace: Workspace) -> list[Root]:
    """Every root this workspace holds, in the table's own fixed order, with
    the several rows of one (handler, kind) collapsed into the one root they
    describe.

    The reader a traversal uses, so that "what can I start from" is answered in
    one place rather than by each caller re-deciding which tables name a root.
    A kind outside D00 §4's closed set raises rather than being carried: this
    table is written by the pass above, so a value that is not a member can
    only mean the workspace was derived by something else — and a walk that
    silently accepted it would report a trace of a kind nobody defined.

    **The collapse happens here and not in the table** because the two answers
    are both wanted and they are wanted by different readers: the walk wants
    one root per (handler, kind), so that a handler serving three addresses
    produces one trace rather than three copies of it, while a reader wants the
    addresses, which is the only name they have for the trace they came to
    find. Rows arrive in the query's own total order, and a dict preserves the
    order keys were first seen in, so the collapsed list is as fixed as the
    table is (NFR-1).
    """
    collapsed: dict[tuple[str, RootKind], list[RootIdentity]] = {}
    for row in workspace.query("roots"):
        # A command whose handler was not read (an entry point behind a library decorator no
        # value model states) is a row with no handler: there is no code to start a walk at.
        if row["handler"] is None:
            continue
        key = (str(row["handler"]), RootKind(str(row["root_kind"])))
        identities = collapsed.setdefault(key, [])
        identity = RootIdentity(
            protocol=_text(row["protocol"]),
            method=_text(row["method"]),
            path=_text(row["path"]),
            method_kind=_text(row["method_kind"]),
            path_kind=_text(row["path_kind"]),
        )
        # An all-NULL row is a root nothing addresses, which is an EMPTY
        # `identities` and never a `RootIdentity` of three NULLs: the second
        # would render as an address whose every half failed to resolve, which
        # is a gap this root does not have.
        if identity != _NO_ADDRESS:
            identities.append(identity)
    return [
        Root(handler=handler, kind=kind, identities=tuple(identities))
        for (handler, kind), identities in collapsed.items()
    ]
