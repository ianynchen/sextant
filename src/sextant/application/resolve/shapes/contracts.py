import json
import re
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.capabilities import missing_capabilities
from sextant.application.resolve.conditions import (
    annotation_index,
    holds,
    member_annotations_by_type,
)
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
    _check_conditional_wrappers(catalogs)
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
        found = _contracts_of(workspace, endpoints, catalog, settled, rules, enums, referenced)
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


def _check_conditional_wrappers(catalogs: list[Catalog]) -> None:
    """Refuses a `wrappers[].when` entry whose `type` some OTHER catalog's
    UNCONDITIONAL `wrappers` also names (spec 2026-09-18 §5a) — the sort-order
    hazard `spring-kafka.yml`'s own `wrappers` comment already describes for
    an unconditional copy: shape expansion is global and insert-if-absent, so
    whichever catalog's rules reach a shared type first is the one everyone
    else's payload gets described by. A conditional entry sits beside that
    same hazard from the other direction — it would make the FIRST catalog's
    unconditional answer depend on which one happened to load first, silently,
    since neither file's own text says the type is shared. Checked once,
    ahead of the loop, so a catalog whose `when` can never even be reached
    (no handler owns a row) is still refused rather than let through by luck.
    """
    unconditional_types: dict[str, Catalog] = {}
    for catalog in catalogs:
        for wrapper in catalog.wrappers:
            if "when" not in wrapper:
                unconditional_types.setdefault(_catalog_symbol(wrapper["type"]), catalog)
    for catalog in catalogs:
        for wrapper in catalog.wrappers:
            if "when" not in wrapper:
                continue
            other = unconditional_types.get(_catalog_symbol(wrapper["type"]))
            if other is not None and other is not catalog:
                raise CatalogError(
                    f"{catalog.source}: wrappers[type={wrapper['type']}] declares `when`, but "
                    f"{other.source} names the same type unconditionally — the type would be "
                    "an envelope everywhere that catalog's rules apply and an envelope only "
                    "conditionally here, so which answer wins would depend on catalog sort "
                    "order rather than on either file's own text"
                )


def _wrappers_for(
    rules: "_Rules", owner: str, index: dict[str, list[tuple[str, dict[str, Any]]]]
) -> list[dict[str, Any]]:
    """The envelopes that apply to THIS owner: every unconditional wrapper, plus each
    conditional one whose `when` holds on the owner or its type (spec 2026-09-18 §5a)."""
    return [
        *rules.wrappers,
        *(
            wrapper
            for condition, wrapper in rules.conditional_wrappers
            if holds(condition, owner, index)
        ),
    ]


# The two endpoint columns this pass fills. Named rather than spelled out at
# each use, because the same two strings key the per-handler answer, the bound
# rows, and the column they land in.
_REQUEST = "request_shape"
_RESPONSE = "response_shape"


