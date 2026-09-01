"""The one interpreter (2G design §3): the only code in the system that
understands a schema format. Embedded descriptor payloads in,
`declared_shape` facts out — no extractor in any language links a schema
runtime, and adding a third format touches this file and nothing else.

Understanding a schema format is not the same as understanding a language, and
this module deliberately does only the first. Naming the class a code
generator compiled a schema type into is per-language knowledge, so it arrives
as a `GeneratedNaming` the caller supplies (ARCHITECTURE §10's confinement
rule) — the same shape as every other adapter this system wires in.

Protobuf is read **two-phase and module-wide**, because descriptors import one
another: a field's type and its `json_name` may live in an imported file, so
phase one collects every payload and phase two adds them to one
`DescriptorPool` dependency-first. A per-payload interpreter would fail on
every multi-file schema.

Failure is a gap, never a crash: an unparseable payload or an import nothing
in the module carries lands that payload's symbol in the returned failure list
(the `descriptors_not_interpreted` gap), and every other payload still
interprets.
"""

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

# The protobuf runtime's `FieldDescriptor.label` is gone in 7.x — presence and
# repeatedness are read as `has_presence`/`is_repeated` below — which is what
# the `>=` floor in pyproject.toml is holding.
from google.protobuf import descriptor, descriptor_pb2, descriptor_pool
from google.protobuf.message import DecodeError

from sextant.domain.facts import DeclaredFieldFact, DeclaredShapeFact, EmbeddedDescriptorFact

# The two origins a payload can have, and the two evidence tiers they earn.
type Origin = Literal["compiled", "source"]

# D00 §5b's wire vocabulary, keyed by protobuf field type (2G design §3's
# mapping table). Every protobuf scalar appears: a type missing here would be
# a silent hole, and the groups protoc still accepts carry a `message_type`,
# so they never reach this table.
_PROTOBUF_SCALARS: dict[int, tuple[str, str | None]] = {
    descriptor.FieldDescriptor.TYPE_DOUBLE: ("number", "double"),
    descriptor.FieldDescriptor.TYPE_FLOAT: ("number", "float"),
    descriptor.FieldDescriptor.TYPE_INT64: ("integer", "int64"),
    descriptor.FieldDescriptor.TYPE_UINT64: ("integer", "uint64"),
    descriptor.FieldDescriptor.TYPE_INT32: ("integer", "int32"),
    descriptor.FieldDescriptor.TYPE_FIXED64: ("integer", "fixed64"),
    descriptor.FieldDescriptor.TYPE_FIXED32: ("integer", "fixed32"),
    descriptor.FieldDescriptor.TYPE_BOOL: ("boolean", None),
    descriptor.FieldDescriptor.TYPE_STRING: ("string", None),
    descriptor.FieldDescriptor.TYPE_BYTES: ("string", "byte"),
    descriptor.FieldDescriptor.TYPE_UINT32: ("integer", "uint32"),
    descriptor.FieldDescriptor.TYPE_SFIXED32: ("integer", "int32"),
    descriptor.FieldDescriptor.TYPE_SFIXED64: ("integer", "int64"),
    descriptor.FieldDescriptor.TYPE_SINT32: ("integer", "int32"),
    descriptor.FieldDescriptor.TYPE_SINT64: ("integer", "int64"),
}

# The same vocabulary for Avro's primitive names. `fixed` is a sized byte
# string and reads as `bytes` does.
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
class SchemaLocation:
    """Where one declared type sits in its schema, in the schema's own terms.

    Everything a code generator needs to name the class it produced, and
    nothing that presumes which generator ran: `options` are the file's
    codegen options under the names the schema itself gives them, and
    `declared_names` the type names the file declares at top level — which one
    generator needs to avoid a collision and another may ignore.
    """

    schema_format: Literal["protobuf", "avro"]
    # The schema file's own name (`order.proto`); empty where the format has
    # no file identity of its own, as an Avro record does not.
    file_name: str
    # The schema's package or namespace, as it declares it.
    package: str
    # The nesting path to the type, outermost first: `("OrderRequest",
    # "Line")` for a message declared inside another.
    path: tuple[str, ...]
    options: Mapping[str, object]
    declared_names: frozenset[str]


