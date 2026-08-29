from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints
from sextant.application.resolve.shapes import derive_endpoint_shapes


@dataclass(frozen=True)
class ResolveReport:
    facts_loaded: int
    endpoints: list[dict[str, object]] = field(default_factory=list)
    skipped_catalogs: list[SkippedCatalog] = field(default_factory=list)
    coverage: dict[str, object] = field(default_factory=dict)
    shapes: list[dict[str, object]] = field(default_factory=list)
    # The types the expansion reached and could not open: no field facts and
    # no catalog entry describing them. Carried rather than counted, because a
    # count cannot be acted on and a catalog only grows from observation
    # (FR-17).
    unexpanded_types: tuple[str, ...] = ()


def resolve(
    workspace: Workspace,
    fact_root: Path,
    catalogs: CatalogSource,
    capabilities: set[str],
) -> ResolveReport:
    """Facts in, graph out. Language-blind: it branches on capabilities, never
    on names (M04)."""
    loaded = workspace.load_facts(fact_root)
    declared = catalogs.load()
    skipped = derive_endpoints(workspace, declared, capabilities)
    # After the endpoints, never beside them: an endpoint's payload types come
    # off its handler's signature, which is a column on the row derive_endpoints
    # just wrote.
    expanded = derive_endpoint_shapes(workspace, declared, capabilities)
    return ResolveReport(
        facts_loaded=loaded,
        endpoints=workspace.query("endpoints"),
        skipped_catalogs=skipped,
        coverage=workspace.query("coverage")[0],
        shapes=workspace.query("shapes"),
        unexpanded_types=expanded.unexpanded_types,
    )
