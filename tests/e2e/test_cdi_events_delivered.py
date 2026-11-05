"""CDI events are in-process dispatch (spec 2026-11-05 §4 item 6): `event.fire(e)` hands `e`
to the container, which calls every observer method whose observed type `e`'s class is
assignable to. An observer is a method with a parameter annotated `@Observes` (or
`@ObservesAsync`); it is a `dispatch_registrations` row keyed by THAT parameter's type, `match:
all`; each fire is a hop per observer it reaches, under `in_process`. Never an endpoint row.

`fire` notifies the synchronous observers only and `fireAsync` the asynchronous ones only
(CP-59 finding 10, measured in ArC 3.17.5), so the two are two mechanisms, each a catalog of its
own: nothing here is written for CDI beyond the catalogs' data.

**Not a document check.** Real bytecode (`fixtures/orders-cdi-events`, Quarkus 3.17.5's
managed versions), real pipeline, assertions on derived rows.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.query.trace import trace_of
from sextant.application.resolve.roots import Root
from sextant.cli.app import cli
from sextant.domain.closed_sets import RootKind, TraceStop
from sextant.domain.symbols import bare_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-cdi-events"


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace_dir = tmp_path_factory.mktemp("orders-cdi-events")
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


@pytest.mark.pins("annotation-registrations.a-PARAMETER-annotation-selects-the-observer")
@pytest.mark.pins("annotation-registrations.ONLY-a-QUALIFIER-makes-an-observer-KEYLESS")
def test_fire_reaches_the_synchronous_observers_and_fire_async_the_asynchronous(tables):
    """`shipped.fire(new Shipped(id))` reaches every synchronous, unqualified observer of a
    supertype of `Shipped` (`match: all`): `on(@Observes Shipped)`, `on(@Observes Object)` and
    `on(@Observes @Priority(10) Shipped)` (`@Priority` orders observers, it qualifies nothing).
    `shipped.fireAsync(new Shipped(id))` reaches only the asynchronous one, `on(@ObservesAsync
    Shipped)`. Neither crosses to the other kind: ArC filters observers by `isAsync()` against
    the call that fired (CP-59 finding 10)."""
    assert _hops_from(tables, "ShippingService#ship") == {
        ("in_process", "Shipped", "AuditObserver#on"),
        ("in_process", "Shipped", "AnyObserver#on"),
        ("in_process", "Shipped", "PriorityObserver#on"),
    }
    assert _hops_from(tables, "ShippingService#shipLater") == {
        ("in_process", "Shipped", "AsyncObserver#on"),
    }


@pytest.mark.pins("annotation-registrations.a-QUALIFIED-observer-is-KEYLESS")
def test_a_qualified_observer_is_kept_keyless_and_gets_no_hop(tables):
    """`on(@Observes @Express Shipped)` (a module `@Qualifier`) and `on(@Observes @Named("audit")
    Shipped)` (a library one, read off its type header) are notified only of events fired with
    that qualifier, which this module's fire sites are not read for. Each keeps its
    registration with no key: no hop, a missing one at worst, never a false one."""
    keys = {
        _short(row["handler"]): row["key_type"]
        for row in tables["registrations"]
        if _short(row["handler"]) in ("ExpressObserver#on", "NamedObserver#on")
    }
    assert keys == {"ExpressObserver#on": None, "NamedObserver#on": None}
    assert not any(
        _short(row["handler"]) in ("ExpressObserver#on", "NamedObserver#on")
        for row in tables["hops"]
    )


@pytest.mark.pins("annotation-registrations.a-PARAMETERIZED-observed-type-is-KEYLESS")
def test_a_parameterized_observed_type_is_kept_keyless(tables):
    """`on(@Observes List<String>)`: CDI matches the parameterized type, so its erasure `List`
    would reach a `List<Integer>` too. The registration is kept with no key."""
    assert {
        _short(row["handler"]): row["key_type"]
        for row in tables["registrations"]
        if _short(row["handler"]) == "ListObserver#on"
    } == {"ListObserver#on": None}


@pytest.mark.pins("annotation-registrations.a-PARAMETER-annotation-selects-the-observer")
def test_each_event_reaches_only_the_observers_of_its_class(tables):
    """The key decides: `events.fire(new Note())` reaches only the observer of `Object`, none
    of `Shipped`'s. A fan-out ignoring the key fails it."""
    assert _hops_from(tables, "ShippingService#note") == {("in_process", "Note", "AnyObserver#on")}


@pytest.mark.pins("annotation-registrations.a-PARAMETER-annotation-selects-the-observer")
def test_a_framework_event_observer_gets_no_hop(tables):
    """`onStart(@Observes StartupEvent event, ShippingService service)`: Quarkus fires
    `StartupEvent`, nothing in the module does. The observer is a registration keyed by the
    ANNOTATED parameter's type (not the injected `ShippingService` beside it), no hop reaches
    it, and it is no endpoint row."""
    assert {
        _short(row["handler"]): row["key_type"]
        for row in tables["registrations"]
        if _short(row["handler"]) == "StartupObserver#onStart"
    } == {"StartupObserver#onStart": "io/quarkus/runtime/StartupEvent#"}
    assert not any(_short(row["handler"]) == "StartupObserver#onStart" for row in tables["hops"])
    assert [row for row in tables["endpoints"] if row["protocol"] == "in_process"] == []


def test_each_observer_belongs_to_the_mechanism_of_its_annotation(tables):
    """The synchronous observers are `cdi-events` registrations and the asynchronous one a
    `cdi-async-events` registration: the mechanism is what keeps `fire` off `@ObservesAsync`
    and `fireAsync` off `@Observes`."""
    assert {
        _short(row["handler"]): row["mechanism"]
        for row in tables["registrations"]
        if _short(row["handler"]).endswith("Observer#on")
        or _short(row["handler"]) == "StartupObserver#onStart"
    } == {
        "AuditObserver#on": "cdi-events",
        "AnyObserver#on": "cdi-events",
        "PriorityObserver#on": "cdi-events",
        "ExpressObserver#on": "cdi-events",
        "NamedObserver#on": "cdi-events",
        "ListObserver#on": "cdi-events",
        "StartupObserver#onStart": "cdi-events",
        "AsyncObserver#on": "cdi-async-events",
    }


def test_an_unread_event_class_is_a_stop(tables, analyzed: Path):
    """`events.fire(pending[0])`: no call, parameter or field produces the value, so its class
    is not read here, and the hop is one stop with no path and no handler, never a hop to every
    observer. `events.fire(event)`, `event` a parameter declared `Object`, is read by that
    declared type: the observer of `Object` is certainly notified, and only it."""
    assert _hops_from(tables, "ShippingService#refireFirst") == {("in_process", None, None)}
    assert _hops_from(tables, "ShippingService#refire") == {
        ("in_process", "Object", "AnyObserver#on")
    }
    workspace = DuckDbWorkspace(analyzed)
    try:
        [refire] = [
            str(row["method"])
            for row in workspace.query("method_returns")
            if "ShippingService#refireFirst(" in str(row["method"])
        ]
        trace = trace_of(workspace, Root(handler=refire, kind=RootKind.INBOUND_ENDPOINT))
    finally:
        workspace.close()
    assert [(step.via, step.stop) for step in trace.steps] == [
        ("in_process (key not read)", TraceStop.BOUNDARY)
    ]
