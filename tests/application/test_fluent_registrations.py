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
import yaml
from test_call_engines import _MODULE, _call, _document
from test_config_join import _module_document

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import fluent
from sextant.domain.closed_sets import ConstructKind
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    ModuleFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.facts import Parameter as DeclaredParameter
from sextant.domain.symbols import method_descriptor
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"call_site", "string_constants", "chain_reconstruction"}

ADAPTER = "com/acme/streams/QueueAdapter#"
ADAPTER_TYPE = "com.acme.streams.QueueAdapter"
CALLER = _MODULE + "com/acme/streams/Wiring#inbound()."
# BARE, as a `lambda` argument names it; the body's own sites and its symbol fact carry
# the module coordinates.
BODY = "com/acme/streams/Wiring#lambda$inbound$0(Lcom/acme/streams/Message;)V."
SUBSCRIPTION = "orders.queue"

# The bean fold is driven by the shipped `bean-models/spring.yml`, as `test_beans.py`
# drives it: the model's own spellings are what the bean facts below are read through, and
# the engine spells none of them. Every catalog here names it, because `_ADAPTER_MATCHES`
# spells a `bean_via` capture and a catalog spelling one without a model is refused.
_SPRING = yaml.safe_load(
    (catalogs_dir() / "bean-models" / "spring.yml").read_text(encoding="utf-8")
)

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
    matches: dict,
    *,
    direction: str = "inbound",
    catalog_id: str = "invented-adapters",
    bean_model: dict | None = None,
) -> Catalog:
    return Catalog(
        id=catalog_id,
        style="fluent",
        protocol="amqp",
        direction=direction,
        requires=("call_site", "string_constants", "chain_reconstruction"),
        matches=matches,
        source=Path(f"tests/{catalog_id}.yml"),
        bean_model=_SPRING if bean_model is None else bean_model,
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


def _run(
    tmp_path: Path, facts: list, catalog: Catalog, readers: list[dict] | None = None
) -> DuckDbWorkspace:
    """The engine alone, on the tables `derive_endpoints` would have reset for it — so a
    chain that writes a binding INSTEAD of a row is observable as exactly that, before
    the join pass mints anything from the binding. `readers` are `read_by` edges already
    in the table when the engine runs — what the channel index's catalog wrote before
    it (spec §3a's "a channel name the channel index knows")."""
    write_fact_file(tmp_path / "facts" / "Wiring.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("endpoints_reset")
    workspace.derive("channel_bindings_reset")
    if readers:
        workspace.derive("channel_bindings_insert", rows=readers)
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
    """A `{bean_via: argN}` link whose argument names a parameter the constructing
    method does not declare (no declaration fact at all) is a bean reference nothing
    resolves — the unreadable case above: row, no binding. (Written before the bean fold
    landed, when every such link read this way; kept as its near-miss.)"""
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


# --- bean_via: the channel bean's name, and the container hop (spec §3a, §4) ----------

_BEAN = "org/springframework/context/annotation/Bean#"
_QUALIFIER = "org/springframework/beans/factory/annotation/Qualifier#"
_CHANNEL_TYPE = "org/springframework/messaging/MessageChannel#"
# An invented container type: nothing a framework bean shares, so the container rungs
# (qualifier, unique type, name) are what resolve a parameter of it.
CONTAINER = "com/acme/streams/Container#"
CONTAINER_TYPE = "com.acme.streams.Container"
WIRING = "com/acme/streams/Wiring#"
CALLER_BARE = WIRING + "inbound()."
ORDERS_CHANNEL_BEAN = WIRING + "ordersChannel(sig_1a2b3c4d)."
CONTAINER_BEAN = WIRING + "container(sig_c0c0c0c0)."
ACTIVATOR = "com.acme.fn.Activator"
ACTIVATOR_SYMBOL = "com/acme/fn/Activator#"


def _declared(
    bare: str,
    *,
    parameters: list[DeclaredParameter] | None = None,
    returns: str | None = None,
) -> SymbolFact:
    """A declared method — the constructing method with its injected parameters, or a
    factory method with its return type — under the module-prefixed symbol the
    `method_declarations` query and `annotations.target` both carry (D00 §5a)."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare,
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + WIRING,
        signature=Signature(
            parameters=parameters or [],
            returns=None if returns is None else TypeRef(symbol=returns),
        ),
    )


def _annotated(bare: str, annotation: str, args: dict | None = None) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + bare,
        retention="runtime",
        use=AnnotationUse(annotation=annotation, args=args or {}),
    )


def _bean(bare: str, returns: str, *, args: dict | None = None) -> list:
    return [_declared(bare, returns=returns), _annotated(bare, _BEAN, args)]


def _parameter(erased: str, name: str | None, qualifier: str | None = None) -> DeclaredParameter:
    annotations = (
        [AnnotationUse(annotation=_QUALIFIER, args={"value": qualifier})] if qualifier else []
    )
    return DeclaredParameter(
        name=name, type=TypeRef(symbol=erased), erased_symbol=erased, annotations=annotations
    )


def _linked_to_parameter(index: int = 0) -> list:
    """`new QueueAdapter(ops, "orders.queue"); adapter.linkToBean(<parameter index>)` —
    the link handed in as an injected parameter of the constructing method."""
    return _adapter(("linkToBean", [CallArgument(kind="parameter", value=index)]))


def test_a_qualified_channel_parameter_links_the_bean_it_names(tmp_path: Path):
    """Spec §4: `setOutputChannel(channel)` where the parameter carries the model's
    qualifier — the first rung for every reference kind — links the channel under the
    bean's name: one `fed_by`, no row, exactly as a literal link would."""
    facts = [
        *_linked_to_parameter(),
        _declared(
            CALLER_BARE,
            parameters=[_parameter(_CHANNEL_TYPE, "inputChannel", qualifier="ordersChannel")],
        ),
        *_bean(ORDERS_CHANNEL_BEAN, _CHANNEL_TYPE),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    rows = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert rows == []
    assert (binding["channel"], binding["role"], binding["destination"]) == (
        "ordersChannel",
        "fed_by",
        SUBSCRIPTION,
    )


def test_a_channel_parameter_links_the_bean_its_own_name_declares(tmp_path: Path):
    """The name rung (§0b A2): a channel parameter is never resolved by type — the
    container sees more channel candidates than the module declares — so its declared
    NAME, where a factory method declares a bean of it, is the link."""
    facts = [
        *_linked_to_parameter(),
        _declared(CALLER_BARE, parameters=[_parameter(_CHANNEL_TYPE, "ordersChannel")]),
        *_bean(ORDERS_CHANNEL_BEAN, _CHANNEL_TYPE),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [binding] = _bindings(workspace)
    assert _rows(workspace) == []
    workspace.close()

    assert binding["channel"] == "ordersChannel"


def test_a_channel_parameter_named_for_a_channel_the_index_knows_links_it(tmp_path: Path):
    """The other half of the name rung: no method declares the bean, but a handler's
    annotation names the channel — the container auto-creates one under a referenced
    name — and the channel index's `read_by` edge is how the engine knows it (spec §3a,
    §3b). The reader's own edge is left standing beside the new one."""
    reader = {
        "channel": "auditChannel",
        "role": "read_by",
        "symbol": _MODULE + WIRING + "audit(sig_aud1t000).",
        "protocol": None,
        "direction": "inbound",
        "destination": None,
        "catalog_id": "invented-channels",
        "resolution": "resolved",
    }
    facts = [
        *_linked_to_parameter(),
        _declared(CALLER_BARE, parameters=[_parameter(_CHANNEL_TYPE, "auditChannel")]),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES), readers=[reader])
    bindings = _bindings(workspace)
    assert _rows(workspace) == []
    workspace.close()

    assert sorted((b["role"], b["channel"]) for b in bindings) == [
        ("fed_by", "auditChannel"),
        ("read_by", "auditChannel"),
    ]


def test_a_channel_name_the_index_knows_only_under_a_placeholder_never_answered_is_no_name(
    tmp_path: Path,
):
    """The near-miss on the index's side: a `read_by` whose name configuration never
    resolved is `unresolved` and names no channel a parameter could be matched to."""
    reader = {
        "channel": "${acme.audit-channel}",
        "role": "read_by",
        "symbol": _MODULE + WIRING + "audit(sig_aud1t000).",
        "protocol": None,
        "direction": "inbound",
        "destination": None,
        "catalog_id": "invented-channels",
        "resolution": "unresolved",
    }
    facts = [
        *_linked_to_parameter(),
        _declared(CALLER_BARE, parameters=[_parameter(_CHANNEL_TYPE, "${acme.audit-channel}")]),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES), readers=[reader])
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (row["path"], row["handler"]) == (SUBSCRIPTION, None)
    assert [b["role"] for b in bindings] == ["read_by"]


def test_two_beans_of_one_name_leave_the_link_unresolved(tmp_path: Path):
    """A rung with two candidates is `ambiguous` (§3a): the registration keeps its own
    row with `handler` NULL — the wire is known — and writes no edge, because a channel
    we cannot name is not a channel we can bind."""
    facts = [
        *_linked_to_parameter(),
        _declared(CALLER_BARE, parameters=[_parameter(_CHANNEL_TYPE, "ordersChannel")]),
        *_bean(ORDERS_CHANNEL_BEAN, _CHANNEL_TYPE),
        *_bean(WIRING + "other(sig_0ffe0ffe).", _CHANNEL_TYPE, args={"name": ["ordersChannel"]}),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (SUBSCRIPTION, None, "resolved")
    assert bindings == []


def test_a_later_literal_link_overrides_an_unresolved_bean_link(tmp_path: Path):
    """The bean fold's failure is a setter's own read failure, not a catalog poison: a
    later `setOutputChannelName("x")` is the setter the framework honours (last wins),
    so it overrides the unresolved bean link rather than being refused by it."""
    facts = [
        *_adapter(
            ("linkToBean", [CallArgument(kind="parameter", value=0)]),
            ("linkTo", [CallArgument(kind="string", value="lateChannel")]),
        ),
        _declared(CALLER_BARE, parameters=[_parameter(_CHANNEL_TYPE, "nobody")]),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [binding] = _bindings(workspace)
    workspace.close()

    assert binding["channel"] == "lateChannel"


def test_a_direct_call_to_the_factory_method_links_its_bean(tmp_path: Path):
    """`setOutputChannel(ordersChannel())` — the argument is the RESULT of a call to the
    declaring method in the same class (`bean_called`), and the bean is that method's.
    The call names it by owner, name and JVM descriptor; the declaration by the symbol
    whose disambiguator is that descriptor's digest (D00 §5a) — `method_descriptor` is
    the bridge, so the bean here is declared under exactly that spelling."""
    declared_under = method_descriptor(WIRING, "ordersChannel", "()V")
    facts = [
        *_adapter(),
        _call(
            CALLER,
            WIRING,
            "ordersChannel",
            1,
            receiver=None,
            result=8,
            arguments=[],
        ),
        _call(
            CALLER,
            ADAPTER,
            "linkToBean",
            2,
            receiver=5,
            result=None,
            arguments=[CallArgument(kind="unresolved", source=8)],
        ),
        _declared(CALLER_BARE),
        *_bean(declared_under, _CHANNEL_TYPE),
    ]
    workspace = _run(tmp_path, facts, _catalog(_ADAPTER_MATCHES))
    [binding] = _bindings(workspace)
    workspace.close()

    assert binding["channel"] == "ordersChannel"


# --- the container hop -------------------------------------------------------------

_CONTAINER_MATCHES = {
    "roots": [
        {"owner": ADAPTER_TYPE, "method": "<init>", "captures": {"channel": {"bean_via": "arg0"}}}
    ],
    # Chains `bean_via` may fold from, rooted at THEIR constructors (spec §4's `beans:`).
    "beans": [{"owner": CONTAINER_TYPE, "method": "<init>", "captures": {}}],
    "steps": [
        {"method": "setQueueNames", "captures": {"channel": "arg0"}},
        {"method": "setQueueExpression", "poisons": ["channel"]},
    ],
    "terminal": ["<init>"],
}


def _container_adapter(*, argument: CallArgument | None = None) -> list:
    """`new QueueAdapter(container)` in the constructing method."""
    return [
        _call(
            CALLER,
            ADAPTER,
            "<init>",
            0,
            receiver=5,
            result=None,
            arguments=[argument or CallArgument(kind="parameter", value=0)],
            invoke_kind="special",
        )
    ]


def _container_bean(*setters: tuple[str, list[CallArgument]]) -> list:
    """The container's own factory method: `new Container(cf)` configured by `setters`,
    declared and annotated as a bean of the container type."""
    caller = _MODULE + CONTAINER_BEAN
    facts = [
        _call(
            caller,
            CONTAINER,
            "<init>",
            0,
            receiver=7,
            result=None,
            arguments=[CallArgument(kind="parameter", value=0)],
            invoke_kind="special",
        )
    ]
    for ordinal, (name, arguments) in enumerate(setters, start=1):
        facts.append(
            _call(caller, CONTAINER, name, ordinal, receiver=7, result=None, arguments=arguments)
        )
    return [*facts, *_bean(CONTAINER_BEAN, CONTAINER)]


def _queue_names(*names: str) -> CallArgument:
    """`setQueueNames("q1", "q2")` — a varargs slot, ONE array argument (9.15)."""
    return CallArgument(
        kind="array", elements=[CallArgument(kind="string", value=name) for name in names]
    )


def test_a_container_reference_folds_the_queues_its_own_chain_captured(tmp_path: Path):
    """Spec §4's container hop: `new AmqpInboundChannelAdapter(container)` names its
    queues nowhere — the container bean's own `setQueueNames("q1", "q2")` does. The
    argument resolves to the bean (a container type: unique by type), its method's chain
    is walked from the matching `beans:` root, and its `channel` capture becomes this
    chain's: one row per element (§3c), `caller` the ADAPTER's method."""
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(("setQueueNames", [_queue_names("q1", "q2")])),
    ]
    workspace = _run(tmp_path, facts, _catalog(_CONTAINER_MATCHES))
    rows = _rows(workspace)
    workspace.close()

    assert [(row["path"], row["caller"], row["resolution"]) for row in rows] == [
        ("q1", CALLER, "resolved"),
        ("q2", CALLER, "resolved"),
    ]


def test_a_container_whose_chain_poisoned_the_capture_leaves_the_row_unresolved(
    tmp_path: Path,
):
    """The bean's chain is walked with the catalog's own steps, poisons included."""
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(
            ("setQueueNames", [_queue_names("q1")]),
            ("setQueueExpression", [CallArgument(kind="parameter", value=1)]),
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_a_container_built_in_a_third_bean_is_unresolved(tmp_path: Path):
    """One hop only (spec §4): the container bean's method constructs nothing of its
    own — it is handed the container by a third bean — so no `beans:` root is found
    in its chain, and the adapter's destination is unread: `path` NULL, `unresolved`."""
    third_hop = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        _call(
            third_hop,
            "com/acme/streams/ContainerFactory#",
            "create",
            0,
            receiver=None,
            result=7,
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        *_bean(CONTAINER_BEAN, CONTAINER),
    ]
    workspace = _run(tmp_path, facts, _catalog(_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_two_container_beans_of_the_type_and_no_name_match_are_unresolved(tmp_path: Path):
    """The container rungs (§0b A2): no qualifier, two beans of the type, a parameter
    name neither declares — `ambiguous`, and the row says so on `path`. (Named
    `listener`: a parameter named `container` would resolve by the name rung to the
    `container()` bean, which is the container's own third rung and the right answer.)"""
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "listener")]),
        *_container_bean(("setQueueNames", [_queue_names("q1")])),
        *_bean(WIRING + "second(sig_5ec0nd00).", CONTAINER),
    ]
    workspace = _run(tmp_path, facts, _catalog(_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


# --- method_annotation ----------------------------------------------------------------


def test_the_constructing_methods_annotation_supplies_the_link(tmp_path: Path):
    """Spec §4: the outbound handler bean — `@ServiceActivator(inputChannel = "orders")`
    on the `@Bean` method that builds the handler — reads its channel off its own
    annotation: the outbound row from the chain AND an outbound `fed_by`, so the
    channel's question is not asked (§3b)."""
    matches = {
        **_ADAPTER_MATCHES,
        "roots": [
            {
                **_ADAPTER_MATCHES["roots"][0],
                "direction": "outbound",
                "method_annotation": {
                    "annotation": ACTIVATOR,
                    "arg": "inputChannel",
                    "into": "channel_link",
                },
            }
        ],
    }
    facts = [
        *_adapter(),
        _declared(CALLER_BARE),
        _annotated(CALLER_BARE, ACTIVATOR_SYMBOL, {"inputChannel": "ordersChannel"}),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert (row["direction"], row["path"], row["handler"]) == ("outbound", SUBSCRIPTION, None)
    assert (binding["channel"], binding["direction"], binding["destination"]) == (
        "ordersChannel",
        "outbound",
        SUBSCRIPTION,
    )


def test_a_constructing_method_without_the_annotation_captures_nothing(tmp_path: Path):
    """Absent → nothing captured: the chain is exactly what it was without the word."""
    matches = {
        **_ADAPTER_MATCHES,
        "roots": [
            {
                **_ADAPTER_MATCHES["roots"][0],
                "direction": "outbound",
                "method_annotation": {
                    "annotation": ACTIVATOR,
                    "arg": "inputChannel",
                    "into": "channel_link",
                },
            }
        ],
    }
    facts = [*_adapter(), _declared(CALLER_BARE), _annotated(CALLER_BARE, ACTIVATOR_SYMBOL, {})]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert row["path"] == SUBSCRIPTION
    assert bindings == []


# --- through the pipeline: the channel index runs before the engine that reads it -----


def test_the_channel_index_is_written_before_the_engine_that_resolves_a_name_through_it(
    tmp_path: Path,
):
    """The one ordering the bean fold depends on, pinned end to end: a `config_join`
    catalog that mints no rows and stamps nothing (the shipped channel index's shape)
    runs BEFORE the engines, so its `read_by` names are there when a channel parameter
    resolves by name — and the join pass then mints the linked registration's row with
    the reader as its handler. Were the index written at that style's usual last turn,
    the name would resolve to nothing, the chain would keep its own row with `handler`
    NULL, and no edge would join."""
    reader = WIRING + "audit(sig_aud1t000)."
    facts = [
        *_linked_to_parameter(),
        _declared(CALLER_BARE, parameters=[_parameter(_CHANNEL_TYPE, "auditChannel")]),
        _declared(reader),
        _annotated(reader, ACTIVATOR_SYMBOL, {"inputChannel": "auditChannel"}),
    ]
    write_fact_file(tmp_path / "facts" / "Wiring.jsonl", _document(), facts)
    write_fact_file(
        tmp_path / "facts" / "module.jsonl",
        _module_document(),
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:orders-service",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=["com.acme:acme-channels"],
            )
        ],
    )
    channels = Catalog(
        id="invented-channels",
        style="config_join",
        protocol="",
        direction="",
        requires=("resolved_config",),
        matches={
            "address_from_config": {
                "binding": {
                    "from": "annotation_value",
                    "channels": [
                        {"annotation": ACTIVATOR, "arg": "inputChannel", "direction": "inbound"}
                    ],
                }
            }
        },
        source=Path("tests/invented-channels.yml"),
        detect_coordinates=("com.acme:acme-channels",),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("resolved_config_reset")
    skipped = derive_endpoints(
        workspace,
        [_catalog(_ADAPTER_MATCHES), channels],
        capabilities={*CAPABILITIES, "resolved_config"},
    )
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert skipped == []
    assert (row["path"], row["handler"], row["caller"]) == (SUBSCRIPTION, _MODULE + reader, CALLER)
    assert sorted(b["role"] for b in bindings) == ["fed_by", "read_by"]


# --- validation of the bean words ---------------------------------------------------


def test_a_bean_via_capture_on_a_catalog_naming_no_bean_model_is_refused(tmp_path: Path):
    """`bean_via` resolves through the catalog's bean model (D02 §1c); a catalog naming
    none would resolve nothing and say nothing, so it is refused by file at load."""
    with pytest.raises(CatalogError, match="invented-adapters.*bean_model"):
        _run(tmp_path, _adapter(), _catalog(_ADAPTER_MATCHES, bean_model={}))


def test_a_malformed_beans_entry_is_refused(tmp_path: Path):
    matches = {**_CONTAINER_MATCHES, "beans": [{"owner": CONTAINER_TYPE}]}
    with pytest.raises(CatalogError, match="invented-adapters.*beans"):
        _run(tmp_path, _adapter(), _catalog(matches))


def test_a_malformed_method_annotation_is_refused(tmp_path: Path):
    matches = {
        **_ADAPTER_MATCHES,
        "roots": [{**_ADAPTER_MATCHES["roots"][0], "method_annotation": {"annotation": ACTIVATOR}}],
    }
    _refused(tmp_path, matches, "invented-adapters.*method_annotation")


# --- the flow: a spec chain handed to a consumer that continues the walk (spec §5) -----

# An invented flow vocabulary, for the reason every block above invents its own: a
# SOURCE spec (`Sources.listenerSpec(cf, "t")`) handed straight to the flow factory
# (`Flow.from(spec)`), whose own result chain is the flow definition — pass-through
# steps, a `channel(String)` link, a `handle(...)` consumer, a `route(...)` divert — and
# a SINK spec (`Sinks.senderSpec(t).topic("out")`) handed to `handle`. The spec chain
# has no terminal of its own: the consumer IS the terminal, and the walk continues along
# the consumer's chain with the spec's captures (`continue: true`).
SOURCES = "com/acme/flows/Sources#"
SOURCES_TYPE = "com.acme.flows.Sources"
SOURCE_SPEC = "com/acme/flows/SourceSpec#"
SINKS = "com/acme/flows/Sinks#"
SINKS_TYPE = "com.acme.flows.Sinks"
SINK_SPEC = "com/acme/flows/SinkSpec#"
SINK_SPEC_TYPE = "com.acme.flows.SinkSpec"
FLOW = "com/acme/flows/Flow#"
FLOW_TYPE = "com.acme.flows.Flow"
FLOW_DEF = "com/acme/flows/FlowDefinition#"
FLOW_DEF_TYPE = "com.acme.flows.FlowDefinition"
PROPS = "com/acme/flows/Props#"
PROPS_TYPE = "com.acme.flows.Props"
TOPIC = "orders.topic"

_FLOW_MATCHES = {
    "roots": [
        {
            "owner": SOURCES_TYPE,
            "method": "listenerSpec",
            "captures": {"channel": "arg1"},
            "via_argument_of": {"owner": FLOW_TYPE, "method": "from"},
            "continue": True,
        },
        # An OUTBOUND flow reads a channel (§5): `from("ch")`, the link is its source.
        {
            "owner": FLOW_TYPE,
            "method": "from",
            "captures": {"channel_link": "arg0"},
            "direction": "outbound",
        },
        # No `sinks:` word: a sink is a root whose continuation is the flow.
        {
            "owner": SINKS_TYPE,
            "method": "senderSpec",
            "captures": {},
            "via_argument_of": {"owner": FLOW_DEF_TYPE, "method": "handle"},
            "continue": True,
        },
    ],
    "steps": [
        {"method": "handle", "captures": {"handler": "arg0"}},
        {"method": "route", "poisons": ["handler"]},
        {"method": "channel", "captures": {"channel_link": "arg0"}},
        {"method": "topic", "owner": SINK_SPEC_TYPE, "captures": {"channel": "arg0"}},
    ],
    # The `build()` form: a spec that ends in its builder call, handed to `from`.
    "terminal": [
        {
            "method": "build",
            "terminal_via_argument": {"owner": FLOW_TYPE, "method": "from"},
            "continue": True,
        }
    ],
}


def _source_spec(ordinal: int = 0, *, topic: CallArgument | None = None) -> CallSiteFact:
    """`Sources.listenerSpec(cf, "orders.topic")` — a static factory, result 10."""
    return _call(
        CALLER,
        SOURCES,
        "listenerSpec",
        ordinal,
        receiver=None,
        result=10,
        arguments=[
            CallArgument(kind="instance", source=2, symbol="com/acme/flows/Factory#"),
            topic or CallArgument(kind="string", value=TOPIC),
        ],
        invoke_kind="static",
    )


def _from(ordinal: int, source: int, result: int) -> CallSiteFact:
    """`Flow.from(<the value `source` names>)` — the consumer of a spec."""
    return _call(
        CALLER,
        FLOW,
        "from",
        ordinal,
        receiver=None,
        result=result,
        arguments=[CallArgument(kind="unresolved", source=source)],
        invoke_kind="static",
    )


def _flow_steps(*steps: tuple[str, list[CallArgument]], start: int, receiver: int) -> list:
    """The flow definition's own chain: each step on the previous step's result, from
    `receiver`, then `get()` closing it."""
    facts = []
    for ordinal, (name, arguments) in enumerate(steps, start=start):
        facts.append(
            _call(
                CALLER,
                FLOW_DEF,
                name,
                ordinal,
                receiver=receiver,
                result=receiver + 1,
                arguments=arguments,
            )
        )
        receiver += 1
    facts.append(
        _call(CALLER, FLOW_DEF, "get", start + len(steps), receiver=receiver, result=receiver + 1)
    )
    return facts


def test_a_source_spec_handed_to_the_flow_continues_the_walk_to_the_flows_handler(
    tmp_path: Path,
):
    """Spec §5's inbound flow: the spec chain ends WITHOUT a terminal of its own — it is
    consumed as `from(spec)`'s argument, and `continue: true` carries its captures on
    along `from`'s own result chain: a pass-through step, then `handle(lambda)`, whose
    body is the row's handler. ONE row, derived at the continued chain's end, never at
    the spec's."""
    facts = [
        _source_spec(),
        _from(1, source=10, result=11),
        *_flow_steps(
            ("transform", [CallArgument(kind="unresolved")]),
            ("handle", [_lambda()]),
            start=2,
            receiver=11,
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    [row] = _rows(workspace)
    assert _bindings(workspace) == []
    workspace.close()

    assert (row["direction"], row["path"], row["handler"], row["caller"], row["resolution"]) == (
        "inbound",
        TOPIC,
        _MODULE + BODY,
        CALLER,
        "resolved",
    )


def test_a_spec_nothing_consumes_derives_nothing(tmp_path: Path):
    """The near-miss: the same spec, built and never handed to `from` — no consumer, no
    continuation, and a spec chain has no terminal of its own (§5: the consumer is the
    terminal)."""
    workspace = _run(tmp_path, [_source_spec()], _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_divert_before_the_handler_leaves_it_null(tmp_path: Path):
    """§5's `divert` on the continued chain: `route(...)` poisons `handler`, and the
    `handle` after it is not certainly what receives the message (§0b A5)."""
    facts = [
        _source_spec(),
        _from(1, source=10, result=11),
        *_flow_steps(
            ("route", [CallArgument(kind="unresolved")]),
            ("handle", [_lambda()]),
            start=2,
            receiver=11,
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (TOPIC, None, "resolved")


def test_a_channel_step_links_the_channel_and_the_walk_continues_to_the_handler(
    tmp_path: Path,
):
    """§0b A4: `.channel("x")` records the link and the walk continues — the `handle`
    after it is a consumer too. The link makes the chain write its `fed_by` edge (and
    no row of its own, the plan's ruling); the handler folded AFTER the link is a READER
    of that channel — the DSL subscribes the next endpoint to the named channel — so the
    chain writes the `read_by` edge for it as well (§5: a channel-sourced consumer
    writes `read_by`), and the join pass mints the row naming both."""
    facts = [
        _source_spec(),
        _from(1, source=10, result=11),
        *_flow_steps(
            ("channel", [CallArgument(kind="string", value="x")]),
            ("handle", [_lambda()]),
            start=2,
            receiver=11,
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert rows == []
    assert [(b["role"], b["channel"], b["symbol"], b["destination"]) for b in bindings] == [
        ("fed_by", "x", CALLER, TOPIC),
        ("read_by", "x", _MODULE + BODY, None),
    ]


def test_the_join_pass_mints_the_row_for_a_flow_that_links_a_channel_and_handles_it(
    tmp_path: Path,
):
    """Through the pipeline: the `fed_by` and `read_by` the chain wrote become one row —
    the wire from the spec, the handler the lambda's body, `caller` the flow method."""
    facts = [
        _source_spec(),
        _from(1, source=10, result=11),
        *_flow_steps(
            ("channel", [CallArgument(kind="string", value="x")]),
            ("handle", [_lambda()]),
            start=2,
            receiver=11,
        ),
        _body_symbol(),
    ]
    write_fact_file(tmp_path / "facts" / "Wiring.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    assert derive_endpoints(workspace, [_catalog(_FLOW_MATCHES)], capabilities=CAPABILITIES) == []
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["caller"]) == (TOPIC, _MODULE + BODY, CALLER)


def test_a_handler_before_the_link_is_the_wires_consumer_not_the_channels_reader(
    tmp_path: Path,
):
    """The near-miss that keeps the reader honest: `handle(h)` BEFORE `.channel("x")` —
    h consumes what the spec delivers and its OUTPUT feeds x, so h reads nothing from x.
    The link is still recorded (the flow feeds x with what came off the wire); no
    `read_by` is written for h."""
    facts = [
        _source_spec(),
        _from(1, source=10, result=11),
        *_flow_steps(
            ("handle", [_lambda()]),
            ("channel", [CallArgument(kind="string", value="x")]),
            start=2,
            receiver=11,
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    bindings = _bindings(workspace)
    workspace.close()

    assert [(b["role"], b["channel"]) for b in bindings] == [("fed_by", "x")]


def test_a_sink_spec_handed_to_handle_derives_the_outbound_flow(tmp_path: Path):
    """§5's outbound flow: `from("ch")` is a root (`channel_link`, `direction:
    outbound`) and `.handle(sinkSpec)` consumes the sink chain — a root whose
    continuation is the flow. Its captures (`channel: "out"` from `.topic("out")`)
    merge with the consumer's prefix (`from("ch")` before `handle`): ONE outbound row
    `path=out`, `caller` the flow method, and one outbound `fed_by` on `ch`."""
    facts = [
        _call(
            CALLER,
            FLOW,
            "from",
            0,
            receiver=None,
            result=20,
            arguments=[CallArgument(kind="string", value="ch")],
            invoke_kind="static",
        ),
        _call(
            CALLER,
            SINKS,
            "senderSpec",
            1,
            receiver=None,
            result=29,
            arguments=[CallArgument(kind="instance", source=3, symbol="com/acme/flows/Template#")],
            invoke_kind="static",
        ),
        _call(
            CALLER,
            SINK_SPEC,
            "topic",
            2,
            receiver=29,
            result=30,
            arguments=[CallArgument(kind="string", value="out")],
        ),
        _call(
            CALLER,
            FLOW_DEF,
            "handle",
            3,
            receiver=20,
            result=21,
            arguments=[CallArgument(kind="unresolved", source=30)],
        ),
        _call(CALLER, FLOW_DEF, "get", 4, receiver=21, result=22),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    [row] = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert (row["direction"], row["path"], row["handler"], row["caller"], row["resolution"]) == (
        "outbound",
        "out",
        None,
        CALLER,
        "resolved",
    )
    assert (binding["channel"], binding["role"], binding["direction"], binding["destination"]) == (
        "ch",
        "fed_by",
        "outbound",
        "out",
    )


def test_a_build_terminated_spec_continues_exactly_as_a_bare_one(tmp_path: Path):
    """The other form: the spec ends in `build()`, a terminal whose execute-join names
    `from` and carries `continue: true` — `from` consumes the BUILT value, and the walk
    continues from there as it does from the spec itself."""
    facts = [
        _source_spec(),
        _call(CALLER, SOURCE_SPEC, "build", 1, receiver=10, result=11),
        _from(2, source=11, result=12),
        *_flow_steps(("handle", [_lambda()]), start=3, receiver=12),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["caller"]) == (TOPIC, _MODULE + BODY, CALLER)


# --- channel_via on a constructor, by descriptor ---------------------------------------


def _typed_call(
    owner: str,
    name: str,
    ordinal: int,
    *,
    descriptor: str,
    receiver: int | None,
    result: int | None,
    arguments: list,
    invoke_kind: str = "virtual",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=CALLER,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=arguments,
    )


_PROPS_VIA = {
    "owner": PROPS_TYPE,
    "method": "<init>",
    "descriptor": "([Ljava/lang/String;)V",
    "arg": 0,
}
_PROPS_MATCHES = {
    **_FLOW_MATCHES,
    "roots": [
        {**_FLOW_MATCHES["roots"][0], "channel_via": [_PROPS_VIA]},
        *_FLOW_MATCHES["roots"][1:],
    ],
}


def _props_flow(constructor: CallSiteFact) -> list:
    """`listenerSpec(cf, <the constructed props>)` → `from(spec)` → `handle(lambda)`."""
    return [
        constructor,
        _source_spec(1, topic=CallArgument(kind="unresolved", source=40)),
        _from(2, source=10, result=11),
        *_flow_steps(("handle", [_lambda()]), start=3, receiver=11),
        _body_symbol(),
    ]


def test_a_destination_on_a_constructors_varargs_reaches_the_row_through_its_descriptor(
    tmp_path: Path,
):
    """Spec §5: `messageDrivenChannelAdapter(cf, new ContainerProperties("t"))` — the
    topic lives on the constructor's own `String...` argument, one producing-site hop
    (`channel_via` with `method: <init>`), and the DESCRIPTOR tells that constructor
    from its siblings. The varargs slot is one array (9.15): one row per element."""
    constructor = _typed_call(
        PROPS,
        "<init>",
        0,
        descriptor="([Ljava/lang/String;)V",
        receiver=40,
        result=None,
        arguments=[_queue_names("t1", "t2")],
        invoke_kind="special",
    )
    workspace = _run(tmp_path, _props_flow(constructor), _catalog(_PROPS_MATCHES))
    rows = _rows(workspace)
    workspace.close()

    assert [(row["path"], row["handler"], row["resolution"]) for row in rows] == [
        ("t1", _MODULE + BODY, "resolved"),
        ("t2", _MODULE + BODY, "resolved"),
    ]


def test_a_sibling_constructor_with_a_string_at_the_same_position_is_not_the_topic(
    tmp_path: Path,
):
    """The near-miss the descriptor exists for: an overload whose argument 0 is a string
    that is NOT a topic (a `Pattern`'s text, a group id) matches the form's owner, name
    and position — and not its descriptor, so the destination stays unread rather than
    fabricated from it."""
    constructor = _typed_call(
        PROPS,
        "<init>",
        0,
        descriptor="(Ljava/lang/String;I)V",
        receiver=40,
        result=None,
        arguments=[CallArgument(kind="string", value="group"), CallArgument(kind="int", value=3)],
        invoke_kind="special",
    )
    workspace = _run(tmp_path, _props_flow(constructor), _catalog(_PROPS_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


# --- validation of the flow words --------------------------------------------------------


def test_via_argument_of_without_continue_is_refused(tmp_path: Path):
    matches = {
        **_FLOW_MATCHES,
        "roots": [{k: v for k, v in _FLOW_MATCHES["roots"][0].items() if k != "continue"}],
    }
    _refused(tmp_path, matches, "invented-adapters.*via_argument_of")


def test_a_continuing_terminal_with_a_bare_join_is_refused(tmp_path: Path):
    matches = {
        **_FLOW_MATCHES,
        "terminal": [{"method": "build", "terminal_via_argument": True, "continue": True}],
    }
    _refused(tmp_path, matches, "invented-adapters.*continue")


def test_a_channel_via_descriptor_that_is_not_a_string_is_refused(tmp_path: Path):
    matches = {
        **_FLOW_MATCHES,
        "roots": [{**_FLOW_MATCHES["roots"][0], "channel_via": [{**_PROPS_VIA, "descriptor": 3}]}],
    }
    _refused(tmp_path, matches, "invented-adapters.*descriptor")
