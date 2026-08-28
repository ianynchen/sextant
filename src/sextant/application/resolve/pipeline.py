from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.endpoints import (
    SkippedCatalog,
    derive_endpoints,
    load_catalogs,
)


@dataclass(frozen=True)
class ResolveReport:
    facts_loaded: int
    endpoints: list[dict[str, object]] = field(default_factory=list)
    skipped_catalogs: list[SkippedCatalog] = field(default_factory=list)
    coverage: dict[str, object] = field(default_factory=dict)


def resolve(
    workspace: Workspace, fact_root: Path, catalogs_dir: Path, capabilities: set[str]
) -> ResolveReport:
    """Facts in, graph out. Language-blind: it branches on capabilities, never
    on names (M04)."""
    loaded = workspace.load_facts(fact_root)
    catalogs = load_catalogs(catalogs_dir)
    skipped = derive_endpoints(workspace, catalogs, capabilities)
    return ResolveReport(
        facts_loaded=loaded,
        endpoints=workspace.query("endpoints"),
        skipped_catalogs=skipped,
        coverage=workspace.query("coverage")[0],
    )
