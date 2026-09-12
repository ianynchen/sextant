"""AWS SQS is delivered when a send through either client is visible.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"
MICRONAUT = FIXTURES / "orders-micronaut"


@pytest.fixture(scope="module")
def sqs_addresses(analyzed_orders_service: Path) -> set[str]:
    # The session's one `module analyze` of `orders-service` (`tests/conftest.py`), not a
    # run of its own: this fixture only reads rows. MEASURED on PR #20's CI run 34665949923:
    # the e2e files each analysed the same fixture on their own worker at once, and the
    # progress bar sat at 78% for nineteen minutes while all four did.
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
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


@pytest.fixture(scope="module")
def micronaut_sqs_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, direction, path)` for every SQS row `orders-micronaut` derives."""
    workspace_dir = tmp_path_factory.mktemp("mn-sqs")
    compile_fixture(MICRONAUT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(MICRONAUT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["protocol"]), str(row["direction"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "sqs"
        }
    finally:
        workspace.close()


def test_a_micronaut_module_using_the_raw_sqs_sdk_derives_its_queues(micronaut_sqs_rows):
    """`micronaut-sqs`. Micronaut ships no SQS annotation (micronaut-jms-sqs 4.2.0 is a
    JMS ConnectionFactory over SQS and carries none). The raw SDK is how a Micronaut
    module addresses SQS directly, and `aws-sqs-sdk.yml` reads it framework-independently
    — this pins that it does so inside a Micronaut module.

    First run against the literal brief assertion (the full queue URL as `path`) was RED:
    `aws-sqs-sdk.yml`'s own `url` capture splits an absolute queue URL into `peer`
    (`sqs.eu-west-1.amazonaws.com`) and `path` (`/123456789012/mn-audit`) — the same
    CP-2 split its comments document and `sqs_addresses` above already relies on by
    checking only `path`. The row itself derived correctly on the first try; only the
    expected tuple's shape was wrong.
    """
    assert ("sqs", "outbound", "/123456789012/mn-audit") in micronaut_sqs_rows, sorted(
        micronaut_sqs_rows
    )
