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


def _local_repository_archive(coordinate: str, version: str) -> Path:
    """Maven's own local-repository layout for one coordinate — resolved at
    call time rather than at import, so a test or a caller that moves `HOME`
    is not answered from whatever it was when this module loaded."""
    group, _, artifact = coordinate.partition(":")
    return (
        Path.home()
        / ".m2"
        / "repository"
        / Path(*group.split("."))
        / artifact
        / version
        / f"{artifact}-{version}.jar"
    )


_CONTAINER_FILES = (
    "Dockerfile",
    "Containerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)


class MavenDetector:
    """Reads the build, never a convention. Offline by default (M02): the
    prerequisite is a successful build, so the local cache already has the
    classpath.

    Phase 1 detects a single module by reading its POM directly. Multi-module
    discovery (walking <modules>) and classpath resolution via `mvn -o` land
    when a fixture needs them; any future `mvn` invocation this detector
    makes must pass `-o` unless `allow_resolve` is set.
    """

    def accepts(self, path: Path) -> bool:
        return (path / "pom.xml").is_file()

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        pom = ElementTree.parse(path / "pom.xml").getroot()
        # A reactor child inherits groupId and version from <parent> and may
        # omit its own elements entirely (Maven's inheritance rule) —
        # artifactId alone is never inherited. Reading the parent's value is
        # Maven convention data, not a guess.
        group = self._text(pom, "groupId", inherited=True)
        artifact = self._text(pom, "artifactId")
        version = self._text(pom, "version", inherited=True)
        source_roots = self._source_roots(path, pom)
        resources = path / "src" / "main" / "resources"
        library_roots, libraries_not_resolved = self._library_roots(path, pom)
        module = ModuleModel(
            module_id=f"{group}:{artifact}",
            coordinates=f"{group}/{artifact}",
            version=version,
            root=path,
            kind=self._classify(path, pom),
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
        return RepositoryModel(root=path, modules=(module,))

    @staticmethod
    def _library_roots(
        path: Path, pom: ElementTree.Element
    ) -> tuple[tuple[LibraryRoot, ...], tuple[str, ...]]:
        """The libraries `.sextant.yml` names, resolved to the archives Maven
        itself would put on this module's compile classpath — and the
        coordinates that resolved to nothing.

        **Two pieces of Maven convention, no invention.** The VERSION comes
        from the module's own declared dependency on that coordinate, because
        that is the only place the build states which release it compiles
        against; a coordinate the POM never declares is not this module's
        library at all, and one whose version a parent or BOM manages is not
        readable here (the detector reads `pom.xml` directly rather than asking
        Maven to resolve it — the standing `maven_parent_and_profile_resolution
        _not_implemented` gap). The ARCHIVE is then the local repository's own
        layout, `~/.m2/repository/<group as directories>/<artifact>/<version>/
        <artifact>-<version>.jar`, which is where a successful build — M02's
        stated prerequisite — has already left it.

        Anything not found is REPORTED, never guessed at: no version scanned
        for in the repository, no nearest match, no second location searched. A
        local repository relocated by `settings.xml` is therefore a coordinate
        that does not resolve, which is an answer a reader can act on, rather
        than a wrong jar that nothing downstream could tell from a right one.
        """
        declared = read_extract_libraries(path)
        if not declared:
            return (), ()
        versions = MavenDetector._dependency_versions(pom)
        roots: list[LibraryRoot] = []
        unresolved: list[str] = []
        for coordinate in declared:
            version = versions.get(coordinate)
            archive = None if version is None else _local_repository_archive(coordinate, version)
            if version is None or archive is None or not archive.is_file():
                unresolved.append(coordinate)
                continue
            roots.append(LibraryRoot(coordinate=coordinate, version=version, archive=archive))
        return tuple(roots), tuple(unresolved)

    @staticmethod
    def _dependency_versions(pom: ElementTree.Element) -> dict[str, str]:
        """Every `groupId:artifactId` this POM declares a version for, mapped
        to it. A dependency whose version is managed elsewhere carries no
        `<version>` element and is simply absent here — the same "no path is
        better than a wrong one" discipline `_source_roots` keeps."""
        versions: dict[str, str] = {}
        for dependency in pom.findall("m:dependencies/m:dependency", _POM_NS):
            group = dependency.find("m:groupId", _POM_NS)
            artifact = dependency.find("m:artifactId", _POM_NS)
            version = dependency.find("m:version", _POM_NS)
            if group is None or artifact is None or version is None:
                continue
            if group.text is None or artifact.text is None or version.text is None:
                continue
            versions[f"{group.text.strip()}:{artifact.text.strip()}"] = version.text.strip()
        return versions

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
    def _text(pom: ElementTree.Element, tag: str, inherited: bool = False) -> str:
        node = pom.find(f"m:{tag}", _POM_NS)
        if node is None and inherited:
            node = pom.find(f"m:parent/m:{tag}", _POM_NS)
        if node is None or node.text is None:
            raise ValueError(f"pom.xml has no <{tag}>")
        return node.text.strip()
