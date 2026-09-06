"""2Q `I1`: the `root_kind` producer (D01 §3's `roots`).

**The set a trace starts from, made real.** [D00](docs/components/D00-fact-schema.md)
§4 has documented a `root_kind` set since the fact schema was written and
nothing produced it — entry #7 of `docs/documented-not-implemented.md` — so a
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
  and calls (D02 §3's merge), so it is as much a root as a purely inbound one
  and an equality test would silently drop it. An outbound row carries no
  handler at all, so it could not be a root even if the test admitted it.
- **Scheduled work.** Every `scheduled_work` row's handler. A method the
  framework calls on a clock starts work, contains business logic, and gets a
  trace for the same reason an endpoint handler does — the user's own ruling,
  and the reason `I1` was promoted out of paperwork.

**One row per (handler, kind).** A method serving three paths is ONE root: the
walk that runs from it is the same walk whichever address invoked it, and three
rows would be three copies of one answer. A method that is both — a handler the
module exposes AND schedules — is two rows, because those are two different
answers to "what starts this".

## What is NOT read, and why the absence is stated

`entry_point` — D00 §4's third member — has **no producer here**. Which
signature starts a program is a fact about a LANGUAGE, and ARCHITECTURE §10
keeps language knowledge out of the language-blind half: the descriptor a
runtime looks for belongs in a catalog, exactly as a framework's annotation
does, and no catalog declares one. Writing it into this pass would put a
language's rule in the resolver, and guessing it from a method's NAME alone
would derive a root for any method that happens to be called that — a
fabrication with a very low bar. `docs/open-issues.md` OI-22 carries it with
what closes it; `docs/COVERAGE.md` carries the boundary a reader meets.
"""

from dataclasses import dataclass

from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Direction, RootKind


@dataclass(frozen=True)
class Root:
    """One place a trace starts: the method, and the kind of thing that starts
    it.

    Carried as a pair rather than as a bare symbol because the kind is what a
    reader needs to say WHAT a trace is a trace of, and because a traversal
    handed only a symbol could not report it back. Nothing in the walk branches
    on `kind`; it travels through so the answer can name itself.
    """

    handler: str
    kind: RootKind


def record_roots(workspace: Workspace) -> None:
    """Derives `roots` — one row per (handler, kind) — and replaces the table
    whole.

    Runs unconditionally and reads no catalog: its inputs are two tables the
    catalog-driven half has already written, and there is no framework
    knowledge left in them to gate on. A module that exposes nothing and
    schedules nothing leaves an empty table rather than a stale one, the
    `resolve_config` discipline.

    **Ordering is part of the answer** (NFR-1): rows are sorted by handler then
    kind, so two runs over one workspace insert the same bytes in the same
    order.
    """
    workspace.derive("roots_reset")
    found = {
        (str(row["handler"]), RootKind.INBOUND_ENDPOINT)
        for row in workspace.query("endpoints")
        if row["handler"] is not None and str(row["direction"]) != str(Direction.OUTBOUND)
    } | {(str(row["handler"]), RootKind.SCHEDULED) for row in workspace.query("scheduled_work")}
    rows = [
        {"handler": handler, "root_kind": str(kind)}
        for handler, kind in sorted(found, key=lambda entry: (entry[0], str(entry[1])))
    ]
    if rows:
        workspace.derive("roots_insert", rows=rows)


def roots_of(workspace: Workspace) -> list[Root]:
    """Every root this workspace holds, in the table's own fixed order.

    The reader a traversal uses, so that "what can I start from" is answered in
    one place rather than by each caller re-deciding which tables name a root.
    A kind outside D00 §4's closed set raises rather than being carried: this
    table is written by the pass above, so a value that is not a member can
    only mean the workspace was derived by something else — and a walk that
    silently accepted it would report a trace of a kind nobody defined.
    """
    return [
        Root(handler=str(row["handler"]), kind=RootKind(str(row["root_kind"])))
        for row in workspace.query("roots")
    ]
