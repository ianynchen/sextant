"""The one interpreter (2G design §3): embedded schema payloads in,
`declared_shape` facts out.

The `.proto` sources here are copies of the fixture's
(`fixtures/orders-service/src/main/proto`), duplicated on purpose: the
interpreter is a pure function over payloads, and a unit test of it must not
depend on a fixture build having run. The hostile comments are part of the
copy — 2G's spike pinned that comments never reach a descriptor, and a test
whose schema is tidier than the fixture's would stop pinning it.
"""

import base64
from pathlib import Path

from google.protobuf import descriptor_pb2
from grpc_tools import protoc

from sextant.domain.facts import EmbeddedDescriptorFact
from sextant.ingress.extract.jvm.generated_naming import JvmGeneratedNaming
from sextant.ingress.interpret.descriptors import interpret_descriptors

ORDER_PROTO = """// Leading file comment — with unicode: héllo, 中文, emoji 🚀
/* Block comment
   spanning lines with weird chars: <>&"'\\x00-ish \\n literal */
syntax = "proto3";

package sextant.orders;  // trailing comment

import "common.proto";

option java_package = "com.example.orders.proto";  /* another trailing */
option java_outer_classname = "OrderProtos";

// Comment on the message
// with a second line — and a fake directive: option java_package = "evil";
message OrderRequest {
  // comment on a field, containing */ almost-terminators and // nested
  string total_amount = 1;  // trailing: renames to totalAmount on JSON wire
  /* block on field */
  int32 count = 2 [json_name = "explicitCount"];  // explicit override
  sextant.orders.Money price = 3;  // cross-file reference (two-phase pool pin)
  // comment before a nested message
  message Line {
    string sku = 1;  // sku comment
  }
  repeated Line lines = 4;
  map<string, string> tags = 5;
  // enum comment
  enum Status {
    STATUS_UNSPECIFIED = 0;  // zero
    STATUS_OPEN = 1;
  }
  Status status = 6;
  optional string note = 7;  // proto3 optional: nullable
}

message OrderReply {
  string order_id = 1;
}
"""

COMMON_PROTO = """// common types — imported by order.proto
syntax = "proto3";
package sextant.orders;
option java_package = "com.example.orders.proto";
option java_outer_classname = "CommonProtos";

message Money {
  string currency = 1;
  int64 amount_minor = 2;  // renames to amountMinor on the JSON wire
}
"""

AUDIT_AVSC = """{
  "type": "record",
  "name": "AuditEvent",
  "namespace": "com.example.orders.avro",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "actor", "type": ["null", "string"], "default": null},
    {"name": "amount", "type": "long", "default": 0}
  ]
}
"""

PROTOS = {"order.proto": ORDER_PROTO, "common.proto": COMMON_PROTO}

# The generated descriptor-holder class each file's messages are compiled
# into — what the extractor puts on an `embedded_descriptor` fact (2G design
# §1). Deliberately not the message symbols the interpreter derives: the two
# must be allowed to differ, or the derivation is untested.
HOLDERS = {
    "order.proto": "com/example/orders/proto/OrderProtos#",
    "common.proto": "com/example/orders/proto/CommonProtos#",
}

ORDER_REQUEST = "com/example/orders/proto/OrderProtos$OrderRequest#"
ORDER_REPLY = "com/example/orders/proto/OrderProtos$OrderReply#"
LINE = "com/example/orders/proto/OrderProtos$OrderRequest$Line#"
MONEY = "com/example/orders/proto/CommonProtos$Money#"
AUDIT_EVENT = "com/example/orders/avro/AuditEvent#"


def _descriptors_from(tmp_path: Path, *names: str, origin: str = "compiled"):
    """The spike's toolchain, which is the only one: compile with
    `grpc_tools.protoc --descriptor_set_out`, split the set into per-file
    `FileDescriptorProto`s, base64 each — byte for byte what a generated
    class embeds and the extractor harvests."""
    for name in names:
        (tmp_path / name).write_text(PROTOS[name], encoding="utf-8")
    out = tmp_path / "descriptor_set.pb"
    code = protoc.main(["protoc", f"-I{tmp_path}", f"--descriptor_set_out={out}", *names])
    assert code == 0, "the fixture schemas must compile"
    compiled = descriptor_pb2.FileDescriptorSet()
    compiled.ParseFromString(out.read_bytes())
    return [
        EmbeddedDescriptorFact(
            document_id="doc:proto",
            symbol=HOLDERS[file.name],
            schema_format="protobuf",
            payload=base64.b64encode(file.SerializeToString()).decode("ascii"),
            origin=origin,
        )
        for file in compiled.file
    ]


def _avro_descriptor(origin: str = "compiled"):
    return EmbeddedDescriptorFact(
        document_id="doc:avro",
        symbol=AUDIT_EVENT,
        schema_format="avro",
        payload=AUDIT_AVSC,
        origin=origin,
    )


def _interpret(descriptors):
    """The naming seam is injected, never assumed: the interpreter knows
    schema formats and no language, so the platform whose classes a payload
    travels as is the caller's answer (ARCHITECTURE §10)."""
    return interpret_descriptors(descriptors, JvmGeneratedNaming())


