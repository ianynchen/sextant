"""Tests for 2Q `I1`, the `root_kind` producer (`resolve/roots.py`, D01 §3's
`roots`).

**What this file is defending.** D00 §4 documented `root_kind` for as long as
the fact schema has existed and nothing wrote one, so "a scheduled method is a
first-class root" was a sentence in a document and an endpoint handler was the
only thing anything ever started from. The tests below are about the two claims
that makes concrete: that every kind of root reaches the table under its own
name, and that nothing else does.

Two halves, for the reason `test_return_flow.py` states:

- **Against a real scan** (`resolved_fixture`), which is the only thing that can
  say the handler spelling in `roots` is the one `endpoints` actually wrote —
  and which carries the outbound rows a near-miss needs.
- **Against hand-built facts**, for the scheduled kind's literal and folded
  shapes: the compiled fixture's only schedules (`scheduling/OrderSweeper`, spec
  2026-10-23-configured-schedules §3e) are two placeholder jobs on one class.
"""

from pathlib import Path

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.resolve.roots import Root, RootIdentity, record_roots, roots_of
from sextant.domain.closed_sets import ConstructKind, OriginTier, Protocol, RootKind
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_SWEEP = "com/acme/orders/Sweeper#sweep(sig_c8e4ed07)."
_SCHEDULED = "com.acme.Scheduled"
_SCHEDULED_SYMBOL = "com/acme/Scheduled#"
_ON_MESSAGE = "com.acme.OnMessage"
_ON_MESSAGE_SYMBOL = "com/acme/OnMessage#"


@pytest.fixture(scope="module")
def roots(resolved_fixture: tuple[DuckDbWorkspace, ResolveReport]) -> list[dict[str, object]]:
    """`roots` as the resolve wrote it — the rows a `sextant module analyze`
    of this fixture leaves on disk, not something re-derived here."""
    workspace, _ = resolved_fixture
    return workspace.query("roots")


def _handlers(rows: list[dict[str, object]], kind: RootKind) -> set[str]:
    return {str(row["handler"]) for row in rows if str(row["root_kind"]) == str(kind)}


def _scheduled_row() -> dict[str, object]:
    """The one row the hand-built half expects: the sweeper, scheduled, and NO
    address — all three wire columns NULL, because a clock reaches this method
    and there is nothing on the wire that does (2Q close, defect 1)."""
    return {
        "handler": _MODULE + _SWEEP,
        "root_kind": str(RootKind.SCHEDULED),
        "protocol": None,
        "method": None,
        "path": None,
    }


def test_every_inbound_endpoint_handler_is_a_root(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    roots: list[dict[str, object]],
):
    """`CONTEXT.md`: "every inbound endpoint is the root of a trace". The
    assertion is set equality rather than a count, so a root set that is
    merely the right SIZE — one handler missing and an unrelated one added —
    fails."""
    workspace, _ = resolved_fixture
    exposed = {
        str(row["handler"])
        for row in workspace.query("endpoints")
        if row["handler"] is not None and row["direction"] != "outbound"
    }
    assert exposed
    assert _handlers(roots, RootKind.INBOUND_ENDPOINT) == exposed


def test_a_handler_serving_several_addresses_is_one_root_not_several(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    roots: list[dict[str, object]],
):
    """A root is a place a walk STARTS, not an address. The trace from a
    handler is the same walk whichever path invoked it, so a method mapped to
    three paths is ONE root and not three copies of one answer — while the
    table carries one row per address, because the address is the only name a
    reader has for the trace they came to find (2Q close, defect 1). The
    fixture really does have such handlers, which is what makes both halves
    observable rather than vacuous."""
    workspace, _ = resolved_fixture
    exposing = [
        str(row["handler"])
        for row in workspace.query("endpoints")
        if row["handler"] is not None and row["direction"] != "outbound"
    ]
    assert len(exposing) > len(set(exposing)), (
        "no handler serves two rows: the collapse is untested"
    )
    assert len(roots) > len(set(exposing)), "the table dropped an address"
    # The fixture's two scheduled jobs (`scheduling/OrderSweeper`) are roots too, and are not
    # what this counts: they are reached by no address at all.
    served = [root for root in roots_of(workspace) if root.kind is not RootKind.SCHEDULED]
    assert len({(root.handler, root.kind) for root in served}) == len(set(exposing))


