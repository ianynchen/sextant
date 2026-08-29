"""Roots a shape by unwrapping declared envelope wrappers (D02 §2a), expands
the rooted type into wire fields (D2), and points each endpoint at the shapes
its handler declares (D01 §3 Contracts).

A return or parameter type reference is often not the wire payload itself —
it is an envelope around it. Which types are envelopes, and where the payload
sits inside them, is framework knowledge, so it arrives as catalog data
(`Catalog.wrappers`) rather than being named here. This module is the generic
interpreter: it never names a framework, only follows what the catalog
declares.

Expansion is computed here rather than in SQL for two reasons: it re-roots
every field through the same wrapper rules, and the `item` descriptor is
recursive — assembled bottom-up over a queue of shapes, which one statement
cannot express. The derivation is handed the finished rows."""

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.endpoints import missing_capabilities


@dataclass(frozen=True)
class RootedType:
    # The whole reference unwrapping stopped at, not only its symbol: what the
    # payload is on the wire — its `wire_type`, its own type arguments — lives
    # on that node, and re-finding it would mean walking the wrappers twice.
    reference: dict[str, Any]
    # `semantics` values, outermost first — e.g. `("async", "http_envelope")`
    # for `Mono<ResponseEntity<T>>`.
    chain: tuple[str, ...]
    # True when unwrapping stopped at a generic type with no matching wrapper
    # rule, rather than at a genuine payload. D02 §2a: an incomplete catalog
    # must degrade visibly, not guess past a wrapper nobody declared.
    unmatched_wrapper: bool

    @property
    def symbol(self) -> str:
        return str(self.reference["symbol"])


@dataclass(frozen=True)
class ExpandedShapes:
    """What the pass could not expand: types with no field facts and no
    `known_types` entry. Returned rather than dropped because M04 reports
    them (D2) — a catalog grows from observation, and a gap nobody can see is
    a gap nobody closes."""

    unexpanded_types: tuple[str, ...]


def root_type(type_ref: dict[str, Any], wrappers: list[dict[str, Any]]) -> RootedType:
    """Unwraps `type_ref` through `wrappers` recursively until it reaches a
    type no wrapper rule claims, or one with no type arguments to unwrap."""
    chain: list[str] = []
    current = type_ref
    while True:
        wrapper = _matching_wrapper(current["symbol"], wrappers)
        if wrapper is None:
            # A leaf with no type arguments (e.g. `OrderView`) is a payload,
            # not an unmatched wrapper — nothing about it looked like an
            # envelope. Only a still-generic type that no rule claims is the
            # "unfamiliar wrapper" D02 §2a means: it could be an envelope,
            # and unwrapping it anyway would be a guess presented as fact.
            unmatched = bool(current["arguments"])
            return RootedType(reference=current, chain=tuple(chain), unmatched_wrapper=unmatched)
        arguments = current["arguments"]
        if wrapper["payload_arg"] >= len(arguments):
            # A declared envelope holding nothing at the payload position:
            # ordinary code, not a broken catalog. A raw `ResponseEntity`, and
            # every envelope reached through an erased method descriptor,
            # arrives with its argument already gone. It is the same answer as
            # an envelope nobody declared — something that could be holding a
            # payload, left unopened and said so — because the two are the same
            # situation: the catalog claims an envelope and no payload is
            # visible inside it. The chain records envelopes actually peeled,
            # so this one is not added: a `semantics` recorded here would let
            # `required` be derived from an unwrapping that never happened.
            return RootedType(reference=current, chain=tuple(chain), unmatched_wrapper=True)
        chain.append(wrapper["semantics"])
        current = arguments[wrapper["payload_arg"]]


def _matching_wrapper(symbol: str, wrappers: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (wrapper for wrapper in wrappers if _catalog_symbol(wrapper["type"]) == symbol), None
    )


