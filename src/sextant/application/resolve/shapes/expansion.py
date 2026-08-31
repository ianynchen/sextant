"""Expansion is computed here rather than in SQL for two reasons: it re-roots
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
from sextant.application.resolve.shapes.nullability import _nullability_of, _scope_prefixes
from sextant.application.resolve.shapes.rooting import _catalog_symbol, root_type
from sextant.domain.symbols import bare_descriptor, owner_of


@dataclass(frozen=True)
class ExpandedShapes:
    """What the pass could not expand: types with no field facts and no
    `known_types` entry. Returned rather than dropped because M04 reports
    them (D2) — a catalog grows from observation, and a gap nobody can see is
    a gap nobody closes."""

    unexpanded_types: tuple[str, ...]


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
        descriptor = bare_descriptor(symbol)
        owner = owner_of(descriptor)
        if owner is None:
            # A field with no owning type belongs to no shape.
            continue
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
    return {bare_descriptor(str(row["symbol"])) for row in workspace.query("enum_types")}


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
