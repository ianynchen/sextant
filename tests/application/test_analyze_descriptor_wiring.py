"""Task 4: interpretation wired ONCE in `analyze`, over compiled and source
descriptors together, with DR-4 (compiled-beats-source) applied afterwards.

Imports `sextant.ingress.*` freely — this is a test, not the layering
contract's target (`test_import_contracts_hold_when_the_suite_runs` scans
only `sextant/`) — the same way the cli composition root itself does to wire
`analyze`'s `interpret` parameter."""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import read_fact_tree, write_fact_file
from sextant.domain.facts import DeclaredShapeFact, Document, EmbeddedDescriptorFact
from sextant.ingress.interpret.descriptors import SchemaLocation, interpret_descriptors
from sextant.ingress.read.avsc import AvscReader
from sextant.ingress.read.graphql_sdl import GraphqlSdlReader
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.proto_source import ProtoSourceReader
from sextant.ingress.read.yaml_config import YamlConfigReader
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


class _FakeInterpreter:
    """The `DescriptorInterpreter` port, satisfied the same way cli's own
    `_JvmDescriptorInterpreter` does — an object with a named `interpret`
    method binding a naming — but with `_FakeNaming` above rather than
    `JvmGeneratedNaming`, which this test has no business constructing."""

    def interpret(
        self, descriptors: Sequence[EmbeddedDescriptorFact]
    ) -> tuple[list[DeclaredShapeFact], list[str]]:
        return interpret_descriptors(descriptors, _FakeNaming())


class _NoOpScanner:
    """A scanner that writes nothing — used by tests exercising only the
    schema-reader/interpretation path, where no compiled facts matter."""

    def accepts(self, languages: set[str]) -> bool:
        return True

    def capabilities(self) -> set[str]:
        return set()

    def rank(self) -> int:
        return 1

    def scan(self, request: ScanRequest) -> ScanReport:
        return ScanReport(documents=0, facts=0, scanner_id="noop", scanner_version="1.0")


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
            interpret=_FakeInterpreter(),
        )
    finally:
        workspace.close()

    shapes = [
        fact
        for _, _, facts in read_fact_tree(fact_root)
        for fact in facts
        if fact.kind == "declared_shape" and fact.schema_name == "pkg.Widget"
    ]

    assert len(shapes) == 1
    [shape] = shapes
    assert shape.origin == "compiled"
    assert [field.name for field in shape.fields] == ["compiled_only"]


def test_a_second_analyze_into_the_same_workspace_does_not_grow_the_fact_tree(
    tmp_path: Path,
):
    """CRITICAL fix (review round 1): schema fact files used to be appended
    to across runs — a second `analyze()` into the same workspace (the
    default `.sextant` workspace makes this the ORDINARY path, not an edge
    case) grew a compiled document's fact file every time, because nothing
    refreshes it except the interpret step's own write, and that write used
    to read-then-append. Fixed by writing each schema-bearing document's
    fact file whole, every run — this asserts the whole fact tree is
    byte-identical after a second run, not merely that the endpoint count
    still matches (NFR-1: identical input, identical output, run after
    run)."""
    schema_root = tmp_path / "schema"
    _write_avsc(schema_root, "widget.avsc", field_name="source_only")
    module_id = "com.acme:widgets"
    module = _module(tmp_path, schema_root)
    compiled_document = _compiled_document(module_id)
    compiled_payload = (
        '{"type":"record","name":"Widget","namespace":"pkg",'
        '"fields":[{"name":"compiled_only","type":"string"}]}'
    )
    fact_root = tmp_path / "facts"

    def _snapshot() -> dict[str, str]:
        return {
            str(path.relative_to(fact_root)): path.read_text(encoding="utf-8")
            for path in sorted(fact_root.rglob("*.jsonl"))
        }

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    snapshots: list[dict[str, str]] = []
    try:
        for _ in range(2):
            analyze(
                path=tmp_path,
                workspace=workspace,
                detectors=[_FakeDetector(module)],
                scanners=[_FakeCompiledScanner(compiled_document, compiled_payload)],
                catalogs=_EmptyCatalogs(),
                fact_root=fact_root,
                progress=NullProgress(),
                readers=[AvscReader()],
                interpret=_FakeInterpreter(),
            )
            snapshots.append(_snapshot())
    finally:
        workspace.close()

    assert snapshots[0], "the first run must actually have written a fact tree"
    assert snapshots[0] == snapshots[1]


