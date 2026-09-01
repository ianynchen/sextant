"""`.proto` protobuf schema source files (2G design §2). A schema root's
files compile together, in ONE `grpc_tools.protoc` invocation per
`ReadRequest` — a proto's imports can name a sibling file in the same root
(Task 1's fixture: `order.proto` imports `common.proto`), so a per-file
invocation would not resolve them, and a syntax error in any one file fails
the whole invocation, which is why a broken proto takes every file in its
root down with it rather than only itself.

The only module besides `ingress.interpret.descriptors` allowed to reach a
protobuf-related runtime (`test_protobuf_confinement.py`'s `PROTO_READER`
allowlist entry) — `grpc_tools` compiles the schema text here; reading the
compiled result with `google.protobuf` is the interpreter's confinement
alone, never this reader's (2G design §3: a reader never interprets). So the
raw `FileDescriptorSet` bytes this reader's own protoc run produces are split
into their per-file `FileDescriptorProto` entries by hand, directly off the
wire format (`_split_length_delimited_field`/`_leading_string_field` below)
rather than by importing `google.protobuf` to parse them.

This is safe only because both messages read here have a fixed, narrow
shape, never a general one: `FileDescriptorSet` declares exactly one field
(`file`, repeated, always wire type 2 — so every top-level entry is this
shape, nothing else to skip or understand), and `FileDescriptorProto.name`
(field 1) is always the very first field protoc serializes — the lowest
field number the message declares, and protoc's own serializer always writes
fields in ascending number order. Neither claim generalizes to reading an
arbitrary protobuf message; nothing here ever asks a third question."""

import base64
import subprocess
import sys
import tempfile
from pathlib import Path

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import Document, EmbeddedDescriptorFact, Fact
from sextant.ingress.read import build_document


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """One protobuf varint starting at `offset`: its value, and the offset
    just past it."""
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        if not byte & 0x80:
            return result, offset
        shift += 7


def _split_length_delimited_field(data: bytes, field_number: int) -> list[bytes]:
    """Every length-delimited value carried at `field_number` in `data`,
    read directly off the wire. Safe for a `FileDescriptorSet`, whose only
    field is `file` (repeated message, field 1, see the module docstring) —
    every top-level entry in `data` is this one shape."""
    tag = (field_number << 3) | 2
    chunks = []
    offset = 0
    while offset < len(data):
        read_tag, offset = _read_varint(data, offset)
        length, offset = _read_varint(data, offset)
        value = data[offset : offset + length]
        offset += length
        if read_tag == tag:
            chunks.append(value)
    return chunks


def _leading_string_field(data: bytes, field_number: int) -> str | None:
    """The value of `field_number` when it is the very first field `data`
    serializes — true for `FileDescriptorProto.name` alone (module
    docstring). Never a general field scan: nothing else in `data` is ever
    read."""
    if not data:
        return None
    tag, offset = _read_varint(data, 0)
    if tag != ((field_number << 3) | 2):
        return None
    length, offset = _read_varint(data, offset)
    return data[offset : offset + length].decode("utf-8")


class ProtoSourceReader:
    """Keyed by extension `proto` (M03)."""

    def accepts(self, file_kind: str) -> bool:
        return file_kind == "proto"

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        if not request.files:
            return []
        relative = [file.relative_to(request.root).as_posix() for file in request.files]
        with tempfile.TemporaryDirectory() as tmp:
            descriptor_set = Path(tmp) / "descriptors.bin"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "grpc_tools.protoc",
                    f"-I{request.root}",
                    f"--descriptor_set_out={descriptor_set}",
                    *relative,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                # protoc compiles the whole invocation or none of it: a
                # syntax error anywhere in this root fails every file in it,
                # never only the offending one — no `embedded_descriptor`
                # fact for any of them, and no exception escapes (D00 §5c's
                # "a reader degrades honestly").
                reason = f"protoc failed: {completed.stderr.strip()}"
                return [
                    (
                        build_document(
                            file=file,
                            root=request.root,
                            module_id=request.module_id,
                            language="proto",
                            content=file.read_bytes(),
                            partial=True,
                            partial_reason=reason,
                        ),
                        [],
                    )
                    for file in request.files
                ]
            raw = descriptor_set.read_bytes()

        by_name = {
            _leading_string_field(chunk, 1): chunk
            for chunk in _split_length_delimited_field(raw, 1)
        }
        pairs: list[tuple[Document, list[Fact]]] = []
        for file, name in zip(request.files, relative):
            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language="proto",
                content=file.read_bytes(),
            )
            fact = EmbeddedDescriptorFact(
                document_id=document.document_id,
                # The schema file's own path-derived identity, protoc's own
                # canonical name for it (relative to `-I`) — display identity
                # only, never the cross-origin join key
                # (`DeclaredShapeFact.schema_name` is that).
                symbol=name,
                schema_format="protobuf",
                payload=base64.b64encode(by_name[name]).decode("ascii"),
                origin="source",
            )
            pairs.append((document, [fact]))
        return pairs
