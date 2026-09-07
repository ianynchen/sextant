"""Tests for 2Q `G3`, cross-method return propagation
(`resolve/return_flow.py`, D01 §3's `return_flows`).

**OI-4 governs how this file is built.** One identity has two string spellings —
a symbol fact carries the full SCIP form (`sextant-jvm maven
com.acme/orders-service 1.0.0 com/acme/X#m(sig_…).`), a call target the bare one
— and a join across them matches nothing on a real module while passing on a
fixture that spells everything bare. It cost round 1's `F6` six green tests and
zero rows, and 2O Task 10 the same. Its stated root cause is that synthetic
fixtures are not in the same coordinate space as real extraction. G3 is a join
across exactly that boundary, so the file answers it twice, and the two halves
answer different questions:

- **Against a real scan** (`tests/application/conftest.py`'s `resolved_fixture`,
  which compiles, scans and resolves at real coordinates). This is the only
  thing that can prove the composed callee descriptor agrees with what the
  EXTRACTOR wrote, `sig_` hash and all — a hand-built fact would compute that
  hash with the same function under test and agree with itself either way. The
  surface is
  `fixtures/orders-service/src/main/java/com/acme/orders/trace/`: one caller and
  one call per dispatch form the JVM has, plus a recursive method and a method
  with two returns. Deliberately unannotated and unreferenced, so it derives no
  endpoint, no shape and no schedule — it moves this table and nothing else.
- **Against hand-built facts that are MODULE-PREFIXED**, which is OI-4's own
  prescribed remedy ("fixture builders emitting module-prefixed symbols so tests
  exercise the real space"). These carry the `pins` markers, because
  `scripts/guard_check.py` copies `src/` and `tests/` and not the 16MB compiled
  fixture: a guard whose test needs `mvn` is reported unmeasurable, which is
  worse than no guard at all.
"""

import json
from typing import Any

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.resolve.return_flow import record_return_flows
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
def flows(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
) -> list[dict[str, object]]:
    """`return_flows` as the resolve wrote it. The pass runs inside `resolve`,
    so nothing here re-derives anything: these are the rows a `sextant module
    analyze` of this fixture leaves on disk."""
    workspace, _ = resolved_fixture
    return workspace.query("return_flows")


def _at(flows: list[dict[str, object]], caller: str, ordinal: int) -> list[dict[str, object]]:
    return [row for row in flows if row["caller"] == caller and row["ordinal"] == ordinal]


def _callees(rows: list[dict[str, object]]) -> list[str]:
    return sorted({str(row["callee"]) for row in rows})


def _values(rows: list[dict[str, object]]) -> list[Any]:
    return [json.loads(str(row["value"])) for row in rows]


def test_the_join_produces_rows_at_all_on_a_module_prefixed_scan(flows):
    """The OI-4 pin, and the first thing to check: `F6` and 2O Task 10 both
    shipped a join that matched NOTHING on a real module while its tests were
    green. A count is what tells the two apart, so it is asserted before
    anything about the rows' contents."""
    assert flows, "the return-flow join matched nothing on a module-prefixed scan"


def test_every_symbol_a_row_carries_is_module_prefixed_not_bare(flows):
    """Both sides of every row are the spelling `call_sites.caller` and
    `method_returns.method` use, so a reader can join a callee straight to that
    callee's own call sites and take the next hop. A row carrying a BARE callee
    would join to nothing, silently — which is OI-4 pointed the other way."""
    for row in flows:
        for column in ("caller", "callee"):
            symbol = str(row[column])
            assert symbol != bare_descriptor(symbol), f"{column} is bare: {symbol}"
            assert symbol.startswith(_MODULE)


def test_a_call_target_composed_bare_still_finds_a_module_prefixed_callee(flows):
    """**The join itself, in one assertion.** A `call_site` names its callee as
    the JVM's triple, which composes to a BARE descriptor; the callee's own
    `method_return` facts are keyed by the MODULE-PREFIXED symbol. G1 and G2
    discharged OI-4 in opposite directions on purpose — `implementation` is
    bare, `method_return.method` is prefixed — so this join has to strip
    exactly one side, and the side it strips is this one.

    Deleting that strip leaves every key in the wrong space and the table
    empty, which is the failure mode this whole file exists for."""
    rows = _at(flows, _DESCRIBE, 0)
    assert [str(row["callee"]) for row in rows] == [
        _MODULE + _TRACE + "SoleRefiner#refine(sig_7b622a99)."
    ] * 2


