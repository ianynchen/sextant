import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import click
from pydantic import ValidationError

from sextant.agents import AGENT_REGISTRY
from sextant.application.enrich.tools import ToolDefinition, ToolExecutor
from sextant.application.enrich.validate import stale_claims
from sextant.application.ports.detector import (
    Detector,
    ModuleModel,
    RepositoryModel,
    select_detector,
)
from sextant.application.ports.enrichment import EnrichmentAgentError
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.stages import enrich as enrich_stage
from sextant.application.stages.analyze import AnalyzeResult, analyze
from sextant.cli.progress import RichProgress
from sextant.cli.resources import catalogs_dir, extractor_jar, instructions_path
from sextant.domain.enrichment import ENRICHMENT_FILE, EnrichmentOverlay, load_overlay
from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import RedactionError, Redactor
from sextant.egress.export.manifest import write_manifest
from sextant.egress.render.document import (
    AssembledDocument,
    ClaimRedactionError,
    assemble_module_document,
    markdown_document,
)
from sextant.egress.render.html import html_document
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.detect.sextant_config import (
    EnrichDefaults,
    SextantConfigError,
    read_enrich_defaults,
    read_redaction_rules,
)
from sextant.ingress.extract.jvm.generated_naming import JvmGeneratedNaming
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.ingress.interpret.descriptors import interpret_descriptors
from sextant.ingress.read.registry import READERS
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The registries the composition root builds (ARCHITECTURE §6). Order is the
# statement of precedence where two adapters could both accept.

# The one real `Detector` registry in this file (2M Task 2 review): a future
# detector added to only one of two hand-kept lists would send the other
# path to `select_detector`'s own uncaught `NoAdapterError`. Every command
# below that needs a real detector reads this list rather than writing its
# own.
_DETECTORS: list[Detector] = [MavenDetector()]


def _modules_json_path(path: Path) -> Path:
    """`modules.json`'s own location (ARCHITECTURE §8's file layout:
    `<repo-root>/.sextant/modules.json`) — named once so the write site in
    `module_analyze` and the read sites in `render`/`enrich`/`export`'s
    refusal cannot drift apart. Not inside any MODULE's own workspace
    (`--workspace` is refused at a multi-module root — there is no single
    one to name); this is the root's own `.sextant/`, holding only the
    inventory, never a full workspace's `facts/`/`render/`/`workspace.duckdb`."""
    return path / ".sextant" / "modules.json"


def _root_relative(root: Path, target: Path) -> str:
    """`target`, spelled relative to `root` (2M Task 2 fix round 1, F5) —
    `os.path.relpath`, never `Path.relative_to`: a `<module>` may climb OUT
    of the aggregator's own directory (`fixtures/orders-reactor`'s own
    adoption of `fixtures/orders-service`, by `../orders-service`, is
    exactly this shape), and `relative_to` refuses anything that is not a
    strict descendant. Both resolved first, so the spelling in
    `modules.json` and in a refusal message is the SAME regardless of
    whether `root`/`target` reached here as relative or absolute strings —
    stable across invocation spellings, the same portability D00 §2 already
    states for every other reader-facing path this codebase writes out."""
    return os.path.relpath(target.resolve(), start=root.resolve())


def _skip_reason(module: ModuleModel) -> str | None:
    """Why a module is skip-listed rather than analyzed, or `None` when it
    should be analyzed (2M design §2, ruled amendment — fix round 1). The
    kind gate inverts to skip only what is KNOWN not to be a service:
    `library` (Gradle-only today — Maven never returns it) and a leaf
    `<packaging>pom</packaging>` (a BOM or aggregation-only sibling with no
    classes to scan — without this exception, any reactor containing one
    hard-fails the whole run, since its own scan has no `target/classes`
    directory to read). EVERYTHING ELSE is analyzed, `kind == "undetermined"`
    included: `kind` stays honestly `undetermined` in `modules.json` and
    `metadata.json` either way — only `analyzed` flips. The original design
    skipped every non-`service` module; the flagship multi-module fixture
    it was meant to serve (`spring-petclinic-microservices`) classifies all
    eight of its modules `undetermined`, so that rule returned zero
    analyzed output on the repository the feature exists for."""
    if module.kind == "library":
        return "kind is library"
    if module.packaging == "pom":
        return "packaging is pom"
    return None


def _module_row(root: Path, module: ModuleModel, analyzed: bool) -> dict[str, object]:
    """One `modules.json` row (2M Task 2 fix round 1, F9: single-sited here
    rather than written out at both the skip and the analyzed call site)."""
    return {
        "dir": _root_relative(root, module.root),
        "module_id": module.module_id,
        "kind": module.kind,
        "analyzed": analyzed,
    }