def test_a_broken_proto_root_is_recorded_as_schema_sources_not_compiled(tmp_path: Path):
    """SPEC MISS 2: the `schema_sources_not_compiled` gap field, asserted
    directly on `AnalyzeResult` rather than only exercised incidentally by a
    reader-level test."""
    schema_root = tmp_path / "schema"
    schema_root.mkdir(parents=True)
    (schema_root / "broken.proto").write_text('syntax = "proto3";\nmessage Foo { nope }\n')
    module = _module(tmp_path, schema_root)

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        result = analyze(
            path=tmp_path,
            workspace=workspace,
            detectors=[_FakeDetector(module)],
            scanners=[_NoOpScanner()],
            catalogs=_EmptyCatalogs(),
            fact_root=tmp_path / "facts",
            progress=NullProgress(),
            readers=[ProtoSourceReader()],
            interpret=_FakeInterpreter(),
        )
    finally:
        workspace.close()

    assert result.schema_sources_not_compiled == ("broken.proto",)


def test_an_uninterpretable_descriptor_is_recorded_as_descriptors_not_interpreted(
    tmp_path: Path,
):
    """SPEC MISS 2: the `descriptors_not_interpreted` gap field, for a
    compiled payload the interpreter cannot read at all (not even valid
    JSON) — `interpret_descriptors`'s own failure list, carried through."""
    module_id = "com.acme:widgets"
    module = _module(tmp_path, tmp_path / "schema")  # no schema root files at all
    compiled_document = _compiled_document(module_id)

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        result = analyze(
            path=tmp_path,
            workspace=workspace,
            detectors=[_FakeDetector(module)],
            scanners=[_FakeCompiledScanner(compiled_document, "not json at all")],
            catalogs=_EmptyCatalogs(),
            fact_root=tmp_path / "facts",
            progress=NullProgress(),
            readers=[],
            interpret=_FakeInterpreter(),
        )
    finally:
        workspace.close()

    assert result.descriptors_not_interpreted == ("pkg.Widget",)


def _sdl_module(root: Path) -> ModuleModel:
    """Maven's real GraphQL layout: the SDL directory is a schema root that
    sits INSIDE the resource root, which is why this module declares both."""
    return ModuleModel(
        module_id="com.acme:widgets",
        coordinates="com.acme/widgets",
        version="1.0.0",
        root=root,
        kind="library",
        languages=frozenset(),
        source_roots=(),
        output_dirs=(root / "target" / "classes",),
        resource_roots=(root / "src" / "main" / "resources",),
        schema_roots=(root / "src" / "main" / "resources" / "graphql",),
    )


def _write_sdl_module(root: Path) -> None:
    schema_root = root / "src" / "main" / "resources" / "graphql"
    schema_root.mkdir(parents=True)
    (schema_root / "schema.graphqls").write_text(
        "type Query { auditTrail: [AuditEntry!] }\n", encoding="utf-8"
    )
    (schema_root / "audit.graphqls").write_text(
        "type AuditEntry { at: String! }\n", encoding="utf-8"
    )


def _analyze_sdl_module(root: Path) -> None:
    workspace = DuckDbWorkspace(root / "ws.duckdb")
    try:
        analyze(
            path=root,
            workspace=workspace,
            detectors=[_FakeDetector(_sdl_module(root))],
            scanners=[_NoOpScanner()],
            catalogs=_EmptyCatalogs(),
            fact_root=root / "facts",
            progress=NullProgress(),
            readers=[PropertiesReader(), YamlConfigReader(), GraphqlSdlReader()],
            interpret=_FakeInterpreter(),
        )
    finally:
        workspace.close()