def _catalog_symbol(dotted_type: str) -> str:
    """Converts a catalog's dotted type name to the SCIP symbol form the facts
    use.

    Two forms exist for the same type on purpose: D02's catalogs write a
    dotted name (`reactor.core.publisher.Mono`) because that is how the spec
    and every catalog author spells a fully qualified type; the scanner emits
    SCIP symbols (`reactor/core/publisher/Mono#`, D00 §5a) because that is the
    grammar the rest of the fact stream is keyed on. Neither side should
    change to suit the other — the catalog stays readable in its source
    notation, the facts stay one grammar — so the conversion happens once,
    here, at the point of comparison.
    """
    return dotted_type.replace(".", "/") + "#"


def derive_shapes(workspace: Workspace, catalog: Catalog, roots: Sequence[str]) -> ExpandedShapes:
    """Expands each root into a `shapes` row and its `shape_fields`, following
    every reference it finds.

    Cycles terminate by construction: an `object` field holds a *reference* to
    another shape, never an inlining, so `Node { Node parent; }` needs no depth
    counter — only the discipline that each shape is expanded once.
    """
    rules = _rules_of(catalog)
    scope_prefixes = _scope_prefixes(workspace, rules)
    declared = _declared_fields(workspace)
    enums = _enum_symbols(workspace)
    shapes: list[dict[str, object]] = []
    fields: list[dict[str, object]] = []
    unexpanded: list[str] = []
    # A list, not a set: the order shapes are reached in decides the order rows
    # are written and the order the report names gaps (NFR-1).
    pending = list(dict.fromkeys(roots))
    expanded: set[str] = set()

    while pending:
        shape_id = pending.pop(0)
        if shape_id in expanded:
            continue
        expanded.add(shape_id)
        referenced: list[str] = []
        rows = _rows_of(
            workspace, rules, scope_prefixes, declared.get(shape_id, []), enums, referenced
        )
        pending.extend(referenced)
        # Expansion needs field facts, and only scanned types have them, so a
        # type without them stops here whoever wrote it (ruling F4). Its
        # reference is still kept: an open, zero-field shape row (D2).
        expandable = shape_id in declared
        if not expandable:
            unexpanded.append(shape_id)
        shapes.append(
            {
                "shape_id": shape_id,
                "content_hash": _content_hash(rows),
                # Direct, never transitive: a shape is open because a field of
                # its own stopped, not because something further down did.
                "open": not expandable or any(held not in declared for held in referenced),
            }
        )
        fields.extend(
            {"shape_id": shape_id, "ordinal": ordinal, **row} for ordinal, row in enumerate(rows)
        )

    # Fields first: the shape row is what marks a shape settled for a later
    # catalog, so it is written once its fields are in (D02 §5).
    workspace.derive("shape_fields", fields=fields)
    workspace.derive("shapes", shapes=shapes)
    return ExpandedShapes(unexpanded_types=tuple(unexpanded))


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
    # Inbound catalogs first, same tie-break as derive_endpoints (D02 §3): an
    # owner's signature is claimed by the first catalog that answers it
    # (below), and an outbound catalog's own wrapper rules do not describe an
    # inbound handler's envelope types — so an inbound owner must reach an
    # inbound catalog before an outbound one gets a turn at it, or it settles
    # for whatever an unrelated catalog's narrower wrapper list left unopened.
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
    out every column an earlier catalog already answered.

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


@dataclass(frozen=True)
class _Rules:
    """The catalog's serialisation and type knowledge, with every dotted name
    already converted — the binding seam, crossed once so no rule below has to
    remember which notation it is holding."""

    wrappers: list[dict[str, Any]]
    known_types: dict[str, dict[str, Any]]
    name_from: list[dict[str, str]]
    ignore: tuple[str, ...]
    default_strategy: str
    # D02 §2e's three ways a catalog declares nullability, each already
    # converted at the binding seam like every other block here.
    nullable_annotations: tuple[str, ...]
    not_null_annotations: tuple[str, ...]
    # Scope annotation symbol -> the `nullable` value it implies for
    # everything the symbol it was found on claims (`_scope_prefixes`).
    scope_annotations: dict[str, bool]


