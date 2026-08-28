from pathlib import Path
from xml.etree import ElementTree

from sextant.application.ports.detector import ModuleModel, RepositoryModel

_POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}
_MAIN_CLASS = f"{{{_POM_NS['m']}}}mainClass"

# Files that declare how the module is packaged to run. Names, not contents:
# M02 forbids the detector from reading code, and these are build files.
# Maven's own non-code build directories. Named here because they are build
# layout, not languages: everything else under src/main is a source root, and
# the name of that directory is what the build says is compiled there.
_NON_SOURCE_DIRECTORIES = frozenset({"resources", "webapp", "filters"})

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
        group = self._text(pom, "groupId")
        artifact = self._text(pom, "artifactId")
        version = self._text(pom, "version")
        source_roots = self._source_roots(path, pom)
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
        )
        return RepositoryModel(root=path, modules=(module,))

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
                    if child.is_dir() and child.name not in _NON_SOURCE_DIRECTORIES
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
    def _text(pom: ElementTree.Element, tag: str) -> str:
        node = pom.find(f"m:{tag}", _POM_NS)
        if node is None or node.text is None:
            raise ValueError(f"pom.xml has no <{tag}>")
        return node.text.strip()
