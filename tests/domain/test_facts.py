import json
from pathlib import Path

from pydantic import TypeAdapter

from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import read_fact_file, write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Fact,
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
        construct_kind=ConstructKind.METHOD,
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


# Captured verbatim from a real `AsmScanner` run over `fixtures/orders-service`
# (2026-08-29, field `com/acme/orders/contracts/OrderRequest#note2.`): a
# Java `Optional<String>` field, carrying the 2B wire projection at every
# level of the type reference, plus the always-written field modifiers.
REAL_2B_FIELD_FACT = {
    "kind": "symbol",
    "document_id": "a2a6ad837af392e9c1163ded272cf3f128b73b0c1d5fe5b22510456e207e500d",
    "symbol": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#note2.",
    "construct_kind": "field",
    "enclosing": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#",
    "modifiers": {"static": False, "transient": False},
    "signature": {
        "returns": {
            "symbol": "java/util/Optional#",
            "arguments": [
                {
                    "symbol": "java/lang/String#",
                    "arguments": [],
                    "wire_type": "string",
                    "wire_format": "",
                    "nullable": True,
                    "nullable_resolution": "resolved",
                }
            ],
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "nullable_resolution": "resolved",
        }
    },
    "visibility": "public",
    "line_start": 0,
    "line_end": 0,
}

# Captured verbatim from the same run, field
# `com/acme/orders/contracts/OrderRequest#cachedSummary.` — a `transient`
# field, so `modifiers.transient` is `true` rather than the all-`false`
# default above.
REAL_2B_TRANSIENT_FIELD_FACT = {
    **REAL_2B_FIELD_FACT,
    "symbol": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#cachedSummary.",
    "modifiers": {"static": False, "transient": True},
    "signature": {
        "returns": {
            "symbol": "java/lang/String#",
            "arguments": [],
            "wire_type": "string",
            "wire_format": "",
            "nullable": True,
            "nullable_resolution": "resolved",
        }
    },
}

# Captured verbatim from the same run, the annotation fact for
# `@org.jspecify.annotations.Nullable` on that same `note` field — a
# type-use annotation, so it carries `type_path`.
REAL_2B_ANNOTATION_FACT = {
    "kind": "annotation",
    "document_id": "a2a6ad837af392e9c1163ded272cf3f128b73b0c1d5fe5b22510456e207e500d",
    "target": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#note.",
    "use": {"annotation": "org/jspecify/annotations/Nullable#", "args": {}},
    "retention": "runtime",
    "type_path": "",
}


def test_a_real_2b_field_fact_validates_into_symbol_fact_without_loss():
    # The real extractor's JSON omits default-valued keys (`parameters: []`,
    # `supertype: null`) that a fresh model_dump would include, so this checks
    # the wire projection round-trips rather than comparing the whole dict.
    fact = SymbolFact.model_validate(REAL_2B_FIELD_FACT)
    dumped = fact.model_dump(mode="json")

    assert fact.modifiers == {"static": False, "transient": False}
    assert dumped["signature"] == {
        "parameters": [],
        "returns": REAL_2B_FIELD_FACT["signature"]["returns"],  # type: ignore[index]
    }


def test_a_real_2b_transient_field_fact_keeps_its_modifiers_without_loss():
    fact = SymbolFact.model_validate(REAL_2B_TRANSIENT_FIELD_FACT)

    assert fact.modifiers == {"static": False, "transient": True}
    assert fact.model_dump(mode="json")["signature"] == {
        "parameters": [],
        "returns": REAL_2B_TRANSIENT_FIELD_FACT["signature"]["returns"],  # type: ignore[index]
    }


def test_a_real_2b_annotation_fact_keeps_its_type_path_without_loss():
    fact = AnnotationFact.model_validate(REAL_2B_ANNOTATION_FACT)

    assert fact.type_path == ""
    assert fact.model_dump(mode="json") == REAL_2B_ANNOTATION_FACT


def test_an_older_hand_built_symbol_fact_still_validates_without_the_2b_fields():
    # Pre-2B fact files never wrote wire_type/wire_format/nullable/modifiers/
    # supertype at all — the new fields must default rather than reject.
    fact = SymbolFact.model_validate(
        {
            "kind": "symbol",
            "document_id": "doc_1",
            "symbol": "sextant-jvm maven com.acme/orders 1.0 com/acme/Order#name.",
            "construct_kind": "field",
        }
    )
    assert fact.modifiers == {}
    assert fact.supertype is None
    assert fact.signature is None
    assert fact.interfaces == []


def test_a_class_symbol_lists_its_implemented_interfaces_in_declaration_order():
    # `implemented_interfaces`: erased interface symbols, in the order the
    # class declares them (D00 §5a) — round-trips like `supertype` above.
    fact = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/orders/messaging/raw/RawPubSubReceiver#",
        construct_kind=ConstructKind.CLASS,
        interfaces=["com/google/cloud/pubsub/v1/MessageReceiver#"],
    )

    dumped = fact.model_dump(mode="json")
    reloaded = SymbolFact.model_validate(dumped)

    assert reloaded.interfaces == ["com/google/cloud/pubsub/v1/MessageReceiver#"]


def test_a_class_symbol_carries_its_generic_supertype_as_a_type_reference():
    # D00 §5a's PTR carrier: `new ParameterizedTypeReference<List<OrderView>>() {}`.
    supertype = TypeRef(
        symbol="org/springframework/core/ParameterizedTypeReference#",
        arguments=[
            TypeRef(symbol="java/util/List#", arguments=[TypeRef(symbol="com/acme/OrderView#")])
        ],
    )
    fact = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderView$1#",
        construct_kind=ConstructKind.CLASS,
        supertype=supertype,
    )

    dumped = fact.model_dump(mode="json")
    reloaded = SymbolFact.model_validate(dumped)

    assert reloaded.supertype == supertype


def test_call_site_fact_round_trips_through_model_dump_and_validate():
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(
            owner="org/springframework/web/client/RestTemplate#",
            name="postForObject",
            descriptor="(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;",
        ),
        invoke_kind="virtual",
        ordinal=14,
        receiver=3,
        result=7,
        arguments=[
            CallArgument(kind="string", value="/billing/invoices"),
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="class", symbol="com/acme/orders/contracts/OrderView#"),
        ],
    )

    dumped = call_site.model_dump(mode="json")
    reloaded = TypeAdapter(Fact).validate_python(dumped)

    assert reloaded == call_site
    assert isinstance(reloaded, CallSiteFact)


def test_call_site_fact_survives_a_fact_file_round_trip(tmp_path: Path):
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(owner="java/lang/RuntimeException#", name="<init>", descriptor="()V"),
        invoke_kind="throw",
        ordinal=2,
    )
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [call_site])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [call_site]


def test_call_site_fact_kind_literal_serialises_as_call_site():
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(
            owner="java/lang/Object#", name="toString", descriptor="()Ljava/lang/String;"
        ),
        invoke_kind="virtual",
        ordinal=0,
    )
    assert json.loads(call_site.model_dump_json())["kind"] == "call_site"
