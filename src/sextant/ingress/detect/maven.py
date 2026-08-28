from pathlib import Path
from xml.etree import ElementTree

from sextant.application.ports.detector import ModuleModel, RepositoryModel

_POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


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
        module = ModuleModel(
            module_id=f"{group}:{artifact}",
            coordinates=f"{group}/{artifact}",
            version=version,
            root=path,
            kind=self._classify(),
            languages=frozenset({"java"}),
            source_roots=(path / "src" / "main" / "java",),
            output_dirs=(path / "target" / "classes",),
        )
        return RepositoryModel(root=path, modules=(module,))

    @staticmethod
    def _classify() -> str:
        """Service, library, or undetermined, from evidence (M02): a boot
        plugin applied, a declared main class, a container file, or inbound
        endpoints make it a service; publishing an artifact with none of
        those makes it a library; absent evidence, `undetermined` — never a
        guess. Phase 1's only fixture is a service and none of that evidence
        is read yet, so this seam returns the fixed answer until a later
        phase supplies the evidence."""
        return "service"

    @staticmethod
    def _text(pom: ElementTree.Element, tag: str) -> str:
        node = pom.find(f"m:{tag}", _POM_NS)
        if node is None or node.text is None:
            raise ValueError(f"pom.xml has no <{tag}>")
        return node.text.strip()
