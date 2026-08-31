from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.artifacts import ArtifactReader, ReadRequest, group_files_by_reader
from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.detector import Detector, ModuleModel, select_detector
from sextant.application.ports.progress import Progress
from sextant.application.ports.scanner import Scanner, ScanRequest, select_scanner
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.domain.factfile import write_fact_file
from sextant.domain.resource_files import list_files


@dataclass(frozen=True)
class AnalyzeResult:
    module: ModuleModel
    report: ResolveReport
    scanner_id: str
    scanner_version: str
    # Compiled sources the scan did not account for. Carried out of the stage
    # rather than dropped here: a source nothing read is a gap the artifacts
    # must name (FR-17, M03), and this is the only place that knows it.
    uncovered: tuple[str, ...] = ()


def analyze(
    path: Path,
    workspace: Workspace,
    detectors: Sequence[Detector],
    scanners: Sequence[Scanner],
    catalogs: CatalogSource,
    fact_root: Path,
    progress: Progress,
    # Defaulted so every existing caller — every test that builds this
    # pipeline by hand — keeps working unchanged. A module with no resource
    # roots, or a registry with no reader, reads nothing here regardless.
    readers: Sequence[ArtifactReader] = (),
) -> AnalyzeResult:
    progress.define("detect", "detect")
    progress.define("scan", "scan")
    progress.define("read", "read")
    progress.define("resolve", "resolve")

    progress.start("detect")
    model = select_detector(detectors, path).detect(path)
    module = model.modules[0]
    progress.finish("detect", f"modules: {len(model.modules)}")

    # Selected here, not by the caller: a scanner is chosen per language
    # (ARCHITECTURE §7) and the languages are not known until detection has
    # run. The registry is the composition root's; the moment is the pipeline's.
    scanner = select_scanner(scanners, module.languages)
    progress.start("scan")
    scan_report = scanner.scan(
        ScanRequest(
            module_id=module.module_id,
            coordinates=module.coordinates,
            version=module.version,
            classes_dir=module.output_dirs[0],
            out_dir=fact_root,
        )
    )
    progress.finish("scan", f"{scan_report.facts} facts")

    # Ingress stays model-blind (design §1): every parseable config file
    # under every resource root is read, sorted by relative path (NFR-1),
    # and written through the same fact-file writer the scanner uses.
    # Readers never see the Workspace port — this stage is the write.
    progress.start("read")
    entries = 0
    for root in module.resource_roots:
        for reader, owned in group_files_by_reader(list_files(root), readers):
            request = ReadRequest(
                module_id=module.module_id, version=module.version, files=owned, root=root
            )
            for document, config_facts in reader.read(request):
                target = fact_root / "config" / Path(document.relative_path).with_suffix(".jsonl")
                write_fact_file(target, document, config_facts)
                entries += len(config_facts)
    progress.finish("read", f"{entries} config entries")

    progress.start("resolve")
    report = resolve(workspace, fact_root, catalogs, scanner.capabilities())
    progress.finish("resolve", f"{len(report.endpoints)} endpoints")

    return AnalyzeResult(
        module,
        report,
        scan_report.scanner_id,
        scan_report.scanner_version,
        scan_report.uncovered,
    )