def _contracts_of(
    workspace: Workspace,
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
    # What the body rule reads beside the signature, built once per call and
    # never per row (GUIDELINES §8.7): the two annotation folds are once per
    # LOAD (`Workspace.once`), and an owner's composed paths are one pass over
    # the rows this catalog owns.
    index = annotation_index(workspace)
    members = member_annotations_by_type(workspace)
    paths = _paths_by_owner(endpoints, catalog)
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
        body = _body_type(
            signature,
            catalog,
            owner=owner,
            paths=paths.get(owner, frozenset()),
            index=index,
            members=members,
        )
        # Once per owner, for both columns (spec §5a): the request and the
        # response of one handler share the same conditional evaluation, so
        # `holds` is asked once here rather than once per column.
        wrappers = _wrappers_for(rules, owner, index)
        columns = {
            _REQUEST: _payload_descriptor(body, rules, enums, referenced, wrappers),
            _RESPONSE: _payload_descriptor(
                signature.get("returns"), rules, enums, referenced, wrappers
            ),
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


def _paths_by_owner(
    endpoints: list[dict[str, object]], catalog: Catalog
) -> dict[str, frozenset[str]]:
    """owner → every composed path the rows this catalog owns give it — what
    the `path_variable` implicit binding reads a parameter's name against
    (spec 2026-09-18 §4 predicate 2). One handler mapped to several paths is
    several rows sharing one signature, so the names are read over all of
    them; a row with no path contributes none."""
    found: dict[str, set[str]] = {}
    for endpoint in endpoints:
        if _owns(catalog, endpoint) and endpoint.get("path") is not None:
            owner = str(endpoint["handler"] or endpoint["caller"] or "")
            found.setdefault(owner, set()).add(str(endpoint["path"]))
    return {owner: frozenset(paths) for owner, paths in found.items()}


def _body_type(
    signature: dict[str, Any], catalog: Catalog, **context: Any
) -> dict[str, Any] | None:
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
    found = _body_parameter(signature, catalog, **context)
    if found is None:
        return None
    reference = dict(found[1]["type"])
    return None if not names_a_type(str(reference.get("symbol", ""))) else reference


def _body_parameter(
    signature: dict[str, Any],
    catalog: Catalog,
    *,
    owner: str,
    paths: frozenset[str],
    index: dict[str, list[tuple[str, dict[str, Any]]]],
    members: dict[str, set[str]],
) -> tuple[int, dict[str, Any]] | None:
    """The payload parameter the catalog's body rule marks, as its DECLARED
    index and the parameter itself (D02 §2 as amended). The marker wins, where
    the catalog declares one; two fallback words follow. `sole_unannotated`
    exists because one contract (Feign's) marks the body by being the only
    bare parameter. `sole_unbound` (spec 2026-09-18 §4) is the framework's own
    rule where it has no marker at all: JAX-RS §3.3.2.1's entity parameter is
    the one carrying none of the SPECIFICATION's parameter annotations, and an
    annotation the framework does not know — `@Valid`, kotlinc's `@NotNull` —
    is invisible to it, so it is invisible here. A catalog declaring none of
    the three contributes no request shapes.

    `owner`, `paths`, `index` and `members` are what the rule reads beside the
    signature — the row's composed paths for the `path_variable` implicit
    binding, the per-type member annotations for `container` — handed in
    rather than looked up so the caller builds them once (GUIDELINES §8.7).

    The index is carried, not only the type, because 2G's parse binding
    (`shapes/parse_binding.py`) joins a call argument that NAMES a parameter
    (`{kind: parameter, value: N}`, D00 §5) back to the payload — and N is
    the declared index. One rule, read two ways, rather than a second copy of
    the marker/fallback logic in the pass that needs the other half.
    """
    declared = catalog.matches.get("request_body")
    if declared is None:
        return None
    marker = declared.get("annotation")
    parameters = signature.get("parameters", [])
    if marker is not None:
        body_annotation = _catalog_symbol(marker)
        for i, parameter in enumerate(parameters):
            if any(
                use["annotation"] == body_annotation for use in parameter.get("annotations", [])
            ):
                return i, parameter
    fallback = declared.get("fallback")
    # Compared against CATALOG-declared type names, so the descriptor's answer:
    # a type variable's name matches nothing a catalog can write, and an
    # excluded parameter would slip back in and be picked as the body.
    excluded = {_catalog_symbol(t) for t in declared.get("excludes", [])}
    if fallback == "sole_unannotated":
        if "bound_by" in declared or "implicit_bindings" in declared:
            raise CatalogError(
                f"loading catalog {catalog.source}: `request_body.bound_by`/"
                "`implicit_bindings` belong to `fallback: sole_unbound`, not `sole_unannotated`"
            )
        bare = [
            (i, p)
            for i, p in enumerate(parameters)
            if not p.get("annotations")
            and (p.get("erased_symbol") or p["type"].get("symbol")) not in excluded
        ]
        return bare[0] if len(bare) == 1 else None
    if fallback == "sole_unbound":
        bound_by = declared.get("bound_by")
        if not isinstance(bound_by, list) or not bound_by:
            raise CatalogError(
                f"loading catalog {catalog.source}: `fallback: sole_unbound` requires a "
                "non-empty `request_body.bound_by` list — the word means 'unbound by THESE'"
            )
        implicit = declared.get("implicit_bindings") or []
        if not isinstance(implicit, list) or not set(implicit) <= _IMPLICIT_BINDINGS:
            raise CatalogError(
                f"loading catalog {catalog.source}: `request_body.implicit_bindings` must be "
                f"a subset of {sorted(_IMPLICIT_BINDINGS)}, got {implicit!r}"
            )
        binders = {_catalog_symbol(a) for a in bound_by}
        variables = _path_variables(paths) if "path_variable" in implicit else frozenset()
        unbound = [
            (i, p)
            for i, p in enumerate(parameters)
            if not _is_bound(p, binders, excluded, variables, "container" in implicit, members)
        ]
        return unbound[0] if len(unbound) == 1 else None
    return None


# The closed vocabulary of `request_body.implicit_bindings` (spec 2026-09-18 §4):
# the two bindings Quarkus REST reads off no annotation at all (its
# `EndpointIndexer`, CP-19 row 4). Declared by `quarkus-rest.yml` alone;
# `jakarta-jaxrs.yml` declares none, because under Jersey `byId(String id)`
# beneath `@Path("/{id}")` IS an entity body.
_IMPLICIT_BINDINGS = frozenset({"path_variable", "container"})
# A path template's variable: `{name}` or `{name: regex}` — the name is the
# token before the `:`, and the regex may hold anything but a closing brace.
_PATH_VARIABLE = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^}]*)?\}")


def _path_variables(paths: frozenset[str]) -> frozenset[str]:
    return frozenset(name for path in paths for name in _PATH_VARIABLE.findall(path))


def _is_bound(
    parameter: dict[str, Any],
    binders: set[str],
    excluded: set[str],
    variables: frozenset[str],
    container: bool,
    members: dict[str, set[str]],
) -> bool:
    """Whether the framework claims this parameter for something other than
    the body — spec §4's three predicates: an excluded (context) type or an
    explicit binding annotation, a name matching a path variable, a
    parameter-container class. Any one of them binds, so the order they are
    asked in changes nothing; the two implicit ones are asked only where the
    catalog declared the word (`variables` is empty, `container` is False)."""
    symbol = parameter.get("erased_symbol") or parameter["type"].get("symbol")
    if symbol in excluded:
        return True
    if any(use["annotation"] in binders for use in parameter.get("annotations", [])):
        return True
    if parameter.get("name") in variables:
        return True
    return container and bool(members.get(symbol, set()) & binders)


def _payload_descriptor(
    reference: dict[str, Any] | None,
    rules: "_Rules",
    enums: set[str],
    referenced: list[str],
    wrappers: list[dict[str, Any]],
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

    `wrappers` is the caller's own list, not `rules.wrappers` — every caller
    but `_contracts_of` has no owner to test a conditional entry against and
    passes `rules.wrappers` straight through; `_contracts_of` passes
    `_wrappers_for`'s per-owner answer instead (spec 2026-09-18 §5a).
    """
    if reference is None:
        return None
    rooted = root_type(reference, wrappers)
    if _matching_wrapper(rooted.symbol, wrappers) is not None:
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