def test_the_sdl_reader_and_the_graphql_branch_reach_declared_shapes_through_analyze(
    tmp_path: Path,
):
    """The whole path in one run: the detector's schema root, the registry's
    reader, and the interpreter's module-wide merge — `Query.auditTrail`
    resolving to the OTHER file's type is the proof the merge happened here
    and not per file."""
    _write_sdl_module(tmp_path)

    _analyze_sdl_module(tmp_path)

    shapes = {
        fact.symbol: fact
        for _, _, facts in read_fact_tree(tmp_path / "facts")
        for fact in facts
        if fact.kind == "declared_shape"
    }
    assert set(shapes) == {"Query", "AuditEntry"}
    assert shapes["Query"].schema_format == "graphql"
    assert shapes["Query"].evidence == "declared"
    [audit_trail] = shapes["Query"].fields
    assert audit_trail.item is not None
    assert audit_trail.item["shape_id"] == "AuditEntry"


def test_an_sdl_file_inside_the_resource_root_is_read_once_not_twice(tmp_path: Path):
    """The SDL directory lives UNDER `src/main/resources`, and the resource
    walk is recursive, so one registry serving both loops would hand the same
    file to the same reader twice — two documents for one file (D00 §7's
    one-record-per-source-file rule), two descriptors, and every graphql type
    declared twice, which the interpreter would then report as a duplicate
    and drop entirely."""
    _write_sdl_module(tmp_path)

    _analyze_sdl_module(tmp_path)

    documents = [document for _, document, _ in read_fact_tree(tmp_path / "facts")]
    assert sorted(document.relative_path for document in documents) == [
        "audit.graphqls",
        # 2O Task 6: the detector's own conclusions are a fact like any other
        # now (D00 §5's `module` kind), and its synthesized document sits
        # beside the read ones.
        "module",
        "schema.graphqls",
    ]


def test_an_ordinary_resource_inside_a_schema_root_stays_an_ordinary_resource(tmp_path: Path):
    """Fix round 1, MINOR: a schema root is a DIRECTORY, and the partition
    between the two read loops is per file. A `messages.properties` filed
    beside the SDL is still config: reading it in the schema loop would give
    it a schema-root-relative path and a `schema/` fact target, so the same
    file would land in a different place purely because of a sibling
    directory's name."""
    _write_sdl_module(tmp_path)
    resources = tmp_path / "src" / "main" / "resources"
    (resources / "application.properties").write_text("a=1\n", encoding="utf-8")
    (resources / "graphql" / "messages.properties").write_text("b=2\n", encoding="utf-8")

    _analyze_sdl_module(tmp_path)

    targets = {
        document.relative_path: target.relative_to(tmp_path / "facts").parts[0]
        for target, document, _ in read_fact_tree(tmp_path / "facts")
    }
    # Keyed by a RESOURCE-root-relative path (`graphql/…`, not `…`) and
    # written under the config tree — the identity it would have had if the
    # sibling SDL directory were named anything else.
    assert targets["graphql/messages.properties"] == "config"
    assert targets["application.properties"] == "config"
    assert targets["schema.graphqls"] == "schema"


def test_the_ingress_import_contract_still_holds():
    """`application/stages/analyze.py` now takes an `interpret` parameter and
    reaches `read_fact_tree`/`schema_fact_target` — this re-runs the same
    import-linter gate `test_layering.py` runs, so a regression here is
    caught beside the wiring it is actually about, without duplicating that
    test's own subprocess logic by hand."""
    script = Path(sys.executable).parent / "lint-imports"
    assert script.exists(), f"import-linter is not installed beside {sys.executable}"
    result = subprocess.run([str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
