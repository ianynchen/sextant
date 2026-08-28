import json
import subprocess
from pathlib import Path
from typing import cast

import click

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.stages.analyze import analyze
from sextant.cli.progress import RichProgress
from sextant.egress.render.document import render_module_document
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_REPO = Path(__file__).parents[3]
_JAR = _REPO / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
_CATALOGS = _REPO / "catalogs"


def _commit_of(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() or "unknown"


def _workspace_dir_of(path: Path, workspace_dir: Path | None) -> Path:
    return workspace_dir or (path / ".sextant")


@click.group()
def cli() -> None:
    """Sextant — architecture from compiled code."""


@cli.group()
def module() -> None:
    """Operate on one buildable unit."""


@module.command("analyze")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
def module_analyze(path: Path, workspace_dir: Path | None) -> None:
    workspace_dir = _workspace_dir_of(path, workspace_dir)
    progress = RichProgress()
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        result = analyze(
            path=path, workspace=workspace, detector=MavenDetector(),
            scanner=AsmScanner(_JAR), catalogs_dir=_CATALOGS,
            fact_root=workspace_dir / "facts", progress=progress,
        )
        write_metadata(
            workspace_dir / "metadata.json", result.module, result.report,
            result.scanner_id, result.scanner_version, _commit_of(path),
        )
    finally:
        workspace.close()
        progress.close()
    click.echo(json.dumps({"endpoints": len(result.report.endpoints)}))


@module.command("render")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
def module_render(path: Path, workspace_dir: Path | None) -> None:
    """Reads the workspace `analyze` left behind — it never re-detects,
    re-scans, or re-resolves (M00 "no analysis"; the workspace persists
    precisely so render is a cheap read)."""
    workspace_dir = _workspace_dir_of(path, workspace_dir)
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"
    if not metadata_path.is_file() or not db_path.is_file():
        raise click.ClickException(
            f"no analysis found at {workspace_dir} — run `sextant module analyze {path}` first."
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    module_info = metadata["module"]
    reconstructed = ModuleModel(
        module_id=module_info["id"], coordinates=module_info["id"], version="unknown",
        root=path, kind=module_info["kind"], languages=frozenset(module_info["languages"]),
        source_roots=(), output_dirs=(),
    )
    # Read back what `analyze` already established, rather than re-deriving
    # it — a skipped catalog must stay visible on `render` too (M04, FR-17).
    skipped_catalogs = [
        SkippedCatalog(skipped["catalog_id"], tuple(skipped["missing_capabilities"]))
        for skipped in metadata.get("skipped_catalogs", [])
    ]

    workspace = DuckDbWorkspace(db_path)
    try:
        report = ResolveReport(
            facts_loaded=cast(int, workspace.query("facts")[0]["facts"]),
            endpoints=workspace.query("endpoints"),
            coverage=workspace.query("coverage")[0],
            skipped_catalogs=skipped_catalogs,
        )
        text = render_module_document(reconstructed, report, _commit_of(path))
        target = workspace_dir / "render" / "architecture.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    finally:
        workspace.close()
    click.echo(str(target))
