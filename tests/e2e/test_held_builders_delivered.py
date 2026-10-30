"""Every shipped builder is read the same whether its calls are chained or written over
statements of their own (ruling 4, spec 2026-10-30). Each test names the catalog.

`fixtures/orders-heldbuilders` holds each builder in a local and configures it in separate
statements, the result of every configuring call dropped: `b.url(u); b.post(x);
client.newCall(b.build())`. Every such call returns the builder it was called on, which the
catalog states with `returns_receiver: true` beside the `javap` evidence, so the row is the
one the chained form gives. The Quartz trigger is `fixtures/orders-quartz`'s
`HeldTriggerScheduler`, where the rest of the Quartz shapes live.

**Not a document check.** Real bytecode, real pipeline, assertion on derived rows.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

HELD = FIXTURES / "orders-heldbuilders"
QUARTZ = FIXTURES / "orders-quartz"


def _analyzed(fixture: Path, workspace_dir: Path, table: str) -> list[dict]:
    compile_fixture(fixture)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(fixture), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return workspace.query(table)
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def held_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every outbound row of `fixtures/orders-heldbuilders`."""
    rows = _analyzed(HELD, tmp_path_factory.mktemp("held"), "endpoints")
    return [row for row in rows if str(row["direction"]) == "outbound"]


def _of(rows: list[dict], catalog: str, caller_class: str) -> list[tuple]:
    """`(method, peer, path, resolution, has a request shape, has a response shape)` of each
    row `catalog` derived in `caller_class`, sorted."""
    return sorted(
        (
            row["method"],
            row["peer"],
            row["path"],
            row["resolution"],
            row["request_shape"] is not None,
            row["response_shape"] is not None,
        )
        for row in rows
        if row["catalog_id"] == catalog and f"/{caller_class}#" in str(row["caller"])
    )


def test_an_okhttp_request_built_over_statements_is_one_row(held_rows):
    """`builder.url("https://h/orders"); builder.post(body); newCall(builder.build())`: the
    address and the verb reach the row. The body is a `RequestBody`, whose wire type nothing
    reads, so the row is `unresolved` as the chained form's is (`okhttp.yml`)."""
    assert _of(held_rows, "okhttp", "HeldOkHttp") == [
        ("POST", "h", "/orders", "unresolved", False, False)
    ]


def test_a_jdk_request_built_over_statements_is_one_row(held_rows):
    """`builder.uri(URI.create(…)); builder.header(…); builder.POST(…)`, sent as
    `builder.build()`. `header` is not a step, and a call on the builder that is not one
    leaves the request as it was. The body is a `BodyPublisher` (`jdk-httpclient.yml`)."""
    assert _of(held_rows, "jdk-httpclient", "HeldJdkClient") == [
        ("POST", "h", "/orders", "unresolved", False, False)
    ]


def test_an_sqs_request_built_over_statements_names_its_queue(held_rows):
    """`builder.queueUrl(…/orders); builder.messageBody(body); sendMessage(builder.build())`:
    the queue's host and path reach the row, and the `String` body is the request shape."""
    assert _of(held_rows, "aws-sqs-sdk", "HeldSqsSender") == [
        (None, "sqs.us-east-1.amazonaws.com", "/123456789012/orders", "resolved", True, False)
    ]


def test_a_message_built_over_statements_names_its_topic(held_rows):
    """`builder = MessageBuilder.withPayload(order); builder.setHeader(TOPIC, "orders");
    kafkaTemplate.send(builder.build())`: the topic header reaches the row, and the payload
    is the request shape."""
    assert _of(held_rows, "spring-kafka-message", "HeldKafkaMessage") == [
        (None, None, "orders", "resolved", True, False)
    ]


def test_a_sink_spec_configured_over_statements_names_its_topic(held_rows):
    """`sink = Kafka.outboundChannelAdapter(t); sink.topic("orders"); flow.handle(sink)`:
    one Spring Integration spec, its topic set on the held spec."""
    assert _of(held_rows, "spring-integration-kafka", "HeldKafkaFlow") == [
        (None, None, "orders", "resolved", False, False)
    ]


