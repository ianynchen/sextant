from pathlib import Path

import pytest
import yaml

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints
from sextant.cli.resources import catalogs_dir
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = catalogs_dir()

# A second, invented annotation_driven shape — deliberately not Spring — so a
# test can hand `derive_endpoints` two catalogs that are genuinely different.
_INVENTED_LISTENER = Catalog(
    id="invented-listener",
    style="annotation_driven",
    protocol="message",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": "com/acme/messaging/annotation/Listener#",
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "method_from": "method",
            "all_methods": ["PUBLISH"],
            "prefix_annotation": "com/acme/messaging/annotation/Topic#",
            "annotations": [
                {"fqn": "com/acme/messaging/annotation/OnMessage#", "method": ["PUBLISH"]},
            ],
        },
    },
)


def test_catalog_declares_its_style_and_required_capabilities_when_loaded():
    catalogs = YamlCatalogSource(CATALOGS).load()
    spring = next(c for c in catalogs if c.id == "spring-web")
    assert spring.style == "annotation_driven"
    assert spring.protocol == "http"
    assert spring.direction == "inbound"
    assert "annotation_args" in spring.requires


def test_catalog_declares_wrappers_nullability_serialization_and_known_types():
    """D02 §2a, §2e, §2f, §2g: `spring-web` and `spring-mvc` both need these
    four blocks before payload shapes can be derived (Tasks 9-11 read them).
    The loader does not parse them into `Catalog` — they ride along in the
    raw file — so this reads the file directly, the same way the catalog
    itself is the source of truth for `matches`."""
    for name in ("spring-web", "spring-mvc"):
        raw = yaml.safe_load((CATALOGS / f"{name}.yml").read_text(encoding="utf-8"))

        wrapper_types = {w["type"] for w in raw["wrappers"]}
        assert wrapper_types == {
            "org.springframework.http.ResponseEntity",
            "reactor.core.publisher.Mono",
            "reactor.core.publisher.Flux",
            "java.util.concurrent.CompletableFuture",
            "java.util.Optional",
        }

        # The JetBrains entries are not redundant with JSpecify/Spring: the
        # Kotlin compiler emits them directly onto fields as CLASS-retention
        # annotations, so they are what makes Kotlin nullability work through
        # the ordinary annotation path.
        assert "org.jetbrains.annotations.Nullable" in raw["nullability"]["nullable"]
        assert "org.jetbrains.annotations.NotNull" in raw["nullability"]["not_null"]
        assert raw["nullability"]["scope"] == [
            {"annotation": "org.jspecify.annotations.NullMarked", "means": "not_null_by_default"}
        ]

        assert raw["serialization"]["name_from"] == [
            {"annotation": "com.fasterxml.jackson.annotation.JsonProperty", "arg": "value"}
        ]
        assert raw["serialization"]["ignore"] == ["com.fasterxml.jackson.annotation.JsonIgnore"]
        assert raw["serialization"]["default_strategy"] == "as_declared"

        known_types = {t["type"] for t in raw["known_types"]}
        assert known_types == {
            "java.time.Instant",
            "java.time.LocalDate",
            "java.math.BigDecimal",
            "java.util.UUID",
        }


def test_catalog_requires_type_annotations_for_nullability():
    """Nullability comes off `type_annotations`; a catalog that declares
    `nullability` without raising `requires` would run against a scanner
    lacking that capability and silently produce no nullability at all —
    the exact bypass capability gating exists to prevent (FR-17)."""
    catalogs = YamlCatalogSource(CATALOGS).load()
    for catalog_id in ("spring-web", "spring-mvc"):
        catalog = next(c for c in catalogs if c.id == catalog_id)
        assert "annotation_args" in catalog.requires
        assert "type_annotations" in catalog.requires


def test_catalog_maps_post_mapping_to_the_post_method():
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    annotations = spring.matches["mapping"]["annotations"]
    methods = {m["fqn"]: m.get("method") for m in annotations}
    assert methods["org/springframework/web/bind/annotation/PostMapping#"] == ["POST"]


def test_catalog_leaves_request_mapping_without_a_preset_method():
    """`@RequestMapping` takes its method from its own argument, and means every
    method when it has none — so it must declare no default here, or the
    fallback that produces one endpoint per method can never be reached."""
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    annotations = spring.matches["mapping"]["annotations"]
    request_mapping = next(
        m
        for m in annotations
        if m["fqn"] == "org/springframework/web/bind/annotation/RequestMapping#"
    )
    assert "method" not in request_mapping