class GeneratedNaming(Protocol):
    """How a schema type is named once a code generator has compiled it into a
    class.

    Per-language knowledge, which is why it is a seam rather than a function
    here: the interpreter is the one place that understands a schema format,
    and it stays a place that understands no language (ARCHITECTURE §10). The
    implementation lives in the language adapter that owns the naming rules,
    and the composition root wires it in.
    """

    def class_symbol(self, location: SchemaLocation) -> str:
        """The symbol of the generated class a payload of this type travels
        as, in the fact stream's grammar (D00 §5a)."""
        ...


def interpret_descriptors(
    descriptors: Sequence[EmbeddedDescriptorFact], naming: GeneratedNaming
) -> tuple[list[DeclaredShapeFact], list[str]]:
    """Every message and record the payloads declare, and the symbols of the
    payloads that could not be interpreted.

    `naming` names the generated classes compiled-origin shapes are keyed by;
    source-origin shapes compile to no class and are keyed by the schema's own
    full name, so nothing is asked of it for them.

    Output is sorted by symbol and never depends on the order the descriptors
    arrived in (NFR-1): descriptor input order is whatever an artifact walk
    happened to produce, and the fact files are content-hashed.
    """
    shapes: list[DeclaredShapeFact] = []
    failed: list[str] = []
    for fact in descriptors:
        if fact.schema_format == "avro":
            found, unread = _avro_shapes(fact, naming)
            shapes.extend(found)
            failed.extend(unread)
    found, unread = _protobuf_shapes(
        [d for d in descriptors if d.schema_format == "protobuf"], naming
    )
    shapes.extend(found)
    failed.extend(unread)
    return sorted(shapes, key=lambda shape: shape.symbol), sorted(failed)


def _evidence(origin: Origin) -> Literal["compiler", "declared"]:
    """A schema compiled into the artifact was written by a compiler; a schema
    file in the repository is a declaration about what the build ought to
    ship (2G design §3)."""
    return "compiler" if origin == "compiled" else "declared"


# --- protobuf ------------------------------------------------------------


def _protobuf_shapes(
    facts: Sequence[EmbeddedDescriptorFact], naming: GeneratedNaming
) -> tuple[list[DeclaredShapeFact], list[str]]:
    """One pool per origin, not one pool overall: a descriptor file name is
    the path it was compiled from, so the same `order.proto` reaches us from
    both the artifact and the repository. Two files of one name cannot enter
    one pool, and DR-4's compiled-beats-source precedence is applied
    downstream on `schema_name` — which requires both origins to have been
    interpreted.
    """
    shapes: list[DeclaredShapeFact] = []
    failed: list[str] = []
    by_origin: dict[Origin, list[EmbeddedDescriptorFact]] = {}
    for fact in facts:
        by_origin.setdefault(fact.origin, []).append(fact)
    for origin in sorted(by_origin):
        found, unread = _pool_shapes(by_origin[origin], origin, naming)
        shapes.extend(found)
        failed.extend(unread)
    return shapes, failed


def _pool_shapes(
    facts: Sequence[EmbeddedDescriptorFact], origin: Origin, naming: GeneratedNaming
) -> tuple[list[DeclaredShapeFact], list[str]]:
    parsed: dict[str, tuple[descriptor_pb2.FileDescriptorProto, EmbeddedDescriptorFact]] = {}
    failed: list[str] = []
    for fact in facts:
        file_proto = descriptor_pb2.FileDescriptorProto()
        try:
            # Validated, so that a payload which is not base64 at all fails
            # here: the permissive decode drops the offending characters and
            # would hand an empty, perfectly parseable descriptor on.
            file_proto.ParseFromString(base64.b64decode(fact.payload, validate=True))
        except (binascii.Error, DecodeError):
            failed.append(fact.symbol)
            continue
        # First payload wins for a file name repeated within one origin: they
        # are the same file, harvested from two holders of the same artifact.
        parsed.setdefault(file_proto.name, (file_proto, fact))

    pool = descriptor_pool.DescriptorPool()
    added: set[str] = set()
    unbuildable: set[str] = set()
    for name in sorted(parsed):
        _add_file(name, parsed, pool, added, unbuildable, [])
    failed.extend(parsed[name][1].symbol for name in sorted(unbuildable))

    shapes: list[DeclaredShapeFact] = []
    for name in sorted(added):
        document_id = parsed[name][1].document_id
        for message in pool.FindFileByName(name).message_types_by_name.values():
            shapes.extend(_message_shapes(message, origin, document_id, naming))
    return shapes, failed


