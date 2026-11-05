"""Retrofit clients that Dagger makes (spec 2026-11-05 di-recipe-hop, OI-304), over
`fixtures/orders-dagger`, through `sextant module analyze` end to end.

A parameter the container fills receives the value of the one recipe (`@Provides` method) the
container chooses for it, so a client made from an injected `Retrofit` takes the address that
recipe's builder sets. Real bytecode (Kotlin 2.4.20 with kapt, Dagger 2.57.2, JDK 21): Dagger's
processor checked every component's wiring when the fixture was built, so each pinned address is
the one the app really gets.

Two rows stay `partial` with no server address, never a guess: `region`, whose
`@Named("regional")` key has two recipes in the module (one per component), and `shared`, whose
recipe is in another build module (`orders-dagger-network`, a jar).
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-dagger"


@pytest.fixture(scope="module")
def retrofit_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple]:
    workspace_dir = tmp_path_factory.mktemp("orders-dagger")
    compile_fixture(_ROOT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(_ROOT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (row["method"], row["peer"], row["path"], row["resolution"])
            for row in workspace.query("endpoints")
            if row["catalog_id"] == "retrofit"
        }
    finally:
        workspace.close()


def test_every_retrofit_row_has_the_address_of_the_recipe_dagger_chooses(retrofit_rows: set):
    """Each row against the source:

    - `/orders`: `NetworkModule` (a Kotlin `object`), `ordersApi(retrofit)` takes the
      unqualified `retrofit()`, built with `BuildConfig.API_URL`.
    - `/pay`: `payApi(@Named("pay") ...)` takes `payRetrofit()`.
    - `/bills`: `BillingModule` (a `class`), `@Billing` (a custom qualifier) takes
      `billingRetrofit()`.
    - `/config`: `configRetrofit(@Named("baseUrl") url)` is built from the qualified base
      `String` `baseUrl()` returns; the unqualified `userAgent()` is not a candidate.
    - `/status`: the `@Inject` constructor of `StatusClient` makes the client from
      `@Named("status") statusRetrofit()`.
    - `/j`: `JavaModule`, a Java module with static recipes, `@Named("j")`.
    - `region`: `euRetrofit()` and `usRetrofit()` share the key `@Named("regional")`.
    - `shared`: `@Named("shared")` is provided in `orders-dagger-network`, not in this module.
    """
    assert retrofit_rows == {
        ("GET", "orders.example.com", "/orders", "resolved"),
        ("GET", "pay.example.com", "/pay", "resolved"),
        ("GET", "billing.example.com", "/bills", "resolved"),
        ("GET", "config.example.com", "/config", "resolved"),
        ("GET", "status.example.com", "/status", "resolved"),
        ("GET", "j.example.com", "/j", "resolved"),
        ("GET", None, "region", "partial"),
        ("GET", None, "shared", "partial"),
    }
