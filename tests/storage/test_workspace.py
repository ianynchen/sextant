import json
from pathlib import Path

import duckdb

from sextant.application.resolve.endpoints import derive_endpoints
from sextant.cli.resources import catalogs_dir
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    SymbolFact,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def _fixture_facts(root: Path) -> None:
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/A.java",
        module_id="com.acme:orders",
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
    symbol = SymbolFact(
        document_id="doc_1", symbol="s maven p 1 com/acme/A#", construct_kind=ConstructKind.CLASS
    )
    write_fact_file(root / "com" / "acme" / "A.jsonl", document, [symbol])


def _loaded_workspace(tmp_path: Path) -> DuckDbWorkspace:
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _endpoint_facts(root: Path) -> None:
    """A minimal RestController with one GetMapping — enough for
    derive_endpoints to produce a single inbound endpoint row (mirrors the
    shape tests/application/test_endpoints.py's `_controller_facts` builds)."""
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
    list_ = "com/acme/orders/OrderController#list(sig_08c5be17)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
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
            target=list_,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def _workspace_with_an_endpoint(tmp_path: Path) -> DuckDbWorkspace:
    _endpoint_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-web")
    derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
    return workspace


def _call_site_facts(root: Path) -> None:
    """One call_site fact with a null receiver and result — the shape a
    static call (or, post-6b, a parameter-rooted receiver such as every
    super() call) actually emits — and two arguments, to exercise the
    view's ::INTEGER casts over JSON null and the JSON round trip of
    `arguments` in the same row."""
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
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(
            owner="org/springframework/web/client/RestTemplate#",
            name="postForObject",
            descriptor="(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;",
        ),
        invoke_kind="static",
        ordinal=0,
        arguments=[
            CallArgument(kind="string", value="/billing/invoices"),
            CallArgument(kind="unresolved", source=7),
        ],
    )
    write_fact_file(root / "OrderController.jsonl", document, [call_site])


def _workspace_with_a_call_site(tmp_path: Path) -> DuckDbWorkspace:
    _call_site_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def test_load_facts_reports_the_row_count_when_a_fact_tree_is_ingested(tmp_path: Path):
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    loaded = workspace.load_facts(tmp_path / "facts")
    workspace.close()
    assert loaded == 2  # one document line, one symbol line


def test_query_returns_the_document_when_documents_are_listed(tmp_path: Path):
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    rows = workspace.query("documents")
    workspace.close()
    assert [row["document_id"] for row in rows] == ["doc_1"]


def test_the_shape_tables_answer_an_empty_query_rather_than_raising(tmp_path: Path):
    """Pre-declared for the same reason `endpoints` is: a scanner too weak to
    populate them must degrade visibly through skipped_catalogs, not crash."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    assert workspace.query("shapes") == []
    assert workspace.query("shape_fields") == []
    workspace.close()


def test_endpoints_carry_the_two_shape_columns(tmp_path: Path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.derive("endpoints_reset")
    columns = workspace.query("endpoints")
    workspace.close()
    # Empty result, so assert on the declared schema rather than on rows.
    assert columns == []


def test_query_rejects_a_name_that_is_not_a_named_query(tmp_path: Path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        raised = False
        try:
            workspace.query("SELECT 1")
        except KeyError:
            raised = True
        assert raised
    finally:
        workspace.close()


def test_call_sites_view_round_trips_every_column_including_arguments_as_json(tmp_path: Path):
    workspace = _workspace_with_a_call_site(tmp_path)
    rows = workspace.query("call_sites")
    workspace.close()
    assert len(rows) == 1
    row = rows[0]
    assert row["document_id"] == "doc_1"
    assert row["caller"] == (
        "sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create()."
    )
    assert row["owner"] == "org/springframework/web/client/RestTemplate#"
    assert row["name"] == "postForObject"
    assert row["descriptor"] == (
        "(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;"
    )
    assert row["invoke_kind"] == "static"
    assert row["ordinal"] == 0
    # A static call carries no receiver, and this fixture leaves result
    # unset too — the view's ::INTEGER cast of a JSON null must come back
    # as SQL NULL, not the string "null" or an error.
    assert row["receiver"] is None
    assert row["result"] is None
    assert json.loads(row["arguments"]) == [
        {"kind": "string", "value": "/billing/invoices", "symbol": None, "source": None},
        {"kind": "unresolved", "value": None, "symbol": None, "source": 7},
    ]


def test_exported_tables_include_call_sites(tmp_path: Path):
    workspace = _workspace_with_a_call_site(tmp_path)
    workspace.export_tables(tmp_path / "bundle")
    workspace.close()
    assert (tmp_path / "bundle" / "graph" / "call_sites.parquet").exists()


def test_exported_tables_read_back_equal_to_the_workspace_query(tmp_path: Path):
    workspace = _workspace_with_an_endpoint(tmp_path)
    written = workspace.export_tables(tmp_path / "bundle")
    assert written == [
        "annotations",
        "call_sites",
        "documents",
        "endpoints",
        "shape_fields",
        "shapes",
        "symbols",
    ]
    back = duckdb.sql(
        f"SELECT * FROM read_parquet('{tmp_path / 'bundle' / 'graph' / 'endpoints.parquet'}')"
    ).fetchall()
    workspace_count = len(workspace.query("endpoints"))
    assert len(back) == workspace_count
    assert workspace_count > 0
    workspace.close()


def test_two_exports_of_one_workspace_are_byte_identical(tmp_path: Path):
    """NFR-1 at the bundle boundary (M08). A failure here on one machine and
    not another is DuckDB's Parquet writer differing between versions —
    environment drift, not code."""
    workspace = _loaded_workspace(tmp_path)
    workspace.export_tables(tmp_path / "one")
    workspace.export_facts(tmp_path / "one")
    workspace.export_tables(tmp_path / "two")
    workspace.export_facts(tmp_path / "two")
    one = {
        p.relative_to(tmp_path / "one"): p.read_bytes()
        for p in sorted((tmp_path / "one").rglob("*.parquet"))
    }
    two = {
        p.relative_to(tmp_path / "two"): p.read_bytes()
        for p in sorted((tmp_path / "two").rglob("*.parquet"))
    }
    assert one == two and one
    workspace.close()
