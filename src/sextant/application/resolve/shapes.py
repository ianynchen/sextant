"""Roots a shape by unwrapping declared envelope wrappers (D02 §2a), then
expands the rooted type into wire fields (D2).

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
        chain.append(wrapper["semantics"])
        current = current["arguments"][wrapper["payload_arg"]]


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
    declared = _declared_fields(workspace)
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
        rows = _rows_of(workspace, rules, declared.get(shape_id, []), referenced)
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

    # Shapes first: the field rows reference them.
    workspace.derive("shapes", shapes=shapes)
    workspace.derive("shape_fields", fields=fields)
    return ExpandedShapes(unexpanded_types=tuple(unexpanded))


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


def _rules_of(catalog: Catalog) -> _Rules:
    serialization = catalog.serialization
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
    )


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
            }
        )
    return owners


def _rows_of(
    workspace: Workspace,
    rules: _Rules,
    declared: list[dict[str, Any]],
    referenced: list[str],
) -> list[dict[str, object]]:
    """One projected row per field that reaches the wire, appending every shape
    the fields reference to `referenced`."""
    rows: list[dict[str, object]] = []
    for field in declared:
        annotations = workspace.query("annotations_of", target=field["symbol"])
        # No row, not a row marked absent: DR-5 would compare a field the
        # catalog says is off the wire against a peer that correctly omits it.
        if any(use["annotation"] in rules.ignore for use in annotations):
            continue
        wire_name, evidence = _wire_name(rules, field["name"], annotations)
        # Rooted first: a field inside a declared envelope is described by what
        # the envelope holds, not by the envelope (D02 §2a).
        rooted = root_type(field["returns"], rules.wrappers)
        described = _described(rules, rooted.reference, referenced)
        rows.append(
            {
                "wire_name": wire_name,
                "wire_type": described["wire_type"],
                "wire_format": described["wire_format"],
                # Presence is Task 11's, and it is decided by presence
                # machinery alone — never read off what nullability says.
                "required": None,
                "nullable": described["nullable"],
                "resolution": rooted.reference["nullable_resolution"],
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


def _described(rules: _Rules, reference: dict[str, Any], referenced: list[str]) -> dict[str, Any]:
    """The recursive `{wire_type, wire_format, nullable, shape_id?, item?}`
    descriptor for one type reference (D01 §5)."""
    known = rules.known_types.get(reference["symbol"])
    if known is not None:
        # Mapped and never expanded: a type the serialiser turns into a scalar
        # has no field list on the wire, and expanding it would invent one
        # (D02 §2g).
        return {
            "wire_type": known["wire"],
            "wire_format": known.get("format", ""),
            "nullable": reference["nullable"],
        }
    described = {
        "wire_type": reference["wire_type"],
        "wire_format": reference["wire_format"],
        "nullable": reference["nullable"],
    }
    if described["wire_type"] in _COLLECTIONS:
        # What a collection holds is its last type argument: a keyed
        # collection's keys are strings on the wire, so only its value
        # argument describes the payload, and a sequence has just the one.
        if reference["arguments"]:
            described["item"] = _described(rules, reference["arguments"][-1], referenced)
    elif described["wire_type"] == "object":
        described["shape_id"] = reference["symbol"]
        referenced.append(reference["symbol"])
    return described


def _item_of(described: dict[str, Any]) -> str | None:
    """What the field holds, as JSON — a collection's element, or the shape an
    object field points at (ruling F3). Without it nothing links a field to the
    shape carrying its fields, and one `wire_type` cannot tell a sequence of
    strings from a sequence of records."""
    held = described.get("item")
    if held is None and "shape_id" in described:
        held = {"wire_type": described["wire_type"], "shape_id": described["shape_id"]}
    return None if held is None else json.dumps(held, sort_keys=True, separators=(",", ":"))


def _content_hash(rows: list[dict[str, object]]) -> str:
    """Change detection, never identity (ruling F1): `item` points at other
    shapes by `shape_id`, so a content-derived identity for a type that refers
    to itself would depend on itself. Taken over the rows in order, because
    two runs that disagree on field order are two different answers (NFR-1)."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "md5:" + hashlib.md5(payload, usedforsecurity=False).hexdigest()
