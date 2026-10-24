"""Tests for the `injected_client` engine (D02 §2's `injected_client` style,
2O design §1c, Task 5).

Facts mirror CP-8's real, checkpoint-recorded call-site shapes exactly
(`scripts/probes/cp3_cp8_grpc_facts.md`) — the `test_supertype_derived.py`
precedent, applied to an `@GrpcClient`-annotated field's own declared stub
type instead of a supertype. Every identity string is invented, the same
`test_schema_operations.py` discipline `test_supertype_derived.py` already
states in full."""

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
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"call_site", "string_constants", "annotation_args", "typed_signatures"}
_MODULE = "sextant-jvm maven com.acme/billing-client 1.0.0 "

GRPC_CLIENT = "net.devh.boot.grpc.client.inject.GrpcClient"
GRPC_CLIENT_SYMBOL = "net/devh/boot/grpc/client/inject/GrpcClient#"
OUTER = "com/acme/billing/proto/BillingServiceGrpc#"
BLOCKING_STUB = "com/acme/billing/proto/BillingServiceGrpc$BillingServiceBlockingStub#"
IMPL_BASE = "com/acme/billing/proto/BillingServiceGrpc$BillingServiceImplBase#"
FIELD = "com/acme/billing/OrderService#billingStub."
SERVICE_NAME = "billing.v1.BillingService"


class _Catalogs(CatalogSource):
    def __init__(self, catalogs: list[Catalog]) -> None:
        self._catalogs = catalogs

    def load(self) -> list[Catalog]:
        return self._catalogs


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/billing/OrderService.java",
        module_id="com.acme:billing-client",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _injected_field(stub_type: str = BLOCKING_STUB, field: str = FIELD) -> list[object]:
    """The one shape `injected_client` matches on: a field's own declared
    type (D00 §5a's typed signature — `Signature.returns`, bare, the
    `single_call._argument_type_identity` precedent) plus the `@GrpcClient`
    annotation on that SAME field, module-prefixed target (D00 §5a)."""
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + field,
            construct_kind=ConstructKind.FIELD,
            signature=Signature(returns=TypeRef(symbol=stub_type)),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_MODULE + field,
            use=AnnotationUse(annotation=GRPC_CLIENT_SYMBOL),
            retention="RUNTIME",
        ),
    ]


def _service_name_site(
    value: str | None = SERVICE_NAME, *, outer: str = OUTER, ordinal: int = 0
) -> CallSiteFact:
    """CP-8(b)'s own `ServiceDescriptor.newBuilder("<protoPackage>.<Service>")`
    call, declared on the stub type's own OUTER generated class."""
    return CallSiteFact(
        document_id="doc_1",
        caller=f"{_MODULE}{outer}getServiceDescriptor().",
        target=CallTarget(
            owner="io/grpc/ServiceDescriptor#", name="newBuilder", descriptor="(...)V"
        ),
        invoke_kind="static",
        ordinal=ordinal,
        arguments=[
            CallArgument(kind="string", value=value)
            if value is not None
            else CallArgument(kind="unresolved")
        ],
    )


def _implementor_facts(
    superclass: str = IMPL_BASE, symbol: str = "com/acme/billing/BillingServiceImpl#"
) -> list[SymbolFact]:
    """A LOCAL class extending the generated base — the fence's own evidence
    (2O design §1c): a module class whose `extends` target shares an OUTER
    CLASS with the injected stub's own type."""
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + symbol,
            construct_kind=ConstructKind.CLASS,
            superclass=_MODULE + superclass,
        )
    ]


def _catalog(
    *, matches: dict[str, object] | None = None, source: str = "test-grpc-net-devh.yml"
) -> Catalog:
    if matches is None:
        matches = {
            "field_annotation": GRPC_CLIENT,
            "identity_marker": {
                "service_name_call": {"owner": "io.grpc.ServiceDescriptor", "method": "newBuilder"}
            },
        }
    return Catalog(
        id="test-grpc-net-devh",
        style="injected_client",
        protocol="grpc",
        direction="outbound",
        requires=("call_site", "string_constants", "annotation_args", "typed_signatures"),
        matches=matches,
        source=Path(source),
    )