def test_a_webclient_request_and_response_held_are_one_row_each(held_rows):
    """The request spec and the response spec are each held; `onStatus` is a statement of
    its own before `bodyToMono`. `onStatus` returns the response spec it was called on, so it
    configures that spec and the walk does not fork there: ONE row per request, carrying the
    response shape, where a fork gave a second row with none."""
    assert _of(held_rows, "spring-webclient", "HeldWebClient") == [
        ("GET", None, "/x", "resolved", False, True),
        ("POST", None, "/x", "resolved", True, True),
    ]


def test_a_restclient_request_held_is_one_row(held_rows):
    """`request.uri("/y"); request.body(order); request.retrieve().body(Order.class)`, the
    request spec held."""
    assert _of(held_rows, "spring-restclient", "HeldRestClient") == [
        ("POST", None, "/y", "resolved", True, True)
    ]


@pytest.fixture(scope="module")
def quartz_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every `scheduled_work` row of `fixtures/orders-quartz`."""
    return _analyzed(QUARTZ, tmp_path_factory.mktemp("held-quartz"), "scheduled_work")


def test_a_trigger_built_over_statements_keeps_its_name_and_cron(quartz_rows):
    """`HeldTriggerScheduler`: `triggers.withIdentity("x")`, a held cron builder given a
    misfire policy in a statement of its own, `triggers.withSchedule(cron)`, then
    `scheduleJob(job, triggers.build())`, the job itself built from a held `JobBuilder`. The
    entry is named `DEFAULT.x` and carries its cron. Read as forks, it was an unnamed
    `simpleSchedule()` at `resolved`: Quartz's default for a trigger given no schedule, which
    is not this trigger's."""
    held = [
        (
            str(row["handler"]).split("/")[-1].split("(")[0],
            row["trigger"],
            row["expression"],
            row["resolution"],
        )
        for row in quartz_rows
        if row["name"] == "DEFAULT.x"
    ]
    assert held == [("SweepJob#executeInternal", "cron", "0 0 * * * ?", "resolved")]
    assert not [row for row in quartz_rows if row["expression"] == "simpleSchedule()"]


def test_an_sqs_request_started_in_a_helper_is_sent_by_its_caller(held_rows):
    """`SqsRequestHelper`: `base()` returns the builder with its queue set, and `send` adds
    the body, builds and sends. No root is in `send` and no terminal is in `base()`, so the
    walk goes back from `build()` across the helper's return (ruling 5): one row, the
    caller's, with the helper's queue and the caller's `String` body."""
    assert _of(held_rows, "aws-sqs-sdk", "SqsRequestHelper") == [
        (
            None,
            "sqs.us-east-1.amazonaws.com",
            "/123456789012/helper-orders",
            "resolved",
            True,
            False,
        )
    ]


def test_each_caller_of_an_okhttp_request_helper_names_its_own_service(held_rows):
    """`OkHttpRequestHelper`: `req(svc)` returns `new Request.Builder().url("http://" + svc +
    "/x")`, and `callA` and `callB` build and send it with `"svc-a"` and `"svc-b"`. Each row
    reads the address on the path its own caller took into the helper (Review Focus 2)."""
    rows = sorted(
        (str(row["caller"]).split("#")[1].split("(")[0], row["method"], row["peer"], row["path"])
        for row in held_rows
        if row["catalog_id"] == "okhttp" and "/OkHttpRequestHelper#" in str(row["caller"])
    )
    assert rows == [("callA", "GET", "svc-a", "/x"), ("callB", "GET", "svc-b", "/x")]
    assert {
        row["resolution"]
        for row in held_rows
        if row["catalog_id"] == "okhttp" and "/OkHttpRequestHelper#" in str(row["caller"])
    } == {"resolved"}
