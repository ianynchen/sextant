"""Capability gating (D02 §1, M04) — split out from `endpoints` so a module
that needs the gate, but not the endpoint-derivation loop itself, does not
have to import it. `shapes.arguments` is exactly that case: an engine
registered in `endpoints._ENGINES` may need `arguments`'s call-payload
helpers (D02 §2h), and `endpoints` importing that engine while `contracts`
(which `arguments` itself imports) pulled the gate back from `endpoints` was
a real cycle, not a hypothetical one — this file is the seam that keeps both
directions acyclic."""

from sextant.application.ports.catalogs import Catalog


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
