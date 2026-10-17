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
from typing import Any

import pytest
import yaml
from test_call_engines import (
    _MODULE,
    FIELD_SOURCES,
    VALUE_ANNOTATION,
    _annotated_field,
    _call,
    _document,
)
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
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource, _hoisted
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
    # **The hoisted identity table, because the engine now resolves through it** (Task 9,
    # the same correction Task 8 made to `test_call_engines`). `YamlCatalogSource.load`
    # hands every real catalog the table its hop declarations hoist into (spec §2a step 1)
    # and `Catalog.value_model` defaults to EMPTY — so a hand-built catalog carrying
    # `channel_via` in `matches` and nothing in `value_model` resolves nothing here while
    # resolving in production, and these tests would be measuring the absence of the table
    # rather than the engine. Built by PRODUCTION's own `_hoisted` rather than a copy of
    # it, so the two spellings cannot drift (§0a) and Task 10's narrowing reaches the tests
    # automatically. A catalog the hoist REFUSES keeps an empty table: the loader rejects
    # such a catalog in production, so a test handing one to the engine is exercising the
    # engine's own validators, which is reached only here.
    source = Path(f"tests/{catalog_id}.yml")
    model: list[dict[str, Any]] = []
    try:
        _hoisted(matches, source, model)
    except CatalogError:
        model = []
    return Catalog(
        id=catalog_id,
        style="fluent",
        protocol="amqp",
        direction=direction,
        requires=("call_site", "string_constants", "chain_reconstruction"),
        matches=matches,
        source=source,
        bean_model=_SPRING if bean_model is None else bean_model,
        value_model=model,
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


def test_a_composed_address_whose_first_half_is_empty_is_the_tail_alone(tmp_path: Path):
    """Final fix wave, item 2. `setExchangeName("").setRoutingKey("orders")` publishes
    through the default exchange, and the destination is `orders` — the spelling
    `single_call._paired_destination` already gives the same wire (§8.1 rule 1), never
    `/orders`, which nothing routes to."""
    facts = _adapter(
        ("setExchangeName", [CallArgument(kind="string", value="")]),
        ("setRoutingKey", [CallArgument(kind="string", value="orders")]),
    )
    workspace = _run(tmp_path, facts, _catalog(_COMPOSED_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == ("orders", "resolved")


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


@pytest.mark.parametrize("where", ["roots", "beans"])
def test_a_poisons_on_a_root_is_refused(tmp_path: Path, where: str):
    """Final fix wave, item 4. `poisons:` is a STEP's word (spec §4): a root starts the
    chain with nothing captured yet to poison, and the entry was rebuilt from named keys
    — so the word loaded, read as valid, and did nothing. Refused by file, on a `roots`
    and on a `beans` entry alike."""
    matches = {
        **_CONTAINER_MATCHES,
        where: [{**_CONTAINER_MATCHES[where][0], "poisons": ["channel"]}],
    }
    _refused(tmp_path, matches, f"invented-adapters.*{where}.*poisons")


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
_PRIMARY = "org/springframework/context/annotation/Primary#"
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


def test_the_primary_container_bean_wins_over_the_one_the_parameter_is_named_after(
    tmp_path: Path,
):
    """Final fix wave, item 1. Two container beans, `container()` marked primary and
    `second()` not, and the adapter's parameter named `second`: the container injects
    the PRIMARY (spring-beans 6.1.6 tries `determinePrimaryCandidate` before it compares
    names — CP-27 row 15), so the row carries the primary's queue, never the queue of
    the bean the parameter happens to be named after — which is what the name rung
    alone folded before this fix."""
    second_bean = WIRING + "second(sig_5ec0nd00)."
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "second")]),
        *_container_bean(("setQueueNames", [_queue_names("primary.q")])),
        _annotated(CONTAINER_BEAN, _PRIMARY),
        _call(
            _MODULE + second_bean,
            CONTAINER,
            "<init>",
            0,
            receiver=7,
            result=None,
            arguments=[CallArgument(kind="parameter", value=0)],
            invoke_kind="special",
        ),
        _call(
            _MODULE + second_bean,
            CONTAINER,
            "setQueueNames",
            1,
            receiver=7,
            result=None,
            arguments=[_queue_names("second.q")],
        ),
        *_bean(second_bean, CONTAINER),
    ]
    workspace = _run(tmp_path, facts, _catalog(_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == ("primary.q", "resolved")


QUEUE = "com/acme/streams/Queue#"
QUEUE_TYPE = "com.acme.streams.Queue"
NAMES = "com/acme/streams/Names#"
NAMES_TYPE = "com.acme.streams.Names"

_LINKED_CONTAINER_MATCHES = {
    **_CONTAINER_MATCHES,
    "steps": [
        *_CONTAINER_MATCHES["steps"],
        {
            "method": "setQueues",
            "captures": {"channel": "arg0"},
            "channel_via": [{"owner": QUEUE_TYPE, "method": "<init>", "arg": 0}],
        },
        {
            "method": "setQueueNamesFrom",
            "captures": {"channel": "arg0"},
            "channel_via": [{"owner": NAMES_TYPE, "method": "of", "arg": 0}],
        },
        {"method": "setQueuesBean", "captures": {"channel": {"bean_via": "arg0"}}},
        {"method": "withQueue", "captures": {"channel": "arg0"}},
    ],
}


def test_a_queue_built_in_the_containers_own_method_reaches_the_row_through_the_hop(
    tmp_path: Path,
):
    """Fix round 1, finding 1: `container.setQueues(new Queue("q"))` — the destination is
    on the constructor's argument, one `channel_via` hop, and that hop is resolved in
    the CONTAINER method's own context (D00 §5: value ids are per method), so the
    adapter's row reads `q` as a literal that carries no id of another method's."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(),
        _call(
            container,
            QUEUE,
            "<init>",
            1,
            receiver=8,
            result=None,
            arguments=[CallArgument(kind="string", value="q")],
            invoke_kind="special",
        ),
        _call(
            container,
            CONTAINER,
            "setQueues",
            2,
            receiver=7,
            result=None,
            arguments=[CallArgument(kind="unresolved", source=8)],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == ("q", "resolved")


def test_a_same_numbered_value_in_the_ADAPTERS_method_is_not_the_containers_queue(
    tmp_path: Path,
):
    """**The negative half of the test above** (GUIDELINES §10), and the one that can fail.

    `_literal_of` exists for a single reason, which its own docstring states: value ids
    are PER METHOD (D00 §5), so a `source` the container's chain captured must never be
    resolved against the ADAPTER method's sites — *"a same-numbered value there is
    unrelated, and reading it fabricates."*

    The test above proves the container's `q` is read. It cannot prove the adapter's
    method was not read, because its facts give the adapter method no value numbered 8 to
    be read INSTEAD. So it passes either way, and the fabrication it describes is
    unguarded.

    Here both methods carry a value 8. The container's is `new Queue("q")`, the one the
    chain actually captured; the adapter's is `new Queue("read-the-wrong-method")`, which
    no chain captured and exists only to be wrong.

    **The decoy is reachable, checked directly rather than assumed**: handing
    `linked_channels` the captured `{kind: unresolved, source: 8}` together with the
    ADAPTER method's sites and `Queue.<init>`'s form answers
    `[(None, "read-the-wrong-method", "resolved")]`. So a reader that resolves this hop in
    the wrong method's context does not merely miss — it publishes a fabricated
    destination at `resolved`, which is spec §7's one failure.

    **This is the guard Task 9 needs before `_literal_of`'s `linked_channels` call becomes
    `resolve_site`.** `resolve_site` is handed a SITE, so resolving in the right method is
    expressible — and silently passing the consuming site instead of the collecting one is
    exactly the mistake that publishes a confident wrong address."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        # The decoy, in the ADAPTER's own method, numbered exactly as the container's is.
        _call(
            CALLER,
            QUEUE,
            "<init>",
            1,
            receiver=8,
            result=None,
            arguments=[CallArgument(kind="string", value="read-the-wrong-method")],
            invoke_kind="special",
        ),
        *_container_bean(),
        _call(
            container,
            QUEUE,
            "<init>",
            1,
            receiver=8,
            result=None,
            arguments=[CallArgument(kind="string", value="q")],
            invoke_kind="special",
        ),
        _call(
            container,
            CONTAINER,
            "setQueues",
            2,
            receiver=7,
            result=None,
            arguments=[CallArgument(kind="unresolved", source=8)],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == ("q", "resolved")
    assert row["path"] != "read-the-wrong-method"


def _queue(container: str, ordinal: int, receiver: int, name: str) -> CallSiteFact:
    return _call(
        container,
        QUEUE,
        "<init>",
        ordinal,
        receiver=receiver,
        result=None,
        arguments=[CallArgument(kind="string", value=name)],
        invoke_kind="special",
    )


def test_every_queue_element_of_a_varargs_setter_reaches_its_own_constructor(tmp_path: Path):
    """Fix round 1 (Task 6, ruling 2): `container.setQueues(new Queue("a"), new Queue("b"))`
    — a varargs slot is ONE `array` argument (9.15) whose elements each carry the
    `source` of their own constructor, while the array itself carries none. The ladder
    walks the elements: one destination per element, through the same `channel_via`
    forms, so the adapter derives two rows."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(),
        _queue(container, 1, 8, "a"),
        _queue(container, 2, 9, "b"),
        _call(
            container,
            CONTAINER,
            "setQueues",
            3,
            receiver=7,
            result=None,
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="unresolved", source=8),
                        CallArgument(kind="unresolved", source=9),
                    ],
                )
            ],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    rows = _rows(workspace)
    workspace.close()

    assert sorted((row["path"], row["resolution"]) for row in rows) == [
        ("a", "resolved"),
        ("b", "resolved"),
    ]


def test_an_element_no_declared_form_reaches_is_unresolved_on_its_own(tmp_path: Path):
    """The near-miss, per element: beside `new Queue("a")`, an element produced by a
    call no `channel_via` form names (`Names.of("q")` is not a `Queue` constructor).
    The readable element is its row; the other is `unresolved` — never the helper's
    argument published as a queue, and never the whole array given up on."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(),
        _queue(container, 1, 8, "a"),
        _call(
            container,
            NAMES,
            "of",
            2,
            receiver=None,
            result=9,
            arguments=[CallArgument(kind="string", value="not-a-queue")],
            invoke_kind="static",
        ),
        _call(
            container,
            CONTAINER,
            "setQueues",
            3,
            receiver=7,
            result=None,
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="unresolved", source=8),
                        CallArgument(kind="unresolved", source=9),
                    ],
                )
            ],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    rows = _rows(workspace)
    workspace.close()

    assert sorted((row["path"] or "", row["resolution"]) for row in rows) == [
        ("", "unresolved"),
        ("a", "resolved"),
    ]


