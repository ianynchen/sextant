"""The engine registry and gating (D02 §2).

Adding a style is an engine function and a registry entry, and `_engine_for`
refuses any catalog naming a style that is not in it."""

from collections.abc import Callable
from dataclasses import dataclass

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.capabilities import missing_capabilities
from sextant.application.resolve.engines import (
    annotation_driven,
    combinator,
    config_join,
    fluent,
    injected_client,
    interface_implementation,
    schema_operations,
    single_call,
    supertype_derived,
)

# The styles that run after every call-site and annotation style, whatever
# their own declared direction (D02 §3). The `protocol_hint` precedent: a
# style that ENRICHES rows other engines minted — reclassifying one, stamping
# a declared media type onto one — cannot run before the rows exist, so its
# position is a property of the style, never a request the catalog file
# makes. `config_join` is the first of them to ship.
#
# `schema_operations` (2H design §3) is the second, for the same reason twice
# over. It stamps a declared response shape onto rows other engines minted, so
# it cannot precede them; and its own rows meet the insert-if-absent guard
# LAST on purpose — a schema states an operation, an annotation states the
# operation AND the code serving it, and running afterwards is the whole of
# what makes the annotation row the one that survives. First-writer agreement
# by ordering, with no second rule to keep in step.
_RUNS_LAST = frozenset({"config_join", "schema_operations"})

# Within the runs-last group, the same reason applies once more, one level
# down (fix round 1, M-3): a style whose catalogs may EITHER derive rows or
# only stamp them must run every deriving one first, or a stamp arrives
# before the rows it was meant to enrich and silently reaches none of them.
# The predicate lives on the engine — which `matches` block means "derives"
# is that style's own vocabulary, and this module names none. A style absent
# from this map has no such split, and every one of its catalogs ranks alike.
_DERIVES_ROWS: dict[str, Callable[[Catalog], bool]] = {
    "config_join": config_join.derives_rows,
}


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
    #
    # Some styles sort ahead of all of that, or rather behind it: a
    # `_RUNS_LAST` style enriches rows the other engines minted (above), so
    # its own declared direction says nothing about when it must run. Its rows
    # therefore face `derive_call_endpoints.sql`'s insert-if-absent guard
    # after every ANNOTATION and CALL-SITE style has written — which is a real
    # consequence and not an accident: a wire identity one of those catalogs
    # already recorded stays that catalog's row. (Not "last" outright: within
    # the runs-last group the ranks below decide, and two members of it are
    # ordered against each other by `_derives_rows` and then the tiebreaks,
    # exactly as any two catalogs are.)
    #
    # `_derives_rows` then orders WITHIN that group, for the same reason one
    # level down: a catalog that only stamps must not run before one that
    # still has rows to write, or the stamp reaches none of them (M-3).
    # Direction and filename stay the tiebreaks after both ranks, unchanged.
    ordered = sorted(
        engines,
        key=lambda pair: (
            pair[0].style in _RUNS_LAST,
            _derives_rows(pair[0]),
            pair[0].direction != "inbound",
            str(pair[0].source),
        ),
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


def _derives_rows(catalog: Catalog) -> int:
    """The within-group sort rank: 0 for a catalog that derives rows, 1 for
    one that only enriches them. `False < True` sorts a deriving catalog
    first, which is the whole point; a style with no declared split ranks 0,
    so nothing outside `_DERIVES_ROWS` is reordered by this key at all."""
    declared = _DERIVES_ROWS.get(catalog.style)
    return 0 if declared is None or declared(catalog) else 1


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


# One entry per engine style D02 §2 declares and this codebase implements.
_ENGINES: dict[str, Callable[[Workspace, Catalog], None]] = {
    "annotation_driven": annotation_driven.run,
    "single_call": single_call.run,
    "fluent": fluent.run,
    "interface_implementation": interface_implementation.run,
    "combinator": combinator.run,
    "config_join": config_join.run,
    "schema_operations": schema_operations.run,
    # 2O design §1b/§1c (Task 5): both derive rows from their OWN evidence —
    # a supertype's own facts, an injected field's own annotation — rather
    # than enriching rows another engine minted, so neither belongs in
    # `_RUNS_LAST` above.
    "supertype_derived": supertype_derived.run,
    "injected_client": injected_client.run,
}
