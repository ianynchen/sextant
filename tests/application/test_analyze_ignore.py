"""2K Task 2: `.sextantignore` wired into `analyze`'s own walk sites. Both
the config-read loop and the schema-read loop funnel through
`domain/resource_files.list_files`, and this is where that wiring is proven
end to end: a file `.sextantignore` names contributes NOTHING to the fact
tree — no `config_entry`, no `embedded_descriptor` — because it is never
handed to a reader at all, not merely read and then discarded."""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.domain.factfile import read_fact_tree
from sextant.ingress.read.wsdl_xsd import WsdlXsdReader
from sextant.ingress.read.yaml_config import YamlConfigReader
from sextant.storage.duckdb.workspace import DuckDbWorkspace


class _FakeDetector:
    """The same hand-built-module idiom `test_analyze_descriptor_wiring.py`
    already uses — this test has no business reading a real `pom.xml`."""

    def __init__(self, module: ModuleModel) -> None:
        self._module = module

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=path, modules=(self._module,))


class _NoOpScanner:
    """Writes nothing — this suite exercises only the read step, never the
    bytecode scan."""

    def accepts(self, languages: set[str]) -> bool:
        return True

    def capabilities(self) -> set[str]:
        return set()

    def rank(self) -> int:
        return 1

    def scan(self, request: ScanRequest) -> ScanReport:
        return ScanReport(documents=0, facts=0, scanner_id="noop", scanner_version="1.0")


class _EmptyCatalogs:
    def load(self) -> list[Catalog]:
        return []


def _module(root: Path, resource_root: Path, schema_root: Path) -> ModuleModel:
    return ModuleModel(
        module_id="com.acme:widgets",
        coordinates="com.acme/widgets",
        version="1.0.0",
        root=root,
        kind="service",
        languages=frozenset(),
        source_roots=(),
        output_dirs=(root / "target" / "classes",),
        resource_roots=(resource_root,),
        schema_roots=(schema_root,),
    )


def _analyzed(tmp_path: Path, resource_root: Path, schema_root: Path) -> Path:
    fact_root = tmp_path / "facts"
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        analyze(
            path=tmp_path,
            workspace=workspace,
            detectors=[_FakeDetector(_module(tmp_path, resource_root, schema_root))],
            scanners=[_NoOpScanner()],
            catalogs=_EmptyCatalogs(),
            fact_root=fact_root,
            progress=NullProgress(),
            readers=[YamlConfigReader(), WsdlXsdReader()],
        )
    finally:
        workspace.close()
    return fact_root


def test_an_ignored_config_file_contributes_zero_config_entries(tmp_path: Path):
    """`application-secret.yml` is an ordinary, valid, parseable config
    file — nothing about its OWN content is wrong — and it still contributes
    nothing once `.sextantignore` names it: the file never reaches
    `YamlConfigReader` at all. A sibling file the ignore file does not name
    is read normally, proving the walk excludes precisely the named file
    and nothing else."""
    resource_root = tmp_path / "src" / "main" / "resources"
    resource_root.mkdir(parents=True)
    (resource_root / "application-secret.yml").write_text(
        "decoy:\n  leaked: should-never-appear\n", encoding="utf-8"
    )
    (resource_root / "application.yml").write_text("kept:\n  key: kept-value\n", encoding="utf-8")
    (tmp_path / ".sextantignore").write_text(
        "src/main/resources/application-secret.yml\n", encoding="utf-8"
    )
    schema_root = tmp_path / "schema"
    schema_root.mkdir()

    fact_root = _analyzed(tmp_path, resource_root, schema_root)

    keys = {
        entry.key_path
        for _, _, facts in read_fact_tree(fact_root)
        for entry in facts
        if entry.kind == "config_entry"
    }
    assert "decoy.leaked" not in keys
    assert "kept.key" in keys


def test_an_ignored_schema_file_contributes_zero_shapes(tmp_path: Path):
    """The same wiring, on the SCHEMA loop — a `.wsdl` `.sextantignore`
    names must contribute no `embedded_descriptor` fact, while a sibling
    `.wsdl` it does not name is read normally."""
    resource_root = tmp_path / "resources"
    resource_root.mkdir(parents=True)
    schema_root = tmp_path / "src" / "main" / "wsdl"
    schema_root.mkdir(parents=True)
    (schema_root / "secret.wsdl").write_text(
        '<wsdl:definitions xmlns:wsdl="w"/>\n', encoding="utf-8"
    )
    (schema_root / "kept.wsdl").write_text('<wsdl:definitions xmlns:wsdl="w"/>\n', encoding="utf-8")
    (tmp_path / ".sextantignore").write_text("src/main/wsdl/secret.wsdl\n", encoding="utf-8")

    fact_root = _analyzed(tmp_path, resource_root, schema_root)

    symbols = {
        fact.symbol
        for _, _, facts in read_fact_tree(fact_root)
        for fact in facts
        if fact.kind == "embedded_descriptor"
    }
    assert "secret.wsdl" not in symbols
    assert "kept.wsdl" in symbols