class _KnownModuleDetector:
    """Adapts one already-detected `ModuleModel` back into the `Detector`
    Protocol, so `analyze`'s own internal `select_detector(...).detect(path)`
    call (M00's "one module, one workspace, one command" contract, unchanged
    by this task) is satisfied from data this command already has, rather
    than invoking the real detector a second time (2M Task 2 review's hard
    gate — a build tool invoked to detect must never run twice per
    `analyze`, and once Task 3's `GradleDetector` lands, a second
    invocation is a second subprocess). `_DETECTORS` above is called exactly
    once per `module analyze` — the reactor walk if the root is one, a plain
    detect otherwise — and every per-module `analyze()` call is driven from
    that single result through an instance of this class."""

    def __init__(self, module: ModuleModel, notes: tuple[str, ...]) -> None:
        self._module = module
        self._notes = notes

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=self._module.root, modules=(self._module,), notes=self._notes)


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


def _refuse_if_unanalyzed(path: Path, workspace_dir: Path) -> None:
    """The `no analysis found` refusal every EXIT command shares (`render`,
    `enrich`, `export` — M00's "no analysis" rule: none of them re-detects,
    re-scans, or re-resolves). Widened for a multi-module root (2M design
    §2): `modules.json` sits at the root's OWN `.sextant/` (ARCHITECTURE
    §8), never inside a per-module workspace — `--workspace` is refused at
    a multi-module root, so there is no single one to find it absent from —
    and its presence with no per-module workspace at `workspace_dir` means
    the caller pointed an EXIT command at the reactor root rather than at
    one of the modules it names, so the refusal reads out that list instead
    of the generic message."""
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"
    if metadata_path.is_file() and db_path.is_file():
        return
    modules_path = _modules_json_path(path)
    if modules_path.is_file():
        modules = json.loads(modules_path.read_text(encoding="utf-8"))["modules"]
        dirs = ", ".join(sorted(str(module["dir"]) for module in modules))
        raise click.ClickException(
            f"{path} is a multi-module root; analyze it, then run this command against "
            f"one of: {dirs}"
        )
    raise click.ClickException(
        f"no analysis found at {workspace_dir} — run `sextant module analyze {path}` first."
    )


def _redactor_for(path: Path) -> Redactor:
    """The redactor both EXITS use (2K design §1): the built-in rule set,
    widened by this module's own `.sextant.yml`. Built at the composition root
    so render and export mask by one set and the manifest can name it.

    Both refusals become the message a user reads, the same way `_analyzed`
    turns a malformed `.sextant.yml` into one: a `redact:` section written
    wrong is a mistake in the analysed repository, and a stack trace would
    report it as a crash in the tool."""
    try:
        return Redactor.from_rules(read_redaction_rules(path))
    except (SextantConfigError, RedactionError) as refused:
        raise click.ClickException(str(refused)) from refused


def _overlay_for(path: Path) -> EnrichmentOverlay | None:
    """The module's enrichment overlay, or `None` where it has none (2K design
    §6). An overlay that is present and malformed becomes the message a user
    reads, for the reason `_redactor_for` turns a bad `redact:` section into
    one: it is Sextant's own program artifact written wrong, and a stack trace
    would report it as a crash in the tool."""
    try:
        return load_overlay(path)
    except ValidationError as refused:
        raise click.ClickException(
            f"{path / ENRICHMENT_FILE} is not a valid overlay: {refused}"
        ) from refused


def _enrich_defaults_for(path: Path) -> EnrichDefaults:
    """This module's `enrich:` defaults (2K design §3), or a message a user
    reads instead of a stack trace — the same turn `_redactor_for` gives a
    bad `redact:` section, for the same reason (D04 §2a's refusal)."""
    try:
        return read_enrich_defaults(path)
    except SextantConfigError as refused:
        raise click.ClickException(str(refused)) from refused


@click.group()
def cli() -> None:
    """Sextant — architecture from compiled code."""


@cli.group()
def module() -> None:
    """Operate on one buildable unit."""


