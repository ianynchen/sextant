import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import compile_fixture
from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScannerProvenance, ScanReport, ScanRequest
from sextant.application.stages.analyze import analyze
from sextant.cli.app import cli
from sextant.domain.factfile import read_fact_tree
from sextant.domain.symbols import bare_descriptor, owner_of
from sextant.domain.version import FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import catalogs_dir, extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The facilities a fixture workspace's documents claim (D02 §3: capabilities and
# provenance are SCANNER-declared). One entry with libraries, one without, so a
# test exercises both shapes: only a facility running third-party code that can
# move independently of Sextant records versions at all.
SCANNERS = (
    ScannerProvenance("sextant-detector"),
    ScannerProvenance("sextant-jvm-extractor", ("org.ow2.asm:asm:9.10.1",)),
)


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


def test_analyze_writes_metadata_and_reports_endpoint_count(analyzed_orders_service: Path):
    metadata = json.loads((analyzed_orders_service / "metadata.json").read_text())
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
    # + 8: 2O Task 6's Spring Data REST surface. `CatalogRepository`
    # declares no path, no verb and no HTTP anything, and the framework
    # serves six CRUD routes for it plus two `/search/` routes (one renamed
    # by `@RestResource(path = "by-customer")`). `SecretRepository`
    # (`exported = false`) and `OrderRepository` (which extends the
    # fixture's OWN `Repository<T, ID>` stand-in, not a Spring Data
    # contract) each derive nothing — the live near-miss beside the live
    # match.
    # + 1 (OI-47): `GET /api/orders/{id}`. The mapping is declared on the
    # interface and reachable only through javac's bridge, since the covariant
    # override's descriptor is not the interface's — it used to be discarded
    # with the bridge, and is now carried across to the real override.
    # + 1 (OI-48): `POST /v1/orders/scoped`. `ScopedRequest` was referenced by
    # nothing, so no endpoint rooted it and the package-scope nullability rule was
    # never exercised in the pipeline — only in a hand-built unit test.
    # + 4 (W26): `/v1/paged/totals`, `/orders`, `/slice` and `/wrapped`. `totals` is a
    # payload type whose wire contract is in its ACCESSORS — an interface, so it has no
    # fields at all — and the three paged ones are the boundary beside it: `Page` and
    # `Slice` live in a jar this fixture names in no `extract_libraries`, so their shapes
    # stay open with zero fields and the types are reported as ones nothing could expand.
    # + 3 (W28): `RoutingConditionsController`'s three handlers on one path and verb,
    # separated by `params` and by `headers`. Spring registers all three — they are
    # different mappings — and they are here because six repositories contained no use of
    # either attribute, so nothing else exercises the discriminators the conflict
    # detector reads.
    # 54 since W44: the three `/mvcfn` Spring MVC functional routes (`G-29`) — inbound
    # http rows like any other, derived by the combinator engine rather than an
    # annotation.
    # 60 since `G-45`: `ShipmentRepository`, a `MongoRepository` behind
    # `@RepositoryRestResource`, derives its six-route table — Spring Data REST exposes
    # a Mongo repository exactly as it does a JPA one, and the roster now names the store
    # contract the fact stream cannot reach through the parent.
    # 78 since `G-37` (A1 Task 4): the eighteen builder-form routes on both stacks —
    # `BuilderRoutes` under `/bld`, `MvcBuilderRoutes` under `/mvcbld`, one `GET /**` each.
    # 87 since A1 Task 5 (`W44-verb-overloads`, `GAP-1b`): the Kotlin router DSL's nine
    # routes on both stacks — `KotlinMvcRoutes` under `/ktmvc`, `KotlinWebFluxRoutes`
    # under `/ktflux`, one `GET /**` each.
    # 88 since A1 Task 5's review: the `accept(JSON) { h }` gap row (`dsl-media-route`),
    # `unresolved` with no address.
    # 90 since the A1 final review (I-1): the Supplier form of `nest` on both stacks —
    # `GET /bld/sup/inner`, `GET /mvcbld/sup/inner` — each once, under its prefix.
    # 91 since B/C Task 10 (`jakarta-jaxrs.yml`): `KotlinOrderResource#create`,
    # `POST /kt/orders` — the same address `KotlinOrderRoutes#ktRoutes`'s own
    # functional-routing row already serves, so the route SET is unchanged and only
    # the row count moves.
    # 92 since spec 2026-09-19 §4a: `GET /kt/extra` — `coRouter { extra() }`, a helper
    # call the combinator now follows into the DSL-receiver extension.
    # 94 since spec 2026-09-19 §5b: `GET /v1/params/search` and `GET /ktparams/search`,
    # the two handlers carrying every parameter-annotation form the binder rule reads
    # (`RequestParamsController`, `KotlinParamController`) — one row each, their
    # requirements in `endpoint_metadata` rather than in this count.
    # 96 since spec 2026-09-19 §5c: `GET /v1/conditions/orders` and `GET /v1/conditions/legacy`
    # (`MappingConditionsController`), the two handlers carrying every `params=`/`headers=`
    # expression form — one row each, the expressions in `endpoint_metadata`.
    assert metadata["endpoints"]["inbound"]["http"] == 96
    assert metadata["endpoints"]["inbound"]["sse"] == 2


