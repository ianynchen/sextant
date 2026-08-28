from pathlib import Path

import pytest

from sextant.application.resolve.endpoints import (
    Catalog,
    CatalogError,
    SkippedCatalog,
    derive_endpoints,
    load_catalogs,
)
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "catalogs"

# A second, invented annotation_driven shape — deliberately not Spring — so a
# test can hand `derive_endpoints` two catalogs that are genuinely different.
_INVENTED_LISTENER = Catalog(
    id="invented-listener",
    style="annotation_driven",
    protocol="message",
    direction="outbound",
    requires=("annotation_args",),
    matches={
        "type_annotation": "com/acme/messaging/annotation/Listener#",
        "mapping": {
            "path_from": ["value"],
            "method_from": "method",
            "all_methods": ["PUBLISH"],
            "prefix_annotation": "com/acme/messaging/annotation/Topic#",
            "annotations": [
                {"fqn": "com/acme/messaging/annotation/OnMessage#", "method": ["PUBLISH"]},
            ],
        },
    },
)


def test_catalog_declares_its_style_and_required_capabilities_when_loaded():
    catalogs = load_catalogs(CATALOGS)
    spring = next(c for c in catalogs if c.id == "spring-web")
    assert spring.style == "annotation_driven"
    assert spring.protocol == "http"
    assert spring.direction == "inbound"
    assert "annotation_args" in spring.requires


def test_catalog_maps_post_mapping_to_the_post_method():
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")
    annotations = spring.matches["mapping"]["annotations"]
    methods = {m["fqn"]: m.get("method") for m in annotations}
    assert methods["org/springframework/web/bind/annotation/PostMapping#"] == ["POST"]


def test_catalog_leaves_request_mapping_without_a_preset_method():
    """`@RequestMapping` takes its method from its own argument, and means every
    method when it has none — so it must declare no default here, or the
    fallback that produces one endpoint per method can never be reached."""
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")
    annotations = spring.matches["mapping"]["annotations"]
    request_mapping = next(
        m
        for m in annotations
        if m["fqn"] == "org/springframework/web/bind/annotation/RequestMapping#"
    )
    assert "method" not in request_mapping


def _controller_facts(root: Path) -> None:
    """Mirrors the exact shape the ASM extractor emits for a Spring
    controller (verified against fixtures/orders-service): a type-level
    RestController with no argument, a RequestMapping whose `value` is a
    one-element JSON array, one PostMapping and one GetMapping with no
    argument at all, and one GetMapping whose `value` is a one-element
    array. Method symbols carry the descriptor-hash disambiguator D00 §1
    requires on every method, because that is what the extractor writes."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
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
    controller = "com/acme/orders/OrderController#"
    create = "com/acme/orders/OrderController#create(sig_1f0a4c2e)."
    get = "com/acme/orders/OrderController#get(sig_74b3d901)."
    list_ = "com/acme/orders/OrderController#list(sig_08c5be17)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=create,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=get,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=list_,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=create,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/PostMapping#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=get,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": ["/{id}"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=list_,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={},
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
        document_id="doc_1",
        relative_path="com/acme/notify/OrderListener.java",
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
    listener = "com/acme/notify/OrderListener#"
    handle = "com/acme/notify/OrderListener#onOrderCreated(sig_3d92af60)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=listener,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/messaging/annotation/Listener#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=listener,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/Topic#",
                args={"value": ["orders."]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
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

    skipped = derive_endpoints(workspace, [_INVENTED_LISTENER], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert len(rows) == 1
    assert rows[0]["protocol"] == "message"
    assert rows[0]["direction"] == "outbound"
    assert rows[0]["protocol"] != "http"
    assert rows[0]["direction"] != "inbound"


def test_derive_endpoints_keeps_both_catalogs_results_when_two_catalogs_match(
    tmp_path: Path,
):
    """D02 §5: "Two catalogs may both match; both produce endpoints, and
    duplicates merge on wire identity." A derivation that replaces the table
    per catalog makes the last catalog the only catalog, and every endpoint
    the earlier ones found disappears with no skip, no gap, and no warning —
    the silent-loss failure capability gating exists to prevent."""
    _controller_facts(tmp_path / "facts")
    _invented_listener_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")

    skipped = derive_endpoints(
        workspace, [spring, _INVENTED_LISTENER], capabilities={"annotation_args"}
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert {(r["protocol"], r["method"], r["path"]) for r in rows} == {
        ("http", "POST", "/v1/orders"),
        ("http", "GET", "/v1/orders/{id}"),
        ("http", "GET", "/v1/orders"),
        ("message", "PUBLISH", "orders.created"),
    }


def test_derive_endpoints_merges_on_wire_identity_when_two_catalogs_match_the_same_code(
    tmp_path: Path,
):
    """The other half of D02 §5: accumulating must not double-report. Two
    catalogs that describe the same annotations — the realistic case of a
    framework catalog and its umbrella — see the same routes, and the wire
    is where sameness is decided."""
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")
    twin = Catalog(**{**vars(spring), "id": "spring-web-twin"})

    derive_endpoints(workspace, [spring, twin], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 3


def test_derive_endpoints_skips_and_reports_when_a_required_capability_is_missing(
    tmp_path: Path,
):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    catalog = Catalog(
        id="spring-web",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=("annotation_args",),
        matches={},
    )

    skipped = derive_endpoints(workspace, [catalog], capabilities=set())
    workspace.close()

    assert skipped == [SkippedCatalog("spring-web", ("annotation_args",))]


def test_derive_endpoints_sql_names_no_framework_when_read():
    """D02's central claim — frameworks are data, engines are generic
    interpreters — is falsified the moment a framework's own identifier
    shows up as a literal in the engine's SQL. A second annotation_driven
    framework must be addable as one YAML file with no change here."""
    sql = (
        Path(__file__).parents[2]
        / "src"
        / "sextant"
        / "storage"
        / "duckdb"
        / "derive_endpoints.sql"
    )
    text = sql.read_text(encoding="utf-8").lower()
    assert "spring" not in text
    assert "org/springframework" not in text


def _scalar_path_facts(root: Path) -> None:
    """A framework whose path arguments are declared `String`, not `String[]`.
    JAX-RS `@Path` is the real one: its `value()` is a plain String, so the
    compiled annotation argument is a bare JSON string and not a one-element
    array."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
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
    resource = "com/acme/rest/OrderResource#"
    find = "com/acme/rest/OrderResource#find(sig_5ea17c38)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=find,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=resource,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Resource#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=resource,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Path#",
                args={"value": "/rest/orders"},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=find,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Get#", args={"value": "/{id}"}),
        ),
    ]
    write_fact_file(root / "OrderResource.jsonl", document, facts)