@module.command("analyze")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--allow-resolve",
    "allow_resolve",
    is_flag=True,
    default=False,
    help="Permit one online dependency-resolution retry when the detector needs it.",
)
def module_analyze(path: Path, workspace_dir: Path | None, allow_resolve: bool) -> None:
    # Detection runs FIRST, before anything below creates so much as a
    # directory (2M design §2): `DuckDbWorkspace`'s own constructor is what
    # makes a workspace and its `.duckdb` file exist, so a refused detection
    # must be discovered here, ahead of any of that, or a repository Sextant
    # cannot analyze would still leave one behind. Exactly ONE real
    # detection happens per invocation (2M Task 2 review's hard gate) — the
    # reactor walk below if `path` is a multi-module root, a single module
    # otherwise — and every per-module `analyze()` call beneath it is driven
    # from THIS result via `_KnownModuleDetector`, never a second real
    # `detect()` call. `ValueError` alongside `SextantConfigError`: the
    # reactor walk's own refusals (a `<modules>` cycle, a `<module>` naming
    # a directory with no `pom.xml` — 2M Task 2 fix round 1, F2) are the
    # same class of "the analysed repository is written wrong" mistake, not
    # a crash in the tool.
    try:
        model = select_detector(_DETECTORS, path).detect(path, allow_resolve=allow_resolve)
    except (SextantConfigError, ValueError) as refused:
        raise click.ClickException(str(refused)) from refused

    # `model.multi_module`, never `len(model.modules) > 1` (2M Task 2 fix
    # round 1, F1): whether `path` ITSELF declared `<modules>` is the gate —
    # a reactor naming exactly one child is still a reactor, and that
    # child's own analysis belongs in ITS OWN workspace, not `path`'s.
    if model.multi_module:
        # `--workspace` names ONE module's workspace (M00); a multi-module
        # root has no single workspace of its own to name — every module
        # gets its own, always at its own `<module-dir>/.sextant` (2M design
        # §2).
        if workspace_dir is not None:
            raise click.ClickException(
                f"{path} is a multi-module root — --workspace is refused there; it names "
                "one module's workspace, and every module here gets its own"
            )
        _module_analyze_reactor(path, model, allow_resolve)
        return

    workspace_dir = _workspace_dir_of(path, workspace_dir)
    result = _analyze_into(path, model.modules[0], model.notes, workspace_dir, allow_resolve)
    click.echo(json.dumps({"endpoints": len(result.report.endpoints)}))


def _analyze_into(
    path: Path,
    module: ModuleModel,
    notes: tuple[str, ...],
    workspace_dir: Path,
    allow_resolve: bool,
) -> AnalyzeResult:
    """One module, analyzed into one workspace, and its `metadata.json`
    written — the body every `module analyze` invocation shares, whether
    `path` is a single-module root or one module inside a just-walked
    reactor (2M design §2). `module`/`notes` are ALREADY the result of the
    one real detection `module_analyze` performed above; `_KnownModuleDetector`
    replays them so `analyze()`'s own internal `select_detector(...).detect(path)`
    call never triggers a second one."""
    # A stale rendered document must never survive a re-analyze (2K Task 8
    # review): `analyze` never otherwise touches `render/` — that is
    # `render`'s own output — so without this, re-analyzing a module after
    # its code changed would leave the OLD architecture.md/.html sitting on
    # disk, and `module_enrich`'s own "no rendered document" refusal below
    # would pass against it, handing an agent a brief composed against code
    # that no longer exists. The whole directory is removed rather than its
    # two known files, deliberately: whatever `render` ever writes there
    # stops being trustworthy the moment the graph it describes changes.
    render_dir = workspace_dir / "render"
    if render_dir.is_dir():
        shutil.rmtree(render_dir)
    progress = RichProgress()
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        result = _analyzed(
            path,
            workspace,
            workspace_dir,
            progress,
            [_KnownModuleDetector(module, notes)],
            allow_resolve=allow_resolve,
        )
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
            detect_notes=result.notes,
        )
    finally:
        workspace.close()
        progress.close()
    return result


# The table's dir column (2M Task 2 fix round 1, F8): a cap, not a
# guess at a terminal width — one fixed number keeps the column, and
# therefore the two columns after it, aligned regardless of how long any
# one module's relative path happens to be.
_TABLE_DIR_WIDTH = 50


