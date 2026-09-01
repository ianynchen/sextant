from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints
from sextant.application.resolve.format import resolve_format
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.shapes import derive_endpoint_shapes
from sextant.application.resolve.shapes.parse_binding import bind_parse_calls


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
    # The 2K hand-off ledger (2G design §6) is emptied once, here, ahead of
    # every pass that writes to it rather than inside one of them — the
    # `resolved_config` reset discipline, lifted out of the writing pass
    # because more than one pass writes these rows. A resolve whose passes
    # had nothing to ask still leaves an empty table rather than the previous
    # run's rows.
    reset_open_questions(workspace)
    # Above the ladder and below the reset, which is exactly where the
    # comment on that line asks a payload-binding pass to go (2G design §6):
    # it WRITES `open_questions` rows, so it must run after the reset, and
    # the format ladder's rung 4 READS the payload column it binds — a bound
    # schema-described parse is what lifts a NULL format to that schema's own
    # format at `narrowed`.
    bound = bind_parse_calls(workspace, declared)
    # LAST, and the ordering is a property of the pass, not a preference (the
    # `_RUNS_LAST` precedent in `resolve/endpoints.py`): every rung of the
    # format ladder reads something an earlier pass wrote — the media columns
    # the config stamp filled, the payload columns the shape pass bound — so
    # a format stamped before them would be answered from a table that was
    # still being written. Anything that BINDS a payload belongs above this
    # line and below the reset.
    resolve_format(workspace, declared)
    return ResolveReport(
        facts_loaded=loaded,
        endpoints=workspace.query("endpoints"),
        skipped_catalogs=skipped,
        coverage=workspace.query("coverage")[0],
        shapes=workspace.query("shapes"),
        # Both passes root payload types and both expand what they root, so
        # both can meet a type nothing opens. Reported as one list, deduped:
        # the gap is in the type, not in how many passes walked into it —
        # the same rule `derive_endpoint_shapes` applies across catalogs.
        unexpanded_types=tuple(
            dict.fromkeys([*expanded.unexpanded_types, *bound.unexpanded_types])
        ),
    )
