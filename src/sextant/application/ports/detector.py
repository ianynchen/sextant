"""The Detector port (M02). Works out what a repository contains, before
anything reads code. Implementations are keyed by build system, never by
language — a module records the languages present."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sextant.application.ports.selection import NoAdapterError


@dataclass(frozen=True)
class LibraryRoot:
    """One dependency a module opted into extracting (D04 §2a): the coordinate
    it was named by, and the archive that coordinate resolved to.

    Both halves are carried because they answer different questions. The
    ARCHIVE is what the scanner reads, and it is a path on this machine — it
    says nothing outside the machine that resolved it. The COORDINATE is what
    every document extracted from it records as its `origin` (D00 §2), so it is
    the half that survives into a bundle and into the rendered document. The
    version is the one the module's build declares for that dependency, and it
    rides along because a scanned symbol's identity carries it.
    """

    coordinate: str
    version: str
    archive: Path


@dataclass(frozen=True)
class ModuleModel:
    module_id: str
    coordinates: str
    version: str
    root: Path
    kind: str
    languages: frozenset[str]
    source_roots: tuple[Path, ...]
    output_dirs: tuple[Path, ...]
    # Maven's own packaging value (`<packaging>`, defaulting to `jar` when
    # the element is absent — Maven's own default, not a guess this
    # detector invents). Defaulted so every existing construction site
    # keeps working. Read by the multi-module CLI (2M design §2, ruled
    # amendment): a leaf module packaged `pom` is a BOM or aggregation-only
    # sibling with nothing to scan, and the one kind-independent signal
    # that a module is NOT a service — every other packaging is analyzed
    # regardless of `kind`, since `kind` alone is honestly `undetermined`
    # for most real modules and was never meant to gate analysis.
    packaging: str = "jar"
    # Where the ArtifactReader port (M03's second port) looks for config
    # files — `src/main/resources` for Maven. Defaulted so every existing
    # construction site keeps working; a build system that names none
    # reports the empty tuple, never a guess.
    resource_roots: tuple[Path, ...] = ()
    # Where the ArtifactReader port looks for schema source files — Maven's
    # protobuf-maven-plugin/avro-maven-plugin convention, `src/main/proto`
    # then `src/main/avro` when present (2G design §2). A schema root is
    # never a source root (`MavenDetector` already excludes these directory
    # names from `languages`, Task 1) — the code these plugins generate is
    # what the real source roots compile, not the schema files themselves.
    # Defaulted for the same reason `resource_roots` is.
    schema_roots: tuple[Path, ...] = ()
    # The libraries this module asked to have extracted alongside its own
    # output, already resolved to archives (2I design §5). Empty for every
    # module that names none, which is every module that ships no
    # `.sextant.yml` — the opt-in is the file, so an empty tuple here is the
    # default state and not a failure.
    library_roots: tuple[LibraryRoot, ...] = ()
    # The coordinates it named that could NOT be resolved to an archive — a
    # dependency the build never declares a version for, or one no local
    # repository holds. Carried rather than raised: a library nobody could find
    # is a gap the artifacts must name (FR-17), the same way an uncovered
    # source is, and refusing the whole analysis over it would answer a
    # question nobody asked.
    libraries_not_resolved: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositoryModel:
    root: Path
    modules: tuple[ModuleModel, ...] = field(default_factory=tuple)
    # Detect-time observations that are neither a module fact nor a refusal
    # (2M design §1c): build-system coexistence, a wrapper fallback, a
    # boundary Sextant refuses but does not fail the whole detection over.
    # Carried into `metadata.json` verbatim. A sorted tuple, never a set or a
    # list — determinism (NFR-1) applies to notes exactly as it does to every
    # other reader-facing sequence this model produces.
    notes: tuple[str, ...] = ()
    # Whether the TARGETED root itself declared `<modules>` (2M Task 2 fix
    # round 1, F1) — the multi-module CLI gate, never `len(modules) > 1`: a
    # reactor naming exactly one child is still a reactor (its own child
    # analyzes into the CHILD's workspace, not the aggregator's), and
    # `fixtures/pom.xml` is exactly this shape. Defaulted `False` so every
    # existing construction site — every one of them a single leaf module —
    # keeps working unchanged.
    multi_module: bool = False


class Detector(Protocol):
    """Keyed by build system, never by language (M02)."""

    def accepts(self, path: Path) -> bool: ...
    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel: ...


def select_detector(detectors: Sequence[Detector], path: Path) -> Detector:
    """The first detector that recognises this repository.

    First rather than best: detectors are keyed by build system, and where a
    repository carries two build files the registry's order is the deliberate
    statement of which one is authoritative. There is no rank to appeal to.
    """
    for detector in detectors:
        if detector.accepts(path):
            return detector
    raise NoAdapterError(f"no detector recognises {path} as a repository it can read")
