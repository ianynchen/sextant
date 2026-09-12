"""WebSocket is delivered when an endpoint registered the way Jakarta WebSocket permits is
visible, whichever of the two registration routes an application used.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


@pytest.fixture(scope="module")
def websocket_addresses(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    workspace_dir = tmp_path_factory.mktemp("websocket")
    compile_fixture(FIXTURE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            str(row["path"])
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "websocket"
        }
    finally:
        workspace.close()


def test_a_programmatically_registered_endpoint_is_visible(websocket_addresses: set[str]):
    """`G-34`. `@ServerEndpoint` is one of two registration routes the specification
    defines; `ServerEndpointConfig.Builder.create(Class, path)` is the other, and it is
    what an application computing its paths — or serving one endpoint at several — uses.

    Reading only the annotation makes such a module's entire WebSocket surface absent from
    the document with nothing saying so.
    """
    assert "/ws/tickets" in websocket_addresses, (
        "a programmatically registered WebSocket endpoint derived nothing. "
        f"Derived: {sorted(websocket_addresses)}"
    )


def test_the_annotated_registration_still_derives(websocket_addresses: set[str]):
    """The control: a change that made the programmatic route work by breaking the
    annotated one would pass the test above and deliver nothing."""
    assert any(a.startswith("/live") for a in websocket_addresses), (
        f"the @ServerEndpoint route stopped deriving. Derived: {sorted(websocket_addresses)}"
    )
