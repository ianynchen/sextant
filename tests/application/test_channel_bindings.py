"""The channel edge as data (spec 2026-09-21 §3b): `channel_bindings`, the `read_by` rows
`config_join.run` writes from the channel index it already builds, the `fed_by ⋈ read_by`
join pass (`resolve/channel_bindings.py`), and `config_join.gaps` asking only about a
channel nothing fed.

Nothing writes `fed_by` yet — the fluent engine does, one task on — so every feeder here
is a hand-inserted table row, exactly the row that engine will write. The invented
vocabulary is `test_config_join.py`'s, for the reason that file states: a test reaching
for the real framework's spellings would not prove the engine reads catalog data.
"""

from pathlib import Path

from test_config_join import (
    _annotated,
    _channel_address,
    _channel_catalog,
    _channel_destination,
    _handler,
    _handler_symbol,
    _rows,
    _workspace,
)

from sextant.application.resolve.channel_bindings import mint_channel_rows
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import config_join
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ADAPTERS = "com/acme/streams/Adapters#"
FEEDER = f"{ADAPTERS}inbound(sig_inbound)."
FEEDER_CATALOG = "invented-adapters"


def _fed_by(
    channel: str,
    *,
    direction: str = "inbound",
    destination: str | None = "orders.queue",
    resolution: str = "resolved",
    symbol: str = FEEDER,
) -> dict[str, object]:
    """The row the fluent engine writes when a chain captured a channel link: the
    constructing method, the wire it read, and the direction the registration means."""
    return {
        "channel": channel,
        "role": "fed_by",
        "symbol": symbol,
        "protocol": "amqp",
        "direction": direction,
        "destination": destination,
        "catalog_id": FEEDER_CATALOG,
        "resolution": resolution,
    }


def _read_by(channel: str, handler: str, *, direction: str = "inbound") -> dict[str, object]:
    return {
        "channel": channel,
        "role": "read_by",
        "symbol": handler,
        "protocol": None,
        "direction": direction,
        "destination": None,
        "catalog_id": "invented-bindings",
        "resolution": "resolved",
    }


def _bound(tmp_path: Path, *rows: dict[str, object]) -> DuckDbWorkspace:
    """A workspace holding exactly the channel edges a test names and an empty
    `endpoints` table — the state the pass reads after the engine loop."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.derive("endpoints_reset")
    workspace.derive("channel_bindings_reset")
    if rows:
        workspace.derive("channel_bindings_insert", rows=list(rows))
    return workspace


def _minted(workspace: DuckDbWorkspace) -> list[dict[str, object]]:
    mint_channel_rows(workspace, [])
    return _rows(workspace)


def _bindings(workspace: DuckDbWorkspace, role: str) -> list[dict[str, object]]:
    return [dict(row) for row in workspace.query("channel_bindings") if row["role"] == role]


# --- the join pass ---------------------------------------------------------


def test_a_fed_channel_with_one_reader_mints_one_inbound_row_naming_both_ends(
    tmp_path: Path,
):
    """The whole edge in one row: the wire is the feeder's (`protocol`, `path` from the
    captured destination, `caller` the constructing method), the handler is the reader,
    and the shapes stay NULL — a channel handler's signature is the framework's own
    convention, not a contract anybody read (§3c)."""
    workspace = _bound(tmp_path, _fed_by("orders"), _read_by("orders", _handler_symbol("handle")))
    [row] = _minted(workspace)
    workspace.close()

    assert row == {
        "protocol": "amqp",
        "direction": "inbound",
        "method": None,
        "path": "orders.queue",
        "handler": _handler_symbol("handle"),
        "handler_signature": None,
        "caller": FEEDER,
        "peer": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "catalog_id": FEEDER_CATALOG,
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
        # The format ladder's two columns, answered by a later pass, NULL as minted.
        "format": None,
        "format_resolution": None,
    }


def test_two_readers_of_one_fed_channel_mint_two_rows(tmp_path: Path):
    """Two handlers subscribed to one channel are two consumers of one wire. The rows
    tie on every identity column and differ on `handler` alone — one batch, so the
    insert's guard (which reads the table as it stood before) refuses neither."""
    workspace = _bound(
        tmp_path,
        _fed_by("orders"),
        _read_by("orders", _handler_symbol("audit")),
        _read_by("orders", _handler_symbol("handle")),
    )
    rows = _minted(workspace)
    workspace.close()

    assert [(row["path"], row["handler"], row["caller"]) for row in rows] == [
        ("orders.queue", _handler_symbol("audit"), FEEDER),
        ("orders.queue", _handler_symbol("handle"), FEEDER),
    ]