def _rules_of(catalog: Catalog) -> _Rules:
    serialization = catalog.serialization
    nullability = catalog.nullability
    return _Rules(
        # Wrappers stay dotted: `root_type` crosses the same seam itself.
        wrappers=catalog.wrappers,
        known_types={_catalog_symbol(known["type"]): known for known in catalog.known_types},
        name_from=[
            {"annotation": _catalog_symbol(source["annotation"]), "arg": source["arg"]}
            for source in serialization.get("name_from", [])
        ],
        ignore=tuple(_catalog_symbol(name) for name in serialization.get("ignore", [])),
        # A catalog that declares no strategy renames nothing. Absence is not a
        # licence to invent one.
        default_strategy=serialization.get("default_strategy", "as_declared"),
        nullable_annotations=tuple(
            _catalog_symbol(name) for name in nullability.get("nullable", [])
        ),
        not_null_annotations=tuple(
            _catalog_symbol(name) for name in nullability.get("not_null", [])
        ),
        scope_annotations={
            _catalog_symbol(entry["annotation"]): _SCOPE_MEANINGS[entry["means"]]
            for entry in nullability.get("scope", [])
        },
    )


# D02 §2e's one scope meaning. A catalog naming one that is not here is a
# broken file, and the KeyError above names it — the same discipline
# `_STRATEGIES` uses for serialisation strategies.
_SCOPE_MEANINGS: dict[str, bool] = {"not_null_by_default": False}


def _declared_fields(workspace: Workspace) -> dict[str, list[dict[str, Any]]]:
    """Every field fact grouped by the type that declares it, in declaration
    order — the `ordinal` source (NFR-1)."""
    owners: dict[str, list[dict[str, Any]]] = {}
    for row in workspace.query("fields"):
        symbol = str(row["symbol"])
        # A symbol is module coordinates then a descriptor (D00 §5a); shape ids
        # and type references are both keyed on the descriptor alone.
        descriptor = symbol.rpartition(" ")[2]
        owner = descriptor[: descriptor.index("#") + 1]
        owners.setdefault(owner, []).append(
            {
                "symbol": symbol,
                "name": descriptor[len(owner) :].removesuffix("."),
                "returns": json.loads(str(row["returns"])),
                "static": bool(row["static"]),
                "transient": bool(row["transient"]),
            }
        )
    return owners


def _enum_symbols(workspace: Workspace) -> set[str]:
    """The declared types the facts call enumerations, as the descriptors a
    type reference is keyed on.

    Read once per pass rather than once per field, for the reason
    `_scope_prefixes` is: the answer is on the referenced type's own fact, not
    on the reference that reaches it.
    """
    return {str(row["symbol"]).rpartition(" ")[2] for row in workspace.query("enum_types")}


# The reserved file-class name the JVM compiles a package-level annotation
# onto — the only spelling `_scope_prefix` strips, so a scope declared on an
# actual type named that (impossible on the JVM) is not a concern.
_PACKAGE_FILE_CLASS = "package-info#"


def _scope_prefixes(workspace: Workspace, rules: _Rules) -> list[tuple[str, bool]]:
    """Where each declared scope (D02 §2e) reaches, as the symbol prefix it
    claims and the `nullable` value it implies. Read once per pass, not once
    per field: a scope's target is a class or a package, never the field
    itself, so `annotations_of`'s per-field lookup cannot find it."""
    if not rules.scope_annotations:
        return []
    prefixes = []
    for row in workspace.query("annotations"):
        means = rules.scope_annotations.get(str(row["annotation"]))
        if means is None:
            continue
        prefixes.append((_scope_prefix(str(row["target"])), means))
    return prefixes


def _scope_prefix(target: str) -> str:
    """The symbol prefix one scope declaration claims (pre-flight ruling, Task
    11 brief). A type-level target is already a prefix of its own members
    (`…X#` prefixes `…X#code.`); a package-level one compiles onto a
    synthetic file-class, so that trailing segment is stripped to recover the
    package it was actually declared on."""
    if target.endswith(_PACKAGE_FILE_CLASS):
        return target[: -len(_PACKAGE_FILE_CLASS)]
    return target


def _scope_nullable(prefixes: list[tuple[str, bool]], field_symbol: str) -> bool | None:
    """`None` when no declared scope encloses this field. When more than one
    does — a package scope and a class scope inside it — the longer, more
    specific prefix wins, the same way a nearer declaration always overrides
    one further out."""
    claiming = [claim for claim in prefixes if field_symbol.startswith(claim[0])]
    if not claiming:
        return None
    return max(claiming, key=lambda claim: len(claim[0]))[1]


