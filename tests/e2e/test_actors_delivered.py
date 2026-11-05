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


@pytest.mark.pins("key-handlers.run-AFTER-self-calls")
def test_a_key_the_module_serves_is_no_outbound_row(actor_rows):
    """`Receptionist.subscribe(Stock.KEY, …)`, `entityRefFor(OrderEntity.KEY, id)` and
    `new Publish("prices", …)` each name a key or topic this module itself registers, inits
    or subscribes to: a hop, not an outbound call (§3d item 5). `Receptionist.find(Audit.KEY,
    …)` too, although no handler here serves `audit`'s class: a key is served by its
    registration, and its row stands with no handler."""
    outbound = {path for direction, path, _ in actor_rows if direction == "outbound"}
    assert not outbound & {"stock", "order", "prices", "audit"}


def test_every_actor_row_the_fixture_gives(actor_rows):
    """The whole set, so a row too many is a failure too: `new Send("/user/broker", …)`
    names a path nothing here serves (the `Put` row's path is unread), so it stays
    outbound."""
    assert actor_rows == {
        ("inbound", "stock", "resolved"),
        ("inbound", "order", "resolved"),
        ("inbound", "audit", "resolved"),
        ("inbound", "prices", "resolved"),
        ("inbound", None, "unresolved"),
        ("outbound", "/user/broker", "resolved"),
    }


@pytest.fixture(scope="module")
def inbound_handlers(analyzed: Path) -> list[tuple]:
    """`(path, handler's Class#method)` for every inbound `actor` row, one per row, sorted;
    a lambda's synthetic body is `Class#lambda` (`handler_cases`' reason)."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        rows = [
            row
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "actor" and str(row["direction"]) == "inbound"
        ]
    finally:
        workspace.close()

    def short(symbol: object) -> str | None:
        if symbol is None:
            return None
        name = str(symbol).rsplit("/", 1)[1].split("(")[0]
        return re.sub(r"#lambda\$.*", "#lambda", name)

    return sorted(((row["path"], short(row["handler"])) for row in rows), key=repr)


@pytest.mark.pins("dispatch-registrations.a-key-reaches-the-cases-of-its-SUBTYPES")
@pytest.mark.pins("dispatch-registrations.a-key-reaches-a-VALUE-case-of-its-class")
@pytest.mark.pins("key-handlers.the-registering-method-is-REPLACED")
@pytest.mark.pins("key-handlers.the-class-is-read-at-the-producers-class_arg")
def test_a_service_key_row_names_each_handler_of_its_class(inbound_handlers):
    """`stock`'s message class is `Stock.Command` (`ServiceKey.create` argument 0, read
    through `KEY`'s `<clinit>`): its row names each handler a `Command` reaches, one row per
    handler (spec §3a, §3d item 6) — `Reserve`'s, the predicated `Release` case and the one
    after it (a predicate never shadows), and `Tick.INSTANCE`'s value case. The registering
    method is not one of them."""
    assert [row for row in inbound_handlers if row[0] == "stock"] == [
        ("stock", "Stock#onRelease"),
        ("stock", "Stock#onReserve"),
        ("stock", "Stock#onTick"),
        ("stock", "Stock#onUrgentRelease"),
    ]


@pytest.mark.pins("key-handlers.the-registering-method-is-REPLACED")
def test_an_entity_key_row_names_its_handlers(inbound_handlers):
    """`order`'s class is `OrderEntity.Command`, read `Entity.of` argument 0 then
    `EntityTypeKey.create` argument 0: its one case, `Get`'s lambda, is its handler."""
    assert [row for row in inbound_handlers if row[0] == "order"] == [
        ("order", "OrderEntity#lambda"),
    ]


@pytest.mark.pins("key-handlers.a-key-no-handler-serves-keeps-ONE-row")
def test_a_key_no_handler_serves_keeps_one_row_without_a_handler(inbound_handlers):
    """`audit`'s class, `Audit.Entry`, is handled by no behavior here: one row, handler
    NULL, never the method that registered it."""
    assert [row for row in inbound_handlers if row[0] == "audit"] == [("audit", None)]


