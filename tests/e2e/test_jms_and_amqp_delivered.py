"""JMS and AMQP are delivered when the RECEIVE half of each template is visible — the
half `G-44` names. `RabbitTemplate` read 1 of 88 methods and `JmsTemplate` 1 of 49; the
sends. A module that polls a queue derived nothing.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

RECEIVERS = FIXTURES / "orders-receivers"


@pytest.fixture(scope="module")
def receiver_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every non-HTTP row the receivers fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("receivers")
    compile_fixture(RECEIVERS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(RECEIVERS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["protocol"]), str(row["direction"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) != "http"
        }
    finally:
        workspace.close()


def test_rabbit_template_receives_derive_one_inbound_row_per_queue(receiver_rows):
    """`G-44`, AMQP half. Four receive shapes on four queues: raw `receive(String)`, a
    timed `receiveAndConvert(String, long)`, a typed `receiveAndConvert(String, PTR)`, and
    `receiveAndReply(String, callback)` — which is ONE inbound row, because the reply goes
    to the message's own `replyTo` and no argument names it."""
    expected = {
        ("amqp", "inbound", "recv.orders.raw"),
        ("amqp", "inbound", "recv.orders.converted"),
        ("amqp", "inbound", "recv.orders.typed"),
        ("amqp", "inbound", "recv.orders.rpc"),
    }
    missing = expected - receiver_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(receiver_rows)}"
    assert ("amqp", "outbound", "recv.orders.rpc") not in receiver_rows, (
        "receiveAndReply derived an OUTBOUND row on the receive queue; the reply address is per-message"
    )
