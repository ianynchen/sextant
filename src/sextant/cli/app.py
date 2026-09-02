import hashlib
import json
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import click

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.stages.analyze import AnalyzeResult, analyze
from sextant.cli.progress import RichProgress
from sextant.cli.resources import catalogs_dir, extractor_jar
from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.egress.export.manifest import write_manifest
from sextant.egress.render.document import render_module_document
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.detect.sextant_config import SextantConfigError
from sextant.ingress.extract.jvm.generated_naming import JvmGeneratedNaming
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.ingress.interpret.descriptors import interpret_descriptors
from sextant.ingress.read.avsc import AvscReader
from sextant.ingress.read.graphql_sdl import GraphqlSdlReader
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.proto_source import ProtoSourceReader
from sextant.ingress.read.wsdl_xsd import WsdlXsdReader
from sextant.ingress.read.yaml_config import YamlConfigReader
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The registries the composition root builds (ARCHITECTURE §6). Order is the
# statement of precedence where two adapters could both accept.


class _JvmDescriptorInterpreter:
    """The `DescriptorInterpreter` port (application/ports/descriptors.py),
    adapted: binds the JVM's own generated-class naming — constructed only
    here, per ARCHITECTURE §10's JVM-confinement rule — into
    `interpret_descriptors`, so `analyze` never has to import either. An
    object with a named method, like every other adapter this composition
    root wires in, never a bare callable."""

    def __init__(self) -> None:
        self._naming = JvmGeneratedNaming()

    def interpret(
        self, descriptors: Sequence[EmbeddedDescriptorFact]
    ) -> tuple[list[DeclaredShapeFact], list[str]]:
        return interpret_descriptors(descriptors, self._naming)


def _commit_of(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _remote_of(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _module_commit_of(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "log", "-1", "--format=%H", "--", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _catalog_hash(catalogs: Path) -> str:
    digest = hashlib.sha256()
    for catalog in sorted(catalogs.glob("*.yml")):
        digest.update(catalog.name.encode("utf-8"))
        digest.update(catalog.read_bytes())
    return "sha256:" + digest.hexdigest()


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
        result = _analyzed(path, workspace, workspace_dir, progress)
        write_metadata(
            workspace_dir / "metadata.json",
            result.module,
            result.report,
            result.scanner_id,
            result.scanner_version,
            _commit_of(path),
            result.uncovered,
            resolved_config=workspace.query("resolved_config"),
            schema_sources_not_compiled=result.schema_sources_not_compiled,
            descriptors_not_interpreted=result.descriptors_not_interpreted,
            libraries_not_scanned=result.libraries_not_scanned,
        )
    finally:
        workspace.close()
        progress.close()
    click.echo(json.dumps({"endpoints": len(result.report.endpoints)}))


def _analyzed(
    path: Path, workspace: DuckDbWorkspace, workspace_dir: Path, progress: RichProgress
) -> AnalyzeResult:
    """`analyze`, with the one failure a USER caused turned into the message a
    user reads. A malformed `.sextant.yml` is Sextant's own input written
    wrong (D04 §2a's refusal) — a stack trace here would report a mistake in
    the analysed repository as a crash in the tool, the same way the two
    `no analysis found` messages below exist so a missing workspace does
    not."""
    try:
        return analyze(
            path=path,
            workspace=workspace,
            detectors=[MavenDetector()],
            scanners=[AsmScanner(extractor_jar())],
            catalogs=YamlCatalogSource(catalogs_dir()),
            fact_root=workspace_dir / "facts",
            progress=progress,
            readers=[
                PropertiesReader(),
                YamlConfigReader(),
                AvscReader(),
                ProtoSourceReader(),
                GraphqlSdlReader(),
                WsdlXsdReader(),
            ],
            interpret=_JvmDescriptorInterpreter(),
        )
    except SextantConfigError as refused:
        raise click.ClickException(str(refused)) from refused


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
        module_id=module_info["id"],
        coordinates=module_info["id"],
        version="unknown",
        root=path,
        kind=module_info["kind"],
        languages=frozenset(module_info["languages"]),
        source_roots=(),
        output_dirs=(),
        # Read back rather than re-detected, the same way a skipped catalog is:
        # `render` never re-runs detection, so the coordinates that resolved to
        # nothing would otherwise vanish from the document `analyze` recorded
        # them for (FR-17).
        libraries_not_resolved=tuple(metadata.get("libraries_not_resolved", [])),
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
            shapes=workspace.query("shapes"),
            # Not recoverable from the workspace: a type nothing could expand
            # gets an open, zero-field shape row, which is indistinguishable
            # from a class that genuinely has no fields. So it rides
            # metadata.json the same way a skipped catalog does, rather than
            # being re-derived here from rows that cannot answer.
            unexpanded_types=tuple(metadata.get("shapes", {}).get("unexpanded_types", [])),
        )
        text = render_module_document(
            reconstructed,
            report,
            _commit_of(path),
            tuple(metadata.get("uncovered", [])),
            shape_fields=workspace.query("shape_fields"),
            resolved_config=workspace.query("resolved_config"),
            open_questions=workspace.query("open_questions"),
            library_symbols=workspace.query("library_symbols"),
            libraries_not_scanned=tuple(metadata.get("libraries_not_scanned", [])),
        )
        target = workspace_dir / "render" / "architecture.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    finally:
        workspace.close()
    click.echo(str(target))


@module.command("export")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def module_export(path: Path, workspace_dir: Path | None, out_dir: Path | None) -> None:
    """Writes the analysis out as a D06 bundle: Parquet plus a manifest. Reads
    what `analyze` left — it never re-analyzes (M08). Publishing the directory
    anywhere is the caller's business; Sextant does not talk to artifact
    stores."""
    workspace_dir = _workspace_dir_of(path, workspace_dir)
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"
    if not metadata_path.is_file() or not db_path.is_file():
        raise click.ClickException(
            f"no analysis found at {workspace_dir} — run `sextant module analyze {path}` first."
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    commit = str(metadata["provenance"]["commit"])
    bundle_name = re.sub(r"[^A-Za-z0-9._-]", "-", str(metadata["module"]["id"])) + "@" + commit
    bundle = (out_dir or workspace_dir / "bundles") / bundle_name

    workspace = DuckDbWorkspace(db_path)
    try:
        tables = workspace.export_tables(bundle)
        facts_files = workspace.export_facts(bundle)
    finally:
        workspace.close()
    write_manifest(
        bundle / "manifest.json",
        metadata,
        source={"repo": _remote_of(path), "commit": commit},
        catalog_hash=_catalog_hash(catalogs_dir()),
        module_commit=_module_commit_of(path),
        tables=tables,
        facts_files=facts_files,
    )
    click.echo(str(bundle))