def test_a_feeder_nobody_reads_still_mints_its_adapter_row_with_no_handler(tmp_path: Path):
    """The adapter exists whether or not anything subscribes: a registration that reads a
    queue onto a channel nobody consumes is still a boundary the module holds open. The
    row carries the wire and the constructing method and an honest NULL where the
    consumer would be."""
    workspace = _bound(tmp_path, _fed_by("orders"), _read_by("other", _handler_symbol("handle")))
    [row] = _minted(workspace)
    workspace.close()

    assert (row["path"], row["handler"], row["caller"]) == ("orders.queue", None, FEEDER)


def test_a_feeder_whose_destination_was_unread_mints_an_unresolved_row(tmp_path: Path):
    """The feeder's own resolution travels onto the row: a captured address nobody could
    read is a real "this adapter feeds this channel from somewhere" fact with `path`
    NULL, which the insert admits only because the row says `unresolved`."""
    workspace = _bound(
        tmp_path,
        _fed_by("orders", destination=None, resolution="unresolved"),
        _read_by("orders", _handler_symbol("handle")),
    )
    [row] = _minted(workspace)
    workspace.close()

    assert (row["path"], row["resolution"], row["handler"]) == (
        None,
        "unresolved",
        _handler_symbol("handle"),
    )


def test_an_outbound_feeder_mints_nothing(tmp_path: Path):
    """A `fed_by` row with `direction: outbound` is an outbound handler bean — the chain
    that found it derived its outbound row already. The row exists so `gaps` stops
    asking, and the pass must not turn it into an inbound row nobody observed."""
    workspace = _bound(
        tmp_path,
        _fed_by("orders", direction="outbound"),
        _read_by("orders", _handler_symbol("handle")),
    )
    rows = _minted(workspace)
    workspace.close()

    assert rows == []


def test_a_reader_whose_name_never_resolved_joins_nothing(tmp_path: Path):
    """The near-miss on the reader's side: a `read_by` whose channel name is still a
    placeholder configuration never answered is `unresolved`, and joins nothing even
    where its raw spelling happens to equal a feeder's channel — the join is over names
    that were READ, never over spellings."""
    workspace = _bound(
        tmp_path,
        _fed_by("${acme.orders-channel}"),
        {
            **_read_by("${acme.orders-channel}", _handler_symbol("handle")),
            "resolution": "unresolved",
        },
    )
    [row] = _minted(workspace)
    workspace.close()

    assert row["handler"] is None


def test_a_reader_on_the_outbound_side_of_a_channel_is_not_a_consumer(tmp_path: Path):
    """A handler that SENDS to the fed channel (`outputChannel`) is not fed by it: only
    the inbound readers join. The feeder keeps its adapter row, handler NULL."""
    workspace = _bound(
        tmp_path,
        _fed_by("orders"),
        _read_by("orders", _handler_symbol("handle"), direction="outbound"),
    )
    [row] = _minted(workspace)
    workspace.close()

    assert row["handler"] is None


def test_the_pass_never_displaces_a_row_an_engine_already_minted(tmp_path: Path):
    """Insert-if-absent, the discipline every call-side engine keeps: a wire identity a
    catalog already recorded stays that catalog's row, so the pass's own `catalog_id`
    never overwrites provenance."""
    workspace = _bound(tmp_path, _fed_by("orders"), _read_by("orders", _handler_symbol("handle")))
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": "amqp",
                "direction": "inbound",
                "method": None,
                "path": "orders.queue",
                "handler": _handler_symbol("handle"),
                "caller": FEEDER,
                "peer": None,
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "earlier-catalog",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
            }
        ],
    )
    [row] = _minted(workspace)
    workspace.close()

    assert row["catalog_id"] == "earlier-catalog"


# --- `read_by` from `config_join.run` ---------------------------------------


