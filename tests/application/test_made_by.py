"""`made_by` (D02 §2's `annotation_driven`, Android outbound spec M8): a Retrofit row takes the
server address of the object that made its client.

Facts are hand-built in the shape `fixtures/gradle-android`'s `Orders` compiles to (read off
its scan): `Retrofit.Builder().baseUrl(url).build().create(OrdersApi::class.java)`, the client
held in a field."""

from dataclasses import replace
from pathlib import Path

import pytest

from flow_facts import straight_line
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shapes.made_by import validated_made_by
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    FieldWriteFact,
    MethodReturnFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
CAPABILITIES = {"annotation_args", "typed_signatures", "call_site", "string_constants"}
_MODULE = "sextant-jvm maven com.acme/app 1.0.0 "

API = "com/acme/app/OrdersApi#"
STATUS_API = "com/acme/app/StatusApi#"
ORDERS = "com/acme/app/Orders#"
RETROFIT = "retrofit2/Retrofit#"
BUILDER = "retrofit2/Retrofit$Builder#"
_BASE_URL = "(Ljava/lang/String;)Lretrofit2/Retrofit$Builder;"
_BUILD = "()Lretrofit2/Retrofit;"
_CREATE = "(Ljava/lang/Class;)Ljava/lang/Object;"


def _catalog():
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "retrofit")


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/app/OrdersApi.kt",
        module_id="com.acme:app",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="build/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _interface(interface: str, path: str) -> list:
    """An interface with one `@GET(path)` method."""
    method = f"{_MODULE}{interface}order(sig_5a5a5a5a)."
    return [
        SymbolFact(
            document_id="doc_1", symbol=_MODULE + interface, construct_kind=ConstructKind.INTERFACE
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=method,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + interface,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#", wire_type="")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=method,
            retention="runtime",
            use=AnnotationUse(annotation="retrofit2/http/GET#", args={"value": path}),
        ),
    ]


def _method(owner: str, name: str) -> str:
    return f"{_MODULE}{owner}{name}()."


def _declared(owner: str, name: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_method(owner, name),
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(parameters=[], returns=TypeRef(symbol="void#", wire_type="")),
    )


def _call(caller, owner, name, descriptor, ordinal, receiver, result, arguments=None, **more):
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind="special" if name == "<init>" else "virtual",
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=arguments or [],
        **more,
    )


def _made_in_one_method(caller: str, base: CallArgument, interface: str = API) -> list:
    """`Retrofit.Builder().baseUrl(base).build().create(interface)`, in `caller`."""
    return [
        _call(caller, BUILDER, "<init>", "()V", 0, receiver=7, result=None),
        _call(caller, BUILDER, "baseUrl", _BASE_URL, 1, receiver=7, result=13, arguments=[base]),
        _call(caller, BUILDER, "build", _BUILD, 2, receiver=13, result=16),
        _call(
            caller,
            RETROFIT,
            "create",
            _CREATE,
            3,
            receiver=16,
            result=20,
            arguments=[CallArgument(kind="class", symbol=interface)],
        ),
    ]


