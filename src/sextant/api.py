"""Sextant as a library (2N Task 5, spec §5b): the four verbs the CLI's own
`module analyze`/`render`/`enrich`/`export` commands are thin wrappers over —
`analyze`, `render`, `enrich`/`enrich_async`, `export` — each a plain,
synchronous function returning a small frozen result object, never printing
anything and never raising `SystemExit`.

**Built by extraction, not duplication.** Every composition that used to live
inline inside a `click` command body in `cli/app.py` — the reactor loop
`module analyze` walks, the tool-jail and door logic `module enrich`
composes, the read-back-and-reassemble `render`/`export` share — moved here,
its OWN observable behavior held fixed (nothing a `click` command printed
moved earlier or later, no message text changed), so `cli/app.py`'s own
commands could shrink to: parse flags, call one function below, translate a
`SextantError` into a `click.ClickException` carrying the SAME message, then
print the result. The existing CLI test suite, untouched, is the proof
(2M's own discipline, restated for this task): a refactor is safe when the
pins around it never moved. Fix round 1's own MAJOR-1 restored one such pin
this extraction had actually MOVED (a report `cli/app.py` used to print
before a later step could still fail, left printing only after that step —
see `_enrich`'s own docstring) — the claim above is the target this module
is now held to, not a claim that the first pass got there untested.

**The v1 contract, stated plainly:**

- **Synchronous.** `enrich_async` is the one exception (see below); every
  other verb blocks until its work is done and returns.
- **Quiet.** No progress callbacks, no `rich` console output — that stays a
  `cli`-only concern (`RichProgress`, injected into the CLI's own calls
  through the same `Progress` port `application.stages.analyze` already
  defines, never imported by this module).
- **Not thread-safe per module.** One workspace (`<module>/.sextant`) is one
  file tree; two calls against the same module at the same time are
  undefined, the same "one module, one workspace, one command" rule M00
  already states for the CLI.
- **Embedded `enrich` defaults to `auth="api-key"`.** The CLI's own default
  is `subscription` (a developer's logged-in machine); a library host is a
  service with no login to hand Tradewind, so the facade's own default is
  the opposite one, deliberately — see the module's own `enrich` docstring.

**`enrich_async`.** Task 4's own adapter review carried this forward
(ledgered there, implemented here): `TradewindAgent.run` is `asyncio.run`
wrapping the whole client/session/turn lifecycle, and `asyncio.run` raises
when called from a thread that already has a running event loop — exactly
the thread an async service's own request handler runs on. `enrich_async`
awaits the very same `enrich` composition, run on a worker thread
(`asyncio.to_thread`) — a thread with no event loop of its own, so the
adapter's own `asyncio.run` succeeds there — rather than re-driving Tradewind
through some second, parallel async code path this module would then have to
keep in sync with the sync one by hand. Calling the plain, synchronous
`enrich` FROM a running loop is left to fail exactly as it already does:
`TradewindAgent.run`'s own `except Exception` wraps `asyncio.run`'s
`RuntimeError` into an `EnrichmentAgentError`, which this module turns into
an `EnrichmentError` the same way every other agent failure becomes one — no
special-casing needed, and no `nest_asyncio` dependency added.

**`enrich_async`'s own two real costs (fix round 1, MODERATE-4) — neither
free, both worth stating plainly rather than leaving this read as pure
upside over the sync `enrich`.** First, `asyncio.to_thread` runs the call on
the default executor's own thread pool: one thread sits blocked for the
FULL duration of a real run — a live model call, potentially minutes — for
every concurrent `enrich_async` call, so a service issuing many at once can
exhaust that pool (sized by `ThreadPoolExecutor`'s own default,
`min(32, os.cpu_count() + 4)`) well before it exhausts anything else, and
every call queued behind a full pool simply waits. Second, it is not
cancellable in the way a native coroutine is: cancelling the `await` (a
timeout, a client disconnect) does not stop the underlying thread — Python
gives no API to interrupt one — so the worker keeps running to completion
regardless, including writing the overlay and both rendered documents to
disk, unseen by the caller that already gave up on it. Accepted for v1 as
stated (review round 1): the real fix is a native async entry point on the
`EnrichmentAgent` port itself (a `run_async` alongside `run`), ledgered as
future work, not this task's.

**The `SextantError` family.** The spec asks for "a typed `SextantError`
family", not naming the members — this module picks four, grouped by what a
caller could sensibly want to catch and retry or report differently, not one
subclass per refusal site:

- `DetectionError` — `analyze`'s own refusals: a detector could not read the
  repository (a malformed `pom.xml`, a `<modules>` cycle), a multi-module
  root was asked for a single `--workspace`, or one module inside a reactor
  walk failed (named, the walk stopped).
- `NotAnalyzedError` — `render`/`enrich`/`export`, pointed at a workspace
  `analyze` never wrote to, at a multi-module root instead of one of its
  modules, or at one whose recorded stamps say a different Sextant build
  derived it (D01 §7's re-derivation rule, enforced at the read gate).
- `ConfigurationError` — Sextant's own on-disk artifacts written wrong: a
  malformed `.sextant.yml` (`redact:`, `enrich:`), a malformed
  `.sextant-enrichment.json` overlay, or a `redact:` rule that breaks a
  claim's own schema when rendering.
- `EnrichmentError` — everything specific to `enrich`'s own run: the
  mutually-exclusive doors, a workspace with no rendered document, the tool
  jail's own setup, an unknown `--agent` name, a missing model, the agent's
  own construction or run failing, or an answer that will not validate.

Every one of these carries the exact string the CLI already prints for the
same refusal — this module raises it; `cli/app.py` is the only place that
still turns it into a `click.ClickException`.
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast
from xml.etree.ElementTree import ParseError

from pydantic import ValidationError

from sextant.agents import AGENT_REGISTRY, DEFAULT_MAX_TURNS
from sextant.application.enrich.tools import ToolDefinition, ToolExecutor
from sextant.application.enrich.validate import stale_claims
from sextant.application.ports.detector import (
    Detector,
    ModuleModel,
    RepositoryModel,
    select_detector,
)
from sextant.application.ports.enrichment import EnrichmentAgentError
from sextant.application.ports.progress import NullProgress, Progress
from sextant.application.query.trace import traces_of
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport, coverage_of
from sextant.application.stages import enrich as enrich_stage
from sextant.application.stages.analyze import AnalyzeResult as _StageAnalyzeResult
from sextant.application.stages.analyze import analyze as _analyze_stage
from sextant.application.stitch import (
    gateway_links as _gateway_links,
)
from sextant.application.stitch import (
    match as _match_links,
)
from sextant.application.stitch import (
    participants_of as _participants_of,
)
from sextant.application.stitch import (
    route_model as _route_model,
)
from sextant.application.stitch import (
    uncalled as _uncalled_endpoints,
)
from sextant.application.stitch import (
    with_registered_names as _with_registered_names,
)
from sextant.application.stitch.links import Link
from sextant.domain.enrichment import ENRICHMENT_FILE, EnrichmentOverlay, load_overlay
from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import RedactionError, Redactor
from sextant.domain.version import FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.egress.export.index import write_index
from sextant.egress.export.manifest import write_manifest
from sextant.egress.render.document import (
    AssembledDocument,
    ClaimRedactionError,
    assemble_module_document,
    markdown_document,
)
from sextant.egress.render.html import html_document
from sextant.egress.render.metadata import write_metadata
from sextant.egress.render.system import render_system_document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.detect.gradle import GradleDetector
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
from sextant.resources import catalogs_dir, extractor_jar, instructions_path
from sextant.storage.duckdb.workspace import DuckDbWorkspace, StaleParticipantError

# --------------------------------------------------------------------------
# The SextantError family (module docstring above states the grouping).
# --------------------------------------------------------------------------


class SextantError(RuntimeError):
    """Base of every refusal the four verbs below raise — never
    `SystemExit`, never a bare `ValueError`/`RuntimeError` from underneath.
    `str(error)` is always the exact message the CLI prints for the same
    refusal."""


class DetectionError(SextantError):
    """`analyze` could not detect, or could not walk, the repository at
    `path` — see the module docstring's family summary."""


