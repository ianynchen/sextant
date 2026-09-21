"""The `fluent` engine's registration words (spec 2026-09-21 §2, §4, §5): a chain that
builds a REGISTRATION — an adapter or a flow — rather than a request, and so carries a
consumer (`handler`), a link to a named channel (`channel_link`), a direction of its own
(`direction:` on the root), an address composed from two captured halves (`compose:`), and
steps that make a field unreadable from there on (`poisons:`, `undeclared_steps:`).

Every word is optional, and the invented vocabulary here is exactly the reason: a catalog
that spells none of them derives what it always did, which `test_call_engines.py`'s own
fluent tests and the shipped catalogs' goldens hold. The facts mirror the emitted grammar
the way that file's do — a `<init>` root chains by its own receiver (CP-3), a setter on
the constructed value returns void and carries that same receiver, a `lambda` argument
names its body BARE while the body's own call sites are recorded under the module-prefixed
symbol (D00 §5a).
"""

from pathlib import Path

import pytest
from test_call_engines import _MODULE, _call, _document

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import fluent
from sextant.domain.closed_sets import ConstructKind
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"call_site", "string_constants", "chain_reconstruction"}

ADAPTER = "com/acme/streams/QueueAdapter#"
ADAPTER_TYPE = "com.acme.streams.QueueAdapter"
CALLER = _MODULE + "com/acme/streams/Wiring#inbound()."
# BARE, as a `lambda` argument names it; the body's own sites and its symbol fact carry
# the module coordinates.
BODY = "com/acme/streams/Wiring#lambda$inbound$0(Lcom/acme/streams/Message;)V."
SUBSCRIPTION = "orders.queue"

_ADAPTER_MATCHES = {
    "roots": [{"owner": ADAPTER_TYPE, "method": "<init>", "captures": {"channel": "arg1"}}],
    "steps": [
        {"method": "onMessage", "captures": {"handler": "arg0"}},
        {"method": "discard", "captures": {"handler": "none"}},
        {"method": "reroute", "poisons": ["handler"]},
        {"method": "linkTo", "captures": {"channel_link": "arg0"}},
        {"method": "linkToBean", "captures": {"channel_link": {"bean_via": "arg0"}}},
        {"method": "setQueueExpression", "poisons": ["channel"]},
    ],
    # The constructed value IS the registration: the root is its own terminal, the
    # Apache `<init>` precedent without the execute-join.
    "terminal": ["<init>"],
}


def _catalog(
    matches: dict, *, direction: str = "inbound", catalog_id: str = "invented-adapters"
) -> Catalog:
    return Catalog(
        id=catalog_id,
        style="fluent",
        protocol="amqp",
        direction=direction,
        requires=("call_site", "string_constants", "chain_reconstruction"),
        matches=matches,
        source=Path(f"tests/{catalog_id}.yml"),
    )


def _lambda(body: str = BODY) -> CallArgument:
    return CallArgument(kind="lambda", source=9, symbol=body)


def _body_symbol(body: str = BODY) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1", symbol=_MODULE + body, construct_kind=ConstructKind.METHOD
    )


def _adapter(
    *calls: tuple[str, list[CallArgument]],
    caller: str = CALLER,
    subscription: CallArgument | None = None,
) -> list:
    """`new QueueAdapter(ops, "orders.queue")` followed by `calls` on it, in that order:
    every call a void setter on the constructed value (receiver 5, `result` null), which
    is how the extractor records a configured bean."""
    facts = [
        _call(
            caller,
            ADAPTER,
            "<init>",
            0,
            receiver=5,
            result=None,
            arguments=[
                CallArgument(kind="instance", source=2, symbol="com/acme/streams/Ops#"),
                subscription or CallArgument(kind="string", value=SUBSCRIPTION),
            ],
            invoke_kind="special",
        )
    ]
    for ordinal, (name, arguments) in enumerate(calls, start=1):
        facts.append(
            _call(caller, ADAPTER, name, ordinal, receiver=5, result=None, arguments=arguments)
        )
    return facts