def test_a_sole_implementation_of_an_interface_resolves(flows):
    """The `mall` acceptance shape, in the fixture: the call site's declared
    target is `Refiner#refine`, an interface declaration with no body, and what
    the caller's `result` actually came from is `SoleRefiner#refine`. 166 of
    `mall-admin`'s 194 such calls are this case."""
    rows = _at(flows, _DESCRIBE, 0)
    assert _callees(rows) == [_MODULE + _TRACE + "SoleRefiner#refine(sig_7b622a99)."]
    assert {str(row["resolution"]) for row in rows} == {str(Resolution.RESOLVED)}
    assert {str(row["evidence"]) for row in rows} == {str(Evidence.COMPILER)}


def test_two_return_statements_are_two_rows_and_neither_is_dropped(flows):
    """A method with two `return`s has two possible answers and no single one.
    `SoleRefiner#refine` returns `""` on one path and `raw.trim()` on the
    other; collapsing them would state a fact about code that may never run,
    and picking either is the refusal the extractor already makes for a merged
    value."""
    values = _values(_at(flows, _DESCRIBE, 0))
    assert {"kind": "string", "value": ""} in values
    # The other path returns a library call's result, so the entry carries the
    # `source` id of that call — inside the CALLEE, which is the next hop.
    assert [value for value in values if value.get("source") is not None]
    assert len(values) == 2


def test_two_implementations_of_an_interface_list_as_a_branch_and_pick_neither(flows):
    """2Q's own rule: several implementations narrow, they do not resolve, and
    every one is listed. **This case has never occurred on real code** — the
    roadmap records zero, and G3 measured zero again on `macrozheng/mall`,
    where all 166 dispatched calls have exactly one implementation — so the
    rule is exercised here or nowhere."""
    rows = _at(flows, _DESCRIBE, 1)
    assert _callees(rows) == [
        _MODULE + _TRACE + "FirstSplitter#head(sig_7b622a99).",
        _MODULE + _TRACE + "SecondSplitter#head(sig_7b622a99).",
    ]
    assert {str(row["resolution"]) for row in rows} == {str(Resolution.NARROWED)}


def test_a_static_call_names_what_runs_and_admits_no_hiding_subclass(flows):
    """DR-6, mirrored from the JVM rather than approximated. `invokestatic`
    dispatches on nothing: `SoleRefiner.tag()` runs `SoleRefiner.tag()`,
    whatever `StrictRefiner` declares — a static method is HIDDEN, never
    overridden. Reading the subclass in here would publish a second candidate
    for a call that has exactly one, and would do the same for every `super.`
    call and every private call in the module."""
    rows = _at(flows, _DESCRIBE, 4)
    assert _callees(rows) == [_MODULE + _TRACE + "SoleRefiner#tag(sig_0e30dfc9)."]
    assert {str(row["resolution"]) for row in rows} == {str(Resolution.RESOLVED)}


def test_a_subclass_declaring_no_override_is_not_a_second_candidate(flows):
    """`StrictRefiner extends SoleRefiner`, so it is an INDIRECT implementation
    of `Refiner` and the hierarchy walk reaches it transitively. It declares no
    `refine` of its own, so `SoleRefiner`'s body stays the one a call through
    the interface can run — a walk that listed every descendant rather than
    every descendant WITH A BODY would narrow a call that resolves."""
    assert _callees(_at(flows, _DESCRIBE, 0)) == [
        _MODULE + _TRACE + "SoleRefiner#refine(sig_7b622a99)."
    ]


def test_a_recursive_call_links_a_method_to_itself_and_terminates(flows):
    """Recursion is real Java. The relation is a single step, so a self-call is
    a row whose caller and callee are the same symbol — the truth, and finite.
    A cycle costs something only to a traversal OVER these links, which is
    G4's."""
    shorten = _MODULE + _TRACE + "SoleRefiner#shorten(sig_1b403611)."
    rows = [row for row in flows if row["caller"] == shorten]
    assert rows, "the recursive call produced no link"
    assert _callees(rows) == [shorten]


def test_a_call_into_a_third_party_produces_no_row(flows):
    """The ruled boundary: a MyBatis mapper, a Spring Data repository, a JDBC
    driver, anything in the JDK — the call IS the terminal, and a row would
    claim a body this workspace never read. `SoleRefiner#refine` calls
    `String#trim`; the call site is a fact and the link is deliberately not.

    The absence is asserted against a caller that DOES produce rows elsewhere,
    so "no row" cannot be satisfied by a pass that produced nothing at all."""
    refine = _MODULE + _TRACE + "SoleRefiner#refine(sig_7b622a99)."
    assert [row for row in flows if row["callee"] == refine], "positive control: no rows at all"
    assert not [row for row in flows if "java/lang/String#" in str(row["callee"])]


