"""Quarkus's two gRPC annotations, read through the SHIPPED catalogs (spec
2026-10-24 §1 ruling 3, §3d; probe CP-52, `scripts/probes/cp52_quarkus_grpc_annotations.md`).

`test_supertype_derived.py` pins the corroboration engine and
`test_injected_client.py` the injected-client engine, each over a catalog a
test builds by hand. This file asks the other question: do the catalogs that
SHIP name Quarkus's annotations, in the one dotted spelling CP-52 row 4 reads
them under. A wrong FQN in either is silent (W53's own lesson), so each is
pinned here against the file itself."""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogSource
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.pipeline import resolve
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {
    "call_site",
    "string_constants",
    "annotation_args",
    "typed_signatures",
    "superclass",
}
_MODULE = "sextant-jvm maven com.acme/hello-client 1.0.0 "

QUARKUS_SERVICE = "io/quarkus/grpc/GrpcService#"
QUARKUS_CLIENT = "io/quarkus/grpc/GrpcClient#"
DEVH_CLIENT = "net/devh/boot/grpc/client/inject/GrpcClient#"

OUTER = "com/acme/hello/proto/HelloGrpc#"
BLOCKING_STUB = "com/acme/hello/proto/HelloGrpc$HelloBlockingStub#"
IMPL_BASE = "com/acme/hello/proto/HelloGrpc$HelloImplBase#"
IMPLEMENTOR = "com/acme/hello/HelloService#"
FIELD = "com/acme/hello/Greeter#hello."
SERVICE_NAME = "hello.v1.Hello"


class _Catalogs(CatalogSource):
    def __init__(self, catalogs: list[Catalog]) -> None:
        self._catalogs = catalogs

    def load(self) -> list[Catalog]:
        return self._catalogs


def _shipped(*ids: str) -> list[Catalog]:
    found = {c.id: c for c in YamlCatalogSource(catalogs_dir()).load()}
    return [found[i] for i in ids]


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/hello/Greeter.java",
        module_id="com.acme:hello-client",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _service_name_site() -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=f"{_MODULE}{OUTER}getServiceDescriptor().",
        target=CallTarget(
            owner="io/grpc/ServiceDescriptor#", name="newBuilder", descriptor="(...)V"
        ),
        invoke_kind="static",
        ordinal=0,
        arguments=[CallArgument(kind="string", value=SERVICE_NAME)],
    )


def _injected_field(annotation: str, args: dict[str, object] | None = None) -> list[object]:
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + FIELD,
            construct_kind=ConstructKind.FIELD,
            signature=Signature(returns=TypeRef(symbol=BLOCKING_STUB)),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_MODULE + FIELD,
            use=AnnotationUse(annotation=annotation, args=args or {}),
            retention="RUNTIME",
        ),
    ]


def _implementor(annotation: str | None) -> list[object]:
    """A class extending the generated base, as a module compiled against a
    PUBLISHED stubs jar has it: the extends edge is the module's own fact and
    the generated supertype's facts never arrive, so `grpc-java.yml` derives
    nothing for it."""
    facts: list[object] = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + IMPLEMENTOR,
            construct_kind=ConstructKind.CLASS,
            superclass=_MODULE + IMPL_BASE,
        )
    ]
    if annotation is not None:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=_MODULE + IMPLEMENTOR,
                use=AnnotationUse(annotation=annotation),
                retention="RUNTIME",
            )
        )
    return facts


def _client_rows(tmp_path: Path, facts: list[object]) -> list[dict[str, object]]:
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(
        workspace, _shipped("grpc-quarkus-client"), capabilities=CAPABILITIES
    )
    assert skipped == []
    rows = workspace.query("endpoints")
    workspace.close()
    return rows


# --- the service side: @GrpcService corroborates ----------------------------


