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

import os
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


# The files that run the whole pipeline, dispatched FIRST under `--dist loadfile`.
#
# MEASURED on PR #20's CI run 34665949923 (2026-09-12): the last 3% of the suite took 3:30
# — one worker on the slowest file while three sat idle. `loadfile` hands each file to one
# worker whole, and the pipeline-running files sit late in collection order, so whichever
# worker drew one last ran it alone. Putting them first lets the fast files fill in behind.
# Same tests, same workers, same fixtures — only the order changes. (The nineteen-minute
# stall at 78% in that run was a different thing: every e2e file analysing the same fixture
# on its own worker at once; those now share the session's run.)
_PIPELINE_FILES = (
    "tests/cli/test_app.py",
    "tests/e2e/test_vertical_slice.py",
    "tests/application/test_pipeline.py",
    "tests/api/test_facade.py",
    "tests/cli/test_enrich_command.py",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = Path(str(config.rootpath))
    slow = [i for i in items if str(Path(i.path).relative_to(root)) in _PIPELINE_FILES]
    fast = [i for i in items if str(Path(i.path).relative_to(root)) not in _PIPELINE_FILES]
    items[:] = slow + fast


# EXPERIMENT (docs/performance.md P-2): under xdist, every worker's DuckDB connections
# share the runner's cores with three other workers' JVMs and DuckDBs. One thread per
# connection per worker is the hypothesis; the CI run this ships on is the measurement.
if os.environ.get("PYTEST_XDIST_WORKER"):
    os.environ.setdefault("SEXTANT_DUCKDB_THREADS", "1")
