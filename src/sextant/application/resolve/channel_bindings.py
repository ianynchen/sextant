"""The `fed_by ⋈ read_by` join (spec 2026-09-21 §3b): the pass that turns the channel
edge into endpoint rows.

A named in-process channel has two ends that two different engines read. An adapter or
a flow FEEDS it — a chain captured the channel's name and the destination behind it, and
wrote a `fed_by` row with the wire (`protocol`, `destination`) and the constructing
method. A handler READS it — its annotation names the channel, and `config_join` wrote a
`read_by` row with the handler and nothing about the wire, because a reader knows
nothing about it. Neither engine can mint the endpoint row alone: the feeder has the
wire and no handler, the reader has the handler and no wire. This pass joins them on the
channel's name, once per resolve, after every engine has written its end.

One row per `(feeder, reader)` pair, inbound, the wire the feeder's and the handler the
reader's, `caller` the constructing method — §3c's inbound row. A feeder nobody reads
still mints its row with `handler` NULL: the adapter exists and holds a wire open whether
or not anything subscribes, and the chain that found it deliberately wrote the edge
INSTEAD of a row so a linked adapter is never counted twice. An OUTBOUND feeder mints
nothing: it is an outbound handler bean whose chain derived the outbound row already,
and its edge exists so `config_join.gaps` stops asking about the channel.

Only a reader whose channel NAME was read joins: a `read_by` still spelled as a
placeholder configuration never answered is `unresolved` and matches nothing, even where
its raw spelling equals a feeder's channel — the join is over names, never spellings.

Runs from `derive_endpoints` after the engine loop and before the borrowed-rows drop:
the rows it mints are rows every later pass reads, so the set must be complete before
`apply_protocol_hints`, and a sibling module's channel rows are this module's to drop
like any other. Insert-if-absent through `call_endpoints`, the discipline every
call-side engine keeps.

Cost per resolve (GUIDELINES §8.7): one read of `channel_bindings`, one
`call_endpoints` insert — none of it per catalog.
"""

from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace

_FED_BY = "fed_by"
_READ_BY = "read_by"


def mint_channel_rows(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Mints one `endpoints` row per inbound feeder of a channel joined to each of the
    channel's resolved inbound readers, or one row with `handler` NULL for a feeder
    nobody reads. `catalogs` is the pass signature every pipeline pass shares and is not
    read: every value a row needs travels on the edge itself (`catalog_id` is the
    feeder's — the catalog whose chain read the wire)."""
    feeders: list[dict[str, Any]] = []
    readers: dict[str, list[str]] = {}
    for row in workspace.query("channel_bindings"):
        if row["direction"] != "inbound":
            continue
        if row["role"] == _FED_BY:
            feeders.append(dict(row))
        elif row["role"] == _READ_BY and row["resolution"] == "resolved":
            readers.setdefault(str(row["channel"]), []).append(str(row["symbol"]))
    rows = [
        _row(feeder, handler)
        for feeder in feeders
        for handler in readers.get(str(feeder["channel"]), [None])
    ]
    workspace.derive("call_endpoints", rows=rows)


def _row(feeder: dict[str, Any], handler: str | None) -> dict[str, Any]:
    """§3c's inbound row: the wire from the feeder, the handler from the reader, `caller`
    the constructing method, shapes NULL — a channel handler's signature is the
    framework's own convention, and no probe has measured one."""
    return {
        "protocol": feeder["protocol"],
        "direction": "inbound",
        "method": None,
        "path": feeder["destination"],
        "handler": handler,
        "caller": feeder["symbol"],
        "peer": None,
        "handler_signature": None,
        "resolution": feeder["resolution"],
        "evidence": "compiler",
        "catalog_id": feeder["catalog_id"],
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }
