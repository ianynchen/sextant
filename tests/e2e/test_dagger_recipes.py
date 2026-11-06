"""Retrofit clients that Dagger makes (spec 2026-11-05 di-recipe-hop, OI-304), over
`fixtures/orders-dagger`, through `sextant module analyze` end to end.

A parameter the container fills receives the value of the one recipe (`@Provides` method) the
container chooses for it, so a client made from an injected `Retrofit` takes the address that
recipe's builder sets. Real bytecode (Kotlin 2.4.20 with kapt, Dagger 2.57.2, JDK 21): Dagger's
processor checked every component's wiring when the fixture was built, so each pinned address is
the one the app really gets.

Two rows stay `partial` with no server address, never a guess: `region`, whose
`@Named("regional")` key has two recipes in the module (one per component), and `shared`, whose
recipe is in a jar the analysis does not scan (`orders-dagger-network`).

A reactor SIBLING is not such a jar: the detector scans a sibling the module depends on, so its
recipes are read with the module's own (`fixtures/orders-dagger-reactor`, the Android shape
`:core:network` -> `:app`), and a key is unique only over the two together.
"""

import shutil

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-dagger"
_REACTOR = FIXTURES / "orders-dagger-reactor"


def _retrofit_rows(workspace_file) -> set[tuple]:
    workspace = DuckDbWorkspace(workspace_file)
    try:
        return {
            (row["method"], row["peer"], row["path"], row["resolution"])
            for row in workspace.query("endpoints")
            if row["catalog_id"] == "retrofit"
        }
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def retrofit_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple]:
    workspace_dir = tmp_path_factory.mktemp("orders-dagger")
    compile_fixture(_ROOT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(_ROOT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return _retrofit_rows(workspace_dir / "workspace.duckdb")


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


def test_a_recipe_in_a_reactor_sibling_is_read_with_the_module_s_own(
    tmp_path_factory: pytest.TempPathFactory,
):
    """Analysed at the reactor ROOT, in a copy, as `test_stitch_links.py` does. Each row
    against the source:

    - `/core`: `app`'s `ApiModule.coreApi(@Named("core") Retrofit)`; the only `@Named("core")`
      recipe is `network`'s `CoreNetworkModule.coreRetrofit()`, `https://core.example.com/`.
    - `edge`: `@Named("edge")` has `network`'s `NetworkEdgeModule.edgeRetrofit()` and `app`'s
      `LocalEdgeModule.edgeRetrofit()`, one per component: two recipes over the module and its
      sibling, so not chosen.
    """
    compile_fixture(_REACTOR)
    reactor = tmp_path_factory.mktemp("dagger-reactor") / "orders-dagger-reactor"
    shutil.copytree(_REACTOR, reactor)
    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])
    assert result.exit_code == 0, result.output

    assert _retrofit_rows(reactor / "app" / ".sextant" / "workspace.duckdb") == {
        ("GET", "core.example.com", "/core", "resolved"),
        ("GET", None, "edge", "partial"),
    }
