import json
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.capabilities import missing_capabilities
from sextant.application.resolve.shapes.expansion import (
    ExpandedShapes,
    _described,
    _enum_symbols,
    _Rules,
    _rules_of,
    derive_shapes,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol, _matching_wrapper, root_type
from sextant.domain.symbols import names_a_type


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
        # `catalog_id` ownership (2E-prep design §1a): a catalog's
        # wrapper/serialization rules describe only the rows its own
        # `catalog_id` names. A `both` row carries the inbound side's id
        # (`merge_endpoints.sql` keeps the handler's own `handler_signature`
        # on it too), so it is inbound-owned without any direction reasoning
        # here.
        if not _owns(catalog, endpoint):
            continue
        owner = str(endpoint["handler"] or endpoint["caller"] or "")
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
            # No declared signature to derive columns from at all — but a
            # style with no handler (`single_call`, D02 §2h) may already have
            # set `request_shape`/`response_shape` directly on this very row,
            # off the call site's own arguments rather than off a signature.
            # Those payload types still have to reach shape expansion (Task 9
            # review, Finding C1: a dangling `shape_id` with no `shapes`/
            # `shape_fields` behind it is a broken contract, not a degraded
            # one) — harvested here rather than recomputed, since the engine
            # that wrote the column already ran `_described` once and this
            # only reads the roots back out of what it already decided.
            # Every owned row is read, not only the first per owner: unlike
            # one handler's one shared signature, two call sites sharing a
            # single caller can each carry a genuinely different payload.
            for column in (_REQUEST, _RESPONSE):
                referenced.extend(_shape_roots_of(endpoint.get(column)))
            continue
        if not owner or owner in found:
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


def _shape_roots_of(descriptor_json: object) -> list[str]:
    """The shape ids one already-computed `request_shape`/`response_shape`
    column names, walking an `item` chain the same way `_described` builds
    one — recovered from the finished JSON rather than re-derived, for a row
    whose payload came from a call site's own arguments (D02 §2h) rather
    than a declared signature. The engine that wrote the column already ran
    `_described` once; this reads back the other half of what that call
    already decided, so a shape reached only through a call site still gets
    expanded and reported like every other root (Task 9 review, Finding
    C1)."""
    if descriptor_json is None:
        return []
    node = json.loads(str(descriptor_json))
    roots: list[str] = []
    while isinstance(node, dict):
        shape_id = node.get("shape_id")
        if shape_id is not None:
            roots.append(str(shape_id))
        node = node.get("item")
    return roots


def _owns(catalog: Catalog, endpoint: dict[str, object]) -> bool:
    """Whether `catalog`'s rules are the ones that produced `endpoint` — read
    straight off the row's own `catalog_id` (2E-prep design §1a), the
    producing catalog's identity stamped at derivation time, rather than
    reasoned about from direction, protocol or row-level overrides. A row
    with no `catalog_id` is owned by nobody, which cannot happen once every
    derivation stamps it."""
    return endpoint.get("catalog_id") == catalog.id


def _body_type(signature: dict[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    """The type of the parameter the catalog's body rule marks (D02 §2 as
    amended).

    This one reads `type`, NOT `erased_symbol` like the comparisons elsewhere in
    this module — the declared type is the point of it, and reading the signature
    is exactly what lets `List<OrderEvent>` keep its element here.

    **But a type VARIABLE is not a type, and a shape is rooted by its symbol.**
    `@RequestBody T body` on a generic base controller would root a shape whose id
    is `T`, and every unrelated `T` anywhere in the module collides onto that one
    id — one shape claiming to describe several unrelated payloads. A type
    variable's name means something only inside the declaration that introduced
    it, and a shape id is read from outside one.

    So the answer is no shape, not a wrong one (§8.1 rule 2). The erasure is not
    substituted in its place: `erased_symbol` is a symbol, while this returns a
    full type REFERENCE carrying `wire_type` and `wire_format`, and those are the
    variable's, not its erasure's. Deriving the erasure's would mean computing a
    language's wire mapping in the application layer, which is the extractor's job
    (NFR-2). Before W5 a parameter's `type` WAS the erasure, so this rooted at the
    bound — a root that expands to nothing wherever the bound is the universal one.
    """
    found = _body_parameter(signature, catalog)
    if found is None:
        return None
    reference = dict(found[1]["type"])
    return None if not names_a_type(str(reference.get("symbol", ""))) else reference


def _body_parameter(
    signature: dict[str, Any], catalog: Catalog
) -> tuple[int, dict[str, Any]] | None:
    """The payload parameter the catalog's body rule marks, as its DECLARED
    index and the parameter itself (D02 §2 as amended). The marker wins; the
    sole-unannotated fallback exists because one contract (Feign's) marks the
    body by being the only bare parameter. A catalog declaring neither
    contributes no request shapes.

    The index is carried, not only the type, because 2G's parse binding
    (`shapes/parse_binding.py`) joins a call argument that NAMES a parameter
    (`{kind: parameter, value: N}`, D00 §5) back to the payload — and N is
    the declared index. One rule, read two ways, rather than a second copy of
    the marker/fallback logic in the pass that needs the other half.
    """
    declared = catalog.matches.get("request_body")
    if declared is None:
        return None
    body_annotation = _catalog_symbol(declared["annotation"])
    parameters = signature.get("parameters", [])
    for index, parameter in enumerate(parameters):
        if any(use["annotation"] == body_annotation for use in parameter.get("annotations", [])):
            return index, parameter
    if declared.get("fallback") == "sole_unannotated":
        excluded = {_catalog_symbol(t) for t in declared.get("excludes", [])}
        bare = [
            (index, parameter)
            for index, parameter in enumerate(parameters)
            # Compared against CATALOG-declared type names, so the descriptor's answer:
            # a type variable's name matches nothing a catalog can write, and an
            # excluded parameter would slip back in and be picked as the body.
            if not parameter.get("annotations")
            and (parameter.get("erased_symbol") or parameter["type"].get("symbol")) not in excluded
        ]
        if len(bare) == 1:
            return bare[0]
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
    # The same answer once more, now that the catalog has had its say: a
    # `known_types` entry declaring no wire type at all (D02 §2g, the empty
    # `wire_type` a `void` return already carries) is the type that reaches
    # no wire — a `Void` response argument. Describing it would claim a
    # payload for a call that returns nothing.
    if described["wire_type"] in (None, ""):
        return None
    return json.dumps(described, sort_keys=True, separators=(",", ":"))
