import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import resolve
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
JAR = REPO / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
FIXTURE = REPO / "fixtures" / "orders-service"


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
