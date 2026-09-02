"""The Avro branch of the one interpreter (2G design §3). An `.avsc` payload
is a self-contained schema — a record it names is declared in the same JSON —
so this is the one branch that reads a payload at a time rather than
module-wide.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.domain.facts import DeclaredFieldFact, DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.ingress.interpret.wire import (
    GeneratedNaming,
    SchemaLocation,
    evidence_for,
    item_of,
    shape_ref_of,
    wire_format_of,
    wire_type_of,
)

# D00 §5b's wire vocabulary for Avro's primitive names. `fixed` is a sized
# byte string and reads as `bytes` does.
_AVRO_SCALARS: dict[str, tuple[str, str | None]] = {
    # A value that is only ever absent has no encoding of its own. `object`
    # with no shape behind it is the vocabulary's least-committal answer, and
    # it only arises for the degenerate `"type": "null"` field — a union's
    # null branch is nullability, handled before this table is reached.
    "null": ("object", None),
    "boolean": ("boolean", None),
    "int": ("integer", "int32"),
    "long": ("integer", "int64"),
    "float": ("number", "float"),
    "double": ("number", "double"),
    "bytes": ("string", "byte"),
    "string": ("string", None),
}


@dataclass(frozen=True)
class _AvroReading:
    """One payload being read: the fact it came on, the naming its classes are
    named by, and the shapes found so far — collected as the recursion walks
    into nested records."""

    fact: EmbeddedDescriptorFact
    naming: GeneratedNaming
    shapes: list[DeclaredShapeFact]


def avro_shapes(
    fact: EmbeddedDescriptorFact, naming: GeneratedNaming
) -> tuple[list[DeclaredShapeFact], list[str]]:
    try:
        schema = json.loads(fact.payload)
    except json.JSONDecodeError:
        return [], [fact.symbol]
    if not isinstance(schema, dict) or schema.get("type") != "record":
        # A schema that declares no record declares no shape. Reported rather
        # than dropped: something harvested it as one.
        return [], [fact.symbol]
    reading = _AvroReading(fact=fact, naming=naming, shapes=[])
    try:
        _avro_record(schema, "", reading)
    except (KeyError, TypeError, IndexError):
        # JSON that parsed is not yet a schema: a field with no `type`, a
        # record with no `name`, an array with no `items`, a `fields` that is
        # not a list. Every one of those is this payload's gap and no reason
        # to lose the others — and the records read before the malformed one
        # are dropped rather than published, because half a schema is a shape
        # nobody declared.
        return [], [fact.symbol]
    return reading.shapes, []


def _avro_record(node: dict[str, Any], namespace: str, reading: _AvroReading) -> str:
    """Appends the record's shape — and any record nested in its fields, each
    its own shape — and returns the symbol that names it."""
    namespace = str(node.get("namespace", namespace))
    fields = [_avro_field(field, namespace, reading) for field in node.get("fields", [])]
    full_name = _avro_full_name(str(node["name"]), namespace)
    symbol = _avro_symbol(full_name, reading)
    reading.shapes.append(
        DeclaredShapeFact(
            document_id=reading.fact.document_id,
            symbol=symbol,
            schema_name=full_name,
            schema_format="avro",
            origin=reading.fact.origin,
            evidence=evidence_for(reading.fact.origin),
            fields=fields,
        )
    )
    return symbol


def _avro_field(node: dict[str, Any], namespace: str, reading: _AvroReading) -> DeclaredFieldFact:
    described = _avro_element(node["type"], namespace, reading)
    held = _avro_held(node["type"])
    name = str(node["name"])
    return DeclaredFieldFact(
        name=name,
        # Avro's JSON encoding writes the declared name itself — there is no
        # second spelling for a wire name to disagree with.
        wire_name=name,
        # Avro has no field numbers: fields are matched by name against the
        # writer's schema.
        field_number=None,
        wire_type=wire_type_of(described),
        wire_format=wire_format_of(described),
        # A default is what makes a field omittable; a `null` branch is what
        # makes it nullable. Avro states both outright (2G design §3).
        required="default" not in node,
        nullable=bool(described["nullable"]),
        default=_avro_default(node["default"]) if "default" in node else None,
        item=item_of(described),
        shape_ref=shape_ref_of(described),
        enum_symbols=(
            [str(symbol) for symbol in held["symbols"]]
            if isinstance(held, dict) and held.get("type") == "enum"
            else None
        ),
    )


def _avro_element(node: Any, namespace: str, reading: _AvroReading) -> dict[str, object]:
    """D01 §5's recursive descriptor for one Avro type node."""
    if isinstance(node, list):
        described = _avro_element(_avro_branch(node), namespace, reading)
        return {**described, "nullable": "null" in node}
    if isinstance(node, dict):
        kind = node.get("type")
        if kind == "record":
            return {
                "wire_type": "object",
                "wire_format": None,
                "nullable": False,
                "shape_id": _avro_record(node, namespace, reading),
            }
        if kind == "enum":
            return {"wire_type": "enum", "wire_format": None, "nullable": False}
        if kind == "fixed":
            return {"wire_type": "string", "wire_format": "byte", "nullable": False}
        if kind == "array":
            return {
                "wire_type": "array",
                "wire_format": None,
                "nullable": False,
                "item": _avro_element(node["items"], namespace, reading),
            }
        if kind == "map":
            return {
                "wire_type": "map",
                "wire_format": None,
                "nullable": False,
                "item": _avro_element(node["values"], namespace, reading),
            }
        # A primitive with attributes, such as a logical type: the attributes
        # qualify a type this vocabulary already has a name for.
        return _avro_element(kind, namespace, reading)
    scalar = _AVRO_SCALARS.get(str(node))
    if scalar is None:
        # Not a primitive, so a name: a reference to a type declared earlier
        # in the same schema.
        return {
            "wire_type": "object",
            "wire_format": None,
            "nullable": False,
            "shape_id": _avro_symbol(_avro_full_name(str(node), namespace), reading),
        }
    return {"wire_type": scalar[0], "wire_format": scalar[1], "nullable": False}


