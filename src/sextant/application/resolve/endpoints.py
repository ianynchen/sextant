"""The catalog loader and the annotation_driven engine (D02 §1-§2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Direction, Protocol


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


class CatalogError(ValueError):
    """A catalog file that cannot be trusted. Raised at load, because an
    unchecked value does not stay in the file: it is bound straight into the
    derivation and published as `protocol` in metadata.json, where a typo is
    indistinguishable from an observation."""


def load_catalogs(directory: Path) -> list[Catalog]:
    """Reads every catalog in `directory`, newest schema only.

    Raises `CatalogError` naming the file and the offending value when a
    catalog omits a required field or declares a `protocol` or `direction`
    outside D00's closed sets.
    """
    catalogs = []
    for path in sorted(directory.glob("*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise CatalogError(f"loading catalog {path}: not a YAML mapping")
        catalogs.append(
            Catalog(
                id=_required(raw, "id", path),
                style=_required(raw, "style", path),
                protocol=_closed(raw, "protocol", Protocol, path),
                direction=_closed(raw, "direction", Direction, path),
                requires=tuple(raw.get("requires", [])),
                matches=_required(raw, "matches", path),
            )
        )
    return catalogs


def _required(raw: dict[str, Any], key: str, path: Path) -> Any:
    if key not in raw:
        raise CatalogError(
            f"loading catalog {path}: no `{key}` — every catalog declares one (D02 §1)"
        )
    return raw[key]


def _closed(raw: dict[str, Any], key: str, values: type[StrEnum], path: Path) -> str:
    """Checks one field against a closed set of D00 (`domain/closed_sets.py`).

    The sets are closed on purpose: adding a value is a schema change, never
    an implementation choice (NFR-5). So a value outside one is not a new
    kind of endpoint, it is a mistake, and the only place it is still cheap
    to name is the file it came from.
    """
    value = _required(raw, key, path)
    allowed = sorted(member.value for member in values)
    if value not in allowed:
        raise CatalogError(
            f"loading catalog {path}: `{key}: {value}` is not one of "
            f"{', '.join(allowed)} — D00's closed sets are closed (NFR-5)"
        )
    return str(value)


def derive_endpoints(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> list[SkippedCatalog]:
    """Runs each catalog whose required capabilities are met, and reports the
    rest. A skipped catalog is never silent (M04, FR-17)."""
    # Emptied once, here, rather than once per catalog: D02 §5 has two
    # catalogs both matching and both producing endpoints, so a per-catalog
    # rebuild would leave only whichever ran last. Unconditional, so a resolve
    # in which every catalog is skipped still leaves an empty table rather
    # than the previous run's rows.
    workspace.derive("endpoints_reset")
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
    """Passes the catalog's own protocol, direction, annotation identifiers and
    mapping declaration through to the derivation as bound parameters. The
    engine here is generic: it never names a framework or a protocol, only
    forwards what the catalog declares."""
    mapping = catalog.matches["mapping"]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        type_annotation=catalog.matches["type_annotation"],
        prefix_annotation=mapping["prefix_annotation"],
        # `method` is absent for an annotation that pre-sets none, and the
        # derivation reads that absence as "every method in all_methods".
        mapping_annotations=[
            {"fqn": m["fqn"], "methods": m.get("method")} for m in mapping["annotations"]
        ],
        path_from=list(mapping["path_from"]),
        method_from=mapping["method_from"],
        all_methods=list(mapping["all_methods"]),
    )
