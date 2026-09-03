import json
import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.cli.app import _tool_executor_for, cli
from sextant.cli.resources import catalogs_dir, extractor_jar
from sextant.domain.factfile import read_fact_tree
from sextant.domain.redaction import Redactor
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
    # later 2H task reclassifies them to SSE). 2H Task 6 IS that task: -2,
    # back to 32, and the two rows reappear under `sse` — the
    # `protocol_hint` pass moves a row between buckets and never adds or
    # removes one, so the TOTAL is untouched. See test_pipeline.py's own
    # dedicated row-level test for the full breakdown.
    # + 2: the prefix-seam controllers — `GET /v1/seam/owners/{ownerId}` and
    # `POST /chat`, one route each. Both were already derivable; what the
    # `path_separator` fix changed is the ADDRESS each derives, not the count.
    assert metadata["endpoints"]["inbound"]["http"] == 34
    assert metadata["endpoints"]["inbound"]["sse"] == 2


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
    # six more class files, one document each.
    # + 1: 2H Task 2's `CustomerGraphqlController` — one more class file, one
    # more document. It is the class-level-scope resolver shape, which needed
    # its own type to carry the class-level annotation.
    # + 2: 2H Task 3's SDL reader now claims Task 1's two `.graphqls` files
    # under `src/main/resources/graphql`, one document each. TWO, not four:
    # that directory is a schema root INSIDE the resource root, and `analyze`
    # reads it in the schema loop only (`_config_files`) — a file read by both
    # loops would mint a second Document for one source file, the very fault
    # this test exists to catch.
    # + 2: the prefix-seam controllers (`SeamController`, `RootSeamController`)
    # — one more class file each, one more document each.
    # + 5: 2I Task 1's SOAP surfaces compile to five more class files
    # (`OrderSoapEndpoint`, `BillingWebService`, `LegacyBillingWebService`,
    # `BillingSoapClient`, `PlaceOrderRequest`), one document each.
    # + 2: 2I Task 3's WSDL/XSD reader now claims Task 1's `orders.wsdl` and
    # `orders-types.xsd` under `src/main/resources/wsdl`, one document each.
    # TWO, not four, for the same reason the SDL pair above is two: that
    # directory is a schema root INSIDE the resource root, so only the schema
    # loop reads it.
    # + 1: 2I Task 6's opt-in library extraction. `BillingPort` is one class
    # file inside `com.example:orders-soap-client`, and a class file is a
    # document wherever it was read from (D00 §2) — this is the count moving
    # because a jar was scanned, which is the point of the feature.
    assert metadata["coverage"]["documents"] == 106


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


def test_render_also_writes_a_self_contained_offline_html_document(tmp_path: Path):
    """2K design §6b, the live pin over a real analysed module rather than a
    synthetic one: `architecture.html` lands beside `architecture.md`, wraps
    the real structure diagram in pan-zoom controls, and carries no CDN or
    external script URL."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    result = runner.invoke(cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    html_path = tmp_path / "render" / "architecture.html"
    assert html_path.is_file()
    document = html_path.read_text(encoding="utf-8")
    assert 'class="diagram"' in document
    assert 'class="diagram-zoom-in"' in document
    assert "<script src=" not in document
    assert "cdn.jsdelivr.net" not in document
    # M-6: the title carries the real module id, not a placeholder — two
    # modules rendered in the same browser session must be distinguishable
    # by their tab.
    assert "<title>Sextant — com.acme:orders-service</title>" in document


def test_rendering_the_same_workspace_twice_writes_a_byte_identical_html_document(
    tmp_path: Path,
):
    """NFR-1's amendment note (2K design §8): re-running render over the same
    workspace and the same (absent) overlay produces the same bytes — nothing
    in the HTML path reads a clock or a dict in insertion-unstable order
    either."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    html_path = tmp_path / "render" / "architecture.html"
    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    first = html_path.read_bytes()
    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    second = html_path.read_bytes()
    assert first == second


