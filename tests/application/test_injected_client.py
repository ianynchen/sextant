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

from sextant.application.ports.catalogs import Catalog, CatalogError, CatalogSource
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
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
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


def _injected_field(
    stub_type: str = BLOCKING_STUB, field: str = FIELD, *, annotation: str = GRPC_CLIENT_SYMBOL
) -> list[object]:
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
            use=AnnotationUse(annotation=annotation),
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


# --- (d) Quarkus's Mutiny client forms (spec 2026-10-25 §2a, §3a, §3b; CP-53)
#
# These run the SHIPPED `grpc-quarkus-client.yml`, so a wrong FQN in it fails
# here. The class names are the shapes measured in `quarkus-quickstarts`'
# `grpc-plain-text-quickstart` (spec §2a); the module is invented.

QUARKUS_CAPABILITIES = CAPABILITIES | {"superclass"}
QUARKUS_CLIENT = "io/quarkus/grpc/GrpcClient#"
GRPC_SERVICE = "io/quarkus/grpc/GrpcService#"
MUTINY_CLIENT = "io/quarkus/grpc/MutinyClient#"
QK_GRPC = "examples/GreeterGrpc#"
QK_BLOCKING_STUB = "examples/GreeterGrpc$GreeterBlockingStub#"
QK_PLAIN_BASE = "examples/GreeterGrpc$GreeterImplBase#"
QK_MUTINY_GRPC = "examples/MutinyGreeterGrpc#"
QK_MUTINY_STUB = "examples/MutinyGreeterGrpc$MutinyGreeterStub#"
QK_MUTINY_BASE = "examples/MutinyGreeterGrpc$GreeterImplBase#"
QK_INTERFACE = "examples/Greeter#"
QK_CLIENT = "examples/GreeterClient#"
QK_BEAN = "examples/GreeterBean#"
QK_NAME = "helloworld.Greeter"


def _class(
    symbol: str,
    *,
    superclass: str | None = None,
    interfaces: tuple[str, ...] = (),
    kind: ConstructKind = ConstructKind.CLASS,
    annotation: str | None = None,
) -> list[object]:
    facts: list[object] = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + symbol,
            construct_kind=kind,
            superclass=_MODULE + superclass if superclass else None,
            interfaces=list(interfaces),
        )
    ]
    if annotation is not None:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=_MODULE + symbol,
                use=AnnotationUse(annotation=annotation),
                retention="RUNTIME",
            )
        )
    return facts


def _call(caller: str, owner: str, name: str, *, ordinal: int = 0) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=f"{_MODULE}{caller}",
        target=CallTarget(owner=owner, name=name, descriptor="(...)V"),
        invoke_kind="virtual",
        ordinal=ordinal,
    )


def _mutiny_client(
    symbol: str = QK_CLIENT, *, interfaces: tuple[str, ...] = (QK_INTERFACE, MUTINY_CLIENT)
) -> list[object]:
    """`GreeterClient implements Greeter, MutinyClient<MutinyGreeterStub>`
    (spec §2a): it builds its stub with `MutinyGreeterGrpc.newMutinyStub`,
    and its `sayHello` calls the stub's."""
    return [
        *_class(symbol, interfaces=interfaces),
        _call(f"{symbol}`<init>`(sig_init).", QK_MUTINY_GRPC, "newMutinyStub"),
        _call(f"{symbol}sayHello(sig_sayHello).", QK_MUTINY_STUB, "sayHello", ordinal=1),
    ]


def _generated(
    *, client_interfaces: tuple[str, ...] = (QK_INTERFACE, MUTINY_CLIENT)
) -> list[object]:
    """What `quarkus-grpc`'s code generation compiles into a module for one
    `service Greeter` (spec §2a), the client half: grpc-java's `GreeterGrpc`,
    which states the identity; the Mutiny interface; the Mutiny stub, whose
    constructor calls `GreeterGrpc.newStub`; and the generated client, which
    declares `client_interfaces`."""
    return [
        _service_name_site(QK_NAME, outer=QK_GRPC),
        *_class(QK_INTERFACE, interfaces=("io/quarkus/grpc/MutinyService#",)),
        *_class(
            QK_MUTINY_STUB,
            superclass="io/grpc/stub/AbstractStub#",
            interfaces=("io/quarkus/grpc/MutinyStub#",),
        ),
        _call(f"{QK_MUTINY_STUB}`<init>`(sig_init).", QK_GRPC, "newStub"),
        *_mutiny_client(interfaces=client_interfaces),
    ]


def _bean() -> list[object]:
    """The generated `GreeterBean extends MutinyGreeterGrpc.GreeterImplBase
    implements BindableService, MutinyBean`, which carries no annotation, and
    the Mutiny base it extends, whose `bindService` calls `GreeterGrpc`."""
    return [
        *_class(QK_MUTINY_BASE, interfaces=("io/grpc/BindableService#",)),
        _call(f"{QK_MUTINY_BASE}bindService().", QK_GRPC, "getServiceDescriptor"),
        *_class(
            QK_BEAN,
            superclass=QK_MUTINY_BASE,
            interfaces=("io/grpc/BindableService#", "io/quarkus/grpc/MutinyBean#"),
        ),
        _call(f"{QK_BEAN}sayHello(sig_sayHello).", QK_INTERFACE, "sayHello"),
    ]


def _quarkus(
    tmp_path: Path, facts: list[object]
) -> tuple[list[tuple[object, object]], list[dict[str, object]]]:
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    shipped = [c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "grpc-quarkus-client"]
    resolve(workspace, tmp_path / "facts", _Catalogs(shipped), QUARKUS_CAPABILITIES)
    rows = [(row["path"], row["resolution"]) for row in workspace.query("endpoints")]
    questions = workspace.query("open_questions")
    workspace.close()
    return rows, questions


