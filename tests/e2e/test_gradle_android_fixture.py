"""Android parts through the real wrapper (Android design §2a, §2b, M3), over
`fixtures/gradle-android`, through `sextant module analyze` end to end.

The fixture has three parts. `:shared` is Kotlin Multiplatform with a JVM version and an
Android version, each with its own pricing address. `:server` is a Kotlin JVM part that uses
the JVM version of `:shared`. `:app` is an Android app built in two editions (`free`, `paid`),
each edition with its own Retrofit base address, and an OkHttp call shared by both editions.
So the build gives five modules: `app-free`, `app-paid`, `shared-jvm`, `shared-android` and
`server`.

**Self-skipping, like `test_gradle_fixture_builds.py`.** Without an Android SDK
(`ANDROID_HOME` or `ANDROID_SDK_ROOT`) the Android Gradle Plugin cannot build the fixture,
so the test skips with that reason. On a machine whose Gradle caches do not hold the
wrapper distribution or the fixture's dependencies, the offline run fails, and the test
skips with Gradle's own words. CI primes both (`.github/workflows/pr.yml`).

Each run removes the results an earlier run left, before analysis, so stale results never
stand in for this run's.
"""

import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.ingress.detect.gradle import _OFFLINE_REFUSAL_SUBSTRING
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = Path(__file__).parents[2] / "fixtures" / "gradle-android"

# The results folder of each module: a folder that holds two modules keeps one sub-folder
# per module, named by the version or the edition (Android design M6).
RESULTS = {
    "app-free": FIXTURE / "app" / ".sextant" / "free",
    "app-paid": FIXTURE / "app" / ".sextant" / "paid",
    "shared-jvm": FIXTURE / "shared" / ".sextant" / "jvm",
    "shared-android": FIXTURE / "shared" / ".sextant" / "android",
    "server": FIXTURE / "server" / ".sextant",
}


def _clear_stale_workspaces() -> None:
    for folder in (FIXTURE, FIXTURE / "app", FIXTURE / "shared", FIXTURE / "server"):
        shutil.rmtree(folder / ".sextant", ignore_errors=True)


def _outbound_rows(results: Path) -> set[tuple[str, str, str, str, str]]:
    """`(catalog, method, peer, path, resolution)` for every outbound row in one module's
    results."""
    workspace = DuckDbWorkspace(results / "workspace.duckdb")
    try:
        return {
            (
                str(row["catalog_id"]),
                str(row["method"]),
                str(row["peer"]),
                str(row["path"]),
                str(row["resolution"]),
            )
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "outbound"
        }
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def analysis() -> tuple[str, dict[str, set[tuple[str, str, str, str, str]]]]:
    """The output of `module analyze` over the fixture, and each module's outbound rows."""
    if not (os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")):
        pytest.skip(
            "no Android SDK: set ANDROID_HOME (or ANDROID_SDK_ROOT) to build "
            "fixtures/gradle-android"
        )
    _clear_stale_workspaces()
    result = CliRunner().invoke(cli, ["module", "analyze", str(FIXTURE)])
    if result.exit_code != 0:
        message = str(result.exception)
        if "Gradle distribution not present" in message or _OFFLINE_REFUSAL_SUBSTRING in message:
            pytest.skip(
                "the Gradle wrapper distribution or fixtures/gradle-android's dependencies "
                "are not primed on this machine; run the CI prime step in "
                ".github/workflows/pr.yml once with network access. "
                f"Gradle said: {message}"
            )
        raise AssertionError(f"module analyze failed: {result.output}\n{message}")
    return result.output, {name: _outbound_rows(folder) for name, folder in RESULTS.items()}


def _without_retrofit(rows: set[tuple[str, str, str, str, str]]) -> set[tuple[str, ...]]:
    return {row for row in rows if row[0] != "retrofit"}


def test_the_android_fixture_gives_every_module_and_its_outbound_rows(analysis):
    """Each edition of `:app` is its own module and makes the OkHttp call of the code every
    edition shares. Each version of `:shared` calls the pricing address its own `actual`
    gives. The Retrofit rows are checked in the test below.

    `:server` has no row: the call it makes goes through `PricingClient`, which is the
    code of `:shared`, and a module does not publish the rows of a part it uses (F4 §5.2,
    `drop_borrowed_endpoints.sql`). The JVM version of `:shared` publishes that row."""
    output, rows = analysis
    for name in RESULTS:
        assert f"analyzed {name.split('-')[0]} (com.acme:{name})" in output, output
    assert "skipped" not in output, output

    status = ("okhttp", "GET", "status.example.com", "/health", "resolved")
    assert _without_retrofit(rows["app-free"]) == {status}
    assert _without_retrofit(rows["app-paid"]) == {status}
    assert rows["shared-jvm"] == {
        ("ktor-client", "GET", "pricing.internal.example", "/quote/{id}", "resolved")
    }
    assert rows["shared-android"] == {
        ("ktor-client", "GET", "pricing.example.com", "/quote/{id}", "resolved")
    }
    assert rows["server"] == set()


@pytest.mark.xfail(
    strict=True,
    reason="Retrofit's base address is not joined to the interface's path: each edition "
    "gives (retrofit, GET, None, orders/{id}, resolved), so the editions cannot be told "
    "apart (Android outbound Task 5 finding)",
)
def test_each_edition_calls_its_own_retrofit_address(analysis):
    """`BuildConfig.API_URL` is a different constant in each edition, and the compiler
    copies it into `Orders`'s static initializer, where `Retrofit.Builder().baseUrl(...)`
    receives it. So each edition calls its own address."""
    _, rows = analysis
    assert {row for row in rows["app-free"] if row[0] == "retrofit"} == {
        ("retrofit", "GET", "free.api.example", "/orders/{id}", "resolved")
    }
    assert {row for row in rows["app-paid"] if row[0] == "retrofit"} == {
        ("retrofit", "GET", "paid.api.example", "/orders/{id}", "resolved")
    }
