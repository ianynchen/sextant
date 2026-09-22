"""Google Pub/Sub is delivered when each of the forms a module addresses it in is visible
on the derived rows, in the direction the code states: `PubSubTemplate` (Spring Cloud GCP),
the raw `google-cloud-pubsub` client (`Publisher`/`Subscriber` builders), Micronaut's
`@PubSubListener`/`@PubSubClient`, and the Spring Integration channel adapter
(`PubSubInboundChannelAdapter` + `@ServiceActivator`, the register's `pubsub-channel-adapter`).

Four forms, three fixtures, one file — the question a reader asks is "does Sextant read
Pub/Sub", and the answer is per form, so each form's rows are asserted whole: a form that
derives a row too few or an address wrong fails here, not in a unit test on the catalog.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

MICRONAUT = FIXTURES / "orders-micronaut"
INTEGRATION = FIXTURES / "spring-integration-probe"


def _short(symbol: object) -> str | None:
    """`Class#method` out of a module-prefixed method symbol, or None for a NULL column —
    an inbound row's deriving method lands in `handler`, an outbound row's in `caller`
    (D02 §2), so both are read and neither is the module coordinates the build assigned."""
    if symbol is None:
        return None
    return str(symbol).rsplit("/", 1)[1].partition("(")[0]


def _identities(
    rows: list[dict], catalog_id: str
) -> set[tuple[str, str | None, str | None, str | None, str]]:
    """`(direction, path, handler, caller, resolution)` per row of one catalog."""
    return {
        (
            str(row["direction"]),
            row["path"],
            _short(row["handler"]),
            _short(row["caller"]),
            str(row["resolution"]),
        )
        for row in rows
        if row["catalog_id"] == catalog_id
    }


@pytest.fixture(scope="module")
def spring_rows(analyzed_orders_service: Path) -> list[dict]:
    """Every Pub/Sub row of the session's one `orders-service` analysis (`tests/conftest.py`),
    whole — the Spring Cloud GCP template and the raw client both live in that module."""
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return [
            dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "pubsub"
        ]
    finally:
        workspace.close()


def test_pubsub_template_publishes_and_subscribes_on_the_named_topic(spring_rows):
    """`spring-pubsub.yml`: `pubSubTemplate.publish("order-notifications", event)` is the
    outbound row from its caller; `subscribeAndConvert("order-notifications", …)` is the
    inbound row with the subscribing method as handler. One topic the module both publishes
    to and consumes is two rows, one per side, never one merged `both` row."""
    assert _identities(spring_rows, "spring-pubsub") == {
        ("outbound", "order-notifications", None, "EventProducers#publishNotification", "resolved"),
        ("inbound", "order-notifications", "NotificationsSubscriber#subscribe", None, "resolved"),
    }


def test_the_raw_client_derives_the_built_publisher_and_the_started_subscribers(spring_rows):
    """The `google-cloud-pubsub` client, three catalogs on one fixture class each:

    * `google-pubsub-publisher.yml` — `Publisher.newBuilder(TopicName.of(project,
      "raw-events")).build().publish(message)`: the topic read through `TopicName.of`,
      one resolved outbound row.
    * `google-pubsub-client.yml` — `publish(PubsubMessage)` on ANY `Publisher`, the
      field-held one included: no topic is readable from the call, so each call is an
      unresolved outbound row with `path` NULL. The co-located `publishToNewTopic` call
      matches this catalog too and stands beside its resolved fluent row — two callers,
      two rows, neither merged (an unresolved wire identity never dedups).
    * `google-pubsub-subscriber.yml` — `Subscriber.newBuilder(ProjectSubscriptionName.of(
      project, "raw-notify"), receiver).build().startAsync()`: one inbound row per STARTED
      subscriber, the handler the receiver — the named `MessageReceiver` implementation's
      `receiveMessage`, or the lambda's synthetic method. `withNamedReceiver` builds
      `raw-notify-factory` and starts nothing, so it is no row here (`OI-64`: construction
      is not subscription).
    """
    assert _identities(spring_rows, "google-pubsub-publisher") == {
        ("outbound", "raw-events", None, "RawPubSubPublishers#publishToNewTopic", "resolved"),
    }
    assert _identities(spring_rows, "google-pubsub-client") == {
        ("outbound", None, None, "RawPubSubPublishers#publishToFieldPublisher", "unresolved"),
        ("outbound", None, None, "RawPubSubPublishers#publishToNewTopic", "unresolved"),
    }
    subscribers = _identities(spring_rows, "google-pubsub-subscriber")
    assert {
        (direction, path, caller, resolution)
        for direction, path, _, caller, resolution in subscribers
    } == {
        ("inbound", "raw-notify", None, "resolved"),
        ("inbound", "raw-notify-lambda", None, "resolved"),
    }
    handlers = {path: handler for _, path, handler, _, _ in subscribers}
    assert handlers["raw-notify"] == "RawPubSubReceiver#receiveMessage"
    assert str(handlers["raw-notify-lambda"]).startswith(
        "RawPubSubSubscribers#lambda$startLambdaReceiver$"
    )


@pytest.fixture(scope="module")
def micronaut_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(direction, path, resolution)` for every Pub/Sub row `orders-micronaut` derives."""
    workspace_dir = tmp_path_factory.mktemp("mn-pubsub")
    compile_fixture(MICRONAUT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(MICRONAUT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["direction"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "pubsub"
        }
    finally:
        workspace.close()


def test_micronaut_listener_and_client_derive_both_directions(micronaut_rows):
    """`@PubSubListener` class + `@Subscription("mn-orders-sub")` method consumes;
    `@PubSubClient` interface + `@Topic("mn-orders-topic")` method publishes — the whole
    Pub/Sub surface of the Micronaut fixture, exactly (micronaut-gcp-pubsub 5.8.0)."""
    assert micronaut_rows == {
        ("inbound", "mn-orders-sub", "resolved"),
        ("outbound", "mn-orders-topic", "resolved"),
    }


@pytest.fixture(scope="module")
def integration_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every Pub/Sub row `spring-integration-probe` derives, whole."""
    workspace_dir = tmp_path_factory.mktemp("si-pubsub")
    compile_fixture(INTEGRATION)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(INTEGRATION), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [
            dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "pubsub"
        ]
    finally:
        workspace.close()


def test_the_channel_adapter_joins_its_subscription_to_the_service_activator(integration_rows):
    """`pubsub-channel-adapter`, the register's last Pub/Sub blocker: the subscription is a
    CONSTRUCTOR argument of `PubSubInboundChannelAdapter`, the channel it feeds is set by
    `setOutputChannel`/`setOutputChannelName`, and the `@ServiceActivator` reading that
    channel is the handler. Two adapters feed `pubsubInputChannel` — a literal subscription
    with the channel as a qualified bean, a `@Value` subscription (the row carries its
    `${…}` expression) with the channel by name — and both join `handlePubSubOrder`; the
    `PubSubMessageHandler` bean derives its topic outbound; the adapter whose channel
    parameter matches two beans keeps its row with `handler` NULL rather than guessing.
    The same set `tests/e2e/test_async_delivered.py::test_pubsub_shape_four_rows` pins from
    the channel's side; here it is the feature's."""
    assert _identities(integration_rows, "spring-integration-pubsub") == {
        (
            "inbound",
            "orders-sub",
            "Shape4PubSub#handlePubSubOrder",
            "Shape4PubSub#ordersSubscriptionAdapter",
            "resolved",
        ),
        (
            "inbound",
            "${probe.subscription}",
            "Shape4PubSub#handlePubSubOrder",
            "Shape4PubSub#placeholderSubscriptionAdapter",
            "resolved",
        ),
        ("outbound", "orders-topic", None, "Shape4PubSub#ordersTopicHandler", "resolved"),
        ("inbound", "ambiguous-sub", None, "Shape5Flows#ambiguousChannelAdapter", "resolved"),
    }
