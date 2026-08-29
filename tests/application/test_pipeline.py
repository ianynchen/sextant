import json
import subprocess
from pathlib import Path

from shape_helpers import ORDER_REQUEST, ORDER_STATUS, shape_fields_of

from sextant.application.ports.catalogs import Catalog, CatalogSource
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.cli.resources import catalogs_dir, extractor_jar
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
JAR = extractor_jar()
FIXTURE = REPO / "fixtures" / "orders-service"
CATALOGS = catalogs_dir()


class _Catalogs:
    """A CatalogSource over catalogs a test built by hand — the seam D02 §6
    exists for, used here so a test can put an invented catalog beside a
    shipped one without writing a YAML file."""

    def __init__(self, catalogs: list[Catalog]) -> None:
        self._catalogs = catalogs

    def load(self) -> list[Catalog]:
        return self._catalogs


def _resolved_fixture(
    tmp_path: Path, catalogs: CatalogSource | None = None
) -> tuple[DuckDbWorkspace, ResolveReport]:
    """Compile, scan and resolve the fixture — the whole path, on real
    bytecode. The workspace is handed back open: the rows the report points at
    are read from it, and closing it here would take them with it."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    facts = tmp_path / "facts"
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders-service",
            coordinates="com.acme/orders-service",
            version="1.0.0",
            classes_dir=FIXTURE / "target" / "classes",
            out_dir=facts,
        )
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(
        workspace,
        facts,
        catalogs or YamlCatalogSource(CATALOGS),
        {"annotation_args", "typed_signatures", "type_annotations"},
    )
    return workspace, report


def _spring_web() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")


def test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end(tmp_path: Path):
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()

    routes = {(e["method"], e["path"]) for e in report.endpoints}
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders/{id}/{view}"),
        ("GET", "/v1/orders"),
        # The one endpoint whose request and response are both real payloads:
        # `OrderRequest` in, `ResponseEntity<OrderView>` out.
        ("POST", "/v1/orders/detailed"),
        # OrderPageController: a `@Controller`, not `@RestController` — the
        # spring-mvc catalog's own two routes, prefixed by its class-level
        # `@RequestMapping`.
        ("GET", "/orders"),
        ("POST", "/orders/new"),
        # LegacyOrderController: the pre-4.3 form, invisible until the mapping
        # declaration replaced one-annotation-per-method (D02 §2). The `path`
        # alias is read here too — reading `value` alone gave an empty path.
        ("GET", "/v1/legacy/orders"),
        ("PUT", "/v1/legacy/orders/{id}"),
        ("PATCH", "/v1/legacy/orders/{id}"),
        # `@RequestMapping` naming no method accepts every one of them, and each
        # is its own wire contract, so each is its own endpoint.
        *(
            (verb, "/v1/legacy/orders/any")
            for verb in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE")
        ),
        # Outbound (Phase 2B): the client interfaces' declared calls.
        ("POST", "/billing/invoices"),
        ("GET", "/billing/invoices"),
        ("GET", "/v1/inventory/levels"),
        ("POST", "/v1/inventory/reserve"),
        ("GET", "legacy/invoices/{id}"),
        ("POST", "legacy/invoices"),
    }
    # One row per mapped method, not one per (method, same-named sibling) pair:
    # the fixture's two `get` overloads share a name, and a symbol that does not
    # disambiguate them (D00 §1) makes this join multiply instead of match.
    # POST /v1/orders is both a handler and a caller (OrdersLoopClient's
    # self-call): the outbound engine derives its own row for it, and the
    # D02 §3 merge folds that into the existing inbound row (direction
    # `both`) rather than keeping both, so the count is 18 inbound + 7
    # outbound rows derived, minus the 1 that merges away.
    assert len(report.endpoints) == 24
    assert report.skipped_catalogs == []

    directions = {(e["method"], e["path"]): e["direction"] for e in report.endpoints}
    assert directions[("POST", "/billing/invoices")] == "outbound"
    assert directions[("POST", "/v1/orders")] == "both"  # the self-call merged
    peers = {e["path"]: e["peer"] for e in report.endpoints if e["direction"] != "inbound"}
    assert peers["/billing/invoices"] == "billing"
    assert peers["/v1/inventory/levels"] is None  # base URL is builder code


def test_an_endpoint_carries_the_request_and_response_shapes_it_declares(tmp_path: Path):
    workspace, report = _resolved_fixture(tmp_path)
    endpoint = next(
        e for e in report.endpoints if e["method"] == "POST" and e["path"] == "/v1/orders/detailed"
    )

    assert json.loads(endpoint["request_shape"]) == {
        "nullable": True,
        "shape_id": "com/acme/orders/contracts/OrderRequest#",
        "wire_format": "",
        "wire_type": "object",
    }
    fields = shape_fields_of(workspace, json.loads(endpoint["request_shape"])["shape_id"])
    assert "customer_id" in [f["wire_name"] for f in fields]
    # The response is a declared envelope around the payload; the shape must
    # root at what the envelope holds, or the wrapper declarations did nothing.
    assert json.loads(endpoint["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderView#"
    )
    workspace.close()


def test_an_endpoint_whose_response_is_a_collection_records_its_element_shape(tmp_path: Path):
    """List<OrderResult> was 2A's parked gap: the endpoint said nothing at
    all. The descriptor keeps the array-ness — it IS the wire contract — and
    points at the element's shape, all the way through on real bytecode."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    listing = next(
        e for e in report.endpoints if e["path"] == "/v1/orders" and e["method"] == "GET"
    )

    descriptor = json.loads(listing["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/OrderResult#"


def test_an_outbound_endpoints_collection_response_resolves_to_the_real_client_interface(
    tmp_path: Path,
):
    """BillingClient's `List<OrderView> ...` is Phase 2B's outbound payoff:
    the Feign catalog derives the *route* — on real bytecode, no other
    catalog's annotations match `@FeignClient`/`@GetMapping` here. Which
    outbound catalog's rules go on to compute the *descriptor* is not
    pinned down by this route (Task 7 review, Finding 1: ownership is
    direction-scoped, not catalog-scoped, so any outbound catalog may
    answer any outbound row) — moot for this one, since a bare `List` needs
    no wrapper any of the three outbound catalogs declares differently. What
    this test actually exercises end to end is the collection-descriptor
    path itself, on an outbound row, on real bytecode — the same path that
    already serves inbound endpoints, now proven to reach one the module
    calls rather than exposes."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    invoices = next(
        e for e in report.endpoints if e["method"] == "GET" and e["path"] == "/billing/invoices"
    )

    descriptor = json.loads(invoices["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_a_scalar_response_is_recorded_rather_than_dropped(tmp_path: Path):
    """A server-rendered view name has no field list to compare, but NULL is
    reserved for exactly one meaning — no payload — so a scalar response is a
    real contract, recorded rather than silently dropped (D01 §5)."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    rendered = next(e for e in report.endpoints if e["path"] == "/orders" and e["method"] == "GET")

    assert json.loads(rendered["response_shape"])["wire_type"] == "string"
    # Nothing annotated the request body either, so there is no root at all.
    assert rendered["request_shape"] is None


def test_only_the_fixtures_payload_fields_reach_the_request_contract(tmp_path: Path):
    """On real bytecode, the whole way through. Every field of the fixture's
    request class is public and typed; what separates a contract term from a
    constant bound to the type or a field declared not serialized is nothing
    the shape pass can see for itself — so a regression anywhere along the
    chain publishes a contract nobody wrote, and D02 §4 makes the fixture the
    place that is caught."""
    workspace, _ = _resolved_fixture(tmp_path)
    names = [f["wire_name"] for f in shape_fields_of(workspace, ORDER_REQUEST)]
    workspace.close()

    assert "SOURCE" not in names
    assert "cachedSummary" not in names
    # The fields that are on the wire are all still there, in declaration order.
    assert names == [
        "reference",
        "note",
        "customer_id",
        "note2",
        "customer",
        "alternates",
        "total",
        "total_amount",
        "status",
    ]


def test_an_enumeration_typed_field_is_mapped_rather_than_expanded(tmp_path: Path):
    """`OrderStatus` is scanned like any other contract type, and expanding it
    structurally would put `NEW` and `DONE` on the wire as payload fields.
    D00 §5b keeps `enum` in the vocabulary so the whole type is one value."""
    workspace, report = _resolved_fixture(tmp_path)
    status = next(
        f for f in shape_fields_of(workspace, ORDER_REQUEST) if f["wire_name"] == "status"
    )
    shapes = [s["shape_id"] for s in workspace.query("shapes")]
    workspace.close()

    assert status["wire_type"] == "enum"
    assert ORDER_STATUS not in shapes
    # Nothing is missing from the catalog, so nothing is reported: the gap list
    # is only useful while everything on it is actionable.
    assert ORDER_STATUS not in report.unexpanded_types


def test_the_report_names_the_types_expansion_could_not_open(tmp_path: Path):
    """A catalog grows from observation, so a type nothing could expand is
    reported by name (FR-17) — a count cannot be acted on."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()

    assert "org/springframework/http/HttpHeaders#" in report.unexpanded_types
    assert [s["shape_id"] for s in report.shapes]


def test_a_catalog_skipped_by_capability_gating_contributes_no_shapes(tmp_path: Path):
    """The shape pass gates on exactly what the endpoint pass gates on. This
    catalog runs first and would rename nothing and ignore nothing, so if it
    reached the payload at all it would settle `OrderRequest` with its source
    field names — a shape produced by a catalog the run already reported as
    skipped."""
    ungated = Catalog(
        **{
            **vars(_spring_web()),
            "id": "invented-demanding",
            "requires": ("constant_propagation",),
            "serialization": {},
        }
    )
    workspace, report = _resolved_fixture(tmp_path, _Catalogs([ungated, _spring_web()]))
    names = [f["wire_name"] for f in shape_fields_of(workspace, ORDER_REQUEST)]
    workspace.close()

    assert SkippedCatalog("invented-demanding", ("constant_propagation",)) in (
        report.skipped_catalogs
    )
    assert "customer_id" in names
    assert "internalTrace" not in names


def test_a_catalog_that_names_no_request_body_rule_claims_no_request_shape(
    tmp_path: Path,
):
    """Which annotation marks the request payload is framework knowledge, so a
    catalog that declares none contributes no request shapes — inferring one
    from a parameter's position would be a guess presented as an observation."""
    silent = Catalog(
        **{
            **vars(_spring_web()),
            "matches": {
                key: value for key, value in _spring_web().matches.items() if key != "request_body"
            },
        }
    )
    workspace, report = _resolved_fixture(tmp_path, _Catalogs([silent]))
    workspace.close()
    endpoint = next(e for e in report.endpoints if e["path"] == "/v1/orders/detailed")

    assert endpoint["request_shape"] is None
    # The response is rooted from the return type, which no catalog field
    # names, so it is unaffected.
    assert json.loads(endpoint["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderView#"
    )


def test_two_runs_agree_on_every_shape_and_every_field(tmp_path: Path):
    """`content_hash` is derived from the ordered field list, so two runs that
    disagree on field order are two different answers about the same type
    (NFR-1) — and DR-5 compares the answer, not the type."""
    first, second = _resolved_fixture(tmp_path / "one"), _resolved_fixture(tmp_path / "two")

    assert first[0].query("shapes") == second[0].query("shapes")
    assert first[0].query("shape_fields") == second[0].query("shape_fields")
    assert first[1].unexpanded_types == second[1].unexpanded_types
    first[0].close()
    second[0].close()


def test_resolve_reports_the_skip_instead_of_crashing_when_no_catalog_is_satisfied(
    tmp_path: Path,
):
    """A weaker scanner must degrade visibly: when capability gating skips
    every catalog, resolve() still returns a ResolveReport naming what was
    skipped and why, rather than raising because the endpoints table was
    never derived (the one path capability gating exists to protect)."""
    facts = tmp_path / "facts"
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(facts / "OrderController.jsonl", document, [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(workspace, facts, YamlCatalogSource(CATALOGS), {"typed_signatures"})
    workspace.close()

    assert report.endpoints == []
    assert (
        SkippedCatalog("spring-web", ("annotation_args", "type_annotations"))
        in report.skipped_catalogs
    )
