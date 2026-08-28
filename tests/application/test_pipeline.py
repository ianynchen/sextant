import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import resolve
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
JAR = REPO / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
FIXTURE = REPO / "fixtures" / "orders-service"
CATALOGS = REPO / "catalogs"


def test_resolve_finds_the_three_fixture_endpoints_when_run_end_to_end(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    facts = tmp_path / "facts"
    AsmScanner(JAR).scan(ScanRequest(
        module_id="com.acme:orders-service", coordinates="com.acme/orders-service",
        version="1.0.0", classes_dir=FIXTURE / "target" / "classes", out_dir=facts,
    ))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(workspace, facts, REPO / "catalogs", {"annotation_args", "typed_signatures"})
    workspace.close()

    routes = {(e["method"], e["path"]) for e in report.endpoints}
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }
    assert report.skipped_catalogs == []


def test_resolve_reports_the_skip_instead_of_crashing_when_no_catalog_is_satisfied(
    tmp_path: Path,
):
    """A weaker scanner must degrade visibly: when capability gating skips
    every catalog, resolve() still returns a ResolveReport naming what was
    skipped and why, rather than raising because the endpoints table was
    never derived (the one path capability gating exists to protect)."""
    facts = tmp_path / "facts"
    document = Document(
        document_id="doc_1", relative_path="com/acme/orders/OrderController.java",
        module_id="com.acme:orders-service", language="java", sextant_version="0.1.0",
        fact_schema_version="1.0.0", scanner_id="asm", scanner_version="9.7",
        content_hash="sha256:a", origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT, redaction_set_hash="sha256:b",
    )
    write_fact_file(facts / "OrderController.jsonl", document, [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(workspace, facts, CATALOGS, {"typed_signatures"})
    workspace.close()

    assert report.endpoints == []
    assert report.skipped_catalogs == [
        SkippedCatalog("spring-web", ("annotation_args",)),
    ]