def test_analyze_document_count_matches_the_real_compiled_and_source_files(
    analyzed_orders_service: Path,
):
    """IMPORTANT A fix (Task 4 review round 1): compiled-origin declared_shape
    facts used to be written into a NEW fact file that re-emitted their own
    `Document` header, so a document that already had one fact file (every
    compiled class) counted twice in `coverage.documents` — 87 for 84 real
    documents. Pinned from a live run, not computed by hand, so any future
    regression that mints a second Document record for an existing document
    is caught here directly rather than only inferred from row counts
    elsewhere."""
    metadata = json.loads((analyzed_orders_service / "metadata.json").read_text())
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
    # + 2: 2O Task 3's generic-superinterface fixture — `Repository<T, ID>` and
    # `OrderRepository`, each its own class file, one document each.
    # + 1: 2O Task 6's `module` fact (D00 §5), which the detector's own
    # conclusions now travel as. Its document is SYNTHESIZED rather than read
    # from a file — the stage may not touch the filesystem — so it is the one
    # document here that is not a class file or a resource; the count moves
    # because the fact tree genuinely gained a record, which is what this test
    # is for.
    # + 2: the same task's Data REST fixture — `CatalogRepository` and
    # `SecretRepository`, one class file each.
    # + 7: 2Q `G3`'s dispatch fixture (`com/acme/orders/trace/`) — one caller
    # and one call per dispatch form the JVM has, which needs an interface with
    # ONE implementation, an interface with TWO, and a subclass that hides a
    # static rather than overriding it: `Refiner`, `SoleRefiner`,
    # `StrictRefiner`, `Splitter`, `FirstSplitter`, `SecondSplitter`,
    # `TraceProbe`. Unannotated and unreferenced, so they move this count and
    # nothing else.
    # + 2 (OI-48): `springscoped/SpringScopedDetail` and its `package-info`, a
    # package declaring itself non-null in SPRING's spelling rather than
    # JSpecify's — the one a Spring codebase actually writes, and the one
    # `shape-models/json.yml` did not declare.
    # + 3: that entry's own review — `apiscoped/package-info` declaring
    # `@NonNullApi` ALONE (which scopes parameters and returns, never fields) plus
    # its `ApiScopedDetail`, and `springscoped/nested/NestedScopedDetail`, a
    # SUBpackage of a scoped package, which inherits no scope from its parent.
    # Both fields must come out nullable, and both were coming out not-null.
    # + 3: W21's `com/acme/orders/model/` — `BaseEntity`, `Customer` and
    # `CustomerRegistry`, giving the always-on corpus the superclass-call shape it
    # scored ZERO of, so Wave 3's resolution work has somewhere to fail.
    # + 2 (W26): `contracts/OrderTotals`, the fieldless interface whose accessors carry
    # its wire contract, and the `PayloadShapeController` that returns it beside the
    # three paged responses no jar here can expand.
    # + 1 (W28): `RoutingConditionsController`.
    # + 1 (W43): `ws/OrderStompPublisher`, the outbound half of the STOMP surface — the
    # module received STOMP and sent none, so `G-33`'s asymmetry had no live instance here.
    # + 2 (W44): `mvcroutes/MvcInvoiceRoutes` and its handlers — Spring MVC functional
    # routing, `G-29`, which this fixture likewise had no instance of.
    # + 1 (W45): `ws/StompBrokerConfig`, which registers the URL a STOMP client opens —
    # `G-42`: the destinations derived and the transport endpoint did not exist.
    # + 1 (W46): `ws/OrderFeedClient`, which opens one — `G-32`'s absent direction.
    # 139 since 2026-09-11: `ProgrammaticWsConfig` + its nested `TicketEndpoint` (`G-34`),
    # `ShipmentRepository` + its nested `Shipment` (`G-45`) — four class files.
    # 141 since `G-37` (A1 Task 4): `routes/BuilderRoutes` and `mvcroutes/MvcBuilderRoutes`.
    # 143 since A1 Task 5: `mvcroutes/KotlinMvcRoutes` and `routes/KotlinWebFluxRoutes` —
    # one class file each, every lambda in them an `invokedynamic` body of the same class.
    # 144 since A2 Task 2: `messaging/OrderPoller` — one class file, its four options
    # lambdas `invokedynamic` bodies of the same class.
    # 146 since A2 Task 8: `httpclient/JdkOrdersClient` and `httpclient/ApacheOrdersClient`
    # — one class file each; the Apache response-handler lambdas are `invokedynamic`
    # bodies of the same class.
    # 148 since Groups B and C Task 1: `jaxrs/KotlinOrderResource` and its nested
    # `KotlinOrderResource$KtOrder` — one class file each, one document each.
    # 150 since spec 2026-09-19 §4a: `routes/KotlinOrderRoutesKt`, the file facade the
    # top-level `extra()` helper compiles into, and `KotlinOrderRoutesKt$extra$1`, its
    # suspend handler's class — one class file each.
    # 152 since spec 2026-09-19 §5b: `RequestParamsController` and
    # `mvcroutes/KotlinParamController` — one class file each.
    # 153 since spec 2026-09-19 §5c: `MappingConditionsController`, one class file.
    assert metadata["coverage"]["documents"] == 153


def test_receipt_avsc_reaches_the_graph_as_a_source_only_declared_shape(
    analyzed_orders_service: Path,
):
    """IMPORTANT B (Task 4 review round 1): `receipt.avsc` is this fixture's
    one schema identity with no compiled counterpart —
    `fixtures/orders-service/pom.xml`'s avro-maven-plugin `<excludes>` block
    keeps the jar from ever embedding it. Pinned end to end, through the real
    CLI command and the real fact tree it writes, so silently deleting that
    `<excludes>` block (making Receipt compiled again, and DR-4 drop the
    source shape this test expects) fails a test rather than only a stale
    fixture comment."""

    shapes = [
        fact
        for _, _, facts in read_fact_tree(analyzed_orders_service / "facts")
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
    compile_fixture(FIXTURE)
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


def test_export_writes_a_bundle_with_manifest_graph_and_facts(analyzed_workspace_copy: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "graph" / "endpoints.parquet").is_file()
    facts_files = list((bundle / "facts").rglob("*.parquet"))
    assert facts_files, "facts/ must not be empty"


def test_render_writes_the_document_after_analyze(analyzed_workspace_copy: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
    assert result.exit_code == 0, result.output
    document = (analyzed_workspace_copy / "render" / "architecture.md").read_text()
    assert "POST" in document and "/v1/orders" in document


def test_render_also_writes_a_self_contained_offline_html_document(analyzed_workspace_copy: Path):
    """2K design §6b, the live pin over a real analysed module rather than a
    synthetic one: `architecture.html` lands beside `architecture.md`, wraps
    the real structure diagram in pan-zoom controls, and carries no CDN or
    external script URL."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
    assert result.exit_code == 0, result.output
    html_path = analyzed_workspace_copy / "render" / "architecture.html"
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
    compile_fixture(FIXTURE)
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


def test_export_carries_both_rendered_documents_into_the_bundle(analyzed_workspace_copy: Path):
    """The bundle carries what `render` already wrote (2K design §6b) — copied
    verbatim rather than re-rendered, so the bundle and the workspace can
    never disagree about what a reader saw."""
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
        ).exit_code
        == 0
    )
    result = runner.invoke(
        cli, ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    assert (bundle / "render" / "architecture.md").read_bytes() == (
        analyzed_workspace_copy / "render" / "architecture.md"
    ).read_bytes()
    assert (bundle / "render" / "architecture.html").read_bytes() == (
        analyzed_workspace_copy / "render" / "architecture.html"
    ).read_bytes()
    # The manifest declares what it shipped (2K Task 8 review, D06 §3):
    # `render/` joins `facts`/`graph`/`tables`/`facts_files` as content the
    # manifest names rather than leaves for a consumer to discover by
    # listing the bundle itself.
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contents"]["render"] == ["architecture.md", "architecture.html"]


def test_export_without_a_prior_render_carries_no_render_directory(analyzed_workspace_copy: Path):
    """`render` is not a prerequisite for `export` (M08: export only ever
    reads what `analyze` left) — a workspace that skipped it must still
    export cleanly, exactly as it did before this task."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
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
    compile_fixture(FIXTURE)
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
    compile_fixture(FIXTURE)

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
            SCANNERS,
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


def test_analyze_reports_nothing_uncovered_now_that_the_nested_class_is_read(
    analyzed_workspace_copy: Path,
):
    """The fixture's nested class was this module's one compiled source the
    facts did not account for, and `uncovered` existed to say so. It is scanned
    now (D00 §2 — one class file is one document), so the honest answer is an
    empty list and a gap section that names no unread source. The channel is
    still load-bearing — a Kotlin class whose metadata cannot be decoded still
    travels it — which is why the assertion is that it is empty here, not that
    it is gone."""
    runner = CliRunner()
    metadata = json.loads((analyzed_workspace_copy / "metadata.json").read_text())
    assert metadata["uncovered"] == []

    assert (
        runner.invoke(
            cli, ["module", "render", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
        ).exit_code
        == 0
    )
    document = (analyzed_workspace_copy / "render" / "architecture.md").read_text()
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
    compile_fixture(FIXTURE)
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
    compile_fixture(FIXTURE)
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


def test_analyze_writes_an_empty_detect_notes_list_for_a_plain_maven_fixture(
    analyzed_orders_service: Path,
):
    """`detect_notes` is a key that is always present (empty where the
    detector had nothing to remark on), not one that appears only once a note
    exists — a reader parsing `metadata.json` must never special-case a
    missing key."""
    metadata = json.loads((analyzed_orders_service / "metadata.json").read_text())
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
    half of.

    The stand-in carries the three version stamps a real `metadata.json` does
    (OI-24, D01 §7): the read gate compares them before the overlay is read at
    all, so a stand-in without them is refused as a workspace from another
    build and this test would pin that refusal instead of the overlay one."""
    module = tmp_path / "module"
    module.mkdir()
    (module / ".sextant-enrichment.json").write_text(
        '{"produced_by": {}, "claims": []}', encoding="utf-8"
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "metadata.json").write_text(
        json.dumps(
            {
                "module": {"id": "a:module", "kind": "service", "languages": ["java"]},
                "schema_version": GRAPH_SCHEMA_VERSION,
                "provenance": {
                    "sextant_version": SEXTANT_VERSION,
                    "fact_schema_version": FACT_SCHEMA_VERSION,
                },
            }
        ),
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


# (2N Task 6, carry (c)): the missing-home-directory whitebox test that
# lived here moved to `tests/api/test_composition.py`, targeting
# `sextant.api._tool_executor_for` directly, now that `cli/app.py`'s own
# `_tool_executor_for` shim — which existed only to give this test a
# `click.ClickException` to catch — is deleted.


# --- Maven reactor discovery (2M Task 2, fix round 1) ----------------------

REACTOR = REPO / "fixtures" / "orders-reactor"
BILLING_LIB = REACTOR / "billing-lib"


def test_detection_reaches_the_detector_exactly_once_per_analyze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """2M Task 2 review's HARD GATE: Task 1 left a double detect (a pre-flight
    call in `module_analyze` plus `analyze()`'s own internal one) — the exact
    shape a real `GradleDetector` cannot afford, since each call is its own
    `./gradlew` subprocess. `_KnownModuleDetector` closes it: the ONE real
    `MavenDetector.detect` call replays into every per-module `analyze()`
    rather than triggering a second one."""
    compile_fixture(FIXTURE)
    calls: list[Path] = []
    original = MavenDetector.detect

    def spy(self: MavenDetector, path: Path, allow_resolve: bool = False):
        calls.append(path)
        return original(self, path, allow_resolve=allow_resolve)

    monkeypatch.setattr(MavenDetector, "detect", spy)

    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def test_workspace_flag_is_refused_at_a_multi_module_root():
    """`--workspace` names one module's workspace (M00); a multi-module root
    has no single workspace of its own — every module gets its own,
    unconditionally (2M design §2). Read-only up to the refusal (the gate
    fires before any per-module work starts), so the real fixture needs no
    snapshot here."""
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(REACTOR), "--workspace", "/tmp/wherever"]
    )
    assert result.exit_code != 0
    assert "--workspace" in result.output
    assert "multi-module root" in result.output


def test_analyze_at_a_reactor_root_analyzes_every_non_bom_module(tmp_path: Path):
    """Ruled spec amendment (2M Task 2 fix round 1): the original "only
    `service` is analyzed" rule returned ZERO analyzed output against
    `spring-petclinic-microservices` — all eight of its modules classify
    `undetermined` — so the kind gate inverts to skip only what is KNOWN
    not to be a service: `library` (Gradle-only) and a leaf `<packaging>
    pom</packaging>`. `orders-service` and `billing-lib`, both
    `undetermined`, are therefore BOTH analyzed here, each into its own
    workspace. `orders-service` is adopted by the reactor completely
    UNCHANGED, so its endpoint count must match the single-module run
    exactly; `billing-lib`'s `<parent>` resolves offline because its own
    `<relativePath>` reaches the reactor parent's `pom.xml` directly, no
    install required."""
    compile_fixture(FIXTURE)
    compile_fixture(BILLING_LIB)

    # On a COPY of the two fixture trees, side by side so `../orders-service` still
    # resolves from the reactor. The analysis writes `.sextant/` into every module it
    # adopts, and this test used to move the real fixture's `.sextant/` aside and back —
    # sound on one worker, a race on four: `tests/application/test_enrich_tools.py` reads
    # `fixtures/orders-service/.sextant/facts` from another worker for the whole session.
    # `copy2` keeps mtimes, so the copied `target/` is up to date and nothing recompiles.
    fixtures = tmp_path / "fixtures"
    ignore = shutil.ignore_patterns(".sextant", ".sextant-enrichment.json", ".tradewind")
    shutil.copytree(FIXTURE, fixtures / "orders-service", ignore=ignore)
    shutil.copytree(REACTOR, fixtures / "orders-reactor", ignore=ignore)
    orders_service = fixtures / "orders-service"
    reactor = fixtures / "orders-reactor"
    billing_lib = reactor / "billing-lib"

    baseline = CliRunner().invoke(
        cli, ["module", "analyze", str(orders_service), "--workspace", str(tmp_path / "baseline")]
    )
    assert baseline.exit_code == 0, baseline.output
    # `click.echo(json.dumps(...))` is the one line `module analyze` writes
    # to stdout; `RichProgress` writes its own lines to stderr, and
    # `CliRunner` mixes the two streams together — the JSON line is the
    # first one out.
    single_module_endpoints = json.loads(baseline.output.splitlines()[0])["endpoints"]

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])
    assert result.exit_code == 0, result.output
    assert (
        f"analyzed ../orders-service (com.acme:orders-service): "
        f"{single_module_endpoints} endpoints" in result.output
    )
    assert "analyzed billing-lib (com.acme:billing-lib):" in result.output
    # The table (2M Task 2 fix round 1, F8): lowercase `yes`, never
    # Python's capitalized `str(True)`.
    assert "yes" in result.output
    assert "True" not in result.output

    assert (orders_service / ".sextant" / "metadata.json").is_file()
    assert (billing_lib / ".sextant" / "metadata.json").is_file()

    modules_json = reactor / ".sextant" / "modules.json"
    modules = json.loads(modules_json.read_text())["modules"]
    assert modules == sorted(modules, key=lambda row: row["dir"])
    by_dir = {row["dir"]: row for row in modules}
    # Root-relative (2M Task 2 fix round 1, F5), not absolute: stable
    # across however `path` was itself spelled on the command line.
    assert by_dir["../orders-service"] == {
        "dir": "../orders-service",
        "module_id": "com.acme:orders-service",
        "kind": "undetermined",
        "analyzed": True,
        "skip_reason": None,
    }
    assert by_dir["billing-lib"] == {
        "dir": "billing-lib",
        "module_id": "com.acme:billing-lib",
        "kind": "undetermined",
        "analyzed": True,
        "skip_reason": None,
    }

    # `render`/`enrich`/`export` never re-detect (M00); pointed at the
    # reactor root itself — where `modules.json` sits and no workspace
    # ever will, `--workspace` being refused there — they refuse by
    # naming every module `modules.json` lists, root-relative, in the
    # exact pinned form.
    render_result = CliRunner().invoke(cli, ["module", "render", str(reactor)])
    assert render_result.exit_code != 0
    assert (
        f"{reactor} is a multi-module root; analyze it, then run this command against "
        "one of: ../orders-service, billing-lib" in render_result.output
    )


_TRIVIAL_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>{name}</artifactId>
  <version>1.0.0</version>
</project>
"""

_BOM_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>{name}</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
</project>
"""

_ONE_MODULE_REACTOR_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>reactor</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <modules>
    <module>child</module>
  </modules>
</project>
"""

_EMPTY_REACTOR_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>reactor</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <modules>
  </modules>
</project>
"""

_REACTOR_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>reactor</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <modules>
    <module>ok-first</module>
    <module>bad</module>
    <module>ok-second</module>
  </modules>
</project>
"""


def _trivial_service_module(root: Path, name: str, compile_it: bool) -> None:
    root.mkdir()
    (root / "pom.xml").write_text(_TRIVIAL_POM.format(name=name), encoding="utf-8")
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    java = root / "src" / "main" / "java" / "com" / "acme"
    java.mkdir(parents=True)
    class_name = name.replace("-", "_").title().replace("_", "")
    (java / f"{class_name}.java").write_text(
        f"package com.acme;\npublic class {class_name} {{}}\n", encoding="utf-8"
    )
    if compile_it:
        compile_fixture(root)


def _bom_module(root: Path, name: str) -> None:
    root.mkdir()
    (root / "pom.xml").write_text(_BOM_POM.format(name=name), encoding="utf-8")


def test_a_leaf_module_packaged_pom_is_skip_listed_with_that_reason(tmp_path: Path):
    """Ruled spec amendment: a leaf `<packaging>pom</packaging>` (a BOM or
    aggregation-only sibling with no classes to scan) is the one
    kind-independent skip signal — without it, a reactor containing a BOM
    hard-fails the whole run, since the BOM's own scan has no
    `target/classes` directory to read at all."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(
        _REACTOR_POM.replace(
            "<module>ok-first</module>\n    <module>bad</module>\n    <module>ok-second</module>",
            "<module>bom</module>\n    <module>service</module>",
        ),
        encoding="utf-8",
    )
    _bom_module(reactor / "bom", "bom")
    _trivial_service_module(reactor / "service", "service", compile_it=True)

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])

    assert result.exit_code == 0, result.output
    assert "skipped bom (com.acme:bom): packaging is pom" in result.output
    assert "analyzed service (com.acme:service):" in result.output
    modules = json.loads((reactor / ".sextant" / "modules.json").read_text())["modules"]
    by_dir = {row["dir"]: row for row in modules}
    assert by_dir["bom"]["analyzed"] is False
    # 2M Task 7 fix round 1, Critical: the reason lives in the COMMITTED
    # artifact too, not only in this run's own stdout — a reader of
    # `modules.json` alone (`--refresh-stale` orchestration, a later
    # `render`/`enrich`/`export` refusal) must be able to answer "why"
    # without the terminal output that produced it.
    assert by_dir["bom"]["skip_reason"] == "packaging is pom"
    assert by_dir["service"]["analyzed"] is True
    assert by_dir["service"]["skip_reason"] is None


# (2N Task 6, carry (c)): the three `_skip_reason` unit tests that lived
# here moved to `tests/api/test_composition.py`, targeting
# `sextant.api._skip_reason` directly, now that `cli/app.py`'s own
# `_skip_reason = api._skip_reason` re-export — which existed only so this
# file could import a local name — is deleted.


def test_a_one_module_reactor_still_analyzes_into_the_childs_own_workspace(tmp_path: Path):
    """2M Task 2 fix round 1, F1 (HIGH): the multi-module gate is whether the
    root declared `<modules>`, never `len(modules) > 1` — a reactor naming
    exactly ONE child (`fixtures/pom.xml` is this shape today) used to fall
    into the single-module branch, landing the child's analysis in the
    AGGREGATOR's own `.sextant`/`.sextant.yml`/overlay/commit instead of the
    child's."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_ONE_MODULE_REACTOR_POM, encoding="utf-8")
    _trivial_service_module(reactor / "child", "child", compile_it=True)

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])
    assert result.exit_code == 0, result.output

    assert (reactor / "child" / ".sextant" / "metadata.json").is_file()
    assert not (reactor / ".sextant" / "metadata.json").exists()
    modules = json.loads((reactor / ".sextant" / "modules.json").read_text())["modules"]
    assert [row["dir"] for row in modules] == ["child"]

    # `--workspace` is still refused at this root, exactly as a multi-child
    # reactor refuses it.
    refused = CliRunner().invoke(
        cli, ["module", "analyze", str(reactor), "--workspace", str(tmp_path / "ws")]
    )
    assert refused.exit_code != 0
    assert "multi-module root" in refused.output


def test_a_missing_child_pom_reaches_the_cli_as_a_message_not_a_traceback(tmp_path: Path):
    """2M Task 2 fix round 1, F2."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(
        _ONE_MODULE_REACTOR_POM.replace("<module>child</module>", "<module>ghost</module>"),
        encoding="utf-8",
    )
    (reactor / "ghost").mkdir()

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])

    assert result.exit_code != 0
    assert "ghost" in result.output
    assert "no pom.xml" in result.output
    assert "Traceback" not in result.output


def test_a_malformed_child_pom_reaches_the_cli_as_a_message_naming_it(tmp_path: Path):
    """2M final review wave, I2: `ElementTree.ParseError` subclasses
    `SyntaxError`, not `ValueError` — reachable past `MavenDetector`'s own
    `_parse_pom` naming only if some future parse site skips it, and past
    that as an uncaught traceback if the CLI's own catch tuple did not carry
    it too. Either way the reader gets a message naming the broken pom, exit
    1, never a traceback."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_ONE_MODULE_REACTOR_POM, encoding="utf-8")
    (reactor / "child").mkdir()
    (reactor / "child" / "pom.xml").write_text("<project><groupId>oops</project>", encoding="utf-8")

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])

    assert result.exit_code != 0
    assert str(reactor / "child" / "pom.xml") in result.output
    assert "Traceback" not in result.output