class NotAnalyzedError(SextantError):
    """`render`/`enrich`/`export` were pointed at a workspace `analyze`
    never wrote, at a multi-module root instead of one of its modules, or at
    one a DIFFERENT Sextant build wrote (OI-24, D01 §7) — all three are the
    same answer to the caller: there is no analysis here this build can
    read, run `analyze`."""


class ConfigurationError(SextantError):
    """One of Sextant's own on-disk artifacts — `.sextant.yml`,
    `.sextant-enrichment.json` — is written in a way this module cannot
    read, or (renderer-side) a `redact:` rule collides with a claim's own
    schema."""


class EnrichmentError(SextantError):
    """`enrich` could not complete: a door conflict, a missing rendered
    document, the tool jail's own setup, an unknown agent or missing model,
    the agent's own construction or run, or an answer that will not
    validate."""


# --------------------------------------------------------------------------
# Result objects — frozen, no methods, nothing printed by any of them.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleOutcome:
    """One module's own row in an `AnalyzeResult` — the same information
    `modules.json` records for a reactor's own walk (`dir`, `module_id`,
    `kind`, `analyzed`, `skip_reason`), plus `endpoints`: the count
    `analyze` found, or `None` for a module that was skip-listed rather than
    analyzed. A true single-module `analyze` (no `<modules>` reactor at
    `path`) still returns exactly one of these — the facade never special-
    cases "one module" the way the CLI's own JSON-only line does."""

    dir: str
    module_id: str
    kind: str
    analyzed: bool
    skip_reason: str | None
    endpoints: int | None


@dataclass(frozen=True)
class AnalyzeResult:
    """`analyze`'s own outcome: every module the walk considered, root-
    relative, in the same order `modules.json` would list them (sorted by
    `dir`) for a reactor, or the one module `path` itself is otherwise.

    `value_resolutions` is spec 2026-09-22 §7a's shadow row count — how many
    candidate conversions the walk recorded. `0` on any run without `--shadow`,
    and `None` for a REACTOR walk, where there is no single number to give: each
    module records into its OWN workspace, and those counts go to `on_module`
    instead, one line per module. Deliberately NOT on `ModuleOutcome`: that
    dataclass is what `modules.json` records, and a published inventory is
    exactly what shadow mode must not move."""

    modules: tuple[ModuleOutcome, ...]
    value_resolutions: int | None = None


@dataclass(frozen=True)
class RenderResult:
    """`render`'s own outcome: the two documents it wrote, both already
    masked by the module's own redaction rules."""

    markdown: Path
    html: Path


@dataclass(frozen=True)
class SystemResult:
    """`system_analyze`'s own outcome: the document it wrote and what it found.

    The counts are the ones a reader checks the run by — `links` against the participants
    they expected to see connected, and `unmatched` against the calls they know leave the
    system. `document` is the primary artifact: the table is intermediary and a blank
    document is a failed run however green the table is (user ruling, 2026-10-17)."""

    document: Path
    workspace: Path
    participants: int
    links: int
    unmatched: int
    uncalled: int
    # Gateway routes whose prefix could not be composed with the service's paths. Counted
    # beside the links because a run with many is one whose gateway the document describes
    # less completely than its link count suggests.
    route_refusals: int


@dataclass(frozen=True)
class EnrichResult:
    """`enrich`'s own outcome. `overlay` is the primary artifact the call
    wrote: `.sextant-enrichment.json`'s path for a live run or an `--ingest`
    run, or the composed brief's own path (`enrich-brief.json`) for
    `dry_run=True`, which writes no overlay at all — `accepted`/`refused`/
    `partial_reason` are all zero/`None` in that case, since no answer was
    ever validated. `accepted`/`refused` count claims, not runs;
    `partial_reason` is `None` for a clean answer."""

    overlay: Path | None
    accepted: int
    refused: int
    partial_reason: str | None


@dataclass(frozen=True)
class ExportResult:
    """`export`'s own outcome: the bundle directory it wrote (Parquet, fact
    files, the manifest, and either rendered document that already existed)."""

    bundle: Path


@dataclass(frozen=True)
class _EnrichOutcome:
    """The internal composition's own result — a superset of the public
    `EnrichResult`, carrying what only `cli/app.py`'s thin wrapper needs to
    print: both dry-run paths (the public result folds down to one), and the
    other two written documents. The per-claim refusal report itself is NOT
    a field here (fix round 1, MAJOR-1) — it is handed to `on_report` at the
    one moment BASE printed it, inside `_enrich` itself, before this object
    is even built; carrying it here too would let a caller print it a
    second time, or read it after a run whose later assembly step failed
    and never returned one."""

    overlay_path: Path | None
    brief_path: Path | None
    instructions_copy_path: Path | None
    markdown: Path | None
    html: Path | None
    accepted: int
    refused: int
    partial_reason: str | None


# --------------------------------------------------------------------------
# The composition root's own registries and helpers — moved from `cli/app.py`
# (2N Task 5): each one's own rationale, carried here as the docstring or
# comment it already had there — restated, not reinvented, and updated only
# where the refusal it raises changed shape (a typed `SextantError` now,
# never `click.ClickException` directly).
# --------------------------------------------------------------------------

# The one real `Detector` registry (2M Task 2 review): a future detector
# added to only one of two hand-kept lists would send the other path to
# `select_detector`'s own uncaught `NoAdapterError`. Order is precedence
# (`select_detector` picks the first that `accepts()`): Maven before Gradle.
_DETECTORS: list[Detector] = [MavenDetector(), GradleDetector()]


def _modules_json_path(path: Path) -> Path:
    """`modules.json`'s own location (ARCHITECTURE §8's file layout:
    `<repo-root>/.sextant/modules.json`) — named once so the write site in
    `_analyze_reactor` and the read site in `_refuse_if_unanalyzed`'s
    refusal cannot drift apart."""
    return path / ".sextant" / "modules.json"


def _root_relative(root: Path, target: Path) -> str:
    """`target`, spelled relative to `root` (2M Task 2 fix round 1, F5) —
    `os.path.relpath`, never `Path.relative_to`: a `<module>` may climb OUT
    of the aggregator's own directory, and `relative_to` refuses anything
    that is not a strict descendant. Both resolved first, so the spelling
    is the SAME regardless of whether `root`/`target` reached here as
    relative or absolute strings."""
    return os.path.relpath(target.resolve(), start=root.resolve())


def _skip_reason(module: ModuleModel) -> str | None:
    """Why a module is skip-listed rather than analyzed, or `None` when it
    should be analyzed (2M design §2, amended by the 2026-09-04 user ruling).

    **A leaf `<packaging>pom</packaging>` is now the only skip**, and it is
    not a judgement about the module's purpose: Maven's own declaration that
    the module produces no jar means there is provably nothing to scan. The
    former `kind == "library"` skip is gone with the publishing inference that
    fed it (see `GradleDetector._classify`) — no detector returns `library`
    any more. Everything with code is analyzed, `undetermined` included: a
    module nothing references simply yields facts nobody links to, which
    costs a little time and risks nothing, while skipping one that IS
    referenced loses its outbound clients and shapes entirely."""
    if module.packaging == "pom":
        return "packaging is pom"
    return None


