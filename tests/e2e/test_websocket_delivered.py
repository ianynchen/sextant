"""WebSocket is delivered when an endpoint registered the way Jakarta WebSocket permits is
visible, whichever of the two registration routes an application used.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest

from fixture_build import FIXTURES
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


@pytest.fixture(scope="module")
def websocket_addresses(analyzed_orders_service: Path) -> set[str]:
    # The session's one `module analyze` of `orders-service` (`tests/conftest.py`), not a
    # run of its own: this fixture only reads rows. MEASURED on PR #20's CI run 34665949923:
    # the e2e files each analysed the same fixture on their own worker at once, and the
    # progress bar sat at 78% for nineteen minutes while all four did.
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
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
