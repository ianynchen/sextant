"""The catalog loader and the annotation_driven engine (D02 §1-§2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sextant.application.ports.workspace import Workspace


@dataclass(frozen=True)
class Catalog:
    id: str
    style: str
    protocol: str
    direction: str
    requires: tuple[str, ...]
    matches: dict[str, Any]


@dataclass(frozen=True)
class SkippedCatalog:
    catalog_id: str
    missing_capabilities: tuple[str, ...]


def load_catalogs(directory: Path) -> list[Catalog]:
    catalogs = []
    for path in sorted(directory.glob("*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        catalogs.append(Catalog(
            id=raw["id"], style=raw["style"], protocol=raw["protocol"],
            direction=raw["direction"], requires=tuple(raw.get("requires", [])),
            matches=raw["matches"],
        ))
    return catalogs


def derive_endpoints(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> list[SkippedCatalog]:
    """Runs each catalog whose required capabilities are met, and reports the
    rest. A skipped catalog is never silent (M04, FR-17)."""
    skipped = []
    for catalog in catalogs:
        missing = tuple(sorted(set(catalog.requires) - capabilities))
        if missing:
            skipped.append(SkippedCatalog(catalog.id, missing))
            continue
        if catalog.style == "annotation_driven":
            _run_annotation_driven(workspace, catalog)
    return skipped


def _run_annotation_driven(workspace: Workspace, catalog: Catalog) -> None:
    """Passes the catalog's own protocol, direction, annotation identifiers,
    and HTTP-method mapping through to the derivation as bound parameters.
    The engine here is generic: it never names a framework or a protocol,
    only forwards what the catalog declares."""
    prefix_from = catalog.matches["path_prefix_from"]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        type_annotation=catalog.matches["type_annotation"],
        prefix_annotation=prefix_from["annotation"],
        prefix_arg=prefix_from["arg"],
        method_annotations=[
            {"fqn": m["fqn"], "http_method": m["http_method"], "path_arg": m["path_arg"]}
            for m in catalog.matches["method_annotations"]
        ],
    )
