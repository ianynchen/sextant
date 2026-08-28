from pathlib import Path

from sextant.application.resolve.endpoints import (
    Catalog,
    SkippedCatalog,
    derive_endpoints,
    load_catalogs,
)
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "catalogs"


def test_catalog_declares_its_style_and_required_capabilities_when_loaded():
    catalogs = load_catalogs(CATALOGS)
    spring = next(c for c in catalogs if c.id == "spring-web")
    assert spring.style == "annotation_driven"
    assert spring.protocol == "http"
    assert spring.direction == "inbound"
    assert "annotation_args" in spring.requires


def test_catalog_maps_post_mapping_to_the_post_method():
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")
    methods = {m["fqn"]: m["http_method"] for m in spring.matches["method_annotations"]}
    assert methods["org/springframework/web/bind/annotation/PostMapping#"] == "POST"


def _controller_facts(root: Path) -> None:
    """Mirrors the exact shape the ASM extractor emits for a Spring
    controller (verified against fixtures/orders-service): a type-level
    RestController with no argument, a RequestMapping whose `value` is a
    one-element JSON array, one PostMapping and one GetMapping with no
    argument at all, and one GetMapping whose `value` is a one-element
    array."""
    document = Document(
        document_id="doc_1", relative_path="com/acme/orders/OrderController.java",
        module_id="com.acme:orders-service", language="java", sextant_version="0.1.0",
        fact_schema_version="1.0.0", scanner_id="asm", scanner_version="9.7",
        content_hash="sha256:a", origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT, redaction_set_hash="sha256:b",
    )
    controller = "com/acme/orders/OrderController#"
    create = "com/acme/orders/OrderController#create()."
    get = "com/acme/orders/OrderController#get()."
    list_ = "com/acme/orders/OrderController#list()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1", symbol=create, construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1", symbol=get, construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1", symbol=list_, construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1", target=controller, retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#", args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1", target=controller, retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1", target=create, retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/PostMapping#", args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1", target=get, retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": ["/{id}"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1", target=list_, retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#", args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def test_derive_endpoints_finds_the_three_annotated_routes_when_the_catalog_is_annotation_driven(
    tmp_path: Path,
):
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")

    skipped = derive_endpoints(workspace, [spring], capabilities={"annotation_args"})
    routes = {(e["method"], e["path"]) for e in workspace.query("endpoints")}
    workspace.close()

    assert skipped == []
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }


def _invented_listener_facts(root: Path) -> None:
    """A second, invented annotation_driven shape — deliberately not Spring —
    used only to prove that `protocol` and `direction` on the derived rows
    come from the catalog's own declared fields rather than from a literal
    baked into the SQL. D02 groups Spring Kafka and JMS listeners under this
    same style with `protocol: message`; a catalog like this one is exactly
    what would have silently come out labelled http/inbound before this fix."""
    document = Document(
        document_id="doc_1", relative_path="com/acme/notify/OrderListener.java",
        module_id="com.acme:orders-service", language="java", sextant_version="0.1.0",
        fact_schema_version="1.0.0", scanner_id="asm", scanner_version="9.7",
        content_hash="sha256:a", origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT, redaction_set_hash="sha256:b",
    )
    listener = "com/acme/notify/OrderListener#"
    handle = "com/acme/notify/OrderListener#onOrderCreated()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1", symbol=handle, construct_kind=ConstructKind.METHOD,
            enclosing=listener,
        ),
        AnnotationFact(
            document_id="doc_1", target=listener, retention="runtime",
            use=AnnotationUse(annotation="com/acme/messaging/annotation/Listener#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1", target=listener, retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/Topic#", args={"value": ["orders."]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1", target=handle, retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/OnMessage#",
                args={"value": ["created"]},
            ),
        ),
    ]
    write_fact_file(root / "OrderListener.jsonl", document, facts)


def test_derive_endpoints_carries_the_catalogs_own_protocol_and_direction_when_non_http(
    tmp_path: Path,
):
    _invented_listener_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = Catalog(
        id="invented-listener", style="annotation_driven", protocol="message",
        direction="outbound", requires=("annotation_args",),
        matches={
            "type_annotation": "com/acme/messaging/annotation/Listener#",
            "path_prefix_from": {
                "annotation": "com/acme/messaging/annotation/Topic#", "arg": "value",
            },
            "method_annotations": [
                {
                    "fqn": "com/acme/messaging/annotation/OnMessage#",
                    "http_method": "PUBLISH", "path_arg": "value",
                },
            ],
        },
    )

    skipped = derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert len(rows) == 1
    assert rows[0]["protocol"] == "message"
    assert rows[0]["direction"] == "outbound"
    assert rows[0]["protocol"] != "http"
    assert rows[0]["direction"] != "inbound"


def test_derive_endpoints_skips_and_reports_when_a_required_capability_is_missing(
    tmp_path: Path,
):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    catalog = Catalog(
        id="spring-web", style="annotation_driven", protocol="http", direction="inbound",
        requires=("annotation_args",), matches={},
    )

    skipped = derive_endpoints(workspace, [catalog], capabilities=set())
    workspace.close()

    assert skipped == [SkippedCatalog("spring-web", ("annotation_args",))]


def test_derive_endpoints_sql_names_no_framework_when_read():
    """D02's central claim — frameworks are data, engines are generic
    interpreters — is falsified the moment a framework's own identifier
    shows up as a literal in the engine's SQL. A second annotation_driven
    framework must be addable as one YAML file with no change here."""
    sql = Path(
        __file__
    ).parents[2] / "src" / "sextant" / "storage" / "duckdb" / "derive_endpoints.sql"
    text = sql.read_text(encoding="utf-8").lower()
    assert "spring" not in text
    assert "org/springframework" not in text