def _module_json_row(outcome: ModuleOutcome) -> dict[str, object]:
    """One `modules.json` row — the same five keys the CLI's own
    `_module_row` wrote before this task, unchanged: `endpoints` is not one
    of them, since it never was (a committed, read-back artifact stays
    byte-compatible across this refactor)."""
    return {
        "dir": outcome.dir,
        "module_id": outcome.module_id,
        "kind": outcome.kind,
        "analyzed": outcome.analyzed,
        "skip_reason": outcome.skip_reason,
    }


class _KnownModuleDetector:
    """Adapts one already-detected `ModuleModel` back into the `Detector`
    Protocol, so the stage's own internal `select_detector(...).detect(path)`
    call (M00's "one module, one workspace, one command" contract) is
    satisfied from data the caller already has, rather than invoking the
    real detector a second time (2M Task 2 review's hard gate)."""

    def __init__(self, module: ModuleModel, notes: tuple[str, ...]) -> None:
        self._module = module
        self._notes = notes

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=self._module.root, modules=(self._module,), notes=self._notes)


class _JvmDescriptorInterpreter:
    """The `DescriptorInterpreter` port, adapted: binds the JVM's own
    generated-class naming — constructed only here, per ARCHITECTURE §10's
    JVM-confinement rule — into `interpret_descriptors`."""

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


# The model subdirectories beside the catalogs, each part of the knowledge a run
# was produced with (`yaml_source.YamlCatalogSource` reads the same four: `_models`
# the first three, `value_model` the fourth).
_MODEL_DIRECTORIES = ("shape-models", "bean-models", "step-models", "value-models")


def _catalog_hash(catalogs: Path) -> str:
    """The identity of the framework knowledge a run was produced with.

    `shape-models/` is walked as well as the catalogs themselves (D02 §1b).
    Since F2, `serialization`, `nullability` and `known_types` live there and
    in no catalog at all — so a hash over `catalogs/*.yml` alone would say two
    runs used the same knowledge while one of them read a different wire-type
    table, which is precisely the drift the hash exists to make visible.
    `bean-models/` (D02 §1c) and `step-models/` (spec 2026-09-21 §5) are
    walked for the same reason: the bean vocabulary and the flow definition's
    step table live there and nowhere else. `value-models/` (D02 §1f, spec
    2026-09-22 §2) joins them: a producing call's identity is declared there once
    rather than once per consuming catalog, so an edit to it is an edit to what
    every catalog resolves through. The path is included, not just the
    filename, so a model and a catalog of the same name cannot collide.
    """
    digest = hashlib.sha256()
    files = sorted(catalogs.glob("*.yml")) + [
        path
        for subdirectory in _MODEL_DIRECTORIES
        for path in sorted((catalogs / subdirectory).glob("*.yml"))
    ]
    for catalog in files:
        digest.update(str(catalog.relative_to(catalogs)).encode("utf-8"))
        digest.update(catalog.read_bytes())
    return "sha256:" + digest.hexdigest()


def _workspace_dir_of(path: Path, workspace_dir: Path | None) -> Path:
    return workspace_dir or (path / ".sextant")


def _stale_stamps(metadata: dict[str, Any]) -> tuple[str, ...]:
    """Which of the three stamps `metadata.json` carries disagree with the
    build now running — empty for a workspace this build could have written
    (OI-24, D01 §7).

    **The rule was documentation until here.** D01 §7 says every result
    records what produced it and *"any Sextant version change re-derives,
    because derivation logic may have changed and there is no cheap way to
    know"*, and its table gives `graph_schema_version` (derived tables) and
    `fact_schema_version` (facts, and everything after) their own
    invalidation costs. All three were WRITTEN — by `egress/render/metadata.py`
    — and read back for comparison by nothing, so the gate below checked only
    that two files exist.

    **Compared, never repaired.** A mismatch is answered by a refusal naming
    the stamp, not by a silent re-analysis: re-deriving inside a `render`
    would make the verb that promises to read what `analyze` left behind
    (M00's "no analysis" rule) the one that quietly re-runs the pipeline. The
    reader is told which stamp moved and what to run.

    An ABSENT stamp is a mismatch, not an exemption. `write_metadata` has
    always written all three, so a document missing one was written by
    something else — and treating `None` as "close enough" is exactly the
    silent acceptance this exists to stop.
    """
    provenance = metadata.get("provenance", {})
    recorded = (
        # `schema_version` at the top level, not under `provenance`:
        # `write_metadata` puts the graph stamp there, and D01 §7's table
        # calls it the workspace's own rather than a document's.
        ("graph_schema_version", metadata.get("schema_version"), GRAPH_SCHEMA_VERSION),
        ("sextant_version", provenance.get("sextant_version"), SEXTANT_VERSION),
        ("fact_schema_version", provenance.get("fact_schema_version"), FACT_SCHEMA_VERSION),
    )
    return tuple(
        f"{name} is {found!r}, this build is {running!r}"
        for name, found, running in recorded
        if found != running
    )


def _refuse_if_unanalyzed(path: Path, workspace_dir: Path) -> None:
    """The `no analysis found` refusal `render`/`enrich`/`export` share
    (M00's "no analysis" rule). Widened for a multi-module root (2M design
    §2): `modules.json`'s presence with no per-module workspace at
    `workspace_dir` means the caller pointed at the reactor root rather than
    at one of the modules it names, so the refusal reads out that list
    instead of the generic message.

    **And widened again for a STALE one** (OI-24). A workspace whose stamps
    do not match this build is refused here rather than read: its derived
    tables were built by different derivation logic, and a table this build
    added is simply absent from it — which reads as a module that has none,
    not as a workspace that predates the table. `## Traces` is the first
    section where that becomes a wrong answer a reader would act on rather
    than a silence nobody could see.
    """
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"
    if metadata_path.is_file() and db_path.is_file():
        stale = _stale_stamps(json.loads(metadata_path.read_text(encoding="utf-8")))
        if stale:
            raise NotAnalyzedError(
                f"the analysis at {workspace_dir} was produced by a different Sextant "
                f"build ({'; '.join(stale)}), so its derived tables are a different "
                f"vintage from this one — re-run `sextant module analyze {path}`."
            )
        return
    modules_path = _modules_json_path(path)
    if modules_path.is_file():
        modules = json.loads(modules_path.read_text(encoding="utf-8"))["modules"]
        dirs = ", ".join(sorted(str(module["dir"]) for module in modules))
        raise NotAnalyzedError(
            f"{path} is a multi-module root; analyze it, then run this command against "
            f"one of: {dirs}"
        )
    raise NotAnalyzedError(
        f"no analysis found at {workspace_dir} — run `sextant module analyze {path}` first."
    )


def _redactor_for(path: Path) -> Redactor:
    """The redactor both EXITS use (2K design §1): the built-in rule set,
    widened by this module's own `.sextant.yml`. Built at the composition root
    so render and export mask by one set and the manifest can name it.

    Both refusals become the message a caller reads, the same way
    `_analyzed` turns a malformed `.sextant.yml` into one: a `redact:`
    section written wrong is a mistake in the analysed repository, and a
    stack trace would report it as a crash in the tool."""
    try:
        return Redactor.from_rules(read_redaction_rules(path))
    except (SextantConfigError, RedactionError) as refused:
        raise ConfigurationError(str(refused)) from refused