@pytest.mark.pins("grpc.the-QUARKUS-service-annotation-corroborates")
def test_a_quarkus_grpc_service_the_supertype_match_missed_becomes_a_question(tmp_path: Path):
    """CP-52 rows 1, 7: Quarkus REQUIRES `@GrpcService` on a service bean, so
    a class that carries it and extends a generated base is a served gRPC
    surface. With the stubs published, no identity is readable — the
    annotation names nothing — so what it earns is the class, as the same
    `service_identity` question the Spring and net.devh spellings file.
    Never a row: the annotation carries no service name."""
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), _implementor(QUARKUS_SERVICE))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(
        workspace,
        tmp_path / "facts",
        _Catalogs(_shipped("grpc-java", "grpc-spring")),
        CAPABILITIES,
    )
    rows = workspace.query("endpoints")
    questions = workspace.query("open_questions")
    workspace.close()

    assert rows == []
    assert [q["question"] for q in questions] == ["service_identity"]
    assert questions[0]["path"] == IMPLEMENTOR
    assert json.loads(str(questions[0]["candidates"]))[0]["class"] == _MODULE + IMPLEMENTOR


# --- the client side: @GrpcClient is an outbound service ---------------------


@pytest.mark.pins("grpc.a-QUARKUS-client-field-is-an-outbound-service")
@pytest.mark.parametrize(
    "args",
    [
        pytest.param({"value": "hello"}, id="named"),
        # CP-52 rows 2, 5: the value OMITTED is the sentinel, and the field's
        # name is the client's. `@GrpcClient("")` is a build error (row 6),
        # so it is not a shape a compiled module has.
        pytest.param({}, id="value-omitted"),
        pytest.param({"value": "<<element name>>"}, id="sentinel-written-out"),
    ],
)
def test_a_quarkus_client_stub_field_derives_one_service_level_outbound_row(
    tmp_path: Path, args: dict[str, object]
):
    """The row `grpc-net-devh` produces for `@GrpcClient("hello")`, whatever
    the client is named: the row's identity is the injected stub's own
    `SERVICE_NAME`, not the injection point's name, so the naming rule does
    not reach the row."""
    rows = _client_rows(tmp_path, [*_injected_field(QUARKUS_CLIENT, args), _service_name_site()])

    assert len(rows) == 1
    row = rows[0]
    assert row["protocol"] == "grpc"
    assert row["direction"] == "outbound"
    assert row["path"] == SERVICE_NAME
    assert row["method"] is None
    assert row["handler"] is None and row["caller"] is None
    assert row["resolution"] == "resolved"


def test_two_quarkus_client_fields_of_one_stub_type_derive_one_row(tmp_path: Path):
    """One named, one value omitted, two injection points of the same stub
    type: one service-level fact, not two (`test_injected_client.py`'s own
    pin for net.devh)."""
    second = "com/acme/hello/Refunder#hello."
    facts = [
        *_injected_field(QUARKUS_CLIENT, {"value": "hello"}),
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + second,
            construct_kind=ConstructKind.FIELD,
            signature=Signature(returns=TypeRef(symbol=BLOCKING_STUB)),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_MODULE + second,
            use=AnnotationUse(annotation=QUARKUS_CLIENT),
            retention="RUNTIME",
        ),
        _service_name_site(),
    ]
    rows = _client_rows(tmp_path, facts)

    assert [row["path"] for row in rows] == [SERVICE_NAME]


@pytest.mark.declines("grpc-quarkus-client")
@pytest.mark.pins("grpc.a-QUARKUS-client-field-is-an-outbound-service")
def test_net_devhs_client_annotation_is_not_a_quarkus_client(tmp_path: Path):
    """Every conjunct of the rule but the annotation's identity: a stub field,
    a readable `SERVICE_NAME`, an annotation of the same simple name from the
    OTHER framework. `grpc-net-devh` owns that spelling; this catalog derives
    nothing from it."""
    assert _client_rows(tmp_path, [*_injected_field(DEVH_CLIENT), _service_name_site()]) == []