def _resolve(tmp_path: Path, facts: list, catalog: Catalog | None = None) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


# --- (a) one service-level outbound row per injected stub ------------------


def test_an_injected_stub_derives_one_service_level_outbound_row(tmp_path: Path):
    facts = [*_injected_field(), _service_name_site()]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["protocol"] == "grpc"
    assert row["direction"] == "outbound"
    assert row["path"] == SERVICE_NAME
    assert row["method"] is None
    assert row["handler"] is None and row["caller"] is None
    assert row["resolution"] == "resolved"


def test_two_fields_injecting_the_same_service_derive_one_row(tmp_path: Path):
    """The identity dedups the same way every other style's does — two
    `@GrpcClient` fields naming the same stub type are one service-level
    fact, not two."""
    facts = [
        *_injected_field(field="com/acme/billing/OrderService#billingStub."),
        *_injected_field(field="com/acme/billing/RefundService#billingStub."),
        _service_name_site(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 1


def _injected_parameter(stub_type: str = BLOCKING_STUB) -> list[object]:
    """`OrderService(@GrpcClient("billing") BillingServiceBlockingStub stub)`:
    net.devh's annotation targets PARAMETER too (`grpc-net-devh.yml`), and the
    extractor records a parameter's annotations on its method's signature
    (D00 §5a)."""
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + "com/acme/billing/OrderService#`<init>`(sig_init).",
            construct_kind=ConstructKind.CONSTRUCTOR,
            signature=Signature(
                parameters=[
                    Parameter(
                        name="stub",
                        type=TypeRef(symbol=stub_type),
                        annotations=[AnnotationUse(annotation=GRPC_CLIENT_SYMBOL)],
                    )
                ]
            ),
        )
    ]


@pytest.mark.pins("injected_client.a-PARAMETER-is-an-injection-point")
def test_an_injected_constructor_parameter_derives_one_service_level_outbound_row(
    tmp_path: Path,
):
    workspace = _resolve(tmp_path, [*_injected_parameter(), _service_name_site()])
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["path"], r["direction"], r["method"], r["resolution"]) for r in rows] == [
        (SERVICE_NAME, "outbound", None, "resolved")
    ]


def test_a_field_and_a_parameter_of_one_stub_type_derive_one_row(tmp_path: Path):
    facts = [*_injected_field(), *_injected_parameter(), _service_name_site()]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert [r["path"] for r in rows] == [SERVICE_NAME]


def test_the_fence_refuses_an_injected_parameter_of_a_service_this_module_implements(
    tmp_path: Path,
):
    facts = [*_injected_parameter(), _service_name_site(), *_implementor_facts()]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert rows == []


def test_an_unreadable_identity_on_a_parameter_files_a_question_naming_the_method(
    tmp_path: Path,
):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), _injected_parameter())
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(workspace, tmp_path / "facts", _Catalogs([_catalog()]), CAPABILITIES)
    [question] = workspace.query("open_questions")
    workspace.close()

    assert question["path"] == BLOCKING_STUB
    candidates = json.loads(str(question["candidates"]))
    assert candidates[0]["class"].startswith(_MODULE + "com/acme/billing/OrderService#")


# --- (b) the fence: no outbound row for a service this module implements ---


def test_the_fence_refuses_an_outbound_row_for_a_service_this_module_implements(tmp_path: Path):
    facts = [*_injected_field(), _service_name_site(), *_implementor_facts()]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert rows == []


def test_the_fence_survives_an_unreadable_stub_identity(tmp_path: Path):
    """The fence is stated by SYMBOL NAME, never by identity (2O design §1c):
    a module implementing a service against PUBLISHED stubs has no local
    `SERVICE_NAME` to read either, so the fence must still fire even when the
    `ServiceDescriptor.newBuilder` call site itself is entirely absent."""
    facts = [*_injected_field(), *_implementor_facts()]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert rows == []