def test_a_modules_cycle_reaches_the_cli_as_a_message_not_a_traceback(tmp_path: Path):
    """2M Task 2 fix round 1, F2."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "pom.xml").write_text(
        _ONE_MODULE_REACTOR_POM.replace("<module>child</module>", "<module>../b</module>"),
        encoding="utf-8",
    )
    (b / "pom.xml").write_text(
        _ONE_MODULE_REACTOR_POM.replace("<module>child</module>", "<module>../a</module>"),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["module", "analyze", str(a)])

    assert result.exit_code != 0
    assert "cycle" in result.output
    assert "Traceback" not in result.output


def test_an_empty_reactor_is_refused_by_name_at_detect(tmp_path: Path):
    """2M final review wave, MINOR 4: `<modules/>` naming zero children used
    to analyze successfully with nothing to show (2M Task 2 fix round 1,
    F8's own honest-empty table) — but a `render`/`enrich`/`export` pointed
    at that root afterwards then hit `_refuse_if_unanalyzed`'s reactor
    listing with nothing after "one of: ". Refused at detect instead, by the
    pom that declares the empty `<modules>`, before anything on disk is
    touched."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_EMPTY_REACTOR_POM, encoding="utf-8")

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])

    assert result.exit_code != 0
    assert "declares <modules> but names none" in result.output
    assert "Traceback" not in result.output
    assert not (reactor / ".sextant").exists()


