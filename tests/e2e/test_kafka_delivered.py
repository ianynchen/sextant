"""Kafka is delivered when the RECEIVE half of `KafkaTemplate` is visible — the half
`G-44` names. `KafkaTemplate` read 10 of its `send`/`sendDefault` overloads; a module
that polls a topic synchronously derived nothing.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

RECEIVERS = FIXTURES / "orders-receivers"


@pytest.fixture(scope="module")
def kafka_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every kafka row the receivers fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("kafka_receivers")
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
            if str(row["protocol"]) == "kafka"
        }
    finally:
        workspace.close()


def test_kafka_template_receive_derives_an_inbound_row_on_the_topic(kafka_rows):
    """`G-44`, Kafka. `KafkaTemplate.receive(String topic, int partition, long offset,
    Duration)` — spring-kafka 3.1.4 — is a synchronous read of one record: an inbound
    boundary on the topic at argument 0."""
    assert ("kafka", "inbound", "recv.orders.replay") in kafka_rows, sorted(kafka_rows)