def _avro_branch(node: Any) -> Any:
    """A union's first non-null branch. Avro itself reads a union's default
    against its first branch, so a union of several is described by that one
    — the wire vocabulary has no word for a value that is two types."""
    if not isinstance(node, list):
        return node
    branches = [branch for branch in node if branch != "null"]
    return branches[0] if branches else "null"


def _avro_held(node: Any) -> Any:
    """What a field's values actually are: past the union, then past the
    collection — the node whose enum constants the field reports, the way a
    protobuf map reports its value type's."""
    resolved = _avro_branch(node)
    if isinstance(resolved, dict):
        if resolved.get("type") == "array":
            return _avro_branch(resolved["items"])
        if resolved.get("type") == "map":
            return _avro_branch(resolved["values"])
    return resolved


def _avro_full_name(name: str, namespace: str) -> str:
    """Avro's own rule: a name containing a dot is already full."""
    if "." in name or not namespace:
        return name
    return f"{namespace}.{name}"


def _avro_symbol(full_name: str, reading: _AvroReading) -> str:
    """An Avro record names one generated class, never a nested one, so its
    location is the whole full name."""
    if reading.fact.origin == "source":
        return full_name
    package, _, name = full_name.rpartition(".")
    return reading.naming.class_symbol(
        SchemaLocation(
            schema_format="avro",
            file_name="",
            package=package,
            path=(name,),
            options={},
            declared_names=frozenset(),
        )
    )


def _avro_default(value: object) -> str:
    """Verbatim, always a string (D00 §5c's rule for a declared value): the
    JSON spelling, so `null` and `false` stay the literals the schema wrote
    rather than becoming Python's."""
    return value if isinstance(value, str) else json.dumps(value)
