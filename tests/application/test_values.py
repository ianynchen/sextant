"""Tests for the backward value walk (`resolve/values.py`, spec 2026-09-22 §1b–§1d).

**Hand-built facts, MODULE-PREFIXED, for OI-4's reason** — the one
`test_return_flow.py` and `test_call_edges.py` both state at length: one identity
has two string spellings, a call target composes BARE and a body's symbol carries
its module coordinates, and a join across the two matches nothing on a real module
while passing on a fixture that spells everything alike. The walk crosses that
boundary at every `bound_to_parameter` and every `returned_by` edge, so every
symbol below is spelled the way a real scan spells it.

The two tables the edge query reads are built by the passes that own them
(`record_return_flows`, `record_call_edges`) rather than inserted by hand: a
fixture that wrote `return_flows` itself would prove the walk agrees with the test
author about what a return flow is, which is not the question.

**The M-1 test is first on purpose** (spec §0c). It is why the primitive is a path,
and nothing else in this file would catch a regression to per-position resolution:
every other test here has one slot, and a per-position walk answers those exactly
as a per-path one does.
"""

from pathlib import Path
from typing import Any

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.values import (
    _REASONS,
    RECEIVER,
    Binding,
    resolve_site,
    value_index,
)
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Fact,
    MethodReturnFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_PKG = "com/acme/orders/values/"

# The sink every fixture site calls: deliberately NOT declared, so it is the
# third-party boundary `call_edges` draws with a NULL callee. What the walk
# answers is about the site's ARGUMENTS, and a declared sink would add bodies
# that say nothing about them.
_REGISTRY = _PKG + "Registry#"
_ONE = "(Ljava/lang/String;)V"
_PAIR = "(Ljava/lang/String;Ljava/lang/Class;)V"
_MANY = "([Ljava/lang/String;)V"
_MAKES_STRING = "()Ljava/lang/String;"
_MAKES_OBJECT = "()Ljava/lang/Object;"
_TAKES_STRING = "(Ljava/lang/String;)V"

_REGISTRAR = _PKG + "Registrar#"
_CALLER = _PKG + "Caller#"
_NAMES = _PKG + "Names#"
_PUBLISHER = _PKG + "Publisher#"
_ARRAYS = _PKG + "Arrays#"
_MUTATOR = _PKG + "Mutator#"
_BUFFER = _PKG + "Buffer#"
_BINDER = _PKG + "Binder#"
_ENTRY = _PKG + "Entry#"
_OUTSIDE = _PKG + "Outside#"
_UNREAD = _PKG + "Unread#"
_LOOP = _PKG + "Loop#"
_ASSEMBLER = _PKG + "Assembler#"
_RECEIVING = _PKG + "Receiving#"
_FACTORY = _PKG + "Factory#"
_DEEP = _PKG + "Deep#"
_DIAMOND = _PKG + "Diamond#"

_ORDER_WORKER = _PKG + "OrderWorker#"
_BILLING_WORKER = _PKG + "BillingWorker#"
_REGISTRY_IMPL = _PKG + "RegistryImpl#"


def _symbol(owner: str, name: str, jvm: str) -> str:
    """A method's symbol as a real scan writes it: module coordinates and all."""
    return _MODULE + method_descriptor(owner, name, jvm)