def test_a_root_carries_the_wire_address_of_the_row_that_named_it(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """**Defect 1's whole point, against a real scan.** A trace named by a
    handler descriptor alone cannot be found by a reader who knows only their
    URL, so every address that reaches a root travels with it — and it is the
    address the `endpoints` row itself carries, column for column, rather than
    anything this pass composed or re-spelled.

    Set equality on the (handler, address) pairs, not a count: a root set that
    is the right SIZE with one address swapped for another would publish a
    trace under an address that does not reach it, which is the fabrication
    this whole table exists to avoid."""
    workspace, _ = resolved_fixture
    exposed = {
        (str(row["handler"]), row["protocol"], row["method"], row["path"])
        for row in workspace.query("endpoints")
        if row["handler"] is not None and row["direction"] != "outbound"
    }
    assert exposed
    assert {
        (str(row["handler"]), row["protocol"], row["method"], row["path"])
        for row in workspace.query("roots")
        if str(row["root_kind"]) == str(RootKind.INBOUND_ENDPOINT)
    } == exposed


def test_a_reclassified_protocol_reaches_the_root_and_not_the_one_it_replaced(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """**The near-miss for the pass's POSITION in the pipeline**, which became
    load-bearing the day a root started carrying an address (2Q close, defect
    1). `apply_protocol_hints` reclassifies rows other engines minted — the
    fixture moves its two SSE routes out of `http` — so a root recorded before
    that pass carries `http` while the `endpoints` row it was copied from
    carries `sse`: one address, two spellings, in one workspace, which is the
    drift D01 §6 forbids a copied fact.

    The positive control is the reclassification itself: the assertion first
    proves the fixture really does reclassify a row that names a handler, so a
    fixture that stopped doing so fails here rather than passing vacuously."""
    workspace, _ = resolved_fixture
    reclassified = {
        (str(row["handler"]), str(row["protocol"]))
        for row in workspace.query("endpoints")
        if row["handler"] is not None and str(row["protocol"]) == str(Protocol.SSE)
    }
    assert reclassified, "positive control: the fixture reclassifies no handler-bearing row"
    assert reclassified <= {
        (str(row["handler"]), str(row["protocol"])) for row in workspace.query("roots")
    }


@pytest.mark.pins("roots.the-address-is-the-one-the-endpoint-row-ends-with")
def test_the_root_pass_runs_below_the_reclassification_it_copies_from():
    """The same rule as the test above, asserted where the guard harness can
    MEASURE it. `resolved_fixture` needs the compiled fixture, which
    `scripts/guard_check.py` does not copy (`_staged`'s docstring, below,
    states the whole reason), so the behavioural test above is unmeasurable
    as a near-miss and this one carries the marker.

    A source-order assertion rather than a behavioural one because the rule
    IS an order: `record_roots` copies three columns off `endpoints`, and
    `apply_protocol_hints` rewrites one of them on rows that already exist. A
    copy taken above that line is a copy taken mid-write — the drift D01 §6
    forbids — and no property of either pass in isolation can catch it."""
    source = (Path(__file__).parents[2] / "src/sextant/application/resolve/pipeline.py").read_text(
        encoding="utf-8"
    )
    assert source.count("record_roots(workspace)") == 1
    assert source.count("apply_protocol_hints(workspace, declared)") == 1
    assert source.index("record_roots(workspace)") > source.index(
        "apply_protocol_hints(workspace, declared)"
    )


def test_an_outbound_row_contributes_no_root(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    roots: list[dict[str, object]],
):
    """The near-miss, with its positive control beside it. An outbound row is
    a call this module MAKES; tracing from one would start a walk at whatever
    method happened to build the request and report a client as a served
    boundary. The fixture carries 40 of them, so "no root" here is a refusal
    and not an empty input.

    The set is narrowed to callers that are NOT also a handler somewhere, and
    that is the honest question rather than a convenience: a listener that
    both answers a destination and publishes to another is a real shape here,
    and it is a root for its inbound half, not for its outbound one."""
    workspace, _ = resolved_fixture
    endpoints = workspace.query("endpoints")
    outbound = [row for row in endpoints if row["direction"] == "outbound"]
    assert outbound, "positive control: the fixture derives no outbound row at all"
    handlers = {str(row["handler"]) for row in endpoints if row["handler"] is not None}
    callers = {str(row["caller"]) for row in outbound if row["caller"] is not None} - handlers
    assert callers, "positive control: every outbound caller is also a handler"
    assert callers & {str(row["handler"]) for row in roots} == set()


def test_no_pass_writes_a_both_row_any_more(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """F5 §6.1 (W27). Six of this fixture's rows used to merge into `direction: both`, and
    the merge that made them is gone: a wire identity the module both serves and calls is
    two rows now, with a `self_exchange` question beside them.

    Stated here, out loud, for the reason `test_no_root_is_recorded_for_a_kind_nothing_
    produces` states its own: `Direction.BOTH` stays in D00 §4 for the linking tier, so a
    reader of the enum cannot tell from it that nothing at this tier writes one."""
    workspace, _ = resolved_fixture

    assert [row for row in workspace.query("endpoints") if row["direction"] == "both"] == []


def test_a_both_row_is_still_a_root_because_the_module_serves_it(tmp_path: Path):
    """The half of the direction rule that would break under `= inbound`, kept alive
    against a hand-built row now that no pass writes one.

    A `both` row is one wire identity the module exposes AND calls; it names the server's
    handler, so the module really does serve it and a trace really does start there.
    Testing `<> outbound` rather than `= inbound` is what will keep the linking tier's
    rows — the only ones that can justify the claim — from silently losing their traces
    the day that tier lands. Built here rather than measured off the fixture because the
    test above is what says the fixture has none.
    """
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    handler = _MODULE + "com/acme/orders/OrderController#create(sig_00000000)."
    workspace._connection.execute(
        "INSERT INTO endpoints (protocol, direction, method, path, handler, caller) "
        "VALUES ('http', 'both', 'POST', '/v1/orders', ?, 'com/acme/Client#call().')",
        [handler],
    )
    record_roots(workspace)
    rows = workspace.query("roots")
    workspace.close()

    assert [(str(row["handler"]), str(row["root_kind"]), str(row["path"])) for row in rows] == [
        (handler, str(RootKind.INBOUND_ENDPOINT), "/v1/orders")
    ]


def test_no_root_is_recorded_for_a_kind_nothing_produces(roots: list[dict[str, object]]):
    """`entry_point` is a member of the closed set with no producer, and this
    is the assertion that says so out loud rather than leaving it to a reader
    of the enum. Which signature starts a program is a LANGUAGE rule, and
    ARCHITECTURE §10 keeps those out of the resolver — so its producer is a
    catalog nobody has written (OI-22). This test is what fails, loudly, on the
    day somebody adds one without also deciding what it means here."""
    assert _handlers(roots, RootKind.ENTRY_POINT) == set()


def test_the_table_is_replaced_whole_rather_than_appended_to(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The reset/insert discipline every derived table here keeps. Running the
    pass twice leaves the same rows, not twice as many."""
    workspace, _ = resolved_fixture
    before = workspace.query("roots")
    record_roots(workspace)
    assert workspace.query("roots") == before


def test_roots_of_reads_the_table_as_typed_pairs(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    roots: list[dict[str, object]],
):
    """The reader a traversal uses. It answers in the closed set's own type so
    a walk cannot be handed a kind that is merely a string that looked
    plausible."""
    workspace, _ = resolved_fixture
    read = roots_of(workspace)
    assert read == [
        Root(
            handler=handler,
            kind=RootKind(kind),
            identities=tuple(
                RootIdentity(
                    protocol=str(row["protocol"]),
                    method=None if row["method"] is None else str(row["method"]),
                    path=None if row["path"] is None else str(row["path"]),
                )
                for row in roots
                if (str(row["handler"]), str(row["root_kind"])) == (handler, kind)
                # An all-NULL row is a root nothing addresses — the fixture's scheduled jobs —
                # and reads as no identity at all.
                and (row["protocol"], row["method"], row["path"]) != (None, None, None)
            ),
        )
        for handler, kind in dict.fromkeys(
            (str(row["handler"]), str(row["root_kind"])) for row in roots
        )
    ]
    assert all(isinstance(root.kind, RootKind) for root in read)
    assert any(len(root.identities) > 1 for root in read), (
        "positive control: no root in this fixture carries two addresses"
    )


# --- hand-built facts: the scheduled kind -----------------------------------
#
# The compiled fixture's only schedules are two placeholder jobs on one class
# (`scheduling/OrderSweeper`). These build the two facts the scheduled engine
# needs and run the same pipeline steps in order.


def _document() -> Document:
    return Document(
        document_id="doc_sweep",
        relative_path="com/acme/orders/Sweeper.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _catalog() -> Catalog:
    """A catalog of the scheduling STYLE that names no framework — the
    `test_scheduled_work.py` discipline: a test about the ROOT mechanism must
    not pass or fail because a shipped catalog file changed."""
    return Catalog(
        id="test-scheduling",
        style="scheduled_work",
        protocol="",
        direction="",
        requires=(),
        matches={
            "annotation": _SCHEDULED,
            "container": "com.acme.Schedules",
            "triggers": {"cron": "cron"},
        },
        source=Path("test-scheduling.yml"),
    )


def _exposing_catalog() -> Catalog:
    """A gateless inbound catalog over a second invented annotation, so one
    method can be a served handler AND a scheduled declaration at once — the
    only shape that can show the row key is (handler, KIND) rather than the
    handler alone."""
    return Catalog(
        id="test-exposed",
        style="annotation_driven",
        protocol="kafka",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("test-exposed.yml"),
        matches={
            "mapping": {
                "path_from": ["value"],
                "prefix_from": [],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": None,
                "annotations": [{"fqn": _ON_MESSAGE}],
            }
        },
    )


def _scheduled_workspace(tmp_path: Path, *, also_exposed: bool = False) -> DuckDbWorkspace:
    facts = tmp_path / "facts"
    uses = [
        AnnotationFact(
            document_id="doc_sweep",
            target=_MODULE + _SWEEP,
            use=AnnotationUse(annotation=_SCHEDULED_SYMBOL, args={"cron": "0 0 3 * * *"}),
            retention="RUNTIME",
        )
    ]
    if also_exposed:
        uses.append(
            AnnotationFact(
                document_id="doc_sweep",
                target=_MODULE + _SWEEP,
                use=AnnotationUse(annotation=_ON_MESSAGE_SYMBOL, args={"value": "sweeps"}),
                retention="RUNTIME",
            )
        )
    write_fact_file(
        facts / "sweeper.jsonl",
        _document(),
        [
            SymbolFact(
                document_id="doc_sweep",
                symbol=_MODULE + _SWEEP,
                construct_kind=ConstructKind.METHOD,
                enclosing=_MODULE + "com/acme/orders/Sweeper#",
                signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
            ),
            *uses,
        ],
    )
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    workspace.derive("scheduled_work_reset")
    catalogs = [_catalog(), *([_exposing_catalog()] if also_exposed else [])]
    assert derive_endpoints(workspace, catalogs, capabilities={"annotation_args"}) == []
    record_roots(workspace)
    return workspace


def test_a_scheduled_method_is_a_root_of_its_own_kind(tmp_path: Path):
    """**The user's ruling, made checkable.** A scheduled job still contains
    business logic, so it starts a trace exactly as a request does. Before
    `I1` this method reached `scheduled_work` and stopped there: nothing
    traversed from it, and D01 said so in a paragraph rather than in a test.

    The kind is asserted, not only the presence: a scheduled method filed as
    an `inbound_endpoint` would claim the module serves an address it does
    not, which is the whole reason `endpoints` refused the row in the first
    place."""
    workspace = _scheduled_workspace(tmp_path)
    rows = workspace.query("roots")
    workspace.close()
    assert rows == [_scheduled_row()]


def test_a_method_that_is_both_scheduled_and_exposed_is_two_roots(tmp_path: Path):
    """Two kinds are two answers to "what starts this", so they are two rows.
    The row key is (handler, kind): collapsing on the handler alone would lose
    one of the two, and a reader could no longer tell a trace that runs on a
    request from one that runs on a clock — which is exactly the distinction
    `I1` exists to make."""
    workspace = _scheduled_workspace(tmp_path, also_exposed=True)
    rows = workspace.query("roots")
    workspace.close()
    assert [str(row["root_kind"]) for row in rows] == [
        str(RootKind.INBOUND_ENDPOINT),
        str(RootKind.SCHEDULED),
    ]
    assert {str(row["handler"]) for row in rows} == {_MODULE + _SWEEP}


def test_a_kind_outside_the_closed_set_is_refused_rather_than_carried(tmp_path: Path):
    """NFR-5's closed set, enforced at the READ. A row whose kind is not a
    member can only come from a workspace something else derived, and a walk
    handed it would report a trace of a kind nobody defined — so `roots_of`
    raises instead of widening the set by accident."""
    workspace = _scheduled_workspace(tmp_path)
    workspace.derive("roots_insert", rows=[{"handler": _MODULE + _SWEEP, "root_kind": "timer"}])
    with pytest.raises(ValueError):
        roots_of(workspace)
    workspace.close()


def _staged(workspace: DuckDbWorkspace, **overrides: object) -> None:
    """One endpoint row, staged straight through the insert the call-site
    engines use.

    A near-miss for each of the root rule's two conjuncts needs a row that
    satisfies the OTHER one, and neither shape can be reached by pointing a
    catalog at hand-built annotations: the engines that mint an exposed row
    with no handler are chain readers over compiled call sites (the compiled
    fixture has four, all functional routes), and nothing anywhere mints a
    row the module CALLS that also names a handler. `scripts/guard_check.py`
    copies `src/` and `tests/` and not the 16MB compiled fixture, so a guard
    whose near-miss needs `mvn` is reported UNMEASURABLE — worse than no
    guard. Staging the row through the engines' own insert is what makes both
    conjuncts measurable here.
    """
    row: dict[str, object] = {
        "protocol": "kafka",
        "direction": "inbound",
        "method": None,
        "path": "/staged",
        "handler": None,
        "caller": None,
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "catalog_id": "test-staged",
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }
    workspace.derive("call_endpoints", rows=[{**row, **overrides}])
    record_roots(workspace)


@pytest.mark.pins("roots.a-row-naming-no-handler-is-no-root")
def test_an_exposed_row_that_names_no_handler_derives_no_root(tmp_path: Path):
    """**The near-miss for the handler conjunct.** An exposed row can name no
    handler at all — the compiled fixture has four, functional routes whose
    real handler is a lambda the chain reader did not name. Read the missing
    value anyway and it does not stay missing: it becomes a root handler in
    its own right, a symbol no fact ever declared, starting a walk that finds
    nothing and explains nothing about why.

    The positive control is the scheduled root in the same workspace, so "no
    root from this row" is a refusal rather than an empty run."""
    workspace = _scheduled_workspace(tmp_path)
    _staged(workspace)
    rows = workspace.query("roots")
    workspace.close()
    assert rows == [_scheduled_row()]


@pytest.mark.pins("roots.only-a-row-the-module-exposes-is-a-root")
def test_a_row_the_module_calls_is_no_root_even_when_it_names_a_handler(tmp_path: Path):
    """**The near-miss for the direction conjunct**, and the definitional half
    of the rule: `CONTEXT.md` says a root is an INBOUND endpoint, because an
    outbound row is a call this module MAKES. Tracing from one would start a
    walk at whatever method built the request and report a client-side call as
    a place work begins — the wire direction inverted, on every outbound row
    in the module at once.

    No engine writes a handler onto an outbound row today, which is exactly
    why the conjunct has to be tested against a row that does: the rule must
    hold on the day one does rather than by accident of what currently
    happens to be NULL.

    The paired positive is `test_a_method_that_is_both_scheduled_and_exposed_
    is_two_roots`: the same method, exposed, IS a root — so this is not a rule
    that has rotted into declining everything."""
    workspace = _scheduled_workspace(tmp_path)
    _staged(workspace, direction="outbound", handler=_MODULE + _SWEEP, caller=_MODULE + _SWEEP)
    rows = workspace.query("roots")
    workspace.close()
    assert rows == [_scheduled_row()]


def test_a_module_with_nothing_to_start_from_answers_with_an_empty_table(tmp_path: Path):
    """The pre-declared-empty rule every derived table here keeps: a module
    that exposes nothing and schedules nothing answers the query with no rows
    rather than with an error, and never with a previous run's."""
    facts = tmp_path / "facts"
    write_fact_file(facts / "empty.jsonl", _document(), [])
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_roots(workspace)
    rows = workspace.query("roots")
    workspace.close()
    assert rows == []
