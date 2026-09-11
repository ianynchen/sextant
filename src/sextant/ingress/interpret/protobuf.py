"""The protobuf branch of the one interpreter (2G design §3). The only module
in the system that reads a protobuf descriptor, which is what
`tests/architecture/test_protobuf_confinement.py` enforces.

Protobuf is read **two-phase and module-wide**, because descriptors import one
another: a field's type and its `json_name` may live in an imported file, so
phase one collects every payload and phase two adds them to one
`DescriptorPool` dependency-first. A per-payload interpreter would fail on
every multi-file schema.
"""

import base64
import binascii
from collections.abc import Sequence

# The protobuf runtime's `FieldDescriptor.label` is gone in 7.x — presence and
# repeatedness are read as `has_presence`/`is_repeated` below — which is what
# the `>=` floor in pyproject.toml is holding.
from google.protobuf import descriptor, descriptor_pb2, descriptor_pool
from google.protobuf.message import DecodeError

from sextant.domain.facts import (
    DeclaredFieldFact,
    DeclaredShapeFact,
    EmbeddedDescriptorFact,
    OperationRecord,
)
from sextant.ingress.interpret.wire import (
    GeneratedNaming,
    Origin,
    SchemaLocation,
    evidence_for,
    shape_ref_of,
    wire_format_of,
    wire_type_of,
)

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


def protobuf_shapes(
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
        if not file_proto.name:
            # Protobuf parses leniently, so bytes that are not a descriptor at
            # all can still yield an empty message. No file name means no
            # file: reported, because a payload that produces neither a shape
            # nor a gap is an omission dressed as success (D00 §3).
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
        file = pool.FindFileByName(name)
        for message in file.message_types_by_name.values():
            shapes.extend(_message_shapes(message, origin, document_id, naming))
        for service in file.services_by_name.values():
            shapes.extend(_service_shapes(service, origin, document_id))
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
            evidence=evidence_for(origin),
            fields=[_protobuf_field(field, origin, naming) for field in message.fields],
        )
    ]
    for nested in message.nested_types:
        shapes.extend(_message_shapes(nested, origin, document_id, naming))
    return shapes


def _service_shapes(
    service: descriptor.ServiceDescriptor, origin: Origin, document_id: str
) -> list[DeclaredShapeFact]:
    """One `declared_shape` per RPC method (2O design §1a): the operation IS
    the shape, the same ruling `wsdl_xsd.py` already applies to a SOAP input
    wrapper element — so there is no per-message-field iteration here, only
    one shape per method the `service` block itself declares.

    Unlike a message, whose generated class IS what `symbol` names for a
    compiled origin, an RPC method travels as no class of its own — the
    `<Service>Grpc` stub CP-4/Task 5 names is per-language codegen knowledge
    this interpreter does not have (ARCHITECTURE §10's confinement rule), and
    naming it is Task 5's to do, from bytecode. `symbol` is therefore the
    schema's own full identity for every origin, exactly `schema_name`'s own
    value — the same identity `wsdl_xsd.py`'s `_add_shape` already gives a
    schema-only fact, because there is no second naming for `schema_name` to
    bridge here either.

    `input_ref`/`output_ref` are the descriptor's own fully-qualified message
    names — `full_name` never carries a leading `.`, so there is no FQN
    spelling to strip — an intra-descriptor join to the SAME file's message
    shapes, the ones `_message_shapes` above derives from this exact pool
    (2O design §1a: never a guess across universes)."""
    shapes = []
    for method in service.methods:
        identity = f"{service.full_name}/{method.name}"
        shapes.append(
            DeclaredShapeFact(
                document_id=document_id,
                symbol=identity,
                schema_name=identity,
                schema_format="protobuf",
                origin=origin,
                evidence=evidence_for(origin),
                role="operation",
                operation=OperationRecord(
                    input_ref=str(method.input_type.full_name),
                    output_ref=str(method.output_type.full_name),
                    client_streaming=method.client_streaming,
                    server_streaming=method.server_streaming,
                ),
            )
        )
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
        wire_type=("map" if entry is not None else "array")
        if collection
        else wire_type_of(described),
        wire_format=None if collection else wire_format_of(described),
        required=always_present,
        nullable=not always_present,
        # proto3 has no field defaults, and 2G design §3 gives the `default`
        # slot to Avro's.
        default=None,
        item=described if collection else None,
        shape_ref=None if collection else shape_ref_of(described),
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