def _document() -> Document:
    return Document(
        document_id="doc_values",
        relative_path="com/acme/orders/values/Registrar.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:v",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _type(owner: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_values", symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS
    )


def _declared(owner: str, name: str, jvm: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_values",
        symbol=_symbol(owner, name, jvm),
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(parameters=[], returns=TypeRef(symbol="java/lang/String#")),
    )


def _returns(owner: str, name: str, jvm: str, ordinal: int, value: CallArgument) -> Fact:
    return MethodReturnFact(
        document_id="doc_values",
        method=_symbol(owner, name, jvm),
        ordinal=ordinal,
        value=value,
    )


def _void(owner: str, name: str, jvm: str) -> Fact:
    """The `method_return` fact a method that hands nothing back still carries — one per
    return instruction, D00 §5 — and the reason it matters here: `dispatch` reads this
    table to answer "did we read a body", so a callee without one is indistinguishable
    from a third-party call and binds no parameter at all."""
    return MethodReturnFact(
        document_id="doc_values", method=_symbol(owner, name, jvm), ordinal=0, value=None
    )


def _site(
    caller: str,
    ordinal: int,
    target: tuple[str, str, str],
    *,
    kind: str = "static",
    arguments: list[CallArgument] | None = None,
    result: int | None = None,
    receiver: int | None = None,
    receiver_parameter: int | None = None,
) -> Fact:
    owner, name, jvm = target
    return CallSiteFact(
        document_id="doc_values",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=jvm),
        invoke_kind=kind,
        ordinal=ordinal,
        result=result,
        receiver=receiver,
        receiver_parameter=receiver_parameter,
        arguments=arguments or [],
    )


_PAIR_TARGET = (_REGISTRY, "pair", _PAIR)
_ONE_TARGET = (_REGISTRY, "one", _ONE)
_MANY_TARGET = (_REGISTRY, "many", _MANY)


