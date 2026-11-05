"""Spring application events are in-process dispatch (spec 2026-11-05 §4 item 5): a
`publishEvent(e)` hands `e` to the context, and every listener whose event type `e`'s class
is assignable to runs. Each listener is a `dispatch_registrations` row keyed by that type,
`match: all`; each publish is a hop per listener it reaches, under `in_process`. Never an
endpoint row.

The second user of the mechanism Task 1 built for actors, so nothing here is written for
Spring: the listeners are read by the annotation engine's own words (`request_body` picks the
payload parameter, `path_from` reads `@EventListener(classes = …)`) and the interface form by
the implementing class's own method, its compiler bridge carried to the method it forwards to.

**Not a document check.** Real bytecode (`fixtures/orders-events`, Spring Boot 4.0.0), real
pipeline, assertions on derived rows.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.query.trace import trace_of
from sextant.application.resolve.roots import Root
from sextant.cli.app import cli
from sextant.domain.closed_sets import RootKind, TraceStop
from sextant.domain.symbols import bare_descriptor, method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-events"
_EVENT = "com/acme/events/OrderPlaced#"


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace_dir = tmp_path_factory.mktemp("orders-events")
    compile_fixture(_ROOT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(_ROOT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return workspace_dir / "workspace.duckdb"


def _short(symbol: object) -> str | None:
    """`Class#method` (a type: `Class`), module, package and signature left out."""
    if symbol is None:
        return None
    return bare_descriptor(str(symbol)).rsplit("/", 1)[-1].split("(")[0].removesuffix("#")


@pytest.fixture(scope="module")
def tables(analyzed: Path) -> dict[str, list[dict]]:
    workspace = DuckDbWorkspace(analyzed)
    try:
        return {
            "hops": workspace.query("hops"),
            "registrations": workspace.query("dispatch_registrations"),
            "endpoints": workspace.query("endpoints"),
        }
    finally:
        workspace.close()


def _hops_from(tables: dict, caller: str) -> set[tuple]:
    """`(protocol, path, handler)` of every hop the method `caller` makes, shortened."""
    return {
        (str(row["protocol"]), _short(row["path"]), _short(row["handler"]))
        for row in tables["hops"]
        if _short(row["caller"]) == caller
    }


_EVERY_LISTENER = {
    ("in_process", "OrderPlaced", "AuditListener#on"),
    ("in_process", "OrderPlaced", "AnyListener#on"),
    ("in_process", "OrderPlaced", "ClassesListener#on"),
    ("in_process", "OrderPlaced", "TxListener#on"),
    ("in_process", "OrderPlaced", "MailListener#onApplicationEvent"),
}


@pytest.mark.pins("annotation-registrations.an-annotation-catalog-READS-registrations")
def test_a_published_event_hops_to_every_listener_of_its_class(tables):
    """`publisher.publishEvent(new OrderPlaced(this, id))` reaches every listener (`match:
    all`): `@EventListener on(OrderPlaced)`, `on(Object)`, `@EventListener(classes =
    OrderPlaced.class) on()`, `@TransactionalEventListener on(OrderPlaced)` and
    `ApplicationListener<OrderPlaced>`. The same publish through an `ApplicationContext`,
    which inherits `publishEvent`, reaches the same five."""
    assert _hops_from(tables, "OrderService#place") == _EVERY_LISTENER
    assert _hops_from(tables, "OrderService#placeThroughContext") == _EVERY_LISTENER


@pytest.mark.pins("annotation-registrations.the-PAYLOAD-parameter-keys-the-listener")
def test_each_event_reaches_only_the_listeners_of_its_class(tables):
    """The key decides: `publishEvent(new OrderShipped(id))` reaches `ShippingListener` and
    the listener of `Object`, none of `OrderPlaced`'s; `publishEvent(new Note())`, a plain
    object through `publishEvent(Object)`, reaches only the listener of `Object`; and no
    `OrderPlaced` publish reaches `ShippingListener`. A fan-out ignoring the key fails all
    three."""
    assert _hops_from(tables, "OrderService#ship") == {
        ("in_process", "OrderShipped", "ShippingListener#on"),
        ("in_process", "OrderShipped", "AnyListener#on"),
    }
    assert _hops_from(tables, "OrderService#note") == {("in_process", "Note", "AnyListener#on")}
    assert not any(
        handler == "ShippingListener#on"
        for _, _, handler in _hops_from(tables, "OrderService#place")
    )


@pytest.mark.pins("dispatch-hops.the-declared-CONFORMANCE-extends-a-values-ancestry")
def test_a_listener_of_a_supertype_receives(tables):
    """`@EventListener on(Object e)` is keyed by `Object`, and an `OrderPlaced` is one:
    `match: all` reads assignability, so the supertype listener is reached and does not hide
    the others."""
    keys = {
        _short(row["handler"]): row["key_type"]
        for row in tables["registrations"]
        if _short(row["handler"]) == "AnyListener#on"
    }
    assert keys == {"AnyListener#on": "java/lang/Object#"}
    assert ("in_process", "OrderPlaced", "AnyListener#on") in _hops_from(
        tables, "OrderService#place"
    )


@pytest.mark.pins("dispatch-hops.a-value-a-MODULE-FACTORY-returns-is-read-through-it")
def test_an_event_a_module_factory_returns_is_read_through_it(tables):
    """`OrderPlaced event = OrderPlaced.of(this, id); publisher.publishEvent(event)`: the
    value is a static call's result, and the module declares that method's body, which
    returns `new OrderPlaced(…)` (the shape apollo-portal's `ConfigPublishEvent.instance()`
    takes, seven of its seventeen publish sites). The code is here, so the class is read
    through it (ruled 2026-11-02: unknown only where code is absent)."""
    assert _hops_from(tables, "OrderService#placeThroughFactory") == _EVERY_LISTENER


def test_an_unread_event_class_is_a_stop(tables, analyzed: Path):
    """`publishEvent(event)` with `event` a parameter: its class is not read here, so the hop
    is one stop with no path and no handler, never a hop to every listener. The trace says
    why in its step."""
    assert _hops_from(tables, "OrderService#republish") == {("in_process", None, None)}
    workspace = DuckDbWorkspace(analyzed)
    try:
        [republish] = [
            str(row["method"])
            for row in workspace.query("method_returns")
            if "OrderService#republish(" in str(row["method"])
        ]
        trace = trace_of(workspace, Root(handler=republish, kind=RootKind.INBOUND_ENDPOINT))
    finally:
        workspace.close()
    assert [(step.via, step.stop) for step in trace.steps] == [
        ("in_process (key not read)", TraceStop.BOUNDARY)
    ]


@pytest.mark.pins("dispatch-implementations.the-BRIDGE-is-carried-to-the-method-it-forwards-to")
def test_an_application_listener_is_keyed_by_its_own_method(tables):
    """`MailListener implements ApplicationListener<OrderPlaced>`: javac writes
    `onApplicationEvent(OrderPlaced)` and a synthetic bridge `onApplicationEvent(
    ApplicationEvent)` forwarding to it. The registration is the method the class wrote,
    keyed by ITS parameter's type; the bridge, keyed `ApplicationEvent`, would reach every
    event the context publishes."""
    rows = [
        (row["key_type"], str(row["handler"]), row["match"])
        for row in tables["registrations"]
        if _short(row["handler"]) == "MailListener#onApplicationEvent"
    ]
    assert len(rows) == 1
    [(key_type, handler, match)] = rows
    assert key_type == _EVENT
    assert match == "all"
    assert bare_descriptor(handler) == method_descriptor(
        "com/acme/events/MailListener#", "onApplicationEvent", f"(L{_EVENT[:-1]};)V"
    )


def test_the_listeners_are_registrations_not_endpoint_rows(tables):
    """A dispatch is a hop, never an endpoint row (spec 2026-11-05 §1): the listeners mint
    no `in_process` row, and the classes listener is keyed by the class its annotation
    names."""
    assert [row for row in tables["endpoints"] if row["protocol"] == "in_process"] == []
    assert {
        _short(row["handler"]): _short(row["key_type"])
        for row in tables["registrations"]
        if _short(row["handler"]) in ("ClassesListener#on", "AuditListener#on", "TxListener#on")
    } == {
        "ClassesListener#on": "OrderPlaced",
        "AuditListener#on": "OrderPlaced",
        "TxListener#on": "OrderPlaced",
    }
