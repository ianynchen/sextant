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
        return ScanReport(documents=0, facts=0, scanner_id="noop")


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


# --- `A-M16` (principles sweep §3.3): which root the ignore file sits at ----


def _analyzed_submodule(reactor_root: Path, module_root: Path, ignore_root: Path | None) -> Path:
    """One SUBMODULE of a reactor, analyzed exactly as `api.py` analyzes one:
    its own module root, its own workspace, its own fact tree — and, since
    `A-M16`, the reactor's root for the ignore file."""
    fact_root = module_root / "facts"
    resource_root = module_root / "src" / "main" / "resources"
    schema_root = module_root / "schema"
    schema_root.mkdir(parents=True, exist_ok=True)
    workspace = DuckDbWorkspace(module_root / "ws.duckdb")
    try:
        analyze(
            path=module_root,
            workspace=workspace,
            detectors=[_FakeDetector(_module(module_root, resource_root, schema_root))],
            scanners=[_NoOpScanner()],
            catalogs=_EmptyCatalogs(),
            fact_root=fact_root,
            progress=NullProgress(),
            readers=[YamlConfigReader(), WsdlXsdReader()],
            ignore_root=ignore_root,
        )
    finally:
        workspace.close()
    return fact_root


def _reactor(tmp_path: Path) -> tuple[Path, Path]:
    """A reactor root with one submodule, one `.sextantignore` at the reactor
    root naming a path relative to THAT root, and two config files in the
    submodule — one named by the pattern, one not."""
    module_root = tmp_path / "orders-service"
    resource_root = module_root / "src" / "main" / "resources"
    resource_root.mkdir(parents=True)
    (resource_root / "application-secret.yml").write_text(
        "decoy:\n  leaked: should-never-appear\n", encoding="utf-8"
    )
    (resource_root / "application.yml").write_text("kept:\n  key: kept-value\n", encoding="utf-8")
    (tmp_path / ".sextantignore").write_text(
        "orders-service/src/main/resources/application-secret.yml\n", encoding="utf-8"
    )
    return tmp_path, module_root


def _config_keys(fact_root: Path) -> set[str]:
    return {
        entry.key_path
        for _, _, facts in read_fact_tree(fact_root)
        for entry in facts
        if entry.kind == "config_entry"
    }


def test_a_reactor_root_ignore_file_reaches_a_submodule(tmp_path: Path):
    """`A-M16`, the positive half. `D04 §3` is emphatic, and is itself an
    amendment: "One file, at the **repository root**, and every pattern in it
    is matched against a path made relative to THAT root."

    `analyze` loaded it at `module.root`, and `api.py` analyzes each submodule
    with its own root — so a reactor-root `.sextantignore` was read for NO
    submodule, and a pattern written relative to the reactor root would not
    have matched even if it had been. Both halves are exercised here: the file
    sits one level above the submodule, and its pattern is spelled
    `orders-service/src/main/resources/...`, which only relativizing against
    the reactor root can match.

    The BUILT-IN patterns applied at every depth throughout, which is why this
    was a coverage gap in the repository-authored layer and never a credential
    leak — but a repository that wrote its own rule got nothing from it."""
    reactor_root, module_root = _reactor(tmp_path)

    keys = _config_keys(_analyzed_submodule(reactor_root, module_root, ignore_root=reactor_root))

    assert "decoy.leaked" not in keys
    assert "kept.key" in keys


def test_a_submodule_rooted_ignore_load_still_reads_the_file_the_reactor_named(
    tmp_path: Path,
):
    """`A-M16`'s near-miss, and it is the whole finding rather than a
    hypothetical: with the ignore file loaded at the SUBMODULE root — the
    behaviour this replaces, reached here by passing `ignore_root=None` — the
    reactor's `.sextantignore` is invisible and the file it names is read.

    Identical to the positive in every other cell; the one difference is the
    root the rules were loaded at, so it measures that and nothing else. The
    sibling key is asserted in both, which is what stops the positive from
    passing because the walk read nothing at all."""
    reactor_root, module_root = _reactor(tmp_path)
    del reactor_root

    keys = _config_keys(_analyzed_submodule(module_root, module_root, ignore_root=None))

    assert "decoy.leaked" in keys
    assert "kept.key" in keys


def test_a_module_outside_the_analysed_root_keeps_its_own_ignore_root(tmp_path: Path):
    """`A-M16`'s own near-miss, and it is not a corner:
    `<module>../orders-service</module>` is legal Maven and
    `fixtures/orders-reactor` is exactly that shape — the reactor root is a
    SIBLING of the module it names, not an ancestor.

    A path outside a root has no root-relative form, so a pattern written
    against that root could not address it even in principle, and asking for
    one raises. The load falls back to the module's own root there — the
    behaviour that shipped — which is what this asserts: the module's OWN
    `.sextantignore` is honoured and the run does not fail.

    It discriminates: passing the sibling root through unconditionally raises
    `ValueError: not in the subpath of`, which is how the reactor end-to-end
    test caught this."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    _, module_root = _reactor(tmp_path)
    (module_root / ".sextantignore").write_text(
        "src/main/resources/application-secret.yml\n", encoding="utf-8"
    )

    keys = _config_keys(_analyzed_submodule(outside, module_root, ignore_root=outside))

    assert "decoy.leaked" not in keys
    assert "kept.key" in keys