def _truncated(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _module_analyze_reactor(path: Path, model: RepositoryModel, allow_resolve: bool) -> None:
    """Every module a just-walked reactor named that is not KNOWN not to be
    a service, each analyzed into its own `<module-dir>/.sextant` workspace
    exactly as a single-module run would (2M design §2, ruled amendment —
    `_skip_reason` is the whole gate). `modules.json` then names every
    module found, analyzed or not, at `path` — the artifact `render`/
    `enrich`/`export`'s own refusal below reads. One failing module fails
    loudly and stops the run (`--keep-going` is not offered in 2M):
    `modules.json` is written only once every module that was going to be
    analyzed has been, so a stopped run leaves no artifact claiming a
    module finished when it did not — and any STALE inventory from a PRIOR
    run is removed at the START, for the same reason (2M Task 2 fix round
    1, F7): a run that fails partway must not leave the previous run's
    `analyzed: true` rows looking current."""
    modules_path = _modules_json_path(path)
    modules_path.unlink(missing_ok=True)

    rows: list[dict[str, object]] = []
    for module in model.modules:
        relative_dir = _root_relative(path, module.root)
        reason = _skip_reason(module)
        if reason is not None:
            click.echo(f"skipped {relative_dir} ({module.module_id}): {reason}")
            rows.append(_module_row(path, module, analyzed=False))
            continue
        workspace_dir = _workspace_dir_of(module.root, None)
        try:
            result = _analyze_into(module.root, module, model.notes, workspace_dir, allow_resolve)
        except Exception as failure:  # deliberately broad, see below
            # A batch run's own failure must name WHICH module failed — left
            # uncaught, the module's own exception would read as this
            # command crashing rather than as that module's analysis
            # failing, with no way to tell which of several modules it was.
            raise click.ClickException(
                f"{relative_dir} ({module.module_id}) failed to analyze: {failure}"
            ) from failure
        click.echo(
            f"analyzed {relative_dir} ({module.module_id}): "
            f"{len(result.report.endpoints)} endpoints"
        )
        rows.append(_module_row(path, module, analyzed=True))

    rows.sort(key=lambda row: cast(str, row["dir"]))
    modules_path.parent.mkdir(parents=True, exist_ok=True)
    modules_path.write_text(json.dumps({"modules": rows}, indent=2) + "\n", encoding="utf-8")

    # No header, no rows, for an empty reactor (2M Task 2 fix round 1, F8):
    # a table with a header and nothing under it reads as a tool that found
    # nothing to say, not as the honest empty case it is.
    if not rows:
        return
    click.echo()
    click.echo(f"{'dir':<{_TABLE_DIR_WIDTH}} {'kind':<15} analyzed")
    for row in rows:
        dir_cell = _truncated(cast(str, row["dir"]), _TABLE_DIR_WIDTH)
        analyzed_cell = "yes" if row["analyzed"] else "no"
        click.echo(f"{dir_cell:<{_TABLE_DIR_WIDTH}} {cast(str, row['kind']):<15} {analyzed_cell}")


def _analyzed(
    path: Path,
    workspace: DuckDbWorkspace,
    workspace_dir: Path,
    progress: RichProgress,
    detectors: Sequence[Detector],
    allow_resolve: bool = False,
) -> AnalyzeResult:
    """`analyze`, with the one failure a USER caused turned into the message a
    user reads. A malformed `.sextant.yml` is Sextant's own input written
    wrong (D04 §2a's refusal) — a stack trace here would report a mistake in
    the analysed repository as a crash in the tool, the same way the two
    `no analysis found` messages below exist so a missing workspace does
    not. `detectors` is always the caller's own `_KnownModuleDetector`
    (2M Task 2 review) — this function itself never picks a real one."""
    try:
        return analyze(
            path=path,
            workspace=workspace,
            detectors=detectors,
            scanners=[AsmScanner(extractor_jar())],
            catalogs=YamlCatalogSource(catalogs_dir()),
            fact_root=workspace_dir / "facts",
            progress=progress,
            readers=READERS,
            interpret=_JvmDescriptorInterpreter(),
            allow_resolve=allow_resolve,
        )
    except SextantConfigError as refused:
        raise click.ClickException(str(refused)) from refused


def _reconstructed_report(
    path: Path, workspace: DuckDbWorkspace, metadata: dict[str, Any]
) -> tuple[ModuleModel, ResolveReport]:
    """`analyze`'s own `ModuleModel`/`ResolveReport`, read back from
    `metadata.json` and the workspace rather than re-derived — the "no
    analysis" rule (M00) `render` and `enrich` (2K design §8) both keep:
    neither re-detects, re-scans, or re-resolves."""
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
        # neither reader re-runs detection, so the coordinates that resolved to
        # nothing would otherwise vanish from the document `analyze` recorded
        # them for (FR-17).
        libraries_not_resolved=tuple(metadata.get("libraries_not_resolved", [])),
    )
    # Read back what `analyze` already established, rather than re-deriving
    # it — a skipped catalog must stay visible here too (M04, FR-17).
    skipped_catalogs = [
        SkippedCatalog(skipped["catalog_id"], tuple(skipped["missing_capabilities"]))
        for skipped in metadata.get("skipped_catalogs", [])
    ]
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
    return reconstructed, report