def test_the_table_truncates_a_dir_column_longer_than_the_cap(tmp_path: Path):
    """2M Task 2 fix round 1, F8: the cap keeps the columns after it aligned
    regardless of how long any one module's relative path is — truncation
    is a TABLE concern only, so the per-module progress line above the
    table still carries the name in full."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    long_name = "a-very-long-module-directory-name-" + "x" * 30
    (reactor / "pom.xml").write_text(
        _ONE_MODULE_REACTOR_POM.replace("<module>child</module>", f"<module>{long_name}</module>"),
        encoding="utf-8",
    )
    _trivial_service_module(reactor / long_name, "thing", compile_it=True)

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])

    assert result.exit_code == 0, result.output
    assert "…" in result.output
    assert f"analyzed {long_name} (" in result.output


def test_one_module_failing_in_a_reactor_stops_the_run_and_names_it(tmp_path: Path):
    """One failing module fails loudly and stops the run (`--keep-going` is
    not offered in 2M): `bad` has no compiled `target/classes` at all (never
    built), so its own scan fails — and the failure names `bad`, not a bare
    traceback, and never reaches `ok-second`, which sits after it in
    `<modules>` declaration order."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_REACTOR_POM, encoding="utf-8")
    _trivial_service_module(reactor / "ok-first", "ok-first", compile_it=True)
    _trivial_service_module(reactor / "bad", "bad", compile_it=False)
    _trivial_service_module(reactor / "ok-second", "ok-second", compile_it=True)

    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])

    assert result.exit_code != 0
    assert "bad" in result.output
    assert "Traceback" not in result.output
    assert (reactor / "ok-first" / ".sextant" / "metadata.json").is_file()
    assert not (reactor / "ok-second" / ".sextant").exists()
    # A stopped run leaves no `modules.json` claiming any module beyond the
    # one that failed was ever reached.
    assert not (reactor / ".sextant" / "modules.json").exists()