def test_a_different_services_implementer_does_not_fence(tmp_path: Path):
    """The fence is scoped to the SAME outer class — a module implementing
    some OTHER service still derives its own outbound row for a genuinely
    different injected stub."""
    facts = [
        *_injected_field(),
        _service_name_site(),
        *_implementor_facts(
            superclass="com/acme/other/proto/OtherServiceGrpc$OtherServiceImplBase#",
            symbol="com/acme/other/OtherServiceImpl#",
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert [row["path"] for row in rows] == [SERVICE_NAME]


def _generated_descriptor_suppliers(outer: str = OUTER) -> list[SymbolFact]:
    """What protoc-gen-grpc-java ALWAYS emits inside `<Service>Grpc` beside the stubs
    when the messages are full protobuf: a `<Service>BaseDescriptorSupplier` and two
    classes extending it, `<Service>FileDescriptorSupplier` and
    `<Service>MethodDescriptorSupplier` — measured on `quarkus-quickstarts`
    (`grpc-plain-text-quickstart`'s `examples.GreeterGrpc`, `javap`). Two `extends`
    edges whose both ends are nested in the stub's own outer class."""
    base = outer.removesuffix("#") + "$BillingServiceBaseDescriptorSupplier#"
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + base,
            construct_kind=ConstructKind.CLASS,
        ),
        *(
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE
                + outer.removesuffix("#")
                + f"$BillingService{kind}DescriptorSupplier#",
                construct_kind=ConstructKind.CLASS,
                superclass=_MODULE + base,
            )
            for kind in ("File", "Method")
        ),
    ]


@pytest.mark.pins("injected_client.a-GENERATED-class-own-nesting-does-not-fence")
def test_the_generated_classs_own_nested_extends_edges_do_not_fence(tmp_path: Path):
    """A client-only module compiling its own `.proto`: the generated outer class
    carries `FileDescriptorSupplier extends BaseDescriptorSupplier`, an edge INSIDE
    that class, not this module implementing the service. Fenced on it, every
    resolved client row of such a module vanished with no question — measured on a
    copy of `fixtures/orders-quarkus` whose stand-in stub was given the pair."""
    facts = [*_injected_field(), _service_name_site(), *_generated_descriptor_suppliers()]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["path"], r["resolution"]) for r in rows] == [(SERVICE_NAME, "resolved")]


def test_a_genuine_implementer_beside_the_generated_suppliers_is_still_fenced(tmp_path: Path):
    """The bound on the rule above: a module class OUTSIDE the generated outer class
    extending its `ImplBase` still fences, with the generated nesting present."""
    facts = [
        *_injected_field(),
        _service_name_site(),
        *_generated_descriptor_suppliers(),
        *_implementor_facts(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert rows == []


def test_an_implementer_nested_in_its_own_outer_class_still_fences(tmp_path: Path):
    """The rule compares the two ends' OUTER classes, not whether the subclass is
    nested at all: `com/acme/Server$Impl extends …ImplBase` is nested, in the module's
    own `Server`, not in the generated `BillingServiceGrpc`, so it is the module
    implementing the service and still fences."""
    facts = [
        *_injected_field(),
        _service_name_site(),
        *_generated_descriptor_suppliers(),
        *_implementor_facts(symbol="com/acme/Server$Impl#"),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    workspace.close()

    assert rows == []


# --- (c) unreadable identity: unresolved fallback and a filed question -----


def test_an_unresolvable_identity_derives_the_unresolved_fallback_row(tmp_path: Path):
    facts = [*_injected_field()]
    workspace = _resolve(tmp_path, facts)
    [row] = workspace.query("endpoints")
    workspace.close()

    assert row["path"] == BLOCKING_STUB
    assert row["resolution"] == "unresolved"


def test_an_unreadable_identity_files_a_question_rather_than_guessing(tmp_path: Path):
    facts = [*_injected_field()]
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(workspace, tmp_path / "facts", _Catalogs([_catalog()]), CAPABILITIES)
    questions = workspace.query("open_questions")
    workspace.close()

    assert len(questions) == 1
    assert questions[0]["question"] == "service_identity"
    assert questions[0]["path"] == BLOCKING_STUB
    candidates = json.loads(str(questions[0]["candidates"]))
    assert candidates[0]["class"] == _MODULE + FIELD
