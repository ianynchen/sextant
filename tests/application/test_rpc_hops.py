"""A gRPC client stub's call to an RPC this module serves lands on its handler (spec
2026-10-25 §3d, ruling 2).

The facts mirror what `grpc-plain-text-quickstart` compiles to (spec §2c, measured with
`call_edges`): `GreeterGrpc$GreeterBlockingStub#sayHello` calls `GreeterGrpc#getSayHelloMethod`
at ordinal 1, whose own body calls `MethodDescriptor.generateFullMethodName(SERVICE_NAME,
"SayHello")`, and then `ClientCalls#blockingUnaryCall` at ordinal 3, a boundary. The stub's
supertypes are library rows (`scanned: false`) in `type_hierarchy`.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.rpc_hops import record_rpc_hops
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven org.acme/greeter 1.0.0 "
SERVICE = "helloworld.Greeter"
OUTER = "examples/GreeterGrpc#"
BLOCKING = "examples/GreeterGrpc$GreeterBlockingStub#"
ASYNC = "examples/GreeterGrpc$GreeterStub#"
ASYNC_SERVICE = "examples/GreeterGrpc$AsyncService#"
ACCESSOR = f"{OUTER}getSayHelloMethod(sig_8f588582)."
BLOCKING_CALL = f"{BLOCKING}sayHello(sig_6c6abb62)."
ASYNC_CALL = f"{ASYNC}sayHello(sig_cba98d0c)."
HANDLER = "io/quarkus/grpc/examples/hello/HelloWorldService#sayHello(sig_849d6ed9)."
OTHER_HANDLER = "io/quarkus/grpc/examples/hello/LegacyGreeter#sayHello(sig_849d6ed9)."
_ABSTRACT_STUB = "io/grpc/stub/AbstractStub#"
_BLOCKING_BASE = "io/grpc/stub/AbstractBlockingStub#"
_ASYNC_BASE = "io/grpc/stub/AbstractAsyncStub#"


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="examples/GreeterGrpc.class",
        module_id="org.acme:greeter",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _site(caller: str, owner: str, name: str, ordinal: int, *strings: str) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=_MODULE + caller,
        target=CallTarget(owner=owner, name=name, descriptor="(...)V"),
        invoke_kind="static",
        ordinal=ordinal,
        arguments=[CallArgument(kind="string", value=value) for value in strings],
    )


def _service_name_site(service: str = SERVICE, outer: str = OUTER) -> CallSiteFact:
    """`getServiceDescriptor`'s `ServiceDescriptor.newBuilder("<package>.<Service>")`."""
    return _site(
        f"{outer}getServiceDescriptor().", "io/grpc/ServiceDescriptor#", "newBuilder", 0, service
    )


def _method_name_site(accessor: str, wire_method: str, ordinal: int = 0) -> CallSiteFact:
    """An accessor's `MethodDescriptor.generateFullMethodName(SERVICE_NAME, "<Method>")`."""
    return _site(
        accessor,
        "io/grpc/MethodDescriptor#",
        "generateFullMethodName",
        ordinal,
        SERVICE,
        wire_method,
    )


def _catalog(source: str = "grpc-java.yml") -> Catalog:
    """The shipped `grpc-java.yml`, so the keys the pass reads are the catalog's own."""
    shipped = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "grpc-java")
    return replace(shipped, source=Path(source))