def _overlay_for(path: Path) -> EnrichmentOverlay | None:
    """The module's enrichment overlay, or `None` where it has none (2K
    design §6). An overlay that is present and malformed becomes the message
    a caller reads, for the reason `_redactor_for` turns a bad `redact:`
    section into one: it is Sextant's own program artifact written wrong,
    and a stack trace would report it as a crash in the tool."""
    try:
        return load_overlay(path)
    except ValidationError as refused:
        raise ConfigurationError(
            f"{path / ENRICHMENT_FILE} is not a valid overlay: {refused}"
        ) from refused


def _enrich_defaults_for(path: Path) -> EnrichDefaults:
    """This module's `enrich:` defaults (2K design §3), or a message a
    caller reads instead of a stack trace — the same turn `_redactor_for`
    gives a bad `redact:` section, for the same reason (D04 §2a's
    refusal)."""
    try:
        return read_enrich_defaults(path)
    except SextantConfigError as refused:
        raise ConfigurationError(str(refused)) from refused


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------


def _run_analyze(
    path: Path,
    module: ModuleModel,
    notes: tuple[str, ...],
    workspace_dir: Path,
    allow_resolve: bool,
    progress_factory: Callable[[], AbstractContextManager[Progress]] | None,
    ignore_root: Path | None = None,
    shadow: bool = False,
) -> _StageAnalyzeResult:
    """One module, analyzed into one workspace, and its `metadata.json`
    written — the body every `analyze` invocation shares, whether `path` is
    a single-module root or one module inside a just-walked reactor.

    `ignore_root` is the root a `.sextantignore` sits at and every pattern in
    it is written against (D04 §3, `A-M16`). It is the module's own root for a
    single-module repository — where the two coincide, which is the case D04
    describes — and the REACTOR root for a submodule, which is the case that
    was wrong: a reactor-root ignore file reached no submodule at all, and a
    pattern written relative to the reactor root would not have matched if it
    had. Defaulted to `path` so every existing caller is unchanged."""
    render_dir = workspace_dir / "render"
    if render_dir.is_dir():
        shutil.rmtree(render_dir)
    factory = progress_factory or (lambda: nullcontext(NullProgress()))
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        with factory() as progress:
            result = _analyzed(
                path,
                workspace,
                workspace_dir,
                progress,
                [_KnownModuleDetector(module, notes)],
                allow_resolve=allow_resolve,
                ignore_root=ignore_root or path,
                shadow=shadow,
            )
        write_metadata(
            workspace_dir / "metadata.json",
            result.module,
            result.report,
            result.scanners,
            _commit_of(path),
            result.uncovered,
            resolved_config=workspace.query("resolved_config"),
            schema_sources_not_compiled=result.schema_sources_not_compiled,
            descriptors_not_interpreted=result.descriptors_not_interpreted,
            libraries_not_scanned=result.libraries_not_scanned,
            detect_notes=result.notes,
            # Recorded here, where the catalogs this run used are in hand; `export` copies it.
            catalog_hash=_catalog_hash(catalogs_dir()),
        )
    finally:
        workspace.close()
    return result


def _analyzed(
    path: Path,
    workspace: DuckDbWorkspace,
    workspace_dir: Path,
    progress: Progress,
    detectors: Sequence[Detector],
    allow_resolve: bool = False,
    ignore_root: Path | None = None,
    shadow: bool = False,
) -> _StageAnalyzeResult:
    """`analyze`, with the one failure a USER caused turned into the message
    a user reads: a malformed `.sextant.yml` is Sextant's own input written
    wrong (D04 §2a's refusal)."""
    try:
        return _analyze_stage(
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
            ignore_root=ignore_root,
            shadow=shadow,
        )
    except SextantConfigError as refused:
        raise ConfigurationError(str(refused)) from refused


def _analyze_reactor(
    path: Path,
    model: RepositoryModel,
    allow_resolve: bool,
    progress_factory: Callable[[], AbstractContextManager[Progress]] | None,
    on_module: Callable[[str], None] | None,
    shadow: bool = False,
) -> tuple[ModuleOutcome, ...]:
    """Every module a just-walked reactor named that is not KNOWN not to be
    a service, each analyzed into its own `<module-dir>/.sextant` workspace
    exactly as a single-module run would (2M design §2). `modules.json` then
    names every module found, analyzed or not. One failing module fails
    loudly and stops the walk: `modules.json` is written only once every
    module that was going to be analyzed has been, and any STALE inventory
    from a PRIOR run is removed at the start."""
    modules_path = _modules_json_path(path)
    modules_path.unlink(missing_ok=True)

    outcomes: list[ModuleOutcome] = []
    for module in model.modules:
        relative_dir = _root_relative(path, module.root)
        reason = _skip_reason(module)
        if reason is not None:
            if on_module is not None:
                on_module(f"skipped {relative_dir} ({module.module_id}): {reason}")
            outcomes.append(
                ModuleOutcome(relative_dir, module.module_id, module.kind, False, reason, None)
            )
            continue
        workspace_dir = _workspace_dir_of(module.root, None)
        try:
            stage_result = _run_analyze(
                module.root,
                module,
                model.notes,
                workspace_dir,
                allow_resolve,
                progress_factory,
                # `A-M16`: the reactor root, not the submodule's. D04 §3 is
                # emphatic — "One file, at the repository root, and every
                # pattern in it is matched against a path made relative to
                # THAT root" — and loading at `module.root` meant a
                # reactor-root `.sextantignore` reached no submodule at all.
                ignore_root=path,
                shadow=shadow,
            )
        except Exception as failure:  # deliberately broad, see below
            # A batch run's own failure must name WHICH module failed — left
            # uncaught, the module's own exception would read as this
            # command crashing rather than as that module's analysis
            # failing, with no way to tell which of several modules it was.
            raise DetectionError(
                f"{relative_dir} ({module.module_id}) failed to analyze: {failure}"
            ) from failure
        endpoints = len(stage_result.report.endpoints)
        if on_module is not None:
            # A reactor walk records shadow rows PER MODULE, into each module's own
            # workspace, so a single number on the `AnalyzeResult` could not name them —
            # this line can, and it is the only place a reader learns a submodule recorded
            # anything at all. Appended ONLY under `--shadow`, so the ordinary line is
            # exactly what it has always been.
            recorded = f", {stage_result.report.value_resolutions} shadow rows" if shadow else ""
            on_module(
                f"analyzed {relative_dir} ({module.module_id}): {endpoints} endpoints{recorded}"
            )
        outcomes.append(
            ModuleOutcome(relative_dir, module.module_id, module.kind, True, None, endpoints)
        )

    outcomes.sort(key=lambda outcome: outcome.dir)
    modules_path.parent.mkdir(parents=True, exist_ok=True)
    modules_path.write_text(
        json.dumps({"modules": [_module_json_row(o) for o in outcomes]}, indent=2) + "\n",
        encoding="utf-8",
    )
    return tuple(outcomes)