_SCALAR_PATH_CATALOG = Catalog(
    id="invented-scalar-path",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=("annotation_args",),
    matches={
        "type_annotation": "com/acme/rest/Resource#",
        "mapping": {
            "path_from": ["value"],
            "method_from": "method",
            "all_methods": ["GET"],
            # Not a mapping annotation: this catalog is the JAX-RS shape, where
            # the type carries the path and the method carries the verb.
            "prefix_annotation": "com/acme/rest/Path#",
            "annotations": [{"fqn": "com/acme/rest/Get#", "method": ["GET"]}],
        },
    },
)


def test_derive_endpoints_reads_a_scalar_annotation_argument_when_it_is_not_an_array(
    tmp_path: Path,
):
    """Reading only element 0 of an array silently yields NULL on a scalar, and
    the path collapses to the prefix alone — a wrong route reported with full
    `resolved`/`compiler` confidence. Spring's `value()` is `String[]`, so this
    is invisible there and fatal for any catalog whose argument is a plain
    String."""
    _scalar_path_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_SCALAR_PATH_CATALOG], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("GET", "/rest/orders/{id}")]


_VALID_CATALOG = """id: invented
style: annotation_driven
protocol: http
direction: inbound
matches: {}
"""


def _catalog_dir(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "invented.yml").write_text(text, encoding="utf-8")
    return root


def test_load_catalogs_names_the_file_and_the_value_when_a_protocol_is_not_a_closed_set_member(
    tmp_path: Path,
):
    """`protocol` and `direction` are closed sets in D00: a value outside one
    is a typo, not a new kind of endpoint. Unchecked, it does not stay in the
    file — it is bound into the derivation and published in metadata.json,
    where it is indistinguishable from something observed. The message names
    the file and the value, because that is what a reader needs (GUIDELINES
    §9)."""
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("http", "htpp"))

    with pytest.raises(CatalogError) as failure:
        load_catalogs(directory)

    assert "htpp" in str(failure.value)
    assert "invented.yml" in str(failure.value)
    assert "http" in str(failure.value)


def test_load_catalogs_rejects_a_direction_outside_the_closed_set(tmp_path: Path):
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("inbound", "incoming"))

    with pytest.raises(CatalogError) as failure:
        load_catalogs(directory)

    assert "incoming" in str(failure.value)
    assert "invented.yml" in str(failure.value)


def test_load_catalogs_names_the_missing_field_when_a_catalog_omits_one(tmp_path: Path):
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("style: annotation_driven\n", ""))

    with pytest.raises(CatalogError) as failure:
        load_catalogs(directory)

    assert "style" in str(failure.value)
    assert "invented.yml" in str(failure.value)


def test_load_catalogs_accepts_a_catalog_whose_values_are_all_in_the_closed_sets(
    tmp_path: Path,
):
    catalog = load_catalogs(_catalog_dir(tmp_path, _VALID_CATALOG))[0]
    assert (catalog.protocol, catalog.direction) == ("http", "inbound")
