"""AWS SQS is delivered when a send through either client is visible.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


@pytest.fixture(scope="module")
def sqs_addresses(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    workspace_dir = tmp_path_factory.mktemp("sqs")
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
            if str(row["protocol"]) == "sqs"
        }
    finally:
        workspace.close()


def test_a_send_through_the_async_client_is_visible(sqs_addresses: set[str]):
    """`G-43`. `SqsAsyncClient` was 0 of 28 methods — and Spring Cloud AWS 3.x
    auto-configures it as the DEFAULT client and backs `SqsTemplate` with it, so the
    unread client is the one a module actually receives.

    The request object is the same `SendMessageRequest` the synchronous client already
    reads; only the terminal owner differs.
    """
    assert any("async-queue" in address for address in sqs_addresses), (
        "a send through SqsAsyncClient derived nothing — the default client in Spring "
        f"Cloud AWS 3.x. Derived: {sorted(sqs_addresses)}"
    )


def test_the_synchronous_client_still_derives(sqs_addresses: set[str]):
    """The control."""
    assert any("raw-queue" in address for address in sqs_addresses), (
        f"the synchronous SqsClient send stopped deriving. Derived: {sorted(sqs_addresses)}"
    )
