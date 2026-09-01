from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.artifacts import ArtifactReader, ReadRequest, group_files_by_reader
from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.descriptors import DescriptorInterpreter
from sextant.application.ports.detector import Detector, ModuleModel, select_detector
from sextant.application.ports.progress import Progress
from sextant.application.ports.scanner import Scanner, ScanRequest, select_scanner
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.domain.factfile import (
    append_fact_file,
    config_fact_target,
    read_fact_tree,
    schema_fact_target,
    write_fact_file,
)
from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
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
    # Schema source files a schema reader could not turn into an
    # embedded_descriptor fact — every file in a `.proto` root protoc failed
    # to compile, or a `.avsc` file that was not readable JSON — named the
    # same way `uncovered` is, for the same FR-17 reason.
    schema_sources_not_compiled: tuple[str, ...] = ()
    # Embedded schema payloads the interpreter could not turn into a
    # declared_shape (compiled or source, whichever origin failed), named by
    # their own `symbol` (interpret_descriptors's own failure list).
    descriptors_not_interpreted: tuple[str, ...] = ()


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
    # Defaulted for the same reason. A caller supplying neither this nor any
    # schema reader interprets no schema at all — never constructed here:
    # the naming it closes over is per-language knowledge only the cli
    # composition root may import (ARCHITECTURE §10's JVM-confinement rule;
    # `DescriptorInterpreter`'s own docstring says why this is a Protocol
    # rather than the interpreter's own `GeneratedNaming` parameter).
    interpret: DescriptorInterpreter | None = None,
) -> AnalyzeResult:
    progress.define("detect", "detect")
    progress.define("scan", "scan")
    progress.define("read", "read")
    progress.define("interpret", "interpret schemas")
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
                target = config_fact_target(fact_root, document.relative_path)
                write_fact_file(target, document, config_facts)
                entries += len(config_facts)
    # Schema roots are read the same way, through the same registry — a
    # reader claims its own extension (`avsc`/`proto`) regardless of which
    # root it is handed, so nothing here has to know which readers are
    # schema readers versus config readers. Kept as its own loop rather than
    # folded into the one above only because its target is `schema_fact_target`,
    # not `config_fact_target` (2F's collision rule: a schema document must
    # never compete with a same-named config file for one fact-file target).
    schema_sources_not_compiled: list[str] = []
    for root in module.schema_roots:
        for reader, owned in group_files_by_reader(list_files(root), readers):
            request = ReadRequest(
                module_id=module.module_id, version=module.version, files=owned, root=root
            )
            for document, schema_facts in reader.read(request):
                target = schema_fact_target(fact_root, document.relative_path)
                write_fact_file(target, document, schema_facts)
                entries += len(schema_facts)
                if document.partial:
                    schema_sources_not_compiled.append(document.relative_path)
    progress.finish("read", f"{entries} entries")

    # Interpretation is wired ONCE, here, over compiled and source
    # descriptors together (2G design §3) — never per-reader, and never
    # inside `resolve` (M04 is language- and format-blind). Compiled
    # `embedded_descriptor` facts were already written to disk by the
    # scanner above; the schema readers' own facts were just written by the
    # loop above this one — `read_fact_tree` is how this stage sees both
    # without touching the filesystem itself (ARCHITECTURE §10).
    progress.start("interpret")
    descriptors_not_interpreted: tuple[str, ...] = ()
    if interpret is not None:
        pairs = read_fact_tree(fact_root)
        documents_by_id = {document.document_id: document for document, _ in pairs}
        descriptors = [
            fact for _, facts in pairs for fact in facts if isinstance(fact, EmbeddedDescriptorFact)
        ]
        shapes, failed = interpret(descriptors)
        descriptors_not_interpreted = tuple(failed)
        kept = _prefer_compiled(shapes)
        by_document: dict[str, list[DeclaredShapeFact]] = {}
        for shape in kept:
            by_document.setdefault(shape.document_id, []).append(shape)
        # Sorted so the write order — and therefore nothing observable about
        # it — never depends on dict iteration order (NFR-1).
        for document_id in sorted(by_document):
            document = documents_by_id[document_id]
            target = schema_fact_target(fact_root, document.relative_path)
            append_fact_file(target, document, by_document[document_id])
    progress.finish("interpret", f"{len(descriptors_not_interpreted)} not interpreted")

    progress.start("resolve")
    report = resolve(workspace, fact_root, catalogs, scanner.capabilities())
    progress.finish("resolve", f"{len(report.endpoints)} endpoints")

    return AnalyzeResult(
        module,
        report,
        scan_report.scanner_id,
        scan_report.scanner_version,
        scan_report.uncovered,
        tuple(schema_sources_not_compiled),
        descriptors_not_interpreted,
    )


def _prefer_compiled(shapes: list[DeclaredShapeFact]) -> list[DeclaredShapeFact]:
    """DR-4: a schema compiled into the artifact outranks the same schema
    read from a repository file. Applied here, after interpretation, rather
    than inside the interpreter — pools are per-origin there (a descriptor
    file name collides across origins otherwise), so comparing origins by
    `schema_name` needs both already interpreted. Deterministic: the input
    is already sorted by `interpret_descriptors`'s own contract, and this
    only filters, never reorders."""
    compiled_names = {shape.schema_name for shape in shapes if shape.origin == "compiled"}
    return [
        shape
        for shape in shapes
        if shape.origin == "compiled" or shape.schema_name not in compiled_names
    ]
