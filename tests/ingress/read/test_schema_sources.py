from pathlib import Path
from unittest.mock import patch

import pytest

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.resource_files import list_files
from sextant.ingress.read.avsc import AvscReader
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.proto_source import (
    ProtoSourceReader,
    _leading_string_field,
    _read_varint,
    _split_length_delimited_field,
)
from sextant.ingress.read.yaml_config import YamlConfigReader

REPO = Path(__file__).parents[3]
PROTO_FIXTURE = REPO / "fixtures" / "orders-service" / "src" / "main" / "proto"


def _write(root: Path, name: str, text: str) -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def _read(reader, root: Path, *files: Path, module_id: str = "com.acme:orders"):
    return reader.read(ReadRequest(module_id=module_id, version="1.0.0", files=files, root=root))


# --- AvscReader ------------------------------------------------------------


def test_avsc_reader_accepts_only_the_avsc_extension():
    reader = AvscReader()
    assert reader.accepts("avsc")
    assert not reader.accepts("proto")
    assert not reader.accepts("yml")


def test_avsc_reader_emits_one_source_descriptor_per_file_with_verbatim_payload(tmp_path: Path):
    text = (
        '{"type":"record","name":"Receipt","namespace":"com.example.orders.avro",'
        '"fields":[{"name":"id","type":"string"}]}'
    )
    file = _write(tmp_path, "receipt.avsc", text)
    [(document, facts)] = _read(AvscReader(), tmp_path, file)

    assert not document.partial
    assert document.language == "avro"
    assert len(facts) == 1
    fact = facts[0]
    assert fact.kind == "embedded_descriptor"
    assert fact.schema_format == "avro"
    assert fact.origin == "source"
    # Symbol is namespace+name — display identity only, the interpreter's own
    # schema_name is the real cross-origin join key.
    assert fact.symbol == "com.example.orders.avro.Receipt"
    # Verbatim: the exact file text, not a re-serialized/normalized form.
    assert fact.payload == text
    assert fact.document_id == document.document_id


def test_avsc_reader_symbol_is_bare_name_when_no_namespace_is_declared(tmp_path: Path):
    file = _write(
        tmp_path,
        "bare.avsc",
        '{"type":"record","name":"Bare","fields":[{"name":"x","type":"string"}]}',
    )
    [(_, facts)] = _read(AvscReader(), tmp_path, file)

    assert facts[0].symbol == "Bare"


def test_avsc_reader_degrades_honestly_on_unparseable_json(tmp_path: Path):
    file = _write(tmp_path, "broken.avsc", "not json at all")
    [(document, facts)] = _read(AvscReader(), tmp_path, file)

    assert document.partial
    assert document.partial_reason is not None
    assert facts == []


def test_avsc_reader_degrades_honestly_when_the_schema_declares_no_name(tmp_path: Path):
    file = _write(tmp_path, "nameless.avsc", '{"type":"record","fields":[]}')
    [(document, facts)] = _read(AvscReader(), tmp_path, file)

    assert document.partial
    assert facts == []


# --- ProtoSourceReader -------------------------------------------------


def test_proto_source_reader_accepts_only_the_proto_extension():
    reader = ProtoSourceReader()
    assert reader.accepts("proto")
    assert not reader.accepts("avsc")
    assert not reader.accepts("yml")


