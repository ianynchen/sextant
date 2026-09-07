"""Tests for 2Q `G4`'s `call_edges` (`resolve/call_edges.py`, D01 §3's Edges).

**Two halves, and the reason is `test_return_flow.py`'s.** OI-4 is one identity
with two string spellings, and this table joins across exactly that boundary —
a call target composes BARE, a body's symbol is MODULE-PREFIXED, and a join
across the two matches nothing on a real module while passing on a fixture that
spells everything bare. So:

- **Against a real scan** (`resolved_fixture`), which is the only thing that can
  prove the composed descriptor agrees with what the extractor wrote, and the
  only place a `dynamic` site with a real bootstrap handle exists.
- **Against hand-built facts that are MODULE-PREFIXED**, which carry the `pins`
  markers: `scripts/guard_check.py` copies `src/` and `tests/` and not the 16MB
  compiled fixture, so a guard whose near-miss needs `mvn` is reported
  unmeasurable, which is worse than no guard.

The dispatch rule itself is `resolve/dispatch.py`'s and is pinned by
`test_return_flow.py` — this file tests what `call_edges` does with the answer,
which is where it differs from `return_flows`: a row for a call that produces no
value, a row for a call that leaves the module, and an edge into a lambda body.
"""

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.closed_sets import ConstructKind, Evidence, OriginTier, Resolution
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    MethodReturnFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import bare_descriptor, disambiguator_of, method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_TRACE = "com/acme/orders/trace/"
_DESCRIBE = _MODULE + _TRACE + "TraceProbe#describe(sig_99bf8bb7)."


@pytest.fixture(scope="module")
def edges(resolved_fixture: tuple[DuckDbWorkspace, ResolveReport]) -> list[dict[str, object]]:
    """`call_edges` as the resolve wrote it — the rows a `sextant module
    analyze` of this fixture leaves on disk, not something re-derived here."""
    workspace, _ = resolved_fixture
    return workspace.query("call_edges")


def _at(rows: list[dict[str, object]], caller: str, ordinal: int) -> list[dict[str, object]]:
    return [row for row in rows if row["caller"] == caller and row["ordinal"] == ordinal]


def test_the_join_produces_rows_at_all_on_a_module_prefixed_scan(edges):
    """The OI-4 pin, and the first thing to check: round 1's `F6` and 2O Task
    10 both shipped a join that matched NOTHING on a real module while their
    tests were green. A count is what tells the two apart."""
    assert edges
    assert [row for row in edges if row["callee"] is not None]


def test_a_call_target_composed_bare_reaches_a_module_prefixed_body(edges):
    """**The join, in one assertion.** `target` is the JVM's own triple
    composed to a BARE descriptor; `callee` is the MODULE-PREFIXED symbol of
    the body it reaches. Both spellings on one row, deliberately: the bare one
    is what a reader sees at that line in the source, and the prefixed one is
    what a walk joins to the callee's own rows to take the next hop."""
    rows = _at(edges, _DESCRIBE, 0)
    assert [str(row["target"]) for row in rows] == [_TRACE + "Refiner#refine(sig_7b622a99)."]
    assert [str(row["callee"]) for row in rows] == [
        _MODULE + _TRACE + "SoleRefiner#refine(sig_7b622a99)."
    ]


def test_a_call_that_produces_no_value_is_still_an_edge(edges):
    """**The difference from `return_flows` that makes this table necessary.**
    A return flow exists only where a call produced a value, so a method that
    hands nothing back contributes no row there at all — and a write, a publish
    or a delete is frequently the whole point of the work a trace is about.
    Here the constructor call at ordinal 2 is an edge like any other, with a
    NULL `result` saying that nothing came back rather than that nothing
    happened."""
    rows = _at(edges, _DESCRIBE, 2)
    assert [row["result"] for row in rows] == [None]
    assert [str(row["callee"]) for row in rows] == [
        _MODULE + _TRACE + "SoleRefiner#<init>(sig_da8c82d5)."
    ]


def test_a_call_into_a_third_party_is_a_row_whose_callee_is_null(edges):
    """The ruled boundary, written as a row rather than as an absence. This is
    where `call_edges` must differ from `return_flows`, which leaves such a
    site out entirely: "this call leaves the module here" and "this method
    makes no calls" are different answers, and a table recording neither would
    report them identically. `target` still names exactly what the compiler
    wrote, because that name IS the terminal a reader wants to see."""
    rows = _at(edges, _DESCRIBE, 5)
    assert [row["callee"] for row in rows] == [None]
    assert [str(row["target"]) for row in rows] == ["java/lang/String#concat(sig_7b622a99)."]
    assert [str(row["resolution"]) for row in rows] == [str(Resolution.RESOLVED)]