def test_run_writes_one_read_by_row_per_indexed_channel(tmp_path: Path):
    """Every name the channel index found becomes a `read_by` edge: the handler, the
    direction the annotation's attribute means, and nothing about the wire — a reader
    knows the channel's name and not what feeds it."""
    workspace = _workspace(
        tmp_path,
        [
            _handler("handle"),
            _handler("emit"),
            _annotated({"inputChannel": "ordersIn", "outputChannel": "auditOut"}),
            _annotated({"inputChannel": "ordersIn"}, target="emit"),
        ],
    )
    workspace.derive("channel_bindings_reset")
    config_join.run(workspace, _channel_catalog())
    rows = _bindings(workspace, "read_by")
    feeders = _bindings(workspace, "fed_by")
    workspace.close()

    assert rows == [
        _read_by("auditOut", _handler_symbol("handle"), direction="outbound"),
        _read_by("ordersIn", _handler_symbol("emit")),
        _read_by("ordersIn", _handler_symbol("handle")),
    ]
    assert feeders == []


def test_a_channel_spelled_as_a_placeholder_is_written_under_the_name_configuration_gives(
    tmp_path: Path,
):
    """The fixture's `@ServiceActivator(inputChannel = "${probe.audit-channel}")` case
    (§0c B5): the name the framework subscribes the handler to is the configured VALUE,
    so the edge is written under it — resolved through `_agreed`, so one value every
    environment gives — and a feeder of that channel joins it."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "${acme.audit-channel}"})],
        [("acme.audit-channel", "default", "audit"), ("acme.audit-channel", "prod", "audit")],
    )
    workspace.derive("channel_bindings_reset")
    config_join.run(workspace, _channel_catalog())
    [reader] = _bindings(workspace, "read_by")
    workspace.derive("channel_bindings_insert", rows=[_fed_by("audit")])
    [row] = _minted(workspace)
    workspace.close()

    assert (reader["channel"], reader["resolution"]) == ("audit", "resolved")
    assert (row["path"], row["handler"]) == ("orders.queue", _handler_symbol("handle"))


def test_a_placeholder_configuration_never_answered_is_written_verbatim_and_unresolved(
    tmp_path: Path,
):
    """The near-miss: no environment gives the key one value, so the name is kept exactly
    as written and marked `unresolved` — it can never join, and a feeder of the channel
    the placeholder happens to stand for still mints only its own adapter row."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "${acme.audit-channel}"})],
        [("acme.audit-channel", "default", "audit"), ("acme.audit-channel", "prod", "audit-prod")],
    )
    workspace.derive("channel_bindings_reset")
    config_join.run(workspace, _channel_catalog())
    [reader] = _bindings(workspace, "read_by")
    workspace.derive("channel_bindings_insert", rows=[_fed_by("audit")])
    [row] = _minted(workspace)
    workspace.close()

    assert (reader["channel"], reader["resolution"]) == ("${acme.audit-channel}", "unresolved")
    assert row["handler"] is None


def test_a_name_that_merely_contains_the_delimiters_is_not_a_placeholder(tmp_path: Path):
    """An opening delimiter with no closing one is text, exactly as the configuration
    resolver reads it: the name is written as it stands and is `resolved` — nothing was
    asked of configuration, so nothing went unanswered."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "orders${in"})],
    )
    workspace.derive("channel_bindings_reset")
    config_join.run(workspace, _channel_catalog())
    [reader] = _bindings(workspace, "read_by")
    workspace.close()

    assert (reader["channel"], reader["resolution"]) == ("orders${in", "resolved")


def test_channel_index_is_the_public_name_of_the_engines_channel_walk(tmp_path: Path):
    """The fluent engine reads the channel names a module's handlers subscribe to
    through this name (a channel reference resolves by a name the index knows, §3a), so
    it is a public function with the walk's own attributes."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn", "outputChannel": "out"})],
    )
    channels = config_join.channel_index(workspace, _channel_catalog())
    workspace.close()

    assert [(c.name, c.handler, c.direction) for c in channels] == [
        ("ordersIn", _handler_symbol("handle"), "inbound"),
        ("out", _handler_symbol("handle"), "outbound"),
    ]


# --- `gaps` asks only about unfed channels ---------------------------------


def _questions(workspace: DuckDbWorkspace) -> list[str]:
    address = _channel_address()
    del address["key"]
    return [str(q["path"]) for q in config_join.gaps(workspace, _channel_catalog(address))]


