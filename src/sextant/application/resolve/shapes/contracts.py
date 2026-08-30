import json
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.endpoints import missing_capabilities
from sextant.application.resolve.shapes.expansion import (
    ExpandedShapes,
    _described,
    _enum_symbols,
    _Rules,
    _rules_of,
    derive_shapes,
)
from sextant.application.resolve.shapes.rooting import _matching_wrapper, root_type


def derive_endpoint_shapes(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> ExpandedShapes:
    """Expands the payloads every derived endpoint declares, and points each
    endpoint at the shapes it got (D01 §3 Contracts).

    Runs over the rows `derive_endpoints` wrote, because that is where the
    handler's signature is: which parameter carries the request payload and
    what the return type unwraps to are read from it here, in the pass, rather
    than re-derived in SQL — the same reason expansion itself is computed
    here.
    """
    # Emptied once, here, for the reason derive_endpoints empties its own
    # table: both halves of the shape derivation are insert-if-absent, so that
    # a type two catalogs reach is one shape rather than two, which makes the
    # whole-table rebuild a once-per-resolve act. Unconditional, so a resolve
    # in which every catalog is skipped leaves empty tables rather than the
    # previous run's answers.
    workspace.derive("shapes_reset")
    endpoints = workspace.query("endpoints")
    settled: dict[str, dict[str, str]] = {}
    unexpanded: list[str] = []
    # Correctness comes from `_owns` below, not from this order: a catalog
    # only ever describes the rows its own direction produced (a `both` row
    # reads as inbound, since the signature surviving on it is the handler's
    # — there is no merge here, `merge_endpoints.sql` already ran, over in
    # `derive_endpoints`, before this pass starts). What this order still
    # decides is which *same-direction* catalog wins when two of them reach
    # the same owner — inbound before outbound only for a stable, named tie-
    # break (filename), same as `derive_endpoints` uses for its own ordering.
    ordered = sorted(
        catalogs, key=lambda catalog: (catalog.direction != "inbound", str(catalog.source))
    )
    for catalog in ordered:
        # Gated exactly as derive_endpoints gates it: a catalog skipped there
        # produced no endpoints and must contribute no shapes either. The skip
        # is already reported once, as a SkippedCatalog; a second channel here
        # would be the same gap said twice.
        if missing_capabilities(catalog, capabilities):
            continue
        rules = _rules_of(catalog)
        enums = _enum_symbols(workspace)
        # `_described` appends every object it meets — including a
        # collection's element — while it builds each column's descriptor, so
        # the roots this catalog expands are read back from there rather than
        # picked out of the two columns by hand: strictly more complete than
        # the 2A roots, which only a bare `object` payload ever reached.
        referenced: list[str] = []
        found = _contracts_of(endpoints, catalog, settled, rules, enums, referenced)
        # Deduped in the order the endpoints reached them, which is the order
        # the shape rows are written and the report names gaps (NFR-1).
        roots = list(dict.fromkeys(referenced))
        unexpanded.extend(derive_shapes(workspace, catalog, roots).unexpanded_types)
        for owner, columns in found.items():
            settled.setdefault(owner, {}).update(columns)

    workspace.derive(
        "endpoint_contracts",
        contracts=[
            {
                # Still the SQL column's name: the owner is the handler for an
                # inbound row and the caller for an outbound one, and the
                # derivation script coalesces both to match it (D01 §3,
                # amended).
                "handler": owner,
                "request_shape": columns.get(_REQUEST),
                "response_shape": columns.get(_RESPONSE),
            }
            for owner, columns in settled.items()
        ],
    )
    # Two catalogs reaching one type report it once: the gap is in the type,
    # not in how many catalogs walked into it.
    return ExpandedShapes(unexpanded_types=tuple(dict.fromkeys(unexpanded)))


# The two endpoint columns this pass fills. Named rather than spelled out at
# each use, because the same two strings key the per-handler answer, the bound
# rows, and the column they land in.
_REQUEST = "request_shape"
_RESPONSE = "response_shape"


def _contracts_of(
    endpoints: list[dict[str, object]],
    catalog: Catalog,
    settled: dict[str, dict[str, str]],
    rules: "_Rules",
    enums: set[str],
    referenced: list[str],
) -> dict[str, dict[str, str]]:
    """The descriptors one catalog can name for each endpoint's owner, leaving
    out every column an earlier catalog already answered — restricted, first,
    to the rows this catalog actually owns (`_owns`), so a catalog is never
    asked to interpret a signature its own rules never governed.

    Keyed on the owner rather than on the endpoint's wire identity because the
    signature is what the shapes come from: one handler mapped to every
    method (an annotation that names none) is several rows sharing one
    signature, and they all carry the same contract. A `both` row keeps both
    `handler` and `caller` (D01 §3, amended), but `handler_signature` on that
    row is always the handler's own signature — the richer side a merge
    keeps rather than the caller's (merge_endpoints.sql) — so `handler` must
    win the or-chain whenever it is present; `caller` only becomes the owner
    on a genuinely outbound row, the one case `handler` is SQL NULL. The SQL
    join coalesces the same two columns in the same order to match.
    """
    found: dict[str, dict[str, str]] = {}
    for endpoint in endpoints:
        # Direction ownership (Task 7 review, Finding 1): a catalog's
        # wrapper/serialization rules describe only the rows its own
        # direction produced. Ordering alone is not this — two catalogs on
        # opposite directions each have rows the other never derived, and an
        # outbound catalog's narrower wrapper list (say, Retrofit's `Call`
        # instead of `ResponseEntity`) is exactly as wrong describing an
        # inbound row as an inbound catalog's is describing an outbound one.
        # A `both` row is inbound-owned: `merge_endpoints.sql` keeps the
        # handler's own `handler_signature` on it, so only the inbound side's
        # rules ever ran against that signature.
        if not _owns(catalog, endpoint):
            continue
        owner = str(endpoint["handler"] or endpoint["caller"] or "")
        if not owner or owner in found:
            continue
        # A handler with no recorded signature declares no payload. `signature`
        # is optional in D00 §5, so the column is SQL NULL — read back as
        # `None` — whenever nothing typed it, and JSON `null` when a fact
        # recorded the absence itself; both arrive here, and neither is a
        # defect. A scanner too weak to type its signatures degrades to "no
        # shapes", never to a crash, exactly as capability gating does one
        # level up.
        declared = endpoint.get("handler_signature")
        signature = None if declared is None else json.loads(str(declared))
        if not isinstance(signature, dict):
            continue
        already = settled.get(owner, {})
        columns = {
            _REQUEST: _payload_descriptor(_body_type(signature, catalog), rules, enums, referenced),
            _RESPONSE: _payload_descriptor(signature.get("returns"), rules, enums, referenced),
        }
        kept = {
            column: descriptor
            for column, descriptor in columns.items()
            if descriptor is not None and column not in already
        }
        if kept:
            found[owner] = kept
    return found


def _owns(catalog: Catalog, endpoint: dict[str, object]) -> bool:
    """Whether `catalog`'s rules are the ones that produced `endpoint`.

    A catalog derives rows of exactly its own declared direction
    (`derive_endpoints.sql` binds `$direction` straight from the catalog), so
    a same-direction row is this catalog's to describe. A `both` row is the
    one exception: `merge_endpoints.sql` folds the outbound duplicate into
    the inbound row and keeps the *inbound* side's `handler_signature`, so
    only an inbound catalog's wrapper and body rules were ever run against
    it — an outbound catalog never touched that signature and must not
    describe it now.
    """
    direction = str(endpoint["direction"])
    return direction == catalog.direction or (
        direction == "both" and catalog.direction == "inbound"
    )


def _body_type(signature: dict[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    """The type of the parameter the catalog's body rule marks (D02 §2 as
    amended). The marker wins; the sole-unannotated fallback exists because
    one contract (Feign's) marks the body by being the only bare parameter.
    A catalog declaring neither contributes no request shapes."""
    declared = catalog.matches.get("request_body")
    if declared is None:
        return None
    parameters = signature.get("parameters", [])
    for parameter in parameters:
        if any(
            use["annotation"] == declared["annotation"] for use in parameter.get("annotations", [])
        ):
            return dict(parameter["type"])
    if declared.get("fallback") == "sole_unannotated":
        bare = [p for p in parameters if not p.get("annotations")]
        if len(bare) == 1:
            return dict(bare[0]["type"])
    return None


def _payload_descriptor(
    reference: dict[str, Any] | None,
    rules: "_Rules",
    enums: set[str],
    referenced: list[str],
) -> str | None:
    """The wire descriptor a signature-level reference roots at, or None for
    *no payload* — a `void` return, an absent body. Scalars are recorded: a
    String response is a real contract, and NULL must keep exactly one
    meaning.

    Rooting can stop *on* a declared envelope when the reference carries
    nothing at the payload position (a raw `ResponseEntity`, every erased
    parameter). That is no payload either: describing the envelope would
    report a type the catalog already declares as one nobody could expand — a
    gap pointing at an entry that is already there. An envelope *nobody*
    declared still becomes a shape and is still reported.
    """
    if reference is None:
        return None
    rooted = root_type(reference, rules.wrappers)
    if _matching_wrapper(rooted.symbol, rules.wrappers) is not None:
        return None
    if rooted.reference.get("wire_type") in (None, ""):
        return None
    described = _described(rules, rooted.reference, enums, referenced)
    return json.dumps(described, sort_keys=True, separators=(",", ":"))