def _assembled_sections(
    path: Path,
    workspace: DuckDbWorkspace,
    metadata: dict[str, Any],
    redactor: Redactor,
    overlay: EnrichmentOverlay | None,
    stale: frozenset[int],
) -> tuple[AssembledDocument, str]:
    """One assembly, called by both `render` and `enrich` (2K design §8:
    "the same code path, so the two can never disagree") — two serializations
    of its result (2K design §6b): `render_module_document` wrapped assembly
    and the markdown serializer together, which was fine while there was one
    output; dual output needs the assembled sections handed to both
    `markdown_document` and `html_document` rather than assembled twice or
    re-derived from either one's bytes. Returns the module id alongside the
    sections — the HTML emitter's `<title>`, read off the SAME reconstruction
    rather than re-read from `metadata` a second time."""
    reconstructed, report = _reconstructed_report(path, workspace, metadata)
    sections = assemble_module_document(
        reconstructed,
        report,
        _commit_of(path),
        tuple(metadata.get("uncovered", [])),
        shape_fields=workspace.query("shape_fields"),
        resolved_config=workspace.query("resolved_config"),
        open_questions=workspace.query("open_questions"),
        library_symbols=workspace.query("library_symbols"),
        libraries_not_scanned=tuple(metadata.get("libraries_not_scanned", [])),
        redactor=redactor,
        overlay=overlay,
        stale=stale,
    )
    return sections, reconstructed.module_id


def _write_rendered_outputs(
    workspace_dir: Path, sections: AssembledDocument, module_id: str
) -> tuple[Path, Path]:
    render_dir = workspace_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    markdown_target = render_dir / "architecture.md"
    markdown_target.write_text(markdown_document(sections), encoding="utf-8")
    html_target = render_dir / "architecture.html"
    html_target.write_text(html_document(sections, module_id), encoding="utf-8")
    return markdown_target, html_target


def _stale_of(
    overlay: EnrichmentOverlay | None, workspace: DuckDbWorkspace, path: Path, redactor: Redactor
) -> frozenset[int]:
    """The positions in `overlay.claims` whose referents no longer exist
    against `workspace` as it stands now (2K design §6) — empty where there
    is no overlay at all. Staleness is the ingest checks re-run against the
    CURRENT workspace: a claim grounded when it was written whose referents
    have since gone renders as a count, not as a claim about code that no
    longer exists."""
    if overlay is None:
        return frozenset()
    return frozenset(refusal.index for refusal in stale_claims(overlay, workspace, path, redactor))


@module.command("render")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
def module_render(path: Path, workspace_dir: Path | None) -> None:
    """Reads the workspace `analyze` left behind — it never re-detects,
    re-scans, or re-resolves (M00 "no analysis"; the workspace persists
    precisely so render is a cheap read)."""
    workspace_dir = _workspace_dir_of(path, workspace_dir)
    _refuse_if_unanalyzed(path, workspace_dir)
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    redactor = _redactor_for(path)
    # Read here, before the workspace is opened, so a malformed overlay is
    # refused without a half-run render behind it. `render` assembles an
    # overlay the same way `enrich` does — the same code path, so the two can
    # never disagree about a committed overlay (2K design §8).
    overlay = _overlay_for(path)

    workspace = DuckDbWorkspace(db_path)
    try:
        try:
            stale = _stale_of(overlay, workspace, path, redactor)
            sections, module_id = _assembled_sections(
                path, workspace, metadata, redactor, overlay, stale
            )
        # A `redact:` pattern wide enough to break a claim's own schema is the
        # analysed repository's input written wrong, the same class of mistake
        # `_redactor_for` and `_overlay_for` already turn into messages — and
        # this one surfaces at the exit rather than at load, because it is the
        # rule set MEETING a claim that fails, not either alone.
        except ClaimRedactionError as refused:
            raise click.ClickException(str(refused)) from refused
        markdown_target, html_target = _write_rendered_outputs(workspace_dir, sections, module_id)
    finally:
        workspace.close()
    click.echo(str(markdown_target))
    click.echo(str(html_target))


def _jailed_roots_of(path: Path, workspace_dir: Path) -> tuple[Path, Path, Path]:
    """The three roots 2K design §4 names: the module's own source, its fact
    root, and its rendered outputs — the exact layout `ToolExecutor.__init__`
    is built to accept (its own docstring: "the module root together with
    its own `.sextant/facts` and `.sextant/render`"). `.sextantignore` is
    loaded for `path` alone, so every root here has to sit under it — true of
    the default `--workspace` layout, and refused loudly by `ToolExecutor`
    itself (caught in `module_enrich`) for a `--workspace` pointed anywhere
    else."""
    return (path, workspace_dir / "facts", workspace_dir / "render")