def test_several_implementations_narrow_and_none_is_picked(edges):
    """2Q's own rule, on the control graph this time. Both bodies are listed,
    the site says `narrowed`, and neither is chosen — so a walk goes into both
    and a reader is never told which one runs."""
    rows = _at(edges, _DESCRIBE, 1)
    assert sorted(str(row["callee"]) for row in rows) == [
        _MODULE + _TRACE + "FirstSplitter#head(sig_7b622a99).",
        _MODULE + _TRACE + "SecondSplitter#head(sig_7b622a99).",
    ]
    assert {str(row["resolution"]) for row in rows} == {str(Resolution.NARROWED)}


def test_a_lambda_site_names_the_body_it_creates_and_not_the_bootstrap(edges):
    """**Capability 9.17's consumer, and OI-14's close condition.** An
    `invokedynamic`'s own target is `LambdaMetafactory#metafactory` — a
    platform class every lambda in the module would terminate at. The site
    records what it actually creates (`call_site.implementation`), and that is
    the edge. Without it a `list.forEach(x -> mapper.insert(x))` stops at
    `forEach` and the persistence inside the lambda is invisible.

    `invoke_kind` rides on the row so a reader is never told the body runs AT
    this line: it is CREATED here and runs later, elsewhere, if at all."""
    rows = [row for row in edges if row["invoke_kind"] == "dynamic"]
    assert rows, "positive control: the fixture derives no lambda site at all"
    assert not [row for row in rows if "LambdaMetafactory" in str(row["target"])]
    reached = [row for row in rows if row["callee"] is not None]
    assert reached
    for row in reached:
        assert str(row["target"]) == bare_descriptor(str(row["callee"]))


def test_a_dynamic_site_that_creates_no_body_contributes_no_edge(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    edges: list[dict[str, object]],
):
    """The near-miss beside the test above, and a fabrication refusal. Not
    every `invokedynamic` creates a body: string concatenation compiles to one
    whose bootstrap is a compiler artifact rather than a call the program
    makes. The extractor writes `implementation` only where there IS a body, so
    a site without one gets no row — an edge to `StringConcatFactory` would put
    a platform factory into a trace at every string a method builds.

    The positive control is in the same table: sites that DO name a body are
    edges, so this is a refusal and not an empty read."""
    workspace, _ = resolved_fixture
    without = {
        (str(site["caller"]), site["ordinal"])
        for site in workspace.query("call_sites")
        if site["invoke_kind"] == "dynamic" and site["implementation"] is None
    }
    assert without, "positive control: every lambda site names a body"
    assert without & {(str(row["caller"]), row["ordinal"]) for row in edges} == set()
    assert [row for row in edges if row["invoke_kind"] == "dynamic" and row["callee"]]


def test_every_other_call_site_contributes_at_least_one_edge(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    edges: list[dict[str, object]],
):
    """The completeness claim, asserted rather than assumed: a trace that
    silently lost call sites would be the second sin, and it would look exactly
    like a short trace. Every site is an edge except the one shape the test
    above names."""
    workspace, _ = resolved_fixture
    sites = {
        (str(site["caller"]), site["ordinal"])
        for site in workspace.query("call_sites")
        if not (site["invoke_kind"] == "dynamic" and site["implementation"] is None)
    }
    assert sites - {(str(row["caller"]), row["ordinal"]) for row in edges} == set()


def test_every_row_carries_the_compiler_as_its_evidence(edges):
    """The call site, the descriptors and the hierarchy are all what the
    compiler wrote into the class files; nothing here is inferred from a name,
    and a row claiming any weaker tier would be claiming a source it did not
    have."""
    assert {str(row["evidence"]) for row in edges} == {str(Evidence.COMPILER)}