def test_a_channel_nothing_fed_keeps_its_question(tmp_path: Path):
    """The control: with no `fed_by` row the question is filed exactly as before this
    table existed — the reader's own `read_by` row is not a feeder."""
    workspace = _workspace(tmp_path, [_handler("handle"), _annotated({"inputChannel": "ordersIn"})])
    workspace.derive("channel_bindings_reset")
    config_join.run(workspace, _channel_catalog())
    questions = _questions(workspace)
    workspace.close()

    assert questions == ["ordersIn"]


def test_a_fed_channel_files_no_question(tmp_path: Path):
    """The destination is known — the feeder read it and the pass minted the row — so
    asking a human for it would be asking what the document already states."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn", "outputChannel": "other"})],
    )
    workspace.derive("channel_bindings_reset")
    workspace.derive("channel_bindings_insert", rows=[_fed_by("ordersIn")])
    questions = _questions(workspace)
    workspace.close()

    assert questions == ["other"]


def test_an_outbound_feeder_suppresses_the_question_too(tmp_path: Path):
    """An outbound handler bean's `fed_by` row (`direction: outbound`) names the channel
    whatever its direction: the chain derived the outbound row, so the channel's
    destination is answered and the question would be a duplicate."""
    workspace = _workspace(tmp_path, [_handler("handle"), _annotated({"inputChannel": "ordersIn"})])
    workspace.derive("channel_bindings_reset")
    workspace.derive("channel_bindings_insert", rows=[_fed_by("ordersIn", direction="outbound")])
    questions = _questions(workspace)
    workspace.close()

    assert questions == []


def test_a_fed_placeholder_channel_files_no_question_and_an_unresolved_one_keeps_it(
    tmp_path: Path,
):
    """The feeder names the configured VALUE; the question is keyed on what the handler
    wrote. Resolved through the same rule the `read_by` write uses, so a fed channel the
    handler spelled as a placeholder is recognised — and one configuration never
    answered is still asked about, under its raw spelling, as it always was."""
    facts = [_handler("handle"), _annotated({"inputChannel": "${acme.audit-channel}"})]
    fed = _workspace(
        tmp_path / "fed",
        facts,
        [("acme.audit-channel", "default", "audit"), ("acme.audit-channel", "prod", "audit")],
    )
    fed.derive("channel_bindings_reset")
    fed.derive("channel_bindings_insert", rows=[_fed_by("audit")])
    fed_questions = _questions(fed)
    fed.close()

    unfed = _workspace(tmp_path / "unfed", facts)
    unfed.derive("channel_bindings_reset")
    unfed.derive("channel_bindings_insert", rows=[_fed_by("audit")])
    unfed_questions = _questions(unfed)
    unfed.close()

    assert fed_questions == []
    assert unfed_questions == ["${acme.audit-channel}"]


def test_a_channel_whose_key_configuration_answered_still_files_no_question(tmp_path: Path):
    """Unchanged by the table: a catalog with a key template whose configuration answered
    derived its row in `run`, and `gaps` skips it as it always did."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        _channel_destination("ordersIn", "orders.queue"),
    )
    workspace.derive("channel_bindings_reset")
    questions = config_join.gaps(workspace, _channel_catalog())
    workspace.close()

    assert questions == []


# --- wiring: `derive_endpoints` resets the table and runs the pass ----------


def test_derive_endpoints_replaces_the_table_whole_and_leaves_the_readers_in_it(
    tmp_path: Path,
):
    """The reset is the pipeline's, beside `route_requirements_reset`: a row left by an
    earlier resolve is gone, and the readers this resolve's engines wrote are there for
    the pass and for `gaps`, which runs from the `service_identity` seam afterwards."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        coordinates=("com.acme:acme-bindings",),
    )
    workspace.derive("channel_bindings_reset")
    workspace.derive("channel_bindings_insert", rows=[_fed_by("stale")])
    skipped = derive_endpoints(workspace, [_channel_catalog()], capabilities={"resolved_config"})
    rows = [dict(row) for row in workspace.query("channel_bindings")]
    endpoints = _rows(workspace)
    workspace.close()

    assert skipped == []
    assert rows == [_read_by("ordersIn", _handler_symbol("handle"))]
    # Nothing fed the channel, so the pass minted nothing: the table is inert on every
    # module until an engine writes `fed_by`.
    assert endpoints == []
