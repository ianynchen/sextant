import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.ingress.detect.conventions import (
    CONTAINER_FILES,
    RESOURCE_SCHEMA_SUFFIXES,
    SOURCE_SCHEMA_NAMES,
)
from sextant.ingress.detect.sextant_config import read_extract_libraries

_POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}
_MAIN_CLASS = f"{{{_POM_NS['m']}}}mainClass"

# Maven's own non-code build directories. Named here because they are build
# layout, not languages: everything else under src/main is a source root, and
# the name of that directory is what the build says is compiled there.
_NON_SOURCE_DIRECTORIES = frozenset({"resources", "webapp", "filters"})

# Schema dirs are not languages, so this detector must not report one from
# them (protobuf-maven-plugin/avro-maven-plugin convention) — shared with
# `GradleDetector` (2M Task 3 fix round 1, M2).
_SCHEMA_DIRECTORIES = frozenset(SOURCE_SCHEMA_NAMES)

# Every schema root, as its path segments under `src/main`, in the order
# `schema_roots` reports them. Spring GraphQL's SDL directory is the one that
# is not a sibling of the source roots: SDL ships on the classpath, so it
# lives UNDER `src/main/resources`. It needs no entry in _SCHEMA_DIRECTORIES
# for that reason — `resources` is already a non-source directory, so no
# language was ever going to be reported from under it. The three WSDL/XSD
# directories (2I design §3) are classpath resources for the same reason: a
# SOAP contract is served at runtime, and `META-INF/wsdl` is where the JAX-WS
# packaging convention puts it. Conventional directories only — Maven has no
# declaration of a contract directory for this detector to read instead, so a
# WSDL kept anywhere else is a stated boundary rather than a guess.
_SCHEMA_ROOT_PATHS = (
    *((name,) for name in SOURCE_SCHEMA_NAMES),
    *(("resources", *suffix) for suffix in RESOURCE_SCHEMA_SUFFIXES),
)


def _no_version_reason(declared_as_a_dependency: bool) -> str:
    """Why a coordinate reached no version — the half of the gap that says what
    to do about it. Both answers end at the same remedy, which is why both name
    it: the three-segment form in `.sextant.yml` states the version outright and
    asks the POM nothing."""
    if declared_as_a_dependency:
        return (
            "this module declares the dependency in a form this detector does not read a "
            "version from (a managed version, a `${...}` property, or a classifier/type) "
            "— pin it as `groupId:artifactId:version`"
        )
    return (
        "this module's pom.xml declares no such dependency — declare it, or pin the "
        "version as `groupId:artifactId:version`"
    )


def _repository_layout(coordinate: str, version: str) -> str:
    """Where one coordinate sits WITHIN a Maven repository —
    `<group as directories>/<artifact>/<version>/<artifact>-<version>.jar`,
    relative to the repository root and never anchored to one.

    The half of the location that is true on every machine, which is what makes
    it safe to publish: the reader supplies the root they actually have.
    """
    group, _, artifact = coordinate.partition(":")
    return f"{'/'.join(group.split('.'))}/{artifact}/{version}/{artifact}-{version}.jar"


def _local_repository_archive(coordinate: str, version: str) -> Path:
    """Maven's own local-repository layout for one coordinate — resolved at
    call time rather than at import, so a test or a caller that moves `HOME`
    is not answered from whatever it was when this module loaded."""
    return Path.home() / ".m2" / "repository" / _repository_layout(coordinate, version)


def _local_repository_pom(coordinate: str, version: str) -> Path:
    """The same layout, for the POM beside the archive. A parent and an
    imported BOM are both published as `.pom` and nothing else, so this is the
    only file there is to read for either."""
    return Path(_local_repository_archive(coordinate, version).as_posix()[: -len(".jar")] + ".pom")


# How far the inheritance walk goes before it refuses (F1). A real chain is
# three or four deep — module, company parent, `spring-boot-starter-parent`,
# `spring-boot-dependencies` — and a cycle is a broken build, which the `seen`
# set below already refuses by identity. This cap is the second belt: a chain
# longer than this is either generated or wrong, and reading it is neither
# cheap nor informative.
_MAX_INHERITANCE_DEPTH = 16
# `${…}` interpolation passes. A property whose value names another property
# is ordinary; one that needs seventeen rounds to settle is a loop, and a loop
# must terminate as "unresolved" rather than spin.
_MAX_INTERPOLATION_PASSES = 8
_IMPORT_SCOPE = "import"

# What Maven prints when a dependency it needs is not in the local repository and `-o`
# forbids fetching it — the ONE failure `allow_resolve` licenses a second, online attempt
# for (M02), recognised by Maven's own words the way `gradle.py` recognises Gradle's.
_OFFLINE_REFUSAL_SUBSTRING = "in offline mode"
# Where `dependency:build-classpath` writes. RELATIVE, so Maven resolves it against each
# module's own basedir and a reactor run leaves one file per module under the build output
# directory every checkout already ignores.
_CLASSPATH_FILE = Path("target") / "sextant-classpath.txt"
# A cap, not a guess at how long a build takes (the Gradle detector's own figure): the
# reactor form attaches `compile`, and a build that never finishes must become a named
# reason, never a hang.
_MAVEN_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class _ResolvedClasspath:
    """One module's compile classpath as MAVEN resolved it (spec 2026-10-21 §3b): the jars
    under the local repository as archives with the coordinate and version their path
    spells, the reactor siblings it lists as `target/classes` directories, and every entry
    that is neither — named, so a reader can see what the resolved set left unnamed."""

    archives: tuple[LibraryRoot, ...]
    versions: dict[str, str]
    siblings: tuple[LibraryRoot, ...]
    unresolvable: tuple[str, ...]


_PLACEHOLDER = re.compile(r"\$\{([^{}]+)\}")


def _text_of(element: ElementTree.Element, tag: str) -> str | None:
    """One child element's stripped text, or `None` where the child is absent
    or empty. An empty element is an absence rather than an empty value: a
    `<version/>` names no version."""
    child = element.find(f"m:{tag}", _POM_NS)
    if child is None or child.text is None or not child.text.strip():
        return None
    return child.text.strip()


def _coordinate_of(dependency: ElementTree.Element) -> str | None:
    """`groupId:artifactId`, or `None` for a declaration missing either — a
    dependency with no coordinate is a broken POM element, and skipping it is
    what this detector already did before it had a name for it."""
    group = _text_of(dependency, "groupId")
    artifact = _text_of(dependency, "artifactId")
    return None if group is None or artifact is None else f"{group}:{artifact}"


def _coordinates_of(pom: ElementTree.Element) -> str | None:
    """A POM's own `groupId:artifactId`, with groupId falling back to its
    parent's the way Maven's inheritance does. Read to CHECK a `<relativePath>`
    candidate is the parent it claims to be, never to identify a module."""
    group = _text_of(pom, "groupId")
    if group is None:
        parent = pom.find("m:parent", _POM_NS)
        group = None if parent is None else _text_of(parent, "groupId")
    artifact = _text_of(pom, "artifactId")
    return None if group is None or artifact is None else f"{group}:{artifact}"


def _parsed_pom(path: Path) -> ElementTree.Element | None:
    """A POM this resolution went looking for, or `None` where it is absent or
    unreadable.

    `None` rather than a raise, unlike `MavenDetector._pom` (which reads the
    module's OWN pom, where malformed XML is a refusal): an ANCESTOR that
    cannot be parsed is a shortfall in reach, the caller names it in
    `dependencies_not_resolved`, and failing the whole detection over somebody
    else's published pom would answer a question nobody asked.
    """
    if not path.is_file():
        return None
    try:
        return ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return None


def _interpolated(raw: str, properties: dict[str, str]) -> str | None:
    """`raw` with every `${…}` replaced, or `None` where one of them names
    something these properties do not define.

    Repeated passes because a property's value may itself be a property, and
    capped because a pair that name each other is a loop the build itself
    would refuse. `None` is the honest answer for an unresolved placeholder —
    an unexpanded `${spring.version}` written into a version column would be a
    version nobody released.
    """
    value = raw.strip()
    for _ in range(_MAX_INTERPOLATION_PASSES):
        if "${" not in value:
            return value
        replaced = _PLACEHOLDER.sub(lambda hit: properties.get(hit.group(1), hit.group(0)), value)
        if replaced == value:
            return None
        value = replaced
    return None


