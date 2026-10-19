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
        ("outbound", "orders-dead-letter", "resolved"),
        ("outbound", "orders-overwritten", "resolved"),
        ("outbound", "orders-live", "resolved"),
    }


@pytest.mark.pins("values.a-binding-written-from-a-CONSTANT-answers-that-constant")
def test_a_destination_held_in_a_field_written_from_a_CONSTANT_derives_that_value(
    field_held_rows,
):
    """The other half of the same fixture, and the other kind of write (`OI-138` cause 2).

    `DeadLetterPublisher` holds its topic in a field too, but the write is not from a
    parameter:

        private String topic = "orders-dead-letter";     // ldc; putfield
        void publish(…) {{ kafkaTemplate.send(topic, payload); }}   // getfield

    `field_writes` could say only *"this field was written from argument N of that method"*,
    so a write from a CONSTANT had nothing to point at and **no fact was emitted at all** —
    the walk then answered `no_writer` about a literal one line above the read, and the row
    published no destination.

    **Measured on real code:** `spring-petclinic-microservices` holds an outbound HOST this
    way (`private String hostname = "http://visits-service/"`, read into
    `hostname + "pets/visits?petId={petId}"`), and that call published `path` NULL while its
    four siblings resolved. A census over every compiled module under `examples/` — 3,568
    classes in 56 modules — counts 25 constant field writes and exactly one on an ADDRESS:
    rare, because javac resolves a `final` constant-initialised field at the use site and
    most hosts arrive by injection. A `no_writer` about a literal in the same file is a false
    statement whatever its frequency, which is why the change ships at that yield.
    """
    assert ("outbound", "orders-dead-letter", "resolved") in field_held_rows


@pytest.mark.pins("values.a-write-a-PRIVATE-uncalled-method-makes-is-not-a-value")
def test_a_write_that_cannot_RUN_contributes_no_destination(field_held_rows):
    """**Two writes that cannot produce a value, and the rows that must not carry them.**
    Both were published at `resolved` by the first build of the constant read, and review
    found them before it shipped: a value the code cannot produce is the worst answer
    available (§8), worse than the `no_writer` it replaced.

    `OverwrittenPublisher` holds `private String topic = "never-reached-default"` and its one
    constructor overwrites it two instructions later, in the same basic block — so no read
    can observe the initialiser, and the row is `orders-overwritten` alone.

    `ResettablePublisher` holds `private String topic = "orders-live"` and a PRIVATE
    `switchToBackup()` that nothing calls. Private means every possible caller is in that
    class, so an uncalled one cannot run; the row is `orders-live` alone. A PUBLIC uncalled
    method stays reported — it is called by something unscanned, which is a different
    statement — and `OrderPublisher`'s own rows prove the parameter arm is untouched.
    """
    published = {path for _, path, _ in field_held_rows}
    assert "never-reached-default" not in published
    assert "orders-backup-nothing-calls" not in published
    assert {"orders-overwritten", "orders-live"} <= published


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
