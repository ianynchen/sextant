"""The analyze stage (M03): detect, scan, read config and schema sources,
interpret embedded schemas, resolve — one pass per module, every fact
written to disk before `resolve` ever runs (M04 reads the whole tree, not a
stream).

No new scanner capability gates `embedded_descriptor`/`declared_shape` (2G
design, Task 4 ruling): a module that carries no schema payload simply
produces no declared shape, the same honest absence an untyped scanner
already leaves for a construct it never emits — no catalog's `requires`
needs a name for that."""

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
    config_fact_target,
    read_fact_tree,
    schema_fact_target,
    write_fact_file,
)
from sextant.domain.facts import DeclaredShapeFact, Document, EmbeddedDescriptorFact, Fact
from sextant.domain.resource_files import list_files


def _config_files(module: ModuleModel, root: Path) -> tuple[Path, ...]:
    """Everything under a resource root that the schema loop below is not
    already reading.

    One schema root genuinely lives INSIDE a resource root — Spring GraphQL's
    SDL ships on the classpath, so the build puts it under
    `src/main/resources/graphql` — and the resource walk is recursive. One
    registry serves both loops, so without this the same reader would be
    handed the same file twice: two `Document` records for one source file
    (D00 §7), and two identical descriptors for the interpreter to read as a
    schema that declares every one of its types twice.
    """
    return tuple(
        file
        for file in list_files(root)
        if not any(file.is_relative_to(schema_root) for schema_root in module.schema_roots)
    )


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
        for reader, owned in group_files_by_reader(_config_files(module, root), readers):
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
        # Every prior declared_shape fact is dropped here, kept nowhere —
        # this run's own interpretation is about to recompute the complete,
        # current answer, and a fact file is written WHOLE below, never
        # appended to. Without this, a second `analyze` into the same
        # workspace would read back the first run's own declared_shape facts
        # alongside the fresh ones and pile up a duplicate set every time.
        by_document_id: dict[str, tuple[Path, Document, list[Fact]]] = {}
        descriptors: list[EmbeddedDescriptorFact] = []
        for target, document, facts in read_fact_tree(fact_root):
            carried: list[Fact] = [
                fact for fact in facts if not isinstance(fact, DeclaredShapeFact)
            ]
            by_document_id[document.document_id] = (target, document, carried)
            descriptors.extend(fact for fact in carried if isinstance(fact, EmbeddedDescriptorFact))

        shapes, failed = interpret.interpret(descriptors)
        descriptors_not_interpreted = tuple(failed)
        kept_shapes: dict[str, list[DeclaredShapeFact]] = {}
        for shape in _prefer_compiled(shapes):
            kept_shapes.setdefault(shape.document_id, []).append(shape)
        # Sorted so the write order — and therefore nothing observable about
        # it — never depends on dict iteration order (NFR-1).
        for document_id in sorted(kept_shapes):
            target, document, carried = by_document_id[document_id]
            # Written into the document's OWN fact file, wherever it already
            # is — a compiled document's own file the scanner wrote, or a
            # schema reader's own file from the read step above — never a
            # NEW file: a second `Document` record for a document that
            # already has one would double it in the workspace's own
            # document count (D00 §7's one-record-per-source-file rule).
            write_fact_file(target, document, [*carried, *kept_shapes[document_id]])
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
