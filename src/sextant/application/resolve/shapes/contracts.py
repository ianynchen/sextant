import json
import re
from dataclasses import dataclass
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
    # The same answer once more, now that the catalog has had its say: a
    # `known_types` entry declaring no wire type at all (D02 §2g, the empty
    # `wire_type` a `void` return already carries) is the type that reaches
    # no wire — a `Void` response argument. Describing it would claim a
    # payload for a call that returns nothing.
    if described["wire_type"] in (None, ""):
        return None
    return json.dumps(described, sort_keys=True, separators=(",", ":"))


# --- Call-payload rooting (D02 §2h) --------------------------------------
#
# `single_call` (Task 9) and `fluent` (Task 11) both derive an endpoint from
# a captured call-site argument rather than from a handler's declared
# signature, and both need the very same answers: how a captured url splits
# into peer and path and what that says about the row's own resolution, how
# one D00 §5 argument roots at a payload descriptor, the one-hop D02 §2h
# follow through a `call_wrappers` constructor or a `type_carriers`
# supertype, and which declared type carries a PTR supertype. Shared here
# rather than duplicated per style.

_ABSOLUTE_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://(?P<authority>[^/]*)(?P<path>/.*)?$")


def split_url(url: str) -> tuple[str | None, str]:
    """Checkpoint ruling CP-2: an absolute URL (a `scheme://` capture)
    splits generically into its authority — the peer — and its path
    component; a relative url string stays path-only, peer NULL, because the
    base address then lives in builder code no call-site literal ever names.
    """
    match = _ABSOLUTE_URL.match(url)
    if match is None:
        return None, url
    return match.group("authority"), match.group("path") or ""