def test_proto_source_reader_emits_one_descriptor_per_file_on_task_1s_fixture():
    """`order.proto` imports `common.proto` — both must compile in ONE
    `protoc` invocation for that import to resolve, and this reader's own
    `ReadRequest.files` already carries every `.proto` under the root
    (`group_files_by_reader`'s own partitioning), so both land in one call."""
    files = tuple(sorted(PROTO_FIXTURE.glob("*.proto")))
    pairs = _read(ProtoSourceReader(), PROTO_FIXTURE, *files)

    by_path = {document.relative_path: (document, facts) for document, facts in pairs}
    assert set(by_path) == {"common.proto", "order.proto"}
    for document, facts in by_path.values():
        assert not document.partial
        assert document.language == "proto"
        assert len(facts) == 1
        fact = facts[0]
        assert fact.schema_format == "protobuf"
        assert fact.origin == "source"
        assert fact.document_id == document.document_id
    assert by_path["order.proto"][1][0].symbol == "order.proto"
    assert by_path["common.proto"][1][0].symbol == "common.proto"
    # A real base64 payload of the raw FileDescriptorProto bytes, non-empty
    # and distinct per file (never the whole FileDescriptorSet — 2G design).
    order_payload = by_path["order.proto"][1][0].payload
    common_payload = by_path["common.proto"][1][0].payload
    assert order_payload and common_payload and order_payload != common_payload


def test_proto_source_reader_round_trips_through_the_real_interpreter():
    """Confirms this reader's hand-rolled wire-format split produces bytes
    the real `google.protobuf`-backed interpreter can actually parse — the
    one place a test may import both sides of the confinement boundary,
    since production code never may (test_protobuf_confinement.py)."""
    from sextant.ingress.extract.jvm.generated_naming import JvmGeneratedNaming
    from sextant.ingress.interpret.descriptors import interpret_descriptors

    files = tuple(sorted(PROTO_FIXTURE.glob("*.proto")))
    pairs = _read(ProtoSourceReader(), PROTO_FIXTURE, *files)
    descriptors = [fact for _, facts in pairs for fact in facts]

    shapes, failed = interpret_descriptors(descriptors, JvmGeneratedNaming())

    assert failed == []
    names = {shape.schema_name for shape in shapes}
    # 2O Task 4: `order.proto`'s new `service OrderService` block adds two
    # `role: operation` shapes beside the four message ones above — the same
    # `.proto` files, read source-origin this time, so the service reaches
    # the interpreter here too.
    assert names == {
        "sextant.orders.Money",
        "sextant.orders.OrderRequest",
        "sextant.orders.OrderRequest.Line",
        "sextant.orders.OrderReply",
        "sextant.orders.OrderService/GetOrder",
        "sextant.orders.OrderService/StreamOrders",
    }
    assert all(shape.origin == "source" for shape in shapes)


def test_a_broken_proto_fails_every_file_in_its_own_root_only(tmp_path: Path):
    broken_root = tmp_path / "broken"
    broken = _write(broken_root, "broken.proto", 'syntax = "proto3";\nmessage Foo { nope }\n')
    ok_in_broken_root = _write(
        broken_root, "ok.proto", 'syntax = "proto3";\nmessage Bar { string x = 1; }\n'
    )
    healthy_root = tmp_path / "healthy"
    healthy = _write(
        healthy_root, "healthy.proto", 'syntax = "proto3";\nmessage Baz { string y = 1; }\n'
    )

    reader = ProtoSourceReader()
    broken_pairs = _read(reader, broken_root, broken, ok_in_broken_root)
    healthy_pairs = _read(reader, healthy_root, healthy)

    # Every file sharing the broken root's one protoc invocation fails,
    # including the syntactically valid sibling — no exception escapes.
    assert len(broken_pairs) == 2
    for document, facts in broken_pairs:
        assert document.partial
        assert document.partial_reason is not None
        assert facts == []

    # A different root's own reader call is a separate protoc invocation —
    # genuinely unaffected.
    [(healthy_document, healthy_facts)] = healthy_pairs
    assert not healthy_document.partial
    assert len(healthy_facts) == 1


