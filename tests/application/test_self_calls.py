"""A module that serves a gRPC service gets no outbound row for it (spec 2026-10-25
§1 rulings 1 and 3, §3c).

Invented services and symbols, as `test_self_exchange.py` does: one behaviour per test,
with the shipped answer pinned against real bytecode in the pipeline and fixture tests.
"""

from pathlib import Path

import pytest

from sextant.application.resolve.self_calls import (
    _is_this_module,
    record_self_calls,
    served_services,
)
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/greeter 1.0.0 "
HANDLER = "com/acme/greeter/GreeterImpl#sayHello(sig_00000000)."
CALLER = "com/acme/greeter/GreeterClient#greet(sig_11111111)."


def _workspace(
    tmp_path: Path,
    *rows: tuple[str, str, str | None, str | None, str | None],
) -> DuckDbWorkspace:
    """A workspace holding exactly the endpoint rows a test names, as
    `(protocol, direction, path, symbol, peer)` — the symbol landing in `handler` for an
    inbound row and in `caller` for an outbound one, which is where the engines put it."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    for protocol, direction, path, symbol, peer in rows:
        stored = None if symbol is None else _MODULE + symbol
        workspace._connection.execute(
            "INSERT INTO endpoints (row_id, protocol, direction, method, path, handler, caller, peer) "
            "VALUES ((SELECT coalesce(max(row_id), 0) + 1 FROM endpoints), ?, ?, NULL, ?, ?, ?, ?)",
            [
                protocol,
                direction,
                path,
                stored if direction == "inbound" else None,
                stored if direction == "outbound" else None,
                peer,
            ],
        )
    return workspace


def _remaining(workspace: DuckDbWorkspace) -> list[tuple[str, str, str | None]]:
    return sorted(
        (str(r["protocol"]), str(r["direction"]), r["path"])  # type: ignore[misc]
        for r in workspace.query("endpoints")
    )


@pytest.mark.pins("grpc.a-SELF-call-is-not-an-outbound-row")
def test_a_client_of_a_service_this_module_handles_is_dropped(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, None),
    )
    record_self_calls(workspace)
    assert _remaining(workspace) == [("grpc", "inbound", "helloworld.Greeter/SayHello")]


def test_an_entry_bound_to_a_dropped_row_goes_with_it(tmp_path: Path) -> None:
    """Ruling 7 (follow the object). The client's call carried a header, written as the
    row was minted and bound to its `row_id`. The row is a self-call and is dropped; a
    header stated about an outbound call that is not there describes nothing, so the entry
    goes too. The served row's own entry stays."""
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, None),
    )
    workspace.derive("endpoint_metadata_reset")
    workspace.derive(
        "endpoint_metadata_insert",
        rows=[
            {
                "protocol": "grpc",
                "direction": direction,
                "method": None,
                "path": path,
                "caller": _MODULE + symbol,
                "kind": "header",
                "name": "x-tenant",
                "value": "acme",
                "resolution": "resolved",
                "evidence": "compiler",
                "requirement": None,
            }
            for direction, path, symbol in (
                ("inbound", "helloworld.Greeter/SayHello", HANDLER),
                ("outbound", "helloworld.Greeter", CALLER),
            )
        ],
    )
    record_self_calls(workspace)
    entries = [str(r["direction"]) for r in workspace.query("endpoint_metadata")]
    workspace.close()

    assert entries == ["inbound"]


@pytest.mark.pins("grpc.a-DESCRIPTOR-only-inbound-row-serves-nothing")
def test_a_descriptor_only_inbound_row_serves_nothing(tmp_path: Path) -> None:
    """A `.proto` row has no handler: a client module compiles the `.proto` too, so it
    says nothing about what this module serves."""
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", None, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, None),
    )
    record_self_calls(workspace)
    assert _remaining(workspace) == [
        ("grpc", "inbound", "helloworld.Greeter/SayHello"),
        ("grpc", "outbound", "helloworld.Greeter"),
    ]
    assert served_services(workspace) == {}