def test_a_container_destination_off_a_getter_is_never_read_off_the_adapters_own_ids(
    tmp_path: Path,
):
    """The near-miss finding 1 closes: the container's `setQueueNamesFrom(props.getQueues())`
    carries `source: 9` in the CONTAINER method; the adapter's method has its own value
    9 — `Names.of("fabricated")`, exactly what the step's `channel_via` names. Read in
    the wrong method the hop would answer `fabricated`; read in the container's it
    answers nothing, and the row is unresolved."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _call(
            CALLER,
            NAMES,
            "of",
            1,
            receiver=None,
            result=9,
            arguments=[CallArgument(kind="string", value="fabricated")],
            invoke_kind="static",
        ),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(),
        _call(
            container,
            "com/acme/streams/Props#",
            "getQueues",
            1,
            receiver=None,
            result=9,
            arguments=[],
        ),
        _call(
            container,
            CONTAINER,
            "setQueueNamesFrom",
            2,
            receiver=7,
            result=None,
            arguments=[CallArgument(kind="unresolved", source=9)],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_a_bean_reference_inside_the_containers_chain_is_not_followed(tmp_path: Path):
    """One hop only (spec §4, finding 2): a `bean_via` met inside a `beans:` chain is
    not resolved — the container's `setQueuesBean(<parameter>)` poisons the capture
    there, and the adapter's destination is unread."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        _declared(CONTAINER_BEAN, parameters=[_parameter(QUEUE, "queue")], returns=CONTAINER),
        _annotated(CONTAINER_BEAN, _BEAN),
        *_bean(WIRING + "queue(sig_0000aaaa).", QUEUE),
        _call(
            container,
            CONTAINER,
            "<init>",
            0,
            receiver=7,
            result=None,
            arguments=[],
            invoke_kind="special",
        ),
        _call(
            container,
            CONTAINER,
            "setQueuesBean",
            1,
            receiver=7,
            result=None,
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_two_ends_of_the_containers_chain_that_disagree_leave_the_destination_unresolved(
    tmp_path: Path,
):
    """Finding 2: the container's chain forks (`c.withQueue("a")`, `c.withQueue("b")` —
    two value-producing calls on one receiver) and its two ends capture different
    destinations; the hop takes neither, never one of them."""
    container = _MODULE + CONTAINER_BEAN
    facts = [
        *_container_adapter(),
        _declared(CALLER_BARE, parameters=[_parameter(CONTAINER, "container")]),
        *_container_bean(),
        _call(
            container,
            CONTAINER,
            "withQueue",
            1,
            receiver=7,
            result=8,
            arguments=[CallArgument(kind="string", value="a")],
        ),
        _call(
            container,
            CONTAINER,
            "withQueue",
            2,
            receiver=7,
            result=9,
            arguments=[CallArgument(kind="string", value="b")],
        ),
    ]
    workspace = _run(tmp_path, facts, _catalog(_LINKED_CONTAINER_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_a_beans_entry_carrying_a_root_only_word_is_refused(tmp_path: Path):
    """A `beans:` chain is walked for its captures alone: a direction, a composition or a
    method annotation on it would be read by nothing, so the file is refused."""
    matches = {
        **_CONTAINER_MATCHES,
        "beans": [{**_CONTAINER_MATCHES["beans"][0], "direction": "outbound"}],
    }
    with pytest.raises(CatalogError, match="invented-adapters.*beans.*direction"):
        _run(tmp_path, _adapter(), _catalog(matches))


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
FROM_STRING = "(Ljava/lang/String;)Lcom/acme/flows/FlowDefinition;"

_FLOW_MATCHES = {
    "roots": [
        {
            "owner": SOURCES_TYPE,
            "method": "listenerSpec",
            "captures": {"channel": "arg1"},
            "via_argument_of": {"owner": FLOW_TYPE, "method": "from"},
            "continue": True,
        },
        # A channel-sourced flow (§5): `from("ch")` CONSUMES the channel — `channel_source`,
        # not a link and not a direction; what the chain then captures decides the row
        # (fix round 1, finding 4). By DESCRIPTOR, as the shipped catalogs key it: the
        # spec form `from(spec)` (a `()V` site here) is the continuation's consumer and
        # not a root of its own — before this, the root matched both and a spec-sourced
        # flow also started a second, source-less chain (final fix wave, item 3).
        {
            "owner": FLOW_TYPE,
            "method": "from",
            "descriptor": FROM_STRING,
            "captures": {"channel_source": "arg0"},
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
    # The flow definition's steps declare their owner, as the real ones do (spec §5:
    # every member of one definition type) — which is also what lets them fold BACKWARD
    # into a continuation's prefix (`_prefix_captures`' owner gate).
    "steps": [
        {"method": "handle", "owner": FLOW_DEF_TYPE, "captures": {"handler": "arg0"}},
        {"method": "route", "owner": FLOW_DEF_TYPE, "poisons": ["handler"]},
        {"method": "channel", "owner": FLOW_DEF_TYPE, "captures": {"channel_link": "arg0"}},
        {"method": "topic", "owner": SINK_SPEC_TYPE, "captures": {"channel": "arg0"}},
    ],
    # The `build()` form: a spec that ends in its builder call, handed to `from`; and
    # `get()`, the flow definition's own end — what a channel-sourced flow (a root of
    # its own, continued by nothing) reaches to derive.
    "terminal": [
        {
            "method": "build",
            "terminal_via_argument": {"owner": FLOW_TYPE, "method": "from"},
            "continue": True,
        },
        "get",
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


def test_a_link_after_the_handler_is_the_handlers_output_channel(tmp_path: Path):
    """Fix round 1, finding 3: the link's meaning depends on where it sits. `handle(h)`
    BEFORE `.channel("x")` — h consumes what the wire delivers (the row, with h) and its
    OUTPUT goes to x: a `sends_to` edge naming h, the table's reserved role's first
    writer. No `fed_by` (the wire does not feed x; h's output does) and no `read_by`."""
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
    [row] = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (TOPIC, _MODULE + BODY, "resolved")
    assert binding == {
        "channel": "x",
        "role": "sends_to",
        "symbol": _MODULE + BODY,
        "protocol": "amqp",
        "direction": "inbound",
        "destination": None,
        "catalog_id": "invented-adapters",
        "resolution": "resolved",
    }


def test_a_link_before_any_handler_is_the_wires_feed_and_writes_no_row(tmp_path: Path):
    """The other order, restated beside its twin: `.channel("x")` before `handle(h)` is
    the SOURCE's feed — `fed_by`, the handler after it a reader, no row of the chain's
    own (the join pass mints it)."""
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
    roles = sorted(b["role"] for b in _bindings(workspace))
    workspace.close()

    assert (rows, roles) == ([], ["fed_by", "read_by"])


# The step model's `channel(MessageChannelSpec)`/`channel(Function)` forms poison the
# link: here the invented `channel` word carries only a spec — a link the walk cannot
# read from there on — and the model's other link word, `fixedSubscriberChannel(String)`,
# is the one that captures (a poison must name a field some step captures). Beside it,
# the compiler's own read failure on the string form.
_SPEC_LINK_MATCHES = {
    **_FLOW_MATCHES,
    "steps": [
        *(step for step in _FLOW_MATCHES["steps"] if step["method"] != "channel"),
        {
            "method": "fixedSubscriberChannel",
            "owner": FLOW_DEF_TYPE,
            "captures": {"channel_link": "arg0"},
        },
        {"method": "channel", "owner": FLOW_DEF_TYPE, "poisons": ["channel_link"]},
    ],
}
_UNREADABLE_LINKS = [
    pytest.param(_FLOW_MATCHES, CallArgument(kind="unresolved"), id="unresolved"),
    pytest.param(_SPEC_LINK_MATCHES, CallArgument(kind="unresolved"), id="poisoned"),
]


@pytest.mark.parametrize(("matches", "link"), _UNREADABLE_LINKS)
def test_a_wire_sourced_flow_whose_link_before_the_handler_is_unreadable_keeps_the_row_without_it(
    tmp_path: Path, matches: dict, link: CallArgument
):
    """Residual fix, item 1, the wire side: `from(spec).channel(<unreadable>).handle(h)`.
    The framework subscribes `h` to the channel the spec builds, never to the wire —
    so `h` is not the wire's consumer and the row keeps `handler` NULL, resolved (the
    wire was read; its consumer was not). No `fed_by` (a channel we cannot name is not
    a channel we can bind, as before) and no `read_by`: the bridge to an anonymous
    channel is the stated boundary."""
    facts = [
        _source_spec(),
        _from(1, source=10, result=11),
        *_flow_steps(("channel", [link]), ("handle", [_lambda()]), start=2, receiver=11),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (TOPIC, None, "resolved")
    assert bindings == []


def test_a_sink_spec_handed_to_handle_derives_the_outbound_flow(tmp_path: Path):
    """§5's outbound flow: `from("ch")` is a root (`channel_source`) and
    `.handle(sinkSpec)` consumes the sink chain — a root whose continuation is the
    flow. Its captures (`channel: "out"` from `.topic("out")`) merge with the
    consumer's prefix (`from("ch")` before `handle`): a channel-sourced chain that
    captured a WIRE is the outbound row — ONE row `path=out`, `caller` the flow method
    — and an outbound `fed_by` on `ch` (§3b: the channel's wire end is known, so the
    question is not asked)."""
    facts = [
        _channel_sourced_flow()[0],
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


def _channel_sourced_flow(*steps: tuple[str, list[CallArgument]]) -> list:
    """`Flow.from("ch")` followed by `steps` and `get()` — a flow nothing continues."""
    return [
        CallSiteFact(
            document_id="doc_1",
            caller=CALLER,
            target=CallTarget(owner=FLOW, name="from", descriptor=FROM_STRING),
            invoke_kind="static",
            ordinal=0,
            receiver=None,
            result=20,
            arguments=[CallArgument(kind="string", value="ch")],
        ),
        *_flow_steps(*steps, start=1, receiver=20),
    ]


def test_a_channel_sourced_flow_with_an_inline_handler_is_the_channels_reader(
    tmp_path: Path,
):
    """§5: `from("ch").handle(h)` is a channel CONSUMER, not a wire — it writes
    `read_by(ch, h)` and no row, so the adapter feeding `ch` gains h as a handler
    through the join pass."""
    facts = [*_channel_sourced_flow(("handle", [_lambda()])), _body_symbol()]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert rows == []
    assert (binding["role"], binding["channel"], binding["symbol"], binding["direction"]) == (
        "read_by",
        "ch",
        _MODULE + BODY,
        "inbound",
    )


def test_a_channel_sourced_flow_that_links_before_its_handler_reads_the_link(
    tmp_path: Path,
):
    """Final fix wave, item 3. `from("a").channel("b").handle(h)`: the framework
    subscribes `h` to `b` (M4's rule — a handler after a link reads the LINKED channel),
    and `a → b` is the bridge the boundary already states. One edge, `read_by(b, h)`;
    nothing about `a`, and never `read_by(a, h)`, which would attribute the handler to
    the source."""
    facts = [
        *_channel_sourced_flow(
            ("channel", [CallArgument(kind="string", value="b")]), ("handle", [_lambda()])
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    [binding] = _bindings(workspace)
    workspace.close()

    assert rows == []
    assert (binding["role"], binding["channel"], binding["symbol"]) == (
        "read_by",
        "b",
        _MODULE + BODY,
    )


@pytest.mark.parametrize(("matches", "link"), _UNREADABLE_LINKS)
def test_a_channel_sourced_flow_whose_link_before_the_handler_is_unreadable_writes_nothing(
    tmp_path: Path, matches: dict, link: CallArgument
):
    """Residual fix, item 1: `from("a").channel(<unreadable>).handle(h)`. The framework
    subscribes `h` to the channel the spec builds, not to `a` — so `read_by(a, h)` would
    be a wrong edge, and the link's name is what the walk cannot read. Nothing is
    written: no edge and no row (the bridge to an anonymous channel is the stated
    boundary). Before the fix the handler was credited to the source."""
    facts = [
        *_channel_sourced_flow(("channel", [link]), ("handle", [_lambda()])),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    rows = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (rows, bindings) == ([], [])


def test_a_channel_sourced_flow_that_links_before_and_after_its_handler_writes_both_edges(
    tmp_path: Path,
):
    """`OI-115`'s shape under a channel source: `from("a").channel("b").handle(h)
    .channel("c")`. The link BEFORE `h` is what `h` reads and the link AFTER it is
    where `h`'s output goes — two markers, so the later link does not reset the
    reader: `read_by(b, h)` and `sends_to(c, h)`, nothing for `a` (the bridge), and
    never `read_by(a, h)`, which the reset used to write."""
    facts = [
        *_channel_sourced_flow(
            ("channel", [CallArgument(kind="string", value="b")]),
            ("handle", [_lambda()]),
            ("channel", [CallArgument(kind="string", value="c")]),
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    edges = sorted((b["role"], b["channel"], b["symbol"]) for b in _bindings(workspace))
    workspace.close()

    assert rows == []
    assert edges == [("read_by", "b", _MODULE + BODY), ("sends_to", "c", _MODULE + BODY)]


def test_a_channel_sourced_flow_that_links_after_its_handler_reads_the_source_and_sends_to_the_link(
    tmp_path: Path,
):
    """The twin without a first link: `from("ch").handle(h).channel("c")` — `h` reads
    the source (no link preceded it) and its output goes to `c`, the `sends_to` edge
    the sourced branch now writes beside the reader."""
    facts = [
        *_channel_sourced_flow(
            ("handle", [_lambda()]), ("channel", [CallArgument(kind="string", value="c")])
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    edges = sorted((b["role"], b["channel"], b["symbol"]) for b in _bindings(workspace))
    workspace.close()

    assert rows == []
    assert edges == [("read_by", "ch", _MODULE + BODY), ("sends_to", "c", _MODULE + BODY)]


def test_a_bridge_between_two_channels_writes_nothing(tmp_path: Path):
    """The stated boundary: `from("a").channel("b")` — a channel-sourced flow that
    captured neither a wire nor a handler says nothing about any wire."""
    facts = _channel_sourced_flow(("channel", [CallArgument(kind="string", value="b")]))
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    rows = _rows(workspace)
    bindings = _bindings(workspace)
    workspace.close()

    assert (rows, bindings) == ([], [])


def test_a_channel_sourced_flow_that_links_and_reaches_a_wire_writes_both_edges(
    tmp_path: Path,
):
    """`channel_source` and `channel_link` on one chain (source `ch`, feeding `b`) with
    a sink's wire: the outbound row, an outbound `fed_by` for the source AND one for
    the link — each edge by its own rule."""
    facts = [
        *_channel_sourced_flow(("channel", [CallArgument(kind="string", value="b")]))[:2],
        _call(
            CALLER,
            SINKS,
            "senderSpec",
            2,
            receiver=None,
            result=29,
            arguments=[CallArgument(kind="instance", source=3, symbol="com/acme/flows/Template#")],
            invoke_kind="static",
        ),
        _call(
            CALLER,
            SINK_SPEC,
            "topic",
            3,
            receiver=29,
            result=30,
            arguments=[CallArgument(kind="string", value="out")],
        ),
        _call(
            CALLER,
            FLOW_DEF,
            "handle",
            4,
            receiver=21,
            result=22,
            arguments=[CallArgument(kind="unresolved", source=30)],
        ),
        _call(CALLER, FLOW_DEF, "get", 5, receiver=22, result=23),
    ]
    workspace = _run(tmp_path, facts, _catalog(_FLOW_MATCHES))
    [row] = _rows(workspace)
    edges = sorted(
        (b["role"], b["channel"], b["direction"], b["destination"]) for b in _bindings(workspace)
    )
    workspace.close()

    assert (row["direction"], row["path"]) == ("outbound", "out")
    assert edges == [("fed_by", "b", "outbound", "out"), ("fed_by", "ch", "outbound", "out")]


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


# --- roots and steps by descriptor (spec 2026-09-21 §5, Task 6) -------------------------
#
# `Kafka.messageDrivenChannelAdapter` has ten overloads at 6.2.4 and the topic list sits
# at slot 1 in `(ConsumerFactory, String...)` and at slot 2 in `(ConsumerFactory,
# ListenerMode, String...)` (CP-27 row 6); `handle` has thirteen on the base definition
# and two more on the subclass, the handler at slot 0 in `handle(GenericHandler)` and at
# slot 1 in `handle(Class, GenericHandler)` (CP-27 rows 3, 3b). A root or step matched by
# owner and name alone reads one slot for every overload, so a root or step may declare a
# `descriptor:` and match only a site whose own parameter types are the declared ones —
# `single_call`'s rule, compared on the parameter portion (F2 §4.1): a return type is not
# method identity and moves between framework releases.

_BY_LIST = "(Lcom/acme/Factory;[Ljava/lang/String;)Lcom/acme/flows/SourceSpec;"
_BY_MODE_AND_LIST = (
    "(Lcom/acme/Factory;Lcom/acme/Mode;[Ljava/lang/String;)Lcom/acme/flows/SourceSpec;"
)
_BY_PATTERN = "(Lcom/acme/Factory;Ljava/util/regex/Pattern;)Lcom/acme/flows/SourceSpec;"
_HANDLE_LAMBDA = "(Lcom/acme/Handler;)Lcom/acme/flows/FlowDefinition;"
_HANDLE_TYPED = "(Ljava/lang/Class;Lcom/acme/Handler;)Lcom/acme/flows/FlowDefinition;"

_DESCRIPTOR_MATCHES = {
    **_FLOW_MATCHES,
    "roots": [
        {
            "owner": SOURCES_TYPE,
            "method": "listenerSpec",
            "descriptor": _BY_LIST,
            "captures": {"channel": "arg1"},
            "via_argument_of": {"owner": FLOW_TYPE, "method": "from"},
            "continue": True,
        },
        {
            "owner": SOURCES_TYPE,
            "method": "listenerSpec",
            "descriptor": _BY_MODE_AND_LIST,
            "captures": {"channel": "arg2"},
            "via_argument_of": {"owner": FLOW_TYPE, "method": "from"},
            "continue": True,
        },
    ],
    "steps": [
        {
            "method": "handle",
            "owner": FLOW_DEF_TYPE,
            "descriptor": _HANDLE_LAMBDA,
            "captures": {"handler": "arg0"},
        },
        {
            "method": "handle",
            "owner": FLOW_DEF_TYPE,
            "descriptor": _HANDLE_TYPED,
            "captures": {"handler": "arg1"},
        },
    ],
}


def _site(
    owner: str,
    name: str,
    descriptor: str,
    ordinal: int,
    *,
    receiver: int | None,
    result: int | None,
    arguments: list[CallArgument],
    invoke_kind: str = "virtual",
) -> CallSiteFact:
    """`_call` with the site's own descriptor — the one thing this section is about."""
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


def _topics(*topics: str) -> CallArgument:
    return CallArgument(
        kind="array", elements=[CallArgument(kind="string", value=topic) for topic in topics]
    )


def test_a_root_matches_only_the_overload_whose_descriptor_it_declares(tmp_path: Path):
    """The `(factory, mode, topics)` overload carries its topics at slot 2. Read by name
    alone, the first root (`channel: arg1`) would take the mode enum for the destination
    and derive an unresolved row; by descriptor the second root reads slot 2."""
    facts = [
        _site(
            SOURCES,
            "listenerSpec",
            _BY_MODE_AND_LIST,
            0,
            receiver=None,
            result=10,
            arguments=[
                CallArgument(kind="instance", source=2, symbol="com/acme/Factory#"),
                CallArgument(kind="unresolved"),
                _topics(TOPIC),
            ],
            invoke_kind="static",
        ),
        _from(1, source=10, result=11),
        _site(FLOW_DEF, "handle", _HANDLE_LAMBDA, 2, receiver=11, result=12, arguments=[_lambda()]),
        _call(CALLER, FLOW_DEF, "get", 3, receiver=12, result=13),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_DESCRIPTOR_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (TOPIC, _MODULE + BODY, "resolved")


def test_a_site_whose_descriptor_matches_no_declared_root_starts_nothing(tmp_path: Path):
    """The near-miss: the `(factory, Pattern)` overload, same owner and name, a descriptor
    neither root declares — no chain starts, nothing derives, even though a `from` and a
    handler follow. A catalog that wants that overload declares it."""
    facts = [
        _site(
            SOURCES,
            "listenerSpec",
            _BY_PATTERN,
            0,
            receiver=None,
            result=10,
            arguments=[
                CallArgument(kind="instance", source=2, symbol="com/acme/Factory#"),
                CallArgument(kind="unresolved", source=7),
            ],
            invoke_kind="static",
        ),
        _from(1, source=10, result=11),
        _site(FLOW_DEF, "handle", _HANDLE_LAMBDA, 2, receiver=11, result=12, arguments=[_lambda()]),
        _call(CALLER, FLOW_DEF, "get", 3, receiver=12, result=13),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_DESCRIPTOR_MATCHES))
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_root_descriptor_is_compared_on_its_parameter_types_alone(tmp_path: Path):
    """F2 §4.1's rule, kept here: a site whose overload returns a DIFFERENT type than the
    catalog's descriptor spells still matches — the parameter list is the identity."""
    facts = [
        _site(
            SOURCES,
            "listenerSpec",
            _BY_LIST.replace("SourceSpec", "OlderSourceSpec"),
            0,
            receiver=None,
            result=10,
            arguments=[
                CallArgument(kind="instance", source=2, symbol="com/acme/Factory#"),
                _topics(TOPIC),
            ],
            invoke_kind="static",
        ),
        _from(1, source=10, result=11),
        _site(FLOW_DEF, "handle", _HANDLE_LAMBDA, 2, receiver=11, result=12, arguments=[_lambda()]),
        _call(CALLER, FLOW_DEF, "get", 3, receiver=12, result=13),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_DESCRIPTOR_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"]) == (TOPIC, _MODULE + BODY)


def test_a_step_matches_only_the_overload_whose_descriptor_it_declares(tmp_path: Path):
    """`handle(Class, handler)` carries the handler at slot 1. Read by name alone, the
    first `handle` step would take the class literal for the handler and read NULL; by
    descriptor the second step reads slot 1 and the row carries the lambda's body."""
    facts = [
        _site(
            SOURCES,
            "listenerSpec",
            _BY_LIST,
            0,
            receiver=None,
            result=10,
            arguments=[
                CallArgument(kind="instance", source=2, symbol="com/acme/Factory#"),
                _topics(TOPIC),
            ],
            invoke_kind="static",
        ),
        _from(1, source=10, result=11),
        _site(
            FLOW_DEF,
            "handle",
            _HANDLE_TYPED,
            2,
            receiver=11,
            result=12,
            arguments=[CallArgument(kind="class", symbol="java/lang/String#"), _lambda()],
        ),
        _call(CALLER, FLOW_DEF, "get", 3, receiver=12, result=13),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(_DESCRIPTOR_MATCHES))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"]) == (TOPIC, _MODULE + BODY)


def test_a_step_whose_descriptor_matches_no_declared_step_is_an_undeclared_member(
    tmp_path: Path,
):
    """A `handle` overload the model does not declare, on an owner `undeclared_steps`
    lists, is the divert every unknown member is: `handler` poisoned, the row resolved
    with `handler` NULL — never the wrong slot read as the handler."""
    matches = {
        **_DESCRIPTOR_MATCHES,
        "undeclared_steps": {"owner": FLOW_DEF_TYPE, "poisons": ["handler"]},
    }
    facts = [
        _site(
            SOURCES,
            "listenerSpec",
            _BY_LIST,
            0,
            receiver=None,
            result=10,
            arguments=[
                CallArgument(kind="instance", source=2, symbol="com/acme/Factory#"),
                _topics(TOPIC),
            ],
            invoke_kind="static",
        ),
        _from(1, source=10, result=11),
        _site(
            FLOW_DEF,
            "handle",
            "(Ljava/lang/Object;Ljava/lang/String;)Lcom/acme/flows/FlowDefinition;",
            2,
            receiver=11,
            result=12,
            arguments=[_lambda(), CallArgument(kind="string", value="onMessage")],
        ),
        _call(CALLER, FLOW_DEF, "get", 3, receiver=12, result=13),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (TOPIC, None, "resolved")


def test_a_root_descriptor_that_is_not_a_method_descriptor_is_refused(tmp_path: Path):
    matches = {
        **_DESCRIPTOR_MATCHES,
        "roots": [{**_DESCRIPTOR_MATCHES["roots"][0], "descriptor": "listenerSpec(Factory)"}],
    }
    _refused(tmp_path, matches, "invented-adapters.*descriptor")


def test_a_step_descriptor_that_is_not_a_string_is_refused(tmp_path: Path):
    matches = {
        **_DESCRIPTOR_MATCHES,
        "steps": [{**_DESCRIPTOR_MATCHES["steps"][0], "descriptor": 7}],
    }
    _refused(tmp_path, matches, "invented-adapters.*descriptor")


def test_two_steps_of_one_name_and_owner_need_distinct_descriptors(tmp_path: Path):
    """The existing refusal, one dimension finer: two `handle` steps on one owner are
    told apart by descriptor, and one of them declaring none would match every overload
    — the silent last-wins the refusal exists to prevent."""
    matches = {
        **_DESCRIPTOR_MATCHES,
        "steps": [
            _DESCRIPTOR_MATCHES["steps"][0],
            {k: v for k, v in _DESCRIPTOR_MATCHES["steps"][1].items() if k != "descriptor"},
        ],
    }
    _refused(tmp_path, matches, "invented-adapters.*steps named `handle`")


# --- the field ladder's parameter rung, in this engine ----------------------------------


def _value_parameter(erased: str, expression: str) -> DeclaredParameter:
    return DeclaredParameter(
        name="subscription",
        type=TypeRef(symbol=erased),
        erased_symbol=erased,
        annotations=[AnnotationUse(annotation=VALUE_ANNOTATION, args={"value": expression})],
    )


def test_a_destination_handed_in_as_an_annotated_parameter_reads_its_expression(
    tmp_path: Path,
):
    """Spec §3c: `new Adapter(ops, subscription)` where `subscription` is the constructing
    method's own `@Value("${probe.subscription}")` parameter — the field ladder's rung 2a,
    which reads the parameter's annotation off THAT method's declared signature and so
    needs the site's own caller. The row carries the expression, resolved, exactly as a
    literal would; `resolved_peers` substitutes it per environment downstream."""
    matches = {**_ADAPTER_MATCHES, "field_sources": FIELD_SOURCES}
    facts = [
        *_adapter(
            ("onMessage", [_lambda()]),
            subscription=CallArgument(kind="parameter", value=1),
        ),
        _declared(
            CALLER[len(_MODULE) :],
            parameters=[
                _parameter("com/acme/streams/Ops#", "ops"),
                _value_parameter("java/lang/String#", "${probe.subscription}"),
            ],
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["resolution"]) == (
        "${probe.subscription}",
        _MODULE + BODY,
        "resolved",
    )


def test_a_parameter_captured_inside_a_lambda_body_is_never_read_against_the_enclosing_method(
    tmp_path: Path,
):
    """The soundness half (Task 4's `bean_via` marker, the same reason): a lambda body's
    `parameter 1` is an index into the LAMBDA's own signature — a captured variable, the
    builder — and reading it against the enclosing method, whose parameter 1 happens to
    carry a `@Value`, would fabricate that method's expression as this chain's
    destination. The lambda's own declaration carries no annotation, so the read is
    honest: `path` NULL, `unresolved`."""
    matches = {
        **_ADAPTER_MATCHES,
        "steps": [
            *_ADAPTER_MATCHES["steps"],
            # `apply(lambda)` hands the lambda in; its body's `configure(x)` is the read.
            {"method": "apply", "captures": {"channel": "arg0"}},
            {"method": "configure", "captures": {"channel": "arg0"}},
        ],
        "field_sources": FIELD_SOURCES,
    }
    body = "com/acme/streams/Wiring#lambda$inbound$1(Lcom/acme/streams/Config;)V."
    facts = [
        *_adapter(("apply", [CallArgument(kind="lambda", source=9, symbol=body)])),
        _call(
            _MODULE + body,
            "com/acme/streams/Config#",
            "configure",
            0,
            receiver=None,
            result=None,
            arguments=[CallArgument(kind="parameter", value=1)],
        ),
        _declared(
            CALLER[len(_MODULE) :],
            parameters=[
                _parameter("com/acme/streams/Ops#", "ops"),
                _value_parameter("java/lang/String#", "${probe.subscription}"),
            ],
        ),
        _declared(body, parameters=[_parameter("com/acme/streams/Config#", "config")]),
        _body_symbol(body),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    [row] = _rows(workspace)
    workspace.close()

    assert (row["path"], row["resolution"]) == (None, "unresolved")


def test_every_element_of_a_varargs_destination_goes_through_the_field_ladder(tmp_path: Path):
    """Spec §3c: a vararg array is one row per element AND every destination goes through
    the ladder — so `inboundAdapter(cf, "literal.q", this.valueQueue, paramQueue)` is three
    rows: the literal, the field's `@Value` expression (rung 1) and the parameter's (rung
    2a), each resolved. Before this the ladder ran on the whole argument, an array named
    no expression, and every varargs registration fed from configuration was `unresolved`
    — the dominant AMQP and Kafka DSL form."""
    matches = {**_ADAPTER_MATCHES, "field_sources": FIELD_SOURCES}
    field = "com/acme/streams/Wiring#valueQueue."
    facts = [
        *_adapter(
            ("onMessage", [_lambda()]),
            subscription=CallArgument(
                kind="array",
                elements=[
                    CallArgument(kind="string", value="literal.q"),
                    CallArgument(kind="field", symbol=field),
                    CallArgument(kind="parameter", value=1),
                ],
            ),
        ),
        *_annotated_field(field, "${probe.value-queue}"),
        _declared(
            CALLER[len(_MODULE) :],
            parameters=[
                _parameter("com/acme/streams/Ops#", "ops"),
                _value_parameter("java/lang/String#", "${probe.param-queue}"),
            ],
        ),
        _body_symbol(),
    ]
    workspace = _run(tmp_path, facts, _catalog(matches))
    rows = _rows(workspace)
    workspace.close()

    assert sorted((row["path"], row["resolution"]) for row in rows) == [
        ("${probe.param-queue}", "resolved"),
        ("${probe.value-queue}", "resolved"),
        ("literal.q", "resolved"),
    ]
    assert {row["handler"] for row in rows} == {_MODULE + BODY}


# --- vertx-eventbus-chain: the SHIPPED catalog, and the terminal that is its whole point


_VERTX_BUS = "io.vertx.core.eventbus.EventBus"
_VERTX_CONSUMER = "io.vertx.core.eventbus.MessageConsumer"
_VERTX_CONSUMER_1 = "(Ljava/lang/String;)Lio/vertx/core/eventbus/MessageConsumer;"
_VERTX_HANDLER = "(Lio/vertx/core/Handler;)Lio/vertx/core/eventbus/MessageConsumer;"
_VERTX_BUFFER = "(I)Lio/vertx/core/eventbus/MessageConsumer;"
_VERTX_CALLER = _MODULE + "com/acme/eb/OrderBus#receiveOrders()."
_VERTX_BODY = "com/acme/eb/OrderBus#lambda$receiveOrders$0(Lio/vertx/core/eventbus/Message;)V."


def _vertx_call(
    owner: str,
    name: str,
    descriptor: str,
    ordinal: int,
    receiver: int | None,
    result: int | None,
    arguments: list | None = None,
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=_VERTX_CALLER,
        target=CallTarget(owner=owner.replace(".", "/") + "#", name=name, descriptor=descriptor),
        invoke_kind="interface",
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=arguments or [],
    )


def _vertx_chain(*, with_handler: bool, owner: str = _VERTX_BUS) -> list:
    """`bus.consumer("orders.twostep")` followed either by `.handler(lambda)` — the
    registration — or by `.setMaxBufferedMessages(16)`, an undeclared step that passes
    through and ends the chain short of any terminal."""
    facts = [
        _vertx_call(
            owner,
            "consumer",
            _VERTX_CONSUMER_1,
            0,
            receiver=1,
            result=5,
            arguments=[CallArgument(kind="string", value="orders.twostep")],
        )
    ]
    if with_handler:
        facts.append(
            _vertx_call(
                _VERTX_CONSUMER,
                "handler",
                _VERTX_HANDLER,
                1,
                receiver=5,
                result=6,
                arguments=[CallArgument(kind="lambda", source=9, symbol=_VERTX_BODY)],
            )
        )
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + _VERTX_BODY,
                construct_kind=ConstructKind.METHOD,
            )
        )
    else:
        facts.append(
            _vertx_call(
                _VERTX_CONSUMER,
                "setMaxBufferedMessages",
                _VERTX_BUFFER,
                1,
                receiver=5,
                result=6,
                arguments=[CallArgument(kind="int", value=16)],
            )
        )
    return facts


def _vertx_rows(tmp_path: Path, *, with_handler: bool, owner: str = _VERTX_BUS) -> list[tuple]:
    catalog = next(
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "vertx-eventbus-chain"
    )
    workspace = _run(tmp_path, _vertx_chain(with_handler=with_handler, owner=owner), catalog)
    rows = sorted(
        (
            str(row["direction"]),
            str(row["protocol"]),
            str(row["path"]),
            row["handler"] and str(row["handler"]),
            str(row["resolution"]),
        )
        for row in _rows(workspace)
    )
    workspace.close()
    return rows


def test_a_vertx_consumer_given_a_handler_registers_and_carries_it(tmp_path: Path):
    """The positive the near-miss below is measured against. `consumer(addr)` roots the
    chain and `.handler(h)` is the declared terminal, so the row derives with the
    address from the root and the handler the FULL symbol of the lambda's body."""
    assert _vertx_rows(tmp_path, with_handler=True) == [
        ("inbound", "eventbus", "orders.twostep", _MODULE + _VERTX_BODY, "resolved")
    ]


@pytest.mark.declines("vertx-eventbus-chain")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_vertx_consumer_on_an_applications_own_type_derives_nothing(tmp_path: Path):
    """§10 near-miss for the ROOT OWNER conjunct.

    Every other conjunct holds — the method name, the erased descriptor CP-31 read off
    both versions, a literal address at argument 0, and a real `.handler(lambda)` step
    reaching the declared terminal. Only the type the chain roots ON differs, and a
    module's own `consumer(String)` helper that hands back something handler-shaped is
    the ordinary way that happens. Without the owner conjunct that helper's argument 0
    would publish an event-bus address at `resolved`/`compiler`, on evidence about a type
    this catalog never read."""
    assert _vertx_rows(tmp_path, with_handler=True, owner="com.acme.eb.OwnBus") == []


@pytest.mark.declines("vertx-eventbus-chain")
@pytest.mark.pins("fluent.no-terminal-no-row")
def test_a_vertx_consumer_never_given_a_handler_derives_nothing(tmp_path: Path):
    """The TERMINAL conjunct, and the measured reason this catalog is shaped around it.

    MEASURED (CP-31 Q4, vertx-core 4.5.10 and 5.0.0, byte-identical):
    `EventBusImpl.consumer(String, Handler)` calls `consumer(String)` at offset 9 and
    `MessageConsumer.handler` at offset 15 — the registration is inside `handler`. So a
    `MessageConsumer` built and configured but never handed a handler receives no
    message at all, and a row for it would publish an endpoint nothing serves at
    `resolved`/`compiler`. Every other conjunct holds here: the root's owner, its erased
    descriptor and its literal address are the same ones the positive above carries, and
    the only difference is that the chain ends on an undeclared step instead of on
    `handler`.

    `fluent.no-terminal-no-row` is the guard, added in this task's fix round: the registry
    carried four `fluent.*` guards and none covered the terminal conjunct — the one rule
    this catalog exists for — so two tests asserted the behaviour and nothing proved
    either would notice a regression. Disabling it derives a row for this input, which is
    the false positive M6 forbids."""
    assert _vertx_rows(tmp_path, with_handler=False) == []
