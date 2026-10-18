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
STREAMS = FIXTURES / "orders-streams"
PEKKO = FIXTURES / "orders-pekko"
FIELD_HELD = FIXTURES / "orders-fieldheld"


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


@pytest.fixture(scope="module")
def field_held_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(direction, path, resolution)` for the field-held destination fixture."""
    workspace_dir = tmp_path_factory.mktemp("kafka_fieldheld")
    compile_fixture(FIELD_HELD)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIELD_HELD), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["direction"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "kafka"
        }
    finally:
        workspace.close()


@pytest.mark.xfail(
    strict=True,
    reason="The walk's sixth edge is unbuilt — spec 2026-10-18-the-sixth-edge-design.md. "
    "The fixture and this assertion come first (GUIDELINES §4.1); `strict` is what makes the "
    "marker come off in the commit that builds the edge.",
)
def test_a_destination_held_in_a_constructor_assigned_field_derives_every_value(field_held_rows):
    """The walk's SIXTH EDGE (spec 2026-10-18, `OI-136`, `OI-141`), and the intention test
    for it.

    `kafkaTemplate.send(topic, payload)` names nothing at the call site — the argument is a
    field read — and the only statement of the value is the literal each construction passed:

        private final String topic;
        OrderPublisher(String topic, …) {{ this.topic = topic; }}
        void publish(…) {{ kafkaTemplate.send(topic, payload); }}

        new OrderPublisher("orders-v2", …)      new OrderPublisher("orders-audit", …)

    **Measured before the edge: ONE row, `path` NULL, `unresolved`** — `_binding` answered
    `no_writer` though `field_writes` had recorded `OrderPublisher#topic ← parameter 0` all
    along and `value_edges.sql` read that table zero times.

    **TWO rows and both resolved, which is §4's ruling rather than a hedge.** The set of
    possible topics is CLOSED — every construction is in this module — so enumerating both is
    the exact answer, not an ambiguity. The user's words, 2026-10-18: *"the parameter is
    preconstructed, meaning only certain values exist — we should be able to enumerate all
    possible values, that's exactly match."* A `narrowed` here would mark an exact answer as a
    doubt.
    """
    assert field_held_rows == {
        ("outbound", "orders-v2", "resolved"),
        ("outbound", "orders-audit", "resolved"),
    }


def test_kafka_template_receive_derives_an_inbound_row_on_the_topic(kafka_rows):
    """`G-44`, Kafka. `KafkaTemplate.receive(String topic, int partition, long offset,
    Duration)` — spring-kafka 3.1.4 — is a synchronous read of one record: an inbound
    boundary on the topic at argument 0."""
    assert ("kafka", "inbound", "recv.orders.replay") in kafka_rows, sorted(kafka_rows)


@pytest.fixture(scope="module")
def streams_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every kafka row the streams fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("kafka_streams")
    compile_fixture(STREAMS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(STREAMS), "--workspace", str(workspace_dir)]
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


def test_a_streams_dsl_topology_derives_every_source_and_sink(streams_rows):
    """`G-31`. `StreamsBuilder.stream/table/globalTable` consume the topic at argument 0
    (a `Collection` through `List.of`); `KStream.to` produces to it. kafka-streams 3.6.2."""
    expected = {
        ("kafka", "inbound", "streams.orders.placed"),
        ("kafka", "inbound", "streams.audit.a"),
        ("kafka", "inbound", "streams.audit.b"),
        ("kafka", "inbound", "streams.customers"),
        ("kafka", "inbound", "streams.rates"),
        ("kafka", "outbound", "streams.orders.shouted"),
        ("kafka", "outbound", "streams.audit.merged"),
        ("kafka", "outbound", "streams.customers.changelog"),
    }
    missing = expected - streams_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(streams_rows)}"


def test_a_processor_api_topology_derives_its_sink_and_source(streams_rows):
    """`Topology.addSink(name, topic, parents…)` names the topic at argument 1.
    `addSource(name, topics…)` takes its topics as a VARARGS array at argument 1 —
    MEASURED (w60, Step 4): that array reaches `single_call` as one `array`-kind
    argument (extractor capability 9.15), and `channels_of` — already shipped for
    `spring-websocket.yml`'s `addHandler(handler, String... paths)` — reads it
    element-wise with no `channel_via` needed, deriving one inbound row per topic."""
    assert ("kafka", "outbound", "streams.pa.out") in streams_rows, sorted(streams_rows)
    assert ("kafka", "inbound", "streams.pa.in.a") in streams_rows, sorted(streams_rows)
    assert ("kafka", "inbound", "streams.pa.in.b") in streams_rows, sorted(streams_rows)


@pytest.fixture(scope="module")
def pekko_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every kafka row the Pekko Connectors Kafka
    fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("kafka_pekko")
    compile_fixture(PEKKO)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(PEKKO), "--workspace", str(workspace_dir)]
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


def test_pekko_consumer_sources_derive_one_inbound_row_per_subscribed_topic(pekko_rows):
    """`Consumer.plainSource(settings, Subscriptions.topics(…))` — pekko-connectors-kafka
    1.1.0. The topics are the varargs of a factory call at argument 1: the `channel_via`
    form `kafka-consumer.yml` uses for `List.of`."""
    expected = {
        ("kafka", "inbound", "pk.orders.placed"),
        ("kafka", "inbound", "pk.audit.a"),
        ("kafka", "inbound", "pk.audit.b"),
    }
    missing = expected - pekko_rows
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(pekko_rows)}"
