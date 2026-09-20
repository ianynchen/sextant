"""Inbound request requirements (spec 2026-09-19 §5): the headers, query parameters and
cookies an inbound endpoint's FRAMEWORK enforces, written to `endpoint_metadata` beside the
outbound entries W29 records — three mechanisms, one writer.

1. `request_params` — parameter annotations on the handler (§5b), read off
   `endpoints.handler_signature`.
2. Route-tree predicates (§5c): Spring's `@RequestMapping(params=, headers=)` read here;
   the combinator's selector/predicate requirements arrive through the `route_requirements`
   stash the engine wrote and are joined to their rows here.
3. `request_reads` — reads in the handler body (§5d), one set-based pass over
   `effective_call_sites`.

Runs AFTER `apply_protocol_hints`: an entry names its row by the row's identity columns,
and `protocol` is final only there. `requirement` states what the framework enforces and
NULL where the code states nothing (A3).

Cost per resolve (GUIDELINES §8.7): one read of `endpoints`, one of the stash, one
`endpoint_metadata_insert` — none of them per catalog. The per-catalog mechanisms read
what the handler row already carries.
"""

from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace


def record_request_requirements(workspace: Workspace, catalogs: list[Catalog]) -> None:
    endpoints = [row for row in workspace.query("endpoints") if row["direction"] == "inbound"]
    rows: list[dict[str, Any]] = []
    rows.extend(_from_stash(workspace, endpoints))
    for catalog in catalogs:
        rows.extend(_from_parameters(endpoints, catalog, workspace))
        rows.extend(_from_mapping_attributes(endpoints, catalog, workspace))
    rows.extend(_from_reads(workspace, endpoints, catalogs))
    # An empty list writes nothing rather than a no-op statement — the
    # `record_open_questions` discipline.
    if rows:
        workspace.derive("endpoint_metadata_insert", rows=rows)


def _entry(
    endpoint: dict[str, object],
    *,
    kind: object,
    name: object,
    value: object,
    requirement: object,
    resolution: object,
    evidence: object,
) -> dict[str, Any]:
    """One `endpoint_metadata` row against an inbound endpoint: the row's own identity
    columns as they stand now, `caller` the handler (§5a)."""
    return {
        "protocol": endpoint["protocol"],
        "direction": "inbound",
        "method": endpoint["method"],
        "path": endpoint["path"],
        "caller": endpoint["handler"],
        "kind": kind,
        "name": name,
        "value": value,
        "resolution": resolution,
        "evidence": evidence,
        "requirement": requirement,
    }


def _from_stash(workspace: Workspace, endpoints: list[dict[str, object]]) -> list[dict[str, Any]]:
    """The combinator's stash joined to its rows on (caller, handler, method, path,
    catalog_id) — the columns the engine minted the route with. A stash row naming no
    live endpoint — the engine refused the route, or another catalog's row won its
    address — is dropped: an entry against a row that does not exist names nothing."""
    by_key = {
        (e["caller"], e["handler"], e["method"], e["path"], e["catalog_id"]): e for e in endpoints
    }
    out = []
    for r in workspace.query("route_requirements"):
        e = by_key.get((r["caller"], r["handler"], r["method"], r["path"], r["catalog_id"]))
        if e is not None:
            out.append(
                _entry(
                    e,
                    kind=r["kind"],
                    name=r["name"],
                    value=r["value"],
                    requirement=r["requirement"],
                    resolution=r["resolution"],
                    evidence=r["evidence"],
                )
            )
    return out


def _from_parameters(
    endpoints: list[dict[str, object]], catalog: Catalog, workspace: Workspace
) -> list[dict[str, Any]]:
    """§5b, `request_params` — lands with its own task; nothing declares it yet."""
    return []


def _from_mapping_attributes(
    endpoints: list[dict[str, object]], catalog: Catalog, workspace: Workspace
) -> list[dict[str, Any]]:
    """§5c, the mapping's own `params`/`headers` attributes — lands with its own task."""
    return []


def _from_reads(
    workspace: Workspace, endpoints: list[dict[str, object]], catalogs: list[Catalog]
) -> list[dict[str, Any]]:
    """§5d, `request_reads` — lands with its own task; nothing declares it yet."""
    return []
