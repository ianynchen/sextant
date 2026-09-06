"""Tests for 2Q `G4`/`I3`, the walk from a root (`application/query/trace.py`,
D01 §3's Traces).

**The failure this file is built against is a trace that looks right and is
empty underneath.** A traversal over a broken join produces exactly that: every
root answers with a short, plausible walk, every assertion about shape passes,
and nothing has been read. So the first assertions here are about DEPTH and
about a specific named terminal that a broken join could not reach, and the
near-misses carry `pins` markers so the harness measures that they discriminate
rather than trusting that they do.

**`I3` is the subject of half of it.** The walk takes a `Root`, not an endpoint
handler, and branches on the kind nowhere — so it is tested from all three of
D00 §4's kinds, including the one nothing produces yet. That is what stops the
walk having to be reopened the day it does.
"""

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.query.trace import DEFAULT_MAX_DEPTH, trace_of, traces_of
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.resolve.roots import Root, roots_of
from sextant.domain.closed_sets import ConstructKind, OriginTier, RootKind, TraceStop
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallSiteFact,
    CallTarget,
    Document,
    MethodReturnFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import disambiguator_of, method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_TRACE = "com/acme/orders/trace/"
_PROBE = Root(
    handler=_MODULE + _TRACE + "TraceProbe#describe(sig_99bf8bb7).", kind=RootKind.ENTRY_POINT
)
_SHORTEN = Root(
    handler=_MODULE + _TRACE + "SoleRefiner#shorten(sig_1b403611).", kind=RootKind.ENTRY_POINT
)


# --- against a real scan ----------------------------------------------------


