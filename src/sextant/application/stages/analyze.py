from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.detector import Detector, ModuleModel
from sextant.application.ports.progress import Progress
from sextant.application.ports.scanner import Scanner, ScanRequest
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.pipeline import ResolveReport, resolve


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
    path: Path, workspace: Workspace, detector: Detector, scanner: Scanner,
    catalogs_dir: Path, fact_root: Path, progress: Progress,
) -> AnalyzeResult:
    progress.define("detect", "detect")
    progress.define("scan", "scan")
    progress.define("resolve", "resolve")

    progress.start("detect")
    model = detector.detect(path)
    module = model.modules[0]
    progress.finish("detect", f"modules: {len(model.modules)}")

    progress.start("scan")
    scan_report = scanner.scan(ScanRequest(
        module_id=module.module_id, coordinates=module.coordinates,
        version=module.version, classes_dir=module.output_dirs[0], out_dir=fact_root,
    ))
    progress.finish("scan", f"{scan_report.facts} facts")

    progress.start("resolve")
    report = resolve(workspace, fact_root, catalogs_dir, scanner.capabilities())
    progress.finish("resolve", f"{len(report.endpoints)} endpoints")

    return AnalyzeResult(
        module, report, scan_report.scanner_id, scan_report.scanner_version,
        scan_report.uncovered,
    )