def _analyze(
    path: Path,
    *,
    workspace_dir: Path | None,
    allow_resolve: bool,
    progress_factory: Callable[[], AbstractContextManager[Progress]] | None = None,
    on_module: Callable[[str], None] | None = None,
    # Spec 2026-09-22 §7a: the CLI's `--shadow`, carried to `resolve` and read
    # nowhere else. It adds one pass that writes one table nothing reads, and
    # moves no row in `endpoints`, `endpoint_metadata` or `shapes`.
    shadow: bool = False,
) -> tuple[AnalyzeResult, bool]:
    """`analyze`'s own composition, shared by the public `analyze()` and
    `cli/app.py`'s `module_analyze`. Returns `(result, multi_module)` —
    `multi_module` is not part of the public `AnalyzeResult` (the facade
    treats a single module and a one-child reactor identically), but the
    CLI's own thin wrapper still needs it to pick its two different print
    formats, the one difference between the CLI's and the library's own
    idea of "done"."""
    # Detection runs FIRST, before anything below creates so much as a
    # directory (2M design §2): a refused detection must be discovered
    # ahead of any workspace write, or a repository Sextant cannot analyze
    # would still leave one behind.
    try:
        model = select_detector(_DETECTORS, path).detect(path, allow_resolve=allow_resolve)
    except (SextantConfigError, ValueError, ParseError) as refused:
        raise DetectionError(str(refused)) from refused

    if model.multi_module:
        # `--workspace` names ONE module's workspace (M00); a multi-module
        # root has no single workspace of its own to name.
        if workspace_dir is not None:
            raise DetectionError(
                f"{path} is a multi-module root — --workspace is refused there; it names "
                "one module's workspace, and every module here gets its own"
            )
        modules = _analyze_reactor(
            path, model, allow_resolve, progress_factory, on_module, shadow=shadow
        )
        return AnalyzeResult(modules=modules), True

    module = model.modules[0]
    resolved_workspace_dir = _workspace_dir_of(path, workspace_dir)
    stage_result = _run_analyze(
        path,
        module,
        model.notes,
        resolved_workspace_dir,
        allow_resolve,
        progress_factory,
        shadow=shadow,
    )
    outcome = ModuleOutcome(
        dir=_root_relative(path, module.root),
        module_id=module.module_id,
        kind=module.kind,
        analyzed=True,
        skip_reason=None,
        endpoints=len(stage_result.report.endpoints),
    )
    return AnalyzeResult(
        modules=(outcome,), value_resolutions=stage_result.report.value_resolutions
    ), False


def analyze(path: Path, *, allow_resolve: bool = False) -> AnalyzeResult:
    """Analyzes `path` into its own `.sextant` workspace (or, for a
    multi-module root, every module it names into ITS own workspace) — the
    library equivalent of `sextant module analyze`. Silent: no progress is
    printed anywhere. Raises `DetectionError` where the CLI would refuse."""
    result, _multi_module = _analyze(path, workspace_dir=None, allow_resolve=allow_resolve)
    return result


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def _with_inbound_conditions(
    links: tuple[Link, ...], conditions: Sequence[Mapping[str, Any]]
) -> tuple[Link, ...]:
    """Each link with the `(environment, holds)` pairs of the inbound endpoint it reaches —
    read off the participants' own `endpoint_conditions` through the federated view, joined
    on (participant, method, path), the identity an inbound row carries. A link to an
    unconditional endpoint keeps the empty tuple."""
    by_endpoint: dict[tuple[str, str | None, str | None], list[tuple[str, str]]] = {}
    for row in conditions:
        key = (
            str(row["participant"]),
            None if row["method"] is None else str(row["method"]),
            None if row["path"] is None else str(row["path"]),
        )
        by_endpoint.setdefault(key, []).append((str(row["environment"]), str(row["holds"])))
    return tuple(
        replace(
            link,
            to_conditions=tuple(
                by_endpoint.get((link.to_participant, link.to_method, link.to_path), ())
            ),
        )
        for link in links
    )


