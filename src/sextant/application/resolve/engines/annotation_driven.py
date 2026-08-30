"""Annotation-driven engine for endpoint derivation (D02 §2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module.
"""

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Passes the catalog's own protocol, direction, annotation identifiers and
    mapping declaration through to the derivation as bound parameters. The
    engine here is generic: it never names a framework or a protocol, only
    forwards what the catalog declares."""
    mapping = catalog.matches["mapping"]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        # Optional (D02 §2, amended): absence means "no type-level gate".
        type_annotation=catalog.matches.get("type_annotation"),
        prefix_annotation=mapping["prefix_annotation"],
        # `method` is absent for an annotation that pre-sets none, and the
        # derivation reads that absence as "every method in all_methods".
        mapping_annotations=[
            {"fqn": m["fqn"], "methods": m.get("method")} for m in mapping["annotations"]
        ],
        path_from=list(mapping["path_from"]),
        prefix_from=list(mapping["prefix_from"]),
        peer_from=list(mapping.get("peer_from", [])),
        method_from=mapping["method_from"],
        all_methods=list(mapping["all_methods"]),
    )