def test_a_broken_protoc_output_fails_the_root_cleanly_no_exception_escapes(tmp_path: Path):
    """IMPORTANT C: `read()` must not let an exception escape even when
    protoc itself succeeds but this reader's own wire-format read of its
    output cannot make sense of it. protoc only ever emits well-formed
    output, so the failure is induced directly on the parsing step rather
    than through a crafted `.proto` file — this is what `read()`'s own
    try/except around the wire-format read (module docstring) is actually
    for."""
    file = _write(tmp_path, "ok.proto", 'syntax = "proto3";\nmessage Bar { string x = 1; }\n')

    with patch(
        "sextant.ingress.read.proto_source._split_length_delimited_field",
        side_effect=ValueError("boom"),
    ):
        [(document, facts)] = _read(ProtoSourceReader(), tmp_path, file)

    assert document.partial
    assert document.partial_reason is not None
    assert "boom" in document.partial_reason
    assert facts == []


# --- Direct wire-format parser tests (IMPORTANT C) --------------------------


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def test_read_varint_decodes_a_single_byte_value():
    assert _read_varint(b"\x05", 0) == (5, 1)


def test_read_varint_decodes_a_multi_byte_value():
    value = 300  # exceeds one byte's 7-bit payload — exercises the continuation bit
    assert _read_varint(_varint(value), 0) == (value, 2)


def test_read_varint_raises_cleanly_on_a_truncated_varint():
    # Continuation bit set on the final byte, no byte follows it.
    with pytest.raises(IndexError):
        _read_varint(b"\x80", 0)


def test_split_length_delimited_field_reads_a_two_byte_length_descriptor():
    payload = b"x" * 200  # length 200 > 127, so the length varint itself is 2 bytes
    chunk = b"\x0a" + _varint(200) + payload
    assert _split_length_delimited_field(chunk, 1) == [payload]


def test_split_length_delimited_field_raises_cleanly_on_a_truncated_final_chunk():
    chunk = b"\x0a" + _varint(10) + b"abc"  # declares length 10, provides 3 bytes
    with pytest.raises(ValueError, match="truncated"):
        _split_length_delimited_field(chunk, 1)


def test_split_length_delimited_field_raises_cleanly_on_unexpected_tag_input():
    # Field 2 (tag 0x12), never field 1 (0x0a) — not the one shape a
    # FileDescriptorSet ever carries (module docstring); no wire type is
    # guessed, so this must raise rather than desync silently.
    chunk = b"\x12" + _varint(3) + b"abc"
    with pytest.raises(ValueError, match="unexpected field"):
        _split_length_delimited_field(chunk, 1)


def test_leading_string_field_raises_cleanly_on_a_truncated_value():
    chunk = b"\x0a" + _varint(10) + b"abc"  # declares length 10, provides 3 bytes
    with pytest.raises(ValueError, match="truncated"):
        _leading_string_field(chunk, 1)


def test_leading_string_field_returns_none_for_a_non_matching_leading_field():
    chunk = b"\x12" + _varint(3) + b"abc"
    assert _leading_string_field(chunk, 1) is None


# --- Registry coexistence ---------------------------------------------------


def test_schema_readers_coexist_with_config_readers_without_claiming_config_extensions(
    tmp_path: Path,
):
    properties_file = _write(tmp_path, "application.properties", "a=1\n")
    yaml_file = _write(tmp_path, "application.yml", "a: 1\n")
    avsc_file = _write(tmp_path, "schema.avsc", '{"type":"record","name":"X","fields":[]}')
    proto_file = _write(tmp_path, "schema.proto", 'syntax = "proto3";\nmessage X {}\n')

    readers = [PropertiesReader(), YamlConfigReader(), AvscReader(), ProtoSourceReader()]
    grouped = group_files_by_reader(
        list_files(tmp_path, tmp_path, IgnoreRules.load(tmp_path)), readers
    )

    by_reader = {type(reader).__name__: owned for reader, owned in grouped}
    assert by_reader["PropertiesReader"] == (properties_file,)
    assert by_reader["YamlConfigReader"] == (yaml_file,)
    assert by_reader["AvscReader"] == (avsc_file,)
    assert by_reader["ProtoSourceReader"] == (proto_file,)
