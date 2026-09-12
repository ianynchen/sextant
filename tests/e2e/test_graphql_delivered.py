"""GraphQL is delivered when a DGS resolver declared the way DGS permits derives every
field it serves, and a federation entity fetcher is visible at all.

**Not a document check.** This asserts what Sextant produces from bytecode `mvn` built
from a fixture that uses the framework the way an application does.
"""

from pathlib import Path

import pytest

from fixture_build import FIXTURES
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


@pytest.fixture(scope="module")
def graphql_addresses(analyzed_orders_service: Path) -> set[str]:
    # The session's one `module analyze` of `orders-service` (`tests/conftest.py`), not a
    # run of its own: this fixture only reads rows. MEASURED on PR #20's CI run 34665949923:
    # the e2e files each analysed the same fixture on their own worker at once, and the
    # progress bar sat at 78% for nineteen minutes while all four did.
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return {
            str(row["path"])
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "graphql"
        }
    finally:
        workspace.close()


def test_one_resolver_serving_two_fields_derives_both(graphql_addresses: set[str]):
    """`G-39`. `@DgsData` is `@Repeatable(DgsData.List.class)` — confirmed in
    `graphql-dgs`'s own class file — and DGS registers both through
    `getMergedRepeatableAnnotations`. Reading only the first silently halves a resolver's
    surface: the second field is served in production and absent from the document.

    Repeatable annotations reach a catalog through `container:`, which five other catalogs
    declare. The container is the NESTED type `DgsData$List`; the source-level spelling
    would match nothing while this test passed for the wrong reason.
    """
    missing = {a for a in ("Order.dgsTotal", "Order.dgsSubtotal") if a not in graphql_addresses}
    assert missing == set(), (
        f"a DGS resolver serving two fields derived {2 - len(missing)} of 2. "
        f"Missing: {sorted(missing)}. Derived: {sorted(graphql_addresses)}"
    )


def test_a_federation_entity_fetcher_is_visible(graphql_addresses: set[str]):
    """`G-40`. `@DgsEntityFetcher(name = "Order")` is Apollo Federation's `_entities`
    resolution path — a separate registration in DGS's own provider. It names a TYPE
    rather than a schema field, so its identity is the type name, and before this it
    derived nothing at all: a federated graph's entity resolution was invisible.
    """
    assert "Order" in graphql_addresses or "_entities.Order" in graphql_addresses, (
        "a @DgsEntityFetcher derived no row — a federated graph's entity resolution is "
        f"invisible. Derived: {sorted(graphql_addresses)}"
    )


def test_the_existing_resolver_forms_still_derive(graphql_addresses: set[str]):
    """The control. A change making the new forms work by breaking the old ones would pass
    both tests above and deliver nothing."""
    for address in ("dgsOrders", "Order.dgsLines"):
        assert address in graphql_addresses, f"{address} stopped deriving"
