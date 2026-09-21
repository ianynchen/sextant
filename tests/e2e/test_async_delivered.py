"""Async and internal boundaries are delivered when a Spring Integration flow declared with
the framework's own annotations is visible, channel by channel.

**What "visible" means here.** A Spring Integration channel is an in-process pipe with no
wire identity of its own, so `spring-integration.yml` derives NO endpoint rows: it indexes
the channel each annotated handler READS and files a `channel_destination` open question
for it. Since spec 2026-09-21 (§3b, §4, §5) the wire behind a channel is read where the
code states it — the adapter's constructor argument, the container's `setQueueNames`, the
DSL factory's argument — by the three broker catalogs on `fluent`, and the channel edge
(`fed_by` ⋈ `read_by`) mints one inbound row per feeder and reader. So a channel some
registration FEEDS is an endpoint row naming the wire and the handler, and the question is
asked only for a channel nothing feeds. Both halves are asserted below: the rows per
fixture shape, and that the questions left are exactly the unfed channels.

**Not a document check.** Real bytecode, real pipeline, assertion on what was derived.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "spring-integration-probe"


@pytest.fixture(scope="module")
def derived(tmp_path_factory: pytest.TempPathFactory) -> tuple[set[str], list[dict]]:
    """The `channel_destination` questions' channels, and every endpoint row the three
    broker catalogs derived — one analysis, both read off it."""
    workspace_dir = tmp_path_factory.mktemp("integration")
    compile_fixture(FIXTURE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        questions = {
            str(row["path"])
            for row in workspace.query("open_questions")
            if str(row["question"]) == "channel_destination"
        }
        rows = [
            dict(row)
            for row in workspace.query("endpoints")
            if str(row["catalog_id"]).startswith("spring-integration-")
        ]
        return questions, rows
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def channels(derived: tuple[set[str], list[dict]]) -> set[str]:
    return derived[0]


def _wires(rows: list[dict], catalog_id: str) -> set[tuple[str, str | None, str | None, str, str]]:
    """`(direction, path, handler, caller, resolution)` per row of one catalog — the
    handler and caller by their method NAME, since the symbol's module coordinates and
    signature hash are the fixture build's, not this test's subject."""
    return {
        (
            str(row["direction"]),
            row["path"],
            _member(row["handler"]),
            _member(row["caller"]) or "",
            str(row["resolution"]),
        )
        for row in rows
        if row["catalog_id"] == catalog_id
    }


def _member(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    return symbol.split("#", 1)[1].split("(", 1)[0]


# The seven annotations Spring Integration ships beside the two the catalog already read,
# each with the channel attribute it ACTUALLY declares (javap, spring-integration-core 6.2.4).
# A flow written with these is the ordinary shape of a Spring Integration application, and
# before `G-47` every one of these channels was absent from the document.
_EXPECTED = {
    "raw.orders",  # @Transformer inputChannel
    "clean.orders",  # @Transformer outputChannel
    "valid.orders",  # @Filter outputChannel, @Splitter inputChannel
    "order.lines",  # @Splitter outputChannel, @Aggregator inputChannel
    "order.totals",  # @Aggregator outputChannel, @Router inputChannel
    "priced.totals",  # @BridgeFrom value
    "archive.orders",  # @BridgeTo value
}


def test_every_channel_bearing_annotation_derives_its_channel(channels: set[str]):
    """`G-47`. The catalog read 2 of the 9 channel-bearing annotations. A module using any
    of the other seven had those channels absent — and `@Transformer`, `@Filter`,
    `@Splitter`, `@Aggregator` and `@Router` are the components a Spring Integration flow
    is made of."""
    missing = _EXPECTED - channels
    assert missing == set(), (
        f"{len(missing)} of {len(_EXPECTED)} channels derived nothing: {sorted(missing)}. "
        f"Derived: {sorted(channels)}"
    )


def test_a_fed_channel_is_a_row_not_a_question(derived: tuple[set[str], list[dict]]):
    """The pin that MOVED with spec 2026-09-21 (its §10 names it as the one intended
    move): `Shape2AdapterAndHandler`'s `@ServiceActivator(inputChannel = "amqpInputChannel")`
    used to be the control question this test held. Its channel is fed by
    `ordersInboundAdapter`, whose container listens on `bean.orders.queue`, so the question
    is gone and the row stands in its place — the wire, the handler, the constructing
    method."""
    questions, rows = derived
    assert "amqpInputChannel" not in questions, sorted(questions)
    assert (
        "inbound",
        "bean.orders.queue",
        "handleOrder",
        "ordersInboundAdapter",
        "resolved",
    ) in _wires(rows, "spring-integration-amqp")


def test_the_remaining_questions_are_exactly_the_unfed_channels(channels: set[str]):
    """Every channel some registration feeds — `amqpInputChannel`, `pubsubInputChannel`,
    `pubsubOutputChannel`, `amqpOutboundChannel`, `kafkaInputChannel`, `dslNamedChannel` —
    is answered by a row and asked about no more. What is left: the seven annotation-only
    channels of `EveryChannelAnnotation` (nothing feeds them), `tickChannel` (a polled
    `@InboundChannelAdapter` — its destination IS the method), `constOrdersChannel` (the
    inlined constant, as before), and `amqpAuditChannel` twice — spelled by `handleOrder`'s
    `outputChannel` and by `handlePlaceholderChannel`'s `${probe.audit-channel}`, which
    the index resolves to it and which nothing feeds either."""
    assert channels == {
        *_EXPECTED,
        "tickChannel",
        "constOrdersChannel",
        "amqpAuditChannel",
        "${probe.audit-channel}",
    }


# --- the rows, per fixture shape (spec §11) --------------------------------------------


def test_pubsub_shape_four_rows(derived: tuple[set[str], list[dict]]):
    """Shape 4: two adapters feed `pubsubInputChannel` — one with the subscription as a
    literal and the channel as a qualified bean, one with the subscription as a `@Value`
    parameter (the row carries the `${…}` expression) and the channel by name — and both
    join `handlePubSubOrder`; the outbound handler bean derives its topic; Shape 5's
    ambiguous adapter (two channel beans, a parameter naming neither) keeps its row with
    `handler` NULL and binds nothing."""
    assert _wires(derived[1], "spring-integration-pubsub") == {
        ("inbound", "orders-sub", "handlePubSubOrder", "ordersSubscriptionAdapter", "resolved"),
        (
            "inbound",
            "${probe.subscription}",
            "handlePubSubOrder",
            "placeholderSubscriptionAdapter",
            "resolved",
        ),
        ("outbound", "orders-topic", None, "ordersTopicHandler", "resolved"),
        ("inbound", "ambiguous-sub", None, "ambiguousChannelAdapter", "resolved"),
    }


def test_amqp_shapes_rows(derived: tuple[set[str], list[dict]]):
    """Shapes 1, 2 and 5 and the variance arm: the container hop (`bean.orders.queue` →
    `handleOrder`), the outbound bean and the outbound DSL sink composing
    `exchange/routingKey`, the DSL flows with their lambda consumers — `dsl.q1`/`dsl.q2`
    one row each from one varargs call, `dsl.named.queue` joined through
    `dslNamedChannel` — and the variance sources, each an element of the VARARGS array
    and each read through the field ladder (spec §3c): a literal, an inlined constant, a
    raw placeholder, a `@Value` field, a `@Value` parameter and a properties getter all
    resolve (the last three to their `${…}` expression); a late constant (a `GETSTATIC`
    of a non-constant field) and a concatenation stay unresolved — no rung reads them."""
    wires = _wires(derived[1], "spring-integration-amqp")
    resolved = {wire for wire in wires if wire[4] == "resolved"}
    assert resolved == {
        ("inbound", "bean.orders.queue", "handleOrder", "ordersInboundAdapter", "resolved"),
        (
            "outbound",
            "bean.shipments.exchange/bean.shipments.rk",
            None,
            "shipmentsOutbound",
            "resolved",
        ),
        (
            "outbound",
            "dsl.shipments.exchange/dsl.shipments.rk",
            None,
            "lambda$shipmentsOutboundDslFlow$2",
            "resolved",
        ),
        (
            "inbound",
            "dsl.orders.queue",
            "lambda$ordersInboundDslFlow$1",
            "ordersInboundDslFlow",
            "resolved",
        ),
        (
            "inbound",
            "dsl.named.queue",
            "lambda$namedChannelDslFlow$3",
            "namedChannelDslFlow",
            "resolved",
        ),
        ("inbound", "dsl.q1", "lambda$twoQueueDslFlow$1", "twoQueueDslFlow", "resolved"),
        ("inbound", "dsl.q2", "lambda$twoQueueDslFlow$1", "twoQueueDslFlow", "resolved"),
        (
            "inbound",
            "variance.literal.queue",
            "lambda$literalQueueFlow$0",
            "literalQueueFlow",
            "resolved",
        ),
        (
            "inbound",
            "const.orders.queue",
            "lambda$constantQueueFlow$1",
            "constantQueueFlow",
            "resolved",
        ),
        (
            "inbound",
            "${probe.placeholder-queue}",
            "lambda$placeholderQueueFlow$5",
            "placeholderQueueFlow",
            "resolved",
        ),
        (
            "inbound",
            "${probe.value-queue}",
            "lambda$valueFieldQueueFlow$3",
            "valueFieldQueueFlow",
            "resolved",
        ),
        (
            "inbound",
            "${probe.param-queue}",
            "lambda$valueParameterQueueFlow$4",
            "valueParameterQueueFlow",
            "resolved",
        ),
        (
            "inbound",
            "${probe.queue}",
            "lambda$propertiesQueueFlow$6",
            "propertiesQueueFlow",
            "resolved",
        ),
    }
    assert {wire[3] for wire in wires - resolved} == {
        "lateConstantQueueFlow",
        "concatenatedQueueFlow",
    }


def test_kafka_shapes_rows(derived: tuple[set[str], list[dict]]):
    """Shapes 3 and 5: two topics from one varargs call with the lambda consumer; the
    outbound sink's topic from the lambda flow form; the router DIVERTS so the handler
    after it is NULL and the row resolved; the flow ending in `kafkaInputChannel` is
    joined to its `@ServiceActivator`; the `Pattern` subscription is not a topic —
    unresolved, never a guess."""
    assert _wires(derived[1], "spring-integration-kafka") == {
        (
            "inbound",
            "kafka.orders.topic",
            "lambda$kafkaInboundFlow$0",
            "kafkaInboundFlow",
            "resolved",
        ),
        (
            "inbound",
            "kafka.orders.retry.topic",
            "lambda$kafkaInboundFlow$0",
            "kafkaInboundFlow",
            "resolved",
        ),
        ("outbound", "kafka.shipments.topic", None, "lambda$kafkaOutboundFlow$1", "resolved"),
        ("inbound", "kafka.routed.topic", None, "kafkaRoutedFlow", "resolved"),
        ("inbound", "kafka.channelled.topic", "handleKafkaOrder", "kafkaToChannelFlow", "resolved"),
        ("inbound", None, "lambda$kafkaPatternFlow$4", "kafkaPatternFlow", "unresolved"),
    }