def _shape(shapes, symbol):
    found = [shape for shape in shapes if shape.symbol == symbol]
    assert len(found) == 1, f"no single shape for {symbol} in {[s.symbol for s in shapes]}"
    return found[0]


def _fields(shape):
    return {field.name: field for field in shape.fields}


# --- protobuf ------------------------------------------------------------


def test_json_names_are_read_from_the_descriptor_never_computed(tmp_path: Path):
    """`wire_name` is the identity a JSON-encoded protobuf payload carries
    (2G design §3). protoc computes the default and honours an override, so
    reading `json_name` is the whole rule — a re-derivation here would get
    `explicitCount` wrong and nothing would notice."""
    shapes, failed = _interpret(_descriptors_from(tmp_path, "order.proto", "common.proto"))

    assert failed == []
    fields = _fields(_shape(shapes, ORDER_REQUEST))
    assert fields["total_amount"].wire_name == "totalAmount"
    assert fields["count"].wire_name == "explicitCount"
    assert fields["total_amount"].field_number == 1
    assert fields["count"].field_number == 2


def test_every_message_becomes_a_shape_and_nothing_else_does(tmp_path: Path):
    """Nested messages are shapes of their own; the enum is one value on the
    wire (D00 §5b) and the map's synthetic entry message is not a payload
    anyone sends, so neither may appear as a shape."""
    shapes, failed = _interpret(_descriptors_from(tmp_path, "order.proto", "common.proto"))

    assert failed == []
    assert [shape.symbol for shape in shapes] == sorted([ORDER_REPLY, ORDER_REQUEST, LINE, MONEY])
    assert {shape.evidence for shape in shapes} == {"compiler"}
    assert {shape.schema_format for shape in shapes} == {"protobuf"}
    assert {shape.origin for shape in shapes} == {"compiled"}


def test_the_two_origins_of_one_schema_meet_on_schema_name(tmp_path: Path):
    """`symbol` deliberately differs between the origins — one names the class
    a payload travels as, the other the schema — so `schema_name` is the only
    thing DR-4's compiled-beats-source precedence can key on. If these two
    ever disagree, that precedence silently keeps both rows."""
    compiled, _ = _interpret(_descriptors_from(tmp_path, "order.proto", "common.proto"))
    source, _ = _interpret(
        _descriptors_from(tmp_path, "order.proto", "common.proto", origin="source")
    )

    assert sorted(shape.schema_name for shape in compiled) == sorted(
        shape.schema_name for shape in source
    )
    assert _shape(compiled, ORDER_REQUEST).schema_name == "sextant.orders.OrderRequest"
    assert _shape(compiled, LINE).schema_name == "sextant.orders.OrderRequest.Line"


def test_a_cross_file_reference_resolves_through_the_shared_pool(tmp_path: Path):
    """`price` is typed by a message from the imported file. One pool over
    every payload in the module is what makes that a `shape_ref` instead of a
    failure — a per-fact interpreter cannot resolve it at all."""
    shapes, failed = _interpret(_descriptors_from(tmp_path, "order.proto", "common.proto"))

    assert failed == []
    price = _fields(_shape(shapes, ORDER_REQUEST))["price"]
    assert price.wire_type == "object"
    assert price.shape_ref == MONEY
    assert _fields(_shape(shapes, MONEY))["amount_minor"].wire_name == "amountMinor"


def test_types_project_into_the_wire_vocabulary(tmp_path: Path):
    """D00 §5b's vocabulary is the comparison level for DR-5, so a protobuf
    type that is not projected into it cannot be compared with anything."""
    shapes, failed = _interpret(_descriptors_from(tmp_path, "order.proto", "common.proto"))

    assert failed == []
    fields = _fields(_shape(shapes, ORDER_REQUEST))
    assert (fields["total_amount"].wire_type, fields["total_amount"].wire_format) == (
        "string",
        None,
    )
    assert (fields["count"].wire_type, fields["count"].wire_format) == ("integer", "int32")
    money = _fields(_shape(shapes, MONEY))["amount_minor"]
    assert (money.wire_type, money.wire_format) == ("integer", "int64")

    assert fields["status"].wire_type == "enum"
    assert fields["status"].enum_symbols == ["STATUS_UNSPECIFIED", "STATUS_OPEN"]

    assert fields["lines"].wire_type == "array"
    assert fields["lines"].item == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": LINE,
    }

    assert fields["tags"].wire_type == "map"
    assert fields["tags"].item == {"wire_type": "string", "wire_format": None, "nullable": False}


def test_proto3_presence_decides_required_and_nullable(tmp_path: Path):
    """proto3 scalars materialize with a default rather than being absent, so
    calling them optional would misreport every generated payload; `optional`
    and message fields are the ones that can actually be missing, and a
    repeated field is empty, never absent (2G design §3)."""
    shapes, failed = _interpret(_descriptors_from(tmp_path, "order.proto", "common.proto"))

    assert failed == []
    fields = _fields(_shape(shapes, ORDER_REQUEST))
    assert (fields["total_amount"].required, fields["total_amount"].nullable) == (True, False)
    assert (fields["note"].required, fields["note"].nullable) == (False, True)
    assert (fields["price"].required, fields["price"].nullable) == (False, True)
    assert (fields["lines"].required, fields["lines"].nullable) == (True, False)
    assert (fields["tags"].required, fields["tags"].nullable) == (True, False)