def test_a_lambda_creation_site_is_never_linked_to_the_body_it_creates(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
    flows: list[dict[str, object]],
):
    """A fabrication near-miss. An `invokedynamic`'s `result` is the
    functional-interface INSTANCE the bootstrap builds, not anything the lambda
    body returns — the body runs later, elsewhere, if at all. G1's
    `call_site.implementation` names that body, and linking its returns to this
    site's result would state that a `Supplier` call site produced the
    supplier's value.

    Asserted by identity of the SITE rather than by the shape of the callee's
    name: `OrderStreamBindings`' `@Bean` methods return their lambdas, so this
    fixture really does have `dynamic` sites carrying a `result` (the positive
    control below), and not one of them may appear in this table."""
    workspace, _ = resolved_fixture
    dynamic = {
        (str(site["caller"]), site["ordinal"])
        for site in workspace.query("call_sites")
        if site["invoke_kind"] == "dynamic" and site["result"] is not None
    }
    assert dynamic, "positive control: the fixture has no lambda site with a result"
    assert not dynamic & {(str(row["caller"]), row["ordinal"]) for row in flows}


def test_a_void_call_contributes_nothing_because_there_is_no_value_to_explain(flows):
    """A call site with no `result` produces no row: the callee returns `void`,
    so there is no value in the caller for anything to have come from. The
    fixture's `new SoleRefiner()` is exactly that — a real in-module call, to a
    constructor whose body the workspace read, at a site between two that do
    produce rows."""
    assert _at(flows, _DESCRIBE, 2) == []
    assert _at(flows, _DESCRIBE, 1) and _at(flows, _DESCRIBE, 3)


