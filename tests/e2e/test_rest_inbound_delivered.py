"""REST inbound is delivered when every way a Spring Boot module exposes an HTTP endpoint
is visible. This file grows one shape at a time; each test names the shape and the gap it
closed.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


@pytest.fixture(scope="module")
def http_routes(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(catalog, method, path)` for every inbound HTTP row the fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("rest-in")
    compile_fixture(FIXTURE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["catalog_id"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "http" and str(row["direction"]) == "inbound"
        }
    finally:
        workspace.close()


def test_a_data_rest_resource_over_mongodb_derives_its_route_table(http_routes):
    """`G-45`. Spring Data REST reads the JPA repository contracts only, so a
    `MongoRepository` — which Spring Data REST exposes identically, and which extends the
    very `ListCrudRepository` the roster names — derived nothing. The parent is reached
    through a jar hop the fact stream does not cross, so naming the parent is not enough:
    the roster has to name the store contract itself.
    """
    expected = {
        ("spring-data-rest", "GET", "/shipments"),
        ("spring-data-rest", "POST", "/shipments"),
        ("spring-data-rest", "GET", "/shipments/{id}"),
        ("spring-data-rest", "PUT", "/shipments/{id}"),
        ("spring-data-rest", "PATCH", "/shipments/{id}"),
        ("spring-data-rest", "DELETE", "/shipments/{id}"),
    }
    missing = expected - http_routes
    assert missing == set(), (
        f"a MongoRepository behind @RepositoryRestResource derived {6 - len(missing)} of 6 "
        f"routes. Missing: {sorted(missing)}"
    )


def test_the_jpa_resource_still_derives(http_routes):
    """The control: `CatalogRepository`, exposed at `/orderViews`, derived before this."""
    assert ("spring-data-rest", "GET", "/orderViews") in http_routes, (
        "the JPA-backed Data REST resource stopped deriving"
    )
