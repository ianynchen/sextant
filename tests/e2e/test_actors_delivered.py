"""Akka and Pekko named cluster keys are `actor` endpoint rows (spec 2026-11-04 §3a, §3d
item 5): a Receptionist service key the module registers, a sharded entity type it inits
and a classic pub-sub topic it subscribes to are inbound rows named by the key or topic; a
key or topic it only calls is outbound, unless the module itself serves it, in which case
the call is a hop and no outbound row.

Both families run the same sources (`fixtures/orders-actors-pekko`, `orders-actors-akka`,
package `com.acme.actors`), so every test runs on each.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.resolve.self_calls import record_self_calls
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_FAMILIES = ("orders-actors-pekko", "orders-actors-akka")


@pytest.fixture(scope="module", params=_FAMILIES)
def actor_rows(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> set:
    """`(direction, path, resolution)` for every `actor` row one fixture derives."""
    root = FIXTURES / request.param
    workspace_dir = tmp_path_factory.mktemp(request.param)
    compile_fixture(root)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(root), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
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