def test_a_source_origin_shape_is_named_by_its_schema_full_name(tmp_path: Path):
    """A `.proto` read off disk has no generated class to name (2G design
    §3), and its evidence is what a declaration earns, not what a compiler
    does."""
    shapes, failed = _interpret(
        _descriptors_from(tmp_path, "order.proto", "common.proto", origin="source")
    )

    assert failed == []
    assert [shape.symbol for shape in shapes] == [
        "sextant.orders.Money",
        "sextant.orders.OrderReply",
        "sextant.orders.OrderRequest",
        "sextant.orders.OrderRequest.Line",
    ]
    assert {shape.evidence for shape in shapes} == {"declared"}
    price = _fields(_shape(shapes, "sextant.orders.OrderRequest"))["price"]
    assert price.shape_ref == "sextant.orders.Money"


# --- avro ----------------------------------------------------------------


def test_an_avro_union_is_nullability_and_a_default_is_optionality():
    """Avro states presence outright: a `null` branch is the only thing that
    makes a field nullable, and a default is the only thing that makes it
    omittable (2G design §3)."""
    shapes, failed = _interpret([_avro_descriptor()])

    assert failed == []
    audit = _shape(shapes, AUDIT_EVENT)
    assert audit.schema_format == "avro"
    assert audit.schema_name == "com.example.orders.avro.AuditEvent"
    fields = _fields(audit)
    assert (fields["event_id"].required, fields["event_id"].nullable) == (True, False)
    assert (fields["actor"].required, fields["actor"].nullable) == (False, True)
    assert fields["actor"].wire_type == "string"
    assert (fields["amount"].wire_type, fields["amount"].wire_format) == ("integer", "int64")
    assert fields["amount"].default == "0"
    assert fields["amount"].field_number is None
    assert fields["event_id"].wire_name == "event_id"


def test_a_source_origin_avro_record_is_named_by_its_full_name():
    shapes, failed = _interpret([_avro_descriptor(origin="source")])

    assert failed == []
    assert [shape.symbol for shape in shapes] == ["com.example.orders.avro.AuditEvent"]
    assert [shape.evidence for shape in shapes] == ["declared"]


# --- failure is a gap, never a crash -------------------------------------


def test_an_unparseable_payload_is_a_gap_not_a_crash():
    """The gap payload is the symbol the extractor named, because that is what
    a reader of `descriptors_not_interpreted` has to go and look at."""
    garbage = EmbeddedDescriptorFact(
        document_id="doc:proto",
        symbol="com/example/orders/proto/BrokenProtos#",
        schema_format="protobuf",
        payload="!!! not a descriptor !!!",
        origin="compiled",
    )

    assert _interpret([garbage]) == ([], ["com/example/orders/proto/BrokenProtos#"])

    shapes, failed = _interpret([garbage, _avro_descriptor()])
    assert failed == ["com/example/orders/proto/BrokenProtos#"]
    assert [shape.symbol for shape in shapes] == [AUDIT_EVENT]


def test_a_missing_import_fails_only_the_file_that_needed_it(tmp_path: Path):
    """`order.proto` cannot be resolved without the file it imports. That is
    one file's gap — the rest of the module still interprets, or one absent
    dependency would blank a whole build's shapes."""
    descriptors = _descriptors_from(tmp_path, "order.proto", "common.proto")
    without_common = [d for d in descriptors if d.symbol != HOLDERS["common.proto"]]

    shapes, failed = _interpret([*without_common, _avro_descriptor()])

    assert failed == [HOLDERS["order.proto"]]
    assert [shape.symbol for shape in shapes] == [AUDIT_EVENT]


def test_broken_avro_json_is_a_gap_not_a_crash():
    broken = EmbeddedDescriptorFact(
        document_id="doc:avro",
        symbol="com/example/orders/avro/Broken#",
        schema_format="avro",
        payload="{not json",
        origin="compiled",
    )

    assert _interpret([broken]) == ([], ["com/example/orders/avro/Broken#"])


# --- determinism (NFR-1) -------------------------------------------------


def test_output_does_not_depend_on_the_order_the_descriptors_arrived_in(tmp_path: Path):
    """Two runs that disagree on order are two different answers: the fact
    files are content-hashed, and descriptor input order is whatever the jar
    walk happened to produce."""
    descriptors = [*_descriptors_from(tmp_path, "order.proto", "common.proto"), _avro_descriptor()]

    first, first_failed = _interpret(descriptors)
    second, second_failed = _interpret(list(reversed(descriptors)))

    serialized = [shape.model_dump_json() for shape in first]
    assert serialized == [shape.model_dump_json() for shape in second]
    assert [shape.symbol for shape in first] == sorted(shape.symbol for shape in first)
    assert first_failed == second_failed == []
