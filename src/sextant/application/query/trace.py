"""2Q `G4`/`I3`: the walk from a root to every terminal (D01 §3's Traces).

**A walk, not a table.** D01 says so and gives the reason: storing a trace
would copy every shared subtree once per root that reaches it — a validator on
the path of 150 endpoints would appear 150 times — and nothing in a trace is
original. The call structure is `call_edges`, the nesting is the control-flow
position carried on each row, the roots are `roots`, and the only per-trace
information is membership and the stop markers, both products of the walk
itself. So the walk IS the representation, and it can never disagree with the
edges it came from because it is them.

## It takes a ROOT, and that is `I3`

Not an endpoint handler. The user's ruling: *"a scheduled job still contains
business logic, so there should still be sequence diagrams."* Every question
this walk asks — which method, how deep, where it stops — is identical for work
a request starts and work a clock starts, so **nothing here branches on
`root_kind` at all**. A walk that took an endpoint would have to be reopened
the first time something else started work; this one is already open, and the
third root kind will cost it nothing on the day it gains a producer (OI-22).

## Reachability, never execution

Every claim this walk makes is "this could run from here", and that is weaker
than it looks in three specific ways a reader must be told:

- **Branches are not distinguished.** Two `return` statements yield a set of
  possible answers, not the one that runs; an `if` contributes both sides. The
  walk contains what is REACHABLE, and no path through it is asserted to have
  happened.
- **A `narrowed` step is several rows, none picked.** Where a call could
  dispatch into more than one in-module body, all of them are walked.
- **A `dynamic` step names a body created at that line, not called at it.** The
  lambda runs later, elsewhere, if at all. `invoke_kind` is on every step so
  this is readable rather than inferred.

## Where it stops, all four of them stated on the step itself

`TraceStop` carries the reason, and a step with none was expanded:

- `boundary` — the workspace read no body for the callee. The ruled
  third-party boundary: a mapper, a repository, a driver, anything in the JDK.
  We do not trace into it and we do not read its configuration, so a terminal
  is a method name and never a table name.
- `cycle` — the callee is already on the path from the root. Recursion is real
  code, so it is stated and not followed.
- `revisited` — the callee was expanded elsewhere in this trace. Its subtree is
  shown at its first occurrence.
- `depth_limit` — the bound was reached. **Never silent**, which is the whole
  reason it is a member: a truncated trace that looked complete would be an
  under-report with nothing saying so, and `Trace.truncated` answers it without
  a reader having to scan the steps.

**Cross-module depth is a fifth stop that looks like the first.** A call into a
sibling build module leaves for a workspace this one does not hold, so it reads
as `boundary` — correctly, in that no body was read here, and incompletely, in
that a body exists somewhere. Joining the two is `Bundle`/`Link` work and not
this walk's; `docs/COVERAGE.md` §7 carries the measurement.

## Determinism

NFR-1 binds ordering as well as content. Steps come out in depth-first order
over `call_edges`' own total ordering (`caller`, `ordinal`, `target`,
`callee`), so the walk is the source order of the statements, and the `expanded`
set that decides which occurrence of a shared method is the expanded one is
therefore the same set on every run.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.roots import Root, roots_of
from sextant.domain.closed_sets import Resolution, TraceStop

# How many edges from the root the walk will follow. **A safety bound, not a
# modelling one**: the `expanded` set already makes the walk finite — each
# method is expanded at most once per trace — so this exists for the shape
# neither that nor cycle detection bounds, a long chain of distinct methods, and
# for the recursion depth of the walk itself.
#
# 64 rather than a number tuned to a corpus: the deepest trace measured on
# `macrozheng/mall`'s `mall-admin` is far below it, so on real code it is
# inert, and a bound that fires routinely would be a modelling decision wearing
# a safety bound's clothes. When it does fire it is REPORTED — `Trace.truncated`
# and a `depth_limit` step — because a silently truncated trace is an
# under-report with nothing saying so.
DEFAULT_MAX_DEPTH = 64


@dataclass(frozen=True)
class Step:
    """One edge the walk took, or refused to take.

    `depth` counts edges from the root, so the calls a root's own body makes are
    at depth 1. `caller`/`ordinal` are the call site's identity and `ordinal` is
    its control-flow position, which is what makes a rendering of these steps
    read in the order the statements were written.

    `returns` is what the callee hands back — `(return_ordinal, value)` pairs
    from `return_flows`, in the callee's own instruction order, and EMPTY where
    the callee returns nothing, where its body was not read, or where the site
    is a `dynamic` one (whose `result` is the lambda instance, never anything
    the body returned). Several entries are several possible answers, not a
    sequence: a method with two `return` statements has two, and neither is the
    one that runs.
    """

    depth: int
    caller: str
    ordinal: int
    invoke_kind: str
    target: str
    callee: str | None
    result: int | None
    resolution: Resolution
    stop: TraceStop | None
    returns: tuple[tuple[int, str], ...] = ()
    # D00 §4's `terminal_kind`, and `persistence`'s own `target_kind` (F7 §8.2, W30) —
    # what the call REACHES, carried on the row that already says the walk stopped.
    #
    # The two answer different questions and a step carries both: `stop: boundary` says
    # this workspace read no body, `terminal_kind: persistence` says a catalog knows the
    # callee is a store. Before this, a JDK call and a MyBatis mapper call read alike and
    # the renderer said so — "the distinction is the reader's to make".
    #
    # None where the edge is not a terminal at all.
    terminal_kind: str | None = None
    target_kind: str | None = None


@dataclass(frozen=True)
class Trace:
    """Everything reachable from one root, with the walk's own markers.

    `response` is what the ROOT method hands back — the same `(ordinal, value)`
    shape a step carries, read from `method_returns` rather than from
    `return_flows`, because nothing in this module calls a root and so no return
    flow describes it. It is the "→ response" half of request-to-response: a
    reader joins a `source` inside it to the root's own `call_sites` to see
    which call composed the answer.
    """

    root: Root
    steps: tuple[Step, ...] = ()
    response: tuple[tuple[int, str], ...] = ()

    @property
    def depth(self) -> int:
        """How many edges the deepest step is from the root; 0 for a root whose
        body makes no call at all."""
        return max((step.depth for step in self.steps), default=0)

    @property
    def truncated(self) -> bool:
        """Whether the depth bound cut this walk short. Answered here so a
        caller never has to scan the steps to find out whether what it is
        holding is complete."""
        return any(step.stop is TraceStop.DEPTH_LIMIT for step in self.steps)

    @property
    def terminals(self) -> tuple[Step, ...]:
        """The steps at which the walk left this workspace — the third-party
        boundary, which is where a trace stops by ruling. `cycle` and
        `revisited` are not terminals: both are places the walk had already been
        and neither leaves the module."""
        return tuple(step for step in self.steps if step.stop is TraceStop.BOUNDARY)


@dataclass
class _Index:
    """The three reads a walk needs, taken once for any number of traces."""

    edges: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    returns: dict[tuple[str, int, str], list[tuple[int, str]]] = field(default_factory=dict)
    responses: dict[str, list[tuple[int, str]]] = field(default_factory=dict)


def _index(workspace: Workspace) -> _Index:
    edges: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in workspace.query("call_edges"):
        edges[str(row["caller"])].append(row)
    returns: dict[tuple[str, int, str], list[tuple[int, str]]] = defaultdict(list)
    for row in workspace.query("return_flows"):
        key = (str(row["caller"]), int(str(row["ordinal"])), str(row["callee"]))
        returns[key].append((int(str(row["return_ordinal"])), str(row["value"])))
    responses: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in workspace.query("method_returns"):
        responses[str(row["method"])].append((int(str(row["ordinal"])), str(row["value"])))
    return _Index(edges=edges, returns=returns, responses=responses)


def trace_of(workspace: Workspace, root: Root, *, max_depth: int = DEFAULT_MAX_DEPTH) -> Trace:
    """Everything reachable from one root, bounded and cycle-refusing.

    `root` may be of ANY kind: nothing here reads `root.kind` except to carry it
    back on the answer, which is `I3` in one line.

    Reads the workspace once per call. A caller tracing every root should use
    `traces_of`, which shares the read — the walk is cheap and the three
    projections are not.
    """
    return _traced(root, _index(workspace), max_depth)


def traces_of(workspace: Workspace, *, max_depth: int = DEFAULT_MAX_DEPTH) -> list[Trace]:
    """One trace per row of `roots`, in the table's own fixed order (NFR-1),
    over one read of the workspace."""
    index = _index(workspace)
    return [_traced(root, index, max_depth) for root in roots_of(workspace)]


def _traced(root: Root, index: _Index, max_depth: int) -> Trace:
    if max_depth < 1:
        raise ValueError(f"max_depth must be at least 1 to take a single step, got {max_depth}")
    steps: list[Step] = []
    # Expanded ONCE per trace, not once per path. A method reached by two routes
    # has its subtree shown at the first, and the second says `revisited` — the
    # alternative is a tree that copies every shared subtree per route, which is
    # exponential on an ordinary diamond and is the cost D01 gives as its reason
    # for not storing traces at all.
    expanded = {root.handler}
    _walk(root.handler, 1, {root.handler}, expanded, steps, index, max_depth)
    return Trace(
        root=root,
        steps=tuple(steps),
        response=tuple(index.responses.get(root.handler, ())),
    )


def _walk(
    method: str,
    depth: int,
    path: frozenset[str] | set[str],
    expanded: set[str],
    steps: list[Step],
    index: _Index,
    max_depth: int,
) -> None:
    """Depth-first over `method`'s own call sites, in control-flow order.

    Recursion mirrors the shape being walked and is bounded by `max_depth`,
    which is what keeps the interpreter's own stack out of the failure modes:
    the walk cannot go deeper than the bound, so a pathological graph produces
    a `depth_limit` step rather than a `RecursionError`.
    """
    for row in index.edges.get(method, ()):
        callee = None if row["callee"] is None else str(row["callee"])
        stop = _stop(callee, depth, path, expanded, max_depth)
        steps.append(
            Step(
                depth=depth,
                caller=method,
                ordinal=int(str(row["ordinal"])),
                invoke_kind=str(row["invoke_kind"]),
                target=str(row["target"]),
                callee=callee,
                result=None if row["result"] is None else int(str(row["result"])),
                resolution=Resolution(str(row["resolution"])),
                stop=stop,
                terminal_kind=None if row["terminal_kind"] is None else str(row["terminal_kind"]),
                target_kind=None if row["target_kind"] is None else str(row["target_kind"]),
                returns=tuple(
                    index.returns.get(
                        (method, int(str(row["ordinal"])), callee or ""),
                        (),
                    )
                ),
            )
        )
        if stop is None and callee is not None:
            expanded.add(callee)
            _walk(callee, depth + 1, set(path) | {callee}, expanded, steps, index, max_depth)


def _stop(
    callee: str | None,
    depth: int,
    path: frozenset[str] | set[str],
    expanded: set[str],
    max_depth: int,
) -> TraceStop | None:
    """Why this step was not expanded, or None where it was.

    Order is the answer's meaning, not an optimisation. The boundary is asked
    first because it is a fact about the CODE and the other three are facts
    about the walk: a call that left the module is the terminal whether or not
    the walk had been there before. `cycle` outranks `revisited` because a
    callee on the current path is genuinely recursive and a reader is owed that
    word specifically. `depth_limit` is last because it is the only one that
    reports a LIMIT rather than the code, and reporting it over a cycle would
    blame the bound for something the code did.
    """
    if callee is None:
        return TraceStop.BOUNDARY
    if callee in path:
        return TraceStop.CYCLE
    if callee in expanded:
        return TraceStop.REVISITED
    if depth >= max_depth:
        return TraceStop.DEPTH_LIMIT
    return None