def test_the_table_is_replaced_whole_rather_than_appended_to(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The reset/insert discipline every derived table here keeps. Running the
    pass twice leaves the same rows, not twice as many."""
    workspace, _ = resolved_fixture
    before = workspace.query("call_edges")
    record_call_edges(workspace)
    assert workspace.query("call_edges") == before


# --- hand-built facts, MODULE-PREFIXED --------------------------------------
#
# OI-4's own prescribed remedy, and the half the guards measure. Every symbol
# below carries `_MODULE`, exactly as a real scan writes it.

_OWNER = "com/acme/orders/gate/Gateway#"
_CALLER = "com/acme/orders/gate/Caller#"
_LAMBDA = "com/acme/orders/gate/Caller#lambda$run$0"
_VOID_JVM = "()V"
_RUN = _CALLER + "run(" + disambiguator_of(_VOID_JVM) + ")."
_BODY = _LAMBDA + "(" + disambiguator_of(_VOID_JVM) + ")."
_FACTORY = "java/lang/invoke/LambdaMetafactory#"


def _document() -> Document:
    return Document(
        document_id="doc_gate",
        relative_path="com/acme/orders/gate/Caller.java",
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


def _declared(owner: str, name: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_gate",
        symbol=_MODULE + method_descriptor(owner, name, _VOID_JVM),
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
    )


@pytest.fixture(scope="module")
def hand_built(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, object]]:
    """`Caller#run` makes three calls: one into a library method nothing
    scanned, one `invokedynamic` naming a lambda body this workspace read, and
    one `invokedynamic` naming no body at all."""
    tmp_path = tmp_path_factory.mktemp("call_edges_hand_built")
    facts = tmp_path / "facts"
    write_fact_file(
        facts / "gate.jsonl",
        _document(),
        [
            SymbolFact(
                document_id="doc_gate", symbol=_MODULE + _CALLER, construct_kind=ConstructKind.CLASS
            ),
            _declared(_CALLER, "run"),
            _declared(_CALLER, "lambda$run$0"),
            MethodReturnFact(
                document_id="doc_gate",
                method=_MODULE + method_descriptor(_CALLER, "lambda$run$0", _VOID_JVM),
                ordinal=0,
                value=None,
            ),
            MethodReturnFact(
                document_id="doc_gate",
                method=_MODULE + _RUN,
                ordinal=0,
                value=None,
            ),
            CallSiteFact(
                document_id="doc_gate",
                caller=_MODULE + _RUN,
                target=CallTarget(owner=_OWNER, name="send", descriptor=_VOID_JVM),
                invoke_kind="interface",
                ordinal=0,
                result=None,
            ),
            CallSiteFact(
                document_id="doc_gate",
                caller=_MODULE + _RUN,
                target=CallTarget(owner=_FACTORY, name="metafactory", descriptor=_VOID_JVM),
                invoke_kind="dynamic",
                ordinal=1,
                result=4,
                implementation=_BODY,
                arguments=[CallArgument(kind="lambda", symbol=_BODY)],
            ),
            CallSiteFact(
                document_id="doc_gate",
                caller=_MODULE + _RUN,
                target=CallTarget(owner=_FACTORY, name="metafactory", descriptor=_VOID_JVM),
                invoke_kind="dynamic",
                ordinal=2,
                result=7,
            ),
        ],
    )
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_call_edges(workspace)
    rows = workspace.query("call_edges")
    workspace.close()
    return rows


@pytest.mark.pins("call_edges.a-lambda-site-names-the-body-not-the-bootstrap")
def test_a_lambda_site_is_an_edge_into_the_body(hand_built):
    """**OI-14's consumer, pinned.** Read the site's own `target` instead and
    every lambda in the module becomes an edge to `LambdaMetafactory` — a
    platform class, therefore a terminal, therefore a trace that stops at the
    line that creates a lambda and never enters the business logic inside it.
    On `macrozheng/mall`'s `mall-admin` that is fifteen bodies, seven of which
    hold a terminal reachable no other way."""
    rows = [row for row in hand_built if row["ordinal"] == 1]
    assert [str(row["target"]) for row in rows] == [_BODY]
    assert [str(row["callee"]) for row in rows] == [
        _MODULE + method_descriptor(_CALLER, "lambda$run$0", _VOID_JVM)
    ]


@pytest.mark.pins("call_edges.a-lambda-site-creating-no-body-is-no-edge")
def test_a_lambda_site_naming_no_body_contributes_no_edge(hand_built):
    """The near-miss for the same branch. The extractor writes
    `implementation` only where the bootstrap names a body; a site without one
    is some other use of `invokedynamic` — string concatenation is the common
    one — whose bootstrap is a compiler artifact rather than a call the program
    makes. Reading the missing value anyway does not leave it missing: it
    becomes an edge whose target is the four-character text `None`, a symbol no
    fact ever declared, once per concatenated string in the module.

    The positive control is ordinal 1 in the same workspace."""
    assert [row["ordinal"] for row in hand_built] == [0, 1]


@pytest.mark.pins("call_edges.a-callee-with-no-body-read-is-still-a-row")
def test_a_call_into_a_third_party_is_written_as_a_row(hand_built):
    """**The boundary is a row, and that is the whole difference between "this
    call leaves the module" and "this method makes no calls".** Drop the row
    and a walk sees a caller with fewer edges than it has call sites: the trace
    is silently shorter, every third-party terminal disappears from it, and the
    output cannot be told apart from a method that really does nothing.

    The positive control is the lambda edge in the same workspace, which is a
    row with a callee."""
    rows = [row for row in hand_built if row["ordinal"] == 0]
    assert [row["callee"] for row in rows] == [None]
    assert [str(row["target"]) for row in rows] == [
        _OWNER + "send(" + disambiguator_of(_VOID_JVM) + ")."
    ]
    assert [row for row in hand_built if row["callee"] is not None]


def test_every_hand_built_symbol_is_module_prefixed():
    """The rule this half of the file exists to keep. A fixture that drifts
    back into the bare space stops testing the thing that broke twice, and it
    does so silently — every assertion above would still pass."""
    for fact in (_declared(_CALLER, "run"), _declared(_CALLER, "lambda$run$0")):
        assert str(fact.symbol).startswith(_MODULE)
        assert bare_descriptor(str(fact.symbol)) != str(fact.symbol)
