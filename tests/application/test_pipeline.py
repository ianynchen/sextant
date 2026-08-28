import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import resolve
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


def test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end(tmp_path: Path):
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
        YamlCatalogSource(catalogs_dir()),
        {"annotation_args", "typed_signatures"},
    )
    workspace.close()

    routes = {(e["method"], e["path"]) for e in report.endpoints}
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders/{id}/{view}"),
        ("GET", "/v1/orders"),
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
    }
    # One row per mapped method, not one per (method, same-named sibling) pair:
    # the fixture's two `get` overloads share a name, and a symbol that does not
    # disambiguate them (D00 §1) makes this join multiply instead of match.
    assert len(report.endpoints) == 17
    assert report.skipped_catalogs == []


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
    assert SkippedCatalog("spring-web", ("annotation_args",)) in report.skipped_catalogs
