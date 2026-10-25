"""A call to a gRPC service this module itself serves is not an outbound row (spec
2026-10-25 §3c, rulings 1 and 3).

The user's ruling: *"A service that calls its inbound endpoints is not an outbound call.
It's just a call hop that's traceable."* So a module that handles `helloworld.Greeter` gets
no outbound row for a client of `helloworld.Greeter`, whichever form serves it and whichever
form calls it.

## What "serves" means here

An inbound `grpc` row whose `handler` is set: some class of this module handles that RPC.
A row from a `.proto` alone has no handler and serves nothing, because a client module
compiles the same `.proto`. The engines already keep their own symbol-based fence (a module
class extending the stub's outer class); this pass is the identity-based half, and it runs
after the merge so every engine's rows are present.

## The exception: a call that names another address

Ruling 3: a client whose row carries a `peer` that is not this module keeps its outbound
row. No gRPC catalog reads a client's configured address yet, so every row's peer is NULL
today and every self-call is dropped. A configured name of the module itself (a service
name, a hostname) is not recognized as this module until OI-186 (SEXTANT-48): such a peer
reads as another host and the row stays outbound, which is the safe side.

## Only gRPC

W27 (`self_exchange.py`) files a question, not a rule, for the other protocols, because
their far end may be another deployment. Ruling 3 builds the rule for gRPC only.
"""

from sextant.application.ports.workspace import Workspace

# OI-198: the other protocols' self-calls are re-checked under this rule as their own item.
_PROTOCOLS = ("grpc",)

# The hosts that name this module itself. IPv6 loopback appears both bare and bracketed.
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})

# The columns that tell two endpoint rows apart, `peer` included (the SQL says why).
_ROW_COLUMNS = ("protocol", "direction", "method", "path", "handler", "caller", "peer")


def served_services(workspace: Workspace) -> dict[str, set[str]]:
    """Each service identity this module handles, mapped to the wire paths it serves.

    From inbound `grpc` rows whose `handler` is set; an inbound path is
    `<identity>/<Method>`, e.g. `helloworld.Greeter/SayHello`.
    """
    served: dict[str, set[str]] = {}
    for row in workspace.query("endpoints"):
        if (
            str(row["protocol"]) not in _PROTOCOLS
            or str(row["direction"]) != "inbound"
            or row["handler"] is None
            or row["path"] is None
        ):
            continue
        path = str(row["path"])
        identity, separator, _method = path.rpartition("/")
        if separator:
            served.setdefault(identity, set()).add(path)
    return served


def _is_this_module(peer: str | None) -> bool:
    """True when a call's address is absent or names the machine it runs on.

    The scheme and the port are ignored: `localhost`, `localhost:9000`,
    `http://localhost:9000` and `[::1]:9000` are all this module.

    A gRPC name-resolver target such as `dns:///localhost:9000` is not read as loopback,
    so such a row stays outbound (the safe side).
    """
    if peer is None:
        return True
    host = peer.split("://", 1)[-1].split("/", 1)[0]
    if host.startswith("["):
        host = host[: host.find("]") + 1]
    elif host.count(":") <= 1:
        host = host.split(":", 1)[0]
    return host.lower() in _LOOPBACK


def record_self_calls(workspace: Workspace) -> None:
    """Drops every outbound row for a service this module serves, unless its peer names
    another host."""
    served = served_services(workspace)
    if not served:
        return
    rows = [
        {column: row.get(column) for column in _ROW_COLUMNS}
        for row in workspace.query("endpoints")
        if str(row["protocol"]) in _PROTOCOLS
        and str(row["direction"]) == "outbound"
        and row["path"] is not None
        and str(row["path"]) in served
        and _is_this_module(None if row["peer"] is None else str(row["peer"]))
    ]
    workspace.derive("self_call_endpoints_drop", rows=rows)
