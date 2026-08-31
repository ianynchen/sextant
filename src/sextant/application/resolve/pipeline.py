from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import resolve_config
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
    # M04 pass 2 (D01, D02 §2i): the generic config-model interpreter, run
    # before endpoint derivation — the `config_join` engine (2F design §3)
    # that will consume `resolved_config` runs as an endpoint style, so its
    # capability has to exist before `derive_endpoints` gates the catalogs.
    # Unconditional, empty in and empty out (`resolve_config`'s own
    # contract), so a config-less run still leaves the table's earlier
    # contents cleared rather than stale.
    resolve_config(workspace, declared)
    # The first PIPELINE-declared capability (D02 §1): every capability
    # above it is scanner-declared, earned once up front by the scanner
    # that produced a module's facts. This one is earned by the pipeline
    # itself, once pass 2 has run — a catalog naming it in `requires` is
    # skipped, visibly, the same as any unmet scanner capability, until this
    # line has run in THIS resolve.
    capabilities = capabilities | {"resolved_config"}
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
