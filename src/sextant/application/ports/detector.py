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
    # Of `library_roots`, the ones that are REACTOR SIBLINGS this module declares as
    # dependencies (F4 §5.2, W24) — scanned automatically rather than named by anybody.
    # `extract_libraries` entries are the other kind and are deliberately not here: that
    # file is a person saying "scan this dependency's own bytecode as well as mine", and
    # what it opts into includes the dependency's own surface.
    sibling_coordinates: tuple[str, ...] = ()
    # The `groupId:artifactId` coordinates this module's BUILD declares, as
    # the build system reports them — D00 §5's `module` fact carries them into
    # the workspace, where a catalog whose framework rule is conditional on a
    # dependency being present can read them (2O design §2a, ruling R9).
    #
    # **The two build systems answer differently, and the difference is
    # visible rather than smoothed over.** Gradle reports the RESOLVED compile
    # classpath, transitives included. Maven reports what the module's own POM
    # DECLARES plus what it INHERITS — every ancestor pom the detector could
    # open contributes its `<dependencies>`, since Maven puts those on the
    # child's classpath too (F1). What it still does not reach is TRANSITIVES:
    # a third-party artifact's own dependencies need Maven's mediation rules,
    # which is a resolver rather than a parse, so a coordinate arriving only
    # that way is absent here. A reader must therefore still treat "absent" as
    # "not declared or inherited here", never as "not on the classpath".
    # *Before F1 this was the POM's DIRECT declarations alone, which had the
    # dependency gate skipping every module whose starter came from a company
    # parent.* Empty for a module whose build declares none, and for every
    # hand-built model in a test — which is why the gate that reads it treats
    # empty as UNANSWERABLE rather than as absence.
    dependency_coordinates: tuple[str, ...] = ()
    # The VERSION each of those coordinates resolved to, for the subset that
    # resolved (F1). Built in sorted key order, so its serialization is stable
    # (NFR-1). A separate mapping rather than a third segment on the
    # coordinate, because the coordinate is an IDENTITY that `detect
    # .coordinates` matches on and a version glued to it would match nothing.
    #
    # **Not every coordinate is in it, and that is the honest shape.** Maven
    # resolves a version from the declaration, from an ancestor's
    # `<dependencyManagement>`, from an imported BOM, and through `${…}`
    # properties — each of which needs the pom that states it to be readable,
    # on disk or in the local Maven repository. Every coordinate that leaves
    # unversioned is named in `dependencies_not_resolved` below. Gradle's
    # resolved report carries a version for every entry, so on Gradle this maps
    # the whole set.
    dependency_versions: dict[str, str] = field(default_factory=dict)
    # The compiler target release this module's BUILD declares — and `None`
    # where it declares
    # none, which is an absence rather than a default. §8.2 admits it: a value
    # written in the pom or build script is code, not a deployment possibility.
    #
    # Its consumer is multi-release SELECTION: which overlay of a class in a
    # dependency actually loads is a property of the module doing the
    # depending, and this is where that module says so. Nothing else may read
    # it as "the JDK this was built with" — a build can declare a release its
    # toolchain does not match, which is the whole point of `--release`.
    declared_release: int | None = None
    # Why a coordinate above has no version, and which ancestor or BOM could
    # not be opened — one sentence each, sorted (NFR-1). Carried rather than
    # raised, exactly as `libraries_not_resolved` is: a version nobody could
    # resolve is a gap the artifacts must name (FR-17), and an under-report
    # this analysis can SEE is one it must state.
    dependencies_not_resolved: tuple[str, ...] = ()
    # The coordinates it named that could NOT be resolved to an archive — a
    # dependency the build never declares a version for, or one no local
    # repository holds. Carried rather than raised: a library nobody could find
    # is a gap the artifacts must name (FR-17), the same way an uncovered
    # source is, and refusing the whole analysis over it would answer a
    # question nobody asked.
    libraries_not_resolved: tuple[str, ...] = ()
    # **Every dependency whose jar resolved on this machine**, as `LibraryRoot`s — not only
    # the ones a person opted into with `extract_libraries` (`library_roots`). The two
    # answer different questions and must not be merged: an opted-in library is SCANNED
    # (every class, every body, its rows become this module's); a dependency here only has
    # the HEADER of each type this module refers to read (`type_header`, D00 §5) — what it
    # extends, implements and is annotated with, nothing below the class level. The
    # extractor is handed this list as its classpath. Empty where nothing resolved, which
    # leaves the scan exactly as it was.
    dependency_archives: tuple[LibraryRoot, ...] = ()
    # WHO answered for the three dependency fields above (spec 2026-10-21 §3b/§3c):
    # `maven` when the build tool's own resolved compile classpath did — transitives
    # included, the version it chose beside each — and `declared` when this detector
    # read the POM chain itself, which reaches no transitive. Gradle has only ever
    # answered the first way; the label exists so a reader of a Maven module can tell
    # the two apart, because they are different claims about the same list.
    dependency_source: str = "declared"
    # Why the build tool did not answer, when it did not — the tool's own last error
    # line, or the precondition that stopped the question being asked (`mvn` not on
    # `PATH`, nothing built). None when `dependency_source` is `maven`. Recorded rather
    # than silent because the declared set is the WEAKER claim and a reader must be
    # able to see which one they hold (user ruling b, 2026-10-21).
    dependency_source_reason: str | None = None


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
