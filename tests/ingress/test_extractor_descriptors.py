"""The harvest half of 2G, closed against the interpreter half.

Every assertion here runs the real extractor over the real fixture jar
through the subprocess harness `test_asm_scanner.py` uses — the payload is
whatever protoc and the Avro compiler actually embedded, never a string this
test wrote for itself, which is the only way a constant-pool harvest can be
tested at all.
"""

import json
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.cli.resources import extractor_jar
from sextant.domain.factfile import read_fact_file
from sextant.domain.facts import EmbeddedDescriptorFact
from sextant.ingress.extract.jvm.generated_naming import JvmGeneratedNaming
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.ingress.interpret.descriptors import interpret_descriptors

REPO = Path(__file__).parents[2]
JAR = extractor_jar()
CLASSES = REPO / "fixtures" / "orders-service" / "target" / "classes"

HOLDER = "com/example/orders/proto/OrderProtos#"
COMMON_HOLDER = "com/example/orders/proto/CommonProtos#"
AUDIT_EVENT = "com/example/orders/avro/AuditEvent#"
ORDER_REQUEST = "com/example/orders/proto/OrderProtos$OrderRequest#"


def _scan(tmp_path: Path) -> Path:
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    return tmp_path


def _descriptors(fact_root: Path, relative: str) -> list[EmbeddedDescriptorFact]:
    """Read through `read_fact_file`, never `json.loads`: the schema Task 2
    froze is the contract this task has to hit, so validating the whole file
    against the `Fact` union is what "matches exactly" means — a payload key
    the extractor spelled differently fails here rather than downstream."""
    _, facts = read_fact_file(fact_root / relative)
    return [fact for fact in facts if isinstance(fact, EmbeddedDescriptorFact)]


def test_the_protobuf_holder_carries_the_descriptor_its_messages_do_not(tmp_path: Path):
    """One fact per holder class, not per message (2G design §1). The
    generated message classes reach `GeneratedMessage` and hold no descriptor
    bytes of their own — they call `OrderProtos.getDescriptor()` — so a fact
    emitted from each of them would be four copies of one payload keyed by
    classes that never embedded it."""
    fact_root = _scan(tmp_path)
    proto = fact_root / "com" / "example" / "orders" / "proto"

    [holder] = _descriptors(fact_root, "com/example/orders/proto/OrderProtos.jsonl")
    assert holder.symbol == HOLDER
    assert holder.schema_format == "protobuf"
    # Omitted by the extractor, defaulted by the schema: the artifact that
    # runs is the authority (DR-4), and it is also the common case.
    assert holder.origin == "compiled"
    assert '"origin"' not in (proto / "OrderProtos.jsonl").read_text(encoding="utf-8")

    for message in (
        "OrderProtos$OrderRequest.jsonl",
        "OrderProtos$OrderRequest$Line.jsonl",
        "OrderProtos$OrderRequest$Status.jsonl",
        "OrderProtos$OrderRequest$Builder.jsonl",
    ):
        assert '"embedded_descriptor"' not in (proto / message).read_text(encoding="utf-8")


def test_a_harvested_protobuf_payload_interprets_into_the_shape_it_declares(tmp_path: Path):
    """The whole loop in one assertion: protoc embedded the descriptor, the
    extractor harvested constants without parsing them, and the interpreter
    read `totalAmount` back out. Each half is unfalsifiable alone — a harvest
    with the wrong charset or the wrong constants still produces a plausible
    base64 string, and only a parse of it says so."""
    fact_root = _scan(tmp_path)
    descriptors = [
        *_descriptors(fact_root, "com/example/orders/proto/OrderProtos.jsonl"),
        *_descriptors(fact_root, "com/example/orders/proto/CommonProtos.jsonl"),
    ]
    assert {fact.symbol for fact in descriptors} == {HOLDER, COMMON_HOLDER}

    shapes, failed = interpret_descriptors(descriptors, JvmGeneratedNaming())

    assert failed == []
    [request] = [shape for shape in shapes if shape.symbol == ORDER_REQUEST]
    fields = {field.name: field for field in request.fields}
    assert fields["total_amount"].wire_name == "totalAmount"
    assert fields["count"].wire_name == "explicitCount"
    # The cross-file reference: `common.proto`'s descriptor came from a
    # different class file, and only a pool holding both resolves it.
    assert fields["price"].shape_ref == "com/example/orders/proto/CommonProtos$Money#"


def test_an_avro_record_carries_its_schema_json_verbatim(tmp_path: Path):
    """Avro's payload is the JSON text, never base64 (2G design §1): the
    class embedded a schema a reader can read, and re-encoding it would make
    the fact stream harder to read for nothing. The generated builder embeds
    no schema of its own and must stay silent."""
    fact_root = _scan(tmp_path)

    [record] = _descriptors(fact_root, "com/example/orders/avro/AuditEvent.jsonl")
    assert record.symbol == AUDIT_EVENT
    assert record.schema_format == "avro"
    schema = json.loads(record.payload)
    assert schema["name"] == "AuditEvent"
    assert schema["namespace"] == "com.example.orders.avro"
    assert [field["name"] for field in schema["fields"]] == ["event_id", "actor", "amount"]

    builder = fact_root / "com" / "example" / "orders" / "avro" / "AuditEvent$Builder.jsonl"
    assert '"embedded_descriptor"' not in builder.read_text(encoding="utf-8")


def test_only_the_generated_schema_holders_carry_the_new_fact(tmp_path: Path):
    """Three holders out of the fixture's 77 class files. The other 74 —
    controllers, clients, listeners, and every generated message, builder and
    enum beside them — build `String[]` literals of their own (a
    `FieldAccessorTable`'s field names, an enum's constants), so a harvest
    anchored on the array rather than on the call it feeds would emit payloads
    for them, and the first thing to notice would be a downstream gap."""
    fact_root = _scan(tmp_path)
    holders = {
        fact.symbol
        for path in fact_root.rglob("*.jsonl")
        for fact in _descriptors(fact_root, str(path.relative_to(fact_root)))
    }
    assert holders == {HOLDER, COMMON_HOLDER, AUDIT_EVENT}


def test_the_scanner_reports_the_version_that_harvests_descriptors(tmp_path: Path):
    """A new fact kind that a stale jar does not emit is indistinguishable
    from a module that embeds no schema, so the version is the only thing
    that says which extractor ran."""
    report = AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    assert report.scanner_version == "9.11"