def _add_file(
    name: str,
    parsed: dict[str, tuple[descriptor_pb2.FileDescriptorProto, EmbeddedDescriptorFact]],
    pool: descriptor_pool.DescriptorPool,
    added: set[str],
    unbuildable: set[str],
    stack: list[str],
) -> bool:
    """Adds one file and, first, everything it imports — the pool's own
    requirement. A file whose imports never arrive is one file's gap, not the
    module's: the rest still resolves."""
    if name in added:
        return True
    if name in unbuildable or name in stack:
        return False
    entry = parsed.get(name)
    if entry is None:
        # An import no payload in this module carries.
        return False
    stack.append(name)
    # Every dependency attempted, not short-circuited, so the outcome does not
    # depend on which import happens to fail first (NFR-1).
    satisfied = [
        _add_file(dependency, parsed, pool, added, unbuildable, stack)
        for dependency in entry[0].dependency
    ]
    stack.pop()
    if all(satisfied):
        try:
            pool.Add(entry[0])
        except (TypeError, KeyError, ValueError):
            # What the pool raises for a file it cannot build — a conflicting
            # definition, or a dependency it disagrees with us about.
            pass
        else:
            added.add(name)
            return True
    unbuildable.add(name)
    return False


def _message_shapes(
    message: descriptor.Descriptor, origin: Origin, document_id: str, naming: GeneratedNaming
) -> list[DeclaredShapeFact]:
    """One shape per message, nested messages included — each its own shape,
    because each is a payload something can send. A map's synthetic entry
    message is not: it is how protobuf spells a map, and a shape for it would
    be a payload nobody sends."""
    if message.GetOptions().map_entry:
        return []
    shapes = [
        DeclaredShapeFact(
            document_id=document_id,
            symbol=_protobuf_symbol(message, origin, naming),
            schema_name=str(message.full_name),
            schema_format="protobuf",
            origin=origin,
            evidence=_evidence(origin),
            fields=[_protobuf_field(field, origin, naming) for field in message.fields],
        )
    ]
    for nested in message.nested_types:
        shapes.extend(_message_shapes(nested, origin, document_id, naming))
    return shapes


def _protobuf_field(
    field: descriptor.FieldDescriptor, origin: Origin, naming: GeneratedNaming
) -> DeclaredFieldFact:
    entry = _map_entry(field)
    held = entry.fields_by_name["value"] if entry is not None else field
    described = _protobuf_element(held, origin, naming)
    collection = entry is not None or field.is_repeated
    # `has_presence` is exactly the set of fields that can be missing: a
    # proto3 scalar materializes its default and a repeated field is empty
    # rather than absent, while `optional`, `oneof` and message fields carry
    # real presence (2G design §3).
    always_present = not field.has_presence
    return DeclaredFieldFact(
        name=field.name,
        # Read, never computed: protoc puts the computed default here and an
        # explicit `json_name` override in the same place, so deriving it
        # would silently disagree with the wire.
        wire_name=field.json_name,
        field_number=field.number,
        wire_type=("map" if entry is not None else "array") if collection else _text(described),
        wire_format=None if collection else _format(described),
        required=always_present,
        nullable=not always_present,
        # proto3 has no field defaults, and 2G design §3 gives the `default`
        # slot to Avro's.
        default=None,
        item=described if collection else None,
        shape_ref=None if collection else _shape_id(described),
        enum_symbols=(
            [value.name for value in held.enum_type.values] if held.enum_type is not None else None
        ),
    )