def test_every_inbound_actor_row_and_its_handler(inbound_handlers):
    """The whole set. A pub-sub row carries no message class (`Subscribe`, `Put`): it keeps
    the method that subscribed, as Task 3 wrote it."""
    assert inbound_handlers == [
        ("audit", None),
        ("order", "OrderEntity#lambda"),
        ("prices", "ClassicBroker#preStart"),
        ("stock", "Stock#onRelease"),
        ("stock", "Stock#onReserve"),
        ("stock", "Stock#onTick"),
        ("stock", "Stock#onUrgentRelease"),
        (None, "ClassicBroker#preStart"),
    ]


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
    """Every `dispatch_registrations` row one fixture derives, by the group's method
    (`Class#method`, module and signature left out), each `(position, key_type,
    key_value, predicated, handler's Class#method, delivers)` in position order."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        rows = workspace.query("dispatch_registrations")
    finally:
        workspace.close()

    def method_of(symbol: str) -> str:
        """`Class#method`; a lambda's synthetic body is `Class#lambda`, because javac names
        it with a hash that differs between the two families' builds."""
        name = symbol.rsplit("/", 1)[1].split("(")[0]
        return re.sub(r"#lambda\$.*", "#lambda", name)

    cases: dict[str, list[tuple]] = {}
    for row in rows:
        group = str(row["group"])
        key = method_of(group.rsplit("#", 1)[0]) + "@" + group.rsplit("#", 1)[1]
        cases.setdefault(key, []).append(
            (
                row["position"],
                None if row["key_type"] is None else method_of(str(row["key_type"])),
                None if row["key_value"] is None else method_of(str(row["key_value"])),
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
            "Session#createReceive",
            [
                (0, "Session$Touched#", None, False, "Session#onTouched", False),
                (1, None, "Session$Timeout#INSTANCE.", False, "Session#onTimeout", False),
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
        rows = [row for row in workspace.query("hops") if row["protocol"] == "actor"]
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


@pytest.mark.pins("calls.a-declared-call-is-matched-by-its-PARAMETER-TYPES")
def test_every_actor_hop_the_fixture_gives(actor_hops):
    """The whole set (spec §3c), so a hop too many is a failure too. Each send's message is
    read by its class, by identity (`Tick.INSTANCE`) or through the `new` a function returns;
    a reply nobody here handles and an envelope told to the pub-sub mediator are stops naming
    their class; a message read only by its declared type (a library factory's or a boxing
    call's result, `Receptionist.register(…)`, `tell(count)`; a parameter declared `Object`) is
    a stop with no path and no handler wherever a behavior's earlier case names a type that a
    subtype of it may also be (an unrelated interface, or a type not known to be a class): its
    class is not read for that behavior. Every row's evidence is `compiler`, D00 §4's closed set: the
    send site is a compiler fact. The ask's reply mapper and the adapter deliver, so the classes they return
    are hops from their own `new`s; `Counter`'s adapter is a constructor reference, whose hop
    is at its super-constructor call."""
    assert actor_hops == {
        ("Audit#lookup", 3, None, None, "compiler"),
        ("Audit#register", 3, None, None, "compiler"),
        ("ClassicBroker#announce", 1, "ClassicBroker$Price", "ClassicBroker#onPrice", "compiler"),
        ("ClassicBroker#announce", 3, "DistributedPubSubMediator$Publish", None, "compiler"),
        ("ClassicBroker#announce", 5, "ClassicBroker$Price", "ClassicBroker#onPrice", "compiler"),
        ("ClassicBroker#announce", 7, "DistributedPubSubMediator$Send", None, "compiler"),
        ("ClassicBroker#onPrice", 3, "ClassicBroker$Ack", None, "compiler"),
        ("ClassicBroker#preStart", 3, "DistributedPubSubMediator$Subscribe", None, "compiler"),
        ("ClassicBroker#preStart", 7, "DistributedPubSubMediator$Put", None, "compiler"),
        ("Counter#onReport", 2, None, None, "compiler"),
        ("Counter#release", 1, "Stock$Release", "Stock#onUrgentRelease", "compiler"),
        ("Counter#release", 1, "Stock$Release", "Stock#onRelease", "compiler"),
        ("Counter#report", 2, "Counter$Report", "Counter#onReport", "compiler"),
        ("Counter$Counted#<init>", 0, "Counter$Counted", "Counter#onCounted", "compiler"),
        ("Frontend#<init>", 6, None, None, "compiler"),
        ("Frontend#onStart", 4, "Stock$Reserve", "Stock#onReserve", "compiler"),
        ("Frontend#onStart", 9, "Frontend$Loaded", "Frontend#lambda", "compiler"),
        ("OrderEntity#onGet", 2, "OrderEntity$Summary", None, "compiler"),
        ("OrderRoutes#summary", 2, "OrderEntity$Get", "OrderEntity#lambda", "compiler"),
        ("Relay#forward", 0, None, None, "compiler"),
        ("Session#<init>", 3, "Session$Timeout#INSTANCE.", "Session#onTimeout", "compiler"),
        ("Stock#lambda", 1, "Stock$Tick#INSTANCE.", "Stock#onTick", "compiler"),
        ("Stock#lambda", 4, None, None, "compiler"),
        ("Stock#onReserve", 3, "Stock$Reply", "Frontend#lambda", "compiler"),
        ("Stock#onReserve", 3, "Stock$Reply", "Counter$Counted#<init>", "compiler"),
        ("Frontend#lambda", 0, "Frontend$Workers", "Frontend#onWorkers", "compiler"),
        ("Frontend#lambda", 0, "Frontend$Reserved", "Frontend#lambda", "compiler"),
        ("Frontend#lambda", 1, "Frontend$Failed", "Frontend#lambda", "compiler"),
    }
