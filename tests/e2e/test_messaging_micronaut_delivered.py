"""Kafka, JMS and Pub/Sub are delivered for Micronaut when each of its three messaging
integrations, declared the way an application declares them, is visible in both directions.

One file for the three because they share one fixture module and one shape — a class-level
role marker plus a method annotation naming the destination — and because a reader asking
"does Sextant read Micronaut messaging" wants one answer.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

MICRONAUT = FIXTURES / "orders-micronaut"


@pytest.fixture(scope="module")
def messaging_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every non-HTTP row the Micronaut fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("mn-messaging")
    compile_fixture(MICRONAUT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(MICRONAUT), "--workspace", str(workspace_dir)]
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


def test_micronaut_kafka_both_directions(messaging_rows):
    """`@KafkaListener` class + `@Topic` method consumes; `@KafkaClient` interface +
    `@Topic` method produces. Measured at micronaut-kafka 5.6.0: `@Topic` declares
    `value[]` and `patterns[]`."""
    expected = {
        ("kafka", "inbound", "mn.orders.placed"),
        ("kafka", "outbound", "mn.orders.shipped"),
    }
    missing = expected - messaging_rows
    assert missing == set(), (
        f"Micronaut Kafka: missing {sorted(missing)}. Derived: {sorted(messaging_rows)}"
    )


def test_micronaut_jms_both_directions(messaging_rows):
    """`@JMSListener` class + `@Queue`/`@Topic` method consumes; `@JMSProducer` interface
    + the same method annotations produce. Measured at micronaut-jms-core 4.2.0."""
    expected = {("jms", "inbound", "mn.orders.queue"), ("jms", "outbound", "mn.orders.audit")}
    missing = expected - messaging_rows
    assert missing == set(), (
        f"Micronaut JMS: missing {sorted(missing)}. Derived: {sorted(messaging_rows)}"
    )


def test_micronaut_pubsub_both_directions(messaging_rows):
    """`@PubSubListener` class + `@Subscription` method consumes; `@PubSubClient`
    interface + `@Topic` method publishes. Measured at micronaut-gcp-pubsub 5.8.0."""
    expected = {("pubsub", "inbound", "mn-orders-sub"), ("pubsub", "outbound", "mn-orders-topic")}
    missing = expected - messaging_rows
    assert missing == set(), (
        f"Micronaut Pub/Sub: missing {sorted(missing)}. Derived: {sorted(messaging_rows)}"
    )


@pytest.mark.xfail(
    strict=True, reason="micronaut-jms-over-sqs: protocol_hint has no attribute condition; spec §5b"
)
def test_micronaut_jms_over_sqs_is_sqs_on_both_sides(messaging_rows):
    assert {
        ("sqs", "inbound", "mn.orders.sqs"),
        ("sqs", "outbound", "mn.orders.sqs-out"),
    } <= messaging_rows
    assert ("jms", "inbound", "mn.orders.sqs") not in messaging_rows


def test_micronaut_jms_on_another_broker_stays_jms(messaging_rows):
    """Not xfail: ActiveMQ Classic's constant is not SQS's, and the existing pair is untouched."""
    assert {
        ("jms", "inbound", "mn.orders.classic"),
        ("jms", "inbound", "mn.orders.queue"),
        ("jms", "outbound", "mn.orders.audit"),
    } <= messaging_rows
