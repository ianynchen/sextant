"""Kafka is delivered for Quarkus when a Quarkus module's SmallRye channels, declared the way
an application declares them, are visible — wired to a broker the way Quarkus wires them
(spec 2026-10-24 §1 rulings 1-2, §3e).

Its own file, beside the two REST files that read the same fixture module, `orders-quarkus` —
the `test_messaging_micronaut_delivered.py` precedent: a reader asking "does Sextant read
Quarkus messaging" wants one answer, apart from the REST one.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

QUARKUS = FIXTURES / "orders-quarkus"


@pytest.fixture(scope="module")
def quarkus_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    """Every non-HTTP row the Quarkus fixture derives, and every open question it files,
    analysed once."""
    workspace_dir = tmp_path_factory.mktemp("quarkus-messaging")
    compile_fixture(QUARKUS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(QUARKUS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            "endpoints": [
                dict(row)
                for row in workspace.query("endpoints")
                if str(row["protocol"]) not in ("http", "sse")
            ],
            "open_questions": [dict(row) for row in workspace.query("open_questions")],
        }
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def channel_rows(quarkus_tables) -> set[tuple[str, str, str, str]]:
    """`(protocol, direction, path, resolution)` for every row the SmallRye catalog mints."""
    return {
        (str(r["protocol"]), str(r["direction"]), str(r["path"]), str(r["resolution"]))
        for r in quarkus_tables["endpoints"]
        if r["catalog_id"] == "smallrye-reactive-messaging"
    }


@pytest.mark.pins("messaging.an-ORPHAN-channel-takes-the-sole-connector")
def test_unconfigured_channels_take_the_sole_connector(channel_rows):
    """`QuoteProcessor`'s `@Incoming("requests") @Outgoing("quotes")` and `QuoteRequester`'s
    `Emitter` on `@Channel("quote-requests")` configure no connector. Each is an ORPHAN, and
    `quarkus-messaging-kafka` is the module's one connector, so Quarkus attaches Kafka to
    every one of them (CP-50 rows 1, 7) at the channel name, Kafka's `topic` default
    (CP-51 rows 4-5). The `Emitter`'s injected type makes its channel outgoing (CP-49 rows
    21, 26)."""
    expected = {
        ("kafka", "inbound", "requests", "resolved"),
        ("kafka", "outbound", "quotes", "resolved"),
        ("kafka", "outbound", "quote-requests", "resolved"),
    }
    missing = expected - channel_rows
    assert missing == set(), (
        f"Quarkus Kafka: missing {sorted(missing)}. Derived: {sorted(channel_rows)}"
    )


def test_a_configured_topic_is_the_channels_destination(channel_rows):
    """`mp.messaging.incoming.audit.topic=orders.audit`: the channel is still an orphan (it
    names no connector) and still takes Kafka, but its destination is the configured topic,
    not the channel name."""
    assert ("kafka", "inbound", "orders.audit", "resolved") in channel_rows, sorted(channel_rows)
    assert not [row for row in channel_rows if row[2] == "audit"], sorted(channel_rows)


@pytest.mark.pins("messaging.an-IN-MEMORY-channel-is-no-boundary")
def test_an_in_memory_pair_is_no_boundary(quarkus_tables):
    """`TickRelay` produces and consumes `ticks` in this module: not an orphan, no
    connector attached (CP-50 rows 1, 11), no wire. No row of any protocol, and no question
    either — it is a hand-off inside the process, not an unread boundary."""
    assert not [r for r in quarkus_tables["endpoints"] if r["path"] == "ticks"]
    assert not [r for r in quarkus_tables["open_questions"] if "ticks" in str(r["path"])]


def test_every_channel_is_read_and_none_is_a_question(channel_rows, quarkus_tables):
    """The four rows above are the whole SmallRye output: one connector, every orphan
    attached, so nothing is left for a `binder_protocol` or `channel_destination`
    question."""
    assert channel_rows == {
        ("kafka", "inbound", "requests", "resolved"),
        ("kafka", "outbound", "quotes", "resolved"),
        ("kafka", "outbound", "quote-requests", "resolved"),
        ("kafka", "inbound", "orders.audit", "resolved"),
    }
    assert not [
        q
        for q in quarkus_tables["open_questions"]
        if q["question"] in ("binder_protocol", "channel_destination")
    ], quarkus_tables["open_questions"]