def _workspace(
    tmp_path: Path,
    *,
    facts: list[object],
    edges: list[tuple[str, int, str, str | None]],
    hierarchy: list[tuple[str, str]],
    handled: list[tuple[str, str | None]],
) -> DuckDbWorkspace:
    """Facts loaded, then `call_edges` as `(caller, ordinal, target, callee)`,
    `type_hierarchy` as `(child, ancestor)` library rows, and inbound `grpc` endpoints as
    `(path, handler)` — the tables the pass reads, as the earlier passes leave them."""
    write_fact_file(tmp_path / "facts" / "GreeterGrpc.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    for caller, ordinal, target, callee in edges:
        workspace._connection.execute(
            "INSERT INTO call_edges (caller, ordinal, invoke_kind, target, callee, resolution, "
            "evidence) VALUES (?, ?, 'virtual', ?, ?, 'resolved', 'compiler')",
            [_MODULE + caller, ordinal, target, None if callee is None else _MODULE + callee],
        )
    for child, ancestor in hierarchy:
        workspace._connection.execute(
            "INSERT INTO type_hierarchy VALUES (?, ?, 'extends', 0, false)", [child, ancestor]
        )
    for path, handler in handled:
        workspace._connection.execute(
            "INSERT INTO endpoints (row_id, protocol, direction, method, path, handler) "
            "VALUES ((SELECT coalesce(max(row_id), 0) + 1 FROM endpoints), 'grpc', 'inbound', NULL, ?, ?)",
            [path, None if handler is None else _MODULE + handler],
        )
    return workspace


def _blocking_edges(
    accessor: str = ACCESSOR, caller: str = BLOCKING_CALL
) -> list[tuple[str, int, str, str | None]]:
    """The blocking stub's `sayHello`, as `call_edges` holds it (spec §2c)."""
    return [
        (caller, 0, f"{BLOCKING}getChannel(sig_6605009e).", None),
        (caller, 1, accessor, accessor),
        (caller, 2, f"{BLOCKING}getCallOptions(sig_ede98ce1).", None),
        (caller, 3, "io/grpc/stub/ClientCalls#blockingUnaryCall(sig_64fbb960).", None),
    ]


_STUB_HIERARCHY = [(BLOCKING, _BLOCKING_BASE), (_BLOCKING_BASE, _ABSTRACT_STUB)]
_GREETER_FACTS: list[object] = [
    _service_name_site(),
    _method_name_site(ACCESSOR, "SayHello"),
]


def _hops(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    rows = [tuple(row.values()) for row in workspace.query("rpc_hops")]
    workspace.close()
    return rows


@pytest.mark.pins("grpc.a-STUB-call-to-a-served-rpc-is-a-hop")
def test_a_blocking_stub_call_to_a_served_rpc_lands_on_its_handler(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=_blocking_edges(),
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert _hops(workspace) == [
        (
            _MODULE + BLOCKING_CALL,
            3,
            "grpc",
            f"{SERVICE}/SayHello",
            _MODULE + HANDLER,
            "compiler",
        )
    ]


def test_an_async_stub_method_gets_its_own_hop(tmp_path: Path) -> None:
    """`GreeterStub#sayHello` leaves through `ClientCalls#asyncUnaryCall` at ordinal 4,
    after a `Channel#newCall` at 3 that is not the client-call API."""
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=[
            *_blocking_edges(),
            (ASYNC_CALL, 0, f"{ASYNC}getChannel(sig_6605009e).", None),
            (ASYNC_CALL, 1, ACCESSOR, ACCESSOR),
            (ASYNC_CALL, 2, f"{ASYNC}getCallOptions(sig_ede98ce1).", None),
            (ASYNC_CALL, 3, "io/grpc/Channel#newCall(sig_f31adf85).", None),
            (ASYNC_CALL, 4, "io/grpc/stub/ClientCalls#asyncUnaryCall(sig_3ed83b3e).", None),
        ],
        hierarchy=[*_STUB_HIERARCHY, (ASYNC, _ASYNC_BASE), (_ASYNC_BASE, _ABSTRACT_STUB)],
        handled=[(f"{SERVICE}/SayHello", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert [(row[0], row[1]) for row in _hops(workspace)] == [
        (_MODULE + BLOCKING_CALL, 3),
        (_MODULE + ASYNC_CALL, 4),
    ]


@pytest.mark.pins("grpc.an-UNHANDLED-rpc-of-a-served-service-gets-a-hop")
def test_an_unhandled_rpc_of_a_served_service_gets_a_row_with_no_handler(
    tmp_path: Path,
) -> None:
    """The module serves `Greeter` (`SayHello` has a handler) but not `SayGoodbye`: the
    stub's call to it still names its wire path, with no handler to land on."""
    goodbye_accessor = f"{OUTER}getSayGoodbyeMethod(sig_8f588582)."
    goodbye_call = f"{BLOCKING}sayGoodbye(sig_6c6abb62)."
    workspace = _workspace(
        tmp_path,
        facts=[
            *_GREETER_FACTS,
            _method_name_site(goodbye_accessor, "SayGoodbye"),
        ],
        edges=_blocking_edges(goodbye_accessor, goodbye_call),
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", HANDLER), (f"{SERVICE}/SayGoodbye", None)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert _hops(workspace) == [
        (_MODULE + goodbye_call, 3, "grpc", f"{SERVICE}/SayGoodbye", None, "compiler")
    ]


def test_a_path_with_two_handlers_gets_one_row_each(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=_blocking_edges(),
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", HANDLER), (f"{SERVICE}/SayHello", OTHER_HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert [row[4] for row in _hops(workspace)] == [_MODULE + HANDLER, _MODULE + OTHER_HANDLER]


def test_a_service_not_served_here_gets_no_hop(tmp_path: Path) -> None:
    """A `.proto` row alone (handler NULL) serves nothing (§3c): the call keeps its
    outbound row and gets no hop."""
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=_blocking_edges(),
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", None)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert _hops(workspace) == []


@pytest.mark.pins("grpc.a-stub-of-a-service-NOT-served-gets-no-hop")
def test_a_stub_of_a_service_other_than_the_one_served_gets_no_hop(tmp_path: Path) -> None:
    """The module serves `helloworld.Hello`, with a handler, and calls `Greeter` through its
    stub: a call to a service it does not serve is outbound, so it gets no hop."""
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=_blocking_edges(),
        hierarchy=_STUB_HIERARCHY,
        handled=[("helloworld.Hello/SayHello", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert _hops(workspace) == []


@pytest.mark.pins("grpc.a-stub-naming-TWO-wire-methods-gets-no-hop")
def test_a_stub_method_naming_two_wire_methods_gets_no_hop(tmp_path: Path) -> None:
    """An accessor whose body names two wire methods says nothing about which one this
    call makes, so no row is guessed."""
    workspace = _workspace(
        tmp_path,
        facts=[
            _service_name_site(),
            _method_name_site(ACCESSOR, "SayHello"),
            _method_name_site(ACCESSOR, "SayGoodbye", ordinal=1),
        ],
        edges=_blocking_edges(),
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", HANDLER), (f"{SERVICE}/SayGoodbye", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert _hops(workspace) == []


@pytest.mark.pins("grpc.only-a-STUB-method-gets-a-hop")
def test_a_class_that_is_not_a_stub_gets_no_hop(tmp_path: Path) -> None:
    """A method of a class outside the stub ancestry gets no hop, though it makes the same
    two calls a stub method does — an accessor in the marked nest, then `ClientCalls`.
    `AsyncService` is the server side; a hand-written module method calling
    `ClientCalls.blockingUnaryCall(channel, GreeterGrpc.getSayHelloMethod(), …)` directly
    has the same shape. Beside a real stub, so the pass reaches its stub-class filter."""
    default_method = f"{ASYNC_SERVICE}sayHello(sig_11111111)."
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=[
            *_blocking_edges(),
            (default_method, 0, ACCESSOR, ACCESSOR),
            (default_method, 1, "io/grpc/stub/ClientCalls#asyncUnaryCall(sig_3ed83b3e).", None),
        ],
        hierarchy=[*_STUB_HIERARCHY, (ASYNC_SERVICE, "io/grpc/BindableService#")],
        handled=[(f"{SERVICE}/SayHello", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert [row[0] for row in _hops(workspace)] == [_MODULE + BLOCKING_CALL]


@pytest.mark.pins("grpc.no-CLIENT-CALL-site-means-no-hop")
def test_a_stub_method_that_never_reaches_the_client_call_api_gets_no_hop(
    tmp_path: Path,
) -> None:
    edges = [edge for edge in _blocking_edges() if edge[1] != 3]
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=edges,
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    assert _hops(workspace) == []


def test_a_second_run_replaces_the_rows(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        facts=_GREETER_FACTS,
        edges=_blocking_edges(),
        hierarchy=_STUB_HIERARCHY,
        handled=[(f"{SERVICE}/SayHello", HANDLER)],
    )
    record_rpc_hops(workspace, [_catalog()])
    record_rpc_hops(workspace, [_catalog()])
    assert len(_hops(workspace)) == 1


def test_two_catalogs_declaring_the_stub_keys_are_refused(tmp_path: Path) -> None:
    """Two catalogs naming the client stub could name two different ones, and this pass
    has no rule for choosing."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    with pytest.raises(CatalogError, match="second.yml"):
        record_rpc_hops(workspace, [_catalog(), _catalog("second.yml")])
    workspace.close()
