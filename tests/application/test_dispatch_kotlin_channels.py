"""Kotlin channels and flows are object-keyed in-process dispatch (spec 2026-11-05 §1, §3, §4
item 7): a value sent on a channel reaches the code that receives from THAT channel object, a
`for` loop over it included (`match: one`); a value emitted on a shared or state flow reaches
every collector of THAT flow (`match: all`), the collector being the lambda `collect` is given.

Read over `fixtures/orders-kotlin-channels` (Kotlin 2.4.20, kotlinx-coroutines 1.11.0, JDK 21),
analysed once the way a user analyses it, so every assertion is on rows the real pipeline
derives from kotlinc's bytecode (CP-59 findings 17-21): a send made inside a coroutine's
synthetic class, read through the compiler's private-field accessor; `for` compiled to an
`iterator()` call; `value =` compiled to `setValue`; a `collect { }` lambda compiled to a class
implementing `FlowCollector`. Nothing here is written for channels beyond the catalogs' data.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.domain.symbols import bare_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-kotlin-channels"
_CHANNELS = "kotlinx-channels"
_FLOWS = "kotlinx-flows"


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace_dir = tmp_path_factory.mktemp("orders-kotlin-channels")
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
        }
    finally:
        workspace.close()


def _hops_from(tables: dict, caller: str) -> set[tuple]:
    """`(protocol, handler)` of every hop the method `caller` makes, shortened."""
    return {
        (str(row["protocol"]), _short(row["handler"]))
        for row in tables["hops"]
        if _short(row["caller"]) == caller
    }


def _paths_from(tables: dict, caller: str) -> set[object]:
    return {row["path"] for row in tables["hops"] if _short(row["caller"]) == caller}


def _keys_of(tables: dict, mechanism: str, handler: str) -> set[object]:
    """The `key_object` of every receive registration of `mechanism` whose handler is
    `handler`."""
    return {
        row["key_object"]
        for row in tables["registrations"]
        if row["mechanism"] == mechanism and _short(row["handler"]) == handler
    }


# The receives on `Pipeline.orders`: a `for` loop in a suspend function and in a launched
# coroutine, `receive`, `tryReceive`, and `consumeEach` (inlined to the same `iterator()`).
_ORDERS = {
    ("in_process", "Pipeline#drain"),
    ("in_process", "Pipeline$start$2#invokeSuspend"),
    ("in_process", "Pipeline#next"),
    ("in_process", "Pipeline#poll"),
    ("in_process", "Pipeline#each"),
}


def test_a_for_loop_over_a_channel_receives(tables):
    """Review Focus 5. `for (o in orders)` is compiled to `Channel.iterator()` then
    `hasNext`/`next` on the iterator it returns: the `iterator()` call is made on the channel,
    so the loop is a receive keyed by `orders`, whose producer is the `Channel(...)` factory
    call in `Pipeline`'s constructor. `submit`'s `send` reaches it."""
    [made] = _keys_of(tables, _CHANNELS, "Pipeline#drain")
    assert _short(str(made).rsplit("#", 1)[0]) == "Pipeline#<init>"
    assert ("in_process", "Pipeline#drain") in _hops_from(tables, "Pipeline#submit")
    assert _paths_from(tables, "Pipeline#submit") == {made}


def test_a_send_reaches_every_receive_on_its_channel(tables):
    """`submit` (`send`) and `trySubmit` (`trySend`, kotlinc's mangled `trySend-JP2dKIU`)
    each reach every receive on `orders` (one consumer takes each order, which one decided at
    run time) and none of `audit`'s."""
    assert _hops_from(tables, "Pipeline#submit") == _ORDERS
    assert _hops_from(tables, "Pipeline#trySubmit") == _ORDERS


def test_a_send_inside_a_coroutine_is_read_through_its_class(tables):
    """`scope.launch { orders.send(Order(1)) }`: kotlinc compiles the block to a class whose
    `invokeSuspend` reads the channel through its captured `this$0` and the private field's
    synthetic accessor `access$getOrders$p`. The walk follows the accessor's return to the
    field, so the send reaches the same receives as `submit`'s."""
    assert _hops_from(tables, "Pipeline$start$1#invokeSuspend") == _ORDERS


def test_two_channels_of_one_type_stay_apart(tables):
    """`Pipeline.audit` is a second `Channel<Order>`: `record` reaches only `auditNext`, and
    no send on `orders` reaches `auditNext`."""
    assert _hops_from(tables, "Pipeline#record") == {("in_process", "Pipeline#auditNext")}
    assert _paths_from(tables, "Pipeline#record") != _paths_from(tables, "Pipeline#submit")


def test_a_channel_held_in_a_data_class_links(tables):
    """`examples/playport`'s shape: `Client(Channel(capacity = 16))`, the channel read through
    the data class's property, sent to by `broadcast` (`trySend` over every client) and looped
    over in a coroutine that captured the client. The property's field has a second writer, the
    data class's generated `copy(channel)`, which nothing in the module calls: on that path the
    channel is a parameter nobody passes, so the send also keeps one stop saying the object
    was not read (the established rule: one such row per path that reaches no producer)."""
    assert _hops_from(tables, "Hub#broadcast") == {
        ("in_process", "Hub$connect$1#invokeSuspend"),
        ("in_process", None),
    }
    assert len([path for path in _paths_from(tables, "Hub#broadcast") if path is not None]) == 1


def test_an_injected_channel_is_a_stop(tables):
    """Nothing in the module constructs a `Relay`, so the channel its constructor is given
    comes from outside: `forward`'s `send` is one stop with no path and no handler, never a
    hop to every receive in the module."""
    assert _hops_from(tables, "Relay#forward") == {("in_process", None)}
    assert _paths_from(tables, "Relay#forward") == {None}


@pytest.mark.pins("dispatch-objects.a-LAMBDA-ARG-receive-is-handled-by-its-FUNCTION")
@pytest.mark.pins("dispatch-objects.a-SHARED-collector-instance-names-its-CLASS")
def test_a_shared_flow_reaches_every_collector(tables):
    """`Bus.events` is collected three times: twice in `Bus` with lambdas that capture
    nothing, once in `Mailer` through the property, with a lambda that captures. Each collector
    is the class kotlinc compiled its lambda to, and its handler is that class's own `emit` (not
    the erased bridge). `publish` (`emit`) and `tryPublish` (`tryEmit`) reach all three
    (`match: all`)."""
    collectors = {
        ("in_process", "Bus$mail$2#emit"),
        ("in_process", "Bus$log$2#emit"),
        ("in_process", "Mailer$run$2#emit"),
    }
    assert _hops_from(tables, "Bus#publish") == collectors
    assert _hops_from(tables, "Bus#tryPublish") == collectors


@pytest.mark.pins("dispatch-objects.a-LAMBDA-ARG-receive-is-handled-by-its-FUNCTION")
@pytest.mark.pins("dispatch-objects.a-collector-BRIDGE-is-carried-to-its-BODY")
def test_a_collector_is_handled_by_its_lambda_body(tables, analyzed: Path):
    """The registration a `collect` site makes: its group is the collecting call site, its
    handler the collector class's non-bridge `emit(Event, Continuation)`, keyed by the flow,
    under `match: all`."""
    [row] = [
        row
        for row in tables["registrations"]
        if row["mechanism"] == _FLOWS and _short(row["handler"]) == "Bus$mail$2#emit"
    ]
    workspace = DuckDbWorkspace(analyzed)
    try:
        [declared] = [
            declared
            for declared in workspace.query("method_declarations")
            if declared["symbol"] == row["handler"]
        ]
    finally:
        workspace.close()
    assert not (declared["modifiers"] or {}).get("synthetic")
    assert _short(str(row["group"]).rsplit("#", 1)[0]) == "Bus#mail"
    assert (row["position"], row["match"], row["key_type"]) == (0, "all", None)
    assert _short(str(row["key_object"]).rsplit("#", 1)[0]) == "Bus#<init>"


def test_a_state_flow_value_set_is_a_send(tables):
    """`state.value = "open"` is compiled to `MutableStateFlow.setValue`; `emit` and `update { }`
    (inlined to `compareAndSet`) are sends too. Each reaches the one collector."""
    watcher = {("in_process", "Status$watch$2#emit")}
    assert _hops_from(tables, "Status#open") == watcher
    assert _hops_from(tables, "Status#close") == watcher
    assert _hops_from(tables, "Status#touch") == watcher


def test_a_flow_send_never_reaches_a_channel_receive(tables):
    """Two mechanisms: a flow's emit reaches only collectors, a channel's send only receives."""
    receivers = {handler for _, handler in _hops_from(tables, "Bus#publish")}
    assert not any(str(handler).startswith("Pipeline") for handler in receivers)


@pytest.mark.pins("dispatch-objects.a-CYCLE-adds-no-object")
def test_a_channel_captured_by_a_coroutine_is_one_object(tables):
    """`coroutineScope { val jobs = Channel<Order>(); launch { jobs.send(…) }; for (j in jobs) … }`:
    kotlinc keeps the captured local in the launched lambda's `$jobs` field, written by its
    constructor from two callers — the block that made the channel, and the lambda's own
    `create`, which copies `this.$jobs` into the fresh instance a coroutine starts with. That
    copy comes back to the field it started from (a cycle), so it adds no object: the send
    reaches the loop, and keeps no stop saying the object was not read."""
    assert _hops_from(tables, "Workers$run$2$1#invokeSuspend") == {
        ("in_process", "Workers$run$2#invokeSuspend")
    }


@pytest.mark.pins("dispatch-objects.a-NULL-CHECK-met-again-adds-no-object")
@pytest.mark.pins("dispatch-objects.a-SPILLED-variable-null-out-is-no-producer")
def test_a_producer_coroutines_send_is_a_stop(tables):
    """`produce { send(x) }`: the block sends on the `ProducerScope` the library hands it
    (kotlinc writes `ProducerScope.send`), and the caller loops over the channel the library
    returns. Neither object is made by a call the walk can pair, so the send is one stop
    naming no object — never a hop to every receive in the module — and the loop's receive is
    keyed by the `produce` call, matching no send.

    The scope sits in the lambda's `L$0` slot, which kotlinc 2.4 also writes as
    `L$0 = nullOutSpilledVariable(scope)` before the suspension: a compiler call handing back
    null (a declared `not_hand_offs` call, passed through to the scope it was given, which is
    that same slot: a cycle). It is not where the scope was made, so no path names it."""
    assert _hops_from(tables, "Numbers$numbers$1#invokeSuspend") == {("in_process", None)}
    assert _paths_from(tables, "Numbers$numbers$1#invokeSuspend") == {None}
    [made] = _keys_of(tables, _CHANNELS, "Numbers#sum")
    assert _short(str(made).rsplit("#", 1)[0]) == "Numbers#numbers"


def test_a_field_held_channel_is_read_after_a_suspension(tables):
    """`later` suspends (`delay`) before it sends on `orders`: the state machine reloads `this`
    from its continuation, but the channel is still read off the field, so the send reaches
    every receive on `orders`."""
    assert _hops_from(tables, "Pipeline#later") == _ORDERS


def test_a_parameter_channel_read_after_a_suspension_is_a_stop(tables):
    """Stated bound. `pump(channel)` sends on its parameter after a suspension: kotlinc reloads
    the parameter from its spilled continuation slot and merges the two, and the facts name no
    receiver for a merged value, so the send is a stop saying its object was not read (a
    missing hop to `auditNext`, never a false one)."""
    assert _hops_from(tables, "Pipeline#pump") == {("in_process", None)}


@pytest.mark.declines("kotlinx-channels")
@pytest.mark.pins("calls.a-declared-call-is-matched-on-its-OWNER")
def test_a_module_type_with_a_channels_method_names_is_no_channel(tables):
    """Near miss for `kotlinx-channels`: `Outbox` has a suspending `send`, a `receive` and an
    `iterator()` a `for` loop calls, with a channel's names and shapes, but kotlinc writes the
    module's own type as their owner. No hop, no registration."""
    assert _hops_from(tables, "OutboxUser#push") == set()
    assert not any(
        _short(row["handler"]) in {"OutboxUser#pull", "OutboxUser#all"}
        for row in tables["registrations"]
    )


@pytest.mark.declines("kotlinx-flows")
@pytest.mark.pins("calls.a-declared-call-is-matched-on-its-OWNER")
def test_a_cold_flows_emit_is_no_send(tables):
    """Near miss for `kotlinx-flows`: `flow { emit(x) }` emits to the collector the flow is
    collected with (kotlinc writes `FlowCollector.emit`, an owner the catalog does not declare:
    there is no shared object), and the module's own `collect(handler)` is not a flow's. No hop,
    no registration."""
    assert _hops_from(tables, "Ticker$ticks$1#invokeSuspend") == set()
    assert not any(
        str(_short(row["handler"])).startswith("Ticker") for row in tables["registrations"]
    )