def _facts() -> list[Fact]:
    """One fact set, one arm per rule the walk implements.

    Every method that is WALKED INTO is declared, because `call_edges` and
    `return_flows` only name a body this workspace read — which is the same
    boundary the walk reports as `external`, and two of the arms below rely on
    a producer that was deliberately left undeclared.
    """
    register = _symbol(_REGISTRAR, "register", _PAIR)
    facts: list[Fact] = [
        _type(owner)
        for owner in (
            _REGISTRAR,
            _CALLER,
            _NAMES,
            _PUBLISHER,
            _ARRAYS,
            _MUTATOR,
            _BINDER,
            _ENTRY,
            _OUTSIDE,
            _UNREAD,
            _LOOP,
            _ASSEMBLER,
            _RECEIVING,
            _FACTORY,
            _DEEP,
            _DIAMOND,
        )
    ]
    facts += [
        # M-1: one helper, two call sites, two values per call.
        _declared(_REGISTRAR, "register", _PAIR),
        _void(_REGISTRAR, "register", _PAIR),
        _declared(_CALLER, "run", "()V"),
        _site(
            register,
            0,
            _PAIR_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="parameter", value=1),
            ],
        ),
        _site(
            _symbol(_CALLER, "run", "()V"),
            0,
            (_REGISTRAR, "register", _PAIR),
            arguments=[
                CallArgument(kind="string", value="orders"),
                CallArgument(kind="class", symbol=_ORDER_WORKER),
            ],
        ),
        _site(
            _symbol(_CALLER, "run", "()V"),
            1,
            (_REGISTRAR, "register", _PAIR),
            arguments=[
                CallArgument(kind="string", value="billing"),
                CallArgument(kind="class", symbol=_BILLING_WORKER),
            ],
        ),
        # Several returns in one callee.
        _declared(_NAMES, "pick", _MAKES_STRING),
        _returns(_NAMES, "pick", _MAKES_STRING, 0, CallArgument(kind="string", value="orders")),
        _returns(
            _NAMES, "pick", _MAKES_STRING, 1, CallArgument(kind="string", value="orders-fast")
        ),
        _declared(_NAMES, "one", _MAKES_STRING),
        _returns(_NAMES, "one", _MAKES_STRING, 0, CallArgument(kind="string", value="solo")),
        _declared(_PUBLISHER, "publish", "()V"),
        _site(_symbol(_PUBLISHER, "publish", "()V"), 0, (_NAMES, "pick", _MAKES_STRING), result=5),
        _site(
            _symbol(_PUBLISHER, "publish", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        # The array rule (§1c), both ways round.
        _declared(_ARRAYS, "listed", "()V"),
        _site(
            _symbol(_ARRAYS, "listed", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="string", value="alpha"),
                        CallArgument(kind="string", value="beta"),
                    ],
                )
            ],
        ),
        _declared(_ARRAYS, "partly", "()V"),
        _site(
            _symbol(_ARRAYS, "partly", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="string", value="alpha"),
                        CallArgument(kind="unresolved"),
                    ],
                )
            ],
        ),
        # A value handed to a method that might mutate it, and the same shape
        # with nothing in between.
        _declared(_MUTATOR, "escaped", "()V"),
        _site(_symbol(_MUTATOR, "escaped", "()V"), 0, (_NAMES, "one", _MAKES_STRING), result=7),
        _site(
            _symbol(_MUTATOR, "escaped", "()V"),
            1,
            (_BUFFER, "append", _TAKES_STRING),
            kind="virtual",
            receiver=7,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        _site(
            _symbol(_MUTATOR, "escaped", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=7)],
        ),
        _declared(_MUTATOR, "kept", "()V"),
        _site(_symbol(_MUTATOR, "kept", "()V"), 0, (_NAMES, "one", _MAKES_STRING), result=7),
        _site(
            _symbol(_MUTATOR, "kept", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=7)],
        ),
        # A binding read.
        _declared(_BINDER, "read", "()V"),
        _site(
            _symbol(_BINDER, "read", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="field", symbol=_BINDER + "name.")],
        ),
        # A parameter nothing in this module binds.
        _declared(_ENTRY, "handle", _TAKES_STRING),
        _site(
            _symbol(_ENTRY, "handle", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # A value from a body this workspace never read.
        _declared(_OUTSIDE, "use", "()V"),
        _site(
            _symbol(_OUTSIDE, "use", "()V"),
            0,
            (_PKG + "Third#", "make", _MAKES_STRING),
            kind="virtual",
            result=9,
        ),
        _site(
            _symbol(_OUTSIDE, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=9)],
        ),
        # Values the grammar names nothing for.
        _declared(_UNREAD, "use", "()V"),
        _site(
            _symbol(_UNREAD, "use", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved")],
        ),
        _site(
            _symbol(_UNREAD, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(kind="lambda", symbol=_UNREAD + "body(sig_0).", captures=0, source=3)
            ],
        ),
        _site(
            _symbol(_UNREAD, "use", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="null")],
        ),
        # A zero-length varargs call: the empty element list is the FACT (D00 §5).
        _declared(_ARRAYS, "none", "()V"),
        _site(
            _symbol(_ARRAYS, "none", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="array", elements=[])],
        ),
        # Two methods that hand each other the same parameter.
        _declared(_LOOP, "ping", _TAKES_STRING),
        _void(_LOOP, "ping", _TAKES_STRING),
        _declared(_LOOP, "pong", _TAKES_STRING),
        _void(_LOOP, "pong", _TAKES_STRING),
        _site(
            _symbol(_LOOP, "ping", _TAKES_STRING),
            0,
            (_LOOP, "pong", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_LOOP, "ping", _TAKES_STRING),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_LOOP, "pong", _TAKES_STRING),
            0,
            (_LOOP, "ping", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # An address the code assembles.
        _declared(_ASSEMBLER, "call", "()V"),
        _site(
            _symbol(_ASSEMBLER, "call", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", value="/orders/{}", source=4)],
        ),
        # A receiver produced by a call, which is a slot like any other.
        _declared(_FACTORY, "make", _MAKES_OBJECT),
        _returns(
            _FACTORY,
            "make",
            _MAKES_OBJECT,
            0,
            CallArgument(kind="instance", symbol=_REGISTRY_IMPL),
        ),
        _declared(_RECEIVING, "use", "()V"),
        _site(_symbol(_RECEIVING, "use", "()V"), 0, (_FACTORY, "make", _MAKES_OBJECT), result=3),
        _site(
            _symbol(_RECEIVING, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            receiver=3,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        # Four methods deep, because there is no cap (§3a).
        _declared(_DEEP, "go", "()V"),
        _declared(_DEEP, "one", _TAKES_STRING),
        _void(_DEEP, "one", _TAKES_STRING),
        _declared(_DEEP, "two", _TAKES_STRING),
        _void(_DEEP, "two", _TAKES_STRING),
        _declared(_DEEP, "three", _TAKES_STRING),
        _void(_DEEP, "three", _TAKES_STRING),
        _site(
            _symbol(_DEEP, "go", "()V"),
            0,
            (_DEEP, "one", _TAKES_STRING),
            arguments=[CallArgument(kind="string", value="deep")],
        ),
        _site(
            _symbol(_DEEP, "one", _TAKES_STRING),
            0,
            (_DEEP, "two", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DEEP, "two", _TAKES_STRING),
            0,
            (_DEEP, "three", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DEEP, "three", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # One position reached through two different wrappers — the shape that makes the
        # memo's KEY observable. `mid` is called by `left` and by `right`, both of which
        # `top` calls, so `top`'s own parameter is resolved twice: once on the path
        # through `left` and once on the path through `right`.
        _declared(_DIAMOND, "start", "()V"),
        _declared(_DIAMOND, "top", _TAKES_STRING),
        _void(_DIAMOND, "top", _TAKES_STRING),
        _declared(_DIAMOND, "left", _TAKES_STRING),
        _void(_DIAMOND, "left", _TAKES_STRING),
        _declared(_DIAMOND, "right", _TAKES_STRING),
        _void(_DIAMOND, "right", _TAKES_STRING),
        _declared(_DIAMOND, "mid", _TAKES_STRING),
        _void(_DIAMOND, "mid", _TAKES_STRING),
        _site(
            _symbol(_DIAMOND, "start", "()V"),
            0,
            (_DIAMOND, "top", _TAKES_STRING),
            arguments=[CallArgument(kind="string", value="alpha")],
        ),
        _site(
            _symbol(_DIAMOND, "top", _TAKES_STRING),
            0,
            (_DIAMOND, "left", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "top", _TAKES_STRING),
            1,
            (_DIAMOND, "right", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "left", _TAKES_STRING),
            0,
            (_DIAMOND, "mid", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "right", _TAKES_STRING),
            0,
            (_DIAMOND, "mid", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "mid", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
    ]
    return facts


@pytest.fixture(scope="module")
def walked(tmp_path_factory: pytest.TempPathFactory) -> DuckDbWorkspace:
    """The workspace, with the two derived tables the edge query reads built by
    the passes that own them. Handed back OPEN — every test reads through it."""
    tmp_path = tmp_path_factory.mktemp("values")
    facts = tmp_path / "facts"
    write_fact_file(facts / "values.jsonl", _document(), _facts())
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_return_flows(workspace)
    record_call_edges(workspace)
    return workspace


def _at(workspace: DuckDbWorkspace, method: str, ordinal: int) -> dict[str, Any]:
    rows = [
        row
        for row in workspace.query("call_sites")
        if row["caller"] == method and row["ordinal"] == ordinal
    ]
    assert len(rows) == 1, f"no single site at {method}@{ordinal}"
    return dict(rows[0])


def _bindings(workspace: DuckDbWorkspace, method: str, ordinal: int) -> list[Binding]:
    return resolve_site(workspace, _at(workspace, method, ordinal))


def _reasons(bindings: list[Binding], slot: int | str = 0) -> list[str | None]:
    return [binding.slots[slot].reason for binding in bindings]


def test_a_helper_called_twice_yields_two_paths_not_four_combinations(walked):
    """**Spec §0c M-1, and the reason the primitive is a path.** `register("orders",
    OrderWorker)` and `register("billing", BillingWorker)` reach ONE site inside
    `register`. Resolving its two slots INDEPENDENTLY yields 2x2 = four pairs, two of
    which no code path produces — recorded at `resolved` and indistinguishable from an
    observation, which is the cardinal sin this repository exists not to commit.

    Per path it is two bindings, and each binding's slots agree because they came from
    the same caller. Memoise on the position alone and this test fails with four rows;
    nothing else in this file would notice."""
    bindings = _bindings(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    assert [(b.slots[0].value, b.slots[1].value) for b in bindings] == [
        ("orders", _ORDER_WORKER),
        ("billing", _BILLING_WORKER),
    ]


def test_each_binding_names_the_calling_context_it_came_from(walked):
    """§1b: a binding carries the path, so a reader can say WHICH call produced the row
    — and two bindings that differ only in their values would be two rows nobody can
    tell apart when one of them turns out to be wrong."""
    bindings = _bindings(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    assert [b.path for b in bindings] == [
        (f"{_symbol(_CALLER, 'run', '()V')}@0",),
        (f"{_symbol(_CALLER, 'run', '()V')}@1",),
    ]


def test_several_returns_in_a_callee_are_several_paths(walked):
    """`method_return` keeps several returns as several facts on the stated ground that
    picking one would be a fact about code that may never run. The walk keeps them as
    several bindings for the same reason (§1c)."""
    bindings = _bindings(walked, _symbol(_PUBLISHER, "publish", "()V"), 1)
    assert sorted(str(b.slots[0].value) for b in bindings) == ["orders", "orders-fast"]
    assert len({b.path for b in bindings}) == 2


def test_an_array_whose_every_element_is_written_branches_into_elements(walked):
    """The enumerable half of §1c's rule — D00's array rule, generalised: every index a
    distinct written constant yields elements, and each element is its own path.

    Paired with the test below on purpose (GUIDELINES §10): a walk that answered
    `non_enumerable` for every array would pass that one and fail this one."""
    bindings = _bindings(walked, _symbol(_ARRAYS, "listed", "()V"), 0)
    assert [b.slots[0].value for b in bindings] == ["alpha", "beta"]


def test_a_value_that_cannot_be_enumerated_is_one_unresolved_not_several_answers(walked):
    """The distinction §1c draws: several PATHS are several answers; one path whose value
    cannot be enumerated is ONE `unresolved`, with no element list at all.

    The shape here is the one the facts can state — an array the extractor read whose
    second element it could not name. A loop-built or branch-merged value arrives as an
    unread argument instead (the facts carry no "this was a loop" claim), and the walk
    answers `not_readable` there; `values.py` says so where it decides."""
    bindings = _bindings(walked, _symbol(_ARRAYS, "partly", "()V"), 0)
    assert _reasons(bindings) == ["non_enumerable"]
    assert [b.slots[0].value for b in bindings] == [None]


def test_a_value_a_method_might_have_mutated_before_use_is_unresolved_escapes(walked):
    """§1d's `escapes`. Between the call that produced the value and the call that uses
    it there is a call ON the value, and nothing in the facts says what it wrote."""
    bindings = _bindings(walked, _symbol(_MUTATOR, "escaped", "()V"), 2)
    assert _reasons(bindings) == ["escapes"]


def test_the_same_chain_with_nothing_in_between_resolves(walked):
    """The positive paired with `escapes` (GUIDELINES §10): the rule declines above and
    must still fire here, or a walk that answered `escapes` for every produced value
    would look correct all the way down."""
    bindings = _bindings(walked, _symbol(_MUTATOR, "kept", "()V"), 1)
    assert [b.slots[0].value for b in bindings] == ["solo"]


def test_a_binding_read_is_unresolved_no_writer(walked):
    """§1d's `no_writer`, and Task 2's absent sixth edge seen from the other side: the
    walk asks `value_edges` for a writer, the query emits no `written_by` row until
    capability 9.19 gives it a fact, and the answer names what is missing rather than
    collapsing into the one word everything used to collapse into."""
    bindings = _bindings(walked, _symbol(_BINDER, "read", "()V"), 0)
    assert _reasons(bindings) == ["no_writer"]


def test_a_parameter_no_scanned_caller_binds_is_unresolved_external(walked):
    """§1d's `external`, on the crossing edge: nothing in this module calls
    `Entry#handle`, so whatever it is handed comes from outside what was scanned. That
    is a different statement from "the code branches", and a reader can act on it."""
    bindings = _bindings(walked, _symbol(_ENTRY, "handle", _TAKES_STRING), 0)
    assert _reasons(bindings) == ["external"]


def test_a_value_from_a_body_this_workspace_never_read_is_unresolved_external(walked):
    """§6: it does not cross the module boundary. The producer is a call into a type
    nothing scanned, which `call_edges` records with a NULL callee — 1,411 of 2,065
    value-producing sites on `mall-admin`, so this is the common case, not the corner."""
    bindings = _bindings(walked, _symbol(_OUTSIDE, "use", "()V"), 1)
    assert _reasons(bindings) == ["external"]


def test_a_value_the_facts_name_nothing_for_is_unresolved_not_readable(walked):
    """§1d's `not_readable`: the producer is there and its value cannot be named. Today
    every miss collapses into one word; this is the one that keeps that meaning, so the
    other five can mean something narrower."""
    bindings = _bindings(walked, _symbol(_UNREAD, "use", "()V"), 0)
    assert _reasons(bindings) == ["not_readable"]


def test_a_lambda_argument_answers_not_readable_rather_than_a_body_symbol(walked):
    """`value_edges.sql` rules on this in its `names_declaration` arm: a lambda names a
    BODY, not a declaration whose value can be identified, and a walk handed that symbol
    would have a method descriptor where it asked for a value."""
    bindings = _bindings(walked, _symbol(_UNREAD, "use", "()V"), 1)
    assert _reasons(bindings) == ["not_readable"]
    assert [b.slots[0].value for b in bindings] == [None]


def test_a_value_the_code_states_is_not_there_is_absent_rather_than_a_miss(walked):
    """`absent` (ruled 2026-09-23): the code STATES there is no value — an explicit null,
    and a zero-length varargs call. D00 §5 draws this line itself for the empty element
    list ("the empty list is the fact ... 'called with no values' is a different statement
    from 'the array could not be read'"), so answering `non_enumerable` there would call a
    known-empty thing ambiguous and contradict the facts it was read from.

    A resolved answer, not a reason: a consumer told `not_readable` would go looking for a
    value that is not there to be found."""
    for method, ordinal in (
        (_symbol(_UNREAD, "use", "()V"), 2),
        (_symbol(_ARRAYS, "none", "()V"), 0),
    ):
        bindings = _bindings(walked, method, ordinal)
        assert [(b.slots[0].kind, b.slots[0].value, b.slots[0].reason) for b in bindings] == [
            ("absent", None, None)
        ], f"{method}@{ordinal}"


def test_a_walk_that_returns_to_a_position_on_its_own_path_is_unresolved_cycle(walked):
    """§1d's `cycle`, which is also the termination proof: `ping` hands its parameter to
    `pong`, `pong` hands it back, and the walk answers rather than running forever."""
    bindings = _bindings(walked, _symbol(_LOOP, "ping", _TAKES_STRING), 1)
    assert _reasons(bindings) == ["cycle"]


def test_an_assembled_address_is_carried_verbatim_and_never_evaluated(walked):
    """§1b's `expression`, and §8.2's line: the template is what the facts carry, so the
    walk hands it back as written. It is never a `literal` — §6 keeps a computed string
    out of this repository — and a consumer reading literals sees nothing here."""
    bindings = _bindings(walked, _symbol(_ASSEMBLER, "call", "()V"), 0)
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [("expression", "/orders/{}")]
    assert _reasons(bindings) == [None]


def test_a_receiver_is_a_slot_like_any_other(walked):
    """§1b: one entry point, not two. The receiver is resolved by the same walk as an
    argument — here through the returns of the call that produced it — and a binding
    carries it under the one key that is not an index."""
    bindings = _bindings(walked, _symbol(_RECEIVING, "use", "()V"), 1)
    assert [b.slots[RECEIVER].value for b in bindings] == [_REGISTRY_IMPL]
    assert [b.slots[0].value for b in bindings] == ["x"]


def test_a_declaration_answers_with_a_symbol_that_no_reader_can_mistake_for_a_string(walked):
    """A class reference IS the value (`value_edges.sql`'s `names_declaration` arm), and
    the answer carries the symbol. It must not carry it as a `string` literal: a catalog
    reading a destination out of a slot would take `com/acme/…#` for an address, which is
    a fabrication of exactly the kind §7 says this work's whole risk is."""
    bindings = _bindings(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    kinds = {(b.slots[1].kind, b.slots[1].literal_kind) for b in bindings}
    assert kinds == {("literal", "symbol")}
    assert {(b.slots[0].kind, b.slots[0].literal_kind) for b in bindings} == {("literal", "string")}


def test_the_walk_follows_a_chain_as_deep_as_the_code_goes(walked):
    """§3a: no cap in v1, and Task 4's measurement is what decides whether one is ever
    needed. Four methods deep is past every "one hop" this codebase has ever declared —
    seven of them, in eighteen places (§0) — and the value still arrives."""
    bindings = _bindings(walked, _symbol(_DEEP, "three", _TAKES_STRING), 0)
    assert [b.slots[0].value for b in bindings] == ["deep"]
    assert [len(b.path) for b in bindings] == [3]


def test_one_position_reached_two_ways_keeps_the_two_paths_apart(walked):
    """**The memo's key, measured.** `mid` is reached through `left` and through `right`,
    and both wrappers are called by `top` — so `top`'s parameter is resolved twice, on two
    paths that disagree about which call reached `mid`.

    Memoise on the position ALONE and the second walk is handed the first one's answer,
    trail and all: both bindings then claim the path through `left`, which is a row
    asserting that a value arrived by a call it did not arrive by. That is M-1's
    fabrication one level down, and this is the only test here that sees it — the helper
    test above passes under a position-only memo, because there each position is resolved
    exactly once."""
    top = _symbol(_DIAMOND, "top", _TAKES_STRING)
    bindings = _bindings(walked, _symbol(_DIAMOND, "mid", _TAKES_STRING), 0)
    assert [b.path for b in bindings] == [
        (
            f"{_symbol(_DIAMOND, 'start', '()V')}@0",
            f"{top}@0",
            f"{_symbol(_DIAMOND, 'left', _TAKES_STRING)}@0",
        ),
        (
            f"{_symbol(_DIAMOND, 'start', '()V')}@0",
            f"{top}@1",
            f"{_symbol(_DIAMOND, 'right', _TAKES_STRING)}@0",
        ),
    ]
    assert [b.slots[0].value for b in bindings] == ["alpha", "alpha"]


def test_the_reasons_are_the_closed_set_the_design_declares(walked):
    """§1d is a CLOSED vocabulary, and §3a keeps `fan_out` and `depth` out of it until a
    measurement asks for them. A seventh word added here without that ruling is the thing
    this test exists to fail on."""
    assert set(_REASONS) == {
        "not_readable",
        "non_enumerable",
        "escapes",
        "no_writer",
        "external",
        "cycle",
    }


def test_an_index_built_once_answers_what_a_fresh_one_answers(walked):
    """§8.7: the walk reads five queries to build its index, and a caller resolving many
    positions builds it once. The two paths must answer identically, or the fast one is a
    different operation wearing the same name."""
    index = value_index(walked)
    site = _at(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    assert resolve_site(walked, site, index) == resolve_site(walked, site)


def test_every_hand_built_symbol_is_module_prefixed():
    """OI-4's own remedy, asserted rather than trusted: a fixture that spelled a caller
    or a callee bare would exercise a join this walk does not actually perform."""
    for fact in _facts():
        for symbol in (getattr(fact, "symbol", None), getattr(fact, "caller", None)):
            if symbol is not None:
                assert str(symbol).startswith(_MODULE)


def test_the_fixture_is_loaded_at_all(walked: DuckDbWorkspace, tmp_path: Path):
    """The OI-4 count check `test_return_flow.py` puts first: a join that matched nothing
    would leave every assertion above vacuously green."""
    assert walked.query("value_edges")
    assert {str(row["kind"]) for row in walked.query("value_edges")} >= {
        "produced_by",
        "returned_by",
        "read_from_binding",
        "bound_to_parameter",
        "names_declaration",
    }