def _controller_facts(root: Path) -> None:
    """Mirrors the exact shape the ASM extractor emits for a Spring
    controller (verified against fixtures/orders-service): a type-level
    RestController with no argument, a RequestMapping whose `value` is a
    one-element JSON array, one PostMapping and one GetMapping with no
    argument at all, and one GetMapping whose `value` is a one-element
    array. Method symbols carry the descriptor-hash disambiguator D00 §1
    requires on every method, because that is what the extractor writes."""
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
    controller = "com/acme/orders/OrderController#"
    create = "com/acme/orders/OrderController#create(sig_1f0a4c2e)."
    get = "com/acme/orders/OrderController#get(sig_74b3d901)."
    list_ = "com/acme/orders/OrderController#list(sig_08c5be17)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=create,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=get,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=list_,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=create,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/PostMapping#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=get,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": ["/{id}"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=list_,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def test_derive_endpoints_finds_the_three_annotated_routes_when_the_catalog_is_annotation_driven(
    tmp_path: Path,
):
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")

    skipped = derive_endpoints(
        workspace, [spring], capabilities={"annotation_args", "type_annotations"}
    )
    routes = {(e["method"], e["path"]) for e in workspace.query("endpoints")}
    workspace.close()

    assert skipped == []
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }


def _invented_listener_facts(root: Path) -> None:
    """A second, invented annotation_driven shape — deliberately not Spring —
    used only to prove that `protocol` and `direction` on the derived rows
    come from the catalog's own declared fields rather than from a literal
    baked into the SQL. D02 groups Spring Kafka and JMS listeners under this
    same style with `protocol: message`; a catalog like this one is exactly
    what would have silently come out labelled http/inbound before this fix."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/notify/OrderListener.java",
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
    listener = "com/acme/notify/OrderListener#"
    handle = "com/acme/notify/OrderListener#onOrderCreated(sig_3d92af60)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=listener,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/messaging/annotation/Listener#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=listener,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/Topic#",
                args={"value": ["orders."]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/OnMessage#",
                args={"value": ["created"]},
            ),
        ),
    ]
    write_fact_file(root / "OrderListener.jsonl", document, facts)


def test_derive_endpoints_carries_the_catalogs_own_protocol_and_direction_when_non_http(
    tmp_path: Path,
):
    _invented_listener_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    skipped = derive_endpoints(workspace, [_INVENTED_LISTENER], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert len(rows) == 1
    assert rows[0]["protocol"] == "message"
    assert rows[0]["direction"] == "outbound"
    assert rows[0]["protocol"] != "http"
    assert rows[0]["direction"] != "inbound"


def test_derive_endpoints_keeps_both_catalogs_results_when_two_catalogs_match(
    tmp_path: Path,
):
    """D02 §5: "Two catalogs may both match; both produce endpoints, and
    duplicates merge on wire identity." A derivation that replaces the table
    per catalog makes the last catalog the only catalog, and every endpoint
    the earlier ones found disappears with no skip, no gap, and no warning —
    the silent-loss failure capability gating exists to prevent."""
    _controller_facts(tmp_path / "facts")
    _invented_listener_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")

    skipped = derive_endpoints(
        workspace,
        [spring, _INVENTED_LISTENER],
        capabilities={"annotation_args", "type_annotations"},
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert {(r["protocol"], r["method"], r["path"]) for r in rows} == {
        ("http", "POST", "/v1/orders"),
        ("http", "GET", "/v1/orders/{id}"),
        ("http", "GET", "/v1/orders"),
        ("message", "PUBLISH", "orders.created"),
    }


def test_derive_endpoints_merges_on_wire_identity_when_two_catalogs_match_the_same_code(
    tmp_path: Path,
):
    """The other half of D02 §5: accumulating must not double-report. Two
    catalogs that describe the same annotations — the realistic case of a
    framework catalog and its umbrella — see the same routes, and the wire
    is where sameness is decided."""
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    twin = Catalog(**{**vars(spring), "id": "spring-web-twin"})

    derive_endpoints(
        workspace, [spring, twin], capabilities={"annotation_args", "type_annotations"}
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 3


def test_derive_endpoints_skips_and_reports_when_a_required_capability_is_missing(
    tmp_path: Path,
):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    catalog = Catalog(
        id="spring-web",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=("annotation_args",),
        matches={},
        source=Path("tests/needs-a-capability.yml"),
    )

    skipped = derive_endpoints(workspace, [catalog], capabilities=set())
    workspace.close()

    assert skipped == [SkippedCatalog("spring-web", ("annotation_args",))]


def test_derive_endpoints_sql_names_no_framework_when_read():
    """D02's central claim — frameworks are data, engines are generic
    interpreters — is falsified the moment a framework's own identifier
    shows up as a literal in the engine's SQL. A second annotation_driven
    framework must be addable as one YAML file with no change here."""
    sql = (
        Path(__file__).parents[2]
        / "src"
        / "sextant"
        / "storage"
        / "duckdb"
        / "derive_endpoints.sql"
    )
    text = sql.read_text(encoding="utf-8").lower()
    assert "spring" not in text
    assert "org/springframework" not in text


def _scalar_path_facts(root: Path) -> None:
    """A framework whose path arguments are declared `String`, not `String[]`.
    JAX-RS `@Path` is the real one: its `value()` is a plain String, so the
    compiled annotation argument is a bare JSON string and not a one-element
    array."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
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
    resource = "com/acme/rest/OrderResource#"
    find = "com/acme/rest/OrderResource#find(sig_5ea17c38)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=find,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=resource,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Resource#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=resource,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Path#",
                args={"value": "/rest/orders"},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=find,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Get#", args={"value": "/{id}"}),
        ),
    ]
    write_fact_file(root / "OrderResource.jsonl", document, facts)