def url_of(argument: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
    """One row's `peer`, `path` and `resolution` from its url argument: a
    `string` argument's value is the template verbatim — placeholders and
    all, because the template is the wire identity — split into peer/path by
    CP-2's rule; anything else (never captured at all, or captured but the
    wrong kind — a `uri` step whose argument is a `lambda`, the uriBuilder
    form — or a positional slot the call site never filled) still derives
    the row, path NULL, resolution `unresolved`: D02 §2's "this method calls
    something over HTTP" is true and useful on its own."""
    if (
        argument is not None
        and argument.get("kind") == "string"
        and isinstance(argument.get("value"), str)
    ):
        peer, path = split_url(str(argument["value"]))
        return peer, path, "resolved"
    return None, None, "unresolved"


@dataclass(frozen=True)
class CarrierRules:
    """The catalog data `argument_descriptor` needs beyond the shared
    `_Rules` (D02 §2h): which `instance` types are PTR-shaped carriers whose
    own declared supertype names the payload, and which constructor argument
    a `call_wrappers` type's real payload sits at. Every dotted name already
    converted — the same binding-seam discipline `_Rules` itself keeps, so no
    rule below has to remember which notation it is holding."""

    rules: _Rules
    enums: set[str]
    type_carriers: tuple[str, ...]
    call_wrappers: dict[str, int]


@dataclass(frozen=True)
class CallFacts:
    """The workspace facts `argument_descriptor` needs beyond the argument
    itself, scoped to the one call site whose arguments are being described:
    every declared type's own supertype reference (D00 §5a's PTR carrier,
    keyed by its bare descriptor — never the module-prefixed identity a
    symbol fact's own `symbol` column holds), and the call sites sharing this
    call's own caller — the pool the `call_wrappers` one-hop searches for a
    matching `<init>`. Never call sites from a different caller: `receiver`/
    `result` ids are meaningless across methods (D00 §5), so the search must
    not reach outside this caller's own sites.

    `referenced` is the same accumulator `_described` already appends every
    object it meets to — threaded through here so a payload this pass roots
    is collected exactly like every other payload root, for the shape queue
    that expands it.
    """

    supertypes: dict[str, dict[str, Any]]
    caller_call_sites: list[dict[str, Any]]
    referenced: list[str]


def supertypes_of(workspace: Workspace) -> dict[str, dict[str, Any]]:
    """Every declared type's own generic supertype reference (D00 §5a's PTR
    carrier), keyed by the type's bare descriptor — the form an `instance`
    argument's own `symbol` carries, never the module-prefixed identity a
    symbol fact's own `symbol` column holds (the same stripping
    `_enum_symbols` applies to its own rows, for the same reason: a symbol is
    module coordinates then a descriptor, D00 §5a, and only the descriptor is
    ever compared)."""
    return {
        str(row["symbol"]).rpartition(" ")[2]: json.loads(str(row["supertype"]))
        for row in workspace.query("supertypes")
    }


def argument_descriptor(
    argument: dict[str, Any] | None,
    workspace_types: CallFacts,
    catalog_rules: CarrierRules,
) -> str | None:
    """The wire descriptor a D00 §5 call argument names, or None when the
    argument carries no resolvable payload — an `unresolved` slot, a `null`,
    a `lambda`, or an `instance`/`class` this catalog's rules say nothing
    special about beyond its own type. Shared with Task 11's `fluent`
    engine, which resolves the very same argument grammar off a captured
    step argument rather than a `methods` row's positional slot.

    - a `class` argument roots at the object (or known-type) descriptor for
      its symbol — a class literal such as `OrderView.class`;
    - a literal argument (`string`, `int`, `long`, `boolean`) roots at the
      scalar its own kind names: a bare `String` body is a real contract,
      and NULL keeps exactly one meaning (D01 §3, amended);
    - an `instance` argument whose type's own declared supertype names a
      `type_carriers` entry roots at that supertype's own payload argument
      (D02 §2h's PTR follow) — a full D00 §5a type reference, fed to
      `_described` exactly as a field reference would be, so a PTR payload
      that is itself a collection or an envelope resolves exactly like one;
    - an `instance` of a declared `call_wrappers` type follows exactly one
      hop, to the linked constructor call site's `payload_ctor_arg` — never
      further, and never where no `call_wrappers` entry matches;
    - a bare `instance` roots at the object (or known-type) descriptor for
      its own concrete type;
    - anything else resolves to no payload — the row still derives (D02 §2's
      `single_call` rule), only the descriptor is absent.
    """
    reference = _reference_of(argument, workspace_types, catalog_rules)
    return _payload_descriptor(
        reference, catalog_rules.rules, catalog_rules.enums, workspace_types.referenced
    )


def _reference_of(
    argument: dict[str, Any] | None,
    workspace_types: CallFacts,
    catalog_rules: CarrierRules,
) -> dict[str, Any] | None:
    """The D00 §5a type reference one call argument names, before wrapper
    unwrapping — `argument_descriptor`'s own rules, split out so
    `argument_descriptor` itself stays a one-line call into the shared
    `_payload_descriptor` projection."""
    if argument is None:
        return None
    kind = argument.get("kind")
    if kind == "class":
        symbol = argument.get("symbol")
        return None if symbol is None else _bare_reference(str(symbol))
    if kind in _LITERAL_WIRE_TYPES:
        return _literal_reference(str(kind))
    if kind != "instance":
        # `unresolved`, `null`, `lambda`: none of these names a payload type
        # at all.
        return None
    symbol = argument.get("symbol")
    if symbol is None:
        return None
    symbol = str(symbol)
    supertype = workspace_types.supertypes.get(symbol)
    if supertype is not None and str(supertype.get("symbol")) in catalog_rules.type_carriers:
        carried = supertype.get("arguments") or []
        # A carrier declared with nothing at its own payload position — the
        # same "declared envelope, nothing visible inside it" case §2a's
        # `root_type` already names — is no payload, not a crash.
        return carried[0] if carried else None
    payload_ctor_arg = catalog_rules.call_wrappers.get(symbol)
    if payload_ctor_arg is not None:
        constructor = _linked_constructor(symbol, argument.get("source"), workspace_types)
        if constructor is None:
            return None
        ctor_arguments = constructor.get("arguments") or []
        if payload_ctor_arg >= len(ctor_arguments):
            return None
        # Exactly one hop (D02 §2h: "the engine follows exactly that one hop
        # and stops"): the ctor's own payload argument is read as a terminal
        # reference — never through `_reference_of` again, which would let a
        # ctor argument that happens to itself be a `type_carriers` or
        # `call_wrappers` instance chain into a second hop the catalog never
        # asked for.
        return _terminal_reference(ctor_arguments[payload_ctor_arg])
    return _bare_reference(symbol)


def _terminal_reference(argument: dict[str, Any] | None) -> dict[str, Any] | None:
    """The bare reference a `call_wrappers` one-hop stops on: the ctor
    argument's own type, read verbatim from a `class` or `instance` kind,
    with no further D02 §2h resolution — the one hop is the whole rule."""
    if argument is None or argument.get("kind") not in ("class", "instance"):
        return None
    symbol = argument.get("symbol")
    return None if symbol is None else _bare_reference(str(symbol))


# D00 §5's literal argument kinds, each projected into the one D00 §5b wire
# type it can be. The kind *is* the answer: a literal carries its own type,
# so this is the one payload projection needing neither a symbol nor a
# catalog's knowledge of one — `int` and `long` are the fact grammar's own
# names for the two integer widths, and `wire_format` is what keeps them
# apart on the wire.
_LITERAL_WIRE_TYPES: dict[str, tuple[str, str]] = {
    "string": ("string", ""),
    "int": ("integer", "int32"),
    "long": ("integer", "int64"),
    "boolean": ("boolean", ""),
}

# Descriptor grammar, not language knowledge (D00 §5a): an array symbol is
# its element's symbol with this suffix. Parsed here — and only here —
# because a `class`/`instance` argument carries a bare symbol and nothing
# else, so the element reference a scanned field already arrives with has to
# be rebuilt from the one thing the argument does carry.
_ARRAY_SUFFIX = "[]"


def _literal_reference(kind: str) -> dict[str, Any]:
    """A D00 §5a type reference synthesised from a literal argument's own
    kind. `symbol` is empty because a literal names no type — nothing keys a
    `known_types` entry or an enum on it, and nothing may root a shape at
    it. `nullable: False` for the same reason a primitive's own reference is
    not nullable: a literal is a value, and an absent one is D00 §5's `null`
    kind instead."""
    wire_type, wire_format = _LITERAL_WIRE_TYPES[kind]
    return {
        "symbol": "",
        "arguments": [],
        "wire_type": wire_type,
        "wire_format": wire_format,
        "nullable": False,
    }


def _bare_reference(symbol: str) -> dict[str, Any]:
    """A D00 §5a type reference synthesised from a bare symbol — a `class`
    literal or a constructed `instance` carries only its type, never the
    `wire_type`/`nullable` projection a typed signature reference does.
    `wire_type: object` is not a guess: both argument kinds name a concrete
    reference type. `nullable: True` is the same default a language whose
    every reference type permits null gives a `resolved` field absent any
    narrower answer (D00 §5a) — `_described` still overrides both from
    `known_types` or the enum set where the catalog names one, which is how
    a scalar type the serialiser flattens (and the `Void` that reaches no
    wire at all) stops being described as an object here.

    An array symbol keeps its element as its single type argument, exactly
    as a scanned `String[]` field's own reference does (D00 §5a): without
    it, `OrderView[].class` and `String[].class` are the same `array`
    holding nothing, which is the one thing `item` exists to prevent."""
    if symbol.endswith(_ARRAY_SUFFIX):
        return {
            "symbol": symbol,
            "arguments": [_bare_reference(symbol[: -len(_ARRAY_SUFFIX)])],
            "wire_type": "array",
            "wire_format": "",
            "nullable": True,
        }
    return {
        "symbol": symbol,
        "arguments": [],
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
    }


def _linked_constructor(
    owner_symbol: str, source: int | None, workspace_types: CallFacts
) -> dict[str, Any] | None:
    """D02 §2h's join: the `<init>` call site, within this same caller, whose
    `receiver` is the constructed value's own id — the argument's `source`.
    Never a search by proximity: the id is what keeps two constructors in one
    method apart."""
    if source is None:
        return None
    return next(
        (
            site
            for site in workspace_types.caller_call_sites
            if site.get("name") == "<init>"
            and site.get("owner") == owner_symbol
            and site.get("receiver") == source
        ),
        None,
    )