def _run(tmp_path: Path, facts: list, catalog: Catalog) -> DuckDbWorkspace:
    """The engine alone, on the tables `derive_endpoints` would have reset for it — so a
    chain that writes a binding INSTEAD of a row is observable as exactly that, before
    the join pass mints anything from the binding."""
    write_fact_file(tmp_path / "facts" / "Wiring.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("endpoints_reset")
    workspace.derive("channel_bindings_reset")
    fluent.run(workspace, catalog)
    return workspace


def _rows(workspace: DuckDbWorkspace) -> list[dict]:
    return [dict(row) for row in workspace.query("endpoints")]


def _bindings(workspace: DuckDbWorkspace) -> list[dict]:
    return [dict(row) for row in workspace.query("channel_bindings")]


# --- the inbound row --------------------------------------------------------


def test_an_inbound_chain_carries_the_lambda_it_was_handed_as_its_handler(tmp_path: Path):
    """§3c's inbound row: the wire from the root, the handler the FULL symbol of the
    lambda's body — joined through the method symbols, since the argument names it bare
    and a column nothing in the graph can follow is no handler — `caller` the
    constructing method, `peer` and the shapes NULL."""
    facts = [*_adapter(("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    assert _bindings(workspace) == []
    workspace.close()

    assert row == {
        "protocol": "amqp",
        "direction": "inbound",
        "method": None,
        "path": SUBSCRIPTION,
        "handler": _MODULE + BODY,
        "handler_signature": None,
        "caller": CALLER,
        "peer": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "catalog_id": "invented-adapters",
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
        "format": None,
        "format_resolution": None,
    }


def test_a_lambda_no_symbol_fact_declares_is_no_handler(tmp_path: Path):
    """The join is the guard: a body the scanned documents never declared reads NULL
    rather than a bare name nothing else in the graph spells."""
    workspace = _run(tmp_path, _adapter(("onMessage", [_lambda()])), _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["handler"], row["resolution"]) == (None, "resolved")


def test_a_handler_the_catalog_spells_none_is_null_and_the_row_is_resolved(tmp_path: Path):
    """Spec §5's `discard` kind: a registration that drops what it receives HAS no
    handler, and NULL is the true answer, not a read failure."""
    facts = [*_adapter(("onMessage", [_lambda()]), ("discard", [])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["handler"], row["resolution"]) == (None, "resolved")


def test_a_handler_that_is_not_a_lambda_reads_null_without_touching_the_row(tmp_path: Path):
    """A handler handed in as a parameter (a bean, spec §3a — the next task's word) is not
    read here; the wire is still known, so the row stays resolved on it."""
    facts = _adapter(("onMessage", [CallArgument(kind="parameter", value=0)]))
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["handler"], row["path"], row["resolution"]) == (None, SUBSCRIPTION, "resolved")


def test_an_outbound_row_never_carries_a_handler(tmp_path: Path):
    """§3c: an outbound registration's `handler` is NULL whatever the chain captured — a
    handler is what an INBOUND registration hands its messages to."""
    facts = [*_adapter(("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES, direction="outbound"))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["direction"], row["handler"]) == ("outbound", None)


# --- poisons ----------------------------------------------------------------


def test_a_poisoning_step_leaves_the_handler_null_for_the_rest_of_the_chain(tmp_path: Path):
    """Spec §5's `divert`: after `reroute()` the message may leave the linear flow, so
    the `onMessage` that follows is not certainly what receives it — `handler` NULL, and
    the row still resolved, because the wire is known regardless (§0b A5)."""
    facts = [*_adapter(("reroute", []), ("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["handler"], row["path"], row["resolution"]) == (None, SUBSCRIPTION, "resolved")


def test_a_poisoned_destination_leaves_the_row_unresolved_on_path(tmp_path: Path):
    """Spec §4: a destination set from an expression is not a literal, so `channel` is
    unreadable from there on — `path` NULL, `unresolved` — even though the constructor
    named one, because the later setter is the one the framework honours."""
    facts = _adapter(("setQueueExpression", [CallArgument(kind="parameter", value=1)]))
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_a_chain_without_the_poisoning_step_keeps_its_handler(tmp_path: Path):
    """The near-miss: the poison is the STEP's effect, never a property of the chain — the
    same chain without `reroute()` is the first test's row."""
    facts = [*_adapter(("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert row["handler"] == _MODULE + BODY


def test_an_undeclared_member_of_a_listed_owner_applies_the_catalog_poisons(tmp_path: Path):
    """Spec §5: an undeclared member of a flow definition is a `divert`. `undeclared_steps`
    names the owners the rule holds for and the fields it poisons; a call the catalog
    declares no step for, on one of those owners, poisons them from there on."""
    matches = {
        **_ADAPTER_MATCHES,
        "undeclared_steps": {"owner": ADAPTER_TYPE, "poisons": ["handler"]},
    }
    facts = [*_adapter(("mystery", []), ("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["handler"], row["resolution"]) == (None, "resolved")


def test_an_undeclared_member_of_another_owner_poisons_nothing(tmp_path: Path):
    """The near-miss: without the owner in the list, an unmatched step passes through
    uncaptured exactly as it always has (D02 §4)."""
    matches = {
        **_ADAPTER_MATCHES,
        "undeclared_steps": {"owner": "com.acme.streams.Other", "poisons": ["handler"]},
    }
    facts = [*_adapter(("mystery", []), ("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    workspace.close()

    assert row["handler"] == _MODULE + BODY


# --- channel_link and the binding ------------------------------------------------


def test_a_resolved_channel_link_writes_one_binding_and_no_row(tmp_path: Path):
    """Spec §3b and the plan's ruling: the chain that links a channel writes the `fed_by`
    edge — the wire it read, the constructing method, the registration's direction — and
    leaves the row to the join pass, so a linked adapter is never counted twice."""
    facts = _adapter(("linkTo", [CallArgument(kind="string", value="ordersChannel")]))
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    rows = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert rows == []
    assert binding == {
        "channel": "ordersChannel",
        "role": "fed_by",
        "symbol": CALLER,
        "protocol": "amqp",
        "direction": "inbound",
        "destination": SUBSCRIPTION,
        "catalog_id": "invented-adapters",
        "resolution": "resolved",
    }


def test_the_join_pass_owns_the_row_of_a_linked_registration(tmp_path: Path):
    """Through the whole pipeline: the binding the chain wrote becomes the registration's
    row — `handler` NULL, since nothing here reads the channel — minted once."""
    write_fact_file(
        tmp_path / "facts" / "Wiring.jsonl",
        _document(),
        _adapter(("linkTo", [CallArgument(kind="string", value="ordersChannel")])),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    assert (
        derive_endpoints(workspace, [_catalog(_ADAPTER_MATCHES)], capabilities=CAPABILITIES) == []
    )
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["caller"], row["resolution"]) == (
        SUBSCRIPTION,
        None,
        CALLER,
        "resolved",
    )


def test_a_binding_carries_an_unresolved_destination_as_such(tmp_path: Path):
    """The link is known and the wire is not: the edge is still written — the channel IS
    fed — with `destination` NULL and `unresolved`, which the join pass carries onto the
    row it mints."""
    facts = _adapter(
        ("linkTo", [CallArgument(kind="string", value="ordersChannel")]),
        subscription=CallArgument(kind="parameter", value=1),
    )
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [binding] = _bindings(workspace)
    assert _rows(workspace) == []
    workspace.close()

    assert (binding["destination"], binding["resolution"]) == (None, "unresolved")


def test_an_unreadable_channel_link_keeps_the_row_and_writes_no_binding(tmp_path: Path):
    """Spec §4: a channel we cannot name is not a channel we can bind — the registration
    derives its own row, `handler` NULL, and no edge is written."""
    facts = _adapter(("linkTo", [CallArgument(kind="parameter", value=1)]))
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (SUBSCRIPTION, None, "resolved")
    assert bindings == []


def test_a_bean_via_channel_link_is_accepted_and_reads_as_unresolved_for_now(tmp_path: Path):
    """The `{bean_via: argN}` spelling loads — the next task fills its behaviour — and
    until then a link declared that way is the unreadable case above: row, no binding."""
    facts = _adapter(("linkToBean", [CallArgument(kind="parameter", value=1)]))
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (row["path"], row["handler"]) == (SUBSCRIPTION, None)
    assert bindings == []


def test_an_outbound_chain_with_a_channel_link_writes_its_row_and_an_outbound_binding(
    tmp_path: Path,
):
    """Spec §3b: an outbound handler bean reads its channel, and says so with a `fed_by`
    of `direction: outbound` — so `gaps` stops asking who feeds it — while deriving its
    own outbound row in the chain, since the join pass mints nothing for an outbound
    feeder."""
    facts = _adapter(("linkTo", [CallArgument(kind="string", value="outChannel")]))
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES, direction="outbound"))
    [row] = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert (row["direction"], row["path"], row["handler"]) == ("outbound", SUBSCRIPTION, None)
    assert (binding["channel"], binding["direction"], binding["destination"]) == (
        "outChannel",
        "outbound",
        SUBSCRIPTION,
    )


# --- direction per root --------------------------------------------------------------


def test_a_root_direction_overrides_the_catalog_direction_for_its_chains(tmp_path: Path):
    """Spec §4: the outbound handler declared in an inbound catalog — the root says
    `direction: outbound`, and every column that reads the direction reads the root's."""
    matches = {
        **_ADAPTER_MATCHES,
        "roots": [{**_ADAPTER_MATCHES["roots"][0], "direction": "outbound"}],
    }
    facts = [*_adapter(("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["direction"], row["handler"], row["path"]) == ("outbound", None, SUBSCRIPTION)


def test_a_root_without_a_direction_keeps_the_catalog_direction(tmp_path: Path):
    facts = [*_adapter(("onMessage", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert row["direction"] == "inbound"


# --- compose -------------------------------------------------------------------


_COMPOSED_MATCHES = {
    "roots": [
        {
            "owner": ADAPTER_TYPE,
            "method": "<init>",
            "captures": {},
            "direction": "outbound",
            "compose": {"channel": ["exchange", "routing_key"], "join": "/"},
        }
    ],
    "steps": [
        {"method": "setExchangeName", "captures": {"exchange": "arg0"}},
        {"method": "setRoutingKey", "captures": {"routing_key": "arg0"}},
    ],
    "terminal": ["<init>"],
}


def test_a_composed_address_joins_both_captured_halves_in_declared_order(tmp_path: Path):
    """Spec §4 (F4): two setters composing one address, joined in the order the root
    declares them whatever order the code called them in."""
    facts = _adapter(
        ("setRoutingKey", [CallArgument(kind="string", value="order.created")]),
        ("setExchangeName", [CallArgument(kind="string", value="orders")]),
    )
    workspace = _run(tmp_path, facts, _catalog(_COMPOSED_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["direction"], row["path"], row["resolution"]) == (
        "outbound",
        "orders/order.created",
        "resolved",
    )


def test_a_composed_address_with_a_half_never_captured_is_unresolved(tmp_path: Path):
    """§0b A3: the framework fills an unset half from defaults the walk does not read, so
    half an address is no address — `path` NULL, `unresolved`."""
    facts = _adapter(("setExchangeName", [CallArgument(kind="string", value="orders")]))
    workspace = _run(tmp_path, facts, _catalog(_COMPOSED_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_a_composed_address_with_an_unreadable_half_is_unresolved(tmp_path: Path):
    facts = _adapter(
        ("setExchangeName", [CallArgument(kind="string", value="orders")]),
        ("setRoutingKey", [CallArgument(kind="parameter", value=0)]),
    )
    workspace = _run(tmp_path, facts, _catalog(_COMPOSED_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


# --- the configured value: void setters fold, results fork ---------------------------


def test_void_calls_on_one_value_configure_one_chain(tmp_path: Path):
    """The shape every registration above relies on, pinned on its own: three setters on
    the constructed value share its receiver and return nothing, and they are ONE object
    configured three times — one row carrying all three captures — never three chains
    each seeing one setter. A call whose `result` is a value is the fork it always was
    (the next test)."""
    facts = [
        *_adapter(
            ("linkTo", [CallArgument(kind="string", value="ordersChannel")]),
            ("onMessage", [_lambda()]),
            ("discard", []),
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES, direction="outbound"))
    [row] = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert (row["path"], binding["channel"]) == (SUBSCRIPTION, "ordersChannel")


def test_a_call_producing_a_value_still_forks_the_chain(tmp_path: Path):
    """Two chains built off one root value each derive on their own — the fork
    `test_call_engines.py` pins for request builders, unchanged by the fold above."""
    caller = CALLER
    facts = [
        _call(caller, ADAPTER, "<init>", 0, receiver=5, result=None, invoke_kind="special"),
        _call(
            caller,
            ADAPTER,
            "forQueue",
            1,
            receiver=5,
            result=6,
            arguments=[CallArgument(kind="string", value="a")],
        ),
        _call(
            caller,
            ADAPTER,
            "forQueue",
            2,
            receiver=5,
            result=7,
            arguments=[CallArgument(kind="string", value="b")],
        ),
    ]
    matches = {
        "roots": [{"owner": ADAPTER_TYPE, "method": "<init>", "captures": {}}],
        "steps": [{"method": "forQueue", "captures": {"channel": "arg0"}}],
        "terminal": ["<init>"],
    }
    workspace = _run(tmp_path, facts, _catalog(matches))
    rows = _rows(workspace)
    workspace.close()

    assert sorted(row["path"] for row in rows) == ["a", "b"]


# --- validation ---------------------------------------------------------------------


def _refused(tmp_path: Path, matches: dict, fragment: str) -> None:
    with pytest.raises(CatalogError, match=fragment):
        _run(tmp_path, _adapter(), _catalog(matches))


def test_a_root_direction_outside_the_closed_set_is_refused(tmp_path: Path):
    matches = {
        **_ADAPTER_MATCHES,
        "roots": [{**_ADAPTER_MATCHES["roots"][0], "direction": "sideways"}],
    }
    _refused(tmp_path, matches, "invented-adapters.*direction: sideways")


def test_a_handler_capture_that_is_neither_a_position_nor_none_is_refused(tmp_path: Path):
    matches = {**_ADAPTER_MATCHES, "steps": [{"method": "onMessage", "captures": {"handler": "x"}}]}
    _refused(tmp_path, matches, "invented-adapters.*handler: x")


def test_a_channel_link_capture_of_the_wrong_shape_is_refused(tmp_path: Path):
    matches = {
        **_ADAPTER_MATCHES,
        "steps": [{"method": "linkTo", "captures": {"channel_link": {"via": "arg0"}}}],
    }
    _refused(tmp_path, matches, "invented-adapters.*channel_link")


def test_a_poison_naming_no_declared_capture_is_refused(tmp_path: Path):
    matches = {**_ADAPTER_MATCHES, "steps": [{"method": "reroute", "poisons": ["peer"]}]}
    _refused(tmp_path, matches, "invented-adapters.*poisons.*peer")


def test_a_malformed_compose_is_refused(tmp_path: Path):
    matches = {
        **_COMPOSED_MATCHES,
        "roots": [{**_COMPOSED_MATCHES["roots"][0], "compose": {"channel": "exchange"}}],
    }
    _refused(tmp_path, matches, "invented-adapters.*compose")


def test_malformed_undeclared_steps_are_refused(tmp_path: Path):
    matches = {**_ADAPTER_MATCHES, "undeclared_steps": {"poisons": ["handler"]}}
    _refused(tmp_path, matches, "invented-adapters.*undeclared_steps")