_SCALAR_PATH_CATALOG = Catalog(
    id="invented-scalar-path",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": "com/acme/rest/Resource#",
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "method_from": "method",
            "all_methods": ["GET"],
            # Not a mapping annotation: this catalog is the JAX-RS shape, where
            # the type carries the path and the method carries the verb.
            "prefix_annotation": "com/acme/rest/Path#",
            "annotations": [{"fqn": "com/acme/rest/Get#", "method": ["GET"]}],
        },
    },
)


def test_derive_endpoints_reads_a_scalar_annotation_argument_when_it_is_not_an_array(
    tmp_path: Path,
):
    """Reading only element 0 of an array silently yields NULL on a scalar, and
    the path collapses to the prefix alone — a wrong route reported with full
    `resolved`/`compiler` confidence. Spring's `value()` is `String[]`, so this
    is invisible there and fatal for any catalog whose argument is a plain
    String."""
    _scalar_path_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_SCALAR_PATH_CATALOG], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("GET", "/rest/orders/{id}")]


def _client_facts(root: Path, type_args: dict[str, object]) -> None:
    """A client interface in the outbound shape D02 §2 (amended) describes: a
    type-level marker that also carries the service name and address prefix
    — the exact @FeignClient hazard the prefix_from/peer_from split exists
    for — and a method-level mapping annotation with no argument beyond its
    own path."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/billing/BillingClient.java",
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
    client = "com/acme/billing/BillingClient#"
    submit = "com/acme/billing/BillingClient#submit(sig_9f1c2b47)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=submit,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=client,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/billing/annotation/ServiceClient#",
                args=type_args,
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=submit,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/billing/annotation/PostExchange#",
                args={"value": ["/invoices"]},
            ),
        ),
    ]
    write_fact_file(root / "BillingClient.jsonl", document, facts)


_OUTBOUND_CATALOG = Catalog(
    id="invented-outbound",
    style="annotation_driven",
    protocol="http",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": "com/acme/billing/annotation/ServiceClient#",
        "request_body": {"annotation": "com/acme/billing/annotation/Body#", "fallback": "none"},
        "mapping": {
            "path_from": ["value"],
            # `path` carries the prefix; `name` (read by peer_from below)
            # never does — the leak the split exists to prevent.
            "prefix_from": ["path"],
            "peer_from": ["name", "value"],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com/acme/billing/annotation/ServiceClient#",
            "annotations": [
                {"fqn": "com/acme/billing/annotation/PostExchange#", "method": ["POST"]},
            ],
        },
    },
)


def _outbound_workspace(tmp_path: Path, type_args: dict[str, object] | None = None):
    args = type_args if type_args is not None else {"name": "billing", "path": "/billing"}
    _client_facts(tmp_path / "facts", args)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_OUTBOUND_CATALOG], capabilities={"annotation_args"})
    assert skipped == []
    return workspace


def test_an_outbound_catalog_produces_caller_rows_with_peer_and_prefixed_path(tmp_path):
    workspace = _outbound_workspace(tmp_path)
    [endpoint] = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert endpoint["path"] == "/billing/invoices"
    assert endpoint["peer"] == "billing"
    assert endpoint["handler"] is None
    assert str(endpoint["caller"]).endswith("#submit(sig_") or "#" in str(endpoint["caller"])
    workspace.close()


def _orders_controller_facts(root: Path) -> None:
    """A controller exposing exactly one route, POST /v1/orders — deliberately
    narrower than `_controller_facts` (which also exposes two GET routes
    sharing the same path), so a path-only filter in the merge test names the
    merged row unambiguously."""
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
    controller = "com/acme/orders/OrderController#"
    create = "com/acme/orders/OrderController#create(sig_1f0a4c2e)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=create,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=create,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/PostMapping#",
                args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def _orders_client_facts(root: Path) -> None:
    """A client whose one method calls the same wire identity
    `_controller_facts` exposes (POST /v1/orders) — used only to prove the
    cross-direction merge, so the path is hard-coded on the method rather
    than assembled from a prefix."""
    document = Document(
        document_id="doc_2",
        relative_path="com/acme/billing/OrdersClient.java",
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
    client = "com/acme/billing/OrdersClient#"
    submit = "com/acme/billing/OrdersClient#submit(sig_9f1c2b47)."
    facts = [
        SymbolFact(document_id="doc_2", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_2",
            symbol=submit,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_2",
            target=client,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/billing/annotation/ServiceClient#", args={}),
        ),
        AnnotationFact(
            document_id="doc_2",
            target=submit,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/billing/annotation/PostExchange#",
                args={"value": ["/v1/orders"]},
            ),
        ),
    ]
    write_fact_file(root / "OrdersClient.jsonl", document, facts)


def _two_direction_workspace(tmp_path: Path):
    """An inbound controller exposing POST /v1/orders and an outbound client
    calling the very same wire identity, resolved together so the merge in
    `endpoints_merge` has something to collapse."""
    _orders_controller_facts(tmp_path / "facts")
    _orders_client_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    skipped = derive_endpoints(
        workspace,
        [spring, _OUTBOUND_CATALOG],
        capabilities={"annotation_args", "type_annotations"},
    )
    assert skipped == []
    return workspace


def test_a_path_the_module_both_exposes_and_calls_is_one_endpoint_with_both(tmp_path):
    """D02 §3: inbound runs first so the merged row keeps the server's handler
    and gains the client's caller — appearing twice would make every consumer
    re-implement the merge."""
    workspace = _two_direction_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "/v1/orders"]
    assert len(rows) == 1
    [merged] = rows
    assert merged["direction"] == "both"
    assert merged["handler"] is not None and merged["caller"] is not None
    workspace.close()


def _legacy_facts(root: Path) -> None:
    """A client interface with no type-level marker at all — the Retrofit
    shape: the mapping annotation on the method is the whole evidence."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/legacy/LegacyClient.java",
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
    client = "com/acme/legacy/LegacyClient#"
    fetch = "com/acme/legacy/LegacyClient#fetch(sig_2a77e410)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=fetch,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=fetch,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/legacy/annotation/GET#",
                args={"value": "legacy/invoices"},
            ),
        ),
    ]
    write_fact_file(root / "LegacyClient.jsonl", document, facts)


