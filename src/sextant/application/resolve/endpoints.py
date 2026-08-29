"""The engine registry and the annotation_driven engine (D02 §2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module."""

from collections.abc import Callable
from dataclasses import dataclass

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace


@dataclass(frozen=True)
class SkippedCatalog:
    catalog_id: str
    missing_capabilities: tuple[str, ...]


def derive_endpoints(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> list[SkippedCatalog]:
    """Runs each catalog whose required capabilities are met, and reports the
    rest. A skipped catalog is never silent (M04, FR-17)."""
    # Every style is resolved before anything is written. A catalog naming an
    # engine that does not exist is a broken file, and a broken file must not
    # leave a half-emptied endpoints table behind it.
    engines = [(catalog, _engine_for(catalog)) for catalog in catalogs]
    # Emptied once, here, rather than once per catalog: D02 §5 has two
    # catalogs both matching and both producing endpoints, so a per-catalog
    # rebuild would leave only whichever ran last. Unconditional, so a resolve
    # in which every catalog is skipped still leaves an empty table rather
    # than the previous run's rows.
    workspace.derive("endpoints_reset")
    # D02 §3: the merge runs once, after every engine, so this ordering does
    # not affect which rows it finds — it exists for determinism only (NFR-1):
    # inbound before outbound, filename breaking the tie within a direction,
    # which is the loader's own order.
    ordered = sorted(
        engines, key=lambda pair: (pair[0].direction != "inbound", str(pair[0].source))
    )
    skipped = []
    for catalog, engine in ordered:
        missing = missing_capabilities(catalog, capabilities)
        if missing:
            skipped.append(SkippedCatalog(catalog.id, missing))
            continue
        engine(workspace, catalog)
    # Once per resolve, after every catalog: a wire identity present in both
    # directions collapses to one row, direction `both` (D02 §3).
    workspace.derive("endpoints_merge")
    return skipped


def missing_capabilities(catalog: Catalog, capabilities: set[str]) -> tuple[str, ...]:
    """What a catalog requires and this scan does not provide, in a stable
    order.

    Shared rather than restated, because every pass that reads a catalog must
    gate on exactly the same answer. A pass that gated differently would run
    against facts the scanner never produced and quietly report nothing — the
    silent degradation capability gating exists to prevent (M04, FR-17) — and
    a catalog already reported as skipped must not be reported a second time
    for the same reason.
    """
    return tuple(sorted(set(catalog.requires) - capabilities))


def _engine_for(catalog: Catalog) -> "Callable[[Workspace, Catalog], None]":
    """Resolves the engine for a catalog's declared style, or refuses it.

    A style with no engine is a broken catalog, not a degraded run. Capability
    gating reports what it skips; an unmatched style would produce no endpoints
    and no skip, which reads as "this framework exposes nothing" — the failure
    the reporting exists to prevent.
    """
    try:
        return _ENGINES[catalog.style]
    except KeyError:
        raise CatalogError(
            f"loading catalog {catalog.source}: `style: {catalog.style}` has no engine "
            f"— one of {', '.join(sorted(_ENGINES))} (D02 §2)"
        ) from None


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


# One entry per engine style D02 §2 declares and this codebase implements.
# Adding a style is a function above and a line here, and `_engine_for` refuses
# any catalog naming a style that is not in it.
_ENGINES: dict[str, Callable[[Workspace, Catalog], None]] = {
    "annotation_driven": _run_annotation_driven,
}
