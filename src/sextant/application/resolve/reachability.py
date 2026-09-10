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

One per `(root, symbol)`. The walk expands a method once per trace (`expanded`), so the
depth recorded is the depth it was expanded AT, and a method reached again by another route
is a `revisited` step carrying no subtree. Recording every route instead is the exponential
tree D01 gives as its own reason for not storing traces.

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
    rows: list[dict[str, object]] = []
    for trace in traces_of(workspace):
        # The root's own body is depth 0 and reaches itself trivially; recording it makes
        # "everything this root touches" a single lookup rather than a lookup plus a union
        # with the key, which is the shape every consumer of this table wants.
        seen: set[str] = {trace.root.handler}
        rows.append(
            {
                "root": trace.root.handler,
                "symbol": trace.root.handler,
                "depth": 0,
                "terminal": False,
            }
        )
        for step in trace.steps:
            # The callee where a body was read, the call TARGET where none was: a terminal
            # is a thing the root reaches, and omitting it would make a root that only
            # calls a library look like a root that calls nothing.
            symbol = step.callee if step.callee is not None else step.target
            if symbol in seen:
                continue
            seen.add(symbol)
            rows.append(
                {
                    "root": trace.root.handler,
                    "symbol": symbol,
                    "depth": step.depth,
                    "terminal": step.callee is None,
                }
            )
    workspace.derive("reachability", rows=rows)


__all__ = ["record_reachability"]
