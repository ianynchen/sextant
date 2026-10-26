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

## Where it stops, all three of them stated on the step itself

`TraceStop` carries the reason, and a step with none was expanded:

- `boundary` — the workspace read no body for the callee. The ruled
  third-party boundary: a mapper, a repository, a driver, anything in the JDK.
  We do not trace into it and we do not read its configuration, so a terminal
  is a method name and never a table name.
- `cycle` — the callee is already on the path from the root. Recursion is real
  code, so it is stated and not followed.
- `revisited` — the callee was expanded elsewhere in this trace. Its subtree is
  shown at its first occurrence.

**A gRPC call to this module's own service is followed, not stopped at** (spec
2026-10-25 §3d, ruling 2: *"a call hop that's traceable"*). A stub method's call into the
client-call API is a `boundary` in `call_edges`, a library no workspace reads; where
`rpc_hops` names the handler that call lands on, the step goes to that handler instead and
carries the wire path in `via`. The handler is then any callee — expanded, `revisited` or a
`cycle` by the same three answers — and a hop with no handler here is still a `boundary`,
with its wire path.

**There is no fourth**, and there was: `depth_limit` retired with the bound it
reported (FR-6, F7 §8.1, W31), along with the `Trace.truncated` property that
answered "did that bound cut this short". Every reason left is a fact about the
code or about a route through it, never about a limit this system imposed.

**Cross-module depth is a fourth stop that looks like the first.** A call into a
sibling build module leaves for a workspace this one does not hold, so it reads
as `boundary` — correctly, in that no body was read here, and incompletely, in
that a body exists somewhere. Joining the two is `Bundle`/`Link` work and not
this walk's; `docs/COVERAGE.md` §7 carries the measurement.

## Determinism

NFR-1 binds ordering as well as content. Steps come out in depth-first order
over `call_edges`' own total ordering (`caller`, `ordinal`, `target`,
`callee`), and several hops at one site in `rpc_hops`' own `handler` order, so
the walk is the source order of the statements, and the `expanded` set that
decides which occurrence of a shared method is the expanded one is therefore the
same set on every run.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.roots import Root, roots_of
from sextant.domain.closed_sets import Resolution, TraceStop


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
    # NULL on exactly one shape (`G-52`): a `throw` whose type this pass could not read —
    # a rethrow, whose type lives in the try-catch table. Kept NULL rather than spelled
    # `str(None)`, which put a participant named `None` into the diagram and a symbol
    # named `None` into `reachability`; a step with no target and no callee is a method
    # leaving through an exception nobody named, and every reader says that in words.
    target: str | None
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
    # Spec 2026-10-25 §3d: `"<protocol> <path>"` where this call left for the wire and
    # `callee` is where it lands in this module (`rpc_hops`) — `target` still names the
    # client-call method the code called. None on every other step.
    via: str | None = None


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
    def terminals(self) -> tuple[Step, ...]:
        """The steps at which the walk left this workspace — the third-party
        boundary, which is where a trace stops by ruling. `cycle` and
        `revisited` are not terminals: both are places the walk had already been
        and neither leaves the module."""
        return tuple(step for step in self.steps if step.stop is TraceStop.BOUNDARY)


@dataclass
class _Index:
    """The four reads a walk needs, taken once for any number of traces."""

    edges: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    returns: dict[tuple[str, int, str], list[tuple[int, str]]] = field(default_factory=dict)
    responses: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    # `rpc_hops` by its call site, `(caller, ordinal)` — the `call_edges` row it replaces.
    hops: dict[tuple[str, int], list[dict[str, object]]] = field(default_factory=dict)


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
    hops: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in workspace.query("rpc_hops"):
        hops[(str(row["caller"]), int(str(row["ordinal"])))].append(row)
    return _Index(edges=edges, returns=returns, responses=responses, hops=hops)


def trace_of(workspace: Workspace, root: Root) -> Trace:
    """Everything reachable from one root, finite and cycle-refusing.

    `root` may be of ANY kind: nothing here reads `root.kind` except to carry it
    back on the answer, which is `I3` in one line.

    Reads the workspace once per call. A caller tracing every root should use
    `traces_of`, which shares the read — the walk is cheap and the three
    projections are not.
    """
    return _traced(root, _index(workspace))


def traces_of(workspace: Workspace) -> list[Trace]:
    """One trace per row of `roots`, in the table's own fixed order (NFR-1),
    over one read of the workspace."""
    index = _index(workspace)
    return [_traced(root, index) for root in roots_of(workspace)]


def _traced(root: Root, index: _Index) -> Trace:
    steps: list[Step] = []
    # Expanded ONCE per trace, not once per path. A method reached by two routes
    # has its subtree shown at the first, and the second says `revisited` — the
    # alternative is a tree that copies every shared subtree per route, which is
    # exponential on an ordinary diamond and is the cost D01 gives as its reason
    # for not storing traces at all.
    expanded = {root.handler}
    _walk(root.handler, expanded, steps, index)
    return Trace(
        root=root,
        steps=tuple(steps),
        response=tuple(index.responses.get(root.handler, ())),
    )