def _rows(tmp_path: Path, facts: list, catalog: Catalog | None = None) -> set[tuple]:
    """The retrofit rows the resolve derives, with the return flows and call edges the
    pipeline records before it (`test_client_base._resolved`), so a helper's return and a
    parameter's callers are followed as in a real run."""
    write_fact_file(tmp_path / "facts" / "App.jsonl", _document(), straight_line(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_return_flows(workspace)
    record_call_edges(workspace)
    derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    rows = {
        (r["method"], r["peer"], r["path"], r["resolution"])
        for r in workspace.query("endpoints")
        if r["catalog_id"] == "retrofit"
    }
    workspace.close()
    return rows


def _url(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def test_a_retrofit_row_takes_the_address_of_the_builder_that_made_its_client(tmp_path: Path):
    """The fixture's own shape: the client is made in a static initialiser, and the row is
    the base joined to the interface's relative path."""
    clinit = _method(ORDERS, "<clinit>")
    facts = [
        *_interface(API, "orders/{id}"),
        _declared(ORDERS, "<clinit>"),
        *_made_in_one_method(clinit, _url("https://free.api.example/")),
    ]
    assert _rows(tmp_path, facts) == {("GET", "free.api.example", "/orders/{id}", "resolved")}


def test_a_path_with_a_leading_slash_replaces_the_base_path(tmp_path: Path):
    """`baseUrl.resolve(relativeUrl)`: `/orders` is from the root, `orders` from the base's
    own path."""
    clinit = _method(ORDERS, "<clinit>")
    facts = [
        *_interface(API, "/orders"),
        *_interface(STATUS_API, "status"),
        _declared(ORDERS, "<clinit>"),
        *_made_in_one_method(clinit, _url("https://api.example/v2/")),
        *[
            site.model_copy(update={"ordinal": site.ordinal + 10})
            for site in _made_in_one_method(clinit, _url("https://api.example/v2/"), STATUS_API)
        ],
    ]
    assert _rows(tmp_path, facts) == {
        ("GET", "api.example", "/orders", "resolved"),
        ("GET", "api.example", "/v2/status", "resolved"),
    }


def test_each_client_made_for_one_interface_gives_its_own_row(tmp_path: Path):
    """Two objects made with two addresses: both are called, so both rows, each exact."""
    first, second = _method(ORDERS, "free"), _method(ORDERS, "paid")
    facts = [
        *_interface(API, "orders/{id}"),
        _declared(ORDERS, "free"),
        _declared(ORDERS, "paid"),
        *_made_in_one_method(first, _url("https://free.api.example/")),
        *_made_in_one_method(second, _url("https://paid.api.example/")),
    ]
    assert _rows(tmp_path, facts) == {
        ("GET", "free.api.example", "/orders/{id}", "resolved"),
        ("GET", "paid.api.example", "/orders/{id}", "resolved"),
    }


def test_the_object_is_followed_through_a_field_to_the_method_that_made_it(tmp_path: Path):
    """`retrofit = Retrofit.Builder().baseUrl(u).build()` in the constructor, and
    `retrofit.create(OrdersApi::class.java)` in another method: the object walk follows the
    field back to the `build()` that made it, and the fold reads `baseUrl` there."""
    init, client = _method(ORDERS, "<init>"), _method(ORDERS, "api")
    field = ORDERS + "retrofit."
    facts = [
        *_interface(API, "orders/{id}"),
        _declared(ORDERS, "<init>"),
        _declared(ORDERS, "api"),
        _call(init, BUILDER, "<init>", "()V", 0, receiver=7, result=None),
        _call(init, BUILDER, "baseUrl", _BASE_URL, 1, receiver=7, result=13,
              arguments=[_url("https://field.api.example/")]),
        _call(init, BUILDER, "build", _BUILD, 2, receiver=13, result=16),
        FieldWriteFact(
            document_id="doc_1",
            field=field,
            value=CallArgument(kind="unresolved", source=16),
            written_by=init,
        ),
        _call(client, RETROFIT, "create", _CREATE, 0, receiver=3, result=5,
              receiver_field=field, arguments=[CallArgument(kind="class", symbol=API)]),
    ]  # fmt: skip
    assert _rows(tmp_path, facts) == {("GET", "field.api.example", "/orders/{id}", "resolved")}


def test_a_client_no_call_makes_is_partial_with_no_server_address(tmp_path: Path):
    """No `create` names the interface (a container makes it, or nothing does): the path is
    the interface's own, no peer, and `partial` — the server address is not read. It was
    `resolved` before, which claimed a complete address the row did not have."""
    assert _rows(tmp_path, _interface(API, "orders/{id}")) == {
        ("GET", None, "orders/{id}", "partial")
    }


def test_a_base_handed_in_from_code_we_do_not_have_is_partial(tmp_path: Path):
    """The builder's address is a parameter of a method nothing in the module calls: the
    address is not read, so the row is `partial` with no peer."""
    maker = f"{_MODULE}{ORDERS}make(Ljava/lang/String;)."
    facts = [
        *_interface(API, "orders/{id}"),
        SymbolFact(
            document_id="doc_1",
            symbol=maker,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + ORDERS,
            signature=Signature(
                parameters=[],
                returns=TypeRef(symbol="void#", wire_type=""),
            ),
        ),
        *_made_in_one_method(maker, CallArgument(kind="parameter", value=0)),
    ]
    assert _rows(tmp_path, facts) == {("GET", None, "orders/{id}", "partial")}


def test_a_base_retrofit_refuses_makes_no_client_and_is_not_read(tmp_path: Path):
    """DR-6, measured: `baseUrl` throws where the base's path does not end in `/`, so no
    client is made with it and no address is published."""
    clinit = _method(ORDERS, "<clinit>")
    facts = [
        *_interface(API, "orders/{id}"),
        _declared(ORDERS, "<clinit>"),
        *_made_in_one_method(clinit, _url("https://api.example/v2")),
    ]
    assert _rows(tmp_path, facts) == {("GET", None, "orders/{id}", "partial")}


def test_made_by_is_refused_on_a_catalog_that_is_not_an_outbound_annotation_catalog():
    """The word says where an annotation-declared CLIENT gets its address: on any other
    catalog it would load and be read by nothing."""
    catalog = _catalog()
    with pytest.raises(CatalogError, match="outbound `annotation_driven`"):
        validated_made_by(replace(catalog, direction="inbound"))
    with pytest.raises(CatalogError, match="unknown"):
        validated_made_by(
            replace(
                catalog,
                matches={**catalog.matches, "made_by": {**catalog.matches["made_by"], "x": 1}},
            )
        )
    with pytest.raises(CatalogError, match="capture `base`"):
        steps = [{"method": "baseUrl", "owner": "a.B", "captures": {"url": "arg0"}}]
        validated_made_by(
            replace(
                catalog,
                matches={
                    **catalog.matches,
                    "made_by": {**catalog.matches["made_by"], "steps": steps},
                },
            )
        )


def test_an_absolute_url_on_the_annotation_is_the_address_whatever_the_base(tmp_path: Path):
    """`@GET("https://status.example/health")` replaces the base entirely (RFC 3986 §5.2), so
    the row's address is read even where no client is made in the module."""
    assert _rows(tmp_path, _interface(API, "https://status.example/health")) == {
        ("GET", "status.example", "/health", "resolved")
    }


_MAKE = "(Ljava/lang/String;)Lretrofit2/Retrofit;"


def _helper_made(maker: str) -> list:
    """`fun retrofit(base: String) = Retrofit.Builder().baseUrl(base).build()`."""
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + ORDERS,
            construct_kind=ConstructKind.CLASS,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=maker,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + ORDERS,
        ),
        _call(maker, BUILDER, "<init>", "()V", 0, receiver=7, result=None),
        _call(maker, BUILDER, "baseUrl", _BASE_URL, 1, receiver=7, result=13,
              arguments=[CallArgument(kind="parameter", value=0)]),
        _call(maker, BUILDER, "build", _BUILD, 2, receiver=13, result=16),
        MethodReturnFact(
            document_id="doc_1",
            method=maker,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=16),
        ),
    ]  # fmt: skip


