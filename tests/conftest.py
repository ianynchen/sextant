"""The one fixture-build step that cannot live beside the test that needs it.

`fixtures/orders-service` declares a dependency on `com.example:orders-soap-client`
(2I Task 6's opt-in library extraction), and Maven resolves every declared
dependency before it compiles anything — so the ~30 `mvn -o compile` calls
scattered through this suite all fail unless that artifact is in the local
repository first. Installing it is therefore a precondition of the suite, not of
one test, which is what makes it a session fixture here rather than a call in
each file. The build-and-install logic itself lives in `fixture_stub.py`,
because CI's priming step needs it before the suite exists.
"""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

import fixture_stub
from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli


@pytest.fixture(scope="session", autouse=True)
def stub_library_in_the_local_repository() -> Path:
    """Built and installed once per session, and skipped entirely when it is
    already current — every test in this suite depends on it, including the ones
    that never touch Maven, so the up-to-date path must cost nothing."""
    jar = fixture_stub.local_repository_jar()
    if fixture_stub.is_current(jar):
        return jar
    return fixture_stub.compile_and_install(offline=True)


@pytest.fixture(scope="session")
def analyzed_orders_service(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`orders-service`, analysed once, for tests that only READ the result.

    MEASURED 2026-09-11: `tests/cli/test_app.py` ran `module analyze` 33 times, 31 of them
    the identical command, at roughly 15s each — to produce a workspace that is identical
    every time. Sixteen of its tests then only read `metadata.json` or query the workspace.

    **Read-only, and that is load-bearing.** The directory is shared, so a test that
    RENDERS, EXPORTS or ENRICHES into it would leave the next test reading something the
    analysis did not produce. Those keep their own run — as do the fourteen that spy on
    the detector, vary a flag, or deliberately mangle a POM to test an error path, none of
    which can observe a run that already happened.
    """
    workspace = tmp_path_factory.mktemp("analyzed-orders-service")
    compile_fixture(FIXTURES / "orders-service")
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURES / "orders-service"), "--workspace", str(workspace)]
    )
    assert result.exit_code == 0, result.output
    return workspace


@pytest.fixture
def analyzed_workspace_copy(analyzed_orders_service: Path, tmp_path: Path) -> Path:
    """A private copy of the analysed workspace, for tests that WRITE into one.

    `render`, `export` and `enrich` all write into the workspace directory, so they cannot
    share the session copy — but they do not need to re-derive it either. Copying costs
    well under a second against roughly fifteen for an analysis, and the analysis is what
    the test is not about.
    """
    private = tmp_path / "workspace"
    shutil.copytree(analyzed_orders_service, private)
    return private