def test_a_refused_detection_leaves_a_pre_existing_workspace_byte_untouched(tmp_path: Path):
    """Task 1's reorder made detection run before `DuckDbWorkspace` ever
    touches disk (2M design §2); this pins the OTHER direction, which Task 1
    left unpinned — a workspace a PRIOR successful run already wrote is
    never touched by a LATER `analyze` invocation that detection refuses,
    since that refusal is discovered before `workspace_dir` is referenced at
    all."""
    module = tmp_path / "module"
    _trivial_service_module(module, "thing", compile_it=True)
    workspace = tmp_path / "ws"

    first = CliRunner().invoke(
        cli, ["module", "analyze", str(module), "--workspace", str(workspace)]
    )
    assert first.exit_code == 0, first.output
    metadata_before = (workspace / "metadata.json").read_bytes()
    db_before = (workspace / "workspace.duckdb").read_bytes()

    (module / ".sextant.yml").write_text("extract_libaries: [x:y]\n", encoding="utf-8")

    second = CliRunner().invoke(
        cli, ["module", "analyze", str(module), "--workspace", str(workspace)]
    )
    assert second.exit_code != 0

    assert (workspace / "metadata.json").read_bytes() == metadata_before
    assert (workspace / "workspace.duckdb").read_bytes() == db_before
