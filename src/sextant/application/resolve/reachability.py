"""What each root reaches, materialised (F8 §9.4, W37).

**The trace walk already computes this and throws it away.** `query/trace.py` walks every
root on every render and hands the renderer a tree; nothing keeps the reachability, so a
question like "what does changing this method affect" is a walk over the whole graph, once
per question, every time.

This is that walk's own answer written down — and written by the SAME function, which is
the point rather than a convenience. A second traversal with its own rules about cycles and
revisits would be a second opinion about what is reachable, and the day the two disagreed
the document and the table would both be defensible and one of them wrong.

## What a row means

One per `(root, symbol)`, carrying the SHALLOWEST depth any route to it reached. The walk
expands a method once per trace (`expanded`) but still emits a step for every route, so
every distance is seen here and the minimum over them is the true distance from the root.

*W37 recorded the first depth the depth-first walk happened to see, which is not the
shortest: 51 rows on `mall-admin` came out deeper than the truth, 26 of them symbols the
root calls DIRECTLY and recorded at depth 2 or more.* Recording every ROUTE rather than the
shortest is the other extreme, and it is the per-endpoint duplication D01 §3 declines to
store — not branching, which D01 is explicit a single trace does not suffer.

`terminal` says the walk STOPPED there — no body was read, so this is where the work leaves
the module. It does not say what kind of thing it stopped at; `call_edges.terminal_kind`
answers that, and a reader wanting both joins on the symbol.
"""

from sextant.application.ports.workspace import Workspace
from sextant.application.query.trace import traces_of


def record_reachability(workspace: Workspace) -> None:
    """Writes one `reachability` row per (root, symbol) the walk reached.

    Runs LAST among the passes that write derived tables, because the walk reads
    `call_edges` and `roots` and both must be final: a root recorded before
    `apply_protocol_hints` moved a row, or an edge recorded before the terminal
    classification, would put a walk over a graph nobody else saw into the bundle.
    """
    # Cleared first, the `resolve/roots.py` precedent: this table has one writer, so reset
    # and insert belong together here. Without it a second `analyze` over one workspace
    # doubled every row — 190 became 380 — and the duplicates shipped.
    workspace.derive("reachability_reset")
    rows: list[dict[str, object]] = []
    for trace in traces_of(workspace):
        # The root's own body is depth 0 and reaches itself trivially; recording it makes
        # "everything this root touches" a single lookup rather than a lookup plus a union
        # with the key, which is the shape every consumer of this table wants.
        # **The SHALLOWEST depth, not the first one the walk happened to see.** The walk is
        # depth-first, so a symbol reached down one branch before a shorter route to it is
        # read comes up deep — and `depth` is meant to be distance from the root. Measured
        # on `mall-admin`: 51 rows recorded deeper than the true distance, and 26 of them
        # are symbols the ROOT ITSELF calls, recorded at depth 2 or more. A consumer
        # filtering `depth = 1` for "what does this handler call directly" missed every one.
        #
        # The walk emits a step for a revisited symbol too — only its SUBTREE is elided —
        # so every route to a symbol is seen here and the minimum over them is the true
        # distance within what the walk reached.
        #
        # The fixture has zero instances of this, which is why the tests passed.
        shallowest: dict[str, tuple[int, bool]] = {trace.root.handler: (0, False)}
        for step in trace.steps:
            # The callee where a body was read, the call TARGET where none was: a terminal
            # is a thing the root reaches, and omitting it would make a root that only
            # calls a library look like a root that calls nothing.
            symbol = step.callee if step.callee is not None else step.target
            # Neither: a `throw` whose type was unread (`G-52`). The method exits and
            # reaches no symbol a row could name — a NULL key here would also have been
            # sorted beside `str` keys below and raised. The exit itself is on the
            # trace's step row; this table is what a root REACHES.
            if symbol is None:
                continue
            found = shallowest.get(symbol)
            # Strictly shallower, so a tie keeps the walk's own first answer and two runs
            # over one graph record one thing (NFR-1). `terminal` travels with the depth
            # it was observed at rather than being merged: it says what happened on the
            # route being recorded, and a symbol reached as a boundary by one route and
            # expanded by another has no single answer — measured, no corpus has one.
            if found is None or step.depth < found[0]:
                shallowest[symbol] = (step.depth, step.callee is None)
        rows.extend(
            {"root": trace.root.handler, "symbol": symbol, "depth": depth, "terminal": terminal}
            # Sorted so two runs write one order whatever the walk's own was (NFR-1).
            for symbol, (depth, terminal) in sorted(shallowest.items())
        )
    workspace.derive("reachability", rows=rows)


__all__ = ["record_reachability"]
