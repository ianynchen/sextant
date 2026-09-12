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
