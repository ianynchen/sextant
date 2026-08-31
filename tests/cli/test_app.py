import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.cli.app import cli
from sextant.cli.resources import catalogs_dir, extractor_jar
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"
_JAR = extractor_jar()
_CATALOGS = catalogs_dir()


class _NoCapabilitiesScanner:
    """Wraps the real scanner but reports no capabilities, so any catalog
    with a `requires` entry is genuinely skipped — Phase 1 ships only one
    catalog, so this is the only way to reproduce a skip without adding a
    second one."""

    def __init__(self, inner: AsmScanner) -> None:
        self._inner = inner

    def accepts(self, languages: set[str]) -> bool:
        return self._inner.accepts(languages)

    def capabilities(self) -> set[str]:
        return set()

    def rank(self) -> int:
        return self._inner.rank()

    def scan(self, request: ScanRequest) -> ScanReport:
        return self._inner.scan(request)


def test_analyze_writes_metadata_and_reports_endpoint_count(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    # 2E-prep Task 6: +1 (`GET /composed`, the effective-annotations
    # pre-pass's `@ApiGet` composition). Phase 2E Task 7: +2 more
    # (`GET /api/orders`, `GET /api/composed`, the inherited-mappings
    # pass). Phase 2E Task 9: +10 more (the `combinator` engine's WebFlux
    # functional-routing tree, both DSLs) — see test_pipeline.py's own
    # dedicated row-level test for the full breakdown.
    assert metadata["endpoints"]["inbound"]["http"] == 31


def test_export_writes_a_bundle_with_manifest_graph_and_facts(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "graph" / "endpoints.parquet").is_file()
    facts_files = list((bundle / "facts").rglob("*.parquet"))
    assert facts_files, "facts/ must not be empty"


def test_render_writes_the_document_after_analyze(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    result = runner.invoke(cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "POST" in document and "/v1/orders" in document


def test_render_exits_nonzero_with_a_message_when_no_workspace_exists(tmp_path: Path):
    result = CliRunner().invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "module analyze" in result.output


def test_render_names_the_catalog_and_capability_analyze_skipped(tmp_path: Path):
    """A weaker scanner must degrade *visibly* (M04, FR-17) — including
    through `render`, which reads back what `analyze` already established
    rather than recomputing it."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        result = analyze(
            path=FIXTURE,
            workspace=workspace,
            detectors=[MavenDetector()],
            scanners=[_NoCapabilitiesScanner(AsmScanner(_JAR))],
            catalogs=YamlCatalogSource(_CATALOGS),
            fact_root=tmp_path / "facts",
            progress=NullProgress(),
        )
        assert result.report.skipped_catalogs, "the catalog was not actually skipped"
        write_metadata(
            tmp_path / "metadata.json",
            result.module,
            result.report,
            "asm",
            "9.7",
            "deadbeef",
        )
    finally:
        workspace.close()

    render_result = CliRunner().invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert render_result.exit_code == 0, render_result.output
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "spring-web" in document
    assert "annotation_args" in document


def test_analyze_reports_nothing_uncovered_now_that_the_nested_class_is_read(tmp_path: Path):
    """The fixture's nested class was this module's one compiled source the
    facts did not account for, and `uncovered` existed to say so. It is scanned
    now (D00 §2 — one class file is one document), so the honest answer is an
    empty list and a gap section that names no unread source. The channel is
    still load-bearing — a Kotlin class whose metadata cannot be decoded still
    travels it — which is why the assertion is that it is empty here, not that
    it is gone."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["uncovered"] == []

    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "Not read" not in document.split("## Known gaps", 1)[1]
