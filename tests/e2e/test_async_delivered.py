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

import json
import re

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.query.trace import traces_of
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
        # **Converted 2026-10-17** (Task 9, carry-forward (b)): was
        # `(None, "unresolved")`. `spring-integration-kafka.yml` had stated `Pattern`
        # subscriptions as a boundary while `kafka-consumer.yml` and `spring-kafka.yml`
        # both read the same shape — "a topic pattern lands on `path` verbatim, never
        # expanded into real topic names" — so the two rows were aligned with that rule.
        # READ AGAINST SOURCE, which is what §3c demands of a conversion:
        # `Shape5Flows.java:80` subscribes with `Pattern.compile("kafka\\.pattern\\..*")`,
        # and this is that string character for character. Nothing claims a topic of that
        # literal name exists; the row says what the module subscribes with.
        (
            "inbound",
            "kafka\\.pattern\\..*",
            "lambda$kafkaPatternFlow$4",
            "kafkaPatternFlow",
            "resolved",
        ),
    }


# --- Temporal: fixtures/temporal-probe (spec 2026-09-22, task-6 report table) -----------
#
# The catalogs and the fixture already ship and the rows already derive; this section pins
# them so a future change that breaks Temporal fails a test instead of shipping. The nine
# endpoint rows and eight endpoint_metadata rows below are read off one real analysis of
# `fixtures/temporal-probe`, not predicted — the task-6 report's table is the contract, and
# task-6 report table, arms 2-4 predate the naming word that composes
# `<workflow type>/<member>` for signals/queries/updates; the actual derived paths are
# `OrderWorkflow/cancel`, `/status`, `/amend`, and each of those three carries a
# `task_queue: orders` metadata row (a signal reaches the same worker as the workflow).

TEMPORAL_FIXTURE = FIXTURES / "temporal-probe"


