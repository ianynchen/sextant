"""Akka and Pekko named cluster keys are `actor` endpoint rows (spec 2026-11-04 §3a, §3d
item 5): a Receptionist service key the module registers, a sharded entity type it inits
and a classic pub-sub topic it subscribes to are inbound rows named by the key or topic; a
key or topic it only calls is outbound, unless the module itself serves it, in which case
the call is a hop and no outbound row.

Both families run the same sources (`fixtures/orders-actors-pekko`, `orders-actors-akka`,
package `com.acme.actors`), so every test runs on each.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.resolve.self_calls import record_self_calls
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_FAMILIES = ("orders-actors-pekko", "orders-actors-akka")


@pytest.fixture(scope="module", params=_FAMILIES)
def analyzed(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One fixture, analysed once the way a user analyses it: its workspace file."""
    root = FIXTURES / request.param
    workspace_dir = tmp_path_factory.mktemp(request.param)
    compile_fixture(root)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(root), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return workspace_dir / "workspace.duckdb"


@pytest.fixture(scope="module")
def actor_rows(analyzed: Path) -> set:
    """`(direction, path, resolution)` for every `actor` row one fixture derives."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        return {
            (str(row["direction"]), row["path"], str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "actor"
        }
    finally:
        workspace.close()


def test_a_registered_service_key_is_an_inbound_row(actor_rows):
    """`Receptionist.register(KEY, self)`, `KEY = ServiceKey.create(Command.class, "stock")`
    held in a static final field: the name is read through the field's `<clinit>`."""
    assert ("inbound", "stock", "resolved") in actor_rows


def test_an_initialised_entity_type_is_an_inbound_row(actor_rows):
    """`sharding.init(Entity.of(OrderEntity.KEY, factory))`: two steps, `Entity.of` arg 0
    then `EntityTypeKey.create` arg 1 in `OrderEntity`'s `<clinit>`."""
    assert ("inbound", "order", "resolved") in actor_rows


def test_a_pubsub_subscription_is_an_inbound_row(actor_rows):
    """`new Subscribe("prices", self)` is inbound on its topic. `new Put(self)` registers the
    actor at its own path, which is set where the actor was started and named by no
    argument here: the row is inbound, path NULL, `unresolved`, kept and never dropped."""
    assert ("inbound", "prices", "resolved") in actor_rows
    assert ("inbound", None, "unresolved") in actor_rows


def test_a_key_the_module_serves_is_no_outbound_row(actor_rows):
    """`Receptionist.subscribe(Stock.KEY, …)`, `entityRefFor(OrderEntity.KEY, id)` and
    `new Publish("prices", …)` each name a key or topic this module itself registers, inits
    or subscribes to: a hop, not an outbound call (§3d item 5)."""
    outbound = {path for direction, path, _ in actor_rows if direction == "outbound"}
    assert not outbound & {"stock", "order", "prices"}


def test_every_actor_row_the_fixture_gives(actor_rows):
    """The whole set, so a row too many is a failure too: `new Send("/user/broker", …)`
    names a path nothing here serves (the `Put` row's path is unread), so it stays
    outbound."""
    assert actor_rows == {
        ("inbound", "stock", "resolved"),
        ("inbound", "order", "resolved"),
        ("inbound", "prices", "resolved"),
        ("inbound", None, "unresolved"),
        ("outbound", "/user/broker", "resolved"),
    }


_MODULE = "sextant-jvm maven com.acme/actors 1.0.0 "


