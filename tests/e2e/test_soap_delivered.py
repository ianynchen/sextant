"""SOAP is delivered when a Spring-WS endpoint declared the way Spring-WS permits derives
every message it serves.

**Not a document check.** This asserts what Sextant produces from real bytecode built by
`mvn` from a fixture that uses the framework the way an application does. It cannot be
satisfied by editing `COVERAGE.md`, and it goes green only when the feature works.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"
NS = "http://orders.example.com/ws"


@pytest.fixture(scope="module")
def soap_addresses(tmp_path_factory) -> set[str]:
    workspace_dir = tmp_path_factory.mktemp("soap")
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
            if str(row["protocol"]) == "soap"
        }
    finally:
        workspace.close()


def test_one_handler_serving_two_message_types_derives_both(soap_addresses: set[str]):
    """`@PayloadRoot` is `@Repeatable(PayloadRoots.class)` — confirmed in spring-ws-core's
    own class file — and Spring-WS routes BOTH messages to the annotated method.

    Reading only the first silently halves a SOAP service's surface: the second message
    type is served in production and absent from the document. Repeatable annotations are
    read through a catalog's `container:` key, which five other catalogs declare.
    """
    missing = {
        address
        for address in (f"{{{NS}}}amendOrderRequest", f"{{{NS}}}reviseOrderRequest")
        if address not in soap_addresses
    }
    assert missing == set(), (
        f"a Spring-WS handler serving two message types derived {2 - len(missing)} of 2. "
        f"Missing: {sorted(missing)}. Derived soap addresses: {sorted(soap_addresses)}"
    )


def test_the_single_payload_root_and_soap_action_forms_still_derive(soap_addresses: set[str]):
    """The control. A change that made the repeatable form work by breaking the singular
    one would pass the test above and deliver nothing."""
    for address in (
        f"{{{NS}}}placeOrderRequest",
        "http://orders.example.com/action/cancelOrder",
    ):
        assert address in soap_addresses, f"{address} stopped deriving"