@pytest.fixture(scope="module")
def temporal(tmp_path_factory: pytest.TempPathFactory) -> tuple[list[dict], list[dict]]:
    """Every `endpoints` and `endpoint_metadata` row `fixtures/temporal-probe` derives —
    one analysis, every test below reads off it."""
    workspace_dir = tmp_path_factory.mktemp("temporal")
    compile_fixture(TEMPORAL_FIXTURE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(TEMPORAL_FIXTURE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        endpoints = [
            dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "temporal"
        ]
        metadata = [
            dict(row)
            for row in workspace.query("endpoint_metadata")
            if str(row["protocol"]) == "temporal"
        ]
        return endpoints, metadata
    finally:
        workspace.close()


def _endpoint_row(row: dict) -> tuple[str, str, str, str | None, str | None]:
    """`(protocol, direction, method, path, handler-or-caller member name)` — an inbound
    row carries a handler, an outbound row carries a caller, never both."""
    member = _member(row["handler"]) if row["handler"] is not None else _member(row["caller"])
    return (str(row["protocol"]), str(row["direction"]), str(row["method"]), row["path"], member)


def _metadata_row(row: dict) -> tuple[str, str, str, str | None, str, object, str | None]:
    """`(protocol, direction, method, path, kind, value, member)` — `endpoint_metadata`'s
    own `caller` column here names the symbol the metadata rides on (the implementing
    method), not a separate call site."""
    return (
        str(row["protocol"]),
        str(row["direction"]),
        str(row["method"]),
        row["path"],
        str(row["kind"]),
        row["value"],
        _member(row["caller"]),
    )


def test_temporal_shapes_nine_rows(temporal: tuple[list[dict], list[dict]]):
    """task-6 report table, arms 1-4, 6-8, 11-12: every naming branch and both partitions,
    as rows. Workflow/signal/query/update read `declaring_type_scoped_name` off the
    CONTRACT (`OrderWorkflow`), never the implementor; activities read
    `prefixed_capitalized_construct_name`, prefix skipped where an explicit
    `@ActivityMethod(name=...)` is given (`Charge`) and applied where it is not
    (`billing_RefundCard`)."""
    endpoints, _ = temporal
    assert len(endpoints) == 9
    assert {_endpoint_row(r) for r in endpoints} == {
        ("temporal", "inbound", "workflow", "OrderWorkflow", "processOrder"),
        ("temporal", "inbound", "signal", "OrderWorkflow/cancel", "cancel"),
        ("temporal", "inbound", "query", "OrderWorkflow/status", "status"),
        ("temporal", "inbound", "update", "OrderWorkflow/amend", "amend"),
        ("temporal", "inbound", "activity", "Charge", "charge"),
        ("temporal", "inbound", "activity", "billing_RefundCard", "refundCard"),
        ("temporal", "outbound", "workflow", "ShipOrder", "ship"),
        ("temporal", "outbound", "workflow", "PaymentsWorkflow", "processPayment"),
        ("temporal", "outbound", "workflow", "OrderWorkflow", "startUntyped"),
    }


def test_temporal_shapes_eight_metadata_rows(temporal: tuple[list[dict], list[dict]]):
    """task-6 report table, arms 1-4 and 7-8: `task_queue` riding on the implementing
    class — `orders` for `OrderWorkflowImpl#processOrder` and its three signal/query/update
    siblings (a signal reaches the same worker as the workflow it belongs to), and
    `billing` + `billing-retry` for both of `BillingActivitiesImpl`'s methods, since its
    `@ActivityImpl(taskQueues = {...})` names two queues per member."""
    _, metadata = temporal
    assert len(metadata) == 8
    assert {_metadata_row(r) for r in metadata} == {
        (
            "temporal",
            "inbound",
            "workflow",
            "OrderWorkflow",
            "task_queue",
            "orders",
            "processOrder",
        ),
        ("temporal", "inbound", "signal", "OrderWorkflow/cancel", "task_queue", "orders", "cancel"),
        ("temporal", "inbound", "query", "OrderWorkflow/status", "task_queue", "orders", "status"),
        ("temporal", "inbound", "update", "OrderWorkflow/amend", "task_queue", "orders", "amend"),
        ("temporal", "inbound", "activity", "Charge", "task_queue", "billing", "charge"),
        ("temporal", "inbound", "activity", "Charge", "task_queue", "billing-retry", "charge"),
        (
            "temporal",
            "inbound",
            "activity",
            "billing_RefundCard",
            "task_queue",
            "billing",
            "refundCard",
        ),
        (
            "temporal",
            "inbound",
            "activity",
            "billing_RefundCard",
            "task_queue",
            "billing-retry",
            "refundCard",
        ),
    }


def test_workflow_interface_default_method_derives_nothing(
    temporal: tuple[list[dict], list[dict]],
):
    """task-6 report table, arm 5: `OrderWorkflow.helper()` carries no Temporal annotation
    at all, so it is not a member of any Temporal-driven catalog and no row of any kind
    can name it."""
    endpoints, _ = temporal
    members = {_member(r["handler"]) for r in endpoints if r["handler"]} | {
        _member(r["caller"]) for r in endpoints if r["caller"]
    }
    assert "helper" not in members
    assert not any("helper" in str(r["path"]) for r in endpoints if r["path"])


def test_activity_impl_only_method_derives_nothing(temporal: tuple[list[dict], list[dict]]):
    """task-6 report table, arm 9: `BillingActivitiesImpl.reloadRates()` is declared only
    by the implementor, never by `BillingActivities`.

    **The fence that stops it is `declared_on: interface`, not `declared_type_methods`**,
    and this docstring used to credit the wrong one. `reloadRates` is enclosed by a CLASS,
    so the catalog's own partition gates the whole type out before any member rule runs —
    swapping `members:` to `public_methods` leaves this arm green. The member word's own
    discriminating shape is one interface up, and it is
    `test_a_sub_interface_of_an_activity_contract_derives_nothing` below."""
    endpoints, _ = temporal
    handler_members = {_member(r["handler"]) for r in endpoints if r["handler"]}
    assert "reloadRates" not in handler_members
    assert not any(r["path"] == "billing_ReloadRates" for r in endpoints)


def test_a_sub_interface_of_an_activity_contract_derives_nothing(
    temporal: tuple[list[dict], list[dict]],
):
    """`declared_type_methods`, measured — the arm the branch review added because nothing
    measured the word at all.

    `AuditedLedgerActivities extends LedgerActivities` carries `@ActivityInterface` only
    SYNTHETICALLY, through the inheritance walk, and declares a member of its own. The
    word admits a member only where the member's own declaring type carries the gate as a
    real annotation row, so `audit` derives nothing.

    WHY that matters, measured against this shipped catalog: under `public_methods` the
    same fixture derives `outbound activity "ledger_Audit"` on
    `AuditedLedgerActivities#audit` — the sub-declared member published under the BASE's
    `namePrefix`, an activity name no worker polls for, at `resolved`/`compiler`. Before
    this arm existed that swap moved no shipped output and failed no test.

    `LedgerActivities` itself derives nothing either, for a different fence: no class
    implements it, but an interface in this module EXTENDS it, so the outbound (SEI) fence
    subtracts the contract and the flip to inbound declines. Asserted, so that a change
    which starts publishing the base cannot hide behind this test's other half."""
    endpoints, _ = temporal
    members = {_member(r["handler"]) for r in endpoints if r["handler"]} | {
        _member(r["caller"]) for r in endpoints if r["caller"]
    }
    assert "audit" not in members
    assert "post" not in members
    assert not any(str(r["path"]).startswith("ledger_") for r in endpoints if r["path"])


def test_shipping_activities_pair_derives_nothing(temporal: tuple[list[dict], list[dict]]):
    """task-6 report table, arm 10: `ShippingActivities`/`ShippingActivitiesImpl` is
    implemented in this module, but the implementor carries no `@ActivityImpl` — the flip
    to inbound DECLINES, and the outbound (SEI) fence still subtracts the interface because
    it IS implemented here. Net zero in either direction: neither served nor called."""
    endpoints, _ = temporal
    handler_members = {_member(r["handler"]) for r in endpoints if r["handler"]}
    caller_members = {_member(r["caller"]) for r in endpoints if r["caller"]}
    assert "arrangePickup" not in handler_members | caller_members
    # `ShippingActivities` carries no `namePrefix`, so a fabricated row for this arm would
    # be `prefixed_capitalized_construct_name`'s output with an empty prefix: the bare
    # capitalized member name, "ArrangePickup" — not a name containing "Shipping" or the
    # unprefixed, uncapitalized method name.
    assert not any(r["path"] == "ArrangePickup" for r in endpoints)


def test_untyped_signal_call_derives_nothing(temporal: tuple[list[dict], list[dict]]):
    """task-6 report table, arm 13: `stub.signal("cancel", "late")` — argument 0 is a bare
    member name with no workflow type anywhere at the call site, so a path of just
    "cancel" would collide with every other workflow's signal of that name. Under-reporting
    is the honest read; this call derives no row."""
    endpoints, _ = temporal
    caller_members = {_member(r["caller"]) for r in endpoints if r["caller"]}
    assert "signalUntyped" not in caller_members
    assert not any(r["path"] == "cancel" for r in endpoints)


def test_attach_to_running_execution_derives_nothing(
    temporal: tuple[list[dict], list[dict]],
):
    """task-6 report table, arm 14: `newWorkflowStub(OrderWorkflow.class, "wf-123")`
    addresses an already-running execution and starts nothing — no call site is read for
    it at all, so it derives no row."""
    endpoints, _ = temporal
    caller_members = {_member(r["caller"]) for r in endpoints if r["caller"]}
    assert "attachToRunning" not in caller_members


# --- The Vert.x event bus: fixtures/orders-eventbus (spec 2026-09-22 §3, §4) ------------
#
# Every row below was read off ONE REAL ANALYSIS of the committed fixture, not predicted:
# `.venv/bin/sextant module analyze fixtures/orders-eventbus --workspace /tmp/eb`, then the
# workspace queried. The sets are EXACT — every row, every column — because a subset check
# or a count would pass for a catalog that published one address as another.

EVENTBUS_FIXTURE = FIXTURES / "orders-eventbus"

_ORDER = "com/acme/eb/Order#"


@pytest.fixture(scope="module")
def eventbus(tmp_path_factory: pytest.TempPathFactory) -> tuple[list[dict], list[dict]]:
    """Every `endpoints` and `endpoint_metadata` row `fixtures/orders-eventbus` derives —
    one analysis, every test below reads off it."""
    workspace_dir = tmp_path_factory.mktemp("eventbus")
    compile_fixture(EVENTBUS_FIXTURE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(EVENTBUS_FIXTURE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        endpoints = [
            dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "eventbus"
        ]
        metadata = [
            dict(row)
            for row in workspace.query("endpoint_metadata")
            if str(row["protocol"]) == "eventbus"
        ]
        return endpoints, metadata
    finally:
        workspace.close()


def _shape(value: str | None) -> str | None:
    """The `shape_id` inside a `request_shape` blob, or None where the row carries none."""
    return None if value is None else str(json.loads(value)["shape_id"])


def _typed_member(symbol: str | None) -> str | None:
    """`Class.member` — the declaring type kept, unlike `_member` above.

    This fixture declares `receiveOrders` on BOTH `OrderBus` and `MutinyOrderBus`, one
    per facade, so a bare member name would let the two rows swap without the set
    noticing. The module coordinates and the signature hash are still dropped: those are
    the fixture build's, not this test's subject."""
    if symbol is None:
        return None
    owner, member = symbol.split("#", 1)
    return f"{owner.rsplit('/', 1)[-1]}.{member.split('(', 1)[0]}"


def _eventbus_row(row: dict) -> tuple:
    """`(catalog, direction, path, handler, caller, resolution, request shape)` — the whole
    row a reader would act on, per catalog, so a path that moved between catalogs or a
    handler that became a caller fails here."""
    return (
        str(row["catalog_id"]),
        str(row["direction"]),
        row["path"],
        _typed_member(row["handler"]),
        _typed_member(row["caller"]),
        str(row["resolution"]),
        _shape(row["request_shape"]),
    )


def test_eventbus_shapes_rows(eventbus: tuple[list[dict], list[dict]]):
    """Spec §4's second fixture, arm by arm, off a real analysis.

    Twenty rows and no more. The four catalogs partition the surface rather than
    overlapping on it: `vertx-eventbus.yml` takes the core interface's one-call forms,
    `vertx-eventbus-chain.yml` the two-step ones, `vertx-eventbus-mutiny.yml` the facade a
    Quarkus service injects, and `quarkus-consume-event.yml` the declarations. Two arms of
    the fixture derive NOTHING and their absence is what the count holds — the
    handler-less `consumer("orders.unhandled")` (M6/CP-31 Q4) and `Order` itself, which is
    a payload and not an endpoint of anything.

    The values worth reading twice:
      * `com.acme.eb.OrderConsumers` — the bare `@ConsumeEvent`'s address is the declaring
        bean class's FULLY-QUALIFIED name (CP-31 Q7), not the method name and not the
        simple name;
      * `${orders.address}` at `unresolved` — a placeholder carried verbatim, never a
        guessed deployed value;
      * `orders.headers` and `orders.mutiny.headers` both carrying `com/acme/eb/Order#` —
        the payload of a `(MultiMap, Order)` method is its SECOND parameter, which is what
        `request_body.excludes` reads, and Quarkus's own `isMessageHeaders` accepts the
        core `MultiMap` and the Mutiny one alike (CP-31 Q11), so the list names both;
      * `orders.created` appearing TWICE under `quarkus-consume-event`, once per handler,
        and carrying `com/acme/eb/Order#` on BOTH, with `orders.mutiny.created` the same
        pair's Mutiny spelling —
        `test_the_envelope_spelling_and_the_payload_spelling_record_one_shape` below is
        where those equalities are the subject rather than one column of a set;
      * `orders.twostep`'s handler is the LAMBDA `.handler(...)` was given, while
        `orders.inbox`'s is the enclosing method: the one-call form registers at the call
        the catalog matched, the chain registers at its terminal;
      * the four `mutiny.*` rows come from `vertx-eventbus-mutiny.yml` and NOT from
        `vertx-eventbus.yml`, which is the whole point of the fourth file — CP-31 Q8
        measured that the facade shares no descriptor with the core interface.

    **What this set does NOT catch, stated so the docstring does not read as coverage it
    does not provide.** The `catalog_id` column above pins which catalog OWNS each row,
    but it does not pin that the two `single_call` catalogs stay partitioned: a leak in
    the other direction — the core catalog widened to name the facade as a second owner
    and given the facade's descriptor as a row — was INJECTED and measured, and this
    analysis still produced exactly the set this assertion then held, with `catalog_id`
    unchanged, because two catalogs deriving the identical row collapse into one. That
    measurement was taken at SEVENTEEN rows, before the envelope arm and the two Mutiny
    arms; the three arms since do not touch what it showed. A count and an exact set are
    both blind to that.
    `test_call_engines.py::test_the_core_catalog_declines_the_facades_descriptor_and_the_facade_the_cores`
    is what holds the partition, and it does hold it: the same injection makes it fail.
    """
    endpoints, _ = eventbus
    assert len(endpoints) == 20
    assert {_eventbus_row(r) for r in endpoints} == {
        # --- quarkus-consume-event: the declarations -------------------------
        (
            "quarkus-consume-event",
            "inbound",
            "${orders.address}",
            "OrderConsumers.onConfiguredOrder",
            None,
            "unresolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "com.acme.eb.OrderConsumers",
            "OrderConsumers.onAnyOrder",
            None,
            "resolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "orders.cluster",
            "OrderConsumers.onClusteredOrder",
            None,
            "resolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "orders.created",
            "OrderConsumers.onOrderCreated",
            None,
            "resolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "orders.created",
            "OrderConsumers.onOrderCreatedEnvelope",
            None,
            "resolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "orders.headers",
            "OrderConsumers.onOrderWithHeaders",
            None,
            "resolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "orders.mutiny.created",
            "OrderConsumers.onMutinyOrderEnvelope",
            None,
            "resolved",
            _ORDER,
        ),
        (
            "quarkus-consume-event",
            "inbound",
            "orders.mutiny.headers",
            "OrderConsumers.onMutinyHeaderOrder",
            None,
            "resolved",
            _ORDER,
        ),
        # --- vertx-eventbus: the core interface's one-call forms -------------
        (
            "vertx-eventbus",
            "inbound",
            "orders.inbox",
            "OrderBus.receiveOrders",
            None,
            "resolved",
            None,
        ),
        (
            "vertx-eventbus",
            "inbound",
            "orders.local",
            "OrderBus.receiveLocalOrders",
            None,
            "resolved",
            None,
        ),
        (
            "vertx-eventbus",
            "outbound",
            "orders.created",
            None,
            "OrderBus.placeOrder",
            "resolved",
            _ORDER,
        ),
        (
            "vertx-eventbus",
            "outbound",
            "orders.events",
            None,
            "OrderBus.announceOrder",
            "resolved",
            _ORDER,
        ),
        (
            "vertx-eventbus",
            "outbound",
            "orders.lookup",
            None,
            "OrderBus.lookupOrder",
            "resolved",
            _ORDER,
        ),
        (
            "vertx-eventbus",
            "outbound",
            "orders.priority",
            None,
            "OrderBus.placeOrderWithOptions",
            "resolved",
            _ORDER,
        ),
        # --- vertx-eventbus-chain: the two-step forms ------------------------
        (
            "vertx-eventbus-chain",
            "inbound",
            "orders.twostep",
            "OrderBus.lambda$receiveOrdersInTwoSteps$2",
            "OrderBus.receiveOrdersInTwoSteps",
            "resolved",
            None,
        ),
        (
            "vertx-eventbus-chain",
            "outbound",
            "orders.shipments",
            None,
            "OrderBus.shipOrder",
            "resolved",
            _ORDER,
        ),
        # --- vertx-eventbus-mutiny: the facade a Quarkus service injects -----
        (
            "vertx-eventbus-mutiny",
            "inbound",
            "mutiny.orders.inbox",
            "MutinyOrderBus.receiveOrders",
            None,
            "resolved",
            None,
        ),
        (
            "vertx-eventbus-mutiny",
            "outbound",
            "mutiny.orders.created",
            None,
            "MutinyOrderBus.placeOrder",
            "resolved",
            _ORDER,
        ),
        (
            "vertx-eventbus-mutiny",
            "outbound",
            "mutiny.orders.events",
            None,
            "MutinyOrderBus.announceOrder",
            "resolved",
            _ORDER,
        ),
        (
            "vertx-eventbus-mutiny",
            "outbound",
            "mutiny.orders.lookup",
            None,
            "MutinyOrderBus.lookupOrder",
            "resolved",
            _ORDER,
        ),
    }


def test_the_envelope_spelling_and_the_payload_spelling_record_one_shape(
    eventbus: tuple[list[dict], list[dict]],
):
    """Two spellings of ONE wire contract, one shape — the pin, asserted as an EQUALITY
    between the two rows rather than against a literal.

    `OrderConsumers` declares `orders.created` twice: `onOrderCreated(Order)` and
    `onOrderCreatedEnvelope(Message<Order>)`. Quarkus permits both — MEASURED (CP-31 Q12,
    quarkus-vertx-deployment 3.17.5): its own validation constant reads *"An event consumer
    business method that accepts io.vertx.core.eventbus.Message or
    io.vertx.mutiny.core.eventbus.Message must return void"*, so the envelope parameter is
    ordinary input and the only condition attached to it is the one this fixture arm
    satisfies. `Message<T>` is the bus's own framing — `address()`, `headers()`,
    `replyAddress()`, `isSend()` and `body()` (CP-31 Q10a/Q10b, byte-identical at 4.5.10 and
    5.0.0) — and `body()` is the one of the five that names what crossed the wire.

    Asserted as `==` between the two rows, not as two separate literals: the claim is that
    the spelling does not change the contract, and an equality is what says that. It is then
    also asserted to be `Order`, because two rows could be equal by both being wrong.

    Before the `wrappers` entry that makes this pass, the envelope row recorded
    `io/vertx/core/eventbus/Message#<com/acme/eb/Order#>` and the analysis expanded
    `Message` ITSELF as a second shape — so the second assertion below is not redundant
    with the first, it is what catches the whole envelope being published as a payload
    type. The wire's other half is `m.reply(order)`, an `Order`, so a linker holding the
    envelope shape on one side would never match the two halves of one address.

    **BOTH envelope types, because Quarkus accepts both.** CP-31 Q11 measured
    `VertxConstants.isMessage` returning true for `io.vertx.core.eventbus.Message` **or**
    `io.vertx.mutiny.core.eventbus.Message`, so the catalog declares a wrapper for each and
    `onMutinyOrderEnvelope` is the arm that exercises the second one. It is asserted the
    same way and separately: measured, without its wrapper entry that row records
    `io/vertx/mutiny/core/eventbus/Message#<com/acme/eb/Order#>` and the analysis grows a
    second shape, exactly as the core one did. The two are DIFFERENT types (CP-31 Q10c),
    so one entry never covers the other and one assertion never covers the other either.
    """
    endpoints, _ = eventbus
    quarkus = [r for r in endpoints if str(r["catalog_id"]) == "quarkus-consume-event"]
    shapes = {
        _typed_member(r["handler"]): _shape(r["request_shape"])
        for r in quarkus
        if r["path"] == "orders.created"
    }
    assert set(shapes) == {"OrderConsumers.onOrderCreated", "OrderConsumers.onOrderCreatedEnvelope"}
    assert (
        shapes["OrderConsumers.onOrderCreatedEnvelope"] == shapes["OrderConsumers.onOrderCreated"]
    )
    assert shapes["OrderConsumers.onOrderCreatedEnvelope"] == _ORDER

    mutiny = {
        _typed_member(r["handler"]): _shape(r["request_shape"])
        for r in quarkus
        if r["path"] == "orders.mutiny.created"
    }
    assert set(mutiny) == {"OrderConsumers.onMutinyOrderEnvelope"}
    assert mutiny["OrderConsumers.onMutinyOrderEnvelope"] == shapes["OrderConsumers.onOrderCreated"]
    assert mutiny["OrderConsumers.onMutinyOrderEnvelope"] == _ORDER


def test_every_eventbus_row_is_verbless_and_states_no_reply_shape(
    eventbus: tuple[list[dict], list[dict]],
):
    """Two claims the row set above does not carry, each asserted over EVERY row rather
    than sampled.

    `method` is NULL because an event-bus address has no verb — `eventbus` is not a verbed
    protocol and none of the four catalogs declares `all_methods`. `response_shape` is NULL
    everywhere INCLUDING on `orders.lookup` and `mutiny.orders.lookup`, which are
    `request(...)` calls: the reply type is the call's RETURN type — `Future<Message<T>>`
    on the core interface, `Uni<Message<T>>` on the facade — and `single_call`'s only
    response word (`response_arg`, an argument POSITION) cannot name one. Both catalogs
    state that as a boundary; this is what holds it, so the day an engine word closes it
    this test fails and the boundary is retired deliberately rather than drifting."""
    endpoints, _ = eventbus
    assert {row["method"] for row in endpoints} == {None}
    assert {row["response_shape"] for row in endpoints} == {None}


def test_a_consumer_never_given_a_handler_derives_nothing(
    eventbus: tuple[list[dict], list[dict]],
):
    """M6's consequence, proven by running the analysis rather than reasoned about.

    `OrderBus.prepareUnhandledConsumer()` calls `bus.consumer("orders.unhandled")` and
    then only `setMaxBufferedMessages(16)`. MEASURED (CP-31 Q4, vertx-core 4.5.10 and
    5.0.0, byte-identical): registration happens inside `MessageConsumer.handler`, which
    this arm never calls — so this address receives no message and a row for it would be
    an endpoint nothing serves. Both halves are asserted: no row anywhere names the
    address, and no row anywhere names the method that built the consumer."""
    endpoints, metadata = eventbus
    assert [r for r in endpoints if r["path"] == "orders.unhandled"] == []
    assert [r for r in metadata if r["path"] == "orders.unhandled"] == []
    members = {_member(r["handler"]) for r in endpoints} | {_member(r["caller"]) for r in endpoints}
    assert "prepareUnhandledConsumer" not in members


def test_eventbus_local_metadata_is_the_measured_default_or_the_declared_value(
    eventbus: tuple[list[dict], list[dict]],
):
    """`@ConsumeEvent.local()`'s `AnnotationDefault` is the boolean `true` (CP-31 Q6), so
    an undecorated consumer is LOCAL-ONLY and `absent_value: "true"` is what says so. The
    set is exact and covers all eight Quarkus consumers, which is what makes it a pin: a
    `metadata_from` that wrote its `absent_value` unconditionally would still produce seven
    of these rows, and `orders.cluster`'s `false` is the one that fails it.

    `kind` is `local`, named after the attribute, and the value is the ATTRIBUTE's own
    boolean, lowercase — `true` means local-only, `false` means reachable from another
    node. Only `orders.cluster` declares `local = false`; the other four derive the
    measured default. None of the twelve raw event-bus rows carries metadata at all,
    because a call site declares no such attribute."""
    _, metadata = eventbus
    assert {
        (str(r["path"]), str(r["kind"]), str(r["value"]), _typed_member(r["caller"]), r["name"])
        for r in metadata
    } == {
        ("${orders.address}", "local", "true", "OrderConsumers.onConfiguredOrder", None),
        ("com.acme.eb.OrderConsumers", "local", "true", "OrderConsumers.onAnyOrder", None),
        ("orders.cluster", "local", "false", "OrderConsumers.onClusteredOrder", None),
        ("orders.created", "local", "true", "OrderConsumers.onOrderCreated", None),
        ("orders.created", "local", "true", "OrderConsumers.onOrderCreatedEnvelope", None),
        ("orders.headers", "local", "true", "OrderConsumers.onOrderWithHeaders", None),
        ("orders.mutiny.created", "local", "true", "OrderConsumers.onMutinyOrderEnvelope", None),
        ("orders.mutiny.headers", "local", "true", "OrderConsumers.onMutinyHeaderOrder", None),
    }


# --- Quartz: fixtures/orders-quartz (spec 2026-10-28) ----------------------------------
#
# Every shape real Quartz code takes — the builder chains of a `@Configuration`, the Spring
# `QuartzJobBean` form, a jobs table scheduled in a loop (RuoYi), a trigger returned from a
# private method (ruoyi-vue-pro) and a job and trigger built apart and paired in a `Set`
# (dolphinscheduler) — read off one analysis and one render, asserted on the rendered
# "Scheduled work" section.

QUARTZ_FIXTURE = FIXTURES / "orders-quartz"

# A NULL cell: the table says so in words rather than leaving a blank (spec §3).
_NOT_IN_THE_CODE = "not in the code"


@pytest.fixture(scope="module")
def quartz(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, list]:
    """The rendered document and every trace, from one `analyze` and one `render`."""
    workspace_dir = tmp_path_factory.mktemp("quartz")
    compile_fixture(QUARTZ_FIXTURE)
    runner = CliRunner()
    for command in ("analyze", "render"):
        result = runner.invoke(
            cli, ["module", command, str(QUARTZ_FIXTURE), "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        document = (workspace_dir / "render" / "architecture.md").read_text(encoding="utf-8")
        return document, traces_of(workspace)
    finally:
        workspace.close()


def _scheduled_section(document: str) -> str:
    return document.split("## Scheduled work", 1)[1].split("\n## ", 1)[0]


def _handler_cell(cell: str) -> str | None:
    """A handler cell as `Class#method` — the module coordinates and signature of the
    symbol are the fixture build's, not this test's subject — or None for a NULL cell."""
    text = cell.strip().strip("`")
    if text == _NOT_IN_THE_CODE:
        return None
    return text.split("/")[-1].split("(", 1)[0]


def _cell(cell: str) -> str | None:
    text = cell.strip().strip("`")
    return None if text == _NOT_IN_THE_CODE else text


@pytest.mark.xfail(strict=True, reason="Quartz not built — plan 2026-10-29")
def test_quartz_triggers_are_scheduled_work_delivered(quartz: tuple[str, list]):
    """One entry per `newTrigger()` root (ruling 3): the three builder triggers of
    `QuartzConfig` that name a job by key, the one that names it by bean, the jobs-table
    cron (RuoYi), the private-method trigger (ruoyi-vue-pro) and the `Set` pair
    (dolphinscheduler). The `QuartzJobBean` handler is `executeInternal`; the name is
    `group.name` where the code states one and NULL where it does not. A non-cron schedule
    is its builder chain as written (ruling 4), with `Calendar.TUESDAY` as the `3` javac
    compiled it to. `updateJob`'s `trigger.getTriggerBuilder()` chain is a re-schedule of an
    existing trigger, not a new one: no entry."""
    document, traces = quartz
    section = _scheduled_section(document)
    rows = [
        [cell for cell in line.strip().strip("|").split(" | ")]
        for line in section.splitlines()
        if line.startswith(("| `", f"| {_NOT_IN_THE_CODE}"))
    ]
    # Handler, Trigger, Name, Expression, Resolution
    derived = [
        (_handler_cell(r[0]), r[1].strip(), _cell(r[2]), _cell(r[3]), r[4].strip()) for r in rows
    ]
    # None in the expected expression of a `partial` row the brief does not spell is
    # compared as "whatever it is"; every other cell is exact.
    wildcard = object()
    expected = [
        (
            "SweepJob#executeInternal",
            "simple",
            "orders.every30s",
            "simpleSchedule().withIntervalInSeconds(30).repeatForever()",
            "resolved",
        ),
        ("SweepJob#executeInternal", "cron", "orders.nightly", "0 0 2 * * ?", "resolved"),
        ("AuditJob#execute", "cron", None, "${orders.sweep.cron}", "unresolved"),
        (
            "SweepJob#executeInternal",
            "dailyTimeInterval",
            None,
            (
                "dailyTimeIntervalSchedule().onDaysOfTheWeek(3, 5)"
                ".startingDailyAt(TimeOfDay.hourAndMinuteOfDay(9, 0)).withIntervalInHours(1)"
            ),
            "resolved",
        ),
        ("BaseRowJob#execute", "cron", None, None, "partial"),
        ("AuditJob#execute", "cron", None, wildcard, "partial"),
        (None, "cron", None, wildcard, "partial"),
    ]
    assert len(derived) == len(expected), derived
    remaining = list(derived)
    for want in expected:
        match = next(
            (
                got
                for got in remaining
                if all(w is wildcard or w == g for w, g in zip(want, got, strict=True))
            ),
            None,
        )
        assert match is not None, f"no entry for {want}; derived {derived}"
        remaining.remove(match)

    # The configured value rides in the detail block of the placeholder entry.
    assert "0 */5 * * * ?" in section, section
    # The partial entry names the method the schedule is read from.
    assert re.search(r"OrderJobRow[#.]getCron", section), section

    [trace] = [t for t in traces if t.root.handler.split("/")[-1].startswith("BaseRowJob#execute")]
    reached = {
        str(name).split("/")[-1].split("(")[0]
        for step in trace.steps
        for name in (step.callee, step.target)
        if name is not None
    }
    assert {"ConcurrentRowJob#run", "SerialRowJob#run"} <= reached, sorted(reached)
