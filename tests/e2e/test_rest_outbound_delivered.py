"""REST outbound is delivered when every way a Spring Boot module calls an HTTP endpoint is
visible. Each test names the shape.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

SPRING7 = FIXTURES / "orders-spring7"


@pytest.fixture(scope="module")
def spring7_outbound(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    workspace_dir = tmp_path_factory.mktemp("rest-out")
    compile_fixture(SPRING7)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(SPRING7), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["catalog_id"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "outbound"
        }
    finally:
        workspace.close()


def test_an_http_interface_registered_by_import_http_services_derives(spring7_outbound):
    """Spring 7's `@ImportHttpServices` registers `@HttpExchange` interfaces as proxied
    beans in one declaration, replacing the per-interface `HttpServiceProxyFactory`
    wiring of 6.x.

    MEASURED 2026-09-11: this derived before any catalog read the registration
    annotation, because the wire identity lives on the interface's own `@HttpExchange`
    and `spring-http-interface.yml` reads that with `declared_on: interface`. The gap
    COVERAGE stated — "registration unread" — implied missing rows; there were none. This
    test pins that the Spring 7 form keeps deriving, which is the claim that matters.
    """
    assert ("spring-http-interface", "GET", "/inventory/levels/{sku}") in spring7_outbound, (
        f"an @ImportHttpServices-registered interface stopped deriving. "
        f"Derived: {sorted(spring7_outbound)}"
    )


GATEWAY = FIXTURES / "orders-gateway"


@pytest.fixture(scope="module")
def gateway_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every endpoint row the Spring Cloud Gateway fixture derives, whole."""
    workspace_dir = tmp_path_factory.mktemp("gateway-out")
    compile_fixture(GATEWAY)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(GATEWAY), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints")]
    finally:
        workspace.close()


def test_gateway_targets_derive_outbound(gateway_rows):
    """`spring-cloud-gateway-outbound`, spec §14 test 11: every `uri(…)` a route's lambda
    ends in, read through `lambda_steps` on both static receiver types (`BooleanSpec.uri`
    after a predicate, `UriSpec.uri` after `filters(…)`), kept WHOLE — a routing
    destination, not a request URL: `lb://orders-service` names a load-balanced service,
    and splitting it into a peer and a path would publish an address the gateway never
    dials. `peer` NULL on every row, no verb, caller = `routes`.

    `uri(billing)` reads `http://billing-service` at `resolved`: `billing` is a `final
    String` field with a literal initialiser — a constant variable (JLS §4.12.4) — so
    javac writes the literal itself at the call (`ldc`, measured on the compiled
    fixture), and the lambda still captures `this` for it. A field that is not a constant
    would arrive as a `field` read and the row would be `unresolved`; this pin moves the
    day the fixture's field stops being one.

    Exactly seven rows: one per `route(…)` call, both overloads."""
    rows = [
        r
        for r in gateway_rows
        if r["catalog_id"] == "spring-cloud-gateway-outbound" and r["direction"] == "outbound"
    ]
    targets = {(r["path"], r["resolution"]) for r in rows}
    assert targets == {
        ("http://orders-service", "resolved"),
        ("lb://orders-service", "resolved"),
        ("http://ab-service", "resolved"),
        ("http://public-service", "resolved"),
        ("http://legacy-service", "resolved"),
        ("http://billing-service", "resolved"),
        ("http://host-service", "resolved"),
    }, sorted(targets, key=str)
    assert len(rows) == 7, sorted(targets, key=str)
    assert all(r["peer"] is None and r["method"] is None for r in rows), rows
    assert all("#routes(" in str(r["caller"]) for r in rows), sorted({r["caller"] for r in rows})