def test_a_key_the_module_does_not_serve_is_an_outbound_row(tmp_path: Path) -> None:
    """A stub workspace (`tests/application/test_self_calls.py`'s form): the module
    registers `stock` and calls `inventory`, which nothing inbound here serves, so the
    `inventory` row stays outbound while the `stock` call is dropped."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    for direction, path, symbol in (
        ("inbound", "stock", "com/acme/actors/Stock#create(sig_00000000)."),
        ("outbound", "stock", "com/acme/actors/Frontend#`<init>`(sig_11111111)."),
        ("outbound", "inventory", "com/acme/actors/Frontend#`<init>`(sig_11111111)."),
    ):
        workspace._connection.execute(
            "INSERT INTO endpoints (row_id, protocol, direction, method, path, handler, caller, peer) "
            "VALUES ((SELECT coalesce(max(row_id), 0) + 1 FROM endpoints), 'actor', ?, NULL, ?, ?, ?, NULL)",
            [
                direction,
                path,
                _MODULE + symbol if direction == "inbound" else None,
                _MODULE + symbol if direction == "outbound" else None,
            ],
        )
    record_self_calls(workspace)
    remaining = sorted((str(r["direction"]), str(r["path"])) for r in workspace.query("endpoints"))
    workspace.close()

    assert remaining == [("inbound", "stock"), ("outbound", "inventory")]


@pytest.fixture(scope="module")
def handler_cases(analyzed: Path) -> dict[str, list[tuple]]:
    """Every `message_handlers` row one fixture derives, by the behavior's method
    (`Class#method`, module and signature left out), each `(position, message_type,
    message_value, predicated, handler's Class#method, delivers)` in position order."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        rows = workspace.query("message_handlers")
    finally:
        workspace.close()

    def method_of(symbol: str) -> str:
        """`Class#method`; a lambda's synthetic body is `Class#lambda`, because javac names
        it with a hash that differs between the two families' builds."""
        name = symbol.rsplit("/", 1)[1].split("(")[0]
        return re.sub(r"#lambda\$.*", "#lambda", name)

    cases: dict[str, list[tuple]] = {}
    for row in rows:
        behavior = str(row["behavior"])
        key = method_of(behavior.rsplit("#", 1)[0]) + "@" + behavior.rsplit("#", 1)[1]
        cases.setdefault(key, []).append(
            (
                row["position"],
                None if row["message_type"] is None else method_of(str(row["message_type"])),
                None if row["message_value"] is None else method_of(str(row["message_value"])),
                row["predicated"],
                None if row["handler"] is None else method_of(str(row["handler"])),
                row["delivers"],
            )
        )
    return {key: sorted(value) for key, value in cases.items()}


def test_stock_handlers_are_read_in_order(handler_cases):
    """`Stock`'s immutable chain (spec §3d items 1-3): four cases, one behavior, in chain
    order; the predicated `Release` case at 1 and the unpredicated one at 2 both stand, and
    the `Tick.INSTANCE` case is a value case, no class."""
    [stock] = [cases for key, cases in handler_cases.items() if key.startswith("Stock#behavior@")]
    assert stock == [
        (0, "Stock$Reserve#", None, False, "Stock#onReserve", False),
        (1, "Stock$Release#", None, True, "Stock#onUrgentRelease", False),
        (2, "Stock$Release#", None, False, "Stock#onRelease", False),
        (3, None, "Stock$Tick#INSTANCE.", False, "Stock#onTick", False),
    ]


def test_every_behavior_the_fixture_builds(handler_cases):
    """The whole set, so a behavior too many is a failure too. `Orders` builds three state
    behaviors on one `CommandHandlerBuilder` (`forAnyState()` chained, then each `forState`
    result held in a local and given its `onCommand` as a statement), each its own; `Frontend`
    a mutable `newReceiveBuilder()` chain, a root its own class inherits; `OrderEntity` an
    immutable chain whose handler is a lambda, its synthetic body named; `ClassicBroker` a
    classic `receiveBuilder()`, also inherited. `Frontend`'s `messageAdapter` and its
    `context.ask` reply mapper are registrations no chain holds: each call is a behavior of
    its own, one case, delivering (spec §3d item 4)."""
    assert sorted((key.split("@")[0], cases) for key, cases in handler_cases.items()) == [
        (
            "ClassicBroker#createReceive",
            [
                (0, "ClassicBroker$Price#", None, False, "ClassicBroker#onPrice", False),
            ],
        ),
        (
            "Counter#<init>",
            [
                (0, "Stock$Reply#", None, False, "Counter$Counted#<init>", True),
            ],
        ),
        (
            "Counter#createReceive",
            [
                (0, "Counter$Counted#", None, False, "Counter#onCounted", False),
                (1, "Counter$Report#", None, False, "Counter#onReport", False),
            ],
        ),
        (
            "Frontend#<init>",
            [
                (0, "Receptionist$Listing#", None, False, "Frontend#lambda", True),
            ],
        ),
        (
            "Frontend#createReceive",
            [
                (0, "Frontend$Workers#", None, False, "Frontend#onWorkers", False),
                (1, "Frontend$Start#", None, False, "Frontend#onStart", False),
                (2, "Frontend$Reserved#", None, False, "Frontend#lambda", False),
                (3, "Frontend$Failed#", None, False, "Frontend#lambda", False),
                (4, "Frontend$Loaded#", None, False, "Frontend#lambda", False),
            ],
        ),
        (
            "Frontend#onStart",
            [
                (0, "Stock$Reply#", None, False, "Frontend#lambda", True),
            ],
        ),
        (
            "OrderEntity#create",
            [
                (0, "OrderEntity$Get#", None, False, "OrderEntity#lambda", False),
            ],
        ),
        (
            "Orders#commandHandler",
            [
                (0, "Orders$Cancel#", None, False, "Orders#onCancel", False),
            ],
        ),
        (
            "Orders#commandHandler",
            [
                (0, "Orders$Cancel#", None, False, "Orders#onCancelEmpty", False),
            ],
        ),
        (
            "Orders#commandHandler",
            [
                (0, "Orders$Place#", None, False, "Orders#onPlace", False),
            ],
        ),
        (
            "Stock#behavior",
            [
                (0, "Stock$Reserve#", None, False, "Stock#onReserve", False),
                (1, "Stock$Release#", None, True, "Stock#onUrgentRelease", False),
                (2, "Stock$Release#", None, False, "Stock#onRelease", False),
                (3, None, "Stock$Tick#INSTANCE.", False, "Stock#onTick", False),
            ],
        ),
    ]


