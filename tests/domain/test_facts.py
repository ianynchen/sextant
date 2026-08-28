from pathlib import Path

from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import read_fact_file, write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)

DOCUMENT = Document(
    document_id="doc_1",
    relative_path="src/main/java/com/acme/OrderController.java",
    module_id="com.acme:orders",
    language="java",
    sextant_version="0.1.0",
    fact_schema_version="1.0.0",
    scanner_id="asm",
    scanner_version="9.7",
    content_hash="sha256:abc",
    origin_entry="target/classes",
    origin_tier=OriginTier.MODULE_OUTPUT,
    redaction_set_hash="sha256:def",
)


def test_round_trip_preserves_every_fact_when_written_and_read_back(tmp_path: Path):
    symbol = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        construct=ConstructKind.METHOD,
        enclosing="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#",
        signature=Signature(
            parameters=[Parameter(name="cmd", type=TypeRef(symbol="com/acme/OrderCommand#"))],
            returns=TypeRef(
                symbol="reactor/core/publisher/Mono#",
                arguments=[TypeRef(symbol="com/acme/OrderResult#")],
            ),
        ),
        visibility="public",
        line_start=21,
        line_end=24,
    )
    annotation = AnnotationFact(
        document_id="doc_1",
        target=symbol.symbol,
        use=AnnotationUse(
            annotation="org/springframework/web/bind/annotation/PostMapping#",
            args={"value": ["/v1/orders"]},
        ),
        retention="runtime",
    )
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [symbol, annotation])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [symbol, annotation]
    read_symbol = facts[0]
    assert isinstance(read_symbol, SymbolFact)
    assert read_symbol.signature is not None
    assert read_symbol.signature.returns is not None
    assert read_symbol.signature.returns.arguments == [TypeRef(symbol="com/acme/OrderResult#")]


def test_document_is_the_first_line_when_a_fact_file_is_written(tmp_path: Path):
    path = tmp_path / "OrderController.jsonl"
    write_fact_file(path, DOCUMENT, [])
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert '"kind":"document"' in first_line.replace(" ", "")


def test_written_bytes_are_identical_when_the_same_facts_are_written_twice(tmp_path: Path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_fact_file(a, DOCUMENT, [])
    write_fact_file(b, DOCUMENT, [])
    assert a.read_bytes() == b.read_bytes()