def test_export_carries_both_rendered_documents_into_the_bundle(tmp_path: Path):
    """The bundle carries what `render` already wrote (2K design §6b) — copied
    verbatim rather than re-rendered, so the bundle and the workspace can
    never disagree about what a reader saw."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    assert (bundle / "render" / "architecture.md").read_bytes() == (
        tmp_path / "render" / "architecture.md"
    ).read_bytes()
    assert (bundle / "render" / "architecture.html").read_bytes() == (
        tmp_path / "render" / "architecture.html"
    ).read_bytes()
    # The manifest declares what it shipped (2K Task 8 review, D06 §3):
    # `render/` joins `facts`/`graph`/`tables`/`facts_files` as content the
    # manifest names rather than leaves for a consumer to discover by
    # listing the bundle itself.
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contents"]["render"] == ["architecture.md", "architecture.html"]


def test_export_without_a_prior_render_carries_no_render_directory(tmp_path: Path):
    """`render` is not a prerequisite for `export` (M08: export only ever
    reads what `analyze` left) — a workspace that skipped it must still
    export cleanly, exactly as it did before this task."""
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
    assert not (bundle / "render").exists()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contents"]["render"] == []


def test_render_exits_nonzero_with_a_message_when_no_workspace_exists(tmp_path: Path):
    result = CliRunner().invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "module analyze" in result.output


def test_re_analyzing_clears_a_stale_rendered_document(tmp_path: Path):
    """2K Task 8 review (Task 4's own review flagged the gap): `analyze`
    never otherwise touches `render/` — that is `render`'s own output — so
    a workspace re-analyzed after its code changed would, without this,
    still carry the OLD `architecture.md`/`.html` on disk. Worse, `enrich`'s
    own "no rendered document" refusal reads `render/architecture.md`'s
    mere presence, so a stale render would let `enrich` compose a brief
    from a document describing code that no longer exists rather than
    guiding the user back to `render` first."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    assert (tmp_path / "render" / "architecture.md").is_file()

    assert (
        runner.invoke(
            cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
        ).exit_code
        == 0
    )
    assert not (tmp_path / "render").exists()

    # `enrich` reads render/architecture.md's presence to decide whether it
    # can compose a brief at all — with the stale directory gone, it refuses
    # loudly and names `render`, exactly as it does for a workspace that was
    # never rendered at all.
    result = runner.invoke(
        cli, ["module", "enrich", str(FIXTURE), "--workspace", str(tmp_path), "--dry-run"]
    )
    assert result.exit_code != 0
    assert "sextant module render" in result.output


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


def test_a_malformed_sextant_yml_is_reported_as_a_message_not_a_stack_trace(tmp_path: Path):
    """A `.sextant.yml` Sextant refuses is a mistake in the analysed
    repository, and the analysed repository belongs to the person running the
    command — so it reaches them as the CLI's own error, the same way "no
    analysis found" does. A traceback here would report a user's typo as a
    crash in the tool, and the message that says which key is wrong would be
    buried in it.

    Written into a COPY of the fixture, never the fixture itself: this suite's
    other tests read that directory and a stray config file would follow them
    around."""
    module = tmp_path / "module"
    module.mkdir()
    (module / "pom.xml").write_text(
        (FIXTURE / "pom.xml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (module / ".sextant.yml").write_text(
        "extract_libaries: [com.example:orders-soap-client]\n", encoding="utf-8"
    )

    result = CliRunner().invoke(
        cli, ["module", "analyze", str(module), "--workspace", str(tmp_path / "ws")]
    )

    assert result.exit_code == 1
    assert "extract_libaries" in result.output
    assert "extract_libraries" in result.output
    assert "Traceback" not in result.output
    # 2M Task 1: detection now runs before the workspace is created at all, so
    # a refused detection must leave no trace of one — today's order created
    # `ws/` (and `ws/workspace.duckdb`) via `DuckDbWorkspace.__init__` before
    # the detector's own refusal was ever reached.
    assert not (tmp_path / "ws").exists()


def test_allow_resolve_flag_reaches_the_detector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The CLI's own half of 2M Task 1's plumbing: `--allow-resolve` must
    reach the detector `analyze` selects, not stop at the command's own
    argument parsing. Spies on `MavenDetector.detect` itself rather than on
    any Sextant-internal wiring, so the pin is about the value a real detector
    receives."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    calls: list[bool] = []
    original = MavenDetector.detect

    def spy(self: MavenDetector, path: Path, allow_resolve: bool = False):
        calls.append(allow_resolve)
        return original(self, path, allow_resolve=allow_resolve)

    monkeypatch.setattr(MavenDetector, "detect", spy)

    result = CliRunner().invoke(
        cli,
        ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path), "--allow-resolve"],
    )

    assert result.exit_code == 0, result.output
    assert calls
    assert all(call is True for call in calls)


def test_allow_resolve_defaults_to_false_when_the_flag_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    calls: list[bool] = []
    original = MavenDetector.detect

    def spy(self: MavenDetector, path: Path, allow_resolve: bool = False):
        calls.append(allow_resolve)
        return original(self, path, allow_resolve=allow_resolve)

    monkeypatch.setattr(MavenDetector, "detect", spy)

    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert calls
    assert all(call is False for call in calls)