_UNGATED_CATALOG = Catalog(
    id="invented-ungated",
    style="annotation_driven",
    protocol="http",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        # No type-level gate at all: absence, not a marker no fact ever
        # carries.
        "type_annotation": None,
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["path"],
            "peer_from": [],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com/acme/legacy/annotation/Prefix#",
            "annotations": [
                {"fqn": "com/acme/legacy/annotation/GET#", "method": ["GET"]},
            ],
        },
    },
)


def _ungated_workspace(tmp_path):
    _legacy_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_UNGATED_CATALOG], capabilities={"annotation_args"})
    assert skipped == []
    return workspace


def test_a_catalog_with_no_type_gate_matches_on_method_annotations_alone(tmp_path):
    """A Retrofit interface has no type-level marker; the mapping annotation
    is the whole evidence."""
    workspace = _ungated_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert [e["path"] for e in rows] == ["legacy/invoices"]
    workspace.close()


def test_the_service_name_never_leaks_into_the_path(tmp_path):
    """@FeignClient(name=…) with NO path attribute: the prefix is empty, not
    the name — the exact bug the prefix_from/peer_from split exists for."""
    workspace = _outbound_workspace(tmp_path, type_args={"name": "billing"})
    [endpoint] = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert endpoint["path"] == "/invoices"
    assert endpoint["peer"] == "billing"
    workspace.close()


