"""The analyze stage (M03): detect, scan, read config and schema sources,
interpret embedded schemas, resolve — one pass per module, every fact
written to disk before `resolve` ever runs (M04 reads the whole tree, not a
stream).

No new scanner capability gates `embedded_descriptor`/`declared_shape` (2G
design, Task 4 ruling): a module that carries no schema payload simply
produces no declared shape, the same honest absence an untyped scanner
already leaves for a construct it never emits — no catalog's `requires`
needs a name for that."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.artifacts import (
    ArtifactReader,
    ReadRequest,
    file_kind,
    group_files_by_reader,
)
from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.descriptors import DescriptorInterpreter
from sextant.application.ports.detector import Detector, ModuleModel, select_detector
from sextant.application.ports.progress import Progress
from sextant.application.ports.scanner import (
    ScanError,
    Scanner,
    ScanRequest,
    select_scanner,
)
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import (
    config_fact_target,
    discard_library_facts,
    library_fact_root,
    read_fact_tree,
    schema_fact_target,
    write_fact_file,
)
from sextant.domain.facts import (
    DeclaredShapeFact,
    Document,
    EmbeddedDescriptorFact,
    Fact,
    ModuleFact,
)
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.resource_files import list_files

# The module fact's own document (`_write_module_fact`). Its `relative_path`,
# its `language` and its fact file's name are one literal: the document IS the
# module, not a file under a root, and naming it three different ways would
# invite a reader to look for three things.
_MODULE_DOCUMENT = "module"
# The facility that produced it — the detector, through this stage. Named the
# way `ingress/read`'s own `SCANNER_ID` names the config-reading facility (D00
# §2: `scanner_id` names the facility, never the format).
_MODULE_SCANNER_ID = "sextant-detector"
# Restated rather than imported: these three values are `ingress/read`'s, and
# `application` may not import `ingress` (the layering contract). They must
# stay equal to that module's own copies — a document written with a different
# `fact_schema_version` than its siblings would claim a schema nobody shipped.
SEXTANT_VERSION = "0.1.0"
FACT_SCHEMA_VERSION = "1.0.0"
SCANNER_VERSION = "0.1.0"
NO_REDACTION_HASH = "sha256:none"


def _config_files(
    module: ModuleModel, root: Path, schema_readers: Sequence[ArtifactReader], ignore: IgnoreRules
) -> tuple[Path, ...]:
    """Everything under a resource root that the schema loop below is not
    already reading.

    One schema root genuinely lives INSIDE a resource root — Spring GraphQL's
    SDL ships on the classpath, so the build puts it under
    `src/main/resources/graphql` — and the resource walk is recursive. One
    registry serves both loops, so without this the same reader would be
    handed the same file twice: two `Document` records for one source file
    (D00 §7), and two identical descriptors for the interpreter to read as a
    schema that declares every one of its types twice.

    The partition is per FILE, not per directory: a schema root is a
    directory, and an ordinary resource sitting in one (a `messages.properties`
    beside the SDL) is still an ordinary resource. Only a file a schema reader
    actually claims belongs to the other loop — everything else keeps the
    resource-root-relative identity its fact file is targeted by.
    """
    return tuple(
        file
        # `ignore.repo_root`, never `module.root`: the root a pattern is
        # matched relative to must be the root the rules were LOADED at, or a
        # reactor-root pattern is compared against a submodule-relative path
        # and matches nothing (`A-M16`). The two coincide for a single-module
        # repository, which is why passing `module.root` looked right.
        for file in list_files(root, ignore.repo_root, ignore)
        if not (
            any(file.is_relative_to(schema_root) for schema_root in module.schema_roots)
            and any(reader.accepts(file_kind(file)) for reader in schema_readers)
        )
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
    # Opted-into libraries whose archive RESOLVED but could not be scanned —
    # `<coordinate>: <reason>`, the shape `uncovered` already uses. Its own
    # list beside the detector's `libraries_not_resolved`, deliberately: the
    # two fail at different stages and are closed by different actions (build
    # or install the dependency, versus the archive is unreadable), and one
    # list would leave a reader to work out which of the two they are looking
    # at from the reason text alone.
    libraries_not_scanned: tuple[str, ...] = ()
    # The detector's own `RepositoryModel.notes` (2M design §1c), carried out
    # unchanged — this stage neither adds to nor filters them, the same
    # pass-through `uncovered` and the two lists above already are.
    notes: tuple[str, ...] = ()


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
    # Threaded to the detector and nowhere else (2M design §1 network-posture
    # bullet): today's port parameter exists on every detector and nothing
    # passed it, so an offline-only build could never opt into the one online
    # retry `allow_resolve` is for. Defaulted so every existing caller stays
    # offline exactly as before.
    allow_resolve: bool = False,
    # The root a `.sextantignore` sits at and every pattern in it is written
    # against (D04 §3, `A-M16`). Defaulted to None so every existing caller —
    # every test that builds this pipeline by hand — keeps the module-root
    # behaviour it had; `api.py` passes the analysed root, which is the
    # reactor's for a submodule and the module's own for a single-module
    # repository.
    ignore_root: Path | None = None,
) -> AnalyzeResult:
    progress.define("detect", "detect")
    progress.define("scan", "scan")
    progress.define("read", "read")
    progress.define("interpret", "interpret schemas")
    progress.define("resolve", "resolve")

    progress.start("detect")
    model = select_detector(detectors, path).detect(path, allow_resolve=allow_resolve)
    module = model.modules[0]
    progress.finish("detect", f"modules: {len(model.modules)}")

    # The detector's conclusions become facts here, before anything else is
    # written — D00 §5's `module` kind, which nothing constructed until this
    # phase needed the declared dependency coordinates in the workspace
    # (2O design §2a, ruling R9). Rewritten whole on every run, like every
    # other fact file.
    _write_module_fact(fact_root, module)

    # Selected here, not by the caller: a scanner is chosen per language
    # (ARCHITECTURE §7) and the languages are not known until detection has
    # run. The registry is the composition root's; the moment is the pipeline's.
    scanner = select_scanner(scanners, module.languages)
    progress.start("scan")
    # Every library fact from a PREVIOUS run of this workspace goes first,
    # before a single one of this run's is written. A fact file is written
    # whole, so a library still opted in overwrites itself — but one that was
    # removed from `.sextant.yml`, or renamed, overwrites nothing, and the
    # resolve below reads the whole tree. Without this, opting OUT would leave
    # the rows exactly where they were and the opt-in would be a decision that
    # cannot be taken back.
    #
    # BEFORE the module's own scan, not after it: `facts/lib/` is a directory
    # name, and a module holding a top-level `lib` package writes its own class
    # facts there (the same target collision `facts/config` and `facts/schema`
    # already live with). Discarding first means such a module rewrites them a
    # line later; discarding after would delete facts this run had just written.
    #
    # The delete-then-rewrite window assumes ONE analyze per fact root at a
    # time. That is what a workspace is (M00: one module, one workspace, one
    # command), and nothing here takes a lock — a second concurrent analyze
    # into the same workspace would see the gap between the discard and the
    # rewrite. Stated because it is load-bearing and free to satisfy, not
    # because it is enforced.
    discard_library_facts(fact_root)
    scan_report = scanner.scan(
        ScanRequest(
            module_id=module.module_id,
            coordinates=module.coordinates,
            version=module.version,
            classes_dir=module.output_dirs[0],
            out_dir=fact_root,
        )
    )
    # Each opted-into library (D04 §2a) is scanned by the SAME scanner, through
    # the same port, into its own subtree — nothing here knows it is reading an
    # archive rather than a directory, which is the scanner's business. Three
    # things differ from the module's own scan and each is deliberate: the
    # library's OWN coordinates and version, so a scanned symbol's identity
    # says which artifact declares it rather than borrowing this module's;
    # `origin`, so every document it writes records the library it came from
    # (D00 §2); and the fact subtree, so a library class can never compete with
    # a module class for one fact-file target. `module_id` stays the analysed
    # module's: these facts are part of THIS module's analysis, whoever
    # compiled the bytecode.
    scanned_facts = scan_report.facts
    uncovered = list(scan_report.uncovered)
    libraries_not_scanned: list[str] = []
    # `.sextantignore` is never consulted here: a library archive is not a
    # repo file to enumerate, and its `.class` walk is out of scope for the
    # ignore matcher by design (2K design §2) — `IgnoreRules` governs the
    # repo's own file enumerations (config, schema, resource walks) only.
    for library in module.library_roots:
        try:
            library_report = scanner.scan(
                ScanRequest(
                    module_id=module.module_id,
                    coordinates=library.coordinate.replace(":", "/"),
                    version=library.version,
                    classes_dir=library.archive,
                    out_dir=library_fact_root(fact_root, library.coordinate),
                    origin=library.coordinate,
                )
            )
        except ScanError as failure:
            # An archive that cannot be read is a gap about THAT library, never
            # the end of the module's analysis: the module's own facts are
            # already on disk and are not made wrong by a dependency nobody
            # could open. The module's own scan above is deliberately outside
            # this — that one failing IS the analysis failing.
            #
            # Whatever the scan managed to write first goes with it. A backend
            # writes each document as it reaches it, so a failure partway
            # through an archive leaves a fraction of a library on disk —
            # indistinguishable, once loaded, from all of a smaller one.
            discard_library_facts(fact_root, library.coordinate)
            # The archive PATH is replaced by the coordinate wherever the
            # backend's own message names it. This string travels — into
            # metadata.json, the rendered gaps list, a published bundle — and a
            # path under someone's home directory identifies nothing off the
            # machine that wrote it (D00 §2's rule, which holds for every
            # reader-facing string and not only for the document record). The
            # coordinate IS the portable name for exactly that path, so the
            # substitution loses nothing and the reason survives intact.
            reason = str(failure).replace(str(library.archive), library.coordinate)
            libraries_not_scanned.append(f"{library.coordinate}: {reason}")
            continue
        scanned_facts += library_report.facts
        uncovered.extend(library_report.uncovered)
    progress.finish("scan", f"{scanned_facts} facts")

    # Ingress stays model-blind (design §1): every parseable config file
    # under every resource root is read, sorted by relative path (NFR-1),
    # and written through the same fact-file writer the scanner uses.
    # Readers never see the Workspace port — this stage is the write.
    progress.start("read")
    entries = 0
    # `.sextantignore` (2K design §2), loaded once and applied at both walk
    # loops below through `list_files` — a file it excludes is read by
    # neither loop, config or schema.
    #
    # **`ignore_root`, not `module.root` (`A-M16`).** D04 §3 is emphatic, and
    # is itself an amendment: "One file, at the REPOSITORY root, and every
    # pattern in it is matched against a path made relative to THAT root."
    # Loading at `module.root` made that false for every multi-module reactor
    # — `api.py` analyzes each submodule with its own root, so a
    # `.sextantignore` at the reactor root was never read for any of them, and
    # a pattern written relative to the reactor root would not have matched if
    # it had. For a single-module repository the two roots coincide and this
    # is the same load it always was, which is why `module.root` is still the
    # fallback: a caller that does not know the analysed root gets the
    # behaviour it had rather than a silently wider jail.
    #
    # `IgnoreRules.matches` relativizes each path against the root it was
    # loaded at, so a submodule's files match reactor-root patterns exactly as
    # the document says. The BUILT-IN layer is unaffected either way — it
    # applies at every depth (`domain/ignorefile.py`), which is why this was a
    # coverage gap in the repository-authored layer and never a credential
    # leak.
    #
    # **A reactor root is not always an ancestor of its own modules**, and that
    # is not a corner: `<module>../orders-service</module>` is legal Maven and
    # `fixtures/orders-reactor` is exactly that shape. A path outside the root
    # has no root-relative form at all, so a pattern written against that root
    # could not address it even in principle — this falls back to the module's
    # own root there, which is the behaviour that shipped. It stops being right
    # if a repository ever wants one ignore file to govern modules it does not
    # contain, which is a question about where the file lives rather than about
    # how it is read.
    ignore = IgnoreRules.load(
        ignore_root
        if ignore_root is not None and module.root.is_relative_to(ignore_root)
        else module.root
    )
    # Which loop a reader serves is the reader's own declaration (the
    # `ArtifactReader` port's `reads_schema_sources`), never a guess from the
    # root a file was found under: since 2H one schema root lives inside a
    # resource root, so the root no longer tells the two apart.
    schema_readers = [reader for reader in readers if reader.reads_schema_sources]
    for root in module.resource_roots:
        for reader, owned in group_files_by_reader(
            _config_files(module, root, schema_readers, ignore), readers
        ):
            request = ReadRequest(
                module_id=module.module_id, version=module.version, files=owned, root=root
            )
            for document, config_facts in reader.read(request):
                target = config_fact_target(fact_root, document.relative_path)
                write_fact_file(target, document, config_facts)
                entries += len(config_facts)
    # Schema roots are read the same way, through the same registry — a
    # reader claims its own extension (`avsc`/`proto`/`graphqls`) regardless
    # of which root it is handed, and only the schema readers are offered
    # these files, so an ordinary resource that happens to sit in a schema
    # directory stays with the loop above. Kept as its own loop rather than
    # folded into the one above only because its target is `schema_fact_target`,
    # not `config_fact_target` (2F's collision rule: a schema document must
    # never compete with a same-named config file for one fact-file target).
    schema_sources_not_compiled: list[str] = []
    for root in module.schema_roots:
        for reader, owned in group_files_by_reader(
            list_files(root, ignore.repo_root, ignore), schema_readers
        ):
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
        tuple(uncovered),
        tuple(schema_sources_not_compiled),
        descriptors_not_interpreted,
        tuple(libraries_not_scanned),
        model.notes,
    )


def _write_module_fact(fact_root: Path, module: ModuleModel) -> None:
    """The detector's own conclusions, written as a fact like any other
    (D00 §5's `module` kind, and its own "why `module` is a fact and not a
    passing argument": three later components need it and never see the
    detector, and a stage resumed from disk never runs one).

    **What it carries today is the coordinate half** — `dependency_coordinates`
    — because that is the half both build systems can answer and the half a
    dependency-gated catalog reads (2O design §2a, ruling R9). Classpath
    TIERING, which D00 also names here, needs a resolved archive per entry and
    stays unwritten rather than half-invented.

    The document is synthesized rather than read from a file: this stage may
    not touch the filesystem (ARCHITECTURE §10), so `content_hash` is the hash
    of the module's own detected identity — the content this document actually
    records — which changes exactly when that identity does. `relative_path`
    is the literal `module`, and the fact file sits at `facts/module.jsonl`,
    which shares its one collision risk with `facts/config`, `facts/schema`
    and `facts/lib`: a top-level class named `module` in the default package
    would write to the same target.
    """
    identity = "\n".join(
        [module.module_id, module.version, module.kind, *module.dependency_coordinates]
    )
    document = Document(
        document_id=hashlib.sha256(f"module:{module.module_id}".encode()).hexdigest(),
        relative_path=_MODULE_DOCUMENT,
        module_id=module.module_id,
        language=_MODULE_DOCUMENT,
        sextant_version=SEXTANT_VERSION,
        fact_schema_version=FACT_SCHEMA_VERSION,
        scanner_id=_MODULE_SCANNER_ID,
        scanner_version=SCANNER_VERSION,
        content_hash="sha256:" + hashlib.sha256(identity.encode()).hexdigest(),
        # The module's own COORDINATES, not a path: this document was not read
        # from a classpath entry at all, and D00 §2's rule that a path under
        # someone's home identifies nothing off the machine that wrote it
        # applies here with nothing to trade against it — a filesystem root
        # would also make two runs of the same module at two checkout paths
        # write different bytes (NFR-1, and `test_analyze_library_wiring`'s
        # own byte-identity pins).
        origin_entry=module.coordinates,
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash=NO_REDACTION_HASH,
    )
    fact = ModuleFact(
        document_id=document.document_id,
        module_id=module.module_id,
        module_kind=module.kind,
        languages=sorted(module.languages),
        source_roots=[root.as_posix() for root in module.source_roots],
        output_dirs=[directory.as_posix() for directory in module.output_dirs],
        dependency_coordinates=list(module.dependency_coordinates),
    )
    write_fact_file(fact_root / f"{_MODULE_DOCUMENT}.jsonl", document, [fact])


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
