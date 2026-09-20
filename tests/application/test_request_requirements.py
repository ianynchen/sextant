"""The inbound request-requirements pass (spec 2026-09-19 §5a): the writer, and the one
mechanism that lands with it — the combinator's `route_requirements` stash joined to the
`endpoints` rows it was minted with.

The three other mechanisms (§5b parameter annotations, §5c mapping attributes, §5d handler
reads) arrive in their own tasks and are tested there; here they return nothing, which is
what lets the first test say that a run with nothing declared writes NOTHING rather than
an empty-looking something.

## Everything here is invented

Invented symbols, an invented catalog id, an invented header — the reason every pass test
in this directory gives: one behaviour per test, isolated and fast, with the shipped
answer pinned once in `test_pipeline.py` against real bytecode.
"""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.request_requirements import record_request_requirements
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
ROUTES = _MODULE + "com/acme/orders/OrderRoutes#routes(sig_00000001)."
HANDLER = _MODULE + "com/acme/orders/OrderRoutes#routes$lambda$1(sig_00000002)."
OTHER_HANDLER = _MODULE + "com/acme/orders/OrderRoutes#routes$lambda$2(sig_00000003)."
CATALOG = "invented-dsl"


def _catalog() -> Catalog:
    """An inbound catalog declaring none of §5's keys — the case every shipped catalog is
    in until its own task lands."""
    return Catalog(
        id=CATALOG,
        style="combinator",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("tests/invented.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )


def _workspace(tmp_path: Path, *rows: tuple[str, str, str, str, str | None]) -> DuckDbWorkspace:
    """A workspace holding exactly the inbound endpoint rows a test names, as
    `(protocol, method, path, handler, caller)` — the columns an engine mints a route
    with, `catalog_id` fixed — and an empty `route_requirements` stash, the way the
    pipeline leaves both before this pass runs."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.derive("endpoint_metadata_reset")
    workspace.derive("route_requirements_reset")
    for protocol, method, path, handler, caller in rows:
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, method, path, handler, caller, catalog_id) "
            "VALUES (?, 'inbound', ?, ?, ?, ?, ?)",
            [protocol, method, path, handler, caller, CATALOG],
        )
    return workspace


def _stash(
    workspace: DuckDbWorkspace,
    handler: str,
    name: str,
    requirement: str | None,
    **overrides: object,
) -> None:
    workspace.derive(
        "route_requirements_insert",
        rows=[
            {
                "caller": ROUTES,
                "handler": handler,
                "method": "GET",
                "path": "/orders",
                "catalog_id": CATALOG,
                "kind": "header",
                "name": name,
                "value": None,
                "requirement": requirement,
                "resolution": "resolved",
                "evidence": "compiler",
                **overrides,
            }
        ],
    )


def _entries(workspace: DuckDbWorkspace) -> list[dict[str, object]]:
    return [dict(row) for row in workspace.query("endpoint_metadata")]


def test_nothing_declared_writes_nothing(tmp_path: Path):
    """An inbound endpoint, a catalog declaring none of §5's keys and an empty stash: the
    table stays empty. Not an entry with every column NULL — the absence of a row is the
    statement "the code states nothing", and a NULL row would be a different one."""
    workspace = _workspace(tmp_path, ("http", "GET", "/orders", HANDLER, ROUTES))
    record_request_requirements(workspace, [_catalog()])
    entries = _entries(workspace)
    workspace.close()

    assert entries == []


def test_the_stash_is_joined_to_its_row_and_carries_the_rows_final_protocol(tmp_path: Path):
    """§4d/§5a: the combinator stashes a requirement under the columns it minted the route
    with — `(caller, handler, method, path, catalog_id)` — and this pass, running after
    `apply_protocol_hints`, writes it against the row as it stands THEN: the row's own
    `protocol` (reclassified to `sse` here, the stash knowing nothing of it), `caller` the
    handler, `direction` inbound. A stash row whose route no longer exists — the engine
    refused it, or another catalog's row won the address — is dropped rather than written
    against nothing."""
    workspace = _workspace(tmp_path, ("sse", "GET", "/orders", HANDLER, ROUTES))
    _stash(workspace, HANDLER, "X-Api-Version", "required", value="2")
    _stash(workspace, HANDLER, "debug", None, kind="query")
    _stash(workspace, OTHER_HANDLER, "X-Orphan", "required")
    record_request_requirements(workspace, [_catalog()])
    entries = _entries(workspace)
    workspace.close()

    assert entries == [
        {
            "protocol": "sse",
            "direction": "inbound",
            "method": "GET",
            "path": "/orders",
            "caller": HANDLER,
            "kind": "header",
            "name": "X-Api-Version",
            "value": "2",
            "resolution": "resolved",
            "evidence": "compiler",
            "requirement": "required",
        },
        {
            "protocol": "sse",
            "direction": "inbound",
            "method": "GET",
            "path": "/orders",
            "caller": HANDLER,
            "kind": "query",
            "name": "debug",
            "value": None,
            "resolution": "resolved",
            "evidence": "compiler",
            "requirement": None,
        },
    ]