def _tool_executor_for(path: Path, workspace_dir: Path, redactor: Redactor) -> ToolExecutor:
    try:
        return ToolExecutor(_jailed_roots_of(path, workspace_dir), redactor, IgnoreRules.load(path))
    # `ToolExecutor.__init__` also calls `Path.home()` (2K Task 7 fix round
    # 3), which raises `RuntimeError` rather than `ValueError` when no home
    # directory can be resolved — a container image with no `HOME` set,
    # above all (2K Task 8 review). Caught into the same message, for the
    # same reason every other refusal in this file is: an environment the
    # operator wiring this jail up needs to fix, not a crash in the tool.
    except (ValueError, RuntimeError) as refused:
        raise click.ClickException(str(refused)) from refused


def _tool_definition_json(definition: ToolDefinition) -> dict[str, object]:
    return {
        "name": definition.name,
        "description": definition.description,
        "schema": definition.schema,
    }


@module.command("enrich")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--agent",
    "agent_flag",
    default=None,
    help=(
        "For a live run, an `AGENT_REGISTRY` name (refused if unknown). Under "
        "--ingest/--dry-run, no adapter runs — a free-text label for the "
        "overlay's provenance instead."
    ),
)
@click.option("--model", "model_flag", default=None, help="Passed to the agent verbatim.")
@click.option("--max-turns", "max_turns_flag", type=int, default=None)
@click.option("--dry-run", is_flag=True, default=False, help="Write the brief; call no agent.")
@click.option(
    "--ingest",
    "ingest_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Validate an externally-authored answers file instead of calling an agent.",
)
def module_enrich(
    path: Path,
    workspace_dir: Path | None,
    agent_flag: str | None,
    model_flag: str | None,
    max_turns_flag: int | None,
    dry_run: bool,
    ingest_path: Path | None,
) -> None:
    """Composes the brief, runs the agent (or a `--dry-run`/`--ingest` door),
    validates the answer by construction, writes `.sextant-enrichment.json`,
    and auto-assembles both rendered outputs — one command, done (2K design
    §8: "no second render command"). Refuses a workspace with no rendered
    document, naming `render`, before composing anything."""
    if dry_run and ingest_path is not None:
        raise click.ClickException("--dry-run and --ingest are mutually exclusive")

    # `ToolExecutor` resolves its jailed roots to absolute paths and checks
    # them against `IgnoreRules.load`'s own `repo_root` unresolved (2K Task 5)
    # — a relative `path` (ordinary on a command line: `sextant module enrich
    # fixtures/orders-service`) would make every root fail that check even
    # though it is genuinely contained, since an absolute path is never
    # "relative to" a merely-relative one. Resolved once, here, so `path` and
    # everything built from it (`workspace_dir`, `ignore`, the jailed roots)
    # agree on one spelling for the rest of this command.
    path = path.resolve()
    workspace_dir = _workspace_dir_of(path, workspace_dir)
    _refuse_if_unanalyzed(path, workspace_dir)
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"

    redactor = _redactor_for(path)
    defaults = _enrich_defaults_for(path)
    # `is None`, never `or` (2K Task 7 fix round 1, minor): a flag's own
    # falsy-but-meaningful value — `--max-turns 0` above all — must reach
    # `ClaudeApiAgent`'s own `>= 1` validation as what it is, not silently
    # read as "no flag given" and fall through to a config default or 50.
    agent_name = agent_flag if agent_flag is not None else defaults.agent
    model_name = model_flag if model_flag is not None else defaults.model
    max_turns = (
        max_turns_flag
        if max_turns_flag is not None
        else (defaults.max_turns if defaults.max_turns is not None else 50)
    )

    instructions = instructions_path().read_text(encoding="utf-8")
    instructions_hash = "sha256:" + hashlib.sha256(instructions.encode("utf-8")).hexdigest()

    # Checked here, in the composition root — `application` reads no files
    # (`tests/architecture/test_source_rules.py`), so the stage decides
    # whether a missing rendered document is refused; this is only the check.
    # The file is a GATE, never the brief's source (see below).
    architecture_md_path = workspace_dir / "render" / "architecture.md"
    if not architecture_md_path.is_file():
        raise click.ClickException(
            f"{path} has no rendered document at {architecture_md_path} — run "
            f"`sextant module render {path}` first"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    # Built only now that a rendered document is confirmed on disk (2K Task 7
    # fix round 1, CRITICAL C1b): `ToolExecutor` refuses a jailed root that
    # does not exist, and `workspace_dir/"render"` genuinely does not exist
    # for an analysed-but-unrendered workspace — the exact case just refused
    # above, with this command's own message. Building the jail any earlier
    # would trade that honest message for `ToolExecutor`'s generic
    # missing-root one, which was the live failure the fix round 1 review
    # actually reproduced.
    executor = _tool_executor_for(path, workspace_dir, redactor)
    roots = _jailed_roots_of(path, workspace_dir)

    workspace = DuckDbWorkspace(db_path)
    try:
        # The brief's document is assembled IN MEMORY, machine-only — never
        # the bytes sitting at `architecture_md_path` (2K final review, F1).
        # Spec §5 mandates the MACHINE-rendered document, and after one
        # `enrich` the on-disk file is the ENRICHED one: reading it would
        # feed a second run its own prior claims as if they were findings,
        # the very loop the Task 3 overlay-jail exclusion exists to prevent,
        # compounding run over run. `overlay=None` with an empty stale set
        # is precisely "as `render` would have written it before any of this
        # existed" (`_assembled_sections`' own contract), and it is the SAME
        # single assembly path `render` and the post-run re-render use, so
        # the brief can never describe a document assembly would not.
        sections, _ = _assembled_sections(
            path, workspace, metadata, redactor, overlay=None, stale=frozenset()
        )
        architecture_md = markdown_document(sections)
        # `architecture_md` is never `None` here — refused above — so this
        # never actually raises in THIS call site; `compose`'s own check
        # stays live and unit-tested (`test_enrich_stage.py`) as the stage's
        # documented contract for any other caller.
        try:
            brief = enrich_stage.compose(
                workspace,
                path,
                instructions,
                architecture_md,
                metadata,
                redactor,
                tuple(executor.definitions()),
                roots,
            )
        except enrich_stage.NotRenderedError as refused:
            raise click.ClickException(str(refused)) from refused

        if dry_run:
            brief_path = workspace_dir / "enrich-brief.json"
            brief_path.write_text(
                json.dumps(
                    {
                        "prompt": brief.prompt,
                        "tool_definitions": [
                            _tool_definition_json(d) for d in brief.tool_definitions
                        ],
                        "jailed_roots": [str(r) for r in brief.jailed_roots],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            instructions_copy = workspace_dir / "enrich-instructions.md"
            instructions_copy.write_text(instructions, encoding="utf-8")
            click.echo(str(brief_path))
            click.echo(str(instructions_copy))
            return

        # `metadata.json`'s own bytes stand in for "the graph" the run went
        # against (D06 §3's "one run of one model against one graph"),
        # deterministic and already on disk — cheaper than a bespoke
        # whole-workspace hash. Honestly imprecise both ways, stated rather
        # than implied: OVER-sensitive, because the dump embeds
        # `provenance.commit`, so the fingerprint moves on every commit even
        # when nothing the overlay actually references changed — it is
        # informational, read by a person, never compared bit-for-bit by any
        # code in this repository; UNDER-sensitive, because it is a set of
        # COUNTS (endpoint totals per protocol, gap lists), not identities —
        # two graphs with the same shape but different symbols underneath
        # (an endpoint swapped for another of the same protocol) hash
        # identically. Detecting that would need a fingerprint over the
        # actual rows, which is D06's own manifest-hash story (Task 8), not
        # this field's job.
        workspace_fingerprint = "sha256:" + hashlib.sha256(metadata_path.read_bytes()).hexdigest()

        if ingest_path is not None:
            if agent_name is None or model_name is None:
                raise click.ClickException(
                    "--ingest needs --agent and --model to label the overlay's provenance "
                    "(no adapter runs, so nothing else can say who produced the answer)"
                )
            answers_text = ingest_path.read_text(encoding="utf-8")
            transcript: tuple[dict[str, object], ...] = ()
            partial, partial_reason = False, None
        else:
            known = ", ".join(sorted(AGENT_REGISTRY))
            if agent_name is None:
                raise click.ClickException(f"--agent is required — known agents: {known}")
            if agent_name not in AGENT_REGISTRY:
                raise click.ClickException(
                    f"unknown --agent {agent_name!r} — known agents: {known}"
                )
            if model_name is None:
                raise click.ClickException("--model is required")
            try:
                agent = AGENT_REGISTRY[agent_name](model=model_name, max_turns=max_turns)
            except ValueError as refused:
                # `ClaudeApiAgent.__init__`'s own `max_turns >= 1` check
                # (2K Task 7 fix round 1, minor): a bad flag value is the
                # user's own input written wrong, not a crash.
                raise click.ClickException(str(refused)) from refused
            try:
                answers = agent.run(brief, executor)
            except EnrichmentAgentError as refused:
                raise click.ClickException(str(refused)) from refused
            answers_text = answers.text
            transcript = tuple(answers.transcript)
            partial, partial_reason = answers.partial, answers.partial_reason

        try:
            result = enrich_stage.validate_and_finish(
                answers_text,
                workspace,
                path,
                redactor,
                agent_name,
                model_name,
                instructions_hash,
                workspace_fingerprint,
                partial=partial,
                partial_reason=partial_reason,
                transcript=transcript,
            )
        except enrich_stage.MalformedAnswersError as refused:
            raise click.ClickException(str(refused)) from refused

        # Written BEFORE assembly, deliberately (2K Task 7 fix round 1): the
        # overlay IS the run's record — if the rendered assembly below fails
        # (`ClaimRedactionError`, a `.sextant.yml` `redact:` rule wide enough
        # to break a claim's own schema), the answer this run produced is
        # still on disk, exactly as `render` would read it back and exactly
        # as a later `render` recovers from without re-running the agent.
        # Losing the overlay to an assembly failure would be worse than the
        # asymmetry of writing it first: it is Sextant's own program
        # artifact, not a byproduct of successfully rendering one.
        overlay_path = path / ENRICHMENT_FILE
        overlay_path.write_text(
            result.overlay.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )

        # The workspace record (2K Task 7 ruling 4): every tool call, and one
        # final line naming exactly how the run ended — persisted even when
        # nothing is partial, so "clean" is a recorded fact and not merely
        # the absence of a warning.
        transcript_path = workspace_dir / "enrich-transcript.jsonl"
        with transcript_path.open("w", encoding="utf-8") as handle:
            for entry in result.transcript:
                handle.write(json.dumps(entry, sort_keys=True, default=repr) + "\n")
            handle.write(
                json.dumps(
                    {
                        "event": "run_summary",
                        "partial": result.partial,
                        "partial_reason": result.partial_reason,
                        "refusals": [
                            {"index": r.index, "reason": r.reason} for r in result.refusals
                        ],
                    },
                    sort_keys=True,
                )
                + "\n"
            )

        # The user-visible report (2K design §6/Task 7 ruling 4): a refused
        # claim named by position and reason, and an honest word about a run
        # that did not end cleanly — before either is buried in a file.
        for refusal in result.refusals:
            click.echo(f"refused claim {refusal.index}: {refusal.reason}")
        if result.partial:
            click.echo(f"partial answer ({result.partial_reason}) — overlay reflects what exists")

        try:
            stale = _stale_of(result.overlay, workspace, path, redactor)
            sections, module_id = _assembled_sections(
                path, workspace, metadata, redactor, result.overlay, stale
            )
        except ClaimRedactionError as refused:
            raise click.ClickException(str(refused)) from refused
        markdown_target, html_target = _write_rendered_outputs(workspace_dir, sections, module_id)
    finally:
        workspace.close()
    click.echo(str(overlay_path))
    click.echo(str(markdown_target))
    click.echo(str(html_target))


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
    _refuse_if_unanalyzed(path, workspace_dir)
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    commit = str(metadata["provenance"]["commit"])
    bundle_name = re.sub(r"[^A-Za-z0-9._-]", "-", str(metadata["module"]["id"])) + "@" + commit
    bundle = (out_dir or workspace_dir / "bundles") / bundle_name

    redactor = _redactor_for(path)
    workspace = DuckDbWorkspace(db_path)
    try:
        tables = workspace.export_tables(bundle, redactor)
        facts_files = workspace.export_facts(bundle, redactor)
    finally:
        workspace.close()

    # Both rendered documents travel with the bundle when `render` has already
    # produced them (2K design §6b) — copied verbatim, already masked at the
    # render exit, so this is a plain file carry rather than a second
    # redaction pass. `render` is not a prerequisite for `export` (M08: export
    # only ever reads what `analyze` left), so their absence is silent, not a
    # failure — the same optionality a workspace with no render step has
    # always had. Collected before the manifest is written, not after (2K
    # Task 8 review): `write_manifest`'s own `contents.render` names what
    # actually shipped, the same "named by the caller, not re-derived" rule
    # `tables`/`facts_files` already follow.
    render_dir = workspace_dir / "render"
    shipped_render: list[str] = []
    for rendered in ("architecture.md", "architecture.html"):
        source = render_dir / rendered
        if source.is_file():
            (bundle / "render").mkdir(parents=True, exist_ok=True)
            (bundle / "render" / rendered).write_bytes(source.read_bytes())
            shipped_render.append(rendered)

    write_manifest(
        bundle / "manifest.json",
        metadata,
        source={"repo": _remote_of(path), "commit": commit},
        catalog_hash=_catalog_hash(catalogs_dir()),
        redaction_set_hash=redactor.rule_set_hash,
        module_commit=_module_commit_of(path),
        tables=tables,
        facts_files=facts_files,
        render=shipped_render,
    )
    click.echo(str(bundle))