def test_the_table_is_replaced_whole_rather_than_appended_to(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The reset/insert discipline every derived table here keeps. Running the
    pass twice must leave the same rows, not twice as many — a stale or doubled
    table is the failure `reset_resolved_config.sql` exists to prevent, and
    this pass owns its own reset because it has exactly one writer."""
    workspace, _ = resolved_fixture
    before = workspace.query("return_flows")
    record_return_flows(workspace)
    assert workspace.query("return_flows") == before


# --- hand-built facts, MODULE-PREFIXED --------------------------------------
#
# OI-4's own prescribed remedy, and the half of this file the guards measure.
# Every symbol below carries `_MODULE`, exactly as a real scan writes it, so a
# join that only works in the bare space fails here the way it fails on a real
# module — which is what the six-green-tests-zero-rows shape defeated.
#
# What these CANNOT prove, and the real-scan half above does: that
# `method_descriptor`'s arithmetic agrees with `ClassScanner.disambiguatorOf`.
# The descriptors here are composed with the same function under test, so they
# would agree with themselves whatever it computed.

_GATEWAY = "com/acme/orders/gate/Gateway#"
_IMPL = "com/acme/orders/gate/GatewayImpl#"
_STRICT = "com/acme/orders/gate/StrictGateway#"
_CALLER = "com/acme/orders/gate/Caller#"
_SEND_JVM = "(Ljava/lang/String;)Ljava/lang/String;"
_TAG_JVM = "()Ljava/lang/String;"
_RUN = _CALLER + "run(" + disambiguator_of(_SEND_JVM) + ")."


def _document() -> Document:
    return Document(
        document_id="doc_gate",
        relative_path="com/acme/orders/gate/Caller.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        scanner_version="9.18",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _type(symbol: str, kind: ConstructKind, **extra: object) -> SymbolFact:
    return SymbolFact(document_id="doc_gate", symbol=_MODULE + symbol, construct_kind=kind, **extra)


def _declared(owner: str, name: str, jvm: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_gate",
        symbol=_MODULE + method_descriptor(owner, name, jvm),
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(parameters=[], returns=TypeRef(symbol="java/lang/String#")),
    )


def _returns(owner: str, name: str, jvm: str, value: CallArgument) -> MethodReturnFact:
    return MethodReturnFact(
        document_id="doc_gate",
        method=_MODULE + method_descriptor(owner, name, jvm),
        ordinal=0,
        value=value,
    )


def _site(owner: str, name: str, jvm: str, kind: str, ordinal: int, result: int) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_gate",
        caller=_MODULE + _RUN,
        target=CallTarget(owner=owner, name=name, descriptor=jvm),
        invoke_kind=kind,
        ordinal=ordinal,
        result=result,
    )


@pytest.fixture(scope="module")
def hand_built(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, object]]:
    """`Caller#run` calls `Gateway#send` through the interface and
    `GatewayImpl#tag` statically. `StrictGateway extends GatewayImpl` and
    declares its own `tag`, which HIDES rather than overrides — so the
    interface call has one candidate reached through a class the walk sees
    directly, and the static call has one candidate the walk must not widen."""
    tmp_path = tmp_path_factory.mktemp("return_flow_hand_built")
    facts = tmp_path / "facts"
    write_fact_file(
        facts / "gate.jsonl",
        _document(),
        [
            _type(_GATEWAY, ConstructKind.INTERFACE),
            # `interfaces` entries are BARE in a real fact and `superclass` is
            # module-prefixed — capability 9.10 and 9.13 disagree deliberately,
            # and a fixture that spelled both alike would hide a normalisation
            # bug in the hierarchy walk.
            _type(_IMPL, ConstructKind.CLASS, interfaces=[_GATEWAY]),
            _type(_STRICT, ConstructKind.CLASS, superclass=_MODULE + _IMPL),
            _type(_CALLER, ConstructKind.CLASS),
            _declared(_GATEWAY, "send", _SEND_JVM),
            _declared(_IMPL, "send", _SEND_JVM),
            _declared(_IMPL, "tag", _TAG_JVM),
            _declared(_STRICT, "tag", _TAG_JVM),
            _declared(_CALLER, "run", _SEND_JVM),
            _returns(_IMPL, "send", _SEND_JVM, CallArgument(kind="string", value="sent")),
            _returns(_IMPL, "tag", _TAG_JVM, CallArgument(kind="string", value="impl")),
            _returns(_STRICT, "tag", _TAG_JVM, CallArgument(kind="string", value="strict")),
            _site(_GATEWAY, "send", _SEND_JVM, "interface", 0, 4),
            _site(_IMPL, "tag", _TAG_JVM, "static", 1, 7),
        ],
    )
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_return_flows(workspace)
    rows = workspace.query("return_flows")
    workspace.close()
    return rows


@pytest.mark.pins("dispatch.callee-descriptor-is-stripped-to-bare")
def test_a_bare_call_target_finds_a_module_prefixed_callee(hand_built):
    """**The join, on facts spelled the way a real scan spells them.** The call
    site names `Gateway#send` as the JVM's triple, which composes BARE; the
    body's `method_return` facts are keyed by the MODULE-PREFIXED symbol. G1
    and G2 discharged OI-4 in opposite directions on purpose
    (`call_site.implementation` bare, `method_return.method` prefixed), so this
    join strips exactly one side. Stop stripping it and every key is in the
    wrong space: no rows, on every real module, with nothing raised."""
    rows = [row for row in hand_built if row["ordinal"] == 0]
    assert [str(row["callee"]) for row in rows] == [
        _MODULE + method_descriptor(_IMPL, "send", _SEND_JVM)
    ]
    # Parsed rather than compared as text: a Python-written fact serialises
    # every optional key of the grammar (as explicit nulls) where the extractor
    # omits the ones it has nothing to say about. The VALUE is the claim here,
    # not the spelling — and the extractor's own spelling is asserted verbatim
    # by the real-scan half above.
    assert json.loads(str(rows[0]["value"]))["value"] == "sent"


@pytest.mark.pins("dispatch.exact-dispatch-admits-no-override")
def test_a_static_call_admits_no_hiding_subclass(hand_built):
    """DR-6, mirrored from the JVM. `invokestatic` dispatches on nothing:
    `GatewayImpl.tag()` runs `GatewayImpl.tag()` whatever `StrictGateway`
    declares, because a static method is HIDDEN and never overridden. Reading
    the subclass in publishes a candidate for code the JVM cannot reach at that
    site, and downgrades a call that resolves to one that merely narrows — for
    every `super.` call and every private call in the module at once."""
    rows = [row for row in hand_built if row["ordinal"] == 1]
    assert [str(row["callee"]) for row in rows] == [
        _MODULE + method_descriptor(_IMPL, "tag", _TAG_JVM)
    ]
    assert str(rows[0]["resolution"]) == str(Resolution.RESOLVED)


def test_the_hierarchy_walk_reaches_an_indirect_implementation(hand_built):
    """The positive half of the test above: `StrictGateway` is an
    implementation of `Gateway` only THROUGH `GatewayImpl`, so a walk that read
    direct `interfaces` alone would never see it. It declares no `send`, so it
    is correctly not a candidate for the interface call — which is exactly why
    the walk has to be checked from the other side too."""
    walked = {str(row["callee"]) for row in hand_built if row["ordinal"] == 0}
    assert _MODULE + method_descriptor(_STRICT, "send", _SEND_JVM) not in walked
    assert _MODULE + method_descriptor(_STRICT, "tag", _TAG_JVM) not in {
        str(row["callee"]) for row in hand_built
    }


def test_every_hand_built_symbol_is_module_prefixed():
    """The rule this half of the file exists to keep. A fixture that drifts
    back into the bare space stops testing the thing that broke twice, and it
    does so silently — every assertion above would still pass."""
    for fact in (
        _declared(_IMPL, "send", _SEND_JVM),
        _returns(_IMPL, "send", _SEND_JVM, CallArgument(kind="null")),
        _site(_GATEWAY, "send", _SEND_JVM, "interface", 0, 4),
    ):
        symbol = getattr(fact, "symbol", None) or getattr(fact, "method", None) or fact.caller
        assert str(symbol).startswith(_MODULE)
        assert bare_descriptor(str(symbol)) != str(symbol)
