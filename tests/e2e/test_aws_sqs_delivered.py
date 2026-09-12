"""AWS SQS is delivered when a send through either client is visible.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest

from fixture_build import FIXTURES
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


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
