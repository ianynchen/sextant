import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.cli.app import cli
from sextant.cli.resources import catalogs_dir, extractor_jar
from sextant.domain.factfile import read_fact_tree
from sextant.domain.symbols import bare_descriptor, owner_of
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"
_JAR = extractor_jar()
_CATALOGS = catalogs_dir()


class _NoCapabilitiesScanner:
    """Wraps the real scanner but reports no capabilities, so any catalog
    with a `requires` entry is genuinely skipped — Phase 1 ships only one
    catalog, so this is the only way to reproduce a skip without adding a
    second one."""

    def __init__(self, inner: AsmScanner) -> None:
        self._inner = inner

    def accepts(self, languages: set[str]) -> bool:
        return self._inner.accepts(languages)

    def capabilities(self) -> set[str]:
        return set()

    def rank(self) -> int:
        return self._inner.rank()

    def scan(self, request: ScanRequest) -> ScanReport:
        return self._inner.scan(request)


def test_analyze_writes_metadata_and_reports_endpoint_count(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    # 2E-prep Task 6: +1 (`GET /composed`, the effective-annotations
    # pre-pass's `@ApiGet` composition). Phase 2E Task 7: +2 more
    # (`GET /api/orders`, `GET /api/composed`, the inherited-mappings
    # pass). Phase 2E Task 9: +10 more (the `combinator` engine's WebFlux
    # functional-routing tree, both DSLs). 2G Task 5: +1 more
    # (`POST /v1/orders/proto-orders`, the generated-protobuf payload
    # endpoint). 2H Task 1: +2 more (`GET /events/emitter`, `GET
    # /events/stream` — `OrderEventsController`'s already-shipped
    # `@GetMapping` annotations derive as ordinary http endpoints today; a
    # later 2H task reclassifies them to SSE) — see test_pipeline.py's own
    # dedicated row-level test for the full breakdown.
    assert metadata["endpoints"]["inbound"]["http"] == 34


def test_analyze_document_count_matches_the_real_compiled_and_source_files(tmp_path: Path):
    """IMPORTANT A fix (Task 4 review round 1): compiled-origin declared_shape
    facts used to be written into a NEW fact file that re-emitted their own
    `Document` header, so a document that already had one fact file (every
    compiled class) counted twice in `coverage.documents` — 87 for 84 real
    documents. Pinned from a live run, not computed by hand, so any future
    regression that mints a second Document record for an existing document
    is caught here directly rather than only inferred from row counts
    elsewhere."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    # 84 + 3: 2G Task 7's `messaging/parse` package compiles to three more
    # class files (the listeners and the two delegation targets), one
    # document each — a real source counted once, which is exactly what this
    # test exists to keep true.
    # + 6: 2H Task 1's GraphQL, WebSocket/STOMP and SSE surfaces compile to
    # six more class files, one document each. The two new `.graphqls`
    # resources under src/main/resources are NOT claimed by any reader yet
    # (readers claim by extension, and nothing in this task adds one), so
    # they add no documents here.
    assert metadata["coverage"]["documents"] == 93


def test_receipt_avsc_reaches_the_graph_as_a_source_only_declared_shape(tmp_path: Path):
    """IMPORTANT B (Task 4 review round 1): `receipt.avsc` is this fixture's
    one schema identity with no compiled counterpart —
    `fixtures/orders-service/pom.xml`'s avro-maven-plugin `<excludes>` block
    keeps the jar from ever embedding it. Pinned end to end, through the real
    CLI command and the real fact tree it writes, so silently deleting that
    `<excludes>` block (making Receipt compiled again, and DR-4 drop the
    source shape this test expects) fails a test rather than only a stale
    fixture comment."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output

    shapes = [
        fact
        for _, _, facts in read_fact_tree(tmp_path / "facts")
        for fact in facts
        if fact.kind == "declared_shape" and fact.schema_name == "com.example.orders.avro.Receipt"
    ]
    assert len(shapes) == 1
    [shape] = shapes
    assert shape.origin == "source"
    assert shape.evidence == "declared"


def test_a_declared_protobuf_shape_expands_from_the_schema_not_the_generated_classes_bytecode(
    tmp_path: Path,
):
    """Task 5 review round 1, SPEC finding: the only prior coverage for the
    never-a-blend rule was a hand-built `declared_shape` universe whose fake
    type carried a single bytecode field — nothing exercised the real
    generated protobuf classes end to end, so an expansion-order or
    lookup-key regression that let a real compiled schema class re-blend
    with its own bytecode fields could still leave the whole suite green.
    `OrderProtos$OrderRequest` — the class ASM actually scans — carries 19
    bytecode fields (protobuf's own serialization machinery: bitfields, a
    memoized hash code, generated accessor plumbing), verified live below;
    the wire contract is exactly the 7 fields `order.proto` declares.
    Pinned end to end through the real CLI `analyze` command and the real
    DuckDB tables it wrote, exact-list, copied from a live run rather than
    computed by hand."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    order_request = "com/example/orders/proto/OrderProtos$OrderRequest#"
    order_reply = "com/example/orders/proto/OrderProtos$OrderReply#"
    line = "com/example/orders/proto/OrderProtos$OrderRequest$Line#"
    money = "com/example/orders/proto/CommonProtos$Money#"

    def fields_of(shape_id: str) -> list[tuple]:
        return [
            (f["ordinal"], f["wire_name"], f["field_number"], f["wire_type"], f["wire_format"])
            for f in workspace.query("shape_fields")
            if f["shape_id"] == shape_id
        ]

    order_request_fields = fields_of(order_request)
    assert len(order_request_fields) == 7
    assert order_request_fields == [
        (0, "totalAmount", 1, "string", None),
        (1, "explicitCount", 2, "integer", "int32"),
        (2, "price", 3, "object", None),
        (3, "lines", 4, "array", None),
        (4, "tags", 5, "map", None),
        (5, "status", 6, "enum", None),
        (6, "note", 7, "string", None),
    ]
    items = {
        f["wire_name"]: (None if f["item"] is None else json.loads(f["item"]))
        for f in workspace.query("shape_fields")
        if f["shape_id"] == order_request
    }
    assert items["price"] == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": True,
        "shape_id": money,
    }
    assert items["lines"] == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": line,
    }
    assert items["tags"] == {"wire_type": "string", "wire_format": None, "nullable": False}
    assert items["status"] is None  # enum: mapped, never expanded
    assert fields_of(order_reply) == [(0, "orderId", 1, "string", None)]
    assert fields_of(line) == [(0, "sku", 1, "string", None)]
    assert fields_of(money) == [
        (0, "currency", 1, "string", None),
        (1, "amountMinor", 2, "integer", "int64"),
    ]

    shapes = {s["shape_id"]: s["open"] for s in workspace.query("shapes")}
    for shape_id in (order_request, order_reply, line, money):
        assert shapes[shape_id] is False

    # The anti-blend pin: the real generated class's own bytecode carries far
    # more than the 7 wire fields above — serialization machinery
    # (bitfields, a memoized hash code, generated accessor plumbing), never
    # the contract. `owner_of(bare_descriptor(...))` is the exact-match test
    # `_declared_fields` itself groups fields by, so this counts precisely
    # `OrderRequest`'s own fields, never `Line`'s (a distinct owner one level
    # further in the descriptor).
    bytecode_field_count = sum(
        1
        for f in workspace.query("fields")
        if owner_of(bare_descriptor(str(f["symbol"]))) == order_request
    )
    assert bytecode_field_count == 19


def test_export_writes_a_bundle_with_manifest_graph_and_facts(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "graph" / "endpoints.parquet").is_file()
    facts_files = list((bundle / "facts").rglob("*.parquet"))
    assert facts_files, "facts/ must not be empty"


def test_render_writes_the_document_after_analyze(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    result = runner.invoke(cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "POST" in document and "/v1/orders" in document


def test_render_exits_nonzero_with_a_message_when_no_workspace_exists(tmp_path: Path):
    result = CliRunner().invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "module analyze" in result.output


def test_render_names_the_catalog_and_capability_analyze_skipped(tmp_path: Path):
    """A weaker scanner must degrade *visibly* (M04, FR-17) — including
    through `render`, which reads back what `analyze` already established
    rather than recomputing it."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        result = analyze(
            path=FIXTURE,
            workspace=workspace,
            detectors=[MavenDetector()],
            scanners=[_NoCapabilitiesScanner(AsmScanner(_JAR))],
            catalogs=YamlCatalogSource(_CATALOGS),
            fact_root=tmp_path / "facts",
            progress=NullProgress(),
        )
        assert result.report.skipped_catalogs, "the catalog was not actually skipped"
        write_metadata(
            tmp_path / "metadata.json",
            result.module,
            result.report,
            "asm",
            "9.7",
            "deadbeef",
        )
    finally:
        workspace.close()

    render_result = CliRunner().invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert render_result.exit_code == 0, render_result.output
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "spring-web" in document
    assert "annotation_args" in document


def test_analyze_reports_nothing_uncovered_now_that_the_nested_class_is_read(tmp_path: Path):
    """The fixture's nested class was this module's one compiled source the
    facts did not account for, and `uncovered` existed to say so. It is scanned
    now (D00 §2 — one class file is one document), so the honest answer is an
    empty list and a gap section that names no unread source. The channel is
    still load-bearing — a Kotlin class whose metadata cannot be decoded still
    travels it — which is why the assertion is that it is empty here, not that
    it is gone."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["uncovered"] == []

    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "Not read" not in document.split("## Known gaps", 1)[1]