def test_a_walk_from_a_real_root_goes_deeper_than_one_hop(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """**The assertion a broken join cannot pass.** A walk whose edges matched
    nothing would still answer for every root — with one level of terminals,
    which looks like a service that calls only libraries. Depth is what tells
    the two apart, so it is asserted before anything about the walk's shape."""
    workspace, _ = resolved_fixture
    traces = traces_of(workspace)
    assert traces, "positive control: the fixture derives no root at all"
    assert max(trace.depth for trace in traces) > 1
    assert sum(1 for trace in traces if trace.depth > 1) > 1


def test_a_walk_reaches_a_named_body_two_hops_from_its_root(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """Depth alone is a number; this names the method. `TraceProbe#describe`
    calls `Refiner#refine` through the interface, and the body that answers it
    calls `String#trim` — so a trace from the probe must contain
    `SoleRefiner#refine` as an expanded step and `String#trim` as a terminal
    under it, which is the whole caller → interface → implementation → terminal
    shape the acceptance corpus asks about."""
    workspace, _ = resolved_fixture
    trace = trace_of(workspace, _PROBE)
    refine = _MODULE + _TRACE + "SoleRefiner#refine(sig_7b622a99)."
    expanded = [step for step in trace.steps if step.callee == refine and step.stop is None]
    assert expanded, "the sole implementation was never entered"
    assert [step.target for step in trace.steps if step.caller == refine and step.stop] == [
        "java/lang/String#trim(sig_0e30dfc9)."
    ]


def test_the_walk_takes_a_root_of_every_kind_and_branches_on_none(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """**`I3` in one assertion.** The user's ruling was that a scheduled job
    contains business logic and deserves the same trace an endpoint does; the
    implementation of that ruling is that this walk reads `Root.kind` for
    exactly one purpose — carrying it back on the answer. The same handler
    traced under all three kinds must produce identical steps, including the
    kind nothing produces yet, because that is what makes the third kind free
    on the day it gains a producer."""
    workspace, _ = resolved_fixture
    traced = [trace_of(workspace, Root(handler=_PROBE.handler, kind=kind)) for kind in RootKind]
    assert len({trace.steps for trace in traced}) == 1
    assert [trace.root.kind for trace in traced] == list(RootKind)


def test_every_root_the_table_holds_is_traced_and_in_the_tables_order(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`traces_of` answers for the whole root set, in the order the table fixes
    (NFR-1) — so two runs produce the same list and a caller that renders them
    produces the same bytes."""
    workspace, _ = resolved_fixture
    traces = traces_of(workspace)
    assert [trace.root for trace in traces] == roots_of(workspace)
    assert [trace.steps for trace in traces] == [trace.steps for trace in traces_of(workspace)]


def test_a_trace_carries_what_its_root_hands_back(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The "→ response" half of request-to-response. Nothing in the module
    calls a root, so no return flow describes one; the root's own
    `method_return` facts are what say what comes back, and a `source` inside
    one joins to the root's own call sites to name the call that composed it."""
    workspace, _ = resolved_fixture
    assert trace_of(workspace, _PROBE).response


def test_a_recursive_call_is_reported_as_a_cycle_and_the_walk_terminates(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """Recursion is real code. `SoleRefiner#shorten` calls itself, so the walk
    meets a callee that is already on its path — it says `cycle` and stops
    following, rather than either looping or quietly dropping the edge."""
    workspace, _ = resolved_fixture
    trace = trace_of(workspace, _SHORTEN)
    recursive = [step for step in trace.steps if step.callee == _SHORTEN.handler]
    assert recursive
    assert {step.stop for step in recursive} == {TraceStop.CYCLE}


def test_the_depth_bound_is_reported_rather_than_applied_silently(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """**A bound that fires without saying so is an under-report with nothing
    to notice it.** Traced at a depth of one, the probe's own calls are all
    that is walked and every expandable step says `depth_limit`; `truncated`
    answers the same question without a caller scanning the steps."""
    workspace, _ = resolved_fixture
    trace = trace_of(workspace, _PROBE, max_depth=1)
    assert trace.truncated
    assert trace.depth == 1
    assert TraceStop.DEPTH_LIMIT in {step.stop for step in trace.steps}
    assert not trace_of(workspace, _PROBE).truncated


def test_a_depth_bound_below_one_step_is_refused(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """A bound of zero would answer with an empty walk for every root, which
    reads exactly like a module whose roots call nothing. It is refused rather
    than served."""
    workspace, _ = resolved_fixture
    with pytest.raises(ValueError):
        trace_of(workspace, _PROBE, max_depth=0)


def test_the_default_bound_does_not_fire_on_the_fixture(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The bound is a SAFETY bound, not a modelling one: a bound that fired
    routinely would be a modelling decision wearing a safety bound's clothes,
    and every trace it cut would be an under-report. Nothing in the fixture
    comes near it."""
    workspace, _ = resolved_fixture
    traces = traces_of(workspace)
    assert not [trace for trace in traces if trace.truncated]
    assert max(trace.depth for trace in traces) < DEFAULT_MAX_DEPTH


def test_a_terminal_is_where_the_workspace_stopped_and_not_where_the_walk_did(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`Trace.terminals` is the third-party boundary alone. A `cycle` and a
    `revisited` step are places the walk had already been, and neither leaves
    the module — counting them as terminals would report a recursive method as
    a place a trace ends."""
    workspace, _ = resolved_fixture
    trace = trace_of(workspace, _PROBE)
    assert {step.stop for step in trace.terminals} == {TraceStop.BOUNDARY}
    assert TraceStop.CYCLE in {step.stop for step in trace.steps}
    assert not [step for step in trace.terminals if step.stop is TraceStop.CYCLE]


# --- hand-built facts, MODULE-PREFIXED --------------------------------------
#
# The half the guards measure: `scripts/guard_check.py` copies `src/` and
# `tests/` and not the compiled fixture, so a guard whose near-miss needs `mvn`
# is reported unmeasurable, which is worse than no guard at all.

_CALLER = "com/acme/orders/gate/Caller#"
_VOID = "()V"
_ROOT = Root(handler=_MODULE + method_descriptor(_CALLER, "run", _VOID), kind=RootKind.SCHEDULED)
_LOOP = _MODULE + method_descriptor(_CALLER, "loop", _VOID)
_SHARED = _MODULE + method_descriptor(_CALLER, "shared", _VOID)


def _document() -> Document:
    return Document(
        document_id="doc_gate",
        relative_path="com/acme/orders/gate/Caller.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.18",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _method(name: str) -> list[object]:
    symbol = _MODULE + method_descriptor(_CALLER, name, _VOID)
    return [
        SymbolFact(
            document_id="doc_gate",
            symbol=symbol,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + _CALLER,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        MethodReturnFact(document_id="doc_gate", method=symbol, ordinal=0, value=None),
    ]


def _call(caller: str, name: str, ordinal: int, owner: str = _CALLER) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_gate",
        caller=_MODULE + method_descriptor(_CALLER, caller, _VOID),
        target=CallTarget(owner=owner, name=name, descriptor=_VOID),
        invoke_kind="static",
        ordinal=ordinal,
        result=None,
    )


@pytest.fixture(scope="module")
def hand_built(tmp_path_factory: pytest.TempPathFactory) -> DuckDbWorkspace:
    """`run` calls `loop` and `shared`; `loop` calls itself and then `shared`
    too. So one workspace holds all three of the walk's own stop reasons: a
    genuine cycle, a method reached twice by different routes, and a call into
    a library nothing scanned."""
    tmp_path = tmp_path_factory.mktemp("trace_hand_built")
    facts = tmp_path / "facts"
    write_fact_file(
        facts / "gate.jsonl",
        _document(),
        [
            SymbolFact(
                document_id="doc_gate", symbol=_MODULE + _CALLER, construct_kind=ConstructKind.CLASS
            ),
            *_method("run"),
            *_method("loop"),
            *_method("shared"),
            _call("run", "loop", 0),
            _call("run", "shared", 1),
            _call("loop", "loop", 0),
            _call("loop", "shared", 1),
            _call("shared", "trim", 0, owner="java/lang/String#"),
        ],
    )
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_call_edges(workspace)
    return workspace


@pytest.mark.pins("trace.a-callee-on-the-current-path-is-a-cycle")
def test_a_callee_already_on_the_path_is_named_a_cycle(hand_built):
    """**Recursion is real code, and `cycle` is the word a reader is owed.**
    Drop the check and the walk still terminates — the expanded set catches the
    second visit — but it reports `revisited`, which says "shown elsewhere in
    this trace" about a method that is calling ITSELF. A reader looking for
    recursion would find none, on every recursive method in the module."""
    trace = trace_of(hand_built, _ROOT)
    recursive = [step for step in trace.steps if step.caller == _LOOP and step.callee == _LOOP]
    assert [step.stop for step in recursive] == [TraceStop.CYCLE]


@pytest.mark.pins("trace.a-depth-bound-reached-is-said-out-loud")
def test_reaching_the_bound_is_a_step_that_says_so(hand_built):
    """The near-miss for the bound. Stop reporting it and a truncated walk is
    indistinguishable from a complete one: `truncated` answers False, the
    deepest steps look like ordinary leaves, and every trace on a deep module
    silently loses everything past the bound. That is the second sin with a
    switch on it."""
    trace = trace_of(hand_built, _ROOT, max_depth=1)
    assert trace.truncated
    assert TraceStop.DEPTH_LIMIT in {step.stop for step in trace.steps}
    assert not trace_of(hand_built, _ROOT).truncated


def test_a_method_reached_twice_is_expanded_once_and_says_so(hand_built):
    """A shared subtree is shown at its first occurrence and marked
    `revisited` at the second. Expanding it per route would copy every shared
    subtree once per path that reaches it — the cost D01 gives as its reason
    for a trace being a walk rather than a stored table — and dropping the
    second edge would hide a call the code really makes."""
    trace = trace_of(hand_built, _ROOT)
    shared = [step for step in trace.steps if step.callee == _SHARED]
    assert len(shared) == 2
    assert [step.stop for step in shared] == [None, TraceStop.REVISITED]


def test_a_call_into_a_library_is_the_terminal(hand_built):
    """The ruled third-party boundary, reached through two hops of in-module
    bodies — so the terminal is a property of the CALL and not of how far the
    walk had gone."""
    trace = trace_of(hand_built, _ROOT)
    assert [step.target for step in trace.terminals] == [
        "java/lang/String#trim(" + disambiguator_of(_VOID) + ")."
    ]


def test_a_root_with_no_edges_traces_to_an_empty_walk(hand_built):
    """A method whose body this workspace read and which calls nothing has no
    steps and no stop reason — the absence of children says it exactly, which
    is why the stop vocabulary needs no member for it."""
    trace = trace_of(hand_built, Root(handler=_SHARED, kind=RootKind.SCHEDULED))
    assert [step.stop for step in trace.steps] == [TraceStop.BOUNDARY]
    empty = trace_of(
        hand_built, Root(handler=_MODULE + "com/acme/Absent#gone().", kind=RootKind.SCHEDULED)
    )
    assert empty.steps == ()
    assert empty.depth == 0
    assert not empty.truncated