def _walk(
    method: str,
    expanded: set[str],
    steps: list[Step],
    index: _Index,
) -> None:
    """Depth-first over `method`'s own call sites, in control-flow order.

    **An explicit stack, and that is what let the depth bound go** (FR-6, F7 §8.1, W31).
    The walk used to recurse and carry a `max_depth` of 64, whose own comment called it "a
    safety bound, not a modelling one" — there for the recursion depth of the walk itself,
    not for anything about the code. Measured across `mall-admin`,
    `spring-petclinic-rest` and `jhipster-sample-app`: the deepest trace is **9** against
    that 64, and no trace was ever truncated. So it was inert on every repository
    available, and FR-6 says a trace should not be bounded by a counter at all.

    **The bound could not simply be deleted, and that is why the stack came first.** While
    it was there the recursion could not exceed 64 frames against an interpreter limit of
    1000, so it was doing its safety job perfectly well; removing it from the recursive
    form would have turned a stated, truncated answer into a `RecursionError` on a long
    chain of distinct methods — which neither cycle detection nor `expanded` bounds. With
    the stack the interpreter's limit is out of the failure modes entirely, so the walk
    terminates where the evidence does: at a terminal, a cycle, or a revisit. Cycle and
    revisit refusal stay because they are correctness — without them it would not finish.

    **The order is preserved exactly, and it was verified rather than argued.** A recursive
    pre-order visits a row, then everything that row leads to, then the next row. The stack
    holds one FRAME per method being expanded, each keeping its own remaining rows in
    source order; a row is taken from the front and, when it expands, the callee's frame is
    pushed immediately — so the deepest open frame is always `stack[-1]` and the callee's
    subtree is finished before the caller's next row is read. Checked against a faithful
    reimplementation of the recursive form over 235 roots on the three repositories above:
    identical step sequences, byte for byte.

    `path` — the ancestors on the CURRENT route, which is what `cycle` is about — rides on
    the frame rather than being reconstructed, because it differs per route while
    `expanded` is per trace.
    """
    # One frame per method being expanded: the rows it has left to visit, its depth, and
    # the ancestors on the route that reached it.
    # A deque per frame rather than a list: rows come off the FRONT, and `list.pop(0)`
    # is linear, so a method with many call sites would cost O(sites²) to expand. Real
    # fan-outs make that unmeasurable — mall-admin's widest trace is 48 steps — but the
    # frame already pays a copy here, and `popleft` is the same copy without the square.
    stack: list[tuple[str, int, frozenset[str], deque[dict[str, object]]]] = [
        (method, 1, frozenset({method}), deque(_rows(method, index)))
    ]
    while stack:
        caller, depth, path, pending = stack[-1]
        if not pending:
            stack.pop()
            continue
        row = pending.popleft()
        callee = None if row["callee"] is None else str(row["callee"])
        stop = _stop(callee, path, expanded)
        steps.append(
            Step(
                depth=depth,
                caller=caller,
                ordinal=int(str(row["ordinal"])),
                invoke_kind=str(row["invoke_kind"]),
                target=None if row["target"] is None else str(row["target"]),
                callee=callee,
                result=None if row["result"] is None else int(str(row["result"])),
                resolution=Resolution(str(row["resolution"])),
                stop=stop,
                terminal_kind=None if row["terminal_kind"] is None else str(row["terminal_kind"]),
                target_kind=None if row["target_kind"] is None else str(row["target_kind"]),
                via=None if row.get("via") is None else str(row["via"]),
                returns=tuple(
                    index.returns.get(
                        (caller, int(str(row["ordinal"])), callee or ""),
                        (),
                    )
                ),
            )
        )
        if stop is None and callee is not None:
            expanded.add(callee)
            # Pushed immediately, which is what makes this pre-order: everything this
            # callee leads to is visited before the caller's next row, exactly as the
            # recursive form did.
            stack.append((callee, depth + 1, path | {callee}, deque(_rows(callee, index))))


def _rows(method: str, index: _Index) -> list[dict[str, object]]:
    """`method`'s `call_edges` rows in their own order, each call site that `rpc_hops` names
    replaced by one row per hop: the same call, its `callee` the handler it lands on (NULL
    where there is none here) and `via` its wire path (spec 2026-10-25 §3d).

    A hop that lands on a handler is not a terminal, so it drops the `ClientCalls` row's
    `terminal_kind`/`target_kind` (D01: NULL on a row that is not a terminal). A hop with no
    handler is still the boundary and keeps the row's classification.

    Replaced in the frame's rows rather than at the step, so each hop is an ordinary row
    to the walk: its handler's subtree follows it before the next hop's step, as a narrowed
    site's candidates do, and `_stop` decides it as it decides any callee.
    """
    rows: list[dict[str, object]] = []
    for row in index.edges.get(method, ()):
        hops = index.hops.get((method, int(str(row["ordinal"]))))
        if not hops:
            rows.append(row)
            continue
        for hop in hops:
            landed = {"callee": hop["handler"], "via": f"{hop['protocol']} {hop['path']}"}
            if hop["handler"] is not None:
                landed |= {"terminal_kind": None, "target_kind": None}
            rows.append({**row, **landed})
    return rows


def _stop(
    callee: str | None,
    path: frozenset[str],
    expanded: set[str],
) -> TraceStop | None:
    """Why this step was not expanded, or None where it was.

    Order is the answer's meaning, not an optimisation. The boundary is asked
    first because it is a fact about the CODE and the other two are facts
    about the walk: a call that left the module is the terminal whether or not
    the walk had been there before. `cycle` outranks `revisited` because a
    callee on the current path is genuinely recursive and a reader is owed that
    word specifically.

    **There is no fourth answer since W31.** `depth_limit` was last here, "the only one
    that reports a LIMIT rather than the code", and the bound it reported is gone: every
    member left is a fact about the code or about a route through it.
    """
    if callee is None:
        return TraceStop.BOUNDARY
    if callee in path:
        return TraceStop.CYCLE
    if callee in expanded:
        return TraceStop.REVISITED
    return None