def _map_entry(field: descriptor.FieldDescriptor) -> descriptor.Descriptor | None:
    """The synthetic entry message behind `map<K,V>`, or None. A map's keys
    are strings on the wire, so only its value type describes the payload."""
    if field.message_type is not None and field.message_type.GetOptions().map_entry:
        return field.message_type
    return None


def _protobuf_element(
    field: descriptor.FieldDescriptor, origin: Origin, naming: GeneratedNaming
) -> dict[str, object]:
    """D01 §5's recursive `{wire_type, wire_format, nullable, shape_id?}`
    descriptor for what one field holds. Elements are never nullable: a
    protobuf collection cannot contain a null."""
    if field.enum_type is not None:
        return {"wire_type": "enum", "wire_format": None, "nullable": False}
    if field.message_type is not None:
        return {
            "wire_type": "object",
            "wire_format": None,
            "nullable": False,
            "shape_id": _protobuf_symbol(field.message_type, origin, naming),
        }
    wire_type, wire_format = _PROTOBUF_SCALARS[field.type]
    return {"wire_type": wire_type, "wire_format": wire_format, "nullable": False}


def _protobuf_symbol(
    message: descriptor.Descriptor, origin: Origin, naming: GeneratedNaming
) -> str:
    """A compiled shape is named by the class the payload actually travels as,
    so it joins the type references the rest of the fact stream carries; a
    schema file compiles to no class, and is named by the schema's own full
    name (2G design §3)."""
    if origin == "source":
        return str(message.full_name)
    return naming.class_symbol(_protobuf_location(message))


def _protobuf_location(message: descriptor.Descriptor) -> SchemaLocation:
    nesting = []
    node: descriptor.Descriptor | None = message
    while node is not None:
        nesting.append(str(node.name))
        node = node.containing_type
    nesting.reverse()
    file = message.file
    return SchemaLocation(
        schema_format="protobuf",
        file_name=str(file.name),
        package=str(file.package),
        path=tuple(nesting),
        # Under the names the descriptor itself gives them: a codegen option
        # is data this module carries, never data it interprets.
        options={option.name: value for option, value in file.GetOptions().ListFields()},
        declared_names=frozenset(
            set(file.message_types_by_name)
            | set(file.enum_types_by_name)
            | set(file.services_by_name)
        ),
    )


# --- avro ----------------------------------------------------------------


@dataclass(frozen=True)
class _AvroReading:
    """One payload being read: the fact it came on, the naming its classes are
    named by, and the shapes found so far — collected as the recursion walks
    into nested records."""

    fact: EmbeddedDescriptorFact
    naming: GeneratedNaming
    shapes: list[DeclaredShapeFact]


def _avro_shapes(
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
    _avro_record(schema, "", reading)
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
            evidence=_evidence(reading.fact.origin),
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
        wire_type=_text(described),
        wire_format=_format(described),
        # A default is what makes a field omittable; a `null` branch is what
        # makes it nullable. Avro states both outright (2G design §3).
        required="default" not in node,
        nullable=bool(described["nullable"]),
        default=_avro_default(node["default"]) if "default" in node else None,
        item=_item(described),
        shape_ref=_shape_id(described),
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


def _text(described: dict[str, object]) -> str:
    return str(described["wire_type"])


def _format(described: dict[str, object]) -> str | None:
    found = described["wire_format"]
    return None if found is None else str(found)


def _item(described: dict[str, object]) -> dict[str, object] | None:
    """What a collection holds, when the described type is one."""
    held = described.get("item")
    return held if isinstance(held, dict) else None


def _shape_id(described: dict[str, object]) -> str | None:
    """The shape an object reference points at, when the described type is
    one."""
    found = described.get("shape_id")
    return None if found is None else str(found)