def _explicit_nullable(rules: _Rules, annotations: list[dict[str, object]]) -> bool | None:
    """`None` when no annotation on the field's own type says anything.
    `type_path` NULL or `''` is what makes this the field's own type rather
    than a type argument's (D00 §5a): `List<@Nullable String>` must not flip
    the field's `nullable`, only its element's."""
    result: bool | None = None
    for use in annotations:
        if use["type_path"] not in (None, ""):
            continue
        if use["annotation"] in rules.not_null_annotations:
            result = False
        elif use["annotation"] in rules.nullable_annotations:
            result = True
    return result


def _nullability_of(
    rules: _Rules,
    reference: dict[str, Any],
    described_nullable: bool,
    annotations: list[dict[str, object]],
    scope_prefixes: list[tuple[str, bool]],
    field_symbol: str,
) -> tuple[bool, str]:
    """`nullable` and its `resolution`, layered extractor -> scope -> explicit
    annotation (D02 §2e), last wins. `described_nullable` already carries a
    known type's own override where one applies (`_described`); that is
    catalog data too; so it resolves the same way as every later layer."""
    known = rules.known_types.get(reference["symbol"])
    nullable = described_nullable
    resolution = (
        "resolved"
        if known is not None and "nullable" in known
        else str(reference["nullable_resolution"])
    )

    scoped = _scope_nullable(scope_prefixes, field_symbol)
    if scoped is not None:
        nullable, resolution = scoped, "resolved"

    explicit = _explicit_nullable(rules, annotations)
    if explicit is not None:
        nullable, resolution = explicit, "resolved"

    return nullable, resolution


def _rows_of(
    workspace: Workspace,
    rules: _Rules,
    scope_prefixes: list[tuple[str, bool]],
    declared: list[dict[str, Any]],
    enums: set[str],
    referenced: list[str],
) -> list[dict[str, object]]:
    """One projected row per field that reaches the wire, appending every shape
    the fields reference to `referenced`."""
    rows: list[dict[str, object]] = []
    for field in declared:
        # On no payload, whoever wrote it: a value bound to the type rather than
        # to an instance, or one the language declares as not serialized. Both
        # are ordinary declarations — the facts keep them — and only the
        # modifier the language recorded separates them from a contract field.
        # Filtered here rather than where the facts are grouped, so a type whose
        # every field is excluded stays a type the pass expanded rather than one
        # it reports as a gap. No row at all, for the reason the ignore rule
        # below gives.
        if field["static"] or field["transient"]:
            continue
        annotations = workspace.query("annotations_of", target=field["symbol"])
        # No row, not a row marked absent: DR-5 would compare a field the
        # catalog says is off the wire against a peer that correctly omits it.
        if any(use["annotation"] in rules.ignore for use in annotations):
            continue
        wire_name, evidence = _wire_name(rules, field["name"], annotations)
        # Rooted first: a field inside a declared envelope is described by what
        # the envelope holds, not by the envelope (D02 §2a).
        rooted = root_type(field["returns"], rules.wrappers)
        described = _described(rules, rooted.reference, enums, referenced)
        nullable, resolution = _nullability_of(
            rules,
            rooted.reference,
            described["nullable"],
            annotations,
            scope_prefixes,
            field["symbol"],
        )
        rows.append(
            {
                "wire_name": wire_name,
                "wire_type": described["wire_type"],
                "wire_format": described["wire_format"],
                # Presence machinery only, never nullability (D00 §5b): the
                # one source this phase has is the wrapper chain rooting
                # already recorded — an `optional` wrapper is what makes a
                # field omittable.
                "required": "optional" not in rooted.chain,
                "nullable": nullable,
                "resolution": resolution,
                "evidence": evidence,
                "item": _item_of(described),
            }
        )
    return rows


