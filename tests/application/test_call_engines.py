"""Tests for the `single_call` engine (D02 §2's `single_call` style) and the
shared call-payload helpers it and Task 11's `fluent` engine both use.

Facts are hand-built to mirror the *real* emitted grammar exactly — verified
against a live scan of `fixtures/orders-service`'s `BillingRestTemplate`
during this task's checkpoint — rather than compiling and scanning real
bytecode, so each behaviour is isolated and fast."""

import json
from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.shapes.contracts import split_url
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS_DIR = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
CAPABILITIES = {"call_site", "string_constants"}

RESTTEMPLATE = "org/springframework/web/client/RestTemplate#"
ORDER_VIEW = "com/acme/orders/contracts/OrderView#"
ORDER_REQUEST = "com/acme/orders/contracts/OrderRequest#"


def _catalog() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "spring-resttemplate")


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/http/Client.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _resolve(tmp_path: Path, facts: list, catalog: Catalog | None = None):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


# --- 1. getForObject, a string url and a class-literal response -----------


def test_a_string_url_and_a_class_literal_response_derive_a_resolved_endpoint(
    tmp_path: Path,
):
    caller = "com/acme/http/Client#getBalance()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[
                CallArgument(kind="string", value="/billing/balances/{id}"),
                CallArgument(kind="class", symbol=ORDER_VIEW),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("GET", "/billing/balances/{id}")
    assert endpoint["direction"] == "outbound"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None
    assert endpoint["peer"] is None
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }
    assert endpoint["request_shape"] is None


# --- 2. exchange: an enum verb, the HttpEntity hop, and the PTR response --


def _batch_facts(caller: str) -> list:
    return [
        # new OrderRequest()
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(owner=ORDER_REQUEST, name="<init>", descriptor="()V"),
            invoke_kind="special",
            ordinal=0,
            receiver=8,
            result=None,
            arguments=[],
        ),
        # new HttpEntity<>(orderRequest)
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner="org/springframework/http/HttpEntity#",
                name="<init>",
                descriptor="(Ljava/lang/Object;)V",
            ),
            invoke_kind="special",
            ordinal=1,
            receiver=6,
            result=None,
            arguments=[CallArgument(kind="instance", source=8, symbol=ORDER_REQUEST)],
        ),
        # new ParameterizedTypeReference<List<OrderView>>() {}
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner="com/acme/http/Client$1#",
                name="<init>",
                descriptor="(Lcom/acme/http/Client;)V",
            ),
            invoke_kind="special",
            ordinal=2,
            receiver=12,
            result=None,
            arguments=[CallArgument(kind="unresolved")],
        ),
        # restTemplate.exchange(url, HttpMethod.POST, entity, ptr)
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="exchange",
                descriptor=(
                    "(Ljava/lang/String;Lorg/springframework/http/HttpMethod;"
                    "Lorg/springframework/http/HttpEntity;"
                    "Lorg/springframework/core/ParameterizedTypeReference;"
                    "[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;"
                ),
            ),
            invoke_kind="virtual",
            ordinal=3,
            receiver=3,
            result=18,
            arguments=[
                CallArgument(kind="string", value="/billing/batch"),
                CallArgument(kind="enum", symbol="org/springframework/http/HttpMethod#POST."),
                CallArgument(
                    kind="instance", source=6, symbol="org/springframework/http/HttpEntity#"
                ),
                CallArgument(kind="instance", source=12, symbol="com/acme/http/Client$1#"),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]


def _ptr_symbol_fact() -> SymbolFact:
    """The anonymous PTR subclass's own symbol fact: its declared generic
    supertype names the payload (D00 §5a; D02 §2h)."""
    return SymbolFact(
        document_id="doc_1",
        symbol="com/acme/http/Client$1#",
        construct_kind="class",
        supertype=TypeRef(
            symbol="org/springframework/core/ParameterizedTypeReference#",
            nullable=True,
            nullable_resolution="resolved",
            wire_type="object",
            wire_format="",
            arguments=[
                TypeRef(
                    symbol="java/util/List#",
                    nullable=True,
                    nullable_resolution="resolved",
                    wire_type="array",
                    wire_format="",
                    arguments=[
                        TypeRef(
                            symbol=ORDER_VIEW,
                            nullable=True,
                            nullable_resolution="resolved",
                            wire_type="object",
                            wire_format="",
                        )
                    ],
                )
            ],
        ),
    )


def test_exchange_resolves_the_enum_verb_the_http_entity_hop_and_the_ptr_response(
    tmp_path: Path,
):
    caller = "com/acme/http/Client#batchSettlements()."
    facts = [*_batch_facts(caller), _ptr_symbol_fact()]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("POST", "/billing/batch")
    assert endpoint["resolution"] == "resolved"
    # The HttpEntity one-hop: the linked constructor's own payload_ctor_arg
    # (0) is the OrderRequest instance built inline.
    assert json.loads(endpoint["request_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_REQUEST,
    }
    # The PTR follow: the anonymous subclass's own declared supertype names
    # List<OrderView>, fed to expansion._described exactly as a field
    # reference — the array-ness survives, and the item roots OrderView.
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "array",
        "wire_format": "",
        "nullable": True,
        "item": {
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "shape_id": ORDER_VIEW,
        },
    }


# --- 3. a variable url: the row still derives, unresolved -----------------


def test_a_variable_url_still_derives_the_row_unresolved(tmp_path: Path):
    caller = "com/acme/http/Client#removeSomething()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="delete",
                descriptor="(Ljava/lang/String;[Ljava/lang/Object;)V",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=None,
            arguments=[CallArgument(kind="unresolved")],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    # "This method calls something over HTTP" is true and useful on its own
    # (D02 §2): the row derives even though the template could not be read.
    assert endpoint["method"] == "DELETE"
    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"


# --- 4. two identical calls in one method dedup to one row ----------------


def test_two_identical_calls_in_one_method_dedup_to_one_row(tmp_path: Path):
    caller = "com/acme/http/Client#getBalanceTwice()."

    def _call(ordinal: int, receiver: int, result: int) -> CallSiteFact:
        return CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=ordinal,
            receiver=receiver,
            result=result,
            arguments=[
                CallArgument(kind="string", value="/billing/duplicate"),
                CallArgument(kind="class", symbol=ORDER_VIEW),
                CallArgument(kind="unresolved"),
            ],
        )

    facts = [_call(0, 3, 12), _call(1, 3, 15)]
    workspace = _resolve(tmp_path, facts)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "/billing/duplicate"]
    workspace.close()

    assert len(rows) == 1


# --- The shared url split (CP-2), unit-tested directly ---------------------


def test_split_url_reads_an_absolute_url_as_peer_and_path():
    assert split_url("http://billing.internal/v1/invoices") == (
        "billing.internal",
        "/v1/invoices",
    )


def test_split_url_leaves_a_relative_url_path_only_with_no_peer():
    assert split_url("/billing/settlements/{id}") == (None, "/billing/settlements/{id}")


def test_split_url_reads_an_absolute_url_with_no_path_as_an_empty_path():
    assert split_url("https://billing.internal") == ("billing.internal", "")