def test_analyze_writes_an_empty_detect_notes_list_for_a_plain_maven_fixture(tmp_path: Path):
    """`detect_notes` is a key that is always present (empty where the
    detector had nothing to remark on), not one that appears only once a note
    exists — a reader parsing `metadata.json` must never special-case a
    missing key."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["detect_notes"] == []


def test_a_malformed_overlay_is_reported_as_a_message_not_a_stack_trace(tmp_path: Path):
    """The overlay is a program artifact (2K design §6), so a malformed one is
    Sextant's own output written wrong — but the person who has to act on it
    is still the one running the command, and a traceback would report it as a
    crash in the tool. The message names the file and the offending field.

    Written into its own directory, never the fixture: the fixture ships a
    VALID golden overlay that the rest of the suite pins, and a broken one
    left beside it would follow every other test around.

    The workspace here is a stand-in — the overlay is read BEFORE the database
    is opened, so a render that refuses one never touches it. That ordering is
    the point: an overlay that cannot be validated is not a document to render
    half of."""
    module = tmp_path / "module"
    module.mkdir()
    (module / ".sextant-enrichment.json").write_text(
        '{"produced_by": {}, "claims": []}', encoding="utf-8"
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "metadata.json").write_text(
        json.dumps({"module": {"id": "a:module", "kind": "service", "languages": ["java"]}}),
        encoding="utf-8",
    )
    (workspace / "workspace.duckdb").write_bytes(b"")

    result = CliRunner().invoke(
        cli, ["module", "render", str(module), "--workspace", str(workspace)]
    )

    assert result.exit_code == 1
    assert ".sextant-enrichment.json is not a valid overlay" in result.output
    assert "instructions_hash" in result.output
    assert "Traceback" not in result.output


def test_a_redaction_rule_that_breaks_a_claim_is_a_message_at_the_render_exit(tmp_path: Path):
    """The third refusal in this family (2K Task 3 review): a `.sextant.yml`
    whose `redact:` widens far enough to eat a claim's own required fields.
    It cannot be caught at load — the rule set is valid, the overlay is valid,
    and only the two MEETING at the exit fails — so it surfaces where it
    happens, as a message naming the claim rather than a traceback.

    The module root here carries only the two files that decide the outcome —
    the widened `redact:` and a copy of the fixture's own golden overlay —
    while the graph is the fixture's, analysed once. `render` reads its rows
    from `--workspace` and its configuration from the module path, so the two
    can legitimately be different directories, and this is the cheapest way to
    put a real claim in front of a pathological rule."""
    workspace = tmp_path / "ws"
    analyzed = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(workspace)]
    )
    assert analyzed.exit_code == 0, analyzed.output

    module = tmp_path / "module"
    module.mkdir()
    (module / ".sextant-enrichment.json").write_text(
        (FIXTURE / ".sextant-enrichment.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (module / ".sextant.yml").write_text(
        "redact:\n  value_patterns:\n    - llm\n", encoding="utf-8"
    )

    result = CliRunner().invoke(
        cli, ["module", "render", str(module), "--workspace", str(workspace)]
    )

    assert result.exit_code == 1
    assert "a redaction rule rewrote enrichment claim 0" in result.output
    assert "Traceback" not in result.output


def test_a_missing_home_directory_is_reported_as_a_message_not_a_stack_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`ToolExecutor.__init__` (2K Task 7 fix round 3) calls `Path.home()`,
    which raises `RuntimeError` — not `ValueError` — when no home directory
    can be resolved (a container image with no `HOME` set, above all). Before
    2K Task 8's review, `_tool_executor_for` caught `ValueError` alone, so
    this would have escaped as an uncaught crash rather than reaching the
    operator as the same kind of message every other jail-construction
    refusal already gets.

    A direct unit test of `_tool_executor_for` rather than a full `module
    enrich` invocation: the jailed roots just need to exist and sit under
    the repository root `IgnoreRules.load` reads, which `tmp_path` alone
    already satisfies — no fixture compile required."""
    (tmp_path / "facts").mkdir()
    (tmp_path / "render").mkdir()

    def _no_home() -> Path:
        raise RuntimeError("could not determine the user's home directory")

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))

    with pytest.raises(click.ClickException) as excinfo:
        _tool_executor_for(tmp_path, tmp_path, Redactor.from_rules())
    assert "could not determine the user's home directory" in str(excinfo.value)