@pytest.mark.pins("grpc.an-INTERFACE-client-resolves-through-the-generated-client")
def test_a_client_typed_by_the_mutiny_interface_resolves_through_its_generated_client(
    tmp_path: Path,
):
    """CP-53 rows 3, 6: Quarkus answers an injected service interface with the
    generated client that implements it and `MutinyClient`. That client states
    no identity; its code reaches `GreeterGrpc` through the Mutiny stub
    (spec §3a), so the row is `GreeterGrpc`'s service."""
    facts = [*_generated(), *_injected_field(QK_INTERFACE, annotation=QUARKUS_CLIENT)]

    rows, questions = _quarkus(tmp_path, facts)

    assert rows == [(QK_NAME, "resolved")]
    assert questions == []


@pytest.mark.pins("grpc.an-injected-WRAPPER-stub-takes-the-identity-it-delegates-to")
def test_an_injected_mutiny_stub_takes_the_identity_its_class_delegates_to(tmp_path: Path):
    """Spec §3a: `MutinyGreeterGrpc` makes no marker call of its own, and the
    stub's constructor calls `GreeterGrpc.newStub`. A client-only module
    injecting the Mutiny stub talks to `GreeterGrpc`'s service."""
    facts = [*_generated(), *_injected_field(QK_MUTINY_STUB, annotation=QUARKUS_CLIENT)]

    rows, questions = _quarkus(tmp_path, facts)

    assert rows == [(QK_NAME, "resolved")]
    assert questions == []


@pytest.mark.pins("grpc.an-UNANNOTATED-generated-bean-does-not-fence")
def test_a_mutiny_stub_client_resolves_and_is_not_fenced_by_the_generated_bean(tmp_path: Path):
    """`GreeterBean` extends a class nested in `MutinyGreeterGrpc`, the Mutiny
    stub's own outer class, which is the symbol fence's whole test. It carries
    no `@GrpcService`, and Quarkus serves only a class that does (CP-52 row 7,
    CP-53 row 9), so under `served_by_annotation` it fences nothing."""
    facts = [
        *_generated(),
        *_bean(),
        *_injected_field(QK_MUTINY_STUB, annotation=QUARKUS_CLIENT),
    ]

    rows, questions = _quarkus(tmp_path, facts)

    assert rows == [(QK_NAME, "resolved")]
    assert questions == []


def test_an_annotated_quarkus_implementer_still_fences(tmp_path: Path):
    """The bound on the rule above: a class that declares `@GrpcService` and
    extends the generated base serves the service, so the module's client of
    it gets no outbound row."""
    facts = [
        *_generated(),
        *_class(QK_PLAIN_BASE, interfaces=("io/grpc/BindableService#",)),
        *_class("examples/HelloWorldService#", superclass=QK_PLAIN_BASE, annotation=GRPC_SERVICE),
        *_injected_field(QK_BLOCKING_STUB, annotation=QUARKUS_CLIENT),
    ]

    rows, _ = _quarkus(tmp_path, facts)

    assert rows == []


@pytest.mark.pins("grpc.two-INTERFACE-clients-resolve-neither")
def test_two_mutiny_clients_for_one_interface_is_unresolved(tmp_path: Path):
    """Two classes implementing `Greeter` and `MutinyClient`: Quarkus's map
    keeps one of them in an order nothing here can read (CP-53 row 3,
    `Map.put`), so neither is taken. The row and question are the ones an
    unreadable identity gets today."""
    facts = [
        *_generated(),
        *_mutiny_client("examples/OtherGreeterClient#"),
        *_injected_field(QK_INTERFACE, annotation=QUARKUS_CLIENT),
    ]

    rows, questions = _quarkus(tmp_path, facts)

    assert rows == [(QK_INTERFACE, "unresolved")]
    assert [(q["question"], q["path"]) for q in questions] == [("service_identity", QK_INTERFACE)]


@pytest.mark.pins("grpc.a-MUTINY-client-is-keyed-by-its-first-other-interface")
def test_a_mutiny_client_is_keyed_by_its_first_interface_other_than_mutiny_client(
    tmp_path: Path,
):
    """CP-53 row 3: Quarkus keys a `MutinyClient` implementor by the FIRST
    interface it declares that is not `MutinyClient`, and reads no further. A
    client declaring `MutinyClient, Greeter, Audited` answers `Greeter`, and
    an injected `Audited` is not answered by it."""
    audited = "examples/Audited#"
    facts = [
        *_generated(client_interfaces=(MUTINY_CLIENT, QK_INTERFACE, audited)),
        *_class(audited, kind=ConstructKind.INTERFACE),
        *_injected_field(QK_INTERFACE, annotation=QUARKUS_CLIENT),
        *_injected_field(
            audited, "com/acme/billing/AuditService#audited.", annotation=QUARKUS_CLIENT
        ),
    ]

    rows, _ = _quarkus(tmp_path, facts)

    assert set(rows) == {(QK_NAME, "resolved"), (audited, "unresolved")}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("interface_client", "io.quarkus.grpc.MutinyClient"),
        ("interface_client", {"implements": 3}),
        ("served_by_annotation", ["io.quarkus.grpc.GrpcService"]),
    ],
)
def test_a_malformed_quarkus_client_key_is_refused(tmp_path: Path, key: str, value: object):
    shipped = next(
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "grpc-quarkus-client"
    )
    matches = dict(shipped.matches)
    matches[key] = value
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    with pytest.raises(CatalogError, match=key):
        derive_endpoints(workspace, [_catalog(matches=matches)], capabilities=CAPABILITIES)
    workspace.close()