def _wire_name(
    rules: _Rules, declared_name: str, annotations: list[dict[str, object]]
) -> tuple[str, str]:
    """The wire name and the evidence behind it (D02 §2f). `wire_name` is the
    identity (D01 §5), so the source name is only ever the fallback."""
    for source in rules.name_from:
        use = next((a for a in annotations if a["annotation"] == source["annotation"]), None)
        given = json.loads(str(use["args"])).get(source["arg"]) if use and use["args"] else None
        if given:
            return str(given), "compiler"
    # A strategy is a declaration a module's own configuration may override, so
    # a name derived from it is never presented as observed.
    return _STRATEGIES[rules.default_strategy](declared_name), "declared"


def _separated(name: str, separator: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", separator, name).lower()


# D02 §2f's four strategies. A catalog naming one that is not here is a broken
# file, and the KeyError names it.
_STRATEGIES: dict[str, Callable[[str], str]] = {
    "as_declared": lambda name: name,
    "snake_case": lambda name: _separated(name, "_"),
    "kebab_case": lambda name: _separated(name, "-"),
    "upper_camel": lambda name: name[:1].upper() + name[1:],
}

# The two wire types that hold something other than themselves (D00 §5b).
_COLLECTIONS = ("array", "map")


def _described(
    rules: _Rules, reference: dict[str, Any], enums: set[str], referenced: list[str]
) -> dict[str, Any]:
    """The recursive `{wire_type, wire_format, nullable, shape_id?, item?}`
    descriptor for one type reference (D01 §5)."""
    known = rules.known_types.get(reference["symbol"])
    if known is not None:
        # Mapped and never expanded: a type the serialiser turns into a scalar
        # has no field list on the wire, and expanding it would invent one
        # (D02 §2g). A known type may also declare its own `nullable` (D02
        # §2g) — a wrapper type such as protobuf's, whose wire behaviour the
        # reference's own flag does not describe — which then overrides the
        # reference's answer for this field or element.
        return {
            "wire_type": known["wire"],
            "wire_format": known.get("format", ""),
            "nullable": known.get("nullable", reference["nullable"]),
        }
    described = {
        "wire_type": reference["wire_type"],
        "wire_format": reference["wire_format"],
        "nullable": reference["nullable"],
    }
    if reference["symbol"] in enums:
        # A closed set of constants is one value on the wire, which is why D00
        # §5b keeps `enum` in the vocabulary — so it is mapped and never
        # expanded, exactly as a known type is. Expanded, its constants become
        # fields of a payload nobody sends; left as the `object` the reference
        # says it is, it marks its owner open and is reported as a gap the
        # catalog cannot close, because nothing is missing. The overridden
        # answer comes from the referenced type's own construct kind, which is
        # fact data every language produces, not knowledge of one of them.
        return {**described, "wire_type": "enum"}
    if described["wire_type"] in _COLLECTIONS:
        # What a collection holds is its last type argument: a keyed
        # collection's keys are strings on the wire, so only its value
        # argument describes the payload, and a sequence has just the one.
        if reference["arguments"]:
            described["item"] = _described(rules, reference["arguments"][-1], enums, referenced)
    elif described["wire_type"] == "object":
        described["shape_id"] = reference["symbol"]
        referenced.append(reference["symbol"])
    return described


def _item_of(described: dict[str, Any]) -> str | None:
    """What the field holds, as JSON — a collection's element, or the shape an
    object field points at (ruling F3). Without it nothing links a field to the
    shape carrying its fields, and one `wire_type` cannot tell a sequence of
    strings from a sequence of records.

    D01 §5 states one grammar, `{wire_type, wire_format, nullable, shape_id?,
    item?}`, so an object field's descriptor is the whole one and not a shorter
    variant: two shapes of `item` would make every consumer detect which it was
    holding before it could read a single key.
    """
    held = described.get("item")
    if held is None and "shape_id" in described:
        held = described
    return None if held is None else json.dumps(held, sort_keys=True, separators=(",", ":"))


def _content_hash(rows: list[dict[str, object]]) -> str:
    """Change detection, never identity (ruling F1): `item` points at other
    shapes by `shape_id`, so a content-derived identity for a type that refers
    to itself would depend on itself. Taken over the rows in order, because
    two runs that disagree on field order are two different answers (NFR-1)."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "md5:" + hashlib.md5(payload, usedforsecurity=False).hexdigest()