@pytest.fixture(scope="module")
def actor_hops(analyzed: Path) -> set[tuple]:
    """Every `actor` hop one fixture gives, `(caller, ordinal, path, handler, evidence)`, each
    symbol as `handler_cases` writes it (a type without its `#`)."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        rows = [row for row in workspace.query("rpc_hops") if row["protocol"] == "actor"]
    finally:
        workspace.close()

    def short(symbol: object) -> str | None:
        if symbol is None:
            return None
        name = str(symbol).rsplit("/", 1)[1].split("(")[0].removesuffix("#")
        return re.sub(r"#lambda\$.*", "#lambda", name)

    return {
        (short(r["caller"]), r["ordinal"], short(r["path"]), short(r["handler"]), r["evidence"])
        for r in rows
    }


def test_every_actor_hop_the_fixture_gives(actor_hops):
    """The whole set (spec §3c), so a hop too many is a failure too. Each send's message is
    read by its class, by identity (`Tick.INSTANCE`) or through the `new` a function returns;
    a reply nobody here handles and an envelope told to the pub-sub mediator are stops naming
    their class; a message from a parameter or a factory call is a stop that says its class
    was not read. The ask's reply mapper and the adapter deliver, so the classes they return
    are hops from their own `new`s; `Counter`'s adapter is a constructor reference, whose hop
    is at its super-constructor call."""
    unread_call = "message class not read: unresolved"
    assert actor_hops == {
        ("ClassicBroker#announce", 1, "ClassicBroker$Price", "ClassicBroker#onPrice", "compiler"),
        ("ClassicBroker#announce", 3, "DistributedPubSubMediator$Publish", None, "compiler"),
        ("ClassicBroker#announce", 5, "ClassicBroker$Price", "ClassicBroker#onPrice", "compiler"),
        ("ClassicBroker#announce", 7, "DistributedPubSubMediator$Send", None, "compiler"),
        ("ClassicBroker#onPrice", 3, "ClassicBroker$Ack", None, "compiler"),
        ("ClassicBroker#preStart", 3, "DistributedPubSubMediator$Subscribe", None, "compiler"),
        ("ClassicBroker#preStart", 7, "DistributedPubSubMediator$Put", None, "compiler"),
        ("Counter#onReport", 2, None, None, unread_call),
        ("Counter#report", 2, "Counter$Report", "Counter#onReport", "compiler"),
        ("Counter$Counted#<init>", 0, "Counter$Counted", "Counter#onCounted", "compiler"),
        ("Frontend#<init>", 6, None, None, unread_call),
        ("Frontend#onStart", 4, "Stock$Reserve", "Stock#onReserve", "compiler"),
        ("Frontend#onStart", 9, "Frontend$Loaded", "Frontend#lambda", "compiler"),
        ("OrderEntity#onGet", 2, "OrderEntity$Summary", None, "compiler"),
        ("OrderRoutes#summary", 2, "OrderEntity$Get", "OrderEntity#lambda", "compiler"),
        ("Relay#forward", 0, None, None, "message class not read: parameter"),
        ("Stock#lambda", 1, "Stock$Tick#INSTANCE.", "Stock#onTick", "compiler"),
        ("Stock#lambda", 4, None, None, unread_call),
        ("Stock#onReserve", 3, "Stock$Reply", "Frontend#lambda", "compiler"),
        ("Stock#onReserve", 3, "Stock$Reply", "Counter$Counted#<init>", "compiler"),
        ("Frontend#lambda", 0, "Frontend$Workers", "Frontend#onWorkers", "compiler"),
        ("Frontend#lambda", 0, "Frontend$Reserved", "Frontend#lambda", "compiler"),
        ("Frontend#lambda", 1, "Frontend$Failed", "Frontend#lambda", "compiler"),
    }
