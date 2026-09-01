"""Task 4: interpretation wired ONCE in `analyze`, over compiled and source
descriptors together, with DR-4 (compiled-beats-source) applied afterwards.

Imports `sextant.ingress.*` freely — this is a test, not the layering
contract's target (`test_import_contracts_hold_when_the_suite_runs` scans
only `sextant/`) — the same way the cli composition root itself does to wire
`analyze`'s `interpret` parameter."""

import subprocess
import sys
from functools import partial
from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import read_fact_tree, write_fact_file
from sextant.domain.facts import Document, EmbeddedDescriptorFact
from sextant.ingress.interpret.descriptors import SchemaLocation, interpret_descriptors
from sextant.ingress.read.avsc import AvscReader
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]


class _FakeDetector:
    """Keyed by nothing in particular — this test builds a module by hand
    rather than reading a real build file, the same fake-detector idiom
    `tests/architecture` and friends already use."""

    def __init__(self, module: ModuleModel) -> None:
        self._module = module

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=path, modules=(self._module,))


def _compiled_document(module_id: str) -> Document:
    return Document(
        document_id="fake-compiled-widget",
        relative_path="pkg/Widget.class",
        module_id=module_id,
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="fake-scanner",
        scanner_version="1.0",
        content_hash="sha256:deadbeef",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


class _FakeCompiledScanner:
    """Stands in for the real JVM scanner: on `scan()`, writes one compiled
    `embedded_descriptor` fact straight to `fact_root` — exactly what the
    real scanner does before `analyze` ever calls back into it — for the
    SAME schema identity (`pkg.Widget`) the fixture's own `.avsc` schema
    root also declares. That shared identity is this test's whole point:
    DR-4 says compiled wins."""

    def __init__(self, document: Document, payload: str) -> None:
        self._document = document
        self._payload = payload

    def accepts(self, languages: set[str]) -> bool:
        return True

    def capabilities(self) -> set[str]:
        return set()

    def rank(self) -> int:
        return 1

    def scan(self, request: ScanRequest) -> ScanReport:
        fact = EmbeddedDescriptorFact(
            document_id=self._document.document_id,
            symbol="pkg.Widget",
            schema_format="avro",
            payload=self._payload,
            origin="compiled",
        )
        write_fact_file(request.out_dir / "compiled" / "widget.jsonl", self._document, [fact])
        return ScanReport(documents=1, facts=1, scanner_id="fake-scanner", scanner_version="1.0")


class _EmptyCatalogs:
    def load(self) -> list[Catalog]:
        return []


class _FakeNaming:
    """A minimal `GeneratedNaming` — dotted package plus nesting path, no
    per-language rule to exercise here (that is `JvmGeneratedNaming`'s own
    surface, covered by `test_generated_naming.py`)."""

    def class_symbol(self, location: SchemaLocation) -> str:
        return (
            ".".join([location.package, *location.path])
            if location.package
            else ".".join(location.path)
        )


def _write_avsc(root: Path, name: str, field_name: str) -> None:
    schema = (
        '{"type":"record","name":"Widget","namespace":"pkg",'
        f'"fields":[{{"name":"{field_name}","type":"string"}}]}}'
    )
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(schema, encoding="utf-8")


def _module(root: Path, schema_root: Path) -> ModuleModel:
    return ModuleModel(
        module_id="com.acme:widgets",
        coordinates="com.acme/widgets",
        version="1.0.0",
        root=root,
        kind="library",
        languages=frozenset(),
        source_roots=(),
        output_dirs=(root / "target" / "classes",),
        resource_roots=(),
        schema_roots=(schema_root,),
    )


def test_compiled_beats_source_for_the_same_schema_identity_after_interpretation(
    tmp_path: Path,
):
    schema_root = tmp_path / "schema"
    _write_avsc(schema_root, "widget.avsc", field_name="source_only")

    module_id = "com.acme:widgets"
    module = _module(tmp_path, schema_root)
    compiled_document = _compiled_document(module_id)
    # Deliberately a DIFFERENT field set from the source payload above, so
    # the surviving shape's own fields say unambiguously which origin won.
    compiled_payload = (
        '{"type":"record","name":"Widget","namespace":"pkg",'
        '"fields":[{"name":"compiled_only","type":"string"}]}'
    )

    fact_root = tmp_path / "facts"
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        analyze(
            path=tmp_path,
            workspace=workspace,
            detectors=[_FakeDetector(module)],
            scanners=[_FakeCompiledScanner(compiled_document, compiled_payload)],
            catalogs=_EmptyCatalogs(),
            fact_root=fact_root,
            progress=NullProgress(),
            readers=[AvscReader()],
            interpret=partial(interpret_descriptors, naming=_FakeNaming()),
        )
    finally:
        workspace.close()

    shapes = [
        fact
        for _, facts in read_fact_tree(fact_root)
        for fact in facts
        if fact.kind == "declared_shape" and fact.schema_name == "pkg.Widget"
    ]

    assert len(shapes) == 1
    [shape] = shapes
    assert shape.origin == "compiled"
    assert [field.name for field in shape.fields] == ["compiled_only"]


def test_the_ingress_import_contract_still_holds():
    """`application/stages/analyze.py` now takes an `interpret` parameter and
    reaches `read_fact_tree`/`schema_fact_target`/`append_fact_file` — this
    re-runs the same import-linter gate `test_layering.py` runs, so a
    regression here is caught beside the wiring it is actually about,
    without duplicating that test's own subprocess logic by hand."""
    script = Path(sys.executable).parent / "lint-imports"
    assert script.exists(), f"import-linter is not installed beside {sys.executable}"
    result = subprocess.run([str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