@pytest.mark.pins("grpc.a-call-naming-ANOTHER-host-stays-outbound")
def test_a_client_naming_another_host_stays_outbound(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, "pricing.internal:9000"),
    )
    record_self_calls(workspace)
    assert _remaining(workspace) == [
        ("grpc", "inbound", "helloworld.Greeter/SayHello"),
        ("grpc", "outbound", "helloworld.Greeter"),
    ]


def test_a_loopback_peer_is_this_module(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, "localhost:9000"),
    )
    record_self_calls(workspace)
    assert _remaining(workspace) == [("grpc", "inbound", "helloworld.Greeter/SayHello")]


def test_another_protocol_is_untouched(tmp_path: Path) -> None:
    """W27 files a question for the other protocols; this rule is gRPC's only (OI-198)."""
    workspace = _workspace(
        tmp_path,
        ("http", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("http", "outbound", "helloworld.Greeter", CALLER, None),
    )
    record_self_calls(workspace)
    assert len(_remaining(workspace)) == 2


@pytest.mark.pins("grpc.a-SERVED-identity-matches-exactly")
def test_only_the_exact_served_identity_is_dropped(tmp_path: Path) -> None:
    """A name that merely starts with a served identity is another service."""
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, None),
        ("grpc", "outbound", "helloworld.GreeterAdmin", CALLER, None),
        ("grpc", "outbound", "helloworld.Greeter.v2", CALLER, None),
    )
    record_self_calls(workspace)
    assert _remaining(workspace) == [
        ("grpc", "inbound", "helloworld.Greeter/SayHello"),
        ("grpc", "outbound", "helloworld.Greeter.v2"),
        ("grpc", "outbound", "helloworld.GreeterAdmin"),
    ]


def test_a_service_this_module_does_not_handle_stays_outbound(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "pricing.Pricer", CALLER, None),
    )
    record_self_calls(workspace)
    assert ("grpc", "outbound", "pricing.Pricer") in _remaining(workspace)


def test_one_remote_row_survives_beside_a_dropped_row_of_the_same_service(
    tmp_path: Path,
) -> None:
    """Two outbound rows of one identity are told apart by their peer, so dropping the
    loopback one must not take the remote one with it."""
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, "localhost:9000"),
        ("grpc", "outbound", "helloworld.Greeter", CALLER, "pricing.internal:9000"),
    )
    record_self_calls(workspace)
    assert [r["peer"] for r in workspace.query("endpoints") if r["direction"] == "outbound"] == [
        "pricing.internal:9000"
    ]


def test_served_services_maps_an_identity_to_its_wire_paths(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        ("grpc", "inbound", "helloworld.Greeter/SayHello", HANDLER, None),
        ("grpc", "inbound", "helloworld.Greeter/SayBye", HANDLER, None),
        ("grpc", "inbound", "helloworld.Other/Ping", None, None),
        ("http", "inbound", "/hello", HANDLER, None),
    )
    assert served_services(workspace) == {
        "helloworld.Greeter": {"helloworld.Greeter/SayHello", "helloworld.Greeter/SayBye"}
    }


@pytest.mark.parametrize(
    "peer",
    [
        None,
        "localhost",
        "localhost:9000",
        "LOCALHOST:9000",
        "127.0.0.1:9000",
        "::1",
        "[::1]",
        "[::1]:9000",
        "0.0.0.0:9000",
        "http://localhost:9000",
    ],
)
def test_these_peers_are_this_module(peer: str | None) -> None:
    assert _is_this_module(peer)


@pytest.mark.parametrize(
    "peer",
    ["pricing.internal", "pricing.internal:9000", "https://pricing.internal:443", "10.0.0.5:9000"],
)
def test_these_peers_are_another_module(peer: str) -> None:
    assert not _is_this_module(peer)