def _inventory_facts(root: Path) -> None:
    """A type-level @HttpExchange("/v1/inventory") that is also, itself, one
    of the mapping annotations — @HttpExchange's shape: it carries the
    prefix and, on a method, a mapping in its own right. Without the
    construct-kind guard the type-level use would mint a phantom endpoint of
    its own."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/inventory/InventoryClient.java",
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
    client = "com/acme/inventory/InventoryClient#"
    levels = "com/acme/inventory/InventoryClient#levels(sig_6b4f9e02)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=levels,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=client,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/inventory/annotation/Exchange#",
                args={"value": ["/v1/inventory"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=levels,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/inventory/annotation/GetExchange#",
                args={"value": ["/levels"]},
            ),
        ),
    ]
    write_fact_file(root / "InventoryClient.jsonl", document, facts)


_UNGATED_PREFIXED_CATALOG = Catalog(
    id="invented-ungated-prefixed",
    style="annotation_driven",
    protocol="http",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": None,
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "peer_from": [],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com/acme/inventory/annotation/Exchange#",
            "annotations": [
                {"fqn": "com/acme/inventory/annotation/Exchange#"},
                {"fqn": "com/acme/inventory/annotation/GetExchange#", "method": ["GET"]},
            ],
        },
    },
)


def _ungated_prefixed_workspace(tmp_path):
    _inventory_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(
        workspace, [_UNGATED_PREFIXED_CATALOG], capabilities={"annotation_args"}
    )
    assert skipped == []
    return workspace


def test_a_type_level_mapping_annotation_mints_no_endpoint_of_its_own(tmp_path):
    """In a catalog with no type gate, a prefix-carrying type-level annotation
    that is also in the mapping list (@HttpExchange's shape) must contribute
    the prefix and nothing else — its type symbol is not a method, and without
    the construct-kind guard it would mint one phantom endpoint per method in
    all_methods (pre-flight ruling R2)."""
    workspace = _ungated_prefixed_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert [(e["method"], e["path"]) for e in rows] == [("GET", "/v1/inventory/levels")]
    workspace.close()


_UNKNOWN_STYLE_CATALOG = """id: invented
style: fluent
protocol: http
direction: inbound
matches: {}
"""

_VALID_CATALOG = """id: invented
style: annotation_driven
protocol: http
direction: inbound
matches: {}
"""


def _catalog_dir(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "invented.yml").write_text(text, encoding="utf-8")
    return root


def test_load_catalogs_names_the_file_and_the_value_when_a_protocol_is_not_a_closed_set_member(
    tmp_path: Path,
):
    """`protocol` and `direction` are closed sets in D00: a value outside one
    is a typo, not a new kind of endpoint. Unchecked, it does not stay in the
    file — it is bound into the derivation and published in metadata.json,
    where it is indistinguishable from something observed. The message names
    the file and the value, because that is what a reader needs (GUIDELINES
    §9)."""
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("http", "htpp"))

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert "htpp" in str(failure.value)
    assert "invented.yml" in str(failure.value)
    assert "http" in str(failure.value)


def test_load_catalogs_rejects_a_direction_outside_the_closed_set(tmp_path: Path):
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("inbound", "incoming"))

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert "incoming" in str(failure.value)
    assert "invented.yml" in str(failure.value)


def test_load_catalogs_names_the_missing_field_when_a_catalog_omits_one(tmp_path: Path):
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("style: annotation_driven\n", ""))

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert "style" in str(failure.value)
    assert "invented.yml" in str(failure.value)


def test_load_catalogs_accepts_a_catalog_whose_values_are_all_in_the_closed_sets(
    tmp_path: Path,
):
    catalog = YamlCatalogSource(_catalog_dir(tmp_path, _VALID_CATALOG)).load()[0]
    assert (catalog.protocol, catalog.direction) == ("http", "inbound")


def test_catalog_naming_a_style_with_no_engine_is_refused_by_file(tmp_path: Path):
    """A style with no engine matches nothing, so it would yield no endpoints
    and no skip — indistinguishable from a framework that exposes none. D02 §2
    declares six styles and this codebase implements one, so the gap is real.

    The reader cannot check it: which engines exist is knowledge of
    `application/resolve`, which `ingress` must not import. So the catalog
    loads and the engine layer refuses it, naming the file — which is what
    `Catalog.source` is carried for."""
    catalogs = YamlCatalogSource(_catalog_dir(tmp_path, _UNKNOWN_STYLE_CATALOG)).load()

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(_UnusedWorkspace(), catalogs, capabilities=set())

    assert "fluent" in str(raised.value)
    assert "annotation_driven" in str(raised.value)
    assert "invented.yml" in str(raised.value)


class _UnusedWorkspace:
    """Refusal comes before any derivation, so a workspace that fails on
    contact proves the catalog was rejected rather than partly run."""

    def load_facts(self, fact_root: Path) -> int:
        raise AssertionError("no fact load for a refused catalog")

    def derive(self, name: str, **params: object) -> None:
        raise AssertionError(f"no derivation for a refused catalog: {name}")

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        raise AssertionError(f"no query for a refused catalog: {name}")

    def close(self) -> None: ...