def _created_through(caller: str, base: str, interface: str) -> list:
    """`retrofit(base).create(interface)` in `caller`."""
    return [
        _call(caller, ORDERS, "retrofit", _MAKE, 0, receiver=None, result=5,
              arguments=[_url(base)]).model_copy(update={"invoke_kind": "static"}),
        _call(caller, RETROFIT, "create", _CREATE, 1, receiver=5, result=6,
              arguments=[CallArgument(kind="class", symbol=interface)]),
    ]  # fmt: skip


def test_a_helper_called_twice_gives_each_client_its_own_callers_base(tmp_path: Path):
    """Review fix round 1, Critical 1. A helper takes the base as a parameter and is called
    twice, once per interface. The object walk keeps the path through the helper, and the
    base is read on that path, so each interface gets its own caller's base and never the
    other's. Before the fix both interfaces took both bases, all `resolved`."""
    maker = _MODULE + method_descriptor(ORDERS, "retrofit", _MAKE)
    auth, public = _method(ORDERS, "auth"), _method(ORDERS, "pub")
    facts = [
        *_interface(API, "orders"),
        *_interface(STATUS_API, "status"),
        *_helper_made(maker),
        _declared(ORDERS, "auth"),
        _declared(ORDERS, "pub"),
        *_created_through(auth, "https://auth.example/", API),
        *_created_through(public, "https://public.example/", STATUS_API),
    ]
    assert _rows(tmp_path, facts) == {
        ("GET", "auth.example", "/orders", "resolved"),
        ("GET", "public.example", "/status", "resolved"),
    }


def test_an_inherited_candidate_takes_only_its_own_interfaces_address(tmp_path: Path):
    """Review fix round 1, Important 2. One inherited method is one candidate per interface
    that serves it (`served_by`), with the same handler, verb and path. Each takes the
    address named for its own interface and never the other's, because `served_by` is part
    of the key the addresses are joined on.

    Pinned at the statement: no shipped catalog derives such a pair today. Retrofit has no
    type gate, so its rows are served by the interface that declares them, and the SEI fence
    drops a base interface another interface extends (logged in the fix report)."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace._connection.execute(
        """
        CREATE TEMP TABLE endpoint_candidates AS
        SELECT * FROM (VALUES
            ('retrofit', 'h#health().', 'a/AuthApi#', NULL, 'GET', 'health', NULL, 'resolved'),
            ('retrofit', 'h#health().', 'a/PublicApi#', NULL, 'GET', 'health', NULL, 'resolved'),
            ('other', 'h#health().', 'a/AuthApi#', NULL, 'GET', 'health', NULL, 'resolved')
        ) t(catalog_id, handler, served_by, caller, method, path, peer, resolution)
        """
    )
    workspace.derive(
        "endpoint_candidates_address",
        catalog_id="retrofit",
        rows=[
            {"handler": "h#health().", "served_by": served, "caller": None, "method": "GET",
             "was": "health", "peer": peer, "path": "/health", "resolution": "resolved"}
            for served, peer in (("a/AuthApi#", "auth.example"), ("a/PublicApi#", "public"))
        ],
    )  # fmt: skip
    rows = workspace._connection.execute(
        "SELECT catalog_id, served_by, peer, path FROM endpoint_candidates ORDER BY ALL"
    ).fetchall()
    workspace.close()
    assert rows == [
        ("other", "a/AuthApi#", None, "health"),
        ("retrofit", "a/AuthApi#", "auth.example", "/health"),
        ("retrofit", "a/PublicApi#", "public", "/health"),
    ]