# Gradle's own build/settings files (2M design §1): when a directory this
# detector accepts ALSO holds one of these, Maven still wins outright — one
# build system per run, stated, never merged — and the coexistence becomes a
# detect note rather than a silent choice.
_GRADLE_BUILD_FILES = (
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
)
_GRADLE_COEXISTENCE_NOTE = "gradle build files present; maven selected"


class MavenDetector:
    """Reads the build, never a convention. Offline by default (M02): the
    prerequisite is a successful build, so the local cache already has the
    classpath.

    A single-module POM is read directly. An aggregation-only POM (one
    declaring `<modules>`, never a module in its own right — 2M design §2)
    is walked recursively instead, each child read by the same
    `_module_of` every leaf goes through, so a reactor child is detected
    identically whether it was reached through the walk or handed to
    `detect` on its own. Classpath resolution via `mvn -o` lands when a
    fixture needs it; any future `mvn` invocation this detector makes must
    pass `-o` unless `allow_resolve` is set.
    """

    def accepts(self, path: Path) -> bool:
        return (path / "pom.xml").is_file()

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        # Read directly, not via `bool(self._walk(...))` or `len(modules) >
        # 1`: whether `path` ITSELF declared `<modules>` is the multi-module
        # gate the CLI branches on (2M Task 2 fix round 1, F1) — a reactor
        # naming exactly one child is still a reactor (that child analyzes
        # into ITS OWN workspace, not the aggregator's), and `fixtures/
        # pom.xml` today names exactly one (`orders-soap-client`).
        top_pom = self._parse_pom(path)
        is_reactor = top_pom.find("m:modules", _POM_NS) is not None
        # Asked ONCE per analysis, from the reactor root, before any module is read
        # (spec 2026-10-21 §3a): every module then finds its own file beside its classes,
        # or inherits the one reason none of them can.
        classpath_reason = self._ask_maven(path, top_pom, is_reactor, allow_resolve)
        modules = self._walk(path, visited=(), seen=set(), classpath_reason=classpath_reason)
        return RepositoryModel(
            root=path, modules=modules, notes=self._notes(path), multi_module=is_reactor
        )

    def _walk(
        self,
        path: Path,
        visited: tuple[Path, ...],
        seen: set[Path],
        classpath_reason: str | None = None,
    ) -> tuple[ModuleModel, ...]:
        """Every buildable module reachable from `path` (2M design §2): a leaf
        POM (no `<modules>`) becomes one `ModuleModel`, exactly as `detect`
        always read a single module; a POM declaring `<modules>` is
        AGGREGATION-ONLY — it names no module of its own, only the children
        named there, walked recursively so a reactor of reactors is read the
        same way a flat one is.

        `visited` is every aggregator directory already on this walk's own
        path to `path`, checked before `path` is read again: a `<modules>`
        entry that leads back to one of them is a cycle, refused loudly
        (DR-6's own discipline — a cycle is not a shape this detector can
        silently skip past) rather than walked forever. `seen` is every LEAF
        already turned into a `ModuleModel`, checked so a parent naming the
        same child by two different spellings (`a` and `./a` — 2M Task 2 fix
        round 1, F6) is analyzed once, not once per spelling.
        """
        resolved = path.resolve()
        if resolved in visited:
            chain = " -> ".join(str(step) for step in (*visited, resolved))
            raise ValueError(f"pom.xml <modules> cycle: {chain}")
        pom = self._parse_pom(path)
        modules_element = pom.find("m:modules", _POM_NS)
        if modules_element is None:
            if resolved in seen:
                return ()
            seen.add(resolved)
            return (self._module_of(path, pom, classpath_reason),)
        module_elements = modules_element.findall("m:module", _POM_NS)
        if not module_elements:
            # An aggregator that names no child analyzes nothing and used to
            # succeed silently — a `render`/`enrich`/`export` pointed at it
            # afterwards then hit the bare "one of: " listing with nothing
            # after it (2M final review wave, MINOR 4). Refused here instead,
            # by the pom that declares the empty `<modules>`.
            raise ValueError(f"{path / 'pom.xml'} declares <modules> but names none")
        children: list[ModuleModel] = []
        for module_element in module_elements:
            text = (module_element.text or "").strip()
            if not text:
                raise ValueError(f"{path / 'pom.xml'} has an empty <module/> entry")
            # `normpath`, not `resolve`: a `<module>` path collapses its own
            # `..` segments lexically, the same way Maven itself reads one,
            # without following symlinks or forcing every `ModuleModel.root`
            # to absolute — `path` stays in whatever form the caller passed
            # `detect` (2M Task 2 review: `fixtures/orders-service`, adopted
            # by `../orders-service`, must report the identical root a
            # direct `detect(FIXTURE)` call would).
            child = Path(os.path.normpath(path / text))
            if not (child / "pom.xml").is_file():
                # Named, not a bare `FileNotFoundError` from the recursive
                # parse below (2M Task 2 fix round 1, F2): a `<module>`
                # naming a directory with no POM is a mistake in the
                # analysed repository, the same class of refusal every other
                # detect-time `ValueError` here already is.
                raise ValueError(
                    f"{path / 'pom.xml'} names <module>{text}</module>, but {child} has no pom.xml"
                )
            children.extend(self._walk(child, (*visited, resolved), seen, classpath_reason))
        return tuple(children)

    @staticmethod
    def _parse_pom(path: Path) -> ElementTree.Element:
        """`path`'s own `pom.xml`, parsed — or a `ValueError` naming that
        file when it is not well-formed XML (2M final review wave, I2/MINOR
        3): a raw `ElementTree.ParseError` names a line and column, never a
        file, which is unactionable the moment a reactor has more than one
        pom to suspect."""
        pom_path = path / "pom.xml"
        try:
            return ElementTree.parse(pom_path).getroot()
        except ElementTree.ParseError as malformed:
            raise ValueError(f"{pom_path} is not well-formed XML: {malformed}") from malformed

    @staticmethod
    def _module_of(
        path: Path, pom: ElementTree.Element, classpath_reason: str | None = None
    ) -> ModuleModel:
        # A reactor child inherits groupId and version from <parent> and may
        # omit its own elements entirely (Maven's inheritance rule) —
        # artifactId alone is never inherited. Reading the parent's value is
        # Maven convention data, not a guess.
        group = MavenDetector._text(pom, "groupId", path, inherited=True)
        artifact = MavenDetector._text(pom, "artifactId", path)
        version = MavenDetector._text(pom, "version", path, inherited=True)
        source_roots = MavenDetector._source_roots(path, pom)
        resources = path / "src" / "main" / "resources"
        library_roots, libraries_not_resolved = MavenDetector._library_roots(path, pom)
        coordinates, versions, not_resolved, declared_release = (
            MavenDetector._resolved_dependencies(path, pom, group, artifact, version)
        )
        # **Maven's own answer, where it gave one** (spec 2026-10-21 §3b). The file
        # `dependency:build-classpath` wrote beside this module's classes replaces three
        # things the POM parse approximates: the dependency set becomes the TRANSITIVE
        # closure with the version Maven chose (what Gradle has always reported), the
        # archives the header read walks become every jar on it, and the reactor siblings
        # become the directories it lists rather than the result of walking sibling POMs.
        # Where it gave none — the user's ruling (b) — the declared set stands, labelled.
        resolved, dependency_source_reason = MavenDetector._from_maven(path, classpath_reason)
        if resolved is not None:
            coordinates = tuple(sorted(resolved.versions))
            versions = dict(sorted(resolved.versions.items()))
            # The declared read's shortfall list described a parse that is no longer the
            # source; a version Maven chose is not "unresolved" because a POM left it to
            # a BOM this detector could not open.
            not_resolved = ()
            siblings = resolved.siblings
            libraries_not_resolved = libraries_not_resolved + resolved.unresolvable
        else:
            # F4 §5.2 (W24). Reactor siblings this module DEPENDS ON, as library roots —
            # appended to whatever `.sextant.yml` opted into, because a sibling is a
            # dependency in every sense that matters here: it is on the classpath, its
            # types appear in this module's signatures, and the only difference from a
            # resolved jar is that it was built from source next door rather than fetched.
            siblings = MavenDetector._sibling_roots(path, pom, coordinates, versions)
        library_roots = library_roots + siblings
        return ModuleModel(
            module_id=f"{group}:{artifact}",
            coordinates=f"{group}/{artifact}",
            version=version,
            root=path,
            kind=MavenDetector._classify(path, pom),
            packaging=MavenDetector._packaging(pom),
            # Observed, never asserted: a module records the languages
            # present (M02), and this detector is keyed by build system, so
            # it has no business naming one.
            languages=frozenset(root.name for root in source_roots),
            source_roots=source_roots,
            output_dirs=(path / "target" / "classes",),
            # Conventional, unlike source_roots: Maven has no
            # `<resourceDirectory>` override worth reading yet, so this
            # stays the one layout it recognises. Present only when it
            # actually exists — the same "no guess" discipline source_roots
            # already follows.
            resource_roots=(resources,) if resources.is_dir() else (),
            # Task 4: the protobuf-maven-plugin/avro-maven-plugin convention,
            # present only when it actually exists — the same "no guess"
            # discipline `resource_roots` keeps.
            schema_roots=tuple(
                root
                for parts in _SCHEMA_ROOT_PATHS
                if (root := path.joinpath("src", "main", *parts)).is_dir()
            ),
            # What this module DECLARES or INHERITS, sorted (NFR-1), with the
            # version each one resolved to beside it (F1 — see
            # `_resolved_dependencies` for what that reads and what it refuses
            # to). TRANSITIVES are still absent: a coordinate this list omits
            # was not declared or inherited HERE, which is a weaker statement
            # than "absent from the classpath", and `ModuleModel`'s own field
            # comment is where that distinction is stated for readers.
            dependency_coordinates=coordinates,
            dependency_versions=versions,
            declared_release=declared_release,
            dependencies_not_resolved=not_resolved,
            library_roots=library_roots,
            sibling_coordinates=tuple(root.coordinate for root in siblings),
            libraries_not_resolved=libraries_not_resolved,
            # The classpath the header read walks: Maven's own, where it answered; else
            # each declared dependency whose version resolved AND whose jar is in the
            # local repository. One that is not is simply absent —
            # `dependencies_not_resolved` already names the version case, and a jar Maven
            # has not fetched is a jar nothing on this machine can read.
            dependency_archives=resolved.archives
            if resolved is not None
            else tuple(
                LibraryRoot(coordinate=coordinate, version=version, archive=archive)
                for coordinate, version in sorted(versions.items())
                if version is not None
                and (archive := _local_repository_archive(coordinate, version)).is_file()
            ),
            dependency_source="declared" if resolved is None else "maven",
            dependency_source_reason=dependency_source_reason,
        )

    @staticmethod
    def _notes(path: Path) -> tuple[str, ...]:
        """Detect-time observations, sorted (RepositoryModel's own
        determinism rule) — today the one Gradle-coexistence note, since this
        detector reads nothing else worth remarking on."""
        notes = (
            [_GRADLE_COEXISTENCE_NOTE]
            if any((path / name).is_file() for name in _GRADLE_BUILD_FILES)
            else []
        )
        return tuple(sorted(notes))

    @staticmethod
    def _library_roots(
        path: Path, pom: ElementTree.Element
    ) -> tuple[tuple[LibraryRoot, ...], tuple[str, ...]]:
        """The libraries `.sextant.yml` names, resolved to the archives Maven
        itself would put on this module's compile classpath — and, for every
        coordinate that resolved to nothing, that coordinate with the REASON.

        **Two pieces of Maven convention, no invention.** The VERSION is the
        author's own, where the coordinate carries a third segment, and
        otherwise the one this module's POM declares for that dependency —
        the only place the build states which release it compiles against.
        The ARCHIVE is then the local repository's own layout,
        `~/.m2/repository/<group as directories>/<artifact>/<version>/
        <artifact>-<version>.jar`, which is where a successful build — M02's
        stated prerequisite — has already left it.

        Anything not found is REPORTED **with its reason**, never guessed at:
        no version scanned for in the repository, no nearest match, no second
        location searched. The reason is the whole value of the report — "the
        POM declares no such dependency", "its version is a property this
        detector does not interpolate" and "the archive is not in the local
        repository" are three different things to go and do, and a bare
        coordinate would leave a reader to work out which. The three
        POM-side reasons are all reachable by pinning the version in
        `.sextant.yml` instead, which is what that form is for.
        """
        declared = read_extract_libraries(path)
        if not declared:
            return (), ()
        versions = MavenDetector._dependency_versions(pom)
        roots: list[LibraryRoot] = []
        unresolved: list[str] = []
        for entry in declared:
            group, artifact, *pinned = entry.split(":")
            coordinate = f"{group}:{artifact}"
            # A pinned version wins outright and asks the POM nothing: the
            # author stated which release to read, and that statement is the
            # escape hatch for every form below the detector cannot read.
            version = pinned[0] if pinned else versions.get(coordinate)
            if version is None:
                unresolved.append(f"{coordinate}: {_no_version_reason(coordinate in versions)}")
                continue
            archive = _local_repository_archive(coordinate, version)
            if not archive.is_file():
                # The RELATIVE layout path, never the absolute one. This string
                # travels — metadata.json, the rendered gaps list, a published
                # bundle — and D00 §2's rule holds for every one of them: a path
                # under someone's home directory identifies nothing off the
                # machine that wrote it. The layout is the useful half anyway,
                # because it says where to look in whichever local repository
                # the reader has.
                unresolved.append(
                    f"{coordinate}: no {version} archive in the local repository "
                    f"(expected at {_repository_layout(coordinate, version)})"
                )
                continue
            roots.append(LibraryRoot(coordinate=coordinate, version=version, archive=archive))
        return tuple(roots), tuple(unresolved)

    @staticmethod
    def _dependency_versions(pom: ElementTree.Element) -> dict[str, str | None]:
        """Every `groupId:artifactId` this POM declares as a dependency, mapped
        to the version it states — or to `None` where that version is not one
        this detector can use.

        Present-with-`None` and absent are different answers, and the caller
        reports them differently: a dependency nobody declared is a coordinate
        that is not this module's library at all, while one declared in a form
        this detector cannot read is a library it could reach if the author
        pinned the version. Three such forms, none of them guessed at:

        * no `<version>` element — a parent POM or a BOM manages it, and THIS
          function reads the one pom;
        * a `${…}` property reference — interpolation is not done here either;
        * a `<classifier>` or a non-default `<type>` — the archive is then not
          `<artifact>-<version>.jar` at all, and composing that name anyway
          would name a file that either does not exist or is the wrong one.

        **The first two are reached by `_resolved_dependencies` and NOT by this
        function, and the split is deliberate rather than an oversight (F1).**
        This one answers a different question: which ARCHIVE to open for a
        `.sextant.yml` library opt-in, where a classifier or a non-jar type
        makes the file name wrong however well the version resolves. Routing it
        through the fuller resolution would widen library extraction on the same
        change that widened the dependency gate, with no measurement of either —
        so a library whose version only a parent manages still asks the author
        to pin it, and that shortfall is registered in `docs/open-issues.md`
        rather than closed by a change nobody sized.
        """
        versions: dict[str, str | None] = {}
        for dependency in pom.findall("m:dependencies/m:dependency", _POM_NS):
            group = dependency.find("m:groupId", _POM_NS)
            artifact = dependency.find("m:artifactId", _POM_NS)
            if group is None or artifact is None or group.text is None or artifact.text is None:
                continue
            coordinate = f"{group.text.strip()}:{artifact.text.strip()}"
            version = dependency.find("m:version", _POM_NS)
            declared = None if version is None or version.text is None else version.text.strip()
            if declared is not None and (
                "${" in declared
                or dependency.find("m:classifier", _POM_NS) is not None
                or MavenDetector._non_default_type(dependency)
            ):
                declared = None
            versions[coordinate] = declared
        return versions

    # --- F1: the RESOLVED dependency set, with versions -------------------
    #
    # **What this reads, and what it refuses to.** Maven's answer is
    # `mvn dependency:list`, and this detector must not have it: `mvn` may not
    # be installed, and running a build as a side effect of ANALYSING it is not
    # a thing an analyser may do (M02 is offline by default; the prerequisite
    # is a build that already happened). So the resolution below is done from
    # POM FILES alone — the module's own, every ancestor it can open, and every
    # BOM those import — which reaches four of the five things a POM parse used
    # to miss:
    #
    #   * a dependency INHERITED from a parent's own `<dependencies>` (the case
    #     that had `resolve/dependencies.py` skipping a Spring Cloud Stream
    #     module whose starter came from a company parent);
    #   * a version managed by a parent's `<dependencyManagement>`;
    #   * a version managed by an IMPORTED BOM (`<type>pom</type>`,
    #     `<scope>import</scope>`) — which is how `spring-boot-dependencies`
    #     answers for most of a Boot application;
    #   * a `${…}` property, interpolated against the merged `<properties>` of
    #     the whole chain plus Maven's own `project.*` built-ins.
    #
    # **The fifth is not reached and is not approximated: TRANSITIVES.** A
    # third-party artifact's own dependencies are in ITS pom in the local
    # repository, and following them means implementing Maven's mediation —
    # nearest-wins, scopes, exclusions, optionality, version ranges — which is
    # a resolver, not a parse, and a wrong one silently ADDS coordinates the
    # classpath does not have. So the set here is "declared by this module or
    # inherited by it", stated as that in `docs/COVERAGE.md`, and a reader must
    # still not read an absence as "not on the classpath".
    #
    # **Its input is the repository AND the local Maven repository.** An
    # ancestor or a BOM that is neither on disk beside the POM nor unpacked
    # under `~/.m2/repository` cannot be read, and every coordinate that leaves
    # unversioned because of it is named in `dependencies_not_resolved` rather
    # than dropped. Determinism (NFR-1) is unaffected in its own terms — same
    # inputs, same bytes — but the local repository IS one of the inputs, the
    # same way it already is for `library_roots`, and a machine that never
    # built the module resolves less. That is why the shortfall is a reported
    # list and not a silence.

    @staticmethod
    def _resolved_dependencies(
        path: Path, pom: ElementTree.Element, group: str, artifact: str, version: str
    ) -> tuple[tuple[str, ...], dict[str, str], tuple[str, ...], int | None]:
        """`(coordinates, versions, not_resolved, declared_release)` for one module.

        The release rides along rather than taking a walk of its own: it is read
        from the SAME `<properties>` merged across parent inheritance that the
        versions are, and walking the ancestor chain twice per module to answer
        two questions about one merge would be I/O for nothing.

        `coordinates` is every `groupId:artifactId` this module declares or
        inherits, sorted (NFR-1). `versions` maps the subset whose version
        this resolution could settle — sorted by key, so the mapping's own
        serialization is stable. `not_resolved` names the rest, each with why,
        plus every ancestor or BOM that could not be opened: an under-report
        this analysis can SEE is one it must state (FR-17).
        """
        properties, managed, declared, unreadable = MavenDetector._inherited_model(
            pom, path, 0, frozenset()
        )
        # Maven's own `project.*` are model values, not properties, and no
        # `<properties>` block can shadow them — so they are applied LAST.
        properties.update(
            {
                "project.groupId": group,
                "project.artifactId": artifact,
                "project.version": version,
                # The pre-3.x spellings, still written in real POMs and still
                # honoured by Maven.
                "pom.groupId": group,
                "pom.artifactId": artifact,
                "pom.version": version,
            }
        )
        versions: dict[str, str] = {}
        not_resolved = list(unreadable)
        for coordinate in sorted(declared):
            raw = declared[coordinate]
            if raw is None:
                raw = managed.get(coordinate)
            if raw is None:
                not_resolved.append(
                    f"{coordinate}: no version on the declaration and none managed by any pom "
                    f"this analysis could read"
                )
                continue
            resolved = _interpolated(raw, properties)
            if resolved is None:
                not_resolved.append(
                    f"{coordinate}: version `{raw}` names a property no pom this analysis "
                    f"could read defines"
                )
                continue
            versions[coordinate] = resolved
        return (
            tuple(sorted(declared)),
            versions,
            tuple(sorted(set(not_resolved))),
            MavenDetector._declared_release(pom, properties),
        )

    @staticmethod
    def _inherited_model(
        pom: ElementTree.Element, pom_dir: Path, depth: int, seen: frozenset[Path]
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str | None], list[str]]:
        """One POM merged with every ancestor this detector could open:
        `(properties, managed versions, declared dependencies, unreadable)`.

        NEAREST WINS on all three maps, which is Maven's own inheritance rule
        and the reason the recursion collects the ancestor first and then
        `update`s the child's own entries over it. `declared` keeps the RAW
        `<version>` text — `None` where the element is absent — because the
        managed lookup and the interpolation both happen afterwards, in the
        child's property context, and nulling a `${…}` here (which
        `_dependency_versions` does, for its own different purpose) would send
        the caller looking for a managed version that does not exist.
        """
        unreadable: list[str] = []
        properties: dict[str, str] = {}
        managed: dict[str, str] = {}
        declared: dict[str, str | None] = {}
        parent = pom.find("m:parent", _POM_NS)
        if parent is not None:
            located, ancestor, reason = MavenDetector._parent_pom(parent, pom_dir)
            if located is None or ancestor is None:
                unreadable.append(reason)
            elif depth >= _MAX_INHERITANCE_DEPTH or located in seen:
                unreadable.append(
                    f"{located.name}: inheritance stopped at depth {depth} — a chain this long "
                    f"is a cycle or a generated pom, and neither is read further"
                )
            else:
                properties, managed, declared, unreadable = MavenDetector._inherited_model(
                    ancestor, located.parent, depth + 1, seen | {located}
                )
        properties.update(MavenDetector._properties(pom))
        # Last, and after the ancestor's: `${project.version}` in an entry this pom
        # declares means THIS pom's version, never the parent's and never an importer's.
        properties.update(MavenDetector._project_properties(pom))
        own_managed, imported_unreadable = MavenDetector._managed_versions(
            pom, properties, depth, seen
        )
        unreadable.extend(imported_unreadable)
        managed.update(own_managed)
        declared.update(MavenDetector._declared_versions(pom))
        return properties, managed, declared, unreadable

    @staticmethod
    def _sibling_roots(
        path: Path,
        pom: ElementTree.Element,
        coordinates: tuple[str, ...],
        versions: dict[str, str],
    ) -> tuple[LibraryRoot, ...]:
        """The compiled output of every reactor sibling this module DEPENDS ON, and of
        every sibling those depend on in turn (F4 §5.2, W24).

        **Declared dependencies, not every module in the reactor.** The first version of
        this walked the parent's whole `<modules>` list, and it was wrong on its face:
        `mall-admin` declares `mall-mbg` and `mall-security`, so `mall-portal` and
        `mall-demo` are not on its classpath at all — yet their documents entered its
        workspace, and `mall-portal`'s `@Scheduled` cron task rendered inside
        `mall-admin`'s own document. A type can only appear in this module's signatures
        if the module compiles against it, so the dependency list IS the right set.

        **Transitive, because the compiler is.** `CommonResult` lives in `mall-common`,
        which `mall-admin` reaches through `mall-security` — the shape 160 of its 160
        endpoints return. Stopping at direct dependencies would miss the type this whole
        item exists to read. The walk keeps a visited set: a reactor is a DAG by Maven's
        own rule, and an unbounded walk here would be a hang triggered by a build file.

        Each sibling's coordinate and version come from ITS OWN POM, never from the
        directory name — a `<module>` entry is a path and Maven does not require it to
        match the artifactId. A sibling whose POM cannot be read, or which has no
        compiled output, contributes nothing rather than a guess.
        """
        by_coordinate = MavenDetector._reactor_modules(path, pom)
        if not by_coordinate:
            return ()
        found: dict[str, LibraryRoot] = {}
        seen: set[str] = set()
        frontier = [c for c in coordinates if c in by_coordinate]
        while frontier:
            coordinate = frontier.pop(0)
            if coordinate in seen:
                continue
            seen.add(coordinate)
            sibling_dir, sibling_pom = by_coordinate[coordinate]
            classes = sibling_dir / "target" / "classes"
            if classes.is_dir() and any(classes.rglob("*.class")):
                # This module's own resolved version where it declared the sibling
                # directly; otherwise the sibling's OWN POM, inherited from the parent
                # the way Maven inherits it. A transitively-reached sibling —
                # `mall-common`, through `mall-security` — appears in neither this
                # module's `<dependencies>` nor its version map, and "unversioned"
                # would then travel into every symbol that sibling declares.
                declared_version = versions.get(coordinate) or MavenDetector._text(
                    sibling_pom, "version", sibling_dir, inherited=True
                )
                found[coordinate] = LibraryRoot(
                    coordinate=coordinate,
                    version=declared_version or "unversioned",
                    archive=classes,
                )
            # Its own declared dependencies, so a sibling reached through a sibling is
            # reached at all.
            for dependency in sibling_pom.findall("m:dependencies/m:dependency", _POM_NS):
                nested = _coordinate_of(dependency)
                if nested is not None and nested in by_coordinate:
                    frontier.append(nested)
        return tuple(found[key] for key in sorted(found))

    def _ask_maven(
        self, path: Path, pom: ElementTree.Element, is_reactor: bool, allow_resolve: bool
    ) -> str | None:
        """Asks Maven for the compile classpath of every module this analysis will read,
        once (spec 2026-10-21 §3a), and returns None when each can now read its own file
        — or the REASON it cannot, which every module then carries as
        `dependency_source_reason`. Never raises: the declared set is the fallback (ruling b),
        and a failure here is a label on it, not the end of the analysis.

        Offline first. The one failure `allow_resolve` licenses an online retry for is
        Maven's own refusal to fetch (`_OFFLINE_REFUSAL_SUBSTRING`), and without the flag
        that refusal is the reason. Two preconditions are checked before any process
        starts, because asking would be pointless: `mvn` on `PATH`, and for a single module
        something BUILT under `target/classes` — a classpath is read FOR compiled classes,
        and a POM with nothing built (every temporary POM the unit suite writes) has none.
        """
        if shutil.which("mvn") is None:
            return "`mvn` is not on PATH, so the dependency set is what the POM declares"
        leaves = MavenDetector._leaf_dirs(path, pom) if is_reactor else [path]
        # **This detector never builds the analysed code.** The prerequisite is a build
        # that already happened (M02), and the `compile` phase a reactor run attaches is
        # there to let Maven see its siblings, not to produce them — so the question is
        # asked for the modules that ARE built and for no other: a reactor is told
        # `-pl <built modules>`, and a module with nothing under `target/classes` carries
        # that as its own reason (`_from_maven`). Its siblings' answers do not depend on
        # it — MEASURED in CI, where a reactor adopting a built fixture beside an unbuilt
        # one read the built fixture differently through the reactor than alone.
        built = [leaf for leaf in leaves if (leaf / "target" / "classes").is_dir()]
        if not built:
            # `leaves` is empty for a reactor the walk is about to REFUSE (a cycle, an
            # empty `<modules>`, a child with no POM): nothing to say here, the walk says it.
            where = (leaves or [path])[0] / "target" / "classes"
            return f"nothing is built under {where}, so there is no classpath to read for"
        # And a classpath is asked for only where there is one: a module declaring and
        # inheriting no dependency compiles against nothing but the platform, which no
        # file could add to — and every temporary POM the unit suite writes is that.
        if not any(MavenDetector._declares_dependencies(leaf) for leaf in built):
            return (
                "no module declares or inherits a dependency, so the compile classpath is "
                "empty and Maven was not asked"
            )
        if all(MavenDetector._classpath_is_current(leaf) for leaf in built):
            return None  # §3d: every built module's file is newer than every POM it reads
        root = MavenDetector._invocation_root(path, pom, is_reactor)
        in_reactor = root.resolve() != path.resolve() or is_reactor
        # Which modules Maven is told to build: every built leaf, unless that is the whole
        # reactor from its own root, which needs no `-pl` at all.
        selected = (
            None
            if is_reactor and len(built) == len(leaves)
            else ",".join(leaf.resolve().relative_to(root.resolve()).as_posix() for leaf in built)
        )
        options = [
            "-q",
            "-B",
            # `compile` ATTACHED only inside a reactor (spec §2, fact 2): the goal resolves a
            # sibling only as a built artifact of the same session. A single module needs
            # no phase and pays none.
            *(["compile"] if in_reactor else []),
            "dependency:build-classpath",
            f"-Dmdep.outputFile={_CLASSPATH_FILE.as_posix()}",
            "-Dmdep.includeScope=compile",
            *(["-pl", selected, "-am"] if selected is not None and in_reactor else []),
        ]
        first = MavenDetector._run_maven(root, ["mvn", "-o", *options])
        if isinstance(first, str):
            return first
        if first.returncode == 0:
            return None
        combined = first.stdout + first.stderr
        if not (allow_resolve and _OFFLINE_REFUSAL_SUBSTRING in combined):
            return MavenDetector._maven_reason(combined, first.returncode)
        second = MavenDetector._run_maven(root, ["mvn", *options])
        if isinstance(second, str):
            return second
        if second.returncode == 0:
            return None
        return MavenDetector._maven_reason(second.stdout + second.stderr, second.returncode)

    @staticmethod
    def _declares_dependencies(module_dir: Path) -> bool:
        """Whether this module's POM, or any ancestor it can open, declares a dependency —
        the same merge `_resolved_dependencies` reads, asked only for its emptiness."""
        pom = _parsed_pom(module_dir / "pom.xml")
        if pom is None:
            return False
        _properties, _managed, declared, _unreadable = MavenDetector._inherited_model(
            pom, module_dir, 0, frozenset()
        )
        return bool(declared)

    @staticmethod
    def _run_maven(root: Path, argv: list[str]) -> "subprocess.CompletedProcess[str] | str":
        """One Maven start, or the reason it could not finish."""
        try:
            return subprocess.run(
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=_MAVEN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return f"mvn did not finish within {_MAVEN_TIMEOUT_SECONDS}s: {' '.join(argv)}"
        except OSError as failed:
            return f"mvn could not be started: {failed}"

    @staticmethod
    def _maven_reason(output: str, returncode: int) -> str:
        """Maven's FIRST informative `[ERROR]` line — the one naming the artifact, plugin or
        POM it could not get — with its boilerplate skipped: the `-> [Help 1]` pointers,
        the re-run advice and the `-rf :module` resume hint all come AFTER the cause and
        were what a last-line rule recorded (measured: `mall-admin`'s reason read as a
        cwiki URL). The last line of anything when Maven printed no `[ERROR]` at all."""
        boilerplate = (
            "-> [Help",
            "[Help",
            "To see the full stack trace",
            "Re-run Maven using",
            "For more information about the errors",
            "Some problems were encountered",
            "After correcting the problems",
            "mvn <args>",
        )
        for line in output.splitlines():
            if not line.startswith("[ERROR]"):
                continue
            text = line.removeprefix("[ERROR]").strip()
            while text.startswith("[ERROR]"):
                text = text.removeprefix("[ERROR]").strip()
            if text and not text.startswith(boilerplate):
                return text
        tail = [line for line in output.splitlines() if line.strip()]
        return tail[-1].strip() if tail else f"mvn exited {returncode} and printed nothing"

    @staticmethod
    def _invocation_root(path: Path, pom: ElementTree.Element, is_reactor: bool) -> Path:
        """Where Maven is started: the reactor root when `analyze` was handed one module of
        a reactor — a module inside a reactor cannot be resolved from its own directory, its
        import-POMs being siblings that were never installed (spec §2, fact 2) — else `path`
        itself."""
        if is_reactor:
            return path
        top = MavenDetector._reactor_root(path, pom)
        if top is None:
            return path
        # `normpath`, as `_walk` spells a `<module>` path: the parent chain is built from
        # `<relativePath>`s like `../pom.xml`, and Maven is told a directory, not a route.
        root = Path(os.path.normpath(top[0].parent))
        # **The top of the `<parent>` chain is a reactor root only if it AGGREGATES this
        # module** — declares `<modules>` and contains it. The climb's own first step is
        # not checked for that (`_reactor_modules` reads nothing from a non-aggregator and
        # loses nothing), so a module whose parent is a published POM in the local
        # repository — `jhipster-sample-app` on `spring-boot-starter-parent` — arrives here
        # with `root` under `~/.m2`. MEASURED: the field pin failed on exactly that, with a
        # `relative_to` error where a single-module run was the answer.
        if top[1].find("m:modules", _POM_NS) is None or not path.resolve().is_relative_to(
            root.resolve()
        ):
            return path
        return root

    @staticmethod
    def _leaf_dirs(
        path: Path, pom: ElementTree.Element, seen: frozenset[Path] = frozenset()
    ) -> list[Path]:
        """Every module directory under `path` that is not itself an aggregator — the ones
        that will each read a classpath file. Cheap: POMs only, which `_walk` re-reads."""
        resolved = path.resolve()
        if resolved in seen:
            return []
        modules_element = pom.find("m:modules", _POM_NS)
        if modules_element is None:
            return [path]
        leaves: list[Path] = []
        for module_element in modules_element.findall("m:module", _POM_NS):
            text = (module_element.text or "").strip()
            child = Path(os.path.normpath(path / text)) if text else None
            child_pom = None if child is None else _parsed_pom(child / "pom.xml")
            if child is not None and child_pom is not None:
                leaves.extend(MavenDetector._leaf_dirs(child, child_pom, seen | {resolved}))
        return leaves

    @staticmethod
    def _classpath_is_current(module_dir: Path) -> bool:
        """Spec §3d: the file is re-used while it is newer than every POM this module's
        model is read from — its own, and each ancestor on disk up the `<parent>` chain. A
        published parent in the local repository never changes, so it is not consulted."""
        file = module_dir / _CLASSPATH_FILE
        if not file.is_file():
            return False
        written = file.stat().st_mtime
        return all(pom.stat().st_mtime <= written for pom in MavenDetector._poms_read(module_dir))

    @staticmethod
    def _poms_read(module_dir: Path) -> list[Path]:
        poms = [module_dir / "pom.xml"]
        pom = _parsed_pom(poms[0])
        here = module_dir
        repository = (Path.home() / ".m2" / "repository").resolve()
        while pom is not None and len(poms) < 32:
            parent = pom.find("m:parent", _POM_NS)
            if parent is None:
                break
            located, pom, _reason = MavenDetector._parent_pom(parent, here)
            if located is None or located.resolve().is_relative_to(repository):
                break
            poms.append(located)
            here = located.parent
        return poms

    @staticmethod
    def _from_maven(
        path: Path, classpath_reason: str | None
    ) -> "tuple[_ResolvedClasspath | None, str | None]":
        """This module's resolved classpath, or the reason it has none: the analysis-wide
        reason where Maven was not asked or did not answer, else that Maven ran and still
        wrote nothing current for THIS module (a `-pl` run that did not reach it)."""
        if classpath_reason is not None:
            return None, classpath_reason
        if not (path / "target" / "classes").is_dir():
            return None, (
                f"nothing is built under {path / 'target' / 'classes'}, so there is no "
                "classpath to read for"
            )
        if not MavenDetector._classpath_is_current(path):
            return None, (
                f"Maven wrote no current {_CLASSPATH_FILE.as_posix()} for this module, so the "
                "dependency set is what the POM declares"
            )
        return MavenDetector._classpath_entries(path / _CLASSPATH_FILE), None

    @staticmethod
    def _classpath_entries(file: Path) -> _ResolvedClasspath:
        """The file `dependency:build-classpath` wrote, read — never interpreted. A jar under
        the local repository names its coordinate and version by the layout
        `_repository_layout` spells (`<group dirs>/<artifact>/<version>/<file>`); a directory
        is a reactor sibling's output, named by ITS OWN POM; anything else is reported by
        its path with the reason, the way Gradle's path-only entries are."""
        repository = (Path.home() / ".m2" / "repository").resolve()
        archives: list[LibraryRoot] = []
        versions: dict[str, str] = {}
        siblings: dict[str, LibraryRoot] = {}
        unresolvable: list[str] = []
        for raw in file.read_text(encoding="utf-8").strip().split(os.pathsep):
            entry = Path(raw.strip())
            if not raw.strip():
                continue
            if entry.is_dir():
                sibling = MavenDetector._sibling_root_of(entry)
                if sibling is not None:
                    siblings.setdefault(sibling.coordinate, sibling)
                else:
                    unresolvable.append(
                        f"{entry}: a directory on the compile classpath that is not a reactor "
                        "module's own target/classes, so it has no coordinate this analysis "
                        "can name"
                    )
                continue
            try:
                relative = entry.resolve().relative_to(repository)
            except ValueError:
                unresolvable.append(
                    f"{entry}: on the compile classpath but outside the local repository, so "
                    "it has no coordinate this analysis can name"
                )
                continue
            if len(relative.parts) < 4 or entry.suffix != ".jar" or not entry.is_file():
                unresolvable.append(f"{entry}: not a jar in the local repository's layout")
                continue
            *group, artifact, version, _name = relative.parts
            coordinate = f"{'.'.join(group)}:{artifact}"
            archives.append(LibraryRoot(coordinate=coordinate, version=version, archive=entry))
            versions.setdefault(coordinate, version)
        return _ResolvedClasspath(
            archives=tuple(archives),
            versions=versions,
            siblings=tuple(siblings[key] for key in sorted(siblings)),
            unresolvable=tuple(unresolvable),
        )

    @staticmethod
    def _sibling_root_of(classes: Path) -> LibraryRoot | None:
        """A `<module>/target/classes` directory as the library root `_sibling_roots` would
        have made of it: coordinate and version from the module's own POM, never from the
        directory name. None where the directory is not that shape or holds no class."""
        if classes.name != "classes" or classes.parent.name != "target":
            return None
        module_dir = classes.parent.parent
        pom = _parsed_pom(module_dir / "pom.xml")
        if pom is None or not any(classes.rglob("*.class")):
            return None
        coordinate = _coordinates_of(pom)
        if coordinate is None:
            return None
        version = MavenDetector._text(pom, "version", module_dir, inherited=True)
        return LibraryRoot(coordinate=coordinate, version=version or "unversioned", archive=classes)

    @staticmethod
    def _reactor_root(
        path: Path, pom: ElementTree.Element
    ) -> tuple[Path, ElementTree.Element] | None:
        """The POM at the TOP of this module's reactor, with its path — or None where this
        module has no aggregating parent on disk. Pulled out of `_reactor_modules` so the
        Maven invocation (spec 2026-10-21 §3a) starts from the same root the sibling walk
        does, under the same containment rule."""
        parent = pom.find("m:parent", _POM_NS)
        if parent is None:
            return None
        parent_path, parent_pom, _reason = MavenDetector._parent_pom(parent, path)
        if parent_path is None or parent_pom is None:
            return None
        # **AND THE WALK STARTS AT THE TOP OF THE REACTOR, not at this module's parent**
        # (`OI-149`, the other half). A reactor is the whole tree from its root by Maven's
        # own definition, and a dependency can be up AND across:
        # `ruoyi-vue-pro`'s `yudao-module-mall/yudao-module-promotion` depends on
        # `yudao-module-system`, a ROOT-level module, and its neighbour
        # `yudao-module-product` on `yudao-framework/yudao-spring-boot-starter-web`, which
        # is in a different subtree. Descending from `yudao-module-mall` reaches neither.
        #
        # **An ancestor replaces this one only if it AGGREGATES THIS MODULE** — it declares
        # `<modules>`, and its directory contains the module being analysed. Both halves
        # are load-bearing, and the second was learned by breaking a pinned corpus:
        # `macrozheng/mall`'s root pom inherits from `spring-boot-starter-parent`, which
        # `_parent_pom` resolves out of the local repository, so an unconditional climb
        # left `parent_path` inside `~/.m2` and DISCARDED the real reactor root.
        # `mall-admin` went from 629 shape fields to 73 — the field pin caught it.
        #
        # Containment is the reactor's own property rather than a heuristic: an aggregator
        # reaches its modules by relative `<module>` paths, so one that does not contain
        # this module cannot be the tree this module belongs to. It also ends the climb at
        # the project boundary without having to reason about where a pom was read from.
        climbed: set[Path] = {parent_path.resolve()}
        module_dir = path.resolve()
        while (grandparent := parent_pom.find("m:parent", _POM_NS)) is not None:
            up_path, up_pom, _reason = MavenDetector._parent_pom(grandparent, parent_path.parent)
            if up_path is None or up_pom is None or up_path.resolve() in climbed:
                break
            if up_pom.find("m:modules", _POM_NS) is None or not module_dir.is_relative_to(
                up_path.parent.resolve()
            ):
                break
            parent_path, parent_pom = up_path, up_pom
            climbed.add(up_path.resolve())
        return parent_path, parent_pom

    @staticmethod
    def _reactor_modules(
        path: Path, pom: ElementTree.Element
    ) -> dict[str, tuple[Path, ElementTree.Element]]:
        """Every module of this module's reactor, by coordinate, with its directory and
        its own parsed POM — including the children of a `<module>` that is itself an
        aggregator, which is the whole of `OI-149`.

        Reached through `<parent>` because `analyze` runs against ONE module's path: the
        detector's own `<modules>` walk descends from an aggregator and so never sees
        the siblings of the module being analysed. `_parent_pom` applies Maven's own
        check that the POM at `<relativePath>` really declares the coordinates the
        `<parent>` names, so an unrelated aggregator sitting at that path is refused
        rather than read.
        """
        top = MavenDetector._reactor_root(path, pom)
        if top is None:
            return {}
        parent_path, parent_pom = top

        found: dict[str, tuple[Path, ElementTree.Element]] = {}
        # **A `<module>` may itself be an aggregator, and its children are reactor
        # modules too** (`OI-149`). Resolving one level and stopping is what made a
        # shared type invisible: `YunaiV/ruoyi-vue-pro` puts the envelope every
        # controller returns in `yudao-framework/yudao-common`, and the root names only
        # `yudao-framework` — `<packaging>pom</packaging>`, no `target/classes`, nothing
        # to read. Measured there: 85 open shapes in one module and 45 in another, which
        # is the response contract of all 323 of their endpoints. `macrozheng/mall-swarm`
        # resolves the same envelope correctly for one reason only — its reactor is FLAT.
        #
        # **This widens the CANDIDATES and not the result.** `_sibling_roots` still walks
        # this module's declared dependencies, transitively, and reads nothing else; a
        # module in the reactor that nothing here compiles against stays out, which is the
        # refusal that docstring was written for after `mall-portal`'s cron task rendered
        # inside `mall-admin`'s document.
        #
        # Breadth-first from the parent, with each aggregator's own directory as the base
        # its `<module>` paths resolve against — Maven's own rule, and the reason the base
        # travels on the frontier rather than being computed from `parent_path`.
        frontier: list[tuple[Path, ElementTree.Element]] = [(parent_path.parent, parent_pom)]
        # Keyed on the DIRECTORY, because that is what a `<module>` names and what a cycle
        # would repeat. A reactor is a DAG by Maven's own rule, so this bounds a walk that
        # a hand-written build file could otherwise make unbounded — the same guard, and
        # the same reason, as `_sibling_roots`' own visited set.
        seen: set[Path] = {parent_path.parent.resolve()}
        while frontier:
            base, aggregator = frontier.pop(0)
            modules = aggregator.find("m:modules", _POM_NS)
            if modules is None:
                continue
            for module in modules.findall("m:module", _POM_NS):
                name = (module.text or "").strip()
                if not name:
                    continue
                sibling = (base / name).resolve()
                if sibling == path.resolve() or sibling in seen:
                    continue
                seen.add(sibling)
                sibling_pom = _parsed_pom(sibling / "pom.xml")
                if sibling_pom is None:
                    continue
                # Descend whatever it turns out to be. An aggregator is not asked for by
                # `<packaging>`: a pom carrying `<modules>` aggregates, and one carrying
                # none contributes nothing to the frontier anyway, so reading the element
                # that decides it is simpler than reading a declaration ABOUT it — and it
                # cannot disagree with itself the way the pair could.
                frontier.append((sibling, sibling_pom))
                # The sibling's OWN coordinates, inherited from its parent the way Maven
                # inherits them — never the directory name.
                group = MavenDetector._text(sibling_pom, "groupId", sibling, inherited=True)
                artifact = MavenDetector._text(sibling_pom, "artifactId", sibling)
                if group is None or artifact is None:
                    continue
                found[f"{group}:{artifact}"] = (sibling, sibling_pom)
        return found

    @staticmethod
    def _parent_pom(
        parent: ElementTree.Element, pom_dir: Path
    ) -> tuple[Path | None, ElementTree.Element | None, str]:
        """The `<parent>` this POM names, as a file this detector opened.

        Maven's own order, and its own check: `<relativePath>` (defaulting to
        `../pom.xml`, and empty meaning "do not look on disk") is tried first
        and is ACCEPTED ONLY IF the pom there declares the coordinates the
        `<parent>` element names — an aggregator that is not this module's
        parent sits at exactly that path in plenty of real layouts, and reading
        its properties as inherited would be a fabrication. Otherwise the
        published pom in the local repository, which is where a parent from
        outside the repository lives once anything has built.
        """
        group = _text_of(parent, "groupId")
        artifact = _text_of(parent, "artifactId")
        version = _text_of(parent, "version")
        if group is None or artifact is None or version is None:
            return None, None, "a <parent> naming no groupId/artifactId/version cannot be read"
        coordinate = f"{group}:{artifact}"
        relative = parent.find("m:relativePath", _POM_NS)
        spelled = "../pom.xml" if relative is None else (relative.text or "").strip()
        if spelled:
            candidate = pom_dir / spelled
            if candidate.is_dir():
                candidate = candidate / "pom.xml"
            found = _parsed_pom(candidate)
            if found is not None and _coordinates_of(found) == coordinate:
                return candidate, found, ""
        published = _local_repository_pom(coordinate, version)
        found = _parsed_pom(published)
        if found is not None:
            return published, found, ""
        published_at = _repository_layout(coordinate, version)[: -len(".jar")]
        reason = (
            f"{coordinate}:{version}: no parent pom on disk at `{spelled or '(none declared)'}` "
            f"and none in the local repository (expected at {published_at}.pom)"
        )
        return None, None, reason

    @staticmethod
    def _managed_versions(
        pom: ElementTree.Element, properties: dict[str, str], depth: int, seen: frozenset[Path]
    ) -> tuple[dict[str, str], list[str]]:
        """This POM's own `<dependencyManagement>`, with every BOM it imports
        already folded in underneath it.

        Maven's precedence, kept: an entry written here beats one an imported
        BOM manages, and among imports the FIRST declared wins — so the
        imported map is built first and the POM's own entries `update` over it.
        A BOM is read through the same inheritance walk a parent is, because a
        BOM's own versions are routinely properties defined in ITS parent.
        """
        unreadable: list[str] = []
        own: dict[str, str] = {}
        imported: dict[str, str] = {}
        for dependency in pom.findall(
            "m:dependencyManagement/m:dependencies/m:dependency", _POM_NS
        ):
            coordinate = _coordinate_of(dependency)
            raw = _text_of(dependency, "version")
            if coordinate is None or raw is None:
                continue
            scope = _text_of(dependency, "scope")
            kind = _text_of(dependency, "type")
            if scope != _IMPORT_SCOPE or kind != "pom":
                own[coordinate] = raw
                continue
            version = _interpolated(raw, properties)
            if version is None:
                unreadable.append(
                    f"{coordinate}: imported BOM version `{raw}` names a property no pom this "
                    f"analysis could read defines"
                )
                continue
            located = _local_repository_pom(coordinate, version)
            bom = _parsed_pom(located)
            if bom is None or depth >= _MAX_INHERITANCE_DEPTH or located in seen:
                unreadable.append(
                    f"{coordinate}:{version}: imported BOM not in the local repository "
                    f"(expected at {_repository_layout(coordinate, version)[: -len('.jar')]}.pom)"
                )
                continue
            bom_properties, bom_managed, _, up = MavenDetector._inherited_model(
                bom, located.parent, depth + 1, seen | {located}
            )
            unreadable.extend(up)
            for managed_coordinate, managed_raw in bom_managed.items():
                # Resolved in the BOM's OWN property context, here, rather than
                # carried raw: `${spring-framework.version}` means whatever the
                # BOM's chain says it means, and the importing module's
                # properties are a different namespace that must not answer it.
                settled = _interpolated(managed_raw, bom_properties)
                if settled is not None:
                    imported.setdefault(managed_coordinate, settled)
                else:
                    # REPORTED, never dropped. This branch did not exist, so an entry whose
                    # version named nothing readable vanished from the map AND from the
                    # reasons — and a module then reported a dependency unresolved for a
                    # cause nothing in `metadata.json` could explain. Four wrong theories
                    # about `OI-139` survived on that silence.
                    unreadable.append(
                        f"{managed_coordinate}: managed by {coordinate}:{version} at version "
                        f"`{managed_raw}`, which names a property no pom this analysis "
                        f"could read defines"
                    )
        imported.update(own)
        return imported, unreadable

    @staticmethod
    def _declared_release(pom: ElementTree.Element, properties: dict[str, str]) -> int | None:
        """The compiler target release this module's BUILD declares, or `None`.

        §8.2 admits it: a value written in the pom is code, not a deployment
        possibility. It is the primary source for multi-release SELECTION —
        which overlay of a class actually loads is a property of the module
        doing the depending, and this is where that module says so.

        **Order, and it is Maven's own rather than the spec's listing order.**
        maven-compiler-plugin's `<configuration><release>` is read FIRST because
        `maven.compiler.release` is merely the default EXPRESSION for that
        parameter, so an explicit configuration overrides the property. Then the
        properties in decreasing specificity: `release`, `target`, `source`, and
        finally the version property the Spring Boot parent sets and nothing else.

        `1.8` and `8` both mean 8 — the legacy `1.x` spelling is still what
        `<source>`/`<target>` carry in older builds, and reading only one of the
        two would silently miss half the estate. A value that is neither is
        ignored rather than guessed at: a `${property}` nothing defines, or a
        toolchain expression, is not a release this detector can honestly claim.
        """
        # `build/plugins` ONLY — not `.//plugin`, which also matches
        # `build/pluginManagement/plugins`, `reporting/plugins` and every
        # `profile`. Measured: with pluginManagement pinning 11 and
        # build/plugins overriding to 21, a document-order search answers 11
        # where Maven uses 21. pluginManagement declares a DEFAULT for plugins
        # a module chooses to use; it is not itself a use. And a profile is a
        # §8.2 possibility — active in some invocations, not others — so
        # reading one as though it were the declared release states a value
        # this analysis cannot know applies.
        for element in pom.iterfind("m:build/m:plugins/m:plugin", _POM_NS):
            artifact = element.find("m:artifactId", _POM_NS)
            if artifact is None or (artifact.text or "").strip() != "maven-compiler-plugin":
                continue
            release = element.find("m:configuration/m:release", _POM_NS)
            if release is not None:
                parsed = MavenDetector._release_number(
                    _interpolated((release.text or "").strip(), properties)
                )
                if parsed is not None:
                    return parsed
        for key in (
            "maven.compiler.release",
            "maven.compiler.target",
            "maven.compiler.source",
            "java.version",
        ):
            if key in properties:
                parsed = MavenDetector._release_number(_interpolated(properties[key], properties))
                if parsed is not None:
                    return parsed
        return None

    @staticmethod
    def _release_number(declared: str | None) -> int | None:
        """`17` and `1.8` both parse; anything else is None rather than a guess."""
        if not declared:
            return None
        text = declared.strip()
        if text.startswith("1.") and text[2:].isascii() and text[2:].isdigit():
            text = text[2:]
        # `isascii()` as well as `isdigit()`: the latter is TRUE for superscript
        # `²` (which `int()` then refuses, crashing the detector) and for
        # Arabic-Indic digits (which `int()` silently accepts as a release
        # nobody wrote). Measured both.
        if not (text.isascii() and text.isdigit()):
            return None
        release = int(text)
        # A release below 1 is not a release, and the upper bound is what keeps
        # an unbounded value out of a `::BIGINT` cast downstream — measured:
        # `str.isdigit()` accepted a 21-digit number that reached it.
        return release if 1 <= release <= 1000 else None

    @staticmethod
    def _project_properties(pom: ElementTree.Element) -> dict[str, str]:
        """Maven's built-in `project.*` properties for THIS pom.

        They are not `<properties>` entries and no pom declares them, so a reader that
        interpolates only from `<properties>` resolves nothing for them — and
        `${project.version}` is how a Spring Cloud component BOM versions its own
        artifacts: 6 of 8 managed entries in `spring-cloud-gateway-dependencies:5.0.0`,
        and every one of the four starters `spring-petclinic-api-gateway` declares
        (`scripts/probes/cp35_bom_chain.md`). Before this existed those entries were
        dropped, so a gateway's whole route table derived nothing (`OI-139`).

        **Scoped to this pom, which is the whole point.** `_inherited_model` calls this
        once per pom it opens, so an imported BOM's entries are settled against the BOM's
        own version rather than the importing module's. Answering them from the module
        would write a coordinate that does not exist into the version map — a silent wrong
        answer where there is otherwise an honest `dependencies_not_resolved` entry.

        `groupId` and `version` fall back to `<parent>`'s, which is Maven's rule for a pom
        that omits them. The three spelled here are the ones a version string uses;
        `project.name` and the rest are not version material and are left out rather than
        half-supported.
        """
        parent = pom.find("m:parent", _POM_NS)
        group = _text_of(pom, "groupId")
        version = _text_of(pom, "version")
        if parent is not None:
            group = group or _text_of(parent, "groupId")
            version = version or _text_of(parent, "version")
        artifact = _text_of(pom, "artifactId")
        return {
            f"project.{name}": value
            for name, value in (
                ("groupId", group),
                ("artifactId", artifact),
                ("version", version),
            )
            if value is not None
        }

    @staticmethod
    def _properties(pom: ElementTree.Element) -> dict[str, str]:
        """This POM's own `<properties>`, by their bare names."""
        block = pom.find("m:properties", _POM_NS)
        if block is None:
            return {}
        return {
            child.tag.removeprefix(f"{{{_POM_NS['m']}}}"): (child.text or "").strip()
            for child in block
            if isinstance(child.tag, str)
        }

    @staticmethod
    def _declared_versions(pom: ElementTree.Element) -> dict[str, str | None]:
        """Every dependency this POM declares, mapped to its RAW `<version>`
        text — `None` where the element is absent, which is the shape that
        sends the caller to the managed versions.

        Scope is deliberately not read, and the cost is stated: a `test`-scoped
        dependency is in this set, so the Maven side over-states the COMPILE
        classpath where the Gradle side reports exactly it. It matched what a
        POM parse recorded before F1 and narrowing it is a separate decision
        with its own evidence, not a detail to slip into a widening.
        """
        return {
            coordinate: _text_of(dependency, "version")
            for dependency in pom.findall("m:dependencies/m:dependency", _POM_NS)
            if (coordinate := _coordinate_of(dependency)) is not None
        }

    @staticmethod
    def _non_default_type(dependency: ElementTree.Element) -> bool:
        """A `<type>` other than Maven's own default. `jar` spelled out is the
        default written down, not a different artifact, so it must not read as
        one."""
        declared = dependency.find("m:type", _POM_NS)
        return declared is not None and (declared.text or "").strip() not in ("", "jar")

    @staticmethod
    def _source_roots(path: Path, pom: ElementTree.Element) -> tuple[Path, ...]:
        """The directories this build compiles from, as they actually exist.

        A declared `<sourceDirectory>` wins, because it is the build saying
        so. Otherwise every directory under `src/main` that is not one of
        Maven's own non-code directories is a source root, and each one's
        name is the language compiled there — which is how a module holding
        a second JVM language is reported as holding it, without any language
        name appearing in this file to say so.

        Returns an empty tuple where the module has no source directory at
        all. A root that does not exist is never returned: a path nothing
        can read is worse than an absence, because everything downstream
        treats it as a place it already looked.
        """
        declared = pom.find("m:build/m:sourceDirectory", _POM_NS)
        if declared is not None and declared.text:
            root = path / declared.text.strip()
            return (root,) if root.is_dir() else ()
        main = path / "src" / "main"
        if not main.is_dir():
            return ()
        return tuple(
            sorted(
                (
                    child
                    for child in main.iterdir()
                    if child.is_dir()
                    and child.name not in _NON_SOURCE_DIRECTORIES
                    and child.name not in _SCHEMA_DIRECTORIES
                ),
                key=lambda child: child.name,
            )
        )

    @staticmethod
    def _classify(path: Path, pom: ElementTree.Element) -> str:
        """Service, library, or undetermined, from evidence (M02): a boot
        plugin applied, a declared main class, a container file, or inbound
        endpoints make it a service; publishing an artifact with none of
        those makes it a library; absent evidence, `undetermined` — never a
        guess.

        Two of those are cheap and framework-neutral, and are read here: a
        container file beside the POM, and a `<mainClass>` anywhere in the
        build. The rest are not. A boot plugin is a framework name, which
        belongs in a catalog and not in this module; inbound endpoints are
        not known until after M04, which M02 records as an open decision.

        `library` is never returned. It requires knowing that the module
        publishes an artifact, and every POM declares coordinates whether
        anything is published or not — reading that as evidence would be the
        guess this method exists to refuse.
        """
        if any((path / name).is_file() for name in CONTAINER_FILES):
            return "service"
        if any(node.tag == _MAIN_CLASS for node in pom.iter()):
            return "service"
        return "undetermined"

    @staticmethod
    def _packaging(pom: ElementTree.Element) -> str:
        """Maven's own `<packaging>`, defaulting to `jar` — Maven's own
        default when the element is absent or empty, not a guess this
        detector invents (2M design §2, ruled amendment). Read for a LEAF
        module only: an aggregation-only POM's own `<packaging>pom</packaging>`
        never reaches here, since it never becomes a `ModuleModel`."""
        node = pom.find("m:packaging", _POM_NS)
        return node.text.strip() if node is not None and node.text else "jar"

    @staticmethod
    def _text(pom: ElementTree.Element, tag: str, path: Path, inherited: bool = False) -> str:
        # Named by its pom (2M final review wave, MINOR 3): "pom.xml has no
        # <groupId>" points nowhere in a many-pom reactor — the reader needs
        # to know WHICH pom.xml.
        node = pom.find(f"m:{tag}", _POM_NS)
        if node is None and inherited:
            node = pom.find(f"m:parent/m:{tag}", _POM_NS)
        if node is None or node.text is None:
            raise ValueError(f"{path / 'pom.xml'} has no <{tag}>")
        return node.text.strip()
