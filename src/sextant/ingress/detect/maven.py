import os
from pathlib import Path
from xml.etree import ElementTree

from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.ingress.detect.sextant_config import read_extract_libraries

_POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}
_MAIN_CLASS = f"{{{_POM_NS['m']}}}mainClass"

# Files that declare how the module is packaged to run. Names, not contents:
# M02 forbids the detector from reading code, and these are build files.
# Maven's own non-code build directories. Named here because they are build
# layout, not languages: everything else under src/main is a source root, and
# the name of that directory is what the build says is compiled there.
_NON_SOURCE_DIRECTORIES = frozenset({"resources", "webapp", "filters"})

# Schema-source directory names (protobuf-maven-plugin / avro-maven-plugin
# convention): schema dirs are not languages, so this detector must not
# report one from them. Ordered, unlike a set, because `schema_roots` reports
# them in this fixed order (protobuf before Avro) rather than whatever order
# a directory listing would give.
_SCHEMA_ROOT_NAMES = ("proto", "avro")
_SCHEMA_DIRECTORIES = frozenset(_SCHEMA_ROOT_NAMES)

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
    *((name,) for name in _SCHEMA_ROOT_NAMES),
    ("resources", "graphql"),
    ("resources", "wsdl"),
    ("resources", "xsd"),
    ("resources", "META-INF", "wsdl"),
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


_CONTAINER_FILES = (
    "Dockerfile",
    "Containerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)

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
        top_pom = ElementTree.parse(path / "pom.xml").getroot()
        is_reactor = top_pom.find("m:modules", _POM_NS) is not None
        modules = self._walk(path, visited=(), seen=set())
        return RepositoryModel(
            root=path, modules=modules, notes=self._notes(path), multi_module=is_reactor
        )

    def _walk(
        self, path: Path, visited: tuple[Path, ...], seen: set[Path]
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
        pom = ElementTree.parse(path / "pom.xml").getroot()
        modules_element = pom.find("m:modules", _POM_NS)
        if modules_element is None:
            if resolved in seen:
                return ()
            seen.add(resolved)
            return (self._module_of(path, pom),)
        children: list[ModuleModel] = []
        for module_element in modules_element.findall("m:module", _POM_NS):
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
            children.extend(self._walk(child, (*visited, resolved), seen))
        return tuple(children)

    @staticmethod
    def _module_of(path: Path, pom: ElementTree.Element) -> ModuleModel:
        # A reactor child inherits groupId and version from <parent> and may
        # omit its own elements entirely (Maven's inheritance rule) —
        # artifactId alone is never inherited. Reading the parent's value is
        # Maven convention data, not a guess.
        group = MavenDetector._text(pom, "groupId", inherited=True)
        artifact = MavenDetector._text(pom, "artifactId")
        version = MavenDetector._text(pom, "version", inherited=True)
        source_roots = MavenDetector._source_roots(path, pom)
        resources = path / "src" / "main" / "resources"
        library_roots, libraries_not_resolved = MavenDetector._library_roots(path, pom)
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
            library_roots=library_roots,
            libraries_not_resolved=libraries_not_resolved,
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

        * no `<version>` element — a parent POM or a BOM manages it, and the
          detector reads `pom.xml` directly rather than asking Maven to resolve
          it (the standing `maven_parent_and_profile_resolution_not_implemented`
          gap);
        * a `${…}` property reference — interpolation is the same gap;
        * a `<classifier>` or a non-default `<type>` — the archive is then not
          `<artifact>-<version>.jar` at all, and composing that name anyway
          would name a file that either does not exist or is the wrong one.
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
        if any((path / name).is_file() for name in _CONTAINER_FILES):
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
    def _text(pom: ElementTree.Element, tag: str, inherited: bool = False) -> str:
        node = pom.find(f"m:{tag}", _POM_NS)
        if node is None and inherited:
            node = pom.find(f"m:parent/m:{tag}", _POM_NS)
        if node is None or node.text is None:
            raise ValueError(f"pom.xml has no <{tag}>")
        return node.text.strip()