def _reconstructed_report(
    path: Path, workspace: DuckDbWorkspace, metadata: dict[str, Any]
) -> tuple[ModuleModel, ResolveReport]:
    """`analyze`'s own `ModuleModel`/`ResolveReport`, read back from
    `metadata.json` and the workspace rather than re-derived — the "no
    analysis" rule (M00) `render` and `enrich` both keep: neither
    re-detects, re-scans, or re-resolves."""
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
        libraries_not_resolved=tuple(metadata.get("libraries_not_resolved", [])),
        # Absent from a `metadata.json` written before 2026-10-21, and then the declared
        # set is what that analysis had — which is what the defaults say.
        dependency_source=module_info.get("dependency_source", "declared"),
        dependency_source_reason=module_info.get("dependency_source_reason"),
    )
    skipped_catalogs = [
        SkippedCatalog(
            skipped["catalog_id"],
            tuple(skipped["missing_capabilities"]),
            # Absent from a `metadata.json` written before 2026-10-22; nothing was recorded.
            tuple(skipped.get("feeds", ())),
        )
        for skipped in metadata.get("skipped_catalogs", [])
    ]
    report = ResolveReport(
        facts_loaded=cast(int, workspace.query("facts")[0]["facts"]),
        endpoints=workspace.query("endpoints"),
        # F8 §9.5 (W38). The DISTRIBUTIONS too, not just the document counts: `render`
        # reads the workspace back rather than re-resolving, so a summary composed only in
        # `resolve/pipeline.py` reached `metadata.json` and never the document a person
        # opens — which is the reader the standing instrument exists for.
        coverage=coverage_of(workspace),
        skipped_catalogs=skipped_catalogs,
        shapes=workspace.query("shapes"),
        # Read back off the workspace, exactly as `endpoints` and `shapes` are,
        # so `render` shows the two non-wire sections without re-resolving
        # (M00's "no analysis" rule). Not from `metadata.json`: these are rows,
        # and the workspace is where rows live.
        scheduled_work=workspace.query("scheduled_work"),
        error_handlers=workspace.query("error_handlers"),
        endpoint_conditions=workspace.query("endpoint_conditions"),
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
    "the same code path, so the two can never disagree").

    It passes no display choice down at all: there is one document, the
    complete one, for the person and for the model alike. `render --brief`
    was the one exception and was deleted rather than repaired (GUIDELINES
    §8.4's audit list) — it drew a prefix of `## Traces` in table order, which
    is an arbitrary cut presented as a reduced document."""
    reconstructed, report = _reconstructed_report(path, workspace, metadata)
    sections = assemble_module_document(
        reconstructed,
        report,
        _commit_of(path),
        tuple(metadata.get("uncovered", [])),
        shape_fields=workspace.query("shape_fields"),
        type_hierarchy=workspace.query("type_hierarchy"),
        resolved_config=workspace.query("resolved_config"),
        open_questions=workspace.query("open_questions"),
        library_symbols=workspace.query("library_symbols"),
        libraries_not_scanned=tuple(metadata.get("libraries_not_scanned", [])),
        redactor=redactor,
        overlay=overlay,
        stale=stale,
        # `G-74`'s join, read back rather than re-derived: `reachable_throws` is a
        # `call_edges`/`reachability`-shaped answer, and deciding it a second time here
        # would be the same derivation-in-egress `traces` below already refuses.
        reachable_throws=workspace.query("reachable_throws"),
        # The walk runs HERE, at the composition root, and its answer is
        # handed to the renderer as data (2Q `G4`/`I3`). `traces_of` reads the
        # workspace once for all roots — the three projections it builds are
        # the expensive part and the walk itself is not — and `egress` never
        # sees a workspace at all, which is what keeps "Egress is read-only"
        # true of a section whose whole content is a graph traversal.
        #
        # Not "re-analysis" in M00's sense: `roots`, `call_edges` and
        # `return_flows` are rows `analyze` already derived, and this reads
        # them exactly as `endpoints` and `shapes` are read back above.
        traces=traces_of(workspace),
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
    is no overlay at all."""
    if overlay is None:
        return frozenset()
    return frozenset(refusal.index for refusal in stale_claims(overlay, workspace, path, redactor))


def _render(path: Path, *, workspace_dir: Path | None) -> RenderResult:
    """`render`'s own composition, shared by the public `render()` and
    `cli/app.py`'s `module_render`. Reads the workspace `analyze` left
    behind — it never re-detects, re-scans, or re-resolves (M00).

    It takes no display flag: there is one document and it is the complete
    one (GUIDELINES §8.4)."""
    resolved_workspace_dir = _workspace_dir_of(path, workspace_dir)
    _refuse_if_unanalyzed(path, resolved_workspace_dir)
    metadata_path = resolved_workspace_dir / "metadata.json"
    db_path = resolved_workspace_dir / "workspace.duckdb"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    redactor = _redactor_for(path)
    overlay = _overlay_for(path)

    workspace = DuckDbWorkspace(db_path)
    try:
        try:
            stale = _stale_of(overlay, workspace, path, redactor)
            sections, module_id = _assembled_sections(
                path, workspace, metadata, redactor, overlay, stale
            )
        except ClaimRedactionError as refused:
            raise ConfigurationError(str(refused)) from refused
        markdown_target, html_target = _write_rendered_outputs(
            resolved_workspace_dir, sections, module_id
        )
    finally:
        workspace.close()
    return RenderResult(markdown=markdown_target, html=html_target)


def render(path: Path) -> RenderResult:
    """Renders the workspace `analyze` left at `path` — the library
    equivalent of `sextant module render`. Raises `NotAnalyzedError` where
    the CLI would refuse for the same reason, `ConfigurationError` for a bad
    `.sextant.yml`/overlay.

    There is one document and it is the complete one: this function carries
    no display parameter, and `## Traces` draws every trace."""
    return _render(path, workspace_dir=None)


# --------------------------------------------------------------------------
# enrich / enrich_async
# --------------------------------------------------------------------------


def _jailed_roots_of(path: Path, workspace_dir: Path) -> tuple[Path, Path, Path]:
    """The three roots 2K design §4 names: the module's own source, its fact
    root, and its rendered outputs — the exact layout `ToolExecutor.__init__`
    is built to accept (its own docstring: "the module root together with
    its own `.sextant/facts` and `.sextant/render`"). `.sextantignore` is
    loaded for `path` alone, so every root here has to sit under it — true of
    the default `--workspace` layout, and refused loudly by `ToolExecutor`
    itself (caught in `_tool_executor_for`) for a `--workspace` pointed
    anywhere else."""
    return (path, workspace_dir / "facts", workspace_dir / "render")


def _tool_executor_for(path: Path, workspace_dir: Path, redactor: Redactor) -> ToolExecutor:
    try:
        return ToolExecutor(_jailed_roots_of(path, workspace_dir), redactor, IgnoreRules.load(path))
    # `ToolExecutor.__init__` also calls `Path.home()` (2K Task 7 fix round
    # 3), which raises `RuntimeError` rather than `ValueError` when no home
    # directory can be resolved — a container image with no `HOME` set,
    # above all (2K Task 8 review). Caught into the same message, for the
    # same reason every other refusal in this module is: an environment the
    # caller wiring this jail up needs to fix, not a crash in the tool.
    except (ValueError, RuntimeError) as refused:
        raise EnrichmentError(str(refused)) from refused


def _tool_definition_json(definition: ToolDefinition) -> dict[str, object]:
    return {
        "name": definition.name,
        "description": definition.description,
        "schema": definition.schema,
    }


def _enrich(
    path: Path,
    *,
    workspace_dir: Path | None,
    agent_flag: str | None,
    model_flag: str | None,
    max_turns_flag: int | None,
    auth_flag: str | None,
    dry_run: bool,
    ingest_path: Path | None,
    on_report: Callable[[str], None] | None = None,
) -> _EnrichOutcome:
    """`enrich`'s own composition, shared by the public `enrich()`/
    `enrich_async()` and `cli/app.py`'s `module_enrich`. Composes the brief,
    runs the agent (or a `dry_run`/`ingest_path` door), validates the answer
    by construction, writes `.sextant-enrichment.json`, and auto-assembles
    both rendered outputs — one call, done (2K design §8: "no second render
    command").

    `on_report` (fix round 1, MAJOR-1) is called, one line per call, with
    each per-claim refusal and — where the run was partial — the partial
    line, at the exact point BASE's own `module_enrich` printed them: after
    the overlay and transcript are written, but BEFORE the final assembly
    that can still raise `EnrichmentError` (a `redact:` rule wide enough to
    break the surviving overlay's own claim schema). The extraction's first
    pass moved that report to `cli/app.py`, printed only after `_enrich`
    returned — which lost it precisely when assembly failed afterward, the
    one case a user most needs to see WHICH claims made it in before reading
    why the run then errored. `None` (the public `enrich()`/`enrich_async()`
    never pass one) prints nothing, matching the facade's own "quiet"
    contract; `cli/app.py`'s thin wrapper passes `click.echo`, the same
    shape `on_module` already uses for `analyze`."""
    if dry_run and ingest_path is not None:
        raise EnrichmentError("--dry-run and --ingest are mutually exclusive")

    # `ToolExecutor` resolves its jailed roots to absolute paths and checks
    # them against `IgnoreRules.load`'s own `repo_root` unresolved (2K Task
    # 5) — a relative `path` would make every root fail that check even
    # though it is genuinely contained. Resolved once, here, so `path` and
    # everything built from it agree on one spelling for the rest of this
    # call.
    path = path.resolve()
    resolved_workspace_dir = _workspace_dir_of(path, workspace_dir)
    _refuse_if_unanalyzed(path, resolved_workspace_dir)
    metadata_path = resolved_workspace_dir / "metadata.json"
    db_path = resolved_workspace_dir / "workspace.duckdb"

    redactor = _redactor_for(path)
    defaults = _enrich_defaults_for(path)
    # `is None`, never `or` (2K Task 7 fix round 1, minor): a flag's own
    # falsy-but-meaningful value — `max_turns=0` above all — must reach
    # `TradewindAgent`'s own validation as what it is.
    agent_name = agent_flag if agent_flag is not None else defaults.agent
    model_name = model_flag if model_flag is not None else defaults.model
    max_turns = (
        max_turns_flag
        if max_turns_flag is not None
        else (defaults.max_turns if defaults.max_turns is not None else DEFAULT_MAX_TURNS)
    )
    auth_name = auth_flag if auth_flag is not None else defaults.auth
    # `session_store` has no CLI flag counterpart (2N design §1) — its only
    # source besides the agent's own per-auth default is `.sextant.yml
    # enrich: session_store:`.
    session_store = Path(defaults.session_store) if defaults.session_store is not None else None

    instructions = instructions_path().read_text(encoding="utf-8")
    instructions_hash = "sha256:" + hashlib.sha256(instructions.encode("utf-8")).hexdigest()

    # Checked here, in the composition root — `application` reads no files
    # (`tests/architecture/test_source_rules.py`), so the stage decides
    # whether a missing rendered document is refused; this is only the check.
    # The file is a GATE, never the brief's source (see below).
    architecture_md_path = resolved_workspace_dir / "render" / "architecture.md"
    if not architecture_md_path.is_file():
        raise EnrichmentError(
            f"{path} has no rendered document at {architecture_md_path} — run "
            f"`sextant module render {path}` first"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    # Built only now that a rendered document is confirmed on disk (2K Task 7
    # fix round 1, CRITICAL C1b): `ToolExecutor` refuses a jailed root that
    # does not exist, and `workspace_dir/"render"` genuinely does not exist
    # for an analysed-but-unrendered workspace — the exact case just refused
    # above, with this composition's own message. Building the jail any
    # earlier would trade that honest message for `ToolExecutor`'s generic
    # missing-root one, which was the live failure the fix round 1 review
    # actually reproduced.
    executor = _tool_executor_for(path, resolved_workspace_dir, redactor)
    roots = _jailed_roots_of(path, resolved_workspace_dir)

    workspace = DuckDbWorkspace(db_path)
    try:
        # The brief's document is assembled IN MEMORY, machine-only — never
        # the bytes already on disk (2K final review, F1): after one
        # `enrich`, the on-disk file is the ENRICHED one, and reading it
        # would feed a second run its own prior claims as if they were
        # findings.
        sections, _ = _assembled_sections(
            path, workspace, metadata, redactor, overlay=None, stale=frozenset()
        )
        architecture_md = markdown_document(sections)
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
            raise EnrichmentError(str(refused)) from refused

        if dry_run:
            brief_path = resolved_workspace_dir / "enrich-brief.json"
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
            instructions_copy = resolved_workspace_dir / "enrich-instructions.md"
            instructions_copy.write_text(instructions, encoding="utf-8")
            return _EnrichOutcome(
                overlay_path=None,
                brief_path=brief_path,
                instructions_copy_path=instructions_copy,
                markdown=None,
                html=None,
                accepted=0,
                refused=0,
                partial_reason=None,
            )

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
                raise EnrichmentError(
                    "--ingest needs --agent and --model to label the overlay's provenance "
                    "(no adapter runs, so nothing else can say who produced the answer)"
                )
            answers_text = ingest_path.read_text(encoding="utf-8")
            transcript: tuple[dict[str, object], ...] = ()
            partial, partial_reason = False, None
        else:
            # Defaults only apply to a LIVE run — never to `ingest_path`'s
            # own `agent_name is None` check just above, which stays a hard
            # requirement.
            if agent_name is None:
                agent_name = "tradewind"
            if auth_name is None:
                auth_name = "subscription"
            known = ", ".join(sorted(AGENT_REGISTRY))
            if agent_name not in AGENT_REGISTRY:
                raise EnrichmentError(f"unknown --agent {agent_name!r} — known agents: {known}")
            if model_name is None:
                raise EnrichmentError("--model is required")
            try:
                agent = AGENT_REGISTRY[agent_name](
                    auth=auth_name,
                    model=model_name,
                    max_turns=max_turns,
                    session_store=session_store,
                )
            except ValueError as refused:
                # `TradewindAgent.__init__`'s own validation (the api-key
                # ceiling above all): a bad flag value is the user's own
                # input written wrong, not a crash.
                raise EnrichmentError(str(refused)) from refused
            try:
                answers = agent.run(brief, executor)
            except EnrichmentAgentError as refused:
                raise EnrichmentError(str(refused)) from refused
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
        except (
            enrich_stage.MalformedAnswersError,
            enrich_stage.EmptyPartialAnswerError,
        ) as refused:
            raise EnrichmentError(str(refused)) from refused

        # Written BEFORE assembly, deliberately (2K Task 7 fix round 1): the
        # overlay IS the run's record — a later assembly failure must not
        # lose it.
        overlay_path = path / ENRICHMENT_FILE
        overlay_path.write_text(
            result.overlay.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )

        # The workspace record (2K Task 7 ruling 4): every tool call, and
        # one final line naming exactly how the run ended.
        transcript_path = resolved_workspace_dir / "enrich-transcript.jsonl"
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
        # that did not end cleanly — before either is buried in a file, and
        # (fix round 1, MAJOR-1) before the assembly below, which can still
        # raise: a report already printed is a report a `ClaimRedactionError`
        # two lines later cannot take back.
        if on_report is not None:
            for refusal in result.refusals:
                on_report(f"refused claim {refusal.index}: {refusal.reason}")
            if result.partial:
                on_report(
                    f"partial answer ({result.partial_reason}) — overlay reflects what exists"
                )

        try:
            stale = _stale_of(result.overlay, workspace, path, redactor)
            sections, module_id = _assembled_sections(
                path, workspace, metadata, redactor, result.overlay, stale
            )
        except ClaimRedactionError as refused:
            raise EnrichmentError(str(refused)) from refused
        markdown_target, html_target = _write_rendered_outputs(
            resolved_workspace_dir, sections, module_id
        )
    finally:
        workspace.close()

    return _EnrichOutcome(
        overlay_path=overlay_path,
        brief_path=None,
        instructions_copy_path=None,
        markdown=markdown_target,
        html=html_target,
        accepted=len(result.overlay.claims),
        refused=len(result.refusals),
        partial_reason=result.partial_reason,
    )


def enrich(
    path: Path,
    *,
    agent: str = "tradewind",
    auth: str = "api-key",
    max_turns: int | None = None,
    dry_run: bool = False,
    ingest: Path | None = None,
) -> EnrichResult:
    """Runs one enrichment over the workspace `analyze`/`render` left at
    `path` — the library equivalent of `sextant module enrich`. `auth`
    defaults to `"api-key"`, the opposite of the CLI's own `"subscription"`
    default (module docstring: a library host is a service with no login).
    `model` has no facade parameter — it comes from `path`'s own
    `.sextant.yml enrich: model:`, the same source the CLI falls back to
    when `--model` is absent; a module with neither is refused exactly as
    the CLI refuses a bare `--agent`/no `--model` invocation. `agent`/`auth`
    are the ASYMMETRIC case (fix round 1, MINOR-11): both are real Python
    defaults here, never `None`, so — unlike `model`/`max_turns`, which fall
    back to `.sextant.yml enrich:` whenever this call's own value is left at
    its default — a module's own `enrich: agent:`/`auth:` config keys are
    never consulted through this facade at all; pass them explicitly to
    override this call's own default instead of relying on the file.

    Blocks until the run is done — including any network call the agent
    makes. Calling this from inside an already-running event loop reaches
    `TradewindAgent`'s own `asyncio.run` nested, which fails; use
    `enrich_async` there instead (module docstring)."""
    outcome = _enrich(
        path,
        workspace_dir=None,
        agent_flag=agent,
        model_flag=None,
        max_turns_flag=max_turns,
        auth_flag=auth,
        dry_run=dry_run,
        ingest_path=ingest,
    )
    return EnrichResult(
        overlay=outcome.brief_path if dry_run else outcome.overlay_path,
        accepted=outcome.accepted,
        refused=outcome.refused,
        partial_reason=outcome.partial_reason,
    )


async def enrich_async(
    path: Path,
    *,
    agent: str = "tradewind",
    auth: str = "api-key",
    max_turns: int | None = None,
    dry_run: bool = False,
    ingest: Path | None = None,
) -> EnrichResult:
    """`enrich`, awaited — the same composition, run on a worker thread
    (module docstring's own "`enrich_async`" section states why): safe to
    call from inside an async service's own running event loop, unlike the
    plain synchronous `enrich`. Two costs that section also states: one
    blocked executor thread for the full run per concurrent call, and no
    real cancellation — a cancelled `await` leaves the worker finishing
    (and still writing the overlay/documents) regardless."""
    return await asyncio.to_thread(
        enrich,
        path,
        agent=agent,
        auth=auth,
        max_turns=max_turns,
        dry_run=dry_run,
        ingest=ingest,
    )


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def _export(path: Path, *, workspace_dir: Path | None, out_dir: Path | None = None) -> ExportResult:
    """`export`'s own composition, shared by the public `export()` and
    `cli/app.py`'s `module_export`. Reads what `analyze` left — it never
    re-analyzes (M08)."""
    resolved_workspace_dir = _workspace_dir_of(path, workspace_dir)
    _refuse_if_unanalyzed(path, resolved_workspace_dir)
    metadata_path = resolved_workspace_dir / "metadata.json"
    db_path = resolved_workspace_dir / "workspace.duckdb"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    commit = str(metadata["provenance"]["commit"])
    bundle_name = re.sub(r"[^A-Za-z0-9._-]", "-", str(metadata["module"]["id"])) + "@" + commit
    bundle = (out_dir or resolved_workspace_dir / "bundles") / bundle_name

    redactor = _redactor_for(path)
    workspace = DuckDbWorkspace(db_path)
    try:
        tables = workspace.export_tables(bundle, redactor)
        facts_files = workspace.export_facts(bundle, redactor)
        # F8 §9.3 (W35). A third projection beside `graph/` and `render/`: the same rows,
        # joined to a file and a line, in the shape a machine reader greps. Derived from
        # the tables inside the same open workspace, so the index and the dataset it
        # indexes can never be two different runs.
        index_files = write_index(
            bundle,
            symbols=workspace.query("located_symbols"),
            documents=workspace.query("located_documents"),
            call_edges=workspace.query("call_edges"),
            implementations=workspace.query("implementations"),
            annotations=workspace.query("located_annotations"),
            endpoints=workspace.query("endpoints"),
            roots=workspace.query("roots"),
            shapes=workspace.query("shapes"),
            shape_fields=workspace.query("shape_fields"),
            source_roots=[str(root) for root in metadata["module"].get("source_roots", [])],
            module_root=path,
            redactor=redactor,
        )
    finally:
        workspace.close()

    # Both rendered documents travel with the bundle when `render` has
    # already produced them (2K design §6b) — copied verbatim, already
    # masked at the render exit.
    render_dir = resolved_workspace_dir / "render"
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
        # Copied from what `analyze` recorded. Recomputed ONLY for a workspace analysed before
        # `analyze` recorded it, whose metadata has no such key.
        catalog_hash=metadata.get("catalog_hash") or _catalog_hash(catalogs_dir()),
        redaction_set_hash=redactor.rule_set_hash,
        module_commit=_module_commit_of(path),
        tables=tables,
        facts_files=facts_files,
        render=shipped_render,
        index=index_files,
    )
    return ExportResult(bundle=bundle)


# --------------------------------------------------------------------------
# system analyze
# --------------------------------------------------------------------------

# The system scope's own files, beside the module layout `analyze` writes. A reactor root
# may itself be a module, so neither name collides with one: `modules.json` already lives
# here and this is its tier's workspace and document.
_SYSTEM_WORKSPACE = "system.duckdb"
_SYSTEM_DOCUMENT = "system.md"

# The environment every comparison resolves values for where the caller names none (`M06`
# step 0, user decision 7). `default` is the profile a Spring module has with none activated,
# which is also what `config_model`'s own `default_profile` calls it.
DEFAULT_ENVIRONMENT = "default"


def system_analyze(path: Path, *, environment: str = DEFAULT_ENVIRONMENT) -> SystemResult:
    """Link the modules of the reactor at `path` to each other — the library equivalent of
    `sextant system analyze`.

    **It analyses nothing.** `M05`'s own division of labour, which this path keeps for one
    reactor: the participant set is the `modules.json` that `module analyze` already wrote,
    and each participant's graph is the workspace it already left. A module with no workspace
    is a participant marked absent with that reason, never a module quietly left out —
    `M06` attributes an unmatched call into an absent participant to the gap rather than to
    the architecture, and it can only do that if the participant has a row.

    Raises `NotAnalyzedError` where the reactor root carries no `modules.json` at all, which
    is the same refusal `render` makes for the same reason: there is nothing to read, and
    saying "no links" would be a claim about the system rather than about the run.
    """
    root = path.resolve()
    modules_json = _modules_json_path(root)
    if not modules_json.exists():
        raise NotAnalyzedError(
            f"no analysis found at {root}: `system analyze` reads the `modules.json` that "
            f"`module analyze` writes at a reactor root. Run "
            f"`sextant module analyze {root}` first."
        )
    entries = cast(
        list[dict[str, Any]], json.loads(modules_json.read_text(encoding="utf-8"))["modules"]
    )
    for entry in entries:
        module_root = root / str(entry.get("dir") or "")
        candidate = module_root / ".sextant" / "workspace.duckdb"
        entry["location"] = candidate if candidate.exists() else None
        entry["commit_id"] = _module_commit_of(module_root) if candidate.exists() else None
    participants = _participants_of(entries)

    system_dir = root / ".sextant"
    system_dir.mkdir(parents=True, exist_ok=True)
    workspace_path = system_dir / _SYSTEM_WORKSPACE
    # Rebuilt per run rather than reopened: the two native tables are replaced whole anyway,
    # and a stale ATTACH set is the one piece of state a reset cannot reach.
    workspace_path.unlink(missing_ok=True)
    workspace = DuckDbWorkspace(workspace_path)
    try:
        try:
            workspace.federate(
                {p.name: p.location for p in participants if p.present and p.location is not None}
            )
        except StaleParticipantError as stale:
            # The same refusal `render` makes for a workspace another build derived (D01
            # §7): nothing here this build can read, run `analyze`.
            raise NotAnalyzedError(str(stale)) from stale
        endpoints = workspace.query("system_endpoints")
        config = workspace.query("system_config", environment=environment)
        # WHICH key holds a module's registered name is framework knowledge, so a catalog
        # declares it and this only asks for the answer (`participant_name_key`).
        _catalogs = YamlCatalogSource(catalogs_dir()).load()
        key = next(
            (catalog.participant_name_key for catalog in _catalogs if catalog.participant_name_key),
            None,
        )
        participants = _with_registered_names(participants, config, key)
        links, unmatched = _match_links(participants, endpoints)
        # **A gateway route's prefix, joined to the paths the service it names serves.** It
        # runs after the matcher and adds to it rather than replacing anything: the
        # participant-level link the `lb://` row already produced stays, because the
        # dependency is real whether or not the composition is licensed, and the routes it
        # could not compose are REFUSALS rather than silence.
        names = {
            name: participant.name
            for participant in participants
            if participant.present
            for name in participant.answers_to()
        }
        model = next(
            (
                found
                for catalog in _catalogs
                if (found := _route_model(catalog.matches)) is not None
            ),
            None,
        )
        composed, refusals = _gateway_links(config, endpoints, model, names)
        links = (*links, *composed)
        # Spec 2026-10-21-conditional-controllers (ruling 2): a condition is a property of
        # the inbound endpoint and travels with it as data. Nothing above read it; each
        # link now carries its inbound endpoint's per-environment verdicts so the system
        # document can state them beside the link, and nothing is dropped for it.
        links = _with_inbound_conditions(links, workspace.query("system_endpoint_conditions"))
        uncalled = _uncalled_endpoints(endpoints, links)
        workspace.derive("participants_reset")
        workspace.derive("participants_insert", rows=[p.row() for p in participants])
        workspace.derive("links_reset")
        if links:
            workspace.derive("links_insert", rows=[link.row() for link in links])
    finally:
        workspace.close()

    render_dir = system_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    document = render_dir / _SYSTEM_DOCUMENT
    document.write_text(
        render_system_document(
            participants, links, unmatched, uncalled, refusals, environment=environment
        ),
        encoding="utf-8",
    )
    return SystemResult(
        document=document,
        workspace=workspace_path,
        participants=len(participants),
        links=len(links),
        unmatched=len(unmatched),
        uncalled=len(uncalled),
        route_refusals=len(refusals),
    )


def export(path: Path) -> ExportResult:
    """Exports the workspace `analyze` left at `path` as a D06 bundle
    (Parquet plus a manifest) — the library equivalent of `sextant module
    export`. Raises `NotAnalyzedError` where the CLI would refuse for the
    same reason."""
    return _export(path, workspace_dir=None)
